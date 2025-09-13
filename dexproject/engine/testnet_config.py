"""
Complete testnet configuration for safe Web3 integration testing.

Includes testnet support for Sepolia, Base Sepolia, and Arbitrum Sepolia
with proper configuration and safety features.

File: dexproject/engine/testnet_config.py
"""

import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class TestnetInfo:
    """Information about a testnet."""
    name: str
    chain_id: int
    currency_symbol: str
    block_explorer: str
    faucet_urls: List[str]
    description: str


# Testnet Information
TESTNETS = {
    11155111: TestnetInfo(  # Sepolia
        name="Sepolia",
        chain_id=11155111,
        currency_symbol="SepoliaETH",
        block_explorer="https://sepolia.etherscan.io",
        faucet_urls=[
            "https://sepoliafaucet.com/",
            "https://faucet.quicknode.com/ethereum/sepolia",
            "https://www.alchemy.com/faucets/ethereum-sepolia"
        ],
        description="Ethereum Sepolia testnet - most reliable Ethereum testnet"
    ),
    84532: TestnetInfo(  # Base Sepolia
        name="Base Sepolia",
        chain_id=84532,
        currency_symbol="ETH",
        block_explorer="https://sepolia.basescan.org",
        faucet_urls=[
            "https://www.coinbase.com/faucets/base-ethereum-sepolia-faucet",
            "https://bridge.base.org/deposit",
            "https://www.alchemy.com/faucets/base-sepolia"
        ],
        description="Base Sepolia testnet - L2 testnet for Base ecosystem"
    ),
    421614: TestnetInfo(  # Arbitrum Sepolia
        name="Arbitrum Sepolia",
        chain_id=421614,
        currency_symbol="ETH",
        block_explorer="https://sepolia.arbiscan.io",
        faucet_urls=[
            "https://bridge.arbitrum.io/",
            "https://faucet.quicknode.com/arbitrum/sepolia"
        ],
        description="Arbitrum Sepolia testnet - L2 testnet for Arbitrum ecosystem"
    ),
    80001: TestnetInfo(  # Polygon Mumbai (being deprecated but still useful)
        name="Polygon Mumbai",
        chain_id=80001,
        currency_symbol="MATIC",
        block_explorer="https://mumbai.polygonscan.com",
        faucet_urls=[
            "https://faucet.polygon.technology/",
            "https://mumbaifaucet.com/"
        ],
        description="Polygon Mumbai testnet - being deprecated, use for legacy testing"
    )
}


def get_testnet_chain_configs() -> Dict[int, Dict]:
    """
    Get simplified chain configurations for all supported testnets.
    
    Returns:
        Dict mapping chain_id to basic config info
    """
    configs = {}
    
    # Sepolia (Ethereum testnet)
    configs[11155111] = {
        'chain_id': 11155111,
        'name': 'Sepolia',
        'native_currency': 'ETH',
        'rpc_urls': [
            f"https://eth-sepolia.g.alchemy.com/v2/{os.getenv('ALCHEMY_API_KEY', 'demo')}",
            "https://rpc.sepolia.org",
            "https://rpc.ankr.com/eth_sepolia"
        ],
        'is_testnet': True,
        'block_time_seconds': 12
    }
    
    # Base Sepolia 
    configs[84532] = {
        'chain_id': 84532,
        'name': 'Base Sepolia',
        'native_currency': 'ETH',
        'rpc_urls': [
            f"https://base-sepolia.g.alchemy.com/v2/{os.getenv('ALCHEMY_API_KEY', 'demo')}",
            "https://sepolia.base.org",
            "https://rpc.ankr.com/base_sepolia"
        ],
        'is_testnet': True,
        'block_time_seconds': 2
    }
    
    # Arbitrum Sepolia
    configs[421614] = {
        'chain_id': 421614,
        'name': 'Arbitrum Sepolia',
        'native_currency': 'ETH',
        'rpc_urls': [
            f"https://arb-sepolia.g.alchemy.com/v2/{os.getenv('ALCHEMY_API_KEY', 'demo')}",
            "https://sepolia-rollup.arbitrum.io/rpc"
        ],
        'is_testnet': True,
        'block_time_seconds': 1
    }
    
    return configs


def get_testnet_tokens() -> Dict[int, Dict[str, Dict[str, str]]]:
    """
    Get common test tokens for each testnet.
    
    Returns:
        Dict mapping chain_id -> token_symbol -> token_info
    """
    return {
        11155111: {  # Sepolia
            "WETH": {
                "address": "0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14",
                "decimals": "18",
                "name": "Wrapped Ether"
            },
            "USDC": {
                "address": "0x6f14C02Fc1F78322cFd7d707aB90f18baD3B54f5", 
                "decimals": "6",
                "name": "USD Coin (Sepolia)"
            },
            "DAI": {
                "address": "0x3e622317f8C93f7328350cF0B56d9eD4C620C5d6",
                "decimals": "18", 
                "name": "Dai Stablecoin (Sepolia)"
            }
        },
        84532: {  # Base Sepolia
            "WETH": {
                "address": "0x4200000000000000000000000000000000000006",
                "decimals": "18",
                "name": "Wrapped Ether"
            },
            "USDbC": {
                "address": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
                "decimals": "6",
                "name": "USD Base Coin (Sepolia)"
            }
        },
        421614: {  # Arbitrum Sepolia
            "WETH": {
                "address": "0x980B62Da83eFf3D4576C647993b0c1D7faf17c73",
                "decimals": "18",
                "name": "Wrapped Ether"
            }
        }
    }


def get_testnet_info(chain_id: int) -> Optional[TestnetInfo]:
    """Get testnet information for a chain ID."""
    return TESTNETS.get(chain_id)


def is_testnet(chain_id: int) -> bool:
    """Check if a chain ID is a testnet."""
    return chain_id in TESTNETS


def get_recommended_testnet() -> int:
    """Get the recommended testnet for development (Base Sepolia for speed)."""
    return 84532  # Base Sepolia


def get_testnet_faucet_instructions(chain_id: int) -> Dict[str, any]:
    """
    Get instructions for getting testnet funds.
    
    Args:
        chain_id: Testnet chain ID
        
    Returns:
        Dict with faucet instructions
    """
    testnet = get_testnet_info(chain_id)
    if not testnet:
        return {"error": f"Unknown testnet chain ID: {chain_id}"}
    
    instructions = {
        "testnet_name": testnet.name,
        "currency": testnet.currency_symbol,
        "faucet_urls": testnet.faucet_urls,
        "block_explorer": testnet.block_explorer,
        "instructions": []
    }
    
    if chain_id == 11155111:  # Sepolia
        instructions["instructions"] = [
            "1. Visit one of the faucet URLs above",
            "2. Connect your wallet or enter your address",
            "3. Request Sepolia ETH (usually 0.5-1 ETH per request)",
            "4. Wait for the transaction to confirm (usually 1-2 minutes)",
            "5. Check your balance on the block explorer"
        ]
    elif chain_id == 84532:  # Base Sepolia
        instructions["instructions"] = [
            "1. First get Sepolia ETH from Ethereum Sepolia faucet",
            "2. Visit the Base bridge: https://bridge.base.org/deposit",
            "3. Bridge Sepolia ETH to Base Sepolia (small amount for gas)",
            "4. Or use Coinbase faucet directly for Base Sepolia ETH",
            "5. Transactions confirm very quickly on Base (~2 seconds)"
        ]
    elif chain_id == 421614:  # Arbitrum Sepolia
        instructions["instructions"] = [
            "1. First get Sepolia ETH from Ethereum Sepolia faucet", 
            "2. Visit the Arbitrum bridge: https://bridge.arbitrum.io/",
            "3. Bridge Sepolia ETH to Arbitrum Sepolia",
            "4. Or use faucets that provide Arbitrum Sepolia ETH directly",
            "5. Transactions confirm very quickly on Arbitrum (~1 second)"
        ]
    
    return instructions


def create_testnet_settings_override() -> Dict[str, any]:
    """
    Create Django settings override for testnet development.
    
    Returns:
        Dict with settings to override for testnet usage
    """
    return {
        # Force paper trading for safety
        'TRADING_MODE': 'PAPER',
        'ENABLE_MOCK_MODE': True,
        
        # Use testnet configurations
        'DEFAULT_CHAIN_ID': get_recommended_testnet(),  # Base Sepolia
        'TESTNET_MODE': True,
        
        # Reduced limits for testing
        'MAX_PORTFOLIO_SIZE_USD': 100.0,  # Very small for testing
        'MAX_POSITION_SIZE_USD': 10.0,
        'DAILY_LOSS_LIMIT_PERCENT': 50.0,  # Higher tolerance for testing
        
        # Testnet gas settings
        'MAX_GAS_PRICE_GWEI': 100.0,  # Higher for testnet
        'DEFAULT_SLIPPAGE_PERCENT': 5.0,  # Higher slippage tolerance
        
        # Faster timeouts for testing
        'EXECUTION_TIMEOUT_SECONDS': 60,
        'RISK_TIMEOUT_SECONDS': 30,
        
        # Enhanced logging for development
        'LOG_LEVEL': 'DEBUG',
        'CELERY_TASK_ALWAYS_EAGER': False,  # Keep async for realistic testing
    }


def validate_testnet_environment() -> Dict[str, any]:
    """
    Validate that the environment is properly configured for testnet usage.
    
    Returns:
        Dict with validation results
    """
    results = {
        'is_valid': True,
        'warnings': [],
        'errors': [],
        'recommendations': []
    }
    
    # Check trading mode
    trading_mode = os.getenv('TRADING_MODE', 'PAPER')
    if trading_mode != 'PAPER':
        results['warnings'].append(
            f"Trading mode is '{trading_mode}' - recommend 'PAPER' for testnet"
        )
    
    # Check for API keys
    if not os.getenv('ALCHEMY_API_KEY'):
        results['warnings'].append(
            "No ALCHEMY_API_KEY found - will use public RPC endpoints (slower/less reliable)"
        )
    
    # Check wallet configuration
    if not os.getenv('WALLET_PRIVATE_KEY'):
        results['recommendations'].append(
            "No WALLET_PRIVATE_KEY set - system will create development wallet"
        )
    
    # Check default chain
    default_chain = int(os.getenv('DEFAULT_CHAIN_ID', 1))
    if not is_testnet(default_chain):
        results['errors'].append(
            f"DEFAULT_CHAIN_ID ({default_chain}) is not a testnet! "
            f"Recommend {get_recommended_testnet()} (Base Sepolia)"
        )
        results['is_valid'] = False
    
    # Check Django settings
    try:
        from django.conf import settings
        if hasattr(settings, 'TRADING_MODE') and settings.TRADING_MODE != 'PAPER':
            results['errors'].append(
                f"Django TRADING_MODE is '{settings.TRADING_MODE}' - must be 'PAPER' for testnet"
            )
            results['is_valid'] = False
    except:
        results['warnings'].append("Could not check Django settings")
    
    return results


class TestnetSetupGuide:
    """Helper class to guide testnet setup."""
    
    @staticmethod
    def print_setup_instructions():
        """Print comprehensive testnet setup instructions."""
        print("🧪 DEX Trading Bot - Testnet Setup Guide")
        print("=" * 50)
        print()
        
        print("📋 Prerequisites:")
        print("1. Set environment variables:")
        print("   - ALCHEMY_API_KEY (recommended for reliable RPC)")
        print("   - WALLET_PRIVATE_KEY (for testnet wallet)")
        print("   - Or let the system create a development wallet")
        print()
        
        print("💰 Getting Testnet Funds:")
        recommended_chain = get_recommended_testnet()
        instructions = get_testnet_faucet_instructions(recommended_chain)
        
        print(f"Recommended testnet: {instructions['testnet_name']} (Chain ID: {recommended_chain})")
        print("Faucet URLs:")
        for url in instructions['faucet_urls']:
            print(f"  - {url}")
        print()
        
        for instruction in instructions['instructions']:
            print(f"  {instruction}")
        print()
        
        print("🚀 Quick Start:")
        print("1. cd dexproject")
        print("2. export TRADING_MODE=PAPER")
        print(f"3. export DEFAULT_CHAIN_ID={recommended_chain}")
        print("4. python manage.py shell -c \"from trading.tasks import check_wallet_status; print(check_wallet_status.delay())\"")
        print("5. Check wallet status and fund if needed")
        print()
        
        print("⚠️  Safety Reminders:")
        print("- Always use TRADING_MODE=PAPER for testing")
        print("- Testnet funds have no real value")
        print("- Never use mainnet private keys on testnets")
        print("- Monitor gas usage even on testnets")
        print("- Test all functionality before mainnet deployment")


# Backward compatibility functions
def get_testnet_chain_config(chain_id: int) -> Optional[Dict]:
    """Get chain config for specific testnet."""
    configs = get_testnet_chain_configs()
    return configs.get(chain_id)


def list_available_testnets() -> List[int]:
    """Get list of available testnet chain IDs."""
    return list(TESTNETS.keys())


def get_testnet_summary() -> Dict[str, any]:
    """Get summary of all available testnets."""
    return {
        'available_testnets': len(TESTNETS),
        'recommended': get_recommended_testnet(),
        'testnets': {
            chain_id: {
                'name': info.name,
                'currency': info.currency_symbol,
                'explorer': info.block_explorer
            }
            for chain_id, info in TESTNETS.items()
        }
    }