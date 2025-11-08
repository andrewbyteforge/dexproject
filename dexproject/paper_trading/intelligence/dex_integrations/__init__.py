"""
DEX Integrations Module - Public API

This module provides DEX adapter implementations for multi-DEX price comparison.
Each DEX has its own adapter that implements the BaseDEX interface and returns
standardized DEXPrice objects.

Available DEXs:
- UniswapV3DEX: Uniswap V3 integration (COMPLETE)
- SushiSwapDEX: SushiSwap integration (PLACEHOLDER)
- CurveDEX: Curve Finance integration (PLACEHOLDER)

Usage:
    from paper_trading.intelligence.dex.protocols import UniswapV3DEX, DEXPrice
    
    # Create DEX adapter
    uniswap = UniswapV3DEX(chain_id=8453)
    
    # Get token price
    price = await uniswap.get_token_price(
        token_address='0x...',
        token_symbol='WETH'
    )
    
    if price.success:
        print(f"Price: ${price.price_usd}")
        print(f"Liquidity: ${price.liquidity_usd}")

File: dexproject/paper_trading/intelligence/dex_integrations/__init__.py
"""

# Import base classes
from paper_trading.intelligence.dex.protocols.base import (
    BaseDEX,
    DEXPrice
)

# Import constants (for external use)
from paper_trading.intelligence.dex.protocols.constants import (
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
    
    # Helper functions
    get_base_tokens,
    get_dex_addresses,
    
    # Backward compatibility
    FEE_TIERS
)

# Import DEX implementations
from paper_trading.intelligence.dex.protocols.uniswap_v3 import UniswapV3DEX
from paper_trading.intelligence.dex.protocols.sushiswap import SushiSwapDEX
from paper_trading.intelligence.dex.protocols.curve import CurveDEX


# =============================================================================
# PUBLIC API
# =============================================================================

__all__ = [
    # Base classes
    'BaseDEX',
    'DEXPrice',
    
    # DEX implementations
    'UniswapV3DEX',
    'SushiSwapDEX',
    'CurveDEX',
    
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
    
    # Helper functions
    'get_base_tokens',
    'get_dex_addresses',
]


__version__ = '1.0.0'