"""
Market State Analyzer for Trading Conditions

Analyzes overall market state and conditions by:
- Evaluating market sentiment (bullish, bearish, neutral)
- Assessing trading conditions quality
- Calculating market stability
- Determining optimal trading windows

File: dexproject/paper_trading/intelligence/analyzers/market_state.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional

# Import base analyzer
from paper_trading.intelligence.analyzers.base import BaseAnalyzer

logger = logging.getLogger(__name__)


class MarketStateAnalyzer(BaseAnalyzer):
    """
    Analyzes overall market state and conditions.

    Evaluates:
    - Market sentiment (bullish, bearish, neutral)
    - Trading conditions quality
    - Market stability
    - Optimal trading windows

    Provides holistic market assessment for decision making.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize market state analyzer.

        Args:
            config: Optional configuration for market state parameters
        """
        super().__init__(config)

    async def analyze(
        self,
        token_address: str,
        volatility_index: float = 30.0,
        trend_direction: str = 'neutral',
        volume_24h: Decimal = Decimal('50000'),
        **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze current market state.

        Args:
            token_address: Token address
            volatility_index: Volatility index (0-100)
            trend_direction: Price trend ('bullish', 'bearish', 'neutral')
            volume_24h: 24-hour trading volume
            **kwargs: Additional parameters

        Returns:
            Dictionary containing market state analysis:
            - market_sentiment: Overall sentiment (bullish/bearish/neutral/uncertain)
            - trading_conditions: Quality of trading conditions (excellent/good/fair/poor)
            - market_stability: Stability score (0-100, higher is more stable)
            - optimal_for_trading: Boolean indicating if conditions are favorable
            - data_quality: Data quality indicator
            - data_source: Source of the analysis
        """
        try:
            # Determine market sentiment from trend and volatility
            sentiment = self._determine_sentiment(trend_direction, volatility_index)

            # Assess trading conditions based on volatility and volume
            conditions = self._assess_trading_conditions(
                volatility_index,
                float(volume_24h)
            )

            # Calculate stability score (inverse of volatility)
            stability = self._calculate_stability(volatility_index)

            # Determine if conditions are optimal for trading
            optimal = self._is_optimal_for_trading(
                sentiment,
                conditions,
                stability
            )

            self.logger.info(
                f"[MARKET] State: {sentiment} sentiment, "
                f"{conditions} conditions, {stability:.0f}% stable"
            )

            return {
                'market_sentiment': sentiment,
                'trading_conditions': conditions,
                'market_stability': stability,
                'optimal_for_trading': optimal,
                'data_quality': 'GOOD',
                'data_source': 'composite_analysis'
            }

        except Exception as e:
            self.logger.error(f"Error in market state analysis: {e}", exc_info=True)
            return {
                'market_sentiment': 'unknown',
                'trading_conditions': 'unknown',
                'market_stability': None,
                'optimal_for_trading': False,
                'data_quality': 'ERROR',
                'data_source': 'error',
                'error': f'Market state analysis failed: {str(e)}'
            }

    def _determine_sentiment(
        self,
        trend_direction: str,
        volatility_index: float
    ) -> str:
        """
        Determine overall market sentiment.

        High volatility makes sentiment uncertain regardless of trend direction.
        Otherwise, sentiment follows the price trend.

        Args:
            trend_direction: Price trend direction (bullish/bearish/neutral)
            volatility_index: Volatility level (0-100)

        Returns:
            Sentiment: 'bullish', 'bearish', 'neutral', or 'uncertain'
        """
        if volatility_index > 60:
            return 'uncertain'  # Too volatile to determine clear sentiment

        return trend_direction  # Use trend as primary sentiment indicator

    def _assess_trading_conditions(
        self,
        volatility_index: float,
        volume_24h: float
    ) -> str:
        """
        Assess overall trading conditions.

        Good conditions require moderate volatility and healthy trading volume.
        High volatility or low volume indicate poor trading conditions.

        Args:
            volatility_index: Volatility level (0-100)
            volume_24h: 24-hour volume in USD

        Returns:
            Conditions: 'excellent', 'good', 'fair', or 'poor'
        """
        # Good conditions = moderate volatility + healthy volume
        if volatility_index < 20 and volume_24h > 100000:
            return 'excellent'
        elif volatility_index < 40 and volume_24h > 50000:
            return 'good'
        elif volatility_index < 60:
            return 'fair'
        else:
            return 'poor'

    def _calculate_stability(self, volatility_index: float) -> float:
        """
        Calculate market stability score.

        Stability is the inverse of volatility - lower volatility means
        higher stability and vice versa.

        Args:
            volatility_index: Volatility level (0-100)

        Returns:
            Stability score (0-100, higher is more stable)
        """
        # Stability is inverse of volatility
        return 100.0 - volatility_index

    def _is_optimal_for_trading(
        self,
        sentiment: str,
        conditions: str,
        stability: float
    ) -> bool:
        """
        Determine if conditions are optimal for trading.

        Optimal conditions require:
        - Clear positive sentiment (bullish or neutral)
        - Good or excellent trading conditions
        - Stable market (>50% stability)

        Args:
            sentiment: Market sentiment
            conditions: Trading conditions
            stability: Market stability score

        Returns:
            True if conditions are favorable for trading
        """
        # Optimal conditions: clear sentiment, good conditions, stable market
        return (
            sentiment in ['bullish', 'neutral'] and
            conditions in ['excellent', 'good'] and
            stability > 50
        )