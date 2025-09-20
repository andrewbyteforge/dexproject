"""
Django models for the wallet app with SIWE (Sign-In with Ethereum) support.

This module defines wallet, transaction, balance management, and SIWE authentication
models for the DEX auto-trading bot's wallet operations.

Updated for Phase 5.1B:
- Added SIWE session tracking
- Client-side key management only
- Wallet-based authentication support
- Base Sepolia and Ethereum Mainnet support
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional
import uuid
from datetime import datetime, timedelta

from django.db import models
from shared.models.mixins import TimestampMixin, UUIDMixin
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
import logging

logger = logging.getLogger(__name__)


class SIWESession(TimestampMixin):
    """
    Tracks SIWE (Sign-In with Ethereum) authentication sessions.
    
    Stores SIWE message data, verification status, and session lifecycle
    for wallet-based authentication without storing private keys.
    """
    
    class SessionStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending Verification'
        VERIFIED = 'VERIFIED', 'Verified and Active'
        EXPIRED = 'EXPIRED', 'Expired'
        REVOKED = 'REVOKED', 'Revoked'
        FAILED = 'FAILED', 'Verification Failed'
    
    # Identification
    session_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique SIWE session identifier"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='siwe_sessions',
        null=True,
        blank=True,
        help_text="Associated Django user (auto-created on first login)"
    )
    
    # SIWE Message Components (EIP-4361)
    wallet_address = models.CharField(
        max_length=42,
        help_text="Wallet address (0x...)"
    )
    domain = models.CharField(
        max_length=255,
        help_text="Domain that issued the SIWE message"
    )
    statement = models.TextField(
        blank=True,
        help_text="Human-readable ASCII assertion"
    )
    uri = models.URLField(
        help_text="URI referring to the resource of the request"
    )
    version = models.CharField(
        max_length=10,
        default='1',
        help_text="SIWE message version"
    )
    chain_id = models.PositiveIntegerField(
        help_text="Chain ID for the network"
    )
    nonce = models.CharField(
        max_length=96,
        help_text="Random nonce for session uniqueness"
    )
    issued_at = models.DateTimeField(
        help_text="When the message was issued"
    )
    expiration_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the session expires"
    )
    not_before = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the session becomes valid"
    )
    request_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional request identifier"
    )
    
    # Authentication Details
    message = models.TextField(
        help_text="Complete SIWE message that was signed"
    )
    signature = models.CharField(
        max_length=132,
        help_text="Signature of the SIWE message (0x...)"
    )
    status = models.CharField(
        max_length=10,
        choices=SessionStatus.choices,
        default=SessionStatus.PENDING
    )
    
    # Session Management
    django_session_key = models.CharField(
        max_length=40,
        blank=True,
        help_text="Associated Django session key"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the session"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="User agent string"
    )
    
    # Verification Metadata
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the signature was verified"
    )
    verification_error = models.TextField(
        blank=True,
        help_text="Error message if verification failed"
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['session_id']),
            models.Index(fields=['wallet_address', 'status']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['django_session_key']),
            models.Index(fields=['status', 'expiration_time']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self) -> str:
        return f"SIWE Session {self.wallet_address[:10]}... ({self.status})"

    def clean(self) -> None:
        """Validate SIWE session data."""
        # Validate wallet address format
        if not self.wallet_address.startswith('0x') or len(self.wallet_address) != 42:
            raise ValidationError("Invalid wallet address format")
        
        # Validate expiration time
        if self.expiration_time and self.expiration_time <= timezone.now():
            raise ValidationError("Expiration time must be in the future")
        
        # Validate not_before time
        if self.not_before and self.expiration_time and self.not_before >= self.expiration_time:
            raise ValidationError("Not before time must be before expiration time")

    def is_valid(self) -> bool:
        """Check if the SIWE session is currently valid."""
        if self.status != self.SessionStatus.VERIFIED:
            return False
        
        now = timezone.now()
        
        # Check expiration
        if self.expiration_time and now >= self.expiration_time:
            return False
        
        # Check not before
        if self.not_before and now < self.not_before:
            return False
        
        return True

    def mark_expired(self) -> None:
        """Mark the session as expired."""
        self.status = self.SessionStatus.EXPIRED
        self.save(update_fields=['status', 'updated_at'])

    def revoke(self) -> None:
        """Revoke the session."""
        self.status = self.SessionStatus.REVOKED
        self.save(update_fields=['status', 'updated_at'])


class Wallet(TimestampMixin):
    """
    Represents a connected wallet used for trading operations.
    
    Stores wallet information and configuration for client-side
    wallet management. Private keys are NEVER stored server-side.
    """
    
    class WalletType(models.TextChoices):
        METAMASK = 'METAMASK', 'MetaMask'
        WALLET_CONNECT = 'WALLET_CONNECT', 'WalletConnect'
        COINBASE_WALLET = 'COINBASE_WALLET', 'Coinbase Wallet'
        RAINBOW = 'RAINBOW', 'Rainbow'
        TRUST_WALLET = 'TRUST_WALLET', 'Trust Wallet'
        OTHER = 'OTHER', 'Other'
    
    class WalletStatus(models.TextChoices):
        CONNECTED = 'CONNECTED', 'Connected'
        DISCONNECTED = 'DISCONNECTED', 'Disconnected'
        LOCKED = 'LOCKED', 'Locked'
        COMPROMISED = 'COMPROMISED', 'Compromised'
    
    # Identification
    wallet_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique wallet identifier"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='wallets'
    )
    
    # Wallet Details
    name = models.CharField(
        max_length=100,
        help_text="Human-readable wallet name (auto-generated or user-set)"
    )
    address = models.CharField(
        max_length=42,
        help_text="Wallet address (0x...)"
    )
    wallet_type = models.CharField(
        max_length=20,
        choices=WalletType.choices
    )
    status = models.CharField(
        max_length=15,
        choices=WalletStatus.choices,
        default=WalletStatus.CONNECTED
    )
    
    # Network Support
    supported_chains = models.JSONField(
        default=list,
        help_text="List of supported chain IDs"
    )
    primary_chain_id = models.PositiveIntegerField(
        default=84532,  # Base Sepolia for development
        help_text="Primary chain ID for this wallet"
    )
    
    # Security Configuration
    is_trading_enabled = models.BooleanField(
        default=True,
        help_text="Whether this wallet can be used for trading"
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
    requires_confirmation = models.BooleanField(
        default=True,
        help_text="Whether transactions require manual confirmation"
    )
    
    # Connection Metadata
    last_connected_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this wallet was connected"
    )
    connection_method = models.CharField(
        max_length=50,
        blank=True,
        help_text="Method used to connect (WalletConnect, injected, etc.)"
    )
    wallet_client_version = models.CharField(
        max_length=100,
        blank=True,
        help_text="Version of the wallet client"
    )
    
    # Configuration
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional wallet configuration and preferences"
    )

    class Meta:
        ordering = ['-last_connected_at', '-created_at']
        unique_together = [['user', 'address']]
        indexes = [
            models.Index(fields=['wallet_id']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['address']),
            models.Index(fields=['primary_chain_id', 'status']),
            models.Index(fields=['is_trading_enabled']),
            models.Index(fields=['last_connected_at']),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.address[:10]}...)"

    def clean(self) -> None:
        """Validate wallet configuration."""
        # Validate wallet address format
        if not self.address.startswith('0x') or len(self.address) != 42:
            raise ValidationError("Invalid wallet address format")
        
        # Validate supported chains
        if not isinstance(self.supported_chains, list):
            raise ValidationError("Supported chains must be a list")
        
        # Validate primary chain is in supported chains
        if self.supported_chains and self.primary_chain_id not in self.supported_chains:
            raise ValidationError("Primary chain must be in supported chains")

    def update_connection_status(self) -> None:
        """Update last connected timestamp."""
        self.last_connected_at = timezone.now()
        self.status = self.WalletStatus.CONNECTED
        self.save(update_fields=['last_connected_at', 'status', 'updated_at'])

    def disconnect(self) -> None:
        """Mark wallet as disconnected."""
        self.status = self.WalletStatus.DISCONNECTED
        self.save(update_fields=['status', 'updated_at'])

    def get_display_name(self) -> str:
        """Get a user-friendly display name for the wallet."""
        if self.name and self.name != f"Wallet {self.address[:10]}...":
            return self.name
        return f"{self.get_wallet_type_display()} ({self.address[:6]}...{self.address[-4:]})"


class WalletBalance(TimestampMixin):
    """
    Tracks token balances for connected wallets.
    
    Updated via periodic balance checks and real-time updates.
    Balances are fetched from blockchain, never stored permanently.
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
    
    # Token Information
    chain_id = models.PositiveIntegerField(
        help_text="Chain ID where the token exists"
    )
    token_address = models.CharField(
        max_length=42,
        help_text="Token contract address (0x... or 'ETH' for native)"
    )
    token_symbol = models.CharField(
        max_length=20,
        help_text="Token symbol (ETH, USDC, etc.)"
    )
    token_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Full token name"
    )
    token_decimals = models.PositiveIntegerField(
        default=18,
        help_text="Number of decimal places for the token"
    )
    
    # Balance Data
    balance_wei = models.CharField(
        max_length=78,  # Max uint256 as string
        help_text="Raw balance in smallest token unit (wei)"
    )
    balance_formatted = models.DecimalField(
        max_digits=36,
        decimal_places=18,
        help_text="Human-readable balance with decimals"
    )
    usd_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Estimated USD value of the balance"
    )
    
    # Metadata
    last_updated = models.DateTimeField(
        help_text="When this balance was last fetched from blockchain"
    )
    is_stale = models.BooleanField(
        default=False,
        help_text="Whether this balance data is considered stale"
    )
    update_error = models.TextField(
        blank=True,
        help_text="Error message if balance update failed"
    )

    class Meta:
        ordering = ['-usd_value', 'token_symbol']
        unique_together = [['wallet', 'chain_id', 'token_address']]
        indexes = [
            models.Index(fields=['balance_id']),
            models.Index(fields=['wallet', 'chain_id']),
            models.Index(fields=['token_address', 'chain_id']),
            models.Index(fields=['last_updated']),
            models.Index(fields=['is_stale']),
        ]

    def __str__(self) -> str:
        return f"{self.balance_formatted} {self.token_symbol} on Chain {self.chain_id}"

    def clean(self) -> None:
        """Validate balance data."""
        # Validate token address format (except for native tokens)
        if self.token_address != 'ETH' and not self.token_address.startswith('0x'):
            raise ValidationError("Invalid token address format")
        
        # Validate balance is positive
        if self.balance_formatted < 0:
            raise ValidationError("Balance cannot be negative")

    def mark_stale(self) -> None:
        """Mark this balance as stale."""
        self.is_stale = True
        self.save(update_fields=['is_stale', 'updated_at'])

    def update_balance(self, balance_wei: str, usd_value: Optional[Decimal] = None) -> None:
        """Update balance data."""
        self.balance_wei = balance_wei
        self.balance_formatted = Decimal(balance_wei) / (10 ** self.token_decimals)
        self.usd_value = usd_value
        self.last_updated = timezone.now()
        self.is_stale = False
        self.update_error = ''
        self.save()


class WalletTransaction(TimestampMixin):
    """
    Tracks transactions initiated through connected wallets.
    
    Records transaction metadata for monitoring and analysis.
    Does not store sensitive transaction data.
    """
    
    class TransactionType(models.TextChoices):
        SWAP = 'SWAP', 'Token Swap'
        TRANSFER = 'TRANSFER', 'Token Transfer'
        APPROVAL = 'APPROVAL', 'Token Approval'
        WRAP = 'WRAP', 'Wrap/Unwrap'
        LIQUIDITY_ADD = 'LIQUIDITY_ADD', 'Add Liquidity'
        LIQUIDITY_REMOVE = 'LIQUIDITY_REMOVE', 'Remove Liquidity'
        OTHER = 'OTHER', 'Other'
    
    class TransactionStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        FAILED = 'FAILED', 'Failed'
        CANCELLED = 'CANCELLED', 'Cancelled'
    
    # Identification
    transaction_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique transaction record identifier"
    )
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    
    # Transaction Details
    chain_id = models.PositiveIntegerField(
        help_text="Chain ID where transaction occurred"
    )
    transaction_hash = models.CharField(
        max_length=66,
        unique=True,
        help_text="Blockchain transaction hash (0x...)"
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices
    )
    status = models.CharField(
        max_length=15,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PENDING
    )
    
    # Gas and Cost Data
    gas_used = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Gas units used by the transaction"
    )
    gas_price_gwei = models.DecimalField(
        max_digits=20,
        decimal_places=9,
        null=True,
        blank=True,
        help_text="Gas price in Gwei"
    )
    transaction_fee_eth = models.DecimalField(
        max_digits=20,
        decimal_places=18,
        null=True,
        blank=True,
        help_text="Total transaction fee in ETH"
    )
    transaction_fee_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total transaction fee in USD"
    )
    
    # Block Information
    block_number = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Block number where transaction was mined"
    )
    block_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Block timestamp"
    )
    
    # Transaction Metadata
    transaction_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional transaction metadata (tokens involved, amounts, etc.)"
    )
    error_reason = models.TextField(
        blank=True,
        help_text="Error reason if transaction failed"
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['transaction_id']),
            models.Index(fields=['wallet', 'status']),
            models.Index(fields=['transaction_hash']),
            models.Index(fields=['chain_id', 'status']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['created_at']),
            models.Index(fields=['block_timestamp']),
        ]

    def __str__(self) -> str:
        return f"{self.transaction_type} - {self.transaction_hash[:10]}... ({self.status})"

    def clean(self) -> None:
        """Validate transaction data."""
        # Validate transaction hash format
        if not self.transaction_hash.startswith('0x') or len(self.transaction_hash) != 66:
            raise ValidationError("Invalid transaction hash format")

    def update_status(self, status: str, error_reason: str = '') -> None:
        """Update transaction status."""
        self.status = status
        self.error_reason = error_reason
        self.save(update_fields=['status', 'error_reason', 'updated_at'])


class WalletActivity(TimestampMixin):
    """
    Logs wallet activity for audit and monitoring purposes.
    
    Tracks all operations performed with wallets including
    connections, transactions, and configuration changes.
    """
    
    class ActivityType(models.TextChoices):
        CONNECTION = 'CONNECTION', 'Wallet Connection'
        DISCONNECTION = 'DISCONNECTION', 'Wallet Disconnection'
        SIWE_LOGIN = 'SIWE_LOGIN', 'SIWE Authentication'
        TRANSACTION = 'TRANSACTION', 'Transaction Initiated'
        BALANCE_UPDATE = 'BALANCE_UPDATE', 'Balance Updated'
        CONFIG_CHANGE = 'CONFIG_CHANGE', 'Configuration Changed'
        SECURITY_EVENT = 'SECURITY_EVENT', 'Security Event'
        ERROR = 'ERROR', 'Error Occurred'
    
    # Identification
    activity_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique activity identifier"
    )
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='activities',
        null=True,
        blank=True
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
    siwe_session = models.ForeignKey(
        SIWESession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activities'
    )
    transaction = models.ForeignKey(
        WalletTransaction,
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
        wallet_name = self.wallet.name if self.wallet else "Unknown"
        return f"{self.activity_type} - {wallet_name} at {self.created_at}"