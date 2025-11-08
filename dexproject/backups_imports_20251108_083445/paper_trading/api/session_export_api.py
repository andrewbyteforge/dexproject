"""
Paper Trading Session Export API

Provides CSV export functionality for individual trading sessions
with complete session details, configuration, trades, and performance metrics.

File: dexproject/paper_trading/api/session_export_api.py
"""

import csv
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from ..models import PaperTradingSession, PaperTrade
from ..utils import get_single_trading_account

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def api_export_session_csv(request: HttpRequest, session_id: str) -> HttpResponse:
    """
    Export a single trading session to CSV format.
    
    Generates a comprehensive CSV file containing:
    - Session overview (name, dates, duration, status)
    - Strategy configuration settings
    - Trade statistics (total, winning, losing, win rate)
    - Performance metrics (P&L, balance changes)
    - Individual trade details
    
    Args:
        request: Django HTTP request
        session_id: UUID of the session to export
        
    Returns:
        CSV file download response
        
    URL: GET /paper-trading/api/sessions/<session_id>/export/
    """
    try:
        logger.info(f"Starting CSV export for session {session_id}")
        
        # Get the account
        account = get_single_trading_account()
        
        # Get the session
        try:
            session = PaperTradingSession.objects.select_related(
                'strategy_config'
            ).get(
                session_id=session_id,
                account=account
            )
        except PaperTradingSession.DoesNotExist:
            logger.error(f"Session {session_id} not found")
            return JsonResponse({
                'success': False,
                'error': 'Session not found'
            }, status=404)
        
        # Get session metadata
        metadata = session.metadata or {}
        session_name = metadata.get('session_name', f'Session {session.session_id.hex[:8]}')
        starting_balance = Decimal(str(metadata.get('starting_balance', 0)))
        ending_balance = Decimal(str(metadata.get('ending_balance', 0)))
        
        # Calculate session duration
        duration_str = "N/A"
        if session.stopped_at and session.started_at:
            duration = session.stopped_at - session.started_at
            hours = int(duration.total_seconds() // 3600)
            minutes = int((duration.total_seconds() % 3600) // 60)
            duration_str = f"{hours}h {minutes}m"
        
        # Calculate P&L
        pnl_usd = ending_balance - starting_balance
        pnl_percent = (pnl_usd / starting_balance * 100) if starting_balance > 0 else 0
        
        # Calculate winning/losing trades from the session's stored statistics
        # Note: PaperTrade doesn't have a session field either
        # Use the session's built-in counters which are updated during trading
        winning_trades = session.successful_trades
        losing_trades = session.failed_trades
        
        # Calculate win rate
        total_closed_trades = winning_trades + losing_trades
        win_rate = (winning_trades / total_closed_trades * 100) if total_closed_trades > 0 else 0
        
        # Create CSV response
        filename = f"session_{session_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv"
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        
        # =====================================================================
        # SECTION 1: SESSION OVERVIEW
        # =====================================================================
        writer.writerow(['SESSION OVERVIEW'])
        writer.writerow([''])
        writer.writerow(['Session Name', session_name])
        writer.writerow(['Session ID', str(session.session_id)])
        writer.writerow(['Status', session.status])
        writer.writerow(['Started At', session.started_at.strftime('%Y-%m-%d %H:%M:%S') if session.started_at else 'N/A'])
        writer.writerow(['Stopped At', session.stopped_at.strftime('%Y-%m-%d %H:%M:%S') if session.stopped_at else 'N/A'])
        writer.writerow(['Duration', duration_str])
        writer.writerow([''])
        
        # =====================================================================
        # SECTION 2: PERFORMANCE METRICS
        # =====================================================================
        writer.writerow(['PERFORMANCE METRICS'])
        writer.writerow([''])
        writer.writerow(['Starting Balance (USD)', f'${starting_balance:,.2f}'])
        writer.writerow(['Ending Balance (USD)', f'${ending_balance:,.2f}'])
        writer.writerow(['Profit/Loss (USD)', f'${pnl_usd:,.2f}'])
        writer.writerow(['Profit/Loss (%)', f'{pnl_percent:.2f}%'])
        writer.writerow([''])
        
        # =====================================================================
        # SECTION 3: TRADE STATISTICS
        # =====================================================================
        writer.writerow(['TRADE STATISTICS'])
        writer.writerow([''])
        writer.writerow(['Total Trades Executed', session.total_trades])
        writer.writerow(['Total Closed Positions', total_closed_trades])
        writer.writerow(['Winning Trades', winning_trades])
        writer.writerow(['Losing Trades', losing_trades])
        writer.writerow(['Win Rate (%)', f'{win_rate:.2f}%'])
        writer.writerow(['Successful Trade Executions', session.successful_trades])
        writer.writerow(['Failed Trade Executions', session.failed_trades])
        writer.writerow([''])
        
        # =====================================================================
        # SECTION 4: STRATEGY CONFIGURATION
        # =====================================================================
        writer.writerow(['STRATEGY CONFIGURATION'])
        writer.writerow([''])
        
        if session.strategy_config:
            config = session.strategy_config
            writer.writerow(['Configuration Name', config.name])
            writer.writerow(['Trading Mode', config.trading_mode])
            writer.writerow(['Intelligence Level', config.intelligence_level])
            writer.writerow(['Min Confidence (%)', config.min_confidence_score])
            writer.writerow(['Max Position Size (USD)', f'${config.max_position_size_usd:,.2f}'])
            writer.writerow(['Stop Loss (%)', config.stop_loss_percent])
            writer.writerow(['Take Profit (%)', config.take_profit_percent])
            writer.writerow(['Max Hold Hours', config.max_hold_hours])
            writer.writerow(['Max Open Positions', config.max_open_positions])
            writer.writerow(['Daily Trade Limit', config.daily_trade_limit])
            writer.writerow(['Gas Strategy', config.gas_strategy])
            writer.writerow(['Auto Pilot Enabled', 'Yes' if config.autopilot_enabled else 'No'])
        else:
            writer.writerow(['No configuration data available'])
        
        writer.writerow([''])
        
        # =====================================================================
        # SECTION 5: INDIVIDUAL TRADES
        # =====================================================================
        writer.writerow(['INDIVIDUAL TRADES'])
        writer.writerow([''])
        
        # Trade headers
        writer.writerow([
            'Date',
            'Time',
            'Trade Type',
            'Token In',
            'Token Out',
            'Amount In',
            'Amount In (USD)',
            'Amount Out',
            'Gas Cost (USD)',
            'Slippage (%)',
            'Status',
            'Execution Time (ms)'
        ])
        
        # Get trades for this session by filtering on timestamp range
        # Note: PaperTrade doesn't have a session field, so we filter by time
        trades_query = PaperTrade.objects.filter(
            account=account,
            created_at__gte=session.started_at
        )
        
        # If session has ended, only include trades up to that point
        if session.stopped_at:
            trades_query = trades_query.filter(created_at__lte=session.stopped_at)
        
        trades = trades_query.order_by('created_at')
        
        for trade in trades:
            writer.writerow([
                trade.created_at.strftime('%Y-%m-%d') if trade.created_at else '',
                trade.created_at.strftime('%H:%M:%S') if trade.created_at else '',
                trade.trade_type.upper(),
                trade.token_in_symbol,
                trade.token_out_symbol,
                f'{trade.amount_in:.6f}',
                f'${trade.amount_in_usd:.2f}',
                f'{trade.actual_amount_out:.6f}' if trade.actual_amount_out else f'{trade.expected_amount_out:.6f}',
                f'${trade.simulated_gas_cost_usd:.2f}',
                f'{trade.simulated_slippage_percent:.2f}',
                trade.status.upper(),
                trade.execution_time_ms if trade.execution_time_ms else 'N/A'
            ])
        
        logger.info(f"CSV export completed successfully for session {session_id}")
        return response
        
    except Exception as e:
        logger.error(f"Error exporting session {session_id} to CSV: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Export failed: {str(e)}'
        }, status=500)


