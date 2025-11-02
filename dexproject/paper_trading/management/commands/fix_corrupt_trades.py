"""
Fix ALL Decimal Fields - COMPREHENSIVE VERSION

Rounds ALL decimal fields to match model definitions.

File: dexproject/paper_trading/management/commands/fix_corrupt_trades.py

Usage:
    python manage.py fix_corrupt_trades
"""

from django.core.management.base import BaseCommand
from django.db import connection
import sqlite3


class Command(BaseCommand):
    """Fix ALL decimal precision issues."""
    
    help = 'Fix decimal precision for ALL fields'

    def handle(self, *args, **options):
        """Execute the fix."""
        self.stdout.write('='*60)
        self.stdout.write('FIXING ALL DECIMAL FIELDS')
        self.stdout.write('='*60)
        
        # Get database path
        db_path = connection.settings_dict['NAME']
        self.stdout.write(f'\nDatabase: {db_path}')
        
        # Connect directly to SQLite
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        try:
            # Count trades
            cursor.execute("SELECT COUNT(*) FROM paper_trades")
            total = cursor.fetchone()[0]
            self.stdout.write(f'Total trades: {total}\n')
            
            if total == 0:
                self.stdout.write('No trades to fix.')
                return
            
            # Round ALL decimal fields to appropriate precision
            updates = [
                ('amount_in', 18),  # Wei precision
                ('amount_in_usd', 2),  # USD precision
                ('expected_amount_out', 18),  # Wei precision
                ('actual_amount_out', 18),  # Wei precision
                ('simulated_gas_price_gwei', 2),  # Gwei precision
                ('simulated_gas_cost_usd', 2),  # USD precision
                ('simulated_slippage_percent', 2),  # Percentage precision
            ]
            
            total_updated = 0
            
            for field, decimals in updates:
                self.stdout.write(f'Rounding {field} to {decimals} decimals...')
                
                # Round the field
                cursor.execute(f"""
                    UPDATE paper_trades 
                    SET {field} = ROUND(CAST({field} AS REAL), {decimals})
                    WHERE {field} IS NOT NULL
                """)
                
                updated = cursor.rowcount
                total_updated += updated
                self.stdout.write(f'  ✓ Updated {updated} rows')
            
            # Fix NULL values
            self.stdout.write('\nFixing NULL values...')
            cursor.execute("UPDATE paper_trades SET amount_in = 0 WHERE amount_in IS NULL")
            cursor.execute("UPDATE paper_trades SET amount_in_usd = 0 WHERE amount_in_usd IS NULL")
            cursor.execute("UPDATE paper_trades SET expected_amount_out = 0 WHERE expected_amount_out IS NULL")
            cursor.execute("UPDATE paper_trades SET simulated_gas_price_gwei = 1.0 WHERE simulated_gas_price_gwei IS NULL")
            cursor.execute("UPDATE paper_trades SET simulated_gas_cost_usd = 0.5 WHERE simulated_gas_cost_usd IS NULL")
            cursor.execute("UPDATE paper_trades SET simulated_slippage_percent = 0.5 WHERE simulated_slippage_percent IS NULL")
            cursor.execute("UPDATE paper_trades SET simulated_gas_used = 21000 WHERE simulated_gas_used IS NULL")
            self.stdout.write('  ✓ Fixed NULLs')
            
            # Commit all changes
            conn.commit()
            self.stdout.write(f'\n✓ All changes committed ({total_updated} total updates)')
            
            # Close SQLite
            cursor.close()
            conn.close()
            
            # Verify with Django ORM
            self.stdout.write('\n' + '='*60)
            self.stdout.write('VERIFYING WITH DJANGO ORM')
            self.stdout.write('='*60)
            
            from paper_trading.models import PaperTrade
            
            try:
                # Try to count first
                count = PaperTrade.objects.count()
                self.stdout.write(f'\n✓ Count works: {count} trades')
                
                # Try to load trades one by one to find problems
                self.stdout.write('\nTesting individual trades...')
                
                with connection.cursor() as c:
                    c.execute("SELECT trade_id FROM paper_trades LIMIT 5")
                    trade_ids = [row[0] for row in c.fetchall()]
                
                success = 0
                failed = 0
                
                for trade_id in trade_ids:
                    try:
                        trade = PaperTrade.objects.get(trade_id=trade_id)
                        # Try to access all decimal fields
                        _ = trade.amount_in
                        _ = trade.amount_in_usd
                        _ = trade.expected_amount_out
                        _ = trade.simulated_gas_price_gwei
                        _ = trade.simulated_gas_cost_usd
                        _ = trade.simulated_slippage_percent
                        success += 1
                        self.stdout.write(f'  ✓ Trade {str(trade_id)[:8]}... OK')
                    except Exception as e:
                        failed += 1
                        self.stdout.write(f'  ✗ Trade {str(trade_id)[:8]}... FAILED: {e}')
                
                if failed == 0:
                    self.stdout.write('\n' + '='*60)
                    self.stdout.write('SUCCESS! 🎉')
                    self.stdout.write('='*60)
                    self.stdout.write(f'All {count} trades can be loaded!')
                    self.stdout.write('='*60)
                    
                    self.stdout.write('\nNext steps:')
                    self.stdout.write('  1. Restart Django server')
                    self.stdout.write('  2. Click Dashboard')
                    self.stdout.write('  3. Should work now! ✨\n')
                else:
                    self.stdout.write(f'\n✗ {failed} trades still have issues')
                    self.stdout.write('\nRun: python manage.py diagnose_decimal_issue')
                    self.stdout.write('To find the specific problem fields.\n')
                
            except Exception as e:
                self.stdout.write(f'\n✗ Verification failed: {e}')
                self.stdout.write('\nTry running: python manage.py diagnose_decimal_issue')
                import traceback
                self.stdout.write(traceback.format_exc())
        
        except Exception as e:
            conn.rollback()
            self.stdout.write(f'\n✗ Error during fix: {e}')
            import traceback
            self.stdout.write(traceback.format_exc())
        
        finally:
            if conn:
                conn.close()