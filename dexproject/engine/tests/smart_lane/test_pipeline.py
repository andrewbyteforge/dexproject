"""
Smart Lane Pipeline Validation Tests

Comprehensive test suite to validate Smart Lane implementation.
Includes Django setup and proper import paths.

Path: tests/smart_lane/test_pipeline.py
"""

import sys
import os
import asyncio
import django
from pathlib import Path
from typing import Dict, Any, List
import logging

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Setup Django before any project imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_imports():
    """Test that all required imports work correctly."""
    try:
        from engine.smart_lane.pipeline import SmartLanePipeline
        from engine.smart_lane import SmartLaneConfig, RiskCategory
        from engine.smart_lane.analyzers import create_analyzer
        from engine.smart_lane.strategy.position_sizing import PositionSizer
        from engine.smart_lane.strategy.exit_strategies import ExitStrategyManager
        from engine.smart_lane.thought_log import ThoughtLogGenerator
        
        print("✅ All imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False


def test_analyzer_creation():
    """Test analyzer factory creation."""
    try:
        from engine.smart_lane.analyzers import create_analyzer
        from engine.smart_lane import RiskCategory
        
        # Test creating all analyzer types
        categories = [
            RiskCategory.HONEYPOT_DETECTION,
            RiskCategory.LIQUIDITY_ANALYSIS,
            RiskCategory.SOCIAL_SENTIMENT,
            RiskCategory.TECHNICAL_ANALYSIS,
            RiskCategory.TOKEN_TAX_ANALYSIS,
            RiskCategory.CONTRACT_SECURITY,
            RiskCategory.HOLDER_DISTRIBUTION,
            RiskCategory.MARKET_STRUCTURE
        ]
        
        for category in categories:
            analyzer = create_analyzer(category, chain_id=1)
            assert analyzer is not None, f"Failed to create {category.value} analyzer"
            print(f"✅ Created {category.value} analyzer")
        
        return True
    except Exception as e:
        print(f"❌ Analyzer creation failed: {e}")
        return False


def test_pipeline_initialization():
    """Test pipeline initialization with all components."""
    try:
        from engine.smart_lane.pipeline import SmartLanePipeline
        from engine.smart_lane import SmartLaneConfig
        
        config = SmartLaneConfig()
        pipeline = SmartLanePipeline(config=config, chain_id=1)
        
        assert pipeline is not None
        assert pipeline.position_sizer is not None
        assert pipeline.exit_strategy_manager is not None
        assert hasattr(pipeline, 'thought_log_generator')
        
        print("✅ Pipeline initialized successfully with all components")
        return True
    except Exception as e:
        print(f"❌ Pipeline initialization failed: {e}")
        return False


async def test_basic_analysis():
    """Test basic analysis execution."""
    try:
        from engine.smart_lane.pipeline import SmartLanePipeline
        from engine.smart_lane import SmartLaneConfig
        
        config = SmartLaneConfig()
        pipeline = SmartLanePipeline(config=config, chain_id=1)
        
        # Mock context with realistic data
        context = {
            'symbol': 'TEST',
            'name': 'Test Token',
            'current_price': 1.5,
            'market_cap': 5000000,
            'liquidity_usd': 250000,
            'volume_24h': 100000,
            'pair_address': '0xabcdefabcdefabcdefabcdefabcdefabcdefabcd'
        }
        
        # Execute analysis
        analysis = await pipeline.analyze_token(
            token_address="0x1234567890123456789012345678901234567890",
            context=context
        )
        
        # Validate analysis result
        assert analysis is not None
        assert hasattr(analysis, 'overall_risk_score')
        assert hasattr(analysis, 'recommended_action')
        assert hasattr(analysis, 'confidence_score')
        assert 0 <= analysis.overall_risk_score <= 1
        assert 0 <= analysis.confidence_score <= 1
        
        print(f"✅ Basic analysis completed:")
        print(f"   - Risk Score: {analysis.overall_risk_score:.3f}")
        print(f"   - Action: {analysis.recommended_action}")
        print(f"   - Confidence: {analysis.confidence_score:.1%}")
        
        return True
    except Exception as e:
        print(f"❌ Basic analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_strategy_components():
    """Test strategy components independently."""
    try:
        from engine.smart_lane.strategy.position_sizing import PositionSizer, SizingCalculation
        from engine.smart_lane.strategy.exit_strategies import ExitStrategyManager, ExitStrategy
        from engine.smart_lane import SmartLaneConfig, TechnicalSignal
        
        config = SmartLaneConfig()
        
        # Test position sizer
        position_sizer = PositionSizer(config)
        
        sizing = position_sizer.calculate_position_size(
            analysis_confidence=0.8,
            overall_risk_score=0.3,
            technical_signals=[],
            market_conditions={'volatility': 0.1, 'liquidity_score': 0.8},
            portfolio_context={'position_count': 2, 'available_capital_percent': 90}
        )
        
        assert isinstance(sizing, SizingCalculation)
        assert 0 <= sizing.recommended_size_percent <= 100
        print(f"✅ Position sizing: {sizing.recommended_size_percent:.1f}%")
        print(f"   - Method: {sizing.sizing_method_used.value}")
        print(f"   - Rationale: {sizing.sizing_rationale[:100]}...")
        
        # Test exit strategy manager
        exit_manager = ExitStrategyManager(config)
        
        strategy = exit_manager.create_exit_strategy(
            risk_score=0.4,
            technical_signals=[],
            market_conditions={'volatility': 0.15, 'trend_strength': 0.6},
            position_context={'entry_price': 1.5, 'position_size_percent': 5}
        )
        
        assert isinstance(strategy, ExitStrategy)
        assert strategy.stop_loss_percent is not None
        assert len(strategy.take_profit_targets) > 0
        
        print(f"✅ Exit strategy: {strategy.strategy_name}")
        print(f"   - Stop Loss: {strategy.stop_loss_percent:.1f}%")
        print(f"   - Take Profits: {strategy.take_profit_targets}")
        print(f"   - Risk/Reward: {strategy.risk_reward_ratio:.2f}")
        
        return True
    except Exception as e:
        print(f"❌ Strategy components failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_thought_log_generation():
    """Test thought log generation."""
    try:
        from engine.smart_lane.thought_log import ThoughtLogGenerator, ThoughtLogLevel
        from engine.smart_lane import SmartLaneAnalysis, SmartLaneAction, DecisionConfidence
        import uuid
        
        # Create generator
        generator = ThoughtLogGenerator()
        
        # Create mock analysis result
        mock_analysis = SmartLaneAnalysis(
            analysis_id=str(uuid.uuid4()),
            token_address="0x1234567890123456789012345678901234567890",
            chain_id=1,
            overall_risk_score=0.35,
            confidence_score=0.75,
            recommended_action=SmartLaneAction.BUY,
            confidence_level=DecisionConfidence.HIGH,
            position_size_percent=5.0,
            stop_loss_percent=10.0,
            take_profit_targets=[15.0, 25.0, 40.0],
            max_hold_time_hours=168,
            risk_scores=[],
            technical_signals=[],
            analysis_timestamp="2024-01-01T00:00:00Z",
            execution_time_ms=2500,
            thought_log=None
        )
        
        # Generate thought log
        thought_log = await generator.generate_thought_log(
            analysis_result={'analysis': mock_analysis.__dict__},
            level=ThoughtLogLevel.DETAILED
        )
        
        assert thought_log is not None
        assert thought_log.analysis_id == mock_analysis.analysis_id
        assert thought_log.confidence_score > 0
        assert len(thought_log.key_opportunities) > 0 or len(thought_log.key_risks) > 0
        
        print("✅ Thought log generated successfully")
        print(f"   - Executive Summary: {thought_log.executive_summary[:100]}...")
        print(f"   - Confidence: {thought_log.confidence_score:.1f}%")
        print(f"   - Generation Time: {thought_log.generation_time_ms:.1f}ms")
        
        return True
    except Exception as e:
        print(f"❌ Thought log generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_file_structure():
    """Check that all required files exist."""
    required_files = [
        'engine/smart_lane/__init__.py',
        'engine/smart_lane/pipeline.py',
        'engine/smart_lane/thought_log.py',
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
    
    missing_files = []
    for file_path in required_files:
        full_path = project_root / file_path
        if not full_path.exists():
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ Missing files:")
        for file_path in missing_files:
            print(f"   - {file_path}")
        return False
    else:
        print("✅ All required files exist")
        return True


def run_all_tests():
    """Run all validation tests."""
    print("=" * 60)
    print("🧪 SMART LANE VALIDATION TEST SUITE")
    print("=" * 60)
    
    # Check file structure first
    print("\n📁 Checking file structure...")
    if not check_file_structure():
        print("\n❌ File structure check failed. Please create missing files.")
        return False
    
    # Run synchronous tests
    tests = [
        ("Import Test", test_imports),
        ("Analyzer Creation", test_analyzer_creation),
        ("Pipeline Initialization", test_pipeline_initialization),
        ("Strategy Components", test_strategy_components)
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\n🔍 Running {test_name}...")
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test_name} error: {e}")
            failed += 1
    
    # Run async tests
    async_tests = [
        ("Basic Analysis", test_basic_analysis),
        ("Thought Log Generation", test_thought_log_generation)
    ]
    
    print("\n🔄 Running async tests...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    for test_name, test_func in async_tests:
        print(f"\n🔍 Running {test_name}...")
        try:
            if loop.run_until_complete(test_func()):
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test_name} error: {e}")
            failed += 1
    
    loop.close()
    
    # Print summary
    total = passed + failed
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)
    print(f"Total Tests: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Success Rate: {(passed/total)*100:.1f}%")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! Smart Lane is ready for integration.")
        print("\n📋 Next Steps:")
        print("1. Enable Smart Lane in dashboard configuration forms")
        print("2. Add thought log display component to dashboard")
        print("3. Create API endpoints for Smart Lane analysis")
        print("4. Test with live data on testnet")
        return True
    else:
        print("\n⚠️ Some tests failed. Please review the errors above.")
        print("Common issues:")
        print("- Missing analyzer implementations")
        print("- Import path problems")
        print("- Missing dependencies")
        return False


if __name__ == "__main__":
    """Run validation tests when executed directly."""
    success = run_all_tests()
    exit(0 if success else 1)