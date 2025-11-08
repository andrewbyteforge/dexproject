"""
Engine Execution Package

Fast Lane execution components for high-speed trade execution.
Provides classes and functions for trade execution, nonce management, and gas optimization.

File: engine/execution/__init__.py
"""

# Import from the main execution module (that exists as a single file)
try:
    from ..execution import (
        TradeType,
        TradeStatus,
        ExitReason,
        TradeDecision,
        TradeExecution,
        Position,
        PaperTradingSimulator
    )
except ImportError:
    # Fallback imports if the module structure is different
    TradeType = None
    TradeStatus = None
    ExitReason = None
    TradeDecision = None
    TradeExecution = None
    Position = None
    PaperTradingSimulator = None

# Import from Fast Lane components
try:
    from .fast_engine import (
        FastLaneExecutionEngine,
        FastLaneStatus,
        TradeExecutionResult,
        FastTradeRequest,
        FastExecutionResult
    )
except ImportError:
    # Fast Lane components might not be available yet
    FastLaneExecutionEngine = None
    FastLaneStatus = None
    TradeExecutionResult = None
    FastTradeRequest = None
    FastExecutionResult = None

try:
    from .gas_optimizer import (
        GasOptimizationEngine,
        GasRecommendation,
        GasMetrics,
        GasStrategy,
        NetworkCongestion,
        GasType
    )
except ImportError:
    GasOptimizationEngine = None
    GasRecommendation = None
    GasMetrics = None
    GasStrategy = None
    NetworkCongestion = None
    GasType = None

try:
    from .nonce_manager import (
        NonceManager,
        NonceTransaction,
        WalletNonceState,
        NonceStatus,
        TransactionPriority
    )
except ImportError:
    NonceManager = None
    NonceTransaction = None
    WalletNonceState = None
    NonceStatus = None
    TransactionPriority = None

# Export all available classes
__all__ = [
    # Core execution classes
    'TradeType',
    'TradeStatus', 
    'ExitReason',
    'TradeDecision',
    'TradeExecution',
    'Position',
    'PaperTradingSimulator',
    
    # Fast Lane components
    'FastLaneExecutionEngine',
    'FastLaneStatus',
    'TradeExecutionResult', 
    'FastTradeRequest',
    'FastExecutionResult',
    
    # Gas optimization
    'GasOptimizationEngine',
    'GasRecommendation',
    'GasMetrics',
    'GasStrategy',
    'NetworkCongestion',
    'GasType',
    
    # Nonce management
    'NonceManager',
    'NonceTransaction',
    'WalletNonceState',
    'NonceStatus',
    'TransactionPriority'
]

# Remove None values from exports
__all__ = [name for name in __all__ if globals().get(name) is not None]