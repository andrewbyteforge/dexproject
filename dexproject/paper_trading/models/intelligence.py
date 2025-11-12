"""
Paper Trading Intelligence Models

Models for AI decision tracking and strategy configuration with Auto Pilot support.
Handles all intelligence-related functionality including thought logs and
adaptive parameter configuration.

File: dexproject/paper_trading/models/intelligence.py
"""

from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
import uuid
import logging
from typing import Optional
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

from .base import PaperTradingAccount, PaperTrade

logger = logging.getLogger(__name__)


# =============================================================================
# INTELLIGENCE & STRATEGY MODELS
# =============================================================================

class PaperAIThoughtLog(models.Model):
    """
    Records the AI's reasoning process for each paper trading decision.
    
    Provides complete transparency into the bot's decision-making process by logging
    all analysis, risk assessments, and reasoning for each trade decision.
    This helps users understand why the bot made specific choices.
    
    UPDATED: Fixed to match database migration schema exactly.
    Uses constants from paper_trading.constants for field name consistency.
    
    Attributes:
        thought_id: Unique identifier (UUID)
        account: Associated trading account
        paper_trade: Associated trade (if executed)
        decision_type: Type of decision (BUY/SELL/HOLD/SKIP/STOP_LOSS/TAKE_PROFIT)
        token_address: Token being analyzed
        token_symbol: Token symbol
        confidence_level: Confidence category (VERY_HIGH, HIGH, MEDIUM, LOW, VERY_LOW)
        confidence_percent: Exact confidence percentage (0-100)
        risk_score: Risk assessment score (0-100, higher is riskier)
        opportunity_score: Opportunity assessment score (0-100)
        primary_reasoning: Primary reasoning for the decision (1-3 sentences)
        key_factors: Important decision factors (JSON list)
        positive_signals: Bullish signals detected (JSON list)
        negative_signals: Bearish signals detected (JSON list)
        market_data: Market data snapshot (JSON dict)
        strategy_name: Strategy used
        lane_used: Fast Lane or Smart Lane
        created_at: When the thought was generated
        analysis_time_ms: Time taken for analysis in milliseconds
    """
    
    class DecisionType(models.TextChoices):
        """Types of trading decisions."""
        BUY = 'BUY', 'Buy'
        SELL = 'SELL', 'Sell'
        HOLD = 'HOLD', 'Hold'
        SKIP = 'SKIP', 'Skip'
        STOP_LOSS = 'STOP_LOSS', 'Stop Loss'
        TAKE_PROFIT = 'TAKE_PROFIT', 'Take Profit'
    
    class ConfidenceLevel(models.TextChoices):
        """Confidence level categories."""
        VERY_HIGH = 'VERY_HIGH', 'Very High (90-100%)'
        HIGH = 'HIGH', 'High (70-90%)'
        MEDIUM = 'MEDIUM', 'Medium (50-70%)'
        LOW = 'LOW', 'Low (30-50%)'
        VERY_LOW = 'VERY_LOW', 'Very Low (<30%)'
    
    # =========================================================================
    # IDENTITY FIELDS
    # =========================================================================
    
    thought_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique thought identifier"
    )
    
    account = models.ForeignKey(
        PaperTradingAccount,
        on_delete=models.CASCADE,
        related_name='thought_logs',
        help_text="Paper trading account"
    )
    
    paper_trade = models.ForeignKey(
        PaperTrade,
        on_delete=models.CASCADE,
        related_name='thought_logs',
        null=True,
        blank=True,
        help_text="Associated paper trade (if executed)"
    )
    
    # =========================================================================
    # DECISION FIELDS
    # =========================================================================
    
    decision_type = models.CharField(
        max_length=20,
        choices=DecisionType.choices,
        help_text="Type of decision made"
    )
    
    token_address = models.CharField(
        max_length=42,
        help_text="Token being analyzed"
    )
    
    token_symbol = models.CharField(
        max_length=20,
        help_text="Token symbol"
    )
    
    # =========================================================================
    # CONFIDENCE AND SCORING FIELDS (FIXED TO MATCH MIGRATION)
    # =========================================================================
    
    confidence_level = models.CharField(
        max_length=20,
        choices=ConfidenceLevel.choices,
        help_text="Confidence level category"
    )
    
    confidence_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Exact confidence percentage (0-100)"
    )
    
    risk_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Risk assessment score (0-100, higher is riskier)"
    )
    
    opportunity_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Opportunity assessment score (0-100)"
    )
    
    # =========================================================================
    # REASONING FIELDS
    # =========================================================================
    
    primary_reasoning = models.TextField(
        help_text="Primary reasoning for the decision (1-3 sentences)"
    )
    
    key_factors = models.JSONField(
        default=list,
        help_text="Key factors that influenced the decision"
    )
    
    positive_signals = models.JSONField(
        default=list,
        help_text="Positive signals identified"
    )
    
    negative_signals = models.JSONField(
        default=list,
        help_text="Negative signals/risks identified"
    )
    
    # =========================================================================
    # CONTEXT FIELDS
    # =========================================================================
    
    market_data = models.JSONField(
        default=dict,
        help_text="Market data snapshot at decision time"
    )
    
    strategy_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Strategy that generated this decision"
    )
    
    lane_used = models.CharField(
        max_length=20,
        choices=[('FAST', 'Fast Lane'), ('SMART', 'Smart Lane')],
        default='FAST',
        help_text="Which lane was used for analysis"
    )
    
    # =========================================================================
    # TIMING FIELDS
    # =========================================================================
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the thought was generated"
    )
    
    analysis_time_ms = models.IntegerField(
        default=0,
        help_text="Time taken for analysis in milliseconds"
    )
    
    class Meta:
        """Meta configuration."""
        db_table = 'paper_ai_thought_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', 'created_at']),
            models.Index(fields=['decision_type']),
            models.Index(fields=['confidence_level']),
            models.Index(fields=['token_address']),
        ]
        verbose_name = 'AI Thought Log'
        verbose_name_plural = 'AI Thought Logs'
    
    def __str__(self) -> str:
        """String representation."""
        return (
            f"Thought: {self.decision_type} {self.token_symbol} "
            f"({self.confidence_percent}% confidence)"
        )


class PaperStrategyConfiguration(models.Model):
    """
    Configuration for paper trading strategies with Auto Pilot support.
    
    Comprehensive strategy configuration that controls all aspects of bot
    behavior including risk management, trading parameters, lane selection,
    and Auto Pilot adaptive learning.
    
    ENHANCED: Includes complete Auto Pilot system for intelligent parameter
    adaptation based on performance metrics and market conditions.
    
    Key Features:
    - Trading mode selection (Conservative/Moderate/Aggressive/Custom)
    - Lane preferences (Fast Lane / Smart Lane)
    - Risk management parameters
    - Token filters and custom parameters
    - Auto Pilot adaptive learning configuration
    - Parameter boundaries for safe adaptation
    - Learning rate and aggressiveness controls
    - Safety limits and cooldown periods
    
    Attributes:
        config_id: Unique identifier (UUID)
        account: Associated trading account
        name: Configuration name
        is_active: Whether config is currently active
        trading_mode: Conservative/Moderate/Aggressive/Custom
        use_fast_lane: Enable Fast Lane trading
        use_smart_lane: Enable Smart Lane trading
        fast_lane_threshold_usd: Max trade size for Fast Lane
        max_position_size_percent: Max position as % of portfolio
        stop_loss_percent: Default stop loss percentage
        take_profit_percent: Default take profit percentage
        max_daily_trades: Maximum trades per day
        max_concurrent_positions: Maximum open positions
        min_liquidity_usd: Minimum liquidity required
        max_slippage_percent: Maximum allowed slippage
        confidence_threshold: Minimum confidence for trades
        allowed_tokens: Whitelist of token addresses
        blocked_tokens: Blacklist of token addresses
        custom_parameters: Additional custom settings
        autopilot_enabled: Enable Auto Pilot
        autopilot_started_at: When Auto Pilot was activated
        autopilot_adjustments_count: Total adjustments made
        autopilot_last_adjustment: Last adjustment timestamp
        min_position_size_percent: Min position Auto Pilot can set
        max_position_size_percent_limit: Max position Auto Pilot can set
        min_confidence_threshold: Min confidence Auto Pilot can set
        max_confidence_threshold_limit: Max confidence Auto Pilot can set
        learning_rate: How quickly parameters adapt
        adaptation_aggressiveness: Conservative/Moderate/Aggressive learning
        performance_window_trades: # trades to analyze
        adjustment_cooldown_minutes: Min time between adjustments
        max_daily_adjustments: Max adjustments per day
        auto_disable_after_failures: Disable after N bad adjustments
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    
    class TradingMode(models.TextChoices):
        """Trading mode options."""
        CONSERVATIVE = 'CONSERVATIVE', 'Conservative'
        MODERATE = 'MODERATE', 'Moderate'
        AGGRESSIVE = 'AGGRESSIVE', 'Aggressive'
        CUSTOM = 'CUSTOM', 'Custom'
    
    class AdaptationAggressiveness(models.TextChoices):
        """How aggressively Auto Pilot adjusts parameters."""
        CONSERVATIVE = 'CONSERVATIVE', 'Conservative - Small adjustments'
        MODERATE = 'MODERATE', 'Moderate - Balanced learning'
        AGGRESSIVE = 'AGGRESSIVE', 'Aggressive - Fast adaptation'
    
    # Identity
    config_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique configuration identifier"
    )
    
    account = models.ForeignKey(
        PaperTradingAccount,
        on_delete=models.CASCADE,
        related_name='strategy_configs',
        help_text="Associated trading account"
    )
    
    name = models.CharField(
        max_length=100,
        help_text="Configuration name"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this configuration is active"
    )

    enable_dca = models.BooleanField(
        default=False,
        help_text='Enable Dollar Cost Averaging (DCA) strategy - spreads buys over time'
    )
    
    enable_grid = models.BooleanField(
        default=False,
        help_text='Enable Grid Trading strategy - places multiple orders at different price levels'
    )
    
    enable_twap = models.BooleanField(
        default=False,
        help_text='Enable TWAP (Time-Weighted Average Price) strategy'
    )
    
    enable_vwap = models.BooleanField(
        default=False,
        help_text='Enable VWAP (Volume-Weighted Average Price) strategy'
    )
    
    dca_num_intervals = models.IntegerField(
        default=5,
        help_text='Number of DCA buy intervals (2-20)',
        validators=[MinValueValidator(2), MaxValueValidator(20)]
    )
    
    dca_interval_hours = models.IntegerField(
        default=2,
        help_text='Hours between each DCA buy (1-168 hours = 1 week max)',
        validators=[MinValueValidator(1), MaxValueValidator(168)]
    )
    
    grid_num_levels = models.IntegerField(
        default=7,
        help_text='Number of grid price levels (3-20)',
        validators=[MinValueValidator(3), MaxValueValidator(20)]
    )
    
    grid_profit_target_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('2.0'),
        help_text='Target profit per grid level in percent (0.1-10.0%)',
        validators=[
            MinValueValidator(Decimal('0.1')),
            MaxValueValidator(Decimal('10.0'))
        ]
    )
    
    # ==========================================================================
    # BASIC TRADING SETTINGS
    # ==========================================================================
    
    trading_mode = models.CharField(
        max_length=20,
        choices=TradingMode.choices,
        default=TradingMode.MODERATE,
        help_text="Trading mode"
    )

    intel_level = models.IntegerField(
        default=5,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(10)
        ],
        help_text='Intelligence level (1-10) controlling bot decision-making behavior'
    )

    
    # Lane preferences
    use_fast_lane = models.BooleanField(
        default=True,
        help_text="Enable Fast Lane trading"
    )
    
    use_smart_lane = models.BooleanField(
        default=False,
        help_text="Enable Smart Lane trading"
    )
    
    fast_lane_threshold_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('100'),
        help_text="Max trade size for Fast Lane"
    )
    
    # ==========================================================================
    # RISK MANAGEMENT
    # ==========================================================================
    
    max_position_size_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.0'),
        validators=[
            MinValueValidator(Decimal('0.1')),
            MaxValueValidator(Decimal('100'))
        ],
        help_text="Max position size as % of portfolio"
    )


    max_trade_size_usd = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('1000.00'),
        validators=[MinValueValidator(Decimal('10')), MaxValueValidator(Decimal('100000'))],
        help_text='Maximum trade size in USD (absolute limit)'
    )

    
    stop_loss_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.0'),
        validators=[
            MinValueValidator(Decimal('0.1')),
            MaxValueValidator(Decimal('50'))
        ],
        help_text="Default stop loss percentage"
    )
    
    take_profit_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('10.0'),
        validators=[
            MinValueValidator(Decimal('0.1')),
            MaxValueValidator(Decimal('1000'))
        ],
        help_text="Default take profit percentage"
    )

    max_hold_hours = models.IntegerField(
        default=72,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(720)  # 30 days max
        ],
        help_text='Maximum hours to hold a position before auto-close (1-720 hours)'
    )
    
    max_daily_trades = models.IntegerField(
        default=20,
        validators=[MinValueValidator(1), MaxValueValidator(1000)],
        help_text="Maximum trades per day"
    )
    
    max_concurrent_positions = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Maximum concurrent open positions"
    )
    
    # ==========================================================================
    # TRADING PARAMETERS
    # ==========================================================================
    
    min_liquidity_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('10000'),
        help_text="Minimum liquidity required"
    )
    
    max_slippage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.0'),
        validators=[
            MinValueValidator(Decimal('0.01')),
            MaxValueValidator(Decimal('10'))
        ],
        help_text="Maximum allowed slippage"
    )
    
    confidence_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('60'),
        validators=[
            MinValueValidator(Decimal('0')),
            MaxValueValidator(Decimal('100'))
        ],
        help_text="Minimum confidence for trades"
    )
    
    # Token filters
    allowed_tokens = models.JSONField(
        default=list,
        blank=True,
        help_text="List of allowed token addresses"
    )
    
    blocked_tokens = models.JSONField(
        default=list,
        blank=True,
        help_text="List of blocked token addresses"
    )
    
    custom_parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Custom strategy parameters"
    )
    
    # ==========================================================================
    # AUTO PILOT CONFIGURATION
    # ==========================================================================
    
    autopilot_enabled = models.BooleanField(
        default=False,
        help_text="Enable Auto Pilot for intelligent parameter adaptation"
    )
    
    autopilot_started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When Auto Pilot was first activated"
    )
    
    autopilot_adjustments_count = models.IntegerField(
        default=0,
        help_text="Total number of adjustments made by Auto Pilot"
    )
    
    autopilot_last_adjustment = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of most recent Auto Pilot adjustment"
    )
    
    # Parameter boundaries (what autopilot can adjust within)
    min_position_size_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.0'),
        validators=[
            MinValueValidator(Decimal('0.1')),
            MaxValueValidator(Decimal('25'))
        ],
        help_text="Minimum position size Auto Pilot can set"
    )
    
    max_position_size_percent_limit = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('20.0'),
        validators=[
            MinValueValidator(Decimal('1')),
            MaxValueValidator(Decimal('50'))
        ],
        help_text="Maximum position size Auto Pilot can set"
    )




    
    min_confidence_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('40.0'),
        validators=[
            MinValueValidator(Decimal('10')),
            MaxValueValidator(Decimal('95'))
        ],
        help_text="Minimum confidence threshold Auto Pilot can set"
    )
    
    max_confidence_threshold_limit = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('95.0'),
        validators=[
            MinValueValidator(Decimal('50')),
            MaxValueValidator(Decimal('100'))
        ],
        help_text="Maximum confidence threshold Auto Pilot can set"
    )
    
    # Learning parameters
    learning_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal('0.1000'),
        validators=[
            MinValueValidator(Decimal('0.0001')),
            MaxValueValidator(Decimal('1.0'))
        ],
        help_text="Learning rate for parameter adjustments (0.0001 - 1.0)"
    )
    
    adaptation_aggressiveness = models.CharField(
        max_length=20,
        choices=AdaptationAggressiveness.choices,
        default=AdaptationAggressiveness.MODERATE,
        help_text="How aggressively Auto Pilot adapts parameters"
    )
    
    performance_window_trades = models.IntegerField(
        default=20,
        validators=[MinValueValidator(5), MaxValueValidator(100)],
        help_text="Number of recent trades to consider for performance analysis"
    )
    
    adjustment_cooldown_minutes = models.IntegerField(
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(1440)],
        help_text="Minimum minutes between Auto Pilot adjustments"
    )
    
    # Safety limits
    max_daily_adjustments = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Maximum parameter adjustments per day"
    )
    
    auto_disable_after_failures = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="Disable Auto Pilot after N consecutive bad adjustments"
    )
    
    # ==========================================================================
    # TIMESTAMPS
    # ==========================================================================
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Configuration creation timestamp"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last update timestamp"
    )
    
    class Meta:
        """Meta configuration."""
        db_table = 'paper_strategy_configs'
        ordering = ['-updated_at']
        unique_together = [['account', 'name']]
        indexes = [
            models.Index(fields=['account', 'is_active']),
            models.Index(fields=['autopilot_enabled']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'Strategy Configuration'
        verbose_name_plural = 'Strategy Configurations'
    
    def __str__(self) -> str:
        """String representation."""
        autopilot_status = "🤖 AUTO" if self.autopilot_enabled else "👤 MANUAL"
        return f"{self.name} ({self.trading_mode}) [{autopilot_status}]"
    
    def can_adjust_now(self) -> bool:
        """
        Check if Auto Pilot can make an adjustment now.
        
        Checks:
        - Auto Pilot is enabled
        - Cooldown period has passed
        - Daily adjustment limit not reached
        
        Returns:
            True if adjustment is allowed, False otherwise
        """
        try:
            if not self.autopilot_enabled:
                logger.debug(f"Config {self.config_id}: Auto Pilot not enabled")
                return False
            
            # Check cooldown
            if self.autopilot_last_adjustment:
                time_since_last = timezone.now() - self.autopilot_last_adjustment
                cooldown_seconds = self.adjustment_cooldown_minutes * 60
                
                if time_since_last.total_seconds() < cooldown_seconds:
                    logger.debug(
                        f"Config {self.config_id}: Still in cooldown "
                        f"({time_since_last.total_seconds():.0f}s / {cooldown_seconds}s)"
                    )
                    return False
            
            # Check daily limit
            # Import here to avoid circular dependency
            from .autopilot import AutoPilotLog
            
            today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_adjustments = AutoPilotLog.objects.filter(
                strategy_config=self,
                timestamp__gte=today_start
            ).count()
            
            if today_adjustments >= self.max_daily_adjustments:
                logger.warning(
                    f"Config {self.config_id}: Daily adjustment limit reached "
                    f"({today_adjustments}/{self.max_daily_adjustments})"
                )
                return False
            
            logger.debug(f"Config {self.config_id}: Can adjust now")
            return True
        
        except Exception as e:
            logger.error(
                f"Error checking if config {self.config_id} can adjust: {e}",
                exc_info=True
            )
            return False
    
    def record_adjustment(self) -> None:
        """
        Record that an adjustment was made.
        
        Updates adjustment count and timestamp.
        """
        try:
            self.autopilot_adjustments_count += 1
            self.autopilot_last_adjustment = timezone.now()
            self.save(update_fields=[
                'autopilot_adjustments_count',
                'autopilot_last_adjustment'
            ])
            logger.info(
                f"Recorded Auto Pilot adjustment for config {self.config_id} "
                f"(total: {self.autopilot_adjustments_count})"
            )
        except Exception as e:
            logger.error(
                f"Error recording Auto Pilot adjustment for config {self.config_id}: {e}",
                exc_info=True
            )