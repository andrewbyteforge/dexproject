"""
Django models for the trading app.

This module defines the core trading entities including trades, positions,
pair information, and trading strategies for the DEX auto-trading bot.
"""

from decimal import Decimal
from typing import Dict, Any, Optional
import uuid

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class Chain(models.Model):
    """
    Represents a blockchain network (e.g., Ethereum, Base, Arbitrum).
    
    This model stores chain-specific information including RPC endpoints,
    gas settings, and chain identifiers.
    """
    
    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Human-readable chain name (e.g., 'Ethereum', 'Base')"
    )
    chain_id = models.PositiveIntegerField(
        unique=True,
        help_text="Chain ID as defined by EIP-155 (e.g., 1 for Ethereum mainnet)"
    )
    rpc_url = models.URLField(
        help_text="Primary RPC endpoint URL"
    )
    fallback_rpc_urls = models.JSONField(
        default=list,
        blank=True,
        help_text="List of fallback RPC URLs for redundancy"
    )
    block_time_seconds = models.PositiveIntegerField(
        default=12,
        help_text="Average block time in seconds"
    )
    gas_price_gwei = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('20.0'),
        help_text="Default gas price in Gwei"
    )
    max_gas_price_gwei = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('50.0'),
        help_text="Maximum allowed gas price in Gwei"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether trading is enabled on this chain"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['chain_id']
        indexes = [
            models.Index(fields=['chain_id']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self) -> str:
        return f"{self.name} (Chain ID: {self.chain_id})"


class DEX(models.Model):
    """
    Represents a decentralized exchange (e.g., Uniswap V2, Uniswap V3).
    
    Stores DEX-specific information including router addresses, factory addresses,
    and fee structures.
    """
    
    name = models.CharField(
        max_length=50,
        help_text="DEX name (e.g., 'Uniswap V2', 'Uniswap V3')"
    )
    chain = models.ForeignKey(
        Chain,
        on_delete=models.CASCADE,
        related_name='dexes'
    )
    router_address = models.CharField(
        max_length=42,
        help_text="Router contract address (0x...)"
    )
    factory_address = models.CharField(
        max_length=42,
        help_text="Factory contract address (0x...)"
    )
    fee_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal('0.3000'),
        help_text="Trading fee as percentage (e.g., 0.3000 for 0.3%)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether trading is enabled on this DEX"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['name', 'chain']
        ordering = ['chain', 'name']
        indexes = [
            models.Index(fields=['chain', 'is_active']),
            models.Index(fields=['router_address']),
            models.Index(fields=['factory_address']),
        ]

    def __str__(self) -> str:
        return f"{self.name} on {self.chain.name}"


class Token(models.Model):
    """
    Represents an ERC-20 token with metadata and safety information.
    
    Stores token contract details, metadata, and risk assessment flags.
    """
    
    address = models.CharField(
        max_length=42,
        help_text="Token contract address (0x...)"
    )
    chain = models.ForeignKey(
        Chain,
        on_delete=models.CASCADE,
        related_name='tokens'
    )
    symbol = models.CharField(
        max_length=20,
        blank=True,
        help_text="Token symbol (e.g., 'USDC', 'WETH')"
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Full token name"
    )
    decimals = models.PositiveIntegerField(
        default=18,
        validators=[MaxValueValidator(30)],
        help_text="Number of decimal places"
    )
    total_supply = models.DecimalField(
        max_digits=50,
        decimal_places=18,
        null=True,
        blank=True,
        help_text="Total token supply"
    )
    is_verified = models.BooleanField(
        default=False,
        help_text="Whether the token contract is verified on blockchain explorers"
    )
    is_honeypot = models.BooleanField(
        default=False,
        help_text="Whether the token has been identified as a honeypot"
    )
    is_blacklisted = models.BooleanField(
        default=False,
        help_text="Whether the token is on our blacklist"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional token metadata (website, social links, etc.)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['address', 'chain']
        ordering = ['chain', 'symbol']
        indexes = [
            models.Index(fields=['chain', 'address']),
            models.Index(fields=['symbol']),
            models.Index(fields=['is_verified']),
            models.Index(fields=['is_honeypot']),
            models.Index(fields=['is_blacklisted']),
        ]

    def __str__(self) -> str:
        return f"{self.symbol or 'Unknown'} ({self.address[:10]}...)"


class TradingPair(models.Model):
    """
    Represents a trading pair on a specific DEX (e.g., WETH/USDC on Uniswap V2).
    
    Stores pair-specific information including pool address, liquidity data,
    and trading statistics.
    """
    
    dex = models.ForeignKey(
        DEX,
        on_delete=models.CASCADE,
        related_name='pairs'
    )
    token0 = models.ForeignKey(
        Token,
        on_delete=models.CASCADE,
        related_name='pairs_as_token0'
    )
    token1 = models.ForeignKey(
        Token,
        on_delete=models.CASCADE,
        related_name='pairs_as_token1'
    )
    pair_address = models.CharField(
        max_length=42,
        help_text="Pair/pool contract address (0x...)"
    )
    reserve0 = models.DecimalField(
        max_digits=50,
        decimal_places=18,
        default=Decimal('0'),
        help_text="Reserve amount for token0"
    )
    reserve1 = models.DecimalField(
        max_digits=50,
        decimal_places=18,
        default=Decimal('0'),
        help_text="Reserve amount for token1"
    )
    liquidity_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total liquidity in USD"
    )
    volume_24h_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="24-hour trading volume in USD"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this pair is actively traded"
    )
    discovered_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this pair was first discovered"
    )
    last_updated = models.DateTimeField(
        auto_now=True,
        help_text="Last time pair data was updated"
    )

    class Meta:
        unique_together = ['dex', 'token0', 'token1']
        ordering = ['-liquidity_usd', '-volume_24h_usd']
        indexes = [
            models.Index(fields=['dex', 'is_active']),
            models.Index(fields=['pair_address']),
            models.Index(fields=['liquidity_usd']),
            models.Index(fields=['discovered_at']),
        ]

    def __str__(self) -> str:
        return f"{self.token0.symbol}/{self.token1.symbol} on {self.dex.name}"


class Strategy(models.Model):
    """
    Represents a trading strategy configuration.
    
    Stores strategy parameters, risk settings, and execution rules that
    can be applied to trading decisions.
    """
    
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Strategy name (e.g., 'Conservative Sniper', 'Aggressive Growth')"
    )
    description = models.TextField(
        blank=True,
        help_text="Strategy description and goals"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this strategy is available for use"
    )
    
    # Risk Parameters
    max_position_size_eth = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=Decimal('0.1'),
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text="Maximum position size in ETH"
    )
    max_slippage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('2.0'),
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('20.0'))],
        help_text="Maximum allowed slippage percentage"
    )
    max_gas_price_gwei = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('50.0'),
        help_text="Maximum gas price willing to pay in Gwei"
    )
    
    # Entry Criteria
    min_liquidity_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('50000.0'),
        help_text="Minimum liquidity required in USD"
    )
    max_buy_tax_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.0'),
        help_text="Maximum acceptable buy tax percentage"
    )
    max_sell_tax_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.0'),
        help_text="Maximum acceptable sell tax percentage"
    )
    
    # Exit Criteria
    take_profit_percent = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal('50.0'),
        help_text="Take profit target percentage"
    )
    stop_loss_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('20.0'),
        help_text="Stop loss percentage"
    )
    
    # Advanced Configuration
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional strategy configuration parameters"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = "Strategies"

    def __str__(self) -> str:
        return self.name


class Trade(models.Model):
    """
    Represents a completed trade transaction.
    
    Stores all details of a trade including entry/exit prices, fees,
    PnL calculations, and execution metadata.
    """
    
    class TradeType(models.TextChoices):
        BUY = 'BUY', 'Buy'
        SELL = 'SELL', 'Sell'
    
    class TradeStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        FAILED = 'FAILED', 'Failed'
        CANCELLED = 'CANCELLED', 'Cancelled'
    
    # Identification
    trade_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique trade identifier"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='trades',
        null=True,
        blank=True,
        help_text="User who initiated this trade (null for bot trades)"
    )
    strategy = models.ForeignKey(
        Strategy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trades'
    )
    
    # Trade Details
    trade_type = models.CharField(
        max_length=4,
        choices=TradeType.choices
    )
    status = models.CharField(
        max_length=10,
        choices=TradeStatus.choices,
        default=TradeStatus.PENDING
    )
    pair = models.ForeignKey(
        TradingPair,
        on_delete=models.CASCADE,
        related_name='trades'
    )
    
    # Amounts and Prices
    amount_in = models.DecimalField(
        max_digits=50,
        decimal_places=18,
        help_text="Input token amount"
    )
    amount_out = models.DecimalField(
        max_digits=50,
        decimal_places=18,
        null=True,
        blank=True,
        help_text="Output token amount (filled after execution)"
    )
    price_usd = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Execution price in USD"
    )
    
    # Execution Details
    transaction_hash = models.CharField(
        max_length=66,
        blank=True,
        help_text="Blockchain transaction hash"
    )
    block_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Block number where transaction was included"
    )
    gas_used = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Gas used for the transaction"
    )
    gas_price_gwei = models.DecimalField(
        max_digits=15,
        decimal_places=9,
        null=True,
        blank=True,
        help_text="Gas price paid in Gwei"
    )
    
    # Slippage and Fees
    expected_amount_out = models.DecimalField(
        max_digits=50,
        decimal_places=18,
        null=True,
        blank=True,
        help_text="Expected output amount before slippage"
    )
    slippage_percent = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Actual slippage percentage"
    )
    fee_usd = models.DecimalField(
        max_digits=15,
        decimal_places=8,
        default=Decimal('0'),
        help_text="Total fees paid in USD"
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the trade was initiated"
    )
    executed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the trade was executed on-chain"
    )
    confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the trade was confirmed"
    )
    
    # Additional Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional trade metadata and context"
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['trade_id']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['pair', 'created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['trade_type']),
            models.Index(fields=['transaction_hash']),
            models.Index(fields=['executed_at']),
        ]

    def __str__(self) -> str:
        return f"{self.trade_type} {self.pair} - {self.trade_id}"

    @property
    def pnl_usd(self) -> Optional[Decimal]:
        """Calculate PnL in USD if trade is part of a position."""
        # This will be implemented when we have position tracking
        return None


class Position(models.Model):
    """
    Represents an open or closed trading position.
    
    A position aggregates multiple trades (buy/sell) for the same token
    and tracks overall PnL, fees, and performance metrics.
    """
    
    class PositionStatus(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        CLOSED = 'CLOSED', 'Closed'
        PARTIALLY_CLOSED = 'PARTIALLY_CLOSED', 'Partially Closed'
    
    # Identification
    position_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique position identifier"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='positions',
        null=True,
        blank=True
    )
    strategy = models.ForeignKey(
        Strategy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='positions'
    )
    pair = models.ForeignKey(
        TradingPair,
        on_delete=models.CASCADE,
        related_name='positions'
    )
    
    # Position Details
    status = models.CharField(
        max_length=20,
        choices=PositionStatus.choices,
        default=PositionStatus.OPEN
    )
    entry_trades = models.ManyToManyField(
        Trade,
        related_name='entry_positions',
        blank=True,
        help_text="Trades that opened this position"
    )
    exit_trades = models.ManyToManyField(
        Trade,
        related_name='exit_positions',
        blank=True,
        help_text="Trades that closed this position"
    )
    
    # Position Metrics
    total_amount_in = models.DecimalField(
        max_digits=50,
        decimal_places=18,
        default=Decimal('0'),
        help_text="Total amount invested"
    )
    average_entry_price = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Average entry price in USD"
    )
    current_amount = models.DecimalField(
        max_digits=50,
        decimal_places=18,
        default=Decimal('0'),
        help_text="Current token amount held"
    )
    realized_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=Decimal('0'),
        help_text="Realized PnL in USD"
    )
    unrealized_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=Decimal('0'),
        help_text="Unrealized PnL in USD"
    )
    total_fees_usd = models.DecimalField(
        max_digits=15,
        decimal_places=8,
        default=Decimal('0'),
        help_text="Total fees paid in USD"
    )
    
    # Timestamps
    opened_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the position was opened"
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the position was closed"
    )
    last_updated = models.DateTimeField(
        auto_now=True,
        help_text="Last update timestamp"
    )

    class Meta:
        ordering = ['-opened_at']
        indexes = [
            models.Index(fields=['position_id']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['pair', 'status']),
            models.Index(fields=['opened_at']),
            models.Index(fields=['closed_at']),
        ]

    def __str__(self) -> str:
        return f"Position {self.position_id} - {self.pair} ({self.status})"

    @property
    def total_pnl_usd(self) -> Decimal:
        """Calculate total PnL (realized + unrealized)."""
        return self.realized_pnl_usd + self.unrealized_pnl_usd

    @property
    def roi_percent(self) -> Optional[Decimal]:
        """Calculate return on investment percentage."""
        if self.total_amount_in > 0:
            return (self.total_pnl_usd / self.total_amount_in) * 100
        return None