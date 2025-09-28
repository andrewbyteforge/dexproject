"""
Paper Trading Django Signals

Automatically broadcast updates to connected WebSocket clients when
database models change. This enables real-time dashboard updates.

File: dexproject/paper_trading/signals.py
"""

import logging
from typing import Dict, Any
from decimal import Decimal

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingSession,
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    PaperPerformanceMetrics
)

logger = logging.getLogger(__name__)


def get_room_group_name(account_id: str) -> str:
    """
    Generate room group name for a paper trading account.
    
    Args:
        account_id: Account UUID string
        
    Returns:
        Room group name for channel layer
    """
    return f"paper_trading_{account_id}"


def broadcast_to_account(account_id: str, message_type: str, data: Dict[str, Any]) -> None:
    """
    Broadcast a message to all WebSocket connections for an account.
    
    Args:
        account_id: Account UUID string
        message_type: Type of message (e.g., 'trade_executed')
        data: Message payload
    """
    try:
        channel_layer = get_channel_layer()
        
        if channel_layer is None:
            logger.warning("Channel layer not available for broadcasting")
            return
        
        room_group_name = get_room_group_name(account_id)
        
        # Send message to room group
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': message_type,
                'data': data
            }
        )
        
        logger.debug(f"Broadcast {message_type} to {room_group_name}")
        
    except Exception as e:
        logger.error(f"Error broadcasting to account {account_id}: {e}", exc_info=True)


# =============================================================================
# PAPER TRADE SIGNALS
# =============================================================================

@receiver(post_save, sender=PaperTrade)
def paper_trade_saved(sender, instance: PaperTrade, created: bool, **kwargs) -> None:
    """
    Signal handler for PaperTrade model save events.
    
    Broadcasts trade execution events to connected clients.
    
    Args:
        sender: The model class
        instance: The saved PaperTrade instance
        created: Whether this is a new instance
        **kwargs: Additional keyword arguments
    """
    try:
        # Only broadcast for completed or failed trades
        if instance.status not in ['completed', 'failed']:
            return
        
        account_id = str(instance.account.account_id)
        
        # Prepare trade data for broadcast
        trade_data = {
            'trade_id': str(instance.trade_id),
            'trade_type': instance.trade_type,
            'token_in_symbol': instance.token_in_symbol,
            'token_in_address': instance.token_in_address,
            'token_out_symbol': instance.token_out_symbol,
            'token_out_address': instance.token_out_address,
            'amount_in_usd': float(instance.amount_in_usd),
            'expected_amount_out': float(instance.expected_amount_out),
            'actual_amount_out': (
                float(instance.actual_amount_out) 
                if instance.actual_amount_out else None
            ),
            'status': instance.status,
            'simulated_gas_cost_usd': float(instance.simulated_gas_cost_usd),
            'simulated_slippage_percent': float(instance.simulated_slippage_percent),
            'execution_time_ms': instance.execution_time_ms,
            'created_at': instance.created_at.isoformat(),
            'executed_at': (
                instance.executed_at.isoformat() 
                if instance.executed_at else None
            ),
            'mock_tx_hash': instance.mock_tx_hash,
            'strategy_name': instance.strategy_name,
            'error_message': instance.error_message if instance.status == 'failed' else None,
        }
        
        # Broadcast to connected clients
        broadcast_to_account(
            account_id=account_id,
            message_type='trade_executed',
            data=trade_data
        )
        
        logger.info(
            f"Broadcast trade execution: trade_id={instance.trade_id}, "
            f"type={instance.trade_type}, status={instance.status}"
        )
        
    except Exception as e:
        logger.error(f"Error in paper_trade_saved signal: {e}", exc_info=True)


# =============================================================================
# PAPER POSITION SIGNALS
# =============================================================================

@receiver(post_save, sender=PaperPosition)
def paper_position_saved(sender, instance: PaperPosition, created: bool, **kwargs) -> None:
    """
    Signal handler for PaperPosition model save events.
    
    Broadcasts position updates and closures to connected clients.
    
    Args:
        sender: The model class
        instance: The saved PaperPosition instance
        created: Whether this is a new instance
        **kwargs: Additional keyword arguments
    """
    try:
        account_id = str(instance.account.account_id)
        
        # Prepare position data
        position_data = {
            'position_id': str(instance.position_id),
            'token_symbol': instance.token_symbol,
            'token_address': instance.token_address,
            'quantity': float(instance.quantity),
            'average_entry_price_usd': float(instance.average_entry_price_usd),
            'current_price_usd': (
                float(instance.current_price_usd) 
                if instance.current_price_usd else None
            ),
            'total_invested_usd': float(instance.total_invested_usd),
            'current_value_usd': (
                float(instance.current_value_usd) 
                if instance.current_value_usd else None
            ),
            'unrealized_pnl_usd': float(instance.unrealized_pnl_usd),
            'realized_pnl_usd': float(instance.realized_pnl_usd),
            'is_open': instance.is_open,
            'stop_loss_price': (
                float(instance.stop_loss_price) 
                if instance.stop_loss_price else None
            ),
            'take_profit_price': (
                float(instance.take_profit_price) 
                if instance.take_profit_price else None
            ),
            'created_at': instance.created_at.isoformat(),
            'closed_at': (
                instance.closed_at.isoformat() 
                if instance.closed_at else None
            ),
        }
        
        # Determine message type based on position state
        if not instance.is_open and instance.closed_at:
            message_type = 'position_closed'
            logger.info(f"Broadcast position closure: position_id={instance.position_id}")
        else:
            message_type = 'position_updated'
            logger.debug(f"Broadcast position update: position_id={instance.position_id}")
        
        # Broadcast to connected clients
        broadcast_to_account(
            account_id=account_id,
            message_type=message_type,
            data=position_data
        )
        
    except Exception as e:
        logger.error(f"Error in paper_position_saved signal: {e}", exc_info=True)


# =============================================================================
# PAPER TRADING ACCOUNT SIGNALS
# =============================================================================

@receiver(post_save, sender=PaperTradingAccount)
def paper_account_saved(sender, instance: PaperTradingAccount, created: bool, **kwargs) -> None:
    """
    Signal handler for PaperTradingAccount model save events.
    
    Broadcasts account balance and statistics updates to connected clients.
    
    Args:
        sender: The model class
        instance: The saved PaperTradingAccount instance
        created: Whether this is a new instance
        **kwargs: Additional keyword arguments
    """
    try:
        # Don't broadcast on account creation
        if created:
            return
        
        account_id = str(instance.account_id)
        
        # Prepare account data
        account_data = {
            'account_id': account_id,
            'name': instance.name,
            'current_balance_usd': float(instance.current_balance_usd),
            'initial_balance_usd': float(instance.initial_balance_usd),
            'eth_balance': float(instance.eth_balance),
            'total_pnl_usd': float(instance.total_pnl_usd),
            'total_trades': instance.total_trades,
            'successful_trades': instance.successful_trades,
            'failed_trades': instance.failed_trades,
            'win_rate': (
                float((instance.successful_trades / instance.total_trades) * 100)
                if instance.total_trades > 0 else 0.0
            ),
            'total_fees_paid_usd': float(instance.total_fees_paid_usd),
            'is_active': instance.is_active,
            'reset_count': instance.reset_count,
        }
        
        # Broadcast to connected clients
        broadcast_to_account(
            account_id=account_id,
            message_type='account_updated',
            data=account_data
        )
        
        logger.debug(f"Broadcast account update: account_id={account_id}")
        
    except Exception as e:
        logger.error(f"Error in paper_account_saved signal: {e}", exc_info=True)


# =============================================================================
# PAPER AI THOUGHT LOG SIGNALS
# =============================================================================

@receiver(post_save, sender=PaperAIThoughtLog)
def paper_thought_log_created(sender, instance: PaperAIThoughtLog, created: bool, **kwargs) -> None:
    """
    Signal handler for PaperAIThoughtLog model save events.
    
    Broadcasts AI decision reasoning to connected clients for transparency.
    
    Args:
        sender: The model class
        instance: The saved PaperAIThoughtLog instance
        created: Whether this is a new instance
        **kwargs: Additional keyword arguments
    """
    try:
        # Only broadcast new thought logs
        if not created:
            return
        
        account_id = str(instance.account.account_id)
        
        # Prepare thought log data
        thought_data = {
            'thought_id': str(instance.thought_id),
            'decision_type': instance.decision_type,
            'token_address': instance.token_address,
            'token_symbol': instance.token_symbol,
            'confidence_level': instance.confidence_level,
            'confidence_percent': float(instance.confidence_percent),
            'risk_score': float(instance.risk_score),
            'opportunity_score': float(instance.opportunity_score),
            'primary_reasoning': instance.primary_reasoning,
            'key_factors': instance.key_factors,
            'positive_signals': instance.positive_signals,
            'negative_signals': instance.negative_signals,
            'market_data': instance.market_data,
            'strategy_name': instance.strategy_name,
            'lane_used': instance.lane_used,
            'analysis_time_ms': instance.analysis_time_ms,
            'created_at': instance.created_at.isoformat(),
            'paper_trade_id': (
                str(instance.paper_trade.trade_id) 
                if instance.paper_trade else None
            ),
        }
        
        # Broadcast to connected clients
        broadcast_to_account(
            account_id=account_id,
            message_type='thought_log_created',
            data=thought_data
        )
        
        logger.info(
            f"Broadcast thought log: decision={instance.decision_type}, "
            f"token={instance.token_symbol}, confidence={instance.confidence_percent:.1f}%"
        )
        
    except Exception as e:
        logger.error(f"Error in paper_thought_log_created signal: {e}", exc_info=True)


# =============================================================================
# PAPER TRADING SESSION SIGNALS
# =============================================================================

@receiver(post_save, sender=PaperTradingSession)
def paper_session_saved(sender, instance: PaperTradingSession, created: bool, **kwargs) -> None:
    """
    Signal handler for PaperTradingSession model save events.
    
    Broadcasts session start/stop events to connected clients.
    
    Args:
        sender: The model class
        instance: The saved PaperTradingSession instance
        created: Whether this is a new instance
        **kwargs: Additional keyword arguments
    """
    try:
        account_id = str(instance.account.account_id)
        
        # Prepare session data
        session_data = {
            'session_id': str(instance.session_id),
            'strategy_name': instance.strategy_name,
            'start_time': instance.start_time.isoformat(),
            'end_time': (
                instance.end_time.isoformat() 
                if instance.end_time else None
            ),
            'status': instance.status,
            'total_trades_executed': instance.total_trades_executed,
            'successful_trades': instance.successful_trades,
            'failed_trades': instance.failed_trades,
            'starting_balance_usd': float(instance.starting_balance_usd),
            'ending_balance_usd': (
                float(instance.ending_balance_usd) 
                if instance.ending_balance_usd else None
            ),
            'total_pnl_usd': (
                float(instance.total_pnl_usd) 
                if instance.total_pnl_usd else None
            ),
            'notes': instance.notes,
        }
        
        # Determine message type based on session status
        if created:
            message_type = 'session_started'
            logger.info(f"Broadcast session start: session_id={instance.session_id}")
        elif instance.status in ['STOPPED', 'COMPLETED']:
            message_type = 'session_stopped'
            logger.info(f"Broadcast session stop: session_id={instance.session_id}")
        else:
            # Session updated but still active
            return
        
        # Broadcast to connected clients
        broadcast_to_account(
            account_id=account_id,
            message_type=message_type,
            data=session_data
        )
        
    except Exception as e:
        logger.error(f"Error in paper_session_saved signal: {e}", exc_info=True)


# =============================================================================
# PAPER PERFORMANCE METRICS SIGNALS
# =============================================================================

@receiver(post_save, sender=PaperPerformanceMetrics)
def paper_metrics_saved(sender, instance: PaperPerformanceMetrics, created: bool, **kwargs) -> None:
    """
    Signal handler for PaperPerformanceMetrics model save events.
    
    Broadcasts performance metrics updates to connected clients.
    
    Args:
        sender: The model class
        instance: The saved PaperPerformanceMetrics instance
        created: Whether this is a new instance
        **kwargs: Additional keyword arguments
    """
    try:
        # Get account from session
        account_id = str(instance.session.account.account_id)
        
        # Prepare metrics data
        metrics_data = {
            'metrics_id': str(instance.metrics_id),
            'session_id': str(instance.session.session_id),
            'period_start': instance.period_start.isoformat(),
            'period_end': instance.period_end.isoformat(),
            'total_trades': instance.total_trades,
            'winning_trades': instance.winning_trades,
            'losing_trades': instance.losing_trades,
            'win_rate': float(instance.win_rate),
            'total_pnl_usd': float(instance.total_pnl_usd),
            'total_pnl_percent': float(instance.total_pnl_percent),
            'avg_win_usd': float(instance.avg_win_usd),
            'avg_loss_usd': float(instance.avg_loss_usd),
            'largest_win_usd': float(instance.largest_win_usd),
            'largest_loss_usd': float(instance.largest_loss_usd),
            'sharpe_ratio': (
                float(instance.sharpe_ratio) 
                if instance.sharpe_ratio else None
            ),
            'max_drawdown_percent': float(instance.max_drawdown_percent),
            'profit_factor': (
                float(instance.profit_factor) 
                if instance.profit_factor else None
            ),
        }
        
        # Broadcast to connected clients
        broadcast_to_account(
            account_id=account_id,
            message_type='metrics_updated',
            data=metrics_data
        )
        
        logger.debug(f"Broadcast metrics update: session_id={instance.session.session_id}")
        
    except Exception as e:
        logger.error(f"Error in paper_metrics_saved signal: {e}", exc_info=True)


# =============================================================================
# PAPER STRATEGY CONFIGURATION SIGNALS
# =============================================================================

@receiver(post_save, sender=PaperStrategyConfiguration)
def paper_strategy_config_saved(sender, instance: PaperStrategyConfiguration, created: bool, **kwargs) -> None:
    """
    Signal handler for PaperStrategyConfiguration model save events.
    
    Broadcasts strategy configuration changes to connected clients.
    
    Args:
        sender: The model class
        instance: The saved PaperStrategyConfiguration instance
        created: Whether this is a new instance
        **kwargs: Additional keyword arguments
    """
    try:
        # Only broadcast updates, not creation
        if created:
            return
        
        account_id = str(instance.account.account_id)
        
        # Prepare strategy config data
        config_data = {
            'config_id': str(instance.config_id),
            'name': instance.name,
            'trading_mode': instance.trading_mode,
            'use_fast_lane': instance.use_fast_lane,
            'use_smart_lane': instance.use_smart_lane,
            'max_position_size': float(instance.max_position_size),
            'max_daily_trades': instance.max_daily_trades,
            'max_concurrent_positions': instance.max_concurrent_positions,
            'stop_loss_percent': float(instance.stop_loss_percent),
            'take_profit_percent': float(instance.take_profit_percent),
            'confidence_threshold': float(instance.confidence_threshold),
            'risk_score_threshold': float(instance.risk_score_threshold),
            'max_gas_price_gwei': float(instance.max_gas_price_gwei),
            'is_active': instance.is_active,
        }
        
        # Broadcast to connected clients
        broadcast_to_account(
            account_id=account_id,
            message_type='strategy_config_updated',
            data=config_data
        )
        
        logger.info(f"Broadcast strategy config update: config_id={instance.config_id}")
        
    except Exception as e:
        logger.error(f"Error in paper_strategy_config_saved signal: {e}", exc_info=True)


# =============================================================================
# SIGNAL REGISTRATION INFO
# =============================================================================

logger.info("Paper trading signals registered successfully")