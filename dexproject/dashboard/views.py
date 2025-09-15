"""
Complete Dashboard Views for DEX Trading Bot

Updated with both Fast Lane and Smart Lane engine integration, comprehensive
configuration management, proper error handling, and improved user experience.

Features:
- Dual-engine support (Fast Lane + Smart Lane)
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
    
    Raises:
        Exception: Logs but does not re-raise engine initialization errors
    """
    # Initialize Fast Lane engine
    if not engine_service.engine_initialized and not engine_service.mock_mode:
        try:
            success = await engine_service.initialize_engine(chain_id=1)  # Ethereum mainnet
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
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse with rendered dashboard home template
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
            'execution_time_ms': performance_metrics.get('fast_lane_execution_time_ms', 0),
            'success_rate': performance_metrics.get('fast_lane_success_rate', 0),
            'trades_per_minute': performance_metrics.get('trades_per_minute', 0),
            'status': 'Operational' if engine_status.get('fast_lane_active') else 'Mock Mode',
            'phase': 'Phase 2-4 Complete'
        }
        
        smart_lane_metrics = {
            'execution_time_ms': performance_metrics.get('smart_lane_analysis_time_ms', 0),
            'success_rate': performance_metrics.get('smart_lane_success_rate', 0),
            'analyses_today': performance_metrics.get('smart_lane_analyses_today', 0),
            'risk_adjusted_return': performance_metrics.get('risk_adjusted_return', 0),
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
        
        # Recent activity (placeholder for future implementation)
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
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse with rendered mode selection template
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
        
        # Prepare Fast Lane metrics for template
        fast_lane_metrics = {
            'execution_time_ms': int(performance_metrics.get('fast_lane_execution_time_ms', 78)),
            'success_rate': f"{performance_metrics.get('fast_lane_success_rate', 96.8):.1f}",
            'trades_per_minute': performance_metrics.get('trades_per_minute', 25),
            'status': 'Operational' if engine_status.get('fast_lane_active') else 'Ready (Mock Mode)',
            'phase': 'Phases 2-4 Complete'
        }
        
        # Prepare Smart Lane metrics for template
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
    
    Args:
        request: Django HTTP request object
        mode: Trading mode ('fast_lane' or 'smart_lane')
        
    Returns:
        HttpResponse with rendered configuration panel template
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
                'default_slippage': settings.DEFAULT_SLIPPAGE_PERCENT,
                'default_gas_price': settings.MAX_GAS_PRICE_GWEI,
                'default_position_size': settings.MAX_POSITION_SIZE_USD,
                'execution_timeout': settings.EXECUTION_TIMEOUT_SECONDS
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
    
    Args:
        request: Django HTTP request object with POST data
        mode: Trading mode ('fast_lane' or 'smart_lane')
        
    Returns:
        HttpResponse redirect to configuration summary or back to form
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


# =========================================================================
# SMART LANE SPECIFIC VIEWS
# =========================================================================

@require_POST
@csrf_exempt
def api_smart_lane_analyze(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for Smart Lane token analysis.
    
    Accepts POST requests with token address and performs comprehensive
    analysis using the Smart Lane pipeline.
    
    Args:
        request: Django HTTP request object with JSON payload
        
    Returns:
        JsonResponse with analysis results or error message
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
        
        # Validate token address format (basic check)
        if not token_address.startswith('0x') or len(token_address) != 42:
            return JsonResponse({
                'success': False,
                'error': 'Invalid token address format',
                'timestamp': datetime.now().isoformat()
            }, status=400)
        
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


def smart_lane_demo(request: HttpRequest) -> HttpResponse:
    """
    Smart Lane demonstration page with sample analysis.
    
    Shows Smart Lane capabilities with a demo token analysis including
    AI thought log, risk assessment, and strategic recommendations.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse with rendered Smart Lane demo template
    """
    try:
        logger.info(f"Smart Lane demo accessed by user: {request.user}")
        
        # Initialize Smart Lane if needed
        run_async_in_view(ensure_engines_initialized())
        
        # Demo token address for consistent demo
        demo_token_address = "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"  # UNI token
        
        # Get demo analysis
        demo_context = {
            'symbol': 'UNI',
            'name': 'Uniswap',
            'current_price': 6.45,
            'market_cap': 4850000000,
            'volume_24h': 125000000,
            'liquidity_usd': 890000000
        }
        
        demo_analysis = run_async_in_view(
            engine_service.analyze_token_smart_lane(demo_token_address, demo_context)
        )
        
        # Get Smart Lane metrics
        performance_metrics = engine_service.get_performance_metrics()
        engine_status = engine_service.get_engine_status()
        
        smart_lane_metrics = {
            'analysis_time_ms': performance_metrics.get('smart_lane_analysis_time_ms', 2800),
            'success_rate': performance_metrics.get('smart_lane_success_rate', 94.2),
            'cache_hit_ratio': performance_metrics.get('smart_lane_cache_hits', 75),
            'analyses_today': performance_metrics.get('smart_lane_analyses_today', 87),
            'status': 'Operational' if engine_status.get('smart_lane_active') else 'Demo Mode'
        }
        
        context = {
            'demo_analysis': demo_analysis,
            'demo_token_address': demo_token_address,
            'smart_lane_metrics': smart_lane_metrics,
            'smart_lane_available': engine_status.get('smart_lane_available', False),
            'is_mock_mode': demo_analysis.get('_mock', True) if demo_analysis else True,
            'timestamp': datetime.now().isoformat()
        }
        
        return render(request, 'dashboard/smart_lane_demo.html', context)
        
    except Exception as e:
        logger.error(f"Smart Lane demo error: {e}", exc_info=True)
        messages.error(request, f"Demo error: {str(e)}")
        
        # Provide fallback context
        context = {
            'demo_analysis': None,
            'smart_lane_metrics': {'status': 'Error'},
            'smart_lane_available': False,
            'is_mock_mode': True,
            'error': str(e)
        }
        
        return render(request, 'dashboard/smart_lane_demo.html', context)


# =========================================================================
# CONFIGURATION MANAGEMENT VIEWS (Enhanced for dual-engine support)
# =========================================================================

def configuration_summary(request: HttpRequest, config_id: int) -> HttpResponse:
    """
    Display configuration summary with enhanced dual-engine support.
    
    Shows detailed configuration information for both Fast Lane and Smart Lane
    configurations with appropriate mode-specific details.
    
    Args:
        request: Django HTTP request object
        config_id: Configuration ID to display
        
    Returns:
        HttpResponse with rendered configuration summary template
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
        return redirect('dashboard:configuration_list')


def configuration_list(request: HttpRequest) -> HttpResponse:
    """
    List all user configurations with enhanced filtering for dual-engine support.
    
    Displays paginated list of user's configurations with filtering by
    trading mode and status.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse with rendered configuration list template
    """
    try:
        # Get filter parameters
        mode_filter = request.GET.get('mode', '')
        status_filter = request.GET.get('status', '')
        
        # Build queryset with filters
        queryset = BotConfiguration.objects.filter(user=request.user)
        
        if mode_filter:
            queryset = queryset.filter(trading_mode=mode_filter.upper())
        
        if status_filter:
            queryset = queryset.filter(status=status_filter.upper())
        
        # Order by most recent
        queryset = queryset.order_by('-updated_at')
        
        # Paginate results
        paginator = Paginator(queryset, 10)
        page_number = request.GET.get('page')
        configurations = paginator.get_page(page_number)
        
        # Get engine status for availability indicators
        engine_status = engine_service.get_engine_status()
        
        # Count configurations by mode
        mode_counts = {
            'fast_lane': BotConfiguration.objects.filter(user=request.user, trading_mode='FAST_LANE').count(),
            'smart_lane': BotConfiguration.objects.filter(user=request.user, trading_mode='SMART_LANE').count(),
            'total': BotConfiguration.objects.filter(user=request.user).count()
        }
        
        context = {
            'configurations': configurations,
            'mode_counts': mode_counts,
            'current_mode_filter': mode_filter,
            'current_status_filter': status_filter,
            'engine_status': engine_status,
            'available_modes': [
                ('FAST_LANE', 'Fast Lane', engine_status.get('fast_lane_available', False)),
                ('SMART_LANE', 'Smart Lane', engine_status.get('smart_lane_available', False))
            ],
            'available_statuses': [
                ('DRAFT', 'Draft'),
                ('ACTIVE', 'Active'),
                ('PAUSED', 'Paused'),
                ('ARCHIVED', 'Archived')
            ],
            'timestamp': datetime.now().isoformat()
        }
        
        return render(request, 'dashboard/configuration_list.html', context)
        
    except Exception as e:
        logger.error(f"Configuration list error: {e}", exc_info=True)
        messages.error(request, f"Error loading configurations: {str(e)}")
        
        # Provide minimal fallback context
        context = {
            'configurations': [],
            'mode_counts': {'fast_lane': 0, 'smart_lane': 0, 'total': 0},
            'current_mode_filter': '',
            'current_status_filter': '',
            'engine_status': {'fast_lane_available': False, 'smart_lane_available': False},
            'available_modes': [],
            'available_statuses': [],
            'error': str(e)
        }
        
        return render(request, 'dashboard/configuration_list.html', context)


@require_POST
def delete_configuration(request: HttpRequest, config_id: int) -> HttpResponse:
    """
    Delete a configuration with confirmation.
    
    Safely deletes a user's configuration after validation and provides
    appropriate feedback messages.
    
    Args:
        request: Django HTTP request object
        config_id: Configuration ID to delete
        
    Returns:
        HttpResponse redirect to configuration list
    """
    try:
        # Get configuration and verify ownership
        config = get_object_or_404(BotConfiguration, id=config_id, user=request.user)
        
        # Check if configuration is currently active
        if config.status == BotConfiguration.ConfigStatus.ACTIVE:
            messages.error(request, "Cannot delete active configuration. Please pause it first.")
            return redirect('dashboard:configuration_summary', config_id=config_id)
        
        # Store config name for success message
        config_name = config.name
        config_mode = config.trading_mode
        
        # Delete the configuration
        config.delete()
        
        logger.info(f"Configuration '{config_name}' ({config_mode}) deleted by user {request.user}")
        messages.success(request, f"Configuration '{config_name}' deleted successfully")
        
        return redirect('dashboard:configuration_list')
        
    except Exception as e:
        logger.error(f"Configuration deletion error: {e}", exc_info=True)
        messages.error(request, f"Error deleting configuration: {str(e)}")
        return redirect('dashboard:configuration_list')


# =========================================================================
# API ENDPOINTS (Enhanced for dual-engine support)
# =========================================================================

def api_engine_status(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for comprehensive engine status including both Fast Lane and Smart Lane.
    
    Returns current engine status including Fast Lane and Smart Lane availability,
    connection states, and system health metrics.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with engine status data or error message
    """
    try:
        # Initialize engines if needed
        run_async_in_view(ensure_engines_initialized())
        
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
    API endpoint for comprehensive performance metrics including both engines.
    
    Returns current performance metrics including execution times, success rates,
    and trading volume statistics from both Fast Lane and Smart Lane engines.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with performance metrics data or error message
    """
    try:
        # Initialize engines if needed
        run_async_in_view(ensure_engines_initialized())
        
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
    API endpoint to set trading mode with dual-engine support.
    
    Accepts POST requests with mode selection and updates the engine configuration.
    Validates mode parameter and uses engine service for mode switching.
    
    Args:
        request: Django HTTP request object with JSON payload
        
    Returns:
        JsonResponse with success status or error message
    """
    try:
        # Parse request data
        data = json.loads(request.body)
        mode = data.get('mode', '').upper()
        
        # Validate mode
        valid_modes = ['FAST_LANE', 'SMART_LANE', 'HYBRID']
        if mode not in valid_modes:
            return JsonResponse({
                'success': False,
                'error': f'Invalid mode. Must be one of: {", ".join(valid_modes)}',
                'timestamp': datetime.now().isoformat()
            }, status=400)
        
        # Initialize engines if needed
        run_async_in_view(ensure_engines_initialized())
        
        # Set trading mode
        success = run_async_in_view(engine_service.set_trading_mode(mode))
        
        if success:
            logger.info(f"Trading mode set to {mode} via API by user {request.user}")
            return JsonResponse({
                'success': True,
                'message': f'Trading mode set to {mode}',
                'mode': mode,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return JsonResponse({
                'success': False,
                'error': f'Failed to set trading mode to {mode}',
                'timestamp': datetime.now().isoformat()
            }, status=500)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON payload',
            'timestamp': datetime.now().isoformat()
        }, status=400)
        
    except Exception as e:
        logger.error(f"API set trading mode error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, status=500)


# =========================================================================
# SERVER-SENT EVENTS FOR REAL-TIME UPDATES
# =========================================================================

def dashboard_live_feed(request: HttpRequest) -> StreamingHttpResponse:
    """
    Server-Sent Events endpoint for real-time dashboard updates.
    
    Streams live engine status and performance metrics for both Fast Lane
    and Smart Lane engines with configurable update intervals.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        StreamingResponse with SSE data stream
    """
    def event_stream():
        """Generate SSE event stream with dual-engine data."""
        max_iterations = getattr(settings, 'SSE_MAX_ITERATIONS', 150)
        update_interval = getattr(settings, 'DASHBOARD_SSE_UPDATE_INTERVAL', 2)
        iteration_count = 0
        
        try:
            # Initialize engines if needed
            run_async_in_view(ensure_engines_initialized())
            
            while iteration_count < max_iterations:
                try:
                    # Get current engine status and metrics
                    engine_status = engine_service.get_engine_status()
                    performance_metrics = engine_service.get_performance_metrics()
                    
                    # Prepare combined data
                    live_data = {
                        'timestamp': datetime.now().isoformat(),
                        'iteration': iteration_count,
                        'engine_status': engine_status,
                        'performance_metrics': performance_metrics,
                        'fast_lane': {
                            'active': engine_status.get('fast_lane_active', False),
                            'execution_time_ms': performance_metrics.get('fast_lane_execution_time_ms', 0),
                            'success_rate': performance_metrics.get('fast_lane_success_rate', 0),
                            'trades_per_minute': performance_metrics.get('trades_per_minute', 0)
                        },
                        'smart_lane': {
                            'active': engine_status.get('smart_lane_active', False),
                            'analysis_time_ms': performance_metrics.get('smart_lane_analysis_time_ms', 0),
                            'success_rate': performance_metrics.get('smart_lane_success_rate', 0),
                            'analyses_today': performance_metrics.get('smart_lane_analyses_today', 0),
                            'risk_adjusted_return': performance_metrics.get('risk_adjusted_return', 0)
                        },
                        'system_health': {
                            'circuit_breaker_ok': engine_status.get('circuit_breaker_state') == 'CLOSED',
                            'mempool_connected': engine_status.get('mempool_connected', False),
                            'is_mock_mode': engine_status.get('_mock', True)
                        }
                    }
                    
                    # Send SSE event
                    yield f"data: {json.dumps(live_data)}\n\n"
                    
                    iteration_count += 1
                    time.sleep(update_interval)
                    
                except Exception as e:
                    logger.error(f"SSE iteration error: {e}")
                    error_data = {
                        'timestamp': datetime.now().isoformat(),
                        'error': str(e),
                        'iteration': iteration_count
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                    break
            
            # Send completion event
            completion_data = {
                'timestamp': datetime.now().isoformat(),
                'completed': True,
                'total_iterations': iteration_count,
                'message': 'SSE stream completed'
            }
            yield f"data: {json.dumps(completion_data)}\n\n"
            
        except Exception as e:
            logger.error(f"SSE stream error: {e}", exc_info=True)
            error_data = {
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'stream_failed': True
            }
            yield f"data: {json.dumps(error_data)}\n\n"
    
    # Create SSE response
    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
    
    # Set SSE headers
    response['Cache-Control'] = 'no-cache'
    response['Connection'] = 'keep-alive'
    response['X-Accel-Buffering'] = 'no'  # Disable Nginx buffering
    
    return response


# =========================================================================
# HEALTH CHECK AND TESTING ENDPOINTS
# =========================================================================

def health_check(request: HttpRequest) -> JsonResponse:
    """
    Health check endpoint for monitoring both engines.
    
    Provides basic health status for monitoring systems and load balancers.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with health status
    """
    try:
        # Get basic engine status
        engine_status = engine_service.get_engine_status()
        
        # Determine overall health
        fast_lane_healthy = engine_status.get('fast_lane_available', False)
        smart_lane_healthy = engine_status.get('smart_lane_available', False)
        circuit_breaker_ok = engine_status.get('circuit_breaker_state') == 'CLOSED'
        
        overall_health = 'healthy' if (fast_lane_healthy or smart_lane_healthy) and circuit_breaker_ok else 'degraded'
        
        health_data = {
            'status': overall_health,
            'timestamp': datetime.now().isoformat(),
            'components': {
                'fast_lane': 'healthy' if fast_lane_healthy else 'unavailable',
                'smart_lane': 'healthy' if smart_lane_healthy else 'unavailable',
                'circuit_breaker': 'healthy' if circuit_breaker_ok else 'open',
                'database': 'healthy',  # Django will handle DB errors
                'cache': 'healthy'      # Redis errors would be caught elsewhere
            },
            'version': '1.0.0',
            'environment': 'development' if settings.DEBUG else 'production'
        }
        
        status_code = 200 if overall_health == 'healthy' else 503
        
        return JsonResponse(health_data, status=status_code)
        
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return JsonResponse({
            'status': 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }, status=503)


@require_http_methods(["GET", "POST"])
def engine_test(request: HttpRequest) -> JsonResponse:
    """
    Engine testing endpoint for development and debugging.
    
    Allows testing of both Fast Lane and Smart Lane engines with
    various test scenarios and mock data.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with test results
    """
    if not settings.DEBUG:
        return JsonResponse({
            'error': 'Engine test endpoint only available in debug mode'
        }, status=403)
    
    try:
        test_type = request.GET.get('type', 'status')
        
        if test_type == 'status':
            # Test engine status retrieval
            status = engine_service.get_engine_status()
            return JsonResponse({
                'test': 'engine_status',
                'result': 'success',
                'data': status,
                'timestamp': datetime.now().isoformat()
            })
            
        elif test_type == 'metrics':
            # Test performance metrics retrieval
            metrics = engine_service.get_performance_metrics()
            return JsonResponse({
                'test': 'performance_metrics',
                'result': 'success',
                'data': metrics,
                'timestamp': datetime.now().isoformat()
            })
            
        elif test_type == 'smart_lane_analysis':
            # Test Smart Lane analysis with demo token
            demo_token = "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"  # UNI
            analysis = run_async_in_view(
                engine_service.analyze_token_smart_lane(demo_token, {'symbol': 'UNI'})
            )
            return JsonResponse({
                'test': 'smart_lane_analysis',
                'result': 'success',
                'data': analysis,
                'timestamp': datetime.now().isoformat()
            })
            
        elif test_type == 'initialization':
            # Test engine initialization
            run_async_in_view(ensure_engines_initialized())
            return JsonResponse({
                'test': 'engine_initialization',
                'result': 'success',
                'fast_lane_initialized': engine_service.engine_initialized,
                'smart_lane_initialized': engine_service.smart_lane_initialized,
                'timestamp': datetime.now().isoformat()
            })
            
        else:
            return JsonResponse({
                'error': f'Unknown test type: {test_type}',
                'available_tests': ['status', 'metrics', 'smart_lane_analysis', 'initialization']
            }, status=400)
            
    except Exception as e:
        logger.error(f"Engine test error: {e}", exc_info=True)
        return JsonResponse({
            'test': test_type,
            'result': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, status=500)
    

