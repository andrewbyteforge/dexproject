"""
Backtest Models - Database Storage for Backtest Results

Stores backtest runs and their results for historical analysis and comparison.

Phase 7B - Day 13: Backtesting Models

File: dexproject/paper_trading/backtesting/models/backtest.py
"""

import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator


# =============================================================================
# BACKTEST RUN MODEL
# =============================================================================

class BacktestRun(models.Model):
    """
    Represents a single backtest execution.
    
    Stores configuration and metadata about a backtest run.
    Results are stored in related BacktestResult model.
    
    Fields:
        backtest_id: Unique identifier (UUID)
        strategy_type: Type of strategy tested (SPOT, DCA, GRID, TWAP, VWAP)
        token_symbol: Token symbol backtested
        start_date: Backtest period start
        end_date: Backtest period end
        interval: Data interval used ('1h', '1d', etc.)
        initial_balance_usd: Starting balance
        strategy_params: JSON field with strategy configuration
        created_at: When backtest was created
        completed_at: When backtest finished
        status: Backtest status (PENDING, RUNNING, COMPLETED, FAILED)
        error_message: Error details if failed
    """
    
    # Status choices
    STATUS_PENDING = 'PENDING'
    STATUS_RUNNING = 'RUNNING'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_FAILED = 'FAILED'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]
    
    # Strategy type choices
    STRATEGY_SPOT = 'SPOT'
    STRATEGY_DCA = 'DCA'
    STRATEGY_GRID = 'GRID'
    STRATEGY_TWAP = 'TWAP'
    STRATEGY_VWAP = 'VWAP'
    
    STRATEGY_CHOICES = [
        (STRATEGY_SPOT, 'Spot Buy'),
        (STRATEGY_DCA, 'Dollar Cost Averaging'),
        (STRATEGY_GRID, 'Grid Trading'),
        (STRATEGY_TWAP, 'Time-Weighted Average Price'),
        (STRATEGY_VWAP, 'Volume-Weighted Average Price'),
    ]
    
    # Primary fields
    backtest_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this backtest"
    )
    
    strategy_type = models.CharField(
        max_length=20,
        choices=STRATEGY_CHOICES,
        help_text="Type of strategy to backtest"
    )
    
    token_symbol = models.CharField(
        max_length=20,
        help_text="Token symbol (e.g., ETH, WBTC)"
    )
    
    # Date range
    start_date = models.DateTimeField(
        help_text="Start of backtest period"
    )
    
    end_date = models.DateTimeField(
        help_text="End of backtest period"
    )
    
    interval = models.CharField(
        max_length=10,
        default='1h',
        help_text="Data interval (e.g., 1h, 1d)"
    )
    
    # Configuration
    initial_balance_usd = models.DecimalField(
        max_digits=28,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Starting balance in USD"
    )
    
    strategy_params = models.JSONField(
        default=dict,
        help_text="Strategy-specific parameters"
    )
    
    fee_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.30'),
        validators=[
            MinValueValidator(Decimal('0.00')),
            MaxValueValidator(Decimal('10.00'))
        ],
        help_text="Trading fee percentage"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        help_text="Current status of backtest"
    )
    
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text="Error details if backtest failed"
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When backtest was created"
    )
    
    completed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When backtest completed"
    )
    
    # Metadata
    data_points = models.IntegerField(
        default=0,
        help_text="Number of historical data points used"
    )
    
    class Meta:
        db_table = 'paper_backtest_runs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['strategy_type', '-created_at']),
            models.Index(fields=['token_symbol', '-created_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self) -> str:
        """String representation."""
        return f"{self.strategy_type} backtest on {self.token_symbol} ({self.created_at.date()})"
    
    def duration_seconds(self) -> int:
        """Calculate backtest duration in seconds."""
        if self.completed_at and self.created_at:
            return int((self.completed_at - self.created_at).total_seconds())
        return 0
    
    def duration_display(self) -> str:
        """Human-readable duration."""
        seconds = self.duration_seconds()
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"


# =============================================================================
# BACKTEST RESULT MODEL
# =============================================================================

class BacktestResult(models.Model):
    """
    Stores the results and metrics from a backtest run.
    
    One-to-one relationship with BacktestRun.
    Contains all performance metrics and trade details.
    
    Fields:
        backtest_run: Related BacktestRun (one-to-one)
        final_balance_usd: Ending balance
        profit_loss_usd: Total profit/loss
        return_percent: Return percentage
        total_fees_usd: Total trading fees paid
        num_trades: Total number of trades
        num_buys: Number of buy trades
        num_sells: Number of sell trades
        avg_entry_price: Average entry price
        win_rate_percent: Percentage of winning trades
        profit_factor: Gross profit / gross loss
        max_drawdown_percent: Maximum drawdown
        sharpe_ratio: Risk-adjusted return
        sortino_ratio: Downside risk-adjusted return
        trades_data: JSON with all trade details
        metrics_data: JSON with additional metrics
    """
    
    # Relationship to BacktestRun
    backtest_run = models.OneToOneField(
        BacktestRun,
        on_delete=models.CASCADE,
        related_name='result',
        primary_key=True,
        help_text="Related backtest run"
    )
    
    # Final results
    final_balance_usd = models.DecimalField(
        max_digits=28,
        decimal_places=2,
        help_text="Final balance in USD"
    )
    
    profit_loss_usd = models.DecimalField(
        max_digits=28,
        decimal_places=2,
        help_text="Total profit or loss in USD"
    )
    
    return_percent = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Return percentage"
    )
    
    # Trade statistics
    total_fees_usd = models.DecimalField(
        max_digits=28,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total trading fees paid"
    )
    
    num_trades = models.IntegerField(
        default=0,
        help_text="Total number of trades"
    )
    
    num_buys = models.IntegerField(
        default=0,
        help_text="Number of buy trades"
    )
    
    num_sells = models.IntegerField(
        default=0,
        help_text="Number of sell trades"
    )
    
    avg_entry_price = models.DecimalField(
        max_digits=28,
        decimal_places=8,
        default=Decimal('0.00'),
        help_text="Average entry price"
    )
    
    # Performance metrics
    win_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[
            MinValueValidator(Decimal('0.00')),
            MaxValueValidator(Decimal('100.00'))
        ],
        help_text="Percentage of winning trades"
    )
    
    profit_factor = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Gross profit / gross loss ratio"
    )
    
    max_drawdown_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Maximum drawdown percentage"
    )
    
    sharpe_ratio = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Sharpe ratio (risk-adjusted return)"
    )
    
    sortino_ratio = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Sortino ratio (downside risk-adjusted return)"
    )
    
    avg_holding_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Average holding period in hours"
    )
    
    # Consecutive statistics
    max_consecutive_wins = models.IntegerField(
        default=0,
        help_text="Maximum consecutive winning trades"
    )
    
    max_consecutive_losses = models.IntegerField(
        default=0,
        help_text="Maximum consecutive losing trades"
    )
    
    # Detailed data (JSON)
    trades_data = models.JSONField(
        default=list,
        help_text="Detailed list of all simulated trades"
    )
    
    metrics_data = models.JSONField(
        default=dict,
        help_text="Additional metrics and statistics"
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When result was created"
    )
    
    class Meta:
        db_table = 'paper_backtest_results'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-return_percent']),
            models.Index(fields=['-sharpe_ratio']),
            models.Index(fields=['-win_rate_percent']),
        ]
    
    def __str__(self) -> str:
        """String representation."""
        return f"Result for {self.backtest_run.strategy_type} backtest: {self.return_percent}%"
    
    def is_profitable(self) -> bool:
        """Check if backtest was profitable."""
        return self.return_percent > Decimal('0.00')
    
    def performance_grade(self) -> str:
        """
        Get performance grade based on return %.
        
        Returns:
            Grade string (A+, A, B, C, D, F)
        """
        if self.return_percent >= Decimal('50.00'):
            return 'A+'
        elif self.return_percent >= Decimal('25.00'):
            return 'A'
        elif self.return_percent >= Decimal('10.00'):
            return 'B'
        elif self.return_percent >= Decimal('0.00'):
            return 'C'
        elif self.return_percent >= Decimal('-10.00'):
            return 'D'
        else:
            return 'F'
