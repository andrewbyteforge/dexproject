"""
Paper Trading Views - Complete Dashboard and API Implementation

This module provides all views for the paper trading dashboard and API endpoints.
Includes portfolio display, trade history, configuration management, and real-time data.

File: dexproject/paper_trading/views.py
"""

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Avg, Count, F
from django.utils import timezone
from django.contrib import messages
from django.core.cache import cache
from django.contrib.auth.decorators import login_required

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
# DASHBOARD VIEWS
# =============================================================================


def paper_trading_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Main paper trading dashboard view.
    
    Displays portfolio summary, active positions, recent trades,
    and performance metrics with AI thought logs.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered dashboard template with context data
    """
    try:
        from django.contrib.auth.models import User
        
        # Get demo user for now (will be replaced with actual user)
        try:
            demo_user = User.objects.get(username='demo_user')
        except User.DoesNotExist:
            # Create demo user if it doesn't exist
            demo_user = User.objects.create_user(
                username='demo_user',
                email='demo@example.com',
                password='demo_password'
            )
            logger.info("Created demo_user for paper trading")
        
        # Get or create paper trading account
        account, created = PaperTradingAccount.objects.get_or_create(
            user=demo_user,
            is_active=True,
            defaults={
                'name': 'Demo Paper Trading Account',
                'initial_balance_usd': Decimal('10000.00'),
                'current_balance_usd': Decimal('10000.00')
            }
        )
        
        if created:
            logger.info(f"Created new paper trading account: {account.account_id}")
        
        # Get active session if exists
        active_session = PaperTradingSession.objects.filter(
            account=account,
            status="ACTIVE"
        ).first()
        
        # Get recent trades
        recent_trades = PaperTrade.objects.filter(
            account=account
        ).order_by('-created_at')[:10]
        
        # Get open positions
        open_positions = PaperPosition.objects.filter(
            account=account,
            is_open=True
        ).order_by('-current_value_usd')
        
        # Get recent AI thoughts
        recent_thoughts = PaperAIThoughtLog.objects.filter(
            account=account
        ).order_by('-created_at')[:5]
        
        # Get performance metrics
        performance = PaperPerformanceMetrics.objects.filter(
            account=account
        ).order_by('-created_at').first()
        
        # Calculate summary statistics
        total_trades = account.total_trades
        successful_trades = account.winning_trades
        
        # Get 24h stats
        time_24h_ago = timezone.now() - timedelta(hours=24)
        trades_24h = PaperTrade.objects.filter(
            account=account,
            created_at__gte=time_24h_ago
        ).aggregate(
            count=Count('trade_id'),
            total_volume=Sum('amount_in_usd')
        )
        
        context = {
            'page_title': 'Paper Trading Dashboard',
            'account': account,
            'active_session': active_session,
            'recent_trades': recent_trades,
            'open_positions': open_positions,
            'performance': performance,
            'recent_thoughts': recent_thoughts,
            'total_trades': total_trades,
            'successful_trades': successful_trades,
            'win_rate': (successful_trades / total_trades * 100) if total_trades > 0 else 0,
            'trades_24h': trades_24h['count'] or 0,
            'volume_24h': trades_24h['total_volume'] or 0,
            'current_balance': account.current_balance_usd,
            'initial_balance': account.initial_balance_usd,
            'total_pnl': account.total_pnl_usd,
            'return_percent': account.total_return_percent,
        }
        
        return render(request, 'paper_trading/dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Error loading paper trading dashboard: {e}", exc_info=True)
        messages.error(request, f"Error loading dashboard: {str(e)}")
        return render(request, 'paper_trading/error.html', {"error": str(e)})



















def trade_history(request: HttpRequest) -> HttpResponse:
    """
    Display detailed trade history with filtering and pagination.
    
    Args:
        request: Django HTTP request with optional filters
        
    Returns:
        Rendered trade history template
    """
    try:
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
        
        account = get_object_or_404(
            PaperTradingAccount,
            user=demo_user,
            is_active=True
        )
        
        # Build query with filters
        trades_query = PaperTrade.objects.filter(account=account)
        
        # Apply filters
        status_filter = request.GET.get('status')
        if status_filter:
            trades_query = trades_query.filter(status=status_filter)
        
        trade_type = request.GET.get('type')
        if trade_type:
            trades_query = trades_query.filter(trade_type=trade_type)
        
        token_symbol = request.GET.get('token')
        if token_symbol:
            trades_query = trades_query.filter(
                Q(token_in_symbol__icontains=token_symbol) | 
                Q(token_out_symbol__icontains=token_symbol)
            )
        
        # Date range filter
        date_from = request.GET.get('date_from')
        if date_from:
            trades_query = trades_query.filter(created_at__gte=date_from)
        
        date_to = request.GET.get('date_to')
        if date_to:
            trades_query = trades_query.filter(created_at__lte=date_to)
        
        # Order by creation date
        trades_query = trades_query.order_by('-created_at')
        
        # Pagination
        paginator = Paginator(trades_query, 25)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Calculate summary stats for filtered results
        summary_stats = trades_query.aggregate(
            total_trades=Count('trade_id'),
            total_volume=Sum('amount_in_usd'),
            avg_trade_size=Avg('amount_in_usd'),
            successful_trades=Count('trade_id', filter=Q(status='completed'))
        )
        
        context = {
            'page_title': 'Trade History',
            'account': account,
            'page_obj': page_obj,
            'trades': page_obj,
            'filters': {
                'status': status_filter,
                'type': trade_type,
                'token': token_symbol,
                'date_from': date_from,
                'date_to': date_to,
            },
            'summary': summary_stats,
        }
        
        return render(request, 'paper_trading/trade_history.html', context)
        
    except Exception as e:
        logger.error(f"Error loading trade history: {e}", exc_info=True)
        messages.error(request, f"Error loading trade history: {str(e)}")
        return redirect('paper_trading:dashboard')


def portfolio_view(request: HttpRequest) -> HttpResponse:
    """
    Display portfolio positions and allocation.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered portfolio template
    """
    try:
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
        
        account = get_object_or_404(
            PaperTradingAccount,
            user=demo_user,
            is_active=True
        )
        
        # Get all positions (open and closed)
        open_positions = PaperPosition.objects.filter(
            account=account,
            is_open=True
        ).order_by('-current_value_usd')
        
        closed_positions = PaperPosition.objects.filter(
            account=account,
            is_open=False
        ).order_by('-closed_at')[:20]  # Last 20 closed positions
        
        # Calculate portfolio metrics
        portfolio_value = account.current_balance_usd + sum(
            pos.current_value_usd for pos in open_positions
        )
        
        total_invested = sum(pos.average_entry_price_usd * pos.quantity for pos in open_positions)
        total_current_value = sum(pos.current_value_usd for pos in open_positions)
        unrealized_pnl = total_current_value - total_invested if total_invested > 0 else 0
        
        # Position distribution
        position_distribution = {}
        for pos in open_positions:
            position_distribution[pos.token_symbol] = {
                'value': float(pos.current_value_usd),
                'percentage': float((pos.current_value_usd / portfolio_value * 100) 
                                  if portfolio_value > 0 else 0),
                'pnl': float(pos.unrealized_pnl_usd)
            }
        
        context = {
            'page_title': 'Portfolio',
            'account': account,
            'open_positions': open_positions,
            'closed_positions': closed_positions,
            'portfolio_value': portfolio_value,
            'cash_balance': account.current_balance_usd,
            'total_invested': total_invested,
            'unrealized_pnl': unrealized_pnl,
            'position_distribution': json.dumps(position_distribution),
            'positions_count': open_positions.count(),
        }
        
        return render(request, 'paper_trading/portfolio.html', context)
        
    except Exception as e:
        logger.error(f"Error loading portfolio: {e}", exc_info=True)
        messages.error(request, f"Error loading portfolio: {str(e)}")
        return redirect('paper_trading:dashboard')


@require_http_methods(["GET", "POST"])
def configuration_view(request: HttpRequest) -> HttpResponse:
    """
    Strategy configuration management view.
    
    Handles both display and updates of trading strategy configuration.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered configuration template or redirect after update
    """
    try:
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
        
        account = get_object_or_404(
            PaperTradingAccount,
            user=demo_user,
            is_active=True
        )
        
        # Get or create configuration
        config, created = PaperStrategyConfiguration.objects.get_or_create(
            account=account,
            defaults={
                'strategy_name': 'default',
                'is_active': True,
                'configuration': {}
            }
        )
        
        if request.method == 'POST':
            # Handle configuration update
            try:
                # Parse JSON configuration
                config_data = json.loads(request.POST.get('configuration', '{}'))
                
                # Update configuration
                config.configuration = config_data
                config.strategy_name = request.POST.get('strategy_name', config.strategy_name)
                config.is_active = request.POST.get('is_active') == 'true'
                config.save()
                
                messages.success(request, 'Configuration updated successfully')
                logger.info(f"Updated configuration for account {account.account_id}")
                
            except json.JSONDecodeError as e:
                messages.error(request, f'Invalid JSON configuration: {e}')
                logger.error(f"JSON decode error: {e}")
            except Exception as e:
                messages.error(request, f'Error updating configuration: {e}')
                logger.error(f"Configuration update error: {e}", exc_info=True)
        
        # Load available strategies
        available_strategies = [
            {'name': 'smart_lane', 'display': 'Smart Lane Strategy'},
            {'name': 'momentum', 'display': 'Momentum Trading'},
            {'name': 'mean_reversion', 'display': 'Mean Reversion'},
            {'name': 'arbitrage', 'display': 'Arbitrage Bot'},
        ]
        
        context = {
            'page_title': 'Strategy Configuration',
            'account': account,
            'config': config,
            'config_json': json.dumps(config.configuration, indent=2),
            'available_strategies': available_strategies,
        }
        
        return render(request, 'paper_trading/configuration.html', context)
        
    except Exception as e:
        logger.error(f"Error in configuration view: {e}", exc_info=True)
        messages.error(request, f"Error loading configuration: {str(e)}")
        return redirect('paper_trading:dashboard')


# =============================================================================
# API ENDPOINTS
# =============================================================================


@require_http_methods(["GET"])
def api_ai_thoughts(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for AI thought logs with real-time updates.
    
    Returns recent AI decision-making thoughts for transparency.
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
        
        # Get recent thoughts
        limit = int(request.GET.get('limit', 10))
        since = request.GET.get('since')
        
        thoughts_query = PaperAIThoughtLog.objects.filter(account=account)
        
        if since:
            since_datetime = datetime.fromisoformat(since)
            thoughts_query = thoughts_query.filter(created_at__gt=since_datetime)
        
        thoughts = thoughts_query.order_by('-created_at')[:limit]
        
        thoughts_data = {
            'thoughts': [
                {
                    'id': str(thought.thought_id),
                    'category': thought.thought_category,
                    'content': thought.thought_content,
                    'metadata': thought.metadata or {},
                    'created_at': thought.created_at.isoformat(),
                    'importance': thought.importance_score,
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
@csrf_exempt
def api_portfolio_data(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for portfolio data.
    
    Returns JSON with current portfolio state including positions,
    balance, and performance metrics.
    
    Args:
        request: Django HTTP request
        
    Returns:
        JSON response with portfolio data
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
        
        # Build portfolio data - FIXED field references
        portfolio_data = {
            'account': {
                'id': str(account.account_id),  # FIXED: Use account_id
                'name': account.name,
                'balance': float(account.current_balance_usd),
                'initial_balance': float(account.initial_balance_usd),
                'total_pnl': float(account.total_pnl_usd),
                'return_percent': float(account.total_return_percent),
                'win_rate': float(account.win_rate),
            },
            'positions': [
                {
                    'id': str(pos.position_id),  # FIXED: Use position_id
                    'token_symbol': pos.token_symbol,
                    'token_address': pos.token_address,
                    'quantity': float(pos.quantity),
                    'entry_price': float(pos.average_entry_price_usd),
                    'current_price': float(pos.current_price_usd),
                    'current_value': float(pos.current_value_usd),
                    'unrealized_pnl': float(pos.unrealized_pnl_usd),
                    'unrealized_pnl_percent': float(pos.unrealized_pnl_percent),
                    'opened_at': pos.opened_at.isoformat(),  # FIXED: Use opened_at
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
@csrf_exempt
def api_trades_data(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for trade history data with filtering support.
    
    Args:
        request: Django HTTP request with optional query parameters
        
    Returns:
        JSON response with filtered trade data
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
        
        # Build query
        trades_query = PaperTrade.objects.filter(account=account)
        
        # Apply filters
        status = request.GET.get('status')
        if status:
            trades_query = trades_query.filter(status=status)
        
        trade_type = request.GET.get('trade_type')
        if trade_type:
            trades_query = trades_query.filter(trade_type=trade_type)
        
        # Limit results
        limit = int(request.GET.get('limit', 50))
        trades_query = trades_query.order_by('-created_at')[:limit]
        
        # Build trades data - FIXED field references
        trades_data = {
            'trades': [
                {
                    'id': str(trade.trade_id),  # FIXED: Use trade_id
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
    
    Returns the most recent trades with essential information.
    
    Args:
        request: Django HTTP request
        
    Returns:
        JSON response with recent trades data
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
        
        # Get recent trades
        limit = min(int(request.GET.get('limit', 10)), 50)
        trades = PaperTrade.objects.filter(
            account=account
        ).order_by('-created_at')[:limit]
        
        # Build response
        trades_data = []
        for trade in trades:
            trade_data = {
                'trade_id': str(trade.trade_id),
                'trade_type': trade.trade_type.upper() if trade.trade_type else 'UNKNOWN',
                'token_symbol': trade.token_out_symbol if trade.trade_type == 'buy' else trade.token_in_symbol,
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
    
    Args:
        request: Django HTTP request
        
    Returns:
        JSON response with open positions data
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
        
        # Build response
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


@require_http_methods(["GET", "POST"])
@csrf_exempt
def api_configuration(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for strategy configuration management.
    
    GET: Returns current configuration
    POST: Updates configuration
    
    Args:
        request: Django HTTP request
        
    Returns:
        JSON response with configuration data or update status
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
@csrf_exempt
def api_performance_metrics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for performance metrics.
    
    Returns detailed performance metrics and statistics.
    
    Args:
        request: Django HTTP request
        
    Returns:
        JSON response with performance data
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
        # First get sessions for this account
        sessions = PaperTradingSession.objects.filter(
            account=account
        ).values_list('session_id', flat=True)
        
        # Then get metrics for those sessions
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
# BOT CONTROL ENDPOINTS
# =============================================================================


@require_http_methods(["POST"])
@csrf_exempt
def api_start_bot(request: HttpRequest) -> JsonResponse:
    """
    Start paper trading bot.
    
    Args:
        request: Django HTTP request
        
    Returns:
        JSON response with bot status
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
        
        # Create new trading session
        session = PaperTradingSession.objects.create(
            account=account,
            is_active=True,
            session_config=json.loads(request.body) if request.body else {}
        )
        
        # TODO: Actually start the bot process
        # This would typically trigger a background task or service
        
        logger.info(f"Started paper trading session {session.session_id} for account {account.account_id}")
        
        return JsonResponse({
            'success': True,
            'session_id': str(session.session_id),
            'message': 'Paper trading bot started',
            'status': 'running'
        })
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def api_stop_bot(request: HttpRequest) -> JsonResponse:
    """
    Stop paper trading bot.
    
    Args:
        request: Django HTTP request
        
    Returns:
        JSON response with bot status
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
            is_active=True
        )
        
        sessions_ended = active_sessions.count()
        active_sessions.update(
            is_active=False,
            ended_at=timezone.now()
        )
        
        # TODO: Actually stop the bot process
        # This would typically stop background tasks or services
        
        logger.info(f"Stopped {sessions_ended} paper trading sessions for account {account.account_id}")
        
        return JsonResponse({
            'success': True,
            'sessions_ended': sessions_ended,
            'message': 'Paper trading bot stopped',
            'status': 'stopped'
        })
        
    except Exception as e:
        logger.error(f"Error stopping bot: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
@csrf_exempt
def api_bot_status(request: HttpRequest) -> JsonResponse:
    """
    Get paper trading bot status.
    
    Args:
        request: Django HTTP request
        
    Returns:
        JSON response with bot status
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


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def _calculate_portfolio_metrics(account: PaperTradingAccount) -> Dict[str, Any]:
    """
    Calculate detailed portfolio metrics.
    
    Args:
        account: Paper trading account
        
    Returns:
        Dictionary with calculated metrics
    """
    try:
        # Get all trades for the account
        all_trades = PaperTrade.objects.filter(account=account, status='completed')
        
        if not all_trades.exists():
            return {
                'total_trades': 0,
                'win_rate': 0,
                'profit_factor': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
            }
        
        # Calculate basic metrics
        total_trades = all_trades.count()
        
        # Winning/losing trades (you might need to add a pnl field to PaperTrade)
        # For now, using a simple heuristic
        winning_trades = 0
        losing_trades = 0
        total_profit = Decimal('0')
        total_loss = Decimal('0')
        
        for trade in all_trades:
            # This is simplified - you'd need actual P&L calculation
            if hasattr(trade, 'pnl_usd'):
                if trade.pnl_usd > 0:
                    winning_trades += 1
                    total_profit += trade.pnl_usd
                elif trade.pnl_usd < 0:
                    losing_trades += 1
                    total_loss += abs(trade.pnl_usd)
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        profit_factor = (total_profit / total_loss) if total_loss > 0 else 0
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': float(win_rate),
            'profit_factor': float(profit_factor),
            'total_profit': float(total_profit),
            'total_loss': float(total_loss),
        }
        
    except Exception as e:
        logger.error(f"Error calculating portfolio metrics: {e}", exc_info=True)
        return {
            'total_trades': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'error': str(e)
        }