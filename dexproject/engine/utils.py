"""
Enhanced Engine Utilities

Robust provider management with circuit breakers, health monitoring,
automatic failover, and comprehensive error handling for production use.

File: dexproject/engine/utils.py
"""

import asyncio
import logging
import time
import json
from typing import Dict, List, Optional, Any, Callable, TypeVar, Awaitable, Union
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from enum import Enum
import aiohttp
import websockets
from web3 import Web3
from web3.exceptions import Web3Exception, BlockNotFound, TransactionNotFound
from eth_utils import is_address, to_checksum_address

from .config import config, RPCProvider, ChainConfig

T = TypeVar('T')

# Configure logging for the engine
def setup_logging() -> None:
    """Configure enhanced logging for the trading engine."""
    
    # Create detailed formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler with level filtering
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.log_level))
    root_logger.addHandler(console_handler)
    
    # Engine-specific loggers
    for logger_name in ['engine', 'engine.provider', 'engine.discovery', 'engine.risk']:
        engine_logger = logging.getLogger(logger_name)
        engine_logger.setLevel(getattr(logging, config.log_level))
    
    logging.info(f"Enhanced logging configured at {config.log_level} level")


class ProviderStatus(Enum):
    """Provider health status states."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # High latency but functional
    FAILING = "failing"    # Intermittent failures
    CIRCUIT_OPEN = "circuit_open"  # Circuit breaker triggered
    OFFLINE = "offline"    # Completely unavailable


@dataclass
class ProviderMetrics:
    """Detailed provider performance metrics."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_latency_ms: float = 0.0
    last_latency_ms: float = 0.0
    requests_per_second: float = 0.0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    last_error_message: str = ""
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    uptime_percentage: float = 100.0
    
    # Circuit breaker state
    circuit_breaker_triggered: bool = False
    circuit_breaker_until: Optional[datetime] = None
    
    def update_success(self, latency_ms: float) -> None:
        """Update metrics after a successful request."""
        self.total_requests += 1
        self.successful_requests += 1
        self.consecutive_successes += 1
        self.consecutive_failures = 0
        self.last_success = datetime.now(timezone.utc)
        self.last_latency_ms = latency_ms
    
        # Update rolling average latency
        if self.average_latency_ms == 0:
            self.average_latency_ms = latency_ms
        else:
            # Exponential moving average (alpha = 0.1)
            self.average_latency_ms = 0.9 * self.average_latency_ms + 0.1 * latency_ms
    
        # Update uptime percentage
        if self.total_requests > 0:
            self.uptime_percentage = (self.successful_requests / self.total_requests) * 100
    
    async def http_request(self, method: str, url: str, **kwargs) -> Optional[Any]:
        """Make HTTP request with provider authentication and failover."""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        
        health = self.provider_health.get(self.current_provider) if self.current_provider else None
        if not health or not health.is_available():
            self._select_best_provider()
            health = self.provider_health.get(self.current_provider) if self.current_provider else None
        
        if not health:
            self.logger.error("No healthy provider for HTTP request")
            return None
        
        provider = health.provider
        start_time = time.time()
        
        try:
            # Add API key authentication if available
            headers = kwargs.get('headers', {})
            if provider.api_key:
                if 'alchemy' in provider.url.lower():
                    headers['Authorization'] = f'Bearer {provider.api_key}'
                elif 'infura' in provider.url.lower():
                    # Infura uses API key in URL typically
                    pass
            kwargs['headers'] = headers
            
            # Rate limiting
            await self.rate_limiters[provider.name].acquire()
            
            async with self.session.request(method, url, **kwargs) as response:
                response.raise_for_status()
                data = await response.json()
                
                # Record success
                latency_ms = (time.time() - start_time) * 1000
                health.metrics.update_success(latency_ms)
                
                return data
                
        except Exception as e:
            health.metrics.update_failure(str(e))
            self.logger.error(f"HTTP request failed for {provider.name}: {e}")
            return None
    
    async def websocket_connect(self, on_message: Callable[[str], Awaitable[None]]) -> None:
        """Maintain WebSocket connection with automatic reconnection."""
        if not self.current_provider:
            self._select_best_provider()
        
        while True:
            try:
                health = self.provider_health.get(self.current_provider) if self.current_provider else None
                if not health or not health.provider.websocket_url:
                    self.logger.warning("No WebSocket URL available, switching to HTTP polling")
                    await asyncio.sleep(config.websocket_reconnect_delay)
                    continue
                
                ws_url = health.provider.websocket_url
                if health.provider.api_key and 'alchemy' in ws_url.lower():
                    # Add API key for Alchemy WebSocket
                    ws_url = f"{ws_url}/{health.provider.api_key}"
                
                self.logger.info(f"Connecting to WebSocket: {health.provider.name}")
                
                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=10
                ) as websocket:
                    
                    # Subscribe to new block headers for connection monitoring
                    subscribe_msg = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "eth_subscribe",
                        "params": ["newHeads"]
                    }
                    await websocket.send(json.dumps(subscribe_msg))
                    
                    self.logger.info(f"WebSocket connected to {health.provider.name}")
                    health.metrics.update_success(0)  # Connection success
                    
                    async for message in websocket:
                        try:
                            await on_message(message)
                            health.metrics.update_success(0)  # Message processing success
                        except Exception as e:
                            self.logger.error(f"Error processing WebSocket message: {e}")
                            health.metrics.update_failure(str(e))
                
            except Exception as e:
                if self.current_provider:
                    health = self.provider_health[self.current_provider]
                    health.metrics.update_failure(str(e))
                    health.status = ProviderStatus.FAILING
                
                self.logger.error(f"WebSocket connection failed: {e}")
                self._select_best_provider()  # Try different provider
                
                await asyncio.sleep(config.websocket_reconnect_delay)
    
    async def _health_monitor_task(self) -> None:
        """Background task to monitor provider health."""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._check_provider_health()
            except Exception as e:
                self.logger.error(f"Health monitor error: {e}")
    
    async def _check_provider_health(self) -> None:
        """Perform health checks on all providers."""
        for name, health in self.provider_health.items():
            try:
                if not health.web3_instance:
                    continue
                
                # Simple connectivity test
                start_time = time.time()
                block_number = health.web3_instance.eth.block_number
                latency_ms = (time.time() - start_time) * 1000
                
                if block_number > 0:
                    health.metrics.update_success(latency_ms)
                    
                    # Update status based on latency
                    if latency_ms > 5000:
                        health.status = ProviderStatus.DEGRADED
                    elif health.status in [ProviderStatus.DEGRADED, ProviderStatus.FAILING]:
                        health.status = ProviderStatus.HEALTHY
                        
                else:
                    health.metrics.update_failure("Invalid block number")
                    health.status = ProviderStatus.FAILING
                    
            except Exception as e:
                health.metrics.update_failure(str(e))
                if health.status != ProviderStatus.CIRCUIT_OPEN:
                    health.status = ProviderStatus.OFFLINE
                
                self.logger.debug(f"Health check failed for {name}: {e}")
        
        # Reselect best provider if current one is unhealthy
        if self.current_provider:
            current_health = self.provider_health[self.current_provider]
            if not current_health.is_available():
                self._select_best_provider()
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive health summary for monitoring."""
        summary = {
            "current_provider": self.current_provider,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "success_rate": (self.successful_requests / max(self.total_requests, 1)) * 100,
            "failover_count": self.failover_count,
            "providers": {}
        }
        
        for name, health in self.provider_health.items():
            summary["providers"][name] = {
                "status": health.status.value,
                "is_paid": health.provider.is_paid,
                "priority": health.provider.priority,
                "total_requests": health.metrics.total_requests,
                "success_rate": health.metrics.uptime_percentage,
                "average_latency_ms": health.metrics.average_latency_ms,
                "consecutive_failures": health.metrics.consecutive_failures,
                "circuit_breaker_active": health.metrics.circuit_breaker_triggered,
                "last_success": health.metrics.last_success.isoformat() if health.metrics.last_success else None,
                "last_error": health.metrics.last_error_message[:100] if health.metrics.last_error_message else None
            }
        
        return summary
    
    async def close(self) -> None:
        """Clean up resources."""
        if self.session:
            await self.session.close()
        
        for health in self.provider_health.values():
            if health.web3_instance:
                # Close any open connections
                try:
                    health.web3_instance.provider.endpoint_uri = None
                except:
                    pass
        
        self.logger.info(f"Provider manager closed for {self.chain_config.name}")


# Utility functions for common blockchain operations
async def get_token_info(provider_manager: ProviderManager, token_address: str) -> Optional[Dict[str, Any]]:
    """Get basic token information using provider manager."""
    if not is_address(token_address):
        return None
    
    token_address = to_checksum_address(token_address)
    
    # Basic ERC20 ABI
    erc20_abi = [
        {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}
    ]
    
    async def _get_info(w3: Web3) -> Dict[str, Any]:
        contract = w3.eth.contract(address=token_address, abi=erc20_abi)
        
        try:
            name = contract.functions.name().call()
        except:
            name = "Unknown"
        
        try:
            symbol = contract.functions.symbol().call()
        except:
            symbol = "UNKNOWN"
        
        try:
            decimals = contract.functions.decimals().call()
        except:
            decimals = 18
        
        try:
            total_supply = contract.functions.totalSupply().call()
        except:
            total_supply = 0
        
        return {
            "address": token_address,
            "name": name,
            "symbol": symbol,
            "decimals": decimals,
            "total_supply": total_supply
        }
    
    return await provider_manager.execute_with_failover(_get_info)


async def get_latest_block(provider_manager: ProviderManager) -> Optional[int]:
    """Get latest block number using provider manager."""
    
    async def _get_block(w3: Web3) -> int:
        return w3.eth.block_number
    
    return await provider_manager.execute_with_failover(_get_block)


# Async context manager for provider lifecycle
class ProviderManagerContext:
    """Context manager for ProviderManager lifecycle."""
   
    def __init__(self, chain_config: ChainConfig):
        self.chain_config = chain_config
        self.provider_manager: Optional[ProviderManager] = None
   
    async def __aenter__(self) -> ProviderManager:
        self.provider_manager = ProviderManager(self.chain_config)
        return self.provider_manager
   
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.provider_manager:
            await self.provider_manager.close()
            
        # Exponential moving average (alpha = 0.1)
        self.average_latency_ms = 0.9 * self.average_latency_ms + 0.1 * latency_ms
       
        # Update uptime percentage
        if self.total_requests > 0:
            self.uptime_percentage = (self.successful_requests / self.total_requests) * 100
    
    def update_failure(self, error_message: str) -> None:
        """Update metrics after a failed request."""
        self.total_requests += 1
        self.failed_requests += 1
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.last_failure = datetime.now(timezone.utc)
        self.last_error_message = error_message
        
        # Update uptime percentage
        if self.total_requests > 0:
            self.uptime_percentage = (self.successful_requests / self.total_requests) * 100
    
    def reset_circuit_breaker(self) -> None:
        """Reset circuit breaker state."""
        self.circuit_breaker_triggered = False
        self.circuit_breaker_until = None
        self.consecutive_failures = 0
    
    def trigger_circuit_breaker(self, duration_seconds: int = 60) -> None:
        """Trigger circuit breaker for specified duration."""
        self.circuit_breaker_triggered = True
        self.circuit_breaker_until = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)


@dataclass
class ProviderHealth:
    """Enhanced provider health status with detailed metrics."""
    provider: RPCProvider
    status: ProviderStatus = ProviderStatus.HEALTHY
    metrics: ProviderMetrics = field(default_factory=ProviderMetrics)
    web3_instance: Optional[Web3] = None
    
    def is_available(self) -> bool:
        """Check if provider is available for requests."""
        if self.status == ProviderStatus.OFFLINE:
            return False
        
        if self.metrics.circuit_breaker_triggered:
            if self.metrics.circuit_breaker_until and datetime.now(timezone.utc) > self.metrics.circuit_breaker_until:
                self.metrics.reset_circuit_breaker()
                self.status = ProviderStatus.HEALTHY
                return True
            return False
        
        return self.status in [ProviderStatus.HEALTHY, ProviderStatus.DEGRADED]
    
    def get_priority_score(self) -> float:
        """Calculate priority score for provider selection (lower = better)."""
        base_priority = self.provider.priority
        
        # Adjust based on health status
        if self.status == ProviderStatus.HEALTHY:
            status_penalty = 0
        elif self.status == ProviderStatus.DEGRADED:
            status_penalty = 1
        elif self.status == ProviderStatus.FAILING:
            status_penalty = 3
        else:
            status_penalty = 10  # Circuit open or offline
        
        # Adjust based on recent performance
        latency_penalty = min(self.metrics.average_latency_ms / 1000, 2)  # Max 2 points for latency
        failure_penalty = self.metrics.consecutive_failures * 0.5
        
        return base_priority + status_penalty + latency_penalty + failure_penalty


class RateLimiter:
    """Advanced rate limiter with burst handling."""
    
    def __init__(self, max_requests_per_second: int, burst_size: Optional[int] = None):
        """Initialize rate limiter."""
        self.max_rps = max_requests_per_second
        self.burst_size = burst_size or min(max_requests_per_second * 2, 100)
        self.tokens = self.burst_size
        self.last_update = time.time()
        self.lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary."""
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            
            # Add tokens based on elapsed time
            tokens_to_add = elapsed * self.max_rps
            self.tokens = min(self.burst_size, self.tokens + tokens_to_add)
            self.last_update = now
            
            if self.tokens >= 1:
                self.tokens -= 1
                return
            
            # Need to wait
            wait_time = (1 - self.tokens) / self.max_rps
            await asyncio.sleep(wait_time)
            self.tokens = 0


class ProviderManager:
    """
    Enhanced provider manager with circuit breakers, health monitoring,
    automatic failover, and comprehensive error handling.
    """
    
    def __init__(self, chain_config: ChainConfig):
        """Initialize enhanced provider manager."""
        self.chain_config = chain_config
        self.provider_health: Dict[str, ProviderHealth] = {}
        self.current_provider: Optional[str] = None  # Store provider name
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limiters: Dict[str, RateLimiter] = {}
        
        self.logger = logging.getLogger(f'engine.provider.{chain_config.name.lower()}')
        
        # Circuit breaker settings
        self.failure_threshold = config.provider_failover_threshold
        self.recovery_timeout = config.provider_recovery_time
        self.health_check_interval = config.provider_health_check_interval
        
        # Performance tracking
        self.total_requests = 0
        self.successful_requests = 0
        self.failover_count = 0
        
        # Initialize providers
        self._initialize_providers()
        
        # Start background health monitoring
        asyncio.create_task(self._health_monitor_task())
    
    def _initialize_providers(self) -> None:
        """Initialize all providers with health tracking."""
        for provider in self.chain_config.rpc_providers:
            # Create health tracker
            health = ProviderHealth(provider=provider)
            self.provider_health[provider.name] = health
            
            # Create rate limiter
            self.rate_limiters[provider.name] = RateLimiter(provider.max_requests_per_second)
            
            # Initialize Web3 connection
            try:
                w3 = Web3(Web3.HTTPProvider(
                    provider.url,
                    request_kwargs={'timeout': provider.timeout_seconds}
                ))
                
                # Test connection
                if w3.is_connected():
                    health.web3_instance = w3
                    health.status = ProviderStatus.HEALTHY
                    self.logger.info(f"Successfully connected to {provider.name}")
                else:
                    health.status = ProviderStatus.OFFLINE
                    self.logger.warning(f"Failed to connect to {provider.name}")
                    
            except Exception as e:
                health.status = ProviderStatus.OFFLINE
                health.metrics.update_failure(str(e))
                self.logger.error(f"Error initializing {provider.name}: {e}")
        
        # Select initial provider
        self._select_best_provider()
        
        self.logger.info(f"Initialized {len(self.provider_health)} providers for {self.chain_config.name}")
    
    def _select_best_provider(self) -> None:
        """Select the best available provider based on health and priority."""
        available_providers = [
            (name, health) for name, health in self.provider_health.items()
            if health.is_available()
        ]
        
        if not available_providers:
            self.current_provider = None
            self.logger.error("No healthy providers available!")
            return
        
        # Sort by priority score (lower = better)
        best_provider_name, best_health = min(
            available_providers,
            key=lambda x: x[1].get_priority_score()
        )
        
        if self.current_provider != best_provider_name:
            old_provider = self.current_provider
            self.current_provider = best_provider_name
            
            if old_provider:
                self.failover_count += 1
                self.logger.warning(f"Failover from {old_provider} to {best_provider_name} "
                                  f"(failover #{self.failover_count})")
            else:
                self.logger.info(f"Selected provider: {best_provider_name}")
    
    async def get_web3(self) -> Optional[Web3]:
        """Get current Web3 instance with automatic failover."""
        if not self.current_provider:
            self._select_best_provider()
        
        if self.current_provider:
            health = self.provider_health[self.current_provider]
            if health.is_available() and health.web3_instance:
                return health.web3_instance
        
        # No healthy provider available
        self.logger.error("No healthy Web3 instance available")
        return None
    
    async def execute_with_failover(self, operation: Callable[[Web3], T], max_retries: int = 3) -> Optional[T]:
        """Execute an operation with automatic provider failover."""
        for attempt in range(max_retries):
            try:
                w3 = await self.get_web3()
                if not w3:
                    if attempt == max_retries - 1:
                        self.logger.error("All providers failed - no Web3 available")
                    await asyncio.sleep(min(2 ** attempt, 10))  # Exponential backoff
                    continue
                
                # Rate limiting
                if self.current_provider:
                    await self.rate_limiters[self.current_provider].acquire()
                
                # Execute operation with timing
                start_time = time.time()
                result = await self._execute_operation(operation, w3)
                execution_time = (time.time() - start_time) * 1000
                
                # Record success
                if self.current_provider:
                    health = self.provider_health[self.current_provider]
                    health.metrics.update_success(execution_time)
                    
                    # Update status based on performance
                    if execution_time > 5000:  # > 5 seconds
                        health.status = ProviderStatus.DEGRADED
                    elif health.status == ProviderStatus.DEGRADED and execution_time < 2000:
                        health.status = ProviderStatus.HEALTHY
                
                self.total_requests += 1
                self.successful_requests += 1
                
                return result
                
            except Exception as e:
                self.total_requests += 1
                
                if self.current_provider:
                    health = self.provider_health[self.current_provider]
                    health.metrics.update_failure(str(e))
                    
                    # Check if we should trigger circuit breaker
                    if health.metrics.consecutive_failures >= self.failure_threshold:
                        health.metrics.trigger_circuit_breaker(self.recovery_timeout)
                        health.status = ProviderStatus.CIRCUIT_OPEN
                        self.logger.warning(f"Circuit breaker triggered for {self.current_provider}")
                    elif health.metrics.consecutive_failures >= 2:
                        health.status = ProviderStatus.FAILING
                
                self.logger.warning(f"Operation failed on {self.current_provider} (attempt {attempt + 1}): {e}")
                
                # Try to select a different provider
                self._select_best_provider()
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(min(2 ** attempt, 5))  # Exponential backoff
        
        self.logger.error(f"Operation failed after {max_retries} attempts across all providers")
        return None
    
    async def _execute_operation(self, operation: Callable[[Web3], T], w3: Web3) -> T:
        """Execute operation with proper error handling."""
        if asyncio.iscoroutinefunction(operation):
            return await operation(w3)
        else:
            pass