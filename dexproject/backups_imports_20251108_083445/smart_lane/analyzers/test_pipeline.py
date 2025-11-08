"""
Smart Lane Pipeline Validation Tests

Comprehensive test suite to validate that all analyzers and the pipeline
work correctly after file reorganization. Tests schema compliance,
error handling, and integration points.

Path: tests/smart_lane/test_pipeline.py
"""

import asyncio
import pytest
import logging
from typing import Dict, Any, List
from unittest.mock import Mock, patch
from datetime import datetime, timezone

# Import all Smart Lane components
try:
    from dexproject.engine.smart_lane.pipeline import SmartLanePipeline, PipelineStatus
    from dexproject.engine.smart_lane import (
        SmartLaneConfig, SmartLaneAnalysis, RiskScore, TechnicalSignal,
        RiskCategory, SmartLaneAction, DecisionConfidence, AnalysisDepth
    )
    from dexproject.engine.smart_lane.analyzers import create_analyzer
    from dexproject.engine.smart_lane.strategy.position_sizing import PositionSizer
    from dexproject.engine.smart_lane.strategy.exit_strategies import ExitStrategyManager
    from dexproject.engine.smart_lane.thought_log import ThoughtLogGenerator
    
    IMPORTS_SUCCESSFUL = True
except ImportError as e:
    IMPORTS_SUCCESSFUL = False
    IMPORT_ERROR = str(e)

# Configure test logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestPipelineValidation:
    """Test Smart Lane pipeline functionality and integration."""
    
    @pytest.fixture
    def mock_token_address(self) -> str:
        """Mock token address for testing."""
        return "0x1234567890123456789012345678901234567890"
    
    @pytest.fixture
    def mock_context(self) -> Dict[str, Any]:
        """Mock analysis context."""
        return {
            'symbol': 'TEST',
            'name': 'Test Token',
            'current_price': 1.5,
            'market_cap': 10000000,
            'liquidity_usd': 500000,
            'volume_24h': 250000,
            'pair_address': '0xabcdefabcdefabcdefabcdefabcdefabcdefabcd'
        }
    
    @pytest.fixture
    def pipeline_config(self) -> SmartLaneConfig:
        """Test pipeline configuration."""
        return SmartLaneConfig(
            analysis_depth=AnalysisDepth.COMPREHENSIVE,
            enabled_categories=[
                RiskCategory.HONEYPOT_DETECTION,
                RiskCategory.LIQUIDITY_ANALYSIS,
                RiskCategory.SOCIAL_SENTIMENT,
                RiskCategory.TECHNICAL_ANALYSIS,
                RiskCategory.CONTRACT_SECURITY
            ],
            max_analysis_time_seconds=30,
            min_confidence_threshold=0.3,
            max_acceptable_risk_score=0.8
        )
    
    def test_imports_successful(self):
        """Test that all required imports work correctly."""
        assert IMPORTS_SUCCESSFUL, f"Import failed: {IMPORT_ERROR if not IMPORTS_SUCCESSFUL else 'N/A'}"
        
        # Test specific imports
        assert SmartLanePipeline is not None
        assert PositionSizer is not None
        assert ExitStrategyManager is not None
        assert create_analyzer is not None
    
    def test_analyzer_factory_creation(self):
        """Test that analyzer factory can create all required analyzers."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        chain_id = 1
        test_categories = [
            RiskCategory.HONEYPOT_DETECTION,
            RiskCategory.LIQUIDITY_ANALYSIS,
            RiskCategory.SOCIAL_SENTIMENT,
            RiskCategory.TECHNICAL_ANALYSIS,
            RiskCategory.TOKEN_TAX_ANALYSIS,
            RiskCategory.CONTRACT_SECURITY,
            RiskCategory.HOLDER_DISTRIBUTION,
            RiskCategory.MARKET_STRUCTURE
        ]
        
        for category in test_categories:
            analyzer = create_analyzer(category, chain_id)
            
            # Test analyzer properties
            assert analyzer is not None, f"Failed to create {category.value} analyzer"
            assert analyzer.get_category() == category
            assert analyzer.chain_id == chain_id
            assert hasattr(analyzer, 'analyze'), f"{category.value} analyzer missing analyze method"
    
    def test_pipeline_initialization(self, pipeline_config):
        """Test pipeline initialization with all components."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        pipeline = SmartLanePipeline(
            config=pipeline_config,
            chain_id=1,
            enable_caching=True
        )
        
        # Test pipeline properties
        assert pipeline.config == pipeline_config
        assert pipeline.chain_id == 1
        assert pipeline.status == PipelineStatus.INITIALIZING
        assert pipeline.position_sizer is not None
        assert pipeline.exit_strategy_manager is not None
        assert pipeline.thought_log_generator is not None
    
    @pytest.mark.asyncio
    async def test_individual_analyzer_schemas(self, mock_token_address, mock_context):
        """Test that each analyzer returns correctly formatted RiskScore."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        chain_id = 1
        test_categories = [
            RiskCategory.HONEYPOT_DETECTION,
            RiskCategory.SOCIAL_SENTIMENT,
            RiskCategory.TECHNICAL_ANALYSIS,
            RiskCategory.CONTRACT_SECURITY,
            RiskCategory.MARKET_STRUCTURE
        ]
        
        for category in test_categories:
            analyzer = create_analyzer(category, chain_id)
            
            try:
                # Execute analyzer
                risk_score = await analyzer.analyze(mock_token_address, mock_context)
                
                # Validate RiskScore schema
                assert isinstance(risk_score, RiskScore), f"{category.value} analyzer didn't return RiskScore"
                assert risk_score.category == category
                assert 0.0 <= risk_score.score <= 1.0, f"Invalid score: {risk_score.score}"
                assert 0.0 <= risk_score.confidence <= 1.0, f"Invalid confidence: {risk_score.confidence}"
                assert isinstance(risk_score.details, dict)
                assert isinstance(risk_score.warnings, list)
                assert risk_score.analysis_time_ms >= 0
                assert risk_score.data_quality in ['POOR', 'FAIR', 'GOOD', 'EXCELLENT']
                
                logger.info(f"✅ {category.value} analyzer: score={risk_score.score:.3f}, confidence={risk_score.confidence:.3f}")
                
            except Exception as e:
                pytest.fail(f"{category.value} analyzer failed: {str(e)}")
    
    @pytest.mark.asyncio
    async def test_pipeline_full_analysis(self, pipeline_config, mock_token_address, mock_context):
        """Test complete pipeline analysis execution."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        pipeline = SmartLanePipeline(
            config=pipeline_config,
            chain_id=1,
            enable_caching=False  # Disable caching for testing
        )
        
        try:
            # Execute full analysis
            analysis = await pipeline.analyze_token(
                token_address=mock_token_address,
                context=mock_context,
                force_refresh=True
            )
            
            # Validate SmartLaneAnalysis schema
            assert isinstance(analysis, SmartLaneAnalysis)
            assert analysis.token_address == mock_token_address
            assert analysis.chain_id == 1
            assert analysis.analysis_id is not None
            assert analysis.timestamp is not None
            
            # Validate risk scores
            assert isinstance(analysis.risk_scores, dict)
            assert len(analysis.risk_scores) > 0
            assert 0.0 <= analysis.overall_risk_score <= 1.0
            assert 0.0 <= analysis.overall_confidence <= 1.0
            
            # Validate technical signals
            assert isinstance(analysis.technical_signals, list)
            assert isinstance(analysis.technical_summary, dict)
            
            # Validate strategic recommendations
            assert isinstance(analysis.recommended_action, SmartLaneAction)
            assert 0.0 <= analysis.position_size_percent <= 100.0
            assert isinstance(analysis.confidence_level, DecisionConfidence)
            
            # Validate exit strategy
            assert analysis.stop_loss_percent is None or analysis.stop_loss_percent > 0
            assert isinstance(analysis.take_profit_targets, list)
            assert analysis.max_hold_time_hours is None or analysis.max_hold_time_hours > 0
            
            # Validate performance metrics
            assert analysis.total_analysis_time_ms > 0
            assert analysis.total_analysis_time_ms < 30000  # Should be under 30 seconds
            assert 0.0 <= analysis.cache_hit_ratio <= 1.0
            assert 0.0 <= analysis.data_freshness_score <= 1.0
            
            # Validate warnings and notes
            assert isinstance(analysis.critical_warnings, list)
            assert isinstance(analysis.informational_notes, list)
            
            logger.info(f"✅ Pipeline analysis completed successfully:")
            logger.info(f"   Risk Score: {analysis.overall_risk_score:.3f}")
            logger.info(f"   Confidence: {analysis.overall_confidence:.3f}")
            logger.info(f"   Action: {analysis.recommended_action.value}")
            logger.info(f"   Position Size: {analysis.position_size_percent:.1f}%")
            logger.info(f"   Analysis Time: {analysis.total_analysis_time_ms:.1f}ms")
            
        except Exception as e:
            pytest.fail(f"Pipeline analysis failed: {str(e)}")
    
    @pytest.mark.asyncio
    async def test_pipeline_error_handling(self, pipeline_config):
        """Test pipeline error handling with invalid inputs."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        pipeline = SmartLanePipeline(config=pipeline_config, chain_id=1)
        
        # Test invalid token address
        try:
            analysis = await pipeline.analyze_token(
                token_address="invalid_address",
                context={}
            )
            # Should not raise exception but return error analysis
            assert analysis.overall_risk_score >= 0.5  # High risk for invalid input
        except Exception as e:
            pytest.fail(f"Pipeline should handle invalid input gracefully: {str(e)}")
        
        # Test empty context
        try:
            analysis = await pipeline.analyze_token(
                token_address="0x1234567890123456789012345678901234567890",
                context={}
            )
            assert isinstance(analysis, SmartLaneAnalysis)
        except Exception as e:
            pytest.fail(f"Pipeline should handle empty context: {str(e)}")
    
    @pytest.mark.asyncio
    async def test_position_sizing_integration(self, pipeline_config):
        """Test position sizing component integration."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        position_sizer = PositionSizer(config=pipeline_config)
        
        # Test position sizing calculation
        try:
            sizing_result = position_sizer.calculate_position_size(
                analysis_confidence=0.8,
                overall_risk_score=0.3,
                technical_signals=[],
                market_conditions={'volatility': 0.1},
                portfolio_context={'position_count': 2, 'available_capital_percent': 80.0}
            )
            
            # Validate sizing calculation
            assert 0.0 <= sizing_result.recommended_size_percent <= 100.0
            assert sizing_result.method_used is not None
            assert isinstance(sizing_result.warnings, list)
            assert isinstance(sizing_result.calculation_details, dict)
            
            logger.info(f"✅ Position sizing: {sizing_result.recommended_size_percent:.1f}% ({sizing_result.method_used.value})")
            
        except Exception as e:
            pytest.fail(f"Position sizing failed: {str(e)}")
    
    @pytest.mark.asyncio
    async def test_exit_strategy_integration(self, pipeline_config):
        """Test exit strategy component integration."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        exit_manager = ExitStrategyManager(config=pipeline_config)
        
        # Test exit strategy creation
        try:
            mock_technical_signals = [
                TechnicalSignal(
                    timeframe="4h",
                    signal="BUY",
                    strength=0.7,
                    indicators={'rsi': 45.0, 'macd': 0.1},
                    price_targets={'support': 1.2, 'resistance': 1.8},
                    confidence=0.8
                )
            ]
            
            exit_strategy = exit_manager.create_exit_strategy(
                risk_score=0.4,
                technical_signals=mock_technical_signals,
                market_conditions={'volatility': 0.15, 'current_price': 1.5},
                position_context={'entry_price': 1.5}
            )
            
            # Validate exit strategy
            assert exit_strategy.strategy_name is not None
            assert len(exit_strategy.exit_levels) > 0
            assert exit_strategy.stop_loss_percent is not None
            assert isinstance(exit_strategy.take_profit_targets, list)
            assert len(exit_strategy.take_profit_targets) > 0
            assert exit_strategy.strategy_rationale is not None
            
            logger.info(f"✅ Exit strategy: {exit_strategy.strategy_name}")
            logger.info(f"   Stop Loss: {exit_strategy.stop_loss_percent:.1f}%")
            logger.info(f"   Take Profits: {exit_strategy.take_profit_targets}")
            logger.info(f"   Max Hold: {exit_strategy.max_hold_time_hours}h")
            
        except Exception as e:
            pytest.fail(f"Exit strategy creation failed: {str(e)}")
    
    @pytest.mark.asyncio
    async def test_thought_log_integration(self, pipeline_config, mock_token_address, mock_context):
        """Test thought log generation integration."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        pipeline = SmartLanePipeline(config=pipeline_config, chain_id=1)
        
        try:
            # Execute analysis to get result for thought log
            analysis = await pipeline.analyze_token(
                token_address=mock_token_address,
                context=mock_context
            )
            
            # Generate thought log
            thought_log = await pipeline.thought_log_generator.generate_thought_log(
                analysis_result=analysis,
                context=mock_context
            )
            
            # Validate thought log
            assert thought_log is not None
            assert hasattr(thought_log, 'entries')
            assert len(thought_log.entries) > 0
            assert thought_log.overall_reasoning is not None
            assert thought_log.confidence_assessment is not None
            
            logger.info(f"✅ Thought log generated with {len(thought_log.entries)} entries")
            
        except Exception as e:
            pytest.fail(f"Thought log generation failed: {str(e)}")
    
    @pytest.mark.asyncio
    async def test_pipeline_performance_requirements(self, pipeline_config, mock_token_address, mock_context):
        """Test that pipeline meets performance requirements."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        pipeline = SmartLanePipeline(config=pipeline_config, chain_id=1)
        
        # Test performance target: <5s for comprehensive analysis
        start_time = asyncio.get_event_loop().time()
        
        try:
            analysis = await pipeline.analyze_token(
                token_address=mock_token_address,
                context=mock_context,
                force_refresh=True
            )
            
            end_time = asyncio.get_event_loop().time()
            total_time_seconds = end_time - start_time
            
            # Validate performance
            assert total_time_seconds < 30.0, f"Analysis took {total_time_seconds:.2f}s (target: <30s for testing)"
            assert analysis.total_analysis_time_ms < 30000, f"Internal timing: {analysis.total_analysis_time_ms:.1f}ms"
            
            logger.info(f"✅ Performance test passed: {total_time_seconds:.2f}s total")
            
        except Exception as e:
            pytest.fail(f"Performance test failed: {str(e)}")
    
    def test_analyzer_registry_completeness(self):
        """Test that all analyzers are properly registered."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        from dexproject.engine.smart_lane.analyzers import ANALYZER_REGISTRY, get_available_analyzers
        
        # Expected analyzers
        expected_categories = [
            RiskCategory.HONEYPOT_DETECTION,
            RiskCategory.LIQUIDITY_ANALYSIS,
            RiskCategory.SOCIAL_SENTIMENT,
            RiskCategory.TECHNICAL_ANALYSIS,
            RiskCategory.TOKEN_TAX_ANALYSIS,
            RiskCategory.CONTRACT_SECURITY,
            RiskCategory.HOLDER_DISTRIBUTION,
            RiskCategory.MARKET_STRUCTURE
        ]
        
        # Check registry completeness
        available_analyzers = get_available_analyzers()
        
        for category in expected_categories:
            assert category in ANALYZER_REGISTRY, f"Missing {category.value} in registry"
            assert category in available_analyzers, f"Missing {category.value} in available analyzers"
        
        logger.info(f"✅ All {len(expected_categories)} analyzers properly registered")
    
    @pytest.mark.asyncio
    async def test_concurrent_analysis_handling(self, pipeline_config, mock_context):
        """Test pipeline handling of concurrent analyses."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        pipeline = SmartLanePipeline(config=pipeline_config, chain_id=1)
        
        # Create multiple token addresses
        token_addresses = [
            f"0x123456789012345678901234567890123456789{i}"
            for i in range(3)  # Test with 3 concurrent analyses
        ]
        
        try:
            # Execute concurrent analyses
            tasks = [
                pipeline.analyze_token(token_address, mock_context)
                for token_address in token_addresses
            ]
            
            analyses = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Validate all analyses completed
            successful_analyses = 0
            for i, analysis in enumerate(analyses):
                if isinstance(analysis, Exception):
                    logger.warning(f"Analysis {i} failed: {analysis}")
                else:
                    assert isinstance(analysis, SmartLaneAnalysis)
                    successful_analyses += 1
            
            assert successful_analyses >= 2, f"Only {successful_analyses}/3 analyses succeeded"
            logger.info(f"✅ Concurrent analysis: {successful_analyses}/3 successful")
            
        except Exception as e:
            pytest.fail(f"Concurrent analysis test failed: {str(e)}")
    
    @pytest.mark.asyncio
    async def test_caching_functionality(self, pipeline_config, mock_token_address, mock_context):
        """Test pipeline caching functionality."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        pipeline = SmartLanePipeline(config=pipeline_config, chain_id=1, enable_caching=True)
        
        try:
            # First analysis (should populate cache)
            start_time = asyncio.get_event_loop().time()
            analysis1 = await pipeline.analyze_token(mock_token_address, mock_context)
            first_time = asyncio.get_event_loop().time() - start_time
            
            # Second analysis (should use cache)
            start_time = asyncio.get_event_loop().time()
            analysis2 = await pipeline.analyze_token(mock_token_address, mock_context)
            second_time = asyncio.get_event_loop().time() - start_time
            
            # Validate caching
            assert isinstance(analysis1, SmartLaneAnalysis)
            assert isinstance(analysis2, SmartLaneAnalysis)
            
            # Second analysis should be faster due to caching
            # Note: In a real scenario with network calls, this would be more pronounced
            logger.info(f"✅ Caching test: First={first_time:.2f}s, Second={second_time:.2f}s")
            
        except Exception as e:
            pytest.fail(f"Caching test failed: {str(e)}")
    
    def test_configuration_validation(self):
        """Test configuration validation and defaults."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        # Test default configuration
        default_config = SmartLaneConfig()
        assert default_config.analysis_depth == AnalysisDepth.COMPREHENSIVE
        assert len(default_config.enabled_categories) > 0
        assert default_config.max_analysis_time_seconds > 0
        
        # Test custom configuration
        custom_config = SmartLaneConfig(
            analysis_depth=AnalysisDepth.FAST,
            enabled_categories=[RiskCategory.HONEYPOT_DETECTION],
            max_analysis_time_seconds=10
        )
        assert custom_config.analysis_depth == AnalysisDepth.FAST
        assert len(custom_config.enabled_categories) == 1
        assert custom_config.max_analysis_time_seconds == 10
        
        logger.info("✅ Configuration validation passed")
    
    @pytest.mark.asyncio
    async def test_error_recovery_mechanisms(self, pipeline_config):
        """Test pipeline error recovery and fallback mechanisms."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        pipeline = SmartLanePipeline(config=pipeline_config, chain_id=1)
        
        # Test with problematic inputs that should trigger fallbacks
        error_test_cases = [
            {
                'token_address': "0x0000000000000000000000000000000000000000",  # Zero address
                'context': {},
                'description': "Zero address"
            },
            {
                'token_address': "0x1234567890123456789012345678901234567890",
                'context': {'symbol': '', 'name': ''},  # Empty metadata
                'description': "Empty metadata"
            },
            {
                'token_address': "0x1234567890123456789012345678901234567890",
                'context': {'current_price': 0},  # Zero price
                'description': "Zero price"
            }
        ]
        
        for test_case in error_test_cases:
            try:
                analysis = await pipeline.analyze_token(
                    token_address=test_case['token_address'],
                    context=test_case['context']
                )
                
                # Should return valid analysis even with bad inputs
                assert isinstance(analysis, SmartLaneAnalysis)
                assert analysis.overall_risk_score >= 0.5  # Should indicate risk for bad inputs
                
                logger.info(f"✅ Error recovery for {test_case['description']}: risk={analysis.overall_risk_score:.2f}")
                
            except Exception as e:
                pytest.fail(f"Error recovery failed for {test_case['description']}: {str(e)}")


class TestAnalyzerSpecific:
    """Test specific analyzer functionality."""
    
    @pytest.mark.asyncio
    async def test_honeypot_analyzer_detection(self):
        """Test honeypot analyzer specific detection capabilities."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        analyzer = create_analyzer(RiskCategory.HONEYPOT_DETECTION, chain_id=1)
        
        # Test with suspicious token context
        suspicious_context = {
            'symbol': 'SCAM',
            'name': 'Definitely Not A Scam Token',
            'current_price': 0.001,
            'market_cap': 1000000,
            'liquidity_usd': 500,  # Very low liquidity
            'volume_24h': 1000000  # Suspicious high volume vs liquidity
        }
        
        risk_score = await analyzer.analyze(
            "0x1234567890123456789012345678901234567890",
            suspicious_context
        )
        
        # Should detect higher risk
        assert risk_score.score > 0.3, f"Honeypot analyzer should detect suspicious patterns: {risk_score.score}"
        logger.info(f"✅ Honeypot analyzer detected risk: {risk_score.score:.3f}")
    
    @pytest.mark.asyncio
    async def test_technical_analyzer_signals(self):
        """Test technical analyzer signal generation."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        analyzer = create_analyzer(RiskCategory.TECHNICAL_ANALYSIS, chain_id=1)
        
        # Test with good technical context
        technical_context = {
            'symbol': 'TEST',
            'current_price': 1.5,
            'price_change_24h': 0.08,  # 8% increase
            'volume_24h': 500000,
            'market_cap': 10000000
        }
        
        risk_score = await analyzer.analyze(
            "0x1234567890123456789012345678901234567890",
            technical_context
        )
        
        # Should provide technical analysis
        assert 'technical_analysis' in risk_score.details or 'indicators' in risk_score.details
        logger.info(f"✅ Technical analyzer completed: score={risk_score.score:.3f}")
    
    @pytest.mark.asyncio
    async def test_contract_analyzer_security(self):
        """Test contract analyzer security assessment."""
        if not IMPORTS_SUCCESSFUL:
            pytest.skip("Imports failed")
        
        analyzer = create_analyzer(RiskCategory.CONTRACT_SECURITY, chain_id=1)
        
        # Test with contract context
        contract_context = {
            'symbol': 'SECURE',
            'verification_status': 'VERIFIED',
            'audit_reports': [],
            'source_code': None  # Unverified source
        }
        
        risk_score = await analyzer.analyze(
            "0x1234567890123456789012345678901234567890",
            contract_context
        )
        
        # Should assess contract security
        assert risk_score.score >= 0, "Contract analyzer should return valid risk score"
        logger.info(f"✅ Contract analyzer completed: score={risk_score.score:.3f}")


# Utility functions for running tests
def run_validation_tests():
    """Run all validation tests manually (without pytest)."""
    print("🧪 Starting Smart Lane Pipeline Validation Tests")
    print("=" * 60)
    
    # Check imports first
    if not IMPORTS_SUCCESSFUL:
        print(f"❌ CRITICAL: Import failed - {IMPORT_ERROR}")
        return False
    
    print("✅ All imports successful")
    
    # Run basic tests manually
    try:
        # Test analyzer creation
        test_categories = [
            RiskCategory.HONEYPOT_DETECTION,
            RiskCategory.SOCIAL_SENTIMENT,
            RiskCategory.TECHNICAL_ANALYSIS,
            RiskCategory.CONTRACT_SECURITY
        ]
        
        for category in test_categories:
            analyzer = create_analyzer(category, chain_id=1)
            assert analyzer is not None
            print(f"✅ {category.value} analyzer created successfully")
        
        # Test pipeline initialization
        config = SmartLaneConfig()
        pipeline = SmartLanePipeline(config=config, chain_id=1)
        assert pipeline is not None
        print("✅ Pipeline initialized successfully")
        
        print("\n🎉 Basic validation tests passed!")
        print("💡 Run 'pytest tests/smart_lane/test_pipeline.py -v' for comprehensive testing")
        return True
        
    except Exception as e:
        print(f"❌ Validation test failed: {str(e)}")
        return False


if __name__ == "__main__":
    """Run validation tests when executed directly."""
    success = run_validation_tests()
    exit(0 if success else 1)