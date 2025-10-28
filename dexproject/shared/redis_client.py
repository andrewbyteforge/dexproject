"""
Redis pub/sub client for communication between async engine and Django backend.

This module handles Redis connections, pub/sub messaging, and caching for
real-time communication in the DEX trading bot system.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, TimeoutError

from .constants import REDIS_CHANNELS, REDIS_KEYS
from .schemas import BaseMessage, serialize_message, deserialize_message


logger = logging.getLogger(__name__)


# =============================================================================
# REDIS CLIENT CLASS
# =============================================================================

class RedisClient:
    """
    Async Redis client for pub/sub messaging and caching.
    
    Provides the communication bridge between the async engine and Django backend,
    handling Redis pub/sub, caching, and health monitoring.
    """
    
    def __init__(
        self,
        redis_url: str,
        max_connections: int = 20,
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
        health_check_interval: int = 30
    ):
        """
        Initialize Redis client.
        
        Args:
            redis_url: Redis connection URL (from Django settings)
            max_connections: Maximum connection pool size
            retry_attempts: Number of retry attempts for failed operations
            retry_delay: Delay between retry attempts in seconds
            health_check_interval: Health check interval in seconds
        """
        self.redis_url = redis_url
        self.max_connections = max_connections
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.health_check_interval = health_check_interval
        
        # Redis instances
        self.redis: Optional[Redis] = None
        self.pubsub_redis: Optional[Redis] = None
        self.pubsub = None
        
        # State tracking
        self._connected = False
        self._subscriptions: Dict[str, Callable] = {}
        self._connection_lock = asyncio.Lock()
        
        # Background tasks
        self._message_listener_task: Optional[asyncio.Task] = None
        self._health_check_task: Optional[asyncio.Task] = None
        
        # Statistics
        self._messages_sent = 0
        self._messages_received = 0
        self._connection_errors = 0
        self._last_heartbeat = None
        
        self.logger = logger.getChild(self.__class__.__name__)
    
    async def connect(self) -> None:
        """Establish Redis connection and start background tasks."""
        async with self._connection_lock:
            if self._connected:
                self.logger.info("Redis client already connected")
                return
            
            try:
                # Create Redis connection pool
                self.redis = redis.from_url(
                    self.redis_url,
                    max_connections=self.max_connections,
                    retry_on_timeout=True,
                    decode_responses=True,
                    socket_keepalive=True,
                    socket_keepalive_options={},
                )
                
                # Create separate connection for pub/sub
                self.pubsub_redis = redis.from_url(
                    self.redis_url,
                    max_connections=self.max_connections,
                    retry_on_timeout=True,
                    decode_responses=True,
                    socket_keepalive=True,
                )
                
                # Test connections
                await self.redis.ping()
                await self.pubsub_redis.ping()
                
                # Initialize pub/sub
                self.pubsub = self.pubsub_redis.pubsub()
                
                self._connected = True
                self._last_heartbeat = datetime.now(timezone.utc)
                
                self.logger.info("Redis client connected successfully")
                
                # Start background tasks
                await self._start_background_tasks()
                
            except Exception as e:
                self.logger.error(f"Failed to connect to Redis: {e}")
                await self._cleanup_connections()
                self._connection_errors += 1
                raise
    
    async def disconnect(self) -> None:
        """Disconnect from Redis and cleanup resources."""
        async with self._connection_lock:
            if not self._connected:
                return
            
            self.logger.info("Disconnecting Redis client...")
            self._connected = False
            
            # Stop background tasks
            await self._stop_background_tasks()
            
            # Cleanup connections
            await self._cleanup_connections()
            
            self.logger.info("Redis client disconnected")
    
    def is_connected(self) -> bool:
        """Check if Redis client is connected."""
        return self._connected
    
    async def _cleanup_connections(self) -> None:
        """Clean up Redis connections."""
        try:
            if self.pubsub:
                await self.pubsub.close()
                self.pubsub = None
            
            if self.pubsub_redis:
                await self.pubsub_redis.close()
                self.pubsub_redis = None
            
            if self.redis:
                await self.redis.close()
                self.redis = None
                
        except Exception as e:
            self.logger.error(f"Error cleaning up Redis connections: {e}")
    
    async def _start_background_tasks(self) -> None:
        """Start background tasks for message listening and health checks."""
        self._message_listener_task = asyncio.create_task(self._message_listener())
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        self.logger.info("Redis background tasks started")
    
    async def _stop_background_tasks(self) -> None:
        """Stop background tasks."""
        tasks = [self._message_listener_task, self._health_check_task]
        
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self._message_listener_task = None
        self._health_check_task = None
        
        self.logger.info("Redis background tasks stopped")
    
    # =========================================================================
    # PUB/SUB OPERATIONS
    # =========================================================================
    
    async def subscribe(self, channel: str, handler: Callable[[dict], None]) -> None:
        """
        Subscribe to a Redis channel.
        
        Args:
            channel: Channel name to subscribe to
            handler: Async function to handle messages
        """
        if not self._connected:
            raise RuntimeError("Redis client not connected")
        
        try:
            await self.pubsub.subscribe(channel)
            self._subscriptions[channel] = handler
            
            self.logger.info(f"Subscribed to channel: {channel}")
            
        except Exception as e:
            self.logger.error(f"Failed to subscribe to channel {channel}: {e}")
            raise
    
    async def unsubscribe(self, channel: str) -> None:
        """
        Unsubscribe from a Redis channel.
        
        Args:
            channel: Channel name to unsubscribe from
        """
        if not self._connected:
            return
        
        try:
            await self.pubsub.unsubscribe(channel)
            self._subscriptions.pop(channel, None)
            
            self.logger.info(f"Unsubscribed from channel: {channel}")
            
        except Exception as e:
            self.logger.error(f"Failed to unsubscribe from channel {channel}: {e}")
    
    async def publish(self, channel: str, data: Union[dict, BaseMessage, str]) -> None:
        """
        Publish a message to a Redis channel.
        
        Args:
            channel: Channel name to publish to
            data: Message data (BaseMessage, dict, or string)
        """
        if not self._connected:
            raise RuntimeError("Redis client not connected")
        
        try:
            # Serialize data based on type
            if isinstance(data, BaseMessage):
                message = serialize_message(data)
            elif isinstance(data, dict):
                # Add timestamp if not present
                if 'timestamp' not in data:
                    data['timestamp'] = datetime.now(timezone.utc).isoformat()
                message = json.dumps(data, default=str)
            else:
                message = str(data)
            
            # Publish with retry logic
            await self._retry_operation(
                self.redis.publish, channel, message
            )
            
            self._messages_sent += 1
            self.logger.debug(f"Published message to {channel}: {len(message)} bytes")
            
        except Exception as e:
            self.logger.error(f"Failed to publish to channel {channel}: {e}")
            raise
    
    async def publish_to_django(self, message: BaseMessage) -> None:
        """
        Publish a message from engine to Django.
        
        Args:
            message: BaseMessage to send to Django
        """
        from .constants import get_redis_channel
        
        # Determine the correct channel based on message type
        channel = get_redis_channel(message.message_type)
        await self.publish(channel, message)
    
    async def _message_listener(self) -> None:
        """Background task to listen for Redis pub/sub messages."""
        self.logger.info("Redis message listener started")
    
        while self._connected:
            try:
                # Only attempt to get messages if we have active subscriptions
                if not self._subscriptions:
                    await asyncio.sleep(1.0)
                    continue
                
                message = await self.pubsub.get_message(timeout=1.0)
                
                if message is None:
                    continue
                
                # Skip subscription confirmation messages
                if message['type'] != 'message':
                    continue
                
                channel = message['channel']
                data = message['data']
                
                # Get handler for this channel
                handler = self._subscriptions.get(channel)
                if not handler:
                    self.logger.warning(f"No handler for channel: {channel}")
                    continue
                
                # Parse JSON data
                try:
                    parsed_data = json.loads(data) if isinstance(data, str) else data
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to parse message from {channel}: {e}")
                    continue
                
                # Handle message in background task
                asyncio.create_task(self._handle_message_safely(handler, parsed_data, channel))
                self._messages_received += 1
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in message listener: {e}")
                await asyncio.sleep(1)
        
        self.logger.info("Redis message listener stopped")
    
    async def _handle_message_safely(
        self, 
        handler: Callable[[dict], None], 
        data: dict, 
        channel: str
    ) -> None:
        """Safely handle a message with error isolation."""
        try:
            await handler(data)
        except Exception as e:
            self.logger.error(f"Error handling message from {channel}: {e}")
    
    # =========================================================================
    # CACHING OPERATIONS (for Engine ↔ Django data sharing)
    # =========================================================================
    
    async def set_engine_status(self, engine_id: str, status_data: dict, ttl: int = 300) -> None:
        """
        Set engine status in Redis cache.
        
        Args:
            engine_id: Engine instance ID
            status_data: Status information
            ttl: Time to live in seconds
        """
        key = f"{REDIS_KEYS['engine_status']}:{engine_id}"
        await self.set(key, status_data, expire=ttl)
    
    async def get_engine_status(self, engine_id: str) -> Optional[dict]:
        """
        Get engine status from Redis cache.
        
        Args:
            engine_id: Engine instance ID
            
        Returns:
            Status data or None if not found
        """
        key = f"{REDIS_KEYS['engine_status']}:{engine_id}"
        return await self.get(key)
    
    async def set_risk_cache(self, token_address: str, risk_data: dict, ttl: int = 3600) -> None:
        """
        Cache risk assessment results.
        
        Args:
            token_address: Token contract address
            risk_data: Risk assessment data
            ttl: Time to live in seconds (default 1 hour)
        """
        key = f"{REDIS_KEYS['risk_cache']}:{token_address.lower()}"
        await self.set(key, risk_data, expire=ttl)
    
    async def get_risk_cache(self, token_address: str) -> Optional[dict]:
        """
        Get cached risk assessment results.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Cached risk data or None if not found
        """
        key = f"{REDIS_KEYS['risk_cache']}:{token_address.lower()}"
        return await self.get(key)
    
    async def set_price_cache(self, token_address: str, price_data: dict, ttl: int = 60) -> None:
        """
        Cache token price data.
        
        Args:
            token_address: Token contract address
            price_data: Price information
            ttl: Time to live in seconds (default 1 minute)
        """
        key = f"{REDIS_KEYS['price_cache']}:{token_address.lower()}"
        await self.set(key, price_data, expire=ttl)
    
    async def get_price_cache(self, token_address: str) -> Optional[dict]:
        """
        Get cached token price data.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Cached price data or None if not found
        """
        key = f"{REDIS_KEYS['price_cache']}:{token_address.lower()}"
        return await self.get(key)
    
    # =========================================================================
    # GENERIC CACHING OPERATIONS
    # =========================================================================
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        expire: Optional[int] = None
    ) -> None:
        """
        Set a key-value pair in Redis.
        
        Args:
            key: Redis key
            value: Value to store (will be JSON serialized if dict/list)
            expire: Expiration time in seconds
        """
        if not self._connected:
            raise RuntimeError("Redis client not connected")
        
        try:
            # Serialize complex objects
            if isinstance(value, (dict, list)):
                serialized_value = json.dumps(value, default=str)
            else:
                serialized_value = str(value)
            
            await self._retry_operation(
                self.redis.set, key, serialized_value, ex=expire
            )
            
            self.logger.debug(f"Set key: {key} (expire: {expire}s)")
            
        except Exception as e:
            self.logger.error(f"Failed to set key {key}: {e}")
            raise
    
    async def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from Redis.
        
        Args:
            key: Redis key
            default: Default value if key doesn't exist
            
        Returns:
            Stored value or default
        """
        if not self._connected:
            raise RuntimeError("Redis client not connected")
        
        try:
            value = await self._retry_operation(self.redis.get, key)
            
            if value is None:
                return default
            
            # Try to parse as JSON, fall back to string
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
                
        except Exception as e:
            self.logger.error(f"Failed to get key {key}: {e}")
            return default
    
    async def delete(self, key: str) -> bool:
        """
        Delete a key from Redis.
        
        Args:
            key: Redis key to delete
            
        Returns:
            True if key was deleted, False if it didn't exist
        """
        if not self._connected:
            raise RuntimeError("Redis client not connected")
        
        try:
            result = await self._retry_operation(self.redis.delete, key)
            self.logger.debug(f"Deleted key: {key}")
            return bool(result)
            
        except Exception as e:
            self.logger.error(f"Failed to delete key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in Redis.
        
        Args:
            key: Redis key to check
            
        Returns:
            True if key exists, False otherwise
        """
        if not self._connected:
            raise RuntimeError("Redis client not connected")
        
        try:
            result = await self._retry_operation(self.redis.exists, key)
            return bool(result)
            
        except Exception as e:
            self.logger.error(f"Failed to check key existence {key}: {e}")
            return False
    
    # =========================================================================
    # UTILITY OPERATIONS
    # =========================================================================
    
    async def _retry_operation(self, operation, *args, **kwargs) -> Any:
        """
        Retry a Redis operation with exponential backoff.
        
        Args:
            operation: Redis operation to execute
            *args: Positional arguments for the operation
            **kwargs: Keyword arguments for the operation
            
        Returns:
            Operation result
        """
        last_exception = None
        
        for attempt in range(self.retry_attempts):
            try:
                return await operation(*args, **kwargs)
            except (ConnectionError, TimeoutError) as e:
                last_exception = e
                self._connection_errors += 1
                
                if attempt < self.retry_attempts - 1:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    self.logger.warning(
                        f"Redis operation failed (attempt {attempt + 1}/{self.retry_attempts}), "
                        f"retrying in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(f"Redis operation failed after {self.retry_attempts} attempts: {e}")
        
        # Re-raise the last exception
        raise last_exception
    
    async def _health_check_loop(self) -> None:
        """Background task to perform periodic health checks."""
        self.logger.info("Redis health check loop started")
        
        while self._connected:
            try:
                # Ping Redis to check connection health
                await self.redis.ping()
                self._last_heartbeat = datetime.now(timezone.utc)
                await asyncio.sleep(self.health_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Redis health check failed: {e}")
                self._connection_errors += 1
                # Don't mark as disconnected immediately, let retry logic handle it
                await asyncio.sleep(5)
        
        self.logger.info("Redis health check loop stopped")
    
    async def get_connection_info(self) -> Dict[str, Any]:
        """
        Get Redis connection information and statistics.
        
        Returns:
            Dictionary with connection details
        """
        if not self._connected:
            return {
                "connected": False,
                "error": "Not connected"
            }
        
        try:
            info = await self.redis.info()
            
            return {
                "connected": True,
                "redis_version": info.get('redis_version'),
                "connected_clients": info.get('connected_clients'),
                "used_memory_human": info.get('used_memory_human'),
                "uptime_in_seconds": info.get('uptime_in_seconds'),
                "subscriptions": list(self._subscriptions.keys()),
                "statistics": {
                    "messages_sent": self._messages_sent,
                    "messages_received": self._messages_received,
                    "connection_errors": self._connection_errors,
                    "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
                }
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get Redis info: {e}")
            return {
                "connected": self._connected,
                "error": str(e),
                "statistics": {
                    "messages_sent": self._messages_sent,
                    "messages_received": self._messages_received,
                    "connection_errors": self._connection_errors,
                }
            }
    
    async def flush_cache(self, pattern: Optional[str] = None) -> int:
        """
        Flush cache entries, optionally matching a pattern.
        
        Args:
            pattern: Key pattern to match (e.g., "dex_bot:*")
            
        Returns:
            Number of keys deleted
        """
        if not self._connected:
            raise RuntimeError("Redis client not connected")
        
        try:
            if pattern:
                # Get keys matching pattern
                keys = await self.redis.keys(pattern)
                if keys:
                    deleted_count = await self.redis.delete(*keys)
                else:
                    deleted_count = 0
            else:
                # Flush entire database (use with caution!)
                await self.redis.flushdb()
                deleted_count = -1  # Unknown count for full flush
            
            self.logger.info(f"Flushed cache: {deleted_count} keys deleted")
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Failed to flush cache: {e}")
            raise
    
    # =========================================================================
    # ENGINE-SPECIFIC HELPERS
    # =========================================================================
    
    async def notify_engine_startup(self, engine_id: str, config: dict) -> None:
        """
        Notify Django that the engine has started.
        
        Args:
            engine_id: Engine instance ID
            config: Engine configuration
        """
        startup_message = {
            "event": "engine_startup",
            "engine_id": engine_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "config": config
        }
        
        await self.publish(REDIS_CHANNELS['system_events'], startup_message)
        await self.set_engine_status(engine_id, {
            "status": "starting",
            "startup_time": startup_message["timestamp"],
            "config": config
        })
    
    async def notify_engine_shutdown(self, engine_id: str, reason: str = "normal") -> None:
        """
        Notify Django that the engine is shutting down.
        
        Args:
            engine_id: Engine instance ID
            reason: Shutdown reason
        """
        shutdown_message = {
            "event": "engine_shutdown",
            "engine_id": engine_id,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "statistics": {
                "messages_sent": self._messages_sent,
                "messages_received": self._messages_received,
                "connection_errors": self._connection_errors,
            }
        }
        
        await self.publish(REDIS_CHANNELS['system_events'], shutdown_message)
        await self.delete(f"{REDIS_KEYS['engine_status']}:{engine_id}")
    
    async def setup_engine_subscriptions(self, handlers: Dict[str, Callable]) -> None:
        """
        Set up standard subscriptions for engine.
        
        Args:
            handlers: Dictionary mapping channel names to handler functions
        """
        # Subscribe to channels that Django sends to Engine
        engine_channels = [
            REDIS_CHANNELS['comprehensive_risk_complete'],
            REDIS_CHANNELS['trading_config_update'],
            REDIS_CHANNELS['emergency_stop'],
            REDIS_CHANNELS['risk_profile_update'],
        ]
        
        for channel in engine_channels:
            handler = handlers.get(channel)
            if handler:
                await self.subscribe(channel, handler)
            else:
                self.logger.warning(f"No handler provided for channel: {channel}")
    
    async def setup_django_subscriptions(self, handlers: Dict[str, Callable]) -> None:
        """
        Set up standard subscriptions for Django.
        
        Args:
            handlers: Dictionary mapping channel names to handler functions
        """
        # Subscribe to channels that Engine sends to Django
        django_channels = [
            REDIS_CHANNELS['pair_discovery'],
            REDIS_CHANNELS['fast_risk_complete'],
            REDIS_CHANNELS['trading_decision'],
            REDIS_CHANNELS['trade_execution'],
            REDIS_CHANNELS['engine_status'],
            REDIS_CHANNELS['engine_alerts'],
        ]
        
        for channel in django_channels:
            handler = handlers.get(channel)
            if handler:
                await self.subscribe(channel, handler)
            else:
                self.logger.warning(f"No handler provided for channel: {channel}")


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def create_redis_client(
    redis_url: str = None, 
    use_django_settings: bool = True,
    **kwargs
) -> RedisClient:
    """
    Create and return a Redis client instance.
    
    Args:
        redis_url: Redis connection URL (if None, tries to get from Django settings)
        use_django_settings: Whether to use Django settings for Redis URL
        **kwargs: Additional configuration options
        
    Returns:
        Configured RedisClient instance
    """
    if redis_url is None and use_django_settings:
        try:
            from django.conf import settings
            redis_url = settings.REDIS_URL
        except ImportError:
            redis_url = 'redis://localhost:6379/0'
    elif redis_url is None:
        redis_url = 'redis://localhost:6379/0'
    
    return RedisClient(redis_url, **kwargs)


async def test_redis_connection(redis_url: str) -> bool:
    """
    Test Redis connection.
    
    Args:
        redis_url: Redis connection URL
        
    Returns:
        True if connection successful, False otherwise
    """
    client = create_redis_client(redis_url, use_django_settings=False)
    
    try:
        await client.connect()
        await client.disconnect()
        logger.info("Redis connection test successful")
        return True
    except Exception as e:
        logger.error(f"Redis connection test failed: {e}")
        return False


# =============================================================================
# DJANGO INTEGRATION HELPERS
# =============================================================================

def get_django_redis_client() -> RedisClient:
    """
    Get a Redis client configured with Django settings.
    
    Returns:
        RedisClient instance configured from Django settings
    """
    return create_redis_client(use_django_settings=True)


class DjangoRedisHandler:
    """
    Helper class for Django to handle Redis messages from the engine.
    
    This class provides a Django-friendly interface for handling
    Redis pub/sub messages from the async engine.
    """
    
    def __init__(self):
        """Initialize Django Redis handler."""
        self.redis_client = get_django_redis_client()
        self.logger = logger.getChild('DjangoRedisHandler')
        
    async def handle_new_pair_discovered(self, message_data: dict) -> None:
        """
        Handle new pair discovery messages from engine.
        
        Args:
            message_data: Parsed message data
        """
        try:
            # Convert to Pydantic model for validation
            from .schemas import NewPairDiscovered
            message = NewPairDiscovered(**message_data)
            
            # Process in Django (trigger comprehensive risk assessment)
            self.logger.info(f"Processing new pair: {message.pair_info.pair_address}")
            
            # Here you would trigger your Django risk assessment tasks
            # Example:
            # from risk.tasks.coordinator import assess_token_risk
            # assess_token_risk.delay(
            #     token_address=message.pair_info.token0.address,
            #     pair_address=message.pair_info.pair_address,
            #     risk_profile='moderate'
            # )
            
        except Exception as e:
            self.logger.error(f"Error handling new pair discovery: {e}")
    
    async def handle_fast_risk_complete(self, message_data: dict) -> None:
        """
        Handle fast risk assessment results from engine.
        
        Args:
            message_data: Parsed message data
        """
        try:
            from .schemas import FastRiskAssessment
            message = FastRiskAssessment(**message_data)
            
            self.logger.info(f"Fast risk complete: {message.token_address} (score: {message.overall_score})")
            
            # Update Django models with fast risk results
            # Example:
            # if message.django_risk_assessment_id:
            #     update_risk_assessment_with_fast_results(
            #         assessment_id=message.django_risk_assessment_id,
            #         fast_results=message
            #     )
            
        except Exception as e:
            self.logger.error(f"Error handling fast risk assessment: {e}")
    
    async def handle_trading_decision(self, message_data: dict) -> None:
        """
        Handle trading decisions from engine.
        
        Args:
            message_data: Parsed message data
        """
        try:
            from .schemas import TradingDecision
            message = TradingDecision(**message_data)
            
            self.logger.info(f"Trading decision: {message.decision} for {message.token_address}")
            
            # Record decision in Django
            # Example:
            # create_trade_record_from_decision(message)
            
        except Exception as e:
            self.logger.error(f"Error handling trading decision: {e}")
    
    async def setup_django_handlers(self) -> None:
        """Set up Redis subscriptions for Django."""
        handlers = {
            REDIS_CHANNELS['pair_discovery']: self.handle_new_pair_discovered,
            REDIS_CHANNELS['fast_risk_complete']: self.handle_fast_risk_complete,
            REDIS_CHANNELS['trading_decision']: self.handle_trading_decision,
        }
        
        await self.redis_client.connect()
        await self.redis_client.setup_django_subscriptions(handlers)