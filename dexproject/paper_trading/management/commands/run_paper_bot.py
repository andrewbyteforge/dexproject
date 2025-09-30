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
            
            # Create bot instance with Intel level
            bot = EnhancedPaperTradingBot(
                account_id=account.pk,
                intel_level=options['intel']
            )
            
            # Override tick interval if specified
            if options['override_tick_interval']:
                bot.tick_interval = options['override_tick_interval']
                self.stdout.write(
                    self.style.WARNING(
                        f'⚠️  Overriding tick interval to {bot.tick_interval}s'
                    )
                )
            
            # Initialize bot
            if not bot.initialize():
                self.stdout.write(self.style.ERROR('❌ Bot initialization failed'))
                return
            
            self.stdout.write(self.style.SUCCESS('✅ Bot initialized successfully'))
            self.stdout.write(
                self.style.WARNING('Press Ctrl+C to stop the bot gracefully\n')
            )
            
            # Run the bot
            bot.run()
            
            self.stdout.write(self.style.SUCCESS('\n✅ Bot stopped successfully'))
            
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\n🛑 Shutting down bot...'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Bot error: {e}'))
            logger.exception("Bot crashed with exception")
            sys.exit(1)
    
    def _display_banner(self, intel_level: int):
        """
        Display startup banner with Intel level information.
        
        Args:
            intel_level: Selected intelligence level
        """
        banner = """
╔══════════════════════════════════════════════════════════════════╗
║          ENHANCED PAPER TRADING BOT - INTEL SLIDER SYSTEM         ║
╚══════════════════════════════════════════════════════════════════╝
        """
        self.stdout.write(self.style.SUCCESS(banner))
        
        # Display Intel level description
        level_descriptions = {
            1: "🛡️  Level 1: ULTRA CAUTIOUS - Maximum safety, minimal trades",
            2: "🛡️  Level 2: VERY CAUTIOUS - High safety, rare opportunities",
            3: "🛡️  Level 3: CAUTIOUS - Conservative with careful risk management",
            4: "⚖️  Level 4: MODERATELY CAUTIOUS - Balanced, leaning safe",
            5: "⚖️  Level 5: BALANCED - Equal risk/reward consideration",
            6: "⚖️  Level 6: MODERATELY AGGRESSIVE - Seeking opportunities",
            7: "🚀 Level 7: AGGRESSIVE - Active trading, higher risks",
            8: "🚀 Level 8: VERY AGGRESSIVE - Competitive, fast execution",
            9: "🚀 Level 9: ULTRA AGGRESSIVE - Maximum risk for profits",
            10: "🤖 Level 10: FULLY AUTONOMOUS - ML-driven optimization"
        }
        
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                f"INTELLIGENCE LEVEL: {level_descriptions[intel_level]}"
            )
        )
        self.stdout.write("")
    
    def _get_or_create_account(self, options):
        """
        Get existing account or create new one.
        
        Args:
            options: Command options
            
        Returns:
            PaperTradingAccount instance or None
        """
        try:
            # ================================================================
            # USE SPECIFIC ACCOUNT ID IF PROVIDED
            # ================================================================
            if options['account_id']:
                return PaperTradingAccount.objects.get(pk=options['account_id'])
            
            # ================================================================
            # GET OR CREATE DEFAULT ACCOUNT
            # ================================================================
            # Use consistent user for dashboard compatibility
            user, user_created = User.objects.get_or_create(
                username='demo_user',
                defaults={
                    'email': 'demo@papertrading.bot',
                    'first_name': 'Demo',
                    'last_name': 'Trader'
                }
            )
            
            if user_created:
                self.stdout.write(f'✅ Created user: {user.username}')
            
            # Get or create account
            account, account_created = PaperTradingAccount.objects.get_or_create(
                user=user,
                name='Intel_Slider_Bot',
                defaults={
                    'initial_balance_usd': Decimal(str(options['initial_balance'])),
                    'current_balance_usd': Decimal(str(options['initial_balance']))
                }
            )
            
            if account_created:
                self.stdout.write(f'✅ Created account: {account.name}')
            else:
                self.stdout.write(f'✅ Using existing account: {account.name}')
            
            # ================================================================
            # RESET BALANCE IF REQUESTED
            # ================================================================
            if options['reset']:
                account.current_balance_usd = account.initial_balance_usd
                account.save()
                self.stdout.write('♻️  Account balance reset')
            
            return account
            
        except PaperTradingAccount.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f"❌ Account with ID {options['account_id']} not found"
                )
            )
            return None
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error getting account: {e}'))
            return None
    
    def _display_configuration(self, account, options):
        """
        Display bot configuration summary.
        
        Args:
            account: PaperTradingAccount instance
            options: Command options
        """
        # ====================================================================
        # CONFIGURATION DISPLAY
        # ====================================================================
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("📋 BOT CONFIGURATION")
        self.stdout.write("=" * 60)
        
        # Account info
        self.stdout.write(f"  Account         : {account.name} (ID: {account.account_id})")
        self.stdout.write(f"  User            : {account.user.username}")
        self.stdout.write(f"  Balance         : ${account.current_balance_usd:,.2f}")
        
        # Intelligence configuration
        intel_level = options['intel']
        self.stdout.write(f"\n  INTELLIGENCE    : Level {intel_level}/10")
        
        # Display what this Intel level controls
        self.stdout.write("  Controlled by Intel Level:")
        
        # Risk tolerance
        risk_tolerances = {
            1: "20%", 2: "25%", 3: "30%", 4: "40%", 5: "50%",
            6: "60%", 7: "70%", 8: "80%", 9: "90%", 10: "Dynamic"
        }
        self.stdout.write(f"    • Risk Tolerance    : {risk_tolerances[intel_level]}")
        
        # Max position size
        position_sizes = {
            1: "2%", 2: "3%", 3: "5%", 4: "7%", 5: "10%",
            6: "12%", 7: "15%", 8: "20%", 9: "25%", 10: "Dynamic"
        }
        self.stdout.write(f"    • Max Position Size : {position_sizes[intel_level]}")
        
        # Trading frequency
        frequencies = {
            1: "Very Low", 2: "Low", 3: "Low", 4: "Moderate", 5: "Moderate",
            6: "Moderate-High", 7: "High", 8: "High", 9: "Very High", 10: "Optimal"
        }
        self.stdout.write(f"    • Trade Frequency   : {frequencies[intel_level]}")
        
        # Gas strategy
        gas_strategies = {
            1: "Minimal", 2: "Low", 3: "Standard", 4: "Standard", 5: "Adaptive",
            6: "Adaptive", 7: "Aggressive", 8: "Aggressive", 
            9: "Ultra Aggressive", 10: "Dynamic"
        }
        self.stdout.write(f"    • Gas Strategy      : {gas_strategies[intel_level]}")
        
        # MEV Protection
        mev_protection = {
            1: "Always On", 2: "Always On", 3: "Always On", 4: "Always On", 
            5: "Always On", 6: "When Needed", 7: "Rarely", 8: "Rarely", 
            9: "Never", 10: "Dynamic"
        }
        self.stdout.write(f"    • MEV Protection    : {mev_protection[intel_level]}")
        
        # Decision speed
        decision_speeds = {
            1: "Slow (30s)", 2: "Slow (30s)", 3: "Moderate (30s)",
            4: "Moderate (15s)", 5: "Moderate (15s)", 6: "Fast (15s)",
            7: "Fast (5s)", 8: "Very Fast (5s)", 9: "Ultra Fast (5s)",
            10: "Optimal (3s)"
        }
        self.stdout.write(f"    • Decision Speed    : {decision_speeds[intel_level]}")
        
        self.stdout.write("=" * 60)
        self.stdout.write("")