"""
Aggressive Decimal Fix - Handles Quantization Issues

This fixes decimals that might have too many decimal places for Django's quantize operation.

Usage:
    python manage.py aggressive_decimal_fix

File: paper_trading/management/commands/aggressive_decimal_fix.py
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from decimal import Decimal, InvalidOperation


class Command(BaseCommand):
    """Aggressively fix all decimal fields that might cause quantization errors."""
    
    help = 'Aggressively fix decimal quantization issues'
    
    def handle(self, *args, **options):
        """Execute the command."""
        
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.WARNING('AGGRESSIVE DECIMAL FIX'))
        self.stdout.write('=' * 70)
        
        try:
            trades_fixed = self.fix_all_trades()
            positions_fixed = self.fix_all_positions()
            
            total = trades_fixed + positions_fixed
            
            self.stdout.write(
                self.style.SUCCESS(f'\n✅ Fixed {trades_fixed} trade(s) and {positions_fixed} position(s)!')
            )
            self.stdout.write(
                self.style.SUCCESS('🎉 Restart your server and refresh browser!')
            )
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Error: {e}')
            )
            import traceback
            traceback.print_exc()
            raise
        
        self.stdout.write('=' * 70)
    
    @transaction.atomic
    def fix_all_trades(self):
        """Fix ALL trades by rounding to proper decimal places."""
        
        self.stdout.write('\n📊 Fixing ALL trades...')
        
        with connection.cursor() as cursor:
            # Round all decimal fields to their proper decimal places
            
            # amount_in and expected_amount_out: 18 decimal places (wei)
            cursor.execute("""
                UPDATE paper_trades 
                SET amount_in = ROUND(CAST(amount_in AS REAL), 18),
                    expected_amount_out = ROUND(CAST(expected_amount_out AS REAL), 18),
                    actual_amount_out = CASE 
                        WHEN actual_amount_out IS NOT NULL 
                        THEN ROUND(CAST(actual_amount_out AS REAL), 18)
                        ELSE NULL 
                    END
            """)
            
            # USD amounts: 2 decimal places
            cursor.execute("""
                UPDATE paper_trades
                SET amount_in_usd = ROUND(CAST(amount_in_usd AS REAL), 2),
                    simulated_gas_cost_usd = ROUND(CAST(simulated_gas_cost_usd AS REAL), 2)
            """)
            
            # Percentages and gwei: 2 decimal places
            cursor.execute("""
                UPDATE paper_trades
                SET simulated_slippage_percent = ROUND(CAST(simulated_slippage_percent AS REAL), 2),
                    simulated_gas_price_gwei = ROUND(CAST(simulated_gas_price_gwei AS REAL), 2)
            """)
            
            cursor.execute("SELECT COUNT(*) FROM paper_trades")
            count = cursor.fetchone()[0]
            
            self.stdout.write(self.style.SUCCESS(f'  ✅ Processed {count} trade(s)'))
            
            return count
    
    @transaction.atomic
    def fix_all_positions(self):
        """Fix ALL positions by rounding to proper decimal places."""
        
        self.stdout.write('\n📊 Fixing ALL positions...')
        
        with connection.cursor() as cursor:
            # quantity: 18 decimal places (wei)
            cursor.execute("""
                UPDATE paper_positions
                SET quantity = ROUND(CAST(quantity AS REAL), 18)
            """)
            
            # Prices: 8 decimal places
            cursor.execute("""
                UPDATE paper_positions
                SET average_entry_price_usd = ROUND(CAST(average_entry_price_usd AS REAL), 8),
                    current_price_usd = CASE 
                        WHEN current_price_usd IS NOT NULL 
                        THEN ROUND(CAST(current_price_usd AS REAL), 8)
                        ELSE NULL 
                    END
            """)
            
            # USD amounts: 2 decimal places  
            cursor.execute("""
                UPDATE paper_positions
                SET total_invested_usd = ROUND(CAST(total_invested_usd AS REAL), 2),
                    current_value_usd = CASE 
                        WHEN current_value_usd IS NOT NULL 
                        THEN ROUND(CAST(current_value_usd AS REAL), 2)
                        ELSE NULL 
                    END,
                    unrealized_pnl_usd = ROUND(CAST(unrealized_pnl_usd AS REAL), 2),
                    realized_pnl_usd = ROUND(CAST(realized_pnl_usd AS REAL), 2)
            """)
            
            cursor.execute("SELECT COUNT(*) FROM paper_positions")
            count = cursor.fetchone()[0]
            
            self.stdout.write(self.style.SUCCESS(f'  ✅ Processed {count} position(s)'))
            
            return count