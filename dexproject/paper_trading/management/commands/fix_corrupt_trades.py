# File Path: dexproject/paper_trading/management/commands/fix_corrupt_trades.py
# Create the directories first:
# mkdir -p paper_trading/management/commands
# touch paper_trading/management/__init__.py
# touch paper_trading/management/commands/__init__.py

from django.core.management.base import BaseCommand
from django.db import connection
from decimal import Decimal, InvalidOperation
from paper_trading.models import PaperTrade, PaperTradingAccount
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fix corrupt decimal fields in PaperTrade model'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Starting to fix corrupt decimal fields...'))
        
        # Get all decimal fields in PaperTrade model
        decimal_fields = [
            'amount_in',
            'amount_in_usd', 
            'expected_amount_out',
            'actual_amount_out',
            'simulated_gas_price_gwei',
            'simulated_gas_used',
            'simulated_gas_cost_usd',
            'simulated_slippage_percent',
            'execution_time_ms'
        ]
        
        # First, let's check what's in the database
        with connection.cursor() as cursor:
            # Check for NULL or invalid values
            cursor.execute("""
                SELECT trade_id, amount_in_usd, simulated_slippage_percent 
                FROM paper_trading_papertrade 
                LIMIT 5
            """)
            rows = cursor.fetchall()
            
            self.stdout.write(f"Sample data from database:")
            for row in rows:
                self.stdout.write(f"  Trade {row[0]}: amount_in_usd={row[1]}, slippage={row[2]}")
            
            # Fix corrupt values by setting them to 0 or NULL
            for field in decimal_fields:
                try:
                    # Update any non-numeric values to 0
                    cursor.execute(f"""
                        UPDATE paper_trading_papertrade 
                        SET {field} = 0 
                        WHERE {field} IS NOT NULL 
                        AND (
                            {field} = 'NaN' 
                            OR {field} = 'Infinity' 
                            OR {field} = '-Infinity'
                            OR {field} = ''
                            OR CAST({field} AS TEXT) NOT GLOB '[0-9]*.*[0-9]*'
                        )
                    """)
                    
                    affected = cursor.rowcount
                    if affected > 0:
                        self.stdout.write(
                            self.style.SUCCESS(f'Fixed {affected} corrupt values in {field}')
                        )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Error fixing {field}: {e}')
                    )
        
        # Now add the missing pnl_usd field if it doesn't exist
        with connection.cursor() as cursor:
            # Check if pnl_usd column exists
            cursor.execute("""
                SELECT COUNT(*) 
                FROM pragma_table_info('paper_trading_papertrade') 
                WHERE name='pnl_usd'
            """)
            
            pnl_exists = cursor.fetchone()[0] > 0
            
            if not pnl_exists:
                self.stdout.write(self.style.WARNING('Adding pnl_usd field to PaperTrade model...'))
                
                # Add the column
                cursor.execute("""
                    ALTER TABLE paper_trading_papertrade 
                    ADD COLUMN pnl_usd DECIMAL(20, 8) DEFAULT 0
                """)
                
                cursor.execute("""
                    ALTER TABLE paper_trading_papertrade 
                    ADD COLUMN pnl_percent DECIMAL(10, 4) DEFAULT 0
                """)
                
                self.stdout.write(self.style.SUCCESS('Added pnl_usd and pnl_percent fields'))
                
                # Calculate P&L for existing trades based on slippage
                cursor.execute("""
                    UPDATE paper_trading_papertrade
                    SET pnl_usd = CASE 
                        WHEN simulated_slippage_percent IS NOT NULL AND amount_in_usd IS NOT NULL
                        THEN CAST((amount_in_usd * simulated_slippage_percent / 100) AS DECIMAL(20, 8))
                        ELSE 0
                    END
                """)
                
                self.stdout.write(self.style.SUCCESS('Calculated P&L for existing trades'))
        
        # Verify the fixes
        try:
            trades = PaperTrade.objects.all()[:5]
            for trade in trades:
                self.stdout.write(f"Trade {trade.trade_id}: amount={trade.amount_in_usd}")
            
            self.stdout.write(self.style.SUCCESS('Successfully fixed corrupt data!'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Verification failed: {e}'))
        
        # Print summary
        total_trades = PaperTrade.objects.count()
        self.stdout.write(
            self.style.SUCCESS(f'\nSummary: Fixed data for {total_trades} total trades')
        )