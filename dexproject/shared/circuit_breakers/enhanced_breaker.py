"""
Enhanced Circuit Breaker Implementation

Production-ready circuit breaker with advanced features including sliding windows,
gradual recovery, jitter, comprehensive metrics, and integration with retry logic.

File: shared/circuit_breakers/enhanced_breaker.py
"""

import asyncio
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import (
    Any, Callable, Deque, Dict, List, Optional, Tuple, TypeVar, Union
)

from .config import (
    CircuitBreakerConfig,
    CircuitBreakerType,
    RecoveryStrategy,
    CircuitBreakerPriority,
)

logger = logging.getLogger(__name__)

# Type variable for generic return types
T = TypeVar('T')


# =============================================================================
# CIRCUIT BREAKER STATES
# =============================================================================

class CircuitBreakerState(Enum):
    """Enhanced circuit breaker states with additional transitional states."""
    CLOSED = "CLOSED"              # Normal operation
    OPEN = "OPEN"                  # Blocking all requests
    HALF_OPEN = "HALF_OPEN"        # Testing recovery
    FORCED_OPEN = "FORCED_OPEN"    # Manually forced open
    DISABLED = "DISABLED"          # Circuit breaker disabled


# =============================================================================
# EXCEPTIONS
# =============================================================================

class CircuitBreakerError(Exception):
    """Base exception for circuit breaker errors."""
    pass


class CircuitBreakerOpenError(CircuitBreakerError):
    """Exception raised when circuit breaker is open."""
    def __init__(
        self,
        message: str,
        breaker_name: str,
        retry_after: Optional[datetime] = None,
        failure_count: int = 0
    ):
        super().__init__(message)
        self.breaker_name = breaker_name
        self.retry_after = retry_after
        self.failure_count = failure_count


# =============================================================================
# METRICS AND MONITORING
# =============================================================================

@dataclass
class CallResult:
    """Result of a single call through the circuit breaker."""
    timestamp: datetime
    success: bool
    latency_ms: float
    error_type: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class CircuitBreakerMetrics:
    """Comprehensive metrics for circuit breaker monitoring."""
    # Basic counters
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    
    # State counters
    state_changes: int = 0
    times_opened: int = 0
    times_half_opened: int = 0
    
    # Timing metrics
    total_open_time_seconds: float = 0
    last_opened_at: Optional[datetime] = None
    last_closed_at: Optional[datetime] = None
    last_call_at: Optional[datetime] = None
    
    # Performance metrics
    avg_latency_ms: float = 0
    p50_latency_ms: float = 0
    p95_latency_ms: float = 0
    p99_latency_ms: float = 0
    
    # Error rate metrics
    error_rate_1min: float = 0
    error_rate_5min: float = 0
    error_rate_15min: float = 0
    
    # Recovery metrics
    recovery_attempts: int = 0
    successful_recoveries: int = 0
    failed_recoveries: int = 0
    avg_recovery_time_seconds: float = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for serialization."""
        return {
            'total_calls': self.total_calls,
            'successful_calls': self.successful_calls,
            'failed_calls': self.failed_calls,
            'rejected_calls': self.rejected_calls,
            'success_rate': self.get_success_rate(),
            'error_rate': self.get_error_rate(),
            'state_changes': self.state_changes,
            'times_opened': self.times_opened,
            'total_open_time_seconds': self.total_open_time_seconds,
            'avg_latency_ms': self.avg_latency_ms,
            'p50_latency_ms': self.p50_latency_ms,
            'p95_latency_ms': self.p95_latency_ms,
            'p99_latency_ms': self.p99_latency_ms,
            'error_rate_1min': self.error_rate_1min,
            'recovery_attempts': self.recovery_attempts,
            'successful_recoveries': self.successful_recoveries,
        }
    
    def get_success_rate(self) -> float:
        """Calculate overall success rate."""
        if self.total_calls == 0:
            return 0.0
        return (self.successful_calls / self.total_calls) * 100
    
    def get_error_rate(self) -> float:
        """Calculate overall error rate."""
        if self.total_calls == 0:
            return 0.0
        return (self.failed_calls / self.total_calls) * 100


# =============================================================================
# ENHANCED CIRCUIT BREAKER
# =============================================================================

class EnhancedCircuitBreaker:
    """
    Production-ready circuit breaker with advanced features.
    
    Features:
        - Sliding window for error rate calculation
        - Configurable recovery strategies
        - Jitter to prevent thundering herd
        - Comprehensive metrics and monitoring
        - Integration with retry logic
        - Gradual recovery support
        - Health check capabilities
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        breaker_type: Optional[CircuitBreakerType] = None,
        health_check_func: Optional[Callable] = None,
        notification_callback: Optional[Callable] = None,
    ):
        """
        Initialize enhanced circuit breaker.
        
        Args:
            name: Unique name for this circuit breaker
            config: Configuration object (if None, uses defaults)
            breaker_type: Type of circuit breaker
            health_check_func: Optional async function for health checks
            notification_callback: Optional callback for state changes
        """
        self.name = name
        self.breaker_type = breaker_type or CircuitBreakerType.EXTERNAL_TRIGGER
        
        # Load configuration
        if config is None:
            from .config import CircuitBreakerDefaults
            config = CircuitBreakerDefaults.get_config(self.breaker_type)
        self.config = config
        
        # State management
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_success_time: Optional[datetime] = None
        self.last_state_change: datetime = datetime.now(timezone.utc)
        
        # Sliding window for call history
        self.call_history: Deque[CallResult] = deque(
            maxlen=self.config.sliding_window_size
        )
        
        # Metrics
        self.metrics = CircuitBreakerMetrics()
        
        # Health check and notifications
        self.health_check_func = health_check_func
        self.notification_callback = notification_callback
        
        # Half-open state management
        self.half_open_calls = 0
        
        # Timeout escalation
        self.current_timeout_multiplier = 1.0
        self.consecutive_timeouts = 0
        
        # Thread safety
        self.lock = asyncio.Lock()
        
        # Logger specific to this breaker
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self.logger.info(
            f"Enhanced Circuit Breaker '{name}' initialized "
            f"[Type: {self.breaker_type.value}, Priority: {config.priority.value}]"
        )
    
    # =========================================================================
    # MAIN EXECUTION METHOD
    # =========================================================================
    
    async def call(
        self,
        func: Callable[..., T],
        *args,
        fallback: Optional[Callable[..., T]] = None,
        **kwargs
    ) -> T:
        """
        Execute a function call through the circuit breaker.
        
        Args:
            func: Async or sync function to execute
            *args: Function arguments
            fallback: Optional fallback function if circuit is open
            **kwargs: Function keyword arguments
            
        Returns:
            Function result or fallback result
            
        Raises:
            CircuitBreakerOpenError: When circuit is open and no fallback
            Original exception: When function fails and circuit remains closed
        """
        async with self.lock:
            start_time = time.time()
            self.metrics.total_calls += 1
            self.metrics.last_call_at = datetime.now(timezone.utc)
            
            # Check if disabled
            if self.state == CircuitBreakerState.DISABLED:
                return await self._execute_function(func, *args, **kwargs)
            
            # Check if circuit is open
            if self.state in [CircuitBreakerState.OPEN, CircuitBreakerState.FORCED_OPEN]:
                if self.state == CircuitBreakerState.FORCED_OPEN:
                    # Forced open doesn't auto-recover
                    self.metrics.rejected_calls += 1
                    if fallback:
                        self.logger.info(f"Circuit '{self.name}' forced open, using fallback")
                        return await self._execute_function(fallback, *args, **kwargs)
                    raise self._create_open_error()
                
                # Check if should attempt recovery
                if self._should_attempt_recovery():
                    await self._transition_to_half_open()
                else:
                    self.metrics.rejected_calls += 1
                    if fallback:
                        self.logger.debug(f"Circuit '{self.name}' open, using fallback")
                        return await self._execute_function(fallback, *args, **kwargs)
                    raise self._create_open_error()
            
            # Check if half-open
            if self.state == CircuitBreakerState.HALF_OPEN:
                if self.half_open_calls >= self.config.half_open_max_calls:
                    self.metrics.rejected_calls += 1
                    if fallback:
                        return await self._execute_function(fallback, *args, **kwargs)
                    raise self._create_open_error("Half-open call limit reached")
                self.half_open_calls += 1
            
            # Attempt the function call
            try:
                result = await self._execute_function(func, *args, **kwargs)
                latency_ms = (time.time() - start_time) * 1000
                
                # Record successful call
                await self._on_success(latency_ms)
                return result
                
            except Exception as error:
                latency_ms = (time.time() - start_time) * 1000
                
                # Record failed call
                await self._on_failure(error, latency_ms)
                
                # If we have a fallback and circuit just opened, use it
                if fallback and self.state == CircuitBreakerState.OPEN:
                    self.logger.info(f"Circuit '{self.name}' just opened, using fallback")
                    return await self._execute_function(fallback, *args, **kwargs)
                
                raise
    
    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================
    
    async def _on_success(self, latency_ms: float) -> None:
        """Handle successful function execution."""
        self.metrics.successful_calls += 1
        self.success_count += 1
        self.last_success_time = datetime.now(timezone.utc)
        
        # Record in history
        self.call_history.append(CallResult(
            timestamp=self.last_success_time,
            success=True,
            latency_ms=latency_ms
        ))
        
        # Update latency metrics
        self._update_latency_metrics(latency_ms)
        
        # State-specific handling
        if self.state == CircuitBreakerState.HALF_OPEN:
            if self.success_count >= self.config.success_threshold:
                await self._transition_to_closed()
                self.metrics.successful_recoveries += 1
        elif self.state == CircuitBreakerState.CLOSED:
            # Reset failure count on success in closed state
            self.failure_count = 0
            self.consecutive_timeouts = 0
            self.current_timeout_multiplier = 1.0
    
    async def _on_failure(self, error: Exception, latency_ms: float) -> None:
        """Handle failed function execution."""
        self.metrics.failed_calls += 1
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)
        
        # Record in history
        self.call_history.append(CallResult(
            timestamp=self.last_failure_time,
            success=False,
            latency_ms=latency_ms,
            error_type=type(error).__name__,
            error_message=str(error)
        ))
        
        # Update latency metrics
        self._update_latency_metrics(latency_ms)
        
        # Log the failure
        self.logger.warning(
            f"Circuit '{self.name}' recorded failure #{self.failure_count}: "
            f"{type(error).__name__}: {error}"
        )
        
        # Check if we should open the circuit
        should_open = False
        
        # Check failure threshold
        if self.failure_count >= self.config.failure_threshold:
            should_open = True
        
        # Check error rate threshold if configured
        if self.config.error_rate_threshold:
            error_rate = self._calculate_error_rate()
            if error_rate > self.config.error_rate_threshold:
                should_open = True
                self.logger.warning(
                    f"Circuit '{self.name}' error rate {error_rate:.1%} "
                    f"exceeds threshold {self.config.error_rate_threshold:.1%}"
                )
        
        # State-specific handling
        if self.state == CircuitBreakerState.HALF_OPEN:
            # Any failure in half-open moves back to open
            await self._transition_to_open()
            self.metrics.failed_recoveries += 1
        elif self.state == CircuitBreakerState.CLOSED and should_open:
            await self._transition_to_open()
    
    # =========================================================================
    # STATE TRANSITIONS
    # =========================================================================
    
    async def _transition_to_closed(self) -> None:
        """Transition circuit breaker to CLOSED state."""
        if self.state == CircuitBreakerState.CLOSED:
            return
        
        previous_state = self.state
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.half_open_calls = 0
        self.current_timeout_multiplier = 1.0
        self.consecutive_timeouts = 0
        
        # Update metrics
        self.metrics.state_changes += 1
        self.metrics.last_closed_at = datetime.now(timezone.utc)
        if self.metrics.last_opened_at:
            open_duration = (
                self.metrics.last_closed_at - self.metrics.last_opened_at
            ).total_seconds()
            self.metrics.total_open_time_seconds += open_duration
            
            # Update average recovery time
            if self.metrics.successful_recoveries > 0:
                self.metrics.avg_recovery_time_seconds = (
                    self.metrics.total_open_time_seconds / 
                    self.metrics.successful_recoveries
                )
        
        self.last_state_change = self.metrics.last_closed_at
        
        self.logger.info(
            f"Circuit '{self.name}' transitioned from {previous_state.value} to CLOSED"
        )
        
        # Send notification
        await self._notify_state_change(previous_state, self.state)
    
    async def _transition_to_open(self) -> None:
        """Transition circuit breaker to OPEN state."""
        if self.state == CircuitBreakerState.OPEN:
            return
        
        previous_state = self.state
        self.state = CircuitBreakerState.OPEN
        self.success_count = 0
        self.half_open_calls = 0
        
        # Escalate timeout if configured
        if self.config.escalation_multiplier > 1.0:
            self.consecutive_timeouts += 1
            self.current_timeout_multiplier = min(
                self.current_timeout_multiplier * self.config.escalation_multiplier,
                self.config.max_timeout_seconds / self.config.timeout_seconds
            )
        
        # Update metrics
        self.metrics.state_changes += 1
        self.metrics.times_opened += 1
        self.metrics.last_opened_at = datetime.now(timezone.utc)
        self.last_state_change = self.metrics.last_opened_at
        
        self.logger.warning(
            f"Circuit '{self.name}' transitioned from {previous_state.value} to OPEN "
            f"[Failures: {self.failure_count}, Timeout: {self._get_current_timeout()}s]"
        )
        
        # Send notification
        await self._notify_state_change(previous_state, self.state)
    
    async def _transition_to_half_open(self) -> None:
        """Transition circuit breaker to HALF_OPEN state."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            return
        
        previous_state = self.state
        self.state = CircuitBreakerState.HALF_OPEN
        self.success_count = 0
        self.half_open_calls = 0
        
        # Update metrics
        self.metrics.state_changes += 1
        self.metrics.times_half_opened += 1
        self.metrics.recovery_attempts += 1
        self.last_state_change = datetime.now(timezone.utc)
        
        self.logger.info(
            f"Circuit '{self.name}' transitioned from {previous_state.value} to HALF_OPEN "
            f"(Testing recovery)"
        )
        
        # Perform health check if configured
        if self.health_check_func and self.config.recovery_strategy == RecoveryStrategy.AUTO_HEALTH_CHECK:
            try:
                if asyncio.iscoroutinefunction(self.health_check_func):
                    health_ok = await self.health_check_func()
                else:
                    health_ok = self.health_check_func()
                
                if health_ok:
                    self.logger.info(f"Circuit '{self.name}' health check passed")
                    # Don't immediately close, still need successful calls
                else:
                    self.logger.warning(f"Circuit '{self.name}' health check failed")
                    await self._transition_to_open()
                    return
            except Exception as e:
                self.logger.error(f"Circuit '{self.name}' health check error: {e}")
                await self._transition_to_open()
                return
        
        # Send notification
        await self._notify_state_change(previous_state, self.state)
    
    # =========================================================================
    # RECOVERY LOGIC
    # =========================================================================
    
    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if not self.last_failure_time:
            return True
        
        timeout = self._get_current_timeout()
        
        # Add jitter if configured
        if self.config.enable_jitter:
            jitter = random.uniform(0.9, 1.1)  # ±10% jitter
            timeout = timeout * jitter
        
        time_since_failure = (
            datetime.now(timezone.utc) - self.last_failure_time
        ).total_seconds()
        
        return time_since_failure >= timeout
    
    def _get_current_timeout(self) -> float:
        """Get current timeout with escalation applied."""
        base_timeout = self.config.timeout_seconds
        return base_timeout * self.current_timeout_multiplier
    
    # =========================================================================
    # METRICS AND MONITORING
    # =========================================================================
    
    def _calculate_error_rate(self) -> float:
        """Calculate current error rate from sliding window."""
        if not self.call_history:
            return 0.0
        
        failures = sum(1 for call in self.call_history if not call.success)
        return failures / len(self.call_history)
    
    def _update_latency_metrics(self, latency_ms: float) -> None:
        """Update latency metrics with new measurement."""
        # Simple moving average for now
        if self.metrics.avg_latency_ms == 0:
            self.metrics.avg_latency_ms = latency_ms
        else:
            # Exponential moving average
            alpha = 0.1  # Smoothing factor
            self.metrics.avg_latency_ms = (
                alpha * latency_ms + (1 - alpha) * self.metrics.avg_latency_ms
            )
        
        # Update percentiles (simplified - proper implementation would use reservoir sampling)
        latencies = [call.latency_ms for call in self.call_history]
        if latencies:
            latencies.sort()
            n = len(latencies)
            self.metrics.p50_latency_ms = latencies[n // 2]
            self.metrics.p95_latency_ms = latencies[int(n * 0.95)] if n > 20 else latencies[-1]
            self.metrics.p99_latency_ms = latencies[int(n * 0.99)] if n > 100 else latencies[-1]
    
    def calculate_error_rates(self) -> Tuple[float, float, float]:
        """
        Calculate error rates for different time windows.
        
        Returns:
            Tuple of (1min, 5min, 15min) error rates
        """
        now = datetime.now(timezone.utc)
        
        # Count failures in different windows
        one_min_ago = now - timedelta(minutes=1)
        five_min_ago = now - timedelta(minutes=5)
        fifteen_min_ago = now - timedelta(minutes=15)
        
        failures_1min = sum(
            1 for call in self.call_history 
            if not call.success and call.timestamp > one_min_ago
        )
        failures_5min = sum(
            1 for call in self.call_history 
            if not call.success and call.timestamp > five_min_ago
        )
        failures_15min = sum(
            1 for call in self.call_history 
            if not call.success and call.timestamp > fifteen_min_ago
        )
        
        # Count total calls in windows
        calls_1min = sum(1 for call in self.call_history if call.timestamp > one_min_ago)
        calls_5min = sum(1 for call in self.call_history if call.timestamp > five_min_ago)
        calls_15min = sum(1 for call in self.call_history if call.timestamp > fifteen_min_ago)
        
        # Calculate rates
        rate_1min = (failures_1min / calls_1min * 100) if calls_1min > 0 else 0
        rate_5min = (failures_5min / calls_5min * 100) if calls_5min > 0 else 0
        rate_15min = (failures_15min / calls_15min * 100) if calls_15min > 0 else 0
        
        # Update metrics
        self.metrics.error_rate_1min = rate_1min
        self.metrics.error_rate_5min = rate_5min
        self.metrics.error_rate_15min = rate_15min
        
        return rate_1min, rate_5min, rate_15min
    
    # =========================================================================
    # MANUAL CONTROLS
    # =========================================================================
    
    async def force_open(self, reason: str = "Manual intervention") -> None:
        """Manually force the circuit breaker open."""
        previous_state = self.state
        self.state = CircuitBreakerState.FORCED_OPEN
        self.metrics.state_changes += 1
        self.last_state_change = datetime.now(timezone.utc)
        
        self.logger.warning(f"Circuit '{self.name}' FORCED OPEN: {reason}")
        await self._notify_state_change(previous_state, self.state)
    
    async def force_closed(self, reason: str = "Manual intervention") -> None:
        """Manually force the circuit breaker closed."""
        previous_state = self.state
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.half_open_calls = 0
        self.current_timeout_multiplier = 1.0
        self.metrics.state_changes += 1
        self.last_state_change = datetime.now(timezone.utc)
        
        self.logger.warning(f"Circuit '{self.name}' FORCED CLOSED: {reason}")
        await self._notify_state_change(previous_state, self.state)
    
    async def disable(self) -> None:
        """Disable the circuit breaker (always allows calls through)."""
        previous_state = self.state
        self.state = CircuitBreakerState.DISABLED
        self.metrics.state_changes += 1
        self.last_state_change = datetime.now(timezone.utc)
        
        self.logger.info(f"Circuit '{self.name}' DISABLED")
        await self._notify_state_change(previous_state, self.state)
    
    async def enable(self) -> None:
        """Re-enable the circuit breaker."""
        if self.state != CircuitBreakerState.DISABLED:
            return
        
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.metrics.state_changes += 1
        self.last_state_change = datetime.now(timezone.utc)
        
        self.logger.info(f"Circuit '{self.name}' ENABLED")
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    async def _execute_function(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function (async or sync)."""
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    
    def _create_open_error(self, message: Optional[str] = None) -> CircuitBreakerOpenError:
        """Create a circuit breaker open error with context."""
        if message is None:
            timeout = self._get_current_timeout()
            retry_after = self.last_failure_time + timedelta(seconds=timeout) if self.last_failure_time else None
            message = (
                f"Circuit breaker '{self.name}' is {self.state.value}. "
                f"Will retry after {timeout:.0f} seconds."
            )
        
        return CircuitBreakerOpenError(
            message=message,
            breaker_name=self.name,
            retry_after=retry_after,
            failure_count=self.failure_count
        )
    
    async def _notify_state_change(
        self, 
        previous_state: CircuitBreakerState, 
        new_state: CircuitBreakerState
    ) -> None:
        """Send notification about state change."""
        if not self.notification_callback:
            return
        
        try:
            notification_data = {
                'breaker_name': self.name,
                'breaker_type': self.breaker_type.value,
                'previous_state': previous_state.value,
                'new_state': new_state.value,
                'failure_count': self.failure_count,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'metrics': self.metrics.to_dict()
            }
            
            if asyncio.iscoroutinefunction(self.notification_callback):
                await self.notification_callback(notification_data)
            else:
                self.notification_callback(notification_data)
                
        except Exception as e:
            self.logger.error(f"Failed to send notification: {e}")
    
    # =========================================================================
    # STATUS AND MONITORING
    # =========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        retry_after = None
        if self.state == CircuitBreakerState.OPEN and self.last_failure_time:
            timeout = self._get_current_timeout()
            retry_after = self.last_failure_time + timedelta(seconds=timeout)
        
        return {
            'name': self.name,
            'type': self.breaker_type.value,
            'state': self.state.value,
            'priority': self.config.priority.value,
            'failure_count': self.failure_count,
            'success_count': self.success_count,
            'last_failure': self.last_failure_time.isoformat() if self.last_failure_time else None,
            'last_success': self.last_success_time.isoformat() if self.last_success_time else None,
            'retry_after': retry_after.isoformat() if retry_after else None,
            'current_timeout': self._get_current_timeout(),
            'metrics': self.metrics.to_dict(),
            'config': {
                'failure_threshold': self.config.failure_threshold,
                'success_threshold': self.config.success_threshold,
                'timeout_seconds': self.config.timeout_seconds,
                'recovery_strategy': self.config.recovery_strategy.value,
            }
        }
    
    def is_healthy(self) -> bool:
        """Check if circuit breaker is in a healthy state."""
        return self.state in [CircuitBreakerState.CLOSED, CircuitBreakerState.DISABLED]
    
    def is_blocking(self) -> bool:
        """Check if circuit breaker is currently blocking calls."""
        return self.state in [CircuitBreakerState.OPEN, CircuitBreakerState.FORCED_OPEN]


# =============================================================================
# CONTEXT MANAGER SUPPORT
# =============================================================================

class circuit_breaker_context:
    """Context manager for circuit breaker operations."""
    
    def __init__(self, breaker: EnhancedCircuitBreaker):
        self.breaker = breaker
    
    async def __aenter__(self):
        return self.breaker
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Let the circuit breaker handle exceptions
        return False


# =============================================================================
# DECORATOR SUPPORT
# =============================================================================

def with_circuit_breaker(
    breaker: Optional[EnhancedCircuitBreaker] = None,
    **breaker_kwargs
) -> Callable:
    """
    Decorator to wrap functions with circuit breaker protection.
    
    Usage:
        @with_circuit_breaker(name="api_call", failure_threshold=3)
        async def make_api_call():
            ...
    
    Args:
        breaker: Existing circuit breaker instance
        **breaker_kwargs: Arguments to create new circuit breaker
    """
    def decorator(func: Callable) -> Callable:
        # Create or use existing breaker
        cb = breaker
        if cb is None:
            name = breaker_kwargs.pop('name', func.__name__)
            cb = EnhancedCircuitBreaker(name=name, **breaker_kwargs)
        
        async def async_wrapper(*args, **kwargs):
            return await cb.call(func, *args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            # For sync functions, we need to run in event loop
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(cb.call(func, *args, **kwargs))
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator