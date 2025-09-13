"""
Django management command to populate initial chains and DEXes data.

This command creates the foundational blockchain networks and decentralized
exchanges needed for the DEX auto-trading bot to operate.

File: trading/management/commands/populate_chains_and_dexes.py
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings

from trading.models import Chain, DEX

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
        parser.add_argument(
            '--testnet',
            action='store_true',
            help='Use testnet configurations instead of mainnet',
        )
    
    def handle(self, *args, **options) -> None:
        """Execute the command."""
        self.verbosity = options.get('verbosity', 1)
        force = options.get('force', False)
        chains_only = options.get('chains_only', False)
        dexes_only = options.get('dexes_only', False)
        use_testnet = options.get('testnet', getattr(settings, 'TESTNET_MODE', True))
        
        # Show configuration header
        self._print_config_header(use_testnet)
        
        try:
            with transaction.atomic():
                if force:
                    self._clear_existing_data()
                
                if not dexes_only:
                    chains_created = self._create_chains(use_testnet)
                    self._log_success(f"Created {chains_created} chains")
                
                if not chains_only:
                    dexes_created = self._create_dexes(use_testnet)
                    self._log_success(f"Created {dexes_created} DEXes")
                
                self._log_success("Initial data population completed successfully!")
                
        except Exception as e:
            logger.error(f"Failed to populate initial data: {e}")
            self._log_error(f"Command failed: {e}")
            raise CommandError(f"Command failed: {e}")
    
    def _print_config_header(self, use_testnet: bool) -> None:
        """Print configuration header."""
        self.stdout.write("=" * 80)
        self.stdout.write("POPULATE CHAINS AND DEXES COMMAND")
        self.stdout.write("=" * 80)
        
        network_type = "TESTNET" if use_testnet else "MAINNET"
        self.stdout.write(f"Network Type: {network_type}")
        self.stdout.write(f"Force Mode: {self.verbosity >= 2}")
        self.stdout.write("")
    
    def _clear_existing_data(self) -> None:
        """Clear existing chains and DEXes if force flag is used."""
        self._log_info("Clearing existing chains and DEXes...")
        
        dex_count = DEX.objects.count()
        chain_count = Chain.objects.count()
        
        DEX.objects.all().delete()
        Chain.objects.all().delete()
        
        self._log_info(f"Deleted {dex_count} DEXes and {chain_count} chains")
    
    def _create_chains(self, use_testnet: bool = True) -> int:
        """Create blockchain networks."""
        self._log_info("Creating blockchain networks...")
        
        chains_data = self._get_chains_data(use_testnet)
        chains_created = 0
        
        for chain_data in chains_data:
            # Filter to only include fields that exist in the Django model
            filtered_data = {
                'name': chain_data['name'],
                'chain_id': chain_data['chain_id'],
                'rpc_url': chain_data['rpc_url'],
                'fallback_rpc_urls': chain_data.get('fallback_rpc_urls', []),
                'block_time_seconds': chain_data.get('block_time_seconds', 12),
                'gas_price_gwei': chain_data.get('gas_price_gwei', Decimal('20.0')),
                'max_gas_price_gwei': chain_data.get('max_gas_price_gwei', Decimal('100.0')),
                'is_active': chain_data.get('is_active', True),
            }
            
            chain, created = Chain.objects.get_or_create(
                chain_id=chain_data['chain_id'],
                defaults=filtered_data
            )
            
            if created:
                chains_created += 1
                self._log_info(f"Created chain: {chain.name} (ID: {chain.chain_id})")
            else:
                self._log_info(f"Chain already exists: {chain.name}")
        
        return chains_created
    
    def _create_dexes(self, use_testnet: bool = True) -> int:
        """Create decentralized exchanges."""
        self._log_info("Creating decentralized exchanges...")
        
        dexes_data = self._get_dexes_data(use_testnet)
        dexes_created = 0
        
        for dex_data in dexes_data:
            try:
                # Get the chain for this DEX
                chain = Chain.objects.get(chain_id=dex_data['chain_id'])
                
                # Filter to only include fields that exist in the Django DEX model
                filtered_dex_data = {
                    'name': dex_data['name'],
                    'chain': chain,
                    'router_address': dex_data['router_address'],
                    'factory_address': dex_data['factory_address'],
                    'fee_percentage': dex_data.get('fee_percentage', Decimal('0.3000')),
                    'is_active': dex_data.get('is_active', True),
                }
                
                dex, created = DEX.objects.get_or_create(
                    name=dex_data['name'],
                    chain=chain,
                    defaults=filtered_dex_data
                )
                
                if created:
                    dexes_created += 1
                    self._log_info(f"Created DEX: {dex.name} on {chain.name}")
                else:
                    self._log_info(f"DEX already exists: {dex.name} on {chain.name}")
                    
            except Chain.DoesNotExist:
                self._log_warning(f"Chain with ID {dex_data['chain_id']} not found, skipping DEX {dex_data['name']}")
                continue
            except Exception as e:
                self._log_error(f"Failed to create DEX {dex_data['name']}: {e}")
                continue
        
        return dexes_created
    
    def _get_chains_data(self, use_testnet: bool = True) -> List[Dict[str, Any]]:
        """Get chain configuration data."""
        if use_testnet:
            return [
                {
                    'name': 'Ethereum Sepolia',
                    'chain_id': 11155111,
                    'rpc_url': f"https://eth-sepolia.g.alchemy.com/v2/{getattr(settings, 'ALCHEMY_API_KEY', 'demo')}",
                    'fallback_rpc_urls': [
                        'https://sepolia.infura.io/v3/demo',
                        'https://ethereum-sepolia.publicnode.com',
                        'https://rpc.ankr.com/eth_sepolia'
                    ],
                    'block_time_seconds': 12,
                    'gas_price_gwei': Decimal('1.0'),
                    'max_gas_price_gwei': Decimal('10.0'),
                    'is_active': True,
                },
                {
                    'name': 'Base Sepolia',
                    'chain_id': 84532,
                    'rpc_url': f"https://base-sepolia.g.alchemy.com/v2/{getattr(settings, 'BASE_ALCHEMY_API_KEY', getattr(settings, 'ALCHEMY_API_KEY', 'demo'))}",
                    'fallback_rpc_urls': [
                        'https://sepolia.base.org',
                        'https://base-sepolia.publicnode.com',
                        'https://rpc.ankr.com/base_sepolia'
                    ],
                    'block_time_seconds': 2,
                    'gas_price_gwei': Decimal('0.001'),
                    'max_gas_price_gwei': Decimal('1.0'),
                    'is_active': True,
                },
                {
                    'name': 'Arbitrum Sepolia',
                    'chain_id': 421614,
                    'rpc_url': f"https://arb-sepolia.g.alchemy.com/v2/{getattr(settings, 'ALCHEMY_API_KEY', 'demo')}",
                    'fallback_rpc_urls': [
                        'https://sepolia-rollup.arbitrum.io/rpc',
                        'https://arbitrum-sepolia.publicnode.com',
                        'https://rpc.ankr.com/arbitrum_sepolia'
                    ],
                    'block_time_seconds': 1,
                    'gas_price_gwei': Decimal('0.001'),
                    'max_gas_price_gwei': Decimal('0.5'),
                    'is_active': False,  # Not enabled in MVP
                },
            ]
        else:
            # Mainnet configurations
            return [
                {
                    'name': 'Ethereum',
                    'chain_id': 1,
                    'rpc_url': f"https://eth-mainnet.g.alchemy.com/v2/{getattr(settings, 'ALCHEMY_API_KEY', 'demo')}",
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
                    'rpc_url': f"https://base-mainnet.g.alchemy.com/v2/{getattr(settings, 'BASE_ALCHEMY_API_KEY', getattr(settings, 'ALCHEMY_API_KEY', 'demo'))}",
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
            ]
    
    def _get_dexes_data(self, use_testnet: bool = True) -> List[Dict[str, Any]]:
        """Get DEX configuration data."""
        if use_testnet:
            return [
                # Ethereum Sepolia DEXes
                {
                    'name': 'Uniswap V2',
                    'chain_id': 11155111,
                    'router_address': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
                    'factory_address': '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',
                    'fee_percentage': Decimal('0.3000'),
                    'is_active': True,
                },
                {
                    'name': 'Uniswap V3',
                    'chain_id': 11155111,
                    'router_address': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
                    'factory_address': '0x1F98431c8aD98523631AE4a59f267346ea31F984',
                    'fee_percentage': Decimal('0.3000'),
                    'is_active': True,
                },
                # Base Sepolia DEXes
                {
                    'name': 'Uniswap V2',
                    'chain_id': 84532,
                    'router_address': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
                    'factory_address': '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',
                    'fee_percentage': Decimal('0.3000'),
                    'is_active': True,
                },
                {
                    'name': 'Uniswap V3',
                    'chain_id': 84532,
                    'router_address': '0x2626664c2603336E57B271c5C0b26F421741e481',
                    'factory_address': '0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24',
                    'fee_percentage': Decimal('0.3000'),
                    'is_active': True,
                },
                # Arbitrum Sepolia DEXes (disabled)
                {
                    'name': 'Uniswap V2',
                    'chain_id': 421614,
                    'router_address': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
                    'factory_address': '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',
                    'fee_percentage': Decimal('0.3000'),
                    'is_active': False,
                },
            ]
        else:
            # Mainnet DEXes
            return [
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
                    'fee_percentage': Decimal('0.3000'),
                    'is_active': True,
                },
                {
                    'name': 'Uniswap V3',
                    'chain_id': 8453,
                    'router_address': '0x2626664c2603336E57B271c5C0b26F421741e481',
                    'factory_address': '0x33128a8fC17869897dcE68Ed026d694621f6FDfD',
                    'fee_percentage': Decimal('0.3000'),
                    'is_active': True,
                },
            ]
    
    def _log_info(self, message: str) -> None:
        """Log info message."""
        if self.verbosity >= 1:
            self.stdout.write(f"  {message}")
        logger.info(message)
    
    def _log_success(self, message: str) -> None:
        """Log success message."""
        if self.verbosity >= 1:
            self.stdout.write(self.style.SUCCESS(f"✓ {message}"))
        logger.info(message)
    
    def _log_warning(self, message: str) -> None:
        """Log warning message."""
        if self.verbosity >= 1:
            self.stdout.write(self.style.WARNING(f"⚠ {message}"))
        logger.warning(message)
    
    def _log_error(self, message: str) -> None:
        """Log error message."""
        if self.verbosity >= 1:
            self.stdout.write(self.style.ERROR(f"✗ {message}"))
        logger.error(message)