#!/usr/bin/env python
"""
Paper Trading Bot Management Command with Intel Slider System

This management command runs the enhanced paper trading bot with
configurable intelligence levels (1-10) that control all aspects
of trading behavior.

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
    Django management command to run the enhanced paper trading bot
    with Intel Slider system for intelligent trading control.
    """
    
    help = 'Run the enhanced paper trading bot with Intel Slider (1-10) control'
    
    def add_arguments(self, parser):
        """Add command-line arguments."""
        
        # ====================================================================
        # ACCOUNT CONFIGURATION
        # ====================================================================
        parser.add_argument(
            '--account-id',
            type=int,
            default=None,
            help='Paper trading account ID to use (optional)'
        )
        
        parser.add_argument(
            '--create-account',
            action='store_true',
            help='Create a new paper trading account if needed'
        )
        
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset the account balance before starting'
        )
        
        # ====================================================================
        # INTEL SLIDER - THE MAIN CONTROL
        # ====================================================================
        parser.add_argument(
            '--intel',
            type=int,
            default=5,
            choices=range(1, 11),
            help=(
                'Intelligence Level (1-10): Controls all bot behavior\n'
                '  1-3: Ultra Cautious - Maximum safety, minimal risk\n'
                '  4-6: Balanced - Moderate risk/reward approach\n'
                '  7-9: Aggressive - High risk tolerance, competitive\n'
                '  10: Autonomous - ML-driven dynamic optimization'
            )
        )
        
        # ====================================================================
        # OPTIONAL OVERRIDES (normally controlled by Intel level)
        # ====================================================================
        parser.add_argument(
            '--override-tick-interval',
            type=int,
            default=None,
            help='Override tick interval in seconds (normally set by Intel level)'
        )
        
        parser.add_argument(
            '--initial-balance',
            type=float,
            default=10000.0,
            help='Initial account balance in USD (default: 10000)'
        )
        
        # ====================================================================
        # DISPLAY OPTIONS
        # ====================================================================
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )
        
        parser.add_argument(
            '--show-thoughts',
            action='store_true',
            help='Display AI thought process in console'
        )
    
    def handle(self, *args, **options):
        """Execute the command."""
        
        # ====================================================================
        # SETUP LOGGING
        # ====================================================================
        if options['verbose']:
            logging.getLogger('paper_trading').setLevel(logging.DEBUG)

        from paper_trading.bot.simple_trader import EnhancedPaperTradingBot
        
        # ====================================================================
        # DISPLAY BANNER
        # ====================================================================
        self._display_banner(options['intel'])
        
        # ====================================================================
        # GET OR CREATE ACCOUNT
        # ====================================================================
        account = self._get_or_create_account(options)
        if not account:
            self.stdout.write(self.style.ERROR('❌ Failed to get/create account'))
            return
        
        # ====================================================================
        # DISPLAY CONFIGURATION
        # ====================================================================
        self._display_configuration(account, options)
        
        # ====================================================================
        # CREATE AND RUN BOT
        # ====================================================================
        try:
            self.stdout.write(
                self.style.SUCCESS(
                    f'🤖 Initializing bot for account: {account.name}'
                )
            )
            
            # FIX: Pass account_id and intel_level as positional arguments
            # The EnhancedPaperTradingBot.__init__ expects:
            # def __init__(self, account_id: int, intel_level: int = 5):
            bot = EnhancedPaperTradingBot(
                account.pk,  # First positional argument
                options['intel']  # Second positional argument
            )
            
            # Override tick interval if specified
            if options['override_tick_interval']:
                bot.tick_interval = options['override_tick_interval']
                self.stdout.write(
                    self.style.WARNING(
                        f'⚠️  Overriding tick interval to {bot.tick_interval}s'
                    )
                )
            
            # Initialize the bot
            if not bot.initialize():
                self.stdout.write(self.style.ERROR('❌ Bot initialization failed'))
                return
            
            # Display final status
            self.stdout.write(self.style.SUCCESS('✅ Bot initialized successfully'))
            
            # Show AI thoughts in console if requested
            if options['show_thoughts']:
                self.stdout.write(
                    self.style.WARNING(
                        '👁️  AI thought process will be displayed in console'
                    )
                )
                bot.display_thoughts = True
            
            # Start bot
            self.stdout.write(
                self.style.NOTICE(
                    '\n🏃 Bot is running... Press Ctrl+C to stop\n'
                )
            )
            
            bot.run()
            
        except KeyboardInterrupt:
            self.stdout.write('\n\n🛑 Shutting down bot...')
            if 'bot' in locals():
                bot.cleanup()
            self.stdout.write(self.style.SUCCESS('✅ Bot stopped gracefully'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Bot error: {e}'))
            logger.exception("Bot crashed with exception")
    
    def _display_banner(self, intel_level: int):
        """Display the startup banner with Intel level visualization."""
        
        self.stdout.write('\n' + '╔' + '═' * 68 + '╗')
        self.stdout.write('║' + ' ' * 10 + 
                         'ENHANCED PAPER TRADING BOT - INTEL SLIDER SYSTEM' + 
                         ' ' * 9 + '║')
        self.stdout.write('╚' + '═' * 68 + '╝\n')
        
        # Intel level visualization
        level_names = {
            range(1, 4): ('🛡️', 'CAUTIOUS', 'Maximum safety, minimal trades'),
            range(4, 7): ('⚖️', 'BALANCED', 'Equal risk/reward consideration'),
            range(7, 10): ('🔥', 'AGGRESSIVE', 'High risk tolerance, competitive'),
            range(10, 11): ('🧠', 'AUTONOMOUS', 'ML-driven dynamic optimization')
        }
        
        for range_obj, (icon, name, desc) in level_names.items():
            if intel_level in range_obj:
                self.stdout.write(f'\nINTELLIGENCE LEVEL: {icon}  Level {intel_level}: {name} - {desc}')
                break
    
    def _get_or_create_account(self, options: dict) -> PaperTradingAccount:
        """
        Get existing account or create a new one.
        
        Args:
            options: Command options dictionary
            
        Returns:
            PaperTradingAccount instance or None if failed
        """
        try:
            # ================================================================
            # DETERMINE ACCOUNT
            # ================================================================
            if options['account_id']:
                # Use specific account ID
                account = PaperTradingAccount.objects.get(pk=options['account_id'])
                action = 'Using existing'
            else:
                # Create or get default account
                user, _ = User.objects.get_or_create(
                    username='demo_user',
                    defaults={
                        'email': 'demo@papertrading.ai',
                        'first_name': 'Demo',
                        'last_name': 'User'
                    }
                )
                
                # Account name based on Intel level
                intel_names = {
                    range(1, 4): 'Cautious',
                    range(4, 7): 'Balanced',
                    range(7, 10): 'Aggressive',
                    range(10, 11): 'Autonomous'
                }
                
                account_suffix = 'Bot'
                for range_obj, name in intel_names.items():
                    if options['intel'] in range_obj:
                        account_suffix = name
                        break
                
                account_name = f"Intel_Slider_{account_suffix}"
                
                if options['create_account']:
                    # Always create new account
                    account = PaperTradingAccount.objects.create(
                        user=user,
                        name=account_name,
                        initial_balance_usd=Decimal(str(options['initial_balance'])),
                        current_balance_usd=Decimal(str(options['initial_balance']))
                    )
                    action = 'Created'
                else:
                    # Get or create account
                    account, created = PaperTradingAccount.objects.get_or_create(
                        user=user,
                        name=account_name,
                        defaults={
                            'initial_balance_usd': Decimal(str(options['initial_balance'])),
                            'current_balance_usd': Decimal(str(options['initial_balance']))
                        }
                    )
                    action = 'Created' if created else 'Using existing'
            
            # ================================================================
            # HANDLE RESET
            # ================================================================
            if options['reset'] and account:
                account.current_balance_usd = account.initial_balance_usd
                account.save()
                self.stdout.write(
                    self.style.WARNING(
                        f'💰 Reset balance to ${account.current_balance_usd:,.2f}'
                    )
                )
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ {action} account: {account.name}')
            )
            
            return account
            
        except PaperTradingAccount.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f"❌ Account with ID {options['account_id']} not found"
                )
            )
            return None
        except Exception as e:
            logger.exception("Error getting/creating account")
            self.stdout.write(self.style.ERROR(f'❌ Account error: {e}'))
            return None
    
    def _display_configuration(self, account: PaperTradingAccount, options: dict):
        """
        Display the bot configuration.
        
        Args:
            account: The paper trading account
            options: Command options dictionary
        """
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write('📋 BOT CONFIGURATION')
        self.stdout.write('=' * 60)
        
        self.stdout.write(f'  Account         : {account.name} (ID: {account.account_id})')
        self.stdout.write(f'  User            : {account.user.username}')
        self.stdout.write(f'  Balance         : ${account.current_balance_usd:,.2f}')
        self.stdout.write('')
        self.stdout.write(f'  INTELLIGENCE    : Level {options["intel"]}/10')
        
        # Show what the Intel level controls
        intel_config = self._get_intel_configuration(options['intel'])
        self.stdout.write('  Controlled by Intel Level:')
        for key, value in intel_config.items():
            self.stdout.write(f'    • {key:18}: {value}')
        
        self.stdout.write('=' * 60)
    
    def _get_intel_configuration(self, intel_level: int) -> dict:
        """
        Get the configuration controlled by Intel level.
        
        Args:
            intel_level: Intelligence level (1-10)
            
        Returns:
            Dictionary of configuration parameters
        """
        # Risk tolerance: 10% at level 1, 100% at level 10
        risk_tolerance = 10 + (intel_level - 1) * 10
        
        # Max position size: 5% at level 1, 25% at level 10
        max_position = 5 + (intel_level - 1) * 2.22
        
        # Trade frequency
        if intel_level <= 3:
            trade_freq = "Very Low"
            decision_speed = "Very Slow (30s)"
        elif intel_level <= 6:
            trade_freq = "Moderate"
            decision_speed = "Moderate (15s)"
        elif intel_level <= 9:
            trade_freq = "High"
            decision_speed = "Fast (5s)"
        else:
            trade_freq = "Maximum"
            decision_speed = "Instant (1s)"
        
        # Gas strategy
        if intel_level <= 3:
            gas_strategy = "Ultra Safe"
        elif intel_level <= 6:
            gas_strategy = "Adaptive"
        elif intel_level <= 9:
            gas_strategy = "Competitive"
        else:
            gas_strategy = "Maximum Speed"
        
        return {
            'Risk Tolerance': f'{risk_tolerance}%',
            'Max Position Size': f'{max_position:.1f}%',
            'Trade Frequency': trade_freq,
            'Gas Strategy': gas_strategy,
            'MEV Protection': 'Always On',
            'Decision Speed': decision_speed
        }