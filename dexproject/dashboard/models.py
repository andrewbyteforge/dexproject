"""
Django models for the dashboard app.

This module defines user profile, bot configuration, and dashboard-related
models for the DEX auto-trading bot's control interface.
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional
import uuid

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError


class UserProfile(models.Model):
    """
    Extended user profile for trading bot users.
    
    Stores additional user information, preferences, and settings
    beyond the default Django User model.
    """
    
    class ExperienceLevel(models.TextChoices):
        BEGINNER = 'BEGINNER', 'Beginner'
        INTERMEDIATE = 'INTERMEDIATE', 'Intermediate'
        ADVANCED = 'ADVANCED', 'Advanced'
        EXPERT = 'EXPERT', 'Expert'
    
    class RiskTolerance(models.TextChoices):
        VERY_LOW = 'VERY_LOW', 'Very Low'
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        VERY_HIGH = 'VERY_HIGH', 'Very High'
    
    # Identification
    profile_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique profile identifier"
    )
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    
    # Profile Information
    display_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Display name for the user"
    )
    avatar_url = models.URLField(
        blank=True,
        help_text="URL to user's avatar image"
    )
    timezone = models.CharField(
        max_length=50,
        default='UTC',
        help_text="User's timezone"
    )
    
    # Trading Experience
    experience_level = models.CharField(
        max_length=15,
        choices=ExperienceLevel.choices,
        default=ExperienceLevel.BEGINNER
    )
    risk_tolerance = models.CharField(
        max_length=10,
        choices=RiskTolerance.choices,
        default=RiskTolerance.MEDIUM
    )
    years_trading = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Years of trading experience"
    )
    
    # Preferences
    preferred_chains = models.ManyToManyField(
        'trading.Chain',
        blank=True,
        related_name='preferred_by_users',
        help_text="User's preferred blockchain networks"
    )
    email_notifications = models.BooleanField(
        default=True,
        help_text="Whether to send email notifications"
    )
    sms_notifications = models.BooleanField(
        default=False,
        help_text="Whether to send SMS notifications"
    )
    desktop_notifications = models.BooleanField(
        default=True,
        help_text="Whether to show desktop notifications"
    )
    
    # Dashboard Preferences
    dashboard_theme = models.CharField(
        max_length=20,
        choices=[
            ('LIGHT', 'Light'),
            ('DARK', 'Dark'),
            ('AUTO', 'Auto'),
        ],
        default='DARK',
        help_text="Dashboard color theme"
    )
    default_timeframe = models.CharField(
        max_length=10,
        choices=[
            ('1H', '1 Hour'),
            ('4H', '4 Hours'),
            ('1D', '1 Day'),
            ('1W', '1 Week'),
            ('1M', '1 Month'),
        ],
        default='1D',
        help_text="Default timeframe for charts"
    )
    
    # Contact Information
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="Phone number for SMS notifications"
    )
    telegram_username = models.CharField(
        max_length=50,
        blank=True,
        help_text="Telegram username for notifications"
    )
    
    # Security
    two_factor_enabled = models.BooleanField(
        default=False,
        help_text="Whether 2FA is enabled"
    )
    api_access_enabled = models.BooleanField(
        default=False,
        help_text="Whether API access is enabled"
    )
    
    # Metadata
    onboarding_completed = models.BooleanField(
        default=False,
        help_text="Whether user has completed onboarding"
    )
    terms_accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When user accepted terms of service"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['profile_id']),
            models.Index(fields=['user']),
            models.Index(fields=['experience_level']),
            models.Index(fields=['risk_tolerance']),
        ]

    def __str__(self) -> str:
        return f"{self.user.username} Profile"


class BotConfiguration(models.Model):
    """
    Represents a trading bot configuration profile.
    
    Stores complete bot settings including strategies, risk parameters,
    and execution preferences that can be applied to trading sessions.
    """
    
    class ConfigStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        ACTIVE = 'ACTIVE', 'Active'
        PAUSED = 'PAUSED', 'Paused'
        ARCHIVED = 'ARCHIVED', 'Archived'
    
    class TradingMode(models.TextChoices):
        PAPER = 'PAPER', 'Paper Trading'
        LIVE = 'LIVE', 'Live Trading'
        SHADOW = 'SHADOW', 'Shadow Trading'
    
    # Identification
    config_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique configuration identifier"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bot_configurations'
    )
    name = models.CharField(
        max_length=100,
        help_text="Configuration name"
    )
    description = models.TextField(
        blank=True,
        help_text="Configuration description"
    )
    status = models.CharField(
        max_length=10,
        choices=ConfigStatus.choices,
        default=ConfigStatus.DRAFT
    )
    trading_mode = models.CharField(
        max_length=10,
        choices=TradingMode.choices,
        default=TradingMode.PAPER
    )
    
    # Strategy Configuration
    strategy = models.ForeignKey(
        'trading.Strategy',
        on_delete=models.CASCADE,
        related_name='bot_configurations'
    )
    risk_profile = models.ForeignKey(
        'risk.RiskProfile',
        on_delete=models.CASCADE,
        related_name='bot_configurations'
    )
    
    # Trading Parameters
    max_position_size_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('1000.0'),
        validators=[MinValueValidator(Decimal('10.0'))],
        help_text="Maximum position size in USD"
    )
    daily_loss_limit_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('100.0'),
        validators=[MinValueValidator(Decimal('1.0'))],
        help_text="Daily loss limit in USD"
    )
    total_bankroll_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('10000.0'),
        validators=[MinValueValidator(Decimal('100.0'))],
        help_text="Total available bankroll in USD"
    )
    
    # Execution Settings
    auto_execution_enabled = models.BooleanField(
        default=False,
        help_text="Whether to auto-execute trades without confirmation"
    )
    max_concurrent_positions = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text="Maximum number of concurrent positions"
    )
    require_manual_approval = models.BooleanField(
        default=True,
        help_text="Whether trades require manual approval"
    )
    
    # Chain Configuration
    enabled_chains = models.ManyToManyField(
        'trading.Chain',
        related_name='bot_configurations',
        help_text="Enabled blockchain networks"
    )
    enabled_dexes = models.ManyToManyField(
        'trading.DEX',
        related_name='bot_configurations',
        help_text="Enabled decentralized exchanges"
    )
    
    # Token Lists
    token_whitelist = models.ManyToManyField(
        'trading.Token',
        through='TokenWhitelistEntry',
        related_name='whitelisted_in_configs',
        blank=True,
        help_text="Whitelisted tokens"
    )
    token_blacklist = models.ManyToManyField(
        'trading.Token',
        through='TokenBlacklistEntry',
        related_name='blacklisted_in_configs',
        blank=True,
        help_text="Blacklisted tokens"
    )
    
    # Notification Settings
    notifications = models.JSONField(
        default=dict,
        blank=True,
        help_text="Notification preferences for this configuration"
    )
    
    # Advanced Settings
    advanced_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Advanced configuration parameters"
    )
    
    # Version Control
    version = models.PositiveIntegerField(
        default=1,
        help_text="Configuration version number"
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Whether this is the user's default configuration"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this configuration was used"
    )

    class Meta:
        unique_together = ['user', 'name']
        ordering = ['-last_used_at', '-updated_at']
        indexes = [
            models.Index(fields=['config_id']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['trading_mode']),
            models.Index(fields=['is_default']),
            models.Index(fields=['last_used_at']),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.trading_mode})"

    def clean(self) -> None:
        """Validate configuration settings."""
        if self.daily_loss_limit_usd > self.total_bankroll_usd:
            raise ValidationError("Daily loss limit cannot exceed total bankroll")
        if self.max_position_size_usd > self.total_bankroll_usd:
            raise ValidationError("Max position size cannot exceed total bankroll")


class TokenWhitelistEntry(models.Model):
    """
    Represents a token whitelist entry for a bot configuration.
    
    Allows fine-grained control over which tokens are allowed
    for trading with specific parameters per token.
    """
    
    config = models.ForeignKey(
        BotConfiguration,
        on_delete=models.CASCADE,
        related_name='whitelist_entries'
    )
    token = models.ForeignKey(
        'trading.Token',
        on_delete=models.CASCADE,
        related_name='whitelist_entries'
    )
    
    # Entry-specific limits
    max_position_size_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Override max position size for this token"
    )
    max_slippage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Override max slippage for this token"
    )
    
    # Metadata
    reason = models.CharField(
        max_length=200,
        blank=True,
        help_text="Reason for whitelisting this token"
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about this token"
    )
    
    added_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whitelist_additions'
    )

    class Meta:
        unique_together = ['config', 'token']
        ordering = ['token__symbol']

    def __str__(self) -> str:
        return f"{self.token.symbol} whitelisted in {self.config.name}"


class TokenBlacklistEntry(models.Model):
    """
    Represents a token blacklist entry for a bot configuration.
    
    Prevents trading of specific tokens with reasons and
    audit trail for compliance and risk management.
    """
    
    class BlacklistReason(models.TextChoices):
        HONEYPOT = 'HONEYPOT', 'Honeypot Token'
        HIGH_RISK = 'HIGH_RISK', 'High Risk'
        SCAM = 'SCAM', 'Known Scam'
        REGULATORY = 'REGULATORY', 'Regulatory Concerns'
        TECHNICAL = 'TECHNICAL', 'Technical Issues'
        USER_CHOICE = 'USER_CHOICE', 'User Choice'
        COMPLIANCE = 'COMPLIANCE', 'Compliance Requirement'
    
    config = models.ForeignKey(
        BotConfiguration,
        on_delete=models.CASCADE,
        related_name='blacklist_entries'
    )
    token = models.ForeignKey(
        'trading.Token',
        on_delete=models.CASCADE,
        related_name='blacklist_entries'
    )
    
    # Blacklist Details
    reason = models.CharField(
        max_length=15,
        choices=BlacklistReason.choices
    )
    description = models.TextField(
        help_text="Detailed reason for blacklisting"
    )
    
    # Validity
    is_permanent = models.BooleanField(
        default=True,
        help_text="Whether this blacklist entry is permanent"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this blacklist entry expires (if not permanent)"
    )
    
    # Evidence
    evidence_urls = models.JSONField(
        default=list,
        blank=True,
        help_text="URLs to evidence supporting the blacklist"
    )
    risk_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Risk score that led to blacklisting (0-100)"
    )
    
    # Audit Trail
    added_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blacklist_additions'
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last review date"
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blacklist_reviews'
    )

    class Meta:
        unique_together = ['config', 'token']
        ordering = ['-added_at']
        indexes = [
            models.Index(fields=['config', 'reason']),
            models.Index(fields=['token']),
            models.Index(fields=['is_permanent']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['added_at']),
        ]

    def __str__(self) -> str:
        return f"{self.token.symbol} blacklisted in {self.config.name} ({self.reason})"

    @property
    def is_active(self) -> bool:
        """Check if blacklist entry is currently active."""
        if not self.is_permanent and self.expires_at:
            return timezone.now() < self.expires_at
        return True


class TradingSession(models.Model):
    """
    Represents an active or completed trading session.
    
    Tracks bot execution sessions with performance metrics,
    status, and configuration snapshots for analysis.
    """
    
    class SessionStatus(models.TextChoices):
        STARTING = 'STARTING', 'Starting'
        ACTIVE = 'ACTIVE', 'Active'
        PAUSED = 'PAUSED', 'Paused'
        STOPPING = 'STOPPING', 'Stopping'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'
        EMERGENCY_STOP = 'EMERGENCY_STOP', 'Emergency Stop'
    
    # Identification
    session_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique session identifier"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='trading_sessions'
    )
    name = models.CharField(
        max_length=200,
        help_text="Session name or description"
    )
    
    # Configuration
    bot_config = models.ForeignKey(
        BotConfiguration,
        on_delete=models.CASCADE,
        related_name='trading_sessions'
    )
    config_snapshot = models.JSONField(
        help_text="Snapshot of bot configuration at session start"
    )
    
    # Session State
    status = models.CharField(
        max_length=15,
        choices=SessionStatus.choices,
        default=SessionStatus.STARTING
    )
    trading_mode = models.CharField(
        max_length=10,
        choices=BotConfiguration.TradingMode.choices
    )
    
    # Performance Metrics
    total_opportunities = models.PositiveIntegerField(
        default=0,
        help_text="Total opportunities evaluated"
    )
    trades_executed = models.PositiveIntegerField(
        default=0,
        help_text="Number of trades executed"
    )
    successful_trades = models.PositiveIntegerField(
        default=0,
        help_text="Number of successful trades"
    )
    failed_trades = models.PositiveIntegerField(
        default=0,
        help_text="Number of failed trades"
    )
    
    # Financial Metrics
    starting_balance_usd = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=Decimal('0'),
        help_text="Starting balance in USD"
    )
    current_balance_usd = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=Decimal('0'),
        help_text="Current balance in USD"
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
    
    # Risk Metrics
    max_drawdown_usd = models.DecimalField(
        max_digits=15,
        decimal_places=8,
        default=Decimal('0'),
        help_text="Maximum drawdown in USD"
    )
    max_drawdown_percent = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=Decimal('0'),
        help_text="Maximum drawdown percentage"
    )
    daily_loss_usd = models.DecimalField(
        max_digits=15,
        decimal_places=8,
        default=Decimal('0'),
        help_text="Daily loss amount in USD"
    )
    
    # Execution Quality
    average_execution_time_ms = models.FloatField(
        null=True,
        blank=True,
        help_text="Average trade execution time in milliseconds"
    )
    average_slippage_percent = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Average slippage percentage"
    )
    
    # Error Tracking
    error_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of errors encountered"
    )
    last_error = models.TextField(
        blank=True,
        help_text="Last error message"
    )
    
    # Circuit Breakers
    daily_limit_hit = models.BooleanField(
        default=False,
        help_text="Whether daily loss limit was hit"
    )
    emergency_stop_triggered = models.BooleanField(
        default=False,
        help_text="Whether emergency stop was triggered"
    )
    
    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    paused_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When session was paused"
    )
    stopped_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When session was stopped"
    )
    last_activity_at = models.DateTimeField(
        auto_now=True,
        help_text="Last activity timestamp"
    )

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['session_id']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['bot_config']),
            models.Index(fields=['status']),
            models.Index(fields=['trading_mode']),
            models.Index(fields=['started_at']),
            models.Index(fields=['daily_limit_hit']),
            models.Index(fields=['emergency_stop_triggered']),
        ]

    def __str__(self) -> str:
        return f"Session {self.name} - {self.status}"

    @property
    def total_pnl_usd(self) -> Decimal:
        """Calculate total PnL (realized + unrealized)."""
        return self.realized_pnl_usd + self.unrealized_pnl_usd

    @property
    def duration_hours(self) -> Optional[float]:
        """Calculate session duration in hours."""
        end_time = self.stopped_at or timezone.now()
        delta = end_time - self.started_at
        return delta.total_seconds() / 3600

    @property
    def success_rate_percent(self) -> Optional[Decimal]:
        """Calculate trade success rate percentage."""
        if self.trades_executed > 0:
            return (Decimal(self.successful_trades) / Decimal(self.trades_executed)) * 100
        return None

    @property
    def roi_percent(self) -> Optional[Decimal]:
        """Calculate return on investment percentage."""
        if self.starting_balance_usd > 0:
            return (self.total_pnl_usd / self.starting_balance_usd) * 100
        return None


class Alert(models.Model):
    """
    Represents system alerts and notifications for users.
    
    Manages different types of alerts including trading notifications,
    risk warnings, system status, and performance updates.
    """
    
    class AlertType(models.TextChoices):
        TRADE_EXECUTED = 'TRADE_EXECUTED', 'Trade Executed'
        POSITION_OPENED = 'POSITION_OPENED', 'Position Opened'
        POSITION_CLOSED = 'POSITION_CLOSED', 'Position Closed'
        PROFIT_TARGET = 'PROFIT_TARGET', 'Profit Target Hit'
        STOP_LOSS = 'STOP_LOSS', 'Stop Loss Hit'
        RISK_WARNING = 'RISK_WARNING', 'Risk Warning'
        DAILY_LIMIT = 'DAILY_LIMIT', 'Daily Limit Hit'
        SYSTEM_ERROR = 'SYSTEM_ERROR', 'System Error'
        EMERGENCY_STOP = 'EMERGENCY_STOP', 'Emergency Stop'
        HIGH_VOLATILITY = 'HIGH_VOLATILITY', 'High Volatility'
        HONEYPOT_DETECTED = 'HONEYPOT_DETECTED', 'Honeypot Detected'
        SYSTEM_STATUS = 'SYSTEM_STATUS', 'System Status'
    
    class AlertSeverity(models.TextChoices):
        INFO = 'INFO', 'Info'
        WARNING = 'WARNING', 'Warning'
        ERROR = 'ERROR', 'Error'
        CRITICAL = 'CRITICAL', 'Critical'
    
    class AlertStatus(models.TextChoices):
        UNREAD = 'UNREAD', 'Unread'
        READ = 'READ', 'Read'
        DISMISSED = 'DISMISSED', 'Dismissed'
        ARCHIVED = 'ARCHIVED', 'Archived'
    
    # Identification
    alert_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique alert identifier"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='alerts'
    )
    
    # Alert Details
    alert_type = models.CharField(
        max_length=20,
        choices=AlertType.choices
    )
    severity = models.CharField(
        max_length=10,
        choices=AlertSeverity.choices
    )
    status = models.CharField(
        max_length=10,
        choices=AlertStatus.choices,
        default=AlertStatus.UNREAD
    )
    
    # Content
    title = models.CharField(
        max_length=200,
        help_text="Alert title"
    )
    message = models.TextField(
        help_text="Alert message content"
    )
    
    # Related Objects
    trading_session = models.ForeignKey(
        TradingSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alerts'
    )
    trade = models.ForeignKey(
        'trading.Trade',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alerts'
    )
    position = models.ForeignKey(
        'trading.Position',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alerts'
    )
    
    # Additional Data
    data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional alert data"
    )
    
    # Actions
    action_required = models.BooleanField(
        default=False,
        help_text="Whether this alert requires user action"
    )
    action_url = models.URLField(
        blank=True,
        help_text="URL for alert action"
    )
    action_text = models.CharField(
        max_length=100,
        blank=True,
        help_text="Text for action button"
    )
    
    # Delivery
    email_sent = models.BooleanField(
        default=False,
        help_text="Whether email notification was sent"
    )
    sms_sent = models.BooleanField(
        default=False,
        help_text="Whether SMS notification was sent"
    )
    push_sent = models.BooleanField(
        default=False,
        help_text="Whether push notification was sent"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When alert was read"
    )
    dismissed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When alert was dismissed"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When alert expires"
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['alert_id']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['alert_type', 'severity']),
            models.Index(fields=['status']),
            models.Index(fields=['action_required']),
            models.Index(fields=['created_at']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self) -> str:
        return f"{self.alert_type} - {self.title}"

    @property
    def is_expired(self) -> bool:
        """Check if alert has expired."""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False


class SystemStatus(models.Model):
    """
    Tracks overall system status and health metrics.
    
    Provides real-time status information for monitoring
    system performance, uptime, and service availability.
    """
    
    class ServiceStatus(models.TextChoices):
        OPERATIONAL = 'OPERATIONAL', 'Operational'
        DEGRADED = 'DEGRADED', 'Degraded Performance'
        PARTIAL_OUTAGE = 'PARTIAL_OUTAGE', 'Partial Outage'
        MAJOR_OUTAGE = 'MAJOR_OUTAGE', 'Major Outage'
        MAINTENANCE = 'MAINTENANCE', 'Under Maintenance'
    
    # Identification
    status_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique status record identifier"
    )
    
    # Service Status
    trading_engine_status = models.CharField(
        max_length=15,
        choices=ServiceStatus.choices,
        default=ServiceStatus.OPERATIONAL
    )
    risk_engine_status = models.CharField(
        max_length=15,
        choices=ServiceStatus.choices,
        default=ServiceStatus.OPERATIONAL
    )
    wallet_service_status = models.CharField(
        max_length=15,
        choices=ServiceStatus.choices,
        default=ServiceStatus.OPERATIONAL
    )
    api_service_status = models.CharField(
        max_length=15,
        choices=ServiceStatus.choices,
        default=ServiceStatus.OPERATIONAL
    )
    
    # Chain Status
    ethereum_status = models.CharField(
        max_length=15,
        choices=ServiceStatus.choices,
        default=ServiceStatus.OPERATIONAL
    )
    base_status = models.CharField(
        max_length=15,
        choices=ServiceStatus.choices,
        default=ServiceStatus.OPERATIONAL
    )
    
    # Performance Metrics
    avg_response_time_ms = models.FloatField(
        null=True,
        blank=True,
        help_text="Average API response time in milliseconds"
    )
    error_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Error rate percentage"
    )
    uptime_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Uptime percentage"
    )
    
    # Active Sessions
    active_sessions = models.PositiveIntegerField(
        default=0,
        help_text="Number of active trading sessions"
    )
    active_users = models.PositiveIntegerField(
        default=0,
        help_text="Number of active users"
    )
    
    # Resource Usage
    cpu_usage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="CPU usage percentage"
    )
    memory_usage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Memory usage percentage"
    )
    
    # Additional Metrics
    metrics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional system metrics"
    )
    
    # Status Messages
    status_message = models.TextField(
        blank=True,
        help_text="Current status message"
    )
    incident_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Incident ID if there's an ongoing issue"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        get_latest_by = 'created_at'
        indexes = [
            models.Index(fields=['status_id']),
            models.Index(fields=['created_at']),
            models.Index(fields=['trading_engine_status']),
            models.Index(fields=['active_sessions']),
        ]

    def __str__(self) -> str:
        return f"System Status - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    @property
    def overall_status(self) -> str:
        """Calculate overall system status."""
        statuses = [
            self.trading_engine_status,
            self.risk_engine_status,
            self.wallet_service_status,
            self.api_service_status,
        ]
        
        if any(status == self.ServiceStatus.MAJOR_OUTAGE for status in statuses):
            return self.ServiceStatus.MAJOR_OUTAGE
        elif any(status == self.ServiceStatus.PARTIAL_OUTAGE for status in statuses):
            return self.ServiceStatus.PARTIAL_OUTAGE
        elif any(status == self.ServiceStatus.DEGRADED for status in statuses):
            return self.ServiceStatus.DEGRADED
        elif any(status == self.ServiceStatus.MAINTENANCE for status in statuses):
            return self.ServiceStatus.MAINTENANCE
        else:
            return self.ServiceStatus.OPERATIONAL