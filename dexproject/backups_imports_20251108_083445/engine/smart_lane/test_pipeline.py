"""
Smart Lane Pipeline Validation Tests

Comprehensive test suite to validate that all Smart Lane components
work correctly together, including the newly implemented strategy
components with thorough error handling and logging.

Path: tests/smart_lane/test_pipeline.py
"""

import sys
import os
import asyncio
import django
import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from unittest.mock import Mock, patch

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
try:
    django.setup()
    DJANGO_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Django setup failed: {e}")
    DJANGO_AVAILABLE = False

# Configure logging for tests
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SmartLaneTestSuite:
    """
    Comprehensive test suite for Smart Lane Phase 5 completion.
    
    Tests all components including analyzers, pipeline, strategy components,
    and integration points with extensive error handling and reporting.
    """
    
    def __init__(self):
        """Initialize test suite with comprehensive tracking."""
        self.test_results = {
            'passed': 0,
            'failed': 0,
            'errors': [],
            'warnings': [],
            'performance_metrics': {},
            'component_status': {}
        }
        self.start_time = time.time()
        logger.info("Smart Lane test suite initialized")
    
    def run_all_tests(self) -> bool:
        """
        Run all Smart Lane tests with comprehensive reporting.
        
        Returns:
            bool: True if all critical tests pass
        """
        try:
            logger.info("=" * 80)
            logger.info("🧪 STARTING SMART LANE PHASE 5 VALIDATION")
            logger.info("=" * 80)
            
            # Test categories in order of dependency
            test_categories = [
                ("Import Tests", self._test_imports),
                ("File Structure", self._test_file_structure),
                ("Analyzer Components", self._test_analyzers),
                ("Strategy Components", self._test_strategy_components),
                ("Pipeline Integration", self._test_pipeline_integration),
                ("Performance Tests", self._test_performance),
                ("Error Handling", self._test_error_handling),
                ("Integration Tests", self._run_integration_tests)
            ]
            
            for category_name, test_method in test_categories:
                logger.info(f"\n🔍 Running {category_name}...")
                try:
                    success = test_method()
                    if success:
                        logger.info(f"✅ {category_name}: PASSED")
                        self.test_results['passed'] += 1
                    else:
                        logger.error(f"❌ {category_name}: FAILED")
                        self.test_results['failed'] += 1
                except Exception as e:
                    logger.error(f"💥 {category_name}: ERROR - {e}", exc_info=True)
                    self.test_results['failed'] += 1
                    self.test_results['errors'].append(f"{category_name}: {e}")
            
            # Generate final report
            self._generate_final_report()
            
            # Return success status
            return self.test_results['failed'] == 0
            
        except Exception as e:
            logger.error(f"Test suite execution failed: {e}", exc_info=True)
            return False
    
    def _test_imports(self) -> bool:
        """Test that all required Smart Lane imports work correctly."""
        try:
            logger.debug("Testing Smart Lane imports...")
            import_errors = []
            
            # Test core Smart Lane imports
            try:
                from engine.smart_lane import (
                    SmartLaneConfig, RiskCategory, AnalysisDepth,
                    SmartLaneAction, DecisionConfidence
                )
                logger.debug("✅ Core Smart Lane imports successful")
            except ImportError as e:
                import_errors.append(f"Core imports: {e}")
            
            # Test pipeline imports
            try:
                from engine.smart_lane.pipeline import SmartLanePipeline
                logger.debug("✅ Pipeline imports successful")
            except ImportError as e:
                import_errors.append(f"Pipeline imports: {e}")
            
            # Test analyzer imports
            try:
                from engine.smart_lane.analyzers import (
                    create_analyzer, get_available_analyzers
                )
                from engine.smart_lane.analyzers.honeypot_analyzer import HoneypotAnalyzer
                from engine.smart_lane.analyzers.social_analyzer import SocialAnalyzer
                from engine.smart_lane.analyzers.technical_analyzer import TechnicalAnalyzer
                from engine.smart_lane.analyzers.contract_analyzer import ContractAnalyzer
                from engine.smart_lane.analyzers.market_analyzer import MarketAnalyzer
                logger.debug("✅ Analyzer imports successful")
            except ImportError as e:
                import_errors.append(f"Analyzer imports: {e}")
            
            # Test strategy imports (NEW Phase 5 components)
            try:
                from engine.smart_lane.strategy import (
                    PositionSizer, SizingCalculation, SizingMethod,
                    ExitStrategyManager, ExitStrategy, ExitLevel,
                    ExitTrigger, ExitMethod
                )
                logger.debug("✅ Strategy imports successful")
            except ImportError as e:
                import_errors.append(f"Strategy imports: {e}")
            
            # Test additional components
            try:
                from engine.smart_lane.cache import SmartLaneCache
                from engine.smart_lane.thought_log import ThoughtLogGenerator
                logger.debug("✅ Additional component imports successful")
            except ImportError as e:
                import_errors.append(f"Additional imports: {e}")
            
            if import_errors:
                logger.error(f"Import failures: {'; '.join(import_errors)}")
                self.test_results['errors'].extend(import_errors)
                return False
            
            logger.info("All Smart Lane imports successful")
            return True
            
        except Exception as e:
            logger.error(f"Import testing failed: {e}")
            return False
    
    def _test_file_structure(self) -> bool:
        """Verify all required files exist with proper structure."""
        try:
            logger.debug("Testing file structure...")
            
            required_files = [
                # Core files
                'engine/smart_lane/__init__.py',
                'engine/smart_lane/pipeline.py',
                'engine/smart_lane/cache.py', 
                'engine/smart_lane/thought_log.py',
                
                # Analyzer files
                'engine/smart_lane/analyzers/__init__.py',
                'engine/smart_lane/analyzers/honeypot_analyzer.py',
                'engine/smart_lane/analyzers/social_analyzer.py',
                'engine/smart_lane/analyzers/technical_analyzer.py',
                'engine/smart_lane/analyzers/contract_analyzer.py',
                'engine/smart_lane/analyzers/market_analyzer.py',
                
                # Strategy files (Phase 5)
                'engine/smart_lane/strategy/__init__.py',
                'engine/smart_lane/strategy/position_sizing.py',
                'engine/smart_lane/strategy/exit_strategies.py'
            ]
            
            missing_files = []
            for file_path in required_files:
                full_path = project_root / file_path
                if not full_path.exists():
                    missing_files.append(file_path)
                else:
                    # Check file is not empty
                    if full_path.stat().st_size == 0:
                        missing_files.append(f"{file_path} (empty)")
            
            if missing_files:
                logger.error(f"Missing files: {', '.join(missing_files)}")
                self.test_results['errors'].append(f"Missing files: {len(missing_files)}")
                return False
            
            logger.info(f"✅ All {len(required_files)} required files exist")
            return True
            
        except Exception as e:
            logger.error(f"File structure test failed: {e}")
            return False
    
    def _test_analyzers(self) -> bool:
        """Test analyzer creation and basic functionality."""
        try:
            logger.debug("Testing analyzer components...")
            
            from engine.smart_lane import RiskCategory
            from engine.smart_lane.analyzers import create_analyzer
            
            # Test analyzer categories
            test_categories = [
                RiskCategory.HONEYPOT_DETECTION,
                RiskCategory.SOCIAL_SENTIMENT,
                RiskCategory.TECHNICAL_ANALYSIS,
                RiskCategory.CONTRACT_SECURITY,
                RiskCategory.MARKET_STRUCTURE
            ]
            
            analyzer_results = {}
            
            for category in test_categories:
                try:
                    analyzer = create_analyzer(category, chain_id=1)
                    if analyzer is None:
                        analyzer_results[category.value] = "Failed - returned None"
                        continue
                    
                    # Test basic analyzer interface
                    if not hasattr(analyzer, 'analyze'):
                        analyzer_results[category.value] = "Failed - no analyze method"
                        continue
                    
                    analyzer_results[category.value] = "Success"
                    logger.debug(f"✅ {category.value} analyzer created successfully")
                    
                except Exception as e:
                    analyzer_results[category.value] = f"Error: {e}"
                    logger.error(f"❌ {category.value} analyzer failed: {e}")
            
            # Check results
            successful_analyzers = [k for k, v in analyzer_results.items() if v == "Success"]
            failed_analyzers = [k for k, v in analyzer_results.items() if v != "Success"]
            
            self.test_results['component_status']['analyzers'] = analyzer_results
            
            if failed_analyzers:
                logger.warning(f"Failed analyzers: {', '.join(failed_analyzers)}")
                self.test_results['warnings'].append(f"Some analyzers failed: {len(failed_analyzers)}")
            
            # Consider success if at least 3 core analyzers work
            success = len(successful_analyzers) >= 3
            logger.info(f"Analyzer test: {len(successful_analyzers)}/{len(test_categories)} successful")
            
            return success
            
        except Exception as e:
            logger.error(f"Analyzer testing failed: {e}")
            return False
    
    def _test_strategy_components(self) -> bool:
        """Test the new Phase 5 strategy components."""
        try:
            logger.debug("Testing strategy components...")
            
            from engine.smart_lane.strategy import (
                PositionSizer, SizingCalculation, SizingMethod,
                ExitStrategyManager, ExitStrategy, ExitLevel
            )
            from engine.smart_lane import SmartLaneConfig
            
            strategy_results = {}
            
            # Test Position Sizer
            try:
                logger.debug("Testing PositionSizer...")
                config = SmartLaneConfig() if SmartLaneConfig else None
                position_sizer = PositionSizer(config)
                
                # Test calculation
                sizing_result = position_sizer.calculate_position_size(
                    analysis_confidence=0.8,
                    overall_risk_score=0.3,
                    technical_signals=[],
                    market_conditions={'volatility': 0.15},
                    portfolio_context={'total_portfolio_value': 10000, 'current_position_count': 2}
                )
                
                # Validate result
                if not isinstance(sizing_result, SizingCalculation):
                    strategy_results['position_sizer'] = f"Invalid result type: {type(sizing_result)}"
                elif not (0 <= sizing_result.recommended_size_percent <= 100):
                    strategy_results['position_sizer'] = f"Invalid size: {sizing_result.recommended_size_percent}%"
                else:
                    strategy_results['position_sizer'] = "Success"
                    logger.debug(f"✅ Position sizing: {sizing_result.recommended_size_percent:.1f}%")
                
            except Exception as e:
                strategy_results['position_sizer'] = f"Error: {e}"
                logger.error(f"Position sizer test failed: {e}")
            
            # Test Exit Strategy Manager
            try:
                logger.debug("Testing ExitStrategyManager...")
                config = SmartLaneConfig() if SmartLaneConfig else None
                exit_manager = ExitStrategyManager(config)
                
                # Test strategy creation
                exit_strategy = exit_manager.create_exit_strategy(
                    risk_score=0.4,
                    technical_signals=[],
                    market_conditions={'volatility': 0.15, 'liquidity_score': 0.7},
                    position_context={'entry_price': 1.5, 'current_price': 1.6, 'position_size_usd': 1000}
                )
                
                # Validate result
                if not isinstance(exit_strategy, ExitStrategy):
                    strategy_results['exit_manager'] = f"Invalid result type: {type(exit_strategy)}"
                elif not exit_strategy.exit_levels:
                    strategy_results['exit_manager'] = "No exit levels created"
                elif not exit_strategy.strategy_name:
                    strategy_results['exit_manager'] = "No strategy name"
                else:
                    strategy_results['exit_manager'] = "Success"
                    logger.debug(f"✅ Exit strategy: {exit_strategy.strategy_name} with {len(exit_strategy.exit_levels)} levels")
                
            except Exception as e:
                strategy_results['exit_manager'] = f"Error: {e}"
                logger.error(f"Exit strategy manager test failed: {e}")
            
            # Test Strategy Integration
            try:
                logger.debug("Testing strategy integration...")
                
                # Test that components work together
                if (strategy_results.get('position_sizer') == "Success" and 
                    strategy_results.get('exit_manager') == "Success"):
                    
                    # Create integrated strategy
                    position_size = sizing_result.recommended_size_percent
                    exit_levels = len(exit_strategy.exit_levels)
                    
                    if position_size > 0 and exit_levels > 0:
                        strategy_results['integration'] = "Success"
                        logger.debug(f"✅ Strategy integration: {position_size:.1f}% position, {exit_levels} exits")
                    else:
                        strategy_results['integration'] = "Integration validation failed"
                else:
                    strategy_results['integration'] = "Component dependencies not met"
                    
            except Exception as e:
                strategy_results['integration'] = f"Error: {e}"
                logger.error(f"Strategy integration test failed: {e}")
            
            self.test_results['component_status']['strategy'] = strategy_results
            
            # Check overall strategy component success
            successful_components = [k for k, v in strategy_results.items() if v == "Success"]
            total_components = len(strategy_results)
            
            success = len(successful_components) >= 2  # At least position sizer and exit manager
            logger.info(f"Strategy components: {len(successful_components)}/{total_components} successful")
            
            if not success:
                failed_components = [k for k, v in strategy_results.items() if v != "Success"]
                logger.error(f"Failed strategy components: {', '.join(failed_components)}")
            
            return success
            
        except Exception as e:
            logger.error(f"Strategy component testing failed: {e}")
            return False
    
    def _test_pipeline_integration(self) -> bool:
        """Test Smart Lane pipeline with new strategy components."""
        try:
            logger.debug("Testing pipeline integration...")
            
            from engine.smart_lane.pipeline import SmartLanePipeline
            from engine.smart_lane import SmartLaneConfig
            
            # Create pipeline
            config = SmartLaneConfig() if SmartLaneConfig else None
            pipeline = SmartLanePipeline(config=config, chain_id=1)
            
            # Validate pipeline initialization
            if not hasattr(pipeline, 'position_sizer'):
                logger.error("Pipeline missing position_sizer")
                return False
            
            if not hasattr(pipeline, 'exit_strategy_manager'):
                logger.error("Pipeline missing exit_strategy_manager")
                return False
            
            logger.debug("✅ Pipeline initialized with strategy components")
            
            # Test basic analysis (async)
            async def test_pipeline_analysis():
                try:
                    # Mock analysis context
                    context = {
                        'symbol': 'TEST',
                        'name': 'Test Token',
                        'current_price': 1.5,
                        'market_cap': 10000000,
                        'liquidity_usd': 500000,
                        'volume_24h': 250000
                    }
                    
                    # Run analysis
                    analysis = await pipeline.analyze_token(
                        token_address="0x1234567890123456789012345678901234567890",
                        context=context
                    )
                    
                    # Validate analysis result
                    if analysis is None:
                        logger.error("Pipeline returned None analysis")
                        return False
                    
                    required_attrs = ['overall_risk_score', 'recommended_action', 'confidence_level']
                    for attr in required_attrs:
                        if not hasattr(analysis, attr):
                            logger.error(f"Analysis missing required attribute: {attr}")
                            return False
                    
                    # Check if strategy components were used
                    if hasattr(analysis, 'position_size_recommendation'):
                        logger.debug("✅ Analysis includes position sizing")
                    
                    if hasattr(analysis, 'exit_strategy'):
                        logger.debug("✅ Analysis includes exit strategy")
                    
                    logger.debug(f"✅ Pipeline analysis completed - risk: {analysis.overall_risk_score:.3f}")
                    return True
                    
                except Exception as e:
                    logger.error(f"Pipeline analysis test failed: {e}")
                    return False
            
            # Run async test
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                analysis_success = loop.run_until_complete(test_pipeline_analysis())
                loop.close()
            except Exception as e:
                logger.error(f"Async pipeline test failed: {e}")
                analysis_success = False
            
            return analysis_success
            
        except Exception as e:
            logger.error(f"Pipeline integration test failed: {e}")
            return False
    
    def _test_performance(self) -> bool:
        """Test performance benchmarks for Smart Lane components."""
        try:
            logger.debug("Testing performance metrics...")
            
            from engine.smart_lane.strategy import PositionSizer, ExitStrategyManager
            from engine.smart_lane import SmartLaneConfig
            
            performance_results = {}
            
            # Test position sizer performance
            try:
                config = SmartLaneConfig() if SmartLaneConfig else None
                sizer = PositionSizer(config)
                
                # Time multiple calculations
                start_time = time.time()
                for i in range(10):
                    sizer.calculate_position_size(
                        analysis_confidence=0.5 + (i * 0.05),
                        overall_risk_score=0.3 + (i * 0.02),
                        market_conditions={'volatility': 0.1 + (i * 0.01)}
                    )
                
                end_time = time.time()
                avg_time = (end_time - start_time) / 10
                performance_results['position_sizer_avg_ms'] = avg_time * 1000
                
                logger.debug(f"Position sizer average time: {avg_time * 1000:.2f}ms")
                
            except Exception as e:
                performance_results['position_sizer_error'] = str(e)
            
            # Test exit strategy manager performance
            try:
                config = SmartLaneConfig() if SmartLaneConfig else None
                exit_manager = ExitStrategyManager(config)
                
                start_time = time.time()
                for i in range(5):  # Fewer iterations as exit strategies are more complex
                    exit_manager.create_exit_strategy(
                        risk_score=0.4 + (i * 0.1),
                        market_conditions={'volatility': 0.15, 'market_regime': 'NORMAL'},
                        position_context={'entry_price': 1.0, 'current_price': 1.1, 'position_size_usd': 1000}
                    )
                
                end_time = time.time()
                avg_time = (end_time - start_time) / 5
                performance_results['exit_manager_avg_ms'] = avg_time * 1000
                
                logger.debug(f"Exit strategy manager average time: {avg_time * 1000:.2f}ms")
                
            except Exception as e:
                performance_results['exit_manager_error'] = str(e)
            
            self.test_results['performance_metrics'] = performance_results
            
            # Performance thresholds
            position_sizer_threshold_ms = 50  # 50ms max
            exit_manager_threshold_ms = 200   # 200ms max
            
            performance_ok = True
            
            if 'position_sizer_avg_ms' in performance_results:
                if performance_results['position_sizer_avg_ms'] > position_sizer_threshold_ms:
                    logger.warning(f"Position sizer performance slow: {performance_results['position_sizer_avg_ms']:.1f}ms > {position_sizer_threshold_ms}ms")
                    performance_ok = False
            
            if 'exit_manager_avg_ms' in performance_results:
                if performance_results['exit_manager_avg_ms'] > exit_manager_threshold_ms:
                    logger.warning(f"Exit manager performance slow: {performance_results['exit_manager_avg_ms']:.1f}ms > {exit_manager_threshold_ms}ms")
                    performance_ok = False
            
            logger.info(f"Performance test completed - within thresholds: {performance_ok}")
            return performance_ok
            
        except Exception as e:
            logger.error(f"Performance testing failed: {e}")
            return False
    
    def _test_error_handling(self) -> bool:
        """Test error handling and resilience of components."""
        try:
            logger.debug("Testing error handling...")
            
            from engine.smart_lane.strategy import PositionSizer, ExitStrategyManager
            
            error_test_results = {
                'position_sizer_errors': 0,
                'exit_manager_errors': 0,
                'handled_gracefully': 0
            }
            
            # Test position sizer error handling
            try:
                sizer = PositionSizer()
                
                # Test with invalid inputs
                test_cases = [
                    {'analysis_confidence': -1.0, 'overall_risk_score': 0.5},  # Invalid confidence
                    {'analysis_confidence': 2.0, 'overall_risk_score': 0.5},   # Invalid confidence
                    {'analysis_confidence': 0.5, 'overall_risk_score': -0.5},  # Invalid risk score
                    {'analysis_confidence': 0.5, 'overall_risk_score': 2.0},   # Invalid risk score
                    {'analysis_confidence': 'invalid', 'overall_risk_score': 0.5},  # Non-numeric
                ]
                
                for i, case in enumerate(test_cases):
                    try:
                        result = sizer.calculate_position_size(**case)
                        
                        # Should still return a valid result (fallback)
                        if hasattr(result, 'recommended_size_percent'):
                            if len(result.warnings) > 0:
                                error_test_results['handled_gracefully'] += 1
                                logger.debug(f"✅ Position sizer handled error case {i+1} gracefully")
                            else:
                                logger.warning(f"Position sizer case {i+1} should have warnings")
                        else:
                            error_test_results['position_sizer_errors'] += 1
                    except Exception as e:
                        error_test_results['position_sizer_errors'] += 1
                        logger.warning(f"Position sizer case {i+1} threw exception: {e}")
                
            except Exception as e:
                logger.error(f"Position sizer error testing failed: {e}")
                error_test_results['position_sizer_errors'] += 10
            
            # Test exit strategy manager error handling
            try:
                exit_manager = ExitStrategyManager()
                
                # Test with invalid inputs
                test_cases = [
                    {'risk_score': -1.0},      # Invalid risk score
                    {'risk_score': 2.0},       # Invalid risk score 
                    {'risk_score': 'invalid'}, # Non-numeric
                    {'risk_score': None},      # None value
                ]
                
                for i, case in enumerate(test_cases):
                    try:
                        result = exit_manager.create_exit_strategy(**case)
                        
                        # Should still return a valid strategy (fallback)
                        if hasattr(result, 'strategy_name'):
                            if hasattr(result, 'risk_management_notes') and result.risk_management_notes:
                                # Check if error is noted
                                error_noted = any('error' in note.lower() or 'fallback' in note.lower() 
                                                for note in result.risk_management_notes)
                                if error_noted:
                                    error_test_results['handled_gracefully'] += 1
                                    logger.debug(f"✅ Exit manager handled error case {i+1} gracefully")
                        else:
                            error_test_results['exit_manager_errors'] += 1
                    except Exception as e:
                        error_test_results['exit_manager_errors'] += 1
                        logger.warning(f"Exit manager case {i+1} threw exception: {e}")
                
            except Exception as e:
                logger.error(f"Exit manager error testing failed: {e}")
                error_test_results['exit_manager_errors'] += 10
            
            self.test_results['component_status']['error_handling'] = error_test_results
            
            # Evaluate error handling quality
            total_error_cases = 9  # 5 position sizer + 4 exit manager
            graceful_handling_rate = error_test_results['handled_gracefully'] / total_error_cases
            
            success = (
                error_test_results['position_sizer_errors'] <= 2 and  # Allow some errors
                error_test_results['exit_manager_errors'] <= 2 and
                graceful_handling_rate >= 0.5  # At least 50% handled gracefully
            )
            
            logger.info(f"Error handling test: {error_test_results['handled_gracefully']}/{total_error_cases} handled gracefully")
            return success
            
        except Exception as e:
            logger.error(f"Error handling test failed: {e}")
            return False
    
    def _run_integration_tests(self) -> bool:
        """Run end-to-end integration tests."""
        try:
            logger.debug("Running integration tests...")
            
            # Test complete workflow: Analysis -> Position Sizing -> Exit Strategy
            from engine.smart_lane.pipeline import SmartLanePipeline
            from engine.smart_lane import SmartLaneConfig
            
            async def integration_test():
                try:
                    # Create pipeline
                    config = SmartLaneConfig() if SmartLaneConfig else None
                    pipeline = SmartLanePipeline(config=config, chain_id=1)
                    
                    # Test scenarios
                    test_scenarios = [
                        {
                            'name': 'Low Risk Token',
                            'context': {
                                'symbol': 'SAFE', 'name': 'Safe Token',
                                'current_price': 1.0, 'market_cap': 50000000,
                                'liquidity_usd': 2000000, 'volume_24h': 1000000
                            },
                            'expected_risk_range': (0.0, 0.4),
                            'expected_action': 'BUY'
                        },
                        {
                            'name': 'High Risk Token', 
                            'context': {
                                'symbol': 'RISKY', 'name': 'Risky Token',
                                'current_price': 0.001, 'market_cap': 100000,
                                'liquidity_usd': 5000, 'volume_24h': 10000
                            },
                            'expected_risk_range': (0.6, 1.0),
                            'expected_action': 'AVOID'
                        },
                        {
                            'name': 'Medium Risk Token',
                            'context': {
                                'symbol': 'MED', 'name': 'Medium Token', 
                                'current_price': 5.0, 'market_cap': 10000000,
                                'liquidity_usd': 500000, 'volume_24h': 200000
                            },
                            'expected_risk_range': (0.3, 0.7),
                            'expected_action': 'PARTIAL_BUY'
                        }
                    ]
                    
                    scenario_results = []
                    
                    for scenario in test_scenarios:
                        try:
                            logger.debug(f"Testing scenario: {scenario['name']}")
                            
                            # Run analysis
                            analysis = await pipeline.analyze_token(
                                token_address=f"0x{scenario['name'].lower()}{'0' * (40 - len(scenario['name']))}",
                                context=scenario['context']
                            )
                            
                            if analysis is None:
                                scenario_results.append(f"{scenario['name']}: Analysis returned None")
                                continue
                            
                            # Validate risk score range
                            risk_score = getattr(analysis, 'overall_risk_score', 0.5)
                            min_risk, max_risk = scenario['expected_risk_range']
                            
                            risk_in_range = min_risk <= risk_score <= max_risk
                            
                            # Validate recommended action exists
                            has_action = hasattr(analysis, 'recommended_action')
                            
                            # Check for strategy components
                            has_position_size = (
                                hasattr(analysis, 'position_size_recommendation') or
                                hasattr(analysis, 'sizing_calculation')
                            )
                            
                            has_exit_strategy = (
                                hasattr(analysis, 'exit_strategy') or
                                hasattr(analysis, 'exit_plan')
                            )
                            
                            # Evaluate scenario
                            if risk_in_range and has_action:
                                if has_position_size and has_exit_strategy:
                                    scenario_results.append(f"{scenario['name']}: COMPLETE SUCCESS")
                                    logger.debug(f"✅ {scenario['name']}: Complete integration success")
                                else:
                                    scenario_results.append(f"{scenario['name']}: PARTIAL SUCCESS (missing strategy components)")
                                    logger.debug(f"⚠️ {scenario['name']}: Analysis successful but missing strategy components")
                            else:
                                scenario_results.append(f"{scenario['name']}: FAILED (risk: {risk_score:.3f}, action: {has_action})")
                                logger.warning(f"❌ {scenario['name']}: Failed validation")
                        
                        except Exception as e:
                            scenario_results.append(f"{scenario['name']}: ERROR - {e}")
                            logger.error(f"💥 {scenario['name']}: {e}")
                    
                    # Evaluate overall integration success
                    successful_scenarios = sum(1 for result in scenario_results if 'SUCCESS' in result)
                    total_scenarios = len(scenario_results)
                    
                    logger.info(f"Integration scenarios: {successful_scenarios}/{total_scenarios} successful")
                    
                    return successful_scenarios >= (total_scenarios * 0.6)  # 60% success rate required
                    
                except Exception as e:
                    logger.error(f"Integration test execution failed: {e}")
                    return False
            
            # Run async integration test
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                integration_success = loop.run_until_complete(integration_test())
                loop.close()
            except Exception as e:
                logger.error(f"Async integration test failed: {e}")
                integration_success = False
            
            return integration_success
            
        except Exception as e:
            logger.error(f"Integration testing failed: {e}")
            return False
    
    def _generate_final_report(self) -> None:
        """Generate comprehensive final test report."""
        try:
            total_time = time.time() - self.start_time
            total_tests = self.test_results['passed'] + self.test_results['failed']
            success_rate = (self.test_results['passed'] / max(1, total_tests)) * 100
            
            logger.info("\n" + "=" * 80)
            logger.info("📋 SMART LANE PHASE 5 TEST REPORT")
            logger.info("=" * 80)
            
            # Overall Results
            logger.info(f"🎯 OVERALL RESULTS:")
            logger.info(f"   Tests Passed: {self.test_results['passed']}/{total_tests} ({success_rate:.1f}%)")
            logger.info(f"   Total Time: {total_time:.2f} seconds")
            logger.info(f"   Errors Encountered: {len(self.test_results['errors'])}")
            logger.info(f"   Warnings: {len(self.test_results['warnings'])}")
            
            # Component Status
            if self.test_results['component_status']:
                logger.info(f"\n🔧 COMPONENT STATUS:")
                for component, status in self.test_results['component_status'].items():
                    if isinstance(status, dict):
                        successful = sum(1 for v in status.values() if v == "Success" or "Success" in str(v))
                        total = len(status)
                        logger.info(f"   {component.title()}: {successful}/{total} components working")
                    else:
                        logger.info(f"   {component.title()}: {status}")
            
            # Performance Metrics
            if self.test_results['performance_metrics']:
                logger.info(f"\n⚡ PERFORMANCE METRICS:")
                for metric, value in self.test_results['performance_metrics'].items():
                    if 'avg_ms' in metric:
                        logger.info(f"   {metric.replace('_', ' ').title()}: {value:.2f}ms")
                    else:
                        logger.info(f"   {metric.replace('_', ' ').title()}: {value}")
            
            # Phase 5 Readiness Assessment
            logger.info(f"\n🚀 PHASE 5 READINESS ASSESSMENT:")
            
            # Critical requirements
            critical_passed = True
            
            # Check imports
            if self.test_results['passed'] >= 1:  # At least imports passed
                logger.info("   ✅ Core imports working")
            else:
                logger.info("   ❌ Core imports failing")
                critical_passed = False
            
            # Check strategy components
            strategy_status = self.test_results['component_status'].get('strategy', {})
            if strategy_status and isinstance(strategy_status, dict):
                strategy_success = sum(1 for v in strategy_status.values() if v == "Success")
                if strategy_success >= 2:  # Position sizer and exit manager
                    logger.info("   ✅ Strategy components operational")
                else:
                    logger.info("   ❌ Strategy components not fully operational") 
                    critical_passed = False
            else:
                logger.info("   ⚠️ Strategy component status unknown")
            
            # Check analyzers
            analyzer_status = self.test_results['component_status'].get('analyzers', {})
            if analyzer_status and isinstance(analyzer_status, dict):
                analyzer_success = sum(1 for v in analyzer_status.values() if v == "Success")
                if analyzer_success >= 3:
                    logger.info("   ✅ Analyzer components operational")
                else:
                    logger.info("   ⚠️ Limited analyzer functionality")
            
            # Overall Phase 5 status
            if critical_passed and success_rate >= 75:
                logger.info(f"\n🎉 PHASE 5 STATUS: ✅ READY FOR PRODUCTION")
                logger.info("   Smart Lane intelligence system is fully operational!")
                logger.info("   - Position sizing engine working")
                logger.info("   - Exit strategy management working") 
                logger.info("   - Analysis pipeline integrated")
                logger.info("   - Error handling implemented")
            elif critical_passed and success_rate >= 60:
                logger.info(f"\n⚠️ PHASE 5 STATUS: 🟡 READY WITH MINOR ISSUES")
                logger.info("   Smart Lane core functionality working with some limitations")
                logger.info("   Recommended: Address warnings before production deployment")
            else:
                logger.info(f"\n❌ PHASE 5 STATUS: 🔴 NEEDS ADDITIONAL WORK") 
                logger.info("   Critical issues need to be resolved before production")
            
            # Errors and Warnings Summary
            if self.test_results['errors']:
                logger.info(f"\n⚠️ ERRORS ENCOUNTERED:")
                for i, error in enumerate(self.test_results['errors'], 1):
                    logger.info(f"   {i}. {error}")
            
            if self.test_results['warnings']:
                logger.info(f"\n💡 WARNINGS:")
                for i, warning in enumerate(self.test_results['warnings'], 1):
                    logger.info(f"   {i}. {warning}")
            
            # Next Steps
            logger.info(f"\n📋 RECOMMENDED NEXT STEPS:")
            if success_rate >= 90:
                logger.info("   1. ✅ Smart Lane Phase 5 implementation complete!")
                logger.info("   2. Enable Smart Lane configuration in dashboard")
                logger.info("   3. Run integration tests with live data")
                logger.info("   4. Begin user testing")
            elif success_rate >= 75:
                logger.info("   1. Address remaining warnings and errors")
                logger.info("   2. Run additional performance testing")
                logger.info("   3. Enable Smart Lane configuration in dashboard")
            else:
                logger.info("   1. ❌ Fix critical errors identified in test results")
                logger.info("   2. Re-run test suite until success rate > 75%")
                logger.info("   3. Review component implementations")
            
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"Final report generation failed: {e}")


def run_manual_tests() -> bool:
    """Run tests manually without pytest framework."""
    try:
        print("🧪 Running Smart Lane Phase 5 Validation Tests")
        print("=" * 60)
        
        # Create and run test suite
        test_suite = SmartLaneTestSuite()
        success = test_suite.run_all_tests()
        
        return success
        
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        return False


def check_file_structure() -> bool:
    """Quick file structure check for manual validation."""
    try:
        print("🔍 Checking Smart Lane file structure...")
        
        required_files = [
            'engine/smart_lane/__init__.py',
            'engine/smart_lane/pipeline.py',
            'engine/smart_lane/analyzers/__init__.py', 
            'engine/smart_lane/analyzers/honeypot_analyzer.py',
            'engine/smart_lane/analyzers/social_analyzer.py',
            'engine/smart_lane/analyzers/technical_analyzer.py',
            'engine/smart_lane/analyzers/contract_analyzer.py',
            'engine/smart_lane/analyzers/market_analyzer.py',
            'engine/smart_lane/strategy/__init__.py',
            'engine/smart_lane/strategy/position_sizing.py',
            'engine/smart_lane/strategy/exit_strategies.py'
        ]
        
        project_root = Path(__file__).parent.parent.parent
        missing_files = []
        
        for file_path in required_files:
            full_path = project_root / file_path
            if not full_path.exists():
                missing_files.append(file_path)
            elif full_path.stat().st_size == 0:
                missing_files.append(f"{file_path} (empty)")
        
        if missing_files:
            print("❌ Missing files:")
            for file_path in missing_files:
                print(f"   - {file_path}")
            return False
        else:
            print(f"✅ All {len(required_files)} required files exist")
            return True
            
    except Exception as e:
        print(f"❌ File structure check failed: {e}")
        return False


def quick_component_test() -> bool:
    """Quick test of key components."""
    try:
        print("🔧 Quick component functionality test...")
        
        # Test imports
        try:
            from engine.smart_lane.strategy import PositionSizer, ExitStrategyManager
            print("✅ Strategy component imports successful")
        except ImportError as e:
            print(f"❌ Strategy import failed: {e}")
            return False
        
        # Test basic functionality
        try:
            # Position sizer test
            sizer = PositionSizer()
            result = sizer.calculate_position_size(
                analysis_confidence=0.7,
                overall_risk_score=0.4
            )
            
            if hasattr(result, 'recommended_size_percent'):
                print(f"✅ Position sizer working: {result.recommended_size_percent:.1f}%")
            else:
                print("❌ Position sizer returned invalid result")
                return False
            
            # Exit strategy manager test
            exit_manager = ExitStrategyManager()
            strategy = exit_manager.create_exit_strategy(risk_score=0.5)
            
            if hasattr(strategy, 'strategy_name') and hasattr(strategy, 'exit_levels'):
                print(f"✅ Exit manager working: {strategy.strategy_name}")
                print(f"   Exit levels: {len(strategy.exit_levels)}")
            else:
                print("❌ Exit manager returned invalid result")
                return False
            
            print("✅ Quick component test passed")
            return True
            
        except Exception as e:
            print(f"❌ Component test failed: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Quick test failed: {e}")
        return False


if __name__ == "__main__":
    """Run validation tests when executed directly."""
    try:
        print("🚀 Smart Lane Phase 5 Validation")
        print("=" * 50)
        
        # Quick checks first
        print("\n1️⃣ File Structure Check:")
        file_check = check_file_structure()
        
        print("\n2️⃣ Quick Component Test:")
        component_check = quick_component_test()
        
        print("\n3️⃣ Full Test Suite:")
        full_test = run_manual_tests()
        
        print("\n" + "=" * 50)
        print("🏁 FINAL RESULT")
        print("=" * 50)
        
        if file_check and component_check and full_test:
            print("🎉 SUCCESS: Smart Lane Phase 5 is ready!")
            print("✅ All critical components operational")
            print("✅ Strategy components working correctly")
            print("✅ Error handling implemented")
            print("✅ Integration tests passed")
            print("\n📋 Next Steps:")
            print("   1. Enable Smart Lane in dashboard")
            print("   2. Run live integration tests") 
            print("   3. Begin user testing")
            exit_code = 0
        elif file_check and component_check:
            print("⚠️ PARTIAL SUCCESS: Core components working")
            print("✅ Basic functionality operational") 
            print("⚠️ Some advanced features may have issues")
            print("\n📋 Recommended:")
            print("   1. Review test results above")
            print("   2. Address any warnings")
            print("   3. Re-run full test suite")
            exit_code = 0
        else:
            print("❌ FAILURE: Critical issues detected")
            print("❌ Phase 5 implementation needs attention")
            print("\n📋 Required Actions:")
            print("   1. Check file structure issues")
            print("   2. Fix component errors")
            print("   3. Re-run tests")
            exit_code = 1
        
        exit(exit_code)
        
    except Exception as e:
        print(f"💥 Test runner failed: {e}")
        exit(1)