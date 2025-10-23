"""
Test Alchemy API Connection and Real Price Fetching

This script verifies that:
1. Alchemy API key is loaded correctly
2. Connection to Alchemy works
3. Real prices are being fetched
4. Fallback to CoinGecko works if needed

Run this AFTER updating your .env file with the correct Alchemy key.

Usage:
    python test_alchemy_connection.py
"""

import os
import sys
import asyncio
from decimal import Decimal

# Django setup
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

from paper_trading.services.price_feed_service import PriceFeedService


async def test_alchemy_connection():
    """Test Alchemy API connection and price fetching."""
    
    print("\n" + "=" * 70)
    print("ALCHEMY API CONNECTION TEST")
    print("=" * 70)
    
    # Check environment variables
    print("\n📋 STEP 1: Checking Environment Variables")
    print("-" * 70)
    
    alchemy_key = os.getenv('ALCHEMY_API_KEY', '')
    base_alchemy_key = os.getenv('BASE_ALCHEMY_API_KEY', '')
    coingecko_key = os.getenv('COIN_GECKO_API_KEY', '')
    
    print(f"ALCHEMY_API_KEY:      {'✅ SET' if alchemy_key else '❌ MISSING'} "
          f"(length: {len(alchemy_key)})")
    print(f"BASE_ALCHEMY_API_KEY: {'✅ SET' if base_alchemy_key else '❌ MISSING'} "
          f"(length: {len(base_alchemy_key)})")
    print(f"COIN_GECKO_API_KEY:   {'✅ SET' if coingecko_key else '❌ MISSING'} "
          f"(length: {len(coingecko_key)})")
    
    if not base_alchemy_key:
        print("\n❌ ERROR: BASE_ALCHEMY_API_KEY not found in environment!")
        print("Please update your .env file with:")
        print("BASE_ALCHEMY_API_KEY=alcht_xxzzvt8iNudqZKlTddpWsf35Pdicql")
        return False
    
    if len(base_alchemy_key) < 30:
        print(f"\n⚠️  WARNING: API key seems too short ({len(base_alchemy_key)} chars)")
        print("Expected ~40 characters for a valid Alchemy key")
    
    # Initialize PriceFeedService
    print("\n🔧 STEP 2: Initializing PriceFeedService")
    print("-" * 70)
    
    try:
        service = PriceFeedService(chain_id=84532)  # Base Sepolia
        print("✅ PriceFeedService initialized for Base Sepolia (Chain ID: 84532)")
    except Exception as e:
        print(f"❌ Failed to initialize PriceFeedService: {e}")
        return False
    
    # Test WETH price fetch (Alchemy)
    print("\n💰 STEP 3: Testing Real Price Fetch from Alchemy")
    print("-" * 70)
    
    weth_address = '0x4200000000000000000000000000000000000006'  # Base WETH
    
    try:
        print(f"Fetching WETH price from Alchemy...")
        print(f"Token Address: {weth_address}")
        
        weth_price = await service.get_token_price(
            token_address=weth_address,
            token_symbol='WETH'
        )
        
        if weth_price and weth_price > 0:
            print(f"✅ SUCCESS! WETH Price: ${weth_price:,.2f}")
            
            # Check if it's a realistic price
            if Decimal('1000') < weth_price < Decimal('10000'):
                print(f"✅ Price is realistic (between $1,000 and $10,000)")
            else:
                print(f"⚠️  Price seems unusual: ${weth_price:,.2f}")
                print("   This might be a fallback/mock price")
        else:
            print(f"❌ FAILED - No price returned or price is 0")
            print("   Check if Alchemy API key is valid")
            return False
            
    except Exception as e:
        print(f"❌ Error fetching price: {e}")
        import traceback
        print(traceback.format_exc())
        return False
    
    # Test USDC price fetch (CoinGecko fallback)
    print("\n💵 STEP 4: Testing CoinGecko Fallback")
    print("-" * 70)
    
    usdc_address = '0x036CbD53842c5426634e7929541eC2318f3dCF7e'  # Base Sepolia USDC
    
    try:
        print(f"Fetching USDC price (should use CoinGecko)...")
        
        usdc_price = await service.get_token_price(
            token_address=usdc_address,
            token_symbol='USDC'
        )
        
        if usdc_price:
            print(f"✅ SUCCESS! USDC Price: ${usdc_price:,.4f}")
            
            # USDC should be ~$1.00
            if Decimal('0.95') <= usdc_price <= Decimal('1.05'):
                print(f"✅ USDC price is correct (near $1.00)")
            else:
                print(f"⚠️  USDC price unusual: ${usdc_price:,.4f}")
        else:
            print(f"⚠️  No USDC price returned (CoinGecko might be down)")
            
    except Exception as e:
        print(f"⚠️  CoinGecko test failed: {e}")
    
    # Test multiple tokens
    print("\n🎯 STEP 5: Testing Multiple Token Prices")
    print("-" * 70)
    
    test_tokens = [
        ('WETH', '0x4200000000000000000000000000000000000006'),
        ('USDC', '0x036CbD53842c5426634e7929541eC2318f3dCF7e'),
        ('DAI', '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb'),
    ]
    
    results = []
    
    for symbol, address in test_tokens:
        try:
            price = await service.get_token_price(address, symbol)
            if price:
                results.append((symbol, price, True))
                print(f"  {symbol:8} ${price:>12,.2f}  ✅")
            else:
                results.append((symbol, None, False))
                print(f"  {symbol:8} {'N/A':>12}  ❌")
        except Exception as e:
            results.append((symbol, None, False))
            print(f"  {symbol:8} {'ERROR':>12}  ❌ ({str(e)[:30]})")
    
    # Close service
    await service.close()
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)
    
    successful = sum(1 for _, _, success in results if success)
    total = len(results)
    
    print(f"\nPrices fetched successfully: {successful}/{total}")
    
    if successful == total:
        print("\n✅ ALL TESTS PASSED!")
        print("\nYour bot is now configured to use REAL prices from:")
        print("  • Alchemy (for on-chain prices)")
        print("  • CoinGecko (for market prices)")
        print("\nYou can now run your paper trading bot with real data!")
        return True
    elif successful > 0:
        print("\n⚠️  PARTIAL SUCCESS")
        print("Some prices are working, but there may be configuration issues.")
        print("Check your API keys and network connectivity.")
        return False
    else:
        print("\n❌ ALL TESTS FAILED")
        print("\nPossible issues:")
        print("  1. Alchemy API key is invalid")
        print("  2. Network connectivity problems")
        print("  3. Rate limits exceeded")
        print("  4. Chain ID mismatch")
        return False


def main():
    """Run the async test."""
    try:
        success = asyncio.run(test_alchemy_connection())
        
        if success:
            print("\n" + "=" * 70)
            print("🚀 NEXT STEPS:")
            print("=" * 70)
            print("\n1. Start your paper trading bot:")
            print("   python manage.py run_paper_bot --intel 5 --verbose")
            print("\n2. Watch for real price updates in the logs:")
            print("   Look for: [PRICE UPDATE] WETH: $X,XXX.XX → $X,XXX.XX")
            print("\n3. Verify trades use real prices:")
            print("   Check trade records for realistic token prices")
            print("=" * 70)
            sys.exit(0)
        else:
            print("\n" + "=" * 70)
            print("❌ TESTS FAILED - PLEASE FIX CONFIGURATION")
            print("=" * 70)
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        print(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()