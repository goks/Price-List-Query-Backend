#!/usr/bin/env python
# coding: utf-8

# In[1]:


import pyodbc as pd 
from PIL import Image
import hashlib
import json
import os, sys, io
import firebase_admin
from firebase_admin import credentials, db
from firebase_admin import storage
from firebase_admin import firestore
from firebase_admin.firestore import SERVER_TIMESTAMP
from firebase_admin import firestore
import datetime

import logging


# In[2]:


logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S')


# In[3]:


try:
    # PyInstaller creates a temp folder and stores path in _MEIPASS
        BASE_PATH = sys._MEIPASS
except Exception:
    BASE_PATH = os.path.abspath(".")
ITEM_IMAGES_PATH = os.path.join(BASE_PATH, r"itemImages")   


# In[4]:


SERVERNAME = "GASERVER\BUSYSTDSQL"
DATABASENAME = "BusyComp0004_db12023"


# In[5]:


class DB:
    def __init__(self):
        connectionString = "Driver={SQL Server};" +'Server='+SERVERNAME +'; Database=' + DATABASENAME + '; Trusted_Connection=yes;'
        self.conn = pd.connect(connectionString)
        self.cursor = self.conn.cursor()
        return
    def getUnits(self):
        self.cursor.execute("SELECT Code,Name FROM Master1 WHERE MasterType=8 AND DeactiveMaster=0")
        return
    def getGroups(self):
        self.cursor.execute("SELECT Code,Name FROM Master1 WHERE MasterType=5 AND DeactiveMaster=0")
        return
    def getItems(self):
        self.cursor.execute("SELECT M.Code,MasterType,Name, Alias,D3,CM1,D16,D2,Image1,FormatType1,ParentGrp FROM Master1 M LEFT JOIN Images I ON M.Code=I.Code WHERE MasterType=6 AND DeactiveMaster=0 AND BlockedMaster=0" ) 
        return
    def getItemsWithTime(self, comparison_datetime):
        sql_query = f"SELECT M.Code,MasterType,Name, Alias,D3,CM1,D16,D2,Image1,FormatType1,ParentGrp FROM Master1 M LEFT JOIN Images I ON M.Code=I.Code WHERE MasterType=6 AND DeactiveMaster=0 AND BlockedMaster=0 AND [ModificationTime] >= ?"
        self.cursor.execute(sql_query, comparison_datetime) 
        return
    def getCursor(self):
        return self.cursor      
    def __del__(self):
        self.conn.close()
        logging.info("DB Connection closed")
        return


# In[6]:


class Item:
    def __init__(self):
        self.MasterCode = None
        self.Code = None
        self.Name = None
        self.PRICE3 = None
        self.Unit = None
        self.DiscPercent = None
        self.MRP = None
        self.imageYes = False
        self.imageH = 0
        self.imageW = 0
        self.imageExt = None
        self.Group = None
        self.lastFBUpdate = None
        return
        
    def __init__(self,MasterCode, Code, Name, PRICE3, Unit, DiscPercent = 0, MRP=0, imageYes=False, imageH=0, imageW=0, Group=None, imageExt=None, lastFBUpdate=None ) -> None:
        self.MasterCode = MasterCode
        self.Code = Code
        self.Name = Name
        self.PRICE3 = PRICE3
        self.Unit = Unit
        self.DiscPercent = DiscPercent
        self.MRP = MRP
        self.imageYes = imageYes
        self.imageH = imageH
        self.imageW = imageW
        self.imageExt = imageExt
        self.Group = Group
        self.lastFBUpdate = lastFBUpdate
        return
    
    def __json__(self):
        return ({
            "MasterCode" : self.MasterCode ,
            "Code" : self.Code ,
            "Name" : self.Name ,
            "PRICE3" : self.PRICE3 ,
            "Unit" : self.Unit ,
            "DiscPercent" : self.DiscPercent ,
            "MRP" : self.MRP ,
            "imageYes" : self.imageYes ,
            "imageH" : self.imageH ,
            "imageW" : self.imageW ,
            "imageExt" : self.imageExt ,
            "Group" : self.Group ,
            "lastFBUpdate" : self.lastFBUpdate.strftime("%Y-%m-%d %H:%M:%S")
        })
        


# In[7]:


class ItemList:
    def __init__(self):
        self.item_list = {}
        self.db=DB()
        self.unit_dict = {}
        self.group_dict = {}
        self.array_of_itemDict=[]
        self.newImages=[]
        
    def deleteDBObject(self):
        del self.db    
        return
    def prepareUnitDict(self):
        self.db.getUnits()
        self.cursor = self.db.getCursor()
        while(True):
            row = self.cursor.fetchone()
            if not row:
                break
            self.unit_dict[row.Code] =row.Name
        return
    def prepareGroupDict(self):
        self.db.getGroups()
        self.cursor = self.db.getCursor()
        while(True):
            row = self.cursor.fetchone()
            if not row:
                break
            self.group_dict[row.Code] =row.Name
        return
    def cleanName(self, input):
        special_characters=['$','/','.','#']
        output = input.replace('[', '(')
        output = output.replace(']', ')')
        for each in special_characters:
            output = output.replace(each,'*')
        return output    
    def checkifImageAlreadyPresent(self,imagePath, image):
        if not os.path.isfile(imagePath):
            logging.warning("image "+ imagePath+' does not exist')
            return False
        oldImage = Image.open(imagePath)
        image.save(os.path.join(ITEM_IMAGES_PATH, 'temp.jpg'))   
        image = Image.open(os.path.join(ITEM_IMAGES_PATH, 'temp.jpg'))
        if hashlib.md5(image.tobytes()).hexdigest() != hashlib.md5(oldImage.tobytes()).hexdigest():
            return False
        return True
    def prepareItemList(self, currentTimestamp, previousUpdateTimestamp):   
        self.prepareUnitDict() 
        self.prepareGroupDict() 
        # For All operation
        # self.db.getItems()
        # For only update operation
        self.db.getItemsWithTime(previousUpdateTimestamp)
        self.cursor = self.db.getCursor()
        
        while(True):
            row = self.cursor.fetchone()
            if not row:
                break
            im = None
            imExt = ''
            image = None
            width, height = (0,0)
            if row.Image1:
                im = row.Image1
                imExt = row.FormatType1
                image = Image.open(io.BytesIO(im))
                width, height = image.size
            i = Item(MasterCode=row.Code, Code = self.cleanName(row.Alias), Name = self.cleanName(row.Name), 
                     PRICE3 = row.D3, Unit = self.unit_dict[row.CM1], DiscPercent = row.D16,
                     MRP = row.D2, Group = self.group_dict[row.ParentGrp],imageYes=True if row.Image1 else False, imageH=height, imageW=width, imageExt=imExt, lastFBUpdate=currentTimestamp)
            if im:
                imName = str(row.Code)
                imagePath = os.path.join(ITEM_IMAGES_PATH, imName+imExt)
                if not self.checkifImageAlreadyPresent(imagePath, image):    
                    if not os.path.isdir(ITEM_IMAGES_PATH):
                        os.mkdir(ITEM_IMAGES_PATH)
                    image.save(imagePath)   
                    self.newImages.append(imagePath)
                    logging.info("image "+ imagePath+' saved.')                
            self.item_list[self.cleanName(row.Name)] = i.__dict__
            self.array_of_itemDict.append(i)
        print(f"{len(self.array_of_itemDict)} number of new items found.")    
        self.deleteDBObject()  
        return
    def getItemList(self):
        return self.item_list
    def getArrayofItemDict(self):
        return self.array_of_itemDict
    def getImagePathstoUpload(self):
        return self.newImages
    def __json__(self):
        return({
            "array_of_itemDict" : [each.__json__() for each in self.array_of_itemDict ],
            "unit_dict" : self.unit_dict,
            "group_dict" : self.group_dict,
            "newImages": self.newImages,
        })

    # def toJSON(self):
    #     return json.dumps(self.getArrayofItemDict, default=lambda o: o.__dict__, 
    #         sort_keys=True, indent=4)


# In[8]:


class FirebaseControlsOLD:
    def __init__(self):
        # correction for auto-py-to-exe
        certificate_path = os.path.join(BASE_PATH, r"service-account\\gokul-agencies-firebase-adminsdk-ti855-702f214fc5.json")
        cred = credentials.Certificate(certificate_path)
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://gokul-agencies.firebaseio.com/',
            'storageBucket': 'gokul-agencies.appspot.com'
            
        })
        self.fdb = firestore.client()
        self.itemList_ref = db.reference("/item_list/") 
        self.itemListUpdateTime_ref = db.reference('/item_list_update_time/')
        self.bucket = storage.bucket()
    def set_itemList(self, data):
        return self.itemList_ref.set(data)
    def remove_itemList(self):
        return self.itemList_ref.set({}) 
        # return self.itemList_ref.child(child).set({}) 
    def get_itemList(self):
        return self.itemList_ref.get() 
    def set_itemListUpdateTime(self):
        # return db.reference('/').update({'item_list_update_time': datetime.datetime.utcnow().timestamp()})
        return self.itemListUpdateTime_ref.set({".sv": "timestamp" })
    def remove_itemListUpdateTime(self):
        return self.itemListUpdateTime_ref.set({}) 
    def get_itemListUpdateTime(self):
        return self.itemListUpdateTime_ref.get()     
    def get_itemListUpdateTime_dt_obj(self):
        # timestamp is number of seconds since 1970-01-01 
        timestamp = self.get_itemListUpdateTime()
        # convert the timestamp to a datetime object in the local timezone
        if(type(timestamp)==int):
            dt_object = datetime.datetime.utcfromtimestamp(timestamp/1000)
        else: 
            raise TypeError    
        return dt_object
    def uploadImages(self, imagePathsList):
        for each in imagePathsList:
            _, tail = os.path.split(each)
            blob = self.bucket.blob(tail)
            blob.upload_from_filename(each)
        return
        


# In[9]:


class FirebaseControls:
    def __init__(self):
        # correction for auto-py-to-exe
        certificate_path = os.path.join(BASE_PATH, r"service-account\\gokul-agencies-firebase-adminsdk-ti855-702f214fc5.json")
        cred = credentials.Certificate(certificate_path)
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://gokul-agencies.firebaseio.com/',
            'storageBucket': 'gokul-agencies.appspot.com'
            
        })
        self.fdb = firestore.client()
        self.itemCollection_ref = self.fdb.collection("items")
        self.dBServicedetails = self.fdb.collection("DB_Service")
        self.serverSideDataDocName = "serverSideData"  
        self.latestImportFromServerFieldName = "latestImportFromServer"  
        self.previousImportFromServerFieldName = "previousImportFromServer"  
        self.batch = None
        
        self.itemList_ref = db.reference("/item_list/") 
        self.itemListUpdateTime_ref = db.reference('/item_list_update_time/')
        self.bucket = storage.bucket()
    
    def add_item_to_batch(self, item_data, itemName):
        doc_ref = self.itemCollection_ref.document(itemName)
        self.batch.set(doc_ref, item_data)
        
    def set_itemFromItemList(self,itemList):
        self.batch = self.fdb.batch()
        for item in itemList:
            self.add_item_to_batch(item.__dict__, item.Name)
        self.batch.commit() 
        return
    def update_itemFromItemList(self, itemList):
        docs = self.itemCollection_ref.stream()  
        # Update Firestore documents that have changed only
        for doc in docs:
            for item in itemList:
                if doc.to_dict() == item:
                    doc_ref = self.itemCollection_ref.document(doc.id)
                    doc_ref.update(item)  
                    print("updated")    
    def remove_itemList(self):
        return self.itemList_ref.set({}) 
        # return self.itemList_ref.child(child).set({}) 
    def get_itemList(self):
        return self.itemList_ref.get() 
    def set_latestServerUpdateTime(self, timestamp):
        latestServerUpdateTime = self.get_latestServerUpdateTime();
        if latestServerUpdateTime:
           print( self.set_previousServerUpdateTime(latestServerUpdateTime))
           return self.dBServicedetails.document(self.serverSideDataDocName).update({self.latestImportFromServerFieldName : timestamp})
        else:
            return None
    def get_latestServerUpdateTime(self):
        doc = self.dBServicedetails.document(self.serverSideDataDocName).get()
        if doc.exists:
            data = doc.to_dict()
            if self.latestImportFromServerFieldName in data:
                return data[self.latestImportFromServerFieldName]
            else:
                print(f"Field '{self.latestImportFromServerFieldName}' not found in the document.")
        else:
            print(f"Document '{self.serverSideDataDocName}' does not exist.")
        return None    
    def set_previousServerUpdateTime(self, timestamp):
        return self.dBServicedetails.document(self.serverSideDataDocName).update({self.previousImportFromServerFieldName : timestamp})  
    def get_previousServerUpdateTime(self):
        doc = self.dBServicedetails.document(self.serverSideDataDocName).get()
        if doc.exists:
            data = doc.to_dict()
            if self.previousImportFromServerFieldName in data:
                return data[self.previousImportFromServerFieldName]
            else:
                print(f"Field '{self.previousImportFromServerFieldName}' not found in the document.")
        else:
            print(f"Document '{self.serverSideDataDocName}' does not exist.")  
        return None        
    def uploadImages(self, imagePathsList):
        for each in imagePathsList:
            _, tail = os.path.split(each)
            blob = self.bucket.blob(tail)
            blob.upload_from_filename(each)
        return
    def __del__(self):
        firebase_admin.delete_app(firebase_admin._apps[0])


# In[15]:


def serialize_datetime(obj):
    if isinstance(obj, datetime.datetime):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    raise TypeError("Type not serializable")
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, '__json__'):
            return obj.__json__()
        return super().default(obj)


def write_op_to_json(itemList, timestamp):
    # a = {}
    # a['itemList'] = itemList.getArrayofItemDict()
    # a['imagePathsList'] = itemList.getImagePathstoUpload()
    # a = itemList.toJSON()
    if not os.path.isdir('output'):
        os.mkdir('output')
    outFile = os.path.join(BASE_PATH, f"output\\output_{timestamp.strftime('%Y-%m-%d_%H.%M.%S')}.json")
    with open(outFile, "w", encoding='utf-8' ) as outfile:
        json.dump(itemList, outfile,ensure_ascii=False, indent=4, cls=CustomJSONEncoder)


# In[17]:


def convert_UTC_to_India_zone(timestamp):
    return timestamp + datetime.timedelta(minutes=330)


# In[12]:


# firebaseControl = FirebaseControls()
# itemList = ItemList()
# currentTime = datetime.datetime.utcnow()
# print(convert_UTC_to_India_zone(currentTime))
# previousUpdateTimestamp = firebaseControl.get_latestServerUpdateTime()
# itemList.prepareItemList( convert_UTC_to_India_zone(currentTime), convert_UTC_to_India_zone(previousUpdateTimestamp) )
# itemListdict = itemList.getItemList()
# imagePathsList = itemList.getImagePathstoUpload()
# logging.info("ItemList prepared. Ready to upload")


# In[16]:


# print(len(itemListdict, ))
# itemListdict


# In[18]:


# write_op_to_json(itemList, convert_UTC_to_India_zone(currentTime))


# In[19]:


# firebaseControl.set_itemFromItemList(itemList.getArrayofItemDict())
# print(firebaseControl.uploadImages(imagePathsList))
# firebaseControl.set_latestServerUpdateTime(currentTime)

# print("Upload OK")


# # TODO
#     add datetime element to db.
#     change ui to reflect update write or masterwrite.

# `` python -m jupyter nbconvert --to script 'core.ipynb' ``
# Use this to convert to python file
