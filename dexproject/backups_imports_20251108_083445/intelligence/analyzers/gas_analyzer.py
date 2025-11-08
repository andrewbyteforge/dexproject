"""
Real Gas Analyzer for Network Conditions

Analyzes network gas conditions using REAL blockchain data by:
- Querying current gas prices from pending blocks
- Extracting base fee and priority fee (EIP-1559)
- Calculating network congestion levels
- Categorizing gas costs for trading decisions

File: dexproject/paper_trading/intelligence/analyzers/gas_analyzer.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional

# Import base analyzer and defaults
from paper_trading.intelligence.analyzers.base import BaseAnalyzer
from paper_trading.defaults import IntelligenceDefaults

logger = logging.getLogger(__name__)


class RealGasAnalyzer(BaseAnalyzer):
    """
    Analyzes network gas conditions using REAL blockchain data.

    Queries the blockchain for:
    - Current gas prices from pending blocks
    - Base fee and priority fee (EIP-1559 networks)
    - Network congestion levels
    - Gas cost categorization

    This provides accurate gas assessment for optimal trade timing.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize gas analyzer with optional configuration.

        Args:
            config: Optional configuration with gas thresholds
                   Example: {'gas_thresholds': {'low': 0.5, 'medium': 2.0, ...}}
        """
        super().__init__(config)

        # Gas price thresholds (in gwei) - can be overridden per chain or via config
        self.gas_thresholds = {
            'low': Decimal('0.5'),      # < 0.5 gwei = Low gas
            'medium': Decimal('2.0'),   # 0.5-2 gwei = Medium gas
            'high': Decimal('5.0'),     # 2-5 gwei = High gas
            'extreme': Decimal('10.0')  # > 5 gwei = Extreme gas
        }

        # Override with config if provided
        if config and 'gas_thresholds' in config:
            self.gas_thresholds.update(config['gas_thresholds'])

    async def analyze(
        self,
        token_address: str,
        chain_id: int = 8453,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze current gas conditions on the blockchain.

        Args:
            token_address: Token address (for context, not used in gas analysis)
            chain_id: Blockchain network ID (default: 8453 for Base Mainnet)
            **kwargs: Additional parameters

        Returns:
            Dictionary containing gas analysis:
            - gas_price_gwei: Current gas price in gwei
            - base_fee_gwei: Base fee (EIP-1559)
            - priority_fee_gwei: Priority fee (EIP-1559)
            - network_congestion: Congestion level (0-100)
            - cost_category: 'low', 'medium', 'high', or 'extreme'
            - data_quality: Data quality indicator (EXCELLENT, NO_DATA, ERROR)
            - data_source: Source of the data ('blockchain_rpc', 'none', 'error')
        """
        try:
            # Try to get real blockchain data via Web3 client
            web3_client = await self._ensure_web3_client(chain_id)

            if web3_client:
                # Get latest block for gas price information
                latest_block = web3_client.web3.eth.get_block('latest')

                # Extract gas prices (EIP-1559 format)
                base_fee = Decimal(str(latest_block.get('baseFeePerGas', 0))) / Decimal('1e9')  # Wei to Gwei
                gas_price = web3_client.web3.eth.gas_price
                gas_price_gwei = Decimal(str(gas_price)) / Decimal('1e9')

                # Calculate priority fee (for EIP-1559 chains)
                priority_fee_gwei = max(Decimal('0'), gas_price_gwei - base_fee)

                # Calculate network congestion based on gas price
                congestion = self._calculate_congestion(gas_price_gwei)

                # Categorize gas cost
                category = self._categorize_gas_cost(gas_price_gwei)

                self.logger.info(
                    f"[GAS] ✅ Real data: {gas_price_gwei:.2f} gwei "
                    f"({category}), Congestion: {congestion:.0f}%"
                )

                return {
                    'gas_price_gwei': float(gas_price_gwei),
                    'base_fee_gwei': float(base_fee),
                    'priority_fee_gwei': float(priority_fee_gwei),
                    'network_congestion': congestion,
                    'cost_category': category,
                    'data_quality': 'EXCELLENT',
                    'data_source': 'blockchain_rpc'
                }

            else:
                # Web3 not available - cannot provide real data
                self.logger.error(
                    "[GAS] Web3 unavailable and REQUIRE_REAL_GAS_DATA=True - "
                    "Cannot analyze without real data"
                )
                
                # Check if we should skip trade on missing data
                if IntelligenceDefaults.SKIP_TRADE_ON_MISSING_DATA:
                    return {
                        'gas_price_gwei': None,
                        'base_fee_gwei': None,
                        'priority_fee_gwei': None,
                        'network_congestion': None,
                        'cost_category': 'unknown',
                        'data_quality': 'NO_DATA',
                        'data_source': 'none',
                        'error': 'Real gas data unavailable - Web3 not connected'
                    }

                # Return zero values if missing data is acceptable
                self.logger.warning("[GAS] Web3 unavailable - cannot get real data")
                return {
                    'gas_price_gwei': 0.0,
                    'base_fee_gwei': 0.0,
                    'priority_fee_gwei': 0.0,
                    'network_congestion': 0.0,
                    'cost_category': 'unknown',
                    'data_quality': 'NO_DATA',
                    'data_source': 'none'
                }

        except Exception as e:
            self.logger.error(f"Error analyzing gas: {e}", exc_info=True)
            return {
                'gas_price_gwei': None,
                'base_fee_gwei': None,
                'priority_fee_gwei': None,
                'network_congestion': None,
                'cost_category': 'unknown',
                'data_quality': 'ERROR',
                'data_source': 'error',
                'error': f'Gas analysis failed: {str(e)}'
            }

    def _calculate_congestion(self, gas_price_gwei: Decimal) -> float:
        """
        Calculate network congestion level from gas price.

        Maps gas prices to congestion levels using configured thresholds.
        Lower gas prices indicate lower congestion and vice versa.

        Args:
            gas_price_gwei: Current gas price in gwei

        Returns:
            Congestion level from 0 (empty) to 100 (completely congested)
        """
        # Map gas price to congestion level using thresholds
        if gas_price_gwei <= self.gas_thresholds['low']:
            # 0-20% congestion for low gas prices
            ratio = float(gas_price_gwei / self.gas_thresholds['low'])
            return min(20.0, ratio * 20.0)

        elif gas_price_gwei <= self.gas_thresholds['medium']:
            # 20-50% congestion for medium gas prices
            ratio = float(
                (gas_price_gwei - self.gas_thresholds['low']) /
                (self.gas_thresholds['medium'] - self.gas_thresholds['low'])
            )
            return 20.0 + (ratio * 30.0)

        elif gas_price_gwei <= self.gas_thresholds['high']:
            # 50-80% congestion for high gas prices
            ratio = float(
                (gas_price_gwei - self.gas_thresholds['medium']) /
                (self.gas_thresholds['high'] - self.gas_thresholds['medium'])
            )
            return 50.0 + (ratio * 30.0)

        else:
            # 80-100% congestion for extreme gas prices
            ratio = min(1.0, float(
                (gas_price_gwei - self.gas_thresholds['high']) /
                (self.gas_thresholds['extreme'] - self.gas_thresholds['high'])
            ))
            return 80.0 + (ratio * 20.0)

    def _categorize_gas_cost(self, gas_price_gwei: Decimal) -> str:
        """
        Categorize gas cost level.

        Args:
            gas_price_gwei: Current gas price in gwei

        Returns:
            Category: 'low', 'medium', 'high', or 'extreme'
        """
        if gas_price_gwei <= self.gas_thresholds['low']:
            return 'low'
        elif gas_price_gwei <= self.gas_thresholds['medium']:
            return 'medium'
        elif gas_price_gwei <= self.gas_thresholds['high']:
            return 'high'
        else:
            return 'extreme'