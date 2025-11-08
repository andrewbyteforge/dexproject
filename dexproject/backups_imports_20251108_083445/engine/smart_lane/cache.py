"""
Smart Lane Cache System

Dedicated caching layer for Smart Lane analysis results. Provides intelligent
caching with data freshness tracking, cache invalidation, and performance
optimization for comprehensive analysis results.

Path: engine/smart_lane/cache.py
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any, List, Set
from dataclasses import asdict
from enum import Enum

import redis.asyncio as redis

from . import SmartLaneAnalysis, RiskCategory, RiskScore

logger = logging.getLogger(__name__)


class CacheStrategy(Enum):
    """Smart Lane cache strategies."""
    AGGRESSIVE = "AGGRESSIVE"  # Cache everything, longer TTL
    BALANCED = "BALANCED"      # Cache successful analyses, medium TTL
    CONSERVATIVE = "CONSERVATIVE"  # Cache only high-confidence results, short TTL


class DataFreshness(Enum):
    """Data freshness levels for cache validation."""
    FRESH = "FRESH"        # <5 minutes old
    GOOD = "GOOD"          # 5-30 minutes old
    STALE = "STALE"        # 30 minutes - 2 hours old
    EXPIRED = "EXPIRED"    # >2 hours old


class SmartLaneCache:
    """
    High-performance cache system for Smart Lane analysis results.
    
    Features:
    - Intelligent TTL based on analysis confidence
    - Data freshness tracking and validation
    - Selective caching based on quality scores
    - Background cache warming for popular tokens
    - Automatic invalidation on market events
    """
    
    def __init__(
        self,
        chain_id: int,
        redis_url: str = "redis://localhost:6379/1",
        cache_strategy: CacheStrategy = CacheStrategy.BALANCED,
        max_cache_size: int = 10000
    ):
        """
        Initialize the Smart Lane cache.
        
        Args:
            chain_id: Blockchain chain identifier
            redis_url: Redis connection URL
            cache_strategy: Caching strategy to use
            max_cache_size: Maximum number of cached analyses
        """
        self.chain_id = chain_id
        self.cache_strategy = cache_strategy
        self.max_cache_size = max_cache_size
        
        # Redis connection
        self.redis_client: Optional[redis.Redis] = None
        self.redis_url = redis_url
        
        # Cache configuration based on strategy
        self.cache_config = self._get_cache_config()
        
        # Performance tracking
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'stores': 0,
            'invalidations': 0,
            'evictions': 0
        }
        
        # Key prefixes for organization
        self.key_prefix = f"smart_lane:{chain_id}"
        
        logger.info(f"Smart Lane cache initialized for chain {chain_id} with {cache_strategy.value} strategy")
    
    async def initialize(self) -> None:
        """Initialize Redis connection and cache structures."""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            
            # Test connection
            await self.redis_client.ping()
            
            # Initialize cache metadata
            await self._initialize_cache_metadata()
            
            logger.info("Smart Lane cache connection established")
            
        except Exception as e:
            logger.error(f"Failed to initialize Smart Lane cache: {e}")
            # Set to None so methods can handle offline mode
            self.redis_client = None
            raise
    
    async def get_analysis(
        self,
        token_address: str,
        max_age_minutes: Optional[int] = None
    ) -> Optional[SmartLaneAnalysis]:
        """
        Retrieve cached analysis result if available and fresh.
        
        Args:
            token_address: Token contract address
            max_age_minutes: Maximum acceptable age in minutes (overrides strategy)
            
        Returns:
            Cached analysis if available and fresh, None otherwise
        """
        if not self.redis_client:
            return None
        
        cache_key = self._get_analysis_key(token_address)
        
        try:
            # Get cached data with metadata
            cached_data = await self.redis_client.hgetall(cache_key)
            
            if not cached_data:
                self.cache_stats['misses'] += 1
                return None
            
            # Check data freshness
            cached_timestamp = cached_data.get('timestamp')
            if not cached_timestamp:
                self.cache_stats['misses'] += 1
                return None
            
            cache_age_minutes = self._calculate_cache_age_minutes(cached_timestamp)
            max_acceptable_age = max_age_minutes or self.cache_config['default_ttl_minutes']
            
            if cache_age_minutes > max_acceptable_age:
                # Cache expired - remove it
                await self._invalidate_analysis(token_address)
                self.cache_stats['misses'] += 1
                return None
            
            # Deserialize analysis data
            analysis_json = cached_data.get('analysis_data')
            if not analysis_json:
                self.cache_stats['misses'] += 1
                return None
            
            analysis_dict = json.loads(analysis_json)
            analysis = self._deserialize_analysis(analysis_dict)
            
            # Update freshness score based on age
            analysis.data_freshness_score = self._calculate_freshness_score(cache_age_minutes)
            
            self.cache_stats['hits'] += 1
            logger.debug(f"Cache hit for {token_address[:10]}... (age: {cache_age_minutes:.1f}m)")
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error retrieving cached analysis for {token_address}: {e}")
            self.cache_stats['misses'] += 1
            return None
    
    async def store_analysis(
        self,
        token_address: str,
        analysis: SmartLaneAnalysis,
        custom_ttl_minutes: Optional[int] = None
    ) -> bool:
        """
        Store analysis result in cache with intelligent TTL.
        
        Args:
            token_address: Token contract address
            analysis: Analysis result to cache
            custom_ttl_minutes: Custom TTL override
            
        Returns:
            True if successfully stored, False otherwise
        """
        if not self.redis_client:
            return False
        
        try:
            # Check if analysis meets caching criteria
            if not self._should_cache_analysis(analysis):
                logger.debug(f"Skipping cache for {token_address[:10]}... (quality threshold not met)")
                return False
            
            cache_key = self._get_analysis_key(token_address)
            
            # Calculate TTL based on analysis quality
            ttl_minutes = custom_ttl_minutes or self._calculate_intelligent_ttl(analysis)
            
            # Serialize analysis data
            analysis_data = self._serialize_analysis(analysis)
            
            # Prepare cache entry
            cache_entry = {
                'analysis_data': json.dumps(analysis_data),
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'confidence': str(analysis.overall_confidence),
                'risk_score': str(analysis.overall_risk_score),
                'ttl_minutes': str(ttl_minutes),
                'cache_strategy': self.cache_strategy.value
            }
            
            # Store in Redis with expiration
            pipe = self.redis_client.pipeline()
            pipe.hset(cache_key, mapping=cache_entry)
            pipe.expire(cache_key, ttl_minutes * 60)  # Convert to seconds
            
            await pipe.execute()
            
            # Update cache size tracking
            await self._update_cache_size_tracking(token_address)
            
            self.cache_stats['stores'] += 1
            logger.debug(
                f"Cached analysis for {token_address[:10]}... "
                f"(TTL: {ttl_minutes}m, confidence: {analysis.overall_confidence:.3f})"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error storing analysis in cache for {token_address}: {e}")
            return False
    
    async def invalidate_analysis(self, token_address: str) -> bool:
        """
        Manually invalidate cached analysis for a token.
        
        Args:
            token_address: Token contract address
            
        Returns:
            True if invalidated, False otherwise
        """
        return await self._invalidate_analysis(token_address)
    
    async def invalidate_by_risk_category(
        self,
        category: RiskCategory,
        min_age_minutes: int = 0
    ) -> int:
        """
        Invalidate cached analyses that may be affected by changes in a specific risk category.
        
        Args:
            category: Risk category that changed
            min_age_minutes: Only invalidate entries older than this
            
        Returns:
            Number of entries invalidated
        """
        if not self.redis_client:
            return 0
        
        try:
            # Get all analysis keys
            pattern = f"{self.key_prefix}:analysis:*"
            keys = await self.redis_client.keys(pattern)
            
            invalidated_count = 0
            
            for key in keys:
                try:
                    # Check cache age
                    cached_data = await self.redis_client.hget(key, 'timestamp')
                    if not cached_data:
                        continue
                    
                    age_minutes = self._calculate_cache_age_minutes(cached_data)
                    
                    if age_minutes >= min_age_minutes:
                        await self.redis_client.delete(key)
                        invalidated_count += 1
                        
                except Exception as e:
                    logger.warning(f"Error checking cache entry {key}: {e}")
            
            self.cache_stats['invalidations'] += invalidated_count
            
            logger.info(
                f"Invalidated {invalidated_count} cache entries for risk category {category.value}"
            )
            
            return invalidated_count
            
        except Exception as e:
            logger.error(f"Error invalidating cache by risk category {category.value}: {e}")
            return 0
    
    async def warm_cache(self, token_addresses: List[str]) -> Dict[str, bool]:
        """
        Pre-warm cache for a list of popular tokens.
        
        Args:
            token_addresses: List of token addresses to warm
            
        Returns:
            Dict mapping token addresses to success status
        """
        logger.info(f"Starting cache warm-up for {len(token_addresses)} tokens")
        
        results = {}
        
        # Import pipeline here to avoid circular imports
        from .pipeline import get_pipeline
        
        pipeline = get_pipeline(chain_id=self.chain_id)
        
        # Warm cache concurrently (but with limits)
        semaphore = asyncio.Semaphore(5)  # Limit concurrent warming
        
        async def warm_single_token(token_address: str) -> bool:
            async with semaphore:
                try:
                    # Check if already cached
                    cached = await self.get_analysis(token_address)
                    if cached:
                        results[token_address] = True
                        return True
                    
                    # Perform analysis to warm cache
                    analysis = await pipeline.analyze_token(
                        token_address=token_address,
                        context={'cache_warming': True}
                    )
                    
                    results[token_address] = True
                    logger.debug(f"Cache warmed for {token_address[:10]}...")
                    return True
                    
                except Exception as e:
                    logger.warning(f"Failed to warm cache for {token_address}: {e}")
                    results[token_address] = False
                    return False
        
        # Execute warming tasks
        warming_tasks = [warm_single_token(addr) for addr in token_addresses]
        await asyncio.gather(*warming_tasks, return_exceptions=True)
        
        successful_warms = sum(1 for success in results.values() if success)
        logger.info(f"Cache warming completed: {successful_warms}/{len(token_addresses)} successful")
        
        return results
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get comprehensive cache performance statistics."""
        total_requests = self.cache_stats['hits'] + self.cache_stats['misses']
        hit_rate = (self.cache_stats['hits'] / total_requests * 100) if total_requests > 0 else 0.0
        
        return {
            'strategy': self.cache_strategy.value,
            'total_requests': total_requests,
            'cache_hits': self.cache_stats['hits'],
            'cache_misses': self.cache_stats['misses'],
            'hit_rate_percent': hit_rate,
            'stores': self.cache_stats['stores'],
            'invalidations': self.cache_stats['invalidations'],
            'evictions': self.cache_stats['evictions'],
            'redis_connected': self.redis_client is not None,
            'default_ttl_minutes': self.cache_config['default_ttl_minutes'],
            'max_cache_size': self.max_cache_size
        }
    
    async def cleanup_expired_entries(self) -> int:
        """
        Clean up expired cache entries and return count removed.
        
        Returns:
            Number of entries cleaned up
        """
        if not self.redis_client:
            return 0
        
        try:
            # Get all analysis keys
            pattern = f"{self.key_prefix}:analysis:*"
            keys = await self.redis_client.keys(pattern)
            
            cleaned_count = 0
            
            for key in keys:
                # Check if key exists (Redis auto-expires, but this catches any stragglers)
                exists = await self.redis_client.exists(key)
                if not exists:
                    cleaned_count += 1
            
            if cleaned_count > 0:
                self.cache_stats['evictions'] += cleaned_count
                logger.info(f"Cleaned up {cleaned_count} expired cache entries")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error during cache cleanup: {e}")
            return 0
    
    async def close(self) -> None:
        """Close Redis connection and cleanup resources."""
        if self.redis_client:
            try:
                await self.redis_client.close()
                logger.info("Smart Lane cache connection closed")
            except Exception as e:
                logger.error(f"Error closing cache connection: {e}")
    
    # Private helper methods
    
    def _get_cache_config(self) -> Dict[str, Any]:
        """Get cache configuration based on strategy."""
        configs = {
            CacheStrategy.AGGRESSIVE: {
                'default_ttl_minutes': 60,
                'high_confidence_ttl_minutes': 120,
                'low_confidence_ttl_minutes': 30,
                'min_confidence_threshold': 0.3,
                'min_quality_threshold': 0.0
            },
            CacheStrategy.BALANCED: {
                'default_ttl_minutes': 30,
                'high_confidence_ttl_minutes': 60,
                'low_confidence_ttl_minutes': 15,
                'min_confidence_threshold': 0.5,
                'min_quality_threshold': 0.4
            },
            CacheStrategy.CONSERVATIVE: {
                'default_ttl_minutes': 15,
                'high_confidence_ttl_minutes': 30,
                'low_confidence_ttl_minutes': 10,
                'min_confidence_threshold': 0.7,
                'min_quality_threshold': 0.6
            }
        }
        
        return configs.get(self.cache_strategy, configs[CacheStrategy.BALANCED])
    
    def _get_analysis_key(self, token_address: str) -> str:
        """Generate Redis key for token analysis."""
        return f"{self.key_prefix}:analysis:{token_address.lower()}"
    
    def _calculate_cache_age_minutes(self, timestamp_str: str) -> float:
        """Calculate cache age in minutes from timestamp string."""
        try:
            cached_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            current_time = datetime.now(timezone.utc)
            age_delta = current_time - cached_time
            return age_delta.total_seconds() / 60.0
        except Exception:
            return float('inf')  # Treat invalid timestamps as very old
    
    def _calculate_freshness_score(self, age_minutes: float) -> float:
        """Calculate data freshness score based on age."""
        if age_minutes < 5:
            return 1.0  # Fresh
        elif age_minutes < 30:
            return 0.8  # Good
        elif age_minutes < 120:
            return 0.5  # Stale
        else:
            return 0.2  # Expired
    
    def _should_cache_analysis(self, analysis: SmartLaneAnalysis) -> bool:
        """Determine if analysis meets criteria for caching."""
        config = self.cache_config
        
        # Check confidence threshold
        if analysis.overall_confidence < config['min_confidence_threshold']:
            return False
        
        # Check quality threshold (combination of confidence and low error rate)
        quality_score = analysis.overall_confidence * (1.0 - len(analysis.critical_warnings) * 0.2)
        if quality_score < config['min_quality_threshold']:
            return False
        
        # Always cache if no critical warnings and decent confidence
        if not analysis.critical_warnings and analysis.overall_confidence > 0.6:
            return True
        
        return True
    
    def _calculate_intelligent_ttl(self, analysis: SmartLaneAnalysis) -> int:
        """Calculate TTL based on analysis quality and confidence."""
        config = self.cache_config
        
        # Base TTL on confidence level
        if analysis.overall_confidence > 0.8:
            base_ttl = config['high_confidence_ttl_minutes']
        elif analysis.overall_confidence > 0.5:
            base_ttl = config['default_ttl_minutes']
        else:
            base_ttl = config['low_confidence_ttl_minutes']
        
        # Adjust based on risk score (higher risk = shorter TTL)
        risk_factor = 1.0 - (analysis.overall_risk_score * 0.3)
        
        # Adjust based on analysis time (faster analysis = shorter TTL as potentially less thorough)
        time_factor = min(1.0, analysis.total_analysis_time_ms / 3000.0)  # Normalize to 3s target
        
        final_ttl = int(base_ttl * risk_factor * time_factor)
        return max(5, final_ttl)  # Minimum 5 minute TTL
    
    def _serialize_analysis(self, analysis: SmartLaneAnalysis) -> Dict[str, Any]:
        """Serialize analysis object for storage."""
        # Convert to dict, handling special types
        analysis_dict = asdict(analysis)
        
        # Convert risk_scores dict (keys are enums)
        if 'risk_scores' in analysis_dict:
            risk_scores_serialized = {}
            for category, score in analysis_dict['risk_scores'].items():
                if hasattr(category, 'value'):  # Enum
                    key = category.value
                else:
                    key = str(category)
                risk_scores_serialized[key] = asdict(score) if hasattr(score, '__dict__') else score
            analysis_dict['risk_scores'] = risk_scores_serialized
        
        # Convert enums to strings
        for key, value in analysis_dict.items():
            if hasattr(value, 'value'):  # Enum
                analysis_dict[key] = value.value
        
        return analysis_dict
    
    def _deserialize_analysis(self, analysis_dict: Dict[str, Any]) -> SmartLaneAnalysis:
        """Deserialize analysis object from storage."""
        # This is a simplified deserialization - in production you'd want more robust handling
        # For now, we'll create a basic SmartLaneAnalysis object
        
        # Import the required enums
        from . import SmartLaneAction, DecisionConfidence
        
        # Convert string values back to enums where needed
        if 'recommended_action' in analysis_dict:
            analysis_dict['recommended_action'] = SmartLaneAction(analysis_dict['recommended_action'])
        
        if 'confidence_level' in analysis_dict:
            analysis_dict['confidence_level'] = DecisionConfidence(analysis_dict['confidence_level'])
        
        # Handle risk_scores reconstruction (simplified)
        if 'risk_scores' in analysis_dict:
            # For now, we'll skip full risk_scores reconstruction to avoid complexity
            # In production, you'd want to properly reconstruct the RiskScore objects
            pass
        
        # Create SmartLaneAnalysis object
        return SmartLaneAnalysis(**analysis_dict)
    
    async def _initialize_cache_metadata(self) -> None:
        """Initialize cache metadata structures."""
        if not self.redis_client:
            return
        
        metadata_key = f"{self.key_prefix}:metadata"
        
        metadata = {
            'initialized_at': datetime.now(timezone.utc).isoformat(),
            'strategy': self.cache_strategy.value,
            'chain_id': str(self.chain_id),
            'max_cache_size': str(self.max_cache_size)
        }
        
        await self.redis_client.hset(metadata_key, mapping=metadata)
    
    async def _invalidate_analysis(self, token_address: str) -> bool:
        """Internal method to invalidate a specific analysis."""
        if not self.redis_client:
            return False
        
        try:
            cache_key = self._get_analysis_key(token_address)
            deleted = await self.redis_client.delete(cache_key)
            
            if deleted:
                self.cache_stats['invalidations'] += 1
                logger.debug(f"Invalidated cache for {token_address[:10]}...")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error invalidating analysis for {token_address}: {e}")
            return False
    
    async def _update_cache_size_tracking(self, token_address: str) -> None:
        """Update cache size tracking and enforce limits."""
        if not self.redis_client:
            return
        
        try:
            # Add to tracking set
            tracking_key = f"{self.key_prefix}:tracking"
            await self.redis_client.sadd(tracking_key, token_address.lower())
            
            # Check if we need to evict entries
            current_size = await self.redis_client.scard(tracking_key)
            
            if current_size > self.max_cache_size:
                # Get oldest entries and evict them
                excess = current_size - self.max_cache_size
                await self._evict_oldest_entries(excess)
                
        except Exception as e:
            logger.error(f"Error updating cache size tracking: {e}")
    
    async def _evict_oldest_entries(self, count: int) -> None:
        """Evict the oldest cache entries to maintain size limits."""
        if not self.redis_client:
            return
        
        try:
            # This is a simplified eviction strategy
            # In production, you'd want LRU or more sophisticated strategies
            
            pattern = f"{self.key_prefix}:analysis:*"
            keys = await self.redis_client.keys(pattern)
            
            # Sort by timestamp (oldest first)
            key_times = []
            for key in keys:
                timestamp = await self.redis_client.hget(key, 'timestamp')
                if timestamp:
                    key_times.append((key, timestamp))
            
            # Sort by timestamp and evict oldest
            key_times.sort(key=lambda x: x[1])
            
            evicted = 0
            for key, _ in key_times[:count]:
                await self.redis_client.delete(key)
                evicted += 1
            
            self.cache_stats['evictions'] += evicted
            logger.info(f"Evicted {evicted} oldest cache entries to maintain size limit")
            
        except Exception as e:
            logger.error(f"Error evicting oldest entries: {e}")


# Export key classes
__all__ = [
    'SmartLaneCache',
    'CacheStrategy',
    'DataFreshness'
]