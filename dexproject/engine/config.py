"""
Engine Configuration Management

Handles all configuration loading from environment variables,
with sensible defaults and validation for the trading engine.
"""

import os
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class RPCProvider:
    """RPC provider configuration."""
    name: str
    url: str
    websocket_url: Optional[str] = None
    api_key: Optional[str] = None
    priority: int = 1  # Lower = higher priority
    max_requests_per_second: int = 10


@dataclass
class ChainConfig:
    """Per-chain configuration."""
    chain_id: int
    name: str
    rpc_providers: List[RPCProvider]
    uniswap_v3_factory: str
    uniswap_v3_router: str
    weth_address: str
    usdc_address: str
    block_time_ms: int = 12000  # Average block time


class EngineConfig:
    """
    Central configuration management for the trading engine.
    
    Loads settings from environment variables with validation
    and provides configuration for all engine components.
    """
    
    def __init__(self):
        """Initialize configuration from environment variables."""
        self.load_config()
        self.validate_config()
    
    def load_config(self) -> None:
        """Load all configuration from environment variables."""
        
        # Engine Core Settings
        self.trading_mode = os.getenv("TRADING_MODE", "PAPER").upper()
        self.engine_name = os.getenv("ENGINE_NAME", "dex-trading-engine")
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        
        # Target Chains (comma-separated chain IDs)
        chain_ids_str = os.getenv("TARGET_CHAINS", "8453")  # Default to Base
        self.target_chains = [int(cid.strip()) for cid in chain_ids_str.split(",")]
        
        # Discovery Settings
        self.discovery_enabled = os.getenv("DISCOVERY_ENABLED", "true").lower() == "true"
        self.websocket_timeout = int(os.getenv("WEBSOCKET_TIMEOUT", "30"))
        self.http_poll_interval = int(os.getenv("HTTP_POLL_INTERVAL", "5"))
        self.max_pairs_per_hour = int(os.getenv("MAX_PAIRS_PER_HOUR", "100"))
        
        # Risk Assessment Settings
        self.risk_timeout = int(os.getenv("RISK_TIMEOUT", "10"))
        self.risk_parallel_checks = int(os.getenv("RISK_PARALLEL_CHECKS", "4"))
        self.min_liquidity_usd = Decimal(os.getenv("MIN_LIQUIDITY_USD", "10000"))
        self.max_buy_tax_percent = Decimal(os.getenv("MAX_BUY_TAX_PERCENT", "5.0"))
        self.max_sell_tax_percent = Decimal(os.getenv("MAX_SELL_TAX_PERCENT", "5.0"))
        
        # Portfolio Management
        self.max_portfolio_size_usd = Decimal(os.getenv("MAX_PORTFOLIO_SIZE_USD", "10000"))
        self.max_position_size_usd = Decimal(os.getenv("MAX_POSITION_SIZE_USD", "1000"))
        self.daily_loss_limit_percent = Decimal(os.getenv("DAILY_LOSS_LIMIT_PERCENT", "5.0"))
        self.circuit_breaker_loss_percent = Decimal(os.getenv("CIRCUIT_BREAKER_LOSS_PERCENT", "10.0"))
        
        # Execution Settings
        self.default_slippage_percent = Decimal(os.getenv("DEFAULT_SLIPPAGE_PERCENT", "1.0"))
        self.max_gas_price_gwei = Decimal(os.getenv("MAX_GAS_PRICE_GWEI", "50"))
        self.execution_timeout = int(os.getenv("EXECUTION_TIMEOUT", "30"))
        
        # Paper Trading Settings
        self.paper_mode_slippage = Decimal(os.getenv("PAPER_MODE_SLIPPAGE", "0.5"))
        self.paper_mode_latency_ms = int(os.getenv("PAPER_MODE_LATENCY_MS", "200"))
        
        # Database & Queue Settings
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.django_db_url = os.getenv("DATABASE_URL", "sqlite:///db.sqlite3")
        
        # Load chain configurations
        self.chains = self._load_chain_configs()
    
    def _load_chain_configs(self) -> Dict[int, ChainConfig]:
        """Load per-chain configurations."""
        chains = {}
        
        # Base configuration
        if 8453 in self.target_chains:
            base_providers = self._load_rpc_providers("BASE")
            chains[8453] = ChainConfig(
                chain_id=8453,
                name="Base",
                rpc_providers=base_providers,
                uniswap_v3_factory="0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
                uniswap_v3_router="0x2626664c2603336E57B271c5C0b26F421741e481",
                weth_address="0x4200000000000000000000000000000000000006",
                usdc_address="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                block_time_ms=2000  # Base ~2s blocks
            )
        
        # Ethereum configuration
        if 1 in self.target_chains:
            eth_providers = self._load_rpc_providers("ETH")
            chains[1] = ChainConfig(
                chain_id=1,
                name="Ethereum",
                rpc_providers=eth_providers,
                uniswap_v3_factory="0x1F98431c8aD98523631AE4a59f267346ea31F984",
                uniswap_v3_router="0xE592427A0AEce92De3Edee1F18E0157C05861564",
                weth_address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                usdc_address="0xA0b86a33E6E67c6e2B2EB44630b58cf95e5e7d77",
                block_time_ms=12000  # Ethereum ~12s blocks
            )
        
        return chains
    
    def _load_rpc_providers(self, chain_prefix: str) -> List[RPCProvider]:
        """Load RPC provider configurations for a chain."""
        providers = []
        
        # Primary provider
        primary_url = os.getenv(f"{chain_prefix}_RPC_URL")
        primary_ws = os.getenv(f"{chain_prefix}_WS_URL")
        primary_key = os.getenv(f"{chain_prefix}_API_KEY")
        
        if primary_url:
            providers.append(RPCProvider(
                name=f"{chain_prefix}_PRIMARY",
                url=primary_url,
                websocket_url=primary_ws,
                api_key=primary_key,
                priority=1
            ))
        
        # Secondary provider (fallback)
        secondary_url = os.getenv(f"{chain_prefix}_RPC_URL_2")
        secondary_ws = os.getenv(f"{chain_prefix}_WS_URL_2")
        secondary_key = os.getenv(f"{chain_prefix}_API_KEY_2")
        
        if secondary_url:
            providers.append(RPCProvider(
                name=f"{chain_prefix}_SECONDARY",
                url=secondary_url,
                websocket_url=secondary_ws,
                api_key=secondary_key,
                priority=2
            ))
        
        # Default fallback if no providers configured
        if not providers:
            if chain_prefix == "BASE":
                providers.append(RPCProvider(
                    name="BASE_PUBLIC",
                    url="https://mainnet.base.org",
                    priority=3,
                    max_requests_per_second=5
                ))
            elif chain_prefix == "ETH":
                providers.append(RPCProvider(
                    name="ETH_PUBLIC",
                    url="https://cloudflare-eth.com",
                    priority=3,
                    max_requests_per_second=5
                ))
        
        return providers
    
    def validate_config(self) -> None:
        """Validate configuration values."""
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
        
        # Validate numeric ranges
        if self.risk_timeout <= 0:
            errors.append("Risk timeout must be positive")
        
        if self.max_position_size_usd > self.max_portfolio_size_usd:
            errors.append("Max position size cannot exceed max portfolio size")
        
        if self.daily_loss_limit_percent <= 0 or self.daily_loss_limit_percent >= 100:
            errors.append("Daily loss limit must be between 0 and 100 percent")
        
        if errors:
            raise ValueError(f"Configuration validation failed: {', '.join(errors)}")
        
        logger.info(f"Configuration validated successfully for {len(self.target_chains)} chains")
    
    def get_chain_config(self, chain_id: int) -> Optional[ChainConfig]:
        """Get configuration for a specific chain."""
        return self.chains.get(chain_id)
    
    def get_primary_provider(self, chain_id: int) -> Optional[RPCProvider]:
        """Get the primary RPC provider for a chain."""
        chain_config = self.get_chain_config(chain_id)
        if not chain_config or not chain_config.rpc_providers:
            return None
        
        # Return provider with lowest priority (highest preference)
        return min(chain_config.rpc_providers, key=lambda p: p.priority)
    
    def is_paper_mode(self) -> bool:
        """Check if engine is in paper trading mode."""
        return self.trading_mode == "PAPER"
    
    def is_live_mode(self) -> bool:
        """Check if engine is in live trading mode."""
        return self.trading_mode == "LIVE"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for logging/debugging."""
        return {
            "trading_mode": self.trading_mode,
            "target_chains": self.target_chains,
            "discovery_enabled": self.discovery_enabled,
            "risk_timeout": self.risk_timeout,
            "max_portfolio_size_usd": str(self.max_portfolio_size_usd),
            "max_position_size_usd": str(self.max_position_size_usd),
            "paper_mode": self.is_paper_mode()
        }


# Global configuration instance
config = EngineConfig()