"""
DEX Integrations Package for Multi-DEX Price Comparison

This package provides integrations with multiple DEXs for Phase 2 price comparison:
- Base DEX interface (BaseDEX)
- Uniswap V3 integration
- SushiSwap integration
- Curve integration

Phase 2: Multi-DEX Price Comparison
File: paper_trading/intelligence/dex_integrations/__init__.py
"""

import logging

# Import base class and data structures
from .base_dex import BaseDEX, DEXPrice

# Import DEX implementations
from .uniswap_v3 import UniswapV3DEX
from .sushiswap import SushiSwapDEX
from .curve import CurveDEX

logger = logging.getLogger(__name__)


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================

def _log_initialization() -> None:
    """Log DEX integrations initialization status."""
    logger.info("=" * 80)
    logger.info("[DEX INTEGRATIONS] Multi-DEX Price Comparison - Phase 2")
    logger.info("=" * 80)
    logger.info("[DEX INTEGRATIONS] Available DEXs:")
    logger.info("[DEX INTEGRATIONS]   ✅ Uniswap V3 (Primary)")
    logger.info("[DEX INTEGRATIONS]   ✅ SushiSwap (Alternative)")
    logger.info("[DEX INTEGRATIONS]   ✅ Curve (Stablecoins)")
    logger.info("[DEX INTEGRATIONS] Features:")
    logger.info("[DEX INTEGRATIONS]   - Real on-chain price queries")
    logger.info("[DEX INTEGRATIONS]   - Parallel execution support")
    logger.info("[DEX INTEGRATIONS]   - Circuit breaker protection")
    logger.info("[DEX INTEGRATIONS]   - Automatic caching")
    logger.info("[DEX INTEGRATIONS]   - Performance tracking")
    logger.info("=" * 80)


# Run initialization logging
_log_initialization()


# =============================================================================
# PUBLIC API
# =============================================================================

__all__ = [
    # Base class
    'BaseDEX',
    'DEXPrice',
    
    # DEX implementations
    'UniswapV3DEX',
    'SushiSwapDEX',
    'CurveDEX',
]