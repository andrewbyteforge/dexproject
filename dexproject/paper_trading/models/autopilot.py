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

# NO IMPORTS from other model files - use string references instead
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
    
    # Use string reference to avoid circular import
    strategy_config = models.ForeignKey(
        'paper_trading.PaperStrategyConfiguration',
        on_delete=models.CASCADE,
        related_name='autopilot_logs',
        help_text="Associated strategy configuration"
    )
    
    # Use string reference to avoid circular import
    session = models.ForeignKey(
        'paper_trading.PaperTradingSession',
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
        """
        Calculate percentage change.
        
        Returns:
            Percentage change (can be negative)
        """
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
        """
        Evaluate the outcome of this adjustment based on performance.
        
        Args:
            current_performance: Current performance metrics
            
        Returns:
            Outcome evaluation (POSITIVE/NEUTRAL/NEGATIVE)
        """
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
            self.save(update_fields=[
                'outcome',
                'performance_after',
                'outcome_evaluated_at'
            ])
            
            logger.info(
                f"Evaluated Auto Pilot adjustment {self.log_id}: "
                f"{outcome} (Win rate: {before_win_rate}% → {after_win_rate}%)"
            )
            
            return outcome
        
        except Exception as e:
            logger.error(
                f"Error evaluating outcome for log {self.log_id}: {e}",
                exc_info=True
            )
            return self.AdjustmentOutcome.UNKNOWN


class AutoPilotPerformanceSnapshot(models.Model):
    """
    Periodic performance snapshots for Auto Pilot learning.
    
    Captures comprehensive performance metrics at regular intervals to help
    Auto Pilot learn which parameter configurations work best under different
    market conditions.
    
    This data is used for:
    - Identifying optimal parameter ranges
    - Detecting regime changes (market conditions)
    - Evaluating adjustment effectiveness
    - Continuous learning and improvement
    """
    
    # Identity
    snapshot_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique snapshot identifier"
    )
    
    # Use string references to avoid circular imports
    strategy_config = models.ForeignKey(
        'paper_trading.PaperStrategyConfiguration',
        on_delete=models.CASCADE,
        related_name='performance_snapshots',
        help_text="Associated strategy configuration"
    )
    
    session = models.ForeignKey(
        'paper_trading.PaperTradingSession',
        on_delete=models.CASCADE,
        related_name='performance_snapshots',
        null=True,
        blank=True,
        help_text="Associated trading session"
    )
    
    timestamp = models.DateTimeField(
        auto_now_add=True,
        help_text="When snapshot was taken"
    )
    
    # Current parameter values
    current_parameters = models.JSONField(
        default=dict,
        help_text="Current parameter configuration at snapshot time"
    )
    
    # Performance metrics
    win_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Win rate percentage"
    )
    
    total_trades = models.IntegerField(
        default=0,
        help_text="Total trades executed"
    )
    
    winning_trades = models.IntegerField(
        default=0,
        help_text="Number of winning trades"
    )
    
    losing_trades = models.IntegerField(
        default=0,
        help_text="Number of losing trades"
    )
    
    total_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Total profit/loss in USD"
    )
    
    average_profit_per_trade = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Average profit per trade"
    )
    
    average_win_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Average winning trade amount"
    )
    
    average_loss_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Average losing trade amount"
    )
    
    largest_win_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Largest winning trade"
    )
    
    largest_loss_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Largest losing trade"
    )
    
    # Risk metrics
    max_drawdown_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Maximum drawdown percentage"
    )
    
    sharpe_ratio = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal('0'),
        help_text="Risk-adjusted return metric (Sharpe Ratio)"
    )
    
    profit_factor = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal('0'),
        help_text="Ratio of gross profit to gross loss"
    )
    
    # Market conditions
    market_volatility = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Market volatility index at snapshot time (0-100)"
    )
    
    avg_gas_price_gwei = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Average gas price in this period"
    )
    
    market_trend = models.CharField(
        max_length=20,
        default='neutral',
        help_text="Market trend (bullish/bearish/neutral)"
    )
    
    market_conditions_detail = models.JSONField(
        default=dict,
        help_text="Detailed market conditions"
    )
    
    # Auto Pilot context
    autopilot_active = models.BooleanField(
        default=False,
        help_text="Whether Auto Pilot was active during this period"
    )
    
    adjustments_made_count = models.IntegerField(
        default=0,
        help_text="Number of Auto Pilot adjustments made before this snapshot"
    )
    
    last_adjustment_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Type of most recent adjustment"
    )
    
    # Learning metadata
    snapshot_period_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('1'),
        help_text="Time period covered by this snapshot in hours"
    )
    
    notes = models.TextField(
        blank=True,
        help_text="Optional notes or observations"
    )
    
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
            else:
                self.win_rate = Decimal('0')
            
            # Calculate average profit per trade
            if self.total_trades > 0:
                self.average_profit_per_trade = (
                    self.total_pnl_usd / Decimal(self.total_trades)
                ).quantize(Decimal('0.01'))
            else:
                self.average_profit_per_trade = Decimal('0')
            
            # Calculate profit factor
            total_wins = self.winning_trades * abs(self.average_win_usd)
            total_losses = abs(self.losing_trades * self.average_loss_usd)
            
            if total_losses > 0:
                self.profit_factor = (total_wins / total_losses).quantize(Decimal('0.001'))
            else:
                self.profit_factor = Decimal('0') if total_wins == 0 else Decimal('999.999')
            
            logger.debug(
                f"Calculated metrics for snapshot {self.snapshot_id}: "
                f"WR={self.win_rate}%, PF={self.profit_factor}"
            )
        
        except Exception as e:
            logger.error(
                f"Error calculating metrics for snapshot {self.snapshot_id}: {e}",
                exc_info=True
            )
    
    def save(self, *args, **kwargs):
        """Override save to auto-calculate metrics."""
        try:
            self.calculate_metrics()
        except Exception as e:
            logger.error(f"Error in AutoPilotPerformanceSnapshot save: {e}", exc_info=True)
        
        super().save(*args, **kwargs)
    
    def compare_to_previous(self) -> Optional[Dict[str, Any]]:
        """
        Compare this snapshot to the previous one.
        
        Returns:
            Dictionary with comparison metrics or None if no previous snapshot
        """
        try:
            previous = AutoPilotPerformanceSnapshot.objects.filter(
                strategy_config=self.strategy_config,
                timestamp__lt=self.timestamp
            ).order_by('-timestamp').first()
            
            if not previous:
                logger.debug(f"No previous snapshot found for config {self.strategy_config.config_id}")
                return None
            
            comparison = {
                'previous_snapshot_id': str(previous.snapshot_id),
                'time_difference_hours': (
                    (self.timestamp - previous.timestamp).total_seconds() / 3600
                ),
                'win_rate_change': float(self.win_rate - previous.win_rate),
                'pnl_change': float(self.total_pnl_usd - previous.total_pnl_usd),
                'trades_count_change': self.total_trades - previous.total_trades,
                'sharpe_ratio_change': float(self.sharpe_ratio - previous.sharpe_ratio),
            }
            
            logger.debug(
                f"Compared snapshot {self.snapshot_id} to previous: "
                f"WR change {comparison['win_rate_change']:+.2f}%"
            )
            
            return comparison
        
        except Exception as e:
            logger.error(
                f"Error comparing snapshot {self.snapshot_id} to previous: {e}",
                exc_info=True
            )
            return None