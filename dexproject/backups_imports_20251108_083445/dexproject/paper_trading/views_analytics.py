"""
Paper Trading Views - Analytics

Analytics dashboard and API endpoints for performance analysis,
data visualization, and CSV export functionality.

File: dexproject/paper_trading/views_analytics.py
"""

import csv
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any

from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import connection
from django.db.models import Sum, Count

from .models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPerformanceMetrics
)
from .utils import get_single_trading_account, to_decimal

logger = logging.getLogger(__name__)


def analytics_view(request: HttpRequest) -> HttpResponse:
    """
    Analytics view for paper trading performance analysis.
    
    Displays comprehensive performance metrics, trading statistics,
    daily performance trends, token distribution, and top performers.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered analytics template with performance data
    """
    try:
        # Get the single account
        account: PaperTradingAccount = get_single_trading_account()
        user = account.user
        
        logger.debug(f"Loading analytics for account {account.account_id}")
        
        # Define date range for analytics
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)  # Last 30 days
        
        # Get trade counts for different periods
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = timezone.now() - timedelta(days=7)
        
        today_trades_count = PaperTrade.objects.filter(
            account=account,
            created_at__gte=today_start
        ).count()
        
        week_trades_count = PaperTrade.objects.filter(
            account=account,
            created_at__gte=week_start
        ).count()
        
        total_trades = PaperTrade.objects.filter(account=account).count()
        
        # Calculate trade statistics using raw SQL for better performance
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_trades,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_trades,
                        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_trades,
                        COALESCE(SUM(CASE WHEN amount_in_usd IS NOT NULL THEN CAST(amount_in_usd AS REAL) ELSE 0 END), 0) as total_volume,
                        AVG(CASE WHEN amount_in_usd IS NOT NULL THEN CAST(amount_in_usd AS REAL) ELSE NULL END) as avg_trade_size
                    FROM paper_trading_papertrade
                    WHERE account_id = %s
                      AND created_at >= %s
                      AND created_at <= %s
                """, [str(account.account_id), start_date, end_date])
                
                trade_stats = cursor.fetchone()
                if trade_stats is not None:
                    total_trades = trade_stats[0] or 0
                    completed_trades = trade_stats[1] or 0
                    failed_trades = trade_stats[2] or 0
                    # pending_trades, total_volume, avg_trade_size not used in this view
                else:
                    total_trades = 0
                    completed_trades = 0
                    failed_trades = 0
                
                logger.info(f"Loaded trade statistics: {total_trades} total trades")
                
        except Exception as e:
            logger.error(f"Error fetching trade statistics: {e}")
            total_trades = 0
            completed_trades = 0
            failed_trades = 0
        
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
                        'volume': to_decimal(str(row[2])) if row[2] else Decimal('0'),
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
            current_date = start_date
            while current_date.date() <= end_date.date():
                day_start = timezone.make_aware(
                    datetime.combine(current_date.date(), datetime.min.time())
                )
                day_end = timezone.make_aware(
                    datetime.combine(current_date.date(), datetime.max.time())
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
                    if day_stats is not None:
                        daily_performance.append({
                            'date': current_date.date().isoformat(),
                            'trades': day_stats[0] or 0,
                            'volume': float(day_stats[1] or 0)
                        })
                    else:
                        daily_performance.append({
                            'date': current_date.date().isoformat(),
                            'trades': 0,
                            'volume': 0.0
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
                if position_stats is not None:
                    total_closed_positions = position_stats[0] or 0
                    winning_trades_positions = position_stats[1] or 0
                    # losing_trades_positions not used - only winning trades displayed
                else:
                    total_closed_positions = 0
                    winning_trades_positions = 0
        except Exception as e:
            logger.error(f"Error fetching position stats: {e}")
            total_closed_positions = 0
            winning_trades_positions = 0
        
        # Win rate based on closed positions
        win_rate = (winning_trades_positions / total_closed_positions * 100) if total_closed_positions > 0 else 0
        
        # Prepare context
        context = {
            'page_title': 'Analytics',
            'account': account,
            'user': user,
            'has_data': total_trades > 0,
            
            # Trading metrics
            'total_trades': total_trades,
            'winning_trades': winning_trades_positions,
            'total_closed_positions': total_closed_positions,
            'win_rate': win_rate,
            'profit_factor': 1.5,  # Placeholder
            'max_drawdown': 15.5,  # Placeholder
            
            # Period performance
            'today_pnl': 0,
            'today_trades': today_trades_count,
            'week_pnl': 0,
            'week_trades': week_trades_count,
            'month_pnl': float(to_decimal(account.total_profit_loss_usd or 0)),
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
            'account_pnl': float(to_decimal(account.total_profit_loss_usd or 0)),
            'account_return': float(to_decimal(account.get_roi() or 0)),
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
    
    Args:
        request: Django HTTP request
        
    Returns:
        JsonResponse with analytics metrics
    """
    try:
        # Get the single account
        account: PaperTradingAccount = get_single_trading_account()
        
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
            if position_stats is not None:
                total_closed_positions = position_stats[0] or 0
                winning_trades = position_stats[1] or 0
                # losing_trades = position_stats[2] or 0  # Not returned in API response
                win_rate = (winning_trades / total_closed_positions * 100) if total_closed_positions > 0 else 0
            else:
                total_closed_positions = 0
                winning_trades = 0
                win_rate = 0
        
        logger.info(f"API analytics data: {total_trades} trades, {total_closed_positions} closed positions, {win_rate:.1f}% win rate")
        
        return JsonResponse({
            'success': True,
            'metrics': {
                'win_rate': float(win_rate),
                'total_trades': total_trades,  # Total trade executions
                'total_closed_positions': total_closed_positions,  # Closed positions
                'winning_trades': winning_trades,  # Profitable positions
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
    
    Generates a CSV file with all trade data for the account,
    including date, trade ID, tokens, type, amount, and status.
    
    Args:
        request: Django HTTP request
        
    Returns:
        CSV file download response
    """
    try:
        # Get the single account
        account: PaperTradingAccount = get_single_trading_account()
        
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