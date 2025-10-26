"""
Intel Slider System for Paper Trading Bot - MAIN ORCHESTRATOR
This module provides the main IntelSliderEngine that coordinates all intelligence
components using composition for clean separation of concerns.
Integrates with real price feeds and market data for accurate trading decisions.
File: dexproject/paper_trading/intelligence/intel_slider.py
"""
import logging
import asyncio
from decimal import Decimal
from typing import Dict, Any, Optional, List
from datetime import datetime
# Django imports for timezone-aware datetimes
from django.utils import timezone
# Import price feed service for real data
from paper_trading.services.price_feed_service import PriceFeedService
# Import base classes and data structures
from paper_trading.intelligence.base import (
    IntelligenceEngine,
    IntelligenceLevel,
    MarketContext,
    TradingDecision
)
# Import configuration
from paper_trading.intelligence.intel_config import INTEL_CONFIGS, IntelLevelConfig
# Import price history
from paper_trading.intelligence.price_history import PriceHistory
# Import analyzers
from paper_trading.intelligence.analyzers import CompositeMarketAnalyzer
from paper_trading.intelligence.decision_maker import DecisionMaker
from paper_trading.intelligence.ml_features import MLFeatureCollector
# Import type utilities
from paper_trading.utils.type_utils import TypeConverter, MarketDataNormalizer
logger = logging.getLogger(__name__)
class IntelSliderEngine(IntelligenceEngine):
    """
    Main intelligence engine controlled by the Intel slider (1-10).
    
    This engine coordinates all intelligence components using composition:
    - CompositeMarketAnalyzer: Comprehensive market analysis with real blockchain data
    - DecisionMaker: Makes trading decisions based on intel level
    - MLFeatureCollector: Collects training data for Level 10
    
    The engine adapts its behavior based on the intelligence level,
    providing a simple interface while handling complex decision-making.
    
    Attributes:
        config: Intelligence level configuration
        intel_level: Current intelligence level (1-10)
        composite_analyzer: Handles comprehensive market analysis
        decision_maker: Makes trading decisions
        ml_collector: Collects ML training data (Level 10)
        price_service: Service for fetching token prices
        price_history_cache: Cache of historical prices
        market_history: Historical market contexts
        price_trends: Tracked price trends
        volatility_tracker: Volatility tracking data
        historical_decisions: Past trading decisions
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
        
        # Initialize price service for real data
        self.price_service = PriceFeedService(chain_id=chain_id)
        
        # Initialize components via composition
        self.composite_analyzer = CompositeMarketAnalyzer()
        self.decision_maker = DecisionMaker(self.config, intel_level)
        self.ml_collector = MLFeatureCollector(intel_level)
        
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
        
        Args:
            strategy_config: Database strategy configuration
        """
        try:
            self.logger.info(
                f"[CONFIG] Applying overrides: {strategy_config.name}"
            )
            
            # Override confidence threshold
            if strategy_config.confidence_threshold:
                self.config.min_confidence_required = Decimal(
                    str(strategy_config.confidence_threshold)
                )
                self.logger.info(
                    f"[CONFIG] Confidence: {self.config.min_confidence_required}%"
                )
            
            # Override max position size
            if strategy_config.max_position_size_percent:
                self.config.max_position_percent = Decimal(
                    str(strategy_config.max_position_size_percent)
                )
                self.logger.info(
                    f"[CONFIG] Max position: {self.config.max_position_percent}%"
                )
            
            # Override risk tolerance based on trading mode
            if strategy_config.trading_mode == 'CONSERVATIVE':
                self.config.risk_tolerance = Decimal('30')
            elif strategy_config.trading_mode == 'AGGRESSIVE':
                self.config.risk_tolerance = Decimal('70')
            elif strategy_config.trading_mode == 'MODERATE':
                self.config.risk_tolerance = Decimal('50')
            
            self.logger.info(
                f"[CONFIG] Risk tolerance: {self.config.risk_tolerance}%"
            )
            
        except Exception as e:
            self.logger.error(
                f"[CONFIG] Error applying overrides: {e}",
                exc_info=True
            )
    
    async def analyze_market(
        self,
        market_context: MarketContext
    ) -> MarketContext:
        """
        Analyze market conditions and enhance the market context.
        
        This method implements the abstract method from IntelligenceEngine.
        It performs comprehensive market analysis including:
        - Gas analysis (network conditions)
        - Liquidity analysis (pool depth, slippage)
        - Volatility analysis (price movements, trends)
        - MEV analysis (threat assessment)
        - Price history tracking
        
        Args:
            market_context: Initial market context with basic token info
            
        Returns:
            Enhanced market context with comprehensive analysis data
            
        Raises:
            Exception: If critical analysis components fail
        """
        try:
            self.logger.info(
                f"[ANALYZE_MARKET] Starting market analysis for {market_context.token_symbol}"
            )
            
            # Step 1: Run comprehensive market analysis using CompositeMarketAnalyzer
            comprehensive_analysis = await self.composite_analyzer.run_comprehensive_analysis(
                token_address=market_context.token_address or "",
                token_symbol=market_context.token_symbol,
                current_price=market_context.current_price
            )
            
            self.logger.debug(
                f"[ANALYZE_MARKET] Comprehensive analysis complete: "
                f"Quality={comprehensive_analysis.get('data_quality', 'UNKNOWN')}"
            )
            
            # Step 2: Fetch and update real token price
            try:
                real_price = await self.price_service.get_token_price(
                    token_address=market_context.token_address or "",
                    token_symbol=market_context.token_symbol
                )
                
                if real_price and real_price > Decimal('0'):
                    market_context.current_price = real_price
                    self.logger.info(
                        f"[ANALYZE_MARKET] Updated price for {market_context.token_symbol}: "
                        f"${real_price:.6f}"
                    )
                else:
                    self.logger.warning(
                        f"[ANALYZE_MARKET] Could not fetch price for {market_context.token_symbol}, "
                        "using context price"
                    )
            except Exception as price_error:
                self.logger.error(
                    f"[ANALYZE_MARKET] Price fetch failed: {price_error}",
                    exc_info=True
                )
            
            # Step 3: Update price history
            price_history = self._update_price_history(
                market_context.token_symbol,
                market_context.current_price
            )
            
            # Step 4: Enhance market context with all analysis data
            enhanced_context = self._enhance_market_context(
                market_context,
                comprehensive_analysis,
                price_history
            )
            
            # Step 5: Update market tracking
            self.update_market_context(enhanced_context)
            
            self.logger.info(
                f"[ANALYZE_MARKET] Market analysis complete for {market_context.token_symbol}: "
                f"Gas={enhanced_context.gas_price_gwei:.2f}gwei, "
                f"Liquidity=${enhanced_context.pool_liquidity_usd:.0f}, "
                f"MEV={enhanced_context.mev_threat_level:.1f}"
            )
            
            return enhanced_context
            
        except Exception as e:
            self.logger.error(
                f"[ANALYZE_MARKET] Critical error analyzing market: {e}",
                exc_info=True
            )
            # Return original context if analysis fails
            return market_context
    
    async def make_decision(
        self,
        market_context: MarketContext,
        portfolio_value: Optional[Decimal] = None,
        account_balance: Optional[Decimal] = None,
        existing_positions: Optional[List[Any]] = None,
        token_address: Optional[str] = None,
        token_symbol: Optional[str] = None
    ) -> TradingDecision:
        """
        Make a trading decision based on analyzed market context.
        
        This method implements the abstract method from IntelligenceEngine.
        It uses the DecisionMaker to create a trading decision and then
        applies intel-level adjustments.
        
        BACKWARD COMPATIBILITY: Accepts both 'portfolio_value' and 'account_balance'
        parameters for compatibility with different calling conventions. Also accepts
        legacy parameters (existing_positions, token_address, token_symbol) which
        are handled gracefully but not currently used in decision logic.
        
        Args:
            market_context: Analyzed market context with comprehensive data
            portfolio_value: Current portfolio value in USD (preferred parameter)
            account_balance: Current account balance (legacy parameter, maps to portfolio_value)
            existing_positions: List of existing positions (legacy parameter, for future use)
            token_address: Token address (legacy parameter, already in market_context)
            token_symbol: Token symbol (legacy parameter, already in market_context)
            
        Returns:
            Complete trading decision with reasoning and execution strategy
            
        Raises:
            Exception: If decision-making fails critically
        """
        try:
            # Handle backward compatibility: map account_balance to portfolio_value
            if portfolio_value is None and account_balance is not None:
                portfolio_value = account_balance
                self.logger.debug(
                    f"[MAKE_DECISION] Using account_balance as portfolio_value: ${account_balance:.2f}"
                )
            elif portfolio_value is None:
                portfolio_value = Decimal('10000')  # Default fallback
                self.logger.warning(
                    "[MAKE_DECISION] No portfolio_value or account_balance provided, using default $10,000"
                )
            
            # Log if legacy parameters were provided
            if existing_positions is not None:
                self.logger.debug(
                    f"[MAKE_DECISION] Received {len(existing_positions)} existing positions (for future use)"
                )
            if token_address and token_address != market_context.token_address:
                self.logger.debug(
                    f"[MAKE_DECISION] Token address parameter provided but using value from market_context"
                )
            if token_symbol and token_symbol != market_context.token_symbol:
                self.logger.debug(
                    f"[MAKE_DECISION] Token symbol parameter provided but using value from market_context"
                )
            
            self.logger.info(
                f"[MAKE_DECISION] Creating decision for {market_context.token_symbol} "
                f"(Portfolio: ${portfolio_value:.2f})"
            )
            
            # Step 1: Check if we should skip due to poor data quality
            if market_context.confidence_in_data < 40.0:
                self.logger.warning(
                    f"[MAKE_DECISION] Low data confidence ({market_context.confidence_in_data:.1f}%), "
                    "skipping trade"
                )
                return self._create_skip_decision(
                    market_context,
                    f"Data confidence too low: {market_context.confidence_in_data:.1f}%"
                )
            
            # Step 2: Build decision using DecisionMaker components
            decision = self._build_decision_from_context(
                market_context,
                portfolio_value
            )
            
            self.logger.debug(
                f"[MAKE_DECISION] Base decision: {decision.action}, "
                f"Confidence={decision.overall_confidence}%, "
                f"Risk={decision.risk_score}, "
                f"Opportunity={decision.opportunity_score}"
            )
            
            # Step 4: Apply intel adjustments (if available)
            try:
                adjusted_decision = self.apply_intel_adjustments(decision) if hasattr(self, 'apply_intel_adjustments') else decision
                self.logger.debug("[MAKE_DECISION] Intel adjustments: " + ("applied" if hasattr(self, 'apply_intel_adjustments') else "skipped (not available)"))
            except Exception as e:
                self.logger.warning(f"[MAKE_DECISION] Intel adjustment failed: {e}")
                adjusted_decision = decision
            
            # Step 5: Store decision in history
            self.historical_decisions.append(adjusted_decision)
            if len(self.historical_decisions) > 100:
                self.historical_decisions.pop(0)
            
            # Step 6: Collect ML features if Level 10
            if self.intel_level == 10:
                try:
                    self.ml_collector.collect_features(
                        market_context=market_context,
                        decision=adjusted_decision
                    )
                    self.logger.debug(
                        f"[MAKE_DECISION] ML features collected for training"
                    )
                except Exception as ml_error:
                    self.logger.warning(
                        f"[MAKE_DECISION] ML feature collection failed: {ml_error}"
                    )
            
            self.logger.info(
                f"[MAKE_DECISION] Final decision for {market_context.token_symbol}: "
                f"{adjusted_decision.action} "
                f"(Size: {adjusted_decision.position_size_percent}%, "
                f"Confidence: {adjusted_decision.overall_confidence}%)"
            )
            
            return adjusted_decision
            
        except Exception as e:
            self.logger.error(
                f"[MAKE_DECISION] Critical error making decision: {e}",
                exc_info=True
            )
            # Return skip decision if decision-making fails
            return self._create_skip_decision(
                market_context,
                f"Decision-making error: {str(e)}"
            )
    
    def _build_decision_from_context(
        self,
        market_context: MarketContext,
        portfolio_value: Decimal
    ) -> TradingDecision:
        """Build TradingDecision by orchestrating DecisionMaker components."""
        # Build comprehensive analysis dict from context
        comp_analysis = {
            'gas_analysis': {'current_gas_gwei': float(market_context.gas_price_gwei), 'network_congestion': market_context.network_congestion},
            'liquidity': {'pool_liquidity_usd': float(market_context.pool_liquidity_usd), 'expected_slippage_percent': float(market_context.expected_slippage), 'liquidity_depth_score': market_context.liquidity_depth_score},
            'volatility': {'volatility_index': market_context.volatility_index, 'trend_direction': market_context.trend_direction},
            'mev_analysis': {'threat_level': market_context.mev_threat_level, 'sandwich_attack_risk': market_context.sandwich_risk, 'frontrun_probability': market_context.frontrun_probability},
            'market_state': {'chaos_event_detected': market_context.chaos_event_detected}
        }
        
        # Calculate scores
        risk_score = self.decision_maker.calculate_risk_score(market_context, comp_analysis)
        opp_score = self.decision_maker.calculate_opportunity_score(market_context, comp_analysis)
        conf_score = self.decision_maker.calculate_confidence_score(risk_score, opp_score, market_context)
        action = self.decision_maker.determine_action(risk_score, opp_score, conf_score, market_context)
        
        # Position sizing
        pos_pct = Decimal('0')
        pos_usd = Decimal('0')
        if action == 'BUY':
            pos_pct = self.decision_maker.calculate_position_size(opp_score, risk_score, portfolio_value)
            pos_usd = (pos_pct / Decimal('100')) * portfolio_value
        
        # Execution parameters
        stop_loss = self.decision_maker.calculate_stop_loss(risk_score)
        exec_mode, priv_relay, gas_strat, max_gas = self.decision_maker.determine_execution_strategy(market_context, risk_score)
        
        # Reasoning
        reason = self.decision_maker.generate_reasoning(action, risk_score, opp_score, conf_score, market_context)
        risk_facts = self.decision_maker.identify_risk_factors(market_context)
        opp_facts = self.decision_maker.identify_opportunity_factors(market_context)
        mitigations = self.decision_maker.generate_mitigation_strategies(market_context)
        time_sens = self.decision_maker.assess_time_sensitivity(market_context)
        
        return TradingDecision(
            action=action, token_address=market_context.token_address or "", token_symbol=market_context.token_symbol,
            position_size_percent=pos_pct, position_size_usd=pos_usd, stop_loss_percent=stop_loss, take_profit_targets=[],
            execution_mode=exec_mode, use_private_relay=priv_relay, gas_strategy=gas_strat, max_gas_price_gwei=max_gas,
            overall_confidence=conf_score, risk_score=risk_score, opportunity_score=opp_score, primary_reasoning=reason,
            risk_factors=risk_facts, opportunity_factors=opp_facts, mitigation_strategies=mitigations,
            intel_level_used=self.intel_level, intel_adjustments={}, time_sensitivity=time_sens,
            max_execution_time_ms=5000 if time_sens == 'critical' else 15000, processing_time_ms=0
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
            enhanced_context = await self.analyze_market(market_context)
            
            # Step 2: Make trading decision based on analysis
            decision = await self.make_decision(enhanced_context, portfolio_value)
            
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
            
        except Exception as e:
            self.logger.error(
                f"[ANALYZE] Fatal error in analysis pipeline: {e}",
                exc_info=True
            )
            
            # Return safe skip decision
            return self._create_skip_decision(
                market_context,
                f"Analysis pipeline error: {str(e)}"
            )
    
    def _update_price_history(
        self,
        token_symbol: str,
        current_price: Decimal
    ) -> Optional[PriceHistory]:
        """Update price history for a token."""
        try:
            if token_symbol not in self.price_history_cache:
                self.price_history_cache[token_symbol] = PriceHistory(token_symbol)
            
            price_history = self.price_history_cache[token_symbol]
            price_history.add_price(current_price)
            
            self.logger.debug(
                f"[PRICE HISTORY] Updated for {token_symbol}: "
                f"{len(price_history.prices)} data points"
            )
            
            return price_history
            
        except Exception as e:
            self.logger.error(
                f"[PRICE HISTORY] Error updating: {e}",
                exc_info=True
            )
            return None
    
    def _enhance_market_context(
        self,
        context: MarketContext,
        comprehensive_analysis: Dict[str, Any],
        price_history: Optional[PriceHistory] = None
    ) -> MarketContext:
        """
        Enhance market context with comprehensive analysis and price history.
        
        Args:
            context: Market context to enhance
            comprehensive_analysis: Results from CompositeMarketAnalyzer
            price_history: Price history data (if available)
            
        Returns:
            Enhanced market context
        """
        try:
            # Extract analysis components
            gas_analysis = comprehensive_analysis.get('gas_analysis', {})
            liquidity_analysis = comprehensive_analysis.get('liquidity', {})
            volatility_analysis = comprehensive_analysis.get('volatility', {})
            mev_analysis = comprehensive_analysis.get('mev_analysis', {})
            market_state = comprehensive_analysis.get('market_state', {})
            composite_scores = comprehensive_analysis.get('composite_scores', {})
            
            # Update gas and network data
            if gas_analysis:
                context.gas_price_gwei = Decimal(str(gas_analysis.get('current_gas_gwei', 0)))
                context.network_congestion = float(gas_analysis.get('network_congestion', 0))
            
            # Update liquidity data
            if liquidity_analysis:
                context.pool_liquidity_usd = Decimal(str(liquidity_analysis.get('pool_liquidity_usd', 0)))
                context.expected_slippage = Decimal(str(liquidity_analysis.get('expected_slippage_percent', 0)))
                context.liquidity_depth_score = float(liquidity_analysis.get('liquidity_depth_score', 0))
            
            # Update volatility data
            if volatility_analysis:
                context.volatility_index = float(volatility_analysis.get('volatility_index', 0))
                context.trend_direction = volatility_analysis.get('trend_direction', 'neutral')
                context.volatility = Decimal(str(volatility_analysis.get('volatility_index', 0))) / Decimal('100')
            
            # Update MEV data
            if mev_analysis:
                context.mev_threat_level = float(mev_analysis.get('threat_level', 0))
                context.sandwich_risk = float(mev_analysis.get('sandwich_attack_risk', 0))
                context.frontrun_probability = float(mev_analysis.get('frontrun_probability', 0))
            
            # Update market state
            if market_state:
                context.chaos_event_detected = market_state.get('chaos_event_detected', False)
            
            # Update confidence in data
            data_quality = comprehensive_analysis.get('data_quality', 'POOR')
            quality_map = {
                'EXCELLENT': 100.0,
                'GOOD': 80.0,
                'FAIR': 60.0,
                'POOR': 40.0
            }
            context.confidence_in_data = quality_map.get(data_quality, 50.0)
            
            # Enhance with price history if available
            if price_history and len(price_history.prices) >= 2:
                # Set historical price
                context.price_24h_ago = price_history.prices[0]
                
                # Calculate momentum
                price_change = price_history.get_price_change_percent(60)
                if price_change is not None:
                    context.momentum = price_change
                
                # Determine trend (price history takes priority over volatility analysis)
                if price_history.is_trending_up():
                    context.trend = 'bullish'
                    context.trend_direction = 'bullish'
                elif price_history.is_trending_down():
                    context.trend = 'bearish'
                    context.trend_direction = 'bearish'
            
            self.logger.debug(
                f"[ENHANCE] Context enhanced for {context.token_symbol}: "
                f"Gas={context.gas_price_gwei:.2f} gwei, "
                f"Liquidity=${context.pool_liquidity_usd:.0f}, "
                f"MEV threat={context.mev_threat_level:.1f}, "
                f"Data quality={data_quality}"
            )
            
            return context
            
        except Exception as e:
            self.logger.error(
                f"[ENHANCE] Error enhancing context: {e}",
                exc_info=True
            )
            return context
    
    def _create_skip_decision(
        self,
        context: MarketContext,
        reason: str
    ) -> TradingDecision:
        """
        Create a SKIP decision with given reason.
        
        Args:
            context: Market context
            reason: Reason for skipping
            
        Returns:
            SKIP trading decision
        """
        return TradingDecision(
            action='SKIP',
            token_address=context.token_address or "",
            token_symbol=context.token_symbol,
            position_size_percent=Decimal('0'),
            position_size_usd=Decimal('0'),
            stop_loss_percent=None,
            take_profit_targets=[],
            execution_mode='NONE',
            use_private_relay=False,
            gas_strategy='standard',
            max_gas_price_gwei=Decimal('30'),
            overall_confidence=Decimal('0'),
            risk_score=Decimal('100'),
            opportunity_score=Decimal('0'),
            primary_reasoning=reason,
            risk_factors=[],
            opportunity_factors=[],
            mitigation_strategies=[],
            intel_level_used=self.intel_level,
            intel_adjustments={},
            time_sensitivity='low',
            max_execution_time_ms=0,
            processing_time_ms=0
        )
    
    def _track_performance(self, metrics: Dict[str, Any]) -> None:
        """
        Track performance metrics for analysis.
        
        Args:
            metrics: Performance metrics dictionary
        """
        try:
            self.performance_history.append(metrics)
            
            # Keep only last 200 metrics
            if len(self.performance_history) > 200:
                self.performance_history.pop(0)
            
            self.logger.debug(
                f"[PERFORMANCE] Tracked metrics: {metrics['action']} decision, "
                f"{metrics['processing_time_ms']:.2f}ms"
            )
            
        except Exception as e:
            self.logger.error(
                f"[PERFORMANCE] Error tracking metrics: {e}",
                exc_info=True
            )
    
    def update_market_context(self, market_context: MarketContext) -> None:
        """
        Update market context tracking for historical analysis.
        
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
            
        except Exception as e:
            self.logger.error(
                f"[MARKET CONTEXT] Error updating: {e}",
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
        """Clean up resources."""
        try:
            await self.price_service.close()
            self.logger.info("[INTEL SLIDER] Cleanup complete")
        except Exception as e:
            self.logger.error(f"[INTEL SLIDER] Cleanup error: {e}", exc_info=True)