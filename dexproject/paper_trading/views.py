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
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Avg, Count, F
from django.utils import timezone
from django.contrib import messages
from django.core.cache import cache

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

@login_required
def paper_trading_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Main paper trading dashboard view.
    
    Displays portfolio summary, active positions, recent trades,
    and performance metrics.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered dashboard template
    """
    try:
        # Get or create default account for user
        account = PaperTradingAccount.objects.filter(
            user=request.user,
            is_active=True
        ).first()
        
        if not account:
            # Create default account if none exists
            account = PaperTradingAccount.objects.create(
                user=request.user,
                name=f"{request.user.username}'s Paper Trading Account"
            )
            logger.info(f"Created new paper trading account for user {request.user.username}")
        
        # Get active trading session if any
        active_session = PaperTradingSession.objects.filter(
            account=account,
            status='ACTIVE'
        ).first()
        
        # Get recent trades (last 10)
        recent_trades = PaperTrade.objects.filter(
            account=account
        ).order_by('-created_at')[:10]
        
        # Get open positions
        open_positions = PaperPosition.objects.filter(
            account=account,
            is_open=True
        ).order_by('-unrealized_pnl_usd')
        
        # Get performance metrics
        # Get performance metrics
        performance = PaperPerformanceMetrics.objects.filter(
            session__account=account
        ).order_by('-calculated_at').first()
        
        # Calculate summary statistics
        total_trades = PaperTrade.objects.filter(account=account).count()
        successful_trades = PaperTrade.objects.filter(
            account=account,
            status='COMPLETED'
        ).count()
        
        # Get thought logs for recent decisions
        # Get thought logs for recent decisions
        recent_thoughts = PaperAIThoughtLog.objects.filter(
            account=account
        ).order_by('-created_at')[:5]
        
        # Calculate 24h performance
        yesterday = timezone.now() - timedelta(days=1)
        trades_24h = PaperTrade.objects.filter(
            account=account,
            created_at__gte=yesterday
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
        # Show the error for debugging
        import traceback
        logger.error(f"Error loading paper trading dashboard: {e}", exc_info=True)
        
        return HttpResponse(f"""
            <html>
            <body style="font-family: monospace;">
                <h1>Paper Trading Dashboard Error</h1>
                <p><strong>Error Type:</strong> {type(e).__name__}</p>
                <p><strong>Error Message:</strong> {str(e)}</p>
                <h3>Full Traceback:</h3>
                <pre style="background: #f0f0f0; padding: 10px;">{traceback.format_exc()}</pre>
                <hr>
                <p><a href="/dashboard/">Back to Main Dashboard</a></p>
            </body>
            </html>
        """)












@login_required
def trade_history(request: HttpRequest) -> HttpResponse:
    """
    Display detailed trade history with filtering and pagination.
    
    Args:
        request: Django HTTP request with optional filters
        
    Returns:
        Rendered trade history template
    """
    try:
        # Get user's active account
        account = get_object_or_404(
            PaperTradingAccount,
            user=request.user,
            is_active=True
        )
        
        # Build query with filters
        trades_query = PaperTrade.objects.filter(account=account)
        
        # Apply filters from request
        status_filter = request.GET.get('status')
        if status_filter:
            trades_query = trades_query.filter(status=status_filter)
        
        trade_type_filter = request.GET.get('trade_type')
        if trade_type_filter:
            trades_query = trades_query.filter(trade_type=trade_type_filter)
        
        date_from = request.GET.get('date_from')
        if date_from:
            trades_query = trades_query.filter(created_at__gte=date_from)
        
        date_to = request.GET.get('date_to')
        if date_to:
            trades_query = trades_query.filter(created_at__lte=date_to)
        
        # Order by creation date (newest first)
        trades_query = trades_query.order_by('-created_at')
        
        # Paginate results
        paginator = Paginator(trades_query, 25)  # 25 trades per page
        page_number = request.GET.get('page')
        trades_page = paginator.get_page(page_number)
        
        # Calculate summary statistics for filtered results
        summary_stats = trades_query.aggregate(
            total_trades=Count('id'),
            total_volume=Sum('amount_in_usd'),
            avg_trade_size=Avg('amount_in_usd'),
            total_gas_cost=Sum('simulated_gas_cost_usd')
        )
        
        context = {
            'page_title': 'Trade History',
            'account': account,
            'trades': trades_page,
            'summary_stats': summary_stats,
            'status_filter': status_filter,
            'trade_type_filter': trade_type_filter,
            'date_from': date_from,
            'date_to': date_to,
        }
        
        return render(request, 'paper_trading/trade_history.html', context)
        
    except Exception as e:
        logger.error(f"Error loading trade history: {e}", exc_info=True)
        messages.error(request, f"Error loading trade history: {str(e)}")
        return redirect('paper_trading:dashboard')


@login_required
def portfolio_view(request: HttpRequest) -> HttpResponse:
    """
    Display detailed portfolio view with positions and analytics.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered portfolio template
    """
    try:
        account = get_object_or_404(
            PaperTradingAccount,
            user=request.user,
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
        
        total_invested = sum(pos.entry_price_usd * pos.quantity for pos in open_positions)
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


@login_required
@require_http_methods(["GET", "POST"])
def configuration_view(request: HttpRequest) -> HttpResponse:
    """
    Strategy configuration management view.
    
    Handles both display and updates of trading strategy configuration.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered configuration template or redirect after save
    """
    try:
        account = get_object_or_404(
            PaperTradingAccount,
            user=request.user,
            is_active=True
        )
        
        # Get or create strategy configuration
        strategy_config = PaperStrategyConfiguration.objects.filter(
            account=account,
            is_active=True
        ).first()
        
        if request.method == 'POST':
            # Handle configuration update
            try:
                # Update or create configuration
                if not strategy_config:
                    strategy_config = PaperStrategyConfiguration(account=account)
                
                # Update fields from form
                strategy_config.name = request.POST.get('name', 'My Strategy')
                strategy_config.trading_mode = request.POST.get('trading_mode', 'MODERATE')
                strategy_config.use_fast_lane = request.POST.get('use_fast_lane') == 'on'
                strategy_config.use_smart_lane = request.POST.get('use_smart_lane') == 'on'
                strategy_config.max_position_size = Decimal(request.POST.get('max_position_size', '100'))
                strategy_config.max_daily_trades = int(request.POST.get('max_daily_trades', '20'))
                strategy_config.stop_loss_percent = Decimal(request.POST.get('stop_loss_percent', '5'))
                strategy_config.take_profit_percent = Decimal(request.POST.get('take_profit_percent', '10'))
                strategy_config.confidence_threshold = Decimal(request.POST.get('confidence_threshold', '60'))
                strategy_config.max_gas_price_gwei = Decimal(request.POST.get('max_gas_price_gwei', '50'))
                
                # Save configuration
                strategy_config.save()
                
                messages.success(request, 'Strategy configuration updated successfully!')
                logger.info(f"Updated strategy config {strategy_config.config_id} for account {account.account_id}")
                
                return redirect('paper_trading:configuration')
                
            except Exception as e:
                logger.error(f"Error saving configuration: {e}", exc_info=True)
                messages.error(request, f"Error saving configuration: {str(e)}")
        
        # Get all configurations for this account
        all_configs = PaperStrategyConfiguration.objects.filter(
            account=account
        ).order_by('-created_at')
        
        # Get trading config
        trading_config = PaperTradingConfig.objects.filter(account=account).first()
        
        context = {
            'page_title': 'Strategy Configuration',
            'account': account,
            'strategy_config': strategy_config,
            'all_configs': all_configs,
            'trading_config': trading_config,
            'trading_modes': ['CONSERVATIVE', 'MODERATE', 'AGGRESSIVE'],
        }
        
        return render(request, 'paper_trading/configuration.html', context)
        
    except Exception as e:
        logger.error(f"Error in configuration view: {e}", exc_info=True)
        messages.error(request, f"Error loading configuration: {str(e)}")
        return redirect('paper_trading:dashboard')


# =============================================================================
# API ENDPOINTS
# =============================================================================

@login_required
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
        account = PaperTradingAccount.objects.filter(
            user=request.user,
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
                    'entry_price': float(pos.entry_price_usd),
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


@login_required
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
        account = PaperTradingAccount.objects.filter(
            user=request.user,
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
            'count': trades_query.count(),
            'timestamp': timezone.now().isoformat(),
        }
        
        return JsonResponse(trades_data)
        
    except Exception as e:
        logger.error(f"Error in trades API: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
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
        account = PaperTradingAccount.objects.filter(
            user=request.user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        if request.method == 'POST':
            # Handle configuration update
            try:
                data = json.loads(request.body)
                
                # Get or create configuration
                config, created = PaperStrategyConfiguration.objects.get_or_create(
                    account=account,
                    is_active=True,
                    defaults={'name': 'Default Strategy'}
                )
                
                # Update fields
                for field, value in data.items():
                    if hasattr(config, field):
                        if field in ['max_position_size', 'stop_loss_percent', 
                                   'take_profit_percent', 'confidence_threshold', 
                                   'max_gas_price_gwei']:
                            value = Decimal(str(value))
                        elif field in ['max_daily_trades']:
                            value = int(value)
                        elif field in ['use_fast_lane', 'use_smart_lane', 'is_active']:
                            value = bool(value)
                        
                        setattr(config, field, value)
                
                config.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Configuration updated successfully',
                    'config_id': str(config.config_id),
                })
                
            except Exception as e:
                logger.error(f"Error updating configuration: {e}", exc_info=True)
                return JsonResponse({'error': str(e)}, status=400)
        
        else:
            # GET request - return current configuration
            config = PaperStrategyConfiguration.objects.filter(
                account=account,
                is_active=True
            ).first()
            
            if not config:
                return JsonResponse({'error': 'No active configuration found'}, status=404)
            
            config_data = {
                'config': {
                    'id': str(config.config_id),
                    'name': config.name,
                    'trading_mode': config.trading_mode,
                    'use_fast_lane': config.use_fast_lane,
                    'use_smart_lane': config.use_smart_lane,
                    'max_position_size': float(config.max_position_size),
                    'max_daily_trades': config.max_daily_trades,
                    'stop_loss_percent': float(config.stop_loss_percent),
                    'take_profit_percent': float(config.take_profit_percent),
                    'confidence_threshold': float(config.confidence_threshold),
                    'max_gas_price_gwei': float(config.max_gas_price_gwei),
                    'is_active': config.is_active,
                    'created_at': config.created_at.isoformat(),
                    'updated_at': config.updated_at.isoformat(),
                },
                'timestamp': timezone.now().isoformat(),
            }
            
            return JsonResponse(config_data)
        
    except Exception as e:
        logger.error(f"Error in configuration API: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
@csrf_exempt
def api_performance_metrics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for performance metrics.
    
    Returns detailed performance analytics for the account.
    
    Args:
        request: Django HTTP request
        
    Returns:
        JSON response with performance metrics
    """
    try:
        account = PaperTradingAccount.objects.filter(
            user=request.user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        # Get latest performance metrics
        latest_metrics = PaperPerformanceMetrics.objects.filter(
            session__account=account
        ).order_by('-date').first()
        
        # Get historical metrics for chart (last 7 days)
        # Get historical metrics for chart (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        historical_metrics = PaperPerformanceMetrics.objects.filter(
            session__account=account,
            calculated_at__gte=week_ago
        ).order_by('calculated_at')
        
        # Calculate additional statistics
        total_trades = PaperTrade.objects.filter(account=account)
        recent_trades = total_trades.filter(created_at__gte=week_ago)
        
        metrics_data = {
            'current': {
                'total_pnl': float(account.total_pnl_usd),
                'return_percent': float(account.total_return_percent),
                'win_rate': float(account.win_rate),
                'total_trades': account.total_trades,
                'successful_trades': account.successful_trades,
                'failed_trades': account.failed_trades,
                'avg_trade_size': float(recent_trades.aggregate(
                    avg=Avg('amount_in_usd'))['avg'] or 0),
                'total_volume': float(recent_trades.aggregate(
                    sum=Sum('amount_in_usd'))['sum'] or 0),
            },
            'latest_metrics': {
                'date': latest_metrics.calculated_at.date().isoformat() if latest_metrics else None,
                'daily_trades': latest_metrics.daily_trades if latest_metrics else 0,
                'daily_volume': float(latest_metrics.daily_volume_usd) if latest_metrics else 0,
                'daily_pnl': float(latest_metrics.daily_pnl_usd) if latest_metrics else 0,
                'win_rate': float(latest_metrics.win_rate) if latest_metrics else 0,
                'sharpe_ratio': float(latest_metrics.sharpe_ratio) if latest_metrics else 0,
            } if latest_metrics else None,
            'historical': [
                {
                    'date': m.calculated_at.date().isoformat(),
                    'daily_pnl': float(m.daily_pnl_usd),
                    'cumulative_pnl': float(m.cumulative_pnl_usd),
                    'daily_trades': m.daily_trades,
                    'win_rate': float(m.win_rate),
                }
                for m in historical_metrics
            ],
            'timestamp': timezone.now().isoformat(),
        }
        
        return JsonResponse(metrics_data)
        
    except Exception as e:
        logger.error(f"Error in performance metrics API: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def api_start_bot(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to start the paper trading bot.
    
    Args:
        request: Django HTTP request
        
    Returns:
        JSON response with bot start status
    """
    try:
        account = PaperTradingAccount.objects.filter(
            user=request.user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        # Check for existing active session
        active_session = PaperTradingSession.objects.filter(
            account=account,
            status='ACTIVE'
        ).first()
        
        if active_session:
            return JsonResponse({
                'error': 'Bot is already running',
                'session_id': str(active_session.session_id)
            }, status=400)
        
        # Create new session
        # Create new session with required fields
        session = PaperTradingSession.objects.create(
            account=account,
            status='ACTIVE',
            starting_balance_usd=account.current_balance_usd  # Add the starting balance
        )
        
        logger.info(f"Started paper trading bot for account {account.account_id}")
        
        # Note: In production, you would actually start the bot process here
        # For now, we just create the session
        
        return JsonResponse({
            'success': True,
            'message': 'Bot started successfully',
            'session_id': str(session.session_id),
        })
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def api_stop_bot(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to stop the paper trading bot.
    
    Args:
        request: Django HTTP request
        
    Returns:
        JSON response with bot stop status
    """
    try:
        account = PaperTradingAccount.objects.filter(
            user=request.user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        # Find active session
        active_session = PaperTradingSession.objects.filter(
            account=account,
            status='ACTIVE'
        ).first()
        
        if not active_session:
            return JsonResponse({'error': 'No active bot session found'}, status=404)
        
        # Stop the session
        active_session.status = 'COMPLETED'
        active_session.end_time = timezone.now()
        active_session.save()
        
        logger.info(f"Stopped paper trading bot for account {account.account_id}")
        
        return JsonResponse({
            'success': True,
            'message': 'Bot stopped successfully',
            'session_id': str(active_session.session_id),
        })
        
    except Exception as e:
        logger.error(f"Error stopping bot: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
@csrf_exempt
def api_bot_status(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to check bot status.
    
    Args:
        request: Django HTTP request
        
    Returns:
        JSON response with bot status information
    """
    try:
        account = PaperTradingAccount.objects.filter(
            user=request.user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        # Check for active session
        active_session = PaperTradingSession.objects.filter(
            account=account,
            status='ACTIVE'
        ).first()
        
        if active_session:
            # Get recent thought logs
            # Get thought logs for recent decisions
            recent_thoughts = PaperAIThoughtLog.objects.filter(
                account=account
            ).order_by('-created_at')[:5]  # Also changed timestamp to created_at
            
            # Get today's metrics
            # Get today's metrics
            today_metrics = PaperPerformanceMetrics.objects.filter(
                session=active_session,
                calculated_at__date=timezone.now().date()
            ).first()
            
            status_data = {
                'status': 'RUNNING',
                'session': {
                    'id': str(active_session.session_id),
                    'start_time': active_session.start_time.isoformat(),
                    'trades_executed': active_session.trades_executed,
                    'current_balance': float(account.current_balance_usd),
                },
                'recent_thoughts': [
                    {
                        'timestamp': thought.created_at.isoformat(),
                        'decision': thought.decision,
                        'confidence': float(thought.confidence_score),
                    }
                    for thought in recent_thoughts
                ],
                'today_metrics': {
                    'trades': today_metrics.daily_trades if today_metrics else 0,
                    'volume': float(today_metrics.daily_volume_usd) if today_metrics else 0,
                    'pnl': float(today_metrics.daily_pnl_usd) if today_metrics else 0,
                },
            }
        else:
            status_data = {
                'status': 'STOPPED',
                'session': None,
            }
        
        status_data['timestamp'] = timezone.now().isoformat()
        
        return JsonResponse(status_data)
        
    except Exception as e:
        logger.error(f"Error checking bot status: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)