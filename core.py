import os
import sys
import io
import json
import hashlib
import datetime
import logging
import pyodbc
import json
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
SERVERNAME = r"GASERVER\BUSYSTDSQL"
DATABASENAME = "BusyComp0004_db12025"

# --- Firestore Meta Fields ---
META_DOC = firestore_db.collection("DB_Service").document("serverSideData")
ITEMS_COL = firestore_db.collection("items")
BUCKET = storage.bucket()
ACTIVE_IDS_DOC = firestore_db.collection("DB_Service").document("active_ids_snapshot")
log_output = []


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
               Image1, FormatType1, ParentGrp,M.DeactiveMaster, M.BlockedMaster,
               CASE 
                   WHEN CAST(ModificationTime AS time) = '00:00:00' THEN CreationTime
                   ELSE ModificationTime
               END AS EffectiveTime
        FROM Master1 M
        LEFT JOIN Images I ON M.Code = I.Code
        WHERE MasterType = 6 
              AND (
                  CASE 
                      WHEN CAST(ModificationTime AS time) = '00:00:00' THEN CreationTime
                      ELSE ModificationTime
                  END
              ) > ?
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

def upload_active_ids_to_firestore(active_ids: set):
    """Stores active SQL MasterCodes in a single Firestore document as an array."""
    db = firestore.client()
    active_ids_array = sorted(list(active_ids))  # Optional: sorted for readability
    ACTIVE_IDS_DOC.set({
        "activeMasterCodes": active_ids_array,
        "updatedAt": datetime.datetime.utcnow().isoformat()
    }, merge=True)

def build_item(row, units, groups, timestamp):
    code = row.Code or "-"
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


def get_items_by_mastercodes(mastercodes: set):
    if not mastercodes:
        return []
    """Returns list of item rows from SQL where MasterCode is in the given set."""
    conn = connect_to_sql()
    cur = conn.cursor()
    placeholders = ",".join(["?"] * len(mastercodes))
    query = f"""
    SELECT M.Code, MasterType, Name, Alias, D3, CM1, D16, D2,
           Image1, FormatType1, ParentGrp, M.DeactiveMaster, M.BlockedMaster,
           CASE 
               WHEN CAST(ModificationTime AS time) = '00:00:00' THEN CreationTime
               ELSE ModificationTime
           END AS EffectiveTime
    FROM Master1 M
    LEFT JOIN Images I ON M.Code = I.Code
    WHERE MasterType = 6
      AND M.Code IN ({placeholders})"""
    cur.execute(query, list(mastercodes))
    rows = cur.fetchall()
    return rows  
# Add this function to extract all items for full sync
def get_all_ids():
    conn = connect_to_sql()
    cur = conn.cursor()
    cur.execute("""
        SELECT M.Code
        FROM Master1 M
        LEFT JOIN Images I ON M.Code = I.Code
        WHERE MasterType = 6 AND M.DeactiveMaster = 0 AND M.BlockedMaster = 0"""
              )
    rows = cur.fetchall()

    active_ids = set()
    for row in rows:
        active_ids.add(row.Code)  # MasterCode

    return active_ids
def get_firestore_item_ids():
    doc_refs = ITEMS_COL.list_documents()  # Zero-cost
    return set(doc_ref.id for doc_ref in doc_refs)


def delete_firestore_docs_by_ids(ids, batch_size=500):
    ids = list(ids)
    for i in range(0, len(ids), batch_size):
        batch = firestore_db.batch()
        for id_ in ids[i:i + batch_size]:
            batch.delete(ITEMS_COL.document(id_))
        batch.commit()

def get_all_items():
    now = datetime.datetime.utcnow()

    conn = connect_to_sql()
    cur = conn.cursor()
    units = fetch_units(cur)
    groups = fetch_groups(cur)

    # Fetch all items regardless of date
    cur.execute("""
        SELECT M.Code, MasterType, Name, Alias, D3, CM1, D16, D2,
               Image1, FormatType1, ParentGrp, M.DeactiveMaster, M.BlockedMaster,
               CASE 
                   WHEN CAST(ModificationTime AS time) = '00:00:00' THEN CreationTime
                   ELSE ModificationTime
               END AS EffectiveTime
        FROM Master1 M
        LEFT JOIN Images I ON M.Code = I.Code
        WHERE MasterType = 6
    """)
    rows = cur.fetchall()

    item_tuples = []
    for row in rows:
        if row.DeactiveMaster or row.BlockedMaster:
            continue  # Skip blocked/deactivated
        item_data, img, ext = build_item(row, units, groups, now)
        item_tuples.append((item_data, img, ext))  # return all 3
    return item_tuples


def delete_all_items_in_batches(items_ref, log_func=None, on_progress=None):
    """Deletes all documents in the 'items' collection in batches."""
    batch_size = 500
    docs = list(items_ref.stream())
    total_docs = len(docs)
    total_deleted = 0

    for i in range(0, total_docs, batch_size):
        batch = firestore_db.batch()
        batch_docs = docs[i:i + batch_size]
        for doc in batch_docs:
            batch.delete(doc.reference)
        batch.commit()
        total_deleted += len(batch_docs)
        if log_func:
            log_func(f"🗑️ Deleted batch {i // batch_size + 1}: {len(batch_docs)} items")
        if on_progress:
            on_progress(total_deleted, 0)  # 0 images during deletion

    if log_func:
        log_func(f"✅ Deleted {total_deleted} documents.")

    return total_deleted

def clear_and_full_upload(log_func=print, on_progress=None):
    logs = []
    def log(msg):
        logs.append(msg)
        log_func(msg)

    log("⚠️ Starting full Firestore upload...")

    items_ref = firestore_db.collection("items")

    # Step 1: Delete in batches
    total_deleted = delete_all_items_in_batches(items_ref, log_func=log, on_progress=on_progress)
    log(f"✅ Deleted {total_deleted} items from Firestore.")

    # Step 2: Upload items and images
    all_items = get_all_items()
    total_items = len(all_items)
    updated_images = 0
    log(f"📦 Uploading {total_items} items...")

    for i in range(0, total_items, 500):
        batch = firestore_db.batch()
        chunk = all_items[i:i+500]

        for item_data, img, ext in chunk:
            doc_ref = items_ref.document(str(item_data['MasterCode']))
            batch.set(doc_ref, item_data)

            if img:
                image_filename = f"{item_data['MasterCode']}{ext}"
                image_path = os.path.join(IMAGE_DIR, image_filename)

                # Save and upload if not already present
                if not os.path.exists(image_path):
                    img.save(image_path)
                    log(f"💾 Saved missing image for {item_data['Name']}")
                    blob = BUCKET.blob(image_filename)
                    blob.upload_from_filename(image_path)
                    updated_images += 1
                    log(f"🖼️ Uploaded image for {item_data['Name']}")

        batch.commit()
        uploaded = min(i + 500, total_items)
        log(f"✅ Uploaded {uploaded}/{total_items} items")
        if on_progress:
            on_progress(uploaded, total_items)


    # ACTIVE MASTER CODES LIST
    active_sql_ids = set(str(id) for id in get_all_ids())
    upload_active_ids_to_firestore(active_sql_ids)
    summary = f"✅ Uploaded {len(active_sql_ids)} active_sql_ids "
    log_output.append(summary)
    logging.info(summary)
    # Step 3: Update sync timestamp
    now = datetime.datetime.utcnow()
    META_DOC.update({"latestImportFromServer": now.isoformat()})
    log(f"🕓 Completed at {now} UTC")

    summary = f"✅ Uploaded {total_items} items | 🖼️ {updated_images} images"
    log(summary) 

    return total_items, updated_images, now, logs


# --- Main Upload Logic ---
def run_sync():
    global log_output
    log_output.clear()
    # Check for existing stock snapshot and compare stock changes
    snapshot_file = "last_stock_snapshot.json"
    # Load previous snapshot or create in-memory if missing
    if os.path.exists(snapshot_file):
        try:
            with open(snapshot_file, "r", encoding="utf-8") as f:
                prev_snapshot = json.load(f)
        except Exception:
            prev_snapshot = fetch_item_stocks_details()
    else:
        log_output.append("📊 Stock snapshot not found, creating initial in-memory snapshot...")
        prev_snapshot = fetch_item_stocks_details()
    # Fetch current snapshot in-memory
    current_snapshot = fetch_item_stocks_details()
    # Compare previous and current stocks
    prev_map = {item['MasterCode']: item['Stock'] for item in prev_snapshot}
    changes = []
    for item in current_snapshot:
        code = item['MasterCode']
        name = item.get('Name', '')
        curr = item['Stock']
        prev = prev_map.get(code, 0)
        delta = curr - prev
        # only record items with stock increase >=10 and positive final stock
        if delta >= 10 and curr > 0:
            changes.append((code, name, prev, curr, delta))
    log_output.append(f"📊 Significant stock increases (>=10): {len(changes)} items")
    for code, name, prev, curr, delta in changes:
        log_output.append(f" - {code} ({name}): {prev} -> {curr} (Δ{delta})")
    # Publish changes to Firestore for app consumption
    try:
        stock_changes_doc = firestore_db.collection("DB_Service").document("stock_changes_snapshot")
        stock_changes_doc.set({
            "changes": [
                {"MasterCode": code, "Name": name, "prevStock": prev, "currStock": curr, "delta": delta}
                for code, name, prev, curr, delta in changes
            ],
            "updatedAt": datetime.datetime.utcnow().isoformat()
        })
        log_output.append("📢 Published stock changes to Firestore.")
    except Exception as e:
        log_output.append(f"❌ Failed to publish stock changes: {e}")
    now = datetime.datetime.utcnow()

    # Get previous timestamp from Firestore meta
    prev_str = META_DOC.get().to_dict().get("latestImportFromServer")
    if isinstance(prev_str, datetime.datetime):
        prev = prev_str
    elif isinstance(prev_str, str):
        prev = datetime.datetime.fromisoformat(prev_str)
    elif isinstance(prev_str, (int, float)):
        prev = datetime.datetime.utcfromtimestamp(prev_str / 1000)
    else:
        prev = datetime.datetime(2000, 1, 1)
    prev -= datetime.timedelta(seconds=5)

    # --- Fetch data from SQL ---
    conn = connect_to_sql()
    cur = conn.cursor()
    units = fetch_units(cur)
    groups = fetch_groups(cur)
    items = fetch_items(cur, prev)

    updated_images = []

    # Initialize Firestore batch and operation counter
    batch = firestore_db.batch()
    op_count = 0

    def commit_if_needed():
        nonlocal batch, op_count
        if op_count >= 500:
            batch.commit()
            batch = firestore_db.batch()
            op_count = 0

    for row in items:
        doc_id = str(row.Code)
        if row.DeactiveMaster or row.BlockedMaster:
            batch.delete(ITEMS_COL.document(doc_id))
            log_output.append(f"🗑️ Deleted {row.Name} (deactivated or blocked)")
            op_count += 1
            commit_if_needed()
            continue
        
        data, img, ext = build_item(row, units, groups, now)

        batch.set(ITEMS_COL.document(str(data["MasterCode"])), data)
        log_output.append(f"📦 Uploaded {data['Name']}")
        op_count += 1
        commit_if_needed()

        if img:
            img_path = os.path.join(IMAGE_DIR, f"{row.Code}{ext}")
            if is_image_updated(img_path, img):
                img.save(img_path)
                BUCKET.blob(os.path.basename(img_path)).upload_from_filename(img_path)
                updated_images.append(img_path)
                log_output.append(f"🖼️  Updated image for {data['Name']}")
            else:
                log_output.append(f"🖼️  Skipped image (no change) for {data['Name']}")

    # --- Identify and delete Firestore docs no longer in SQL ---
    active_sql_ids = get_all_ids()
    existing_firestore_ids = get_firestore_item_ids()

    existing_firestore_ids = set(str(id) for id in existing_firestore_ids)
    active_sql_ids = set(str(id) for id in active_sql_ids)
    ids_to_delete = existing_firestore_ids - active_sql_ids
    ids_to_add = active_sql_ids - existing_firestore_ids
    print(len(existing_firestore_ids),len(active_sql_ids))
    # to delete items that are deactivated (modification time not updated)
    if ids_to_delete:
        log_output.append(f"🗑️ Removing {len(ids_to_delete)} stale items from Firestore...")
        logging.info(f"🗑️ Removing {len(ids_to_delete)} stale items: {sorted(ids_to_delete)}")
        delete_firestore_docs_by_ids(ids_to_delete)
        for doc_id in ids_to_delete:
            log_output.append(f"🗑️ Deleted stale item: {doc_id}")
    else:
        log_output.append("✅ No stale Firestore items found for deletion.")
        logging.info("✅ No stale Firestore items found for deletion.")
    # to add items that are activated (modification time not updated)
    if ids_to_add:
        log_output.append(f"➕ Uploading {len(ids_to_add)} new items to Firestore...")
        logging.info(f"➕ Uploading {len(ids_to_add)} new items: {sorted(ids_to_add)}")

        # Step 1: Fetch those rows from SQL
        rows = get_items_by_mastercodes(ids_to_add)  # Make sure this returns List[Item] or List[Row]

        for row in rows:
            data, img, ext = build_item(row, units, groups, now)
            batch.set(ITEMS_COL.document(str(data["MasterCode"])), data)
            log_output.append(f"📦 Uploaded {data['Name']}")
            op_count += 1
            commit_if_needed()
            if img:
                img_path = os.path.join(IMAGE_DIR, f"{row.Code}{ext}")
                if is_image_updated(img_path, img):
                    img.save(img_path)
                    BUCKET.blob(os.path.basename(img_path)).upload_from_filename(img_path)
                    updated_images.append(img_path)
                    log_output.append(f"🖼️  Updated image for {data['Name']}")
                else:
                    log_output.append(f"🖼️  Skipped image (no change) for {data['Name']}")

    else:
        log_output.append("✅ No new items found for Firestore upload.")
        logging.info("✅ No new items found for Firestore upload.")

    # Final commit for any remaining operations
    if op_count > 0:
        batch.commit()
    # ACTIVE MASTER CODES LIST
    upload_active_ids_to_firestore(active_sql_ids)
    summary = f"✅ Uploaded {len(active_sql_ids)} active_sql_ids "
    log_output.append(summary)
    logging.info(summary)
    # Update Firestore meta
    META_DOC.update({"latestImportFromServer": now.isoformat()})

    summary = f"✅ Uploaded {len(items)} items | 🖼️ {len(updated_images)} images updated"
    log_output.append(summary)
    logging.info(summary)
    # Save updated stock snapshot after successful upload
    try:
        save_stock_snapshot(current_snapshot, snapshot_file)
        log_output.append(f"📊 Saved new stock snapshot to '{snapshot_file}'")
    except Exception as e:
        log_output.append(f"❌ Failed to save stock snapshot: {e}")
    return len(items), len(updated_images), now, log_output

# Utility function to save stock data locally as JSON
def save_stock_snapshot(stock_dict, filename="last_stock_snapshot.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(stock_dict, f, indent=2)
# Fetch all item stocks with details and save locally
def fetch_and_save_all_item_stocks_with_details(filename="last_stock_snapshot.json"):
    """
    Fetch stock and details for all items, save to JSON, and return the list.
    Returns a list of dicts: [{MasterCode, Name, Alias, Stock, ...}, ...]
    """
    conn = connect_to_sql()
    cur = conn.cursor()
    cur.execute('''
        SELECT 
            F.MasterCode,
            M.Name,
            M.Alias,
            SUM(
                F.D1 
                + ISNULL(F.D23,0) + ISNULL(F.D24,0) + ISNULL(F.D25,0) + ISNULL(F.D26,0) + ISNULL(F.D27,0) + ISNULL(F.D28,0) + ISNULL(F.D29,0) + ISNULL(F.D30,0) + ISNULL(F.D31,0) + ISNULL(F.D32,0) + ISNULL(F.D33,0)
                - ISNULL(F.D11,0) - ISNULL(F.D12,0) - ISNULL(F.D13,0) - ISNULL(F.D14,0) - ISNULL(F.D15,0) - ISNULL(F.D16,0) - ISNULL(F.D17,0) - ISNULL(F.D18,0) - ISNULL(F.D19,0) - ISNULL(F.D20,0) - ISNULL(F.D21,0)
            ) AS Stock
        FROM dbo.Folio1 F
        JOIN Master1 M ON F.MasterCode = M.Code
        WHERE M.MasterType = 6 AND M.DeactiveMaster = 0 AND M.BlockedMaster = 0
        GROUP BY F.MasterCode, M.Name, M.Alias
    ''')
    results = []
    for row in cur.fetchall():
        results.append({
            "MasterCode": row.MasterCode,
            "Name": row.Name,
            "Alias": row.Alias,
            "Stock": float(row.Stock)
        })
    conn.close()
    # Save to JSON
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    return results

# New helper to fetch stocks without writing file
def fetch_item_stocks_details():
    """Fetch stock details for all active items without saving to file."""
    conn = connect_to_sql()
    cur = conn.cursor()
    cur.execute('''
        SELECT 
            F.MasterCode,
            M.Name,
            M.Alias,
            SUM(
                F.D1 + ISNULL(F.D23,0) + ISNULL(F.D24,0) + ISNULL(F.D25,0) + ISNULL(F.D26,0) + ISNULL(F.D27,0) + ISNULL(F.D28,0) + ISNULL(F.D29,0) + ISNULL(F.D30,0) + ISNULL(F.D31,0) + ISNULL(F.D32,0) + ISNULL(F.D33,0)
                - ISNULL(F.D11,0) - ISNULL(F.D12,0) - ISNULL(F.D13,0) - ISNULL(F.D14,0) - ISNULL(F.D15,0) - ISNULL(F.D16,0) - ISNULL(F.D17,0) - ISNULL(F.D18,0) - ISNULL(F.D19,0) - ISNULL(F.D20,0) - ISNULL(F.D21,0)
            ) AS Stock
        FROM dbo.Folio1 F
        JOIN Master1 M ON F.MasterCode = M.Code
        WHERE M.MasterType = 6 AND M.DeactiveMaster = 0 AND M.BlockedMaster = 0
        GROUP BY F.MasterCode, M.Name, M.Alias
    ''')
    rows = cur.fetchall()
    conn.close()
    result = []
    for row in rows:
        result.append({
            "MasterCode": row.MasterCode,
            "Name": row.Name,
            "Alias": row.Alias,
            "Stock": float(row.Stock)
        })
    return result

