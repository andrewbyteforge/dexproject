"""
Gas Optimizer Test Script - Phase 6A

Test script to demonstrate the Django Gas Optimization Service
with real-time console output and integration testing.

Run this from the Django management command or shell to see
live gas optimization in action.

File: scripts/test_gas_optimizer.py
"""

import asyncio
import sys
import os
from decimal import Decimal
from datetime import datetime

# Add Django project to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import django
from django.conf import settings

# Configure Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()


async def test_gas_optimizer():
    """Test the gas optimizer with different scenarios."""
    print("=" * 80)
    print("🧪 TESTING DJANGO GAS OPTIMIZATION SERVICE")
    print("=" * 80)
    
    try:
        # Import after Django setup
        from trading.services.gas_optimizer import (
            get_gas_optimizer,
            optimize_trade_gas,
            TradingGasStrategy
        )
        
        print("✅ Successfully imported gas optimizer service")
        
        # Initialize the optimizer
        print("\n🔧 Initializing gas optimizer...")
        optimizer = await get_gas_optimizer()
        
        if not optimizer:
            print("❌ Failed to initialize gas optimizer")
            return
        
        print("✅ Gas optimizer initialized successfully")
        
        # Wait a moment for initialization to complete
        await asyncio.sleep(2)
        
        print("\n" + "=" * 60)
        print("📊 TESTING GAS OPTIMIZATION SCENARIOS")
        print("=" * 60)
        
        # Test scenarios
        test_scenarios = [
            {
                'name': 'Paper Trading - Small Buy',
                'chain_id': 1,
                'trade_type': 'buy',
                'amount_usd': Decimal('100'),
                'strategy': 'balanced',
                'is_paper_trade': True
            },
            {
                'name': 'Live Trading - Medium Sell on Ethereum',
                'chain_id': 1,
                'trade_type': 'sell',
                'amount_usd': Decimal('1000'),
                'strategy': 'cost_efficient',
                'is_paper_trade': False
            },
            {
                'name': 'Speed Priority - Large Buy on Base',
                'chain_id': 8453,
                'trade_type': 'buy',
                'amount_usd': Decimal('5000'),
                'strategy': 'speed_priority',
                'is_paper_trade': False
            },
            {
                'name': 'MEV Protected Swap',
                'chain_id': 1,
                'trade_type': 'swap',
                'amount_usd': Decimal('2500'),
                'strategy': 'mev_protected',
                'is_paper_trade': False
            }
        ]
        
        for i, scenario in enumerate(test_scenarios, 1):
            print(f"\n🧪 Test {i}: {scenario['name']}")
            print("-" * 50)
            
            try:
                result = await optimize_trade_gas(
                    chain_id=scenario['chain_id'],
                    trade_type=scenario['trade_type'],
                    amount_usd=scenario['amount_usd'],
                    strategy=scenario['strategy'],
                    is_paper_trade=scenario['is_paper_trade']
                )
                
                if result.success:
                    print("✅ Optimization successful")
                    
                    if result.gas_price:
                        gas_price = result.gas_price
                        print(f"   💰 Strategy: {gas_price.strategy.value}")
                        print(f"   ⛽ Max Fee: {gas_price.max_fee_per_gas_gwei} gwei")
                        print(f"   ⚡ Priority Fee: {gas_price.max_priority_fee_per_gas_gwei} gwei")
                        print(f"   💵 Estimated Cost: ${gas_price.estimated_cost_usd}")
                        print(f"   💸 Savings: {gas_price.cost_savings_percent}%")
                        print(f"   ⏱️  Confirmation Time: {gas_price.expected_confirmation_time_ms}ms")
                        print(f"   📊 Network: {gas_price.network_congestion.value}")
                        
                        if result.fallback_used:
                            print("   ⚠️  Used fallback pricing")
                    
                    # Print console output
                    if result.console_output:
                        print("\n   📺 Console Output:")
                        for line in result.console_output.split('\n'):
                            print(f"   {line}")
                else:
                    print(f"❌ Optimization failed: {result.error_message}")
                
            except Exception as e:
                print(f"❌ Test failed with exception: {e}")
            
            print()
            await asyncio.sleep(1)  # Brief pause between tests
        
        print("\n" + "=" * 60)
        print("📈 PERFORMANCE STATISTICS")
        print("=" * 60)
        
        stats = optimizer.get_performance_stats()
        print(f"📊 Total Optimizations: {stats['optimization_count']}")
        print(f"💰 Total Cost Savings: ${stats['cost_savings_total_usd']:.2f}")
        print(f"🚨 Emergency Stops: {stats['emergency_stops_triggered']}")
        print(f"🌐 Active Chains: {stats['initialized_chains']}")
        print(f"⏰ Last Activity: {stats['last_console_output']}")
        print(f"🟢 Status: {'Active' if stats['active'] else 'Inactive'}")
        
        print("\n" + "=" * 60)
        print("📝 RECENT CONSOLE OUTPUT")
        print("=" * 60)
        
        console_output = optimizer.get_console_output(last_n=15)
        for line in console_output:
            print(line)
        
        print("\n" + "=" * 60)
        print("🧪 EMERGENCY STOP TEST")
        print("=" * 60)
        
        print("🚨 Testing emergency stop functionality...")
        await optimizer.emergency_stop_all_chains("Test emergency stop")
        print("✅ Emergency stop test completed")
        
        await asyncio.sleep(2)
        
        print("\n" + "=" * 80)
        print("✅ GAS OPTIMIZER TESTING COMPLETED SUCCESSFULLY")
        print("=" * 80)
        
        # Final console output
        final_output = optimizer.get_console_output(last_n=5)
        print("\n📺 Final Console Output:")
        for line in final_output:
            print(line)
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


async def continuous_monitoring_demo():
    """Demonstrate continuous gas monitoring with live updates."""
    print("\n" + "=" * 80)
    print("📊 CONTINUOUS MONITORING DEMO (30 seconds)")
    print("=" * 80)
    
    try:
        from trading.services.gas_optimizer import get_gas_optimizer
        
        optimizer = await get_gas_optimizer()
        
        print("🔄 Starting continuous monitoring... (Watch for live updates)")
        print("💡 This simulates real trading conditions with periodic gas checks")
        
        # Run monitoring for 30 seconds with periodic test trades
        for i in range(6):  # 6 iterations x 5 seconds = 30 seconds
            await asyncio.sleep(5)
            
            # Simulate a trade optimization every 5 seconds
            test_amount = Decimal(str(100 + (i * 200)))  # Varying amounts
            chain_id = 1 if i % 2 == 0 else 8453  # Alternate chains
            
            print(f"\n⚡ Simulating trade #{i+1} on chain {chain_id}")
            
            from trading.services.gas_optimizer import optimize_trade_gas
            result = await optimize_trade_gas(
                chain_id=chain_id,
                trade_type='buy',
                amount_usd=test_amount,
                strategy='balanced',
                is_paper_trade=True
            )
            
            if result.success and result.gas_price:
                print(f"   💰 Optimized: {result.gas_price.max_fee_per_gas_gwei} gwei")
            
        print("\n✅ Continuous monitoring demo completed")
        
    except Exception as e:
        print(f"❌ Monitoring demo failed: {e}")


if __name__ == '__main__':
    print("🚀 Starting Django Gas Optimizer Test Suite...")
    
    # Run main tests
    asyncio.run(test_gas_optimizer())
    
    # Run continuous monitoring demo
    asyncio.run(continuous_monitoring_demo())
    
    print("\n🎉 All tests completed! Check console output above for live gas optimization data.")