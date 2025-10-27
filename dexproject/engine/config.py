"""
Enhanced Engine Configuration Management - Django Models as SSOT

Uses Django Chain/DEX models as the single source of truth for chain configuration,
eliminating duplication and ensuring consistency across the system.

File: dexproject/engine/config.py
"""

import os
import logging
import asyncio
from typing import Dict, List, Optional, Any
from decimal import Decimal

# Import shared components for Django integration
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.chain_config_bridge import (
    ChainConfigBridge, ChainConfig, RPCProvider, 
    get_engine_chain_configs
)
from shared.redis_client import RedisClient

# Setup Django integration early
try:
    import django
    from django.conf import settings
    
    # Setup Django if not already configured
    if not settings.configured:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
        django.setup()
        
    DJANGO_AVAILABLE = True
    
except ImportError as e:
    logging.warning(f"Django not available for engine config: {e}")
    settings = None
    DJANGO_AVAILABLE = False
except Exception as e:
    logging.warning(f"Could not setup Django for engine config: {e}")
    settings = None
    DJANGO_AVAILABLE = False

logger = logging.getLogger(__name__)


class EngineConfig:
    """
    Enhanced configuration management for the trading engine.
    
    Now uses Django settings as the single source of truth for configuration,
    ensuring consistency between Django and engine components.
    """
    
    def __init__(self):
        """Initialize configuration from Django settings and environment variables."""
        self.logger = logger
        self._redis_client = None
        self._chain_config_bridge = None
        
        # Load engine-specific configuration first
        self.load_engine_config()
        
        # Initialize Django integration
        self._setup_django_integration()
        
        # Load chain configurations from Django
        self.chains = {}  # Will be populated asynchronously
        
        # Validate engine configuration
        self.validate_config()
        self._log_configuration_summary()
    
    def load_engine_config(self) -> None:
        """Load engine-specific configuration from Django settings and environment variables."""
        
        # Engine Core Settings - prioritize Django settings over environment
        if DJANGO_AVAILABLE and settings:
            self.trading_mode = getattr(settings, 'TRADING_MODE', os.getenv("TRADING_MODE", "PAPER")).upper()
            self.testnet_mode = getattr(settings, 'TESTNET_MODE', os.getenv('TESTNET_MODE', 'True').lower() == 'true')
        else:
            self.trading_mode = os.getenv("TRADING_MODE", "PAPER").upper()
            self.testnet_mode = os.getenv('TESTNET_MODE', 'True').lower() == 'true'
        
        self.engine_name = os.getenv("ENGINE_NAME", "dex-trading-engine")
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        
        # Target Chains - use Django settings as source of truth
        try:
            if DJANGO_AVAILABLE and settings and hasattr(settings, 'SUPPORTED_CHAINS'):
                supported_chains = getattr(settings, 'SUPPORTED_CHAINS', [])
                if supported_chains:
                    default_chains = ",".join(str(chain_id) for chain_id in supported_chains)
                else:
                    # Fall back to DEFAULT_CHAIN_ID
                    default_chains = str(getattr(settings, 'DEFAULT_CHAIN_ID', 84532 if self.testnet_mode else 8453))
            else:
                # Fallback based on testnet mode
                if self.testnet_mode:
                    default_chains = "11155111,84532,421614"  # Sepolia, Base Sepolia, Arbitrum Sepolia
                else:
                    default_chains = "1,8453,42161"  # Ethereum, Base, Arbitrum
                    
        except Exception as e:
            logger.warning(f"Could not access Django settings for chains: {e}")
            default_chains = "84532" if self.testnet_mode else "8453,1"
        
        chain_ids_str = os.getenv("TARGET_CHAINS", default_chains)
        self.target_chains = [int(cid.strip()) for cid in chain_ids_str.split(",")]
        
        # Discovery Settings
        self.discovery_enabled = os.getenv("DISCOVERY_ENABLED", "true").lower() == "true"
        self.websocket_timeout = int(os.getenv("WEBSOCKET_TIMEOUT", "30"))
        self.websocket_reconnect_delay = int(os.getenv("WEBSOCKET_RECONNECT_DELAY", "5"))
        self.http_poll_interval = int(os.getenv("HTTP_POLL_INTERVAL", "5"))
        self.max_pairs_per_hour = int(os.getenv("MAX_PAIRS_PER_HOUR", "100"))
        self.event_batch_size = int(os.getenv("EVENT_BATCH_SIZE", "50"))
        
        # Risk Assessment Settings - use Django settings where available
        if DJANGO_AVAILABLE and settings:
            self.risk_timeout = getattr(settings, 'RISK_TIMEOUT_SECONDS', int(os.getenv("RISK_TIMEOUT", "15")))
            self.risk_parallel_checks = getattr(settings, 'RISK_PARALLEL_CHECKS', int(os.getenv("RISK_PARALLEL_CHECKS", "4")))
        else:
            self.risk_timeout = int(os.getenv("RISK_TIMEOUT", "15"))
            self.risk_parallel_checks = int(os.getenv("RISK_PARALLEL_CHECKS", "4"))
            
        self.min_liquidity_usd = Decimal(os.getenv("MIN_LIQUIDITY_USD", "10000"))
        self.max_buy_tax_percent = Decimal(os.getenv("MAX_BUY_TAX_PERCENT", "5.0"))
        self.max_sell_tax_percent = Decimal(os.getenv("MAX_SELL_TAX_PERCENT", "5.0"))
        self.min_holder_count = int(os.getenv("MIN_HOLDER_COUNT", "50"))
        
        # Portfolio Management - use Django settings where available
        if DJANGO_AVAILABLE and settings:
            self.max_portfolio_size_usd = getattr(settings, 'MAX_PORTFOLIO_SIZE_USD', 
                                                Decimal(os.getenv("MAX_PORTFOLIO_SIZE_USD", "1000" if self.testnet_mode else "10000")))
            self.max_position_size_usd = getattr(settings, 'MAX_POSITION_SIZE_USD',
                                               Decimal(os.getenv("MAX_POSITION_SIZE_USD", "100" if self.testnet_mode else "1000")))
            self.daily_loss_limit_percent = getattr(settings, 'DAILY_LOSS_LIMIT_PERCENT',
                                                   Decimal(os.getenv("DAILY_LOSS_LIMIT_PERCENT", "50.0" if self.testnet_mode else "5.0")))
            self.circuit_breaker_loss_percent = getattr(settings, 'CIRCUIT_BREAKER_LOSS_PERCENT',
                                                       Decimal(os.getenv("CIRCUIT_BREAKER_LOSS_PERCENT", "75.0" if self.testnet_mode else "10.0")))
        else:
            testnet_portfolio = "1000" if self.testnet_mode else "10000"
            testnet_position = "100" if self.testnet_mode else "1000"
            testnet_loss = "50.0" if self.testnet_mode else "5.0"
            testnet_breaker = "75.0" if self.testnet_mode else "10.0"
            
            self.max_portfolio_size_usd = Decimal(os.getenv("MAX_PORTFOLIO_SIZE_USD", testnet_portfolio))
            self.max_position_size_usd = Decimal(os.getenv("MAX_POSITION_SIZE_USD", testnet_position))
            self.daily_loss_limit_percent = Decimal(os.getenv("DAILY_LOSS_LIMIT_PERCENT", testnet_loss))
            self.circuit_breaker_loss_percent = Decimal(os.getenv("CIRCUIT_BREAKER_LOSS_PERCENT", testnet_breaker))
        
        # Execution Settings - use Django settings where available
        if DJANGO_AVAILABLE and settings:
            self.default_slippage_percent = getattr(settings, 'DEFAULT_SLIPPAGE_PERCENT',
                                                  Decimal(os.getenv("DEFAULT_SLIPPAGE_PERCENT", "5.0" if self.testnet_mode else "1.0")))
            self.max_gas_price_gwei = getattr(settings, 'MAX_GAS_PRICE_GWEI',
                                            Decimal(os.getenv("MAX_GAS_PRICE_GWEI", "100.0" if self.testnet_mode else "50.0")))
            self.execution_timeout = getattr(settings, 'EXECUTION_TIMEOUT_SECONDS',
                                           int(os.getenv("EXECUTION_TIMEOUT", "60" if self.testnet_mode else "30")))
        else:
            testnet_slippage = "5.0" if self.testnet_mode else "1.0"
            testnet_gas = "100.0" if self.testnet_mode else "50.0"
            testnet_timeout = "60" if self.testnet_mode else "30"
            
            self.default_slippage_percent = Decimal(os.getenv("DEFAULT_SLIPPAGE_PERCENT", testnet_slippage))
            self.max_gas_price_gwei = Decimal(os.getenv("MAX_GAS_PRICE_GWEI", testnet_gas))
            self.execution_timeout = int(os.getenv("EXECUTION_TIMEOUT", testnet_timeout))
            
        self.nonce_management = os.getenv("NONCE_MANAGEMENT", "auto").lower()
        
        # Paper Trading Settings
        self.paper_mode_slippage = Decimal(os.getenv("PAPER_MODE_SLIPPAGE", "0.5"))
        self.paper_mode_latency_ms = int(os.getenv("PAPER_MODE_LATENCY_MS", "200"))
        
        # Provider Management Settings
        self.provider_health_check_interval = int(os.getenv("PROVIDER_HEALTH_CHECK_INTERVAL", "30"))
        self.provider_failover_threshold = int(os.getenv("PROVIDER_FAILOVER_THRESHOLD", "3"))
        self.provider_recovery_time = int(os.getenv("PROVIDER_RECOVERY_TIME", "300"))
        
        # Database & Queue Settings - use Django settings where available
        if DJANGO_AVAILABLE and settings:
            self.redis_url = getattr(settings, 'REDIS_URL', os.getenv("REDIS_URL", "redis://localhost:6379/0"))
            # Get database URL from Django settings
            databases = getattr(settings, 'DATABASES', {})
            default_db = databases.get('default', {})
            if default_db.get('ENGINE') == 'django.db.backends.postgresql':
                self.django_db_url = f"postgresql://{default_db.get('USER')}:{default_db.get('PASSWORD')}@{default_db.get('HOST', 'localhost')}:{default_db.get('PORT', 5432)}/{default_db.get('NAME')}"
            else:
                self.django_db_url = str(default_db.get('NAME', 'db.sqlite3'))
        else:
            self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self.django_db_url = os.getenv("DATABASE_URL", "sqlite:///db.sqlite3")
        
        logger.info(f"Engine configuration loaded for {len(self.target_chains)} target chains in {self.trading_mode} mode (testnet: {self.testnet_mode})")
    
    def _setup_django_integration(self) -> None:
        """Set up Django integration for chain configuration."""
        if not DJANGO_AVAILABLE:
            logger.warning("Django not available - using fallback configurations only")
            return
            
        try:
            # Fix Redis key mismatch issue
            try:
                from shared.constants import REDIS_KEYS
                # Temporarily fix the key mismatch for chain config bridge
                if 'config' not in REDIS_KEYS and 'config_cache' in REDIS_KEYS:
                    REDIS_KEYS['config'] = REDIS_KEYS['config_cache']
                    logger.debug("Fixed Redis key mapping for chain config bridge")
            except ImportError:
                logger.debug("Could not import REDIS_KEYS - continuing without Redis caching")
            
            # Initialize Redis client for caching Django data
            if self.redis_url:
                self._redis_client = RedisClient(self.redis_url)
                self._chain_config_bridge = ChainConfigBridge(self._redis_client)
                logger.info("Django integration initialized with Redis caching")
            else:
                self._chain_config_bridge = ChainConfigBridge()
                logger.warning("Django integration initialized without Redis caching")
                
        except Exception as e:
            logger.error(f"Failed to initialize Django integration: {e}")
            logger.warning("Disabling Django integration - will use fallback configurations")
            self._chain_config_bridge = None








    async def initialize_chain_configs(self) -> None:
        """
        Asynchronously load chain configurations from Django models.
        
        This must be called after the engine starts to load chain data.
        """
        try:
            if self._redis_client and not self._redis_client.is_connected():
                await self._redis_client.connect()
            
            if self._chain_config_bridge:
                logger.info("Loading chain configurations from Django models...")
                try:
                    self.chains = await self._chain_config_bridge.get_chain_configs()
                    
                    # Filter to only target chains
                    filtered_chains = {
                        chain_id: config for chain_id, config in self.chains.items()
                        if chain_id in self.target_chains
                    }
                    self.chains = filtered_chains
                    
                    if self.chains:
                        logger.info(f"[OK] Loaded {len(self.chains)} chain configurations from Django models")
                        
                        # Log chain details
                        for chain_id, config in self.chains.items():
                            logger.info(f"  {config.name} (ID: {chain_id}): {len(config.rpc_providers)} providers")
                    else:
                        logger.warning("No chain configurations loaded from Django - using fallbacks")
                        self.chains = self._get_fallback_chain_configs()
                        
                except Exception as bridge_error:
                    logger.error(f"Chain config bridge failed: {bridge_error}")
                    logger.warning("Falling back to hardcoded configurations")
                    self.chains = self._get_fallback_chain_configs()
            else:
                logger.warning("Django integration not available, using fallback configurations")
                self.chains = self._get_fallback_chain_configs()
                
        except Exception as e:
            logger.error(f"Failed to load chain configurations: {e}")
            logger.warning("Using fallback configurations")
            self.chains = self._get_fallback_chain_configs()










    async def refresh_chain_configs(self) -> None:
        """Refresh chain configurations from Django models."""
        if self._chain_config_bridge:
            try:
                await self._chain_config_bridge.refresh_cache()
                await self.initialize_chain_configs()
                logger.info("Chain configurations refreshed from Django")
            except Exception as e:
                logger.error(f"Failed to refresh chain configurations: {e}")
    
    def _get_fallback_chain_configs(self) -> Dict[int, ChainConfig]:
        """Get fallback chain configurations when Django is not available."""
        from shared.chain_config_bridge import ChainConfig, RPCProvider
        
        logger.warning("Using fallback chain configurations - ensure Django models are properly configured!")
        
        configs = {}
        
        if self.testnet_mode:
            # Testnet configurations
            
            # Sepolia (11155111)
            if 11155111 in self.target_chains:
                sepolia_url = self._get_rpc_url_from_settings('SEPOLIA_RPC_URL', 'https://rpc.sepolia.org')
                configs[11155111] = ChainConfig(
                    chain_id=11155111,
                    name="Sepolia",
                    rpc_providers=[
                        RPCProvider(
                            name="sepolia_primary",
                            url=sepolia_url,
                            priority=1,
                            is_paid=False,
                        ),
                    ],
                    uniswap_v3_factory="0x1F98431c8aD98523631AE4a59f267346ea31F984",
                    uniswap_v3_router="0xE592427A0AEce92De3Edee1F18E0157C05861564",
                    uniswap_v2_factory="0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
                    uniswap_v2_router="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
                    weth_address="0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14",  # Sepolia WETH
                    usdc_address="0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",  # Sepolia USDC
                    block_time_ms=12000,
                    confirmations_required=1,
                )
            
            # Base Sepolia (84532)
            if 84532 in self.target_chains:
                base_sepolia_url = self._get_rpc_url_from_settings('BASE_SEPOLIA_RPC_URL', 'https://sepolia.base.org')
                configs[84532] = ChainConfig(
                    chain_id=84532,
                    name="Base Sepolia",
                    rpc_providers=[
                        RPCProvider(
                            name="base_sepolia_primary",
                            url=base_sepolia_url,
                            priority=1,
                            is_paid=False,
                        ),
                    ],
                    uniswap_v3_factory="0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24",
                    uniswap_v3_router="0x2626664c2603336E57B271c5C0b26F421741e481",
                    uniswap_v2_factory="0x8909dc15e40173ff4699343b6eb8132c65e18ec6",
                    uniswap_v2_router="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
                    weth_address="0x4200000000000000000000000000000000000006",  # Base WETH
                    usdc_address="0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # Base Sepolia USDC
                    block_time_ms=2000,
                    confirmations_required=1,
                )
            
            # Arbitrum Sepolia (421614)
            if 421614 in self.target_chains:
                arb_sepolia_url = self._get_rpc_url_from_settings('ARBITRUM_SEPOLIA_RPC_URL', 'https://sepolia-rollup.arbitrum.io/rpc')
                configs[421614] = ChainConfig(
                    chain_id=421614,
                    name="Arbitrum Sepolia",
                    rpc_providers=[
                        RPCProvider(
                            name="arbitrum_sepolia_primary",
                            url=arb_sepolia_url,
                            priority=1,
                            is_paid=False,
                        ),
                    ],
                    uniswap_v3_factory="0x1F98431c8aD98523631AE4a59f267346ea31F984",
                    uniswap_v3_router="0xE592427A0AEce92De3Edee1F18E0157C05861564",
                    uniswap_v2_factory="0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
                    uniswap_v2_router="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
                    weth_address="0x980B62Da83eFf3D4576C647993b0c1D7faf17c73",  # Arbitrum Sepolia WETH
                    usdc_address="0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",  # Arbitrum Sepolia USDC
                    block_time_ms=1000,
                    confirmations_required=1,
                )
        else:
            # Mainnet configurations
            
            # Ethereum (1)
            if 1 in self.target_chains:
                eth_url = self._get_rpc_url_from_settings('ETH_RPC_URL', 'https://cloudflare-eth.com')
                configs[1] = ChainConfig(
                    chain_id=1,
                    name="Ethereum",
                    rpc_providers=[
                        RPCProvider(
                            name="ethereum_primary",
                            url=eth_url,
                            priority=1,
                            is_paid=True,
                        ),
                        RPCProvider(
                            name="ethereum_fallback",
                            url=self._get_rpc_url_from_settings('ETH_RPC_URL_FALLBACK', 'https://rpc.ankr.com/eth'),
                            priority=2,
                            is_paid=False,
                        ),
                    ],
                    uniswap_v3_factory="0x1F98431c8aD98523631AE4a59f267346ea31F984",
                    uniswap_v3_router="0xE592427A0AEce92De3Edee1F18E0157C05861564",
                    uniswap_v2_factory="0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
                    uniswap_v2_router="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
                    weth_address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                    usdc_address="0xA0b86a33E6441E2BF3B7E5D95CCcd6D8DD6b8F73",
                    block_time_ms=12000,
                    confirmations_required=2,
                )
            
            # Base (8453)
            if 8453 in self.target_chains:
                base_url = self._get_rpc_url_from_settings('BASE_RPC_URL', 'https://mainnet.base.org')
                configs[8453] = ChainConfig(
                    chain_id=8453,
                    name="Base",
                    rpc_providers=[
                        RPCProvider(
                            name="base_primary",
                            url=base_url,
                            priority=1,
                            is_paid=True,
                        ),
                        RPCProvider(
                            name="base_fallback",
                            url=self._get_rpc_url_from_settings('BASE_RPC_URL_FALLBACK', 'https://mainnet.base.org'),  # ✅ FIXED
                            priority=2,
                            is_paid=False,
                        ),
                    ],
                    uniswap_v3_factory="0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
                    uniswap_v3_router="0x2626664c2603336E57B271c5C0b26F421741e481",
                    uniswap_v2_factory="0x8909dc15e40173ff4699343b6eb8132c65e18ec6",
                    uniswap_v2_router="0x327df1e6de05895d2ab08513aadd9313fe505d86",
                    weth_address="0x4200000000000000000000000000000000000006",
                    usdc_address="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                    block_time_ms=2000,
                    confirmations_required=1,
                )
            
            # Arbitrum (42161)
            if 42161 in self.target_chains:
                arb_url = self._get_rpc_url_from_settings('ARBITRUM_RPC_URL', 'https://arb1.arbitrum.io/rpc')
                configs[42161] = ChainConfig(
                    chain_id=42161,
                    name="Arbitrum",
                    rpc_providers=[
                        RPCProvider(
                            name="arbitrum_primary",
                            url=arb_url,
                            priority=1,
                            is_paid=False,
                        ),
                        RPCProvider(
                            name="arbitrum_fallback",
                            url=self._get_rpc_url_from_settings('ARBITRUM_RPC_URL_FALLBACK', 'https://arbitrum.blockpi.network/v1/rpc/public'),
                            priority=2,
                            is_paid=False,
                        ),
                    ],
                    uniswap_v3_factory="0x1F98431c8aD98523631AE4a59f267346ea31F984",
                    uniswap_v3_router="0xE592427A0AEce92De3Edee1F18E0157C05861564",
                    uniswap_v2_factory="0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
                    uniswap_v2_router="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
                    weth_address="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
                    usdc_address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
                    block_time_ms=1000,
                    confirmations_required=1,
                )
        
        return configs
    
    def _get_rpc_url_from_settings(self, setting_name: str, fallback: str) -> str:
        """Get RPC URL from Django settings or fallback."""
        if DJANGO_AVAILABLE and settings:
            return getattr(settings, setting_name, fallback)
        return os.getenv(setting_name, fallback)
    
    def validate_config(self) -> None:
        """Validate engine configuration (chain configs validated after async load)."""
        errors = []
        
        # Validate trading mode
        valid_modes = ["PAPER", "SHADOW", "LIVE"]
        if self.trading_mode not in valid_modes:
            errors.append(f"Invalid trading mode: {self.trading_mode}. Must be one of {valid_modes}")
        
        # Validate testnet/mainnet consistency
        if self.trading_mode == "LIVE" and self.testnet_mode:
            errors.append("Cannot use LIVE trading mode with testnet_mode=True")
        
        # Validate target chains
        if not self.target_chains:
            errors.append("At least one target chain must be specified")
        
        # Validate chain/testnet consistency
        mainnet_chains = [1, 8453, 42161]
        testnet_chains = [11155111, 84532, 421614]
        
        if self.testnet_mode:
            mainnet_in_targets = [chain for chain in self.target_chains if chain in mainnet_chains]
            if mainnet_in_targets:
                errors.append(f"Mainnet chains {mainnet_in_targets} specified while testnet_mode=True")
        else:
            testnet_in_targets = [chain for chain in self.target_chains if chain in testnet_chains]
            if testnet_in_targets:
                errors.append(f"Testnet chains {testnet_in_targets} specified while testnet_mode=False")
        
        # Validate numeric ranges
        if self.risk_timeout <= 0:
            errors.append("Risk timeout must be positive")
        
        if self.max_position_size_usd > self.max_portfolio_size_usd:
            errors.append("Max position size cannot exceed max portfolio size")
        
        if not (0 < self.daily_loss_limit_percent < 100):
            errors.append("Daily loss limit must be between 0 and 100 percent")
        
        if not (0 < self.default_slippage_percent <= 50):
            errors.append("Default slippage must be between 0 and 50 percent")
        
        # Validate provider settings
        if self.provider_failover_threshold < 1:
            errors.append("Provider failover threshold must be at least 1")
        
        if self.provider_health_check_interval < 10:
            errors.append("Provider health check interval must be at least 10 seconds")
        
        if errors:
            raise ValueError(f"Configuration validation failed: {', '.join(errors)}")
        
        logger.info("Engine configuration validated successfully")
    
    async def validate_chain_configs(self) -> None:
        """Validate chain configurations (called after async initialization)."""
        errors = []
        
        # Check that all target chains have configurations
        for chain_id in self.target_chains:
            if chain_id not in self.chains:
                errors.append(f"No configuration found for target chain ID: {chain_id}")
            else:
                chain_config = self.chains[chain_id]
                if not chain_config.rpc_providers:
                    errors.append(f"No RPC providers configured for chain ID: {chain_id}")
                elif not any(p.url for p in chain_config.rpc_providers):
                    errors.append(f"No valid provider URLs for chain ID: {chain_id}")
        
        if errors:
            raise ValueError(f"Chain configuration validation failed: {', '.join(errors)}")
        
        logger.info(f"Chain configurations validated successfully for {len(self.chains)} chains")
    
    def _log_configuration_summary(self) -> None:
        """Log a summary of the current configuration."""
        summary = {
            "trading_mode": self.trading_mode,
            "testnet_mode": self.testnet_mode,
            "target_chains": self.target_chains,
            "discovery_enabled": self.discovery_enabled,
            "risk_timeout": self.risk_timeout,
            "max_portfolio_size_usd": str(self.max_portfolio_size_usd),
            "django_available": DJANGO_AVAILABLE,
            "django_integration": self._chain_config_bridge is not None,
            "redis_caching": self._redis_client is not None,
        }
        
        logger.info(f"Engine configuration summary: {summary}")
    
    # =========================================================================
    # CHAIN CONFIGURATION ACCESS METHODS
    # =========================================================================
    
    def get_chain_config(self, chain_id: int) -> Optional[ChainConfig]:
        """Get configuration for a specific chain."""
        return self.chains.get(chain_id)
    
    def get_primary_provider(self, chain_id: int) -> Optional[RPCProvider]:
        """Get the primary (highest priority) RPC provider for a chain."""
        chain_config = self.get_chain_config(chain_id)
        if not chain_config or not chain_config.rpc_providers:
            return None
        
        # Return provider with lowest priority number (highest preference)
        return min(chain_config.rpc_providers, key=lambda p: p.priority)
    
    def get_paid_providers(self, chain_id: int) -> List[RPCProvider]:
        """Get all paid providers for a chain."""
        chain_config = self.get_chain_config(chain_id)
        if not chain_config:
            return []
        
        return [p for p in chain_config.rpc_providers if p.is_paid]
    
    def get_public_providers(self, chain_id: int) -> List[RPCProvider]:
        """Get all public/free providers for a chain."""
        chain_config = self.get_chain_config(chain_id)
        if not chain_config:
            return []
        
        return [p for p in chain_config.rpc_providers if not p.is_paid]
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def is_paper_mode(self) -> bool:
        """Check if engine is in paper trading mode."""
        return self.trading_mode == "PAPER"
    
    def is_live_mode(self) -> bool:
        """Check if engine is in live trading mode."""
        return self.trading_mode == "LIVE"
    
    def is_shadow_mode(self) -> bool:
        """Check if engine is in shadow trading mode."""
        return self.trading_mode == "SHADOW"
    
    def is_testnet_mode(self) -> bool:
        """Check if engine is in testnet mode."""
        return self.testnet_mode
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for logging/debugging."""
        config_dict = {
            "trading_mode": self.trading_mode,
            "testnet_mode": self.testnet_mode,
            "target_chains": self.target_chains,
            "discovery_enabled": self.discovery_enabled,
            "risk_timeout": self.risk_timeout,
            "max_portfolio_size_usd": str(self.max_portfolio_size_usd),
            "max_position_size_usd": str(self.max_position_size_usd),
            "provider_failover_threshold": self.provider_failover_threshold,
            "paper_mode": self.is_paper_mode(),
            "live_mode": self.is_live_mode(),
            "django_integration": self._chain_config_bridge is not None,
        }
        
        # Add chain configuration summary
        if self.chains:
            config_dict["chains"] = {
                chain_id: {
                    "name": config.name,
                    "provider_count": len(config.rpc_providers),
                    "block_time_ms": config.block_time_ms,
                }
                for chain_id, config in self.chains.items()
            }
        
        return config_dict
    
    async def shutdown(self) -> None:
        """Shutdown configuration and cleanup resources."""
        if self._redis_client and self._redis_client.is_connected():
            await self._redis_client.disconnect()
            logger.info("Configuration Redis client disconnected")


# ============================================================================= 
# ASYNC CONFIGURATION FACTORY
# =============================================================================

async def create_engine_config() -> EngineConfig:
    """
    Create and initialize engine configuration asynchronously.
    
    This factory function handles the async initialization of chain configurations
    from Django models.
    
    Returns:
        Fully initialized EngineConfig instance
    """
    # Create config instance
    config = EngineConfig()
    
    # Initialize chain configurations from Django
    await config.initialize_chain_configs()
    
    # Validate chain configurations
    await config.validate_chain_configs()
    
    logger.info("Engine configuration fully initialized from Django models")
    return config


# Global configuration instance (will be set by main.py)
config: Optional[EngineConfig] = None


async def get_config() -> EngineConfig:
    """Get the global engine configuration, initializing if necessary."""
    global config
    if config is None:
        config = await create_engine_config()
    return config







from dataclasses import dataclass
from typing import List, Optional
from decimal import Decimal

@dataclass
class ChainConfig:
    """Complete chain configuration for Transaction Manager."""
    chain_id: int
    name: str
    rpc_providers: List[str]
    weth_address: str
    native_token_symbol: str = "ETH"
    block_time_seconds: int = 12
    max_gas_price_gwei: Decimal = Decimal('100')
    
    # Optional WebSocket providers
    ws_providers: Optional[List[str]] = None
    
    # DEX contracts
    uniswap_v2_router: Optional[str] = None
    uniswap_v3_router: Optional[str] = None
    sushiswap_router: Optional[str] = None

# Predefined chain configurations
CHAIN_CONFIGS = {
    1: ChainConfig(
        chain_id=1,
        name="Ethereum",
        rpc_providers=[
            "https://eth-mainnet.g.alchemy.com/v2/demo",
            "https://mainnet.infura.io/v3/demo",
        ],
        weth_address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        uniswap_v2_router="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
        uniswap_v3_router="0xE592427A0AEce92De3Edee1F18E0157C05861564",
    ),
    8453: ChainConfig(
        chain_id=8453,
        name="Base",
        rpc_providers=[
            "https://mainnet.base.org",
            "https://base.gateway.tenderly.co",
        ],
        weth_address="0x4200000000000000000000000000000000000006",
        block_time_seconds=2,
        max_gas_price_gwei=Decimal('10'),
    ),
    84532: ChainConfig(
        chain_id=84532,
        name="Base Sepolia",
        rpc_providers=[
            "https://sepolia.base.org",
            "https://base-sepolia.gateway.tenderly.co",
        ],
        weth_address="0x4200000000000000000000000000000000000006",
        block_time_seconds=2,
        max_gas_price_gwei=Decimal('5'),
    ),
}

def get_chain_config(chain_id: int) -> ChainConfig:
    """Get chain configuration by ID."""
    if chain_id in CHAIN_CONFIGS:
        return CHAIN_CONFIGS[chain_id]
    
    # Return a default config if not found
    return ChainConfig(
        chain_id=chain_id,
        name=f"Chain_{chain_id}",
        rpc_providers=["https://rpc.example.com"],
        weth_address="0x0000000000000000000000000000000000000000",
    )