# This Python file uses the following encoding: utf-8
import os
from pathlib import Path
import sys
from PySide2 import QtGui
from PySide2.QtGui import QGuiApplication, QIcon
from PySide2.QtQml import QQmlApplicationEngine
from PySide2.QtCore import QObject, Signal, Property,Slot,QRunnable, QThreadPool
from datetime import datetime, timezone
import pytz
import json
import traceback
import logging

import core as C


IND = pytz.timezone('Asia/Calcutta')

try:
    from ctypes import windll  # Only exists on Windows.
    myappid = 'neoproductions.pricelistquery.backend.1.1'
    windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except ImportError:
    pass

class MainWindow(QObject):
    def __init__(self):
        QObject.__init__(self)
        self.FB = C.FirebaseControls()
        self._mainScreenLoadingStatus = True
        self._itemUpdationStatus = False
        self.setLastUpdatedTime("firsttime")
        self._connectionSuccessText = ""
        self._taskFinishedText = ""
        self._onlineUpdateSuccessText= ""
        self.threadpool = QThreadPool()
        print("Multithreading with maximum %d threads" % self.threadpool.maxThreadCount())
        return
        
    def setLastUpdatedTime(self,time="default"):
        try:
            timestamp_obj = self.FB.get_itemListUpdateTime_dt_obj()
        except :
            self._lastUpdatedTime = "Cannot get data, check internet conn."   
        else:
            timestamp_obj = timestamp_obj.replace(tzinfo=timezone.utc)
            datetime_str = timestamp_obj.astimezone(IND).strftime("%d-%m-%Y %H:%M.")
            self._lastUpdatedTime = "Last uploaded on " + datetime_str
        finally:    
            if time != "firsttime":    
                self.lastUpdateTime_changed.emit()
            self._mainScreenLoadingStatus = False
            self.mainScreenLoadingStatus_changed.emit()
        return
    
    showMainScreenLoadingIndicator = Signal()
    hideMainScreenLoadingIndicator = Signal()

    @Signal
    def lastUpdateTime_changed(self):
        pass
    def get_lastUpdateTime(self):
        return self._lastUpdatedTime    
    
    @Signal
    def mainScreenLoadingStatus_changed(self):
        pass
    def get_mainScreenLoadingStatus(self):
        return self._mainScreenLoadingStatus  
    
    @Signal
    def itemUpdationStatus_changed(self):
        pass
    def get_itemUpdationStatus(self):
        return self._itemUpdationStatus
    
    @Signal
    def connectionSuccessText_changed(self):
        pass
    def get_connectionSuccessText(self):
        return self._connectionSuccessText
    
    @Signal
    def onlineUpdateSuccessText_changed(self):
        pass
    def get_onlineUpdateSuccessText(self):
        return self._onlineUpdateSuccessText 
    
    @Signal
    def taskFinishedText_changed(self):
        pass
    def get_taskFinishedText(self):
        return self._taskFinishedText      
            
    lastUpdatedTime = Property(str, get_lastUpdateTime, notify=lastUpdateTime_changed)
    mainScreenLoadingStatus = Property(bool, get_mainScreenLoadingStatus, notify=mainScreenLoadingStatus_changed)
    itemUpdationStatus = Property(bool, get_itemUpdationStatus, notify=itemUpdationStatus_changed)
    connectionSuccessText= Property(str, get_connectionSuccessText, notify=connectionSuccessText_changed)
    onlineUpdateSuccessText= Property(str, get_onlineUpdateSuccessText, notify=onlineUpdateSuccessText_changed)
    taskFinishedText= Property(str, get_taskFinishedText, notify=taskFinishedText_changed)

    @Slot()    
    def beginUploading(self):
        print("Begin updation process.")
        
        worker = Worker(self.updationFuctions) # Any other args, kwargs are passed to the run function
        worker.signals.finished.connect(self.thread_complete)
        worker.signals.progress.connect(self.progress_fn)

        self.threadpool.start(worker)
        
        self._itemUpdationStatus = True
        self.itemUpdationStatus_changed.emit()
        
        worker = Worker()
        self.threadpool.start(worker)
        
        return 
    
    def updationFuctions(self, progress_callback):
        itemList = C.ItemList()
        itemList.prepareItemList()
        itemListdict = itemList.getItemList()
        imagePathsList = itemList.getImagePathstoUpload()
        logging.info("ItemList prepared. Ready to upload")
        progress_callback.emit(1)
        
        self.FB.remove_itemList()
        self.FB.set_itemList(itemListdict)
        self.FB.remove_itemListUpdateTime()
        self.FB.uploadImages(imagePathsList)
        self.FB.set_itemListUpdateTime()
        progress_callback.emit(2)
        print("Upload OK")
        
        C.write_op_to_json(itemList)  
        print("json dump at output/output.json")    
        return      
      
    def thread_complete(self):
        self._taskFinishedText = "Task Finished"
        self.taskFinishedText_changed.emit()
        self._itemUpdationStatus = False   
        self.itemUpdationStatus_changed.emit()
        self.setLastUpdatedTime()
        return  
    
    def progress_fn(self, n):
        if n==1:
            self._connectionSuccessText = "Busy Connection Succeeded"
            self.connectionSuccessText_changed.emit()
        else:
            self._onlineUpdateSuccessText = "Online Updation Success"
            self.onlineUpdateSuccessText_changed.emit()
        return                
             
            

class WorkerSignals(QObject):
   
    finished = Signal()
    error = Signal(tuple)
    progress = Signal(int)
    
class Worker(QRunnable):
    '''
    Worker thread
    '''
    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        # Add the callback to our kwargs
        self.kwargs['progress_callback'] = self.signals.progress
            
    @Slot()  # QtCore.Slot
    def run(self):
        '''
        Your code goes in this function
        '''
        print("Thread start")
        
        try:        
            result = self.fn(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))   
        finally:
            self.signals.finished.emit()  # Done     
        print("Thread complete")    


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    app.setOrganizationName('Neo Productions')
    app.setOrganizationDomain('Fly fly fly')
    app.setWindowIcon(QtGui.QIcon(os.fspath(Path(__file__).resolve().parent / "icons/16x16.bmp")))
    
    #Get Context
    main = MainWindow()
    engine.rootContext().setContextProperty("backend", main)
    
    
    engine.load(os.fspath(Path(__file__).resolve().parent / "GUI/main.qml"))
    if not engine.rootObjects():
        sys.exit(-1)
    sys.exit(app.exec_())
