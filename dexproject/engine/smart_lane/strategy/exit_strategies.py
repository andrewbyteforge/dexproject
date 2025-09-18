"""
Smart Lane Exit Strategy Manager

Advanced exit strategy system that creates comprehensive exit plans
based on risk analysis, technical levels, and market conditions with
extensive error handling and logging throughout.

Path: engine/smart_lane/strategy/exit_strategies.py
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone

# Import from parent Smart Lane module
try:
    from .. import TechnicalSignal  # noqa: F401  (may be unused depending on call site)
except ImportError as e:  # pragma: no cover - fallback for isolated testing
    logging.error("Failed to import Smart Lane dependencies: %s", e)
    TechnicalSignal = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class ExitTrigger(Enum):
    """Types of exit triggers with detailed descriptions."""
    STOP_LOSS = "STOP_LOSS"               # Stop loss protection
    TAKE_PROFIT = "TAKE_PROFIT"           # Profit taking target
    TRAILING_STOP = "TRAILING_STOP"       # Trailing stop loss
    TIME_BASED = "TIME_BASED"             # Time-based exit
    TECHNICAL = "TECHNICAL"               # Technical indicator trigger
    RISK_MANAGEMENT = "RISK_MANAGEMENT"   # Risk management override
    VOLATILITY = "VOLATILITY"             # Volatility-based exit
    CORRELATION = "CORRELATION"           # Correlation breakdown
    NEWS_EVENT = "NEWS_EVENT"             # News/event driven exit
    EMERGENCY = "EMERGENCY"               # Emergency exit conditions


class ExitMethod(Enum):
    """Exit execution methods."""
    MARKET_ORDER = "MARKET_ORDER"         # Immediate market execution
    LIMIT_ORDER = "LIMIT_ORDER"           # Limit order execution
    SCALED_EXIT = "SCALED_EXIT"           # Scaled exit over time
    ICEBERG_ORDER = "ICEBERG_ORDER"       # Large order fragmentation
    TWAP = "TWAP"                         # Time-weighted average price
    VWAP = "VWAP"                         # Volume-weighted average price


class ExitPriority(Enum):
    """Exit priority levels."""
    EMERGENCY = 1
    RISK_MANAGEMENT = 2
    PROFIT_PROTECTION = 3
    STANDARD = 4
    OPPORTUNISTIC = 5


@dataclass
class ExitLevel:
    """
    Individual exit level definition with comprehensive configuration.

    Represents a single exit condition with all necessary parameters
    for execution and monitoring.
    """
    trigger_type: ExitTrigger
    trigger_price_percent: float              # % change from entry price
    position_percent: float                   # % of position to exit
    execution_method: ExitMethod = ExitMethod.MARKET_ORDER
    priority: ExitPriority = ExitPriority.STANDARD

    # Execution configuration
    conditions: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    enabled: bool = True

    # Timing parameters
    min_hold_time_minutes: Optional[int] = None
    max_hold_time_hours: Optional[int] = None
    cooldown_minutes: int = 0

    # Advanced parameters
    slippage_tolerance: float = 0.5           # Max slippage tolerance %
    partial_fill_threshold: float = 0.8       # Minimum fill ratio
    retry_attempts: int = 3                   # Execution retry count

    # Monitoring
    last_triggered: Optional[datetime] = None
    trigger_count: int = 0
    execution_history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ExitStrategy:
    """
    Complete exit strategy definition with all levels and configurations.
    """
    # Strategy identification
    strategy_name: str
    strategy_id: str = field(
        default_factory=lambda: f"exit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Exit levels
    exit_levels: List[ExitLevel] = field(default_factory=list)

    # Risk management
    max_hold_time_hours: Optional[int] = 48
    stop_loss_percent: Optional[float] = None
    take_profit_targets: List[float] = field(default_factory=list)

    # Trailing stop configuration
    trailing_stop_config: Dict[str, Any] = field(default_factory=dict)

    # Emergency conditions
    emergency_exit_conditions: List[Dict[str, Any]] = field(default_factory=list)

    # Strategy metadata
    strategy_rationale: str = "Automated exit strategy generation"
    risk_management_notes: List[str] = field(default_factory=list)
    confidence_level: float = 0.5

    # Performance tracking
    total_exits_executed: int = 0
    successful_exits: int = 0
    average_exit_slippage: float = 0.0
    strategy_pnl: float = 0.0

    # Status
    active: bool = True
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MarketConditions:
    """Market condition context for exit strategy creation."""
    volatility: float = 0.15
    liquidity_score: float = 0.5
    market_regime: str = "NORMAL"
    bid_ask_spread: float = 0.005
    market_stress_level: float = 0.0
    correlation_breakdown: bool = False


@dataclass
class PositionContext:
    """Position context for exit strategy customization."""
    entry_price: float
    current_price: float
    position_size_usd: float
    unrealized_pnl_percent: float = 0.0
    hold_time_hours: float = 0.0
    average_daily_volume: float = 0.0
    position_risk_score: float = 0.5


class ExitStrategyError(Exception):
    """Custom exception for exit strategy errors."""
    pass


class ExitStrategyManager:
    """
    Advanced exit strategy manager for Smart Lane trades.

    Creates comprehensive exit strategies with multiple levels,
    risk management rules, and adaptive execution methods.
    Features extensive error handling, logging, and performance tracking.
    """

    def __init__(self, config: Optional[Any] = None):
        """
        Initialize exit strategy manager with configuration.

        Args:
            config: Smart Lane configuration object
        """
        try:
            self.config = config

            # Default strategy parameters
            self.default_stop_loss_percent = 15.0
            self.default_take_profit_percent = 25.0
            self.max_exit_levels = 10
            self.min_position_for_scaling = 1000.0  # USD

            # Risk management limits
            self.max_stop_loss_percent = 50.0
            self.min_stop_loss_percent = 2.0
            self.max_take_profit_percent = 200.0
            self.min_take_profit_percent = 5.0

            # Performance tracking
            self.strategies_created = 0
            self.strategies_executed = 0
            self.error_count = 0
            self.average_creation_time = 0.0

            # Strategy templates
            self.strategy_templates = self._initialize_templates()

            logger.info(
                "Exit strategy manager initialized - default_stop: %.1f%%, "
                "default_profit: %.1f%%, max_levels: %d",
                self.default_stop_loss_percent,
                self.default_take_profit_percent,
                self.max_exit_levels,
            )
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to initialize exit strategy manager: %s", exc, exc_info=True)
            raise ExitStrategyError(f"Initialization failed: {exc}") from exc

    def create_exit_strategy(
        self,
        risk_score: float,
        technical_signals: Optional[List] = None,
        market_conditions: Optional[Dict[str, Any]] = None,
        position_context: Optional[Dict[str, Any]] = None,
        strategy_type: Optional[str] = None,
    ) -> ExitStrategy:
        """
        Create comprehensive exit strategy based on analysis and conditions.

        Args:
            risk_score: Overall risk assessment (0-1)
            technical_signals: List of technical analysis signals
            market_conditions: Market condition data
            position_context: Position-specific context
            strategy_type: Preferred strategy type
        """
        creation_start = datetime.now(timezone.utc)

        try:
            self.strategies_created += 1
            logger.debug(
                "Creating exit strategy #%d - risk_score: %.3f",
                self.strategies_created,
                float(risk_score),
            )

            # Input validation (non-fatal)
            try:
                self._validate_inputs(
                    risk_score, technical_signals, market_conditions, position_context
                )
            except ValueError as val_err:
                logger.warning("Input validation failed: %s", val_err)
                risk_score = max(0.0, min(1.0, float(risk_score)))

            # Parse contexts
            market_ctx = self._parse_market_conditions(market_conditions or {})
            position_ctx = self._parse_position_context(position_context or {})
            technical_signals = technical_signals or []

            # Determine strategy type
            if not strategy_type:
                strategy_type = self._select_strategy_type(
                    risk_score, market_ctx, position_ctx, technical_signals
                )

            logger.debug("Selected strategy type: %s", strategy_type)

            # Create base strategy (also stores temp calculations)
            strategy = self._create_base_strategy(
                strategy_type, risk_score, market_ctx, position_ctx
            )

            # Add exit levels
            exit_levels = self._create_exit_levels(
                risk_score, market_ctx, position_ctx, technical_signals
            )
            strategy.exit_levels = exit_levels

            # Configure trailing stops if applicable
            if self._should_use_trailing_stops(risk_score, market_ctx, position_ctx):
                strategy.trailing_stop_config = self._create_trailing_stop_config(
                    risk_score, market_ctx, position_ctx
                )

            # Add emergency conditions
            strategy.emergency_exit_conditions = self._create_emergency_conditions(
                risk_score, market_ctx, position_ctx
            )

            # Generate strategy rationale
            strategy.strategy_rationale = self._generate_strategy_rationale(
                strategy_type, risk_score, len(exit_levels), market_ctx
            )

            # Add risk management notes
            strategy.risk_management_notes = self._generate_risk_notes(
                risk_score, market_ctx, position_ctx
            )

            # Calculate confidence level
            strategy.confidence_level = self._calculate_strategy_confidence(
                risk_score, market_ctx, position_ctx, len(technical_signals)
            )

            # Validate final strategy
            validation_results = self._validate_strategy(strategy)
            if not validation_results["valid"]:
                logger.warning(
                    "Strategy validation issues: %s", validation_results["issues"]
                )
                strategy = self._fix_strategy_issues(
                    strategy, validation_results["issues"]
                )

            # Performance tracking
            creation_time = (datetime.now(timezone.utc) - creation_start).total_seconds()
            prev = max(0, self.strategies_created - 1)
            self.average_creation_time = (
                (self.average_creation_time * prev) + creation_time
            ) / max(1, self.strategies_created)

            logger.info(
                "Exit strategy created - type: %s, levels: %d, time: %.3fs, "
                "confidence: %.2f",
                strategy_type,
                len(strategy.exit_levels),
                creation_time,
                strategy.confidence_level,
            )
            return strategy

        except Exception as exc:  # pragma: no cover
            self.error_count += 1
            logger.error(
                "Exit strategy creation failed: %s (error #%d)",
                exc,
                self.error_count,
                exc_info=True,
            )
            return self._create_fallback_strategy(risk_score, str(exc))
        finally:
            # Always clear any temp calc storage
            self._clear_temp_calculations()

    def _validate_inputs(
        self,
        risk_score: float,
        technical_signals: Optional[List],
        market_conditions: Optional[Dict],
        position_context: Optional[Dict],
    ) -> None:
        """Validate all input parameters."""
        errors: List[str] = []

        # Validate risk score
        if not isinstance(risk_score, (int, float)):
            errors.append(f"Risk score must be numeric, got {type(risk_score)}")
        elif not (0.0 <= float(risk_score) <= 1.0):
            errors.append(f"Risk score must be 0-1, got {risk_score}")

        # Validate optional parameters
        if technical_signals is not None and not isinstance(technical_signals, list):
            errors.append(
                f"Technical signals must be list, got {type(technical_signals)}"
            )

        if market_conditions is not None and not isinstance(market_conditions, dict):
            errors.append(
                f"Market conditions must be dict, got {type(market_conditions)}"
            )

        if position_context is not None and not isinstance(position_context, dict):
            errors.append(
                f"Position context must be dict, got {type(position_context)}"
            )

        if errors:
            raise ValueError("; ".join(errors))

    def _parse_market_conditions(self, conditions: Dict[str, Any]) -> MarketConditions:
        """Parse and validate market conditions."""
        try:
            return MarketConditions(
                volatility=max(
                    0.01, min(2.0, float(conditions.get("volatility", 0.15)))
                ),
                liquidity_score=max(
                    0.0, min(1.0, float(conditions.get("liquidity_score", 0.5)))
                ),
                market_regime=str(conditions.get("market_regime", "NORMAL")),
                bid_ask_spread=max(
                    0.001, min(0.1, float(conditions.get("bid_ask_spread", 0.005)))
                ),
                market_stress_level=max(
                    0.0, min(1.0, float(conditions.get("market_stress_level", 0.0)))
                ),
                correlation_breakdown=bool(
                    conditions.get("correlation_breakdown", False)
                ),
            )
        except Exception as exc:
            logger.warning("Failed to parse market conditions: %s. Using defaults.", exc)
            return MarketConditions()

    def _parse_position_context(self, context: Dict[str, Any]) -> PositionContext:
        """Parse and validate position context."""
        try:
            entry_price = float(context.get("entry_price", 1.0))
            current_price = float(context.get("current_price", entry_price))

            return PositionContext(
                entry_price=entry_price,
                current_price=current_price,
                position_size_usd=max(0.0, float(context.get("position_size_usd", 1000.0))),
                unrealized_pnl_percent=float(context.get("unrealized_pnl_percent", 0.0)),
                hold_time_hours=max(0.0, float(context.get("hold_time_hours", 0.0))),
                average_daily_volume=max(
                    0.0, float(context.get("average_daily_volume", 100000.0))
                ),
                position_risk_score=max(
                    0.0, min(1.0, float(context.get("position_risk_score", 0.5)))
                ),
            )
        except Exception as exc:
            logger.warning("Failed to parse position context: %s. Using defaults.", exc)
            return PositionContext(
                entry_price=1.0, current_price=1.0, position_size_usd=1000.0
            )

    def _select_strategy_type(
        self,
        risk_score: float,
        market_ctx: MarketConditions,
        position_ctx: PositionContext,
        technical_signals: List,
    ) -> str:
        """Select optimal strategy type based on conditions."""
        try:
            if risk_score > 0.7:
                return "CONSERVATIVE"

            if market_ctx.volatility > 0.3:
                return "VOLATILITY_ADJUSTED"

            if position_ctx.position_size_usd > self.min_position_for_scaling:
                return "SCALED_EXIT"

            if len(technical_signals) >= 3:
                return "TECHNICAL_BASED"

            if market_ctx.market_regime == "BULL":
                return "AGGRESSIVE"

            if market_ctx.market_regime == "BEAR":
                return "DEFENSIVE"

            return "BALANCED"
        except Exception as exc:
            logger.warning("Strategy type selection failed: %s. Using BALANCED.", exc)
            return "BALANCED"

    def _create_base_strategy(
        self,
        strategy_type: str,
        risk_score: float,
        market_ctx: MarketConditions,
        position_ctx: PositionContext,
    ) -> ExitStrategy:
        """Create base strategy structure."""
        try:
            # Calculate base parameters
            stop_loss = self._calculate_stop_loss(risk_score, market_ctx)
            take_profits = self._calculate_take_profit_targets(
                risk_score, market_ctx, strategy_type
            )

            # Store for subsequent level creation (used by _create_exit_levels)
            self._store_temp_calculations(stop_loss, take_profits)

            return ExitStrategy(
                strategy_name=f"{strategy_type.title()} Exit Strategy",
                stop_loss_percent=stop_loss,
                take_profit_targets=take_profits,
                max_hold_time_hours=self._calculate_max_hold_time(risk_score, market_ctx),
                exit_levels=[],
                trailing_stop_config={},
                emergency_exit_conditions=[],
                strategy_rationale="",
                risk_management_notes=[],
                confidence_level=0.5,
            )
        except Exception as exc:
            logger.error("Base strategy creation failed: %s", exc)
            return ExitStrategy(strategy_name=f"{strategy_type} Strategy (Error Recovery)")

    def _calculate_stop_loss(self, risk_score: float, market_ctx: MarketConditions) -> float:
        """Calculate appropriate stop loss percentage (positive number)."""
        try:
            base_stop = self.default_stop_loss_percent
            risk_adjustment = risk_score * 10.0
            volatility_adjustment = market_ctx.volatility * 20.0
            stress_adjustment = market_ctx.market_stress_level * 5.0

            total_stop = base_stop + risk_adjustment + volatility_adjustment + stress_adjustment
            return max(self.min_stop_loss_percent, min(self.max_stop_loss_percent, total_stop))
        except Exception as exc:
            logger.warning("Stop loss calculation failed: %s", exc)
            return self.default_stop_loss_percent

    def _calculate_take_profit_targets(
        self, risk_score: float, market_ctx: MarketConditions, strategy_type: str
    ) -> List[float]:
        """Calculate take profit target levels (positive numbers)."""
        try:
            base_profit = self.default_take_profit_percent

            # Lower risk => push for higher targets
            risk_factor = 1.0 + (1.0 - risk_score) * 0.5
            adjusted_base = base_profit * risk_factor

            if strategy_type == "CONSERVATIVE":
                targets = [adjusted_base * 0.8]

            elif strategy_type == "AGGRESSIVE":
                targets = [adjusted_base * 0.6, adjusted_base * 1.2, adjusted_base * 2.0]

            elif strategy_type == "SCALED_EXIT":
                targets = [
                    adjusted_base * 0.5,
                    adjusted_base * 1.0,
                    adjusted_base * 1.5,
                    adjusted_base * 2.5,
                ]
            else:
                targets = [adjusted_base * 0.7, adjusted_base * 1.3]

            clipped = [
                max(self.min_take_profit_percent, min(self.max_take_profit_percent, t))
                for t in targets
            ]
            return sorted(clipped)
        except Exception as exc:
            logger.warning("Take profit calculation failed: %s", exc)
            return [self.default_take_profit_percent]

    def _calculate_max_hold_time(self, risk_score: float, market_ctx: MarketConditions) -> int:
        """Calculate maximum hold time in hours."""
        try:
            base_time = 48
            risk_factor = 1.0 - (risk_score * 0.5)
            volatility_factor = max(0.5, 1.0 - (market_ctx.volatility * 0.5))
            stress_factor = max(0.3, 1.0 - market_ctx.market_stress_level)

            adjusted_time = base_time * risk_factor * volatility_factor * stress_factor
            return max(4, min(168, int(adjusted_time)))
        except Exception as exc:
            logger.warning("Hold time calculation failed: %s", exc)
            return 48

    def _create_exit_levels(
        self,
        risk_score: float,
        market_ctx: MarketConditions,
        position_ctx: PositionContext,
        technical_signals: List,
    ) -> List[ExitLevel]:
        """Create all exit levels for the strategy."""
        try:
            levels: List[ExitLevel] = []

            # Stop loss level (highest priority)
            if hasattr(self, "_temp_stop_loss"):
                stop_loss = float(self._temp_stop_loss)
            else:
                stop_loss = self._calculate_stop_loss(risk_score, market_ctx)

            levels.append(
                ExitLevel(
                    trigger_type=ExitTrigger.STOP_LOSS,
                    trigger_price_percent=-stop_loss,
                    position_percent=100.0,
                    execution_method=ExitMethod.MARKET_ORDER,
                    priority=ExitPriority.RISK_MANAGEMENT,
                    description=f"Stop loss at -{stop_loss:.1f}%",
                    slippage_tolerance=1.0,
                    retry_attempts=5,
                )
            )

            # Take profit levels
            if hasattr(self, "_temp_take_profits"):
                take_profits = list(self._temp_take_profits)
            else:
                take_profits = self._calculate_take_profit_targets(
                    risk_score, market_ctx, "BALANCED"
                )

            if len(take_profits) == 1:
                position_percentages = [100.0]
            elif len(take_profits) == 2:
                position_percentages = [50.0, 50.0]
            elif len(take_profits) == 3:
                position_percentages = [30.0, 40.0, 30.0]
            else:
                percentage = 100.0 / max(1, len(take_profits))
                position_percentages = [percentage] * len(take_profits)

            for idx, (profit, pct) in enumerate(zip(take_profits, position_percentages)):
                levels.append(
                    ExitLevel(
                        trigger_type=ExitTrigger.TAKE_PROFIT,
                        trigger_price_percent=float(profit),
                        position_percent=float(pct),
                        execution_method=(
                            ExitMethod.LIMIT_ORDER if idx == 0 else ExitMethod.MARKET_ORDER
                        ),
                        priority=ExitPriority.PROFIT_PROTECTION,
                        description=f"Take profit {idx + 1} at +{float(profit):.1f}%",
                        slippage_tolerance=0.3,
                        retry_attempts=3,
                    )
                )

            # Time-based exit if holding too long
            max_hold_hours = self._calculate_max_hold_time(risk_score, market_ctx)
            if max_hold_hours < 168:
                levels.append(
                    ExitLevel(
                        trigger_type=ExitTrigger.TIME_BASED,
                        trigger_price_percent=0.0,
                        position_percent=100.0,
                        execution_method=ExitMethod.MARKET_ORDER,
                        priority=ExitPriority.RISK_MANAGEMENT,
                        description=f"Time-based exit after {max_hold_hours} hours",
                        max_hold_time_hours=max_hold_hours,
                        slippage_tolerance=0.8,
                    )
                )

            # Volatility-based exit for high volatility conditions
            if market_ctx.volatility > 0.4:
                levels.append(
                    ExitLevel(
                        trigger_type=ExitTrigger.VOLATILITY,
                        trigger_price_percent=0.0,
                        position_percent=100.0,
                        execution_method=ExitMethod.MARKET_ORDER,
                        priority=ExitPriority.RISK_MANAGEMENT,
                        description="Volatility spike emergency exit",
                        conditions={"volatility_threshold": market_ctx.volatility * 1.5},
                        slippage_tolerance=1.5,
                    )
                )

            logger.debug("Created %d exit levels", len(levels))
            return levels
        except Exception as exc:
            logger.error("Exit level creation failed: %s", exc)
            return [
                ExitLevel(
                    trigger_type=ExitTrigger.STOP_LOSS,
                    trigger_price_percent=-15.0,
                    position_percent=100.0,
                    description="Fallback stop loss",
                ),
                ExitLevel(
                    trigger_type=ExitTrigger.TAKE_PROFIT,
                    trigger_price_percent=25.0,
                    position_percent=100.0,
                    description="Fallback take profit",
                ),
            ]

    def _should_use_trailing_stops(
        self,
        risk_score: float,
        market_ctx: MarketConditions,
        position_ctx: PositionContext,
    ) -> bool:
        """Determine if trailing stops should be used."""
        try:
            if risk_score < 0.3 and market_ctx.market_regime == "BULL":
                return True
            if market_ctx.liquidity_score > 0.7 and position_ctx.position_size_usd > 5000:
                return True
            if market_ctx.volatility < 0.2 and market_ctx.market_stress_level < 0.3:
                return True
            return False
        except Exception:
            return False

    def _create_trailing_stop_config(
        self,
        risk_score: float,
        market_ctx: MarketConditions,
        position_ctx: PositionContext,
    ) -> Dict[str, Any]:
        """
        Create trailing stop configuration.

        Returns a dict with keys:
        - enabled
        - trailing_distance_percent
        - activation_threshold_percent
        - update_frequency_minutes
        - min_movement_percent
        - max_drawdown_reset
        """
        try:
            # Base trailing distance (8–15%) widens slightly with higher risk
            base_distance = 8.0 + (risk_score * 7.0)

            # Volatility adjustment widens the trail in choppy markets
            volatility_adjustment = market_ctx.volatility * 10.0

            trailing_distance = base_distance + volatility_adjustment
            trailing_distance = max(5.0, min(25.0, trailing_distance))

            # Activation threshold: when to begin trailing (usually below the
            # trailing distance so it can actually engage)
            activation_threshold = max(5.0, min(20.0, trailing_distance * 0.6))

            return {
                "enabled": True,
                "trailing_distance_percent": trailing_distance,
                "activation_threshold_percent": activation_threshold,
                "update_frequency_minutes": 5,
                "min_movement_percent": 1.0,
                "max_drawdown_reset": 0.5,
            }
        except Exception as exc:
            logger.warning("Trailing stop config creation failed: %s", exc)
            return {
                "enabled": False,
                "trailing_distance_percent": 15.0,
                "activation_threshold_percent": 10.0,
                "update_frequency_minutes": 5,
                "min_movement_percent": 1.0,
                "max_drawdown_reset": 0.5,
            }

    def _create_emergency_conditions(
        self,
        risk_score: float,
        market_ctx: MarketConditions,
        position_ctx: PositionContext,
    ) -> List[Dict[str, Any]]:
        """Create emergency exit conditions."""
        try:
            conditions: List[Dict[str, Any]] = []

            conditions.append(
                {
                    "name": "market_crash",
                    "description": "Emergency exit on market crash",
                    "trigger": "price_drop_percent",
                    "threshold": -20.0,
                    "time_window_minutes": 15,
                    "action": "immediate_market_exit",
                    "priority": ExitPriority.EMERGENCY.value,
                }
            )

            if market_ctx.liquidity_score < 0.3:
                conditions.append(
                    {
                        "name": "liquidity_crisis",
                        "description": "Exit on liquidity shortage",
                        "trigger": "bid_ask_spread_percent",
                        "threshold": 2.0,
                        "action": "gradual_exit",
                        "priority": ExitPriority.RISK_MANAGEMENT.value,
                    }
                )

            if hasattr(position_ctx, "correlation_assets") and getattr(
                position_ctx, "correlation_assets"
            ):
                conditions.append(
                    {
                        "name": "correlation_breakdown",
                        "description": "Exit on correlation breakdown",
                        "trigger": "correlation_coefficient",
                        "threshold": 0.3,
                        "action": "scaled_exit",
                        "priority": ExitPriority.RISK_MANAGEMENT.value,
                    }
                )

            if risk_score > 0.6:
                conditions.append(
                    {
                        "name": "risk_escalation",
                        "description": "Risk score deterioration exit",
                        "trigger": "risk_score_increase",
                        "threshold": 0.2,
                        "action": "immediate_exit",
                        "priority": ExitPriority.RISK_MANAGEMENT.value,
                    }
                )

            return conditions
        except Exception as exc:
            logger.warning("Emergency conditions creation failed: %s", exc)
            return [
                {
                    "name": "fallback_emergency",
                    "description": "Fallback emergency exit",
                    "trigger": "price_drop_percent",
                    "threshold": -25.0,
                    "action": "immediate_market_exit",
                }
            ]

    def _generate_strategy_rationale(
        self,
        strategy_type: str,
        risk_score: float,
        exit_level_count: int,
        market_ctx: MarketConditions,
    ) -> str:
        """Generate human-readable strategy rationale."""
        try:
            parts: List[str] = []

            type_explanations = {
                "CONSERVATIVE": "Conservative approach prioritizing capital preservation",
                "AGGRESSIVE": "Aggressive strategy maximizing profit potential",
                "BALANCED": "Balanced approach between risk and reward",
                "VOLATILITY_ADJUSTED": "Volatility-adjusted strategy for unstable markets",
                "SCALED_EXIT": "Scaled exit strategy for large positions",
                "TECHNICAL_BASED": "Technical analysis-driven exit strategy",
                "DEFENSIVE": "Defensive strategy for bearish conditions",
            }
            parts.append(type_explanations.get(strategy_type, f"{strategy_type} exit strategy"))

            if risk_score > 0.7:
                parts.append("High risk analysis necessitates tight risk controls")
            elif risk_score < 0.3:
                parts.append("Low risk assessment allows for more aggressive targets")
            else:
                parts.append("Moderate risk level supports balanced exit approach")

            if market_ctx.volatility > 0.3:
                parts.append("High market volatility requires wider stops and dynamic exits")
            elif market_ctx.market_stress_level > 0.5:
                parts.append("Market stress conditions favor defensive exit positioning")

            if exit_level_count >= 5:
                parts.append("Multiple exit levels provide granular position management")
            elif exit_level_count <= 2:
                parts.append("Simplified exit structure for clear decision making")

            return ". ".join(parts) + "."
        except Exception as exc:
            logger.warning("Rationale generation failed: %s", exc)
            return (
                f"{strategy_type} exit strategy with {exit_level_count} "
                f"levels based on {risk_score:.2f} risk score."
            )

    def _generate_risk_notes(
        self,
        risk_score: float,
        market_ctx: MarketConditions,
        position_ctx: PositionContext,
    ) -> List[str]:
        """Generate risk management notes."""
        try:
            notes: List[str] = []

            if risk_score > 0.8:
                notes.append(
                    "⚠️ Very high risk - monitor position closely and consider reducing size"
                )
            elif risk_score > 0.6:
                notes.append(
                    "⚠️ High risk detected - maintain strict discipline on exit levels"
                )

            if market_ctx.volatility > 0.4:
                notes.append("⚠️ High volatility environment - expect increased slippage")

            if market_ctx.liquidity_score < 0.3:
                notes.append("⚠️ Low liquidity - use limit orders when possible")

            if market_ctx.market_stress_level > 0.6:
                notes.append("⚠️ Market stress detected - consider reducing position size")

            if position_ctx.position_size_usd > 10000:
                notes.append(
                    "💡 Large position - consider using scaled exits to minimize market impact"
                )

            if position_ctx.unrealized_pnl_percent > 20:
                notes.append(
                    "💡 Significant unrealized gains - consider taking partial profits"
                )
            elif position_ctx.unrealized_pnl_percent < -10:
                notes.append("⚠️ Unrealized losses - monitor stop loss levels closely")

            notes.append("📋 Always honor stop losses - emotions can override logic")
            notes.append("📋 Review and adjust exit levels as market conditions change")

            return notes
        except Exception as exc:
            logger.warning("Risk notes generation failed: %s", exc)
            return ["📋 Monitor position regularly and follow exit strategy discipline"]

    def _calculate_strategy_confidence(
        self,
        risk_score: float,
        market_ctx: MarketConditions,
        position_ctx: PositionContext,
        signal_count: int,
    ) -> float:
        """Calculate confidence in the exit strategy (0.1–1.0)."""
        try:
            confidence = 0.7

            if 0.3 <= risk_score <= 0.7:
                confidence += 0.1
            elif risk_score < 0.2 or risk_score > 0.8:
                confidence += 0.15

            if market_ctx.liquidity_score > 0.7:
                confidence += 0.1

            if market_ctx.volatility < 0.2:
                confidence += 0.05
            elif market_ctx.volatility > 0.5:
                confidence -= 0.1

            if signal_count >= 3:
                confidence += 0.1
            elif signal_count == 0:
                confidence -= 0.05

            confidence -= market_ctx.market_stress_level * 0.2

            return max(0.1, min(1.0, confidence))
        except Exception as exc:
            logger.warning("Confidence calculation failed: %s", exc)
            return 0.5

    def _validate_strategy(self, strategy: ExitStrategy) -> Dict[str, Any]:
        """Validate the created strategy for issues."""
        try:
            issues: List[str] = []
            valid = True

            if not strategy.exit_levels:
                issues.append("No exit levels defined")
                valid = False

            has_stop_loss = any(
                level.trigger_type == ExitTrigger.STOP_LOSS for level in strategy.exit_levels
            )
            if not has_stop_loss:
                issues.append("No stop loss level defined")
                valid = False

            profit_levels = [
                level for level in strategy.exit_levels
                if level.trigger_type == ExitTrigger.TAKE_PROFIT
            ]
            if profit_levels:
                total_percent = sum(level.position_percent for level in profit_levels)
                if abs(total_percent - 100.0) > 1.0:
                    issues.append(
                        f"Take profit percentages sum to {total_percent:.2f}%, not 100%"
                    )

            for stop in (l for l in strategy.exit_levels if l.trigger_type == ExitTrigger.STOP_LOSS):
                if stop.trigger_price_percent > -2.0 or stop.trigger_price_percent < -50.0:
                    issues.append(
                        f"Stop loss {stop.trigger_price_percent}% outside reasonable range"
                    )

            for profit in profit_levels:
                if profit.trigger_price_percent < 2.0 or profit.trigger_price_percent > 500.0:
                    issues.append(
                        f"Take profit {profit.trigger_price_percent}% outside reasonable range"
                    )

            if strategy.max_hold_time_hours and strategy.max_hold_time_hours < 1:
                issues.append("Max hold time too short")

            return {"valid": valid, "issues": issues}
        except Exception as exc:
            logger.error("Strategy validation failed: %s", exc)
            return {"valid": False, "issues": [f"Validation error: {exc}"]}

    def _fix_strategy_issues(self, strategy: ExitStrategy, issues: List[str]) -> ExitStrategy:
        """Attempt to fix identified strategy issues."""
        try:
            logger.info("Fixing %d strategy issues", len(issues))

            for issue in issues:
                if "No exit levels defined" in issue:
                    strategy.exit_levels = [
                        ExitLevel(
                            trigger_type=ExitTrigger.STOP_LOSS,
                            trigger_price_percent=-15.0,
                            position_percent=100.0,
                            description="Emergency stop loss",
                        ),
                        ExitLevel(
                            trigger_type=ExitTrigger.TAKE_PROFIT,
                            trigger_price_percent=25.0,
                            position_percent=100.0,
                            description="Emergency take profit",
                        ),
                    ]

                elif "No stop loss level defined" in issue:
                    strategy.exit_levels.append(
                        ExitLevel(
                            trigger_type=ExitTrigger.STOP_LOSS,
                            trigger_price_percent=-15.0,
                            position_percent=100.0,
                            description="Added stop loss",
                        )
                    )

                elif "percentages sum to" in issue:
                    profit_levels = [
                        l for l in strategy.exit_levels
                        if l.trigger_type == ExitTrigger.TAKE_PROFIT
                    ]
                    if profit_levels:
                        equal_percent = 100.0 / len(profit_levels)
                        for lvl in profit_levels:
                            lvl.position_percent = equal_percent

            logger.debug("Strategy issues fixed")
            return strategy
        except Exception as exc:
            logger.error("Strategy fix failed: %s", exc)
            return strategy

    def _create_fallback_strategy(self, risk_score: float, error_message: str) -> ExitStrategy:
        """Create safe fallback strategy when primary creation fails."""
        logger.warning("Creating fallback exit strategy due to error: %s", error_message)

        stop_loss = min(-20.0, -(self.default_stop_loss_percent + risk_score * 10.0))
        take_profit = max(15.0, self.default_take_profit_percent - risk_score * 5.0)

        return ExitStrategy(
            strategy_name="Fallback Exit Strategy",
            exit_levels=[
                ExitLevel(
                    trigger_type=ExitTrigger.STOP_LOSS,
                    trigger_price_percent=stop_loss,
                    position_percent=100.0,
                    execution_method=ExitMethod.MARKET_ORDER,
                    priority=ExitPriority.EMERGENCY,
                    description=f"Fallback stop loss at {stop_loss:.1f}%",
                ),
                ExitLevel(
                    trigger_type=ExitTrigger.TAKE_PROFIT,
                    trigger_price_percent=take_profit,
                    position_percent=100.0,
                    execution_method=ExitMethod.LIMIT_ORDER,
                    priority=ExitPriority.STANDARD,
                    description=f"Fallback take profit at +{take_profit:.1f}%",
                ),
                ExitLevel(
                    trigger_type=ExitTrigger.TIME_BASED,
                    trigger_price_percent=0.0,
                    position_percent=100.0,
                    execution_method=ExitMethod.MARKET_ORDER,
                    priority=ExitPriority.RISK_MANAGEMENT,
                    description="24-hour time-based exit",
                    max_hold_time_hours=24,
                ),
            ],
            max_hold_time_hours=24,
            stop_loss_percent=-stop_loss,
            take_profit_targets=[take_profit],
            trailing_stop_config={"enabled": False},
            emergency_exit_conditions=[],
            strategy_rationale=(
                "Conservative fallback strategy due to creation error: "
                f"{error_message}"
            ),
            risk_management_notes=[
                f"⚠️ Fallback strategy created due to error: {error_message}",
                "📋 Monitor position extra carefully",
                "📋 Consider manual exit if conditions deteriorate",
            ],
            confidence_level=0.3,
        )

    def _initialize_templates(self) -> Dict[str, Dict[str, Any]]:
        """Initialize strategy templates for common scenarios."""
        try:
            return {
                "CONSERVATIVE": {
                    "stop_loss_multiplier": 0.8,
                    "take_profit_multiplier": 0.7,
                    "max_levels": 3,
                    "use_trailing": False,
                },
                "AGGRESSIVE": {
                    "stop_loss_multiplier": 1.2,
                    "take_profit_multiplier": 1.8,
                    "max_levels": 6,
                    "use_trailing": True,
                },
                "BALANCED": {
                    "stop_loss_multiplier": 1.0,
                    "take_profit_multiplier": 1.0,
                    "max_levels": 4,
                    "use_trailing": True,
                },
                "SCALPING": {
                    "stop_loss_multiplier": 0.5,
                    "take_profit_multiplier": 0.6,
                    "max_levels": 2,
                    "use_trailing": False,
                    "max_hold_hours": 4,
                },
            }
        except Exception as exc:
            logger.error("Template initialization failed: %s", exc)
            return {}

    def get_strategy_performance(self, strategy_id: str) -> Dict[str, Any]:
        """Get performance statistics for a specific strategy."""
        try:
            # Stub: production should query persistent storage
            return {
                "strategy_id": strategy_id,
                "total_executions": 0,
                "successful_executions": 0,
                "average_slippage": 0.0,
                "total_pnl": 0.0,
                "success_rate": 0.0,
                "average_hold_time": 0.0,
            }
        except Exception as exc:
            logger.error("Performance retrieval failed for %s: %s", strategy_id, exc)
            return {"error": str(exc)}

    def get_manager_stats(self) -> Dict[str, Any]:
        """Get exit strategy manager performance statistics."""
        return {
            "strategies_created": self.strategies_created,
            "strategies_executed": self.strategies_executed,
            "error_count": self.error_count,
            "error_rate": self.error_count / max(1, self.strategies_created),
            "average_creation_time_seconds": self.average_creation_time,
            "available_templates": len(self.strategy_templates),
        }

    # --- Temp calc sharing across methods ---------------------------------

    def _store_temp_calculations(self, stop_loss: float, take_profits: List[float]) -> None:
        """Temporarily store calculations for use across methods."""
        self._temp_stop_loss = float(stop_loss)
        self._temp_take_profits = list(take_profits)

    def _clear_temp_calculations(self) -> None:
        """Clear temporary calculation storage."""
        if hasattr(self, "_temp_stop_loss"):
            delattr(self, "_temp_stop_loss")
        if hasattr(self, "_temp_take_profits"):
            delattr(self, "_temp_take_profits")


# Export main classes and exceptions
__all__ = [
    "ExitStrategyManager",
    "ExitStrategy",
    "ExitLevel",
    "ExitTrigger",
    "ExitMethod",
    "ExitPriority",
    "MarketConditions",
    "PositionContext",
    "ExitStrategyError",
]

logger.info("Smart Lane exit strategy management module loaded successfully")
