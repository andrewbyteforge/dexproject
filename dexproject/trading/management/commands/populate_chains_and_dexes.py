"""
Complete Django management command to populate chains and DEXes.

This command creates comprehensive database records for testnet trading
with proper error handling, validation, and RPC provider management.

Path: trading/management/commands/populate_chains_and_dexes.py
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from trading.models import Chain, DEX
from decimal import Decimal
import os
import requests
import logging
from typing import Dict, List, Any, Optional


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command to populate chains and DEXes with comprehensive testnet configuration.
    
    Features:
    - Creates testnet chain configurations using real API keys
    - Sets up multiple RPC providers with failover
    - Configures DEX contracts for each supported chain
    - Validates RPC endpoints before saving
    - Handles updates and duplicates properly
    - Comprehensive error handling and logging
    """
    
    help = 'Populate database with comprehensive testnet chain and DEX configurations'
    
    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            '--force-update',
            action='store_true',
            help='Force update existing records, overwriting current data'
        )
        
        parser.add_argument(
            '--validate-rpc',
            action='store_true',
            help='Validate RPC endpoints before saving (slower but more reliable)'
        )
        
        parser.add_argument(
            '--chains',
            nargs='+',
            type=int,
            help='Specific chain IDs to populate (default: all testnet chains)',
            default=[84532, 11155111, 421614]
        )
        
        parser.add_argument(
            '--skip-dexes',
            action='store_true',
            help='Skip DEX configuration creation'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating records'
        )
    
    def handle(self, *args, **options):
        """Execute the command with comprehensive error handling."""
        self.verbosity = options['verbosity']
        self.force_update = options['force_update']
        self.validate_rpc = options['validate_rpc']
        self.target_chains = options['chains']
        self.skip_dexes = options['skip_dexes']
        self.dry_run = options['dry_run']
        
        # Display configuration
        self.log_info("=" * 80)
        self.log_info("POPULATE CHAINS AND DEXES COMMAND")
        self.log_info("=" * 80)
        self.log_info(f"Target chains: {self.target_chains}")
        self.log_info(f"Force update: {self.force_update}")
        self.log_info(f"Validate RPC: {self.validate_rpc}")
        self.log_info(f"Skip DEXes: {self.skip_dexes}")
        self.log_info(f"Dry run: {self.dry_run}")
        
        if self.dry_run:
            self.log_warning("DRY RUN MODE - No changes will be made")
        
        # Get API keys and validate
        api_keys = self.get_api_keys()
        self.validate_api_keys(api_keys)
        
        try:
            with transaction.atomic():
                if self.dry_run:
                    # Use savepoint for dry run to rollback changes
                    savepoint = transaction.savepoint()
                
                # Create chain configurations
                chains_result = self.create_chain_configurations(api_keys)
                
                # Create DEX configurations
                dexes_result = {}
                if not self.skip_dexes:
                    dexes_result = self.create_dex_configurations()
                
                if self.dry_run:
                    # Rollback changes in dry run
                    transaction.savepoint_rollback(savepoint)
                    self.log_info("\nDRY RUN COMPLETED - No actual changes made")
                else:
                    # Commit changes
                    self.log_success("Transaction completed successfully")
                
                # Display summary
                self.display_summary(chains_result, dexes_result)
                
        except Exception as e:
            self.log_error(f"Command failed: {str(e)}")
            if self.verbosity >= 2:
                import traceback
                self.log_error(traceback.format_exc())
            raise CommandError(f"Failed to populate chains and DEXes: {str(e)}")
    
    def get_api_keys(self) -> Dict[str, str]:
        """Get API keys from environment variables."""
        api_keys = {
            'alchemy': os.getenv('ALCHEMY_API_KEY', ''),
            'base_alchemy': os.getenv('BASE_ALCHEMY_API_KEY', ''),
            'ankr': os.getenv('ANKR_API_KEY', ''),
            'infura': os.getenv('INFURA_PROJECT_ID', ''),
        }
        
        # Use primary alchemy key as fallback for base
        if not api_keys['base_alchemy']:
            api_keys['base_alchemy'] = api_keys['alchemy']
        
        return api_keys
    
    def validate_api_keys(self, api_keys: Dict[str, str]) -> None:
        """Validate that we have necessary API keys."""
        if not api_keys['alchemy']:
            self.log_warning("No ALCHEMY_API_KEY found - using demo key (limited functionality)")
            api_keys['alchemy'] = 'demo'
        
        if not api_keys['base_alchemy']:
            self.log_warning("No BASE_ALCHEMY_API_KEY found - using primary Alchemy key")
        
        # Log key status (masked for security)
        self.log_info("API Key Status:")
        for key_name, key_value in api_keys.items():
            if key_value:
                masked_key = key_value[:6] + '...' if len(key_value) > 6 else 'demo'
                self.log_info(f"  {key_name.upper()}: {masked_key}")
            else:
                self.log_warning(f"  {key_name.upper()}: Not set")
    
    def create_chain_configurations(self, api_keys: Dict[str, str]) -> Dict[int, str]:
        """Create comprehensive chain configurations."""
        self.log_info("\nCreating chain configurations...")
        results = {}
        
        chain_configs = {
            84532: self.get_base_sepolia_config(api_keys),
            11155111: self.get_ethereum_sepolia_config(api_keys),
            421614: self.get_arbitrum_sepolia_config(api_keys),
        }
        
        for chain_id in self.target_chains:
            if chain_id not in chain_configs:
                self.log_warning(f"No configuration available for chain ID {chain_id}")
                continue
            
            config = chain_configs[chain_id]
            result = self.create_single_chain(chain_id, config)
            results[chain_id] = result
        
        return results
    
    def get_base_sepolia_config(self, api_keys: Dict[str, str]) -> Dict[str, Any]:
        """Get Base Sepolia chain configuration."""
        return {
            'name': 'Base Sepolia',
            'native_currency': 'ETH',
            'block_time_seconds': 2,
            'gas_price_gwei': Decimal('1.0'),
            'max_gas_price_gwei': Decimal('10.0'),
            'explorer_url': 'https://sepolia.basescan.org',
            'is_testnet': True,
            'is_active': True,
            'rpc_providers': [
                {
                    'name': 'base_alchemy_primary',
                    'url': f"https://base-sepolia.g.alchemy.com/v2/{api_keys['base_alchemy']}",
                    'websocket_url': f"wss://base-sepolia.g.alchemy.com/v2/{api_keys['base_alchemy']}",
                    'is_paid': True,
                    'priority': 1,
                    'timeout_seconds': 30,
                    'max_requests_per_second': 100,
                },
                {
                    'name': 'base_public_fallback',
                    'url': 'https://sepolia.base.org',
                    'websocket_url': None,
                    'is_paid': False,
                    'priority': 2,
                    'timeout_seconds': 30,
                    'max_requests_per_second': 10,
                },
                {
                    'name': 'base_blockpi_fallback',
                    'url': 'https://base-sepolia.blockpi.network/v1/rpc/public',
                    'websocket_url': None,
                    'is_paid': False,
                    'priority': 3,
                    'timeout_seconds': 30,
                    'max_requests_per_second': 5,
                }
            ]
        }
    
    def get_ethereum_sepolia_config(self, api_keys: Dict[str, str]) -> Dict[str, Any]:
        """Get Ethereum Sepolia chain configuration."""
        rpc_providers = [
            {
                'name': 'ethereum_alchemy_primary',
                'url': f"https://eth-sepolia.g.alchemy.com/v2/{api_keys['alchemy']}",
                'websocket_url': f"wss://eth-sepolia.g.alchemy.com/v2/{api_keys['alchemy']}",
                'is_paid': True,
                'priority': 1,
                'timeout_seconds': 30,
                'max_requests_per_second': 100,
            },
            {
                'name': 'ethereum_public_fallback',
                'url': 'https://rpc.sepolia.org',
                'websocket_url': None,
                'is_paid': False,
                'priority': 2,
                'timeout_seconds': 30,
                'max_requests_per_second': 10,
            },
            {
                'name': 'ethereum_blockpi_fallback',
                'url': 'https://sepolia.blockpi.network/v1/rpc/public',
                'websocket_url': None,
                'is_paid': False,
                'priority': 3,
                'timeout_seconds': 30,
                'max_requests_per_second': 5,
            }
        ]
        
        # Add Infura if available
        if api_keys['infura']:
            rpc_providers.insert(1, {
                'name': 'ethereum_infura_secondary',
                'url': f"https://sepolia.infura.io/v3/{api_keys['infura']}",
                'websocket_url': f"wss://sepolia.infura.io/ws/v3/{api_keys['infura']}",
                'is_paid': True,
                'priority': 2,
                'timeout_seconds': 30,
                'max_requests_per_second': 100,
            })
            # Adjust priorities
            for provider in rpc_providers[2:]:
                provider['priority'] += 1
        
        return {
            'name': 'Ethereum Sepolia',
            'native_currency': 'ETH',
            'block_time_seconds': 12,
            'gas_price_gwei': Decimal('10.0'),
            'max_gas_price_gwei': Decimal('50.0'),
            'explorer_url': 'https://sepolia.etherscan.io',
            'is_testnet': True,
            'is_active': True,
            'rpc_providers': rpc_providers
        }
    
    def get_arbitrum_sepolia_config(self, api_keys: Dict[str, str]) -> Dict[str, Any]:
        """Get Arbitrum Sepolia chain configuration."""
        return {
            'name': 'Arbitrum Sepolia',
            'native_currency': 'ETH',
            'block_time_seconds': 1,
            'gas_price_gwei': Decimal('0.1'),
            'max_gas_price_gwei': Decimal('5.0'),
            'explorer_url': 'https://sepolia.arbiscan.io',
            'is_testnet': True,
            'is_active': True,
            'rpc_providers': [
                {
                    'name': 'arbitrum_official_primary',
                    'url': 'https://sepolia-rollup.arbitrum.io/rpc',
                    'websocket_url': 'wss://sepolia-rollup.arbitrum.io/ws',
                    'is_paid': False,
                    'priority': 1,
                    'timeout_seconds': 30,
                    'max_requests_per_second': 50,
                },
                {
                    'name': 'arbitrum_blockpi_fallback',
                    'url': 'https://arbitrum-sepolia.blockpi.network/v1/rpc/public',
                    'websocket_url': None,
                    'is_paid': False,
                    'priority': 2,
                    'timeout_seconds': 30,
                    'max_requests_per_second': 5,
                }
            ]
        }
    
    def create_single_chain(self, chain_id: int, config: Dict[str, Any]) -> str:
        """Create a single chain configuration with RPC providers."""
        chain_name = config['name']
        
        try:
            # Prepare chain data
            chain_data = {
                'name': config['name'],
                'native_currency': config['native_currency'],
                'block_time_seconds': config['block_time_seconds'],
                'gas_price_gwei': config['gas_price_gwei'],
                'max_gas_price_gwei': config['max_gas_price_gwei'],
                'explorer_url': config['explorer_url'],
                'is_testnet': config['is_testnet'],
                'is_active': config['is_active'],
                'created_at': timezone.now(),
                'updated_at': timezone.now(),
            }
            
            # Set primary RPC URL (first provider)
            primary_provider = config['rpc_providers'][0]
            chain_data['rpc_url'] = primary_provider['url']
            
            # Set fallback URLs
            fallback_urls = [p['url'] for p in config['rpc_providers'][1:]]
            chain_data['fallback_rpc_urls'] = fallback_urls
            
            # Create or update chain
            if self.force_update:
                chain, created = Chain.objects.update_or_create(
                    chain_id=chain_id,
                    defaults=chain_data
                )
            else:
                chain, created = Chain.objects.get_or_create(
                    chain_id=chain_id,
                    defaults=chain_data
                )
            
            action = "Created" if created else "Updated" if self.force_update else "Found existing"
            self.log_info(f"  {action}: {chain_name} ({chain_id})")
            
            # Create RPC providers
            if created or self.force_update:
                self.create_rpc_providers(chain, config['rpc_providers'])
            
            return action.lower()
            
        except Exception as e:
            self.log_error(f"Failed to create chain {chain_name}: {str(e)}")
            raise
    
    def create_rpc_providers(self, chain: Chain, providers_config: List[Dict[str, Any]]) -> None:
        """Create RPC provider configurations for a chain."""
        if self.force_update:
            # Clear existing providers if force update
            chain.rpc_providers.all().delete()
        
        for provider_config in providers_config:
            try:
                # Validate RPC endpoint if requested
                if self.validate_rpc:
                    is_valid = self.validate_rpc_endpoint(provider_config['url'])
                    if not is_valid:
                        self.log_warning(f"    RPC validation failed for {provider_config['name']}, creating anyway")
                
                # Create RPC provider
                rpc_provider_data = {
                    'name': provider_config['name'],
                    'url': provider_config['url'],
                    'websocket_url': provider_config.get('websocket_url'),
                    'is_paid': provider_config['is_paid'],
                    'priority': provider_config['priority'],
                    'timeout_seconds': provider_config['timeout_seconds'],
                    'max_requests_per_second': provider_config['max_requests_per_second'],
                    'is_active': True,
                    'chain': chain,
                }
                
                rpc_provider, created = RPCProvider.objects.get_or_create(
                    chain=chain,
                    name=provider_config['name'],
                    defaults=rpc_provider_data
                )
                
                status = "Created" if created else "Found"
                priority = provider_config['priority']
                self.log_info(f"    {status} RPC provider: {provider_config['name']} (Priority: {priority})")
                
            except Exception as e:
                self.log_error(f"    Failed to create RPC provider {provider_config['name']}: {str(e)}")
                continue
    
    def validate_rpc_endpoint(self, url: str, timeout: int = 10) -> bool:
        """Validate an RPC endpoint by making a test request."""
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "eth_blockNumber",
                "params": [],
                "id": 1
            }
            
            response = requests.post(
                url,
                json=payload,
                timeout=timeout,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                result = response.json()
                return 'result' in result
            
            return False
            
        except Exception:
            return False
    
    def create_dex_configurations(self) -> Dict[str, str]:
        """Create DEX configurations for all chains."""
        self.log_info("\nCreating DEX configurations...")
        results = {}
        
        dex_configs = {
            84532: self.get_base_sepolia_dex_config(),
            11155111: self.get_ethereum_sepolia_dex_config(),
            421614: self.get_arbitrum_sepolia_dex_config(),
        }
        
        for chain_id in self.target_chains:
            if chain_id not in dex_configs:
                continue
            
            try:
                chain = Chain.objects.get(chain_id=chain_id)
                config = dex_configs[chain_id]
                result = self.create_chain_dexes(chain, config)
                results[f"{chain.name}_dexes"] = result
            except Chain.DoesNotExist:
                self.log_warning(f"Chain {chain_id} not found, skipping DEX creation")
                continue
        
        return results
    
    def get_base_sepolia_dex_config(self) -> List[Dict[str, Any]]:
        """Get Base Sepolia DEX configurations."""
        return [
            {
                'name': 'Uniswap V3',
                'protocol_version': 'v3',
                'factory_address': '0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24',
                'router_address': '0x2626664c2603336E57B271c5C0b26F421741e481',
                'quoter_address': '0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a',
                'is_active': True,
                'fee_tiers': [100, 500, 3000, 10000],
                'supports_exact_output': True,
                'supports_multi_hop': True,
            }
        ]
    
    def get_ethereum_sepolia_dex_config(self) -> List[Dict[str, Any]]:
        """Get Ethereum Sepolia DEX configurations."""
        return [
            {
                'name': 'Uniswap V3',
                'protocol_version': 'v3',
                'factory_address': '0x1F98431c8aD98523631AE4a59f267346ea31F984',
                'router_address': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
                'quoter_address': '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6',
                'is_active': True,
                'fee_tiers': [100, 500, 3000, 10000],
                'supports_exact_output': True,
                'supports_multi_hop': True,
            },
            {
                'name': 'Uniswap V2',
                'protocol_version': 'v2',
                'factory_address': '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',
                'router_address': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
                'quoter_address': None,
                'is_active': True,
                'fee_tiers': [3000],  # 0.3% fixed fee
                'supports_exact_output': True,
                'supports_multi_hop': True,
            }
        ]
    
    def get_arbitrum_sepolia_dex_config(self) -> List[Dict[str, Any]]:
        """Get Arbitrum Sepolia DEX configurations."""
        return [
            {
                'name': 'Uniswap V3',
                'protocol_version': 'v3',
                'factory_address': '0x1F98431c8aD98523631AE4a59f267346ea31F984',
                'router_address': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
                'quoter_address': '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6',
                'is_active': True,
                'fee_tiers': [100, 500, 3000, 10000],
                'supports_exact_output': True,
                'supports_multi_hop': True,
            }
        ]
    
    def create_chain_dexes(self, chain: Chain, dex_configs: List[Dict[str, Any]]) -> str:
        """Create DEX configurations for a specific chain."""
        created_count = 0
        
        for dex_config in dex_configs:
            try:
                dex_data = {
                    'name': dex_config['name'],
                    'protocol_version': dex_config['protocol_version'],
                    'factory_address': dex_config['factory_address'],
                    'router_address': dex_config['router_address'],
                    'quoter_address': dex_config.get('quoter_address'),
                    'is_active': dex_config['is_active'],
                    'fee_tiers': dex_config['fee_tiers'],
                    'supports_exact_output': dex_config['supports_exact_output'],
                    'supports_multi_hop': dex_config['supports_multi_hop'],
                    'chain': chain,
                }
                
                if self.force_update:
                    dex, created = DEX.objects.update_or_create(
                        name=dex_config['name'],
                        chain=chain,
                        defaults=dex_data
                    )
                else:
                    dex, created = DEX.objects.get_or_create(
                        name=dex_config['name'],
                        chain=chain,
                        defaults=dex_data
                    )
                
                if created:
                    created_count += 1
                
                action = "Created" if created else "Updated" if self.force_update else "Found"
                protocol = dex_config['protocol_version'].upper()
                self.log_info(f"  {action}: {dex_config['name']} {protocol} on {chain.name}")
                
            except Exception as e:
                self.log_error(f"  Failed to create DEX {dex_config['name']} on {chain.name}: {str(e)}")
                continue
        
        return f"{created_count} created"
    
    def display_summary(self, chains_result: Dict[int, str], dexes_result: Dict[str, str]) -> None:
        """Display command execution summary."""
        self.log_info("\n" + "=" * 80)
        self.log_info("EXECUTION SUMMARY")
        self.log_info("=" * 80)
        
        # Chain summary
        self.log_info("Chains:")
        for chain_id, action in chains_result.items():
            try:
                chain = Chain.objects.get(chain_id=chain_id)
                provider_count = chain.rpc_providers.count()
                self.log_info(f"  {chain.name} ({chain_id}): {action} with {provider_count} RPC providers")
            except Chain.DoesNotExist:
                self.log_info(f"  Chain {chain_id}: {action} (not found)")
        
        # DEX summary
        if not self.skip_dexes and dexes_result:
            self.log_info("DEXes:")
            for chain_name, result in dexes_result.items():
                self.log_info(f"  {chain_name}: {result}")
        
        self.log_success("Command completed successfully!")
    
    def log_info(self, message: str) -> None:
        """Log info message with proper styling."""
        self.stdout.write(self.style.HTTP_INFO(message))
    
    def log_success(self, message: str) -> None:
        """Log success message with proper styling."""
        self.stdout.write(self.style.SUCCESS(message))
    
    def log_warning(self, message: str) -> None:
        """Log warning message with proper styling."""
        self.stdout.write(self.style.WARNING(message))
    
    def log_error(self, message: str) -> None:
        """Log error message with proper styling."""
        self.stdout.write(self.style.ERROR(message))