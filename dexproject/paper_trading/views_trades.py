"""
Paper Trading Views - Trade History

Trade history view with filtering, pagination, and summary statistics.
Displays detailed trade execution history with comprehensive filters.

File: dexproject/paper_trading/views_trades.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any

from django.shortcuts import render
from django.http import HttpRequest, HttpResponse
from django.contrib import messages
from django.db import connection
from django.db.models import Q
from django.core.paginator import Paginator

from .models import PaperTradingAccount, PaperTrade
from .utils import get_single_trading_account, to_decimal
from .views_helpers import format_trade_for_template

logger = logging.getLogger(__name__)


def trade_history(request: HttpRequest) -> HttpResponse:
    """
    Display detailed trade history with filtering and pagination.
    
    Provides comprehensive trade filtering by status, trade type, token,
    and date range. Includes summary statistics and pagination support.
    
    Args:
        request: Django HTTP request with optional filters
        
    Returns:
        Rendered trade history template
    """
    try:
        # Get the single account
        account: PaperTradingAccount = get_single_trading_account()
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
        for trade in trades_query.iterator():  # Use iterator() to handle decimal errors
            try:
                formatted_trades.append(format_trade_for_template(trade))
            except Exception as e:
                logger.error(f"Error formatting trade {trade.trade_id}: {e}")
                continue
        
        # Paginate the formatted trades
        paginator = Paginator(formatted_trades, 5)
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
                    params.extend([f"%{token_symbol}%", f"%{token_symbol}%"])
                
                if date_from:
                    where_clauses.append("created_at >= %s")
                    params.append(date_from)
                
                if date_to:
                    where_clauses.append("created_at <= %s")
                    params.append(date_to)
                
                where_clause = " AND ".join(where_clauses)
                
                # Calculate summary statistics
                cursor.execute(f"""
                    SELECT 
                        COUNT(*) as total_trades,
                        COALESCE(SUM(CAST(amount_in_usd AS REAL)), 0) as total_volume,
                        COALESCE(AVG(CAST(amount_in_usd AS REAL)), 0) as avg_trade_size,
                        COALESCE(SUM(CAST(simulated_gas_cost_usd AS REAL)), 0) as total_gas_cost
                    FROM paper_trades
                    WHERE {where_clause}
                """, params)
                
                stats = cursor.fetchone()
                if stats:
                    summary_stats = {
                        'total_trades': stats[0] or 0,
                        'total_volume': Decimal(str(stats[1] or 0)),
                        'avg_trade_size': Decimal(str(stats[2] or 0)),
                        'total_gas_cost': Decimal(str(stats[3] or 0))
                    }
                
                logger.debug(
                    f"Successfully calculated summary stats: {summary_stats['total_trades']} trades")
                
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