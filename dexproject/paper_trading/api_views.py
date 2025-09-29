"""
Paper Trading API Views - REST API Endpoints

This module provides all API endpoints for the paper trading system including
real-time data feeds, bot control, and configuration management.

File: dexproject/paper_trading/api_views.py
"""

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List

from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Sum, Avg, Count
from django.utils import timezone
from django.core.cache import cache

# Import all models
from .models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingConfig,
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    PaperTradingSession,
    PaperPerformanceMetrics
)

logger = logging.getLogger(__name__)


# =============================================================================
# DATA API ENDPOINTS
# =============================================================================


@require_http_methods(["GET"])
def api_ai_thoughts(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for AI thought logs with real-time updates.
    
    Returns recent AI decision-making thoughts for transparency.
    
    Query Parameters:
        limit (int): Maximum number of thoughts to return (default: 10)
        since (str): ISO datetime to get thoughts after
    
    Returns:
        JsonResponse: AI thoughts data with metadata
    """
    try:
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
        
        account = PaperTradingAccount.objects.filter(
            user=demo_user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        # Get query parameters
        limit = int(request.GET.get('limit', 10))
        since = request.GET.get('since')
        
        # Build query
        thoughts_query = PaperAIThoughtLog.objects.filter(account=account)
        
        if since:
            since_datetime = datetime.fromisoformat(since)
            thoughts_query = thoughts_query.filter(created_at__gt=since_datetime)
        
        # Get thoughts ordered by creation time
        thoughts = thoughts_query.order_by('-created_at')[:limit]
        
        # Build response data
        thoughts_data = {
            'thoughts': [
                {
                    'id': str(thought.thought_id),
                    'category': thought.thought_category,
                    'content': thought.thought_content,
                    'metadata': thought.metadata or {},
                    'created_at': thought.created_at.isoformat(),
                    'importance': thought.importance_score,
                    # Additional fields for dashboard display
                    'decision_type': thought.metadata.get('decision_type', 'ANALYSIS') if thought.metadata else 'ANALYSIS',
                    'token_symbol': thought.metadata.get('token_symbol', '') if thought.metadata else '',
                    'lane_used': thought.metadata.get('lane_used', 'SMART') if thought.metadata else 'SMART',
                    'confidence_percent': thought.metadata.get('confidence', 50) if thought.metadata else 50,
                    'primary_reasoning': thought.thought_content[:200] if thought.thought_content else '',
                    'timestamp': thought.created_at.isoformat(),
                }
                for thought in thoughts
            ],
            'count': len(thoughts),
            'timestamp': timezone.now().isoformat(),
        }
        
        return JsonResponse(thoughts_data)
        
    except Exception as e:
        logger.error(f"Error in AI thoughts API: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_portfolio_data(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for portfolio data.
    
    Returns current portfolio state including positions,
    balance, and performance metrics.
    
    Returns:
        JsonResponse: Portfolio data with positions and metrics
    """
    try:
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
            
        account = PaperTradingAccount.objects.filter(
            user=demo_user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        # Get open positions
        positions = PaperPosition.objects.filter(
            account=account,
            is_open=True
        )
        
        # Build portfolio data
        portfolio_data = {
            'account': {
                'id': str(account.account_id),
                'name': account.name,
                'balance': float(account.current_balance_usd),
                'initial_balance': float(account.initial_balance_usd),
                'total_pnl': float(account.total_pnl_usd),
                'return_percent': float(account.total_return_percent),
                'win_rate': float(account.win_rate),
            },
            'positions': [
                {
                    'id': str(pos.position_id),
                    'token_symbol': pos.token_symbol,
                    'token_address': pos.token_address,
                    'quantity': float(pos.quantity),
                    'entry_price': float(pos.average_entry_price_usd),
                    'current_price': float(pos.current_price_usd),
                    'current_value': float(pos.current_value_usd),
                    'unrealized_pnl': float(pos.unrealized_pnl_usd),
                    'unrealized_pnl_percent': float(pos.unrealized_pnl_percent),
                    'opened_at': pos.opened_at.isoformat(),
                }
                for pos in positions
            ],
            'summary': {
                'total_value': float(account.current_balance_usd + 
                                   sum(p.current_value_usd for p in positions)),
                'positions_count': positions.count(),
                'cash_percentage': float((account.current_balance_usd / 
                                        (account.current_balance_usd + 
                                         sum(p.current_value_usd for p in positions)) * 100)
                                       if positions.exists() else 100),
            },
            'timestamp': timezone.now().isoformat(),
        }
        
        return JsonResponse(portfolio_data)
        
    except Exception as e:
        logger.error(f"Error in portfolio API: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_trades_data(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for trade history data with filtering support.
    
    Query Parameters:
        status (str): Filter by trade status
        trade_type (str): Filter by trade type (buy/sell)
        limit (int): Maximum number of trades to return
    
    Returns:
        JsonResponse: Filtered trade data
    """
    try:
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
            
        account = PaperTradingAccount.objects.filter(
            user=demo_user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        # Build query with filters
        trades_query = PaperTrade.objects.filter(account=account)
        
        # Apply status filter
        status = request.GET.get('status')
        if status:
            trades_query = trades_query.filter(status=status)
        
        # Apply trade type filter
        trade_type = request.GET.get('trade_type')
        if trade_type:
            trades_query = trades_query.filter(trade_type=trade_type)
        
        # Apply limit
        limit = int(request.GET.get('limit', 50))
        trades_query = trades_query.order_by('-created_at')[:limit]
        
        # Build trades data
        trades_data = {
            'trades': [
                {
                    'id': str(trade.trade_id),
                    'type': trade.trade_type,
                    'status': trade.status,
                    'token_in': trade.token_in_symbol,
                    'token_out': trade.token_out_symbol,
                    'amount_in': float(trade.amount_in),
                    'amount_in_usd': float(trade.amount_in_usd),
                    'expected_amount_out': float(trade.expected_amount_out) if trade.expected_amount_out else None,
                    'actual_amount_out': float(trade.actual_amount_out) if trade.actual_amount_out else None,
                    'gas_cost_usd': float(trade.simulated_gas_cost_usd) if trade.simulated_gas_cost_usd else 0,
                    'slippage': float(trade.simulated_slippage_percent) if trade.simulated_slippage_percent else 0,
                    'created_at': trade.created_at.isoformat(),
                    'executed_at': trade.executed_at.isoformat() if trade.executed_at else None,
                }
                for trade in trades_query
            ],
            'count': len(trades_query),
            'timestamp': timezone.now().isoformat(),
        }
        
        return JsonResponse(trades_data)
        
    except Exception as e:
        logger.error(f"Error in trades API: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_recent_trades(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for recent trades - simplified for dashboard display.
    
    Query Parameters:
        limit (int): Number of trades to return (max: 50)
        since (str): ISO datetime to get trades after
    
    Returns:
        JsonResponse: Recent trades with essential information
    """
    try:
        from django.contrib.auth.models import User
        
        # Get user (demo or authenticated)
        if request.user.is_authenticated:
            user = request.user
        else:
            try:
                user = User.objects.get(username='demo_user')
            except User.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Demo user not configured',
                    'trades': []
                }, status=404)
        
        # Get active account
        account = PaperTradingAccount.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({
                'success': True,
                'trades': [],
                'count': 0,
                'timestamp': timezone.now().isoformat()
            })
        
        # Build query
        trades_query = PaperTrade.objects.filter(account=account)
        
        # Apply since filter if provided
        since = request.GET.get('since')
        if since:
            try:
                since_datetime = datetime.fromisoformat(since)
                trades_query = trades_query.filter(created_at__gt=since_datetime)
            except (ValueError, TypeError):
                logger.warning(f"Invalid since parameter: {since}")
        
        # Get recent trades with limit
        limit = min(int(request.GET.get('limit', 10)), 50)
        trades = trades_query.order_by('-created_at')[:limit]
        
        # Build response data
        trades_data = []
        for trade in trades:
            trade_data = {
                'trade_id': str(trade.trade_id),
                'trade_type': trade.trade_type.upper() if trade.trade_type else 'UNKNOWN',
                'token_symbol': trade.token_out_symbol if trade.trade_type == 'buy' else trade.token_in_symbol,
                'token_out_symbol': trade.token_out_symbol,
                'token_in_symbol': trade.token_in_symbol,
                'amount_in_usd': float(trade.amount_in_usd) if trade.amount_in_usd else 0,
                'amount_usd': float(trade.amount_in_usd) if trade.amount_in_usd else 0,
                'price': float(trade.execution_price_usd) if trade.execution_price_usd else 0,
                'status': trade.status.upper() if trade.status else 'PENDING',
                'created_at': trade.created_at.isoformat(),
                'execution_time_ms': trade.execution_time_ms,
            }
            
            # Add P&L if available
            if hasattr(trade, 'pnl_usd') and trade.pnl_usd is not None:
                trade_data['pnl_usd'] = float(trade.pnl_usd)
                trade_data['pnl_percent'] = float(trade.pnl_percent) if hasattr(trade, 'pnl_percent') and trade.pnl_percent else 0
            
            trades_data.append(trade_data)
        
        return JsonResponse({
            'success': True,
            'trades': trades_data,
            'count': len(trades_data),
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in api_recent_trades: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch recent trades',
            'trades': []
        }, status=500)


@require_http_methods(["GET"])
def api_open_positions(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to get current open positions.
    
    Returns all open positions with current values and P&L calculations.
    
    Returns:
        JsonResponse: Open positions data with summary metrics
    """
    try:
        from django.contrib.auth.models import User
        
        # Get user (demo or authenticated)
        if request.user.is_authenticated:
            user = request.user
        else:
            try:
                user = User.objects.get(username='demo_user')
            except User.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Demo user not configured',
                    'positions': []
                }, status=404)
        
        # Get active account
        account = PaperTradingAccount.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({
                'success': True,
                'positions': [],
                'summary': {
                    'total_positions': 0,
                    'total_value_usd': 0,
                    'total_unrealized_pnl_usd': 0,
                    'total_unrealized_pnl_percent': 0
                },
                'timestamp': timezone.now().isoformat()
            })
        
        # Get open positions
        positions = PaperPosition.objects.filter(
            account=account,
            is_open=True
        ).order_by('-current_value_usd')
        
        # Build response data
        positions_data = []
        total_value = Decimal('0')
        total_pnl = Decimal('0')
        total_cost_basis = Decimal('0')
        
        for position in positions:
            # Calculate current metrics
            current_value = position.current_value_usd or Decimal('0')
            cost_basis = (position.average_entry_price_usd * position.quantity) if position.average_entry_price_usd else Decimal('0')
            unrealized_pnl = position.unrealized_pnl_usd or Decimal('0')
            unrealized_pnl_percent = position.unrealized_pnl_percent or Decimal('0')
            
            position_data = {
                'position_id': str(position.position_id),
                'token_symbol': position.token_symbol,
                'token_address': position.token_address,
                'quantity': float(position.quantity),
                'average_entry_price_usd': float(position.average_entry_price_usd) if position.average_entry_price_usd else 0,
                'current_price_usd': float(position.current_price_usd) if position.current_price_usd else 0,
                'current_value_usd': float(current_value),
                'cost_basis_usd': float(cost_basis),
                'unrealized_pnl_usd': float(unrealized_pnl),
                'unrealized_pnl_percent': float(unrealized_pnl_percent),
                'opened_at': position.opened_at.isoformat() if position.opened_at else None,
                'last_updated': position.last_updated.isoformat() if position.last_updated else None,
            }
            
            positions_data.append(position_data)
            total_value += current_value
            total_pnl += unrealized_pnl
            total_cost_basis += cost_basis
        
        # Calculate summary metrics
        total_unrealized_pnl_percent = float(
            (total_pnl / total_cost_basis * 100) if total_cost_basis > 0 else 0
        )
        
        summary = {
            'total_positions': len(positions_data),
            'total_value_usd': float(total_value),
            'total_cost_basis_usd': float(total_cost_basis),
            'total_unrealized_pnl_usd': float(total_pnl),
            'total_unrealized_pnl_percent': total_unrealized_pnl_percent
        }
        
        return JsonResponse({
            'success': True,
            'positions': positions_data,
            'summary': summary,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in api_open_positions: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch open positions',
            'positions': []
        }, status=500)


@require_http_methods(["GET"])
def api_metrics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for dashboard metrics summary.
    
    Returns key performance indicators for the dashboard display.
    
    Returns:
        JsonResponse: Metrics data including P&L, win rate, and trading volume
    """
    try:
        from django.contrib.auth.models import User
        
        # Get user
        if request.user.is_authenticated:
            user = request.user
        else:
            try:
                user = User.objects.get(username='demo_user')
            except User.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Demo user not configured'
                }, status=404)
        
        # Get active account
        account = PaperTradingAccount.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({
                'success': True,
                'current_balance': 10000,
                'total_pnl': 0,
                'return_percent': 0,
                'win_rate': 0,
                'trades_24h': 0,
                'volume_24h': 0,
                'total_trades': 0,
                'successful_trades': 0
            })
        
        # Get 24h stats
        time_24h_ago = timezone.now() - timedelta(hours=24)
        trades_24h_data = PaperTrade.objects.filter(
            account=account,
            created_at__gte=time_24h_ago
        ).aggregate(
            count=Count('trade_id'),
            total_volume=Sum('amount_in_usd')
        )
        
        # Calculate return percentage
        return_percent = float(account.total_return_percent) if account.total_return_percent else 0
        
        metrics = {
            'success': True,
            'current_balance': float(account.current_balance_usd),
            'initial_balance': float(account.initial_balance_usd),
            'total_pnl': float(account.total_pnl_usd),
            'return_percent': return_percent,
            'win_rate': float(account.win_rate) if account.win_rate else 0,
            'trades_24h': trades_24h_data['count'] or 0,
            'volume_24h': float(trades_24h_data['total_volume']) if trades_24h_data['total_volume'] else 0,
            'total_trades': account.total_trades,
            'successful_trades': account.successful_trades,
            'failed_trades': account.failed_trades,
            'timestamp': timezone.now().isoformat()
        }
        
        return JsonResponse(metrics)
        
    except Exception as e:
        logger.error(f"Error in api_metrics: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch metrics'
        }, status=500)


# =============================================================================
# CONFIGURATION API
# =============================================================================


@require_http_methods(["GET", "POST"])
@csrf_exempt
def api_configuration(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for strategy configuration management.
    
    GET: Returns current configuration
    POST: Updates configuration
    
    Returns:
        JsonResponse: Configuration data or update status
    """
    try:
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
        
        account = PaperTradingAccount.objects.filter(
            user=demo_user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        if request.method == 'GET':
            # Get current configuration
            config = PaperStrategyConfiguration.objects.filter(
                account=account,
                is_active=True
            ).first()
            
            if config:
                config_data = {
                    'strategy_name': config.strategy_name,
                    'is_active': config.is_active,
                    'configuration': config.configuration,
                    'created_at': config.created_at.isoformat(),
                    'updated_at': config.updated_at.isoformat(),
                }
            else:
                config_data = {
                    'strategy_name': 'default',
                    'is_active': False,
                    'configuration': {},
                    'message': 'No active configuration found'
                }
            
            return JsonResponse(config_data)
            
        elif request.method == 'POST':
            # Update configuration
            try:
                data = json.loads(request.body)
                
                config, created = PaperStrategyConfiguration.objects.update_or_create(
                    account=account,
                    strategy_name=data.get('strategy_name', 'default'),
                    defaults={
                        'is_active': data.get('is_active', True),
                        'configuration': data.get('configuration', {})
                    }
                )
                
                logger.info(f"Configuration {'created' if created else 'updated'} for account {account.account_id}")
                
                return JsonResponse({
                    'success': True,
                    'message': f"Configuration {'created' if created else 'updated'}",
                    'config_id': str(config.config_id)
                })
                
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid JSON'}, status=400)
            except Exception as e:
                logger.error(f"Error updating configuration: {e}", exc_info=True)
                return JsonResponse({'error': str(e)}, status=500)
                
    except Exception as e:
        logger.error(f"Error in configuration API: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_performance_metrics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for performance metrics.
    
    Returns detailed performance metrics and statistics.
    
    Returns:
        JsonResponse: Performance data including Sharpe ratio, win rate, etc.
    """
    try:
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
        
        account = PaperTradingAccount.objects.filter(
            user=demo_user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        # Get latest metrics through session
        sessions = PaperTradingSession.objects.filter(
            account=account
        ).values_list('session_id', flat=True)
        
        # Get metrics for those sessions
        metrics = PaperPerformanceMetrics.objects.filter(
            session__in=sessions
        ).order_by('-calculated_at').first()
        
        if metrics:
            metrics_data = {
                'sharpe_ratio': float(metrics.sharpe_ratio) if metrics.sharpe_ratio else 0,
                'sortino_ratio': float(metrics.sortino_ratio) if hasattr(metrics, 'sortino_ratio') and metrics.sortino_ratio else 0,
                'max_drawdown': float(metrics.max_drawdown_percent) if metrics.max_drawdown_percent else 0,
                'win_rate': float(metrics.win_rate) if metrics.win_rate else 0,
                'profit_factor': float(metrics.profit_factor) if metrics.profit_factor else 0,
                'average_win': float(metrics.avg_win_usd) if metrics.avg_win_usd else 0,
                'average_loss': float(metrics.avg_loss_usd) if metrics.avg_loss_usd else 0,
                'best_trade': float(metrics.largest_win_usd) if metrics.largest_win_usd else 0,
                'worst_trade': float(metrics.largest_loss_usd) if metrics.largest_loss_usd else 0,
                'trades_count': metrics.total_trades,
                'created_at': metrics.calculated_at.isoformat() if metrics.calculated_at else timezone.now().isoformat(),
            }
        else:
            # Return default metrics if none exist
            metrics_data = {
                'sharpe_ratio': 0,
                'sortino_ratio': 0,
                'max_drawdown': 0,
                'win_rate': float(account.win_rate) if account.win_rate else 0,
                'profit_factor': 0,
                'average_win': 0,
                'average_loss': 0,
                'best_trade': 0,
                'worst_trade': 0,
                'trades_count': account.total_trades,
                'message': 'No performance metrics calculated yet'
            }
        
        # Add account-level stats
        metrics_data['account_stats'] = {
            'total_pnl': float(account.total_pnl_usd),
            'total_return': float(account.total_return_percent),
            'current_balance': float(account.current_balance_usd),
            'initial_balance': float(account.initial_balance_usd),
            'total_trades': account.total_trades,
            'successful_trades': account.successful_trades,
            'failed_trades': account.failed_trades,
            'win_rate': float(account.win_rate) if account.win_rate else 0,
        }
        
        return JsonResponse(metrics_data)
        
    except Exception as e:
        logger.error(f"Error in performance metrics API: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# BOT CONTROL API
# =============================================================================


@require_http_methods(["POST"])
@csrf_exempt
def api_start_bot(request: HttpRequest) -> JsonResponse:
    """
    Start paper trading bot.
    
    Creates a new trading session and initiates the bot process.
    
    Returns:
        JsonResponse: Bot status with session ID
    """
    try:
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
        
        account = PaperTradingAccount.objects.filter(
            user=demo_user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        # Check if there's already an active session
        active_session = PaperTradingSession.objects.filter(
            account=account,
            status="ACTIVE"
        ).first()
        
        if active_session:
            return JsonResponse({
                'success': False,
                'error': 'Bot is already running',
                'session_id': str(active_session.session_id)
            }, status=400)
        
        # Create new trading session
        session = PaperTradingSession.objects.create(
            account=account,
            status="ACTIVE",
            session_config=json.loads(request.body) if request.body else {}
        )
        
        # TODO: Actually start the bot process
        # This would typically trigger a background task or service
        # For example, using Celery:
        # from .tasks import run_paper_trading_bot
        # run_paper_trading_bot.delay(session.session_id)
        
        logger.info(f"Started paper trading session {session.session_id} for account {account.account_id}")
        
        return JsonResponse({
            'success': True,
            'session_id': str(session.session_id),
            'message': 'Paper trading bot started',
            'status': 'running'
        })
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def api_stop_bot(request: HttpRequest) -> JsonResponse:
    """
    Stop paper trading bot.
    
    Ends active trading sessions and stops the bot process.
    
    Returns:
        JsonResponse: Bot status with number of sessions ended
    """
    try:
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
        
        account = PaperTradingAccount.objects.filter(
            user=demo_user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        # End active sessions
        active_sessions = PaperTradingSession.objects.filter(
            account=account,
            status="ACTIVE"
        )
        
        sessions_ended = active_sessions.count()
        
        if sessions_ended == 0:
            return JsonResponse({
                'success': False,
                'error': 'No active bot session found',
                'sessions_ended': 0
            }, status=400)
        
        # Update session status
        for session in active_sessions:
            session.status = "COMPLETED"
            session.ended_at = timezone.now()
            session.save()
        
        # TODO: Actually stop the bot process
        # This would typically stop background tasks or services
        # For example, using Celery:
        # from .tasks import stop_paper_trading_bot
        # for session in active_sessions:
        #     stop_paper_trading_bot.delay(session.session_id)
        
        logger.info(f"Stopped {sessions_ended} paper trading sessions for account {account.account_id}")
        
        return JsonResponse({
            'success': True,
            'sessions_ended': sessions_ended,
            'message': 'Paper trading bot stopped',
            'status': 'stopped'
        })
        
    except Exception as e:
        logger.error(f"Error stopping bot: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_bot_status(request: HttpRequest) -> JsonResponse:
    """
    Get paper trading bot status.
    
    Returns current bot status with session information.
    
    Returns:
        JsonResponse: Bot status data
    """
    try:
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
        
        account = PaperTradingAccount.objects.filter(
            user=demo_user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        # Check for active session
        active_session = PaperTradingSession.objects.filter(
            account=account,
            status="ACTIVE"
        ).first()
        
        if active_session:
            # Calculate session stats
            session_trades = PaperTrade.objects.filter(
                account=account,
                created_at__gte=active_session.started_at
            ).count()
            
            status_data = {
                'status': 'running',
                'session_id': str(active_session.session_id),
                'started_at': active_session.started_at.isoformat(),
                'duration_minutes': int((timezone.now() - active_session.started_at).total_seconds() / 60),
                'trades_executed': session_trades,
                'session_pnl': float(active_session.session_pnl_usd) if active_session.session_pnl_usd else 0,
                'config': active_session.session_config,
            }
        else:
            status_data = {
                'status': 'stopped',
                'message': 'No active trading session'
            }
        
        return JsonResponse(status_data)
        
    except Exception as e:
        logger.error(f"Error getting bot status: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)