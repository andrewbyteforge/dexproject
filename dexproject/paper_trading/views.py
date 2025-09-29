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
# ADD THESE FUNCTIONS TO YOUR EXISTING views.py FILE

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


# REPLACE the analytics_view function in your views.py with this version
# This version works WITHOUT the pnl_usd field
# File Path: dexproject/paper_trading/views.py

def analytics_view(request: HttpRequest) -> HttpResponse:
    """
    Analytics view for paper trading performance analysis.
    
    Displays detailed analytics including:
    - Performance metrics over time
    - Trade distribution and success rates
    - Token performance analysis
    - Risk metrics and analysis
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered analytics template
    """
    try:
        # Get demo user's active account
        from django.contrib.auth.models import User
        
        # Try to get the demo user - if it doesn't exist, redirect
        try:
            demo_user = User.objects.get(username='demo_user')
        except User.DoesNotExist:
            messages.warning(request, "Demo user not found. Please set up the demo account first.")
            return redirect('paper_trading:dashboard')
        
        # Get the active account
        account = PaperTradingAccount.objects.filter(
            user=demo_user,
            is_active=True
        ).first()
        
        if not account:
            messages.info(request, "No active paper trading account found.")
            return redirect('paper_trading:dashboard')
        
        # Date range for analytics (default to last 30 days)
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        # Get date range from request if provided
        date_from = request.GET.get('date_from')
        if date_from:
            try:
                start_date = timezone.make_aware(
                    datetime.strptime(date_from, '%Y-%m-%d')
                )
            except (ValueError, TypeError):
                logger.warning(f"Invalid date_from format: {date_from}")
        
        date_to = request.GET.get('date_to')
        if date_to:
            try:
                end_date = timezone.make_aware(
                    datetime.strptime(date_to, '%Y-%m-%d')
                )
            except (ValueError, TypeError):
                logger.warning(f"Invalid date_to format: {date_to}")
        
        # Get all trades with proper error handling for decimal fields
        all_trades = PaperTrade.objects.filter(
            account=account,
            created_at__gte=start_date,
            created_at__lte=end_date
        ).exclude(
            # Exclude trades with NULL or invalid decimal values
            Q(amount_in_usd__isnull=True) |
            Q(simulated_gas_cost_usd__isnull=True) |
            Q(simulated_slippage_percent__isnull=True)
        )
        
        # Calculate metrics with error handling
        total_trades = all_trades.count()
        completed_trades = all_trades.filter(status='COMPLETED').count()
        failed_trades = all_trades.filter(status='FAILED').count()
        pending_trades = all_trades.filter(status='PENDING').count()
        
        # Calculate volume and fees with NULL handling
        trade_metrics = all_trades.aggregate(
            total_volume=Sum('amount_in_usd', default=Decimal('0')),
            total_gas=Sum('simulated_gas_cost_usd', default=Decimal('0')),
            avg_trade_size=Avg('amount_in_usd', default=Decimal('0')),
            avg_slippage=Avg('simulated_slippage_percent', default=Decimal('0'))
        )
        
        # Get performance metrics
        latest_metrics = PaperPerformanceMetrics.objects.filter(
            session__account=account
        ).order_by('-calculated_at').first()
        
        # Get token distribution
        token_stats = {}
        try:
            # Group trades by token with error handling
            for trade in all_trades:
                # Skip trades with invalid data
                if not trade.token_out_symbol or trade.amount_in_usd is None:
                    continue
                    
                symbol = trade.token_out_symbol
                if symbol not in token_stats:
                    token_stats[symbol] = {
                        'count': 0,
                        'volume': Decimal('0'),
                        'success': 0,
                        'failed': 0
                    }
                
                token_stats[symbol]['count'] += 1
                # Safe addition with NULL check
                if trade.amount_in_usd:
                    token_stats[symbol]['volume'] += trade.amount_in_usd
                
                if trade.status == 'COMPLETED':
                    token_stats[symbol]['success'] += 1
                elif trade.status == 'FAILED':
                    token_stats[symbol]['failed'] += 1
        except Exception as e:
            logger.error(f"Error calculating token stats: {e}")
            token_stats = {}
        
        # Get daily performance data
        daily_performance = []
        current_date = start_date.date()
        while current_date <= end_date.date():
            day_start = timezone.make_aware(
                datetime.combine(current_date, datetime.min.time())
            )
            day_end = timezone.make_aware(
                datetime.combine(current_date, datetime.max.time())
            )
            
            # Get trades for this day with error handling
            day_trades = all_trades.filter(
                created_at__gte=day_start,
                created_at__lte=day_end
            )
            
            # Calculate daily metrics with NULL handling
            day_metrics = day_trades.aggregate(
                count=Count('trade_id'),
                volume=Sum('amount_in_usd', default=Decimal('0')),
                gas_cost=Sum('simulated_gas_cost_usd', default=Decimal('0'))
            )
            
            daily_performance.append({
                'date': current_date.isoformat(),
                'trades': day_metrics['count'] or 0,
                'volume': float(day_metrics['volume'] or 0),
                'gas_cost': float(day_metrics['gas_cost'] or 0)
            })
            
            current_date += timedelta(days=1)
        
        # Prepare context
        context = {
            'page_title': 'Paper Trading Analytics',
            'account': account,
            'date_from': start_date.date(),
            'date_to': end_date.date(),
            
            # Trade statistics
            'total_trades': total_trades,
            'completed_trades': completed_trades,
            'failed_trades': failed_trades,
            'pending_trades': pending_trades,
            'success_rate': (completed_trades / total_trades * 100) if total_trades > 0 else 0,
            
            # Financial metrics
            'total_volume': float(trade_metrics['total_volume'] or 0),
            'total_gas_cost': float(trade_metrics['total_gas'] or 0),
            'avg_trade_size': float(trade_metrics['avg_trade_size'] or 0),
            'avg_slippage': float(trade_metrics['avg_slippage'] or 0),
            
            # Performance metrics
            'latest_metrics': latest_metrics,
            'account_pnl': float(account.total_pnl_usd or 0),
            'account_return': float(account.total_return_percent or 0),
            
            # Token distribution
            'token_stats': dict(sorted(
                token_stats.items(),
                key=lambda x: x[1]['volume'],
                reverse=True
            )[:10]),  # Top 10 tokens by volume
            
            # Chart data
            'daily_performance': json.dumps(daily_performance),
            'chart_labels': json.dumps([d['date'] for d in daily_performance]),
            'chart_volumes': json.dumps([d['volume'] for d in daily_performance]),
            'chart_trades': json.dumps([d['trades'] for d in daily_performance]),
        }
        
        return render(request, 'paper_trading/analytics.html', context)
        
    except Exception as e:
        logger.error(f"Error loading analytics: {e}", exc_info=True)
        messages.error(request, f"Error loading analytics: {str(e)}")
        return redirect('paper_trading:dashboard')











@require_http_methods(["GET"])
def api_analytics_data(request: HttpRequest) -> JsonResponse:
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
def api_analytics_export(request: HttpRequest) -> HttpResponse:
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
