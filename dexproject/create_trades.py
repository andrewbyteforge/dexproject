#!/usr/bin/env python
"""
Ultra Simple Trade Creator - Handles decimal issues properly

Run from project root:
    python create_trades.py

File: dexproject/create_trades.py
"""

import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

from decimal import Decimal
from django.utils import timezone
from django.contrib.auth.models import User
from paper_trading.models import PaperTradingAccount, PaperTrade

def create_trades():
    """Create trades with proper decimal handling."""
    
    print("\nCreating test trades...")
    
    # Get account
    user, _ = User.objects.get_or_create(
        username='demo_user',
        defaults={'email': 'demo@example.com'}
    )
    
    account = PaperTradingAccount.objects.filter(user=user).first()
    if not account:
        account = PaperTradingAccount.objects.create(
            user=user,
            name='Demo Account',
            initial_balance_usd=Decimal('10000.00'),
            current_balance_usd=Decimal('10000.00')
        )
    
    print(f"Using account: {account.name}")
    
    # Create 5 simple BUY trades
    for i in range(5):
        trade = PaperTrade.objects.create(
            account=account,
            trade_type='buy',
            token_in_symbol='USDC',
            token_in_address='0x' + '0' * 40,
            token_out_symbol='WETH',
            token_out_address='0x' + '1' * 40,
            amount_in=Decimal('100000000000000000000'),  # 100 * 10^18
            amount_in_usd=Decimal('100.00'),
            expected_amount_out=Decimal('40000000000000000'),  # 0.04 * 10^18
            actual_amount_out=Decimal('40000000000000000'),
            simulated_gas_price_gwei=Decimal('25.0'),
            simulated_gas_used=150000,
            simulated_gas_cost_usd=Decimal('10.00'),
            simulated_slippage_percent=Decimal('1.0'),
            status='completed',
            executed_at=timezone.now(),
            execution_time_ms=1000,
            mock_tx_hash=f'0x{"a" * 64}{i:x}',
            strategy_name='Test'
        )
        print(f"  Created BUY trade #{i+1}")
    
    # Create 5 simple SELL trades
    for i in range(5):
        trade = PaperTrade.objects.create(
            account=account,
            trade_type='sell',
            token_in_symbol='WETH',
            token_in_address='0x' + '1' * 40,
            token_out_symbol='USDC',
            token_out_address='0x' + '0' * 40,
            amount_in=Decimal('40000000000000000'),  # 0.04 * 10^18
            amount_in_usd=Decimal('100.00'),
            expected_amount_out=Decimal('100000000000000000000'),  # 100 * 10^18
            actual_amount_out=Decimal('99000000000000000000'),  # 99 * 10^18
            simulated_gas_price_gwei=Decimal('25.0'),
            simulated_gas_used=150000,
            simulated_gas_cost_usd=Decimal('10.00'),
            simulated_slippage_percent=Decimal('1.0'),
            status='completed',
            executed_at=timezone.now(),
            execution_time_ms=1000,
            mock_tx_hash=f'0x{"b" * 64}{i:x}',
            strategy_name='Test'
        )
        print(f"  Created SELL trade #{i+1}")
    
    total = PaperTrade.objects.filter(account=account).count()
    print(f"\nSuccess! Total trades in account: {total}")
    print("Visit: http://127.0.0.1:8000/paper-trading/trades/")

if __name__ == "__main__":
    create_trades()