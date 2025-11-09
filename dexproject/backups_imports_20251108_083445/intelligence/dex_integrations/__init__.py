"""
DEX Integrations Module - Public API

This module provides DEX adapter implementations for multi-DEX price comparison.
Each DEX has its own adapter that implements the BaseDEX interface and returns
standardized DEXPrice objects.

Available DEXs:
- UniswapV3DEX: Uniswap V3 integration (PLACEHOLDER - TODO)
- SushiSwapDEX: SushiSwap integration (PLACEHOLDER - TODO)
- CurveDEX: Curve Finance integration (PLACEHOLDER - TODO)

Usage:
    from paper_trading.intelligence.dex_integrations import UNISWAP_V3_FACTORY
    
    # Get DEX constants for trading
    factory = UNISWAP_V3_FACTORY[8453]  # Base Mainnet

File: dexproject/paper_trading/intelligence/dex_integrations/__init__.py
"""

# =============================================================================
# Import constants from the centralized constants file
# =============================================================================
from paper_trading.intelligence.dex_integrations.constants import (
    # Uniswap V3
    UNISWAP_V3_FACTORY,
    UNISWAP_V3_ROUTER,
    UNISWAP_V3_FEE_TIERS,
    
    # Uniswap V2
    UNISWAP_V2_FACTORY,
    UNISWAP_V2_ROUTER,
    
    # SushiSwap
    SUSHISWAP_FACTORY,
    SUSHISWAP_ROUTER,
    
    # Curve
    CURVE_REGISTRY,
    CURVE_ADDRESS_PROVIDER,
    
    # Base tokens
    WETH_ADDRESS,
    USDC_ADDRESS,
    USDT_ADDRESS,
    DAI_ADDRESS,
    
    # ABIs
    FACTORY_ABI,
    POOL_ABI,
    ERC20_ABI,
    UNISWAP_V2_PAIR_ABI,
    UNISWAP_V2_FACTORY_ABI,
    
    # Gas estimates
    GAS_ESTIMATES_PER_CHAIN,
    DEFAULT_GAS_ESTIMATE,
    get_gas_estimate,
    
    # Helper functions
    get_base_tokens,
    get_dex_addresses,
    
    # Backward compatibility
    FEE_TIERS
)

# =============================================================================
# COMMENTED OUT - DEX implementations don't exist yet
# =============================================================================
# TODO: Create these DEX adapter classes
# from paper_trading.intelligence.dex_integrations.uniswap_v3 import UniswapV3DEX
# from paper_trading.intelligence.dex_integrations.sushiswap import SushiSwapDEX
# from paper_trading.intelligence.dex_integrations.curve import CurveDEX


# =============================================================================
# PUBLIC API
# =============================================================================

__all__ = [
    # Base classes (TODO: uncomment when implemented)
    # 'BaseDEX',
    # 'DEXPrice',
    
    # DEX implementations (TODO: uncomment when implemented)
    # 'UniswapV3DEX',
    # 'SushiSwapDEX',
    # 'CurveDEX',
    
    # Uniswap V3 constants
    'UNISWAP_V3_FACTORY',
    'UNISWAP_V3_ROUTER',
    'UNISWAP_V3_FEE_TIERS',
    'FEE_TIERS',  # Backward compatibility
    
    # Uniswap V2 constants
    'UNISWAP_V2_FACTORY',
    'UNISWAP_V2_ROUTER',
    
    # SushiSwap constants
    'SUSHISWAP_FACTORY',
    'SUSHISWAP_ROUTER',
    
    # Curve constants
    'CURVE_REGISTRY',
    'CURVE_ADDRESS_PROVIDER',
    
    # Base token addresses
    'WETH_ADDRESS',
    'USDC_ADDRESS',
    'USDT_ADDRESS',
    'DAI_ADDRESS',
    
    # ABIs
    'FACTORY_ABI',
    'POOL_ABI',
    'ERC20_ABI',
    'UNISWAP_V2_PAIR_ABI',
    'UNISWAP_V2_FACTORY_ABI',
    
    # Gas estimates
    'GAS_ESTIMATES_PER_CHAIN',
    'DEFAULT_GAS_ESTIMATE',
    'get_gas_estimate',
    
    # Helper functions
    'get_base_tokens',
    'get_dex_addresses',
]


__version__ = '1.0.0'