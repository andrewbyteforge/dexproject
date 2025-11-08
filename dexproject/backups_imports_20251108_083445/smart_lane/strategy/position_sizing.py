"""
Smart Lane Position Sizing Strategy

Intelligent position sizing system that calculates optimal position sizes
based on risk assessment, confidence levels, technical signals, and
portfolio management principles with comprehensive error handling.

Path: engine/smart_lane/strategy/position_sizing.py
"""

import logging
import math
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone

# Import from parent Smart Lane module
try:
    from .. import SmartLaneConfig, TechnicalSignal, RiskCategory
except ImportError as e:
    logging.error(f"Failed to import Smart Lane dependencies: {e}")
    # Fallback imports for testing
    SmartLaneConfig = None
    TechnicalSignal = None
    RiskCategory = None

logger = logging.getLogger(__name__)


class SizingMethod(Enum):
    """Position sizing methodologies with detailed descriptions."""
    FIXED_PERCENT = "FIXED_PERCENT"          # Fixed percentage of portfolio
    RISK_BASED = "RISK_BASED"                # Risk-adjusted sizing
    KELLY_CRITERION = "KELLY_CRITERION"      # Kelly Criterion optimal sizing
    VOLATILITY_ADJUSTED = "VOLATILITY_ADJUSTED"  # Volatility-normalized sizing
    CONFIDENCE_WEIGHTED = "CONFIDENCE_WEIGHTED"   # Confidence-based sizing
    PORTFOLIO_HEAT = "PORTFOLIO_HEAT"        # Portfolio heat model
    ANTI_MARTINGALE = "ANTI_MARTINGALE"     # Anti-martingale progression


@dataclass
class SizingCalculation:
    """
    Comprehensive position sizing calculation result with full details.
    
    Contains all sizing information, rationale, warnings, and calculation
    details for transparency and debugging purposes.
    """
    # Core sizing results
    recommended_size_percent: float
    recommended_size_usd: Optional[float] = None
    method_used: SizingMethod = SizingMethod.FIXED_PERCENT
    
    # Component calculations
    risk_adjusted_size: float = 0.0
    confidence_adjusted_size: float = 0.0
    technical_adjusted_size: float = 0.0
    volatility_adjusted_size: float = 0.0
    portfolio_adjusted_size: float = 0.0
    
    # Risk management
    max_allowed_size: float = 25.0
    min_allowed_size: float = 0.5
    suggested_stop_loss_percent: Optional[float] = None
    max_risk_per_trade_percent: float = 2.0
    
    # Calculation metadata
    sizing_rationale: str = "Default sizing calculation"
    calculation_confidence: float = 0.5
    warnings: List[str] = field(default_factory=list)
    calculation_details: Dict[str, Any] = field(default_factory=dict)
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Performance tracking
    expected_profit_loss_ratio: Optional[float] = None
    kelly_fraction: Optional[float] = None
    sharpe_adjustment: Optional[float] = None


@dataclass
class PortfolioContext:
    """Portfolio context for position sizing calculations."""
    total_portfolio_value: float
    available_cash: float
    current_position_count: int
    max_positions: int = 10
    portfolio_heat: float = 0.0  # Current risk exposure
    max_portfolio_heat: float = 20.0
    recent_pnl_streak: List[float] = field(default_factory=list)
    correlation_exposure: Dict[str, float] = field(default_factory=dict)


@dataclass
class MarketConditions:
    """Market condition context for position sizing."""
    volatility: float = 0.15
    market_regime: str = "NORMAL"  # BULL, BEAR, SIDEWAYS, VOLATILE
    liquidity_score: float = 0.5
    market_cap: Optional[float] = None
    trading_volume_24h: Optional[float] = None
    bid_ask_spread: Optional[float] = None
    market_stress_level: float = 0.0


class PositionSizerError(Exception):
    """Custom exception for position sizing errors."""
    pass


class PositionSizer:
    """
    Advanced position sizing engine with multiple methodologies.
    
    Implements sophisticated position sizing algorithms including:
    - Risk-based sizing with volatility adjustments
    - Kelly Criterion optimization
    - Confidence-weighted sizing
    - Portfolio heat management
    - Anti-martingale progression
    
    Features comprehensive error handling, logging, and validation.
    """
    
    def __init__(self, config: Optional[Any] = None):
        """
        Initialize position sizer with configuration and safety limits.
        
        Args:
            config: Smart Lane configuration object
        
        Raises:
            PositionSizerError: If initialization fails
        """
        try:
            self.config = config
            
            # Default sizing parameters with conservative limits
            self.max_position_percent = 25.0      # Never risk more than 25% on single trade
            self.min_position_percent = 0.5       # Minimum viable position size
            self.base_position_percent = 5.0      # Default base position size
            self.max_risk_per_trade = 2.0         # Max 2% portfolio risk per trade
            self.max_portfolio_heat = 20.0        # Max 20% total portfolio at risk
            
            # Kelly Criterion parameters
            self.kelly_multiplier = 0.25          # Use 25% of Kelly for safety
            self.min_win_rate_for_kelly = 0.55    # Min 55% win rate for Kelly
            
            # Performance tracking
            self.calculation_count = 0
            self.error_count = 0
            self.last_calculation_time = None
            
            # Validation ranges
            self.valid_confidence_range = (0.0, 1.0)
            self.valid_risk_score_range = (0.0, 1.0)
            self.valid_volatility_range = (0.01, 2.0)
            
            logger.info(
                f"Position sizer initialized - "
                f"max_position: {self.max_position_percent}%, "
                f"max_risk: {self.max_risk_per_trade}%, "
                f"base_size: {self.base_position_percent}%"
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize position sizer: {e}", exc_info=True)
            raise PositionSizerError(f"Initialization failed: {e}") from e
    
    def calculate_position_size(
        self,
        analysis_confidence: float,
        overall_risk_score: float,
        technical_signals: Optional[List] = None,
        market_conditions: Optional[Dict[str, Any]] = None,
        portfolio_context: Optional[Dict[str, Any]] = None,
        preferred_method: Optional[SizingMethod] = None
    ) -> SizingCalculation:
        """
        Calculate optimal position size using multiple methodologies.
        
        Args:
            analysis_confidence: Confidence in analysis (0-1)
            overall_risk_score: Overall risk assessment (0-1)
            technical_signals: List of technical analysis signals
            market_conditions: Market condition data
            portfolio_context: Current portfolio state
            preferred_method: Preferred sizing method
        
        Returns:
            SizingCalculation: Comprehensive sizing result
        
        Raises:
            PositionSizerError: If calculation fails critically
        """
        calculation_start = datetime.now(timezone.utc)
        warnings = []
        calculation_details = {}
        
        try:
            self.calculation_count += 1
            logger.debug(
                f"Starting position size calculation #{self.calculation_count} - "
                f"confidence: {analysis_confidence:.3f}, risk: {overall_risk_score:.3f}"
            )
            
            # Input validation with detailed error messages
            try:
                self._validate_inputs(
                    analysis_confidence, overall_risk_score, 
                    technical_signals, market_conditions, portfolio_context
                )
            except ValueError as e:
                logger.warning(f"Input validation failed: {e}")
                warnings.append(f"Input validation issue: {e}")
                # Continue with corrected values
                analysis_confidence = max(0.0, min(1.0, analysis_confidence))
                overall_risk_score = max(0.0, min(1.0, overall_risk_score))
            
            # Parse and validate contexts
            market_ctx = self._parse_market_conditions(market_conditions or {})
            portfolio_ctx = self._parse_portfolio_context(portfolio_context or {})
            technical_signals = technical_signals or []
            
            calculation_details.update({
                'input_confidence': analysis_confidence,
                'input_risk_score': overall_risk_score,
                'technical_signal_count': len(technical_signals),
                'market_regime': market_ctx.market_regime,
                'portfolio_positions': portfolio_ctx.current_position_count
            })
            
            # Determine optimal sizing method
            if preferred_method:
                method = preferred_method
                logger.debug(f"Using preferred method: {method.value}")
            else:
                method = self._select_optimal_method(
                    analysis_confidence, overall_risk_score, 
                    market_ctx, portfolio_ctx
                )
                logger.debug(f"Auto-selected method: {method.value}")
            
            # Calculate base position size using selected method
            try:
                base_size = self._calculate_base_size(
                    method, analysis_confidence, overall_risk_score,
                    market_ctx, portfolio_ctx, technical_signals
                )
                logger.debug(f"Base size calculated: {base_size:.2f}%")
            except Exception as e:
                logger.error(f"Base size calculation failed: {e}")
                warnings.append(f"Base calculation error: {e}")
                base_size = self.base_position_percent
                method = SizingMethod.FIXED_PERCENT
            
            # Apply adjustments and safety constraints
            adjustments = self._apply_adjustments(
                base_size, analysis_confidence, overall_risk_score,
                market_ctx, portfolio_ctx, technical_signals
            )
            
            final_size = adjustments['final_size']
            calculation_details.update(adjustments['details'])
            warnings.extend(adjustments['warnings'])
            
            # Calculate additional metrics
            stop_loss_percent = self._calculate_suggested_stop_loss(
                overall_risk_score, market_ctx.volatility
            )
            
            kelly_fraction = None
            if method == SizingMethod.KELLY_CRITERION:
                kelly_fraction = calculation_details.get('kelly_fraction', 0.0)
            
            # Build comprehensive result
            result = SizingCalculation(
                recommended_size_percent=final_size,
                recommended_size_usd=self._calculate_usd_size(final_size, portfolio_ctx),
                method_used=method,
                risk_adjusted_size=adjustments['risk_adjusted'],
                confidence_adjusted_size=adjustments['confidence_adjusted'],
                technical_adjusted_size=adjustments['technical_adjusted'],
                volatility_adjusted_size=adjustments['volatility_adjusted'],
                portfolio_adjusted_size=adjustments['portfolio_adjusted'],
                max_allowed_size=self.max_position_percent,
                min_allowed_size=self.min_position_percent,
                suggested_stop_loss_percent=stop_loss_percent,
                max_risk_per_trade_percent=self.max_risk_per_trade,
                sizing_rationale=self._generate_rationale(
                    method, final_size, analysis_confidence, overall_risk_score
                ),
                calculation_confidence=self._calculate_result_confidence(adjustments),
                warnings=warnings,
                calculation_details=calculation_details,
                calculated_at=calculation_start,
                kelly_fraction=kelly_fraction
            )
            
            # Log successful calculation
            calculation_time = (datetime.now(timezone.utc) - calculation_start).total_seconds()
            self.last_calculation_time = calculation_time
            
            logger.info(
                f"Position sizing completed successfully - "
                f"method: {method.value}, size: {final_size:.2f}%, "
                f"time: {calculation_time:.3f}s, warnings: {len(warnings)}"
            )
            
            return result
            
        except Exception as e:
            self.error_count += 1
            logger.error(
                f"Position sizing calculation failed: {e} "
                f"(error #{self.error_count})", exc_info=True
            )
            
            # Return safe fallback calculation
            return self._create_fallback_calculation(
                analysis_confidence, overall_risk_score, str(e)
            )
    


    
    def _validate_inputs(
        self, confidence: float, risk_score: float, 
        technical_signals: Optional[List], 
        market_conditions: Optional[Dict], 
        portfolio_context: Optional[Dict]
    ) -> None:
        """Validate all input parameters with detailed error messages."""
        errors = []
        
        # Validate confidence score
        if not isinstance(confidence, (int, float)):
            errors.append(f"Confidence must be numeric, got {type(confidence)}")
        elif not (0.0 <= confidence <= 1.0):
            errors.append(f"Confidence must be 0-1, got {confidence}")
        
        # Validate risk score
        if not isinstance(risk_score, (int, float)):
            errors.append(f"Risk score must be numeric, got {type(risk_score)}")
        elif not (0.0 <= risk_score <= 1.0):
            errors.append(f"Risk score must be 0-1, got {risk_score}")
        
        # Validate optional parameters
        if technical_signals is not None and not isinstance(technical_signals, list):
            errors.append(f"Technical signals must be list, got {type(technical_signals)}")
        
        if market_conditions is not None and not isinstance(market_conditions, dict):
            errors.append(f"Market conditions must be dict, got {type(market_conditions)}")
        
        if portfolio_context is not None and not isinstance(portfolio_context, dict):
            errors.append(f"Portfolio context must be dict, got {type(portfolio_context)}")
        
        if errors:
            raise ValueError("; ".join(errors))
    
    def _parse_market_conditions(self, conditions: Dict[str, Any]) -> MarketConditions:
        """Parse and validate market conditions with safe defaults."""
        try:
            return MarketConditions(
                volatility=max(0.01, min(2.0, float(conditions.get('volatility', 0.15)))),
                market_regime=conditions.get('market_regime', 'NORMAL'),
                liquidity_score=max(0.0, min(1.0, float(conditions.get('liquidity_score', 0.5)))),
                market_cap=conditions.get('market_cap'),
                trading_volume_24h=conditions.get('trading_volume_24h'),
                bid_ask_spread=conditions.get('bid_ask_spread'),
                market_stress_level=max(0.0, min(1.0, float(conditions.get('market_stress_level', 0.0))))
            )
        except Exception as e:
            logger.warning(f"Failed to parse market conditions: {e}, using defaults")
            return MarketConditions()
    
    def _parse_portfolio_context(self, context: Dict[str, Any]) -> PortfolioContext:
        """Parse and validate portfolio context with safe defaults."""
        try:
            return PortfolioContext(
                total_portfolio_value=max(1000.0, float(context.get('total_portfolio_value', 10000.0))),
                available_cash=max(0.0, float(context.get('available_cash', 5000.0))),
                current_position_count=max(0, int(context.get('current_position_count', 0))),
                max_positions=max(1, int(context.get('max_positions', 10))),
                portfolio_heat=max(0.0, min(100.0, float(context.get('portfolio_heat', 0.0)))),
                max_portfolio_heat=max(5.0, min(50.0, float(context.get('max_portfolio_heat', 20.0)))),
                recent_pnl_streak=context.get('recent_pnl_streak', []),
                correlation_exposure=context.get('correlation_exposure', {})
            )
        except Exception as e:
            logger.warning(f"Failed to parse portfolio context: {e}, using defaults")
            return PortfolioContext(
                total_portfolio_value=10000.0,
                available_cash=5000.0,
                current_position_count=0
            )
    
    def _select_optimal_method(
        self, confidence: float, risk_score: float,
        market_ctx: MarketConditions, portfolio_ctx: PortfolioContext
    ) -> SizingMethod:
        """Select optimal sizing method based on conditions."""
        try:
            # High confidence and low risk: Use Kelly Criterion
            if confidence > 0.8 and risk_score < 0.3 and len(portfolio_ctx.recent_pnl_streak) >= 10:
                return SizingMethod.KELLY_CRITERION
            
            # High volatility market: Use volatility-adjusted sizing
            if market_ctx.volatility > 0.3:
                return SizingMethod.VOLATILITY_ADJUSTED
            
            # High portfolio heat: Use conservative risk-based
            if portfolio_ctx.portfolio_heat > 15.0:
                return SizingMethod.RISK_BASED
            
            # Low confidence: Use confidence-weighted
            if confidence < 0.5:
                return SizingMethod.CONFIDENCE_WEIGHTED
            
            # Default: Risk-based sizing
            return SizingMethod.RISK_BASED
            
        except Exception as e:
            logger.warning(f"Method selection failed: {e}, using RISK_BASED")
            return SizingMethod.RISK_BASED
    
    def _calculate_base_size(
        self, method: SizingMethod, confidence: float, risk_score: float,
        market_ctx: MarketConditions, portfolio_ctx: PortfolioContext,
        technical_signals: List
    ) -> float:
        """Calculate base position size using specified method."""
        try:
            if method == SizingMethod.FIXED_PERCENT:
                return self.base_position_percent
            
            elif method == SizingMethod.RISK_BASED:
                # Risk-adjusted sizing: lower risk = larger position
                risk_factor = 1.0 - risk_score
                return self.base_position_percent * risk_factor * confidence
            
            elif method == SizingMethod.KELLY_CRITERION:
                return self._calculate_kelly_size(portfolio_ctx.recent_pnl_streak)
            
            elif method == SizingMethod.VOLATILITY_ADJUSTED:
                # Inverse volatility weighting
                vol_factor = 0.15 / max(0.05, market_ctx.volatility)
                return self.base_position_percent * vol_factor * confidence
            
            elif method == SizingMethod.CONFIDENCE_WEIGHTED:
                # Confidence-based scaling
                return self.base_position_percent * (confidence ** 2)
            
            elif method == SizingMethod.PORTFOLIO_HEAT:
                # Portfolio heat-adjusted sizing
                heat_factor = max(0.2, (self.max_portfolio_heat - portfolio_ctx.portfolio_heat) / self.max_portfolio_heat)
                return self.base_position_percent * heat_factor
            
            else:
                logger.warning(f"Unknown method {method}, using fixed percent")
                return self.base_position_percent
                
        except Exception as e:
            logger.error(f"Base size calculation failed for {method}: {e}")
            return self.base_position_percent
    
    def _calculate_kelly_size(self, pnl_history: List[float]) -> float:
        """Calculate Kelly Criterion position size from PnL history."""
        try:
            if len(pnl_history) < 10:
                logger.debug("Insufficient PnL history for Kelly calculation")
                return self.base_position_percent
            
            wins = [pnl for pnl in pnl_history if pnl > 0]
            losses = [abs(pnl) for pnl in pnl_history if pnl < 0]
            
            if not wins or not losses:
                return self.base_position_percent
            
            win_rate = len(wins) / len(pnl_history)
            avg_win = sum(wins) / len(wins)
            avg_loss = sum(losses) / len(losses)
            
            if avg_loss == 0 or win_rate < self.min_win_rate_for_kelly:
                return self.base_position_percent
            
            # Kelly fraction: f = (bp - q) / b
            # where b = avg_win/avg_loss, p = win_rate, q = 1 - win_rate
            b = avg_win / avg_loss
            kelly_fraction = (b * win_rate - (1 - win_rate)) / b
            
            # Apply safety multiplier and constraints
            kelly_size = max(0, kelly_fraction) * self.kelly_multiplier * 100
            return min(kelly_size, self.max_position_percent)
            
        except Exception as e:
            logger.error(f"Kelly calculation failed: {e}")
            return self.base_position_percent
    
    def _apply_adjustments(
        self, base_size: float, confidence: float, risk_score: float,
        market_ctx: MarketConditions, portfolio_ctx: PortfolioContext,
        technical_signals: List
    ) -> Dict[str, Any]:
        """Apply all position size adjustments and constraints."""
        warnings = []
        details = {'base_size': base_size}
        
        try:
            # Risk adjustment
            risk_factor = 1.0 - (risk_score * 0.5)  # High risk reduces size by up to 50%
            risk_adjusted = base_size * risk_factor
            details['risk_factor'] = risk_factor
            
            # Confidence adjustment
            confidence_factor = 0.5 + (confidence * 0.5)  # 50-100% based on confidence
            confidence_adjusted = risk_adjusted * confidence_factor
            details['confidence_factor'] = confidence_factor
            
            # Technical signal adjustment
            technical_factor = self._calculate_technical_factor(technical_signals)
            technical_adjusted = confidence_adjusted * technical_factor
            details['technical_factor'] = technical_factor
            
            # Volatility adjustment
            vol_factor = min(2.0, 0.15 / max(0.05, market_ctx.volatility))
            volatility_adjusted = technical_adjusted * vol_factor
            details['volatility_factor'] = vol_factor
            
            # Portfolio heat constraint
            available_heat = max(0, portfolio_ctx.max_portfolio_heat - portfolio_ctx.portfolio_heat)
            heat_constraint = min(1.0, available_heat / 10.0)  # Scale by 10% chunks
            portfolio_adjusted = volatility_adjusted * heat_constraint
            details['heat_constraint'] = heat_constraint
            
            if heat_constraint < 1.0:
                warnings.append(f"Position size reduced due to portfolio heat: {portfolio_ctx.portfolio_heat:.1f}%")
            
            # Apply absolute limits
            final_size = max(self.min_position_percent, min(self.max_position_percent, portfolio_adjusted))
            
            # Check if size was clamped
            if final_size != portfolio_adjusted:
                if final_size == self.min_position_percent:
                    warnings.append(f"Position size increased to minimum: {self.min_position_percent}%")
                else:
                    warnings.append(f"Position size capped at maximum: {self.max_position_percent}%")
            
            # Position count adjustment
            if portfolio_ctx.current_position_count >= portfolio_ctx.max_positions:
                final_size = 0.0
                warnings.append("Maximum position count reached, no new positions allowed")
            
            return {
                'final_size': final_size,
                'risk_adjusted': risk_adjusted,
                'confidence_adjusted': confidence_adjusted,
                'technical_adjusted': technical_adjusted,
                'volatility_adjusted': volatility_adjusted,
                'portfolio_adjusted': portfolio_adjusted,
                'details': details,
                'warnings': warnings
            }
            
        except Exception as e:
            logger.error(f"Adjustment calculation failed: {e}")
            return {
                'final_size': self.base_position_percent,
                'risk_adjusted': self.base_position_percent,
                'confidence_adjusted': self.base_position_percent,
                'technical_adjusted': self.base_position_percent,
                'volatility_adjusted': self.base_position_percent,
                'portfolio_adjusted': self.base_position_percent,
                'details': {'error': str(e)},
                'warnings': [f"Adjustment calculation failed: {e}"]
            }
    
    def _calculate_technical_factor(self, technical_signals: List) -> float:
        """Calculate technical analysis adjustment factor."""
        try:
            if not technical_signals:
                return 1.0
            
            # Count bullish vs bearish signals
            bullish = sum(1 for signal in technical_signals if getattr(signal, 'direction', '').upper() == 'BULLISH')
            bearish = sum(1 for signal in technical_signals if getattr(signal, 'direction', '').upper() == 'BEARISH')
            total = len(technical_signals)
            
            if total == 0:
                return 1.0
            
            # Calculate signal strength ratio
            net_bullish = (bullish - bearish) / total
            
            # Convert to multiplier (0.5 to 1.5 range)
            return 1.0 + (net_bullish * 0.5)
            
        except Exception as e:
            logger.warning(f"Technical factor calculation failed: {e}")
            return 1.0
    
    def _calculate_suggested_stop_loss(self, risk_score: float, volatility: float) -> float:
        """Calculate suggested stop loss percentage based on risk and volatility."""
        try:
            # Base stop loss of 10%, adjusted for risk and volatility
            base_stop = 10.0
            risk_adjustment = risk_score * 10.0  # Higher risk = wider stop
            volatility_adjustment = volatility * 20.0  # Higher vol = wider stop
            
            suggested_stop = base_stop + risk_adjustment + volatility_adjustment
            return min(25.0, max(5.0, suggested_stop))  # 5-25% range
            
        except Exception as e:
            logger.warning(f"Stop loss calculation failed: {e}")
            return 15.0  # Safe default
    
    def _calculate_usd_size(self, size_percent: float, portfolio_ctx: PortfolioContext) -> Optional[float]:
        """Calculate USD position size from percentage."""
        try:
            if portfolio_ctx.total_portfolio_value <= 0:
                return None
            return (size_percent / 100.0) * portfolio_ctx.total_portfolio_value
        except Exception:
            return None
    
    def _calculate_result_confidence(self, adjustments: Dict[str, Any]) -> float:
        """Calculate confidence in the sizing result."""
        try:
            # Base confidence starts at 0.8
            confidence = 0.8
            
            # Reduce confidence if many warnings
            warning_penalty = len(adjustments.get('warnings', [])) * 0.1
            confidence -= warning_penalty
            
            # Reduce confidence if large adjustments were made
            details = adjustments.get('details', {})
            base_size = details.get('base_size', 5.0)
            final_size = adjustments.get('final_size', 5.0)
            
            if base_size > 0:
                adjustment_ratio = abs(final_size - base_size) / base_size
                if adjustment_ratio > 0.5:  # More than 50% adjustment
                    confidence -= 0.2
            
            return max(0.1, min(1.0, confidence))
            
        except Exception:
            return 0.5  # Neutral confidence
    
    def _generate_rationale(
        self, method: SizingMethod, final_size: float, 
        confidence: float, risk_score: float
    ) -> str:
        """Generate human-readable rationale for the sizing decision."""
        try:
            rationale_parts = []
            
            # Method explanation
            method_explanations = {
                SizingMethod.FIXED_PERCENT: "Fixed percentage allocation for consistent sizing",
                SizingMethod.RISK_BASED: "Risk-adjusted sizing based on analysis risk score",
                SizingMethod.KELLY_CRITERION: "Kelly Criterion optimization based on historical performance",
                SizingMethod.VOLATILITY_ADJUSTED: "Volatility-adjusted sizing for risk normalization",
                SizingMethod.CONFIDENCE_WEIGHTED: "Confidence-weighted sizing based on analysis certainty",
                SizingMethod.PORTFOLIO_HEAT: "Portfolio heat-adjusted sizing for risk management"
            }
            
            rationale_parts.append(method_explanations.get(method.value, f"Using {method.value} methodology"))
            
            # Size description
            if final_size <= 1.0:
                size_desc = "Very small position due to high risk or low confidence"
            elif final_size <= 3.0:
                size_desc = "Small position with conservative sizing"
            elif final_size <= 7.0:
                size_desc = "Moderate position size balancing risk and opportunity"
            elif final_size <= 15.0:
                size_desc = "Large position reflecting high confidence or low risk"
            else:
                size_desc = "Maximum position size with strong conviction"
            
            rationale_parts.append(f"{size_desc} ({final_size:.1f}%)")
            
            # Risk and confidence context
            if risk_score > 0.7:
                rationale_parts.append("High risk analysis led to reduced position size")
            elif risk_score < 0.3:
                rationale_parts.append("Low risk assessment supports larger position")
            
            if confidence > 0.8:
                rationale_parts.append("High confidence in analysis")
            elif confidence < 0.4:
                rationale_parts.append("Low confidence led to conservative sizing")
            
            return ". ".join(rationale_parts) + "."
            
        except Exception as e:
            logger.warning(f"Rationale generation failed: {e}")
            return f"Position size calculated using {method.value}: {final_size:.1f}%"
    
    def _create_fallback_calculation(
        self, confidence: float, risk_score: float, error_message: str
    ) -> SizingCalculation:
        """Create safe fallback calculation when primary calculation fails."""
        logger.warning("Creating fallback position sizing calculation")
        
        # Very conservative fallback sizing
        fallback_size = min(self.base_position_percent * 0.5, 2.0)
        
        return SizingCalculation(
            recommended_size_percent=fallback_size,
            method_used=SizingMethod.FIXED_PERCENT,
            risk_adjusted_size=fallback_size,
            confidence_adjusted_size=fallback_size,
            technical_adjusted_size=fallback_size,
            volatility_adjusted_size=fallback_size,
            portfolio_adjusted_size=fallback_size,
            max_allowed_size=self.max_position_percent,
            min_allowed_size=self.min_position_percent,
            suggested_stop_loss_percent=15.0,
            max_risk_per_trade_percent=self.max_risk_per_trade,
            sizing_rationale=f"Conservative fallback sizing due to calculation error: {error_message}",
            calculation_confidence=0.3,
            warnings=[f"Primary calculation failed: {error_message}", "Using conservative fallback sizing"],
            calculation_details={
                'fallback_triggered': True,
                'original_confidence': confidence,
                'original_risk_score': risk_score,
                'error': error_message
            }
        )
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get position sizer performance statistics."""
        return {
            'calculation_count': self.calculation_count,
            'error_count': self.error_count,
            'error_rate': self.error_count / max(1, self.calculation_count),
            'last_calculation_time_seconds': self.last_calculation_time,
            'average_calculation_time': self.last_calculation_time  # Simplified
        }


# Export main classes and exceptions
__all__ = [
    'PositionSizer',
    'SizingCalculation',
    'SizingMethod',
    'PortfolioContext',
    'MarketConditions',
    'PositionSizerError'
]

logger.info("Smart Lane position sizing strategy module loaded successfully")