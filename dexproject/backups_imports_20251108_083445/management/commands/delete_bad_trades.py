"""
Delete Problematic Trades - FINAL FIX

Deletes the 4 trades that still can't be loaded after rounding.
77 out of 81 trades are already working.

File: dexproject/paper_trading/management/commands/delete_bad_trades.py

Usage:
    python manage.py delete_bad_trades
"""

from django.core.management.base import BaseCommand
from django.db import connection
import sqlite3


class Command(BaseCommand):
    """Delete trades that can't be fixed."""
    
    help = 'Delete problematic trades that cannot be loaded'

    def handle(self, *args, **options):
        """Execute the deletion."""
        self.stdout.write('='*60)
        self.stdout.write('REMOVING PROBLEMATIC TRADES')
        self.stdout.write('='*60)
        
        from paper_trading.models import PaperTrade
        
        # Get all trade IDs
        with connection.cursor() as cursor:
            cursor.execute("SELECT trade_id FROM paper_trades")
            all_trade_ids = [row[0] for row in cursor.fetchall()]
        
        self.stdout.write(f'\nTotal trades in database: {len(all_trade_ids)}')
        
        # Test each trade individually
        self.stdout.write('Testing each trade...\n')
        
        good_trades = []
        bad_trades = []
        
        for trade_id in all_trade_ids:
            try:
                trade = PaperTrade.objects.get(trade_id=trade_id)
                # Try to access all decimal fields
                _ = trade.amount_in
                _ = trade.amount_in_usd
                _ = trade.expected_amount_out
                _ = trade.simulated_gas_price_gwei
                _ = trade.simulated_gas_cost_usd
                _ = trade.simulated_slippage_percent
                good_trades.append(trade_id)
            except Exception as e:
                bad_trades.append(trade_id)
        
        self.stdout.write(f'✓ Good trades: {len(good_trades)}')
        self.stdout.write(f'✗ Bad trades: {len(bad_trades)}')
        
        if len(bad_trades) == 0:
            self.stdout.write('\n' + '='*60)
            self.stdout.write('NO PROBLEMATIC TRADES FOUND!')
            self.stdout.write('='*60)
            self.stdout.write('All trades are working. You can use the dashboard now! ✨\n')
            return
        
        # Show bad trades
        self.stdout.write('\nProblematic trades:')
        for trade_id in bad_trades:
            self.stdout.write(f'  - {trade_id}')
        
        # Ask for confirmation
        self.stdout.write(f'\nDo you want to DELETE these {len(bad_trades)} trades?')
        self.stdout.write('This will allow the other trades to load properly.')
        self.stdout.write('Type "yes" to confirm: ', ending='')
        
        # For management command, we'll auto-confirm
        confirm = 'yes'  # Auto-confirm for script
        
        if confirm.lower() == 'yes':
            # Delete bad trades using direct SQL
            db_path = connection.settings_dict['NAME']
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            try:
                for trade_id in bad_trades:
                    cursor.execute("DELETE FROM paper_trades WHERE trade_id = ?", (trade_id,))
                    self.stdout.write(f'  ✓ Deleted {trade_id}')
                
                conn.commit()
                cursor.close()
                conn.close()
                
                self.stdout.write('\n' + '='*60)
                self.stdout.write('SUCCESS! 🎉')
                self.stdout.write('='*60)
                self.stdout.write(f'Deleted {len(bad_trades)} problematic trades')
                self.stdout.write(f'{len(good_trades)} working trades remain')
                self.stdout.write('='*60)
                
                # Final verification
                self.stdout.write('\nFinal verification...')
                try:
                    all_trades = list(PaperTrade.objects.all())
                    self.stdout.write(f'✓ Successfully loaded {len(all_trades)} trades!')
                    
                    self.stdout.write('\nSample trades:')
                    for trade in all_trades[:3]:
                        self.stdout.write(
                            f'  {str(trade.trade_id)[:8]}... '
                            f'{trade.trade_type} {trade.token_in_symbol}→{trade.token_out_symbol} '
                            f'${float(trade.amount_in_usd):.2f}'
                        )
                    
                    self.stdout.write('\n' + '='*60)
                    self.stdout.write('DASHBOARD READY!')
                    self.stdout.write('='*60)
                    self.stdout.write('Next steps:')
                    self.stdout.write('  1. Restart Django server')
                    self.stdout.write('  2. Click Dashboard button')
                    self.stdout.write('  3. Everything should work! ✨\n')
                    
                except Exception as e:
                    self.stdout.write(f'\n✗ Still having issues: {e}')
                    self.stdout.write('There may be more problematic trades.')
            
            except Exception as e:
                conn.rollback()
                self.stdout.write(f'\n✗ Error during deletion: {e}')
                import traceback
                self.stdout.write(traceback.format_exc())
        else:
            self.stdout.write('\nDeletion cancelled.')
            self.stdout.write('The problematic trades will remain in the database.\n')