"""
DEX Price Comparator - Multi-DEX Price Comparison Engine

This module orchestrates price queries across multiple DEXs to find the best
prices and detect arbitrage opportunities. It runs queries in parallel with
timeouts and proper error handling.

Phase 2: Multi-DEX Price Comparison
File: paper_trading/intelligence/dex_price_comparator.py
"""

import logging
import asyncio
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from django.utils import timezone
from django.core.cache import cache

# Import DEX integrations
from paper_trading.intelligence.dex_integrations import (
    BaseDEX,
    DEXPrice,
    UniswapV3DEX,
    SushiSwapDEX,
    CurveDEX
)

# Import constants and defaults
from paper_trading.constants import DEXNames, DEXPriceFields
from paper_trading.defaults import DEXComparisonDefaults

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class DEXPriceComparison:
    """
    Result of comparing prices across multiple DEXs.
    
    Attributes:
        token_address: Token contract address
        token_symbol: Token symbol
        prices: List of prices from each DEX
        best_price: Highest price found
        best_dex: DEX with best price
        price_spread_percent: Spread between best and worst
        average_price: Average across all DEXs
        successful_queries: Number of successful DEX queries
        total_queries: Total number of DEX queries attempted
        comparison_time_ms: Total time for comparison
        timestamp: When comparison was performed
    """
    token_address: str
    token_symbol: str
    prices: List[DEXPrice] = field(default_factory=list)
    best_price: Optional[Decimal] = None
    best_dex: Optional[str] = None
    worst_price: Optional[Decimal] = None
    worst_dex: Optional[str] = None
    price_spread_percent: Decimal = Decimal('0')
    average_price: Optional[Decimal] = None
    successful_queries: int = 0
    total_queries: int = 0
    comparison_time_ms: float = 0.0
    timestamp: datetime = None
    
    def __post_init__(self):
        """Calculate derived fields after initialization."""
        if self.timestamp is None:
            self.timestamp = timezone.now()
        
        # Calculate best and worst prices
        successful_prices = [p for p in self.prices if p.success and p.price_usd]
        
        if successful_prices:
            # Sort by price
            prices_sorted = sorted(successful_prices, key=lambda x: x.price_usd, reverse=True)
            
            self.best_price = prices_sorted[0].price_usd
            self.best_dex = prices_sorted[0].dex_name
            
            self.worst_price = prices_sorted[-1].price_usd
            self.worst_dex = prices_sorted[-1].dex_name
            
            # Calculate spread
            if self.worst_price and self.worst_price > 0:
                self.price_spread_percent = (
                    ((self.best_price - self.worst_price) / self.worst_price) * Decimal('100')
                )
            
            # Calculate average
            total = sum(p.price_usd for p in successful_prices)
            self.average_price = total / len(successful_prices)
            
            self.successful_queries = len(successful_prices)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'token_address': self.token_address,
            'token_symbol': self.token_symbol,
            'prices': [p.to_dict() for p in self.prices],
            'best_price': float(self.best_price) if self.best_price else None,
            'best_dex': self.best_dex,
            'worst_price': float(self.worst_price) if self.worst_price else None,
            'worst_dex': self.worst_dex,
            'price_spread_percent': float(self.price_spread_percent),
            'average_price': float(self.average_price) if self.average_price else None,
            'successful_queries': self.successful_queries,
            'total_queries': self.total_queries,
            'comparison_time_ms': self.comparison_time_ms,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


# =============================================================================
# DEX PRICE COMPARATOR
# =============================================================================

class DEXPriceComparator:
    """
    Multi-DEX price comparison engine.
    
    Features:
    - Queries multiple DEXs in parallel
    - Timeout protection per DEX
    - Circuit breaker for failed DEXs
    - Caching for performance
    - Best price selection
    - Arbitrage opportunity detection (see arbitrage_detector.py)
    
    Usage:
        comparator = DEXPriceComparator(chain_id=84532)
        comparison = await comparator.compare_prices(
            token_address='0x...',
            token_symbol='WETH'
        )
        print(f"Best price: ${comparison.best_price} on {comparison.best_dex}")
    """
    
    def __init__(
        self,
        chain_id: int = 8453,
        enabled_dexs: Optional[List[str]] = None
    ):
        """
        Initialize DEX price comparator.
        
        Args:
            chain_id: Blockchain network ID
            enabled_dexs: List of enabled DEX names (None = all enabled)
        """
        self.logger = logging.getLogger(f'{__name__}.Comparator')  # ✅ KEEP THIS ONE
        self.chain_id = chain_id
        
        # Determine which DEXs to use
        if enabled_dexs is None:
            self.enabled_dexs = self._get_default_enabled_dexs()
        else:
            self.enabled_dexs = enabled_dexs
        
        # Initialize DEX instances
        self.dexs: Dict[str, BaseDEX] = {}
        self._initialize_dexs()
        
        # Configuration
        self.single_dex_timeout = DEXComparisonDefaults.SINGLE_DEX_TIMEOUT_SECONDS
        self.total_timeout = DEXComparisonDefaults.TOTAL_COMPARISON_TIMEOUT_SECONDS
        self.min_successful_quotes = DEXComparisonDefaults.MIN_SUCCESSFUL_DEX_QUOTES
        self.cache_ttl = DEXComparisonDefaults.COMPARISON_CACHE_TTL_SECONDS
        
        # Performance tracking
        self.total_comparisons = 0
        self.successful_comparisons = 0
        self.cache_hits = 0
        
        # ❌ REMOVE THIS DUPLICATE LINE:
        # self.logger = logging.getLogger(f'{__name__}.Comparator')
        
        self.logger.info(
            f"[DEX COMPARATOR] Initialized for chain {chain_id}, "
            f"Enabled DEXs: {', '.join(self.enabled_dexs)}"
        )






    def _get_default_enabled_dexs(self) -> List[str]:
        """
        Get list of enabled DEXs from defaults.
        
        Returns:
            List of enabled DEX names
        """
        enabled = []
        
        if DEXComparisonDefaults.ENABLE_UNISWAP_V3:
            enabled.append(DEXNames.UNISWAP_V3)
        
        if DEXComparisonDefaults.ENABLE_SUSHISWAP:
            enabled.append(DEXNames.SUSHISWAP)
        
        if DEXComparisonDefaults.ENABLE_CURVE:
            enabled.append(DEXNames.CURVE)
        
        return enabled
    
    def _initialize_dexs(self) -> None:
        """Initialize DEX integration instances."""
        try:
            if DEXNames.UNISWAP_V3 in self.enabled_dexs:
                self.dexs[DEXNames.UNISWAP_V3] = UniswapV3DEX(
                    chain_id=self.chain_id,
                    cache_ttl_seconds=DEXComparisonDefaults.PRICE_CACHE_TTL_SECONDS
                )
            
            if DEXNames.SUSHISWAP in self.enabled_dexs:
                self.dexs[DEXNames.SUSHISWAP] = SushiSwapDEX(
                    chain_id=self.chain_id,
                    cache_ttl_seconds=DEXComparisonDefaults.PRICE_CACHE_TTL_SECONDS
                )
            
            if DEXNames.CURVE in self.enabled_dexs:
                self.dexs[DEXNames.CURVE] = CurveDEX(
                    chain_id=self.chain_id,
                    cache_ttl_seconds=DEXComparisonDefaults.PRICE_CACHE_TTL_SECONDS
                )
            
            self.logger.info(
                f"[DEX COMPARATOR] Initialized {len(self.dexs)} DEX integrations"
            )
        
        except Exception as e:
            self.logger.error(
                f"[DEX COMPARATOR] Error initializing DEXs: {e}",
                exc_info=True
            )
    
    # =========================================================================
    # MAIN COMPARISON METHOD
    # =========================================================================
    
    async def compare_prices(
        self,
        token_address: str,
        token_symbol: str,
        use_cache: bool = True
    ) -> DEXPriceComparison:
        """
        Compare token prices across all enabled DEXs.
        
        This method:
        1. Checks cache first (if enabled)
        2. Queries all DEXs in parallel with timeouts
        3. Collects successful results
        4. Identifies best price
        5. Caches result
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            use_cache: Whether to use cached results
            
        Returns:
            DEXPriceComparison with results from all DEXs
        """
        import time as time_module
        start_time = time_module.time()
        self.total_comparisons += 1
        
        # Check cache first
        if use_cache:
            cached = self._get_cached_comparison(token_address)
            if cached:
                self.cache_hits += 1
                self.logger.debug(
                    f"[DEX COMPARATOR] Cache hit for {token_symbol}"
                )
                return cached
        
        try:
            # Query all DEXs in parallel with timeout
            prices = await self._query_all_dexs_parallel(
                token_address,
                token_symbol
            )

            # ===================================================================
            # LIQUIDITY FILTERING - Filter out low-liquidity pools
            # ===================================================================
            filtered_prices = []
            for price in prices:
                if not price.success or not price.liquidity_usd:
                    # Keep failed prices for debugging
                    filtered_prices.append(price)
                    continue
                
                # Get minimum liquidity threshold for this DEX
                min_liquidity = self._get_min_liquidity_for_dex(price.dex_name)
                
                if price.liquidity_usd >= min_liquidity:
                    filtered_prices.append(price)
                    self.logger.debug(
                        f"[{price.dex_name.upper()}] ✅ Liquidity OK: "
                        f"${price.liquidity_usd:,.0f} >= ${min_liquidity:,.0f}"
                    )
                else:
                    self.logger.warning(
                        f"[{price.dex_name.upper()}] ❌ REJECTED - Low liquidity: "
                        f"${price.liquidity_usd:,.0f} < ${min_liquidity:,.0f}"
                    )
                    # Mark as failed and keep for debugging
                    price.success = False
                    price.error_message = f"Insufficient liquidity: ${price.liquidity_usd:,.0f}"
                    filtered_prices.append(price)

            prices = filtered_prices
            # ===================================================================
            
            # Calculate comparison time
            comparison_time_ms = (time_module.time() - start_time) * 1000
            
            # Create comparison result
            comparison = DEXPriceComparison(
                token_address=token_address,
                token_symbol=token_symbol,
                prices=prices,
                total_queries=len(self.dexs),
                comparison_time_ms=comparison_time_ms
            )
            
            # Check if we got enough successful results
            if comparison.successful_queries < self.min_successful_quotes:
                self.logger.warning(
                    f"[DEX COMPARATOR] Only {comparison.successful_queries} successful "
                    f"quotes for {token_symbol} (minimum: {self.min_successful_quotes})"
                )
                # ✅ FIX: Invalidate comparison - no trade should happen
                comparison.best_price = None
                comparison.best_dex = None
                comparison.worst_price = None
                comparison.worst_dex = None
                comparison.average_price = None
            else:
                self.successful_comparisons += 1
            
            # Cache result
            if use_cache and comparison.successful_queries > 0:
                self._cache_comparison(comparison)
            
            # Log results
            if comparison.best_price:
                self.logger.info(
                    f"[DEX COMPARATOR] {token_symbol}: "
                    f"Best ${comparison.best_price:.4f} ({comparison.best_dex}), "
                    f"Spread: {comparison.price_spread_percent:.2f}%, "
                    f"Time: {comparison_time_ms:.0f}ms"
                )
            
            return comparison
        
        except Exception as e:
            self.logger.error(
                f"[DEX COMPARATOR] Error comparing prices for {token_symbol}: {e}",
                exc_info=True
            )
            
            # Return empty comparison on error
            return DEXPriceComparison(
                token_address=token_address,
                token_symbol=token_symbol,
                total_queries=len(self.dexs),
                comparison_time_ms=(time_module.time() - start_time) * 1000
            )
    
    # =========================================================================
    # PARALLEL QUERY EXECUTION
    # =========================================================================
    
    async def _query_all_dexs_parallel(
        self,
        token_address: str,
        token_symbol: str
    ) -> List[DEXPrice]:
        """
        Query all DEXs in parallel with individual timeouts.
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            
        Returns:
            List of DEXPrice objects (successful and failed)
        """
        # Create tasks for each DEX
        tasks = []
        
        for dex_name, dex_instance in self.dexs.items():
            # Wrap each query with timeout
            task = asyncio.create_task(
                self._query_dex_with_timeout(
                    dex_instance,
                    token_address,
                    token_symbol
                )
            )
            tasks.append(task)
        
        # Wait for all tasks with overall timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.total_timeout
            )
        except asyncio.TimeoutError:
            self.logger.warning(
                f"[DEX COMPARATOR] Overall timeout ({self.total_timeout}s) "
                f"exceeded for {token_symbol}"
            )
            # Cancel remaining tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
            results = []
        
        # Filter out exceptions and return valid results
        prices = []
        for result in results:
            if isinstance(result, DEXPrice):
                prices.append(result)
            elif isinstance(result, Exception):
                self.logger.debug(
                    f"[DEX COMPARATOR] Query exception: {result}"
                )
        
        return prices
    
    async def _query_dex_with_timeout(
        self,
        dex: BaseDEX,
        token_address: str,
        token_symbol: str
    ) -> DEXPrice:
        """
        Query single DEX with timeout protection.
        
        Args:
            dex: DEX instance to query
            token_address: Token contract address
            token_symbol: Token symbol
            
        Returns:
            DEXPrice object (may indicate failure)
        """
        try:
            # Query with timeout
            price = await asyncio.wait_for(
                dex.get_token_price(token_address, token_symbol),
                timeout=self.single_dex_timeout
            )
            return price
        
        except asyncio.TimeoutError:
            self.logger.warning(
                f"[{dex.dex_name.upper()}] Timeout ({self.single_dex_timeout}s) "
                f"for {token_symbol}"
            )
            return DEXPrice(
                dex_name=dex.dex_name,
                token_address=token_address,
                token_symbol=token_symbol,
                success=False,
                error_message=f"Timeout after {self.single_dex_timeout}s"
            )
        
        except Exception as e:
            self.logger.error(
                f"[{dex.dex_name.upper()}] Error querying {token_symbol}: {e}"
            )
            return DEXPrice(
                dex_name=dex.dex_name,
                token_address=token_address,
                token_symbol=token_symbol,
                success=False,
                error_message=str(e)
            )
    
    # =========================================================================
    # CACHING
    # =========================================================================
    
    def _get_cache_key(self, token_address: str) -> str:
        """Generate cache key for price comparison."""
        return f"dex_comparison:{self.chain_id}:{token_address}"
    
    def _get_cached_comparison(
        self,
        token_address: str
    ) -> Optional[DEXPriceComparison]:
        """Get cached price comparison."""
        cache_key = self._get_cache_key(token_address)
        return cache.get(cache_key)
    
    def _cache_comparison(self, comparison: DEXPriceComparison) -> None:
        """Cache price comparison result."""
        cache_key = self._get_cache_key(comparison.token_address)
        cache.set(cache_key, comparison, self.cache_ttl)
    
    # =========================================================================
    # PERFORMANCE METRICS
    # =========================================================================

    def _get_min_liquidity_for_dex(self, dex_name: str) -> Decimal:
        """
        Get minimum liquidity threshold for specific DEX.
        
        Args:
            dex_name: Name of the DEX
            
        Returns:
            Minimum liquidity threshold in USD
        """
        thresholds = {
            DEXNames.UNISWAP_V3: DEXComparisonDefaults.MIN_LIQUIDITY_USD_UNISWAP_V3,
            DEXNames.SUSHISWAP: DEXComparisonDefaults.MIN_LIQUIDITY_USD_SUSHISWAP,
            DEXNames.CURVE: DEXComparisonDefaults.MIN_LIQUIDITY_USD_CURVE,
        }
        return thresholds.get(dex_name, DEXComparisonDefaults.MIN_DEX_LIQUIDITY_USD)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get performance statistics for price comparator.
        
        Returns:
            Dictionary with performance metrics
        """
        success_rate = (
            (self.successful_comparisons / max(self.total_comparisons, 1)) * 100
            if self.total_comparisons > 0
            else 0
        )
        
        cache_hit_rate = (
            (self.cache_hits / max(self.total_comparisons, 1)) * 100
            if self.total_comparisons > 0
            else 0
        )
        
        # Get DEX-specific stats
        dex_stats = {}
        for dex_name, dex_instance in self.dexs.items():
            dex_stats[dex_name] = dex_instance.get_performance_stats()
        
        return {
            'total_comparisons': self.total_comparisons,
            'successful_comparisons': self.successful_comparisons,
            'success_rate_percent': round(success_rate, 2),
            'cache_hits': self.cache_hits,
            'cache_hit_rate_percent': round(cache_hit_rate, 2),
            'enabled_dexs': self.enabled_dexs,
            'dex_stats': dex_stats
        }
    
    # =========================================================================
    # CLEANUP
    # =========================================================================
    
    async def cleanup(self) -> None:
        """Clean up all DEX integrations."""
        try:
            # Cleanup all DEX instances
            for dex_name, dex_instance in self.dexs.items():
                await dex_instance.cleanup()
            
            self.logger.info("[DEX COMPARATOR] Cleanup complete")
        
        except Exception as e:
            self.logger.error(
                f"[DEX COMPARATOR] Cleanup error: {e}",
                exc_info=True
            )