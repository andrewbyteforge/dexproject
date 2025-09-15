"""
Trading Session Management Views

Handles trading session lifecycle: start, stop, monitor, and manage sessions.
Split from the original monolithic views.py file for better organization.

File: dashboard/views/sessions.py
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, HttpRequest
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError

from ..models import BotConfiguration, TradingSession
from ..engine_service import engine_service

logger = logging.getLogger(__name__)


@require_POST
@login_required
def start_trading_session(request: HttpRequest) -> HttpResponse:
    """
    Start a new trading session with specified configuration.
    
    Creates a new trading session using the selected configuration and
    initializes the appropriate trading engine (Fast Lane or Smart Lane).
    
    Args:
        request: Django HTTP request object with configuration_id
        
    Returns:
        Redirect to session monitoring page or error page
    """
    try:
        logger.info(f"Start trading session requested by user: {request.user.username}")
        
        # Get configuration ID from POST data
        config_id = request.POST.get('configuration_id')
        if not config_id:
            messages.error(request, "Configuration ID is required.")
            return redirect('dashboard:configuration_list')
        
        # Get the configuration
        try:
            config = get_object_or_404(BotConfiguration, id=config_id, user=request.user)
        except BotConfiguration.DoesNotExist:
            logger.warning(f"Configuration {config_id} not found for user: {request.user.username}")
            messages.error(request, "Configuration not found.")
            return redirect('dashboard:configuration_list')
        
        # Validate engine availability
        engine_status = engine_service.get_engine_status()
        if not _can_start_session(config, engine_status):
            error_msg = _get_session_start_error_message(config, engine_status)
            messages.error(request, error_msg)
            return redirect('dashboard:configuration_summary', config_id=config_id)
        
        # Check for existing active sessions
        existing_sessions = TradingSession.objects.filter(
            user=request.user,
            is_active=True
        ).count()
        
        max_concurrent_sessions = 3  # Configurable limit
        if existing_sessions >= max_concurrent_sessions:
            messages.error(request, 
                f"Maximum concurrent sessions ({max_concurrent_sessions}) reached. "
                "Please stop an existing session first."
            )
            return redirect('dashboard:configuration_summary', config_id=config_id)
        
        # Create trading session
        session = TradingSession.objects.create(
            user=request.user,
            configuration=config,
            session_id=uuid.uuid4(),
            is_active=True,
            status='STARTING',
            trading_mode=config.trading_mode
        )
        
        # Initialize session with engine
        initialization_result = _initialize_trading_session(session, config)
        
        if initialization_result['success']:
            session.status = 'RUNNING'
            session.save()
            
            logger.info(f"Trading session started successfully: {session.session_id}")
            messages.success(request, 
                f"Trading session started with configuration '{config.name}'"
            )
            
            return redirect('dashboard:session_monitor', session_id=session.session_id)
        else:
            # Initialization failed
            session.status = 'FAILED'
            session.is_active = False
            session.error_message = initialization_result.get('error', 'Initialization failed')
            session.save()
            
            logger.error(f"Session initialization failed: {initialization_result.get('error')}")
            messages.error(request, 
                f"Failed to start trading session: {initialization_result.get('error')}"
            )
            
            return redirect('dashboard:configuration_summary', config_id=config_id)
        
    except Exception as e:
        logger.error(f"Error starting trading session: {e}", exc_info=True)
        messages.error(request, "Error starting trading session.")
        return redirect('dashboard:home')


@require_POST
@login_required
def stop_trading_session(request: HttpRequest, session_id: uuid.UUID) -> HttpResponse:
    """
    Stop an active trading session.
    
    Gracefully stops the specified trading session, ensuring all pending
    operations are completed and resources are properly cleaned up.
    
    Args:
        request: Django HTTP request object
        session_id: UUID of the session to stop
        
    Returns:
        Redirect to appropriate page with status message
    """
    try:
        logger.info(f"Stop trading session requested: {session_id} by user: {request.user.username}")
        
        # Get the trading session
        try:
            session = get_object_or_404(TradingSession, 
                session_id=session_id, 
                user=request.user,
                is_active=True
            )
        except TradingSession.DoesNotExist:
            logger.warning(f"Active session {session_id} not found for user: {request.user.username}")
            messages.error(request, "Active trading session not found.")
            return redirect('dashboard:home')
        
        # Stop the session with engine
        stop_result = _stop_trading_session(session)
        
        if stop_result['success']:
            # Update session status
            session.is_active = False
            session.status = 'STOPPED'
            session.ended_at = datetime.now()
            session.trades_executed = stop_result.get('trades_executed', 0)
            session.total_volume = stop_result.get('total_volume', 0)
            session.save()
            
            logger.info(f"Trading session stopped successfully: {session_id}")
            messages.success(request, 
                f"Trading session stopped. Executed {session.trades_executed} trades."
            )
        else:
            # Force stop even if engine stop failed
            session.is_active = False
            session.status = 'FORCE_STOPPED'
            session.ended_at = datetime.now()
            session.error_message = stop_result.get('error', 'Stop operation failed')
            session.save()
            
            logger.warning(f"Trading session force stopped: {session_id}")
            messages.warning(request, 
                f"Trading session force stopped due to error: {stop_result.get('error')}"
            )
        
        return redirect('dashboard:session_summary', session_id=session_id)
        
    except Exception as e:
        logger.error(f"Error stopping trading session {session_id}: {e}", exc_info=True)
        messages.error(request, "Error stopping trading session.")
        return redirect('dashboard:home')


@login_required
def session_monitor(request: HttpRequest, session_id: uuid.UUID) -> HttpResponse:
    """
    Real-time monitoring interface for active trading session.
    
    Displays live trading session metrics, recent trades, and performance
    statistics with real-time updates via SSE integration.
    
    Args:
        request: Django HTTP request object
        session_id: UUID of the session to monitor
        
    Returns:
        HttpResponse with session monitoring template
    """
    try:
        logger.debug(f"Session monitor accessed: {session_id} by user: {request.user.username}")
        
        # Get the trading session
        try:
            session = get_object_or_404(TradingSession, 
                session_id=session_id, 
                user=request.user
            )
        except TradingSession.DoesNotExist:
            logger.warning(f"Session {session_id} not found for user: {request.user.username}")
            messages.error(request, "Trading session not found.")
            return redirect('dashboard:home')
        
        # Get session metrics from engine
        session_metrics = _get_session_metrics(session)
        
        # Get recent trades (would be from database in real implementation)
        recent_trades = _get_recent_trades(session, limit=20)
        
        # Get performance statistics
        performance_stats = _calculate_session_performance(session, session_metrics)
        
        context = {
            'page_title': f'Session Monitor - {session.configuration.name}',
            'session': session,
            'session_metrics': session_metrics,
            'recent_trades': recent_trades,
            'performance_stats': performance_stats,
            'configuration': session.configuration,
            'is_active': session.is_active,
            'can_stop': session.is_active and session.status == 'RUNNING',
            'real_time_updates': True,  # Enable SSE updates
            'user': request.user
        }
        
        return render(request, 'dashboard/session_monitor.html', context)
        
    except Exception as e:
        logger.error(f"Error in session monitor for {session_id}: {e}", exc_info=True)
        messages.error(request, "Error loading session monitor.")
        return redirect('dashboard:home')


@login_required
def session_summary(request: HttpRequest, session_id: uuid.UUID) -> HttpResponse:
    """
    Display comprehensive summary of completed trading session.
    
    Shows detailed session results, trade history, performance analysis,
    and provides options for session review and reporting.
    
    Args:
        request: Django HTTP request object
        session_id: UUID of the session to summarize
        
    Returns:
        HttpResponse with session summary template
    """
    try:
        logger.debug(f"Session summary accessed: {session_id} by user: {request.user.username}")
        
        # Get the trading session
        try:
            session = get_object_or_404(TradingSession, 
                session_id=session_id, 
                user=request.user
            )
        except TradingSession.DoesNotExist:
            logger.warning(f"Session {session_id} not found for user: {request.user.username}")
            messages.error(request, "Trading session not found.")
            return redirect('dashboard:home')
        
        # Get comprehensive session data
        session_data = _get_comprehensive_session_data(session)
        
        # Calculate detailed performance metrics
        performance_analysis = _calculate_detailed_performance(session)
        
        # Get trade history
        trade_history = _get_session_trade_history(session)
        
        context = {
            'page_title': f'Session Summary - {session.configuration.name}',
            'session': session,
            'session_data': session_data,
            'performance_analysis': performance_analysis,
            'trade_history': trade_history,
            'configuration': session.configuration,
            'duration_minutes': _calculate_session_duration(session),
            'can_restart': not session.is_active,
            'user': request.user
        }
        
        return render(request, 'dashboard/session_summary.html', context)
        
    except Exception as e:
        logger.error(f"Error in session summary for {session_id}: {e}", exc_info=True)
        messages.error(request, "Error loading session summary.")
        return redirect('dashboard:home')


@login_required
def session_list(request: HttpRequest) -> HttpResponse:
    """
    Display list of user's trading sessions with filtering and pagination.
    
    Shows all trading sessions for the current user with options to filter
    by status, configuration, date range, and search functionality.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse with session list template
    """
    try:
        logger.debug(f"Session list accessed by user: {request.user.username}")
        
        # Get user's sessions
        sessions = TradingSession.objects.filter(user=request.user).order_by('-created_at')
        
        # Apply filters
        status_filter = request.GET.get('status', '')
        if status_filter:
            sessions = sessions.filter(status=status_filter)
        
        config_filter = request.GET.get('configuration', '')
        if config_filter:
            sessions = sessions.filter(configuration_id=config_filter)
        
        mode_filter = request.GET.get('mode', '')
        if mode_filter:
            sessions = sessions.filter(trading_mode=mode_filter)
        
        # Pagination
        from django.core.paginator import Paginator
        paginator = Paginator(sessions, 15)  # Show 15 sessions per page
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        
        # Get user's configurations for filter dropdown
        user_configs = BotConfiguration.objects.filter(user=request.user)
        
        # Calculate summary statistics
        stats = _calculate_session_list_stats(sessions)
        
        context = {
            'page_title': 'Trading Sessions',
            'sessions': page_obj,
            'user_configs': user_configs,
            'stats': stats,
            'filters': {
                'status': status_filter,
                'configuration': config_filter,
                'mode': mode_filter
            },
            'user': request.user
        }
        
        return render(request, 'dashboard/session_list.html', context)
        
    except Exception as e:
        logger.error(f"Error in session list: {e}", exc_info=True)
        messages.error(request, "Error loading session list.")
        return redirect('dashboard:home')


# =========================================================================
# HELPER FUNCTIONS
# =========================================================================

def _can_start_session(config: BotConfiguration, engine_status: Dict[str, Any]) -> bool:
    """Check if a trading session can be started with this configuration."""
    # Check overall engine status
    if engine_status.get('status') not in ['RUNNING', 'READY']:
        return False
    
    # Check mode-specific availability
    if config.trading_mode == 'FAST_LANE':
        return engine_status.get('fast_lane_active', False)
    elif config.trading_mode == 'SMART_LANE':
        return engine_status.get('smart_lane_active', False)
    
    return False


def _get_session_start_error_message(config: BotConfiguration, engine_status: Dict[str, Any]) -> str:
    """Get appropriate error message for session start failure."""
    overall_status = engine_status.get('status', 'UNKNOWN')
    
    if overall_status not in ['RUNNING', 'READY']:
        return f"Trading engine is not ready (Status: {overall_status}). Please wait or contact support."
    
    if config.trading_mode == 'FAST_LANE':
        if not engine_status.get('fast_lane_active', False):
            return "Fast Lane is not currently active. Please check engine status."
    elif config.trading_mode == 'SMART_LANE':
        if not engine_status.get('smart_lane_active', False):
            return "Smart Lane is not currently active. Phase 5 integration may be in progress."
    
    return "Unable to start session with current engine configuration."


def _initialize_trading_session(session: TradingSession, config: BotConfiguration) -> Dict[str, Any]:
    """Initialize trading session with the engine."""
    try:
        # This would integrate with the actual engine initialization
        # For now, simulate successful initialization
        
        logger.info(f"Initializing session {session.session_id} with {config.trading_mode} mode")
        
        # Simulate initialization based on mode
        if config.trading_mode == 'FAST_LANE':
            # Initialize Fast Lane components
            initialization_time = 2  # seconds
        else:  # SMART_LANE
            # Initialize Smart Lane components
            initialization_time = 5  # seconds
        
        return {
            'success': True,
            'initialization_time': initialization_time,
            'mode': config.trading_mode
        }
        
    except Exception as e:
        logger.error(f"Session initialization error: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def _stop_trading_session(session: TradingSession) -> Dict[str, Any]:
    """Stop trading session with the engine."""
    try:
        # This would integrate with the actual engine stop procedures
        logger.info(f"Stopping session {session.session_id}")
        
        # Simulate session stopping
        return {
            'success': True,
            'trades_executed': session.trades_executed,
            'total_volume': float(session.total_volume or 0),
            'stop_time': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Session stop error: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def _get_session_metrics(session: TradingSession) -> Dict[str, Any]:
    """Get real-time session metrics from engine."""
    # This would integrate with real engine metrics
    return {
        'trades_executed': session.trades_executed,
        'successful_trades': session.trades_executed - 1,  # Mock
        'failed_trades': 1,  # Mock
        'total_volume': float(session.total_volume or 0),
        'average_execution_time': 85.5,  # Mock
        'success_rate': 95.0,  # Mock
        'uptime_seconds': (datetime.now() - session.created_at).total_seconds(),
        'is_active': session.is_active
    }


def _get_recent_trades(session: TradingSession, limit: int = 20) -> list:
    """Get recent trades for the session."""
    # This would query actual trade records
    return []  # Mock - would return list of trade objects


def _calculate_session_performance(session: TradingSession, metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate session performance statistics."""
    return {
        'total_trades': metrics.get('trades_executed', 0),
        'success_rate': metrics.get('success_rate', 0),
        'average_execution_time': metrics.get('average_execution_time', 0),
        'total_volume': metrics.get('total_volume', 0),
        'profit_loss': 0.0,  # Would be calculated from actual trades
        'efficiency_score': 85.0  # Mock calculation
    }


def _get_comprehensive_session_data(session: TradingSession) -> Dict[str, Any]:
    """Get comprehensive session data for summary."""
    return {
        'session_id': str(session.session_id),
        'configuration_name': session.configuration.name,
        'trading_mode': session.trading_mode,
        'status': session.status,
        'created_at': session.created_at,
        'ended_at': session.ended_at,
        'duration': _calculate_session_duration(session),
        'trades_executed': session.trades_executed,
        'total_volume': float(session.total_volume or 0)
    }


def _calculate_detailed_performance(session: TradingSession) -> Dict[str, Any]:
    """Calculate detailed performance analysis."""
    return {
        'execution_efficiency': 85.0,  # Mock
        'risk_management_score': 92.0,  # Mock
        'strategy_effectiveness': 78.0,  # Mock
        'overall_performance': 85.0  # Mock
    }


def _get_session_trade_history(session: TradingSession) -> list:
    """Get trade history for the session."""
    # This would query actual trade records
    return []  # Mock - would return detailed trade history


def _calculate_session_duration(session: TradingSession) -> int:
    """Calculate session duration in minutes."""
    if session.ended_at:
        duration = session.ended_at - session.created_at
    else:
        duration = datetime.now() - session.created_at
    
    return int(duration.total_seconds() / 60)


def _calculate_session_list_stats(sessions) -> Dict[str, Any]:
    """Calculate statistics for session list."""
    total_sessions = sessions.count()
    active_sessions = sessions.filter(is_active=True).count()
    completed_sessions = sessions.filter(status='STOPPED').count()
    
    return {
        'total_sessions': total_sessions,
        'active_sessions': active_sessions,
        'completed_sessions': completed_sessions,
        'success_rate': 85.0 if total_sessions > 0 else 0  # Mock calculation
    }