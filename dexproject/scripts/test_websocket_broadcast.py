#!/usr/bin/env python
"""
Test WebSocket Broadcasting

This script tests if WebSocket messages are properly broadcast
through Redis Channel Layer.

File: scripts/test_websocket_broadcast.py
"""

import os
import sys
import django
from pathlib import Path
from datetime import datetime

# Setup Django
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from paper_trading.models import PaperTradingAccount
from django.contrib.auth.models import User
import uuid
import json


def test_channel_layer():
    """Test that channel layer is properly configured."""
    print("\n" + "=" * 60)
    print("Testing Channel Layer Configuration")
    print("=" * 60)
    
    channel_layer = get_channel_layer()
    
    if not channel_layer:
        print("ERROR: No channel layer configured!")
        return None
    
    layer_type = type(channel_layer).__name__
    print(f"Channel Layer Type: {layer_type}")
    
    if 'InMemory' in layer_type:
        print("WARNING: Using InMemoryChannelLayer - broadcasts won't work across processes!")
        print("Redis is not properly configured.")
        return None
    elif 'Redis' in layer_type:
        print("SUCCESS: Using RedisChannelLayer - broadcasts will work!")
        return channel_layer
    else:
        print(f"Unknown channel layer type: {layer_type}")
        return channel_layer


def get_test_account():
    """Get or create a test paper trading account."""
    print("\n" + "=" * 60)
    print("Getting Test Account")
    print("=" * 60)
    
    try:
        # Try to get existing account
        account = PaperTradingAccount.objects.filter(is_active=True).first()
        
        if account:
            print(f"Using existing account: {account.name} (ID: {account.id})")
            return account
            
        # Create a test user if needed
        user, created = User.objects.get_or_create(
            username='websocket_test_user',
            defaults={'email': 'test@example.com'}
        )
        
        if created:
            print("Created test user: websocket_test_user")
        
        # Create test account
        account = PaperTradingAccount.objects.create(
            user=user,
            name="WebSocket Test Account",
            initial_balance=10000,
            current_balance=10000
        )
        print(f"Created test account: {account.name} (ID: {account.id})")
        return account
        
    except Exception as e:
        print(f"Error getting/creating account: {e}")
        # Return mock account for testing
        mock_account = type('MockAccount', (), {
            'id': str(uuid.uuid4()),
            'name': 'Mock Test Account'
        })()
        print(f"Using mock account (ID: {mock_account.id})")
        return mock_account


def test_broadcast(channel_layer, account):
    """Test broadcasting a message."""
    print("\n" + "=" * 60)
    print("Testing Message Broadcast")
    print("=" * 60)
    
    room_group_name = f'paper_trading_{account.id}'
    print(f"Broadcasting to room: {room_group_name}")
    
    # Create test trade data
    test_trade = {
        'id': str(uuid.uuid4()),
        'symbol': 'TEST/USDC',
        'side': 'BUY',
        'quantity': '100.0',
        'price': '1.234',
        'total_cost': '123.40',
        'fee': '0.25',
        'executed_at': datetime.now().isoformat(),
        'status': 'COMPLETED',
        'transaction_hash': '0x' + 'a' * 64
    }
    
    messages_to_test = [
        {
            'type': 'trade.executed',
            'data': test_trade
        },
        {
            'type': 'bot.status.update',
            'data': {
                'status': 'RUNNING',
                'message': 'WebSocket test successful!',
                'timestamp': datetime.now().isoformat()
            }
        },
        {
            'type': 'thought.log.created',
            'data': {
                'thought_type': 'MARKET_ANALYSIS',
                'content': 'This is a test thought from the WebSocket broadcast test',
                'confidence_score': 0.95,
                'timestamp': datetime.now().isoformat()
            }
        }
    ]
    
    success_count = 0
    
    for i, message in enumerate(messages_to_test, 1):
        print(f"\nTest {i}: Broadcasting {message['type']}...")
        
        try:
            async_to_sync(channel_layer.group_send)(
                room_group_name,
                message
            )
            print(f"  SUCCESS: {message['type']} broadcast sent")
            success_count += 1
            
        except Exception as e:
            print(f"  ERROR: Failed to broadcast {message['type']}: {e}")
    
    print("\n" + "-" * 40)
    print(f"Results: {success_count}/{len(messages_to_test)} messages broadcast successfully")
    
    return success_count == len(messages_to_test)


def test_websocket_service():
    """Test the centralized WebSocket service."""
    print("\n" + "=" * 60)
    print("Testing WebSocket Notification Service")
    print("=" * 60)
    
    try:
        from paper_trading.services.websocket_service import websocket_service
        
        # Get test account
        account = get_test_account()
        
        # Test sending different message types
        test_data = {
            'trade': {
                'symbol': 'ETH/USDC',
                'side': 'SELL',
                'quantity': '0.5',
                'price': '2500.00',
                'executed_at': datetime.now().isoformat()
            }
        }
        
        print(f"\nSending trade update via websocket_service...")
        result = websocket_service.send_trade_update(account.id, test_data['trade'])
        
        if result:
            print("  SUCCESS: Trade update sent via service")
        else:
            print("  ERROR: Failed to send trade update via service")
        
        return result
        
    except ImportError as e:
        print(f"  ERROR: Could not import websocket_service: {e}")
        return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def print_instructions():
    """Print instructions for testing."""
    print("\n" + "=" * 60)
    print("TESTING INSTRUCTIONS")
    print("=" * 60)
    
    print("\nTo fully test WebSocket functionality:")
    print("\n1. Keep this Django server running")
    print("\n2. Open your paper trading dashboard in a browser:")
    print("   http://localhost:8000/paper-trading/")
    print("\n3. Open browser developer console (F12)")
    print("\n4. Look for WebSocket connection messages")
    print("\n5. Run your paper trading bot")
    print("\n6. You should see real-time updates in the dashboard!")
    
    print("\nTo monitor WebSocket messages in the console:")
    print("  - Look for 'WebSocket message received' in browser console")
    print("  - Check Django server logs for broadcast messages")
    
    print("\n" + "=" * 60)


def main():
    """Main test execution."""
    print("=" * 70)
    print("WEBSOCKET BROADCAST TEST")
    print("=" * 70)
    
    # Test 1: Channel Layer
    channel_layer = test_channel_layer()
    if not channel_layer:
        print("\nERROR: Channel layer not properly configured!")
        print("Make sure Redis is running and Django settings are correct.")
        return False
    
    # Test 2: Get account
    account = get_test_account()
    
    # Test 3: Broadcast
    broadcast_success = test_broadcast(channel_layer, account)
    
    # Test 4: WebSocket Service
    service_success = test_websocket_service()
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    if broadcast_success and service_success:
        print("\nSUCCESS: All WebSocket tests passed!")
        print("\nYour WebSocket configuration is working correctly.")
        print("Real-time updates should now work in your paper trading dashboard.")
    else:
        print("\nWARNING: Some tests failed.")
        print("Check the errors above for details.")
    
    print_instructions()
    
    return broadcast_success and service_success


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)