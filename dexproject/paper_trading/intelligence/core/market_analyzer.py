"""
Market Analyzer for Intel Slider System
Handles market context building and enhancement with comprehensive analysis.

This module orchestrates:
- Market condition analysis
- Context enhancement with analyzer results
- Integration of gas, liquidity, volatility, and MEV data
- Data quality validation

File: dexproject/paper_trading/intelligence/core/market_analyzer.py
"""
import logging
from decimal import Decimal
from typing import Dict, Any, Optional

from paper_trading.intelligence.core.base import MarketContext
from paper_trading.intelligence.data.price_history import PriceHistory


logger = logging.getLogger(__name__)


class MarketAnalyzer:
    """
    Analyzes market conditions and enhances market context with comprehensive data.

    This class coordinates with CompositeMarketAnalyzer to build complete
    market contexts with all necessary data for decision-making.

    Attributes:
        composite_analyzer: CompositeMarketAnalyzer instance
        chain_id: Chain ID for blockchain data
        logger: Logger instance for structured logging
    """

    def __init__(self, composite_analyzer: Any, chain_id: int = 84532):
        """
        Initialize the Market Analyzer.

        Args:
            composite_analyzer: CompositeMarketAnalyzer instance
            chain_id: Chain ID for market analysis (default: Base Sepolia 84532)
        """
        self.composite_analyzer = composite_analyzer
        self.chain_id = chain_id
        self.logger = logger

    async def analyze_market(
        self,
        token_address: str
    ) -> MarketContext:
        """
        Analyze market conditions for a token.

        This method creates a market context and enhances it with
        comprehensive analysis from all available analyzers.

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
            # Note: token_symbol will be updated by analyzer
            market_context = MarketContext(
                token_address=token_address,
                token_symbol="UNKNOWN",
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
            # Enhance market context with ALL analysis results
            if analysis_result:
                market_context = self.enhance_context_with_analysis(
                    market_context=market_context,
                    analysis_result=analysis_result,
                    price_history=None
                )

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

    def enhance_context_with_analysis(
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