"""
Uniswap V3 Constants and Network Configuration - ENHANCED FOR PHASE 3

This module centralizes all Uniswap V3 and DEX-related constants including:
- Factory addresses by chain
- Contract ABIs (Factory and Pool)
- Fee tiers
- Gas estimates per chain (PHASE 3 ADDITION)
- Engine config module availability flag

File: dexproject/paper_trading/intelligence/analyzers/constants.py
"""

from typing import Dict, List, Any

# =============================================================================
# ENGINE AVAILABILITY CHECK
# =============================================================================

# Check if engine config module is available
# This flag is set at import time and used throughout the analyzers
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


# =============================================================================
# UNISWAP V3 CONSTANTS
# =============================================================================

# Uniswap V3 Factory addresses by chain
UNISWAP_V3_FACTORY: Dict[int, str] = {
    84532: '0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24',  # Base Sepolia
    11155111: '0x0227628f3F023bb0B980b67D528571c95c6DaC1c',  # Ethereum Sepolia
    8453: '0x33128a8fC17869897dcE68Ed026d694621f6FDfD',  # Base Mainnet
    1: '0x1F98431c8aD98523631AE4a59f267346ea31F984',  # Ethereum Mainnet
}

# Uniswap V3 Factory ABI (minimal - just what we need for pool lookup)
FACTORY_ABI: List[Dict[str, Any]] = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"}
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# Uniswap V3 Pool ABI (minimal - just what we need for liquidity and price data)
POOL_ABI: List[Dict[str, Any]] = [
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

# Common fee tiers for Uniswap V3 (in basis points)
# 500 = 0.05%, 3000 = 0.3%, 10000 = 1%
FEE_TIERS: List[int] = [500, 3000, 10000]


# =============================================================================
# GAS ESTIMATES - PHASE 3 ADDITION
# =============================================================================

# Gas cost estimates per chain (in gas units)
# Used for cost calculations in arbitrage detection and trade execution
# 
# These are estimated gas units for typical DEX swap operations:
# - Token approval: ~50,000 gas
# - Buy swap: ~100,000-150,000 gas
# - Sell swap: ~100,000-150,000 gas
GAS_ESTIMATES_PER_CHAIN: Dict[int, int] = {
    1: 150000,          # Ethereum mainnet (higher due to more expensive execution)
    8453: 100000,       # Base mainnet (optimized L2)
    84532: 100000,      # Base Sepolia testnet
    42161: 80000,       # Arbitrum (efficient L2)
    10: 100000,         # Optimism (L2)
    11155111: 150000,   # Ethereum Sepolia testnet
}

# Default gas estimate if chain not found
DEFAULT_GAS_ESTIMATE: int = 100000


def get_gas_estimate(chain_id: int) -> int:
    """
    Get gas estimate for a specific chain.
    
    Args:
        chain_id: Blockchain chain ID
        
    Returns:
        Estimated gas units for the chain
    """
    return GAS_ESTIMATES_PER_CHAIN.get(chain_id, DEFAULT_GAS_ESTIMATE)