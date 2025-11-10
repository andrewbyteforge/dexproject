"""
Paper Trading Strategies Package - Phase 7B

This package contains user-facing automated trading strategies:
- DCA (Dollar Cost Averaging) - Recurring buys over time
- Grid Trading - Range-bound automated trading
- TWAP - Time-Weighted Average Price execution
- VWAP - Volume-Weighted Average Price execution
- Custom - User-defined rule-based strategies

These are different from intelligence/strategies which contains AI decision logic.

File: dexproject/paper_trading/strategies/__init__.py
Phase: 7B - Advanced Strategies
"""

from .base_strategy import BaseStrategy

# Import strategy type and status constants
from paper_trading.constants import (
    StrategyType,
    StrategyStatus,
    StrategyRunFields,
    StrategyOrderFields,
    validate_strategy_type,
    validate_strategy_status,
    is_strategy_active,
    is_strategy_terminal,
)


# Export all strategy components
__all__ = [
    # Base class
    'BaseStrategy',
    
    # Constants
    'StrategyType',
    'StrategyStatus',
    'StrategyRunFields',
    'StrategyOrderFields',
    
    # Validation functions
    'validate_strategy_type',
    'validate_strategy_status',
    'is_strategy_active',
    'is_strategy_terminal',
]