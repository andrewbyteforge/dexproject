#!/usr/bin/env python3
"""
Fix the position display field name error.

Run from dexproject directory:
    python fix_position_display.py
"""

import os

def fix_position_display():
    file_path = "paper_trading/bot/simple_trader.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix all occurrences of entry_price to average_entry_price_usd
    content = content.replace('position.entry_price', 'position.average_entry_price_usd')
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Fixed position display field names")

if __name__ == "__main__":
    fix_position_display()
    print("\nThe display error is fixed!")
    print("Run the bot again: python manage.py run_paper_bot")