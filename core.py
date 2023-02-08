#!/usr/bin/env python
# coding: utf-8

# In[1]:


import pyodbc as pd 
import os, sys
import firebase_admin
from firebase_admin import credentials, db
from firebase_admin.firestore import SERVER_TIMESTAMP
import datetime


# In[2]:


SERVERNAME = "GASERVER\BUSYSTDSQL"
DATABASENAME = "BusyComp0004_db12022"


# In[3]:


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
        self.cursor.execute("SELECT * FROM Master1 WHERE MasterType=6 AND DeactiveMaster=0 AND BlockedMaster=0") 
        return
    def getCursor(self):
        return self.cursor      
    def __del__(self):
        self.conn.close()
        print("DB Connection closed")
        return


# In[4]:


class Item:
    def __init__(self):
        self.Code = None
        self.Name = None
        self.PRICE3 = None
        self.Unit = None
        self.DiscPercent = None
        self.MRP = None
        return
        
    def __init__(self, Code, Name, PRICE3, Unit, DiscPercent = 0, MRP=0) -> None:
        self.Code = Code
        self.Name = Name
        self.PRICE3 = PRICE3
        self.Unit = Unit
        self.DiscPercent = DiscPercent
        self.MRP = MRP
        return
        


# In[5]:


class ItemList:
    def __init__(self):
        self.item_list = {}
        self.db=DB()
        self.unit_dict = {}
        self.array_of_itemDict=[]
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
    def prepareItemList(self):   
        self.prepareUnitDict() 
        self.db.getItems()
        self.cursor = self.db.getCursor()
        while(True):
            row = self.cursor.fetchone()
            if not row:
                break
            i = Item(Code = self.cleanName(row.Alias), Name = self.cleanName(row.Name), PRICE3 = row.D3, Unit = self.unit_dict[row.CM1], DiscPercent = row.D16, MRP = row.D2)
            self.item_list[self.cleanName(row.Name)] = i.__dict__
            self.array_of_itemDict.append(i.__dict__)
        self.deleteDBObject()  
    def getItemList(self):
        return self.item_list
    def getArrayofItemDict(self):
        return self.array_of_itemDict


# In[6]:


class FirebaseControls:
    def __init__(self):
        # correction for auto-py-to-exe
        try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        certificate_path = os.path.join(base_path, r"service-account\\gokul-agencies-firebase-adminsdk-ti855-702f214fc5.json")
        cred = credentials.Certificate(certificate_path)
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://gokul-agencies.firebaseio.com/'
        })
        self.itemList_ref = db.reference("/item_list/") 
        self.itemListUpdateTime_ref = db.reference('/item_list_update_time/')
    def set_itemList(self, data):
        return self.itemList_ref.set(data)
        return self.itemList_ref.child(child).set(data)
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


# In[7]:


# itemList = ItemList()
# itemList.prepareItemList()
# itemListdict = itemList.getItemList()
# print("ItemList prepared. Ready to upload")


# In[8]:


# import json
# a = json.dumps(itemList.getArrayofItemDict())
# with open("./output/ouput.json", "w") as outfile:
#     json.dump(itemList.getArrayofItemDict(), outfile)


# In[9]:


# firebaseControl = FirebaseControls()

# print(firebaseControl.remove_itemList())
# print(firebaseControl.set_itemList(itemListdict))
# print(firebaseControl.remove_itemListUpdateTime())
# print(firebaseControl.set_itemListUpdateTime())
# print("Upload OK")


# `` python -m jupyter nbconvert --to script 'core.ipynb' ``
# Use this to convert to python file
