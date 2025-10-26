"""
Analytics Views Module

Provides endpoints for system monitoring and Prometheus metrics.

Endpoints:
- /api/analytics/metrics/ - Prometheus metrics endpoint (for scraping)
- /api/analytics/monitoring/data/ - JSON data for dashboard
- /analytics/monitoring/ - Visual monitoring dashboard (HTML)

File: dexproject/analytics/views.py
"""

import logging
import json
from typing import Dict, Any, List
from datetime import datetime, timedelta
from decimal import Decimal

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Count, Sum, Avg, Q
from django.conf import settings

from .metrics import get_prometheus_metrics, get_metrics_summary, metrics_recorder

logger = logging.getLogger(__name__)


# =============================================================================
# PROMETHEUS METRICS ENDPOINT
# =============================================================================

@require_http_methods(["GET"])
@csrf_exempt  # Prometheus scraping doesn't use CSRF tokens
def prometheus_metrics_view(request: HttpRequest) -> HttpResponse:
    """
    Prometheus metrics endpoint for scraping.
    
    Returns metrics in Prometheus exposition format.
    This endpoint should be scraped by Prometheus server.
    
    Endpoint: GET /api/analytics/metrics/
    
    Returns:
        HttpResponse with Prometheus metrics in text format
    """
    try:
        logger.debug("Prometheus metrics requested")
        
        # Get metrics in Prometheus format
        metrics_data, content_type = get_prometheus_metrics()
        
        # Return response
        response = HttpResponse(
            metrics_data,
            content_type=content_type
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error generating Prometheus metrics: {e}", exc_info=True)
        return HttpResponse(
            f"# Error generating metrics: {str(e)}\n",
            content_type="text/plain",
            status=500
        )


# =============================================================================
# MONITORING DASHBOARD DATA API
# =============================================================================

@require_http_methods(["GET"])
def monitoring_data_api(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for monitoring dashboard data.
    
    Returns real-time metrics data in JSON format for the visual dashboard.
    
    Endpoint: GET /api/analytics/monitoring/data/
    
    Query Parameters:
        timeframe: Time period for data ('1h', '24h', '7d', '30d')
    
    Returns:
        JsonResponse with current system metrics
    """
    try:
        logger.debug("Monitoring data API requested")
        
        # Get timeframe parameter
        timeframe = request.GET.get('timeframe', '24h')
        
        # Get base metrics summary
        summary = get_metrics_summary()
        
        # Get detailed metrics
        detailed_metrics = _get_detailed_metrics(timeframe)
        
        # Combine data
        response_data = {
            'success': True,
            'timestamp': timezone.now().isoformat(),
            'timeframe': timeframe,
            'summary': summary,
            'detailed': detailed_metrics,
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error in monitoring data API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)


# =============================================================================
# MONITORING DASHBOARD PAGE
# =============================================================================

@require_http_methods(["GET"])
def monitoring_dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    Visual monitoring dashboard page.
    
    Displays system metrics, trading performance, and health status
    in a dark-themed dashboard interface.
    
    Endpoint: GET /analytics/monitoring/
    
    Returns:
        Rendered HTML template with monitoring dashboard
    """
    try:
        logger.info(f"Monitoring dashboard accessed by user: {request.user}")
        
        # Get initial metrics for page load
        summary = get_metrics_summary()
        
        # Get system information
        system_info = {
            'environment': getattr(settings, 'TRADING_ENVIRONMENT', 'development'),
            'trading_mode': getattr(settings, 'TRADING_MODE', 'PAPER'),
            'debug': settings.DEBUG,
            'redis_available': getattr(settings, 'REDIS_AVAILABLE', False),
            'prometheus_enabled': summary.get('system', {}).get('prometheus_enabled', False),
        }
        
        # Prepare context
        context = {
            'page_title': 'System Monitoring',
            'user': request.user,
            'active_page': 'monitoring',
            'summary': summary,
            'system_info': system_info,
            'timestamp': timezone.now().isoformat(),
        }
        
        return render(request, 'analytics/system_monitoring.html', context)
        
    except Exception as e:
        logger.error(f"Error in monitoring dashboard view: {e}", exc_info=True)
        return render(request, 'analytics/error.html', {
            'error': str(e),
            'page_title': 'Monitoring Error'
        })


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_detailed_metrics(timeframe: str) -> Dict[str, Any]:
    """
    Get detailed metrics for the specified timeframe.
    
    Args:
        timeframe: Time period ('1h', '24h', '7d', '30d')
    
    Returns:
        Dictionary with detailed metrics
    """
    try:
        # Calculate time range
        now = timezone.now()
        time_delta = _parse_timeframe(timeframe)
        start_time = now - time_delta
        
        # Import models
        from paper_trading.models import (
            PaperTrade, PaperPosition, PaperTradingAccount, PaperTradingSession
        )
        from trading.models import Trade, Position
        
        # Paper trading metrics
        paper_trades = PaperTrade.objects.filter(created_at__gte=start_time)
        paper_metrics = {
            'total_count': paper_trades.count(),
            'completed_count': paper_trades.filter(status='completed').count(),
            'failed_count': paper_trades.filter(status='failed').count(),
            'total_volume': float(
                paper_trades.aggregate(
                    total=Sum('amount_in_usd')
                )['total'] or 0
            ),
            'avg_execution_time': float(
                paper_trades.filter(execution_time_ms__isnull=False).aggregate(
                    avg=Avg('execution_time_ms')
                )['avg'] or 0
            ) / 1000,  # Convert to seconds
        }
        
        # Real trading metrics
        real_trades = Trade.objects.filter(created_at__gte=start_time)
        real_metrics = {
            'total_count': real_trades.count(),
            'completed_count': real_trades.filter(status='COMPLETED').count(),
            'failed_count': real_trades.filter(status='FAILED').count(),
        }
        
        # Session metrics
        # Session metrics
        paper_sessions = PaperTradingSession.objects.filter(
            started_at__gte=start_time
        )
        session_metrics = {
            'total_sessions': paper_sessions.count(),
            'active_sessions': paper_sessions.filter(
                status__in=['running', 'active', 'started']  # ✅ CORRECT - use status field
            ).count(),
        }
        
        # Performance metrics
        # Performance metrics
        paper_accounts = PaperTradingAccount.objects.filter(is_active=True)

        # Calculate average return percent manually from existing fields
        total_accounts = paper_accounts.count()
        if total_accounts > 0:
            total_return = 0
            for account in paper_accounts:
                if account.initial_balance_usd > 0:
                    return_pct = ((account.current_balance_usd - account.initial_balance_usd) / 
                                account.initial_balance_usd) * 100
                    total_return += return_pct
            avg_return = total_return / total_accounts
        else:
            avg_return = 0

        performance_metrics = {
            'total_accounts': total_accounts,
            'profitable_accounts': paper_accounts.filter(
                total_profit_loss_usd__gt=0 
            ).count(),
            'avg_return_percent': float(avg_return),
        }
        
        # Hourly distribution (for charts)
        hourly_data = _get_hourly_trade_distribution(start_time, paper_trades)
        
        return {
            'paper_trading': paper_metrics,
            'real_trading': real_metrics,
            'sessions': session_metrics,
            'performance': performance_metrics,
            'hourly_distribution': hourly_data,
            'timeframe': timeframe,
            'start_time': start_time.isoformat(),
            'end_time': now.isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Error getting detailed metrics: {e}", exc_info=True)
        return {
            'error': str(e),
            'timeframe': timeframe,
        }


def _parse_timeframe(timeframe: str) -> timedelta:
    """
    Parse timeframe string to timedelta.
    
    Args:
        timeframe: Time period string ('1h', '24h', '7d', '30d')
    
    Returns:
        timedelta object
    """
    timeframe_map = {
        '1h': timedelta(hours=1),
        '24h': timedelta(hours=24),
        '7d': timedelta(days=7),
        '30d': timedelta(days=30),
    }
    
    return timeframe_map.get(timeframe, timedelta(hours=24))


def _get_hourly_trade_distribution(
    start_time: datetime,
    trades_queryset
) -> List[Dict[str, Any]]:
    """
    Get hourly trade count distribution.
    
    Args:
        start_time: Start time for analysis
        trades_queryset: Django queryset of trades
    
    Returns:
        List of hourly trade counts
    """
    try:
        from django.db.models.functions import TruncHour
        
        # Group trades by hour
        hourly_trades = trades_queryset.annotate(
            hour=TruncHour('created_at')
        ).values('hour').annotate(
            count=Count('trade_id')
        ).order_by('hour')
        
        # Format for charts
        result = []
        for item in hourly_trades:
            result.append({
                'hour': item['hour'].isoformat() if item['hour'] else None,
                'count': item['count'],
            })
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting hourly distribution: {e}")
        return []


# =============================================================================
# HEALTH CHECK ENDPOINT
# =============================================================================

@require_http_methods(["GET"])
@csrf_exempt
def health_check_view(request: HttpRequest) -> JsonResponse:
    """
    Simple health check endpoint.
    
    Returns basic system health status.
    
    Endpoint: GET /api/analytics/health/
    
    Returns:
        JsonResponse with health status
    """
    try:
        # Check database connection
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        db_healthy = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_healthy = False
    
    # Check cache
    try:
        from django.core.cache import cache
        cache.set('health_check', 'ok', 10)
        cache_result = cache.get('health_check')
        cache_healthy = (cache_result == 'ok')
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")
        cache_healthy = False
    
    # Overall health
    healthy = db_healthy and cache_healthy
    
    return JsonResponse({
        'status': 'healthy' if healthy else 'unhealthy',
        'timestamp': timezone.now().isoformat(),
        'checks': {
            'database': 'ok' if db_healthy else 'failed',
            'cache': 'ok' if cache_healthy else 'failed',
        }
    }, status=200 if healthy else 503)


# Log module initialization
logger.info("Analytics views module loaded")