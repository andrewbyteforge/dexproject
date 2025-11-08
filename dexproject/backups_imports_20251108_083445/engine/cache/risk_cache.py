"""
Fast Risk Cache - In-Memory Risk Data Engine

High-performance caching system for fast lane execution risk assessments.
Provides sub-50ms risk score retrieval with intelligent cache warming,
eviction policies, and real-time risk data synchronization.

Key Features:
- Sub-50ms risk score retrieval for fast lane decisions
- Intelligent cache warming based on trading patterns  
- Multi-tier cache architecture (Memory + Redis)
- Risk data staleness detection and refresh
- Cache hit ratio optimization
- Emergency risk overrides and blacklist support
- Statistical risk pattern learning
- Integration with comprehensive risk analysis results

File: dexproject/engine/cache/risk_cache.py
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
import json
import hashlib
import statistics
from collections import defaultdict, deque

# Redis for persistent caching
import redis.asyncio as redis

# Internal imports
from ..config import config
from ..utils import safe_decimal
from shared.schemas import RiskLevel, RiskCategory


logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class CacheStatus(Enum):
    """Cache entry status."""
    FRESH = "fresh"           # Recently updated, high confidence
    STALE = "stale"          # Older but still usable
    EXPIRED = "expired"      # Too old, needs refresh
    REFRESHING = "refreshing" # Currently being updated
    FAILED = "failed"        # Update failed, using last known data


class RiskCacheLevel(Enum):
    """Multi-tier cache levels."""
    MEMORY = "memory"        # In-memory cache (fastest)
    REDIS = "redis"          # Redis cache (fast)
    DATABASE = "database"    # Database fallback (slow)


@dataclass
class RiskCacheEntry:
    """Single risk cache entry with metadata."""
    token_address: str
    chain_id: int
    
    # Risk data
    overall_risk_score: Decimal
    risk_level: RiskLevel
    risk_categories: Dict[RiskCategory, Decimal]
    
    # Flags
    is_honeypot: bool = False
    is_scam: bool = False
    is_verified: bool = False
    is_blacklisted: bool = False
    
    # Cache metadata
    cached_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=1))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0
    
    # Data source
    source: str = "unknown"
    confidence: float = 1.0
    
    # Performance tracking
    retrieval_time_ms: float = 0.0
    cache_level: RiskCacheLevel = RiskCacheLevel.MEMORY
    
    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return datetime.now(timezone.utc) > self.expires_at
    
    def is_stale(self, stale_threshold_minutes: int = 30) -> bool:
        """Check if cache entry is stale but not expired."""
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=stale_threshold_minutes)
        return self.cached_at < stale_time
    
    def update_access(self) -> None:
        """Update access statistics."""
        self.last_accessed = datetime.now(timezone.utc)
        self.access_count += 1
    
    def get_cache_key(self) -> str:
        """Generate cache key for this entry."""
        return f"risk:{self.chain_id}:{self.token_address.lower()}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "token_address": self.token_address,
            "chain_id": self.chain_id,
            "overall_risk_score": str(self.overall_risk_score),
            "risk_level": self.risk_level.value,
            "risk_categories": {
                category.value: str(score) 
                for category, score in self.risk_categories.items()
            },
            "is_honeypot": self.is_honeypot,
            "is_scam": self.is_scam,
            "is_verified": self.is_verified,
            "is_blacklisted": self.is_blacklisted,
            "cached_at": self.cached_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "source": self.source,
            "confidence": self.confidence,
            "retrieval_time_ms": self.retrieval_time_ms,
            "cache_level": self.cache_level.value
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RiskCacheEntry':
        """Create instance from dictionary."""
        entry = cls(
            token_address=data["token_address"],
            chain_id=data["chain_id"],
            overall_risk_score=Decimal(data["overall_risk_score"]),
            risk_level=RiskLevel(data["risk_level"]),
            risk_categories={
                RiskCategory(cat): Decimal(score)
                for cat, score in data["risk_categories"].items()
            },
            is_honeypot=data["is_honeypot"],
            is_scam=data["is_scam"],
            is_verified=data["is_verified"],
            is_blacklisted=data["is_blacklisted"],
            cached_at=datetime.fromisoformat(data["cached_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]),
            access_count=data["access_count"],
            source=data["source"],
            confidence=data["confidence"],
            retrieval_time_ms=data["retrieval_time_ms"],
            cache_level=RiskCacheLevel(data["cache_level"])
        )
        return entry


@dataclass
class CacheStatistics:
    """Cache performance statistics."""
    cache_hits: int = 0
    cache_misses: int = 0
    cache_refreshes: int = 0
    cache_evictions: int = 0
    
    # Timing metrics
    avg_retrieval_time_ms: float = 0.0
    max_retrieval_time_ms: float = 0.0
    min_retrieval_time_ms: float = float('inf')
    
    # Hit ratios by cache level
    memory_hits: int = 0
    redis_hits: int = 0
    database_hits: int = 0
    
    def get_hit_ratio(self) -> float:
        """Calculate overall cache hit ratio."""
        total_requests = self.cache_hits + self.cache_misses
        return (self.cache_hits / total_requests * 100) if total_requests > 0 else 0.0
    
    def get_memory_hit_ratio(self) -> float:
        """Calculate memory cache hit ratio."""
        total_hits = self.memory_hits + self.redis_hits + self.database_hits
        return (self.memory_hits / total_hits * 100) if total_hits > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_refreshes": self.cache_refreshes,
            "cache_evictions": self.cache_evictions,
            "hit_ratio_percent": round(self.get_hit_ratio(), 2),
            "memory_hit_ratio_percent": round(self.get_memory_hit_ratio(), 2),
            "avg_retrieval_time_ms": round(self.avg_retrieval_time_ms, 2),
            "max_retrieval_time_ms": round(self.max_retrieval_time_ms, 2),
            "min_retrieval_time_ms": round(self.min_retrieval_time_ms, 2) if self.min_retrieval_time_ms != float('inf') else 0.0
        }


class FastRiskCache:
    """
    High-performance risk cache for fast lane execution decisions.
    
    Features:
    - Multi-tier caching (Memory -> Redis -> Database)
    - Sub-50ms risk score retrieval for cached data
    - Intelligent cache warming based on trading patterns
    - Risk data staleness detection and background refresh
    - LRU eviction with access pattern optimization
    - Emergency override system for known threats
    - Performance monitoring and optimization
    """
    
    def __init__(self, chain_id: int):
        """
        Initialize fast risk cache for specific chain.
        
        Args:
            chain_id: Blockchain network identifier
        """
        self.chain_id = chain_id
        self.logger = logging.getLogger(f"{__name__}.chain_{chain_id}")
        
        # Multi-tier cache storage
        self.memory_cache: Dict[str, RiskCacheEntry] = {}
        self.access_order: deque = deque()  # For LRU eviction
        self.redis_client: Optional[redis.Redis] = None
        
        # Cache configuration
        self.max_memory_entries = 10000  # Maximum entries in memory cache
        self.default_ttl_hours = 1       # Default cache TTL
        self.stale_threshold_minutes = 30 # Consider data stale after this time
        self.refresh_threshold_minutes = 45 # Background refresh trigger
        
        # Performance tracking
        self.statistics = CacheStatistics()
        self.retrieval_times: deque = deque(maxlen=1000)  # Recent retrieval times
        
        # Cache warming and patterns
        self.access_patterns: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.warming_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.refresh_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        
        # Emergency overrides
        self.blacklisted_tokens: Set[str] = set()
        self.whitelisted_tokens: Set[str] = set()
        self.emergency_overrides: Dict[str, Dict[str, Any]] = {}
        
        # Background tasks
        self.is_active = False
        self.warming_task: Optional[asyncio.Task] = None
        self.refresh_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
        self.stats_task: Optional[asyncio.Task] = None
        
        # Redis cache keys
        self.cache_key_prefix = f"fast_risk_cache:{chain_id}"
        self.blacklist_key = f"{self.cache_key_prefix}:blacklist"
        self.whitelist_key = f"{self.cache_key_prefix}:whitelist"
        
        self.logger.info(f"Fast risk cache initialized for chain {chain_id}")
    
    async def start(self) -> bool:
        """
        Start the fast risk cache with background tasks.
        
        Returns:
            True if started successfully, False otherwise
        """
        try:
            # Initialize Redis connection
            self.redis_client = redis.Redis.from_url(
                config.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            
            # Test connection
            await self.redis_client.ping()
            
            # Load emergency lists from Redis
            await self._load_emergency_lists()
            
            # Start background tasks
            self.warming_task = asyncio.create_task(self._cache_warming_worker())
            self.refresh_task = asyncio.create_task(self._cache_refresh_worker())
            self.cleanup_task = asyncio.create_task(self._cache_cleanup_worker())
            self.stats_task = asyncio.create_task(self._statistics_worker())
            
            self.is_active = True
            
            self.logger.info("Fast risk cache started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start fast risk cache: {e}")
            return False
    
    async def stop(self) -> None:
        """Stop the fast risk cache and cleanup resources."""
        self.is_active = False
        
        # Cancel background tasks
        tasks_to_cancel = [
            self.warming_task,
            self.refresh_task,
            self.cleanup_task,
            self.stats_task
        ]
        
        for task in tasks_to_cancel:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Save emergency lists to Redis
        await self._save_emergency_lists()
        
        # Close Redis connection
        if self.redis_client:
            await self.redis_client.close()
        
        self.logger.info("Fast risk cache stopped")
    
    async def get_token_risk(self, token_address: str) -> Optional[Dict[str, Any]]:
        """
        Get risk data for token with fast retrieval (target <50ms).
        
        Args:
            token_address: Token contract address
            
        Returns:
            Risk data dictionary or None if not available
        """
        start_time = time.perf_counter()
        token_address = token_address.lower()
        
        try:
            # Check emergency overrides first
            override = await self._check_emergency_overrides(token_address)
            if override:
                retrieval_time = (time.perf_counter() - start_time) * 1000
                self._update_retrieval_stats(retrieval_time, CacheLevel.MEMORY)
                return override
            
            # Try memory cache first (fastest)
            cache_key = f"risk:{self.chain_id}:{token_address}"
            
            if cache_key in self.memory_cache:
                entry = self.memory_cache[cache_key]
                entry.update_access()
                
                # Move to front of access order for LRU
                if cache_key in self.access_order:
                    self.access_order.remove(cache_key)
                self.access_order.append(cache_key)
                
                retrieval_time = (time.perf_counter() - start_time) * 1000
                self._update_retrieval_stats(retrieval_time, RiskCacheLevel.MEMORY)
                
                # Trigger background refresh if stale
                if entry.is_stale(self.stale_threshold_minutes):
                    await self._queue_for_refresh(token_address)
                
                self.logger.debug(f"Memory cache hit for {token_address} ({retrieval_time:.1f}ms)")
                return self._entry_to_risk_data(entry)
            
            # Try Redis cache (fast)
            if self.redis_client:
                redis_data = await self.redis_client.get(cache_key)
                if redis_data:
                    try:
                        entry_data = json.loads(redis_data)
                        entry = RiskCacheEntry.from_dict(entry_data)
                        
                        # Store in memory cache for next time
                        await self._store_in_memory_cache(entry)
                        
                        retrieval_time = (time.perf_counter() - start_time) * 1000
                        self._update_retrieval_stats(retrieval_time, RiskCacheLevel.REDIS)
                        
                        # Trigger background refresh if stale
                        if entry.is_stale(self.stale_threshold_minutes):
                            await self._queue_for_refresh(token_address)
                        
                        self.logger.debug(f"Redis cache hit for {token_address} ({retrieval_time:.1f}ms)")
                        return self._entry_to_risk_data(entry)
                        
                    except (json.JSONDecodeError, Exception) as e:
                        self.logger.error(f"Failed to deserialize Redis cache entry: {e}")
            
            # Cache miss - queue for warming if this token is frequently accessed
            await self._record_access_pattern(token_address)
            await self._queue_for_warming(token_address)
            
            retrieval_time = (time.perf_counter() - start_time) * 1000
            self.statistics.cache_misses += 1
            
            self.logger.debug(f"Cache miss for {token_address} ({retrieval_time:.1f}ms)")
            return None
            
        except Exception as e:
            self.logger.error(f"Error retrieving risk data for {token_address}: {e}")
            return None
    
    async def store_risk_data(
        self, 
        token_address: str, 
        risk_data: Dict[str, Any],
        source: str = "risk_engine",
        ttl_hours: Optional[int] = None
    ) -> bool:
        """
        Store risk data in cache with specified TTL.
        
        Args:
            token_address: Token contract address
            risk_data: Risk assessment data
            source: Data source identifier
            ttl_hours: Cache TTL in hours (uses default if None)
            
        Returns:
            True if stored successfully, False otherwise
        """
        try:
            token_address = token_address.lower()
            ttl = ttl_hours or self.default_ttl_hours
            
            # Create cache entry
            entry = RiskCacheEntry(
                token_address=token_address,
                chain_id=self.chain_id,
                overall_risk_score=Decimal(str(risk_data.get("overall_risk_score", 50))),
                risk_level=RiskLevel(risk_data.get("risk_level", "MEDIUM")),
                risk_categories={
                    RiskCategory(cat): Decimal(str(score))
                    for cat, score in risk_data.get("risk_categories", {}).items()
                },
                is_honeypot=risk_data.get("is_honeypot", False),
                is_scam=risk_data.get("is_scam", False),
                is_verified=risk_data.get("is_verified", False),
                is_blacklisted=risk_data.get("is_blacklisted", False),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl),
                source=source,
                confidence=risk_data.get("confidence", 1.0)
            )
            
            # Store in memory cache
            await self._store_in_memory_cache(entry)
            
            # Store in Redis cache
            if self.redis_client:
                cache_key = entry.get_cache_key()
                try:
                    await self.redis_client.setex(
                        cache_key,
                        ttl * 3600,  # Convert to seconds
                        json.dumps(entry.to_dict())
                    )
                except Exception as e:
                    self.logger.error(f"Failed to store in Redis cache: {e}")
            
            self.logger.debug(f"Stored risk data for {token_address} (TTL: {ttl}h)")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to store risk data for {token_address}: {e}")
            return False
    
    async def invalidate_token(self, token_address: str) -> bool:
        """
        Invalidate cached risk data for specific token.
        
        Args:
            token_address: Token to invalidate
            
        Returns:
            True if invalidated successfully, False otherwise
        """
        try:
            token_address = token_address.lower()
            cache_key = f"risk:{self.chain_id}:{token_address}"
            
            # Remove from memory cache
            if cache_key in self.memory_cache:
                del self.memory_cache[cache_key]
                if cache_key in self.access_order:
                    self.access_order.remove(cache_key)
            
            # Remove from Redis cache
            if self.redis_client:
                await self.redis_client.delete(cache_key)
            
            self.logger.info(f"Invalidated cache for token {token_address}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to invalidate cache for {token_address}: {e}")
            return False
    
    async def add_to_blacklist(self, token_address: str, reason: str = "") -> bool:
        """
        Add token to emergency blacklist.
        
        Args:
            token_address: Token to blacklist
            reason: Reason for blacklisting
            
        Returns:
            True if added successfully, False otherwise
        """
        try:
            token_address = token_address.lower()
            self.blacklisted_tokens.add(token_address)
            
            # Store emergency override
            self.emergency_overrides[token_address] = {
                "is_blacklisted": True,
                "is_scam": True,
                "overall_risk_score": 100,
                "risk_level": "CRITICAL",
                "reason": reason,
                "added_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Invalidate existing cache entry
            await self.invalidate_token(token_address)
            
            # Save to Redis
            if self.redis_client:
                await self.redis_client.sadd(self.blacklist_key, token_address)
            
            self.logger.warning(f"Added token {token_address} to blacklist: {reason}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add {token_address} to blacklist: {e}")
            return False
    
    async def remove_from_blacklist(self, token_address: str) -> bool:
        """
        Remove token from emergency blacklist.
        
        Args:
            token_address: Token to remove from blacklist
            
        Returns:
            True if removed successfully, False otherwise
        """
        try:
            token_address = token_address.lower()
            self.blacklisted_tokens.discard(token_address)
            
            # Remove emergency override
            self.emergency_overrides.pop(token_address, None)
            
            # Invalidate cache to force refresh
            await self.invalidate_token(token_address)
            
            # Remove from Redis
            if self.redis_client:
                await self.redis_client.srem(self.blacklist_key, token_address)
            
            self.logger.info(f"Removed token {token_address} from blacklist")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to remove {token_address} from blacklist: {e}")
            return False
    
    async def get_cache_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive cache performance statistics.
        
        Returns:
            Dictionary containing cache statistics
        """
        memory_usage = len(self.memory_cache)
        memory_usage_percent = (memory_usage / self.max_memory_entries * 100)
        
        return {
            "cache": "fast_risk_cache",
            "chain_id": self.chain_id,
            "is_active": self.is_active,
            "memory_cache": {
                "entries": memory_usage,
                "max_entries": self.max_memory_entries,
                "usage_percent": round(memory_usage_percent, 2)
            },
            "emergency_lists": {
                "blacklisted_tokens": len(self.blacklisted_tokens),
                "whitelisted_tokens": len(self.whitelisted_tokens),
                "emergency_overrides": len(self.emergency_overrides)
            },
            "configuration": {
                "default_ttl_hours": self.default_ttl_hours,
                "stale_threshold_minutes": self.stale_threshold_minutes,
                "refresh_threshold_minutes": self.refresh_threshold_minutes,
                "max_memory_entries": self.max_memory_entries
            },
            "performance": self.statistics.to_dict(),
            "queues": {
                "warming_queue_size": self.warming_queue.qsize(),
                "refresh_queue_size": self.refresh_queue.qsize()
            }
        }
    
    # =========================================================================
    # PRIVATE METHODS - Core Logic
    # =========================================================================
    
    async def _store_in_memory_cache(self, entry: RiskCacheEntry) -> None:
        """Store entry in memory cache with LRU eviction."""
        cache_key = entry.get_cache_key()
        
        # Check if cache is full and needs eviction
        if len(self.memory_cache) >= self.max_memory_entries:
            await self._evict_lru_entries(1)
        
        # Store entry
        self.memory_cache[cache_key] = entry
        
        # Update access order
        if cache_key in self.access_order:
            self.access_order.remove(cache_key)
        self.access_order.append(cache_key)
    
    async def _evict_lru_entries(self, count: int) -> None:
        """Evict least recently used entries from memory cache."""
        evicted = 0
        
        while evicted < count and self.access_order:
            lru_key = self.access_order.popleft()
            if lru_key in self.memory_cache:
                del self.memory_cache[lru_key]
                evicted += 1
                self.statistics.cache_evictions += 1
        
        if evicted > 0:
            self.logger.debug(f"Evicted {evicted} LRU entries from memory cache")
    
    async def _check_emergency_overrides(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Check for emergency overrides for token."""
        if token_address in self.blacklisted_tokens:
            return {
                "is_blacklisted": True,
                "is_scam": True,
                "overall_risk_score": 100,
                "risk_level": "CRITICAL",
                "source": "emergency_blacklist"
            }
        
        if token_address in self.whitelisted_tokens:
            return {
                "is_verified": True,
                "overall_risk_score": 10,
                "risk_level": "LOW",
                "source": "emergency_whitelist"
            }
        
        if token_address in self.emergency_overrides:
            return self.emergency_overrides[token_address]
        
        return None
    
    def _entry_to_risk_data(self, entry: RiskCacheEntry) -> Dict[str, Any]:
        """Convert cache entry to risk data dictionary."""
        return {
            "overall_risk_score": float(entry.overall_risk_score),
            "risk_level": entry.risk_level.value,
            "risk_categories": {
                cat.value: float(score)
                for cat, score in entry.risk_categories.items()
            },
            "is_honeypot": entry.is_honeypot,
            "is_scam": entry.is_scam,
            "is_verified": entry.is_verified,
            "is_blacklisted": entry.is_blacklisted,
            "source": entry.source,
            "confidence": entry.confidence,
            "cached_at": entry.cached_at.isoformat(),
            "cache_level": entry.cache_level.value
        }
    
    def _update_retrieval_stats(self, retrieval_time_ms: float, cache_level: RiskCacheLevel) -> None:
        """Update retrieval performance statistics."""
        self.statistics.cache_hits += 1
        
        if cache_level == RiskCacheLevel.MEMORY:
            self.statistics.memory_hits += 1
        elif cache_level == RiskCacheLevel.REDIS:
            self.statistics.redis_hits += 1
        else:
            self.statistics.database_hits += 1
        
        # Update timing stats
        self.retrieval_times.append(retrieval_time_ms)
        
        if retrieval_time_ms > self.statistics.max_retrieval_time_ms:
            self.statistics.max_retrieval_time_ms = retrieval_time_ms
        
        if retrieval_time_ms < self.statistics.min_retrieval_time_ms:
            self.statistics.min_retrieval_time_ms = retrieval_time_ms
        
        # Calculate rolling average
        if self.retrieval_times:
            self.statistics.avg_retrieval_time_ms = statistics.mean(self.retrieval_times)
    
    async def _record_access_pattern(self, token_address: str) -> None:
        """Record access pattern for cache warming decisions."""
        self.access_patterns[token_address].append(datetime.now(timezone.utc))
    
    async def _queue_for_warming(self, token_address: str) -> None:
        """Queue token for cache warming if frequently accessed."""
        try:
            if self.warming_queue.full():
                return
            
            # Check access frequency
            accesses = self.access_patterns[token_address]
            if len(accesses) >= 3:  # Accessed 3+ times
                recent_accesses = [
                    access for access in accesses 
                    if (datetime.now(timezone.utc) - access).total_seconds() < 300  # Last 5 minutes
                ]
                
                if len(recent_accesses) >= 2:  # 2+ recent accesses
                    await self.warming_queue.put(token_address)
        
        except asyncio.QueueFull:
            pass  # Queue full, skip warming
        except Exception as e:
            self.logger.error(f"Error queuing for warming: {e}")
    
    async def _queue_for_refresh(self, token_address: str) -> None:
        """Queue token for background refresh."""
        try:
            if not self.refresh_queue.full():
                await self.refresh_queue.put(token_address)
        except asyncio.QueueFull:
            pass  # Queue full, skip refresh
        except Exception as e:
            self.logger.error(f"Error queuing for refresh: {e}")
    
    # =========================================================================
    # PRIVATE METHODS - Background Tasks
    # =========================================================================
    
    async def _cache_warming_worker(self) -> None:
        """Background task for cache warming based on access patterns."""
        self.logger.info("Started cache warming worker")
        
        while self.is_active:
            try:
                # Get token to warm (with timeout)
                token_address = await asyncio.wait_for(
                    self.warming_queue.get(), 
                    timeout=10.0
                )
                
                # TODO: Implement actual risk data fetching from risk engine
                # For now, simulate warming
                self.logger.debug(f"Would warm cache for token: {token_address}")
                
                await asyncio.sleep(0.1)  # Prevent tight loop
                
            except asyncio.TimeoutError:
                continue  # Normal timeout, check is_active
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in cache warming worker: {e}")
                await asyncio.sleep(1)
        
        self.logger.info("Cache warming worker stopped")
    
    async def _cache_refresh_worker(self) -> None:
        """Background task for refreshing stale cache entries."""
        self.logger.info("Started cache refresh worker")
        
        while self.is_active:
            try:
                # Get token to refresh (with timeout)
                token_address = await asyncio.wait_for(
                    self.refresh_queue.get(),
                    timeout=30.0
                )
                
                # TODO: Implement actual risk data refresh
                # For now, simulate refresh
                self.statistics.cache_refreshes += 1
                self.logger.debug(f"Would refresh cache for token: {token_address}")
                
                await asyncio.sleep(0.1)  # Prevent tight loop
                
            except asyncio.TimeoutError:
                continue  # Normal timeout, check is_active
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in cache refresh worker: {e}")
                await asyncio.sleep(5)
        
        self.logger.info("Cache refresh worker stopped")
    
    async def _cache_cleanup_worker(self) -> None:
        """Background task for cleaning up expired cache entries."""
        self.logger.info("Started cache cleanup worker")
        
        while self.is_active:
            try:
                current_time = datetime.now(timezone.utc)
                expired_keys = []
                
                # Find expired entries in memory cache
                for cache_key, entry in self.memory_cache.items():
                    if entry.is_expired():
                        expired_keys.append(cache_key)
                
                # Remove expired entries
                for cache_key in expired_keys:
                    del self.memory_cache[cache_key]
                    if cache_key in self.access_order:
                        self.access_order.remove(cache_key)
                
                if expired_keys:
                    self.logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
                
                await asyncio.sleep(300)  # Run every 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in cache cleanup worker: {e}")
                await asyncio.sleep(300)
        
        self.logger.info("Cache cleanup worker stopped")
    
    async def _statistics_worker(self) -> None:
        """Background task for updating cache statistics."""
        self.logger.info("Started statistics worker")
        
        while self.is_active:
            try:
                # Log performance metrics every minute
                await asyncio.sleep(60)
                
                stats = await self.get_cache_statistics()
                self.logger.info(
                    f"Cache Performance - Hit Ratio: {stats['performance']['hit_ratio_percent']:.1f}%, "
                    f"Memory: {stats['memory_cache']['entries']}/{stats['memory_cache']['max_entries']} entries, "
                    f"Avg Retrieval: {stats['performance']['avg_retrieval_time_ms']:.1f}ms"
                )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in statistics worker: {e}")
                await asyncio.sleep(60)
        
        self.logger.info("Statistics worker stopped")
    
    # =========================================================================
    # PRIVATE METHODS - State Persistence
    # =========================================================================
    
    async def _load_emergency_lists(self) -> None:
        """Load emergency blacklist and whitelist from Redis."""
        if not self.redis_client:
            return
        
        try:
            # Load blacklist
            blacklisted = await self.redis_client.smembers(self.blacklist_key)
            self.blacklisted_tokens.update(blacklisted)
            
            # Load whitelist
            whitelisted = await self.redis_client.smembers(self.whitelist_key)
            self.whitelisted_tokens.update(whitelisted)
            
            self.logger.info(
                f"Loaded emergency lists - Blacklisted: {len(self.blacklisted_tokens)}, "
                f"Whitelisted: {len(self.whitelisted_tokens)}"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to load emergency lists from Redis: {e}")
    
    async def _save_emergency_lists(self) -> None:
        """Save emergency blacklist and whitelist to Redis."""
        if not self.redis_client:
            return
        
        try:
            # Save blacklist
            if self.blacklisted_tokens:
                await self.redis_client.delete(self.blacklist_key)
                await self.redis_client.sadd(self.blacklist_key, *self.blacklisted_tokens)
            
            # Save whitelist
            if self.whitelisted_tokens:
                await self.redis_client.delete(self.whitelist_key)
                await self.redis_client.sadd(self.whitelist_key, *self.whitelisted_tokens)
            
            self.logger.info("Saved emergency lists to Redis")
            
        except Exception as e:
            self.logger.error(f"Failed to save emergency lists to Redis: {e}")