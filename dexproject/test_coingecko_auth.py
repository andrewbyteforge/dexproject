"""
Test CoinGecko API Authentication

This script tests if the CoinGecko API key is working correctly.
Run this to verify authentication before debugging the main bot.
"""

import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API key from environment
api_key = os.getenv('COIN_GECKO_API_KEY', '')

print("=" * 60)
print("CoinGecko API Authentication Test")
print("=" * 60)
print()

# Test 1: Check if API key is loaded
print("Test 1: API Key Loaded")
print("-" * 40)
if api_key:
    print(f"✅ API Key found: {api_key[:10]}...{api_key[-5:]}")
    print(f"   Length: {len(api_key)} characters")
else:
    print("❌ API Key NOT found in environment variables!")
    print("   Check your .env file has: COIN_GECKO_API_KEY=your-key-here")
    exit(1)

print()

# Test 2: Test with Header method (RECOMMENDED)
print("Test 2: Header Method (Recommended)")
print("-" * 40)

headers = {
    "accept": "application/json",
    "x-cg-demo-api-key": api_key  # Hyphen version for headers
}

try:
    # Test with /ping endpoint first
    response = requests.get(
        "https://api.coingecko.com/api/v3/ping",
        headers=headers,
        timeout=10
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text[:200]}")
    
    if response.status_code == 200:
        print("✅ Header authentication WORKS!")
    elif response.status_code == 401:
        print("❌ Authentication FAILED - API key invalid or not recognized")
    elif response.status_code == 403:
        print("❌ Authentication FAILED - API key not activated")
    elif response.status_code == 429:
        print("⚠️  Rate limited (but authentication probably works)")
    else:
        print(f"⚠️  Unexpected status code: {response.status_code}")
        
except Exception as e:
    print(f"❌ Request failed: {e}")

print()

# Test 3: Test actual price endpoint
print("Test 3: Price Endpoint (/simple/price)")
print("-" * 40)

params = {
    'ids': 'ethereum',
    'vs_currencies': 'usd'
}

try:
    response = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        headers=headers,
        params=params,
        timeout=10
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 200:
        print("✅ Price fetch with authentication WORKS!")
        data = response.json()
        if 'ethereum' in data:
            price = data['ethereum']['usd']
            print(f"   Ethereum price: ${price:,.2f}")
    else:
        print(f"❌ Price fetch failed with status {response.status_code}")
        
except Exception as e:
    print(f"❌ Request failed: {e}")

print()

# Test 4: Test with Query String method (alternative)
print("Test 4: Query String Parameter Method (Alternative)")
print("-" * 40)

params_with_key = {
    'ids': 'ethereum',
    'vs_currencies': 'usd',
    'x_cg_demo_api_key': api_key  # Underscore version for query params
}

try:
    response = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params=params_with_key,
        timeout=10
    )
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        print("✅ Query parameter authentication WORKS!")
    else:
        print(f"⚠️  Query parameter method status: {response.status_code}")
        
except Exception as e:
    print(f"❌ Request failed: {e}")

print()
print("=" * 60)
print("Test Complete!")
print("=" * 60)
print()
print("Next Steps:")
print("1. If all tests passed, the API key works correctly")
print("2. Check your .env file has: COIN_GECKO_API_KEY=your-key-here")
print("3. Check your Django settings.py loads: COIN_GECKO_API_KEY = os.getenv('COIN_GECKO_API_KEY')")
print("4. After 24 hours, check CoinGecko dashboard to see if calls are tracked")
print()