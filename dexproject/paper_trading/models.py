"""
Paper Trading Models - Complete with PTphase1 Enhancements

This module includes both the existing paper trading models and the
enhanced models required for Phase 1:
- PaperAIThoughtLog: AI decision tracking
- PaperStrategyConfiguration: Bot settings
- PaperPerformanceMetrics: Analytics
- PaperTradingSession: Bot runtime tracking

File: dexproject/paper_trading/models.py
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
import uuid
import json
from typing import Dict, Any, Optional


# =============================================================================
# EXISTING MODELS (Already in the system)
# =============================================================================

class PaperTradingAccount(models.Model):
    """
    Virtual trading account for paper trading.
    
    Each user can have multiple paper trading accounts
    to test different strategies.
    """
    
    account_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='paper_accounts'
    )
    name = models.CharField(
        max_length=100,
        help_text="Account name for identification"
    )
    
    # Account balance
    initial_balance_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('10000.00'),
        help_text="Starting balance in USD"
    )
    current_balance_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('10000.00'),
        help_text="Current balance in USD"
    )
    eth_balance = models.DecimalField(
        max_digits=36,
        decimal_places=18,
        default=Decimal('1.0'),
        help_text="ETH balance for gas simulation"
    )
    
    # Performance tracking
    total_trades = models.IntegerField(default=0)
    successful_trades = models.IntegerField(default=0)
    failed_trades = models.IntegerField(default=0)
    total_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Total profit/loss in USD"
    )
    total_fees_paid_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Total gas fees paid"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reset_count = models.IntegerField(
        default=0,
        help_text="Number of times account has been reset"
    )
    
    class Meta:
        db_table = 'paper_trading_accounts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.user.username})"
    
    def reset_account(self):
        """Reset account to initial state."""
        self.current_balance_usd = self.initial_balance_usd
        self.eth_balance = Decimal('1.0')
        self.total_trades = 0
        self.successful_trades = 0
        self.failed_trades = 0
        self.total_pnl_usd = Decimal('0')
        self.total_fees_paid_usd = Decimal('0')
        self.reset_count += 1
        self.save()
    
    @property
    def win_rate(self):
        """Calculate win rate percentage."""
        if self.total_trades == 0:
            return 0
        return (self.successful_trades / self.total_trades) * 100
    
    @property
    def total_return_percent(self):
        """Calculate total return percentage."""
        if self.initial_balance_usd == 0:
            return 0
        return ((self.current_balance_usd - self.initial_balance_usd) / 
                self.initial_balance_usd * 100)


class PaperTrade(models.Model):
    """
    Individual paper trade record.
    
    Stores all simulated trades with realistic execution details.
    """
    
    TRADE_STATUS = (
        ('pending', 'Pending'),
        ('executing', 'Executing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    )
    
    TRADE_TYPES = (
        ('buy', 'Buy'),
        ('sell', 'Sell'),
        ('swap', 'Swap'),
    )
    
    # Identity
    trade_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    account = models.ForeignKey(
        PaperTradingAccount,
        on_delete=models.CASCADE,
        related_name='trades'
    )
    
    # Trade details
    trade_type = models.CharField(
        max_length=10,
        choices=TRADE_TYPES
    )
    token_in_address = models.CharField(max_length=42)
    token_in_symbol = models.CharField(max_length=20)
    token_out_address = models.CharField(max_length=42)
    token_out_symbol = models.CharField(max_length=20)
    
    # Amounts
    amount_in = models.DecimalField(
        max_digits=36,
        decimal_places=18,
        help_text="Amount in (wei)"
    )
    amount_in_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2
    )
    expected_amount_out = models.DecimalField(
        max_digits=36,
        decimal_places=18
    )
    actual_amount_out = models.DecimalField(
        max_digits=36,
        decimal_places=18,
        null=True,
        blank=True
    )
    
    # Execution details
    simulated_gas_price_gwei = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    simulated_gas_used = models.IntegerField()
    simulated_gas_cost_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    simulated_slippage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )
    
    # Timing
    created_at = models.DateTimeField(auto_now_add=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    execution_time_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Simulated execution time in milliseconds"
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=TRADE_STATUS,
        default='pending'
    )
    error_message = models.TextField(blank=True)
    
    # Mock transaction details
    mock_tx_hash = models.CharField(
        max_length=66,
        blank=True,
        help_text="Simulated transaction hash"
    )
    mock_block_number = models.IntegerField(null=True, blank=True)
    
    # Strategy reference (optional)
    strategy_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Trading strategy used"
    )
    
    class Meta:
        db_table = 'paper_trades'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['trade_type']),
        ]
    
    def __str__(self):
        return f"Paper Trade {self.trade_id} - {self.trade_type}"
    
    def calculate_pnl(self):
        """Calculate P&L for this trade."""
        if self.status != 'completed':
            return Decimal('0')
        
        # Calculate based on trade type
        if self.trade_type == 'sell':
            # For sells, P&L is the USD received minus gas
            return self.amount_in_usd - self.simulated_gas_cost_usd
        else:
            # For buys, we need position tracking (simplified here)
            return Decimal('0')


class PaperPosition(models.Model):
    """
    Open positions in paper trading account.
    
    Tracks simulated holdings and unrealized P&L.
    """
    
    position_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    account = models.ForeignKey(
        PaperTradingAccount,
        on_delete=models.CASCADE,
        related_name='positions'
    )
    
    # Token details
    token_address = models.CharField(max_length=42)
    token_symbol = models.CharField(max_length=20)
    
    # Position details
    quantity = models.DecimalField(
        max_digits=36,
        decimal_places=18
    )
    average_entry_price_usd = models.DecimalField(
        max_digits=20,
        decimal_places=6
    )
    current_price_usd = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True
    )
    
    # P&L tracking
    total_invested_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2
    )
    current_value_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True
    )
    unrealized_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0')
    )
    realized_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0')
    )
    
    # Risk management
    stop_loss_price = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True
    )
    take_profit_price = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True
    )
    
    # Status
    is_open = models.BooleanField(default=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'paper_positions'
        ordering = ['-opened_at']
        indexes = [
            models.Index(fields=['account', 'is_open']),
            models.Index(fields=['token_address']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['account', 'token_address'],
                condition=models.Q(is_open=True),
                name='unique_open_position_per_token'
            )
        ]
    
    def __str__(self):
        return f"{self.token_symbol} Position - {self.quantity}"
    
    def update_price(self, new_price_usd):
        """Update current price and calculate unrealized P&L."""
        self.current_price_usd = new_price_usd
        self.current_value_usd = self.quantity * new_price_usd
        self.unrealized_pnl_usd = self.current_value_usd - self.total_invested_usd
        self.last_updated = timezone.now()
        self.save()
    
    def close_position(self, exit_price_usd):
        """Close position and calculate realized P&L."""
        self.current_price_usd = exit_price_usd
        self.current_value_usd = self.quantity * exit_price_usd
        self.realized_pnl_usd = self.current_value_usd - self.total_invested_usd
        self.unrealized_pnl_usd = Decimal('0')
        self.is_open = False
        self.closed_at = timezone.now()
        self.save()


class PaperTradingConfig(models.Model):
    """
    Configuration for paper trading simulation parameters.
    
    Allows customization of simulation behavior per account.
    """
    
    account = models.OneToOneField(
        PaperTradingAccount,
        on_delete=models.CASCADE,
        related_name='config'
    )
    
    # Simulation parameters
    base_slippage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.5'),
        help_text="Base slippage percentage for all trades"
    )
    gas_price_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.0'),
        help_text="Multiplier for gas price simulation"
    )
    execution_delay_ms = models.IntegerField(
        default=500,
        help_text="Simulated execution delay in milliseconds"
    )
    
    # Risk limits
    max_position_size_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('10.0'),
        help_text="Max position size as % of portfolio"
    )
    max_daily_trades = models.IntegerField(
        default=50,
        help_text="Maximum trades per day"
    )
    stop_loss_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.0'),
        help_text="Default stop loss percentage"
    )
    
    # Realistic simulation
    simulate_network_issues = models.BooleanField(
        default=True,
        help_text="Simulate occasional network failures"
    )
    simulate_mev = models.BooleanField(
        default=True,
        help_text="Simulate MEV bot competition"
    )
    failure_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('2.0'),
        help_text="Percentage of trades that should randomly fail"
    )
    
    class Meta:
        db_table = 'paper_trading_configs'
    
    def __str__(self):
        return f"Config for {self.account.name}"


# =============================================================================
# ENHANCED MODELS FOR PTPHASE1
# =============================================================================

class PaperAIThoughtLog(models.Model):
    """
    Records the AI's reasoning process for each paper trading decision.
    
    Simplified version for paper trading that tracks decision reasoning
    without the full complexity of the main analytics.ThoughtLog model.
    """
    
    class DecisionType(models.TextChoices):
        """Types of trading decisions."""
        BUY = 'BUY', 'Buy'
        SELL = 'SELL', 'Sell'  
        HOLD = 'HOLD', 'Hold'
        SKIP = 'SKIP', 'Skip'
        STOP_LOSS = 'STOP_LOSS', 'Stop Loss'
        TAKE_PROFIT = 'TAKE_PROFIT', 'Take Profit'
    
    class ConfidenceLevel(models.TextChoices):
        """Confidence levels for decisions."""
        VERY_HIGH = 'VERY_HIGH', 'Very High (90-100%)'
        HIGH = 'HIGH', 'High (70-90%)'
        MEDIUM = 'MEDIUM', 'Medium (50-70%)'
        LOW = 'LOW', 'Low (30-50%)'
        VERY_LOW = 'VERY_LOW', 'Very Low (<30%)'
    
    # Identity
    thought_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this thought log"
    )
    
    # Relationship to paper trade
    paper_trade = models.ForeignKey(
        'PaperTrade',
        on_delete=models.CASCADE,
        related_name='thought_logs',
        null=True,
        blank=True,
        help_text="Associated paper trade (if executed)"
    )
    
    account = models.ForeignKey(
        'PaperTradingAccount',
        on_delete=models.CASCADE,
        related_name='thought_logs',
        help_text="Paper trading account"
    )
    
    # Decision details
    decision_type = models.CharField(
        max_length=20,
        choices=DecisionType.choices,
        help_text="Type of decision made"
    )
    
    token_address = models.CharField(
        max_length=42,
        help_text="Token being analyzed"
    )
    
    token_symbol = models.CharField(
        max_length=20,
        help_text="Token symbol"
    )
    
    # Confidence and scoring
    confidence_level = models.CharField(
        max_length=20,
        choices=ConfidenceLevel.choices,
        help_text="Confidence level category"
    )
    
    confidence_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Exact confidence percentage (0-100)"
    )
    
    risk_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Risk assessment score (0-100, higher is riskier)"
    )
    
    opportunity_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Opportunity assessment score (0-100)"
    )
    
    # Reasoning
    primary_reasoning = models.TextField(
        help_text="Primary reasoning for the decision (1-3 sentences)"
    )
    
    key_factors = models.JSONField(
        default=list,
        help_text="Key factors that influenced the decision"
    )
    
    positive_signals = models.JSONField(
        default=list,
        help_text="Positive signals identified"
    )
    
    negative_signals = models.JSONField(
        default=list,
        help_text="Negative signals/risks identified"  
    )
    
    # Market data at decision time
    market_data = models.JSONField(
        default=dict,
        help_text="Market data snapshot at decision time"
    )
    
    # Strategy used
    strategy_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Strategy that generated this decision"
    )
    
    lane_used = models.CharField(
        max_length=20,
        choices=[('FAST', 'Fast Lane'), ('SMART', 'Smart Lane')],
        default='FAST',
        help_text="Which lane was used for analysis"
    )
    
    # Timing
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the thought was generated"
    )
    
    analysis_time_ms = models.IntegerField(
        default=0,
        help_text="Time taken for analysis in milliseconds"
    )
    
    class Meta:
        """Meta configuration."""
        db_table = 'paper_ai_thought_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', 'created_at']),
            models.Index(fields=['decision_type']),
            models.Index(fields=['confidence_level']),
            models.Index(fields=['token_address']),
        ]
    
    def __str__(self) -> str:
        """String representation."""
        return f"Thought {self.thought_id}: {self.decision_type} {self.token_symbol}"


class PaperStrategyConfiguration(models.Model):
    """
    Configuration for paper trading strategies.
    
    Stores bot settings for Fast/Smart lane strategies and
    trading parameters.
    """
    
    class TradingMode(models.TextChoices):
        """Trading mode options."""
        CONSERVATIVE = 'CONSERVATIVE', 'Conservative'
        MODERATE = 'MODERATE', 'Moderate'
        AGGRESSIVE = 'AGGRESSIVE', 'Aggressive'
        CUSTOM = 'CUSTOM', 'Custom'
    
    # Identity
    config_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    account = models.ForeignKey(
        'PaperTradingAccount',
        on_delete=models.CASCADE,
        related_name='strategy_configs'
    )
    
    name = models.CharField(
        max_length=100,
        help_text="Configuration name"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this configuration is active"
    )
    
    # Trading mode
    trading_mode = models.CharField(
        max_length=20,
        choices=TradingMode.choices,
        default=TradingMode.MODERATE
    )
    
    # Lane preferences
    use_fast_lane = models.BooleanField(
        default=True,
        help_text="Enable Fast Lane trading"
    )
    
    use_smart_lane = models.BooleanField(
        default=False,
        help_text="Enable Smart Lane trading"
    )
    
    fast_lane_threshold_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('100'),
        help_text="Max trade size for Fast Lane"
    )
    
    # Risk management
    max_position_size_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.0'),
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('100'))],
        help_text="Max position size as % of portfolio"
    )
    
    stop_loss_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.0'),
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('50'))],
        help_text="Default stop loss percentage"
    )
    
    take_profit_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('10.0'),
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('1000'))],
        help_text="Default take profit percentage"
    )
    
    max_daily_trades = models.IntegerField(
        default=20,
        validators=[MinValueValidator(1), MaxValueValidator(1000)],
        help_text="Maximum trades per day"
    )
    
    max_concurrent_positions = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Maximum concurrent open positions"
    )
    
    # Trading parameters
    min_liquidity_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('10000'),
        help_text="Minimum liquidity required"
    )
    
    max_slippage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.0'),
        validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(Decimal('10'))],
        help_text="Maximum allowed slippage"
    )
    
    confidence_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('60'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Minimum confidence for trades"
    )
    
    # Token filters
    allowed_tokens = models.JSONField(
        default=list,
        blank=True,
        help_text="List of allowed token addresses"
    )
    
    blocked_tokens = models.JSONField(
        default=list,
        blank=True,
        help_text="List of blocked token addresses"
    )
    
    # Advanced settings
    custom_parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Custom strategy parameters"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        """Meta configuration."""
        db_table = 'paper_strategy_configs'
        ordering = ['-updated_at']
        unique_together = [['account', 'name']]
    
    def __str__(self) -> str:
        """String representation."""
        return f"{self.name} ({self.trading_mode})"


class PaperPerformanceMetrics(models.Model):
    """
    Tracks performance metrics for paper trading sessions.
    
    Calculates and stores key performance indicators (KPIs)
    for analysis and improvement.
    """
    
    # Identity
    metrics_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    session = models.ForeignKey(
        'PaperTradingSession',
        on_delete=models.CASCADE,
        related_name='performance_metrics'
    )
    
    # Time period
    period_start = models.DateTimeField(
        help_text="Start of measurement period"
    )
    
    period_end = models.DateTimeField(
        help_text="End of measurement period"
    )
    
    # Trade statistics
    total_trades = models.IntegerField(default=0)
    winning_trades = models.IntegerField(default=0)
    losing_trades = models.IntegerField(default=0)
    
    win_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Win rate percentage"
    )
    
    # Financial metrics
    total_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Total P&L in USD"
    )
    
    total_pnl_percent = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Total P&L as percentage"
    )
    
    avg_win_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Average winning trade in USD"
    )
    
    avg_loss_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Average losing trade in USD"
    )
    
    largest_win_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0')
    )
    
    largest_loss_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0')
    )
    
    # Risk metrics
    sharpe_ratio = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Sharpe ratio"
    )
    
    max_drawdown_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Maximum drawdown percentage"
    )
    
    profit_factor = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Profit factor (gross profit / gross loss)"
    )
    
    # Execution metrics
    avg_execution_time_ms = models.IntegerField(
        default=0,
        help_text="Average trade execution time"
    )
    
    total_gas_fees_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Total gas fees paid"
    )
    
    avg_slippage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Average slippage percentage"
    )
    
    # Strategy metrics
    fast_lane_trades = models.IntegerField(default=0)
    smart_lane_trades = models.IntegerField(default=0)
    
    fast_lane_win_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0')
    )
    
    smart_lane_win_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0')
    )
    
    # Timestamps
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        """Meta configuration."""
        db_table = 'paper_performance_metrics'
        ordering = ['-period_end']
        indexes = [
            models.Index(fields=['session', 'period_end']),
            models.Index(fields=['win_rate']),
            models.Index(fields=['total_pnl_percent']),
        ]
    
    def __str__(self) -> str:
        """String representation."""
        return f"Metrics for {self.session}: {self.win_rate}% win rate"


class PaperTradingSession(models.Model):
    """
    Represents a paper trading bot session.
    
    Tracks when the bot is running, its configuration, and
    overall session statistics.
    """
    
    class SessionStatus(models.TextChoices):
        """Session status options."""
        STARTING = 'STARTING', 'Starting'
        RUNNING = 'RUNNING', 'Running'
        PAUSED = 'PAUSED', 'Paused'
        STOPPING = 'STOPPING', 'Stopping'
        STOPPED = 'STOPPED', 'Stopped'
        ERROR = 'ERROR', 'Error'
    
    # Identity
    session_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    account = models.ForeignKey(
        'PaperTradingAccount',
        on_delete=models.CASCADE,
        related_name='trading_sessions'
    )
    
    strategy_config = models.ForeignKey(
        'PaperStrategyConfiguration',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sessions'
    )
    
    # Session details
    name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Session name/description"
    )
    
    status = models.CharField(
        max_length=20,
        choices=SessionStatus.choices,
        default=SessionStatus.STARTING
    )
    
    # Timing
    started_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the session started"
    )
    
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the session ended"
    )
    
    last_heartbeat = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last activity timestamp"
    )
    
    # Statistics
    total_trades_executed = models.IntegerField(default=0)
    successful_trades = models.IntegerField(default=0)
    failed_trades = models.IntegerField(default=0)
    
    session_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Total P&L for this session"
    )
    
    starting_balance_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Balance at session start"
    )
    
    ending_balance_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Balance at session end"
    )
    
    # Error tracking
    error_count = models.IntegerField(default=0)
    last_error_message = models.TextField(blank=True)
    last_error_time = models.DateTimeField(null=True, blank=True)
    
    # Configuration snapshot
    config_snapshot = models.JSONField(
        default=dict,
        help_text="Strategy configuration at session start"
    )
    
    # Metadata
    notes = models.TextField(
        blank=True,
        help_text="Session notes or observations"
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
    
    def __str__(self) -> str:
        """String representation."""
        return f"Session {self.session_id}: {self.status}"
    
    @property
    def duration_seconds(self) -> Optional[int]:
        """Calculate session duration in seconds."""
        if self.ended_at and self.started_at:
            delta = self.ended_at - self.started_at
            return int(delta.total_seconds())
        elif self.started_at:
            delta = timezone.now() - self.started_at
            return int(delta.total_seconds())
        return None
    
    @property
    def is_active(self) -> bool:
        """Check if session is currently active."""
        return self.status in ['STARTING', 'RUNNING', 'PAUSED']
    
    def update_heartbeat(self) -> None:
        """Update the last heartbeat timestamp."""
        self.last_heartbeat = timezone.now()
        self.save(update_fields=['last_heartbeat'])
    
    def stop_session(self, reason: str = "") -> None:
        """Stop the trading session."""
        self.status = self.SessionStatus.STOPPED
        self.ended_at = timezone.now()
        if reason:
            self.notes = f"{self.notes}\nStopped: {reason}".strip()
        
        # Calculate final balance
        if self.account:
            self.ending_balance_usd = self.account.current_balance_usd
        
        self.save()