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

File: dexproject/paper_trading/intelligence/core/intel_slider_engine.py
"""
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List, Type

from django.utils import timezone

from paper_trading.services.price_feed_service import PriceFeedService

from paper_trading.intelligence.core.base import (
    IntelligenceEngine,
    MarketContext,
    TradingDecision
)

# Import configuration
from paper_trading.intelligence.config.intel_config import INTEL_CONFIGS, IntelLevelConfig

# Import analyzers
from paper_trading.intelligence.analyzers import CompositeMarketAnalyzer
from paper_trading.intelligence.strategies.decision_maker import DecisionMaker
from paper_trading.intelligence.data.ml_features import MLFeatureCollector

# Import type utilities
from paper_trading.utils.type_utils import TypeConverter, MarketDataNormalizer

# Import core components
from paper_trading.intelligence.core.position_manager import PositionManager
from paper_trading.intelligence.core.dex_operations import DEXOperations
from paper_trading.intelligence.core.market_analyzer import MarketAnalyzer
from paper_trading.intelligence.core.decision_engine import DecisionEngine
from paper_trading.intelligence.core.data_tracker import DataTracker

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
    - DecisionEngine: Orchestrates trading decisions
    - PositionManager: Enforces position limits
    - MarketAnalyzer: Builds and enhances market contexts
    - DEXOperations (Phase 2): Multi-DEX comparison and arbitrage
    - DataTracker: Historical data and ML features
    - MLFeatureCollector: Collects training data for Level 10

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
        decision_engine: Orchestrates decision-making
        position_manager: Enforces position limits
        market_analyzer: Builds market contexts
        dex_operations: Multi-DEX operations (Phase 2)
        data_tracker: Historical data tracking
        ml_collector: Collects ML training data (Level 10)
        price_service: Service for fetching token prices
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

        # Initialize composite analyzer
        self.composite_analyzer = CompositeMarketAnalyzer()

        # Initialize core components
        self.position_manager = PositionManager(strategy_config=strategy_config)

        # Initialize ML collector
        self.ml_collector = MLFeatureCollector(intel_level)

        # Initialize decision maker
        decision_maker = DecisionMaker(
            config=self.config,
            intel_level=intel_level,
            strategy_config=strategy_config
        )

        # Initialize decision engine
        self.decision_engine = DecisionEngine(
            decision_maker=decision_maker,
            ml_collector=self.ml_collector,
            intel_level=intel_level
        )

        # Initialize market analyzer
        self.market_analyzer = MarketAnalyzer(
            composite_analyzer=self.composite_analyzer,
            chain_id=chain_id
        )

        # Initialize data tracker
        self.data_tracker = DataTracker()

        # PHASE 2: Initialize DEX operations
        dex_comparator_instance: Optional[Any] = None
        arbitrage_detector_instance: Optional[Any] = None

        if PHASE_2_AVAILABLE and DEXPriceComparator is not None and ArbitrageDetector is not None:
            try:
                dex_comparator_instance = DEXPriceComparator(chain_id=chain_id)
                arbitrage_detector_instance = ArbitrageDetector()
                self.logger.info(
                    "[INTEL SLIDER] Phase 2 components initialized: "
                    "DEX comparison + Arbitrage detection"
                )
            except Exception as init_error:
                self.logger.warning(
                    f"[INTEL SLIDER] Failed to initialize Phase 2 components: {init_error}"
                )
                dex_comparator_instance = None
                arbitrage_detector_instance = None
        else:
            self.logger.info("[INTEL SLIDER] Phase 2 not available, running in Phase 1 mode")

        self.dex_operations = DEXOperations(
            dex_comparator=dex_comparator_instance,
            arbitrage_detector=arbitrage_detector_instance,
            chain_id=chain_id
        )

        # Utility classes
        self.converter = TypeConverter()
        self.normalizer = MarketDataNormalizer()

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

    async def make_decision(
        self,
        market_context: MarketContext,
        account_balance: Decimal,
        existing_positions: List[Any],
        portfolio_value: Optional[Decimal] = None,
        token_address: Optional[str] = None,
        token_symbol: Optional[str] = None,
        position_entry_price: Optional[Decimal] = None,
        position_current_value: Optional[Decimal] = None,
        position_invested: Optional[Decimal] = None,
        position_hold_time_hours: Optional[float] = None
    ) -> TradingDecision:
        """
        Make a trading decision based on analyzed market context.

        PHASE 1: Now checks position limits before making BUY decisions.

        Args:
            market_context: Analyzed market context with comprehensive data
            account_balance: Current account balance in USD
            existing_positions: List of existing positions
            portfolio_value: DEPRECATED - uses account_balance instead
            token_address: DEPRECATED - already in market_context
            token_symbol: DEPRECATED - already in market_context
            position_entry_price: Optional entry price for position evaluation
            position_current_value: Optional current value for position evaluation
            position_invested: Optional invested amount for position evaluation
            position_hold_time_hours: Optional hold time for position evaluation

        Returns:
            Complete trading decision with reasoning and execution strategy
        """
        try:
            # Use account_balance as the primary portfolio value
            portfolio_val = account_balance

            # PHASE 1: Check position limits before making BUY decision
            if existing_positions is not None and len(existing_positions) > 0:
                can_buy, position_reason = self.position_manager.check_position_limits(
                    market_context,
                    existing_positions,
                    portfolio_val
                )

                if not can_buy:
                    self.logger.warning(
                        f"[MAKE_DECISION] Position limit reached for "
                        f"{market_context.token_symbol}, returning SKIP decision"
                    )
                    return self.decision_engine.create_skip_decision(
                        market_context,
                        f"Position limit: {position_reason}"
                    )
                else:
                    self.logger.debug(
                        f"[MAKE_DECISION] Position check passed: {position_reason}"
                    )

            # Delegate to decision engine
            return await self.decision_engine.make_decision(
                market_context=market_context,
                account_balance=account_balance,
                existing_positions=existing_positions,
                portfolio_value=portfolio_value,
                token_address=token_address,
                token_symbol=token_symbol,
                position_entry_price=position_entry_price,
                position_current_value=position_current_value,
                position_invested=position_invested,
                position_hold_time_hours=position_hold_time_hours
            )

        except Exception as decision_error:
            self.logger.error(
                f"[MAKE_DECISION] Error in make_decision: {decision_error}",
                exc_info=True
            )
            return self.decision_engine.create_skip_decision(
                market_context,
                f"Decision error: {str(decision_error)}"
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

        Args:
            market_context: Current market context for the token
            position_data: Information about the existing position
            account_balance: Current account balance
            existing_positions: All existing positions

        Returns:
            TradingDecision with SELL, HOLD, or SKIP action
        """
        return await self.decision_engine.evaluate_position_exit(
            market_context=market_context,
            position_data=position_data,
            account_balance=account_balance,
            existing_positions=existing_positions
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
        return await self.market_analyzer.analyze_market(token_address)

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
            self.data_tracker.track_performance({
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
            return self.decision_engine.create_skip_decision(
                market_context,
                f"Analysis pipeline error: {str(analyze_error)}"
            )

    def update_market_context(self, market_context: MarketContext) -> None:
        """
        Update market tracking with new context.

        Args:
            market_context: Market context to track
        """
        self.data_tracker.update_market_context(market_context)

    def get_ml_training_data(self) -> List[Dict[str, Any]]:
        """
        Get ML training data (Level 10 only).

        Returns:
            List of ML training samples
        """
        return self.decision_engine.get_ml_training_data()

    async def cleanup(self) -> None:
        """Clean up resources including Phase 2 components."""
        try:
            # Close price service
            await self.price_service.close()

            # Clean up DEX operations (Phase 2)
            await self.dex_operations.cleanup()

            self.logger.info("[INTEL SLIDER] Cleanup complete")

        except Exception as cleanup_error:
            self.logger.error(
                f"[INTEL SLIDER] Cleanup error: {cleanup_error}",
                exc_info=True
            )