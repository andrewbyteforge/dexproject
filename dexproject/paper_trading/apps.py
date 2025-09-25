from django.apps import AppConfig


class PaperTradingConfig(AppConfig):
    """Paper Trading application configuration."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'paper_trading'
    verbose_name = 'Paper Trading Simulator'
    
    def ready(self):
        """Initialize app when Django starts."""
        # Import signal handlers if needed
        pass
