#!/usr/bin/env python
"""
Generate Test Trades for Paper Trading Dashboard

This script creates sample trades to verify the dashboard is working correctly.

Run from project root:
    python generate_test_trades.py

File: dexproject/generate_test_trades.py
"""

import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

import random
import uuid
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
from django.contrib.auth.models import User

from paper_trading.models import (
    PaperTradingAccount,
    PaperTrade,
    PaperAIThoughtLog,
    PaperStrategyConfiguration
)

def generate_test_trades(num_trades=10):
    """Generate test trades for the paper trading system."""
    
    print("\n" + "="*60)
    print("PAPER TRADING TEST DATA GENERATOR")
    print("="*60)
    
    # Get the demo_user account
    try:
        user = User.objects.get(username='demo_user')
        account = PaperTradingAccount.objects.filter(user=user).first()
        
        if not account:
            print("❌ No paper trading account found for demo_user")
            return
        
        print(f"✅ Found account: {account.name} (ID: {account.account_id})")
        print(f"   Current balance: ${account.current_balance_usd:.2f}")
        
    except User.DoesNotExist:
        print("❌ demo_user not found")
        return
    
    # Token data
    tokens = [
        {'symbol': 'WETH', 'address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', 'price': 2500},
        {'symbol': 'WBTC', 'address': '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599', 'price': 45000},
        {'symbol': 'UNI', 'address': '0x1f9840a85d5aF5bf1D1762F925BDADdc4201F984', 'price': 6.50},
        {'symbol': 'AAVE', 'address': '0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9', 'price': 95},
        {'symbol': 'LINK', 'address': '0x514910771AF9Ca656af840dff83E8264EcF986CA', 'price': 15},
        {'symbol': 'MATIC', 'address': '0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0', 'price': 0.85},
    ]
    
    trades_created = 0
    
    print(f"\n📝 Generating {num_trades} test trades...")
    
    for i in range(num_trades):
        # Randomly select token and trade type
        token = random.choice(tokens)
        trade_type = random.choice(['buy', 'sell'])
        
        # Generate trade amounts
        amount_usd = Decimal(str(random.uniform(50, 500)))
        token_price = Decimal(str(token['price']))
        
        # Add some price variation
        price_variation = Decimal(str(random.uniform(0.95, 1.05)))
        current_price = token_price * price_variation
        
        # Calculate slippage and gas
        slippage = Decimal(str(random.uniform(0.5, 2.5)))
        gas_price = Decimal(str(random.uniform(15, 40)))
        gas_used = random.randint(100000, 200000)
        gas_cost = (gas_price * gas_used) / Decimal('1e9') * Decimal('3000')
        
        # Determine tokens based on trade type
        if trade_type == 'buy':
            token_in_symbol = 'USDC'
            token_in_address = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'
            token_out_symbol = token['symbol']
            token_out_address = token['address']
            token_quantity = amount_usd / current_price
            expected_out = token_quantity * (Decimal('1') - slippage / Decimal('100'))
        else:
            token_in_symbol = token['symbol']
            token_in_address = token['address']
            token_out_symbol = 'USDC'
            token_out_address = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'
            token_quantity = amount_usd / current_price
            expected_out = amount_usd * (Decimal('1') - slippage / Decimal('100'))
        
        # Create the trade with random timestamp in last 24 hours
        hours_ago = random.randint(0, 23)
        trade_time = timezone.now() - timedelta(hours=hours_ago, minutes=random.randint(0, 59))
        
        trade = PaperTrade.objects.create(
            account=account,
            trade_type=trade_type,  # lowercase!
            token_in_address=token_in_address,
            token_in_symbol=token_in_symbol,
            token_out_address=token_out_address,
            token_out_symbol=token_out_symbol,
            amount_in=amount_usd * Decimal('1e18'),
            amount_in_usd=amount_usd,
            expected_amount_out=expected_out * Decimal('1e18'),
            actual_amount_out=expected_out * Decimal('1e18'),
            simulated_gas_price_gwei=gas_price,
            simulated_gas_used=gas_used,
            simulated_gas_cost_usd=gas_cost,
            simulated_slippage_percent=slippage,
            status='completed',  # lowercase!
            created_at=trade_time,
            executed_at=trade_time,
            execution_time_ms=random.randint(500, 2000),
            mock_tx_hash='0x' + uuid.uuid4().hex,
            mock_block_number=random.randint(18000000, 18100000),
            strategy_name='Test_Strategy',
            metadata={
                'test_trade': True,
                'intel_level': 5,
                'confidence': random.randint(60, 95)
            }
        )
        
        # Create AI thought log for the trade
        confidence = random.randint(60, 95)
        PaperAIThoughtLog.objects.create(
            account=account,
            paper_trade=trade,
            decision_type=trade_type.upper(),
            token_address=token_out_address if trade_type == 'buy' else token_in_address,
            token_symbol=token['symbol'],
            confidence_level='HIGH' if confidence >= 70 else 'MEDIUM',
            confidence_percent=Decimal(str(confidence)),
            risk_score=Decimal(str(random.randint(20, 60))),
            opportunity_score=Decimal(str(random.randint(60, 90))),
            primary_reasoning=f"Test trade {i+1}: Market analysis indicates {'bullish' if trade_type == 'buy' else 'bearish'} momentum for {token['symbol']}. "
                            f"Technical indicators suggest a favorable entry point with manageable risk.",
            lane_used='SMART',
            strategy_name='Test_Strategy',
            created_at=trade_time
        )
        
        trades_created += 1
        
        # Update account balance
        if trade_type == 'buy':
            account.current_balance_usd -= (amount_usd + gas_cost)
        else:
            account.current_balance_usd += (expected_out - gas_cost)
        
        print(f"   ✅ Trade {i+1}: {trade_type.upper()} {token['symbol']} - ${amount_usd:.2f}")
    
    # Save final balance and update trade count
    account.total_trades = PaperTrade.objects.filter(account=account).count()
    account.save()
    
    print(f"\n📊 Summary:")
    print(f"   • Created {trades_created} test trades")
    print(f"   • Final balance: ${account.current_balance_usd:.2f}")
    print(f"   • Total trades in account: {account.total_trades}")
    
    print("\n✅ Test data generation complete!")
    print("\n🎯 Next steps:")
    print("   1. Visit http://127.0.0.1:8000/paper-trading/trades/")
    print("   2. You should now see the test trades")
    print("   3. Check the analytics page for updated metrics")
    print("="*60)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate test trades for paper trading')
    parser.add_argument('--count', type=int, default=10, help='Number of trades to generate (default: 10)')
    parser.add_argument('--clear', action='store_true', help='Clear existing trades before generating')
    
    args = parser.parse_args()
    
    if args.clear:
        print("\n⚠️  Clearing existing trades...")
        try:
            user = User.objects.get(username='demo_user')
            account = PaperTradingAccount.objects.filter(user=user).first()
            if account:
                PaperTrade.objects.filter(account=account).delete()
                PaperAIThoughtLog.objects.filter(account=account).delete()
                # Reset balance
                account.current_balance_usd = Decimal('10000')
                account.total_trades = 0
                account.save()
                print("✅ Existing trades cleared")
        except:
            pass
    
    generate_test_trades(args.count)


if __name__ == "__main__":
    main()