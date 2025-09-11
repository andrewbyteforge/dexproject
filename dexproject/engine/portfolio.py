"""
Portfolio Management & Circuit Breakers

Advanced portfolio management with risk limits, circuit breakers,
and comprehensive performance tracking across all chains.
"""

import asyncio
import logging
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
    """Represents a circuit breaker activation."""
    breaker_type: CircuitBreakerType
    trigger_value: Decimal
    threshold_value: Decimal
    triggered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    description: str = ""
    auto_recovery_time: Optional[datetime] = None


@dataclass
class PerformanceMetrics:
    """Portfolio performance metrics."""
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
    """Risk management metrics."""
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
    recovery and escalation procedures.
    """
    
    def __init__(self):
        """Initialize circuit breaker manager."""
        self.active_breakers: Dict[CircuitBreakerType, CircuitBreakerEvent] = {}
        self.breaker_history: List[CircuitBreakerEvent] = []
        self.manual_override = False
        self.logger = logging.getLogger('engine.portfolio.circuit_breaker')
    
    def check_circuit_breakers(self, portfolio_state: Dict[str, Any]) -> List[CircuitBreakerEvent]:
        """Check all circuit breaker conditions."""
        new_breakers = []
        
        # Daily loss circuit breaker
        daily_loss_breaker = self._check_daily_loss_breaker(portfolio_state)
        if daily_loss_breaker:
            new_breakers.append(daily_loss_breaker)
        
        # Portfolio loss circuit breaker
        portfolio_loss_breaker = self._check_portfolio_loss_breaker(portfolio_state)
        if portfolio_loss_breaker:
            new_breakers.append(portfolio_loss_breaker)
        
        # Consecutive losses circuit breaker
        consecutive_loss_breaker = self._check_consecutive_losses_breaker(portfolio_state)
        if consecutive_loss_breaker:
            new_breakers.append(consecutive_loss_breaker)
        
        # Activate new breakers
        for breaker in new_breakers:
            self._activate_breaker(breaker)
        
        return new_breakers
    
    def _check_daily_loss_breaker(self, portfolio_state: Dict[str, Any]) -> Optional[CircuitBreakerEvent]:
        """Check daily loss limit circuit breaker."""
        if CircuitBreakerType.DAILY_LOSS in self.active_breakers:
            return None  # Already active
        
        daily_pnl = safe_decimal(portfolio_state.get('daily_pnl', 0))
        daily_loss_limit = config.max_portfolio_size_usd * config.daily_loss_limit_percent / 100
        
        if daily_pnl < -daily_loss_limit:
            return CircuitBreakerEvent(
                breaker_type=CircuitBreakerType.DAILY_LOSS,
                trigger_value=daily_pnl,
                threshold_value=daily_loss_limit,
                description=f"Daily loss of {format_currency(abs(daily_pnl))} exceeds limit of {format_currency(daily_loss_limit)}",
                auto_recovery_time=datetime.now(timezone.utc) + timedelta(hours=24)
            )
        
        return None
    
    def _check_portfolio_loss_breaker(self, portfolio_state: Dict[str, Any]) -> Optional[CircuitBreakerEvent]:
        """Check portfolio loss circuit breaker."""
        if CircuitBreakerType.PORTFOLIO_LOSS in self.active_breakers:
            return None
        
        total_pnl = safe_decimal(portfolio_state.get('total_pnl', 0))
        portfolio_loss_limit = config.max_portfolio_size_usd * config.circuit_breaker_loss_percent / 100
        
        if total_pnl < -portfolio_loss_limit:
            return CircuitBreakerEvent(
                breaker_type=CircuitBreakerType.PORTFOLIO_LOSS,
                trigger_value=total_pnl,
                threshold_value=portfolio_loss_limit,
                description=f"Portfolio loss of {format_currency(abs(total_pnl))} exceeds circuit breaker limit",
                auto_recovery_time=None  # Manual recovery required
            )
        
        return None
    
    def _check_consecutive_losses_breaker(self, portfolio_state: Dict[str, Any]) -> Optional[CircuitBreakerEvent]:
        """Check consecutive losses circuit breaker."""
        if CircuitBreakerType.CONSECUTIVE_LOSSES in self.active_breakers:
            return None
        
        consecutive_losses = portfolio_state.get('consecutive_losses', 0)
        max_consecutive = 5  # Configurable threshold
        
        if consecutive_losses >= max_consecutive:
            return CircuitBreakerEvent(
                breaker_type=CircuitBreakerType.CONSECUTIVE_LOSSES,
                trigger_value=Decimal(str(consecutive_losses)),
                threshold_value=Decimal(str(max_consecutive)),
                description=f"{consecutive_losses} consecutive losing trades",
                auto_recovery_time=datetime.now(timezone.utc) + timedelta(hours=4)
            )
        
        return None
    
    def _activate_breaker(self, breaker: CircuitBreakerEvent) -> None:
        """Activate a circuit breaker."""
        self.active_breakers[breaker.breaker_type] = breaker
        self.breaker_history.append(breaker)
        
        self.logger.critical(
            f"CIRCUIT BREAKER ACTIVATED: {breaker.breaker_type.value} - {breaker.description}"
        )
    
    def can_trade(self) -> Tuple[bool, List[str]]:
        """Check if trading is allowed based on circuit breakers."""
        if self.manual_override:
            return True, []
        
        # Check for auto-recovery
        self._check_auto_recovery()
        
        if not self.active_breakers:
            return True, []
        
        reasons = [
            f"{breaker.breaker_type.value}: {breaker.description}"
            for breaker in self.active_breakers.values()
        ]
        
        return False, reasons
    
    def _check_auto_recovery(self) -> None:
        """Check and process auto-recovery for circuit breakers."""
        now = datetime.now(timezone.utc)
        
        breakers_to_clear = []
        for breaker_type, breaker in self.active_breakers.items():
            if breaker.auto_recovery_time and now >= breaker.auto_recovery_time:
                breakers_to_clear.append(breaker_type)
                self.logger.info(f"Auto-recovering circuit breaker: {breaker_type.value}")
        
        for breaker_type in breakers_to_clear:
            del self.active_breakers[breaker_type]
    
    def manual_reset(self, breaker_type: Optional[CircuitBreakerType] = None) -> bool:
        """
        Manually reset circuit breakers.
        
        Args:
            breaker_type: Specific breaker type to reset, or None to reset all
            
        Returns:
            bool: True if any breakers were reset, False otherwise
        """
        if breaker_type:
            if breaker_type in self.active_breakers:
                del self.active_breakers[breaker_type]
                self.logger.warning(f"Manually reset circuit breaker: {breaker_type.value}")
                return True
            return False
        else:
            # Reset all breakers
            count = len(self.active_breakers)
            self.active_breakers.clear()
            self.logger.warning(f"Manually reset all {count} circuit breakers")
            return count > 0
    
    def set_manual_override(self, enabled: bool) -> None:
        """Enable/disable manual override of circuit breakers."""
        self.manual_override = enabled
        self.logger.warning(f"Manual override {'ENABLED' if enabled else 'DISABLED'}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status."""
        return {
            "active_breakers": [
                {
                    "type": breaker.breaker_type.value,
                    "description": breaker.description,
                    "triggered_at": breaker.triggered_at.isoformat(),
                    "auto_recovery": breaker.auto_recovery_time.isoformat() if breaker.auto_recovery_time else None
                }
                for breaker in self.active_breakers.values()
            ],
            "manual_override": self.manual_override,
            "total_breaker_events": len(self.breaker_history),
            "can_trade": self.can_trade()[0]
        }


class PerformanceAnalyzer:
    """
    Analyzes portfolio performance and calculates key metrics.
    
    Tracks returns, risk metrics, and trading statistics
    for comprehensive performance evaluation.
    """
    
    def __init__(self):
        """Initialize performance analyzer."""
        self.trade_history: List[Dict[str, Any]] = []
        self.daily_returns: List[Tuple[datetime, Decimal]] = []
        self.portfolio_values: List[Tuple[datetime, Decimal]] = []
        self.logger = logging.getLogger('engine.portfolio.performance')
    
    def add_trade_result(self, trade_data: Dict[str, Any]) -> None:
        """Add a completed trade for performance analysis."""
        self.trade_history.append({
            **trade_data,
            'timestamp': datetime.now(timezone.utc)
        })
    
    def add_portfolio_snapshot(self, portfolio_value: Decimal) -> None:
        """Add portfolio value snapshot for return calculation."""
        self.portfolio_values.append((datetime.now(timezone.utc), portfolio_value))
        
        # Keep only last 30 days of data
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        self.portfolio_values = [
            (ts, val) for ts, val in self.portfolio_values 
            if ts >= cutoff
        ]
    
    def calculate_metrics(self) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics."""
        metrics = PerformanceMetrics()
        
        if not self.trade_history:
            return metrics
        
        # Basic trade statistics
        metrics.total_trades = len(self.trade_history)
        
        winning_trades = [t for t in self.trade_history if t.get('pnl', 0) > 0]
        losing_trades = [t for t in self.trade_history if t.get('pnl', 0) < 0]
        
        metrics.winning_trades = len(winning_trades)
        metrics.losing_trades = len(losing_trades)
        
        if metrics.total_trades > 0:
            metrics.win_rate_percent = Decimal(str(metrics.winning_trades / metrics.total_trades * 100))
        
        # PnL calculations
        total_pnl = sum(safe_decimal(t.get('pnl', 0)) for t in self.trade_history)
        gross_profit = sum(safe_decimal(t.get('pnl', 0)) for t in winning_trades)
        gross_loss = abs(sum(safe_decimal(t.get('pnl', 0)) for t in losing_trades))
        
        if gross_loss > 0:
            metrics.profit_factor = gross_profit / gross_loss
        
        # Largest win/loss
        if winning_trades:
            metrics.largest_win = max(safe_decimal(t.get('pnl', 0)) for t in winning_trades)
        if losing_trades:
            metrics.largest_loss = abs(min(safe_decimal(t.get('pnl', 0)) for t in losing_trades))
        
        # Portfolio returns
        if len(self.portfolio_values) >= 2:
            metrics.total_return_percent = self._calculate_total_return()
            metrics.daily_return_percent = self._calculate_daily_return()
            metrics.max_drawdown_percent = self._calculate_max_drawdown()
            metrics.sharpe_ratio = self._calculate_sharpe_ratio()
        
        # Average trade duration
        trade_durations = []
        for trade in self.trade_history:
            if trade.get('entry_time') and trade.get('exit_time'):
                duration = trade['exit_time'] - trade['entry_time']
                trade_durations.append(duration.total_seconds() / 3600)  # Convert to hours
        
        if trade_durations:
            metrics.avg_trade_duration_hours = Decimal(str(sum(trade_durations) / len(trade_durations)))
        
        metrics.last_updated = datetime.now(timezone.utc)
        return metrics
    
    def _calculate_total_return(self) -> Decimal:
        """Calculate total portfolio return percentage."""
        if len(self.portfolio_values) < 2:
            return Decimal('0')
        
        initial_value = self.portfolio_values[0][1]
        current_value = self.portfolio_values[-1][1]
        
        if initial_value > 0:
            return (current_value - initial_value) / initial_value * 100
        
        return Decimal('0')
    
    def _calculate_daily_return(self) -> Decimal:
        """Calculate daily return percentage."""
        if len(self.portfolio_values) < 2:
            return Decimal('0')
        
        # Get today's and yesterday's values
        today = datetime.now(timezone.utc).date()
        yesterday = today - timedelta(days=1)
        
        today_values = [val for ts, val in self.portfolio_values if ts.date() == today]
        yesterday_values = [val for ts, val in self.portfolio_values if ts.date() == yesterday]
        
        if today_values and yesterday_values:
            today_value = today_values[-1]
            yesterday_value = yesterday_values[-1]
            
            if yesterday_value > 0:
                return (today_value - yesterday_value) / yesterday_value * 100
        
        return Decimal('0')
    
    def _calculate_max_drawdown(self) -> Decimal:
        """Calculate maximum drawdown percentage."""
        if len(self.portfolio_values) < 2:
            return Decimal('0')
        
        peak_value = Decimal('0')
        max_drawdown = Decimal('0')
        
        for _, value in self.portfolio_values:
            if value > peak_value:
                peak_value = value
            else:
                drawdown = (peak_value - value) / peak_value * 100 if peak_value > 0 else Decimal('0')
                max_drawdown = max(max_drawdown, drawdown)
        
        return max_drawdown
    
    def _calculate_sharpe_ratio(self) -> Optional[Decimal]:
        """Calculate Sharpe ratio (simplified)."""
        if len(self.portfolio_values) < 10:  # Need sufficient data
            return None
        
        # Calculate daily returns
        daily_returns = []
        for i in range(1, len(self.portfolio_values)):
            prev_value = self.portfolio_values[i-1][1]
            curr_value = self.portfolio_values[i][1]
            
            if prev_value > 0:
                daily_return = (curr_value - prev_value) / prev_value
                daily_returns.append(float(daily_return))
        
        if not daily_returns:
            return None
        
        import statistics
        
        mean_return = statistics.mean(daily_returns)
        std_return = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0
        
        # Assume risk-free rate of 2% annual (0.0055% daily)
        risk_free_rate = 0.000055
        
        if std_return > 0:
            sharpe = (mean_return - risk_free_rate) / std_return
            return Decimal(str(round(sharpe, 3)))
        
        return None


class RiskAnalyzer:
    """
    Analyzes portfolio risk metrics and concentration.
    
    Calculates Value at Risk, concentration risk,
    and other risk management metrics.
    """
    
    def __init__(self):
        """Initialize risk analyzer."""
        self.position_history: List[Dict[str, Any]] = []
        self.logger = logging.getLogger('engine.portfolio.risk')
    
    def update_positions(self, positions: List[Dict[str, Any]]) -> None:
        """Update current positions for risk analysis."""
        self.position_history.append({
            'timestamp': datetime.now(timezone.utc),
            'positions': positions.copy()
        })
        
        # Keep only last 24 hours of position data
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        self.position_history = [
            entry for entry in self.position_history 
            if entry['timestamp'] >= cutoff
        ]
    
    def calculate_risk_metrics(self, current_positions: List[Dict[str, Any]], 
                             portfolio_value: Decimal) -> RiskMetrics:
        """Calculate comprehensive risk metrics."""
        metrics = RiskMetrics()
        
        # Concentration risk
        metrics.concentration_risk_score = self._calculate_concentration_risk(current_positions, portfolio_value)
        
        # Value at Risk (5%)
        metrics.value_at_risk_5pct = self._calculate_value_at_risk(portfolio_value)
        
        # Liquidity risk (simplified)
        metrics.liquidity_risk_score = self._calculate_liquidity_risk(current_positions)
        
        # Overall risk score (weighted combination)
        metrics.overall_risk_score = self._calculate_overall_risk_score(metrics)
        
        metrics.last_calculated = datetime.now(timezone.utc)
        return metrics
    
    def _calculate_concentration_risk(self, positions: List[Dict[str, Any]], 
                                    portfolio_value: Decimal) -> Decimal:
        """Calculate concentration risk score (0-100)."""
        if not positions or portfolio_value == 0:
            return Decimal('0')
        
        # Calculate position weights
        position_weights = []
        for position in positions:
            position_value = safe_decimal(position.get('value', 0))
            weight = position_value / portfolio_value if portfolio_value > 0 else Decimal('0')
            position_weights.append(float(weight))
        
        # Calculate Herfindahl-Hirschman Index
        hhi = sum(weight ** 2 for weight in position_weights)
        
        # Convert to 0-100 scale (higher = more concentrated = riskier)
        # HHI ranges from 1/n (perfectly diversified) to 1 (all in one position)
        if len(positions) > 0:
            min_hhi = 1 / len(positions)
            concentration_score = (hhi - min_hhi) / (1 - min_hhi) * 100
            return Decimal(str(min(100, max(0, concentration_score))))
        
        return Decimal('0')
    
    def _calculate_value_at_risk(self, portfolio_value: Decimal) -> Decimal:
        """Calculate 5% Value at Risk (simplified)."""
        if not self.position_history:
            return Decimal('0')
        
        # Calculate historical portfolio value changes
        value_changes = []
        
        for i in range(1, len(self.position_history)):
            prev_total = sum(safe_decimal(p.get('value', 0)) for p in self.position_history[i-1]['positions'])
            curr_total = sum(safe_decimal(p.get('value', 0)) for p in self.position_history[i]['positions'])
            
            if prev_total > 0:
                change_pct = (curr_total - prev_total) / prev_total
                value_changes.append(float(change_pct))
        
        if len(value_changes) < 5:  # Need sufficient data
            # Use conservative estimate
            return portfolio_value * Decimal('0.05')  # 5% of portfolio
        
        # Calculate 5th percentile of losses
        import statistics
        value_changes.sort()
        percentile_5_index = int(len(value_changes) * 0.05)
        var_5pct_change = abs(value_changes[percentile_5_index])
        
        return portfolio_value * Decimal(str(var_5pct_change))
    
    def _calculate_liquidity_risk(self, positions: List[Dict[str, Any]]) -> Decimal:
        """Calculate liquidity risk score (0-100)."""
        if not positions:
            return Decimal('0')
        
        # Simplified liquidity scoring based on position characteristics
        total_risk_score = Decimal('0')
        total_weight = Decimal('0')
        
        for position in positions:
            # Basic liquidity risk factors (would be enhanced with real market data)
            position_value = safe_decimal(position.get('value', 0))
            
            # Assume newer tokens are less liquid
            liquidity_score = Decimal('30')  # Base score
            
            # Add to weighted average
            total_risk_score += liquidity_score * position_value
            total_weight += position_value
        
        if total_weight > 0:
            return total_risk_score / total_weight
        
        return Decimal('0')
    
    def _calculate_overall_risk_score(self, metrics: RiskMetrics) -> Decimal:
        """Calculate overall risk score from individual metrics."""
        # Weighted combination of risk factors
        weights = {
            'concentration': Decimal('0.4'),
            'liquidity': Decimal('0.3'),
            'var': Decimal('0.3')
        }
        
        # Normalize VaR to 0-100 scale
        var_score = min(Decimal('100'), metrics.value_at_risk_5pct / config.max_portfolio_size_usd * 100 * 10)
        
        overall_score = (
            metrics.concentration_risk_score * weights['concentration'] +
            metrics.liquidity_risk_score * weights['liquidity'] +
            var_score * weights['var']
        )
        
        return min(Decimal('100'), max(Decimal('0'), overall_score))


class GlobalPortfolioManager:
    """
    Global portfolio manager that coordinates across all chains.
    
    Provides unified portfolio view, risk management,
    and performance tracking across multiple blockchains.
    """
    
    def __init__(self):
        """Initialize global portfolio manager."""
        self.circuit_breaker = CircuitBreakerManager()
        self.performance_analyzer = PerformanceAnalyzer()
        self.risk_analyzer = RiskAnalyzer()
        
        self.status = EngineStatus.STOPPED
        self.last_update = datetime.now(timezone.utc)
        self.logger = logging.getLogger('engine.portfolio.global')
        
        # Global portfolio state
        self.total_portfolio_value = Decimal('0')
        self.total_available_capital = config.max_portfolio_size_usd
        self.daily_pnl = Decimal('0')
        self.total_pnl = Decimal('0')
        self.consecutive_losses = 0
        
        # Performance tracking
        self.performance_metrics: Optional[PerformanceMetrics] = None
        self.risk_metrics: Optional[RiskMetrics] = None
    
    async def update_portfolio_state(self, chain_portfolios: Dict[int, Dict[str, Any]]) -> None:
        """Update global portfolio state from all chains."""
        try:
            # Aggregate portfolio values
            self.total_portfolio_value = sum(
                safe_decimal(portfolio.get('total_value', 0))
                for portfolio in chain_portfolios.values()
            )
            
            self.total_available_capital = sum(
                safe_decimal(portfolio.get('available_capital', 0))
                for portfolio in chain_portfolios.values()
            )
            
            self.daily_pnl = sum(
                safe_decimal(portfolio.get('daily_pnl', 0))
                for portfolio in chain_portfolios.values()
            )
            
            # Aggregate all positions
            all_positions = []
            for portfolio in chain_portfolios.values():
                all_positions.extend(portfolio.get('positions', []))
            
            # Update performance metrics
            self.performance_analyzer.add_portfolio_snapshot(self.total_portfolio_value)
            self.performance_metrics = self.performance_analyzer.calculate_metrics()
            
            # Update risk metrics
            self.risk_analyzer.update_positions(all_positions)
            self.risk_metrics = self.risk_analyzer.calculate_risk_metrics(all_positions, self.total_portfolio_value)
            
            # Check circuit breakers
            portfolio_state = {
                'total_value': self.total_portfolio_value,
                'daily_pnl': self.daily_pnl,
                'total_pnl': self.total_pnl,
                'consecutive_losses': self.consecutive_losses
            }
            
            new_breakers = self.circuit_breaker.check_circuit_breakers(portfolio_state)
            
            # Log circuit breaker activations
            for breaker in new_breakers:
                self.logger.critical(f"Circuit breaker activated: {breaker.description}")
            
            self.last_update = datetime.now(timezone.utc)
            
        except Exception as e:
            self.logger.error(f"Error updating global portfolio state: {e}")
    
    def can_open_new_position(self, position_size: Decimal, chain_id: int) -> Tuple[bool, str]:
        """Check if a new position can be opened globally."""
        # Check circuit breakers first
        can_trade, reasons = self.circuit_breaker.can_trade()
        if not can_trade:
            return False, f"Circuit breakers active: {'; '.join(reasons)}"
        
        # Check global position size limits
        if position_size > config.max_position_size_usd:
            return False, f"Position exceeds global limit: {format_currency(config.max_position_size_usd)}"
        
        # Check global available capital
        if position_size > self.total_available_capital:
            return False, f"Insufficient global capital: {format_currency(self.total_available_capital)}"
        
        # Check portfolio concentration
        if self.total_portfolio_value > 0:
            concentration_pct = position_size / self.total_portfolio_value * 100
            if concentration_pct > 15:  # Max 15% of portfolio in any single position
                return False, f"Position would exceed 15% portfolio concentration"
        
        return True, "OK"
    
    def record_trade_result(self, trade_result: Dict[str, Any]) -> None:
        """Record a trade result for performance tracking."""
        self.performance_analyzer.add_trade_result(trade_result)
        
        # Update consecutive losses counter
        if trade_result.get('pnl', 0) < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get comprehensive portfolio summary."""
        # Trading permissions
        can_trade, trade_restrictions = self.circuit_breaker.can_trade()
        
        summary = {
            "global_portfolio": {
                "total_value": float(self.total_portfolio_value),
                "available_capital": float(self.total_available_capital),
                "daily_pnl": float(self.daily_pnl),
                "total_pnl": float(self.total_pnl),
                "utilization_percent": float(
                    (config.max_portfolio_size_usd - self.total_available_capital) / 
                    config.max_portfolio_size_usd * 100
                ) if config.max_portfolio_size_usd > 0 else 0
            },
            "trading_status": {
                "can_trade": can_trade,
                "restrictions": trade_restrictions,
                "consecutive_losses": self.consecutive_losses
            },
            "circuit_breakers": self.circuit_breaker.get_status(),
            "last_updated": self.last_update.isoformat()
        }
        
        # Add performance metrics if available
        if self.performance_metrics:
            summary["performance"] = {
                "total_return_percent": float(self.performance_metrics.total_return_percent),
                "daily_return_percent": float(self.performance_metrics.daily_return_percent),
                "max_drawdown_percent": float(self.performance_metrics.max_drawdown_percent),
                "win_rate_percent": float(self.performance_metrics.win_rate_percent),
                "profit_factor": float(self.performance_metrics.profit_factor),
                "total_trades": self.performance_metrics.total_trades,
                "sharpe_ratio": float(self.performance_metrics.sharpe_ratio) if self.performance_metrics.sharpe_ratio else None
            }
        
        # Add risk metrics if available
        if self.risk_metrics:
            summary["risk"] = {
                "overall_risk_score": float(self.risk_metrics.overall_risk_score),
                "concentration_risk": float(self.risk_metrics.concentration_risk_score),
                "liquidity_risk": float(self.risk_metrics.liquidity_risk_score),
                "value_at_risk_5pct": float(self.risk_metrics.value_at_risk_5pct)
            }
        
        return summary
    
    async def emergency_stop(self) -> None:
        """Emergency stop all trading activities."""
        # Activate manual circuit breaker
        emergency_breaker = CircuitBreakerEvent(
            breaker_type=CircuitBreakerType.EXTERNAL_TRIGGER,
            trigger_value=Decimal('1'),
            threshold_value=Decimal('1'),
            description="Emergency stop activated manually"
        )
        
        self.circuit_breaker._activate_breaker(emergency_breaker)
        self.logger.critical("EMERGENCY STOP ACTIVATED - All trading halted")
    
    async def start(self) -> None:
        """Start the global portfolio manager."""
        self.logger.info("Starting global portfolio manager")
        self.status = EngineStatus.RUNNING
    
    async def stop(self) -> None:
        """Stop the global portfolio manager."""
        self.logger.info("Stopping global portfolio manager")
        self.status = EngineStatus.STOPPED
    
    async def get_status(self) -> Dict[str, Any]:
        """Get global portfolio manager status."""
        return {
            "manager": "global_portfolio",
            "status": self.status,
            "last_update": self.last_update.isoformat(),
            "portfolio_summary": self.get_portfolio_summary()
        }