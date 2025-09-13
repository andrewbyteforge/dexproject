#!/usr/bin/env python
"""
Populate Testnet Chains and DEXes for DEX Trading Bot

This script populates the Django database with testnet chain configurations
so the engine can load all 3 target chains properly.

Usage:
    cd dexproject
    python populate_testnet_chains.py
"""

import os
import sys
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

from trading.models import Chain, DEX


def populate_testnet_chains():
    """Populate Django database with testnet chain configurations."""
    
    print("🔧 Populating Testnet Chains...")
    print("=" * 50)
    
    # Testnet chain configurations
    testnet_chains = [
        {
            'name': 'Sepolia',
            'chain_id': 11155111,
            'rpc_url': 'https://eth-sepolia.g.alchemy.com/v2/demo',
            'fallback_rpc_urls': [
                'https://sepolia.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161',
                'https://rpc.sepolia.org'
            ],
            'block_time_seconds': 12,
            'gas_price_gwei': Decimal('20.0'),
            'max_gas_price_gwei': Decimal('100.0'),
            'is_active': True,
        },
        {
            'name': 'Base Sepolia',
            'chain_id': 84532,
            'rpc_url': 'https://base-sepolia.g.alchemy.com/v2/demo',
            'fallback_rpc_urls': [
                'https://sepolia.base.org',
                'https://base-sepolia-rpc.publicnode.com'
            ],
            'block_time_seconds': 2,
            'gas_price_gwei': Decimal('1.0'),
            'max_gas_price_gwei': Decimal('50.0'),
            'is_active': True,
        },
        {
            'name': 'Arbitrum Sepolia',
            'chain_id': 421614,
            'rpc_url': 'https://arb-sepolia.g.alchemy.com/v2/demo',
            'fallback_rpc_urls': [
                'https://sepolia-rollup.arbitrum.io/rpc',
                'https://arbitrum-sepolia-rpc.publicnode.com'
            ],
            'block_time_seconds': 1,
            'gas_price_gwei': Decimal('0.1'),
            'max_gas_price_gwei': Decimal('10.0'),
            'is_active': True,
        }
    ]
    
    # Create or update chains
    created_chains = []
    updated_chains = []
    
    for chain_data in testnet_chains:
        chain, created = Chain.objects.get_or_create(
            chain_id=chain_data['chain_id'],
            defaults=chain_data
        )
        
        if created:
            created_chains.append(chain)
            print(f"✅ Created: {chain.name} (Chain ID: {chain.chain_id})")
        else:
            # Update existing chain with new data
            for field, value in chain_data.items():
                setattr(chain, field, value)
            chain.save()
            updated_chains.append(chain)
            print(f"🔄 Updated: {chain.name} (Chain ID: {chain.chain_id})")
    
    # Now create DEXes for each chain - CORRECTED VERSION
    print("\n📊 Creating DEX configurations...")
    
    # DEX configurations matching Django model fields exactly
    dex_configs = [
        # Sepolia DEXes
        {
            'name': 'Uniswap V3 Sepolia',
            'chain_id': 11155111,
            'router_address': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
            'factory_address': '0x1F98431c8aD98523631AE4a59f267346ea31F984',
            'fee_percentage': Decimal('0.3000'),  # 0.3%
            'is_active': True,
        },
        {
            'name': 'Uniswap V2 Sepolia',
            'chain_id': 11155111,
            'router_address': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
            'factory_address': '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',
            'fee_percentage': Decimal('0.3000'),  # 0.3%
            'is_active': True,
        },
        # Base Sepolia DEXes
        {
            'name': 'Uniswap V3 Base Sepolia',
            'chain_id': 84532,
            'router_address': '0x2626664c2603336E57B271c5C0b26F421741e481',
            'factory_address': '0x33128a8fC17869897dcE68Ed026d694621f6FDfD',
            'fee_percentage': Decimal('0.3000'),  # 0.3%
            'is_active': True,
        },
        # Arbitrum Sepolia DEXes  
        {
            'name': 'Uniswap V3 Arbitrum Sepolia',
            'chain_id': 421614,
            'router_address': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
            'factory_address': '0x1F98431c8aD98523631AE4a59f267346ea31F984',
            'fee_percentage': Decimal('0.3000'),  # 0.3%
            'is_active': True,
        }
    ]
    
    created_dexes = []
    updated_dexes = []
    
    for dex_data in dex_configs:
        # Get the chain for this DEX
        try:
            chain = Chain.objects.get(chain_id=dex_data['chain_id'])
        except Chain.DoesNotExist:
            print(f"❌ Chain {dex_data['chain_id']} not found for DEX {dex_data['name']}")
            continue
        
        # Create DEX data without chain_id (we'll use the chain object)
        # ONLY include fields that exist in the Django DEX model
        dex_create_data = {
            'name': dex_data['name'],
            'chain': chain,
            'router_address': dex_data['router_address'],
            'factory_address': dex_data['factory_address'],
            'fee_percentage': dex_data['fee_percentage'],
            'is_active': dex_data['is_active'],
        }
        
        # Try to find existing DEX
        existing_dex = DEX.objects.filter(
            name=dex_data['name'],
            chain=chain
        ).first()
        
        if existing_dex:
            # Update existing DEX
            for field, value in dex_create_data.items():
                setattr(existing_dex, field, value)
            existing_dex.save()
            updated_dexes.append(existing_dex)
            print(f"🔄 Updated: {existing_dex.name} on {chain.name}")
        else:
            # Create new DEX
            dex = DEX.objects.create(**dex_create_data)
            created_dexes.append(dex)
            print(f"✅ Created: {dex.name} on {chain.name}")
    
    # Summary
    print("\n📊 Population Summary:")
    print(f"   Chains: {len(created_chains)} created, {len(updated_chains)} updated")
    print(f"   DEXes:  {len(created_dexes)} created, {len(updated_dexes)} updated")
    
    # Verify the data
    print("\n🔍 Verification:")
    total_chains = Chain.objects.count()
    active_chains = Chain.objects.filter(is_active=True).count()
    total_dexes = DEX.objects.count()
    active_dexes = DEX.objects.filter(is_active=True).count()
    
    print(f"   Total chains: {total_chains} ({active_chains} active)")
    print(f"   Total DEXes:  {total_dexes} ({active_dexes} active)")
    
    # Show chain details
    print("\n📋 Current Chain Configuration:")
    for chain in Chain.objects.filter(is_active=True).order_by('chain_id'):
        dex_count = DEX.objects.filter(chain=chain, is_active=True).count()
        print(f"   - {chain.name} (ID: {chain.chain_id}): {dex_count} DEXes")
    
    return len(created_chains) + len(updated_chains)


def test_engine_config():
    """Test if the engine can now load all chains."""
    print("\n🧪 Testing Engine Configuration...")
    
    try:
        from engine.config import EngineConfig
        import asyncio
        
        # Create config
        config = EngineConfig()
        print(f"   Target chains: {config.target_chains}")
        
        # Test async initialization
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        loop.run_until_complete(config.initialize_chain_configs())
        
        print(f"   [OK] Chains loaded: {len(config.chains)}")
        for chain_id, chain_config in config.chains.items():
            print(f"      - {chain_config.name} (ID: {chain_id}): {len(chain_config.rpc_providers)} RPC providers")
        
        if len(config.chains) == 3:
            print("   ✅ SUCCESS: All 3 testnet chains loaded correctly!")
            return True
        else:
            print(f"   ⚠️  WARNING: Expected 3 chains, got {len(config.chains)}")
            return False
            
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main function."""
    print("🚀 DEX Trading Bot - Testnet Chain Population")
    print("=" * 60)
    
    try:
        # Populate chains and DEXes
        chains_processed = populate_testnet_chains()
        
        if chains_processed > 0:
            # Test engine configuration
            success = test_engine_config()
            
            if success:
                print("\n🎉 SUCCESS: Testnet chains populated and engine config working!")
                print("\nNext steps:")
                print("1. Restart your Django shell")
                print("2. Re-run your engine configuration test")
                print("3. You should now see all 3 chains loading")
            else:
                print("\n⚠️  Chains populated but engine config test failed")
                print("Check the error messages above")
        else:
            print("\n⚠️  No changes made to database")
            
    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())