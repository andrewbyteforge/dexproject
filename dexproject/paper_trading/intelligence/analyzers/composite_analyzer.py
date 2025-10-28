"""
Composite Market Analyzer - Orchestrates All Analysis Components

Coordinates all market analysis components to provide comprehensive intelligence:
- Gas analysis (network conditions)
- Liquidity analysis (pool depth)
- Volatility analysis (price movements)
- MEV analysis (threat detection)
- Market state analysis (overall conditions)

Combines results and calculates composite scores for informed trading decisions.

File: dexproject/paper_trading/intelligence/analyzers/composite_analyzer.py
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional, List

# Import base analyzer
from paper_trading.intelligence.analyzers.base import BaseAnalyzer

# Import all specific analyzers
from paper_trading.intelligence.analyzers.gas_analyzer import RealGasAnalyzer
from paper_trading.intelligence.analyzers.liquidity_analyzer import RealLiquidityAnalyzer
from paper_trading.intelligence.analyzers.volatility_analyzer import RealVolatilityAnalyzer
from paper_trading.intelligence.analyzers.mev_detector import MEVThreatDetector
from paper_trading.intelligence.analyzers.market_state import MarketStateAnalyzer

logger = logging.getLogger(__name__)


class CompositeMarketAnalyzer(BaseAnalyzer):
    """
    Composite analyzer that coordinates all market analysis components.

    Combines:
    - Gas analysis (network conditions)
    - Liquidity analysis (pool depth)
    - Volatility analysis (price movements)
    - MEV analysis (threat detection)
    - Market state analysis (overall conditions)

    Provides comprehensive market intelligence for informed trading decisions.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize composite analyzer with all sub-analyzers.

        Args:
            config: Optional configuration for sub-analyzers
        """
        super().__init__(config)

        # Initialize all sub-analyzers with shared config
        self.gas_analyzer = RealGasAnalyzer(config)
        self.liquidity_analyzer = RealLiquidityAnalyzer(config)
        self.volatility_analyzer = RealVolatilityAnalyzer(config)
        self.mev_detector = MEVThreatDetector(config)
        self.market_state = MarketStateAnalyzer(config)

    async def analyze_comprehensive(
        self,
        token_address: str,
        chain_id: int = 8453,
        trade_size_usd: Decimal = Decimal('1000'),
        price_history: Optional[List[Dict[str, Any]]] = None,
        current_price: Optional[Decimal] = None,
        liquidity_usd: Optional[Decimal] = None,
        volume_24h: Optional[Decimal] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Perform comprehensive market analysis using all analyzers.

        Args:
            token_address: Token to analyze
            chain_id: Blockchain network ID (default: 8453 for Base Mainnet)
            trade_size_usd: Intended trade size in USD
            price_history: Historical price data (optional, will be queried if needed)
            current_price: Current token price (optional)
            liquidity_usd: Pool liquidity in USD (optional, will be queried if not provided)
            volume_24h: 24-hour trading volume (optional)
            **kwargs: Additional parameters

        Returns:
            Dictionary with all analysis results and composite scores:
            - token_address: Token being analyzed
            - chain_id: Chain ID
            - timestamp: Analysis timestamp
            - gas_analysis: Gas analysis results
            - liquidity: Liquidity analysis results
            - volatility: Volatility analysis results
            - mev_analysis: MEV analysis results
            - market_state: Market state analysis results
            - composite_scores: Combined risk/opportunity scores
            - data_quality: Overall data quality assessment
        """
        try:
            self.logger.info(
                f"[COMPOSITE] Running REAL DATA analysis for {token_address[:10]}... "
                f"on chain {chain_id}"
            )

            # Run gas analysis first (provides network context)
            gas_analysis = await self.gas_analyzer.analyze(
                token_address,
                chain_id=chain_id
            )

            # Run liquidity analysis (may query blockchain if liquidity_usd not provided)
            liquidity_analysis = await self.liquidity_analyzer.analyze(
                token_address,
                chain_id=chain_id,
                trade_size_usd=trade_size_usd
            )

            # Use queried liquidity if we didn't have it
            if liquidity_usd is None and liquidity_analysis['pool_liquidity_usd'] is not None:
                liquidity_usd = Decimal(str(liquidity_analysis['pool_liquidity_usd']))
            elif liquidity_usd is None:
                liquidity_usd = Decimal('0')

            # Run volatility analysis with price history
            volatility_analysis = await self.volatility_analyzer.analyze(
                token_address,
                price_history=price_history,
                current_price=current_price or Decimal('0')
            )

            # Run MEV analysis with real market data
            mev_analysis = await self.mev_detector.analyze(
                token_address,
                liquidity_usd=liquidity_usd,
                volume_24h=volume_24h or Decimal('50000'),
                trade_size_usd=trade_size_usd
            )

            # Get volatility values for market state (handle None values)
            volatility_index = volatility_analysis.get('volatility_index')
            if volatility_index is None:
                volatility_index = 0.0

            trend_direction = volatility_analysis.get('trend_direction', 'unknown')

            # Run market state analysis
            market_analysis = await self.market_state.analyze(
                token_address,
                volatility_index=volatility_index,
                trend_direction=trend_direction,
                volume_24h=volume_24h or Decimal('50000')
            )

            # Combine results
            result = {
                'token_address': token_address,
                'chain_id': chain_id,
                'timestamp': datetime.now().isoformat(),
                'gas_analysis': gas_analysis,
                'liquidity': liquidity_analysis,
                'volatility': volatility_analysis,
                'mev_analysis': mev_analysis,
                'market_state': market_analysis,
                'composite_scores': self._calculate_composite_scores(
                    gas_analysis,
                    liquidity_analysis,
                    volatility_analysis,
                    mev_analysis,
                    market_analysis
                ),
                'data_quality': self._assess_overall_quality(
                    gas_analysis,
                    liquidity_analysis,
                    volatility_analysis,
                    mev_analysis
                )
            }

            quality = result['data_quality']
            self.logger.info(
                f"[COMPOSITE] ✅ REAL DATA analysis complete for {token_address[:10]}... "
                f"Quality: {quality}"
            )

            return result

        except Exception as e:
            self.logger.error(f"Error in comprehensive analysis: {e}", exc_info=True)
            raise

    async def analyze(
        self,
        token_address: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Backward-compatible analyze method that calls analyze_comprehensive.

        This method exists for compatibility with code that calls .analyze()
        instead of .analyze_comprehensive().

        Args:
            token_address: Token to analyze
            **kwargs: Additional parameters passed to analyze_comprehensive

        Returns:
            Complete market analysis from analyze_comprehensive
        """
        return await self.analyze_comprehensive(token_address, **kwargs)

    def _calculate_composite_scores(
        self,
        gas: Dict[str, Any],
        liquidity: Dict[str, Any],
        volatility: Dict[str, Any],
        mev: Dict[str, Any],
        market: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate composite risk/opportunity scores from all analyses.

        Weights different factors based on their importance:
        - Risk: MEV (30%), volatility (25%), liquidity (30%), gas (15%)
        - Opportunity: Liquidity (40%), stability (20%), MEV (20%), gas (20%)

        Args:
            gas: Gas analysis results
            liquidity: Liquidity analysis results
            volatility: Volatility analysis results
            mev: MEV analysis results
            market: Market state analysis results

        Returns:
            Dictionary with composite scores:
            - overall_risk: Combined risk score (0-100, lower is better)
            - overall_opportunity: Combined opportunity score (0-100, higher is better)
            - overall_confidence: Trading confidence score (0-100, higher is better)
            - favorable_conditions: Boolean indicating if conditions are favorable
        """
        # Get values, handling None cases
        network_congestion = gas.get('network_congestion', 0) or 0
        threat_level = mev.get('threat_level', 0) or 0
        volatility_index = volatility.get('volatility_index', 0) or 0
        liquidity_depth_score = liquidity.get('liquidity_depth_score', 0) or 0

        # Calculate overall risk (lower is better)
        # High risk from: high congestion, high MEV threat, high volatility, low liquidity
        risk_score = (
            network_congestion * 0.15 +
            threat_level * 0.30 +
            volatility_index * 0.25 +
            (100 - liquidity_depth_score) * 0.30
        )

        # Calculate overall opportunity (higher is better)
        # High opportunity from: high liquidity, low volatility, low MEV threat, low congestion
        opportunity_score = (
            liquidity_depth_score * 0.40 +
            (100 - volatility_index) * 0.20 +
            (100 - threat_level) * 0.20 +
            (100 - network_congestion) * 0.20
        )

        # Calculate overall confidence (balance of opportunity vs risk)
        confidence_score = (opportunity_score - risk_score + 100) / 2

        return {
            'overall_risk': round(risk_score, 2),
            'overall_opportunity': round(opportunity_score, 2),
            'overall_confidence': round(confidence_score, 2),
            'favorable_conditions': opportunity_score > 60 and risk_score < 40
        }

    def _assess_overall_quality(
        self,
        gas_analysis: Dict[str, Any],
        liquidity_analysis: Dict[str, Any],
        volatility_analysis: Dict[str, Any],
        mev_analysis: Dict[str, Any]
    ) -> str:
        """
        Assess overall data quality across all analyzers.

        Takes the worst-case approach: if any analyzer has poor data,
        the overall quality is downgraded accordingly.

        Args:
            gas_analysis: Gas analysis results
            liquidity_analysis: Liquidity analysis results
            volatility_analysis: Volatility analysis results
            mev_analysis: MEV analysis results

        Returns:
            Overall quality rating: EXCELLENT, GOOD, FAIR, POOR, NO_DATA, ERROR
        """
        qualities = [
            gas_analysis.get('data_quality', 'UNKNOWN'),
            liquidity_analysis.get('data_quality', 'UNKNOWN'),
            volatility_analysis.get('data_quality', 'UNKNOWN'),
            mev_analysis.get('data_quality', 'UNKNOWN')
        ]

        # Check for error states first
        if 'ERROR' in qualities:
            return 'ERROR'

        # Check for missing data
        if 'NO_DATA' in qualities or 'NO_POOL_FOUND' in qualities:
            return 'NO_DATA'

        # Count excellent/good sources
        excellent_count = qualities.count('EXCELLENT')
        good_count = excellent_count + qualities.count('GOOD')

        if excellent_count >= 3:
            return 'EXCELLENT'
        elif good_count >= 3:
            return 'GOOD'
        elif good_count >= 2:
            return 'FAIR'
        else:
            return 'POOR'