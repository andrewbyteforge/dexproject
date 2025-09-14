"""
Django models for the analytics app.

This module defines AI decision tracking, learning sessions, and performance
metrics for the DEX auto-trading bot's intelligent decision-making system.
"""

from decimal import Decimal
from typing import Dict, Any, Optional
import uuid

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

# Import mixins but don't use TimestampMixin for LearningSession
from shared.models.mixins import UUIDMixin


class DecisionContext(models.Model):
    """
    Captures the complete context surrounding a trading decision.
    
    Stores market conditions, portfolio state, timing information,
    and environmental factors at the moment a decision was made.
    """
    
    class DecisionType(models.TextChoices):
        BUY = 'BUY', 'Buy Decision'
        SELL = 'SELL', 'Sell Decision'
        HOLD = 'HOLD', 'Hold Decision'
        SKIP = 'SKIP', 'Skip Decision'
        EMERGENCY_EXIT = 'EMERGENCY_EXIT', 'Emergency Exit'
    
    # Identification
    context_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique context identifier"
    )
    decision_type = models.CharField(
        max_length=15,
        choices=DecisionType.choices
    )
    
    # Related Objects
    pair = models.ForeignKey(
        'trading.TradingPair',
        on_delete=models.CASCADE,
        related_name='decision_contexts'
    )
    token = models.ForeignKey(
        'trading.Token',
        on_delete=models.CASCADE,
        related_name='decision_contexts',
        help_text="Primary token being analyzed"
    )
    strategy = models.ForeignKey(
        'trading.Strategy',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='decision_contexts'
    )
    risk_assessment = models.ForeignKey(
        'risk.RiskAssessment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='decision_contexts'
    )
    
    # Market Conditions at Decision Time
    eth_price_usd = models.DecimalField(
        max_digits=15,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="ETH price in USD at decision time"
    )
    gas_price_gwei = models.DecimalField(
        max_digits=15,
        decimal_places=9,
        null=True,
        blank=True,
        help_text="Gas price in Gwei at decision time"
    )
    token_price_usd = models.DecimalField(
        max_digits=20,
        decimal_places=12,
        null=True,
        blank=True,
        help_text="Token price in USD at decision time"
    )
    pair_liquidity_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Pair liquidity in USD at decision time"
    )
    
    # Timing Metrics
    discovery_latency_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Time from pair discovery to decision start (ms)"
    )
    analysis_duration_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Time spent on analysis (ms)"
    )
    execution_latency_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Time from decision to execution (ms)"
    )
    
    # Contextual Data
    market_conditions = models.JSONField(
        default=dict,
        blank=True,
        help_text="Market conditions at decision time"
    )
    portfolio_state = models.JSONField(
        default=dict,
        blank=True,
        help_text="Portfolio state at decision time"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['context_id']),
            models.Index(fields=['decision_type']),
            models.Index(fields=['pair', 'created_at']),
            models.Index(fields=['token', 'created_at']),
            models.Index(fields=['strategy']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self) -> str:
        return f"Decision Context {self.context_id} - {self.decision_type}"


class DecisionFeature(models.Model):
    """
    Stores individual features extracted for a trading decision.
    
    Represents structured data points that feed into the AI decision process,
    enabling feature importance analysis and model interpretability.
    """
    
    class FeatureCategory(models.TextChoices):
        TECHNICAL = 'TECHNICAL', 'Technical Indicators'
        FUNDAMENTAL = 'FUNDAMENTAL', 'Fundamental Analysis'
        SENTIMENT = 'SENTIMENT', 'Market Sentiment'
        RISK = 'RISK', 'Risk Metrics'
        LIQUIDITY = 'LIQUIDITY', 'Liquidity Analysis'
        TIMING = 'TIMING', 'Timing Factors'
        PORTFOLIO = 'PORTFOLIO', 'Portfolio Context'
        MARKET = 'MARKET', 'Market Conditions'
    
    # Identification
    feature_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique feature identifier"
    )
    context = models.ForeignKey(
        DecisionContext,
        on_delete=models.CASCADE,
        related_name='features'
    )
    
    # Feature Definition
    name = models.CharField(
        max_length=100,
        help_text="Feature name (e.g., 'rsi_14', 'holder_concentration')"
    )
    category = models.CharField(
        max_length=15,
        choices=FeatureCategory.choices
    )
    
    # Feature Values
    value_numeric = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Numeric feature value"
    )
    value_text = models.TextField(
        blank=True,
        help_text="Text/categorical feature value"
    )
    value_bool = models.BooleanField(
        null=True,
        blank=True,
        help_text="Boolean feature value"
    )
    
    # Metadata
    importance_score = models.DecimalField(
        max_digits=8,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Feature importance score (0-1)"
    )
    confidence_level = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Confidence in this feature value (0-100)"
    )
    raw_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw data used to compute this feature"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['context', '-importance_score', 'category', 'name']
        unique_together = [['context', 'name']]
        indexes = [
            models.Index(fields=['feature_id']),
            models.Index(fields=['context', 'category']),
            models.Index(fields=['name']),
            models.Index(fields=['category']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self) -> str:
        return f"Feature: {self.name} ({self.category})"


class ThoughtLog(models.Model):
    """
    Records the AI's reasoning process for each trading decision.
    
    Captures the step-by-step thought process, confidence levels,
    and decision rationale for transparency and learning.
    """
    
    class DecisionOutcome(models.TextChoices):
        BUY = 'BUY', 'Buy'
        SELL = 'SELL', 'Sell'
        HOLD = 'HOLD', 'Hold'
        SKIP = 'SKIP', 'Skip'
        EMERGENCY_EXIT = 'EMERGENCY_EXIT', 'Emergency Exit'
    
    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        URGENT = 'URGENT', 'Urgent'
    
    # Identification
    thought_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique thought log identifier"
    )
    
    # Decision Context
    context = models.OneToOneField(
        DecisionContext,
        on_delete=models.CASCADE,
        related_name='thought_log'
    )
    
    # Decision Output
    decision_outcome = models.CharField(
        max_length=15,
        choices=DecisionOutcome.choices
    )
    confidence_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Confidence in this decision (0-100)"
    )
    
    # Reasoning Process
    reasoning_steps = models.JSONField(
        help_text="Step-by-step reasoning process as structured data"
    )
    key_factors = models.JSONField(
        default=list,
        blank=True,
        help_text="Key factors that influenced the decision"
    )
    risk_concerns = models.JSONField(
        default=list,
        blank=True,
        help_text="Risk concerns identified during analysis"
    )
    alternative_scenarios = models.JSONField(
        default=list,
        blank=True,
        help_text="Alternative scenarios considered"
    )
    
    # Decision Metadata
    recommended_position_size_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Recommended position size in USD"
    )
    recommended_stop_loss_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Recommended stop loss percentage"
    )
    recommended_take_profit_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Recommended take profit percentage"
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        help_text="Execution priority level"
    )
    
    # Execution Link
    trade = models.ForeignKey(
        'trading.Trade',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='thought_logs',
        help_text="Trade that resulted from this decision"
    )
    
    # Feedback and Evaluation
    feedback_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('-100')), MaxValueValidator(Decimal('100'))],
        help_text="Feedback score on decision quality (-100 to 100)"
    )
    outcome_evaluation = models.TextField(
        blank=True,
        help_text="Post-execution evaluation of the decision"
    )
    
    # Model Metadata
    model_version = models.CharField(
        max_length=50,
        blank=True,
        help_text="Version of the decision model used"
    )
    feature_version = models.CharField(
        max_length=50,
        blank=True,
        help_text="Version of the feature engineering pipeline"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['thought_id']),
            models.Index(fields=['decision_outcome']),
            models.Index(fields=['context']),
            models.Index(fields=['trade']),
            models.Index(fields=['confidence_percent']),
            models.Index(fields=['created_at']),
            models.Index(fields=['model_version']),
        ]

    def __str__(self) -> str:
        return f"Thought Log {self.thought_id} - {self.decision_outcome}"

    @property
    def execution_time_total_ms(self) -> Optional[int]:
        """Calculate total execution time from context."""
        if self.context.analysis_duration_ms:
            return self.context.analysis_duration_ms
        return None


class DecisionMetrics(models.Model):
    """
    Stores quantitative metrics and performance data for decisions.
    
    Tracks execution quality, timing, costs, and outcomes for
    performance analysis and model improvement.
    """
    
    # Identification
    metrics_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique metrics identifier"
    )
    thought_log = models.OneToOneField(
        ThoughtLog,
        on_delete=models.CASCADE,
        related_name='metrics'
    )
    
    # Execution Metrics
    decision_latency_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Time from opportunity to decision (ms)"
    )
    execution_latency_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Time from decision to execution (ms)"
    )
    total_latency_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total time from opportunity to execution (ms)"
    )
    
    # Trading Metrics
    slippage_actual_percent = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Actual slippage percentage"
    )
    slippage_vs_expected_percent = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Difference between actual and expected slippage"
    )
    gas_efficiency_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Gas efficiency score (0-100)"
    )
    
    # Financial Performance
    pnl_1hr_usd = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="PnL after 1 hour (USD)"
    )
    pnl_24hr_usd = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="PnL after 24 hours (USD)"
    )
    pnl_7d_usd = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="PnL after 7 days (USD)"
    )
    max_drawdown_percent = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Maximum drawdown percentage"
    )
    
    # Quality Scores
    overall_quality_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Overall decision quality score (0-100)"
    )
    
    # Comparison Metrics
    vs_random_performance = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Performance vs random decision baseline"
    )
    vs_market_performance = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Performance vs market/index baseline"
    )
    
    # Additional Metrics
    custom_metrics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional custom metrics"
    )
    
    # Evaluation Timestamps
    last_evaluated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time metrics were updated"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['metrics_id']),
            models.Index(fields=['thought_log']),
            models.Index(fields=['overall_quality_score']),
            models.Index(fields=['pnl_24hr_usd']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self) -> str:
        return f"Metrics for {self.thought_log.thought_id}"


class LearningSession(models.Model):  # Note: NOT inheriting from TimestampMixin
    """
    Represents a learning/training session for the AI model.
    
    Groups related decisions and outcomes for batch learning,
    model updates, and performance evaluation.
    
    Uses domain-specific timestamp fields instead of generic ones.
    """
    
    class SessionType(models.TextChoices):
        LIVE_TRADING = 'LIVE_TRADING', 'Live Trading'
        PAPER_TRADING = 'PAPER_TRADING', 'Paper Trading'
        BACKTEST = 'BACKTEST', 'Backtest'
        MANUAL_REVIEW = 'MANUAL_REVIEW', 'Manual Review'
    
    class SessionStatus(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        FAILED = 'FAILED', 'Failed'
    
    # Identification
    session_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique session identifier"
    )
    name = models.CharField(
        max_length=200,
        help_text="Session name or description"
    )
    session_type = models.CharField(
        max_length=15,
        choices=SessionType.choices
    )
    status = models.CharField(
        max_length=10,
        choices=SessionStatus.choices,
        default=SessionStatus.ACTIVE
    )
    
    # Session Configuration
    strategy = models.ForeignKey(
        'trading.Strategy',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='learning_sessions'
    )
    model_version = models.CharField(
        max_length=50,
        blank=True,
        help_text="Model version used in this session"
    )
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Session configuration parameters"
    )
    
    # Session Metrics
    total_decisions = models.PositiveIntegerField(
        default=0,
        help_text="Total number of decisions in this session"
    )
    successful_decisions = models.PositiveIntegerField(
        default=0,
        help_text="Number of successful decisions"
    )
    average_quality_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average decision quality score"
    )
    total_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=Decimal('0'),
        help_text="Total PnL for this session (USD)"
    )
    
    # Learning Outcomes
    lessons_learned = models.JSONField(
        default=list,
        blank=True,
        help_text="Key lessons learned from this session"
    )
    model_updates = models.JSONField(
        default=list,
        blank=True,
        help_text="Model updates made based on this session"
    )
    
    # Domain-specific timestamps (not generic created_at/updated_at)
    started_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the learning session started"
    )
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the session ended"
    )
    
    # Related Decisions
    thought_logs = models.ManyToManyField(
        ThoughtLog,
        related_name='learning_sessions',
        blank=True,
        help_text="Thought logs included in this session"
    )

    class Meta:
        ordering = ['-started_at']  # Order by started_at, not created_at
        indexes = [
            models.Index(fields=['session_id']),
            models.Index(fields=['session_type', 'status']),
            models.Index(fields=['strategy']),
            models.Index(fields=['started_at']),
            models.Index(fields=['average_quality_score']),
        ]

    def __str__(self) -> str:
        return f"Learning Session: {self.name}"

    @property
    def duration_hours(self) -> Optional[float]:
        """Calculate session duration in hours."""
        if self.ended_at:
            delta = self.ended_at - self.started_at
            return delta.total_seconds() / 3600
        return None

    @property
    def success_rate(self) -> Optional[Decimal]:
        """Calculate success rate percentage."""
        if self.total_decisions > 0:
            return (Decimal(self.successful_decisions) / Decimal(self.total_decisions)) * 100
        return None


class ModelPerformance(models.Model):
    """
    Tracks model performance metrics over time.
    
    Stores aggregated performance data for different time windows
    and model versions for monitoring and comparison.
    """
    
    class TimeWindow(models.TextChoices):
        HOUR = 'HOUR', '1 Hour'
        DAY = 'DAY', '1 Day'
        WEEK = 'WEEK', '1 Week'
        MONTH = 'MONTH', '1 Month'
        QUARTER = 'QUARTER', '1 Quarter'
        YEAR = 'YEAR', '1 Year'
    
    # Identification
    performance_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique performance identifier"
    )
    model_version = models.CharField(
        max_length=50,
        help_text="Model version being tracked"
    )
    time_window = models.CharField(
        max_length=10,
        choices=TimeWindow.choices
    )
    
    # Time Period
    period_start = models.DateTimeField(
        help_text="Start of the performance measurement period"
    )
    period_end = models.DateTimeField(
        help_text="End of the performance measurement period"
    )
    
    # Performance Metrics
    total_decisions = models.PositiveIntegerField(
        default=0,
        help_text="Total decisions made in this period"
    )
    successful_decisions = models.PositiveIntegerField(
        default=0,
        help_text="Number of successful decisions"
    )
    win_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Win rate percentage"
    )
    
    # Financial Performance
    total_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=Decimal('0'),
        help_text="Total PnL for this period (USD)"
    )
    average_pnl_per_decision_usd = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Average PnL per decision (USD)"
    )
    max_drawdown_percent = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Maximum drawdown percentage"
    )
    sharpe_ratio = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Sharpe ratio"
    )
    
    # Quality Metrics
    average_quality_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average decision quality score"
    )
    average_confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average confidence level"
    )
    
    # Timing Metrics
    average_decision_latency_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Average decision latency (ms)"
    )
    average_execution_latency_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Average execution latency (ms)"
    )
    
    # Additional Metrics
    custom_metrics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional performance metrics"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-period_start']
        unique_together = [['model_version', 'time_window', 'period_start']]
        indexes = [
            models.Index(fields=['performance_id']),
            models.Index(fields=['model_version', 'time_window']),
            models.Index(fields=['period_start', 'period_end']),
            models.Index(fields=['win_rate_percent']),
            models.Index(fields=['total_pnl_usd']),
            models.Index(fields=['sharpe_ratio']),
        ]

    def __str__(self) -> str:
        return f"Performance: {self.model_version} ({self.time_window}) - {self.period_start.date()}"

    @property
    def duration_hours(self) -> float:
        """Calculate period duration in hours."""
        delta = self.period_end - self.period_start
        return delta.total_seconds() / 3600

    @property
    def success_rate(self) -> Optional[Decimal]:
        """Calculate success rate percentage."""
        if self.total_decisions > 0:
            return (Decimal(self.successful_decisions) / Decimal(self.total_decisions)) * 100
        return None