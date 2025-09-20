#!/usr/bin/env python3
"""
API Key Test Script - Independent Validation

Tests your API keys independently to verify they work before using them in the service.
This helps identify whether the issue is with the keys themselves or the integration.

CREATE THIS FILE: scripts/test_api_keys.py

Usage:
    python scripts/test_api_keys.py

File: scripts/test_api_keys.py
"""

import asyncio
import aiohttp
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Add Django project to path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

# Setup Django to access settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
import django
django.setup()

from django.conf import settings


class APIKeyTester:
    """Test API keys independently of the main application."""
    
    def __init__(self):
        """Initialize the tester."""
        self.results = {}
        
    async def test_alchemy_key(self) -> dict:
        """Test Alchemy API key."""
        print("🧪 Testing Alchemy API Key...")
        
        key = getattr(settings, 'ALCHEMY_API_KEY', '')
        if not key:
            return {
                'status': 'MISSING',
                'message': 'ALCHEMY_API_KEY not found in settings',
                'working': False
            }
        
        # Test with Ethereum Sepolia
        url = f"https://eth-sepolia.g.alchemy.com/v2/{key}"
        
        try:
            result = await self._make_test_call(url, "Alchemy Ethereum Sepolia")
            return result
        except Exception as e:
            return {
                'status': 'ERROR',
                'message': f'Exception during test: {e}',
                'working': False
            }
    
    async def test_base_alchemy_key(self) -> dict:
        """Test Base Alchemy API key."""
        print("🧪 Testing Base Alchemy API Key...")
        
        key = getattr(settings, 'BASE_ALCHEMY_API_KEY', '') or getattr(settings, 'ALCHEMY_API_KEY', '')
        if not key:
            return {
                'status': 'MISSING',
                'message': 'BASE_ALCHEMY_API_KEY not found in settings',
                'working': False
            }
        
        # Test with Base Sepolia
        url = f"https://base-sepolia.g.alchemy.com/v2/{key}"
        
        try:
            result = await self._make_test_call(url, "Alchemy Base Sepolia")
            return result
        except Exception as e:
            return {
                'status': 'ERROR',
                'message': f'Exception during test: {e}',
                'working': False
            }
    
    async def test_infura_key(self) -> dict:
        """Test Infura project ID."""
        print("🧪 Testing Infura Project ID...")
        
        project_id = getattr(settings, 'INFURA_PROJECT_ID', '')
        if not project_id:
            return {
                'status': 'MISSING',
                'message': 'INFURA_PROJECT_ID not found in settings',
                'working': False
            }
        
        # Test with Ethereum Sepolia
        url = f"https://sepolia.infura.io/v3/{project_id}"
        
        try:
            result = await self._make_test_call(url, "Infura Ethereum Sepolia")
            return result
        except Exception as e:
            return {
                'status': 'ERROR',
                'message': f'Exception during test: {e}',
                'working': False
            }
    
    async def test_public_endpoints(self) -> dict:
        """Test public endpoints as fallback."""
        print("🧪 Testing Public Endpoints...")
        
        # Test Ethereum Sepolia public endpoint
        url = "https://rpc.sepolia.org"
        
        try:
            result = await self._make_test_call(url, "Public Ethereum Sepolia")
            return result
        except Exception as e:
            return {
                'status': 'ERROR',
                'message': f'Exception during test: {e}',
                'working': False
            }
    
    async def _make_test_call(self, url: str, description: str) -> dict:
        """Make a test RPC call to validate the endpoint."""
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_blockNumber",
            "params": [],
            "id": 1
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "DEX-API-Key-Tester/1.0"
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        
                        if 'result' in result:
                            block_number = int(result['result'], 16)
                            return {
                                'status': 'SUCCESS',
                                'message': f'✅ {description}: Block #{block_number}',
                                'working': True,
                                'block_number': block_number
                            }
                        else:
                            return {
                                'status': 'ERROR',
                                'message': f'❌ {description}: No result in response: {result}',
                                'working': False
                            }
                    
                    elif response.status == 401:
                        return {
                            'status': 'AUTH_FAILED',
                            'message': f'❌ {description}: 401 Authentication failed - Invalid API key',
                            'working': False
                        }
                    
                    elif response.status == 403:
                        return {
                            'status': 'FORBIDDEN',
                            'message': f'❌ {description}: 403 Access forbidden - Check API key permissions',
                            'working': False
                        }
                    
                    elif response.status == 429:
                        return {
                            'status': 'RATE_LIMITED',
                            'message': f'⚠️ {description}: 429 Rate limited - API key works but hit limits',
                            'working': True  # Key works, just rate limited
                        }
                    
                    else:
                        response_text = await response.text()
                        return {
                            'status': 'HTTP_ERROR',
                            'message': f'❌ {description}: HTTP {response.status} - {response_text[:100]}',
                            'working': False
                        }
        
        except asyncio.TimeoutError:
            return {
                'status': 'TIMEOUT',
                'message': f'⏱️ {description}: Request timeout - Network or endpoint issue',
                'working': False
            }
        
        except aiohttp.ClientError as e:
            return {
                'status': 'CLIENT_ERROR',
                'message': f'❌ {description}: Client error - {e}',
                'working': False
            }
    
    async def run_all_tests(self) -> None:
        """Run all API key tests."""
        print("🔑 API Key Validation Test")
        print("=" * 50)
        print(f"Test started at: {datetime.now()}\n")
        
        # Test all endpoints
        self.results['alchemy'] = await self.test_alchemy_key()
        self.results['base_alchemy'] = await self.test_base_alchemy_key()
        self.results['infura'] = await self.test_infura_key()
        self.results['public'] = await self.test_public_endpoints()
        
        # Print results
        print("\n📊 Test Results Summary:")
        print("=" * 30)
        
        working_count = 0
        for service, result in self.results.items():
            status_emoji = "✅" if result['working'] else "❌"
            print(f"{status_emoji} {service.upper()}: {result['message']}")
            if result['working']:
                working_count += 1
        
        print(f"\n📈 Summary: {working_count}/{len(self.results)} endpoints working")
        
        # Recommendations
        print("\n💡 Recommendations:")
        if working_count == 0:
            print("❌ No endpoints working - Check your API keys and network connection")
            print("   1. Verify your API keys are complete and not truncated")
            print("   2. Check that your API keys have Sepolia testnet permissions")
            print("   3. Ensure your .env file is being loaded correctly")
        elif working_count < len(self.results):
            print("⚠️ Some endpoints failing - System can work with fallbacks")
            print("   • Fix failing endpoints for better reliability")
            print("   • Public endpoints work as backup")
        else:
            print("🎯 All endpoints working - Your API configuration is excellent!")
        
        # Check for specific issues
        if not self.results['alchemy']['working'] and not self.results['base_alchemy']['working']:
            print("\n⚠️ Alchemy Issue Detected:")
            print("   Your Alchemy API keys appear to be invalid or incomplete")
            print("   Check: https://dashboard.alchemy.com/")
        
        if not self.results['infura']['working']:
            print("\n⚠️ Infura Issue Detected:")
            print("   Your Infura project ID appears to be invalid or incomplete") 
            print("   Check: https://infura.io/dashboard")


def show_current_settings():
    """Show current API key settings (masked for security)."""
    print("🔧 Current API Key Configuration:")
    print("-" * 35)
    
    alchemy_key = getattr(settings, 'ALCHEMY_API_KEY', '')
    base_key = getattr(settings, 'BASE_ALCHEMY_API_KEY', '')
    infura_id = getattr(settings, 'INFURA_PROJECT_ID', '')
    
    def mask_key(key: str) -> str:
        if not key:
            return "❌ NOT SET"
        elif len(key) < 10:
            return f"⚠️ TOO SHORT ({len(key)} chars)"
        else:
            return f"✅ SET ({key[:8]}***{key[-4:]})"
    
    print(f"ALCHEMY_API_KEY: {mask_key(alchemy_key)}")
    print(f"BASE_ALCHEMY_API_KEY: {mask_key(base_key)}")
    print(f"INFURA_PROJECT_ID: {mask_key(infura_id)}")
    print()


async def main():
    """Main test function."""
    try:
        show_current_settings()
        
        tester = APIKeyTester()
        await tester.run_all_tests()
        
        print(f"\n🏁 Test completed at: {datetime.now()}")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())