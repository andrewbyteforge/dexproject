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


logger = logging.getLogger(__name__)


class EngineConfig:
    """
    Enhanced configuration management for the trading engine.
    
    Now uses Django Chain/DEX models as single source of truth for chain configuration,
    while maintaining engine-specific settings via environment variables.
    """
    
    def __init__(self):
        """Initialize configuration from environment and Django models."""
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
        """Load engine-specific configuration from environment variables."""
        
        # Engine Core Settings
        self.trading_mode = os.getenv("TRADING_MODE", "PAPER").upper()
        self.engine_name = os.getenv("ENGINE_NAME", "dex-trading-engine")
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        
        # Target Chains (comma-separated chain IDs)
        chain_ids_str = os.getenv("TARGET_CHAINS", "8453,1")  # Base + Ethereum
        self.target_chains = [int(cid.strip()) for cid in chain_ids_str.split(",")]
        
        # Discovery Settings
        self.discovery_enabled = os.getenv("DISCOVERY_ENABLED", "true").lower() == "true"
        self.websocket_timeout = int(os.getenv("WEBSOCKET_TIMEOUT", "30"))
        self.websocket_reconnect_delay = int(os.getenv("WEBSOCKET_RECONNECT_DELAY", "5"))
        self.http_poll_interval = int(os.getenv("HTTP_POLL_INTERVAL", "5"))
        self.max_pairs_per_hour = int(os.getenv("MAX_PAIRS_PER_HOUR", "100"))
        self.event_batch_size = int(os.getenv("EVENT_BATCH_SIZE", "50"))
        
        # Risk Assessment Settings
        self.risk_timeout = int(os.getenv("RISK_TIMEOUT", "15"))
        self.risk_parallel_checks = int(os.getenv("RISK_PARALLEL_CHECKS", "4"))
        self.min_liquidity_usd = Decimal(os.getenv("MIN_LIQUIDITY_USD", "10000"))
        self.max_buy_tax_percent = Decimal(os.getenv("MAX_BUY_TAX_PERCENT", "5.0"))
        self.max_sell_tax_percent = Decimal(os.getenv("MAX_SELL_TAX_PERCENT", "5.0"))
        self.min_holder_count = int(os.getenv("MIN_HOLDER_COUNT", "50"))
        
        # Portfolio Management
        self.max_portfolio_size_usd = Decimal(os.getenv("MAX_PORTFOLIO_SIZE_USD", "10000"))
        self.max_position_size_usd = Decimal(os.getenv("MAX_POSITION_SIZE_USD", "1000"))
        self.daily_loss_limit_percent = Decimal(os.getenv("DAILY_LOSS_LIMIT_PERCENT", "5.0"))
        self.circuit_breaker_loss_percent = Decimal(os.getenv("CIRCUIT_BREAKER_LOSS_PERCENT", "10.0"))
        
        # Execution Settings
        self.default_slippage_percent = Decimal(os.getenv("DEFAULT_SLIPPAGE_PERCENT", "1.0"))
        self.max_gas_price_gwei = Decimal(os.getenv("MAX_GAS_PRICE_GWEI", "50"))
        self.execution_timeout = int(os.getenv("EXECUTION_TIMEOUT", "30"))
        self.nonce_management = os.getenv("NONCE_MANAGEMENT", "auto").lower()
        
        # Paper Trading Settings
        self.paper_mode_slippage = Decimal(os.getenv("PAPER_MODE_SLIPPAGE", "0.5"))
        self.paper_mode_latency_ms = int(os.getenv("PAPER_MODE_LATENCY_MS", "200"))
        
        # Provider Management Settings
        self.provider_health_check_interval = int(os.getenv("PROVIDER_HEALTH_CHECK_INTERVAL", "30"))
        self.provider_failover_threshold = int(os.getenv("PROVIDER_FAILOVER_THRESHOLD", "3"))
        self.provider_recovery_time = int(os.getenv("PROVIDER_RECOVERY_TIME", "300"))
        
        # Database & Queue Settings
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.django_db_url = os.getenv("DATABASE_URL", "sqlite:///db.sqlite3")
        
        logger.info(f"Engine configuration loaded for {len(self.target_chains)} target chains in {self.trading_mode} mode")
    
    def _setup_django_integration(self) -> None:
        """Set up Django integration for chain configuration."""
        try:
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
                self.chains = await self._chain_config_bridge.get_chain_configs()
                
                # Filter to only target chains
                filtered_chains = {
                    chain_id: config for chain_id, config in self.chains.items()
                    if chain_id in self.target_chains
                }
                self.chains = filtered_chains
                
                logger.info(f"Loaded {len(self.chains)} chain configurations from Django")
                
                # Log chain details
                for chain_id, config in self.chains.items():
                    logger.info(f"  {config.name} (ID: {chain_id}): {len(config.rpc_providers)} providers")
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
        
        # Base (8453) - only if in target chains
        if 8453 in self.target_chains:
            configs[8453] = ChainConfig(
                chain_id=8453,
                name="Base",
                rpc_providers=[
                    RPCProvider(
                        name="base_primary",
                        url="https://base-mainnet.g.alchemy.com/v2/demo",
                        priority=1,
                        is_paid=True,
                    ),
                    RPCProvider(
                        name="base_fallback",
                        url="https://mainnet.base.org",
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
        
        # Ethereum (1) - only if in target chains
        if 1 in self.target_chains:
            configs[1] = ChainConfig(
                chain_id=1,
                name="Ethereum",
                rpc_providers=[
                    RPCProvider(
                        name="ethereum_primary",
                        url="https://eth-mainnet.g.alchemy.com/v2/demo",
                        priority=1,
                        is_paid=True,
                    ),
                    RPCProvider(
                        name="ethereum_fallback",
                        url="https://ethereum.publicnode.com",
                        priority=2,
                        is_paid=False,
                    ),
                ],
                uniswap_v3_factory="0x1F98431c8aD98523631AE4a59f267346ea31F984",
                uniswap_v3_router="0xE592427A0AEce92De3Edee1F18E0157C05861564",
                uniswap_v2_factory="0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
                uniswap_v2_router="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
                weth_address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                usdc_address="0xA0b86a33E6E67c6e2B2EB44630b58cf95e5e7d77",
                block_time_ms=12000,
                confirmations_required=2,
            )
        
        return configs
    
    def validate_config(self) -> None:
        """Validate engine configuration (chain configs validated after async load)."""
        errors = []
        
        # Validate trading mode
        valid_modes = ["PAPER", "SHADOW", "LIVE"]
        if self.trading_mode not in valid_modes:
            errors.append(f"Invalid trading mode: {self.trading_mode}. Must be one of {valid_modes}")
        
        # Validate target chains
        if not self.target_chains:
            errors.append("At least one target chain must be specified")
        
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
            "target_chains": self.target_chains,
            "discovery_enabled": self.discovery_enabled,
            "risk_timeout": self.risk_timeout,
            "max_portfolio_size_usd": str(self.max_portfolio_size_usd),
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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for logging/debugging."""
        config_dict = {
            "trading_mode": self.trading_mode,
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