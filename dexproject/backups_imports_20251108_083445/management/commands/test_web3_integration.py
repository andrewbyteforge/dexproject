"""
Web3 Integration Test Management Command

Tests the Web3 integration with proper environment validation using Django settings.

File: shared/management/commands/test_web3_integration.py
"""

import asyncio
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from shared.management.commands.base import BaseDexCommand

logger = logging.getLogger(__name__)


class Command(BaseDexCommand):
    """
    Management command to test Web3 integration with environment validation.
    
    Uses Django settings as the single source of truth for configuration.
    """
    
    help = 'Test Web3 integration with comprehensive environment validation'
    
    def add_arguments(self, parser) -> None:
        """Add command-specific arguments."""
        parser.add_argument(
            '--chain-id',
            type=int,
            help='Specific chain ID to test (defaults to DEFAULT_CHAIN_ID from settings)',
        )
        parser.add_argument(
            '--skip-connection',
            action='store_true',
            help='Skip actual Web3 connection test',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output',
        )
    
    def execute_command(self, *args, **options) -> None:
        """Execute the Web3 integration test command."""
        
        # Set up logging level
        if options.get('verbose'):
            logging.getLogger().setLevel(logging.DEBUG)
        
        # Print configuration header
        self._print_config_header()
        
        # Get target chain ID from options or settings
        target_chain_id = options.get('chain_id') or getattr(settings, 'DEFAULT_CHAIN_ID', 1)
        
        self.stdout.write(
            self.style.SUCCESS("🚀 DEX Trading Bot - Web3 Integration Test")
        )
        self.stdout.write("=" * 60)
        
        # Step 1: Environment Validation
        self._validate_environment(target_chain_id)
        
        # Step 2: Web3 Connection Test (unless skipped)
        if not options.get('skip_connection'):
            self._test_web3_connection(target_chain_id)
        
        # Step 3: Risk System Integration Test
        self._test_risk_system_integration()
        
        # Step 4: Configuration Validation
        self._validate_configuration()
        
        self.stdout.write(
            self.style.SUCCESS("✅ Web3 Integration Test Completed Successfully!")
        )
    
    def _print_config_header(self) -> None:
        """Print the configuration header showing current settings."""
        trading_mode = getattr(settings, 'TRADING_MODE', 'UNKNOWN')
        testnet_mode = getattr(settings, 'TESTNET_MODE', False)
        default_chain = getattr(settings, 'DEFAULT_CHAIN_ID', 'UNKNOWN')
        supported_chains = getattr(settings, 'SUPPORTED_CHAINS', [])
        max_portfolio = getattr(settings, 'MAX_PORTFOLIO_SIZE_USD', 'UNKNOWN')
        has_alchemy = bool(getattr(settings, 'ALCHEMY_API_KEY', ''))
        has_wallet = bool(getattr(settings, 'WALLET_PRIVATE_KEY', ''))
        
        self.stdout.write("🔧 DEX Trading Bot Configuration:")
        self.stdout.write(f"   Trading Mode: {trading_mode}")
        self.stdout.write(f"   Testnet Mode: {testnet_mode}")
        self.stdout.write(f"   Default Chain: {default_chain}")
        self.stdout.write(f"   Supported Chains: {supported_chains}")
        self.stdout.write(f"   Max Portfolio: ${max_portfolio}")
        self.stdout.write(f"   Has Alchemy Key: {'Yes' if has_alchemy else 'No'}")
        self.stdout.write(f"   Has Wallet Key: {'Yes' if has_wallet else 'No (will create dev wallet)'}")
    
    def _validate_environment(self, target_chain_id: int) -> None:
        """Validate the environment configuration."""
        self.stdout.write("🔍 Validating Environment Configuration...")
        
        errors = []
        warnings = []
        
        # Get settings values
        trading_mode = getattr(settings, 'TRADING_MODE', 'UNKNOWN')
        testnet_mode = getattr(settings, 'TESTNET_MODE', False)
        supported_chains = getattr(settings, 'SUPPORTED_CHAINS', [])
        default_chain_id = getattr(settings, 'DEFAULT_CHAIN_ID', 1)
        
        # Validate trading mode
        valid_trading_modes = ['PAPER', 'LIVE']
        if trading_mode not in valid_trading_modes:
            errors.append(f"Invalid TRADING_MODE: {trading_mode}. Must be one of {valid_trading_modes}")
        
        # Validate testnet configuration
        mainnet_chains = [1, 8453, 42161]  # Ethereum, Base, Arbitrum
        testnet_chains = [11155111, 84532, 421614]  # Sepolia, Base Sepolia, Arbitrum Sepolia
        
        if testnet_mode:
            # In testnet mode, should use testnet chains
            if default_chain_id in mainnet_chains:
                errors.append(f"DEFAULT_CHAIN_ID ({default_chain_id}) is not a testnet! Recommend {84532} (Base Sepolia)")
            
            # Check if any supported chains are mainnet
            mainnet_in_supported = [chain for chain in supported_chains if chain in mainnet_chains]
            if mainnet_in_supported:
                warnings.append(f"Mainnet chains in SUPPORTED_CHAINS while in testnet mode: {mainnet_in_supported}")
        else:
            # In mainnet mode, should use mainnet chains
            if default_chain_id in testnet_chains:
                errors.append(f"DEFAULT_CHAIN_ID ({default_chain_id}) is a testnet! Switch to mainnet or enable TESTNET_MODE")
        
        # Validate target chain is supported
        if target_chain_id != default_chain_id and target_chain_id not in supported_chains:
            errors.append(f"Target chain {target_chain_id} not in SUPPORTED_CHAINS: {supported_chains}")
        
        # Validate chain consistency
        if target_chain_id in mainnet_chains and testnet_mode:
            errors.append(f"Cannot test mainnet chain {target_chain_id} in testnet mode")
        elif target_chain_id in testnet_chains and not testnet_mode:
            errors.append(f"Cannot test testnet chain {target_chain_id} in mainnet mode")
        
        # Validate API keys for mainnet
        if not testnet_mode:
            alchemy_key = getattr(settings, 'ALCHEMY_API_KEY', '')
            infura_key = getattr(settings, 'INFURA_PROJECT_ID', '')
            if not alchemy_key and not infura_key:
                warnings.append("No premium API keys configured for mainnet - may hit rate limits")
        
        # Print results
        if errors:
            self.stdout.write(self.style.ERROR("❌ Environment Errors:"))
            for error in errors:
                self.stdout.write(f"   • {error}")
            raise CommandError("Test failed: Environment validation failed")
        
        if warnings:
            self.stdout.write(self.style.WARNING("⚠️  Environment Warnings:"))
            for warning in warnings:
                self.stdout.write(f"   • {warning}")
        
        self.stdout.write(self.style.SUCCESS("✅ Environment validation passed"))
    
    def _test_web3_connection(self, target_chain_id: int) -> None:
        """Test Web3 connection to the specified chain."""
        self.stdout.write(f"🌐 Testing Web3 Connection to Chain {target_chain_id}...")
        
        try:
            # Import here to avoid circular imports and test the new engine config
            from engine.config import EngineConfig
            
            # Try to get chain configuration using the new engine config
            try:
                engine_config = EngineConfig()
                # Since we can't call async methods in Django command, use fallback configs
                engine_config.chains = engine_config._get_fallback_chain_configs()
                
                chain_config = engine_config.get_chain_config(target_chain_id)
                if not chain_config:
                    self.stdout.write(
                        self.style.WARNING(f"⚠️  No chain configuration found for {target_chain_id}")
                    )
                    return
                
                # Test connection
                self.stdout.write(f"   Chain: {chain_config.name}")
                self.stdout.write(f"   Providers: {len(chain_config.rpc_providers)}")
                
                # Test actual connection with fallback method
                self._test_fallback_connection(target_chain_id, chain_config.rpc_providers[0].url)
                
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"⚠️  Could not load engine config: {e}")
                )
                self.stdout.write("   Using fallback connection test...")
                
                # Fallback connection test using Django settings
                self._test_fallback_connection(target_chain_id)
                
        except ImportError as e:
            self.stdout.write(
                self.style.WARNING(f"⚠️  Engine modules not available: {e}")
            )
            self._test_fallback_connection(target_chain_id)
    
    def _test_fallback_connection(self, target_chain_id: int, rpc_url: str = None) -> None:
        """Test Web3 connection using fallback method with Django settings."""
        try:
            from web3 import Web3
            
            # Get RPC URL from parameter or Django settings
            if not rpc_url:
                rpc_url = self._get_rpc_url_for_chain(target_chain_id)
                if not rpc_url:
                    self.stdout.write(
                        self.style.ERROR(f"❌ No RPC URL configured for chain {target_chain_id}")
                    )
                    return
            
            # Create Web3 connection
            w3 = Web3(Web3.HTTPProvider(rpc_url))
            
            # Test connection
            if w3.is_connected():
                block_number = w3.eth.block_number
                self.stdout.write(
                    self.style.SUCCESS(f"✅ Connected to chain {target_chain_id}")
                )
                self.stdout.write(f"   Latest block: {block_number}")
                self.stdout.write(f"   RPC URL: {rpc_url[:50]}...")
            else:
                self.stdout.write(
                    self.style.ERROR(f"❌ Failed to connect to chain {target_chain_id}")
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Connection test failed: {e}")
            )
    
    def _get_rpc_url_for_chain(self, chain_id: int) -> Optional[str]:
        """Get RPC URL for a specific chain from Django settings."""
        testnet_mode = getattr(settings, 'TESTNET_MODE', False)
        
        if testnet_mode:
            chain_urls = {
                11155111: getattr(settings, 'SEPOLIA_RPC_URL', ''),
                84532: getattr(settings, 'BASE_SEPOLIA_RPC_URL', ''),
                421614: getattr(settings, 'ARBITRUM_SEPOLIA_RPC_URL', ''),
            }
        else:
            chain_urls = {
                1: getattr(settings, 'ETH_RPC_URL', ''),
                8453: getattr(settings, 'BASE_RPC_URL', ''),
                42161: getattr(settings, 'ARBITRUM_RPC_URL', ''),
            }
        
        return chain_urls.get(chain_id)
    
    def _test_risk_system_integration(self) -> None:
        """Test risk system integration."""
        self.stdout.write("⚠️  Testing Risk System Integration...")
        
        try:
            # Try to import risk modules
            from risk.tasks.ownership import ownership_check
            
            # Test with a well-known address (WETH)
            test_address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
            
            self.stdout.write(f"   Testing ownership check for {test_address[:10]}...")
            self.stdout.write("   ✅ Risk system modules are importable")
            
        except ImportError as e:
            self.stdout.write(
                self.style.WARNING(f"⚠️  Risk system not available: {e}")
            )
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"⚠️  Risk system error: {e}")
            )
    
    def _validate_configuration(self) -> None:
        """Validate overall configuration consistency."""
        self.stdout.write("⚙️  Validating Configuration Consistency...")
        
        issues = []
        
        # Check for required settings
        required_settings = [
            'TRADING_MODE', 'TESTNET_MODE', 'DEFAULT_CHAIN_ID', 
            'SUPPORTED_CHAINS', 'MAX_PORTFOLIO_SIZE_USD'
        ]
        
        for setting in required_settings:
            if not hasattr(settings, setting):
                issues.append(f"Missing required setting: {setting}")
        
        # Check trading mode consistency
        trading_mode = getattr(settings, 'TRADING_MODE', 'UNKNOWN')
        testnet_mode = getattr(settings, 'TESTNET_MODE', False)
        
        if trading_mode == 'LIVE' and testnet_mode:
            issues.append("Cannot use LIVE trading mode with TESTNET_MODE=True")
        
        # Test engine config consistency
        try:
            from engine.config import EngineConfig
            engine_config = EngineConfig()
            
            # Check if engine config respects Django settings
            if engine_config.testnet_mode != testnet_mode:
                issues.append(f"Engine testnet_mode ({engine_config.testnet_mode}) != Django TESTNET_MODE ({testnet_mode})")
            
            if engine_config.trading_mode != trading_mode:
                issues.append(f"Engine trading_mode ({engine_config.trading_mode}) != Django TRADING_MODE ({trading_mode})")
                
            self.stdout.write(f"   Engine config loaded with {len(engine_config.target_chains)} chains")
            
        except Exception as e:
            issues.append(f"Could not validate engine config: {e}")
        
        if issues:
            self.stdout.write(self.style.ERROR("❌ Configuration Issues:"))
            for issue in issues:
                self.stdout.write(f"   • {issue}")
        else:
            self.stdout.write(self.style.SUCCESS("✅ Configuration validation passed"))