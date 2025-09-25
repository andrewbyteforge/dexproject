#!/usr/bin/env python3
"""
Remove the arrow character that's causing encoding issues.

Run from dexproject directory:
    python remove_arrow.py
"""

import os

def fix_arrow():
    file_path = "paper_trading/bot/simple_trader.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace arrow with ->
    content = content.replace('→', '->')
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Replaced arrow character with ->")

if __name__ == "__main__":
    fix_arrow()
    print("\nNow run: python manage.py run_paper_bot")
    print("The bot should work without any encoding errors!")