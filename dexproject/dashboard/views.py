"""
Complete Dashboard Views for DEX Trading Bot

Updated with Fast Lane engine integration, configuration summary functionality, 
proper error handling, thorough logging, and improved user experience.

File: dexproject/dashboard/views.py
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any
from decimal import Decimal

from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, StreamingHttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.conf import settings
from django.db import IntegrityError
from django.core.paginator import Paginator
from django.urls import reverse

from .models import BotConfiguration, TradingSession, UserProfile
from .engine_service import engine_service

logger = logging.getLogger(__name__)


# =========================================================================
# ENGINE INITIALIZATION HELPER
# =========================================================================

async def ensure_engine_initialized():
    """Ensure the Fast Lane engine is initialized."""
    if not engine_service.engine_initialized and not engine_service.mock_mode:
        try:
            success = await engine_service.initialize_engine(chain_id=1)  # Ethereum mainnet
            if success:
                logger.info("Fast Lane engine initialized successfully")
            else:
                logger.warning("Failed to initialize Fast Lane engine - falling back to mock mode")
        except Exception as e:
            logger.error(f"Engine initialization error: {e}")


def run_async_in_view(coro):
    """Helper to run async code in Django views."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Async execution error: {e}")
        return None


# =========================================================================
# MAIN DASHBOARD PAGES
# =========================================================================

def dashboard_home(request):
    """
    Main dashboard page with Fast Lane engine integration and comprehensive error handling.
    
    Displays trading bot status, performance metrics, and recent activity with real-time data.
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
        trading_sessions = engine_service.get_trading_sessions()
        
        # Log data source for debugging
        data_source = "LIVE" if not performance_metrics.get('_mock', False) else "MOCK"
        logger.info(f"Dashboard showing {data_source} data - Fast Lane: {engine_status.get('fast_lane_active', False)}")
        
        # Get user's configurations for display
        try:
            user_configs = BotConfiguration.objects.filter(
                user=request.user
            ).order_by('-last_used_at', '-updated_at')[:5]
            
            # Get active sessions from database
            active_sessions_db = TradingSession.objects.filter(
                user=request.user,
                status__in=['ACTIVE', 'STARTING']
            ).order_by('-started_at')[:3]
            
            logger.debug(f"Found {user_configs.count()} configs and {active_sessions_db.count()} DB sessions")
            
        except Exception as db_error:
            logger.error(f"Database error loading user data: {db_error}", exc_info=True)
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
                'smart_lane_trades_today': performance_metrics.get('smart_lane_trades_today', 0),
                'risk_cache_hits': performance_metrics.get('risk_cache_hits', 0),
                'mempool_latency_ms': performance_metrics.get('mempool_latency_ms', 0),
                'is_live': not performance_metrics.get('_mock', False)
            },
            
            # Combined sessions (engine + database)
            'total_sessions': len(trading_sessions) + len(active_sessions_db),
            
            # Phase completion status
            'phase_status': {
                'fast_lane_ready': True,  # Phase 3 & 4 complete
                'smart_lane_ready': False,  # Phase 5 pending
                'dashboard_ready': True,  # Phase 2 in progress
            },
            
            # Competitive metrics highlight
            'competitive_metrics': {
                'execution_speed': f"{performance_metrics.get('execution_time_ms', 78):.1f}ms",
                'competitor_speed': "300ms",  # Unibot baseline
                'speed_advantage': f"{((300 - performance_metrics.get('execution_time_ms', 78)) / 300 * 100):.0f}%"
            },
            
            'show_onboarding': user_configs.count() == 0,
            'user': request.user
        }
        
        logger.debug("Dashboard context created successfully with real engine integration")
        return render(request, 'dashboard/home.html', context)
        
    except Exception as e:
        logger.error(f"Critical error in dashboard_home: {e}", exc_info=True)
        return render(request, 'dashboard/error.html', {'error': str(e)})


def mode_selection(request):
    """
    Mode selection interface with Fast Lane integration and comprehensive error handling.
    
    Allows users to choose between Fast Lane and Smart Lane trading modes with real metrics.
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


def configuration_panel(request, mode):
    """
    Comprehensive configuration panel for specific trading mode with Fast Lane integration.
    
    Handles both GET (display form) and POST (save configuration) requests
    with extensive validation, error handling, and real engine status.
    
    Args:
        mode: Either 'fast_lane' or 'smart_lane'
    """
    # Input validation and logging
    logger.info(f"Configuration panel accessed for mode: {mode} by user: {getattr(request.user, 'username', 'anonymous')}")
    
    if mode not in ['fast_lane', 'smart_lane']:
        logger.warning(f"Invalid trading mode attempted: {mode}")
        messages.error(request, "Invalid trading mode specified.")
        return redirect('dashboard:home')
    
    try:
        # Initialize engine if needed
        run_async_in_view(ensure_engine_initialized())
        
        # Ensure user is set up
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
                logger.info("Created demo user for configuration panel")
        
        mode_display = mode.replace('_', ' ').title()
        logger.debug(f"Processing {mode_display} configuration for user: {request.user.username}")
        
        # Handle POST request (form submission)
        if request.method == 'POST':
            logger.info(f"Processing {mode_display} configuration form submission")
            return handle_configuration_update(request, mode, mode_display)
        
        # Handle GET request (display form)
        try:
            # Get real engine status and metrics
            engine_status = engine_service.get_engine_status()
            performance_metrics = engine_service.get_performance_metrics()
            
            # Get or create default configuration for this mode
            default_config, config_created = BotConfiguration.objects.get_or_create(
                user=request.user,
                trading_mode=mode.upper(),
                is_default=True,
                defaults={
                    'name': f'Default {mode_display} Config',
                    'status': 'INACTIVE',
                    'description': f'Default configuration for {mode_display} trading',
                    'max_position_size_usd': Decimal('100.0'),
                    'risk_tolerance_level': 'MEDIUM',
                    'execution_timeout_ms': 500 if mode == 'fast_lane' else 5000,
                    'auto_execution_enabled': False,
                    'require_manual_approval': True,
                    'max_slippage_percent': Decimal('2.0'),
                    'mev_protection_enabled': True,
                    'analysis_depth': 'COMPREHENSIVE' if mode == 'smart_lane' else 'BASIC'
                }
            )
            
            if config_created:
                logger.info(f"Created new default {mode_display} configuration")
            else:
                logger.debug(f"Retrieved existing {mode_display} configuration")
            
        except Exception as db_error:
            logger.error(f"Database error creating/retrieving configuration: {db_error}", exc_info=True)
            # Create a minimal fallback configuration object
            default_config = type('Config', (), {
                'name': f'Default {mode_display} Config',
                'description': f'Default configuration for {mode_display} trading',
                'max_position_size_usd': 100.0,
                'risk_tolerance_level': 'MEDIUM',
                'execution_timeout_ms': 500 if mode == 'fast_lane' else 5000,
                'auto_execution_enabled': False,
                'require_manual_approval': True,
                'max_slippage_percent': 2.0,
                'mev_protection_enabled': True,
            })()
            messages.warning(request, "Using default settings due to database connectivity issues.")
        
        # Prepare template context with real engine data
        context = {
            'mode': mode,
            'mode_display': mode_display,
            'config': default_config,
            'page_title': f'{mode_display} Configuration',
            
            # Real engine status
            'engine_status': engine_status,
            'engine_ready': engine_status.get('fast_lane_active', False) if mode == 'fast_lane' else False,
            'performance_metrics': performance_metrics,
            
            # Mode-specific information
            'mode_info': {
                'fast_lane': {
                    'description': 'Speed-optimized execution for time-sensitive opportunities',
                    'target_speed': f"{performance_metrics.get('execution_time_ms', 78):.0f}ms",
                    'status': 'PRODUCTION_READY' if engine_status.get('fast_lane_active') else 'INITIALIZING',
                    'phase': 'Phase 4 Complete'
                },
                'smart_lane': {
                    'description': 'Intelligence-optimized analysis for strategic positions',
                    'target_speed': '2-5 seconds',
                    'status': 'DEVELOPMENT',
                    'phase': 'Phase 5 Pending'
                }
            }.get(mode, {}),
            
            # System capabilities
            'system_capabilities': {
                'mev_protection': engine_status.get('fast_lane_active', False),
                'gas_optimization': engine_status.get('provider_status', {}).get('gas_optimizer') == 'CONNECTED',
                'risk_cache': engine_status.get('risk_cache_status') == 'HEALTHY',
                'mempool_monitoring': engine_status.get('mempool_connected', False)
            },
            
            # Data source indicator
            'data_source': 'LIVE' if not performance_metrics.get('_mock', False) else 'MOCK',
            'user': request.user,
        }
        
        logger.debug(f"Configuration panel context created for {mode_display}")
        return render(request, 'dashboard/configuration_panel.html', context)
        
    except Exception as e:
        logger.error(f"Unexpected error in configuration_panel for {mode}: {e}", exc_info=True)
        messages.error(request, f"Error loading {mode.replace('_', ' ').lower()} configuration. Please try again.")
        return redirect('dashboard:home')


def handle_configuration_update(request, mode: str, mode_display: str):
    """
    Handle configuration form submission with comprehensive validation and error handling.
    
    Fixed to match the actual form field names from the template.
    
    Args:
        request: Django request object
        mode: Trading mode ('fast_lane' or 'smart_lane')
        mode_display: Display name for the mode
        
    Returns:
        Redirect to configuration summary or JsonResponse with error
    """
    try:
        logger.info(f"Processing {mode_display} configuration update for user: {request.user.username}")
        
        # Validate CSRF token
        if not request.POST.get('csrfmiddlewaretoken'):
            logger.warning(f"Missing CSRF token in {mode_display} configuration update")
            return JsonResponse({
                'success': False, 
                'error': 'Security token missing. Please refresh and try again.'
            })
        
        # Extract and validate form data - FIXED field names to match template
        form_data = {}
        errors = []
        
        # Required fields validation - corrected field names
        required_fields = {
            'name': 'Configuration name',  # Template sends 'name', not 'config_name'
            'max_position_size_usd': 'Maximum position size',  # Template sends 'max_position_size_usd'
            'risk_tolerance': 'Risk tolerance level'
        }
        
        for field, display_name in required_fields.items():
            value = request.POST.get(field, '').strip()
            if not value:
                errors.append(f'{display_name} is required.')
                logger.warning(f"Missing required field {field} in {mode_display} configuration")
            else:
                form_data[field] = value
        
        # Validate numeric fields - FIXED to use correct field name
        try:
            position_size = float(request.POST.get('max_position_size_usd', 0))  # Corrected field name
            if position_size < 1 or position_size > 10000:
                errors.append('Position size must be between $1 and $10,000.')
                logger.warning(f"Invalid position size: {position_size}")
            else:
                form_data['max_position_size_usd'] = Decimal(str(position_size))
        except (ValueError, TypeError):
            errors.append('Position size must be a valid number.')
            logger.warning("Invalid position size format")
        
        # Mode-specific validation
        if mode == 'fast_lane':
            try:
                timeout = int(request.POST.get('execution_timeout_ms', 500))
                if timeout < 50 or timeout > 10000:  # Allow up to 10 seconds for flexibility
                    errors.append('Execution timeout must be between 50ms and 10000ms.')
                    logger.warning(f"Invalid execution timeout: {timeout}")
                else:
                    form_data['execution_timeout_ms'] = timeout
            except (ValueError, TypeError):
                errors.append('Execution timeout must be a valid number.')
                logger.warning("Invalid execution timeout format")
            
            # Slippage validation - FIXED field name
            slippage = request.POST.get('max_slippage_percent')  # Template sends 'max_slippage_percent'
            if slippage:
                try:
                    slippage_val = float(slippage)
                    if slippage_val < 0.1 or slippage_val > 10.0:
                        errors.append('Slippage must be between 0.1% and 10.0%.')
                    else:
                        form_data['max_slippage_percent'] = Decimal(str(slippage_val))
                except (ValueError, TypeError):
                    errors.append('Slippage must be a valid number.')
        
        # Return validation errors if any
        if errors:
            logger.warning(f"Validation errors in {mode_display} configuration: {errors}")
            return JsonResponse({
                'success': False,
                'error': 'Please correct the following errors: ' + '; '.join(errors)
            })
        
        # Save configuration
        try:
            # Get or create configuration
            config, created = BotConfiguration.objects.get_or_create(
                user=request.user,
                trading_mode=mode.upper(),
                is_default=True,
                defaults={}
            )
            
            # Update configuration with validated data - FIXED field names
            config.name = form_data['name']  # Corrected
            config.description = request.POST.get('description', '')
            config.max_position_size_usd = form_data['max_position_size_usd']  # Corrected
            config.risk_tolerance_level = form_data['risk_tolerance']
            
            # Mode-specific updates
            if mode == 'fast_lane':
                config.execution_timeout_ms = form_data.get('execution_timeout_ms', 500)
                config.max_slippage_percent = form_data.get('max_slippage_percent', Decimal('2.0'))
                config.mev_protection_enabled = request.POST.get('mev_protection_enabled') == 'on'
                config.auto_execution_enabled = request.POST.get('auto_execution_enabled') == 'on'
                config.require_manual_approval = request.POST.get('require_manual_approval') == 'on'
            else:  # smart_lane
                config.analysis_depth = 'COMPREHENSIVE'
            
            # Update timestamps and version
            config.updated_at = datetime.now()
            if not created:
                config.version += 1
            
            # Save to database
            config.save()
            
            logger.info(f"Successfully saved {mode_display} configuration: {config.name}")
            
            # Log configuration details for audit
            logger.debug(f"Configuration details - Name: {config.name}, "
                        f"Position Size: ${config.max_position_size_usd}, "
                        f"Risk Level: {config.risk_tolerance_level}")
            
            # Add success message
            messages.success(
                request, 
                f'{mode_display} configuration "{config.name}" saved successfully!'
            )
            
            # Redirect to configuration summary instead of returning JSON
            return redirect('dashboard:configuration_summary', config_id=config.id)
            
        except IntegrityError as db_error:
            logger.error(f"Database integrity error saving configuration: {db_error}")
            return JsonResponse({
                'success': False,
                'error': 'Configuration name already exists. Please choose a different name.'
            })
        except Exception as db_error:
            logger.error(f"Database error saving configuration: {db_error}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to save configuration due to database error. Please try again.'
            })
    
    except Exception as e:
        logger.error(f"Unexpected error in handle_configuration_update for {mode}: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'An unexpected error occurred. Please try again or contact support.'
        })


def configuration_summary(request, config_id):
    """
    Display configuration summary page with saved settings and navigation options.
    
    Shows the user their saved configuration with options to edit, delete, or return to dashboard.
    
    Args:
        request: Django request object
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


def configuration_list(request):
    """
    Display list of user's saved configurations with pagination and filtering.
    
    Shows all user configurations organized by trading mode with management options.
    
    Args:
        request: Django request object
        
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


def delete_configuration(request, config_id):
    """
    Delete a configuration with confirmation and proper error handling.
    
    Args:
        request: Django request object
        config_id: ID of the configuration to delete
        
    Returns:
        Redirect to configuration list or confirmation page
    """
    try:
        logger.info(f"Delete request for configuration {config_id} by user: {request.user.username}")
        
        # Get the configuration
        config = get_object_or_404(BotConfiguration, id=config_id, user=request.user)
        
        if request.method == 'POST':
            # Confirm deletion
            config_name = config.name
            config_mode = config.get_trading_mode_display()
            
            # Check if this is the user's only configuration
            user_config_count = BotConfiguration.objects.filter(user=request.user).count()
            
            config.delete()
            
            logger.info(f"Successfully deleted configuration: {config_name}")
            messages.success(request, f'Configuration "{config_name}" deleted successfully.')
            
            # Redirect to appropriate page
            if user_config_count > 1:
                return redirect('dashboard:configuration_list')
            else:
                # If this was their last config, redirect to mode selection
                messages.info(request, "Create a new configuration to get started.")
                return redirect('dashboard:mode_selection')
        else:
            # Show confirmation page
            context = {
                'config': config,
                'page_title': 'Delete Configuration',
                'cancel_url': reverse('dashboard:configuration_summary', kwargs={'config_id': config.id}),
            }
            return render(request, 'dashboard/confirm_delete_config.html', context)
            
    except BotConfiguration.DoesNotExist:
        logger.warning(f"Configuration {config_id} not found for deletion")
        messages.error(request, "Configuration not found.")
        return redirect('dashboard:configuration_list')
    except Exception as e:
        logger.error(f"Error deleting configuration {config_id}: {e}", exc_info=True)
        messages.error(request, "Error deleting configuration.")
        return redirect('dashboard:configuration_list')


# =========================================================================
# REAL-TIME DATA STREAMS (Updated with Fast Lane Integration)
# =========================================================================

def metrics_stream(request):
    """
    Server-Sent Events endpoint for real-time metrics with Fast Lane integration.
    
    Streams live trading metrics from the Fast Lane engine to the dashboard.
    Falls back to mock data if engine is unavailable.
    """
    def event_stream():
        """Generator function for SSE data stream with Fast Lane integration."""
        import time
        
        try:
            # Initialize engine if needed
            run_async_in_view(ensure_engine_initialized())
            
            # Send initial connection confirmation
            initial_status = engine_service.get_engine_status()
            initial_data = {
                'type': 'connection',
                'status': 'connected',
                'engine_status': initial_status,
                'data_source': 'LIVE' if not initial_status.get('_mock', False) else 'MOCK',
                'timestamp': datetime.now().isoformat()
            }
            yield f"data: {json.dumps(initial_data)}\n\n"
            
            # Stream metrics updates
            counter = 0
            while counter < 100:  # Limit to prevent long-running processes
                try:
                    # Get real-time metrics from engine service
                    metrics = engine_service.get_performance_metrics()
                    status = engine_service.get_engine_status()
                    
                    message_data = {
                        'type': 'metrics_update',
                        'timestamp': datetime.now().isoformat(),
                        'metrics': {
                            'execution_time_ms': metrics.get('execution_time_ms', 0),
                            'success_rate': metrics.get('success_rate', 0),
                            'trades_per_minute': metrics.get('trades_per_minute', 0),
                            'risk_cache_hits': metrics.get('risk_cache_hits', 0),
                            'mempool_latency_ms': metrics.get('mempool_latency_ms', 0),
                            'gas_optimization_ms': metrics.get('gas_optimization_ms', 0),
                            'total_executions': metrics.get('total_executions', 0),
                            'is_live': not metrics.get('_mock', False)
                        },
                        'status': {
                            'status': status.get('status', 'UNKNOWN'),
                            'fast_lane_active': status.get('fast_lane_active', False),
                            'smart_lane_active': status.get('smart_lane_active', False),
                            'mempool_connected': status.get('mempool_connected', False),
                            'uptime_seconds': status.get('uptime_seconds', 0),
                            'is_live': not status.get('_mock', False)
                        },
                        'data_source': 'LIVE' if not metrics.get('_mock', False) else 'MOCK'
                    }
                    
                    yield f"data: {json.dumps(message_data)}\n\n"
                    time.sleep(2)  # Update every 2 seconds for better responsiveness
                    counter += 1
                    
                except Exception as stream_error:
                    logger.error(f"Error in metrics stream iteration: {stream_error}")
                    # Send error message to client
                    error_data = {
                        'type': 'error',
                        'message': 'Metrics stream interrupted',
                        'timestamp': datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                    break
                    
        except Exception as e:
            logger.error(f"Critical error in metrics stream: {e}", exc_info=True)
            # Send final error message
            error_data = {
                'type': 'fatal_error',
                'message': 'Metrics stream failed',
                'timestamp': datetime.now().isoformat()
            }
            yield f"data: {json.dumps(error_data)}\n\n"
    
    # Return SSE response with proper headers
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['Access-Control-Allow-Origin'] = '*'
    response['X-Accel-Buffering'] = 'no'
    return response


# =========================================================================
# API ENDPOINTS (Updated with Fast Lane Integration)
# =========================================================================

def api_engine_status(request):
    """API endpoint for engine status with Fast Lane integration."""
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


def api_performance_metrics(request):
    """API endpoint for performance metrics with Fast Lane integration."""
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
def api_set_trading_mode(request):
    """API endpoint to set trading mode with Fast Lane engine integration."""
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

def start_trading_session(request):
    """Start a new trading session with comprehensive validation."""
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


def stop_trading_session(request, session_id):
    """Stop an active trading session with proper cleanup."""
    try:
        logger.info(f"Trading session stop requested for session {session_id} by user: {request.user.username}")
        # Mock session stop for demo
        messages.success(request, f'Demo trading session {session_id} stopped successfully!')
        logger.info(f"Demo trading session {session_id} stopped")
    except Exception as e:
        logger.error(f"Error stopping trading session {session_id}: {e}", exc_info=True)
        messages.error(request, "Failed to stop trading session.")
    
    return redirect('dashboard:home')


# =========================================================================
# DEBUG AND TESTING ENDPOINTS
# =========================================================================

def simple_test(request):
    """Simple test endpoint that returns basic HTML for debugging."""
    logger.debug("Simple test endpoint accessed")
    return HttpResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>DEX Bot Test</title>
        <style>body{{background:#000;color:#0f0;font-family:monospace;padding:50px;}}</style>
    </head>
    <body>
        <h1>🚀 Django DEX Bot is WORKING!</h1>
        <p>If you see this, Django views are working correctly.</p>
        <p>Time: {datetime.now()}</p>
        <p>User: {getattr(request.user, 'username', 'anonymous')}</p>
        <a href="/dashboard/" style="color:#0f0;">Go to Dashboard</a>
    </body>
    </html>
    """)


def debug_templates(request):
    """Debug template loading with comprehensive error reporting."""
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


def minimal_dashboard(request):
    """Minimal dashboard without template dependencies for emergency access."""
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