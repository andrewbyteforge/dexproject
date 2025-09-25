"""
Management command to run the paper trading bot.

This command starts the automated paper trading bot with
configurable parameters.

File: dexproject/paper_trading/management/commands/run_paper_bot.py
"""

import logging
from typing import Optional
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from paper_trading.models import (
    PaperTradingAccount,
    PaperStrategyConfiguration
)
from paper_trading.bot.simple_trader import SimplePaperBot

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Run the paper trading bot."""
    
    help = 'Starts the automated paper trading bot'
    
    def __init__(self):
        """Initialize the command."""
        super().__init__()
        self.bot = None
    
    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            '--account',
            type=str,
            help='Account ID or name to use'
        )
        parser.add_argument(
            '--strategy',
            type=str,
            help='Strategy configuration ID or name'
        )
        parser.add_argument(
            '--username',
            type=str,
            help='Username for account selection'
        )
        parser.add_argument(
            '--create-account',
            action='store_true',
            help='Create a new account if needed'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=30,
            help='Check interval in seconds (default: 30)'
        )
    
    def handle(self, *args, **options):
        """Execute the command."""
        self.stdout.write("=" * 80)
        self.stdout.write(self.style.SUCCESS("PAPER TRADING BOT"))
        self.stdout.write("=" * 80)
        
        try:
            # Get or create account
            account = self._get_account(options)
            if not account:
                self.stdout.write(self.style.ERROR("No account available"))
                return
            
            # Get strategy configuration
            strategy = self._get_strategy(account, options)
            
            # Display configuration
            self._display_configuration(account, strategy)
            
            # Create bot instance
            self.bot = SimplePaperBot(
                account_id=str(account.account_id),
                strategy_config_id=str(strategy.config_id) if strategy else None
            )
            
            # Set check interval
            if options['interval']:
                self.bot.check_interval = options['interval']
            
            # Run the bot
            self.stdout.write("\n🚀 Starting bot...")
            self.stdout.write("Press Ctrl+C to stop\n")
            
            try:
                self.bot.start()
            except KeyboardInterrupt:
                self.stdout.write("\n\n⏹️  Stopping bot...")
                self.bot.stop("User requested shutdown")
            
            self.stdout.write(self.style.SUCCESS("\n✅ Bot stopped successfully"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Error: {e}"))
            logger.error(f"Bot failed", exc_info=True)
    
    def _get_account(self, options) -> Optional[PaperTradingAccount]:
        """Get or create paper trading account."""
        account = None
        
        # Try to find by account ID or name
        if options['account']:
            try:
                # Try as UUID first
                account = PaperTradingAccount.objects.get(
                    account_id=options['account']
                )
            except (PaperTradingAccount.DoesNotExist, ValueError):
                # Try as name
                account = PaperTradingAccount.objects.filter(
                    name__icontains=options['account']
                ).first()
        
        # Try to find by username
        elif options['username']:
            try:
                user = User.objects.get(username=options['username'])
                account = PaperTradingAccount.objects.filter(
                    user=user,
                    is_active=True
                ).first()
            except User.DoesNotExist:
                self.stdout.write(f"User '{options['username']}' not found")
        
        # Get first active account
        else:
            account = PaperTradingAccount.objects.filter(
                is_active=True
            ).first()
        
        # Create account if requested
        if not account and options['create_account']:
            self.stdout.write("Creating new paper trading account...")
            
            # Get or create user
            user = User.objects.first()
            if not user:
                user = User.objects.create_user(
                    username='paper_bot',
                    email='bot@papertrading.local'
                )
            
            account = PaperTradingAccount.objects.create(
                user=user,
                name="Auto-Trading Bot Account",
                initial_balance_usd=Decimal('10000'),
                current_balance_usd=Decimal('10000')
            )
            self.stdout.write(f"Created account: {account.name}")
        
        return account
    
    def _get_strategy(self, account: PaperTradingAccount, options) -> Optional[PaperStrategyConfiguration]:
        """Get strategy configuration."""
        strategy = None
        
        if options['strategy']:
            try:
                # Try as UUID first
                strategy = PaperStrategyConfiguration.objects.get(
                    config_id=options['strategy']
                )
            except (PaperStrategyConfiguration.DoesNotExist, ValueError):
                # Try as name
                strategy = PaperStrategyConfiguration.objects.filter(
                    account=account,
                    name__icontains=options['strategy']
                ).first()
        else:
            # Get first active strategy for account
            strategy = PaperStrategyConfiguration.objects.filter(
                account=account,
                is_active=True
            ).first()
        
        return strategy
    
    def _display_configuration(self, account: PaperTradingAccount, strategy: Optional[PaperStrategyConfiguration]):
        """Display bot configuration."""
        self.stdout.write("\n📋 Configuration:")
        self.stdout.write("-" * 40)
        self.stdout.write(f"Account: {account.name}")
        self.stdout.write(f"Balance: ${account.current_balance_usd:.2f}")
        self.stdout.write(f"Total Trades: {account.total_trades}")
        
        if strategy:
            self.stdout.write(f"\nStrategy: {strategy.name}")
            self.stdout.write(f"Mode: {strategy.trading_mode}")
            self.stdout.write(f"Confidence: {strategy.confidence_threshold}%")
            self.stdout.write(f"Max Daily Trades: {strategy.max_daily_trades}")
            
            lanes = []
            if strategy.use_fast_lane:
                lanes.append("Fast")
            if strategy.use_smart_lane:
                lanes.append("Smart")
            self.stdout.write(f"Lanes: {', '.join(lanes) if lanes else 'None'}")
        else:
            self.stdout.write("\nStrategy: Default (will be created)")