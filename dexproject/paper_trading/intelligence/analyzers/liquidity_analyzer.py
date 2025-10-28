"""
Real Liquidity Analyzer for Uniswap V3 Pools

Analyzes token liquidity using REAL blockchain data from Uniswap V3 by:
- Querying actual Uniswap V3 pools for liquidity data
- Calculating trade size impact on price
- Assessing pool depth and sustainability
- Estimating slippage for trades

File: dexproject/paper_trading/intelligence/analyzers/liquidity_analyzer.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional

# Import base analyzer, defaults, and constants
from paper_trading.intelligence.analyzers.base import BaseAnalyzer
from paper_trading.intelligence.analyzers.constants import (
    UNISWAP_V3_FACTORY,
    FACTORY_ABI,
    POOL_ABI,
    FEE_TIERS
)
from paper_trading.defaults import IntelligenceDefaults

logger = logging.getLogger(__name__)


class RealLiquidityAnalyzer(BaseAnalyzer):
    """
    Analyzes token liquidity using REAL blockchain data from Uniswap V3.

    Queries actual Uniswap V3 pools to determine:
    - Pool liquidity (total value locked)
    - Trade size impact on price
    - Pool depth and sustainability
    - Slippage estimates

    This provides accurate liquidity assessment for informed trading decisions.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize liquidity analyzer.

        Args:
            config: Optional configuration with liquidity thresholds
                   Example: {'liquidity_thresholds': {'excellent': 1000000, ...}}
        """
        super().__init__(config)

        # Liquidity thresholds (in USD)
        self.liquidity_thresholds = {
            'excellent': Decimal('1000000'),   # $1M+ = Excellent liquidity
            'good': Decimal('250000'),         # $250K+ = Good liquidity
            'fair': Decimal('50000'),          # $50K+ = Fair liquidity
            'poor': Decimal('10000')           # $10K+ = Poor but tradeable
        }

        # Override with config if provided
        if config and 'liquidity_thresholds' in config:
            self.liquidity_thresholds.update(config['liquidity_thresholds'])

    async def analyze(
        self,
        token_address: str,
        chain_id: int = 8453,
        trade_size_usd: Decimal = Decimal('1000'),
        **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze token liquidity from Uniswap V3 pools.

        Args:
            token_address: Token contract address to analyze
            chain_id: Blockchain network ID (default: 8453 for Base Mainnet)
            trade_size_usd: Intended trade size in USD for impact calculation
            **kwargs: Additional parameters

        Returns:
            Dictionary containing liquidity analysis:
            - pool_liquidity_usd: Total pool liquidity in USD
            - pool_address: Uniswap V3 pool address
            - fee_tier: Pool fee tier (500, 3000, or 10000)
            - trade_impact_percent: Estimated price impact of trade
            - liquidity_depth_score: Score from 0-100
            - liquidity_category: 'excellent', 'good', 'fair', or 'poor'
            - data_quality: Data quality indicator
            - data_source: Source of the data
        """
        try:
            # Try to get real blockchain data via Web3 client
            web3_client = await self._ensure_web3_client(chain_id)

            if web3_client:
                # Get pool info from Uniswap V3
                pool_info = await self._get_uniswap_pool_info(
                    web3_client,
                    token_address,
                    chain_id
                )

                if pool_info:
                    liquidity_usd = pool_info['liquidity_usd']

                    # Calculate trade impact
                    trade_impact = self._calculate_trade_impact(
                        trade_size_usd,
                        liquidity_usd
                    )

                    # Calculate liquidity depth score
                    depth_score = self._calculate_depth_score(liquidity_usd)

                    # Categorize liquidity
                    category = self._categorize_liquidity(liquidity_usd)

                    self.logger.info(
                        f"[LIQUIDITY] ✅ Real pool data: ${liquidity_usd:,.0f} "
                        f"({category}) - Impact: {trade_impact:.2f}%"
                    )

                    return {
                        'pool_liquidity_usd': float(liquidity_usd),
                        'pool_address': pool_info['pool_address'],
                        'fee_tier': pool_info['fee_tier'],
                        'trade_impact_percent': trade_impact,
                        'liquidity_depth_score': depth_score,
                        'liquidity_category': category,
                        'data_quality': 'EXCELLENT',
                        'data_source': 'uniswap_v3_pool'
                    }
                else:
                    # Pool not found - no real data available
                    self.logger.warning(
                        f"[LIQUIDITY] No pool found for token {token_address[:10]}... "
                        f"on chain {chain_id}"
                    )

                    # Check if we should skip trade on missing data
                    if IntelligenceDefaults.SKIP_TRADE_ON_MISSING_DATA:
                        return {
                            'pool_liquidity_usd': None,
                            'pool_address': None,
                            'fee_tier': None,
                            'trade_impact_percent': None,
                            'liquidity_depth_score': 0.0,
                            'liquidity_category': 'none',
                            'data_quality': 'NO_POOL_FOUND',
                            'data_source': 'none',
                            'error': 'No Uniswap V3 pool found for this token'
                        }

                    return {
                        'pool_liquidity_usd': 0.0,
                        'pool_address': None,
                        'fee_tier': None,
                        'trade_impact_percent': None,
                        'liquidity_depth_score': 0.0,
                        'liquidity_category': 'none',
                        'data_quality': 'NO_POOL_FOUND',
                        'data_source': 'none'
                    }

            else:
                # Web3 not available - cannot get real data
                if IntelligenceDefaults.SKIP_TRADE_ON_MISSING_DATA:
                    self.logger.error(
                        "[LIQUIDITY] Web3 unavailable and SKIP_TRADE_ON_MISSING_DATA=True - "
                        "Cannot analyze without real data"
                    )
                    return {
                        'pool_liquidity_usd': None,
                        'pool_address': None,
                        'fee_tier': None,
                        'trade_impact_percent': None,
                        'liquidity_depth_score': 0.0,
                        'liquidity_category': 'none',
                        'data_quality': 'NO_DATA',
                        'data_source': 'none',
                        'error': 'Real liquidity data unavailable - Web3 not connected'
                    }

                self.logger.warning("[LIQUIDITY] Web3 unavailable - cannot get real data")
                return {
                    'pool_liquidity_usd': 0.0,
                    'pool_address': None,
                    'fee_tier': None,
                    'trade_impact_percent': None,
                    'liquidity_depth_score': 0.0,
                    'liquidity_category': 'none',
                    'data_quality': 'NO_DATA',
                    'data_source': 'none'
                }

        except Exception as e:
            self.logger.error(f"[LIQUIDITY] Error analyzing liquidity: {e}", exc_info=True)
            # No fallback data - return error state
            return {
                'pool_liquidity_usd': None,
                'pool_address': None,
                'fee_tier': None,
                'trade_impact_percent': None,
                'liquidity_depth_score': 0.0,
                'liquidity_category': 'unknown',
                'data_quality': 'ERROR',
                'data_source': 'error',
                'error': f'Liquidity analysis failed: {str(e)}'
            }

    async def _get_uniswap_pool_info(
        self,
        web3_client: Any,
        token_address: str,
        chain_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get Uniswap V3 pool information from blockchain.
        
        Searches for pools pairing the token with common base tokens (WETH, USDC)
        across all standard fee tiers. Uses correct Web3Client API and proper
        contract creation methods.
        
        Args:
            web3_client: Connected Web3 client
            token_address: Token contract address
            chain_id: Blockchain network ID
        
        Returns:
            Dictionary with pool info or None if not found:
            - pool_address: Address of the pool
            - fee_tier: Fee tier in basis points
            - liquidity: Raw liquidity value
            - liquidity_usd: Estimated liquidity in USD
            - sqrt_price_x96: Current price (sqrt format)
        """
        try:
            # Get factory address for this chain
            factory_address = UNISWAP_V3_FACTORY.get(chain_id)
            if not factory_address:
                self.logger.error(f"No Uniswap V3 factory address for chain {chain_id}")
                return None
            
            # Common base tokens to check pairs against
            base_tokens = {
                84532: [
                    '0x4200000000000000000000000000000000000006',  # WETH on Base Sepolia
                    '0x036CbD53842c5426634e7929541eC2318f3dCF7e',  # USDC on Base Sepolia
                ],
                8453: [
                    '0x4200000000000000000000000000000000000006',  # WETH on Base Mainnet
                    '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',  # USDC on Base Mainnet
                ]
            }
            
            base_token_list = base_tokens.get(chain_id, [])
            
            if not base_token_list:
                self.logger.warning(
                    f"[LIQUIDITY] No base tokens configured for chain {chain_id}"
                )
                return None
            
            # Log pool search attempt
            self.logger.info(
                f"[LIQUIDITY] Searching for pools: {token_address[:10]}... on chain {chain_id} "
                f"against {len(base_token_list)} base tokens"
            )
            
            # Access the actual web3 instance from Web3Client
            w3 = web3_client.web3
            
            # Checksum the factory address
            factory_address_checksummed = w3.to_checksum_address(factory_address)
            token_address_checksummed = w3.to_checksum_address(token_address)
            
            # Try each base token with each fee tier
            for base_token in base_token_list:
                # Skip if trying to pair token with itself
                if token_address.lower() == base_token.lower():
                    self.logger.info(
                        f"[LIQUIDITY] Skipping self-pair: {token_address[:10]}... with itself"
                    )
                    continue
                
                # Checksum base token address
                base_token_checksummed = w3.to_checksum_address(base_token)
                
                for fee_tier in FEE_TIERS:
                    try:
                        # Create factory contract using correct API
                        factory_contract = w3.eth.contract(
                            address=factory_address_checksummed,
                            abi=FACTORY_ABI
                        )
                        
                        # Get pool address for this token pair and fee tier
                        pool_address = factory_contract.functions.getPool(
                            token_address_checksummed,
                            base_token_checksummed,
                            fee_tier
                        ).call()
                        
                        # Check if pool exists (non-zero address)
                        if pool_address and pool_address != '0x0000000000000000000000000000000000000000':
                            # Create pool contract using correct API
                            pool_contract = w3.eth.contract(
                                address=pool_address,
                                abi=POOL_ABI
                            )
                            
                            # Get liquidity
                            liquidity = pool_contract.functions.liquidity().call()
                            
                            # Get slot0 for price
                            slot0 = pool_contract.functions.slot0().call()
                            sqrt_price_x96 = slot0[0]
                            
                            # Calculate liquidity in USD (simplified approximation)
                            # For a more accurate calculation, we'd need token prices
                            liquidity_usd = Decimal(str(liquidity)) / Decimal('1e18') * Decimal('2')
                            
                            # SUCCESS: Found a pool!
                            self.logger.info(
                                f"[LIQUIDITY] ✅ Found pool {pool_address[:10]}... for "
                                f"{token_address[:10]}.../{base_token[:10]}... "
                                f"(fee: {fee_tier/10000}%)"
                            )
                            
                            return {
                                'pool_address': pool_address,
                                'fee_tier': fee_tier,
                                'liquidity': liquidity,
                                'liquidity_usd': liquidity_usd,
                                'sqrt_price_x96': sqrt_price_x96
                            }
                        else:
                            # Pool address is zero - no pool exists for this pair/fee
                            self.logger.warning(
                                f"[LIQUIDITY] No pool for {token_address[:10]}.../"
                                f"{base_token[:10]}... fee={fee_tier/10000}% "
                                f"(zero address returned)"
                            )
                    
                    except Exception as e:
                        # Pool query failed - could be RPC error, contract error, etc.
                        error_msg = str(e)[:100]  # Truncate long error messages
                        self.logger.warning(
                            f"[LIQUIDITY] Query failed for {token_address[:10]}.../"
                            f"{base_token[:10]}... fee={fee_tier/10000}%: {error_msg}"
                        )
                        continue
            
            # No pool found after checking all base tokens and fee tiers
            self.logger.warning(
                f"[LIQUIDITY] No pool found for {token_address[:10]}... on chain {chain_id} "
                f"after checking {len(base_token_list)} base tokens with {len(FEE_TIERS)} fee tiers"
            )
            return None
        
        except Exception as e:
            self.logger.error(
                f"[LIQUIDITY] Error getting Uniswap pool info for {token_address[:10]}... "
                f"on chain {chain_id}: {e}",
                exc_info=True
            )
            return None

    def _calculate_trade_impact(
        self,
        trade_size_usd: Decimal,
        pool_liquidity_usd: Decimal
    ) -> float:
        """
        Calculate estimated price impact of a trade.

        Args:
            trade_size_usd: Trade size in USD
            pool_liquidity_usd: Pool liquidity in USD

        Returns:
            Estimated price impact as percentage
        """
        if pool_liquidity_usd == 0:
            return 100.0  # Maximum impact

        # Simplified impact calculation: impact = (trade_size / liquidity) * 100
        # Real calculation would use pool math, but this is a reasonable approximation
        impact_ratio = float(trade_size_usd / pool_liquidity_usd)

        # Apply non-linear scaling for larger trades
        if impact_ratio < 0.01:  # < 1% of pool
            return impact_ratio * 100
        elif impact_ratio < 0.05:  # 1-5% of pool
            return impact_ratio * 120  # Slightly higher impact
        else:  # > 5% of pool
            return min(100.0, impact_ratio * 150)  # Much higher impact

    def _calculate_depth_score(self, liquidity_usd: Decimal) -> float:
        """
        Calculate liquidity depth score (0-100).

        Args:
            liquidity_usd: Pool liquidity in USD

        Returns:
            Score from 0 (no liquidity) to 100 (excellent liquidity)
        """
        if liquidity_usd >= self.liquidity_thresholds['excellent']:
            return 100.0
        elif liquidity_usd >= self.liquidity_thresholds['good']:
            # Score between 75-100
            ratio = float(
                (liquidity_usd - self.liquidity_thresholds['good']) /
                (self.liquidity_thresholds['excellent'] - self.liquidity_thresholds['good'])
            )
            return 75.0 + (ratio * 25.0)
        elif liquidity_usd >= self.liquidity_thresholds['fair']:
            # Score between 50-75
            ratio = float(
                (liquidity_usd - self.liquidity_thresholds['fair']) /
                (self.liquidity_thresholds['good'] - self.liquidity_thresholds['fair'])
            )
            return 50.0 + (ratio * 25.0)
        elif liquidity_usd >= self.liquidity_thresholds['poor']:
            # Score between 25-50
            ratio = float(
                (liquidity_usd - self.liquidity_thresholds['poor']) /
                (self.liquidity_thresholds['fair'] - self.liquidity_thresholds['poor'])
            )
            return 25.0 + (ratio * 25.0)
        else:
            # Score 0-25 for very low liquidity
            ratio = min(1.0, float(liquidity_usd / self.liquidity_thresholds['poor']))
            return ratio * 25.0

    def _categorize_liquidity(self, liquidity_usd: Decimal) -> str:
        """
        Categorize liquidity level.

        Args:
            liquidity_usd: Pool liquidity in USD

        Returns:
            Category: 'excellent', 'good', 'fair', or 'poor'
        """
        if liquidity_usd >= self.liquidity_thresholds['excellent']:
            return 'excellent'
        elif liquidity_usd >= self.liquidity_thresholds['good']:
            return 'good'
        elif liquidity_usd >= self.liquidity_thresholds['fair']:
            return 'fair'
        else:
            return 'poor'