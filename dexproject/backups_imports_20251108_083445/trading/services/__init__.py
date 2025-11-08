"""
Trading Services Package - Phase 6B Update

This package contains trading-related services for DEX interactions,
portfolio management, gas optimization, and trading execution.

UPDATED: Added Transaction Manager service exports for Phase 6B
Phase 6A: Gas optimizer service ✅ COMPLETE
Phase 6B: Transaction manager service ✅ COMPLETE

File: dexproject/trading/services/__init__.py
"""

from .dex_router_service import (
    DEXRouterService,
    create_dex_router_service,
    SwapParams,
    SwapResult,
    SwapType,
    DEXVersion
)

from .portfolio_service import (
    PortfolioTrackingService,
    create_portfolio_service,
    PortfolioUpdate
)

from .gas_optimizer import (
    DjangoGasOptimizer,
    TradingGasStrategy,
    TradingGasPrice,
    GasOptimizationResult,
    get_gas_optimizer,
    optimize_trade_gas
)

# Phase 6B: Transaction Manager Service
from .transaction_manager import (
    TransactionManager,
    TransactionStatus,
    TransactionState,
    TransactionSubmissionRequest,
    TransactionManagerResult,
    get_transaction_manager,
    create_transaction_submission_request
)

__all__ = [
    # DEX Router Service
    'DEXRouterService',
    'create_dex_router_service',
    'SwapParams',
    'SwapResult',
    'SwapType',
    'DEXVersion',
    
    # Portfolio Service
    'PortfolioTrackingService',
    'create_portfolio_service',
    'PortfolioUpdate',
    
    # Gas Optimizer Service - Phase 6A
    'DjangoGasOptimizer',
    'TradingGasStrategy',
    'TradingGasPrice',
    'GasOptimizationResult',
    'get_gas_optimizer',
    'optimize_trade_gas',
    
    # Transaction Manager Service - Phase 6B
    'TransactionManager',
    'TransactionStatus',
    'TransactionState',
    'TransactionSubmissionRequest',
    'TransactionManagerResult',
    'get_transaction_manager',
    'create_transaction_submission_request',
]