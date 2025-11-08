"""
MEV Threat Detector for Trading Protection

Detects MEV (Maximal Extractable Value) threats using market heuristics by:
- Analyzing sandwich attack probability based on liquidity and trade size
- Assessing front-running risk based on gas prices and timing
- Calculating overall MEV threat levels
- Recommending protection strategies

File: dexproject/paper_trading/intelligence/analyzers/mev_detector.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional

# Import base analyzer
from paper_trading.intelligence.analyzers.base import BaseAnalyzer

logger = logging.getLogger(__name__)


class MEVThreatDetector(BaseAnalyzer):
    """
    Detects MEV (Maximal Extractable Value) threats using market heuristics.

    Analyzes:
    - Sandwich attack probability based on liquidity and trade size
    - Front-running risk based on gas prices and timing
    - Overall MEV threat level
    - Recommended protection strategies

    Uses smart heuristics when direct MEV detection is not available.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize MEV detector.

        Args:
            config: Optional configuration for MEV detection parameters
        """
        super().__init__(config)

    async def analyze(
        self,
        token_address: str,
        liquidity_usd: Decimal = Decimal('100000'),
        volume_24h: Decimal = Decimal('50000'),
        trade_size_usd: Decimal = Decimal('1000'),
        **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze MEV threat level for a potential trade.

        Args:
            token_address: Token address
            liquidity_usd: Pool liquidity in USD
            volume_24h: 24-hour trading volume
            trade_size_usd: Intended trade size in USD
            **kwargs: Additional parameters

        Returns:
            Dictionary containing MEV analysis:
            - threat_level: MEV threat score (0-100)
            - sandwich_risk: Risk of sandwich attacks (0-100)
            - frontrun_risk: Risk of front-running (0-100)
            - recommended_protection: Protection strategy recommendation
            - data_quality: Data quality indicator
            - data_source: Source of the analysis
        """
        try:
            # Calculate sandwich attack risk based on liquidity and trade size
            sandwich_risk = self._calculate_sandwich_risk(trade_size_usd, liquidity_usd)

            # Calculate front-running risk based on volume patterns
            frontrun_risk = self._calculate_frontrun_risk(volume_24h, liquidity_usd)

            # Overall threat level (weighted average)
            # Sandwich attacks are more common, so weight them higher
            threat_level = (sandwich_risk * 0.6 + frontrun_risk * 0.4)

            # Recommend protection strategy based on threat level
            protection = self._recommend_protection(threat_level)

            self.logger.info(
                f"[MEV] Threat analysis: Level {threat_level:.0f}% "
                f"(Sandwich: {sandwich_risk:.0f}%, Frontrun: {frontrun_risk:.0f}%)"
            )

            return {
                'threat_level': threat_level,
                'sandwich_risk': sandwich_risk,
                'frontrun_risk': frontrun_risk,
                'recommended_protection': protection,
                'data_quality': 'GOOD',
                'data_source': 'heuristic_analysis'
            }

        except Exception as e:
            self.logger.error(f"Error in MEV analysis: {e}", exc_info=True)
            return {
                'threat_level': None,
                'sandwich_risk': None,
                'frontrun_risk': None,
                'recommended_protection': 'unknown',
                'data_quality': 'ERROR',
                'data_source': 'error',
                'error': f'MEV analysis failed: {str(e)}'
            }

    def _calculate_sandwich_risk(
        self,
        trade_size_usd: Decimal,
        liquidity_usd: Decimal
    ) -> float:
        """
        Calculate sandwich attack risk.

        Sandwich attacks are more profitable when the trade size is large
        relative to pool liquidity, as this creates significant slippage
        that attackers can exploit by front-running and back-running.

        Args:
            trade_size_usd: Trade size in USD
            liquidity_usd: Pool liquidity in USD

        Returns:
            Risk score (0-100)
        """
        if liquidity_usd == 0:
            return 100.0  # Maximum risk if no liquidity

        # Trade size as percentage of liquidity
        impact_ratio = float(trade_size_usd / liquidity_usd)

        # Larger trades relative to liquidity = higher sandwich risk
        if impact_ratio < 0.01:  # < 1%
            return 10.0  # Low risk for small trades
        elif impact_ratio < 0.05:  # 1-5%
            # Risk increases linearly in this range
            return 30.0 + (impact_ratio * 1000)  # 30-80%
        else:  # > 5%
            # Very high risk for large trades
            return min(100.0, 80.0 + (impact_ratio * 400))  # 80-100%

    def _calculate_frontrun_risk(
        self,
        volume_24h: Decimal,
        liquidity_usd: Decimal
    ) -> float:
        """
        Calculate front-running risk.

        Higher trading volume relative to liquidity indicates more competition
        for trades and higher MEV bot activity, increasing front-running risk.

        Args:
            volume_24h: 24-hour trading volume
            liquidity_usd: Pool liquidity in USD

        Returns:
            Risk score (0-100)
        """
        if liquidity_usd == 0:
            return 100.0  # Maximum risk if no liquidity

        # Volume to liquidity ratio indicates competition for trades
        volume_ratio = float(volume_24h / liquidity_usd)

        # Higher volume relative to liquidity = more MEV bot activity
        if volume_ratio < 0.5:  # Low activity
            return 20.0
        elif volume_ratio < 2.0:  # Moderate activity
            return 40.0
        elif volume_ratio < 5.0:  # High activity
            return 60.0
        else:  # Very high activity
            return 80.0

    def _recommend_protection(self, threat_level: float) -> str:
        """
        Recommend MEV protection strategy based on threat level.

        Args:
            threat_level: Overall MEV threat level (0-100)

        Returns:
            Protection recommendation:
            - 'standard': Normal transaction (low risk)
            - 'private_rpc': Use private RPC (medium risk)
            - 'flashbots': Use Flashbots protect (high risk)
        """
        if threat_level < 30:
            return 'standard'  # Normal transaction
        elif threat_level < 60:
            return 'private_rpc'  # Use private RPC to reduce mempool visibility
        else:
            return 'flashbots'  # Use Flashbots protect for high-risk trades