"""
Django models for the dashboard app.

This module defines user profile, bot configuration, and dashboard-related
models for the DEX auto-trading bot's control interface.

Updated to include missing fields that were causing database errors:
- analysis_depth
- execution_timeout_ms  
- max_slippage_percent
- mev_protection_enabled
- risk_tolerance_level
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
import uuid

from shared.constants import RISK_LEVELS
from django.db import models
from shared.models.mixins import TimestampMixin, UUIDMixin
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class UserProfile(TimestampMixin):
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
    
    class Meta:
        indexes = [
            models.Index(fields=['profile_id']),
            models.Index(fields=['user']),
            models.Index(fields=['experience_level']),
            models.Index(fields=['risk_tolerance']),
        ]

    def __str__(self) -> str:
        return f"{self.user.username} Profile"

    def save(self, *args, **kwargs):
        """Override save to add logging."""
        try:
            logger.debug(f"Saving UserProfile for user: {self.user.username}")
            super().save(*args, **kwargs)
            logger.info(f"Successfully saved UserProfile for user: {self.user.username}")
        except Exception as e:
            logger.error(f"Error saving UserProfile for user {self.user.username}: {e}", exc_info=True)
            raise


class BotConfiguration(TimestampMixin):
    """
    Represents a trading bot configuration profile.
    
    Stores complete bot settings including strategies, risk parameters,
    and execution preferences that can be applied to trading sessions.
    
    Updated with missing fields to fix fast_lane configuration errors.
    """
    
    class ConfigStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        ACTIVE = 'ACTIVE', 'Active'
        PAUSED = 'PAUSED', 'Paused'
        ARCHIVED = 'ARCHIVED', 'Archived'
        INACTIVE = 'INACTIVE', 'Inactive'  # Added for compatibility
    
    class TradingMode(models.TextChoices):
        PAPER = 'PAPER', 'Paper Trading'
        LIVE = 'LIVE', 'Live Trading'
        SHADOW = 'SHADOW', 'Shadow Trading'
        FAST_LANE = 'FAST_LANE', 'Fast Lane'  # Added for compatibility
        SMART_LANE = 'SMART_LANE', 'Smart Lane'  # Added for compatibility
    
    class RiskToleranceLevel(models.TextChoices):
        """Risk tolerance levels for bot configuration."""
        VERY_LOW = 'VERY_LOW', 'Very Low'
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        VERY_HIGH = 'VERY_HIGH', 'Very High'
    
    class AnalysisDepth(models.TextChoices):
        """Analysis depth options for smart lane."""
        BASIC = 'BASIC', 'Basic'
        STANDARD = 'STANDARD', 'Standard'
        COMPREHENSIVE = 'COMPREHENSIVE', 'Comprehensive'
        DEEP = 'DEEP', 'Deep Analysis'
    
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
        max_length=15,  # Increased to accommodate FAST_LANE/SMART_LANE
        choices=TradingMode.choices,
        default=TradingMode.PAPER
    )
    
    # Strategy Configuration - Made optional for compatibility
    strategy = models.ForeignKey(
        'trading.Strategy',
        on_delete=models.CASCADE,
        related_name='bot_configurations',
        null=True,
        blank=True,
        help_text="Trading strategy to use"
    )
    risk_profile = models.ForeignKey(
        'risk.RiskProfile',
        on_delete=models.CASCADE,
        related_name='bot_configurations',
        null=True,
        blank=True,
        help_text="Risk profile to apply"
    )
    
    # NEW FIELDS - These were missing and causing the errors
    risk_tolerance_level = models.CharField(
        max_length=15,
        choices=RiskToleranceLevel.choices,
        default=RiskToleranceLevel.MEDIUM,
        help_text="Risk tolerance level for this configuration"
    )
    
    execution_timeout_ms = models.PositiveIntegerField(
        default=5000,  # 5 seconds default
        validators=[MinValueValidator(100), MaxValueValidator(30000)],  # 100ms to 30s
        help_text="Maximum execution timeout in milliseconds"
    )
    
    max_slippage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('2.0'),
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('50.0'))],
        help_text="Maximum acceptable slippage percentage"
    )
    
    mev_protection_enabled = models.BooleanField(
        default=True,
        help_text="Whether MEV (Maximum Extractable Value) protection is enabled"
    )
    
    analysis_depth = models.CharField(
        max_length=15,
        choices=AnalysisDepth.choices,
        default=AnalysisDepth.STANDARD,
        help_text="Depth of analysis for smart lane trading"
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
    
    # Chain Configuration - Made optional for compatibility
    enabled_chains = models.ManyToManyField(
        'trading.Chain',
        related_name='bot_configurations',
        blank=True,
        help_text="Enabled blockchain networks"
    )
    enabled_dexes = models.ManyToManyField(
        'trading.DEX',
        related_name='bot_configurations',
        blank=True,
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
            models.Index(fields=['risk_tolerance_level']),  # New index
            models.Index(fields=['mev_protection_enabled']),  # New index
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.trading_mode})"

    def clean(self) -> None:
        """Validate configuration settings with comprehensive error handling."""
        try:
            logger.debug(f"Validating BotConfiguration: {self.name}")
            
            # Existing validations
            if self.daily_loss_limit_usd and self.total_bankroll_usd:
                if self.daily_loss_limit_usd > self.total_bankroll_usd:
                    error_msg = "Daily loss limit cannot exceed total bankroll"
                    logger.warning(f"Validation error for {self.name}: {error_msg}")
                    raise ValidationError(error_msg)
            
            if self.max_position_size_usd and self.total_bankroll_usd:
                if self.max_position_size_usd > self.total_bankroll_usd:
                    error_msg = "Max position size cannot exceed total bankroll"
                    logger.warning(f"Validation error for {self.name}: {error_msg}")
                    raise ValidationError(error_msg)
            
            # New validations for added fields
            if self.execution_timeout_ms:
                if self.trading_mode == 'FAST_LANE' and self.execution_timeout_ms > 1000:
                    logger.warning(f"Fast lane timeout of {self.execution_timeout_ms}ms is high - consider reducing for optimal performance")
                
                if self.execution_timeout_ms < 100:
                    error_msg = "Execution timeout cannot be less than 100ms"
                    logger.error(f"Validation error for {self.name}: {error_msg}")
                    raise ValidationError(error_msg)
            
            if self.max_slippage_percent:
                if self.max_slippage_percent > Decimal('10.0'):
                    logger.warning(f"High slippage tolerance of {self.max_slippage_percent}% for {self.name}")
                
                if self.max_slippage_percent < Decimal('0.1'):
                    error_msg = "Slippage cannot be less than 0.1%"
                    logger.error(f"Validation error for {self.name}: {error_msg}")
                    raise ValidationError(error_msg)
            
            # Validate fast lane specific settings
            if self.trading_mode == 'FAST_LANE':
                if self.analysis_depth == 'COMPREHENSIVE':
                    logger.warning(f"Fast lane config {self.name} using comprehensive analysis - may impact speed")
                
                if not self.mev_protection_enabled:
                    logger.warning(f"Fast lane config {self.name} has MEV protection disabled - high risk")
            
            logger.debug(f"Successfully validated BotConfiguration: {self.name}")
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during validation of {self.name}: {e}", exc_info=True)
            raise ValidationError(f"Configuration validation failed: {e}")

    def save(self, *args, **kwargs):
        """Override save to add logging and validation."""
        try:
            logger.debug(f"Saving BotConfiguration: {self.name} for user: {self.user.username}")
            
            # Run validation
            self.full_clean()
            
            # Update version on changes (excluding created_at updates)
            if self.pk and not kwargs.get('update_fields') == ['last_used_at']:
                original = BotConfiguration.objects.get(pk=self.pk)
                if (original.max_position_size_usd != self.max_position_size_usd or
                    original.risk_tolerance_level != self.risk_tolerance_level or
                    original.execution_timeout_ms != self.execution_timeout_ms or
                    original.max_slippage_percent != self.max_slippage_percent or
                    original.mev_protection_enabled != self.mev_protection_enabled or
                    original.analysis_depth != self.analysis_depth):
                    self.version += 1
                    logger.info(f"Updated version to {self.version} for config: {self.name}")
            
            super().save(*args, **kwargs)
            logger.info(f"Successfully saved BotConfiguration: {self.name} (ID: {self.config_id})")
            
        except Exception as e:
            logger.error(f"Error saving BotConfiguration {self.name} for user {self.user.username}: {e}", exc_info=True)
            raise

    @property
    def is_fast_lane(self) -> bool:
        """Check if this is a fast lane configuration."""
        return self.trading_mode == 'FAST_LANE'

    @property 
    def is_smart_lane(self) -> bool:
        """Check if this is a smart lane configuration."""
        return self.trading_mode == 'SMART_LANE'

    @property
    def risk_score(self) -> int:
        """Calculate a risk score based on configuration parameters."""
        try:
            score = 0
            
            # Risk tolerance component (0-40 points)
            risk_scores = {
                'VERY_LOW': 0,
                'LOW': 10,
                'MEDIUM': 20,
                'HIGH': 30,
                'VERY_HIGH': 40
            }
            score += risk_scores.get(self.risk_tolerance_level, 20)
            
            # Position size component (0-30 points)
            if self.max_position_size_usd and self.total_bankroll_usd:
                position_ratio = float(self.max_position_size_usd / self.total_bankroll_usd)
                if position_ratio > 0.5:
                    score += 30
                elif position_ratio > 0.3:
                    score += 20
                elif position_ratio > 0.1:
                    score += 10
            
            # Slippage component (0-20 points)
            if self.max_slippage_percent:
                if self.max_slippage_percent > Decimal('5.0'):
                    score += 20
                elif self.max_slippage_percent > Decimal('2.0'):
                    score += 10
            
            # MEV protection component (-10 points if enabled, +10 if disabled)
            score += -10 if self.mev_protection_enabled else 10
            
            return max(0, min(100, score))
            
        except Exception as e:
            logger.error(f"Error calculating risk score for {self.name}: {e}", exc_info=True)
            return 50  # Default medium risk


class TokenWhitelistEntry(TimestampMixin):
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

    def save(self, *args, **kwargs):
        """Override save to add logging."""
        try:
            logger.debug(f"Saving TokenWhitelistEntry for token: {self.token.symbol} in config: {self.config.name}")
            super().save(*args, **kwargs)
            logger.info(f"Successfully whitelisted token {self.token.symbol} in {self.config.name}")
        except Exception as e:
            logger.error(f"Error saving whitelist entry for {self.token.symbol}: {e}", exc_info=True)
            raise


class TokenBlacklistEntry(TimestampMixin):
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
        try:
            if not self.is_permanent and self.expires_at:
                is_active = timezone.now() < self.expires_at
                logger.debug(f"Blacklist entry for {self.token.symbol} is {'active' if is_active else 'expired'}")
                return is_active
            return True
        except Exception as e:
            logger.error(f"Error checking blacklist status for {self.token.symbol}: {e}", exc_info=True)
            return True  # Err on the side of caution

    def save(self, *args, **kwargs):
        """Override save to add logging."""
        try:
            logger.debug(f"Saving TokenBlacklistEntry for token: {self.token.symbol} with reason: {self.reason}")
            super().save(*args, **kwargs)
            logger.warning(f"Blacklisted token {self.token.symbol} in {self.config.name} - Reason: {self.reason}")
        except Exception as e:
            logger.error(f"Error saving blacklist entry for {self.token.symbol}: {e}", exc_info=True)
            raise


class TradingSession(TimestampMixin):
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
        max_length=15,  # Increased to match BotConfiguration
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
        try:
            return self.realized_pnl_usd + self.unrealized_pnl_usd
        except Exception as e:
            logger.error(f"Error calculating total PnL for session {self.name}: {e}", exc_info=True)
            return Decimal('0')

    @property
    def duration_hours(self) -> Optional[float]:
        """Calculate session duration in hours."""
        try:
            end_time = self.stopped_at or timezone.now()
            delta = end_time - self.started_at
            return delta.total_seconds() / 3600
        except Exception as e:
            logger.error(f"Error calculating duration for session {self.name}: {e}", exc_info=True)
            return None

    @property
    def success_rate_percent(self) -> Optional[Decimal]:
        """Calculate trade success rate percentage."""
        try:
            if self.trades_executed > 0:
                return (Decimal(self.successful_trades) / Decimal(self.trades_executed)) * 100
            return None
        except Exception as e:
            logger.error(f"Error calculating success rate for session {self.name}: {e}", exc_info=True)
            return None

    @property
    def roi_percent(self) -> Optional[Decimal]:
        """Calculate return on investment percentage."""
        try:
            if self.starting_balance_usd > 0:
                return (self.total_pnl_usd / self.starting_balance_usd) * 100
            return None
        except Exception as e:
            logger.error(f"Error calculating ROI for session {self.name}: {e}", exc_info=True)
            return None

    def save(self, *args, **kwargs):
        """Override save to add logging."""
        try:
            logger.debug(f"Saving TradingSession: {self.name} with status: {self.status}")
            super().save(*args, **kwargs)
            
            # Log significant status changes
            if self.status in ['ACTIVE', 'COMPLETED', 'FAILED', 'EMERGENCY_STOP']:
                logger.info(f"TradingSession {self.name} status changed to: {self.status}")
                
        except Exception as e:
            logger.error(f"Error saving TradingSession {self.name}: {e}", exc_info=True)
            raise


class Alert(TimestampMixin):
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
        try:
            if self.expires_at:
                is_expired = timezone.now() > self.expires_at
                logger.debug(f"Alert {self.title} is {'expired' if is_expired else 'active'}")
                return is_expired
            return False
        except Exception as e:
            logger.error(f"Error checking alert expiration for {self.title}: {e}", exc_info=True)
            return False

    def save(self, *args, **kwargs):
        """Override save to add logging."""
        try:
            logger.debug(f"Saving Alert: {self.title} ({self.alert_type}) for user: {self.user.username}")
            super().save(*args, **kwargs)
            
            # Log critical alerts
            if self.severity in ['ERROR', 'CRITICAL']:
                logger.warning(f"Critical alert created: {self.title} for user {self.user.username}")
                
        except Exception as e:
            logger.error(f"Error saving Alert {self.title}: {e}", exc_info=True)
            raise


class SystemStatus(TimestampMixin):
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
        """Calculate overall system status with proper error handling."""
        try:
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
                
        except Exception as e:
            logger.error(f"Error calculating overall system status: {e}", exc_info=True)
            return self.ServiceStatus.DEGRADED

    def save(self, *args, **kwargs):
        """Override save to add logging and status change notifications."""
        try:
            logger.debug(f"Saving SystemStatus with overall status: {self.overall_status}")
            
            # Check for status changes if this is an update
            if self.pk:
                try:
                    previous = SystemStatus.objects.get(pk=self.pk)
                    if previous.overall_status != self.overall_status:
                        logger.warning(f"System status changed from {previous.overall_status} to {self.overall_status}")
                except SystemStatus.DoesNotExist:
                    pass  # New record
            
            super().save(*args, **kwargs)
            logger.info(f"SystemStatus saved - Overall: {self.overall_status}")
            
        except Exception as e:
            logger.error(f"Error saving SystemStatus: {e}", exc_info=True)
            raise


"""
Fund Allocation Model Addition

Add this to your existing dashboard/models.py file to enable persistent
storage of user fund allocation settings.

File: dexproject/dashboard/models.py (addition)
"""

import uuid
from decimal import Decimal
from typing import Dict, Any

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from shared.models.mixins import TimestampMixin


class FundAllocation(TimestampMixin):
    """
    User fund allocation settings for trading bot.
    
    Stores user preferences for how much of their wallet balance
    should be allocated for trading, including safety settings
    and risk management parameters.
    """
    
    class AllocationMethod(models.TextChoices):
        PERCENTAGE = 'PERCENTAGE', 'Percentage of Balance'
        FIXED = 'FIXED', 'Fixed Amount'
    
    class RiskLevel(models.TextChoices):
        CONSERVATIVE = 'CONSERVATIVE', 'Conservative'
        MODERATE = 'MODERATE', 'Moderate'
        AGGRESSIVE = 'AGGRESSIVE', 'Aggressive'
    
    # Identification
    allocation_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique allocation identifier"
    )
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='fund_allocation',
        help_text="User who owns this allocation setting"
    )
    
    # Primary Allocation Settings
    allocation_method = models.CharField(
        max_length=15,
        choices=AllocationMethod.choices,
        default=AllocationMethod.PERCENTAGE,
        help_text="Method for determining trading allocation"
    )
    
    allocation_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('10.00'),
        validators=[MinValueValidator(Decimal('1.00')), MaxValueValidator(Decimal('50.00'))],
        help_text="Percentage of available balance to allocate (1-50%)"
    )
    
    allocation_fixed_amount = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        default=Decimal('0.10000000'),
        validators=[MinValueValidator(Decimal('0.00100000'))],
        help_text="Fixed amount in ETH to allocate for trading"
    )
    
    # Safety and Risk Management
    daily_spending_limit = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        default=Decimal('1.00000000'),
        validators=[MinValueValidator(Decimal('0.00100000'))],
        help_text="Maximum ETH that can be spent per day"
    )
    
    minimum_balance_reserve = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        default=Decimal('0.05000000'),
        validators=[MinValueValidator(Decimal('0.00100000'))],
        help_text="Minimum ETH balance to always keep in wallet"
    )
    
    # Trading Preferences
    auto_rebalance_enabled = models.BooleanField(
        default=True,
        help_text="Automatically rebalance allocation after successful trades"
    )
    
    stop_loss_enabled = models.BooleanField(
        default=True,
        help_text="Enable automatic stop-loss protection"
    )
    
    stop_loss_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        validators=[MinValueValidator(Decimal('1.00')), MaxValueValidator(Decimal('25.00'))],
        help_text="Stop loss percentage (1-25%)"
    )
    
    # Risk Assessment
    risk_level = models.CharField(
        max_length=15,
        choices=RiskLevel.choices,
        default=RiskLevel.CONSERVATIVE,
        help_text="Calculated risk level based on allocation settings"
    )
    
    # Usage Tracking
    total_allocated_eth = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        default=Decimal('0.00000000'),
        help_text="Total ETH currently allocated for trading"
    )
    
    daily_spent_today = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        default=Decimal('0.00000000'),
        help_text="ETH spent today (resets daily)"
    )
    
    last_daily_reset = models.DateField(
        default=timezone.now,
        help_text="Last date when daily spending was reset"
    )
    
    # Status and Activity
    is_active = models.BooleanField(
        default=True,
        help_text="Whether allocation settings are currently active"
    )
    
    last_modified_by_user = models.DateTimeField(
        auto_now=True,
        help_text="When user last modified these settings"
    )
    
    # Metadata
    settings_version = models.PositiveIntegerField(
        default=1,
        help_text="Version number for settings schema"
    )
    
    notes = models.TextField(
        blank=True,
        help_text="User notes about allocation strategy"
    )
    
    class Meta:
        db_table = 'dashboard_fund_allocation'
        verbose_name = 'Fund Allocation'
        verbose_name_plural = 'Fund Allocations'
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['is_active']),
            models.Index(fields=['last_daily_reset']),
        ]
    
    def __str__(self) -> str:
        """String representation of fund allocation."""
        if self.allocation_method == self.AllocationMethod.PERCENTAGE:
            return f"{self.user.username}: {self.allocation_percentage}% allocation"
        else:
            return f"{self.user.username}: {self.allocation_fixed_amount} ETH allocation"
    
    def save(self, *args, **kwargs):
        """Override save to automatically calculate risk level and reset daily spending."""
        # Update risk level based on allocation settings
        self.risk_level = self.calculate_risk_level()
        
        # Reset daily spending if it's a new day
        today = timezone.now().date()
        if self.last_daily_reset < today:
            self.daily_spent_today = Decimal('0.00000000')
            self.last_daily_reset = today
        
        super().save(*args, **kwargs)
    
    def calculate_risk_level(self) -> str:
        """
        Calculate risk level based on allocation percentage.
        
        Returns:
            Risk level string
        """
        if self.allocation_method == self.AllocationMethod.PERCENTAGE:
            percentage = float(self.allocation_percentage)
        else:
            # For fixed amounts, assume a reasonable balance to calculate percentage
            # This is an approximation and should be updated with actual balance
            assumed_balance = 1.0  # 1 ETH
            percentage = (float(self.allocation_fixed_amount) / assumed_balance) * 100
        
        if percentage <= 5:
            return self.RiskLevel.CONSERVATIVE
        elif percentage <= 20:
            return self.RiskLevel.MODERATE
        else:
            return self.RiskLevel.AGGRESSIVE
    
    def get_daily_remaining_limit(self) -> Decimal:
        """
        Calculate remaining daily spending limit.
        
        Returns:
            Remaining ETH that can be spent today
        """
        # Reset if it's a new day
        today = timezone.now().date()
        if self.last_daily_reset < today:
            self.daily_spent_today = Decimal('0.00000000')
            self.last_daily_reset = today
            self.save(update_fields=['daily_spent_today', 'last_daily_reset'])
        
        return max(Decimal('0.00000000'), self.daily_spending_limit - self.daily_spent_today)
    
    def can_spend_amount(self, amount: Decimal) -> bool:
        """
        Check if an amount can be spent within daily limits.
        
        Args:
            amount: Amount in ETH to check
            
        Returns:
            True if amount can be spent, False otherwise
        """
        remaining = self.get_daily_remaining_limit()
        return amount <= remaining
    
    def record_spending(self, amount: Decimal) -> bool:
        """
        Record spending against daily limit.
        
        Args:
            amount: Amount in ETH that was spent
            
        Returns:
            True if spending was recorded, False if it would exceed limit
        """
        if not self.can_spend_amount(amount):
            return False
        
        self.daily_spent_today += amount
        self.save(update_fields=['daily_spent_today'])
        return True
    
    def calculate_available_for_trading(self, wallet_balance: Decimal) -> Dict[str, Any]:
        """
        Calculate how much is available for trading based on current settings.
        
        Args:
            wallet_balance: Current wallet balance in ETH
            
        Returns:
            Dictionary with allocation calculation details
        """
        # Calculate available balance after reserves
        available_balance = max(Decimal('0.00000000'), wallet_balance - self.minimum_balance_reserve)
        
        # Calculate trading allocation
        if self.allocation_method == self.AllocationMethod.PERCENTAGE:
            trading_amount = (available_balance * self.allocation_percentage) / Decimal('100')
        else:
            trading_amount = min(self.allocation_fixed_amount, available_balance)
        
        # Apply daily limit
        daily_remaining = self.get_daily_remaining_limit()
        actual_available = min(trading_amount, daily_remaining)
        
        return {
            'total_balance': wallet_balance,
            'reserved_balance': self.minimum_balance_reserve,
            'available_balance': available_balance,
            'calculated_allocation': trading_amount,
            'daily_limit': self.daily_spending_limit,
            'daily_remaining': daily_remaining,
            'daily_spent': self.daily_spent_today,
            'actual_available': actual_available,
            'risk_level': self.risk_level,
            'allocation_method': self.allocation_method,
            'allocation_percentage': self.allocation_percentage if self.allocation_method == self.AllocationMethod.PERCENTAGE else None,
            'allocation_fixed': self.allocation_fixed_amount if self.allocation_method == self.AllocationMethod.FIXED else None
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert allocation settings to dictionary format.
        
        Returns:
            Dictionary representation of allocation settings
        """
        return {
            'allocation_id': str(self.allocation_id),
            'user_id': self.user.id,
            'method': self.allocation_method,
            'percentage': float(self.allocation_percentage),
            'fixed_amount': float(self.allocation_fixed_amount),
            'daily_limit': float(self.daily_spending_limit),
            'minimum_balance': float(self.minimum_balance_reserve),
            'auto_rebalance': self.auto_rebalance_enabled,
            'stop_loss_enabled': self.stop_loss_enabled,
            'stop_loss_percentage': float(self.stop_loss_percentage),
            'risk_level': self.risk_level,
            'total_allocated': float(self.total_allocated_eth),
            'daily_spent': float(self.daily_spent_today),
            'daily_remaining': float(self.get_daily_remaining_limit()),
            'is_active': self.is_active,
            'last_modified': self.last_modified_by_user.isoformat(),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


# Add this to the existing models.py admin configuration section
class FundAllocationAdmin(TimestampMixin):
    """Admin interface for fund allocation settings."""
    
    list_display = [
        'user', 'allocation_method', 'allocation_percentage', 'allocation_fixed_amount',
        'risk_level', 'daily_spending_limit', 'is_active', 'last_modified_by_user'
    ]
    list_filter = [
        'allocation_method', 'risk_level', 'is_active', 'auto_rebalance_enabled',
        'stop_loss_enabled', 'last_daily_reset', 'created_at'
    ]
    search_fields = [
        'user__username', 'user__email', 'notes'
    ]
    readonly_fields = [
        'allocation_id', 'risk_level', 'daily_spent_today', 'last_daily_reset',
        'total_allocated_eth', 'created_at', 'updated_at'
    ]
    ordering = ['-last_modified_by_user']
    
    fieldsets = (
        ('User Information', {
            'fields': ('allocation_id', 'user', 'is_active')
        }),
        ('Allocation Settings', {
            'fields': (
                'allocation_method', 'allocation_percentage', 'allocation_fixed_amount'
            )
        }),
        ('Safety Settings', {
            'fields': (
                'daily_spending_limit', 'minimum_balance_reserve',
                'stop_loss_enabled', 'stop_loss_percentage'
            )
        }),
        ('Trading Preferences', {
            'fields': ('auto_rebalance_enabled', 'notes')
        }),
        ('Status and Tracking', {
            'fields': (
                'risk_level', 'total_allocated_eth', 'daily_spent_today',
                'last_daily_reset', 'settings_version'
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'last_modified_by_user'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimize admin queryset with select_related."""
        return super().get_queryset(request).select_related('user')


# Remember to register this in admin.py:
# from django.contrib import admin
# from .models import FundAllocation
# 
# @admin.register(FundAllocation)
# class FundAllocationAdmin(admin.ModelAdmin):
#     # Use the configuration above