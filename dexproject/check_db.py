import os

DB_PATH = r'D:\dex-django\dexproject\db.sqlite3'

if os.path.exists(DB_PATH):
    size = os.path.getsize(DB_PATH)
    print(f"✅ Database exists: {DB_PATH}")
    print(f"📦 Size: {size:,} bytes ({size/1024/1024:.2f} MB)")
else:
    print(f"❌ Database NOT found at: {DB_PATH}")