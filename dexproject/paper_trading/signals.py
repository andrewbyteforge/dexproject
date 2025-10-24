"""
Paper Trading Signals Module - Migration Safe Version

This module handles all Django signals for the paper trading app.
Signals are only registered during normal operation, not during migrations.

File: dexproject/paper_trading/signals.py
"""
import sys
import logging
from typing import Any, Optional
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
        from ws.services.centralized_service import centralized_ws_service
        return centralized_ws_service
    except ImportError as e:
        logger.warning(f"WebSocket service not available: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting WebSocket service: {e}")
        return None


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
    
    Sends real-time updates via WebSocket when accounts are created or modified.
    
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
            
        # Prepare account data
        account_data = {
            'id': str(instance.id),
            'user_id': instance.user.id if instance.user else None,
            'username': instance.user.username if instance.user else None,
            'balance': str(instance.balance),
            'equity': str(instance.equity),
            'is_active': instance.is_active,
            'created_at': instance.created_at.isoformat() if instance.created_at else None,
            'updated_at': instance.updated_at.isoformat() if instance.updated_at else None,
        }
        
        # Send notification after successful database commit
        def send_notification():
            try:
                event_type = 'paper_account_created' if created else 'paper_account_updated'
                ws_service.broadcast_to_user(
                    user_id=instance.user.id if instance.user else None,
                    message_type=event_type,
                    data=account_data
                )
                logger.info(
                    f"Paper account {event_type}: account_id={instance.id}, "
                    f"balance={instance.balance}"
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
    
    Sends real-time trade notifications and updates account metrics.
    
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
            'id': str(instance.id),
            'account_id': str(instance.account.id) if instance.account else None,
            'token_address': instance.token_address,
            'trade_type': instance.trade_type,
            'amount': str(instance.amount),
            'price': str(instance.price),
            'total_value': str(instance.total_value),
            'status': instance.status,
            'executed_at': instance.executed_at.isoformat() if instance.executed_at else None,
            'created_at': instance.created_at.isoformat() if instance.created_at else None,
        }
        
        # Send notification after database commit
        def send_notification():
            try:
                event_type = 'paper_trade_created' if created else 'paper_trade_updated'
                
                # Send to user who owns the account
                if instance.account and instance.account.user:
                    ws_service.broadcast_to_user(
                        user_id=instance.account.user.id,
                        message_type=event_type,
                        data=trade_data
                    )
                    
                logger.info(
                    f"Paper trade {event_type}: trade_id={instance.id}, "
                    f"type={instance.trade_type}, amount={instance.amount}"
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
    
    Calculates total_value before saving the trade.
    
    Args:
        sender: The model class (PaperTrade)
        instance: The trade instance about to be saved
        **kwargs: Additional signal arguments
    """
    if RUNNING_MIGRATION:
        return
        
    try:
        # Calculate total value if not already set
        if instance.amount and instance.price:
            instance.total_value = instance.amount * instance.price
            logger.debug(
                f"Calculated trade total_value: {instance.total_value} "
                f"(amount={instance.amount} * price={instance.price})"
            )
            
    except Exception as e:
        logger.error(f"Error in paper_trade_pre_save signal: {e}")


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
    
    Sends real-time position updates via WebSocket.
    
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
            'id': str(instance.id),
            'account_id': str(instance.account.id) if instance.account else None,
            'token_address': instance.token_address,
            'amount': str(instance.amount),
            'average_price': str(instance.average_price),
            'current_price': str(instance.current_price) if instance.current_price else None,
            'unrealized_pnl': str(instance.unrealized_pnl) if instance.unrealized_pnl else None,
            'is_open': instance.is_open,
            'opened_at': instance.opened_at.isoformat() if instance.opened_at else None,
            'updated_at': instance.updated_at.isoformat() if instance.updated_at else None,
        }
        
        # Send notification after database commit
        def send_notification():
            try:
                event_type = 'paper_position_created' if created else 'paper_position_updated'
                
                # Send to user who owns the account
                if instance.account and instance.account.user:
                    ws_service.broadcast_to_user(
                        user_id=instance.account.user.id,
                        message_type=event_type,
                        data=position_data
                    )
                    
                logger.info(
                    f"Paper position {event_type}: position_id={instance.id}, "
                    f"token={instance.token_address}, amount={instance.amount}"
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
            'id': str(instance.id),
            'account_id': str(instance.account.id) if instance.account else None,
            'token_address': instance.token_address,
            'final_amount': str(instance.amount),
            'deleted_at': instance.updated_at.isoformat() if instance.updated_at else None,
        }
        
        # Send to user who owns the account
        if instance.account and instance.account.user:
            ws_service.broadcast_to_user(
                user_id=instance.account.user.id,
                message_type='paper_position_deleted',
                data=deletion_data
            )
            
        logger.info(
            f"Paper position deleted: position_id={instance.id}, "
            f"token={instance.token_address}"
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
            
        # Prepare thought data
        thought_data = {
            'id': str(instance.id),
            'trade_id': str(instance.trade.id) if instance.trade else None,
            'thought_type': instance.thought_type,
            'decision': instance.decision,
            'confidence': float(instance.confidence) if instance.confidence else None,
            'reasoning': instance.reasoning,
            'created_at': instance.created_at.isoformat() if instance.created_at else None,
        }
        
        # Send notification after database commit
        def send_notification():
            try:
                # Get user from trade's account
                if instance.trade and instance.trade.account and instance.trade.account.user:
                    ws_service.broadcast_to_user(
                        user_id=instance.trade.account.user.id,
                        message_type='paper_ai_thought_created',
                        data=thought_data
                    )
                    
                logger.debug(
                    f"AI thought logged: type={instance.thought_type}, "
                    f"decision={instance.decision}, confidence={instance.confidence}"
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
            'id': str(instance.id),
            'account_id': str(instance.account.id) if instance.account else None,
            'total_trades': instance.total_trades,
            'winning_trades': instance.winning_trades,
            'losing_trades': instance.losing_trades,
            'win_rate': float(instance.win_rate) if instance.win_rate else None,
            'total_profit_loss': str(instance.total_profit_loss),
            'sharpe_ratio': float(instance.sharpe_ratio) if instance.sharpe_ratio else None,
            'max_drawdown': float(instance.max_drawdown) if instance.max_drawdown else None,
            'updated_at': instance.updated_at.isoformat() if instance.updated_at else None,
        }
        
        # Send notification after database commit
        def send_notification():
            try:
                event_type = 'paper_performance_created' if created else 'paper_performance_updated'
                
                # Send to user who owns the account
                if instance.account and instance.account.user:
                    ws_service.broadcast_to_user(
                        user_id=instance.account.user.id,
                        message_type=event_type,
                        data=metrics_data
                    )
                    
                logger.info(
                    f"Performance metrics {event_type}: account_id={instance.account.id}, "
                    f"win_rate={instance.win_rate}, total_pnl={instance.total_profit_loss}"
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