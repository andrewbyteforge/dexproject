"""
Paper Trading WebSocket Consumer

Real-time WebSocket consumer for paper trading dashboard updates.
Provides live notifications for trades, positions, and performance metrics.

FIXED: Added trade_update() handler to fix "No handler for message type trade.update" error

File: dexproject/paper_trading/consumers.py
"""

import json
import logging
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.utils import timezone

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


class PaperTradingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time paper trading updates.

    Features:
    - Real-time trade notifications
    - Position updates
    - Performance metrics streaming
    - AI thought process streaming
    - Bot status updates
    """

    async def connect(self) -> None:
        """
        Handle WebSocket connection.

        Auto-creates or retrieves default paper trading account for single-user setup.
        """
        try:
            # Get user from scope
            self.user = self.scope.get("user")

            # For single-user setup, use default account
            # No authentication required
            logger.info("WebSocket connection attempt (single-user mode)")

            # Get or create default paper trading account
            account = await self.get_or_create_default_account()
            if not account:
                logger.error("Failed to create/get default paper trading account")
                await self.close(code=4004)
                return

            # Store account_id using the correct field name
            self.account_id = str(account.account_id)

            # Create unique group name for this user's paper trading
            self.room_group_name = f"paper_trading_{self.account_id}"

            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            # Accept the connection
            await self.accept()
            
            logger.info(
                f"Paper trading WebSocket connected: "
                f"account={self.account_id} (single-user mode)"
            )
            
            # Send connection confirmation with initial data
            await self.send_connection_confirmed()
            
            # Send initial portfolio snapshot
            await self.send_initial_snapshot()
            
        except Exception as e:
            logger.error(f"Error in WebSocket connect: {e}", exc_info=True)
            await self.close(code=4500)
    
    async def disconnect(self, code: int) -> None:
        """
        Handle WebSocket disconnection.
        
        Args:
            code: WebSocket close code
        """
        try:
            # Leave room group
            if hasattr(self, 'room_group_name'):
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
            
            logger.info(
                f"Paper trading WebSocket disconnected: "
                f"account={getattr(self, 'account_id', 'unknown')}, "
                f"code={code}"
            )
            
        except Exception as e:
            logger.error(f"Error in WebSocket disconnect: {e}", exc_info=True)
    
    async def receive(self, text_data: Optional[str] = None, bytes_data: Optional[bytes] = None) -> None:
        """
        Handle messages from WebSocket client.
        
        Args:
            text_data: JSON string from client (optional)
            bytes_data: Binary data from client (optional)
        """
        # We only handle text data (JSON messages)
        if not text_data:
            logger.warning("Received WebSocket message with no text data")
            return
        
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            logger.debug(f"Received WebSocket message: type={message_type}")
            
            # Handle different message types
            if message_type == 'ping':
                await self.send_pong(data.get('timestamp'))
            
            elif message_type == 'request_portfolio_update':
                await self.send_portfolio_update()
            
            elif message_type == 'request_trade_history':
                limit = data.get('limit', 10)
                await self.send_trade_history(limit)
            
            elif message_type == 'request_open_positions':
                await self.send_open_positions()
            
            elif message_type == 'request_performance_metrics':
                await self.send_performance_metrics()
            
            else:
                logger.warning(f"Unknown WebSocket message type: {message_type}")
                await self.send_error(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
            await self.send_error("Invalid JSON format")
        
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}", exc_info=True)
            await self.send_error("Internal server error")
    
    # =========================================================================
    # MESSAGE SENDERS - Client Communication
    # =========================================================================
    
    async def send_connection_confirmed(self) -> None:
        """Send connection confirmation to client."""
        await self.send(text_data=json.dumps({
            'type': 'connection_confirmed',
            'timestamp': timezone.now().isoformat(),
            'account_id': self.account_id,
            'message': 'WebSocket connected successfully'
        }))
    
    async def send_pong(self, timestamp: Optional[str] = None) -> None:
        """Send pong response to ping."""
        await self.send(text_data=json.dumps({
            'type': 'pong',
            'timestamp': timestamp or timezone.now().isoformat()
        }))
    
    async def send_error(self, message: str) -> None:
        """Send error message to client."""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message,
            'timestamp': timezone.now().isoformat()
        }))
    
    async def send_initial_snapshot(self) -> None:
        """Send initial data snapshot after connection."""
        try:
            account_data = await self.get_account_data()
            active_session = await self.get_active_session()
            
            snapshot = {
                'type': 'initial_snapshot',
                'timestamp': timezone.now().isoformat(),
                'account': account_data,
                'session': active_session,
            }
            
            await self.send(text_data=json.dumps(snapshot, default=str))
            
        except Exception as e:
            logger.error(f"Error sending initial snapshot: {e}", exc_info=True)
    
    # =========================================================================
    # GROUP MESSAGE HANDLERS - Broadcast to Client
    # =========================================================================
    
    async def trade_executed(self, event: Dict[str, Any]) -> None:
        """
        Handle trade_executed event from channel layer.
        
        Args:
            event: Event data containing trade information
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'trade_executed',
                'data': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending trade_executed: {e}", exc_info=True)
    
    async def trade_update(self, event: Dict[str, Any]) -> None:
        """
        Handle trade_update event from channel layer.
        
        This is an alias for trade_executed to handle the 'trade.update' message type
        sent by the WebSocket service signals.
        
        Args:
            event: Event data containing trade information
        """
        # Delegate to trade_executed for consistency
        logger.debug("Received trade.update message, delegating to trade_executed")
        await self.trade_executed(event)
    
    async def position_updated(self, event: Dict[str, Any]) -> None:
        """
        Handle position_updated event from channel layer.
        
        Args:
            event: Event data containing position information
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'position_updated',
                'data': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending position_updated: {e}", exc_info=True)
    
    async def position_closed(self, event: Dict[str, Any]) -> None:
        """
        Handle position_closed event from channel layer.
        
        Args:
            event: Event data containing closed position information
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'position_closed',
                'data': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending position_closed: {e}", exc_info=True)
    
    async def account_updated(self, event: Dict[str, Any]) -> None:
        """
        Handle account_updated event from channel layer.
        
        Args:
            event: Event data containing account information
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'account_updated',
                'data': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending account_updated: {e}", exc_info=True)
    
    async def thought_log_created(self, event: Dict[str, Any]) -> None:
        """
        Handle thought_log_created event from channel layer.
        
        Args:
            event: Event data containing AI thought log
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'thought_log_created',
                'data': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending thought_log_created: {e}", exc_info=True)
    
    async def session_started(self, event: Dict[str, Any]) -> None:
        """
        Handle session_started event from channel layer.
        
        Args:
            event: Event data containing session information
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'session_started',
                'data': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending session_started: {e}", exc_info=True)
    
    async def session_stopped(self, event: Dict[str, Any]) -> None:
        """
        Handle session_stopped event from channel layer.
        
        Args:
            event: Event data containing session information
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'session_stopped',
                'data': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending session_stopped: {e}", exc_info=True)
    
    async def metrics_updated(self, event: Dict[str, Any]) -> None:
        """
        Handle metrics_updated event from channel layer.
        
        Args:
            event: Event data containing performance metrics
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'metrics_updated',
                'data': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending metrics_updated: {e}", exc_info=True)
    
    # =========================================================================
    # DATA REQUEST HANDLERS - Client Requested Updates
    # =========================================================================
    
    async def send_portfolio_update(self) -> None:
        """Send current portfolio data to client."""
        try:
            account_data = await self.get_account_data()
            
            await self.send(text_data=json.dumps({
                'type': 'portfolio_update',
                'data': account_data,
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending portfolio update: {e}", exc_info=True)
            await self.send_error("Failed to retrieve portfolio data")
    
    async def send_trade_history(self, limit: int = 10) -> None:
        """
        Send recent trade history to client.
        
        Args:
            limit: Number of recent trades to retrieve
        """
        try:
            trades = await self.get_recent_trades(limit)
            
            await self.send(text_data=json.dumps({
                'type': 'trade_history',
                'data': trades,
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending trade history: {e}", exc_info=True)
            await self.send_error("Failed to retrieve trade history")
    
    async def send_open_positions(self) -> None:
        """Send current open positions to client."""
        try:
            positions = await self.get_open_positions()
            
            await self.send(text_data=json.dumps({
                'type': 'open_positions',
                'data': positions,
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending open positions: {e}", exc_info=True)
            await self.send_error("Failed to retrieve open positions")
    
    async def send_performance_metrics(self) -> None:
        """Send current performance metrics to client."""
        try:
            metrics = await self.get_performance_metrics()
            
            await self.send(text_data=json.dumps({
                'type': 'performance_metrics',
                'data': metrics,
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending performance metrics: {e}", exc_info=True)
            await self.send_error("Failed to retrieve performance metrics")
    
    # =========================================================================
    # DATABASE OPERATIONS - Async Wrapped
    # =========================================================================
    
    @database_sync_to_async
    def get_or_create_default_account(self) -> Optional[PaperTradingAccount]:
        """
        Get the single paper trading account for the system.
        
        Uses centralized utilities to ensure consistency across
        the entire application (bot, API, dashboard, WebSocket).
        
        Returns:
            PaperTradingAccount or None if creation failed
        """
        try:
            # ✅ USE CENTRALIZED UTILITY - prevents hardcoded IDs
            from paper_trading.utils import get_default_user, get_single_trading_account
            
            # Get the demo_user (same user the bot/dashboard uses)
            user = get_default_user()
            
            # Get the single trading account
            account = get_single_trading_account()
            
            logger.info(f"WebSocket using account: {account.name} ({account.account_id})")
            return account
            
        except Exception as e:
            logger.error(f"Error getting paper trading account: {e}", exc_info=True)
            return None

    @database_sync_to_async
    def get_user_account(self) -> Optional[PaperTradingAccount]:
        """
        Get user's active paper trading account.
        For single-user mode, this method is not used.
        
        Returns:
            PaperTradingAccount or None if not found
        """
        try:
            # In single-user mode, get default account
            return PaperTradingAccount.objects.filter(
                name="Default Paper Trading Account",
                is_active=True
            ).first()
        except Exception as e:
            logger.error(f"Error getting user account: {e}", exc_info=True)
            return None
    
    @database_sync_to_async
    def get_account_data(self) -> Dict[str, Any]:
        """
        Get account data for client.
        
        Returns:
            Dictionary with account information
        """
        try:
            account = PaperTradingAccount.objects.get(
                account_id=self.account_id
            )
            
            return {
                'account_id': str(account.account_id),
                'name': account.name,
                'current_balance_usd': float(account.current_balance_usd),
                'initial_balance_usd': float(account.initial_balance_usd),
                'total_pnl_usd': float(account.total_profit_loss_usd),
                'total_trades': account.total_trades,
                'successful_trades': account.winning_trades,
                'failed_trades': account.losing_trades,
                'win_rate': (
                    float((account.winning_trades / account.total_trades) * 100)
                    if account.total_trades > 0 else 0.0
                ),
                'is_active': account.is_active,
                'created_at': account.created_at.isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Error getting account data: {e}", exc_info=True)
            return {}
    
    @database_sync_to_async
    def get_active_session(self) -> Optional[Dict[str, Any]]:
        """
        Get active trading session data.
        
        Returns:
            Dictionary with session information or None
        """
        try:
            session = PaperTradingSession.objects.filter(
                account__account_id=self.account_id,
                status__in=['RUNNING', 'PAUSED']  # ✅ Only valid statuses
            ).first()
            
            if not session:
                return None
            
            return {
                'session_id': str(session.session_id),
                'started_at': session.started_at.isoformat(),
                'total_trades': session.total_trades,
                'strategy_name': (
                    session.strategy_config.name 
                    if session.strategy_config else 'Unknown'
                ),
                'status': session.status,
            }
            
        except Exception as e:
            logger.error(f"Error getting active session: {e}", exc_info=True)
            return None
    
    @database_sync_to_async
    def get_recent_trades(self, limit: int = 10) -> list:
        """
        Get recent trades for account.
        
        Args:
            limit: Number of trades to retrieve
            
        Returns:
            List of trade dictionaries
        """
        try:
            trades = PaperTrade.objects.filter(
                account__account_id=self.account_id
            ).order_by('-created_at')[:limit]
            
            return [
                {
                    'trade_id': str(trade.trade_id),
                    'trade_type': trade.trade_type,
                    'token_in_symbol': trade.token_in_symbol,
                    'token_out_symbol': trade.token_out_symbol,
                    'amount_in_usd': float(trade.amount_in_usd),
                    'status': trade.status,
                    'created_at': trade.created_at.isoformat(),
                    'executed_at': (
                        trade.executed_at.isoformat() 
                        if trade.executed_at else None
                    ),
                }
                for trade in trades
            ]
            
        except Exception as e:
            logger.error(f"Error getting recent trades: {e}", exc_info=True)
            return []
    
    @database_sync_to_async
    def get_open_positions(self) -> list:
        """
        Get open positions for account.
        
        Returns:
            List of position dictionaries
        """
        try:
            positions = PaperPosition.objects.filter(
                account__account_id=self.account_id,
                is_open=True
            ).order_by('-opened_at')
            
            return [
                {
                    'position_id': str(position.position_id),
                    'token_symbol': position.token_symbol,
                    'token_address': position.token_address,
                    'quantity': float(position.quantity),
                    'average_entry_price_usd': float(position.average_entry_price_usd),
                    'current_value_usd': (
                        float(position.current_value_usd) 
                        if position.current_value_usd else 0.0
                    ),
                    'unrealized_pnl_usd': float(position.unrealized_pnl_usd),
                    'opened_at': position.opened_at.isoformat(),
                }
                for position in positions
            ]
            
        except Exception as e:
            logger.error(f"Error getting open positions: {e}", exc_info=True)
            return []
    
    @database_sync_to_async
    def get_performance_metrics(self) -> Optional[Dict[str, Any]]:
        """
        Get latest performance metrics.
        
        Returns:
            Dictionary with performance metrics or None
        """
        try:
            session = PaperTradingSession.objects.filter(
                account__account_id=self.account_id,
                status__in=['RUNNING']  # or just status='RUNNING'
            ).first()
            
            if not session:
                return None
            
            metrics = PaperPerformanceMetrics.objects.filter(
                session=session
            ).order_by('-period_end').first()
            
            if not metrics:
                return None
            
            return {
                'metrics_id': str(metrics.metric_id),
                'total_trades': metrics.total_trades,
                'winning_trades': metrics.winning_trades,
                'losing_trades': metrics.losing_trades,
                'win_rate': float(metrics.win_rate),
                'total_pnl_usd': float(metrics.total_pnl_usd),
                'total_pnl_percent': float(metrics.total_pnl_percent),
                'avg_win_usd': float(metrics.average_win_usd),
                'avg_loss_usd': float(metrics.average_loss_usd),
                'largest_win_usd': float(metrics.largest_win_usd),
                'largest_loss_usd': float(metrics.largest_loss_usd),
                'max_drawdown_percent': (
                    float(metrics.max_drawdown_percent)
                    if metrics.max_drawdown_percent else 0.0
                ),
                'period_start': metrics.period_start.isoformat(),
                'period_end': metrics.period_end.isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}", exc_info=True)
            return None      

    async def performance_update(self, event: Dict[str, Any]) -> None:
        """
        Handle performance update messages from the bot.
        
        Args:
            event: Dictionary containing performance metrics data
        """
        try:
            # Extract the performance data from the event
            performance_data = event.get('data', {})
            
            # Log the update for debugging
            logger.info("[WS] Broadcasting performance update to client")
            
            # Send the performance update to the WebSocket client
            await self.send(text_data=json.dumps({
                'type': 'performance_update',
                'data': performance_data,
                'timestamp': timezone.now().isoformat()
            }))
            
        except Exception as e:
            logger.error(f"[WS] Error handling performance update: {e}")
            # Don't crash the connection on error
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to process performance update',
                'timestamp': timezone.now().isoformat()
            }))

    async def session_update(self, event: Dict[str, Any]) -> None:
        """
        Handle session update messages.
        
        Args:
            event: Dictionary containing session data
        """
        await self.send(text_data=json.dumps(event))

    async def strategy_config_updated(self, event: Dict[str, Any]) -> None:
        """
        Handle strategy config update messages.
        
        Args:
            event: Dictionary containing strategy configuration data
        """
        await self.send(text_data=json.dumps(event))

    async def portfolio_update(self, event: Dict[str, Any]) -> None:
        """
        Handle portfolio update messages.
        
        Args:
            event: Dictionary containing portfolio data
        """
        await self.send(text_data=json.dumps(event))


    async def order_update(self, event):
        """Handle order status updates."""
        logger.info(f"Broadcasting order update: {event.get('order_id', 'unknown')}")
        
        await self.send(text_data=json.dumps({
            'type': 'order_update',
            'order': event.get('order', {}),
            'timestamp': timezone.now().isoformat()
        }))
    
    async def order_filled(self, event):
        """Handle order filled notification."""
        logger.info(f"Broadcasting order filled: {event.get('order_id', 'unknown')}")
        
        await self.send(text_data=json.dumps({
            'type': 'order_filled',
            'order': event.get('order', {}),
            'timestamp': timezone.now().isoformat()
        }))
    
    async def order_cancelled(self, event):
        """Handle order cancellation notification."""
        logger.info(f"Broadcasting order cancelled: {event.get('order_id', 'unknown')}")
        
        await self.send(text_data=json.dumps({
            'type': 'order_cancelled',
            'order': event.get('order', {}),
            'reason': event.get('reason', 'Unknown'),
            'timestamp': timezone.now().isoformat()
        }))