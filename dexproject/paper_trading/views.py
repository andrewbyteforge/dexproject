"""
Paper Trading Views - Dashboard and Page Views

This module provides all dashboard and page views for the paper trading system.
Includes portfolio display, trade history, and configuration management pages.
API endpoints have been moved to api_views.py

UPDATED: Fixed decimal handling issues and trade history redirect bug

File: dexproject/paper_trading/views.py
"""

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Optional

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Avg, Count
from django.utils import timezone
from django.contrib import messages
from django.db import connection
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

logger = logging.getLogger(__name__)


# =============================================================================
# DECIMAL HANDLING HELPERS
# =============================================================================

def safe_decimal(value, default='0'):
    """
    Safely convert a value to decimal, handling large wei values.
    
    Args:
        value: The value to convert
        default: Default value if conversion fails
        
    Returns:
        Decimal safe for display
    """
    try:
        if value is None:
            return Decimal(default)
        
        # If it's already a Decimal, check if it's too large (wei value)
        if isinstance(value, Decimal):
            # If it's a wei value (> 10^15), return 0 for display
            if value > Decimal('1000000000000000'):
                logger.debug(f"Converting large wei value to {default}: {value}")
                return Decimal(default)
            return value
            
        # Try to convert to Decimal
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as e:
        logger.warning(f"Failed to convert value to decimal: {value}, error: {e}")
        return Decimal(default)


def format_trade_for_template(trade):
    """
    Format a trade object for safe template display.
    
    Converts wei values to human-readable format and ensures
    all decimal values are safe for template rendering.
    
    Args:
        trade: PaperTrade object
        
    Returns:
        Dictionary with formatted trade data
    """
    try:
        return {
            'trade_id': str(trade.trade_id),
            'trade_type': trade.trade_type or 'unknown',
            'token_in_symbol': trade.token_in_symbol or 'Unknown',
            'token_out_symbol': trade.token_out_symbol or 'Unknown',
            'amount_in_usd': safe_decimal(trade.amount_in_usd, '0'),
            'amount_in_display': safe_decimal(trade.amount_in_usd, '0'),  # Use USD for display
            'amount_out_display': safe_decimal(trade.amount_in_usd, '0'),  # Use USD approximation
            'simulated_gas_cost_usd': safe_decimal(trade.simulated_gas_cost_usd, '0'),
            'simulated_slippage_percent': safe_decimal(trade.simulated_slippage_percent, '0'),
            'status': trade.status or 'pending',
            'created_at': trade.created_at,
            'executed_at': trade.executed_at,
            'execution_time_ms': trade.execution_time_ms or 0,
            'mock_tx_hash': trade.mock_tx_hash or '',
            'strategy_name': trade.strategy_name or 'Manual',
            'simulated_gas_price_gwei': safe_decimal(trade.simulated_gas_price_gwei, '0'),
            'simulated_gas_used': trade.simulated_gas_used or 0,
            # Original trade object for other attributes
            '_original': trade
        }
    except Exception as e:
        logger.error(f"Error formatting trade {getattr(trade, 'trade_id', 'unknown')}: {e}")
        # Return minimal safe data
        return {
            'trade_id': str(getattr(trade, 'trade_id', 'Unknown')),
            'trade_type': 'unknown',
            'token_in_symbol': 'Unknown',
            'token_out_symbol': 'Unknown',
            'amount_in_usd': Decimal('0'),
            'amount_in_display': Decimal('0'),
            'amount_out_display': Decimal('0'),
            'simulated_gas_cost_usd': Decimal('0'),
            'simulated_slippage_percent': Decimal('0'),
            'status': 'error',
            'created_at': timezone.now(),
            'executed_at': None,
            'execution_time_ms': 0,
            'mock_tx_hash': '',
            'strategy_name': 'Unknown',
            'simulated_gas_price_gwei': Decimal('0'),
            'simulated_gas_used': 0,
            '_original': trade
        }


def format_position_for_template(position):
    """
    Format a position object for safe template display.
    
    Args:
        position: PaperPosition object
        
    Returns:
        Dictionary with formatted position data
    """
    try:
        return {
            'position_id': str(position.position_id),
            'token_symbol': position.token_symbol or 'Unknown',
            'token_address': position.token_address or '',
            'quantity': safe_decimal(position.quantity, '0'),
            'average_entry_price_usd': safe_decimal(position.average_entry_price_usd, '0'),
            'current_price_usd': safe_decimal(position.current_price_usd, '0'),
            'total_invested_usd': safe_decimal(position.total_invested_usd, '0'),
            'current_value_usd': safe_decimal(position.current_value_usd, '0'),
            'unrealized_pnl_usd': safe_decimal(position.unrealized_pnl_usd, '0'),
            'realized_pnl_usd': safe_decimal(position.realized_pnl_usd, '0'),
            'is_open': position.is_open,
            'opened_at': position.opened_at,
            'closed_at': position.closed_at,
            '_original': position
        }
    except Exception as e:
        logger.error(f"Error formatting position: {e}")
        return {
            'position_id': str(getattr(position, 'position_id', 'Unknown')),
            'token_symbol': 'Unknown',
            'token_address': '',
            'quantity': Decimal('0'),
            'average_entry_price_usd': Decimal('0'),
            'current_price_usd': Decimal('0'),
            'total_invested_usd': Decimal('0'),
            'current_value_usd': Decimal('0'),
            'unrealized_pnl_usd': Decimal('0'),
            'realized_pnl_usd': Decimal('0'),
            'is_open': False,
            'opened_at': None,
            'closed_at': None,
            '_original': position
        }


# =============================================================================
# CENTRALIZED ACCOUNT MANAGEMENT
# =============================================================================

def get_default_user():
    """
    Get or create the default user for single-user operation.
    No authentication required.
    
    Returns:
        User: The default user instance
    """
    user, created = User.objects.get_or_create(
        username='demo_user',  # Using demo_user to match the bot
        defaults={
            'email': 'demo@example.com',
            'first_name': 'Demo',
            'last_name': 'User'
        }
    )
    if created:
        logger.info("Created demo_user for paper trading")
    return user


def get_single_trading_account(user: Optional[User] = None) -> PaperTradingAccount:
    """
    Get or create the single paper trading account for the application.
    
    This ensures only one account exists and is consistently used across
    the entire application (bot, API, dashboard, WebSocket).
    
    Args:
        user: The user to get account for. If None, uses demo_user.
        
    Returns:
        PaperTradingAccount: The single account for this user
    """
    if user is None:
        user = get_default_user()
    
    # Get all accounts for this user
    accounts = PaperTradingAccount.objects.filter(user=user).order_by('created_at')
    
    if accounts.exists():
        # Use the first (oldest) account
        account = accounts.first()
        
        # Clean up any duplicates
        if accounts.count() > 1:
            logger.warning(f"Found {accounts.count()} accounts, cleaning duplicates")
            # Keep the first account, delete others
            for duplicate in accounts[1:]:
                logger.info(f"Removing duplicate account: {duplicate.name} ({duplicate.account_id})")
                duplicate.delete()
        
        # Ensure the account is active and has the consistent name
        if not account.is_active or account.name != 'My_Trading_Account':
            account.is_active = True
            account.name = 'My_Trading_Account'  # Use consistent name with bot
            account.save()
            logger.info(f"Updated account to standard name: {account.name}")
        
        logger.debug(f"Using existing account: {account.name} ({account.account_id})")
        
    else:
        # No account exists, create the single account
        account = PaperTradingAccount.objects.create(
            user=user,
            name='My_Trading_Account',  # Consistent name with bot
            initial_balance_usd=Decimal('10000.00'),
            current_balance_usd=Decimal('10000.00'),
            is_active=True
        )
        logger.info(f"Created new paper trading account: {account.name} ({account.account_id})")
    
    return account


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
        # Get the single account
        account = get_single_trading_account()
        user = account.user
        
        logger.debug(f"Loading paper trading dashboard for account {account.account_id}")
        
        # Get active session if exists (check for today's session)
        today = timezone.now().date()
        active_session = PaperTradingSession.objects.filter(
            account=account,
            started_at__date=today,
            status__in=["ACTIVE", "RUNNING", "STARTING"]
        ).order_by('-started_at').first()
        
        # If no session today but there are old running sessions, close them
        if not active_session:
            old_sessions = PaperTradingSession.objects.filter(
                account=account,
                started_at__date__lt=today,
                status__in=["ACTIVE", "RUNNING", "STARTING"]
            )
            for old_session in old_sessions:
                old_session.status = "STOPPED"
                old_session.ended_at = timezone.now()
                old_session.save()
                logger.info(f"Closed old session from {old_session.started_at.date()}: {old_session.session_id}")
        
        # Get recent trades - format them for safe display
        try:
            raw_trades = PaperTrade.objects.filter(
                account=account
            ).order_by('-created_at')[:10]
            recent_trades = [format_trade_for_template(trade) for trade in raw_trades]
        except Exception as e:
            logger.warning(f"Error fetching recent trades: {e}")
            recent_trades = []
        
        # Get open positions - format them for safe display
        try:
            raw_positions = PaperPosition.objects.filter(
                account=account,
                is_open=True
            ).order_by('-current_value_usd')
            open_positions = [format_position_for_template(pos) for pos in raw_positions]
        except Exception as e:
            logger.warning(f"Error fetching open positions: {e}")
            open_positions = []
        
        # Get recent AI thoughts - these are usually safe
        recent_thoughts = PaperAIThoughtLog.objects.filter(
            account=account
        ).order_by('-created_at')[:5]
        
        # Format thoughts for template
        formatted_thoughts = []
        for thought in recent_thoughts:
            formatted_thoughts.append({
                'thought_id': str(thought.thought_id),
                'decision_type': thought.decision_type,
                'token_symbol': thought.token_symbol,
                'confidence_percent': safe_decimal(thought.confidence_level, '0'),
                'created_at': thought.created_at,
                'thought_content': thought.reasoning[:150] if thought.reasoning else "Analyzing market conditions...",
                '_original': thought
            })
        
        # Get performance metrics
        performance = None
        if active_session:
            try:
                performance = PaperPerformanceMetrics.objects.filter(
                    session=active_session
                ).order_by('-created_at').first()
            except Exception as e:
                logger.warning(f"Error fetching performance metrics: {e}")
        
        # Calculate summary statistics with safe decimal handling
        # FIXED: Get winning/losing trades from closed positions, not trade status
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_closed,
                    SUM(CASE WHEN realized_pnl_usd > 0 THEN 1 ELSE 0 END) as winning,
                    SUM(CASE WHEN realized_pnl_usd < 0 THEN 1 ELSE 0 END) as losing
                FROM paper_positions
                WHERE account_id = %s AND is_open = FALSE
            """, [str(account.account_id)])
            
            position_stats = cursor.fetchone()
            total_closed_positions = position_stats[0] or 0
            winning_trades = position_stats[1] or 0
            losing_trades = position_stats[2] or 0
        
        # Get total trades (number of trade executions)
        total_trades = PaperTrade.objects.filter(account=account).count()
        
        # Calculate total portfolio value = cash balance + value of open positions
        total_portfolio_value = safe_decimal(account.current_balance_usd)
        for position in open_positions:
            total_portfolio_value += safe_decimal(position['current_value_usd'])
        
        # Get 24h stats with error handling
        time_24h_ago = timezone.now() - timedelta(hours=24)
        try:
            trades_24h = PaperTrade.objects.filter(
                account=account,
                created_at__gte=time_24h_ago
            ).aggregate(
                count=Count('trade_id'),
                total_volume=Sum('amount_in_usd', default=Decimal('0'))
            )
        except Exception as e:
            logger.warning(f"Error calculating 24h stats: {e}")
            trades_24h = {'count': 0, 'total_volume': Decimal('0')}
        
        context = {
            'page_title': 'Paper Trading Dashboard',
            'account': account,
            'account_id': str(account.account_id),
            'active_session': active_session,
            'recent_trades': recent_trades,
            'open_positions': open_positions,
            'performance': performance,
            'recent_thoughts': formatted_thoughts,
            'total_trades': total_trades,  # Total trade executions
            'successful_trades': winning_trades,  # Winning positions (realized_pnl_usd > 0)
            'total_closed_positions': total_closed_positions,  # Total closed positions
            'win_rate': safe_decimal((winning_trades / total_closed_positions * 100) if total_closed_positions > 0 else 0),
            'trades_24h': trades_24h.get('count', 0),
            'volume_24h': safe_decimal(trades_24h.get('total_volume', 0)),
            'current_balance': safe_decimal(account.current_balance_usd),  # Cash balance only
            'portfolio_value': total_portfolio_value,  # FIXED: Total value = cash + open positions
            'initial_balance': safe_decimal(account.initial_balance_usd),
            'total_pnl': safe_decimal(account.total_profit_loss_usd),
            'return_percent': safe_decimal(account.get_roi()),
            'user': user,
        }
        
        logger.info(f"Successfully loaded dashboard for account {account.account_id}")
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
        # Get the single account
        account = get_single_trading_account()
        user = account.user
        
        logger.debug(f"Loading trade history for account {account.account_id}")
        
        # Build query with filters
        trades_query = PaperTrade.objects.filter(account=account)
        
        # Apply filters with validation
        status_filter = request.GET.get('status', '')
        if status_filter:
            # Don't convert to lowercase - check the actual values in your database
            trades_query = trades_query.filter(status=status_filter)
            logger.debug(f"Applied status filter: {status_filter}")
        
        trade_type_filter = request.GET.get('trade_type', '')
        if trade_type_filter:
            # Don't convert to lowercase - check the actual values in your database
            trades_query = trades_query.filter(trade_type=trade_type_filter)
            logger.debug(f"Applied trade type filter: {trade_type_filter}")
        
        token_symbol = request.GET.get('token')
        if token_symbol:
            trades_query = trades_query.filter(
                Q(token_in_symbol__icontains=token_symbol) | 
                Q(token_out_symbol__icontains=token_symbol)
            )
            logger.debug(f"Applied token filter: {token_symbol}")
        
        # Date range filter with validation
        date_from = request.GET.get('date_from')
        if date_from:
            try:
                trades_query = trades_query.filter(created_at__gte=date_from)
                logger.debug(f"Applied date from filter: {date_from}")
            except Exception as e:
                logger.warning(f"Invalid date_from format: {date_from}, error: {e}")
        
        date_to = request.GET.get('date_to')
        if date_to:
            try:
                trades_query = trades_query.filter(created_at__lte=date_to)
                logger.debug(f"Applied date to filter: {date_to}")
            except Exception as e:
                logger.warning(f"Invalid date_to format: {date_to}, error: {e}")
        
        # Order by creation date
        trades_query = trades_query.order_by('-created_at')
        
        # Format trades BEFORE pagination to avoid issues
        formatted_trades = []
        for trade in trades_query[:500]:  # Limit to avoid memory issues
            try:
                formatted_trades.append(format_trade_for_template(trade))
            except Exception as e:
                logger.error(f"Error formatting trade {trade.trade_id}: {e}")
                continue
        
        # Paginate the formatted trades
        paginator = Paginator(formatted_trades, 25)
        page_number = request.GET.get('page', 1)
        
        try:
            page_obj = paginator.get_page(page_number)
        except Exception as e:
            logger.warning(f"Pagination error: {e}")
            page_obj = paginator.get_page(1)
        
        # Calculate summary stats with safe decimal handling
        summary_stats = {
            'total_trades': 0,
            'total_volume': Decimal('0'),
            'avg_trade_size': Decimal('0'),
            'total_gas_cost': Decimal('0')
        }
        
        try:
            # Use raw SQL to avoid decimal issues
            with connection.cursor() as cursor:
                # Build WHERE clause for filters
                where_clauses = ["account_id = %s"]
                params = [str(account.account_id)]
                
                if status_filter:
                    where_clauses.append("status = %s")
                    params.append(status_filter)
                
                if trade_type_filter:
                    where_clauses.append("trade_type = %s")
                    params.append(trade_type_filter)
                
                if token_symbol:
                    where_clauses.append("(token_in_symbol LIKE %s OR token_out_symbol LIKE %s)")
                    params.extend([f'%{token_symbol}%', f'%{token_symbol}%'])
                
                if date_from:
                    where_clauses.append("created_at >= %s")
                    params.append(date_from)
                
                if date_to:
                    where_clauses.append("created_at <= %s")
                    params.append(date_to)
                
                where_sql = " AND ".join(where_clauses)
                
                cursor.execute(f"""
                    SELECT 
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN amount_in_usd IS NOT NULL THEN CAST(amount_in_usd AS REAL) ELSE 0 END) as total_volume,
                        AVG(CASE WHEN amount_in_usd IS NOT NULL THEN CAST(amount_in_usd AS REAL) ELSE NULL END) as avg_trade_size,
                        SUM(CASE WHEN simulated_gas_cost_usd IS NOT NULL THEN CAST(simulated_gas_cost_usd AS REAL) ELSE 0 END) as total_gas_cost
                    FROM paper_trading_papertrade
                    WHERE {where_sql}
                """, params)
                
                stats = cursor.fetchone()
                summary_stats = {
                    'total_trades': stats[0] or 0,
                    'total_volume': safe_decimal(str(stats[1] or 0)),
                    'avg_trade_size': safe_decimal(str(stats[2] or 0)),
                    'total_gas_cost': safe_decimal(str(stats[3] or 0))
                }
                
                logger.info(f"Successfully calculated summary stats: {summary_stats['total_trades']} trades")
                
        except Exception as e:
            logger.error(f"Error calculating summary stats: {e}", exc_info=True)
            # Keep default values
        
        context = {
            'page_title': 'Trade History',
            'account': account,
            'page_obj': page_obj,
            'trades': page_obj,
            'status_filter': status_filter,
            'trade_type_filter': trade_type_filter,
            'token_filter': token_symbol,
            'date_from': date_from,
            'date_to': date_to,
            'summary_stats': summary_stats,
            'user': user,
        }
        
        logger.info(f"Successfully loaded trade history page with {len(formatted_trades)} trades")
        return render(request, 'paper_trading/trade_history.html', context)
        
    except Exception as e:
        logger.error(f"Critical error loading trade history: {e}", exc_info=True)
        messages.error(request, f"Error loading trade history: {str(e)}")
        
        # Instead of redirecting, render the trade history with no data
        context = {
            'page_title': 'Trade History',
            'account': None,
            'page_obj': None,
            'trades': [],
            'status_filter': '',
            'trade_type_filter': '',
            'token_filter': '',
            'date_from': '',
            'date_to': '',
            'summary_stats': {
                'total_trades': 0,
                'total_volume': Decimal('0'),
                'avg_trade_size': Decimal('0'),
                'total_gas_cost': Decimal('0')
            },
            'user': None,
            'error_message': f"Unable to load trade history: {str(e)}"
        }
        
        return render(request, 'paper_trading/trade_history.html', context)


def portfolio_view(request: HttpRequest) -> HttpResponse:
    """
    Display portfolio positions and allocation.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered portfolio template
    """
    try:
        # Get the single account
        account = get_single_trading_account()
        user = account.user
        
        logger.debug(f"Loading portfolio view for account {account.account_id}")
        
        # Get positions with error handling and formatting
        try:
            raw_open_positions = PaperPosition.objects.filter(
                account=account,
                is_open=True
            ).order_by('-current_value_usd')
            open_positions = [format_position_for_template(pos) for pos in raw_open_positions]
        except Exception as e:
            logger.error(f"Error fetching open positions: {e}")
            open_positions = []
        
        try:
            raw_closed_positions = PaperPosition.objects.filter(
                account=account,
                is_open=False
            ).order_by('-closed_at')[:20]
            closed_positions = [format_position_for_template(pos) for pos in raw_closed_positions]
        except Exception as e:
            logger.error(f"Error fetching closed positions: {e}")
            closed_positions = []
        
        # Calculate portfolio metrics with safe decimal handling
        try:
            portfolio_value = safe_decimal(account.current_balance_usd) + sum(
                safe_decimal(pos['current_value_usd']) for pos in open_positions
            )
        except Exception as e:
            logger.error(f"Error calculating portfolio value: {e}")
            portfolio_value = safe_decimal(account.current_balance_usd)
        
        try:
            total_invested = sum(
                safe_decimal(pos['total_invested_usd']) for pos in open_positions
            )
        except Exception as e:
            logger.error(f"Error calculating total invested: {e}")
            total_invested = Decimal('0')
        
        total_current_value = sum(safe_decimal(pos['current_value_usd']) for pos in open_positions)
        unrealized_pnl = total_current_value - total_invested if total_invested > 0 else Decimal('0')
        
        # Position distribution for chart
        position_distribution = {}
        for pos in open_positions:
            try:
                if pos['token_symbol'] and portfolio_value > 0:
                    position_distribution[pos['token_symbol']] = {
                        'value': float(pos['current_value_usd']),
                        'percentage': float((pos['current_value_usd'] / portfolio_value * 100)),
                        'pnl': float(pos['unrealized_pnl_usd'])
                    }
            except Exception as e:
                logger.warning(f"Error calculating distribution for {pos['token_symbol']}: {e}")
                continue
        
        context = {
            'page_title': 'Portfolio',
            'account': account,
            'open_positions': open_positions,
            'closed_positions': closed_positions,
            'portfolio_value': portfolio_value,
            'cash_balance': safe_decimal(account.current_balance_usd),
            'total_invested': total_invested,
            'unrealized_pnl': unrealized_pnl,
            'position_distribution': json.dumps(position_distribution),
            'positions_count': len(open_positions),
            'user': user,
        }
        
        logger.info(f"Successfully loaded portfolio with {len(open_positions)} open positions")
        return render(request, 'paper_trading/portfolio.html', context)
        
    except Exception as e:
        logger.error(f"Error loading portfolio: {e}", exc_info=True)
        messages.error(request, f"Error loading portfolio: {str(e)}")
        return redirect('paper_trading:dashboard')


@require_http_methods(["GET", "POST"])
def configuration_view(request: HttpRequest) -> HttpResponse:
    """
    Strategy configuration management view with pagination and delete.
    
    Handles display, updates, and deletion of trading strategy configurations.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered configuration template or redirect after action
    """
    try:
        # Get the single account
        account = get_single_trading_account()
        user = account.user
        
        logger.debug(f"Loading configuration view for account {account.account_id}")
        
        # Handle delete action if requested
        if request.method == 'POST' and request.POST.get('action') == 'delete':
            config_id = request.POST.get('config_id')
            if config_id:
                try:
                    config_to_delete = PaperStrategyConfiguration.objects.get(
                        config_id=config_id,
                        account=account
                    )
                    # Don't delete if it's the only configuration or if it's active
                    total_configs = PaperStrategyConfiguration.objects.filter(account=account).count()
                    
                    if total_configs <= 1:
                        messages.warning(request, "Cannot delete the last configuration")
                    elif config_to_delete.is_active:
                        messages.warning(request, "Cannot delete active configuration. Please activate another configuration first.")
                    else:
                        config_name = config_to_delete.name
                        config_to_delete.delete()
                        messages.success(request, f'Configuration "{config_name}" deleted successfully')
                        logger.info(f"Deleted configuration {config_id} for account {account.account_id}")
                except PaperStrategyConfiguration.DoesNotExist:
                    messages.error(request, "Configuration not found")
                except Exception as e:
                    messages.error(request, f"Error deleting configuration: {str(e)}")
                    logger.error(f"Error deleting configuration: {e}", exc_info=True)
                
                return redirect('paper_trading:configuration')
        
        # Handle load/activate configuration
        if request.method == 'GET' and request.GET.get('load_config'):
            config_id = request.GET.get('load_config')
            try:
                config_to_load = PaperStrategyConfiguration.objects.get(
                    config_id=config_id,
                    account=account
                )
                # Deactivate all others and activate this one
                PaperStrategyConfiguration.objects.filter(
                    account=account
                ).update(is_active=False)
                
                config_to_load.is_active = True
                config_to_load.save()
                
                messages.success(request, f'Configuration "{config_to_load.name}" loaded and activated')
                logger.info(f"Loaded configuration {config_id} for account {account.account_id}")
                return redirect('paper_trading:configuration')
                
            except PaperStrategyConfiguration.DoesNotExist:
                messages.error(request, "Configuration not found")
            except Exception as e:
                messages.error(request, f"Error loading configuration: {str(e)}")
                logger.error(f"Error loading configuration: {e}", exc_info=True)
        
        # Get the active configuration
        config = PaperStrategyConfiguration.objects.filter(
            account=account,
            is_active=True
        ).order_by('-updated_at').first()
        
        # If no active config, get the most recent one
        if not config:
            config = PaperStrategyConfiguration.objects.filter(
                account=account
            ).order_by('-updated_at').first()
        
        # If still no config, create a new one with defaults
        if not config:
            config = PaperStrategyConfiguration.objects.create(
                account=account,
                name='Default Strategy',
                is_active=True,
                trading_mode='MODERATE',
                use_fast_lane=True,
                use_smart_lane=False,
                fast_lane_threshold_usd=Decimal('100'),
                max_position_size_percent=Decimal('25'),
                stop_loss_percent=Decimal('5'),
                take_profit_percent=Decimal('10'),
                max_daily_trades=20,
                max_concurrent_positions=10,
                min_liquidity_usd=Decimal('10000'),
                max_slippage_percent=Decimal('2'),
                confidence_threshold=Decimal('60'),
                allowed_tokens=[],
                blocked_tokens=[],
                custom_parameters={}
            )
            logger.info(f"Created new strategy configuration for account {account.account_id}")
        else:
            logger.info(f"Using existing configuration: {config.config_id}")
        
        # Handle configuration update (POST without delete action)
        if request.method == 'POST' and request.POST.get('action') != 'delete':
            try:
                # Check if creating new or updating existing
                save_as_new = request.POST.get('save_as_new') == 'true'
                
                if save_as_new:
                    # Create a new configuration
                    new_config = PaperStrategyConfiguration(account=account)
                    update_target = new_config
                    # Deactivate others if this will be active
                    if request.POST.get('is_active', 'true').lower() == 'true':
                        PaperStrategyConfiguration.objects.filter(
                            account=account
                        ).update(is_active=False)
                else:
                    update_target = config
                
                # Update configuration from form data
                update_target.name = request.POST.get('name', update_target.name if not save_as_new else 'New Strategy')
                update_target.trading_mode = request.POST.get('trading_mode', 'MODERATE')
                update_target.use_fast_lane = request.POST.get('use_fast_lane') == 'on'
                update_target.use_smart_lane = request.POST.get('use_smart_lane') == 'on'
                update_target.is_active = request.POST.get('is_active', 'true').lower() == 'true'
                
                # Update numeric fields with error handling
                try:
                    update_target.max_position_size_percent = Decimal(request.POST.get('max_position_size_percent', '25'))
                except (ValueError, InvalidOperation):
                    update_target.max_position_size_percent = Decimal('25')
                
                try:
                    update_target.max_daily_trades = int(request.POST.get('max_daily_trades', '20'))
                except ValueError:
                    update_target.max_daily_trades = 20
                
                try:
                    update_target.max_concurrent_positions = int(request.POST.get('max_concurrent_positions', '10'))
                except ValueError:
                    update_target.max_concurrent_positions = 10
                
                try:
                    update_target.confidence_threshold = Decimal(request.POST.get('confidence_threshold', '60'))
                except (ValueError, InvalidOperation):
                    update_target.confidence_threshold = Decimal('60')
                
                try:
                    update_target.stop_loss_percent = Decimal(request.POST.get('stop_loss_percent', '5'))
                except (ValueError, InvalidOperation):
                    update_target.stop_loss_percent = Decimal('5')
                
                try:
                    update_target.take_profit_percent = Decimal(request.POST.get('take_profit_percent', '10'))
                except (ValueError, InvalidOperation):
                    update_target.take_profit_percent = Decimal('10')
                
                try:
                    update_target.min_liquidity_usd = Decimal(request.POST.get('min_liquidity_usd', '10000'))
                except (ValueError, InvalidOperation):
                    update_target.min_liquidity_usd = Decimal('10000')
                
                try:
                    update_target.max_slippage_percent = Decimal(request.POST.get('max_slippage_percent', '2'))
                except (ValueError, InvalidOperation):
                    update_target.max_slippage_percent = Decimal('2')
                
                try:
                    update_target.fast_lane_threshold_usd = Decimal(request.POST.get('fast_lane_threshold_usd', '100'))
                except (ValueError, InvalidOperation):
                    update_target.fast_lane_threshold_usd = Decimal('100')
                
                # Save the configuration
                update_target.save()
                
                # If this config is set to active and not new, deactivate others
                if update_target.is_active and not save_as_new:
                    PaperStrategyConfiguration.objects.filter(
                        account=account
                    ).exclude(config_id=update_target.config_id).update(is_active=False)
                
                action_word = "created" if save_as_new else "updated"
                messages.success(request, f'Configuration "{update_target.name}" {action_word} successfully!')
                logger.info(f"{action_word.capitalize()} configuration {update_target.config_id} for account {account.account_id}")
                
                return redirect('paper_trading:configuration')
                
            except Exception as e:
                messages.error(request, f'Error saving configuration: {str(e)}')
                logger.error(f"Configuration save error: {e}", exc_info=True)
        
        # Get all configurations with pagination
        all_configs_query = PaperStrategyConfiguration.objects.filter(
            account=account
        ).order_by('-is_active', '-updated_at')  # Active first, then by update time
        
        # Pagination
        configs_per_page = 10  # Show 10 configs per page
        paginator = Paginator(all_configs_query, configs_per_page)
        page_number = request.GET.get('page', 1)
        
        try:
            all_configs = paginator.get_page(page_number)
        except Exception as e:
            logger.warning(f"Pagination error: {e}")
            all_configs = paginator.get_page(1)
        
        # Get active session for bot status
        active_session = PaperTradingSession.objects.filter(
            account=account,
            status__in=["ACTIVE", "RUNNING", "STARTING"]
        ).first()
        
        # Load available strategies
        available_strategies = [
            {'name': 'smart_lane', 'display': 'Smart Lane Strategy'},
            {'name': 'momentum', 'display': 'Momentum Trading'},
            {'name': 'mean_reversion', 'display': 'Mean Reversion'},
            {'name': 'arbitrage', 'display': 'Arbitrage Bot'},
        ]
        
        # Prepare context with safe decimal values
        context = {
            'page_title': 'Strategy Configuration',
            'account': account,
            'config': config,
            'available_strategies': available_strategies,
            'all_configs': all_configs,
            'active_session': active_session,
            'total_configs': all_configs_query.count(),
            'user': user,
            
            # Map actual model fields to template variables with safe decimals
            'strategy_config': {
                'config_id': str(config.config_id),
                'name': config.name,
                'is_active': config.is_active,
                'trading_mode': config.trading_mode,
                'use_fast_lane': config.use_fast_lane,
                'use_smart_lane': config.use_smart_lane,
                'fast_lane_threshold_usd': safe_decimal(config.fast_lane_threshold_usd),
                'max_position_size_percent': safe_decimal(config.max_position_size_percent),
                'stop_loss_percent': safe_decimal(config.stop_loss_percent),
                'take_profit_percent': safe_decimal(config.take_profit_percent),
                'max_daily_trades': config.max_daily_trades,
                'max_concurrent_positions': config.max_concurrent_positions,
                'min_liquidity_usd': safe_decimal(config.min_liquidity_usd),
                'max_slippage_percent': safe_decimal(config.max_slippage_percent),
                'confidence_threshold': safe_decimal(config.confidence_threshold),
                'allowed_tokens': config.allowed_tokens if config.allowed_tokens else [],
                'blocked_tokens': config.blocked_tokens if config.blocked_tokens else [],
                'custom_parameters': config.custom_parameters if config.custom_parameters else {},
                'created_at': config.created_at,
                'updated_at': config.updated_at,
            }
        }
        
        logger.info(f"Successfully loaded configuration view with {all_configs_query.count()} configs")
        return render(request, 'paper_trading/configuration.html', context)
        
    except Exception as e:
        logger.error(f"Error in configuration view: {e}", exc_info=True)
        messages.error(request, f"Error loading configuration: {str(e)}")
        return redirect('paper_trading:dashboard')


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
        # Get the single account
        account = get_single_trading_account()
        user = account.user
        
        logger.debug(f"Loading analytics view for account {account.account_id}")
        
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
                logger.debug(f"Using date_from: {date_from}")
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid date_from format: {date_from}, error: {e}")
        
        date_to = request.GET.get('date_to')
        if date_to:
            try:
                end_date = timezone.make_aware(
                    datetime.strptime(date_to, '%Y-%m-%d')
                )
                logger.debug(f"Using date_to: {date_to}")
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid date_to format: {date_to}, error: {e}")
        
        # Get trades using raw SQL to avoid decimal conversion issues
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) as total_trades,
                           SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                           SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                           SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                           SUM(CASE WHEN amount_in_usd IS NOT NULL THEN CAST(amount_in_usd AS REAL) ELSE 0 END) as total_volume,
                           AVG(CASE WHEN amount_in_usd IS NOT NULL THEN CAST(amount_in_usd AS REAL) ELSE NULL END) as avg_trade_size
                    FROM paper_trading_papertrade
                    WHERE account_id = %s
                      AND created_at >= %s
                      AND created_at <= %s
                """, [str(account.account_id), start_date, end_date])
                
                trade_stats = cursor.fetchone()
                total_trades = trade_stats[0] or 0
                completed_trades = trade_stats[1] or 0
                failed_trades = trade_stats[2] or 0
                pending_trades = trade_stats[3] or 0
                total_volume = safe_decimal(str(trade_stats[4] or 0))
                avg_trade_size = safe_decimal(str(trade_stats[5] or 0))
                
                logger.info(f"Loaded trade statistics: {total_trades} total trades")
                
        except Exception as e:
            logger.error(f"Error fetching trade statistics: {e}")
            total_trades = 0
            completed_trades = 0
            failed_trades = 0
            pending_trades = 0
            total_volume = Decimal('0')
            avg_trade_size = Decimal('0')
        
        # Get token distribution using raw SQL to avoid decimal issues
        token_stats = {}
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        token_out_symbol,
                        COUNT(*) as count,
                        SUM(CASE WHEN amount_in_usd IS NULL THEN 0 ELSE CAST(amount_in_usd AS REAL) END) as total_volume,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as success,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                    FROM paper_trading_papertrade
                    WHERE account_id = %s
                        AND created_at >= %s
                        AND created_at <= %s
                        AND token_out_symbol IS NOT NULL
                    GROUP BY token_out_symbol
                    ORDER BY total_volume DESC
                    LIMIT 10
                """, [str(account.account_id), start_date, end_date])
                
                for row in cursor.fetchall():
                    token_stats[row[0]] = {
                        'count': row[1],
                        'volume': safe_decimal(str(row[2])) if row[2] else Decimal('0'),
                        'success': row[3],
                        'failed': row[4]
                    }
                    
                logger.info(f"Loaded token statistics for {len(token_stats)} tokens")
                    
        except Exception as e:
            logger.error(f"Error calculating token stats: {e}", exc_info=True)
            token_stats = {}
        
        # Get performance metrics
        try:
            latest_metrics = PaperPerformanceMetrics.objects.filter(
                session__account=account
            ).order_by('-created_at').first()
        except Exception as e:
            logger.error(f"Error fetching performance metrics: {e}")
            latest_metrics = None
        
        # Get daily performance data
        daily_performance = []
        try:
            current_date = start_date.date()
            while current_date <= end_date.date():
                day_start = timezone.make_aware(
                    datetime.combine(current_date, datetime.min.time())
                )
                day_end = timezone.make_aware(
                    datetime.combine(current_date, datetime.max.time())
                )
                
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as count,
                            SUM(CASE WHEN amount_in_usd IS NULL THEN 0 ELSE CAST(amount_in_usd AS REAL) END) as volume
                        FROM paper_trading_papertrade
                        WHERE account_id = %s
                          AND created_at >= %s
                          AND created_at <= %s
                    """, [str(account.account_id), day_start, day_end])
                    
                    day_stats = cursor.fetchone()
                    daily_performance.append({
                        'date': current_date.isoformat(),
                        'trades': day_stats[0] or 0,
                        'volume': float(day_stats[1] or 0)
                    })
                
                current_date += timedelta(days=1)
                
        except Exception as e:
            logger.error(f"Error calculating daily performance: {e}")
            daily_performance = []
        
        # Calculate additional metrics
        # FIXED: Get actual winning/losing trades from closed positions
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_closed,
                        SUM(CASE WHEN realized_pnl_usd > 0 THEN 1 ELSE 0 END) as winning,
                        SUM(CASE WHEN realized_pnl_usd < 0 THEN 1 ELSE 0 END) as losing
                    FROM paper_positions
                    WHERE account_id = %s AND is_open = FALSE
                """, [str(account.account_id)])
                
                position_stats = cursor.fetchone()
                total_closed_positions = position_stats[0] or 0
                winning_trades_positions = position_stats[1] or 0
                losing_trades_positions = position_stats[2] or 0
        except Exception as e:
            logger.error(f"Error fetching position stats: {e}")
            total_closed_positions = 0
            winning_trades_positions = 0
            losing_trades_positions = 0
        
        # Win rate based on closed positions, not trade executions
        win_rate = (winning_trades_positions / total_closed_positions * 100) if total_closed_positions > 0 else 0
        
        # Calculate period-specific metrics
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        
        # Get trade counts for different periods
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        SUM(CASE WHEN DATE(created_at) = %s THEN 1 ELSE 0 END) as today_trades,
                        SUM(CASE WHEN DATE(created_at) >= %s THEN 1 ELSE 0 END) as week_trades
                    FROM paper_trading_papertrade
                    WHERE account_id = %s
                """, [today, week_ago, str(account.account_id)])
                
                period_stats = cursor.fetchone()
                today_trades_count = period_stats[0] or 0
                week_trades_count = period_stats[1] or 0
        except Exception as e:
            logger.error(f"Error calculating period stats: {e}")
            today_trades_count = 0
            week_trades_count = 0
        
        # Prepare context for template with safe decimal values
        context = {
            'page_title': 'Paper Trading Analytics',
            'has_data': total_trades > 0,
            'account': account,
            'date_from': start_date.date(),
            'date_to': end_date.date(),
            'user': user,
            
            # Key metrics with safe decimals
            'win_rate': float(win_rate),
            'profit_factor': 1.5 if win_rate > 50 else 0.8,
            'total_trades': total_trades,
            'avg_profit': float(safe_decimal(account.total_profit_loss_usd) / completed_trades) if completed_trades > 0 else 0,
            'avg_loss': float(abs(safe_decimal(account.total_profit_loss_usd)) / failed_trades) if failed_trades > 0 else 0,
            'max_drawdown': 15.5,  # Placeholder
            
            # Period performance
            'today_pnl': 0,
            'today_trades': today_trades_count,
            'week_pnl': 0,
            'week_trades': week_trades_count,
            'month_pnl': float(safe_decimal(account.total_profit_loss_usd or 0)),
            'month_trades': total_trades,
            
            # Chart data
            'daily_pnl_data': json.dumps(daily_performance),
            'hourly_distribution': json.dumps([]),
            'token_stats': json.dumps(
                [{'name': k, 'value': float(v['volume'])} for k, v in list(token_stats.items())[:5]]
            ),
            
            # Top performers
            'top_performers': [
                {
                    'symbol': symbol,
                    'trades': stats['count'],
                    'win_rate': (stats['success'] / stats['count'] * 100) if stats['count'] > 0 else 0,
                    'total_pnl': float(stats['volume'] * Decimal('0.02'))
                }
                for symbol, stats in list(token_stats.items())[:5]
            ] if token_stats else [],
            
            # Risk metrics
            'sharpe_ratio': float(latest_metrics.sharpe_ratio) if latest_metrics and latest_metrics.sharpe_ratio else 0,
            'best_hours': [],
            
            # Account metrics with safe decimals
            'account_pnl': float(safe_decimal(account.total_profit_loss_usd or 0)),
            'account_return': float(safe_decimal(account.get_roi() or 0)),
        }
        
        logger.info(f"Successfully loaded analytics for account {account.account_id}")
        return render(request, 'paper_trading/paper_trading_analytics.html', context)
        
    except Exception as e:
        logger.error(f"Critical error in analytics view: {e}", exc_info=True)
        messages.error(request, f"Error loading analytics: {str(e)}")
        return redirect('paper_trading:dashboard')


@require_http_methods(["GET"])
def api_analytics_data(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to fetch analytics data for real-time updates.
    
    Returns JSON data for updating charts without page refresh.
    """
    try:
        # Get the single account
        account = get_single_trading_account()
        
        logger.debug(f"API call for analytics data for account {account.account_id}")
        
        # FIXED: Get metrics using correct position-based winning/losing trades
        with connection.cursor() as cursor:
            # Get total trade executions
            cursor.execute("""
                SELECT COUNT(*) as total_trades
                FROM paper_trading_papertrade
                WHERE account_id = %s
            """, [str(account.account_id)])
            
            total_trades = cursor.fetchone()[0] or 0
            
            # Get winning/losing trades from closed positions
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_closed,
                    SUM(CASE WHEN realized_pnl_usd > 0 THEN 1 ELSE 0 END) as winning,
                    SUM(CASE WHEN realized_pnl_usd < 0 THEN 1 ELSE 0 END) as losing
                FROM paper_positions
                WHERE account_id = %s AND is_open = FALSE
            """, [str(account.account_id)])
            
            position_stats = cursor.fetchone()
            total_closed_positions = position_stats[0] or 0
            winning_trades = position_stats[1] or 0
            losing_trades = position_stats[2] or 0
            win_rate = (winning_trades / total_closed_positions * 100) if total_closed_positions > 0 else 0
        
        logger.info(f"API analytics data: {total_trades} trades, {total_closed_positions} closed positions, {win_rate:.1f}% win rate")
        
        return JsonResponse({
            'success': True,
            'metrics': {
                'win_rate': float(win_rate),
                'total_trades': total_trades,  # Total trade executions
                'total_closed_positions': total_closed_positions,  # Closed positions
                'winning_trades': winning_trades,  # Profitable positions
                'losing_trades': losing_trades,  # Losing positions
                'timestamp': timezone.now().isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Error in api_analytics_data: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_analytics_export(request: HttpRequest) -> HttpResponse:
    """
    Export analytics data to CSV format.
    """
    import csv
    
    try:
        # Get the single account
        account = get_single_trading_account()
        
        logger.info(f"Exporting analytics data to CSV for account {account.account_id}")
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="paper_trading_analytics.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow(['Date', 'Trade ID', 'Token In', 'Token Out', 'Type', 'Amount USD', 'Status'])
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    created_at, trade_id, token_in_symbol, token_out_symbol, 
                    trade_type, amount_in_usd, status
                FROM paper_trading_papertrade
                WHERE account_id = %s
                ORDER BY created_at DESC
            """, [str(account.account_id)])
            
            for row in cursor.fetchall():
                writer.writerow([
                    row[0].strftime('%Y-%m-%d %H:%M:%S') if row[0] else '',
                    row[1],
                    row[2] or '',
                    row[3] or '',
                    row[4] or '',
                    float(row[5]) if row[5] else 0,
                    row[6] or ''
                ])
        
        logger.info(f"Analytics export completed successfully")
        return response
        
    except Exception as e:
        logger.error(f"Error exporting analytics: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def calculate_portfolio_metrics(account: PaperTradingAccount) -> Dict[str, Any]:
    """
    Calculate detailed portfolio metrics.
    
    FIXED: Now correctly calculates winning/losing trades from PaperPosition.realized_pnl_usd
    instead of incorrectly using PaperTrade.status='completed'.
    
    Helper function to calculate various performance metrics for an account.
    
    Args:
        account: Paper trading account
        
    Returns:
        Dictionary with calculated metrics
    """
    try:
        logger.debug(f"Calculating portfolio metrics for account {account.account_id}")
        
        # FIXED: Query PaperPosition table to get actual profit/loss data
        # Winning trades = closed positions with positive realized P&L
        # Losing trades = closed positions with negative realized P&L
        with connection.cursor() as cursor:
            # Get closed positions with profit/loss data
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_positions,
                    SUM(CASE WHEN realized_pnl_usd > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(CASE WHEN realized_pnl_usd < 0 THEN 1 ELSE 0 END) as losing_trades,
                    SUM(CASE WHEN realized_pnl_usd = 0 THEN 1 ELSE 0 END) as breakeven_trades,
                    SUM(realized_pnl_usd) as total_realized_pnl
                FROM paper_positions
                WHERE account_id = %s AND is_open = FALSE
            """, [str(account.account_id)])
            
            stats = cursor.fetchone()
            total_closed_positions = stats[0] or 0
            winning_trades = stats[1] or 0
            losing_trades = stats[2] or 0
            breakeven_trades = stats[3] or 0
            total_realized_pnl = Decimal(str(stats[4])) if stats[4] else Decimal('0')
            
            # Also get total number of trades executed
            cursor.execute("""
                SELECT COUNT(*) as total_trades
                FROM paper_trading_papertrade
                WHERE account_id = %s
            """, [str(account.account_id)])
            
            total_trades = cursor.fetchone()[0] or 0
        
        # Calculate win rate based on closed positions
        win_rate = (winning_trades / total_closed_positions * 100) if total_closed_positions > 0 else 0
        
        # Calculate profit factor (total wins / total losses)
        # This requires calculating average win vs average loss
        if winning_trades > 0 and losing_trades > 0:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        AVG(CASE WHEN realized_pnl_usd > 0 THEN realized_pnl_usd ELSE NULL END) as avg_win,
                        AVG(CASE WHEN realized_pnl_usd < 0 THEN ABS(realized_pnl_usd) ELSE NULL END) as avg_loss
                    FROM paper_positions
                    WHERE account_id = %s AND is_open = FALSE
                """, [str(account.account_id)])
                
                pnl_stats = cursor.fetchone()
                avg_win = Decimal(str(pnl_stats[0])) if pnl_stats[0] else Decimal('0')
                avg_loss = Decimal(str(pnl_stats[1])) if pnl_stats[1] else Decimal('1')
                
                # Profit factor = (avg_win * win_count) / (avg_loss * loss_count)
                profit_factor = float((avg_win * winning_trades) / (avg_loss * losing_trades)) if avg_loss > 0 else 0
        else:
            profit_factor = 0
        
        metrics = {
            'total_trades': total_trades,  # Total trade executions
            'total_closed_positions': total_closed_positions,  # Total positions closed
            'winning_trades': winning_trades,  # Positions with profit
            'losing_trades': losing_trades,  # Positions with loss
            'breakeven_trades': breakeven_trades,  # Positions that broke even
            'win_rate': float(win_rate),
            'profit_factor': float(profit_factor),
            'total_realized_pnl': float(total_realized_pnl),
        }
        
        logger.info(
            f"Portfolio metrics calculated: {total_closed_positions} closed positions, "
            f"{winning_trades} wins, {losing_trades} losses, {win_rate:.1f}% win rate, "
            f"profit factor: {profit_factor:.2f}"
        )
        return metrics
        
    except Exception as e:
        logger.error(f"Error calculating portfolio metrics: {e}", exc_info=True)
        return {
            'total_trades': 0,
            'total_closed_positions': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'breakeven_trades': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'total_realized_pnl': 0,
            'error': str(e)
        }