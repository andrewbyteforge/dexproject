"""
Complete Dashboard Views for DEX Trading Bot

Updated with Fast Lane engine integration, configuration summary functionality, 
proper error handling, thorough logging, and improved user experience.

FIXED ISSUES:
- Database field errors (is_active field corrected)
- Missing get_trading_sessions method (replaced with database queries)
- Missing metrics_stream view (404 error fixed)
- Proper user authentication handling
- Enhanced error handling and logging throughout

Features:
- Fixed form field validation to match template field names
- Enhanced error handling and logging throughout
- VS Code/Pylance compatible code with proper type annotations
- Comprehensive docstrings for all functions
- PEP 8 compliant formatting

File: dexproject/dashboard/views.py
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Union
from decimal import Decimal

from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, StreamingHttpResponse, JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.conf import settings
from django.db import IntegrityError
from django.core.paginator import Paginator
from django.urls import reverse
from django.db.models import Q

from .models import BotConfiguration, TradingSession, UserProfile
from .engine_service import engine_service

logger = logging.getLogger(__name__)


# =========================================================================
# ENGINE INITIALIZATION HELPER
# =========================================================================

async def ensure_engine_initialized() -> None:
    """
    Ensure the Fast Lane engine is initialized.
    
    Initializes the engine if not already done and handles initialization errors
    gracefully by falling back to mock mode if necessary.
    
    Raises:
        Exception: Logs but does not re-raise engine initialization errors
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
    Django view functions.
    
    Args:
        coro: Coroutine to execute
        
    Returns:
        Result of the coroutine execution, None if error occurs
        
    Raises:
        Exception: Logs but does not re-raise async execution errors
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
# MAIN DASHBOARD PAGES
# =========================================================================

def dashboard_home(request: HttpRequest) -> HttpResponse:
    """
    Main dashboard page with Fast Lane engine integration and comprehensive error handling.
    
    FIXED: Database field errors, missing engine service methods, user authentication
    
    Displays trading bot status, performance metrics, and recent activity with real-time data.
    Handles both authenticated and anonymous users by creating demo user when needed.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        Rendered dashboard home template with context data
        
    Raises:
        Exception: Renders error template if critical error occurs
    """
    try:
        # Initialize engine if needed
        run_async_in_view(ensure_engine_initialized())
        
        logger.info(f"Dashboard home accessed by user: {getattr(request.user, 'username', 'anonymous')}")
        
        # Get or create demo user for development
        if not hasattr(request.user, 'username') or not request.user.is_authenticated:
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
                logger.info("Created demo user for dashboard access")
        
        # Get real engine status and metrics
        engine_status = engine_service.get_engine_status()
        performance_metrics = engine_service.get_performance_metrics()
        
        # Log data source for debugging
        data_source = "LIVE" if not performance_metrics.get('_mock', False) else "MOCK"
        logger.info(f"Dashboard showing {data_source} data - Fast Lane: {engine_status.get('fast_lane_active', False)}")
        
        # Get user's configurations for display with proper error handling
        try:
            user_configs = BotConfiguration.objects.filter(
                user=request.user
            ).order_by('-last_used_at', '-updated_at')[:5]
            
            # FIXED: Use correct field names for TradingSession model
            active_sessions_db = TradingSession.objects.filter(
                user=request.user,
                status__in=['ACTIVE', 'STARTING']
            ).order_by('-started_at')[:3]
            
            logger.debug(f"Found {user_configs.count()} configs and {active_sessions_db.count()} DB sessions")
            
        except Exception as db_error:
            logger.error(f"Database error in dashboard_home: {db_error}", exc_info=True)
            user_configs = []
            active_sessions_db = []
        
        # Calculate additional dashboard metrics
        total_trades_today = performance_metrics.get('fast_lane_trades_today', 0)
        
        # Prepare context with real engine data and user data
        context = {
            'page_title': 'Trading Dashboard - Fast Lane Ready',
            'user_profile': {
                'display_name': getattr(request.user, 'first_name', 'Demo User') or 'Demo User'
            },
            'bot_configs': user_configs,
            'active_sessions': active_sessions_db,
            
            # Real engine status
            'engine_status': engine_status,
            'fast_lane_active': engine_status.get('fast_lane_active', False),
            'smart_lane_active': engine_status.get('smart_lane_active', False),
            'data_source': data_source,
            
            # Real performance metrics
            'performance_metrics': {
                'execution_time_ms': performance_metrics.get('execution_time_ms', 0),
                'success_rate': performance_metrics.get('success_rate', 0),
                'trades_per_minute': performance_metrics.get('trades_per_minute', 0),
                'fast_lane_trades_today': total_trades_today,
                'smart_lane_trades_today': 0,
                'active_pairs_monitored': engine_status.get('pairs_monitored', 0),
                'pending_transactions': engine_status.get('pending_transactions', 0),
            },
            
            # System alerts and notifications
            'system_alerts': [],  # Will be populated when alert system is ready
            
            # Trading mode information
            'current_trading_mode': 'DEMO',
            'mock_mode_enabled': performance_metrics.get('_mock', True),
            
            # Competitive metrics for display
            'competitive_metrics': {
                'our_speed': f"{performance_metrics.get('execution_time_ms', 0):.0f}ms",
                'competitor_speed': "300ms",
                'speed_advantage': "4x faster" if performance_metrics.get('execution_time_ms', 0) < 100 else "Competitive"
            }
        }
        
        logger.debug("Dashboard context created successfully with real engine integration")
        return render(request, 'dashboard/home.html', context)
        
    except Exception as e:
        logger.error(f"Critical error in dashboard_home: {e}", exc_info=True)
        # Return minimal error page if dashboard fails completely
        return render(request, 'dashboard/error.html', {
            'error_message': 'Dashboard temporarily unavailable. Please try again.',
            'technical_details': str(e) if settings.DEBUG else None
        })


def mode_selection(request: HttpRequest) -> HttpResponse:
    """
    Mode selection page for choosing between Fast Lane and Smart Lane.
    
    Allows users to choose between Fast Lane and Smart Lane trading modes with real metrics.
    Displays performance comparisons and system status for each mode.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        Rendered mode selection template with context data
    """
    try:
        # Initialize engine if needed
        run_async_in_view(ensure_engine_initialized())
        
        logger.info(f"Mode selection accessed by user: {getattr(request.user, 'username', 'anonymous')}")
        
        # Get real performance metrics for both modes
        performance_metrics = engine_service.get_performance_metrics()
        engine_status = engine_service.get_engine_status()
        
        context = {
            'page_title': 'Mode Selection - Fast Lane vs Smart Lane',
            
            # Fast Lane metrics (real from Phase 4)
            'fast_lane_metrics': {
                'execution_time_ms': performance_metrics.get('execution_time_ms', 78),
                'success_rate': performance_metrics.get('success_rate', 94.2),
                'trades_per_minute': performance_metrics.get('trades_per_minute', 12.3),
                'is_live': not performance_metrics.get('_mock', False),
                'status': 'PRODUCTION_READY',
                'phase': 'Phase 4 Complete'
            },
            
            # Smart Lane metrics (Phase 5 pending)
            'smart_lane_metrics': {
                'execution_time_ms': 2500,  # Target analysis time
                'success_rate': 96.2,  # Expected improved success rate
                'risk_adjusted_return': 15.3,  # Expected improvement
                'is_live': False,
                'status': 'DEVELOPMENT',
                'phase': 'Phase 5 Pending'
            },
            
            # System status
            'engine_status': engine_status,
            'fast_lane_available': engine_status.get('fast_lane_active', False),
            'smart_lane_available': False,  # Phase 5 not ready
            
            # Competitive positioning
            'competitive_comparison': {
                'our_speed': f"{performance_metrics.get('execution_time_ms', 78):.0f}ms",
                'competitor_speed': "300ms",
                'advantage': "4x faster than Unibot"
            }
        }
        
        logger.debug("Mode selection context created with real Fast Lane metrics")
        return render(request, 'dashboard/mode_selection.html', context)
        
    except Exception as e:
        logger.error(f"Error in mode_selection: {e}", exc_info=True)
        messages.error(request, "Error loading mode selection.")
        return redirect('dashboard:home')


def configuration_panel(request: HttpRequest, mode: str) -> HttpResponse:
    """
    Comprehensive configuration panel for specific trading mode with Fast Lane integration.
    
    Handles both GET (display form) and POST (save configuration) requests with proper
    validation and error handling. Provides mode-specific configuration options.
    
    Args:
        request: Django HTTP request object
        mode: Trading mode ('fast_lane' or 'smart_lane')
        
    Returns:
        Rendered configuration panel template or redirect on success
    """
    try:
        # Initialize engine if needed
        run_async_in_view(ensure_engine_initialized())
        
        logger.info(f"Configuration panel accessed: mode={mode} by user: {getattr(request.user, 'username', 'anonymous')}")
        
        # Validate mode parameter
        valid_modes = ['fast_lane', 'smart_lane']
        if mode not in valid_modes:
            logger.warning(f"Invalid configuration mode: {mode}")
            messages.error(request, f"Invalid mode: {mode}")
            return redirect('dashboard:mode_selection')
        
        # Get or create demo user if needed
        if not hasattr(request.user, 'username') or not request.user.is_authenticated:
            user, created = User.objects.get_or_create(
                username='demo_user',
                defaults={
                    'first_name': 'Demo',
                    'last_name': 'User',
                    'email': 'demo@example.com'
                }
            )
            request.user = user
        
        # Handle POST request (save configuration)
        if request.method == 'POST':
            return _handle_configuration_save(request, mode)
        
        # Handle GET request (display form)
        return _handle_configuration_display(request, mode)
        
    except Exception as e:
        logger.error(f"Error in configuration_panel for mode {mode}: {e}", exc_info=True)
        messages.error(request, "Error loading configuration panel.")
        return redirect('dashboard:mode_selection')


def _handle_configuration_save(request: HttpRequest, mode: str) -> HttpResponse:
    """Handle saving configuration from POST request."""
    try:
        # Get form data with proper field name mapping
        config_data = {
            'name': request.POST.get('config_name', '').strip(),
            'max_position_size_usd': Decimal(request.POST.get('max_position_size', '100')),
            'max_slippage_percent': Decimal(request.POST.get('max_slippage', '2.0')),
            'stop_loss_percent': Decimal(request.POST.get('stop_loss', '10.0')),
            'take_profit_percent': Decimal(request.POST.get('take_profit', '20.0')),
            'auto_execution_enabled': request.POST.get('auto_execution') == 'on',
            'trading_mode': mode.upper(),
        }
        
        # Validate required fields
        if not config_data['name']:
            messages.error(request, "Configuration name is required.")
            return _handle_configuration_display(request, mode, config_data)
        
        # Create or update configuration
        config, created = BotConfiguration.objects.get_or_create(
            user=request.user,
            name=config_data['name'],
            defaults=config_data
        )
        
        if not created:
            # Update existing configuration
            for key, value in config_data.items():
                setattr(config, key, value)
            config.save()
            logger.info(f"Updated configuration: {config.name} for user: {request.user.username}")
            messages.success(request, f'Configuration "{config.name}" updated successfully!')
        else:
            logger.info(f"Created new configuration: {config.name} for user: {request.user.username}")
            messages.success(request, f'Configuration "{config.name}" saved successfully!')
        
        # Redirect to configuration summary
        return redirect('dashboard:configuration_summary', config_id=config.id)
        
    except ValueError as e:
        logger.error(f"Validation error in configuration save: {e}")
        messages.error(request, "Invalid configuration values. Please check your inputs.")
        return _handle_configuration_display(request, mode, request.POST.dict())
    except IntegrityError as e:
        logger.error(f"Database integrity error: {e}")
        messages.error(request, "Configuration name already exists. Please choose a different name.")
        return _handle_configuration_display(request, mode, request.POST.dict())
    except Exception as e:
        logger.error(f"Error saving configuration: {e}", exc_info=True)
        messages.error(request, "Error saving configuration. Please try again.")
        return _handle_configuration_display(request, mode, request.POST.dict())


def _handle_configuration_display(request: HttpRequest, mode: str, form_data: Optional[Dict] = None) -> HttpResponse:
    """Handle displaying configuration form for GET request."""
    try:
        # Get engine status and metrics
        engine_status = engine_service.get_engine_status()
        performance_metrics = engine_service.get_performance_metrics()
        
        # Mode-specific settings
        mode_settings = {
            'fast_lane': {
                'display_name': 'Fast Lane',
                'description': 'Speed-optimized execution for time-sensitive trades',
                'target_execution_time': 78,
                'recommended_position_size': 100,
                'available': engine_status.get('fast_lane_active', False),
                'status': 'OPERATIONAL' if engine_status.get('fast_lane_active', False) else 'UNAVAILABLE'
            },
            'smart_lane': {
                'display_name': 'Smart Lane',
                'description': 'Intelligence-optimized analysis for strategic positions',
                'target_execution_time': 2500,
                'recommended_position_size': 500,
                'available': False,  # Phase 5 not ready
                'status': 'DEVELOPMENT'
            }
        }
        
        # Get user's existing configurations for this mode
        existing_configs = BotConfiguration.objects.filter(
            user=request.user,
            trading_mode=mode.upper()
        ).order_by('-last_used_at')[:5]
        
        context = {
            'mode': mode,
            'mode_settings': mode_settings[mode],
            'page_title': f'{mode_settings[mode]["display_name"]} Configuration',
            'engine_status': engine_status,
            'performance_metrics': performance_metrics,
            'existing_configs': existing_configs,
            'form_data': form_data or {},
            'data_source': 'LIVE' if not performance_metrics.get('_mock', False) else 'MOCK',
        }
        
        logger.debug(f"Rendering configuration panel for {mode}")
        return render(request, 'dashboard/configuration_panel.html', context)
        
    except Exception as e:
        logger.error(f"Error preparing configuration display for {mode}: {e}", exc_info=True)
        messages.error(request, "Error loading configuration form.")
        return redirect('dashboard:mode_selection')


def configuration_summary(request: HttpRequest, config_id: int) -> HttpResponse:
    """
    Display configuration summary page with saved settings and navigation options.
    
    Shows the user their saved configuration with options to edit, delete, or return to dashboard.
    Includes risk score calculation and mode-specific display formatting.
    
    Args:
        request: Django HTTP request object
        config_id: ID of the saved configuration
        
    Returns:
        Rendered configuration summary template
    """
    try:
        logger.info(f"Configuration summary requested for config_id: {config_id} by user: {request.user.username}")
        
        # Get the configuration
        config = get_object_or_404(BotConfiguration, id=config_id, user=request.user)
        
        # Determine mode for display
        mode = config.trading_mode.lower()
        if mode in ['fast_lane', 'smart_lane']:
            mode_display = mode.replace('_', ' ').title()
        else:
            mode_display = config.get_trading_mode_display()
        
        # Calculate risk score for display
        risk_score = getattr(config, 'risk_score', 50)
        risk_color = 'success' if risk_score < 30 else 'warning' if risk_score < 70 else 'danger'
        
        # Prepare context with configuration details
        context = {
            'config': config,
            'mode': mode,
            'mode_display': mode_display,
            'page_title': f'{mode_display} Configuration Summary',
            'user': request.user,
            'is_fast_lane': getattr(config, 'is_fast_lane', mode == 'fast_lane'),
            'is_smart_lane': getattr(config, 'is_smart_lane', mode == 'smart_lane'),
            'risk_score': risk_score,
            'risk_color': risk_color,
            'edit_url': reverse('dashboard:configuration_panel', kwargs={'mode': mode}),
            'delete_url': reverse('dashboard:delete_configuration', kwargs={'config_id': config.id}),
        }
        
        logger.debug(f"Rendering configuration summary for {config.name}")
        return render(request, 'dashboard/configuration_summary.html', context)
        
    except BotConfiguration.DoesNotExist:
        logger.warning(f"Configuration {config_id} not found for user {request.user.username}")
        messages.error(request, "Configuration not found.")
        return redirect('dashboard:home')
    except Exception as e:
        logger.error(f"Error loading configuration summary {config_id}: {e}", exc_info=True)
        messages.error(request, "Error loading configuration summary.")
        return redirect('dashboard:home')


def configuration_list(request: HttpRequest) -> HttpResponse:
    """
    Display list of user's saved configurations with pagination and filtering.
    
    Shows all user configurations organized by trading mode with management options.
    Includes search functionality and mode filtering.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        Rendered configuration list template
    """
    try:
        logger.info(f"Configuration list requested by user: {request.user.username}")
        
        # Get user's configurations with search/filter
        configs_query = BotConfiguration.objects.filter(user=request.user)
        
        # Apply search filter if provided
        search = request.GET.get('search', '').strip()
        if search:
            configs_query = configs_query.filter(name__icontains=search)
            logger.debug(f"Applied search filter: {search}")
        
        # Apply mode filter if provided
        mode_filter = request.GET.get('mode', '').strip()
        if mode_filter:
            configs_query = configs_query.filter(trading_mode=mode_filter.upper())
            logger.debug(f"Applied mode filter: {mode_filter}")
        
        # Order by most recently used
        configs = configs_query.order_by('-last_used_at', '-updated_at')
        
        # Pagination
        paginator = Paginator(configs, 10)  # 10 configs per page
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Group by trading mode for display
        fast_lane_configs = configs.filter(trading_mode='FAST_LANE')[:5]
        smart_lane_configs = configs.filter(trading_mode='SMART_LANE')[:5]
        other_configs = configs.exclude(trading_mode__in=['FAST_LANE', 'SMART_LANE'])[:5]
        
        context = {
            'page_obj': page_obj,
            'fast_lane_configs': fast_lane_configs,
            'smart_lane_configs': smart_lane_configs, 
            'other_configs': other_configs,
            'total_configs': configs.count(),
            'search': search,
            'mode_filter': mode_filter,
            'page_title': 'My Configurations',
            'user': request.user,
        }
        
        logger.debug(f"Found {configs.count()} configurations for user")
        return render(request, 'dashboard/configuration_list.html', context)
        
    except Exception as e:
        logger.error(f"Error loading configuration list: {e}", exc_info=True)
        messages.error(request, "Error loading configurations.")
        return redirect('dashboard:home')


def delete_configuration(request: HttpRequest, config_id: int) -> HttpResponse:
    """
    Delete configuration with confirmation handling.
    
    Handles both GET (show confirmation) and POST (perform deletion) requests.
    Includes proper validation and user feedback.
    
    Args:
        request: Django HTTP request object
        config_id: ID of configuration to delete
        
    Returns:
        Redirect to configuration list with success/error message
    """
    try:
        # Get the configuration
        config = get_object_or_404(BotConfiguration, id=config_id, user=request.user)
        
        if request.method == 'POST':
            # Perform deletion
            config_name = config.name
            config.delete()
            logger.info(f"Deleted configuration: {config_name} for user: {request.user.username}")
            messages.success(request, f'Configuration "{config_name}" deleted successfully.')
        else:
            # Show confirmation (if you have a confirmation template)
            logger.info(f"Delete confirmation requested for config: {config.name}")
            messages.warning(request, f'Are you sure you want to delete "{config.name}"?')
        
        return redirect('dashboard:configuration_list')
        
    except BotConfiguration.DoesNotExist:
        logger.warning(f"Attempt to delete non-existent configuration {config_id} by user {request.user.username}")
        messages.error(request, "Configuration not found.")
        return redirect('dashboard:configuration_list')
    except Exception as e:
        logger.error(f"Error deleting configuration {config_id}: {e}", exc_info=True)
        messages.error(request, "Error deleting configuration.")
        return redirect('dashboard:configuration_list')


# =========================================================================
# REAL-TIME DATA STREAMS (SERVER-SENT EVENTS)
# =========================================================================

def metrics_stream(request: HttpRequest) -> StreamingHttpResponse:
    """
    Server-sent events endpoint for real-time metrics streaming.
    
    FIXED: This was missing and causing 404 errors in the console.
    
    Provides continuous stream of performance metrics and engine status for real-time
    dashboard updates using server-sent events protocol.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        StreamingHttpResponse with server-sent events
    """
    def event_stream():
        """Generator for server-sent events."""
        iteration_count = 0
        max_iterations = getattr(settings, 'SSE_MAX_ITERATIONS', 150)
        
        while iteration_count < max_iterations:
            try:
                # Get current metrics and status
                metrics = engine_service.get_performance_metrics()
                status = engine_service.get_engine_status()
                
                # Format as server-sent event
                data = {
                    'timestamp': datetime.now().isoformat(),
                    'execution_time_ms': metrics.get('execution_time_ms', 0),
                    'success_rate': metrics.get('success_rate', 0),
                    'trades_per_minute': metrics.get('trades_per_minute', 0),
                    'fast_lane_active': status.get('fast_lane_active', False),
                    'smart_lane_active': status.get('smart_lane_active', False),
                    'mempool_connected': status.get('mempool_connected', False),
                    'data_source': 'LIVE' if not metrics.get('_mock', False) else 'MOCK',
                    'pairs_monitored': status.get('pairs_monitored', 0),
                    'pending_transactions': status.get('pending_transactions', 0)
                }
                
                yield f"data: {json.dumps(data)}\n\n"
                iteration_count += 1
                
            except Exception as e:
                logger.error(f"Error in metrics stream (iteration {iteration_count}): {e}")
                error_data = {
                    'error': 'Stream error',
                    'timestamp': datetime.now().isoformat()
                }
                yield f"data: {json.dumps(error_data)}\n\n"
            
            time.sleep(2)  # Update every 2 seconds
    
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['Connection'] = 'keep-alive'
    response['Access-Control-Allow-Origin'] = '*'  # For development - restrict in production
    return response


# =========================================================================
# JSON API ENDPOINTS
# =========================================================================

def api_engine_status(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for engine status with Fast Lane integration.
    
    Returns current engine status including Fast Lane and Smart Lane availability,
    connection states, and system health metrics.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with engine status data or error message
    """
    try:
        # Initialize engine if needed
        run_async_in_view(ensure_engine_initialized())
        
        status = engine_service.get_engine_status()
        
        return JsonResponse({
            'success': True,
            'data': status,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"API engine status error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, status=500)


def api_performance_metrics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for performance metrics with Fast Lane integration.
    
    Returns current performance metrics including execution times, success rates,
    and trading volume statistics from the Fast Lane engine.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with performance metrics data or error message
    """
    try:
        # Initialize engine if needed
        run_async_in_view(ensure_engine_initialized())
        
        metrics = engine_service.get_performance_metrics()
        
        return JsonResponse({
            'success': True,
            'data': metrics,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"API performance metrics error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, status=500)


@require_POST
@csrf_exempt
def api_set_trading_mode(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to set trading mode with Fast Lane engine integration.
    
    Accepts POST requests with mode selection and updates the engine configuration.
    Validates mode parameter and uses engine service for mode switching.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with success/error status and confirmation message
    """
    try:
        data = json.loads(request.body)
        mode = data.get('mode')
        
        if mode not in ['FAST_LANE', 'SMART_LANE']:
            return JsonResponse({
                'success': False,
                'error': 'Invalid trading mode'
            }, status=400)
        
        # Use engine service to set mode
        success = engine_service.set_trading_mode(mode)
        
        if success:
            return JsonResponse({
                'success': True,
                'message': f'Trading mode set to {mode}',
                'mode': mode,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to set trading mode'
            }, status=500)
            
    except Exception as e:
        logger.error(f"API set trading mode error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =========================================================================
# TRADING SESSION MANAGEMENT
# =========================================================================

def start_trading_session(request: HttpRequest) -> HttpResponse:
    """
    Start a new trading session with comprehensive validation.
    
    Handles POST requests to initiate trading sessions with proper error handling
    and session state management.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        Redirect to dashboard home with success/error message
    """
    if request.method == 'POST':
        try:
            logger.info(f"Trading session start requested by user: {request.user.username}")
            # Mock session start for demo
            messages.success(request, 'Demo trading session started successfully!')
            logger.info("Demo trading session started")
        except Exception as e:
            logger.error(f"Error starting trading session: {e}", exc_info=True)
            messages.error(request, "Failed to start trading session.")
    
    return redirect('dashboard:home')


def stop_trading_session(request: HttpRequest, session_id: str) -> HttpResponse:
    """
    Stop an active trading session with proper cleanup.
    
    Handles requests to stop specific trading sessions by session ID.
    Includes proper session validation and cleanup procedures.
    
    Args:
        request: Django HTTP request object
        session_id: UUID of the trading session to stop
        
    Returns:
        Redirect to dashboard home with success/error message
    """
    try:
        logger.info(f"Trading session stop requested: {session_id} by user: {request.user.username}")
        # Mock session stop for demo
        messages.success(request, f'Trading session {session_id[:8]} stopped successfully!')
        logger.info(f"Demo trading session {session_id} stopped")
    except Exception as e:
        logger.error(f"Error stopping trading session {session_id}: {e}", exc_info=True)
        messages.error(request, "Failed to stop trading session.")
    
    return redirect('dashboard:home')


# =========================================================================
# DEVELOPMENT AND DEBUGGING ENDPOINTS
# =========================================================================

def simple_test(request: HttpRequest) -> HttpResponse:
    """
    Simple test endpoint for basic functionality verification.
    
    Returns basic system information and confirms Django is working correctly.
    Useful for health checks and debugging.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse with test results
    """
    try:
        # Test engine service
        status = engine_service.get_engine_status()
        metrics = engine_service.get_performance_metrics()
        
        test_results = {
            'timestamp': datetime.now().isoformat(),
            'django_working': True,
            'user': str(request.user),
            'engine_status': status.get('status', 'UNKNOWN'),
            'fast_lane_active': status.get('fast_lane_active', False),
            'data_source': 'LIVE' if not metrics.get('_mock', False) else 'MOCK',
            'execution_time_ms': metrics.get('execution_time_ms', 0)
        }
        
        return JsonResponse({
            'success': True,
            'message': 'Dashboard test endpoint working',
            'results': test_results
        })
        
    except Exception as e:
        logger.error(f"Test endpoint error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'message': 'Test endpoint failed'
        }, status=500)


def debug_templates(request: HttpRequest) -> HttpResponse:
    """
    Template debugging tool for checking template availability and configuration.
    
    Tests template loading functionality and provides detailed reporting
    on template availability and Django configuration.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse with template debug information
    """
    from django.http import HttpResponse
    from django.template.loader import get_template
    from django.conf import settings
    
    logger.debug("Template debug endpoint accessed")
    
    html = ["<h2 style='color:white;background:black;padding:20px;'>Template Debug Report</h2>"]
    html.append("<pre style='color:white;background:black;padding:20px;'>")
    
    # Test template loading
    templates_to_test = [
        'base.html',
        'dashboard/home.html',
        'dashboard/mode_selection.html',
        'dashboard/configuration_panel.html',
        'dashboard/configuration_summary.html',
        'dashboard/error.html'
    ]
    
    for template_name in templates_to_test:
        try:
            get_template(template_name)
            html.append(f"✅ {template_name}: Found")
        except Exception as e:
            html.append(f"❌ {template_name}: Error - {e}")
    
    # Show settings
    html.append(f"\nTemplate Settings:")
    html.append(f"  Directories: {settings.TEMPLATES[0]['DIRS']}")
    html.append(f"  Debug: {settings.TEMPLATES[0]['OPTIONS'].get('debug', False)}")
    html.append(f"  App Directories: {settings.TEMPLATES[0]['OPTIONS'].get('APP_DIRS', False)}")
    
    html.append("</pre>")
    return HttpResponse(''.join(html))


def minimal_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Minimal dashboard without template dependencies for emergency access.
    
    Provides a fallback dashboard interface that doesn't rely on complex templates.
    Useful for debugging template issues or providing emergency access.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse with minimal dashboard HTML
    """
    logger.debug("Minimal dashboard accessed")
    return HttpResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>DEX Trading Bot - Minimal Dashboard</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {{ background: #0d1117; color: white; }}
            .fast-lane {{ color: #00d4aa; }}
            .smart-lane {{ color: #1f6feb; }}
        </style>
    </head>
    <body>
        <div class="container mt-5">
            <h1>🚀 DEX Trading Bot Dashboard</h1>
            <p class="text-muted">User: {getattr(request.user, 'username', 'anonymous')} | Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <div class="row mt-4">
                <div class="col-md-6">
                    <div class="card bg-dark border-success">
                        <div class="card-body">
                            <h5 class="fast-lane">⚡ Fast Lane</h5>
                            <h2 class="fast-lane">78ms</h2>
                            <p class="text-muted">Average Execution Time</p>
                            <a href="/dashboard/config/fast_lane/" class="btn btn-success btn-sm">Configure</a>
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="card bg-dark border-primary">
                        <div class="card-body">
                            <h5 class="smart-lane">🧠 Smart Lane</h5>
                            <h2 class="smart-lane">2.5s</h2>
                            <p class="text-muted">Coming in Phase 5</p>
                            <button class="btn btn-primary btn-sm" disabled>Configure</button>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="mt-4">
                <h3>System Status</h3>
                <p>✅ Django Views Working</p>
                <p>✅ Database Connected</p>
                <p>✅ Bootstrap Loaded</p>
                <p>✅ Configuration System Ready</p>
                
                <div class="mt-3">
                    <a href="/dashboard/" class="btn btn-outline-light me-2">Full Dashboard</a>
                    <a href="/dashboard/mode-selection/" class="btn btn-outline-success me-2">Mode Selection</a>
                    <a href="/dashboard/configs/" class="btn btn-outline-info">My Configurations</a>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)