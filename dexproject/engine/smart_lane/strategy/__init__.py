"""
Smart Lane Strategy Package

Contains strategy components for position sizing and exit management.
These components take analysis results and convert them into actionable
trading strategies with risk management.

Path: engine/smart_lane/strategy/__init__.py
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SizingMethod(Enum):
    """Position sizing methodologies."""
    FIXED_PERCENT = "FIXED_PERCENT"
    RISK_BASED = "RISK_BASED"
    KELLY_CRITERION = "KELLY_CRITERION"
    VOLATILITY_ADJUSTED = "VOLATILITY_ADJUSTED"
    CONFIDENCE_WEIGHTED = "CONFIDENCE_WEIGHTED"


class ExitTrigger(Enum):
    """Types of exit triggers."""
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    TIME_BASED = "TIME_BASED"
    TECHNICAL_SIGNAL = "TECHNICAL_SIGNAL"
    RISK_THRESHOLD = "RISK_THRESHOLD"


class ExitMethod(Enum):
    """Exit execution methods."""
    MARKET_ORDER = "MARKET_ORDER"
    LIMIT_ORDER = "LIMIT_ORDER"
    SCALED_EXIT = "SCALED_EXIT"
    TRAILING_EXIT = "TRAILING_EXIT"


@dataclass
class StrategyMetrics:
    """Metrics for strategy performance tracking."""
    strategy_id: str
    expected_return: float
    risk_reward_ratio: float
    win_probability: float
    max_drawdown_percent: float
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None


# Import main strategy classes (will be created next)
# These imports will work once we create the files
try:
    from .position_sizing import (
        PositionSizer, 
        SizingCalculation
    )
    from .exit_strategies import (
        ExitStrategyManager, 
        ExitStrategy,
        ExitLevel
    )
    
    __all__ = [
        # Enums
        'SizingMethod',
        'ExitTrigger',
        'ExitMethod',
        
        # Data classes
        'StrategyMetrics',
        
        # Position Sizing
        'PositionSizer',
        'SizingCalculation',
        
        # Exit Strategies
        'ExitStrategyManager',
        'ExitStrategy',
        'ExitLevel'
    ]
    
    logger.info("Smart Lane strategy package initialized successfully")
    
except ImportError as e:
    logger.warning(f"Strategy components not yet available: {e}")
    __all__ = [
        'SizingMethod',
        'ExitTrigger', 
        'ExitMethod',
        'StrategyMetrics'
    ]

# Package version
__version__ = "1.0.0"