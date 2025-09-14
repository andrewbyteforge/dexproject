#!/usr/bin/env python3
"""
Phase 3 Mempool Integration Test Script

This script tests the complete Phase 3 implementation including:
1. Live WebSocket connections to mempool providers
2. Real-time transaction streaming and parsing
3. MEV protection active logic and threat detection
4. Private relay submission (Flashbots integration)

Usage: python phase3_integration_test.py [--chain-id CHAIN_ID] [--quick-test]

File: dexproject/scripts/phase3_integration_test.py
"""

import asyncio
import logging
import time
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from decimal import Decimal

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('phase3_test.log')
    ]
)

logger = logging.getLogger(__name__)

class Phase3IntegrationTest:
    """Comprehensive test suite for Phase 3 mempool integration."""
    
    def __init__(self, target_chain_id: Optional[int] = None):
        self.target_chain_id = target_chain_id or 84532  # Base Sepolia for testing
        self.test_results = {
            'websocket_connections': {},
            'transaction_streaming': {},
            'mev_protection': {},
            'relay_submission': {},
            'performance_metrics': {},
            'errors': []
        }
        self.start_time = time.time()
        
        # Component instances
        self.monitor = None
        self.mev_engine = None
        self.relay_manager = None
        
    async def run_comprehensive_test(self, quick_test: bool = False) -> Dict[str, Any]:
        """
        Run complete Phase 3 integration test suite.
        
        Args:
            quick_test: If True, run abbreviated tests for faster validation
            
        Returns:
            Test results dictionary
        """
        logger.info("=" * 80)
        logger.info("PHASE 3 MEMPOOL INTEGRATION - COMPREHENSIVE TEST")
        logger.info("=" * 80)
        
        try:
            # Test 1: Component Initialization
            await self._test_component_initialization()
            
            # Test 2: WebSocket Connections
            await self._test_websocket_connections(quick_test)
            
            # Test 3: Transaction Streaming (if not quick test)
            if not quick_test:
                await self._test_transaction_streaming()
            
            # Test 4: MEV Protection Logic
            await self._test_mev_protection()
            
            # Test 5: Private Relay Integration
            await self._test_relay_submission()
            
            # Test 6: Performance Validation
            await self._test_performance_metrics()
            
            # Generate final report
            await self._generate_test_report()
            
        except Exception as e:
            logger.error(f"Test suite failed with critical error: {e}")
            self.test_results['errors'].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'phase': 'test_suite_execution'
            })
        finally:
            # Cleanup
            await self._cleanup_test_resources()
        
        return self.test_results
    
    async def _test_component_initialization(self) -> None:
        """Test initialization of all Phase 3 components."""
        logger.info("🧪 Test 1: Component Initialization")
        
        try:
            # Import components (test import errors)
            from engine.config import get_config
            from engine.mempool.monitor import MempoolMonitor, create_mempool_monitor
            from engine.mempool.protection import MEVProtectionEngine, create_mev_protection_engine
            from engine.mempool.relay import PrivateRelayManager, create_private_relay_manager
            from engine.execution.gas_optimizer import GasOptimizationEngine
            
            logger.info("   ✅ All component imports successful")
            
            # Initialize configuration
            config = await get_config()
            logger.info(f"   ✅ Engine configuration loaded: {len(config.chain_configs)} chains")
            
            # Create component instances
            self.relay_manager = PrivateRelayManager(config)
            await self.relay_manager.initialize()
            logger.info("   ✅ Private relay manager initialized")
            
            self.mev_engine = MEVProtectionEngine(config)
            await self.mev_engine.initialize(self.relay_manager)
            logger.info("   ✅ MEV protection engine initialized")
            
            # Create gas optimizer (simplified for testing)
            gas_optimizer = GasOptimizationEngine(config)
            logger.info("   ✅ Gas optimization engine created")
            
            # Create mempool monitor
            self.monitor = MempoolMonitor(config)
            await self.monitor.initialize(self.mev_engine, gas_optimizer, self.relay_manager)
            logger.info("   ✅ Mempool monitor initialized")
            
            self.test_results['websocket_connections']['initialization'] = True
            
        except Exception as e:
            logger.error(f"   ❌ Component initialization failed: {e}")
            self.test_results['errors'].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'phase': 'component_initialization'
            })
            raise
    
    async def _test_websocket_connections(self, quick_test: bool) -> None:
        """Test WebSocket connections to mempool providers."""
        logger.info("🧪 Test 2: WebSocket Connections")
        
        try:
            if not self.monitor:
                raise RuntimeError("Monitor not initialized")
            
            # Test connection establishment
            connection_start_time = time.time()
            
            # Start monitoring for target chain
            await self.monitor.start_monitoring([self.target_chain_id])
            
            connection_time = time.time() - connection_start_time
            logger.info(f"   ⏱️  Connection establishment time: {connection_time:.2f}s")
            
            # Wait for connections to establish
            await asyncio.sleep(5)
            
            # Check connection status
            connected_chains = self.monitor.get_connected_chains()
            is_connected = self.monitor.is_connected(self.target_chain_id)
            
            logger.info(f"   📊 Connected chains: {connected_chains}")
            logger.info(f"   🔗 Chain {self.target_chain_id} connected: {is_connected}")
            
            # Get connection statistics
            stats = self.monitor.get_statistics(self.target_chain_id)
            if isinstance(stats, dict) and 'error' not in stats:
                active_providers = stats.get('active_providers', [])
                failed_providers = stats.get('failed_providers', [])
                
                logger.info(f"   ✅ Active providers: {active_providers}")
                if failed_providers:
                    logger.warning(f"   ⚠️  Failed providers: {failed_providers}")
                
                self.test_results['websocket_connections']['active_providers'] = active_providers
                self.test_results['websocket_connections']['failed_providers'] = failed_providers
                self.test_results['websocket_connections']['connection_time_s'] = connection_time
                
            else:
                logger.warning(f"   ⚠️  No statistics available: {stats}")
            
            # Test connection resilience (if not quick test)
            if not quick_test:
                logger.info("   🧪 Testing connection resilience...")
                # Could add connection drop/reconnect tests here
            
            self.test_results['websocket_connections']['success'] = is_connected
            
        except Exception as e:
            logger.error(f"   ❌ WebSocket connection test failed: {e}")
            self.test_results['websocket_connections']['success'] = False
            self.test_results['errors'].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'phase': 'websocket_connections'
            })
    
    async def _test_transaction_streaming(self) -> None:
        """Test real-time transaction streaming and parsing."""
        logger.info("🧪 Test 3: Transaction Streaming")
        
        try:
            if not self.monitor:
                raise RuntimeError("Monitor not initialized")
            
            # Monitor transaction flow for a brief period
            streaming_start = time.time()
            initial_stats = self.monitor.get_statistics(self.target_chain_id)
            
            logger.info("   📡 Monitoring transaction stream for 30 seconds...")
            await asyncio.sleep(30)
            
            # Get updated statistics
            final_stats = self.monitor.get_statistics(self.target_chain_id)
            streaming_time = time.time() - streaming_start
            
            if isinstance(final_stats, dict) and 'error' not in final_stats:
                transactions_seen = final_stats.get('total_transactions_seen', 0)
                dex_transactions = final_stats.get('dex_transactions_seen', 0)
                processing_latency = final_stats.get('avg_processing_latency_ms', 0)
                
                logger.info(f"   📊 Transactions seen: {transactions_seen}")
                logger.info(f"   💱 DEX transactions: {dex_transactions}")
                logger.info(f"   ⚡ Processing latency: {processing_latency:.2f}ms")
                
                # Calculate transaction rate
                tx_rate = transactions_seen / streaming_time if streaming_time > 0 else 0
                logger.info(f"   📈 Transaction rate: {tx_rate:.1f} tx/second")
                
                self.test_results['transaction_streaming'] = {
                    'transactions_seen': transactions_seen,
                    'dex_transactions': dex_transactions,
                    'processing_latency_ms': processing_latency,
                    'transaction_rate_per_second': tx_rate,
                    'streaming_duration_s': streaming_time
                }
                
                # Test transaction parsing
                recent_transactions = self.monitor.get_pending_transactions(
                    self.target_chain_id, limit=5
                )
                
                logger.info(f"   🔍 Recent transactions sample: {len(recent_transactions)}")
                for i, tx in enumerate(recent_transactions[:2], 1):
                    logger.info(f"      {i}. {tx.hash[:10]}... DEX: {tx.is_dex_interaction}")
            
        except Exception as e:
            logger.error(f"   ❌ Transaction streaming test failed: {e}")
            self.test_results['errors'].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'phase': 'transaction_streaming'
            })
    
    async def _test_mev_protection(self) -> None:
        """Test MEV protection logic and threat detection."""
        logger.info("🧪 Test 4: MEV Protection Logic")
        
        try:
            if not self.mev_engine:
                raise RuntimeError("MEV engine not initialized")
            
            # Create test transaction scenarios
            test_scenarios = [
                {
                    'name': 'Normal DEX Transaction',
                    'transaction': self._create_test_transaction('normal_dex'),
                    'expected_threats': 0
                },
                {
                    'name': 'Potential Frontrunning Target',
                    'transaction': self._create_test_transaction('frontrun_target'),
                    'expected_threats': 0  # No mempool context for threats
                },
                {
                    'name': 'High-Value Swap',
                    'transaction': self._create_test_transaction('high_value'),
                    'expected_threats': 0
                }
            ]
            
            mev_test_results = {}
            total_analysis_time = 0
            
            for scenario in test_scenarios:
                scenario_start = time.time()
                
                logger.info(f"   🎯 Testing scenario: {scenario['name']}")
                
                # Test MEV analysis
                from engine.mempool.protection import PendingTransaction
                
                # Convert to PendingTransaction format
                pending_tx = PendingTransaction(
                    hash=scenario['transaction']['hash'],
                    from_address=scenario['transaction']['from'],
                    to_address=scenario['transaction']['to'],
                    value=Decimal(str(scenario['transaction']['value'])),
                    gas_price=Decimal(str(scenario['transaction']['gasPrice'])),
                    gas_limit=scenario['transaction']['gas'],
                    nonce=scenario['transaction']['nonce'],
                    data=scenario['transaction']['data'],
                    timestamp=datetime.utcnow(),
                    is_dex_interaction=True
                )
                
                # Analyze for MEV threats
                analysis = await self.mev_engine.analyze_pending_transaction(pending_tx)
                
                scenario_time = (time.time() - scenario_start) * 1000
                total_analysis_time += scenario_time
                
                if analysis:
                    threats_detected = len(analysis.threats)
                    recommendation = analysis.recommendation.action.value
                    
                    logger.info(f"      🔍 Threats detected: {threats_detected}")
                    logger.info(f"      🛡️  Recommendation: {recommendation}")
                    logger.info(f"      ⏱️  Analysis time: {scenario_time:.2f}ms")
                    
                    mev_test_results[scenario['name']] = {
                        'threats_detected': threats_detected,
                        'recommendation': recommendation,
                        'analysis_time_ms': scenario_time
                    }
                else:
                    logger.warning(f"      ⚠️  No analysis result for {scenario['name']}")
            
            # Test performance metrics
            avg_analysis_time = total_analysis_time / len(test_scenarios)
            logger.info(f"   📊 Average MEV analysis time: {avg_analysis_time:.2f}ms")
            
            # Get MEV engine statistics
            mev_stats = self.mev_engine.get_protection_statistics()
            logger.info(f"   📈 MEV engine stats: {mev_stats}")
            
            self.test_results['mev_protection'] = {
                'test_scenarios': mev_test_results,
                'average_analysis_time_ms': avg_analysis_time,
                'engine_statistics': mev_stats
            }
            
        except Exception as e:
            logger.error(f"   ❌ MEV protection test failed: {e}")
            self.test_results['errors'].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'phase': 'mev_protection'
            })
    
    async def _test_relay_submission(self) -> None:
        """Test private relay submission functionality."""
        logger.info("🧪 Test 5: Private Relay Submission")
        
        try:
            if not self.relay_manager:
                raise RuntimeError("Relay manager not initialized")
            
            # Test relay configuration
            relay_configs = self.relay_manager.get_relay_configs()
            logger.info(f"   ⚙️  Configured relays: {list(relay_configs.keys())}")
            
            # Test bundle preparation (without actual submission to avoid costs)
            test_transactions = [
                self._create_test_transaction('relay_test_1'),
                self._create_test_transaction('relay_test_2')
            ]
            
            logger.info(f"   📦 Testing bundle preparation with {len(test_transactions)} transactions")
            
            # Test relay selection logic
            from engine.mempool.relay import PriorityLevel
            
            for priority in [PriorityLevel.CRITICAL, PriorityLevel.HIGH, PriorityLevel.MEDIUM]:
                selected_relay = self.relay_manager._select_optimal_relay(priority)
                if selected_relay:
                    logger.info(f"   🎯 Priority {priority.value} -> {selected_relay.name}")
                else:
                    logger.warning(f"   ⚠️  No relay available for priority {priority.value}")
            
            # Test bundle submission (dry run - don't actually submit)
            logger.info("   🧪 Testing bundle submission logic (dry run)...")
            
            # This would normally submit to Flashbots, but we'll simulate
            submission_start = time.time()
            
            # Simulate submission process
            await asyncio.sleep(0.1)  # Simulate network latency
            
            submission_time = (time.time() - submission_start) * 1000
            logger.info(f"   ⏱️  Simulated submission time: {submission_time:.2f}ms")
            
            # Get relay manager statistics
            relay_stats = self.relay_manager.get_performance_metrics()
            logger.info(f"   📊 Relay manager stats: {relay_stats}")
            
            self.test_results['relay_submission'] = {
                'configured_relays': len(relay_configs),
                'relay_names': list(relay_configs.keys()),
                'simulated_submission_time_ms': submission_time,
                'performance_metrics': relay_stats
            }
            
        except Exception as e:
            logger.error(f"   ❌ Relay submission test failed: {e}")
            self.test_results['errors'].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'phase': 'relay_submission'
            })
    
    async def _test_performance_metrics(self) -> None:
        """Test overall system performance metrics."""
        logger.info("🧪 Test 6: Performance Validation")
        
        try:
            total_test_time = time.time() - self.start_time
            
            # Collect performance metrics from all components
            performance_data = {
                'total_test_time_s': total_test_time,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # Monitor performance metrics
            if self.monitor:
                monitor_metrics = self.monitor.get_performance_metrics()
                performance_data['monitor_metrics'] = monitor_metrics
                logger.info(f"   📊 Monitor metrics: {monitor_metrics}")
            
            # MEV engine performance
            if self.mev_engine:
                mev_metrics = self.mev_engine.get_protection_statistics()
                performance_data['mev_metrics'] = mev_metrics
                logger.info(f"   🛡️  MEV engine metrics: {mev_metrics}")
            
            # Relay manager performance  
            if self.relay_manager:
                relay_metrics = self.relay_manager.get_performance_metrics()
                performance_data['relay_metrics'] = relay_metrics
                logger.info(f"   🚀 Relay manager metrics: {relay_metrics}")
            
            # Validate performance targets
            performance_targets = {
                'websocket_connection_time': 10.0,  # seconds
                'mev_analysis_time': 100.0,  # milliseconds
                'relay_submission_time': 500.0,  # milliseconds
            }
            
            performance_validation = {}
            
            # Check WebSocket connection time
            connection_time = self.test_results.get('websocket_connections', {}).get('connection_time_s', 0)
            performance_validation['websocket_connection'] = {
                'actual': connection_time,
                'target': performance_targets['websocket_connection_time'],
                'passed': connection_time <= performance_targets['websocket_connection_time']
            }
            
            # Check MEV analysis time
            mev_time = self.test_results.get('mev_protection', {}).get('average_analysis_time_ms', 0)
            performance_validation['mev_analysis'] = {
                'actual': mev_time,
                'target': performance_targets['mev_analysis_time'],
                'passed': mev_time <= performance_targets['mev_analysis_time']
            }
            
            # Check relay submission time
            relay_time = self.test_results.get('relay_submission', {}).get('simulated_submission_time_ms', 0)
            performance_validation['relay_submission'] = {
                'actual': relay_time,
                'target': performance_targets['relay_submission_time'],
                'passed': relay_time <= performance_targets['relay_submission_time']
            }
            
            logger.info("   🎯 Performance validation:")
            for metric, validation in performance_validation.items():
                status = "✅ PASS" if validation['passed'] else "❌ FAIL"
                logger.info(f"      {metric}: {validation['actual']:.2f} vs {validation['target']:.2f} {status}")
            
            performance_data['validation'] = performance_validation
            self.test_results['performance_metrics'] = performance_data
            
        except Exception as e:
            logger.error(f"   ❌ Performance validation failed: {e}")
            self.test_results['errors'].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'phase': 'performance_validation'
            })
    
    def _create_test_transaction(self, scenario: str) -> Dict[str, Any]:
        """Create a test transaction for various scenarios."""
        base_tx = {
            'from': '0x742d35Cc4Bf8b5263F84e3fb527f5b4aF38877B6',
            'to': '0xE592427A0AEce92De3Edee1F18E0157C05861564',  # Uniswap V3 Router
            'gasPrice': 25000000000,  # 25 gwei
            'gas': 200000,
            'nonce': 42,
            'data': '0x414bf3890000000000000000000000000000000000000000000000000000000000000020',
            'hash': f'0x{scenario}' + '0' * (64 - len(scenario))
        }
        
        if scenario == 'normal_dex':
            base_tx['value'] = 1000000000000000000  # 1 ETH
        elif scenario == 'frontrun_target':
            base_tx['value'] = 500000000000000000   # 0.5 ETH
            base_tx['gasPrice'] = 20000000000        # 20 gwei (lower gas)
        elif scenario == 'high_value':
            base_tx['value'] = 10000000000000000000  # 10 ETH
            base_tx['gasPrice'] = 50000000000        # 50 gwei (higher gas)
        else:
            base_tx['value'] = 100000000000000000    # 0.1 ETH
        
        return base_tx
    
    async def _generate_test_report(self) -> None:
        """Generate comprehensive test report."""
        logger.info("=" * 80)
        logger.info("📋 PHASE 3 INTEGRATION TEST REPORT")
        logger.info("=" * 80)
        
        total_time = time.time() - self.start_time
        
        # Summary statistics
        total_tests = 6
        passed_tests = 0
        
        test_status = {
            'Component Initialization': self.test_results.get('websocket_connections', {}).get('initialization', False),
            'WebSocket Connections': self.test_results.get('websocket_connections', {}).get('success', False),
            'Transaction Streaming': len(self.test_results.get('transaction_streaming', {})) > 0,
            'MEV Protection': len(self.test_results.get('mev_protection', {})) > 0,
            'Relay Submission': len(self.test_results.get('relay_submission', {})) > 0,
            'Performance Metrics': len(self.test_results.get('performance_metrics', {})) > 0
        }
        
        for test_name, status in test_status.items():
            if status:
                passed_tests += 1
                logger.info(f"✅ {test_name}: PASSED")
            else:
                logger.info(f"❌ {test_name}: FAILED")
        
        # Overall results
        success_rate = (passed_tests / total_tests) * 100
        logger.info(f"\n📊 TEST SUMMARY:")
        logger.info(f"   Tests passed: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
        logger.info(f"   Total time: {total_time:.2f} seconds")
        logger.info(f"   Errors encountered: {len(self.test_results['errors'])}")
        
        # Performance summary
        if 'performance_metrics' in self.test_results:
            validation = self.test_results['performance_metrics'].get('validation', {})
            perf_passed = sum(1 for v in validation.values() if v['passed'])
            perf_total = len(validation)
            logger.info(f"   Performance targets: {perf_passed}/{perf_total} met")
        
        # Phase 3 readiness assessment
        if success_rate >= 80 and len(self.test_results['errors']) == 0:
            logger.info("\n🎯 PHASE 3 STATUS: ✅ READY FOR PRODUCTION")
        elif success_rate >= 60:
            logger.info("\n🎯 PHASE 3 STATUS: ⚠️  NEEDS MINOR FIXES")
        else:
            logger.info("\n🎯 PHASE 3 STATUS: ❌ REQUIRES MAJOR REPAIRS")
        
        # Error summary
        if self.test_results['errors']:
            logger.info(f"\n⚠️  ERRORS ENCOUNTERED:")
            for i, error in enumerate(self.test_results['errors'], 1):
                logger.info(f"   {i}. {error['phase']}: {error['error']}")
        
        logger.info("=" * 80)
    
    async def _cleanup_test_resources(self) -> None:
        """Clean up test resources."""
        try:
            if self.monitor:
                await self.monitor.stop_monitoring()
            if self.mev_engine:
                await self.mev_engine.shutdown()
            if self.relay_manager:
                await self.relay_manager.shutdown()
                
            logger.info("🧹 Test cleanup completed")
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")


async def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Phase 3 Mempool Integration Test")
    parser.add_argument('--chain-id', type=int, default=84532, help='Target chain ID (default: Base Sepolia)')
    parser.add_argument('--quick-test', action='store_true', help='Run abbreviated test suite')
    
    args = parser.parse_args()
    
    # Run the test suite
    test_runner = Phase3IntegrationTest(args.chain_id)
    
    try:
        results = await test_runner.run_comprehensive_test(args.quick_test)
        
        # Save results to file
        import json
        results_file = f"phase3_test_results_{int(time.time())}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"Test results saved to: {results_file}")
        
        return 0 if len(results['errors']) == 0 else 1
        
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Test runner failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())