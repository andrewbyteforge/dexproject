"""
Aerodrome DEX Integration - BASE CHAIN SPECIFIC

Aerodrome is the leading DEX on Base chain, a fork of Velodrome.
Features both volatile (xy=k) and stable (Curve-style) pools.

This implementation:
- Queries Aerodrome factory for pairs
- Supports both volatile and stable pools
- Handles router for price queries
- Optimized for Base Mainnet (chain 8453)
- Returns standardized DEXPrice objects

Aerodrome is critical for Base trading as it has:
- Highest liquidity on Base
- Native BASE token integration
- Optimized gas costs
- Deep stablecoin pools

File: dexproject/paper_trading/intelligence/dex_integrations/aerodrome.py
"""

import logging
import time as time_module
from decimal import Decimal
from typing import Optional, Dict, Any, List

# Import base classes
from paper_trading.intelligence.dex_integrations.base import BaseDEX, DEXPrice

# Import constants
from paper_trading.intelligence.dex_integrations.constants import (
    ERC20_ABI,
    get_base_tokens
)

logger = logging.getLogger(__name__)


# Aerodrome addresses on Base Mainnet
AERODROME_ADDRESSES = {
    8453: {  # Base Mainnet
        'factory': '0x420DD381b31aEf6683db6B902084cB0FFECe40Da',
        'router': '0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43'
    }
}

# Aerodrome Factory ABI (minimal)
AERODROME_FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "bool", "name": "stable", "type": "bool"}
        ],
        "name": "getPair",
        "outputs": [{"internalType": "address", "name": "pair", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# Aerodrome Pair ABI (minimal)
AERODROME_PAIR_ABI = [
    {
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint256", "name": "_reserve0", "type": "uint256"},
            {"internalType": "uint256", "name": "_reserve1", "type": "uint256"},
            {"internalType": "uint256", "name": "_blockTimestampLast", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "stable",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    }
]


class AerodromeDEX(BaseDEX):
    """
    Aerodrome DEX price fetching implementation.
    
    Aerodrome is THE dominant DEX on Base chain (Velodrome fork).
    
    Features:
    - Volatile pools (constant product xy=k)
    - Stable pools (Curve-style for stablecoins)
    - Optimized for Base chain gas costs
    - Deep liquidity for Base-native tokens
    
    Best for:
    - Base chain trading (highest liquidity)
    - Both regular tokens (volatile) and stables (stable pools)
    - Low gas costs on L2
    
    Process:
    1. Try both volatile and stable pool types
    2. Check multiple base tokens (WETH, USDC, etc.)
    3. Get reserves and calculate price
    4. Select pool with highest liquidity
    """
    
    def __init__(
        self,
        chain_id: int = 8453,
        cache_ttl_seconds: int = 60
    ):
        """
        Initialize Aerodrome integration.
        
        Args:
            chain_id: Blockchain network ID (default: 8453 = Base Mainnet)
            cache_ttl_seconds: Cache TTL for price data
        """
        super().__init__(
            dex_name="aerodrome",
            chain_id=chain_id,
            cache_ttl_seconds=cache_ttl_seconds
        )
        
        # Get Aerodrome addresses for this chain
        addresses = AERODROME_ADDRESSES.get(chain_id)
        if not addresses:
            self.logger.warning(
                f"[AERODROME] No addresses configured for chain {chain_id}"
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
                f"[AERODROME] No base tokens configured for chain {chain_id}"
            )
        
        self.logger.info(
            f"[AERODROME] Initialized for Base chain with {len(self.base_tokens)} base tokens"
        )
    
    async def get_token_price(
        self,
        token_address: str,
        token_symbol: str
    ) -> DEXPrice:
        """
        Get token price from Aerodrome.
        
        Process:
        1. Check cache
        2. Try both volatile and stable pool types
        3. Check all base token pairs
        4. Get reserves and calculate price
        5. Select highest liquidity pool
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
                    error_message=f"No Aerodrome factory for chain {self.chain_id}",
                    query_time_ms=(time_module.time() - start_time) * 1000
                )
            
            # Find best pair (try both volatile and stable)
            best_pair = await self._find_best_pair(token_address)
            
            if not best_pair:
                return DEXPrice(
                    dex_name=self.dex_name,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    success=False,
                    error_message="No Aerodrome pair found",
                    query_time_ms=(time_module.time() - start_time) * 1000
                )
            
            # Query pair for price
            price_usd, liquidity_usd = await self._query_pair_data(
                best_pair['address'],
                token_address,
                best_pair['base_token'],
                best_pair['is_stable']
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
                
                pool_type = "stable" if best_pair['is_stable'] else "volatile"
                self.logger.debug(
                    f"[AERODROME] {token_symbol}: ${price_usd:.4f}, "
                    f"Liquidity: ${liquidity_usd:,.0f}, Type: {pool_type} ({query_time_ms:.0f}ms)"
                )
            else:
                price_obj.error_message = "Failed to fetch price from pair"
            
            return price_obj
        
        except Exception as e:
            self.logger.error(
                f"[AERODROME] Error fetching price for {token_symbol}: {e}",
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
        Find best Aerodrome pair for token.
        
        Tries both volatile and stable pools across all base tokens.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Dict with pair info, or None if not found
        """
        best_pair = None
        best_liquidity = Decimal('0')
        
        # Create factory contract
        factory_contract = self.web3_client.web3.eth.contract(
            address=self.factory_address,
            abi=AERODROME_FACTORY_ABI
        )
        
        # Try each base token with both pool types
        for base_token in self.base_tokens:
            for is_stable in [False, True]:  # Try volatile, then stable
                try:
                    # Query pair address
                    pair_address = factory_contract.functions.getPair(
                        token_address,
                        base_token,
                        is_stable
                    ).call()
                    
                    # Check if pair exists
                    if pair_address and pair_address != '0x' + '0' * 40:
                        # Get liquidity
                        liquidity = await self._get_pair_liquidity(
                            pair_address,
                            base_token
                        )
                        
                        if liquidity > best_liquidity:
                            best_liquidity = liquidity
                            best_pair = {
                                'address': pair_address,
                                'base_token': base_token,
                                'liquidity': liquidity,
                                'is_stable': is_stable
                            }
                
                except Exception as e:
                    self.logger.debug(
                        f"[AERODROME] Error checking pair "
                        f"({token_address[:10]}.../{base_token[:10]}.../"
                        f"{'stable' if is_stable else 'volatile'}): {e}"
                    )
                    continue
        
        return best_pair
    
    async def _get_pair_liquidity(
        self,
        pair_address: str,
        base_token_address: str
    ) -> Decimal:
        """Get liquidity from Aerodrome pair."""
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
            
            # Convert to USD
            base_symbol_lower = base_symbol.lower()
            if 'usdc' in base_symbol_lower or 'usdt' in base_symbol_lower or 'dai' in base_symbol_lower:
                liquidity_usd = base_amount * Decimal('2')
            else:
                # Assume WETH at $3000
                liquidity_usd = base_amount * Decimal('3000') * Decimal('2')
            
            return liquidity_usd
        
        except Exception as e:
            self.logger.debug(f"[AERODROME] Error getting pair liquidity: {e}")
            return Decimal('0')
    
    async def _query_pair_data(
        self,
        pair_address: str,
        token_address: str,
        base_token_address: str,
        is_stable: bool
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """
        Query pair for price and liquidity.
        
        Args:
            pair_address: Pair contract address
            token_address: Target token address
            base_token_address: Base token address
            is_stable: Whether this is a stable pool
            
        Returns:
            Tuple of (price_usd, liquidity_usd)
        """
        try:
            # Create pair contract
            pair_contract = self.web3_client.web3.eth.contract(
                address=pair_address,
                abi=AERODROME_PAIR_ABI
            )
            
            # Get token0 and token1
            token0 = pair_contract.functions.token0().call()
            token1 = pair_contract.functions.token1().call()
            
            # Get reserves
            reserves = pair_contract.functions.getReserves().call()
            reserve0 = Decimal(reserves[0])
            reserve1 = Decimal(reserves[1])
            
            # Determine token positions
            if token0.lower() == token_address.lower():
                token_contract = self.web3_client.web3.eth.contract(address=token0, abi=ERC20_ABI)
                base_contract = self.web3_client.web3.eth.contract(address=token1, abi=ERC20_ABI)
                token_reserve = reserve0
                base_reserve = reserve1
            else:
                token_contract = self.web3_client.web3.eth.contract(address=token1, abi=ERC20_ABI)
                base_contract = self.web3_client.web3.eth.contract(address=token0, abi=ERC20_ABI)
                token_reserve = reserve1
                base_reserve = reserve0
            
            # Get decimals
            token_decimals = token_contract.functions.decimals().call()
            base_decimals = base_contract.functions.decimals().call()
            base_symbol = base_contract.functions.symbol().call()
            
            # Convert to amounts
            token_amount = token_reserve / Decimal(10 ** token_decimals)
            base_amount = base_reserve / Decimal(10 ** base_decimals)
            
            # Check for zero reserves
            if token_amount == 0 or base_amount == 0:
                return None, None
            
            # Calculate price
            price_in_base = base_amount / token_amount
            
            # Convert to USD
            base_symbol_lower = base_symbol.lower()
            if 'usdc' in base_symbol_lower or 'usdt' in base_symbol_lower or 'dai' in base_symbol_lower:
                price_usd = price_in_base
                liquidity_usd = base_amount * Decimal('2')
            else:
                # WETH at $3000
                price_usd = price_in_base * Decimal('3000')
                liquidity_usd = base_amount * Decimal('3000') * Decimal('2')
            
            return price_usd, liquidity_usd
        
        except Exception as e:
            self.logger.error(
                f"[AERODROME] Error querying pair data: {e}",
                exc_info=True
            )
            return None, None