"""Test CoinGecko API key integration"""
import asyncio
import aiohttp
from django.conf import settings

async def test_coingecko_api():
    """Test if CoinGecko API key works"""
    
    # Get API key from settings
    api_key = getattr(settings, 'COIN_GECKO_API_KEY', None)
    
    print(f"API Key found: {'Yes' if api_key else 'No'}")
    if api_key:
        print(f"API Key starts with: {api_key[:10]}...")
    
    # Test API call
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {'ids': 'ethereum', 'vs_currencies': 'usd'}
    headers = {'x-cg-demo-api-key': api_key} if api_key else {}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers) as response:
            print(f"Response status: {response.status}")
            
            if response.status == 200:
                data = await response.json()
                print(f"✅ SUCCESS! Ethereum price: ${data['ethereum']['usd']}")
                return True
            elif response.status == 429:
                print("❌ RATE LIMIT: Too many requests")
                return False
            elif response.status == 401:
                print("❌ UNAUTHORIZED: Invalid API key")
                return False
            else:
                text = await response.text()
                print(f"❌ ERROR {response.status}: {text}")
                return False

if __name__ == "__main__":
    # Setup Django settings
    import os
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
    django.setup()
    
    # Run test
    asyncio.run(test_coingecko_api())