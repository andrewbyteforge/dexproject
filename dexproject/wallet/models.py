"""
Django models for the wallet app.

This module defines wallet, transaction, and balance management models
for the DEX auto-trading bot's wallet operations.
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional
import uuid

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError


class Wallet(models.Model):
    """
    Represents a wallet used for trading operations.
    
    Stores wallet information, configuration, and security settings
    for both custodial and non-custodial wallet management.
    """
    
    class WalletType(models.TextChoices):
        HOT_WALLET = 'HOT_WALLET', 'Hot Wallet'
        CONNECTED_WALLET = 'CONNECTED_WALLET', 'Connected Wallet'
        HARDWARE_WALLET = 'HARDWARE_WALLET', 'Hardware Wallet'
        MULTISIG_WALLET = 'MULTISIG_WALLET', 'Multisig Wallet'
    
    class WalletStatus(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        INACTIVE = 'INACTIVE', 'Inactive'
        LOCKED = 'LOCKED', 'Locked'
        COMPROMISED = 'COMPROMISED', 'Compromised'
        ARCHIVED = 'ARCHIVED', 'Archived'
    
    # Identification
    wallet_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique wallet identifier"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='wallets',
        null=True,
        blank=True,
        help_text="Wallet owner (null for system wallets)"
    )
    name = models.CharField(
        max_length=100,
        help_text="Human-readable wallet name"
    )
    wallet_type = models.CharField(
        max_length=20,
        choices=WalletType.choices
    )
    status = models.CharField(
        max_length=15,
        choices=WalletStatus.choices,
        default=WalletStatus.ACTIVE
    )
    
    # Wallet Details
    address = models.CharField(
        max_length=42,
        unique=True,
        help_text="Wallet address (0x...)"
    )
    chain = models.ForeignKey(
        'trading.Chain',
        on_delete=models.CASCADE,
        related_name='wallets'
    )
    
    # Security Configuration
    requires_confirmation = models.BooleanField(
        default=True,
        help_text="Whether transactions require manual confirmation"
    )
    daily_limit_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Daily spending limit in USD"
    )
    per_transaction_limit_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Per-transaction limit in USD"
    )
    is_trading_enabled = models.BooleanField(
        default=True,
        help_text="Whether this wallet can be used for trading"
    )
    
    # Hardware Wallet Specific
    derivation_path = models.CharField(
        max_length=100,
        blank=True,
        help_text="Derivation path for hardware wallets"
    )
    hardware_device_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Hardware device identifier"
    )
    
    # Multisig Specific
    required_signatures = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Required signatures for multisig wallets"
    )
    total_signers = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total number of signers for multisig wallets"
    )
    
    # Configuration
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional wallet configuration"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this wallet was used"
    )

    class Meta:
        ordering = ['-last_used_at', '-created_at']
        indexes = [
            models.Index(fields=['wallet_id']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['address']),
            models.Index(fields=['chain', 'status']),
            models.Index(fields=['is_trading_enabled']),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.address[:10]}...)"

    def clean(self) -> None:
        """Validate wallet configuration."""
        if self.wallet_type == self.WalletType.MULTISIG_WALLET:
            if not self.required_signatures or not self.total_signers:
                raise ValidationError("Multisig wallets must specify required signatures and total signers")
            if self.required_signatures > self.total_signers:
                raise ValidationError("Required signatures cannot exceed total signers")


class WalletBalance(models.Model):
    """
    Tracks token balances for wallets.
    
    Stores current and historical balance information for each
    token held in a wallet.
    """
    
    # Identification
    balance_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique balance record identifier"
    )
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='balances'
    )
    token = models.ForeignKey(
        'trading.Token',
        on_delete=models.CASCADE,
        related_name='wallet_balances'
    )
    
    # Balance Information
    balance = models.DecimalField(
        max_digits=50,
        decimal_places=18,
        default=Decimal('0'),
        help_text="Current token balance"
    )
    balance_usd = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Balance value in USD"
    )
    available_balance = models.DecimalField(
        max_digits=50,
        decimal_places=18,
        default=Decimal('0'),
        help_text="Available balance (excluding locked/pending amounts)"
    )
    locked_balance = models.DecimalField(
        max_digits=50,
        decimal_places=18,
        default=Decimal('0'),
        help_text="Locked balance (in pending orders)"
    )
    
    # Price Information
    last_price_usd = models.DecimalField(
        max_digits=20,
        decimal_places=12,
        null=True,
        blank=True,
        help_text="Last known token price in USD"
    )
    price_source = models.CharField(
        max_length=100,
        blank=True,
        help_text="Source of price information"
    )
    
    # Tracking
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this balance is actively tracked"
    )
    last_updated = models.DateTimeField(
        auto_now=True,
        help_text="Last time balance was updated"
    )
    last_sync_block = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Last block number where balance was synced"
    )

    class Meta:
        unique_together = ['wallet', 'token']
        ordering = ['-balance_usd', 'token__symbol']
        indexes = [
            models.Index(fields=['balance_id']),
            models.Index(fields=['wallet', 'is_active']),
            models.Index(fields=['token']),
            models.Index(fields=['balance_usd']),
            models.Index(fields=['last_updated']),
        ]

    def __str__(self) -> str:
        return f"{self.wallet.name} - {self.token.symbol}: {self.balance}"

    @property
    def total_balance(self) -> Decimal:
        """Calculate total balance (available + locked)."""
        return self.available_balance + self.locked_balance


class Transaction(models.Model):
    """
    Represents a blockchain transaction initiated by the trading bot.
    
    Stores transaction details, status, and execution information
    for all wallet operations.
    """
    
    class TransactionType(models.TextChoices):
        TRADE_BUY = 'TRADE_BUY', 'Trade Buy'
        TRADE_SELL = 'TRADE_SELL', 'Trade Sell'
        TRANSFER_IN = 'TRANSFER_IN', 'Transfer In'
        TRANSFER_OUT = 'TRANSFER_OUT', 'Transfer Out'
        APPROVAL = 'APPROVAL', 'Token Approval'
        WITHDRAW = 'WITHDRAW', 'Withdraw'
        DEPOSIT = 'DEPOSIT', 'Deposit'
        GAS_REFILL = 'GAS_REFILL', 'Gas Refill'
        EMERGENCY_EXIT = 'EMERGENCY_EXIT', 'Emergency Exit'
    
    class TransactionStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        SUBMITTED = 'SUBMITTED', 'Submitted'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        FAILED = 'FAILED', 'Failed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        REPLACED = 'REPLACED', 'Replaced'
    
    # Identification
    transaction_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique transaction identifier"
    )
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    trade = models.ForeignKey(
        'trading.Trade',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions',
        help_text="Associated trade (if applicable)"
    )
    
    # Transaction Details
    transaction_type = models.CharField(
        max_length=15,
        choices=TransactionType.choices
    )
    status = models.CharField(
        max_length=10,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PENDING
    )
    
    # Blockchain Details
    transaction_hash = models.CharField(
        max_length=66,
        blank=True,
        unique=True,
        null=True,
        help_text="Blockchain transaction hash"
    )
    block_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Block number where transaction was included"
    )
    block_hash = models.CharField(
        max_length=66,
        blank=True,
        help_text="Block hash where transaction was included"
    )
    transaction_index = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Transaction index within the block"
    )
    
    # Gas and Fees
    gas_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Gas limit set for the transaction"
    )
    gas_used = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Actual gas used"
    )
    gas_price_gwei = models.DecimalField(
        max_digits=15,
        decimal_places=9,
        null=True,
        blank=True,
        help_text="Gas price in Gwei"
    )
    max_fee_per_gas_gwei = models.DecimalField(
        max_digits=15,
        decimal_places=9,
        null=True,
        blank=True,
        help_text="Max fee per gas (EIP-1559)"
    )
    max_priority_fee_per_gas_gwei = models.DecimalField(
        max_digits=15,
        decimal_places=9,
        null=True,
        blank=True,
        help_text="Max priority fee per gas (EIP-1559)"
    )
    
    # Transaction Data
    to_address = models.CharField(
        max_length=42,
        help_text="Recipient address"
    )
    value_wei = models.DecimalField(
        max_digits=30,
        decimal_places=0,
        default=Decimal('0'),
        help_text="ETH value in wei"
    )
    input_data = models.TextField(
        blank=True,
        help_text="Transaction input data (hex encoded)"
    )
    nonce = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Transaction nonce"
    )
    
    # Token Transfer Details (if applicable)
    token = models.ForeignKey(
        'trading.Token',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    token_amount = models.DecimalField(
        max_digits=50,
        decimal_places=18,
        null=True,
        blank=True,
        help_text="Token amount being transferred"
    )
    
    # Execution Details
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When transaction was submitted to the network"
    )
    confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When transaction was confirmed"
    )
    failed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When transaction failed"
    )
    
    # Error Information
    error_message = models.TextField(
        blank=True,
        help_text="Error message if transaction failed"
    )
    revert_reason = models.TextField(
        blank=True,
        help_text="Smart contract revert reason"
    )
    
    # Replacement Transaction
    replaced_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='replaces',
        help_text="Transaction that replaced this one"
    )
    replacement_reason = models.CharField(
        max_length=100,
        blank=True,
        help_text="Reason for transaction replacement"
    )
    
    # Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional transaction metadata"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['transaction_id']),
            models.Index(fields=['wallet', 'status']),
            models.Index(fields=['transaction_hash']),
            models.Index(fields=['block_number']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['status']),
            models.Index(fields=['submitted_at']),
            models.Index(fields=['confirmed_at']),
            models.Index(fields=['trade']),
        ]

    def __str__(self) -> str:
        return f"{self.transaction_type} - {self.transaction_hash or self.transaction_id}"

    @property
    def total_fee_eth(self) -> Optional[Decimal]:
        """Calculate total transaction fee in ETH."""
        if self.gas_used and self.gas_price_gwei:
            # Convert from gwei to ETH
            return (self.gas_used * self.gas_price_gwei) / Decimal('1000000000')
        return None

    @property
    def is_pending(self) -> bool:
        """Check if transaction is still pending."""
        return self.status in [self.TransactionStatus.PENDING, self.TransactionStatus.SUBMITTED]

    @property
    def execution_time_seconds(self) -> Optional[int]:
        """Calculate execution time from submission to confirmation."""
        if self.submitted_at and self.confirmed_at:
            return int((self.confirmed_at - self.submitted_at).total_seconds())
        return None


class TransactionReceipt(models.Model):
    """
    Stores detailed transaction receipt information from the blockchain.
    
    Contains complete receipt data including logs, events, and
    execution details for post-transaction analysis.
    """
    
    # Identification
    receipt_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique receipt identifier"
    )
    transaction = models.OneToOneField(
        Transaction,
        on_delete=models.CASCADE,
        related_name='receipt'
    )
    
    # Receipt Data
    status = models.PositiveIntegerField(
        help_text="Transaction status (0 = failed, 1 = success)"
    )
    cumulative_gas_used = models.PositiveIntegerField(
        help_text="Cumulative gas used in the block up to this transaction"
    )
    effective_gas_price = models.DecimalField(
        max_digits=15,
        decimal_places=9,
        null=True,
        blank=True,
        help_text="Effective gas price paid"
    )
    
    # Logs and Events
    logs = models.JSONField(
        default=list,
        blank=True,
        help_text="Transaction logs/events"
    )
    logs_bloom = models.TextField(
        blank=True,
        help_text="Bloom filter for logs"
    )
    
    # Contract Interaction
    contract_address = models.CharField(
        max_length=42,
        blank=True,
        help_text="Contract address if contract was created"
    )
    
    # Raw Receipt Data
    raw_receipt = models.JSONField(
        default=dict,
        blank=True,
        help_text="Complete raw receipt data from the blockchain"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['receipt_id']),
            models.Index(fields=['transaction']),
            models.Index(fields=['status']),
        ]

    def __str__(self) -> str:
        return f"Receipt for {self.transaction.transaction_hash}"


class WalletAuthorization(models.Model):
    """
    Manages authorizations and permissions for wallet operations.
    
    Controls which operations are allowed for each wallet and
    tracks approval workflows for sensitive operations.
    """
    
    class AuthorizationType(models.TextChoices):
        TRADING = 'TRADING', 'Trading Operations'
        TRANSFERS = 'TRANSFERS', 'Token Transfers'
        APPROVALS = 'APPROVALS', 'Token Approvals'
        EMERGENCY = 'EMERGENCY', 'Emergency Operations'
        ADMIN = 'ADMIN', 'Administrative Operations'
    
    class AuthorizationStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        DENIED = 'DENIED', 'Denied'
        REVOKED = 'REVOKED', 'Revoked'
        EXPIRED = 'EXPIRED', 'Expired'
    
    # Identification
    authorization_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique authorization identifier"
    )
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='authorizations'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='wallet_authorizations'
    )
    
    # Authorization Details
    authorization_type = models.CharField(
        max_length=15,
        choices=AuthorizationType.choices
    )
    status = models.CharField(
        max_length=10,
        choices=AuthorizationStatus.choices,
        default=AuthorizationStatus.PENDING
    )
    
    # Permissions
    permissions = models.JSONField(
        default=dict,
        help_text="Detailed permissions configuration"
    )
    spending_limit_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Spending limit for this authorization"
    )
    
    # Validity
    valid_from = models.DateTimeField(
        default=timezone.now,
        help_text="When this authorization becomes valid"
    )
    valid_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this authorization expires"
    )
    
    # Approval Workflow
    requested_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='requested_authorizations'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_authorizations'
    )
    approval_notes = models.TextField(
        blank=True,
        help_text="Notes from the approval process"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this authorization was approved"
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this authorization was used"
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['authorization_id']),
            models.Index(fields=['wallet', 'status']),
            models.Index(fields=['user', 'authorization_type']),
            models.Index(fields=['status']),
            models.Index(fields=['valid_from', 'valid_until']),
        ]

    def __str__(self) -> str:
        return f"{self.authorization_type} for {self.wallet.name} - {self.status}"

    @property
    def is_valid(self) -> bool:
        """Check if authorization is currently valid."""
        now = timezone.now()
        if self.status != self.AuthorizationStatus.APPROVED:
            return False
        if self.valid_from > now:
            return False
        if self.valid_until and self.valid_until < now:
            return False
        return True

    def clean(self) -> None:
        """Validate authorization configuration."""
        if self.valid_until and self.valid_from >= self.valid_until:
            raise ValidationError("Valid until must be after valid from")


class WalletActivity(models.Model):
    """
    Logs wallet activity for audit and monitoring purposes.
    
    Tracks all operations performed on wallets including
    configuration changes, transactions, and access patterns.
    """
    
    class ActivityType(models.TextChoices):
        LOGIN = 'LOGIN', 'Login'
        TRANSACTION = 'TRANSACTION', 'Transaction'
        CONFIG_CHANGE = 'CONFIG_CHANGE', 'Configuration Change'
        AUTHORIZATION = 'AUTHORIZATION', 'Authorization'
        BALANCE_UPDATE = 'BALANCE_UPDATE', 'Balance Update'
        SECURITY_EVENT = 'SECURITY_EVENT', 'Security Event'
        API_ACCESS = 'API_ACCESS', 'API Access'
    
    # Identification
    activity_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique activity identifier"
    )
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='activities'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='wallet_activities'
    )
    
    # Activity Details
    activity_type = models.CharField(
        max_length=15,
        choices=ActivityType.choices
    )
    description = models.CharField(
        max_length=500,
        help_text="Brief description of the activity"
    )
    
    # Context
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the activity source"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="User agent string"
    )
    session_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Session identifier"
    )
    
    # Related Objects
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activities'
    )
    authorization = models.ForeignKey(
        WalletAuthorization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activities'
    )
    
    # Additional Data
    data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional activity data"
    )
    
    # Success/Failure
    was_successful = models.BooleanField(
        default=True,
        help_text="Whether the activity was successful"
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if activity failed"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Wallet Activities"
        indexes = [
            models.Index(fields=['activity_id']),
            models.Index(fields=['wallet', 'activity_type']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['activity_type']),
            models.Index(fields=['was_successful']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self) -> str:
        return f"{self.activity_type} - {self.wallet.name} at {self.created_at}"