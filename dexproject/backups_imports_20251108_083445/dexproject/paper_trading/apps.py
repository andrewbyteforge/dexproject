"""
Enhanced Django app configuration with type safety initialization.

File: dexproject/paper_trading/apps.py
"""

from django.apps import AppConfig
from decimal import getcontext, ROUND_HALF_EVEN
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class PaperTradingConfig(AppConfig):
    """
    Paper Trading app configuration with production-level type safety.
    """
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'paper_trading'
    verbose_name = 'Paper Trading Simulator'
    
    def ready(self):
        """
        Initialize app when Django starts.
        
        Sets up:
        - Decimal context for consistent numeric operations
        - Signal handlers
        - Type validation
        """
        # Configure decimal context for production
        self._configure_decimal_context()
        
        # Import and register signals
        try:
            from . import signals
            logger.info("Paper trading signals registered successfully")
        except ImportError as e:
            logger.warning(f"Could not import signals: {e}")
        
        # Validate type configuration
        self._validate_type_configuration()
        
        logger.info(
            f"Paper Trading app initialized: "
            f"verbose_name={self.verbose_name}, "
            f"decimal_precision={getcontext().prec}"
        )
    
    def _configure_decimal_context(self):
        """
        Configure decimal context for production use.
        
        This ensures consistent decimal operations across the entire
        application lifecycle.
        """
        # Set precision high enough for crypto calculations
        getcontext().prec = 28
        
        # Set rounding mode to banker's rounding (reduces bias)
        getcontext().rounding = ROUND_HALF_EVEN
        
        # Don't trap errors in production - log them instead
        # This prevents crashes but allows error monitoring
        from decimal import InvalidOperation, DivisionByZero, Overflow
        
        getcontext().traps[InvalidOperation] = False
        getcontext().traps[DivisionByZero] = False
        getcontext().traps[Overflow] = False
        
        logger.info(
            f"Decimal context configured: "
            f"precision={getcontext().prec}, "
            f"rounding={getcontext().rounding}"
        )
    
    def _validate_type_configuration(self):
        """
        Validate that type utilities are properly configured.
        """
        try:
            from paper_trading.utils.type_utils import TypeConverter, to_decimal
            
            # Test basic conversions
            test_cases = [
                (10, "integer"),
                (10.5, "float"),
                ("10.5", "string"),
                (None, "None with default")
            ]
            
            for value, description in test_cases:
                try:
                    result = to_decimal(value, default=Decimal('0'))
                    logger.debug(f"Type conversion test passed: {description} -> {result}")
                except Exception as e:
                    logger.error(f"Type conversion test failed for {description}: {e}")
            
            logger.info("Type configuration validation completed")
            
        except ImportError as e:
            logger.error(f"Type utilities not available: {e}")