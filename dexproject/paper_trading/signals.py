"""
Paper Trading Signals Module - Migration Safe Version

This module handles all Django signals for the paper trading app.
Signals are only registered during normal operation, not during migrations.

CRITICAL: This module sends WebSocket updates for real-time dashboard updates.
The portfolio metrics must match the JavaScript field names exactly:
- handlePortfolioUpdate expects: portfolio_value, return_percent, total_pnl, win_rate
- handleAccountUpdated expects: current_balance_usd, total_pnl_usd, win_rate, total_trades, successful_trades

File: dexproject/paper_trading/signals.py
"""
import sys
import logging
from typing import Any, Dict
from decimal import Decimal
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.db import transaction

# Configure logger
logger = logging.getLogger(__name__)

# ============================================================================
# MIGRATION SAFETY CHECK
# ============================================================================
# Check if we're running a migration-related command
# This prevents signals from executing during makemigrations/migrate
RUNNING_MIGRATION = any(
    cmd in sys.argv
    for cmd in ['makemigrations', 'migrate', 'showmigrations', 'sqlmigrate']
)

if RUNNING_MIGRATION:
    logger.info(
        "Migration command detected - paper trading signals will NOT be registered"
    )
else:
    logger.debug("Normal operation - paper trading signals will be registered")


# ============================================================================
# WEBSOCKET SERVICE INTEGRATION
# ============================================================================

def get_ws_service():
    """
    Safely get the centralized WebSocket service.

    Returns:
        WebSocket service instance or None if unavailable

    Note:
        This lazy import prevents circular dependencies and allows
        the service to be optional during testing/migrations.
    """
    try:
        # Use the correct import path for the paper trading WebSocket service
        from paper_trading.services.websocket_service import websocket_service
        return websocket_service
    except ImportError as e:
        logger.warning(f"[SIGNALS] WebSocket service not available (ImportError): {e}")
        return None
    except Exception as e:
        logger.error(f"[SIGNALS] Error getting WebSocket service: {e}")
        return None


# ============================================================================
# PORTFOLIO CALCULATION HELPER
# ============================================================================

def calculate_portfolio_metrics(account: Any) -> Dict[str, Any]:
    """
    Calculate complete portfolio metrics including cash and positions.

    This is the centralized function for calculating portfolio value
    to ensure consistency across all WebSocket updates.

    CRITICAL: Positions must be valued at CURRENT MARKET PRICE, not entry price!
    This must match the calculation in data_api.py and the
    JavaScript handlePortfolioUpdate function expectations.

    Args:
        account: PaperTradingAccount instance

    Returns:
        Dictionary with portfolio metrics matching JavaScript field names:
        - portfolio_value: Total value (cash + open positions)
        - cash_balance: Current cash balance
        - positions_value: Total value of open positions
        - total_pnl: Portfolio value minus initial balance
        - return_percent: Percentage return on initial investment
        - win_rate: Percentage of winning trades
        - total_trades: Total number of trades
        - successful_trades: Number of winning trades (for backward compat)
    """
    try:
        from paper_trading.models import PaperPosition
        from paper_trading.services import get_default_price_feed_service
        from asgiref.sync import async_to_sync

        logger.debug(f"[PORTFOLIO CALC] Starting calculation for account {account.account_id}")

        # Get cash balance (this is just the cash, not including positions)
        cash_balance = float(account.current_balance_usd or Decimal('0'))
        logger.debug(f"[PORTFOLIO CALC] Cash balance: ${cash_balance:.2f}")

        # CRITICAL FIX: Calculate position values using CURRENT MARKET PRICES
        # NOT the current_value_usd field which stores values at ENTRY prices!
        positions = PaperPosition.objects.filter(
            account=account,
            is_open=True
        ).select_related('account')

        positions_value = Decimal('0')
        price_service = get_default_price_feed_service()
        
        for position in positions:
            # Get CURRENT market price for accurate valuation
            try:
                # FIXED: Use correct parameter names and async_to_sync wrapper
                current_price = async_to_sync(price_service.get_token_price)(
                    token_address=position.token_address,
                    token_symbol=position.token_symbol
                )
                
                if current_price is None:
                    # Fallback to entry price if current price unavailable
                    logger.warning(
                        f"[PORTFOLIO CALC] No current price for {position.token_symbol}, "
                        f"using entry price"
                    )
                    current_price = position.average_entry_price_usd
                else:
                    logger.debug(
                        f"[PORTFOLIO CALC] {position.token_symbol}: "
                        f"Current=${current_price} vs Entry=${position.average_entry_price_usd}"
                    )
                
                # Calculate value using CURRENT price × quantity (natural units)
                position_value = position.quantity * current_price
                positions_value += position_value
                
                logger.debug(
                    f"[PORTFOLIO CALC] {position.token_symbol}: "
                    f"{position.quantity} × ${current_price} = ${position_value:.2f}"
                )
                
            except Exception as e:
                logger.warning(
                    f"[PORTFOLIO CALC] Error getting price for {position.token_symbol}: {e}, "
                    f"using fallback entry price"
                )
                # Fallback to entry price on any error
                position_value = position.quantity * position.average_entry_price_usd
                positions_value += position_value

        positions_value = float(positions_value)
        logger.debug(f"[PORTFOLIO CALC] Open positions value: ${positions_value:.2f}")

        # Calculate portfolio value (cash + positions at CURRENT MARKET prices)
        portfolio_value = cash_balance + positions_value
        logger.debug(f"[PORTFOLIO CALC] Total portfolio value: ${portfolio_value:.2f}")

        # Get initial balance for P&L and return calculation
        initial_balance = float(account.initial_balance_usd or Decimal('10000'))
        logger.debug(f"[PORTFOLIO CALC] Initial balance: ${initial_balance:.2f}")

        # CRITICAL: Calculate P&L as portfolio_value - initial_balance
        # This matches the calculation in data_api.py
        # Do NOT use account.total_profit_loss_usd as it may not be updated yet
        total_pnl = portfolio_value - initial_balance
        logger.debug(f"[PORTFOLIO CALC] Total P&L: ${total_pnl:.2f}")

        # Calculate return percentage
        return_percent = 0.0
        if initial_balance > 0:
            return_percent = (total_pnl / initial_balance) * 100
        logger.debug(f"[PORTFOLIO CALC] Return percent: {return_percent:.2f}%")

        # Calculate win rate from account statistics
        total_trades = account.total_trades or 0
        winning_trades = account.winning_trades or 0
        win_rate = 0.0
        if total_trades > 0:
            win_rate = (winning_trades / total_trades) * 100
        logger.debug(
            f"[PORTFOLIO CALC] Win rate: {win_rate:.1f}% "
            f"({winning_trades}/{total_trades} trades)"
        )

        metrics = {
            # Fields for handlePortfolioUpdate (JavaScript)
            'portfolio_value': portfolio_value,
            'cash_balance': cash_balance,
            'positions_value': positions_value,
            'total_pnl': total_pnl,
            'return_percent': return_percent,
            'win_rate': win_rate,
            'total_trades': total_trades,
            'successful_trades': winning_trades,  # For backward compatibility
            # Additional fields that may be useful
            'initial_balance': initial_balance,
            'winning_trades': winning_trades,
            'losing_trades': account.losing_trades or 0,
        }

        logger.info(
            f"[PORTFOLIO CALC] Complete - Portfolio=${portfolio_value:.2f}, "
            f"P&L=${total_pnl:.2f}, Return={return_percent:.2f}%, "
            f"WinRate={win_rate:.1f}%"
        )

        return metrics

    except Exception as e:
        logger.error(
            f"[PORTFOLIO CALC] Error calculating portfolio metrics: {e}",
            exc_info=True
        )
        # Return safe defaults on error
        cash_balance = float(account.current_balance_usd or Decimal('0'))
        return {
            'portfolio_value': cash_balance,
            'cash_balance': cash_balance,
            'positions_value': 0.0,
            'total_pnl': 0.0,
            'return_percent': 0.0,
            'win_rate': 0.0,
            'total_trades': 0,
            'successful_trades': 0,
            'initial_balance': 10000.0,
            'winning_trades': 0,
            'losing_trades': 0,
        }
# ============================================================================
# SIGNAL HANDLERS - PAPER TRADING ACCOUNT
# ============================================================================

@receiver(post_save, sender='paper_trading.PaperTradingAccount')
def paper_account_created_or_updated(
    sender: Any,
    instance: Any,
    created: bool,
    **kwargs: Any
) -> None:
    """
    Handle paper trading account creation or updates.

    Sends real-time portfolio updates via WebSocket when accounts are created or modified.
    This ensures the dashboard shows up-to-date portfolio value (cash + positions).

    CRITICAL: This triggers whenever the account is saved, which happens after
    every trade execution. This is the primary way the dashboard gets updates.

    Args:
        sender: The model class (PaperTradingAccount)
        instance: The actual instance being saved
        created: True if this is a new instance
        **kwargs: Additional signal arguments

    Note:
        Uses transaction.on_commit() to ensure WebSocket notification
        only happens after successful database commit.
    """
    if RUNNING_MIGRATION:
        return

    logger.debug(
        f"[SIGNAL] paper_account_created_or_updated triggered - "
        f"account_id={instance.account_id}, created={created}"
    )

    try:
        ws_service = get_ws_service()
        if not ws_service:
            logger.warning(
                "[SIGNAL] WebSocket service unavailable, dashboard will not update in real-time"
            )
            return

        # Send notification after successful database commit
        def send_notification():
            try:
                logger.debug(
                    f"[SIGNAL] Sending portfolio update for account {instance.account_id}"
                )

                # Calculate full portfolio metrics (cash + positions)
                portfolio_metrics = calculate_portfolio_metrics(instance)

                # =====================================================
                # SEND portfolio_update MESSAGE
                # This is handled by handlePortfolioUpdate in JavaScript
                # =====================================================
                portfolio_success = ws_service.send_portfolio_update(
                    account_id=instance.account_id,
                    portfolio_data=portfolio_metrics
                )

                if portfolio_success:
                    logger.info(
                        f"[SIGNAL] portfolio_update SENT - "
                        f"account={instance.account_id}, "
                        f"portfolio_value=${portfolio_metrics['portfolio_value']:.2f}, "
                        f"cash=${portfolio_metrics['cash_balance']:.2f}, "
                        f"positions=${portfolio_metrics['positions_value']:.2f}, "
                        f"pnl=${portfolio_metrics['total_pnl']:.2f}, "
                        f"return={portfolio_metrics['return_percent']:.2f}%"
                    )
                else:
                    logger.warning(
                        f"[SIGNAL] portfolio_update FAILED to send for account {instance.account_id}"
                    )

                # =====================================================
                # SEND account_updated MESSAGE (backward compatibility)
                # This is handled by handleAccountUpdated in JavaScript
                # =====================================================
                account_data = {
                    'account_id': str(instance.account_id),
                    # Fields expected by handleAccountUpdated
                    'current_balance_usd': portfolio_metrics['cash_balance'],
                    'total_pnl_usd': portfolio_metrics['total_pnl'],
                    'win_rate': portfolio_metrics['win_rate'],
                    'total_trades': portfolio_metrics['total_trades'],
                    'successful_trades': portfolio_metrics['successful_trades'],
                    # Additional context
                    'is_active': instance.is_active,
                    'event_type': 'created' if created else 'updated',
                }

                account_success = ws_service.send_update(
                    account_id=instance.account_id,
                    message_type='account_updated',
                    data=account_data
                )

                if account_success:
                    logger.debug(
                        f"[SIGNAL] account_updated SENT - account={instance.account_id}"
                    )
                else:
                    logger.warning(
                        f"[SIGNAL] account_updated FAILED to send for account {instance.account_id}"
                    )

            except Exception as e:
                logger.error(
                    f"[SIGNAL] Error sending account notification: {e}",
                    exc_info=True
                )

        transaction.on_commit(send_notification)

    except Exception as e:
        logger.error(
            f"[SIGNAL] Error in paper_account_created_or_updated: {e}",
            exc_info=True
        )


# ============================================================================
# SIGNAL HANDLERS - PAPER TRADE
# ============================================================================

@receiver(post_save, sender='paper_trading.PaperTrade')
def paper_trade_created_or_updated(
    sender: Any,
    instance: Any,
    created: bool,
    **kwargs: Any
) -> None:
    """
    Handle paper trade creation or updates.

    Sends real-time trade notifications and portfolio updates.
    Trades affect account balance and positions, so portfolio must be recalculated.

    Args:
        sender: The model class (PaperTrade)
        instance: The actual trade instance
        created: True if this is a new trade
        **kwargs: Additional signal arguments
    """
    if RUNNING_MIGRATION:
        return

    logger.debug(
        f"[SIGNAL] paper_trade_created_or_updated triggered - "
        f"trade_id={instance.trade_id}, created={created}, status={instance.status}"
    )

    try:
        ws_service = get_ws_service()
        if not ws_service:
            logger.warning("[SIGNAL] WebSocket service unavailable, skipping trade notification")
            return

        # Prepare trade data
        trade_data = {
            'trade_id': str(instance.trade_id),
            'account_id': str(instance.account.account_id) if instance.account else None,
            'token_in_symbol': instance.token_in_symbol,
            'token_out_symbol': instance.token_out_symbol,
            'trade_type': instance.trade_type,
            'amount_in': float(instance.amount_in),
            'amount_out': float(instance.actual_amount_out) if instance.actual_amount_out else None,
            'amount_in_usd': float(instance.amount_in_usd),
            'status': instance.status,
            'executed_at': instance.executed_at.isoformat() if instance.executed_at else None,
            'event_type': 'created' if created else 'updated',
        }

        # Send notification after database commit
        def send_notification():
            try:
                # Send trade update
                trade_success = ws_service.send_trade_update(
                    account_id=instance.account.account_id,
                    trade_data=trade_data
                )

                if trade_success:
                    logger.info(
                        f"[SIGNAL] trade_update SENT - "
                        f"trade_id={instance.trade_id}, "
                        f"type={instance.trade_type}, "
                        f"amount=${float(instance.amount_in_usd):.2f}, "
                        f"status={instance.status}"
                    )
                else:
                    logger.warning(
                        f"[SIGNAL] trade_update FAILED for trade {instance.trade_id}"
                    )

                # CRITICAL: Send portfolio update for completed/executed trades
                # since they affect account balance and positions
                if instance.status in ['completed', 'executed', 'success', 'COMPLETED', 'EXECUTED', 'SUCCESS']:
                    logger.debug(
                        f"[SIGNAL] Trade {instance.trade_id} is completed, sending portfolio update"
                    )
                    portfolio_metrics = calculate_portfolio_metrics(instance.account)
                    portfolio_success = ws_service.send_portfolio_update(
                        account_id=instance.account.account_id,
                        portfolio_data=portfolio_metrics
                    )

                    if portfolio_success:
                        logger.info(
                            f"[SIGNAL] portfolio_update SENT after trade - "
                            f"portfolio=${portfolio_metrics['portfolio_value']:.2f}, "
                            f"pnl=${portfolio_metrics['total_pnl']:.2f}"
                        )
                    else:
                        logger.warning(
                            f"[SIGNAL] portfolio_update FAILED after trade {instance.trade_id}"
                        )
                else:
                    logger.debug(
                        f"[SIGNAL] Trade {instance.trade_id} status={instance.status}, "
                        f"skipping portfolio update (only for completed trades)"
                    )

            except Exception as e:
                logger.error(
                    f"[SIGNAL] Error sending trade notification: {e}",
                    exc_info=True
                )

        transaction.on_commit(send_notification)

    except Exception as e:
        logger.error(
            f"[SIGNAL] Error in paper_trade_created_or_updated: {e}",
            exc_info=True
        )


@receiver(pre_save, sender='paper_trading.PaperTrade')
def paper_trade_pre_save(
    sender: Any,
    instance: Any,
    **kwargs: Any
) -> None:
    """
    Pre-save handler for paper trades.

    Performs any calculations or validations before saving the trade.

    Args:
        sender: The model class (PaperTrade)
        instance: The trade instance about to be saved
        **kwargs: Additional signal arguments
    """
    if RUNNING_MIGRATION:
        return

    try:
        # Any pre-save logic can go here
        pass
    except Exception as e:
        logger.error(f"[SIGNAL] Error in paper_trade_pre_save: {e}")


# ============================================================================
# SIGNAL HANDLERS - PAPER POSITION
# ============================================================================

@receiver(post_save, sender='paper_trading.PaperPosition')
def paper_position_created_or_updated(
    sender: Any,
    instance: Any,
    created: bool,
    **kwargs: Any
) -> None:
    """
    Handle paper position creation or updates.

    Sends real-time position updates AND portfolio updates when positions change.
    This is crucial because position changes affect total portfolio value.

    Args:
        sender: The model class (PaperPosition)
        instance: The position instance
        created: True if this is a new position
        **kwargs: Additional signal arguments
    """
    if RUNNING_MIGRATION:
        return

    logger.debug(
        f"[SIGNAL] paper_position_created_or_updated triggered - "
        f"position_id={instance.position_id}, token={instance.token_symbol}, "
        f"created={created}, is_open={instance.is_open}"
    )

    try:
        ws_service = get_ws_service()
        if not ws_service:
            logger.warning("[SIGNAL] WebSocket service unavailable, skipping position notification")
            return

        # Prepare position data
        position_data = {
            'position_id': str(instance.position_id),
            'account_id': str(instance.account.account_id) if instance.account else None,
            'token_symbol': instance.token_symbol,
            'token_address': instance.token_address,
            'quantity': float(instance.quantity),
            'average_entry_price_usd': float(instance.average_entry_price_usd),
            'current_value_usd': float(instance.current_value_usd) if instance.current_value_usd else None,
            'unrealized_pnl_usd': float(instance.unrealized_pnl_usd),
            'is_open': instance.is_open,
            'opened_at': instance.opened_at.isoformat() if instance.opened_at else None,
            'closed_at': instance.closed_at.isoformat() if instance.closed_at else None,
            'event_type': 'created' if created else 'updated',
        }

        # Send notification after database commit
        def send_notification():
            try:
                # Send position update
                position_success = ws_service.send_position_update(
                    account_id=instance.account.account_id,
                    position_data=position_data
                )

                if position_success:
                    logger.info(
                        f"[SIGNAL] position_updated SENT - "
                        f"token={instance.token_symbol}, "
                        f"qty={float(instance.quantity):.4f}, "
                        f"value=${float(instance.current_value_usd or 0):.2f}, "
                        f"is_open={instance.is_open}"
                    )
                else:
                    logger.warning(
                        f"[SIGNAL] position_updated FAILED for position {instance.position_id}"
                    )

                # CRITICAL: Also send portfolio update since position value affects total portfolio
                portfolio_metrics = calculate_portfolio_metrics(instance.account)
                portfolio_success = ws_service.send_portfolio_update(
                    account_id=instance.account.account_id,
                    portfolio_data=portfolio_metrics
                )

                if portfolio_success:
                    logger.info(
                        f"[SIGNAL] portfolio_update SENT after position change - "
                        f"portfolio=${portfolio_metrics['portfolio_value']:.2f}, "
                        f"pnl=${portfolio_metrics['total_pnl']:.2f}"
                    )
                else:
                    logger.warning(
                        f"[SIGNAL] portfolio_update FAILED after position {instance.position_id}"
                    )

            except Exception as e:
                logger.error(
                    f"[SIGNAL] Error sending position notification: {e}",
                    exc_info=True
                )

        transaction.on_commit(send_notification)

    except Exception as e:
        logger.error(
            f"[SIGNAL] Error in paper_position_created_or_updated: {e}",
            exc_info=True
        )


@receiver(post_delete, sender='paper_trading.PaperPosition')
def paper_position_deleted(
    sender: Any,
    instance: Any,
    **kwargs: Any
) -> None:
    """
    Handle paper position deletion.

    Notifies users when positions are closed/deleted.
    Also triggers portfolio update since deleting a position changes portfolio value.

    Args:
        sender: The model class (PaperPosition)
        instance: The deleted position instance
        **kwargs: Additional signal arguments
    """
    if RUNNING_MIGRATION:
        return

    logger.debug(
        f"[SIGNAL] paper_position_deleted triggered - "
        f"position_id={instance.position_id}, token={instance.token_symbol}"
    )

    try:
        ws_service = get_ws_service()
        if not ws_service:
            logger.warning("[SIGNAL] WebSocket service unavailable, skipping deletion notification")
            return

        # Prepare deletion data
        deletion_data = {
            'position_id': str(instance.position_id),
            'account_id': str(instance.account.account_id) if instance.account else None,
            'token_symbol': instance.token_symbol,
            'token_address': instance.token_address,
            'final_quantity': float(instance.quantity),
            'closed_at': instance.closed_at.isoformat() if instance.closed_at else None,
            'event_type': 'deleted',
        }

        # Send position deletion notification
        position_success = ws_service.send_position_update(
            account_id=instance.account.account_id,
            position_data=deletion_data
        )

        if position_success:
            logger.info(
                f"[SIGNAL] position_deleted SENT - "
                f"token={instance.token_symbol}, "
                f"position_id={instance.position_id}"
            )
        else:
            logger.warning(
                f"[SIGNAL] position_deleted FAILED for position {instance.position_id}"
            )

        # CRITICAL: Also send portfolio update since position was removed
        portfolio_metrics = calculate_portfolio_metrics(instance.account)
        portfolio_success = ws_service.send_portfolio_update(
            account_id=instance.account.account_id,
            portfolio_data=portfolio_metrics
        )

        if portfolio_success:
            logger.info(
                f"[SIGNAL] portfolio_update SENT after position deletion - "
                f"portfolio=${portfolio_metrics['portfolio_value']:.2f}"
            )
        else:
            logger.warning(
                f"[SIGNAL] portfolio_update FAILED after position deletion"
            )

    except Exception as e:
        logger.error(
            f"[SIGNAL] Error in paper_position_deleted: {e}",
            exc_info=True
        )


# ============================================================================
# SIGNAL HANDLERS - AI THOUGHT LOG
# ============================================================================

@receiver(post_save, sender='paper_trading.PaperAIThoughtLog')
def paper_ai_thought_created(
    sender: Any,
    instance: Any,
    created: bool,
    **kwargs: Any
) -> None:
    """
    Handle AI thought log creation.

    Broadcasts AI decision-making process to interested users.

    Args:
        sender: The model class (PaperAIThoughtLog)
        instance: The thought log instance
        created: True if this is a new log entry
        **kwargs: Additional signal arguments
    """
    if RUNNING_MIGRATION:
        return

    # Only send notifications for new thoughts
    if not created:
        return

    logger.debug(
        f"[SIGNAL] paper_ai_thought_created triggered - "
        f"thought_id={instance.thought_id}, decision={instance.decision_type}"
    )

    try:
        ws_service = get_ws_service()
        if not ws_service:
            logger.debug("[SIGNAL] WebSocket service unavailable, skipping thought notification")
            return

        # Prepare thought data in format expected by WebSocket service
        thought_data = {
            'thought_id': str(instance.thought_id),
            'account_id': str(instance.account.account_id) if instance.account else None,
            'trade_id': str(instance.paper_trade.trade_id) if instance.paper_trade else None,
            'decision_type': instance.decision_type,
            'token_symbol': instance.token_symbol,
            'token_address': instance.token_address,
            # Confidence fields
            'confidence_percent': float(instance.confidence_percent) if instance.confidence_percent else None,
            'confidence_level': instance.confidence_level,
            # Risk and opportunity scores
            'risk_score': float(instance.risk_score) if instance.risk_score else None,
            'opportunity_score': float(instance.opportunity_score) if instance.opportunity_score else None,
            # Reasoning field
            'primary_reasoning': instance.primary_reasoning,
            # Strategy and context
            'strategy_name': instance.strategy_name,
            'lane_used': instance.lane_used,
            # Signal lists
            'key_factors': instance.key_factors,
            'positive_signals': instance.positive_signals,
            'negative_signals': instance.negative_signals,
            # Market data
            'market_data': instance.market_data,
            # Timestamp
            'created_at': instance.created_at.isoformat() if instance.created_at else None,
        }

        # Send notification after database commit
        def send_notification():
            try:
                # Use thought-specific WebSocket method
                thought_success = ws_service.send_thought_log(
                    account_id=instance.account.account_id,
                    thought_data=thought_data
                )

                if thought_success:
                    logger.debug(
                        f"[SIGNAL] thought_log_created SENT - "
                        f"decision={instance.decision_type}, "
                        f"token={instance.token_symbol}, "
                        f"confidence={instance.confidence_percent}%"
                    )
                else:
                    logger.warning(
                        f"[SIGNAL] thought_log_created FAILED for thought {instance.thought_id}"
                    )

            except Exception as e:
                logger.error(
                    f"[SIGNAL] Error sending AI thought notification: {e}",
                    exc_info=True
                )

        transaction.on_commit(send_notification)

    except Exception as e:
        logger.error(
            f"[SIGNAL] Error in paper_ai_thought_created: {e}",
            exc_info=True
        )


# ============================================================================
# SIGNAL HANDLERS - PERFORMANCE METRICS
# ============================================================================

@receiver(post_save, sender='paper_trading.PaperPerformanceMetrics')
def paper_performance_updated(
    sender: Any,
    instance: Any,
    created: bool,
    **kwargs: Any
) -> None:
    """
    Handle performance metrics updates.

    Broadcasts updated metrics to users for real-time dashboard updates.

    Args:
        sender: The model class (PaperPerformanceMetrics)
        instance: The metrics instance
        created: True if this is a new metrics record
        **kwargs: Additional signal arguments
    """
    if RUNNING_MIGRATION:
        return

    logger.debug(
        f"[SIGNAL] paper_performance_updated triggered - "
        f"metric_id={instance.metric_id}, created={created}"
    )

    try:
        ws_service = get_ws_service()
        if not ws_service:
            logger.debug("[SIGNAL] WebSocket service unavailable, skipping performance notification")
            return

        # Prepare metrics data
        metrics_data = {
            'metric_id': str(instance.metric_id),
            'session_id': str(instance.session.session_id) if instance.session else None,
            'account_id': str(instance.session.account.account_id) if instance.session and instance.session.account else None,
            'total_trades': instance.total_trades,
            'winning_trades': instance.winning_trades,
            'losing_trades': instance.losing_trades,
            'win_rate': float(instance.win_rate) if instance.win_rate else 0.0,
            'total_pnl_usd': float(instance.total_pnl_usd) if instance.total_pnl_usd else 0.0,
            'total_pnl_percent': float(instance.total_pnl_percent) if instance.total_pnl_percent else 0.0,
            'sharpe_ratio': float(instance.sharpe_ratio) if instance.sharpe_ratio else None,
            'max_drawdown_percent': float(instance.max_drawdown_percent) if instance.max_drawdown_percent else 0.0,
            'period_start': instance.period_start.isoformat() if instance.period_start else None,
            'period_end': instance.period_end.isoformat() if instance.period_end else None,
            'event_type': 'created' if created else 'updated',
        }

        # Send notification after database commit
        def send_notification():
            try:
                # Use performance-specific WebSocket method
                if instance.session and instance.session.account:
                    performance_success = ws_service.send_performance_update(
                        account_id=instance.session.account.account_id,
                        performance_data=metrics_data
                    )

                    if performance_success:
                        logger.info(
                            f"[SIGNAL] performance_update SENT - "
                            f"session={instance.session.session_id if instance.session else 'N/A'}, "
                            f"win_rate={instance.win_rate}%, "
                            f"pnl=${instance.total_pnl_usd}"
                        )
                    else:
                        logger.warning(
                            f"[SIGNAL] performance_update FAILED for metric {instance.metric_id}"
                        )

            except Exception as e:
                logger.error(
                    f"[SIGNAL] Error sending performance notification: {e}",
                    exc_info=True
                )

        transaction.on_commit(send_notification)

    except Exception as e:
        logger.error(
            f"[SIGNAL] Error in paper_performance_updated: {e}",
            exc_info=True
        )


# ============================================================================
# SIGNAL REGISTRATION CONFIRMATION
# ============================================================================

if not RUNNING_MIGRATION:
    logger.info(
        "[SIGNALS] Paper trading signals registered successfully - "
        "using centralized WebSocket service for real-time dashboard updates"
    )
else:
    logger.info(
        "[SIGNALS] Paper trading signals SKIPPED - "
        "running migration command"
    )