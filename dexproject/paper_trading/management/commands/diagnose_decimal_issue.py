"""
DIAGNOSTIC: Find Which Field is Causing decimal.InvalidOperation

This will test each field individually to find the problem.

File: dexproject/paper_trading/management/commands/diagnose_decimal_issue.py

Usage:
    python manage.py diagnose_decimal_issue
"""

from django.core.management.base import BaseCommand
from django.db import connection
from decimal import Decimal


class Command(BaseCommand):
    """Diagnose which decimal field is causing issues."""
    
    help = 'Find which field causes decimal.InvalidOperation'

    def handle(self, *args, **options):
        """Execute diagnostic."""
        self.stdout.write('='*60)
        self.stdout.write('DECIMAL FIELD DIAGNOSTIC')
        self.stdout.write('='*60)
        
        from paper_trading.models import PaperTrade
        
        # All decimal fields in PaperTrade
        decimal_fields = [
            'amount_in',
            'amount_in_usd',
            'expected_amount_out',
            'actual_amount_out',
            'simulated_gas_price_gwei',
            'simulated_gas_used',
            'simulated_gas_cost_usd',
            'simulated_slippage_percent',
        ]
        
        # Get all trade IDs
        with connection.cursor() as cursor:
            cursor.execute("SELECT trade_id FROM paper_trades LIMIT 10")
            trade_ids = [row[0] for row in cursor.fetchall()]
        
        self.stdout.write(f'\nTesting {len(trade_ids)} trades...\n')
        
        # Test each field individually
        for field in decimal_fields:
            self.stdout.write(f'Testing {field}...')
            
            problem_count = 0
            for trade_id in trade_ids:
                try:
                    # Try to load just this one field
                    trade = PaperTrade.objects.filter(trade_id=trade_id).values(field).first()
                    if trade:
                        value = trade[field]
                        # Try to convert to Decimal
                        if value is not None:
                            _ = Decimal(str(value))
                except Exception as e:
                    problem_count += 1
                    if problem_count == 1:
                        self.stdout.write(f'  ✗ PROBLEM FOUND!')
                        self.stdout.write(f'  Trade {trade_id}: {e}')
                        
                        # Show the actual database value
                        with connection.cursor() as cursor:
                            cursor.execute(f"SELECT {field} FROM paper_trades WHERE trade_id = ?", [trade_id])
                            raw_value = cursor.fetchone()[0]
                            self.stdout.write(f'  Raw DB value: {raw_value} (type: {type(raw_value)})')
            
            if problem_count == 0:
                self.stdout.write(f'  ✓ OK')
            else:
                self.stdout.write(f'  ✗ {problem_count} problems found')
        
        # Try to load full trade objects
        self.stdout.write('\n' + '='*60)
        self.stdout.write('Testing full trade loading...')
        self.stdout.write('='*60)
        
        for i, trade_id in enumerate(trade_ids[:3]):
            self.stdout.write(f'\nTrade {i+1}: {trade_id}')
            try:
                trade = PaperTrade.objects.get(trade_id=trade_id)
                self.stdout.write('  ✓ Loaded successfully')
                
                # Try to access each decimal field
                for field in decimal_fields:
                    try:
                        value = getattr(trade, field)
                        self.stdout.write(f'  ✓ {field} = {value}')
                    except Exception as e:
                        self.stdout.write(f'  ✗ {field} FAILED: {e}')
                        
            except Exception as e:
                self.stdout.write(f'  ✗ Failed to load trade: {e}')
        
        self.stdout.write('\n' + '='*60)
        self.stdout.write('DIAGNOSTIC COMPLETE')
        self.stdout.write('='*60)