"""
Session Management Views for Dashboard

Handles trading session lifecycle including start, stop, and status monitoring.
Integrates with both Fast Lane and Smart Lane execution engines.

Path: dashboard/views/sessions.py
"""

import logging
import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from decimal import Decimal

from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone as django_timezone
from django.core.cache import cache

from trading.models import TradingSession, BotConfiguration
from dashboard.engine_service import DashboardEngineService

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def start_session(request: HttpRequest) -> JsonResponse:
    """
    Start a new trading session with the specified configuration.
    
    Args:
        request: HTTP request with session configuration
        
    Returns:
        JsonResponse: Session start status and session ID
    """
    try:
        logger.info(f"Starting trading session for user: {request.user.username}")
        
        # Parse request data
        data = json.loads(request.body) if request.body else {}
        
        # Validate required fields
        mode = data.get('mode', 'FAST_LANE')
        config_id = data.get('config_id')
        
        if not config_id:
            return JsonResponse({
                'success': False,
                'error': 'Configuration ID is required'
            }, status=400)
        
        # Load bot configuration
        try:
            bot_config = BotConfiguration.objects.get(
                id=config_id,
                user=request.user
            )
        except BotConfiguration.DoesNotExist:
            logger.warning(f"Configuration {config_id} not found for user {request.user.id}")
            return JsonResponse({
                'success': False,
                'error': 'Configuration not found'
            }, status=404)
        
        # Check for existing active session
        active_session = TradingSession.objects.filter(
            user=request.user,
            status='RUNNING'
        ).first()
        
        if active_session:
            logger.info(f"User {request.user.username} already has active session: {active_session.session_id}")
            return JsonResponse({
                'success': False,
                'error': 'An active session already exists',
                'session_id': str(active_session.session_id)
            }, status=400)
        
        # Create new trading session
        with transaction.atomic():
            # Get initial capital from config or use default
            initial_capital = Decimal(str(bot_config.config_data.get('initial_capital', 1000.0)))
            
            session = TradingSession.objects.create(
                user=request.user,
                bot_config=bot_config,
                name=f"{mode} Session - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                trading_mode=mode,
                status='INITIALIZING',
                config_snapshot=bot_config.config_data,
                starting_balance_usd=initial_capital,
                current_balance_usd=initial_capital,
                realized_pnl_usd=Decimal('0.00'),
                unrealized_pnl_usd=Decimal('0.00'),
                total_fees_usd=Decimal('0.00'),
                max_drawdown_usd=Decimal('0.00'),
                max_drawdown_percent=Decimal('0.00'),
                average_execution_time_ms=Decimal('0.00'),
                average_slippage_percent=Decimal('0.00'),
                trades_executed=0,
                successful_trades=0,
                failed_trades=0,
                total_opportunities=0,
                error_count=0,
                daily_loss_usd=Decimal('0.00'),
                daily_limit_hit=False,
                emergency_stop_triggered=False
            )
            
            logger.info(f"Created session {session.session_id} in database")
            
            # Initialize engine service
            engine_service = DashboardEngineService()
            
            # Start the appropriate engine
            if mode == 'FAST_LANE':
                # Start Fast Lane engine
                engine_result = asyncio.run(
                    engine_service.start_fast_lane_session(
                        session_id=str(session.session_id),
                        config=bot_config.config_data
                    )
                )
            else:
                # Start Smart Lane engine (Phase 5)
                engine_result = asyncio.run(
                    engine_service.start_smart_lane_session(
                        session_id=str(session.session_id),
                        config=bot_config.config_data
                    )
                )
            
            # Update session status based on engine result
            if engine_result.get('success'):
                session.status = 'RUNNING'
                session.started_at = django_timezone.now()
                session.last_activity_at = django_timezone.now()
                session.save()
                
                logger.info(f"Successfully started {mode} session: {session.session_id}")
                
                return JsonResponse({
                    'success': True,
                    'session_id': str(session.session_id),
                    'mode': mode,
                    'status': 'RUNNING',
                    'message': f'{mode.replace("_", " ").title()} session started successfully',
                    'started_at': session.started_at.isoformat()
                })
            else:
                # Engine start failed
                session.status = 'FAILED'
                session.last_error = engine_result.get('error', 'Unknown engine error')
                session.stopped_at = django_timezone.now()
                session.save()
                
                logger.error(f"Failed to start engine for session: {session.session_id} - {session.last_error}")
                
                return JsonResponse({
                    'success': False,
                    'error': engine_result.get('error', 'Failed to start trading engine'),
                    'session_id': str(session.session_id)
                }, status=500)
                
    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Unexpected error starting session: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def stop_session(request: HttpRequest) -> JsonResponse:
    """
    Stop an active trading session.
    
    Args:
        request: HTTP request with session ID
        
    Returns:
        JsonResponse: Session stop status
    """
    try:
        logger.info(f"Stopping trading session for user: {request.user.username}")
        
        # Parse request data
        data = json.loads(request.body) if request.body else {}
        session_id = data.get('session_id')
        
        if not session_id:
            # Try to find active session
            session = TradingSession.objects.filter(
                user=request.user,
                status='RUNNING'
            ).first()
            
            if not session:
                logger.warning(f"No active session found for user {request.user.username}")
                return JsonResponse({
                    'success': False,
                    'error': 'No active session found'
                }, status=404)
        else:
            # Load specific session
            try:
                session = TradingSession.objects.get(
                    session_id=session_id,
                    user=request.user
                )
            except TradingSession.DoesNotExist:
                logger.warning(f"Session {session_id} not found for user {request.user.id}")
                return JsonResponse({
                    'success': False,
                    'error': 'Session not found'
                }, status=404)
        
        # Check if session is already stopped
        if session.status in ['STOPPED', 'COMPLETED', 'FAILED']:
            logger.info(f"Session {session.session_id} is already {session.status}")
            return JsonResponse({
                'success': False,
                'error': f'Session is already {session.status.lower()}',
                'status': session.status
            }, status=400)
        
        # Stop the engine
        engine_service = DashboardEngineService()
        engine_result = asyncio.run(
            engine_service.stop_session(str(session.session_id))
        )
        
        # Update session status
        with transaction.atomic():
            session.status = 'STOPPED'
            session.stopped_at = django_timezone.now()
            session.last_activity_at = django_timezone.now()
            
            # Calculate final metrics
            if session.started_at and session.stopped_at:
                duration = (session.stopped_at - session.started_at).total_seconds()
                logger.info(f"Session {session.session_id} ran for {duration:.1f} seconds")
            
            # Calculate final P&L
            session.realized_pnl_usd = session.current_balance_usd - session.starting_balance_usd
            
            session.save()
        
        logger.info(f"Successfully stopped session: {session.session_id}")
        
        return JsonResponse({
            'success': True,
            'session_id': str(session.session_id),
            'status': 'STOPPED',
            'message': 'Trading session stopped successfully',
            'final_balance': float(session.current_balance_usd),
            'starting_balance': float(session.starting_balance_usd),
            'total_trades': session.trades_executed,
            'successful_trades': session.successful_trades,
            'failed_trades': session.failed_trades,
            'pnl': float(session.realized_pnl_usd),
            'pnl_percent': float((session.realized_pnl_usd / session.starting_balance_usd * 100) if session.starting_balance_usd > 0 else 0),
            'stopped_at': session.stopped_at.isoformat()
        })
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Unexpected error stopping session: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_session_status(request: HttpRequest) -> JsonResponse:
    """
    Get the status of trading sessions.
    
    Args:
        request: HTTP request with optional session_id parameter
        
    Returns:
        JsonResponse: Session status information
    """
    try:
        session_id = request.GET.get('session_id')
        
        if session_id:
            # Get specific session status
            try:
                session = TradingSession.objects.get(
                    session_id=session_id,
                    user=request.user
                )
                
                # Get real-time metrics from engine
                engine_service = DashboardEngineService()
                engine_metrics = asyncio.run(
                    engine_service.get_session_metrics(str(session.session_id))
                )
                
                # Build comprehensive session status
                session_data = {
                    'session_id': str(session.session_id),
                    'name': session.name,
                    'mode': session.trading_mode,
                    'status': session.status,
                    'started_at': session.started_at.isoformat() if session.started_at else None,
                    'stopped_at': session.stopped_at.isoformat() if session.stopped_at else None,
                    'last_activity': session.last_activity_at.isoformat() if session.last_activity_at else None,
                    
                    # Financial metrics
                    'current_balance': float(session.current_balance_usd),
                    'starting_balance': float(session.starting_balance_usd),
                    'realized_pnl': float(session.realized_pnl_usd),
                    'unrealized_pnl': float(session.unrealized_pnl_usd),
                    'total_pnl': float(session.realized_pnl_usd + session.unrealized_pnl_usd),
                    'pnl_percent': float(
                        ((session.current_balance_usd - session.starting_balance_usd) / 
                         session.starting_balance_usd * 100)
                        if session.starting_balance_usd > 0 else 0
                    ),
                    
                    # Trading metrics
                    'trades_executed': session.trades_executed,
                    'successful_trades': session.successful_trades,
                    'failed_trades': session.failed_trades,
                    'success_rate': float(
                        (session.successful_trades / session.trades_executed * 100)
                        if session.trades_executed > 0 else 0
                    ),
                    'total_opportunities': session.total_opportunities,
                    'opportunity_conversion': float(
                        (session.trades_executed / session.total_opportunities * 100)
                        if session.total_opportunities > 0 else 0
                    ),
                    
                    # Performance metrics
                    'avg_execution_time_ms': float(session.average_execution_time_ms),
                    'avg_slippage_percent': float(session.average_slippage_percent),
                    'total_fees': float(session.total_fees_usd),
                    'max_drawdown_usd': float(session.max_drawdown_usd),
                    'max_drawdown_percent': float(session.max_drawdown_percent),
                    
                    # Risk metrics
                    'daily_loss': float(session.daily_loss_usd),
                    'daily_limit_hit': session.daily_limit_hit,
                    'emergency_stop_triggered': session.emergency_stop_triggered,
                    'error_count': session.error_count,
                    'last_error': session.last_error,
                    
                    # Engine metrics (real-time)
                    'engine_metrics': engine_metrics
                }
                
                return JsonResponse({
                    'success': True,
                    'session': session_data
                })
                
            except TradingSession.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Session not found'
                }, status=404)
        
        else:
            # Get all user sessions
            sessions = TradingSession.objects.filter(
                user=request.user
            ).order_by('-created_at')[:10]  # Last 10 sessions
            
            # Get active session if exists
            active_session = sessions.filter(status='RUNNING').first()
            
            # Build session list
            session_list = []
            for s in sessions:
                session_list.append({
                    'session_id': str(s.session_id),
                    'name': s.name,
                    'mode': s.trading_mode,
                    'status': s.status,
                    'started_at': s.started_at.isoformat() if s.started_at else None,
                    'stopped_at': s.stopped_at.isoformat() if s.stopped_at else None,
                    'pnl': float(s.realized_pnl_usd),
                    'pnl_percent': float(
                        ((s.current_balance_usd - s.starting_balance_usd) / 
                         s.starting_balance_usd * 100)
                        if s.starting_balance_usd > 0 else 0
                    ),
                    'trades': s.trades_executed,
                    'success_rate': float(
                        (s.successful_trades / s.trades_executed * 100)
                        if s.trades_executed > 0 else 0
                    ),
                    'duration_minutes': float(
                        ((s.stopped_at or django_timezone.now()) - s.started_at).total_seconds() / 60
                        if s.started_at else 0
                    )
                })
            
            return JsonResponse({
                'success': True,
                'active_session': {
                    'session_id': str(active_session.session_id),
                    'mode': active_session.trading_mode,
                    'status': active_session.status,
                    'current_balance': float(active_session.current_balance_usd),
                    'pnl': float(active_session.realized_pnl_usd),
                    'trades_executed': active_session.trades_executed,
                    'started_at': active_session.started_at.isoformat() if active_session.started_at else None
                } if active_session else None,
                'recent_sessions': session_list,
                'total_sessions': TradingSession.objects.filter(user=request.user).count(),
                'total_pnl_all_time': float(
                    TradingSession.objects.filter(user=request.user).aggregate(
                        total=models.Sum('realized_pnl_usd')
                    )['total'] or 0
                )
            })
            
    except Exception as e:
        logger.error(f"Error getting session status: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# Import models at the end to avoid circular imports
from django.db import models