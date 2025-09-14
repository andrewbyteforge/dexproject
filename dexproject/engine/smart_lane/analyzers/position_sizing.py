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
            config: Smart Lane configuration with sizing parameters
        """
        self.config = config
        
        # Position sizing parameters
        self.max_position_percent = config.max_position_size_percent
        self.risk_per_trade_percent = config.risk_per_trade_percent
        self.enable_dynamic_sizing = config.enable_dynamic_sizing
        
        # Sizing method weights for ensemble approach
        self.method_weights = {
            SizingMethod.RISK_BASED: 0.4,
            SizingMethod.CONFIDENCE_WEIGHTED: 0.3,
            SizingMethod.VOLATILITY_ADJUSTED: 0.2,
            SizingMethod.KELLY_CRITERION: 0.1
        }
        
        # Risk category impact factors
        self.risk_impact_factors = {
            RiskCategory.HONEYPOT_DETECTION: 0.9,     # Highest impact
            RiskCategory.CONTRACT_SECURITY: 0.8,      # High impact  
            RiskCategory.LIQUIDITY_ANALYSIS: 0.7,     # High impact
            RiskCategory.TOKEN_TAX_ANALYSIS: 0.6,     # Medium-high impact
            RiskCategory.HOLDER_DISTRIBUTION: 0.5,    # Medium impact
            RiskCategory.MARKET_STRUCTURE: 0.4,       # Medium impact
            RiskCategory.SOCIAL_SENTIMENT: 0.3,       # Lower impact
            RiskCategory.TECHNICAL_ANALYSIS: 0.2      # Lowest impact (handled separately)
        }
        
        logger.info(f"Position sizer initialized - Max position: {self.max_position_percent}%")
    
    async def calculate_position_size(
        self,
        risk_score: float,
        confidence: float,
        technical_signals: List[TechnicalSignal],
        context: Dict[str, Any]
    ) -> float:
        """
        Calculate optimal position size using ensemble methodology.
        
        Args:
            risk_score: Overall risk score (0-1, higher is riskier)
            confidence: Analysis confidence (0-1, higher is more confident)
            technical_signals: List of technical analysis signals
            context: Additional context for sizing calculation
            
        Returns:
            Recommended position size as percentage of portfolio
        """
        try:
            logger.debug(f"Calculating position size: risk={risk_score:.3f}, confidence={confidence:.3f}")
            
            # Calculate using different methods
            sizing_results = await self._calculate_all_methods(
                risk_score=risk_score,
                confidence=confidence,
                technical_signals=technical_signals,
                context=context
            )
            
            # Combine results using weighted ensemble
            final_size = self._combine_sizing_methods(sizing_results)
            
            # Apply safety constraints
            constrained_size = self._apply_position_constraints(final_size, risk_score, confidence)
            
            logger.debug(f"Final position size calculated: {constrained_size:.2f}%")
            
            return constrained_size
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}", exc_info=True)
            # Return conservative fallback size
            return min(1.0, self.risk_per_trade_percent / 2)
    
    async def calculate_detailed_sizing(
        self,
        risk_score: float,
        confidence: float,
        technical_signals: List[TechnicalSignal],
        context: Dict[str, Any]
    ) -> SizingCalculation:
        """
        Calculate detailed position sizing with full breakdown.
        
        Args:
            risk_score: Overall risk score (0-1)
            confidence: Analysis confidence (0-1)  
            technical_signals: Technical analysis signals
            context: Additional context
            
        Returns:
            Detailed sizing calculation with rationale
        """
        try:
            # Calculate using all methods
            sizing_results = await self._calculate_all_methods(
                risk_score, confidence, technical_signals, context
            )
            
            # Determine primary method
            primary_method = max(sizing_results.keys(), key=lambda k: self.method_weights.get(k, 0))
            
            # Calculate component adjustments
            risk_adjusted = self._calculate_risk_adjusted_size(risk_score)
            confidence_adjusted = self._calculate_confidence_adjusted_size(confidence)
            technical_adjusted = self._calculate_technical_adjusted_size(technical_signals)
            
            # Final ensemble size
            final_size = self._combine_sizing_methods(sizing_results)
            constrained_size = self._apply_position_constraints(final_size, risk_score, confidence)
            
            # Generate warnings
            warnings = self._generate_sizing_warnings(constrained_size, risk_score, confidence)
            
            # Create rationale
            rationale = self._create_sizing_rationale(
                constrained_size, primary_method, risk_score, confidence, technical_signals
            )
            
            return SizingCalculation(
                recommended_size_percent=constrained_size,
                method_used=primary_method,
                risk_adjusted_size=risk_adjusted,
                confidence_adjusted_size=confidence_adjusted,
                technical_adjusted_size=technical_adjusted,
                max_allowed_size=self.max_position_percent,
                sizing_rationale=rationale,
                warnings=warnings,
                calculation_details={
                    'method_results': sizing_results,
                    'method_weights': self.method_weights,
                    'constraints_applied': True,
                    'risk_score': risk_score,
                    'confidence': confidence,
                    'technical_signal_count': len(technical_signals)
                }
            )
            
        except Exception as e:
            logger.error(f"Error in detailed sizing calculation: {e}", exc_info=True)
            
            # Return conservative fallback
            fallback_size = min(1.0, self.risk_per_trade_percent / 2)
            
            return SizingCalculation(
                recommended_size_percent=fallback_size,
                method_used=SizingMethod.FIXED_PERCENT,
                risk_adjusted_size=fallback_size,
                confidence_adjusted_size=fallback_size,
                technical_adjusted_size=fallback_size,
                max_allowed_size=self.max_position_percent,
                sizing_rationale=f"Conservative fallback due to calculation error: {str(e)}",
                warnings=[f"Sizing calculation error: {str(e)}"],
                calculation_details={'error': str(e)}
            )
    
    async def _calculate_all_methods(
        self,
        risk_score: float,
        confidence: float,
        technical_signals: List[TechnicalSignal],
        context: Dict[str, Any]
    ) -> Dict[SizingMethod, float]:
        """Calculate position size using all available methods."""
        results = {}
        
        # Risk-based sizing
        results[SizingMethod.RISK_BASED] = self._calculate_risk_based_sizing(risk_score)
        
        # Confidence-weighted sizing
        results[SizingMethod.CONFIDENCE_WEIGHTED] = self._calculate_confidence_weighted_sizing(
            confidence, risk_score
        )
        
        # Volatility-adjusted sizing
        results[SizingMethod.VOLATILITY_ADJUSTED] = self._calculate_volatility_adjusted_sizing(
            technical_signals, context
        )
        
        # Kelly criterion sizing
        results[SizingMethod.KELLY_CRITERION] = self._calculate_kelly_criterion_sizing(
            risk_score, confidence, technical_signals
        )
        
        # Fixed percentage (baseline)
        results[SizingMethod.FIXED_PERCENT] = self._calculate_fixed_percent_sizing()
        
        return results
    
    def _calculate_risk_based_sizing(self, risk_score: float) -> float:
        """
        Calculate position size based on risk score.
        
        Uses inverse relationship: higher risk = smaller position.
        """
        # Base size from risk tolerance
        base_size = self.risk_per_trade_percent
        
        # Risk adjustment factor (exponential decay)
        risk_factor = math.exp(-3 * risk_score)  # e^(-3*risk)
        
        # Apply risk factor
        risk_adjusted_size = base_size * risk_factor
        
        # Ensure minimum viable size
        min_size = 0.1  # 0.1% minimum
        return max(min_size, risk_adjusted_size)
    
    def _calculate_confidence_weighted_sizing(self, confidence: float, risk_score: float) -> float:
        """
        Calculate position size weighted by analysis confidence.
        
        Higher confidence allows for larger positions, but still respects risk limits.
        """
        # Base size from configuration
        base_size = self.risk_per_trade_percent
        
        # Confidence multiplier (sigmoid curve for smooth scaling)
        confidence_multiplier = 1 / (1 + math.exp(-10 * (confidence - 0.5)))
        
        # Risk constraint (don't let confidence override high risk)
        risk_constraint = 1.0 - (risk_score * 0.8)
        
        # Combined adjustment
        adjusted_size = base_size * confidence_multiplier * risk_constraint
        
        return max(0.1, adjusted_size)
    
    def _calculate_volatility_adjusted_sizing(
        self,
        technical_signals: List[TechnicalSignal],
        context: Dict[str, Any]
    ) -> float:
        """
        Calculate position size adjusted for expected volatility.
        
        Uses technical indicators to estimate volatility and adjust accordingly.
        """
        # Base size
        base_size = self.risk_per_trade_percent
        
        if not technical_signals:
            return base_size
        
        # Estimate volatility from technical signals
        volatility_estimate = self._estimate_volatility_from_signals(technical_signals)
        
        # Volatility adjustment (inverse relationship)
        # High volatility = smaller position
        volatility_factor = 1.0 / (1.0 + volatility_estimate)
        
        return base_size * volatility_factor
    
    def _calculate_kelly_criterion_sizing(
        self,
        risk_score: float,
        confidence: float,
        technical_signals: List[TechnicalSignal]
    ) -> float:
        """
        Calculate position size using Kelly Criterion.
        
        Kelly % = (bp - q) / b
        Where:
        - b = odds received (reward/risk ratio)
        - p = probability of winning  
        - q = probability of losing (1-p)
        """
        # Estimate probability of success based on confidence and risk
        win_probability = confidence * (1.0 - risk_score * 0.5)
        lose_probability = 1.0 - win_probability
        
        # Estimate reward/risk ratio from technical signals
        reward_risk_ratio = self._estimate_reward_risk_ratio(technical_signals)
        
        # Kelly formula
        if reward_risk_ratio > 0 and win_probability > 0:
            kelly_percent = (
                (reward_risk_ratio * win_probability - lose_probability) / 
                reward_risk_ratio
            )
        else:
            kelly_percent = 0.0
        
        # Apply Kelly fraction (typically use 25-50% of full Kelly)
        kelly_fraction = 0.25
        adjusted_kelly = kelly_percent * kelly_fraction
        
        # Convert to position size percentage and constrain
        kelly_size = max(0.1, min(self.max_position_percent, adjusted_kelly * 100))
        
        return kelly_size
    
    def _calculate_fixed_percent_sizing(self) -> float:
        """Calculate simple fixed percentage sizing."""
        return self.risk_per_trade_percent
    
    def _combine_sizing_methods(self, sizing_results: Dict[SizingMethod, float]) -> float:
        """
        Combine sizing method results using weighted ensemble.
        
        Args:
            sizing_results: Results from different sizing methods
            
        Returns:
            Combined position size
        """
        weighted_sum = 0.0
        total_weight = 0.0
        
        for method, size in sizing_results.items():
            weight = self.method_weights.get(method, 0.1)
            weighted_sum += size * weight
            total_weight += weight
        
        if total_weight > 0:
            combined_size = weighted_sum / total_weight
        else:
            # Fallback to risk-based sizing
            combined_size = sizing_results.get(SizingMethod.RISK_BASED, self.risk_per_trade_percent)
        
        return combined_size
    
    def _apply_position_constraints(
        self,
        calculated_size: float,
        risk_score: float,
        confidence: float
    ) -> float:
        """
        Apply final position constraints and safety limits.
        
        Args:
            calculated_size: Size calculated by ensemble methods
            risk_score: Overall risk score
            confidence: Analysis confidence
            
        Returns:
            Constrained position size
        """
        # Start with calculated size
        constrained_size = calculated_size
        
        # Apply maximum position limit
        constrained_size = min(constrained_size, self.max_position_percent)
        
        # Apply risk-based limits
        if risk_score > 0.8:  # Critical risk
            constrained_size = min(constrained_size, 0.5)  # Max 0.5%
        elif risk_score > 0.6:  # High risk
            constrained_size = min(constrained_size, 1.5)  # Max 1.5%
        elif risk_score > 0.4:  # Medium risk
            constrained_size = min(constrained_size, 3.0)  # Max 3%
        
        # Apply confidence-based limits
        if confidence < 0.5:  # Low confidence
            constrained_size = min(constrained_size, 2.0)  # Max 2%
        elif confidence < 0.7:  # Medium confidence  
            constrained_size = min(constrained_size, 5.0)  # Max 5%
        
        # Ensure minimum viable size
        constrained_size = max(0.1, constrained_size)
        
        return constrained_size
    
    def _calculate_risk_adjusted_size(self, risk_score: float) -> float:
        """Calculate position size component based purely on risk."""
        return self.max_position_percent * (1.0 - risk_score)
    
    def _calculate_confidence_adjusted_size(self, confidence: float) -> float:
        """Calculate position size component based purely on confidence."""
        return self.max_position_percent * confidence
    
    def _calculate_technical_adjusted_size(self, technical_signals: List[TechnicalSignal]) -> float:
        """Calculate position size component based on technical signals."""
        if not technical_signals:
            return self.max_position_percent * 0.5
        
        # Calculate signal strength
        avg_strength = sum(signal.strength for signal in technical_signals) / len(technical_signals)
        avg_confidence = sum(signal.confidence for signal in technical_signals) / len(technical_signals)
        
        # Combine strength and confidence
        technical_factor = (avg_strength + avg_confidence) / 2.0
        
        return self.max_position_percent * technical_factor
    
    def _estimate_volatility_from_signals(self, technical_signals: List[TechnicalSignal]) -> float:
        """
        Estimate volatility from technical signals.
        
        Returns volatility estimate (0-1 scale, higher = more volatile).
        """
        if not technical_signals:
            return 0.5  # Default medium volatility
        
        volatility_indicators = []
        
        for signal in technical_signals:
            # Extract volatility indicators from signal data
            indicators = signal.indicators
            
            # Look for common volatility indicators
            if 'atr_percent' in indicators:  # Average True Range
                volatility_indicators.append(indicators['atr_percent'] / 10.0)  # Normalize
            
            if 'bollinger_width' in indicators:  # Bollinger Band width
                volatility_indicators.append(indicators['bollinger_width'] / 5.0)  # Normalize
            
            # Use signal strength as proxy for volatility
            volatility_indicators.append(signal.strength)
        
        if volatility_indicators:
            return min(1.0, sum(volatility_indicators) / len(volatility_indicators))
        else:
            return 0.5
    
    def _estimate_reward_risk_ratio(self, technical_signals: List[TechnicalSignal]) -> float:
        """
        Estimate reward/risk ratio from technical analysis.
        
        Returns estimated ratio (e.g., 2.0 means 2:1 reward/risk).
        """
        if not technical_signals:
            return 1.5  # Default conservative ratio
        
        reward_risk_ratios = []
        
        for signal in technical_signals:
            # Extract price targets from signal
            if 'price_targets' in signal.indicators:
                targets = signal.indicators['price_targets']
                if 'resistance' in targets and 'support' in targets:
                    upside = targets['resistance'] - 1.0  # Assume current price = 1.0
                    downside = 1.0 - targets['support']
                    
                    if downside > 0:
                        ratio = upside / downside
                        reward_risk_ratios.append(ratio)
            
            # Use signal strength as proxy
            if signal.signal == 'BUY':
                ratio = 1.0 + signal.strength  # 1.0 to 2.0 ratio
                reward_risk_ratios.append(ratio)
            elif signal.signal == 'SELL':
                ratio = 1.0 - (signal.strength * 0.5)  # Reduce ratio for sell signals
                reward_risk_ratios.append(ratio)
        
        if reward_risk_ratios:
            avg_ratio = sum(reward_risk_ratios) / len(reward_risk_ratios)
            return max(0.5, min(5.0, avg_ratio))  # Constrain between 0.5:1 and 5:1
        else:
            return 1.5  # Default ratio
    
    def _generate_sizing_warnings(
        self,
        position_size: float,
        risk_score: float,
        confidence: float
    ) -> List[str]:
        """Generate warnings about position sizing."""
        warnings = []
        
        # Large position warnings
        if position_size > 5.0:
            warnings.append(f"Large position size: {position_size:.1f}% - ensure adequate risk management")
        
        # High risk with large position
        if risk_score > 0.6 and position_size > 2.0:
            warnings.append("High risk score with significant position - consider reducing size")
        
        # Low confidence with large position
        if confidence < 0.6 and position_size > 3.0:
            warnings.append("Low confidence with large position - consider waiting for better setup")
        
        # Maximum position reached
        if position_size >= self.max_position_percent:
            warnings.append(f"Position capped at maximum allowed: {self.max_position_percent}%")
        
        # Very small position
        if position_size < 0.5:
            warnings.append("Very small position size - consider if trade is worthwhile")
        
        return warnings
    
    def _create_sizing_rationale(
        self,
        position_size: float,
        primary_method: SizingMethod,
        risk_score: float,
        confidence: float,
        technical_signals: List[TechnicalSignal]
    ) -> str:
        """Create human-readable rationale for position sizing decision."""
        # Risk level description
        if risk_score > 0.8:
            risk_desc = "critical"
        elif risk_score > 0.6:
            risk_desc = "high"
        elif risk_score > 0.4:
            risk_desc = "moderate"
        else:
            risk_desc = "low"
        
        # Confidence description
        if confidence > 0.8:
            confidence_desc = "high"
        elif confidence > 0.6:
            confidence_desc = "moderate"
        else:
            confidence_desc = "low"
        
        # Technical bias
        if technical_signals:
            buy_signals = sum(1 for s in technical_signals if s.signal == 'BUY')
            sell_signals = sum(1 for s in technical_signals if s.signal == 'SELL')
            
            if buy_signals > sell_signals:
                technical_desc = "bullish"
            elif sell_signals > buy_signals:
                technical_desc = "bearish"
            else:
                technical_desc = "neutral"
        else:
            technical_desc = "unavailable"
        
        rationale = f"""
        Position size of {position_size:.1f}% calculated using {primary_method.value.lower().replace('_', ' ')} methodology.
        
        Key factors:
        • Risk level: {risk_desc} ({risk_score:.2f}/1.00)
        • Analysis confidence: {confidence_desc} ({confidence:.1%})
        • Technical bias: {technical_desc} across {len(technical_signals)} timeframes
        • Portfolio risk limit: {self.risk_per_trade_percent:.1f}% per trade
        • Maximum position limit: {self.max_position_percent:.1f}%
        
        The position size balances opportunity potential with risk management requirements,
        ensuring appropriate portfolio exposure while maintaining capital preservation.
        """.strip()
        
        return rationale


# Export key classes
__all__ = [
    'PositionSizer',
    'SizingCalculation',
    'SizingMethod'
]