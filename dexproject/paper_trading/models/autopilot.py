"""
Paper Trading Auto Pilot Models

Models for Auto Pilot intelligent parameter adaptation and learning system.
Tracks all adjustments, performance snapshots, and outcomes for transparency
and continuous improvement.

File: dexproject/paper_trading/models/autopilot.py
"""

from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
import uuid
import logging
from typing import Dict, Any, Optional

from .intelligence import PaperStrategyConfiguration
from .performance import PaperTradingSession

logger = logging.getLogger(__name__)


# =============================================================================
# AUTO PILOT INTELLIGENCE MODELS
# =============================================================================

class AutoPilotLog(models.Model):
    """
    Tracks all Auto Pilot parameter adjustments for transparency and analysis.
    
    Every time Auto Pilot adjusts a parameter, it's logged here with complete
    context including:
    - What was changed (parameter name and values)
    - Why it was changed (reasoning and trigger)
    - Performance metrics before and after
    - Market conditions at the time
    - Outcome evaluation (was it beneficial?)
    
    This provides full transparency and allows users to understand and
    analyze Auto Pilot's decision-making process.
    
    Attributes:
        log_id: Unique identifier (UUID)
        strategy_config: Associated strategy configuration
        session: Associated trading session
        timestamp: When adjustment was made
        adjustment_type: Type of adjustment
        parameter_name: Name of parameter adjusted
        old_value: Previous value
        new_value: New value
        change_percent: Percentage change
        reason: Detailed explanation
        trigger_metric: Metric that triggered adjustment
        trigger_value: Value of the trigger metric
        performance_before: Performance metrics before adjustment
        performance_after: Performance metrics after adjustment
        outcome: Evaluation of adjustment outcome
        market_conditions: Market context at time of adjustment
    """
    
    class AdjustmentType(models.TextChoices):
        """Types of adjustments Auto Pilot can make."""
        POSITION_SIZE_INCREASE = 'POSITION_SIZE_INCREASE', 'Position Size Increase'
        POSITION_SIZE_DECREASE = 'POSITION_SIZE_DECREASE', 'Position Size Decrease'
        CONFIDENCE_INCREASE = 'CONFIDENCE_INCREASE', 'Confidence Threshold Increase'
        CONFIDENCE_DECREASE = 'CONFIDENCE_DECREASE', 'Confidence Threshold Decrease'
        FREQUENCY_INCREASE = 'FREQUENCY_INCREASE', 'Trading Frequency Increase'
        FREQUENCY_DECREASE = 'FREQUENCY_DECREASE', 'Trading Frequency Decrease'
        STOP_LOSS_TIGHTEN = 'STOP_LOSS_TIGHTEN', 'Stop Loss Tightened'
        STOP_LOSS_LOOSEN = 'STOP_LOSS_LOOSEN', 'Stop Loss Loosened'
        TAKE_PROFIT_INCREASE = 'TAKE_PROFIT_INCREASE', 'Take Profit Increased'
        TAKE_PROFIT_DECREASE = 'TAKE_PROFIT_DECREASE', 'Take Profit Decreased'
        PAUSE_TRADING = 'PAUSE_TRADING', 'Trading Paused'
        RESUME_TRADING = 'RESUME_TRADING', 'Trading Resumed'
        GAS_STRATEGY_ADJUST = 'GAS_STRATEGY_ADJUST', 'Gas Strategy Adjusted'
        RISK_TOLERANCE_ADJUST = 'RISK_TOLERANCE_ADJUST', 'Risk Tolerance Adjusted'
    
    class AdjustmentOutcome(models.TextChoices):
        """Outcome of the adjustment."""
        PENDING = 'PENDING', 'Pending - Too early to tell'
        POSITIVE = 'POSITIVE', 'Positive - Improved performance'
        NEUTRAL = 'NEUTRAL', 'Neutral - No significant change'
        NEGATIVE = 'NEGATIVE', 'Negative - Worsened performance'
        UNKNOWN = 'UNKNOWN', 'Unknown - Insufficient data'
    
    # Identity
    log_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique log identifier"
    )
    
    strategy_config = models.ForeignKey(
        PaperStrategyConfiguration,
        on_delete=models.CASCADE,
        related_name='autopilot_logs',
        help_text="Associated strategy configuration"
    )
    
    session = models.ForeignKey(
        PaperTradingSession,
        on_delete=models.CASCADE,
        related_name='autopilot_logs',
        null=True,
        blank=True,
        help_text="Associated trading session"
    )
    
    timestamp = models.DateTimeField(
        auto_now_add=True,
        help_text="When adjustment was made"
    )
    
    # Adjustment details
    adjustment_type = models.CharField(
        max_length=50,
        choices=AdjustmentType.choices,
        help_text="Type of adjustment made"
    )
    
    parameter_name = models.CharField(
        max_length=50,
        help_text="Name of the parameter adjusted"
    )
    
    old_value = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="Previous parameter value"
    )
    
    new_value = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="New parameter value"
    )
    
    change_percent = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        help_text="Percentage change"
    )
    
    # Reasoning
    reason = models.TextField(
        help_text="Detailed explanation of why this adjustment was made"
    )
    
    trigger_metric = models.CharField(
        max_length=50,
        help_text="Metric that triggered adjustment (e.g., 'win_rate', 'drawdown')"
    )
    
    trigger_value = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="Value of the trigger metric"
    )
    
    trigger_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0'),
        help_text="Threshold value that was crossed"
    )
    
    # Performance context
    performance_before = models.JSONField(
        default=dict,
        help_text="Performance metrics before adjustment"
    )
    
    performance_after = models.JSONField(
        default=dict,
        null=True,
        blank=True,
        help_text="Performance metrics after adjustment (filled later)"
    )
    
    # Outcome tracking
    outcome = models.CharField(
        max_length=20,
        choices=AdjustmentOutcome.choices,
        default=AdjustmentOutcome.PENDING,
        help_text="Evaluation of adjustment outcome"
    )
    
    outcome_evaluated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the outcome was evaluated"
    )
    
    outcome_notes = models.TextField(
        blank=True,
        help_text="Additional notes on the outcome"
    )
    
    trades_since_adjustment = models.IntegerField(
        default=0,
        help_text="Number of trades executed since this adjustment"
    )
    
    # Market context
    market_conditions = models.JSONField(
        default=dict,
        help_text="Market conditions at time of adjustment"
    )
    
    # Learning metadata
    confidence_in_adjustment = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('50'),
        help_text="Auto Pilot's confidence in this adjustment (0-100)"
    )
    
    is_reversal = models.BooleanField(
        default=False,
        help_text="Whether this reverses a previous adjustment"
    )
    
    reverses_log = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reversed_by',
        help_text="Previous adjustment this reverses"
    )
    
    class Meta:
        """Meta configuration."""
        db_table = 'autopilot_logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['strategy_config', 'timestamp']),
            models.Index(fields=['adjustment_type']),
            models.Index(fields=['outcome']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['session', 'timestamp']),
        ]
        verbose_name = 'Auto Pilot Log'
        verbose_name_plural = 'Auto Pilot Logs'
    
    def __str__(self) -> str:
        """String representation."""
        return (
            f"{self.adjustment_type}: {self.parameter_name} "
            f"{self.old_value} → {self.new_value}"
        )
    
    def calculate_change_percent(self) -> Decimal:
        """Calculate percentage change."""
        try:
            if self.old_value == 0:
                if self.new_value > 0:
                    return Decimal('100')
                return Decimal('0')
            
            change = ((self.new_value - self.old_value) / self.old_value) * Decimal('100')
            return change.quantize(Decimal('0.01'))
        
        except Exception as e:
            logger.error(f"Error calculating change percent for log {self.log_id}: {e}")
            return Decimal('0')
    
    def save(self, *args, **kwargs):
        """Override save to auto-calculate change_percent."""
        try:
            if not self.change_percent or self.change_percent == Decimal('0'):
                self.change_percent = self.calculate_change_percent()
        except Exception as e:
            logger.error(f"Error in AutoPilotLog save: {e}", exc_info=True)
        
        super().save(*args, **kwargs)
    
    def evaluate_outcome(self, current_performance: Dict[str, Any]) -> str:
        """Evaluate the outcome of this adjustment based on performance."""
        try:
            if not self.performance_before:
                logger.warning(f"No performance_before data for log {self.log_id}")
                return self.AdjustmentOutcome.UNKNOWN
            
            # Compare key metrics
            before_win_rate = Decimal(str(self.performance_before.get('win_rate', 0)))
            after_win_rate = Decimal(str(current_performance.get('win_rate', 0)))
            
            before_pnl = Decimal(str(self.performance_before.get('total_pnl_usd', 0)))
            after_pnl = Decimal(str(current_performance.get('total_pnl_usd', 0)))
            
            # Calculate improvements
            win_rate_improved = after_win_rate > before_win_rate
            pnl_improved = after_pnl > before_pnl
            
            # Evaluate
            if win_rate_improved and pnl_improved:
                outcome = self.AdjustmentOutcome.POSITIVE
            elif not win_rate_improved and not pnl_improved:
                outcome = self.AdjustmentOutcome.NEGATIVE
            else:
                outcome = self.AdjustmentOutcome.NEUTRAL
            
            # Update
            self.outcome = outcome
            self.performance_after = current_performance
            self.outcome_evaluated_at = timezone.now()
            self.save(update_fields=['outcome', 'performance_after', 'outcome_evaluated_at'])
            
            logger.info(
                f"Evaluated Auto Pilot adjustment {self.log_id}: {outcome} "
                f"(Win rate: {before_win_rate}% → {after_win_rate}%)"
            )
            
            return outcome
        
        except Exception as e:
            logger.error(f"Error evaluating outcome for log {self.log_id}: {e}", exc_info=True)
            return self.AdjustmentOutcome.UNKNOWN


class AutoPilotPerformanceSnapshot(models.Model):
    """Periodic performance snapshots for Auto Pilot learning."""
    
    snapshot_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    strategy_config = models.ForeignKey(
        PaperStrategyConfiguration, on_delete=models.CASCADE, related_name='performance_snapshots'
    )
    session = models.ForeignKey(
        PaperTradingSession, on_delete=models.CASCADE, related_name='performance_snapshots',
        null=True, blank=True
    )
    
    timestamp = models.DateTimeField(auto_now_add=True)
    current_parameters = models.JSONField(default=dict)
    
    # Performance metrics
    win_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'))
    total_trades = models.IntegerField(default=0)
    winning_trades = models.IntegerField(default=0)
    losing_trades = models.IntegerField(default=0)
    total_pnl_usd = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    average_profit_per_trade = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    average_win_usd = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    average_loss_usd = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    largest_win_usd = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    largest_loss_usd = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    
    # Risk metrics
    max_drawdown_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'))
    sharpe_ratio = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal('0'))
    profit_factor = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal('0'))
    
    # Market conditions
    market_volatility = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'))
    avg_gas_price_gwei = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    market_trend = models.CharField(max_length=20, default='neutral')
    market_conditions_detail = models.JSONField(default=dict)
    
    # Auto Pilot context
    autopilot_active = models.BooleanField(default=False)
    adjustments_made_count = models.IntegerField(default=0)
    last_adjustment_type = models.CharField(max_length=50, blank=True)
    
    # Learning metadata
    snapshot_period_hours = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('1'))
    notes = models.TextField(blank=True)
    
    class Meta:
        """Meta configuration."""
        db_table = 'autopilot_performance_snapshots'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['strategy_config', 'timestamp']),
            models.Index(fields=['autopilot_active']),
            models.Index(fields=['win_rate']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['session', 'timestamp']),
        ]
        verbose_name = 'Auto Pilot Performance Snapshot'
        verbose_name_plural = 'Auto Pilot Performance Snapshots'
    
    def __str__(self) -> str:
        """String representation."""
        return (
            f"Snapshot {self.timestamp.strftime('%Y-%m-%d %H:%M')} - "
            f"WR: {self.win_rate}% | P&L: ${self.total_pnl_usd}"
        )
    
    def calculate_metrics(self) -> None:
        """Calculate all derived metrics."""
        try:
            # Calculate win rate
            if self.total_trades > 0:
                self.win_rate = (
                    Decimal(self.winning_trades) / Decimal(self.total_trades)
                ) * Decimal('100')
                self.win_rate = self.win_rate.quantize(Decimal('0.01'))
            
            # Calculate average profit per trade
            if self.total_trades > 0:
                self.average_profit_per_trade = (
                    self.total_pnl_usd / Decimal(self.total_trades)
                ).quantize(Decimal('0.01'))
            
            # Calculate profit factor
            total_wins = self.winning_trades * self.average_win_usd
            total_losses = abs(self.losing_trades * self.average_loss_usd)
            
            if total_losses > 0:
                self.profit_factor = (total_wins / total_losses).quantize(Decimal('0.001'))
            
            logger.debug(f"Calculated metrics for snapshot {self.snapshot_id}")
        
        except Exception as e:
            logger.error(f"Error calculating metrics for snapshot {self.snapshot_id}: {e}", exc_info=True)
    
    def save(self, *args, **kwargs):
        """Override save to auto-calculate metrics."""
        try:
            self.calculate_metrics()
        except Exception as e:
            logger.error(f"Error in AutoPilotPerformanceSnapshot save: {e}", exc_info=True)
        
        super().save(*args, **kwargs)