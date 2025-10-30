"""
Paper Trading Account API

Handles account management operations including reset and add funds.

File: paper_trading/api/account_management_api.py
"""

import json
import logging
from decimal import Decimal

from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import transaction

# Import models
from ..models import (
    PaperPosition,
    PaperTradingSession,
)

# Import constants
from ..constants import (
    SessionStatus,
)

# Import utilities
from ..utils import get_single_trading_account

logger = logging.getLogger(__name__)


# =============================================================================
# ACCOUNT RESET API
# =============================================================================

@require_http_methods(["POST"])
@csrf_exempt
def api_reset_account(request: HttpRequest) -> JsonResponse:
    """
    Reset paper trading account and add new funds.

    This endpoint will:
    1. Close all open positions and calculate realized P&L
    2. Stop any active bot sessions
    3. Reset account balance to the specified amount
    4. Create a new trading session

    Request Body:
        {
            "amount": 10000.00  # New balance amount in USD
        }

    Response:
        {
            "success": true,
            "data": {
                "new_balance": 10000.00,
                "positions_closed": 5,
                "realized_pnl": -125.50,
                "new_session_name": "Session #15"
            }
        }

    Returns:
        JsonResponse: Reset confirmation with details
    """
    try:
        # Parse request body
        try:
            body_data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON in request body'
            }, status=400)

        # Validate amount
        amount = body_data.get('amount')
        if amount is None:
            return JsonResponse({
                'success': False,
                'error': 'Missing required field: amount'
            }, status=400)

        try:
            amount = Decimal(str(amount))
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid amount value'
            }, status=400)

        # Validate amount range
        if amount < Decimal('100') or amount > Decimal('1000000'):
            return JsonResponse({
                'success': False,
                'error': 'Amount must be between $100 and $1,000,000'
            }, status=400)

        # Get account
        account = get_single_trading_account()

        logger.info(f"Resetting account {account.account_id} with new balance: ${amount}")

        # Use transaction to ensure atomicity
        with transaction.atomic():
            # Step 1: Close all open positions and calculate realized P&L
            open_positions = PaperPosition.objects.filter(
                account=account,
                is_open=True
            ).select_for_update()

            positions_closed = 0
            total_realized_pnl = Decimal('0')

            for position in open_positions:
                # Calculate realized P&L for this position
                realized_pnl = position.unrealized_pnl_usd or Decimal('0')
                total_realized_pnl += realized_pnl

                # Close the position
                position.is_open = False
                position.closed_at = timezone.now()
                position.realized_pnl_usd = realized_pnl
                position.save()

                positions_closed += 1
                logger.debug(f"Closed position {position.position_id}: {position.token_symbol} with P&L ${realized_pnl}")

            # Step 2: Stop any active bot sessions
            active_sessions = PaperTradingSession.objects.filter(
                account=account,
                status__in=[SessionStatus.RUNNING, SessionStatus.STARTING]
            ).select_for_update()

            for session in active_sessions:
                session.status = SessionStatus.STOPPED
                session.stopped_at = timezone.now()
                # Note: end_reason field doesn't exist in model
                session.save()
                logger.debug(f"Stopped session {session.session_id}")

            # Step 3: Reset account balance
            old_balance = account.current_balance_usd
            account.current_balance_usd = amount
            account.initial_balance_usd = amount
            account.total_profit_loss_usd = Decimal('0')
            # reset_count field doesn't exist in model
            account.save()

            logger.info(f"Reset account balance from ${old_balance} to ${amount}")

            # Step 4: Create new session for tracking
            session_count = PaperTradingSession.objects.filter(account=account).count()
            new_session = PaperTradingSession.objects.create(
                account=account,
                status=SessionStatus.STOPPED,
                started_at=timezone.now(),
                metadata={
                    'session_type': 'reset',
                    'previous_balance': float(old_balance),
                    'new_balance': float(amount),
                    'positions_closed': positions_closed,
                    'realized_pnl': float(total_realized_pnl)
                }
            )

            new_session_name = f"Session #{session_count + 1}"
            logger.info(f"Created new session: {new_session_name} (ID: {new_session.session_id})")

        # Return success response
        return JsonResponse({
            'success': True,
            'data': {
                'new_balance': float(amount),
                'positions_closed': positions_closed,
                'realized_pnl': float(total_realized_pnl),
                'new_session_name': new_session_name,
                'account_id': str(account.account_id),
                # reset_count field doesn't exist
            }
        })

    except Exception as e:
        logger.error(f"Error resetting account: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# GET SESSIONS HISTORY API
# =============================================================================

@require_http_methods(["GET"])
def api_sessions_history(request: HttpRequest) -> JsonResponse:
    """
    Get sessions history for comparison graph.

    Returns all completed sessions with their performance data
    for displaying in the sessions comparison chart.

    Query Parameters:
        limit (int): Number of sessions to return (default: 10)

    Returns:
        JsonResponse: List of sessions with metrics
    """
    try:
        account = get_single_trading_account()

        # Get limit parameter
        limit = int(request.GET.get('limit', 10))
        limit = min(limit, 50)  # Cap at 50 sessions

        # Get completed sessions
        sessions = PaperTradingSession.objects.filter(
            account=account,
            status__in=['COMPLETED', 'STOPPED']
        ).order_by('-started_at')[:limit]

        sessions_data = []
        for session in sessions:
            # Get starting balance from metadata
            starting_balance = Decimal('0')
            if session.metadata and 'starting_balance' in session.metadata:
                starting_balance = Decimal(str(session.metadata['starting_balance']))

            # Get session name from metadata
            session_name = session.metadata.get('session_name', f"Session {session.session_id.hex[:8]}")

            # Get final balance by looking at positions closed during this session
            positions = PaperPosition.objects.filter(
                account=account,
                opened_at__gte=session.started_at,
                closed_at__lte=session.stopped_at if session.stopped_at else timezone.now()
            )

            total_pnl = sum(
                pos.realized_pnl_usd if pos.realized_pnl_usd else Decimal('0')
                for pos in positions
            )

            ending_balance = starting_balance + total_pnl

            # Calculate win rate
            win_rate = 0
            if session.total_trades and session.total_trades > 0:
                win_rate = (
                    (session.successful_trades / session.total_trades) * 100
                    if session.successful_trades
                    else 0
                )

            sessions_data.append({
                'session_id': str(session.session_id),
                'session_name': session_name,
                'started_at': session.started_at.isoformat(),
                'ended_at': session.stopped_at.isoformat() if session.stopped_at else None,
                'starting_balance': float(starting_balance),
                'ending_balance': float(ending_balance),
                'total_pnl': float(total_pnl),
                'total_pnl_percent': float((total_pnl / starting_balance * 100) if starting_balance > 0 else 0),
                'total_trades': session.total_trades or 0,
                'winning_trades': session.successful_trades or 0,
                'losing_trades': session.failed_trades or 0,
                'win_rate': float(win_rate),
                'status': session.status,
            })

        return JsonResponse({
            'success': True,
            'sessions': sessions_data,
            'count': len(sessions_data)
        })

    except Exception as e:
        logger.error(f"Error fetching sessions history: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
