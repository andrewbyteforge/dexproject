"""
Django models for the analytics app.

This module defines AI Thought Log models and analytics tracking
for explainable decision-making in the DEX auto-trading bot.
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional
import uuid

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class DecisionContext(models.Model):
    """
    Represents the context in which a trading decision was made.
    
    Stores market conditions, strategy settings, and environmental
    factors that influenced the decision-making process.
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
        related_name='decision_contexts'
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
    
    # Market Context
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
    
    # Decision Timing
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
    
    # Additional Context
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
        return f"{self.decision_type} Context - {self.pair}"


class DecisionFeature(models.Model):
    """
    Represents individual features/signals used in decision-making.
    
    Stores feature values, weights, and transformations that
    contribute to the AI's decision-making process.
    """
    
    class FeatureCategory(models.TextChoices):
        RISK_SIGNAL = 'RISK_SIGNAL', 'Risk Signal'
        MARKET_SIGNAL = 'MARKET_SIGNAL', 'Market Signal'
        LIQUIDITY_SIGNAL = 'LIQUIDITY_SIGNAL', 'Liquidity Signal'
        TECHNICAL_SIGNAL = 'TECHNICAL_SIGNAL', 'Technical Signal'
        SOCIAL_SIGNAL = 'SOCIAL_SIGNAL', 'Social Signal'
        PORTFOLIO_SIGNAL = 'PORTFOLIO_SIGNAL', 'Portfolio Signal'
        TIMING_SIGNAL = 'TIMING_SIGNAL', 'Timing Signal'
    
    class DataType(models.TextChoices):
        NUMERIC = 'NUMERIC', 'Numeric'
        BOOLEAN = 'BOOLEAN', 'Boolean'
        CATEGORICAL = 'CATEGORICAL', 'Categorical'
        TEXT = 'TEXT', 'Text'
    
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
        help_text="Feature name (e.g., 'honeypot_score', 'liquidity_depth')"
    )
    category = models.CharField(
        max_length=20,
        choices=FeatureCategory.choices
    )
    data_type = models.CharField(
        max_length=15,
        choices=DataType.choices
    )
    
    # Feature Values
    raw_value = models.JSONField(
        help_text="Raw feature value before processing"
    )
    processed_value = models.JSONField(
        null=True,
        blank=True,
        help_text="Processed/normalized feature value"
    )
    weight = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=Decimal('1.0'),
        help_text="Weight applied to this feature"
    )
    contribution_score = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="This feature's contribution to the final decision"
    )
    
    # Feature Metadata
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Confidence in this feature value (0-100)"
    )
    source = models.CharField(
        max_length=100,
        blank=True,
        help_text="Data source for this feature"
    )
    processing_time_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Time taken to compute this feature (ms)"
    )
    
    # Thresholds and Boundaries
    threshold_values = models.JSONField(
        default=dict,
        blank=True,
        help_text="Threshold values for this feature (e.g., min, max, optimal)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['context', 'name']
        ordering = ['context', 'category', 'name']
        indexes = [
            models.Index(fields=['feature_id']),
            models.Index(fields=['context', 'category']),
            models.Index(fields=['name']),
            models.Index(fields=['category']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.category})"

    @property
    def weighted_contribution(self) -> Optional[Decimal]:
        """Calculate weighted contribution score."""
        if self.contribution_score is not None:
            return self.contribution_score * self.weight
        return None


class ThoughtLog(models.Model):
    """
    Represents the AI's thought process and reasoning for a decision.
    
    This is the core model for explainable AI, storing the complete
    reasoning chain, alternative considerations, and decision rationale.
    """
    
    class DecisionOutcome(models.TextChoices):
        EXECUTE_BUY = 'EXECUTE_BUY', 'Execute Buy'
        EXECUTE_SELL = 'EXECUTE_SELL', 'Execute Sell'
        HOLD_POSITION = 'HOLD_POSITION', 'Hold Position'
        SKIP_OPPORTUNITY = 'SKIP_OPPORTUNITY', 'Skip Opportunity'
        BLOCK_TRADE = 'BLOCK_TRADE', 'Block Trade'
        EMERGENCY_EXIT = 'EMERGENCY_EXIT', 'Emergency Exit'
    
    # Identification
    thought_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique thought log identifier"
    )
    context = models.OneToOneField(
        DecisionContext,
        on_delete=models.CASCADE,
        related_name='thought_log'
    )
    
    # Decision Summary
    decision_outcome = models.CharField(
        max_length=20,
        choices=DecisionOutcome.choices
    )
    confidence_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="AI's confidence in this decision (0-100)"
    )
    overall_score = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        help_text="Overall decision score computed by the AI"
    )
    
    # Reasoning
    primary_reasoning = models.TextField(
        help_text="Primary reasoning for the decision (1-3 sentences)"
    )
    detailed_analysis = models.TextField(
        blank=True,
        help_text="Detailed analysis and reasoning chain"
    )
    key_factors = models.JSONField(
        default=list,
        help_text="List of key factors that influenced the decision"
    )
    risk_factors = models.JSONField(
        default=list,
        help_text="Risk factors considered"
    )
    positive_signals = models.JSONField(
        default=list,
        help_text="Positive signals identified"
    )
    negative_signals = models.JSONField(
        default=list,
        help_text="Negative signals identified"
    )
    
    # Alternative Scenarios
    alternative_outcomes = models.JSONField(
        default=list,
        blank=True,
        help_text="Alternative decisions that were considered"
    )
    counterfactuals = models.JSONField(
        default=list,
        blank=True,
        help_text="What would change the decision (counterfactual reasoning)"
    )
    
    # Execution Parameters
    recommended_amount = models.DecimalField(
        max_digits=50,
        decimal_places=18,
        null=True,
        blank=True,
        help_text="Recommended trade amount"
    )
    max_slippage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Recommended maximum slippage"
    )
    max_gas_price_gwei = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Recommended maximum gas price"
    )
    priority_level = models.CharField(
        max_length=20,
        choices=[
            ('LOW', 'Low'),
            ('MEDIUM', 'Medium'),
            ('HIGH', 'High'),
            ('URGENT', 'Urgent'),
        ],
        default='MEDIUM',
        help_text="Execution priority level"
    )
    
    # Related Actions
    trade = models.ForeignKey(
        'trading.Trade',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='thought_logs',
        help_text="Trade that resulted from this decision"
    )
    
    # Learning and Feedback
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
    
    # Model Version
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
    
    # Quality Metrics
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
    
    # Financial Metrics
    execution_cost_usd = models.DecimalField(
        max_digits=15,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Total execution cost in USD"
    )
    opportunity_cost_usd = models.DecimalField(
        max_digits=15,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Estimated opportunity cost of delays"
    )
    
    # Outcome Metrics (measured after execution)
    pnl_5min_usd = models.DecimalField(
        max_digits=15,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="PnL after 5 minutes (USD)"
    )
    pnl_30min_usd = models.DecimalField(
        max_digits=15,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="PnL after 30 minutes (USD)"
    )
    pnl_24hr_usd = models.DecimalField(
        max_digits=15,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="PnL after 24 hours (USD)"
    )
    
    # Decision Quality Scores
    risk_accuracy_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="How accurate was the risk assessment (0-100)"
    )
    timing_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Quality of entry/exit timing (0-100)"
    )
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


class LearningSession(models.Model):
    """
    Represents a learning/training session for the AI model.
    
    Groups related decisions and outcomes for batch learning,
    model updates, and performance evaluation.
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
    
    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
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
        ordering = ['-started_at']
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
        HOURLY = 'HOURLY', 'Hourly'
        DAILY = 'DAILY', 'Daily'
        WEEKLY = 'WEEKLY', 'Weekly'
        MONTHLY = 'MONTHLY', 'Monthly'
    
    # Identification
    performance_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique performance record identifier"
    )
    model_version = models.CharField(
        max_length=50,
        help_text="Model version being tracked"
    )
    time_window = models.CharField(
        max_length=10,
        choices=TimeWindow.choices
    )
    period_start = models.DateTimeField(
        help_text="Start of the performance period"
    )
    period_end = models.DateTimeField(
        help_text="End of the performance period"
    )
    
    # Volume Metrics
    total_opportunities = models.PositiveIntegerField(
        default=0,
        help_text="Total opportunities evaluated"
    )
    decisions_made = models.PositiveIntegerField(
        default=0,
        help_text="Total decisions made"
    )
    trades_executed = models.PositiveIntegerField(
        default=0,
        help_text="Total trades executed"
    )
    
    # Quality Metrics
    average_confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average decision confidence"
    )
    average_quality_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average decision quality score"
    )
    risk_accuracy = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Risk assessment accuracy percentage"
    )
    
    # Performance Metrics
    total_pnl_usd = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=Decimal('0'),
        help_text="Total PnL in USD"
    )
    win_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Percentage of profitable trades"
    )
    average_return_percent = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Average return percentage per trade"
    )
    sharpe_ratio = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Risk-adjusted return (Sharpe ratio)"
    )
    max_drawdown_percent = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Maximum drawdown percentage"
    )
    
    # Timing Metrics
    average_decision_latency_ms = models.FloatField(
        null=True,
        blank=True,
        help_text="Average decision latency in milliseconds"
    )
    average_execution_latency_ms = models.FloatField(
        null=True,
        blank=True,
        help_text="Average execution latency in milliseconds"
    )
    
    # Comparison Metrics
    vs_benchmark_percent = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Performance vs benchmark percentage"
    )
    
    # Additional Metrics
    custom_metrics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional custom performance metrics"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['model_version', 'time_window', 'period_start']
        ordering = ['-period_start']
        indexes = [
            models.Index(fields=['performance_id']),
            models.Index(fields=['model_version', 'time_window']),
            models.Index(fields=['period_start', 'period_end']),
            models.Index(fields=['total_pnl_usd']),
            models.Index(fields=['win_rate_percent']),
        ]

    def __str__(self) -> str:
        return f"Performance {self.model_version} - {self.time_window} {self.period_start.date()}"


class FeatureImportance(models.Model):
    """
    Tracks the importance and contribution of different features over time.
    
    Helps understand which signals are most valuable for decision-making
    and guides feature engineering efforts.
    """
    
    # Identification
    importance_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique importance record identifier"
    )
    feature_name = models.CharField(
        max_length=100,
        help_text="Name of the feature"
    )
    feature_category = models.CharField(
        max_length=20,
        choices=DecisionFeature.FeatureCategory.choices
    )
    
    # Analysis Period
    analysis_start = models.DateTimeField(
        help_text="Start of analysis period"
    )
    analysis_end = models.DateTimeField(
        help_text="End of analysis period"
    )
    model_version = models.CharField(
        max_length=50,
        help_text="Model version for this analysis"
    )
    
    # Importance Metrics
    usage_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this feature was used"
    )
    average_weight = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=Decimal('0'),
        help_text="Average weight applied to this feature"
    )
    average_contribution = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=Decimal('0'),
        help_text="Average contribution to decisions"
    )
    importance_score = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=Decimal('0'),
        help_text="Overall importance score"
    )
    
    # Quality Metrics
    predictive_power = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Predictive power score (0-100)"
    )
    stability_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Feature stability score (0-100)"
    )
    correlation_with_outcome = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Correlation with successful outcomes (-1 to 1)"
    )
    
    # Performance Impact
    decisions_with_feature = models.PositiveIntegerField(
        default=0,
        help_text="Number of decisions that used this feature"
    )
    success_rate_with_feature = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Success rate when this feature was used"
    )
    avg_pnl_with_feature = models.DecimalField(
        max_digits=15,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Average PnL when this feature was used"
    )
    
    # Trend Analysis
    trend_direction = models.CharField(
        max_length=20,
        choices=[
            ('INCREASING', 'Increasing'),
            ('DECREASING', 'Decreasing'),
            ('STABLE', 'Stable'),
            ('VOLATILE', 'Volatile'),
        ],
        null=True,
        blank=True,
        help_text="Trend in feature importance"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['feature_name', 'model_version', 'analysis_start']
        ordering = ['-importance_score', 'feature_name']
        indexes = [
            models.Index(fields=['importance_id']),
            models.Index(fields=['feature_name', 'feature_category']),
            models.Index(fields=['model_version']),
            models.Index(fields=['importance_score']),
            models.Index(fields=['analysis_start', 'analysis_end']),
        ]

    def __str__(self) -> str:
        return f"{self.feature_name} - Importance: {self.importance_score}"