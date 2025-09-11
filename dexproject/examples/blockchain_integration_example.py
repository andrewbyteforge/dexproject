"""
Real Blockchain Integration Usage Example

Demonstrates how to use the enhanced Web3 infrastructure for
production-ready blockchain integration with Django.

File: examples/blockchain_integration_example.py
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from decimal import Decimal

# Django setup
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

# Import our enhanced modules
from engine.config import config
from engine.utils import ProviderManager, setup_logging, get_token_info, get_latest_block
from engine.discovery import PairDiscoveryService, MultiChainDiscoveryManager, NewPairEvent
from risk.tasks.liquidity import enhanced_liquidity_check, get_pair_liquidity_info, estimate_trade_slippage

# Set up logging
setup_logging()
logger = logging.getLogger(__name__)


async def example_provider_management():
    """
    Example 1: Using Provider Manager with Automatic Failover
    
    Shows how to use the enhanced provider manager for reliable
    blockchain connectivity with automatic failover.
    """
    print("\n=== Example 1: Provider Management with Failover ===")
    
    # Get chain configuration (Base network)
    chain_config = config.get_chain_config(8453)  # Base
    if not chain_config:
        print("❌ No configuration found for Base network")
        return
    
    # Initialize provider manager
    provider_manager = ProviderManager(chain_config)
    
    try:
        # Get Web3 instance with automatic failover
        w3 = await provider_manager.get_web3()
        if w3:
            # Get latest block number
            block_number = await get_latest_block(provider_manager)
            print(f"✅ Connected to {chain_config.name}")
            print(f"📊 Latest block: {block_number}")
            print(f"🔗 Current provider: {provider_manager.current_provider}")
            
            # Get health summary
            health = provider_manager.get_health_summary()
            print(f"🏥 Provider health:")
            for provider_name, status in health['providers'].items():
                print(f"   {provider_name}: {status['status']} "
                      f"(Success rate: {status['success_rate']:.1f}%, "
                      f"Latency: {status['average_latency_ms']:.1f}ms)")
        else:
            print("❌ Failed to connect to blockchain")
            
    finally:
        await provider_manager.close()


async def example_token_analysis():
    """
    Example 2: Real Token Information Retrieval
    
    Shows how to get comprehensive token information using
    real blockchain calls with provider failover.
    """
    print("\n=== Example 2: Real Token Analysis ===")
    
    # Well-known token addresses for testing
    test_tokens = {
        "USDC (Base)": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "WETH (Base)": "0x4200000000000000000000000000000000000006",
    }
    
    chain_config = config.get_chain_config(8453)  # Base
    if not chain_config:
        print("❌ No chain configuration available")
        return
    
    provider_manager = ProviderManager(chain_config)
    
    try:
        for token_name, token_address in test_tokens.items():
            print(f"\n🪙 Analyzing {token_name}...")
            
            token_info = await get_token_info(provider_manager, token_address)
            
            if token_info:
                print(f"   Name: {token_info['name']}")
                print(f"   Symbol: {token_info['symbol']}")
                print(f"   Decimals: {token_info['decimals']}")
                print(f"   Total Supply: {token_info['total_supply']:,}")
                print(f"   Address: {token_info['address']}")
            else:
                print(f"   ❌ Failed to get token information")
                
    finally:
        await provider_manager.close()


async def example_liquidity_analysis():
    """
    Example 3: Enhanced Liquidity Risk Assessment
    
    Shows how to perform comprehensive liquidity analysis
    with real blockchain data and slippage calculations.
    """
    print("\n=== Example 3: Enhanced Liquidity Analysis ===")
    
    # Example Uniswap V3 pool on Base (USDC/WETH)
    test_pair = "0xd0b53D9277642d899DF5C87A3966A349A798F224"  # Example pool address
    
    print(f"🏊 Analyzing liquidity for pool: {test_pair[:8]}...")
    
    try:
        # Get basic liquidity info
        liquidity_info = await get_pair_liquidity_info(8453, test_pair)
        
        if liquidity_info:
            print(f"   💰 Total Liquidity: ${liquidity_info['total_liquidity_usd']:,.2f}")
            print(f"   🏭 Pair Type: {liquidity_info['pair_type']}")
            print(f"   💸 Fee Tier: {liquidity_info['fee_tier'] / 10000:.2f}%")
            
            # Test slippage for different trade sizes
            trade_sizes = [1000, 5000, 10000]  # USD
            print(f"\n📈 Slippage Analysis:")
            
            for trade_size in trade_sizes:
                slippage = await estimate_trade_slippage(8453, test_pair, trade_size)
                if slippage is not None:
                    print(f"   ${trade_size:,} trade: {slippage:.2f}% slippage")
                else:
                    print(f"   ${trade_size:,} trade: Unable to calculate")
        else:
            print("   ❌ Failed to get liquidity information")
            
    except Exception as e:
        logger.error(f"Liquidity analysis failed: {e}")


def example_celery_task_usage():
    """
    Example 4: Using Enhanced Risk Assessment Tasks
    
    Shows how to trigger enhanced risk assessment tasks
    that use real blockchain connectivity.
    """
    print("\n=== Example 4: Enhanced Celery Risk Tasks ===")
    
    # Example pair for risk assessment
    test_pair = "0xd0b53D9277642d899DF5C87A3966A349A798F224"
    test_token = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # USDC
    
    print(f"🔍 Triggering enhanced liquidity risk assessment...")
    print(f"   Pair: {test_pair}")
    print(f"   Token: {test_token}")
    
    try:
        # Trigger enhanced liquidity check (synchronous call for demo)
        # In production, this would be: enhanced_liquidity_check.delay(...)
        from risk.tasks.liquidity import enhanced_liquidity_check
        
        result = enhanced_liquidity_check(
            pair_address=test_pair,
            token_address=test_token,
            chain_id=8453,
            min_liquidity_usd=10000.0,
            max_slippage_percent=5.0,
            test_trade_sizes=[1000, 5000, 10000]
        )
        
        print(f"   ✅ Risk Assessment Complete:")
        print(f"   Status: {result.get('status', 'Unknown')}")
        print(f"   Risk Score: {result.get('risk_score', 'N/A')}/100")
        print(f"   Execution Time: {result.get('execution_time_ms', 0):.1f}ms")
        
        # Display key metrics from details
        details = result.get('details', {})
        liquidity_data = details.get('liquidity_depth', {})
        slippage_data = details.get('slippage_impact', {})
        
        if liquidity_data:
            print(f"   💰 Total Liquidity: ${liquidity_data.get('total_liquidity_usd', 0):,.2f}")
        
        if slippage_data:
            print(f"   📊 Max Slippage: {slippage_data.get('max_slippage_percent', 0):.2f}%")
            
    except Exception as e:
        print(f"   ❌ Risk assessment failed: {e}")


async def example_discovery_service():
    """
    Example 5: Real-time Pair Discovery
    
    Shows how to use the enhanced discovery service to monitor
    for new trading pairs in real-time.
    """
    print("\n=== Example 5: Real-time Pair Discovery ===")
    
    discovered_pairs = []
    
    def pair_discovery_callback(pair_event: NewPairEvent):
        """Handle newly discovered pairs."""
        discovered_pairs.append(pair_event)
        print(f"🆕 New pair discovered: {pair_event.token0_symbol}/{pair_event.token1_symbol}")
        print(f"   Pool: {pair_event.pool_address[:8]}...")
        print(f"   Fee: {pair_event.fee_tier/10000:.2f}%")
        print(f"   Block: {pair_event.block_number}")
        print(f"   Discovery Latency: {pair_event.discovery_latency_ms:.1f}ms")
        print(f"   Is WETH Pair: {pair_event.is_weth_pair}")
        print(f"   Is Tradeable: {pair_event.is_tradeable()}")
    
    # Initialize multi-chain discovery manager
    discovery_manager = MultiChainDiscoveryManager(pair_discovery_callback)
    
    print(f"🔎 Starting discovery service for {len(config.target_chains)} chains...")
    print("   (This will run for 30 seconds to demonstrate real-time discovery)")
    
    try:
        # Start discovery
        discovery_task = asyncio.create_task(discovery_manager.start())
        
        # Let it run for 30 seconds
        await asyncio.sleep(30)
        
        # Stop discovery
        await discovery_manager.stop()
        
        print(f"\n📈 Discovery Summary:")
        print(f"   Pairs discovered: {len(discovered_pairs)}")
        
        if discovered_pairs:
            tradeable_pairs = [p for p in discovered_pairs if p.is_tradeable()]
            weth_pairs = [p for p in discovered_pairs if p.is_weth_pair]
            
            print(f"   Tradeable pairs: {len(tradeable_pairs)}")
            print(f"   WETH pairs: {len(weth_pairs)}")
            
            # Show discovery performance
            if discovered_pairs:
                avg_latency = sum(p.discovery_latency_ms for p in discovered_pairs if p.discovery_latency_ms) / len(discovered_pairs)
                print(f"   Average discovery latency: {avg_latency:.1f}ms")
        
    except Exception as e:
        logger.error(f"Discovery service error: {e}")
        await discovery_manager.stop()


async def example_configuration_validation():
    """
    Example 6: Configuration Validation and Health Check
    
    Shows how to validate the enhanced configuration and
    check the health of all configured providers.
    """
    print("\n=== Example 6: Configuration & Health Check ===")
    
    print(f"⚙️  Configuration Summary:")
    print(f"   Trading Mode: {config.trading_mode}")
    print(f"   Target Chains: {config.target_chains}")
    print(f"   Discovery Enabled: {config.discovery_enabled}")
    print(f"   Risk Timeout: {config.risk_timeout}s")
    
    # Check each configured chain
    for chain_id in config.target_chains:
        chain_config = config.get_chain_config(chain_id)
        if not chain_config:
            print(f"   ❌ {chain_id}: No configuration")
            continue
            
        print(f"\n🔗 {chain_config.name} (Chain ID: {chain_id}):")
        print(f"   Providers: {len(chain_config.rpc_providers)}")
        
        # Test connectivity for each provider
        provider_manager = ProviderManager(chain_config)
        
        try:
            # Test connection
            w3 = await provider_manager.get_web3()
            if w3:
                block_number = await get_latest_block(provider_manager)
                print(f"   ✅ Connected - Block: {block_number}")
                
                # Show provider health
                health = provider_manager.get_health_summary()
                paid_providers = [p for p in health['providers'].values() if p['is_paid']]
                public_providers = [p for p in health['providers'].values() if not p['is_paid']]
                
                print(f"   💰 Paid providers: {len(paid_providers)} available")
                print(f"   🌐 Public providers: {len(public_providers)} available")
                print(f"   📊 Success rate: {health['success_rate']:.1f}%")
            else:
                print(f"   ❌ Connection failed")
                
        finally:
            await provider_manager.close()


async def run_all_examples():
    """Run all blockchain integration examples."""
    print("🚀 Real Blockchain Integration Examples")
    print("=" * 50)
    
    try:
        # Example 1: Provider Management
        await example_provider_management()
        
        # Example 2: Token Analysis
        await example_token_analysis()
        
        # Example 3: Liquidity Analysis
        await example_liquidity_analysis()
        
        # Example 4: Celery Risk Tasks
        example_celery_task_usage()
        
        # Example 5: Discovery Service (commented out for demo - runs for 30 seconds)
        # await example_discovery_service()
        
        # Example 6: Configuration Validation
        await example_configuration_validation()
        
        print("\n✅ All examples completed successfully!")
        
    except Exception as e:
        logger.error(f"Example execution failed: {e}")
        print(f"❌ Example failed: {e}")


def show_environment_setup():
    """Show required environment variable setup."""
    print("\n📋 Required Environment Variables:")
    print("=" * 40)
    
    required_vars = [
        ("BASE_RPC_URL", "Alchemy/Infura Base RPC URL"),
        ("BASE_WS_URL", "WebSocket URL for Base"),
        ("BASE_API_KEY", "API key for Base provider"),
        ("ETH_RPC_URL", "Alchemy/Infura Ethereum RPC URL"),
        ("ETH_WS_URL", "WebSocket URL for Ethereum"),
        ("ETH_API_KEY", "API key for Ethereum provider"),
        ("TRADING_MODE", "PAPER | SHADOW | LIVE"),
        ("TARGET_CHAINS", "8453,1 (Base + Ethereum)"),
        ("LOG_LEVEL", "DEBUG | INFO | WARNING | ERROR"),
    ]
    
    for var_name, description in required_vars:
        value = os.getenv(var_name, "❌ NOT SET")
        if value == "❌ NOT SET":
            print(f"   {var_name:<20}: {value}")
        else:
            # Mask sensitive values
            if 'key' in var_name.lower() or 'url' in var_name.lower():
                masked_value = value[:10] + "..." if len(value) > 10 else value
                print(f"   {var_name:<20}: {masked_value} ✅")
            else:
                print(f"   {var_name:<20}: {value} ✅")
    
    print("\n💡 Copy the sample .env file and configure with your actual API keys!")


if __name__ == "__main__":
    # Show environment setup
    show_environment_setup()
    
    print("\n" + "=" * 60)
    print("🧪 Starting Blockchain Integration Examples")
    print("=" * 60)
    
    # Run all examples
    asyncio.run(run_all_examples())