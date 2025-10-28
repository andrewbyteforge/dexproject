"""
Paper Trading Data API - Read-Only Endpoints

This module provides all read-only API endpoints for data retrieval including
AI thoughts, portfolio data, trades, positions, and performance metrics.

File: paper_trading/api/data_api.py
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List
import asyncio

from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Sum, Avg, Count
from django.utils import timezone

# Import models
from ..models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperAIThoughtLog,
    PaperPerformanceMetrics,
)

# Import constants for field names
from ..constants import (
    ThoughtLogFields,
    TradeFields,
    SessionStatus,
)

# Import utilities
from ..utils import get_default_user, get_single_trading_account
from ..services.price_feed_service import PriceFeedService

logger = logging.getLogger(__name__)


# =============================================================================
# AI THOUGHTS API
# =============================================================================

@require_http_methods(["GET"])
def api_ai_thoughts(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for AI thought logs with real-time updates.
    
    Returns recent AI decision-making thoughts for transparency.
    
    Query Parameters:
        limit (int): Number of thoughts to return (default: 10)
        since (datetime): Return thoughts after this timestamp
        
    Returns:
        JsonResponse: List of AI thought logs with reasoning
    """
    try:
        # Get default user and account
        user = get_default_user()
        account = get_single_trading_account()
        
        # Parse query parameters
        limit = int(request.GET.get('limit', 10))
        limit = min(limit, 100)  # Cap at 100 for performance
        
        since_param = request.GET.get('since')
        
        # Build query
        thoughts_query = PaperAIThoughtLog.objects.filter(
            account=account
        ).select_related('account')
        
        # Filter by timestamp if provided
        if since_param:
            try:
                since_dt = datetime.fromisoformat(since_param.replace('Z', '+00:00'))
                thoughts_query = thoughts_query.filter(
                    created_at__gt=since_dt
                )
            except ValueError:
                logger.warning(f"Invalid 'since' parameter: {since_param}")
        
        # Get most recent thoughts
        thoughts = thoughts_query.order_by('-created_at')[:limit]
        
        # Format thoughts for response
        thoughts_data = []
        for thought in thoughts:
            thoughts_data.append({
                ThoughtLogFields.THOUGHT_ID: str(thought.thought_id),
                ThoughtLogFields.DECISION_TYPE: thought.decision_type,
                ThoughtLogFields.TOKEN_SYMBOL: thought.token_symbol,
                ThoughtLogFields.TOKEN_ADDRESS: thought.token_address,
                ThoughtLogFields.CONFIDENCE_LEVEL: thought.confidence_level,
                ThoughtLogFields.CONFIDENCE_PERCENT: float(thought.confidence_percent),
                ThoughtLogFields.RISK_SCORE: float(thought.risk_score),
                ThoughtLogFields.OPPORTUNITY_SCORE: float(thought.opportunity_score),
                ThoughtLogFields.PRIMARY_REASONING: thought.primary_reasoning,
                ThoughtLogFields.KEY_FACTORS: thought.key_factors or [],
                ThoughtLogFields.POSITIVE_SIGNALS: thought.positive_signals or [],
                ThoughtLogFields.NEGATIVE_SIGNALS: thought.negative_signals or [],
                ThoughtLogFields.MARKET_DATA: thought.market_data or {},
                ThoughtLogFields.STRATEGY_NAME: thought.strategy_name or '',
                ThoughtLogFields.LANE_USED: thought.lane_used or '',
                ThoughtLogFields.CREATED_AT: thought.created_at.isoformat(),
                ThoughtLogFields.ANALYSIS_TIME_MS: thought.analysis_time_ms or 0,
            })
        
        logger.debug(f"Fetched {len(thoughts_data)} AI thoughts")
        return JsonResponse({
            'success': True,
            'thoughts': thoughts_data,
            'count': len(thoughts_data)
        })
        
    except Exception as e:
        logger.error(f"Error in AI thoughts API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# PORTFOLIO DATA API
# =============================================================================

@require_http_methods(["GET"])
def api_portfolio_data(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for complete portfolio state.
    
    Returns current portfolio holdings, cash balance, and total value.
    
    Returns:
        JsonResponse: Portfolio summary with all positions
    """
    try:
        account = get_single_trading_account()
        
        # Get all open positions
        open_positions = PaperPosition.objects.filter(
            account=account,
            status='OPEN'
        ).order_by('-current_value_usd')
        
        # Format positions
        positions_data = []
        for position in open_positions:
            positions_data.append({
                'position_id': str(position.position_id),
                'token_symbol': position.token_symbol,
                'token_address': position.token_address,
                'amount_token': float(position.amount_token),
                'entry_price': float(position.entry_price),
                'current_price': float(position.current_price),
                'current_value_usd': float(position.current_value_usd),
                'total_cost_usd': float(position.total_cost_usd),
                'unrealized_pnl_usd': float(position.unrealized_pnl_usd),
                'unrealized_pnl_percent': float(position.unrealized_pnl_percent),
                'opened_at': position.opened_at.isoformat(),
            })
        
        # Calculate totals
        total_value = sum(float(p.current_value_usd) for p in open_positions)
        cash_balance = float(account.current_balance_usd)
        portfolio_value = total_value + cash_balance
        
        return JsonResponse({
            'success': True,
            'portfolio': {
                'cash_balance': cash_balance,
                'positions_value': total_value,
                'total_value': portfolio_value,
                'positions': positions_data,
                'positions_count': len(positions_data),
            }
        })
        
    except Exception as e:
        logger.error(f"Error in portfolio data API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# TRADES DATA API
# =============================================================================

@require_http_methods(["GET"])
def api_trades_data(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for trade history with filtering.
    
    Query Parameters:
        limit (int): Number of trades to return (default: 50)
        decision_type (str): Filter by BUY, SELL, etc.
        status (str): Filter by trade status
        since (datetime): Trades after this timestamp
        
    Returns:
        JsonResponse: List of trades with details
    """
    try:
        account = get_single_trading_account()
        
        # Parse query parameters
        limit = int(request.GET.get('limit', 50))
        limit = min(limit, 500)
        
        decision_type = request.GET.get('decision_type')
        status = request.GET.get('status')
        since_param = request.GET.get('since')
        
        # Build query
        trades_query = PaperTrade.objects.filter(
            account=account
        ).select_related('account', 'session')
        
        # Apply filters
        if decision_type:
            trades_query = trades_query.filter(decision_type=decision_type)
        
        if status:
            trades_query = trades_query.filter(status=status)
        
        if since_param:
            try:
                since_dt = datetime.fromisoformat(since_param.replace('Z', '+00:00'))
                trades_query = trades_query.filter(executed_at__gt=since_dt)
            except ValueError:
                logger.warning(f"Invalid 'since' parameter: {since_param}")
        
        # Get trades
        trades = trades_query.order_by('-executed_at')[:limit]
        
        # Format trades
        trades_data = []
        for trade in trades:
            trades_data.append({
                TradeFields.TRADE_ID: str(trade.trade_id),
                TradeFields.DECISION_TYPE: trade.decision_type,
                TradeFields.TOKEN_SYMBOL: trade.token_symbol,
                TradeFields.TOKEN_ADDRESS: trade.token_address,
                TradeFields.AMOUNT_TOKEN: float(trade.amount_token),
                TradeFields.AMOUNT_USD: float(trade.amount_usd),
                TradeFields.ENTRY_PRICE: float(trade.entry_price) if trade.entry_price else None,
                TradeFields.EXIT_PRICE: float(trade.exit_price) if trade.exit_price else None,
                TradeFields.STATUS: trade.status,
                TradeFields.EXECUTED_AT: trade.executed_at.isoformat(),
                TradeFields.PROFIT_LOSS_USD: float(trade.profit_loss_usd) if trade.profit_loss_usd else 0,
                TradeFields.PROFIT_LOSS_PERCENT: float(trade.profit_loss_percent) if trade.profit_loss_percent else 0,
            })
        
        return JsonResponse({
            'success': True,
            'trades': trades_data,
            'count': len(trades_data)
        })
        
    except Exception as e:
        logger.error(f"Error in trades data API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# RECENT TRADES API
# =============================================================================

@require_http_methods(["GET"])
def api_recent_trades(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for most recent trades (last 24 hours).
    
    Returns:
        JsonResponse: Recent trades list
    """
    try:
        account = get_single_trading_account()
        
        # Get trades from last 24 hours
        since_time = timezone.now() - timedelta(hours=24)
        recent_trades = PaperTrade.objects.filter(
            account=account,
            executed_at__gte=since_time
        ).order_by('-executed_at')[:20]
        
        # Format trades
        trades_data = []
        for trade in recent_trades:
            trades_data.append({
                'trade_id': str(trade.trade_id),
                'decision_type': trade.decision_type,
                'token_symbol': trade.token_symbol,
                'amount_usd': float(trade.amount_usd),
                'executed_at': trade.executed_at.isoformat(),
                'profit_loss_usd': float(trade.profit_loss_usd) if trade.profit_loss_usd else 0,
            })
        
        return JsonResponse({
            'success': True,
            'trades': trades_data,
            'count': len(trades_data)
        })
        
    except Exception as e:
        logger.error(f"Error in recent trades API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# OPEN POSITIONS API
# =============================================================================

@require_http_methods(["GET"])
def api_open_positions(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for current open positions.
    
    Returns:
        JsonResponse: List of open positions with current values
    """
    try:
        account = get_single_trading_account()
        
        # Get all open positions
        open_positions = PaperPosition.objects.filter(
            account=account,
            status='OPEN'
        ).order_by('-current_value_usd')
        
        # Format positions
        positions_data = []
        for position in open_positions:
            positions_data.append({
                'position_id': str(position.position_id),
                'token_symbol': position.token_symbol,
                'amount_token': float(position.amount_token),
                'entry_price': float(position.entry_price),
                'current_price': float(position.current_price),
                'current_value_usd': float(position.current_value_usd),
                'unrealized_pnl_usd': float(position.unrealized_pnl_usd),
                'unrealized_pnl_percent': float(position.unrealized_pnl_percent),
                'opened_at': position.opened_at.isoformat(),
            })
        
        return JsonResponse({
            'success': True,
            'positions': positions_data,
            'count': len(positions_data)
        })
        
    except Exception as e:
        logger.error(f"Error in open positions API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# METRICS API
# =============================================================================

@require_http_methods(["GET"])
def api_metrics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for key performance metrics.
    
    Returns:
        JsonResponse: Dashboard KPIs and statistics
    """
    try:
        account = get_single_trading_account()
        
        # Calculate basic metrics
        total_trades = PaperTrade.objects.filter(account=account).count()
        winning_trades = PaperTrade.objects.filter(
            account=account,
            profit_loss_usd__gt=0
        ).count()
        
        # Calculate win rate
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Get total P&L
        total_pnl = float(account.total_profit_loss_usd)
        
        # Get open positions value
        open_positions_value = PaperPosition.objects.filter(
            account=account,
            status='OPEN'
        ).aggregate(total=Sum('current_value_usd'))['total'] or 0
        
        portfolio_value = float(account.current_balance_usd) + float(open_positions_value)
        
        return JsonResponse({
            'success': True,
            'metrics': {
                'portfolio_value': portfolio_value,
                'cash_balance': float(account.current_balance_usd),
                'total_pnl': total_pnl,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': total_trades - winning_trades,
                'win_rate': round(win_rate, 2),
                'roi': float(account.get_roi()) if hasattr(account, 'get_roi') else 0,
            }
        })
        
    except Exception as e:
        logger.error(f"Error in metrics API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# PERFORMANCE METRICS API
# =============================================================================

@require_http_methods(["GET"])
def api_performance_metrics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for detailed performance metrics.
    
    Returns:
        JsonResponse: Comprehensive performance statistics
    """
    try:
        account = get_single_trading_account()
        
        # Get latest performance metrics
        latest_metrics = PaperPerformanceMetrics.objects.filter(
            account=account
        ).order_by('-updated_at').first()
        
        if not latest_metrics:
            return JsonResponse({
                'success': True,
                'metrics': {},
                'message': 'No performance metrics calculated yet'
            })
        
        # Format metrics
        metrics_data = {
            'total_pnl': float(latest_metrics.total_pnl_usd),
            'total_return_percent': float(latest_metrics.total_return_percent),
            'win_rate': float(latest_metrics.win_rate),
            'profit_factor': float(latest_metrics.profit_factor) if latest_metrics.profit_factor else 0,
            'sharpe_ratio': float(latest_metrics.sharpe_ratio) if latest_metrics.sharpe_ratio else 0,
            'max_drawdown': float(latest_metrics.max_drawdown_percent) if latest_metrics.max_drawdown_percent else 0,
            'avg_win': float(latest_metrics.avg_win_usd) if latest_metrics.avg_win_usd else 0,
            'avg_loss': float(latest_metrics.avg_loss_usd) if latest_metrics.avg_loss_usd else 0,
            'largest_win': float(latest_metrics.largest_win_usd) if latest_metrics.largest_win_usd else 0,
            'largest_loss': float(latest_metrics.largest_loss_usd) if latest_metrics.largest_loss_usd else 0,
            'total_trades': latest_metrics.total_trades,
            'winning_trades': latest_metrics.winning_trades,
            'losing_trades': latest_metrics.losing_trades,
        }
        
        # Add account-level stats
        metrics_data['account_stats'] = {
            'total_pnl': float(account.total_profit_loss_usd),
            'total_return': float(account.get_roi()) if hasattr(account, 'get_roi') else 0,
            'current_balance': float(account.current_balance_usd),
            'initial_balance': float(account.initial_balance_usd),
            'total_trades': account.total_trades,
            'successful_trades': account.winning_trades,
            'failed_trades': account.losing_trades,
            'win_rate': float(account.get_win_rate()) if hasattr(account, 'get_win_rate') else 0,
        }
        
        logger.debug("Performance metrics fetched")
        return JsonResponse({
            'success': True,
            'metrics': metrics_data
        })
        
    except Exception as e:
        logger.error(f"Error in performance metrics API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# TOKEN PRICE API
# =============================================================================

@require_http_methods(["GET"])
def api_token_price(request: HttpRequest, token_symbol: str) -> JsonResponse:
    """
    API endpoint for token price lookup.
    
    Args:
        token_symbol: Token symbol to look up
        
    Returns:
        JsonResponse: Current token price data
    """
    try:
        # Initialize price service
        price_service = PriceFeedService()
        
        # Get token price
        price_data = asyncio.run(price_service.get_token_price(token_symbol))
        
        if not price_data:
            return JsonResponse({
                'success': False,
                'error': f'Price not found for {token_symbol}'
            }, status=404)
        
        return JsonResponse({
            'success': True,
            'token': token_symbol,
            'price': price_data
        })
        
    except Exception as e:
        logger.error(f"Error in token price API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)