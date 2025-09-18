"""
Smart Lane Strategy Package

Contains strategy components for position sizing and exit management.
These components take analysis results and convert them into actionable
trading strategies with comprehensive risk management.

Path: engine/smart_lane/strategy/__init__.py
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    # Import main strategy classes with comprehensive error handling
    from .position_sizing import (
        PositionSizer, SizingCalculation, SizingMethod,
        PortfolioContext, MarketConditions as SizingMarketConditions,
        PositionSizerError
    )
    logger.debug("Position sizing components imported successfully")
    
    from .exit_strategies import (
        ExitStrategyManager, ExitStrategy, ExitLevel, 
        ExitTrigger, ExitMethod, ExitPriority,
        MarketConditions as ExitMarketConditions, PositionContext,
        ExitStrategyError
    )
    logger.debug("Exit strategy components imported successfully")
    
    IMPORT_SUCCESS = True
    IMPORT_ERRORS = []

except ImportError as e:
    logger.error(f"Failed to import strategy components: {e}")
    IMPORT_SUCCESS = False
    IMPORT_ERRORS = [str(e)]
    
    # Create fallback classes to prevent complete failure
    class PositionSizer:
        """Fallback position sizer class."""
        def __init__(self, config=None):
            self.config = config
            logger.warning("Using fallback PositionSizer due to import failure")
        
        def calculate_position_size(self, *args, **kwargs):
            logger.error("PositionSizer not available - using fallback")
            from dataclasses import dataclass
            
            @dataclass
            class FallbackCalculation:
                recommended_size_percent: float = 2.0
                method_used: str = "FALLBACK"
                warnings: list = None
                calculation_details: dict = None
                
                def __post_init__(self):
                    if self.warnings is None:
                        self.warnings = ["Position sizer not available"]
                    if self.calculation_details is None:
                        self.calculation_details = {"fallback": True}
            
            return FallbackCalculation()
    
    class ExitStrategyManager:
        """Fallback exit strategy manager class."""
        def __init__(self, config=None):
            self.config = config
            logger.warning("Using fallback ExitStrategyManager due to import failure")
        
        def create_exit_strategy(self, *args, **kwargs):
            logger.error("ExitStrategyManager not available - using fallback")
            from dataclasses import dataclass, field
            from datetime import datetime, timezone
            
            @dataclass
            class FallbackStrategy:
                strategy_name: str = "Fallback Strategy"
                exit_levels: list = field(default_factory=list)
                stop_loss_percent: float = 15.0
                take_profit_targets: list = field(default_factory=lambda: [25.0])
                strategy_rationale: str = "Fallback strategy due to import failure"
                warnings: list = field(default_factory=lambda: ["Exit strategy manager not available"])
            
            return FallbackStrategy()
    
    # Define fallback enums
    class SizingMethod:
        FIXED_PERCENT = "FIXED_PERCENT"
        RISK_BASED = "RISK_BASED"
    
    class ExitTrigger:
        STOP_LOSS = "STOP_LOSS"
        TAKE_PROFIT = "TAKE_PROFIT"
    
    class ExitMethod:
        MARKET_ORDER = "MARKET_ORDER"
        LIMIT_ORDER = "LIMIT_ORDER"

except Exception as e:
    logger.error(f"Unexpected error during strategy package initialization: {e}", exc_info=True)
    IMPORT_SUCCESS = False
    IMPORT_ERRORS = [f"Unexpected error: {e}"]


# Package metadata
__version__ = "1.0.0"
__author__ = "Smart Lane Strategy Team"
__description__ = "Advanced position sizing and exit strategy management for DEX trading"

# Package configuration
PACKAGE_CONFIG = {
    'default_position_size_percent': 5.0,
    'max_position_size_percent': 25.0,
    'default_stop_loss_percent': 15.0,
    'default_take_profit_percent': 25.0,
    'max_exit_levels': 10,
    'enable_logging': True,
    'log_level': 'INFO'
}

# Performance tracking
PACKAGE_STATS = {
    'initialization_time': None,
    'import_success': IMPORT_SUCCESS,
    'import_errors': IMPORT_ERRORS,
    'components_loaded': 0,
    'fallback_mode': not IMPORT_SUCCESS
}


def get_package_info() -> Dict[str, Any]:
    """
    Get comprehensive package information and status.
    
    Returns:
        Dict containing package version, status, and configuration
    """
    try:
        info = {
            'version': __version__,
            'description': __description__,
            'import_success': IMPORT_SUCCESS,
            'fallback_mode': not IMPORT_SUCCESS,
            'available_components': [],
            'configuration': PACKAGE_CONFIG.copy(),
            'stats': PACKAGE_STATS.copy()
        }
        
        # Check which components are available
        if IMPORT_SUCCESS:
            info['available_components'] = [
                'PositionSizer',
                'SizingCalculation', 
                'SizingMethod',
                'ExitStrategyManager',
                'ExitStrategy',
                'ExitLevel',
                'ExitTrigger',
                'ExitMethod'
            ]
        else:
            info['available_components'] = ['FallbackPositionSizer', 'FallbackExitStrategyManager']
            info['import_errors'] = IMPORT_ERRORS
        
        return info
        
    except Exception as e:
        logger.error(f"Failed to get package info: {e}")
        return {
            'version': __version__,
            'error': str(e),
            'fallback_mode': True
        }


def create_strategy_suite(config: Optional[Any] = None) -> Dict[str, Any]:
    """
    Create a complete strategy suite with position sizer and exit strategy manager.
    
    Args:
        config: Optional Smart Lane configuration
    
    Returns:
        Dict containing initialized strategy components
    
    Raises:
        RuntimeError: If component creation fails
    """
    try:
        logger.info("Creating Smart Lane strategy suite")
        
        suite = {}
        creation_errors = []
        
        # Create position sizer
        try:
            position_sizer = PositionSizer(config)
            suite['position_sizer'] = position_sizer
            logger.debug("Position sizer created successfully")
        except Exception as e:
            logger.error(f"Failed to create position sizer: {e}")
            creation_errors.append(f"Position sizer error: {e}")
            suite['position_sizer'] = None
        
        # Create exit strategy manager
        try:
            exit_manager = ExitStrategyManager(config)
            suite['exit_strategy_manager'] = exit_manager
            logger.debug("Exit strategy manager created successfully")
        except Exception as e:
            logger.error(f"Failed to create exit strategy manager: {e}")
            creation_errors.append(f"Exit strategy manager error: {e}")
            suite['exit_strategy_manager'] = None
        
        # Add metadata
        suite.update({
            'config': config,
            'created_at': logger.handlers[0].formatter.formatTime(logger.makeRecord(
                'strategy', 20, '', 0, '', (), None
            )) if logger.handlers else "unknown",
            'creation_errors': creation_errors,
            'fallback_mode': not IMPORT_SUCCESS,
            'suite_complete': all(suite.get(key) is not None 
                                for key in ['position_sizer', 'exit_strategy_manager'])
        })
        
        if creation_errors:
            logger.warning(f"Strategy suite created with {len(creation_errors)} errors")
        else:
            logger.info("Strategy suite created successfully")
        
        return suite
        
    except Exception as e:
        logger.error(f"Strategy suite creation failed: {e}", exc_info=True)
        raise RuntimeError(f"Failed to create strategy suite: {e}") from e


def validate_strategy_components() -> Dict[str, Any]:
    """
    Validate that all strategy components are working correctly.
    
    Returns:
        Dict containing validation results
    """
    validation_start = logger.makeRecord('strategy', 20, '', 0, '', (), None).created
    results = {
        'validation_time': None,
        'position_sizer_valid': False,
        'exit_manager_valid': False,
        'overall_valid': False,
        'errors': [],
        'warnings': []
    }
    
    try:
        logger.debug("Validating strategy components")
        
        # Test position sizer
        try:
            test_sizer = PositionSizer()
            test_calculation = test_sizer.calculate_position_size(
                analysis_confidence=0.7,
                overall_risk_score=0.4
            )
            
            if hasattr(test_calculation, 'recommended_size_percent'):
                results['position_sizer_valid'] = True
                logger.debug("Position sizer validation passed")
            else:
                results['errors'].append("Position sizer returned invalid result")
                
        except Exception as e:
            logger.warning(f"Position sizer validation failed: {e}")
            results['errors'].append(f"Position sizer error: {e}")
        
        # Test exit strategy manager
        try:
            test_manager = ExitStrategyManager()
            test_strategy = test_manager.create_exit_strategy(risk_score=0.5)
            
            if hasattr(test_strategy, 'strategy_name') and hasattr(test_strategy, 'exit_levels'):
                results['exit_manager_valid'] = True
                logger.debug("Exit strategy manager validation passed")
            else:
                results['errors'].append("Exit strategy manager returned invalid result")
                
        except Exception as e:
            logger.warning(f"Exit strategy manager validation failed: {e}")
            results['errors'].append(f"Exit strategy manager error: {e}")
        
        # Overall validation
        results['overall_valid'] = (
            results['position_sizer_valid'] and 
            results['exit_manager_valid'] and
            len(results['errors']) == 0
        )
        
        # Add warnings for fallback mode
        if not IMPORT_SUCCESS:
            results['warnings'].append("Running in fallback mode due to import failures")
        
        validation_end = logger.makeRecord('strategy', 20, '', 0, '', (), None).created
        results['validation_time'] = validation_end - validation_start
        
        if results['overall_valid']:
            logger.info("Strategy component validation passed")
        else:
            logger.warning(f"Strategy validation failed with {len(results['errors'])} errors")
        
        return results
        
    except Exception as e:
        logger.error(f"Strategy validation failed: {e}", exc_info=True)
        results['errors'].append(f"Validation error: {e}")
        return results


# Export main classes and functions
if IMPORT_SUCCESS:
    __all__ = [
        # Position Sizing
        'PositionSizer',
        'SizingCalculation', 
        'SizingMethod',
        'PortfolioContext',
        'PositionSizerError',
        
        # Exit Strategies
        'ExitStrategyManager',
        'ExitStrategy',
        'ExitLevel',
        'ExitTrigger',
        'ExitMethod',
        'ExitPriority',
        'PositionContext',
        'ExitStrategyError',
        
        # Package functions
        'create_strategy_suite',
        'validate_strategy_components',
        'get_package_info',
        
        # Package metadata
        'PACKAGE_CONFIG',
        'IMPORT_SUCCESS'
    ]
else:
    __all__ = [
        # Fallback classes
        'PositionSizer',  # Fallback version
        'ExitStrategyManager',  # Fallback version
        'SizingMethod',
        'ExitTrigger', 
        'ExitMethod',
        
        # Package functions
        'create_strategy_suite',
        'validate_strategy_components', 
        'get_package_info',
        
        # Package metadata
        'PACKAGE_CONFIG',
        'IMPORT_SUCCESS'
    ]

# Initialize package statistics
try:
    import time
    PACKAGE_STATS['initialization_time'] = time.time()
    PACKAGE_STATS['components_loaded'] = len(__all__)
    
    if IMPORT_SUCCESS:
        logger.info(f"Smart Lane strategy package initialized successfully - version {__version__}")
        logger.info(f"Loaded {len(__all__)} components with full functionality")
    else:
        logger.warning(f"Smart Lane strategy package initialized in fallback mode - version {__version__}")
        logger.warning(f"Import errors: {', '.join(IMPORT_ERRORS)}")
        
except Exception as e:
    logger.error(f"Package statistics initialization failed: {e}")

# Package-level configuration
def configure_strategy_package(
    position_size_percent: Optional[float] = None,
    stop_loss_percent: Optional[float] = None,
    take_profit_percent: Optional[float] = None,
    max_exit_levels: Optional[int] = None,
    enable_logging: Optional[bool] = None
) -> None:
    """
    Configure package-level defaults for strategy components.
    
    Args:
        position_size_percent: Default position size percentage
        stop_loss_percent: Default stop loss percentage  
        take_profit_percent: Default take profit percentage
        max_exit_levels: Maximum number of exit levels
        enable_logging: Enable/disable package logging
    """
    global PACKAGE_CONFIG
    
    try:
        if position_size_percent is not None:
            PACKAGE_CONFIG['default_position_size_percent'] = max(0.1, min(50.0, position_size_percent))
        
        if stop_loss_percent is not None:
            PACKAGE_CONFIG['default_stop_loss_percent'] = max(1.0, min(50.0, stop_loss_percent))
        
        if take_profit_percent is not None:
            PACKAGE_CONFIG['default_take_profit_percent'] = max(2.0, min(500.0, take_profit_percent))
        
        if max_exit_levels is not None:
            PACKAGE_CONFIG['max_exit_levels'] = max(2, min(20, max_exit_levels))
        
        if enable_logging is not None:
            PACKAGE_CONFIG['enable_logging'] = bool(enable_logging)
            if enable_logging:
                logger.setLevel(logging.INFO)
            else:
                logger.setLevel(logging.WARNING)
        
        logger.info("Strategy package configuration updated")
        
    except Exception as e:
        logger.error(f"Package configuration failed: {e}")


# Cleanup function for proper package shutdown
def cleanup_strategy_package() -> None:
    """Clean up package resources and log final statistics."""
    try:
        logger.info("Cleaning up Smart Lane strategy package")
        logger.info(f"Package statistics: {PACKAGE_STATS}")
        
        # Additional cleanup could go here (close connections, save state, etc.)
        
    except Exception as e:
        logger.error(f"Package cleanup failed: {e}")

# Set up package shutdown handler
import atexit
atexit.register(cleanup_strategy_package)