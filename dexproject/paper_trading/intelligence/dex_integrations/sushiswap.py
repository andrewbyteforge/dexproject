"""
SushiSwap DEX Integration for Real Price Queries

This module implements the SushiSwap (V2-style) integration for Phase 2 multi-DEX
price comparison. It queries real SushiSwap pools on-chain for price data.

Phase 2: Multi-DEX Price Comparison
File: paper_trading/intelligence/dex_integrations/sushiswap.py

FIXED: Proper price calculation - normalizes reserves for decimals BEFORE calculating price
"""

import logging
import time
from decimal import Decimal
from typing import Optional, Dict, Any, List

from django.utils import timezone

# Import base DEX class
from .base_dex import BaseDEX, DEXPrice

# Import defaults
from paper_trading.defaults import DEXComparisonDefaults

logger = logging.getLogger(__name__)


# =============================================================================
# SUSHISWAP CONSTANTS
# =============================================================================

# SushiSwap Factory addresses by chain
SUSHISWAP_FACTORY: Dict[int, str] = {
    84532: '0x71524B4f93c58fcbF659783284E38825f0622859',  # Base Sepolia
    8453: '0x71524B4f93c58fcbF659783284E38825f0622859',   # Base Mainnet
    1: '0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac',      # Ethereum Mainnet
}

# SushiSwap V2 Factory ABI (minimal)
FACTORY_ABI = [
    {
        "constant": True,
        "inputs": [
            {"name": "tokenA", "type": "address"},
            {"name": "tokenB", "type": "address"}
        ],
        "name": "getPair",
        "outputs": [{"name": "pair", "type": "address"}],
        "type": "function"
    }
]

# SushiSwap V2 Pair ABI (minimal)
PAIR_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"name": "reserve0", "type": "uint112"},
            {"name": "reserve1", "type": "uint112"},
            {"name": "blockTimestampLast", "type": "uint32"}
        ],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function"
    }
]

# ERC20 ABI for getting token decimals
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]


# =============================================================================
# SUSHISWAP DEX INTEGRATION
# =============================================================================

class SushiSwapDEX(BaseDEX):
    """
    SushiSwap integration for real price and liquidity queries.
    
    Features:
    - Queries real SushiSwap pairs on-chain
    - Uses Uniswap V2-style pair contracts
    - Calculates prices from reserves (FIXED: now normalizes for decimals)
    - Returns liquidity data for risk assessment
    
    FIXED: Now properly normalizes token reserves for decimals BEFORE
    calculating price ratio, preventing $0 or billion dollar prices.
    """
    
    def __init__(
        self,
        chain_id: int = 84532,
        cache_ttl_seconds: int = 30
    ):
        """
        Initialize SushiSwap DEX integration.
        
        Args:
            chain_id: Blockchain network ID
            cache_ttl_seconds: Cache TTL for price quotes
        """
        super().__init__(
            dex_name='sushiswap',
            chain_id=chain_id,
            cache_ttl_seconds=cache_ttl_seconds
        )
        
        # SushiSwap specific configuration
        self.factory_address = SUSHISWAP_FACTORY.get(chain_id)
        
        # Base tokens for price pairs
        self.base_tokens = self._get_base_tokens(chain_id)
        
        self.logger.info(
            f"[SUSHISWAP] Initialized for chain {chain_id}, "
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
        Get token price from SushiSwap pairs.
        
        This method:
        1. Checks cache first
        2. Finds pair with WETH or USDC
        3. Queries pair for reserves
        4. Gets token decimals for both tokens
        5. Normalizes reserves to actual amounts
        6. Calculates price from actual amounts (FIXED)
        7. Caches result
        
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
            self.logger.debug(f"[SUSHISWAP] Cache hit for {token_symbol}")
            return cached_price
        
        try:
            # Ensure Web3 client is initialized
            web3_client = await self._ensure_web3_client()
            if not web3_client:
                raise Exception("Web3 client unavailable")
            
            # Find best pair for this token
            pair_info = await self._find_best_pair(
                web3_client,
                token_address,
                token_symbol
            )
            
            if not pair_info:
                raise Exception(f"No SushiSwap pair found for {token_symbol}")
            
            # Calculate price and liquidity
            price_usd = pair_info['price_usd']
            liquidity_usd = pair_info['liquidity_usd']
            
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
                f"[SUSHISWAP] {token_symbol} price: ${price_usd:.4f}, "
                f"Liquidity: ${liquidity_usd:,.0f}, "
                f"Response: {response_time_ms:.0f}ms"
            )
            
            return price
        
        except Exception as e:
            # Record failure
            response_time_ms = (time.time() - start_time) * 1000
            self._record_failure()
            
            self.logger.error(
                f"[SUSHISWAP] Error getting price for {token_symbol}: {e}",
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
        Get available liquidity for token on SushiSwap.
        
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
                f"[SUSHISWAP] Error getting liquidity for {token_address}: {e}"
            )
            return None
    
    async def is_available(self) -> bool:
        """
        Check if SushiSwap is available on this chain.
        
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
    # SUSHISWAP SPECIFIC METHODS
    # =========================================================================
    
    async def _find_best_pair(
        self,
        web3_client: Any,
        token_address: str,
        token_symbol: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find best SushiSwap pair for token.
        
        Searches for pairs with WETH and USDC and returns the one
        with highest liquidity.
        
        Args:
            web3_client: Connected Web3 client
            token_address: Token contract address
            token_symbol: Token symbol
            
        Returns:
            Dictionary with pair info or None if not found
        """
        try:
            # Get factory contract
            factory_contract = web3_client.web3.eth.contract(
                address=web3_client.web3.to_checksum_address(self.factory_address),
                abi=FACTORY_ABI
            )
            
            best_pair = None
            best_liquidity = Decimal('0')
            
            # Check each base token
            for base_token in self.base_tokens:
                try:
                    # Query factory for pair address
                    pair_address = factory_contract.functions.getPair(
                        web3_client.web3.to_checksum_address(token_address),
                        web3_client.web3.to_checksum_address(base_token['address'])
                    ).call()
                    
                    # Check if pair exists
                    if pair_address == '0x0000000000000000000000000000000000000000':
                        continue
                    
                    # Query pair for reserves and price (FIXED METHOD)
                    pair_data = await self._query_pair_data(
                        web3_client,
                        pair_address,
                        token_address,
                        base_token
                    )
                    
                    if pair_data and pair_data['liquidity_usd'] > best_liquidity:
                        best_liquidity = pair_data['liquidity_usd']
                        best_pair = pair_data
                
                except Exception as e:
                    self.logger.debug(
                        f"[SUSHISWAP] No pair found for {token_symbol}-{base_token['symbol']}"
                    )
                    continue
            
            if best_pair:
                self.logger.info(
                    f"[SUSHISWAP] Found pair for {token_symbol} with "
                    f"${best_liquidity:,.0f} liquidity"
                )
            
            return best_pair
        
        except Exception as e:
            self.logger.error(
                f"[SUSHISWAP] Error finding pair for {token_symbol}: {e}",
                exc_info=True
            )
            return None
    
    async def _query_pair_data(
        self,
        web3_client: Any,
        pair_address: str,
        token_address: str,
        base_token: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Query SushiSwap pair for price and liquidity data.
        
        FIXED: Now properly gets decimals for both tokens and normalizes
        reserves BEFORE calculating price ratio.
        
        Args:
            web3_client: Connected Web3 client
            pair_address: Pair contract address
            token_address: Token being priced
            base_token: Base token info (WETH, USDC)
            
        Returns:
            Dictionary with price and liquidity data
        """
        try:
            # Get pair contract
            pair_contract = web3_client.web3.eth.contract(
                address=web3_client.web3.to_checksum_address(pair_address),
                abi=PAIR_ABI
            )
            
            # Query pair state
            reserves = pair_contract.functions.getReserves().call()
            token0 = pair_contract.functions.token0().call()
            token1 = pair_contract.functions.token1().call()
            
            reserve0 = Decimal(reserves[0])
            reserve1 = Decimal(reserves[1])
            
            # Determine which reserve is our token
            token0_lower = token0.lower()
            token_address_lower = token_address.lower()
            
            if token0_lower == token_address_lower:
                # Token is token0
                token_reserve_raw = reserve0
                base_reserve_raw = reserve1
                our_token_address = token0
                their_token_address = token1
            else:
                # Token is token1
                token_reserve_raw = reserve1
                base_reserve_raw = reserve0
                our_token_address = token1
                their_token_address = token0
            
            # FIXED: Get decimals for both tokens
            our_token_contract = web3_client.web3.eth.contract(
                address=web3_client.web3.to_checksum_address(our_token_address),
                abi=ERC20_ABI
            )
            their_token_contract = web3_client.web3.eth.contract(
                address=web3_client.web3.to_checksum_address(their_token_address),
                abi=ERC20_ABI
            )
            
            our_token_decimals = our_token_contract.functions.decimals().call()
            their_token_decimals = their_token_contract.functions.decimals().call()
            
            # FIXED: Normalize reserves to actual token amounts FIRST
            token_amount = token_reserve_raw / Decimal(10 ** our_token_decimals)
            base_amount = base_reserve_raw / Decimal(10 ** their_token_decimals)
            
            # Safety check: ensure we have liquidity
            if token_amount <= 0 or base_amount <= 0:
                self.logger.debug(
                    f"[SUSHISWAP] Pair {pair_address[:10]}... has zero liquidity"
                )
                return None
            
            # FIXED: Calculate price from actual amounts (not raw reserves)
            price_ratio = base_amount / token_amount
            
            # Convert to USD price based on base token
            if base_token['symbol'] == 'USDC':
                # USDC is approximately $1
                price_usd = price_ratio
            else:
                # WETH - approximate at $2500 (simplified)
                price_usd = price_ratio * Decimal('2500')
            
            # Calculate total liquidity in USD
            # Total pool value = (base_amount * base_token_usd_price) * 2
            if base_token['symbol'] == 'USDC':
                base_token_usd_price = Decimal('1')
            else:
                base_token_usd_price = Decimal('2500')  # WETH approximate
            
            liquidity_usd = base_amount * base_token_usd_price * Decimal('2')
            
            self.logger.debug(
                f"[SUSHISWAP] Pair {pair_address[:10]}... | "
                f"Token amount: {token_amount:.4f}, "
                f"Base amount: {base_amount:.4f}, "
                f"Price: ${price_usd:.4f}, "
                f"Liquidity: ${liquidity_usd:,.0f}"
            )
            
            return {
                'pair_address': pair_address,
                'base_token': base_token['symbol'],
                'price_usd': price_usd,
                'liquidity_usd': liquidity_usd,
                'token_amount': token_amount,
                'base_amount': base_amount
            }
        
        except Exception as e:
            self.logger.debug(
                f"[SUSHISWAP] Error querying pair {pair_address[:10]}...: {e}"
            )
            return None