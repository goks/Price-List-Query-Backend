import sys
from pathlib import Path
from PySide2.QtGui import QGuiApplication, QIcon
from PySide2.QtQml import QQmlApplicationEngine
from PySide2.QtCore import QObject, Signal, Property, Slot, QRunnable, QThreadPool
from datetime import datetime
import pytz
import traceback
import core

IST = pytz.timezone("Asia/Calcutta")

class MainWindow(QObject):
    progressChanged = Signal(int, int)

    def __init__(self):
        super().__init__()
        self._status = "Ready"
        self._lastUpdated = "Never"
        self.threadpool = QThreadPool()
        self._logs = []
        self.loadLastUpdated()
        self.progress = 0

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
    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    win = MainWindow()
    engine.rootContext().setContextProperty("backend", win)
    win.progressChanged.connect(lambda value: engine.rootObjects()[0].setProperty("uploadProgress", value))
    engine.load(Path("GUI/main.qml").as_posix())

    if not engine.rootObjects():
        sys.exit(-1)

    # After the UI is loaded and event loop starts, check DB connection
    from PySide2.QtCore import QTimer, QCoreApplication
    def delayed_check():
        QCoreApplication.instance().processEvents()  # flush UI events
        win.checkDbConnection()
    QTimer.singleShot(500, delayed_check)  # 500ms to ensure UI is visible

    sys.exit(app.exec_())
