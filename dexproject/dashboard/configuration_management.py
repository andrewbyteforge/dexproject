"""
Configuration Management Views - Settings & Session Control

Contains all configuration panel views, CRUD operations, and session management.
Split from the original monolithic views.py file (1400+ lines) for better organization.

File: dexproject/dashboard/configuration_management.py
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from decimal import Decimal

from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, HttpRequest
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
# UTILITY FUNCTIONS FOR CONFIGURATION MANAGEMENT
# =========================================================================

def get_smart_lane_status() -> Dict[str, Any]:
    """
    Get Smart Lane status for configuration views.
    
    Returns:
        Dict containing Smart Lane availability and capabilities
    """
    try:
        from .smart_lane_features import smart_lane_available, smart_lane_pipeline
        
        if not smart_lane_available:
            return {
                'status': 'UNAVAILABLE',
                'pipeline_initialized': False,
                'capabilities': []
            }
        
        return {
            'status': 'OPERATIONAL' if smart_lane_pipeline else 'READY',
            'pipeline_initialized': smart_lane_pipeline is not None,
            'capabilities': [
                'HONEYPOT_DETECTION',
                'LIQUIDITY_ANALYSIS', 
                'SOCIAL_SENTIMENT',
                'TECHNICAL_ANALYSIS',
                'CONTRACT_SECURITY'
            ] if smart_lane_available else []
        }
        
    except ImportError:
        return {
            'status': 'UNAVAILABLE',
            'pipeline_initialized': False,
            'capabilities': []
        }


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


# =========================================================================
# CONFIGURATION PANEL VIEWS
# =========================================================================

def configuration_panel(request: HttpRequest, mode: str = 'FAST_LANE') -> HttpResponse:
    """
    Configuration panel for Fast Lane or Smart Lane with form handling.
    
    Displays configuration form for the specified trading mode and handles
    both GET (display) and POST (save configuration) requests.
    
    Args:
        request: Django HTTP request object
        mode: Trading mode ('fast_lane' or 'smart_lane')
        
    Returns:
        Rendered configuration panel template or redirect
    """
    handle_anonymous_user(request)
    
    # Normalize mode
    mode = mode.lower().replace('_', '-')
    if mode not in ['fast-lane', 'smart-lane']:
        mode = 'fast-lane'
    
    logger.info(f"Configuration panel accessed for mode: {mode} by user: {request.user}")
    
    if request.method == 'POST':
        return _handle_configuration_save(request, mode)
    else:
        return _handle_configuration_display_with_smart_lane(request, mode)


def _handle_configuration_save(request: HttpRequest, mode: str) -> HttpResponse:
    """Handle saving configuration for POST request."""
    try:
        logger.info(f"Saving {mode} configuration for user: {request.user}")
        
        # Extract form data
        config_name = request.POST.get('config_name', '').strip()
        if not config_name:
            messages.error(request, "Configuration name is required")
            return _handle_configuration_display_with_smart_lane(request, mode, request.POST)
        
        # Mode-specific configuration extraction
        if mode == 'fast-lane':
            config_data = _extract_fast_lane_config(request.POST)
        else:  # smart-lane
            config_data = _extract_smart_lane_config(request.POST)
        
        # Save configuration
        config = BotConfiguration.objects.create(
            user=request.user,
            name=config_name,
            trading_mode=mode.upper().replace('-', '_'),
            parameters=config_data,
            is_active=True
        )
        
        # Deactivate other configurations for this mode
        BotConfiguration.objects.filter(
            user=request.user,
            trading_mode=mode.upper().replace('-', '_')
        ).exclude(id=config.id).update(is_active=False)
        
        logger.info(f"Configuration '{config_name}' saved successfully with ID: {config.id}")
        messages.success(request, f"Configuration '{config_name}' saved successfully!")
        
        return redirect('dashboard:configuration_panel', mode=mode.replace('-', '_'))
        
    except IntegrityError as e:
        logger.error(f"Database integrity error saving configuration: {e}")
        messages.error(request, "Configuration name already exists. Please choose a different name.")
        return _handle_configuration_display_with_smart_lane(request, mode, request.POST)
    
    except Exception as e:
        logger.error(f"Error saving configuration: {e}", exc_info=True)
        messages.error(request, f"Error saving configuration: {str(e)}")
        return _handle_configuration_display_with_smart_lane(request, mode, request.POST)


def _extract_fast_lane_config(form_data) -> Dict[str, Any]:
    """Extract Fast Lane configuration from form data."""
    return {
        'position_size': float(form_data.get('position_size', 100)),
        'slippage_tolerance': float(form_data.get('slippage_tolerance', 1.0)),
        'gas_price_gwei': float(form_data.get('gas_price_gwei', 20)),
        'max_execution_time_ms': int(form_data.get('max_execution_time_ms', 500)),
        'enable_mev_protection': form_data.get('enable_mev_protection') == 'on',
        'auto_approval': form_data.get('auto_approval') == 'on',
        'risk_level': form_data.get('risk_level', 'MEDIUM'),
        'target_pairs': form_data.getlist('target_pairs') or ['WETH/USDC', 'WETH/USDT'],
        'min_liquidity_usd': float(form_data.get('min_liquidity_usd', 10000)),
        'max_position_value_usd': float(form_data.get('max_position_value_usd', 1000))
    }


def _extract_smart_lane_config(form_data) -> Dict[str, Any]:
    """Extract Smart Lane configuration from form data."""
    return {
        'position_size': float(form_data.get('position_size', 500)),
        'analysis_depth': form_data.get('analysis_depth', 'COMPREHENSIVE'),
        'max_analysis_time_seconds': float(form_data.get('max_analysis_time_seconds', 5.0)),
        'min_confidence_threshold': float(form_data.get('min_confidence_threshold', 0.7)),
        'risk_categories': form_data.getlist('risk_categories') or [
            'HONEYPOT_DETECTION',
            'LIQUIDITY_ANALYSIS',
            'CONTRACT_SECURITY'
        ],
        'enable_social_sentiment': form_data.get('enable_social_sentiment') == 'on',
        'enable_technical_analysis': form_data.get('enable_technical_analysis') == 'on',
        'thought_log_enabled': form_data.get('thought_log_enabled') == 'on',
        'auto_position_sizing': form_data.get('auto_position_sizing') == 'on',
        'exit_strategy': form_data.get('exit_strategy', 'TRAILING_STOP'),
        'max_acceptable_risk_score': float(form_data.get('max_acceptable_risk_score', 0.8)),
        'target_profit_percentage': float(form_data.get('target_profit_percentage', 20.0)),
        'stop_loss_percentage': float(form_data.get('stop_loss_percentage', 10.0))
    }


def _handle_configuration_display_with_smart_lane(request: HttpRequest, mode: str, form_data: Optional[Dict] = None) -> HttpResponse:
    """Handle displaying configuration form for GET request with Smart Lane support."""
    try:
        # Get engine status and metrics
        engine_status = engine_service.get_engine_status()
        performance_metrics = engine_service.get_performance_metrics()
        smart_lane_status = get_smart_lane_status()
        
        # Mode-specific settings
        mode_settings = {
            'fast-lane': {
                'display_name': 'Fast Lane',
                'description': 'Speed-optimized execution for time-sensitive trades',
                'target_execution_time': 78,
                'recommended_position_size': 100,
                'available': engine_status.get('fast_lane_active', False),
                'status': 'OPERATIONAL' if engine_status.get('fast_lane_active', False) else 'UNAVAILABLE'
            },
            'smart-lane': {
                'display_name': 'Smart Lane',
                'description': 'Intelligence-optimized analysis for strategic positions',
                'target_execution_time': 2500,
                'recommended_position_size': 500,
                'available': smart_lane_status.get('pipeline_initialized', False),
                'status': 'OPERATIONAL' if smart_lane_status.get('pipeline_initialized', False) else 'READY' if smart_lane_status.get('status') != 'UNAVAILABLE' else 'UNAVAILABLE'
            }
        }
        
        # Get user's existing configurations for this mode
        existing_configs = BotConfiguration.objects.filter(
            user=request.user,
            trading_mode=mode.upper().replace('-', '_')
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
        
        # Add Smart Lane specific context
        if mode == 'smart-lane':
            context.update({
                'smart_lane_status': smart_lane_status,
                'smart_lane_ready': smart_lane_status.get('pipeline_initialized', False),
                'smart_lane_capabilities': smart_lane_status.get('capabilities', []),
                'analysis_options': {
                    'analysis_depth': ['BASIC', 'COMPREHENSIVE', 'DEEP_DIVE'],
                    'enabled_categories': [
                        'HONEYPOT_DETECTION',
                        'LIQUIDITY_ANALYSIS', 
                        'SOCIAL_SENTIMENT',
                        'TECHNICAL_ANALYSIS',
                        'CONTRACT_SECURITY'
                    ],
                    'risk_levels': ['LOW', 'MEDIUM', 'HIGH'],
                    'exit_strategies': ['FIXED_TARGET', 'TRAILING_STOP', 'DYNAMIC_EXIT']
                }
            })
        
        return render(request, 'dashboard/configuration_panel.html', context)
        
    except Exception as e:
        logger.error(f"Error loading configuration panel: {e}", exc_info=True)
        messages.error(request, f"Error loading configuration panel: {str(e)}")
        return render(request, 'dashboard/error.html', {'error': str(e)})


# =========================================================================
# CONFIGURATION MANAGEMENT CRUD OPERATIONS
# =========================================================================

@require_POST
@csrf_exempt
def save_configuration(request: HttpRequest) -> JsonResponse:
    """
    Save bot configuration via AJAX.
    
    Creates or updates a bot configuration with the provided parameters
    and manages active configuration state.
    
    Args:
        request: Django HTTP request containing configuration data
        
    Returns:
        JsonResponse indicating success or failure
    """
    try:
        handle_anonymous_user(request)
        
        data = json.loads(request.body)
        logger.info(f"Saving configuration via API for user: {request.user}")
        
        # Validate required fields
        config_name = data.get('name', '').strip()
        trading_mode = data.get('trading_mode', '').upper()
        parameters = data.get('parameters', {})
        
        if not config_name:
            return JsonResponse({'success': False, 'error': 'Configuration name is required'})
        
        if trading_mode not in ['FAST_LANE', 'SMART_LANE']:
            return JsonResponse({'success': False, 'error': 'Invalid trading mode'})
        
        # Create or update configuration
        config, created = BotConfiguration.objects.update_or_create(
            user=request.user,
            name=config_name,
            defaults={
                'trading_mode': trading_mode,
                'parameters': parameters,
                'is_active': data.get('is_active', True)
            }
        )
        
        # If this config is set as active, deactivate others
        if config.is_active:
            BotConfiguration.objects.filter(
                user=request.user,
                trading_mode=trading_mode
            ).exclude(id=config.id).update(is_active=False)
        
        logger.info(f"Configuration '{config_name}' {'created' if created else 'updated'} successfully")
        
        return JsonResponse({
            'success': True,
            'config_id': config.id,
            'message': f"Configuration {'created' if created else 'updated'} successfully"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    
    except Exception as e:
        logger.error(f"Error saving configuration: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["GET", "POST"])
def load_configuration(request: HttpRequest) -> JsonResponse:
    """
    Load bot configuration by ID or name.
    
    Retrieves a specific bot configuration and optionally sets it as active
    for the current user session.
    
    Args:
        request: Django HTTP request containing config identifier
        
    Returns:
        JsonResponse with configuration data or error
    """
    try:
        handle_anonymous_user(request)
        
        if request.method == 'GET':
            config_id = request.GET.get('config_id')
        else:
            data = json.loads(request.body)
            config_id = data.get('config_id')
        
        if not config_id:
            return JsonResponse({'success': False, 'error': 'Configuration ID is required'})
        
        # Get configuration
        config = get_object_or_404(BotConfiguration, id=config_id, user=request.user)
        
        # Update last used timestamp
        config.last_used_at = datetime.now()
        config.save(update_fields=['last_used_at'])
        
        logger.info(f"Configuration '{config.name}' loaded successfully for user: {request.user}")
        
        return JsonResponse({
            'success': True,
            'configuration': {
                'id': config.id,
                'name': config.name,
                'trading_mode': config.trading_mode,
                'parameters': config.parameters,
                'is_active': config.is_active,
                'created_at': config.created_at.isoformat(),
                'last_used_at': config.last_used_at.isoformat() if config.last_used_at else None
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    
    except Exception as e:
        logger.error(f"Error loading configuration: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})


@require_POST
@csrf_exempt
def delete_configuration(request: HttpRequest) -> JsonResponse:
    """
    Delete bot configuration by ID.
    
    Removes a bot configuration from the database with proper ownership
    validation and cleanup.
    
    Args:
        request: Django HTTP request containing config ID
        
    Returns:
        JsonResponse indicating success or failure
    """
    try:
        handle_anonymous_user(request)
        
        data = json.loads(request.body)
        config_id = data.get('config_id')
        
        if not config_id:
            return JsonResponse({'success': False, 'error': 'Configuration ID is required'})
        
        # Get and delete configuration
        config = get_object_or_404(BotConfiguration, id=config_id, user=request.user)
        config_name = config.name
        
        config.delete()
        
        logger.info(f"Configuration '{config_name}' deleted successfully for user: {request.user}")
        
        return JsonResponse({
            'success': True,
            'message': f"Configuration '{config_name}' deleted successfully"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    
    except Exception as e:
        logger.error(f"Error deleting configuration: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["GET"])
def get_configurations(request: HttpRequest) -> JsonResponse:
    """
    Get all configurations for the current user.
    
    Returns a list of all bot configurations belonging to the current user
    with optional filtering by trading mode.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with configurations list or error
    """
    try:
        handle_anonymous_user(request)
        
        # Get filter parameters
        mode_filter = request.GET.get('mode', '').upper()
        active_only = request.GET.get('active_only', 'false').lower() == 'true'
        
        # Build query
        configs = BotConfiguration.objects.filter(user=request.user)
        
        if mode_filter and mode_filter in ['FAST_LANE', 'SMART_LANE']:
            configs = configs.filter(trading_mode=mode_filter)
        
        if active_only:
            configs = configs.filter(is_active=True)
        
        # Order by most recently used
        configs = configs.order_by('-last_used_at', '-updated_at')
        
        # Format response
        configurations = []
        for config in configs:
            configurations.append({
                'id': config.id,
                'name': config.name,
                'trading_mode': config.trading_mode,
                'is_active': config.is_active,
                'created_at': config.created_at.isoformat(),
                'updated_at': config.updated_at.isoformat(),
                'last_used_at': config.last_used_at.isoformat() if config.last_used_at else None,
                'parameter_count': len(config.parameters) if config.parameters else 0
            })
        
        return JsonResponse({
            'success': True,
            'configurations': configurations,
            'total_count': len(configurations)
        })
        
    except Exception as e:
        logger.error(f"Error getting configurations: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})


# =========================================================================
# CONFIGURATION SUMMARY AND LISTING VIEWS
# =========================================================================

def configuration_summary(request: HttpRequest, config_id: int) -> HttpResponse:
    """
    Display detailed summary of a specific configuration.
    
    Shows comprehensive configuration details including parameters,
    performance history, and usage statistics.
    
    Args:
        request: Django HTTP request object
        config_id: ID of the configuration to display
        
    Returns:
        Rendered configuration summary template
    """
    try:
        handle_anonymous_user(request)
        
        config = get_object_or_404(BotConfiguration, id=config_id, user=request.user)
        
        logger.info(f"Configuration summary requested: {config.name} (ID: {config_id})")
        
        # Get related trading sessions
        sessions = TradingSession.objects.filter(
            user=request.user,
            configuration_name=config.name
        ).order_by('-created_at')[:10]
        
        # Calculate summary statistics
        total_sessions = sessions.count()
        active_sessions = sessions.filter(is_active=True).count()
        
        context = {
            'config': config,
            'sessions': sessions,
            'total_sessions': total_sessions,
            'active_sessions': active_sessions,
            'page_title': f'Configuration: {config.name}',
            'user': request.user,
            'mode_display': config.trading_mode.replace('_', ' ').title()
        }
        
        return render(request, 'dashboard/configuration_summary.html', context)
        
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
        handle_anonymous_user(request)
        
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


# =========================================================================
# TRADING SESSION MANAGEMENT
# =========================================================================

@require_POST
@csrf_exempt
def start_session(request: HttpRequest) -> JsonResponse:
    """
    Start a new trading session with specified configuration.
    
    Creates and initializes a new trading session using the selected
    bot configuration and trading mode.
    
    Args:
        request: Django HTTP request containing session parameters
        
    Returns:
        JsonResponse indicating success or failure of session start
    """
    try:
        handle_anonymous_user(request)
        
        data = json.loads(request.body)
        config_id = data.get('config_id')
        
        if not config_id:
            return JsonResponse({'success': False, 'error': 'Configuration ID is required'})
        
        # Get configuration
        config = get_object_or_404(BotConfiguration, id=config_id, user=request.user)
        
        # Check if there's already an active session
        existing_session = TradingSession.objects.filter(
            user=request.user,
            is_active=True
        ).first()
        
        if existing_session:
            return JsonResponse({
                'success': False,
                'error': 'Another trading session is already active'
            })
        
        # Create new session
        session = TradingSession.objects.create(
            user=request.user,
            configuration_name=config.name,
            trading_mode=config.trading_mode,
            parameters=config.parameters,
            is_active=True,
            start_time=datetime.now()
        )
        
        # Update configuration last used time
        config.last_used_at = datetime.now()
        config.save(update_fields=['last_used_at'])
        
        logger.info(f"Trading session started: {session.id} with config '{config.name}'")
        
        return JsonResponse({
            'success': True,
            'session_id': session.id,
            'message': f'Trading session started with {config.name}',
            'trading_mode': config.trading_mode
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    
    except Exception as e:
        logger.error(f"Error starting session: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})


@require_POST
@csrf_exempt
def stop_session(request: HttpRequest) -> JsonResponse:
    """
    Stop the active trading session.
    
    Terminates the currently active trading session and records
    the end time and session statistics.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse indicating success or failure of session stop
    """
    try:
        handle_anonymous_user(request)
        
        # Find active session
        session = TradingSession.objects.filter(
            user=request.user,
            is_active=True
        ).first()
        
        if not session:
            return JsonResponse({'success': False, 'error': 'No active trading session found'})
        
        # Stop session
        session.is_active = False
        session.end_time = datetime.now()
        session.save(update_fields=['is_active', 'end_time'])
        
        logger.info(f"Trading session stopped: {session.id}")
        
        return JsonResponse({
            'success': True,
            'session_id': session.id,
            'message': 'Trading session stopped successfully'
        })
        
    except Exception as e:
        logger.error(f"Error stopping session: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["GET"])
def get_session_status(request: HttpRequest) -> JsonResponse:
    """
    Get current trading session status.
    
    Returns information about the currently active trading session
    including configuration details and runtime statistics.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with session status data
    """
    try:
        handle_anonymous_user(request)
        
        # Find active session
        session = TradingSession.objects.filter(
            user=request.user,
            is_active=True
        ).first()
        
        if not session:
            return JsonResponse({
                'success': True,
                'has_active_session': False,
                'message': 'No active trading session'
            })
        
        # Calculate runtime
        runtime_seconds = (datetime.now() - session.start_time).total_seconds()
        
        return JsonResponse({
            'success': True,
            'has_active_session': True,
            'session': {
                'id': session.id,
                'configuration_name': session.configuration_name,
                'trading_mode': session.trading_mode,
                'start_time': session.start_time.isoformat(),
                'runtime_seconds': int(runtime_seconds),
                'runtime_formatted': f"{int(runtime_seconds // 3600):02d}:{int((runtime_seconds % 3600) // 60):02d}:{int(runtime_seconds % 60):02d}"
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting session status: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})


# =========================================================================
# PERFORMANCE METRICS FOR CONFIGURATION VIEWS
# =========================================================================

@require_http_methods(["GET"])
def get_performance_metrics(request: HttpRequest) -> JsonResponse:
    """
    Get performance metrics for configuration management views.
    
    Returns performance data specific to configuration management
    including configuration usage statistics and success rates.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with performance metrics data
    """
    try:
        handle_anonymous_user(request)
        
        # Get user's configurations
        total_configs = BotConfiguration.objects.filter(user=request.user).count()
        active_configs = BotConfiguration.objects.filter(user=request.user, is_active=True).count()
        
        # Get session statistics
        total_sessions = TradingSession.objects.filter(user=request.user).count()
        active_sessions = TradingSession.objects.filter(user=request.user, is_active=True).count()
        
        # Get engine metrics
        engine_metrics = engine_service.get_performance_metrics()
        
        return JsonResponse({
            'success': True,
            'metrics': {
                'configurations': {
                    'total': total_configs,
                    'active': active_configs,
                    'fast_lane': BotConfiguration.objects.filter(
                        user=request.user, 
                        trading_mode='FAST_LANE'
                    ).count(),
                    'smart_lane': BotConfiguration.objects.filter(
                        user=request.user, 
                        trading_mode='SMART_LANE'
                    ).count()
                },
                'sessions': {
                    'total': total_sessions,
                    'active': active_sessions
                },
                'engine': engine_metrics,
                'timestamp': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})