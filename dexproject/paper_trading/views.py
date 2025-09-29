"""
Paper Trading Views - Dashboard and Page Views

This module provides all dashboard and page views for the paper trading system.
Includes portfolio display, trade history, and configuration management pages.
API endpoints have been moved to api_views.py

File: dexproject/paper_trading/views.py
"""

import json
import logging
from datetime import timedelta
from decimal import Decimal
from typing import Dict, Any

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Avg, Count
from django.utils import timezone
from django.contrib import messages
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
        if active_session:
            performance = PaperPerformanceMetrics.objects.filter(
                session=active_session
            ).order_by('-calculated_at').first()
        else:
            performance = None
        
        # Calculate summary statistics
        total_trades = account.total_trades
        successful_trades = account.successful_trades
        
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
        
        total_invested = sum(
            pos.average_entry_price_usd * pos.quantity 
            for pos in open_positions 
            if pos.average_entry_price_usd
        )
        
        total_current_value = sum(pos.current_value_usd for pos in open_positions)
        unrealized_pnl = total_current_value - total_invested if total_invested > 0 else 0
        
        # Position distribution for chart
        position_distribution = {}
        for pos in open_positions:
            position_distribution[pos.token_symbol] = {
                'value': float(pos.current_value_usd),
                'percentage': float((pos.current_value_usd / portfolio_value * 100) 
                                  if portfolio_value > 0 else 0),
                'pnl': float(pos.unrealized_pnl_usd) if pos.unrealized_pnl_usd else 0
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
# UTILITY FUNCTIONS
# =============================================================================


def calculate_portfolio_metrics(account: PaperTradingAccount) -> Dict[str, Any]:
    """
    Calculate detailed portfolio metrics.
    
    Helper function to calculate various performance metrics for an account.
    
    Args:
        account: Paper trading account
        
    Returns:
        Dictionary with calculated metrics
    """
    try:
        # Get all completed trades for the account
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
        
        # Count winning and losing trades
        winning_trades = 0
        losing_trades = 0
        total_profit = Decimal('0')
        total_loss = Decimal('0')
        
        for trade in all_trades:
            # Check if trade has P&L data
            if hasattr(trade, 'pnl_usd') and trade.pnl_usd is not None:
                if trade.pnl_usd > 0:
                    winning_trades += 1
                    total_profit += trade.pnl_usd
                elif trade.pnl_usd < 0:
                    losing_trades += 1
                    total_loss += abs(trade.pnl_usd)
        
        # Calculate win rate
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Calculate profit factor
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


def get_or_create_demo_account() -> PaperTradingAccount:
    """
    Get or create a demo paper trading account.
    
    Helper function to ensure a demo account exists for testing.
    
    Returns:
        PaperTradingAccount: The demo account instance
    """
    from django.contrib.auth.models import User
    
    try:
        demo_user = User.objects.get(username='demo_user')
    except User.DoesNotExist:
        demo_user = User.objects.create_user(
            username='demo_user',
            email='demo@example.com',
            password='demo_password'
        )
        logger.info("Created demo_user for paper trading")
    
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
        logger.info(f"Created new demo paper trading account: {account.account_id}")
    
    return account