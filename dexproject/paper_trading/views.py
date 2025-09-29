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




# File Path: dexproject/paper_trading/views.py
# ADD THIS FUNCTION TO YOUR EXISTING views.py FILE

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.contrib import messages
from django.db.models import Sum, Avg, Count, Q, F
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperPerformanceMetrics
)

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def paper_trading_analytics_view(request: HttpRequest) -> HttpResponse:
    """
    Analytics dashboard for paper trading performance.
    
    Displays comprehensive trading analytics including:
    - Performance charts and graphs
    - Win/loss analysis
    - Token performance breakdown
    - Trading patterns and insights
    
    Args:
        request: HTTP request object
        
    Returns:
        Rendered analytics template with performance data
    """
    try:
        # Get demo user account
        from django.contrib.auth.models import User
        demo_user, _ = User.objects.get_or_create(username='demo_user')
        
        # Get or create paper trading account
        account, created = PaperTradingAccount.objects.get_or_create(
            user=demo_user,
            is_active=True,
            defaults={'name': 'Demo Paper Account'}
        )
        
        # Time periods for analysis
        now = timezone.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        # ====================
        # Basic Metrics
        # ====================
        
        # Get all trades
        all_trades = PaperTrade.objects.filter(
            account=account,
            status='COMPLETED'
        ).order_by('created_at')
        
        # Calculate win rate
        profitable_trades = all_trades.filter(pnl_usd__gt=0).count()
        total_completed_trades = all_trades.count()
        win_rate = (profitable_trades / total_completed_trades * 100) if total_completed_trades > 0 else 0
        
        # Calculate average trade metrics
        avg_profit = all_trades.filter(pnl_usd__gt=0).aggregate(
            avg=Avg('pnl_usd')
        )['avg'] or Decimal('0')
        
        avg_loss = all_trades.filter(pnl_usd__lt=0).aggregate(
            avg=Avg('pnl_usd')
        )['avg'] or Decimal('0')
        
        # Profit factor
        total_profit = all_trades.filter(pnl_usd__gt=0).aggregate(
            total=Sum('pnl_usd')
        )['total'] or Decimal('0')
        
        total_loss = abs(all_trades.filter(pnl_usd__lt=0).aggregate(
            total=Sum('pnl_usd')
        )['total'] or Decimal('0'))
        
        profit_factor = (total_profit / total_loss) if total_loss > 0 else total_profit
        
        # ====================
        # Performance Over Time
        # ====================
        
        # Daily P&L for last 30 days
        daily_pnl = []
        cumulative_pnl = Decimal('0')
        
        for i in range(30):
            day = today - timedelta(days=29-i)
            next_day = day + timedelta(days=1)
            
            day_trades = all_trades.filter(
                created_at__gte=day,
                created_at__lt=next_day
            )
            
            day_pnl = day_trades.aggregate(
                total=Sum('pnl_usd')
            )['total'] or Decimal('0')
            
            cumulative_pnl += day_pnl
            
            daily_pnl.append({
                'date': day.strftime('%Y-%m-%d'),
                'pnl': float(day_pnl),
                'cumulative': float(cumulative_pnl)
            })
        
        # ====================
        # Token Performance
        # ====================
        
        # Get performance by token
        token_performance = {}
        
        for trade in all_trades:
            token = trade.token_out_symbol
            if token not in token_performance:
                token_performance[token] = {
                    'trades': 0,
                    'wins': 0,
                    'total_pnl': Decimal('0'),
                    'total_volume': Decimal('0')
                }
            
            token_performance[token]['trades'] += 1
            token_performance[token]['total_volume'] += trade.amount_in_usd
            token_performance[token]['total_pnl'] += trade.pnl_usd or Decimal('0')
            if trade.pnl_usd and trade.pnl_usd > 0:
                token_performance[token]['wins'] += 1
        
        # Calculate win rate and format for display
        token_stats = []
        for token, stats in token_performance.items():
            win_rate = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
            token_stats.append({
                'symbol': token,
                'trades': stats['trades'],
                'win_rate': win_rate,
                'total_pnl': float(stats['total_pnl']),
                'avg_pnl': float(stats['total_pnl'] / stats['trades']) if stats['trades'] > 0 else 0,
                'volume': float(stats['total_volume'])
            })
        
        # Sort by total P&L
        token_stats.sort(key=lambda x: x['total_pnl'], reverse=True)
        top_performers = token_stats[:5]
        worst_performers = token_stats[-5:] if len(token_stats) > 5 else []
        
        # ====================
        # Trading Patterns
        # ====================
        
        # Hourly distribution
        hourly_distribution = {}
        for hour in range(24):
            hour_trades = all_trades.filter(created_at__hour=hour)
            hourly_distribution[hour] = {
                'count': hour_trades.count(),
                'avg_pnl': float(hour_trades.aggregate(
                    avg=Avg('pnl_usd')
                )['avg'] or 0)
            }
        
        # Best trading hours
        best_hours = sorted(
            hourly_distribution.items(),
            key=lambda x: x[1]['avg_pnl'],
            reverse=True
        )[:3]
        
        # ====================
        # Recent Performance
        # ====================
        
        # Today's performance
        today_trades = all_trades.filter(created_at__gte=today)
        today_pnl = today_trades.aggregate(
            total=Sum('pnl_usd')
        )['total'] or Decimal('0')
        
        # Week performance
        week_trades = all_trades.filter(created_at__gte=week_ago)
        week_pnl = week_trades.aggregate(
            total=Sum('pnl_usd')
        )['total'] or Decimal('0')
        
        # Month performance
        month_trades = all_trades.filter(created_at__gte=month_ago)
        month_pnl = month_trades.aggregate(
            total=Sum('pnl_usd')
        )['total'] or Decimal('0')
        
        # ====================
        # Risk Metrics
        # ====================
        
        # Maximum drawdown calculation
        balance_history = [10000]  # Starting balance
        running_balance = Decimal('10000')
        peak_balance = Decimal('10000')
        max_drawdown = Decimal('0')
        
        for trade in all_trades:
            running_balance += trade.pnl_usd or Decimal('0')
            balance_history.append(float(running_balance))
            
            if running_balance > peak_balance:
                peak_balance = running_balance
            
            drawdown = ((peak_balance - running_balance) / peak_balance * 100) if peak_balance > 0 else 0
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # Sharpe Ratio (simplified)
        returns = []
        for trade in all_trades:
            if trade.amount_in_usd > 0:
                return_pct = (trade.pnl_usd / trade.amount_in_usd * 100)
                returns.append(float(return_pct))
        
        if returns:
            avg_return = sum(returns) / len(returns)
            variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
            std_dev = variance ** 0.5
            sharpe_ratio = (avg_return / std_dev) if std_dev > 0 else 0
        else:
            sharpe_ratio = 0
        
        # ====================
        # Prepare Context
        # ====================
        
        context = {
            'page_title': 'Trading Analytics',
            
            # Account info
            'account': account,
            'total_trades': total_completed_trades,
            
            # Performance metrics
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'avg_profit': avg_profit,
            'avg_loss': avg_loss,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            
            # Time-based performance
            'today_pnl': today_pnl,
            'today_trades': today_trades.count(),
            'week_pnl': week_pnl,
            'week_trades': week_trades.count(),
            'month_pnl': month_pnl,
            'month_trades': month_trades.count(),
            
            # Charts data (JSON for JavaScript)
            'daily_pnl_data': json.dumps(daily_pnl),
            'hourly_distribution': json.dumps(hourly_distribution),
            
            # Token performance
            'top_performers': top_performers,
            'worst_performers': worst_performers,
            'token_stats': json.dumps(token_stats[:10]),  # Top 10 for chart
            
            # Trading patterns
            'best_hours': best_hours,
            
            # For chart rendering
            'has_data': total_completed_trades > 0,
        }
        
        return render(request, 'paper_trading/paper_trading_analytics.html', context)
        
    except Exception as e:
        logger.error(f"Error loading analytics: {e}", exc_info=True)
        messages.error(request, f"Error loading analytics: {str(e)}")
        return redirect('paper_trading:dashboard')


@require_http_methods(["GET"])
def paper_trading_api_analytics_data(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to fetch analytics data for real-time updates.
    
    Returns JSON data for updating charts without page refresh.
    """
    try:
        # Similar logic to analytics_view but returns JSON
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
        account = PaperTradingAccount.objects.get(user=demo_user, is_active=True)
        
        # Get recent metrics
        now = timezone.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        all_trades = PaperTrade.objects.filter(
            account=account,
            status='COMPLETED'
        )
        
        profitable_trades = all_trades.filter(pnl_usd__gt=0).count()
        total_trades = all_trades.count()
        win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
        
        return JsonResponse({
            'success': True,
            'metrics': {
                'win_rate': win_rate,
                'total_trades': total_trades,
                # Add more metrics as needed
            }
        })
        
    except Exception as e:
        logger.error(f"Error fetching analytics data: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
def paper_trading_api_analytics_export(request: HttpRequest) -> HttpResponse:
    """
    Export analytics data to CSV format.
    """
    import csv
    from django.http import HttpResponse
    
    try:
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="paper_trading_analytics.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow(['Date', 'Trade ID', 'Token', 'Type', 'Amount', 'P&L', 'Status'])
        
        # Get trades
        from django.contrib.auth.models import User
        demo_user = User.objects.get(username='demo_user')
        account = PaperTradingAccount.objects.get(user=demo_user, is_active=True)
        
        trades = PaperTrade.objects.filter(account=account).order_by('-created_at')
        
        for trade in trades:
            writer.writerow([
                trade.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                trade.trade_id,
                trade.token_out_symbol,
                trade.trade_type,
                trade.amount_in_usd,
                trade.pnl_usd or 0,
                trade.status
            ])
        
        return response
        
    except Exception as e:
        logger.error(f"Error exporting analytics: {e}")
        return JsonResponse({'error': str(e)}, status=500)


