"""
Paper Trading API - Account Management

API endpoints for account balance management, session resets,
and fund allocation. Handles account lifecycle operations.

File: dexproject/paper_trading/api/account_management_api.py
"""

import logging
from decimal import Decimal

from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import transaction

from ..models import (
    PaperPosition,
    PaperTradingSession,
    PaperTrade,
)
from ..utils import get_single_trading_account, to_decimal

logger = logging.getLogger(__name__)


# =============================================================================
# RESET & ADD FUNDS API
# =============================================================================

@require_http_methods(["POST"])
def api_reset_and_add_funds(request: HttpRequest) -> JsonResponse:
    """
    Reset account and add funds - creates a new isolated trading session.

    This endpoint:
    1. Validates bot is stopped
    2. Force closes all open positions at current prices
    3. Calculates and archives final session metrics
    4. Resets account balance to specified amount
    5. Creates new session with fresh start

    POST Body:
        {
            "amount": 10000.00  # Amount to add in USD
        }

    Returns:
        JsonResponse: Success status with new session info
    """
    try:
        # Parse request body
        import json
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON format'
            }, status=400)

        # Validate amount
        amount_str = data.get('amount')
        if not amount_str:
            return JsonResponse({
                'success': False,
                'error': 'Amount is required'
            }, status=400)

        try:
            amount = to_decimal(amount_str)
            if amount <= 0:
                return JsonResponse({
                    'success': False,
                    'error': 'Amount must be greater than 0'
                }, status=400)
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid amount format'
            }, status=400)

        # Get account
        account = get_single_trading_account()

        # Check if bot is running
        active_sessions = PaperTradingSession.objects.filter(
            account=account,
            status='RUNNING'
        )

        if active_sessions.exists():
            return JsonResponse({
                'success': False,
                'error': 'Bot is currently running. Please stop the bot before resetting.'
            }, status=400)

        # Use transaction to ensure all-or-nothing operation
        with transaction.atomic():
            # Step 1: Get current session
            current_session = PaperTradingSession.objects.filter(
                account=account
            ).order_by('-started_at').first()

            # Step 2: Force close all open positions
            open_positions = PaperPosition.objects.filter(
                account=account,
                is_open=True
            )

            positions_closed = 0
            total_realized_pnl = Decimal('0')

            for position in open_positions:
                # Calculate realized P&L
                realized_pnl = position.current_value_usd - position.total_invested_usd
                total_realized_pnl += realized_pnl

                # Update position to closed
                position.is_open = False
                position.closed_at = timezone.now()
                position.current_price_usd = position.current_price_usd
                position.realized_pnl_usd = realized_pnl
                position.save()

                # Create a closing trade record
                PaperTrade.objects.create(
                    account=account,
                    session=current_session,
                    trade_type='sell',
                    token_in_address=position.token_address,
                    token_in_symbol=position.token_symbol,
                    token_out_address='0x0000000000000000000000000000000000000000',
                    token_out_symbol='USD',
                    amount_in=position.quantity,
                    amount_in_usd=position.current_value_usd,
                    expected_amount_out=position.current_value_usd,
                    simulated_gas_price_gwei=Decimal('1.0'),
                    simulated_gas_used=21000,
                    simulated_gas_cost_usd=Decimal('0.50'),
                    simulated_slippage_percent=Decimal('0.50'),
                    status='completed',
                    metadata={
                        'note': f'Force closed during session reset. Realized P&L: ${realized_pnl:+.2f}'
                    }
                )

                positions_closed += 1

                logger.info(
                    f"[RESET] Force closed position {position.token_symbol}: "
                    f"P&L=${realized_pnl:+.2f}"
                )

            # Step 3: Calculate final session metrics
            if current_session:
                # Update session with final data
                current_session.status = 'COMPLETED'
                current_session.stopped_at = timezone.now()
                current_session.total_trades = PaperTrade.objects.filter(
                    session=current_session
                ).count()

                # Calculate wins/losses
                completed_trades = PaperTrade.objects.filter(
                    session=current_session,
                    status='completed'
                )

                winning_trades = 0
                losing_trades = 0

                for trade in completed_trades:
                    # Try to find associated position to get P&L
                    try:
                        position = PaperPosition.objects.filter(
                            account=account,
                            token_address=trade.token_in_address,
                            opened_at__gte=trade.created_at
                        ).first()

                        if position and position.realized_pnl_usd is not None:
                            if position.realized_pnl_usd > 0:
                                winning_trades += 1
                            elif position.realized_pnl_usd < 0:
                                losing_trades += 1
                    except Exception:
                        pass

                current_session.successful_trades = winning_trades
                current_session.failed_trades = losing_trades
                current_session.save()

                logger.info(
                    f"[RESET] Archived session {current_session.session_id}: "
                    f"{current_session.total_trades} trades, "
                    f"{winning_trades}W/{losing_trades}L"
                )

            # Step 4: Calculate old balance for logging
            old_balance = account.current_balance_usd

            # Add realized P&L to balance (from closed positions)
            account.current_balance_usd = old_balance + total_realized_pnl

            # Step 5: Reset account balance to new amount
            account.current_balance_usd = amount
            account.save()

            logger.info(
                f"[RESET] Reset account balance: "
                f"${old_balance:.2f} → ${amount:.2f}"
            )

            # Step 6: Create new session
            session_name = f"Session_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
            new_session = PaperTradingSession.objects.create(
                account=account,
                status='STOPPED',
                started_at=timezone.now(),
                metadata={
                    'session_name': session_name,
                    'starting_balance': float(amount),
                    'previous_session_id': str(current_session.session_id) if current_session else None,
                    'reset_timestamp': timezone.now().isoformat(),
                    'positions_closed': positions_closed,
                    'realized_pnl': float(total_realized_pnl)
                }
            )

            logger.info(
                f"[RESET] Created new session: {new_session.session_id}"
            )

        # Return success response
        return JsonResponse({
            'success': True,
            'message': 'Account reset successfully',
            'data': {
                'new_balance': float(amount),
                'positions_closed': positions_closed,
                'realized_pnl': float(total_realized_pnl),
                'new_session_id': str(new_session.session_id),
                'new_session_name': session_name,
                'previous_session_completed': current_session is not None
            }
        })

    except Exception as e:
        logger.error(f"[RESET] Error in reset and add funds: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Failed to reset account: {str(e)}'
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
                starting_balance = to_decimal(session.metadata['starting_balance'])

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
