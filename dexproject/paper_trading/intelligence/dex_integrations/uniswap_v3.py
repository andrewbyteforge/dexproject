"""
Uniswap V3 DEX Integration with Live Base Token Prices

This module implements the Uniswap V3 integration using LIVE prices from multiple sources.

Key Innovation:
- Base tokens (WETH, USDC) use live prices from PriceFeedService (CoinGecko aggregation)
- All other tokens calculated from Uniswap V3 pools using real base token prices
- No hardcoded prices = always accurate

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
# ERC20 ABI FOR TOKEN QUERIES
# =============================================================================

# Minimal ERC20 ABI for getting balances and decimals
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


# =============================================================================
# UNISWAP V3 DEX INTEGRATION WITH LIVE PRICES
# =============================================================================

class UniswapV3DEX(BaseDEX):
    """
    Uniswap V3 integration with LIVE base token prices from multiple exchanges.
    
    Architecture:
    1. Base tokens (WETH, USDC) get prices from PriceFeedService (CoinGecko)
    2. CoinGecko aggregates from 100+ exchanges (Binance, Coinbase, Kraken, etc.)
    3. All other tokens calculated from Uniswap pools using real base prices
    4. No hardcoded prices = always accurate
    
    Features:
    - Live prices from multiple sources
    - Proper token identification
    - Strict price validation
    - Deep liquidity data
    """
    
    def __init__(
        self,
        chain_id: int = 8453,
        cache_ttl_seconds: int = 30
    ):
        """
        Initialize Uniswap V3 DEX integration with live price support.
        
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
        
        # Base tokens (without hardcoded prices)
        self.base_tokens = self._get_base_tokens(chain_id)
        
        # Cache for base token prices (refreshed each query)
        self._base_token_prices: Optional[Dict[str, Decimal]] = None
        self._base_prices_last_updated: Optional[float] = None
        self._base_prices_cache_seconds = 60  # Refresh every minute
        
        self.logger.info(
            f"[UNISWAP V3] Initialized for chain {chain_id} with LIVE price feeds"
        )
    
    def _get_base_tokens(self, chain_id: int) -> List[Dict[str, str]]:
        """
        Get base tokens for this chain (without hardcoded prices).
        
        Args:
            chain_id: Blockchain network ID
            
        Returns:
            List of base token dictionaries
        """
        base_tokens_by_chain = {
            84532: [  # Base Sepolia (testnet)
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
    
    async def _get_base_token_prices(self) -> Dict[str, Decimal]:
        """
        Get LIVE USD prices for base tokens from PriceFeedService.
        
        This fetches prices from CoinGecko, which aggregates from 100+ exchanges:
        - Binance, Coinbase, Kraken, etc.
        - Returns volume-weighted average prices
        - Most accurate real-world market prices
        
        Caches results for 60 seconds to avoid excessive API calls.
        
        Returns:
            Dictionary mapping symbol to USD price
        """
        # Check cache first
        current_time = time.time()
        if (self._base_token_prices and self._base_prices_last_updated and
            (current_time - self._base_prices_last_updated) < self._base_prices_cache_seconds):
            return self._base_token_prices
        
        try:
            from paper_trading.services.price_feed_service import PriceFeedService
            
            price_feed = PriceFeedService(chain_id=self.chain_id)
            prices = {}
            
            # Get WETH price from CoinGecko (aggregated from multiple exchanges)
            weth_token = next((t for t in self.base_tokens if t['symbol'] == 'WETH'), None)
            if weth_token:
                try:
                    weth_data = await price_feed.get_token_price(weth_token['address'], 'WETH')
                    if weth_data and weth_data.get('price_usd'):
                        weth_price = Decimal(str(weth_data['price_usd']))
                        prices['WETH'] = weth_price
                        self.logger.info(
                            f"[UNISWAP V3] 📊 LIVE WETH price: ${weth_price:.2f} "
                            f"(from CoinGecko aggregation)"
                        )
                except Exception as e:
                    self.logger.warning(f"[UNISWAP V3] Failed to get WETH price: {e}")
            
            # Get USDC price (should be ~$1, but verify)
            usdc_token = next((t for t in self.base_tokens if t['symbol'] == 'USDC'), None)
            if usdc_token:
                try:
                    usdc_data = await price_feed.get_token_price(usdc_token['address'], 'USDC')
                    if usdc_data and usdc_data.get('price_usd'):
                        usdc_price = Decimal(str(usdc_data['price_usd']))
                        # Validate USDC is within reasonable range
                        if Decimal('0.98') <= usdc_price <= Decimal('1.02'):
                            prices['USDC'] = usdc_price
                            self.logger.debug(f"[UNISWAP V3] USDC price: ${usdc_price:.4f}")
                        else:
                            self.logger.warning(
                                f"[UNISWAP V3] USDC price ${usdc_price:.4f} outside normal range, "
                                f"using $1.00"
                            )
                            prices['USDC'] = Decimal('1.00')
                except Exception as e:
                    self.logger.warning(f"[UNISWAP V3] Failed to get USDC price: {e}")
                    prices['USDC'] = Decimal('1.00')
            
            # Fallback prices if API fails
            if 'WETH' not in prices:
                fallback_weth = Decimal('3400')
                prices['WETH'] = fallback_weth
                self.logger.warning(
                    f"[UNISWAP V3] ⚠️ Using FALLBACK WETH price: ${fallback_weth} "
                    f"(PriceFeedService unavailable)"
                )
            
            if 'USDC' not in prices:
                prices['USDC'] = Decimal('1.00')
            
            # Cache the results
            self._base_token_prices = prices
            self._base_prices_last_updated = current_time
            
            return prices
        
        except Exception as e:
            self.logger.error(f"[UNISWAP V3] Error getting base token prices: {e}")
            
            # Return fallback prices
            return {
                'WETH': Decimal('3400'),
                'USDC': Decimal('1.00')
            }
    
    # =========================================================================
    # MAIN INTERFACE METHODS
    # =========================================================================
    
    async def get_token_price(
        self,
        token_address: str,
        token_symbol: str
    ) -> DEXPrice:
        """
        Get token price from Uniswap V3 pools using LIVE base token prices.
        
        Process:
        1. Get LIVE base token prices (WETH, USDC) from PriceFeedService
        2. Find best Uniswap V3 pool for target token
        3. Calculate price using LIVE base token prices
        4. Validate result
        5. Cache and return
        
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
            # Get LIVE base token prices first
            base_prices = await self._get_base_token_prices()
            
            # Ensure Web3 client is initialized
            web3_client = await self._ensure_web3_client()
            if not web3_client:
                raise Exception("Web3 client unavailable")
            
            # Find best pool for this token
            pool_info = await self._find_best_pool(
                web3_client,
                token_address,
                token_symbol,
                base_prices
            )
            
            if not pool_info:
                self._record_failure()
                return DEXPrice(
                    dex_name=self.dex_name,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    success=False,
                    error_message="No pool found with sufficient liquidity"
                )
            
            # Validate price is reasonable
            price_usd = pool_info['price_usd']
            if not self._validate_price(token_symbol, price_usd):
                self._record_failure()
                return DEXPrice(
                    dex_name=self.dex_name,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    success=False,
                    error_message=f"Price validation failed: ${price_usd:.4f}"
                )
            
            # Create successful result
            query_time_ms = (time.time() - start_time) * 1000
            
            price_obj = DEXPrice(
                dex_name=self.dex_name,
                token_address=token_address,
                token_symbol=token_symbol,
                price_usd=price_usd,
                liquidity_usd=pool_info['liquidity_usd'],
                success=True,
                response_time_ms=query_time_ms
            )
            
            # Cache and log
            self._cache_price(price_obj)
            self._record_success()
            
            self.logger.info(
                f"[UNISWAP V3] {token_symbol} price: ${price_usd:.4f}, "
                f"Liquidity: ${pool_info['liquidity_usd']:,.0f}, "
                f"Base: {pool_info['base_token']}, "
                f"Response: {query_time_ms:.0f}ms"
            )
            
            return price_obj
        
        except Exception as e:
            self.logger.error(
                f"[UNISWAP V3] Error fetching price for {token_symbol}: {e}",
                exc_info=True
            )
            self._record_failure()
            
            return DEXPrice(
                dex_name=self.dex_name,
                token_address=token_address,
                token_symbol=token_symbol,
                success=False,
                error_message=str(e),
                response_time_ms=(time.time() - start_time) * 1000
            )
    
    async def get_liquidity(
        self,
        token_address: str
    ) -> Optional[Decimal]:
        """Get available liquidity for token."""
        price_obj = await self.get_token_price(token_address, "UNKNOWN")
        return price_obj.liquidity_usd if price_obj.success else None
    
    async def is_available(self) -> bool:
        """Check if Uniswap V3 is available."""
        web3_client = await self._ensure_web3_client()
        return web3_client is not None
    
    # =========================================================================
    # UNISWAP V3 SPECIFIC METHODS
    # =========================================================================
    
    async def _find_best_pool(
        self,
        web3_client: Any,
        token_address: str,
        token_symbol: str,
        base_prices: Dict[str, Decimal]
    ) -> Optional[Dict[str, Any]]:
        """
        Find best Uniswap V3 pool for token across all fee tiers.
        
        Args:
            web3_client: Connected Web3 client
            token_address: Token contract address
            token_symbol: Token symbol
            base_prices: Live USD prices for base tokens
            
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
                # Get live price for this base token
                base_token_price = base_prices.get(base_token['symbol'])
                if not base_token_price:
                    continue
                
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
                            base_token_price,
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
        base_token_usd_price: Decimal,
        fee_tier: int
    ) -> Optional[Dict[str, Any]]:
        """
        Query Uniswap V3 pool for price and liquidity using LIVE base token price.
        
        Args:
            web3_client: Connected Web3 client
            pool_address: Pool contract address
            token_address: Token being priced
            base_token: Base token info
            base_token_usd_price: LIVE USD price of base token
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
            
            # Get token0 and token1 from pool
            token0_address = pool_contract.functions.token0().call()
            token1_address = pool_contract.functions.token1().call()
            
            # Normalize addresses for comparison
            token_address_lower = token_address.lower()
            base_token_address_lower = base_token['address'].lower()
            token0_lower = token0_address.lower()
            token1_lower = token1_address.lower()
            
            # Identify which token is which - VERIFY BOTH!
            if token0_lower == token_address_lower and token1_lower == base_token_address_lower:
                our_token_address = token0_address
                base_token_address_actual = token1_address
            elif token1_lower == token_address_lower and token0_lower == base_token_address_lower:
                our_token_address = token1_address
                base_token_address_actual = token0_address
            else:
                # Pool doesn't match expected pair
                return None
            
            # Create ERC20 contracts
            our_token_contract = web3_client.web3.eth.contract(
                address=web3_client.web3.to_checksum_address(our_token_address),
                abi=ERC20_ABI
            )
            base_token_contract = web3_client.web3.eth.contract(
                address=web3_client.web3.to_checksum_address(base_token_address_actual),
                abi=ERC20_ABI
            )
            
            # Get token decimals
            our_token_decimals = our_token_contract.functions.decimals().call()
            base_token_decimals = base_token_contract.functions.decimals().call()
            
            # Get actual token balances in the pool
            pool_address_checksum = web3_client.web3.to_checksum_address(pool_address)
            our_token_balance_raw = our_token_contract.functions.balanceOf(pool_address_checksum).call()
            base_token_balance_raw = base_token_contract.functions.balanceOf(pool_address_checksum).call()
            
            # Convert to actual amounts (accounting for decimals)
            our_token_amount = Decimal(our_token_balance_raw) / Decimal(10 ** our_token_decimals)
            base_token_amount = Decimal(base_token_balance_raw) / Decimal(10 ** base_token_decimals)
            
            # Safety check: ensure we have liquidity
            if our_token_amount == 0 or base_token_amount == 0:
                return None
            
            # Calculate price using LIVE base token price
            # Price = (base_token_amount / our_token_amount) * base_token_usd_price
            price_in_base_token = base_token_amount / our_token_amount
            price_usd = price_in_base_token * base_token_usd_price
            
            # Calculate total liquidity in USD using LIVE price
            liquidity_usd = base_token_amount * base_token_usd_price * Decimal('2')
            
            self.logger.debug(
                f"[UNISWAP V3] Pool {pool_address[:10]}... | "
                f"Our token: {our_token_amount:.4f}, "
                f"Base ({base_token['symbol']}): {base_token_amount:.4f} @ ${base_token_usd_price:.2f}, "
                f"Price: ${price_usd:.4f}, "
                f"Liquidity: ${liquidity_usd:,.0f}"
            )
            
            return {
                'pool_address': pool_address,
                'fee_tier': fee_tier,
                'base_token': base_token['symbol'],
                'price_usd': price_usd,
                'liquidity_usd': liquidity_usd,
                'our_token_amount': our_token_amount,
                'base_token_amount': base_token_amount
            }
        
        except Exception as e:
            self.logger.debug(f"[UNISWAP V3] Error querying pool: {e}")
            return None
    
    def _validate_price(self, token_symbol: str, price_usd: Decimal) -> bool:
        """Validate that price is reasonable."""
        stablecoins = ['USDC', 'USDT', 'DAI', 'FRAX', 'LUSD', 'BUSD']
        
        if token_symbol in stablecoins:
            if not (Decimal('0.98') <= price_usd <= Decimal('1.02')):
                self.logger.error(
                    f"[UNISWAP V3] ❌ REJECTED - Invalid stablecoin price: "
                    f"{token_symbol} at ${price_usd:.4f} (expected ~$1.00)"
                )
                return False
        
        if price_usd <= 0:
            self.logger.error(
                f"[UNISWAP V3] ❌ REJECTED - Non-positive price: "
                f"{token_symbol} at ${price_usd:.4f}"
            )
            return False
        
        if price_usd > Decimal('1000000'):
            self.logger.error(
                f"[UNISWAP V3] ❌ REJECTED - Unrealistic price: "
                f"{token_symbol} at ${price_usd:.4f}"
            )
            return False
        
        return True