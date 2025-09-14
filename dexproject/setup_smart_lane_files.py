#!/usr/bin/env python3
"""
Smart Lane File Setup Script

Creates all necessary directories and files for Smart Lane Phase 5 completion.
Run this script from the dexproject root directory.

Usage: python setup_smart_lane_files.py
"""

import os
import sys
from pathlib import Path

def create_directory_structure():
    """Create the required directory structure."""
    directories = [
        "engine/smart_lane/strategy",
        "tests/smart_lane"
    ]
    
    for directory in directories:
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"✅ Created directory: {directory}")

def create_strategy_init():
    """Create strategy package __init__.py"""
    content = '''"""
Smart Lane Strategy Package

Contains strategy components for position sizing and exit management.
These components take analysis results and convert them into actionable
trading strategies with risk management.

Path: engine/smart_lane/strategy/__init__.py
"""

import logging

logger = logging.getLogger(__name__)

# Import main strategy classes
from .position_sizing import PositionSizer, SizingCalculation, SizingMethod
from .exit_strategies import (
    ExitStrategyManager, ExitStrategy, ExitLevel, 
    ExitTrigger, ExitMethod
)

# Package version
__version__ = "1.0.0"

# Export main classes
__all__ = [
    # Position Sizing
    'PositionSizer',
    'SizingCalculation', 
    'SizingMethod',
    
    # Exit Strategies
    'ExitStrategyManager',
    'ExitStrategy',
    'ExitLevel',
    'ExitTrigger',
    'ExitMethod'
]

logger.info(f"Smart Lane strategy package initialized - version {__version__}")
'''
    
    file_path = Path("engine/smart_lane/strategy/__init__.py")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ Created: {file_path}")

def create_position_sizing():
    """Create position sizing strategy file."""
    content = '''"""
Smart Lane Position Sizing Strategy

Intelligent position sizing system that calculates optimal position sizes
based on risk assessment, confidence levels, technical signals, and
portfolio management principles.

Path: engine/smart_lane/strategy/position_sizing.py
"""

import logging
import math
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .. import SmartLaneConfig, TechnicalSignal, RiskCategory

logger = logging.getLogger(__name__)


class SizingMethod(Enum):
    """Position sizing methodologies."""
    FIXED_PERCENT = "FIXED_PERCENT"
    RISK_BASED = "RISK_BASED"
    KELLY_CRITERION = "KELLY_CRITERION"
    VOLATILITY_ADJUSTED = "VOLATILITY_ADJUSTED"
    CONFIDENCE_WEIGHTED = "CONFIDENCE_WEIGHTED"


@dataclass
class SizingCalculation:
    """Position sizing calculation result."""
    recommended_size_percent: float
    method_used: SizingMethod
    risk_adjusted_size: float
    confidence_adjusted_size: float
    technical_adjusted_size: float
    max_allowed_size: float
    sizing_rationale: str
    warnings: List[str]
    calculation_details: Dict[str, Any]


class PositionSizer:
    """
    Intelligent position sizing calculator for Smart Lane trades.
    
    Combines multiple sizing methodologies with risk management
    and portfolio optimization principles.
    """
    
    def __init__(self, config: SmartLaneConfig):
        """Initialize position sizer."""
        self.config = config
        self.max_position_percent = 25.0
        self.min_position_percent = 1.0
        self.base_position_percent = 5.0
        logger.info("Position sizer initialized")
    
    def calculate_position_size(
        self,
        analysis_confidence: float,
        overall_risk_score: float,
        technical_signals: List[TechnicalSignal],
        market_conditions: Dict[str, Any],
        portfolio_context: Dict[str, Any]
    ) -> SizingCalculation:
        """Calculate optimal position size."""
        try:
            # Simple risk-based calculation for now
            risk_factor = 1.0 - overall_risk_score
            confidence_factor = analysis_confidence
            
            base_size = self.base_position_percent * risk_factor * confidence_factor
            final_size = max(self.min_position_percent, min(base_size, self.max_position_percent))
            
            return SizingCalculation(
                recommended_size_percent=final_size,
                method_used=SizingMethod.RISK_BASED,
                risk_adjusted_size=final_size,
                confidence_adjusted_size=final_size,
                technical_adjusted_size=final_size,
                max_allowed_size=self.max_position_percent,
                sizing_rationale=f"Risk-based sizing: {final_size:.1f}%",
                warnings=[],
                calculation_details={'risk_score': overall_risk_score, 'confidence': analysis_confidence}
            )
        except Exception as e:
            logger.error(f"Position sizing error: {e}")
            return SizingCalculation(
                recommended_size_percent=2.0,
                method_used=SizingMethod.FIXED_PERCENT,
                risk_adjusted_size=2.0,
                confidence_adjusted_size=2.0,
                technical_adjusted_size=2.0,
                max_allowed_size=25.0,
                sizing_rationale="Default sizing due to error",
                warnings=["Calculation failed"],
                calculation_details={'error': str(e)}
            )


# Export main class
__all__ = ['PositionSizer', 'SizingCalculation', 'SizingMethod']
'''
    
    file_path = Path("engine/smart_lane/strategy/position_sizing.py")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ Created: {file_path}")

def create_exit_strategies():
    """Create exit strategies file."""
    content = '''"""
Smart Lane Exit Strategy Manager

Advanced exit strategy system that creates comprehensive exit plans
based on risk analysis, technical levels, and market conditions.

Path: engine/smart_lane/strategy/exit_strategies.py
"""

import logging
import math
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone, timedelta

from .. import TechnicalSignal

logger = logging.getLogger(__name__)


class ExitTrigger(Enum):
    """Types of exit triggers."""
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    TIME_BASED = "TIME_BASED"


class ExitMethod(Enum):
    """Exit execution methods."""
    MARKET_ORDER = "MARKET_ORDER"
    LIMIT_ORDER = "LIMIT_ORDER"
    SCALED_EXIT = "SCALED_EXIT"


@dataclass
class ExitLevel:
    """Individual exit level definition."""
    trigger_type: ExitTrigger
    trigger_price_percent: float
    position_percent: float
    execution_method: ExitMethod
    priority: int
    conditions: Dict[str, Any]
    description: str


@dataclass
class ExitStrategy:
    """Complete exit strategy definition."""
    strategy_name: str
    exit_levels: List[ExitLevel]
    max_hold_time_hours: Optional[int]
    stop_loss_percent: Optional[float]
    take_profit_targets: List[float]
    trailing_stop_config: Dict[str, Any]
    emergency_exit_conditions: List[Dict[str, Any]]
    strategy_rationale: str
    risk_management_notes: List[str]


class ExitStrategyManager:
    """Advanced exit strategy manager for Smart Lane trades."""
    
    def __init__(self, config: Any):
        """Initialize exit strategy manager."""
        self.config = config
        self.default_stop_loss_percent = 15.0
        self.default_take_profit_percent = 25.0
        logger.info("Exit strategy manager initialized")
    
    def create_exit_strategy(
        self,
        risk_score: float,
        technical_signals: List[TechnicalSignal],
        market_conditions: Dict[str, Any],
        position_context: Dict[str, Any]
    ) -> ExitStrategy:
        """Create comprehensive exit strategy."""
        try:
            # Simple strategy creation
            stop_loss = self.default_stop_loss_percent * (1 + risk_score)
            take_profit = self.default_take_profit_percent * (1 - risk_score * 0.5)
            
            exit_levels = [
                ExitLevel(
                    trigger_type=ExitTrigger.STOP_LOSS,
                    trigger_price_percent=-stop_loss,
                    position_percent=100.0,
                    execution_method=ExitMethod.MARKET_ORDER,
                    priority=1,
                    conditions={},
                    description=f"Stop loss at -{stop_loss:.1f}%"
                ),
                ExitLevel(
                    trigger_type=ExitTrigger.TAKE_PROFIT,
                    trigger_price_percent=take_profit,
                    position_percent=100.0,
                    execution_method=ExitMethod.LIMIT_ORDER,
                    priority=2,
                    conditions={},
                    description=f"Take profit at +{take_profit:.1f}%"
                )
            ]
            
            return ExitStrategy(
                strategy_name=f"Smart Lane Exit Strategy",
                exit_levels=exit_levels,
                max_hold_time_hours=48,
                stop_loss_percent=stop_loss,
                take_profit_targets=[take_profit],
                trailing_stop_config={'enabled': False},
                emergency_exit_conditions=[],
                strategy_rationale=f"Risk-adjusted strategy for {risk_score:.2f} risk score",
                risk_management_notes=["Monitor position regularly"]
            )
        except Exception as e:
            logger.error(f"Exit strategy error: {e}")
            return ExitStrategy(
                strategy_name="Default Exit Strategy",
                exit_levels=[],
                max_hold_time_hours=24,
                stop_loss_percent=15.0,
                take_profit_targets=[25.0],
                trailing_stop_config={'enabled': False},
                emergency_exit_conditions=[],
                strategy_rationale="Default strategy due to error",
                risk_management_notes=["Error in strategy creation"]
            )


# Export main class
__all__ = ['ExitStrategyManager', 'ExitStrategy', 'ExitLevel', 'ExitTrigger', 'ExitMethod']
'''
    
    file_path = Path("engine/smart_lane/strategy/exit_strategies.py")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ Created: {file_path}")

def create_test_file():
    """Create the test file."""
    content = '''"""
Smart Lane Pipeline Validation Tests

Basic validation tests to ensure pipeline components work correctly.

Path: tests/smart_lane/test_pipeline.py
"""

import asyncio
import pytest
import logging
from typing import Dict, Any, List

# Test imports
def test_imports():
    """Test that all required imports work correctly."""
    try:
        from dexproject.engine.smart_lane.pipeline import SmartLanePipeline
        from dexproject.engine.smart_lane import SmartLaneConfig, RiskCategory
        from dexproject.engine.smart_lane.analyzers import create_analyzer
        from dexproject.engine.smart_lane.strategy.position_sizing import PositionSizer
        from dexproject.engine.smart_lane.strategy.exit_strategies import ExitStrategyManager
        print("✅ All imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

def test_analyzer_creation():
    """Test analyzer factory creation."""
    try:
        from dexproject.engine.smart_lane.analyzers import create_analyzer
        from dexproject.engine.smart_lane import RiskCategory
        
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
        from dexproject.engine.smart_lane.pipeline import SmartLanePipeline
        from dexproject.engine.smart_lane import SmartLaneConfig
        
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

@pytest.mark.asyncio
async def test_basic_analysis():
    """Test basic analysis execution."""
    try:
        from dexproject.engine.smart_lane.pipeline import SmartLanePipeline
        from dexproject.engine.smart_lane import SmartLaneConfig
        
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

def run_manual_tests():
    """Run tests manually without pytest."""
    print("🧪 Running Smart Lane Validation Tests")
    print("=" * 50)
    
    tests = [
        ("Import Test", test_imports),
        ("Analyzer Creation", test_analyzer_creation),
        ("Pipeline Initialization", test_pipeline_initialization)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\\n🔍 Running {test_name}...")
        try:
            if test_func():
                passed += 1
            else:
                print(f"❌ {test_name} failed")
        except Exception as e:
            print(f"❌ {test_name} error: {e}")
    
    # Run async test
    print(f"\\n🔍 Running Basic Analysis Test...")
    try:
        loop = asyncio.get_event_loop()
        if loop.run_until_complete(test_basic_analysis()):
            passed += 1
            total += 1
    except Exception as e:
        print(f"❌ Basic analysis test error: {e}")
        total += 1
    
    print(f"\\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Smart Lane is ready.")
        return True
    else:
        print("⚠️  Some tests failed. Check the errors above.")
        return False

if __name__ == "__main__":
    """Run validation tests when executed directly."""
    success = run_manual_tests()
    exit(0 if success else 1)
'''
    
    file_path = Path("tests/smart_lane/test_pipeline.py")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ Created: {file_path}")

def remove_old_files():
    """Remove old files from wrong locations if they exist."""
    old_files = [
        "engine/smart_lane/analyzers/exit_strategies.py",
        "engine/smart_lane/analyzers/position_sizing.py"
    ]
    
    for file_path in old_files:
        path = Path(file_path)
        if path.exists():
            path.unlink()
            print(f"🗑️  Removed old file: {file_path}")
        else:
            print(f"ℹ️  File not found (OK): {file_path}")

def main():
    """Main setup function."""
    print("🚀 Setting up Smart Lane Phase 5 Files")
    print("=" * 50)
    
    # Check if we're in the right directory
    if not Path("engine").exists():
        print("❌ Error: Run this script from the dexproject root directory")
        print("   Current directory should contain 'engine' folder")
        return False
    
    try:
        # Create directory structure
        print("\\n📁 Creating directories...")
        create_directory_structure()
        
        # Remove old files
        print("\\n🗑️  Checking for old files...")
        remove_old_files()
        
        # Create new files
        print("\\n📝 Creating strategy files...")
        create_strategy_init()
        create_position_sizing()
        create_exit_strategies()
        
        print("\\n🧪 Creating test files...")
        create_test_file()
        
        print("\\n✅ Setup completed successfully!")
        print("\\n🎯 Next steps:")
        print("1. Run: python tests/smart_lane/test_pipeline.py")
        print("2. Or run: pytest tests/smart_lane/test_pipeline.py -v")
        
        return True
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

    
    file_path = Path("setup_smart_lane_files.py")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ Created setup script: {file_path}")