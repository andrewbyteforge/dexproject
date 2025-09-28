#!/usr/bin/env python
"""
Debug Paper Trading Accounts

This script checks the current state of paper trading accounts and users
to diagnose the synchronization issue between the management command bot
and the web dashboard.

Usage:
    python manage.py shell < debug_paper_trading_accounts.py

File: debug_paper_trading_accounts.py
"""

import os
import sys
import django
from decimal import Decimal

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

from django.contrib.auth.models import User
from paper_trading.models import (
    PaperTradingAccount,
    PaperTrade,
    PaperTradingSession,
    PaperAIThoughtLog,
    PaperStrategyConfiguration
)

def debug_accounts():
    """Debug paper trading accounts and data."""
    print("🔍 DEBUGGING PAPER TRADING ACCOUNTS")
    print("=" * 60)
    
    # 1. Check all users
    print("\n📊 ALL USERS:")
    users = User.objects.all()
    for user in users:
        print(f"  • {user.username} (ID: {user.id}) - {user.email}")
    
    # 2. Check all paper trading accounts
    print("\n💰 ALL PAPER TRADING ACCOUNTS:")
    accounts = PaperTradingAccount.objects.all()
    for account in accounts:
        print(f"  • Account: {account.name}")
        print(f"    User: {account.user.username}")
        print(f"    ID: {account.account_id}")
        print(f"    Balance: ${account.current_balance_usd}")
        print(f"    Active: {account.is_active}")
        print(f"    Created: {account.created_at}")
        print()
    
    # 3. Check active sessions
    print("\n🎯 ACTIVE TRADING SESSIONS:")
    active_sessions = PaperTradingSession.objects.filter(status='ACTIVE')
    for session in active_sessions:
        print(f"  • Session: {session.name}")
        print(f"    ID: {session.session_id}")
        print(f"    Account: {session.account.name} ({session.account.user.username})")
        print(f"    Status: {session.status}")
        print(f"    Started: {session.start_time}")
        print()
    
    # 4. Check recent trades
    print("\n💱 RECENT TRADES (Last 10):")
    recent_trades = PaperTrade.objects.all().order_by('-created_at')[:10]
    for trade in recent_trades:
        print(f"  • {trade.trade_type.upper()}: {trade.token_out_symbol}")
        print(f"    Account: {trade.account.user.username}")
        print(f"    Amount: ${trade.amount_in_usd}")
        print(f"    Status: {trade.status}")
        print(f"    Created: {trade.created_at}")
        print()
    
    # 5. Check AI thoughts
    print("\n🧠 RECENT AI THOUGHTS (Last 5):")
    recent_thoughts = PaperAIThoughtLog.objects.all().order_by('-created_at')[:5]
    for thought in recent_thoughts:
        print(f"  • {thought.decision_type}: {thought.token_symbol}")
        print(f"    Account: {thought.account.user.username}")
        print(f"    Confidence: {thought.confidence_percent}%")
        print(f"    Lane: {thought.lane_used}")
        print(f"    Created: {thought.created_at}")
        print()
    
    # 6. Summary
    print("\n📈 SUMMARY:")
    print(f"  Total Users: {users.count()}")
    print(f"  Total Accounts: {accounts.count()}")
    print(f"  Active Sessions: {active_sessions.count()}")
    print(f"  Total Trades: {PaperTrade.objects.count()}")
    print(f"  Total AI Thoughts: {PaperAIThoughtLog.objects.count()}")
    
    # 7. Check specific users that dashboard expects
    print("\n🎯 SPECIFIC USER CHECK:")
    
    # Check demo_user (dashboard)
    try:
        demo_user = User.objects.get(username='demo_user')
        demo_account = PaperTradingAccount.objects.filter(user=demo_user).first()
        print(f"  demo_user: ✅ EXISTS")
        if demo_account:
            print(f"    Account: ✅ {demo_account.account_id}")
            print(f"    Balance: ${demo_account.current_balance_usd}")
            trades_count = PaperTrade.objects.filter(account=demo_account).count()
            thoughts_count = PaperAIThoughtLog.objects.filter(account=demo_account).count()
            print(f"    Trades: {trades_count}")
            print(f"    AI Thoughts: {thoughts_count}")
        else:
            print(f"    Account: ❌ NO ACCOUNT")
    except User.DoesNotExist:
        print(f"  demo_user: ❌ DOES NOT EXIST")
    
    # Check papertrader (management command might use this)
    try:
        paper_user = User.objects.get(username='papertrader')
        paper_account = PaperTradingAccount.objects.filter(user=paper_user).first()
        print(f"  papertrader: ✅ EXISTS")
        if paper_account:
            print(f"    Account: ✅ {paper_account.account_id}")
            print(f"    Balance: ${paper_account.current_balance_usd}")
            trades_count = PaperTrade.objects.filter(account=paper_account).count()
            thoughts_count = PaperAIThoughtLog.objects.filter(account=paper_account).count()
            print(f"    Trades: {trades_count}")
            print(f"    AI Thoughts: {thoughts_count}")
        else:
            print(f"    Account: ❌ NO ACCOUNT")
    except User.DoesNotExist:
        print(f"  papertrader: ❌ DOES NOT EXIST")

if __name__ == "__main__":
    debug_accounts()