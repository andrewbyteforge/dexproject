"""
Management Command: Clean up paper trading accounts (Robust version)

Consolidates to a single paper trading account for single-user operation.
Handles duplicate entries and partial migrations gracefully.

Usage:
    python manage.py cleanup_paper_accounts

File: dexproject/paper_trading/management/commands/cleanup_paper_accounts.py
"""

from django.core.management.base import BaseCommand
from django.db import transaction, connection
from decimal import Decimal

from paper_trading.models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingSession,
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    PaperPerformanceMetrics
)


class Command(BaseCommand):
    """Clean up duplicate paper trading accounts."""
    
    help = 'Consolidate to a single paper trading account'
    
    def handle(self, *args, **options):
        """Execute the cleanup."""
        self.stdout.write("\n" + "="*60)
        self.stdout.write("PAPER TRADING ACCOUNT CLEANUP (ROBUST VERSION)")
        self.stdout.write("="*60 + "\n")
        
        # Get all accounts
        accounts = PaperTradingAccount.objects.all()
        
        if accounts.count() == 0:
            # No accounts - create one
            self.stdout.write("No accounts found. Creating default account...")
            self._create_default_account()
            
        elif accounts.count() == 1:
            # Already have just one
            account = accounts.first()
            self.stdout.write(f"✅ Already using single account: {account.name}")
            self.stdout.write(f"   Balance: ${account.current_balance_usd:.2f}")
            # Rename if needed
            if account.name != "Main_Trading_Account":
                account.name = "Main_Trading_Account"
                account.save()
                self.stdout.write(f"   Renamed to: {account.name}")
            
        else:
            # Multiple accounts - consolidate
            self.stdout.write(f"Found {accounts.count()} accounts. Consolidating...")
            self._consolidate_accounts_robust(accounts)
        
        self.stdout.write("\n✅ Cleanup complete!")
    
    def _create_default_account(self):
        """Create a default paper trading account."""
        account = PaperTradingAccount.objects.create(
            name="Main_Trading_Account",
            initial_balance_usd=Decimal('10000.00'),
            current_balance_usd=Decimal('10000.00')
        )
        self.stdout.write(f"✅ Created account: {account.name}")
        self.stdout.write(f"   ID: {account.account_id}")
        self.stdout.write(f"   Balance: ${account.current_balance_usd:.2f}")
    
    @transaction.atomic
    def _consolidate_accounts_robust(self, accounts):
        """Consolidate multiple accounts into one (robust version)."""
        # Display current accounts
        self.stdout.write("\nCurrent accounts:")
        for i, acc in enumerate(accounts, 1):
            self.stdout.write(
                f"  {i}. {acc.name} "
                f"(ID: {acc.pk}, Balance: ${acc.current_balance_usd:.2f}, "
                f"Trades: {acc.trades.count()})"
            )
        
        # Find or decide primary account
        # First check if "Main_Trading_Account" already exists
        primary = accounts.filter(name="Main_Trading_Account").first()
        
        if not primary:
            # Use the account with most activity
            primary = None
            max_score = 0
            
            for acc in accounts:
                score = (
                    acc.trades.count() * 10 +  # Weight trades heavily
                    float(acc.current_balance_usd) / 1000 +  # Consider balance
                    (100 if "Intel" in acc.name else 0)  # Prefer Intel bot account
                )
                if score > max_score:
                    max_score = score
                    primary = acc
        
        self.stdout.write(f"\n📌 Primary account: {primary.name} (ID: {primary.pk})")
        
        # Ask for confirmation
        confirm = input("\nProceed with consolidation? (yes/no): ")
        if confirm.lower() != 'yes':
            self.stdout.write("Cancelled.")
            return
        
        # Migrate data from other accounts
        for acc in accounts:
            if acc.pk != primary.pk:
                self.stdout.write(f"\nMigrating from {acc.name} (ID: {acc.pk})...")
                
                try:
                    # Move trades
                    trade_count = acc.trades.count()
                    if trade_count > 0:
                        acc.trades.update(account=primary)
                        self.stdout.write(f"  ✓ Moved {trade_count} trades")
                except Exception as e:
                    self.stdout.write(f"  ⚠ Could not move trades: {e}")
                
                try:
                    # Move positions
                    position_count = acc.positions.count()
                    if position_count > 0:
                        acc.positions.update(account=primary)
                        self.stdout.write(f"  ✓ Moved {position_count} positions")
                except Exception as e:
                    self.stdout.write(f"  ⚠ Could not move positions: {e}")
                
                try:
                    # Move sessions
                    session_count = acc.trading_sessions.count()
                    if session_count > 0:
                        acc.trading_sessions.update(account=primary)
                        self.stdout.write(f"  ✓ Moved {session_count} sessions")
                except Exception as e:
                    self.stdout.write(f"  ⚠ Could not move sessions: {e}")
                
                try:
                    # Move thought logs
                    thought_count = PaperAIThoughtLog.objects.filter(account=acc).count()
                    if thought_count > 0:
                        PaperAIThoughtLog.objects.filter(account=acc).update(account=primary)
                        self.stdout.write(f"  ✓ Moved {thought_count} thought logs")
                except Exception as e:
                    self.stdout.write(f"  ⚠ Could not move thought logs: {e}")
                
                try:
                    # Handle strategy configs carefully (due to unique constraint)
                    strategy_count = 0
                    for strategy in acc.strategy_configs.all():
                        # Check if primary already has a strategy with this name
                        existing = primary.strategy_configs.filter(name=strategy.name).first()
                        if existing:
                            # Update existing with better settings if needed
                            if strategy.is_active and not existing.is_active:
                                existing.is_active = True
                                existing.save()
                            # Delete duplicate
                            strategy.delete()
                            self.stdout.write(f"  ✓ Merged duplicate strategy: {strategy.name}")
                        else:
                            # Move to primary
                            strategy.account = primary
                            strategy.save()
                            strategy_count += 1
                    
                    if strategy_count > 0:
                        self.stdout.write(f"  ✓ Moved {strategy_count} strategies")
                except Exception as e:
                    self.stdout.write(f"  ⚠ Could not move strategies: {e}")
                
                try:
                    # Delete the duplicate account
                    acc.delete()
                    self.stdout.write(f"  ✓ Deleted account {acc.name}")
                except Exception as e:
                    self.stdout.write(f"  ⚠ Could not delete account: {e}")
        
        # Update primary account name if needed
        if primary.name != "Main_Trading_Account":
            primary.name = "Main_Trading_Account"
            primary.save()
            self.stdout.write(f"\n✅ Renamed primary account to: {primary.name}")
        
        # Final summary
        remaining = PaperTradingAccount.objects.all()
        self.stdout.write(f"\n✅ Consolidation complete!")
        self.stdout.write(f"   Accounts remaining: {remaining.count()}")
        if remaining.count() == 1:
            final = remaining.first()
            self.stdout.write(f"   Single account: {final.name}")
            self.stdout.write(f"   ID: {final.account_id}")
            self.stdout.write(f"   Balance: ${final.current_balance_usd:.2f}")
            self.stdout.write(f"   Total trades: {final.trades.count()}")
            self.stdout.write(f"   Total sessions: {final.trading_sessions.count()}")