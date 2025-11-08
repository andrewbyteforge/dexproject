"""
Circuit Breaker Monitoring and Metrics Export

Provides monitoring, metrics export, and analytics for circuit breakers.
Includes Prometheus integration, health checks, and performance tracking.

File: shared/circuit_breakers/monitoring.py
"""

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional, Set, Tuple

try:
    # Prometheus client (optional dependency)
    from prometheus_client import (
        Counter, Gauge, Histogram, Summary,
        CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logging.warning("prometheus_client not available - metrics export disabled")

from django.http import HttpResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from .config import (
    CircuitBreakerType,
    CircuitBreakerPriority,
    CircuitBreakerGroup,
    BREAKER_GROUPS,
)
from .enhanced_breaker import CircuitBreakerState

logger = logging.getLogger(__name__)


# =============================================================================
# MONITORING DATA STRUCTURES
# =============================================================================

@dataclass
class BreakerHealthStatus:
    """Health status for a single circuit breaker."""
    name: str
    breaker_type: CircuitBreakerType
    state: CircuitBreakerState
    is_healthy: bool
    is_blocking: bool
    failure_count: int
    error_rate: float
    avg_latency_ms: float
    last_failure: Optional[datetime] = None
    health_score: float = 100.0  # 0-100 scale
    issues: List[str] = field(default_factory=list)


@dataclass
class SystemHealthReport:
    """Overall system health report."""
    timestamp: datetime
    total_breakers: int
    healthy_breakers: int
    unhealthy_breakers: int
    blocking_breakers: int
    overall_health_score: float
    cascade_risk: bool
    breaker_statuses: List[BreakerHealthStatus]
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'total_breakers': self.total_breakers,
            'healthy_breakers': self.healthy_breakers,
            'unhealthy_breakers': self.unhealthy_breakers,
            'blocking_breakers': self.blocking_breakers,
            'overall_health_score': self.overall_health_score,
            'cascade_risk': self.cascade_risk,
            'breaker_statuses': [
                {
                    'name': bs.name,
                    'type': bs.breaker_type.value,
                    'state': bs.state.value,
                    'is_healthy': bs.is_healthy,
                    'is_blocking': bs.is_blocking,
                    'failure_count': bs.failure_count,
                    'error_rate': bs.error_rate,
                    'health_score': bs.health_score,
                    'issues': bs.issues,
                }
                for bs in self.breaker_statuses
            ],
            'recommendations': self.recommendations,
        }


# =============================================================================
# PROMETHEUS METRICS EXPORTER
# =============================================================================

class PrometheusExporter:
    """
    Exports circuit breaker metrics to Prometheus.
    
    Provides counters, gauges, histograms, and summaries
    for comprehensive monitoring.
    """
    
    def __init__(self, namespace: str = "dex_trading"):
        """
        Initialize Prometheus exporter.
        
        Args:
            namespace: Prometheus metric namespace
        """
        if not PROMETHEUS_AVAILABLE:
            self.enabled = False
            return
        
        self.enabled = True
        self.namespace = namespace
        self.registry = CollectorRegistry()
        
        # Initialize metrics
        self._init_metrics()
        
        self.logger = logging.getLogger(f"{__name__}.prometheus")
        self.logger.info(f"Prometheus exporter initialized with namespace '{namespace}'")
    
    def _init_metrics(self) -> None:
        """Initialize Prometheus metrics."""
        # Counters
        self.breaker_calls_total = Counter(
            f'{self.namespace}_circuit_breaker_calls_total',
            'Total number of calls through circuit breakers',
            ['breaker_name', 'breaker_type', 'result'],  # result: success/failure/rejected
            registry=self.registry
        )
        
        self.breaker_state_changes_total = Counter(
            f'{self.namespace}_circuit_breaker_state_changes_total',
            'Total number of state changes',
            ['breaker_name', 'breaker_type', 'from_state', 'to_state'],
            registry=self.registry
        )
        
        # Gauges
        self.breaker_state = Gauge(
            f'{self.namespace}_circuit_breaker_state',
            'Current state of circuit breaker (0=closed, 1=open, 2=half-open)',
            ['breaker_name', 'breaker_type'],
            registry=self.registry
        )
        
        self.breaker_failure_count = Gauge(
            f'{self.namespace}_circuit_breaker_failure_count',
            'Current failure count',
            ['breaker_name', 'breaker_type'],
            registry=self.registry
        )
        
        self.breaker_error_rate = Gauge(
            f'{self.namespace}_circuit_breaker_error_rate_percent',
            'Current error rate percentage',
            ['breaker_name', 'breaker_type', 'window'],  # window: 1min/5min/15min
            registry=self.registry
        )
        
        self.system_health_score = Gauge(
            f'{self.namespace}_system_health_score',
            'Overall system health score (0-100)',
            registry=self.registry
        )
        
        self.cascade_risk = Gauge(
            f'{self.namespace}_cascade_risk',
            'Cascade failure risk (0=no risk, 1=risk detected)',
            registry=self.registry
        )
        
        # Histograms
        self.call_latency = Histogram(
            f'{self.namespace}_circuit_breaker_call_latency_seconds',
            'Latency of calls through circuit breakers',
            ['breaker_name', 'breaker_type'],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
            registry=self.registry
        )
        
        # Summaries
        self.recovery_time = Summary(
            f'{self.namespace}_circuit_breaker_recovery_time_seconds',
            'Time taken to recover from open state',
            ['breaker_name', 'breaker_type'],
            registry=self.registry
        )
    
    def update_metrics(
        self,
        breaker_name: str,
        breaker_type: CircuitBreakerType,
        state: CircuitBreakerState,
        metrics: Dict[str, Any]
    ) -> None:
        """
        Update Prometheus metrics for a circuit breaker.
        
        Args:
            breaker_name: Name of the circuit breaker
            breaker_type: Type of circuit breaker
            state: Current state
            metrics: Metrics dictionary from the breaker
        """
        if not self.enabled:
            return
        
        try:
            # Update state gauge
            state_value = {
                CircuitBreakerState.CLOSED: 0,
                CircuitBreakerState.OPEN: 1,
                CircuitBreakerState.HALF_OPEN: 2,
                CircuitBreakerState.FORCED_OPEN: 3,
                CircuitBreakerState.DISABLED: -1,
            }.get(state, -1)
            
            self.breaker_state.labels(
                breaker_name=breaker_name,
                breaker_type=breaker_type.value
            ).set(state_value)
            
            # Update failure count
            self.breaker_failure_count.labels(
                breaker_name=breaker_name,
                breaker_type=breaker_type.value
            ).set(metrics.get('failure_count', 0))
            
            # Update error rates
            self.breaker_error_rate.labels(
                breaker_name=breaker_name,
                breaker_type=breaker_type.value,
                window='1min'
            ).set(metrics.get('error_rate_1min', 0))
            
            self.breaker_error_rate.labels(
                breaker_name=breaker_name,
                breaker_type=breaker_type.value,
                window='5min'
            ).set(metrics.get('error_rate_5min', 0))
            
            self.breaker_error_rate.labels(
                breaker_name=breaker_name,
                breaker_type=breaker_type.value,
                window='15min'
            ).set(metrics.get('error_rate_15min', 0))
            
        except Exception as e:
            self.logger.error(f"Failed to update Prometheus metrics: {e}")
    
    def record_call(
        self,
        breaker_name: str,
        breaker_type: CircuitBreakerType,
        result: str,  # 'success', 'failure', 'rejected'
        latency_seconds: float
    ) -> None:
        """Record a call through a circuit breaker."""
        if not self.enabled:
            return
        
        try:
            # Increment counter
            self.breaker_calls_total.labels(
                breaker_name=breaker_name,
                breaker_type=breaker_type.value,
                result=result
            ).inc()
            
            # Record latency
            if result != 'rejected':
                self.call_latency.labels(
                    breaker_name=breaker_name,
                    breaker_type=breaker_type.value
                ).observe(latency_seconds)
            
        except Exception as e:
            self.logger.error(f"Failed to record call: {e}")
    
    def record_state_change(
        self,
        breaker_name: str,
        breaker_type: CircuitBreakerType,
        from_state: CircuitBreakerState,
        to_state: CircuitBreakerState
    ) -> None:
        """Record a state change."""
        if not self.enabled:
            return
        
        try:
            self.breaker_state_changes_total.labels(
                breaker_name=breaker_name,
                breaker_type=breaker_type.value,
                from_state=from_state.value,
                to_state=to_state.value
            ).inc()
        except Exception as e:
            self.logger.error(f"Failed to record state change: {e}")
    
    def update_system_health(
        self,
        health_score: float,
        cascade_risk_detected: bool
    ) -> None:
        """Update system-wide health metrics."""
        if not self.enabled:
            return
        
        try:
            self.system_health_score.set(health_score)
            self.cascade_risk.set(1 if cascade_risk_detected else 0)
        except Exception as e:
            self.logger.error(f"Failed to update system health: {e}")
    
    def get_metrics(self) -> bytes:
        """
        Get metrics in Prometheus text format.
        
        Returns:
            Metrics data in Prometheus format
        """
        if not self.enabled:
            return b""
        
        return generate_latest(self.registry)


# =============================================================================
# CIRCUIT BREAKER MONITOR
# =============================================================================

class CircuitBreakerMonitor:
    """
    Monitors circuit breakers and provides health reporting.
    
    Features:
        - Real-time health monitoring
        - Performance tracking
        - Anomaly detection
        - Alert generation
        - Trend analysis
    """
    
    def __init__(
        self,
        prometheus_exporter: Optional[PrometheusExporter] = None,
        monitoring_interval: int = 60,  # seconds
        alert_callbacks: Optional[List[Callable]] = None
    ):
        """
        Initialize the monitor.
        
        Args:
            prometheus_exporter: Optional Prometheus exporter
            monitoring_interval: How often to check health (seconds)
            alert_callbacks: List of callbacks for alerts
        """
        self.prometheus_exporter = prometheus_exporter
        self.monitoring_interval = monitoring_interval
        self.alert_callbacks = alert_callbacks or []
        
        # Health tracking
        self.health_history: Deque[SystemHealthReport] = deque(maxlen=100)
        self.breaker_health: Dict[str, BreakerHealthStatus] = {}
        
        # Alert tracking
        self.active_alerts: Dict[str, Dict[str, Any]] = {}
        self.alert_cooldowns: Dict[str, datetime] = {}
        
        # Performance tracking
        self.performance_metrics: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=60)
        )
        
        # Monitoring task
        self.monitoring_task: Optional[asyncio.Task] = None
        self.running = False
        
        self.logger = logging.getLogger(f"{__name__}.monitor")
    
    # =========================================================================
    # MONITORING LIFECYCLE
    # =========================================================================
    
    async def start(self) -> None:
        """Start the monitoring task."""
        if self.running:
            return
        
        self.running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        self.logger.info(f"Circuit breaker monitor started (interval: {self.monitoring_interval}s)")
    
    async def stop(self) -> None:
        """Stop the monitoring task."""
        self.running = False
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
            self.monitoring_task = None
        
        self.logger.info("Circuit breaker monitor stopped")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        while self.running:
            try:
                # Perform health check
                await self.check_health()
                
                # Wait for next interval
                await asyncio.sleep(self.monitoring_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(self.monitoring_interval)
    
    # =========================================================================
    # HEALTH MONITORING
    # =========================================================================
    
    async def check_health(
        self,
        breakers: Optional[Dict[str, Any]] = None
    ) -> SystemHealthReport:
        """
        Check health of all circuit breakers.
        
        Args:
            breakers: Dictionary of breakers to check (or fetch from manager)
            
        Returns:
            System health report
        """
        if breakers is None:
            # Would fetch from CircuitBreakerManager
            breakers = {}
        
        breaker_statuses = []
        total_health_score = 0
        blocking_count = 0
        unhealthy_count = 0
        
        for name, breaker_info in breakers.items():
            status = self._assess_breaker_health(name, breaker_info)
            breaker_statuses.append(status)
            
            total_health_score += status.health_score
            
            if status.is_blocking:
                blocking_count += 1
            if not status.is_healthy:
                unhealthy_count += 1
            
            # Update individual health tracking
            self.breaker_health[name] = status
        
        # Calculate overall health
        total_breakers = len(breaker_statuses)
        healthy_breakers = total_breakers - unhealthy_count
        
        if total_breakers > 0:
            overall_health_score = total_health_score / total_breakers
        else:
            overall_health_score = 100.0
        
        # Check cascade risk
        cascade_risk = self._detect_cascade_risk(breaker_statuses)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            breaker_statuses,
            overall_health_score,
            cascade_risk
        )
        
        # Create report
        report = SystemHealthReport(
            timestamp=datetime.now(timezone.utc),
            total_breakers=total_breakers,
            healthy_breakers=healthy_breakers,
            unhealthy_breakers=unhealthy_count,
            blocking_breakers=blocking_count,
            overall_health_score=overall_health_score,
            cascade_risk=cascade_risk,
            breaker_statuses=breaker_statuses,
            recommendations=recommendations
        )
        
        # Store in history
        self.health_history.append(report)
        
        # Update Prometheus metrics if available
        if self.prometheus_exporter:
            self.prometheus_exporter.update_system_health(
                overall_health_score,
                cascade_risk
            )
        
        # Check for alerts
        await self._check_alerts(report)
        
        return report
    
    def _assess_breaker_health(
        self,
        name: str,
        breaker_info: Dict[str, Any]
    ) -> BreakerHealthStatus:
        """Assess health of a single circuit breaker."""
        state = CircuitBreakerState[breaker_info.get('state', 'CLOSED')]
        metrics = breaker_info.get('metrics', {})
        
        # Basic health checks
        is_blocking = state in [CircuitBreakerState.OPEN, CircuitBreakerState.FORCED_OPEN]
        is_healthy = state in [CircuitBreakerState.CLOSED, CircuitBreakerState.DISABLED]
        
        # Calculate health score (0-100)
        health_score = 100.0
        issues = []
        
        # Check error rate
        error_rate = metrics.get('error_rate', 0)
        if error_rate > 50:
            health_score -= 30
            issues.append(f"High error rate: {error_rate:.1f}%")
        elif error_rate > 25:
            health_score -= 15
            issues.append(f"Elevated error rate: {error_rate:.1f}%")
        
        # Check state
        if state == CircuitBreakerState.OPEN:
            health_score -= 40
            issues.append("Circuit breaker is OPEN")
        elif state == CircuitBreakerState.HALF_OPEN:
            health_score -= 20
            issues.append("Circuit breaker is recovering")
        
        # Check failure count
        failure_count = breaker_info.get('failure_count', 0)
        failure_threshold = breaker_info.get('failure_threshold', 5)
        if failure_count >= failure_threshold * 0.8:
            health_score -= 10
            issues.append(f"Near failure threshold: {failure_count}/{failure_threshold}")
        
        # Check latency
        avg_latency = metrics.get('avg_latency_ms', 0)
        if avg_latency > 1000:  # > 1 second
            health_score -= 10
            issues.append(f"High latency: {avg_latency:.0f}ms")
        
        health_score = max(0, min(100, health_score))
        
        return BreakerHealthStatus(
            name=name,
            breaker_type=CircuitBreakerType[breaker_info.get('type', 'EXTERNAL_TRIGGER')],
            state=state,
            is_healthy=is_healthy,
            is_blocking=is_blocking,
            failure_count=failure_count,
            error_rate=error_rate,
            avg_latency_ms=avg_latency,
            last_failure=breaker_info.get('last_failure_time'),
            health_score=health_score,
            issues=issues
        )
    
    def _detect_cascade_risk(
        self,
        breaker_statuses: List[BreakerHealthStatus]
    ) -> bool:
        """Detect if there's a risk of cascade failure."""
        # Count critical breakers that are unhealthy
        critical_unhealthy = sum(
            1 for bs in breaker_statuses
            if not bs.is_healthy and bs.breaker_type in [
                CircuitBreakerType.RPC_FAILURE,
                CircuitBreakerType.DATABASE_FAILURE,
                CircuitBreakerType.PORTFOLIO_LOSS,
            ]
        )
        
        # Check if multiple breakers opened recently
        recent_opens = sum(
            1 for bs in breaker_statuses
            if bs.state == CircuitBreakerState.OPEN and
            bs.last_failure and 
            (datetime.now(timezone.utc) - bs.last_failure).total_seconds() < 60
        )
        
        return critical_unhealthy >= 2 or recent_opens >= 3
    
    def _generate_recommendations(
        self,
        breaker_statuses: List[BreakerHealthStatus],
        overall_health_score: float,
        cascade_risk: bool
    ) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []
        
        if cascade_risk:
            recommendations.append(
                "⚠️ CASCADE RISK: Multiple critical systems failing. "
                "Consider emergency shutdown."
            )
        
        if overall_health_score < 50:
            recommendations.append(
                "🔴 CRITICAL: System health below 50%. "
                "Immediate intervention required."
            )
        elif overall_health_score < 75:
            recommendations.append(
                "🟡 WARNING: System health degraded. "
                "Monitor closely and prepare for intervention."
            )
        
        # Check for specific issues
        high_error_breakers = [
            bs for bs in breaker_statuses
            if bs.error_rate > 50
        ]
        if high_error_breakers:
            names = ", ".join(b.name for b in high_error_breakers[:3])
            recommendations.append(
                f"High error rates detected in: {names}. "
                "Check underlying services."
            )
        
        # Check for stuck breakers
        stuck_open = [
            bs for bs in breaker_statuses
            if bs.state == CircuitBreakerState.OPEN and
            bs.last_failure and
            (datetime.now(timezone.utc) - bs.last_failure).total_seconds() > 300
        ]
        if stuck_open:
            names = ", ".join(b.name for b in stuck_open[:3])
            recommendations.append(
                f"Breakers stuck open: {names}. "
                "Consider manual intervention."
            )
        
        return recommendations
    
    # =========================================================================
    # ALERT MANAGEMENT
    # =========================================================================
    
    async def _check_alerts(self, report: SystemHealthReport) -> None:
        """Check for alert conditions and trigger alerts."""
        alerts_to_send = []
        
        # Critical health alert
        if report.overall_health_score < 50:
            alert_id = "critical_health"
            if self._should_send_alert(alert_id, priority='critical'):
                alerts_to_send.append({
                    'id': alert_id,
                    'type': 'CRITICAL_HEALTH',
                    'priority': 'critical',
                    'message': f"System health critical: {report.overall_health_score:.1f}%",
                    'details': report.to_dict()
                })
        
        # Cascade risk alert
        if report.cascade_risk:
            alert_id = "cascade_risk"
            if self._should_send_alert(alert_id, priority='critical'):
                alerts_to_send.append({
                    'id': alert_id,
                    'type': 'CASCADE_RISK',
                    'priority': 'critical',
                    'message': "Cascade failure risk detected",
                    'details': report.to_dict()
                })
        
        # High blocking count alert
        if report.blocking_breakers >= 3:
            alert_id = "high_blocking"
            if self._should_send_alert(alert_id, priority='high'):
                alerts_to_send.append({
                    'id': alert_id,
                    'type': 'HIGH_BLOCKING',
                    'priority': 'high',
                    'message': f"{report.blocking_breakers} circuit breakers blocking",
                    'details': {
                        'blocking_count': report.blocking_breakers,
                        'breakers': [
                            bs.name for bs in report.breaker_statuses
                            if bs.is_blocking
                        ]
                    }
                })
        
        # Send alerts
        for alert in alerts_to_send:
            await self._send_alert(alert)
            self.active_alerts[alert['id']] = alert
            self.alert_cooldowns[alert['id']] = datetime.now(timezone.utc)
    
    def _should_send_alert(
        self,
        alert_id: str,
        priority: str = 'medium',
        cooldown_seconds: int = 300
    ) -> bool:
        """Check if an alert should be sent based on cooldown."""
        if alert_id in self.alert_cooldowns:
            last_sent = self.alert_cooldowns[alert_id]
            if (datetime.now(timezone.utc) - last_sent).total_seconds() < cooldown_seconds:
                return False
        
        # Higher priority alerts have shorter cooldowns
        if priority == 'critical':
            cooldown_seconds = min(cooldown_seconds, 60)
        elif priority == 'high':
            cooldown_seconds = min(cooldown_seconds, 180)
        
        return True
    
    async def _send_alert(self, alert: Dict[str, Any]) -> None:
        """Send an alert through all configured callbacks."""
        self.logger.warning(f"ALERT: {alert['type']} - {alert['message']}")
        
        for callback in self.alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert)
                else:
                    callback(alert)
            except Exception as e:
                self.logger.error(f"Failed to send alert via callback: {e}")
    
    # =========================================================================
    # ANALYTICS AND REPORTING
    # =========================================================================
    
    def get_trend_analysis(self, hours: int = 1) -> Dict[str, Any]:
        """
        Analyze trends over the specified time period.
        
        Args:
            hours: Number of hours to analyze
            
        Returns:
            Trend analysis report
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent_reports = [
            report for report in self.health_history
            if report.timestamp > cutoff_time
        ]
        
        if not recent_reports:
            return {'error': 'Insufficient data for trend analysis'}
        
        # Calculate trends
        health_scores = [r.overall_health_score for r in recent_reports]
        blocking_counts = [r.blocking_breakers for r in recent_reports]
        
        # Simple trend detection
        health_trend = 'stable'
        if len(health_scores) >= 3:
            recent_avg = sum(health_scores[-3:]) / 3
            older_avg = sum(health_scores[:3]) / 3
            if recent_avg < older_avg - 10:
                health_trend = 'degrading'
            elif recent_avg > older_avg + 10:
                health_trend = 'improving'
        
        return {
            'period_hours': hours,
            'samples': len(recent_reports),
            'health_trend': health_trend,
            'current_health': health_scores[-1] if health_scores else 0,
            'avg_health': sum(health_scores) / len(health_scores) if health_scores else 0,
            'min_health': min(health_scores) if health_scores else 0,
            'max_health': max(health_scores) if health_scores else 0,
            'avg_blocking': sum(blocking_counts) / len(blocking_counts) if blocking_counts else 0,
            'cascade_incidents': sum(1 for r in recent_reports if r.cascade_risk),
        }
    
    def get_breaker_ranking(self) -> List[Dict[str, Any]]:
        """
        Rank circuit breakers by health/reliability.
        
        Returns:
            List of breakers ranked by health score
        """
        ranked = sorted(
            self.breaker_health.values(),
            key=lambda x: (x.health_score, -x.failure_count)
        )
        
        return [
            {
                'rank': i + 1,
                'name': bs.name,
                'type': bs.breaker_type.value,
                'health_score': bs.health_score,
                'state': bs.state.value,
                'issues': bs.issues,
            }
            for i, bs in enumerate(ranked)
        ]


# =============================================================================
# DJANGO VIEWS FOR MONITORING
# =============================================================================

@method_decorator(csrf_exempt, name='dispatch')
class PrometheusMetricsView(View):
    """Django view for Prometheus metrics endpoint."""
    
    def get(self, request):
        """Return Prometheus metrics."""
        if not PROMETHEUS_AVAILABLE:
            return HttpResponse(
                "Prometheus client not installed",
                status=503,
                content_type="text/plain"
            )
        
        try:
            # Get the global Prometheus exporter
            # This would be initialized elsewhere
            from .manager import get_manager
            manager = asyncio.run(get_manager())
            
            if hasattr(manager, 'prometheus_exporter'):
                metrics = manager.prometheus_exporter.get_metrics()
                return HttpResponse(
                    metrics,
                    content_type=CONTENT_TYPE_LATEST
                )
            else:
                return HttpResponse(
                    "Prometheus exporter not configured",
                    status=503,
                    content_type="text/plain"
                )
        except Exception as e:
            logger.error(f"Failed to generate Prometheus metrics: {e}")
            return HttpResponse(
                f"Error generating metrics: {str(e)}",
                status=500,
                content_type="text/plain"
            )


class CircuitBreakerHealthView(View):
    """Django view for circuit breaker health status."""
    
    def get(self, request):
        """Return current health status."""
        try:
            from .manager import get_manager
            manager = asyncio.run(get_manager())
            
            # Get health report
            health = manager.get_health_report()
            
            return HttpResponse(
                json.dumps(health, indent=2),
                content_type="application/json"
            )
        except Exception as e:
            logger.error(f"Failed to get health status: {e}")
            return HttpResponse(
                json.dumps({'error': str(e)}),
                status=500,
                content_type="application/json"
            )


# =============================================================================
# MONITORING UTILITIES
# =============================================================================

def calculate_reliability_score(
    total_calls: int,
    failed_calls: int,
    rejected_calls: int,
    avg_latency_ms: float,
    target_latency_ms: float = 100
) -> float:
    """
    Calculate a reliability score for a circuit breaker.
    
    Args:
        total_calls: Total number of calls
        failed_calls: Number of failed calls
        rejected_calls: Number of rejected calls
        avg_latency_ms: Average latency
        target_latency_ms: Target latency for scoring
        
    Returns:
        Reliability score (0-100)
    """
    if total_calls == 0:
        return 100.0
    
    # Calculate success rate
    successful_calls = total_calls - failed_calls - rejected_calls
    success_rate = (successful_calls / total_calls) * 100
    
    # Calculate latency score
    if avg_latency_ms <= target_latency_ms:
        latency_score = 100.0
    else:
        # Degrade score as latency increases
        latency_score = max(0, 100 - ((avg_latency_ms - target_latency_ms) / target_latency_ms * 50))
    
    # Weight success rate more heavily than latency
    reliability_score = (success_rate * 0.7) + (latency_score * 0.3)
    
    return max(0, min(100, reliability_score))


def format_health_report(report: SystemHealthReport) -> str:
    """
    Format a health report for human readability.
    
    Args:
        report: System health report
        
    Returns:
        Formatted string representation
    """
    lines = [
        "=" * 60,
        "CIRCUIT BREAKER HEALTH REPORT",
        "=" * 60,
        f"Timestamp: {report.timestamp.isoformat()}",
        f"Overall Health: {report.overall_health_score:.1f}%",
        f"Total Breakers: {report.total_breakers}",
        f"  - Healthy: {report.healthy_breakers}",
        f"  - Unhealthy: {report.unhealthy_breakers}",
        f"  - Blocking: {report.blocking_breakers}",
        f"Cascade Risk: {'YES ⚠️' if report.cascade_risk else 'No'}",
        "",
        "TOP ISSUES:",
    ]
    
    # Add top issues
    problematic = sorted(
        report.breaker_statuses,
        key=lambda x: x.health_score
    )[:5]
    
    for bs in problematic:
        if bs.health_score < 100:
            lines.append(f"  - {bs.name}: {bs.health_score:.0f}% - {', '.join(bs.issues)}")
    
    if report.recommendations:
        lines.append("")
        lines.append("RECOMMENDATIONS:")
        for rec in report.recommendations:
            lines.append(f"  • {rec}")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)