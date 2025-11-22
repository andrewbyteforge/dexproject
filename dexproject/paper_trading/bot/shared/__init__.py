"""
Shared Utilities Module

This module contains shared utilities used across the bot.
"""

from paper_trading.bot.shared.price_service_integration import (
    RealPriceManager,
    create_price_manager
)
from paper_trading.bot.shared.validation import (
    ValidationLimits,
    is_valid_decimal,
    validate_usd_amount,
    validate_balance_update,
    decimal_to_str,
    get_token_address_for_trade
)

# Try to import optional components
try:
    from paper_trading.bot.shared.metrics_logger import MetricsLogger
except ImportError:
    MetricsLogger = None

__all__ = [
    'RealPriceManager',
    'create_price_manager',
    'ValidationLimits',
    'is_valid_decimal',
    'validate_usd_amount',
    'validate_balance_update',
    'decimal_to_str',
    'get_token_address_for_trade',
]

# Add MetricsLogger to exports if available
if MetricsLogger is not None:
    __all__.append('MetricsLogger')