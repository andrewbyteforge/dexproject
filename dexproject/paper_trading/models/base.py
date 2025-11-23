"""
Paper Trading Base Models

Core models for paper trading infrastructure including accounts, trades,
positions, and basic configuration. These are the fundamental building blocks
for the paper trading system.

File: dexproject/paper_trading/models/base.py
"""
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid
import logging
from typing import Optional

logger = logging.getLogger(__name__)


from decimal import Decimal, InvalidOperation
from typing import Optional
import logging
from django.core.exceptions import ValidationError


def validate_decimal_field(
    value: Optional[Decimal],
    field_name: str,
    min_value: Optional[Decimal] = None,
    max_value: Optional[Decimal] = None,
    default_value: Decimal = Decimal('0.00'),
    decimal_places: int = 2
) -> Decimal:
    """
    Validate and clean decimal field values.
    
    Prevents scientific notation and ensures proper decimal formatting.
    Quantizes values to match database field precision.
    
    Args:
        value: Decimal value to validate
        field_name: Name of field (for logging)
        min_value: Minimum allowed value (optional)
        max_value: Maximum allowed value (optional)
        default_value: Default value if validation fails
        decimal_places: Number of decimal places for quantization (default: 2)
        
    Returns:
        Validated and quantized Decimal value
        
    Raises:
        ValidationError: If value is invalid and cannot be corrected
    """
    logger = logging.getLogger(__name__)
    
    # Handle None values
    if value is None:
        logger.debug(f"[VALIDATION] {field_name} is None, using default: {default_value}")
        return default_value
    
    # Check for NaN as string BEFORE conversion to Decimal
    if isinstance(value, str) and value.lower() in ('nan', 'inf', '-inf', 'infinity', '-infinity'):
        logger.warning(f"[VALIDATION] {field_name} is {value}, using default: {default_value}")
        return default_value
    
    try:
        # Convert to Decimal if not already
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        
        # Check for scientific notation in string representation
        value_str = str(value)
        if 'e' in value_str.lower() or 'E' in value_str:
            logger.warning(f"[VALIDATION] {field_name} has scientific notation: {value_str}")
            # Convert properly without scientific notation
            value = Decimal(value).quantize(Decimal('0.00000001'))
        
        # Check for NaN
        if value.is_nan():
            logger.error(f"[VALIDATION] {field_name} is NaN, using default: {default_value}")
            return default_value
        
        # Check for Infinity
        if value.is_infinite():
            logger.error(f"[VALIDATION] {field_name} is Infinite, using default: {default_value}")
            return default_value
        
        # Validate minimum value
        if min_value is not None and value < min_value:
            logger.warning(
                f"[VALIDATION] {field_name} too small: {value} < {min_value}, "
                f"using minimum: {min_value}"
            )
            value = min_value
        
        # Validate maximum value
        if max_value is not None and value > max_value:
            logger.warning(
                f"[VALIDATION] {field_name} too large: {value} > {max_value}, "
                f"using maximum: {max_value}"
            )
            value = max_value
        
        # Check if value is suspiciously large (likely a wei value used as USD)
        if field_name.endswith('_usd') and value > Decimal('1000000'):
            logger.error(
                f"[VALIDATION] {field_name} suspiciously large: {value}. "
                f"This might be a wei value mistakenly used as USD. Using default: {default_value}"
            )
            return default_value
        
        # CRITICAL: Quantize to match the database field's decimal_places
        # This prevents decimal.InvalidOperation when reading from database
        try:
            if decimal_places == 2:
                quantize_pattern = Decimal('0.01')
            elif decimal_places == 18:
                quantize_pattern = Decimal('0.000000000000000001')
            else:
                quantize_pattern = Decimal(10) ** -decimal_places
            
            # Attempt quantization
            quantized_value = value.quantize(quantize_pattern)
            
            # CRITICAL: Check if quantization produced NaN or Infinity
            if quantized_value.is_nan() or quantized_value.is_infinite():
                logger.error(
                    f"[VALIDATION] {field_name} quantization produced NaN/Inf for value {value}. "
                    f"Using default: {default_value}"
                )
                return default_value
            
            value = quantized_value
            logger.debug(f"[VALIDATION] {field_name} validated and quantized to {decimal_places} places: {value}")
            return value
            
        except (InvalidOperation, ValueError) as e:
            logger.error(
                f"[VALIDATION] Quantization failed for {field_name}: {value} - {e}. "
                f"Using default: {default_value}"
            )
            return default_value
        
    except (InvalidOperation, ValueError, TypeError) as e:
        logger.error(
            f"[VALIDATION] Failed to validate {field_name}: {value} - {e}. "
            f"Using default: {default_value}"
        )
        return default_value


# =============================================================================
# CORE PAPER TRADING MODELS
# =============================================================================

class PaperTradingAccount(models.Model):
    """
    Virtual trading account for paper trading.
    
    Each user can have multiple paper trading accounts to test different
    strategies without risking real funds.
    
    Attributes:
        account_id: Unique identifier (UUID)
        user: Owner of the account
        name: Account name for identification
        description: Optional account description
        initial_balance_usd: Starting virtual balance
        current_balance_usd: Current virtual balance
        is_active: Whether account is active
        created_at: Account creation timestamp
        last_activity: Last activity timestamp
        total_trades: Total number of trades executed
        winning_trades: Number of profitable trades
        losing_trades: Number of losing trades
        total_profit_loss_usd: Total P&L in USD
    """
    
    # Identity
    account_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique account identifier"
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='paper_accounts',
        help_text="Account owner"
    )
    
    name = models.CharField(
        max_length=100,
        help_text="Account name"
    )
    
    description = models.TextField(
        blank=True,
        help_text="Account description"
    )
    
    # Balance tracking
    initial_balance_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('10000.00'),
        help_text="Starting virtual balance in USD"
    )
    
    current_balance_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('10000.00'),
        help_text="Current virtual balance in USD"
    )
    
    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether account is active"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Account creation timestamp"
    )
    
    last_activity = models.DateTimeField(
        auto_now=True,
        help_text="Last activity timestamp"
    )
    
    # Statistics
    total_trades = models.IntegerField(
        default=0,
        help_text="Total number of trades"
    )
    
    winning_trades = models.IntegerField(
        default=0,
        help_text="Number of winning trades"
    )
    
    losing_trades = models.IntegerField(
        default=0,
        help_text="Number of losing trades"
    )
    
    total_profit_loss_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total profit/loss in USD"
    )
    
    class Meta:
        """Meta configuration."""
        db_table = 'paper_trading_accounts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'Paper Trading Account'
        verbose_name_plural = 'Paper Trading Accounts'
    
    def __str__(self) -> str:
        """String representation."""
        return f"{self.name} ({self.user.username})"
    
    def get_win_rate(self) -> Decimal:
        """
        Calculate win rate percentage.
        
        Returns:
            Win rate as percentage (0-100)
        """
        try:
            if self.total_trades == 0:
                return Decimal('0')
            win_rate = (Decimal(self.winning_trades) / Decimal(self.total_trades)) * Decimal('100')
            return win_rate.quantize(Decimal('0.01'))
        except Exception as e:
            logger.error(f"Error calculating win rate for account {self.account_id}: {e}")
            return Decimal('0')
    
    def get_roi(self) -> Decimal:
        """
        Calculate return on investment percentage.
        
        Returns:
            ROI as percentage
        """
        try:
            if self.initial_balance_usd == 0:
                return Decimal('0')
            roi = (self.total_profit_loss_usd / self.initial_balance_usd) * Decimal('100')
            return roi.quantize(Decimal('0.01'))
        except Exception as e:
            logger.error(f"Error calculating ROI for account {self.account_id}: {e}")
            return Decimal('0')


class PaperTrade(models.Model):
    """
    Individual simulated trade record.
    
    Stores all simulated trades with realistic execution details including
    gas costs, slippage, timing, and execution status.
    
    Attributes:
        trade_id: Unique identifier (UUID)
        account: Associated trading account
        trade_type: Type of trade (buy/sell/swap)
        token_in_address: Input token contract address
        token_in_symbol: Input token symbol
        token_out_address: Output token contract address
        token_out_symbol: Output token symbol
        amount_in: Input amount in wei
        amount_in_usd: Input amount in USD
        expected_amount_out: Expected output amount in wei
        actual_amount_out: Actual output amount in wei
        simulated_gas_price_gwei: Simulated gas price
        simulated_gas_used: Simulated gas units used
        simulated_gas_cost_usd: Simulated gas cost in USD
        simulated_slippage_percent: Simulated slippage percentage
        created_at: Trade creation timestamp
        executed_at: Trade execution timestamp
        execution_time_ms: Simulated execution time in milliseconds
        status: Current trade status
        error_message: Error message if failed
        mock_tx_hash: Simulated transaction hash
        mock_block_number: Simulated block number
        strategy_name: Strategy that generated this trade
        metadata: Additional context (AI decisions, etc.)
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
        editable=False,
        help_text="Unique trade identifier"
    )
    
    account = models.ForeignKey(
        PaperTradingAccount,
        on_delete=models.CASCADE,
        related_name='trades',
        help_text="Associated account"
    )
    
    # Trade details
    trade_type = models.CharField(
        max_length=10,
        choices=TRADE_TYPES,
        help_text="Type of trade"
    )
    
    token_in_address = models.CharField(
        max_length=42,
        help_text="Input token address"
    )
    
    token_in_symbol = models.CharField(
        max_length=20,
        help_text="Input token symbol"
    )
    
    token_out_address = models.CharField(
        max_length=42,
        help_text="Output token address"
    )
    
    token_out_symbol = models.CharField(
        max_length=20,
        help_text="Output token symbol"
    )
    
    # Amounts
    amount_in = models.DecimalField(
        max_digits=36,
        decimal_places=18,
        default=Decimal('0'),
        help_text="Amount in (wei)"
    )
    
    amount_in_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('10.00'),
        help_text="Amount in USD"
    )
    
    expected_amount_out = models.DecimalField(
        max_digits=36,
        decimal_places=18,
        default=Decimal('0'),
        help_text="Expected output amount"
    )
    
    actual_amount_out = models.DecimalField(
        max_digits=36,
        decimal_places=18,
        null=True,
        blank=True,
        default=None,
        help_text="Actual output amount"
    )
    
    # Execution details
    simulated_gas_price_gwei = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('1.0'),
        help_text="Simulated gas price"
    )
    
    simulated_gas_used = models.IntegerField(
        default=21000,
        help_text="Simulated gas units used"
    )
    
    simulated_gas_cost_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.50'),
        help_text="Simulated gas cost in USD"
    )
    
    simulated_slippage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.50'),
        help_text="Simulated slippage percentage"
    )
    
    # Timing
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Trade creation timestamp"
    )
    
    executed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Trade execution timestamp"
    )
    
    execution_time_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Simulated execution time in milliseconds"
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=TRADE_STATUS,
        default='pending',
        help_text="Current trade status"
    )
    
    error_message = models.TextField(
        blank=True,
        help_text="Error message if failed"
    )
    
    # Mock transaction details
    mock_tx_hash = models.CharField(
        max_length=66,
        blank=True,
        help_text="Simulated transaction hash"
    )
    
    mock_block_number = models.IntegerField(
        null=True,
        blank=True,
        help_text="Simulated block number"
    )
    
    # Strategy reference
    strategy_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Strategy that generated this trade"
    )

    # Metadata for AI context
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="AI trade context (intel level, confidence, reasoning)"
    )

    def save(self, *args, **kwargs):
        """Validate and clean decimal fields before saving."""
        
        # Convert None to Decimal for required fields with proper defaults
        if self.amount_in is None:
            self.amount_in = Decimal('0')
        if self.amount_in_usd is None:
            self.amount_in_usd = Decimal('10.00')
        if self.expected_amount_out is None:
            self.expected_amount_out = Decimal('0')
        if self.simulated_gas_price_gwei is None:
            self.simulated_gas_price_gwei = Decimal('1.0')
        if self.simulated_gas_cost_usd is None:
            self.simulated_gas_cost_usd = Decimal('0.50')
        if self.simulated_slippage_percent is None:
            self.simulated_slippage_percent = Decimal('0.50')
        
        # Validate token amounts (18 decimal places for wei precision)
        self.amount_in = validate_decimal_field(
            self.amount_in, 'amount_in',
            Decimal('0'), None, Decimal('0'),
            decimal_places=0  # ← Changed from 18 to 0
        )
        
        self.expected_amount_out = validate_decimal_field(
            self.expected_amount_out, 'expected_amount_out',
            Decimal('0'), None, Decimal('0'),
            decimal_places=0  # ← Changed from 18 to 0
        )
        
        # Validate actual_amount_out (nullable, 18 decimal places)
        if self.actual_amount_out is not None:
            self.actual_amount_out = validate_decimal_field(
                self.actual_amount_out, 'actual_amount_out',
                Decimal('0'), None, Decimal('0'),
                decimal_places=0  # ← Changed from 18 to 0
            )
        
        # Validate USD amounts (2 decimal places: $0.01 to $100,000)
        self.amount_in_usd = validate_decimal_field(
            self.amount_in_usd, 'amount_in_usd',
            Decimal('0.01'), Decimal('100000.00'), Decimal('10.00'),
            decimal_places=2
        )
        
        # Validate gas costs (2 decimal places)
        self.simulated_gas_cost_usd = validate_decimal_field(
            self.simulated_gas_cost_usd, 'simulated_gas_cost_usd',
            Decimal('0.01'), Decimal('500.00'), Decimal('0.50'),
            decimal_places=2
        )

        # Validate slippage (2 decimal places: 0% to 50%)
        self.simulated_slippage_percent = validate_decimal_field(
            self.simulated_slippage_percent, 'simulated_slippage_percent',
            Decimal('0.00'), Decimal('50.00'), Decimal('0.50'),
            decimal_places=2
        )

        # Validate gas price (2 decimal places: 0.1 to 1000 gwei)
        self.simulated_gas_price_gwei = validate_decimal_field(
            self.simulated_gas_price_gwei, 'simulated_gas_price_gwei',
            Decimal('0.1'), Decimal('1000.00'), Decimal('1.0'),
            decimal_places=2
        )

        # Fix gas_used
        if not self.simulated_gas_used or self.simulated_gas_used <= 0:
            self.simulated_gas_used = 21000

        super().save(*args, **kwargs)

    class Meta:
        """Meta configuration."""
        db_table = 'paper_trades'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['trade_type']),
        ]
        verbose_name = 'Paper Trade'
        verbose_name_plural = 'Paper Trades'
    
    def __str__(self) -> str:
        """String representation."""
        return f"{self.trade_type.upper()}: {self.token_in_symbol} → {self.token_out_symbol}"
    

class PaperPosition(models.Model):
    """
    Open position in paper trading account.
    
    Tracks currently held token positions with real-time P&L calculations.
    Positions are marked as closed when fully exited.
    
    Attributes:
        position_id: Unique identifier (UUID)
        account: Associated trading account
        token_address: Token contract address
        token_symbol: Token symbol
        token_name: Token name
        quantity: Amount held (in wei)
        average_entry_price_usd: Average entry price
        total_invested_usd: Total amount invested
        current_price_usd: Current market price
        current_value_usd: Current position value
        unrealized_pnl_usd: Unrealized profit/loss
        realized_pnl_usd: Realized profit/loss after closing
        is_open: Whether position is still open
        opened_at: Position open timestamp
        closed_at: Position close timestamp
        last_updated: Last update timestamp
    """
    
    # Identity
    position_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique position identifier"
    )
    
    account = models.ForeignKey(
        PaperTradingAccount,
        on_delete=models.CASCADE,
        related_name='positions',
        help_text="Associated account"
    )
    
    # Token details
    token_address = models.CharField(
        max_length=42,
        help_text="Token contract address"
    )
    
    token_symbol = models.CharField(
        max_length=20,
        help_text="Token symbol"
    )
    
    token_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Token name"
    )
    
    # Position details
    quantity = models.DecimalField(
        max_digits=36,
        decimal_places=18,
        default=Decimal('0'),  # ADDED DEFAULT to prevent NULL
        help_text="Amount held in wei"
    )
    
    average_entry_price_usd = models.DecimalField(
        max_digits=20,
        decimal_places=18,
        default=Decimal('0'),  # ADDED DEFAULT to prevent NULL
        help_text="Average entry price in USD"
    )
    
    total_invested_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),  # ADDED DEFAULT to prevent NULL
        help_text="Total amount invested"
    )
    
    # Current values
    current_price_usd = models.DecimalField(
        max_digits=20,
        decimal_places=18,
        default=Decimal('0'),  # ADDED DEFAULT to prevent NULL
        help_text="Current market price"
    )
    
    current_value_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),  # ADDED DEFAULT to prevent NULL
        help_text="Current position value"
    )
    
    unrealized_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),  # ADDED DEFAULT to prevent NULL
        help_text="Unrealized profit/loss"
    )
    
    realized_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),
        help_text="Realized profit/loss after closing"
    )
    
    # Status
    is_open = models.BooleanField(
        default=True,
        help_text="Whether position is still open"
    )
    
    opened_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Position open timestamp"
    )
    
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Position close timestamp"
    )
    
    last_updated = models.DateTimeField(
        auto_now=True,
        help_text="Last update timestamp"
    )
    
    class Meta:
        """Meta configuration."""
        db_table = 'paper_positions'
        ordering = ['-opened_at']
        indexes = [
            models.Index(fields=['account', 'is_open']),
            models.Index(fields=['token_address']),
        ]
        unique_together = [['account', 'token_address', 'is_open']]
        verbose_name = 'Paper Position'
        verbose_name_plural = 'Paper Positions'
    
    def __str__(self) -> str:
        """String representation."""
        status = "OPEN" if self.is_open else "CLOSED"
        return f"{status}: {self.quantity} {self.token_symbol}"
    
    def clean(self) -> None:
        """
        Validate all decimal fields before saving.
        
        This prevents decimal.InvalidOperation errors by ensuring all decimal
        values are properly formatted and within valid ranges.
        
        Raises:
            ValidationError: If validation fails critically
        """
        # Validate quantity (wei values, 18 decimal places)
        self.quantity = validate_decimal_field(
            value=self.quantity,
            field_name='quantity',
            min_value=Decimal('0'),
            default_value=Decimal('0'),
            decimal_places=18
        )
        
        # Validate prices (18 decimal places for precision)
        self.average_entry_price_usd = validate_decimal_field(
            value=self.average_entry_price_usd,
            field_name='average_entry_price_usd',
            min_value=Decimal('0'),
            default_value=Decimal('0'),
            decimal_places=18
        )
        
        self.current_price_usd = validate_decimal_field(
            value=self.current_price_usd,
            field_name='current_price_usd',
            min_value=Decimal('0'),
            default_value=Decimal('0'),
            decimal_places=18
        )
        
        # Validate USD values (2 decimal places)
        self.total_invested_usd = validate_decimal_field(
            value=self.total_invested_usd,
            field_name='total_invested_usd',
            min_value=Decimal('0'),
            default_value=Decimal('0'),
            decimal_places=2
        )
        
        self.current_value_usd = validate_decimal_field(
            value=self.current_value_usd,
            field_name='current_value_usd',
            min_value=Decimal('0'),
            default_value=Decimal('0'),
            decimal_places=2
        )
        
        # Validate P&L fields (can be negative, 2 decimal places)
        self.unrealized_pnl_usd = validate_decimal_field(
            value=self.unrealized_pnl_usd,
            field_name='unrealized_pnl_usd',
            default_value=Decimal('0'),
            decimal_places=2
        )
        
        self.realized_pnl_usd = validate_decimal_field(
            value=self.realized_pnl_usd,
            field_name='realized_pnl_usd',
            default_value=Decimal('0'),
            decimal_places=2
        )
        
        logger.debug(
            f"[VALIDATION] Position {self.position_id} validated: "
            f"{self.token_symbol} quantity={self.quantity}, "
            f"value=${self.current_value_usd}"
        )

    def save(self, *args, **kwargs) -> None:
        """
        Save the position with comprehensive decimal validation and error tracking.
        
        This enhanced version:
        1. Logs all field values before validation for debugging
        2. Ensures no NULL values reach the database
        3. Provides detailed error tracking
        """
        # Log incoming values for debugging
        logger.info(
            f"[POSITION SAVE] Attempting to save position {self.token_symbol}:\n"
            f"  position_id: {self.position_id}\n"
            f"  quantity: {self.quantity} (type: {type(self.quantity)})\n"
            f"  current_value_usd: {self.current_value_usd} (type: {type(self.current_value_usd)})"
        )
        
        # Pre-validation: Ensure no NULL values
        decimal_fields = [
            ('quantity', Decimal('0')),
            ('average_entry_price_usd', Decimal('0')),
            ('total_invested_usd', Decimal('0')),
            ('current_price_usd', Decimal('0')),
            ('current_value_usd', Decimal('0')),
            ('unrealized_pnl_usd', Decimal('0')),
            ('realized_pnl_usd', Decimal('0')),
        ]
        
        # Fix NULL values before validation
        for field_name, default_value in decimal_fields:
            current_value = getattr(self, field_name, None)
            
            # Check for NULL, None, empty string, or invalid values
            if current_value is None or current_value == '' or current_value == 'None':
                logger.warning(
                    f"[POSITION SAVE] Field {field_name} is NULL/empty, setting to {default_value}"
                )
                setattr(self, field_name, default_value)
            else:
                # Try to convert to Decimal to ensure it's valid
                try:
                    if not isinstance(current_value, Decimal):
                        converted = Decimal(str(current_value))
                        setattr(self, field_name, converted)
                except (InvalidOperation, ValueError, TypeError) as e:
                    logger.error(
                        f"[POSITION SAVE] Invalid value for {field_name}: {current_value}, "
                        f"using default {default_value}. Error: {e}"
                    )
                    setattr(self, field_name, default_value)
        
        # Now run the clean() validation
        try:
            self.clean()
            logger.info(f"[POSITION SAVE] Validation successful for {self.token_symbol}")
        except Exception as e:
            logger.error(
                f"[POSITION SAVE] Validation failed for {self.token_symbol}: {e}",
                exc_info=True
            )
            # Try to fix and continue instead of raising
            for field_name, default_value in decimal_fields:
                setattr(self, field_name, default_value)
            logger.warning(f"[POSITION SAVE] Reset all decimal fields to defaults for {self.token_symbol}")
        
        # Log final values before saving
        logger.info(
            f"[POSITION SAVE] Final values for {self.token_symbol}:\n"
            f"  quantity: {self.quantity}\n"
            f"  current_value_usd: {self.current_value_usd}\n"
            f"  unrealized_pnl_usd: {self.unrealized_pnl_usd}"
        )
        
        # Call parent save with validated data
        try:
            super().save(*args, **kwargs)
            logger.info(f"[POSITION SAVE] ✅ Successfully saved position {self.token_symbol}")
        except Exception as e:
            logger.error(f"[POSITION SAVE] ❌ Failed to save position {self.token_symbol}: {e}", exc_info=True)
            raise
    
    @classmethod
    def fix_all_positions(cls) -> int:
        """
        Class method to fix all positions with invalid decimal fields.
        Run this after migration to clean up existing data.
        
        Returns:
            int: Number of positions fixed
        """
        from decimal import Decimal, InvalidOperation
        fixed_count = 0
        positions = cls.objects.all()
        
        for position in positions:
            needs_save = False
            
            # Check and fix each decimal field
            decimal_fields = [
                ('quantity', Decimal('0')),
                ('average_entry_price_usd', Decimal('0')),
                ('total_invested_usd', Decimal('0')),
                ('current_price_usd', Decimal('0')),
                ('current_value_usd', Decimal('0')),
                ('unrealized_pnl_usd', Decimal('0')),
                ('realized_pnl_usd', Decimal('0')),
            ]
            
            for field_name, default_value in decimal_fields:
                current_value = getattr(position, field_name, None)
                
                if current_value is None or current_value == '':
                    setattr(position, field_name, default_value)
                    needs_save = True
                    logger.info(f"[FIX] Fixed {field_name} for position {position.position_id}")
            
            if needs_save:
                try:
                    position.save()
                    fixed_count += 1
                except Exception as e:
                    logger.error(f"[FIX] Failed to fix position {position.position_id}: {e}")
        
        logger.info(f"[FIX] Fixed {fixed_count} positions total")
        return fixed_count
    
    def update_price(self, new_price_usd: Decimal) -> None:
        """
        Update position with new price and recalculate P&L.
        
        Args:
            new_price_usd: New market price in USD
        """
        try:
            self.current_price_usd = new_price_usd
            self.current_value_usd = self.quantity * new_price_usd
            self.unrealized_pnl_usd = self.current_value_usd - self.total_invested_usd
            self.last_updated = timezone.now()
            self.save(update_fields=[
                'current_price_usd',
                'current_value_usd',
                'unrealized_pnl_usd',
                'last_updated'
            ])
            logger.debug(f"Updated position {self.position_id} price to ${new_price_usd}")
        except Exception as e:
            logger.error(f"Error updating position {self.position_id} price: {e}", exc_info=True)
    
    def close_position(self, exit_price_usd: Decimal) -> None:
        """
        Close position and calculate realized P&L.
        
        Args:
            exit_price_usd: Exit price in USD
        """
        try:
            self.current_price_usd = exit_price_usd
            self.current_value_usd = self.quantity * exit_price_usd
            self.realized_pnl_usd = self.current_value_usd - self.total_invested_usd
            self.unrealized_pnl_usd = Decimal('0')
            self.is_open = False
            self.closed_at = timezone.now()
            self.save()
            logger.info(
                f"Closed position {self.position_id}: "
                f"{self.token_symbol} P&L=${self.realized_pnl_usd}"
            )
        except Exception as e:
            logger.error(f"Error closing position {self.position_id}: {e}", exc_info=True)
    
    # =========================================================================
    # BACKWARD COMPATIBILITY PROPERTIES
    # =========================================================================
    # These properties allow old code to work with correct database field names
    # TODO: Remove these once all code is updated to use correct field names
    
    @property
    def status(self) -> str:
        """
        Backward compatibility: Convert is_open boolean to status string.
        
        Old code expects: position.status == 'OPEN'
        Database has: position.is_open == True
        
        Returns:
            'OPEN' if position is open, 'CLOSED' if closed
        """
        return 'OPEN' if self.is_open else 'CLOSED'
    
    @property
    def entry_price(self) -> Decimal:
        """
        Backward compatibility: Alias for average_entry_price_usd.
        
        Old code expects: position.entry_price
        Database has: position.average_entry_price_usd
        
        Returns:
            Average entry price in USD
        """
        return self.average_entry_price_usd
    
    @property
    def amount(self) -> Decimal:
        """
        Backward compatibility: Alias for quantity.
        
        Old code expects: position.amount
        Database has: position.quantity
        
        Returns:
            Position quantity in wei
        """
        return self.quantity
    
    @property
    def amount_invested_usd(self) -> Decimal:
        """
        Backward compatibility: Alias for total_invested_usd.
        
        Old code expects: position.amount_invested_usd
        Database has: position.total_invested_usd
        
        Returns:
            Total amount invested in USD
        """
        return self.total_invested_usd







class PaperTradingConfig(models.Model):
    """
    Configuration for paper trading simulation parameters.
    
    Allows customization of simulation behavior per account to make
    paper trading more realistic with configurable slippage, gas costs,
    delays, and failure simulation.
    
    Attributes:
        account: Associated trading account (OneToOne)
        base_slippage_percent: Base slippage for all trades
        gas_price_multiplier: Gas price simulation multiplier
        execution_delay_ms: Simulated execution delay
        max_position_size_percent: Max position size as % of portfolio
        max_daily_trades: Maximum trades per day
        stop_loss_percent: Default stop loss percentage
        simulate_network_issues: Whether to simulate failures
        simulate_mev: Whether to simulate MEV competition
        failure_rate_percent: Percentage of trades that fail
    """
    
    account = models.OneToOneField(
        PaperTradingAccount,
        on_delete=models.CASCADE,
        related_name='config',
        help_text="Associated account"
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
        """Meta configuration."""
        db_table = 'paper_trading_configs'
        verbose_name = 'Paper Trading Config'
        verbose_name_plural = 'Paper Trading Configs'
    
    def __str__(self) -> str:
        """String representation."""
        return f"Config for {self.account.name}"