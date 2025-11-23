"""
DEX Integrations Module - Complete Multi-DEX Support

This module provides unified access to 6 major DEX protocols:
- Uniswap V3: Multi-tier concentrated liquidity
- SushiSwap: Proven V2-style AMM
- Curve: Optimized stablecoin swaps
- Aerodrome: Base chain's largest DEX
- BaseSwap: Base chain V2 alternative

All DEX adapters implement the BaseDEX interface and return DEXPrice objects
for consistent cross-DEX comparison and arbitrage detection.

File: dexproject/paper_trading/intelligence/dex_integrations/__init__.py
"""

import logging

# Import base classes and data structures
from paper_trading.intelligence.dex_integrations.base import (
    BaseDEX,
    DEXPrice
)

# Import all DEX implementations
from paper_trading.intelligence.dex_integrations.uniswap_v3 import UniswapV3DEX
from paper_trading.intelligence.dex_integrations.sushiswap import SushiSwapDEX
from paper_trading.intelligence.dex_integrations.curve import CurveDEX
from paper_trading.intelligence.dex_integrations.aerodrome import AerodromeDEX
from paper_trading.intelligence.dex_integrations.baseswap import BaseSwapDEX

# Import all constants
from paper_trading.intelligence.dex_integrations.constants import (
    # Uniswap V3
    UNISWAP_V3_FACTORY,
    UNISWAP_V3_ROUTER,
    UNISWAP_V3_FEE_TIERS,
    FEE_TIERS,  # Alias
    
    # Uniswap V2
    UNISWAP_V2_FACTORY,
    UNISWAP_V2_ROUTER,
    
    # SushiSwap
    SUSHISWAP_FACTORY,
    SUSHISWAP_ROUTER,
    
    # Curve
    CURVE_REGISTRY,
    CURVE_ADDRESS_PROVIDER,
    
    # Aerodrome (Base chain)
    AERODROME_FACTORY,
    AERODROME_ROUTER,
    
    # BaseSwap (Base chain)
    BASESWAP_FACTORY,
    BASESWAP_ROUTER,
    
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
    
    # Helper functions
    get_base_tokens,
    get_dex_addresses,
    get_gas_estimate
)

# Configure module logger
logger = logging.getLogger(__name__)


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================

def _log_initialization() -> None:
    """
    Log DEX integrations initialization status.
    
    Provides visibility into available DEX protocols and their capabilities.
    """
    logger.info("=" * 80)
    logger.info("[DEX INTEGRATIONS] Multi-DEX Trading System Initialized")
    logger.info("=" * 80)
    logger.info("[DEX INTEGRATIONS] Available DEX Protocols:")
    logger.info("[DEX INTEGRATIONS]   1. Uniswap V3 - Concentrated liquidity")
    logger.info("[DEX INTEGRATIONS]   2. SushiSwap - V2-style AMM")
    logger.info("[DEX INTEGRATIONS]   3. Curve Finance - Stablecoin optimization")
    logger.info("[DEX INTEGRATIONS]   4. Aerodrome - Base chain primary")
    logger.info("[DEX INTEGRATIONS]   5. BaseSwap - Base chain alternative")
    logger.info("[DEX INTEGRATIONS]")
    logger.info("[DEX INTEGRATIONS] Capabilities:")
    logger.info("[DEX INTEGRATIONS]   ✅ Multi-DEX price comparison")
    logger.info("[DEX INTEGRATIONS]   ✅ Cross-DEX arbitrage detection")
    logger.info("[DEX INTEGRATIONS]   ✅ Smart trade routing")
    logger.info("[DEX INTEGRATIONS]   ✅ Base chain optimization")
    logger.info("[DEX INTEGRATIONS]   ✅ Stablecoin specialization")
    logger.info("=" * 80)


# Run initialization logging when module is imported
_log_initialization()


# =============================================================================
# DEX FACTORY FUNCTION
# =============================================================================

def create_dex(
    dex_name: str,
    chain_id: int = 8453,
    cache_ttl_seconds: int = 60
) -> BaseDEX:
    """
    Factory function to create DEX instances by name.
    
    This provides a convenient way to instantiate DEX adapters without
    knowing their specific class names.
    
    Args:
        dex_name: DEX name ('uniswap_v3', 'sushiswap', 'curve', 'aerodrome', 'baseswap')
        chain_id: Blockchain network ID (default: 8453 = Base Mainnet)
        cache_ttl_seconds: Cache TTL for price data (default: 60 seconds)
        
    Returns:
        Initialized DEX instance
        
    Raises:
        ValueError: If dex_name is not recognized
        
    Example:
        >>> dex = create_dex('aerodrome', chain_id=8453)
        >>> price = await dex.get_token_price(token_address, 'WETH')
    """
    dex_map = {
        'uniswap_v3': UniswapV3DEX,
        'sushiswap': SushiSwapDEX,
        'curve': CurveDEX,
        'aerodrome': AerodromeDEX,
        'baseswap': BaseSwapDEX
    }
    
    dex_class = dex_map.get(dex_name.lower())
    if not dex_class:
        raise ValueError(
            f"Unknown DEX: {dex_name}. "
            f"Available: {', '.join(dex_map.keys())}"
        )
    
    return dex_class(
        chain_id=chain_id,
        cache_ttl_seconds=cache_ttl_seconds
    )


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_supported_dexs(chain_id: int = 8453) -> list[str]:
    """
    Get list of supported DEXs for a specific chain.
    
    Args:
        chain_id: Blockchain network ID
        
    Returns:
        List of DEX names available on this chain
        
    Example:
        >>> get_supported_dexs(8453)
        ['uniswap_v3', 'sushiswap', 'curve', 'aerodrome', 'baseswap']
    """
    supported = []
    
    # Uniswap V3 - Multi-chain
    if chain_id in UNISWAP_V3_FACTORY:
        supported.append('uniswap_v3')
    
    # SushiSwap - Multi-chain
    if chain_id in SUSHISWAP_FACTORY:
        supported.append('sushiswap')
    
    # Curve - Multi-chain
    if chain_id in CURVE_REGISTRY:
        supported.append('curve')
    
    # Aerodrome - Base only
    if chain_id in AERODROME_FACTORY:
        supported.append('aerodrome')
    
    # BaseSwap - Base only
    if chain_id in BASESWAP_FACTORY:
        supported.append('baseswap')
    
    return supported


def get_dex_info() -> dict[str, dict[str, str]]:
    """
    Get information about all available DEXs.
    
    Returns:
        Dictionary mapping DEX names to their descriptions
        
    Example:
        >>> info = get_dex_info()
        >>> print(info['aerodrome']['description'])
        'Base chain primary DEX with volatile and stable pools'
    """
    return {
        'uniswap_v3': {
            'name': 'Uniswap V3',
            'type': 'Concentrated Liquidity',
            'description': 'Multi-tier concentrated liquidity with 0.05%, 0.3%, and 1% fees',
            'best_for': 'High-volume tokens, deep liquidity',
            'chains': 'Multi-chain (Ethereum, Base, Arbitrum, Optimism)'
        },
        'sushiswap': {
            'name': 'SushiSwap',
            'type': 'Constant Product AMM',
            'description': 'Proven Uniswap V2-style AMM with consistent pricing',
            'best_for': 'Alternative liquidity, arbitrage opportunities',
            'chains': 'Multi-chain (Ethereum, Base, Arbitrum, Polygon)'
        },
        'curve': {
            'name': 'Curve Finance',
            'type': 'Stableswap AMM',
            'description': 'Optimized for stablecoin swaps with minimal slippage',
            'best_for': 'USDC/USDT/DAI swaps, large stable volumes',
            'chains': 'Multi-chain (Ethereum, Base, Arbitrum, Optimism)'
        },
        'aerodrome': {
            'name': 'Aerodrome',
            'type': 'Hybrid AMM',
            'description': 'Base chain primary DEX with volatile and stable pools',
            'best_for': 'Base chain trading, highest Base liquidity',
            'chains': 'Base only'
        },
        'baseswap': {
            'name': 'BaseSwap',
            'type': 'Constant Product AMM',
            'description': 'Uniswap V2 fork on Base with Base-native token support',
            'best_for': 'Alternative Base liquidity, Base-specific tokens',
            'chains': 'Base only'
        }
    }


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
    'AerodromeDEX',
    'BaseSwapDEX',
    
    # Factory function
    'create_dex',
    
    # Utility functions
    'get_supported_dexs',
    'get_dex_info',
    
    # Constants - Factories
    'UNISWAP_V3_FACTORY',
    'UNISWAP_V2_FACTORY',
    'SUSHISWAP_FACTORY',
    'CURVE_REGISTRY',
    'AERODROME_FACTORY',
    'BASESWAP_FACTORY',
    
    # Constants - Routers
    'UNISWAP_V3_ROUTER',
    'UNISWAP_V2_ROUTER',
    'SUSHISWAP_ROUTER',
    'AERODROME_ROUTER',
    'BASESWAP_ROUTER',
    
    # Constants - Tokens
    'WETH_ADDRESS',
    'USDC_ADDRESS',
    'USDT_ADDRESS',
    'DAI_ADDRESS',
    
    # Constants - ABIs
    'FACTORY_ABI',
    'POOL_ABI',
    'ERC20_ABI',
    'UNISWAP_V2_PAIR_ABI',
    'UNISWAP_V2_FACTORY_ABI',
    
    # Helper functions
    'get_base_tokens',
    'get_dex_addresses',
    'get_gas_estimate',
    
    # Fee tiers
    'FEE_TIERS',
    'UNISWAP_V3_FEE_TIERS',
]