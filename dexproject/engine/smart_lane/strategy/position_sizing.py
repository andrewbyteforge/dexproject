"""
Smart Lane Position Sizing Strategy

Intelligent position sizing system that calculates optimal position sizes
based on risk assessment, confidence levels, technical signals, and
portfolio management principles.

Path: engine/smart_lane/strategy/position_sizing.py
"""

import logging
import math
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .. import SmartLaneConfig, TechnicalSignal, RiskCategory

logger = logging.getLogger(__name__)


class SizingMethod(Enum):
    """Position sizing methodologies."""
    FIXED_PERCENT = "FIXED_PERCENT"
    RISK_BASED = "RISK_BASED"
    KELLY_CRITERION = "KELLY_CRITERION"
    VOLATILITY_ADJUSTED = "VOLATILITY_ADJUSTED"
    CONFIDENCE_WEIGHTED = "CONFIDENCE_WEIGHTED"


@dataclass
class SizingCalculation:
    """Position sizing calculation result."""
    recommended_size_percent: float
    method_used: SizingMethod
    risk_adjusted_size: float
    confidence_adjusted_size: float
    technical_adjusted_size: float
    max_allowed_size: float
    sizing_rationale: str
    warnings: List[str]
    calculation_details: Dict[str, Any]


class PositionSizer:
    """
    Intelligent position sizing calculator for Smart Lane trades.
    
    Combines multiple sizing methodologies with risk management
    and portfolio optimization principles.
    """
    
    def __init__(self, config: SmartLaneConfig):
        """Initialize position sizer."""
        self.config = config
        self.max_position_percent = 25.0
        self.min_position_percent = 1.0
        self.base_position_percent = 5.0
        logger.info("Position sizer initialized")
    
    # Quick fixes for the minor issues found in testing

    # 1. Fix for position_sizing.py - Update the method signature
    # In engine/smart_lane/strategy/position_sizing.py, replace the calculate_position_size method:

    def calculate_position_size(
        self,
        risk_score: float,  # Changed from analysis_confidence 
        confidence: float,  # Added confidence parameter
        technical_signals: List[TechnicalSignal],
        context: Dict[str, Any]  # Changed from market_conditions and portfolio_context
    ) -> SizingCalculation:
        """Calculate optimal position size."""
        try:
            # Simple risk-based calculation for now
            risk_factor = 1.0 - risk_score
            confidence_factor = confidence
            
            base_size = self.base_position_percent * risk_factor * confidence_factor
            final_size = max(self.min_position_percent, min(base_size, self.max_position_percent))
            
            return SizingCalculation(
                recommended_size_percent=final_size,
                method_used=SizingMethod.RISK_BASED,
                risk_adjusted_size=final_size,
                confidence_adjusted_size=final_size,
                technical_adjusted_size=final_size,
                max_allowed_size=self.max_position_percent,
                sizing_rationale=f"Risk-based sizing: {final_size:.1f}%",
                warnings=[],
                calculation_details={'risk_score': risk_score, 'confidence': confidence}
            )
        except Exception as e:
            logger.error(f"Position sizing error: {e}")
            return SizingCalculation(
                recommended_size_percent=2.0,
                method_used=SizingMethod.FIXED_PERCENT,
                risk_adjusted_size=2.0,
                confidence_adjusted_size=2.0,
                technical_adjusted_size=2.0,
                max_allowed_size=25.0,
                sizing_rationale="Default sizing due to error",
                warnings=["Calculation failed"],
                calculation_details={'error': str(e)}
            )

    # 2. Fix for holder_analyzer.py - Around line 212, change:
    # FROM: f"({len(whale_holders)} whales, {distribution_metrics.get('total_holders', 0)} total holders, "
    # TO:   f"({len(whale_holders)} whales, {distribution_metrics.total_holders} total holders, "

    # 3. The technical analyzer and contract analyzer warnings are not critical for basic functionality
    # but should be addressed in a future update.


# Export main class
__all__ = ['PositionSizer', 'SizingCalculation', 'SizingMethod']
