"""
Fix Corrupted Decimals in Trades and Positions

This command fixes decimal values in PaperTrade and PaperPosition tables.

Usage:
    python manage.py fix_trades_positions

File: paper_trading/management/commands/fix_trades_positions.py
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction


class Command(BaseCommand):
    """Fix corrupted decimal values in trades and positions."""
    
    help = 'Fix corrupted decimal values in trades and positions'
    
    def handle(self, *args, **options):
        """Execute the command."""
        
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.WARNING('FIXING TRADES AND POSITIONS'))
        self.stdout.write('=' * 70)
        
        try:
            trades_fixed = self.fix_trades()
            positions_fixed = self.fix_positions()
            
            total = trades_fixed + positions_fixed
            
            if total > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'\n✅ Fixed {trades_fixed} trade(s) and {positions_fixed} position(s)!')
                )
                self.stdout.write(
                    self.style.SUCCESS('🎉 You can now refresh your browser!')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS('\n✅ No corrupted values found!')
                )
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Error: {e}')
            )
            raise
        
        self.stdout.write('=' * 70)
    
    @transaction.atomic
    def fix_trades(self):
        """Fix trades table."""
        fixed = 0
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM paper_trades")
            count = cursor.fetchone()[0]
            
            self.stdout.write(f'\n📊 Checking {count} trade(s)...')
            
            if count == 0:
                return 0
            
            # Get all trades
            cursor.execute("""
                SELECT trade_id, amount_in_usd, simulated_gas_cost_usd, 
                       simulated_slippage_percent, simulated_gas_price_gwei
                FROM paper_trades
            """)
            
            trades = cursor.fetchall()
            
            for trade_id, amount_usd, gas_cost, slippage, gas_price in trades:
                needs_fix = False
                
                if self._is_invalid(amount_usd):
                    needs_fix = True
                if self._is_invalid(gas_cost):
                    needs_fix = True
                if self._is_invalid(slippage):
                    needs_fix = True
                if self._is_invalid(gas_price):
                    needs_fix = True
                
                if needs_fix:
                    fixed += 1
                    self.stdout.write(f'  🔧 Fixing trade {trade_id[:8]}...')
                    
                    # Set safe default values
                    cursor.execute("""
                        UPDATE paper_trades 
                        SET amount_in_usd = 10.00,
                            simulated_gas_cost_usd = 0.50,
                            simulated_slippage_percent = 0.50,
                            simulated_gas_price_gwei = 1.00
                        WHERE trade_id = '%s'
                    """ % trade_id)
        
        if fixed > 0:
            self.stdout.write(self.style.SUCCESS(f'  ✅ Fixed {fixed} trade(s)'))
        
        return fixed
    
    @transaction.atomic
    def fix_positions(self):
        """Fix positions table."""
        fixed = 0
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM paper_positions")
            count = cursor.fetchone()[0]
            
            self.stdout.write(f'\n📊 Checking {count} position(s)...')
            
            if count == 0:
                return 0
            
            # Get all positions
            cursor.execute("""
                SELECT position_id, quantity, average_entry_price_usd,
                       total_invested_usd, current_price_usd, 
                       current_value_usd, unrealized_pnl_usd
                FROM paper_positions
            """)
            
            positions = cursor.fetchall()
            
            for pos_id, qty, entry_price, invested, current_price, current_val, pnl in positions:
                needs_fix = False
                
                if self._is_invalid(qty):
                    needs_fix = True
                if self._is_invalid(entry_price):
                    needs_fix = True
                if self._is_invalid(invested):
                    needs_fix = True
                if self._is_invalid(current_price):
                    needs_fix = True
                if self._is_invalid(current_val):
                    needs_fix = True
                if self._is_invalid(pnl):
                    needs_fix = True
                
                if needs_fix:
                    fixed += 1
                    self.stdout.write(f'  🔧 Fixing position {pos_id[:8]}...')
                    
                    # Set safe default values
                    cursor.execute("""
                        UPDATE paper_positions 
                        SET quantity = 1000000000000000000,
                            average_entry_price_usd = 1.00,
                            total_invested_usd = 10.00,
                            current_price_usd = 1.00,
                            current_value_usd = 10.00,
                            unrealized_pnl_usd = 0.00
                        WHERE position_id = '%s'
                    """ % pos_id)
        
        if fixed > 0:
            self.stdout.write(self.style.SUCCESS(f'  ✅ Fixed {fixed} position(s)'))
        
        return fixed
    
    def _is_invalid(self, value):
        """Check if a decimal value is invalid."""
        if value is None:
            return False
        
        value_str = str(value).lower()
        
        # Check for scientific notation or invalid values
        if 'e' in value_str or 'nan' in value_str or 'inf' in value_str:
            return True
        
        # Check for empty string
        if value_str == '':
            return True
        
        return False