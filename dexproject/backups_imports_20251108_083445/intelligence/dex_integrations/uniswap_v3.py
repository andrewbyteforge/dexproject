"""
Uniswap V3 DEX Integration

Complete Uniswap V3 integration for price and liquidity queries.
Queries Uniswap V3 pools on-chain for real-time price data.

File: dexproject/paper_trading/intelligence/dex_integrations/uniswap_v3.py
"""

import logging
import time as time_module
from decimal import Decimal
from typing import Optional, Dict, Any, List

# Import base classes
from paper_trading.intelligence.dex_integrations.base import BaseDEX, DEXPrice

# Import constants
from paper_trading.intelligence.dex_integrations.constants import (
    UNISWAP_V3_FACTORY,
    UNISWAP_V3_FEE_TIERS,
    FACTORY_ABI,
    POOL_ABI,
    ERC20_ABI,
    get_base_tokens
)

logger = logging.getLogger(__name__)


class UniswapV3DEX(BaseDEX):
    """
    Uniswap V3 price fetching implementation.
    
    Queries Uniswap V3 pools on-chain to get:
    - Current token prices
    - Pool liquidity
    - Best pool across fee tiers
    
    Uses multiple fee tiers (0.05%, 0.3%, 1%) and base tokens (WETH, USDC, USDT, DAI)
    to find the best liquidity pool for price discovery.
    """
    
    def __init__(
        self,
        chain_id: int = 8453,
        cache_ttl_seconds: int = 60
    ):
        """
        Initialize Uniswap V3 integration.
        
        Args:
            chain_id: Blockchain network ID (default: 8453 = Base Mainnet)
            cache_ttl_seconds: Cache TTL for price data
        """
        super().__init__(
            dex_name="uniswap_v3",
            chain_id=chain_id,
            cache_ttl_seconds=cache_ttl_seconds
        )
        
        # Get Uniswap V3 factory address for this chain
        self.factory_address = UNISWAP_V3_FACTORY.get(chain_id)
        if not self.factory_address:
            self.logger.warning(
                f"[UNISWAP V3] No factory address for chain {chain_id}"
            )
        
        # Get base tokens for this chain (WETH, USDC, USDT, DAI)
        self.base_tokens = get_base_tokens(chain_id)
        if not self.base_tokens:
            self.logger.warning(
                f"[UNISWAP V3] No base tokens configured for chain {chain_id}"
            )
        
        self.logger.info(
            f"[UNISWAP V3] Initialized with {len(self.base_tokens)} base tokens, "
            f"{len(UNISWAP_V3_FEE_TIERS)} fee tiers"
        )
    
    async def get_token_price(
        self,
        token_address: str,
        token_symbol: str
    ) -> DEXPrice:
        """
        Get token price from Uniswap V3.
        
        Process:
        1. Check cache
        2. Find best pool (across fee tiers and base tokens)
        3. Query pool for price and liquidity
        4. Calculate price in USD
        5. Cache result
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            
        Returns:
            DEXPrice object with price and liquidity data
        """
        start_time = time_module.time()
        self.total_queries += 1
        
        try:
            # Check cache first
            cached = self._get_cached_price(token_address)
            if cached:
                return cached
            
            # Validate Web3 client
            if not self.web3_client:
                return DEXPrice(
                    dex_name=self.dex_name,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    success=False,
                    error_message="Web3 client not initialized",
                    query_time_ms=(time_module.time() - start_time) * 1000
                )
            
            # Find best pool
            best_pool = await self._find_best_pool(token_address)
            
            if not best_pool:
                return DEXPrice(
                    dex_name=self.dex_name,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    success=False,
                    error_message="No Uniswap V3 pool found",
                    query_time_ms=(time_module.time() - start_time) * 1000
                )
            
            # Query pool for price and liquidity
            price_usd, liquidity_usd = await self._query_pool_data(
                best_pool['address'],
                token_address,
                best_pool['base_token']
            )
            
            # Calculate query time
            query_time_ms = (time_module.time() - start_time) * 1000
            
            # Create result
            price_obj = DEXPrice(
                dex_name=self.dex_name,
                token_address=token_address,
                token_symbol=token_symbol,
                pool_address=best_pool['address'],
                query_time_ms=query_time_ms,
                data_source="on_chain"
            )
            
            if price_usd and liquidity_usd:
                price_obj.price_usd = price_usd
                price_obj.liquidity_usd = liquidity_usd
                price_obj.success = True
                
                # Update performance counters
                self.successful_queries += 1
                self.total_query_time_ms += query_time_ms
                self._cache_price(token_address, price_obj)
                
                self.logger.debug(
                    f"[UNISWAP V3] {token_symbol}: ${price_usd:.4f}, "
                    f"Liquidity: ${liquidity_usd:,.0f} ({query_time_ms:.0f}ms)"
                )
            else:
                price_obj.error_message = "Failed to fetch price from pool"
            
            return price_obj
        
        except Exception as e:
            self.logger.error(
                f"[UNISWAP V3] Error fetching price for {token_symbol}: {e}",
                exc_info=True
            )
            
            return DEXPrice(
                dex_name=self.dex_name,
                token_address=token_address,
                token_symbol=token_symbol,
                success=False,
                error_message=str(e),
                query_time_ms=(time_module.time() - start_time) * 1000
            )
    
    async def _find_best_pool(self, token_address: str) -> Optional[Dict[str, Any]]:
        """
        Find best Uniswap V3 pool for token.
        
        Checks all fee tiers and base tokens to find pool with highest liquidity.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Dict with pool address and metadata, or None if not found
        """
        best_pool = None
        best_liquidity = Decimal('0')
        
        # Try each base token (WETH, USDC, USDT, DAI)
        for base_token in self.base_tokens:
            # Try each fee tier (0.05%, 0.3%, 1%)
            for fee_tier in UNISWAP_V3_FEE_TIERS:
                try:
                    pool_address = await self._get_pool_address(
                        token_address,
                        base_token,
                        fee_tier
                    )
                    
                    if pool_address and pool_address != '0x' + '0' * 40:
                        # Query liquidity
                        liquidity = await self._get_pool_liquidity(pool_address)
                        
                        if liquidity > best_liquidity:
                            best_liquidity = liquidity
                            best_pool = {
                                'address': pool_address,
                                'base_token': base_token,
                                'fee_tier': fee_tier,
                                'liquidity': liquidity
                            }
                
                except Exception as e:
                    self.logger.debug(
                        f"[UNISWAP V3] Error checking pool "
                        f"({token_address[:10]}.../{base_token[:10]}.../{fee_tier}): {e}"
                    )
                    continue
        
        return best_pool
    
    async def _get_pool_address(
        self,
        token_a: str,
        token_b: str,
        fee_tier: int
    ) -> Optional[str]:
        """Get pool address from Uniswap V3 factory."""
        if not self.web3_client:
            return None
        
        try:
            # Create factory contract
            factory_contract = self.web3_client.web3.eth.contract(
                address=self.factory_address,
                abi=FACTORY_ABI
            )
            
            # Query pool address
            pool_address = factory_contract.functions.getPool(
                token_a,
                token_b,
                fee_tier
            ).call()
            
            return pool_address
        
        except Exception as e:
            self.logger.debug(f"[UNISWAP V3] Error getting pool address: {e}")
            return None
    
    async def _get_pool_liquidity(self, pool_address: str) -> Decimal:
        """Get liquidity from Uniswap V3 pool."""
        if not self.web3_client:
            return Decimal('0')
        
        try:
            # Create pool contract
            pool_contract = self.web3_client.web3.eth.contract(
                address=pool_address,
                abi=POOL_ABI
            )
            
            # Query liquidity
            liquidity = pool_contract.functions.liquidity().call()
            
            return Decimal(str(liquidity))
        
        except Exception as e:
            self.logger.debug(f"[UNISWAP V3] Error getting pool liquidity: {e}")
            return Decimal('0')
    
    async def _query_pool_data(
        self,
        pool_address: str,
        token_address: str,
        base_token_address: str
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """
        Query pool for price and liquidity data.
        
        This is the FIXED implementation that properly:
        1. Gets token reserves using balanceOf
        2. Gets token decimals
        3. Calculates price ratio
        4. Converts to USD using base token price
        
        Args:
            pool_address: Pool contract address
            token_address: Token contract address
            base_token_address: Base token address (WETH, USDC, etc.)
            
        Returns:
            Tuple of (price_usd, liquidity_usd)
        """
        if not self.web3_client:
            return None, None
        
        try:
            # Create pool contract
            pool_contract = self.web3_client.web3.eth.contract(
                address=pool_address,
                abi=POOL_ABI
            )
            
            # Get token0 and token1
            token0 = pool_contract.functions.token0().call()
            token1 = pool_contract.functions.token1().call()
            
            # Determine which is our target token
            is_token0 = token0.lower() == token_address.lower()
            
            # Create token contracts
            token_contract = self.web3_client.web3.eth.contract(
                address=token_address,
                abi=ERC20_ABI
            )
            base_contract = self.web3_client.web3.eth.contract(
                address=base_token_address,
                abi=ERC20_ABI
            )
            
            # Get token reserves (balances in pool)
            token_balance = token_contract.functions.balanceOf(pool_address).call()
            base_balance = base_contract.functions.balanceOf(pool_address).call()
            
            # Get decimals
            token_decimals = token_contract.functions.decimals().call()
            base_decimals = base_contract.functions.decimals().call()
            
            # Convert to decimal amounts
            token_amount = Decimal(token_balance) / Decimal(10 ** token_decimals)
            base_amount = Decimal(base_balance) / Decimal(10 ** base_decimals)
            
            if token_amount == 0:
                return None, None
            
            # Calculate price (base tokens per target token)
            if is_token0:
                # Price = base_amount / token_amount
                price_in_base = base_amount / token_amount
            else:
                # Price = base_amount / token_amount
                price_in_base = base_amount / token_amount
            
            # Convert to USD
            # For WETH: assume $3000
            # For USDC/USDT/DAI: $1.00
            base_token_lower = base_token_address.lower()
            
            # Simple USD conversion (can be enhanced with oracle prices)
            if 'usdc' in str(base_contract.functions.symbol().call()).lower():
                price_usd = price_in_base
            elif 'usdt' in str(base_contract.functions.symbol().call()).lower():
                price_usd = price_in_base
            elif 'dai' in str(base_contract.functions.symbol().call()).lower():
                price_usd = price_in_base
            else:
                # Assume WETH at $3000
                price_usd = price_in_base * Decimal('3000')
            
            # Calculate liquidity in USD
            # Liquidity = 2 * base_token_value (for symmetric pools)
            if 'usdc' in str(base_contract.functions.symbol().call()).lower() or \
               'usdt' in str(base_contract.functions.symbol().call()).lower() or \
               'dai' in str(base_contract.functions.symbol().call()).lower():
                liquidity_usd = base_amount * Decimal('2')
            else:
                # WETH pool
                liquidity_usd = base_amount * Decimal('3000') * Decimal('2')
            
            return price_usd, liquidity_usd
        
        except Exception as e:
            self.logger.error(
                f"[UNISWAP V3] Error querying pool data: {e}",
                exc_info=True
            )
            return None, None