"""
HTTP Polling Live Service - Windows Compatible Version (No Unicode Issues)

This version replaces all emoji characters with ASCII alternatives
to avoid Windows console encoding issues.

File: dashboard/http_live_service.py
"""

import logging
import json
import time
import asyncio
import aiohttp
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class HTTPLiveService:
    """
    HTTP polling-based live blockchain data service.
    
    Uses HTTP RPC calls to get live blockchain data instead of WebSocket streams.
    More reliable than WebSocket in Django environments with fewer dependencies.
    """
    
    def __init__(self):
        """Initialize HTTP live service with Windows-compatible logging."""
        self.logger = logging.getLogger(__name__)
        
        # Use same configuration pattern as engine_service.py
        mock_mode = getattr(settings, 'ENGINE_MOCK_MODE', True)
        force_mock_data = getattr(settings, 'FORCE_MOCK_DATA', False)
        self.is_live_mode = not mock_mode and not force_mock_data
        
        self.is_initialized = False
        self.is_polling = False
        
        # Connection tracking
        self.connections_active = 0
        self.total_requests = 0
        self.successful_requests = 0
        self.total_transactions = 0
        self.dex_transactions = 0
        self.last_update = datetime.now(timezone.utc)
        self.connection_errors = []
        
        # Polling configuration
        self.poll_interval = 5  # Poll every 5 seconds
        self.max_blocks_per_poll = 10  # Check last 10 blocks
        
        # API endpoints
        self.endpoints = self._setup_endpoints()
        
        self.logger.info(f"HTTP live service initialized - Live mode: {self.is_live_mode}")
        self.logger.info(f"Configuration: ENGINE_MOCK_MODE={mock_mode}, FORCE_MOCK_DATA={force_mock_data}")
        if self.endpoints:
            self.logger.info(f"Available endpoints: {list(self.endpoints.keys())}")
        else:
            self.logger.warning("[WARNING] No valid RPC endpoints configured - check API keys")
    
    def _setup_endpoints(self) -> Dict[str, str]:
        """
        Setup HTTP RPC endpoints for each chain and provider.
        
        Uses correct environment variable names and validates API keys.
        """
        endpoints = {}
        
        # Ethereum Sepolia endpoints
        eth_alchemy_key = getattr(settings, 'ETH_ALCHEMY_API_KEY', None)
        if eth_alchemy_key:
            endpoints['eth_sepolia_alchemy'] = f"https://eth-sepolia.g.alchemy.com/v2/{eth_alchemy_key}"
            self.logger.debug("Configured Ethereum Sepolia Alchemy endpoint")
        
        eth_infura_key = getattr(settings, 'ETH_INFURA_PROJECT_ID', None)
        if eth_infura_key:
            endpoints['eth_sepolia_infura'] = f"https://sepolia.infura.io/v3/{eth_infura_key}"
            self.logger.debug("Configured Ethereum Sepolia Infura endpoint")
        
        eth_ankr_key = getattr(settings, 'ETH_ANKR_API_KEY', None)
        if eth_ankr_key:
            endpoints['eth_sepolia_ankr'] = f"https://rpc.ankr.com/eth_sepolia/{eth_ankr_key}"
            self.logger.debug("Configured Ethereum Sepolia Ankr endpoint")
        
        # Public Ethereum Sepolia endpoint (no key needed)
        endpoints['eth_sepolia_public'] = "https://rpc.sepolia.org"
        
        # Base Sepolia endpoints
        base_alchemy_key = getattr(settings, 'BASE_ALCHEMY_API_KEY', None)
        if base_alchemy_key:
            endpoints['base_sepolia_alchemy'] = f"https://base-sepolia.g.alchemy.com/v2/{base_alchemy_key}"
            self.logger.debug("Configured Base Sepolia Alchemy endpoint")
        
        base_ankr_key = getattr(settings, 'BASE_ANKR_API_KEY', None)
        if base_ankr_key:
            endpoints['base_sepolia_ankr'] = f"https://rpc.ankr.com/base_sepolia/{base_ankr_key}"
            self.logger.debug("Configured Base Sepolia Ankr endpoint")
        
        # Public Base Sepolia endpoint
        endpoints['base_sepolia_public'] = "https://sepolia.base.org"
        
        return endpoints
    
    async def _make_rpc_call(self, endpoint_url: str, method: str, params: list = None) -> Any:
        """Make an RPC call to the specified endpoint."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or [],
            "id": 1
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    endpoint_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'error' in data:
                            raise Exception(f"RPC error: {data['error']}")
                        return data.get('result')
                    else:
                        text = await response.text()
                        raise Exception(f"HTTP {response.status}: {text[:200]}")
        except asyncio.TimeoutError:
            raise Exception("Request timeout")
        except Exception as e:
            raise Exception(f"RPC call failed: {e}")
    
    async def _test_endpoint(self, endpoint_name: str) -> bool:
        """Test if an endpoint is working by getting the latest block."""
        try:
            endpoint_url = self.endpoints.get(endpoint_name)
            if not endpoint_url:
                return False
            
            block_number = await self._make_rpc_call(
                endpoint_url,
                "eth_blockNumber"
            )
            
            if block_number:
                block_number = int(block_number, 16)
                self.logger.debug(f"[OK] {endpoint_name}: Block #{block_number}")
                return True
            
            return False
            
        except Exception as e:
            error_msg = f"{endpoint_name}: {str(e)}"
            self.connection_errors.append(error_msg)
            self.logger.debug(f"[FAILED] {error_msg}")
            return False
    
    async def _poll_endpoint(self, endpoint_name: str, endpoint_url: str) -> Dict[str, Any]:
        """Poll an endpoint for recent transactions."""
        try:
            # Get latest block number
            latest_block_hex = await self._make_rpc_call(endpoint_url, "eth_blockNumber")
            latest_block = int(latest_block_hex, 16)
            
            # Get recent blocks
            transactions = []
            blocks_to_check = min(self.max_blocks_per_poll, 3)  # Start with fewer blocks
            
            for i in range(blocks_to_check):
                block_num = latest_block - i
                block_hex = hex(block_num)
                
                try:
                    block = await self._make_rpc_call(
                        endpoint_url,
                        "eth_getBlockByNumber",
                        [block_hex, True]  # Include full transactions
                    )
                    
                    if block and 'transactions' in block:
                        transactions.extend(block['transactions'])
                        
                except Exception as e:
                    self.logger.debug(f"Error fetching block {block_num}: {e}")
            
            # Process transactions
            dex_txs = self._filter_dex_transactions(transactions)
            
            # Update metrics
            self.total_requests += 1
            self.successful_requests += 1
            self.total_transactions += len(transactions)
            self.dex_transactions += len(dex_txs)
            
            return {
                'endpoint': endpoint_name,
                'latest_block': latest_block,
                'transactions_found': len(transactions),
                'dex_transactions': len(dex_txs),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            self.logger.debug(f"Polling error for {endpoint_name}: {e}")
            return {}
    
    def _filter_dex_transactions(self, transactions: list) -> list:
        """Filter transactions for DEX activity."""
        dex_txs = []
        
        # Known DEX router addresses (lowercase)
        dex_routers = {
            '0x2626664c2603336e57b271c5c0b26f421741e481',  # Base Uniswap V3
            '0x7a250d5630b4cf539739df2c5dacb4c659f2488d',  # Uniswap V2
            '0xe592427a0aece92de3edee1f18e0157c05861564',  # Uniswap V3
        }
        
        for tx in transactions:
            if tx and isinstance(tx, dict):
                to_address = tx.get('to', '').lower()
                if to_address in dex_routers:
                    dex_txs.append(tx)
        
        return dex_txs
    
    async def initialize_live_monitoring(self) -> bool:
        """
        Initialize the live monitoring service.
        
        Returns:
            True if initialization successful
        """
        if not self.is_live_mode:
            self.logger.info("[INFO] Live monitoring disabled - using mock mode")
            return False
        
        if not self.endpoints:
            self.logger.error("[ERROR] No RPC endpoints configured")
            return False
        
        self.logger.info(f"[INIT] Testing {len(self.endpoints)} endpoints...")
        
        # Test all endpoints
        working_endpoints = []
        for endpoint_name in self.endpoints:
            if await self._test_endpoint(endpoint_name):
                working_endpoints.append(endpoint_name)
                self.logger.info(f"[OK] {endpoint_name}: Connected")
            else:
                self.logger.warning(f"[X] {endpoint_name}: Failed")
        
        if working_endpoints:
            self.connections_active = len(working_endpoints)
            self.is_initialized = True
            self.logger.info(f"[SUCCESS] Live monitoring initialized with {len(working_endpoints)} working endpoints")
            self.logger.info(f"Active endpoints: {', '.join(working_endpoints)}")
            
            # Start background polling
            asyncio.create_task(self._background_polling(working_endpoints))
            self.logger.info("[POLLING] Starting background polling...")
            
            return True
        else:
            self.logger.error("[ERROR] No working endpoints found")
            return False
    
    async def _background_polling(self, working_endpoints: list):
        """Background task to poll endpoints for live data."""
        self.is_polling = True
        
        while self.is_polling:
            try:
                # Poll each working endpoint
                for endpoint_name in working_endpoints:
                    endpoint_url = self.endpoints[endpoint_name]
                    result = await self._poll_endpoint(endpoint_name, endpoint_url)
                    
                    if result:
                        # Store result in cache
                        cache_key = f"live_data:{endpoint_name}"
                        cache.set(cache_key, result, timeout=30)
                        
                        self.last_update = datetime.now(timezone.utc)
                
                # Wait before next poll
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                self.logger.error(f"[ERROR] Polling error: {e}")
                await asyncio.sleep(self.poll_interval)
    
    def get_live_status(self) -> Dict[str, Any]:
        """Get current status of the live service."""
        return {
            'is_running': self.is_initialized and self.is_polling,
            'is_live_mode': self.is_live_mode,
            'connections': {
                'active': self.connections_active,
                'endpoints': list(self.endpoints.keys()) if self.endpoints else []
            },
            'metrics': {
                'total_requests': self.total_requests,
                'successful_requests': self.successful_requests,
                'total_transactions': self.total_transactions,
                'dex_transactions': self.dex_transactions,
                'active_connections': self.connections_active,
                'last_update': self.last_update.isoformat() if self.last_update else None
            },
            'connection_errors': self.connection_errors[-5:] if self.connection_errors else []
        }
    
    def stop(self):
        """Stop the live monitoring service."""
        self.is_polling = False
        self.is_initialized = False
        self.logger.info("[STOP] Live monitoring stopped")


# Create singleton instance
http_live_service = HTTPLiveService()

# Export for use by other modules
__all__ = ['HTTPLiveService', 'http_live_service']