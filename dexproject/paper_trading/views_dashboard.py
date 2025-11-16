"""
Paper Trading Views - Dashboard

Main dashboard view displaying portfolio summary, active positions,
recent trades, and performance metrics with AI thought logs.

File: dexproject/paper_trading/views_dashboard.py
"""

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Dict, Any
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required  # ADDED: For sessions_history
from django.db import connection
from django.db.models import Count, Sum

from .models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperAIThoughtLog,
    PaperTradingSession,
    PaperPerformanceMetrics
)
from .utils import get_single_trading_account
from .utils.type_utils import to_decimal
from .views_helpers import format_trade_for_template, format_position_for_template

logger = logging.getLogger(__name__)


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
        account: PaperTradingAccount = get_single_trading_account()
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
                old_session.stopped_at = timezone.now()
                old_session.save()
                logger.info(f"Closed old session from {old_session.started_at.date()}: {old_session.session_id}")
        
        # =====================================================================
        # RECENT TRADES WITH PAGINATION (5 per page)
        # =====================================================================
        try:
            raw_trades = PaperTrade.objects.filter(
                account=account
            ).order_by('-created_at')
            
            # Paginate trades - 5 per page
            trades_page_number = request.GET.get('trades_page', 1)
            trades_paginator = Paginator(raw_trades, 5)  # 5 trades per page
            
            # Safe page retrieval
            if trades_paginator.num_pages == 0:
                # No items, create empty page object manually
                trades_page_obj = None
                recent_trades = []
            else:
                try:
                    trades_page_obj = trades_paginator.page(trades_page_number)
                    recent_trades = [format_trade_for_template(trade) for trade in trades_page_obj]
                except PageNotAnInteger:
                    # Page is not an integer, deliver first page
                    trades_page_obj = trades_paginator.page(1)
                    recent_trades = [format_trade_for_template(trade) for trade in trades_page_obj]
                except EmptyPage:
                    # Page is out of range, deliver last page
                    trades_page_obj = trades_paginator.page(trades_paginator.num_pages)
                    recent_trades = [format_trade_for_template(trade) for trade in trades_page_obj]
            
        except Exception as e:
            logger.warning(f"Error fetching recent trades: {e}", exc_info=True)
            recent_trades = []
            trades_page_obj = None
        
        # =====================================================================
        # OPEN POSITIONS WITH PAGINATION (5 per page)
        # =====================================================================
        try:
            raw_positions = PaperPosition.objects.filter(
                account=account,
                is_open=True
            ).order_by('-current_value_usd')
            
            # Paginate positions - 5 per page
            positions_page_number = request.GET.get('positions_page', 1)
            positions_paginator = Paginator(raw_positions, 5)  # 5 positions per page
            
            # Safe page retrieval
            if positions_paginator.num_pages == 0:
                # No items, create empty page object manually
                positions_page_obj = None
                open_positions = []
                total_open_positions = 0
            else:
                try:
                    positions_page_obj = positions_paginator.page(positions_page_number)
                    open_positions = [format_position_for_template(pos) for pos in positions_page_obj]
                    total_open_positions = raw_positions.count()
                except PageNotAnInteger:
                    # Page is not an integer, deliver first page
                    positions_page_obj = positions_paginator.page(1)
                    open_positions = [format_position_for_template(pos) for pos in positions_page_obj]
                    total_open_positions = raw_positions.count()
                except EmptyPage:
                    # Page is out of range, deliver last page
                    positions_page_obj = positions_paginator.page(positions_paginator.num_pages)
                    open_positions = [format_position_for_template(pos) for pos in positions_page_obj]
                    total_open_positions = raw_positions.count()
            
        except Exception as e:
            logger.warning(f"Error fetching open positions: {e}", exc_info=True)
            open_positions = []
            positions_page_obj = None
            total_open_positions = 0
        
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
                'confidence_percent': thought.confidence_percent,
                'created_at': thought.created_at,
                'thought_content': thought.primary_reasoning[:150] if thought.primary_reasoning else "Analyzing market conditions...",
                '_original': thought
            })

        # DEBUG: Log what we're passing to template
        logger.info(f"=== DEBUG: Passing {len(formatted_thoughts)} thoughts to template ===")
        for i, ft in enumerate(formatted_thoughts):
            logger.info(f"Thought {i+1}: {ft['created_at']} - {ft['decision_type']} - {ft['token_symbol']}")
        
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
            # Get closed position stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_closed,
                    SUM(CASE WHEN realized_pnl_usd > 0 THEN 1 ELSE 0 END) as winning,
                    SUM(CASE WHEN realized_pnl_usd < 0 THEN 1 ELSE 0 END) as losing
                FROM paper_positions
                WHERE account_id = %s AND is_open = FALSE
            """, [str(account.account_id)])
            
            position_stats = cursor.fetchone()
            if position_stats is not None:
                total_closed_positions = position_stats[0] or 0
                winning_trades = position_stats[1] or 0
                # losing_trades not used in dashboard view - only winning trades shown
            else:
                total_closed_positions = 0
                winning_trades = 0
        
        # Get total trades (number of trade executions)
        total_trades = PaperTrade.objects.filter(account=account).count()
        
        # Calculate total portfolio value = cash balance + value of open positions
        total_portfolio_value = to_decimal(account.current_balance_usd)
        for position in open_positions:
            total_portfolio_value += to_decimal(position['current_value_usd'])
        
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
            'trades_page_obj': trades_page_obj,  # 🆕 Pagination object for trades
            'open_positions': open_positions,
            'positions_page_obj': positions_page_obj,  # 🆕 Pagination object for positions
            'open_positions_count': total_open_positions,  # 🆕 Total count (not just current page)
            'performance': performance,
            'recent_thoughts': formatted_thoughts,
            'total_trades': total_trades,  # Total trade executions
            'successful_trades': winning_trades,  # Winning positions (realized_pnl_usd > 0)
            'total_closed_positions': total_closed_positions,  # Total closed positions
            'win_rate': to_decimal((winning_trades / total_closed_positions * 100) if total_closed_positions > 0 else 0),
            'trades_24h': trades_24h.get('count', 0),
            'volume_24h': to_decimal(trades_24h.get('total_volume', 0)),
            'current_balance': to_decimal(account.current_balance_usd),  # Cash balance only
            'portfolio_value': total_portfolio_value,  # FIXED: Total value = cash + open positions
            'initial_balance': to_decimal(account.initial_balance_usd),
            'total_pnl': to_decimal(account.total_profit_loss_usd),
            'return_percent': to_decimal(account.get_roi()),
            'user': user,
        }
        
        logger.info(f"Successfully loaded dashboard for account {account.account_id}")
        return render(request, 'paper_trading/dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Error loading paper trading dashboard: {e}", exc_info=True)
        messages.error(request, f"Error loading dashboard: {str(e)}")
        return render(request, 'paper_trading/error.html', {"error": str(e)})


# =============================================================================
# SESSIONS HISTORY VIEW
# =============================================================================

@login_required
def sessions_history(request: HttpRequest) -> HttpResponse:
    """
    Render the sessions history and comparison page.
    
    This page allows users to view and compare performance across different
    trading sessions. Data is loaded dynamically via the API endpoint
    /paper-trading/api/sessions/history/
    
    URL: GET /paper-trading/sessions/
    Django Name: paper_trading:sessions
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered sessions_analysis.html template with context data
    """
    try:
        context = {
            'page_title': 'Sessions History',
            'active_page': 'sessions'
        }
        
        logger.info("Rendering sessions history page")
        return render(request, 'paper_trading/sessions_analysis.html', context)
        
    except Exception as e:
        logger.error(f"Error rendering sessions page: {e}", exc_info=True)
        context = {
            'error': 'Failed to load sessions page',
            'error_details': str(e)
        }
        return render(request, 'paper_trading/sessions_analysis.html', context, status=500)