import sys
from pathlib import Path
from PySide2.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction
from PySide2.QtGui import QIcon
from PySide2.QtQml import QQmlApplicationEngine
from PySide2.QtCore import QObject, Signal, Property, Slot, QRunnable, QThreadPool, QTimer
from datetime import datetime
import pytz
import traceback
import json
import os
import core

IST = pytz.timezone("Asia/Calcutta")
SETTINGS_FILE = "auto_update_settings.json"

class MainWindow(QObject):
    progressChanged = Signal(int, int)

    def __init__(self):
        super().__init__()
        self._status = "Ready"
        self._lastUpdated = "Never"
        self.threadpool = QThreadPool()
        self._logs = []
        self.progress = 0
        
        # Auto-update settings
        self._autoUpdateEnabled = False
        self._autoUpdateInterval = 15  # minutes
        self.loadSettings()
        
        # Auto-update timer
        self.autoUpdateTimer = QTimer()
        self.autoUpdateTimer.timeout.connect(self.onAutoUpdateTrigger)
        if self._autoUpdateEnabled:
            self.startAutoUpdate()

    def loadSettings(self):
        """Load auto-update settings from file"""
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                    self._autoUpdateEnabled = settings.get('enabled', False)
                    self._autoUpdateInterval = settings.get('interval', 15)
        except Exception as e:
            print(f"Error loading settings: {e}")
    
    def saveSettings(self):
        """Save auto-update settings to file"""
        try:
            settings = {
                'enabled': self._autoUpdateEnabled,
                'interval': self._autoUpdateInterval
            }
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def startAutoUpdate(self):
        """Start the auto-update timer"""
        if self._autoUpdateInterval > 0:
            interval_ms = self._autoUpdateInterval * 60 * 1000  # Convert minutes to milliseconds
            self.autoUpdateTimer.start(interval_ms)
            self._logs.append(f"⏰ Auto-update enabled: every {self._autoUpdateInterval} minutes")
            self.logChanged.emit()
    
    def stopAutoUpdate(self):
        """Stop the auto-update timer"""
        self.autoUpdateTimer.stop()
        self._logs.append("⏰ Auto-update disabled")
        self.logChanged.emit()
    
    @Slot()
    def onAutoUpdateTrigger(self):
        """Called when auto-update timer triggers"""
        self._logs.append(f"⏰ Auto-update triggered at {datetime.now(IST).strftime('%d-%m-%Y %H:%M')}")
        self.logChanged.emit()
        self.upload()
    
    @Slot()
    def checkDbConnection(self):
        self._status = "Checking database connection..."
        self.statusChanged.emit()
        try:
            if hasattr(core, "connect_to_sql"):
                conn = core.connect_to_sql()
                conn.close()
            self._logs.append("✅ Database connection successful.")
            self._status = "✅ Database connection successful."
        except Exception as e:
            self._status = "❌ Cannot connect to database."
            self._logs.append(f"❌ Database connection failed: {str(e)}")
        self.statusChanged.emit()
        self.logChanged.emit()

    def loadLastUpdated(self):
        try:
            ts = core.firestore_db.collection("DB_Service").document("serverSideData").get().to_dict().get("latestImportFromServer", None)

            if isinstance(ts, datetime):
                dt = ts.astimezone(IST)
            elif isinstance(ts, str):
                dt = datetime.fromisoformat(ts).replace(tzinfo=pytz.utc).astimezone(IST)
            elif isinstance(ts, (int, float)):
                dt = datetime.utcfromtimestamp(ts / 1000).replace(tzinfo=pytz.utc).astimezone(IST)
            else:
                dt = None

            if dt:
                self._lastUpdated = dt.strftime("%d-%m-%Y %H:%M")
            else:
                self._lastUpdated = "Unknown"
        except Exception as e:
            print("Error in loadLastUpdated:", e)
            self._lastUpdated = "Unknown"

    @Slot()
    def clearAndUploadAll(self):
        self._status = "Clearing and uploading..."
        self.statusChanged.emit()

        # Reset logs and progress
        self._logs = []
        self.logChanged.emit()
        self.progressChanged.emit(0, 1)

        # Start threaded work
        worker = Worker(self.performClearAndUpload)
        self.threadpool.start(worker)

    def performClearAndUpload(self):
        try:
            def log(msg):
                print(msg)
                self._logs.append(msg)
                self.logChanged.emit()

            def on_progress(done, total):
                self.progressChanged.emit(done, total if total > 0 else 1)

            item_count, image_count, now, _ = core.clear_and_full_upload(
                log_func=log,
                on_progress=on_progress
            )

            dt = now.replace(tzinfo=pytz.utc).astimezone(IST)
            self._status = f"✅ Uploaded {item_count} items"
            self._lastUpdated = dt.strftime("%d-%m-%Y %H:%M")

        except Exception as e:
            traceback.print_exc()
            self._status = f"❌ Error: {str(e)}"
            self._logs.append(str(e))
            self.logChanged.emit()
        finally:
            self.statusChanged.emit()
            self.lastUpdatedChanged.emit()
            self.logChanged.emit()

    @Signal
    def statusChanged(self): pass
    def getStatus(self): return self._status
    status = Property(str, getStatus, notify=statusChanged)

    @Signal
    def lastUpdatedChanged(self): pass
    def getLastUpdated(self): return self._lastUpdated
    lastUpdated = Property(str, getLastUpdated, notify=lastUpdatedChanged)

    @Signal
    def logChanged(self): pass
    def getLogs(self): return "\n".join(self._logs)
    logs = Property(str, getLogs, notify=logChanged)
    
    @Signal
    def autoUpdateEnabledChanged(self): pass
    def getAutoUpdateEnabled(self): return self._autoUpdateEnabled
    def setAutoUpdateEnabled(self, enabled):
        if self._autoUpdateEnabled != enabled:
            self._autoUpdateEnabled = enabled
            self.saveSettings()
            if enabled:
                self.startAutoUpdate()
            else:
                self.stopAutoUpdate()
            self.autoUpdateEnabledChanged.emit()
    autoUpdateEnabled = Property(bool, getAutoUpdateEnabled, setAutoUpdateEnabled, notify=autoUpdateEnabledChanged)
    
    @Signal
    def autoUpdateIntervalChanged(self): pass
    def getAutoUpdateInterval(self): return self._autoUpdateInterval
    def setAutoUpdateInterval(self, interval):
        if self._autoUpdateInterval != interval and interval > 0:
            self._autoUpdateInterval = interval
            self.saveSettings()
            if self._autoUpdateEnabled:
                # Restart timer with new interval
                self.stopAutoUpdate()
                self.startAutoUpdate()
            self.autoUpdateIntervalChanged.emit()
    autoUpdateInterval = Property(int, getAutoUpdateInterval, setAutoUpdateInterval, notify=autoUpdateIntervalChanged)
    
    @Slot()
    def showWindow(self):
        """Show the main window"""
        if hasattr(self, 'qmlWindow') and self.qmlWindow:
            self.qmlWindow.show()
            self.qmlWindow.raise_()
            self.qmlWindow.requestActivate()
    
    @Slot()
    def hideWindow(self):
        """Hide the main window"""
        if hasattr(self, 'qmlWindow') and self.qmlWindow:
            self.qmlWindow.hide()
    
    @Slot()
    def toggleWindow(self):
        """Toggle window visibility"""
        if hasattr(self, 'qmlWindow') and self.qmlWindow:
            if self.qmlWindow.isVisible():
                self.hideWindow()
            else:
                self.showWindow()
    
    def setupTrayIcon(self, app):
        """Setup system tray icon with context menu"""
        self.trayIcon = QSystemTrayIcon(app)
        
        # Try to set icon, fallback to default if not found
        icon_path = os.path.join(os.path.dirname(__file__), "icons", "app_icon.png")
        if os.path.exists(icon_path):
            self.trayIcon.setIcon(QIcon(icon_path))
        else:
            self.trayIcon.setIcon(app.style().standardIcon(app.style().SP_ComputerIcon))
        
        # Create context menu
        tray_menu = QMenu()
        
        show_action = QAction("Show", app)
        show_action.triggered.connect(self.showWindow)
        tray_menu.addAction(show_action)
        
        sync_action = QAction("Sync Now", app)
        sync_action.triggered.connect(self.upload)
        tray_menu.addAction(sync_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("Quit", app)
        quit_action.triggered.connect(app.quit)
        tray_menu.addAction(quit_action)
        
        self.trayIcon.setContextMenu(tray_menu)
        self.trayIcon.activated.connect(self.onTrayIconActivated)
        self.trayIcon.setToolTip("GA Price Uploader")
        self.trayIcon.show()
    
    def onTrayIconActivated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.DoubleClick or reason == QSystemTrayIcon.Trigger:
            self.toggleWindow()

    @Slot()
    def upload(self):
        self._status = "Uploading..."
        self.statusChanged.emit()
        worker = Worker(self.performUpload)
        self.threadpool.start(worker)

    def performUpload(self):
        try:
            item_count, image_count, now, logs = core.run_sync()
            dt = now.replace(tzinfo=pytz.utc).astimezone(IST)
            self._status = f"Success: {item_count} items, {image_count} images"
            self._lastUpdated = dt.strftime("%d-%m-%Y %H:%M")
            self._logs = logs
        except Exception as e:
            traceback.print_exc()
            self._status = f"Error: {str(e)}"
            self._logs.append(str(e))
        finally:
            self.statusChanged.emit()
            self.lastUpdatedChanged.emit()
            self.logChanged.emit()


class Worker(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        self.fn()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Don't quit when window is hidden
    
    engine = QQmlApplicationEngine()
    win = MainWindow()
    engine.rootContext().setContextProperty("backend", win)
    win.progressChanged.connect(lambda value: engine.rootObjects()[0].setProperty("uploadProgress", value))
    engine.load(Path("GUI/main.qml").as_posix())

    if not engine.rootObjects():
        sys.exit(-1)
    
    # Store reference to QML window
    win.qmlWindow = engine.rootObjects()[0]
    
    # Setup system tray
    win.setupTrayIcon(app)
    
    # Track visibility state to show notification only when actually minimizing
    win._wasVisible = True
    def on_visibility_changed():
        is_visible = win.qmlWindow.isVisible()
        # Show notification only when transitioning from visible to hidden
        if win._wasVisible and not is_visible:
            win.trayIcon.showMessage(
                "GA Price Uploader", 
                "App minimized to system tray",
                QSystemTrayIcon.Information,
                2000
            )
        win._wasVisible = is_visible
    
    win.qmlWindow.visibilityChanged.connect(on_visibility_changed)

    # After the UI is loaded and event loop starts, check DB connection
    from PySide2.QtCore import QTimer, QCoreApplication
    def delayed_check():
        QCoreApplication.instance().processEvents()  # flush UI events
        win.loadLastUpdated()  # Load last updated timestamp
        win.checkDbConnection()
    QTimer.singleShot(500, delayed_check)  # 500ms to ensure UI is visible

    sys.exit(app.exec_())
