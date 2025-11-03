"""
Inspect Paper Trading Account Database Values

This command shows the actual raw database values to identify
which field is causing the decimal.InvalidOperation error.

Usage:
    python manage.py inspect_account_data

File: paper_trading/management/commands/inspect_account_data.py
"""
from django.core.management.base import BaseCommand
from django.db import connection
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Inspect raw database values in paper trading accounts."""
    
    help = 'Inspect raw database values to find problematic decimals'
    
    def handle(self, *args, **options):
        """Execute the command."""
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.WARNING('INSPECTING PAPER TRADING ACCOUNT DATA'))
        self.stdout.write('=' * 70)
        
        try:
            self.inspect_schema()
            self.inspect_data()
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Error inspecting data: {e}')
            )
            logger.error(f"Error in inspect_account_data command", exc_info=True)
            raise
        
        self.stdout.write('=' * 70)
    
    def inspect_schema(self):
        """Show the actual database schema."""
        with connection.cursor() as cursor:
            # Get table info
            cursor.execute("PRAGMA table_info(paper_trading_accounts)")
            columns = cursor.fetchall()
            
            self.stdout.write('\n📋 DATABASE SCHEMA:')
            self.stdout.write('-' * 70)
            
            for col in columns:
                col_id, name, col_type, not_null, default_val, pk = col
                self.stdout.write(
                    f"  {name:30} | Type: {col_type:15} | Default: {default_val}"
                )
            
            self.stdout.write('')
    
    def inspect_data(self):
        """Show all raw data from the accounts table."""
        with connection.cursor() as cursor:
            # Get all columns first
            cursor.execute("PRAGMA table_info(paper_trading_accounts)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Get all data
            cursor.execute("SELECT * FROM paper_trading_accounts")
            rows = cursor.fetchall()
            
            self.stdout.write(f'\n📊 FOUND {len(rows)} ACCOUNT(S):')
            self.stdout.write('-' * 70)
            
            for idx, row in enumerate(rows, 1):
                self.stdout.write(f'\n🔍 Account #{idx}:')
                
                for col_name, value in zip(columns, row):
                    # Highlight potentially problematic values
                    value_str = str(value) if value is not None else 'NULL'
                    
                    # Check for problematic values
                    is_problem = False
                    problem_type = ''
                    
                    if value is None:
                        is_problem = True
                        problem_type = '[NULL]'
                    elif value == '':
                        is_problem = True
                        problem_type = '[EMPTY STRING]'
                    elif str(value).lower() in ['nan', 'inf', '-inf', 'infinity', '-infinity']:
                        is_problem = True
                        problem_type = '[INVALID DECIMAL]'
                    
                    # Check if it's a decimal field
                    if any(keyword in col_name.lower() for keyword in ['balance', 'usd', 'pnl', 'fee', 'price', 'eth']):
                        if is_problem:
                            self.stdout.write(
                                self.style.ERROR(
                                    f"  ❌ {col_name:30} = {value_str:20} {problem_type}"
                                )
                            )
                        else:
                            self.stdout.write(
                                f"  ✓  {col_name:30} = {value_str:20}"
                            )
                    else:
                        self.stdout.write(
                            f"     {col_name:30} = {value_str:20}"
                        )
                
                self.stdout.write('')