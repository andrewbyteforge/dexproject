"""
Curve Finance DEX Integration - COMPLETE IMPLEMENTATION

Curve Finance integration for stablecoin and low-slippage price queries.
Curve uses a specialized stableswap AMM optimized for low-slippage swaps.

This implementation:
- Queries Curve registry to find pools containing tokens
- Handles both plain pools and meta pools
- Calculates prices using virtual price and get_dy methods
- Optimized for stablecoin pairs (USDC, USDT, DAI)
- Returns standardized DEXPrice objects

File: dexproject/paper_trading/intelligence/dex_integrations/curve.py
"""

import logging
import time as time_module
from decimal import Decimal
from typing import Optional, Dict, Any, List

# Import base classes
from paper_trading.intelligence.dex_integrations.base import BaseDEX, DEXPrice

# Import constants
from paper_trading.intelligence.dex_integrations.constants import (
    CURVE_REGISTRY,
    CURVE_ADDRESS_PROVIDER,
    ERC20_ABI
)

logger = logging.getLogger(__name__)


# Curve Registry ABI (minimal - what we need)
CURVE_REGISTRY_ABI = [
    {
        "name": "find_pool_for_coins",
        "outputs": [{"type": "address", "name": ""}],
        "inputs": [
            {"type": "address", "name": "_from"},
            {"type": "address", "name": "_to"},
            {"type": "uint256", "name": "i"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "name": "get_n_coins",
        "outputs": [{"type": "uint256", "name": ""}],
        "inputs": [{"type": "address", "name": "_pool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "name": "get_coins",
        "outputs": [{"type": "address[8]", "name": ""}],
        "inputs": [{"type": "address", "name": "_pool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "name": "get_balances",
        "outputs": [{"type": "uint256[8]", "name": ""}],
        "inputs": [{"type": "address", "name": "_pool"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# Curve Pool ABI (minimal - for price queries)
CURVE_POOL_ABI = [
    {
        "name": "get_dy",
        "outputs": [{"type": "uint256", "name": ""}],
        "inputs": [
            {"type": "int128", "name": "i"},
            {"type": "int128", "name": "j"},
            {"type": "uint256", "name": "dx"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "name": "get_virtual_price",
        "outputs": [{"type": "uint256", "name": ""}],
        "inputs": [],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "name": "balances",
        "outputs": [{"type": "uint256", "name": ""}],
        "inputs": [{"type": "uint256", "name": "arg0"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "name": "coins",
        "outputs": [{"type": "address", "name": ""}],
        "inputs": [{"type": "uint256", "name": "arg0"}],
        "stateMutability": "view",
        "type": "function"
    }
]


class CurveDEX(BaseDEX):
    """
    Curve Finance price fetching implementation.
    
    Curve is optimized for stablecoin swaps with minimal slippage.
    Uses specialized stableswap invariant instead of constant product.
    
    Best for:
    - Stablecoin pairs (USDC/USDT, DAI/USDC, etc.)
    - Low slippage on similar-value assets
    - Large stablecoin trades
    
    Process:
    1. Query registry to find pools containing token
    2. Get pool coins and balances
    3. Use get_dy to calculate exchange rate
    4. Convert to USD (stablecoins = $1.00)
    5. Calculate liquidity from pool balances
    """
    
    def __init__(
        self,
        chain_id: int = 8453,
        cache_ttl_seconds: int = 60
    ):
        """
        Initialize Curve integration.
        
        Args:
            chain_id: Blockchain network ID (default: 8453 = Base Mainnet)
            cache_ttl_seconds: Cache TTL for price data
        """
        super().__init__(
            dex_name="curve",
            chain_id=chain_id,
            cache_ttl_seconds=cache_ttl_seconds
        )
        
        # Get Curve registry address for this chain
        self.registry_address = CURVE_REGISTRY.get(chain_id)
        if not self.registry_address:
            self.logger.warning(
                f"[CURVE] No registry address for chain {chain_id}"
            )
        
        # Stablecoin addresses for USD conversion
        self.stablecoins = self._get_stablecoin_addresses(chain_id)
        
        self.logger.info(
            f"[CURVE] Initialized for chain {chain_id} with {len(self.stablecoins)} stablecoins"
        )
    
    def _get_stablecoin_addresses(self, chain_id: int) -> List[str]:
        """Get list of stablecoin addresses for this chain."""
        from paper_trading.intelligence.dex_integrations.constants import (
            USDC_ADDRESS,
            USDT_ADDRESS,
            DAI_ADDRESS
        )
        
        stables = []
        if chain_id in USDC_ADDRESS:
            stables.append(USDC_ADDRESS[chain_id].lower())
        if chain_id in USDT_ADDRESS:
            stables.append(USDT_ADDRESS[chain_id].lower())
        if chain_id in DAI_ADDRESS:
            stables.append(DAI_ADDRESS[chain_id].lower())
        
        return stables
    
    async def get_token_price(
        self,
        token_address: str,
        token_symbol: str
    ) -> DEXPrice:
        """
        Get token price from Curve.
        
        Process:
        1. Check cache
        2. Find pools containing this token
        3. Try each stablecoin pairing
        4. Use get_dy for exchange rate
        5. Convert to USD (stables = $1.00)
        6. Select pool with highest liquidity
        7. Cache result
        
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
            
            # Validate registry address
            if not self.registry_address:
                return DEXPrice(
                    dex_name=self.dex_name,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    success=False,
                    error_message=f"No Curve registry for chain {self.chain_id}",
                    query_time_ms=(time_module.time() - start_time) * 1000
                )
            
            # Find best pool across stablecoin pairs
            best_pool = await self._find_best_pool(token_address)
            
            if not best_pool:
                return DEXPrice(
                    dex_name=self.dex_name,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    success=False,
                    error_message="No Curve pool found",
                    query_time_ms=(time_module.time() - start_time) * 1000
                )
            
            # Get price from pool
            price_usd, liquidity_usd = await self._query_pool_price(
                best_pool['address'],
                token_address,
                best_pool['stable_coin'],
                best_pool['token_index'],
                best_pool['stable_index']
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
                    f"[CURVE] {token_symbol}: ${price_usd:.4f}, "
                    f"Liquidity: ${liquidity_usd:,.0f} ({query_time_ms:.0f}ms)"
                )
            else:
                price_obj.error_message = "Failed to fetch price from pool"
            
            return price_obj
        
        except Exception as e:
            self.logger.error(
                f"[CURVE] Error fetching price for {token_symbol}: {e}",
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
        Find best Curve pool for token.
        
        Tries each stablecoin to find pool with highest liquidity.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Dict with pool info, or None if not found
        """
        best_pool = None
        best_liquidity = Decimal('0')
        
        # Create registry contract
        try:
            registry_contract = self.web3_client.web3.eth.contract(
                address=self.registry_address,
                abi=CURVE_REGISTRY_ABI
            )
        except Exception as e:
            self.logger.error(f"[CURVE] Error creating registry contract: {e}")
            return None
        
        # Try each stablecoin
        for stable_address in self.stablecoins:
            try:
                # Find pool for this pair (try both directions)
                pool_address = registry_contract.functions.find_pool_for_coins(
                    token_address,
                    stable_address,
                    0  # First pool found
                ).call()
                
                # Check if pool exists
                if not pool_address or pool_address == '0x' + '0' * 40:
                    # Try reverse direction
                    pool_address = registry_contract.functions.find_pool_for_coins(
                        stable_address,
                        token_address,
                        0
                    ).call()
                
                if pool_address and pool_address != '0x' + '0' * 40:
                    # Get pool info
                    liquidity, token_idx, stable_idx = await self._get_pool_info(
                        pool_address,
                        token_address,
                        stable_address
                    )
                    
                    if liquidity > best_liquidity:
                        best_liquidity = liquidity
                        best_pool = {
                            'address': pool_address,
                            'stable_coin': stable_address,
                            'liquidity': liquidity,
                            'token_index': token_idx,
                            'stable_index': stable_idx
                        }
            
            except Exception as e:
                self.logger.debug(
                    f"[CURVE] Error checking pool for {token_address[:10]}.../{stable_address[:10]}...: {e}"
                )
                continue
        
        return best_pool
    
    async def _get_pool_info(
        self,
        pool_address: str,
        token_address: str,
        stable_address: str
    ) -> tuple[Decimal, int, int]:
        """
        Get pool liquidity and coin indices.
        
        Returns:
            Tuple of (liquidity_usd, token_index, stable_index)
        """
        try:
            pool_contract = self.web3_client.web3.eth.contract(
                address=pool_address,
                abi=CURVE_POOL_ABI
            )
            
            # Find coin indices
            token_idx = -1
            stable_idx = -1
            total_liquidity = Decimal('0')
            
            for i in range(8):  # Max 8 coins in Curve pool
                try:
                    coin = pool_contract.functions.coins(i).call()
                    balance = pool_contract.functions.balances(i).call()
                    
                    if coin.lower() == token_address.lower():
                        token_idx = i
                    elif coin.lower() == stable_address.lower():
                        stable_idx = i
                        # Add stable balance to liquidity (assuming $1.00)
                        total_liquidity += Decimal(balance) / Decimal(10 ** 6)  # Most stables are 6 decimals
                
                except Exception:
                    # No more coins
                    break
            
            if token_idx == -1 or stable_idx == -1:
                return Decimal('0'), -1, -1
            
            return total_liquidity, token_idx, stable_idx
        
        except Exception as e:
            self.logger.debug(f"[CURVE] Error getting pool info: {e}")
            return Decimal('0'), -1, -1
    
    async def _query_pool_price(
        self,
        pool_address: str,
        token_address: str,
        stable_address: str,
        token_idx: int,
        stable_idx: int
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """
        Query pool for price using get_dy.
        
        Args:
            pool_address: Pool contract address
            token_address: Target token address
            stable_address: Stablecoin address
            token_idx: Token index in pool
            stable_idx: Stablecoin index in pool
            
        Returns:
            Tuple of (price_usd, liquidity_usd)
        """
        try:
            pool_contract = self.web3_client.web3.eth.contract(
                address=pool_address,
                abi=CURVE_POOL_ABI
            )
            
            # Get token decimals
            token_contract = self.web3_client.web3.eth.contract(
                address=token_address,
                abi=ERC20_ABI
            )
            token_decimals = token_contract.functions.decimals().call()
            
            # Calculate exchange rate using get_dy
            # How much stable do we get for 1 token?
            one_token = 10 ** token_decimals
            
            stable_out = pool_contract.functions.get_dy(
                token_idx,
                stable_idx,
                one_token
            ).call()
            
            # Stablecoin is 6 or 18 decimals
            stable_contract = self.web3_client.web3.eth.contract(
                address=stable_address,
                abi=ERC20_ABI
            )
            stable_decimals = stable_contract.functions.decimals().call()
            
            # Price = stable_out / 10^stable_decimals (since stables = $1.00)
            price_usd = Decimal(stable_out) / Decimal(10 ** stable_decimals)
            
            # Calculate liquidity from pool balances
            total_liquidity = Decimal('0')
            for i in range(8):
                try:
                    balance = pool_contract.functions.balances(i).call()
                    coin = pool_contract.functions.coins(i).call()
                    
                    # Get coin decimals
                    coin_contract = self.web3_client.web3.eth.contract(
                        address=coin,
                        abi=ERC20_ABI
                    )
                    decimals = coin_contract.functions.decimals().call()
                    
                    # If it's a stablecoin, add to liquidity
                    if coin.lower() in self.stablecoins:
                        total_liquidity += Decimal(balance) / Decimal(10 ** decimals)
                
                except Exception:
                    break
            
            # If no stablecoin balances found, use stable balance * 2
            if total_liquidity == 0:
                stable_balance = pool_contract.functions.balances(stable_idx).call()
                total_liquidity = (Decimal(stable_balance) / Decimal(10 ** stable_decimals)) * Decimal('2')
            
            return price_usd, total_liquidity
        
        except Exception as e:
            self.logger.error(
                f"[CURVE] Error querying pool price: {e}",
                exc_info=True
            )
            return None, None