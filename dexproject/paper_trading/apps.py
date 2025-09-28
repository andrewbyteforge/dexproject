"""
Paper Trading Application Configuration

Configures the Paper Trading app and imports signal handlers
to enable real-time WebSocket updates.

File: dexproject/paper_trading/apps.py
"""

import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class PaperTradingConfig(AppConfig):
    """Paper Trading application configuration."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'paper_trading'
    verbose_name = 'Paper Trading Simulator'
    
    def ready(self) -> None:
        """
        Initialize app when Django starts.
        
        This method is called once Django has fully loaded all models
        and is ready to start processing requests. We use it to:
        1. Import signal handlers for WebSocket broadcasting
        2. Perform any other initialization needed
        """
        try:
            # Import signal handlers to register them
            # This must be done here to avoid circular imports
            # and ensure signals are registered before the app starts
            from . import signals
            
            logger.info("Paper trading signals registered successfully")
            
            # Log app initialization
            logger.info(
                f"Paper Trading app initialized: "
                f"verbose_name={self.verbose_name}, "
                f"signals=enabled, websocket=enabled"
            )
            
        except ImportError as e:
            logger.error(f"Failed to import paper trading signals: {e}", exc_info=True)
            # Re-raise to prevent app from starting with missing signals
            raise
        
        except Exception as e:
            logger.error(f"Error in paper trading app ready(): {e}", exc_info=True)
            # Re-raise to prevent app from starting with initialization errors
            raise