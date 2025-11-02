"""
Base DEX Interface for Multi-DEX Price Comparison

This module provides the abstract base class that all DEX integrations must implement.
It defines the common interface for price queries, liquidity checks, and error handling.

Phase 2: Multi-DEX Price Comparison
File: paper_trading/intelligence/dex_integrations/base_dex.py
"""

import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from django.utils import timezone
from django.core.cache import cache

# Import existing infrastructure
from paper_trading.intelligence.analyzers.constants import (
    ENGINE_CONFIG_MODULE_AVAILABLE,
    engine_config_module,
    get_config,
    Web3Client
)

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class DEXPrice:
    """
    Price quote from a specific DEX.
    
    Attributes:
        dex_name: Name of the DEX
        token_address: Token contract address
        token_symbol: Token symbol
        price_usd: Price in USD
        liquidity_usd: Available liquidity in USD
        timestamp: When quote was obtained
        success: Whether query was successful
        error_message: Error message if failed
        response_time_ms: Query response time
    """
    dex_name: str
    token_address: str
    token_symbol: str
    price_usd: Optional[Decimal] = None
    liquidity_usd: Optional[Decimal] = None
    timestamp: datetime = None
    success: bool = False
    error_message: Optional[str] = None
    response_time_ms: float = 0.0
    
    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = timezone.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'dex_name': self.dex_name,
            'token_address': self.token_address,
            'token_symbol': self.token_symbol,
            'price_usd': float(self.price_usd) if self.price_usd else None,
            'liquidity_usd': float(self.liquidity_usd) if self.liquidity_usd else None,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'success': self.success,
            'error_message': self.error_message,
            'response_time_ms': self.response_time_ms
        }


# =============================================================================
# BASE DEX CLASS
# =============================================================================

class BaseDEX(ABC):
    """
    Abstract base class for all DEX integrations.
    
    All DEX implementations must inherit from this class and implement:
    - get_token_price(): Fetch current token price
    - get_liquidity(): Query available liquidity
    - is_available(): Check if DEX is operational
    
    The base class provides:
    - Web3 client initialization
    - Caching infrastructure
    - Error handling utilities
    - Performance tracking
    """
    
    def __init__(
        self,
        dex_name: str,
        chain_id: int = 84532,
        cache_ttl_seconds: int = 30
    ):
        """
        Initialize base DEX integration.
        
        Args:
            dex_name: Name of the DEX (e.g., 'uniswap_v3')
            chain_id: Blockchain network ID
            cache_ttl_seconds: Cache time-to-live in seconds
        """
        self.dex_name = dex_name
        self.chain_id = chain_id
        self.cache_ttl = cache_ttl_seconds
        
        # Web3 infrastructure
        self._web3_client: Optional[Any] = None
        self._web3_initialized = False
        
        # Performance tracking
        self.total_queries = 0
        self.successful_queries = 0
        self.failed_queries = 0
        self.total_response_time_ms = 0.0
        
        # Circuit breaker for repeated failures
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5
        self.is_disabled = False
        self.disabled_until: Optional[datetime] = None
        
        self.logger = logging.getLogger(f'{__name__}.{self.dex_name}')
        
        self.logger.info(
            f"[{self.dex_name.upper()}] Initialized for chain {chain_id}"
        )
    
    # =========================================================================
    # ABSTRACT METHODS (Must be implemented by subclasses)
    # =========================================================================
    
    @abstractmethod
    async def get_token_price(
        self,
        token_address: str,
        token_symbol: str
    ) -> DEXPrice:
        """
        Get current token price from this DEX.
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            
        Returns:
            DEXPrice object with price and metadata
        """
        pass
    
    @abstractmethod
    async def get_liquidity(
        self,
        token_address: str
    ) -> Optional[Decimal]:
        """
        Get available liquidity for token on this DEX.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Liquidity in USD, or None if unavailable
        """
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if DEX is currently operational.
        
        Returns:
            True if DEX can handle queries, False otherwise
        """
        pass
    
    # =========================================================================
    # WEB3 INFRASTRUCTURE
    # =========================================================================
    
    async def _ensure_web3_client(self) -> Optional[Any]:
        """
        Ensure Web3 client is initialized (lazy initialization).
        
        Returns:
            Web3Client instance or None if unavailable
        """
        # Check if engine config module is available
        if not ENGINE_CONFIG_MODULE_AVAILABLE:
            self.logger.warning(
                f"[{self.dex_name.upper()}] Web3 infrastructure not available"
            )
            return None
        
        # Return cached client if already initialized
        if self._web3_initialized and self._web3_client:
            return self._web3_client
        
        try:
            # Lazy initialization of engine config
            if engine_config_module is None:
                self.logger.error(f"[{self.dex_name.upper()}] Engine config module is None")
                return None
            
            # Get config instance
            engine_config = getattr(engine_config_module, 'config', None)
            
            # Initialize config if needed
            if engine_config is None and get_config is not None:
                self.logger.info(f"[{self.dex_name.upper()}] Initializing engine config...")
                await get_config()
                engine_config = getattr(engine_config_module, 'config', None)
            
            if engine_config is None:
                self.logger.error(f"[{self.dex_name.upper()}] Failed to initialize engine config")
                return None
            
            # Get chain configuration
            chain_config = engine_config.get_chain_config(self.chain_id)
            if not chain_config:
                self.logger.warning(
                    f"[{self.dex_name.upper()}] No configuration for chain {self.chain_id}"
                )
                return None
            
            # Check if Web3Client is available
            if Web3Client is None:
                self.logger.error(f"[{self.dex_name.upper()}] Web3Client class not available")
                return None
            
            # Initialize Web3 client
            self._web3_client = Web3Client(chain_config)
            await self._web3_client.connect()
            
            # Verify connection
            if not self._web3_client.is_connected:
                self.logger.error(f"[{self.dex_name.upper()}] Failed to connect to chain {self.chain_id}")
                return None
            
            self._web3_initialized = True
            self.logger.info(f"[{self.dex_name.upper()}] Web3 client connected")
            return self._web3_client
        
        except Exception as e:
            self.logger.error(
                f"[{self.dex_name.upper()}] Error initializing Web3 client: {e}",
                exc_info=True
            )
            return None
    
    # =========================================================================
    # CACHING UTILITIES
    # =========================================================================
    
    def _get_cache_key(self, prefix: str, identifier: str) -> str:
        """
        Generate cache key for this DEX.
        
        Args:
            prefix: Cache key prefix (e.g., 'price', 'liquidity')
            identifier: Unique identifier (e.g., token address)
            
        Returns:
            Cache key string
        """
        return f"dex:{self.dex_name}:{self.chain_id}:{prefix}:{identifier}"
    
    def _get_cached_price(self, token_address: str) -> Optional[DEXPrice]:
        """
        Get cached price for token.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Cached DEXPrice or None if not in cache
        """
        cache_key = self._get_cache_key('price', token_address)
        return cache.get(cache_key)
    
    def _cache_price(self, price: DEXPrice) -> None:
        """
        Cache price quote.
        
        Args:
            price: DEXPrice object to cache
        """
        cache_key = self._get_cache_key('price', price.token_address)
        cache.set(cache_key, price, self.cache_ttl)
    
    # =========================================================================
    # CIRCUIT BREAKER
    # =========================================================================
    
    def _record_success(self) -> None:
        """Record successful query and reset circuit breaker."""
        self.successful_queries += 1
        self.consecutive_failures = 0
        
        # Re-enable if was disabled
        if self.is_disabled:
            self.is_disabled = False
            self.disabled_until = None
            self.logger.info(f"[{self.dex_name.upper()}] Re-enabled after successful query")
    
    def _record_failure(self) -> None:
        """Record failed query and check circuit breaker."""
        self.failed_queries += 1
        self.consecutive_failures += 1
        
        # Check if should disable
        if self.consecutive_failures >= self.max_consecutive_failures:
            self.is_disabled = True
            self.disabled_until = timezone.now() + timedelta(minutes=5)
            self.logger.warning(
                f"[{self.dex_name.upper()}] Disabled due to {self.consecutive_failures} "
                f"consecutive failures. Will re-enable after {self.disabled_until}"
            )
    
    def _check_if_disabled(self) -> bool:
        """
        Check if DEX is currently disabled by circuit breaker.
        
        Returns:
            True if disabled, False if operational
        """
        if not self.is_disabled:
            return False
        
        # Check if cooldown period has passed
        if self.disabled_until and timezone.now() >= self.disabled_until:
            self.is_disabled = False
            self.disabled_until = None
            self.consecutive_failures = 0
            self.logger.info(f"[{self.dex_name.upper()}] Cooldown period expired, re-enabling")
            return False
        
        return True
    
    # =========================================================================
    # PERFORMANCE METRICS
    # =========================================================================
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get performance statistics for this DEX.
        
        Returns:
            Dictionary with performance metrics
        """
        success_rate = (
            (self.successful_queries / max(self.total_queries, 1)) * 100
            if self.total_queries > 0
            else 0
        )
        
        avg_response_time = (
            self.total_response_time_ms / max(self.successful_queries, 1)
            if self.successful_queries > 0
            else 0
        )
        
        return {
            'dex_name': self.dex_name,
            'chain_id': self.chain_id,
            'total_queries': self.total_queries,
            'successful_queries': self.successful_queries,
            'failed_queries': self.failed_queries,
            'success_rate_percent': round(success_rate, 2),
            'average_response_time_ms': round(avg_response_time, 2),
            'consecutive_failures': self.consecutive_failures,
            'is_disabled': self.is_disabled,
            'disabled_until': self.disabled_until.isoformat() if self.disabled_until else None
        }
    
    # =========================================================================
    # CLEANUP
    # =========================================================================
    
    async def cleanup(self) -> None:
        """Clean up resources (Web3 connections, etc.)."""
        try:
            if self._web3_client and self._web3_initialized:
                # Web3Client cleanup if available
                if hasattr(self._web3_client, 'disconnect'):
                    await self._web3_client.disconnect()
            
            self.logger.info(f"[{self.dex_name.upper()}] Cleanup complete")
        
        except Exception as e:
            self.logger.error(
                f"[{self.dex_name.upper()}] Cleanup error: {e}",
                exc_info=True
            )