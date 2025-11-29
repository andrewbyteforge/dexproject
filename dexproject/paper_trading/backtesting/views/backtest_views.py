"""
Backtest Dashboard Views

Django views for the backtesting interface:
- Main dashboard with backtest configuration
- Results display and analysis
- Strategy comparison

Phase 7B - Day 13: Backtesting Views

File: dexproject/paper_trading/backtesting/views/backtest_views.py
"""

import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal
from datetime import datetime, timedelta
from django.shortcuts import render, get_object_or_404
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.db.models import Avg, Count, Q

from paper_trading.backtesting.models import BacktestRun, BacktestResult
from paper_trading.backtesting.constants import YAHOO_TICKER_MAPPING


logger = logging.getLogger(__name__)


# =============================================================================
# BACKTEST DASHBOARD VIEW
# =============================================================================

def backtest_dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    Main backtesting dashboard.
    
    Displays:
    - Backtest configuration form
    - Recent backtest results
    - Performance comparisons
    - Available tokens
    
    URL: /paper-trading/backtest/
    Template: paper_trading/backtest/backtest_dashboard.html
    """
    try:
        # Get filter parameters from query string
        strategy_filter = request.GET.get('strategy', '')
        token_filter = request.GET.get('token', '')
        status_filter = request.GET.get('status', '')
        
        # Build queryset for recent backtests
        backtests = BacktestRun.objects.all()
        
        if strategy_filter:
            backtests = backtests.filter(strategy_type=strategy_filter.upper())
        
        if token_filter:
            backtests = backtests.filter(token_symbol=token_filter.upper())
        
        if status_filter:
            backtests = backtests.filter(status=status_filter.upper())
        
        # Get recent backtests with results
        recent_backtests = backtests.select_related('result').order_by('-created_at')[:20]
        
        # Get statistics
        stats = _get_dashboard_statistics()
        
        # Get available tokens
        available_tokens = _get_available_tokens()
        
        # Get strategy options
        strategy_options = _get_strategy_options()
        
        # Get date range suggestions
        date_ranges = _get_date_range_suggestions()
        
        # Prepare backtest list for template
        backtest_list = []
        for run in recent_backtests:
            backtest_data = {
                'backtest_id': str(run.backtest_id),
                'strategy_type': run.strategy_type,
                'strategy_display': run.get_strategy_type_display(),
                'token_symbol': run.token_symbol,
                'status': run.status,
                'status_display': run.get_status_display(),
                'start_date': run.start_date,
                'end_date': run.end_date,
                'created_at': run.created_at,
                'duration': run.duration_display(),
                'initial_balance': run.initial_balance_usd,
            }
            
            # Add result data if completed
            if run.status == BacktestRun.STATUS_COMPLETED:
                try:
                    result = run.result
                    backtest_data.update({
                        'has_result': True,
                        'return_percent': result.return_percent,
                        'profit_loss': result.profit_loss_usd,
                        'win_rate': result.win_rate_percent,
                        'sharpe_ratio': result.sharpe_ratio,
                        'num_trades': result.num_trades,
                        'performance_grade': result.performance_grade(),
                        'is_profitable': result.is_profitable(),
                    })
                except BacktestResult.DoesNotExist:
                    backtest_data['has_result'] = False
            else:
                backtest_data['has_result'] = False
            
            # Add error message if failed
            if run.status == BacktestRun.STATUS_FAILED:
                backtest_data['error_message'] = run.error_message
            
            backtest_list.append(backtest_data)
        
        # Prepare context
        context = {
            'page_title': 'Backtesting Dashboard',
            'backtests': backtest_list,
            'stats': stats,
            'available_tokens': available_tokens,
            'strategy_options': strategy_options,
            'date_ranges': date_ranges,
            'current_filters': {
                'strategy': strategy_filter,
                'token': token_filter,
                'status': status_filter,
            },
        }
        
        logger.info(
            f"[BACKTEST VIEW] Dashboard loaded: {len(backtest_list)} backtests displayed"
        )
        
        return render(request, 'paper_trading/backtest/backtest_dashboard.html', context)
        
    except Exception as e:
        logger.error(
            f"[BACKTEST VIEW] Error loading dashboard: {e}",
            exc_info=True
        )
        
        # Return error page
        context = {
            'page_title': 'Backtesting Dashboard',
            'error_message': f'Error loading dashboard: {str(e)}',
            'backtests': [],
            'stats': {},
        }
        return render(request, 'paper_trading/backtest/backtest_dashboard.html', context)


# =============================================================================
# BACKTEST DETAIL VIEW
# =============================================================================

def backtest_detail_view(request: HttpRequest, backtest_id: str) -> HttpResponse:
    """
    Detailed view of a specific backtest.
    
    Displays:
    - Full backtest configuration
    - Complete performance metrics
    - Trade-by-trade breakdown
    - Performance charts
    
    URL: /paper-trading/backtest/<backtest_id>/
    Template: paper_trading/backtest/backtest_detail.html
    """
    try:
        # Fetch backtest run
        backtest_run = get_object_or_404(BacktestRun, backtest_id=backtest_id)
        
        # Prepare basic info
        backtest_info = {
            'backtest_id': str(backtest_run.backtest_id),
            'strategy_type': backtest_run.strategy_type,
            'strategy_display': backtest_run.get_strategy_type_display(),
            'token_symbol': backtest_run.token_symbol,
            'status': backtest_run.status,
            'status_display': backtest_run.get_status_display(),
            'start_date': backtest_run.start_date,
            'end_date': backtest_run.end_date,
            'interval': backtest_run.interval,
            'initial_balance': backtest_run.initial_balance_usd,
            'strategy_params': backtest_run.strategy_params,
            'fee_percent': backtest_run.fee_percent,
            'created_at': backtest_run.created_at,
            'completed_at': backtest_run.completed_at,
            'duration': backtest_run.duration_display(),
            'data_points': backtest_run.data_points,
        }
        
        # Add result data if completed
        result_data = None
        trades_data = None
        
        if backtest_run.status == BacktestRun.STATUS_COMPLETED:
            try:
                result = backtest_run.result
                
                result_data = {
                    'final_balance': result.final_balance_usd,
                    'profit_loss': result.profit_loss_usd,
                    'return_percent': result.return_percent,
                    'total_fees': result.total_fees_usd,
                    'num_trades': result.num_trades,
                    'num_buys': result.num_buys,
                    'num_sells': result.num_sells,
                    'avg_entry_price': result.avg_entry_price,
                    'win_rate': result.win_rate_percent,
                    'profit_factor': result.profit_factor,
                    'max_drawdown': result.max_drawdown_percent,
                    'sharpe_ratio': result.sharpe_ratio,
                    'sortino_ratio': result.sortino_ratio,
                    'avg_holding_hours': result.avg_holding_hours,
                    'max_consecutive_wins': result.max_consecutive_wins,
                    'max_consecutive_losses': result.max_consecutive_losses,
                    'performance_grade': result.performance_grade(),
                    'is_profitable': result.is_profitable(),
                }
                
                # Get trades data
                trades_data = result.trades_data
                
                # Calculate additional metrics for display
                result_data.update(_calculate_display_metrics(result))
                
            except BacktestResult.DoesNotExist:
                logger.warning(
                    f"[BACKTEST VIEW] No result found for completed backtest {backtest_id}"
                )
        
        # Add error message if failed
        error_message = None
        if backtest_run.status == BacktestRun.STATUS_FAILED:
            error_message = backtest_run.error_message
        
        # Prepare context
        context = {
            'page_title': f'Backtest Details - {backtest_run.strategy_type} on {backtest_run.token_symbol}',
            'backtest': backtest_info,
            'result': result_data,
            'trades': trades_data,
            'error_message': error_message,
        }
        
        logger.info(
            f"[BACKTEST VIEW] Detail view loaded for backtest {backtest_id}"
        )
        
        return render(request, 'paper_trading/backtest/backtest_detail.html', context)
        
    except Exception as e:
        logger.error(
            f"[BACKTEST VIEW] Error loading backtest detail: {e}",
            exc_info=True
        )
        
        # Return 404 or error page
        context = {
            'page_title': 'Backtest Not Found',
            'error_message': f'Error loading backtest: {str(e)}',
        }
        return render(request, 'paper_trading/backtest/backtest_detail.html', context, status=404)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_dashboard_statistics() -> Dict[str, Any]:
    """
    Calculate dashboard statistics.
    
    Returns:
        Dictionary with statistics
    """
    try:
        total_backtests = BacktestRun.objects.count()
        completed_backtests = BacktestRun.objects.filter(
            status=BacktestRun.STATUS_COMPLETED
        ).count()
        
        # Get average return across all completed backtests
        avg_return = BacktestResult.objects.aggregate(
            avg_return=Avg('return_percent')
        )['avg_return'] or Decimal('0')
        
        # Get best performing backtest
        best_backtest = BacktestResult.objects.order_by('-return_percent').first()
        
        # Get profitable backtests count
        profitable_count = BacktestResult.objects.filter(
            return_percent__gt=Decimal('0')
        ).count()
        
        # Calculate success rate
        success_rate = (
            (Decimal(str(profitable_count)) / Decimal(str(completed_backtests)) * Decimal('100'))
            if completed_backtests > 0
            else Decimal('0')
        )
        
        return {
            'total_backtests': total_backtests,
            'completed_backtests': completed_backtests,
            'avg_return_percent': avg_return,
            'success_rate_percent': success_rate,
            'best_return_percent': best_backtest.return_percent if best_backtest else Decimal('0'),
            'best_strategy': best_backtest.backtest_run.strategy_type if best_backtest else 'N/A',
        }
        
    except Exception as e:
        logger.error(f"[BACKTEST VIEW] Error calculating statistics: {e}")
        return {
            'total_backtests': 0,
            'completed_backtests': 0,
            'avg_return_percent': Decimal('0'),
            'success_rate_percent': Decimal('0'),
            'best_return_percent': Decimal('0'),
            'best_strategy': 'N/A',
        }


def _get_available_tokens() -> List[Dict[str, str]]:
    """
    Get list of available tokens for backtesting.
    
    Returns:
        List of token dictionaries
    """
    tokens = []
    
    for symbol, ticker in YAHOO_TICKER_MAPPING.items():
        tokens.append({
            'symbol': symbol,
            'yahoo_ticker': ticker if ticker else 'Stablecoin ($1.00)',
            'is_stablecoin': ticker is None,
        })
    
    # Sort by symbol
    tokens.sort(key=lambda x: x['symbol'])
    
    return tokens


def _get_strategy_options() -> List[Dict[str, str]]:
    """
    Get list of available strategies.
    
    Returns:
        List of strategy dictionaries
    """
    return [
        {
            'value': BacktestRun.STRATEGY_SPOT,
            'label': 'Spot Buy',
            'description': 'Single buy and hold strategy',
        },
        {
            'value': BacktestRun.STRATEGY_DCA,
            'label': 'Dollar Cost Averaging',
            'description': 'Split purchases over time at regular intervals',
        },
        {
            'value': BacktestRun.STRATEGY_GRID,
            'label': 'Grid Trading',
            'description': 'Profit from price oscillations in range',
        },
        {
            'value': BacktestRun.STRATEGY_TWAP,
            'label': 'TWAP (Time-Weighted)',
            'description': 'Equal-sized chunks for illiquid markets',
        },
        {
            'value': BacktestRun.STRATEGY_VWAP,
            'label': 'VWAP (Volume-Weighted)',
            'description': 'Volume-optimized execution for liquid markets',
        },
    ]


def _get_date_range_suggestions() -> List[Dict[str, str]]:
    """
    Get suggested date ranges for backtesting.
    
    Returns:
        List of date range dictionaries
    """
    now = timezone.now()
    
    return [
        {
            'label': 'Last 7 Days',
            'start_date': (now - timedelta(days=7)).isoformat(),
            'end_date': now.isoformat(),
        },
        {
            'label': 'Last 30 Days',
            'start_date': (now - timedelta(days=30)).isoformat(),
            'end_date': now.isoformat(),
        },
        {
            'label': 'Last 90 Days',
            'start_date': (now - timedelta(days=90)).isoformat(),
            'end_date': now.isoformat(),
        },
        {
            'label': 'Last 6 Months',
            'start_date': (now - timedelta(days=180)).isoformat(),
            'end_date': now.isoformat(),
        },
        {
            'label': 'Last Year',
            'start_date': (now - timedelta(days=365)).isoformat(),
            'end_date': now.isoformat(),
        },
    ]


def _calculate_display_metrics(result: BacktestResult) -> Dict[str, Any]:
    """
    Calculate additional metrics for display.
    
    Args:
        result: BacktestResult instance
        
    Returns:
        Dictionary with display metrics
    """
    try:
        # Calculate average trade metrics from trades_data
        trades = result.trades_data
        
        if not trades:
            return {}
        
        # Calculate average trade size
        buy_trades = [t for t in trades if t.get('side') == 'BUY']
        avg_trade_size = (
            sum(Decimal(t['amount_usd']) for t in buy_trades) / len(buy_trades)
            if buy_trades else Decimal('0')
        )
        
        # Calculate best and worst trades
        trade_pnls = []
        for i, buy in enumerate(buy_trades):
            sell_trades = [t for t in trades if t.get('side') == 'SELL']
            if i < len(sell_trades):
                sell = sell_trades[i]
                pnl = Decimal(sell['amount_usd']) - Decimal(buy['amount_usd'])
                trade_pnls.append(pnl)
        
        best_trade = max(trade_pnls) if trade_pnls else Decimal('0')
        worst_trade = min(trade_pnls) if trade_pnls else Decimal('0')
        
        return {
            'avg_trade_size': avg_trade_size,
            'best_trade_pnl': best_trade,
            'worst_trade_pnl': worst_trade,
        }
        
    except Exception as e:
        logger.error(f"[BACKTEST VIEW] Error calculating display metrics: {e}")
        return {}