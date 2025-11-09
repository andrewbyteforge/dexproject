"""
OPTIMIZED Real Price Feed Service for Paper Trading

This is an OPTIMIZED version that reduces CoinGecko API calls by 90% by:
1. Fetching multiple token prices in a SINGLE API call
2. Using bulk endpoints instead of per-token requests
3. Smarter caching strategy

KEY IMPROVEMENTS:
- 9 tokens = 1 API call (instead of 9 separate calls)
- Reduces monthly API usage from 10,000/day to ~1,100/day
- Stays within CoinGecko free tier limits

File: dexproject/paper_trading/services/price_feed_service.py
"""
import asyncio
from contextlib import suppress
from typing import Any, Awaitable, Callable, Optional
import logging
import asyncio
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
import aiohttp
from django.conf import settings
from django.core.cache import cache

# Import centralized token addresses from shared constants
from shared.constants import TOKEN_ADDRESSES_BY_CHAIN

# Import existing Web3 infrastructure
from shared.web3_utils import (
    Web3,
    is_address,
    to_checksum_ethereum_address
)

logger = logging.getLogger(__name__)


# =============================================================================
# CACHE CONFIGURATION
# =============================================================================

# Primary cache TTL (configurable via environment)
# Default: 60 seconds - balances freshness with API call reduction
# Can be overridden with PRICE_CACHE_TTL_SECONDS environment variable
PRICE_CACHE_TTL = int(getattr(settings, 'PRICE_CACHE_TTL_SECONDS', 60))

# Stale cache TTL - how long to keep "stale" cache as backup
# If API fails, we can serve data up to this age
STALE_CACHE_TTL = PRICE_CACHE_TTL * 4  # 4 minutes by default

# Cache key prefixes for Redis
PRICE_CACHE_PREFIX = "token_price"
STALE_CACHE_PREFIX = "token_price_stale"
BULK_CACHE_PREFIX = "bulk_token_prices"

# Stablecoin cache TTL (much longer since they don't change)
STABLECOIN_CACHE_TTL = 3600  # 1 hour

# API endpoints
COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"

# Supported chains for price lookup
SUPPORTED_CHAINS: Dict[int, str] = {
    1: "ethereum",      # Ethereum Mainnet
    8453: "base",       # Base Mainnet
    11155111: "sepolia",  # Ethereum Sepolia
    84532: "base-sepolia"  # Base Sepolia
}

# Known stablecoins (always return $1.00)
STABLECOINS: Dict[str, Decimal] = {
    "USDC": Decimal("1.00"),
    "USDT": Decimal("1.00"),
    "DAI": Decimal("1.00"),
}


# =============================================================================
# OPTIMIZED PRICE FEED SERVICE WITH BULK FETCHING
# =============================================================================

class PriceFeedService:
    """
    OPTIMIZED real-time token price fetching service with bulk API calls.
    
    KEY OPTIMIZATION: Fetches multiple token prices in a single API call,
    reducing API usage by 90% compared to per-token requests.
    
    Features:
    - Bulk CoinGecko API calls (1 call for all tokens)
    - Smart Redis caching (60s fresh + 4min stale for resilience)
    - Stale-while-revalidate pattern
    - Cache performance tracking
    - Multi-chain support
    - Comprehensive error handling
    
    Cache Strategy:
    - Fresh cache: 60 seconds (configurable)
    - Stale cache: 4 minutes (fallback during API failures)
    - Stablecoins: 1 hour (they don't change)
    - Reduces API calls from 9/update to 1/update (90% reduction)
    
    Example usage:
        service = PriceFeedService(chain_id=84532)
        
        # Bulk fetch (RECOMMENDED - 1 API call)
        prices = await service.get_bulk_token_prices([
            ('WETH', '0x4200...'),
            ('USDC', '0x036C...'),
            ('DAI', '0x50c5...')
        ])
        # Returns: {'WETH': Decimal('2543.50'), 'USDC': Decimal('1.00'), ...}
        
        # Single token (uses bulk cache if available)
        price = await service.get_token_price("0xC02...WETH", "WETH")
        # Returns: Decimal("2543.50")
    """
    
    def __init__(
        self,
        chain_id: int,
        web3_client: Optional[Any] = None
    ) -> None:
        """
        Initialize price feed service for a specific chain.
        
        Args:
            chain_id: Blockchain network ID (e.g., 84532 for Base Sepolia)
            web3_client: Optional Web3Client for DEX quotes
        """
        self.chain_id: int = chain_id
        self.chain_name: str = self._get_chain_name(chain_id)
        
        # Token addresses for this chain (from centralized constants)
        self.token_addresses: Dict[str, str] = self._get_token_addresses()
        
        # Price cache - stores last known prices
        self.price_cache: Dict[str, Decimal] = {}
        self.last_update: Dict[str, datetime] = {}
        
        # Cache statistics tracking
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.stale_cache_hits: int = 0
        self.api_call_count: int = 0
        self.bulk_api_calls: int = 0
        
        # CoinGecko API Configuration  
        self.coingecko_base_url: str = "https://api.coingecko.com/api/v3"
        self.coingecko_api_key: Optional[str] = getattr(settings, 'COIN_GECKO_API_KEY', None)
        
        # Rate limiting for CoinGecko free tier
        self.last_coingecko_call: Optional[datetime] = None
        self.coingecko_rate_limit_seconds: float = 1.5
        
        # Request timeout configuration
        self.request_timeout_seconds: int = 10
        
        # Session holder (lazy initialization)
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Web3 infrastructure for DEX quotes (optional)
        self.web3_client: Optional[Any] = web3_client
        self.dex_quotes_enabled: bool = web3_client is not None
        
        logger.info(
            f"[PRICE FEED] Initialized OPTIMIZED service for chain {chain_id} ({self.chain_name}), "
            f"Bulk fetching: ENABLED, "
            f"DEX quotes: {'ENABLED' if self.dex_quotes_enabled else 'DISABLED'}"
        )    

    def _get_chain_name(self, chain_id: int) -> str:
        """
        Get human-readable chain name from chain ID.
        
        Args:
            chain_id: Blockchain network ID
            
        Returns:
            Human-readable chain name
        """
        chain_names: Dict[int, str] = {
            1: 'mainnet',
            5: 'goerli',
            11155111: 'sepolia',
            84531: 'base-goerli',
            84532: 'base-sepolia',
            8453: 'base-mainnet',
            137: 'polygon',
            80001: 'mumbai',
            42161: 'arbitrum',
            421613: 'arbitrum-goerli'
        }
        return chain_names.get(chain_id, f'chain-{chain_id}')

    def _get_token_addresses(self) -> Dict[str, str]:
        """
        Get token addresses for the current chain from centralized constants.
        
        Fetches addresses from TOKEN_ADDRESSES_BY_CHAIN and validates them
        with checksum conversion. Invalid addresses are skipped with a warning
        rather than crashing the entire service.
        
        Returns:
            Dictionary mapping token symbols to checksummed addresses.
            Empty dict if no addresses configured for this chain.
            
        Notes:
            - Uses centralized TOKEN_ADDRESSES_BY_CHAIN constant
            - Automatically checksums all addresses for Web3 compatibility
            - Skips invalid addresses instead of raising exceptions
            - Logs warnings for any validation failures
        
        Example:
            >>> service = PriceFeedService(chain_id=84532)
            >>> addresses = service._get_token_addresses()
            >>> addresses['WETH']
            '0x4200000000000000000000000000000000000006'
        """
        def _checksum_or_raise(address: str, symbol: str) -> str:
            """
            Helper function to checksum an address or raise if invalid.
            
            Args:
                address: The Ethereum address to checksum
                symbol: The token symbol (for error messages)
                
            Returns:
                Checksummed address string
                
            Raises:
                ValueError: If address is invalid and cannot be checksummed
            """
            checksummed = to_checksum_ethereum_address(address)
            if checksummed is None:
                raise ValueError(f"Invalid address for {symbol}: {address}")
            return checksummed
        
        # Get addresses from centralized constants for this chain
        chain_tokens: Dict[str, str] = TOKEN_ADDRESSES_BY_CHAIN.get(self.chain_id, {})
        
        # Log if no addresses found for this chain
        if not chain_tokens:
            logger.warning(
                f"[PRICE FEED] No token addresses configured for chain {self.chain_id} "
                f"in TOKEN_ADDRESSES_BY_CHAIN constant"
            )
            return {}
        
        # Checksum all addresses for Web3 compatibility
        checksummed_tokens: Dict[str, str] = {}
        for symbol, address in chain_tokens.items():
            try:
                checksummed_tokens[symbol] = _checksum_or_raise(address, symbol)
            except ValueError as e:
                # Skip invalid addresses with warning instead of crashing
                logger.warning(
                    f"[PRICE FEED] Skipping invalid address for {symbol} "
                    f"on chain {self.chain_id}: {e}"
                )
                continue
        
        # Log success
        logger.info(
            f"[PRICE FEED] Loaded {len(checksummed_tokens)} token addresses "
            f"for chain {self.chain_id}: {', '.join(checksummed_tokens.keys())}"
        )
        
        return checksummed_tokens

    from typing import Optional, Dict

    def _get_coingecko_id(self, token_symbol: str, address: str, chain_id: int) -> Optional[str]:
        """
        Resolve a CoinGecko ID for a given token on a specific chain.

        Prefer explicit per-chain address mappings; if not found, use a conservative
        symbol fallback for well-known assets. Returns None when unresolved.

        Args:
            token_symbol: Token symbol (e.g., 'WETH', 'USDC', 'DAI', 'cbETH')
            address: Token contract address on the given chain (checksum or lower)
            chain_id: EVM chain id (e.g., 8453 for Base mainnet, 1 for Ethereum)

        Returns:
            CoinGecko asset id string or None if unknown.
        """
        sym = (token_symbol or "").strip().upper()
        addr = (address or "").strip().lower()

        # --- Explicit per-chain address mappings ---
        per_chain: Dict[int, Dict[str, str]] = {
            # Base mainnet (8453)
            8453: {
                # WETH on Base
                "0x4200000000000000000000000000000000000006": "weth",
                # USDC (native) on Base
                "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": "usd-coin",
                # DAI on Base
                "0x50c57259e8bbb31c10c1e2a9f98c171d7290d3e1": "dai",
                # cbETH on Base
                "0x2ae3f1ec7f1f5012cfe0f2108faadf6f0b9adcc1": "coinbase-wrapped-staked-eth",
                
                # Week 1 additions - Base native tokens
                # WBTC on Base
                "0x0555e30da8f98308edb960aa94c0db47230d2b9c": "wrapped-bitcoin",
                # DEGEN on Base
                "0x4ed4e862860bed51a9570b96d89af5e1b0efefed": "degen-base",
                # TOSHI on Base
                "0xac1bd2486aaf3b5c0fc3fd868558b082a531b2b4": "toshi",
                # BRETT on Base
                "0x532f27101965dd16442e59d40670faf5ebb142e4": "based-brett",
                # USDbC (Bridged USDC) on Base
                "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca": "bridged-usd-coin-base",
                "0x940181a94a35a4569e4529a3cdfb74e38fd98631": "aerodrome-finance",  # AERO
                "0x0b3e328455c4059eeb9e3f84b5543f74e24e7e1b": "virtual-protocol",   # VIRTUAL
                "0x58d97b57bb95320f9a05dc918aef65434969c2b2": "morpho-blue",        # MORPHO
            },
            # Ethereum mainnet (1)
            1: {
                "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "weth",
                "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "usd-coin",
                "0x6b175474e89094c44da98b954eedeac495271d0f": "dai",
                "0xbe9895146f7af43049ca1c1ae358b0541ea49704": "coinbase-wrapped-staked-eth",
            },
        }

        mapping = per_chain.get(chain_id, {})
        if addr in mapping:
            return mapping[addr]

        # --- Conservative symbol fallback (only unambiguous for our set) ---
        symbol_fallback: Dict[str, str] = {
            "WETH": "weth",
            "USDC": "usd-coin",
            "DAI": "dai",
            "CBETH": "coinbase-wrapped-staked-eth",
            
            # Week 1 additions
            "WBTC": "wrapped-bitcoin",
            "DEGEN": "degen-base",
            "TOSHI": "toshi",
            "BRETT": "based-brett",
            "USDBC": "bridged-usd-coin-base",
        }
        if sym in symbol_fallback:
            return symbol_fallback[sym]

        # Unknown → let caller decide (e.g., skip and log once)
        return None

    async def _get_or_create_session(self) -> aiohttp.ClientSession:
        """
        Get or create aiohttp session (lazy initialization).
        
        This prevents memory leaks by reusing the same session across requests.
        
        Returns:
            Active aiohttp ClientSession
        """
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout)
            logger.debug("[PRICE FEED] Created new aiohttp session")
        return self._session

    async def close(self) -> None:
        """
        Close aiohttp session and cleanup resources.
        
        Should be called when service is no longer needed to prevent resource leaks.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("[PRICE FEED] Closed aiohttp session")

    # =========================================================================
    # PUBLIC API METHODS
    # =========================================================================

    async def get_token_price(
        self,
        token_address: str,
        token_symbol: str
    ) -> Optional[Decimal]:
        """
        Get current price for a single token with caching.
        
        This method checks cache first, then falls back to API if needed.
        For multiple tokens, use get_bulk_token_prices() instead for better performance.
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol (e.g., 'WETH', 'USDC')
            
        Returns:
            Token price in USD as Decimal, or None if unavailable
            
        Example:
            >>> price = await service.get_token_price(
            ...     "0x4200000000000000000000000000000000000006",
            ...     "WETH"
            ... )
            >>> print(f"${price:.2f}")
            $2543.50
        """
        # Check if it's a stablecoin (instant return)
        if token_symbol.upper() in STABLECOINS:
            logger.debug(f"[PRICE FEED] {token_symbol} is stablecoin, returning $1.00")
            return STABLECOINS[token_symbol.upper()]
        
        # Try fresh cache first
        cached_price = self._get_cached_price(token_address)
        if cached_price is not None:
            return cached_price
        
        # Cache miss - fetch from API
        logger.debug(
            f"[PRICE FEED] Cache miss for {token_symbol}, fetching from API"
        )
        
        try:
            price = await self._fetch_from_coingecko(token_symbol, token_address)
            
            if price is not None:
                # Cache the new price
                self._cache_price(token_address, price)
                self.api_call_count += 1
                return price
            else:
                # API failed - try stale cache as fallback
                stale_price = self._get_stale_cached_price(token_address)
                if stale_price is not None:
                    logger.info(
                        f"[PRICE FEED] Using stale cache for {token_symbol} "
                        f"(API unavailable)"
                    )
                    return stale_price
                
                logger.warning(
                    f"[PRICE FEED] No price available for {token_symbol} "
                    f"(API failed, no cache)"
                )
                return None
                
        except Exception as e:
            logger.error(
                f"[PRICE FEED] Error fetching price for {token_symbol}: {e}",
                exc_info=True
            )
            
            # Try stale cache on error
            stale_price = self._get_stale_cached_price(token_address)
            if stale_price is not None:
                logger.info(
                    f"[PRICE FEED] Using stale cache for {token_symbol} (error recovery)"
                )
                return stale_price
            
            return None

    async def get_bulk_token_prices(
        self,
        tokens: List[Tuple[str, str]]
    ) -> Dict[str, Optional[Decimal]]:
        """
        Get prices for multiple tokens in a single API call (RECOMMENDED).
        
        This is the OPTIMIZED way to fetch prices - uses 1 API call instead of N.
        
        Args:
            tokens: List of (symbol, address) tuples
            
        Returns:
            Dictionary mapping symbols to prices (or None if unavailable)
            
        Example:
            >>> prices = await service.get_bulk_token_prices([
            ...     ('WETH', '0x4200...'),
            ...     ('USDC', '0x036C...'),
            ...     ('DAI', '0x50c5...')
            ... ])
            >>> prices
            {'WETH': Decimal('2543.50'), 'USDC': Decimal('1.00'), 'DAI': Decimal('1.00')}
        """
        if not tokens:
            logger.warning("[PRICE FEED] get_bulk_token_prices called with empty list")
            return {}
        
        logger.info(
            f"[PRICE FEED] Fetching bulk prices for {len(tokens)} tokens: "
            f"{', '.join(sym for sym, _ in tokens)}"
        )
        
        results: Dict[str, Optional[Decimal]] = {}
        tokens_to_fetch: List[Tuple[str, str]] = []
        
        # Step 1: Check cache for each token
        for symbol, address in tokens:
            # Stablecoins always return $1.00
            if symbol.upper() in STABLECOINS:
                results[symbol] = STABLECOINS[symbol.upper()]
                logger.debug(f"[PRICE FEED] {symbol} is stablecoin")
                continue
            
            # Check fresh cache
            cached_price = self._get_cached_price(address)
            if cached_price is not None:
                results[symbol] = cached_price
                logger.debug(f"[PRICE FEED] Cache hit for {symbol}")
            else:
                # Need to fetch this token
                tokens_to_fetch.append((symbol, address))
        
        # Step 2: Fetch uncached tokens in bulk (1 API call)
        if tokens_to_fetch:
            logger.info(
                f"[PRICE FEED] Need to fetch {len(tokens_to_fetch)} tokens from API: "
                f"{', '.join(sym for sym, _ in tokens_to_fetch)}"
            )
            
            try:
                fetched_prices = await self._fetch_bulk_from_coingecko(tokens_to_fetch)
                self.bulk_api_calls += 1
                
                # Cache and add fetched prices to results
                for symbol, price in fetched_prices.items():
                    if price is not None:
                        # Find address for this symbol
                        address = next(
                            (addr for sym, addr in tokens_to_fetch if sym == symbol),
                            None
                        )
                        if address:
                            self._cache_price(address, price)
                        results[symbol] = price
                    else:
                        # Try stale cache as fallback
                        address = next(
                            (addr for sym, addr in tokens_to_fetch if sym == symbol),
                            None
                        )
                        if address:
                            stale_price = self._get_stale_cached_price(address)
                            results[symbol] = stale_price
                        else:
                            results[symbol] = None
                            
            except Exception as e:
                logger.error(
                    f"[PRICE FEED] Bulk fetch failed: {e}",
                    exc_info=True
                )
                
                # Fallback to stale cache for failed tokens
                for symbol, address in tokens_to_fetch:
                    if symbol not in results:
                        stale_price = self._get_stale_cached_price(address)
                        results[symbol] = stale_price
        
        # Log summary
        successful = sum(1 for p in results.values() if p is not None)
        logger.info(
            f"[PRICE FEED] Bulk fetch complete: {successful}/{len(tokens)} prices retrieved"
        )
        
        return results

    # =========================================================================
    # COINGECKO API METHODS
    # =========================================================================

    async def _enforce_rate_limit(self) -> None:
        """
        Enforce rate limiting for CoinGecko API calls.
        
        Waits if necessary to respect the rate limit.
        """
        if self.last_coingecko_call is not None:
            elapsed = (datetime.now() - self.last_coingecko_call).total_seconds()
            
            if elapsed < self.coingecko_rate_limit_seconds:
                wait_time = self.coingecko_rate_limit_seconds - elapsed
                logger.debug(f"[RATE LIMIT] Waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
        
        self.last_coingecko_call = datetime.now()

    async def _fetch_from_coingecko(
        self,        
        token_symbol: str,
        token_address: str
    ) -> Optional[Decimal]:
        """
        Fetch single token price from CoinGecko API.
        
        Args:
            token_symbol: Token symbol
            token_address: Token contract address
            
        Returns:
            Price in USD or None if unavailable
        """
        try:
            await self._enforce_rate_limit()
            
            # Get CoinGecko ID for this token
            coin_id = self._get_coingecko_id(token_symbol, token_address, self.chain_id)  # ✅ All 3 params
            if not coin_id:
                logger.debug(f"[PRICE FEED] No CoinGecko ID for {token_symbol}")
                return None
            
            url = f"{self.coingecko_base_url}/simple/price"
            params = {
                'ids': coin_id,
                'vs_currencies': 'usd'
            }

            # Build headers with API key (Demo tier)
            headers: Dict[str, str] = {}
            if self.coingecko_api_key:
                headers['x-cg-demo-api-key'] = self.coingecko_api_key
                logger.debug(f"[PRICE FEED] Using CoinGecko API key for {token_symbol}")

            # Use reusable session to prevent memory leaks
            session = await self._get_or_create_session()
            async with session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if coin_id in data and 'usd' in data[coin_id]:
                        price_usd = Decimal(str(data[coin_id]['usd']))
                        logger.info(
                            f"[PRICE FEED] ✅ Fetched price for {token_symbol}: "
                            f"${price_usd:.2f}"
                        )
                        return price_usd
                elif response.status == 429:
                    logger.warning(
                        "[PRICE FEED] CoinGecko rate limit exceeded"
                    )
                    return None
                else:
                    logger.debug(
                        f"[PRICE FEED] CoinGecko API error: {response.status}"
                    )
                    return None
                        
        except asyncio.TimeoutError:
            logger.debug(f"[PRICE FEED] CoinGecko timeout for {token_symbol}")
            return None
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                logger.debug(
                    f"[PRICE FEED] Event loop closed for {token_symbol}, "
                    f"skipping CoinGecko"
                )
                return None
            raise
        except Exception as e:
            logger.error(
                f"[PRICE FEED] CoinGecko API error: {e}",
                exc_info=True
            )
            return None

    async def _fetch_bulk_from_coingecko(
        self,
        tokens: List[Tuple[str, str]]
    ) -> Dict[str, Optional[Decimal]]:
        """
        Fetch multiple token prices in a single CoinGecko API call.
        
        This is the KEY OPTIMIZATION that reduces API usage by 90%.
        
        Args:
            tokens: List of (symbol, address) tuples to fetch
            
        Returns:
            Dictionary mapping symbols to prices
        """
        if not tokens:
            return {}
        
        try:
            await self._enforce_rate_limit()
            
            # Build list of CoinGecko IDs
            coin_ids: List[str] = []
            symbol_to_coin_id: Dict[str, str] = {}
            
            for symbol, address in tokens:
                coin_id = self._get_coingecko_id(symbol, address, self.chain_id)
                if coin_id:
                    coin_ids.append(coin_id)
                    symbol_to_coin_id[coin_id] = symbol
            
            if not coin_ids:
                logger.warning("[PRICE FEED] No valid CoinGecko IDs in bulk request")
                return {symbol: None for symbol, _ in tokens}
            
            # Make single bulk API call
            url = f"{self.coingecko_base_url}/simple/price"
            params = {
                'ids': ','.join(coin_ids),
                'vs_currencies': 'usd'
            }
            
            headers: Dict[str, str] = {}
            if self.coingecko_api_key:
                headers['x-cg-demo-api-key'] = self.coingecko_api_key
            
            session = await self._get_or_create_session()
            async with session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    results: Dict[str, Optional[Decimal]] = {}
                    for coin_id, symbol in symbol_to_coin_id.items():
                        if coin_id in data and 'usd' in data[coin_id]:
                            price = Decimal(str(data[coin_id]['usd']))
                            results[symbol] = price
                            logger.debug(
                                f"[PRICE FEED] Bulk fetch: {symbol} = ${price:.2f}"
                            )
                        else:
                            results[symbol] = None
                    
                    logger.info(
                        f"[PRICE FEED] ✅ Bulk fetch succeeded: "
                        f"{len(results)}/{len(tokens)} prices"
                    )
                    return results
                    
                elif response.status == 429:
                    logger.warning("[PRICE FEED] CoinGecko rate limit in bulk fetch")
                    return {symbol: None for symbol, _ in tokens}
                else:
                    logger.warning(
                        f"[PRICE FEED] CoinGecko bulk fetch error: {response.status}"
                    )
                    return {symbol: None for symbol, _ in tokens}
                    
        except Exception as e:
            logger.error(
                f"[PRICE FEED] Bulk fetch exception: {e}",
                exc_info=True
            )
            return {symbol: None for symbol, _ in tokens}

    # =========================================================================
    # CACHING METHODS (ENHANCED WITH STALE-WHILE-REVALIDATE)
    # =========================================================================
    def _get_cached_price(self, token_address: str) -> Optional[Decimal]:
        """
        Get cached price from Redis with fresh/stale distinction.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Cached price or None if not in fresh cache
        """
        try:
            # Try fresh cache first
            cache_key = f"{PRICE_CACHE_PREFIX}:{self.chain_id}:{token_address.lower()}"
            cached_value = cache.get(cache_key)

            if cached_value is not None:
                self.cache_hits += 1
                logger.debug(
                    f"[CACHE HIT] Fresh price for {token_address[:10]}: "
                    f"${cached_value:.2f}"
                )
                return Decimal(str(cached_value))
            
            # Fresh cache miss
            self.cache_misses += 1
            return None
            
        except Exception as e:
            logger.warning(f"[PRICE FEED] Cache retrieval error: {e}")
            return None
    
    def _get_stale_cached_price(self, token_address: str) -> Optional[Decimal]:
        """
        Get stale cached price as fallback when API fails.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Stale cached price or None if not available
        """
        try:
            stale_key = f"{STALE_CACHE_PREFIX}:{self.chain_id}:{token_address.lower()}"
            stale_value = cache.get(stale_key)
            
            if stale_value is not None:
                self.stale_cache_hits += 1
                logger.info(
                    f"[STALE CACHE] Using stale price for {token_address[:10]}: "
                    f"${stale_value:.2f} (API unavailable)"
                )
                return Decimal(str(stale_value))
            
            return None
            
        except Exception as e:
            logger.warning(f"[PRICE FEED] Stale cache retrieval error: {e}")
            return None
    
    def _cache_price(self, token_address: str, price: Decimal) -> None:
        """
        Cache price in Redis with both fresh and stale TTLs.
        
        Args:
            token_address: Token contract address
            price: Price to cache
        """
        try:
            # Store in fresh cache
            fresh_key = f"{PRICE_CACHE_PREFIX}:{self.chain_id}:{token_address.lower()}"
            cache.set(fresh_key, float(price), timeout=PRICE_CACHE_TTL)
            
            # Also store in stale cache with longer TTL
            stale_key = f"{STALE_CACHE_PREFIX}:{self.chain_id}:{token_address.lower()}"
            cache.set(stale_key, float(price), timeout=STALE_CACHE_TTL)
            
            logger.debug(
                f"[CACHE SET] Cached price for {token_address[:10]}: "
                f"${price:.2f} (Fresh: {PRICE_CACHE_TTL}s, Stale: {STALE_CACHE_TTL}s)"
            )
            
        except Exception as e:
            logger.warning(f"[PRICE FEED] Cache storage error: {e}")
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """
        Get cache performance statistics.
        
        Returns:
            Dictionary containing cache metrics and performance data
        """
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'stale_cache_hits': self.stale_cache_hits,
            'total_requests': total_requests,
            'hit_rate_percent': round(hit_rate, 2),
            'api_calls': self.api_call_count,
            'bulk_api_calls': self.bulk_api_calls,
            'cache_ttl_seconds': PRICE_CACHE_TTL,
            'stale_ttl_seconds': STALE_CACHE_TTL,
            'api_call_reduction': f"{100 - (self.api_call_count / max(total_requests, 1) * 100):.1f}%"
        }


# =============================================================================
# HELPER FUNCTIONS (for easy usage)
# =============================================================================

# Global instance (singleton pattern)
_default_price_feed_service: Optional[PriceFeedService] = None


def get_default_price_feed_service() -> PriceFeedService:
    """
    Get or create the default price feed service instance.
    
    Returns:
        Singleton PriceFeedService instance
    """
    global _default_price_feed_service
    
    if _default_price_feed_service is None:
        chain_id = getattr(settings, 'DEFAULT_CHAIN_ID', 84532)
        _default_price_feed_service = PriceFeedService(chain_id=chain_id)
        logger.info(
            f"[PRICE FEED] Created OPTIMIZED default service for chain {chain_id}"
        )
    
    return _default_price_feed_service


async def get_bulk_token_prices_simple(
    tokens: List[Tuple[str, str]],
    chain_id: int = 84532
) -> Dict[str, Optional[Decimal]]:
    """
    Simple helper function to fetch multiple token prices quickly.
    
    This is the RECOMMENDED way to fetch prices for paper trading.
    
    Args:
        tokens: List of (symbol, address) tuples
        chain_id: Blockchain network ID (default: Base Sepolia)
    
    Returns:
        Dictionary mapping symbols to prices
    
    Example:
        prices = await get_bulk_token_prices_simple([
            ("WETH", "0x4200000000000000000000000000000000000006"),
            ("USDC", "0x036CbD53842c5426634e7929541eC2318f3dCF7e"),
            ("DAI", "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb")
        ])
        # Returns: {'WETH': Decimal('2543.50'), 'USDC': Decimal('1.00'), ...}
    """
    service = PriceFeedService(chain_id=chain_id)
    try:
        prices = await service.get_bulk_token_prices(tokens)
        return prices
    finally:
        await service.close()