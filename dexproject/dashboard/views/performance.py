"""
Performance Metrics Views for Dashboard

Provides real-time and historical performance metrics via API endpoints.

Path: dashboard/views/performance.py
"""

import logging
import json
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List

from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Sum, Avg, Count, Q
from django.core.cache import cache

from trading.models import TradingSession, BotConfiguration
from dashboard.engine_service import DashboardEngineService

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def get_performance_metrics(request: HttpRequest) -> JsonResponse:
    """
    Get real-time performance metrics for the dashboard.
    
    This endpoint provides both real-time engine metrics and historical
    database metrics, with caching for performance.
    
    Args:
        request: HTTP request with optional parameters
        
    Returns:
        JsonResponse: Performance metrics data
    """
    try:
        # Get parameters
        time_range = request.GET.get('range', '24h')
        session_id = request.GET.get('session_id')
        use_cache = request.GET.get('cache', 'true').lower() == 'true'
        
        # Try to get from cache first
        cache_key = f'performance_metrics_{request.user.id}_{time_range}_{session_id}'
        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.debug(f"Returning cached metrics for user {request.user.username}")
                return JsonResponse(cached_data)
        
        # Calculate date range
        end_date = timezone.now()
        if time_range == '1h':
            start_date = end_date - timedelta(hours=1)
        elif time_range == '24h':
            start_date = end_date - timedelta(hours=24)
        elif time_range == '7d':
            start_date = end_date - timedelta(days=7)
        elif time_range == '30d':
            start_date = end_date - timedelta(days=30)
        else:
            start_date = end_date - timedelta(hours=24)
        
        # Initialize metrics
        metrics = {
            'success': True,
            'timestamp': end_date.isoformat(),
            'time_range': time_range,
            'real_time': {},
            'historical': {},
            'session': {},
            'system': {}
        }
        
        # Get real-time metrics from engine
        engine_service = DashboardEngineService()
        
        if session_id:
            # Get specific session metrics
            session_metrics = asyncio.run(
                engine_service.get_session_metrics(session_id)
            )
            metrics['session'] = session_metrics
        
        # Get live engine metrics
        live_metrics = asyncio.run(engine_service.get_performance_metrics())
        
        # Real-time metrics from engine
        metrics['real_time'] = {
            'execution_time_ms': live_metrics.get('execution_time_ms', 78),
            'trades_per_second': live_metrics.get('trades_per_second', 0),
            'success_rate': live_metrics.get('success_rate', 0),
            'active_positions': live_metrics.get('active_positions', 0),
            'mempool_latency_ms': live_metrics.get('mempool_latency_ms', 0),
            'gas_price_gwei': live_metrics.get('gas_price_gwei', 0),
            'risk_cache_hits': live_metrics.get('risk_cache_hits', 0),
            'risk_cache_misses': live_metrics.get('risk_cache_misses', 0),
            'is_live': not live_metrics.get('_mock', False)
        }
        
        # Historical metrics from database
        sessions = TradingSession.objects.filter(
            user=request.user,
            created_at__gte=start_date,
            created_at__lte=end_date
        )
        
        # Calculate historical metrics
        total_sessions = sessions.count()
        completed_sessions = sessions.filter(
            status__in=['COMPLETED', 'STOPPED']
        ).count()
        
        profitable_sessions = sessions.filter(
            realized_pnl_usd__gt=0
        ).count()
        
        # Aggregate calculations
        aggregates = sessions.aggregate(
            total_pnl=Sum('realized_pnl_usd'),
            total_trades=Sum('trades_executed'),
            successful_trades=Sum('successful_trades'),
            failed_trades=Sum('failed_trades'),
            total_fees=Sum('total_fees_usd'),
            avg_execution_time=Avg('average_execution_time_ms'),
            max_drawdown=Avg('max_drawdown_percent')
        )
        
        metrics['historical'] = {
            'total_sessions': total_sessions,
            'completed_sessions': completed_sessions,
            'profitable_sessions': profitable_sessions,
            'win_rate': (profitable_sessions / completed_sessions * 100) if completed_sessions > 0 else 0,
            'total_pnl': float(aggregates['total_pnl'] or 0),
            'total_trades': aggregates['total_trades'] or 0,
            'successful_trades': aggregates['successful_trades'] or 0,
            'failed_trades': aggregates['failed_trades'] or 0,
            'trade_success_rate': (
                (aggregates['successful_trades'] / aggregates['total_trades'] * 100)
                if aggregates['total_trades'] and aggregates['total_trades'] > 0 else 0
            ),
            'total_fees': float(aggregates['total_fees'] or 0),
            'avg_execution_time_ms': float(aggregates['avg_execution_time'] or 0),
            'max_drawdown_percent': float(aggregates['max_drawdown'] or 0)
        }
        
        # Mode-specific metrics
        fast_lane_sessions = sessions.filter(trading_mode='FAST_LANE')
        smart_lane_sessions = sessions.filter(trading_mode='SMART_LANE')
        
        metrics['mode_breakdown'] = {
            'fast_lane': {
                'sessions': fast_lane_sessions.count(),
                'total_pnl': float(
                    fast_lane_sessions.aggregate(Sum('realized_pnl_usd'))['realized_pnl_usd__sum'] or 0
                ),
                'avg_execution_ms': float(
                    fast_lane_sessions.aggregate(Avg('average_execution_time_ms'))['average_execution_time_ms__avg'] or 0
                ),
                'trades': fast_lane_sessions.aggregate(Sum('trades_executed'))['trades_executed__sum'] or 0
            },
            'smart_lane': {
                'sessions': smart_lane_sessions.count(),
                'total_pnl': float(
                    smart_lane_sessions.aggregate(Sum('realized_pnl_usd'))['realized_pnl_usd__sum'] or 0
                ),
                'avg_execution_ms': float(
                    smart_lane_sessions.aggregate(Avg('average_execution_time_ms'))['average_execution_time_ms__avg'] or 0
                ),
                'trades': smart_lane_sessions.aggregate(Sum('trades_executed'))['trades_executed__sum'] or 0
            }
        }
        
        # System status metrics
        metrics['system'] = {
            'fast_lane_available': engine_service.fast_lane_available,
            'smart_lane_available': engine_service.smart_lane_available,
            'engine_status': 'ONLINE' if engine_service.fast_lane_available else 'MOCK',
            'last_update': datetime.now().isoformat()
        }
        
        # Get current active session if exists
        active_session = sessions.filter(status='RUNNING').first()
        if active_session:
            metrics['active_session'] = {
                'session_id': str(active_session.session_id),
                'mode': active_session.trading_mode,
                'started_at': active_session.started_at.isoformat() if active_session.started_at else None,
                'current_pnl': float(active_session.realized_pnl_usd),
                'trades_executed': active_session.trades_executed,
                'status': active_session.status
            }
        else:
            metrics['active_session'] = None
        
        # Calculate 24h comparison
        yesterday_end = end_date - timedelta(days=1)
        yesterday_start = yesterday_end - timedelta(days=1)
        
        yesterday_sessions = TradingSession.objects.filter(
            user=request.user,
            created_at__gte=yesterday_start,
            created_at__lte=yesterday_end
        )
        
        yesterday_pnl = yesterday_sessions.aggregate(Sum('realized_pnl_usd'))['realized_pnl_usd__sum'] or 0
        today_pnl = aggregates['total_pnl'] or 0
        
        metrics['comparison'] = {
            '24h_change': float(today_pnl - yesterday_pnl) if time_range == '24h' else 0,
            '24h_change_percent': (
                float((today_pnl - yesterday_pnl) / yesterday_pnl * 100)
                if yesterday_pnl and yesterday_pnl != 0 else 0
            )
        }
        
        # Cache the results
        cache.set(cache_key, metrics, 30)  # Cache for 30 seconds
        
        return JsonResponse(metrics)
        
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'real_time': {
                'execution_time_ms': 78,
                'trades_per_second': 0,
                'success_rate': 0,
                'active_positions': 0,
                'is_live': False
            },
            'historical': {},
            'system': {
                'fast_lane_available': False,
                'smart_lane_available': False,
                'engine_status': 'ERROR'
            }
        }, status=500)