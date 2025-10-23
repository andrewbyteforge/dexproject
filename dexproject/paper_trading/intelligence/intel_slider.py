"""
Intel Slider System for Paper Trading Bot - REAL DATA INTEGRATION

UPDATED: Now integrates with real price feeds and market data for accurate
trading decisions based on live market conditions.

Implements the 1-10 intelligence level slider that controls all bot behaviors,
integrating with the existing paper trading infrastructure.

New Features:
- Real token price fetching from Alchemy/CoinGecko
- Price-aware decision making (buy low, sell high)
- Position sizing with real USD/token conversions
- Historical price tracking for performance analysis
- Enhanced risk assessment with price volatility
- Market context tracking for trend analysis (NEW)
- Level 10 AI learning data collection (NEW)

File: dexproject/paper_trading/intelligence/intel_slider.py
"""

import logging
import uuid
import asyncio
from decimal import Decimal
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass

# Django imports for timezone-aware datetimes
from django.utils import timezone

# Import price feed service for real data
from paper_trading.services.price_feed_service import PriceFeedService

from paper_trading.intelligence.base import (
    IntelligenceEngine,
    IntelligenceLevel,
    MarketContext,
    TradingDecision
)
from paper_trading.intelligence.analyzers import CompositeMarketAnalyzer

# Import the type utilities for production-level type safety
try:
    from paper_trading.utils.type_utils import TypeConverter, MarketDataNormalizer
except ImportError:
    # Fallback if type_utils not yet created
    class TypeConverter:
        @staticmethod
        def to_decimal(value, default=None):
            if default is None:
                default = Decimal('0')
            try:
                if value is None:
                    return default
                return Decimal(str(value))
            except:
                return default
        
        @staticmethod
        def safe_multiply(a, b):
            return TypeConverter.to_decimal(a) * TypeConverter.to_decimal(b)
        
        @staticmethod
        def safe_percentage(value, percentage, precision=2):
            result = (TypeConverter.to_decimal(value) * TypeConverter.to_decimal(percentage)) / Decimal('100')
            quantize_str = '0.' + '0' * precision
            return result.quantize(Decimal(quantize_str))
    
    class MarketDataNormalizer:
        @staticmethod
        def normalize_context(context):
            return context

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class IntelLevelConfig:
    """Configuration for each intelligence level."""
    
    level: int
    name: str
    description: str
    risk_tolerance: Decimal
    max_position_percent: Decimal
    min_confidence_required: Decimal
    min_position_usd: Decimal = Decimal('10')  # Add minimum position
    use_mev_protection: bool = True
    gas_aggressiveness: str = "standard"
    trade_frequency: str = "moderate"
    decision_speed: str = "moderate"


@dataclass
class PriceHistory:
    """
    Historical price data for a token.
    
    Used to track price movements and calculate trends for better
    trading decisions.
    """
    token_address: str
    token_symbol: str
    prices: List[Decimal]  # Recent prices
    timestamps: List[datetime]  # When prices were fetched
    
    def get_price_change_percent(self, period_minutes: int = 60) -> Optional[Decimal]:
        """
        Calculate price change percentage over a time period.
        
        Args:
            period_minutes: Time period to calculate change over
            
        Returns:
            Price change percentage, or None if insufficient data
        """
        if len(self.prices) < 2:
            return None
        
        # Find price from period_minutes ago
        cutoff_time = timezone.now() - timedelta(minutes=period_minutes)
        
        for i, timestamp in enumerate(self.timestamps):
            if timestamp <= cutoff_time:
                if i < len(self.prices) - 1:
                    old_price = self.prices[i]
                    current_price = self.prices[-1]
                    
                    change = ((current_price - old_price) / old_price) * Decimal('100')
                    return change
        
        return None
    
    def is_trending_up(self) -> bool:
        """Check if price is in upward trend."""
        if len(self.prices) < 3:
            return False
        
        # Simple trend: last 3 prices increasing
        return (
            self.prices[-1] > self.prices[-2] and
            self.prices[-2] > self.prices[-3]
        )
    
    def is_trending_down(self) -> bool:
        """Check if price is in downward trend."""
        if len(self.prices) < 3:
            return False
        
        # Simple trend: last 3 prices decreasing
        return (
            self.prices[-1] < self.prices[-2] and
            self.prices[-2] < self.prices[-3]
        )


# =============================================================================
# INTEL LEVEL CONFIGURATIONS
# =============================================================================

# Intel level configurations (1-10)
INTEL_CONFIGS = {
    1: IntelLevelConfig(
        level=1,
        name="Ultra Cautious - Maximum Safety",
        description="Extreme caution, misses opportunities for safety",
        risk_tolerance=Decimal('20'),
        max_position_percent=Decimal('2'),
        min_confidence_required=Decimal('95'),
        min_position_usd=Decimal('10'),
        use_mev_protection=True,
        gas_aggressiveness="minimal",
        trade_frequency="very_low",
        decision_speed="slow"
    ),
    2: IntelLevelConfig(
        level=2,
        name="Very Cautious - High Safety",
        description="Very conservative, only obvious opportunities",
        risk_tolerance=Decimal('25'),
        max_position_percent=Decimal('3'),
        min_confidence_required=Decimal('90'),
        min_position_usd=Decimal('20'),
        use_mev_protection=True,
        gas_aggressiveness="low",
        trade_frequency="low",
        decision_speed="slow"
    ),
    3: IntelLevelConfig(
        level=3,
        name="Cautious - Safety First",
        description="Conservative approach with careful risk management",
        risk_tolerance=Decimal('30'),
        max_position_percent=Decimal('5'),
        min_confidence_required=Decimal('85'),
        min_position_usd=Decimal('30'),
        use_mev_protection=True,
        gas_aggressiveness="standard",
        trade_frequency="low",
        decision_speed="moderate"
    ),
    4: IntelLevelConfig(
        level=4,
        name="Moderately Cautious",
        description="Balanced but leaning towards safety",
        risk_tolerance=Decimal('40'),
        max_position_percent=Decimal('7'),
        min_confidence_required=Decimal('75'),
        min_position_usd=Decimal('40'),
        use_mev_protection=True,
        gas_aggressiveness="standard",
        trade_frequency="moderate",
        decision_speed="moderate"
    ),
    5: IntelLevelConfig(
        level=5,
        name="Balanced - Smart Trading",
        description="Optimal balance of risk and opportunity",
        risk_tolerance=Decimal('50'),
        max_position_percent=Decimal('10'),
        min_confidence_required=Decimal('65'),
        min_position_usd=Decimal('50'),
        use_mev_protection=True,
        gas_aggressiveness="standard",
        trade_frequency="moderate",
        decision_speed="moderate"
    ),
    6: IntelLevelConfig(
        level=6,
        name="Moderately Aggressive",
        description="Favors opportunities while managing risk",
        risk_tolerance=Decimal('60'),
        max_position_percent=Decimal('12'),
        min_confidence_required=Decimal('55'),
        min_position_usd=Decimal('60'),
        use_mev_protection=False,
        gas_aggressiveness="standard",
        trade_frequency="moderate",
        decision_speed="fast"
    ),
    7: IntelLevelConfig(
        level=7,
        name="Aggressive - Growth Focus",
        description="Prioritizes profits with calculated risks",
        risk_tolerance=Decimal('70'),
        max_position_percent=Decimal('15'),
        min_confidence_required=Decimal('45'),
        min_position_usd=Decimal('70'),
        use_mev_protection=False,
        gas_aggressiveness="aggressive",
        trade_frequency="high",
        decision_speed="fast"
    ),
    8: IntelLevelConfig(
        level=8,
        name="Very Aggressive",
        description="High risk tolerance, competitive execution",
        risk_tolerance=Decimal('80'),
        max_position_percent=Decimal('20'),
        min_confidence_required=Decimal('35'),
        min_position_usd=Decimal('80'),
        use_mev_protection=False,
        gas_aggressiveness="aggressive",
        trade_frequency="high",
        decision_speed="very_fast"
    ),
    9: IntelLevelConfig(
        level=9,
        name="Ultra Aggressive - Maximum Risk",
        description="Extreme risk-taking for maximum profits",
        risk_tolerance=Decimal('90'),
        max_position_percent=Decimal('25'),
        min_confidence_required=Decimal('25'),
        min_position_usd=Decimal('90'),
        use_mev_protection=False,
        gas_aggressiveness="ultra_aggressive",
        trade_frequency="very_high",
        decision_speed="ultra_fast"
    ),
    10: IntelLevelConfig(
        level=10,
        name="Fully Autonomous - AI Optimized",
        description="Bot determines optimal approach using ML",
        risk_tolerance=Decimal('0'),  # Dynamic
        max_position_percent=Decimal('0'),  # Dynamic
        min_confidence_required=Decimal('0'),  # Dynamic
        min_position_usd=Decimal('100'),
        use_mev_protection=False,  # Dynamic
        gas_aggressiveness="dynamic",
        trade_frequency="dynamic",
        decision_speed="optimal"
    )
}


# =============================================================================
# MAIN INTELLIGENCE ENGINE
# =============================================================================

class IntelSliderEngine(IntelligenceEngine):
    """
    Intelligence engine controlled by the Intel slider with real data integration.
    
    This engine adapts its behavior based on the selected intelligence
    level, providing a simple interface for users while handling
    complex decision-making internally.
    
    NEW FEATURES:
    - Real-time market context tracking
    - Historical price trend analysis
    - Volatility monitoring
    - Level 10 AI learning data collection
    """
    
    def __init__(
        self, 
        intel_level: int = 5, 
        account_id: Optional[str] = None,
        strategy_config=None,
        chain_id: int = 84532
    ):
        """
        Initialize the Intel Slider engine with real data integration.
        
        Args:
            intel_level: Intelligence level (1-10)
            account_id: Optional paper trading account ID
            strategy_config: Optional PaperStrategyConfiguration to override defaults
            chain_id: Chain ID for price feeds (default: Base Sepolia 84532)
        """
        super().__init__(intel_level)
        self.config = INTEL_CONFIGS[intel_level]
        self.account_id = account_id
        self.chain_id = chain_id
        self.analyzer = CompositeMarketAnalyzer()
        self.converter = TypeConverter()
        self.normalizer = MarketDataNormalizer()
        
        # Initialize price service for real data
        self.price_service = PriceFeedService(chain_id=chain_id)
        self.price_history_cache: Dict[str, PriceHistory] = {}
        
        # Initialize market tracking storage (NEW)
        self.market_history: Dict[str, List[MarketContext]] = {}
        self.price_trends: Dict[str, Dict[str, Any]] = {}
        self.volatility_tracker: Dict[str, List[Decimal]] = {}
        
        # Level 10 AI learning storage
        if intel_level == 10:
            self.ml_training_data: List[Dict[str, Any]] = []
        
        # Apply configuration overrides from database
        if strategy_config:
            self._apply_strategy_config(strategy_config)
        
        # Learning system data (for level 10)
        self.historical_decisions: List[TradingDecision] = []
        self.performance_history: List[Dict[str, Any]] = []
        
        self.logger.info(
            f"[INTEL] Intel Slider Engine initialized: Level {intel_level} - "
            f"{self.config.name} (Chain ID: {chain_id})"
        )
    
    def _apply_strategy_config(self, strategy_config):
        """Apply configuration overrides from database."""
        try:
            self.logger.info(
                f"[CONFIG] Applying database configuration overrides: {strategy_config.name}"
            )
            
            # Override confidence threshold
            if strategy_config.confidence_threshold:
                self.config.min_confidence_required = Decimal(
                    str(strategy_config.confidence_threshold)
                )
                self.logger.info(
                    f"[CONFIG] Confidence threshold: {self.config.min_confidence_required}%"
                )
            
            # Override max position size
            if strategy_config.max_position_size_percent:
                self.config.max_position_percent = Decimal(
                    str(strategy_config.max_position_size_percent)
                )
                self.logger.info(
                    f"[CONFIG] Max position size: {self.config.max_position_percent}%"
                )
            
            # Override risk tolerance based on trading mode
            if strategy_config.trading_mode == 'CONSERVATIVE':
                self.config.risk_tolerance = Decimal('30')
                self.logger.info("[CONFIG] Risk tolerance: CONSERVATIVE (30%)")
            elif strategy_config.trading_mode == 'AGGRESSIVE':
                self.config.risk_tolerance = Decimal('70')
                self.logger.info("[CONFIG] Risk tolerance: AGGRESSIVE (70%)")
            elif strategy_config.trading_mode == 'MODERATE':
                self.config.risk_tolerance = Decimal('50')
                self.logger.info("[CONFIG] Risk tolerance: MODERATE (50%)")
            
            # Override stop loss
            if strategy_config.stop_loss_percent:
                stop_loss = Decimal(str(strategy_config.stop_loss_percent))
                self.logger.info(f"[CONFIG] Stop loss: {stop_loss}%")
            
            # Override max daily trades
            if strategy_config.max_daily_trades:
                self.logger.info(
                    f"[CONFIG] Max daily trades: {strategy_config.max_daily_trades}"
                )
        except Exception as e:
            self.logger.error(
                f"[CONFIG] Error applying strategy config: {e}",
                exc_info=True
            )

    # =========================================================================
    # REAL DATA INTEGRATION METHODS
    # =========================================================================

    async def _fetch_real_price(
        self,
        token_address: str,
        token_symbol: str
    ) -> Optional[Decimal]:
        """
        Fetch real token price from price feed service.
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol for logging
            
        Returns:
            Current token price in USD, or None if fetch fails
        """
        try:
            price = await self.price_service.get_token_price(
                token_address,
                token_symbol
            )
            
            if price and price > 0:
                self.logger.debug(
                    f"[PRICE] Fetched real price for {token_symbol}: ${price:.2f}"
                )
                
                # Update price history cache
                self._update_price_history(token_address, token_symbol, price)
                
                return price
            else:
                self.logger.warning(
                    f"[PRICE] Invalid price for {token_symbol}: {price}"
                )
                return None
                
        except Exception as e:
            self.logger.error(
                f"[PRICE] Error fetching price for {token_symbol}: {e}",
                exc_info=True
            )
            return None
    
    def _update_price_history(
        self,
        token_address: str,
        token_symbol: str,
        price: Decimal
    ):
        """
        Update price history cache with new price.
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            price: New price to add
        """
        try:
            if token_address not in self.price_history_cache:
                self.price_history_cache[token_address] = PriceHistory(
                    token_address=token_address,
                    token_symbol=token_symbol,
                    prices=[],
                    timestamps=[]
                )
            
            history = self.price_history_cache[token_address]
            history.prices.append(price)
            history.timestamps.append(timezone.now())
            
            # Keep only last 100 prices (prevent memory bloat)
            if len(history.prices) > 100:
                history.prices.pop(0)
                history.timestamps.pop(0)
            
            self.logger.debug(
                f"[PRICE HISTORY] Updated for {token_symbol}: "
                f"{len(history.prices)} prices tracked"
            )
        except Exception as e:
            self.logger.error(
                f"[PRICE HISTORY] Error updating history for {token_symbol}: {e}",
                exc_info=True
            )

    # =========================================================================
    # MARKET ANALYSIS WITH REAL DATA
    # =========================================================================

    async def analyze_market(
        self,
        token_address: str,
        token_symbol: str = "UNKNOWN",
        **kwargs
    ) -> MarketContext:
        """
        Analyze market conditions with REAL price data.
        
        Args:
            token_address: Token to analyze
            token_symbol: Token symbol for better logging
            **kwargs: Additional parameters
            
        Returns:
            Market context with real prices and intel-level adjustments
        """
        try:
            self.logger.info(
                f"[ANALYZE] Starting market analysis for {token_symbol} "
                f"(Level {self.intel_level})"
            )
            
            # STEP 1: Fetch real current price
            current_price = await self._fetch_real_price(token_address, token_symbol)
            
            if not current_price or current_price <= 0:
                self.logger.warning(
                    f"[ANALYZE] Could not fetch real price for {token_symbol}, "
                    "using fallback"
                )
                current_price = kwargs.get('fallback_price', Decimal('0'))
            
            # STEP 2: Get comprehensive analysis from analyzers
            analysis = await self.analyzer.analyze_comprehensive(
                token_address=token_address,
                trade_size_usd=kwargs.get('trade_size_usd', Decimal('1000')),
                liquidity_usd=kwargs.get('liquidity_usd', Decimal('100000')),
                volume_24h=kwargs.get('volume_24h', Decimal('50000'))
            )
            
            # STEP 3: Get price history data
            price_history = self.price_history_cache.get(token_address)
            price_24h_ago = current_price
            price_trend = 'neutral'
            momentum = Decimal('0')
            
            if price_history and len(price_history.prices) >= 2:
                # Use oldest available price as 24h ago price
                price_24h_ago = price_history.prices[0]
                
                # Calculate momentum (1h change)
                change_1h = price_history.get_price_change_percent(60)
                if change_1h:
                    momentum = change_1h
                
                # Determine trend
                if price_history.is_trending_up():
                    price_trend = 'bullish'
                elif price_history.is_trending_down():
                    price_trend = 'bearish'
            
            # STEP 4: Calculate volatility from price history
            volatility = Decimal('0.10')  # Default 10%
            if price_history and len(price_history.prices) >= 5:
                # Calculate standard deviation of recent prices
                prices = [float(p) for p in price_history.prices[-10:]]
                mean_price = sum(prices) / len(prices)
                variance = sum((p - mean_price) ** 2 for p in prices) / len(prices)
                std_dev = variance ** 0.5
                volatility = Decimal(str(std_dev / mean_price)) if mean_price > 0 else Decimal('0.10')
            
            # STEP 5: Build MarketContext with REAL data
            context = MarketContext(
                # Real price data
                token_symbol=token_symbol,
                token_address=token_address,
                current_price=current_price,
                price_24h_ago=price_24h_ago,
                volatility=volatility,
                trend=price_trend,
                momentum=momentum,
                
                # Market data from analysis
                volume_24h=self.converter.to_decimal(
                    kwargs.get('volume_24h', Decimal('50000'))
                ),
                liquidity_usd=self.converter.to_decimal(
                    analysis['liquidity']['pool_liquidity_usd']
                ),
                
                # Network conditions
                gas_price_gwei=self.converter.to_decimal(
                    analysis['gas_analysis']['current_gas_gwei']
                ),
                network_congestion=analysis['gas_analysis']['network_congestion'],
                pending_tx_count=analysis['gas_analysis']['pending_tx_count'],
                
                # MEV environment
                mev_threat_level=analysis['mev_analysis']['threat_level'],
                sandwich_risk=analysis['mev_analysis']['sandwich_risk'],
                frontrun_probability=analysis['mev_analysis']['frontrun_probability'],
                
                # Competition
                competing_bots_detected=analysis['competition']['competing_bots'],
                average_bot_gas_price=self.converter.to_decimal(
                    analysis['competition']['avg_bot_gas']
                ),
                bot_success_rate=analysis['competition']['bot_success_rate'],
                
                # Liquidity
                pool_liquidity_usd=self.converter.to_decimal(
                    analysis['liquidity']['pool_liquidity_usd']
                ),
                expected_slippage=self.converter.to_decimal(
                    analysis['liquidity']['expected_slippage']
                ),
                liquidity_depth_score=analysis['liquidity']['liquidity_depth_score'],
                
                # Market state
                volatility_index=float(volatility * 100),
                chaos_event_detected=analysis['market_state']['chaos_event_detected'],
                trend_direction=price_trend,
                volume_24h_change=kwargs.get('volume_24h_change', Decimal('0')),
                
                # Historical performance
                recent_failures=kwargs.get('recent_failures', 0),
                success_rate_1h=kwargs.get('success_rate_1h', 50.0),
                average_profit_1h=kwargs.get('average_profit_1h', Decimal('0')),
                
                # Metadata
                timestamp=timezone.now(),
                confidence_in_data=100.0 if current_price > 0 else 50.0
            )
            
            # STEP 6: Normalize all numeric fields
            context = self.normalizer.normalize_context(context)
            
            # STEP 7: Adjust perception based on intel level
            context = self._adjust_market_perception(context)
            
            self.logger.info(
                f"[ANALYZE] Market analysis complete for {token_symbol}: "
                f"Price=${current_price:.2f}, Trend={price_trend}, "
                f"Volatility={volatility:.2%}"
            )
            
            return context
            
        except Exception as e:
            self.logger.error(
                f"[ANALYZE] Error in market analysis for {token_symbol}: {e}",
                exc_info=True
            )
            raise
    
    def _adjust_market_perception(self, context: MarketContext) -> MarketContext:
        """
        Adjust market perception based on intel level.
        
        Lower levels see more risk, higher levels see more opportunity.
        
        Args:
            context: Raw market context
            
        Returns:
            Adjusted market context
        """
        try:
            # Cautious levels (1-3): Amplify risks, diminish opportunities
            if self.intel_level <= 3:
                context.mev_threat_level *= 1.5
                context.network_congestion *= 1.3
                context.volatility_index *= 1.4
                
                self.logger.debug(
                    f"[PERCEPTION] Ultra Cautious adjustment: Amplified risks"
                )
            
            # Balanced levels (4-6): Neutral perception
            elif self.intel_level <= 6:
                # No adjustment needed
                self.logger.debug("[PERCEPTION] Balanced view: No adjustments")
            
            # Aggressive levels (7-9): Diminish risks, see opportunities
            elif self.intel_level <= 9:
                context.mev_threat_level *= 0.7
                context.network_congestion *= 0.8
                context.volatility_index *= 0.6
                
                self.logger.debug(
                    f"[PERCEPTION] Aggressive adjustment: Reduced risk perception"
                )
            
            # Autonomous (10): Dynamic ML-based adjustments
            else:
                # Use historical data to optimize perception
                if len(self.historical_decisions) > 10:
                    # Analyze past decisions to optimize perception
                    self.logger.debug(
                        "[PERCEPTION] Autonomous: ML-optimized perception"
                    )
                else:
                    self.logger.debug(
                        "[PERCEPTION] Autonomous: Collecting training data"
                    )
            
            return context
            
        except Exception as e:
            self.logger.error(
                f"[PERCEPTION] Error adjusting market perception: {e}",
                exc_info=True
            )
            return context

    # =========================================================================
    # TRADING DECISION WITH REAL DATA
    # =========================================================================

    async def make_decision(
        self,
        market_context: MarketContext,
        account_balance: Decimal,
        existing_positions: List[Dict[str, Any]],
        token_address: str,
        token_symbol: str
    ) -> TradingDecision:
        """
        Make a trading decision with REAL price data.
        
        Args:
            market_context: Current market conditions (with real prices)
            account_balance: Available balance
            existing_positions: Current open positions
            token_address: Token being analyzed
            token_symbol: Token symbol
            
        Returns:
            Complete trading decision with real price-based reasoning
        """
        try:
            start_time = timezone.now()
            
            self.logger.info(
                f"[DECISION] Making decision for {token_symbol} at "
                f"${market_context.current_price:.2f} (Level {self.intel_level})"
            )
            
            # STEP 1: Calculate risk score with real price volatility
            risk_score = self._calculate_risk_score(market_context)
            
            # STEP 2: Calculate opportunity score with price trends
            opportunity_score = self._calculate_opportunity_score(market_context)
            
            # STEP 3: Calculate overall confidence
            confidence_score = self._calculate_confidence_score(
                risk_score,
                opportunity_score,
                market_context
            )
            
            # STEP 4: Make BUY/SKIP decision
            action = self._determine_action(
                risk_score,
                opportunity_score,
                confidence_score,
                market_context
            )
            
            # STEP 5: Calculate position size with real USD amounts
            position_size_usd = Decimal('0')
            position_size_percent = Decimal('0')
            
            if action == 'BUY' and market_context.current_price > 0:
                position_size_percent = self._calculate_position_size(
                    risk_score,
                    opportunity_score,
                    market_context
                )
                position_size_usd = (
                    account_balance * position_size_percent / Decimal('100')
                )
                
                # Ensure minimum position size
                if position_size_usd < self.config.min_position_usd:
                    if account_balance >= self.config.min_position_usd:
                        position_size_usd = self.config.min_position_usd
                        position_size_percent = (
                            position_size_usd / account_balance * Decimal('100')
                        )
                    else:
                        action = 'SKIP'
                        self.logger.warning(
                            f"[DECISION] Insufficient balance for minimum position "
                            f"(${account_balance:.2f} < ${self.config.min_position_usd:.2f})"
                        )
            
            # STEP 6: Calculate stop loss with real price
            stop_loss_percent = None
            if action == 'BUY':
                stop_loss_percent = self._calculate_stop_loss(risk_score)
            
            # STEP 7: Determine execution strategy
            execution_strategy = self._determine_execution_strategy(
                market_context,
                action
            )
            
            # STEP 8: Build the decision
            decision = TradingDecision(
                # Core decision
                action=action,
                token_address=token_address,
                token_symbol=token_symbol,
                
                # Position sizing with REAL USD amounts
                position_size_percent=position_size_percent,
                position_size_usd=position_size_usd,
                stop_loss_percent=stop_loss_percent,
                take_profit_targets=[Decimal('5'), Decimal('10'), Decimal('20')],
                
                # Execution strategy
                execution_mode=execution_strategy['mode'],
                use_private_relay=execution_strategy['use_private_relay'],
                gas_strategy=execution_strategy['gas_strategy'],
                max_gas_price_gwei=execution_strategy['max_gas_gwei'],
                
                # Confidence and reasoning
                overall_confidence=confidence_score,
                risk_score=risk_score,
                opportunity_score=opportunity_score,
                
                # Detailed reasoning with REAL price data
                primary_reasoning=self._generate_reasoning(
                    action,
                    risk_score,
                    opportunity_score,
                    confidence_score,
                    market_context
                ),
                risk_factors=self._identify_risk_factors(market_context),
                opportunity_factors=self._identify_opportunity_factors(market_context),
                mitigation_strategies=self._generate_mitigation_strategies(market_context),
                
                # Intel level impact
                intel_level_used=self.intel_level,
                intel_adjustments={},
                
                # Timing
                time_sensitivity=self._assess_time_sensitivity(market_context),
                max_execution_time_ms=self._calculate_max_execution_time(),
                
                # Metadata
                decision_id=str(uuid.uuid4()),
                timestamp=timezone.now(),
                processing_time_ms=(timezone.now() - start_time).total_seconds() * 1000
            )
            
            # STEP 9: Apply intel level adjustments
            decision = self.adjust_for_intel_level(decision)
            
            # STEP 10: Store decision for learning (Level 10)
            if self.intel_level == 10:
                self.historical_decisions.append(decision)
                if len(self.historical_decisions) > 100:
                    self.historical_decisions.pop(0)
            
            self.logger.info(
                f"[DECISION] {action} decision for {token_symbol}: "
                f"Risk={risk_score:.1f}, Opportunity={opportunity_score:.1f}, "
                f"Confidence={confidence_score:.1f}, Size=${position_size_usd:.2f}"
            )
            
            return decision
            
        except Exception as e:
            self.logger.error(
                f"[DECISION] Error making decision for {token_symbol}: {e}",
                exc_info=True
            )
            raise

    # =========================================================================
    # DECISION CALCULATION HELPERS
    # =========================================================================

    def _calculate_risk_score(self, context: MarketContext) -> Decimal:
        """Calculate risk score with real price volatility."""
        try:
            context = self.normalizer.normalize_context(context)
            
            # Base risk from MEV and volatility
            mev_risk = self.converter.to_decimal(context.mev_threat_level, Decimal('0'))
            volatility_risk = self.converter.to_decimal(
                context.volatility_index,
                Decimal('0')
            )
            network_risk = self.converter.to_decimal(
                context.network_congestion,
                Decimal('0')
            )
            
            # Liquidity risk
            liquidity_score = self.converter.to_decimal(
                context.liquidity_depth_score,
                Decimal('100')
            )
            liquidity_risk = (Decimal('100') - liquidity_score)
            
            # Competition risk
            competing_bots = self.converter.to_decimal(
                context.competing_bots_detected,
                Decimal('0')
            )
            competition_risk = min(competing_bots * Decimal('10'), Decimal('50'))
            
            # Weighted average
            risk_score = (
                mev_risk * Decimal('0.25') +
                volatility_risk * Decimal('0.30') +
                network_risk * Decimal('0.15') +
                liquidity_risk * Decimal('0.20') +
                competition_risk * Decimal('0.10')
            )
            
            # Ensure within bounds
            risk_score = max(Decimal('0'), min(Decimal('100'), risk_score))
            
            self.logger.debug(
                f"[RISK] Score={risk_score:.1f} "
                f"(MEV={mev_risk:.1f}, Vol={volatility_risk:.1f}, "
                f"Liq={liquidity_risk:.1f})"
            )
            
            return risk_score
            
        except Exception as e:
            self.logger.error(f"[RISK] Error calculating risk score: {e}", exc_info=True)
            return Decimal('50')  # Safe default
    
    def _calculate_opportunity_score(self, context: MarketContext) -> Decimal:
        """Calculate opportunity score with price trends."""
        try:
            context = self.normalizer.normalize_context(context)
            
            # Trend score
            trend_score = Decimal('50')  # Default neutral
            if context.trend_direction == 'bullish':
                trend_score = Decimal('75')
            elif context.trend_direction == 'bearish':
                trend_score = Decimal('25')
            
            # Momentum score
            momentum = self.converter.to_decimal(context.momentum, Decimal('0'))
            momentum_score = Decimal('50') + (momentum * Decimal('5'))
            momentum_score = max(Decimal('0'), min(Decimal('100'), momentum_score))
            
            # Volume score
            volume_change = self.converter.to_decimal(
                context.volume_24h_change,
                Decimal('0')
            )
            volume_score = Decimal('50') + (volume_change / Decimal('2'))
            volume_score = max(Decimal('0'), min(Decimal('100'), volume_score))
            
            # Liquidity score
            liquidity_score = self.converter.to_decimal(
                context.liquidity_depth_score,
                Decimal('50')
            )
            
            # Network efficiency
            congestion = self.converter.to_decimal(
                context.network_congestion,
                Decimal('50')
            )
            network_score = Decimal('100') - congestion
            
            # Weighted average
            opportunity_score = (
                trend_score * Decimal('0.30') +
                momentum_score * Decimal('0.25') +
                volume_score * Decimal('0.20') +
                liquidity_score * Decimal('0.15') +
                network_score * Decimal('0.10')
            )
            
            # Ensure within bounds
            opportunity_score = max(Decimal('0'), min(Decimal('100'), opportunity_score))
            
            self.logger.debug(
                f"[OPPORTUNITY] Score={opportunity_score:.1f} "
                f"(Trend={trend_score:.1f}, Momentum={momentum_score:.1f}, "
                f"Volume={volume_score:.1f})"
            )
            
            return opportunity_score
            
        except Exception as e:
            self.logger.error(
                f"[OPPORTUNITY] Error calculating opportunity score: {e}",
                exc_info=True
            )
            return Decimal('50')  # Safe default
    
    def _calculate_confidence_score(
        self,
        risk_score: Decimal,
        opportunity_score: Decimal,
        context: MarketContext
    ) -> Decimal:
        """Calculate overall confidence in the decision."""
        try:
            # Convert inputs to Decimal
            risk_score = self.converter.to_decimal(risk_score)
            opportunity_score = self.converter.to_decimal(opportunity_score)
            
            # Base confidence from risk/opportunity balance
            if opportunity_score > risk_score:
                base_confidence = opportunity_score - (risk_score / Decimal('2'))
            else:
                base_confidence = Decimal('50') - (risk_score - opportunity_score)
            
            # Adjust for data confidence
            data_confidence = self.converter.to_decimal(
                context.confidence_in_data,
                Decimal('100')
            )
            confidence_multiplier = data_confidence / Decimal('100')
            
            # Adjust for price data availability
            if context.current_price > 0:
                confidence_multiplier *= Decimal('1.1')  # 10% boost for real prices
            
            # Final confidence
            confidence_score = base_confidence * confidence_multiplier
            
            # Ensure within bounds
            confidence_score = max(Decimal('0'), min(Decimal('100'), confidence_score))
            
            self.logger.debug(
                f"[CONFIDENCE] Score={confidence_score:.1f} "
                f"(Base={base_confidence:.1f}, Data={data_confidence:.1f}%)"
            )
            
            return confidence_score
            
        except Exception as e:
            self.logger.error(
                f"[CONFIDENCE] Error calculating confidence: {e}",
                exc_info=True
            )
            return Decimal('50')  # Safe default
    
    def _determine_action(
        self,
        risk_score: Decimal,
        opportunity_score: Decimal,
        confidence_score: Decimal,
        context: MarketContext
    ) -> str:
        """Determine BUY or SKIP action."""
        try:
            risk_score = self.converter.to_decimal(risk_score)
            opportunity_score = self.converter.to_decimal(opportunity_score)
            confidence_score = self.converter.to_decimal(confidence_score)
            
            # Check minimum requirements
            if confidence_score < self.config.min_confidence_required:
                self.logger.debug(
                    f"[ACTION] SKIP - Low confidence "
                    f"({confidence_score:.1f} < {self.config.min_confidence_required})"
                )
                return 'SKIP'
            
            if risk_score > self.config.risk_tolerance:
                self.logger.debug(
                    f"[ACTION] SKIP - High risk "
                    f"({risk_score:.1f} > {self.config.risk_tolerance})"
                )
                return 'SKIP'
            
            # Price-based decision: Only buy if we have a valid price
            if not context.current_price or context.current_price <= 0:
                self.logger.warning(
                    "[ACTION] SKIP - No valid price data available"
                )
                return 'SKIP'
            
            # Opportunity must exceed risk
            if opportunity_score <= risk_score:
                self.logger.debug(
                    f"[ACTION] SKIP - Opportunity "
                    f"({opportunity_score:.1f}) <= Risk ({risk_score:.1f})"
                )
                return 'SKIP'
            
            # All checks passed
            self.logger.debug(
                f"[ACTION] BUY - Opportunity={opportunity_score:.1f}, "
                f"Risk={risk_score:.1f}, Confidence={confidence_score:.1f}"
            )
            return 'BUY'
            
        except Exception as e:
            self.logger.error(
                f"[ACTION] Error determining action: {e}",
                exc_info=True
            )
            return 'SKIP'  # Safe default
    
    def _calculate_position_size(
        self,
        risk_score: Decimal,
        opportunity_score: Decimal,
        context: MarketContext
    ) -> Decimal:
        """Calculate position size percentage."""
        try:
            risk_score = self.converter.to_decimal(risk_score)
            opportunity_score = self.converter.to_decimal(opportunity_score)
            
            # Base size from config
            base_size = self.config.max_position_percent
            
            # Adjust based on opportunity/risk ratio
            ratio = opportunity_score / max(risk_score, Decimal('1'))
            
            if ratio > Decimal('2'):  # Great opportunity
                position_size = base_size * Decimal('1.0')
            elif ratio > Decimal('1.5'):  # Good opportunity
                position_size = base_size * Decimal('0.8')
            elif ratio > Decimal('1.2'):  # Moderate opportunity
                position_size = base_size * Decimal('0.6')
            else:  # Minimal opportunity
                position_size = base_size * Decimal('0.4')
            
            # Adjust for volatility (higher volatility = smaller position)
            volatility = self.converter.to_decimal(
                context.volatility_index,
                Decimal('50')
            )
            if volatility > 70:
                position_size *= Decimal('0.7')
            elif volatility > 50:
                position_size *= Decimal('0.85')
            
            # Ensure within bounds
            position_size = max(Decimal('1'), min(base_size, position_size))
            
            self.logger.debug(
                f"[POSITION SIZE] {position_size:.2f}% "
                f"(Ratio={ratio:.2f}, Volatility={volatility:.1f})"
            )
            
            return position_size.quantize(Decimal('0.01'))
            
        except Exception as e:
            self.logger.error(
                f"[POSITION SIZE] Error calculating position size: {e}",
                exc_info=True
            )
            return Decimal('5')  # Safe default
    
    def _calculate_stop_loss(self, risk_score: Decimal) -> Decimal:
        """Calculate stop loss percentage based on risk."""
        try:
            risk_score = self.converter.to_decimal(risk_score)
            
            # Higher risk = tighter stop loss
            if risk_score > 70:
                stop_loss = Decimal('3')  # 3% stop loss
            elif risk_score > 50:
                stop_loss = Decimal('5')  # 5% stop loss
            elif risk_score > 30:
                stop_loss = Decimal('7')  # 7% stop loss
            else:
                stop_loss = Decimal('10')  # 10% stop loss
            
            self.logger.debug(
                f"[STOP LOSS] {stop_loss}% (Risk={risk_score:.1f})"
            )
            
            return stop_loss
            
        except Exception as e:
            self.logger.error(
                f"[STOP LOSS] Error calculating stop loss: {e}",
                exc_info=True
            )
            return Decimal('5')  # Safe default
    
    def _determine_execution_strategy(
        self,
        context: MarketContext,
        action: str
    ) -> Dict[str, Any]:
        """Determine execution strategy based on intel level."""
        try:
            context = self.normalizer.normalize_context(context)
            
            if action in ['SKIP', 'HOLD']:
                return {
                    'mode': 'NONE',
                    'use_private_relay': False,
                    'gas_strategy': 'standard',
                    'max_gas_gwei': self.converter.to_decimal(
                        context.gas_price_gwei
                    )
                }
            
            # Determine gas strategy based on config
            if self.config.gas_aggressiveness == "minimal":
                gas_strategy = 'standard'
                gas_multiplier = Decimal('1.0')
            elif self.config.gas_aggressiveness == "aggressive":
                gas_strategy = 'aggressive'
                gas_multiplier = Decimal('1.5')
            elif self.config.gas_aggressiveness == "ultra_aggressive":
                gas_strategy = 'ultra_aggressive'
                gas_multiplier = Decimal('2.0')
            else:  # adaptive or dynamic
                congestion = self.converter.to_decimal(
                    context.network_congestion,
                    Decimal('50')
                )
                if congestion > 70:
                    gas_strategy = 'aggressive'
                    gas_multiplier = Decimal('1.5')
                else:
                    gas_strategy = 'standard'
                    gas_multiplier = Decimal('1.1')
            
            # Determine execution mode
            if self.config.decision_speed in ['ultra_fast', 'very_fast']:
                mode = 'FAST_LANE'
            elif self.converter.to_decimal(context.mev_threat_level, Decimal('50')) > 60:
                mode = 'SMART_LANE'
            else:
                mode = 'HYBRID'
            
            # MEV protection
            mev_threat = self.converter.to_decimal(
                context.mev_threat_level,
                Decimal('0')
            )
            sandwich_risk = self.converter.to_decimal(
                context.sandwich_risk,
                Decimal('0')
            )
            use_relay = (
                self.config.use_mev_protection or
                mev_threat > 70 or
                sandwich_risk > 60
            )
            
            return {
                'mode': mode,
                'use_private_relay': use_relay,
                'gas_strategy': gas_strategy,
                'max_gas_gwei': self.converter.safe_multiply(
                    self.converter.to_decimal(context.gas_price_gwei),
                    gas_multiplier
                )
            }
            
        except Exception as e:
            self.logger.error(
                f"[EXECUTION] Error determining execution strategy: {e}",
                exc_info=True
            )
            return {
                'mode': 'SMART_LANE',
                'use_private_relay': True,
                'gas_strategy': 'standard',
                'max_gas_gwei': Decimal('30')
            }

    # =========================================================================
    # REASONING AND FACTORS
    # =========================================================================

    def _generate_reasoning(
        self,
        action: str,
        risk_score: Decimal,
        opportunity_score: Decimal,
        confidence_score: Decimal,
        context: MarketContext
    ) -> str:
        """Generate detailed reasoning for the decision."""
        try:
            reasoning = f"Intel Level {self.intel_level} ({self.config.name}) Decision:\n"
            reasoning += f"Action: {action}\n"
            reasoning += f"Risk Assessment: {risk_score:.1f}/100\n"
            reasoning += f"Opportunity Score: {opportunity_score:.1f}/100\n"
            reasoning += f"Confidence: {confidence_score:.1f}/100\n"
            
            # Add price context if available
            if hasattr(context, 'current_price') and context.current_price:
                reasoning += f"Current Price: ${context.current_price:.2f}\n"
            if hasattr(context, 'trend'):
                reasoning += f"Price Trend: {context.trend}\n"
            if hasattr(context, 'momentum') and context.momentum:
                reasoning += f"1H Change: {context.momentum:+.2f}%\n"
            
            reasoning += "\n"
            
            if action == 'BUY':
                reasoning += "Rationale: Favorable opportunity with acceptable risk. "
                if context.trend_direction == 'bullish':
                    reasoning += "Bullish trend supports entry. "
                if hasattr(context, 'trend') and context.trend == 'bullish':
                    reasoning += "Price momentum is positive. "
                liquidity_score = self.converter.to_decimal(
                    context.liquidity_depth_score,
                    Decimal('0')
                )
                if liquidity_score > 70:
                    reasoning += "Good liquidity minimizes slippage. "
            elif action == 'SKIP':
                reasoning += "Rationale: "
                if risk_score > self.config.risk_tolerance:
                    reasoning += f"Risk ({risk_score:.1f}) exceeds tolerance ({self.config.risk_tolerance}). "
                if confidence_score < self.config.min_confidence_required:
                    reasoning += f"Insufficient confidence ({confidence_score:.1f} < {self.config.min_confidence_required}). "
            
            return reasoning
            
        except Exception as e:
            self.logger.error(
                f"[REASONING] Error generating reasoning: {e}",
                exc_info=True
            )
            return f"Decision: {action}"
    
    def _identify_risk_factors(self, context: MarketContext) -> List[str]:
        """Identify key risk factors."""
        try:
            context = self.normalizer.normalize_context(context)
            factors = []
            
            mev_threat = self.converter.to_decimal(
                context.mev_threat_level,
                Decimal('0')
            )
            volatility = self.converter.to_decimal(
                context.volatility_index,
                Decimal('0')
            )
            liquidity_score = self.converter.to_decimal(
                context.liquidity_depth_score,
                Decimal('100')
            )
            competing_bots = self.converter.to_decimal(
                context.competing_bots_detected,
                Decimal('0')
            )
            
            if mev_threat > 60:
                factors.append(f"High MEV threat ({mev_threat:.1f}/100)")
            if volatility > 70:
                factors.append(f"High volatility ({volatility:.1f}/100)")
            if liquidity_score < 40:
                factors.append(f"Poor liquidity depth ({liquidity_score:.1f}/100)")
            if context.chaos_event_detected:
                factors.append("Chaos event detected in market")
            if competing_bots > 5:
                factors.append(f"{int(competing_bots)} competing bots detected")
            
            return factors[:5]  # Top 5 risks
            
        except Exception as e:
            self.logger.error(
                f"[RISK FACTORS] Error identifying risk factors: {e}",
                exc_info=True
            )
            return []
    
    def _identify_opportunity_factors(self, context: MarketContext) -> List[str]:
        """Identify opportunity factors."""
        try:
            context = self.normalizer.normalize_context(context)
            factors = []
            
            volume_change = self.converter.to_decimal(
                context.volume_24h_change,
                Decimal('0')
            )
            liquidity_score = self.converter.to_decimal(
                context.liquidity_depth_score,
                Decimal('0')
            )
            congestion = self.converter.to_decimal(
                context.network_congestion,
                Decimal('100')
            )
            bot_success = self.converter.to_decimal(
                context.bot_success_rate,
                Decimal('100')
            )
            
            if context.trend_direction == 'bullish':
                factors.append("Bullish market trend")
            if hasattr(context, 'trend') and context.trend == 'bullish':
                factors.append("Positive price momentum")
            if volume_change > 50:
                factors.append(f"Volume surge ({volume_change:.1f}%)")
            if liquidity_score > 70:
                factors.append(f"Excellent liquidity ({liquidity_score:.1f}/100)")
            if congestion < 30:
                factors.append("Low network congestion")
            if bot_success < 40:
                factors.append("Low bot competition")
            
            return factors[:5]  # Top 5 opportunities
            
        except Exception as e:
            self.logger.error(
                f"[OPPORTUNITY FACTORS] Error identifying opportunities: {e}",
                exc_info=True
            )
            return []
    
    def _generate_mitigation_strategies(self, context: MarketContext) -> List[str]:
        """Generate risk mitigation strategies."""
        try:
            context = self.normalizer.normalize_context(context)
            strategies = []
            
            mev_threat = self.converter.to_decimal(
                context.mev_threat_level,
                Decimal('0')
            )
            volatility = self.converter.to_decimal(
                context.volatility_index,
                Decimal('0')
            )
            slippage = self.converter.to_decimal(
                context.expected_slippage,
                Decimal('0')
            )
            competing_bots = self.converter.to_decimal(
                context.competing_bots_detected,
                Decimal('0')
            )
            
            if mev_threat > 60:
                strategies.append("Use private relay for MEV protection")
            if volatility > 70:
                strategies.append("Reduce position size for volatility")
            if slippage > 3:
                strategies.append("Split trade to reduce slippage")
            if competing_bots > 5:
                strategies.append("Increase gas for competitive execution")
            
            return strategies
            
        except Exception as e:
            self.logger.error(
                f"[MITIGATION] Error generating strategies: {e}",
                exc_info=True
            )
            return []
    
    def _assess_time_sensitivity(self, context: MarketContext) -> str:
        """Assess time sensitivity of the opportunity."""
        try:
            context = self.normalizer.normalize_context(context)
            
            volatility = self.converter.to_decimal(
                context.volatility_index,
                Decimal('0')
            )
            competing_bots = self.converter.to_decimal(
                context.competing_bots_detected,
                Decimal('0')
            )
            volume_change = self.converter.to_decimal(
                context.volume_24h_change,
                Decimal('0')
            )
            
            if context.chaos_event_detected:
                return 'critical'
            elif volatility > 70 or competing_bots > 5:
                return 'high'
            elif context.trend_direction == 'bullish' and volume_change > 50:
                return 'medium'
            else:
                return 'low'
                
        except Exception as e:
            self.logger.error(
                f"[TIME SENSITIVITY] Error assessing time sensitivity: {e}",
                exc_info=True
            )
            return 'medium'
    
    def _calculate_max_execution_time(self) -> int:
        """Calculate maximum execution time based on intel level."""
        try:
            if self.config.decision_speed == 'ultra_fast':
                return 100  # 100ms
            elif self.config.decision_speed == 'very_fast':
                return 200
            elif self.config.decision_speed == 'fast':
                return 500
            elif self.config.decision_speed == 'moderate':
                return 1000
            else:  # slow
                return 3000
        except Exception as e:
            self.logger.error(
                f"[EXECUTION TIME] Error calculating max time: {e}",
                exc_info=True
            )
            return 1000  # Safe default

    # =========================================================================
    # MARKET CONTEXT TRACKING (NEW)
    # =========================================================================

    def update_market_context(self, market_context: MarketContext) -> None:
        """
        Update the intelligence engine with latest market context.
        
        This method allows the engine to track market conditions over time,
        enabling trend analysis, pattern recognition, and better decision-making.
        Critical for Real Data Integration (Phase 4-5) and Level 10 AI learning.
        
        Args:
            market_context: Latest market context with real-time data
        
        Features:
            - Tracks price history for trend analysis
            - Maintains volatility metrics
            - Stores recent market conditions
            - Enables Level 10 autonomous learning
            - Supports real-time price integration
            - Non-blocking: errors are logged but don't stop execution
        """
        try:
            token_symbol = market_context.token_symbol
            
            self.logger.debug(
                f"[MARKET CONTEXT] Updating context for {token_symbol}: "
                f"Price=${market_context.current_price:.2f}"
            )
            
            # Store market context history (last 100 ticks)
            if token_symbol not in self.market_history:
                self.market_history[token_symbol] = []
                self.logger.debug(
                    f"[MARKET CONTEXT] Created new history tracker for {token_symbol}"
                )
            
            self.market_history[token_symbol].append(market_context)
            
            # Keep only last 100 contexts
            if len(self.market_history[token_symbol]) > 100:
                removed = self.market_history[token_symbol].pop(0)
                self.logger.debug(
                    f"[MARKET CONTEXT] Removed oldest context for {token_symbol} "
                    f"(timestamp: {removed.timestamp})"
                )
            
            # Update price trends
            if token_symbol not in self.price_trends:
                self.price_trends[token_symbol] = {
                    'current_price': market_context.current_price,
                    'highest_price_24h': market_context.current_price,
                    'lowest_price_24h': market_context.current_price,
                    'price_change_percent': Decimal('0'),
                    'trend_direction': 'neutral',
                    'last_updated': market_context.timestamp,
                    'data_points': 1
                }
                self.logger.info(
                    f"[PRICE TREND] Initialized trend tracker for {token_symbol} "
                    f"at ${market_context.current_price:.2f}"
                )
            else:
                trends = self.price_trends[token_symbol]
                old_price = trends['current_price']
                new_price = market_context.current_price
                
                trends['current_price'] = new_price
                trends['data_points'] = trends.get('data_points', 0) + 1
                
                # Update 24h high/low
                if new_price > trends['highest_price_24h']:
                    trends['highest_price_24h'] = new_price
                    self.logger.debug(
                        f"[PRICE TREND] New 24h high for {token_symbol}: ${new_price:.2f}"
                    )
                
                if new_price < trends['lowest_price_24h']:
                    trends['lowest_price_24h'] = new_price
                    self.logger.debug(
                        f"[PRICE TREND] New 24h low for {token_symbol}: ${new_price:.2f}"
                    )
                
                # Calculate price change
                if old_price > 0:
                    price_change = ((new_price - old_price) / old_price) * 100
                    trends['price_change_percent'] = price_change
                    
                    old_trend = trends['trend_direction']
                    if price_change > Decimal('1'):
                        trends['trend_direction'] = 'bullish'
                    elif price_change < Decimal('-1'):
                        trends['trend_direction'] = 'bearish'
                    else:
                        trends['trend_direction'] = 'neutral'
                    
                    if old_trend != trends['trend_direction']:
                        self.logger.info(
                            f"[PRICE TREND] Trend changed for {token_symbol}: "
                            f"{old_trend} → {trends['trend_direction']} "
                            f"({price_change:+.2f}%)"
                        )
                
                trends['last_updated'] = market_context.timestamp
                
                # Clean up old 24h data
                time_diff = timezone.now() - trends['last_updated']
                if time_diff > timedelta(hours=24):
                    self.logger.info(
                        f"[PRICE TREND] Resetting 24h data for {token_symbol}"
                    )
                    trends['highest_price_24h'] = new_price
                    trends['lowest_price_24h'] = new_price
                    trends['data_points'] = 1
            
            # Track volatility
            if token_symbol not in self.volatility_tracker:
                self.volatility_tracker[token_symbol] = []
            
            self.volatility_tracker[token_symbol].append(market_context.volatility)
            
            # Keep only last 50 readings
            if len(self.volatility_tracker[token_symbol]) > 50:
                self.volatility_tracker[token_symbol].pop(0)
            
            # Calculate average volatility
            if len(self.volatility_tracker[token_symbol]) > 0:
                avg_volatility = sum(
                    self.volatility_tracker[token_symbol]
                ) / len(self.volatility_tracker[token_symbol])
                
                if token_symbol in self.price_trends:
                    old_avg = self.price_trends[token_symbol].get(
                        'average_volatility',
                        Decimal('0')
                    )
                    self.price_trends[token_symbol]['average_volatility'] = avg_volatility
                    
                    if abs(avg_volatility - old_avg) > Decimal('0.05'):
                        self.logger.info(
                            f"[VOLATILITY] Significant change for {token_symbol}: "
                            f"{old_avg:.2%} → {avg_volatility:.2%}"
                        )
            
            # Level 10 AI learning
            if self.intel_level == 10:
                if not hasattr(self, 'ml_training_data'):
                    self.ml_training_data = []
                
                ml_features = {
                    'timestamp': market_context.timestamp.isoformat(),
                    'token_symbol': token_symbol,
                    'price': float(market_context.current_price),
                    'volatility': float(market_context.volatility),
                    'volume_24h': float(market_context.volume_24h),
                    'liquidity': float(market_context.liquidity_usd),
                    'gas_price': float(market_context.gas_price_gwei),
                    'mev_threat': float(market_context.mev_threat_level),
                    'trend': market_context.trend
                }
                
                self.ml_training_data.append(ml_features)
                
                if len(self.ml_training_data) > 1000:
                    self.ml_training_data.pop(0)
            
            # Log update for aggressive levels
            if self.intel_level >= 7:
                trend_data = self.price_trends.get(token_symbol, {})
                self.logger.debug(
                    f"[MARKET CONTEXT] ✅ Updated {token_symbol}: "
                    f"Price=${market_context.current_price:.2f}, "
                    f"Trend={trend_data.get('trend_direction', 'unknown')}, "
                    f"Vol={market_context.volatility:.2%}"
                )
            
            self.logger.info(
                f"[MARKET CONTEXT] Successfully updated context for {token_symbol}"
            )
            
        except Exception as e:
            self.logger.error(
                f"[MARKET CONTEXT] ❌ Failed to update context for "
                f"{market_context.token_symbol if hasattr(market_context, 'token_symbol') else 'UNKNOWN'}: {e}",
                exc_info=True
            )
            return

    def get_price_trend(self, token_symbol: str) -> Dict[str, Any]:
        """Get current price trend for a token."""
        try:
            if hasattr(self, 'price_trends') and token_symbol in self.price_trends:
                trend = self.price_trends[token_symbol].copy()
                self.logger.debug(
                    f"[PRICE TREND] Retrieved trend for {token_symbol}: "
                    f"{trend.get('trend_direction', 'unknown')}"
                )
                return trend
            else:
                self.logger.warning(
                    f"[PRICE TREND] No trend data available for {token_symbol}"
                )
                return {}
        except Exception as e:
            self.logger.error(
                f"[PRICE TREND] Error retrieving trend for {token_symbol}: {e}",
                exc_info=True
            )
            return {}

    def get_market_history(
        self,
        token_symbol: str,
        limit: int = 10
    ) -> List[MarketContext]:
        """Get recent market context history for a token."""
        try:
            if hasattr(self, 'market_history') and token_symbol in self.market_history:
                history = list(reversed(self.market_history[token_symbol][-limit:]))
                self.logger.debug(
                    f"[MARKET HISTORY] Retrieved {len(history)} contexts for {token_symbol}"
                )
                return history
            else:
                self.logger.warning(
                    f"[MARKET HISTORY] No history available for {token_symbol}"
                )
                return []
        except Exception as e:
            self.logger.error(
                f"[MARKET HISTORY] Error retrieving history for {token_symbol}: {e}",
                exc_info=True
            )
            return []

    def get_average_volatility(self, token_symbol: str) -> Decimal:
        """Get average volatility for a token."""
        try:
            if hasattr(self, 'price_trends') and token_symbol in self.price_trends:
                avg_vol = self.price_trends[token_symbol].get(
                    'average_volatility',
                    Decimal('0')
                )
                self.logger.debug(
                    f"[VOLATILITY] Average for {token_symbol}: {avg_vol:.2%}"
                )
                return avg_vol
            else:
                self.logger.warning(
                    f"[VOLATILITY] No volatility data for {token_symbol}"
                )
                return Decimal('0')
        except Exception as e:
            self.logger.error(
                f"[VOLATILITY] Error retrieving volatility for {token_symbol}: {e}",
                exc_info=True
            )
            return Decimal('0')

    def clear_market_history(self, token_symbol: Optional[str] = None) -> None:
        """Clear market history for a token or all tokens."""
        try:
            if token_symbol:
                cleared_items = []
                if hasattr(self, 'market_history') and token_symbol in self.market_history:
                    count = len(self.market_history[token_symbol])
                    self.market_history[token_symbol] = []
                    cleared_items.append(f"{count} contexts")
                
                if hasattr(self, 'price_trends') and token_symbol in self.price_trends:
                    del self.price_trends[token_symbol]
                    cleared_items.append("price trends")
                
                if hasattr(self, 'volatility_tracker') and token_symbol in self.volatility_tracker:
                    self.volatility_tracker[token_symbol] = []
                    cleared_items.append("volatility data")
                
                if cleared_items:
                    self.logger.info(
                        f"[MARKET CONTEXT] Cleared {', '.join(cleared_items)} for {token_symbol}"
                    )
            else:
                if hasattr(self, 'market_history'):
                    self.market_history = {}
                if hasattr(self, 'price_trends'):
                    self.price_trends = {}
                if hasattr(self, 'volatility_tracker'):
                    self.volatility_tracker = {}
                if hasattr(self, 'ml_training_data'):
                    ml_count = len(self.ml_training_data)
                    self.ml_training_data = []
                    self.logger.info(
                        f"[AI LEARNING] Cleared {ml_count} ML training samples"
                    )
                
                self.logger.info("[MARKET CONTEXT] Cleared all history")
        except Exception as e:
            self.logger.error(
                f"[MARKET CONTEXT] Error clearing history: {e}",
                exc_info=True
            )

    def get_ml_training_data(self) -> List[Dict[str, Any]]:
        """Get ML training data for Level 10 AI learning."""
        try:
            if self.intel_level != 10:
                self.logger.warning(
                    f"[AI LEARNING] ML data only available at Level 10 "
                    f"(current: {self.intel_level})"
                )
                return []
            
            if hasattr(self, 'ml_training_data'):
                self.logger.info(
                    f"[AI LEARNING] Retrieved {len(self.ml_training_data)} samples"
                )
                return self.ml_training_data.copy()
            else:
                self.logger.warning("[AI LEARNING] No ML training data yet")
                return []
        except Exception as e:
            self.logger.error(
                f"[AI LEARNING] Error retrieving ML data: {e}",
                exc_info=True
            )
            return []

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def get_risk_threshold(self) -> float:
        """Get dynamic risk threshold based on intelligence level."""
        try:
            base_threshold = (self.intel_level * 10) - 10
            configured_threshold = float(self.config.risk_tolerance)
            blended_threshold = (configured_threshold * 0.7) + (base_threshold * 0.3)
            
            if len(self.historical_decisions) > 5:
                recent_wins = sum(
                    1 for d in self.historical_decisions[-10:]
                    if d.opportunity_score > d.risk_score
                )
                win_rate = recent_wins / min(10, len(self.historical_decisions))
                performance_adjustment = (win_rate - 0.5) * 20
                blended_threshold += performance_adjustment
            
            final_threshold = max(10.0, min(95.0, blended_threshold))
            
            self.logger.debug(
                f"[THRESHOLD] Risk threshold: {final_threshold:.1f}% "
                f"(Level {self.intel_level})"
            )
            
            return final_threshold
        except Exception as e:
            self.logger.error(
                f"[THRESHOLD] Error calculating risk threshold: {e}",
                exc_info=True
            )
            return 50.0

    async def cleanup(self):
        """Cleanup resources when done."""
        try:
            await self.price_service.close()
            self.logger.info("[INTEL] Engine cleanup complete")
        except Exception as e:
            self.logger.error(f"[INTEL] Error during cleanup: {e}", exc_info=True)