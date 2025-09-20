#!/usr/bin/env python3
"""
Simple WebSocket Connection Test

Quick test script to verify WebSocket connections to blockchain providers
without Django management command complexity.

Save as: test_websockets.py
Run with: python test_websockets.py
"""

import asyncio
import os
from datetime import datetime

# Load environment variables
from pathlib import Path
import sys

# Add Django project to path
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
import django
django.setup()

from django.conf import settings


async def test_websocket_connection(url: str, provider: str, chain_id: int) -> bool:
    """Test a single WebSocket connection - FIXED VERSION."""
    try:
        import websockets
        print(f"  Testing {provider} chain {chain_id}: {url[:50]}...")
        
        # Use a more compatible connection method
        try:
            # Try with timeout parameter (newer versions)
            async with websockets.connect(url, timeout=5) as websocket:
                # Send a simple ping
                pong = await websocket.ping()
                await asyncio.wait_for(pong, timeout=3)
                print(f"    ✅ SUCCESS - Connection established and ping successful")
                return True
        except TypeError:
            # Fallback for older versions without timeout parameter
            try:
                async with websockets.connect(url) as websocket:
                    # Just check if we can connect
                    print(f"    ✅ SUCCESS - Connection established (basic test)")
                    return True
            except Exception as e:
                print(f"    ❌ FAILED - Connection error: {e}")
                return False
            
    except ImportError:
        print(f"    ❌ FAILED - websockets library not installed")
        print(f"    💡 Run: pip install websockets")
        return False
    except asyncio.TimeoutError:
        print(f"    ❌ FAILED - Connection timeout")
        return False
    except ConnectionRefusedError:
        print(f"    ❌ FAILED - Connection refused (server not available)")
        return False
    except Exception as e:
        print(f"    ❌ FAILED - {type(e).__name__}: {e}")
        return False


def generate_websocket_url(chain_id: int, provider: str) -> str:
    """Generate WebSocket URL for testing."""
    
    if provider == 'alchemy':
        api_key = getattr(settings, 'ALCHEMY_API_KEY', '')
        base_key = getattr(settings, 'BASE_API_KEY', api_key)
        
        if chain_id == 84532:  # Base Sepolia
            return f"wss://base-sepolia.g.alchemy.com/v2/{base_key}"
        elif chain_id == 11155111:  # Ethereum Sepolia
            return f"wss://eth-sepolia.g.alchemy.com/v2/{api_key}"
        elif chain_id == 8453:  # Base Mainnet
            return f"wss://base-mainnet.g.alchemy.com/v2/{base_key}"
        elif chain_id == 1:  # Ethereum Mainnet
            return f"wss://eth-mainnet.g.alchemy.com/v2/{api_key}"
    
    elif provider == 'ankr':
        api_key = getattr(settings, 'ANKR_API_KEY', '')
        
        if chain_id == 84532:  # Base Sepolia
            return f"wss://rpc.ankr.com/base_sepolia/ws/{api_key}"
        elif chain_id == 11155111:  # Ethereum Sepolia
            return f"wss://rpc.ankr.com/eth_sepolia/ws/{api_key}"
    
    elif provider == 'infura':
        project_id = getattr(settings, 'INFURA_PROJECT_ID', '')
        
        if chain_id == 11155111:  # Ethereum Sepolia
            return f"wss://sepolia.infura.io/ws/v3/{project_id}"
        elif chain_id == 1:  # Ethereum Mainnet
            return f"wss://mainnet.infura.io/ws/v3/{project_id}"
    
    return None


async def main():
    """Run WebSocket connection tests."""
    print("🔗 WebSocket Connection Diagnostic")
    print("=" * 50)
    
    # Check configuration
    print("\n🔧 Configuration Check:")
    
    api_keys = {
        'ALCHEMY_API_KEY': getattr(settings, 'ALCHEMY_API_KEY', ''),
        'BASE_API_KEY': getattr(settings, 'BASE_API_KEY', ''),
        'ANKR_API_KEY': getattr(settings, 'ANKR_API_KEY', ''),
        'INFURA_PROJECT_ID': getattr(settings, 'INFURA_PROJECT_ID', '')
    }
    
    for key_name, key_value in api_keys.items():
        status = "✅ CONFIGURED" if key_value else "❌ MISSING"
        if key_value:
            print(f"  {key_name}: {status} ({key_value[:8]}...{key_value[-4:]})")
        else:
            print(f"  {key_name}: {status}")
    
    # Test supported chains
    chains = getattr(settings, 'SUPPORTED_CHAINS', [84532, 11155111])
    print(f"\n📡 Supported chains: {chains}")
    
    # Test WebSocket connections
    print(f"\n🧪 Testing WebSocket Connections:")
    
    successful_connections = 0
    total_tests = 0
    
    for chain_id in chains:
        print(f"\nChain {chain_id}:")
        
        for provider in ['alchemy', 'ankr', 'infura']:
            # Check if API key is available
            if provider == 'alchemy' and not api_keys['ALCHEMY_API_KEY']:
                print(f"  {provider}: ⏭️  SKIPPED (no API key)")
                continue
            elif provider == 'ankr' and not api_keys['ANKR_API_KEY']:
                print(f"  {provider}: ⏭️  SKIPPED (no API key)")
                continue
            elif provider == 'infura' and not api_keys['INFURA_PROJECT_ID']:
                print(f"  {provider}: ⏭️  SKIPPED (no API key)")
                continue
            
            # Generate URL
            url = generate_websocket_url(chain_id, provider)
            if not url:
                print(f"  {provider}: ❌ NO URL PATTERN for chain {chain_id}")
                continue
            
            # Test connection
            total_tests += 1
            success = await test_websocket_connection(url, provider, chain_id)
            if success:
                successful_connections += 1
    
    # Summary
    print(f"\n📊 Test Results:")
    print(f"  Total tests: {total_tests}")
    print(f"  Successful: {successful_connections}")
    print(f"  Failed: {total_tests - successful_connections}")
    
    if successful_connections > 0:
        print(f"\n✅ SUCCESS: {successful_connections} working connections found!")
        print("Your live data system should work properly.")
    else:
        print(f"\n❌ FAILURE: No working connections found.")
        print("\n💡 Troubleshooting tips:")
        print("1. Install websockets: pip install websockets")
        print("2. Check your API keys are valid and active")
        print("3. Verify your internet connection")
        print("4. Check if testnet access is enabled for your API keys")
    
    print(f"\nTest completed at: {datetime.now()}")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()