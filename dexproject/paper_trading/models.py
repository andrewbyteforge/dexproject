"""
Paper Trading Models

Separate models for paper trading to keep simulation data
isolated from real trading data.

File: dexproject/paper_trading/models.py
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
import uuid


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
        help_text="Account name (e.g., 'Conservative Strategy', 'High Risk')"
    )
    
    # Virtual balances
    initial_balance_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('10000.00'),
        help_text="Starting virtual USD balance"
    )
    current_balance_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('10000.00')
    )
    
    # Virtual ETH for gas
    eth_balance = models.DecimalField(
        max_digits=20,
        decimal_places=18,
        default=Decimal('1.0'),
        help_text="Virtual ETH for gas fees"
    )
    
    # Performance metrics
    total_trades = models.IntegerField(default=0)
    successful_trades = models.IntegerField(default=0)
    failed_trades = models.IntegerField(default=0)
    total_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0')
    )
    total_fees_paid_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0')
    )
    
    # Account status
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
        return f"{self.user.username} - {self.name}"
    
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
        unique_together = [
            ['account', 'token_address', 'is_open']
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
