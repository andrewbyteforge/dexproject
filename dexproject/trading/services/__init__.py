"""
Trading Services Package - Phase 6A Complete

This package contains trading-related services for DEX interactions,
portfolio management, gas optimization, and trading execution.

UPDATED: Added gas optimizer service exports for Phase 6A

File: trading/services/__init__.py
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
]