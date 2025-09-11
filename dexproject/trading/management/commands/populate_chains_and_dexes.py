"""
Django management command to populate initial chains and DEXes data.

This command creates the foundational blockchain networks and decentralized
exchanges needed for the DEX auto-trading bot to operate.
"""

import logging
from decimal import Decimal
from typing import Dict, List

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ...models import Chain, DEX


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Management command to populate initial chains and DEXes."""
    
    help = 'Populate initial blockchain chains and DEX data for trading bot'
    
    def add_arguments(self, parser) -> None:
        """Add command line arguments."""
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation of existing data (will delete existing chains/DEXes)',
        )
        parser.add_argument(
            '--chains-only',
            action='store_true',
            help='Only create chains, skip DEXes',
        )
        parser.add_argument(
            '--dexes-only',
            action='store_true',
            help='Only create DEXes, skip chains',
        )
    
    def handle(self, *args, **options) -> None:
        """Execute the command."""
        self.verbosity = options.get('verbosity', 1)
        force = options.get('force', False)
        chains_only = options.get('chains_only', False)
        dexes_only = options.get('dexes_only', False)
        
        try:
            with transaction.atomic():
                if force:
                    self._clear_existing_data()
                
                if not dexes_only:
                    chains_created = self._create_chains()
                    self._log_success(f"Created {chains_created} chains")
                
                if not chains_only:
                    dexes_created = self._create_dexes()
                    self._log_success(f"Created {dexes_created} DEXes")
                
                self._log_success("Initial data population completed successfully!")
                
        except Exception as e:
            logger.error(f"Failed to populate initial data: {e}")
            raise CommandError(f"Command failed: {e}")
    
    def _clear_existing_data(self) -> None:
        """Clear existing chains and DEXes if force flag is used."""
        self._log_info("Clearing existing chains and DEXes...")
        
        dex_count = DEX.objects.count()
        chain_count = Chain.objects.count()
        
        DEX.objects.all().delete()
        Chain.objects.all().delete()
        
        self._log_info(f"Deleted {dex_count} DEXes and {chain_count} chains")
    
    def _create_chains(self) -> int:
        """Create blockchain networks."""
        self._log_info("Creating blockchain networks...")
        
        chains_data = self._get_chains_data()
        chains_created = 0
        
        for chain_data in chains_data:
            chain, created = Chain.objects.get_or_create(
                chain_id=chain_data['chain_id'],
                defaults=chain_data
            )
            
            if created:
                chains_created += 1
                self._log_info(f"Created chain: {chain.name} (ID: {chain.chain_id})")
            else:
                self._log_info(f"Chain already exists: {chain.name}")
        
        return chains_created
    
    def _create_dexes(self) -> int:
        """Create decentralized exchanges."""
        self._log_info("Creating decentralized exchanges...")
        
        dexes_data = self._get_dexes_data()
        dexes_created = 0
        
        for dex_data in dexes_data:
            try:
                # Get the chain for this DEX
                chain = Chain.objects.get(chain_id=dex_data['chain_id'])
                dex_data['chain'] = chain
                del dex_data['chain_id']  # Remove chain_id as we now have chain object
                
                dex, created = DEX.objects.get_or_create(
                    name=dex_data['name'],
                    chain=chain,
                    defaults=dex_data
                )
                
                if created:
                    dexes_created += 1
                    self._log_info(f"Created DEX: {dex.name} on {chain.name}")
                else:
                    self._log_info(f"DEX already exists: {dex.name} on {chain.name}")
                    
            except Chain.DoesNotExist:
                logger.warning(f"Chain with ID {dex_data['chain_id']} not found, skipping DEX {dex_data['name']}")
                continue
        
        return dexes_created
    
    def _get_chains_data(self) -> List[Dict]:
        """Get chain configuration data."""
        return [
            {
                'name': 'Ethereum',
                'chain_id': 1,
                'rpc_url': 'https://eth-mainnet.g.alchemy.com/v2/demo',
                'fallback_rpc_urls': [
                    'https://mainnet.infura.io/v3/demo',
                    'https://ethereum.publicnode.com',
                    'https://rpc.ankr.com/eth'
                ],
                'block_time_seconds': 12,
                'gas_price_gwei': Decimal('20.0'),
                'max_gas_price_gwei': Decimal('100.0'),
                'is_active': True,
            },
            {
                'name': 'Base',
                'chain_id': 8453,
                'rpc_url': 'https://base-mainnet.g.alchemy.com/v2/demo',
                'fallback_rpc_urls': [
                    'https://mainnet.base.org',
                    'https://base.publicnode.com',
                    'https://rpc.ankr.com/base'
                ],
                'block_time_seconds': 2,
                'gas_price_gwei': Decimal('0.1'),
                'max_gas_price_gwei': Decimal('5.0'),
                'is_active': True,
            },
            {
                'name': 'Arbitrum',
                'chain_id': 42161,
                'rpc_url': 'https://arb-mainnet.g.alchemy.com/v2/demo',
                'fallback_rpc_urls': [
                    'https://arbitrum.publicnode.com',
                    'https://rpc.ankr.com/arbitrum'
                ],
                'block_time_seconds': 1,
                'gas_price_gwei': Decimal('0.1'),
                'max_gas_price_gwei': Decimal('2.0'),
                'is_active': False,  # Not enabled in MVP
            },
        ]
    
    def _get_dexes_data(self) -> List[Dict]:
        """Get DEX configuration data."""
        return [
            # Ethereum DEXes
            {
                'name': 'Uniswap V2',
                'chain_id': 1,
                'router_address': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
                'factory_address': '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',
                'fee_percentage': Decimal('0.3000'),
                'is_active': True,
            },
            {
                'name': 'Uniswap V3',
                'chain_id': 1,
                'router_address': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
                'factory_address': '0x1F98431c8aD98523631AE4a59f267346ea31F984',
                'fee_percentage': Decimal('0.3000'),  # Variable fees, using 0.3% as default
                'is_active': True,
            },
            {
                'name': 'SushiSwap',
                'chain_id': 1,
                'router_address': '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F',
                'factory_address': '0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac',
                'fee_percentage': Decimal('0.3000'),
                'is_active': False,  # Not prioritized in MVP
            },
            
            # Base DEXes
            {
                'name': 'Uniswap V3',
                'chain_id': 8453,
                'router_address': '0x2626664c2603336E57B271c5C0b26F421741e481',
                'factory_address': '0x33128a8fC17869897dcE68Ed026d694621f6FDfD',
                'fee_percentage': Decimal('0.3000'),
                'is_active': True,
            },
            {
                'name': 'BaseSwap',
                'chain_id': 8453,
                'router_address': '0x327Df1E6de05895d2ab08513aaDD9313Fe505d86',
                'factory_address': '0xFDa619b6d20975be80A10332cD39b9a4b0FAa8BB',
                'fee_percentage': Decimal('0.2500'),
                'is_active': False,  # Not prioritized in MVP
            },
            
            # Arbitrum DEXes (inactive for MVP)
            {
                'name': 'Uniswap V3',
                'chain_id': 42161,
                'router_address': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
                'factory_address': '0x1F98431c8aD98523631AE4a59f267346ea31F984',
                'fee_percentage': Decimal('0.3000'),
                'is_active': False,
            },
        ]
    
    def _log_info(self, message: str) -> None:
        """Log info message based on verbosity."""
        if self.verbosity >= 1:
            self.stdout.write(message)
        logger.info(message)
    
    def _log_success(self, message: str) -> None:
        """Log success message."""
        if self.verbosity >= 1:
            self.stdout.write(self.style.SUCCESS(message))
        logger.info(message)