"""
Circuit Breaker Persistence Layer

Database persistence for circuit breaker states and events.
Integrates with Django models for state management and audit logging.

File: shared/circuit_breakers/persistence.py
"""

import json
import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Type, Union

from django.db import models, transaction
from django.core.cache import cache
from django.contrib.postgres.fields import JSONField
from django.utils import timezone as django_timezone

from .config import (
    CircuitBreakerType,
    CircuitBreakerPriority,
    RecoveryStrategy,
)
from .enhanced_breaker import (
    CircuitBreakerState,
    CircuitBreakerMetrics,
)

logger = logging.getLogger(__name__)


# =============================================================================
# DJANGO MODELS
# =============================================================================

class CircuitBreakerStateModel(models.Model):
    """
    Django model for persisting circuit breaker states.
    
    Stores the current state of each circuit breaker for recovery
    after system restarts.
    """
    
    # Identification
    name = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique name of the circuit breaker"
    )
    breaker_type = models.CharField(
        max_length=50,
        choices=[(t.value, t.value) for t in CircuitBreakerType],
        db_index=True,
        help_text="Type of circuit breaker"
    )
    
    # State information
    state = models.CharField(
        max_length=20,
        choices=[(s.value, s.value) for s in CircuitBreakerState],
        default=CircuitBreakerState.CLOSED.value,
        help_text="Current state of the circuit breaker"
    )
    failure_count = models.IntegerField(
        default=0,
        help_text="Current failure count"
    )
    success_count = models.IntegerField(
        default=0,
        help_text="Current success count (for half-open state)"
    )
    
    # Timing information
    last_failure_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Time of last failure"
    )
    last_success_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Time of last success"
    )
    last_state_change = models.DateTimeField(
        default=django_timezone.now,
        help_text="Time of last state change"
    )
    
    # Metrics (stored as JSON)
    metrics_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Serialized metrics data"
    )
    
    # Escalation state
    current_timeout_multiplier = models.FloatField(
        default=1.0,
        help_text="Current timeout escalation multiplier"
    )
    consecutive_timeouts = models.IntegerField(
        default=0,
        help_text="Number of consecutive timeout escalations"
    )
    
    # Association (optional)
    user_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Associated user ID (for user-specific breakers)"
    )
    chain_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Associated chain ID (for chain-specific breakers)"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this breaker is currently active"
    )
    
    class Meta:
        db_table = 'circuit_breaker_states'
        indexes = [
            models.Index(fields=['breaker_type', 'state']),
            models.Index(fields=['user_id', 'is_active']),
            models.Index(fields=['chain_id', 'is_active']),
        ]
        verbose_name = 'Circuit Breaker State'
        verbose_name_plural = 'Circuit Breaker States'
    
    def __str__(self):
        return f"{self.name} ({self.state})"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary."""
        return {
            'name': self.name,
            'breaker_type': self.breaker_type,
            'state': self.state,
            'failure_count': self.failure_count,
            'success_count': self.success_count,
            'last_failure_time': self.last_failure_time.isoformat() if self.last_failure_time else None,
            'last_success_time': self.last_success_time.isoformat() if self.last_success_time else None,
            'last_state_change': self.last_state_change.isoformat(),
            'metrics_data': self.metrics_data,
            'current_timeout_multiplier': self.current_timeout_multiplier,
            'consecutive_timeouts': self.consecutive_timeouts,
            'user_id': self.user_id,
            'chain_id': self.chain_id,
            'is_active': self.is_active,
        }


class CircuitBreakerEventModel(models.Model):
    """
    Django model for circuit breaker event logging.
    
    Provides an audit trail of all circuit breaker state changes
    and important events.
    """
    
    # Event identification
    breaker_name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Name of the circuit breaker"
    )
    breaker_type = models.CharField(
        max_length=50,
        choices=[(t.value, t.value) for t in CircuitBreakerType],
        db_index=True,
        help_text="Type of circuit breaker"
    )
    
    # Event details
    event_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Type of event (opened, closed, half_open, reset, etc.)"
    )
    priority = models.CharField(
        max_length=20,
        choices=[(p.value, p.value) for p in CircuitBreakerPriority],
        default=CircuitBreakerPriority.MEDIUM.value,
        help_text="Event priority level"
    )
    
    # Event data
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional event details"
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text="Error message if applicable"
    )
    
    # Context
    failure_count = models.IntegerField(
        default=0,
        help_text="Failure count at time of event"
    )
    previous_state = models.CharField(
        max_length=20,
        choices=[(s.value, s.value) for s in CircuitBreakerState],
        null=True,
        blank=True,
        help_text="Previous state before event"
    )
    new_state = models.CharField(
        max_length=20,
        choices=[(s.value, s.value) for s in CircuitBreakerState],
        null=True,
        blank=True,
        help_text="New state after event"
    )
    
    # Association
    user_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Associated user ID"
    )
    chain_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Associated chain ID"
    )
    
    # Timestamp
    timestamp = models.DateTimeField(
        default=django_timezone.now,
        db_index=True,
        help_text="When the event occurred"
    )
    
    class Meta:
        db_table = 'circuit_breaker_events'
        indexes = [
            models.Index(fields=['breaker_name', '-timestamp']),
            models.Index(fields=['event_type', '-timestamp']),
            models.Index(fields=['user_id', '-timestamp']),
            models.Index(fields=['-timestamp']),
        ]
        ordering = ['-timestamp']
        verbose_name = 'Circuit Breaker Event'
        verbose_name_plural = 'Circuit Breaker Events'
    
    def __str__(self):
        return f"{self.breaker_name} - {self.event_type} at {self.timestamp}"


class CircuitBreakerMetricsSnapshot(models.Model):
    """
    Django model for periodic metrics snapshots.
    
    Stores historical metrics for analysis and reporting.
    """
    
    breaker_name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Name of the circuit breaker"
    )
    
    # Timing
    snapshot_time = models.DateTimeField(
        default=django_timezone.now,
        db_index=True,
        help_text="When this snapshot was taken"
    )
    period_start = models.DateTimeField(
        help_text="Start of the metrics period"
    )
    period_end = models.DateTimeField(
        help_text="End of the metrics period"
    )
    
    # Metrics
    total_calls = models.IntegerField(default=0)
    successful_calls = models.IntegerField(default=0)
    failed_calls = models.IntegerField(default=0)
    rejected_calls = models.IntegerField(default=0)
    
    # Rates
    success_rate = models.FloatField(default=0.0)
    error_rate = models.FloatField(default=0.0)
    error_rate_1min = models.FloatField(default=0.0)
    error_rate_5min = models.FloatField(default=0.0)
    error_rate_15min = models.FloatField(default=0.0)
    
    # Latency
    avg_latency_ms = models.FloatField(default=0.0)
    p50_latency_ms = models.FloatField(default=0.0)
    p95_latency_ms = models.FloatField(default=0.0)
    p99_latency_ms = models.FloatField(default=0.0)
    
    # State information
    state_changes = models.IntegerField(default=0)
    times_opened = models.IntegerField(default=0)
    total_open_time_seconds = models.FloatField(default=0.0)
    
    class Meta:
        db_table = 'circuit_breaker_metrics'
        indexes = [
            models.Index(fields=['breaker_name', '-snapshot_time']),
            models.Index(fields=['-snapshot_time']),
        ]
        ordering = ['-snapshot_time']
        verbose_name = 'Circuit Breaker Metrics Snapshot'
        verbose_name_plural = 'Circuit Breaker Metrics Snapshots'


# =============================================================================
# PERSISTENCE MANAGER
# =============================================================================

class CircuitBreakerPersistence:
    """
    Manages persistence of circuit breaker states and events.
    
    Features:
        - Save/load circuit breaker states
        - Log events to database
        - Cache frequently accessed states
        - Periodic metrics snapshots
        - Cleanup of old data
    """
    
    def __init__(
        self,
        cache_enabled: bool = True,
        cache_ttl: int = 300,  # 5 minutes
        auto_cleanup: bool = True,
        cleanup_days: int = 30  # Keep 30 days of history
    ):
        """
        Initialize the persistence manager.
        
        Args:
            cache_enabled: Whether to use cache for state reads
            cache_ttl: Cache time-to-live in seconds
            auto_cleanup: Whether to auto-cleanup old data
            cleanup_days: Days of history to keep
        """
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl
        self.auto_cleanup = auto_cleanup
        self.cleanup_days = cleanup_days
        
        self.logger = logging.getLogger(f"{__name__}.persistence")
        
    # =========================================================================
    # STATE PERSISTENCE
    # =========================================================================
    
    async def save_state(
        self,
        breaker_name: str,
        breaker_type: CircuitBreakerType,
        state: CircuitBreakerState,
        failure_count: int,
        success_count: int,
        metrics: Optional[CircuitBreakerMetrics] = None,
        last_failure_time: Optional[datetime] = None,
        last_success_time: Optional[datetime] = None,
        current_timeout_multiplier: float = 1.0,
        consecutive_timeouts: int = 0,
        user_id: Optional[int] = None,
        chain_id: Optional[int] = None
    ) -> bool:
        """
        Save circuit breaker state to database.
        
        Returns:
            True if save was successful
        """
        try:
            with transaction.atomic():
                state_obj, created = CircuitBreakerStateModel.objects.update_or_create(
                    name=breaker_name,
                    defaults={
                        'breaker_type': breaker_type.value,
                        'state': state.value,
                        'failure_count': failure_count,
                        'success_count': success_count,
                        'last_failure_time': last_failure_time,
                        'last_success_time': last_success_time,
                        'last_state_change': datetime.now(timezone.utc),
                        'metrics_data': metrics.to_dict() if metrics else {},
                        'current_timeout_multiplier': current_timeout_multiplier,
                        'consecutive_timeouts': consecutive_timeouts,
                        'user_id': user_id,
                        'chain_id': chain_id,
                        'is_active': True,
                    }
                )
                
                # Update cache if enabled
                if self.cache_enabled:
                    cache_key = self._get_cache_key(breaker_name)
                    cache.set(cache_key, state_obj.to_dict(), self.cache_ttl)
                
                self.logger.debug(
                    f"Saved state for {breaker_name}: {state.value} "
                    f"(Created: {created})"
                )
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to save state for {breaker_name}: {e}")
            return False
    
    async def load_state(
        self,
        breaker_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Load circuit breaker state from database.
        
        Args:
            breaker_name: Name of the circuit breaker
            
        Returns:
            State dictionary or None if not found
        """
        try:
            # Check cache first
            if self.cache_enabled:
                cache_key = self._get_cache_key(breaker_name)
                cached_state = cache.get(cache_key)
                if cached_state:
                    self.logger.debug(f"Loaded state for {breaker_name} from cache")
                    return cached_state
            
            # Load from database
            state_obj = CircuitBreakerStateModel.objects.filter(
                name=breaker_name,
                is_active=True
            ).first()
            
            if state_obj:
                state_dict = state_obj.to_dict()
                
                # Update cache
                if self.cache_enabled:
                    cache_key = self._get_cache_key(breaker_name)
                    cache.set(cache_key, state_dict, self.cache_ttl)
                
                self.logger.debug(f"Loaded state for {breaker_name} from database")
                return state_dict
            
            self.logger.debug(f"No persisted state found for {breaker_name}")
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to load state for {breaker_name}: {e}")
            return None
    
    async def load_all_states(
        self,
        user_id: Optional[int] = None,
        chain_id: Optional[int] = None,
        breaker_type: Optional[CircuitBreakerType] = None
    ) -> List[Dict[str, Any]]:
        """
        Load all active circuit breaker states.
        
        Args:
            user_id: Filter by user ID
            chain_id: Filter by chain ID
            breaker_type: Filter by breaker type
            
        Returns:
            List of state dictionaries
        """
        try:
            query = CircuitBreakerStateModel.objects.filter(is_active=True)
            
            if user_id is not None:
                query = query.filter(user_id=user_id)
            if chain_id is not None:
                query = query.filter(chain_id=chain_id)
            if breaker_type:
                query = query.filter(breaker_type=breaker_type.value)
            
            states = [state.to_dict() for state in query]
            self.logger.debug(f"Loaded {len(states)} circuit breaker states")
            return states
            
        except Exception as e:
            self.logger.error(f"Failed to load states: {e}")
            return []
    
    async def delete_state(self, breaker_name: str) -> bool:
        """
        Delete (deactivate) a circuit breaker state.
        
        Args:
            breaker_name: Name of the circuit breaker
            
        Returns:
            True if deletion was successful
        """
        try:
            updated = CircuitBreakerStateModel.objects.filter(
                name=breaker_name
            ).update(is_active=False)
            
            # Clear cache
            if self.cache_enabled:
                cache_key = self._get_cache_key(breaker_name)
                cache.delete(cache_key)
            
            self.logger.debug(f"Deactivated state for {breaker_name}")
            return updated > 0
            
        except Exception as e:
            self.logger.error(f"Failed to delete state for {breaker_name}: {e}")
            return False
    
    # =========================================================================
    # EVENT LOGGING
    # =========================================================================
    
    async def log_event(
        self,
        breaker_name: str,
        breaker_type: CircuitBreakerType,
        event_type: str,
        priority: CircuitBreakerPriority = CircuitBreakerPriority.MEDIUM,
        details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        failure_count: int = 0,
        previous_state: Optional[CircuitBreakerState] = None,
        new_state: Optional[CircuitBreakerState] = None,
        user_id: Optional[int] = None,
        chain_id: Optional[int] = None
    ) -> bool:
        """
        Log a circuit breaker event to the database.
        
        Returns:
            True if logging was successful
        """
        try:
            event = CircuitBreakerEventModel.objects.create(
                breaker_name=breaker_name,
                breaker_type=breaker_type.value,
                event_type=event_type,
                priority=priority.value,
                details=details or {},
                error_message=error_message,
                failure_count=failure_count,
                previous_state=previous_state.value if previous_state else None,
                new_state=new_state.value if new_state else None,
                user_id=user_id,
                chain_id=chain_id,
                timestamp=datetime.now(timezone.utc)
            )
            
            self.logger.debug(
                f"Logged event for {breaker_name}: {event_type} "
                f"({previous_state} -> {new_state})"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to log event for {breaker_name}: {e}")
            return False
    
    async def get_event_history(
        self,
        breaker_name: Optional[str] = None,
        event_type: Optional[str] = None,
        user_id: Optional[int] = None,
        chain_id: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve event history from the database.
        
        Returns:
            List of event dictionaries
        """
        try:
            query = CircuitBreakerEventModel.objects.all()
            
            if breaker_name:
                query = query.filter(breaker_name=breaker_name)
            if event_type:
                query = query.filter(event_type=event_type)
            if user_id is not None:
                query = query.filter(user_id=user_id)
            if chain_id is not None:
                query = query.filter(chain_id=chain_id)
            if start_time:
                query = query.filter(timestamp__gte=start_time)
            if end_time:
                query = query.filter(timestamp__lte=end_time)
            
            events = query[:limit]
            
            return [
                {
                    'breaker_name': event.breaker_name,
                    'breaker_type': event.breaker_type,
                    'event_type': event.event_type,
                    'priority': event.priority,
                    'details': event.details,
                    'error_message': event.error_message,
                    'failure_count': event.failure_count,
                    'previous_state': event.previous_state,
                    'new_state': event.new_state,
                    'user_id': event.user_id,
                    'chain_id': event.chain_id,
                    'timestamp': event.timestamp.isoformat(),
                }
                for event in events
            ]
            
        except Exception as e:
            self.logger.error(f"Failed to get event history: {e}")
            return []
    
    # =========================================================================
    # METRICS SNAPSHOTS
    # =========================================================================
    
    async def save_metrics_snapshot(
        self,
        breaker_name: str,
        metrics: CircuitBreakerMetrics,
        period_start: datetime,
        period_end: Optional[datetime] = None
    ) -> bool:
        """
        Save a metrics snapshot to the database.
        
        Returns:
            True if save was successful
        """
        if period_end is None:
            period_end = datetime.now(timezone.utc)
        
        try:
            snapshot = CircuitBreakerMetricsSnapshot.objects.create(
                breaker_name=breaker_name,
                period_start=period_start,
                period_end=period_end,
                total_calls=metrics.total_calls,
                successful_calls=metrics.successful_calls,
                failed_calls=metrics.failed_calls,
                rejected_calls=metrics.rejected_calls,
                success_rate=metrics.get_success_rate(),
                error_rate=metrics.get_error_rate(),
                error_rate_1min=metrics.error_rate_1min,
                error_rate_5min=metrics.error_rate_5min,
                error_rate_15min=metrics.error_rate_15min,
                avg_latency_ms=metrics.avg_latency_ms,
                p50_latency_ms=metrics.p50_latency_ms,
                p95_latency_ms=metrics.p95_latency_ms,
                p99_latency_ms=metrics.p99_latency_ms,
                state_changes=metrics.state_changes,
                times_opened=metrics.times_opened,
                total_open_time_seconds=metrics.total_open_time_seconds,
            )
            
            self.logger.debug(f"Saved metrics snapshot for {breaker_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save metrics snapshot: {e}")
            return False
    
    async def get_metrics_history(
        self,
        breaker_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve metrics history for a circuit breaker.
        
        Returns:
            List of metrics snapshots
        """
        try:
            query = CircuitBreakerMetricsSnapshot.objects.filter(
                breaker_name=breaker_name
            )
            
            if start_time:
                query = query.filter(snapshot_time__gte=start_time)
            if end_time:
                query = query.filter(snapshot_time__lte=end_time)
            
            snapshots = query[:limit]
            
            return [
                {
                    'snapshot_time': s.snapshot_time.isoformat(),
                    'period_start': s.period_start.isoformat(),
                    'period_end': s.period_end.isoformat(),
                    'total_calls': s.total_calls,
                    'success_rate': s.success_rate,
                    'error_rate': s.error_rate,
                    'avg_latency_ms': s.avg_latency_ms,
                    'p95_latency_ms': s.p95_latency_ms,
                    'times_opened': s.times_opened,
                }
                for s in snapshots
            ]
            
        except Exception as e:
            self.logger.error(f"Failed to get metrics history: {e}")
            return []
    
    # =========================================================================
    # CLEANUP
    # =========================================================================
    
    async def cleanup_old_data(self, days: Optional[int] = None) -> Dict[str, int]:
        """
        Clean up old events and metrics data.
        
        Args:
            days: Days of history to keep (uses self.cleanup_days if None)
            
        Returns:
            Dictionary with counts of deleted records
        """
        if days is None:
            days = self.cleanup_days
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
        
        try:
            # Delete old events
            events_deleted, _ = CircuitBreakerEventModel.objects.filter(
                timestamp__lt=cutoff_time
            ).delete()
            
            # Delete old metrics
            metrics_deleted, _ = CircuitBreakerMetricsSnapshot.objects.filter(
                snapshot_time__lt=cutoff_time
            ).delete()
            
            # Deactivate old states that haven't been updated
            states_deactivated = CircuitBreakerStateModel.objects.filter(
                updated_at__lt=cutoff_time,
                is_active=True
            ).update(is_active=False)
            
            result = {
                'events_deleted': events_deleted,
                'metrics_deleted': metrics_deleted,
                'states_deactivated': states_deactivated,
            }
            
            self.logger.info(
                f"Cleanup completed: {events_deleted} events, "
                f"{metrics_deleted} metrics, {states_deactivated} states"
            )
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup old data: {e}")
            return {
                'events_deleted': 0,
                'metrics_deleted': 0,
                'states_deactivated': 0,
            }
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _get_cache_key(self, breaker_name: str) -> str:
        """Generate cache key for a circuit breaker."""
        return f"circuit_breaker:state:{breaker_name}"
    
    async def bulk_save_states(
        self,
        states: List[Dict[str, Any]]
    ) -> int:
        """
        Bulk save multiple circuit breaker states.
        
        Args:
            states: List of state dictionaries
            
        Returns:
            Number of states saved successfully
        """
        saved_count = 0
        
        for state in states:
            success = await self.save_state(
                breaker_name=state['name'],
                breaker_type=CircuitBreakerType[state['breaker_type']],
                state=CircuitBreakerState[state['state']],
                failure_count=state.get('failure_count', 0),
                success_count=state.get('success_count', 0),
                last_failure_time=state.get('last_failure_time'),
                last_success_time=state.get('last_success_time'),
                user_id=state.get('user_id'),
                chain_id=state.get('chain_id'),
            )
            if success:
                saved_count += 1
        
        self.logger.info(f"Bulk saved {saved_count}/{len(states)} states")
        return saved_count


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_persistence_instance: Optional[CircuitBreakerPersistence] = None


def get_persistence() -> CircuitBreakerPersistence:
    """
    Get the singleton persistence manager instance.
    
    Returns:
        The global persistence manager
    """
    global _persistence_instance
    
    if _persistence_instance is None:
        _persistence_instance = CircuitBreakerPersistence()
        logger.info("Created singleton CircuitBreakerPersistence instance")
    
    return _persistence_instance