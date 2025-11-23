"""
DEX Integration Base Classes

This module provides the foundation for all DEX integrations:
- DEXPrice: Standard price data structure returned by all DEXs
- BaseDEX: Abstract base class that all DEX implementations must inherit from

All DEX adapters (Uniswap, SushiSwap, Curve) inherit from BaseDEX and return DEXPrice objects.

File: dexproject/paper_trading/intelligence/dex_integrations/base.py
"""

import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from django.utils import timezone
from django.core.cache import cache

# Import Web3 and blockchain interaction tools
from engine.web3_client import Web3Client
from engine.config import get_config

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class DEXPrice:
    """
    Standard price data structure returned by all DEX integrations.
    
    This is the common format that all DEX adapters must return, ensuring
    consistency across different DEXs (Uniswap, SushiSwap, Curve, etc.).
    
    Attributes:
        dex_name: Name of the DEX (e.g., 'uniswap_v3', 'sushiswap')
        token_address: Token contract address
        token_symbol: Token symbol (e.g., 'WETH')
        price_usd: Price in USD
        liquidity_usd: Available liquidity in USD
        pool_address: Pool/pair contract address
        timestamp: When price was fetched
        success: Whether price fetch was successful
        error_message: Error message if failed
        query_time_ms: Time taken to fetch price (milliseconds)
        data_source: Source of price data ('on_chain', 'api', 'cache')
    """
    dex_name: str
    token_address: str
    token_symbol: str
    price_usd: Optional[Decimal] = None
    liquidity_usd: Optional[Decimal] = None
    pool_address: Optional[str] = None
    timestamp: datetime = field(default_factory=timezone.now)
    success: bool = False
    error_message: Optional[str] = None
    query_time_ms: float = 0.0
    data_source: str = "on_chain"
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.
        
        Returns:
            Dictionary representation of DEXPrice
        """
        return {
            'dex_name': self.dex_name,
            'token_address': self.token_address,
            'token_symbol': self.token_symbol,
            'price_usd': float(self.price_usd) if self.price_usd else None,
            'liquidity_usd': float(self.liquidity_usd) if self.liquidity_usd else None,
            'pool_address': self.pool_address,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'success': self.success,
            'error_message': self.error_message,
            'query_time_ms': self.query_time_ms,
            'data_source': self.data_source
        }


# =============================================================================
# BASE DEX CLASS
# =============================================================================

class BaseDEX(ABC):
    """
    Abstract base class for DEX integrations.
    
    All DEX implementations (Uniswap, SushiSwap, Curve) must inherit from this
    class and implement the get_token_price method.
    
    This base class provides:
    - Web3 client initialization and management
    - Price caching with TTL
    - Performance tracking
    - Common configuration
    
    Attributes:
        dex_name: Unique identifier for this DEX
        chain_id: Blockchain network ID
        web3_client: Web3 client for blockchain queries
        cache_ttl_seconds: Time-to-live for cached prices
        logger: Logger instance
        
    Subclass Requirements:
        - Must implement get_token_price() method
        - Should call _cache_price() after successful price fetch
        - Should increment performance counters (total_queries, successful_queries, etc.)
    """
    
    def __init__(
        self,
        dex_name: str,
        chain_id: int = 8453,
        cache_ttl_seconds: int = 60
    ):
        """
        Initialize base DEX integration.
        
        Args:
            dex_name: Unique identifier for this DEX (e.g., 'uniswap_v3')
            chain_id: Blockchain network ID (default: 8453 = Base Mainnet)
            cache_ttl_seconds: Cache TTL for price data (default: 60 seconds)
        """
        self.dex_name = dex_name
        self.chain_id = chain_id
        self.cache_ttl_seconds = cache_ttl_seconds
        self.logger = logging.getLogger(f'{__name__}.{dex_name.upper()}')
        
        # Initialize Web3 client
        self.web3_client: Optional[Web3Client] = None
        self._initialize_web3()
        
        # Performance tracking
        self.total_queries = 0
        self.successful_queries = 0
        self.cache_hits = 0
        self.total_query_time_ms = 0.0
        
        self.logger.info(
            f"[{self.dex_name.upper()}] Initialized for chain {chain_id}"
        )
    
    def _initialize_web3(self) -> None:
        """
        Initialize Web3 client for blockchain queries.
        
        This method attempts to create a Web3Client using the engine's config.
        If initialization fails, web3_client will be None and queries will fail.
        
        Note: get_config() is an async function that takes NO arguments and 
        initializes a global config object in the engine.config module.
        """
        try:
            # Import async_to_sync for calling async function
            from asgiref.sync import async_to_sync
            
            # Import engine config module to access global config
            import engine.config as engine_config_module
            
            # Check if config is already initialized
            if not hasattr(engine_config_module, 'config') or engine_config_module.config is None:
                # Initialize config asynchronously (takes no args)
                async_to_sync(get_config)()
            
            # Access the initialized config from the module
            # Access the initialized config from the module
            if hasattr(engine_config_module, 'config') and engine_config_module.config is not None:
                engine_config = engine_config_module.config  # This is EngineConfig
                
                # ✅ GET CHAIN-SPECIFIC CONFIG
                chain_config = engine_config.get_chain_config(self.chain_id)
                
                if chain_config is None:
                    self.logger.warning(
                        f"[{self.dex_name.upper()}] No chain config found for chain {self.chain_id}"
                    )
                    self.web3_client = None
                    return
            else:
                self.logger.warning(
                    f"[{self.dex_name.upper()}] Engine config not available - "
                    f"Web3 client will not be initialized"
                )
                self.web3_client = None
                return
            
            # Create Web3 client using the config
            self.web3_client = Web3Client(chain_config)
            
            # ✅ CRITICAL: Connect the Web3 client to the blockchain
            async_to_sync(self.web3_client.connect)()
            
            self.logger.info(
                f"[{self.dex_name.upper()}] Web3 client initialized for chain {self.chain_id}"
            )
        
        except Exception as e:
            self.logger.error(
                f"[{self.dex_name.upper()}] Failed to initialize Web3 client: {e}",
                exc_info=True
            )
            self.web3_client = None
    
    @abstractmethod
    async def get_token_price(
        self,
        token_address: str,
        token_symbol: str
    ) -> DEXPrice:
        """
        Get token price from this DEX.
        
        This is the main method that all DEX subclasses must implement.
        It should:
        1. Check cache first (using _get_cached_price)
        2. Query the DEX for price and liquidity
        3. Create and return a DEXPrice object
        4. Cache the result (using _cache_price)
        5. Update performance counters
        
        Args:
            token_address: Token contract address (checksummed)
            token_symbol: Token symbol (e.g., 'WETH')
            
        Returns:
            DEXPrice object with price and liquidity data
            
        Example Implementation:
            ```python
            async def get_token_price(self, token_address: str, token_symbol: str) -> DEXPrice:
                # Check cache
                cached = self._get_cached_price(token_address)
                if cached:
                    return cached
                
                # Query DEX
                price_usd, liquidity_usd = await self._query_dex(token_address)
                
                # Create result
                result = DEXPrice(
                    dex_name=self.dex_name,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    price_usd=price_usd,
                    liquidity_usd=liquidity_usd,
                    success=True
                )
                
                # Cache and return
                self._cache_price(token_address, result)
                return result
            ```
        """
        pass
    
    # =========================================================================
    # CACHING METHODS
    # =========================================================================
    
    def _get_cache_key(self, token_address: str) -> str:
        """
        Generate cache key for token price.
        
        Cache keys are namespaced by DEX name and chain ID to prevent collisions.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Cache key string
        """
        return f"{self.dex_name}:price:{self.chain_id}:{token_address.lower()}"
    
    def _get_cached_price(self, token_address: str) -> Optional[DEXPrice]:
        """
        Get cached price if available and fresh.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Cached DEXPrice object, or None if not cached or expired
        """
        cache_key = self._get_cache_key(token_address)
        cached = cache.get(cache_key)
        
        if cached:
            self.cache_hits += 1
            self.logger.debug(
                f"[{self.dex_name.upper()}] Cache hit for {token_address[:10]}..."
            )
        
        return cached
    
    def _cache_price(self, token_address: str, price: DEXPrice) -> None:
        """
        Cache token price.
        
        Only caches successful price fetches with valid price data.
        
        Args:
            token_address: Token contract address
            price: DEXPrice object to cache
        """
        if price.success and price.price_usd:
            cache_key = self._get_cache_key(token_address)
            cache.set(cache_key, price, self.cache_ttl_seconds)
    
    # =========================================================================
    # PERFORMANCE TRACKING
    # =========================================================================
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get performance statistics for this DEX.
        
        Returns:
            Dictionary with performance metrics:
            - dex_name: Name of the DEX
            - chain_id: Chain ID
            - total_queries: Total number of queries
            - successful_queries: Number of successful queries
            - success_rate_percent: Success rate percentage
            - cache_hits: Number of cache hits
            - cache_hit_rate_percent: Cache hit rate percentage
            - avg_query_time_ms: Average query time in milliseconds
        """
        success_rate = (
            (self.successful_queries / max(self.total_queries, 1)) * 100
            if self.total_queries > 0
            else 0
        )
        
        cache_hit_rate = (
            (self.cache_hits / max(self.total_queries, 1)) * 100
            if self.total_queries > 0
            else 0
        )
        
        avg_query_time = (
            self.total_query_time_ms / max(self.successful_queries, 1)
            if self.successful_queries > 0
            else 0
        )
        
        return {
            'dex_name': self.dex_name,
            'chain_id': self.chain_id,
            'total_queries': self.total_queries,
            'successful_queries': self.successful_queries,
            'success_rate_percent': round(success_rate, 2),
            'cache_hits': self.cache_hits,
            'cache_hit_rate_percent': round(cache_hit_rate, 2),
            'avg_query_time_ms': round(avg_query_time, 2)
        }
    
    # =========================================================================
    # CLEANUP
    # =========================================================================
    
    async def cleanup(self) -> None:
        """
        Clean up resources (Web3 client, connections, etc.).
        
        Should be called when the DEX integration is no longer needed.
        """
        try:
            if self.web3_client:
                # Web3Client cleanup if needed
                self.logger.info(
                    f"[{self.dex_name.upper()}] Cleaning up Web3 client"
                )
            
            self.logger.info(f"[{self.dex_name.upper()}] Cleanup complete")
        
        except Exception as e:
            self.logger.error(
                f"[{self.dex_name.upper()}] Error during cleanup: {e}",
                exc_info=True
            )