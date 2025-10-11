"""
WebSocket Notification Service for Paper Trading Bot - IMPROVED VERSION

This service provides a centralized way for the trading bot to send 
real-time updates to connected dashboard clients via WebSocket.

Key improvements:
- Consistent room naming using account_id (UUID)
- Better error handling and validation
- Support for all message types
- Generic send method for flexibility
- Proper UUID handling

File: dexproject/paper_trading/services/websocket_service.py
"""

import logging
import uuid
from typing import Dict, Any, Optional, Union, List
from decimal import Decimal
from datetime import datetime

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


class WebSocketNotificationService:
    """
    Centralized service for sending real-time notifications to WebSocket clients.
    
    This service handles all WebSocket communications for the paper trading bot,
    ensuring consistent message formatting and delivery.
    """
    
    def __init__(self):
        """
        Initialize the WebSocket notification service.
        
        Sets up the channel layer and configures default settings.
        """
        self.channel_layer = get_channel_layer()
        
        # Log warning if channel layer is not available
        if not self.channel_layer:
            logger.warning(
                "Channel layer not configured! WebSocket notifications will not work. "
                "Please configure CHANNEL_LAYERS in settings.py"
            )
    
    # =========================================================================
    # ROOM NAME MANAGEMENT
    # =========================================================================
    
    def _get_room_group_name(self, account_id: Union[str, uuid.UUID]) -> str:
        """
        Generate consistent room group name for a paper trading account.
        
        Args:
            account_id: Account UUID (as string or UUID object)
            
        Returns:
            Room group name for channel layer
        """
        # Convert to string if UUID object
        if isinstance(account_id, uuid.UUID):
            account_id = str(account_id)
        
        # Use consistent naming pattern
        return f'paper_trading_{account_id}'
    
    # =========================================================================
    # CORE SEND METHOD
    # =========================================================================
    
    def send_update(
        self,
        account_id: Union[str, uuid.UUID],
        message_type: str,
        data: Dict[str, Any],
        include_timestamp: bool = True
    ) -> bool:
        """
        Generic method to send any type of update to WebSocket clients.
    
        This is the core method that all other send methods use internally.
    
        Args:
            account_id: Account UUID (string or UUID object)
            message_type: Type of message (e.g., 'trade_update', 'thought_log')
            data: Message payload
            include_timestamp: Whether to add timestamp to message
        
        Returns:
            True if message sent successfully, False otherwise
        """
        # Check if channel layer is available
        if not self.channel_layer:
            logger.error("Cannot send WebSocket update: Channel layer not configured")
            return False
    
        # Validate inputs
        if not account_id:
            logger.error("Cannot send WebSocket update: No account_id provided")
            return False
    
        if not message_type:
            logger.error("Cannot send WebSocket update: No message_type provided")
            return False
    
        try:
            # Get room group name
            room_group_name = self._get_room_group_name(account_id)
        
            # Serialize data
            serialized_data = self._serialize_data(data)
        
            # Add timestamp if requested
            if include_timestamp and 'timestamp' not in serialized_data:
                serialized_data['timestamp'] = datetime.now().isoformat()
            
            # DEBUG: Log what we're sending
            logger.info(
                f"SENDING WebSocket message to room {room_group_name}: "
                f"type={message_type} -> {message_type.replace('_', '.')}"
            )
        
            # Send message to room group
            async_to_sync(self.channel_layer.group_send)(
                room_group_name,
                {
                    'type': message_type.replace('_', '.'),  # Django Channels convention
                    'data': serialized_data
                }
            )
        
            logger.info(
                f"SENT WebSocket update: type={message_type}, "
                f"room={room_group_name}, data_keys={list(serialized_data.keys())}"
            )
            return True
        
        except Exception as e:
            logger.error(
                f"Error sending WebSocket update: type={message_type}, "
                f"account={account_id}, error={e}",
                exc_info=True
            )
            return False




    # =========================================================================
    # SPECIFIC MESSAGE METHODS (for backward compatibility and convenience)
    # =========================================================================
    
    def send_trade_update(
        self,
        account_id: Union[str, uuid.UUID],
        trade_data: Dict[str, Any]
    ) -> bool:
        """
        Send trade update to user's WebSocket group.
        
        Args:
            account_id: Account UUID
            trade_data: Trade information to send
            
        Returns:
            Success status
        """
        return self.send_update(account_id, 'trade_update', trade_data)
    
    def send_portfolio_update(
        self,
        account_id: Union[str, uuid.UUID],
        portfolio_data: Dict[str, Any]
    ) -> bool:
        """
        Send portfolio update to user's WebSocket group.
        
        Args:
            account_id: Account UUID
            portfolio_data: Portfolio information to send
            
        Returns:
            Success status
        """
        return self.send_update(account_id, 'portfolio_update', portfolio_data)
    
    def send_bot_status_update(
        self,
        account_id: Union[str, uuid.UUID],
        status_data: Dict[str, Any]
    ) -> bool:
        """
        Send bot status update to user's WebSocket group.
        
        Args:
            account_id: Account UUID
            status_data: Bot status information to send
            
        Returns:
            Success status
        """
        return self.send_update(account_id, 'bot_status_update', status_data)
    
    def send_thought_log(
        self,
        account_id: Union[str, uuid.UUID],
        thought_data: Dict[str, Any]
    ) -> bool:
        """
        Send AI thought log to user's WebSocket group.
    
        Args:
            account_id: Account UUID
            thought_data: AI decision thought log
        
        Returns:
            Success status
        """
        # Format thought data specifically for display
        formatted_thought = {
            'action': thought_data.get('action', 'Unknown'),
            'reasoning': thought_data.get('reasoning', ''),
            'confidence': thought_data.get('confidence_score', 0),
            'intel_level': thought_data.get('intel_level'),
            'risk_score': thought_data.get('risk_score'),
            'opportunity_score': thought_data.get('opportunity_score'),
            'created_at': thought_data.get('created_at', datetime.now().isoformat()),
            # Add fields that the frontend expects
            'decision_type': thought_data.get('decision_type', 'ANALYSIS'),
            'token_symbol': thought_data.get('token_symbol', ''),
            'thought_content': thought_data.get('primary_reasoning', thought_data.get('reasoning', '')),
            'thought_id': thought_data.get('thought_id', str(uuid.uuid4()))
        }
    
        # CRITICAL: Use 'thought_log_created' to match what JavaScript expects
        return self.send_update(account_id, 'thought_log_created', formatted_thought)





    def send_performance_update(
        self,
        account_id: Union[str, uuid.UUID],
        performance_data: Dict[str, Any]
    ) -> bool:
        """
        Send performance metrics update.
        
        Args:
            account_id: Account UUID
            performance_data: Performance metrics
            
        Returns:
            Success status
        """
        return self.send_update(account_id, 'performance_update', performance_data)
    
    def send_position_update(
        self,
        account_id: Union[str, uuid.UUID],
        position_data: Dict[str, Any]
    ) -> bool:
        """
        Send position update to user's WebSocket group.
        
        Args:
            account_id: Account UUID
            position_data: Position information
            
        Returns:
            Success status
        """
        return self.send_update(account_id, 'position_updated', position_data)
    
    def send_alert(
        self,
        account_id: Union[str, uuid.UUID],
        alert_data: Dict[str, Any]
    ) -> bool:
        """
        Send alert/notification to user's WebSocket group.
        
        Args:
            account_id: Account UUID
            alert_data: Alert information
            
        Returns:
            Success status
        """
        # Ensure alert has required fields
        formatted_alert = {
            'severity': alert_data.get('severity', 'info'),  # info, warning, error, critical
            'title': alert_data.get('title', 'Alert'),
            'message': alert_data.get('message', ''),
            'details': alert_data.get('details', {}),
            'dismissible': alert_data.get('dismissible', True)
        }
        
        return self.send_update(account_id, 'alert_message', formatted_alert)
    
    def send_session_update(
        self,
        account_id: Union[str, uuid.UUID],
        session_data: Dict[str, Any]
    ) -> bool:
        """
        Send trading session update.
        
        Args:
            account_id: Account UUID
            session_data: Session information
            
        Returns:
            Success status
        """
        return self.send_update(account_id, 'session_update', session_data)
    
    # =========================================================================
    # BULK MESSAGE METHODS
    # =========================================================================
    
    def send_bulk_update(
        self,
        account_id: Union[str, uuid.UUID],
        updates: List[Dict[str, Any]]
    ) -> bool:
        """
        Send multiple updates in a single message.
        
        Args:
            account_id: Account UUID
            updates: List of update dictionaries with 'type' and 'data' keys
            
        Returns:
            Success status
        """
        bulk_data = {
            'updates': updates,
            'count': len(updates)
        }
        
        return self.send_update(account_id, 'bulk_update', bulk_data)
    
    # =========================================================================
    # DATA SERIALIZATION
    # =========================================================================
    
    def _serialize_data(self, data: Any) -> Any:
        """
        Recursively serialize data for JSON transmission.
        
        Handles:
        - Decimal to float conversion
        - datetime to ISO format string
        - UUID to string
        - Nested dictionaries and lists
        
        Args:
            data: Data to serialize
            
        Returns:
            Serialized data
        """
        if data is None:
            return None
        
        if isinstance(data, dict):
            return {
                key: self._serialize_data(value)
                for key, value in data.items()
            }
        
        if isinstance(data, (list, tuple)):
            return [self._serialize_data(item) for item in data]
        
        if isinstance(data, Decimal):
            return float(data)
        
        if isinstance(data, datetime):
            return data.isoformat()
        
        if isinstance(data, uuid.UUID):
            return str(data)
        
        # For any object with a to_dict method
        if hasattr(data, 'to_dict'):
            return self._serialize_data(data.to_dict())
        
        # For any object with a __dict__ attribute
        if hasattr(data, '__dict__') and not isinstance(data, type):
            return self._serialize_data(data.__dict__)
        
        return data
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def is_available(self) -> bool:
        """
        Check if WebSocket service is available.
        
        Returns:
            True if channel layer is configured, False otherwise
        """
        return self.channel_layer is not None
    
    def get_room_members_count(self, account_id: Union[str, uuid.UUID]) -> Optional[int]:
        """
        Get approximate count of connected clients for an account.
        
        Note: This is an approximation as Django Channels doesn't provide
        exact group membership counts by default.
        
        Args:
            account_id: Account UUID
            
        Returns:
            Approximate member count or None if not available
        """
        # This would require additional infrastructure to track accurately
        # For now, return None to indicate the feature is not available
        logger.debug(f"Member count requested for account {account_id} - not implemented")
        return None


# =========================================================================
# SINGLETON INSTANCE
# =========================================================================

# Global instance for easy import and use throughout the application
websocket_service = WebSocketNotificationService()


# =========================================================================
# CONVENIENCE FUNCTIONS
# =========================================================================

def notify_trade(account_id: Union[str, uuid.UUID], trade_data: Dict[str, Any]) -> bool:
    """Convenience function to send trade notification."""
    return websocket_service.send_trade_update(account_id, trade_data)


def notify_thought(account_id: Union[str, uuid.UUID], thought_data: Dict[str, Any]) -> bool:
    """Convenience function to send thought log notification."""
    return websocket_service.send_thought_log(account_id, thought_data)


def notify_alert(account_id: Union[str, uuid.UUID], message: str, severity: str = 'info') -> bool:
    """Convenience function to send alert notification."""
    return websocket_service.send_alert(
        account_id,
        {'message': message, 'severity': severity}
    )


def is_websocket_available() -> bool:
    """Check if WebSocket service is available."""
    return websocket_service.is_available()