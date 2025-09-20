"""
HTTP Polling Live Service - WebSocket Alternative

Since WebSocket connections are failing in the Django environment due to library
compatibility issues, this service uses HTTP polling to get live blockchain data.
This provides real blockchain data without WebSocket complexity.

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
        """Initialize HTTP live service."""
        self.logger = logging.getLogger(__name__)
        self.is_live_mode = not getattr(settings, 'ENGINE_MOCK_MODE', True)
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
        if self.endpoints:
            self.logger.info(f"Available endpoints: {list(self.endpoints.keys())}")
    
    def _setup_endpoints(self) -> Dict[str, str]:
        """Setup HTTP RPC endpoints for each chain and provider."""
        endpoints = {}
        
        # Alchemy endpoints
        alchemy_key = getattr(settings, 'ALCHEMY_API_KEY', '')
        if alchemy_key:
            endpoints['eth_sepolia_alchemy'] = f"https://eth-sepolia.g.alchemy.com/v2/{alchemy_key}"
            
            # Use BASE_API_KEY if available, otherwise use main Alchemy key
            base_key = getattr(settings, 'BASE_API_KEY', alchemy_key)
            endpoints['base_sepolia_alchemy'] = f"https://base-sepolia.g.alchemy.com/v2/{base_key}"
        
        # Infura endpoints
        infura_id = getattr(settings, 'INFURA_PROJECT_ID', '')
        if infura_id:
            endpoints['eth_sepolia_infura'] = f"https://sepolia.infura.io/v3/{infura_id}"
        
        return endpoints
    
    async def _make_rpc_call(self, endpoint: str, method: str, params: list) -> Optional[Dict]:
        """Make an RPC call to a blockchain endpoint."""
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": int(time.time())
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    endpoint,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    self.total_requests += 1
                    
                    if response.status == 200:
                        result = await response.json()
                        self.successful_requests += 1
                        return result
                    else:
                        self.logger.warning(f"RPC call failed: {response.status}")
                        return None
                        
        except Exception as e:
            error_msg = f"RPC call error: {e}"
            self.logger.debug(error_msg)
            self.connection_errors.append(error_msg)
            return None
    
    async def _get_latest_block_number(self, endpoint: str) -> Optional[int]:
        """Get the latest block number from a blockchain."""
        try:
            result = await self._make_rpc_call(endpoint, "eth_blockNumber", [])
            if result and 'result' in result:
                # Convert hex to int
                block_number = int(result['result'], 16)
                return block_number
        except Exception as e:
            self.logger.debug(f"Failed to get latest block: {e}")
        
        return None
    
    async def _get_block_transactions(self, endpoint: str, block_number: int) -> list:
        """Get transactions from a specific block."""
        try:
            # Convert to hex
            block_hex = hex(block_number)
            
            result = await self._make_rpc_call(
                endpoint, 
                "eth_getBlockByNumber", 
                [block_hex, True]  # True to get full transaction objects
            )
            
            if result and 'result' in result and result['result']:
                block_data = result['result']
                transactions = block_data.get('transactions', [])
                
                # Filter for DEX transactions
                dex_transactions = []
                for tx in transactions:
                    if self._is_dex_transaction(tx):
                        dex_transactions.append(tx)
                        self.dex_transactions += 1
                    
                    self.total_transactions += 1
                
                return dex_transactions
                
        except Exception as e:
            self.logger.debug(f"Failed to get block transactions: {e}")
        
        return []
    
    def _is_dex_transaction(self, tx: Dict) -> bool:
        """Check if a transaction is DEX-related."""
        try:
            to_address = tx.get('to', '').lower()
            
            # Known DEX addresses (testnet)
            dex_addresses = {
                # Base Sepolia
                '0x2626664c2603336e57b271c5c0b26f421741e481',  # Uniswap V3 Router
                '0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24',  # Uniswap V3 Factory
                # Ethereum Sepolia  
                '0x7a250d5630b4cf539739df2c5dacb4c659f2488d',  # Uniswap V2 Router
                '0xe592427a0aece92de3edee1f18e0157c05861564',  # Uniswap V3 Router
            }
            
            return to_address in dex_addresses
            
        except Exception:
            return False
    
    async def _poll_endpoints(self):
        """Poll all endpoints for new data."""
        if not self.is_polling:
            return
        
        active_connections = 0
        
        for endpoint_name, endpoint_url in self.endpoints.items():
            try:
                # Get latest block
                latest_block = await self._get_latest_block_number(endpoint_url)
                
                if latest_block:
                    active_connections += 1
                    
                    # Check last few blocks for new transactions
                    start_block = max(0, latest_block - self.max_blocks_per_poll)
                    
                    for block_num in range(start_block, latest_block + 1):
                        dex_txs = await self._get_block_transactions(endpoint_url, block_num)
                        
                        if dex_txs:
                            self.logger.debug(f"Found {len(dex_txs)} DEX transactions in block {block_num}")
                            
                            # Cache transactions for analysis
                            for tx in dex_txs:
                                cache_key = f"live_tx_{endpoint_name}_{tx.get('hash', 'unknown')}"
                                cache.set(cache_key, {
                                    'transaction': tx,
                                    'endpoint': endpoint_name,
                                    'block_number': block_num,
                                    'detected_at': datetime.now(timezone.utc).isoformat(),
                                    'is_dex_transaction': True
                                }, timeout=300)
                
            except Exception as e:
                self.logger.debug(f"Error polling {endpoint_name}: {e}")
        
        self.connections_active = active_connections
        self.last_update = datetime.now(timezone.utc)
    
    async def start_polling(self):
        """Start the HTTP polling loop."""
        if not self.is_live_mode:
            self.logger.info("HTTP polling disabled - using mock mode")
            return False
        
        if not self.endpoints:
            self.logger.error("No endpoints configured for HTTP polling")
            return False
        
        self.is_polling = True
        self.logger.info(f"Starting HTTP polling with {len(self.endpoints)} endpoints")
        
        # Start background polling task
        asyncio.create_task(self._polling_loop())
        return True
    
    async def _polling_loop(self):
        """Background polling loop."""
        while self.is_polling:
            try:
                await self._poll_endpoints()
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                self.logger.error(f"Polling loop error: {e}")
                await asyncio.sleep(self.poll_interval)
    
    def stop_polling(self):
        """Stop the HTTP polling."""
        self.is_polling = False
        self.logger.info("HTTP polling stopped")
    
    async def initialize_live_monitoring(self) -> bool:
        """Initialize live monitoring with HTTP polling."""
        if not self.is_live_mode:
            self.logger.info("Live monitoring disabled - using mock mode")
            return False
        
        try:
            self.logger.info("Initializing HTTP-based live monitoring...")
            self.connection_errors = []
            
            # Test endpoints
            working_endpoints = 0
            for endpoint_name, endpoint_url in self.endpoints.items():
                try:
                    latest_block = await self._get_latest_block_number(endpoint_url)
                    if latest_block:
                        working_endpoints += 1
                        self.logger.info(f"✅ {endpoint_name}: Latest block {latest_block}")
                    else:
                        self.logger.warning(f"❌ {endpoint_name}: No response")
                except Exception as e:
                    self.logger.warning(f"❌ {endpoint_name}: {e}")
            
            if working_endpoints > 0:
                self.connections_active = working_endpoints
                self.is_initialized = True
                
                # Start polling
                await self.start_polling()
                
                self.logger.info(f"HTTP live monitoring initialized with {working_endpoints} endpoints")
                return True
            else:
                self.logger.error("No working endpoints found for HTTP polling")
                return False
                
        except Exception as e:
            error_msg = f"Failed to initialize HTTP live monitoring: {e}"
            self.logger.error(error_msg)
            self.connection_errors.append(error_msg)
            return False
    
    def get_live_status(self) -> Dict[str, Any]:
        """Get live data status."""
        success_rate = (self.successful_requests / max(self.total_requests, 1)) * 100
        
        return {
            'is_live_mode': self.is_live_mode,
            'is_running': self.is_initialized and self.is_live_mode and self.is_polling,
            'connections': {},
            'metrics': {
                'total_connections': len(self.endpoints),
                'active_connections': self.connections_active,
                'connection_uptime_percentage': success_rate,
                'total_transactions_processed': self.total_transactions,
                'dex_transactions_detected': self.dex_transactions,
                'total_requests': self.total_requests,
                'successful_requests': self.successful_requests,
                'success_rate': success_rate
            },
            'api_keys_configured': {
                'alchemy': bool(getattr(settings, 'ALCHEMY_API_KEY', '')),
                'infura': bool(getattr(settings, 'INFURA_PROJECT_ID', ''))
            },
            'supported_chains': getattr(settings, 'SUPPORTED_CHAINS', [84532, 11155111]),
            'connection_errors': self.connection_errors[-5:] if self.connection_errors else [],
            'poll_interval': self.poll_interval,
            'method': 'HTTP_POLLING',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def get_live_metrics(self) -> Dict[str, Any]:
        """Get live mempool metrics."""
        success_rate = (self.successful_requests / max(self.total_requests, 1)) * 100
        
        return {
            'total_transactions_processed': self.total_transactions,
            'dex_transactions_detected': self.dex_transactions,
            'average_processing_latency_ms': 5000,  # 5 second polling interval
            'active_connections': self.connections_active,
            'connection_uptime_percentage': success_rate,
            'is_live': self.is_live_mode and self.is_initialized and self.is_polling,
            'last_update': self.last_update.isoformat(),
            'dex_detection_rate': (
                (self.dex_transactions / max(self.total_transactions, 1)) * 100
                if self.total_transactions > 0 else 0
            ),
            'connection_errors_count': len(self.connection_errors),
            'method': 'HTTP_POLLING',
            'poll_interval_seconds': self.poll_interval
        }
    
    def is_ready(self) -> bool:
        """Check if service is ready for use."""
        return self.is_initialized or not self.is_live_mode


# Global service instance
http_live_service = HTTPLiveService()


# Helper functions  
def get_live_mempool_status() -> Dict[str, Any]:
    """Get live mempool status via HTTP polling."""
    return http_live_service.get_live_status()


def get_live_mempool_metrics() -> Dict[str, Any]:
    """Get live mempool metrics via HTTP polling."""
    return http_live_service.get_live_metrics()


async def initialize_live_mempool() -> bool:
    """Initialize live mempool monitoring via HTTP polling."""
    return await http_live_service.initialize_live_monitoring()


def is_live_data_available() -> bool:
    """Check if live data is available via HTTP polling."""
    return http_live_service.is_live_mode and http_live_service.is_ready()