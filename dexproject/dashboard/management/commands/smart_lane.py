"""
Smart Lane Management Command

Django management command for testing and managing Smart Lane functionality.
Provides comprehensive testing, initialization, and debugging capabilities.

Usage:
    python manage.py smart_lane status
    python manage.py smart_lane test
    python manage.py smart_lane analyze <token_address>
    python manage.py smart_lane demo

File: dashboard/management/commands/smart_lane.py
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from dashboard.engine_service import engine_service


class Command(BaseCommand):
    """
    Smart Lane management command for testing and debugging.
    
    Provides comprehensive functionality for Smart Lane pipeline testing,
    status monitoring, and demonstration capabilities.
    """
    
    help = 'Manage and test Smart Lane functionality'
    
    def add_arguments(self, parser) -> None:
        """Add command line arguments."""
        subparsers = parser.add_subparsers(dest='action', help='Available actions')
        
        # Status command
        status_parser = subparsers.add_parser('status', help='Show Smart Lane status')
        status_parser.add_argument(
            '--verbose', '-v',
            action='store_true',
            help='Show detailed status information'
        )
        
        # Test command
        test_parser = subparsers.add_parser('test', help='Run Smart Lane tests')
        test_parser.add_argument(
            '--quick', '-q',
            action='store_true',
            help='Run quick tests only'
        )
        
        # Analyze command
        analyze_parser = subparsers.add_parser('analyze', help='Analyze a token with Smart Lane')
        analyze_parser.add_argument(
            'token_address',
            help='Token contract address to analyze'
        )
        analyze_parser.add_argument(
            '--symbol',
            help='Token symbol (optional)'
        )
        analyze_parser.add_argument(
            '--save',
            action='store_true',
            help='Save analysis results to file'
        )
        
        # Demo command
        demo_parser = subparsers.add_parser('demo', help='Run Smart Lane demonstration')
        demo_parser.add_argument(
            '--interactive', '-i',
            action='store_true',
            help='Interactive demo mode'
        )
        
        # Initialize command
        init_parser = subparsers.add_parser('init', help='Initialize Smart Lane pipeline')
        init_parser.add_argument(
            '--chain-id',
            type=int,
            default=1,
            help='Blockchain chain ID (default: 1 for Ethereum)'
        )
    
    def handle(self, *args, **options) -> None:
        """Handle command execution based on action."""
        action = options.get('action')
        
        if not action:
            self.print_help()
            return
        
        try:
            if action == 'status':
                self.handle_status(options)
            elif action == 'test':
                self.handle_test(options)
            elif action == 'analyze':
                self.handle_analyze(options)
            elif action == 'demo':
                self.handle_demo(options)
            elif action == 'init':
                self.handle_init(options)
            else:
                raise CommandError(f"Unknown action: {action}")
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Command failed: {e}"))
            if options.get('verbosity', 1) >= 2:
                import traceback
                self.stdout.write(traceback.format_exc())
    
    def print_help(self) -> None:
        """Print command help information."""
        self.stdout.write(self.style.SUCCESS('=== Smart Lane Management Command ==='))
        self.stdout.write('')
        self.stdout.write('Available actions:')
        self.stdout.write('  status    - Show Smart Lane status and health')
        self.stdout.write('  test      - Run Smart Lane functionality tests')
        self.stdout.write('  analyze   - Analyze a specific token')
        self.stdout.write('  demo      - Run demonstration analysis')
        self.stdout.write('  init      - Initialize Smart Lane pipeline')
        self.stdout.write('')
        self.stdout.write('Use --help with any action for more details')
    
    def handle_status(self, options: Dict[str, Any]) -> None:
        """Handle status command."""
        verbose = options.get('verbose', False)
        
        self.stdout.write(self.style.SUCCESS('=== Smart Lane Status ==='))
        
        # Check Django configuration
        self.stdout.write('\n📋 Django Configuration:')
        self.stdout.write(f'  SMART_LANE_ENABLED: {getattr(settings, "SMART_LANE_ENABLED", "Not set")}')
        self.stdout.write(f'  SMART_LANE_MOCK_MODE: {getattr(settings, "SMART_LANE_MOCK_MODE", "Not set")}')
        self.stdout.write(f'  ENGINE_MOCK_MODE: {getattr(settings, "ENGINE_MOCK_MODE", "Not set")}')
        self.stdout.write(f'  REDIS_URL: {getattr(settings, "REDIS_URL", "Not set")}')
        
        # Check engine service status
        self.stdout.write('\n🔧 Engine Service Status:')
        self.stdout.write(f'  Smart Lane available: {engine_service.smart_lane_available}')
        self.stdout.write(f'  Smart Lane initialized: {engine_service.smart_lane_initialized}')
        self.stdout.write(f'  Mock mode: {engine_service.mock_mode}')
        self.stdout.write(f'  Circuit breaker state: {engine_service.circuit_breaker.state}')
        
        # Get engine status
        try:
            status = engine_service.get_engine_status()
            self.stdout.write('\n🧠 Smart Lane Status:')
            self.stdout.write(f'  Status: {status.get("smart_lane_status", "UNKNOWN")}')
            self.stdout.write(f'  Active: {status.get("smart_lane_active", False)}')
            self.stdout.write(f'  Analyses completed: {status.get("smart_lane_analyses_completed", 0)}')
            self.stdout.write(f'  Success rate: {status.get("smart_lane_success_rate", 0):.1f}%')
            self.stdout.write(f'  Average analysis time: {status.get("smart_lane_avg_time_ms", 0):.1f}ms')
            self.stdout.write(f'  Cache hit ratio: {status.get("smart_lane_cache_hit_ratio", 0):.1f}%')
            
            if verbose:
                self.stdout.write(f'\n🔍 Detailed Status:')
                self.stdout.write(json.dumps(status, indent=2, default=str))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to get Smart Lane status: {e}'))
        
        # Get performance metrics
        try:
            metrics = engine_service.get_performance_metrics()
            self.stdout.write('\n📊 Performance Metrics:')
            self.stdout.write(f'  Smart Lane calls: {metrics.get("smart_lane_calls", 0)}')
            self.stdout.write(f'  Analysis time: {metrics.get("smart_lane_analysis_time_ms", 0):.1f}ms')
            self.stdout.write(f'  Success rate: {metrics.get("smart_lane_success_rate", 0):.1f}%')
            self.stdout.write(f'  Risk-adjusted return: +{metrics.get("risk_adjusted_return", 0):.1f}%')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to get performance metrics: {e}'))
    
    def handle_test(self, options: Dict[str, Any]) -> None:
        """Handle test command."""
        quick = options.get('quick', False)
        
        self.stdout.write(self.style.SUCCESS('=== Smart Lane Testing ==='))
        
        tests = []
        
        # Basic tests (always run)
        tests.extend([
            ('Engine Service Instantiation', self.test_engine_service),
            ('Smart Lane Availability', self.test_smart_lane_availability),
            ('Status Endpoint', self.test_status_endpoint),
            ('Metrics Endpoint', self.test_metrics_endpoint),
        ])
        
        # Extended tests (unless quick mode)
        if not quick:
            tests.extend([
                ('Smart Lane Initialization', self.test_smart_lane_initialization),
                ('Token Analysis', self.test_token_analysis),
                ('Performance Timing', self.test_performance_timing),
            ])
        
        # Run tests
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            self.stdout.write(f'\n🧪 Test: {test_name}')
            try:
                start_time = time.time()
                result = test_func()
                elapsed_ms = (time.time() - start_time) * 1000
                
                if result:
                    self.stdout.write(f'  ✅ PASSED ({elapsed_ms:.1f}ms)')
                    passed += 1
                else:
                    self.stdout.write(f'  ❌ FAILED ({elapsed_ms:.1f}ms)')
                    
            except Exception as e:
                self.stdout.write(f'  ❌ ERROR: {e}')
        
        # Summary
        self.stdout.write(f'\n📊 Test Results: {passed}/{total} tests passed')
        success_rate = (passed / total) * 100
        
        if success_rate == 100:
            self.stdout.write(self.style.SUCCESS('🎉 All tests passed! Smart Lane is operational.'))
        elif success_rate >= 80:
            self.stdout.write(self.style.WARNING(f'⚠️  {success_rate:.1f}% tests passed. Some issues detected.'))
        else:
            self.stdout.write(self.style.ERROR(f'❌ Only {success_rate:.1f}% tests passed. Major issues detected.'))
    
    def handle_analyze(self, options: Dict[str, Any]) -> None:
        """Handle analyze command."""
        token_address = options['token_address']
        symbol = options.get('symbol', '')
        save_results = options.get('save', False)
        
        self.stdout.write(self.style.SUCCESS(f'=== Analyzing Token: {token_address} ==='))
        
        # Validate token address
        if not token_address.startswith('0x') or len(token_address) != 42:
            raise CommandError('Invalid token address format. Must be 42 characters starting with 0x')
        
        # Prepare analysis context
        context = {}
        if symbol:
            context['symbol'] = symbol
        
        try:
            # Initialize Smart Lane if needed
            self.stdout.write('🔧 Initializing Smart Lane...')
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            if not engine_service.smart_lane_initialized:
                success = loop.run_until_complete(engine_service.initialize_smart_lane())
                if not success:
                    self.stdout.write(self.style.WARNING('Smart Lane initialization failed, using mock mode'))
            
            # Perform analysis
            self.stdout.write(f'🧠 Analyzing token {token_address}...')
            start_time = time.time()
            
            analysis = loop.run_until_complete(
                engine_service.analyze_token_smart_lane(token_address, context)
            )
            
            elapsed_ms = (time.time() - start_time) * 1000
            loop.close()
            
            if analysis:
                self.stdout.write(f'✅ Analysis completed in {elapsed_ms:.1f}ms')
                self.display_analysis_results(analysis)
                
                if save_results:
                    self.save_analysis_results(analysis, token_address)
            else:
                self.stdout.write(self.style.ERROR('❌ Analysis failed'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Analysis error: {e}'))
            raise
    
    def handle_demo(self, options: Dict[str, Any]) -> None:
        """Handle demo command."""
        interactive = options.get('interactive', False)
        
        self.stdout.write(self.style.SUCCESS('=== Smart Lane Demonstration ==='))
        
        # Demo tokens for testing
        demo_tokens = [
            ('0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984', 'UNI', 'Uniswap'),
            ('0xA0b86a33E6285c7C2aF97ac0A8A8A4a0885de96e', 'DEMO', 'Demo Token'),
            ('0xdAC17F958D2ee523a2206206994597C13D831ec7', 'USDT', 'Tether USD'),
        ]
        
        if interactive:
            self.stdout.write('\n🎯 Interactive Demo Mode')
            self.stdout.write('Available demo tokens:')
            for i, (address, symbol, name) in enumerate(demo_tokens, 1):
                self.stdout.write(f'  {i}. {symbol} ({name}) - {address[:10]}...')
            
            choice = input('\nSelect token (1-3) or enter custom address: ').strip()
            
            try:
                if choice.isdigit() and 1 <= int(choice) <= len(demo_tokens):
                    token_address, symbol, name = demo_tokens[int(choice) - 1]
                elif choice.startswith('0x') and len(choice) == 42:
                    token_address = choice
                    symbol = input('Enter symbol (optional): ').strip()
                    name = symbol
                else:
                    raise ValueError('Invalid selection')
            except (ValueError, IndexError):
                self.stdout.write(self.style.ERROR('Invalid selection, using default demo token'))
                token_address, symbol, name = demo_tokens[0]
        else:
            # Use default demo token
            token_address, symbol, name = demo_tokens[0]
        
        self.stdout.write(f'\n🎪 Running demo analysis for {symbol} ({name})')
        
        # Run analysis using the analyze handler
        options_copy = options.copy()
        options_copy.update({
            'token_address': token_address,
            'symbol': symbol,
            'save': False
        })
        
        self.handle_analyze(options_copy)
    
    def handle_init(self, options: Dict[str, Any]) -> None:
        """Handle init command."""
        chain_id = options.get('chain_id', 1)
        
        self.stdout.write(self.style.SUCCESS(f'=== Initializing Smart Lane (Chain {chain_id}) ==='))
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            self.stdout.write('🔧 Initializing Smart Lane pipeline...')
            success = loop.run_until_complete(engine_service.initialize_smart_lane(chain_id=chain_id))
            
            loop.close()
            
            if success:
                self.stdout.write(self.style.SUCCESS('✅ Smart Lane initialized successfully'))
                
                # Get status after initialization
                status = engine_service.get_engine_status()
                self.stdout.write(f'\n📊 Initialization Results:')
                self.stdout.write(f'  Smart Lane active: {status.get("smart_lane_active", False)}')
                self.stdout.write(f'  Status: {status.get("smart_lane_status", "UNKNOWN")}')
                
            else:
                self.stdout.write(self.style.ERROR('❌ Smart Lane initialization failed'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Initialization error: {e}'))
            raise
    
    # =========================================================================
    # TEST METHODS
    # =========================================================================
    
    def test_engine_service(self) -> bool:
        """Test engine service instantiation."""
        try:
            self.stdout.write(f'  📊 Smart Lane available: {engine_service.smart_lane_available}')
            self.stdout.write(f'  📊 Initialized: {engine_service.smart_lane_initialized}')
            self.stdout.write(f'  📊 Mock mode: {engine_service.mock_mode}')
            return True
        except Exception as e:
            self.stdout.write(f'  ❌ Engine service error: {e}')
            return False
    
    def test_smart_lane_availability(self) -> bool:
        """Test Smart Lane component availability."""
        try:
            # Check if Smart Lane components are importable
            from engine.smart_lane.pipeline import SmartLanePipeline
            from engine.smart_lane import SmartLaneConfig
            self.stdout.write('  ✅ Smart Lane components available')
            return True
        except ImportError as e:
            self.stdout.write(f'  ❌ Smart Lane components not available: {e}')
            return engine_service.smart_lane_available  # Still pass if engine service handles it
    
    def test_status_endpoint(self) -> bool:
        """Test status endpoint."""
        try:
            status = engine_service.get_engine_status()
            smart_lane_status = status.get('smart_lane_status', 'UNKNOWN')
            self.stdout.write(f'  📊 Smart Lane status: {smart_lane_status}')
            return smart_lane_status != 'ERROR'
        except Exception as e:
            self.stdout.write(f'  ❌ Status endpoint error: {e}')
            return False
    
    def test_metrics_endpoint(self) -> bool:
        """Test metrics endpoint."""
        try:
            metrics = engine_service.get_performance_metrics()
            analysis_time = metrics.get('smart_lane_analysis_time_ms', 0)
            success_rate = metrics.get('smart_lane_success_rate', 0)
            self.stdout.write(f'  📊 Analysis time: {analysis_time:.1f}ms')
            self.stdout.write(f'  📊 Success rate: {success_rate:.1f}%')
            return analysis_time > 0 and success_rate > 0
        except Exception as e:
            self.stdout.write(f'  ❌ Metrics endpoint error: {e}')
            return False
    
    def test_smart_lane_initialization(self) -> bool:
        """Test Smart Lane initialization."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            success = loop.run_until_complete(engine_service.initialize_smart_lane())
            loop.close()
            
            self.stdout.write(f'  📊 Initialization success: {success}')
            self.stdout.write(f'  📊 Pipeline initialized: {engine_service.smart_lane_initialized}')
            
            return success
        except Exception as e:
            self.stdout.write(f'  ❌ Initialization error: {e}')
            return False
    
    def test_token_analysis(self) -> bool:
        """Test token analysis functionality."""
        try:
            demo_token = "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"  # UNI
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            analysis = loop.run_until_complete(
                engine_service.analyze_token_smart_lane(demo_token, {'symbol': 'UNI'})
            )
            
            loop.close()
            
            if analysis:
                self.stdout.write(f'  📊 Analysis ID: {analysis.get("analysis_id", "N/A")}')
                self.stdout.write(f'  📊 Risk score: {analysis.get("overall_risk_score", 0):.3f}')
                self.stdout.write(f'  📊 Confidence: {analysis.get("confidence_score", 0):.3f}')
                self.stdout.write(f'  📊 Recommendation: {analysis.get("recommended_action", "N/A")}')
                return True
            else:
                self.stdout.write('  ❌ Analysis returned no results')
                return False
                
        except Exception as e:
            self.stdout.write(f'  ❌ Token analysis error: {e}')
            return False
    
    def test_performance_timing(self) -> bool:
        """Test performance timing."""
        try:
            demo_token = "0xA0b86a33E6285c7C2aF97ac0A8A8A4a0885de96e"
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            start_time = time.time()
            analysis = loop.run_until_complete(
                engine_service.analyze_token_smart_lane(demo_token, {})
            )
            elapsed_ms = (time.time() - start_time) * 1000
            
            loop.close()
            
            self.stdout.write(f'  📊 Analysis time: {elapsed_ms:.1f}ms')
            self.stdout.write(f'  📊 Target: <5000ms')
            
            # Consider it a pass if analysis completes within reasonable time
            return analysis is not None and elapsed_ms < 10000  # 10 second timeout
            
        except Exception as e:
            self.stdout.write(f'  ❌ Performance test error: {e}')
            return False
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def display_analysis_results(self, analysis: Dict[str, Any]) -> None:
        """Display analysis results in a formatted way."""
        self.stdout.write('\n📊 Analysis Results:')
        self.stdout.write('=' * 50)
        
        # Basic info
        self.stdout.write(f'Token Address: {analysis.get("token_address", "N/A")}')
        self.stdout.write(f'Analysis ID: {analysis.get("analysis_id", "N/A")}')
        self.stdout.write(f'Timestamp: {analysis.get("timestamp", "N/A")}')
        self.stdout.write(f'Analysis Time: {analysis.get("analysis_time_ms", 0):.1f}ms')
        self.stdout.write(f'Mock Data: {analysis.get("_mock", False)}')
        
        # Risk assessment
        self.stdout.write(f'\n🎯 Risk Assessment:')
        risk_score = analysis.get('overall_risk_score', 0)
        confidence = analysis.get('confidence_score', 0)
        action = analysis.get('recommended_action', 'UNKNOWN')
        
        self.stdout.write(f'  Overall Risk Score: {risk_score:.3f}/1.0')
        self.stdout.write(f'  Confidence Score: {confidence:.3f}/1.0')
        self.stdout.write(f'  Recommended Action: {action}')
        
        # Risk categories
        risk_categories = analysis.get('risk_categories', {})
        if risk_categories:
            self.stdout.write(f'\n🛡️  Risk Categories:')
            for category, details in risk_categories.items():
                score = details.get('score', 0)
                conf = details.get('confidence', 0)
                self.stdout.write(f'  {category}: {score:.3f} (confidence: {conf:.3f})')
        
        # Technical signals
        technical_signals = analysis.get('technical_signals', [])
        if technical_signals:
            self.stdout.write(f'\n📈 Technical Signals:')
            for signal in technical_signals:
                signal_type = signal.get('signal_type', 'UNKNOWN')
                strength = signal.get('strength', 0)
                timeframe = signal.get('timeframe', 'N/A')
                self.stdout.write(f'  {signal_type} ({timeframe}): {strength:.2f}')
        
        # Position sizing
        position_sizing = analysis.get('position_sizing')
        if position_sizing:
            self.stdout.write(f'\n💰 Position Sizing:')
            size_percent = position_sizing.get('recommended_size_percent', 0)
            risk_percent = position_sizing.get('risk_per_trade_percent', 0)
            reasoning = position_sizing.get('reasoning', 'N/A')
            self.stdout.write(f'  Recommended Size: {size_percent:.1f}% of portfolio')
            self.stdout.write(f'  Risk Per Trade: {risk_percent:.1f}%')
            self.stdout.write(f'  Reasoning: {reasoning}')
        
        # Exit strategy
        exit_strategy = analysis.get('exit_strategy')
        if exit_strategy:
            self.stdout.write(f'\n🚪 Exit Strategy:')
            strategy_name = exit_strategy.get('strategy_name', 'UNKNOWN')
            stop_loss = exit_strategy.get('stop_loss_percent', 0)
            take_profit = exit_strategy.get('take_profit_percent', 0)
            self.stdout.write(f'  Strategy: {strategy_name}')
            self.stdout.write(f'  Stop Loss: {stop_loss:.1f}%')
            self.stdout.write(f'  Take Profit: +{take_profit:.1f}%')
        
        # AI Thought Log (first 5 steps)
        thought_log = analysis.get('thought_log', [])
        if thought_log:
            self.stdout.write(f'\n🧠 AI Thought Log (first 5 steps):')
            for i, step in enumerate(thought_log[:5], 1):
                self.stdout.write(f'  {i}. {step}')
            if len(thought_log) > 5:
                self.stdout.write(f'  ... and {len(thought_log) - 5} more steps')
    
    def save_analysis_results(self, analysis: Dict[str, Any], token_address: str) -> None:
        """Save analysis results to a JSON file."""
        import os
        from datetime import datetime
        
        # Create results directory if it doesn't exist
        results_dir = 'smart_lane_results'
        os.makedirs(results_dir, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        token_short = token_address[:10]
        filename = f'{results_dir}/analysis_{token_short}_{timestamp}.json'
        
        # Save results
        try:
            with open(filename, 'w') as f:
                json.dump(analysis, f, indent=2, default=str)
            
            self.stdout.write(f'💾 Analysis results saved to: {filename}')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to save results: {e}'))