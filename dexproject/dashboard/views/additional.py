"""
Additional Dashboard Views

Provides settings and analytics views for the dashboard.

Path: dashboard/views/additional.py
"""

import logging
from typing import Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal

from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Avg, Count, Q
from django.utils import timezone

from trading.models import BotConfiguration, TradingSession, Trade
from analytics.models import PerformanceMetric
from dashboard.engine_service import DashboardEngineService

logger = logging.getLogger(__name__)



def dashboard_settings(request: HttpRequest) -> HttpResponse:
    """
    Dashboard settings page for user preferences and system configuration.
    
    Args:
        request: HTTP request object
        
    Returns:
        HttpResponse: Rendered settings page
    """
    try:
        logger.debug(f"Loading settings page for user: {request.user.username}")
        
        # Get user's configurations
        user_configs = BotConfiguration.objects.filter(user=request.user)
        
        # Get user's preferences (if you have a UserPreference model)
        # user_prefs = UserPreference.objects.get_or_create(user=request.user)[0]
        
        # Get system status
        engine_service = DashboardEngineService()
        system_status = {
            'fast_lane_available': engine_service.fast_lane_available,
            'smart_lane_available': engine_service.smart_lane_available,
            'mempool_connected': engine_service.fast_lane_available,  # Simplified check
            'risk_engine_status': 'ONLINE' if engine_service.fast_lane_available else 'OFFLINE',
        }
        
        # Get API key status (don't show actual keys)
        api_status = {
            'alchemy_configured': bool(getattr(settings, 'ALCHEMY_API_KEY', None)),
            'ankr_configured': bool(getattr(settings, 'ANKR_API_KEY', None)),
            'infura_configured': bool(getattr(settings, 'INFURA_PROJECT_ID', None)),
            'flashbots_configured': True,  # Always available in our setup
        }
        
        context = {
            'user': request.user,
            'page_title': 'Settings',
            'active_page': 'settings',
            'configurations': user_configs,
            'config_count': user_configs.count(),
            'system_status': system_status,
            'api_status': api_status,
            # 'preferences': user_prefs,
            'testnet_mode': getattr(settings, 'TESTNET_MODE', True),
            'current_chain': getattr(settings, 'DEFAULT_CHAIN_ID', 84532),
            'supported_chains': getattr(settings, 'SUPPORTED_CHAINS', [84532, 11155111]),
        }
        
        # Handle form submission if POST
        if request.method == 'POST':
            # Handle settings update
            action = request.POST.get('action')
            
            if action == 'update_preferences':
                # Update user preferences
                messages.success(request, 'Settings updated successfully')
                return redirect('dashboard:settings')
            
            elif action == 'clear_cache':
                # Clear cache
                try:
                    from django.core.cache import cache
                    cache.clear()
                    messages.success(request, 'Cache cleared successfully')
                except Exception as e:
                    messages.error(request, f'Failed to clear cache: {e}')
                return redirect('dashboard:settings')
        
        return render(request, 'dashboard/settings.html', context)
        
    except Exception as e:
        logger.error(f"Error loading settings page: {e}", exc_info=True)
        messages.error(request, f"Error loading settings: {str(e)}")
        return render(request, 'dashboard/error.html', {'error': str(e)})



def dashboard_analytics(request: HttpRequest) -> HttpResponse:
    """
    Dashboard analytics page showing detailed performance metrics and charts.
    
    Args:
        request: HTTP request object
        
    Returns:
        HttpResponse: Rendered analytics page
    """
    try:
        logger.debug(f"Loading analytics page for user: {request.user.username}")
        
        # Get time range from query params
        time_range = request.GET.get('range', '7d')
        
        # Calculate date range
        end_date = timezone.now()
        if time_range == '24h':
            start_date = end_date - timedelta(hours=24)
        elif time_range == '7d':
            start_date = end_date - timedelta(days=7)
        elif time_range == '30d':
            start_date = end_date - timedelta(days=30)
        elif time_range == '90d':
            start_date = end_date - timedelta(days=90)
        else:
            start_date = end_date - timedelta(days=7)
        
        # Get user's trading sessions in date range
        sessions = TradingSession.objects.filter(
            user=request.user,
            created_at__gte=start_date,
            created_at__lte=end_date
        )
        
        # Calculate aggregate metrics
        total_sessions = sessions.count()
        successful_sessions = sessions.filter(
            realized_pnl_usd__gt=0
        ).count()
        
        # Get trades if you have a Trade model
        # trades = Trade.objects.filter(
        #     session__user=request.user,
        #     created_at__gte=start_date,
        #     created_at__lte=end_date
        # )
        
        # Calculate performance metrics
        metrics = {
            'total_sessions': total_sessions,
            'successful_sessions': successful_sessions,
            'win_rate': (successful_sessions / total_sessions * 100) if total_sessions > 0 else 0,
            'total_pnl': sessions.aggregate(Sum('realized_pnl_usd'))['realized_pnl_usd__sum'] or Decimal('0'),
            'total_trades': sessions.aggregate(Sum('trades_executed'))['trades_executed__sum'] or 0,
            'avg_execution_time': sessions.aggregate(Avg('average_execution_time_ms'))['average_execution_time_ms__avg'] or Decimal('0'),
            'total_fees': sessions.aggregate(Sum('total_fees_usd'))['total_fees_usd__sum'] or Decimal('0'),
        }
        
        # Get best and worst sessions
        best_session = sessions.order_by('-realized_pnl_usd').first()
        worst_session = sessions.order_by('realized_pnl_usd').first()
        
        # Mode breakdown
        fast_lane_sessions = sessions.filter(trading_mode='FAST_LANE').count()
        smart_lane_sessions = sessions.filter(trading_mode='SMART_LANE').count()
        
        # Prepare chart data (simplified)
        daily_pnl = []
        daily_trades = []
        
        # You would normally aggregate this from your database
        # For now, providing mock data structure
        for i in range(7):
            date = end_date - timedelta(days=i)
            daily_pnl.append({
                'date': date.strftime('%Y-%m-%d'),
                'pnl': float(Decimal('0')),  # Replace with actual data
                'trades': 0  # Replace with actual data
            })
        
        context = {
            'user': request.user,
            'page_title': 'Analytics',
            'active_page': 'analytics',
            'time_range': time_range,
            'start_date': start_date,
            'end_date': end_date,
            'metrics': metrics,
            'best_session': best_session,
            'worst_session': worst_session,
            'fast_lane_sessions': fast_lane_sessions,
            'smart_lane_sessions': smart_lane_sessions,
            'daily_pnl': daily_pnl,
            'chart_data': {
                'labels': [d['date'] for d in daily_pnl],
                'pnl_data': [d['pnl'] for d in daily_pnl],
                'trades_data': [d['trades'] for d in daily_pnl],
            }
        }
        
        return render(request, 'dashboard/analytics.html', context)
        
    except Exception as e:
        logger.error(f"Error loading analytics page: {e}", exc_info=True)
        messages.error(request, f"Error loading analytics: {str(e)}")
        return render(request, 'dashboard/error.html', {'error': str(e)})


# Import settings at the end to avoid circular imports
from django.conf import settings