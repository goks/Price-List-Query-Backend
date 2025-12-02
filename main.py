import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QObject, Signal, Property, Slot, QRunnable, QThreadPool, QTimer
from datetime import datetime
from typing import Any, Optional
import pytz
import traceback
import json
import os
import winreg
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
        self._logs: list[str] = []
        self.progress = 0
        self.qmlWindow: Optional[Any] = None  # type: ignore
        self._wasVisible = True
        
        # Auto-update settings
        self._autoUpdateEnabled = True  # Auto-update enabled by default
        self._autoUpdateInterval = 4  # hours
        self._autostartEnabled = True  # Default enabled
        
        # Database settings
        self._dbServer = r"GASERVER\BUSYSTDSQL"
        self._dbName = "BusyComp0004_db12025"
        
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
                    self._autoUpdateEnabled = settings.get('enabled', True)
                    self._autoUpdateInterval = settings.get('interval', 4)
                    self._autostartEnabled = settings.get('autostart', True)
                    self._dbServer = settings.get('dbServer', r"GASERVER\BUSYSTDSQL")
                    self._dbName = settings.get('dbName', "BusyComp0004_db12025")
        except Exception as e:
            print(f"Error loading settings: {e}")
    
    def saveSettings(self):
        """Save auto-update settings to file"""
        try:
            settings = {
                'enabled': self._autoUpdateEnabled,
                'interval': self._autoUpdateInterval,
                'autostart': self._autostartEnabled,
                'dbServer': self._dbServer,
                'dbName': self._dbName
            }
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def startAutoUpdate(self):
        """Start the auto-update timer"""
        if self._autoUpdateInterval > 0:
            interval_ms = self._autoUpdateInterval * 60 * 60 * 1000  # Convert hours to milliseconds
            self.autoUpdateTimer.start(interval_ms)
            self._logs.append(f"⏰ Auto-update enabled: every {self._autoUpdateInterval} hours")
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
            doc_dict = core.firestore_db.collection("DB_Service").document("serverSideData").get().to_dict()
            ts = doc_dict.get("latestImportFromServer", None) if doc_dict else None  # type: ignore

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
        finally:
            self.lastUpdatedChanged.emit()  # Notify QML that lastUpdated has changed

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

    statusChanged = Signal()  # type: ignore
    def getStatus(self): return self._status
    status = Property(str, getStatus, notify=statusChanged)  # type: ignore

    lastUpdatedChanged = Signal()  # type: ignore
    def getLastUpdated(self): return self._lastUpdated
    lastUpdated = Property(str, getLastUpdated, notify=lastUpdatedChanged)  # type: ignore

    logChanged = Signal()  # type: ignore
    def getLogs(self): return "\n".join(self._logs)
    logs = Property(str, getLogs, notify=logChanged)  # type: ignore
    
    autoUpdateEnabledChanged = Signal()  # type: ignore
    def getAutoUpdateEnabled(self): return self._autoUpdateEnabled
    def setAutoUpdateEnabled(self, enabled):
        if self._autoUpdateEnabled != enabled:
            self._autoUpdateEnabled = enabled
            self.saveSettings()
            if enabled:
                self.startAutoUpdate()
            else:
                self.stopAutoUpdate()
            self.autoUpdateEnabledChanged.emit()  # type: ignore
    autoUpdateEnabled = Property(bool, getAutoUpdateEnabled, setAutoUpdateEnabled, notify=autoUpdateEnabledChanged)  # type: ignore
    
    autoUpdateIntervalChanged = Signal()  # type: ignore
    def getAutoUpdateInterval(self): return self._autoUpdateInterval
    def setAutoUpdateInterval(self, interval):
        if self._autoUpdateInterval != interval and interval > 0:
            self._autoUpdateInterval = interval
            self.saveSettings()
            if self._autoUpdateEnabled:
                # Restart timer with new interval
                self.stopAutoUpdate()
                self.startAutoUpdate()
            self.autoUpdateIntervalChanged.emit()  # type: ignore
    autoUpdateInterval = Property(int, getAutoUpdateInterval, setAutoUpdateInterval, notify=autoUpdateIntervalChanged)  # type: ignore
    
    def setWindowsAutostart(self, enable):
        """Enable/disable Windows autostart via registry"""
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            app_name = "GA_Price_Uploader"
            
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            if enable:
                # Get the executable path
                if getattr(sys, 'frozen', False):
                    # Running as compiled executable
                    exe_path = sys.executable
                else:
                    # Running as script - use pythonw to avoid console window
                    exe_path = f'pythonw "{os.path.abspath(__file__)}"'
                
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
                self._logs.append("✅ Autostart enabled")
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                    self._logs.append("✅ Autostart disabled")
                except FileNotFoundError:
                    pass  # Key doesn't exist, already disabled
            
            winreg.CloseKey(key)
            self.logChanged.emit()
            return True
        except Exception as e:
            self._logs.append(f"❌ Failed to set autostart: {e}")
            self.logChanged.emit()
            return False
    
    def checkWindowsAutostart(self):
        """Check if autostart is currently enabled in registry"""
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            app_name = "GA_Price_Uploader"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, app_name)
                winreg.CloseKey(key)
                return True
            except FileNotFoundError:
                winreg.CloseKey(key)
                return False
        except:
            return False
    
    autostartEnabledChanged = Signal()  # type: ignore
    def getAutostartEnabled(self): return self._autostartEnabled
    def setAutostartEnabled(self, enabled):
        if self._autostartEnabled != enabled:
            self._autostartEnabled = enabled
            self.saveSettings()
            self.setWindowsAutostart(enabled)
            self.autostartEnabledChanged.emit()  # type: ignore
    autostartEnabled = Property(bool, getAutostartEnabled, setAutostartEnabled, notify=autostartEnabledChanged)  # type: ignore
    
    dbServerChanged = Signal()  # type: ignore
    def getDbServer(self): return self._dbServer
    def setDbServer(self, server):
        if self._dbServer != server:
            self._dbServer = server
            self.saveSettings()
            # Update core.py settings
            core.SERVERNAME = server
            self._logs.append(f"✅ Database server updated: {server}")
            self.logChanged.emit()  # type: ignore
            self.dbServerChanged.emit()  # type: ignore
    dbServer = Property(str, getDbServer, setDbServer, notify=dbServerChanged)  # type: ignore
    
    dbNameChanged = Signal()  # type: ignore
    def getDbName(self): return self._dbName
    def setDbName(self, dbName):
        if self._dbName != dbName:
            self._dbName = dbName
            self.saveSettings()
            # Update core.py settings
            core.DATABASENAME = dbName
            self._logs.append(f"✅ Database name updated: {dbName}")
            self.logChanged.emit()  # type: ignore
            self.dbNameChanged.emit()  # type: ignore
    dbName = Property(str, getDbName, setDbName, notify=dbNameChanged)  # type: ignore
    
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
        if getattr(sys, 'frozen', False):
            base_path = Path(sys._MEIPASS)  # type: ignore
        else:
            base_path = Path(__file__).parent
        
        icon_path = base_path / "icons" / "Price List Backend Quenry v2.ico"
        if icon_path.exists():
            self.trayIcon.setIcon(QIcon(str(icon_path)))
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
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick or reason == QSystemTrayIcon.ActivationReason.Trigger:  # type: ignore
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
    
    # Get the base path for resources (works with PyInstaller)
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        base_path = Path(sys._MEIPASS)  # type: ignore
    else:
        # Running as script
        base_path = Path(__file__).parent
    
    # Load custom fonts into Qt's font database
    font_dir = base_path / "fonts"
    if font_dir.exists():
        for font_file in ["Poppins-Regular.ttf", "Poppins-Medium.ttf", "Poppins-SemiBold.ttf", "Poppins-Bold.ttf"]:
            font_path = font_dir / font_file
            if font_path.exists():
                font_id = QFontDatabase.addApplicationFont(str(font_path))
                if font_id != -1:
                    print(f"Loaded font: {font_file}")
                else:
                    print(f"Failed to load font: {font_file}")
    
    app.setWindowIcon(QIcon(str(base_path / "icons" / "Price List Backend Quenry v2.ico")))
    
    engine = QQmlApplicationEngine()
    win = MainWindow()
    engine.rootContext().setContextProperty("backend", win)
    win.progressChanged.connect(lambda value: engine.rootObjects()[0].setProperty("uploadProgress", value))
    engine.load((base_path / "GUI" / "main.qml").as_posix())

    if not engine.rootObjects():
        sys.exit(-1)
    
    # Store reference to QML window
    win.qmlWindow = engine.rootObjects()[0]
    
    # Setup system tray
    win.setupTrayIcon(app)
    
    # Track visibility state to show notification only when actually minimizing
    def on_visibility_changed():
        is_visible = win.qmlWindow.isVisible()  # type: ignore
        # Show notification only when transitioning from visible to hidden
        if win._wasVisible and not is_visible:
            win.trayIcon.showMessage(
                "GA Price Uploader", 
                "App minimized to system tray",
                QSystemTrayIcon.MessageIcon.Information,  # type: ignore
                2000
            )
        win._wasVisible = is_visible
    
    win.qmlWindow.visibilityChanged.connect(on_visibility_changed)  # type: ignore

    # After the UI is loaded and event loop starts, check DB connection
    from PySide6.QtCore import QTimer, QCoreApplication
    def delayed_check():
        app_instance = QCoreApplication.instance()
        if app_instance:
            app_instance.processEvents()  # flush UI events
        # Apply database settings to core module
        core.SERVERNAME = win._dbServer
        core.DATABASENAME = win._dbName
        win.loadLastUpdated()  # Load last updated timestamp
        win.checkDbConnection()
        # Apply autostart setting
        if win._autostartEnabled != win.checkWindowsAutostart():
            win.setWindowsAutostart(win._autostartEnabled)
    QTimer.singleShot(500, delayed_check)  # 500ms to ensure UI is visible

    sys.exit(app.exec())
  