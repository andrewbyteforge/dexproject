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
    
    async def analyze(
        self,
        market_context: MarketContext,
        portfolio_value: Decimal = Decimal('10000')
    ) -> TradingDecision:
        """
        Main entry point: Analyze market and make trading decision.
        
        This method coordinates all components to:
        1. Run comprehensive market analysis (gas, liquidity, MEV, volatility)
        2. Fetch real token price
        3. Build enhanced market context
        4. Calculate risk and opportunity scores
        5. Make trading decision
        6. Collect ML features (if Level 10)
        
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
            
            # Step 1: Fetch real price from price service
            real_price = await self.price_service.get_token_price_usd(
                market_context.token_address
            )
            
            if real_price and real_price > 0:
                market_context.current_price = Decimal(str(real_price))
                self._update_price_history(
                    market_context.token_address,
                    market_context.token_symbol,
                    market_context.current_price
                )
                self.logger.info(
                    f"[ANALYZE] Real price for {market_context.token_symbol}: "
                    f"${market_context.current_price:.6f}"
                )
            else:
                self.logger.warning(
                    f"[ANALYZE] Could not fetch real price for {market_context.token_symbol}"
                )
            
            # Step 2: Get price history for trend analysis
            price_history = self.price_history_cache.get(market_context.token_address)
            
            # Step 3: Run comprehensive market analysis using CompositeMarketAnalyzer
            comprehensive_analysis = await self.composite_analyzer.analyze_comprehensive(
                token_address=market_context.token_address,
                trade_size_usd=Decimal('1000'),  # Default trade size for analysis
                liquidity_usd=market_context.pool_liquidity_usd if market_context.pool_liquidity_usd > 0 else None,
                volume_24h=market_context.volume_24h if market_context.volume_24h > 0 else None,
                chain_id=self.chain_id,
                price_history=[p for p in price_history.prices] if price_history else None,
                current_price=market_context.current_price if market_context.current_price > 0 else None
            )
            
            self.logger.debug(
                f"[ANALYZE] Comprehensive analysis complete: "
                f"Data quality={comprehensive_analysis.get('data_quality', 'UNKNOWN')}"
            )
            
            # Step 4: Enhance market context with analysis results and price history
            market_context = self._enhance_context_with_analysis(
                market_context,
                comprehensive_analysis,
                price_history
            )
            
            # Step 5: Calculate scores using decision maker
            risk_score = self.decision_maker.calculate_risk_score(
                market_context,
                comprehensive_analysis
            )
            
            opportunity_score = self.decision_maker.calculate_opportunity_score(
                market_context,
                comprehensive_analysis
            )
            
            confidence_score = self.decision_maker.calculate_confidence_score(
                risk_score,
                opportunity_score,
                market_context
            )
            
            # Step 6: Determine action
            action = self.decision_maker.determine_action(
                risk_score,
                opportunity_score,
                confidence_score,
                market_context
            )
            
            # Step 7: Calculate position size and stop loss
            position_size_percent = self.decision_maker.calculate_position_size(
                risk_score,
                opportunity_score,
                market_context
            )
            
            stop_loss_percent = self.decision_maker.calculate_stop_loss(risk_score)
            
            # Step 8: Calculate USD position size
            position_size_usd = self.converter.safe_percentage(
                portfolio_value,
                position_size_percent
            )
            
            # Enforce minimum position size
            if position_size_usd < self.config.min_position_usd:
                if action == 'BUY':
                    self.logger.info(
                        f"[ANALYZE] Position size ${position_size_usd:.2f} below "
                        f"minimum ${self.config.min_position_usd:.2f}, adjusting to SKIP"
                    )
                    action = 'SKIP'
            
            # Step 9: Determine execution strategy
            execution_strategy = self.decision_maker.determine_execution_strategy(
                market_context,
                action
            )
            
            # Step 10: Generate reasoning and factors
            reasoning = self.decision_maker.generate_reasoning(
                action,
                risk_score,
                opportunity_score,
                confidence_score,
                market_context
            )
            
            risk_factors = self.decision_maker.identify_risk_factors(market_context)
            opportunity_factors = self.decision_maker.identify_opportunity_factors(
                market_context
            )
            mitigation_strategies = self.decision_maker.generate_mitigation_strategies(
                market_context
            )
            time_sensitivity = self.decision_maker.assess_time_sensitivity(market_context)
            
            # Step 11: Build trading decision
            decision = TradingDecision(
                action=action,
                token_address=market_context.token_address,
                token_symbol=market_context.token_symbol,
                position_size_percent=position_size_percent,
                position_size_usd=position_size_usd,
                stop_loss_percent=stop_loss_percent,
                take_profit_targets=[
                    Decimal('5'),   # 5% profit
                    Decimal('10'),  # 10% profit
                    Decimal('20')   # 20% profit
                ],
                execution_mode=execution_strategy['mode'],
                use_private_relay=execution_strategy['use_private_relay'],
                gas_strategy=execution_strategy['gas_strategy'],
                max_gas_price_gwei=execution_strategy['max_gas_gwei'],
                overall_confidence=confidence_score,
                risk_score=risk_score,
                opportunity_score=opportunity_score,
                primary_reasoning=reasoning,
                risk_factors=risk_factors,
                opportunity_factors=opportunity_factors,
                mitigation_strategies=mitigation_strategies,
                intel_level_used=self.intel_level,
                intel_adjustments={},
                time_sensitivity=time_sensitivity,
                max_execution_time_ms=5000 if time_sensitivity == 'critical' else 10000,
                processing_time_ms=0
            )
            
            # Step 12: Apply intel level adjustments
            decision = self.adjust_for_intel_level(decision)
            
            # Step 13: Calculate processing time
            end_time = timezone.now()
            decision.processing_time_ms = (
                (end_time - start_time).total_seconds() * 1000
            )
            
            # Step 14: Store decision history
            self.historical_decisions.append(decision)
            if len(self.historical_decisions) > 100:
                self.historical_decisions.pop(0)
            
            # Step 15: Update market context tracking
            self.update_market_context(market_context)
            
            # Step 16: Collect ML features (Level 10 only)
            self.ml_collector.collect_features(market_context, decision)
            
            # Log final decision
            self.logger.info(
                f"[ANALYZE] Decision complete for {market_context.token_symbol}: "
                f"Action={action}, Risk={risk_score:.1f}, "
                f"Opportunity={opportunity_score:.1f}, "
                f"Confidence={confidence_score:.1f}, "
                f"Processing={decision.processing_time_ms:.0f}ms"
            )
            
            return decision
            
        except Exception as e:
            self.logger.error(
                f"[ANALYZE] Error analyzing {market_context.token_symbol}: {e}",
                exc_info=True
            )
            
            # Return safe SKIP decision on error
            return self._create_skip_decision(
                market_context,
                f"Error during analysis: {str(e)}"
            )
    
    def _update_price_history(
        self,
        token_address: str,
        token_symbol: str,
        price: Decimal
    ) -> None:
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
            
            # Keep only last 100 prices
            if len(history.prices) > 100:
                history.prices.pop(0)
                history.timestamps.pop(0)
            
            self.logger.debug(
                f"[PRICE HISTORY] Updated {token_symbol}: "
                f"{len(history.prices)} prices tracked"
            )
            
        except Exception as e:
            self.logger.error(
                f"[PRICE HISTORY] Error updating: {e}",
                exc_info=True
            )
    
    def _enhance_context_with_analysis(
        self,
        context: MarketContext,
        comprehensive_analysis: Dict[str, Any],
        price_history: Optional[PriceHistory]
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
            token_address=context.token_address,
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