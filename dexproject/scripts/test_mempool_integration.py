#!/usr/bin/env python3
"""
Mempool Integration Validation Script

This script validates the mempool monitoring and analysis components by:
1. Testing WebSocket connections to configured RPC providers
2. Streaming live mempool transactions and showing analysis results
3. Measuring performance against Fast Lane SLA requirements
4. Providing clear diagnostics and recommendations

Usage:
    python scripts/test_mempool_integration.py [options]
    
Options:
    --duration SECONDS     Test duration (default: 60)
    --chain-id CHAIN_ID    Test specific chain (default: test all)
    --verbose              Show detailed transaction analysis
    --demo-mode            Use demo API keys for testing
    --save-results         Save test results to file

Path: scripts/test_mempool_integration.py
"""

import asyncio
import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import asdict

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import Django setup
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

# Import engine components
from engine.mempool import (
    create_mempool_monitor,
    create_mempool_analyzer,
    MempoolEventType,
    MempoolTransaction,
    TransactionAnalysis,
    TransactionType,
    RiskFlag
)
from engine.utils import ProviderManager
from engine.config import get_config
from shared.chain_config_bridge import get_engine_chain_configs


class MempoolTester:
    """
    Comprehensive mempool integration tester.
    
    Tests all aspects of mempool monitoring and analysis to validate
    Fast Lane readiness and performance characteristics.
    """
    
    def __init__(self, test_duration: int = 60, verbose: bool = False, demo_mode: bool = False):
        """
        Initialize mempool tester.
        
        Args:
            test_duration: Test duration in seconds
            verbose: Enable verbose output
            demo_mode: Use demo API keys
        """
        self.test_duration = test_duration
        self.verbose = verbose
        self.demo_mode = demo_mode
        
        # Test components
        self.monitor = None
        self.analyzer = None
        self.provider_manager = None
        self.chain_configs = {}
        
        # Test results
        self.test_results = {
            'start_time': None,
            'end_time': None,
            'duration_seconds': 0,
            'connections': {},
            'transactions': [],
            'analysis_results': [],
            'performance_metrics': {},
            'errors': [],
            'summary': {}
        }
        
        # Real-time statistics
        self.stats = {
            'connections_attempted': 0,
            'connections_successful': 0,
            'transactions_received': 0,
            'transactions_analyzed': 0,
            'analysis_errors': 0,
            'dex_transactions': 0,
            'opportunities_found': 0,
            'average_analysis_time_ms': 0.0,
            'max_analysis_time_ms': 0.0,
            'sla_violations': 0,  # Analysis time > 300ms
        }
        
        # Setup logging
        self.setup_logging()
        self.logger = logging.getLogger('mempool_tester')
    
    def setup_logging(self) -> None:
        """Setup colored logging for better readability."""
        # Create custom formatter with colors
        class ColoredFormatter(logging.Formatter):
            """Custom formatter with colors for different log levels."""
            
            COLORS = {
                'DEBUG': '\033[36m',    # Cyan
                'INFO': '\033[32m',     # Green  
                'WARNING': '\033[33m',  # Yellow
                'ERROR': '\033[31m',    # Red
                'CRITICAL': '\033[35m', # Magenta
                'RESET': '\033[0m'      # Reset
            }
            
            def format(self, record):
                # Add color to levelname
                color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
                record.levelname = f"{color}{record.levelname}{self.COLORS['RESET']}"
                return super().format(record)
        
        # Configure logging
        logging.basicConfig(
            level=logging.DEBUG if self.verbose else logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Apply colored formatter to console handler
        for handler in logging.root.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setFormatter(ColoredFormatter('%(asctime)s [%(levelname)s] %(message)s'))
    
    async def run_comprehensive_test(self, target_chain_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Run comprehensive mempool integration test.
        
        Args:
            target_chain_id: Optional chain ID to test specifically
            
        Returns:
            Test results dictionary
        """
        self.logger.info("🚀 Starting Mempool Integration Validation")
        self.logger.info("=" * 80)
        
        self.test_results['start_time'] = datetime.now(timezone.utc)
        
        try:
            # Phase 1: Configuration and Setup
            await self._test_configuration_loading()
            
            # Phase 2: Provider Connection Testing
            await self._test_provider_connections(target_chain_id)
            
            # Phase 3: Mempool Monitor Testing
            await self._test_mempool_monitoring(target_chain_id)
            
            # Phase 4: Live Transaction Analysis
            await self._test_live_analysis()
            
            # Phase 5: Performance Validation
            self._validate_performance_requirements()
            
            # Generate final report
            self._generate_test_report()
            
        except Exception as e:
            self.logger.error(f"❌ Test failed with error: {e}")
            self.test_results['errors'].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'phase': 'test_execution'
            })
        
        finally:
            await self._cleanup()
            self.test_results['end_time'] = datetime.now(timezone.utc)
            self.test_results['duration_seconds'] = (
                self.test_results['end_time'] - self.test_results['start_time']
            ).total_seconds()
        
        return self.test_results
    
    async def _test_configuration_loading(self) -> None:
        """Test configuration loading from Django."""
        self.logger.info("🔧 Phase 1: Configuration Loading")
        
        try:
            # Load engine configuration
            config = await get_config()
            self.logger.info(f"✅ Engine configuration loaded")
            
            # Load chain configurations from Django
            self.chain_configs = await get_engine_chain_configs()
            self.logger.info(f"✅ Loaded configurations for {len(self.chain_configs)} chains")
            
            # Log available chains
            for chain_id, chain_config in self.chain_configs.items():
                providers_count = len(chain_config.rpc_providers)
                self.logger.info(f"   📡 {chain_config.name} (ID: {chain_id}): {providers_count} providers")
            
            self.test_results['connections']['config_loaded'] = True
            
        except Exception as e:
            self.logger.error(f"❌ Configuration loading failed: {e}")
            self.test_results['errors'].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'phase': 'configuration_loading'
            })
            raise
    
    async def _test_provider_connections(self, target_chain_id: Optional[int] = None) -> None:
        """Test RPC provider connections."""
        self.logger.info("🌐 Phase 2: Provider Connection Testing")
        
        test_chains = [target_chain_id] if target_chain_id else list(self.chain_configs.keys())
        
        for chain_id in test_chains:
            if chain_id not in self.chain_configs:
                self.logger.warning(f"⚠️  Chain {chain_id} not in configuration, skipping")
                continue
            
            chain_config = self.chain_configs[chain_id]
            self.logger.info(f"🔗 Testing {chain_config.name} (Chain {chain_id})")
            
            # Test each provider
            connection_results = {
                'chain_id': chain_id,
                'chain_name': chain_config.name,
                'providers': [],
                'websocket_endpoints': []
            }
            
            for i, provider in enumerate(chain_config.rpc_providers):
                self.stats['connections_attempted'] += 1
                
                provider_result = {
                    'name': provider.name,
                    'url': provider.url,
                    'http_connected': False,
                    'websocket_url': None,
                    'websocket_connected': False,
                    'latency_ms': None,
                    'error': None
                }
                
                try:
                    # Test HTTP connection
                    provider_manager = ProviderManager(chain_config)
                    w3 = await provider_manager.get_web3()
                    
                    if w3:
                        start_time = time.perf_counter()
                        block_number = w3.eth.block_number
                        latency = (time.perf_counter() - start_time) * 1000
                        
                        provider_result['http_connected'] = True
                        provider_result['latency_ms'] = latency
                        self.stats['connections_successful'] += 1
                        
                        self.logger.info(f"   ✅ {provider.name}: Block {block_number} ({latency:.1f}ms)")
                    
                    # Test WebSocket connection (if available)
                    ws_url = self._get_websocket_url(provider.url)
                    if ws_url:
                        provider_result['websocket_url'] = ws_url
                        ws_connected = await self._test_websocket_connection(ws_url)
                        provider_result['websocket_connected'] = ws_connected
                        
                        if ws_connected:
                            connection_results['websocket_endpoints'].append(ws_url)
                            self.logger.info(f"   🔌 WebSocket: {ws_url[:50]}... ✅")
                        else:
                            self.logger.warning(f"   🔌 WebSocket: {ws_url[:50]}... ❌")
                
                except Exception as e:
                    error_msg = str(e)
                    provider_result['error'] = error_msg
                    self.logger.error(f"   ❌ {provider.name}: {error_msg}")
                    self.test_results['errors'].append({
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'error': error_msg,
                        'phase': 'provider_connection',
                        'provider': provider.name,
                        'chain_id': chain_id
                    })
                
                connection_results['providers'].append(provider_result)
            
            self.test_results['connections'][chain_id] = connection_results
    
    def _get_websocket_url(self, http_url: str) -> Optional[str]:
        """Convert HTTP RPC URL to WebSocket URL."""
        if 'alchemy.com' in http_url:
            return http_url.replace('https://', 'wss://')
        elif 'ankr.com' in http_url:
            return http_url.replace('https://', 'wss://')
        elif 'infura.io' in http_url:
            return http_url.replace('https://', 'wss://')
        return None
    
    async def _test_websocket_connection(self, ws_url: str, timeout: float = 5.0) -> bool:
        """Test WebSocket connection."""
        try:
            import websockets
            async with websockets.connect(ws_url, timeout=timeout):
                return True
        except Exception:
            return False
    
    async def _test_mempool_monitoring(self, target_chain_id: Optional[int] = None) -> None:
        """Test mempool monitor initialization and connection."""
        self.logger.info("👁️  Phase 3: Mempool Monitor Testing")
        
        try:
            # Get a working chain configuration
            test_chain_config = None
            for chain_id, results in self.test_results['connections'].items():
                if isinstance(results, dict) and results.get('websocket_endpoints'):
                    test_chain_config = self.chain_configs[chain_id]
                    break
            
            if not test_chain_config:
                self.logger.warning("⚠️  No chains with WebSocket support found, using fallback")
                test_chain_config = list(self.chain_configs.values())[0]
            
            # Create provider manager
            self.provider_manager = ProviderManager(test_chain_config)
            
            # Create mempool monitor
            self.monitor = await create_mempool_monitor(
                self.provider_manager,
                event_callback=self._on_mempool_event
            )
            
            self.logger.info(f"✅ Mempool monitor created for {test_chain_config.name}")
            
            # Create analyzer
            self.analyzer = await create_mempool_analyzer(
                self.provider_manager,
                self.chain_configs
            )
            
            self.logger.info("✅ Mempool analyzer created")
            
        except Exception as e:
            self.logger.error(f"❌ Mempool monitor setup failed: {e}")
            self.test_results['errors'].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'phase': 'mempool_monitor_setup'
            })
            raise
    
    async def _test_live_analysis(self) -> None:
        """Test live mempool monitoring and analysis."""
        self.logger.info(f"📊 Phase 4: Live Transaction Analysis ({self.test_duration}s)")
        
        if not self.monitor or not self.analyzer:
            self.logger.error("❌ Monitor or analyzer not initialized")
            return
        
        try:
            # Start mempool monitoring
            await self.monitor.start_monitoring()
            self.logger.info("🎯 Mempool monitoring started - watching for transactions...")
            
            # Monitor for specified duration
            start_time = time.time()
            last_stats_time = start_time
            
            while time.time() - start_time < self.test_duration:
                await asyncio.sleep(1)
                
                # Log statistics every 10 seconds
                current_time = time.time()
                if current_time - last_stats_time >= 10:
                    self._log_progress_stats(current_time - start_time)
                    last_stats_time = current_time
            
            self.logger.info("⏱️  Test duration completed, stopping monitoring...")
            
        except Exception as e:
            self.logger.error(f"❌ Live analysis failed: {e}")
            self.test_results['errors'].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'phase': 'live_analysis'
            })
        finally:
            if self.monitor:
                await self.monitor.stop_monitoring()
    
    async def _on_mempool_event(self, event_type: MempoolEventType, transaction: MempoolTransaction) -> None:
        """Handle mempool events during testing."""
        try:
            if event_type == MempoolEventType.PENDING_TRANSACTION:
                self.stats['transactions_received'] += 1
                
                # Store transaction data (limit to prevent memory issues)
                if len(self.test_results['transactions']) < 100:
                    tx_data = {
                        'hash': transaction.hash,
                        'from': transaction.from_address,
                        'to': transaction.to_address,
                        'value_eth': transaction.value / 1e18,
                        'gas_price_gwei': transaction.gas_price / 1e9,
                        'chain_id': transaction.chain_id,
                        'timestamp': transaction.timestamp,
                        'age_seconds': transaction.age_seconds()
                    }
                    self.test_results['transactions'].append(tx_data)
                
                # Analyze transaction
                if self.analyzer:
                    analysis_start = time.perf_counter()
                    analysis = await self.analyzer.analyze_transaction(transaction)
                    analysis_time_ms = (time.perf_counter() - analysis_start) * 1000
                    
                    self.stats['transactions_analyzed'] += 1
                    
                    # Track analysis performance
                    if analysis_time_ms > self.stats['max_analysis_time_ms']:
                        self.stats['max_analysis_time_ms'] = analysis_time_ms
                    
                    # Update average analysis time
                    total_time = (self.stats['average_analysis_time_ms'] * (self.stats['transactions_analyzed'] - 1) + 
                                analysis_time_ms)
                    self.stats['average_analysis_time_ms'] = total_time / self.stats['transactions_analyzed']
                    
                    # Track SLA violations (>300ms analysis time)
                    if analysis_time_ms > 300:
                        self.stats['sla_violations'] += 1
                    
                    # Count DEX transactions
                    if analysis.transaction_type != TransactionType.NON_DEX:
                        self.stats['dex_transactions'] += 1
                    
                    # Count opportunities
                    if (analysis.is_front_run_opportunity or 
                        analysis.is_copy_trade_candidate or 
                        analysis.is_arbitrage_opportunity):
                        self.stats['opportunities_found'] += 1
                    
                    # Log interesting transactions
                    if (self.verbose or 
                        analysis.transaction_type != TransactionType.NON_DEX or
                        analysis.risk_score > 0.5):
                        
                        self._log_transaction_analysis(transaction, analysis, analysis_time_ms)
                    
                    # Store analysis results (limited)
                    if len(self.test_results['analysis_results']) < 50:
                        analysis_data = {
                            'transaction_hash': analysis.transaction_hash,
                            'transaction_type': analysis.transaction_type.value,
                            'risk_score': analysis.risk_score,
                            'risk_flags': [flag.value for flag in analysis.risk_flags],
                            'is_front_run_opportunity': analysis.is_front_run_opportunity,
                            'is_copy_trade_candidate': analysis.is_copy_trade_candidate,
                            'is_arbitrage_opportunity': analysis.is_arbitrage_opportunity,
                            'analysis_time_ms': analysis_time_ms,
                            'confidence_score': analysis.confidence_score
                        }
                        self.test_results['analysis_results'].append(analysis_data)
        
        except Exception as e:
            self.stats['analysis_errors'] += 1
            self.logger.error(f"Error processing mempool event: {e}")
    
    def _log_transaction_analysis(self, transaction: MempoolTransaction, analysis: TransactionAnalysis, analysis_time_ms: float) -> None:
        """Log interesting transaction analysis results."""
        # Create transaction summary
        tx_summary = f"{transaction.hash[:10]}..."
        
        # Add transaction details
        value_eth = transaction.value / 1e18
        gas_gwei = transaction.gas_price / 1e9
        
        details = []
        if value_eth > 0.01:
            details.append(f"Value: {value_eth:.3f} ETH")
        if gas_gwei > 50:
            details.append(f"Gas: {gas_gwei:.1f} gwei")
        
        # Add analysis results
        if analysis.transaction_type != TransactionType.NON_DEX:
            details.append(f"Type: {analysis.transaction_type.value}")
        
        if analysis.risk_score > 0.3:
            details.append(f"Risk: {analysis.risk_score:.2f}")
        
        if analysis.risk_flags:
            flags = [flag.value for flag in analysis.risk_flags]
            details.append(f"Flags: {', '.join(flags[:2])}")
        
        # Add opportunities
        opportunities = []
        if analysis.is_front_run_opportunity:
            opportunities.append("Front-run")
        if analysis.is_copy_trade_candidate:
            opportunities.append("Copy")
        if analysis.is_arbitrage_opportunity:
            opportunities.append("Arbitrage")
        
        if opportunities:
            details.append(f"Opportunities: {', '.join(opportunities)}")
        
        # Performance info
        sla_status = "✅" if analysis_time_ms <= 300 else "⚠️"
        details.append(f"Analysis: {analysis_time_ms:.1f}ms {sla_status}")
        
        # Log the transaction
        detail_str = " | ".join(details) if details else "Basic transaction"
        self.logger.info(f"   📝 {tx_summary}: {detail_str}")
    
    def _log_progress_stats(self, elapsed_seconds: float) -> None:
        """Log progress statistics during testing."""
        tx_rate = self.stats['transactions_received'] / max(elapsed_seconds, 1)
        analysis_rate = self.stats['transactions_analyzed'] / max(elapsed_seconds, 1)
        
        self.logger.info(f"⏱️  Progress ({elapsed_seconds:.0f}s): "
                        f"{self.stats['transactions_received']} tx received "
                        f"({tx_rate:.1f}/s), "
                        f"{self.stats['dex_transactions']} DEX tx, "
                        f"{self.stats['opportunities_found']} opportunities, "
                        f"Avg analysis: {self.stats['average_analysis_time_ms']:.1f}ms")
    
    def _validate_performance_requirements(self) -> None:
        """Validate performance against Fast Lane SLA requirements."""
        self.logger.info("⚡ Phase 5: Performance Validation")
        
        # Calculate performance metrics
        self.test_results['performance_metrics'] = {
            'total_transactions': self.stats['transactions_received'],
            'total_analyzed': self.stats['transactions_analyzed'],
            'dex_transactions': self.stats['dex_transactions'],
            'opportunities_found': self.stats['opportunities_found'],
            'analysis_errors': self.stats['analysis_errors'],
            'average_analysis_time_ms': round(self.stats['average_analysis_time_ms'], 2),
            'max_analysis_time_ms': round(self.stats['max_analysis_time_ms'], 2),
            'sla_violations': self.stats['sla_violations'],
            'sla_compliance_rate': 0.0
        }
        
        # Calculate SLA compliance
        if self.stats['transactions_analyzed'] > 0:
            compliance_rate = 1.0 - (self.stats['sla_violations'] / self.stats['transactions_analyzed'])
            self.test_results['performance_metrics']['sla_compliance_rate'] = round(compliance_rate, 3)
        
        # Log performance results
        metrics = self.test_results['performance_metrics']
        
        self.logger.info(f"📊 Performance Results:")
        self.logger.info(f"   Transactions processed: {metrics['total_transactions']}")
        self.logger.info(f"   Transactions analyzed: {metrics['total_analyzed']}")
        self.logger.info(f"   DEX transactions: {metrics['dex_transactions']}")
        self.logger.info(f"   Opportunities found: {metrics['opportunities_found']}")
        self.logger.info(f"   Average analysis time: {metrics['average_analysis_time_ms']:.1f}ms")
        self.logger.info(f"   Maximum analysis time: {metrics['max_analysis_time_ms']:.1f}ms")
        self.logger.info(f"   SLA violations (>300ms): {metrics['sla_violations']}")
        self.logger.info(f"   SLA compliance rate: {metrics['sla_compliance_rate']*100:.1f}%")
        
        # Performance assessment
        if metrics['average_analysis_time_ms'] <= 300:
            self.logger.info("   ✅ Average analysis time meets Fast Lane SLA")
        else:
            self.logger.warning("   ⚠️  Average analysis time exceeds Fast Lane SLA")
        
        if metrics['sla_compliance_rate'] >= 0.95:
            self.logger.info("   ✅ SLA compliance rate acceptable (≥95%)")
        else:
            self.logger.warning("   ⚠️  SLA compliance rate needs improvement")
    
    def _generate_test_report(self) -> None:
        """Generate final test report summary."""
        self.logger.info("=" * 80)
        self.logger.info("📋 MEMPOOL INTEGRATION TEST REPORT")
        self.logger.info("=" * 80)
        
        # Connection summary
        total_chains = len(self.test_results['connections']) - 1  # -1 for 'config_loaded'
        successful_chains = sum(1 for k, v in self.test_results['connections'].items() 
                              if k != 'config_loaded' and isinstance(v, dict) and v.get('websocket_endpoints'))
        
        self.logger.info(f"🌐 Connection Results:")
        self.logger.info(f"   Chains tested: {total_chains}")
        self.logger.info(f"   Chains with WebSocket: {successful_chains}")
        self.logger.info(f"   Success rate: {successful_chains/max(total_chains,1)*100:.1f}%")
        
        # Transaction summary
        metrics = self.test_results['performance_metrics']
        self.logger.info(f"📊 Transaction Analysis:")
        self.logger.info(f"   Total transactions: {metrics.get('total_transactions', 0)}")
        self.logger.info(f"   DEX transactions: {metrics.get('dex_transactions', 0)}")
        self.logger.info(f"   Opportunities found: {metrics.get('opportunities_found', 0)}")
        self.logger.info(f"   Analysis errors: {metrics.get('analysis_errors', 0)}")
        
        # Performance summary
        avg_time = metrics.get('average_analysis_time_ms', 0)
        compliance = metrics.get('sla_compliance_rate', 0) * 100
        
        self.logger.info(f"⚡ Performance Summary:")
        self.logger.info(f"   Average analysis time: {avg_time:.1f}ms (Target: <300ms)")
        self.logger.info(f"   SLA compliance: {compliance:.1f}% (Target: ≥95%)")
        
        # Overall assessment
        if (successful_chains > 0 and 
            avg_time <= 300 and 
            compliance >= 95 and
            len(self.test_results['errors']) == 0):
            self.logger.info("🎯 OVERALL RESULT: ✅ READY FOR FAST LANE")
        elif successful_chains > 0 and avg_time <= 500:
            self.logger.info("🎯 OVERALL RESULT: ⚠️  NEEDS OPTIMIZATION")
        else:
            self.logger.info("🎯 OVERALL RESULT: ❌ REQUIRES FIXES")
        
        # Error summary
        if self.test_results['errors']:
            self.logger.warning(f"⚠️  {len(self.test_results['errors'])} errors encountered during testing")
            for error in self.test_results['errors'][-3:]:  # Show last 3 errors
                self.logger.warning(f"   - {error['phase']}: {error['error']}")
        
        self.logger.info("=" * 80)
    
    async def _cleanup(self) -> None:
        """Clean up test resources."""
        if self.monitor:
            try:
                await self.monitor.stop_monitoring()
            except Exception as e:
                self.logger.debug(f"Error stopping monitor: {e}")
    
    def save_results(self, filename: str = None) -> str:
        """Save test results to file."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"mempool_test_results_{timestamp}.json"
        
        # Convert datetime objects to strings for JSON serialization
        results_copy = self.test_results.copy()
        if results_copy['start_time']:
            results_copy['start_time'] = results_copy['start_time'].isoformat()
        if results_copy['end_time']:
            results_copy['end_time'] = results_copy['end_time'].isoformat()
        
        with open(filename, 'w') as f:
            json.dump(results_copy, f, indent=2, default=str)
        
        return filename


# =============================================================================
# CLI INTERFACE
# =============================================================================

async def main():
    """Main CLI interface for mempool testing."""
    parser = argparse.ArgumentParser(description="Test mempool integration components")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    parser.add_argument("--chain-id", type=int, help="Test specific chain ID only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--demo-mode", action="store_true", help="Use demo API keys")
    parser.add_argument("--save-results", action="store_true", help="Save results to file")
    
    args = parser.parse_args()
    
    # Create tester
    tester = MempoolTester(
        test_duration=args.duration,
        verbose=args.verbose,
        demo_mode=args.demo_mode
    )
    
    try:
        # Run comprehensive test
        results = await tester.run_comprehensive_test(args.chain_id)
        
        # Save results if requested
        if args.save_results:
            filename = tester.save_results()
            print(f"\n💾 Results saved to: {filename}")
        
        # Return appropriate exit code
        errors = len(results.get('errors', []))
        if errors == 0:
            sys.exit(0)  # Success
        else:
            print(f"\n❌ Test completed with {errors} errors")
            sys.exit(1)  # Failure
    
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())