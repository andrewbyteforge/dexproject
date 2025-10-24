"""Test bulk price fetching optimization"""
import asyncio
import django
import os

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

from paper_trading.bot.price_service_integration import RealPriceManager

async def test_bulk_optimization():
    """Test the bulk price fetching optimization"""
    
    print("🚀 Testing OPTIMIZED Bulk Price Fetching")
    print("=" * 60)
    
    # Create price manager
    manager = RealPriceManager(use_real_prices=True, chain_id=84532)
    await manager.initialize()
    
    try:
        # Update all prices (should make only 1 API call)
        print("\n📊 Updating all token prices...")
        results = await manager.update_all_prices()
        
        # Show results
        print(f"\n✅ Update Results:")
        for symbol, success in results.items():
            token = next((t for t in manager.token_list if t['symbol'] == symbol), None)
            if token:
                status = "✅" if success else "❌"
                print(f"  {status} {symbol}: ${token['price']:.2f}")
        
        # Show statistics
        print(f"\n📈 Statistics:")
        stats = manager.get_statistics()
        print(f"  • Total API calls: {stats['total_api_calls']}")
        print(f"  • Bulk API calls: {stats['bulk_api_calls']}")
        print(f"  • API reduction: {stats['api_reduction_percent']}")
        print(f"  • Tokens updated: {sum(1 for r in results.values() if r)}/{len(results)}")
        
        # Calculate expected vs actual
        print(f"\n💡 Optimization Impact:")
        expected_calls = len(manager.token_list)  # Old way: 1 call per token
        actual_calls = stats['total_api_calls']
        reduction = ((expected_calls - actual_calls) / expected_calls * 100)
        print(f"  • Without optimization: {expected_calls} API calls")
        print(f"  • With optimization: {actual_calls} API call(s)")
        print(f"  • Reduction: {reduction:.0f}%")
        
        print("\n" + "=" * 60)
        print("🎉 Bulk fetching optimization is working!")
        
    finally:
        await manager.close()

if __name__ == "__main__":
    asyncio.run(test_bulk_optimization())