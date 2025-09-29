"""
Paper Trading WebSocket Consumer

Real-time WebSocket consumer for paper trading dashboard updates.
Provides live notifications for trades, positions, and performance metrics.

File: paper_trading/consumers.py
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
        
        FIXED: Now allows both authenticated and anonymous connections.
        Anonymous users get assigned to a default group for testing.
        """
        try:
            # Get user from scope (may be AnonymousUser)
            self.user = self.scope.get("user")
            
            # Determine user_id and account_id based on authentication status
            if self.user and hasattr(self.user, 'is_authenticated') and self.user.is_authenticated:
                # Authenticated user
                self.user_id = self.user.id
                
                # Try to get the user's paper trading account
                account = await self.get_user_account()
                if account:
                    self.account_id = str(account.account_id)
                    logger.info(f"Authenticated WebSocket connection for user {self.user.username} (ID: {self.user_id})")
                else:
                    # Authenticated but no account - use user ID as fallback
                    self.account_id = f"user_{self.user_id}"
                    logger.info(f"Authenticated user {self.user.username} has no paper trading account")
            else:
                # Anonymous user - use default values for testing
                self.user_id = 1  # Default user ID for anonymous
                self.account_id = "435f14e1-56b5-46dd-add6-2fd242177c29"  # Your demo account ID
                logger.info("Anonymous WebSocket connection - using default account for testing")
            
            # Create room group name
            self.room_group_name = f'paper_trading_{self.account_id}'
            
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            # Accept the WebSocket connection
            await self.accept()
            
            # Send connection confirmation
            await self.send(text_data=json.dumps({
                'type': 'connection_confirmed',
                'message': 'WebSocket connected successfully',
                'account_id': self.account_id,
                'authenticated': self.user.is_authenticated if self.user else False
            }))
            
            logger.info(f"WebSocket connected - Room: {self.room_group_name}")
            
            # Send initial data if needed
            await self.send_initial_data()
            
        except Exception as e:
            logger.error(f"Error in WebSocket connect: {e}", exc_info=True)
            await self.close()
    
    async def disconnect(self, close_code: int) -> None:
        """
        Handle WebSocket disconnection.
        
        Args:
            close_code: WebSocket close code
        """
        try:
            if hasattr(self, 'room_group_name'):
                # Leave room group
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
                logger.info(f"WebSocket disconnected from {self.room_group_name} with code {close_code}")
        except Exception as e:
            logger.error(f"Error in disconnect: {e}")
    
    async def receive(self, text_data: str) -> None:
        """
        Handle messages from WebSocket client.
        
        Args:
            text_data: JSON string from client
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            logger.debug(f"Received WebSocket message: {message_type}")
            
            # Handle different message types
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': data.get('timestamp', timezone.now().isoformat())
                }))
            elif message_type == 'get_portfolio':
                await self.send_portfolio_update()
            elif message_type == 'get_recent_trades':
                await self.send_recent_trades()
            elif message_type == 'get_thoughts':
                await self.send_recent_thoughts()
            elif message_type == 'subscribe':
                channel = data.get('channel')
                logger.info(f"Client subscribed to channel: {channel}")
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON received from client")
        except Exception as e:
            logger.error(f"Error handling client message: {e}", exc_info=True)
    
    # =========================================================================
    # CHANNEL LAYER MESSAGE HANDLERS - Server Initiated Updates
    # =========================================================================
    
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
    
    async def ai_decision_update(self, event: Dict[str, Any]) -> None:
        """
        Handle AI decision update from channel layer.
        
        Args:
            event: Event data containing AI decision
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'ai_decision_update',
                'data': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending ai_decision_update: {e}", exc_info=True)
    
    async def trade_update(self, event: Dict[str, Any]) -> None:
        """
        Handle trade update from channel layer.
        
        Args:
            event: Event data containing trade information
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'trade_update',
                'data': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending trade_update: {e}", exc_info=True)
    
    async def portfolio_update(self, event: Dict[str, Any]) -> None:
        """
        Handle portfolio update from channel layer.
        
        Args:
            event: Event data containing portfolio information
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'portfolio_update',
                'data': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending portfolio_update: {e}", exc_info=True)
    
    async def bot_status_update(self, event: Dict[str, Any]) -> None:
        """
        Handle bot status update from channel layer.
        
        Args:
            event: Event data containing bot status
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'bot_status_update',
                'data': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending bot_status_update: {e}", exc_info=True)
    
    async def performance_update(self, event: Dict[str, Any]) -> None:
        """
        Handle performance metrics update from channel layer.
        
        Args:
            event: Event data containing performance metrics
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'performance_update',
                'data': event.get('data', {}),
                'timestamp': timezone.now().isoformat()
            }, default=str))
            
        except Exception as e:
            logger.error(f"Error sending performance_update: {e}", exc_info=True)
    
    # =========================================================================
    # DATABASE ACCESS METHODS
    # =========================================================================
    
    @database_sync_to_async
    def get_user_account(self):
        """Get the user's paper trading account."""
        if self.user and self.user.is_authenticated:
            try:
                from paper_trading.models import PaperTradingAccount
                return PaperTradingAccount.objects.filter(
                    user=self.user,
                    is_active=True
                ).first()
            except Exception as e:
                logger.error(f"Error getting user account: {e}")
        return None
    
    async def send_initial_data(self) -> None:
        """Send initial data upon connection."""
        try:
            # Get recent thoughts
            thoughts = await self.get_recent_thoughts()
            if thoughts:
                await self.send(text_data=json.dumps({
                    'type': 'initial_thoughts',
                    'data': thoughts
                }))
                logger.debug(f"Sent {len(thoughts)} initial thoughts")
        except Exception as e:
            logger.error(f"Error sending initial data: {e}")
    
    @database_sync_to_async
    def get_recent_thoughts(self, limit: int = 3):
        """Get recent AI thoughts for initial load."""
        try:
            from paper_trading.models import PaperAIThoughtLog
            
            # Get thoughts for the account
            thoughts = PaperAIThoughtLog.objects.filter(
                account__account_id=self.account_id
            ).order_by('-created_at')[:limit]
            
            return [{
                'thought_id': str(thought.thought_id),
                'token_symbol': thought.token_symbol,
                'decision_type': thought.decision_type,
                'confidence': float(thought.confidence_percent),
                'lane_used': thought.lane_used,
                'reasoning': thought.primary_reasoning[:200] if thought.primary_reasoning else '',
                'created_at': thought.created_at.isoformat()
            } for thought in thoughts]
        except Exception as e:
            logger.error(f"Error getting recent thoughts: {e}")
            return []
    
    async def send_portfolio_update(self) -> None:
        """Send current portfolio data to client."""
        try:
            portfolio_data = await self.get_portfolio_data()
            await self.send(text_data=json.dumps({
                'type': 'portfolio_data',
                'data': portfolio_data
            }))
        except Exception as e:
            logger.error(f"Error sending portfolio update: {e}")
    
    @database_sync_to_async
    def get_portfolio_data(self):
        """Get current portfolio data."""
        try:
            from paper_trading.models import PaperPosition
            
            positions = PaperPosition.objects.filter(
                account__account_id=self.account_id,
                is_open=True
            )
            
            return {
                'positions': [{
                    'token_symbol': pos.token_symbol,
                    'quantity': float(pos.quantity),
                    'current_value': float(pos.current_value_usd),
                    'unrealized_pnl': float(pos.unrealized_pnl_usd),
                    'pnl_percent': float(pos.unrealized_pnl_percent)
                } for pos in positions],
                'total_value': float(sum(pos.current_value_usd for pos in positions)),
                'position_count': positions.count()
            }
        except Exception as e:
            logger.error(f"Error getting portfolio data: {e}")
            return {'positions': [], 'total_value': 0, 'position_count': 0}
    
    async def send_recent_trades(self) -> None:
        """Send recent trades to client."""
        try:
            trades = await self.get_recent_trades_data()
            await self.send(text_data=json.dumps({
                'type': 'recent_trades',
                'data': trades
            }))
        except Exception as e:
            logger.error(f"Error sending recent trades: {e}")
    
    @database_sync_to_async
    def get_recent_trades_data(self, limit: int = 10):
        """Get recent trades data."""
        try:
            from paper_trading.models import PaperTrade
            
            trades = PaperTrade.objects.filter(
                account__account_id=self.account_id
            ).order_by('-created_at')[:limit]
            
            return [{
                'trade_id': str(trade.trade_id),
                'trade_type': trade.trade_type,
                'token_symbol': trade.token_out_symbol or trade.token_in_symbol,
                'amount_usd': float(trade.amount_in_usd),
                'status': trade.status,
                'created_at': trade.created_at.isoformat()
            } for trade in trades]
        except Exception as e:
            logger.error(f"Error getting recent trades: {e}")
            return []
    
    async def send_recent_thoughts(self) -> None:
        """Send recent AI thoughts to client."""
        try:
            thoughts = await self.get_recent_thoughts(limit=5)
            await self.send(text_data=json.dumps({
                'type': 'recent_thoughts',
                'data': thoughts
            }))
        except Exception as e:
            logger.error(f"Error sending recent thoughts: {e}")


# dashboard/consumers.py
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)

class DashboardMetricsConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for dashboard metrics."""
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.group_name = "dashboard_metrics"
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()
        logger.info("Dashboard metrics WebSocket connected")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )