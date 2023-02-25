#!/usr/bin/env python
# coding: utf-8

# In[29]:


import pyodbc as pd 
from PIL import Image
import hashlib
import json
import os, sys, io
import firebase_admin
from firebase_admin import credentials, db
from firebase_admin import storage
from firebase_admin.firestore import SERVER_TIMESTAMP
import datetime

import logging


# In[30]:


logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S')


# In[31]:


try:
    # PyInstaller creates a temp folder and stores path in _MEIPASS
        BASE_PATH = sys._MEIPASS
except Exception:
    BASE_PATH = os.path.abspath(".")
ITEM_IMAGES_PATH = os.path.join(BASE_PATH, r"itemImages")   


# In[32]:


SERVERNAME = "GASERVER\BUSYSTDSQL"
DATABASENAME = "BusyComp0004_db12022"


# In[33]:


class DB:
    def __init__(self):
        connectionString = "Driver={SQL Server};" +'Server='+SERVERNAME +'; Database=' + DATABASENAME + '; Trusted_Connection=yes;'
        self.conn = pd.connect(connectionString)
        self.cursor = self.conn.cursor()
        return
    def getUnits(self):
        self.cursor.execute("SELECT Code,Name FROM Master1 WHERE MasterType=8 AND DeactiveMaster=0")
        return
    def getItems(self):
        self.cursor.execute("SELECT M.Code,MasterType,Name, Alias,D3,CM1,D16,D2,Image1,FormatType1 FROM Master1 M LEFT JOIN Images I ON M.Code=I.Code WHERE MasterType=6 AND DeactiveMaster=0 AND BlockedMaster=0") 
        return
    def getCursor(self):
        return self.cursor      
    def __del__(self):
        self.conn.close()
        logging.info("DB Connection closed")
        return


# In[34]:


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
        return
        
    def __init__(self,MasterCode, Code, Name, PRICE3, Unit, DiscPercent = 0, MRP=0, imageYes=False, imageH=0, imageW=0) -> None:
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
        return
        


# In[35]:


class ItemList:
    def __init__(self):
        self.item_list = {}
        self.db=DB()
        self.unit_dict = {}
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
    def prepareItemList(self):   
        self.prepareUnitDict() 
        self.db.getItems()
        self.cursor = self.db.getCursor()
        while(True):
            row = self.cursor.fetchone()
            if not row:
                break
            im = None
            imExt = None
            image = None
            width, height = (0,0)
            if row.Image1:
                im = row.Image1
                imExt = row.FormatType1
                image = Image.open(io.BytesIO(im))
                width, height = image.size
            i = Item(MasterCode=row.Code, Code = self.cleanName(row.Alias), Name = self.cleanName(row.Name), 
                     PRICE3 = row.D3, Unit = self.unit_dict[row.CM1], DiscPercent = row.D16,
                     MRP = row.D2, imageYes=True if row.Image1 else False, imageH=height, imageW=width)
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
            self.array_of_itemDict.append(i.__dict__)
        self.deleteDBObject()  
    def getItemList(self):
        return self.item_list
    def getArrayofItemDict(self):
        return self.array_of_itemDict
    def getImagePathstoUpload(self):
        return self.newImages


# In[36]:


class FirebaseControls:
    def __init__(self):
        # correction for auto-py-to-exe
        certificate_path = os.path.join(BASE_PATH, r"service-account\\gokul-agencies-firebase-adminsdk-ti855-702f214fc5.json")
        cred = credentials.Certificate(certificate_path)
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://gokul-agencies.firebaseio.com/',
            'storageBucket': 'gokul-agencies.appspot.com'
        })
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
        # return db.reference('/').update({'item_list_update_time': datetime.datetime.now().timestamp()})
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
        


# In[37]:


def write_op_to_json(itemList):
    a = {}
    a['itemList'] = itemList.getArrayofItemDict()
    a['imagePathsList'] = itemList.getImagePathstoUpload()
    if not os.path.isdir('output'):
        os.mkdir('output')
    outFile = os.path.join(BASE_PATH, r"output\\output.json")
    with open(outFile, "w", encoding='utf-8' ) as outfile:
        json.dump(a, outfile,ensure_ascii=False, indent=4)


# In[38]:


itemList = ItemList()
itemList.prepareItemList()
itemListdict = itemList.getItemList()
imagePathsList = itemList.getImagePathstoUpload()
logging.info("ItemList prepared. Ready to upload")


# In[ ]:


# write_op_to_json(itemList)
# firebaseControl = FirebaseControls()

# print(firebaseControl.remove_itemList())
# print(firebaseControl.set_itemList(itemListdict))
# print(firebaseControl.remove_itemListUpdateTime())
# print(firebaseControl.uploadImages(imagePathsList))

# print(firebaseControl.set_itemListUpdateTime())
# print("Upload OK")


# `` python -m jupyter nbconvert --to script 'core.ipynb' ``
# Use this to convert to python file
