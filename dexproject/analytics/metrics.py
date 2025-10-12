"""
Analytics Metrics Collection Module

Prometheus-compatible metrics collection for system monitoring.
Tracks HTTP requests, trading performance, Celery tasks, WebSocket connections,
database queries, and cache statistics.

This module provides both Prometheus metrics (for scraping) and helper functions
to record metrics from anywhere in the application.

File: dexproject/analytics/metrics.py
"""

import logging
import time
from typing import Dict, Any, Optional, List
from decimal import Decimal
from functools import wraps
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone
from django.db import connection
from django.core.cache import cache

# Prometheus client imports
try:
    from prometheus_client import (
        Counter, Histogram, Gauge, Info,
        CollectorRegistry, generate_latest,
        CONTENT_TYPE_LATEST
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logging.warning("prometheus-client not installed. Install with: pip install prometheus-client")

logger = logging.getLogger(__name__)

# =============================================================================
# PROMETHEUS REGISTRY
# =============================================================================

if PROMETHEUS_AVAILABLE:
    # Create custom registry for our metrics
    registry = CollectorRegistry()
    
    # =============================================================================
    # HTTP REQUEST METRICS
    # =============================================================================
    
    http_requests_total = Counter(
        'http_requests_total',
        'Total HTTP requests',
        ['method', 'endpoint', 'status'],
        registry=registry
    )
    
    http_request_duration_seconds = Histogram(
        'http_request_duration_seconds',
        'HTTP request latency in seconds',
        ['method', 'endpoint'],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        registry=registry
    )
    
    http_requests_in_progress = Gauge(
        'http_requests_in_progress',
        'Number of HTTP requests in progress',
        registry=registry
    )
    
    # =============================================================================
    # TRADING METRICS - PAPER TRADING
    # =============================================================================
    
    paper_trades_total = Counter(
        'paper_trades_total',
        'Total paper trades executed',
        ['trade_type', 'status'],
        registry=registry
    )
    
    paper_trade_execution_seconds = Histogram(
        'paper_trade_execution_seconds',
        'Paper trade execution time in seconds',
        ['trade_type'],
        buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
        registry=registry
    )
    
    paper_trade_volume_usd = Counter(
        'paper_trade_volume_usd_total',
        'Total paper trading volume in USD',
        ['trade_type'],
        registry=registry
    )
    
    paper_positions_open = Gauge(
        'paper_positions_open',
        'Number of open paper trading positions',
        registry=registry
    )
    
    paper_pnl_usd = Gauge(
        'paper_pnl_usd',
        'Current paper trading P&L in USD',
        ['type'],  # 'realized' or 'unrealized'
        registry=registry
    )
    
    paper_trading_sessions_active = Gauge(
        'paper_trading_sessions_active',
        'Number of active paper trading sessions',
        registry=registry
    )
    
    # =============================================================================
    # TRADING METRICS - REAL TRADING
    # =============================================================================
    
    real_trades_total = Counter(
        'real_trades_total',
        'Total real trades executed',
        ['trade_type', 'status'],
        registry=registry
    )
    
    real_trade_execution_seconds = Histogram(
        'real_trade_execution_seconds',
        'Real trade execution time in seconds',
        ['trade_type'],
        buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
        registry=registry
    )
    
    real_trade_volume_usd = Counter(
        'real_trade_volume_usd_total',
        'Total real trading volume in USD',
        ['trade_type'],
        registry=registry
    )
    
    real_positions_open = Gauge(
        'real_positions_open',
        'Number of open real trading positions',
        registry=registry
    )
    
    real_pnl_usd = Gauge(
        'real_pnl_usd',
        'Current real trading P&L in USD',
        ['type'],  # 'realized' or 'unrealized'
        registry=registry
    )
    
    real_gas_cost_usd = Counter(
        'real_gas_cost_usd_total',
        'Total gas costs in USD for real trading',
        registry=registry
    )
    
    # =============================================================================
    # CELERY TASK METRICS
    # =============================================================================
    
    celery_tasks_total = Counter(
        'celery_tasks_total',
        'Total Celery tasks executed',
        ['task_name', 'queue', 'status'],
        registry=registry
    )
    
    celery_task_duration_seconds = Histogram(
        'celery_task_duration_seconds',
        'Celery task execution time in seconds',
        ['task_name', 'queue'],
        buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
        registry=registry
    )
    
    celery_queue_length = Gauge(
        'celery_queue_length',
        'Current Celery queue length',
        ['queue'],
        registry=registry
    )
    
    # =============================================================================
    # WEBSOCKET METRICS
    # =============================================================================
    
    websocket_connections_active = Gauge(
        'websocket_connections_active',
        'Number of active WebSocket connections',
        ['consumer_type'],
        registry=registry
    )
    
    websocket_messages_total = Counter(
        'websocket_messages_total',
        'Total WebSocket messages',
        ['consumer_type', 'direction'],  # 'sent' or 'received'
        registry=registry
    )
    
    websocket_errors_total = Counter(
        'websocket_errors_total',
        'Total WebSocket errors',
        ['consumer_type', 'error_type'],
        registry=registry
    )
    
    # =============================================================================
    # DATABASE METRICS
    # =============================================================================
    
    db_queries_total = Counter(
        'db_queries_total',
        'Total database queries',
        ['operation'],  # 'select', 'insert', 'update', 'delete'
        registry=registry
    )
    
    db_query_duration_seconds = Histogram(
        'db_query_duration_seconds',
        'Database query execution time in seconds',
        ['operation'],
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
        registry=registry
    )
    
    db_connections_active = Gauge(
        'db_connections_active',
        'Number of active database connections',
        registry=registry
    )
    
    # =============================================================================
    # CACHE METRICS (REDIS)
    # =============================================================================
    
    cache_operations_total = Counter(
        'cache_operations_total',
        'Total cache operations',
        ['operation', 'status'],  # operation: 'get'/'set'/'delete', status: 'hit'/'miss'
        registry=registry
    )
    
    cache_operation_duration_seconds = Histogram(
        'cache_operation_duration_seconds',
        'Cache operation duration in seconds',
        ['operation'],
        buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1),
        registry=registry
    )
    
    # =============================================================================
    # EXCHANGE API METRICS
    # =============================================================================
    
    exchange_api_calls_total = Counter(
        'exchange_api_calls_total',
        'Total exchange API calls',
        ['exchange', 'endpoint', 'status'],
        registry=registry
    )
    
    exchange_api_duration_seconds = Histogram(
        'exchange_api_duration_seconds',
        'Exchange API call duration in seconds',
        ['exchange', 'endpoint'],
        buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
        registry=registry
    )
    
    exchange_api_errors_total = Counter(
        'exchange_api_errors_total',
        'Total exchange API errors',
        ['exchange', 'error_type'],
        registry=registry
    )
    
    # =============================================================================
    # SYSTEM METRICS
    # =============================================================================
    
    app_info = Info(
        'app',
        'Application information',
        registry=registry
    )
    
    # Set app info
    app_info.info({
        'version': '1.0.0',
        'environment': getattr(settings, 'TRADING_ENVIRONMENT', 'development'),
        'trading_mode': getattr(settings, 'TRADING_MODE', 'PAPER'),
    })

else:
    # Fallback if Prometheus is not installed
    registry = None
    logger.warning("Prometheus metrics disabled - prometheus-client not installed")


# =============================================================================
# HELPER FUNCTIONS FOR RECORDING METRICS
# =============================================================================

class MetricsRecorder:
    """
    Helper class for recording metrics throughout the application.
    
    Provides simple functions to record metrics without needing to
    import Prometheus directly.
    """
    
    def __init__(self):
        """Initialize metrics recorder."""
        self.enabled = PROMETHEUS_AVAILABLE
        self.logger = logging.getLogger('analytics.metrics')
    
    # =========================================================================
    # HTTP REQUEST METRICS
    # =========================================================================
    
    def record_http_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration_seconds: float
    ) -> None:
        """
        Record an HTTP request.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: Request endpoint/path
            status_code: HTTP status code
            duration_seconds: Request duration in seconds
        """
        if not self.enabled:
            return
        
        try:
            http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status=str(status_code)
            ).inc()
            
            http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration_seconds)
            
        except Exception as e:
            self.logger.error(f"Error recording HTTP request metric: {e}")
    
    def increment_requests_in_progress(self) -> None:
        """Increment in-progress requests counter."""
        if self.enabled:
            try:
                http_requests_in_progress.inc()
            except Exception as e:
                self.logger.error(f"Error incrementing requests in progress: {e}")
    
    def decrement_requests_in_progress(self) -> None:
        """Decrement in-progress requests counter."""
        if self.enabled:
            try:
                http_requests_in_progress.dec()
            except Exception as e:
                self.logger.error(f"Error decrementing requests in progress: {e}")
    
    # =========================================================================
    # PAPER TRADING METRICS
    # =========================================================================
    
    def record_paper_trade(
        self,
        trade_type: str,
        status: str,
        execution_time_seconds: float,
        volume_usd: Decimal
    ) -> None:
        """
        Record a paper trade execution.
        
        Args:
            trade_type: Type of trade ('buy', 'sell', 'swap')
            status: Trade status ('completed', 'failed', etc.)
            execution_time_seconds: Execution time in seconds
            volume_usd: Trade volume in USD
        """
        if not self.enabled:
            return
        
        try:
            paper_trades_total.labels(
                trade_type=trade_type,
                status=status
            ).inc()
            
            paper_trade_execution_seconds.labels(
                trade_type=trade_type
            ).observe(execution_time_seconds)
            
            paper_trade_volume_usd.labels(
                trade_type=trade_type
            ).inc(float(volume_usd))
            
        except Exception as e:
            self.logger.error(f"Error recording paper trade metric: {e}")
    
    def update_paper_positions(self, open_count: int) -> None:
        """Update paper trading open positions count."""
        if self.enabled:
            try:
                paper_positions_open.set(open_count)
            except Exception as e:
                self.logger.error(f"Error updating paper positions: {e}")
    
    def update_paper_pnl(self, realized: Decimal, unrealized: Decimal) -> None:
        """Update paper trading P&L gauges."""
        if self.enabled:
            try:
                paper_pnl_usd.labels(type='realized').set(float(realized))
                paper_pnl_usd.labels(type='unrealized').set(float(unrealized))
            except Exception as e:
                self.logger.error(f"Error updating paper P&L: {e}")
    
    def update_paper_sessions(self, active_count: int) -> None:
        """Update active paper trading sessions count."""
        if self.enabled:
            try:
                paper_trading_sessions_active.set(active_count)
            except Exception as e:
                self.logger.error(f"Error updating paper sessions: {e}")
    
    # =========================================================================
    # REAL TRADING METRICS
    # =========================================================================
    
    def record_real_trade(
        self,
        trade_type: str,
        status: str,
        execution_time_seconds: float,
        volume_usd: Decimal,
        gas_cost_usd: Optional[Decimal] = None
    ) -> None:
        """
        Record a real trade execution.
        
        Args:
            trade_type: Type of trade ('buy', 'sell', 'swap')
            status: Trade status ('completed', 'failed', etc.)
            execution_time_seconds: Execution time in seconds
            volume_usd: Trade volume in USD
            gas_cost_usd: Gas cost in USD (optional)
        """
        if not self.enabled:
            return
        
        try:
            real_trades_total.labels(
                trade_type=trade_type,
                status=status
            ).inc()
            
            real_trade_execution_seconds.labels(
                trade_type=trade_type
            ).observe(execution_time_seconds)
            
            real_trade_volume_usd.labels(
                trade_type=trade_type
            ).inc(float(volume_usd))
            
            if gas_cost_usd is not None:
                real_gas_cost_usd.inc(float(gas_cost_usd))
            
        except Exception as e:
            self.logger.error(f"Error recording real trade metric: {e}")
    
    def update_real_positions(self, open_count: int) -> None:
        """Update real trading open positions count."""
        if self.enabled:
            try:
                real_positions_open.set(open_count)
            except Exception as e:
                self.logger.error(f"Error updating real positions: {e}")
    
    def update_real_pnl(self, realized: Decimal, unrealized: Decimal) -> None:
        """Update real trading P&L gauges."""
        if self.enabled:
            try:
                real_pnl_usd.labels(type='realized').set(float(realized))
                real_pnl_usd.labels(type='unrealized').set(float(unrealized))
            except Exception as e:
                self.logger.error(f"Error updating real P&L: {e}")
    
    # =========================================================================
    # CELERY TASK METRICS
    # =========================================================================
    
    def record_celery_task(
        self,
        task_name: str,
        queue: str,
        status: str,
        duration_seconds: float
    ) -> None:
        """
        Record Celery task execution.
        
        Args:
            task_name: Name of the task
            queue: Queue name
            status: Task status ('success', 'failure', 'retry')
            duration_seconds: Task duration in seconds
        """
        if not self.enabled:
            return
        
        try:
            celery_tasks_total.labels(
                task_name=task_name,
                queue=queue,
                status=status
            ).inc()
            
            celery_task_duration_seconds.labels(
                task_name=task_name,
                queue=queue
            ).observe(duration_seconds)
            
        except Exception as e:
            self.logger.error(f"Error recording Celery task metric: {e}")
    
    def update_celery_queue_length(self, queue: str, length: int) -> None:
        """Update Celery queue length gauge."""
        if self.enabled:
            try:
                celery_queue_length.labels(queue=queue).set(length)
            except Exception as e:
                self.logger.error(f"Error updating Celery queue length: {e}")
    
    # =========================================================================
    # WEBSOCKET METRICS
    # =========================================================================
    
    def record_websocket_connection(
        self,
        consumer_type: str,
        connected: bool
    ) -> None:
        """
        Record WebSocket connection change.
        
        Args:
            consumer_type: Type of consumer ('paper_trading', 'dashboard', etc.)
            connected: True if connecting, False if disconnecting
        """
        if not self.enabled:
            return
        
        try:
            if connected:
                websocket_connections_active.labels(
                    consumer_type=consumer_type
                ).inc()
            else:
                websocket_connections_active.labels(
                    consumer_type=consumer_type
                ).dec()
        except Exception as e:
            self.logger.error(f"Error recording WebSocket connection: {e}")
    
    def record_websocket_message(
        self,
        consumer_type: str,
        direction: str  # 'sent' or 'received'
    ) -> None:
        """Record WebSocket message."""
        if self.enabled:
            try:
                websocket_messages_total.labels(
                    consumer_type=consumer_type,
                    direction=direction
                ).inc()
            except Exception as e:
                self.logger.error(f"Error recording WebSocket message: {e}")
    
    def record_websocket_error(
        self,
        consumer_type: str,
        error_type: str
    ) -> None:
        """Record WebSocket error."""
        if self.enabled:
            try:
                websocket_errors_total.labels(
                    consumer_type=consumer_type,
                    error_type=error_type
                ).inc()
            except Exception as e:
                self.logger.error(f"Error recording WebSocket error: {e}")
    
    # =========================================================================
    # DATABASE METRICS
    # =========================================================================
    
    def record_db_query(
        self,
        operation: str,  # 'select', 'insert', 'update', 'delete'
        duration_seconds: float
    ) -> None:
        """Record database query."""
        if not self.enabled:
            return
        
        try:
            db_queries_total.labels(operation=operation).inc()
            db_query_duration_seconds.labels(operation=operation).observe(duration_seconds)
        except Exception as e:
            self.logger.error(f"Error recording DB query: {e}")
    
    def update_db_connections(self, active_count: int) -> None:
        """Update active database connections count."""
        if self.enabled:
            try:
                db_connections_active.set(active_count)
            except Exception as e:
                self.logger.error(f"Error updating DB connections: {e}")
    
    # =========================================================================
    # CACHE METRICS
    # =========================================================================
    
    def record_cache_operation(
        self,
        operation: str,  # 'get', 'set', 'delete'
        status: str,  # 'hit', 'miss', 'success', 'error'
        duration_seconds: float
    ) -> None:
        """Record cache operation."""
        if not self.enabled:
            return
        
        try:
            cache_operations_total.labels(
                operation=operation,
                status=status
            ).inc()
            
            cache_operation_duration_seconds.labels(
                operation=operation
            ).observe(duration_seconds)
        except Exception as e:
            self.logger.error(f"Error recording cache operation: {e}")
    
    # =========================================================================
    # EXCHANGE API METRICS
    # =========================================================================
    
    def record_exchange_api_call(
        self,
        exchange: str,
        endpoint: str,
        status: str,  # 'success', 'error'
        duration_seconds: float,
        error_type: Optional[str] = None
    ) -> None:
        """
        Record exchange API call.
        
        Args:
            exchange: Exchange name ('binance', 'coinbase', etc.)
            endpoint: API endpoint called
            status: Call status
            duration_seconds: Call duration
            error_type: Error type if failed
        """
        if not self.enabled:
            return
        
        try:
            exchange_api_calls_total.labels(
                exchange=exchange,
                endpoint=endpoint,
                status=status
            ).inc()
            
            exchange_api_duration_seconds.labels(
                exchange=exchange,
                endpoint=endpoint
            ).observe(duration_seconds)
            
            if error_type:
                exchange_api_errors_total.labels(
                    exchange=exchange,
                    error_type=error_type
                ).inc()
        except Exception as e:
            self.logger.error(f"Error recording exchange API call: {e}")


# =============================================================================
# GLOBAL METRICS RECORDER INSTANCE
# =============================================================================

metrics_recorder = MetricsRecorder()


# =============================================================================
# DECORATOR FOR AUTOMATIC METRIC RECORDING
# =============================================================================

def track_execution_time(metric_type: str = 'function'):
    """
    Decorator to automatically track function execution time.
    
    Args:
        metric_type: Type of metric ('function', 'celery', 'api')
    
    Usage:
        @track_execution_time('celery')
        def my_task():
            # task code
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                # Log execution time
                logger.debug(f"{func.__name__} executed in {duration:.3f}s")
                
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"{func.__name__} failed after {duration:.3f}s: {e}")
                raise
        
        return wrapper
    return decorator


# =============================================================================
# METRICS EXPORT FUNCTION
# =============================================================================

def get_prometheus_metrics() -> tuple[bytes, str]:
    """
    Get Prometheus metrics in exposition format.
    
    Returns:
        Tuple of (metrics_bytes, content_type)
    """
    if not PROMETHEUS_AVAILABLE:
        return b"# Prometheus client not installed\n", "text/plain"
    
    try:
        metrics = generate_latest(registry)
        return metrics, CONTENT_TYPE_LATEST
    except Exception as e:
        logger.error(f"Error generating Prometheus metrics: {e}")
        return b"# Error generating metrics\n", "text/plain"


# =============================================================================
# METRICS SUMMARY FUNCTION (FOR DASHBOARD)
# =============================================================================

def get_metrics_summary() -> Dict[str, Any]:
    """
    Get metrics summary for dashboard display.
    
    Returns:
        Dictionary with current metric values
    """
    try:
        from paper_trading.models import PaperTrade, PaperPosition, PaperTradingAccount
        from trading.models import Trade, Position
        
        # Paper trading metrics
        paper_trades_count = PaperTrade.objects.count()
        paper_positions_count = PaperPosition.objects.filter(is_open=True).count()
        paper_accounts = PaperTradingAccount.objects.filter(is_active=True)
        paper_total_pnl = sum(
            acc.total_pnl_usd for acc in paper_accounts if acc.total_pnl_usd
        ) if paper_accounts else Decimal('0')
        
        # Real trading metrics
        real_trades_count = Trade.objects.count()
        real_positions_count = Position.objects.filter(status='OPEN').count()
        
        # Database metrics
        db_queries = len(connection.queries) if settings.DEBUG else 0
        
        summary = {
            'timestamp': timezone.now().isoformat(),
            'paper_trading': {
                'total_trades': paper_trades_count,
                'open_positions': paper_positions_count,
                'total_pnl_usd': float(paper_total_pnl),
                'active_accounts': paper_accounts.count() if paper_accounts else 0,
            },
            'real_trading': {
                'total_trades': real_trades_count,
                'open_positions': real_positions_count,
            },
            'system': {
                'prometheus_enabled': PROMETHEUS_AVAILABLE,
                'database_queries': db_queries,
            }
        }
        
        return summary
        
    except Exception as e:
        logger.error(f"Error getting metrics summary: {e}", exc_info=True)
        return {
            'timestamp': timezone.now().isoformat(),
            'error': str(e)
        }


# Log initialization
if PROMETHEUS_AVAILABLE:
    logger.info("Prometheus metrics collection enabled")
else:
    logger.warning("Prometheus metrics collection disabled - install prometheus-client")