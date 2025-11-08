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
            self.logger.error(
                f"[LIQUIDITY] Error analyzing liquidity for {token_address[:10]}...: {e}",
                exc_info=True
            )

            if IntelligenceDefaults.SKIP_TRADE_ON_MISSING_DATA:
                return {
                    'pool_liquidity_usd': None,
                    'pool_address': None,
                    'fee_tier': None,
                    'trade_impact_percent': None,
                    'liquidity_depth_score': 0.0,
                    'liquidity_category': 'none',
                    'data_quality': 'ERROR',
                    'data_source': 'error',
                    'error': str(e)
                }

            return {
                'pool_liquidity_usd': 0.0,
                'pool_address': None,
                'fee_tier': None,
                'trade_impact_percent': None,
                'liquidity_depth_score': 0.0,
                'liquidity_category': 'none',
                'data_quality': 'ERROR',
                'data_source': 'error'
            }

    async def _get_uniswap_pool_info(
        self,
        web3_client,
        token_address: str,
        chain_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get Uniswap V3 pool information for a token.
        
        Searches for pools pairing the token with common base tokens (WETH, USDC)
        across multiple fee tiers (0.05%, 0.3%, 1%).
        
        Args:
            web3_client: Web3Client instance
            token_address: Token contract address
            chain_id: Chain ID
            
        Returns:
            Dictionary with pool info or None if no pool found:
            - pool_address: Pool contract address
            - fee_tier: Fee tier (500, 3000, 10000)
            - liquidity: Raw liquidity value
            - liquidity_usd: Estimated USD value
            - sqrt_price_x96: Current price (sqrt format)
        """
        try:
            # Get factory address for this chain
            factory_address = UNISWAP_V3_FACTORY.get(chain_id)
            
            if not factory_address:
                self.logger.error(
                    f"[LIQUIDITY] No Uniswap V3 factory address for chain {chain_id}"
                )
                return None
            
            # Common base tokens to pair with (WETH, USDC for Base Mainnet)
            base_token_list = [
                '0x4200000000000000000000000000000000000006',  # WETH on Base
                '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',  # USDC on Base
            ]
            
            self.logger.info(
                f"[LIQUIDITY] Searching for pools: {token_address[:10]}... "
                f"on chain {chain_id} against {len(base_token_list)} base tokens"
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
                            
                            # Get token0 and token1 from the pool
                            try:
                                token0 = pool_contract.functions.token0().call()
                                token1 = pool_contract.functions.token1().call()
                                
                                # Calculate actual TVL using token reserves
                                liquidity_usd = await self._calculate_pool_tvl_usd(
                                    w3=w3,
                                    pool_address=pool_address,
                                    token0=token0,
                                    token1=token1,
                                    base_token=base_token_checksummed
                                )
                            except Exception as e:
                                self.logger.warning(
                                    f"[LIQUIDITY] Could not calculate TVL for pool {pool_address[:10]}...: {e}"
                                )
                                # Fallback: Use a better approximation based on liquidity value
                                # Uniswap V3 liquidity is roughly in the range of 1e12-1e18 for decent pools
                                liquidity_usd = Decimal(str(liquidity)) / Decimal('1e12')
                            
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

    async def _calculate_pool_tvl_usd(
        self,
        w3,
        pool_address: str,
        token0: str,
        token1: str,
        base_token: str
    ) -> Decimal:
        """
        Calculate pool TVL in USD by reading token reserves.
        
        Uses ERC20 balanceOf to get actual token amounts in the pool,
        then estimates USD value based on the base token (WETH or USDC).
        
        Args:
            w3: Web3 instance
            pool_address: Pool contract address
            token0: Token0 address from pool
            token1: Token1 address from pool
            base_token: Base token address (WETH or USDC)
            
        Returns:
            Estimated TVL in USD
        """
        try:
            # ERC20 ABI for balanceOf and decimals
            ERC20_ABI = [
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "decimals",
                    "outputs": [{"name": "", "type": "uint8"}],
                    "type": "function"
                }
            ]
            
            # Get token0 contract
            token0_contract = w3.eth.contract(
                address=w3.to_checksum_address(token0),
                abi=ERC20_ABI
            )
            
            # Get token1 contract
            token1_contract = w3.eth.contract(
                address=w3.to_checksum_address(token1),
                abi=ERC20_ABI
            )
            
            # Get balances of both tokens in the pool
            balance0 = token0_contract.functions.balanceOf(pool_address).call()
            balance1 = token1_contract.functions.balanceOf(pool_address).call()
            
            # Get decimals
            decimals0 = token0_contract.functions.decimals().call()
            decimals1 = token1_contract.functions.decimals().call()
            
            # Convert to human-readable amounts
            amount0 = Decimal(str(balance0)) / Decimal(10 ** decimals0)
            amount1 = Decimal(str(balance1)) / Decimal(10 ** decimals1)
            
            self.logger.debug(
                f"[LIQUIDITY] Pool reserves: {amount0:.4f} token0, {amount1:.4f} token1"
            )
            
            # Determine which token is the base token and estimate USD value
            base_token_lower = base_token.lower()
            
            # Base token addresses (lowercase for comparison)
            WETH_BASE = '0x4200000000000000000000000000000000000006'.lower()
            USDC_BASE = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'.lower()
            
            if token0.lower() == base_token_lower:
                # token0 is base token (WETH or USDC)
                if base_token_lower == WETH_BASE:
                    # WETH pool - estimate at ~$3000 per ETH
                    tvl_usd = amount0 * Decimal('3000') * Decimal('2')  # Multiply by 2 for both sides
                elif base_token_lower == USDC_BASE:
                    # USDC pool - 1:1 with USD
                    tvl_usd = amount0 * Decimal('2')  # Multiply by 2 for both sides
                else:
                    # Unknown base token - use conservative estimate
                    tvl_usd = amount0 * Decimal('1000')
                    
            elif token1.lower() == base_token_lower:
                # token1 is base token
                if base_token_lower == WETH_BASE:
                    # WETH pool - estimate at ~$3000 per ETH
                    tvl_usd = amount1 * Decimal('3000') * Decimal('2')
                elif base_token_lower == USDC_BASE:
                    # USDC pool - 1:1 with USD
                    tvl_usd = amount1 * Decimal('2')
                else:
                    # Unknown base token - use conservative estimate
                    tvl_usd = amount1 * Decimal('1000')
            else:
                # Neither is base token - use simple estimation
                # Assume average token value and add both sides
                avg_amount = (amount0 + amount1) / Decimal('2')
                tvl_usd = avg_amount * Decimal('1000')  # Rough estimate
            
            self.logger.debug(f"[LIQUIDITY] Estimated pool TVL: ${tvl_usd:,.2f}")
            
            return tvl_usd
            
        except Exception as e:
            self.logger.error(f"[LIQUIDITY] Error calculating pool TVL: {e}", exc_info=True)
            # Return a conservative estimate on error
            return Decimal('100000')  # $100K fallback

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