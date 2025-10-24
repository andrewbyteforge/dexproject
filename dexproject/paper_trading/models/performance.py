"""
Paper Trading Performance Models

Models for tracking bot performance metrics and trading sessions.
Provides comprehensive analytics and session management.

File: dexproject/paper_trading/models/performance.py
"""

from django.db import models
from django.utils import timezone
from decimal import Decimal
import uuid
import logging
from typing import Optional

from .base import PaperTradingAccount
from .intelligence import PaperStrategyConfiguration

logger = logging.getLogger(__name__)


# =============================================================================
# PERFORMANCE TRACKING MODELS
# =============================================================================

class PaperTradingSession(models.Model):
    """
    Represents a paper trading bot session.
    
    Tracks bot runtime, configuration, status, and high-level statistics
    for each trading session. A session begins when the bot starts and
    ends when it stops or encounters an error.
    
    Attributes:
        session_id: Unique identifier (UUID)
        account: Associated trading account
        strategy_config: Strategy configuration used
        status: Current session status (RUNNING/PAUSED/STOPPED/COMPLETED/ERROR)
        started_at: When session started
        stopped_at: When session stopped
        last_activity: Last activity timestamp
        total_trades: Total trades in this session
        successful_trades: Number of successful trades
        failed_trades: Number of failed trades
        metadata: Additional session metadata (JSON)
        error_message: Error message if status is ERROR
    """
    
    class SessionStatus(models.TextChoices):
        """Session status options."""
        RUNNING = 'RUNNING', 'Running'
        PAUSED = 'PAUSED', 'Paused'
        STOPPED = 'STOPPED', 'Stopped'
        COMPLETED = 'COMPLETED', 'Completed'
        ERROR = 'ERROR', 'Error'
    
    # Identity
    session_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique session identifier"
    )
    
    account = models.ForeignKey(
        PaperTradingAccount,
        on_delete=models.CASCADE,
        related_name='sessions',
        help_text="Associated trading account"
    )
    
    strategy_config = models.ForeignKey(
        PaperStrategyConfiguration,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sessions',
        help_text="Strategy configuration used"
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=SessionStatus.choices,
        default=SessionStatus.RUNNING,
        help_text="Current session status"
    )
    
    # Timing
    started_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Session start timestamp"
    )
    
    stopped_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Session stop timestamp"
    )
    
    last_activity = models.DateTimeField(
        auto_now=True,
        help_text="Last activity timestamp"
    )
    
    # Statistics
    total_trades = models.IntegerField(
        default=0,
        help_text="Total trades in this session"
    )
    
    successful_trades = models.IntegerField(
        default=0,
        help_text="Number of successful trades"
    )
    
    failed_trades = models.IntegerField(
        default=0,
        help_text="Number of failed trades"
    )
    
    # Session metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional session metadata"
    )
    
    error_message = models.TextField(
        blank=True,
        help_text="Error message if status is ERROR"
    )
    
    class Meta:
        """Meta configuration."""
        db_table = 'paper_trading_sessions'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['account', 'status']),
            models.Index(fields=['started_at']),
            models.Index(fields=['status']),
        ]
        verbose_name = 'Paper Trading Session'
        verbose_name_plural = 'Paper Trading Sessions'
    
    def __str__(self) -> str:
        """String representation."""
        duration = ""
        if self.stopped_at:
            delta = self.stopped_at - self.started_at
            hours = delta.total_seconds() / 3600
            duration = f" ({hours:.1f}h)"
        
        return f"Session {self.session_id.hex[:8]} - {self.status}{duration}"
    
    def get_success_rate(self) -> Decimal:
        """
        Calculate trade success rate for this session.
        
        Returns:
            Success rate as percentage (0-100)
        """
        try:
            if self.total_trades == 0:
                return Decimal('0')
            
            rate = (Decimal(self.successful_trades) / Decimal(self.total_trades)) * Decimal('100')
            return rate.quantize(Decimal('0.01'))
        
        except Exception as e:
            logger.error(f"Error calculating success rate for session {self.session_id}: {e}")
            return Decimal('0')
    
    def get_duration_hours(self) -> Optional[Decimal]:
        """
        Get session duration in hours.
        
        Returns:
            Duration in hours, or None if still running
        """
        try:
            if not self.stopped_at:
                # Session still running, calculate from now
                delta = timezone.now() - self.started_at
            else:
                delta = self.stopped_at - self.started_at
            
            hours = Decimal(str(delta.total_seconds() / 3600))
            return hours.quantize(Decimal('0.01'))
        
        except Exception as e:
            logger.error(f"Error calculating duration for session {self.session_id}: {e}")
            return None
    
    def stop_session(self, error: Optional[str] = None) -> None:
        """
        Stop the session.
        
        Args:
            error: Optional error message if session stopped due to error
        """
        try:
            self.stopped_at = timezone.now()
            
            if error:
                self.status = self.SessionStatus.ERROR
                self.error_message = error
                logger.error(f"Session {self.session_id} stopped with error: {error}")
            else:
                self.status = self.SessionStatus.STOPPED
                logger.info(f"Session {self.session_id} stopped normally")
            
            self.save(update_fields=['stopped_at', 'status', 'error_message'])
        
        except Exception as e:
            logger.error(f"Error stopping session {self.session_id}: {e}", exc_info=True)


class PaperPerformanceMetrics(models.Model):
    """
    Performance metrics for paper trading sessions.
    
    Tracks comprehensive performance metrics over specific time periods
    for detailed analysis and reporting. Metrics are calculated periodically
    and stored for historical tracking.
    
    Attributes:
        metric_id: Unique identifier (UUID)
        session: Associated trading session
        period_start: Period start timestamp
        period_end: Period end timestamp
        total_trades: Total trades in period
        winning_trades: Number of winning trades
        losing_trades: Number of losing trades
        win_rate: Win rate percentage
        total_pnl_usd: Total profit/loss in USD
        total_pnl_percent: Total P&L as percentage
        average_win_usd: Average winning trade amount
        average_loss_usd: Average losing trade amount
        largest_win_usd: Largest winning trade
        largest_loss_usd: Largest losing trade
        max_drawdown_percent: Maximum drawdown percentage
        sharpe_ratio: Risk-adjusted return metric
        profit_factor: Ratio of gross profit to gross loss
        created_at: When metrics were calculated
    """
    
    # Identity
    metric_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique metric identifier"
    )
    
    session = models.ForeignKey(
        PaperTradingSession,
        on_delete=models.CASCADE,
        related_name='metrics',
        help_text="Associated trading session"
    )
    
    # Time period
    period_start = models.DateTimeField(
        help_text="Period start timestamp"
    )
    
    period_end = models.DateTimeField(
        help_text="Period end timestamp"
    )
    
    # Trading metrics
    total_trades = models.IntegerField(
        default=0,
        help_text="Total trades in period"
    )
    
    winning_trades = models.IntegerField(
        default=0,
        help_text="Number of winning trades"
    )
    
    losing_trades = models.IntegerField(
        default=0,
        help_text="Number of losing trades"
    )
    
    win_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Win rate percentage (0-100)"
    )
    
    # P&L metrics
    total_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Total profit/loss in USD"
    )
    
    total_pnl_percent = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Total P&L as percentage"
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
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When metrics were calculated"
    )
    
    class Meta:
        """Meta configuration."""
        db_table = 'paper_performance_metrics'
        ordering = ['-period_end']
        indexes = [
            models.Index(fields=['session', 'period_end']),
            models.Index(fields=['win_rate']),
            models.Index(fields=['total_pnl_percent']),
        ]
        verbose_name = 'Performance Metrics'
        verbose_name_plural = 'Performance Metrics'
    
    def __str__(self) -> str:
        """String representation."""
        return (
            f"Metrics {self.period_start.strftime('%Y-%m-%d')} - "
            f"{self.period_end.strftime('%Y-%m-%d')}: "
            f"WR={self.win_rate}% P&L=${self.total_pnl_usd}"
        )
    
    def calculate_metrics(self) -> None:
        """
        Calculate all derived metrics.
        
        Updates win rate, averages, and other calculated fields based on
        the raw trade data.
        """
        try:
            # Calculate win rate
            if self.total_trades > 0:
                self.win_rate = (
                    Decimal(self.winning_trades) / Decimal(self.total_trades)
                ) * Decimal('100')
                self.win_rate = self.win_rate.quantize(Decimal('0.01'))
            else:
                self.win_rate = Decimal('0')
            
            # Calculate profit factor
            total_wins = self.winning_trades * abs(self.average_win_usd)
            total_losses = abs(self.losing_trades * self.average_loss_usd)
            
            if total_losses > 0:
                self.profit_factor = (total_wins / total_losses).quantize(Decimal('0.001'))
            else:
                self.profit_factor = Decimal('0') if total_wins == 0 else Decimal('999.999')
            
            logger.debug(
                f"Calculated metrics for {self.metric_id}: "
                f"WR={self.win_rate}%, PF={self.profit_factor}"
            )
        
        except Exception as e:
            logger.error(
                f"Error calculating metrics for {self.metric_id}: {e}",
                exc_info=True
            )
    
    def save(self, *args, **kwargs):
        """Override save to auto-calculate metrics."""
        try:
            self.calculate_metrics()
        except Exception as e:
            logger.error(f"Error in PaperPerformanceMetrics save: {e}", exc_info=True)
        
        super().save(*args, **kwargs)