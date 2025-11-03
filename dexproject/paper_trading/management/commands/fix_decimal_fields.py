"""
Fix Decimal Field Issues in Paper Trading Accounts

This management command fixes NULL or invalid decimal values in the
PaperTradingAccount model that cause decimal.InvalidOperation errors.

Usage:
    python manage.py fix_decimal_fields

File: paper_trading/management/commands/fix_decimal_fields.py
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from paper_trading.models import PaperTradingAccount
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Fix NULL or invalid decimal values in PaperTradingAccount."""
    
    help = 'Fix NULL or invalid decimal values in paper trading accounts'
    
    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )
    
    def handle(self, *args, **options):
        """Execute the command."""
        dry_run = options.get('dry_run', False)
        
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.WARNING('FIXING DECIMAL FIELDS IN PAPER TRADING ACCOUNTS'))
        self.stdout.write('=' * 70)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n🔍 DRY RUN MODE - No changes will be made\n'))
        
        try:
            fixed_count = self.fix_decimal_fields(dry_run)
            
            if fixed_count > 0:
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(f'\n✅ Would fix {fixed_count} account(s)')
                    )
                    self.stdout.write(
                        self.style.WARNING('Run without --dry-run to apply fixes')
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(f'\n✅ Fixed {fixed_count} account(s) successfully!')
                    )
            else:
                self.stdout.write(
                    self.style.SUCCESS('\n✅ No issues found - all accounts are healthy!')
                )
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Error fixing decimal fields: {e}')
            )
            logger.error(f"Error in fix_decimal_fields command", exc_info=True)
            raise
        
        self.stdout.write('=' * 70)
    
    @transaction.atomic
    def fix_decimal_fields(self, dry_run: bool) -> int:
        """
        Fix NULL or invalid decimal values.
        
        Args:
            dry_run: If True, only report issues without fixing
            
        Returns:
            Number of accounts fixed
        """
        fixed_count = 0
        
        # Get all accounts using raw SQL to bypass decimal conversion
        from django.db import connection
        
        with connection.cursor() as cursor:
            # Query to find problematic records
            cursor.execute("""
                SELECT 
                    account_id,
                    name,
                    current_balance_usd,
                    initial_balance_usd,
                    total_profit_loss_usd
                FROM paper_trading_accounts
            """)
            
            rows = cursor.fetchall()
            
            self.stdout.write(f'\n📊 Checking {len(rows)} account(s)...\n')
            
            for row in rows:
                account_id, name, current_balance, initial_balance, total_pnl = row
                needs_fix = False
                fixes = []
                
                # Check current_balance_usd
                if current_balance is None or current_balance == '':
                    needs_fix = True
                    new_balance = initial_balance if initial_balance else '10000.00'
                    fixes.append(f"current_balance_usd: NULL → {new_balance}")
                
                # Check initial_balance_usd
                if initial_balance is None or initial_balance == '':
                    needs_fix = True
                    fixes.append(f"initial_balance_usd: NULL → 10000.00")
                
                # Check total_profit_loss_usd
                if total_pnl is None or total_pnl == '':
                    needs_fix = True
                    fixes.append(f"total_profit_loss_usd: NULL → 0.00")
                
                if needs_fix:
                    fixed_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'\n🔧 Account: {name} ({account_id})')
                    )
                    for fix in fixes:
                        self.stdout.write(f'   • {fix}')
                    
                    if not dry_run:
                        # Fix the values using raw SQL
                        update_sql = """
                            UPDATE paper_trading_accounts
                            SET 
                                current_balance_usd = COALESCE(
                                    NULLIF(current_balance_usd, ''),
                                    COALESCE(NULLIF(initial_balance_usd, ''), '10000.00')
                                ),
                                initial_balance_usd = COALESCE(
                                    NULLIF(initial_balance_usd, ''),
                                    '10000.00'
                                ),
                                total_profit_loss_usd = COALESCE(
                                    NULLIF(total_profit_loss_usd, ''),
                                    '0.00'
                                )
                            WHERE account_id = ?
                        """
                        cursor.execute(update_sql, [account_id])
                        self.stdout.write(
                            self.style.SUCCESS('   ✅ Fixed!')
                        )
        
        return fixed_count