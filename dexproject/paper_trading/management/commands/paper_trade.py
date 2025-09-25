"""
Paper Trading Management Command (Simplified)

Simple command for testing paper trading.

File: dexproject/paper_trading/management/commands/paper_trade.py
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from paper_trading.models import PaperTradingAccount, PaperTradingConfig
from paper_trading.services.simulator import (
    SimplePaperTradeRequest,
    get_simulator
)


class Command(BaseCommand):
    """Simple paper trading command."""
    
    help = 'Run paper trading simulations'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--create-account',
            action='store_true',
            help='Create a paper trading account'
        )
        parser.add_argument(
            '--test-trade',
            action='store_true',
            help='Execute a test trade'
        )
        parser.add_argument(
            '--show-balance',
            action='store_true',
            help='Show account balance'
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset account to initial state'
        )
    
    def handle(self, *args, **options):
        if options['create_account']:
            self.create_account()
        elif options['test_trade']:
            self.test_trade()
        elif options['show_balance']:
            self.show_balance()
        elif options['reset']:
            self.reset_account()
        else:
            self.stdout.write("Use --help to see available options")
    
    def create_account(self):
        """Create a paper trading account."""
        # Get or create test user
        user, created = User.objects.get_or_create(
            username='papertrader',
            defaults={'email': 'paper@trader.com'}
        )
        
        # Check if account exists
        existing = PaperTradingAccount.objects.filter(user=user).first()
        if existing:
            self.stdout.write(
                self.style.WARNING(
                    f'Account already exists: {existing.account_id}'
                )
            )
            return
        
        # Create paper trading account
        account = PaperTradingAccount.objects.create(
            user=user,
            name='Test Account',
            initial_balance_usd=Decimal('10000.00')
        )
        
        # Create config
        PaperTradingConfig.objects.create(account=account)
        
        self.stdout.write(
            self.style.SUCCESS(
                f'[OK] Created paper trading account: {account.account_id}'
            )
        )
    
    def test_trade(self):
        """Execute a test trade."""
        try:
            # Get account
            account = PaperTradingAccount.objects.filter(
                is_active=True
            ).first()
            
            if not account:
                self.stdout.write(
                    self.style.ERROR(
                        '[ERROR] No active account found. Run --create-account first'
                    )
                )
                return
            
            # Show current balance
            self.stdout.write(f'Current balance: ${account.current_balance_usd}')
            
            # Create trade request
            request = SimplePaperTradeRequest(
                account=account,
                trade_type='buy',
                token_in='USDC',
                token_out='WETH',
                amount_in_usd=Decimal('100')
            )
            
            # Execute trade
            simulator = get_simulator()
            result = simulator.execute_trade(request)
            
            if result.success:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'[OK] Trade executed successfully!'
                    )
                )
                self.stdout.write(f'   Trade ID: {result.trade_id}')
                self.stdout.write(f'   Slippage: {result.slippage_percent}%')
                self.stdout.write(f'   Gas Cost: ${result.gas_cost_usd}')
                self.stdout.write(f'   TX Hash: {result.transaction_hash[:10]}...')
                
                # Reload account to show new balance
                account.refresh_from_db()
                self.stdout.write(f'New balance: ${account.current_balance_usd}')
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f'[ERROR] Trade failed: {result.error_message}'
                    )
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
    
    def show_balance(self):
        """Show account balance."""
        account = PaperTradingAccount.objects.filter(
            is_active=True
        ).first()
        
        if account:
            self.stdout.write('=' * 50)
            self.stdout.write('PAPER TRADING ACCOUNT STATUS')
            self.stdout.write('=' * 50)
            self.stdout.write(f'Account: {account.name}')
            self.stdout.write(f'Balance: ${account.current_balance_usd}')
            self.stdout.write(f'Initial: ${account.initial_balance_usd}')
            self.stdout.write(f'P&L: ${account.total_pnl_usd}')
            self.stdout.write(f'Return: {account.total_return_percent:.2f}%')
            self.stdout.write('-' * 50)
            self.stdout.write(f'Total Trades: {account.total_trades}')
            self.stdout.write(f'Successful: {account.successful_trades}')
            self.stdout.write(f'Failed: {account.failed_trades}')
            self.stdout.write(f'Win Rate: {account.win_rate:.1f}%')
            self.stdout.write(f'Fees Paid: ${account.total_fees_paid_usd}')
            self.stdout.write('=' * 50)
        else:
            self.stdout.write('No active account found')
    
    def reset_account(self):
        """Reset account to initial state."""
        account = PaperTradingAccount.objects.filter(
            is_active=True
        ).first()
        
        if account:
            account.reset_account()
            self.stdout.write(
                self.style.SUCCESS(
                    f'[OK] Account reset to ${account.initial_balance_usd}'
                )
            )
        else:
            self.stdout.write('No active account found')
