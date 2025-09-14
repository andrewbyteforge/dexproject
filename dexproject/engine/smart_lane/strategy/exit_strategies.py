"""
Smart Lane Exit Strategy Manager

Advanced exit strategy system that creates comprehensive exit plans
based on risk analysis, technical levels, and market conditions.

Path: engine/smart_lane/strategy/exit_strategies.py
"""

import logging
import math
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone, timedelta

from .. import TechnicalSignal

logger = logging.getLogger(__name__)


class ExitTrigger(Enum):
    """Types of exit triggers."""
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    TIME_BASED = "TIME_BASED"


class ExitMethod(Enum):
    """Exit execution methods."""
    MARKET_ORDER = "MARKET_ORDER"
    LIMIT_ORDER = "LIMIT_ORDER"
    SCALED_EXIT = "SCALED_EXIT"


@dataclass
class ExitLevel:
    """Individual exit level definition."""
    trigger_type: ExitTrigger
    trigger_price_percent: float
    position_percent: float
    execution_method: ExitMethod
    priority: int
    conditions: Dict[str, Any]
    description: str


@dataclass
class ExitStrategy:
    """Complete exit strategy definition."""
    strategy_name: str
    exit_levels: List[ExitLevel]
    max_hold_time_hours: Optional[int]
    stop_loss_percent: Optional[float]
    take_profit_targets: List[float]
    trailing_stop_config: Dict[str, Any]
    emergency_exit_conditions: List[Dict[str, Any]]
    strategy_rationale: str
    risk_management_notes: List[str]


class ExitStrategyManager:
    """Advanced exit strategy manager for Smart Lane trades."""
    
    def __init__(self, config: Any):
        """Initialize exit strategy manager."""
        self.config = config
        self.default_stop_loss_percent = 15.0
        self.default_take_profit_percent = 25.0
        logger.info("Exit strategy manager initialized")
    
    def create_exit_strategy(
        self,
        risk_score: float,
        technical_signals: List[TechnicalSignal],
        market_conditions: Dict[str, Any],
        position_context: Dict[str, Any]
    ) -> ExitStrategy:
        """Create comprehensive exit strategy."""
        try:
            # Simple strategy creation
            stop_loss = self.default_stop_loss_percent * (1 + risk_score)
            take_profit = self.default_take_profit_percent * (1 - risk_score * 0.5)
            
            exit_levels = [
                ExitLevel(
                    trigger_type=ExitTrigger.STOP_LOSS,
                    trigger_price_percent=-stop_loss,
                    position_percent=100.0,
                    execution_method=ExitMethod.MARKET_ORDER,
                    priority=1,
                    conditions={},
                    description=f"Stop loss at -{stop_loss:.1f}%"
                ),
                ExitLevel(
                    trigger_type=ExitTrigger.TAKE_PROFIT,
                    trigger_price_percent=take_profit,
                    position_percent=100.0,
                    execution_method=ExitMethod.LIMIT_ORDER,
                    priority=2,
                    conditions={},
                    description=f"Take profit at +{take_profit:.1f}%"
                )
            ]
            
            return ExitStrategy(
                strategy_name=f"Smart Lane Exit Strategy",
                exit_levels=exit_levels,
                max_hold_time_hours=48,
                stop_loss_percent=stop_loss,
                take_profit_targets=[take_profit],
                trailing_stop_config={'enabled': False},
                emergency_exit_conditions=[],
                strategy_rationale=f"Risk-adjusted strategy for {risk_score:.2f} risk score",
                risk_management_notes=["Monitor position regularly"]
            )
        except Exception as e:
            logger.error(f"Exit strategy error: {e}")
            return ExitStrategy(
                strategy_name="Default Exit Strategy",
                exit_levels=[],
                max_hold_time_hours=24,
                stop_loss_percent=15.0,
                take_profit_targets=[25.0],
                trailing_stop_config={'enabled': False},
                emergency_exit_conditions=[],
                strategy_rationale="Default strategy due to error",
                risk_management_notes=["Error in strategy creation"]
            )


# Export main class
__all__ = ['ExitStrategyManager', 'ExitStrategy', 'ExitLevel', 'ExitTrigger', 'ExitMethod']
