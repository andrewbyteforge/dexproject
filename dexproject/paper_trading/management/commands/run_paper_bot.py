"""
Django Management Command - Run Paper Trading Bot

This command runs the enhanced paper trading bot with AI decision-making capabilities.
It provides options for configuration and monitoring of the bot's performance.

Usage:
    python manage.py run_paper_bot
    python manage.py run_paper_bot --account-id 2 --tick-interval 10
    python manage.py run_paper_bot --create-account --reset

File: dexproject/paper_trading/management/commands/run_paper_bot.py
"""

import logging
import sys
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone

from paper_trading.models import (
    PaperTradingAccount,
    PaperTradingSession,
    PaperStrategyConfiguration
)
from paper_trading.bot.simple_trader import EnhancedPaperTradingBot


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Django management command to run the enhanced paper trading bot.
    
    This command initializes and runs the paper trading bot with AI-driven
    decision making, Fast/Smart lane strategies, and comprehensive logging.
    """
    
    help = 'Run the enhanced paper trading bot with AI decision engine'
    
    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument(
            '--account-id',
            type=int,
            default=None,
            help='Paper trading account ID to use'
        )
        
        parser.add_argument(
            '--create-account',
            action='store_true',
            help='Create a new paper trading account'
        )
        
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset the account balance before starting'
        )
        
        parser.add_argument(
            '--tick-interval',
            type=int,
            default=5,
            help='Seconds between market analysis ticks (default: 5)'
        )
        
        parser.add_argument(
            '--initial-balance',
            type=float,
            default=10000.0,
            help='Initial account balance in USD (default: 10000)'
        )
        
        parser.add_argument(
            '--strategy-mode',
            choices=['FAST', 'SMART', 'HYBRID'],
            default='HYBRID',
            help='Trading strategy mode (default: HYBRID)'
        )
        
        parser.add_argument(
            '--max-position-size',
            type=float,
            default=25.0,
            help='Maximum position size as percentage (default: 25%%)'
        )
        
        parser.add_argument(
            '--stop-loss',
            type=float,
            default=5.0,
            help='Default stop loss percentage (default: 5%%)'
        )
        
        parser.add_argument(
            '--take-profit',
            type=float,
            default=10.0,
            help='Default take profit percentage (default: 10%%)'
        )
    
    def handle(self, *args, **options):
        """Execute the command."""
        self.stdout.write(self.style.SUCCESS('🚀 Starting Enhanced Paper Trading Bot...'))
        
        # Get or create account
        account = self._get_or_create_account(options)
        if not account:
            self.stdout.write(self.style.ERROR('❌ Failed to get/create account'))
            return
        
        # Configure strategy
        self._configure_strategy(account, options)
        
        # Display configuration
        self._display_configuration(account, options)
        
        # Create and run bot
        try:
            self.stdout.write(self.style.SUCCESS(f'🤖 Initializing bot for account: {account.name}'))
            
            # Create bot instance
            bot = EnhancedPaperTradingBot(account_id=account.pk)
            bot.tick_interval = options['tick_interval']
            
            # Initialize bot
            if not bot.initialize():
                self.stdout.write(self.style.ERROR('❌ Bot initialization failed'))
                return
            
            self.stdout.write(self.style.SUCCESS('✅ Bot initialized successfully'))
            self.stdout.write(self.style.WARNING('Press Ctrl+C to stop the bot gracefully\n'))
            
            # Run the bot
            bot.run()
            
            self.stdout.write(self.style.SUCCESS('\n✅ Bot stopped successfully'))
            
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\n🛑 Shutting down bot...'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Bot error: {e}'))
            logger.exception("Bot crashed with exception")
            sys.exit(1)
    
    def _get_or_create_account(self, options):
        """Get existing account or create new one."""
        account_id = options.get('account_id')
        create_new = options.get('create_account')
        reset = options.get('reset')
        initial_balance = Decimal(str(options.get('initial_balance', 10000)))
        
        if create_new:
            # Create new account
            try:
                # Get or create a default user
                user, _ = User.objects.get_or_create(
                    username='paper_trader',
                    defaults={'email': 'paper@trading.bot'}
                )
                
                # Create account with timestamp
                account = PaperTradingAccount.objects.create(
                    user=user,
                    name=f"AI_Bot_{timezone.now().strftime('%Y%m%d_%H%M%S')}",
                    initial_balance_usd=initial_balance,
                    current_balance_usd=initial_balance
                )
                
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Created new account: {account.name} (ID: {account.id})')
                )
                return account
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Failed to create account: {e}'))
                return None
        
        # Get existing account
        if account_id:
            try:
                account = PaperTradingAccount.objects.get(id=account_id)
                
                # Reset if requested
                if reset:
                    account.reset_account()
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Reset account: {account.name}')
                    )
                
                return account
                
            except PaperTradingAccount.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Account with ID {account_id} not found'))
                return None
        
        # Get or create default account
        try:
            user, _ = User.objects.get_or_create(
                username='paper_trader',
                defaults={'email': 'paper@trading.bot'}
            )
            
            account, created = PaperTradingAccount.objects.get_or_create(
                user=user,
                name='Default_AI_Bot',
                defaults={
                    'initial_balance_usd': initial_balance,
                    'current_balance_usd': initial_balance
                }
            )
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Created default account: {account.name}')
                )
            else:
                if reset:
                    account.reset_account()
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Reset account: {account.name}')
                    )
            
            return account
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to get/create default account: {e}'))
            return None
    
    def _configure_strategy(self, account, options):
        """Configure trading strategy for the bot."""
        try:
            # Map strategy mode to trading mode
            mode_mapping = {
            'FAST': 'AGGRESSIVE',
            'SMART': 'CONSERVATIVE',
            'HYBRID': 'MODERATE'
            }

            # Get or create strategy configuration
            strategy, created = PaperStrategyConfiguration.objects.get_or_create(
                account=account,
                name=f"Strategy_{account.name}",
                defaults={
                    'is_active': True,
                    'trading_mode': mode_mapping.get(options['strategy_mode'], 'MODERATE'),
                    'use_fast_lane': options['strategy_mode'] in ['FAST', 'HYBRID'],
                    'use_smart_lane': options['strategy_mode'] in ['SMART', 'HYBRID'],
                    'max_position_size_percent': Decimal(str(options['max_position_size'])),
                    'stop_loss_percent': Decimal(str(options['stop_loss'])),
                    'take_profit_percent': Decimal(str(options['take_profit'])),
                    'max_daily_trades': 100,
                    'confidence_threshold': Decimal("40"),
                }
            )
            
            if not created:
                # Update existing strategy
                strategy.trading_mode = mode_mapping.get(options['strategy_mode'], 'MODERATE')
                strategy.use_fast_lane = options['strategy_mode'] in ['FAST', 'HYBRID']
                strategy.use_smart_lane = options['strategy_mode'] in ['SMART', 'HYBRID']
                strategy.max_position_size_percent = Decimal(str(options['max_position_size']))
                strategy.stop_loss_percent = Decimal(str(options['stop_loss']))
                strategy.take_profit_percent = Decimal(str(options['take_profit']))
                strategy.save()
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Strategy configured: {options["strategy_mode"]} mode')
            )
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to configure strategy: {e}'))
    
    def _display_configuration(self, account, options):
        """Display bot configuration."""
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('📋 BOT CONFIGURATION'))
        self.stdout.write(self.style.SUCCESS('='*60))
        
        config_items = [
            ('Account', f'{account.name} (ID: {account.pk})'),
            ('Balance', f'${account.current_balance_usd:.2f}'),
            ('Strategy Mode', options['strategy_mode']),
            ('Tick Interval', f'{options["tick_interval"]} seconds'),
            ('Max Position', f'{options["max_position_size"]}%'),
            ('Stop Loss', f'{options["stop_loss"]}%'),
            ('Take Profit', f'{options["take_profit"]}%'),
        ]
        
        for label, value in config_items:
            self.stdout.write(f'  {label:<15} : {value}')
        
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))