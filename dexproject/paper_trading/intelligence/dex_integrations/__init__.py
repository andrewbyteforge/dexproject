"""
Modular Market Analyzers for Paper Trading Intelligence

Separate analyzer modules for different aspects of market analysis,
making the system easier to maintain and extend.

This module provides a clean public API for all analyzer components:
- RealGasAnalyzer: Network gas conditions
- RealLiquidityAnalyzer: Uniswap V3 pool liquidity
- RealVolatilityAnalyzer: Price volatility and trends
- MEVThreatDetector: MEV threat analysis
- MarketStateAnalyzer: Overall market conditions
- CompositeMarketAnalyzer: Comprehensive analysis coordinator

File: dexproject/paper_trading/intelligence/analyzers/__init__.py
"""

import logging

# Import defaults for initialization logging
from paper_trading.defaults import IntelligenceDefaults

# Import DEX constants
from paper_trading.intelligence.dex_integrations.constants import (
    UNISWAP_V3_FACTORY,
    FACTORY_ABI,
    POOL_ABI,
    FEE_TIERS,
)

# =============================================================================
# ENGINE AVAILABILITY CHECK
# =============================================================================
# Check if engine config module is available for Web3 connectivity
try:
    import engine.config as engine_config_module
    from engine.config import get_config
    from engine.web3_client import Web3Client
    ENGINE_CONFIG_MODULE_AVAILABLE = True
except ImportError:
    engine_config_module = None  # type: ignore
    get_config = None  # type: ignore
    Web3Client = None  # type: ignore
    ENGINE_CONFIG_MODULE_AVAILABLE = False

# Import base analyzer
from paper_trading.intelligence.analyzers.base import BaseAnalyzer

# Import all specific analyzers
from paper_trading.intelligence.analyzers.gas_analyzer import RealGasAnalyzer
from paper_trading.intelligence.analyzers.liquidity_analyzer import RealLiquidityAnalyzer
from paper_trading.intelligence.analyzers.volatility_analyzer import RealVolatilityAnalyzer
from paper_trading.intelligence.analyzers.mev_detector import MEVThreatDetector
from paper_trading.intelligence.analyzers.market_state import MarketStateAnalyzer
from paper_trading.intelligence.analyzers.composite_analyzer import CompositeMarketAnalyzer

# Configure module logger
logger = logging.getLogger(__name__)


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================

def _log_initialization() -> None:
    """
    Log analyzer initialization status.
    
    Provides visibility into:
    - Engine config availability
    - Data sources being used
    - Configuration settings
    """
    logger.info("=" * 80)
    logger.info("[ANALYZERS] Modular Market Analyzers - REAL DATA VERSION")
    logger.info("=" * 80)
    logger.info(
        f"[ANALYZERS] Engine Config Module Available: {ENGINE_CONFIG_MODULE_AVAILABLE}"
    )
    
    if ENGINE_CONFIG_MODULE_AVAILABLE:
        logger.info("[ANALYZERS] ✅ Using REAL blockchain data (lazy initialization)")
        logger.info("[ANALYZERS]    - Gas: Blockchain RPC queries")
        logger.info("[ANALYZERS]    - Liquidity: Uniswap V3 pool queries")
        logger.info("[ANALYZERS]    - Volatility: Price history calculations")
        logger.info("[ANALYZERS]    - MEV: Smart heuristics (liquidity-based)")
        logger.info("[ANALYZERS]    - Config: Initialized on-demand when analyzers run")
    else:
        logger.warning("[ANALYZERS] ⚠️ Engine config module unavailable")
    
    logger.info(
        "[ANALYZERS] SKIP_TRADE_ON_MISSING_DATA: %s",
        IntelligenceDefaults.SKIP_TRADE_ON_MISSING_DATA
    )
    logger.info("=" * 80)


# Run initialization logging when module is imported
_log_initialization()


# =============================================================================
# PUBLIC API
# =============================================================================

__all__ = [
    # Constants
    'UNISWAP_V3_FACTORY',
    'FACTORY_ABI',
    'POOL_ABI',
    'FEE_TIERS',
    'ENGINE_CONFIG_MODULE_AVAILABLE',
    
    # Base class
    'BaseAnalyzer',
    
    # Analyzers
    'RealGasAnalyzer',
    'RealLiquidityAnalyzer',
    'RealVolatilityAnalyzer',
    'MEVThreatDetector',
    'MarketStateAnalyzer',
    'CompositeMarketAnalyzer',
]