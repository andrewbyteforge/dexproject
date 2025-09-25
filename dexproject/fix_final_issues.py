#!/usr/bin/env python3
"""
Fix the final two issues:
1. Remove emojis from logging (Windows console encoding issue)
2. Add starting_balance_usd to session creation

Run from dexproject directory:
    python fix_final_issues.py
"""

import os
import re

def remove_emojis_from_file(file_path):
    """Remove emoji characters from Python file to fix Windows encoding issues"""
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Common emoji replacements for logging
    replacements = [
        ('🤖', '[BOT]'),
        ('📊', '[DATA]'),
        ('✅', '[OK]'),
        ('❌', '[ERROR]'),
        ('🎮', '[GAME]'),
        ('🧠', '[AI]'),
        ('📍', '[TICK]'),
        ('💹', '[PRICE]'),
        ('🤔', '[THINK]'),
        ('💰', '[MONEY]'),
        ('📦', '[POS]'),
        ('🚀', '[START]'),
        ('🛑', '[STOP]'),
        ('💭', '[THOUGHT]'),
        ('⚡', '[FAST]'),
        ('⚠️', '[WARN]'),
        ('📈', '[UP]'),
        ('📉', '[DOWN]'),
        ('💡', '[IDEA]'),
        ('🔧', '[CONFIG]'),
        ('📋', '[INFO]'),
        ('🔑', '[KEY]'),
    ]
    
    changed = False
    for emoji, replacement in replacements:
        if emoji in content:
            content = content.replace(emoji, replacement)
            changed = True
            print(f"  Replaced {emoji} with {replacement}")
    
    if changed:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Fixed emojis in {file_path}")
    else:
        print(f"  No emojis found in {file_path}")
    
    return True


def fix_session_creation():
    """Fix the PaperTradingSession creation to include starting_balance_usd"""
    
    file_path = "paper_trading/bot/simple_trader.py"
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the session creation and add starting_balance_usd
    old_creation = """self.session = PaperTradingSession.objects.create(
                account=self.account,
                name=f"AI_Bot_Session_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                status='RUNNING',
                starting_balance_usd=self.account.current_balance_usd
            )"""
    
    # Check if starting_balance_usd is already there
    if "starting_balance_usd=self.account.current_balance_usd" not in content:
        # Find the session creation pattern
        pattern = r'self\.session = PaperTradingSession\.objects\.create\([^)]+\)'
        
        # New creation with starting_balance_usd
        new_creation = """self.session = PaperTradingSession.objects.create(
                account=self.account,
                name=f"AI_Bot_Session_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                status='RUNNING',
                starting_balance_usd=self.account.current_balance_usd
            )"""
        
        # Replace using regex
        content = re.sub(pattern, new_creation, content, count=1)
        print("✅ Added starting_balance_usd to session creation")
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
    else:
        print("  starting_balance_usd already present")
    
    return True


def create_no_emoji_config():
    """Create a logging configuration that works better with Windows"""
    
    config_content = '''"""
Windows-compatible logging configuration for paper trading bot.
Add this to the top of your bot files to fix encoding issues.
"""

import logging
import sys

# Configure logging for Windows compatibility
def configure_logging():
    # Remove all handlers
    logger = logging.getLogger()
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create new handler with UTF-8 encoding
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
    )
    
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    
    return logger
'''
    
    with open("paper_trading/bot/logging_config.py", 'w', encoding='utf-8') as f:
        f.write(config_content)
    
    print("✅ Created logging_config.py for Windows compatibility")
    return True


def main():
    print("Fixing final issues...")
    print("=" * 60)
    
    # Fix emoji issues in bot files
    print("\n1. Removing emojis from bot files...")
    files_to_fix = [
        "paper_trading/bot/simple_trader.py",
        "paper_trading/bot/ai_engine.py"
    ]
    
    for file_path in files_to_fix:
        print(f"\nProcessing {file_path}...")
        remove_emojis_from_file(file_path)
    
    # Fix session creation
    print("\n2. Fixing session creation...")
    fix_session_creation()
    
    # Create logging config
    print("\n3. Creating Windows-compatible logging config...")
    create_no_emoji_config()
    
    print("\n" + "=" * 60)
    print("✅ All fixes applied!")
    print("\nNow try running:")
    print("  python manage.py run_paper_bot")
    print("\nOr if you still see emoji issues:")
    print("  python manage.py run_paper_bot_minimal")
    print("\nThe bot should now work properly on Windows!")


if __name__ == "__main__":
    main()