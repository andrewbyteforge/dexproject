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
    FIXED_PERCENT = "FIXED_PERCENT"          # Fixed percentage of portfolio
    RISK_BASED = "RISK_BASED"                # Based on risk per trade
    KELLY_CRITERION = "KELLY_CRITERION"      # Kelly criterion optimization
    VOLATILITY_ADJUSTED = "VOLATILITY_ADJUSTED"  # Adjusted for volatility
    CONFIDENCE_WEIGHTED = "CONFIDENCE_WEIGHTED"   # Weighted by analysis confidence


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
        """
        Initialize position sizer.
        
        Args:
            config: Smart Lane configuration object
        """
        self.config = config
        
        # Position sizing parameters
        self.max_position_percent = 25.0  # Maximum 25% of portfolio per trade
        self.min_position_percent = 1.0   # Minimum 1% position size
        self.base_position_percent = 5.0  # Base position size
        
        # Risk management parameters
        self.max_risk_per_trade = 2.0     # Maximum 2% portfolio risk per trade
        self.max_total_risk = 10.0        # Maximum 10% total portfolio risk
        self.correlation_limit = 0.7      # Maximum correlation between positions
        
        # Kelly Criterion parameters
        self.kelly_fraction = 0.25        # Use 25% of Kelly recommendation
        self.min_win_rate = 0.35          # Minimum win rate for Kelly
        self.min_avg_return = 0.05        # Minimum 5% average return
        
        # Volatility parameters
        self.volatility_lookback = 30     # Days for volatility calculation
        self.max_volatility = 0.50       # Maximum acceptable volatility
        self.volatility_adjustment = 2.0  # Volatility adjustment factor
        
        # Confidence parameters
        self.min_confidence = 0.3         # Minimum confidence for full size
        self.confidence_threshold = 0.7   # Threshold for increased size
        
        logger.info("Position sizer initialized with portfolio risk management")
    
    def calculate_position_size(
        self,
        analysis_confidence: float,
        overall_risk_score: float,
        technical_signals: List[TechnicalSignal],
        market_conditions: Dict[str, Any],
        portfolio_context: Dict[str, Any]
    ) -> SizingCalculation:
        """
        Calculate optimal position size based on multiple factors.
        
        Args:
            analysis_confidence: Confidence in analysis (0-1)
            overall_risk_score: Overall risk assessment (0-1)
            technical_signals: Technical analysis signals
            market_conditions: Current market conditions
            portfolio_context: Current portfolio state
            
        Returns:
            Complete position sizing calculation with rationale
        """
        try:
            logger.debug("Calculating position size...")
            
            # Input validation
            analysis_confidence = max(0.0, min(1.0, analysis_confidence))
            overall_risk_score = max(0.0, min(1.0, overall_risk_score))
            
            # Calculate using different methods
            risk_based_size = self._calculate_risk_based_size(
                overall_risk_score, market_conditions, portfolio_context
            )
            
            confidence_weighted_size = self._calculate_confidence_weighted_size(
                analysis_confidence, risk_based_size
            )
            
            technical_adjusted_size = self._calculate_technical_adjusted_size(
                confidence_weighted_size, technical_signals
            )
            
            volatility_adjusted_size = self._calculate_volatility_adjusted_size(
                technical_adjusted_size, market_conditions
            )
            
            # Apply portfolio constraints
            portfolio_constrained_size = self._apply_portfolio_constraints(
                volatility_adjusted_size, portfolio_context
            )
            
            # Determine final size and method
            final_size, method_used = self._select_final_size(
                risk_based_size, confidence_weighted_size, 
                technical_adjusted_size, volatility_adjusted_size, 
                portfolio_constrained_size
            )
            
            # Generate sizing rationale
            rationale = self._generate_sizing_rationale(
                final_size, method_used, analysis_confidence, 
                overall_risk_score, market_conditions
            )
            
            # Generate warnings
            warnings = self._generate_sizing_warnings(
                final_size, overall_risk_score, analysis_confidence, 
                market_conditions, portfolio_context
            )
            
            # Create calculation details
            calculation_details = {
                'risk_based_size': risk_based_size,
                'confidence_weighted_size': confidence_weighted_size,
                'technical_adjusted_size': technical_adjusted_size,
                'volatility_adjusted_size': volatility_adjusted_size,
                'portfolio_constrained_size': portfolio_constrained_size,
                'analysis_confidence': analysis_confidence,
                'overall_risk_score': overall_risk_score,
                'market_volatility': market_conditions.get('volatility', 0.1),
                'portfolio_utilization': portfolio_context.get('position_count', 0)
            }
            
            return SizingCalculation(
                recommended_size_percent=final_size,
                method_used=method_used,
                risk_adjusted_size=risk_based_size,
                confidence_adjusted_size=confidence_weighted_size,
                technical_adjusted_size=technical_adjusted_size,
                max_allowed_size=self.max_position_percent,
                sizing_rationale=rationale,
                warnings=warnings,
                calculation_details=calculation_details
            )
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}", exc_info=True)
            return self._create_default_sizing(overall_risk_score)
    
    def _calculate_risk_based_size(
        self,
        risk_score: float,
        market_conditions: Dict[str, Any],
        portfolio_context: Dict[str, Any]
    ) -> float:
        """Calculate position size based on risk assessment."""
        # Base size inversely related to risk
        risk_factor = 1.0 - risk_score
        base_size = self.base_position_percent * risk_factor
        
        # Adjust for stop loss distance
        stop_loss_percent = market_conditions.get('expected_stop_loss', 15.0)
        
        # Calculate size to risk maximum per trade
        max_size_for_risk = (self.max_risk_per_trade / stop_loss_percent) * 100
        
        # Use smaller of calculated sizes
        risk_based_size = min(base_size, max_size_for_risk)
        
        # Ensure within bounds
        return max(self.min_position_percent, min(risk_based_size, self.max_position_percent))
    
    def _calculate_confidence_weighted_size(
        self,
        confidence: float,
        base_size: float
    ) -> float:
        """Adjust size based on analysis confidence."""
        if confidence < self.min_confidence:
            # Very low confidence - minimal size
            multiplier = 0.5
        elif confidence < 0.5:
            # Low confidence - reduced size
            multiplier = 0.7
        elif confidence > self.confidence_threshold:
            # High confidence - increased size
            multiplier = 1.3
        else:
            # Medium confidence - base size
            multiplier = 1.0
        
        adjusted_size = base_size * multiplier
        return max(self.min_position_percent, min(adjusted_size, self.max_position_percent))
    
    def _calculate_technical_adjusted_size(
        self,
        base_size: float,
        technical_signals: List[TechnicalSignal]
    ) -> float:
        """Adjust size based on technical signal strength."""
        if not technical_signals:
            return base_size
        
        # Calculate signal consensus
        buy_signals = len([s for s in technical_signals if s.signal == 'BUY'])
        sell_signals = len([s for s in technical_signals if s.signal == 'SELL'])
        total_signals = len(technical_signals)
        
        if total_signals == 0:
            signal_strength = 0.5  # Neutral
        else:
            signal_strength = buy_signals / total_signals
        
        # Calculate average signal strength
        avg_strength = sum(s.strength for s in technical_signals) / len(technical_signals)
        
        # Combine consensus and strength
        technical_factor = (signal_strength * 0.6) + (avg_strength * 0.4)
        
        # Apply technical adjustment
        if technical_factor > 0.7:
            # Strong bullish signals
            multiplier = 1.2
        elif technical_factor < 0.3:
            # Strong bearish signals
            multiplier = 0.6
        else:
            # Mixed or neutral signals
            multiplier = 1.0
        
        adjusted_size = base_size * multiplier
        return max(self.min_position_percent, min(adjusted_size, self.max_position_percent))
    
    def _calculate_volatility_adjusted_size(
        self,
        base_size: float,
        market_conditions: Dict[str, Any]
    ) -> float:
        """Adjust size based on market volatility."""
        volatility = market_conditions.get('volatility', 0.1)
        
        # Adjust size inversely to volatility
        if volatility > self.max_volatility:
            # Very high volatility - significant reduction
            multiplier = 0.5
        elif volatility > 0.3:
            # High volatility - moderate reduction
            multiplier = 0.7
        elif volatility < 0.05:
            # Very low volatility - slight increase
            multiplier = 1.1
        else:
            # Normal volatility - no adjustment
            multiplier = 1.0
        
        adjusted_size = base_size * multiplier
        return max(self.min_position_percent, min(adjusted_size, self.max_position_percent))
    
    def _apply_portfolio_constraints(
        self,
        base_size: float,
        portfolio_context: Dict[str, Any]
    ) -> float:
        """Apply portfolio-level position size constraints."""
        # Check total portfolio utilization
        current_positions = portfolio_context.get('position_count', 0)
        max_positions = 10  # Maximum 10 positions
        
        if current_positions >= max_positions:
            # Portfolio full - minimal new positions
            return self.min_position_percent
        
        # Check available capital
        available_capital_percent = portfolio_context.get('available_capital_percent', 100.0)
        
        if available_capital_percent < base_size:
            # Insufficient capital - use what's available
            return max(self.min_position_percent, available_capital_percent * 0.8)
        
        # Check risk budget
        current_risk_percent = portfolio_context.get('total_risk_percent', 0.0)
        position_risk = base_size * 0.15  # Assume 15% position risk
        
        if current_risk_percent + position_risk > self.max_total_risk:
            # Risk budget exceeded - reduce size
            available_risk = self.max_total_risk - current_risk_percent
            max_size_for_risk = available_risk / 0.15
            return max(self.min_position_percent, min(base_size, max_size_for_risk))
        
        return base_size
    
    def _select_final_size(
        self,
        risk_based: float,
        confidence_weighted: float,
        technical_adjusted: float,
        volatility_adjusted: float,
        portfolio_constrained: float
    ) -> Tuple[float, SizingMethod]:
        """Select final position size from calculated options."""
        sizes = {
            SizingMethod.RISK_BASED: risk_based,
            SizingMethod.CONFIDENCE_WEIGHTED: confidence_weighted,
            SizingMethod.VOLATILITY_ADJUSTED: volatility_adjusted,
            SizingMethod.FIXED_PERCENT: portfolio_constrained
        }
        
        # Use the most conservative (smallest) size for safety
        min_size = min(sizes.values())
        selected_method = min(sizes, key=sizes.get)
        
        # Ensure within absolute bounds
        final_size = max(self.min_position_percent, min(min_size, self.max_position_percent))
        
        return final_size, selected_method
    
    def _calculate_kelly_criterion_size(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> float:
        """Calculate Kelly Criterion position size."""
        if win_rate < self.min_win_rate or avg_win < self.min_avg_return:
            return self.min_position_percent
        
        # Kelly formula: f = (bp - q) / b
        # where b = odds received (avg_win/avg_loss), p = win rate, q = loss rate
        b = avg_win / avg_loss if avg_loss > 0 else 2.0
        p = win_rate
        q = 1 - win_rate
        
        kelly_fraction = (b * p - q) / b
        
        # Apply conservative fraction
        kelly_size = kelly_fraction * self.kelly_fraction * 100
        
        return max(self.min_position_percent, min(kelly_size, self.max_position_percent))
    
    def _generate_sizing_rationale(
        self,
        final_size: float,
        method_used: SizingMethod,
        confidence: float,
        risk_score: float,
        market_conditions: Dict[str, Any]
    ) -> str:
        """Generate human-readable sizing rationale."""
        rationale_parts = []
        
        # Size category
        if final_size <= 2.0:
            rationale_parts.append("Minimal position size")
        elif final_size <= 5.0:
            rationale_parts.append("Conservative position size")
        elif final_size <= 10.0:
            rationale_parts.append("Standard position size")
        elif final_size <= 20.0:
            rationale_parts.append("Aggressive position size")
        else:
            rationale_parts.append("Maximum position size")
        
        # Method rationale
        if method_used == SizingMethod.RISK_BASED:
            rationale_parts.append("determined by risk assessment")
        elif method_used == SizingMethod.CONFIDENCE_WEIGHTED:
            rationale_parts.append("adjusted for analysis confidence")
        elif method_used == SizingMethod.VOLATILITY_ADJUSTED:
            rationale_parts.append("reduced due to market volatility")
        else:
            rationale_parts.append("constrained by portfolio limits")
        
        # Risk factors
        if risk_score > 0.7:
            rationale_parts.append("with significant risk reduction")
        elif risk_score < 0.3:
            rationale_parts.append("with risk-appropriate sizing")
        
        # Confidence factors
        if confidence > 0.8:
            rationale_parts.append("reflecting high analysis confidence")
        elif confidence < 0.4:
            rationale_parts.append("reflecting low analysis confidence")
        
        # Market factors
        volatility = market_conditions.get('volatility', 0.1)
        if volatility > 0.3:
            rationale_parts.append("accounting for high market volatility")
        
        return f"{final_size:.1f}% " + ", ".join(rationale_parts) + "."
    
    def _generate_sizing_warnings(
        self,
        final_size: float,
        risk_score: float,
        confidence: float,
        market_conditions: Dict[str, Any],
        portfolio_context: Dict[str, Any]
    ) -> List[str]:
        """Generate warnings about position sizing."""
        warnings = []
        
        # Size warnings
        if final_size <= self.min_position_percent:
            warnings.append("Position size at minimum due to risk constraints")
        elif final_size >= self.max_position_percent:
            warnings.append("Position size at maximum - consider risk carefully")
        
        # Risk warnings
        if risk_score > 0.8:
            warnings.append("High risk score - consider avoiding this trade")
        elif risk_score > 0.6:
            warnings.append("Elevated risk - monitor position closely")
        
        # Confidence warnings
        if confidence < 0.3:
            warnings.append("Low analysis confidence - consider additional research")
        
        # Market warnings
        volatility = market_conditions.get('volatility', 0.1)
        if volatility > 0.4:
            warnings.append("Extreme volatility - position may experience large swings")
        
        # Portfolio warnings
        position_count = portfolio_context.get('position_count', 0)
        if position_count >= 8:
            warnings.append("Portfolio approaching maximum position limit")
        
        total_risk = portfolio_context.get('total_risk_percent', 0.0)
        if total_risk > 8.0:
            warnings.append("Portfolio risk approaching maximum limit")
        
        return warnings
    
    def _create_default_sizing(self, risk_score: float) -> SizingCalculation:
        """Create default sizing when calculation fails."""
        # Conservative default based on risk
        if risk_score > 0.7:
            default_size = 1.0  # Minimal size for high risk
        elif risk_score > 0.4:
            default_size = 2.5  # Small size for medium risk
        else:
            default_size = 5.0  # Standard size for low risk
        
        return SizingCalculation(
            recommended_size_percent=default_size,
            method_used=SizingMethod.FIXED_PERCENT,
            risk_adjusted_size=default_size,
            confidence_adjusted_size=default_size,
            technical_adjusted_size=default_size,
            max_allowed_size=self.max_position_percent,
            sizing_rationale=f"Default {default_size}% position due to calculation error",
            warnings=["Using default position size - review calculation manually"],
            calculation_details={'error': 'Calculation failed', 'default_applied': True}
        )
    
    def calculate_position_value(
        self,
        position_size_percent: float,
        portfolio_value: float,
        token_price: float
    ) -> Dict[str, Any]:
        """
        Calculate actual position value and token quantity.
        
        Args:
            position_size_percent: Position size as percentage of portfolio
            portfolio_value: Total portfolio value in USD
            token_price: Current token price in USD
            
        Returns:
            Dictionary with position calculations
        """
        try:
            # Calculate position value
            position_value = portfolio_value * (position_size_percent / 100)
            
            # Calculate token quantity
            token_quantity = position_value / token_price if token_price > 0 else 0
            
            # Calculate risk amount (assuming 15% max loss)
            risk_amount = position_value * 0.15
            risk_percent_of_portfolio = (risk_amount / portfolio_value) * 100
            
            return {
                'position_value_usd': position_value,
                'token_quantity': token_quantity,
                'risk_amount_usd': risk_amount,
                'risk_percent_portfolio': risk_percent_of_portfolio,
                'position_percent_portfolio': position_size_percent,
                'token_price': token_price,
                'calculations_valid': True
            }
            
        except Exception as e:
            logger.error(f"Error calculating position value: {e}")
            return {
                'position_value_usd': 0.0,
                'token_quantity': 0.0,
                'risk_amount_usd': 0.0,
                'risk_percent_portfolio': 0.0,
                'position_percent_portfolio': 0.0,
                'token_price': 0.0,
                'calculations_valid': False,
                'error': str(e)
            }
    
    def validate_position_size(
        self,
        position_size_percent: float,
        portfolio_context: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate if position size is acceptable given current portfolio state.
        
        Args:
            position_size_percent: Proposed position size
            portfolio_context: Current portfolio state
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        # Size bounds check
        if position_size_percent < self.min_position_percent:
            issues.append(f"Position size below minimum {self.min_position_percent}%")
        elif position_size_percent > self.max_position_percent:
            issues.append(f"Position size exceeds maximum {self.max_position_percent}%")
        
        # Portfolio capacity check
        current_positions = portfolio_context.get('position_count', 0)
        if current_positions >= 10:
            issues.append("Portfolio at maximum position capacity")
        
        # Capital availability check
        available_capital = portfolio_context.get('available_capital_percent', 100.0)
        if position_size_percent > available_capital:
            issues.append(f"Insufficient capital: {available_capital:.1f}% available")
        
        # Risk budget check
        current_risk = portfolio_context.get('total_risk_percent', 0.0)
        position_risk = position_size_percent * 0.15  # Assume 15% risk
        
        if current_risk + position_risk > self.max_total_risk:
            issues.append(f"Risk budget exceeded: {current_risk + position_risk:.1f}% > {self.max_total_risk}%")
        
        return len(issues) == 0, issues


# Export main class
__all__ = ['PositionSizer', 'SizingCalculation', 'SizingMethod']