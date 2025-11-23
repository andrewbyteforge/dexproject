"""
BaseSwap DEX Integration - BASE CHAIN SPECIFIC

BaseSwap is a Uniswap V2 fork on Base chain.
Simple constant product AMM (xy=k) optimized for Base.

This implementation:
- Queries BaseSwap factory for pairs
- Gets reserves using getReserves()
- Calculates prices with constant product formula
- Supports multiple base tokens (WETH, USDC, etc.)
- Returns standardized DEXPrice objects

BaseSwap is important for Base trading as it provides:
- Additional liquidity sources
- Alternative to Aerodrome for certain pairs
- Simple, proven AMM design
- Base-native token support

File: dexproject/paper_trading/intelligence/dex_integrations/baseswap.py
"""

import logging
import time as time_module
from decimal import Decimal
from typing import Optional, Dict, Any, List

# Import base classes
from paper_trading.intelligence.dex_integrations.base import BaseDEX, DEXPrice

# Import constants
from paper_trading.intelligence.dex_integrations.constants import (
    UNISWAP_V2_FACTORY_ABI,
    UNISWAP_V2_PAIR_ABI,
    ERC20_ABI,
    get_base_tokens
)

logger = logging.getLogger(__name__)


# BaseSwap addresses on Base Mainnet
BASESWAP_ADDRESSES = {
    8453: {  # Base Mainnet
        'factory': '0xFDa619b6d20975be80A10332cD39b9a4b0FAa8BB',
        'router': '0x327Df1E6de05895d2ab08513aaDD9313Fe505d86'
    }
}


class BaseSwapDEX(BaseDEX):
    """
    BaseSwap DEX price fetching implementation.
    
    BaseSwap is a Uniswap V2 fork on Base chain.
    Uses the proven constant product formula (xy=k).
    
    Best for:
    - Base chain trading (additional liquidity)
    - Simple token swaps
    - Alternative pricing to Aerodrome
    - Arbitrage opportunities vs other Base DEXs
    
    Process:
    1. Try each base token (WETH, USDC, USDT, DAI)
    2. Query factory.getPair()
    3. Get reserves from pair.getReserves()
    4. Calculate price from reserve ratio
    5. Convert to USD
    6. Select highest liquidity pair
    """
    
    def __init__(
        self,
        chain_id: int = 8453,
        cache_ttl_seconds: int = 60
    ):
        """
        Initialize BaseSwap integration.
        
        Args:
            chain_id: Blockchain network ID (default: 8453 = Base Mainnet)
            cache_ttl_seconds: Cache TTL for price data
        """
        super().__init__(
            dex_name="baseswap",
            chain_id=chain_id,
            cache_ttl_seconds=cache_ttl_seconds
        )
        
        # Get BaseSwap addresses for this chain
        addresses = BASESWAP_ADDRESSES.get(chain_id)
        if not addresses:
            self.logger.warning(
                f"[BASESWAP] No addresses configured for chain {chain_id}"
            )
            self.factory_address = None
            self.router_address = None
        else:
            self.factory_address = addresses['factory']
            self.router_address = addresses['router']
        
        # Get base tokens for this chain
        self.base_tokens = get_base_tokens(chain_id)
        if not self.base_tokens:
            self.logger.warning(
                f"[BASESWAP] No base tokens configured for chain {chain_id}"
            )
        
        self.logger.info(
            f"[BASESWAP] Initialized for Base chain with {len(self.base_tokens)} base tokens"
        )
    
    async def get_token_price(
        self,
        token_address: str,
        token_symbol: str
    ) -> DEXPrice:
        """
        Get token price from BaseSwap.
        
        Process:
        1. Check cache
        2. Find best pair (across base tokens)
        3. Query pair for reserves
        4. Calculate price from reserves
        5. Convert to USD
        6. Cache result
        
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
            
            # Validate factory address
            if not self.factory_address:
                return DEXPrice(
                    dex_name=self.dex_name,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    success=False,
                    error_message=f"No BaseSwap factory for chain {self.chain_id}",
                    query_time_ms=(time_module.time() - start_time) * 1000
                )
            
            # Find best pair
            best_pair = await self._find_best_pair(token_address)
            
            if not best_pair:
                return DEXPrice(
                    dex_name=self.dex_name,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    success=False,
                    error_message="No BaseSwap pair found",
                    query_time_ms=(time_module.time() - start_time) * 1000
                )
            
            # Query pair for price and liquidity
            price_usd, liquidity_usd = await self._query_pair_data(
                best_pair['address'],
                token_address,
                best_pair['base_token']
            )
            
            # Calculate query time
            query_time_ms = (time_module.time() - start_time) * 1000
            
            # Create result
            price_obj = DEXPrice(
                dex_name=self.dex_name,
                token_address=token_address,
                token_symbol=token_symbol,
                pool_address=best_pair['address'],
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
                    f"[BASESWAP] {token_symbol}: ${price_usd:.4f}, "
                    f"Liquidity: ${liquidity_usd:,.0f} ({query_time_ms:.0f}ms)"
                )
            else:
                price_obj.error_message = "Failed to fetch price from pair"
            
            return price_obj
        
        except Exception as e:
            self.logger.error(
                f"[BASESWAP] Error fetching price for {token_symbol}: {e}",
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
    
    async def _find_best_pair(self, token_address: str) -> Optional[Dict[str, Any]]:
        """
        Find best BaseSwap pair for token.
        
        Tries all base tokens to find pair with highest liquidity.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Dict with pair address and metadata, or None if not found
        """
        best_pair = None
        best_liquidity = Decimal('0')
        
        # Create factory contract
        factory_contract = self.web3_client.web3.eth.contract(
            address=self.factory_address,
            abi=UNISWAP_V2_FACTORY_ABI
        )
        
        # Try each base token (WETH, USDC, USDT, DAI)
        for base_token in self.base_tokens:
            try:
                # Query pair address from factory
                pair_address = factory_contract.functions.getPair(
                    token_address,
                    base_token
                ).call()
                
                # Check if pair exists (non-zero address)
                if pair_address and pair_address != '0x' + '0' * 40:
                    # Calculate liquidity for this pair
                    liquidity = await self._get_pair_liquidity(
                        pair_address,
                        base_token
                    )
                    
                    if liquidity > best_liquidity:
                        best_liquidity = liquidity
                        best_pair = {
                            'address': pair_address,
                            'base_token': base_token,
                            'liquidity': liquidity
                        }
            
            except Exception as e:
                self.logger.debug(
                    f"[BASESWAP] Error checking pair "
                    f"({token_address[:10]}.../{base_token[:10]}...): {e}"
                )
                continue
        
        return best_pair
    
    async def _get_pair_liquidity(
        self,
        pair_address: str,
        base_token_address: str
    ) -> Decimal:
        """
        Get liquidity from BaseSwap pair.
        
        Args:
            pair_address: Pair contract address
            base_token_address: Base token address
            
        Returns:
            Liquidity in USD
        """
        try:
            # Create base token contract
            base_contract = self.web3_client.web3.eth.contract(
                address=base_token_address,
                abi=ERC20_ABI
            )
            
            # Get base token balance in pair
            base_balance = base_contract.functions.balanceOf(pair_address).call()
            base_decimals = base_contract.functions.decimals().call()
            base_symbol = base_contract.functions.symbol().call()
            
            # Convert to decimal amount
            base_amount = Decimal(base_balance) / Decimal(10 ** base_decimals)
            
            # Convert to USD based on token type
            base_symbol_lower = base_symbol.lower()
            if 'usdc' in base_symbol_lower or 'usdt' in base_symbol_lower or 'dai' in base_symbol_lower:
                # Stablecoins = $1.00
                liquidity_usd = base_amount * Decimal('2')  # Both sides of pair
            else:
                # Assume WETH at $3000
                liquidity_usd = base_amount * Decimal('3000') * Decimal('2')
            
            return liquidity_usd
        
        except Exception as e:
            self.logger.debug(f"[BASESWAP] Error getting pair liquidity: {e}")
            return Decimal('0')
    
    async def _query_pair_data(
        self,
        pair_address: str,
        token_address: str,
        base_token_address: str
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """
        Query pair for price and liquidity data.
        
        This method:
        1. Gets token0 and token1 from pair
        2. Gets reserves using getReserves()
        3. Determines which token is which
        4. Calculates price ratio
        5. Converts to USD using base token price
        
        Args:
            pair_address: Pair contract address
            token_address: Target token address
            base_token_address: Base token address (WETH, USDC, etc.)
            
        Returns:
            Tuple of (price_usd, liquidity_usd)
        """
        if not self.web3_client:
            return None, None
        
        try:
            # Create pair contract
            pair_contract = self.web3_client.web3.eth.contract(
                address=pair_address,
                abi=UNISWAP_V2_PAIR_ABI
            )
            
            # Get token0 and token1
            token0 = pair_contract.functions.token0().call()
            token1 = pair_contract.functions.token1().call()
            
            # Get reserves
            reserves = pair_contract.functions.getReserves().call()
            reserve0 = Decimal(reserves[0])
            reserve1 = Decimal(reserves[1])
            
            # Determine which is our target token and which is base token
            if token0.lower() == token_address.lower():
                token_contract = self.web3_client.web3.eth.contract(
                    address=token0,
                    abi=ERC20_ABI
                )
                base_contract = self.web3_client.web3.eth.contract(
                    address=token1,
                    abi=ERC20_ABI
                )
                token_reserve = reserve0
                base_reserve = reserve1
            else:
                token_contract = self.web3_client.web3.eth.contract(
                    address=token1,
                    abi=ERC20_ABI
                )
                base_contract = self.web3_client.web3.eth.contract(
                    address=token0,
                    abi=ERC20_ABI
                )
                token_reserve = reserve1
                base_reserve = reserve0
            
            # Get decimals
            token_decimals = token_contract.functions.decimals().call()
            base_decimals = base_contract.functions.decimals().call()
            base_symbol = base_contract.functions.symbol().call()
            
            # Convert reserves to decimal amounts
            token_amount = token_reserve / Decimal(10 ** token_decimals)
            base_amount = base_reserve / Decimal(10 ** base_decimals)
            
            # Check for zero reserves
            if token_amount == 0 or base_amount == 0:
                return None, None
            
            # Calculate price (base tokens per target token)
            price_in_base = base_amount / token_amount
            
            # Convert to USD
            base_symbol_lower = base_symbol.lower()
            if 'usdc' in base_symbol_lower or 'usdt' in base_symbol_lower or 'dai' in base_symbol_lower:
                # Stablecoin pairs - price is already in USD
                price_usd = price_in_base
            else:
                # WETH pairs - assume $3000 per ETH
                price_usd = price_in_base * Decimal('3000')
            
            # Calculate total liquidity in USD
            if 'usdc' in base_symbol_lower or 'usdt' in base_symbol_lower or 'dai' in base_symbol_lower:
                liquidity_usd = base_amount * Decimal('2')
            else:
                liquidity_usd = base_amount * Decimal('3000') * Decimal('2')
            
            return price_usd, liquidity_usd
        
        except Exception as e:
            self.logger.error(
                f"[BASESWAP] Error querying pair data: {e}",
                exc_info=True
            )
            return None, None