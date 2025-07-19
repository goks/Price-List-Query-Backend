import os
import sys
import io
import json
import hashlib
import datetime
import logging
import pyodbc
from PIL import Image
import firebase_admin
from firebase_admin import credentials, firestore, storage

# --- Logging setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Paths ---
BASE_PATH = getattr(sys, '_MEIPASS', os.path.abspath("."))
IMAGE_DIR = os.path.join(BASE_PATH, "itemImages")
os.makedirs(IMAGE_DIR, exist_ok=True)

# --- Firebase Init ---
CERT_PATH = os.path.join(BASE_PATH, r"service-account\gokul-agencies-firebase-adminsdk-ti855-702f214fc5.json")
if not firebase_admin._apps:
    cred = credentials.Certificate(CERT_PATH)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'gokul-agencies.appspot.com'
    })
firestore_db = firestore.client()

# --- SQL Constants ---
SERVERNAME = "GASERVER\BUSYSTDSQL"
DATABASENAME = "BusyComp0004_db12025"

# --- Firestore Meta Fields ---
META_DOC = firestore_db.collection("DB_Service").document("serverSideData")
ITEMS_COL = firestore_db.collection("items")
BUCKET = storage.bucket()

# --- SQL helpers ---
def connect_to_sql():
    conn_str = f"Driver={{SQL Server}};Server={SERVERNAME};Database={DATABASENAME};Trusted_Connection=yes;"
    return pyodbc.connect(conn_str)

def fetch_units(cursor):
    cursor.execute("SELECT Code,Name FROM Master1 WHERE MasterType=8 AND DeactiveMaster=0")
    return {row.Code: row.Name for row in cursor.fetchall()}

def fetch_groups(cursor):
    cursor.execute("SELECT Code,Name FROM Master1 WHERE MasterType=5 AND DeactiveMaster=0")
    return {row.Code: row.Name for row in cursor.fetchall()}

def fetch_items(cursor, modified_after):
    cursor.execute("""
        SELECT M.Code, MasterType, Name, Alias, D3, CM1, D16, D2,
               Image1, FormatType1, ParentGrp
        FROM Master1 M
        LEFT JOIN Images I ON M.Code = I.Code
        WHERE MasterType = 6 AND DeactiveMaster = 0 AND BlockedMaster = 0
              AND ModificationTime >= ?
    """, modified_after)
    return cursor.fetchall()

def sanitize_name(name):
    return name.replace('[', '(').replace(']', ')').translate(str.maketrans({
        '$': '*', '/': '*', '.': '*', '#': '*'
    }))

def is_image_updated(image_path, new_image):
    if not os.path.exists(image_path):
        return True
    old_image = Image.open(image_path)
    return hashlib.md5(new_image.tobytes()).hexdigest() != hashlib.md5(old_image.tobytes()).hexdigest()

def build_item(row, units, groups, timestamp):
    code = row.Code
    name = sanitize_name(row.Name)
    alias = sanitize_name(row.Alias)
    price = row.D3 or 0
    unit = units.get(row.CM1, "Unknown")
    disc = row.D16 or 0
    mrp = row.D2 or 0
    group = groups.get(row.ParentGrp, "Unknown")

    img, ext = None, ""
    if row.Image1:
        img = Image.open(io.BytesIO(row.Image1))
        ext = row.FormatType1 or ".jpg"

    item_data = {
        "MasterCode": code,
        "Code": alias,
        "Name": name,
        "PRICE3": price,
        "Unit": unit,
        "DiscPercent": disc,
        "MRP": mrp,
        "Group": group,
        "imageYes": bool(img),
        "imageH": img.height if img else 0,
        "imageW": img.width if img else 0,
        "imageExt": ext,
        "lastFBUpdate": timestamp,
        "lastFBUpdateStr": timestamp.strftime('%Y-%m-%d %H:%M:%S')
    }
    return item_data, img, ext

log_output = []
# --- Main Upload Logic ---
def run_sync():
    now = datetime.datetime.utcnow()
    ts = int(now.timestamp() * 1000)

    # Get previous timestamp
    prev_raw = META_DOC.get().to_dict().get("latestImportFromServer", 0)
    if isinstance(prev_raw, datetime.datetime):
        prev = prev_raw
    else:
        prev = datetime.datetime.utcfromtimestamp(prev_raw / 1000)

    conn = connect_to_sql()
    cur = conn.cursor()
    units = fetch_units(cur)
    groups = fetch_groups(cur)
    items = fetch_items(cur, prev)

    batch = firestore_db.batch()
    updated_images = []

    for row in items:
        data, img, ext = build_item(row, units, groups, now)
        batch.set(ITEMS_COL.document(data["Name"]), data)
        log_output.append(f"Uploading {data['Name']}")
        if img:
            img_path = os.path.join(IMAGE_DIR, f"{row.Code}{ext}")
            if is_image_updated(img_path, img):
                img.save(img_path)
                BUCKET.blob(os.path.basename(img_path)).upload_from_filename(img_path)
                updated_images.append(img_path)
                log_output.append(f"🖼️  Updated image for {data['Name']}")
            else:
                log_output.append(f"🖼️  Skipped image (no change) for {data['Name']}")
                

    batch.commit()
    META_DOC.update({"latestImportFromServer": ts})
    logging.info(f"Uploaded {len(items)} items. {len(updated_images)} images updated.")
    return len(items), len(updated_images), now, log_output
