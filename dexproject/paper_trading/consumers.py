"""
WebSocket consumers for real-time paper trading updates.

This module handles WebSocket connections for live dashboard updates,
including trades, portfolio changes, and performance metrics.

File: dexproject/paper_trading/consumers.py
"""

import json
import logging
import asyncio
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime, timedelta

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder

from .models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperAIThoughtLog,
    PaperPerformanceMetrics,
    PaperTradingSession
)

logger = logging.getLogger(__name__)


class PaperTradingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time paper trading updates.
    
    Handles:
    - Portfolio value updates
    - New trade notifications
    - Position changes
    - Performance metrics
    - AI thought logs
    - Bot status updates
    """
    
    def __init__(self, *args, **kwargs):
        """Initialize the consumer with default values."""
        super().__init__(*args, **kwargs)
        self.user = None
        self.account_id = None
        self.room_group_name = None
        self.update_task = None
        
    async def connect(self) -> None:
        """
        Handle WebSocket connection.
        
        Sets up the connection, joins appropriate groups,
        and starts sending periodic updates.
        """
        try:
            # Get user from scope
            self.user = self.scope["user"]
            
            if not self.user.is_authenticated:
                logger.warning("Unauthenticated WebSocket connection attempt")
                await self.close()
                return
                
            # Get user's paper trading account
            account = await self.get_user_account()
            if not account:
                logger.error(f"No paper trading account for user {self.user.username}")
                await self.close()
                return
                
            self.account_id = account.account_id
            
            # Create room name for this user's updates
            self.room_group_name = f'paper_trading_{self.user.id}'
            
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            await self.accept()
            
            # Send initial data
            await self.send_initial_data()
            
            # Start periodic updates (every 2 seconds)
            self.update_task = asyncio.create_task(self.send_periodic_updates())
            
            logger.info(f"WebSocket connected for user {self.user.username}")
            
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
            # Cancel update task if running
            if self.update_task:
                self.update_task.cancel()
                
            # Leave room group
            if self.room_group_name:
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
                
            logger.info(f"WebSocket disconnected for user {self.user.username if self.user else 'unknown'}")
            
        except Exception as e:
            logger.error(f"Error in WebSocket disconnect: {e}", exc_info=True)
    
    async def receive(self, text_data: str) -> None:
        """
        Handle incoming WebSocket messages.
        
        Args:
            text_data: JSON string with message data
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            # Handle different message types
            if message_type == 'ping':
                await self.send_pong()
                
            elif message_type == 'request_update':
                await self.send_full_update()
                
            elif message_type == 'subscribe':
                # Handle subscription to specific data streams
                stream = data.get('stream')
                await self.handle_subscription(stream)
                
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}", exc_info=True)
    
    async def send_initial_data(self) -> None:
        """Send initial dashboard data when connection is established."""
        try:
            # Get all initial data
            account_data = await self.get_account_data()
            portfolio_data = await self.get_portfolio_data()
            recent_trades = await self.get_recent_trades(limit=10)
            performance_data = await self.get_performance_data()
            session_data = await self.get_session_status()
            thought_logs = await self.get_recent_thoughts(limit=5)
            
            # Send initial data package
            await self.send(text_data=json.dumps({
                'type': 'initial_data',
                'timestamp': datetime.now().isoformat(),
                'data': {
                    'account': account_data,
                    'portfolio': portfolio_data,
                    'recent_trades': recent_trades,
                    'performance': performance_data,
                    'session': session_data,
                    'thoughts': thought_logs
                }
            }, cls=DjangoJSONEncoder))
            
        except Exception as e:
            logger.error(f"Error sending initial data: {e}", exc_info=True)
    
    async def send_periodic_updates(self) -> None:
        """Send periodic updates every 2 seconds."""
        while True:
            try:
                await asyncio.sleep(2)  # Update every 2 seconds
                
                # Get latest data
                portfolio_data = await self.get_portfolio_data()
                performance_data = await self.get_performance_data()
                session_data = await self.get_session_status()
                
                # Check for new trades
                new_trades = await self.get_new_trades_since(seconds=2)
                
                # Check for new thoughts
                new_thoughts = await self.get_new_thoughts_since(seconds=2)
                
                # Send update
                await self.send(text_data=json.dumps({
                    'type': 'periodic_update',
                    'timestamp': datetime.now().isoformat(),
                    'data': {
                        'portfolio': portfolio_data,
                        'performance': performance_data,
                        'session': session_data,
                        'new_trades': new_trades,
                        'new_thoughts': new_thoughts
                    }
                }, cls=DjangoJSONEncoder))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic update: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait longer on error
    
    async def send_full_update(self) -> None:
        """Send a complete data update on request."""
        try:
            account_data = await self.get_account_data()
            portfolio_data = await self.get_portfolio_data()
            recent_trades = await self.get_recent_trades(limit=20)
            performance_data = await self.get_performance_data()
            session_data = await self.get_session_status()
            
            await self.send(text_data=json.dumps({
                'type': 'full_update',
                'timestamp': datetime.now().isoformat(),
                'data': {
                    'account': account_data,
                    'portfolio': portfolio_data,
                    'recent_trades': recent_trades,
                    'performance': performance_data,
                    'session': session_data
                }
            }, cls=DjangoJSONEncoder))
            
        except Exception as e:
            logger.error(f"Error sending full update: {e}", exc_info=True)
    
    async def send_pong(self) -> None:
        """Send pong response to ping."""
        await self.send(text_data=json.dumps({
            'type': 'pong',
            'timestamp': datetime.now().isoformat()
        }))
    
    # =========================================================================
    # Database query methods (async)
    # =========================================================================
    
    @database_sync_to_async
    def get_user_account(self) -> Optional[PaperTradingAccount]:
        """Get the user's paper trading account."""
        return PaperTradingAccount.objects.filter(
            user=self.user,
            is_active=True
        ).first()
    
    @database_sync_to_async
    def get_account_data(self) -> Dict[str, Any]:
        """Get account summary data."""
        account = PaperTradingAccount.objects.get(account_id=self.account_id)
        return {
            'id': account.account_id,
            'name': account.name,
            'initial_balance': float(account.initial_balance_usd),
            'current_balance': float(account.current_balance_usd),
            'total_pnl': float(account.total_pnl_usd),
            'return_percent': float(account.total_return_percent),
            'created_at': account.created_at.isoformat()
        }
    
    @database_sync_to_async
    def get_portfolio_data(self) -> Dict[str, Any]:
        """Get current portfolio data including positions."""
        positions = PaperPosition.objects.filter(
            account_id=self.account_id,
            is_open=True
        ).order_by('-current_value_usd')
        
        position_list = []
        total_value = Decimal('0')
        total_unrealized_pnl = Decimal('0')
        
        for pos in positions:
            position_list.append({
                'token_symbol': pos.token_symbol,
                'quantity': float(pos.quantity),
                'entry_price': float(pos.entry_price),
                'current_price': float(pos.current_price),
                'current_value': float(pos.current_value_usd),
                'unrealized_pnl': float(pos.unrealized_pnl_usd),
                'pnl_percent': float(pos.unrealized_pnl_percent)
            })
            total_value += pos.current_value_usd
            total_unrealized_pnl += pos.unrealized_pnl_usd
        
        return {
            'positions': position_list,
            'total_value': float(total_value),
            'total_unrealized_pnl': float(total_unrealized_pnl),
            'position_count': len(position_list)
        }
    
    @database_sync_to_async
    def get_recent_trades(self, limit: int = 10) -> list:
        """Get recent trades."""
        trades = PaperTrade.objects.filter(
            account_id=self.account_id
        ).order_by('-created_at')[:limit]
        
        return [{
            'id': trade.trade_id,
            'trade_type': trade.trade_type,
            'token_in': trade.token_in_symbol,
            'token_out': trade.token_out_symbol,
            'amount_in': float(trade.amount_in),
            'amount_out': float(trade.amount_out),
            'amount_usd': float(trade.amount_in_usd),
            'status': trade.status,
            'created_at': trade.created_at.isoformat(),
            'strategy': trade.strategy_name
        } for trade in trades]
    
    @database_sync_to_async
    def get_performance_data(self) -> Dict[str, Any]:
        """Get performance metrics."""
        metrics = PaperPerformanceMetrics.objects.filter(
            session__account_id=self.account_id
        ).order_by('-calculated_at').first()
        
        if metrics:
            return {
                'total_trades': metrics.total_trades,
                'winning_trades': metrics.winning_trades,
                'losing_trades': metrics.losing_trades,
                'win_rate': float(metrics.win_rate),
                'avg_win_usd': float(metrics.avg_win_usd),
                'avg_loss_usd': float(metrics.avg_loss_usd),
                'profit_factor': float(metrics.profit_factor),
                'sharpe_ratio': float(metrics.sharpe_ratio) if metrics.sharpe_ratio else None,
                'max_drawdown_percent': float(metrics.max_drawdown_percent),
                'calculated_at': metrics.calculated_at.isoformat()
            }
        return {}
    
    @database_sync_to_async
    def get_session_status(self) -> Dict[str, Any]:
        """Get current trading session status."""
        session = PaperTradingSession.objects.filter(
            account_id=self.account_id,
            status='ACTIVE'
        ).first()
        
        if session:
            return {
                'active': True,
                'session_id': session.session_id,
                'strategy': session.strategy_name,
                'started_at': session.start_time.isoformat(),
                'trades_executed': session.trades_executed,
                'status': session.status
            }
        return {'active': False}
    
    @database_sync_to_async
    def get_recent_thoughts(self, limit: int = 5) -> list:
        """Get recent AI thought logs."""
        thoughts = PaperAIThoughtLog.objects.filter(
            account_id=self.account_id
        ).order_by('-created_at')[:limit]
        
        return [{
            'id': thought.thought_id,
            'action': thought.action,
            'decision_type': thought.decision_type,
            'reasoning': thought.reasoning,
            'confidence': float(thought.confidence_score),
            'created_at': thought.created_at.isoformat()
        } for thought in thoughts]
    
    @database_sync_to_async
    def get_new_trades_since(self, seconds: int = 2) -> list:
        """Get trades created in the last N seconds."""
        cutoff = timezone.now() - timedelta(seconds=seconds)
        trades = PaperTrade.objects.filter(
            account_id=self.account_id,
            created_at__gte=cutoff
        ).order_by('-created_at')
        
        return [{
            'id': trade.trade_id,
            'trade_type': trade.trade_type,
            'token_out': trade.token_out_symbol,
            'amount_usd': float(trade.amount_in_usd),
            'status': trade.status,
            'created_at': trade.created_at.isoformat()
        } for trade in trades]
    
    @database_sync_to_async
    def get_new_thoughts_since(self, seconds: int = 2) -> list:
        """Get thought logs created in the last N seconds."""
        cutoff = timezone.now() - timedelta(seconds=seconds)
        thoughts = PaperAIThoughtLog.objects.filter(
            account_id=self.account_id,
            created_at__gte=cutoff
        ).order_by('-created_at')
        
        return [{
            'action': thought.action,
            'reasoning': thought.reasoning[:100] + '...' if len(thought.reasoning) > 100 else thought.reasoning,
            'confidence': float(thought.confidence_score),
            'created_at': thought.created_at.isoformat()
        } for thought in thoughts]
    
    async def handle_subscription(self, stream: str) -> None:
        """
        Handle subscription to specific data streams.
        
        Args:
            stream: Name of the stream to subscribe to
        """
        # This can be extended to handle specific subscriptions
        logger.info(f"Subscription request for stream: {stream}")
    
    # =========================================================================
    # Group message handlers
    # =========================================================================
    
    async def trade_update(self, event: Dict[str, Any]) -> None:
        """
        Handle trade update messages from the group.
        
        Args:
            event: Event data containing trade information
        """
        await self.send(text_data=json.dumps({
            'type': 'trade_update',
            'data': event['data']
        }, cls=DjangoJSONEncoder))
    
    async def portfolio_update(self, event: Dict[str, Any]) -> None:
        """
        Handle portfolio update messages from the group.
        
        Args:
            event: Event data containing portfolio information
        """
        await self.send(text_data=json.dumps({
            'type': 'portfolio_update',
            'data': event['data']
        }, cls=DjangoJSONEncoder))
    
    async def bot_status_update(self, event: Dict[str, Any]) -> None:
        """
        Handle bot status update messages from the group.
        
        Args:
            event: Event data containing bot status
        """
        await self.send(text_data=json.dumps({
            'type': 'bot_status_update',
            'data': event['data']
        }, cls=DjangoJSONEncoder))