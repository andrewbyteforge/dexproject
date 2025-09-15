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
from decimal import Decimal

from . import SizingMethod, StrategyMetrics

logger = logging.getLogger(__name__)


@dataclass
class SizingCalculation:
    """Position sizing calculation result."""
    recommended_size_percent: float
    sizing_method_used: SizingMethod
    risk_adjusted_size: float
    max_position_size: float
    min_position_size: float
    
    # Risk metrics
    position_risk_score: float
    portfolio_risk_impact: float
    concentration_risk: float
    
    # Adjustment factors
    confidence_adjustment: float
    volatility_adjustment: float
    liquidity_adjustment: float
    market_condition_adjustment: float
    
    # Reasoning
    sizing_rationale: str
    risk_warnings: List[str]
    optimization_notes: List[str]


class PositionSizer:
    """
    Advanced position sizing calculator for Smart Lane trades.
    
    Implements multiple sizing methodologies including Kelly Criterion,
    risk-based sizing, and volatility-adjusted position calculations.
    """
    
    def __init__(self, config: Any):
        """
        Initialize position sizer with configuration.
        
        Args:
            config: Smart Lane configuration object
        """
        self.config = config
        
        # Default sizing parameters
        self.max_position_percent = getattr(config, 'max_position_size_percent', 10.0)
        self.min_position_percent = 0.5
        self.risk_per_trade_percent = getattr(config, 'risk_per_trade_percent', 2.0)
        self.enable_dynamic_sizing = getattr(config, 'enable_dynamic_sizing', True)
        
        # Risk management limits
        self.max_portfolio_concentration = 0.25  # Max 25% in single position
        self.max_correlated_exposure = 0.40      # Max 40% in correlated assets
        self.max_total_risk_exposure = 0.30      # Max 30% portfolio at risk
        
        # Kelly Criterion parameters
        self.kelly_fraction = 0.25  # Use 25% of Kelly for safety
        self.max_kelly_size = 0.15  # Never exceed 15% even with high Kelly
        
        # Performance tracking
        self.sizing_history = []
        self.performance_stats = {
            'total_sized': 0,
            'avg_size_percent': 0,
            'kelly_overrides': 0,
            'risk_limit_hits': 0
        }
        
        logger.info(f"PositionSizer initialized with max {self.max_position_percent}% position size")
    
    def calculate_position_size(
        self,
        analysis_confidence: float,
        overall_risk_score: float,
        technical_signals: List[Any],
        market_conditions: Dict[str, Any],
        portfolio_context: Optional[Dict[str, Any]] = None
    ) -> SizingCalculation:
        """
        Calculate optimal position size based on multiple factors.
        
        Args:
            analysis_confidence: Confidence score from analysis (0-1)
            overall_risk_score: Overall risk assessment (0-1, lower is better)
            technical_signals: List of technical analysis signals
            market_conditions: Current market condition data
            portfolio_context: Optional portfolio state information
            
        Returns:
            Complete position sizing calculation with rationale
        """
        logger.debug(f"Calculating position size: confidence={analysis_confidence:.2f}, risk={overall_risk_score:.2f}")
        
        # Select sizing method based on configuration and conditions
        sizing_method = self._select_sizing_method(
            analysis_confidence,
            overall_risk_score,
            market_conditions
        )
        
        # Calculate base position size using selected method
        base_size = self._calculate_base_size(
            sizing_method,
            analysis_confidence,
            overall_risk_score,
            technical_signals
        )
        
        # Apply risk adjustments
        risk_adjusted_size = self._apply_risk_adjustments(
            base_size,
            overall_risk_score,
            portfolio_context
        )
        
        # Apply market condition adjustments
        market_adjusted_size = self._apply_market_adjustments(
            risk_adjusted_size,
            market_conditions
        )
        
        # Apply portfolio constraints
        final_size = self._apply_portfolio_constraints(
            market_adjusted_size,
            portfolio_context
        )
        
        # Calculate adjustment factors for transparency
        confidence_adjustment = self._calculate_confidence_adjustment(analysis_confidence)
        volatility_adjustment = self._calculate_volatility_adjustment(market_conditions)
        liquidity_adjustment = self._calculate_liquidity_adjustment(market_conditions)
        market_condition_adjustment = self._calculate_market_condition_adjustment(market_conditions)
        
        # Generate sizing rationale
        sizing_rationale = self._generate_sizing_rationale(
            sizing_method,
            base_size,
            final_size,
            analysis_confidence,
            overall_risk_score
        )
        
        # Identify risk warnings
        risk_warnings = self._identify_risk_warnings(
            final_size,
            overall_risk_score,
            portfolio_context
        )
        
        # Generate optimization notes
        optimization_notes = self._generate_optimization_notes(
            final_size,
            analysis_confidence,
            market_conditions
        )
        
        # Update statistics
        self._update_statistics(final_size, sizing_method)
        
        return SizingCalculation(
            recommended_size_percent=final_size,
            sizing_method_used=sizing_method,
            risk_adjusted_size=risk_adjusted_size,
            max_position_size=self.max_position_percent,
            min_position_size=self.min_position_percent,
            position_risk_score=self._calculate_position_risk(final_size, overall_risk_score),
            portfolio_risk_impact=self._calculate_portfolio_impact(final_size, portfolio_context),
            concentration_risk=self._calculate_concentration_risk(final_size, portfolio_context),
            confidence_adjustment=confidence_adjustment,
            volatility_adjustment=volatility_adjustment,
            liquidity_adjustment=liquidity_adjustment,
            market_condition_adjustment=market_condition_adjustment,
            sizing_rationale=sizing_rationale,
            risk_warnings=risk_warnings,
            optimization_notes=optimization_notes
        )
    
    def _select_sizing_method(
        self,
        confidence: float,
        risk_score: float,
        market_conditions: Dict[str, Any]
    ) -> SizingMethod:
        """Select appropriate sizing method based on conditions."""
        if not self.enable_dynamic_sizing:
            return SizingMethod.FIXED_PERCENT
        
        # High confidence + low risk = Kelly Criterion
        if confidence > 0.8 and risk_score < 0.3:
            return SizingMethod.KELLY_CRITERION
        
        # High volatility = Volatility adjusted
        if market_conditions.get('volatility', 0) > 0.3:
            return SizingMethod.VOLATILITY_ADJUSTED
        
        # Medium confidence = Confidence weighted
        if 0.5 <= confidence <= 0.8:
            return SizingMethod.CONFIDENCE_WEIGHTED
        
        # Default to risk-based sizing
        return SizingMethod.RISK_BASED
    
    def _calculate_base_size(
        self,
        method: SizingMethod,
        confidence: float,
        risk_score: float,
        technical_signals: List[Any]
    ) -> float:
        """Calculate base position size using selected method."""
        if method == SizingMethod.FIXED_PERCENT:
            return 5.0  # Fixed 5% position
        
        elif method == SizingMethod.KELLY_CRITERION:
            return self._calculate_kelly_size(confidence, risk_score, technical_signals)
        
        elif method == SizingMethod.RISK_BASED:
            return self._calculate_risk_based_size(risk_score)
        
        elif method == SizingMethod.VOLATILITY_ADJUSTED:
            return self._calculate_volatility_based_size(risk_score)
        
        elif method == SizingMethod.CONFIDENCE_WEIGHTED:
            return self._calculate_confidence_weighted_size(confidence, risk_score)
        
        return 5.0  # Default fallback
    
    def _calculate_kelly_size(
        self,
        confidence: float,
        risk_score: float,
        technical_signals: List[Any]
    ) -> float:
        """
        Calculate position size using Kelly Criterion.
        
        Kelly % = (p * b - q) / b
        Where:
        - p = probability of winning
        - q = probability of losing (1 - p)
        - b = ratio of win to loss
        """
        # Estimate win probability from confidence and risk
        win_probability = confidence * (1 - risk_score)
        
        # Estimate win/loss ratio from technical signals
        win_loss_ratio = self._estimate_win_loss_ratio(technical_signals)
        
        # Kelly calculation
        if win_loss_ratio > 0:
            kelly_percent = (
                (win_probability * win_loss_ratio - (1 - win_probability)) / 
                win_loss_ratio
            )
        else:
            kelly_percent = 0
        
        # Apply Kelly fraction for safety
        kelly_size = kelly_percent * self.kelly_fraction * 100
        
        # Cap at maximum Kelly size
        kelly_size = min(kelly_size, self.max_kelly_size * 100)
        
        # Never go negative
        kelly_size = max(kelly_size, 0)
        
        logger.debug(f"Kelly sizing: p={win_probability:.2f}, b={win_loss_ratio:.2f}, size={kelly_size:.1f}%")
        
        return kelly_size
    
    def _calculate_risk_based_size(self, risk_score: float) -> float:
        """Calculate size based on risk score."""
        # Inverse relationship: lower risk = larger position
        risk_multiplier = 1 - risk_score
        base_size = self.risk_per_trade_percent * 2  # Base on 2x risk per trade
        
        return base_size * risk_multiplier * (1 + risk_multiplier)
    
    def _calculate_volatility_based_size(self, risk_score: float) -> float:
        """Calculate size adjusted for volatility."""
        # Start with standard size
        base_size = 5.0
        
        # Reduce size based on risk (as proxy for volatility)
        volatility_factor = 1 - (risk_score * 0.7)  # Max 70% reduction
        
        return base_size * volatility_factor
    
    def _calculate_confidence_weighted_size(
        self,
        confidence: float,
        risk_score: float
    ) -> float:
        """Calculate size weighted by confidence level."""
        # Base size scaled by confidence
        base_size = self.max_position_percent * 0.5  # Start at 50% of max
        
        # Apply confidence scaling
        confidence_factor = confidence ** 1.5  # Non-linear scaling
        
        # Apply risk reduction
        risk_factor = 1 - (risk_score * 0.5)
        
        return base_size * confidence_factor * risk_factor
    
    def _estimate_win_loss_ratio(self, technical_signals: List[Any]) -> float:
        """Estimate win/loss ratio from technical signals."""
        if not technical_signals:
            return 1.5  # Default ratio
        
        # Extract price targets from signals
        ratios = []
        for signal in technical_signals:
            if hasattr(signal, 'price_targets'):
                targets = signal.price_targets
                if 'take_profit' in targets and 'stop_loss' in targets:
                    ratio = abs(targets['take_profit']) / abs(targets['stop_loss'])
                    ratios.append(ratio)
        
        if ratios:
            return sum(ratios) / len(ratios)
        
        return 1.5  # Default ratio
    
    def _apply_risk_adjustments(
        self,
        base_size: float,
        risk_score: float,
        portfolio_context: Optional[Dict[str, Any]]
    ) -> float:
        """Apply risk-based adjustments to position size."""
        adjusted_size = base_size
        
        # High risk reduction
        if risk_score > 0.7:
            adjusted_size *= 0.5  # Halve position for high risk
            self.performance_stats['risk_limit_hits'] += 1
        elif risk_score > 0.5:
            adjusted_size *= 0.75  # 25% reduction for medium-high risk
        
        # Portfolio risk considerations
        if portfolio_context:
            current_risk = portfolio_context.get('total_risk_exposure', 0)
            if current_risk > 0.25:  # Portfolio already has high risk
                adjusted_size *= 0.7  # Reduce new position size
        
        return adjusted_size
    
    def _apply_market_adjustments(
        self,
        size: float,
        market_conditions: Dict[str, Any]
    ) -> float:
        """Apply market condition adjustments."""
        adjusted_size = size
        
        # Volatility adjustment
        volatility = market_conditions.get('volatility', 0.1)
        if volatility > 0.3:
            adjusted_size *= 0.7  # Reduce in high volatility
        elif volatility > 0.2:
            adjusted_size *= 0.85
        
        # Liquidity adjustment
        liquidity = market_conditions.get('liquidity_score', 1.0)
        if liquidity < 0.3:
            adjusted_size *= 0.5  # Halve for low liquidity
        elif liquidity < 0.5:
            adjusted_size *= 0.75
        
        # Trend adjustment
        trend = market_conditions.get('trend_strength', 0)
        if abs(trend) > 0.7:  # Strong trend
            adjusted_size *= 1.2  # Increase size in strong trends
        
        return adjusted_size
    
    def _apply_portfolio_constraints(
        self,
        size: float,
        portfolio_context: Optional[Dict[str, Any]]
    ) -> float:
        """Apply portfolio-level constraints."""
        final_size = size
        
        # Apply absolute limits
        final_size = max(self.min_position_percent, final_size)
        final_size = min(self.max_position_percent, final_size)
        
        if portfolio_context:
            # Check concentration limits
            largest_position = portfolio_context.get('largest_position_percent', 0)
            if largest_position > 20 and final_size > 5:
                final_size = 5  # Limit to 5% if already concentrated
            
            # Check number of positions
            position_count = portfolio_context.get('position_count', 0)
            if position_count > 10:
                # Reduce size as portfolio gets more positions
                final_size *= (10 / position_count)
            
            # Check available capital
            available_capital = portfolio_context.get('available_capital_percent', 100)
            if available_capital < final_size:
                final_size = available_capital * 0.9  # Use 90% of available
        
        return round(final_size, 2)
    
    def _calculate_confidence_adjustment(self, confidence: float) -> float:
        """Calculate confidence-based adjustment factor."""
        # Non-linear scaling: low confidence has bigger impact
        if confidence < 0.3:
            return 0.3
        elif confidence < 0.5:
            return 0.5
        elif confidence < 0.7:
            return 0.75
        elif confidence < 0.9:
            return 0.9
        else:
            return 1.0
    
    def _calculate_volatility_adjustment(self, market_conditions: Dict[str, Any]) -> float:
        """Calculate volatility-based adjustment factor."""
        volatility = market_conditions.get('volatility', 0.1)
        
        if volatility > 0.4:
            return 0.5
        elif volatility > 0.3:
            return 0.7
        elif volatility > 0.2:
            return 0.85
        elif volatility > 0.1:
            return 0.95
        else:
            return 1.0
    
    def _calculate_liquidity_adjustment(self, market_conditions: Dict[str, Any]) -> float:
        """Calculate liquidity-based adjustment factor."""
        liquidity = market_conditions.get('liquidity_score', 1.0)
        
        if liquidity < 0.2:
            return 0.3
        elif liquidity < 0.4:
            return 0.6
        elif liquidity < 0.6:
            return 0.8
        elif liquidity < 0.8:
            return 0.9
        else:
            return 1.0
    
    def _calculate_market_condition_adjustment(
        self,
        market_conditions: Dict[str, Any]
    ) -> float:
        """Calculate overall market condition adjustment."""
        # Combine multiple market factors
        trend = market_conditions.get('trend_strength', 0)
        momentum = market_conditions.get('momentum', 0)
        fear_greed = market_conditions.get('fear_greed_index', 50) / 100
        
        # Average the factors
        market_score = (abs(trend) + abs(momentum) + fear_greed) / 3
        
        if market_score > 0.7:
            return 1.1  # Slightly increase in good conditions
        elif market_score > 0.5:
            return 1.0
        elif market_score > 0.3:
            return 0.9
        else:
            return 0.8
    
    def _calculate_position_risk(self, size: float, risk_score: float) -> float:
        """Calculate risk associated with position size."""
        return (size / 100) * risk_score
    
    def _calculate_portfolio_impact(
        self,
        size: float,
        portfolio_context: Optional[Dict[str, Any]]
    ) -> float:
        """Calculate impact on overall portfolio risk."""
        if not portfolio_context:
            return size / 100
        
        current_risk = portfolio_context.get('total_risk_exposure', 0)
        new_risk = current_risk + (size / 100)
        
        return new_risk
    
    def _calculate_concentration_risk(
        self,
        size: float,
        portfolio_context: Optional[Dict[str, Any]]
    ) -> float:
        """Calculate concentration risk score."""
        if not portfolio_context:
            return size / self.max_position_percent
        
        largest_position = portfolio_context.get('largest_position_percent', 0)
        new_largest = max(largest_position, size)
        
        # Concentration risk increases non-linearly
        return (new_largest / self.max_position_percent) ** 2
    
    def _generate_sizing_rationale(
        self,
        method: SizingMethod,
        base_size: float,
        final_size: float,
        confidence: float,
        risk_score: float
    ) -> str:
        """Generate human-readable sizing rationale."""
        rationale = f"Position sized using {method.value} method. "
        
        if method == SizingMethod.KELLY_CRITERION:
            rationale += f"Kelly Criterion suggests {base_size:.1f}% based on {confidence:.0%} confidence. "
        elif method == SizingMethod.RISK_BASED:
            rationale += f"Risk-based sizing for {risk_score:.0%} risk score. "
        elif method == SizingMethod.CONFIDENCE_WEIGHTED:
            rationale += f"Confidence-weighted sizing at {confidence:.0%} confidence level. "
        
        if abs(final_size - base_size) > 1:
            reduction = ((base_size - final_size) / base_size) * 100
            if reduction > 0:
                rationale += f"Reduced {reduction:.0f}% due to risk and market adjustments. "
            else:
                rationale += f"Increased {abs(reduction):.0f}% due to favorable conditions. "
        
        rationale += f"Final position: {final_size:.1f}% of portfolio."
        
        return rationale
    
    def _identify_risk_warnings(
        self,
        size: float,
        risk_score: float,
        portfolio_context: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Identify risk warnings for the position."""
        warnings = []
        
        if risk_score > 0.7:
            warnings.append("⚠️ High risk score - consider reducing position or avoiding")
        
        if size > 7.5:
            warnings.append("⚠️ Large position size - increased portfolio concentration risk")
        
        if portfolio_context:
            if portfolio_context.get('position_count', 0) > 15:
                warnings.append("⚠️ Portfolio has many positions - consider consolidation")
            
            if portfolio_context.get('total_risk_exposure', 0) > 0.25:
                warnings.append("⚠️ Portfolio risk exposure already high")
            
            if portfolio_context.get('available_capital_percent', 100) < size * 1.1:
                warnings.append("⚠️ Limited available capital for position")
        
        return warnings
    
    def _generate_optimization_notes(
        self,
        size: float,
        confidence: float,
        market_conditions: Dict[str, Any]
    ) -> List[str]:
        """Generate optimization suggestions."""
        notes = []
        
        if confidence > 0.85 and size < 5:
            notes.append("💡 High confidence but conservative sizing - consider scaling up")
        
        if market_conditions.get('trend_strength', 0) > 0.7 and size < 7:
            notes.append("💡 Strong trend detected - position could be larger")
        
        if market_conditions.get('volatility', 0) < 0.1 and size < self.max_position_percent:
            notes.append("💡 Low volatility environment - safe to increase position")
        
        if size == self.max_position_percent:
            notes.append("💡 At maximum position size - consider splitting entry")
        
        return notes
    
    def _update_statistics(self, size: float, method: SizingMethod) -> None:
        """Update internal statistics."""
        self.performance_stats['total_sized'] += 1
        
        # Update rolling average
        current_avg = self.performance_stats['avg_size_percent']
        new_count = self.performance_stats['total_sized']
        new_avg = ((current_avg * (new_count - 1)) + size) / new_count
        self.performance_stats['avg_size_percent'] = new_avg
        
        if method == SizingMethod.KELLY_CRITERION:
            self.performance_stats['kelly_overrides'] += 1
        
        # Store in history (keep last 100)
        self.sizing_history.append({
            'size': size,
            'method': method.value,
            'timestamp': 'current'
        })
        
        if len(self.sizing_history) > 100:
            self.sizing_history.pop(0)