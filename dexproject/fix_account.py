import sqlite3

DB_PATH = r'D:\dex-django\dexproject\db.sqlite3'
ACCOUNT_ID = 'aa3ad361-6664-4496-a6ef-f1529bfe73ec'

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("🔍 Looking for tables...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%account%'")
    tables = cursor.fetchall()
    
    if not tables:
        print("❌ No account tables found!")
        conn.close()
        exit(1)
    
    print("📋 Found tables:")
    for table in tables:
        print(f"   • {table[0]}")
    
    # Try common table names
    table_names = [
        'paper_accounts',
        'paper_trading_accounts', 
        'papertradingaccount',
        'paper_trading_papertrading_account'
    ]
    
    account_table = None
    for name in table_names:
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{name}'")
        if cursor.fetchone():
            account_table = name
            break
    
    if not account_table:
        # Use the first table we found
        account_table = tables[0][0]
    
    print(f"\n🎯 Using table: {account_table}")
    
    # Delete ALL accounts (fresh start)
    print("🗑️  Deleting all accounts...")
    cursor.execute(f"DELETE FROM {account_table}")
    
    # Find and delete from positions table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%position%'")
    pos_table = cursor.fetchone()
    if pos_table:
        print(f"🗑️  Deleting all positions from {pos_table[0]}...")
        cursor.execute(f"DELETE FROM {pos_table[0]}")
    
    # Find and delete from trades table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%trade%'")
    trade_table = cursor.fetchone()
    if trade_table:
        print(f"🗑️  Deleting all trades from {trade_table[0]}...")
        cursor.execute(f"DELETE FROM {trade_table[0]}")
    
    conn.commit()
    print("\n✅ Database cleaned!")
    print("Now run: python manage.py shell and create a fresh account")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()