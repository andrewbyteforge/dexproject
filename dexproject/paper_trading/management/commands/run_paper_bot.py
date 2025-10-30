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
from django.conf import settings
from paper_trading.models import (
    PaperTradingAccount,
    PaperTradingSession,
    PaperStrategyConfiguration
)
from paper_trading.bot import EnhancedPaperTradingBot

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
        # EXECUTION MODE
        # ====================================================================
        parser.add_argument(
            '--background',
            action='store_true',
            help='Run bot in background using Celery (optional)'
        )
        
        parser.add_argument(
            '--session-name',
            type=str,
            default=None,
            help='Name for this trading session'
        )
        
        parser.add_argument(
            '--runtime-minutes',
            type=int,
            default=None,
            help='Runtime limit in minutes (only for background mode)'
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

        from paper_trading.bot import EnhancedPaperTradingBot
        
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
        # NOTE: Session will be created by the bot during initialization
        # ====================================================================
        session_name = options['session_name'] or f'Session_{timezone.now().strftime("%Y%m%d_%H%M%S")}'
        
        self.stdout.write(
            self.style.SUCCESS(
                f'📝 Bot will create session: {session_name}'
            )
        )
        
        # ====================================================================
        # RUN BOT (BACKGROUND OR DIRECT)
        # ====================================================================
        if options['background']:
            # Run via Celery in background
            try:
                from paper_trading.tasks import run_paper_trading_bot
                
                self.stdout.write(
                    self.style.WARNING(
                        '🚀 Starting bot in BACKGROUND mode using Celery...'
                    )
                )
                
                # Start the Celery task
                task = run_paper_trading_bot.delay(  # type: ignore[attr-defined]
                    account_name=account.name,
                    intel_level=options['intel'],
                    user_id=account.user.pk,  # Use .pk for Pylance compatibility
                    runtime_minutes=options['runtime_minutes']
                )
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ Bot started in background (Task ID: {task.id})'
                    )
                )
                self.stdout.write(
                    self.style.WARNING(
                        '\n💡 Check status with: python manage.py paper_status'
                    )
                )
                
            except ImportError:
                self.stdout.write(
                    self.style.ERROR(
                        '❌ Celery not available. Run in direct mode instead.'
                    )
                )
                return
            except Exception as e:
                logger.exception("Failed to start background bot")
                self.stdout.write(
                    self.style.ERROR(f'❌ Failed to start background bot: {e}')
                )
                return
        else:
            # Run directly in foreground
            bot = None  # Initialize to avoid 'possibly unbound' warning
            try:
                self.stdout.write(
                    self.style.WARNING(
                        '\n🚀 Starting bot in DIRECT mode (foreground)...'
                    )
                )
                self.stdout.write(
                    self.style.WARNING(
                        '   Press Ctrl+C to stop the bot gracefully\n'
                    )
                )
                
                # Initialize the bot with correct parameters
                bot = EnhancedPaperTradingBot(
                    account_name=account.name,
                    intel_level=options['intel'],
                    use_real_prices=True,
                    chain_id=settings.PAPER_TRADING['DEFAULTS']['DEFAULT_CHAIN_ID']  # ← NEW
                )
                
                # Set tick interval if overridden
                if options['override_tick_interval']:
                    bot.tick_interval = options['override_tick_interval']
                
                # Initialize the bot (this will load account and create session)
                if not bot.initialize():
                    self.stdout.write(self.style.ERROR('❌ Bot initialization failed'))
                    return
                
                # Get the session that bot created
                session = bot.session
                
                # Run the bot (this blocks until stopped)
                bot.run()
                
                # Get final session state
                session = bot.session
                account = bot.account
                
                # Update session when done
                if session and account:
                    session.status = 'STOPPED'
                    session.stopped_at = timezone.now()
                    
                    # Store ending balance in metadata
                    if session.metadata and 'ending_balance_usd' not in session.metadata:
                        session.metadata['ending_balance_usd'] = float(account.current_balance_usd)
                    
                    # Calculate session P&L
                    starting_balance = Decimal(str(session.metadata.get('starting_balance_usd', 0)))
                    session_pnl = account.current_balance_usd - starting_balance
                    if session.metadata:
                        session.metadata['session_pnl_usd'] = float(session_pnl)
                    
                    session.save(update_fields=['status', 'stopped_at', 'metadata'])
                
                # Display final stats
                if session and account:
                    # Calculate session P&L
                    starting_balance = Decimal(str(session.metadata.get('starting_balance_usd', 0)))
                    session_pnl = account.current_balance_usd - starting_balance
                    
                    # Get duration safely
                    duration = getattr(session, 'duration_seconds', None)
                    duration_display = f"{duration}s" if duration else "N/A"
                    
                    self.stdout.write('\n' + '=' * 60)
                    self.stdout.write(
                        self.style.SUCCESS('✅ BOT STOPPED SUCCESSFULLY')
                    )
                    self.stdout.write('=' * 60)
                    self.stdout.write(f"  Session Duration : {duration_display}")
                    self.stdout.write(f"  Total Trades     : {session.total_trades}")
                    self.stdout.write(f"  Successful       : {session.successful_trades}")
                    self.stdout.write(f"  Failed           : {session.failed_trades}")
                    self.stdout.write(
                        f"  Session P&L      : ${session_pnl:,.2f}"
                    )
                    self.stdout.write(
                        f"  Final Balance    : ${account.current_balance_usd:,.2f}"
                    )
                    self.stdout.write('=' * 60 + '\n')
                
            except KeyboardInterrupt:
                self.stdout.write('\n')
                self.stdout.write(
                    self.style.WARNING('⏸️  Bot interrupted by user...')
                )
                
                # Get session and account from bot if bot exists
                session = None
                account = None
                if bot and hasattr(bot, 'session'):
                    session = bot.session
                if bot and hasattr(bot, 'account'):
                    account = bot.account
                
                # Update session status on interrupt
                if session and account:
                    session.status = 'STOPPED'
                    session.stopped_at = timezone.now()
                    
                    # Store ending balance in metadata
                    if session.metadata:
                        session.metadata['ending_balance_usd'] = float(account.current_balance_usd)
                        
                        # Calculate session P&L
                        starting_balance = Decimal(str(session.metadata.get('starting_balance_usd', 0)))
                        session_pnl = account.current_balance_usd - starting_balance
                        session.metadata['session_pnl_usd'] = float(session_pnl)
                    
                    session.save(update_fields=['status', 'stopped_at', 'metadata'])
                    
                self.stdout.write(
                    self.style.SUCCESS('✅ Bot stopped gracefully')
                )
                
            except Exception as e:
                logger.exception("Bot execution failed")
                self.stdout.write(
                    self.style.ERROR(f'❌ Bot error: {e}')
                )
                
                # Update session status on error
                session = None
                if bot and hasattr(bot, 'session'):
                    session = bot.session
                    
                if session:
                    session.status = 'ERROR'
                    session.error_message = str(e)
                    session.stopped_at = timezone.now()
                    session.save(update_fields=['status', 'error_message', 'stopped_at'])
    
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
    
    def _get_or_create_account(self, options: dict) -> PaperTradingAccount | None:
        """
        Get existing account or create a new one.
        
        FIXED: Always uses a single account for demo_user to prevent multiple accounts.
        
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
                # Get or create demo_user
                user, _ = User.objects.get_or_create(
                    username='demo_user',
                    defaults={
                        'email': 'demo@papertrading.ai',
                        'first_name': 'Demo',
                        'last_name': 'User'
                    }
                )
                
                if options['create_account']:
                    # Force create new account (only if user explicitly requested)
                    account = PaperTradingAccount.objects.create(
                        user=user,
                        name='My_Trading_Account',  # Fixed name
                        initial_balance_usd=Decimal(str(options['initial_balance'])),
                        current_balance_usd=Decimal(str(options['initial_balance']))
                    )
                    action = 'Created'
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✅ Created new account: {account.name}'
                        )
                    )
                else:
                    # FIXED: Use utility function to get single account
                    from paper_trading.utils import get_single_trading_account
                    
                    try:
                        account = get_single_trading_account()
                        action = 'Using existing'
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'✅ Using single account: {account.name} '
                                f'(ID: {account.account_id})'
                            )
                        )
                    except Exception as e:
                        logger.error(f"Failed to get single trading account: {e}")
                        self.stdout.write(
                            self.style.ERROR(
                                f'❌ Failed to get account: {e}'
                            )
                        )
                        return None
            
            # ================================================================
            # HANDLE RESET (NOTE: This is at the same level as the if/else above!)
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
        
        # Show execution mode
        if options['background']:
            self.stdout.write('  EXECUTION MODE  : Background (Celery)')
            if options['runtime_minutes']:
                self.stdout.write(f'  RUNTIME LIMIT   : {options["runtime_minutes"]} minutes')
        else:
            self.stdout.write('  EXECUTION MODE  : Direct (Foreground)')
        
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