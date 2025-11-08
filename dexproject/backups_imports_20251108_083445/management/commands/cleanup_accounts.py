# Save this as: paper_trading/management/commands/cleanup_accounts.py
# Create the directories if they don't exist: paper_trading/management/commands/

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from paper_trading.models import PaperTradingAccount, PaperTradingSession, PaperPosition, PaperTrade
from django.utils import timezone
from decimal import Decimal

class Command(BaseCommand):
    help = 'Clean up duplicate paper trading accounts and keep only one'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('=' * 60))
        self.stdout.write(self.style.WARNING('PAPER TRADING ACCOUNT CLEANUP'))
        self.stdout.write(self.style.WARNING('=' * 60))
        
        # Get or create the demo user
        user, created = User.objects.get_or_create(
            username='demo_user',
            defaults={'email': 'demo@example.com'}
        )
        
        # Get all accounts for this user
        accounts = PaperTradingAccount.objects.filter(user=user).order_by('created_at')
        
        if not accounts.exists():
            # No accounts exist, create one
            account = PaperTradingAccount.objects.create(
                name='My_Trading_Account',
                user=user,
                current_balance_usd=Decimal('10000'),
                initial_balance_usd=Decimal('10000')
            )
            self.stdout.write(self.style.SUCCESS(f'✅ Created new account: {account.name} (ID: {account.account_id})'))
            return
        
        if accounts.count() == 1:
            account = accounts.first()
            self.stdout.write(self.style.SUCCESS(f'✅ Only one account exists: {account.name} (ID: {account.account_id})'))
            self.stdout.write(self.style.SUCCESS(f'   Balance: ${account.current_balance_usd:,.2f}'))
            return
        
        # Multiple accounts exist - merge them
        self.stdout.write(self.style.WARNING(f'⚠️  Found {accounts.count()} accounts - will merge into one'))
        
        # Choose the account to keep (the one with most activity or highest balance)
        keeper = None
        max_score = -1
        
        for account in accounts:
            # Calculate a score based on activity and balance
            trade_count = PaperTrade.objects.filter(account=account).count()
            position_count = PaperPosition.objects.filter(account=account).count()
            balance = float(account.current_balance_usd)
            score = trade_count * 10 + position_count * 5 + balance / 1000
            
            self.stdout.write(f'\nAccount: {account.name} (ID: {account.account_id})')
            self.stdout.write(f'  Created: {account.created_at}')
            self.stdout.write(f'  Balance: ${account.current_balance_usd:,.2f}')
            self.stdout.write(f'  Trades: {trade_count}')
            self.stdout.write(f'  Positions: {position_count}')
            self.stdout.write(f'  Score: {score:.2f}')
            
            if score > max_score:
                max_score = score
                keeper = account
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Keeping account: {keeper.name} (ID: {keeper.account_id})'))
        
        # Rename the keeper account to a standard name
        keeper.name = 'My_Trading_Account'
        keeper.save()
        
        # Migrate data from other accounts to keeper
        for account in accounts:
            if account.account_id == keeper.account_id:
                continue
            
            self.stdout.write(f'\nMigrating data from: {account.name} (ID: {account.account_id})')
            
            # Migrate trades
            trades = PaperTrade.objects.filter(account=account)
            migrated_trades = trades.update(account=keeper)
            self.stdout.write(f'  Migrated {migrated_trades} trades')
            
            # Migrate positions
            positions = PaperPosition.objects.filter(account=account)
            migrated_positions = positions.update(account=keeper)
            self.stdout.write(f'  Migrated {migrated_positions} positions')
            
            # Migrate sessions
            sessions = PaperTradingSession.objects.filter(account=account)
            migrated_sessions = sessions.update(account=keeper)
            self.stdout.write(f'  Migrated {migrated_sessions} sessions')
            
            # Delete the duplicate account
            account.delete()
            self.stdout.write(self.style.WARNING(f'  Deleted duplicate account'))
        
        # Final summary
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('CLEANUP COMPLETE'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS(f'✅ Single account maintained: {keeper.name}'))
        self.stdout.write(self.style.SUCCESS(f'   ID: {keeper.account_id}'))
        self.stdout.write(self.style.SUCCESS(f'   Balance: ${keeper.current_balance_usd:,.2f}'))
        self.stdout.write(self.style.SUCCESS(f'   Total Trades: {PaperTrade.objects.filter(account=keeper).count()}'))
        self.stdout.write(self.style.SUCCESS(f'   Open Positions: {PaperPosition.objects.filter(account=keeper, is_open=True).count()}'))
        
        # Store the account ID in a file for reference
        try:
            with open('paper_trading_account_id.txt', 'w') as f:
                f.write(str(keeper.account_id))
            self.stdout.write(self.style.SUCCESS(f'\n📝 Account ID saved to paper_trading_account_id.txt'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'\n⚠️  Could not save account ID to file: {e}'))