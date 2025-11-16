"""
Intel Slider System for Paper Trading Bot - MAIN ORCHESTRATOR
This module provides the main IntelSliderEngine that coordinates all intelligence
components using composition for clean separation of concerns.
Integrates with real price feeds and market data for accurate trading decisions.

FIXED: Dashboard configuration now properly overrides hardcoded intelligence level thresholds
FIXED: Method signatures now match base class IntelligenceEngine
FIXED: All Pylance type checking errors resolved
PHASE 1: Added position-aware decision logic to prevent over-concentration
PHASE 2: Added multi-DEX price comparison and arbitrage detection for optimal sell prices

File: dexproject/paper_trading/intelligence/intel_slider.py
"""
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List, Tuple, Type


# Django imports for timezone-aware datetimes
from django.utils import timezone

# Import price feed service for real data
from paper_trading.services.price_feed_service import PriceFeedService

from paper_trading.intelligence.core.base import (
    IntelligenceEngine,
    MarketContext,
    TradingDecision
)

# Import configuration
from paper_trading.intelligence.config.intel_config import INTEL_CONFIGS, IntelLevelConfig

# Import price history
from paper_trading.intelligence.data.price_history import PriceHistory

# Import analyzers
from paper_trading.intelligence.analyzers import CompositeMarketAnalyzer
from paper_trading.intelligence.strategies.decision_maker import DecisionMaker
from paper_trading.intelligence.data.ml_features import MLFeatureCollector

# Import type utilities
from paper_trading.utils.type_utils import TypeConverter, MarketDataNormalizer

# PHASE 2: Import DEX comparison and arbitrage detection
DEXPriceComparator: Optional[Type[Any]] = None
ArbitrageDetector: Optional[Type[Any]] = None
PHASE_2_AVAILABLE = False

try:
    from paper_trading.intelligence.dex.dex_price_comparator import DEXPriceComparator as _DEXPriceComparator
    from paper_trading.intelligence.strategies.arbitrage_engine import ArbitrageDetector as _ArbitrageDetector
    DEXPriceComparator = _DEXPriceComparator
    ArbitrageDetector = _ArbitrageDetector
    PHASE_2_AVAILABLE = True
except ImportError:
    # Phase 2 components not available - bot will run in Phase 1 mode
    PHASE_2_AVAILABLE = False

logger = logging.getLogger(__name__)


class IntelSliderEngine(IntelligenceEngine):
    """
    Main intelligence engine controlled by the Intel slider (1-10).

    This engine coordinates all intelligence components using composition:
    - CompositeMarketAnalyzer: Comprehensive market analysis with real blockchain data
    - DecisionMaker: Makes trading decisions based on intel level
    - MLFeatureCollector: Collects training data for Level 10
    - DEXPriceComparator (Phase 2): Compares prices across multiple DEXs
    - ArbitrageDetector (Phase 2): Detects profitable arbitrage opportunities

    The engine adapts its behavior based on the intelligence level,
    providing a simple interface while handling complex decision-making.

    Phase 1 Features:
    - Position-aware trading: Prevents over-concentration in any single token
    - Configurable position limits per token

    Phase 2 Features:
    - Multi-DEX price comparison: Queries Uniswap V3, SushiSwap, Curve
    - Arbitrage detection: Finds profitable sell opportunities
    - Optimal execution: Routes trades to best-priced DEX

    Attributes:
        config: Intelligence level configuration
        intel_level: Current intelligence level (1-10)
        composite_analyzer: Handles comprehensive market analysis
        decision_maker: Makes trading decisions
        ml_collector: Collects ML training data (Level 10)
        dex_comparator: Multi-DEX price comparison (Phase 2)
        arbitrage_detector: Arbitrage opportunity detection (Phase 2)
        price_service: Service for fetching token prices
        price_history_cache: Cache of historical prices
        market_history: Historical market contexts
        price_trends: Tracked price trends
        volatility_tracker: Volatility tracking data
        historical_decisions: Past trading decisions
        strategy_config: Optional strategy configuration from dashboard
    """

    def __init__(
        self,
        intel_level: int = 5,
        account_id: Optional[str] = None,
        strategy_config=None,
        chain_id: int = 84532
    ):
        """
        Initialize the Intel Slider engine.

        Args:
            intel_level: Intelligence level (1-10)
            account_id: Optional paper trading account ID
            strategy_config: Optional PaperStrategyConfiguration for overrides
            chain_id: Chain ID for price feeds (default: Base Sepolia 84532)
        """
        super().__init__(intel_level)

        # Get configuration for this intel level
        self.config: IntelLevelConfig = INTEL_CONFIGS[intel_level]
        self.account_id = account_id
        self.chain_id = chain_id

        # Store strategy_config for position checking
        self.strategy_config = strategy_config

        # Initialize price service for real data
        self.price_service = PriceFeedService(chain_id=chain_id)

        # Initialize components via composition
        self.composite_analyzer = CompositeMarketAnalyzer()
        self.decision_maker = DecisionMaker(
            config=self.config,
            intel_level=intel_level,
            strategy_config=strategy_config  # 🆕 Pass user's strategy config
        )
        self.ml_collector = MLFeatureCollector(intel_level)

        # PHASE 2: Initialize DEX comparison and arbitrage detection
        self.dex_comparator: Optional[Any] = None
        self.arbitrage_detector: Optional[Any] = None
        if PHASE_2_AVAILABLE and DEXPriceComparator is not None and ArbitrageDetector is not None:
            try:
                self.dex_comparator = DEXPriceComparator(chain_id=chain_id)
                self.arbitrage_detector = ArbitrageDetector()
                self.logger.info(
                    "[INTEL SLIDER] Phase 2 components initialized: "
                    "DEX comparison + Arbitrage detection"
                )
            except Exception as init_error:
                self.logger.warning(
                    f"[INTEL SLIDER] Failed to initialize Phase 2 components: {init_error}"
                )
                self.dex_comparator = None
                self.arbitrage_detector = None
        else:
            self.logger.info("[INTEL SLIDER] Phase 2 not available, running in Phase 1 mode")

        # Utility classes
        self.converter = TypeConverter()
        self.normalizer = MarketDataNormalizer()

        # Price history tracking
        self.price_history_cache: Dict[str, PriceHistory] = {}

        # Market tracking storage
        self.market_history: Dict[str, List[MarketContext]] = {}
        self.price_trends: Dict[str, Dict[str, Any]] = {}
        self.volatility_tracker: Dict[str, List[Decimal]] = {}

        # Learning and performance tracking
        self.historical_decisions: List[TradingDecision] = []
        self.performance_history: List[Dict[str, Any]] = []

        # Apply configuration overrides from database if provided
        if strategy_config:
            self._apply_strategy_config(strategy_config)

        self.logger.info(
            f"[INTEL SLIDER] Initialized: Level {intel_level} - {self.config.name} "
            f"(Chain: {chain_id})"
        )

    @property
    def analyzer(self):
        """
        Backward compatibility property for market_analyzer.py.

        Returns composite_analyzer to maintain compatibility with legacy code
        that expects 'intelligence_engine.analyzer' instead of
        'intelligence_engine.composite_analyzer'.

        Returns:
            CompositeMarketAnalyzer instance
        """
        return self.composite_analyzer

    def _apply_strategy_config(self, strategy_config) -> None:
        """
        Apply configuration overrides from database.

        This method overrides the hardcoded intelligence level defaults with
        user-configured values from the dashboard. It properly updates the
        correct field names in IntelLevelConfig.

        Args:
            strategy_config: Database strategy configuration from dashboard
        """
        try:
            # ================================================================
            # 1. CONFIDENCE THRESHOLD OVERRIDE
            # ================================================================
            if hasattr(strategy_config, 'confidence_threshold') and \
               strategy_config.confidence_threshold is not None:
                old_threshold = self.config.min_confidence_required
                new_threshold = Decimal(str(strategy_config.confidence_threshold))
                
                # Update the CORRECT field in IntelLevelConfig
                self.config.min_confidence_required = new_threshold
                
                # Update parent class attribute for consistency
                self.confidence_threshold = new_threshold
                
                self.logger.info(
                    f"[CONFIG OVERRIDE] Confidence threshold: "
                    f"{old_threshold}% → {new_threshold}% "
                    f"(Updated config.min_confidence_required)"
                )

            # ================================================================
            # 2. RISK THRESHOLD OVERRIDE
            # ================================================================
            if hasattr(strategy_config, 'risk_threshold') and \
               strategy_config.risk_threshold is not None:
                old_threshold = self.config.risk_tolerance
                new_threshold = Decimal(str(strategy_config.risk_threshold))
                
                # Update the CORRECT field in IntelLevelConfig
                self.config.risk_tolerance = new_threshold
                
                # Update parent class attribute for consistency
                self.risk_threshold = new_threshold
                
                self.logger.info(
                    f"[CONFIG OVERRIDE] Risk threshold: "
                    f"{old_threshold} → {new_threshold} "
                    f"(Updated config.risk_tolerance)"
                )

            # ================================================================
            # 3. OPPORTUNITY THRESHOLD - No corresponding field in config
            # ================================================================
            if hasattr(strategy_config, 'opportunity_threshold') and \
               strategy_config.opportunity_threshold is not None:
                old_threshold = self.opportunity_threshold
                new_threshold = float(strategy_config.opportunity_threshold)
                
                # Only update parent class attribute (no config field exists)
                self.opportunity_threshold = new_threshold
                
                self.logger.info(
                    f"[CONFIG OVERRIDE] Opportunity threshold: "
                    f"{old_threshold} → {new_threshold} "
                    f"(Updated parent class only - no config field)"
                )

            # ================================================================
            # 4. MAX POSITION SIZE PER TOKEN
            # ================================================================
            if hasattr(strategy_config, 'max_position_size_per_token_percent'):
                self.logger.info(
                    f"[CONFIG OVERRIDE] Max position per token: "
                    f"{strategy_config.max_position_size_per_token_percent}%"
                )

            self.logger.info("[CONFIG OVERRIDE] Strategy configuration applied successfully")

        except Exception as config_error:
            self.logger.error(
                f"[CONFIG OVERRIDE] Error applying strategy config: {config_error}",
                exc_info=True
            )

    def _check_position_limits(
        self,
        market_context: MarketContext,
        existing_positions: List[Any],
        portfolio_value: Decimal
    ) -> Tuple[bool, str]:
        """
        Check if we can buy more of this token without exceeding position limits.

        This method implements Phase 1 position-aware trading by checking if the
        current position in a token exceeds the configured maximum percentage of
        the portfolio.

        Args:
            market_context: Market context containing token information
            existing_positions: List of existing positions
            portfolio_value: Current portfolio value in USD

        Returns:
            Tuple of (can_buy: bool, reason: str)
        """
        try:
            # Get max position size per token from strategy config
            if not self.strategy_config or \
               not hasattr(self.strategy_config, 'max_position_size_per_token_percent'):
                # No limit configured, allow the trade
                return True, "No position limit configured"

            max_position_per_token_percent = Decimal(
                str(self.strategy_config.max_position_size_per_token_percent)
            )

            # If limit is 0 or negative, no restriction
            if max_position_per_token_percent <= 0:
                return True, "Position limit disabled (0%)"

            # Find if we already have a position in this token
            token_symbol = market_context.token_symbol
            current_invested = Decimal('0')

            for pos in existing_positions:
                if pos.get('token_symbol') == token_symbol:
                    current_invested += Decimal(str(pos.get('invested_usd', 0)))

            # Calculate current position as percentage of portfolio
            if portfolio_value <= 0:
                # Can't calculate percentage with zero portfolio
                return True, "Portfolio value is zero, allowing trade"

            current_position_percent = (current_invested / portfolio_value) * Decimal('100')

            self.logger.info(
                f"[POSITION CHECK] Current {token_symbol} position: "
                f"${current_invested:.2f} ({current_position_percent:.2f}% of portfolio)"
            )

            # Check if we're at or over the limit
            if current_position_percent >= max_position_per_token_percent:
                reason = (
                    f"Already own {current_position_percent:.2f}% of portfolio in {token_symbol} "
                    f"(limit: {max_position_per_token_percent}%). "
                    "Will HOLD to prevent over-concentration."
                )
                self.logger.warning(f"[POSITION CHECK] ❌ {reason}")
                return False, reason

            # We can still buy more (under the limit)
            remaining_percent = max_position_per_token_percent - current_position_percent
            reason = (
                f"Can still buy {token_symbol}: currently {current_position_percent:.2f}%, "
                f"can add up to {remaining_percent:.2f}% more "
                f"(limit: {max_position_per_token_percent}%)"
            )
            self.logger.info(f"[POSITION CHECK] ✅ {reason}")
            return True, reason

        except Exception as check_error:
            self.logger.error(
                f"[POSITION CHECK] Error checking position limits: {check_error}",
                exc_info=True
            )
            # On error, allow the trade (fail-safe)
            return True, f"Position check error, allowing trade: {str(check_error)}"

    # =========================================================================
    # PHASE 2: DEX COMPARISON AND ARBITRAGE METHODS
    # =========================================================================

    async def _compare_dex_prices(
        self,
        token_address: str,
        token_symbol: str,
        trade_size_usd: Decimal
    ) -> Optional[Dict[str, Any]]:
        """
        Compare prices across multiple DEXs to find the best execution price.

        This method queries Uniswap V3, SushiSwap, and Curve to find the best
        price for buying or selling a token. It returns the best price along
        with comparison data from all available DEXs.

        Args:
            token_address: Token contract address
            token_symbol: Token symbol for logging
            trade_size_usd: Trade size in USD for accurate price quotes

        Returns:
            Dictionary with price comparison results, or None if Phase 2 unavailable
        """
        if not self.dex_comparator:
            self.logger.debug(
                f"[DEX COMPARISON] Phase 2 not available for {token_symbol}, "
                "using single price source"
            )
            return None

        try:
            self.logger.info(
                f"[DEX COMPARISON] Comparing prices across DEXs for {token_symbol} "
                f"(${trade_size_usd:.2f})"
            )

            if hasattr(self.dex_comparator, 'compare_prices'):
                comparison_result = await self.dex_comparator.compare_prices(
                    token_address,
                    token_symbol,
                    trade_size_usd
                )
            else:
                self.logger.warning(
                    "[DEX COMPARISON] DEXPriceComparator.compare_prices method not found"
                )
                return None

            if comparison_result and comparison_result.get('best_price'):
                best_price = comparison_result['best_price']
                best_dex = comparison_result.get('best_dex', 'unknown')
                advantage = comparison_result.get('price_advantage_percent', Decimal('0'))

                self.logger.info(
                    f"[DEX COMPARISON] Best price for {token_symbol}: "
                    f"${best_price:.2f} on {best_dex} "
                    f"({advantage:.2f}% better than average)"
                )

                return comparison_result
            else:
                self.logger.warning(
                    f"[DEX COMPARISON] No valid prices found for {token_symbol}"
                )
                return None

        except Exception as comparison_error:
            self.logger.error(
                f"[DEX COMPARISON] Error comparing prices for {token_symbol}: "
                f"{comparison_error}",
                exc_info=True
            )
            return None

    async def _detect_arbitrage_opportunity(
        self,
        token_address: str,
        token_symbol: str,
        current_price: Decimal,
        trade_size_usd: Decimal,
        gas_price_gwei: Optional[Decimal] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Detect arbitrage opportunities by comparing current position price
        with available sell prices across multiple DEXs.

        This method helps the bot decide where to sell tokens for maximum profit.
        It calculates net profit after gas costs and validates profitability.

        Args:
            token_address: Token contract address
            token_symbol: Token symbol for logging
            current_price: Current price we bought at (or holding price)
            trade_size_usd: Size of position to sell in USD
            gas_price_gwei: Current gas price for cost calculation

        Returns:
            Dictionary with arbitrage opportunity details, or None if not profitable
        """
        if not self.arbitrage_detector:
            self.logger.debug(
                f"[ARBITRAGE] Phase 2 not available for {token_symbol}, "
                "no arbitrage detection"
            )
            return None

        try:
            self.logger.info(
                f"[ARBITRAGE] Checking for arbitrage opportunity on {token_symbol} "
                f"(entry: ${current_price:.2f}, size: ${trade_size_usd:.2f})"
            )

            if hasattr(self.arbitrage_detector, 'find_opportunity'):
                opportunity = await self.arbitrage_detector.find_opportunity(
                    token_address=token_address,
                    buy_price=current_price,
                    trade_size_usd=trade_size_usd,
                    gas_price_gwei=gas_price_gwei
                )
            else:
                self.logger.warning(
                    "[ARBITRAGE] ArbitrageDetector.find_opportunity method not found"
                )
                return None

            if opportunity and opportunity.get('is_profitable'):
                net_profit = opportunity.get('net_profit_usd', Decimal('0'))
                margin = opportunity.get('profit_margin_percent', Decimal('0'))
                sell_dex = opportunity.get('sell_dex', 'unknown')

                self.logger.info(
                    f"[ARBITRAGE] 💰 Profitable opportunity found for {token_symbol}! "
                    f"Sell on {sell_dex} for ${net_profit:.2f} profit ({margin:.2f}% margin)"
                )

                return opportunity
            else:
                self.logger.debug(
                    f"[ARBITRAGE] No profitable arbitrage found for {token_symbol}"
                )
                return None

        except Exception as arbitrage_error:
            self.logger.error(
                f"[ARBITRAGE] Error detecting arbitrage for {token_symbol}: "
                f"{arbitrage_error}",
                exc_info=True
            )
            return None

    async def make_decision(
        self,
        market_context: MarketContext,
        account_balance: Decimal,
        existing_positions: List[Any],
        portfolio_value: Optional[Decimal] = None,
        token_address: Optional[str] = None,
        token_symbol: Optional[str] = None,
        # ADD THESE FOUR NEW OPTIONAL PARAMETERS:
        position_entry_price: Optional[Decimal] = None,
        position_current_value: Optional[Decimal] = None,
        position_invested: Optional[Decimal] = None,
        position_hold_time_hours: Optional[float] = None
    ) -> TradingDecision:
        """
        Make a trading decision based on analyzed market context.

        This method implements the abstract method from IntelligenceEngine.
        It uses the DecisionMaker to create a trading decision and then
        applies intel-level adjustments.

        BACKWARD COMPATIBILITY: Accepts deprecated 'portfolio_value' parameter
        for compatibility with legacy code. The base class uses 'account_balance'
        as the primary parameter.

        PHASE 1: Now checks position limits before making BUY decisions.

        Args:
            market_context: Analyzed market context with comprehensive data
            account_balance: Current account balance in USD (base class parameter)
            existing_positions: List of existing positions (base class parameter)
            portfolio_value: DEPRECATED - uses account_balance instead
            token_address: DEPRECATED - already in market_context
            token_symbol: DEPRECATED - already in market_context

        Returns:
            Complete trading decision with reasoning and execution strategy

        Raises:
            Exception: If decision-making fails critically
        """
        try:
            # Use account_balance as the primary portfolio value
            portfolio_val = account_balance
            
            self.logger.debug(
                f"[MAKE_DECISION] Using account_balance: ${account_balance:.2f}"
            )
            
            # If portfolio_value was provided, log a deprecation warning
            if portfolio_value is not None and portfolio_value != account_balance:
                self.logger.warning(
                    f"[MAKE_DECISION] DEPRECATED: portfolio_value parameter ignored. "
                    f"Using account_balance=${account_balance:.2f} instead of "
                    f"portfolio_value=${portfolio_value:.2f}"
                )

            # Log if legacy parameters were provided
            if existing_positions is not None and len(existing_positions) > 0:
                self.logger.debug(
                    f"[MAKE_DECISION] Received {len(existing_positions)} existing positions"
                )
            
            if token_address and token_address != market_context.token_address:
                self.logger.debug(
                    "[MAKE_DECISION] DEPRECATED: Token address parameter provided "
                    "but using value from market_context"
                )
            
            if token_symbol and token_symbol != market_context.token_symbol:
                self.logger.debug(
                    "[MAKE_DECISION] DEPRECATED: Token symbol parameter provided "
                    "but using value from market_context"
                )

            self.logger.info(
                f"[MAKE_DECISION] Creating decision for {market_context.token_symbol} "
                f"(Portfolio: ${portfolio_val:.2f})"
            )

            # Step 1: Check if we should skip due to poor data quality
            if market_context.confidence_in_data < 40.0:
                self.logger.warning(
                    f"[MAKE_DECISION] Low data confidence "
                    f"({market_context.confidence_in_data:.1f}%), skipping trade"
                )
                return self._create_skip_decision(
                    market_context,
                    f"Data confidence too low: {market_context.confidence_in_data:.1f}%"
                )

            # ================================================================
            # PHASE 1: Check position limits before making BUY decision
            # ================================================================
            if existing_positions is not None and len(existing_positions) > 0:
                can_buy, position_reason = self._check_position_limits(
                    market_context,
                    existing_positions,
                    portfolio_val
                )

                if not can_buy:
                    self.logger.warning(
                        f"[MAKE_DECISION] Position limit reached for "
                        f"{market_context.token_symbol}, returning SKIP decision"
                    )
                    return self._create_skip_decision(
                        market_context,
                        f"Position limit: {position_reason}"
                    )
                else:
                    self.logger.debug(
                        f"[MAKE_DECISION] Position check passed: {position_reason}"
                    )

            # Step 2: Build decision using DecisionMaker components
            # Step 2: Build decision using DecisionMaker components
            # Pass position data if we have it
            decision = self._build_decision_from_context(
                market_context=market_context,
                portfolio_value=portfolio_val,
                position_entry_price=position_entry_price,
                position_current_value=position_current_value,
                position_invested=position_invested,
                position_hold_time_hours=position_hold_time_hours
            )

            self.logger.debug(
                f"[MAKE_DECISION] Base decision: {decision.action}, "
                f"Confidence={decision.overall_confidence}%, "
                f"Risk={decision.risk_score}, Opportunity={decision.opportunity_score}"
            )

            # Step 3: Store decision in history for learning
            self.historical_decisions.append(decision)
            if len(self.historical_decisions) > 100:
                self.historical_decisions.pop(0)

            # Step 4: Collect ML features if Level 10
            if self.intel_level == 10:
                try:
                    # Attempt to collect ML features
                    # Note: MLFeatureCollector interface may vary
                    if hasattr(self.ml_collector, 'collect'):
                        self.ml_collector.collect_features(
                            context=market_context,  # Changed parameter name
                            decision=decision
                        )
                    else:
                        self.logger.debug(
                            "[MAKE_DECISION] ML collector has no collect method, skipping"
                        )
                except Exception as ml_error:
                    self.logger.warning(
                        f"[MAKE_DECISION] ML feature collection failed: {ml_error}"
                    )

            self.logger.info(
                f"[MAKE_DECISION] Final decision: {decision.action} "
                f"{market_context.token_symbol} "
                f"(Confidence: {decision.overall_confidence:.1f}%)"
            )

            return decision

        except Exception as decision_error:
            self.logger.error(
                f"[MAKE_DECISION] Fatal error in decision making: {decision_error}",
                exc_info=True
            )

            # Return safe skip decision
            return self._create_skip_decision(
                market_context,
                f"Decision making error: {str(decision_error)}"
            )

    async def evaluate_position_exit(
        self,
        market_context: MarketContext,
        position_data: Dict[str, Any],
        account_balance: Decimal,
        existing_positions: Dict[str, Any]
    ) -> TradingDecision:
        """
        Evaluate whether to exit an existing position (SELL decision).
        
        This method analyzes an existing position and decides whether it's time
        to sell based on:
        - Market conditions changing
        - Position P&L performance
        - Risk increasing
        - Better opportunities elsewhere
        
        Args:
            market_context: Current market context for the token
            position_data: Information about the existing position
            account_balance: Current account balance
            existing_positions: All existing positions
            
        Returns:
            TradingDecision with SELL, HOLD, or SKIP action
        """
        try:
            # Extract position information
            entry_price = Decimal(str(position_data.get('entry_price', 0)))
            current_price = Decimal(str(position_data.get('current_price', 0)))
            invested_usd = Decimal(str(position_data.get('invested_usd', 0)))
            current_value_usd = Decimal(str(position_data.get('current_value_usd', 0)))
            hold_time_hours = float(position_data.get('hold_time_hours', 0))
            
            self.logger.info(
                f"[EVALUATE EXIT] Analyzing position for {market_context.token_symbol}: "
                f"Entry=${entry_price:.4f}, Current=${current_price:.4f}, "
                f"Hold time={hold_time_hours:.1f}h"
            )
            
            # Use make_decision with position parameters to determine exit
            decision = await self.make_decision(
                market_context=market_context,
                account_balance=account_balance,
                existing_positions=list(existing_positions.values()) if existing_positions else [],
                position_entry_price=entry_price,
                position_current_value=current_value_usd,
                position_invested=invested_usd,
                position_hold_time_hours=hold_time_hours
            )
            
            self.logger.info(
                f"[EVALUATE EXIT] Decision for {market_context.token_symbol}: "
                f"{decision.action} (Confidence: {decision.overall_confidence:.1f}%)"
            )
            
            return decision
            
        except Exception as exit_error:
            self.logger.error(
                f"[EVALUATE EXIT] Error evaluating position exit: {exit_error}",
                exc_info=True
            )
            return self._create_skip_decision(
                market_context,
                f"Position exit evaluation error: {str(exit_error)}"
            )

    def _create_skip_decision(
        self,
        market_context: MarketContext,
        reason: str
    ) -> TradingDecision:
        """
        Create a SKIP decision with the given reason.

        Args:
            market_context: Market context for the decision
            reason: Reason for skipping

        Returns:
            TradingDecision with action='SKIP'
        """
        return TradingDecision(
            action='SKIP',
            token_address=market_context.token_address or "",
            token_symbol=market_context.token_symbol,
            position_size_percent=Decimal('0'),
            position_size_usd=Decimal('0'),
            stop_loss_percent=Decimal('0'),
            take_profit_targets=[],
            execution_mode='standard',
            use_private_relay=False,
            gas_strategy='standard',
            max_gas_price_gwei=Decimal('50'),
            overall_confidence=Decimal('0'),
            risk_score=Decimal('100'),
            opportunity_score=Decimal('0'),
            primary_reasoning=reason,
            risk_factors=[reason],
            opportunity_factors=[],
            mitigation_strategies=[],
            intel_level_used=self.intel_level,
            intel_adjustments={},
            time_sensitivity='low',
            max_execution_time_ms=15000,
            processing_time_ms=0
        )

    async def analyze_market(
        self,
        token_address: str
    ) -> MarketContext:
        """
        Analyze market conditions for a token.

        This method implements the abstract method from IntelligenceEngine.
        It creates a market context and enhances it with comprehensive analysis.

        Args:
            token_address: Token contract address to analyze

        Returns:
            Enhanced market context with analysis results
        """
        try:
            self.logger.info(
                f"[ANALYZE MARKET] Starting market analysis for token: {token_address}"
            )

            # Create initial market context
            # Note: You may need to fetch token_symbol from a token registry
            market_context = MarketContext(
                token_address=token_address,
                token_symbol="UNKNOWN",  # Will be updated by analyzer
                current_price=Decimal('0')
            )

            # Run comprehensive analysis using composite analyzer
            if hasattr(self.composite_analyzer, 'analyze_comprehensive'):
                analysis_result = await self.composite_analyzer.analyze_comprehensive(
                    token_address=token_address,
                    chain_id=self.chain_id,
                    trade_size_usd=Decimal('1000')
                )
            else:
                analysis_result = await self.composite_analyzer.analyze(
                    token_address=token_address
                )

            # Enhance market context with analysis results
            if analysis_result:
                # Extract relevant metrics from analysis
                if 'gas_analysis' in analysis_result:
                    gas_data = analysis_result['gas_analysis']
                    market_context.gas_price_gwei = gas_data.get(
                        'current_gas_price',
                        market_context.gas_price_gwei
                    )

                if 'liquidity_analysis' in analysis_result:
                    liquidity_data = analysis_result['liquidity_analysis']
                    market_context.liquidity_usd = liquidity_data.get(
                        'total_liquidity_usd',
                        market_context.liquidity_usd
                    )

                if 'overall_confidence' in analysis_result:
                    market_context.confidence_in_data = analysis_result['overall_confidence']

            self.logger.info(
                f"[ANALYZE MARKET] Market analysis complete for {token_address}"
            )

            return market_context

        except Exception as analysis_error:
            self.logger.error(
                f"[ANALYZE MARKET] Error in market analysis: {analysis_error}",
                exc_info=True
            )
            # Return minimal context on error
            return MarketContext(
                token_address=token_address,
                token_symbol="ERROR",
                current_price=Decimal('0')
            )

    def _build_decision_from_context(
        self,
        market_context: MarketContext,
        portfolio_value: Decimal,
        # NEW: Add position parameters for SELL evaluation
        position_entry_price: Optional[Decimal] = None,
        position_current_value: Optional[Decimal] = None,
        position_invested: Optional[Decimal] = None,
        position_hold_time_hours: Optional[float] = None
    ) -> TradingDecision:
        """
        Build a trading decision from market context using DecisionMaker.

        This is a helper method that delegates to DecisionMaker components
        to build a complete trading decision.

        Args:
            market_context: Analyzed market context
            portfolio_value: Current portfolio value

        Returns:
            Complete TradingDecision object
        """
        # Build comprehensive analysis dict from context
        comprehensive_analysis = {
            'gas_analysis': {
                'current_gas_gwei': float(market_context.gas_price_gwei),
                'network_congestion': market_context.network_congestion
            },
            'liquidity': {
                'pool_liquidity_usd': float(market_context.pool_liquidity_usd),
                'expected_slippage_percent': float(market_context.expected_slippage),
                'liquidity_depth_score': market_context.liquidity_depth_score
            },
            'volatility': {
                'volatility_index': market_context.volatility_index,
                'trend_direction': market_context.trend_direction
            },
            'mev_analysis': {
                'threat_level': market_context.mev_threat_level,
                'sandwich_attack_risk': market_context.sandwich_risk,
                'frontrun_probability': market_context.frontrun_probability
            },
            'market_state': {
                'chaos_event_detected': market_context.chaos_event_detected
            }
        }

        # Calculate risk and opportunity scores
        risk_score = self.decision_maker.calculate_risk_score(
            market_context,
            comprehensive_analysis
        )
        opp_score = self.decision_maker.calculate_opportunity_score(
            market_context,
            comprehensive_analysis
        )

        # Calculate overall confidence
        conf_score = self.decision_maker.calculate_confidence_score(
            risk_score,
            opp_score,
            market_context
        )
        
        # Determine action (with position data for SELL evaluation)
        # Determine if there is an existing position
        has_position = (position_entry_price is not None and position_invested is not None)

        # DEBUG: Log position data
        self.logger.info(
            f"[BUILD DECISION] has_position={has_position}, "
            f"entry_price={position_entry_price}, "
            f"invested={position_invested}, "
            f"hold_time={position_hold_time_hours}"
        )

        # Determine action (with position data for SELL evaluation)
        action = self.decision_maker.determine_action(
            risk_score=risk_score,
            opportunity_score=opp_score,
            confidence_score=conf_score,
            context=market_context,
            has_position=has_position,
            position_entry_price=position_entry_price,
            position_current_value=position_current_value,
            position_invested=position_invested,
            position_hold_time_hours=position_hold_time_hours
        )


        # Position sizing
        pos_pct = Decimal('0')
        pos_usd = Decimal('0')
        if action == 'BUY':
            pos_pct = self.decision_maker.calculate_position_size(
                risk_score,
                opp_score,
                market_context
            )
            pos_usd = (pos_pct / Decimal('100')) * portfolio_value
            
            # ✅ Apply max_trade_size_usd limit if configured
            if self.strategy_config and hasattr(self.strategy_config, 'max_trade_size_usd'):
                max_trade_usd = Decimal(str(self.strategy_config.max_trade_size_usd))
                if max_trade_usd > 0 and pos_usd > max_trade_usd:
                    self.logger.info(
                        f"[POSITION SIZE] 💰 USD limit applied: ${max_trade_usd:.2f} "
                        f"(was ${pos_usd:.2f} from {pos_pct:.2f}% of portfolio)"
                    )
                    pos_usd = max_trade_usd
                    # Recalculate percentage based on capped USD amount
                    pos_pct = (pos_usd / portfolio_value) * Decimal('100')

        # Execution parameters
        stop_loss = self.decision_maker.calculate_stop_loss(risk_score)

        # FIXED: determine_execution_strategy returns a dictionary, not a tuple
        # Correct parameter order: (context, action)
        exec_strategy = self.decision_maker.determine_execution_strategy(
            market_context,
            action
        )

        # Extract values from dictionary
        exec_mode = exec_strategy.get('mode', 'SMART_LANE')
        priv_relay = exec_strategy.get('use_private_relay', True)
        gas_strat = exec_strategy.get('gas_strategy', 'standard')
        max_gas = exec_strategy.get('max_gas_gwei', Decimal('30'))

        # Reasoning
        reason = self.decision_maker.generate_reasoning(
            action,
            risk_score,
            opp_score,
            conf_score,
            market_context
        )
        risk_facts = self.decision_maker.identify_risk_factors(market_context)
        opp_facts = self.decision_maker.identify_opportunity_factors(market_context)
        mitigations = self.decision_maker.generate_mitigation_strategies(market_context)
        time_sens = self.decision_maker.assess_time_sensitivity(market_context)

        # Build and return TradingDecision
        return TradingDecision(
            action=action,
            token_address=market_context.token_address or "",
            token_symbol=market_context.token_symbol,
            position_size_percent=pos_pct,
            position_size_usd=pos_usd,
            stop_loss_percent=stop_loss,
            take_profit_targets=[],
            execution_mode=exec_mode,
            use_private_relay=priv_relay,
            gas_strategy=gas_strat,
            max_gas_price_gwei=max_gas,
            overall_confidence=conf_score,
            risk_score=risk_score,
            opportunity_score=opp_score,
            primary_reasoning=reason,
            risk_factors=risk_facts,
            opportunity_factors=opp_facts,
            mitigation_strategies=mitigations,
            intel_level_used=self.intel_level,
            intel_adjustments={},
            time_sensitivity=time_sens,
            max_execution_time_ms=5000 if time_sens == 'critical' else 15000,
            processing_time_ms=0
        )

    async def analyze(
        self,
        market_context: MarketContext,
        portfolio_value: Decimal = Decimal('10000')
    ) -> TradingDecision:
        """
        Main entry point: Analyze market and make trading decision.

        This method orchestrates the full analysis-to-decision pipeline by:
        1. Analyzing market conditions (analyze_market)
        2. Making trading decision (make_decision)
        3. Tracking performance metrics

        Args:
            market_context: Initial market context
            portfolio_value: Current portfolio value in USD

        Returns:
            Complete trading decision with reasoning
        """
        start_time = timezone.now()

        try:
            self.logger.info(
                f"[ANALYZE] Starting analysis for {market_context.token_symbol} "
                f"(Intel Level {self.intel_level})"
            )

            # Step 1: Analyze market conditions
            enhanced_context = await self.analyze_market(market_context.token_address or "")

            # Update enhanced_context with original context data
            if market_context.token_symbol != "UNKNOWN":
                enhanced_context.token_symbol = market_context.token_symbol
            if market_context.current_price > 0:
                enhanced_context.current_price = market_context.current_price

            # Step 2: Make trading decision based on analysis
            decision = await self.make_decision(
                enhanced_context,
                portfolio_value,
                []  # Empty positions list
            )

            # Step 3: Calculate processing time
            end_time = timezone.now()
            processing_time_ms = (end_time - start_time).total_seconds() * 1000
            decision.processing_time_ms = processing_time_ms

            # Step 4: Log performance metrics
            self._track_performance({
                'token_symbol': market_context.token_symbol,
                'action': decision.action,
                'confidence': float(decision.overall_confidence),
                'risk_score': float(decision.risk_score),
                'opportunity_score': float(decision.opportunity_score),
                'processing_time_ms': processing_time_ms,
                'intel_level': self.intel_level,
                'timestamp': end_time
            })

            self.logger.info(
                f"[ANALYZE] Analysis complete for {market_context.token_symbol}: "
                f"{decision.action} decision in {processing_time_ms:.2f}ms"
            )

            return decision

        except Exception as analyze_error:
            self.logger.error(
                f"[ANALYZE] Fatal error in analysis pipeline: {analyze_error}",
                exc_info=True
            )

            # Return safe skip decision
            return self._create_skip_decision(
                market_context,
                f"Analysis pipeline error: {str(analyze_error)}"
            )

    def _update_price_history(
        self,
        token_symbol: str,
        current_price: Decimal
    ) -> Optional[PriceHistory]:
        """
        Update price history for a token.
        
        Note: Currently disabled due to unknown PriceHistory interface.
        To enable: implement proper PriceHistory constructor and methods.
        """
        # Price history tracking disabled - interface unknown
        # Return None to indicate no history available
        return None

    def _enhance_context_with_analysis(
        self,
        market_context: MarketContext,
        analysis_result: Dict[str, Any],
        price_history: Optional[PriceHistory]
    ) -> MarketContext:
        """
        Enhance market context with comprehensive analysis data.
        
        CRITICAL: This method must populate ALL fields that DecisionMaker uses
        for risk/opportunity calculations. Missing fields cause identical scores.

        Args:
            market_context: Base market context
            analysis_result: Results from CompositeMarketAnalyzer
            price_history: Historical price data

        Returns:
            Enhanced market context with all analyzer results populated
        """
        try:
            # Extract analysis metrics from each analyzer
            gas_analysis = analysis_result.get('gas_analysis', {})
            liquidity_analysis = analysis_result.get('liquidity_analysis', {})
            volatility_analysis = analysis_result.get('volatility_analysis', {})
            mev_analysis = analysis_result.get('mev_analysis', {})
            market_state = analysis_result.get('market_state_analysis', {})

            # === GAS & NETWORK DATA ===
            if gas_analysis:
                market_context.gas_price_gwei = Decimal(str(gas_analysis.get(
                    'current_gas_price',
                    market_context.gas_price_gwei
                )))
                # CRITICAL: network_congestion used in DecisionMaker (15% weight)
                market_context.network_congestion = float(gas_analysis.get(
                    'network_congestion',
                    market_context.network_congestion
                ))

            # === LIQUIDITY DATA ===
            if liquidity_analysis:
                market_context.liquidity_usd = Decimal(str(liquidity_analysis.get(
                    'total_liquidity_usd',
                    market_context.liquidity_usd
                )))
                # CRITICAL: liquidity_depth_score used in DecisionMaker (20% weight)
                market_context.liquidity_depth_score = float(liquidity_analysis.get(
                    'liquidity_depth_score',
                    market_context.liquidity_depth_score
                ))
                # CRITICAL: pool_liquidity_usd used in decision logic
                market_context.pool_liquidity_usd = Decimal(str(liquidity_analysis.get(
                    'pool_liquidity_usd',
                    market_context.pool_liquidity_usd
                )))
                # CRITICAL: expected_slippage used in execution strategy
                market_context.expected_slippage = Decimal(str(liquidity_analysis.get(
                    'expected_slippage_percent',
                    market_context.expected_slippage
                )))

            # === VOLATILITY DATA ===
            if volatility_analysis:
                market_context.volatility = Decimal(str(volatility_analysis.get(
                    'volatility_percent',
                    market_context.volatility
                )))
                # CRITICAL: volatility_index used in DecisionMaker (20% weight)
                market_context.volatility_index = float(volatility_analysis.get(
                    'volatility_index',
                    market_context.volatility_index
                ))
                # CRITICAL: trend_direction used in opportunity score (30% weight)
                market_context.trend_direction = volatility_analysis.get(
                    'trend_direction',
                    market_context.trend_direction
                )
                # Additional trend data
                market_context.momentum = Decimal(str(volatility_analysis.get(
                    'momentum_score',
                    market_context.momentum
                )))

            # === MEV THREAT DATA ===
            if mev_analysis:
                # CRITICAL: mev_threat_level used in DecisionMaker (25% weight)
                market_context.mev_threat_level = float(mev_analysis.get(
                    'threat_level',
                    market_context.mev_threat_level
                ))
                # CRITICAL: sandwich_risk used in execution strategy
                market_context.sandwich_risk = float(mev_analysis.get(
                    'sandwich_risk',
                    market_context.sandwich_risk
                ))
                # CRITICAL: frontrun_probability used in execution strategy
                market_context.frontrun_probability = float(mev_analysis.get(
                    'frontrun_risk',
                    market_context.frontrun_probability
                ))

            # === MARKET STATE DATA ===
            if market_state:
                # Chaos events affect risk score (+10 points)
                market_context.chaos_event_detected = market_state.get(
                    'chaos_event_detected',
                    market_context.chaos_event_detected
                )

            # === OVERALL QUALITY ===
            # Set confidence in data from overall analysis
            market_context.confidence_in_data = float(analysis_result.get(
                'overall_confidence',
                market_context.confidence_in_data
            ))

            # Log what we populated (debugging)
            self.logger.debug(
                f"[ENHANCE CONTEXT] {market_context.token_symbol}: "
                f"MEV={market_context.mev_threat_level:.1f}, "
                f"Vol={market_context.volatility_index:.1f}, "
                f"Liq={market_context.liquidity_depth_score:.1f}, "
                f"Congestion={market_context.network_congestion:.1f}, "
                f"Trend={market_context.trend_direction}"
            )

            return market_context

        except Exception as enhance_error:
            self.logger.error(
                f"[ENHANCE CONTEXT] Error: {enhance_error}",
                exc_info=True
            )
            return market_context

    def _track_performance(self, metrics: Dict[str, Any]) -> None:
        """
        Track performance metrics for analysis.

        Args:
            metrics: Performance metrics to track
        """
        try:
            self.performance_history.append(metrics)

            # Keep only last 1000 metrics
            if len(self.performance_history) > 1000:
                self.performance_history.pop(0)

        except Exception as track_error:
            self.logger.error(
                f"[TRACK PERFORMANCE] Error: {track_error}",
                exc_info=True
            )

    def update_market_context(self, market_context: MarketContext) -> None:
        """
        Update market tracking with new context.

        Args:
            market_context: Market context to track
        """
        try:
            token_symbol = market_context.token_symbol

            # Store in history
            if token_symbol not in self.market_history:
                self.market_history[token_symbol] = []

            self.market_history[token_symbol].append(market_context)

            # Keep only last 50 contexts
            if len(self.market_history[token_symbol]) > 50:
                self.market_history[token_symbol].pop(0)

            # Update price trends
            if hasattr(market_context, 'trend_direction'):
                if token_symbol not in self.price_trends:
                    self.price_trends[token_symbol] = {}

                self.price_trends[token_symbol].update({
                    'trend_direction': market_context.trend_direction,
                    'momentum': market_context.momentum,
                    'volatility': market_context.volatility,
                    'last_updated': timezone.now()
                })

            # Track volatility
            if hasattr(market_context, 'volatility'):
                if token_symbol not in self.volatility_tracker:
                    self.volatility_tracker[token_symbol] = []

                self.volatility_tracker[token_symbol].append(
                    market_context.volatility
                )

                # Keep last 20 volatility measurements
                if len(self.volatility_tracker[token_symbol]) > 20:
                    self.volatility_tracker[token_symbol].pop(0)

            self.logger.debug(
                f"[MARKET CONTEXT] Updated tracking for {token_symbol}"
            )

        except Exception as update_error:
            self.logger.error(
                f"[MARKET CONTEXT] Error updating: {update_error}",
                exc_info=True
            )

    def get_ml_training_data(self) -> List[Dict[str, Any]]:
        """
        Get ML training data (Level 10 only).

        Returns:
            List of ML training samples
        """
        return self.ml_collector.get_training_data()

    async def cleanup(self) -> None:
        """Clean up resources including Phase 2 components."""
        try:
            # Close price service
            await self.price_service.close()

            # PHASE 2: Clean up DEX comparator
            if self.dex_comparator:
                try:
                    if hasattr(self.dex_comparator, 'cleanup'):
                        await self.dex_comparator.cleanup()
                        self.logger.info("[INTEL SLIDER] DEX comparator cleaned up")
                except Exception as dex_cleanup_error:
                    self.logger.error(
                        f"[INTEL SLIDER] Error cleaning up DEX comparator: "
                        f"{dex_cleanup_error}"
                    )

            # PHASE 2: Clean up arbitrage detector
            if self.arbitrage_detector:
                try:
                    if hasattr(self.arbitrage_detector, 'cleanup'):
                        await self.arbitrage_detector.cleanup()
                        self.logger.info("[INTEL SLIDER] Arbitrage detector cleaned up")
                except Exception as arb_cleanup_error:
                    self.logger.error(
                        f"[INTEL SLIDER] Error cleaning up arbitrage detector: "
                        f"{arb_cleanup_error}"
                    )

            self.logger.info("[INTEL SLIDER] Cleanup complete")
        except Exception as cleanup_error:
            self.logger.error(
                f"[INTEL SLIDER] Cleanup error: {cleanup_error}",
                exc_info=True
            )
