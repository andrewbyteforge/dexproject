"""
WebSocket Connection Diagnostic Test

This script tests WebSocket connectivity to various providers
to diagnose why live mempool connections are failing.

Run: python websocket_diagnostic.py

File: dexproject/websocket_diagnostic.py
"""

import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_websocket_connection(url: str, name: str) -> dict:
    """Test a single WebSocket connection."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    result = {
        'name': name,
        'url': url,
        'connected': False,
        'error': None,
        'details': []
    }
    
    try:
        # Try to import websockets
        try:
            import websockets
            result['details'].append("✅ websockets library available")
        except ImportError:
            result['error'] = "websockets library not installed"
            result['details'].append("❌ websockets library not installed")
            print("❌ FAILED: websockets library not installed")
            print("   Install with: pip install websockets")
            return result
        
        # Test connection with timeout
        print("Attempting connection...")
        async with asyncio.timeout(10):
            async with websockets.connect(url) as ws:
                result['connected'] = True
                result['details'].append("✅ WebSocket connection established")
                print("✅ CONNECTION SUCCESSFUL!")
                
                # Try to send a ping
                try:
                    pong = await ws.ping()
                    await asyncio.wait_for(pong, timeout=5)
                    result['details'].append("✅ Ping/pong successful")
                    print("✅ Ping/pong works")
                except Exception as e:
                    result['details'].append(f"⚠️  Ping failed: {e}")
                    print(f"⚠️  Ping failed but connection OK: {e}")
                
                # Try to subscribe to newHeads (if Ethereum JSON-RPC)
                try:
                    import json
                    subscribe_msg = json.dumps({
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "eth_subscribe",
                        "params": ["newHeads"]
                    })
                    await ws.send(subscribe_msg)
                    result['details'].append("✅ Sent subscription request")
                    print("✅ Sent eth_subscribe request")
                    
                    # Wait for response
                    response = await asyncio.wait_for(ws.recv(), timeout=5)
                    result['details'].append(f"✅ Received response: {response[:100]}...")
                    print(f"✅ Received response")
                except Exception as e:
                    result['details'].append(f"⚠️  Subscribe test failed: {e}")
                    print(f"⚠️  Subscribe test failed: {e}")
                
    except asyncio.TimeoutError:
        result['error'] = "Connection timeout after 10 seconds"
        result['details'].append("❌ Connection timeout")
        print("❌ FAILED: Connection timeout")
        
    except Exception as e:
        result['error'] = str(e)
        result['details'].append(f"❌ Error: {e}")
        print(f"❌ FAILED: {e}")
    
    return result

async def main():
    """Run diagnostic tests."""
    print("\n" + "="*60)
    print("WebSocket Connection Diagnostic Tool")
    print("="*60)
    
    # Get API keys from environment
    alchemy_key = os.getenv('ALCHEMY_API_KEY', '')
    base_alchemy_key = os.getenv('BASE_ALCHEMY_API_KEY', '')
    ankr_key = os.getenv('ANKR_API_KEY', '')
    infura_key = os.getenv('INFURA_PROJECT_ID', '')
    
    print("\n📋 Configuration:")
    print(f"   Alchemy Key: {'✅ Set' if alchemy_key else '❌ Missing'}")
    print(f"   Base Alchemy Key: {'✅ Set' if base_alchemy_key else '❌ Missing'}")
    print(f"   Ankr Key: {'✅ Set' if ankr_key else '❌ Missing'}")
    print(f"   Infura Key: {'✅ Set' if infura_key else '❌ Missing'}")
    
    # Define test endpoints
    tests = []
    
    if base_alchemy_key and base_alchemy_key != 'demo':
        tests.append({
            'name': 'Base Sepolia (Alchemy)',
            'url': f'wss://base-sepolia.g.alchemy.com/v2/{base_alchemy_key}'
        })
    
    if alchemy_key and alchemy_key != 'demo':
        tests.append({
            'name': 'Ethereum Sepolia (Alchemy)',
            'url': f'wss://eth-sepolia.g.alchemy.com/v2/{alchemy_key}'
        })
    
    if infura_key and infura_key != 'demo':
        tests.append({
            'name': 'Ethereum Sepolia (Infura)',
            'url': f'wss://sepolia.infura.io/ws/v3/{infura_key}'
        })
    
    # Public endpoints (no API key needed)
    tests.append({
        'name': 'Base Sepolia (Public)',
        'url': 'wss://base-sepolia-rpc.publicnode.com'
    })
    
    if not tests:
        print("\n❌ No API keys configured for testing!")
        print("   Please set ALCHEMY_API_KEY or BASE_ALCHEMY_API_KEY in .env")
        return
    
    # Run tests
    results = []
    for test in tests:
        result = await test_websocket_connection(test['url'], test['name'])
        results.append(result)
        await asyncio.sleep(1)  # Brief pause between tests
    
    # Summary
    print("\n" + "="*60)
    print("DIAGNOSTIC SUMMARY")
    print("="*60)
    
    successful = [r for r in results if r['connected']]
    failed = [r for r in results if not r['connected']]
    
    print(f"\n✅ Successful: {len(successful)}/{len(results)}")
    for r in successful:
        print(f"   • {r['name']}")
    
    if failed:
        print(f"\n❌ Failed: {len(failed)}/{len(results)}")
        for r in failed:
            print(f"   • {r['name']}")
            if r['error']:
                print(f"      Error: {r['error']}")
    
    # Recommendations
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)
    
    if not any(r['connected'] for r in results):
        print("""
❌ No WebSocket connections succeeded!

Possible issues:
1. Firewall blocking WebSocket connections (wss://)
2. Alchemy API keys may not support WebSocket access
3. Network connectivity issues
4. API rate limits reached

Solutions:
1. Check if 'websockets' library is installed:
   pip install websockets

2. Try using HTTP polling instead of WebSocket:
   In .env, set:
   MEMPOOL_MONITORING_ENABLED=false
   MEMPOOL_LIVE_MODE=false

3. Verify API keys are correct and active

4. Check Alchemy dashboard for WebSocket access permissions
        """)
    else:
        print(f"""
✅ {len(successful)} connection(s) working!

You can use these providers for live data.
The system should automatically use working connections.
        """)

if __name__ == '__main__':
    print("\nStarting WebSocket diagnostic test...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Diagnostic failed: {e}")
        import traceback
        traceback.print_exc()