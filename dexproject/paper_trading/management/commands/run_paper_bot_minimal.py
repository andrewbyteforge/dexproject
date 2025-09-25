"""
Minimal working version of run_paper_bot command.

File: paper_trading/management/commands/run_paper_bot_minimal.py
"""

import logging
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from paper_trading.models import PaperTradingAccount
from paper_trading.bot.simple_trader import EnhancedPaperTradingBot

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run the paper trading bot (minimal version)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--tick-interval',
            type=int,
            default=5,
            help='Seconds between market ticks'
        )
    
    def handle(self, *args, **options):
        self.stdout.write('🚀 Starting Paper Trading Bot (Minimal)...')
        
        try:
            # Get or create account
            user, _ = User.objects.get_or_create(
                username='paper_trader',
                defaults={'email': 'paper@trading.bot'}
            )
            
            account, created = PaperTradingAccount.objects.get_or_create(
                user=user,
                name='Default_AI_Bot',
                defaults={
                    'initial_balance_usd': Decimal('10000'),
                    'current_balance_usd': Decimal('10000')
                }
            )
            
            if created:
                self.stdout.write(f'✅ Created account: {account.name}')
            else:
                self.stdout.write(f'✅ Using account: {account.name}')
            
            self.stdout.write(f'💰 Balance: ${account.current_balance_usd}')
            self.stdout.write(f'🔑 Account PK: {account.pk}')
            
            # Create and run bot
            bot = EnhancedPaperTradingBot(account_id=account.pk)
            bot.tick_interval = options['tick_interval']
            
            if not bot.initialize():
                self.stdout.write(self.style.ERROR('❌ Bot initialization failed'))
                return
            
            self.stdout.write(self.style.SUCCESS('✅ Bot initialized'))
            self.stdout.write('Press Ctrl+C to stop\n')
            
            bot.run()
            
        except KeyboardInterrupt:
            self.stdout.write('\n🛑 Shutting down...')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {e}'))
            logger.exception("Bot error")
