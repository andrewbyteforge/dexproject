from django.core.management.base import BaseCommand
from paper_trading.bot.trade_executor import TradeExecutor

class Command(BaseCommand):
    help = 'Reset circuit breaker to allow trading to resume'

    def handle(self, *args, **options):
        # This is a hack since we can't access the running bot instance
        # You'll need to restart the bot for this to take effect
        self.stdout.write(
            self.style.WARNING(
                'To reset circuit breaker, you need to restart the bot.\n'
                'The circuit breaker will automatically reset on bot restart.'
            )
        )