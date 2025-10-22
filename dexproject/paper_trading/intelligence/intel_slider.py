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

File: dexproject/paper_trading/intelligence/intel_slider.py
"""

import logging
import uuid
import asyncio
from decimal import Decimal
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass

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
        cutoff_time = datetime.now() - timedelta(minutes=period_minutes)
        
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
        name="Balanced - Default",
        description="Equal weight to risk and opportunity",
        risk_tolerance=Decimal('50'),
        max_position_percent=Decimal('10'),
        min_confidence_required=Decimal('65'),
        min_position_usd=Decimal('50'),
        use_mev_protection=True,
        gas_aggressiveness="adaptive",
        trade_frequency="moderate",
        decision_speed="moderate"
    ),
    6: IntelLevelConfig(
        level=6,
        name="Moderately Aggressive",
        description="Balanced but seeking opportunities",
        risk_tolerance=Decimal('60'),
        max_position_percent=Decimal('12'),
        min_confidence_required=Decimal('55'),
        min_position_usd=Decimal('60'),
        use_mev_protection=False,  # Only when needed
        gas_aggressiveness="adaptive",
        trade_frequency="moderate_high",
        decision_speed="fast"
    ),
    7: IntelLevelConfig(
        level=7,
        name="Aggressive - Opportunity Seeker",
        description="Actively pursues opportunities, accepts risks",
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
# INTEL SLIDER ENGINE - MAIN CLASS
# =============================================================================

class IntelSliderEngine(IntelligenceEngine):
    """
    Intelligence engine controlled by the Intel slider with REAL data integration.
    
    This engine adapts its behavior based on the selected intelligence level,
    providing a simple interface for users while handling complex decision-making
    internally. Now integrates with real token prices and market data.
    
    New Features:
    - Fetches real token prices from Alchemy/CoinGecko APIs
    - Tracks price history for trend analysis
    - Makes price-aware trading decisions (buy low, sell high)
    - Calculates position sizes with real USD/token conversions
    - Adjusts risk assessment based on price volatility
    
    Example:
        engine = IntelSliderEngine(intel_level=5, chain_id=84532)
        context = await engine.analyze_market('0x...', trade_size_usd=Decimal('100'))
        decision = await engine.make_decision(context, account_balance, [], '0x...', 'WETH')
    """
    
    def __init__(
        self, 
        intel_level: int = 5, 
        account_id: Optional[str] = None, 
        strategy_config=None,
        chain_id: int = 84532
    ):
        """
        Initialize the Intel Slider engine with real data support.
        
        Args:
            intel_level: Intelligence level (1-10)
            account_id: Optional paper trading account ID
            strategy_config: Optional PaperStrategyConfiguration to override defaults
            chain_id: Blockchain network ID for price feeds (default: Base Sepolia)
        """
        super().__init__(intel_level)
        self.config = INTEL_CONFIGS[intel_level]
        self.account_id = account_id
        self.chain_id = chain_id
        
        # Initialize market analyzer
        self.analyzer = CompositeMarketAnalyzer()
        
        # Initialize type converters
        self.converter = TypeConverter()
        self.normalizer = MarketDataNormalizer()
        
        # =====================================================================
        # REAL DATA INTEGRATION - Price Feed Service
        # =====================================================================
        # Initialize price feed service for fetching real token prices
        self.price_service = PriceFeedService(chain_id=chain_id)
        
        # Price history tracking for trend analysis
        # Key: token_address -> PriceHistory object
        self.price_history: Dict[str, PriceHistory] = {}
        
        # Cache for recent price fetches (avoid API spam)
        self.price_cache: Dict[str, tuple[Decimal, datetime]] = {}
        self.price_cache_ttl = 30  # seconds
        
        logger.info(
            f"[INTEL] Initialized with REAL data integration: "
            f"Chain={chain_id}, Price feeds enabled"
        )
        
        # =====================================================================
        # CONFIGURATION OVERRIDES from database
        # =====================================================================
        if strategy_config:
            logger.info(
                f"[CONFIG] Applying database configuration overrides: "
                f"{strategy_config.name}"
            )
            
            # Override confidence threshold from HTML slider
            if strategy_config.confidence_threshold:
                self.config.min_confidence_required = Decimal(
                    str(strategy_config.confidence_threshold)
                )
                logger.info(
                    f"[CONFIG] Confidence threshold set to: "
                    f"{self.config.min_confidence_required}%"
                )
            
            # Override max position size from HTML slider
            if strategy_config.max_position_size_percent:
                self.config.max_position_percent = Decimal(
                    str(strategy_config.max_position_size_percent)
                )
                logger.info(
                    f"[CONFIG] Max position size set to: "
                    f"{self.config.max_position_percent}%"
                )
            
            # Override risk tolerance based on trading mode
            if strategy_config.trading_mode == 'CONSERVATIVE':
                self.config.risk_tolerance = Decimal('30')
                logger.info(
                    "[CONFIG] Risk tolerance set to CONSERVATIVE: 30%"
                )
            elif strategy_config.trading_mode == 'AGGRESSIVE':
                self.config.risk_tolerance = Decimal('70')
                logger.info(
                    "[CONFIG] Risk tolerance set to AGGRESSIVE: 70%"
                )
            elif strategy_config.trading_mode == 'MODERATE':
                self.config.risk_tolerance = Decimal('50')
                logger.info(
                    "[CONFIG] Risk tolerance set to MODERATE: 50%"
                )
            
            # Override stop loss if provided
            if strategy_config.stop_loss_percent:
                stop_loss = Decimal(str(strategy_config.stop_loss_percent))
                logger.info(f"[CONFIG] Stop loss set to: {stop_loss}%")
            
            # Override max daily trades
            if strategy_config.max_daily_trades:
                logger.info(
                    f"[CONFIG] Max daily trades set to: "
                    f"{strategy_config.max_daily_trades}"
                )
        
        # Learning system data (for level 10)
        self.historical_decisions: List[TradingDecision] = []
        self.performance_history: List[Dict[str, Any]] = []
        
        self.logger.info(
            f"Intel Slider Engine initialized: Level {intel_level} - "
            f"{self.config.name}"
        )
    
    # =========================================================================
    # REAL PRICE FETCHING METHODS
    # =========================================================================
    
    async def _get_token_price(
        self,
        token_address: str,
        token_symbol: str
    ) -> Optional[Decimal]:
        """
        Fetch REAL token price from APIs with caching.
        
        This method fetches live token prices from Alchemy (primary) and
        CoinGecko (fallback) APIs. Prices are cached for 30 seconds to
        reduce API calls.
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol (e.g., 'WETH', 'USDC')
            
        Returns:
            Token price in USD, or None if fetch fails
            
        Example:
            price = await engine._get_token_price('0x...', 'WETH')
            # Returns: Decimal("2543.50")
        """
        try:
            # ================================================================
            # STEP 1: Check cache first
            # ================================================================
            cache_key = f"{token_address.lower()}_{token_symbol}"
            
            if cache_key in self.price_cache:
                cached_price, cached_time = self.price_cache[cache_key]
                age = (datetime.now() - cached_time).total_seconds()
                
                if age < self.price_cache_ttl:
                    logger.debug(
                        f"[PRICE] Cache hit for {token_symbol}: "
                        f"${cached_price:.2f} (age: {age:.0f}s)"
                    )
                    return cached_price
            
            # ================================================================
            # STEP 2: Fetch real price from APIs
            # ================================================================
            logger.info(
                f"[PRICE] Fetching real price for {token_symbol} "
                f"from APIs..."
            )
            
            price = await self.price_service.get_token_price(
                token_address,
                token_symbol
            )
            
            if price is None:
                logger.error(
                    f"[PRICE] Failed to fetch price for {token_symbol}"
                )
                return None
            
            # ================================================================
            # STEP 3: Cache the price
            # ================================================================
            self.price_cache[cache_key] = (price, datetime.now())
            
            # ================================================================
            # STEP 4: Update price history for trend analysis
            # ================================================================
            self._update_price_history(
                token_address,
                token_symbol,
                price
            )
            
            logger.info(
                f"[PRICE] ✅ Real price fetched for {token_symbol}: "
                f"${price:.2f}"
            )
            
            return price
            
        except Exception as e:
            logger.error(
                f"[PRICE] Error fetching price for {token_symbol}: {e}",
                exc_info=True
            )
            return None
    
    def _update_price_history(
        self,
        token_address: str,
        token_symbol: str,
        price: Decimal
    ) -> None:
        """
        Update price history for trend analysis.
        
        Maintains a rolling window of recent prices to detect trends
        (upward, downward, or sideways movement).
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            price: Current price to add to history
        """
        try:
            # Create history object if doesn't exist
            if token_address not in self.price_history:
                self.price_history[token_address] = PriceHistory(
                    token_address=token_address,
                    token_symbol=token_symbol,
                    prices=[],
                    timestamps=[]
                )
            
            history = self.price_history[token_address]
            
            # Add new price and timestamp
            history.prices.append(price)
            history.timestamps.append(datetime.now())
            
            # Keep only last 100 prices (rolling window)
            if len(history.prices) > 100:
                history.prices = history.prices[-100:]
                history.timestamps = history.timestamps[-100:]
            
            logger.debug(
                f"[PRICE HISTORY] Updated for {token_symbol}: "
                f"{len(history.prices)} prices tracked"
            )
            
        except Exception as e:
            logger.error(
                f"[PRICE HISTORY] Error updating for {token_symbol}: {e}"
            )
    
    def _get_price_trend(self, token_address: str) -> str:
        """
        Analyze price trend from history.
        
        Args:
            token_address: Token contract address
            
        Returns:
            'bullish', 'bearish', or 'neutral'
        """
        if token_address not in self.price_history:
            return 'neutral'
        
        history = self.price_history[token_address]
        
        if history.is_trending_up():
            return 'bullish'
        elif history.is_trending_down():
            return 'bearish'
        else:
            return 'neutral'
    
    # =========================================================================
    # MARKET ANALYSIS WITH REAL PRICES
    # =========================================================================
    
    async def analyze_market(
        self,
        token_address: str,
        **kwargs
    ) -> MarketContext:
        """
        Analyze market conditions with REAL price data.
        
        This method combines comprehensive market analysis with live token
        prices to provide a complete picture of trading conditions.
        
        Args:
            token_address: Token to analyze
            **kwargs: Additional parameters including:
                - trade_size_usd: Size of trade in USD
                - liquidity_usd: Pool liquidity
                - volume_24h: 24-hour volume
                - token_symbol: Token symbol
            
        Returns:
            Market context with real price data and intel-level adjustments
            
        Example:
            context = await engine.analyze_market(
                '0x...',
                trade_size_usd=Decimal('100'),
                token_symbol='WETH'
            )
        """
        try:
            # =================================================================
            # STEP 1: Fetch REAL token price
            # =================================================================
            token_symbol = kwargs.get('token_symbol', 'UNKNOWN')
            
            logger.info(
                f"[MARKET ANALYSIS] Starting analysis for {token_symbol}..."
            )
            
            # Fetch current token price from APIs
            current_price = await self._get_token_price(
                token_address,
                token_symbol
            )
            
            if current_price is None:
                logger.warning(
                    f"[MARKET ANALYSIS] Failed to fetch price for "
                    f"{token_symbol}, using fallback"
                )
                # Fallback: use a default price if API fails
                current_price = Decimal('1.00')
            
            # =================================================================
            # STEP 2: Get comprehensive market analysis
            # =================================================================
            analysis = await self.analyzer.analyze_comprehensive(
                token_address=token_address,
                trade_size_usd=kwargs.get('trade_size_usd', Decimal('1000')),
                liquidity_usd=kwargs.get('liquidity_usd', Decimal('100000')),
                volume_24h=kwargs.get('volume_24h', Decimal('50000'))
            )
            
            # =================================================================
            # STEP 3: Get price trend from history
            # =================================================================
            price_trend = self._get_price_trend(token_address)
            
            # Calculate price change if we have history
            price_change_1h = None
            if token_address in self.price_history:
                price_change_1h = self.price_history[token_address].get_price_change_percent(60)
            
            logger.info(
                f"[MARKET ANALYSIS] Price data: "
                f"Current=${current_price:.2f}, "
                f"Trend={price_trend}, "
                f"Change(1h)={price_change_1h:.2f}% if price_change_1h else 'N/A'"
            )
            
            # =================================================================
            # STEP 4: Convert to MarketContext with type safety
            # =================================================================
            # Calculate price 24h ago from history if available
            price_24h_ago = current_price  # Default to current
            if token_address in self.price_history:
                change_24h = self.price_history[token_address].get_price_change_percent(1440)  # 24 hours
                if change_24h:
                    price_24h_ago = current_price / (Decimal('1') + (change_24h / Decimal('100')))
            
            context = MarketContext(
                # =============================================================
                # REQUIRED PARAMETERS (must come first)
                # =============================================================
                token_symbol=token_symbol,
                token_address=token_address,
                current_price=current_price,
                price_24h_ago=price_24h_ago,
                volume_24h=kwargs.get('volume_24h', Decimal('50000')),
                liquidity_usd=self.converter.to_decimal(
                    analysis['liquidity']['pool_liquidity_usd']
                ),
                holder_count=kwargs.get('holder_count', 1000),
                market_cap=kwargs.get('market_cap', current_price * Decimal('1000000')),  # Estimate
                volatility=self.converter.to_decimal(
                    analysis['market_state']['volatility_index']
                ),
                trend=price_trend,  # 'bullish', 'bearish', 'neutral'
                momentum=price_change_1h or Decimal('0'),
                support_levels=kwargs.get('support_levels', []),
                resistance_levels=kwargs.get('resistance_levels', []),
                
                # =============================================================
                # Gas and network data
                # =============================================================
                gas_price_gwei=self.converter.to_decimal(
                    analysis['gas_analysis']['current_gas_gwei']
                ),
                network_congestion=analysis['gas_analysis']['network_congestion'],
                pending_tx_count=analysis['gas_analysis']['pending_tx_count'],
                
                # =============================================================
                # MEV protection data
                # =============================================================
                mev_threat_level=analysis['mev_analysis']['threat_level'],
                sandwich_risk=analysis['mev_analysis']['sandwich_risk'],
                frontrun_probability=analysis['mev_analysis']['frontrun_probability'],
                
                # =============================================================
                # Competition data
                # =============================================================
                competing_bots_detected=analysis['competition']['competing_bots'],
                average_bot_gas_price=self.converter.to_decimal(
                    analysis['competition']['avg_bot_gas']
                ),
                bot_success_rate=analysis['competition']['bot_success_rate'],
                
                # =============================================================
                # Liquidity data
                # =============================================================
                pool_liquidity_usd=self.converter.to_decimal(
                    analysis['liquidity']['pool_liquidity_usd']
                ),
                expected_slippage=self.converter.to_decimal(
                    analysis['liquidity']['expected_slippage']
                ),
                liquidity_depth_score=analysis['liquidity']['liquidity_depth_score'],
                
                # =============================================================
                # Market state data
                # =============================================================
                volatility_index=analysis['market_state']['volatility_index'],
                chaos_event_detected=analysis['market_state']['chaos_event_detected'],
                trend_direction=analysis['market_state']['trend_direction'],
                volume_24h_change=self.converter.to_decimal(
                    analysis['market_state']['volume_24h_change']
                ),
                
                # =============================================================
                # Historical performance
                # =============================================================
                recent_failures=kwargs.get('recent_failures', 0),
                success_rate_1h=kwargs.get('success_rate_1h', 50.0),
                average_profit_1h=kwargs.get('average_profit_1h', Decimal('0')),
                
                # =============================================================
                # Timestamp and confidence
                # =============================================================
                timestamp=datetime.now(),
                confidence_in_data=kwargs.get('confidence_in_data', 80.0)
            )
            
            # =================================================================
            # STEP 5: Normalize all numeric fields
            # =================================================================
            context = self.normalizer.normalize_context(context)
            
            # =================================================================
            # STEP 6: Adjust perception based on intel level
            # =================================================================
            context = self._adjust_market_perception(context)
            
            logger.info(
                f"[MARKET ANALYSIS] ✅ Complete for {token_symbol}: "
                f"Risk={context.mev_threat_level:.0f}, "
                f"Liquidity={context.liquidity_depth_score:.0f}, "
                f"Trend={context.trend_direction}"
            )
            
            return context
            
        except Exception as e:
            logger.error(
                f"[MARKET ANALYSIS] Error analyzing market: {e}",
                exc_info=True
            )
            raise
    
    def _adjust_market_perception(self, context: MarketContext) -> MarketContext:
        """
        Adjust market perception based on intel level.
        
        Lower intel levels are more pessimistic (see more risk), while
        higher levels are more optimistic (see more opportunity).
        
        Args:
            context: Market context to adjust
            
        Returns:
            Adjusted market context
        """
        if self.intel_level <= 3:
            # ================================================================
            # CAUTIOUS LEVELS (1-3): Amplify risks, reduce confidence
            # ================================================================
            context.mev_threat_level = self.converter.safe_multiply(
                context.mev_threat_level,
                Decimal('1.3')
            )
            context.sandwich_risk = self.converter.safe_multiply(
                context.sandwich_risk,
                Decimal('1.3')
            )
            context.volatility_index = self.converter.safe_multiply(
                context.volatility_index,
                Decimal('1.2')
            )
            context.confidence_in_data = self.converter.safe_multiply(
                context.confidence_in_data,
                Decimal('0.8')
            )
            
            logger.debug(
                f"[PERCEPTION] Cautious adjustment applied (Level {self.intel_level})"
            )
            
        elif self.intel_level >= 7:
            # ================================================================
            # AGGRESSIVE LEVELS (7-10): Downplay risks, boost confidence
            # ================================================================
            context.mev_threat_level = self.converter.safe_multiply(
                context.mev_threat_level,
                Decimal('0.8')
            )
            context.sandwich_risk = self.converter.safe_multiply(
                context.sandwich_risk,
                Decimal('0.8')
            )
            context.volatility_index = self.converter.safe_multiply(
                context.volatility_index,
                Decimal('0.9')
            )
            context.confidence_in_data = self.converter.safe_multiply(
                context.confidence_in_data,
                Decimal('1.1')
            )
            
            logger.debug(
                f"[PERCEPTION] Aggressive adjustment applied (Level {self.intel_level})"
            )
        
        return context
    
    # =========================================================================
    # DECISION MAKING WITH REAL PRICES
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
        Make trading decision based on intel level and REAL price data.
        
        This method analyzes market conditions, real token prices, and price
        trends to make intelligent trading decisions aligned with the selected
        intelligence level.
        
        Args:
            market_context: Current market conditions (with real prices)
            account_balance: Available balance in USD
            existing_positions: Current open positions
            token_address: Token contract address
            token_symbol: Token symbol (e.g., 'WETH')
            
        Returns:
            Complete trading decision with action, sizing, and reasoning
            
        Example:
            decision = await engine.make_decision(
                context,
                Decimal('1000.00'),
                [],
                '0x...',
                'WETH'
            )
            print(f"Action: {decision.action}")  # BUY, SELL, HOLD, SKIP
            print(f"Amount: ${decision.position_size_usd}")
        """
        try:
            # Ensure account_balance is Decimal
            account_balance = self.converter.to_decimal(account_balance)
            
            logger.info(
                f"[DECISION] Making decision for {token_symbol}: "
                f"Intel Level={self.intel_level}, "
                f"Balance=${account_balance:.2f}"
            )
            
            # =================================================================
            # STEP 1: Calculate risk score
            # =================================================================
            risk_score = self._calculate_risk_score(market_context)
            logger.info(f"[DECISION] Risk score: {risk_score:.2f}/100")
            
            # =================================================================
            # STEP 2: Calculate opportunity score WITH PRICE AWARENESS
            # =================================================================
            opportunity_score = self._calculate_opportunity_score_with_price(
                market_context,
                token_address,
                existing_positions
            )
            logger.info(f"[DECISION] Opportunity score: {opportunity_score:.2f}/100")
            
            # =================================================================
            # STEP 3: Calculate confidence score
            # =================================================================
            confidence_score = self._calculate_confidence_score(
                market_context,
                risk_score,
                opportunity_score
            )
            logger.info(f"[DECISION] Confidence score: {confidence_score:.2f}/100")
            
            # =================================================================
            # STEP 4: Determine action (BUY, SELL, HOLD, SKIP)
            # =================================================================
            action = self._determine_action(
                risk_score,
                opportunity_score,
                confidence_score
            )
            logger.info(f"[DECISION] Action determined: {action}")
            
            # =================================================================
            # STEP 5: Calculate position size with REAL price
            # =================================================================
            if action in ['BUY', 'SELL']:
                position_size_percent = self._calculate_position_size(
                    confidence_score,
                    risk_score,
                    account_balance
                )
                position_size_usd = self.converter.safe_percentage(
                    account_balance,
                    position_size_percent
                )
                
                # Calculate actual token quantity using real price
                if hasattr(market_context, 'current_price') and market_context.current_price:
                    token_quantity = position_size_usd / market_context.current_price
                else:
                    token_quantity = Decimal('0')
                
                logger.info(
                    f"[DECISION] Position sizing: "
                    f"{position_size_percent:.2f}% = ${position_size_usd:.2f} = "
                    f"{token_quantity:.6f} {token_symbol}"
                )
            else:
                position_size_usd = Decimal('0')
                token_quantity = Decimal('0')
            
            # =================================================================
            # STEP 6: Determine execution strategy
            # =================================================================
            execution_strategy = self._determine_execution_strategy(
                market_context,
                action
            )
            
            # =================================================================
            # STEP 7: Calculate stop loss and take profit targets
            # =================================================================
            stop_loss_percent = self._calculate_stop_loss(risk_score)
            take_profit_targets = self._calculate_take_profits(opportunity_score)
            
            # =================================================================
            # STEP 8: Generate detailed reasoning
            # =================================================================
            reasoning = self._generate_reasoning(
                action,
                risk_score,
                opportunity_score,
                confidence_score,
                market_context
            )
            
            # =================================================================
            # STEP 9: Identify risk and opportunity factors
            # =================================================================
            risk_factors = self._identify_risk_factors(market_context)
            opportunity_factors = self._identify_opportunity_factors(market_context)
            mitigation_strategies = self._generate_mitigation_strategies(market_context)
            
            # =================================================================
            # STEP 10: Assess time sensitivity
            # =================================================================
            time_sensitivity = self._assess_time_sensitivity(market_context)
            max_execution_time_ms = self._calculate_max_execution_time()
            
            # =================================================================
            # STEP 11: Create trading decision object
            # =================================================================
            decision = TradingDecision(
                decision_id=str(uuid.uuid4()),
                timestamp=datetime.now(),
                action=action,
                confidence_score=confidence_score,
                risk_score=risk_score,
                opportunity_score=opportunity_score,
                position_size_usd=position_size_usd,
                token_quantity=token_quantity,
                stop_loss_percent=stop_loss_percent,
                take_profit_targets=take_profit_targets,
                execution_strategy=execution_strategy,
                reasoning=reasoning,
                intel_level=self.intel_level,
                risk_factors=risk_factors,
                opportunity_factors=opportunity_factors,
                mitigation_strategies=mitigation_strategies,
                time_sensitivity=time_sensitivity,
                max_execution_time_ms=max_execution_time_ms,
                # Add price-related metadata
                metadata={
                    'token_price': float(market_context.current_price) if hasattr(market_context, 'current_price') else None,
                    'price_trend': market_context.trend if hasattr(market_context, 'trend') else None,
                    'price_change_1h': float(market_context.momentum) if hasattr(market_context, 'momentum') else None,
                    'token_symbol': token_symbol,
                    'token_address': token_address
                }
            )
            
            # =================================================================
            # STEP 12: Store decision in history (for level 10 learning)
            # =================================================================
            self.historical_decisions.append(decision)
            
            # Keep only last 1000 decisions
            if len(self.historical_decisions) > 1000:
                self.historical_decisions = self.historical_decisions[-1000:]
            
            logger.info(
                f"[DECISION] ✅ Decision complete: {action} "
                f"${position_size_usd:.2f} with {confidence_score:.1f}% confidence"
            )
            
            return decision
            
        except Exception as e:
            logger.error(
                f"[DECISION] Error making decision: {e}",
                exc_info=True
            )
            raise
    
    # =========================================================================
    # SCORING METHODS WITH PRICE AWARENESS
    # =========================================================================
    
    def _calculate_opportunity_score_with_price(
        self,
        context: MarketContext,
        token_address: str,
        existing_positions: List[Dict[str, Any]]
    ) -> Decimal:
        """
        Calculate opportunity score considering REAL price trends.
        
        This method evaluates trading opportunities by analyzing:
        1. Market conditions (liquidity, volume, trend)
        2. Price trends (is it going up or down?)
        3. Price momentum (fast or slow movement?)
        4. Existing positions (already invested?)
        
        Args:
            context: Market context with price data
            token_address: Token being analyzed
            existing_positions: Current open positions
            
        Returns:
            Opportunity score (0-100)
        """
        context = self.normalizer.normalize_context(context)
        
        # =================================================================
        # BASE OPPORTUNITY SCORE from market conditions
        # =================================================================
        # Liquidity component (30% weight)
        liquidity_score = self.converter.safe_multiply(
            self.converter.to_decimal(
                context.liquidity_depth_score,
                Decimal('50')
            ),
            Decimal('0.30')
        )
        
        # Volume component (20% weight)
        volume_factor = min(
            self.converter.to_decimal(context.volume_24h_change, Decimal('0')) / Decimal('100'),
            Decimal('1.0')
        )
        volume_score = self.converter.safe_multiply(volume_factor * Decimal('100'), Decimal('0.20'))
        
        # Trend component (20% weight)
        if context.trend_direction == 'bullish':
            trend_score = Decimal('20')
        elif context.trend_direction == 'bearish':
            trend_score = Decimal('5')
        else:
            trend_score = Decimal('10')
        
        # Competition component (15% weight) - inverse
        competition_factor = max(
            Decimal('0'),
            Decimal('100') - self.converter.to_decimal(
                context.competing_bots_detected,
                Decimal('0')
            ) * Decimal('10')
        )
        competition_score = self.converter.safe_multiply(competition_factor, Decimal('0.15'))
        
        # Network conditions (15% weight) - inverse congestion
        network_factor = max(
            Decimal('0'),
            Decimal('100') - self.converter.to_decimal(
                context.network_congestion,
                Decimal('50')
            )
        )
        network_score = self.converter.safe_multiply(network_factor, Decimal('0.15'))
        
        base_score = (
            liquidity_score +
            volume_score +
            trend_score +
            competition_score +
            network_score
        )
        
        # =================================================================
        # PRICE TREND ADJUSTMENT (NEW!)
        # =================================================================
        price_adjustment = Decimal('0')
        
        # Get price trend from history
        if token_address in self.price_history:
            history = self.price_history[token_address]
            
            # Bullish trend bonus
            if history.is_trending_up():
                price_adjustment += Decimal('15')  # +15 points for uptrend
                logger.debug("[OPPORTUNITY] +15 points for bullish price trend")
            
            # Bearish trend penalty
            elif history.is_trending_down():
                price_adjustment -= Decimal('10')  # -10 points for downtrend
                logger.debug("[OPPORTUNITY] -10 points for bearish price trend")
            
            # Price momentum bonus (fast changes = more opportunity)
            price_change_1h = history.get_price_change_percent(60)
            if price_change_1h:
                if price_change_1h > 5:  # >5% gain in 1 hour
                    price_adjustment += Decimal('10')
                    logger.debug(
                        f"[OPPORTUNITY] +10 points for strong momentum "
                        f"({price_change_1h:.1f}%)"
                    )
                elif price_change_1h < -5:  # >5% loss in 1 hour
                    price_adjustment -= Decimal('10')
                    logger.debug(
                        f"[OPPORTUNITY] -10 points for negative momentum "
                        f"({price_change_1h:.1f}%)"
                    )
        
        # =================================================================
        # EXISTING POSITION ADJUSTMENT
        # =================================================================
        # Penalty for duplicate positions (diversification)
        has_position = any(
            pos.get('token_address', '').lower() == token_address.lower()
            for pos in existing_positions
        )
        
        if has_position:
            price_adjustment -= Decimal('20')  # -20 points for duplicate
            logger.debug("[OPPORTUNITY] -20 points for existing position")
        
        # =================================================================
        # FINAL OPPORTUNITY SCORE
        # =================================================================
        final_score = base_score + price_adjustment
        
        # Cap at 0-100 range
        final_score = max(Decimal('0'), min(Decimal('100'), final_score))
        
        logger.debug(
            f"[OPPORTUNITY] Score breakdown: "
            f"Base={base_score:.1f}, Price={price_adjustment:+.1f}, "
            f"Final={final_score:.1f}"
        )
        
        return final_score.quantize(Decimal('0.01'))
    
    def _calculate_risk_score(self, context: MarketContext) -> Decimal:
        """
        Calculate comprehensive risk score from market conditions.
        
        Args:
            context: Market context
            
        Returns:
            Risk score (0-100, higher = more risky)
        """
        context = self.normalizer.normalize_context(context)
        
        # MEV risk (30% weight)
        mev_risk = self.converter.safe_multiply(
            self.converter.to_decimal(context.mev_threat_level, Decimal('0')),
            Decimal('0.30')
        )
        
        # Volatility risk (25% weight)
        volatility_risk = self.converter.safe_multiply(
            self.converter.to_decimal(context.volatility_index, Decimal('0')),
            Decimal('0.25')
        )
        
        # Liquidity risk (20% weight) - inverse
        liquidity_factor = max(
            Decimal('0'),
            Decimal('100') - self.converter.to_decimal(
                context.liquidity_depth_score,
                Decimal('100')
            )
        )
        liquidity_risk = self.converter.safe_multiply(liquidity_factor, Decimal('0.20'))
        
        # Slippage risk (15% weight)
        slippage_risk = self.converter.safe_multiply(
            min(
                self.converter.to_decimal(context.expected_slippage, Decimal('0')) * Decimal('10'),
                Decimal('100')
            ),
            Decimal('0.15')
        )
        
        # Chaos event risk (10% weight)
        chaos_risk = (
            Decimal('10') if context.chaos_event_detected 
            else Decimal('0')
        )
        
        total_risk = (
            mev_risk +
            volatility_risk +
            liquidity_risk +
            slippage_risk +
            chaos_risk
        )
        
        return min(total_risk, Decimal('100')).quantize(Decimal('0.01'))
    
    def _calculate_confidence_score(
        self,
        context: MarketContext,
        risk_score: Decimal,
        opportunity_score: Decimal
    ) -> Decimal:
        """
        Calculate overall confidence in the trading decision.
        
        Args:
            context: Market context
            risk_score: Calculated risk score
            opportunity_score: Calculated opportunity score
            
        Returns:
            Confidence score (0-100)
        """
        context = self.normalizer.normalize_context(context)
        
        # Data quality confidence (30% weight)
        data_confidence = self.converter.safe_multiply(
            self.converter.to_decimal(context.confidence_in_data, Decimal('50')),
            Decimal('0.30')
        )
        
        # Volatility confidence (30% weight) - inverse
        volatility_confidence = self.converter.safe_multiply(
            Decimal('100') - self.converter.to_decimal(context.volatility_index, Decimal('50')),
            Decimal('0.30')
        )
        
        # Liquidity confidence (20% weight)
        liquidity_confidence = self.converter.safe_multiply(
            self.converter.to_decimal(context.liquidity_depth_score, Decimal('50')),
            Decimal('0.20')
        )
        
        # Chaos confidence (20% weight)
        chaos_confidence = self.converter.safe_multiply(
            Decimal('100') if not context.chaos_event_detected else Decimal('20'),
            Decimal('0.20')
        )
        
        base_confidence = (
            data_confidence +
            volatility_confidence +
            liquidity_confidence +
            chaos_confidence
        )
        
        # Adjust for risk/opportunity balance
        if risk_score < self.config.risk_tolerance and opportunity_score > 50:
            base_confidence = self.converter.safe_multiply(base_confidence, Decimal('1.2'))
        elif risk_score > self.config.risk_tolerance:
            base_confidence = self.converter.safe_multiply(base_confidence, Decimal('0.8'))
        
        return min(base_confidence, Decimal('100')).quantize(Decimal('0.01'))
    
    def _calculate_position_size(
        self,
        confidence: Decimal,
        risk_score: Decimal,
        account_balance: Decimal
    ) -> Decimal:
        """
        Calculate position size based on confidence, risk, and account balance.
        
        Production-level implementation with proper type handling.
        
        Args:
            confidence: Overall confidence score (0-100)
            risk_score: Risk assessment score (0-100)
            account_balance: Available account balance
            
        Returns:
            Position size percentage
        """
        # Ensure all inputs are Decimals
        confidence = self.converter.to_decimal(confidence)
        risk_score = self.converter.to_decimal(risk_score)
        account_balance = self.converter.to_decimal(account_balance)
        
        if self.intel_level == 10:
            # Autonomous sizing
            return self._calculate_ml_position_size(risk_score, confidence)
        
        # Base position percentage from configuration
        base_position_percent = self.converter.to_decimal(self.config.max_position_percent)
        
        # Adjust by confidence (0.5x to 1.5x)
        confidence_multiplier = Decimal('0.5') + (confidence / Decimal('100'))
        
        # Adjust by inverse risk (high risk = smaller position)
        risk_multiplier = (Decimal('100') - risk_score) / Decimal('100')
        
        # Calculate final position size percentage
        position_percent = self.converter.safe_multiply(
            base_position_percent,
            self.converter.safe_multiply(confidence_multiplier, risk_multiplier)
        )
        
        # Apply minimum and maximum constraints
        min_position_percent = (self.converter.to_decimal(self.config.min_position_usd) / account_balance) * Decimal('100')
        max_position_percent = self.converter.to_decimal(self.config.max_position_percent)
        
        # Ensure position is within bounds
        position_percent = max(min_position_percent, min(max_position_percent, position_percent))
        
        # Round to 2 decimal places
        return position_percent.quantize(Decimal('0.01'))
    
    def _calculate_ml_confidence(
        self,
        context: MarketContext,
        risk_score: Decimal,
        opportunity_score: Decimal
    ) -> Decimal:
        """
        Calculate confidence using machine learning (Level 10).
        
        In production, this would use actual ML models.
        """
        # Simulate ML confidence based on historical patterns
        if len(self.historical_decisions) > 10:
            # Use recent performance
            recent_success = sum(
                1 for d in self.historical_decisions[-10:]
                if d.opportunity_score > d.risk_score
            )
            ml_confidence = Decimal(str(recent_success * 10))
        else:
            # Default to balanced confidence
            ml_confidence = Decimal('60')
        
        return ml_confidence
    
    def _determine_action(
        self,
        risk_score: Decimal,
        opportunity_score: Decimal,
        confidence_score: Decimal
    ) -> str:
        """Determine trading action based on scores and intel level."""
        
        # Ensure all scores are Decimals
        risk_score = self.converter.to_decimal(risk_score)
        opportunity_score = self.converter.to_decimal(opportunity_score)
        confidence_score = self.converter.to_decimal(confidence_score)
        
        # Check minimum confidence
        if confidence_score < self.config.min_confidence_required:
            return 'SKIP'
        
        # Check risk tolerance
        if risk_score > self.config.risk_tolerance:
            if self.intel_level >= 7:
                # Aggressive levels might still trade
                if opportunity_score > 70:
                    return 'BUY'
            return 'SKIP'
        
        # More aggressive opportunity assessment
        # Lower thresholds to trigger BUY/SELL more easily
        if opportunity_score > 50:  # Lowered from 60
            return 'BUY'
        elif opportunity_score < 45:  # Raised from 40
            return 'SELL' if risk_score > 50 else 'HOLD'
        else:
            # Add random factor for borderline cases
            # If confidence is high enough, sometimes trade even in neutral territory
            if confidence_score > self.config.min_confidence_required * Decimal('1.2'):
                # High confidence - make a decision
                if opportunity_score >= 47:
                    return 'BUY'
                else:
                    return 'SELL' if risk_score > 45 else 'HOLD'
            return 'HOLD'
    
    def _calculate_ml_position_size(
        self,
        risk_score: Decimal,
        opportunity_score: Decimal
    ) -> Decimal:
        """ML-based position sizing for level 10."""
        risk_score = self.converter.to_decimal(risk_score)
        opportunity_score = self.converter.to_decimal(opportunity_score)
        
        # Kelly Criterion simulation
        win_prob = opportunity_score / Decimal('100')
        loss_prob = risk_score / Decimal('100')
        
        if loss_prob > 0:
            kelly_fraction = (win_prob - loss_prob) / loss_prob
            position_size = min(kelly_fraction * Decimal('100'), Decimal('30'))
        else:
            position_size = Decimal('10')
        
        return max(position_size, Decimal('1')).quantize(Decimal('0.01'))
    
    def _determine_execution_strategy(
        self,
        context: MarketContext,
        action: str
    ) -> Dict[str, Any]:
        """Determine execution strategy based on intel level."""
        context = self.normalizer.normalize_context(context)
        
        if action in ['SKIP', 'HOLD']:
            return {
                'mode': 'NONE',
                'use_private_relay': False,
                'gas_strategy': 'standard',
                'max_gas_gwei': self.converter.to_decimal(context.gas_price_gwei)
            }
        
        # Base strategy on intel config
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
            if self.converter.to_decimal(context.network_congestion, Decimal('50')) > 70:
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
        use_relay = (
            self.config.use_mev_protection or
            self.converter.to_decimal(context.mev_threat_level, Decimal('0')) > 70 or
            self.converter.to_decimal(context.sandwich_risk, Decimal('0')) > 60
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
    
    def _calculate_stop_loss(self, risk_score: Decimal) -> Decimal:
        """Calculate stop loss based on risk."""
        risk_score = self.converter.to_decimal(risk_score)
        
        if self.intel_level <= 3:
            return Decimal('3')  # Tight stop loss
        elif self.intel_level <= 6:
            return Decimal('5')
        elif self.intel_level <= 9:
            return Decimal('8')
        else:  # Level 10
            # Dynamic based on volatility
            return Decimal('3') if risk_score > 70 else Decimal('10')
    
    def _calculate_take_profits(self, opportunity_score: Decimal) -> List[Decimal]:
        """Calculate take profit targets."""
        opportunity_score = self.converter.to_decimal(opportunity_score)
        
        if opportunity_score > 80:
            return [Decimal('5'), Decimal('10'), Decimal('20')]
        elif opportunity_score > 60:
            return [Decimal('3'), Decimal('7'), Decimal('12')]
        else:
            return [Decimal('2'), Decimal('5'), Decimal('8')]
    
    def _generate_reasoning(
        self,
        action: str,
        risk_score: Decimal,
        opportunity_score: Decimal,
        confidence_score: Decimal,
        context: MarketContext
    ) -> str:
        """Generate detailed reasoning for the decision."""
        
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
            if self.converter.to_decimal(context.liquidity_depth_score, Decimal('0')) > 70:
                reasoning += "Good liquidity minimizes slippage. "
        elif action == 'SKIP':
            reasoning += "Rationale: "
            if risk_score > self.config.risk_tolerance:
                reasoning += f"Risk ({risk_score:.1f}) exceeds tolerance ({self.config.risk_tolerance}). "
            if confidence_score < self.config.min_confidence_required:
                reasoning += f"Insufficient confidence ({confidence_score:.1f} < {self.config.min_confidence_required}). "
        
        return reasoning
    
    def _identify_risk_factors(self, context: MarketContext) -> List[str]:
        """Identify key risk factors."""
        context = self.normalizer.normalize_context(context)
        factors = []
        
        mev_threat = self.converter.to_decimal(context.mev_threat_level, Decimal('0'))
        volatility = self.converter.to_decimal(context.volatility_index, Decimal('0'))
        liquidity_score = self.converter.to_decimal(context.liquidity_depth_score, Decimal('100'))
        competing_bots = self.converter.to_decimal(context.competing_bots_detected, Decimal('0'))
        
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
    
    def _identify_opportunity_factors(self, context: MarketContext) -> List[str]:
        """Identify opportunity factors."""
        context = self.normalizer.normalize_context(context)
        factors = []
        
        volume_change = self.converter.to_decimal(context.volume_24h_change, Decimal('0'))
        liquidity_score = self.converter.to_decimal(context.liquidity_depth_score, Decimal('0'))
        congestion = self.converter.to_decimal(context.network_congestion, Decimal('100'))
        bot_success = self.converter.to_decimal(context.bot_success_rate, Decimal('100'))
        
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
    
    def _generate_mitigation_strategies(self, context: MarketContext) -> List[str]:
        """Generate risk mitigation strategies."""
        context = self.normalizer.normalize_context(context)
        strategies = []
        
        mev_threat = self.converter.to_decimal(context.mev_threat_level, Decimal('0'))
        volatility = self.converter.to_decimal(context.volatility_index, Decimal('0'))
        slippage = self.converter.to_decimal(context.expected_slippage, Decimal('0'))
        competing_bots = self.converter.to_decimal(context.competing_bots_detected, Decimal('0'))
        
        if mev_threat > 60:
            strategies.append("Use private relay for MEV protection")
        if volatility > 70:
            strategies.append("Reduce position size for volatility")
        if slippage > 3:
            strategies.append("Split trade to reduce slippage")
        if competing_bots > 5:
            strategies.append("Increase gas for competitive execution")
        
        return strategies
    
    def _assess_time_sensitivity(self, context: MarketContext) -> str:
        """Assess time sensitivity of the opportunity."""
        context = self.normalizer.normalize_context(context)
        
        volatility = self.converter.to_decimal(context.volatility_index, Decimal('0'))
        competing_bots = self.converter.to_decimal(context.competing_bots_detected, Decimal('0'))
        volume_change = self.converter.to_decimal(context.volume_24h_change, Decimal('0'))
        
        if context.chaos_event_detected:
            return 'critical'
        elif volatility > 70 or competing_bots > 5:
            return 'high'
        elif context.trend_direction == 'bullish' and volume_change > 50:
            return 'medium'
        else:
            return 'low'
    
    def _calculate_max_execution_time(self) -> int:
        """Calculate maximum execution time based on intel level."""
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
    
    async def cleanup(self):
        """
        Cleanup resources when done.
        
        Call this when shutting down the engine to properly
        close the price feed service.
        """
        try:
            await self.price_service.close()
            logger.info("[INTEL] Engine cleanup complete")
        except Exception as e:
            logger.error(f"[INTEL] Error during cleanup: {e}")