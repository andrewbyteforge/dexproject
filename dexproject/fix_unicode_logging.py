#!/usr/bin/env python
"""
Fix Unicode logging issues in the DEX Trading Bot.

This script will:
1. Fix Windows console encoding issues
2. Replace Unicode emojis with ASCII equivalents in log messages
3. Update logging configuration for Windows compatibility

Run this from the dexproject directory:
    python fix_unicode_logging.py
"""

import os
import sys
import re
from pathlib import Path


def fix_engine_config_logging():
    """Fix Unicode emoji issues in engine/config.py logging."""
    config_file = Path("engine/config.py")
    
    if not config_file.exists():
        print(f"ERROR: {config_file} not found!")
        return False
    
    print(f"Fixing Unicode logging in {config_file}...")
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace Unicode emojis with ASCII equivalents
        emoji_replacements = {
            '✅': '[OK]',
            '❌': '[ERROR]',
            '⚠️': '[WARNING]',  
            '🚀': '[START]',
            '🎯': '[TARGET]',
            '📥': '[LOAD]',
            '🔗': '[CONNECT]',
            '💡': '[INFO]',
            '📍': '[CHAIN]',
        }
        
        for emoji, replacement in emoji_replacements.items():
            content = content.replace(emoji, replacement)
        
        # Write back with UTF-8 encoding
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"SUCCESS: Fixed Unicode emojis in {config_file}")
        return True
        
    except Exception as e:
        print(f"ERROR fixing {config_file}: {e}")
        return False


def fix_redis_client_logging():
    """Fix Unicode emoji issues in shared/redis_client.py logging."""
    redis_file = Path("shared/redis_client.py")
    
    if not redis_file.exists():
        print(f"WARNING: {redis_file} not found, skipping...")
        return True
    
    print(f"Fixing Unicode logging in {redis_file}...")
    
    try:
        with open(redis_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace Unicode emojis with ASCII equivalents
        emoji_replacements = {
            '✅': '[OK]',
            '❌': '[ERROR]',
            '⚠️': '[WARNING]',
            '📨': '[MSG]',
            '🔌': '[CONNECT]',
        }
        
        for emoji, replacement in emoji_replacements.items():
            content = content.replace(emoji, replacement)
        
        with open(redis_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"SUCCESS: Fixed Unicode emojis in {redis_file}")
        return True
        
    except Exception as e:
        print(f"ERROR fixing {redis_file}: {e}")
        return False


def fix_logging_handlers():
    """Fix logging handler configuration for Windows."""
    settings_file = Path("dexproject/settings.py")
    
    if not settings_file.exists():
        print(f"ERROR: {settings_file} not found!")
        return False
    
    print(f"Fixing logging configuration in {settings_file}...")
    
    try:
        with open(settings_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Add encoding parameter to file handlers
        if "'class': 'logging.handlers.RotatingFileHandler'" in content:
            # Add encoding to RotatingFileHandler if not present
            if "'encoding': 'utf-8'" not in content:
                content = content.replace(
                    "'maxBytes': 10485760,  # 10MB\n            'backupCount': 10,",
                    "'maxBytes': 10485760,  # 10MB\n            'backupCount': 10,\n            'encoding': 'utf-8',"
                )
        
        # Fix console handler stream for Windows
        console_handler_pattern = r"'console': \{[^}]*'class': 'logging\.StreamHandler'[^}]*\},"
        if re.search(console_handler_pattern, content, re.DOTALL):
            console_replacement = """'console': {
            'class': 'logging.StreamHandler',
            'level': LOG_LEVEL,
            'formatter': 'verbose',
            'stream': 'ext://sys.stdout',
        },"""
            
            content = re.sub(
                console_handler_pattern,
                console_replacement,
                content,
                flags=re.DOTALL
            )
        
        with open(settings_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"SUCCESS: Fixed logging configuration in {settings_file}")
        return True
        
    except Exception as e:
        print(f"ERROR fixing {settings_file}: {e}")
        return False


def set_console_encoding():
    """Set console encoding for Windows to handle UTF-8."""
    if sys.platform.startswith('win'):
        try:
            # Set console to UTF-8 mode
            os.system('chcp 65001 >nul 2>&1')
            
            # Set environment variables for UTF-8
            os.environ['PYTHONIOENCODING'] = 'utf-8'
            
            print("SUCCESS: Set Windows console to UTF-8 mode")
            return True
        except Exception as e:
            print(f"WARNING: Could not set console encoding: {e}")
            return False
    else:
        print("INFO: Not on Windows, skipping console encoding setup")
        return True


def create_test_script():
    """Create a test script to verify logging fixes."""
    test_script = Path("test_logging_fix.py")
    
    test_content = '''#!/usr/bin/env python
"""
Test script to verify logging fixes work properly.
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

import logging

def test_logging():
    """Test logging with various characters."""
    logger = logging.getLogger('test_logger')
    
    print("Testing logging with ASCII characters...")
    logger.info("[OK] This should work fine")
    logger.warning("[WARNING] This is a warning")
    logger.error("[ERROR] This is an error")
    
    print("Testing logging with numbers and symbols...")
    logger.info("Loaded 3 chain configurations successfully")
    logger.info("Redis connection established on localhost:6379")
    logger.info("Engine status: RUNNING")
    
    print("All logging tests completed successfully!")

if __name__ == "__main__":
    test_logging()
'''
    
    try:
        with open(test_script, 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        print(f"SUCCESS: Created test script: {test_script}")
        return True
        
    except Exception as e:
        print(f"ERROR creating test script: {e}")
        return False


def main():
    """Main function to fix all Unicode logging issues."""
    print("🔧 DEX Trading Bot - Unicode Logging Fix")
    print("=" * 50)
    
    success_count = 0
    total_fixes = 5
    
    # Fix 1: Set console encoding
    if set_console_encoding():
        success_count += 1
    
    # Fix 2: Fix engine config logging
    if fix_engine_config_logging():
        success_count += 1
    
    # Fix 3: Fix Redis client logging
    if fix_redis_client_logging():
        success_count += 1
    
    # Fix 4: Fix logging handlers
    if fix_logging_handlers():
        success_count += 1
    
    # Fix 5: Create test script
    if create_test_script():
        success_count += 1
    
    print(f"\nCompleted {success_count}/{total_fixes} fixes successfully")
    
    if success_count == total_fixes:
        print("\n[SUCCESS] All logging fixes applied!")
        print("\nNext steps:")
        print("1. Restart your Django shell")
        print("2. Test with: python test_logging_fix.py")
        print("3. Re-run your engine config test")
    else:
        print(f"\n[WARNING] {total_fixes - success_count} fixes failed")
        print("Check the error messages above and fix manually if needed")


if __name__ == "__main__":
    main()