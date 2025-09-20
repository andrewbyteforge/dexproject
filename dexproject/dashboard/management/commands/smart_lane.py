"""
Smart Lane Management Command

Django management command for testing and managing Smart Lane functionality.
Provides comprehensive testing, initialization, and debugging capabilities.

Enhanced with complete Smart Lane integration and real-time monitoring.

Usage:
    python manage.py smart_lane status
    python manage.py smart_lane test
    python manage.py smart_lane analyze <token_address>
    python manage.py smart_lane demo
    python manage.py smart_lane init
    python manage.py smart_lane metrics
    python manage.py smart_lane thought-log <analysis_id>

File: dashboard/management/commands/smart_lane.py
"""

import asyncio
import json
import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Smart Lane management command for testing and debugging.
    
    Provides comprehensive functionality for Smart Lane pipeline testing,
    status monitoring, and demonstration capabilities.
    """
    
    help = 'Manage and test Smart Lane functionality'
    
    def add_arguments(self, parser) -> None:
        """Add command line arguments."""
        parser.add_argument(
            'action',
            choices=['status', 'test', 'analyze', 'demo', 'init', 'metrics', 'thought-log', 'benchmark'],
            help='Action to perform'
        )
        
        parser.add_argument(
            'target',
            nargs='?',
            help='Target for action (e.g., token address for analyze, analysis_id for thought-log)'
        )
        
        parser.add_argument(
            '--config',
            type=str,
            help='Configuration JSON file for analysis'
        )
        
        parser.add_argument(
            '--depth',
            choices=['BASIC', 'COMPREHENSIVE', 'DEEP_DIVE'],
            default='COMPREHENSIVE',
            help='Analysis depth for analyze command'
        )
        
        parser.add_argument(
            '--count',
            type=int,
            default=1,
            help='Number of iterations for test/demo commands'
        )
        
        parser.add_argument(
            '--export',
            action='store_true',
            help='Export results to file'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )
        
        parser.add_argument(
            '--format',
            choices=['table', 'json', 'csv'],
            default='table',
            help='Output format'
        )
    
    def handle(self, *args, **options) -> None:
        """Handle command execution."""
        action = options['action']
        
        # Set logging level based on verbosity
        if options['verbose']:
            logging.getLogger().setLevel(logging.DEBUG)
        
        self.stdout.write(
            self.style.SUCCESS(f'🧠 Smart Lane Management - {action.upper()}')
        )
        
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
            elif action == 'metrics':
                self.handle_metrics(options)
            elif action == 'thought-log':
                self.handle_thought_log(options)
            elif action == 'benchmark':
                self.handle_benchmark(options)
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\n⚠️  Command interrupted by user'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {str(e)}'))
            if options['verbose']:
                import traceback
                self.stdout.write(traceback.format_exc())
            raise CommandError(f'Smart Lane command failed: {e}')
    
    def handle_status(self, options: Dict[str, Any]) -> None:
        """Display Smart Lane status information."""
        self.stdout.write('📊 Smart Lane Status Check')
        self.stdout.write('=' * 50)
        
        try:
            # Import Smart Lane service
            from dashboard.smart_lane_service import smart_lane_service
            
            # Get status information
            pipeline_status = smart_lane_service.get_pipeline_status()
            metrics = smart_lane_service.get_analysis_metrics()
            
            # Display status
            status = pipeline_status.get('status', 'UNKNOWN')
            status_color = self.get_status_color(status)
            
            self.stdout.write(f'Pipeline Status: {status_color}')
            self.stdout.write(f'Pipeline Active: {pipeline_status.get("pipeline_active", False)}')
            self.stdout.write(f'Analyzers Count: {pipeline_status.get("analyzers_count", 0)}')
            self.stdout.write(f'Analysis Ready: {pipeline_status.get("analysis_ready", False)}')
            
            if pipeline_status.get('capabilities'):
                self.stdout.write('\n🔧 Available Capabilities:')
                for capability in pipeline_status['capabilities']:
                    self.stdout.write(f'  • {capability.replace("_", " ").title()}')
            
            # Display metrics
            self.stdout.write('\n📈 Performance Metrics:')
            self.stdout.write(f'Analyses Completed: {metrics.get("analyses_completed", 0)}')
            self.stdout.write(f'Success Rate: {metrics.get("success_rate", 0):.1f}%')
            self.stdout.write(f'Average Analysis Time: {metrics.get("average_analysis_time_ms", 0):.1f}ms')
            self.stdout.write(f'Cache Hit Ratio: {metrics.get("cache_hit_ratio", 0):.1%}')
            self.stdout.write(f'Thought Logs Generated: {metrics.get("thought_logs_generated", 0)}')
            
            # Mock mode indicator
            if metrics.get('_mock', False):
                self.stdout.write(self.style.WARNING('\n⚠️  Running in mock mode'))
            else:
                self.stdout.write(self.style.SUCCESS('\n✅ Connected to live Smart Lane pipeline'))
                
        except ImportError:
            self.stdout.write(self.style.ERROR('❌ Smart Lane service not available'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error getting status: {e}'))
    
    def handle_test(self, options: Dict[str, Any]) -> None:
        """Test Smart Lane functionality."""
        count = options['count']
        
        self.stdout.write(f'🧪 Testing Smart Lane ({count} iteration{"s" if count > 1 else ""})')
        self.stdout.write('=' * 50)
        
        try:
            from dashboard.smart_lane_service import smart_lane_service
            
            # Initialize service if needed
            if not smart_lane_service.initialized:
                self.stdout.write('🔄 Initializing Smart Lane service...')
                result = asyncio.run(smart_lane_service.initialize())
                if result:
                    self.stdout.write(self.style.SUCCESS('✅ Service initialized'))
                else:
                    self.stdout.write(self.style.WARNING('⚠️  Using mock mode'))
            
            # Run tests
            test_results = []
            
            for i in range(count):
                if count > 1:
                    self.stdout.write(f'\n🔄 Test iteration {i + 1}/{count}')
                
                start_time = time.time()
                
                # Test token address (using a known test token)
                test_token = '0x1234567890123456789012345678901234567890'
                
                # Run analysis
                self.stdout.write('🔍 Running test analysis...')
                analysis_result = asyncio.run(
                    smart_lane_service.run_analysis(test_token, {})
                )
                
                end_time = time.time()
                execution_time = (end_time - start_time) * 1000
                
                if analysis_result.get('success'):
                    self.stdout.write(self.style.SUCCESS(f'✅ Analysis completed in {execution_time:.1f}ms'))
                    
                    # Display results
                    if options['verbose']:
                        result = analysis_result.get('result', {})
                        self.stdout.write(f'   Risk Score: {result.get("overall_risk_score", 0):.2f}')
                        self.stdout.write(f'   Risk Category: {result.get("risk_category", "UNKNOWN")}')
                        self.stdout.write(f'   Recommendation: {result.get("recommendations", {}).get("action", "NONE")}')
                    
                    # Check thought log
                    thought_log_id = analysis_result.get('thought_log_id')
                    if thought_log_id:
                        thought_log = smart_lane_service.get_thought_log(thought_log_id)
                        if thought_log:
                            self.stdout.write(f'✅ Thought log generated ({len(thought_log.get("reasoning_steps", []))} steps)')
                
                else:
                    self.stdout.write(self.style.ERROR(f'❌ Analysis failed: {analysis_result.get("error")}'))
                
                test_results.append({
                    'iteration': i + 1,
                    'success': analysis_result.get('success', False),
                    'execution_time_ms': execution_time,
                    'error': analysis_result.get('error')
                })
                
                # Brief pause between iterations
                if i < count - 1:
                    time.sleep(1)
            
            # Summary
            self.stdout.write('\n📊 Test Summary:')
            successful_tests = sum(1 for r in test_results if r['success'])
            self.stdout.write(f'Success Rate: {successful_tests}/{count} ({successful_tests/count*100:.1f}%)')
            
            if test_results:
                avg_time = sum(r['execution_time_ms'] for r in test_results if r['success']) / max(successful_tests, 1)
                self.stdout.write(f'Average Execution Time: {avg_time:.1f}ms')
            
            # Export results if requested
            if options['export']:
                self.export_results('smart_lane_test', test_results, options)
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Test failed: {e}'))
            raise
    
    def handle_analyze(self, options: Dict[str, Any]) -> None:
        """Analyze a specific token."""
        token_address = options.get('target')
        if not token_address:
            raise CommandError('Token address is required for analyze command')
        
        self.stdout.write(f'🔍 Analyzing token: {token_address}')
        self.stdout.write('=' * 50)
        
        try:
            from dashboard.smart_lane_service import smart_lane_service
            from engine.smart_lane import AnalysisDepth
            
            # Initialize service
            if not smart_lane_service.initialized:
                self.stdout.write('🔄 Initializing Smart Lane service...')
                asyncio.run(smart_lane_service.initialize())
            
            # Prepare analysis configuration
            config = {}
            if options.get('config'):
                with open(options['config'], 'r') as f:
                    config = json.load(f)
            
            # Set analysis depth
            depth_map = {
                'BASIC': 'BASIC',
                'COMPREHENSIVE': 'COMPREHENSIVE', 
                'DEEP_DIVE': 'DEEP_DIVE'
            }
            config['analysis_depth'] = depth_map.get(options['depth'], 'COMPREHENSIVE')
            
            self.stdout.write(f'📋 Analysis Configuration:')
            self.stdout.write(f'   Depth: {config["analysis_depth"]}')
            self.stdout.write(f'   Token: {token_address}')
            
            # Run analysis
            start_time = time.time()
            self.stdout.write('\n🔄 Running analysis...')
            
            analysis_result = asyncio.run(
                smart_lane_service.run_analysis(token_address, config)
            )
            
            end_time = time.time()
            execution_time = (end_time - start_time) * 1000
            
            if analysis_result.get('success'):
                self.stdout.write(self.style.SUCCESS(f'\n✅ Analysis completed in {execution_time:.1f}ms'))
                
                # Display detailed results
                result = analysis_result.get('result', {})
                self.display_analysis_results(result, options)
                
                # Display thought log
                thought_log_id = analysis_result.get('thought_log_id')
                if thought_log_id and options['verbose']:
                    self.display_thought_log(thought_log_id, smart_lane_service)
                
                # Export if requested
                if options['export']:
                    self.export_results('smart_lane_analysis', {
                        'token_address': token_address,
                        'analysis_result': analysis_result,
                        'execution_time_ms': execution_time
                    }, options)
                    
            else:
                self.stdout.write(self.style.ERROR(f'❌ Analysis failed: {analysis_result.get("error")}'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Analysis error: {e}'))
            raise
    
    def handle_demo(self, options: Dict[str, Any]) -> None:
        """Run Smart Lane demonstration."""
        count = options['count']
        
        self.stdout.write(f'🎯 Smart Lane Demo ({count} sample{"s" if count > 1 else ""})')
        self.stdout.write('=' * 50)
        
        # Demo tokens (mix of safe and risky for demonstration)
        demo_tokens = [
            ('0x1111111111111111111111111111111111111111', 'Safe Token Demo'),
            ('0x2222222222222222222222222222222222222222', 'Medium Risk Demo'),
            ('0x3333333333333333333333333333333333333333', 'High Risk Demo'),
            ('0x4444444444444444444444444444444444444444', 'Honeypot Demo'),
            ('0x5555555555555555555555555555555555555555', 'Low Liquidity Demo')
        ]
        
        try:
            from dashboard.smart_lane_service import smart_lane_service
            
            # Initialize service
            if not smart_lane_service.initialized:
                self.stdout.write('🔄 Initializing Smart Lane service...')
                asyncio.run(smart_lane_service.initialize())
            
            demo_results = []
            
            for i in range(min(count, len(demo_tokens))):
                token_address, description = demo_tokens[i]
                
                self.stdout.write(f'\n🔍 Demo {i + 1}: {description}')
                self.stdout.write(f'   Token: {token_address}')
                
                # Run analysis
                start_time = time.time()
                analysis_result = asyncio.run(
                    smart_lane_service.run_analysis(token_address, {})
                )
                end_time = time.time()
                
                if analysis_result.get('success'):
                    result = analysis_result.get('result', {})
                    
                    # Display key metrics
                    risk_score = result.get('overall_risk_score', 0)
                    risk_category = result.get('risk_category', 'UNKNOWN')
                    action = result.get('recommendations', {}).get('action', 'HOLD')
                    confidence = result.get('recommendations', {}).get('confidence', 0)
                    
                    risk_color = self.get_risk_color(risk_category)
                    action_color = self.get_action_color(action)
                    
                    self.stdout.write(f'   Risk Score: {risk_score:.2f}')
                    self.stdout.write(f'   Risk Category: {risk_color}')
                    self.stdout.write(f'   Recommendation: {action_color}')
                    self.stdout.write(f'   Confidence: {confidence:.1%}')
                    self.stdout.write(f'   Analysis Time: {(end_time - start_time) * 1000:.1f}ms')
                    
                    demo_results.append({
                        'description': description,
                        'token_address': token_address,
                        'risk_score': risk_score,
                        'risk_category': risk_category,
                        'action': action,
                        'confidence': confidence,
                        'analysis_time_ms': (end_time - start_time) * 1000
                    })
                
                else:
                    self.stdout.write(self.style.ERROR(f'   ❌ Failed: {analysis_result.get("error")}'))
                
                # Pause between demos
                if i < count - 1 and i < len(demo_tokens) - 1:
                    time.sleep(2)
            
            # Demo summary
            self.stdout.write('\n📊 Demo Summary:')
            if demo_results:
                avg_time = sum(r['analysis_time_ms'] for r in demo_results) / len(demo_results)
                self.stdout.write(f'Average Analysis Time: {avg_time:.1f}ms')
                
                risk_distribution = {}
                for result in demo_results:
                    category = result['risk_category']
                    risk_distribution[category] = risk_distribution.get(category, 0) + 1
                
                self.stdout.write('Risk Distribution:')
                for category, count_val in risk_distribution.items():
                    self.stdout.write(f'  {category}: {count_val}')
            
            # Export if requested
            if options['export']:
                self.export_results('smart_lane_demo', demo_results, options)
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Demo failed: {e}'))
            raise
    
    def handle_init(self, options: Dict[str, Any]) -> None:
        """Initialize Smart Lane service."""
        self.stdout.write('🚀 Initializing Smart Lane Service')
        self.stdout.write('=' * 50)
        
        try:
            from dashboard.smart_lane_service import smart_lane_service
            
            self.stdout.write('🔄 Starting initialization...')
            
            start_time = time.time()
            result = asyncio.run(smart_lane_service.initialize())
            end_time = time.time()
            
            if result:
                self.stdout.write(self.style.SUCCESS(f'✅ Smart Lane initialized successfully in {(end_time - start_time):.1f}s'))
                
                # Display initialization details
                status = smart_lane_service.get_pipeline_status()
                self.stdout.write(f'   Status: {status.get("status")}')
                self.stdout.write(f'   Analyzers: {status.get("analyzers_count", 0)}')
                self.stdout.write(f'   Capabilities: {len(status.get("capabilities", []))}')
                
            else:
                self.stdout.write(self.style.WARNING('⚠️  Initialization completed with warnings (mock mode)'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Initialization failed: {e}'))
            raise
    
    def handle_metrics(self, options: Dict[str, Any]) -> None:
        """Display Smart Lane metrics."""
        self.stdout.write('📊 Smart Lane Metrics Dashboard')
        self.stdout.write('=' * 50)
        
        try:
            from dashboard.smart_lane_service import smart_lane_service
            
            metrics = smart_lane_service.get_analysis_metrics()
            recent_analyses = smart_lane_service.get_recent_analyses(limit=10)
            recent_logs = smart_lane_service.get_recent_thought_logs(limit=5)
            
            # Performance metrics
            self.stdout.write('🚀 Performance Metrics:')
            self.stdout.write(f'   Total Analyses: {metrics.get("analyses_completed", 0)}')
            self.stdout.write(f'   Successful: {metrics.get("successful_analyses", 0)}')
            self.stdout.write(f'   Failed: {metrics.get("failed_analyses", 0)}')
            self.stdout.write(f'   Success Rate: {metrics.get("success_rate", 0):.1f}%')
            self.stdout.write(f'   Avg Analysis Time: {metrics.get("average_analysis_time_ms", 0):.1f}ms')
            self.stdout.write(f'   Cache Hit Ratio: {metrics.get("cache_hit_ratio", 0):.1%}')
            self.stdout.write(f'   Active Analyses: {metrics.get("active_analyses", 0)}')
            
            # Recent analyses
            if recent_analyses:
                self.stdout.write('\n📈 Recent Analyses:')
                for analysis in recent_analyses[-5:]:
                    timestamp = datetime.fromisoformat(analysis['timestamp'].replace('Z', '+00:00'))
                    self.stdout.write(f'   {timestamp.strftime("%H:%M:%S")} - {analysis["token_address"][:10]}... ({analysis["analysis_time_ms"]:.0f}ms)')
            
            # Thought logs
            if recent_logs:
                self.stdout.write(f'\n🧠 Recent Thought Logs: {len(recent_logs)} generated')
            
            # Export if requested
            if options['export']:
                export_data = {
                    'metrics': metrics,
                    'recent_analyses': recent_analyses,
                    'recent_logs': recent_logs,
                    'timestamp': datetime.now().isoformat()
                }
                self.export_results('smart_lane_metrics', export_data, options)
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Metrics error: {e}'))
            raise
    
    def handle_thought_log(self, options: Dict[str, Any]) -> None:
        """Display thought log for specific analysis."""
        analysis_id = options.get('target')
        if not analysis_id:
            raise CommandError('Analysis ID is required for thought-log command')
        
        self.stdout.write(f'🧠 Thought Log: {analysis_id}')
        self.stdout.write('=' * 50)
        
        try:
            from dashboard.smart_lane_service import smart_lane_service
            
            thought_log = smart_lane_service.get_thought_log(analysis_id)
            
            if thought_log:
                self.display_thought_log_details(thought_log, options)
                
                if options['export']:
                    self.export_results('thought_log', thought_log, options)
            else:
                self.stdout.write(self.style.ERROR(f'❌ Thought log not found for analysis: {analysis_id}'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Thought log error: {e}'))
            raise
    
    def handle_benchmark(self, options: Dict[str, Any]) -> None:
        """Run Smart Lane performance benchmark."""
        count = options.get('count', 10)
        
        self.stdout.write(f'⚡ Smart Lane Benchmark ({count} iterations)')
        self.stdout.write('=' * 50)
        
        try:
            from dashboard.smart_lane_service import smart_lane_service
            
            # Initialize service
            if not smart_lane_service.initialized:
                asyncio.run(smart_lane_service.initialize())
            
            benchmark_results = []
            test_token = '0x1234567890123456789012345678901234567890'
            
            self.stdout.write('🔄 Running benchmark...')
            
            total_start = time.time()
            
            for i in range(count):
                start_time = time.time()
                
                analysis_result = asyncio.run(
                    smart_lane_service.run_analysis(test_token, {})
                )
                
                end_time = time.time()
                execution_time = (end_time - start_time) * 1000
                
                benchmark_results.append({
                    'iteration': i + 1,
                    'success': analysis_result.get('success', False),
                    'execution_time_ms': execution_time
                })
                
                if (i + 1) % 10 == 0:
                    self.stdout.write(f'   Completed {i + 1}/{count} iterations')
            
            total_end = time.time()
            total_time = total_end - total_start
            
            # Calculate statistics
            successful_runs = [r for r in benchmark_results if r['success']]
            if successful_runs:
                times = [r['execution_time_ms'] for r in successful_runs]
                avg_time = sum(times) / len(times)
                min_time = min(times)
                max_time = max(times)
                
                # Calculate percentiles
                times_sorted = sorted(times)
                p50 = times_sorted[len(times_sorted) // 2]
                p95 = times_sorted[int(len(times_sorted) * 0.95)]
                p99 = times_sorted[int(len(times_sorted) * 0.99)]
                
                # Display results
                self.stdout.write('\n📊 Benchmark Results:')
                self.stdout.write(f'   Total Runs: {count}')
                self.stdout.write(f'   Successful: {len(successful_runs)}')
                self.stdout.write(f'   Success Rate: {len(successful_runs)/count*100:.1f}%')
                self.stdout.write(f'   Total Time: {total_time:.1f}s')
                self.stdout.write(f'   Throughput: {count/total_time:.1f} analyses/second')
                
                self.stdout.write('\n⏱️  Execution Time Statistics:')
                self.stdout.write(f'   Average: {avg_time:.1f}ms')
                self.stdout.write(f'   Minimum: {min_time:.1f}ms')
                self.stdout.write(f'   Maximum: {max_time:.1f}ms')
                self.stdout.write(f'   P50 (Median): {p50:.1f}ms')
                self.stdout.write(f'   P95: {p95:.1f}ms')
                self.stdout.write(f'   P99: {p99:.1f}ms')
                
                # Performance assessment
                if avg_time < 3000:
                    self.stdout.write(self.style.SUCCESS('✅ Excellent performance'))
                elif avg_time < 5000:
                    self.stdout.write(self.style.SUCCESS('✅ Good performance'))
                elif avg_time < 10000:
                    self.stdout.write(self.style.WARNING('⚠️  Acceptable performance'))
                else:
                    self.stdout.write(self.style.ERROR('❌ Poor performance'))
                
                # Export if requested
                if options['export']:
                    export_data = {
                        'benchmark_results': benchmark_results,
                        'statistics': {
                            'total_runs': count,
                            'successful_runs': len(successful_runs),
                            'success_rate': len(successful_runs)/count*100,
                            'total_time_seconds': total_time,
                            'throughput_per_second': count/total_time,
                            'avg_time_ms': avg_time,
                            'min_time_ms': min_time,
                            'max_time_ms': max_time,
                            'p50_ms': p50,
                            'p95_ms': p95,
                            'p99_ms': p99
                        }
                    }
                    self.export_results('smart_lane_benchmark', export_data, options)
                    
            else:
                self.stdout.write(self.style.ERROR('❌ No successful runs in benchmark'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Benchmark failed: {e}'))
            raise
    
    # Helper methods
    
    def get_status_color(self, status: str) -> str:
        """Get colored status text."""
        if status in ['OPERATIONAL', 'READY']:
            return self.style.SUCCESS(status)
        elif status in ['MOCK_MODE', 'PARTIALLY_OPERATIONAL']:
            return self.style.WARNING(status)
        else:
            return self.style.ERROR(status)
    
    def get_risk_color(self, risk_category: str) -> str:
        """Get colored risk category text."""
        if risk_category == 'LOW':
            return self.style.SUCCESS(risk_category)
        elif risk_category == 'MEDIUM':
            return self.style.WARNING(risk_category)
        else:
            return self.style.ERROR(risk_category)
    
    def get_action_color(self, action: str) -> str:
        """Get colored action text."""
        if action == 'BUY':
            return self.style.SUCCESS(action)
        elif action in ['HOLD', 'SELL']:
            return self.style.WARNING(action)
        else:
            return self.style.ERROR(action)
    
    def display_analysis_results(self, result: Dict[str, Any], options: Dict[str, Any]) -> None:
        """Display detailed analysis results."""
        self.stdout.write('\n📊 Analysis Results:')
        
        # Overall assessment
        risk_score = result.get('overall_risk_score', 0)
        risk_category = result.get('risk_category', 'UNKNOWN')
        
        self.stdout.write(f'   Overall Risk Score: {risk_score:.3f}')
        self.stdout.write(f'   Risk Category: {self.get_risk_color(risk_category)}')
        
        # Recommendations
        recommendations = result.get('recommendations', {})
        if recommendations:
            action = recommendations.get('action', 'NONE')
            confidence = recommendations.get('confidence', 0)
            
            self.stdout.write(f'   Recommended Action: {self.get_action_color(action)}')
            self.stdout.write(f'   Confidence Level: {confidence:.1%}')
            
            if 'position_size_percentage' in recommendations:
                self.stdout.write(f'   Position Size: {recommendations["position_size_percentage"]:.1f}%')
            if 'stop_loss_percentage' in recommendations:
                self.stdout.write(f'   Stop Loss: {recommendations["stop_loss_percentage"]:.1f}%')
        
        # Analyzer results (if verbose)
        if options['verbose'] and 'analyzers' in result:
            self.stdout.write('\n🔍 Analyzer Results:')
            for analyzer_name, analyzer_result in result['analyzers'].items():
                self.stdout.write(f'   {analyzer_name.replace("_", " ").title()}:')
                
                if 'risk_score' in analyzer_result:
                    self.stdout.write(f'     Risk Score: {analyzer_result["risk_score"]:.3f}')
                
                # Analyzer-specific details
                if analyzer_name == 'honeypot_detection':
                    is_honeypot = analyzer_result.get('is_honeypot', False)
                    confidence = analyzer_result.get('confidence', 0)
                    status = 'HONEYPOT' if is_honeypot else 'SAFE'
                    color = self.style.ERROR if is_honeypot else self.style.SUCCESS
                    self.stdout.write(f'     Status: {color(status)} (confidence: {confidence:.1%})')
                
                elif analyzer_name == 'liquidity_analysis':
                    liquidity_score = analyzer_result.get('liquidity_score', 0)
                    pool_size = analyzer_result.get('pool_size_usd', 0)
                    self.stdout.write(f'     Liquidity Score: {liquidity_score:.3f}')
                    self.stdout.write(f'     Pool Size: ${pool_size:,.0f}')
                
                elif analyzer_name == 'social_sentiment':
                    sentiment_score = analyzer_result.get('sentiment_score', 0)
                    trend = analyzer_result.get('trend', 'NEUTRAL')
                    self.stdout.write(f'     Sentiment Score: {sentiment_score:.3f}')
                    self.stdout.write(f'     Trend: {trend}')
    
    def display_thought_log(self, thought_log_id: str, smart_lane_service) -> None:
        """Display thought log information."""
        thought_log = smart_lane_service.get_thought_log(thought_log_id)
        if thought_log:
            self.stdout.write('\n🧠 AI Thought Log:')
            reasoning_steps = thought_log.get('reasoning_steps', [])
            for i, step in enumerate(reasoning_steps[:5], 1):  # Show first 5 steps
                self.stdout.write(f'   {i}. {step}')
            
            if len(reasoning_steps) > 5:
                self.stdout.write(f'   ... and {len(reasoning_steps) - 5} more steps')
            
            final_decision = thought_log.get('final_decision', 'N/A')
            confidence = thought_log.get('confidence_level', 0)
            self.stdout.write(f'   Final Decision: {self.get_action_color(final_decision)}')
            self.stdout.write(f'   Confidence: {confidence:.1%}')
    
    def display_thought_log_details(self, thought_log: Dict[str, Any], options: Dict[str, Any]) -> None:
        """Display detailed thought log."""
        token_address = thought_log.get('token_address', 'Unknown')
        timestamp = thought_log.get('timestamp', 'Unknown')
        
        self.stdout.write(f'Token: {token_address}')
        self.stdout.write(f'Timestamp: {timestamp}')
        self.stdout.write(f'Analysis ID: {thought_log.get("analysis_id", "Unknown")}')
        
        # Reasoning steps
        reasoning_steps = thought_log.get('reasoning_steps', [])
        self.stdout.write(f'\n🧠 AI Reasoning Process ({len(reasoning_steps)} steps):')
        
        for i, step in enumerate(reasoning_steps, 1):
            self.stdout.write(f'   {i:2d}. {step}')
        
        # Final decision
        final_decision = thought_log.get('final_decision', 'N/A')
        confidence = thought_log.get('confidence_level', 0)
        
        self.stdout.write(f'\n🎯 Final Decision: {self.get_action_color(final_decision)}')
        self.stdout.write(f'   Confidence Level: {confidence:.1%}')
        
        # Risk factors
        risk_factors = thought_log.get('risk_factors', [])
        if risk_factors:
            self.stdout.write(f'\n⚠️  Risk Factors Considered:')
            for factor in risk_factors:
                self.stdout.write(f'   • {factor}')
    
    def export_results(self, export_type: str, data: Any, options: Dict[str, Any]) -> None:
        """Export results to file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        format_type = options.get('format', 'json')
        
        filename = f'smart_lane_{export_type}_{timestamp}.{format_type}'
        
        try:
            if format_type == 'json':
                with open(filename, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
            
            elif format_type == 'csv':
                import csv
                
                if isinstance(data, list) and len(data) > 0:
                    with open(filename, 'w', newline='') as f:
                        if isinstance(data[0], dict):
                            writer = csv.DictWriter(f, fieldnames=data[0].keys())
                            writer.writeheader()
                            writer.writerows(data)
                        else:
                            writer = csv.writer(f)
                            writer.writerows(data)
                else:
                    with open(filename, 'w') as f:
                        f.write(str(data))
            
            self.stdout.write(self.style.SUCCESS(f'📁 Results exported to: {filename}'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Export failed: {e}'))