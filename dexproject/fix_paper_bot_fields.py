#!/usr/bin/env python3
"""
Quick fix script to update the run_paper_bot.py file with correct field names.

This script will fix the field name issues in your management command.

Run this from the dexproject directory:
    python fix_paper_bot_fields.py

File: dexproject/fix_paper_bot_fields.py
"""

import os

def fix_run_paper_bot():
    """Fix the field names in run_paper_bot.py"""
    
    file_path = "paper_trading/management/commands/run_paper_bot.py"
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        print("Please run this script from the dexproject directory")
        return False
    
    # Read the file with UTF-8 encoding
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Apply fixes
    fixes = [
        # Fix the account.id issue
        ("('Account', f'{account.name} (ID: {account.id})')",
         "('Account', f'{account.name} (ID: {account.pk})')"),
        
        # Fix strategy field names
        ("'mode': options['strategy_mode'],",
         "'trading_mode': mode_mapping.get(options['strategy_mode'], 'MODERATE'),"),
        
        ("'fast_lane_enabled': options['strategy_mode'] in ['FAST', 'HYBRID'],",
         "'use_fast_lane': options['strategy_mode'] in ['FAST', 'HYBRID'],"),
        
        ("'smart_lane_enabled': options['strategy_mode'] in ['SMART', 'HYBRID'],",
         "'use_smart_lane': options['strategy_mode'] in ['SMART', 'HYBRID'],"),
        
        ("'max_position_size': Decimal(str(options['max_position_size'])),",
         "'max_position_size_percent': Decimal(str(options['max_position_size'])),"),
        
        ("'min_confidence_score': Decimal(\"40\"),",
         "'confidence_threshold': Decimal(\"40\"),"),
        
        ("strategy.mode = options['strategy_mode']",
         "strategy.trading_mode = mode_mapping.get(options['strategy_mode'], 'MODERATE')"),
        
        ("strategy.fast_lane_enabled = options['strategy_mode'] in ['FAST', 'HYBRID']",
         "strategy.use_fast_lane = options['strategy_mode'] in ['FAST', 'HYBRID']"),
        
        ("strategy.smart_lane_enabled = options['strategy_mode'] in ['SMART', 'HYBRID']",
         "strategy.use_smart_lane = options['strategy_mode'] in ['SMART', 'HYBRID']"),
        
        ("strategy.max_position_size = Decimal(str(options['max_position_size']))",
         "strategy.max_position_size_percent = Decimal(str(options['max_position_size']))")
    ]
    
    # Check if mode_mapping already exists
    if "mode_mapping" not in content:
        # Add mode_mapping at the beginning of _configure_strategy method
        mapping_code = """
            # Map strategy mode to trading mode
            mode_mapping = {
                'FAST': 'AGGRESSIVE',
                'SMART': 'CONSERVATIVE',
                'HYBRID': 'MODERATE'
            }
            """
        
        # Find where to insert
        method_start = "def _configure_strategy(self, account, options):"
        try_start = "try:"
        
        if method_start in content and try_start in content:
            # Find the position after "try:" in _configure_strategy
            method_pos = content.find(method_start)
            try_pos = content.find(try_start, method_pos)
            
            if try_pos > -1:
                # Insert after the try: line
                lines = content[:try_pos + len(try_start)].split('\n')
                indent = ' ' * 12  # 3 levels of indentation
                mapping_with_indent = '\n'.join(indent + line.strip() for line in mapping_code.strip().split('\n'))
                
                content = (content[:try_pos + len(try_start)] + '\n' + 
                          mapping_with_indent + '\n' +
                          content[try_pos + len(try_start):])
    
    # Apply all the fixes
    for old, new in fixes:
        if old in content:
            content = content.replace(old, new)
            print(f"✅ Fixed: {old[:50]}...")
    
    # Need to also fix the get_or_create call to include account
    if "strategy, created = PaperStrategyConfiguration.objects.get_or_create(" in content:
        # Check if account parameter is missing
        if "name=f\"Strategy_{account.name}\"," in content and "account=account," not in content:
            # Add account parameter after the get_or_create line
            old_line = "strategy, created = PaperStrategyConfiguration.objects.get_or_create(\n                name=f\"Strategy_{account.name}\","
            new_line = "strategy, created = PaperStrategyConfiguration.objects.get_or_create(\n                account=account,\n                name=f\"Strategy_{account.name}\","
            content = content.replace(old_line, new_line)
            print("✅ Added account parameter to strategy configuration")
    
    # Write the fixed content back with UTF-8 encoding
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"\n✅ Successfully fixed {file_path}")
    return True


def fix_simple_trader():
    """Fix field names in simple_trader.py if needed"""
    
    file_path = "paper_trading/bot/simple_trader.py"
    
    if not os.path.exists(file_path):
        print(f"⚠️  File not found: {file_path} (might be using enhanced version)")
        return False
    
    # Read the file with UTF-8 encoding
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if it needs fixing
    needs_fixing = False
    
    # Fix session.id to session.session_id
    if "self.session.id" in content:
        content = content.replace("self.session.id", "self.session.session_id")
        needs_fixing = True
        print("✅ Fixed session.id references")
    
    # Fix session creation
    if "bot_type='ENHANCED_AI'," in content:
        content = content.replace("bot_type='ENHANCED_AI',", "name='AI_Bot_Session',")
        needs_fixing = True
        print("✅ Fixed session creation")
    
    if needs_fixing:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Successfully fixed {file_path}")
    else:
        print(f"ℹ️  No fixes needed for {file_path}")
    
    return True


def fix_ai_engine():
    """Fix field names in ai_engine.py"""
    
    file_path = "paper_trading/bot/ai_engine.py"
    
    if not os.path.exists(file_path):
        print(f"⚠️  File not found: {file_path}")
        return False
    
    # Read the file with UTF-8 encoding
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    needs_fixing = False
    
    # Fix the create_ai_engine function
    if "name=f\"Strategy_{session.id}\"" in content:
        content = content.replace(
            "name=f\"Strategy_{session.id}\"",
            "name=f\"Strategy_{session.session_id}\""
        )
        needs_fixing = True
        print("✅ Fixed session.id in ai_engine.py")
    
    # Fix get_or_create to include account
    if "strategy_config, created = PaperStrategyConfiguration.objects.get_or_create(" in content:
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if "PaperStrategyConfiguration.objects.get_or_create(" in line:
                # Check next few lines for the pattern
                if i + 1 < len(lines) and "name=f\"Strategy_" in lines[i + 1]:
                    # Need to add account parameter
                    # First, need to get account from session
                    insert_line = "    account = session.account"
                    if insert_line not in content:
                        # Find the line before get_or_create
                        before_getorcreate = '\n'.join(lines[:i])
                        after_getorcreate = '\n'.join(lines[i:])
                        
                        # Add the account line
                        content = before_getorcreate + '\n    \n    # Get the account from the session\n    account = session.account\n    \n    ' + after_getorcreate
                        
                        # Now add account parameter to get_or_create
                        content = content.replace(
                            "PaperStrategyConfiguration.objects.get_or_create(\n        name=",
                            "PaperStrategyConfiguration.objects.get_or_create(\n        account=account,\n        name="
                        )
                        needs_fixing = True
                        print("✅ Added account parameter in ai_engine.py")
                break
    
    # Fix field names in defaults
    fixes = [
        ("'mode': 'HYBRID',", "'trading_mode': 'MODERATE',"),
        ("'fast_lane_enabled': True,", "'use_fast_lane': True,"),
        ("'smart_lane_enabled': True,", "'use_smart_lane': True,"),
        ("'max_position_size': Decimal", "'max_position_size_percent': Decimal"),
        ("'min_confidence_score': Decimal", "'confidence_threshold': Decimal")
    ]
    
    for old, new in fixes:
        if old in content:
            content = content.replace(old, new)
            needs_fixing = True
            print(f"✅ Fixed: {old}")
    
    if needs_fixing:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Successfully fixed {file_path}")
    else:
        print(f"ℹ️  No fixes needed for {file_path}")
    
    return True


def main():
    print("🔧 Fixing Paper Trading Bot Field Names...")
    print("=" * 60)
    
    # Check we're in the right directory
    if not os.path.exists("paper_trading"):
        print("❌ Error: paper_trading directory not found!")
        print("Please run this script from the dexproject directory")
        return
    
    # Fix each file
    print("\n📝 Fixing run_paper_bot.py...")
    fix_run_paper_bot()
    
    print("\n📝 Checking simple_trader.py...")
    fix_simple_trader()
    
    print("\n📝 Checking ai_engine.py...")
    fix_ai_engine()
    
    print("\n" + "=" * 60)
    print("✅ Field name fixes complete!")
    print("\nYou can now run:")
    print("  python manage.py run_paper_bot")
    print("\nOr with options:")
    print("  python manage.py run_paper_bot --create-account")
    print("  python manage.py run_paper_bot --strategy-mode HYBRID")


if __name__ == "__main__":
    main()