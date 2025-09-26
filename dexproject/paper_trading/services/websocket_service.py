"""
WebSocket notification service for paper trading bot.

This service allows the trading bot to send real-time updates
to connected dashboard clients via WebSocket.

File: dexproject/paper_trading/services/websocket_service.py
"""

import logging
from typing import Dict, Any
from decimal import Decimal
from datetime import datetime

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


class WebSocketNotificationService:
    """
    Service for sending real-time notifications to WebSocket clients.
    
    Used by the trading bot to push updates to connected dashboards.
    """
    
    def __init__(self):
        """Initialize the WebSocket notification service."""
        self.channel_layer = get_channel_layer()
        
    def send_trade_update(self, user_id: int, trade_data: Dict[str, Any]) -> None:
        """
        Send trade update to user's WebSocket group.
        
        Args:
            user_id: User ID for routing
            trade_data: Trade information to send
        """
        try:
            room_group_name = f'paper_trading_{user_id}'
            trade_data = self._serialize_data(trade_data)
            
            async_to_sync(self.channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'trade_update',
                    'data': trade_data
                }
            )
            logger.debug(f"Sent trade update to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error sending trade update: {e}", exc_info=True)
    
    def send_portfolio_update(self, user_id: int, portfolio_data: Dict[str, Any]) -> None:
        """
        Send portfolio update to user's WebSocket group.
        
        Args:
            user_id: User ID for routing
            portfolio_data: Portfolio information to send
        """
        try:
            room_group_name = f'paper_trading_{user_id}'
            portfolio_data = self._serialize_data(portfolio_data)
            
            async_to_sync(self.channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'portfolio_update',
                    'data': portfolio_data
                }
            )
            logger.debug(f"Sent portfolio update to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error sending portfolio update: {e}", exc_info=True)
    
    def send_bot_status_update(self, user_id: int, status_data: Dict[str, Any]) -> None:
        """
        Send bot status update to user's WebSocket group.
        
        Args:
            user_id: User ID for routing
            status_data: Bot status information to send
        """
        try:
            room_group_name = f'paper_trading_{user_id}'
            status_data = self._serialize_data(status_data)
            
            async_to_sync(self.channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'bot_status_update',
                    'data': status_data
                }
            )
            logger.debug(f"Sent bot status update to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error sending bot status update: {e}", exc_info=True)
    
    def send_thought_log(self, user_id: int, thought_data: Dict[str, Any]) -> None:
        """
        Send AI thought log to user's WebSocket group.
        
        Args:
            user_id: User ID for routing
            thought_data: AI decision thought log
        """
        try:
            room_group_name = f'paper_trading_{user_id}'
            thought_data = self._serialize_data(thought_data)
            
            formatted_thought = {
                'action': thought_data.get('action', 'Unknown'),
                'reasoning': thought_data.get('reasoning', ''),
                'confidence': thought_data.get('confidence_score', 0),
                'created_at': datetime.now().isoformat()
            }
            
            async_to_sync(self.channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'thought_update',
                    'data': formatted_thought
                }
            )
            logger.debug(f"Sent thought log to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error sending thought log: {e}", exc_info=True)
    
    def send_performance_update(self, user_id: int, performance_data: Dict[str, Any]) -> None:
        """
        Send performance metrics update.
        
        Args:
            user_id: User ID for routing
            performance_data: Performance metrics
        """
        try:
            room_group_name = f'paper_trading_{user_id}'
            performance_data = self._serialize_data(performance_data)
            
            async_to_sync(self.channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'performance_update',
                    'data': performance_data
                }
            )
            logger.debug(f"Sent performance update to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error sending performance update: {e}", exc_info=True)
    
    def _serialize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Serialize data for JSON transmission.
        
        Converts Decimal and datetime objects to JSON-compatible formats.
        
        Args:
            data: Data dictionary to serialize
            
        Returns:
            Serialized data dictionary
        """
        serialized = {}
        for key, value in data.items():
            if isinstance(value, Decimal):
                serialized[key] = float(value)
            elif isinstance(value, datetime):
                serialized[key] = value.isoformat()
            elif isinstance(value, dict):
                serialized[key] = self._serialize_data(value)
            elif isinstance(value, list):
                serialized[key] = [
                    self._serialize_data(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                serialized[key] = value
        return serialized


# Global instance for easy import
websocket_service = WebSocketNotificationService()
