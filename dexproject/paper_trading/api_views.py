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
from .services.price_feed_service import PriceFeedService
import asyncio
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Sum, Avg, Count
from django.utils import timezone
from django.core.cache import cache
from django.contrib.auth.models import User

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

# Import Celery tasks for bot control
from .tasks import run_paper_trading_bot, stop_paper_trading_bot

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTION TO GET DEFAULT USER
# =============================================================================

def get_default_user():
    """
    Get or create the default user for single-user operation.
    No authentication required.
    
    Returns:
        User: The default user instance
    """
    user, created = User.objects.get_or_create(
        username='demo_user',
        defaults={
            'email': 'user@localhost',
            'first_name': 'Default',
            'last_name': 'User'
        }
    )
    if created:
        logger.info("Created default user for paper trading API")
    return user


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
        # Get default user - no authentication required
        user = get_default_user()
        
        # Get or create account for user
        account = PaperTradingAccount.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        if not account:
            # Create account if it doesn't exist
            account = PaperTradingAccount.objects.create(
                user=user,
                name='My_Trading_Account',
                initial_balance_usd=Decimal('10000.00'),
                current_balance_usd=Decimal('10000.00'),
                is_active=True
            )
            logger.info(f"Created new paper trading account: {account.account_id}")
        
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
        # Get default user - no authentication required
        user = get_default_user()
            
        # Get or create account for user
        account = PaperTradingAccount.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        if not account:
            # Create account if it doesn't exist
            account = PaperTradingAccount.objects.create(
                user=user,
                name='My_Trading_Account',
                initial_balance_usd=Decimal('10000.00'),
                current_balance_usd=Decimal('10000.00'),
                is_active=True
            )
            logger.info(f"Created new paper trading account: {account.account_id}")
        
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
                'total_pnl': float(account.total_profit_loss_usd),
                'return_percent': float(account.get_roi()),
                'win_rate': float(account.get_win_rate()),
            },
            'positions': [],
            'summary': {
                'total_value': float(account.current_balance_usd),
                'positions_count': positions.count(),
                'cash_percentage': 100.0,
            },
            'timestamp': timezone.now().isoformat(),
        }
        
        # Process positions with calculated fields
        total_position_value = Decimal('0')
        for pos in positions:
            # Calculate unrealized_pnl_percent dynamically
            if pos.total_invested_usd and pos.total_invested_usd > 0:
                unrealized_pnl_percent = (pos.unrealized_pnl_usd / pos.total_invested_usd) * 100
            else:
                unrealized_pnl_percent = Decimal('0')
            
            position_dict = {
                'id': str(pos.position_id),
                'token_symbol': pos.token_symbol,
                'token_address': pos.token_address,
                'quantity': float(pos.quantity),
                'entry_price': float(pos.average_entry_price_usd) if pos.average_entry_price_usd else 0,
                'current_price': float(pos.current_price_usd) if pos.current_price_usd else 0,
                'current_value': float(pos.current_value_usd) if pos.current_value_usd else 0,
                'unrealized_pnl': float(pos.unrealized_pnl_usd),
                'unrealized_pnl_percent': float(unrealized_pnl_percent),
                'opened_at': pos.opened_at.isoformat(),
            }
            portfolio_data['positions'].append(position_dict)
            total_position_value += pos.current_value_usd or Decimal('0')
        
        # Update summary
        total_value = account.current_balance_usd + total_position_value
        portfolio_data['summary']['total_value'] = float(total_value)
        portfolio_data['summary']['cash_percentage'] = float(
            (account.current_balance_usd / total_value * 100) if total_value > 0 else 100
        )
        
        logger.debug(f"Portfolio data fetched")
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
        # Get default user - no authentication required
        user = get_default_user()
            
        # Get account for user
        account = PaperTradingAccount.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        if not account:
            # Create account if it doesn't exist
            account = PaperTradingAccount.objects.create(
                user=user,
                name='My_Trading_Account',
                initial_balance_usd=Decimal('10000.00'),
                current_balance_usd=Decimal('10000.00'),
                is_active=True
            )
            logger.info(f"Created new paper trading account: {account.account_id}")
        
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
        
        logger.debug(f"Trade data fetched: {len(trades_query)} trades")
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
        # Get default user - no authentication required
        user = get_default_user()
        
        # Get active account
        account = PaperTradingAccount.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        if not account:
            # Create account if it doesn't exist
            account = PaperTradingAccount.objects.create(
                user=user,
                name='My_Trading_Account',
                initial_balance_usd=Decimal('10000.00'),
                current_balance_usd=Decimal('10000.00'),
                is_active=True
            )
            logger.info(f"Created new paper trading account: {account.account_id}")
        
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
                'price': float(trade.amount_in_usd) if trade.amount_in_usd else 0,
                'status': trade.status.upper() if trade.status else 'PENDING',
                'created_at': trade.created_at.isoformat(),
                'execution_time_ms': trade.execution_time_ms,
            }
            
            # Add P&L if available
            if hasattr(trade, 'pnl_usd') and trade.pnl_usd is not None:
                trade_data['pnl_usd'] = float(trade.pnl_usd)
                trade_data['pnl_percent'] = float(trade.pnl_percent) if hasattr(trade, 'pnl_percent') and trade.pnl_percent else 0
            
            trades_data.append(trade_data)
        
        logger.debug(f"Recent trades fetched: {len(trades_data)} trades")
        
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
        # Get default user - no authentication required
        user = get_default_user()
        
        # Get active account
        account = PaperTradingAccount.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        if not account:
            # Create account if it doesn't exist
            account = PaperTradingAccount.objects.create(
                user=user,
                name='My_Trading_Account',
                initial_balance_usd=Decimal('10000.00'),
                current_balance_usd=Decimal('10000.00'),
                is_active=True
            )
            logger.info(f"Created new paper trading account: {account.account_id}")
        
        # Get open positions
        positions = PaperPosition.objects.filter(
            account=account,
            is_open=True
        ).order_by('-current_value_usd')
        
        # Build response data
        positions_data = []
        total_value = Decimal('0')
        total_pnl = Decimal('0')
        total_invested = Decimal('0')
        
        for position in positions:
            # Get current values with safe defaults
            current_value = position.current_value_usd or Decimal('0')
            invested = position.total_invested_usd or Decimal('0')
            unrealized_pnl = position.unrealized_pnl_usd or Decimal('0')
            
            # Calculate unrealized_pnl_percent dynamically
            if invested and invested > 0:
                unrealized_pnl_percent = (unrealized_pnl / invested) * 100
            else:
                unrealized_pnl_percent = Decimal('0')
            
            position_data = {
                'position_id': str(position.position_id),
                'token_symbol': position.token_symbol,
                'token_address': position.token_address,
                'quantity': float(position.quantity),
                'average_entry_price_usd': float(position.average_entry_price_usd) if position.average_entry_price_usd else 0,
                'current_price_usd': float(position.current_price_usd) if position.current_price_usd else 0,
                'current_value_usd': float(current_value),
                'cost_basis_usd': float(invested),
                'total_invested_usd': float(invested),
                'unrealized_pnl_usd': float(unrealized_pnl),
                'unrealized_pnl_percent': float(unrealized_pnl_percent),
                'opened_at': position.opened_at.isoformat() if position.opened_at else None,
                'last_updated': position.last_updated.isoformat() if position.last_updated else None,
            }
            
            positions_data.append(position_data)
            total_value += current_value
            total_pnl += unrealized_pnl
            total_invested += invested
        
        # Calculate summary metrics
        total_unrealized_pnl_percent = float(
            (total_pnl / total_invested * 100) if total_invested > 0 else 0
        )
        
        summary = {
            'total_positions': len(positions_data),
            'total_value_usd': float(total_value),
            'total_cost_basis_usd': float(total_invested),
            'total_unrealized_pnl_usd': float(total_pnl),
            'total_unrealized_pnl_percent': total_unrealized_pnl_percent
        }
        
        logger.debug(f"Open positions fetched: {len(positions_data)} positions")
        
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
        # Get default user - no authentication required
        user = get_default_user()
        
        # Get active account
        account = PaperTradingAccount.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        if not account:
            # Create account if it doesn't exist
            account = PaperTradingAccount.objects.create(
                user=user,
                name='My_Trading_Account',
                initial_balance_usd=Decimal('10000.00'),
                current_balance_usd=Decimal('10000.00'),
                is_active=True
            )
            logger.info(f"Created new paper trading account: {account.account_id}")
        
        # ✅ CALCULATE POSITIONS VALUE
        open_positions = PaperPosition.objects.filter(account=account, is_open=True)
        positions_value = sum(pos.current_value_usd or Decimal('0') for pos in open_positions)
        portfolio_value = account.current_balance_usd + positions_value
        
        # ✅ CALCULATE CORRECT RETURN PERCENTAGE
        return_percent = float(
            ((portfolio_value - account.initial_balance_usd) / account.initial_balance_usd * 100)
            if account.initial_balance_usd > 0 else 0
        )
        
        # Get 24h stats
        time_24h_ago = timezone.now() - timedelta(hours=24)
        trades_24h_data = PaperTrade.objects.filter(
            account=account,
            created_at__gte=time_24h_ago
        ).aggregate(
            count=Count('trade_id'),
            total_volume=Sum('amount_in_usd')
        )
        
        metrics = {
            'success': True,
            'current_balance': float(account.current_balance_usd),
            'initial_balance': float(account.initial_balance_usd),
            'positions_value': float(positions_value),        # ✅ ADD THIS
            'portfolio_value': float(portfolio_value),         # ✅ ADD THIS
            'total_pnl': float(account.total_profit_loss_usd),
            'return_percent': return_percent,                  # ✅ NOW CORRECT
            'win_rate': float(account.get_win_rate()) if account.get_win_rate() else 0,
            'trades_24h': trades_24h_data['count'] or 0,
            'volume_24h': float(trades_24h_data['total_volume']) if trades_24h_data['total_volume'] else 0,
            'total_trades': account.total_trades,
            'successful_trades': account.winning_trades,
            'failed_trades': account.losing_trades,
            'timestamp': timezone.now().isoformat()
        }
        
        logger.debug(f"Metrics fetched: portfolio=${portfolio_value:.2f}, pnl=${account.total_profit_loss_usd:.2f}")
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
        # Get default user - no authentication required
        user = get_default_user()
        
        # Get or create account
        account = PaperTradingAccount.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        if not account:
            # Create account if it doesn't exist
            account = PaperTradingAccount.objects.create(
                user=user,
                name='My_Trading_Account',
                initial_balance_usd=Decimal('10000.00'),
                current_balance_usd=Decimal('10000.00'),
                is_active=True
            )
            logger.info(f"Created new paper trading account: {account.account_id}")
        
        if request.method == 'GET':
            # Get current configuration
            config = PaperStrategyConfiguration.objects.filter(
                account=account,
                is_active=True
            ).first()
            
            if config:
                config_data = {
                    'strategy_name': config.name,
                    'is_active': config.is_active,
                    'trading_mode': config.trading_mode,
                    'use_fast_lane': config.use_fast_lane,
                    'use_smart_lane': config.use_smart_lane,
                    'fast_lane_threshold_usd': float(config.fast_lane_threshold_usd),
                    'max_position_size_percent': float(config.max_position_size_percent),
                    'stop_loss_percent': float(config.stop_loss_percent),
                    'take_profit_percent': float(config.take_profit_percent),
                    'max_daily_trades': config.max_daily_trades,
                    'max_concurrent_positions': config.max_concurrent_positions,
                    'min_liquidity_usd': float(config.min_liquidity_usd),
                    'max_slippage_percent': float(config.max_slippage_percent),
                    'confidence_threshold': float(config.confidence_threshold),
                    'created_at': config.created_at.isoformat(),
                    'updated_at': config.updated_at.isoformat(),
                }
            else:
                # Create default configuration
                config = PaperStrategyConfiguration.objects.create(
                    account=account,
                    name='Default Strategy',
                    is_active=True,
                    trading_mode='MODERATE',
                    use_fast_lane=True,
                    use_smart_lane=False,
                    fast_lane_threshold_usd=Decimal('100'),
                    max_position_size_percent=Decimal('5.0'),
                    stop_loss_percent=Decimal('5.0'),
                    take_profit_percent=Decimal('10.0'),
                    max_daily_trades=20,
                    max_concurrent_positions=5,
                    min_liquidity_usd=Decimal('10000'),
                    max_slippage_percent=Decimal('1.0'),
                    confidence_threshold=Decimal('60')
                )
                config_data = {
                    'strategy_name': config.name,
                    'is_active': config.is_active,
                    'trading_mode': config.trading_mode,
                    'message': 'Created default configuration'
                }
            
            return JsonResponse(config_data)
            
        elif request.method == 'POST':
            # Update configuration
            try:
                data = json.loads(request.body)
                
                config, created = PaperStrategyConfiguration.objects.update_or_create(
                    account=account,
                    name=data.get('strategy_name', 'default'),
                    defaults={
                        'is_active': data.get('is_active', True),
                        'trading_mode': data.get('trading_mode', 'MODERATE'),
                        'use_fast_lane': data.get('use_fast_lane', True),
                        'use_smart_lane': data.get('use_smart_lane', False),
                        'fast_lane_threshold_usd': Decimal(str(data.get('fast_lane_threshold_usd', 100))),
                        'max_position_size_percent': Decimal(str(data.get('max_position_size_percent', 5.0))),
                        'stop_loss_percent': Decimal(str(data.get('stop_loss_percent', 5.0))),
                        'take_profit_percent': Decimal(str(data.get('take_profit_percent', 10.0))),
                        'max_daily_trades': data.get('max_daily_trades', 20),
                        'max_concurrent_positions': data.get('max_concurrent_positions', 5),
                        'min_liquidity_usd': Decimal(str(data.get('min_liquidity_usd', 10000))),
                        'max_slippage_percent': Decimal(str(data.get('max_slippage_percent', 1.0))),
                        'confidence_threshold': Decimal(str(data.get('confidence_threshold', 60))),
                        'allowed_tokens': data.get('allowed_tokens', []),
                        'blocked_tokens': data.get('blocked_tokens', []),
                        'custom_parameters': data.get('custom_parameters', {}),
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
        # Get default user - no authentication required
        user = get_default_user()
        
        # Get account
        account = PaperTradingAccount.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        if not account:
            # Create account if it doesn't exist
            account = PaperTradingAccount.objects.create(
                user=user,
                name='My_Trading_Account',
                initial_balance_usd=Decimal('10000.00'),
                current_balance_usd=Decimal('10000.00'),
                is_active=True
            )
            logger.info(f"Created new paper trading account: {account.account_id}")
        
        # Get active sessions
        active_sessions = PaperTradingSession.objects.filter(
            account=account,
            status__in=['STARTING', 'RUNNING', 'PAUSED']
        )
        
        # Get latest metrics
        latest_metrics = None
        if active_sessions.exists():
            latest_metrics = PaperPerformanceMetrics.objects.filter(
                session__in=active_sessions
            ).order_by('-created_at').first()
        
        if not latest_metrics:
            # Try to get any metrics for this account
            all_sessions = PaperTradingSession.objects.filter(account=account)
            if all_sessions.exists():
                latest_metrics = PaperPerformanceMetrics.objects.filter(
                    session__in=all_sessions
                ).order_by('-created_at').first()
        
        if latest_metrics:
            metrics_data = {
                'sharpe_ratio': float(latest_metrics.sharpe_ratio) if latest_metrics.sharpe_ratio else 0,
                'max_drawdown': float(latest_metrics.max_drawdown_percent) if latest_metrics.max_drawdown_percent else 0,
                'win_rate': float(latest_metrics.win_rate) if latest_metrics.win_rate else 0,
                'profit_factor': float(latest_metrics.profit_factor) if latest_metrics.profit_factor else 0,
                'average_win': float(latest_metrics.average_win_usd) if latest_metrics.average_win_usd else 0,
                'average_loss': float(latest_metrics.average_loss_usd) if latest_metrics.average_loss_usd else 0,
                'best_trade': float(latest_metrics.largest_win_usd) if latest_metrics.largest_win_usd else 0,
                'worst_trade': float(latest_metrics.largest_loss_usd) if latest_metrics.largest_loss_usd else 0,
                'total_trades': latest_metrics.total_trades,
                'winning_trades': latest_metrics.winning_trades,
                'losing_trades': latest_metrics.losing_trades,
                'total_pnl_usd': float(latest_metrics.total_pnl_usd),
                'total_pnl_percent': float(latest_metrics.total_pnl_percent),
                # REMOVED IN MIGRATION:                 'avg_execution_time_ms': latest_metrics.avg_execution_time_ms,
                # REMOVED IN MIGRATION:                 'total_gas_fees_usd': float(latest_metrics.total_gas_fees_usd),
                # REMOVED IN MIGRATION:                 'avg_slippage_percent': float(latest_metrics.avg_slippage_percent),
                # REMOVED IN MIGRATION:                 'fast_lane_trades': latest_metrics.fast_lane_trades,
                # REMOVED IN MIGRATION:                 'smart_lane_trades': latest_metrics.smart_lane_trades,
                # REMOVED IN MIGRATION:                 'fast_lane_win_rate': float(latest_metrics.fast_lane_win_rate),
                # REMOVED IN MIGRATION:                 'smart_lane_win_rate': float(latest_metrics.smart_lane_win_rate),
                'period_start': latest_metrics.period_start.isoformat(),
                'period_end': latest_metrics.period_end.isoformat(),
                'calculated_at': latest_metrics.created_at.isoformat(),
            }
        else:
            # Return default metrics if none exist
            metrics_data = {
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'win_rate': float(account.get_win_rate()) if account.get_win_rate() else 0,
                'profit_factor': 0,
                'average_win': 0,
                'average_loss': 0,
                'best_trade': 0,
                'worst_trade': 0,
                'total_trades': account.total_trades,
                'winning_trades': account.winning_trades,
                'losing_trades': account.losing_trades,
                'total_pnl_usd': float(account.total_profit_loss_usd),
                'total_pnl_percent': float(account.get_roi()),
                'message': 'No performance metrics calculated yet'
            }
        
        # Add account-level stats
        metrics_data['account_stats'] = {
            'total_pnl': float(account.total_profit_loss_usd),
            'total_return': float(account.get_roi()),
            'current_balance': float(account.current_balance_usd),
            'initial_balance': float(account.initial_balance_usd),
            'total_trades': account.total_trades,
            'successful_trades': account.winning_trades,
            'failed_trades': account.losing_trades,
            'win_rate': float(account.get_win_rate()) if account.get_win_rate() else 0,
        }
        
        logger.debug(f"Performance metrics fetched")
        return JsonResponse(metrics_data)
        
    except Exception as e:
        logger.error(f"Error in performance metrics API: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# BOT CONTROL API - NO AUTHENTICATION REQUIRED
# =============================================================================

@require_http_methods(["POST"])
@csrf_exempt
def api_start_bot(request: HttpRequest) -> JsonResponse:
    """
    Start paper trading bot.
    
    Creates a new trading session and initiates the bot process via Celery.
    
    Returns:
        JsonResponse: Bot status with session ID and Celery task ID
    """
    try:
        # Get default user - no authentication required
        user = get_default_user()
        
        # Get or create account for user
        account = PaperTradingAccount.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        if not account:
            # Create default account if none exists
            account = PaperTradingAccount.objects.create(
                user=user,
                name="My_Trading_Account",
                initial_balance_usd=Decimal('10000.00'),
                current_balance_usd=Decimal('10000.00'),
                is_active=True
            )
            logger.info(f"Created new paper trading account: {account.account_id}")
        
        # Check if there's already an active session
        active_session = PaperTradingSession.objects.filter(
            account=account,
            status__in=['STARTING', 'RUNNING', 'PAUSED']
        ).first()
        
        if active_session:
            return JsonResponse({
                'success': False,
                'error': 'Bot is already running',
                'session_id': str(active_session.session_id),
                'status': active_session.status
            }, status=400)
        
        # Get active strategy configuration
        strategy_config = PaperStrategyConfiguration.objects.filter(
            account=account,
            is_active=True
        ).first()
        
        # Parse request body for session config
        session_config = {}
        runtime_minutes = None
        if request.body:
            try:
                body_data = json.loads(request.body)
                session_config = body_data.get('config', {})
                runtime_minutes = body_data.get('runtime_minutes')
            except json.JSONDecodeError:
                pass
        
        # Create new trading session
        session = PaperTradingSession.objects.create(
            account=account,
            strategy_config=strategy_config,
            status='STARTING',
            name=session_config.get('name', f'Session {timezone.now().strftime("%Y%m%d_%H%M%S")}'),
            starting_balance_usd=account.current_balance_usd,
            config_snapshot=session_config
        )
        
        # Start the bot via Celery task
        task_result = run_paper_trading_bot.delay(
            session_id=str(session.session_id),
            user_id=user.id,
            runtime_minutes=runtime_minutes
        )
        
        # Store task ID in session metadata
        session.metadata = session.metadata or {}
        session.metadata['celery_task_id'] = task_result.id
        session.save()
        
        logger.info(
            f"Started paper trading session {session.session_id} with task {task_result.id}"
        )
        
        return JsonResponse({
            'success': True,
            'session_id': str(session.session_id),
            'task_id': task_result.id,
            'message': 'Paper trading bot started',
            'status': 'starting',
            'account_balance': float(account.current_balance_usd)
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
    
    Ends active trading sessions and stops the bot process via Celery.
    
    Returns:
        JsonResponse: Bot status with number of sessions ended
    """
    try:
        # Get default user - no authentication required
        user = get_default_user()
        
        # Get account
        account = PaperTradingAccount.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        # Find active sessions for this user
        active_sessions = PaperTradingSession.objects.filter(
            account=account,
            status__in=['STARTING', 'RUNNING', 'PAUSED']
        )
        
        sessions_ended = 0
        tasks_stopped = []
        
        if active_sessions.count() == 0:
            return JsonResponse({
                'success': False,
                'error': 'No active bot session found',
                'sessions_ended': 0
            }, status=400)
        
        # Parse request body for stop reason
        stop_reason = "User requested stop"
        if request.body:
            try:
                body_data = json.loads(request.body)
                stop_reason = body_data.get('reason', stop_reason)
            except json.JSONDecodeError:
                pass
        
        # Stop each active session via Celery
        for session in active_sessions:
            # Call stop task
            task_result = stop_paper_trading_bot.delay(
                session_id=str(session.session_id),
                user_id=user.id,
                reason=stop_reason
            )
            
            tasks_stopped.append({
                'session_id': str(session.session_id),
                'task_id': task_result.id
            })
            
            sessions_ended += 1
            
            logger.info(
                f"Stopping paper trading session {session.session_id} with task {task_result.id}"
            )
        
        return JsonResponse({
            'success': True,
            'sessions_ended': sessions_ended,
            'tasks_stopped': tasks_stopped,
            'message': f'Stopped {sessions_ended} paper trading bot session(s)',
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
        JsonResponse: Bot status and metrics
    """
    try:
        # Get default user - no authentication required
        user = get_default_user()
        
        # Get account
        account = PaperTradingAccount.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({
                'status': 'no_account',
                'message': 'No paper trading account found'
            })
        
        # Find active sessions
        active_sessions = PaperTradingSession.objects.filter(
            account=account,
            status__in=['STARTING', 'RUNNING', 'PAUSED']
        ).order_by('-started_at')
        
        # Get recent completed sessions
        recent_sessions = PaperTradingSession.objects.filter(
            account=account,
            status__in=['COMPLETED', 'STOPPED']
        ).order_by('-ended_at')[:5]
        
        # Build response
        sessions_data = []
        for session in active_sessions:
            session_data = {
                'session_id': str(session.session_id),
                'status': session.status,
                'name': session.name,
                'started_at': session.started_at.isoformat() if session.started_at else None,
                'current_pnl': float(
                    account.current_balance_usd - session.starting_balance_usd
                ),
                'trades_executed': session.total_trades_executed or 0
            }
            
            # Add Celery task status if available
            if session.metadata and 'celery_task_id' in session.metadata:
                from celery.result import AsyncResult
                task_id = session.metadata['celery_task_id']
                task_result = AsyncResult(task_id)
                session_data['task_status'] = task_result.status
                session_data['task_id'] = task_id
            
            sessions_data.append(session_data)
        
        # Add recent sessions summary
        recent_data = []
        for session in recent_sessions:
            recent_data.append({
                'session_id': str(session.session_id),
                'name': session.name,
                'ended_at': session.ended_at.isoformat() if session.ended_at else None,
                'final_pnl': float(session.session_pnl_usd) if session.session_pnl_usd else 0,
                'trades': session.total_trades_executed or 0
            })
        
        logger.debug(f"Bot status fetched")
        
        return JsonResponse({
            'success': True,
            'account_balance': float(account.current_balance_usd),
            'active_sessions': sessions_data,
            'recent_sessions': recent_data,
            'bot_running': len(sessions_data) > 0
        })
        
    except Exception as e:
        logger.error(f"Error getting bot status: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)