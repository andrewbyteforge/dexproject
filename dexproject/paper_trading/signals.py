"""
Paper Trading Signals Module - Migration Safe Version

This module handles all Django signals for the paper trading app.
Signals are only registered during normal operation, not during migrations.

File: dexproject/paper_trading/signals.py
"""
import sys
import logging
from typing import Any
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
        logger.warning(f"WebSocket service not available: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting WebSocket service: {e}")
        return None


# ============================================================================
# PORTFOLIO CALCULATION HELPER
# ============================================================================

def calculate_portfolio_metrics(account):
    """
    Calculate complete portfolio metrics including cash and positions.

    This is the centralized function for calculating portfolio value
    to ensure consistency across all WebSocket updates.

    Args:
        account: PaperTradingAccount instance

    Returns:
        Dictionary with portfolio metrics
    """
    try:
        from paper_trading.models import PaperPosition
        from decimal import Decimal

        # Get cash balance
        cash_balance = float(account.current_balance_usd or 0)

        # Calculate total value of open positions
        open_positions = PaperPosition.objects.filter(
            account=account,
            is_open=True
        )

        positions_value = sum(
            float(pos.current_value_usd or 0)
            for pos in open_positions
        )

        # Calculate portfolio value (cash + positions)
        portfolio_value = cash_balance + positions_value

        # Get P&L and return percentage
        total_pnl = float(account.total_profit_loss_usd or 0)
        initial_balance = float(account.initial_balance_usd or 10000)
        return_percent = ((portfolio_value - initial_balance) / initial_balance * 100) if initial_balance > 0 else 0.0

        # Calculate win rate
        total_trades = account.total_trades or 0
        winning_trades = account.winning_trades or 0
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        return {
            'portfolio_value': portfolio_value,
            'cash_balance': cash_balance,
            'positions_value': positions_value,
            'total_pnl': total_pnl,
            'return_percent': return_percent,
            'win_rate': win_rate,
            'total_trades': total_trades,
            'successful_trades': winning_trades,
        }

    except Exception as e:
        logger.error(f"Error calculating portfolio metrics: {e}", exc_info=True)
        return {
            'portfolio_value': float(account.current_balance_usd or 0),
            'cash_balance': float(account.current_balance_usd or 0),
            'positions_value': 0.0,
            'total_pnl': 0.0,
            'return_percent': 0.0,
            'win_rate': 0.0,
            'total_trades': 0,
            'successful_trades': 0,
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

    try:
        ws_service = get_ws_service()
        if not ws_service:
            logger.debug("WebSocket service unavailable, skipping notification")
            return

        # Send notification after successful database commit
        def send_notification():
            try:
                # Calculate full portfolio metrics (cash + positions)
                portfolio_metrics = calculate_portfolio_metrics(instance)

                # Send portfolio_update (primary update for dashboard)
                ws_service.send_portfolio_update(
                    account_id=instance.account_id,
                    portfolio_data=portfolio_metrics
                )

                # Also send account_updated for backward compatibility
                account_data = {
                    'account_id': str(instance.account_id),
                    'current_balance_usd': portfolio_metrics['cash_balance'],
                    'total_pnl_usd': portfolio_metrics['total_pnl'],
                    'win_rate': portfolio_metrics['win_rate'],
                    'total_trades': portfolio_metrics['total_trades'],
                    'successful_trades': portfolio_metrics['successful_trades'],
                    'is_active': instance.is_active,
                    'event_type': 'created' if created else 'updated',
                }

                ws_service.send_update(
                    account_id=instance.account_id,
                    message_type='account_updated',
                    data=account_data
                )

                logger.info(
                    f"Paper account {'created' if created else 'updated'}: "
                    f"account_id={instance.account_id}, "
                    f"portfolio_value=${portfolio_metrics['portfolio_value']:.2f}, "
                    f"cash=${portfolio_metrics['cash_balance']:.2f}, "
                    f"positions=${portfolio_metrics['positions_value']:.2f}"
                )
            except Exception as e:
                logger.error(f"Error sending account notification: {e}")

        transaction.on_commit(send_notification)

    except Exception as e:
        logger.error(f"Error in paper_account_created_or_updated signal: {e}")


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

    try:
        ws_service = get_ws_service()
        if not ws_service:
            logger.debug("WebSocket service unavailable, skipping notification")
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
                ws_service.send_trade_update(
                    account_id=instance.account.account_id,
                    trade_data=trade_data
                )

                # IMPORTANT: Send portfolio update for completed/executed trades
                # since they affect account balance and positions
                if instance.status in ['completed', 'executed', 'success']:
                    portfolio_metrics = calculate_portfolio_metrics(instance.account)
                    ws_service.send_portfolio_update(
                        account_id=instance.account.account_id,
                        portfolio_data=portfolio_metrics
                    )

                logger.info(
                    f"Paper trade {'created' if created else 'updated'}: "
                    f"trade_id={instance.trade_id}, type={instance.trade_type}, "
                    f"amount=${float(instance.amount_in_usd):.2f}, status={instance.status}"
                )

            except Exception as e:
                logger.error(f"Error sending trade notification: {e}")

        transaction.on_commit(send_notification)

    except Exception as e:
        logger.error(f"Error in paper_trade_created_or_updated signal: {e}")


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
        logger.error(f"Error in paper_trade_pre_save: {e}")


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

    try:
        ws_service = get_ws_service()
        if not ws_service:
            logger.debug("WebSocket service unavailable, skipping notification")
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
                ws_service.send_position_update(
                    account_id=instance.account.account_id,
                    position_data=position_data
                )

                # CRITICAL: Also send portfolio update since position value affects total portfolio
                portfolio_metrics = calculate_portfolio_metrics(instance.account)
                ws_service.send_portfolio_update(
                    account_id=instance.account.account_id,
                    portfolio_data=portfolio_metrics
                )

                logger.info(
                    f"Paper position {'created' if created else 'updated'}: "
                    f"position_id={instance.position_id}, token={instance.token_symbol}, "
                    f"qty={float(instance.quantity):.4f}, "
                    f"value=${float(instance.current_value_usd or 0):.2f}"
                )

            except Exception as e:
                logger.error(f"Error sending position notification: {e}")

        transaction.on_commit(send_notification)

    except Exception as e:
        logger.error(f"Error in paper_position_created_or_updated signal: {e}")


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

    try:
        ws_service = get_ws_service()
        if not ws_service:
            logger.debug("WebSocket service unavailable, skipping notification")
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
        ws_service.send_position_update(
            account_id=instance.account.account_id,
            position_data=deletion_data
        )

        # CRITICAL: Also send portfolio update since position was removed
        portfolio_metrics = calculate_portfolio_metrics(instance.account)
        ws_service.send_portfolio_update(
            account_id=instance.account.account_id,
            portfolio_data=portfolio_metrics
        )

        logger.info(
            f"Paper position deleted: position_id={instance.position_id}, "
            f"token={instance.token_symbol}"
        )

    except Exception as e:
        logger.error(f"Error in paper_position_deleted signal: {e}")


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
        
    try:
        ws_service = get_ws_service()
        if not ws_service:
            logger.debug("WebSocket service unavailable, skipping notification")
            return
            
        # Prepare thought data in format expected by WebSocket service
        thought_data = {
            'thought_id': str(instance.thought_id),
            'account_id': str(instance.account.account_id) if instance.account else None,
            'trade_id': str(instance.paper_trade.trade_id) if instance.paper_trade else None,
            'decision_type': instance.decision_type,
            'token_symbol': instance.token_symbol,
            'token_address': instance.token_address,
            # Confidence fields (fixed: use confidence_percent for float, confidence_level for string)
            'confidence_percent': float(instance.confidence_percent) if instance.confidence_percent else None,
            'confidence_level': instance.confidence_level,  # String: 'VERY_HIGH', 'HIGH', 'MEDIUM', 'LOW', 'VERY_LOW'
            # Risk and opportunity scores
            'risk_score': float(instance.risk_score) if instance.risk_score else None,
            'opportunity_score': float(instance.opportunity_score) if instance.opportunity_score else None,
            # Reasoning field (fixed: use primary_reasoning not reasoning)
            'primary_reasoning': instance.primary_reasoning,
            # Strategy and context
            'strategy_name': instance.strategy_name,
            'lane_used': instance.lane_used,
            # Signal lists
            'key_factors': instance.key_factors,
            'positive_signals': instance.positive_signals,
            'negative_signals': instance.negative_signals,
            # Market data (includes additional context)
            'market_data': instance.market_data,
            # Timestamp
            'created_at': instance.created_at.isoformat() if instance.created_at else None,
        }
        
        # Send notification after database commit
        def send_notification():
            try:
                # Use thought-specific WebSocket method
                ws_service.send_thought_log(
                    account_id=instance.account.account_id,
                    thought_data=thought_data
                )
                    
                logger.debug(
                    f"AI thought logged: decision={instance.decision_type}, "
                    f"token={instance.token_symbol}, "
                    f"confidence={instance.confidence_percent}% ({instance.confidence_level})"
                )
                
            except Exception as e:
                logger.error(f"Error sending AI thought notification: {e}")
        
        transaction.on_commit(send_notification)
        
    except Exception as e:
        logger.error(f"Error in paper_ai_thought_created signal: {e}")


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
        
    try:
        ws_service = get_ws_service()
        if not ws_service:
            logger.debug("WebSocket service unavailable, skipping notification")
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
                    ws_service.send_performance_update(
                        account_id=instance.session.account.account_id,
                        performance_data=metrics_data
                    )
                    
                    logger.info(
                        f"Performance metrics {'created' if created else 'updated'}: "
                        f"session={instance.session.session_id if instance.session else 'N/A'}, "
                        f"win_rate={instance.win_rate}%, pnl=${instance.total_pnl_usd}"
                    )
                
            except Exception as e:
                logger.error(f"Error sending performance notification: {e}")
        
        transaction.on_commit(send_notification)
        
    except Exception as e:
        logger.error(f"Error in paper_performance_updated signal: {e}")


# ============================================================================
# SIGNAL REGISTRATION CONFIRMATION
# ============================================================================

if not RUNNING_MIGRATION:
    logger.info(
        "Paper trading signals registered successfully - "
        "using centralized WebSocket service"
    )
else:
    logger.info(
        "Paper trading signals SKIPPED - "
        "running migration command"
    )
