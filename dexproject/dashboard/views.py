"""
Complete Dashboard Views for DEX Trading Bot

This file contains all functions referenced in dashboard/urls.py to resolve
the AttributeError and ensure Django can start properly.

Features:
- All URL-referenced functions implemented
- Smart Lane functionality
- Configuration management
- Session management  
- Performance metrics APIs
- Comprehensive error handling
- VS Code/Pylance compatible with type annotations
- PEP 8 compliant formatting

File: dexproject/dashboard/views.py
"""

from django.contrib.auth.decorators import login_required
import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Union, List
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
from django.utils import timezone

from .models import BotConfiguration, TradingSession, UserProfile
from .engine_service import engine_service

logger = logging.getLogger(__name__)


# =========================================================================
# ENGINE INITIALIZATION HELPERS
# =========================================================================

async def ensure_engines_initialized() -> None:
    """
    Ensure both Fast Lane and Smart Lane engines are initialized.
    
    Initializes both engines if not already done and handles initialization 
    errors gracefully by falling back to mock mode if necessary.
    """
    # Initialize Fast Lane engine
    if not engine_service.engine_initialized and not engine_service.mock_mode:
        try:
            success = await engine_service.initialize_engine(chain_id=1)
            if success:
                logger.info("Fast Lane engine initialized successfully")
            else:
                logger.warning("Failed to initialize Fast Lane engine - falling back to mock mode")
        except Exception as e:
            logger.error(f"Fast Lane engine initialization error: {e}", exc_info=True)
    
    # Initialize Smart Lane pipeline
    if not engine_service.smart_lane_initialized:
        try:
            success = await engine_service.initialize_smart_lane(chain_id=1)
            if success:
                logger.info("Smart Lane pipeline initialized successfully")
            else:
                logger.warning("Failed to initialize Smart Lane pipeline - using mock data")
        except Exception as e:
            logger.error(f"Smart Lane pipeline initialization error: {e}", exc_info=True)


def run_async_in_view(coro) -> Optional[Any]:
    """
    Helper to run async code in Django views.
    
    Creates a new event loop to execute async functions within synchronous
    Django view functions.
    
    Args:
        coro: Async coroutine to execute
        
    Returns:
        Result of the coroutine execution or None if failed
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(coro)
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Error running async operation: {e}")
        return None


# =========================================================================
# MAIN DASHBOARD VIEWS
# =========================================================================

def dashboard_home(request: HttpRequest) -> HttpResponse:
    """
    Main dashboard home page with dual-engine status and metrics.
    
    Displays overview of both Fast Lane and Smart Lane engines including
    real-time metrics, system status, and recent activity.
    """
    try:
        logger.info(f"Dashboard home accessed by user: {request.user}")
        
        # Initialize engines if needed
        run_async_in_view(ensure_engines_initialized())
        
        # Get comprehensive engine status
        engine_status = engine_service.get_engine_status()
        performance_metrics = engine_service.get_performance_metrics()
        
        # Prepare metrics for template
        fast_lane_metrics = {
            'execution_time_ms': performance_metrics.get('fast_lane_execution_time_ms', 78),
            'success_rate': performance_metrics.get('fast_lane_success_rate', 96.8),
            'trades_per_minute': performance_metrics.get('trades_per_minute', 25),
            'status': 'Operational' if engine_status.get('fast_lane_active') else 'Mock Mode',
            'phase': 'Phase 2-4 Complete'
        }
        
        smart_lane_metrics = {
            'execution_time_ms': performance_metrics.get('smart_lane_analysis_time_ms', 2800),
            'success_rate': performance_metrics.get('smart_lane_success_rate', 94.2),
            'analyses_today': performance_metrics.get('smart_lane_analyses_today', 87),
            'risk_adjusted_return': performance_metrics.get('risk_adjusted_return', 10.3),
            'status': 'Development' if engine_status.get('smart_lane_available') else 'Phase 5 Pending',
            'phase': 'Phase 5 In Progress'
        }
        
        # System health indicators
        system_health = {
            'fast_lane_available': engine_status.get('fast_lane_available', False),
            'smart_lane_available': engine_status.get('smart_lane_available', False),
            'circuit_breaker_ok': engine_status.get('circuit_breaker_state') == 'CLOSED',
            'mempool_connected': engine_status.get('mempool_connected', False),
            'data_source': 'LIVE' if not engine_status.get('_mock', True) else 'MOCK'
        }
        
        # Recent activity (placeholder)
        recent_activity = []
        
        context = {
            'engine_status': engine_status,
            'performance_metrics': performance_metrics,
            'fast_lane_metrics': fast_lane_metrics,
            'smart_lane_metrics': smart_lane_metrics,
            'system_health': system_health,
            'recent_activity': recent_activity,
            'is_mock_mode': engine_status.get('_mock', True),
            'timestamp': datetime.now().isoformat()
        }
        
        return render(request, 'dashboard/home.html', context)
        
    except Exception as e:
        logger.error(f"Dashboard home error: {e}", exc_info=True)
        messages.error(request, f"Dashboard error: {str(e)}")
        
        # Provide minimal fallback context
        context = {
            'engine_status': {'status': 'ERROR'},
            'performance_metrics': {},
            'fast_lane_metrics': {'status': 'Error', 'phase': 'Unknown'},
            'smart_lane_metrics': {'status': 'Error', 'phase': 'Unknown'},
            'system_health': {'fast_lane_available': False, 'smart_lane_available': False},
            'recent_activity': [],
            'is_mock_mode': True,
            'error': str(e)
        }
        
        return render(request, 'dashboard/home.html', context)


def mode_selection(request: HttpRequest) -> HttpResponse:
    """
    Trading mode selection page for choosing between Fast Lane and Smart Lane.
    
    Displays both engine options with real-time metrics and availability status.
    Handles mode selection and redirects to appropriate configuration panel.
    """
    try:
        logger.info(f"Mode selection accessed by user: {request.user}")
        
        # Initialize engines if needed
        run_async_in_view(ensure_engines_initialized())
        
        # Handle mode selection POST request
        if request.method == 'POST':
            selected_mode = request.POST.get('mode')
            logger.info(f"User {request.user} selected mode: {selected_mode}")
            
            if selected_mode in ['FAST_LANE', 'SMART_LANE']:
                # Set the trading mode
                success = run_async_in_view(engine_service.set_trading_mode(selected_mode))
                
                if success:
                    messages.success(request, f"{selected_mode.replace('_', ' ').title()} mode activated")
                    return redirect('dashboard:configuration_panel', mode=selected_mode.lower())
                else:
                    messages.error(request, f"Failed to activate {selected_mode.replace('_', ' ').title()} mode")
            else:
                messages.error(request, "Invalid mode selection")
        
        # Get current engine status and metrics
        engine_status = engine_service.get_engine_status()
        performance_metrics = engine_service.get_performance_metrics()
        
        # Prepare metrics for template
        fast_lane_metrics = {
            'execution_time_ms': int(performance_metrics.get('fast_lane_execution_time_ms', 78)),
            'success_rate': f"{performance_metrics.get('fast_lane_success_rate', 96.8):.1f}",
            'trades_per_minute': performance_metrics.get('trades_per_minute', 25),
            'status': 'Operational' if engine_status.get('fast_lane_active') else 'Ready (Mock Mode)',
            'phase': 'Phases 2-4 Complete'
        }
        
        smart_lane_metrics = {
            'execution_time_ms': int(performance_metrics.get('smart_lane_analysis_time_ms', 2800)),
            'success_rate': f"{performance_metrics.get('smart_lane_success_rate', 94.2):.1f}",
            'risk_adjusted_return': f"{performance_metrics.get('risk_adjusted_return', 10.3):.1f}",
            'analyses_today': performance_metrics.get('smart_lane_analyses_today', 87),
            'status': 'Development Ready' if engine_status.get('smart_lane_available') else 'Phase 5 Pending',
            'phase': 'Phase 5 In Progress'
        }
        
        # Engine availability flags
        fast_lane_available = engine_status.get('fast_lane_available', False)
        smart_lane_available = engine_status.get('smart_lane_available', False)
        
        context = {
            'fast_lane_metrics': fast_lane_metrics,
            'smart_lane_metrics': smart_lane_metrics,
            'fast_lane_available': fast_lane_available,
            'smart_lane_available': smart_lane_available,
            'is_mock_mode': engine_status.get('_mock', True),
            'timestamp': datetime.now().isoformat()
        }
        
        return render(request, 'dashboard/mode_selection.html', context)
        
    except Exception as e:
        logger.error(f"Mode selection error: {e}", exc_info=True)
        messages.error(request, f"Mode selection error: {str(e)}")
        
        # Provide fallback context
        context = {
            'fast_lane_metrics': {'status': 'Error', 'phase': 'Unknown'},
            'smart_lane_metrics': {'status': 'Error', 'phase': 'Unknown'},
            'fast_lane_available': False,
            'smart_lane_available': False,
            'is_mock_mode': True,
            'error': str(e)
        }
        
        return render(request, 'dashboard/mode_selection.html', context)


def configuration_panel(request: HttpRequest, mode: str) -> HttpResponse:
    """
    Configuration panel for selected trading mode (Fast Lane or Smart Lane).
    
    Displays mode-specific configuration options and handles configuration
    form submission with validation and error handling.
    """
    try:
        logger.info(f"Configuration panel accessed for {mode} by user: {request.user}")
        
        # Validate mode parameter
        if mode not in ['fast_lane', 'smart_lane']:
            messages.error(request, f"Invalid trading mode: {mode}")
            return redirect('dashboard:mode_selection')
        
        # Initialize engines if needed
        run_async_in_view(ensure_engines_initialized())
        
        # Handle configuration form submission
        if request.method == 'POST':
            return handle_configuration_form(request, mode)
        
        # Get current engine status for mode availability
        engine_status = engine_service.get_engine_status()
        
        # Check if selected mode is available
        mode_available = True
        if mode == 'fast_lane':
            mode_available = engine_status.get('fast_lane_available', False)
        elif mode == 'smart_lane':
            mode_available = engine_status.get('smart_lane_available', False)
        
        if not mode_available:
            messages.warning(request, f"{mode.replace('_', ' ').title()} is not currently available")
        
        # Get user's existing configurations for this mode
        user_configs = BotConfiguration.objects.filter(
            user=request.user,
            trading_mode=mode.upper()
        ).order_by('-updated_at')[:5]
        
        # Prepare mode-specific context
        context = {
            'mode': mode,
            'mode_title': mode.replace('_', ' ').title(),
            'mode_available': mode_available,
            'user_configurations': user_configs,
            'engine_status': engine_status,
            'is_mock_mode': engine_status.get('_mock', True),
            'timestamp': datetime.now().isoformat()
        }
        
        # Add mode-specific default values
        if mode == 'fast_lane':
            context.update({
                'default_slippage': getattr(settings, 'DEFAULT_SLIPPAGE_PERCENT', 1.0),
                'default_gas_price': getattr(settings, 'MAX_GAS_PRICE_GWEI', 50.0),
                'default_position_size': getattr(settings, 'MAX_POSITION_SIZE_USD', 1000.0),
                'execution_timeout': getattr(settings, 'EXECUTION_TIMEOUT_SECONDS', 30)
            })
        elif mode == 'smart_lane':
            context.update({
                'default_analysis_depth': 'COMPREHENSIVE',
                'default_risk_tolerance': 'MEDIUM',
                'default_thought_log': True,
                'default_position_sizing': True,
                'max_analysis_time': 5.0
            })
        
        return render(request, 'dashboard/configuration_panel.html', context)
        
    except Exception as e:
        logger.error(f"Configuration panel error for {mode}: {e}", exc_info=True)
        messages.error(request, f"Configuration panel error: {str(e)}")
        return redirect('dashboard:mode_selection')


def handle_configuration_form(request: HttpRequest, mode: str) -> HttpResponse:
    """
    Handle configuration form submission for both Fast Lane and Smart Lane.
    
    Validates form data, creates/updates BotConfiguration objects, and
    redirects to appropriate summary page.
    """
    try:
        # Extract common form fields
        config_name = request.POST.get('config_name', '').strip()
        config_description = request.POST.get('config_description', '').strip()
        
        # Validate required fields
        if not config_name:
            messages.error(request, "Configuration name is required")
            return redirect('dashboard:configuration_panel', mode=mode)
        
        # Check for duplicate names
        existing_config = BotConfiguration.objects.filter(
            user=request.user,
            name=config_name,
            trading_mode=mode.upper()
        ).first()
        
        if existing_config:
            messages.error(request, f"Configuration '{config_name}' already exists")
            return redirect('dashboard:configuration_panel', mode=mode)
        
        # Create new configuration
        bot_config = BotConfiguration(
            user=request.user,
            name=config_name,
            description=config_description,
            trading_mode=mode.upper(),
            status=BotConfiguration.ConfigStatus.DRAFT
        )
        
        # Handle mode-specific fields
        if mode == 'fast_lane':
            # Extract Fast Lane specific fields
            bot_config.max_slippage_percent = Decimal(request.POST.get('slippage_tolerance', '1.0'))
            bot_config.max_gas_price_gwei = Decimal(request.POST.get('gas_price_limit', '50.0'))
            bot_config.position_size_usd = Decimal(request.POST.get('position_size', '1000.0'))
            bot_config.execution_timeout_seconds = int(request.POST.get('execution_timeout', '30'))
            
            # Fast Lane specific settings
            mev_protection = request.POST.get('mev_protection') == 'on'
            private_mempool = request.POST.get('private_mempool') == 'on'
            
            # Store Fast Lane settings in additional_settings JSON field
            bot_config.additional_settings = {
                'mev_protection_enabled': mev_protection,
                'private_mempool_enabled': private_mempool,
                'fast_lane_mode': True
            }
            
        elif mode == 'smart_lane':
            # Extract Smart Lane specific fields
            analysis_depth = request.POST.get('analysis_depth', 'COMPREHENSIVE')
            risk_tolerance = request.POST.get('risk_tolerance_level', 'MEDIUM')
            ai_thought_log = request.POST.get('ai_thought_log') == 'on'
            dynamic_sizing = request.POST.get('dynamic_sizing') == 'on'
            
            # Set Smart Lane specific fields
            bot_config.risk_tolerance_level = risk_tolerance
            bot_config.analysis_depth = analysis_depth
            
            # Store Smart Lane settings in additional_settings JSON field
            bot_config.additional_settings = {
                'ai_thought_log_enabled': ai_thought_log,
                'dynamic_position_sizing': dynamic_sizing,
                'smart_lane_mode': True,
                'enabled_categories': [
                    'HONEYPOT_DETECTION',
                    'LIQUIDITY_ANALYSIS',
                    'SOCIAL_SENTIMENT',
                    'TECHNICAL_ANALYSIS',
                    'CONTRACT_SECURITY'
                ]
            }
        
        # Save configuration
        bot_config.save()
        
        logger.info(f"Configuration '{config_name}' created for {mode} by user {request.user}")
        messages.success(request, f"Configuration '{config_name}' saved successfully")
        
        return redirect('dashboard:configuration_summary', config_id=bot_config.id)
        
    except ValueError as e:
        logger.error(f"Configuration form validation error: {e}")
        messages.error(request, f"Invalid configuration values: {str(e)}")
        return redirect('dashboard:configuration_panel', mode=mode)
        
    except IntegrityError as e:
        logger.error(f"Configuration database error: {e}")
        messages.error(request, "Database error - please try again")
        return redirect('dashboard:configuration_panel', mode=mode)
        
    except Exception as e:
        logger.error(f"Configuration form handling error: {e}", exc_info=True)
        messages.error(request, f"Error saving configuration: {str(e)}")
        return redirect('dashboard:configuration_panel', mode=mode)


def dashboard_settings(request: HttpRequest) -> HttpResponse:
    """
    Dashboard settings page for user preferences and system configuration.
    
    Allows users to configure dashboard preferences, notification settings,
    and system-wide trading parameters.
    """
    try:
        logger.info(f"Dashboard settings accessed by user: {request.user}")
        
        if request.method == 'POST':
            # Handle settings form submission
            user_profile, created = UserProfile.objects.get_or_create(user=request.user)
            
            # Update user preferences
            user_profile.notification_preferences = {
                'email_notifications': request.POST.get('email_notifications') == 'on',
                'sms_notifications': request.POST.get('sms_notifications') == 'on',
                'trade_alerts': request.POST.get('trade_alerts') == 'on',
                'risk_alerts': request.POST.get('risk_alerts') == 'on'
            }
            
            # Update dashboard preferences
            user_profile.dashboard_preferences = {
                'theme': request.POST.get('theme', 'dark'),
                'refresh_rate': int(request.POST.get('refresh_rate', '5')),
                'show_advanced_metrics': request.POST.get('show_advanced_metrics') == 'on',
                'auto_refresh': request.POST.get('auto_refresh') == 'on'
            }
            
            user_profile.save()
            
            logger.info(f"Dashboard settings updated for user: {request.user}")
            messages.success(request, "Settings saved successfully!")
            return redirect('dashboard:settings')
        
        # Get current user profile
        user_profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        context = {
            'user_profile': user_profile,
            'notification_preferences': user_profile.notification_preferences or {},
            'dashboard_preferences': user_profile.dashboard_preferences or {},
            'timestamp': datetime.now().isoformat()
        }
        
        return render(request, 'dashboard/settings.html', context)
        
    except Exception as e:
        logger.error(f"Dashboard settings error: {e}", exc_info=True)
        messages.error(request, f"Settings error: {str(e)}")
        return redirect('dashboard:home')


def dashboard_analytics(request: HttpRequest) -> HttpResponse:
    """
    Dashboard analytics page showing comprehensive trading performance data.
    
    Displays detailed analytics including profit/loss, success rates,
    trading patterns, and performance comparisons.
    """
    try:
        logger.info(f"Dashboard analytics accessed by user: {request.user}")
        
        # Get analytics data (mock implementation)
        analytics_data = {
            'total_trades': 147,
            'successful_trades': 132,
            'success_rate': 89.8,
            'total_profit_usd': 2847.65,
            'average_profit_per_trade': 19.37,
            'best_performing_token': 'UNI',
            'worst_performing_token': 'SUSHI',
            'trading_volume_24h': 15780.00,
            'active_positions': 3,
            'closed_positions': 144
        }
        
        # Get recent trading sessions
        recent_sessions = TradingSession.objects.filter(
            user=request.user
        ).order_by('-created_at')[:10]
        
        # Performance by trading mode
        performance_by_mode = {
            'fast_lane': {
                'trades': 98,
                'success_rate': 92.3,
                'avg_profit': 21.45,
                'total_profit': 2102.10
            },
            'smart_lane': {
                'trades': 49,
                'success_rate': 85.7,
                'avg_profit': 15.22,
                'total_profit': 745.55
            }
        }
        
        context = {
            'analytics_data': analytics_data,
            'recent_sessions': recent_sessions,
            'performance_by_mode': performance_by_mode,
            'timestamp': datetime.now().isoformat()
        }
        
        return render(request, 'dashboard/analytics.html', context)
        
    except Exception as e:
        logger.error(f"Dashboard analytics error: {e}", exc_info=True)
        messages.error(request, f"Analytics error: {str(e)}")
        return redirect('dashboard:home')


# =========================================================================
# CONFIGURATION MANAGEMENT API ENDPOINTS
# =========================================================================

@require_POST
@csrf_exempt
def save_configuration(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to save a new or updated configuration.
    
    Accepts POST requests with configuration data and saves it to the database
    with proper validation and error handling.
    """
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        required_fields = ['name', 'trading_mode']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }, status=400)
        
        # Check for duplicate configuration names
        existing = BotConfiguration.objects.filter(
            user=request.user,
            name=data['name'],
            trading_mode=data['trading_mode'].upper()
        ).first()
        
        if existing and not data.get('update_existing'):
            return JsonResponse({
                'success': False,
                'error': f'Configuration "{data["name"]}" already exists'
            }, status=409)
        
        # Create or update configuration
        if existing and data.get('update_existing'):
            config = existing
        else:
            config = BotConfiguration(user=request.user)
        
        # Set basic fields
        config.name = data['name']
        config.description = data.get('description', '')
        config.trading_mode = data['trading_mode'].upper()
        config.status = BotConfiguration.ConfigStatus.DRAFT
        
        # Set trading parameters
        if 'max_slippage_percent' in data:
            config.max_slippage_percent = Decimal(str(data['max_slippage_percent']))
        if 'max_gas_price_gwei' in data:
            config.max_gas_price_gwei = Decimal(str(data['max_gas_price_gwei']))
        if 'position_size_usd' in data:
            config.position_size_usd = Decimal(str(data['position_size_usd']))
        if 'execution_timeout_seconds' in data:
            config.execution_timeout_seconds = int(data['execution_timeout_seconds'])
        if 'risk_tolerance_level' in data:
            config.risk_tolerance_level = data['risk_tolerance_level']
        if 'analysis_depth' in data:
            config.analysis_depth = data['analysis_depth']
        
        # Set additional settings
        config.additional_settings = data.get('additional_settings', {})
        
        config.save()
        
        logger.info(f"Configuration '{config.name}' saved by user {request.user}")
        
        return JsonResponse({
            'success': True,
            'config_id': config.id,
            'message': f'Configuration "{config.name}" saved successfully'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
        
    except Exception as e:
        logger.error(f"Save configuration error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def load_configuration(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to load a specific configuration by ID.
    
    Returns configuration data for editing or activation.
    """
    try:
        config_id = request.GET.get('config_id')
        if not config_id:
            return JsonResponse({
                'success': False,
                'error': 'Configuration ID required'
            }, status=400)
        
        config = get_object_or_404(BotConfiguration, id=config_id, user=request.user)
        
        config_data = {
            'id': config.id,
            'name': config.name,
            'description': config.description,
            'trading_mode': config.trading_mode,
            'status': config.status,
            'max_slippage_percent': float(config.max_slippage_percent) if config.max_slippage_percent else None,
            'max_gas_price_gwei': float(config.max_gas_price_gwei) if config.max_gas_price_gwei else None,
            'position_size_usd': float(config.position_size_usd) if config.position_size_usd else None,
            'execution_timeout_seconds': config.execution_timeout_seconds,
            'risk_tolerance_level': config.risk_tolerance_level,
            'analysis_depth': config.analysis_depth,
            'additional_settings': config.additional_settings,
            'created_at': config.created_at.isoformat(),
            'updated_at': config.updated_at.isoformat()
        }
        
        return JsonResponse({
            'success': True,
            'configuration': config_data
        })
        
    except Exception as e:
        logger.error(f"Load configuration error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_POST
@csrf_exempt
def delete_configuration(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to delete a configuration by ID.
    
    Safely deletes a configuration after validation.
    """
    try:
        data = json.loads(request.body)
        config_id = data.get('config_id')
        
        if not config_id:
            return JsonResponse({
                'success': False,
                'error': 'Configuration ID required'
            }, status=400)
        
        config = get_object_or_404(BotConfiguration, id=config_id, user=request.user)
        
        # Check if configuration is currently active
        if config.status == BotConfiguration.ConfigStatus.ACTIVE:
            return JsonResponse({
                'success': False,
                'error': 'Cannot delete active configuration'
            }, status=409)
        
        config_name = config.name
        config.delete()
        
        logger.info(f"Configuration '{config_name}' deleted by user {request.user}")
        
        return JsonResponse({
            'success': True,
            'message': f'Configuration "{config_name}" deleted successfully'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
        
    except Exception as e:
        logger.error(f"Delete configuration error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def get_configurations(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to retrieve all user configurations.
    
    Returns paginated list of user's configurations with filtering options.
    """
    try:
        # Get filter parameters
        trading_mode = request.GET.get('trading_mode', '')
        status = request.GET.get('status', '')
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 10))
        
        # Build queryset
        queryset = BotConfiguration.objects.filter(user=request.user)
        
        if trading_mode:
            queryset = queryset.filter(trading_mode=trading_mode.upper())
        if status:
            queryset = queryset.filter(status=status.upper())
        
        # Order by most recent
        queryset = queryset.order_by('-updated_at')
        
        # Apply pagination
        paginator = Paginator(queryset, per_page)
        configurations_page = paginator.get_page(page)
        
        # Serialize configurations
        configurations = []
        for config in configurations_page:
            configurations.append({
                'id': config.id,
                'name': config.name,
                'description': config.description,
                'trading_mode': config.trading_mode,
                'status': config.status,
                'max_slippage_percent': float(config.max_slippage_percent) if config.max_slippage_percent else None,
                'max_gas_price_gwei': float(config.max_gas_price_gwei) if config.max_gas_price_gwei else None,
                'position_size_usd': float(config.position_size_usd) if config.position_size_usd else None,
                'execution_timeout_seconds': config.execution_timeout_seconds,
                'risk_tolerance_level': config.risk_tolerance_level,
                'analysis_depth': config.analysis_depth,
                'created_at': config.created_at.isoformat(),
                'updated_at': config.updated_at.isoformat()
            })
        
        return JsonResponse({
            'success': True,
            'configurations': configurations,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_pages': paginator.num_pages,
                'total_count': paginator.count,
                'has_next': configurations_page.has_next(),
                'has_previous': configurations_page.has_previous()
            }
        })
        
    except Exception as e:
        logger.error(f"Get configurations error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =========================================================================
# SESSION MANAGEMENT API ENDPOINTS
# =========================================================================

@require_POST
@csrf_exempt
def start_session(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to start a new trading session.
    
    Creates and starts a new trading session with the specified configuration.
    """
    try:
        data = json.loads(request.body)
        config_id = data.get('config_id')
        
        if not config_id:
            return JsonResponse({
                'success': False,
                'error': 'Configuration ID required'
            }, status=400)
        
        # Get configuration
        config = get_object_or_404(BotConfiguration, id=config_id, user=request.user)
        
        # Check if there's already an active session
        existing_session = TradingSession.objects.filter(
            user=request.user,
            status='ACTIVE'
        ).first()
        
        if existing_session:
            return JsonResponse({
                'success': False,
                'error': 'Active trading session already exists'
            }, status=409)
        
        # Create new trading session
        session = TradingSession.objects.create(
            user=request.user,
            configuration=config,
            status='ACTIVE'
        )
        
        # Initialize session with engine service
        run_async_in_view(engine_service.start_trading_session(session.id, config))
        
        logger.info(f"Trading session {session.id} started by user {request.user}")
        
        return JsonResponse({
            'success': True,
            'session_id': str(session.id),
            'message': 'Trading session started successfully',
            'config_name': config.name
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
        
    except Exception as e:
        logger.error(f"Start session error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_POST
@csrf_exempt
def stop_session(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to stop an active trading session.
    
    Safely stops the specified trading session and updates its status.
    """
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        
        if not session_id:
            return JsonResponse({
                'success': False,
                'error': 'Session ID required'
            }, status=400)
        
        # Get session
        session = get_object_or_404(TradingSession, id=session_id, user=request.user)
        
        if session.status != 'ACTIVE':
            return JsonResponse({
                'success': False,
                'error': 'Session is not active'
            }, status=409)
        
        # Stop session with engine service
        run_async_in_view(engine_service.stop_trading_session(session.id))
        
        # Update session status
        session.status = 'STOPPED'
        session.save()
        
        logger.info(f"Trading session {session.id} stopped by user {request.user}")
        
        return JsonResponse({
            'success': True,
            'message': 'Trading session stopped successfully'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
        
    except Exception as e:
        logger.error(f"Stop session error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def get_session_status(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to get current trading session status.
    
    Returns information about active trading sessions and their performance.
    """
    try:
        session_id = request.GET.get('session_id')
        
        if session_id:
            # Get specific session
            session = get_object_or_404(TradingSession, id=session_id, user=request.user)
            sessions_data = [serialize_session(session)]
        else:
            # Get all user sessions
            sessions = TradingSession.objects.filter(user=request.user).order_by('-created_at')[:10]
            sessions_data = [serialize_session(session) for session in sessions]
        
        return JsonResponse({
            'success': True,
            'sessions': sessions_data
        })
        
    except Exception as e:
        logger.error(f"Get session status error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def serialize_session(session: TradingSession) -> Dict[str, Any]:
    """
    Serialize a TradingSession object to dictionary.
    
    Args:
        session: TradingSession instance to serialize
        
    Returns:
        Dictionary representation of the session
    """
    return {
        'id': str(session.id),
        'status': session.status,
        'configuration_name': session.configuration.name if session.configuration else 'Unknown',
        'trading_mode': session.configuration.trading_mode if session.configuration else 'UNKNOWN',
        'created_at': session.created_at.isoformat(),
        'updated_at': session.updated_at.isoformat()
    }


# =========================================================================
# PERFORMANCE METRICS API ENDPOINT
# =========================================================================

@require_http_methods(["GET"])
def get_performance_metrics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for comprehensive performance metrics.
    
    Returns current performance metrics including execution times, success rates,
    and trading volume statistics from both Fast Lane and Smart Lane engines.
    """
    try:
        # Initialize engines if needed
        run_async_in_view(ensure_engines_initialized())
        
        # Get metrics from engine service
        metrics = engine_service.get_performance_metrics()
        
        # Add user-specific metrics
        user_metrics = {
            'user_total_trades': TradingSession.objects.filter(user=request.user).count(),
            'user_active_sessions': TradingSession.objects.filter(user=request.user, status='ACTIVE').count(),
            'user_configurations': BotConfiguration.objects.filter(user=request.user).count()
        }
        
        # Combine metrics
        combined_metrics = {**metrics, **user_metrics}
        
        return JsonResponse({
            'success': True,
            'metrics': combined_metrics,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Get performance metrics error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =========================================================================
# SMART LANE SPECIFIC VIEWS
# =========================================================================

@login_required
def smart_lane_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Smart Lane main dashboard view.
    
    Displays Smart Lane specific interface with analysis capabilities,
    configuration options, and real-time metrics.
    """
    try:
        logger.info(f"Smart Lane dashboard accessed by user: {request.user}")
        
        # Initialize engines if needed
        run_async_in_view(ensure_engines_initialized())
        
        # Get engine status and metrics
        engine_status = engine_service.get_engine_status()
        performance_metrics = engine_service.get_performance_metrics()
        
        # Smart Lane specific metrics
        smart_lane_metrics = {
            'analyses_today': performance_metrics.get('smart_lane_analyses_today', 87),
            'success_rate': f"{performance_metrics.get('smart_lane_success_rate', 94.2):.1f}",
            'avg_analysis_time': performance_metrics.get('smart_lane_analysis_time_ms', 2800),
            'risk_adjusted_return': f"{performance_metrics.get('risk_adjusted_return', 10.3):.1f}",
            'confidence_score': performance_metrics.get('avg_confidence_score', 75.8),
            'active_analyses': performance_metrics.get('active_smart_lane_analyses', 3)
        }
        
        # Risk analysis categories
        risk_categories = [
            'Honeypot Detection',
            'Liquidity Analysis', 
            'Social Sentiment',
            'Technical Analysis',
            'Contract Security',
            'Holder Distribution',
            'Market Structure'
        ]
        
        # Get user's Smart Lane configurations
        user_configs = BotConfiguration.objects.filter(
            user=request.user,
            trading_mode='SMART_LANE'
        ).order_by('-updated_at')[:5]
        
        # Recent analysis results (mock data for development)
        recent_analyses = request.session.get('smart_lane_analyses', [])
        
        context = {
            'page_title': 'Smart Lane Intelligence',
            'smart_lane_metrics': smart_lane_metrics,
            'risk_categories': risk_categories,
            'user_configurations': user_configs,
            'recent_analyses': recent_analyses,
            'smart_lane_enabled': getattr(settings, 'SMART_LANE_ENABLED', True),
            'smart_lane_available': engine_status.get('smart_lane_available', False),
            'analysis_depth': 'COMPREHENSIVE',
            'thought_log_enabled': True,
            'is_mock_mode': engine_status.get('_mock', True),
            'timestamp': datetime.now().isoformat()
        }
        
        return render(request, 'dashboard/smart_lane_dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Smart Lane dashboard error: {e}", exc_info=True)
        messages.error(request, f"Smart Lane dashboard error: {str(e)}")
        
        # Fallback context
        context = {
            'page_title': 'Smart Lane Intelligence',
            'smart_lane_metrics': {},
            'risk_categories': [],
            'user_configurations': [],
            'recent_analyses': [],
            'smart_lane_enabled': False,
            'smart_lane_available': False,
            'error': str(e)
        }
        
        return render(request, 'dashboard/smart_lane_dashboard.html', context)


@login_required
def smart_lane_demo(request: HttpRequest) -> HttpResponse:
    """
    Smart Lane demo page showing analysis capabilities.
    
    Demonstrates Smart Lane analysis features with mock data and
    interactive examples for user education.
    """
    try:
        logger.info(f"Smart Lane demo accessed by user: {request.user}")
        
        # Get recent analyses from session
        recent_analyses = request.session.get('smart_lane_analyses', [])
        
        # Demo analysis data for display
        demo_analysis = {
            'token_address': '0x1234...5678',
            'token_symbol': 'DEMO',
            'risk_score': 0.35,
            'confidence': 75,
            'action': 'BUY',
            'position_size': 5.0,
            'stop_loss': 10.0,
            'take_profits': [15.0, 25.0, 40.0],
            'analysis_time': 325,
            'timestamp': timezone.now().isoformat()
        }
        
        context = {
            'page_title': 'Smart Lane Demo',
            'demo_analysis': demo_analysis,
            'recent_analyses': recent_analyses,
            'smart_lane_enabled': True,
            'thought_log_enabled': True,
            'timestamp': datetime.now().isoformat()
        }
        
        return render(request, 'dashboard/smart_lane_demo.html', context)
        
    except Exception as e:
        logger.error(f"Smart Lane demo error: {e}", exc_info=True)
        messages.error(request, f"Smart Lane demo error: {str(e)}")
        
        context = {
            'page_title': 'Smart Lane Demo',
            'demo_analysis': None,
            'recent_analyses': [],
            'smart_lane_enabled': False,
            'error': str(e)
        }
        
        return render(request, 'dashboard/smart_lane_demo.html', context)


@login_required  
def smart_lane_config(request: HttpRequest) -> HttpResponse:
    """
    Smart Lane configuration page.
    
    Provides configuration interface for Smart Lane analysis parameters,
    risk tolerance, and analysis depth settings.
    """
    try:
        logger.info(f"Smart Lane config accessed by user: {request.user}")
        
        # Handle configuration form submission
        if request.method == 'POST':
            # Handle basic configuration without form
            config_data = {
                'analysis_depth': request.POST.get('analysis_depth', 'COMPREHENSIVE'),
                'risk_tolerance': request.POST.get('risk_tolerance', 'MEDIUM'),
                'ai_thought_log': request.POST.get('ai_thought_log') == 'on',
                'dynamic_sizing': request.POST.get('dynamic_sizing') == 'on',
                'confidence_threshold': float(request.POST.get('confidence_threshold', '0.7')),
                'max_analysis_time': float(request.POST.get('max_analysis_time', '5.0'))
            }
            request.session['smart_lane_config'] = config_data
            logger.info(f"Smart Lane configuration saved for user {request.user}")
            messages.success(request, 'Smart Lane configuration saved!')
            return redirect('dashboard:smart_lane_dashboard')
        
        # Load existing configuration
        config_data = request.session.get('smart_lane_config', {})
        
        # Default configuration options
        default_config = {
            'analysis_depth': 'COMPREHENSIVE',
            'risk_tolerance': 'MEDIUM',
            'ai_thought_log': True,
            'dynamic_sizing': True,
            'max_analysis_time': 5.0,
            'confidence_threshold': 0.7
        }
        
        # Merge with existing config
        current_config = {**default_config, **config_data}
        
        context = {
            'page_title': 'Smart Lane Configuration',
            'current_config': current_config,
            'analysis_depth_choices': [
                ('BASIC', 'Basic Analysis'),
                ('STANDARD', 'Standard Analysis'),
                ('COMPREHENSIVE', 'Comprehensive Analysis'),
                ('DEEP', 'Deep Analysis')
            ],
            'risk_tolerance_choices': [
                ('CONSERVATIVE', 'Conservative'),
                ('MODERATE', 'Moderate'),
                ('AGGRESSIVE', 'Aggressive')
            ],
            'timestamp': datetime.now().isoformat()
        }
        
        return render(request, 'dashboard/smart_lane_config.html', context)
        
    except Exception as e:
        logger.error(f"Smart Lane config error: {e}", exc_info=True)
        messages.error(request, f"Smart Lane configuration error: {str(e)}")
        return redirect('dashboard:smart_lane_dashboard')


@login_required
def smart_lane_analyze(request: HttpRequest) -> HttpResponse:
    """
    Smart Lane analysis request page.
    
    Provides interface for requesting Smart Lane token analysis with
    custom parameters and thought log options.
    """
    try:
        logger.info(f"Smart Lane analyze page accessed by user: {request.user}")
        
        # Handle analysis request
        if request.method == 'POST':
            token_address = request.POST.get('token_address', '').strip()
            include_thought_log = request.POST.get('include_thought_log') == 'on'
            
            if token_address:
                # Basic validation
                if token_address.startswith('0x') and len(token_address) == 42:
                    request.session['last_analysis_request'] = {
                        'token_address': token_address,
                        'include_thought_log': include_thought_log,
                        'timestamp': datetime.now().isoformat()
                    }
                    logger.info(f"Analysis requested for {token_address[:10]}... by user {request.user}")
                    messages.success(request, f'Analysis requested for {token_address[:10]}...')
                    return redirect('dashboard:smart_lane_demo')
                else:
                    messages.error(request, 'Invalid token address format')
            else:
                messages.error(request, 'Token address is required')
        
        context = {
            'page_title': 'Smart Lane Analysis',
            'last_request': request.session.get('last_analysis_request'),
            'timestamp': datetime.now().isoformat()
        }
        
        return render(request, 'dashboard/smart_lane_analyze.html', context)
        
    except Exception as e:
        logger.error(f"Smart Lane analyze error: {e}", exc_info=True)
        messages.error(request, f"Smart Lane analyze error: {str(e)}")
        return redirect('dashboard:smart_lane_dashboard')


@require_POST
@csrf_exempt
def api_smart_lane_analyze(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for Smart Lane token analysis.
    
    Accepts POST requests with token address and performs comprehensive
    analysis using the Smart Lane pipeline.
    """
    try:
        # Parse request data
        data = json.loads(request.body)
        token_address = data.get('token_address', '').strip()
        
        if not token_address:
            return JsonResponse({
                'success': False,
                'error': 'Token address is required',
                'timestamp': datetime.now().isoformat()
            }, status=400)
        
        # Validate token address format
        if not token_address.startswith('0x') or len(token_address) != 42:
            return JsonResponse({
                'success': False,
                'error': 'Invalid token address format',
                'timestamp': datetime.now().isoformat()
            }, status=400)
        
        logger.info(f"Smart Lane analysis requested for token: {token_address}")
        
        # Initialize Smart Lane if needed
        run_async_in_view(ensure_engines_initialized())
        
        # Prepare analysis context from request data
        context = {
            'symbol': data.get('symbol', ''),
            'name': data.get('name', ''),
            'current_price': data.get('current_price'),
            'market_cap': data.get('market_cap'),
            'volume_24h': data.get('volume_24h'),
            'liquidity_usd': data.get('liquidity_usd')
        }
        
        # Remove None values from context
        context = {k: v for k, v in context.items() if v is not None}
        
        # Perform Smart Lane analysis
        analysis_result = run_async_in_view(
            engine_service.analyze_token_smart_lane(token_address, context)
        )
        
        if analysis_result:
            # Store analysis in session for user tracking
            analyses = request.session.get('smart_lane_analyses', [])
            analyses.insert(0, analysis_result)
            request.session['smart_lane_analyses'] = analyses[:10]  # Keep last 10
            
            logger.info(f"Smart Lane analysis completed for token: {token_address}")
            
            return JsonResponse({
                'success': True,
                'data': analysis_result,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Analysis failed - please try again',
                'timestamp': datetime.now().isoformat()
            }, status=500)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON payload',
            'timestamp': datetime.now().isoformat()
        }, status=400)
        
    except Exception as e:
        logger.error(f"Smart Lane analysis API error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, status=500)


@login_required
def api_get_thought_log(request: HttpRequest, analysis_id: str) -> JsonResponse:
    """
    API endpoint to get thought log for a specific analysis.
    
    Returns detailed reasoning and decision-making process for
    a Smart Lane analysis result.
    """
    try:
        logger.info(f"Thought log requested for analysis: {analysis_id}")
        
        # Mock thought log for demo (replace with actual logic)
        thought_log = {
            'analysis_id': analysis_id,
            'executive_summary': 'Based on comprehensive analysis, this token shows moderate risk with good upside potential.',
            'key_opportunities': [
                'Strong technical indicators suggest upward momentum',
                'Liquidity depth supports large trades',
                'Community sentiment is positive'
            ],
            'key_risks': [
                'High holder concentration in top wallets',
                'Contract has modifiable tax functions',
                'Limited trading history'
            ],
            'confidence_score': 75,
            'reasoning_steps': [
                {
                    'category': 'RISK_ASSESSMENT',
                    'title': 'Initial Risk Evaluation',
                    'analysis': 'Scanning for honeypot indicators and contract vulnerabilities...',
                    'confidence_impact': 0.8
                },
                {
                    'category': 'TECHNICAL_ANALYSIS',
                    'title': 'Chart Pattern Recognition',
                    'analysis': 'Analyzing price action across multiple timeframes...',
                    'confidence_impact': 0.7
                },
                {
                    'category': 'LIQUIDITY_ANALYSIS',
                    'title': 'Market Depth Assessment',
                    'analysis': 'Evaluating available liquidity and potential slippage...',
                    'confidence_impact': 0.9
                }
            ],
            'timestamp': datetime.now().isoformat()
        }
        
        return JsonResponse(thought_log)
        
    except Exception as e:
        logger.error(f"Thought log API error: {e}", exc_info=True)
        return JsonResponse({
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, status=500)


# =========================================================================
# ADDITIONAL MISSING VIEWS
# =========================================================================

def configuration_summary(request: HttpRequest, config_id: int) -> HttpResponse:
    """
    Display configuration summary with enhanced dual-engine support.
    
    Shows detailed configuration information for both Fast Lane and Smart Lane
    configurations with appropriate mode-specific details.
    """
    try:
        # Get configuration object
        config = get_object_or_404(BotConfiguration, id=config_id, user=request.user)
        
        logger.info(f"Configuration summary viewed: {config.name} ({config.trading_mode})")
        
        # Get current engine status
        engine_status = engine_service.get_engine_status()
        
        # Prepare mode-specific information
        mode_info = {
            'is_fast_lane': config.trading_mode == 'FAST_LANE',
            'is_smart_lane': config.trading_mode == 'SMART_LANE',
            'mode_available': True
        }
        
        if config.trading_mode == 'FAST_LANE':
            mode_info['mode_available'] = engine_status.get('fast_lane_available', False)
        elif config.trading_mode == 'SMART_LANE':
            mode_info['mode_available'] = engine_status.get('smart_lane_available', False)
        
        # Parse additional settings
        additional_settings = config.additional_settings or {}
        
        context = {
            'config': config,
            'mode_info': mode_info,
            'additional_settings': additional_settings,
            'engine_status': engine_status,
            'can_activate': mode_info['mode_available'] and config.status == BotConfiguration.ConfigStatus.DRAFT,
            'timestamp': datetime.now().isoformat()
        }
        
        return render(request, 'dashboard/configuration_summary.html', context)
        
    except Exception as e:
        logger.error(f"Configuration summary error: {e}", exc_info=True)
        messages.error(request, f"Error loading configuration: {str(e)}")
        return redirect('dashboard:home')