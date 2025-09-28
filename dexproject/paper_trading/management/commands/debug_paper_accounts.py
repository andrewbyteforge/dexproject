"""
Debug Paper Trading Accounts Management Command

This command checks the current state of paper trading accounts and users
to diagnose the synchronization issue between the management command bot
and the web dashboard.

File: dexproject/paper_trading/management/commands/debug_paper_accounts.py
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from paper_trading.models import (
    PaperTradingAccount,
    PaperTrade,
    PaperTradingSession,
    PaperAIThoughtLog,
    PaperStrategyConfiguration
)


class Command(BaseCommand):
    """Debug paper trading accounts and data."""
    
    help = 'Debug paper trading accounts and synchronization issues'
    
    def handle(self, *args, **options):
        """Execute the debug command."""
        self.stdout.write("=" * 60)
        self.stdout.write("DEBUGGING PAPER TRADING ACCOUNTS")
        self.stdout.write("=" * 60)
        
        # 1. Check all users
        self.stdout.write("\n1. ALL USERS:")
        users = User.objects.all()
        for user in users:
            self.stdout.write(f"  - {user.username} (ID: {user.id}) - {user.email}")
        
        # 2. Check all paper trading accounts
        self.stdout.write("\n2. ALL PAPER TRADING ACCOUNTS:")
        accounts = PaperTradingAccount.objects.all()
        for account in accounts:
            self.stdout.write(f"  - Account: {account.name}")
            self.stdout.write(f"    User: {account.user.username}")
            self.stdout.write(f"    ID: {account.account_id}")
            self.stdout.write(f"    Balance: ${account.current_balance_usd}")
            self.stdout.write(f"    Active: {account.is_active}")
            self.stdout.write(f"    Created: {account.created_at}")
            self.stdout.write("")
        
        # 3. Check active sessions
        self.stdout.write("3. ACTIVE TRADING SESSIONS:")
        active_sessions = PaperTradingSession.objects.filter(status='ACTIVE')
        for session in active_sessions:
            self.stdout.write(f"  - Session: {session.name}")
            self.stdout.write(f"    ID: {session.session_id}")
            self.stdout.write(f"    Account: {session.account.name} ({session.account.user.username})")
            self.stdout.write(f"    Status: {session.status}")
            self.stdout.write(f"    Started: {session.started_at}")
            self.stdout.write("")
        
        # 4. Check recent trades
        self.stdout.write("4. RECENT TRADES (Last 10):")
        recent_trades = PaperTrade.objects.all().order_by('-created_at')[:10]
        for trade in recent_trades:
            self.stdout.write(f"  - {trade.trade_type.upper()}: {trade.token_out_symbol}")
            self.stdout.write(f"    Account: {trade.account.user.username}")
            self.stdout.write(f"    Amount: ${trade.amount_in_usd}")
            self.stdout.write(f"    Status: {trade.status}")
            self.stdout.write(f"    Created: {trade.created_at}")
            self.stdout.write("")
        
        # 5. Check AI thoughts
        self.stdout.write("5. RECENT AI THOUGHTS (Last 5):")
        recent_thoughts = PaperAIThoughtLog.objects.all().order_by('-created_at')[:5]
        for thought in recent_thoughts:
            self.stdout.write(f"  - {thought.decision_type}: {thought.token_symbol}")
            self.stdout.write(f"    Account: {thought.account.user.username}")
            self.stdout.write(f"    Confidence: {thought.confidence_percent}%")
            self.stdout.write(f"    Lane: {thought.lane_used}")
            self.stdout.write(f"    Created: {thought.created_at}")
            self.stdout.write("")
        
        # 6. Summary
        self.stdout.write("6. SUMMARY:")
        self.stdout.write(f"  Total Users: {users.count()}")
        self.stdout.write(f"  Total Accounts: {accounts.count()}")
        self.stdout.write(f"  Active Sessions: {active_sessions.count()}")
        self.stdout.write(f"  Total Trades: {PaperTrade.objects.count()}")
        self.stdout.write(f"  Total AI Thoughts: {PaperAIThoughtLog.objects.count()}")
        
        # 7. Check specific users that dashboard expects
        self.stdout.write("\n7. SPECIFIC USER CHECK:")
        
        # Check demo_user (dashboard)
        try:
            demo_user = User.objects.get(username='demo_user')
            demo_account = PaperTradingAccount.objects.filter(user=demo_user).first()
            self.stdout.write("  demo_user: EXISTS")
            if demo_account:
                self.stdout.write(f"    Account: {demo_account.account_id}")
                self.stdout.write(f"    Balance: ${demo_account.current_balance_usd}")
                trades_count = PaperTrade.objects.filter(account=demo_account).count()
                thoughts_count = PaperAIThoughtLog.objects.filter(account=demo_account).count()
                self.stdout.write(f"    Trades: {trades_count}")
                self.stdout.write(f"    AI Thoughts: {thoughts_count}")
            else:
                self.stdout.write("    Account: NO ACCOUNT")
        except User.DoesNotExist:
            self.stdout.write("  demo_user: DOES NOT EXIST")
        
        # Check papertrader (management command might use this)
        try:
            paper_user = User.objects.get(username='papertrader')
            paper_account = PaperTradingAccount.objects.filter(user=paper_user).first()
            self.stdout.write("  papertrader: EXISTS")
            if paper_account:
                self.stdout.write(f"    Account: {paper_account.account_id}")
                self.stdout.write(f"    Balance: ${paper_account.current_balance_usd}")
                trades_count = PaperTrade.objects.filter(account=paper_account).count()
                thoughts_count = PaperAIThoughtLog.objects.filter(account=paper_account).count()
                self.stdout.write(f"    Trades: {trades_count}")
                self.stdout.write(f"    AI Thoughts: {thoughts_count}")
            else:
                self.stdout.write("    Account: NO ACCOUNT")
        except User.DoesNotExist:
            self.stdout.write("  papertrader: DOES NOT EXIST")
        
        # Check paper_trader (another possible user)
        try:
            paper_trader_user = User.objects.get(username='paper_trader')
            paper_trader_account = PaperTradingAccount.objects.filter(user=paper_trader_user).first()
            self.stdout.write("  paper_trader: EXISTS")
            if paper_trader_account:
                self.stdout.write(f"    Account: {paper_trader_account.account_id}")
                self.stdout.write(f"    Balance: ${paper_trader_account.current_balance_usd}")
                trades_count = PaperTrade.objects.filter(account=paper_trader_account).count()
                thoughts_count = PaperAIThoughtLog.objects.filter(account=paper_trader_account).count()
                self.stdout.write(f"    Trades: {trades_count}")
                self.stdout.write(f"    AI Thoughts: {thoughts_count}")
            else:
                self.stdout.write("    Account: NO ACCOUNT")
        except User.DoesNotExist:
            self.stdout.write("  paper_trader: DOES NOT EXIST")
        
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("DEBUG COMPLETE")
        self.stdout.write("=" * 60)