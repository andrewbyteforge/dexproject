#!/usr/bin/env python3
"""
Quick Live Data Test Script

Simple test script to check the HTTP live service directly without Django management
command complexity. This tests the actual service running in the Django server.

Save as: quick_live_test.py
Run with: python quick_live_test.py
"""

import asyncio
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add Django project to path
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
import django
django.setup()

from django.conf import settings


async def test_http_live_service():
    """Test the HTTP live service directly."""
    print("🧪 Testing HTTP Live Service")
    print("=" * 40)
    
    try:
        # Import HTTP live service
        from dashboard.http_live_service import http_live_service
        
        print("✅ HTTP live service imported successfully")
        print(f"Live mode: {http_live_service.is_live_mode}")
        print(f"Available endpoints: {list(http_live_service.endpoints.keys())}")
        
        # Test initialization
        print("\n🔧 Testing initialization...")
        success = await http_live_service.initialize_live_monitoring()
        
        if success:
            print("✅ HTTP live monitoring initialized successfully")
            
            # Get status
            status = http_live_service.get_live_status()
            metrics = http_live_service.get_live_metrics()
            
            print("\n📊 Live Status:")
            print(f"  Running: {status['is_running']}")
            print(f"  Active connections: {status['metrics']['active_connections']}")
            print(f"  Method: {status.get('method', 'Unknown')}")
            print(f"  Success rate: {status['metrics'].get('success_rate', 0):.1f}%")
            
            print("\n📈 Live Metrics:")
            print(f"  Total transactions: {metrics['total_transactions_processed']}")
            print(f"  DEX transactions: {metrics['dex_transactions_detected']}")
            print(f"  Detection rate: {metrics['dex_detection_rate']:.1f}%")
            print(f"  Poll interval: {metrics['poll_interval_seconds']}s")
            
            # Monitor for a few seconds
            print("\n⏱️ Monitoring for 10 seconds...")
            start_time = time.time()
            
            while time.time() - start_time < 10:
                await asyncio.sleep(2)
                
                current_metrics = http_live_service.get_live_metrics()
                elapsed = int(time.time() - start_time)
                
                print(f"\r  {elapsed}s: TX: {current_metrics['total_transactions_processed']} | "
                      f"DEX: {current_metrics['dex_transactions_detected']} | "
                      f"Connections: {current_metrics['active_connections']}", end="")
            
            print("\n")
            
            # Final metrics
            final_metrics = http_live_service.get_live_metrics()
            print("📋 Final Results:")
            print(f"  Total transactions processed: {final_metrics['total_transactions_processed']}")
            print(f"  DEX transactions detected: {final_metrics['dex_transactions_detected']}")
            print(f"  Active connections: {final_metrics['active_connections']}")
            print(f"  Connection uptime: {final_metrics['connection_uptime_percentage']:.1f}%")
            
            if final_metrics['active_connections'] > 0:
                print("\n🎯 SUCCESS: HTTP live service is working!")
                print("Your Django server should show live data instead of mock data.")
                print("Check your dashboard at http://127.0.0.1:8000/")
            else:
                print("\n⚠️ PARTIAL: Service initialized but no active connections")
                print("Check API keys and network connectivity")
        else:
            print("❌ HTTP live monitoring failed to initialize")
            
            # Show errors
            status = http_live_service.get_live_status()
            errors = status.get('connection_errors', [])
            if errors:
                print("\nErrors:")
                for error in errors[-3:]:  # Show last 3 errors
                    print(f"  - {error}")
                    
    except ImportError as e:
        print(f"❌ Failed to import HTTP live service: {e}")
        
        # Try fallback service
        try:
            from dexproject.engine.simple_live_service import simple_live_service
            print("⚠️ Using fallback WebSocket service")
            
            success = await simple_live_service.initialize_live_monitoring()
            if success:
                print("✅ Fallback service initialized")
            else:
                print("❌ Fallback service also failed")
                
        except ImportError:
            print("❌ No live services available")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


def test_django_integration():
    """Test Django integration with engine service."""
    print("\n🔗 Testing Django Integration")
    print("=" * 30)
    
    try:
        from dashboard.engine_service import engine_service
        
        print("✅ Engine service imported")
        print(f"Live mode: {engine_service.live_data_enabled}")
        print(f"Mock mode: {engine_service.mock_mode}")
        
        # Get status
        status = engine_service.get_engine_status()
        metrics = engine_service.get_performance_metrics()
        
        print(f"\nEngine Status:")
        print(f"  Initialized: {status.get('initialized', False)}")
        print(f"  Status: {status.get('status', 'Unknown')}")
        print(f"  Live mode: {status.get('is_live', False)}")
        print(f"  Data source: {metrics.get('data_source', 'Unknown')}")
        
        if status.get('is_live', False):
            print("🎯 Django integration is using LIVE data!")
        else:
            print("⚠️ Django integration is using MOCK data")
            
    except Exception as e:
        print(f"❌ Django integration test failed: {e}")


async def main():
    """Run all tests."""
    print("🔍 Live Data System Test")
    print("=" * 50)
    print(f"Test time: {datetime.now()}")
    
    # Test HTTP service directly
    await test_http_live_service()
    
    # Test Django integration
    test_django_integration()
    
    print(f"\n✅ Test completed at {datetime.now()}")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()