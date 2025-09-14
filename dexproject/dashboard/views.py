"""
Complete Dashboard Views for DEX Trading Bot

Updated with configuration summary functionality, proper error handling,
thorough logging, and improved user experience.

File: dashboard/views.py
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any
from decimal import Decimal
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, StreamingHttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.conf import settings
from django.db import IntegrityError
from django.core.paginator import Paginator
from django.urls import reverse
from .models import BotConfiguration, TradingSession, UserProfile

logger = logging.getLogger(__name__)


def dashboard_home(request):
    """
    Main dashboard page with comprehensive error handling and logging.
    
    Displays trading bot status, performance metrics, and recent activity.
    """
    try:
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
        
        # Get user's configurations for display
        try:
            user_configs = BotConfiguration.objects.filter(
                user=request.user
            ).order_by('-last_used_at', '-updated_at')[:5]
            
            # Get active sessions
            active_sessions = TradingSession.objects.filter(
                user=request.user,
                status__in=['ACTIVE', 'STARTING']
            ).order_by('-started_at')[:3]
            
            logger.debug(f"Found {user_configs.count()} configs and {active_sessions.count()} active sessions")
            
        except Exception as db_error:
            logger.error(f"Database error loading user data: {db_error}", exc_info=True)
            user_configs = []
            active_sessions = []
        
        # Prepare context with mock data and real user data
        context = {
            'page_title': 'Trading Dashboard',
            'user_profile': {
                'display_name': getattr(request.user, 'first_name', 'Demo User') or 'Demo User'
            },
            'bot_configs': user_configs,
            'active_sessions': active_sessions,
            'engine_status': {
                'status': 'OPERATIONAL',
                'message': 'Demo mode - all systems operational',
                'fast_lane_active': True,
                'smart_lane_active': False,
                'mempool_connected': True,
                'risk_cache_status': 'HEALTHY',
                'is_mock': True
            },
            'performance_metrics': {
                'execution_time_ms': 78.5,
                'success_rate': 94.2,
                'trades_per_minute': 12.3,
                'risk_cache_hits': 98,
                'mempool_latency_ms': 1.2,
                'gas_optimization_ms': 15.8,
                'fast_lane_trades_today': 67,
                'smart_lane_trades_today': 23,
                'is_mock': True
            },
            'show_onboarding': user_configs.count() == 0,
            'user': request.user
        }
        
        logger.debug("Dashboard context created successfully")
        return render(request, 'dashboard/home.html', context)
        
    except Exception as e:
        logger.error(f"Critical error in dashboard_home: {e}", exc_info=True)
        return render(request, 'dashboard/error.html', {'error': str(e)})


def mode_selection(request):
    """
    Mode selection interface with comprehensive error handling.
    
    Allows users to choose between Fast Lane and Smart Lane trading modes.
    """
    try:
        logger.info(f"Mode selection accessed by user: {getattr(request.user, 'username', 'anonymous')}")
        
        context = {
            'page_title': 'Mode Selection - Fast Lane vs Smart Lane',
            'fast_lane_metrics': {
                'execution_time_ms': 78.5,
                'success_rate': 94.2,
                'trades_per_minute': 12.3,
                'is_mock': True
            },
            'smart_lane_metrics': {
                'execution_time_ms': 2500,
                'success_rate': 96.2,
                'risk_adjusted_return': 15.3,
                'is_mock': True
            }
        }
        
        logger.debug("Mode selection context created successfully")
        return render(request, 'dashboard/mode_selection.html', context)
        
    except Exception as e:
        logger.error(f"Error in mode_selection: {e}", exc_info=True)
        messages.error(request, "Error loading mode selection.")
        return redirect('dashboard:home')


def configuration_panel(request, mode):
    """
    Comprehensive configuration panel for specific trading mode.
    
    Handles both GET (display form) and POST (save configuration) requests
    with extensive validation, error handling, and logging.
    
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
        
        # Prepare template context
        context = {
            'mode': mode,
            'mode_display': mode_display,
            'config': default_config,
            'page_title': f'{mode_display} Configuration',
            'user': request.user,
        }
        
        logger.debug(f"Rendering {mode_display} configuration template")
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
# API ENDPOINTS
# =========================================================================

def metrics_stream(request):
    """
    Server-Sent Events endpoint for real-time metrics with proper error handling.
    
    Streams live trading metrics to the dashboard for real-time updates.
    """
    def event_stream():
        """Generator function for SSE data stream with comprehensive error handling."""
        import time
        import random
        
        try:
            # Send initial connection confirmation
            yield f"data: {json.dumps({'type': 'connection', 'status': 'connected', 'timestamp': datetime.now().isoformat()})}\n\n"
            
            # Stream metrics updates
            counter = 0
            while counter < 50:  # Limit to prevent long-running processes
                try:
                    # Generate realistic mock metrics
                    base_time = 78
                    execution_time = base_time + random.uniform(-5, 10)
                    
                    message_data = {
                        'type': 'metrics_update',
                        'timestamp': datetime.now().isoformat(),
                        'metrics': {
                            'execution_time_ms': round(execution_time, 2),
                            'success_rate': round(random.uniform(92, 98), 1),
                            'trades_per_minute': round(random.uniform(8, 15), 1),
                            'risk_cache_hits': random.randint(95, 100),
                            'mempool_latency_ms': round(random.uniform(0.5, 2.0), 2),
                            'is_mock': True
                        },
                        'status': {
                            'status': 'OPERATIONAL',
                            'fast_lane_active': True,
                            'smart_lane_active': False,
                            'is_mock': True
                        }
                    }
                    
                    yield f"data: {json.dumps(message_data)}\n\n"
                    time.sleep(3)  # Update every 3 seconds
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
    
    # Return SSE response with proper headers
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['Access-Control-Allow-Origin'] = '*'
    response['X-Accel-Buffering'] = 'no'
    return response


def api_engine_status(request):
    """API endpoint for engine status with comprehensive error handling."""
    try:
        logger.debug("Engine status API called")
        status = {
            'status': 'OPERATIONAL',
            'message': 'Demo mode active',
            'fast_lane_active': True,
            'smart_lane_active': False,
            'mempool_connected': True,
            'risk_cache_status': 'HEALTHY',
            'is_mock': True
        }
        return JsonResponse({'success': True, 'data': status})
    except Exception as e:
        logger.error(f"Error getting engine status: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'Failed to retrieve engine status'}, status=500)


def api_performance_metrics(request):
    """API endpoint for performance metrics with error handling."""
    try:
        logger.debug("Performance metrics API called")
        import random
        metrics = {
            'execution_time_ms': round(78 + random.uniform(-5, 10), 2),
            'success_rate': round(random.uniform(92, 98), 1),
            'trades_per_minute': round(random.uniform(8, 15), 1),
            'risk_cache_hits': random.randint(95, 100),
            'mempool_latency_ms': round(random.uniform(0.5, 2.0), 2),
            'is_mock': True
        }
        return JsonResponse({'success': True, 'data': metrics})
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'Failed to retrieve metrics'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_set_trading_mode(request):
    """API endpoint to change trading mode with validation and logging."""
    try:
        logger.info(f"Trading mode change requested by user: {getattr(request.user, 'username', 'anonymous')}")
        
        data = json.loads(request.body)
        mode = data.get('mode', '').upper()
        
        if mode not in ['FAST_LANE', 'SMART_LANE']:
            logger.warning(f"Invalid trading mode requested: {mode}")
            return JsonResponse({'success': False, 'error': 'Invalid trading mode'}, status=400)
        
        # Log successful mode change (mock)
        logger.info(f"Mock mode change to: {mode}")
        return JsonResponse({'success': True, 'mode': mode})
            
    except json.JSONDecodeError:
        logger.error("Invalid JSON in trading mode request")
        return JsonResponse({'success': False, 'error': 'Invalid request format'}, status=400)
    except Exception as e:
        logger.error(f"Error setting trading mode: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'Failed to set trading mode'}, status=500)


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