"""
DEX Integration Constants - Single Source of Truth

This module centralizes ALL DEX-related constants including:
- Contract addresses (factory, router, registry) by chain
- Contract ABIs (minimal - only what we need)
- Fee tiers and configuration
- Base token addresses (WETH, USDC, etc.)

This is the SINGLE SOURCE OF TRUTH for all DEX constants.
Both analyzers and DEX integrations import from here.

File: dexproject/paper_trading/intelligence/dex_integrations/constants.py
"""

from typing import Dict, List, Any


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

# Uniswap V3 Router addresses by chain
UNISWAP_V3_ROUTER: Dict[int, str] = {
    84532: '0x2626664c2603336E57B271c5C0b26F421741e481',  # Base Sepolia
    8453: '0x2626664c2603336E57B271c5C0b26F421741e481',  # Base Mainnet
    1: '0xE592427A0AEce92De3Edee1F18E0157C05861564',  # Ethereum Mainnet
}

# Uniswap V3 Fee tiers (in basis points)
# 500 = 0.05%, 3000 = 0.3%, 10000 = 1%
UNISWAP_V3_FEE_TIERS: List[int] = [500, 3000, 10000]

# Alias for backward compatibility
FEE_TIERS = UNISWAP_V3_FEE_TIERS


# =============================================================================
# UNISWAP V2 CONSTANTS
# =============================================================================

# Uniswap V2 Factory addresses by chain
UNISWAP_V2_FACTORY: Dict[int, str] = {
    84532: '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',  # Base Sepolia (if deployed)
    8453: '0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6',  # Base Mainnet
    1: '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',  # Ethereum Mainnet
}

# Uniswap V2 Router addresses by chain
UNISWAP_V2_ROUTER: Dict[int, str] = {
    84532: '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',  # Base Sepolia
    8453: '0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24',  # Base Mainnet
    1: '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',  # Ethereum Mainnet
}


# =============================================================================
# SUSHISWAP CONSTANTS
# =============================================================================

# SushiSwap Factory addresses by chain
SUSHISWAP_FACTORY: Dict[int, str] = {
    8453: '0x71524B4f93c58fcbF659783284E38825f0622859',  # Base Mainnet
    1: '0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac',  # Ethereum Mainnet
}

# SushiSwap Router addresses by chain
SUSHISWAP_ROUTER: Dict[int, str] = {
    8453: '0x6BDED42c6DA8FBf0d2bA55B2fa120C5e0c8D7891',  # Base Mainnet
    1: '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F',  # Ethereum Mainnet
}


# =============================================================================
# CURVE CONSTANTS
# =============================================================================

# Curve Registry addresses by chain
CURVE_REGISTRY: Dict[int, str] = {
    8453: '0xA5961898870943c68037F6848d2D866Ed2016bcB',  # Base Mainnet (example)
    1: '0x90E00ACe148ca3b23Ac1bC8C240C2a7Dd9c2d7f5',  # Ethereum Mainnet
}

# Curve Address Provider by chain
CURVE_ADDRESS_PROVIDER: Dict[int, str] = {
    1: '0x0000000022D53366457F9d5E68Ec105046FC4383',  # Ethereum Mainnet
}


# =============================================================================
# BASE TOKEN ADDRESSES (WETH, USDC, USDT, DAI)
# =============================================================================

# WETH addresses by chain
WETH_ADDRESS: Dict[int, str] = {
    84532: '0x4200000000000000000000000000000000000006',  # Base Sepolia
    8453: '0x4200000000000000000000000000000000000006',  # Base Mainnet
    1: '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',  # Ethereum Mainnet
    11155111: '0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14',  # Sepolia
}

# USDC addresses by chain
USDC_ADDRESS: Dict[int, str] = {
    84532: '0x036CbD53842c5426634e7929541eC2318f3dCF7e',  # Base Sepolia
    8453: '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',  # Base Mainnet
    1: '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',  # Ethereum Mainnet
    11155111: '0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238',  # Sepolia
}

# USDT addresses by chain
USDT_ADDRESS: Dict[int, str] = {
    8453: '0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2',  # Base Mainnet (example)
    1: '0xdAC17F958D2ee523a2206206994597C13D831ec7',  # Ethereum Mainnet
}

# DAI addresses by chain
DAI_ADDRESS: Dict[int, str] = {
    8453: '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb',  # Base Mainnet
    1: '0x6B175474E89094C44Da98b954EedeAC495271d0F',  # Ethereum Mainnet
}


# =============================================================================
# CONTRACT ABIs (MINIMAL - ONLY WHAT WE NEED)
# =============================================================================

# Uniswap V3 Factory ABI (minimal - just getPool function)
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

# Uniswap V3 Pool ABI (minimal - what we need for price and liquidity)
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
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# ERC20 Token ABI (minimal - just what we need for balances)
ERC20_ABI: List[Dict[str, Any]] = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    }
]

# Uniswap V2 Pair ABI (minimal - for reserves)
UNISWAP_V2_PAIR_ABI: List[Dict[str, Any]] = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"name": "reserve0", "type": "uint112"},
            {"name": "reserve1", "type": "uint112"},
            {"name": "blockTimestampLast", "type": "uint32"}
        ],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function"
    }
]

# Uniswap V2 Factory ABI (minimal - for pair lookup)
UNISWAP_V2_FACTORY_ABI: List[Dict[str, Any]] = [
    {
        "constant": True,
        "inputs": [
            {"name": "tokenA", "type": "address"},
            {"name": "tokenB", "type": "address"}
        ],
        "name": "getPair",
        "outputs": [{"name": "pair", "type": "address"}],
        "type": "function"
    }
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_base_tokens(chain_id: int) -> List[str]:
    """
    Get list of base token addresses for a chain.
    
    Base tokens are used to find trading pairs (e.g., TOKEN/WETH, TOKEN/USDC).
    
    Args:
        chain_id: Blockchain network ID
        
    Returns:
        List of base token addresses (WETH, USDC, USDT, DAI)
    """
    base_tokens = []
    
    if chain_id in WETH_ADDRESS:
        base_tokens.append(WETH_ADDRESS[chain_id])
    
    if chain_id in USDC_ADDRESS:
        base_tokens.append(USDC_ADDRESS[chain_id])
    
    if chain_id in USDT_ADDRESS:
        base_tokens.append(USDT_ADDRESS[chain_id])
    
    if chain_id in DAI_ADDRESS:
        base_tokens.append(DAI_ADDRESS[chain_id])
    
    return base_tokens


def get_dex_addresses(dex_name: str, chain_id: int) -> Dict[str, str]:
    """
    Get DEX addresses (factory, router) for a specific DEX and chain.
    
    Args:
        dex_name: DEX name ('uniswap_v3', 'uniswap_v2', 'sushiswap', 'curve')
        chain_id: Blockchain network ID
        
    Returns:
        Dictionary with 'factory' and 'router' addresses
        
    Raises:
        ValueError: If DEX or chain not supported
    """
    if dex_name == 'uniswap_v3':
        return {
            'factory': UNISWAP_V3_FACTORY.get(chain_id, ''),
            'router': UNISWAP_V3_ROUTER.get(chain_id, '')
        }
    elif dex_name == 'uniswap_v2':
        return {
            'factory': UNISWAP_V2_FACTORY.get(chain_id, ''),
            'router': UNISWAP_V2_ROUTER.get(chain_id, '')
        }
    elif dex_name == 'sushiswap':
        return {
            'factory': SUSHISWAP_FACTORY.get(chain_id, ''),
            'router': SUSHISWAP_ROUTER.get(chain_id, '')
        }
    elif dex_name == 'curve':
        return {
            'registry': CURVE_REGISTRY.get(chain_id, ''),
            'address_provider': CURVE_ADDRESS_PROVIDER.get(chain_id, '')
        }
    else:
        raise ValueError(f"Unknown DEX: {dex_name}")