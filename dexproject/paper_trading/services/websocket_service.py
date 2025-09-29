"""
WebSocket notification service for paper trading bot.

This service allows the trading bot to send real-time updates
to connected dashboard clients via WebSocket.

UPDATED: Added AI decision streaming and thought log creation methods
for real-time dashboard updates.

File: dexproject/paper_trading/services/websocket_service.py
"""

import logging
from typing import Dict, Any, List
from decimal import Decimal
from datetime import datetime

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


class WebSocketNotificationService:
    """
    Service for sending real-time notifications to WebSocket clients.
    
    Used by the trading bot to push updates to connected dashboards.
    Enhanced with AI decision streaming capabilities.
    """
    
    def __init__(self):
        """Initialize the WebSocket notification service."""
        self.channel_layer = get_channel_layer()
        logger.info("WebSocket notification service initialized")
        
    def send_ai_decision(self, user_id: int, decision_data: Dict[str, Any]) -> None:
        """
        Send AI decision update to user's WebSocket group.
        
        This is the main method for streaming AI decisions in real-time.
        
        Args:
            user_id: User ID for routing
            decision_data: AI decision information to send
        """
        try:
            room_group_name = f'paper_trading_{user_id}'
            
            # Serialize and format the decision data
            serialized_data = self._serialize_data(decision_data)
            
            # Format for frontend consumption
            formatted_decision = {
                'token_symbol': serialized_data.get('token_symbol', 'Unknown'),
                'signal': serialized_data.get('signal', 'HOLD'),
                'action': serialized_data.get('action', 'hold'),
                'confidence': float(serialized_data.get('confidence', 0)),
                'lane_type': serialized_data.get('lane_type', 'SMART'),
                'position_size': float(serialized_data.get('position_size', 0)),
                'reasoning': serialized_data.get('reasoning', 'No reasoning provided'),
                'timestamp': datetime.now().isoformat(),
                'current_price': float(serialized_data.get('current_price', 0)) if serialized_data.get('current_price') else None,
                'risk_score': float(serialized_data.get('risk_score', 0)) if serialized_data.get('risk_score') else None
            }
            
            # Send to WebSocket channel
            async_to_sync(self.channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'ai_decision_update',
                    'data': formatted_decision
                }
            )
            
            logger.info(f"Sent AI decision for {formatted_decision['token_symbol']} to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error sending AI decision update: {e}", exc_info=True)
    
    def send_thought_log_created(self, user_id: int, thought_data: Dict[str, Any]) -> None:
        """
        Send AI thought log creation notification for real-time dashboard updates.
        
        This method is called when a new AI thought is logged to immediately
        update the AI Decision Stream on the dashboard.
        
        Args:
            user_id: User ID for routing
            thought_data: Thought log data containing AI reasoning
        """
        try:
            room_group_name = f'paper_trading_{user_id}'
            
            # Serialize the thought data
            serialized_data = self._serialize_data(thought_data)
            
            # Format thought for dashboard display
            formatted_thought = {
                'thought_id': str(serialized_data.get('thought_id', '')),
                'token_symbol': serialized_data.get('token_symbol', 'Unknown'),
                'decision_type': serialized_data.get('decision_type', 'ANALYSIS'),
                'confidence': float(serialized_data.get('confidence', 0)),
                'risk_score': float(serialized_data.get('risk_score', 0)),
                'lane_used': serialized_data.get('lane_used', 'SMART'),
                'reasoning': serialized_data.get('reasoning', ''),
                'positive_signals': serialized_data.get('positive_signals', []),
                'negative_signals': serialized_data.get('negative_signals', []),
                'created_at': serialized_data.get('created_at', datetime.now().isoformat()),
                'action': self._format_action_text(
                    serialized_data.get('decision_type', 'ANALYSIS'),
                    serialized_data.get('token_symbol', 'Unknown'),
                    serialized_data.get('confidence', 0)
                )
            }
            
            # Send to WebSocket channel with specific event type
            async_to_sync(self.channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'thought_log_created',
                    'data': formatted_thought
                }
            )
            
            logger.debug(f"Sent thought log notification for {formatted_thought['token_symbol']} to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error sending thought log notification: {e}", exc_info=True)
    
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
        
        Legacy method - use send_thought_log_created for new implementations.
        
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
    
    def _format_action_text(self, decision_type: str, token_symbol: str, confidence: float) -> str:
        """
        Format action text for display in thought log.
        
        Args:
            decision_type: Type of decision (BUY, SELL, HOLD, etc.)
            token_symbol: Token being analyzed
            confidence: Confidence percentage
            
        Returns:
            Formatted action text for dashboard display
        """
        confidence_text = f"({confidence:.0f}% confidence)"
        
        if decision_type == 'BUY':
            return f"Considering buy of {token_symbol} {confidence_text}"
        elif decision_type == 'SELL':
            return f"Considering sell of {token_symbol} {confidence_text}"
        elif decision_type == 'HOLD':
            return f"Holding position in {token_symbol} {confidence_text}"
        elif decision_type == 'ANALYSIS':
            return f"Analyzing {token_symbol} {confidence_text}"
        else:
            return f"{decision_type} for {token_symbol} {confidence_text}"


# Global instance for easy import
websocket_service = WebSocketNotificationService()