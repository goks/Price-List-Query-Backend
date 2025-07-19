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
    def __init__(self):
        super().__init__()
        self._status = "Ready"
        self._lastUpdated = "Never"
        self.threadpool = QThreadPool()
        self.loadLastUpdated()

    def loadLastUpdated(self):
        try:
            ts = core.firestore_db.collection("DB_Service").document("serverSideData").get().to_dict().get("latestImportFromServer", None)
            if ts:
                dt = datetime.utcfromtimestamp(ts / 1000).replace(tzinfo=pytz.utc).astimezone(IST)
                self._lastUpdated = dt.strftime("%d-%m-%Y %H:%M")
        except:
            self._lastUpdated = "Unknown"

    @Signal
    def statusChanged(self): pass
    def getStatus(self): return self._status

    @Signal
    def lastUpdatedChanged(self): pass
    def getLastUpdated(self): return self._lastUpdated
    
    @Signal
    def logChanged(self): pass
    def getLogs(self): return "\n".join(self._logs)
    logs = Property(str, getLogs, notify=logChanged)

    status = Property(str, getStatus, notify=statusChanged)
    lastUpdated = Property(str, getLastUpdated, notify=lastUpdatedChanged)

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
            self.logChanged.emit()
        except Exception as e:
            traceback.print_exc()
            self._status = f"Error: {str(e)}"
        finally:
            self.statusChanged.emit()
            self.lastUpdatedChanged.emit()

class Worker(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        self.fn()

if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    engine.load(Path("GUI/main.qml").as_posix())

    win = MainWindow()
    engine.rootContext().setContextProperty("backend", win)

    if not engine.rootObjects():
        sys.exit(-1)
    sys.exit(app.exec_())
