"""
Engine Utilities

Shared utilities for provider management, logging configuration,
and common helper functions used across the trading engine.
"""

import asyncio
import logging
import time
import json
from typing import Dict, List, Optional, Any, Callable, TypeVar, Awaitable
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone
import aiohttp
import websockets
from web3 import Web3

from .config import config, RPCProvider, ChainConfig

T = TypeVar('T')

# Configure logging for the engine
def setup_logging() -> None:
    """Configure logging for the trading engine."""
    
    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.log_level))
    root_logger.addHandler(console_handler)
    
    # Engine-specific logger
    engine_logger = logging.getLogger('engine')
    engine_logger.setLevel(getattr(logging, config.log_level))
    
    logging.info(f"Logging configured at {config.log_level} level")


@dataclass
class ProviderHealth:
    """Health status for an RPC provider."""
    provider: RPCProvider
    is_healthy: bool = True
    last_success: Optional[datetime] = None
    last_error: Optional[str] = None
    consecutive_failures: int = 0
    average_latency_ms: float = 0.0
    requests_per_second: float = 0.0


class ProviderManager:
    """
    Manages RPC provider connections with health monitoring and failover.
    
    Handles automatic failover between providers, tracks health metrics,
    and implements circuit breaker patterns for reliability.
    """
    
    def __init__(self, chain_config: ChainConfig):
        """Initialize provider manager for a chain."""
        self.chain_config = chain_config
        self.provider_health: Dict[str, ProviderHealth] = {}
        self.current_provider: Optional[RPCProvider] = None
        self.web3_instances: Dict[str, Web3] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.logger = logging.getLogger(f'engine.provider.{chain_config.name.lower()}')
        
        # Circuit breaker settings
        self.max_consecutive_failures = 5
        self.health_check_interval = 30  # seconds
        self.failover_cooldown = 60  # seconds
        
        self._initialize_providers()
    
    def _initialize_providers(self) -> None:
        """Initialize provider health tracking."""
        for provider in self.chain_config.rpc_providers:
            self.provider_health[provider.name] = ProviderHealth(
                provider=provider,
                last_success=datetime.now(timezone.utc)
            )
            
            # Create Web3 instance
            try:
                w3 = Web3(Web3.HTTPProvider(provider.url))
                if w3.is_connected():
                    self.web3_instances[provider.name] = w3
                    self.logger.info(f"Connected to provider {provider.name}")
                else:
                    self.logger.warning(f"Failed to connect to provider {provider.name}")
            except Exception as e:
                self.logger.error(f"Error initializing provider {provider.name}: {e}")
        
        # Set current provider to highest priority healthy one
        self._select_current_provider()
    
    def _select_current_provider(self) -> None:
        """Select the best available provider based on priority and health."""
        healthy_providers = [
            health.provider for health in self.provider_health.values()
            if health.is_healthy and health.provider.name in self.web3_instances
        ]
        
        if healthy_providers:
            # Sort by priority (lower = better) then by health metrics
            self.current_provider = min(
                healthy_providers,
                key=lambda p: (p.priority, self.provider_health[p.name].consecutive_failures)
            )
            self.logger.info(f"Selected provider: {self.current_provider.name}")
        else:
            self.current_provider = None
            self.logger.error("No healthy providers available!")
    
    async def get_web3(self) -> Optional[Web3]:
        """Get current Web3 instance with automatic failover."""
        if not self.current_provider:
            self._select_current_provider()
        
        if self.current_provider and self.current_provider.name in self.web3_instances:
            return self.web3_instances[self.current_provider.name]
        
        return None
    
    async def http_request(self, method: str, url: str, **kwargs) -> Optional[Any]:
        """Make HTTP request with provider failover."""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        provider = self.current_provider
        if not provider:
            return None
        
        start_time = time.time()
        
        try:
            # Add API key if configured
            headers = kwargs.get('headers', {})
            if provider.api_key:
                headers['Authorization'] = f'Bearer {provider.api_key}'
            kwargs['headers'] = headers
            
            async with self.session.request(method, url, timeout=10, **kwargs) as response:
                response.raise_for_status()
                data = await response.json()
                
                # Update health metrics
                latency_ms = (time.time() - start_time) * 1000
                self._record_success(provider.name, latency_ms)
                
                return data
                
        except Exception as e:
            self.logger.error(f"HTTP request failed for {provider.name}: {e}")
            self._record_failure(provider.name, str(e))
            
            # Try failover
            await self._attempt_failover()
            return None
    
    async def websocket_connect(self, url: str) -> Optional[websockets.WebSocketServerProtocol]:
        """Connect to WebSocket with provider failover."""
        provider = self.current_provider
        if not provider or not provider.websocket_url:
            return None
        
        try:
            # Add authentication if needed
            headers = {}
            if provider.api_key:
                headers['Authorization'] = f'Bearer {provider.api_key}'
            
            websocket = await websockets.connect(
                provider.websocket_url,
                extra_headers=headers,
                ping_timeout=config.websocket_timeout
            )
            
            self._record_success(provider.name, 0)  # WebSocket connection success
            self.logger.info(f"WebSocket connected to {provider.name}")
            return websocket
            
        except Exception as e:
            self.logger.error(f"WebSocket connection failed for {provider.name}: {e}")
            self._record_failure(provider.name, str(e))
            await self._attempt_failover()
            return None
    
    def _record_success(self, provider_name: str, latency_ms: float) -> None:
        """Record successful request for provider health tracking."""
        if provider_name in self.provider_health:
            health = self.provider_health[provider_name]
            health.is_healthy = True
            health.last_success = datetime.now(timezone.utc)
            health.consecutive_failures = 0
            
            # Update rolling average latency
            if health.average_latency_ms == 0:
                health.average_latency_ms = latency_ms
            else:
                health.average_latency_ms = (health.average_latency_ms * 0.9) + (latency_ms * 0.1)
    
    def _record_failure(self, provider_name: str, error: str) -> None:
        """Record failed request for provider health tracking."""
        if provider_name in self.provider_health:
            health = self.provider_health[provider_name]
            health.last_error = error
            health.consecutive_failures += 1
            
            # Mark as unhealthy if too many consecutive failures
            if health.consecutive_failures >= self.max_consecutive_failures:
                health.is_healthy = False
                self.logger.warning(f"Provider {provider_name} marked unhealthy after {health.consecutive_failures} failures")
    
    async def _attempt_failover(self) -> None:
        """Attempt to failover to next healthy provider."""
        old_provider = self.current_provider
        self._select_current_provider()
        
        if self.current_provider != old_provider:
            if old_provider:
                self.logger.warning(f"Failed over from {old_provider.name} to {self.current_provider.name}")
            else:
                self.logger.info(f"Selected new provider: {self.current_provider.name}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all providers."""
        health_status = {}
        
        for name, health in self.provider_health.items():
            health_status[name] = {
                'is_healthy': health.is_healthy,
                'consecutive_failures': health.consecutive_failures,
                'average_latency_ms': health.average_latency_ms,
                'last_success': health.last_success.isoformat() if health.last_success else None,
                'last_error': health.last_error
            }
        
        return {
            'chain': self.chain_config.name,
            'current_provider': self.current_provider.name if self.current_provider else None,
            'providers': health_status
        }
    
    async def close(self) -> None:
        """Close all connections and cleanup."""
        if self.session:
            await self.session.close()
        self.logger.info(f"Provider manager closed for {self.chain_config.name}")


class CircuitBreaker:
    """
    Circuit breaker implementation for protecting against cascading failures.
    
    Implements the circuit breaker pattern to prevent repeated calls
    to failing services and allow graceful degradation.
    """
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        """Initialize circuit breaker."""
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.logger = logging.getLogger('engine.circuit_breaker')
    
    async def call(self, func: Callable[[], Awaitable[T]]) -> Optional[T]:
        """Execute function with circuit breaker protection."""
        if self.state == "OPEN":
            if self._should_attempt_reset():
                self.state = "HALF_OPEN"
                self.logger.info("Circuit breaker moving to HALF_OPEN state")
            else:
                self.logger.warning("Circuit breaker is OPEN, call blocked")
                return None
        
        try:
            result = await func()
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            self.logger.error(f"Circuit breaker caught exception: {e}")
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if not self.last_failure_time:
            return True
        return time.time() - self.last_failure_time >= self.timeout
    
    def _on_success(self) -> None:
        """Handle successful call."""
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            self.logger.info("Circuit breaker reset to CLOSED state")
        self.failure_count = 0
    
    def _on_failure(self) -> None:
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            self.logger.warning(f"Circuit breaker opened after {self.failure_count} failures")


class RateLimiter:
    """Rate limiter for API requests."""
    
    def __init__(self, max_requests: int, time_window: int = 60):
        """Initialize rate limiter."""
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
        self.logger = logging.getLogger('engine.rate_limiter')
    
    async def acquire(self) -> bool:
        """Acquire permission to make a request."""
        now = time.time()
        
        # Remove old requests outside time window
        self.requests = [req_time for req_time in self.requests if now - req_time < self.time_window]
        
        # Check if we can make another request
        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True
        else:
            self.logger.warning(f"Rate limit exceeded: {len(self.requests)}/{self.max_requests} requests")
            return False
    
    async def wait_if_needed(self) -> None:
        """Wait if rate limit would be exceeded."""
        while not await self.acquire():
            await asyncio.sleep(1)


def format_currency(amount: Decimal, decimals: int = 2) -> str:
    """Format decimal amount as currency string."""
    return f"${amount:,.{decimals}f}"


def format_percentage(value: Decimal, decimals: int = 2) -> str:
    """Format decimal as percentage string."""
    return f"{value:.{decimals}f}%"


def calculate_slippage(expected: Decimal, actual: Decimal) -> Decimal:
    """Calculate slippage percentage between expected and actual amounts."""
    if expected == 0:
        return Decimal('0')
    return abs((actual - expected) / expected) * 100


def truncate_address(address: str, start: int = 6, end: int = 4) -> str:
    """Truncate Ethereum address for display."""
    if len(address) <= start + end:
        return address
    return f"{address[:start]}...{address[-end:]}"


def safe_decimal(value: Any, default: Decimal = Decimal('0')) -> Decimal:
    """Safely convert value to Decimal."""
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, OverflowError):
        return default


def get_current_timestamp() -> int:
    """Get current Unix timestamp."""
    return int(time.time())


def get_current_timestamp_ms() -> int:
    """Get current Unix timestamp in milliseconds."""
    return int(time.time() * 1000)