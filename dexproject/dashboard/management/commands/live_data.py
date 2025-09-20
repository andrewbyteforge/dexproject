"""
Live Data Management Command

Provides command-line interface for activating, testing, and monitoring
live blockchain data connections. Replaces mock data with real mempool
streaming and transaction processing.

File: dashboard/management/commands/live_data.py
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional
from django.core.management.base import BaseCommand, CommandError
from django.core.cache import cache
from django.conf import settings
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Management command for live blockchain data operations."""
    
    help = 'Manage live blockchain data connections and monitoring'
    
    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show live data connection status'
        )
        
        parser.add_argument(
            '--activate',
            action='store_true',
            help='Activate live blockchain data connections'
        )
        
        parser.add_argument(
            '--test',
            action='store_true',
            help='Test live data connections and processing'
        )
        
        parser.add_argument(
            '--monitor',
            action='store_true',
            help='Monitor live data streams in real-time'
        )
        
        parser.add_argument(
            '--deactivate',
            action='store_true',
            help='Deactivate live data and return to mock mode'
        )
        
        parser.add_argument(
            '--chain-id',
            type=int,
            help='Target specific chain ID for operations'
        )
        
        parser.add_argument(
            '--provider',
            choices=['alchemy', 'ankr', 'infura'],
            help='Target specific provider for operations'
        )
        
        parser.add_argument(
            '--duration',
            type=int,
            default=30,
            help='Duration for monitoring operations (seconds)'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )
    
    def handle(self, *args, **options):
        """Handle command execution."""
        try:
            # Setup logging level
            if options['verbose']:
                logging.getLogger().setLevel(logging.DEBUG)
                self.stdout.write(self.style.WARNING('Verbose mode enabled'))
            
            # Execute requested operation
            if options['status']:
                self.show_status(options)
            elif options['activate']:
                self.activate_live_data(options)
            elif options['test']:
                self.test_live_connections(options)
            elif options['monitor']:
                self.monitor_live_data(options)
            elif options['deactivate']:
                self.deactivate_live_data(options)
            else:
                self.show_help(options)
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Command failed: {e}'))
            raise CommandError(f'Live data command failed: {e}')
    
    def show_help(self, options):
        """Show command help and current system status."""
        self.stdout.write(self.style.SUCCESS('=== Live Blockchain Data Management ==='))
        self.stdout.write('\nAvailable commands:')
        self.stdout.write('  --status              Show live data connection status')
        self.stdout.write('  --activate            Activate live blockchain connections')
        self.stdout.write('  --test                Test live data connections')
        self.stdout.write('  --monitor             Monitor live data streams')
        self.stdout.write('  --deactivate          Return to mock data mode')
        
        self.stdout.write('\nOptions:')
        self.stdout.write('  --chain-id CHAIN_ID   Target specific chain')
        self.stdout.write('  --provider PROVIDER   Target specific provider')
        self.stdout.write('  --duration SECONDS    Monitor duration')
        self.stdout.write('  --verbose             Enable verbose output')
        
        self.stdout.write('\nExamples:')
        self.stdout.write('  python manage.py live_data --status')
        self.stdout.write('  python manage.py live_data --activate --verbose')
        self.stdout.write('  python manage.py live_data --test --chain-id 84532')
        self.stdout.write('  python manage.py live_data --monitor --duration 60')
        
        # Show current status
        self.stdout.write('\n📊 Current System Status:')
        try:
            mock_mode = getattr(settings, 'ENGINE_MOCK_MODE', True)
            live_enabled = not mock_mode
            
            self.stdout.write(f'  Mock mode: {"✅ ENABLED" if mock_mode else "❌ DISABLED"}')
            self.stdout.write(f'  Live mode: {"✅ ENABLED" if live_enabled else "❌ DISABLED"}')
            self.stdout.write(f'  API keys: {self._get_api_key_summary()}')
            self.stdout.write(f'  Target chains: {getattr(settings, "SUPPORTED_CHAINS", [])}')
            
        except Exception as e:
            self.stdout.write(f'  Status check failed: {e}')
    
    def show_status(self, options):
        """Show detailed live data connection status."""
        self.stdout.write(self.style.SUCCESS('=== Live Data Connection Status ==='))
        
        try:
            # Import live services
            from dashboard.live_mempool_service import get_live_mempool_status, get_live_mempool_metrics
            from dashboard.engine_service import engine_service
            
            # Get system configuration
            mock_mode = getattr(settings, 'ENGINE_MOCK_MODE', True)
            live_enabled = not mock_mode
            
            self.stdout.write(f'\n🔧 Configuration:')
            self.stdout.write(f'  Engine Mock Mode: {"✅ ENABLED" if mock_mode else "❌ DISABLED"}')
            self.stdout.write(f'  Live Data Mode: {"✅ ENABLED" if live_enabled else "❌ DISABLED"}')
            self.stdout.write(f'  Force Mock Data: {getattr(settings, "FORCE_MOCK_DATA", False)}')
            
            # API Keys Status
            self.stdout.write(f'\n🔑 API Keys:')
            api_keys = {
                'Alchemy': bool(getattr(settings, 'ALCHEMY_API_KEY', '')),
                'Ankr': bool(getattr(settings, 'ANKR_API_KEY', '')),
                'Infura': bool(getattr(settings, 'INFURA_PROJECT_ID', ''))
            }
            
            for provider, configured in api_keys.items():
                status = "✅ CONFIGURED" if configured else "❌ MISSING"
                self.stdout.write(f'  {provider}: {status}')
            
            # Engine Status
            self.stdout.write(f'\n🚀 Engine Status:')
            engine_status = engine_service.get_engine_status()
            
            self.stdout.write(f'  Initialized: {"✅ YES" if engine_status.get("initialized") else "❌ NO"}')
            self.stdout.write(f'  Status: {engine_status.get("status", "UNKNOWN")}')
            self.stdout.write(f'  Live Mode: {"✅ YES" if engine_status.get("is_live") else "❌ NO"}')
            self.stdout.write(f'  Circuit Breaker: {engine_status.get("circuit_breaker_state", "UNKNOWN")}')
            
            # Live Connection Status
            if live_enabled:
                self.stdout.write(f'\n🌐 Live Connections:')
                
                try:
                    live_status = get_live_mempool_status()
                    
                    self.stdout.write(f'  Service Running: {"✅ YES" if live_status.get("is_running") else "❌ NO"}')
                    self.stdout.write(f'  Active Connections: {live_status.get("metrics", {}).get("active_connections", 0)}')
                    self.stdout.write(f'  Total Connections: {live_status.get("metrics", {}).get("total_connections", 0)}')
                    self.stdout.write(f'  Uptime: {live_status.get("metrics", {}).get("connection_uptime_percentage", 0):.1f}%')
                    
                    # Individual connection details
                    connections = live_status.get('connections', {})
                    if connections:
                        self.stdout.write(f'\n📡 Individual Connections:')
                        for conn_key, conn_data in connections.items():
                            status = "✅ CONNECTED" if conn_data.get('connected') else "❌ DISCONNECTED"
                            self.stdout.write(f'  {conn_key}: {status}')
                            self.stdout.write(f'    Messages: {conn_data.get("message_count", 0)}')
                            self.stdout.write(f'    Errors: {conn_data.get("error_count", 0)}')
                    
                    # Metrics
                    metrics = get_live_mempool_metrics()
                    self.stdout.write(f'\n📊 Live Metrics:')
                    self.stdout.write(f'  Transactions Processed: {metrics.get("total_transactions_processed", 0)}')
                    self.stdout.write(f'  DEX Transactions: {metrics.get("dex_transactions_detected", 0)}')
                    self.stdout.write(f'  Processing Latency: {metrics.get("average_processing_latency_ms", 0):.2f}ms')
                    self.stdout.write(f'  DEX Detection Rate: {metrics.get("dex_detection_rate", 0):.1f}%')
                    
                except Exception as e:
                    self.stdout.write(f'  ❌ Live status check failed: {e}')
            else:
                self.stdout.write(f'\n🌐 Live Connections: ❌ DISABLED (Mock mode active)')
            
            # Performance Metrics
            self.stdout.write(f'\n⚡ Performance Metrics:')
            try:
                metrics = engine_service.get_performance_metrics()
                data_source = metrics.get('data_source', 'UNKNOWN')
                
                self.stdout.write(f'  Data Source: {data_source}')
                self.stdout.write(f'  Execution Time: {metrics.get("execution_time_ms", 0):.1f}ms')
                self.stdout.write(f'  Success Rate: {metrics.get("success_rate", 0):.1f}%')
                self.stdout.write(f'  Trades/Min: {metrics.get("trades_per_minute", 0)}')
                
            except Exception as e:
                self.stdout.write(f'  ❌ Metrics check failed: {e}')
                
        except ImportError as e:
            self.stdout.write(self.style.ERROR(f'❌ Live data services not available: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Status check failed: {e}'))
    
    def activate_live_data(self, options):
        """Activate live blockchain data connections."""
        self.stdout.write(self.style.WARNING('=== Activating Live Blockchain Data ==='))
        
        # Check prerequisites
        if not self._check_prerequisites():
            return
        
        try:
            # Import required services
            from dashboard.live_mempool_service import initialize_live_mempool
            from dashboard.engine_service import engine_service
            
            self.stdout.write('\n🔧 Updating configuration...')
            
            # Update Django settings (in memory)
            settings.ENGINE_MOCK_MODE = False
            settings.FORCE_MOCK_DATA = False
            
            self.stdout.write('✅ Mock mode disabled')
            self.stdout.write('✅ Live data mode enabled')
            
            # Clear caches
            cache.clear()
            self.stdout.write('✅ Caches cleared')
            
            # Initialize live services
            self.stdout.write('\n🚀 Initializing live services...')
            
            # Run async initialization
            async def init_live():
                try:
                    # Initialize live mempool
                    if await initialize_live_mempool():
                        self.stdout.write('✅ Live mempool monitoring activated')
                        return True
                    else:
                        self.stdout.write('❌ Live mempool initialization failed')
                        return False
                except Exception as e:
                    self.stdout.write(f'❌ Live mempool error: {e}')
                    return False
            
            # Run initialization
            success = asyncio.run(init_live())
            
            if success:
                # Re-initialize engine service
                self.stdout.write('\n🔄 Re-initializing engine service...')
                
                async def reinit_engine():
                    return await engine_service.initialize_engine(force_reinit=True)
                
                if asyncio.run(reinit_engine()):
                    self.stdout.write('✅ Engine service re-initialized')
                    
                    self.stdout.write('\n🎯 Live Data Activation Complete!')
                    self.stdout.write('✅ System now using real blockchain data')
                    self.stdout.write('✅ Dashboard will show live metrics')
                    self.stdout.write('\n💡 Next steps:')
                    self.stdout.write('  1. Run: python manage.py live_data --test')
                    self.stdout.write('  2. Monitor dashboard for live data indicators')
                    self.stdout.write('  3. Check logs for any connection issues')
                else:
                    self.stdout.write('❌ Engine re-initialization failed')
            else:
                self.stdout.write('\n❌ Live data activation failed')
                self.stdout.write('💡 Try: python manage.py live_data --test --verbose')
                
        except ImportError as e:
            self.stdout.write(self.style.ERROR(f'❌ Live services not available: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Activation failed: {e}'))
    
    def test_live_connections(self, options):
        """Test live data connections and processing."""
        self.stdout.write(self.style.WARNING('=== Testing Live Data Connections ==='))
        
        target_chain = options.get('chain_id')
        target_provider = options.get('provider')
        
        try:
            from dashboard.live_mempool_service import live_mempool_service
            
            async def run_connection_tests():
                self.stdout.write('\n🧪 Running connection tests...')
                
                # Test API key configuration
                self.stdout.write('\n1️⃣ Testing API key configuration...')
                api_keys = live_mempool_service.api_keys
                
                for provider, key in api_keys.items():
                    if target_provider and provider != target_provider:
                        continue
                        
                    if key:
                        self.stdout.write(f'  ✅ {provider.capitalize()}: API key configured')
                    else:
                        self.stdout.write(f'  ❌ {provider.capitalize()}: API key missing')
                
                # Test WebSocket URLs
                self.stdout.write('\n2️⃣ Testing WebSocket URL generation...')
                
                test_chains = [target_chain] if target_chain else live_mempool_service.supported_chains
                test_providers = [target_provider] if target_provider else ['alchemy', 'ankr', 'infura']
                
                for chain_id in test_chains:
                    for provider in test_providers:
                        if api_keys.get(provider):
                            ws_url = live_mempool_service._get_websocket_url(chain_id, provider)
                            if ws_url:
                                self.stdout.write(f'  ✅ {provider} chain {chain_id}: URL generated')
                                
                                # Test actual connection
                                if await live_mempool_service._test_websocket_connection(ws_url):
                                    self.stdout.write(f'    ✅ Connection test successful')
                                else:
                                    self.stdout.write(f'    ❌ Connection test failed')
                            else:
                                self.stdout.write(f'  ❌ {provider} chain {chain_id}: No URL available')
                
                # Test live monitoring initialization
                self.stdout.write('\n3️⃣ Testing live monitoring...')
                
                if await live_mempool_service.start_live_monitoring():
                    self.stdout.write('  ✅ Live monitoring started successfully')
                    
                    # Monitor for a few seconds
                    self.stdout.write('  📡 Monitoring for live data (10 seconds)...')
                    await asyncio.sleep(10)
                    
                    # Get status
                    status = live_mempool_service.get_live_status()
                    metrics = live_mempool_service.get_live_metrics()
                    
                    self.stdout.write(f'    Active connections: {metrics.get("active_connections", 0)}')
                    self.stdout.write(f'    Transactions processed: {metrics.get("total_transactions_processed", 0)}')
                    self.stdout.write(f'    DEX transactions: {metrics.get("dex_transactions_detected", 0)}')
                    
                    await live_mempool_service.stop_live_monitoring()
                    self.stdout.write('  ✅ Live monitoring stopped')
                else:
                    self.stdout.write('  ❌ Live monitoring failed to start')
            
            # Run tests
            asyncio.run(run_connection_tests())
            
            self.stdout.write('\n🎯 Connection tests completed!')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Connection tests failed: {e}'))
    
    def monitor_live_data(self, options):
        """Monitor live data streams in real-time."""
        duration = options.get('duration', 30)
        
        self.stdout.write(self.style.WARNING(f'=== Monitoring Live Data ({duration}s) ==='))
        
        try:
            from dashboard.live_mempool_service import live_mempool_service, get_live_mempool_metrics
            
            async def monitor_streams():
                # Start monitoring
                if not await live_mempool_service.start_live_monitoring():
                    self.stdout.write('❌ Failed to start live monitoring')
                    return
                
                self.stdout.write('📡 Live monitoring active - watching for transactions...')
                self.stdout.write(f'⏱️  Monitoring for {duration} seconds')
                self.stdout.write('Press Ctrl+C to stop early\n')
                
                start_time = time.time()
                last_update = 0
                
                try:
                    while time.time() - start_time < duration:
                        await asyncio.sleep(5)  # Update every 5 seconds
                        
                        # Get current metrics
                        metrics = get_live_mempool_metrics()
                        elapsed = int(time.time() - start_time)
                        
                        # Clear previous line and show update
                        print(f'\r⏱️  {elapsed}s | Connections: {metrics.get("active_connections", 0)} | ' +
                              f'TX: {metrics.get("total_transactions_processed", 0)} | ' +
                              f'DEX: {metrics.get("dex_transactions_detected", 0)} | ' +
                              f'Latency: {metrics.get("average_processing_latency_ms", 0):.1f}ms', end='')
                        
                        # Detailed update every 15 seconds
                        if elapsed > 0 and elapsed % 15 == 0 and elapsed != last_update:
                            print()  # New line
                            self.stdout.write(f'\n📊 Status at {elapsed}s:')
                            self.stdout.write(f'  Total transactions: {metrics.get("total_transactions_processed", 0)}')
                            self.stdout.write(f'  DEX transactions: {metrics.get("dex_transactions_detected", 0)}')
                            self.stdout.write(f'  Processing latency: {metrics.get("average_processing_latency_ms", 0):.2f}ms')
                            self.stdout.write(f'  Connection uptime: {metrics.get("connection_uptime_percentage", 0):.1f}%')
                            last_update = elapsed
                
                except KeyboardInterrupt:
                    print()  # New line
                    self.stdout.write('\n⏹️  Monitoring stopped by user')
                
                finally:
                    await live_mempool_service.stop_live_monitoring()
                    
                    # Final summary
                    final_metrics = get_live_mempool_metrics()
                    print()  # New line
                    self.stdout.write('\n🎯 Final Summary:')
                    self.stdout.write(f'  Duration: {int(time.time() - start_time)}s')
                    self.stdout.write(f'  Total transactions: {final_metrics.get("total_transactions_processed", 0)}')
                    self.stdout.write(f'  DEX transactions: {final_metrics.get("dex_transactions_detected", 0)}')
                    self.stdout.write(f'  Average latency: {final_metrics.get("average_processing_latency_ms", 0):.2f}ms')
            
            # Run monitoring
            asyncio.run(monitor_streams())
            
        except KeyboardInterrupt:
            self.stdout.write('\n⏹️  Monitoring interrupted')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Monitoring failed: {e}'))
    
    def deactivate_live_data(self, options):
        """Deactivate live data and return to mock mode."""
        self.stdout.write(self.style.WARNING('=== Deactivating Live Data ==='))
        
        try:
            from dashboard.live_mempool_service import live_mempool_service
            from dashboard.engine_service import engine_service
            
            async def deactivate():
                # Stop live services
                self.stdout.write('⏹️  Stopping live services...')
                await live_mempool_service.stop_live_monitoring()
                self.stdout.write('✅ Live monitoring stopped')
                
                # Update configuration
                settings.ENGINE_MOCK_MODE = True
                settings.FORCE_MOCK_DATA = True
                
                # Clear caches
                cache.clear()
                self.stdout.write('✅ Caches cleared')
                
                # Re-initialize engine in mock mode
                if await engine_service.initialize_engine(force_reinit=True):
                    self.stdout.write('✅ Engine re-initialized in mock mode')
                else:
                    self.stdout.write('❌ Engine re-initialization failed')
            
            asyncio.run(deactivate())
            
            self.stdout.write('\n🎯 Live Data Deactivated!')
            self.stdout.write('✅ System returned to mock data mode')
            self.stdout.write('✅ Dashboard will show simulated metrics')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Deactivation failed: {e}'))
    
    def _check_prerequisites(self) -> bool:
        """Check prerequisites for live data activation."""
        self.stdout.write('\n🔍 Checking prerequisites...')
        
        # Check API keys
        api_keys = {
            'ALCHEMY_API_KEY': getattr(settings, 'ALCHEMY_API_KEY', ''),
            'ANKR_API_KEY': getattr(settings, 'ANKR_API_KEY', ''),
            'INFURA_PROJECT_ID': getattr(settings, 'INFURA_PROJECT_ID', '')
        }
        
        configured_keys = sum(1 for key in api_keys.values() if key)
        
        if configured_keys == 0:
            self.stdout.write('❌ No API keys configured')
            self.stdout.write('💡 Add API keys to your .env file:')
            self.stdout.write('   ALCHEMY_API_KEY=your_key_here')
            self.stdout.write('   ANKR_API_KEY=your_key_here')
            return False
        
        self.stdout.write(f'✅ {configured_keys}/3 API keys configured')
        
        # Check supported chains
        chains = getattr(settings, 'SUPPORTED_CHAINS', [])
        if not chains:
            self.stdout.write('❌ No supported chains configured')
            return False
        
        self.stdout.write(f'✅ {len(chains)} supported chains: {chains}')
        
        # Check required services
        try:
            from dashboard.http_live_service import http_live_service as live_service
            self.stdout.write('✅ HTTP live service available')
        except ImportError:
            try:
                from dashboard.live_mempool_service import live_mempool_service as live_service
                self.stdout.write('⚠️ Using fallback WebSocket service')
            except ImportError:
                self.stdout.write('❌ Live mempool service not available')
                return False
        
        self.stdout.write('✅ Prerequisites satisfied')
        return True
    
    def _get_api_key_summary(self) -> str:
        """Get summary of configured API keys."""
        keys = {
            'Alchemy': bool(getattr(settings, 'ALCHEMY_API_KEY', '')),
            'Ankr': bool(getattr(settings, 'ANKR_API_KEY', '')),
            'Infura': bool(getattr(settings, 'INFURA_PROJECT_ID', ''))
        }
        
        configured = sum(keys.values())
        return f'{configured}/3 configured'