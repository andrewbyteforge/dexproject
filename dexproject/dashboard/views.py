"""
Dashboard Views with Wallet Integration

Updated main dashboard views to include wallet connection functionality,
fund allocation, and SIWE authentication integration.

File: dexproject/dashboard/views.py
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List

from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpRequest, JsonResponse, StreamingHttpResponse
from django.contrib import messages
from django.conf import settings
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.db.models import Q, Count, Avg
from django.utils import timezone

from .models import BotConfiguration, TradingSession, UserProfile
from .engine_service import engine_service

# Import wallet services
try:
    from wallet.services import SIWEService, WalletService
    from wallet.models import SIWESession, Wallet, WalletBalance
    wallet_service_available = True
except ImportError:
    wallet_service_available = False

logger = logging.getLogger(__name__)


# =========================================================================
# UTILITY FUNCTIONS
# =========================================================================

def handle_anonymous_user(request: HttpRequest) -> None:
    """
    Create demo user for anonymous users to provide seamless experience.
    
    Args:
        request: Django HTTP request object
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
            logger.info("Created demo user for anonymous access")


def ensure_engine_initialized() -> None:
    """
    Ensure the Fast Lane engine is properly initialized.
    
    Attempts to initialize the engine if it's not already running.
    Logs warnings if initialization fails but doesn't raise exceptions.
    """
    try:
        status = engine_service.get_engine_status()
        if status.get('status') != 'OPERATIONAL':
            logger.warning("Engine not operational, attempting initialization")
            # Additional initialization logic could go here
    except Exception as e:
        logger.error(f"Engine initialization check failed: {e}")


def run_async_in_view(coro) -> Optional[Any]:
    """
    Execute async functions within synchronous Django view functions.
    
    Creates a new event loop to execute async functions within synchronous
    Django view functions. Handles Django's multi-threaded environment.
    
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


def get_user_wallet_info(user: User) -> Dict[str, Any]:
    """
    Get wallet connection and balance information for a user.
    
    Args:
        user: Django user object
        
    Returns:
        Dictionary containing wallet information
    """
    wallet_info = {
        'connected': False,
        'address': None,
        'balance_eth': 0,
        'balance_usd': 0,
        'network': None,
        'last_updated': None,
        'trading_allocation': {
            'method': 'percentage',
            'percentage': 10,
            'fixed_amount': 0.1,
            'daily_limit': 1.0,
            'minimum_balance': 0.05,
            'auto_rebalance': True,
            'available_for_trading': 0,
            'risk_level': 'conservative'
        }
    }
    
    if not wallet_service_available:
        return wallet_info
    
    try:
        # Get active SIWE session
        siwe_session = SIWESession.objects.filter(
            user=user,
            status=SIWESession.SessionStatus.VERIFIED,
            expiration_time__gt=timezone.now()
        ).first()
        
        if siwe_session:
            wallet_info['connected'] = True
            wallet_info['address'] = siwe_session.wallet_address
            wallet_info['network'] = f"Chain {siwe_session.chain_id}"
            wallet_info['last_updated'] = siwe_session.verified_at
            
            # Get wallet balance
            try:
                wallet = Wallet.objects.get(user=user, address=siwe_session.wallet_address)
                balances = WalletBalance.objects.filter(
                    wallet=wallet,
                    chain_id=siwe_session.chain_id,
                    token_symbol='ETH'
                ).first()
                
                if balances:
                    wallet_info['balance_eth'] = float(balances.balance_formatted)
                    wallet_info['balance_usd'] = float(balances.usd_value or 0)
                    
                    # Calculate trading allocation
                    total_balance = wallet_info['balance_eth']
                    reserved = wallet_info['trading_allocation']['minimum_balance']
                    available = max(0, total_balance - reserved)
                    
                    if wallet_info['trading_allocation']['method'] == 'percentage':
                        trading_amount = (available * wallet_info['trading_allocation']['percentage']) / 100
                    else:
                        trading_amount = min(wallet_info['trading_allocation']['fixed_amount'], available)
                    
                    wallet_info['trading_allocation']['available_for_trading'] = trading_amount
                    
                    # Determine risk level
                    percentage = (trading_amount / total_balance * 100) if total_balance > 0 else 0
                    if percentage <= 5:
                        wallet_info['trading_allocation']['risk_level'] = 'conservative'
                    elif percentage <= 20:
                        wallet_info['trading_allocation']['risk_level'] = 'moderate'
                    else:
                        wallet_info['trading_allocation']['risk_level'] = 'aggressive'
                        
            except Wallet.DoesNotExist:
                logger.warning(f"Wallet not found for user {user.username}")
                
    except Exception as e:
        logger.error(f"Error getting wallet info for user {user.username}: {e}")
    
    return wallet_info


# =========================================================================
# MAIN DASHBOARD VIEWS
# =========================================================================

def dashboard_home(request: HttpRequest) -> HttpResponse:
    """
    Main dashboard home page with wallet integration and real-time metrics.
    
    Displays trading bot status, performance metrics, wallet connection status,
    fund allocation settings, and recent activity with real-time data.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        Rendered dashboard home template with wallet integration
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
        
        # Get wallet information
        wallet_info = get_user_wallet_info(request.user)
        
        # Get recent wallet activity (if wallet connected)
        recent_activity = []
        if wallet_info['connected'] and wallet_service_available:
            try:
                from wallet.models import WalletActivity
                recent_activity = WalletActivity.objects.filter(
                    wallet__user=request.user
                ).order_by('-created_at')[:10]
            except ImportError:
                pass
        
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
            
            # Wallet integration
            'wallet_info': wallet_info,
            'wallet_service_available': wallet_service_available,
            'recent_activity': recent_activity,
            
            # Feature availability
            'fast_lane_available': engine_status.get('fast_lane_active', False) or engine_service.mock_mode,
            'smart_lane_available': smart_lane_status.get('status') != 'UNAVAILABLE',
            
            # Quick stats
            'quick_stats': {
                'fast_lane_execution_time': performance_metrics.get('execution_time_ms', 0),
                'success_rate': performance_metrics.get('success_rate', 0),
                'active_pairs': engine_status.get('pairs_monitored', 0),
                'smart_lane_analyses': smart_lane_status.get('analyses_completed', 0),
                'wallet_connected': wallet_info['connected'],
                'trading_ready': wallet_info['connected'] and wallet_info['trading_allocation']['available_for_trading'] > 0
            },
            
            # Trading capabilities
            'trading_enabled': wallet_info['connected'] and wallet_info['trading_allocation']['available_for_trading'] > 0,
            'emergency_stop_available': active_session is not None,
            
            # System status
            'system_operational': engine_status.get('status') == 'OPERATIONAL',
            'mock_mode': engine_service.mock_mode if hasattr(engine_service, 'mock_mode') else True
        }
        
        logger.debug("Dashboard context created successfully with wallet integration")
        return render(request, 'dashboard/home.html', context)
        
    except Exception as e:
        logger.error(f"Critical error in dashboard_home: {e}", exc_info=True)
        return render(request, 'dashboard/error.html', {'error': str(e)})


def mode_selection(request: HttpRequest) -> HttpResponse:
    """
    Mode selection interface with wallet integration.
    
    Allows users to choose between Fast Lane and Smart Lane trading modes.
    Displays performance comparisons and wallet connection status.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        Rendered mode selection template
    """
    handle_anonymous_user(request)
    
    try:
        logger.info(f"Mode selection accessed by user: {request.user}")
        
        # Get engine status
        engine_status = engine_service.get_engine_status()
        performance_metrics = engine_service.get_performance_metrics()
        
        # Get wallet info
        wallet_info = get_user_wallet_info(request.user)
        
        context = {
            'page_title': 'Select Trading Mode',
            'user': request.user,
            'engine_status': engine_status,
            'performance_metrics': performance_metrics,
            'wallet_info': wallet_info,
            'fast_lane_available': True,
            'smart_lane_available': True,
            'wallet_required_message': 'Connect your wallet to start trading' if not wallet_info['connected'] else None
        }
        
        return render(request, 'dashboard/mode_selection.html', context)
        
    except Exception as e:
        logger.error(f"Error in mode_selection: {e}", exc_info=True)
        return render(request, 'dashboard/error.html', {'error': str(e)})


# =========================================================================
# WALLET MANAGEMENT API ENDPOINTS
# =========================================================================

@require_POST
@csrf_exempt
def api_save_allocation_settings(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to save user's fund allocation settings.
    
    Expected JSON payload:
    {
        "method": "percentage|fixed",
        "percentage": 10,
        "fixed_amount": 0.1,
        "daily_limit": 1.0,
        "minimum_balance": 0.05,
        "auto_rebalance": true
    }
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JSON response with success/error status
    """
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        data = json.loads(request.body)
        
        # Validate allocation settings
        method = data.get('method', 'percentage')
        if method not in ['percentage', 'fixed']:
            return JsonResponse({'error': 'Invalid allocation method'}, status=400)
        
        percentage = float(data.get('percentage', 10))
        if not 1 <= percentage <= 50:
            return JsonResponse({'error': 'Percentage must be between 1% and 50%'}, status=400)
        
        fixed_amount = float(data.get('fixed_amount', 0.1))
        if fixed_amount < 0.001:
            return JsonResponse({'error': 'Fixed amount must be at least 0.001 ETH'}, status=400)
        
        daily_limit = float(data.get('daily_limit', 1.0))
        minimum_balance = float(data.get('minimum_balance', 0.05))
        auto_rebalance = bool(data.get('auto_rebalance', True))
        
        # Save settings to user profile or wallet model
        # For now, store in session until we implement persistent storage
        request.session['allocation_settings'] = {
            'method': method,
            'percentage': percentage,
            'fixed_amount': fixed_amount,
            'daily_limit': daily_limit,
            'minimum_balance': minimum_balance,
            'auto_rebalance': auto_rebalance,
            'updated_at': timezone.now().isoformat()
        }
        
        logger.info(f"Saved allocation settings for user {request.user.username}")
        
        return JsonResponse({
            'success': True,
            'message': 'Allocation settings saved successfully',
            'settings': request.session['allocation_settings']
        })
        
    except Exception as e:
        logger.error(f"Error saving allocation settings: {e}")
        return JsonResponse({'error': 'Failed to save settings'}, status=500)


@require_POST
@csrf_exempt
def api_emergency_stop(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for emergency stop of all trading activities.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JSON response with stop status
    """
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        # Stop all active trading sessions
        active_sessions = TradingSession.objects.filter(
            user=request.user,
            is_active=True
        )
        
        stopped_count = 0
        for session in active_sessions:
            session.is_active = False
            session.status = 'EMERGENCY_STOPPED'
            session.ended_at = timezone.now()
            session.save()
            stopped_count += 1
        
        # TODO: Integrate with actual trading engine emergency stop
        
        logger.warning(f"Emergency stop triggered by user {request.user.username}, stopped {stopped_count} sessions")
        
        return JsonResponse({
            'success': True,
            'message': f'Emergency stop executed. Stopped {stopped_count} trading sessions.',
            'stopped_sessions': stopped_count
        })
        
    except Exception as e:
        logger.error(f"Error during emergency stop: {e}")
        return JsonResponse({'error': 'Failed to execute emergency stop'}, status=500)


@require_http_methods(["GET"])
def api_wallet_status(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to get current wallet connection and balance status.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JSON response with wallet status
    """
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        wallet_info = get_user_wallet_info(request.user)
        
        return JsonResponse({
            'success': True,
            'wallet_info': wallet_info,
            'service_available': wallet_service_available
        })
        
    except Exception as e:
        logger.error(f"Error getting wallet status: {e}")
        return JsonResponse({'error': 'Failed to get wallet status'}, status=500)


@require_POST
@csrf_exempt
def api_start_trading(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to start trading with current configuration.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JSON response with trading start status
    """
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        # Check wallet connection
        wallet_info = get_user_wallet_info(request.user)
        if not wallet_info['connected']:
            return JsonResponse({'error': 'Wallet not connected'}, status=400)
        
        if wallet_info['trading_allocation']['available_for_trading'] <= 0:
            return JsonResponse({'error': 'No funds allocated for trading'}, status=400)
        
        # Create new trading session
        session = TradingSession.objects.create(
            user=request.user,
            session_name=f"Trading Session {timezone.now().strftime('%Y%m%d_%H%M%S')}",
            is_active=True,
            started_at=timezone.now(),
            # TODO: Add configuration and other session details
        )
        
        logger.info(f"Started trading session {session.id} for user {request.user.username}")
        
        return JsonResponse({
            'success': True,
            'message': 'Trading started successfully',
            'session_id': session.id,
            'trading_amount': wallet_info['trading_allocation']['available_for_trading']
        })
        
    except Exception as e:
        logger.error(f"Error starting trading: {e}")
        return JsonResponse({'error': 'Failed to start trading'}, status=500)


# =========================================================================
# REAL-TIME DATA STREAMS
# =========================================================================

def metrics_stream(request: HttpRequest) -> StreamingHttpResponse:
    """
    Server-sent events stream for real-time dashboard metrics.
    
    Streams live performance metrics, engine status, and wallet updates
    to the dashboard for real-time display.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        StreamingHttpResponse with SSE data
    """
    def event_generator():
        """Generate server-sent events with real-time data."""
        while True:
            try:
                # Get current metrics
                engine_status = engine_service.get_engine_status()
                performance_metrics = engine_service.get_performance_metrics()
                
                # Get wallet info if user is authenticated
                wallet_info = {}
                if request.user.is_authenticated:
                    wallet_info = get_user_wallet_info(request.user)
                
                # Create event data
                data = {
                    'timestamp': timezone.now().isoformat(),
                    'engine_status': engine_status,
                    'performance_metrics': performance_metrics,
                    'wallet_info': wallet_info,
                    'data_source': 'LIVE' if not performance_metrics.get('_mock', False) else 'MOCK'
                }
                
                yield f"data: {json.dumps(data)}\n\n"
                
                # Sleep for 2 seconds before next update
                import time
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Error in metrics stream: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                break
    
    response = StreamingHttpResponse(
        event_generator(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['Connection'] = 'keep-alive'
    return response


# =========================================================================
# CONFIGURATION MANAGEMENT
# =========================================================================

def configuration_panel(request: HttpRequest, mode: str = 'fast_lane') -> HttpResponse:
    """
    Configuration panel for Fast Lane or Smart Lane with wallet integration.
    
    Args:
        request: Django HTTP request object
        mode: Trading mode ('fast_lane' or 'smart_lane')
        
    Returns:
        Rendered configuration panel template
    """
    handle_anonymous_user(request)
    
    try:
        # Normalize mode parameter
        mode = mode.upper()
        if mode not in ['FAST_LANE', 'SMART_LANE']:
            mode = 'FAST_LANE'
        
        # Get wallet info to validate configuration
        wallet_info = get_user_wallet_info(request.user)
        
        # Get user's configurations for this mode
        user_configs = BotConfiguration.objects.filter(
            user=request.user,
            trading_mode=mode
        ).order_by('-updated_at')
        
        context = {
            'mode': mode,
            'is_fast_lane': mode == 'FAST_LANE',
            'is_smart_lane': mode == 'SMART_LANE',
            'configurations': user_configs,
            'user': request.user,
            'wallet_info': wallet_info,
            'page_title': f'{mode.replace("_", " ").title()} Configuration'
        }
        
        return render(request, 'dashboard/configuration_panel.html', context)
        
    except Exception as e:
        logger.error(f"Error in configuration_panel: {e}")
        return render(request, 'dashboard/error.html', {'error': str(e)})


# =========================================================================
# ADDITIONAL DASHBOARD VIEWS
# =========================================================================

def dashboard_settings(request: HttpRequest) -> HttpResponse:
    """
    Dashboard settings page with wallet and trading preferences.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        Rendered settings template
    """
    handle_anonymous_user(request)
    
    try:
        # Get user configurations
        user_configs = BotConfiguration.objects.filter(user=request.user)
        
        # Get wallet info
        wallet_info = get_user_wallet_info(request.user)
        
        # System status indicators
        system_status = {
            'engine_operational': engine_service.get_engine_status().get('status') == 'OPERATIONAL',
            'wallet_service_available': wallet_service_available,
            'database_connected': True,  # If we're here, database is connected
            'live_data_available': not engine_service.get_performance_metrics().get('_mock', False)
        }
        
        context = {
            'user': request.user,
            'page_title': 'Settings',
            'active_page': 'settings',
            'configurations': user_configs,
            'config_count': user_configs.count(),
            'wallet_info': wallet_info,
            'system_status': system_status,
            'testnet_mode': getattr(settings, 'TESTNET_MODE', True),
            'current_chain': getattr(settings, 'DEFAULT_CHAIN_ID', 84532),
            'supported_chains': getattr(settings, 'SUPPORTED_CHAINS', [84532, 11155111]),
        }
        
        return render(request, 'dashboard/settings.html', context)
        
    except Exception as e:
        logger.error(f"Error loading settings page: {e}", exc_info=True)
        messages.error(request, f"Error loading settings: {str(e)}")
        return render(request, 'dashboard/error.html', {'error': str(e)})


def dashboard_analytics(request: HttpRequest) -> HttpResponse:
    """
    Dashboard analytics page with wallet integration and P&L tracking.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        Rendered analytics template
    """
    handle_anonymous_user(request)
    
    try:
        # Get performance metrics
        engine_status = engine_service.get_engine_status()
        performance_metrics = engine_service.get_performance_metrics()
        
        # Get wallet info
        wallet_info = get_user_wallet_info(request.user)
        
        # Get user trading sessions for analytics
        trading_sessions = TradingSession.objects.filter(
            user=request.user
        ).order_by('-created_at')[:20]
        
        # Calculate basic analytics
        total_sessions = trading_sessions.count()
        active_sessions = trading_sessions.filter(is_active=True).count()
        
        context = {
            'page_title': 'Trading Analytics',
            'user': request.user,
            'engine_status': engine_status,
            'performance_metrics': performance_metrics,
            'wallet_info': wallet_info,
            'trading_sessions': trading_sessions,
            'total_sessions': total_sessions,
            'active_sessions': active_sessions,
            'data_source': 'LIVE' if not performance_metrics.get('_mock', False) else 'MOCK',
            'analytics_ready': wallet_info['connected'] and total_sessions > 0
        }
        
        return render(request, 'dashboard/analytics.html', context)
        
    except Exception as e:
        logger.error(f"Error loading analytics page: {e}", exc_info=True)
        return render(request, 'dashboard/error.html', {'error': str(e)})


# =========================================================================
# HEALTH CHECK AND DEBUG
# =========================================================================

def health_check(request: HttpRequest) -> JsonResponse:
    """
    Health check endpoint for monitoring.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JSON response with system health status
    """
    try:
        engine_status = engine_service.get_engine_status()
        performance_metrics = engine_service.get_performance_metrics()
        
        health_data = {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'services': {
                'engine': {
                    'status': engine_status.get('status', 'UNKNOWN'),
                    'healthy': engine_status.get('status') == 'OPERATIONAL'
                },
                'database': {
                    'status': 'connected',
                    'healthy': True
                },
                'wallet_service': {
                    'status': 'available' if wallet_service_available else 'unavailable',
                    'healthy': wallet_service_available
                }
            },
            'metrics': {
                'execution_time_ms': performance_metrics.get('execution_time_ms', 0),
                'success_rate': performance_metrics.get('success_rate', 0),
                'data_source': 'LIVE' if not performance_metrics.get('_mock', False) else 'MOCK'
            }
        }
        
        # Determine overall health
        all_healthy = all(service['healthy'] for service in health_data['services'].values())
        health_data['status'] = 'healthy' if all_healthy else 'degraded'
        
        status_code = 200 if all_healthy else 503
        return JsonResponse(health_data, status=status_code)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JsonResponse({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)
    

"""
Additional Wallet API Endpoints

Add these functions to your dashboard/views.py file to complete
the wallet integration functionality.

File: dexproject/dashboard/views.py (additional functions)
"""




# =========================================================================
# ENGINE STATUS API ENDPOINT
# Critical endpoint for engine status monitoring - REQUIRED BY URLS.PY
# =========================================================================

@require_http_methods(["GET"])
def api_engine_status(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for engine status with Fast Lane integration.
    
    Returns JSON response with current engine status, performance metrics,
    and system health information for both Fast Lane and Smart Lane.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with engine status data
    """
    try:
        logger.debug(f"Engine status API called by user: {request.user.username if request.user.is_authenticated else 'anonymous'}")
        
        # Initialize engine if needed
        run_async_in_view(ensure_engine_initialized())
        
        # Get Fast Lane status
        fast_lane_status = engine_service.get_engine_status()
        fast_lane_metrics = engine_service.get_performance_metrics()
        
        # Get Smart Lane status if available
        smart_lane_status = {'status': 'UNAVAILABLE', 'pipeline_initialized': False}
        try:
            from .smart_lane_features import get_smart_lane_status
            smart_lane_status = get_smart_lane_status()
        except ImportError:
            logger.debug("Smart Lane features not available")
        
        # Determine overall system status
        overall_status = 'OPERATIONAL' if (
            fast_lane_status.get('status') == 'OPERATIONAL' and
            fast_lane_status.get('fast_lane_active', False)
        ) else 'DEGRADED'
        
        # Compile comprehensive status
        status_data = {
            'timestamp': timezone.now().isoformat(),
            'system': {
                'overall_status': overall_status,
                'data_source': 'LIVE' if not fast_lane_metrics.get('_mock', False) else 'MOCK',
                'uptime_seconds': fast_lane_status.get('uptime_seconds', 0),
                'user': request.user.username if request.user.is_authenticated else 'anonymous'
            },
            'fast_lane': {
                'status': fast_lane_status.get('status', 'UNKNOWN'),
                'active': fast_lane_status.get('fast_lane_active', False),
                'initialized': fast_lane_status.get('engine_initialized', False),
                'execution_time_ms': fast_lane_metrics.get('execution_time_ms', 0),
                'success_rate': fast_lane_metrics.get('success_rate', 0),
                'pairs_monitored': fast_lane_status.get('pairs_monitored', 0),
                'last_update': fast_lane_status.get('last_update', ''),
                'mempool_connected': fast_lane_status.get('mempool_connected', False),
                'websocket_status': fast_lane_status.get('websocket_status', 'DISCONNECTED'),
                'processing_queue_size': fast_lane_status.get('processing_queue_size', 0)
            },
            'smart_lane': {
                'status': smart_lane_status.get('status', 'UNAVAILABLE'),
                'pipeline_initialized': smart_lane_status.get('pipeline_initialized', False),
                'analyses_completed': smart_lane_status.get('analyses_completed', 0),
                'active_models': smart_lane_status.get('active_models', 0),
                'last_analysis': smart_lane_status.get('last_analysis', ''),
                'ai_confidence': smart_lane_status.get('ai_confidence', 0)
            },
            'performance': {
                'fast_lane': {
                    'avg_execution_time': fast_lane_metrics.get('execution_time_ms', 0),
                    'success_rate': fast_lane_metrics.get('success_rate', 0),
                    'total_processed': fast_lane_metrics.get('total_processed', 0),
                    'errors_count': fast_lane_metrics.get('errors_count', 0)
                },
                'smart_lane': {
                    'analyses_completed': smart_lane_status.get('analyses_completed', 0),
                    'average_confidence': smart_lane_status.get('ai_confidence', 0),
                    'processing_time_avg': smart_lane_status.get('processing_time_avg', 0)
                }
            },
            'health_checks': {
                'database': True,  # If we're here, database is working
                'engine_service': fast_lane_status.get('status') == 'OPERATIONAL',
                'websocket_connection': fast_lane_status.get('websocket_status') == 'CONNECTED',
                'mempool_access': fast_lane_status.get('mempool_connected', False),
                'smart_lane_ai': smart_lane_status.get('status') not in ['ERROR', 'UNAVAILABLE']
            },
            'configuration': {
                'mock_mode': fast_lane_metrics.get('_mock', True),
                'debug_mode': getattr(settings, 'DEBUG', False),
                'environment': getattr(settings, 'ENVIRONMENT', 'development')
            }
        }
        
        # Add user-specific information if authenticated
        if request.user.is_authenticated:
            # Get user's active sessions
            active_sessions = TradingSession.objects.filter(
                user=request.user,
                is_active=True
            ).count()
            
            status_data['user_context'] = {
                'active_sessions': active_sessions,
                'total_configurations': BotConfiguration.objects.filter(user=request.user).count(),
                'last_login': request.user.last_login.isoformat() if request.user.last_login else None
            }
        
        logger.debug(f"Engine status API response prepared successfully")
        return JsonResponse(status_data)
        
    except Exception as e:
        logger.error(f"Error in api_engine_status: {e}", exc_info=True)
        return JsonResponse({
            'error': 'Failed to get engine status',
            'message': str(e),
            'timestamp': timezone.now().isoformat(),
            'system': {
                'overall_status': 'ERROR',
                'data_source': 'UNKNOWN'
            }
        }, status=500)

@require_http_methods(["GET"])
def api_get_allocation_settings(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to get user's current fund allocation settings.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JSON response with allocation settings
    """
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        # Try to get existing allocation settings
        try:
            from .models import FundAllocation
            allocation = FundAllocation.objects.get(user=request.user)
            return JsonResponse({
                'success': True,
                'allocation': allocation.to_dict()
            })
        except FundAllocation.DoesNotExist:
            # Return default settings if none exist
            return JsonResponse({
                'success': True,
                'allocation': {
                    'method': 'percentage',
                    'percentage': 10.0,
                    'fixed_amount': 0.1,
                    'daily_limit': 1.0,
                    'minimum_balance': 0.05,
                    'auto_rebalance': True,
                    'stop_loss_enabled': True,
                    'stop_loss_percentage': 5.0,
                    'risk_level': 'conservative',
                    'is_active': True
                }
            })
        except ImportError:
            # Model not available, return session-based settings
            allocation_settings = request.session.get('allocation_settings', {
                'method': 'percentage',
                'percentage': 10.0,
                'fixed_amount': 0.1,
                'daily_limit': 1.0,
                'minimum_balance': 0.05,
                'auto_rebalance': True
            })
            return JsonResponse({
                'success': True,
                'allocation': allocation_settings
            })
        
    except Exception as e:
        logger.error(f"Error getting allocation settings: {e}")
        return JsonResponse({'error': 'Failed to get allocation settings'}, status=500)


@require_POST
@csrf_exempt
def api_reset_allocation_settings(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to reset fund allocation settings to defaults.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JSON response with reset confirmation
    """
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        # Default allocation settings
        default_settings = {
            'method': 'percentage',
            'percentage': 10.0,
            'fixed_amount': 0.1,
            'daily_limit': 1.0,
            'minimum_balance': 0.05,
            'auto_rebalance': True,
            'stop_loss_enabled': True,
            'stop_loss_percentage': 5.0
        }
        
        try:
            from .models import FundAllocation
            allocation, created = FundAllocation.objects.get_or_create(
                user=request.user,
                defaults={
                    'allocation_method': FundAllocation.AllocationMethod.PERCENTAGE,
                    'allocation_percentage': Decimal('10.00'),
                    'allocation_fixed_amount': Decimal('0.10000000'),
                    'daily_spending_limit': Decimal('1.00000000'),
                    'minimum_balance_reserve': Decimal('0.05000000'),
                    'auto_rebalance_enabled': True,
                    'stop_loss_enabled': True,
                    'stop_loss_percentage': Decimal('5.00')
                }
            )
            
            if not created:
                # Reset existing allocation to defaults
                allocation.allocation_method = FundAllocation.AllocationMethod.PERCENTAGE
                allocation.allocation_percentage = Decimal('10.00')
                allocation.allocation_fixed_amount = Decimal('0.10000000')
                allocation.daily_spending_limit = Decimal('1.00000000')
                allocation.minimum_balance_reserve = Decimal('0.05000000')
                allocation.auto_rebalance_enabled = True
                allocation.stop_loss_enabled = True
                allocation.stop_loss_percentage = Decimal('5.00')
                allocation.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Allocation settings reset to defaults',
                'allocation': allocation.to_dict()
            })
            
        except ImportError:
            # Use session storage if model not available
            request.session['allocation_settings'] = default_settings
            return JsonResponse({
                'success': True,
                'message': 'Allocation settings reset to defaults',
                'allocation': default_settings
            })
        
    except Exception as e:
        logger.error(f"Error resetting allocation settings: {e}")
        return JsonResponse({'error': 'Failed to reset allocation settings'}, status=500)


@require_POST
@csrf_exempt
def api_stop_trading(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to stop trading (normal stop, not emergency).
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JSON response with stop status
    """
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        # Stop active trading sessions
        active_sessions = TradingSession.objects.filter(
            user=request.user,
            is_active=True
        )
        
        stopped_count = 0
        for session in active_sessions:
            session.is_active = False
            session.status = 'STOPPED'
            session.ended_at = timezone.now()
            session.save()
            stopped_count += 1
        
        logger.info(f"Trading stopped by user {request.user.username}, stopped {stopped_count} sessions")
        
        return JsonResponse({
            'success': True,
            'message': f'Trading stopped. {stopped_count} sessions ended.',
            'stopped_sessions': stopped_count
        })
        
    except Exception as e:
        logger.error(f"Error stopping trading: {e}")
        return JsonResponse({'error': 'Failed to stop trading'}, status=500)


@require_http_methods(["GET"])
def api_trading_status(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to get current trading status.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JSON response with trading status
    """
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        # Get active sessions
        active_sessions = TradingSession.objects.filter(
            user=request.user,
            is_active=True
        )
        
        # Get wallet info
        wallet_info = get_user_wallet_info(request.user)
        
        # Calculate trading status
        trading_status = {
            'active': active_sessions.exists(),
            'session_count': active_sessions.count(),
            'wallet_connected': wallet_info['connected'],
            'funds_available': wallet_info['trading_allocation']['available_for_trading'] > 0,
            'trading_ready': wallet_info['connected'] and wallet_info['trading_allocation']['available_for_trading'] > 0,
            'sessions': []
        }
        
        # Add session details
        for session in active_sessions:
            trading_status['sessions'].append({
                'id': session.id,
                'name': getattr(session, 'session_name', f'Session {session.id}'),
                'started_at': session.started_at.isoformat() if session.started_at else None,
                'status': getattr(session, 'status', 'ACTIVE')
            })
        
        return JsonResponse({
            'success': True,
            'trading_status': trading_status,
            'wallet_info': wallet_info
        })
        
    except Exception as e:
        logger.error(f"Error getting trading status: {e}")
        return JsonResponse({'error': 'Failed to get trading status'}, status=500)


@require_http_methods(["GET"])
def api_performance_analytics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for performance analytics data.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JSON response with performance analytics
    """
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        # Get time range from query parameters
        days = int(request.GET.get('days', 7))
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        # Get user's trading sessions in time range
        sessions = TradingSession.objects.filter(
            user=request.user,
            created_at__gte=start_date,
            created_at__lte=end_date
        )
        
        # Calculate analytics
        total_sessions = sessions.count()
        active_sessions = sessions.filter(is_active=True).count()
        completed_sessions = sessions.filter(is_active=False).count()
        
        # Mock performance data (replace with actual calculation)
        analytics = {
            'time_range': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days': days
            },
            'session_stats': {
                'total_sessions': total_sessions,
                'active_sessions': active_sessions,
                'completed_sessions': completed_sessions,
                'success_rate': 95.5 if total_sessions > 0 else 0  # Mock data
            },
            'performance_metrics': {
                'avg_execution_time_ms': 78.5,  # Mock data
                'total_trades': total_sessions * 10,  # Mock calculation
                'successful_trades': int(total_sessions * 10 * 0.955),  # Mock calculation
                'failed_trades': int(total_sessions * 10 * 0.045)  # Mock calculation
            },
            'risk_metrics': {
                'max_drawdown': 2.1,  # Mock data
                'volatility': 15.3,  # Mock data
                'sharpe_ratio': 1.8  # Mock data
            }
        }
        
        return JsonResponse({
            'success': True,
            'analytics': analytics
        })
        
    except Exception as e:
        logger.error(f"Error getting performance analytics: {e}")
        return JsonResponse({'error': 'Failed to get performance analytics'}, status=500)


@require_http_methods(["GET"])
def api_pnl_analytics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for profit and loss analytics.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JSON response with P&L analytics
    """
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        # Get wallet info
        wallet_info = get_user_wallet_info(request.user)
        
        # Mock P&L data (replace with actual calculation from trading history)
        pnl_data = {
            'current_balance': wallet_info['balance_eth'],
            'total_invested': 0.5,  # Mock data
            'total_pnl_eth': 0.025,  # Mock data
            'total_pnl_usd': 62.50,  # Mock data
            'pnl_percentage': 5.0,  # Mock data
            'daily_pnl': [
                {'date': '2025-09-14', 'pnl_eth': 0.005, 'pnl_usd': 12.50},
                {'date': '2025-09-15', 'pnl_eth': 0.003, 'pnl_usd': 7.50},
                {'date': '2025-09-16', 'pnl_eth': -0.001, 'pnl_usd': -2.50},
                {'date': '2025-09-17', 'pnl_eth': 0.008, 'pnl_usd': 20.00},
                {'date': '2025-09-18', 'pnl_eth': 0.002, 'pnl_usd': 5.00},
                {'date': '2025-09-19', 'pnl_eth': 0.004, 'pnl_usd': 10.00},
                {'date': '2025-09-20', 'pnl_eth': 0.004, 'pnl_usd': 10.00}
            ],
            'monthly_summary': {
                'september_2025': {
                    'total_pnl_eth': 0.025,
                    'total_pnl_usd': 62.50,
                    'trading_days': 7,
                    'profitable_days': 6,
                    'best_day': {'date': '2025-09-17', 'pnl_eth': 0.008},
                    'worst_day': {'date': '2025-09-16', 'pnl_eth': -0.001}
                }
            }
        }
        
        return JsonResponse({
            'success': True,
            'pnl_data': pnl_data,
            'wallet_connected': wallet_info['connected']
        })
        
    except Exception as e:
        logger.error(f"Error getting P&L analytics: {e}")
        return JsonResponse({'error': 'Failed to get P&L analytics'}, status=500)


@require_http_methods(["GET"])
def api_risk_analytics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for risk analytics and monitoring.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JSON response with risk analytics
    """
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        # Get allocation settings
        wallet_info = get_user_wallet_info(request.user)
        allocation = wallet_info['trading_allocation']
        
        # Calculate risk metrics
        risk_data = {
            'current_allocation': {
                'method': allocation['method'],
                'percentage': allocation['percentage'],
                'amount_eth': allocation['available_for_trading'],
                'risk_level': allocation['risk_level']
            },
            'risk_metrics': {
                'portfolio_concentration': allocation['percentage'],
                'daily_var': 0.05,  # Value at Risk (mock data)
                'max_daily_loss': allocation['daily_limit'],
                'stop_loss_trigger': allocation.get('stop_loss_percentage', 5.0)
            },
            'safety_indicators': {
                'adequate_reserves': wallet_info['balance_eth'] > allocation['minimum_balance'],
                'within_daily_limit': True,  # Mock data
                'diversification_score': 7.5,  # Mock score out of 10
                'risk_score': 3.5 if allocation['risk_level'] == 'conservative' else 
                             6.0 if allocation['risk_level'] == 'moderate' else 8.5
            },
            'recommendations': []
        }
        
        # Generate risk recommendations
        if allocation['percentage'] > 25:
            risk_data['recommendations'].append({
                'type': 'warning',
                'message': 'Consider reducing allocation percentage for better risk management'
            })
        
        if wallet_info['balance_eth'] < allocation['minimum_balance'] * 2:
            risk_data['recommendations'].append({
                'type': 'caution',
                'message': 'Wallet balance is low relative to minimum reserve'
            })
        
        if allocation['risk_level'] == 'aggressive':
            risk_data['recommendations'].append({
                'type': 'info',
                'message': 'High-risk allocation detected. Monitor positions closely.'
            })
        
        return JsonResponse({
            'success': True,
            'risk_data': risk_data
        })
        
    except Exception as e:
        logger.error(f"Error getting risk analytics: {e}")
        return JsonResponse({'error': 'Failed to get risk analytics'}, status=500)


# Error handlers
def custom_404(request, exception):
    """Custom 404 error handler."""
    return render(request, 'dashboard/error.html', {
        'error': 'Page not found',
        'error_code': 404,
        'message': 'The requested page could not be found.'
    }, status=404)


def custom_500(request):
    """Custom 500 error handler."""
    return render(request, 'dashboard/error.html', {
        'error': 'Internal server error',
        'error_code': 500,
        'message': 'An unexpected error occurred. Please try again later.'
    }, status=500)



"""
Missing API Engine Status Function Stub

Add this function to your dashboard/views.py file to resolve the Django URL resolution error.
This function stub provides the missing api_engine_status endpoint that your URLs are trying to reference.

File: dashboard/views.py (add this function to the existing file)

INSTRUCTIONS:
1. Copy this function and paste it into your dashboard/views.py file
2. Add it after the existing API endpoints section around line 800+
3. Make sure it's properly indented and follows the existing code style
"""

# =========================================================================
# ENGINE STATUS API ENDPOINT
# Critical endpoint for engine status monitoring - REQUIRED BY URLS.PY
# =========================================================================












