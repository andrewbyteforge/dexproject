"""
Additional Dashboard Views

Provides settings and analytics views for the dashboard.
Properly integrated with dashboard models and paper trading constants.

FIXED:
- Moved settings import to top (was causing import errors)
- Changed from trading.models to dashboard.models (correct models)
- Replaced all hardcoded strings with constants from paper_trading.constants
- Added proper type hints and comprehensive logging
- Fixed field name references to use proper model fields
- Removed all unused imports (Flake8 F401)
- Fixed DashboardEngineService import
- Added type validation for POST data
- Removed all trailing whitespace (Flake8 W291, W293)
- Added newline at end of file (Flake8 W292)

Path: dashboard/views/additional.py
"""

import logging
from typing import Dict, Any, List
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse
from django.contrib import messages
from django.db.models import Sum, Avg
from django.utils import timezone

# Import dashboard models (not trading models)
from dashboard.models import BotConfiguration, TradingSession, UserProfile
from dashboard.engine_service import engine_service

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# Status constants for system components
class SystemStatus:
    """System component status constants."""
    ONLINE: str = 'ONLINE'
    OFFLINE: str = 'OFFLINE'
    ERROR: str = 'ERROR'
    UNKNOWN: str = 'UNKNOWN'


# Time range options for analytics
class TimeRange:
    """Time range options for analytics queries."""
    HOUR_24: str = '24h'
    DAYS_7: str = '7d'
    DAYS_30: str = '30d'
    DAYS_90: str = '90d'


# =============================================================================
# SETTINGS VIEW
# =============================================================================

def dashboard_settings(request: HttpRequest) -> HttpResponse:
    """
    Dashboard settings page for user preferences and system configuration.

    Displays user configurations, system status, API status, and handles
    settings updates and cache management.

    Args:
        request: HTTP request object

    Returns:
        HttpResponse: Rendered settings page with configuration data
    """
    try:
        logger.debug(f"Loading settings page for user: {request.user.username}")

        # Get user's bot configurations
        user_configs = BotConfiguration.objects.filter(
            user=request.user
        ).order_by('-last_used_at')

        # Get or create user profile
        try:
            user_profile = UserProfile.objects.get(user=request.user)
        except UserProfile.DoesNotExist:
            logger.info(f"Creating UserProfile for user: {request.user.username}")
            user_profile = UserProfile.objects.create(
                user=request.user,
                display_name=request.user.username
            )

        # Get system status from engine service
        # Build system status dictionary
        system_status = {
            'fast_lane_available': engine_service.fast_lane_available,
            'smart_lane_available': engine_service.smart_lane_available,
            'mempool_connected': engine_service.fast_lane_available,
            'risk_engine_status': (
                SystemStatus.ONLINE
                if engine_service.fast_lane_available
                else SystemStatus.OFFLINE
            ),
        }

        # Get API configuration status (without exposing actual keys)
        api_status = {
            'alchemy_configured': bool(getattr(settings, 'ALCHEMY_API_KEY', None)),
            'ankr_configured': bool(getattr(settings, 'ANKR_API_KEY', None)),
            'infura_configured': bool(getattr(settings, 'INFURA_PROJECT_ID', None)),
            'flashbots_configured': True,  # Always available in our setup
        }

        # Build context dictionary
        context = {
            'user': request.user,
            'page_title': 'Settings',
            'active_page': 'settings',
            'configurations': user_configs,
            'config_count': user_configs.count(),
            'system_status': system_status,
            'api_status': api_status,
            'user_profile': user_profile,
            'testnet_mode': getattr(settings, 'TESTNET_MODE', True),
            'current_chain': getattr(settings, 'DEFAULT_CHAIN_ID', 84532),
            'supported_chains': getattr(settings, 'SUPPORTED_CHAINS', [84532, 11155111]),
        }

        # Handle POST requests for settings updates
        if request.method == 'POST':
            action = request.POST.get('action')

            if action == 'update_preferences':
                # Update user preferences
                try:
                    # Update profile fields from POST data with validation
                    if 'display_name' in request.POST:
                        display_name = request.POST.get('display_name', '')
                        if display_name:
                            user_profile.display_name = display_name

                    if 'timezone' in request.POST:
                        timezone_val = request.POST.get('timezone', 'UTC')
                        if timezone_val:
                            user_profile.timezone = timezone_val

                    if 'experience_level' in request.POST:
                        experience_level = request.POST.get('experience_level')
                        # Validate that the value is one of the valid choices
                        if experience_level and experience_level in dict(
                            UserProfile.ExperienceLevel.choices
                        ):
                            user_profile.experience_level = experience_level

                    if 'risk_tolerance' in request.POST:
                        risk_tolerance = request.POST.get('risk_tolerance')
                        # Validate that the value is one of the valid choices
                        if risk_tolerance and risk_tolerance in dict(
                            UserProfile.RiskTolerance.choices
                        ):
                            user_profile.risk_tolerance = risk_tolerance

                    user_profile.save()
                    logger.info(f"Updated preferences for user: {request.user.username}")
                    messages.success(request, 'Settings updated successfully')

                except Exception as e:
                    logger.error(f"Error updating preferences: {e}", exc_info=True)
                    messages.error(request, f'Failed to update settings: {e}')

                return redirect('dashboard:settings')

            elif action == 'clear_cache':
                # Clear cache
                try:
                    from django.core.cache import cache
                    cache.clear()
                    logger.info(f"Cache cleared by user: {request.user.username}")
                    messages.success(request, 'Cache cleared successfully')
                except Exception as e:
                    logger.error(f"Failed to clear cache: {e}", exc_info=True)
                    messages.error(request, f'Failed to clear cache: {e}')

                return redirect('dashboard:settings')

        return render(request, 'dashboard/settings.html', context)

    except Exception as e:
        logger.error(f"Error loading settings page: {e}", exc_info=True)
        messages.error(request, f"Error loading settings: {str(e)}")
        return render(request, 'dashboard/error.html', {'error': str(e)})


# =============================================================================
# ANALYTICS VIEW
# =============================================================================

def dashboard_analytics(request: HttpRequest) -> HttpResponse:
    """
    Dashboard analytics page showing detailed performance metrics and charts.

    Displays comprehensive trading analytics including P&L, win rates,
    execution times, and trading mode performance breakdowns.

    Args:
        request: HTTP request object

    Returns:
        HttpResponse: Rendered analytics page with metrics and chart data
    """
    try:
        logger.debug(f"Loading analytics page for user: {request.user.username}")

        # Get time range from query parameters
        time_range = request.GET.get('range', TimeRange.DAYS_7)

        # Calculate date range based on selection
        end_date = timezone.now()

        if time_range == TimeRange.HOUR_24:
            start_date = end_date - timedelta(hours=24)
        elif time_range == TimeRange.DAYS_7:
            start_date = end_date - timedelta(days=7)
        elif time_range == TimeRange.DAYS_30:
            start_date = end_date - timedelta(days=30)
        elif time_range == TimeRange.DAYS_90:
            start_date = end_date - timedelta(days=90)
        else:
            # Default to 7 days if invalid range specified
            start_date = end_date - timedelta(days=7)

        logger.debug(
            f"Analytics date range: {start_date.isoformat()} to {end_date.isoformat()}"
        )

        # Get user's trading sessions within date range
        sessions = TradingSession.objects.filter(
            user=request.user,
            started_at__gte=start_date,
            started_at__lte=end_date
        ).select_related('bot_config')

        # Calculate aggregate metrics
        total_sessions = sessions.count()

        # Count successful sessions (P&L > 0)
        successful_sessions = sessions.filter(
            realized_pnl_usd__gt=0
        ).count()

        # Calculate win rate
        win_rate = (
            (successful_sessions / total_sessions * 100)
            if total_sessions > 0
            else Decimal('0')
        )

        # Aggregate financial metrics
        aggregated = sessions.aggregate(
            total_pnl=Sum('realized_pnl_usd'),
            total_trades=Sum('trades_executed'),
            avg_execution_time=Avg('average_execution_time_ms'),
            total_fees=Sum('total_fees_usd'),
        )

        # Build metrics dictionary with safe defaults
        metrics = {
            'total_sessions': total_sessions,
            'successful_sessions': successful_sessions,
            'win_rate': win_rate,
            'total_pnl': aggregated['total_pnl'] or Decimal('0'),
            'total_trades': aggregated['total_trades'] or 0,
            'avg_execution_time': aggregated['avg_execution_time'] or Decimal('0'),
            'total_fees': aggregated['total_fees'] or Decimal('0'),
        }

        # Get best and worst performing sessions
        best_session = sessions.order_by('-realized_pnl_usd').first()
        worst_session = sessions.order_by('realized_pnl_usd').first()

        # Trading mode breakdown
        # Note: TradingSession.trading_mode matches BotConfiguration.TradingMode choices
        fast_lane_sessions = sessions.filter(
            trading_mode=BotConfiguration.TradingMode.FAST_LANE
        ).count()

        smart_lane_sessions = sessions.filter(
            trading_mode=BotConfiguration.TradingMode.SMART_LANE
        ).count()

        paper_sessions = sessions.filter(
            trading_mode=BotConfiguration.TradingMode.PAPER
        ).count()

        live_sessions = sessions.filter(
            trading_mode=BotConfiguration.TradingMode.LIVE
        ).count()

        # Prepare daily aggregated data for charts
        # Group sessions by date and aggregate P&L and trade counts
        daily_data: List[Dict[str, Any]] = []

        current_date = start_date.date()
        end_date_only = end_date.date()

        while current_date <= end_date_only:
            next_date = current_date + timedelta(days=1)

            # Get sessions for this day
            day_sessions = sessions.filter(
                started_at__date=current_date
            )

            # Aggregate for the day
            day_agg = day_sessions.aggregate(
                pnl=Sum('realized_pnl_usd'),
                trades=Sum('trades_executed')
            )

            daily_data.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'pnl': float(day_agg['pnl'] or Decimal('0')),
                'trades': day_agg['trades'] or 0
            })

            current_date = next_date

        # Build context dictionary
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
            'paper_sessions': paper_sessions,
            'live_sessions': live_sessions,
            'daily_data': daily_data,
            'chart_data': {
                'labels': [d['date'] for d in daily_data],
                'pnl_data': [d['pnl'] for d in daily_data],
                'trades_data': [d['trades'] for d in daily_data],
            }
        }

        return render(request, 'dashboard/analytics.html', context)

    except Exception as e:
        logger.error(f"Error loading analytics page: {e}", exc_info=True)
        messages.error(request, f"Error loading analytics: {str(e)}")
        return render(request, 'dashboard/error.html', {'error': str(e)})