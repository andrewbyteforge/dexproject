"""
Smart Lane Strategy Package

Contains strategy components for position sizing and exit management.
These components take analysis results and convert them into actionable
trading strategies with risk management.

Path: engine/smart_lane/strategy/__init__.py
"""

import logging

logger = logging.getLogger(__name__)

# Import main strategy classes
from .position_sizing import PositionSizer, SizingCalculation, SizingMethod
from .exit_strategies import (
    ExitStrategyManager, ExitStrategy, ExitLevel, 
    ExitTrigger, ExitMethod
)

# Package version
__version__ = "1.0.0"

# Export main classes
__all__ = [
    # Position Sizing
    'PositionSizer',
    'SizingCalculation', 
    'SizingMethod',
    
    # Exit Strategies
    'ExitStrategyManager',
    'ExitStrategy',
    'ExitLevel',
    'ExitTrigger',
    'ExitMethod'
]

logger.info(f"Smart Lane strategy package initialized - version {__version__}")