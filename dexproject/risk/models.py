"""
Django models for the risk app.

This module defines risk assessment models including risk checks,
risk assessments, and risk configuration for the DEX auto-trading bot.
Implements industrial-grade risk management with hard blocks and soft penalties.
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional
import uuid

from shared.constants import RISK_LEVELS
from django.db import models
from shared.models.mixins import TimestampMixin, UUIDMixin
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class RiskCheckType(TimestampMixin):
    """
    Defines the types of risk checks that can be performed.
    
    Each risk check type has its own configuration, severity level,
    and execution parameters for consistent risk assessment.
    """
    
    class Severity(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
       
    
    class CheckCategory(models.TextChoices):
        HONEYPOT = 'HONEYPOT', 'Honeypot Detection'
        LIQUIDITY = 'LIQUIDITY', 'Liquidity Analysis'
        OWNERSHIP = 'OWNERSHIP', 'Ownership Check'
        TAX_ANALYSIS = 'TAX_ANALYSIS', 'Tax Analysis'
        CONTRACT_SECURITY = 'CONTRACT_SECURITY', 'Contract Security'
        HOLDER_ANALYSIS = 'HOLDER_ANALYSIS', 'Holder Analysis'
        MARKET_STRUCTURE = 'MARKET_STRUCTURE', 'Market Structure'
        SOCIAL_SIGNALS = 'SOCIAL_SIGNALS', 'Social Signals'
    
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Risk check name (e.g., 'Honeypot Detection', 'LP Lock Check')"
    )
    category = models.CharField(
        max_length=20,
        choices=CheckCategory.choices,
        help_text="Category of risk check"
    )
    description = models.TextField(
        help_text="Detailed description of what this check does"
    )
    severity = models.CharField(
        max_length=10,
        choices=Severity.choices,
        default=Severity.MEDIUM,
        help_text="Default severity level for this check"
    )
    is_blocking = models.BooleanField(
        default=False,
        help_text="Whether a failure of this check blocks trading (hard block)"
    )
    timeout_seconds = models.PositiveIntegerField(
        default=10,
        help_text="Maximum time allowed for this check to complete"
    )
    retry_count = models.PositiveIntegerField(
        default=2,
        help_text="Number of retries on failure"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this check is currently enabled"
    )
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.0'),
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('10.0'))],
        help_text="Weight for this check in overall risk scoring"
    )
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Check-specific configuration parameters"
    )
    class Meta:
        ordering = ['category', 'name']

    def __str__(self) -> str:
        return f"{self.name} ({self.category})"


class RiskAssessment(TimestampMixin):
    """
    Represents a complete risk assessment for a trading pair or token.
    
    Aggregates results from multiple risk checks and provides an overall
    risk score and trading recommendation.
    """
    
    class AssessmentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'
        TIMEOUT = 'TIMEOUT', 'Timeout'
    
    class RiskLevel(models.TextChoices):
        VERY_LOW = 'VERY_LOW', 'Very Low'
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        VERY_HIGH = 'VERY_HIGH', 'Very High'
        
    
    class Recommendation(models.TextChoices):
        STRONG_BUY = 'STRONG_BUY', 'Strong Buy'
        BUY = 'BUY', 'Buy'
        HOLD = 'HOLD', 'Hold'
        AVOID = 'AVOID', 'Avoid'
        STRONG_AVOID = 'STRONG_AVOID', 'Strong Avoid'
        BLOCKED = 'BLOCKED', 'Blocked'
    
    # Identification
    assessment_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique assessment identifier"
    )
    pair = models.ForeignKey(
        'trading.TradingPair',
        on_delete=models.CASCADE,
        related_name='risk_assessments'
    )
    token = models.ForeignKey(
        'trading.Token',
        on_delete=models.CASCADE,
        related_name='risk_assessments',
        help_text="Primary token being assessed"
    )
    
    # Assessment Status
    status = models.CharField(
        max_length=15,
        choices=AssessmentStatus.choices,
        default=AssessmentStatus.PENDING
    )
    risk_level = models.CharField(
        max_length=12,
        choices=RiskLevel.choices,
        null=True,
        blank=True
    )
    recommendation = models.CharField(
        max_length=15,
        choices=Recommendation.choices,
        null=True,
        blank=True
    )
    
    # Risk Scoring
    overall_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Overall risk score (0-100, higher is riskier)"
    )
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Confidence in the assessment (0-100)"
    )
    
    # Blocking Factors
    has_blocking_issues = models.BooleanField(
        default=False,
        help_text="Whether any blocking risk checks failed"
    )
    blocking_reasons = models.JSONField(
        default=list,
        blank=True,
        help_text="List of reasons why trading is blocked"
    )
    
    # Summary
    summary = models.TextField(
        blank=True,
        help_text="Human-readable summary of the risk assessment"
    )
    key_risks = models.JSONField(
        default=list,
        blank=True,
        help_text="List of key risks identified"
    )
    mitigating_factors = models.JSONField(
        default=list,
        blank=True,
        help_text="List of factors that reduce risk"
    )
    
    # Execution Context
    strategy = models.ForeignKey(
        'trading.Strategy',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Strategy context for this assessment"
    )
    context = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional context for the assessment"
    )
    
    # Timestamps
    started_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the assessment was started"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the assessment was completed"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this assessment expires and should be refreshed"
    )

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['assessment_id']),
            models.Index(fields=['pair', 'started_at']),
            models.Index(fields=['token', 'started_at']),
            models.Index(fields=['status']),
            models.Index(fields=['risk_level']),
            models.Index(fields=['recommendation']),
            models.Index(fields=['has_blocking_issues']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self) -> str:
        return f"Risk Assessment {self.assessment_id} - {self.pair}"

    @property
    def duration_seconds(self) -> Optional[int]:
        """Calculate assessment duration in seconds."""
        if self.completed_at and self.started_at:
            return int((self.completed_at - self.started_at).total_seconds())
        return None

    @property
    def is_expired(self) -> bool:
        """Check if this assessment has expired."""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False


class RiskCheckResult(TimestampMixin):
    """
    Represents the result of a single risk check within an assessment.
    
    Stores check-specific results, scores, and detailed findings
    for transparency and debugging.
    """
    
    class CheckStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        PASSED = 'PASSED', 'Passed'
        FAILED = 'FAILED', 'Failed'
        ERROR = 'ERROR', 'Error'
        TIMEOUT = 'TIMEOUT', 'Timeout'
        SKIPPED = 'SKIPPED', 'Skipped'
    
    # Identification
    result_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique result identifier"
    )
    assessment = models.ForeignKey(
        RiskAssessment,
        on_delete=models.CASCADE,
        related_name='check_results'
    )
    check_type = models.ForeignKey(
        RiskCheckType,
        on_delete=models.CASCADE,
        related_name='results'
    )
    
    # Result Status
    status = models.CharField(
        max_length=10,
        choices=CheckStatus.choices,
        default=CheckStatus.PENDING
    )
    is_blocking = models.BooleanField(
        default=False,
        help_text="Whether this result blocks trading"
    )
    
    # Scoring
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Risk score for this check (0-100, higher is riskier)"
    )
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.0'),
        help_text="Weight applied to this check"
    )
    weighted_score = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Score multiplied by weight"
    )
    
    # Check Results
    findings = models.JSONField(
        default=dict,
        blank=True,
        help_text="Detailed findings from the check"
    )
    raw_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw data returned by the check"
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if check failed"
    )
    
    # Execution Details
    execution_time_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Execution time in milliseconds"
    )
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of retries attempted"
    )
    provider_used = models.CharField(
        max_length=100,
        blank=True,
        help_text="Service/provider used for this check"
    )
    
    # Timestamps
    started_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the check was started"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the check was completed"
    )

    class Meta:
        unique_together = ['assessment', 'check_type']
        ordering = ['assessment', 'check_type__category', 'check_type__name']
        indexes = [
            models.Index(fields=['result_id']),
            models.Index(fields=['assessment', 'status']),
            models.Index(fields=['check_type', 'status']),
            models.Index(fields=['is_blocking']),
            models.Index(fields=['started_at']),
        ]

    def __str__(self) -> str:
        return f"{self.check_type.name} - {self.status}"

    def save(self, *args, **kwargs) -> None:
        """Calculate weighted score on save."""
        if self.score is not None and self.weight is not None:
            self.weighted_score = self.score * self.weight
        super().save(*args, **kwargs)


class RiskProfile(TimestampMixin):
    """
    Defines risk tolerance and configuration for strategies or users.
    
    Contains risk parameters, thresholds, and configuration that
    determines how risk assessments are interpreted and applied.
    """
    
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Risk profile name (e.g., 'Conservative', 'Aggressive')"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this risk profile"
    )
    
    # Risk Tolerance
    max_risk_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('70.0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Maximum acceptable overall risk score"
    )
    min_confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('70.0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Minimum required confidence score"
    )
    
    # Check Configuration
    enabled_checks = models.ManyToManyField(
        RiskCheckType,
        through='RiskProfileCheckConfig',
        related_name='risk_profiles',
        help_text="Risk checks enabled for this profile"
    )
    
    # Thresholds
    liquidity_threshold_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('50000.0'),
        help_text="Minimum liquidity threshold in USD"
    )
    max_holder_concentration_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('20.0'),
        help_text="Maximum acceptable top holder concentration percentage"
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
    
    # Advanced Configuration
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional risk profile configuration"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this risk profile is active"
    )
    class Meta:
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class RiskProfileCheckConfig(TimestampMixin):
    """
    Configuration for specific risk checks within a risk profile.
    
    Allows customization of check parameters, weights, and thresholds
    on a per-profile basis.
    """
    
    risk_profile = models.ForeignKey(
        RiskProfile,
        on_delete=models.CASCADE,
        related_name='check_configs'
    )
    check_type = models.ForeignKey(
        RiskCheckType,
        on_delete=models.CASCADE,
        related_name='profile_configs'
    )
    
    # Override Configuration
    is_enabled = models.BooleanField(
        default=True,
        help_text="Whether this check is enabled for this profile"
    )
    is_blocking = models.BooleanField(
        null=True,
        blank=True,
        help_text="Override blocking behavior (null = use default)"
    )
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('10.0'))],
        help_text="Override weight for this check (null = use default)"
    )
    timeout_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Override timeout for this check (null = use default)"
    )
    
    # Custom Configuration
    custom_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Check-specific configuration overrides"
    )
    class Meta:
        unique_together = ['risk_profile', 'check_type']
        ordering = ['risk_profile', 'check_type__category', 'check_type__name']

    def __str__(self) -> str:
        return f"{self.risk_profile.name} - {self.check_type.name}"

    @property
    def effective_weight(self) -> Decimal:
        """Get effective weight (custom or default)."""
        return self.weight if self.weight is not None else self.check_type.weight

    @property
    def effective_blocking(self) -> bool:
        """Get effective blocking behavior (custom or default)."""
        return self.is_blocking if self.is_blocking is not None else self.check_type.is_blocking

    @property
    def effective_timeout(self) -> int:
        """Get effective timeout (custom or default)."""
        return self.timeout_seconds if self.timeout_seconds is not None else self.check_type.timeout_seconds


class RiskEvent(TimestampMixin):
    """
    Records significant risk events and alerts.
    
    Tracks when risk thresholds are exceeded, checks fail,
    or other risk-related events occur for monitoring and analysis.
    """
    
    class EventType(models.TextChoices):
        ASSESSMENT_BLOCKED = 'ASSESSMENT_BLOCKED', 'Assessment Blocked'
        HIGH_RISK_DETECTED = 'HIGH_RISK_DETECTED', 'High Risk Detected'
        CHECK_FAILURE = 'CHECK_FAILURE', 'Check Failure'
        THRESHOLD_EXCEEDED = 'THRESHOLD_EXCEEDED', 'Threshold Exceeded'
        HONEYPOT_DETECTED = 'HONEYPOT_DETECTED', 'Honeypot Detected'
        LIQUIDITY_WARNING = 'LIQUIDITY_WARNING', 'Liquidity Warning'
        UNUSUAL_ACTIVITY = 'UNUSUAL_ACTIVITY', 'Unusual Activity'
    
    class Severity(models.TextChoices):
        INFO = 'INFO', 'Info'
        WARNING = 'WARNING', 'Warning'
        ERROR = 'ERROR', 'Error'
        
    
    # Identification
    event_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique event identifier"
    )
    event_type = models.CharField(
        max_length=25,
        choices=EventType.choices
    )
    severity = models.CharField(
        max_length=10,
        choices=Severity.choices
    )
    
    # Related Objects
    assessment = models.ForeignKey(
        RiskAssessment,
        on_delete=models.CASCADE,
        related_name='risk_events',
        null=True,
        blank=True
    )
    check_result = models.ForeignKey(
        RiskCheckResult,
        on_delete=models.CASCADE,
        related_name='risk_events',
        null=True,
        blank=True
    )
    token = models.ForeignKey(
        'trading.Token',
        on_delete=models.CASCADE,
        related_name='risk_events',
        null=True,
        blank=True
    )
    
    # Event Details
    title = models.CharField(
        max_length=200,
        help_text="Event title/summary"
    )
    description = models.TextField(
        help_text="Detailed event description"
    )
    data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional event data"
    )
    
    # Resolution
    is_resolved = models.BooleanField(
        default=False,
        help_text="Whether this event has been resolved"
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this event was resolved"
    )
    resolution_notes = models.TextField(
        blank=True,
        help_text="Notes on how this event was resolved"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event_id']),
            models.Index(fields=['event_type', 'severity']),
            models.Index(fields=['assessment']),
            models.Index(fields=['token', 'created_at']),
            models.Index(fields=['is_resolved']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} - {self.title}"