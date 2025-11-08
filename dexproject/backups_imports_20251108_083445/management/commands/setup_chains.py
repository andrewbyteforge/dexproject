"""
Django management command to set up blockchain chain configurations.

This command creates or updates Chain objects in the database using
configuration from Django settings, including RPC URLs, gas settings,
and chain-specific parameters.

Usage:
    python manage.py setup_chains
    python manage.py setup_chains --testnet
    python manage.py setup_chains --force  # Overwrite existing

File: trading/management/commands/setup_chains.py
"""

from decimal import Decimal
from typing import Dict, Any, List
import logging

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction

from trading.models import Chain

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command to set up Chain configurations.
    
    Creates Chain objects for all supported blockchain networks using
    configuration from Django settings.
    """
    
    help = 'Set up blockchain chain configurations from Django settings'
    
    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            '--testnet',
            action='store_true',
            help='Configure testnet chains instead of mainnet',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite existing chain configurations',
        )
        parser.add_argument(
            '--chain-id',
            type=int,
            help='Only set up a specific chain by ID',
        )
    
    def handle(self, *args, **options):
        """Execute the command."""
        self.stdout.write(self.style.NOTICE('=' * 80))
        self.stdout.write(self.style.NOTICE('🔗 Setting up Chain Configurations'))
        self.stdout.write(self.style.NOTICE('=' * 80))
        
        testnet_mode = options['testnet'] or getattr(settings, 'TESTNET_MODE', False)
        force_update = options['force']
        specific_chain = options.get('chain_id')
        
        self.stdout.write(f"Mode: {'TESTNET' if testnet_mode else 'MAINNET'}")
        self.stdout.write(f"Force update: {force_update}")
        self.stdout.write('')
        
        # Get chain configurations
        chain_configs = self._get_chain_configs(testnet_mode)
        
        # Filter to specific chain if requested
        if specific_chain:
            chain_configs = {
                cid: config for cid, config in chain_configs.items()
                if cid == specific_chain
            }
            if not chain_configs:
                raise CommandError(f"Chain ID {specific_chain} not found in configuration")
        
        if not chain_configs:
            self.stdout.write(self.style.ERROR('❌ No chain configurations found!'))
            self.stdout.write(self.style.WARNING('Please set RPC URLs in your settings or .env file'))
            return
        
        # Create or update chains
        created_count = 0
        updated_count = 0
        skipped_count = 0
        
        with transaction.atomic():
            for chain_id, config in chain_configs.items():
                try:
                    result = self._setup_chain(chain_id, config, force_update)
                    
                    if result == 'created':
                        created_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(f"  ✅ Created: {config['name']} (Chain {chain_id})")
                        )
                    elif result == 'updated':
                        updated_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(f"  🔄 Updated: {config['name']} (Chain {chain_id})")
                        )
                    else:  # skipped
                        skipped_count += 1
                        self.stdout.write(
                            self.style.WARNING(f"  ⏭️  Skipped: {config['name']} (Chain {chain_id}) - already exists")
                        )
                
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"  ❌ Failed: Chain {chain_id} - {e}")
                    )
                    logger.error(f"Failed to set up chain {chain_id}: {e}", exc_info=True)
        
        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.NOTICE('=' * 80))
        self.stdout.write(self.style.NOTICE('📊 Summary'))
        self.stdout.write(self.style.NOTICE('=' * 80))
        self.stdout.write(f"  Created: {created_count}")
        self.stdout.write(f"  Updated: {updated_count}")
        self.stdout.write(f"  Skipped: {skipped_count}")
        self.stdout.write(f"  Total: {created_count + updated_count + skipped_count}")
        self.stdout.write('')
        
        if created_count > 0 or updated_count > 0:
            self.stdout.write(self.style.SUCCESS('✅ Chain configurations set up successfully!'))
            self.stdout.write('')
            self.stdout.write('Next steps:')
            self.stdout.write('  1. Restart your Django server')
            self.stdout.write('  2. Run the bot: python manage.py run_paper_bot')
            self.stdout.write('  3. The chain configuration warning should be gone!')
        else:
            self.stdout.write(self.style.WARNING('⚠️  No chains were created or updated'))
            if not force_update:
                self.stdout.write('  Tip: Use --force to update existing configurations')
    
    def _get_chain_configs(self, testnet_mode: bool) -> Dict[int, Dict[str, Any]]:
        """
        Get chain configurations from Django settings.
        
        Args:
            testnet_mode: Whether to configure testnet or mainnet chains
            
        Returns:
            Dictionary mapping chain_id to configuration dict
        """
        configs = {}
        
        if testnet_mode:
            # Testnet configurations
            
            # Base Sepolia (84532)
            base_sepolia_rpc = getattr(settings, 'BASE_SEPOLIA_RPC_URL', None)
            if base_sepolia_rpc and base_sepolia_rpc != 'https://base-sepolia.g.alchemy.com/v2/demo':
                configs[84532] = {
                    'name': 'Base Sepolia',
                    'rpc_url': base_sepolia_rpc,
                    'fallback_rpc_urls': [
                        'https://sepolia.base.org',
                        'https://base-sepolia-rpc.publicnode.com'
                    ],
                    'block_time_seconds': 2,
                    'gas_price_gwei': Decimal('0.1'),
                    'max_gas_price_gwei': Decimal('10.0'),
                    'is_active': True,
                }
            
            # Ethereum Sepolia (11155111)
            sepolia_rpc = getattr(settings, 'SEPOLIA_RPC_URL', None)
            if sepolia_rpc and sepolia_rpc != 'https://eth-sepolia.g.alchemy.com/v2/demo':
                configs[11155111] = {
                    'name': 'Ethereum Sepolia',
                    'rpc_url': sepolia_rpc,
                    'fallback_rpc_urls': [
                        'https://rpc.sepolia.org',
                        'https://ethereum-sepolia-rpc.publicnode.com'
                    ],
                    'block_time_seconds': 12,
                    'gas_price_gwei': Decimal('1.0'),
                    'max_gas_price_gwei': Decimal('50.0'),
                    'is_active': True,
                }
        
        else:
            # Mainnet configurations
            
            # Base Mainnet (8453)
            base_mainnet_rpc = getattr(settings, 'BASE_MAINNET_RPC_URL', None)
            if base_mainnet_rpc and base_mainnet_rpc != 'https://base-mainnet.g.alchemy.com/v2/demo':
                configs[8453] = {
                    'name': 'Base',
                    'rpc_url': base_mainnet_rpc,
                    'fallback_rpc_urls': [
                        'https://mainnet.base.org',
                        'https://base-rpc.publicnode.com',
                        'https://base.gateway.tenderly.co'
                    ],
                    'block_time_seconds': 2,
                    'gas_price_gwei': Decimal('0.01'),
                    'max_gas_price_gwei': Decimal('50.0'),
                    'is_active': True,
                }
            
            # Ethereum Mainnet (1)
            eth_mainnet_rpc = getattr(settings, 'ETH_MAINNET_RPC_URL', None)
            if eth_mainnet_rpc and eth_mainnet_rpc != 'https://eth-mainnet.g.alchemy.com/v2/demo':
                configs[1] = {
                    'name': 'Ethereum',
                    'rpc_url': eth_mainnet_rpc,
                    'fallback_rpc_urls': [
                        'https://eth-rpc.gateway.pokt.network',
                        'https://ethereum-rpc.publicnode.com',
                        'https://eth.llamarpc.com'
                    ],
                    'block_time_seconds': 12,
                    'gas_price_gwei': Decimal('20.0'),
                    'max_gas_price_gwei': Decimal('100.0'),
                    'is_active': True,
                }
            
            # Arbitrum Mainnet (42161) - if configured
            arb_mainnet_rpc = getattr(settings, 'ARB_MAINNET_RPC_URL', None)
            if arb_mainnet_rpc and arb_mainnet_rpc != 'https://arb-mainnet.g.alchemy.com/v2/demo':
                configs[42161] = {
                    'name': 'Arbitrum',
                    'rpc_url': arb_mainnet_rpc,
                    'fallback_rpc_urls': [
                        'https://arb1.arbitrum.io/rpc',
                        'https://arbitrum-one-rpc.publicnode.com'
                    ],
                    'block_time_seconds': 1,
                    'gas_price_gwei': Decimal('0.1'),
                    'max_gas_price_gwei': Decimal('10.0'),
                    'is_active': True,
                }
        
        return configs
    
    def _setup_chain(self, chain_id: int, config: Dict[str, Any], force_update: bool) -> str:
        """
        Create or update a Chain object.
        
        Args:
            chain_id: Chain ID
            config: Chain configuration dict
            force_update: Whether to update existing chains
            
        Returns:
            'created', 'updated', or 'skipped'
        """
        try:
            chain = Chain.objects.get(chain_id=chain_id)
            
            if force_update:
                # Update existing chain
                chain.name = config['name']
                chain.rpc_url = config['rpc_url']
                chain.fallback_rpc_urls = config['fallback_rpc_urls']
                chain.block_time_seconds = config['block_time_seconds']
                chain.gas_price_gwei = config['gas_price_gwei']
                chain.max_gas_price_gwei = config['max_gas_price_gwei']
                chain.is_active = config['is_active']
                chain.save()
                
                logger.info(f"Updated chain {chain_id}: {config['name']}")
                return 'updated'
            else:
                logger.info(f"Skipped existing chain {chain_id}: {config['name']}")
                return 'skipped'
        
        except Chain.DoesNotExist:
            # Create new chain
            chain = Chain.objects.create(
                chain_id=chain_id,
                name=config['name'],
                rpc_url=config['rpc_url'],
                fallback_rpc_urls=config['fallback_rpc_urls'],
                block_time_seconds=config['block_time_seconds'],
                gas_price_gwei=config['gas_price_gwei'],
                max_gas_price_gwei=config['max_gas_price_gwei'],
                is_active=config['is_active']
            )
            
            logger.info(f"Created chain {chain_id}: {config['name']}")
            return 'created'