"""
Paper Trading Models Package

This package contains all paper trading models organized into logical modules:
- base: Core paper trading infrastructure (accounts, trades, positions)
- intelligence: AI decision tracking and strategy configuration
- performance: Performance metrics and session tracking
- autopilot: Auto Pilot intelligence and learning models

File: dexproject/paper_trading/models/__init__.py
"""

from .base import (
    # Core trading models
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingConfig,
)

from .intelligence import (
    # Intelligence & strategy models
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
)

from .performance import (
    # Performance tracking models
    PaperPerformanceMetrics,
    PaperTradingSession,
)

from .autopilot import (
    # Auto Pilot models
    AutoPilotLog,
    AutoPilotPerformanceSnapshot,
)

from .orders import (
    PaperOrder,
)

# Export all models for Django
__all__ = [
    # Core trading models
    'PaperTradingAccount',
    'PaperTrade',
    'PaperPosition',
    'PaperTradingConfig',
    
    # Intelligence & strategy models
    'PaperAIThoughtLog',
    'PaperStrategyConfiguration',
    
    # Performance tracking models
    'PaperPerformanceMetrics',
    'PaperTradingSession',
    
    # Auto Pilot models
    'AutoPilotLog',
    'AutoPilotPerformanceSnapshot',


    'PaperOrder',
]