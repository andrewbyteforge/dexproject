"""
WebSocket Consumer for Dashboard Metrics

Simple WebSocket consumer for future expansion when we need 
bidirectional real-time communication beyond SSE capabilities.

File: dashboard/consumers.py
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


class DashboardMetricsConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time dashboard metrics.
    
    Currently minimal implementation for future expansion.
    SSE handles most real-time updates for Phase 2.
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        # Only allow authenticated users
        if not self.scope["user"].is_authenticated:
            await self.close()
            return
        
        # Join dashboard group
        self.group_name = f"dashboard_{self.scope['user'].id}"
        
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"WebSocket connected for user {self.scope['user'].username}")
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_confirmed',
            'message': 'WebSocket connected successfully'
        }))
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        
        logger.info(f"WebSocket disconnected with code {close_code}")
    
    async def receive(self, text_data):
        """Handle messages from WebSocket."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': data.get('timestamp')
                }))
            else:
                logger.warning(f"Unknown WebSocket message type: {message_type}")
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON received via WebSocket")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
    
    # Message handlers for group messages
    async def metrics_update(self, event):
        """Send metrics update to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'metrics_update',
            'data': event['data']
        }))
    
    async def status_update(self, event):
        """Send status update to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'status_update',  
            'data': event['data']
        }))
    
    async def alert_message(self, event):
        """Send alert message to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'alert',
            'data': event['data']
        }))