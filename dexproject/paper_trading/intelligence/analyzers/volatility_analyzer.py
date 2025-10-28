"""
Real Volatility Analyzer for Price Movements

Analyzes price volatility using REAL historical price data by:
- Calculating historical volatility from price movements
- Determining price trends and momentum
- Computing volatility indices and risk metrics
- Categorizing volatility levels for risk management

File: dexproject/paper_trading/intelligence/analyzers/volatility_analyzer.py
"""

import logging
import math
from decimal import Decimal
from typing import Dict, Any, Optional, List, Union, cast

# Import base analyzer and defaults
from paper_trading.intelligence.analyzers.base import BaseAnalyzer
from paper_trading.defaults import IntelligenceDefaults

logger = logging.getLogger(__name__)


class RealVolatilityAnalyzer(BaseAnalyzer):
    """
    Analyzes price volatility using REAL historical price data.

    Calculates:
    - Historical volatility from price movements
    - Price trends and momentum
    - Volatility indices
    - Risk metrics

    This provides accurate volatility assessment for risk management.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize volatility analyzer.

        Args:
            config: Optional configuration with volatility parameters
                   Example: {'lookback_periods': [24, 48, 168]}
        """
        super().__init__(config)

        # Volatility configuration
        self.lookback_periods = config.get('lookback_periods', [24, 48, 168]) if config else [24, 48, 168]
        self.volatility_thresholds = {
            'low': Decimal('5.0'),      # < 5% volatility
            'medium': Decimal('15.0'),  # 5-15% volatility
            'high': Decimal('30.0'),    # 15-30% volatility
            'extreme': Decimal('50.0')  # > 30% volatility
        }

    async def analyze(
        self,
        token_address: str,
        price_history: Optional[List[Dict[str, Any]]] = None,
        current_price: Decimal = Decimal('0'),
        **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze token price volatility.

        Args:
            token_address: Token contract address
            price_history: List of historical price data points
                         Each point: {'timestamp': int, 'price': Decimal}
                         Can also accept a list of Decimal prices directly
            current_price: Current token price
            **kwargs: Additional parameters

        Returns:
            Dictionary containing volatility analysis:
            - volatility_index: Overall volatility score (0-100)
            - volatility_percent: Historical volatility percentage
            - trend_direction: 'bullish', 'bearish', or 'neutral'
            - price_momentum: Momentum score (-100 to +100)
            - volatility_category: 'low', 'medium', 'high', or 'extreme'
            - data_points: Number of price points analyzed
            - data_quality: Data quality indicator
            - data_source: Source of the data
        """
        try:
            # Use empty list if price_history is None
            price_history = price_history or []

            if not price_history or len(price_history) < 2:
                # No price data - cannot calculate real volatility
                self.logger.warning(
                    "[VOLATILITY] No price history available - cannot calculate volatility"
                )

                # Check if we should skip trade on missing data
                if IntelligenceDefaults.SKIP_TRADE_ON_MISSING_DATA:
                    return {
                        'volatility_index': None,
                        'volatility_percent': None,
                        'trend_direction': 'unknown',
                        'price_momentum': None,
                        'volatility_category': 'unknown',
                        'data_points': 0,
                        'data_quality': 'NO_DATA',
                        'data_source': 'none',
                        'error': 'Insufficient price history for volatility calculation'
                    }

                # If real data not required, return minimal data
                return {
                    'volatility_index': 0.0,
                    'volatility_percent': 0.0,
                    'trend_direction': 'unknown',
                    'price_momentum': 0.0,
                    'volatility_category': 'unknown',
                    'data_points': 0,
                    'data_quality': 'INSUFFICIENT_DATA',
                    'data_source': 'none'
                }

            # Calculate historical volatility
            volatility_percent = self._calculate_historical_volatility(price_history)

            # Determine trend direction
            trend = self._determine_trend(price_history, current_price)

            # Calculate momentum
            momentum = self._calculate_momentum(price_history)

            # Calculate volatility index (0-100)
            volatility_index = self._calculate_volatility_index(volatility_percent)

            # Categorize volatility
            category = self._categorize_volatility(volatility_percent)

            self.logger.info(
                f"[VOLATILITY] ✅ Real data: {volatility_percent:.1f}% "
                f"({category}), Trend: {trend}"
            )

            return {
                'volatility_index': volatility_index,
                'volatility_percent': float(volatility_percent),
                'trend_direction': trend,
                'price_momentum': momentum,
                'volatility_category': category,
                'data_points': len(price_history),
                'data_quality': 'EXCELLENT',
                'data_source': 'historical_prices'
            }

        except Exception as e:
            self.logger.error(f"[VOLATILITY] Error analyzing volatility: {e}", exc_info=True)
            # No fallback - return error state
            return {
                'volatility_index': None,
                'volatility_percent': None,
                'trend_direction': 'unknown',
                'price_momentum': None,
                'volatility_category': 'unknown',
                'data_points': 0,
                'data_quality': 'ERROR',
                'data_source': 'error',
                'error': f'Volatility analysis failed: {str(e)}'
            }

    def _calculate_historical_volatility(
        self,
        price_history: Union[List[Decimal], List[Dict[str, Any]]]
    ) -> Decimal:
        """
        Calculate historical volatility from price data.
        
        Handles two formats:
        - List of Decimal prices directly
        - List of dicts with 'price' key
        
        Args:
            price_history: Either list of Decimal prices or list of dicts with 'price' key
            
        Returns:
            Volatility as percentage (annualized)
        """
        if not price_history or len(price_history) < 2:
            return Decimal('0')  # Return 0 if insufficient data
        
        # Extract prices - ensure we always get List[Decimal]
        prices: List[Decimal] = []
        
        if isinstance(price_history[0], dict):
            # Extract from dict format - cast to tell Pylance the type
            dict_history = cast(List[Dict[str, Any]], price_history)
            prices = [Decimal(str(point['price'])) for point in dict_history]
        elif isinstance(price_history[0], Decimal):
            # Already Decimals - cast to tell Pylance the type
            decimal_history = cast(List[Decimal], price_history)
            prices = list(decimal_history)
        else:
            # Fallback: try to convert whatever format we have
            prices = [Decimal(str(p)) for p in price_history]
        
        # Validate we have prices after extraction
        if not prices or len(prices) < 2:
            return Decimal('0')
        
        # Calculate returns (percentage changes)
        returns: List[Decimal] = []
        for i in range(1, len(prices)):
            if prices[i-1] > Decimal('0'):
                ret = (prices[i] - prices[i-1]) / prices[i-1]
                returns.append(ret)
        
        if not returns:
            return Decimal('0')
        
        # Calculate standard deviation of returns
        mean_return = sum(returns) / Decimal(len(returns))
        variance = sum((r - mean_return) ** 2 for r in returns) / Decimal(len(returns))
        
        # Use math.sqrt for proper Decimal type handling
        std_dev = Decimal(str(math.sqrt(float(variance))))
        
        # Annualize (assuming hourly data, convert to annual)
        # sqrt(8760 hours per year) ≈ 93.6
        annual_volatility = std_dev * Decimal('93.6') * Decimal('100')
        
        return annual_volatility

    def _determine_trend(
        self,
        price_history: Union[List[Decimal], List[Dict[str, Any]]],
        current_price: Decimal
    ) -> str:
        """
        Determine price trend direction.

        Accepts either:
        - List[Decimal] (prices), or
        - List[Dict[str, Any]] where each dict has key 'price'.

        Args:
            price_history: Historical price points
            current_price: Current price

        Returns:
            Trend: 'bullish', 'bearish', or 'neutral'
        """
        # Normalize to a list of Decimal prices
        prices: List[Decimal] = []

        if not price_history:
            return 'neutral'

        first_item = price_history[0]
        if isinstance(first_item, dict):
            dict_history = cast(List[Dict[str, Any]], price_history)
            prices = [Decimal(str(point['price'])) for point in dict_history]
        elif isinstance(first_item, Decimal):
            decimal_history = cast(List[Decimal], price_history)
            prices = list(decimal_history)
        else:
            prices = [Decimal(str(p)) for p in price_history]

        if not prices:
            return 'neutral'

        avg_price = sum(prices) / Decimal(len(prices))

        if current_price == 0:
            current_price = prices[-1]

        if avg_price <= 0:
            return 'neutral'

        price_change_percent = ((current_price - avg_price) / avg_price) * Decimal('100')

        if price_change_percent > Decimal('5'):
            return 'bullish'
        if price_change_percent < Decimal('-5'):
            return 'bearish'
        return 'neutral'

    def _calculate_momentum(
        self,
        price_history: Union[List[Decimal], List[Dict[str, Any]]]
    ) -> float:
        """
        Calculate price momentum score.

        Accepts either:
        - List[Decimal] (prices), or
        - List[Dict[str, Any]] where each dict has key 'price'.

        Returns:
            Momentum score from -100 (strong bearish) to +100 (strong bullish)
        """
        if len(price_history) < 2:
            return 0.0

        # Normalize to a list of Decimal prices
        prices: List[Decimal]
        first_item = price_history[0]

        if isinstance(first_item, dict):
            dict_history = cast(List[Dict[str, Any]], price_history)
            prices = [Decimal(str(point['price'])) for point in dict_history]
        elif isinstance(first_item, Decimal):
            decimal_history = cast(List[Decimal], price_history)
            prices = list(decimal_history)
        else:
            prices = [Decimal(str(p)) for p in price_history]

        if len(prices) < 2:
            return 0.0

        first_price = prices[0]
        last_price = prices[-1]

        if first_price == 0:
            return 0.0

        # Percentage change
        percent_change = ((last_price - first_price) / first_price) * Decimal('100')

        # Map ±50% change to ±100 momentum, clamp to [-100, 100]
        momentum_dec = max(
            Decimal('-100'),
            min(Decimal('100'), percent_change * Decimal('2'))
        )
        return float(momentum_dec)

    def _calculate_volatility_index(self, volatility_percent: Decimal) -> float:
        """
        Convert volatility percentage to index score (0-100).

        Args:
            volatility_percent: Volatility percentage

        Returns:
            Volatility index from 0 (stable) to 100 (extremely volatile)
        """
        # Map volatility to 0-100 scale
        # 0% volatility = 0 index
        # 50%+ volatility = 100 index
        index = float(min(Decimal('100'), (volatility_percent / Decimal('50')) * Decimal('100')))
        return index

    def _categorize_volatility(self, volatility_percent: Decimal) -> str:
        """
        Categorize volatility level.

        Args:
            volatility_percent: Volatility percentage

        Returns:
            Category: 'low', 'medium', 'high', or 'extreme'
        """
        if volatility_percent < self.volatility_thresholds['low']:
            return 'low'
        elif volatility_percent < self.volatility_thresholds['medium']:
            return 'medium'
        elif volatility_percent < self.volatility_thresholds['high']:
            return 'high'
        else:
            return 'extreme'