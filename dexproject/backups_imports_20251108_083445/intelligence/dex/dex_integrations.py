"""
DEX Integrations - Base Classes and Implementations

This module provides the foundation for multi-DEX price comparison by defining:
- BaseDEX: Abstract base class for DEX integrations
- DEXPrice: Standard price data structure
- UniswapV3DEX: Uniswap V3 price fetching
- SushiSwapDEX: SushiSwap price fetching
- CurveDEX: Curve Finance price fetching

Phase 2: Multi-DEX Price Comparison
File: paper_trading/intelligence/dex_integrations.py
"""

import logging
import asyncio
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime

from django.utils import timezone
from django.core.cache import cache

# Import Web3 and blockchain interaction tools
from engine.web3_client import Web3Client
from engine.config import get_config

# Import Uniswap constants from analyzers
from paper_trading.intelligence.dex_integrations.constants import (
    UNISWAP_V3_FACTORY,
    FEE_TIERS,
    FACTORY_ABI,
    POOL_ABI
)

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class DEXPrice:
    """
    Standard price data structure returned by all DEX integrations.
    
    Attributes:
        dex_name: Name of the DEX (e.g., 'uniswap_v3')
        token_address: Token contract address
        token_symbol: Token symbol
        price_usd: Price in USD
        liquidity_usd: Available liquidity in USD
        pool_address: Pool/pair contract address
        timestamp: When price was fetched
        success: Whether price fetch was successful
        error_message: Error message if failed
        query_time_ms: Time taken to fetch price
        data_source: Source of price data
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
        """Convert to dictionary for serialization."""
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
    
    All DEX implementations must inherit from this class and implement
    the get_token_price method.
    
    Attributes:
        dex_name: Unique identifier for this DEX
        chain_id: Blockchain network ID
        web3_client: Web3 client for blockchain queries
        cache_ttl_seconds: Time-to-live for cached prices
        logger: Logger instance
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
            dex_name: Unique identifier for this DEX
            chain_id: Blockchain network ID
            cache_ttl_seconds: Cache TTL for price data
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
        """Initialize Web3 client for blockchain queries."""
        try:
            # Get chain config
            config = get_config(self.chain_id)
            
            # Create Web3 client
            self.web3_client = Web3Client(config)
            
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
        
        This method must be implemented by all DEX subclasses.
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            
        Returns:
            DEXPrice object with price and liquidity data
        """
        pass
    
    def _get_cache_key(self, token_address: str) -> str:
        """Generate cache key for token price."""
        return f"{self.dex_name}:price:{self.chain_id}:{token_address.lower()}"
    
    def _get_cached_price(self, token_address: str) -> Optional[DEXPrice]:
        """Get cached price if available and fresh."""
        cache_key = self._get_cache_key(token_address)
        cached = cache.get(cache_key)
        
        if cached:
            self.cache_hits += 1
            self.logger.debug(
                f"[{self.dex_name.upper()}] Cache hit for {token_address[:10]}..."
            )
        
        return cached
    
    def _cache_price(self, token_address: str, price: DEXPrice) -> None:
        """Cache token price."""
        if price.success and price.price_usd:
            cache_key = self._get_cache_key(token_address)
            cache.set(cache_key, price, self.cache_ttl_seconds)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for this DEX."""
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
    
    async def cleanup(self) -> None:
        """Cleanup resources."""
        try:
            if self.web3_client:
                # Close any open connections
                pass
            
            self.logger.info(f"[{self.dex_name.upper()}] Cleanup complete")
        
        except Exception as e:
            self.logger.error(
                f"[{self.dex_name.upper()}] Cleanup error: {e}",
                exc_info=True
            )


# =============================================================================
# UNISWAP V3 IMPLEMENTATION
# =============================================================================

class UniswapV3DEX(BaseDEX):
    """
    Uniswap V3 price fetching implementation.
    
    Features:
    - Multi-tier fee pool checking (0.05%, 0.3%, 1%)
    - Real on-chain liquidity data
    - Price calculation from pool reserves
    - Automatic best pool selection
    
    Usage:
        dex = UniswapV3DEX(chain_id=8453)
        price = await dex.get_token_price(
            token_address='0x...',
            token_symbol='WETH'
        )
    """
    
    def __init__(
        self,
        chain_id: int = 8453,
        cache_ttl_seconds: int = 60
    ):
        """
        Initialize Uniswap V3 integration.
        
        Args:
            chain_id: Blockchain network ID
            cache_ttl_seconds: Cache TTL for price data
        """
        super().__init__(
            dex_name="uniswap_v3",
            chain_id=chain_id,
            cache_ttl_seconds=cache_ttl_seconds
        )
        
        # Get factory address for this chain
        self.factory_address = UNISWAP_V3_FACTORY.get(chain_id)
        
        if not self.factory_address:
            self.logger.warning(
                f"[UNISWAP V3] No factory address configured for chain {chain_id}"
            )
        
        # Base tokens for pairing (WETH, USDC, etc.)
        self.base_tokens = self._get_base_tokens()
    
    def _get_base_tokens(self) -> List[str]:
        """Get base tokens for this chain."""
        # Get base tokens from chain config
        if self.web3_client and self.web3_client.chain_config:
            return [
                self.web3_client.chain_config.weth_address,
                self.web3_client.chain_config.usdc_address
            ]
        return []
    
    async def get_token_price(
        self,
        token_address: str,
        token_symbol: str
    ) -> DEXPrice:
        """
        Get token price from Uniswap V3.
        
        Process:
        1. Check cache
        2. Find best pool (check all fee tiers)
        3. Query pool for price and liquidity
        4. Calculate USD price
        5. Cache result
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            
        Returns:
            DEXPrice with price and liquidity data
        """
        import time as time_module
        start_time = time_module.time()
        
        self.total_queries += 1
        
        try:
            # Check cache first
            cached = self._get_cached_price(token_address)
            if cached:
                return cached
            
            # Validate Web3 client
            if not self.web3_client or not self.factory_address:
                return DEXPrice(
                    dex_name=self.dex_name,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    success=False,
                    error_message="Web3 client or factory not available"
                )
            
            # Find best pool across all fee tiers
            best_pool = await self._find_best_pool(token_address)
            
            if not best_pool:
                return DEXPrice(
                    dex_name=self.dex_name,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    success=False,
                    error_message="No pool found"
                )
            
            # Query pool for price and liquidity
            price_usd, liquidity_usd = await self._query_pool_data(
                best_pool['address'],
                token_address
            )
            
            query_time_ms = (time_module.time() - start_time) * 1000
            
            # Create result
            price_obj = DEXPrice(
                dex_name=self.dex_name,
                token_address=token_address,
                token_symbol=token_symbol,
                price_usd=price_usd,
                liquidity_usd=liquidity_usd,
                pool_address=best_pool['address'],
                success=True if price_usd else False,
                query_time_ms=query_time_ms
            )
            
            # Cache and track
            if price_obj.success:
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
        
        # Try each base token
        for base_token in self.base_tokens:
            # Try each fee tier
            for fee_tier in FEE_TIERS:
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
        token_address: str
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """
        Query pool for price and liquidity data.
        
        Args:
            pool_address: Pool contract address
            token_address: Token contract address
            
        Returns:
            Tuple of (price_usd, liquidity_usd)
        """
        # Simplified implementation - in production you would:
        # 1. Query slot0 for current price tick
        # 2. Calculate price from tick using Uniswap math
        # 3. Convert to USD using base token price
        # 4. Calculate liquidity in USD
        
        # For now, return None (placeholder)
        # This will be implemented in the next step
        return None, None


# =============================================================================
# SUSHISWAP IMPLEMENTATION (Placeholder)
# =============================================================================

class SushiSwapDEX(BaseDEX):
    """
    SushiSwap price fetching implementation.
    
    Note: This is a placeholder. SushiSwap uses similar logic to Uniswap V2.
    """
    
    def __init__(
        self,
        chain_id: int = 8453,
        cache_ttl_seconds: int = 60
    ):
        super().__init__(
            dex_name="sushiswap",
            chain_id=chain_id,
            cache_ttl_seconds=cache_ttl_seconds
        )
        
        self.logger.warning(
            "[SUSHISWAP] Implementation is placeholder - will return no price"
        )
    
    async def get_token_price(
        self,
        token_address: str,
        token_symbol: str
    ) -> DEXPrice:
        """Get token price from SushiSwap (placeholder)."""
        self.total_queries += 1
        
        return DEXPrice(
            dex_name=self.dex_name,
            token_address=token_address,
            token_symbol=token_symbol,
            success=False,
            error_message="SushiSwap integration not yet implemented"
        )


# =============================================================================
# CURVE IMPLEMENTATION (Placeholder)
# =============================================================================

class CurveDEX(BaseDEX):
    """
    Curve Finance price fetching implementation.
    
    Note: This is a placeholder. Curve requires special handling for
    stablecoin and meta pools.
    """
    
    def __init__(
        self,
        chain_id: int = 8453,
        cache_ttl_seconds: int = 60
    ):
        super().__init__(
            dex_name="curve",
            chain_id=chain_id,
            cache_ttl_seconds=cache_ttl_seconds
        )
        
        self.logger.warning(
            "[CURVE] Implementation is placeholder - will return no price"
        )
    
    async def get_token_price(
        self,
        token_address: str,
        token_symbol: str
    ) -> DEXPrice:
        """Get token price from Curve (placeholder)."""
        self.total_queries += 1
        
        return DEXPrice(
            dex_name=self.dex_name,
            token_address=token_address,
            token_symbol=token_symbol,
            success=False,
            error_message="Curve integration not yet implemented"
        )