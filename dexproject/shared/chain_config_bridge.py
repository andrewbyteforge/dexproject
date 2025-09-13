"""
Chain Configuration Bridge - Django Models as Single Source of Truth

This module provides the bridge between Django models (SSOT) and the async engine,
ensuring consistent chain configuration across the entire system.

File: dexproject/shared/chain_config_bridge.py
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from decimal import Decimal

from .redis_client import RedisClient
from .constants import REDIS_KEYS


logger = logging.getLogger(__name__)


@dataclass
class RPCProvider:
    """RPC provider configuration (matches engine/config.py structure)."""
    name: str
    url: str
    websocket_url: Optional[str] = None
    api_key: Optional[str] = None
    priority: int = 1
    max_requests_per_second: int = 10
    timeout_seconds: int = 10
    is_paid: bool = False
    supports_debug: bool = False
    supports_trace: bool = False


@dataclass
class ChainConfig:
    """Chain configuration (matches engine/config.py structure)."""
    chain_id: int
    name: str
    rpc_providers: List[RPCProvider]
    uniswap_v3_factory: str
    uniswap_v3_router: str
    uniswap_v2_factory: str
    uniswap_v2_router: str
    weth_address: str
    usdc_address: str
    block_time_ms: int = 12000
    gas_limit_buffer: float = 1.2
    max_gas_price_multiplier: float = 2.0
    confirmations_required: int = 1


class ChainConfigBridge:
    """
    Bridge between Django Chain/DEX models and engine configuration.
    
    Provides a clean interface for the engine to get chain configuration
    from Django models without direct Django imports.
    """
    
    def __init__(self, redis_client: Optional[RedisClient] = None):
        """
        Initialize chain configuration bridge.
        
        Args:
            redis_client: Optional Redis client for caching
        """
        self.redis_client = redis_client
        self.logger = logger.getChild(self.__class__.__name__)
        self._cache_ttl = 300  # 5 minutes cache
    
    async def get_chain_configs(self, use_cache: bool = True) -> Dict[int, ChainConfig]:
        """
        Get all chain configurations from Django models.
        
        Args:
            use_cache: Whether to use Redis cache
            
        Returns:
            Dictionary of chain_id -> ChainConfig
        """
        cache_key = f"{REDIS_KEYS['config']}:chains"
        
        # Try cache first
        if use_cache and self.redis_client:
            try:
                cached_configs = await self.redis_client.get(cache_key)
                if cached_configs:
                    self.logger.debug("Using cached chain configurations")
                    return self._deserialize_chain_configs(cached_configs)
            except Exception as e:
                self.logger.warning(f"Cache read failed, fetching from Django: {e}")
        
        # Fetch from Django
        configs = await self._fetch_from_django()
        
        # Cache the result
        if self.redis_client:
            try:
                await self.redis_client.set(
                    cache_key, 
                    self._serialize_chain_configs(configs),
                    expire=self._cache_ttl
                )
                self.logger.debug("Cached chain configurations")
            except Exception as e:
                self.logger.warning(f"Cache write failed: {e}")
        
        return configs
    
    async def get_chain_config(self, chain_id: int, use_cache: bool = True) -> Optional[ChainConfig]:
        """
        Get configuration for a specific chain.
        
        Args:
            chain_id: Chain ID to get config for
            use_cache: Whether to use Redis cache
            
        Returns:
            ChainConfig or None if not found
        """
        configs = await self.get_chain_configs(use_cache)
        return configs.get(chain_id)
    
    async def refresh_cache(self) -> None:
        """Force refresh of cached chain configurations."""
        await self.get_chain_configs(use_cache=False)
        self.logger.info("Chain configuration cache refreshed")
    
    async def _fetch_from_django(self) -> Dict[int, ChainConfig]:
        """
        Fetch chain configurations from Django models.
        
        This method uses the Django REST framework or direct model access
        to get chain and DEX information from the database.
        """
        try:
            # Method 1: Try to use Django REST API (if available)
            configs = await self._fetch_via_api()
            if configs:
                return configs
        except Exception as e:
            self.logger.debug(f"API fetch failed, trying direct model access: {e}")
        
        try:
            # Method 2: Direct Django model access (requires Django to be available)
            configs = await self._fetch_via_models()
            if configs:
                return configs
        except Exception as e:
            self.logger.warning(f"Django model access failed: {e}")
        
        # Method 3: Fallback to hardcoded configuration
        self.logger.warning("Using fallback hardcoded configuration")
        return self._get_fallback_configs()
    
    async def _fetch_via_api(self) -> Dict[int, ChainConfig]:
        """Fetch configurations via Django REST API."""
        import aiohttp
        
        # This would call your Django API endpoints
        # For now, return empty dict to fall through to model access
        return {}
    
    async def _fetch_via_models(self) -> Dict[int, ChainConfig]:
            """Fetch configurations via direct Django model access."""
            from asgiref.sync import sync_to_async
            
            @sync_to_async
            def get_chains_from_django():
                """Synchronous function to get chains from Django models."""
                try:
                    from trading.models import Chain, DEX
                    chains = Chain.objects.filter(is_active=True)
                    results = []
                    for chain in chains:
                        dexes = DEX.objects.filter(chain=chain, is_active=True)
                        results.append({
                            'chain_id': chain.chain_id,
                            'name': chain.name,
                            'rpc_url': chain.rpc_url,
                            'fallback_rpc_urls': chain.fallback_rpc_urls or [],
                            'block_time_seconds': chain.block_time_seconds,
                            'dexes': list(dexes.values(
                                'name', 'router_address', 'factory_address', 'fee_percentage'
                            ))
                        })
                    return results
                except Exception as e:
                    self.logger.error(f"Django model access error: {e}")
                    raise
            
            try:
                # Use sync_to_async to access Django models
                django_chains = await get_chains_from_django()
                configs = {}
                
                for chain_data in django_chains:
                    # Build RPC providers from chain data
                    rpc_providers = [
                        RPCProvider(
                            name=f"{chain_data['name'].lower().replace(' ', '_')}_primary",
                            url=chain_data['rpc_url'],
                            priority=1,
                            is_paid=False,
                        )
                    ]
                    
                    # Add fallback URLs if available
                    for i, fallback_url in enumerate(chain_data.get('fallback_rpc_urls', [])):
                        if fallback_url:
                            rpc_providers.append(
                                RPCProvider(
                                    name=f"{chain_data['name'].lower().replace(' ', '_')}_fallback_{i+1}",
                                    url=fallback_url,
                                    priority=i+2,
                                    is_paid=False,
                                )
                            )
                    
                    # Extract DEX information (get first available DEX for addresses)
                    uniswap_v3_factory = ''
                    uniswap_v3_router = ''
                    uniswap_v2_factory = ''
                    uniswap_v2_router = ''
                    weth_address = ''
                    usdc_address = ''
                    
                    for dex in chain_data['dexes']:
                        if 'v3' in dex['name'].lower():
                            uniswap_v3_factory = dex.get('factory_address', '')
                            uniswap_v3_router = dex.get('router_address', '')
                            # Extract WETH/USDC from metadata if available
                            metadata = dex.get('dex_metadata') or {}
                            if isinstance(metadata, dict):
                                weth_address = metadata.get('weth_address', weth_address)
                                usdc_address = metadata.get('usdc_address', usdc_address)
                        elif 'v2' in dex['name'].lower():
                            uniswap_v2_factory = dex.get('factory_address', '')
                            uniswap_v2_router = dex.get('router_address', '')
                            # Extract WETH/USDC from metadata if available
                            metadata = dex.get('dex_metadata') or {}
                            if isinstance(metadata, dict):
                                weth_address = metadata.get('weth_address', weth_address)
                                usdc_address = metadata.get('usdc_address', usdc_address)
                    
                    # Create ChainConfig
                    configs[chain_data['chain_id']] = ChainConfig(
                        chain_id=chain_data['chain_id'],
                        name=chain_data['name'],
                        rpc_providers=rpc_providers,
                        uniswap_v3_factory=uniswap_v3_factory,
                        uniswap_v3_router=uniswap_v3_router,
                        uniswap_v2_factory=uniswap_v2_factory,
                        uniswap_v2_router=uniswap_v2_router,
                        weth_address=weth_address,
                        usdc_address=usdc_address,
                        block_time_ms=chain_data['block_time_seconds'] * 1000,
                        confirmations_required=1 if chain_data['chain_id'] in [8453, 84532, 42161, 421614] else 2,
                    )
                
                self.logger.info(f"Successfully loaded {len(configs)} chain configurations from Django models")
                return configs
                
            except Exception as e:
                self.logger.error(f"Failed to fetch from Django models: {e}")
                raise

















    def _build_rpc_providers(self, chain) -> List[RPCProvider]:
        """Build RPC providers list from Django Chain model."""
        providers = []
        
        # Primary provider
        providers.append(RPCProvider(
            name=f"{chain.name}_primary",
            url=chain.rpc_url,
            priority=1,
            is_paid=True,  # Assume primary is paid
            timeout_seconds=10,
        ))
        
        # Fallback providers
        for i, fallback_url in enumerate(chain.fallback_rpc_urls):
            providers.append(RPCProvider(
                name=f"{chain.name}_fallback_{i+1}",
                url=fallback_url,
                priority=i + 2,  # Lower priority than primary
                is_paid=False,  # Assume fallbacks are public
                timeout_seconds=15,
            ))
        
        return providers
    
    def _extract_dex_addresses(self, dexes) -> Dict[str, str]:
        """Extract DEX addresses from Django DEX models."""
        addresses = {
            'uniswap_v3_factory': '',
            'uniswap_v3_router': '',
            'uniswap_v2_factory': '',
            'uniswap_v2_router': '',
            'weth_address': '',
            'usdc_address': '',
        }
        
        for dex in dexes:
            dex_name_lower = dex.name.lower()
            
            if 'uniswap' in dex_name_lower and 'v3' in dex_name_lower:
                addresses['uniswap_v3_factory'] = dex.factory_address
                addresses['uniswap_v3_router'] = dex.router_address
            elif 'uniswap' in dex_name_lower and 'v2' in dex_name_lower:
                addresses['uniswap_v2_factory'] = dex.factory_address
                addresses['uniswap_v2_router'] = dex.router_address
            
            # Extract token addresses from config if available
            config = getattr(dex, 'config', {})
            if isinstance(config, dict):
                addresses['weth_address'] = config.get('weth_address', addresses['weth_address'])
                addresses['usdc_address'] = config.get('usdc_address', addresses['usdc_address'])
        
        return addresses
    
    def _get_fallback_configs(self) -> Dict[int, ChainConfig]:
        """Get fallback hardcoded configurations."""
        self.logger.warning("Using fallback configurations - update Django models for production!")
        
        return {
            # Base (8453)
            8453: ChainConfig(
                chain_id=8453,
                name="Base",
                rpc_providers=[
                    RPCProvider(
                        name="base_alchemy",
                        url="https://base-mainnet.g.alchemy.com/v2/demo",
                        priority=1,
                        is_paid=True,
                    ),
                    RPCProvider(
                        name="base_public",
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
            ),
            # Ethereum (1)
            1: ChainConfig(
                chain_id=1,
                name="Ethereum",
                rpc_providers=[
                    RPCProvider(
                        name="ethereum_alchemy",
                        url="https://eth-mainnet.g.alchemy.com/v2/demo",
                        priority=1,
                        is_paid=True,
                    ),
                    RPCProvider(
                        name="ethereum_public",
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
            ),
        }
    
    def _serialize_chain_configs(self, configs: Dict[int, ChainConfig]) -> Dict:
        """Serialize chain configs for Redis storage."""
        serialized = {}
        
        for chain_id, config in configs.items():
            serialized[str(chain_id)] = {
                'chain_id': config.chain_id,
                'name': config.name,
                'rpc_providers': [
                    {
                        'name': p.name,
                        'url': p.url,
                        'websocket_url': p.websocket_url,
                        'priority': p.priority,
                        'is_paid': p.is_paid,
                        'timeout_seconds': p.timeout_seconds,
                    }
                    for p in config.rpc_providers
                ],
                'uniswap_v3_factory': config.uniswap_v3_factory,
                'uniswap_v3_router': config.uniswap_v3_router,
                'uniswap_v2_factory': config.uniswap_v2_factory,
                'uniswap_v2_router': config.uniswap_v2_router,
                'weth_address': config.weth_address,
                'usdc_address': config.usdc_address,
                'block_time_ms': config.block_time_ms,
                'confirmations_required': config.confirmations_required,
            }
        
        return serialized
    
    def _deserialize_chain_configs(self, data: Dict) -> Dict[int, ChainConfig]:
        """Deserialize chain configs from Redis storage."""
        configs = {}
        
        for chain_id_str, config_data in data.items():
            chain_id = int(chain_id_str)
            
            # Deserialize RPC providers
            rpc_providers = []
            for provider_data in config_data.get('rpc_providers', []):
                rpc_providers.append(RPCProvider(
                    name=provider_data['name'],
                    url=provider_data['url'],
                    websocket_url=provider_data.get('websocket_url'),
                    priority=provider_data.get('priority', 1),
                    is_paid=provider_data.get('is_paid', False),
                    timeout_seconds=provider_data.get('timeout_seconds', 10),
                ))
            
            # Create ChainConfig
            configs[chain_id] = ChainConfig(
                chain_id=config_data['chain_id'],
                name=config_data['name'],
                rpc_providers=rpc_providers,
                uniswap_v3_factory=config_data['uniswap_v3_factory'],
                uniswap_v3_router=config_data['uniswap_v3_router'],
                uniswap_v2_factory=config_data['uniswap_v2_factory'],
                uniswap_v2_router=config_data['uniswap_v2_router'],
                weth_address=config_data['weth_address'],
                usdc_address=config_data['usdc_address'],
                block_time_ms=config_data.get('block_time_ms', 12000),
                confirmations_required=config_data.get('confirmations_required', 1),
            )
        
        return configs


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def get_engine_chain_configs(redis_client: Optional[RedisClient] = None) -> Dict[int, ChainConfig]:
    """
    Get chain configurations for the engine from Django models.
    
    Args:
        redis_client: Optional Redis client for caching
        
    Returns:
        Dictionary of chain_id -> ChainConfig
    """
    bridge = ChainConfigBridge(redis_client)
    return await bridge.get_chain_configs()


async def get_engine_chain_config(
    chain_id: int, 
    redis_client: Optional[RedisClient] = None
) -> Optional[ChainConfig]:
    """
    Get configuration for a specific chain from Django models.
    
    Args:
        chain_id: Chain ID to get config for
        redis_client: Optional Redis client for caching
        
    Returns:
        ChainConfig or None if not found
    """
    bridge = ChainConfigBridge(redis_client)
    return await bridge.get_chain_config(chain_id)