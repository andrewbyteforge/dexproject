"""
Smart Lane Pipeline Validation Tests

Basic validation tests to ensure pipeline components work correctly.
Fixed for Django project structure.

Path: tests/smart_lane/test_pipeline.py
"""

import sys
import os
import asyncio
import django
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

def test_imports():
    """Test that all required imports work correctly."""
    try:
        from engine.smart_lane.pipeline import SmartLanePipeline
        from engine.smart_lane import SmartLaneConfig, RiskCategory
        from engine.smart_lane.analyzers import create_analyzer
        from engine.smart_lane.strategy.position_sizing import PositionSizer
        from engine.smart_lane.strategy.exit_strategies import ExitStrategyManager
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
        
        # Test creating a few analyzers
        categories = [
            RiskCategory.HONEYPOT_DETECTION,
            RiskCategory.SOCIAL_SENTIMENT,
            RiskCategory.TECHNICAL_ANALYSIS
        ]
        
        for category in categories:
            analyzer = create_analyzer(category, chain_id=1)
            assert analyzer is not None
            print(f"✅ Created {category.value} analyzer")
        
        return True
    except Exception as e:
        print(f"❌ Analyzer creation failed: {e}")
        return False

def test_pipeline_initialization():
    """Test pipeline initialization."""
    try:
        from engine.smart_lane.pipeline import SmartLanePipeline
        from engine.smart_lane import SmartLaneConfig
        
        config = SmartLaneConfig()
        pipeline = SmartLanePipeline(config=config, chain_id=1)
        
        assert pipeline is not None
        assert pipeline.position_sizer is not None
        assert pipeline.exit_strategy_manager is not None
        
        print("✅ Pipeline initialized successfully")
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
        
        # Mock context
        context = {
            'symbol': 'TEST',
            'name': 'Test Token',
            'current_price': 1.0,
            'market_cap': 1000000
        }
        
        analysis = await pipeline.analyze_token(
            token_address="0x1234567890123456789012345678901234567890",
            context=context
        )
        
        assert analysis is not None
        assert hasattr(analysis, 'overall_risk_score')
        assert hasattr(analysis, 'recommended_action')
        
        print(f"✅ Basic analysis completed: risk={analysis.overall_risk_score:.3f}")
        return True
    except Exception as e:
        print(f"❌ Basic analysis failed: {e}")
        return False

def test_strategy_components():
    """Test strategy components independently."""
    try:
        from engine.smart_lane.strategy.position_sizing import PositionSizer, SizingCalculation
        from engine.smart_lane.strategy.exit_strategies import ExitStrategyManager, ExitStrategy
        from engine.smart_lane import SmartLaneConfig
        
        # Test position sizer
        config = SmartLaneConfig()
        position_sizer = PositionSizer(config)
        
        sizing = position_sizer.calculate_position_size(
            analysis_confidence=0.8,
            overall_risk_score=0.3,
            technical_signals=[],
            market_conditions={'volatility': 0.1},
            portfolio_context={'position_count': 2}
        )
        
        assert isinstance(sizing, SizingCalculation)
        assert 0 <= sizing.recommended_size_percent <= 100
        print(f"✅ Position sizing: {sizing.recommended_size_percent:.1f}%")
        
        # Test exit strategy manager
        exit_manager = ExitStrategyManager(config)
        
        strategy = exit_manager.create_exit_strategy(
            risk_score=0.4,
            technical_signals=[],
            market_conditions={'volatility': 0.15},
            position_context={'entry_price': 1.5}
        )
        
        assert isinstance(strategy, ExitStrategy)
        assert strategy.stop_loss_percent is not None
        print(f"✅ Exit strategy: {strategy.strategy_name}")
        
        return True
    except Exception as e:
        print(f"❌ Strategy components failed: {e}")
        return False

def check_file_structure():
    """Check that all required files exist."""
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
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ Missing files:")
        for file_path in missing_files:
            print(f"   - {file_path}")
        return False
    else:
        print("✅ All required files exist")
        return True

def run_manual_tests():
    """Run tests manually without pytest."""
    print("🧪 Running Smart Lane Validation Tests")
    print("=" * 50)
    
    # Check file structure first
    print(f"\n🔍 Checking file structure...")
    if not check_file_structure():
        print("❌ File structure check failed")
        return False
    
    tests = [
        ("Import Test", test_imports),
        ("Analyzer Creation", test_analyzer_creation),
        ("Pipeline Initialization", test_pipeline_initialization),
        ("Strategy Components", test_strategy_components)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 Running {test_name}...")
        try:
            if test_func():
                passed += 1
            else:
                print(f"❌ {test_name} failed")
        except Exception as e:
            print(f"❌ {test_name} error: {e}")
    
    # Run async test
    print(f"\n🔍 Running Basic Analysis Test...")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        if loop.run_until_complete(test_basic_analysis()):
            passed += 1
            total += 1
        loop.close()
    except Exception as e:
        print(f"❌ Basic analysis test error: {e}")
        total += 1
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Smart Lane is ready for dashboard integration.")
        return True
    else:
        print("⚠️  Some tests failed. Check the errors above.")
        return False

if __name__ == "__main__":
    """Run validation tests when executed directly."""
    success = run_manual_tests()
    exit(0 if success else 1)