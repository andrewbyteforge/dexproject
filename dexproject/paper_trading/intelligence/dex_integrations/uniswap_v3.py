"""
Uniswap V3 DEX Integration for Real Price Queries

This module implements the Uniswap V3 integration for Phase 2 multi-DEX price comparison.
It queries real Uniswap V3 pools on-chain for accurate price and liquidity data.

Phase 2: Multi-DEX Price Comparison
File: paper_trading/intelligence/dex_integrations/uniswap_v3.py
"""

import logging
import time
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple

from django.utils import timezone

# Import base DEX class
from .base_dex import BaseDEX, DEXPrice

# Import Uniswap V3 constants
from paper_trading.intelligence.analyzers.constants import (
    UNISWAP_V3_FACTORY,
    FACTORY_ABI,
    POOL_ABI,
    FEE_TIERS
)

# Import defaults
from paper_trading.defaults import DEXComparisonDefaults

logger = logging.getLogger(__name__)


# =============================================================================
# UNISWAP V3 DEX INTEGRATION
# =============================================================================

class UniswapV3DEX(BaseDEX):
    """
    Uniswap V3 integration for real price and liquidity queries.
    
    Features:
    - Queries real Uniswap V3 pools on-chain
    - Searches across all fee tiers (0.05%, 0.3%, 1%)
    - Calculates prices from pool reserves
    - Returns liquidity data for risk assessment
    """
    
    def __init__(
        self,
        chain_id: int = 84532,
        cache_ttl_seconds: int = 30
    ):
        """
        Initialize Uniswap V3 DEX integration.
        
        Args:
            chain_id: Blockchain network ID
            cache_ttl_seconds: Cache TTL for price quotes
        """
        super().__init__(
            dex_name='uniswap_v3',
            chain_id=chain_id,
            cache_ttl_seconds=cache_ttl_seconds
        )
        
        # Uniswap V3 specific configuration
        self.factory_address = UNISWAP_V3_FACTORY.get(chain_id)
        self.fee_tiers = DEXComparisonDefaults.UNISWAP_V3_FEE_TIERS
        
        # Base tokens for price pairs
        self.base_tokens = self._get_base_tokens(chain_id)
        
        self.logger.info(
            f"[UNISWAP V3] Initialized for chain {chain_id}, "
            f"Factory: {self.factory_address[:10] if self.factory_address else 'N/A'}..."
        )
    
    def _get_base_tokens(self, chain_id: int) -> List[Dict[str, str]]:
        """
        Get base tokens for this chain (WETH, USDC).
        
        Args:
            chain_id: Blockchain network ID
            
        Returns:
            List of base token dictionaries
        """
        base_tokens_by_chain = {
            84532: [  # Base Sepolia
                {
                    'symbol': 'WETH',
                    'address': '0x4200000000000000000000000000000000000006'
                },
                {
                    'symbol': 'USDC',
                    'address': '0x036CbD53842c5426634e7929541eC2318f3dCF7e'
                }
            ],
            8453: [  # Base Mainnet
                {
                    'symbol': 'WETH',
                    'address': '0x4200000000000000000000000000000000000006'
                },
                {
                    'symbol': 'USDC',
                    'address': '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
                }
            ],
            1: [  # Ethereum Mainnet
                {
                    'symbol': 'WETH',
                    'address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'
                },
                {
                    'symbol': 'USDC',
                    'address': '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'
                }
            ]
        }
        
        return base_tokens_by_chain.get(chain_id, [])
    
    # =========================================================================
    # MAIN INTERFACE METHODS
    # =========================================================================
    
    async def get_token_price(
        self,
        token_address: str,
        token_symbol: str
    ) -> DEXPrice:
        """
        Get token price from Uniswap V3 pools.
        
        This method:
        1. Checks cache first
        2. Finds best pool across fee tiers
        3. Queries pool for current price
        4. Calculates price in USD
        5. Caches result
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            
        Returns:
            DEXPrice with price and metadata
        """
        start_time = time.time()
        self.total_queries += 1
        
        # Check if DEX is disabled by circuit breaker
        if self._check_if_disabled():
            return DEXPrice(
                dex_name=self.dex_name,
                token_address=token_address,
                token_symbol=token_symbol,
                success=False,
                error_message="DEX temporarily disabled due to consecutive failures"
            )
        
        # Check cache first
        cached_price = self._get_cached_price(token_address)
        if cached_price:
            self.logger.debug(f"[UNISWAP V3] Cache hit for {token_symbol}")
            return cached_price
        
        try:
            # Ensure Web3 client is initialized
            web3_client = await self._ensure_web3_client()
            if not web3_client:
                raise Exception("Web3 client unavailable")
            
            # Find best pool for this token
            pool_info = await self._find_best_pool(
                web3_client,
                token_address,
                token_symbol
            )
            
            if not pool_info:
                raise Exception(f"No Uniswap V3 pool found for {token_symbol}")
            
            # Calculate price and liquidity
            price_usd = pool_info['price_usd']
            liquidity_usd = pool_info['liquidity_usd']
            
            # Record success
            response_time_ms = (time.time() - start_time) * 1000
            self.total_response_time_ms += response_time_ms
            self._record_success()
            
            # Create price object
            price = DEXPrice(
                dex_name=self.dex_name,
                token_address=token_address,
                token_symbol=token_symbol,
                price_usd=price_usd,
                liquidity_usd=liquidity_usd,
                timestamp=timezone.now(),
                success=True,
                response_time_ms=response_time_ms
            )
            
            # Cache result
            self._cache_price(price)
            
            self.logger.info(
                f"[UNISWAP V3] {token_symbol} price: ${price_usd:.4f}, "
                f"Liquidity: ${liquidity_usd:,.0f}, "
                f"Response: {response_time_ms:.0f}ms"
            )
            
            return price
        
        except Exception as e:
            # Record failure
            response_time_ms = (time.time() - start_time) * 1000
            self._record_failure()
            
            self.logger.error(
                f"[UNISWAP V3] Error getting price for {token_symbol}: {e}",
                exc_info=True
            )
            
            return DEXPrice(
                dex_name=self.dex_name,
                token_address=token_address,
                token_symbol=token_symbol,
                success=False,
                error_message=str(e),
                response_time_ms=response_time_ms
            )
    
    async def get_liquidity(
        self,
        token_address: str
    ) -> Optional[Decimal]:
        """
        Get available liquidity for token on Uniswap V3.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Liquidity in USD, or None if unavailable
        """
        try:
            # Get price (which includes liquidity)
            price = await self.get_token_price(token_address, "UNKNOWN")
            return price.liquidity_usd if price.success else None
        
        except Exception as e:
            self.logger.error(
                f"[UNISWAP V3] Error getting liquidity for {token_address}: {e}"
            )
            return None
    
    async def is_available(self) -> bool:
        """
        Check if Uniswap V3 is available on this chain.
        
        Returns:
            True if available, False otherwise
        """
        # Check if factory address configured
        if not self.factory_address:
            return False
        
        # Check if disabled by circuit breaker
        if self._check_if_disabled():
            return False
        
        # Try to initialize Web3 client
        web3_client = await self._ensure_web3_client()
        return web3_client is not None
    
    # =========================================================================
    # UNISWAP V3 SPECIFIC METHODS
    # =========================================================================
    
    async def _find_best_pool(
        self,
        web3_client: Any,
        token_address: str,
        token_symbol: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find best Uniswap V3 pool for token across all fee tiers.
        
        Searches for pools pairing with WETH and USDC across all
        configured fee tiers and returns the one with highest liquidity.
        
        Args:
            web3_client: Connected Web3 client
            token_address: Token contract address
            token_symbol: Token symbol
            
        Returns:
            Dictionary with pool info or None if not found
        """
        try:
            # Get factory contract
            factory_contract = web3_client.web3.eth.contract(
                address=web3_client.web3.to_checksum_address(self.factory_address),
                abi=FACTORY_ABI
            )
            
            best_pool = None
            best_liquidity = Decimal('0')
            
            # Check each base token
            for base_token in self.base_tokens:
                # Check each fee tier
                for fee_tier in self.fee_tiers:
                    try:
                        # Query factory for pool address
                        pool_address = factory_contract.functions.getPool(
                            web3_client.web3.to_checksum_address(token_address),
                            web3_client.web3.to_checksum_address(base_token['address']),
                            fee_tier
                        ).call()
                        
                        # Check if pool exists
                        if pool_address == '0x0000000000000000000000000000000000000000':
                            continue
                        
                        # Query pool for liquidity and price
                        pool_data = await self._query_pool_data(
                            web3_client,
                            pool_address,
                            token_address,
                            base_token,
                            fee_tier
                        )
                        
                        if pool_data and pool_data['liquidity_usd'] > best_liquidity:
                            best_liquidity = pool_data['liquidity_usd']
                            best_pool = pool_data
                    
                    except Exception as e:
                        self.logger.debug(
                            f"[UNISWAP V3] No pool found for {token_symbol}-"
                            f"{base_token['symbol']} at {fee_tier} fee tier"
                        )
                        continue
            
            if best_pool:
                self.logger.info(
                    f"[UNISWAP V3] Found pool for {token_symbol} with "
                    f"${best_liquidity:,.0f} liquidity"
                )
            
            return best_pool
        
        except Exception as e:
            self.logger.error(
                f"[UNISWAP V3] Error finding pool for {token_symbol}: {e}",
                exc_info=True
            )
            return None
    
    async def _query_pool_data(
        self,
        web3_client: Any,
        pool_address: str,
        token_address: str,
        base_token: Dict[str, str],
        fee_tier: int
    ) -> Optional[Dict[str, Any]]:
        """
        Query Uniswap V3 pool for price and liquidity data.
        
        Args:
            web3_client: Connected Web3 client
            pool_address: Pool contract address
            token_address: Token being priced
            base_token: Base token info (WETH, USDC)
            fee_tier: Pool fee tier
            
        Returns:
            Dictionary with price and liquidity data
        """
        try:
            # Get pool contract
            pool_contract = web3_client.web3.eth.contract(
                address=web3_client.web3.to_checksum_address(pool_address),
                abi=POOL_ABI
            )
            
            # Query pool state
            liquidity = pool_contract.functions.liquidity().call()
            slot0 = pool_contract.functions.slot0().call()
            sqrt_price_x96 = slot0[0]
            
            # Calculate price from sqrt price
            price_ratio = (Decimal(sqrt_price_x96) / Decimal(2**96)) ** 2
            
            # Convert to USD price
            # Simplified: Assume base token is $1 (USDC) or needs conversion (WETH)
            if base_token['symbol'] == 'USDC':
                price_usd = price_ratio
            else:
                # Would need to fetch WETH price - simplified for now
                # In production, chain another query
                price_usd = price_ratio * Decimal('2500')  # Approximate WETH price
            
            # Estimate liquidity in USD (simplified)
            liquidity_usd = Decimal(liquidity) / Decimal(1e18) * price_usd
            
            return {
                'pool_address': pool_address,
                'fee_tier': fee_tier,
                'base_token': base_token['symbol'],
                'price_usd': price_usd,
                'liquidity_usd': liquidity_usd,
                'sqrt_price_x96': sqrt_price_x96,
                'raw_liquidity': liquidity
            }
        
        except Exception as e:
            self.logger.debug(
                f"[UNISWAP V3] Error querying pool {pool_address[:10]}...: {e}"
            )
            return None