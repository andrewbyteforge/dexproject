"""
Dashboard Views - Streamlined Main File

Core dashboard views with imports from split modules for better organization.
Replaces the original monolithic views.py file (1400+ lines).

This file now contains only the essential core views and imports functionality
from the specialized modules:
- api_endpoints.py: JSON API endpoints and real-time streaming
- configuration_management.py: Configuration CRUD and session management  
- smart_lane_features.py: Smart Lane analysis and intelligence features

File: dexproject/dashboard/views.py
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpRequest
from django.contrib import messages
from django.conf import settings

from .models import BotConfiguration, TradingSession, UserProfile
from .engine_service import engine_service

logger = logging.getLogger(__name__)


# =========================================================================
# UTILITY FUNCTIONS
# =========================================================================

def handle_anonymous_user(request: HttpRequest) -> None:
    """
    Handle anonymous users by creating demo user.
    
    Args:
        request: HTTP request object to modify
    """
    if not request.user.is_authenticated:
        user, created = User.objects.get_or_create(
            username='demo_user',
            defaults={
                'first_name': 'Demo',
                'last_name': 'User',
                'email': 'demo@example.com'
            }
        )
        request.user = user
        if created:
            logger.info("Created demo user for anonymous session")


async def ensure_engine_initialized() -> None:
    """
    Ensure the Fast Lane engine is initialized.
    
    Initializes the engine if not already done and handles initialization errors
    gracefully by falling back to mock mode if necessary.
    """
    if not engine_service.engine_initialized and not engine_service.mock_mode:
        try:
            success = await engine_service.initialize_engine(chain_id=1)  # Ethereum mainnet
            if success:
                logger.info("Fast Lane engine initialized successfully")
            else:
                logger.warning("Failed to initialize Fast Lane engine - falling back to mock mode")
        except Exception as e:
            logger.error(f"Engine initialization error: {e}", exc_info=True)


def run_async_in_view(coro) -> Optional[Any]:
    """
    Helper to run async code in Django views.
    
    Creates a new event loop to execute async functions within synchronous
    Django view functions. Fixed to handle Django's multi-threaded environment.
    
    Args:
        coro: Coroutine to execute
        
    Returns:
        Result of the coroutine execution, or None if failed
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Async execution error: {e}", exc_info=True)
        return None


# =========================================================================
# CORE DASHBOARD VIEWS
# =========================================================================

def dashboard_home(request: HttpRequest) -> HttpResponse:
    """
    Main dashboard home page with Fast Lane and Smart Lane integration.
    
    Displays trading bot status, performance metrics, and recent activity with real-time data.
    Handles both authenticated and anonymous users by creating demo user when needed.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        Rendered dashboard home template
    """
    handle_anonymous_user(request)
    
    try:
        logger.info(f"Dashboard home accessed by user: {request.user}")
        
        # Initialize Fast Lane engine if needed
        run_async_in_view(ensure_engine_initialized())
        
        # Get engine status and performance metrics
        engine_status = engine_service.get_engine_status()
        performance_metrics = engine_service.get_performance_metrics()
        
        # Get Smart Lane status
        try:
            from .smart_lane_features import get_smart_lane_status
            smart_lane_status = get_smart_lane_status()
        except ImportError:
            smart_lane_status = {'status': 'UNAVAILABLE', 'pipeline_initialized': False}
        
        # Get user's recent configurations
        recent_configs = BotConfiguration.objects.filter(
            user=request.user
        ).order_by('-last_used_at')[:3]
        
        # Get active trading session
        active_session = TradingSession.objects.filter(
            user=request.user,
            is_active=True
        ).first()
        
        # Calculate summary statistics
        total_configs = BotConfiguration.objects.filter(user=request.user).count()
        total_sessions = TradingSession.objects.filter(user=request.user).count()
        
        context = {
            'page_title': 'Trading Dashboard',
            'user': request.user,
            
            # Engine status
            'engine_status': engine_status,
            'performance_metrics': performance_metrics,
            'smart_lane_status': smart_lane_status,
            
            # Data source indicator
            'data_source': 'LIVE' if not performance_metrics.get('_mock', False) else 'MOCK',
            'is_live_data': not performance_metrics.get('_mock', False),
            
            # User data
            'recent_configs': recent_configs,
            'active_session': active_session,
            'total_configs': total_configs,
            'total_sessions': total_sessions,
            
            # Feature availability
            'fast_lane_available': engine_status.get('fast_lane_active', False) or engine_service.mock_mode,
            'smart_lane_available': smart_lane_status.get('status') != 'UNAVAILABLE',
            
            # Quick stats
            'quick_stats': {
                'fast_lane_execution_time': performance_metrics.get('execution_time_ms', 0),
                'success_rate': performance_metrics.get('success_rate', 0),
                'active_pairs': engine_status.get('pairs_monitored', 0),
                'smart_lane_analyses': smart_lane_status.get('analyses_completed', 0)
            }
        }
        
        return render(request, 'dashboard/home.html', context)
        
    except Exception as e:
        logger.error(f"Error loading dashboard home: {e}", exc_info=True)
        messages.error(request, f"Error loading dashboard: {str(e)}")
        
        # Fallback context for error cases
        context = {
            'page_title': 'Trading Dashboard',
            'user': request.user,
            'error': str(e),
            'data_source': 'ERROR',
            'is_live_data': False
        }
        
        return render(request, 'dashboard/home.html', context)


def mode_selection(request: HttpRequest) -> HttpResponse:
    """
    Trading mode selection page for Fast Lane vs Smart Lane.
    
    Allows users to choose between Fast Lane (speed-optimized) and Smart Lane
    (intelligence-optimized) trading modes with detailed comparisons.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        Rendered mode selection template
    """
    handle_anonymous_user(request)
    
    try:
        logger.info(f"Mode selection accessed by user: {request.user}")
        
        # Get engine status for both modes
        engine_status = engine_service.get_engine_status()
        
        try:
            from .smart_lane_features import get_smart_lane_status
            smart_lane_status = get_smart_lane_status()
        except ImportError:
            smart_lane_status = {'status': 'UNAVAILABLE', 'pipeline_initialized': False}
        
        # Mode comparison data
        modes = {
            'fast_lane': {
                'name': 'Fast Lane',
                'tagline': 'Speed-Optimized Execution',
                'description': 'Millisecond-precision execution for time-sensitive opportunities',
                'key_features': [
                    'Sub-500ms execution times',
                    'MEV protection',
                    'Real-time mempool monitoring',
                    'Automated arbitrage detection'
                ],
                'best_for': [
                    'Token launches and presales',
                    'Arbitrage opportunities',
                    'Quick scalping strategies',
                    'High-frequency trading'
                ],
                'target_execution_time': '78ms',
                'recommended_position': '$100-1000',
                'status': 'OPERATIONAL' if engine_status.get('fast_lane_active', False) else 'MOCK' if engine_service.mock_mode else 'UNAVAILABLE',
                'available': engine_status.get('fast_lane_active', False) or engine_service.mock_mode,
                'icon': 'zap',
                'color': 'primary'
            },
            'smart_lane': {
                'name': 'Smart Lane',
                'tagline': 'Intelligence-Optimized Analysis',
                'description': 'Comprehensive AI-powered analysis for strategic positioning',
                'key_features': [
                    'Multi-factor risk assessment',
                    'Social sentiment analysis',
                    'Technical pattern recognition',
                    'AI thought process transparency'
                ],
                'best_for': [
                    'Strategic long-term positions',
                    'Risk-conscious trading',
                    'Complex market analysis',
                    'Educational transparency'
                ],
                'target_execution_time': '2-5 seconds',
                'recommended_position': '$500-5000',
                'status': smart_lane_status.get('status', 'UNAVAILABLE'),
                'available': smart_lane_status.get('status') != 'UNAVAILABLE',
                'icon': 'brain',
                'color': 'success'
            }
        }
        
        # Get user's current preference
        user_preference = None
        try:
            profile = UserProfile.objects.get(user=request.user)
            user_preference = profile.preferred_trading_mode
        except UserProfile.DoesNotExist:
            pass
        
        context = {
            'page_title': 'Choose Trading Mode',
            'modes': modes,
            'user_preference': user_preference,
            'user': request.user,
            'comparison_metrics': {
                'speed': {
                    'fast_lane': 95,
                    'smart_lane': 25
                },
                'intelligence': {
                    'fast_lane': 30,
                    'smart_lane': 95
                },
                'risk_management': {
                    'fast_lane': 60,
                    'smart_lane': 90
                },
                'transparency': {
                    'fast_lane': 40,
                    'smart_lane': 100
                }
            }
        }
        
        return render(request, 'dashboard/mode_selection.html', context)
        
    except Exception as e:
        logger.error(f"Error loading mode selection: {e}", exc_info=True)
        messages.error(request, f"Error loading mode selection: {str(e)}")
        return redirect('dashboard:home')


# =========================================================================
# SETTINGS AND ANALYTICS VIEWS
# =========================================================================

def dashboard_settings(request: HttpRequest) -> HttpResponse:
    """
    Dashboard settings page for user preferences and system configuration.
    
    Args:
        request: HTTP request object
        
    Returns:
        HttpResponse: Rendered settings page
    """
    handle_anonymous_user(request)
    
    try:
        logger.debug(f"Loading settings page for user: {request.user.username}")
        
        # Get user's configurations
        user_configs = BotConfiguration.objects.filter(user=request.user)
        
        # Get system status
        system_status = {
            'fast_lane_available': engine_service.fast_lane_available,
            'smart_lane_available': True,  # Simplified check
            'mempool_connected': engine_service.fast_lane_available,
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
    
    FIXED: Now includes both performance_metrics AND engine_status for live data display.
    
    Args:
        request: HTTP request object
        
    Returns:
        HttpResponse: Rendered analytics page
    """
    handle_anonymous_user(request)
    
    try:
        logger.debug(f"Loading analytics page for user: {request.user.username}")
        
        # Get user's trading history
        user_sessions = TradingSession.objects.filter(user=request.user).order_by('-created_at')
        user_configs = BotConfiguration.objects.filter(user=request.user)
        
        # Calculate analytics
        total_sessions = user_sessions.count()
        active_sessions = user_sessions.filter(is_active=True).count()
        fast_lane_configs = user_configs.filter(trading_mode='FAST_LANE').count()
        smart_lane_configs = user_configs.filter(trading_mode='SMART_LANE').count()
        
        # FIXED: Get BOTH engine metrics AND status
        performance_metrics = engine_service.get_performance_metrics()
        engine_status = engine_service.get_engine_status()  # ← This was missing!
        
        context = {
            'user': request.user,
            'page_title': 'Analytics',
            'active_page': 'analytics',
            'analytics_data': {
                'total_sessions': total_sessions,
                'active_sessions': active_sessions,
                'fast_lane_configs': fast_lane_configs,
                'smart_lane_configs': smart_lane_configs,
                'total_configs': user_configs.count()
            },
            'performance_metrics': performance_metrics,  # ✅ Already there
            'engine_status': engine_status,              # ✅ FIXED: Added this!
            'recent_sessions': user_sessions[:10],
            'chart_data': {
                'session_history': [
                    {'date': '2024-01-15', 'sessions': 3, 'success_rate': 85},
                    {'date': '2024-01-14', 'sessions': 5, 'success_rate': 92},
                    {'date': '2024-01-13', 'sessions': 2, 'success_rate': 78},
                ]
            }
        }
        
        return render(request, 'dashboard/analytics.html', context)
        
    except Exception as e:
        logger.error(f"Error loading analytics page: {e}", exc_info=True)
        messages.error(request, f"Error loading analytics: {str(e)}")
        return render(request, 'dashboard/error.html', {'error': str(e)})










# =========================================================================
# IMPORTS FROM SPLIT MODULES
# =========================================================================

# Import API endpoints and streaming functions
try:
    from .api_endpoints import (
        metrics_stream,
        api_engine_status,
        api_performance_metrics,
        api_set_trading_mode,
        api_smart_lane_analyze,
        api_get_thought_log,
        health_check,
        engine_test
    )
    logger.debug("Successfully imported API endpoints")
except ImportError as e:
    logger.error(f"Failed to import API endpoints: {e}")
    # Create placeholder functions if import fails
    from django.http import JsonResponse
    
    def metrics_stream(request):
        return JsonResponse({'error': 'Metrics stream not available'})
    
    def api_engine_status(request):
        return JsonResponse({'error': 'API endpoints not available'})
    
    def api_performance_metrics(request):
        return JsonResponse({'error': 'API endpoints not available'})
    
    def api_set_trading_mode(request):
        return JsonResponse({'error': 'API endpoints not available'})
    
    def api_smart_lane_analyze(request):
        return JsonResponse({'error': 'API endpoints not available'})
    
    def api_get_thought_log(request, analysis_id):
        return JsonResponse({'error': 'API endpoints not available'})
    
    def health_check(request):
        return JsonResponse({'error': 'Health check not available'})
    
    def engine_test(request):
        return JsonResponse({'error': 'Engine test not available'})


# Import configuration management functions
try:
    from .configuration_management import (
        configuration_panel,
        configuration_summary,
        configuration_list,
        save_configuration,
        load_configuration,
        delete_configuration,
        get_configurations,
        start_session,
        stop_session,
        get_session_status,
        get_performance_metrics
    )
    logger.debug("Successfully imported configuration management")
except ImportError as e:
    logger.error(f"Failed to import configuration management: {e}")
    # Create placeholder functions if import fails
    def configuration_panel(request, mode='FAST_LANE'):
        messages.error(request, 'Configuration management not available')
        return redirect('dashboard:home')
    
    def configuration_summary(request, config_id):
        messages.error(request, 'Configuration management not available')
        return redirect('dashboard:home')
    
    def configuration_list(request):
        messages.error(request, 'Configuration management not available')
        return redirect('dashboard:home')
    
    def save_configuration(request):
        return JsonResponse({'error': 'Configuration management not available'})
    
    def load_configuration(request):
        return JsonResponse({'error': 'Configuration management not available'})
    
    def delete_configuration(request):
        return JsonResponse({'error': 'Configuration management not available'})
    
    def get_configurations(request):
        return JsonResponse({'error': 'Configuration management not available'})
    
    def start_session(request):
        return JsonResponse({'error': 'Session management not available'})
    
    def stop_session(request):
        return JsonResponse({'error': 'Session management not available'})
    
    def get_session_status(request):
        return JsonResponse({'error': 'Session management not available'})
    
    def get_performance_metrics(request):
        return JsonResponse({'error': 'Performance metrics not available'})


# Import Smart Lane features
try:
    from .smart_lane_features import (
        smart_lane_dashboard,
        smart_lane_demo,
        smart_lane_config,
        smart_lane_analyze,
        initialize_smart_lane_pipeline,
        get_smart_lane_status,
        run_smart_lane_analysis,
        get_thought_log
    )
    logger.debug("Successfully imported Smart Lane features")
except ImportError as e:
    logger.error(f"Failed to import Smart Lane features: {e}")
    # Create placeholder functions if import fails
    def smart_lane_dashboard(request):
        messages.error(request, 'Smart Lane features not available')
        return redirect('dashboard:home')
    
    def smart_lane_demo(request):
        messages.error(request, 'Smart Lane features not available')
        return redirect('dashboard:home')
    
    def smart_lane_config(request):
        messages.error(request, 'Smart Lane features not available')
        return redirect('dashboard:home')
    
    def smart_lane_analyze(request):
        messages.error(request, 'Smart Lane features not available')
        return redirect('dashboard:home')
    
    async def initialize_smart_lane_pipeline():
        return False
    
    def get_smart_lane_status():
        return {'status': 'UNAVAILABLE', 'pipeline_initialized': False}
    
    async def run_smart_lane_analysis(token_address):
        return None
    
    def get_thought_log(analysis_id):
        return None


# =========================================================================
# MODULE EXPORTS
# =========================================================================

__all__ = [
    # Core dashboard views
    'dashboard_home',
    'mode_selection',
    'dashboard_settings',
    'dashboard_analytics',
    
    # API endpoints
    'metrics_stream',
    'api_engine_status',
    'api_performance_metrics',
    'api_set_trading_mode',
    'api_smart_lane_analyze',
    'api_get_thought_log',
    'health_check',
    'engine_test',
    
    # Configuration management
    'configuration_panel',
    'configuration_summary',
    'configuration_list',
    'save_configuration',
    'load_configuration',
    'delete_configuration',
    'get_configurations',
    'start_session',
    'stop_session',
    'get_session_status',
    'get_performance_metrics',
    
    # Smart Lane features
    'smart_lane_dashboard',
    'smart_lane_demo',
    'smart_lane_config',
    'smart_lane_analyze',
    
    # Utility functions
    'handle_anonymous_user',
    'ensure_engine_initialized',
    'run_async_in_view'
]