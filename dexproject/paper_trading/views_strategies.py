"""
Paper Trading Views - Strategy Performance History

Strategy performance history view displaying aggregated statistics by strategy type.
Shows bot's strategy selection intelligence with success rates, P&L, and usage metrics.

Phase 7B - Day 6-7: Strategy History View

File: dexproject/paper_trading/views_strategies.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List

from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse
from django.contrib import messages
from django.db import connection

from .models import PaperTradingAccount, StrategyRun
from .utils import get_single_trading_account
from .utils.type_utils import to_decimal
from .constants import StrategyType, StrategyStatus

logger = logging.getLogger(__name__)


# =============================================================================
# STRATEGY HISTORY VIEW
# =============================================================================

def strategies_view(request: HttpRequest) -> HttpResponse:
    """
    Display strategy performance history and statistics.
    
    Shows aggregated performance metrics for each strategy type (DCA, GRID, SPOT)
    that the bot has deployed, including:
    - Total usage count per strategy
    - Success rate (% of strategies that completed successfully)
    - Total P&L per strategy type
    - Average ROI per strategy type
    - Overall strategy statistics
    
    This view demonstrates the bot's intelligence by showing which strategies
    it selected and how they performed over time.
    
    Args:
        request: Django HTTP request
        
    Returns:
        Rendered strategies template with performance data
    """
    try:
        # Get the single account
        account: PaperTradingAccount = get_single_trading_account()
        user = account.user
        
        logger.debug(f"Loading strategy history for account {account.account_id}")
        
        # =============================================================================
        # QUERY STRATEGY STATISTICS BY TYPE
        # =============================================================================
        
        strategy_stats = {}
        total_strategies = 0
        total_pnl = Decimal('0.00')
        overall_success_rate = Decimal('0.00')
        
        try:
            with connection.cursor() as cursor:
                # Get aggregated statistics by strategy type
                # Success = strategies with COMPLETED status and positive completion rate
                cursor.execute("""
                    SELECT 
                        strategy_type,
                        COUNT(*) as total_count,
                        SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_count,
                        SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed_count,
                        COALESCE(SUM(CAST(total_invested AS REAL)), 0) as total_invested,
                        COALESCE(SUM(CAST(current_pnl AS REAL)), 0) as total_pnl,
                        COALESCE(AVG(CAST(current_pnl AS REAL)), 0) as avg_pnl,
                        COALESCE(AVG(CAST(progress_percent AS REAL)), 0) as avg_progress,
                        SUM(total_orders) as total_orders_sum,
                        SUM(completed_orders) as completed_orders_sum
                    FROM paper_strategy_runs
                    WHERE account_id = %s
                    GROUP BY strategy_type
                    ORDER BY total_count DESC
                """, [str(account.account_id)])
                
                rows = cursor.fetchall()
                
                for row in rows:
                    strategy_type = row[0]
                    total_count = row[1] or 0
                    completed_count = row[2] or 0
                    failed_count = row[3] or 0
                    total_invested = Decimal(str(row[4] or 0))
                    total_pnl_type = Decimal(str(row[5] or 0))
                    avg_pnl = Decimal(str(row[6] or 0))
                    avg_progress = Decimal(str(row[7] or 0))
                    total_orders_sum = row[8] or 0
                    completed_orders_sum = row[9] or 0
                    
                    # Calculate success rate (completed strategies / total strategies)
                    success_rate = Decimal('0.00')
                    if total_count > 0:
                        success_rate = (Decimal(str(completed_count)) / Decimal(str(total_count))) * Decimal('100')
                    
                    # Calculate average ROI
                    avg_roi = Decimal('0.00')
                    if total_invested > 0:
                        avg_roi = (total_pnl_type / total_invested) * Decimal('100')
                    
                    # Calculate order completion rate
                    order_success_rate = Decimal('0.00')
                    if total_orders_sum > 0:
                        order_success_rate = (Decimal(str(completed_orders_sum)) / Decimal(str(total_orders_sum))) * Decimal('100')
                    
                    strategy_stats[strategy_type] = {
                        'strategy_type': strategy_type,
                        'total_count': total_count,
                        'completed_count': completed_count,
                        'failed_count': failed_count,
                        'success_rate': success_rate,
                        'total_invested': total_invested,
                        'total_pnl': total_pnl_type,
                        'avg_pnl': avg_pnl,
                        'avg_roi': avg_roi,
                        'avg_progress': avg_progress,
                        'total_orders': total_orders_sum,
                        'completed_orders': completed_orders_sum,
                        'order_success_rate': order_success_rate,
                    }
                    
                    # Update totals
                    total_strategies += total_count
                    total_pnl += total_pnl_type
                    
                logger.debug(f"Loaded strategy stats for {len(strategy_stats)} strategy types")
                
        except Exception as e:
            logger.error(f"Error querying strategy statistics: {e}", exc_info=True)
            strategy_stats = {}
            total_strategies = 0
            total_pnl = Decimal('0.00')
        
        # =============================================================================
        # CALCULATE OVERALL STATISTICS
        # =============================================================================
        
        # Calculate overall success rate across all strategies
        if total_strategies > 0:
            try:
                total_completed = sum(s['completed_count'] for s in strategy_stats.values())
                overall_success_rate = (Decimal(str(total_completed)) / Decimal(str(total_strategies))) * Decimal('100')
            except Exception as e:
                logger.warning(f"Error calculating overall success rate: {e}")
                overall_success_rate = Decimal('0.00')
        
        # Calculate overall average ROI
        overall_avg_roi = Decimal('0.00')
        try:
            total_invested_all = sum(s['total_invested'] for s in strategy_stats.values())
            if total_invested_all > 0:
                overall_avg_roi = (total_pnl / total_invested_all) * Decimal('100')
        except Exception as e:
            logger.warning(f"Error calculating overall ROI: {e}")
            overall_avg_roi = Decimal('0.00')
        
        # =============================================================================
        # GET RECENT STRATEGY RUNS FOR TIMELINE
        # =============================================================================
        
        recent_strategies = []
        try:
            recent_runs = StrategyRun.objects.filter(
                account=account
            ).select_related('account').order_by('-created_at')[:10]
            
            for strategy_run in recent_runs:
                recent_strategies.append({
                    'strategy_id': str(strategy_run.strategy_id),
                    'strategy_type': strategy_run.strategy_type,
                    'status': strategy_run.status,
                    'created_at': strategy_run.created_at,
                    'completed_at': strategy_run.completed_at,
                    'progress_percent': to_decimal(strategy_run.progress_percent),
                    'total_orders': strategy_run.total_orders,
                    'completed_orders': strategy_run.completed_orders,
                    'total_invested': to_decimal(strategy_run.total_invested),
                    'current_pnl': to_decimal(strategy_run.current_pnl),
                })
                
            logger.debug(f"Loaded {len(recent_strategies)} recent strategy runs")
            
        except Exception as e:
            logger.error(f"Error loading recent strategies: {e}", exc_info=True)
            recent_strategies = []
        
        # =============================================================================
        # BUILD CONTEXT AND RENDER
        # =============================================================================
        
        # Ensure we have entries for all strategy types (even if unused)
        for strategy_type in [StrategyType.DCA, StrategyType.GRID, StrategyType.SPOT]:
            if strategy_type not in strategy_stats:
                strategy_stats[strategy_type] = {
                    'strategy_type': strategy_type,
                    'total_count': 0,
                    'completed_count': 0,
                    'failed_count': 0,
                    'success_rate': Decimal('0.00'),
                    'total_invested': Decimal('0.00'),
                    'total_pnl': Decimal('0.00'),
                    'avg_pnl': Decimal('0.00'),
                    'avg_roi': Decimal('0.00'),
                    'avg_progress': Decimal('0.00'),
                    'total_orders': 0,
                    'completed_orders': 0,
                    'order_success_rate': Decimal('0.00'),
                }
        
        # Sort strategy stats by usage count (most used first)
        sorted_strategy_stats = dict(
            sorted(
                strategy_stats.items(),
                key=lambda x: x[1]['total_count'],
                reverse=True
            )
        )
        
        context = {
            'page_title': 'Strategy Performance',
            'account': account,
            'user': user,
            'strategy_stats': sorted_strategy_stats,
            'recent_strategies': recent_strategies,
            'total_strategies': total_strategies,
            'total_pnl': total_pnl,
            'overall_success_rate': overall_success_rate,
            'overall_avg_roi': overall_avg_roi,
            # Strategy type constants for template
            'STRATEGY_DCA': StrategyType.DCA,
            'STRATEGY_GRID': StrategyType.GRID,
            'STRATEGY_SPOT': StrategyType.SPOT,
        }
        
        logger.info(
            f"Successfully loaded strategy history: {total_strategies} total strategies, "
            f"{len(sorted_strategy_stats)} types used"
        )
        
        return render(request, 'paper_trading/strategies.html', context)
        
    except Exception as e:
        logger.error(f"Critical error loading strategy history: {e}", exc_info=True)
        messages.error(request, f"Error loading strategy history: {str(e)}")
        
        # Fallback to dashboard on critical error
        return redirect('paper_trading:dashboard')


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================

logger.info("Paper trading strategy history view loaded")