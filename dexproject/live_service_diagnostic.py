#!/usr/bin/env python3
"""
Live Service Diagnostic Script

Diagnoses the live service connection issues and provides specific fixes.
This script will test your API keys and connections to identify the exact problem.

Usage:
    python live_service_diagnostic.py

Path: live_service_diagnostic.py
"""

import asyncio
import aiohttp
import os
import sys
from pathlib import Path
from datetime import datetime
import json

# Add Django project to path
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
import django
django.setup()

from django.conf import settings


class LiveServiceDiagnostic:
    """Diagnostic tool for live service issues."""
    
    def __init__(self):
        self.results = {}
        self.api_keys = {
            'alchemy': getattr(settings, 'ALCHEMY_API_KEY', ''),
            'base_alchemy': getattr(settings, 'BASE_ALCHEMY_API_KEY', ''),
            'ankr': getattr(settings, 'ANKR_API_KEY', ''),
            'infura': getattr(settings, 'INFURA_PROJECT_ID', '')
        }
    
    async def test_api_endpoint(self, url: str, provider: str, chain_id: int) -> dict:
        """Test a specific API endpoint."""
        result = {
            'url': url,
            'provider': provider,
            'chain_id': chain_id,
            'success': False,
            'error': None,
            'response_time': None,
            'block_number': None
        }
        
        # Create RPC request
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_blockNumber",
            "params": [],
            "id": 1
        }
        
        start_time = datetime.now()
        
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as response:
                    end_time = datetime.now()
                    result['response_time'] = (end_time - start_time).total_seconds()
                    
                    if response.status == 200:
                        data = await response.json()
                        if 'result' in data:
                            result['success'] = True
                            result['block_number'] = int(data['result'], 16)
                        else:
                            result['error'] = f"API Error: {data.get('error', 'Unknown error')}"
                    else:
                        result['error'] = f"HTTP {response.status}: {await response.text()}"
                        
        except asyncio.TimeoutError:
            result['error'] = "Connection timeout (10s)"
        except aiohttp.ClientError as e:
            result['error'] = f"Connection error: {str(e)}"
        except Exception as e:
            result['error'] = f"Unexpected error: {str(e)}"
        
        return result
    
    def generate_test_urls(self) -> list:
        """Generate list of URLs to test."""
        urls = []
        
        # Alchemy Ethereum Sepolia
        if self.api_keys['alchemy']:
            urls.append({
                'url': f"https://eth-sepolia.g.alchemy.com/v2/{self.api_keys['alchemy']}",
                'provider': 'alchemy',
                'chain_id': 11155111
            })
        
        # Alchemy Base Sepolia
        if self.api_keys['base_alchemy']:
            urls.append({
                'url': f"https://base-sepolia.g.alchemy.com/v2/{self.api_keys['base_alchemy']}",
                'provider': 'base_alchemy', 
                'chain_id': 84532
            })
        
        # Infura Ethereum Sepolia
        if self.api_keys['infura']:
            urls.append({
                'url': f"https://sepolia.infura.io/v3/{self.api_keys['infura']}",
                'provider': 'infura',
                'chain_id': 11155111
            })
        
        # Ankr Base Sepolia
        if self.api_keys['ankr']:
            urls.append({
                'url': f"https://rpc.ankr.com/base_sepolia/{self.api_keys['ankr']}",
                'provider': 'ankr',
                'chain_id': 84532
            })
        
        # Public fallback endpoints
        urls.extend([
            {
                'url': 'https://sepolia.base.org',
                'provider': 'public_base',
                'chain_id': 84532
            },
            {
                'url': 'https://ethereum-sepolia.publicnode.com',
                'provider': 'public_eth',
                'chain_id': 11155111
            }
        ])
        
        return urls
    
    async def run_comprehensive_test(self):
        """Run comprehensive diagnostic test."""
        print("🔍 Live Service Connection Diagnostic")
        print("=" * 60)
        print(f"Test started: {datetime.now()}")
        
        # Check API key configuration
        print("\n📋 API Key Configuration:")
        for key_name, key_value in self.api_keys.items():
            if key_value:
                masked_key = f"{key_value[:6]}...{key_value[-4:]}" if len(key_value) > 10 else "***"
                print(f"  ✅ {key_name.upper()}: {masked_key} (length: {len(key_value)})")
            else:
                print(f"  ❌ {key_name.upper()}: NOT SET")
        
        # Generate test URLs
        test_urls = self.generate_test_urls()
        print(f"\n🌐 Testing {len(test_urls)} endpoints...")
        
        # Test all endpoints
        results = []
        for i, url_config in enumerate(test_urls, 1):
            print(f"\n[{i}/{len(test_urls)}] Testing {url_config['provider']} (Chain {url_config['chain_id']})...")
            
            result = await self.test_api_endpoint(
                url_config['url'],
                url_config['provider'],
                url_config['chain_id']
            )
            
            results.append(result)
            
            if result['success']:
                print(f"  ✅ SUCCESS - Block: {result['block_number']} ({result['response_time']:.2f}s)")
            else:
                print(f"  ❌ FAILED - {result['error']}")
        
        # Analyze results
        print(f"\n📊 Test Results Summary:")
        print("=" * 40)
        
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]
        
        print(f"✅ Successful: {len(successful)}/{len(results)}")
        print(f"❌ Failed: {len(failed)}/{len(results)}")
        
        if successful:
            print(f"\n🎯 Working Endpoints:")
            for result in successful:
                print(f"  • {result['provider']} (Chain {result['chain_id']}) - {result['response_time']:.2f}s")
        
        if failed:
            print(f"\n⚠️ Failed Endpoints:")
            for result in failed:
                print(f"  • {result['provider']}: {result['error']}")
        
        # Provide recommendations
        self.provide_recommendations(successful, failed)
        
        return len(successful) > 0
    
    def provide_recommendations(self, successful: list, failed: list):
        """Provide specific recommendations based on test results."""
        print(f"\n💡 Recommendations:")
        print("=" * 30)
        
        if not successful:
            print("❌ CRITICAL: No working endpoints found!")
            print("\n🔧 Immediate Actions Required:")
            print("1. Check your internet connection")
            print("2. Verify API keys are complete and not truncated")
            print("3. Ensure API keys have testnet permissions enabled")
            print("4. Try regenerating your API keys from provider dashboards")
            
            # Specific provider issues
            alchemy_failed = any(r['provider'].startswith('alchemy') or r['provider'] == 'base_alchemy' for r in failed)
            infura_failed = any(r['provider'] == 'infura' for r in failed)
            ankr_failed = any(r['provider'] == 'ankr' for r in failed)
            
            if alchemy_failed:
                print("\n⚠️ Alchemy Issues:")
                print("   • Check: https://dashboard.alchemy.com/")
                print("   • Ensure Sepolia testnet is enabled")
                print("   • Verify API key isn't rate limited")
            
            if infura_failed:
                print("\n⚠️ Infura Issues:")
                print("   • Check: https://infura.io/dashboard")
                print("   • Ensure project has Sepolia access")
                print("   • Verify project ID is correct")
            
            if ankr_failed:
                print("\n⚠️ Ankr Issues:")
                print("   • Check: https://www.ankr.com/rpc/")
                print("   • Ensure API key format is correct")
        
        elif len(successful) < len(successful) + len(failed):
            print("⚠️ PARTIAL: Some endpoints working, some failing")
            print("   • System will work with fallbacks")
            print("   • Fix failing endpoints for better reliability")
            
            if any(r['provider'] in ['public_base', 'public_eth'] for r in successful):
                print("   • Currently relying on public endpoints")
                print("   • Add working API keys for better performance")
        
        else:
            print("🎯 EXCELLENT: All endpoints working!")
            print("   • Your API configuration is optimal")
            print("   • Live service should work perfectly")
        
        print(f"\n🔄 Next Steps:")
        if successful:
            print("1. The live service should now work")
            print("2. Restart your Django server if needed")
            print("3. Check dashboard at http://127.0.0.1:8000/")
        else:
            print("1. Fix API key issues listed above")
            print("2. Re-run this diagnostic script")
            print("3. Contact API providers if keys still don't work")
    
    async def test_live_service_integration(self):
        """Test integration with actual live service."""
        print(f"\n🔗 Testing Live Service Integration:")
        print("-" * 40)
        
        try:
            # Test HTTP live service
            from dashboard.http_live_service import http_live_service
            print("✅ HTTP live service imported")
            
            # Check if it's properly configured
            print(f"   Live mode: {http_live_service.is_live_mode}")
            print(f"   Endpoints: {list(http_live_service.endpoints.keys())}")
            
            if http_live_service.endpoints:
                print("✅ HTTP live service has configured endpoints")
                
                # Try to test one endpoint
                endpoint_name = list(http_live_service.endpoints.keys())[0]
                is_working = await http_live_service._test_endpoint(endpoint_name)
                
                if is_working:
                    print(f"✅ Test endpoint '{endpoint_name}' is working")
                else:
                    print(f"❌ Test endpoint '{endpoint_name}' failed")
                    
                    # Check for errors
                    if http_live_service.connection_errors:
                        print("   Recent errors:")
                        for error in http_live_service.connection_errors[-3:]:
                            print(f"     • {error}")
            else:
                print("❌ HTTP live service has no configured endpoints")
        
        except ImportError as e:
            print(f"❌ Could not import HTTP live service: {e}")
        except Exception as e:
            print(f"❌ Live service integration test failed: {e}")


async def main():
    """Run the diagnostic."""
    diagnostic = LiveServiceDiagnostic()
    
    # Run comprehensive test
    success = await diagnostic.run_comprehensive_test()
    
    # Test live service integration
    await diagnostic.test_live_service_integration()
    
    print(f"\n🏁 Diagnostic Complete: {datetime.now()}")
    
    if success:
        print("🎯 RESULT: At least one endpoint is working - live service should function")
    else:
        print("❌ RESULT: No working endpoints - live service will use mock data")
    
    return success


if __name__ == '__main__':
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n🛑 Diagnostic interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Diagnostic failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)