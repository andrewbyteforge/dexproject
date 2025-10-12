"""
Circuit Breaker Manager

Centralized management of all circuit breakers in the system.
Coordinates breakers, handles cascading failures, and provides bulk operations.

File: shared/circuit_breakers/manager.py
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import (
    Any, Callable, Dict, List, Optional, Set, Tuple, Union
)

from .config import (
    CircuitBreakerType,
    CircuitBreakerConfig,
    CircuitBreakerDefaults,
    CircuitBreakerPriority,
    CircuitBreakerGroup,
    BREAKER_GROUPS,
    NotificationConfig,
    RecoveryStrategy,
)
from .enhanced_breaker import (
    EnhancedCircuitBreaker,
    CircuitBreakerState,
    CircuitBreakerMetrics,
    CircuitBreakerOpenError,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CIRCUIT BREAKER EVENTS
# =============================================================================

@dataclass
class CircuitBreakerEvent:
    """
    Represents a circuit breaker event for tracking and notification.
    
    Attributes:
        breaker_name: Name of the circuit breaker
        breaker_type: Type of circuit breaker
        event_type: Type of event (opened, closed, etc.)
        timestamp: When the event occurred
        details: Additional event details
        user_id: Optional user ID associated with event
        chain_id: Optional chain ID for blockchain-specific breakers
    """
    breaker_name: str
    breaker_type: CircuitBreakerType
    event_type: str  # "opened", "closed", "half_open", "forced_open", etc.
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[int] = None
    chain_id: Optional[int] = None
    priority: CircuitBreakerPriority = CircuitBreakerPriority.MEDIUM
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            'breaker_name': self.breaker_name,
            'breaker_type': self.breaker_type.value,
            'event_type': self.event_type,
            'timestamp': self.timestamp.isoformat(),
            'details': self.details,
            'user_id': self.user_id,
            'chain_id': self.chain_id,
            'priority': self.priority.value,
        }


# =============================================================================
# CIRCUIT BREAKER REGISTRY
# =============================================================================

class CircuitBreakerRegistry:
    """
    Registry for all circuit breakers in the system.
    Provides lookup and management capabilities.
    """
    
    def __init__(self):
        """Initialize the registry."""
        # Main storage: name -> breaker
        self._breakers: Dict[str, EnhancedCircuitBreaker] = {}
        
        # Type mapping: breaker_type -> list of breaker names
        self._type_index: Dict[CircuitBreakerType, List[str]] = defaultdict(list)
        
        # Group mapping: group -> list of breaker names
        self._group_index: Dict[CircuitBreakerGroup, List[str]] = defaultdict(list)
        
        # User-specific breakers: user_id -> list of breaker names
        self._user_breakers: Dict[int, List[str]] = defaultdict(list)
        
        # Chain-specific breakers: chain_id -> list of breaker names
        self._chain_breakers: Dict[int, List[str]] = defaultdict(list)
        
        self.logger = logging.getLogger(f"{__name__}.registry")
    
    def register(
        self,
        breaker: EnhancedCircuitBreaker,
        user_id: Optional[int] = None,
        chain_id: Optional[int] = None
    ) -> None:
        """
        Register a circuit breaker in the registry.
        
        Args:
            breaker: Circuit breaker instance
            user_id: Optional user ID for user-specific breakers
            chain_id: Optional chain ID for chain-specific breakers
        """
        name = breaker.name
        breaker_type = breaker.breaker_type
        
        # Store in main registry
        self._breakers[name] = breaker
        
        # Update type index
        if name not in self._type_index[breaker_type]:
            self._type_index[breaker_type].append(name)
        
        # Update group indices
        for group, types in BREAKER_GROUPS.items():
            if breaker_type in types and name not in self._group_index[group]:
                self._group_index[group].append(name)
        
        # Update user index if applicable
        if user_id is not None and name not in self._user_breakers[user_id]:
            self._user_breakers[user_id].append(name)
        
        # Update chain index if applicable
        if chain_id is not None and name not in self._chain_breakers[chain_id]:
            self._chain_breakers[chain_id].append(name)
        
        self.logger.info(
            f"Registered circuit breaker '{name}' "
            f"[Type: {breaker_type.value}, User: {user_id}, Chain: {chain_id}]"
        )
    
    def unregister(self, name: str) -> Optional[EnhancedCircuitBreaker]:
        """
        Unregister a circuit breaker from the registry.
        
        Args:
            name: Name of the circuit breaker
            
        Returns:
            The unregistered breaker or None if not found
        """
        breaker = self._breakers.pop(name, None)
        if not breaker:
            return None
        
        # Clean up indices
        breaker_type = breaker.breaker_type
        
        # Remove from type index
        if name in self._type_index[breaker_type]:
            self._type_index[breaker_type].remove(name)
        
        # Remove from group indices
        for group in self._group_index:
            if name in self._group_index[group]:
                self._group_index[group].remove(name)
        
        # Remove from user indices
        for user_id in self._user_breakers:
            if name in self._user_breakers[user_id]:
                self._user_breakers[user_id].remove(name)
        
        # Remove from chain indices
        for chain_id in self._chain_breakers:
            if name in self._chain_breakers[chain_id]:
                self._chain_breakers[chain_id].remove(name)
        
        self.logger.info(f"Unregistered circuit breaker '{name}'")
        return breaker
    
    def get(self, name: str) -> Optional[EnhancedCircuitBreaker]:
        """Get a circuit breaker by name."""
        return self._breakers.get(name)
    
    def get_by_type(self, breaker_type: CircuitBreakerType) -> List[EnhancedCircuitBreaker]:
        """Get all circuit breakers of a specific type."""
        names = self._type_index.get(breaker_type, [])
        return [self._breakers[name] for name in names if name in self._breakers]
    
    def get_by_group(self, group: CircuitBreakerGroup) -> List[EnhancedCircuitBreaker]:
        """Get all circuit breakers in a specific group."""
        names = self._group_index.get(group, [])
        return [self._breakers[name] for name in names if name in self._breakers]
    
    def get_by_user(self, user_id: int) -> List[EnhancedCircuitBreaker]:
        """Get all circuit breakers for a specific user."""
        names = self._user_breakers.get(user_id, [])
        return [self._breakers[name] for name in names if name in self._breakers]
    
    def get_by_chain(self, chain_id: int) -> List[EnhancedCircuitBreaker]:
        """Get all circuit breakers for a specific chain."""
        names = self._chain_breakers.get(chain_id, [])
        return [self._breakers[name] for name in names if name in self._breakers]
    
    def get_all(self) -> Dict[str, EnhancedCircuitBreaker]:
        """Get all registered circuit breakers."""
        return self._breakers.copy()


# =============================================================================
# CIRCUIT BREAKER MANAGER
# =============================================================================

class CircuitBreakerManager:
    """
    Centralized manager for all circuit breakers in the system.
    
    Features:
        - Automatic breaker creation and registration
        - Cascading failure detection
        - Group operations
        - Event tracking and notifications
        - Health monitoring
        - Persistence support
    """
    
    def __init__(
        self,
        notification_config: Optional[NotificationConfig] = None,
        persistence_enabled: bool = True,
        auto_create_breakers: bool = True
    ):
        """
        Initialize the circuit breaker manager.
        
        Args:
            notification_config: Configuration for notifications
            persistence_enabled: Whether to persist breaker states
            auto_create_breakers: Automatically create default breakers
        """
        self.registry = CircuitBreakerRegistry()
        self.notification_config = notification_config or NotificationConfig()
        self.persistence_enabled = persistence_enabled
        
        # Event tracking
        self.event_history: List[CircuitBreakerEvent] = []
        self.max_event_history = 1000
        
        # Cascading failure detection
        self.cascade_detection_enabled = True
        self.cascade_threshold = 3  # Number of breakers that trigger cascade
        self.cascade_window_seconds = 60  # Time window for cascade detection
        
        # Statistics
        self.total_events = 0
        self.total_opens = 0
        self.total_closes = 0
        self.total_resets = 0
        
        # Notification handling
        self.notification_callbacks: List[Callable] = []
        self.websocket_callbacks: List[Callable] = []
        
        # Lock for thread safety
        self.lock = asyncio.Lock()
        
        self.logger = logging.getLogger(f"{__name__}.manager")
        
        # Auto-create default breakers if enabled
        if auto_create_breakers:
            asyncio.create_task(self._initialize_default_breakers())
        
        self.logger.info(
            f"Circuit Breaker Manager initialized "
            f"[Persistence: {persistence_enabled}, Auto-create: {auto_create_breakers}]"
        )
    
    # =========================================================================
    # INITIALIZATION
    # =========================================================================
    
    async def _initialize_default_breakers(self) -> None:
        """Initialize default circuit breakers based on configuration."""
        try:
            # Create critical breakers first
            critical_types = [
                CircuitBreakerType.RPC_FAILURE,
                CircuitBreakerType.DATABASE_FAILURE,
                CircuitBreakerType.PORTFOLIO_LOSS,
                CircuitBreakerType.MANUAL_EMERGENCY_STOP,
            ]
            
            for breaker_type in critical_types:
                await self.create_breaker(
                    name=f"default_{breaker_type.value.lower()}",
                    breaker_type=breaker_type
                )
            
            self.logger.info(f"Initialized {len(critical_types)} critical circuit breakers")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize default breakers: {e}")
    
    # =========================================================================
    # BREAKER CREATION AND MANAGEMENT
    # =========================================================================
    
    async def create_breaker(
        self,
        name: str,
        breaker_type: CircuitBreakerType,
        config: Optional[CircuitBreakerConfig] = None,
        user_id: Optional[int] = None,
        chain_id: Optional[int] = None,
        health_check_func: Optional[Callable] = None
    ) -> EnhancedCircuitBreaker:
        """
        Create and register a new circuit breaker.
        
        Args:
            name: Unique name for the breaker
            breaker_type: Type of circuit breaker
            config: Optional configuration (uses defaults if None)
            user_id: Optional user ID for user-specific breakers
            chain_id: Optional chain ID for chain-specific breakers
            health_check_func: Optional health check function
            
        Returns:
            The created circuit breaker
        """
        async with self.lock:
            # Check if breaker already exists
            existing = self.registry.get(name)
            if existing:
                self.logger.warning(f"Circuit breaker '{name}' already exists")
                return existing
            
            # Get configuration
            if config is None:
                config = CircuitBreakerDefaults.get_config(breaker_type)
            
            # Create notification callback
            async def notification_callback(data: Dict[str, Any]):
                await self._handle_breaker_state_change(name, data)
            
            # Create the breaker
            breaker = EnhancedCircuitBreaker(
                name=name,
                config=config,
                breaker_type=breaker_type,
                health_check_func=health_check_func,
                notification_callback=notification_callback
            )
            
            # Register it
            self.registry.register(breaker, user_id, chain_id)
            
            # Load persisted state if available
            if self.persistence_enabled:
                await self._load_breaker_state(breaker)
            
            self.logger.info(f"Created circuit breaker '{name}' of type {breaker_type.value}")
            return breaker
    
    async def get_or_create_breaker(
        self,
        name: str,
        breaker_type: CircuitBreakerType,
        **kwargs
    ) -> EnhancedCircuitBreaker:
        """Get an existing breaker or create a new one."""
        breaker = self.registry.get(name)
        if breaker:
            return breaker
        return await self.create_breaker(name, breaker_type, **kwargs)
    
    # =========================================================================
    # BREAKER OPERATIONS
    # =========================================================================
    
    async def check_breakers(
        self,
        breaker_types: Optional[List[CircuitBreakerType]] = None,
        user_id: Optional[int] = None,
        chain_id: Optional[int] = None
    ) -> Tuple[bool, List[str]]:
        """
        Check if trading/operations can proceed based on circuit breakers.
        
        Args:
            breaker_types: Specific breaker types to check (None = all)
            user_id: Check user-specific breakers
            chain_id: Check chain-specific breakers
            
        Returns:
            Tuple of (can_proceed, list_of_blocking_reasons)
        """
        blocking_reasons = []
        
        # Get relevant breakers
        breakers_to_check = []
        
        if breaker_types:
            for breaker_type in breaker_types:
                breakers_to_check.extend(self.registry.get_by_type(breaker_type))
        else:
            breakers_to_check = list(self.registry.get_all().values())
        
        # Add user-specific breakers
        if user_id is not None:
            breakers_to_check.extend(self.registry.get_by_user(user_id))
        
        # Add chain-specific breakers
        if chain_id is not None:
            breakers_to_check.extend(self.registry.get_by_chain(chain_id))
        
        # Remove duplicates
        seen = set()
        unique_breakers = []
        for breaker in breakers_to_check:
            if breaker.name not in seen:
                seen.add(breaker.name)
                unique_breakers.append(breaker)
        
        # Check each breaker
        for breaker in unique_breakers:
            if breaker.is_blocking():
                reason = (
                    f"{breaker.breaker_type.value}: {breaker.name} is {breaker.state.value} "
                    f"(Failed {breaker.failure_count} times)"
                )
                blocking_reasons.append(reason)
        
        can_proceed = len(blocking_reasons) == 0
        return can_proceed, blocking_reasons
    
    async def reset_breaker(
        self,
        name: Optional[str] = None,
        breaker_type: Optional[CircuitBreakerType] = None,
        group: Optional[CircuitBreakerGroup] = None,
        user_id: Optional[int] = None,
        force: bool = False
    ) -> int:
        """
        Reset circuit breakers.
        
        Args:
            name: Specific breaker name to reset
            breaker_type: Reset all breakers of this type
            group: Reset all breakers in this group
            user_id: Reset all breakers for this user
            force: Force reset even if in FORCED_OPEN state
            
        Returns:
            Number of breakers reset
        """
        async with self.lock:
            breakers_to_reset = []
            
            if name:
                breaker = self.registry.get(name)
                if breaker:
                    breakers_to_reset.append(breaker)
            elif breaker_type:
                breakers_to_reset = self.registry.get_by_type(breaker_type)
            elif group:
                breakers_to_reset = self.registry.get_by_group(group)
            elif user_id is not None:
                breakers_to_reset = self.registry.get_by_user(user_id)
            else:
                # Reset all breakers
                breakers_to_reset = list(self.registry.get_all().values())
            
            reset_count = 0
            for breaker in breakers_to_reset:
                if force or breaker.state != CircuitBreakerState.FORCED_OPEN:
                    await breaker.force_closed(reason="Manual reset via manager")
                    reset_count += 1
                    
                    # Record event
                    event = CircuitBreakerEvent(
                        breaker_name=breaker.name,
                        breaker_type=breaker.breaker_type,
                        event_type="reset",
                        details={"forced": force}
                    )
                    await self._record_event(event)
            
            self.total_resets += reset_count
            self.logger.info(f"Reset {reset_count} circuit breakers")
            return reset_count
    
    async def force_open_group(
        self,
        group: CircuitBreakerGroup,
        reason: str = "Group force open"
    ) -> int:
        """Force open all breakers in a group."""
        breakers = self.registry.get_by_group(group)
        for breaker in breakers:
            await breaker.force_open(reason)
        
        self.logger.warning(f"Force opened {len(breakers)} breakers in group {group.value}")
        return len(breakers)
    
    # =========================================================================
    # CASCADE DETECTION
    # =========================================================================
    
    async def _check_cascade_condition(self) -> bool:
        """
        Check if cascade failure conditions are met.
        
        Returns:
            True if cascade is detected
        """
        if not self.cascade_detection_enabled:
            return False
        
        # Count recent open events
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=self.cascade_window_seconds)
        recent_opens = [
            event for event in self.event_history
            if event.event_type == "opened" and event.timestamp > cutoff_time
        ]
        
        if len(recent_opens) >= self.cascade_threshold:
            self.logger.critical(
                f"CASCADE FAILURE DETECTED: {len(recent_opens)} breakers opened "
                f"in {self.cascade_window_seconds} seconds"
            )
            return True
        
        return False
    
    async def _handle_cascade_failure(self) -> None:
        """Handle cascade failure by opening critical breakers."""
        # Open all HIGH and CRITICAL priority breakers
        critical_breakers = []
        for breaker in self.registry.get_all().values():
            if breaker.config.priority.value >= CircuitBreakerPriority.HIGH.value:
                if not breaker.is_blocking():
                    await breaker.force_open("Cascade failure detected")
                    critical_breakers.append(breaker.name)
        
        self.logger.critical(
            f"Cascade failure response: Opened {len(critical_breakers)} critical breakers"
        )
        
        # Send emergency notification
        await self._send_emergency_notification({
            'type': 'CASCADE_FAILURE',
            'affected_breakers': critical_breakers,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    # =========================================================================
    # EVENT HANDLING
    # =========================================================================
    
    async def _handle_breaker_state_change(
        self,
        breaker_name: str,
        data: Dict[str, Any]
    ) -> None:
        """Handle state change notification from a circuit breaker."""
        # Create event
        breaker = self.registry.get(breaker_name)
        if not breaker:
            return
        
        event = CircuitBreakerEvent(
            breaker_name=breaker_name,
            breaker_type=breaker.breaker_type,
            event_type=data.get('new_state', '').lower(),
            details=data,
            priority=breaker.config.priority
        )
        
        await self._record_event(event)
        
        # Update statistics
        if event.event_type == "open":
            self.total_opens += 1
            # Check for cascade
            if await self._check_cascade_condition():
                await self._handle_cascade_failure()
        elif event.event_type == "closed":
            self.total_closes += 1
        
        # Send notifications based on priority
        if event.priority.value >= self.notification_config.email_priority_threshold.value:
            await self._send_email_notification(event)
        
        if event.priority.value >= self.notification_config.slack_priority_threshold.value:
            await self._send_slack_notification(event)
        
        # Always send WebSocket notifications if enabled
        if self.notification_config.websocket_enabled:
            await self._send_websocket_notification(event)
        
        # Persist state if enabled
        if self.persistence_enabled:
            await self._persist_breaker_state(breaker)
    
    async def _record_event(self, event: CircuitBreakerEvent) -> None:
        """Record a circuit breaker event."""
        self.event_history.append(event)
        self.total_events += 1
        
        # Trim history if needed
        if len(self.event_history) > self.max_event_history:
            self.event_history = self.event_history[-self.max_event_history:]
        
        # Log to database if enabled
        if self.notification_config.database_logging:
            await self._log_event_to_database(event)
    
    # =========================================================================
    # NOTIFICATIONS
    # =========================================================================
    
    async def _send_websocket_notification(self, event: CircuitBreakerEvent) -> None:
        """Send WebSocket notification for circuit breaker event."""
        for callback in self.websocket_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event.to_dict())
                else:
                    callback(event.to_dict())
            except Exception as e:
                self.logger.error(f"WebSocket notification failed: {e}")
    
    async def _send_email_notification(self, event: CircuitBreakerEvent) -> None:
        """Send email notification for critical events."""
        if not self.notification_config.email_enabled:
            return
        
        # TODO: Implement email sending
        self.logger.info(f"Email notification would be sent for {event.breaker_name}")
    
    async def _send_slack_notification(self, event: CircuitBreakerEvent) -> None:
        """Send Slack notification for important events."""
        if not self.notification_config.slack_enabled:
            return
        
        # TODO: Implement Slack webhook
        self.logger.info(f"Slack notification would be sent for {event.breaker_name}")
    
    async def _send_emergency_notification(self, data: Dict[str, Any]) -> None:
        """Send emergency notification through all channels."""
        self.logger.critical(f"EMERGENCY NOTIFICATION: {data}")
        
        # Send through all available channels
        for callback in self.notification_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback({'emergency': True, **data})
                else:
                    callback({'emergency': True, **data})
            except Exception as e:
                self.logger.error(f"Emergency notification failed: {e}")
    
    # =========================================================================
    # PERSISTENCE
    # =========================================================================
    
    async def _persist_breaker_state(self, breaker: EnhancedCircuitBreaker) -> None:
        """Persist circuit breaker state to database."""
        if not self.persistence_enabled:
            return
        
        try:
            # TODO: Implement actual database persistence
            # This would save to CircuitBreakerStateModel
            state_data = {
                'name': breaker.name,
                'state': breaker.state.value,
                'failure_count': breaker.failure_count,
                'last_failure_time': breaker.last_failure_time,
                'metrics': breaker.metrics.to_dict()
            }
            self.logger.debug(f"Would persist state for {breaker.name}: {state_data}")
        except Exception as e:
            self.logger.error(f"Failed to persist breaker state: {e}")
    
    async def _load_breaker_state(self, breaker: EnhancedCircuitBreaker) -> None:
        """Load persisted circuit breaker state from database."""
        if not self.persistence_enabled:
            return
        
        try:
            # TODO: Implement actual database loading
            # This would load from CircuitBreakerStateModel
            self.logger.debug(f"Would load persisted state for {breaker.name}")
        except Exception as e:
            self.logger.error(f"Failed to load breaker state: {e}")
    
    async def _log_event_to_database(self, event: CircuitBreakerEvent) -> None:
        """Log event to database for audit trail."""
        try:
            # TODO: Implement actual database logging
            # This would save to CircuitBreakerEventModel
            self.logger.debug(f"Would log event to database: {event.to_dict()}")
        except Exception as e:
            self.logger.error(f"Failed to log event to database: {e}")
    
    # =========================================================================
    # MONITORING AND STATUS
    # =========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get overall circuit breaker system status."""
        all_breakers = self.registry.get_all()
        
        # Count breakers by state
        state_counts = defaultdict(int)
        for breaker in all_breakers.values():
            state_counts[breaker.state.value] += 1
        
        # Get blocking breakers
        blocking_breakers = [
            {
                'name': b.name,
                'type': b.breaker_type.value,
                'state': b.state.value,
                'failure_count': b.failure_count
            }
            for b in all_breakers.values()
            if b.is_blocking()
        ]
        
        # Get recent events
        recent_events = [
            event.to_dict()
            for event in self.event_history[-10:]  # Last 10 events
        ]
        
        return {
            'total_breakers': len(all_breakers),
            'state_counts': dict(state_counts),
            'blocking_breakers': blocking_breakers,
            'can_trade': len(blocking_breakers) == 0,
            'cascade_detection_enabled': self.cascade_detection_enabled,
            'recent_events': recent_events,
            'statistics': {
                'total_events': self.total_events,
                'total_opens': self.total_opens,
                'total_closes': self.total_closes,
                'total_resets': self.total_resets,
            }
        }
    
    def get_health_report(self) -> Dict[str, Any]:
        """Generate a health report for all circuit breakers."""
        all_breakers = self.registry.get_all()
        
        healthy_count = sum(1 for b in all_breakers.values() if b.is_healthy())
        blocking_count = sum(1 for b in all_breakers.values() if b.is_blocking())
        
        # Calculate overall health score (0-100)
        if len(all_breakers) > 0:
            health_score = (healthy_count / len(all_breakers)) * 100
        else:
            health_score = 100
        
        # Get problematic breakers
        problematic = []
        for breaker in all_breakers.values():
            if breaker.metrics.error_rate_1min > 50:  # >50% error rate
                problematic.append({
                    'name': breaker.name,
                    'error_rate_1min': breaker.metrics.error_rate_1min,
                    'state': breaker.state.value
                })
        
        return {
            'health_score': health_score,
            'total_breakers': len(all_breakers),
            'healthy_breakers': healthy_count,
            'blocking_breakers': blocking_count,
            'problematic_breakers': problematic,
            'cascade_risk': len(problematic) >= self.cascade_threshold,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    async def run_health_checks(self) -> Dict[str, bool]:
        """Run health checks for all breakers that have them configured."""
        results = {}
        
        for name, breaker in self.registry.get_all().items():
            if breaker.health_check_func:
                try:
                    if asyncio.iscoroutinefunction(breaker.health_check_func):
                        health_ok = await breaker.health_check_func()
                    else:
                        health_ok = breaker.health_check_func()
                    results[name] = health_ok
                except Exception as e:
                    self.logger.error(f"Health check failed for {name}: {e}")
                    results[name] = False
        
        return results
    
    # =========================================================================
    # CALLBACK MANAGEMENT
    # =========================================================================
    
    def add_notification_callback(self, callback: Callable) -> None:
        """Add a general notification callback."""
        self.notification_callbacks.append(callback)
    
    def add_websocket_callback(self, callback: Callable) -> None:
        """Add a WebSocket notification callback."""
        self.websocket_callbacks.append(callback)
    
    def remove_notification_callback(self, callback: Callable) -> None:
        """Remove a notification callback."""
        if callback in self.notification_callbacks:
            self.notification_callbacks.remove(callback)
    
    def remove_websocket_callback(self, callback: Callable) -> None:
        """Remove a WebSocket callback."""
        if callback in self.websocket_callbacks:
            self.websocket_callbacks.remove(callback)


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

# Global manager instance
_manager_instance: Optional[CircuitBreakerManager] = None
_manager_lock = asyncio.Lock()


async def get_manager() -> CircuitBreakerManager:
    """
    Get the singleton circuit breaker manager instance.
    
    Returns:
        The global circuit breaker manager
    """
    global _manager_instance
    
    if _manager_instance is None:
        async with _manager_lock:
            if _manager_instance is None:
                _manager_instance = CircuitBreakerManager()
                logger.info("Created singleton CircuitBreakerManager instance")
    
    return _manager_instance


async def reset_manager() -> None:
    """Reset the singleton manager (mainly for testing)."""
    global _manager_instance
    async with _manager_lock:
        _manager_instance = None
        logger.info("Reset singleton CircuitBreakerManager instance")