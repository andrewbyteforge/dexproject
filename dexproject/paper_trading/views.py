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
# Add to your existing imports if not already present:
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from datetime import datetime
from decimal import Decimal
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
        Rendered dashboard template
    """
    try:
        # Get or create default account for user (no authentication needed)
        # For demo purposes, we'll use a default user or create one
        from django.contrib.auth.models import User
        
        # Get or create a demo user for paper trading
        demo_user, created = User.objects.get_or_create(
            username='demo_user',
            defaults={
                'email': 'demo@example.com',
                'first_name': 'Demo',
                'last_name': 'User'
            }
        )
        
        # FIXED: Get the specific account with trades
        account = PaperTradingAccount.objects.filter(
            account_id='435f14e1-56b5-46dd-add6-2fd242177c29'
        ).first()
        
        if not account:
            # Fallback to original logic if specific account not found
            account = PaperTradingAccount.objects.filter(
                user=demo_user,
                is_active=True
            ).first()
            
            if not account:
                # Create default account if none exists
                account = PaperTradingAccount.objects.create(
                    user=demo_user,
                    name=f"Demo Paper Trading Account"
                )
                logger.info(f"Created new paper trading account for demo user")
        
        # Get active trading session if any
        active_session = PaperTradingSession.objects.filter(
            account=account,
            status='ACTIVE'  # FIXED: Use correct status value
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
        
        # Get performance metrics (latest)
        performance = PaperPerformanceMetrics.objects.filter(
            session__account=account
        ).order_by('-calculated_at').first()
        
        # Calculate summary statistics - FIXED field references
        total_trades = PaperTrade.objects.filter(account=account).count()
        successful_trades = PaperTrade.objects.filter(
            account=account,
            status='COMPLETED'  # FIXED: Use correct status value
        ).count()
        
        # Get thought logs for recent decisions
        recent_thoughts = PaperAIThoughtLog.objects.filter(
            account=account
        ).order_by('-created_at')[:5]
        
        # Calculate 24h performance - FIXED field reference
        yesterday = timezone.now() - timedelta(days=1)
        trades_24h = PaperTrade.objects.filter(
            account=account,
            created_at__gte=yesterday
        ).aggregate(
            count=Count('trade_id'),  # FIXED: Use trade_id instead of id
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
        return redirect('dashboard:home')


def trade_history(request: HttpRequest) -> HttpResponse:
    """
    Display detailed trade history with filtering and pagination.
    
    Args:
        request: Django HTTP request with optional filters
        
    Returns:
        Rendered trade history template
    """
    try:
        # Get demo user's active account
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
        
        account = get_object_or_404(
            PaperTradingAccount,
            user=demo_user,
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
            total_trades=Count('trade_id'),  # FIXED: Use trade_id
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


def portfolio_view(request: HttpRequest) -> HttpResponse:
    """
    Display detailed portfolio view with positions and analytics.
    
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
        Rendered configuration template or redirect after save
    """
    try:
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
        
        account = get_object_or_404(
            PaperTradingAccount,
            user=demo_user,
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
                
                # Update fields from form - FIXED field names
                strategy_config.name = request.POST.get('name', 'My Strategy')
                strategy_config.trading_mode = request.POST.get('trading_mode', 'MODERATE')
                strategy_config.use_fast_lane = request.POST.get('use_fast_lane') == 'on'
                strategy_config.use_smart_lane = request.POST.get('use_smart_lane') == 'on'
                strategy_config.max_position_size_percent = Decimal(request.POST.get('max_position_size_percent', '100'))  # FIXED
                strategy_config.max_daily_trades = int(request.POST.get('max_daily_trades', '20'))
                strategy_config.stop_loss_percent = Decimal(request.POST.get('stop_loss_percent', '5'))
                strategy_config.take_profit_percent = Decimal(request.POST.get('take_profit_percent', '10'))
                strategy_config.confidence_threshold = Decimal(request.POST.get('confidence_threshold', '60'))
                
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


@require_http_methods(["GET"])
@csrf_exempt
def api_ai_thoughts(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for AI thought logs - THE STAR FEATURE!
    
    Returns recent AI decisions with full reasoning, confidence, and risk assessment.
    Used for real-time dashboard updates to show bot's decision-making process.
    
    Args:
        request: Django HTTP request with optional query parameters:
            - limit: Number of thoughts to return (default: 10, max: 50)
            - since: ISO timestamp to get thoughts after this time
            - decision_type: Filter by decision type (BUY, SELL, HOLD, etc.)
        
    Returns:
        JSON response with AI thought data
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
        
        # Build query for thought logs
        thoughts_query = PaperAIThoughtLog.objects.filter(account=account)
        
        # Apply filters
        decision_type = request.GET.get('decision_type')
        if decision_type:
            thoughts_query = thoughts_query.filter(decision_type=decision_type)
        
        # Filter by time (for incremental updates)
        since = request.GET.get('since')
        if since:
            try:
                since_datetime = datetime.fromisoformat(since.replace('Z', '+00:00'))
                thoughts_query = thoughts_query.filter(created_at__gt=since_datetime)
            except ValueError:
                logger.warning(f"Invalid 'since' timestamp: {since}")
        
        # Limit results
        limit = min(int(request.GET.get('limit', 10)), 50)  # Cap at 50
        thoughts_query = thoughts_query.order_by('-created_at')[:limit]
        
        # Build thoughts data with full AI transparency
        thoughts_data = {
            'thoughts': [
                {
                    # Basic decision info - FIXED field references
                    'id': str(thought.thought_id),  # FIXED: Use thought_id
                    'timestamp': thought.created_at.isoformat(),
                    'decision_type': thought.decision_type,
                    'token_symbol': thought.token_symbol,
                    'token_address': thought.token_address,
                    
                    # Confidence and scoring
                    'confidence_level': thought.confidence_level,
                    'confidence_percent': float(thought.confidence_percent),
                    'risk_score': float(thought.risk_score),
                    'opportunity_score': float(thought.opportunity_score),
                    
                    # AI reasoning (the gold!)
                    'primary_reasoning': thought.primary_reasoning,
                    'key_factors': thought.key_factors,  # JSON field
                    'positive_signals': thought.positive_signals,
                    'negative_signals': thought.negative_signals,
                    
                    # Market context
                    'market_data': thought.market_data,  # JSON field
                    
                    # Strategy info
                    'lane_used': thought.lane_used,
                    'strategy_name': thought.strategy_name,
                    
                    # Performance tracking
                    'analysis_time_ms': thought.analysis_time_ms,
                    
                    # Related trade (if executed)
                    'paper_trade_id': str(thought.paper_trade.trade_id) if thought.paper_trade else None,
                }
                for thought in thoughts_query
            ],
            'meta': {
                'count': len(thoughts_query),
                'account_id': str(account.account_id),  # FIXED: Use account_id
                'has_more': len(thoughts_query) == limit,  # Indicates if there are more results
                'filters_applied': {
                    'decision_type': decision_type,
                    'since': since,
                    'limit': limit,
                },
            },
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
                
                # Update fields - FIXED field names and validation
                for field, value in data.items():
                    if hasattr(config, field):
                        if field in ['max_position_size_percent', 'stop_loss_percent', 
                                   'take_profit_percent', 'confidence_threshold']:
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
                    'config_id': str(config.config_id),  # FIXED: Use config_id
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
            
            # FIXED field references
            config_data = {
                'config': {
                    'id': str(config.config_id),  # FIXED: Use config_id
                    'name': config.name,
                    'trading_mode': config.trading_mode,
                    'use_fast_lane': config.use_fast_lane,
                    'use_smart_lane': config.use_smart_lane,
                    'max_position_size_percent': float(config.max_position_size_percent),
                    'max_daily_trades': config.max_daily_trades,
                    'stop_loss_percent': float(config.stop_loss_percent),
                    'take_profit_percent': float(config.take_profit_percent),
                    'confidence_threshold': float(config.confidence_threshold),
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
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
            
        account = PaperTradingAccount.objects.filter(
            user=demo_user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        # Get latest performance metrics
        latest_metrics = PaperPerformanceMetrics.objects.filter(
            session__account=account
        ).order_by('-calculated_at').first()
        
        # Get historical metrics for chart (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        historical_metrics = PaperPerformanceMetrics.objects.filter(
            session__account=account,
            calculated_at__gte=week_ago
        ).order_by('calculated_at')
        
        # Calculate additional statistics - FIXED field references
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
                'calculated_at': latest_metrics.calculated_at.isoformat() if latest_metrics else None,
                'total_trades': latest_metrics.total_trades if latest_metrics else 0,
                'total_pnl_usd': float(latest_metrics.total_pnl_usd) if latest_metrics else 0,
                'win_rate': float(latest_metrics.win_rate) if latest_metrics else 0,
                'sharpe_ratio': float(latest_metrics.sharpe_ratio) if latest_metrics and latest_metrics.sharpe_ratio else 0,
            } if latest_metrics else None,
            'historical': [
                {
                    'date': m.calculated_at.date().isoformat(),
                    'total_pnl_usd': float(m.total_pnl_usd),
                    'total_trades': m.total_trades,
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
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
            
        account = PaperTradingAccount.objects.filter(
            user=demo_user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        # Check for existing active session
        active_session = PaperTradingSession.objects.filter(
            account=account,
            status='ACTIVE'  # FIXED: Use correct status value
        ).first()
        
        if active_session:
            return JsonResponse({
                'error': 'Bot is already running',
                'session_id': str(active_session.session_id)  # FIXED: Use session_id
            }, status=400)
        
        # Create new session with required fields - FIXED
        session = PaperTradingSession.objects.create(
            account=account,
            status='ACTIVE',
            starting_balance_usd=account.current_balance_usd  # FIXED: Add required field
        )
        
        logger.info(f"Started paper trading bot for account {account.account_id}")
        
        return JsonResponse({
            'success': True,
            'message': 'Bot started successfully',
            'session_id': str(session.session_id),  # FIXED: Use session_id
        })
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


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
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
            
        account = PaperTradingAccount.objects.filter(
            user=demo_user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({'error': 'No active account found'}, status=404)
        
        # Find active session
        active_session = PaperTradingSession.objects.filter(
            account=account,
            status='ACTIVE'  # FIXED: Use correct status value
        ).first()
        
        if not active_session:
            return JsonResponse({'error': 'No active bot session found'}, status=404)
        
        # Stop the session - FIXED field names
        active_session.status = 'STOPPED'
        active_session.end_time = timezone.now()  # FIXED: Use end_time instead of ended_at
        active_session.save()
        
        logger.info(f"Stopped paper trading bot for account {account.account_id}")
        
        return JsonResponse({
            'success': True,
            'message': 'Bot stopped successfully',
            'session_id': str(active_session.session_id),  # FIXED: Use session_id
        })
        
    except Exception as e:
        logger.error(f"Error stopping bot: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
@csrf_exempt
def api_bot_status(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to check bot status with recent AI thoughts.
    
    Args:
        request: Django HTTP request
        
    Returns:
        JSON response with bot status information
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
            status='ACTIVE'  # FIXED: Use correct status value
        ).first()
        
        if active_session:
            # Get recent thought logs
            recent_thoughts = PaperAIThoughtLog.objects.filter(
                account=account
            ).order_by('-created_at')[:3]
            
            # Get today's metrics
            latest_metrics = PaperPerformanceMetrics.objects.filter(
                session=active_session
            ).order_by('-calculated_at').first()
            
            # FIXED field references
            status_data = {
                'status': 'ACTIVE',
                'session': {
                    'id': str(active_session.session_id),  # FIXED: Use session_id
                    'started_at': active_session.start_time.isoformat() if active_session.start_time else None,  # FIXED: Use start_time
                    'total_trades_executed': active_session.total_trades_executed,
                    'current_balance': float(account.current_balance_usd),
                },
                'recent_thoughts': [
                    {
                        'timestamp': thought.created_at.isoformat(),
                        'decision_type': thought.decision_type,
                        'token_symbol': thought.token_symbol,
                        'confidence_percent': float(thought.confidence_percent),
                        'lane_used': thought.lane_used,
                    }
                    for thought in recent_thoughts
                ],
                'metrics': {
                    'total_trades': latest_metrics.total_trades if latest_metrics else 0,
                    'total_pnl_usd': float(latest_metrics.total_pnl_usd) if latest_metrics else 0,
                    'win_rate': float(latest_metrics.win_rate) if latest_metrics else 0,
                } if latest_metrics else None,
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


@require_http_methods(["GET"])
@csrf_exempt
def api_recent_trades(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for fetching recent trades with normalized uppercase values.
    
    Query Parameters:
        - limit: Number of trades to return (default: 10, max: 50)
        - since: ISO timestamp to get trades created after this time
        
    Returns:
        JSON response with recent trades data
    """
    try:
        # Get demo user account
        from django.contrib.auth.models import User
        
        # Check if user is authenticated first, otherwise use demo user
        if request.user.is_authenticated:
            user = request.user
        else:
            try:
                user = User.objects.get(username='demo_user')
            except User.DoesNotExist:
                logger.error("Demo user not found")
                return JsonResponse({
                    'success': False,
                    'error': 'Demo user not configured'
                }, status=404)
        
        # FIXED: Get the specific account with trades
        account = PaperTradingAccount.objects.filter(
            account_id='435f14e1-56b5-46dd-add6-2fd242177c29'
        ).first()
        
        if not account:
            # Fallback to get active account for user
            account = PaperTradingAccount.objects.filter(
                user=user,
                is_active=True
            ).first()
            
            if not account:
                logger.warning(f"No active paper trading account for user {user.username}")
                return JsonResponse({
                    'success': False,
                    'error': 'No active paper trading account found',
                    'trades': []
                })
        
        # Build base query
        trades_query = PaperTrade.objects.filter(account=account)
        
        # Apply 'since' filter if provided
        since = request.GET.get('since')
        if since:
            try:
                # Parse the ISO timestamp
                from django.utils.dateparse import parse_datetime
                since_datetime = parse_datetime(since)
                if since_datetime:
                    # Make it timezone aware if it isn't already
                    if timezone.is_naive(since_datetime):
                        since_datetime = timezone.make_aware(since_datetime)
                    trades_query = trades_query.filter(created_at__gt=since_datetime)
                    logger.debug(f"Filtering trades since {since_datetime}")
            except Exception as e:
                logger.warning(f"Error parsing 'since' parameter: {e}")
        
        # Apply limit
        limit = min(int(request.GET.get('limit', 10)), 50)
        
        # Order by most recent first
        trades = trades_query.order_by('-created_at')[:limit]
        
        # Build response data with normalized uppercase values
        trades_data = []
        for trade in trades:
            try:
                # Normalize status and trade_type to uppercase
                trade_type = trade.trade_type.upper() if trade.trade_type else 'UNKNOWN'
                status = trade.status.upper() if trade.status else 'PENDING'
                
                # Handle common variations
                if status == 'COMPLETE':
                    status = 'COMPLETED'
                
                trade_dict = {
                    'trade_id': str(trade.trade_id),
                    'trade_type': trade_type,  # Now uppercase
                    'status': status,  # Now uppercase
                    'token_symbol': trade.token_out_symbol or trade.token_in_symbol or 'N/A',
                    'token_in_symbol': trade.token_in_symbol or 'N/A',
                    'token_out_symbol': trade.token_out_symbol or 'N/A',
                    'amount_in': float(trade.amount_in) if trade.amount_in else 0,
                    'amount_in_usd': float(trade.amount_in_usd) if trade.amount_in_usd else 0,
                    'amount_out': float(trade.actual_amount_out) if trade.actual_amount_out else 0,
                    'created_at': trade.created_at.isoformat() if trade.created_at else None,
                    'executed_at': trade.executed_at.isoformat() if trade.executed_at else None,
                }
                trades_data.append(trade_dict)
            except Exception as e:
                logger.error(f"Error serializing trade {trade.trade_id}: {e}")
                continue
        
        # Log for debugging
        logger.info(f"Returning {len(trades_data)} trades for account {account.account_id}")
        
        response = {
            'success': True,
            'trades': trades_data,
            'count': len(trades_data),
            'timestamp': timezone.now().isoformat()
        }
        
        return JsonResponse(response)
        
    except Exception as e:
        logger.error(f"Error in api_recent_trades: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'trades': []
        }, status=500)


@require_http_methods(["GET"])
@csrf_exempt
def api_positions_open(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for fetching open positions.
    
    Returns:
        JSON response with open positions data
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
                    'total_value_usd': 0
                },
                'timestamp': timezone.now().isoformat()
            })
        
        # Get open positions
        positions = PaperPosition.objects.filter(
            account=account,
            is_open=True
        ).order_by('-unrealized_pnl_usd')
        
        # Build response
        positions_data = []
        total_value = Decimal('0')
        
        for position in positions:
            pos_data = {
                'position_id': str(position.position_id),
                'token_symbol': position.token_symbol,
                'token_address': position.token_address,
                'quantity': float(position.quantity),
                'average_entry_price_usd': float(position.average_entry_price_usd),
                'current_value_usd': float(position.current_value_usd) if position.current_value_usd else 0,
                'unrealized_pnl_usd': float(position.unrealized_pnl_usd),
                'unrealized_pnl_percent': float(position.unrealized_pnl_percent),
                'created_at': position.created_at.isoformat()
            }
            positions_data.append(pos_data)
            total_value += position.current_value_usd if position.current_value_usd else Decimal('0')
        
        return JsonResponse({
            'success': True,
            'positions': positions_data,
            'summary': {
                'total_positions': len(positions_data),
                'total_value_usd': float(total_value)
            },
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in api_positions_open: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'positions': []
        }, status=500)


@require_http_methods(["GET"])
def api_metrics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for dashboard metrics.
    
    Returns:
        JSON response with current metrics data
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
                'current_balance': 0,
                'total_pnl': 0,
                'win_rate': 0,
                'trades_24h': 0,
                'total_trades': 0
            })
        
        # Calculate 24h metrics
        yesterday = timezone.now() - timedelta(days=1)
        trades_24h = PaperTrade.objects.filter(
            account=account,
            created_at__gte=yesterday
        ).count()
        
        return JsonResponse({
            'success': True,
            'current_balance': float(account.current_balance_usd),
            'total_pnl': float(account.total_pnl_usd),
            'win_rate': float(account.win_rate),
            'trades_24h': trades_24h,
            'total_trades': account.total_trades,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in api_metrics: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# UTILITY VIEWS
# =============================================================================


def reset_account(request: HttpRequest) -> HttpResponse:
    """
    Reset paper trading account to initial state.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Redirect to dashboard
    """
    try:
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
        
        account = get_object_or_404(
            PaperTradingAccount,
            user=demo_user,
            is_active=True
        )
        
        # Stop any active sessions first
        active_sessions = PaperTradingSession.objects.filter(
            account=account,
            status='ACTIVE'
        )
        
        for session in active_sessions:
            session.status = 'STOPPED'
            session.end_time = timezone.now()
            session.save()
        
        # Reset account
        account.reset_account()
        
        messages.success(request, 'Paper trading account has been reset successfully!')
        logger.info(f"Reset paper trading account {account.account_id} for demo user")
        
        return redirect('paper_trading:dashboard')
        
    except Exception as e:
        logger.error(f"Error resetting account: {e}", exc_info=True)
        messages.error(request, f"Error resetting account: {str(e)}")
        return redirect('paper_trading:dashboard')


def delete_trade(request: HttpRequest, trade_id: str) -> JsonResponse:
    """
    Delete a specific paper trade.
    
    Args:
        request: Django HTTP request
        trade_id: UUID of the trade to delete
        
    Returns:
        JSON response with deletion status
    """
    try:
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
        
        account = get_object_or_404(
            PaperTradingAccount,
            user=demo_user,
            is_active=True
        )
        
        trade = get_object_or_404(
            PaperTrade,
            trade_id=trade_id,  # FIXED: Use trade_id
            account=account
        )
        
        # Don't allow deletion of executed trades
        if trade.status == 'COMPLETED':
            return JsonResponse({
                'success': False,
                'error': 'Cannot delete completed trades'
            }, status=400)
        
        trade.delete()
        
        logger.info(f"Deleted trade {trade_id} for account {account.account_id}")
        
        return JsonResponse({
            'success': True,
            'message': 'Trade deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error deleting trade: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)