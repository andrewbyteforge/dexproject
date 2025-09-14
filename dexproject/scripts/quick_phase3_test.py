#!/usr/bin/env python3
"""
Quick Phase 3 Test Script

This is a simplified test to validate the basic functionality
of your Phase 3 mempool integration without complex setup.

Run this from your dexproject directory:
    python scripts/quick_phase3_test.py

File: dexproject/scripts/quick_phase3_test.py
"""

import sys
import asyncio
import logging
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure simple logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

async def test_imports():
    """Test that all Phase 3 components can be imported."""
    print("Testing imports...")
    
    try:
        # Test core imports
        from engine.mempool.monitor import MempoolMonitor, MempoolProvider
        from engine.mempool.protection import MEVProtectionEngine, MEVThreatType
        from engine.mempool.relay import PrivateRelayManager, RelayType
        from engine.config import get_config
        
        print("✅ All imports successful")
        return True
        
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

async def test_basic_initialization():
    """Test basic component initialization."""
    print("\nTesting component initialization...")
    
    try:
        from engine.config import get_config
        from engine.mempool.monitor import MempoolMonitor
        from engine.mempool.protection import MEVProtectionEngine
        from engine.mempool.relay import PrivateRelayManager
        
        # Get configuration
        config = await get_config()
        print(f"✅ Config loaded: {len(config.chain_configs)} chains configured")
        
        # Test relay manager
        relay_manager = PrivateRelayManager(config)
        await relay_manager.initialize()
        print("✅ Relay manager initialized")
        
        # Test MEV engine
        mev_engine = MEVProtectionEngine(config)
        await mev_engine.initialize(relay_manager)
        print("✅ MEV engine initialized")
        
        # Test monitor (don't start actual connections)
        monitor = MempoolMonitor(config)
        print("✅ Monitor created")
        
        # Cleanup
        await mev_engine.shutdown()
        await relay_manager.shutdown()
        print("✅ Components cleaned up")
        
        return True
        
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        return False

async def test_websocket_url_generation():
    """Test WebSocket URL generation."""
    print("\nTesting WebSocket URL generation...")
    
    try:
        from engine.config import get_config
        from engine.mempool.monitor import MempoolMonitor, MempoolProvider
        
        config = await get_config()
        monitor = MempoolMonitor(config)
        
        # Test URL generation for different providers and chains
        test_cases = [
            (1, MempoolProvider.ALCHEMY),      # Ethereum mainnet
            (8453, MempoolProvider.ALCHEMY),   # Base mainnet
        ]
        
        for chain_id, provider in test_cases:
            try:
                url = monitor._get_websocket_url(chain_id, provider)
                print(f"✅ {provider.value} chain {chain_id}: {url[:50]}...")
            except Exception as e:
                print(f"⚠️  {provider.value} chain {chain_id}: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ WebSocket URL test failed: {e}")
        return False

async def test_mev_analysis():
    """Test MEV analysis functionality."""
    print("\nTesting MEV analysis...")
    
    try:
        from engine.config import get_config
        from engine.mempool.protection import MEVProtectionEngine, PendingTransaction
        from engine.mempool.relay import PrivateRelayManager
        from datetime import datetime
        from decimal import Decimal
        
        # Initialize components
        config = await get_config()
        relay_manager = PrivateRelayManager(config)
        await relay_manager.initialize()
        
        mev_engine = MEVProtectionEngine(config)
        await mev_engine.initialize(relay_manager)
        
        # Create test transaction
        test_tx = PendingTransaction(
            hash="0xtest123456789",
            from_address="0x742d35Cc4Bf8b5263F84e3fb527f5b4aF38877B6",
            to_address="0xE592427A0AEce92De3Edee1F18E0157C05861564",  # Uniswap V3
            value=Decimal("1000000000000000000"),  # 1 ETH
            gas_price=Decimal("25000000000"),      # 25 gwei
            gas_limit=200000,
            nonce=42,
            data="0x414bf389",  # exactInputSingle
            timestamp=datetime.utcnow(),
            is_dex_interaction=True
        )
        
        # Test MEV analysis
        analysis = await mev_engine.analyze_pending_transaction(test_tx)
        
        if analysis:
            print(f"✅ MEV analysis completed")
            print(f"   Threats detected: {len(analysis.threats)}")
            print(f"   Recommendation: {analysis.recommendation.action.value}")
            print(f"   Analysis time: {analysis.analysis_time_ms:.2f}ms")
        else:
            print("⚠️  No analysis result returned")
        
        # Get statistics
        stats = mev_engine.get_protection_statistics()
        print(f"✅ MEV engine statistics: {stats}")
        
        # Cleanup
        await mev_engine.shutdown()
        await relay_manager.shutdown()
        
        return True
        
    except Exception as e:
        print(f"❌ MEV analysis test failed: {e}")
        return False

async def test_relay_configuration():
    """Test relay configuration and selection."""
    print("\nTesting relay configuration...")
    
    try:
        from engine.config import get_config
        from engine.mempool.relay import PrivateRelayManager, PriorityLevel
        
        config = await get_config()
        relay_manager = PrivateRelayManager(config)
        await relay_manager.initialize()
        
        # Test relay configs
        configs = relay_manager.get_relay_configs()
        print(f"✅ Relay configs: {list(configs.keys())}")
        
        # Test relay selection
        for priority in [PriorityLevel.CRITICAL, PriorityLevel.HIGH, PriorityLevel.MEDIUM]:
            selected = relay_manager._select_optimal_relay(priority)
            if selected:
                print(f"✅ Priority {priority.value} -> {selected.name}")
            else:
                print(f"⚠️  No relay for priority {priority.value}")
        
        # Test performance metrics
        metrics = relay_manager.get_performance_metrics()
        print(f"✅ Relay metrics: {metrics}")
        
        await relay_manager.shutdown()
        return True
        
    except Exception as e:
        print(f"❌ Relay test failed: {e}")
        return False

async def main():
    """Run all quick tests."""
    print("=" * 60)
    print("QUICK PHASE 3 INTEGRATION TEST")
    print("=" * 60)
    
    tests = [
        ("Import Test", test_imports),
        ("Initialization Test", test_basic_initialization),
        ("WebSocket URL Test", test_websocket_url_generation),
        ("MEV Analysis Test", test_mev_analysis),
        ("Relay Configuration Test", test_relay_configuration),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🧪 Running {test_name}...")
        try:
            result = await test_func()
            results.append(result)
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append(False)
    
    # Summary
    passed = sum(results)
    total = len(results)
    success_rate = (passed / total) * 100
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Tests passed: {passed}/{total} ({success_rate:.1f}%)")
    
    if success_rate == 100:
        print("🎉 ALL TESTS PASSED! Phase 3 components are working correctly.")
    elif success_rate >= 80:
        print("⚠️  Most tests passed. Minor issues may need attention.")
    else:
        print("❌ Multiple test failures. Check your implementation.")
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)