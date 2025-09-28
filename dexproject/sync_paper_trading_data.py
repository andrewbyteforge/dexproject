#!/usr/bin/env python
"""
Sync Paper Trading Data

This script fixes the data synchronization issue between the management command bot
and the web dashboard by ensuring both use the same user account.

Usage:
    python manage.py shell < sync_paper_trading_data.py

File: sync_paper_trading_data.py
"""

import os
import sys
import django
from decimal import Decimal

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

from django.contrib.auth.models import User
from django.utils import timezone
from paper_trading.models import (
    PaperTradingAccount,
    PaperTrade,
    PaperTradingSession,
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    PaperTradingConfig
)

def sync_paper_trading_data():
    """Sync paper trading data between management command and dashboard."""
    print("🔄 SYNCING PAPER TRADING DATA")
    print("=" * 60)
    
    # 1. Ensure demo_user exists (this is what the dashboard uses)
    demo_user, created = User.objects.get_or_create(
        username='demo_user',
        defaults={
            'email': 'demo@example.com',
            'first_name': 'Demo',
            'last_name': 'User'
        }
    )
    
    if created:
        print("✅ Created demo_user")
    else:
        print("✅ demo_user already exists")
    
    # 2. Check if demo_user has an account
    demo_account = PaperTradingAccount.objects.filter(user=demo_user).first()
    
    if not demo_account:
        print("📝 Creating paper trading account for demo_user...")
        demo_account = PaperTradingAccount.objects.create(
            user=demo_user,
            name="Demo Paper Trading Account",
            initial_balance_usd=Decimal('10000.00'),
            current_balance_usd=Decimal('10000.00'),
            is_active=True
        )
        print(f"✅ Created account: {demo_account.account_id}")
    else:
        print(f"✅ demo_user account exists: {demo_account.account_id}")
    
    # 3. Create trading config if needed
    demo_config, created = PaperTradingConfig.objects.get_or_create(
        account=demo_account,
        defaults={
            'max_daily_trades': 10,
            'max_position_size_usd': Decimal('1000.00'),
            'stop_loss_percent': Decimal('5.00'),
            'take_profit_percent': Decimal('10.00'),
            'is_active': True
        }
    )
    
    if created:
        print("✅ Created trading config for demo_user")
    else:
        print("✅ Trading config already exists for demo_user")
    
    # 4. Check for other user accounts with data
    print("\n🔍 Checking for other accounts with data...")
    
    all_accounts = PaperTradingAccount.objects.exclude(user=demo_user)
    
    for account in all_accounts:
        trades_count = PaperTrade.objects.filter(account=account).count()
        thoughts_count = PaperAIThoughtLog.objects.filter(account=account).count()
        sessions_count = PaperTradingSession.objects.filter(account=account).count()
        
        if trades_count > 0 or thoughts_count > 0 or sessions_count > 0:
            print(f"\n📊 Found data for {account.user.username}:")
            print(f"    Account: {account.account_id}")
            print(f"    Trades: {trades_count}")
            print(f"    AI Thoughts: {thoughts_count}")
            print(f"    Sessions: {sessions_count}")
            
            # Ask if we should move this data to demo_user
            move_data = input(f"\n🤔 Move this data to demo_user account? (y/N): ").strip().lower()
            
            if move_data == 'y':
                print(f"🔄 Moving data from {account.user.username} to demo_user...")
                
                # Move trades
                moved_trades = PaperTrade.objects.filter(account=account).update(account=demo_account)
                print(f"  ✅ Moved {moved_trades} trades")
                
                # Move AI thoughts
                moved_thoughts = PaperAIThoughtLog.objects.filter(account=account).update(account=demo_account)
                print(f"  ✅ Moved {moved_thoughts} AI thoughts")
                
                # Move sessions
                moved_sessions = PaperTradingSession.objects.filter(account=account).update(account=demo_account)
                print(f"  ✅ Moved {moved_sessions} sessions")
                
                # Update demo account balance from the source account
                if account.current_balance_usd != demo_account.current_balance_usd:
                    demo_account.current_balance_usd = account.current_balance_usd
                    demo_account.save()
                    print(f"  ✅ Updated balance to ${account.current_balance_usd}")
                
                print(f"  ✅ Data migration complete!")
            else:
                print(f"  ⏭️  Skipping data migration for {account.user.username}")
    
    # 5. Create some sample data if demo_user has no data
    demo_trades = PaperTrade.objects.filter(account=demo_account).count()
    demo_thoughts = PaperAIThoughtLog.objects.filter(account=demo_account).count()
    
    if demo_trades == 0 and demo_thoughts == 0:
        print("\n📝 Creating sample data for demo_user...")
        
        # Create sample strategy config
        strategy, created = PaperStrategyConfiguration.objects.get_or_create(
            account=demo_account,
            name="Demo Strategy",
            defaults={
                'is_active': True,
                'trading_mode': 'MODERATE',
                'use_fast_lane': True,
                'use_smart_lane': True,
                'max_position_size_percent': Decimal('25.00'),
                'stop_loss_percent': Decimal('5.00'),
                'take_profit_percent': Decimal('10.00'),
                'confidence_threshold': Decimal('60.00'),
                'max_daily_trades': 10
            }
        )
        
        # Create sample trade
        sample_trade = PaperTrade.objects.create(
            account=demo_account,
            trade_type='buy',
            token_in_address='0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',  # USDC
            token_in_symbol='USDC',
            token_out_address='0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',  # WETH
            token_out_symbol='WETH',
            amount_in=Decimal('500.00'),
            amount_in_usd=Decimal('500.00'),
            expected_amount_out=Decimal('0.2'),
            actual_amount_out=Decimal('0.195'),
            simulated_gas_price_gwei=Decimal('30'),
            simulated_gas_used=150000,
            simulated_gas_cost_usd=Decimal('15'),
            simulated_slippage_percent=Decimal('2.5'),
            status='completed',
            executed_at=timezone.now()
        )
        
        # Create sample AI thought
        sample_thought = PaperAIThoughtLog.objects.create(
            account=demo_account,
            paper_trade=sample_trade,
            decision_type='BUY',
            token_address=sample_trade.token_out_address,
            token_symbol=sample_trade.token_out_symbol,
            confidence_level='HIGH',
            confidence_percent=Decimal('75'),
            risk_score=Decimal('35'),
            opportunity_score=Decimal('80'),
            primary_reasoning="Strong bullish signals detected with favorable market conditions.",
            lane_used='SMART',
            strategy_name='Demo Strategy'
        )
        
        print("✅ Created sample trade and AI thought")
    
    # 6. Final summary
    print("\n📈 FINAL STATUS:")
    demo_trades = PaperTrade.objects.filter(account=demo_account).count()
    demo_thoughts = PaperAIThoughtLog.objects.filter(account=demo_account).count()
    demo_sessions = PaperTradingSession.objects.filter(account=demo_account).count()
    
    print(f"  demo_user account: {demo_account.account_id}")
    print(f"  Balance: ${demo_account.current_balance_usd}")
    print(f"  Trades: {demo_trades}")
    print(f"  AI Thoughts: {demo_thoughts}")
    print(f"  Sessions: {demo_sessions}")
    
    print("\n🎉 SYNC COMPLETE!")
    print("Now the dashboard should show the data correctly.")
    print("\nTo start the bot for the dashboard:")
    print("1. Visit the paper trading dashboard")
    print("2. Click 'Start Bot' button")
    print("3. Or run: python manage.py run_paper_bot --account-id", demo_account.pk)

if __name__ == "__main__":
    sync_paper_trading_data()