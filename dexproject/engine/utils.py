"""
Engine utilities for Web3 integration.

Provides provider management, utility functions, and helper classes
for reliable blockchain connectivity and operations.

File: dexproject/engine/utils.py
"""

from __future__ import annotations

import asyncio
import logging
import time
import json
from typing import Dict, Any, List, Optional, Union, Callable, TYPE_CHECKING
from decimal import Decimal
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from enum import Enum

# Conditional imports to avoid missing dependency errors
try:
    from web3 import Web3
    from web3.exceptions import Web3Exception
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False
    Web3 = None
    Web3Exception = Exception

if TYPE_CHECKING:
    from .config import ChainConfig

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """Configuration for a single RPC provider."""
    name: str
    url: str
    is_paid: bool = False
    max_requests_per_second: int = 10
    timeout_seconds: int = 30
    priority: int = 1
    api_key: Optional[str] = None


@dataclass 
class ChainConfig:
    """Configuration for a blockchain network."""
    chain_id: int
    name: str
    rpc_providers: List[ProviderConfig] = field(default_factory=list)
    native_currency: str = "ETH"
    is_testnet: bool = False
    block_time_seconds: int = 12
    max_gas_price_gwei: Optional[Decimal] = None


@dataclass
class ProviderHealth:
    """Health metrics for a single provider."""
    provider_name: str
    is_available: bool = True
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_latency_ms: float = 0.0
    last_error: Optional[str] = None
    last_success: Optional[datetime] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_latency_ms: float = 0.0
    uptime_percentage: float = 100.0
    
    def get_success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100.0
    
    def is_healthy(self) -> bool:
        """Check if provider is considered healthy."""
        return (
            self.is_available and 
            self.consecutive_failures < 3 and
            self.get_success_rate() > 50.0
        )
    
    def get_priority_score(self) -> float:
        """Calculate priority score (lower = better)."""
        if not self.is_healthy():
            return 999.0  # Very low priority for unhealthy providers
        
        # Combine latency and success rate for priority
        latency_score = self.average_latency_ms / 1000.0  # Convert to seconds
        success_penalty = (100.0 - self.get_success_rate()) / 10.0
        
        return latency_score + success_penalty
    
    def update_success(self, latency_ms: float) -> None:
        """Update metrics after a successful request."""
        self.total_requests += 1
        self.successful_requests += 1
        self.consecutive_successes += 1
        self.consecutive_failures = 0
        self.last_success = datetime.now(timezone.utc)
        self.last_latency_ms = latency_ms
        self.is_available = True
       
        # Update rolling average latency
        if self.average_latency_ms == 0:
            self.average_latency_ms = latency_ms
        else:
            # Exponential moving average (alpha = 0.1)
            self.average_latency_ms = 0.9 * self.average_latency_ms + 0.1 * latency_ms
       
        # Update uptime percentage
        if self.total_requests > 0:
            self.uptime_percentage = (self.successful_requests / self.total_requests) * 100
    
    def update_failure(self, error_message: str = "") -> None:
        """Update metrics after a failed request."""
        self.total_requests += 1
        self.failed_requests += 1
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.last_error = error_message
        
        # Mark as unavailable after 3 consecutive failures
        if self.consecutive_failures >= 3:
            self.is_available = False
        
        # Update uptime percentage
        if self.total_requests > 0:
            self.uptime_percentage = (self.successful_requests / self.total_requests) * 100


class RateLimiter:
    """Simple rate limiter for API requests."""
    
    def __init__(self, max_requests_per_second: int):
        self.max_requests_per_second = max_requests_per_second
        self.requests = []
        self.lock = asyncio.Lock()
    
    async def wait_if_needed(self):
        """Wait if rate limit would be exceeded."""
        async with self.lock:
            now = time.time()
            
            # Remove requests older than 1 second
            self.requests = [req_time for req_time in self.requests if now - req_time < 1.0]
            
            # Check if we need to wait
            if len(self.requests) >= self.max_requests_per_second:
                sleep_time = 1.0 - (now - self.requests[0])
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    # Clean up old requests again
                    now = time.time()
                    self.requests = [req_time for req_time in self.requests if now - req_time < 1.0]
            
            # Record this request
            self.requests.append(now)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Circuit breaker triggered, blocking requests
    HALF_OPEN = "HALF_OPEN"  # Testing if service has recovered


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for resilient service calls.
    
    Prevents cascading failures by temporarily blocking calls to failing services
    and allowing them time to recover.
    
    Features:
    - Configurable failure thresholds and timeouts
    - Automatic recovery testing in half-open state
    - Success rate monitoring and health checking
    - Async/await compatible
    - Detailed logging and metrics
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        expected_exception: type = Exception,
        success_threshold: int = 2
    ):
        """
        Initialize circuit breaker.
        
        Args:
            name: Name for logging and identification
            failure_threshold: Number of failures before opening circuit
            timeout_seconds: How long to wait before moving to half-open
            expected_exception: Exception type that triggers the circuit breaker
            success_threshold: Number of successes needed to close circuit from half-open
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.expected_exception = expected_exception
        self.success_threshold = success_threshold
        
        # State tracking
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_success_time: Optional[datetime] = None
        
        # Statistics
        self.total_requests = 0
        self.total_successes = 0
        self.total_failures = 0
        self.state_changes = 0
        
        # Thread safety
        self.lock = asyncio.Lock()
        
        self.logger = logging.getLogger(f"circuit_breaker.{name}")
        self.logger.info(f"Circuit breaker '{name}' initialized")
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function call through the circuit breaker.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpenError: When circuit is open
            Original exception: When function fails and circuit remains closed
        """
        async with self.lock:
            self.total_requests += 1
            
            # Check if circuit is open
            if self.state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    self._move_to_half_open()
                else:
                    self.logger.warning(f"Circuit breaker '{self.name}' is OPEN - blocking request")
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is open. "
                        f"Will retry after {self.timeout_seconds} seconds."
                    )
            
            # Attempt the function call
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                await self._on_success()
                return result
                
            except self.expected_exception as e:
                await self._on_failure(e)
                raise
    
    async def _on_success(self):
        """Handle successful function execution."""
        self.total_successes += 1
        self.last_success_time = datetime.now(timezone.utc)
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            
            if self.success_count >= self.success_threshold:
                self._move_to_closed()
        
        elif self.state == CircuitBreakerState.CLOSED:
            # Reset failure count on success in closed state
            self.failure_count = 0
    
    async def _on_failure(self, exception: Exception):
        """Handle failed function execution."""
        self.total_failures += 1
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)
        
        self.logger.warning(
            f"Circuit breaker '{self.name}' recorded failure #{self.failure_count}: {exception}"
        )
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            # Any failure in half-open state moves back to open
            self._move_to_open()
        
        elif (self.state == CircuitBreakerState.CLOSED and 
              self.failure_count >= self.failure_threshold):
            self._move_to_open()
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt circuit reset."""
        if not self.last_failure_time:
            return True
        
        time_since_failure = datetime.now(timezone.utc) - self.last_failure_time
        return time_since_failure.total_seconds() >= self.timeout_seconds
    
    def _move_to_closed(self):
        """Move circuit breaker to CLOSED state."""
        if self.state != CircuitBreakerState.CLOSED:
            self.logger.info(f"Circuit breaker '{self.name}' moving to CLOSED state")
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.state_changes += 1
    
    def _move_to_open(self):
        """Move circuit breaker to OPEN state."""
        if self.state != CircuitBreakerState.OPEN:
            self.logger.warning(f"Circuit breaker '{self.name}' moving to OPEN state")
            self.state = CircuitBreakerState.OPEN
            self.success_count = 0
            self.state_changes += 1
    
    def _move_to_half_open(self):
        """Move circuit breaker to HALF_OPEN state."""
        if self.state != CircuitBreakerState.HALF_OPEN:
            self.logger.info(f"Circuit breaker '{self.name}' moving to HALF_OPEN state")
            self.state = CircuitBreakerState.HALF_OPEN
            self.success_count = 0
            self.state_changes += 1
    
    @property
    def is_closed(self) -> bool:
        """Check if circuit breaker is closed (normal operation)."""
        return self.state == CircuitBreakerState.CLOSED
    
    @property
    def is_open(self) -> bool:
        """Check if circuit breaker is open (blocking requests)."""
        return self.state == CircuitBreakerState.OPEN
    
    @property
    def is_half_open(self) -> bool:
        """Check if circuit breaker is half-open (testing recovery)."""
        return self.state == CircuitBreakerState.HALF_OPEN
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        success_rate = 0.0
        if self.total_requests > 0:
            success_rate = (self.total_successes / self.total_requests) * 100
        
        return {
            "name": self.name,
            "state": self.state.value,
            "total_requests": self.total_requests,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "success_rate_percent": success_rate,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "state_changes": self.state_changes,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_success_time": self.last_success_time.isoformat() if self.last_success_time else None,
            "failure_threshold": self.failure_threshold,
            "timeout_seconds": self.timeout_seconds
        }
    
    def reset(self):
        """Manually reset circuit breaker to closed state."""
        self.logger.info(f"Manually resetting circuit breaker '{self.name}'")
        self._move_to_closed()


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""
    pass


# Context manager for circuit breaker
class circuit_breaker_context:
    """Context manager for circuit breaker operations."""
    
    def __init__(self, breaker: CircuitBreaker):
        self.breaker = breaker
    
    async def __aenter__(self):
        return self.breaker
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type and issubclass(exc_type, self.breaker.expected_exception):
            # Exception will be handled by the circuit breaker
            pass
        return False  # Don't suppress exceptions


class ProviderManager:
    """
    Manages multiple RPC providers with automatic failover and health monitoring.
    
    Features:
    - Automatic failover between providers
    - Health monitoring and recovery
    - Rate limiting per provider
    - Load balancing based on latency and success rate
    """
    
    def __init__(self, chain_config: ChainConfig):
        """
        Initialize provider manager.
        
        Args:
            chain_config: Configuration for the blockchain network
        """
        self.chain_config = chain_config
        self.logger = logging.getLogger(f'engine.providers.{chain_config.name.lower()}')
        
        # Provider health tracking
        self.provider_health: Dict[str, ProviderHealth] = {}
        self.rate_limiters: Dict[str, RateLimiter] = {}
        
        # Connection state
        self.current_provider: Optional[str] = None
        self.web3_instances: Dict[str, Web3] = {}
        self.failover_count = 0
        
        # Initialize providers
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Initialize all providers and health tracking."""
        if not WEB3_AVAILABLE:
            self.logger.warning("Web3 not available - running in simulation mode")
            return
        
        for provider_config in self.chain_config.rpc_providers:
            # Initialize health tracking
            health = ProviderHealth(provider_name=provider_config.name)
            self.provider_health[provider_config.name] = health
            
            # Initialize rate limiter
            rate_limiter = RateLimiter(provider_config.max_requests_per_second)
            self.rate_limiters[provider_config.name] = rate_limiter
            
            # Test provider connection
            try:
                if self._test_provider_sync(provider_config):
                    health.update_success(50.0)  # Assume 50ms for initial test
                    self.logger.info(f"✅ Provider {provider_config.name} initialized successfully")
                else:
                    health.update_failure("Initial connection test failed")
                    self.logger.warning(f"⚠️ Provider {provider_config.name} failed initial test")
            except Exception as e:
                health.update_failure(str(e))
                self.logger.error(f"❌ Error initializing provider {provider_config.name}: {e}")
        
        # Select best initial provider
        self._select_best_provider()
    
    def _test_provider_sync(self, provider_config: ProviderConfig) -> bool:
        """Test provider connection synchronously."""
        if not WEB3_AVAILABLE:
            return False
        
        try:
            # Create Web3 instance
            w3 = Web3(Web3.HTTPProvider(
                provider_config.url,
                request_kwargs={'timeout': provider_config.timeout_seconds}
            ))
            
            # Test connection
            if w3.is_connected():
                # Try to get latest block number
                block_number = w3.eth.block_number
                return block_number > 0
            
            return False
            
        except Exception as e:
            self.logger.debug(f"Provider test failed for {provider_config.name}: {e}")
            return False
    
    def _select_best_provider(self):
        """Select the best available provider based on health metrics."""
        available_providers = [
            (name, health) for name, health in self.provider_health.items()
            if health.is_healthy()
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
                self.logger.warning(
                    f"Failover from {old_provider} to {best_provider_name} "
                    f"(failover #{self.failover_count})"
                )
            else:
                self.logger.info(f"Selected provider: {best_provider_name}")
    
    async def get_web3(self) -> Optional[Web3]:
        """Get current Web3 instance with automatic failover."""
        if not WEB3_AVAILABLE:
            self.logger.warning("Web3 not available - returning None")
            return None
        
        if not self.current_provider:
            self._select_best_provider()
            if not self.current_provider:
                return None
        
        # Get or create Web3 instance for current provider
        if self.current_provider not in self.web3_instances:
            provider_config = next(
                (p for p in self.chain_config.rpc_providers if p.name == self.current_provider),
                None
            )
            
            if not provider_config:
                return None
            
            try:
                w3 = Web3(Web3.HTTPProvider(
                    provider_config.url,
                    request_kwargs={'timeout': provider_config.timeout_seconds}
                ))
                
                if w3.is_connected():
                    self.web3_instances[self.current_provider] = w3
                else:
                    # Mark provider as failed and try failover
                    self.provider_health[self.current_provider].update_failure("Connection failed")
                    self._select_best_provider()
                    return None
                    
            except Exception as e:
                self.provider_health[self.current_provider].update_failure(str(e))
                self._select_best_provider()
                return None
        
        return self.web3_instances.get(self.current_provider)
    
    async def execute_with_retry(self, operation: Callable, *args, **kwargs) -> Any:
        """Execute operation with automatic retry and failover."""
        max_retries = 3
        
        for attempt in range(max_retries):
            w3 = await self.get_web3()
            if not w3:
                await asyncio.sleep(1)
                continue
            
            try:
                # Apply rate limiting
                if self.current_provider in self.rate_limiters:
                    await self.rate_limiters[self.current_provider].wait_if_needed()
                
                start_time = time.time()
                
                # Execute operation
                if asyncio.iscoroutinefunction(operation):
                    result = await operation(w3, *args, **kwargs)
                else:
                    # Run synchronous operation in thread pool
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, operation, w3, *args, **kwargs)
                
                # Record success
                latency_ms = (time.time() - start_time) * 1000
                if self.current_provider in self.provider_health:
                    self.provider_health[self.current_provider].update_success(latency_ms)
                
                return result
                
            except Exception as e:
                # Record failure
                if self.current_provider in self.provider_health:
                    self.provider_health[self.current_provider].update_failure(str(e))
                
                self.logger.warning(f"Operation failed on {self.current_provider}: {e}")
                
                # Try failover on last attempt
                if attempt == max_retries - 1:
                    self._select_best_provider()
                    if self.current_provider:
                        continue
                
                await asyncio.sleep(1)
        
        raise Exception("All providers failed after retries")
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive health summary of all providers."""
        total_requests = sum(h.total_requests for h in self.provider_health.values())
        total_successful = sum(h.successful_requests for h in self.provider_health.values())
        
        overall_success_rate = 0.0
        if total_requests > 0:
            overall_success_rate = (total_successful / total_requests) * 100
        
        provider_details = {}
        for name, health in self.provider_health.items():
            provider_details[name] = {
                'status': 'healthy' if health.is_healthy() else 'unhealthy',
                'success_rate': health.get_success_rate(),
                'average_latency_ms': health.average_latency_ms,
                'total_requests': health.total_requests,
                'consecutive_failures': health.consecutive_failures,
                'is_paid': any(p.is_paid for p in self.chain_config.rpc_providers if p.name == name),
                'last_error': health.last_error
            }
        
        return {
            'chain': self.chain_config.name,
            'current_provider': self.current_provider,
            'failover_count': self.failover_count,
            'success_rate': overall_success_rate,
            'total_providers': len(self.provider_health),
            'healthy_providers': sum(1 for h in self.provider_health.values() if h.is_healthy()),
            'providers': provider_details
        }
    
    async def close(self):
        """Close all connections and clean up resources."""
        for w3 in self.web3_instances.values():
            try:
                # Close any open connections
                if hasattr(w3.provider, 'close'):
                    w3.provider.close()
            except Exception as e:
                self.logger.debug(f"Error closing provider connection: {e}")
        
        self.web3_instances.clear()
        self.logger.info(f"Closed all connections for {self.chain_config.name}")


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


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def safe_decimal(value: Any, default: Union[int, float, str] = 0) -> Decimal:
    """
    Safely convert value to Decimal.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Decimal representation of value
    """
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, decimal.InvalidOperation):
        return Decimal(str(default))


def format_currency(value: Decimal, symbol: str = "$") -> str:
    """
    Format a decimal value as currency.
    
    Args:
        value: Decimal value to format
        symbol: Currency symbol
        
    Returns:
        Formatted currency string
    """
    try:
        from decimal import Decimal
        
        if value is None:
            return f"{symbol}0.00"
        
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        
        # Format with commas and 2 decimal places
        return f"{symbol}{value:,.2f}"
        
    except Exception:
        return f"{symbol}0.00"

def safe_decimal(value: Any, default: Decimal = Decimal('0')) -> Decimal:
    """
    Safely convert a value to Decimal.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Decimal value
    """
    from decimal import Decimal
    
    if value is None:
        return default
    
    if isinstance(value, Decimal):
        return value
    
    try:
        return Decimal(str(value))
    except Exception:
        return default


def calculate_slippage(expected: Union[Decimal, float], actual: Union[Decimal, float]) -> float:
    """
    Calculate slippage percentage between expected and actual values.
    
    Args:
        expected: Expected value
        actual: Actual value received
        
    Returns:
        Slippage percentage (positive = worse than expected)
    """
    try:
        expected_decimal = safe_decimal(expected)
        actual_decimal = safe_decimal(actual)
        
        if expected_decimal == 0:
            return 0.0
        
        slippage = (expected_decimal - actual_decimal) / expected_decimal * 100
        return float(slippage)
    except:
        return 0.0


def setup_logging(level: str = "INFO"):
    """
    Set up basic logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='[%(levelname)s] %(asctime)s %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def format_address(address: str, length: int = 8) -> str:
    """
    Format Ethereum address for display.
    
    Args:
        address: Full Ethereum address
        length: Number of characters to show from start/end
        
    Returns:
        Formatted address (e.g., "0x1234...7890")
    """
    if not address or len(address) < 10:
        return address
    
    return f"{address[:length]}...{address[-4:]}"


def format_hash(tx_hash: str, length: int = 10) -> str:
    """
    Format transaction hash for display.
    
    Args:
        tx_hash: Full transaction hash
        length: Number of characters to show from start
        
    Returns:
        Formatted hash (e.g., "0x1234567...")
    """
    if not tx_hash or len(tx_hash) < 10:
        return tx_hash
    
    return f"{tx_hash[:length]}..."


def wei_to_ether(wei_amount: Union[int, str]) -> Decimal:
    """
    Convert Wei to Ether.
    
    Args:
        wei_amount: Amount in Wei
        
    Returns:
        Amount in Ether as Decimal
    """
    try:
        wei_decimal = safe_decimal(wei_amount)
        return wei_decimal / Decimal('1e18')
    except:
        return Decimal('0')


def ether_to_wei(ether_amount: Union[Decimal, float, str]) -> int:
    """
    Convert Ether to Wei.
    
    Args:
        ether_amount: Amount in Ether
        
    Returns:
        Amount in Wei as integer
    """
    try:
        ether_decimal = safe_decimal(ether_amount)
        wei_decimal = ether_decimal * Decimal('1e18')
        return int(wei_decimal)
    except:
        return 0


# =============================================================================
# ASYNC UTILITY FUNCTIONS
# =============================================================================

async def get_token_info(provider_manager: ProviderManager, token_address: str) -> Optional[Dict[str, Any]]:
    """
    Get token information from blockchain.
    
    Args:
        provider_manager: Provider manager instance
        token_address: Token contract address
        
    Returns:
        Token information dict or None if failed
    """
    try:
        def _get_token_info_sync(w3: Web3) -> Dict[str, Any]:
            # Basic ERC-20 ABI for token info
            erc20_abi = [
                {
                    "constant": True,
                    "inputs": [],
                    "name": "symbol",
                    "outputs": [{"name": "", "type": "string"}],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "name", 
                    "outputs": [{"name": "", "type": "string"}],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "decimals",
                    "outputs": [{"name": "", "type": "uint8"}],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "totalSupply",
                    "outputs": [{"name": "", "type": "uint256"}],
                    "type": "function"
                }
            ]
            
            contract = w3.eth.contract(address=token_address, abi=erc20_abi)
            
            return {
                'address': token_address,
                'symbol': contract.functions.symbol().call(),
                'name': contract.functions.name().call(),
                'decimals': contract.functions.decimals().call(),
                'total_supply': contract.functions.totalSupply().call()
            }
        
        return await provider_manager.execute_with_retry(_get_token_info_sync)
        
    except Exception as e:
        logger.error(f"Failed to get token info for {token_address}: {e}")
        return None


async def get_latest_block(provider_manager: ProviderManager) -> Optional[int]:
    """
    Get latest block number.
    
    Args:
        provider_manager: Provider manager instance
        
    Returns:
        Latest block number or None if failed
    """
    try:
        def _get_block_sync(w3: Web3) -> int:
            return w3.eth.block_number
        
        return await provider_manager.execute_with_retry(_get_block_sync)
        
    except Exception as e:
        logger.error(f"Failed to get latest block: {e}")
        return None


async def get_gas_price(provider_manager: ProviderManager) -> Optional[int]:
    """
    Get current gas price.
    
    Args:
        provider_manager: Provider manager instance
        
    Returns:
        Gas price in Wei or None if failed
    """
    try:
        def _get_gas_price_sync(w3: Web3) -> int:
            return w3.eth.gas_price
        
        return await provider_manager.execute_with_retry(_get_gas_price_sync)
        
    except Exception as e:
        logger.error(f"Failed to get gas price: {e}")
        return None


async def get_eth_balance(provider_manager: ProviderManager, address: str) -> Optional[Decimal]:
    """
    Get ETH balance for address.
    
    Args:
        provider_manager: Provider manager instance
        address: Ethereum address
        
    Returns:
        ETH balance as Decimal or None if failed
    """
    try:
        def _get_balance_sync(w3: Web3) -> int:
            return w3.eth.get_balance(address)
        
        balance_wei = await provider_manager.execute_with_retry(_get_balance_sync)
        return wei_to_ether(balance_wei) if balance_wei is not None else None
        
    except Exception as e:
        logger.error(f"Failed to get ETH balance for {address}: {e}")
        return None


# =============================================================================
# CONFIGURATION HELPERS
# =============================================================================

def create_testnet_chain_config(chain_id: int, name: str, rpc_urls: List[str]) -> ChainConfig:
    """
    Create a basic testnet chain configuration.
    
    Args:
        chain_id: Blockchain network ID
        name: Network name
        rpc_urls: List of RPC endpoint URLs
        
    Returns:
        ChainConfig instance
    """
    providers = []
    for i, url in enumerate(rpc_urls):
        provider = ProviderConfig(
            name=f"{name}-RPC-{i+1}",
            url=url,
            is_paid=False,
            max_requests_per_second=5,
            timeout_seconds=30,
            priority=i+1
        )
        providers.append(provider)
    
    return ChainConfig(
        chain_id=chain_id,
        name=name,
        rpc_providers=providers,
        native_currency="ETH",
        is_testnet=True,
        block_time_seconds=2 if "base" in name.lower() else 12,
        max_gas_price_gwei=Decimal('100')
    )


def get_default_testnet_configs() -> Dict[int, ChainConfig]:
    """
    Get default testnet configurations.
    
    Returns:
        Dict mapping chain_id to ChainConfig
    """
    import os
    
    alchemy_key = os.getenv('ALCHEMY_API_KEY', 'demo')
    
    configs = {}
    
    # Base Sepolia
    configs[84532] = create_testnet_chain_config(
        chain_id=84532,
        name="Base Sepolia",
        rpc_urls=[
            f"https://base-sepolia.g.alchemy.com/v2/{alchemy_key}",
            "https://sepolia.base.org",
            "https://rpc.ankr.com/base_sepolia"
        ]
    )
    
    # Ethereum Sepolia
    configs[11155111] = create_testnet_chain_config(
        chain_id=11155111,
        name="Sepolia",
        rpc_urls=[
            f"https://eth-sepolia.g.alchemy.com/v2/{alchemy_key}",
            "https://rpc.sepolia.org",
            "https://rpc.ankr.com/eth_sepolia"
        ]
    )
    
    # Arbitrum Sepolia
    configs[421614] = create_testnet_chain_config(
        chain_id=421614,
        name="Arbitrum Sepolia", 
        rpc_urls=[
            f"https://arb-sepolia.g.alchemy.com/v2/{alchemy_key}",
            "https://sepolia-rollup.arbitrum.io/rpc"
        ]
    )
    
    return configs





def format_percentage(value: Decimal, decimals: int = 2) -> str:
    """
    Format a decimal value as a percentage string.
    
    Args:
        value: Decimal value to format (e.g., 0.15 for 15%)
        decimals: Number of decimal places
        
    Returns:
        Formatted percentage string
    """
    try:
        from decimal import Decimal
        
        if value is None:
            return "0.00%"
        
        # Convert to Decimal if not already
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        
        # Multiply by 100 for percentage and format
        percentage = value * 100
        return f"{percentage:.{decimals}f}%"
        
    except Exception:
        return "0.00%"