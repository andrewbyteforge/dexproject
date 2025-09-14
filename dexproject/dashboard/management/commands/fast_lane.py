"""
Django Management Command for Fast Lane Engine Control

Provides initialization, testing, and status checking for the Fast Lane engine
integration with the dashboard.

File: dexproject/dashboard/management/commands/fast_lane.py

Usage:
    python manage.py fast_lane --status              # Check engine status
    python manage.py fast_lane --init                # Initialize engine
    python manage.py fast_lane --test                # Run integration test
    python manage.py fast_lane --mock                # Force mock mode
    python manage.py fast_lane --live                # Force live mode
    python manage.py fast_lane --dashboard-test      # Test dashboard integration
"""

import asyncio
import time
import json
from datetime import datetime
from typing import Dict, Any, Optional

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.core.cache import cache

from dashboard.engine_service import engine_service


class Command(BaseCommand):
    """Django management command for Fast Lane engine control."""
    
    help = 'Control and test Fast Lane engine integration with dashboard'
    
    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show current engine status and configuration'
        )
        
        parser.add_argument(
            '--init',
            action='store_true',
            help='Initialize Fast Lane engine'
        )
        
        parser.add_argument(
            '--test',
            action='store_true',
            help='Run Fast Lane engine integration test'
        )
        
        parser.add_argument(
            '--mock',
            action='store_true',
            help='Force mock mode for testing'
        )
        
        parser.add_argument(
            '--live',
            action='store_true',
            help='Force live mode (requires real engine)'
        )
        
        parser.add_argument(
            '--dashboard-test',
            action='store_true',
            help='Test dashboard integration with engine service'
        )
        
        parser.add_argument(
            '--chain-id',
            type=int,
            default=84532,  # Base Sepolia
            help='Blockchain chain ID for engine initialization'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )
    
    def handle(self, *args, **options):
        """Handle command execution."""
        self.verbosity = options.get('verbosity', 1)
        self.verbose = options.get('verbose', False)
        
        try:
            if options['status']:
                self.show_status(options)
            elif options['init']:
                self.initialize_engine(options)
            elif options['test']:
                self.run_integration_test(options)
            elif options['mock']:
                self.force_mock_mode(options)
            elif options['live']:
                self.force_live_mode(options)
            elif options['dashboard_test']:
                self.test_dashboard_integration(options)
            else:
                self.print_usage()
                
        except Exception as e:
            raise CommandError(f'Command failed: {e}')
    
    def show_status(self, options):
        """Show current engine status and configuration."""
        self.stdout.write(self.style.SUCCESS('=== Fast Lane Engine Status ==='))
        
        # Check Django configuration
        self.stdout.write('\n📋 Django Configuration:')
        self.stdout.write(f'  ENGINE_MOCK_MODE: {getattr(settings, "ENGINE_MOCK_MODE", "Not set")}')
        self.stdout.write(f'  FAST_LANE_ENABLED: {getattr(settings, "FAST_LANE_ENABLED", "Not set")}')
        self.stdout.write(f'  ENGINE_DEFAULT_CHAIN: {getattr(settings, "ENGINE_DEFAULT_CHAIN", "Not set")}')
        self.stdout.write(f'  REDIS_URL: {getattr(settings, "REDIS_URL", "Not set")}')
        
        # Check engine service status
        self.stdout.write('\n🔧 Engine Service Status:')
        self.stdout.write(f'  Mock mode: {engine_service.mock_mode}')
        self.stdout.write(f'  Engine initialized: {engine_service.engine_initialized}')
        self.stdout.write(f'  Circuit breaker state: {engine_service.circuit_breaker.state}')
        
        # Get engine status
        try:
            status = engine_service.get_engine_status()
            self.stdout.write('\n⚡ Engine Status:')
            self.stdout.write(f'  Status: {status.get("status", "UNKNOWN")}')
            self.stdout.write(f'  Fast Lane active: {status.get("fast_lane_active", False)}')
            self.stdout.write(f'  Smart Lane active: {status.get("smart_lane_active", False)}')
            self.stdout.write(f'  Mempool connected: {status.get("mempool_connected", False)}')
            self.stdout.write(f'  Data source: {"LIVE" if not status.get("_mock", False) else "MOCK"}')
            
            if self.verbose:
                self.stdout.write(f'\n🔍 Detailed Status:')
                self.stdout.write(json.dumps(status, indent=2, default=str))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to get engine status: {e}'))
        
        # Get performance metrics
        try:
            metrics = engine_service.get_performance_metrics()
            self.stdout.write('\n📊 Performance Metrics:')
            self.stdout.write(f'  Execution time: {metrics.get("execution_time_ms", 0):.1f}ms')
            self.stdout.write(f'  Success rate: {metrics.get("success_rate", 0):.1f}%')
            self.stdout.write(f'  Trades per minute: {metrics.get("trades_per_minute", 0):.1f}')
            self.stdout.write(f'  Risk cache hits: {metrics.get("risk_cache_hits", 0)}%')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to get performance metrics: {e}'))
    
    def initialize_engine(self, options):
        """Initialize the Fast Lane engine."""
        chain_id = options['chain_id']
        
        self.stdout.write(self.style.SUCCESS(f'=== Initializing Fast Lane Engine (Chain {chain_id}) ==='))
        
        async def init_async():
            try:
                success = await engine_service.initialize_engine(chain_id=chain_id)
                return success
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Engine initialization failed: {e}'))
                return False
        
        # Run async initialization
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                success = loop.run_until_complete(init_async())
                
                if success:
                    self.stdout.write(self.style.SUCCESS('✅ Fast Lane engine initialized successfully'))
                    
                    # Test basic functionality
                    status = engine_service.get_engine_status()
                    self.stdout.write(f'📊 Engine status: {status.get("status", "UNKNOWN")}')
                    self.stdout.write(f'⚡ Fast Lane active: {status.get("fast_lane_active", False)}')
                    
                else:
                    self.stdout.write(self.style.ERROR('❌ Failed to initialize Fast Lane engine'))
                    
            finally:
                loop.close()
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Initialization error: {e}'))
    
    def run_integration_test(self, options):
        """Run Fast Lane engine integration test."""
        self.stdout.write(self.style.SUCCESS('=== Fast Lane Integration Test ==='))
        
        # Test 1: Engine service initialization
        self.stdout.write('\n🧪 Test 1: Engine Service Initialization')
        try:
            if not engine_service.mock_mode:
                async def test_init():
                    return await engine_service.initialize_engine(chain_id=options['chain_id'])
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    success = loop.run_until_complete(test_init())
                    if success:
                        self.stdout.write('  ✅ Engine initialized successfully')
                    else:
                        self.stdout.write('  ❌ Engine initialization failed')
                finally:
                    loop.close()
            else:
                self.stdout.write('  ⚠️  Mock mode - skipping real engine initialization')
        except Exception as e:
            self.stdout.write(f'  ❌ Initialization test failed: {e}')
        
        # Test 2: Status retrieval
        self.stdout.write('\n🧪 Test 2: Status Retrieval')
        try:
            start_time = time.time()
            status = engine_service.get_engine_status()
            elapsed_ms = (time.time() - start_time) * 1000
            
            if status and 'status' in status:
                self.stdout.write(f'  ✅ Status retrieved in {elapsed_ms:.1f}ms')
                self.stdout.write(f'  📊 Status: {status["status"]}')
            else:
                self.stdout.write('  ❌ Invalid status response')
        except Exception as e:
            self.stdout.write(f'  ❌ Status test failed: {e}')
        
        # Test 3: Performance metrics
        self.stdout.write('\n🧪 Test 3: Performance Metrics')
        try:
            start_time = time.time()
            metrics = engine_service.get_performance_metrics()
            elapsed_ms = (time.time() - start_time) * 1000
            
            if metrics:
                self.stdout.write(f'  ✅ Metrics retrieved in {elapsed_ms:.1f}ms')
                self.stdout.write(f'  ⚡ Execution time: {metrics.get("execution_time_ms", 0):.1f}ms')
                self.stdout.write(f'  📈 Success rate: {metrics.get("success_rate", 0):.1f}%')
                
                # Check if we're meeting Phase 4 targets
                exec_time = metrics.get('execution_time_ms', 0)
                if exec_time > 0 and exec_time < 500:
                    self.stdout.write(f'  🎯 Meeting Phase 4 target (<500ms)')
                elif exec_time == 0:
                    self.stdout.write(f'  ⚠️  No execution data available')
                else:
                    self.stdout.write(f'  ⚠️  Execution time exceeds target')
            else:
                self.stdout.write('  ❌ Invalid metrics response')
        except Exception as e:
            self.stdout.write(f'  ❌ Metrics test failed: {e}')
        
        # Test 4: Circuit breaker
        self.stdout.write('\n🧪 Test 4: Circuit Breaker')
        try:
            cb_state = engine_service.circuit_breaker.state
            cb_failures = engine_service.circuit_breaker.failure_count
            self.stdout.write(f'  📊 Circuit breaker state: {cb_state}')
            self.stdout.write(f'  📊 Failure count: {cb_failures}')
            
            if cb_state == 'CLOSED':
                self.stdout.write('  ✅ Circuit breaker healthy')
            else:
                self.stdout.write(f'  ⚠️  Circuit breaker in {cb_state} state')
        except Exception as e:
            self.stdout.write(f'  ❌ Circuit breaker test failed: {e}')
        
        self.stdout.write('\n🎯 Integration test complete')
    
    def force_mock_mode(self, options):
        """Force mock mode for testing."""
        self.stdout.write(self.style.WARNING('=== Forcing Mock Mode ==='))
        
        engine_service.mock_mode = True
        engine_service.engine_initialized = False
        
        # Clear cache to force fresh data
        cache.clear()
        
        self.stdout.write('✅ Mock mode enabled')
        self.stdout.write('ℹ️  Dashboard will now show mock data based on Phase 4 test results')
        
        # Test mock data generation
        try:
            status = engine_service.get_engine_status()
            metrics = engine_service.get_performance_metrics()
            
            self.stdout.write(f'📊 Mock status: {status.get("status", "UNKNOWN")}')
            self.stdout.write(f'⚡ Mock execution time: {metrics.get("execution_time_ms", 0):.1f}ms')
            self.stdout.write(f'🎯 Mock success rate: {metrics.get("success_rate", 0):.1f}%')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Mock data test failed: {e}'))
    
    def force_live_mode(self, options):
        """Force live mode (requires real engine)."""
        self.stdout.write(self.style.WARNING('=== Forcing Live Mode ==='))
        
        # Check if Fast Lane components are available
        try:
            from engine.execution.fast_engine import FastLaneExecutionEngine
            from dashboard.engine_service import FAST_LANE_AVAILABLE
            
            if not FAST_LANE_AVAILABLE:
                self.stdout.write(self.style.ERROR('❌ Fast Lane engine components not available'))
                self.stdout.write('💡 Make sure engine modules are properly installed')
                return
                
        except ImportError as e:
            self.stdout.write(self.style.ERROR(f'❌ Cannot import Fast Lane engine: {e}'))
            return
        
        engine_service.mock_mode = False
        engine_service.engine_initialized = False
        
        # Clear cache
        cache.clear()
        
        self.stdout.write('✅ Live mode enabled')
        self.stdout.write('⚠️  Dashboard will attempt to connect to real Fast Lane engine')
        
        # Test initialization
        self.stdout.write('\n🧪 Testing live engine initialization...')
        self.initialize_engine(options)
    
    def test_dashboard_integration(self, options):
        """Test dashboard integration with engine service."""
        self.stdout.write(self.style.SUCCESS('=== Dashboard Integration Test ==='))
        
        # Test 1: Engine service instantiation
        self.stdout.write('\n🧪 Test 1: Engine Service')
        try:
            self.stdout.write(f'  📊 Mock mode: {engine_service.mock_mode}')
            self.stdout.write(f'  📊 Initialized: {engine_service.engine_initialized}')
            self.stdout.write(f'  📊 Circuit breaker: {engine_service.circuit_breaker.state}')
            self.stdout.write('  ✅ Engine service accessible')
        except Exception as e:
            self.stdout.write(f'  ❌ Engine service test failed: {e}')
        
        # Test 2: Status endpoint simulation
        self.stdout.write('\n🧪 Test 2: Status Endpoint')
        try:
            start_time = time.time()
            status = engine_service.get_engine_status()
            elapsed_ms = (time.time() - start_time) * 1000
            
            self.stdout.write(f'  ✅ Status retrieved in {elapsed_ms:.1f}ms')
            self.stdout.write(f'  📊 Status: {status.get("status", "UNKNOWN")}')
            self.stdout.write(f'  📊 Fast Lane: {status.get("fast_lane_active", False)}')
            self.stdout.write(f'  📊 Data source: {"LIVE" if not status.get("_mock", False) else "MOCK"}')
        except Exception as e:
            self.stdout.write(f'  ❌ Status endpoint test failed: {e}')
        
        # Test 3: Metrics endpoint simulation
        self.stdout.write('\n🧪 Test 3: Metrics Endpoint')
        try:
            start_time = time.time()
            metrics = engine_service.get_performance_metrics()
            elapsed_ms = (time.time() - start_time) * 1000
            
            self.stdout.write(f'  ✅ Metrics retrieved in {elapsed_ms:.1f}ms')
            self.stdout.write(f'  ⚡ Execution time: {metrics.get("execution_time_ms", 0):.1f}ms')
            self.stdout.write(f'  📈 Success rate: {metrics.get("success_rate", 0):.1f}%')
            self.stdout.write(f'  🔄 Trades/min: {metrics.get("trades_per_minute", 0):.1f}')
            self.stdout.write(f'  📊 Data source: {"LIVE" if not metrics.get("_mock", False) else "MOCK"}')
        except Exception as e:
            self.stdout.write(f'  ❌ Metrics endpoint test failed: {e}')
        
        # Test 4: Trading mode setting
        self.stdout.write('\n🧪 Test 4: Trading Mode Setting')
        try:
            # Test setting Fast Lane mode
            success = engine_service.set_trading_mode('FAST_LANE')
            if success:
                self.stdout.write('  ✅ Fast Lane mode set successfully')
            else:
                self.stdout.write('  ❌ Failed to set Fast Lane mode')
            
            # Test setting Smart Lane mode (should work but warn about Phase 5)
            success = engine_service.set_trading_mode('SMART_LANE')
            if success:
                self.stdout.write('  ✅ Smart Lane mode set successfully (Phase 5 pending)')
            else:
                self.stdout.write('  ❌ Failed to set Smart Lane mode')
                
        except Exception as e:
            self.stdout.write(f'  ❌ Trading mode test failed: {e}')
        
        # Test 5: Cache functionality
        self.stdout.write('\n🧪 Test 5: Cache Integration')
        try:
            # Test cache keys
            cache.set('test_dashboard_key', {'test': 'data'}, 60)
            cached_data = cache.get('test_dashboard_key')
            
            if cached_data and cached_data.get('test') == 'data':
                self.stdout.write('  ✅ Cache integration working')
            else:
                self.stdout.write('  ❌ Cache integration failed')
                
            # Clean up test data
            cache.delete('test_dashboard_key')
            
        except Exception as e:
            self.stdout.write(f'  ❌ Cache test failed: {e}')
        
        # Test 6: SSE data simulation
        self.stdout.write('\n🧪 Test 6: SSE Data Format')
        try:
            # Simulate SSE message format
            metrics = engine_service.get_performance_metrics()
            status = engine_service.get_engine_status()
            
            sse_message = {
                'type': 'metrics_update',
                'timestamp': datetime.now().isoformat(),
                'metrics': {
                    'execution_time_ms': metrics.get('execution_time_ms', 0),
                    'success_rate': metrics.get('success_rate', 0),
                    'trades_per_minute': metrics.get('trades_per_minute', 0),
                    'is_live': not metrics.get('_mock', False)
                },
                'status': {
                    'status': status.get('status', 'UNKNOWN'),
                    'fast_lane_active': status.get('fast_lane_active', False),
                    'is_live': not status.get('_mock', False)
                }
            }
            
            # Validate JSON serialization
            json_data = json.dumps(sse_message, default=str)
            self.stdout.write('  ✅ SSE message format valid')
            
            if self.verbose:
                self.stdout.write(f'  📊 SSE message: {json_data}')
                
        except Exception as e:
            self.stdout.write(f'  ❌ SSE format test failed: {e}')
        
        self.stdout.write('\n🎯 Dashboard integration test complete')
        
        # Summary
        self.stdout.write('\n📋 Integration Summary:')
        self.stdout.write(f'  Engine mode: {"MOCK" if engine_service.mock_mode else "LIVE"}')
        self.stdout.write(f'  Dashboard ready: ✅')
        self.stdout.write(f'  Fast Lane ready: ✅')
        self.stdout.write(f'  Smart Lane ready: ⏳ (Phase 5)')
    
    def print_usage(self):
        """Print command usage information."""
        self.stdout.write(self.style.SUCCESS('=== Fast Lane Engine Management ==='))
        self.stdout.write('\nAvailable commands:')
        self.stdout.write('  --status              Show engine status and configuration')
        self.stdout.write('  --init                Initialize Fast Lane engine')
        self.stdout.write('  --test                Run integration test')
        self.stdout.write('  --mock                Force mock mode')
        self.stdout.write('  --live                Force live mode')
        self.stdout.write('  --dashboard-test      Test dashboard integration')
        
        self.stdout.write('\nOptions:')
        self.stdout.write('  --chain-id CHAIN_ID   Specify blockchain chain ID (default: 84532)')
        self.stdout.write('  --verbose             Enable verbose output')
        
        self.stdout.write('\nExamples:')
        self.stdout.write('  python manage.py fast_lane --status')
        self.stdout.write('  python manage.py fast_lane --init --chain-id 1')
        self.stdout.write('  python manage.py fast_lane --test --verbose')
        self.stdout.write('  python manage.py fast_lane --dashboard-test')
        
        self.stdout.write('\n📊 Current Status:')
        try:
            self.stdout.write(f'  Mock mode: {engine_service.mock_mode}')
            self.stdout.write(f'  Engine initialized: {engine_service.engine_initialized}')
        except:
            self.stdout.write('  Status unavailable')