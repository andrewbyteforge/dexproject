import sqlite3

DB_PATH = r'D:\dex-django\dexproject\db.sqlite3'

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("📋 ALL tables in database:\n")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = cursor.fetchall()
    
    for table in tables:
        print(f"   • {table[0]}")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")