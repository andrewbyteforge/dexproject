"""
Management command to fix the multiple accounts issue.

Run this to clean up duplicate accounts and ensure only one active account exists.

File: dexproject/paper_trading/management/commands/fix_accounts.py
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from paper_trading.models import PaperTradingAccount
from decimal import Decimal


class Command(BaseCommand):
    help = 'Fix multiple paper trading accounts issue'
    
    def handle(self, *args, **options):
        """Clean up duplicate accounts for demo_user."""
        
        self.stdout.write("=" * 60)
        self.stdout.write("FIXING MULTIPLE ACCOUNTS ISSUE")
        self.stdout.write("=" * 60)
        
        try:
            # Get demo user
            demo_user = User.objects.get(username='demo_user')
            self.stdout.write(f"\n✓ Found demo_user (ID: {demo_user.id})")
            
            # Get all accounts for this user
            accounts = PaperTradingAccount.objects.filter(user=demo_user).order_by('created_at')
            self.stdout.write(f"\nFound {accounts.count()} accounts for demo_user:")
            
            for i, account in enumerate(accounts, 1):
                self.stdout.write(
                    f"  {i}. {account.name} "
                    f"(ID: {account.account_id}, "
                    f"Balance: ${account.current_balance_usd}, "
                    f"Active: {account.is_active}, "
                    f"Created: {account.created_at})"
                )
            
            if accounts.count() > 1:
                self.stdout.write("\nFIXING: Multiple accounts detected!")
                
                # Keep the first (oldest) account, deactivate others
                primary_account = accounts.first()
                self.stdout.write(f"\nKeeping primary account: {primary_account.name}")
                
                # Ensure primary account is active and has proper name
                primary_account.is_active = True
                primary_account.name = "Demo Paper Trading Account"
                primary_account.save()
                
                # Deactivate all other accounts
                for account in accounts[1:]:
                    account.is_active = False
                    account.save()
                    self.stdout.write(f"  - Deactivated: {account.name}")
                
                self.stdout.write("\n✅ Fixed! Now only one active account exists.")
                
            elif accounts.count() == 1:
                # Ensure the single account is active
                account = accounts.first()
                account.is_active = True
                account.name = "Demo Paper Trading Account"
                account.save()
                self.stdout.write("\n✅ Single account found and ensured active.")
                
            else:
                # No accounts exist, create one
                self.stdout.write("\nNo accounts found. Creating default account...")
                account = PaperTradingAccount.objects.create(
                    user=demo_user,
                    name="Demo Paper Trading Account",
                    initial_balance_usd=Decimal('10000.00'),
                    current_balance_usd=Decimal('10000.00'),
                    is_active=True
                )
                self.stdout.write(f"✅ Created account: {account.account_id}")
            
            # Final verification
            active_accounts = PaperTradingAccount.objects.filter(
                user=demo_user,
                is_active=True
            )
            
            self.stdout.write("\n" + "=" * 60)
            self.stdout.write("VERIFICATION")
            self.stdout.write("=" * 60)
            self.stdout.write(f"Active accounts for demo_user: {active_accounts.count()}")
            
            if active_accounts.count() == 1:
                account = active_accounts.first()
                self.stdout.write(f"✅ SUCCESS! Single active account:")
                self.stdout.write(f"   ID: {account.account_id}")
                self.stdout.write(f"   Name: {account.name}")
                self.stdout.write(f"   Balance: ${account.current_balance_usd}")
                
                self.stdout.write("\n🎉 You can now access the paper trading dashboard!")
                self.stdout.write("   URL: http://localhost:8000/paper-trading/")
            else:
                self.stdout.write(self.style.ERROR("⚠️ Still have multiple active accounts!"))
                
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR("\n❌ demo_user not found!"))
            self.stdout.write("Run this first:")
            self.stdout.write("  python manage.py shell")
            self.stdout.write("  >>> from django.contrib.auth.models import User")
            self.stdout.write("  >>> User.objects.create_user('demo_user', 'demo@example.com')")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Error: {e}"))
            import traceback
            traceback.print_exc()