#!/usr/bin/env python3
"""
Basic Connection Test

Simple HTTP connection test to verify API keys work before trying WebSocket.
This tests the underlying connectivity without websockets library complexity.

Save as: basic_test.py
Run with: python basic_test.py
"""

import requests
import os
import sys
from pathlib import Path

# Add Django project to path
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
import django
django.setup()

from django.conf import settings


def test_http_connection(url: str, provider: str, chain_id: int) -> bool:
    """Test HTTP connection to verify API key works."""
    try:
        print(f"  Testing {provider} chain {chain_id}: {url[:50]}...")
        
        # Simple HTTP request to test connectivity
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            print(f"    ✅ SUCCESS - HTTP connection working")
            return True
        elif response.status_code == 401:
            print(f"    ❌ FAILED - Authentication error (invalid API key)")
            return False
        elif response.status_code == 403:
            print(f"    ❌ FAILED - Access forbidden (check API permissions)")
            return False
        else:
            print(f"    ⚠️  PARTIAL - HTTP {response.status_code} (API accessible but may have issues)")
            return True
            
    except requests.exceptions.ConnectTimeout:
        print(f"    ❌ FAILED - Connection timeout")
        return False
    except requests.exceptions.ConnectionError:
        print(f"    ❌ FAILED - Connection error (network/DNS issue)")
        return False
    except Exception as e:
        print(f"    ❌ FAILED - {type(e).__name__}: {e}")
        return False


def generate_http_url(chain_id: int, provider: str) -> str:
    """Generate HTTP RPC URL for testing."""
    
    if provider == 'alchemy':
        api_key = getattr(settings, 'ALCHEMY_API_KEY', '')
        base_key = getattr(settings, 'BASE_API_KEY', api_key)
        
        if chain_id == 84532:  # Base Sepolia
            return f"https://base-sepolia.g.alchemy.com/v2/{base_key}"
        elif chain_id == 11155111:  # Ethereum Sepolia
            return f"https://eth-sepolia.g.alchemy.com/v2/{api_key}"
        elif chain_id == 8453:  # Base Mainnet
            return f"https://base-mainnet.g.alchemy.com/v2/{base_key}"
        elif chain_id == 1:  # Ethereum Mainnet
            return f"https://eth-mainnet.g.alchemy.com/v2/{api_key}"
    
    elif provider == 'ankr':
        api_key = getattr(settings, 'ANKR_API_KEY', '')
        
        if chain_id == 84532:  # Base Sepolia
            return f"https://rpc.ankr.com/base_sepolia/{api_key}"
        elif chain_id == 11155111:  # Ethereum Sepolia
            return f"https://rpc.ankr.com/eth_sepolia/{api_key}"
    
    elif provider == 'infura':
        project_id = getattr(settings, 'INFURA_PROJECT_ID', '')
        
        if chain_id == 11155111:  # Ethereum Sepolia
            return f"https://sepolia.infura.io/v3/{project_id}"
        elif chain_id == 1:  # Ethereum Mainnet
            return f"https://mainnet.infura.io/v3/{project_id}"
    
    return None


def test_api_key_validity():
    """Test if API keys are valid by making RPC calls."""
    print("🔧 API Key Validation Test")
    print("=" * 40)
    
    # Check configuration
    print("\n📋 Configuration Check:")
    
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
    
    # Test HTTP connections
    chains = getattr(settings, 'SUPPORTED_CHAINS', [84532, 11155111])
    print(f"\n🌐 Testing HTTP RPC Connections:")
    print(f"Target chains: {chains}")
    
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
            url = generate_http_url(chain_id, provider)
            if not url:
                print(f"  {provider}: ❌ NO URL PATTERN for chain {chain_id}")
                continue
            
            # Test connection
            total_tests += 1
            success = test_http_connection(url, provider, chain_id)
            if success:
                successful_connections += 1
    
    # Summary
    print(f"\n📊 Test Results:")
    print(f"  Total tests: {total_tests}")
    print(f"  Successful: {successful_connections}")
    print(f"  Failed: {total_tests - successful_connections}")
    
    if successful_connections > 0:
        print(f"\n✅ SUCCESS: {successful_connections} working API connections found!")
        print("Your API keys are working. The issue is likely with WebSocket library.")
        print("\n🔧 Next steps:")
        print("1. pip install --upgrade websockets")
        print("2. Restart your Django server") 
        print("3. Try the live data monitoring again")
    else:
        print(f"\n❌ FAILURE: No working API connections found.")
        print("\n💡 Troubleshooting:")
        print("1. Check your API keys are valid and active")
        print("2. Verify testnet access is enabled")
        print("3. Check your internet connection")
        print("4. Contact API provider support")


if __name__ == '__main__':
    try:
        test_api_key_validity()
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()