"""
Enhanced Engine Configuration Management

Real blockchain integration with robust RPC provider management,
failover handling, and production-ready Web3 infrastructure.
Supports paid providers (Alchemy/Infura) with public fallbacks.

File: dexproject/engine/config.py
"""

import os
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class RPCProvider:
    """RPC provider configuration with enhanced features."""
    name: str
    url: str
    websocket_url: Optional[str] = None
    api_key: Optional[str] = None
    priority: int = 1  # Lower = higher priority
    max_requests_per_second: int = 10
    timeout_seconds: int = 10
    is_paid: bool = False  # Track if this is a paid provider
    supports_debug: bool = False  # For transaction simulation
    supports_trace: bool = False  # For advanced tracing
    
    def __post_init__(self):
        """Validate provider configuration."""
        if not self.url:
            raise ValueError(f"Provider {self.name} must have a URL")
        if not self.url.startswith(('http://', 'https://', 'wss://', 'ws://')):
            raise ValueError(f"Provider {self.name} URL must include protocol")


@dataclass
class ChainConfig:
    """Enhanced per-chain configuration."""
    chain_id: int
    name: str
    rpc_providers: List[RPCProvider]
    uniswap_v3_factory: str
    uniswap_v3_router: str
    uniswap_v2_factory: str  # Add V2 support
    uniswap_v2_router: str
    weth_address: str
    usdc_address: str
    block_time_ms: int = 12000
    gas_limit_buffer: float = 1.2  # 20% buffer on gas estimates
    max_gas_price_multiplier: float = 2.0  # Max 2x current gas price
    confirmations_required: int = 1  # Blocks to wait for confirmation
    
    # DEX-specific settings
    pair_creation_events: Dict[str, List[str]] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize DEX event configurations."""
        if not self.pair_creation_events:
            self.pair_creation_events = {
                'uniswap_v3': [
                    '0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118'  # PoolCreated
                ],
                'uniswap_v2': [
                    '0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9'  # PairCreated
                ]
            }


class EngineConfig:
    """
    Enhanced configuration management for the trading engine.
    
    Provides robust RPC provider management, failover handling,
    and comprehensive validation for production deployment.
    """
    
    def __init__(self):
        """Initialize configuration from environment variables."""
        self.load_config()
        self.validate_config()
        self._log_configuration_summary()
    
    def load_config(self) -> None:
        """Load all configuration from environment variables."""
        
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
        self.risk_timeout = int(os.getenv("RISK_TIMEOUT", "15"))  # Increased for real checks
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
        self.provider_recovery_time = int(os.getenv("PROVIDER_RECOVERY_TIME", "300"))  # 5 minutes
        
        # Database & Queue Settings
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.django_db_url = os.getenv("DATABASE_URL", "sqlite:///db.sqlite3")
        
        # Load chain configurations
        self.chains = self._load_chain_configs()
        
        logger.info(f"Configuration loaded for {len(self.target_chains)} chains in {self.trading_mode} mode")
    
    def _load_chain_configs(self) -> Dict[int, ChainConfig]:
        """Load enhanced per-chain configurations with robust provider setup."""
        chains = {}
        
        # Base (8453) configuration
        if 8453 in self.target_chains:
            base_providers = self._load_rpc_providers("BASE")
            chains[8453] = ChainConfig(
                chain_id=8453,
                name="Base",
                rpc_providers=base_providers,
                uniswap_v3_factory="0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
                uniswap_v3_router="0x2626664c2603336E57B271c5C0b26F421741e481",
                uniswap_v2_factory="0x8909dc15e40173ff4699343b6eb8132c65e18ec6",  # BaseSwap
                uniswap_v2_router="0x327df1e6de05895d2ab08513aadd9313fe505d86",
                weth_address="0x4200000000000000000000000000000000000006",
                usdc_address="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                block_time_ms=2000,  # Base ~2s blocks
                confirmations_required=1,
                gas_limit_buffer=1.1  # Lower buffer for Base
            )
            logger.info(f"Configured Base chain with {len(base_providers)} providers")
        
        # Ethereum (1) configuration
        if 1 in self.target_chains:
            eth_providers = self._load_rpc_providers("ETH")
            chains[1] = ChainConfig(
                chain_id=1,
                name="Ethereum",
                rpc_providers=eth_providers,
                uniswap_v3_factory="0x1F98431c8aD98523631AE4a59f267346ea31F984",
                uniswap_v3_router="0xE592427A0AEce92De3Edee1F18E0157C05861564",
                uniswap_v2_factory="0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
                uniswap_v2_router="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
                weth_address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                usdc_address="0xA0b86a33E6E67c6e2B2EB44630b58cf95e5e7d77",
                block_time_ms=12000,  # Ethereum ~12s blocks
                confirmations_required=2,  # More confirmations for Ethereum
                gas_limit_buffer=1.3  # Higher buffer for Ethereum
            )
            logger.info(f"Configured Ethereum chain with {len(eth_providers)} providers")
        
        return chains
    
    def _load_rpc_providers(self, chain_prefix: str) -> List[RPCProvider]:
        """Load RPC provider configurations with paid + fallback support."""
        providers = []
        
        # Primary paid provider (Alchemy/Infura)
        primary_url = os.getenv(f"{chain_prefix}_RPC_URL")
        primary_ws = os.getenv(f"{chain_prefix}_WS_URL")
        primary_key = os.getenv(f"{chain_prefix}_API_KEY")
        
        if primary_url:
            # Detect provider type for enhanced features
            is_alchemy = 'alchemy' in primary_url.lower()
            is_infura = 'infura' in primary_url.lower()
            is_quicknode = 'quicknode' in primary_url.lower()
            
            providers.append(RPCProvider(
                name=f"{chain_prefix}_PRIMARY",
                url=primary_url,
                websocket_url=primary_ws,
                api_key=primary_key,
                priority=1,
                max_requests_per_second=25 if (is_alchemy or is_infura) else 10,
                is_paid=True,
                supports_debug=is_alchemy or is_quicknode,  # Alchemy/QuickNode support debug
                supports_trace=is_alchemy or is_quicknode,
                timeout_seconds=10
            ))
            logger.info(f"Added primary provider for {chain_prefix}: {primary_url[:50]}...")
        
        # Secondary paid provider
        secondary_url = os.getenv(f"{chain_prefix}_RPC_URL_2")
        secondary_ws = os.getenv(f"{chain_prefix}_WS_URL_2")
        secondary_key = os.getenv(f"{chain_prefix}_API_KEY_2")
        
        if secondary_url:
            is_alchemy = 'alchemy' in secondary_url.lower()
            is_infura = 'infura' in secondary_url.lower()
            is_quicknode = 'quicknode' in secondary_url.lower()
            
            providers.append(RPCProvider(
                name=f"{chain_prefix}_SECONDARY",
                url=secondary_url,
                websocket_url=secondary_ws,
                api_key=secondary_key,
                priority=2,
                max_requests_per_second=25 if (is_alchemy or is_infura) else 10,
                is_paid=True,
                supports_debug=is_alchemy or is_quicknode,
                supports_trace=is_alchemy or is_quicknode,
                timeout_seconds=10
            ))
            logger.info(f"Added secondary provider for {chain_prefix}")
        
        # Public fallback providers
        if chain_prefix == "BASE":
            providers.extend([
                RPCProvider(
                    name="BASE_PUBLIC_1",
                    url="https://mainnet.base.org",
                    priority=3,
                    max_requests_per_second=5,
                    is_paid=False,
                    timeout_seconds=15
                ),
                RPCProvider(
                    name="BASE_PUBLIC_2", 
                    url="https://base.blockpi.network/v1/rpc/public",
                    priority=4,
                    max_requests_per_second=3,
                    is_paid=False,
                    timeout_seconds=20
                )
            ])
        elif chain_prefix == "ETH":
            providers.extend([
                RPCProvider(
                    name="ETH_PUBLIC_1",
                    url="https://cloudflare-eth.com",
                    priority=3,
                    max_requests_per_second=5,
                    is_paid=False,
                    timeout_seconds=15
                ),
                RPCProvider(
                    name="ETH_PUBLIC_2",
                    url="https://ethereum.publicnode.com",
                    priority=4,
                    max_requests_per_second=3,
                    is_paid=False,
                    timeout_seconds=20
                )
            ])
        
        if not providers:
            logger.warning(f"No RPC providers configured for {chain_prefix}!")
        else:
            paid_count = sum(1 for p in providers if p.is_paid)
            logger.info(f"Loaded {len(providers)} providers for {chain_prefix} ({paid_count} paid, {len(providers)-paid_count} public)")
        
        return providers
    
    def validate_config(self) -> None:
        """Enhanced configuration validation."""
        errors = []
        
        # Validate trading mode
        valid_modes = ["PAPER", "SHADOW", "LIVE"]
        if self.trading_mode not in valid_modes:
            errors.append(f"Invalid trading mode: {self.trading_mode}. Must be one of {valid_modes}")
        
        # Validate chains have providers
        for chain_id in self.target_chains:
            if chain_id not in self.chains:
                errors.append(f"No configuration found for chain ID: {chain_id}")
            elif not self.chains[chain_id].rpc_providers:
                errors.append(f"No RPC providers configured for chain ID: {chain_id}")
            else:
                # Check for at least one working provider
                chain_config = self.chains[chain_id]
                if not any(p.url for p in chain_config.rpc_providers):
                    errors.append(f"No valid provider URLs for chain ID: {chain_id}")
        
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
        
        logger.info(f"Configuration validated successfully for {len(self.target_chains)} chains")
    
    def _log_configuration_summary(self) -> None:
        """Log a summary of the current configuration."""
        summary = {
            "trading_mode": self.trading_mode,
            "target_chains": self.target_chains,
            "discovery_enabled": self.discovery_enabled,
            "risk_timeout": self.risk_timeout,
            "max_portfolio_size_usd": str(self.max_portfolio_size_usd),
            "provider_count_by_chain": {
                chain_id: len(config.rpc_providers) 
                for chain_id, config in self.chains.items()
            }
        }
        
        logger.info(f"Engine configuration summary: {summary}")
    
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
        return {
            "trading_mode": self.trading_mode,
            "target_chains": self.target_chains,
            "discovery_enabled": self.discovery_enabled,
            "risk_timeout": self.risk_timeout,
            "max_portfolio_size_usd": str(self.max_portfolio_size_usd),
            "max_position_size_usd": str(self.max_position_size_usd),
            "provider_failover_threshold": self.provider_failover_threshold,
            "paper_mode": self.is_paper_mode(),
            "live_mode": self.is_live_mode()
        }


# Global configuration instance
config = EngineConfig()