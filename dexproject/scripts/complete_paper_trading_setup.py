#!/usr/bin/env python3
"""
Complete Paper Trading Setup Script (Windows Compatible)

This script adds the remaining files needed for the paper trading system:
- Services directory and simulator
- Management command for paper trading

Run after creating the initial app structure.

File: dexproject/scripts/complete_paper_trading_setup.py
"""

import os
import sys
from pathlib import Path

def complete_paper_trading_setup():
    """Add remaining paper trading files."""
    
    print("Completing Paper Trading setup...")
    
    # Base directory for the app
    app_dir = Path("paper_trading")
    
    if not app_dir.exists():
        print("Error: paper_trading directory not found!")
        print("   Run create_paper_trading_app.py first")
        return False
    
    # Create services directory
    services_dir = app_dir / "services"
    services_dir.mkdir(exist_ok=True)
    (services_dir / "__init__.py").touch()
    print("Created services directory")
    
    # Create simplified simulator (without complex imports and emojis)
    simulator_content = '''"""
Paper Trading Simulator Service (Simplified)

A simplified simulator that works without Phase 6B dependencies for testing.

File: dexproject/paper_trading/services/simulator.py
"""

import logging
import random
import time
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timezone
from dataclasses import dataclass
import uuid

from django.contrib.auth.models import User
from django.db import transaction as db_transaction

from ..models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingConfig
)

logger = logging.getLogger(__name__)


@dataclass
class SimplePaperTradeRequest:
    """Simple request to execute a paper trade."""
    
    account: PaperTradingAccount
    trade_type: str  # 'buy', 'sell', 'swap'
    token_in: str
    token_out: str
    amount_in_usd: Decimal
    slippage_tolerance: Decimal = Decimal('0.005')  # 0.5%


@dataclass
class SimplePaperTradeResult:
    """Result of a paper trade execution."""
    
    success: bool
    trade_id: str
    trade: Optional[PaperTrade] = None
    position: Optional[PaperPosition] = None
    execution_time_ms: float = 0.0
    gas_cost_usd: Decimal = Decimal('0')
    slippage_percent: Decimal = Decimal('0')
    error_message: Optional[str] = None
    transaction_hash: Optional[str] = None


class SimplePaperTradingSimulator:
    """
    Simplified paper trading simulator for testing.
    
    Features:
    - Basic slippage simulation
    - Simple gas cost estimation
    - Position tracking
    - P&L calculation
    """
    
    def __init__(self):
        """Initialize the simulator."""
        self.logger = logging.getLogger('paper_trading.simulator')
        
    def execute_trade(self, request: SimplePaperTradeRequest) -> SimplePaperTradeResult:
        """
        Execute a paper trade with basic simulation.
        
        Args:
            request: Paper trade request parameters
            
        Returns:
            SimplePaperTradeResult with execution details
        """
        start_time = time.time()
        trade_id = str(uuid.uuid4())
        
        try:
            self.logger.info(
                f"[PAPER] Executing paper trade: {request.trade_type} "
                f"${request.amount_in_usd} of {request.token_in}"
            )
            
            # Validate trade
            if request.account.current_balance_usd < request.amount_in_usd:
                return SimplePaperTradeResult(
                    success=False,
                    trade_id=trade_id,
                    error_message="Insufficient balance"
                )
            
            # Create paper trade record
            paper_trade = PaperTrade(
                trade_id=trade_id,
                account=request.account,
                trade_type=request.trade_type,
                token_in_address=request.token_in,
                token_in_symbol=self._get_token_symbol(request.token_in),
                token_out_address=request.token_out,
                token_out_symbol=self._get_token_symbol(request.token_out),
                amount_in=self._usd_to_wei(request.amount_in_usd),
                amount_in_usd=request.amount_in_usd,
                expected_amount_out=self._usd_to_wei(request.amount_in_usd),
                status='executing'
            )
            
            # Simulate gas costs (simplified)
            gas_cost = Decimal('5.00')  # Fixed $5 gas cost
            paper_trade.simulated_gas_price_gwei = Decimal('20')
            paper_trade.simulated_gas_used = 150000
            paper_trade.simulated_gas_cost_usd = gas_cost
            
            # Simulate slippage
            slippage = self._simulate_slippage(request.amount_in_usd)
            paper_trade.simulated_slippage_percent = slippage
            
            # Calculate actual amount with slippage
            slippage_factor = Decimal('1') - (slippage / Decimal('100'))
            paper_trade.actual_amount_out = paper_trade.expected_amount_out * slippage_factor
            
            # Random failure (2% chance)
            if random.random() < 0.02:
                paper_trade.status = 'failed'
                paper_trade.error_message = "Transaction failed: insufficient liquidity"
                paper_trade.save()
                
                return SimplePaperTradeResult(
                    success=False,
                    trade_id=trade_id,
                    trade=paper_trade,
                    error_message=paper_trade.error_message
                )
            
            # Update account balances
            with db_transaction.atomic():
                request.account.current_balance_usd -= (request.amount_in_usd + gas_cost)
                request.account.total_fees_paid_usd += gas_cost
                request.account.total_trades += 1
                request.account.successful_trades += 1
                request.account.save()
            
            # Update position (simplified)
            position = self._update_position(
                request.account,
                request.token_out,
                request.amount_in_usd
            )
            
            # Complete trade
            paper_trade.status = 'completed'
            paper_trade.executed_at = datetime.now(timezone.utc)
            paper_trade.execution_time_ms = int((time.time() - start_time) * 1000)
            paper_trade.mock_tx_hash = self._generate_mock_tx_hash()
            paper_trade.mock_block_number = random.randint(18000000, 18100000)
            paper_trade.save()
            
            self.logger.info(
                f"[SUCCESS] Paper trade completed: {trade_id} "
                f"(slippage: {slippage}%, gas: ${gas_cost})"
            )
            
            return SimplePaperTradeResult(
                success=True,
                trade_id=trade_id,
                trade=paper_trade,
                position=position,
                execution_time_ms=paper_trade.execution_time_ms,
                gas_cost_usd=gas_cost,
                slippage_percent=slippage,
                transaction_hash=paper_trade.mock_tx_hash
            )
            
        except Exception as e:
            self.logger.error(f"[ERROR] Paper trade failed: {e}")
            return SimplePaperTradeResult(
                success=False,
                trade_id=trade_id,
                error_message=str(e)
            )
    
    def _simulate_slippage(self, amount_usd: Decimal) -> Decimal:
        """Simulate basic slippage."""
        base_slippage = 0.5
        size_impact = min(float(amount_usd) / 10000 * 0.5, 2.0)
        volatility = random.uniform(-0.2, 0.8)
        total_slippage = max(0, base_slippage + size_impact + volatility)
        return Decimal(str(min(total_slippage, 5.0)))
    
    def _update_position(
        self,
        account: PaperTradingAccount,
        token_address: str,
        amount_usd: Decimal
    ) -> Optional[PaperPosition]:
        """Update or create position (simplified)."""
        with db_transaction.atomic():
            position, created = PaperPosition.objects.get_or_create(
                account=account,
                token_address=token_address,
                is_open=True,
                defaults={
                    'token_symbol': self._get_token_symbol(token_address),
                    'quantity': Decimal('0'),
                    'average_entry_price_usd': Decimal('1'),
                    'total_invested_usd': Decimal('0')
                }
            )
            
            # Simple position update
            position.quantity += amount_usd  # Simplified: using USD as quantity
            position.total_invested_usd += amount_usd
            position.save()
            
            return position
    
    def _get_token_symbol(self, address: str) -> str:
        """Get token symbol from address."""
        symbols = {
            'WETH': 'WETH',
            'USDC': 'USDC',
            'USDT': 'USDT',
        }
        return symbols.get(address.upper(), address[:6].upper())
    
    def _usd_to_wei(self, usd_amount: Decimal) -> Decimal:
        """Convert USD to wei (simplified)."""
        return usd_amount * Decimal('1e18')
    
    def _generate_mock_tx_hash(self) -> str:
        """Generate mock transaction hash."""
        return f"0x{''.join(random.choices('0123456789abcdef', k=64))}"


# Singleton instance
_simulator = None

def get_simulator() -> SimplePaperTradingSimulator:
    """Get simulator instance."""
    global _simulator
    if _simulator is None:
        _simulator = SimplePaperTradingSimulator()
    return _simulator
'''
    
    # Write with UTF-8 encoding
    with open(services_dir / "simulator.py", "w", encoding='utf-8') as f:
        f.write(simulator_content)
    print("Created simplified simulator service")
    
    # Create management command
    cmd_content = '''"""
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
'''
    
    # Create command file with UTF-8 encoding
    cmd_path = app_dir / "management" / "commands" / "paper_trade.py"
    with open(cmd_path, "w", encoding='utf-8') as f:
        f.write(cmd_content)
    print("Created paper_trade management command")
    
    print("\nPaper Trading setup completed!")
    print("\nNext steps:")
    print("1. Add 'paper_trading' to INSTALLED_APPS")
    print("2. Run: python manage.py makemigrations paper_trading")
    print("3. Run: python manage.py migrate")
    print("4. Run: python manage.py paper_trade --create-account")
    print("5. Run: python manage.py paper_trade --test-trade")
    
    return True


if __name__ == "__main__":
    success = complete_paper_trading_setup()
    if not success:
        sys.exit(1)