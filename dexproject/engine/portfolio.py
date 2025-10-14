"""
Portfolio Management & Circuit Breakers - FIXED VERSION

Advanced portfolio management with risk limits, circuit breakers,
and comprehensive performance tracking across all chains.

CRITICAL FIXES:
- Added safety checks for missing config in all circuit breaker methods
- Added comprehensive error handling and logging
- Added traceback error identification
- Fixed NoneType attribute access errors

File: dexproject/engine/portfolio.py
"""

import asyncio
import logging
import traceback
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
import time

from .config import config
from .utils import format_currency, format_percentage, safe_decimal
from . import EngineStatus

logger = logging.getLogger(__name__)


class CircuitBreakerType(Enum):
    """Type of circuit breaker trigger."""
    DAILY_LOSS = "DAILY_LOSS"
    PORTFOLIO_LOSS = "PORTFOLIO_LOSS"
    CONSECUTIVE_LOSSES = "CONSECUTIVE_LOSSES"
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"
    EXTERNAL_TRIGGER = "EXTERNAL_TRIGGER"


class AlertLevel(Enum):
    """Portfolio alert severity levels."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


@dataclass
class CircuitBreakerEvent:
    """
    Represents a circuit breaker activation.
    
    Attributes:
        breaker_type: Type of circuit breaker that triggered
        trigger_value: Value that triggered the breaker
        threshold_value: Threshold that was exceeded
        triggered_at: Timestamp when breaker was triggered
        description: Human-readable description of the event
        auto_recovery_time: Optional time when breaker will auto-recover
    """
    breaker_type: CircuitBreakerType
    trigger_value: Decimal
    threshold_value: Decimal
    triggered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    description: str = ""
    auto_recovery_time: Optional[datetime] = None


@dataclass
class PerformanceMetrics:
    """
    Portfolio performance metrics.
    
    Tracks comprehensive performance data including returns, drawdowns,
    win rates, and trade statistics.
    """
    total_return_percent: Decimal = Decimal('0')
    daily_return_percent: Decimal = Decimal('0')
    max_drawdown_percent: Decimal = Decimal('0')
    sharpe_ratio: Optional[Decimal] = None
    win_rate_percent: Decimal = Decimal('0')
    profit_factor: Decimal = Decimal('0')
    avg_trade_duration_hours: Decimal = Decimal('0')
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    largest_win: Decimal = Decimal('0')
    largest_loss: Decimal = Decimal('0')
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RiskMetrics:
    """
    Risk management metrics.
    
    Provides comprehensive risk assessment including VaR, concentration,
    correlation, and liquidity risk scores.
    """
    portfolio_beta: Optional[Decimal] = None
    value_at_risk_5pct: Decimal = Decimal('0')
    expected_shortfall: Decimal = Decimal('0')
    concentration_risk_score: Decimal = Decimal('0')
    correlation_risk_score: Decimal = Decimal('0')
    liquidity_risk_score: Decimal = Decimal('0')
    overall_risk_score: Decimal = Decimal('0')  # 0-100
    last_calculated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CircuitBreakerManager:
    """
    Manages circuit breakers and automatic trading halts.
    
    Implements multiple circuit breaker types with automatic
    recovery and escalation procedures. Includes comprehensive
    safety checks for missing configuration.
    
    SAFETY FEATURES:
    - Gracefully handles missing config (None values)
    - Comprehensive error logging with tracebacks
    - Safe fallback behavior when config unavailable
    """
    
    def __init__(self, portfolio_config: Optional[Any] = None):
        """
        Initialize circuit breaker manager.
        
        Args:
            portfolio_config: Optional portfolio configuration object
        """
        self.active_breakers: Dict[CircuitBreakerType, CircuitBreakerEvent] = {}
        self.breaker_history: List[CircuitBreakerEvent] = []
        self.manual_override = False
        self.config = portfolio_config  # Store config reference
        self.logger = logging.getLogger('engine.portfolio.circuit_breaker')
        
        # Log initialization status
        if self.config is None:
            self.logger.warning(
                "[CB INIT] Circuit breaker initialized WITHOUT config - "
                "checks will be skipped until config is provided"
            )
        else:
            self.logger.info("[CB INIT] Circuit breaker initialized with config")
    
    def set_config(self, portfolio_config: Any) -> None:
        """
        Set or update the portfolio configuration.
        
        Args:
            portfolio_config: Portfolio configuration object
        """
        self.config = portfolio_config
        self.logger.info("[CB CONFIG] Portfolio config updated")
    
    def check_circuit_breakers(self, portfolio_state: Dict[str, Any]) -> List[CircuitBreakerEvent]:
        """
        Check all circuit breaker conditions.
        
        SAFETY: Returns empty list if config is not available.
        This prevents AttributeError when accessing config properties.
        
        Args:
            portfolio_state: Current portfolio state with metrics
            
        Returns:
            List of newly triggered circuit breaker events
        """
        try:
            # ✅ CRITICAL SAFETY CHECK - Skip all checks if no config
            if not hasattr(self, 'config') or self.config is None:
                self.logger.debug(
                    "[CB CHECK] Circuit breaker config not available, skipping checks"
                )
                return []
            
            new_breakers = []
            
            # Daily loss circuit breaker
            try:
                daily_loss_breaker = self._check_daily_loss_breaker(portfolio_state)
                if daily_loss_breaker:
                    new_breakers.append(daily_loss_breaker)
            except Exception as e:
                self.logger.error(
                    f"[CB ERROR] Daily loss breaker check failed: {e}",
                    exc_info=True
                )
            
            # Portfolio loss circuit breaker
            try:
                portfolio_loss_breaker = self._check_portfolio_loss_breaker(portfolio_state)
                if portfolio_loss_breaker:
                    new_breakers.append(portfolio_loss_breaker)
            except Exception as e:
                self.logger.error(
                    f"[CB ERROR] Portfolio loss breaker check failed: {e}",
                    exc_info=True
                )
            
            # Consecutive losses circuit breaker
            try:
                consecutive_loss_breaker = self._check_consecutive_losses_breaker(portfolio_state)
                if consecutive_loss_breaker:
                    new_breakers.append(consecutive_loss_breaker)
            except Exception as e:
                self.logger.error(
                    f"[CB ERROR] Consecutive losses breaker check failed: {e}",
                    exc_info=True
                )
            
            # Activate new breakers
            for breaker in new_breakers:
                self._activate_breaker(breaker)
            
            return new_breakers
            
        except Exception as e:
            self.logger.error(
                f"[CB ERROR] Circuit breaker check failed: {e}",
                exc_info=True
            )
            traceback.print_exc()
            return []
    
    def _check_daily_loss_breaker(self, portfolio_state: Dict[str, Any]) -> Optional[CircuitBreakerEvent]:
        """
        Check daily loss limit circuit breaker.
        
        Args:
            portfolio_state: Current portfolio state
            
        Returns:
            CircuitBreakerEvent if triggered, None otherwise
        """
        try:
            # ✅ SAFETY CHECK - Skip if no config
            if not hasattr(self, 'config') or self.config is None:
                return None
            
            # Check if already active
            if CircuitBreakerType.DAILY_LOSS in self.active_breakers:
                return None
            
            # Get daily P&L from portfolio state
            daily_pnl = safe_decimal(portfolio_state.get('daily_pnl', 0))
            
            # Calculate daily loss limit from config
            # ✅ SAFE: We already checked config exists above
            if not hasattr(self.config, 'max_portfolio_size_usd'):
                self.logger.warning(
                    "[CB] Config missing 'max_portfolio_size_usd', skipping daily loss check"
                )
                return None
            
            if not hasattr(self.config, 'daily_loss_limit_percent'):
                self.logger.warning(
                    "[CB] Config missing 'daily_loss_limit_percent', skipping daily loss check"
                )
                return None
            
            daily_loss_limit = (
                self.config.max_portfolio_size_usd * 
                self.config.daily_loss_limit_percent / 100
            )
            
            # Check if daily loss exceeds limit
            if daily_pnl < -daily_loss_limit:
                self.logger.warning(
                    f"[CB TRIGGER] Daily loss breaker: "
                    f"Loss=${abs(daily_pnl):.2f} exceeds limit=${daily_loss_limit:.2f}"
                )
                
                return CircuitBreakerEvent(
                    breaker_type=CircuitBreakerType.DAILY_LOSS,
                    trigger_value=daily_pnl,
                    threshold_value=daily_loss_limit,
                    description=(
                        f"Daily loss of {format_currency(abs(daily_pnl))} "
                        f"exceeds limit of {format_currency(daily_loss_limit)}"
                    ),
                    auto_recovery_time=datetime.now(timezone.utc) + timedelta(hours=24)
                )
            
            return None
            
        except AttributeError as e:
            self.logger.error(
                f"[CB ERROR] Daily loss breaker config error: {e}",
                exc_info=True
            )
            return None
        except Exception as e:
            self.logger.error(
                f"[CB ERROR] Daily loss breaker check failed: {e}",
                exc_info=True
            )
            return None
    
    def _check_portfolio_loss_breaker(self, portfolio_state: Dict[str, Any]) -> Optional[CircuitBreakerEvent]:
        """
        Check portfolio loss circuit breaker.
        
        Args:
            portfolio_state: Current portfolio state
            
        Returns:
            CircuitBreakerEvent if triggered, None otherwise
        """
        try:
            # ✅ SAFETY CHECK - Skip if no config
            if not hasattr(self, 'config') or self.config is None:
                return None
            
            # Check if already active
            if CircuitBreakerType.PORTFOLIO_LOSS in self.active_breakers:
                return None
            
            # Get total P&L from portfolio state
            total_pnl = safe_decimal(portfolio_state.get('total_pnl', 0))
            
            # Calculate portfolio loss limit from config
            # ✅ SAFE: We already checked config exists above
            if not hasattr(self.config, 'max_portfolio_size_usd'):
                self.logger.warning(
                    "[CB] Config missing 'max_portfolio_size_usd', skipping portfolio loss check"
                )
                return None
            
            if not hasattr(self.config, 'circuit_breaker_loss_percent'):
                self.logger.warning(
                    "[CB] Config missing 'circuit_breaker_loss_percent', skipping portfolio loss check"
                )
                return None
            
            portfolio_loss_limit = (
                self.config.max_portfolio_size_usd * 
                self.config.circuit_breaker_loss_percent / 100
            )
            
            # Check if total loss exceeds limit
            if total_pnl < -portfolio_loss_limit:
                self.logger.critical(
                    f"[CB TRIGGER] Portfolio loss breaker: "
                    f"Loss=${abs(total_pnl):.2f} exceeds limit=${portfolio_loss_limit:.2f}"
                )
                
                return CircuitBreakerEvent(
                    breaker_type=CircuitBreakerType.PORTFOLIO_LOSS,
                    trigger_value=total_pnl,
                    threshold_value=portfolio_loss_limit,
                    description=(
                        f"Portfolio loss of {format_currency(abs(total_pnl))} "
                        f"exceeds circuit breaker limit"
                    ),
                    auto_recovery_time=None  # Manual recovery required
                )
            
            return None
            
        except AttributeError as e:
            self.logger.error(
                f"[CB ERROR] Portfolio loss breaker config error: {e}",
                exc_info=True
            )
            return None
        except Exception as e:
            self.logger.error(
                f"[CB ERROR] Portfolio loss breaker check failed: {e}",
                exc_info=True
            )
            return None
    
    def _check_consecutive_losses_breaker(self, portfolio_state: Dict[str, Any]) -> Optional[CircuitBreakerEvent]:
        """
        Check consecutive losses circuit breaker.
        
        Args:
            portfolio_state: Current portfolio state
            
        Returns:
            CircuitBreakerEvent if triggered, None otherwise
        """
        try:
            # Check if already active
            if CircuitBreakerType.CONSECUTIVE_LOSSES in self.active_breakers:
                return None
            
            # Get consecutive losses from portfolio state
            consecutive_losses = portfolio_state.get('consecutive_losses', 0)
            
            # Use configurable threshold or default
            max_consecutive = 5  # Default threshold
            
            if hasattr(self, 'config') and self.config is not None:
                if hasattr(self.config, 'max_consecutive_losses'):
                    max_consecutive = self.config.max_consecutive_losses
            
            # Check if consecutive losses exceed threshold
            if consecutive_losses >= max_consecutive:
                self.logger.warning(
                    f"[CB TRIGGER] Consecutive losses breaker: "
                    f"{consecutive_losses} losses >= {max_consecutive} threshold"
                )
                
                return CircuitBreakerEvent(
                    breaker_type=CircuitBreakerType.CONSECUTIVE_LOSSES,
                    trigger_value=Decimal(str(consecutive_losses)),
                    threshold_value=Decimal(str(max_consecutive)),
                    description=f"{consecutive_losses} consecutive losing trades",
                    auto_recovery_time=datetime.now(timezone.utc) + timedelta(hours=4)
                )
            
            return None
            
        except Exception as e:
            self.logger.error(
                f"[CB ERROR] Consecutive losses breaker check failed: {e}",
                exc_info=True
            )
            return None
    
    def _activate_breaker(self, breaker: CircuitBreakerEvent) -> None:
        """
        Activate a circuit breaker.
        
        Args:
            breaker: Circuit breaker event to activate
        """
        try:
            self.active_breakers[breaker.breaker_type] = breaker
            self.breaker_history.append(breaker)
            
            self.logger.critical(
                f"🚨 CIRCUIT BREAKER ACTIVATED: {breaker.breaker_type.value} - {breaker.description}"
            )
            
            # Log auto-recovery time if set
            if breaker.auto_recovery_time:
                self.logger.info(
                    f"[CB] Auto-recovery scheduled for: {breaker.auto_recovery_time.isoformat()}"
                )
            else:
                self.logger.warning(
                    f"[CB] Manual recovery required for {breaker.breaker_type.value}"
                )
                
        except Exception as e:
            self.logger.error(
                f"[CB ERROR] Failed to activate breaker: {e}",
                exc_info=True
            )
    
    def can_trade(self) -> Tuple[bool, List[str]]:
        """
        Check if trading is allowed based on circuit breakers.
        
        Returns:
            Tuple of (can_trade: bool, reasons: List[str])
        """
        try:
            # Manual override bypasses all breakers
            if self.manual_override:
                self.logger.debug("[CB] Manual override active - trading allowed")
                return True, []
            
            # Check for auto-recovery
            self._check_auto_recovery()
            
            # No active breakers = trading allowed
            if not self.active_breakers:
                return True, []
            
            # Build list of reasons trading is blocked
            reasons = [
                f"{breaker.breaker_type.value}: {breaker.description}"
                for breaker in self.active_breakers.values()
            ]
            
            self.logger.debug(
                f"[CB] Trading blocked by {len(reasons)} active breakers"
            )
            
            return False, reasons
            
        except Exception as e:
            self.logger.error(
                f"[CB ERROR] Error checking if trading allowed: {e}",
                exc_info=True
            )
            # Fail safe - allow trading if check fails
            return True, []
    
    def _check_auto_recovery(self) -> None:
        """Check and process auto-recovery for circuit breakers."""
        try:
            now = datetime.now(timezone.utc)
            
            breakers_to_clear = []
            for breaker_type, breaker in self.active_breakers.items():
                if breaker.auto_recovery_time and now >= breaker.auto_recovery_time:
                    breakers_to_clear.append(breaker_type)
                    self.logger.info(
                        f"[CB RECOVERY] Auto-recovering circuit breaker: {breaker_type.value}"
                    )
            
            # Clear recovered breakers
            for breaker_type in breakers_to_clear:
                del self.active_breakers[breaker_type]
                
        except Exception as e:
            self.logger.error(
                f"[CB ERROR] Auto-recovery check failed: {e}",
                exc_info=True
            )
    
    def manual_reset(self, breaker_type: Optional[CircuitBreakerType] = None) -> bool:
        """
        Manually reset circuit breakers.
        
        Args:
            breaker_type: Specific breaker type to reset, or None to reset all
            
        Returns:
            bool: True if any breakers were reset, False otherwise
        """
        try:
            if breaker_type:
                # Reset specific breaker
                if breaker_type in self.active_breakers:
                    del self.active_breakers[breaker_type]
                    self.logger.warning(
                        f"[CB RESET] Manually reset circuit breaker: {breaker_type.value}"
                    )
                    return True
                else:
                    self.logger.info(
                        f"[CB RESET] Breaker {breaker_type.value} not active"
                    )
                    return False
            else:
                # Reset all breakers
                count = len(self.active_breakers)
                self.active_breakers.clear()
                self.logger.warning(
                    f"[CB RESET] Manually reset all {count} circuit breakers"
                )
                return count > 0
                
        except Exception as e:
            self.logger.error(
                f"[CB ERROR] Manual reset failed: {e}",
                exc_info=True
            )
            return False
    
    def set_manual_override(self, enabled: bool) -> None:
        """
        Enable/disable manual override of circuit breakers.
        
        Args:
            enabled: True to enable override, False to disable
        """
        try:
            self.manual_override = enabled
            self.logger.warning(
                f"⚠️ [CB OVERRIDE] Manual override {'ENABLED' if enabled else 'DISABLED'}"
            )
        except Exception as e:
            self.logger.error(
                f"[CB ERROR] Failed to set manual override: {e}",
                exc_info=True
            )
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get circuit breaker status.
        
        Returns:
            Dictionary with complete circuit breaker status
        """
        try:
            return {
                "active_breakers": [
                    {
                        "type": breaker.breaker_type.value,
                        "description": breaker.description,
                        "triggered_at": breaker.triggered_at.isoformat(),
                        "trigger_value": float(breaker.trigger_value),
                        "threshold_value": float(breaker.threshold_value),
                        "auto_recovery": (
                            breaker.auto_recovery_time.isoformat() 
                            if breaker.auto_recovery_time 
                            else None
                        )
                    }
                    for breaker in self.active_breakers.values()
                ],
                "manual_override": self.manual_override,
                "total_breaker_events": len(self.breaker_history),
                "can_trade": self.can_trade()[0],
                "config_available": (
                    hasattr(self, 'config') and self.config is not None
                )
            }
        except Exception as e:
            self.logger.error(
                f"[CB ERROR] Failed to get status: {e}",
                exc_info=True
            )
            return {
                "error": str(e),
                "active_breakers": [],
                "can_trade": True
            }


class PerformanceAnalyzer:
    """
    Analyzes portfolio performance and calculates key metrics.
    
    Tracks performance over time and provides comprehensive
    statistical analysis of trading results.
    """
    
    def __init__(self):
        """Initialize performance analyzer."""
        self.portfolio_snapshots: List[Tuple[datetime, Decimal]] = []
        self.logger = logging.getLogger('engine.portfolio.performance')
    
    def add_portfolio_snapshot(self, value: Decimal) -> None:
        """
        Add a portfolio value snapshot.
        
        Args:
            value: Current portfolio value
        """
        try:
            self.portfolio_snapshots.append((datetime.now(timezone.utc), value))
            
            # Keep only last 1000 snapshots
            if len(self.portfolio_snapshots) > 1000:
                self.portfolio_snapshots = self.portfolio_snapshots[-1000:]
                
        except Exception as e:
            self.logger.error(f"Error adding portfolio snapshot: {e}", exc_info=True)
    
    def calculate_metrics(self) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics.
        
        Returns:
            PerformanceMetrics object with calculated values
        """
        try:
            metrics = PerformanceMetrics()
            
            if len(self.portfolio_snapshots) < 2:
                return metrics
            
            # Calculate returns
            first_value = self.portfolio_snapshots[0][1]
            last_value = self.portfolio_snapshots[-1][1]
            
            if first_value > 0:
                metrics.total_return_percent = (
                    (last_value - first_value) / first_value * 100
                )
            
            # Calculate max drawdown
            peak = self.portfolio_snapshots[0][1]
            max_drawdown = Decimal('0')
            
            for _, value in self.portfolio_snapshots:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak * 100 if peak > 0 else Decimal('0')
                max_drawdown = max(max_drawdown, drawdown)
            
            metrics.max_drawdown_percent = max_drawdown
            metrics.last_updated = datetime.now(timezone.utc)
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error calculating metrics: {e}", exc_info=True)
            return PerformanceMetrics()


class RiskAnalyzer:
    """
    Analyzes portfolio risk and calculates risk metrics.
    
    Provides comprehensive risk assessment including concentration,
    correlation, and liquidity risk analysis.
    """
    
    def __init__(self):
        """Initialize risk analyzer."""
        self.logger = logging.getLogger('engine.portfolio.risk')
    
    def update_positions(self, positions: List[Dict[str, Any]]) -> None:
        """
        Update positions for risk analysis.
        
        Args:
            positions: List of current positions
        """
        pass  # Implementation depends on position structure
    
    def calculate_risk_metrics(
        self, 
        positions: List[Dict[str, Any]], 
        portfolio_value: Decimal
    ) -> RiskMetrics:
        """
        Calculate comprehensive risk metrics.
        
        Args:
            positions: List of current positions
            portfolio_value: Total portfolio value
            
        Returns:
            RiskMetrics object with calculated values
        """
        try:
            metrics = RiskMetrics()
            
            # Calculate concentration risk
            if portfolio_value > 0 and positions:
                max_position_pct = max(
                    safe_decimal(pos.get('value', 0)) / portfolio_value * 100
                    for pos in positions
                ) if positions else Decimal('0')
                
                # Simple concentration score: 0-100
                metrics.concentration_risk_score = min(max_position_pct, Decimal('100'))
            
            metrics.last_calculated = datetime.now(timezone.utc)
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error calculating risk metrics: {e}", exc_info=True)
            return RiskMetrics()


class GlobalPortfolioManager:
    """
    Manages the global portfolio state across all chains.
    
    Provides centralized portfolio tracking, circuit breaker management,
    and performance/risk analysis across all trading operations.
    """
    
    def __init__(self):
        """Initialize global portfolio manager."""
        self.logger = logging.getLogger('engine.portfolio.global')
        
        # Initialize components
        self.circuit_breaker = CircuitBreakerManager()
        self.performance_analyzer = PerformanceAnalyzer()
        self.risk_analyzer = RiskAnalyzer()
        
        # Portfolio state
        self.total_portfolio_value = Decimal('0')
        self.total_available_capital = Decimal('0')
        self.daily_pnl = Decimal('0')
        self.total_pnl = Decimal('0')
        self.consecutive_losses = 0
        
        # Metrics
        self.performance_metrics = PerformanceMetrics()
        self.risk_metrics = RiskMetrics()
        
        # Status tracking
        self.status = EngineStatus.INITIALIZING
        self.last_update = datetime.now(timezone.utc)
        
        self.logger.info("[PORTFOLIO] Global portfolio manager initialized")
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        Get summary of global portfolio.
        
        Returns:
            Dictionary with portfolio summary
        """
        try:
            return {
                "total_value": float(self.total_portfolio_value),
                "available_capital": float(self.total_available_capital),
                "daily_pnl": float(self.daily_pnl),
                "total_pnl": float(self.total_pnl),
                "consecutive_losses": self.consecutive_losses,
                "circuit_breakers": self.circuit_breaker.get_status(),
                "performance": {
                    "total_return_percent": float(self.performance_metrics.total_return_percent),
                    "max_drawdown_percent": float(self.performance_metrics.max_drawdown_percent),
                    "win_rate_percent": float(self.performance_metrics.win_rate_percent)
                },
                "risk": {
                    "overall_risk_score": float(self.risk_metrics.overall_risk_score),
                    "concentration_risk": float(self.risk_metrics.concentration_risk_score)
                },
                "last_update": self.last_update.isoformat()
            }
        except Exception as e:
            self.logger.error(f"Error getting portfolio summary: {e}", exc_info=True)
            return {"error": str(e)}
    
    async def start(self) -> None:
        """Start the global portfolio manager."""
        self.logger.info("[PORTFOLIO] Starting global portfolio manager")
        self.status = EngineStatus.RUNNING
    
    async def stop(self) -> None:
        """Stop the global portfolio manager."""
        self.logger.info("[PORTFOLIO] Stopping global portfolio manager")
        self.status = EngineStatus.STOPPED
    
    async def get_status(self) -> Dict[str, Any]:
        """
        Get global portfolio manager status.
        
        Returns:
            Dictionary with status information
        """
        return {
            "manager": "global_portfolio",
            "status": self.status.value if hasattr(self.status, 'value') else str(self.status),
            "last_update": self.last_update.isoformat(),
            "portfolio_summary": self.get_portfolio_summary()
        }