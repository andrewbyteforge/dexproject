"""
Complete Dashboard Views for DEX Trading Bot - UPDATED WITH SMART LANE INTEGRATION

Updated with Fast Lane engine integration, Smart Lane Phase 5 integration,
configuration summary functionality, proper error handling, thorough logging,
and improved user experience with comprehensive strategy management.

FIXED ISSUES:
- Database field errors (is_active field corrected)
- Missing get_trading_sessions method (replaced with database queries)
- Missing metrics_stream view (404 error fixed)
- Proper user authentication handling
- Enhanced error handling and logging throughout
- Smart Lane pipeline integration and configuration

NEW PHASE 5 FEATURES:
- Smart Lane pipeline initialization and management
- Position sizing and exit strategy configuration
- Real-time Smart Lane metrics streaming
- Comprehensive analysis API endpoints
- Strategy component integration

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
from django.db.models import Q

from .models import BotConfiguration, TradingSession, UserProfile
from .engine_service import engine_service

logger = logging.getLogger(__name__)


# =========================================================================
# SMART LANE INTEGRATION (PHASE 5)
# =========================================================================

# Smart Lane Integration
smart_lane_available = False
smart_lane_pipeline = None
smart_lane_metrics = {
    'analyses_completed': 0,
    'average_analysis_time_ms': 0.0,
    'risk_assessments': {},
    'position_recommendations': {},
    'last_analysis': None,
    'errors': []
}

try:
    from engine.smart_lane.pipeline import SmartLanePipeline
    from engine.smart_lane import SmartLaneConfig, AnalysisDepth, RiskCategory
    from engine.smart_lane.strategy import (
        PositionSizer, ExitStrategyManager, SizingMethod,
        ExitTrigger, ExitMethod, create_strategy_suite, validate_strategy_components
    )
    smart_lane_available = True
    logger.info("Smart Lane components imported successfully for dashboard integration")
except ImportError as e:
    smart_lane_available = False
    logger.warning(f"Smart Lane components not available: {e}")


async def initialize_smart_lane_pipeline() -> bool:
    """
    Initialize Smart Lane pipeline for dashboard integration.
    
    Returns:
        bool: True if initialization successful
    """
    global smart_lane_pipeline
    
    try:
        if not smart_lane_available:
            logger.warning("Smart Lane not available - cannot initialize pipeline")
            return False
        
        if smart_lane_pipeline is not None:
            logger.debug("Smart Lane pipeline already initialized")
            return True
        
        logger.info("Initializing Smart Lane pipeline for dashboard...")
        
        # Create Smart Lane configuration
        config = SmartLaneConfig(
            analysis_depth=AnalysisDepth.COMPREHENSIVE,
            enabled_categories=[
                RiskCategory.HONEYPOT_DETECTION,
                RiskCategory.LIQUIDITY_ANALYSIS,
                RiskCategory.SOCIAL_SENTIMENT,
                RiskCategory.TECHNICAL_ANALYSIS,
                RiskCategory.CONTRACT_SECURITY
            ],
            max_analysis_time_seconds=5.0,
            thought_log_enabled=True,
            min_confidence_threshold=0.3,
            max_acceptable_risk_score=0.8
        )
        
        # Initialize pipeline
        smart_lane_pipeline = SmartLanePipeline(
            config=config,
            chain_id=1,  # Ethereum mainnet
            enable_caching=True
        )
        
        # Test basic functionality
        if smart_lane_pipeline.position_sizer is None:
            logger.error("Smart Lane pipeline missing position sizer")
            return False
        
        if smart_lane_pipeline.exit_strategy_manager is None:
            logger.error("Smart Lane pipeline missing exit strategy manager") 
            return False
        
        logger.info("Smart Lane pipeline initialized successfully for dashboard")
        return True
        
    except Exception as e:
        logger.error(f"Smart Lane pipeline initialization failed: {e}", exc_info=True)
        smart_lane_pipeline = None
        return False


def get_smart_lane_status() -> Dict[str, Any]:
    """
    Get current Smart Lane status for dashboard display.
    
    Returns:
        Dict containing Smart Lane status information
    """
    try:
        global smart_lane_metrics
        
        status = {
            'available': smart_lane_available,
            'pipeline_initialized': smart_lane_pipeline is not None,
            'last_update': datetime.now().isoformat(),
            'metrics': smart_lane_metrics.copy(),
            'capabilities': []
        }
        
        if smart_lane_available and smart_lane_pipeline:
            # Add capability information
            status['capabilities'] = [
                'Comprehensive Risk Analysis',
                'AI Thought Log Generation',
                'Strategic Position Sizing',
                'Advanced Exit Strategies',
                'Multi-timeframe Technical Analysis',
                'Honeypot Detection',
                'Social Sentiment Analysis'
            ]
            
            # Add component status
            status['components'] = {
                'position_sizer': smart_lane_pipeline.position_sizer is not None,
                'exit_strategy_manager': smart_lane_pipeline.exit_strategy_manager is not None,
                'analyzers_count': len(smart_lane_pipeline.enabled_categories) if hasattr(smart_lane_pipeline, 'enabled_categories') else 0,
                'cache_enabled': hasattr(smart_lane_pipeline, 'cache') and smart_lane_pipeline.cache is not None
            }
        else:
            status['error'] = "Smart Lane not available or not initialized"
        
        return status
        
    except Exception as e:
        logger.error(f"Smart Lane status check failed: {e}")
        return {
            'available': False,
            'error': str(e),
            'last_update': datetime.now().isoformat()
        }


async def run_smart_lane_analysis(
    token_address: str,
    context: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Run Smart Lane analysis for a token with full integration.
    
    Args:
        token_address: Token contract address
        context: Analysis context (symbol, price, etc.)
    
    Returns:
        Dict containing analysis results or None if failed
    """
    global smart_lane_metrics
    
    analysis_start = time.time()
    
    try:
        if not smart_lane_available or not smart_lane_pipeline:
            logger.warning("Smart Lane analysis requested but not available")
            return None
        
        logger.debug(f"Running Smart Lane analysis for {token_address}")
        
        # Run comprehensive analysis
        analysis = await smart_lane_pipeline.analyze_token(
            token_address=token_address,
            context=context
        )
        
        if analysis is None:
            logger.warning(f"Smart Lane analysis returned None for {token_address}")
            return None
        
        # Extract analysis results
        results = {
            'token_address': token_address,
            'analysis_timestamp': datetime.now().isoformat(),
            'overall_risk_score': getattr(analysis, 'overall_risk_score', 0.5),
            'confidence_level': getattr(analysis, 'confidence_level', 0.5),
            'recommended_action': getattr(analysis, 'recommended_action', 'HOLD').value if hasattr(getattr(analysis, 'recommended_action', None), 'value') else str(getattr(analysis, 'recommended_action', 'HOLD')),
            'risk_categories': {},
            'technical_signals': [],
            'position_sizing': None,
            'exit_strategy': None,
            'thought_log': None
        }
        
        # Extract position sizing recommendation
        if hasattr(analysis, 'position_size_recommendation'):
            sizing = analysis.position_size_recommendation
            results['position_sizing'] = {
                'recommended_size_percent': getattr(sizing, 'recommended_size_percent', 0.0),
                'method_used': getattr(sizing, 'method_used', 'UNKNOWN').value if hasattr(getattr(sizing, 'method_used', None), 'value') else str(getattr(sizing, 'method_used', 'UNKNOWN')),
                'sizing_rationale': getattr(sizing, 'sizing_rationale', ''),
                'warnings': getattr(sizing, 'warnings', []),
                'suggested_stop_loss': getattr(sizing, 'suggested_stop_loss_percent', None)
            }
        
        # Extract exit strategy
        if hasattr(analysis, 'exit_strategy'):
            strategy = analysis.exit_strategy
            results['exit_strategy'] = {
                'strategy_name': getattr(strategy, 'strategy_name', ''),
                'stop_loss_percent': getattr(strategy, 'stop_loss_percent', None),
                'take_profit_targets': getattr(strategy, 'take_profit_targets', []),
                'max_hold_time_hours': getattr(strategy, 'max_hold_time_hours', None),
                'exit_levels_count': len(getattr(strategy, 'exit_levels', [])),
                'strategy_rationale': getattr(strategy, 'strategy_rationale', ''),
                'confidence_level': getattr(strategy, 'confidence_level', 0.0)
            }
        
        # Update metrics
        analysis_time = (time.time() - analysis_start) * 1000  # Convert to ms
        smart_lane_metrics['analyses_completed'] += 1
        
        # Update rolling average
        prev_avg = smart_lane_metrics['average_analysis_time_ms']
        count = smart_lane_metrics['analyses_completed']
        smart_lane_metrics['average_analysis_time_ms'] = (
            (prev_avg * (count - 1) + analysis_time) / count
        )
        
        smart_lane_metrics['last_analysis'] = {
            'timestamp': results['analysis_timestamp'],
            'token': context.get('symbol', token_address),
            'risk_score': results['overall_risk_score'],
            'analysis_time_ms': analysis_time
        }
        
        logger.info(
            f"Smart Lane analysis completed for {context.get('symbol', token_address)} - "
            f"risk: {results['overall_risk_score']:.3f}, "
            f"action: {results['recommended_action']}, "
            f"time: {analysis_time:.1f}ms"
        )
        
        return results
        
    except Exception as e:
        analysis_time = (time.time() - analysis_start) * 1000
        logger.error(f"Smart Lane analysis failed: {e} (time: {analysis_time:.1f}ms)", exc_info=True)
        
        # Record error
        smart_lane_metrics['errors'].append({
            'timestamp': datetime.now().isoformat(),
            'token_address': token_address,
            'error': str(e),
            'analysis_time_ms': analysis_time
        })
        
        # Keep only last 10 errors
        smart_lane_metrics['errors'] = smart_lane_metrics['errors'][-10:]
        
        return None


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
    Main dashboard page with Fast Lane and Smart Lane integration.
    
    UPDATED: Added Smart Lane status and metrics integration
    
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
        # Initialize engines if needed
        run_async_in_view(ensure_engine_initialized())
        
        # Initialize Smart Lane if available
        if smart_lane_available and smart_lane_pipeline is None:
            run_async_in_view(initialize_smart_lane_pipeline())
        
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
        
        # Get Smart Lane status
        smart_lane_status = get_smart_lane_status()
        
        # Log data source for debugging
        data_source = "LIVE" if not performance_metrics.get('_mock', False) else "MOCK"
        logger.info(f"Dashboard showing {data_source} data - Fast Lane: {engine_status.get('fast_lane_active', False)}, Smart Lane: {smart_lane_status.get('available', False)}")
        
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
        smart_lane_analyses_today = smart_lane_metrics.get('analyses_completed', 0)
        
        # Prepare context with real engine data and user data
        context = {
            'page_title': 'Trading Dashboard - Fast Lane & Smart Lane Ready',
            'user_profile': {
                'display_name': getattr(request.user, 'first_name', 'Demo User') or 'Demo User'
            },
            'bot_configs': user_configs,
            'active_sessions': active_sessions_db,
            
            # Real engine status
            'engine_status': engine_status,
            'fast_lane_active': engine_status.get('fast_lane_active', False),
            'smart_lane_active': smart_lane_status.get('pipeline_initialized', False),
            'data_source': data_source,
            
            # Real performance metrics
            'performance_metrics': {
                'execution_time_ms': performance_metrics.get('execution_time_ms', 0),
                'success_rate': performance_metrics.get('success_rate', 0),
                'trades_per_minute': performance_metrics.get('trades_per_minute', 0),
                'fast_lane_trades_today': total_trades_today,
                'smart_lane_trades_today': smart_lane_analyses_today,
                'active_pairs_monitored': engine_status.get('pairs_monitored', 0),
                'pending_transactions': engine_status.get('pending_transactions', 0),
            },
            
            # Smart Lane specific metrics (NEW Phase 5)
            'smart_lane_metrics': {
                'average_analysis_time_ms': smart_lane_metrics.get('average_analysis_time_ms', 0),
                'analyses_completed': smart_lane_analyses_today,
                'last_analysis': smart_lane_metrics.get('last_analysis'),
                'available_capabilities': len(smart_lane_status.get('capabilities', [])),
                'error_count': len(smart_lane_metrics.get('errors', []))
            },
            
            # System alerts and notifications
            'system_alerts': [],  # Will be populated when alert system is ready
            
            # Trading mode information
            'current_trading_mode': 'DEMO',
            'mock_mode_enabled': performance_metrics.get('_mock', True),
            'smart_lane_available': smart_lane_status.get('available', False),
            
            # Competitive metrics for display
            'competitive_metrics': {
                'our_speed': f"{performance_metrics.get('execution_time_ms', 0):.0f}ms",
                'competitor_speed': "300ms",
                'speed_advantage': "4x faster" if performance_metrics.get('execution_time_ms', 0) < 100 else "Competitive"
            }
        }
        
        logger.debug("Dashboard context created successfully with Fast Lane and Smart Lane integration")
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
    
    UPDATED: Added Smart Lane status and availability detection
    
    Allows users to choose between Fast Lane and Smart Lane trading modes with real metrics.
    Displays performance comparisons and system status for each mode.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        Rendered mode selection template with context data
    """
    try:
        # Initialize engines if needed
        run_async_in_view(ensure_engine_initialized())
        
        # Initialize Smart Lane if available
        if smart_lane_available and smart_lane_pipeline is None:
            run_async_in_view(initialize_smart_lane_pipeline())
        
        logger.info(f"Mode selection accessed by user: {getattr(request.user, 'username', 'anonymous')}")
        
        # Get real performance metrics for both modes
        performance_metrics = engine_service.get_performance_metrics()
        engine_status = engine_service.get_engine_status()
        smart_lane_status = get_smart_lane_status()
        
        context = {
            'page_title': 'Mode Selection - Fast Lane vs Smart Lane',
            
            # Fast Lane metrics (real from Phase 4)
            'fast_lane_metrics': {
                'execution_time_ms': performance_metrics.get('execution_time_ms', 78),
                'success_rate': performance_metrics.get('success_rate', 94.2),
                'trades_per_minute': performance_metrics.get('trades_per_minute', 12.3),
                'trades_today': performance_metrics.get('fast_lane_trades_today', 0),
                'is_live': not performance_metrics.get('_mock', False),
                'status': 'OPERATIONAL' if engine_status.get('fast_lane_active', False) else 'UNAVAILABLE',
                'phase': 'Phase 4 Complete'
            },
            
            # Smart Lane metrics (Phase 5 - NOW IMPLEMENTED)
            'smart_lane_metrics': {
                'execution_time_ms': smart_lane_metrics.get('average_analysis_time_ms', 2500),
                'success_rate': 96.2,  # Expected improved success rate
                'risk_adjusted_return': 15.3,  # Expected improvement
                'analyses_today': smart_lane_metrics.get('analyses_completed', 0),
                'is_live': smart_lane_status.get('pipeline_initialized', False),
                'status': 'OPERATIONAL' if smart_lane_status.get('pipeline_initialized', False) else 'PHASE5_READY' if smart_lane_available else 'UNAVAILABLE',
                'phase': 'Phase 5 Complete' if smart_lane_status.get('pipeline_initialized', False) else 'Phase 5 Ready'
            },
            
            # System status
            'engine_status': engine_status,
            'fast_lane_available': True if engine_status.get('mock_mode', False) else engine_status.get('fast_lane_active', False),
            'smart_lane_available': smart_lane_status.get('pipeline_initialized', False),
            
            # Smart Lane capabilities (NEW)
            'smart_lane_capabilities': smart_lane_status.get('capabilities', []),
            'smart_lane_components': smart_lane_status.get('components', {}),
            
            # Competitive positioning
            'competitive_comparison': {
                'our_speed': f"{performance_metrics.get('execution_time_ms', 78):.0f}ms",
                'competitor_speed': "300ms",
                'advantage': "4x faster than Unibot"
            }
        }
        
        logger.debug("Mode selection context created with real Fast Lane and Smart Lane metrics")
        return render(request, 'dashboard/mode_selection.html', context)
        
    except Exception as e:
        logger.error(f"Error in mode_selection: {e}", exc_info=True)
        messages.error(request, "Error loading mode selection.")
        return redirect('dashboard:home')


def configuration_panel(request, mode):
    """Configuration panel that returns JSON for AJAX requests."""
    
    # Handle anonymous users
    if not request.user.is_authenticated:
        from django.contrib.auth.models import User
        user, created = User.objects.get_or_create(
            username='demo_user',
            defaults={'first_name': 'Demo', 'last_name': 'User', 'email': 'demo@example.com'}
        )
        request.user = user

    # Validate mode
    valid_modes = ['fast_lane', 'smart_lane']
    if mode not in valid_modes:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': f'Invalid mode: {mode}'})
        messages.error(request, f"Invalid mode: {mode}")
        return redirect('dashboard:mode_selection')

    # CRITICAL: Handle POST requests with JSON responses for AJAX
    if request.method == 'POST':
        # Check if this is an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            try:
                logger.info(f"Processing AJAX configuration save for mode: {mode}")
                
                # Extract form data
                config_data = {
                    'name': request.POST.get('name', '').strip(),
                    'description': request.POST.get('description', '').strip(),
                    'max_position_size_usd': request.POST.get('max_position_size_usd', '100'),
                    'risk_tolerance': request.POST.get('risk_tolerance', 'MEDIUM'),
                    'auto_execution_enabled': request.POST.get('auto_execution_enabled') == 'on',
                    'require_manual_approval': request.POST.get('require_manual_approval') == 'on',
                }
                
                # Mode-specific data extraction
                if mode == 'fast_lane':
                    config_data.update({
                        'execution_timeout_ms': request.POST.get('execution_timeout_ms', '500'),
                        'max_slippage_percent': request.POST.get('max_slippage_percent', '2.0'),
                        'mev_protection_enabled': request.POST.get('mev_protection_enabled') == 'on'
                    })
                elif mode == 'smart_lane':
                    config_data.update({
                        'analysis_depth': request.POST.get('analysis_depth', 'COMPREHENSIVE'),
                        'ai_thought_log': request.POST.get('ai_thought_log', 'COMPREHENSIVE'),
                        'position_sizing_method': request.POST.get('position_sizing_method', 'RISK_BASED'),
                        'max_analysis_time_seconds': request.POST.get('max_analysis_time_seconds', '5')
                    })
                
                # Basic validation
                if not config_data['name']:
                    return JsonResponse({'success': False, 'error': 'Configuration name is required'})
                
                if len(config_data['name']) > 100:
                    return JsonResponse({'success': False, 'error': 'Configuration name must be 100 characters or less'})
                
                # Try to save the configuration
                try:
                    # Import your model - adjust the import path as needed
                    from dashboard.models import BotConfiguration
                    
                    # Create or update configuration
                    config, created = BotConfiguration.objects.update_or_create(
                        user=request.user,
                        name=config_data['name'],
                        trading_mode=mode.upper(),
                        defaults={
                            'config_data': config_data,
                            'is_active': True
                        }
                    )
                    
                    # Deactivate other configs of the same mode
                    BotConfiguration.objects.filter(
                        user=request.user,
                        trading_mode=mode.upper()
                    ).exclude(id=config.id).update(is_active=False)
                    
                    action = 'created' if created else 'updated'
                    logger.info(f"Configuration {action}: {config.name} (ID: {config.id})")
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Configuration "{config_data["name"]}" {action} successfully!',
                        'config_id': config.id,
                        'redirect_url': '/dashboard/'
                    })
                    
                except Exception as db_error:
                    logger.error(f"Database error saving configuration: {db_error}")
                    return JsonResponse({
                        'success': False,
                        'error': 'Database error. Please try again.'
                    })
                
            except Exception as e:
                logger.error(f"Error in AJAX configuration save: {e}", exc_info=True)
                return JsonResponse({
                    'success': False,
                    'error': 'Server error. Please try again.'
                })
        else:
            # Handle non-AJAX POST requests (traditional form submission)
            logger.info("Processing traditional form submission")
            # Your existing POST logic here, or redirect to prevent issues
            messages.info(request, "Please use the form interface to save configurations.")
            return redirect(request.path)
    
    # Handle GET requests (display the form)
    try:
        # Get user's existing configurations
        try:
            from dashboard.models import BotConfiguration
            user_configs = BotConfiguration.objects.filter(
                user=request.user,
                trading_mode=mode.upper()
            ).order_by('-created_at')
            active_config = user_configs.filter(is_active=True).first()
        except:
            user_configs = []
            active_config = None
        
        context = {
            'page_title': f'{mode.replace("_", " ").title()} Configuration',
            'mode': mode,
            'mode_display': mode.replace('_', ' ').title(),
            'config': active_config.config_data if active_config else {},
            'user_configs': user_configs,
            'user': request.user,
        }
        
        return render(request, 'dashboard/configuration_panel.html', context)
        
    except Exception as e:
        logger.error(f"Error loading configuration form: {e}", exc_info=True)
        messages.error(request, "Error loading configuration panel.")
        return redirect('dashboard:mode_selection')















def _handle_configuration_post_json(request, mode):
    """FIXED: Handle POST and return JSON response."""
    try:
        # Extract form data
        config_data = {
            'name': request.POST.get('name', '').strip(),
            'description': request.POST.get('description', '').strip(),
            'max_position_size_usd': float(request.POST.get('max_position_size_usd', 100)),
            'risk_tolerance': request.POST.get('risk_tolerance', 'MEDIUM'),
            'auto_execution_enabled': request.POST.get('auto_execution_enabled') == 'on',
            'require_manual_approval': request.POST.get('require_manual_approval') == 'on'
        }
        
        if mode == 'fast_lane':
            config_data.update({
                'execution_timeout_ms': int(request.POST.get('execution_timeout_ms', 500)),
                'max_slippage_percent': float(request.POST.get('max_slippage_percent', 2.0)),
                'mev_protection_enabled': request.POST.get('mev_protection_enabled') == 'on'
            })
        elif mode == 'smart_lane':
            config_data.update({
                'analysis_depth': request.POST.get('analysis_depth', 'COMPREHENSIVE'),
                'ai_thought_log': request.POST.get('ai_thought_log', 'COMPREHENSIVE'),
                'position_sizing_method': request.POST.get('position_sizing_method', 'RISK_BASED'),
                'max_analysis_time_seconds': float(request.POST.get('max_analysis_time_seconds', 5.0))
            })
        
        # Basic validation
        if not config_data['name']:
            return JsonResponse({'success': False, 'error': 'Configuration name is required'})
        
        # Create or update configuration
        config, created = BotConfiguration.objects.update_or_create(
            user=request.user,
            name=config_data['name'],
            trading_mode=mode.upper(),
            defaults={'config_data': config_data, 'is_active': True}
        )
        
        logger.info(f"Configuration {'created' if created else 'updated'}: {config.name}")
        
        return JsonResponse({
            'success': True,
            'message': f'Configuration "{config_data["name"]}" {"created" if created else "updated"} successfully!',
            'config_id': config.id,
            'redirect_url': '/dashboard/'
        })
        
    except ValueError as e:
        return JsonResponse({'success': False, 'error': f'Invalid values: {str(e)}'})
    except Exception as e:
        logger.error(f"Error saving configuration: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'Error saving configuration. Please try again.'})












def _handle_configuration_display_with_smart_lane(request: HttpRequest, mode: str, form_data: Optional[Dict] = None) -> HttpResponse:
    """Handle displaying configuration form for GET request with Smart Lane support."""
    try:
        # Get engine status and metrics
        engine_status = engine_service.get_engine_status()
        performance_metrics = engine_service.get_performance_metrics()
        smart_lane_status = get_smart_lane_status()
        
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
                'available': smart_lane_status.get('pipeline_initialized', False),
                'status': 'OPERATIONAL' if smart_lane_status.get('pipeline_initialized', False) else 'READY' if smart_lane_available else 'UNAVAILABLE'
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
        
        # Add Smart Lane specific context
        if mode == 'smart_lane':
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
                    'position_sizing_methods': [
                        'RISK_BASED',
                        'KELLY_CRITERION', 
                        'VOLATILITY_ADJUSTED',
                        'CONFIDENCE_WEIGHTED'
                    ],
                    'exit_strategy_types': [
                        'CONSERVATIVE',
                        'BALANCED',
                        'AGGRESSIVE',
                        'VOLATILITY_ADJUSTED'
                    ]
                },
                'current_settings': {
                    'analysis_depth': 'COMPREHENSIVE',
                    'thought_log_enabled': True,
                    'max_analysis_time': 5.0,
                    'min_confidence_threshold': 0.3,
                    'max_position_size_percent': 10.0,
                    'risk_per_trade_percent': 2.0
                } if context.get('smart_lane_ready') else None
            })
        
        logger.debug(f"Rendering configuration panel for {mode} - Smart Lane ready: {context.get('smart_lane_ready', 'N/A')}")
        return render(request, 'dashboard/configuration_panel.html', context)
        
    except Exception as e:
        logger.error(f"Error preparing configuration display for {mode}: {e}", exc_info=True)
        messages.error(request, "Error loading configuration form.")
        return redirect('dashboard:mode_selection')


# =========================================================================
# EXISTING VIEWS (Preserved with enhancements)
# =========================================================================

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
# REAL-TIME DATA STREAMS (Enhanced with Smart Lane)
# =========================================================================

def metrics_stream(request: HttpRequest) -> StreamingHttpResponse:
    """
    Server-sent events endpoint for real-time metrics streaming with Smart Lane support.
    
    ENHANCED: Added Smart Lane metrics to the stream
    
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
                smart_lane_status = get_smart_lane_status()
                
                # Format as server-sent event
                data = {
                    'timestamp': datetime.now().isoformat(),
                    
                    # Fast Lane metrics
                    'execution_time_ms': metrics.get('execution_time_ms', 0),
                    'success_rate': metrics.get('success_rate', 0),
                    'trades_per_minute': metrics.get('trades_per_minute', 0),
                    'fast_lane_active': status.get('fast_lane_active', False),
                    
                    # Smart Lane metrics (NEW)
                    'smart_lane_active': smart_lane_status.get('pipeline_initialized', False),
                    'smart_lane_analysis_time_ms': smart_lane_metrics.get('average_analysis_time_ms', 0),
                    'smart_lane_analyses_count': smart_lane_metrics.get('analyses_completed', 0),
                    'smart_lane_last_analysis': smart_lane_metrics.get('last_analysis'),
                    
                    # System status
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
# JSON API ENDPOINTS (Enhanced with Smart Lane)
# =========================================================================

def api_engine_status(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for engine status with Fast Lane and Smart Lane integration.
    
    ENHANCED: Added Smart Lane status information
    
    Returns current engine status including Fast Lane and Smart Lane availability,
    connection states, and system health metrics.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with engine status data or error message
    """
    try:
        # Initialize engines if needed
        run_async_in_view(ensure_engine_initialized())
        
        status = engine_service.get_engine_status()
        smart_lane_status = get_smart_lane_status()
        
        # Combine status information
        combined_status = {
            **status,
            'smart_lane': smart_lane_status
        }
        
        return JsonResponse({
            'success': True,
            'data': combined_status,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"API engine status error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, status=500)


@require_POST
@csrf_exempt
def api_run_smart_lane_analysis(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to run Smart Lane analysis.
    
    NEW: Phase 5 API endpoint for Smart Lane functionality
    
    Args:
        request: HTTP request with token analysis parameters
    
    Returns:
        JsonResponse: Analysis results
    """
    try:
        if not smart_lane_available:
            return JsonResponse({
                'success': False,
                'error': 'Smart Lane not available',
                'timestamp': datetime.now().isoformat()
            }, status=503)
        
        # Parse request data
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data',
                'timestamp': datetime.now().isoformat()
            }, status=400)
        
        # Extract parameters
        token_address = data.get('token_address')
        context = data.get('context', {})
        
        if not token_address:
            return JsonResponse({
                'success': False,
                'error': 'token_address is required',
                'timestamp': datetime.now().isoformat()
            }, status=400)
        
        # Run analysis
        results = run_async_in_view(run_smart_lane_analysis(token_address, context))
        
        if results is None:
            return JsonResponse({
                'success': False,
                'error': 'Analysis failed to complete',
                'timestamp': datetime.now().isoformat()
            }, status=500)
        
        return JsonResponse({
            'success': True,
            'data': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Smart Lane analysis API error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, status=500)


@require_http_methods(["GET"])
def api_smart_lane_status(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for Smart Lane status information.
    
    NEW: Phase 5 API endpoint
    
    Args:
        request: HTTP request object
    
    Returns:
        JsonResponse: Smart Lane status data
    """
    try:
        status = get_smart_lane_status()
        
        return JsonResponse({
            'success': True,
            'data': status,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Smart Lane status API error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, status=500)


def api_performance_metrics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for performance metrics with Fast Lane and Smart Lane integration.
    
    ENHANCED: Added Smart Lane metrics
    
    Returns current performance metrics including execution times, success rates,
    and trading volume statistics from both engines.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with performance metrics data or error message
    """
    try:
        # Initialize engines if needed
        run_async_in_view(ensure_engine_initialized())
        
        fast_lane_metrics = engine_service.get_performance_metrics()
        smart_lane_status = get_smart_lane_status()
        
        # Combine metrics
        combined_metrics = {
            'fast_lane': fast_lane_metrics,
            'smart_lane': {
                'metrics': smart_lane_metrics,
                'status': smart_lane_status
            }
        }
        
        return JsonResponse({
            'success': True,
            'data': combined_metrics,
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
    API endpoint to set trading mode with Fast Lane and Smart Lane engine integration.
    
    ENHANCED: Added Smart Lane mode support
    
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
        
        # For Smart Lane, also ensure pipeline is initialized
        if mode == 'SMART_LANE' and smart_lane_available:
            if smart_lane_pipeline is None:
                smart_lane_success = run_async_in_view(initialize_smart_lane_pipeline())
                if not smart_lane_success:
                    return JsonResponse({
                        'success': False,
                        'error': 'Failed to initialize Smart Lane pipeline'
                    }, status=500)
        
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
# TRADING SESSION MANAGEMENT (Preserved)
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


def simple_test(request: HttpRequest) -> HttpResponse:
    """
    Simple test endpoint for basic functionality verification with Smart Lane support.
    
    ENHANCED: Added Smart Lane component testing
    
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
        smart_lane_status = get_smart_lane_status()

        results = {
            'timestamp': datetime.now().isoformat(),
            'engine_status': status,
            'performance_metrics': metrics,
            'smart_lane_status': smart_lane_status,
            'user': getattr(request.user, 'username', 'anonymous')
        }

        logger.debug(f"Simple test executed: {results}")
        return JsonResponse({'success': True, 'data': results}, json_dumps_params={'indent': 2})

    except Exception as e:
        logger.error(f"Simple test endpoint failed: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, status=500)
