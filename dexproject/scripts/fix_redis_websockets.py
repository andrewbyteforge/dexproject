#!/usr/bin/env python
"""
Diagnose and Fix Redis Connection for Django Channels WebSockets

This script will:
1. Test Redis connection
2. Install missing packages
3. Fix Django settings configuration
4. Verify WebSocket setup

File: dexproject/scripts/fix_redis_websockets.py
"""

import os
import sys
import subprocess
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def check_redis_server():
    """Check if Redis server is running."""
    print("=" * 60)
    print("📡 Testing Redis Server Connection...")
    print("=" * 60)
    
    try:
        import redis
        
        # Test different connection methods
        connections_tested = []
        
        # Test 1: localhost connection
        try:
            r = redis.Redis(host='localhost', port=6379, db=0, socket_connect_timeout=2)
            if r.ping():
                connections_tested.append(('localhost:6379', True))
                print("✅ Redis server is running at localhost:6379")
                
                # Test set/get
                r.set('test_key', 'test_value', ex=10)
                value = r.get('test_key')
                if value == b'test_value':
                    print("✅ Redis read/write test successful")
                return True
        except Exception as e:
            connections_tested.append(('localhost:6379', False))
            print(f"❌ Failed to connect to localhost:6379: {e}")
        
        # Test 2: 127.0.0.1 connection
        try:
            r = redis.Redis(host='127.0.0.1', port=6379, db=0, socket_connect_timeout=2)
            if r.ping():
                connections_tested.append(('127.0.0.1:6379', True))
                print("✅ Redis server is running at 127.0.0.1:6379")
                return True
        except Exception as e:
            connections_tested.append(('127.0.0.1:6379', False))
            print(f"❌ Failed to connect to 127.0.0.1:6379: {e}")
            
        print("\n❌ Redis server is not accessible")
        print("\nMake sure Redis is running:")
        print("  Windows: redis-server.exe redis.windows.conf")
        print("  Linux/Mac: redis-server")
        return False
        
    except ImportError:
        print("❌ redis package not installed")
        return False


def check_required_packages():
    """Check and install required packages."""
    print("\n" + "=" * 60)
    print("📦 Checking Required Packages...")
    print("=" * 60)
    
    packages = {
        'redis': 'redis',
        'channels_redis': 'channels-redis',
        'channels': 'channels',
        'daphne': 'daphne'
    }
    
    missing_packages = []
    
    for import_name, pip_name in packages.items():
        try:
            __import__(import_name)
            print(f"✅ {pip_name} is installed")
        except ImportError:
            print(f"❌ {pip_name} is NOT installed")
            missing_packages.append(pip_name)
    
    if missing_packages:
        print(f"\n⚠️  Missing packages: {', '.join(missing_packages)}")
        install = input("\nDo you want to install missing packages? (y/n): ")
        
        if install.lower() == 'y':
            for package in missing_packages:
                print(f"\nInstalling {package}...")
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                    print(f"✅ {package} installed successfully")
                except subprocess.CalledProcessError:
                    print(f"❌ Failed to install {package}")
                    print(f"   Try manually: pip install {package}")
            return False
        else:
            print("\nPlease install missing packages manually:")
            for package in missing_packages:
                print(f"  pip install {package}")
            return False
    
    return True


def test_django_redis_configuration():
    """Test Django's Redis configuration."""
    print("\n" + "=" * 60)
    print("🔧 Testing Django Redis Configuration...")
    print("=" * 60)
    
    # Setup Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
    
    try:
        import django
        django.setup()
        
        from django.conf import settings
        
        print("\n📋 Current Django Settings:")
        print(f"  REDIS_URL: {getattr(settings, 'REDIS_URL', 'Not set')}")
        print(f"  REDIS_AVAILABLE: {getattr(settings, 'REDIS_AVAILABLE', 'Not set')}")
        
        # Check channel layers configuration
        channel_layers = getattr(settings, 'CHANNEL_LAYERS', {})
        if channel_layers:
            backend = channel_layers.get('default', {}).get('BACKEND', 'Not configured')
            print(f"  CHANNEL_LAYERS backend: {backend}")
            
            if 'InMemoryChannelLayer' in backend:
                print("\n⚠️  WARNING: Using InMemoryChannelLayer!")
                print("  This means Redis is not being detected properly.")
                return False
            elif 'RedisChannelLayer' in backend:
                print("\n✅ Redis Channel Layer is configured!")
                return True
        else:
            print("  CHANNEL_LAYERS: Not configured")
            return False
            
    except Exception as e:
        print(f"❌ Error testing Django configuration: {e}")
        return False


def fix_redis_timeout_issue():
    """Fix the Redis timeout issue in settings.py."""
    print("\n" + "=" * 60)
    print("🔨 Fixing Redis Connection Timeout Issue...")
    print("=" * 60)
    
    settings_file = project_root / 'dexproject' / 'settings.py'
    
    if not settings_file.exists():
        print(f"❌ Settings file not found: {settings_file}")
        return False
    
    # Read current settings
    with open(settings_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find and fix the Redis connection test
    if 'socket_connect_timeout=1' in content:
        # Replace timeout value
        new_content = content.replace(
            'socket_connect_timeout=1',
            'socket_connect_timeout=2'
        )
        
        # Also fix the Redis.from_url call to use correct parameters
        new_content = new_content.replace(
            'r = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=2)',
            'r = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=2)'
        )
        
        # Write back
        with open(settings_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print("✅ Fixed Redis timeout configuration in settings.py")
        print("  Changed socket_connect_timeout from 1 to 2 seconds")
        return True
    else:
        print("ℹ️  Redis timeout already configured or using different format")
        return True


def create_test_script():
    """Create a test script for WebSocket functionality."""
    print("\n" + "=" * 60)
    print("📝 Creating WebSocket Test Script...")
    print("=" * 60)
    
    test_script = project_root / 'scripts' / 'test_websocket_broadcast.py'
    
    test_content = '''#!/usr/bin/env python
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

# Setup Django
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from paper_trading.models import PaperTradingAccount
import uuid


def test_websocket_broadcast():
    """Test broadcasting a message through channel layer."""
    
    channel_layer = get_channel_layer()
    
    if not channel_layer:
        print("❌ No channel layer configured!")
        return False
    
    print(f"Channel Layer: {type(channel_layer).__name__}")
    
    # Get or create a test account
    try:
        account = PaperTradingAccount.objects.first()
        if not account:
            print("Creating test account...")
            account = PaperTradingAccount.objects.create(
                user_id=1,  # Adjust as needed
                name="Test Account",
                initial_balance=10000
            )
    except Exception as e:
        print(f"Using mock account ID due to: {e}")
        account = type('obj', (object,), {'id': uuid.uuid4()})()
    
    # Test broadcast
    room_group_name = f'paper_trading_{account.id}'
    
    print(f"\\nBroadcasting to room: {room_group_name}")
    
    try:
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'test.message',
                'data': {
                    'message': 'WebSocket test successful!',
                    'timestamp': 'test'
                }
            }
        )
        print("✅ Message broadcast successful!")
        print("\\nNOTE: To see the message, you need a WebSocket client connected to:")
        print(f"  ws://localhost:8000/ws/paper-trading/")
        return True
        
    except Exception as e:
        print(f"❌ Broadcast failed: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("WebSocket Broadcast Test")
    print("=" * 60)
    
    test_websocket_broadcast()
'''
    
    test_script.parent.mkdir(parents=True, exist_ok=True)
    test_script.write_text(test_content)
    test_script.chmod(0o755)
    
    print(f"✅ Created test script: {test_script}")
    print("  Run it with: python scripts/test_websocket_broadcast.py")
    
    return True


def print_summary_and_next_steps():
    """Print summary and next steps."""
    print("\n" + "=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)
    
    # Re-test after fixes
    redis_ok = check_redis_server()
    
    if redis_ok:
        print("\n✅ Redis server is running and accessible")
    else:
        print("\n❌ Redis server is not accessible")
        print("\nFIX: Make sure Redis is running:")
        print("  1. Open your Redis directory (D:\\redis)")
        print("  2. Run: redis-server.exe redis.windows.conf")
        print("  3. Keep that window open")
    
    print("\n" + "=" * 70)
    print("🚀 NEXT STEPS")
    print("=" * 70)
    
    print("\n1. Make sure Redis is running (keep the Redis window open)")
    print("\n2. Restart your Django server:")
    print("   python manage.py runserver")
    print("\n3. Test WebSocket broadcast:")
    print("   python scripts/test_websocket_broadcast.py")
    print("\n4. Open your paper trading dashboard and check if updates work")
    print("\n5. Check Django startup logs for:")
    print('   "Redis connection successful for Channel Layer"')
    print('   "Using Redis Channel Layer for WebSockets"')
    
    print("\n" + "=" * 70)
    print("💡 DEBUGGING TIPS")
    print("=" * 70)
    
    print("\nIf WebSockets still don't work:")
    print("\n1. Check Django logs when starting:")
    print("   Look for 'Redis not available' or 'Using In-Memory'")
    print("\n2. Test Redis directly:")
    print("   redis-cli ping")
    print("   (should return PONG)")
    print("\n3. Check Windows Firewall:")
    print("   Make sure port 6379 is not blocked")
    print("\n4. Try setting REDIS_URL explicitly:")
    print("   Set environment variable: REDIS_URL=redis://127.0.0.1:6379/0")


def main():
    """Main execution."""
    print("🔧 Redis WebSocket Fix Script")
    print("=" * 70)
    
    # Step 1: Check Redis server
    redis_ok = check_redis_server()
    
    # Step 2: Check packages
    packages_ok = check_required_packages()
    
    # Step 3: Fix timeout issue
    fix_redis_timeout_issue()
    
    # Step 4: Test Django configuration
    if redis_ok:
        django_ok = test_django_redis_configuration()
    else:
        django_ok = False
    
    # Step 5: Create test script
    create_test_script()
    
    # Step 6: Summary
    print_summary_and_next_steps()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nScript interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()