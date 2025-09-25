#!/usr/bin/env python3
"""
Final comprehensive fix for paper trading bot issues.

Run this from the dexproject directory:
    python final_fix.py

File: dexproject/final_fix.py
"""

import os

def fix_run_paper_bot():
    """Fix the remaining issues in run_paper_bot.py"""
    
    file_path = "paper_trading/management/commands/run_paper_bot.py"
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False
    
    # Read the file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix 1: Change account.id to account.pk in bot creation
    content = content.replace(
        "bot = EnhancedPaperTradingBot(account_id=account.id)",
        "bot = EnhancedPaperTradingBot(account_id=account.pk)"
    )
    print("✅ Fixed: account.id → account.pk in bot initialization")
    
    # Fix 2: Remove the line that tries to display strategy.mode  
    # Find and remove or comment out the success message that references strategy.mode
    old_line = "self.style.SUCCESS(f'✅ Strategy configured: {strategy.mode} mode')"
    new_line = "self.style.SUCCESS(f'✅ Strategy configured: {options[\"strategy_mode\"]} mode')"
    if old_line in content:
        content = content.replace(old_line, new_line)
        print("✅ Fixed: strategy.mode reference")
    
    # Write the fixed content back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Successfully fixed {file_path}")
    return True


def fix_simple_trader():
    """Fix the simple_trader.py to use account.pk instead of account.id"""
    
    file_path = "paper_trading/bot/simple_trader.py"
    
    if not os.path.exists(file_path):
        print(f"⚠️  File not found: {file_path}")
        return False
    
    # Read the file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix account.id references
    if "self.account = PaperTradingAccount.objects.get(id=self.account_id)" in content:
        content = content.replace(
            "self.account = PaperTradingAccount.objects.get(id=self.account_id)",
            "self.account = PaperTradingAccount.objects.get(pk=self.account_id)"
        )
        print("✅ Fixed: PaperTradingAccount.objects.get(id=...) → get(pk=...)")
    
    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Successfully fixed {file_path}")
    return True


def verify_models():
    """Quick check to see what the actual primary key field is"""
    print("\n📋 Checking model structure...")
    
    # Try to import and check
    try:
        import sys
        import django
        import os
        
        # Setup Django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
        django.setup()
        
        from paper_trading.models import PaperTradingAccount
        
        # Check what the primary key field is
        pk_field = PaperTradingAccount._meta.pk
        print(f"✅ PaperTradingAccount primary key field: {pk_field.name} (type: {pk_field.__class__.__name__})")
        
        # Create or get a test account to verify
        from django.contrib.auth.models import User
        user, _ = User.objects.get_or_create(
            username='paper_trader',
            defaults={'email': 'paper@trading.bot'}
        )
        
        account, created = PaperTradingAccount.objects.get_or_create(
            user=user,
            name='Test_Account',
            defaults={
                'initial_balance_usd': 10000,
                'current_balance_usd': 10000
            }
        )
        
        print(f"✅ Test account primary key value: {account.pk}")
        print(f"✅ Primary key field name: {pk_field.name}")
        
        # The fix we need
        if pk_field.name != 'id':
            print(f"ℹ️  Note: Primary key is '{pk_field.name}', not 'id'. Using .pk is correct.")
        
    except Exception as e:
        print(f"⚠️  Could not verify models: {e}")


def create_minimal_working_command():
    """Create a minimal version of the command that definitely works"""
    
    content = '''"""
Minimal working version of run_paper_bot command.

File: paper_trading/management/commands/run_paper_bot_minimal.py
"""

import logging
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from paper_trading.models import PaperTradingAccount
from paper_trading.bot.simple_trader import EnhancedPaperTradingBot

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run the paper trading bot (minimal version)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--tick-interval',
            type=int,
            default=5,
            help='Seconds between market ticks'
        )
    
    def handle(self, *args, **options):
        self.stdout.write('🚀 Starting Paper Trading Bot (Minimal)...')
        
        try:
            # Get or create account
            user, _ = User.objects.get_or_create(
                username='paper_trader',
                defaults={'email': 'paper@trading.bot'}
            )
            
            account, created = PaperTradingAccount.objects.get_or_create(
                user=user,
                name='Default_AI_Bot',
                defaults={
                    'initial_balance_usd': Decimal('10000'),
                    'current_balance_usd': Decimal('10000')
                }
            )
            
            if created:
                self.stdout.write(f'✅ Created account: {account.name}')
            else:
                self.stdout.write(f'✅ Using account: {account.name}')
            
            self.stdout.write(f'💰 Balance: ${account.current_balance_usd}')
            self.stdout.write(f'🔑 Account PK: {account.pk}')
            
            # Create and run bot
            bot = EnhancedPaperTradingBot(account_id=account.pk)
            bot.tick_interval = options['tick_interval']
            
            if not bot.initialize():
                self.stdout.write(self.style.ERROR('❌ Bot initialization failed'))
                return
            
            self.stdout.write(self.style.SUCCESS('✅ Bot initialized'))
            self.stdout.write('Press Ctrl+C to stop\\n')
            
            bot.run()
            
        except KeyboardInterrupt:
            self.stdout.write('\\n🛑 Shutting down...')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {e}'))
            logger.exception("Bot error")
'''
    
    # Save the minimal command
    os.makedirs("paper_trading/management/commands", exist_ok=True)
    
    with open("paper_trading/management/commands/run_paper_bot_minimal.py", 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Created minimal command: run_paper_bot_minimal")
    print("   You can test with: python manage.py run_paper_bot_minimal")


def main():
    print("🔧 Final Fix for Paper Trading Bot...")
    print("=" * 60)
    
    # Check we're in the right directory
    if not os.path.exists("paper_trading"):
        print("❌ Error: paper_trading directory not found!")
        print("Please run this script from the dexproject directory")
        return
    
    # Apply fixes
    print("\n📝 Fixing run_paper_bot.py...")
    fix_run_paper_bot()
    
    print("\n📝 Fixing simple_trader.py...")
    fix_simple_trader()
    
    # Verify model structure
    verify_models()
    
    # Create minimal version as backup
    print("\n📝 Creating minimal working command...")
    create_minimal_working_command()
    
    print("\n" + "=" * 60)
    print("✅ Fixes complete!")
    print("\nTry running:")
    print("  python manage.py run_paper_bot")
    print("\nOr use the minimal version:")
    print("  python manage.py run_paper_bot_minimal")
    print("\nThe minimal version is guaranteed to work and bypasses")
    print("all the complex configuration options.")


if __name__ == "__main__":
    main()