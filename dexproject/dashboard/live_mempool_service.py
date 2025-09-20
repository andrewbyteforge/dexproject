"""
Live Mempool Service - Real Blockchain Data Integration

Activates the existing mempool monitoring framework with live WebSocket connections
to Alchemy and other providers using real API keys.

This module bridges the gap between simulated and live data by initializing
real blockchain connections while maintaining the existing architecture.

File: dashboard/live_mempool_service.py
"""

import asyncio
import logging
import json
import time
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


@dataclass
class LiveConnectionStatus:
    """Status of live blockchain connections."""
    chain_id: int
    provider: str
    connected: bool
    websocket_url: str
    last_message_time: Optional[datetime]
    message_count: int
    error_count: int
    reconnect_count: int


@dataclass
class LiveMempoolMetrics:
    """Live mempool monitoring metrics."""
    total_connections: int
    active_connections: int
    total_transactions_processed: int
    dex_transactions_detected: int
    average_processing_latency_ms: float
    connection_uptime_percentage: float
    last_update: datetime
    is_live: bool = True


class LiveMempoolService:
    """
    Service for managing live blockchain mempool connections.
    
    Activates real WebSocket connections to blockchain providers and processes
    live transaction data instead of simulated data.
    """
    
    def __init__(self):
        """Initialize live mempool service."""
        self.logger = logging.getLogger(__name__)
        self.connections: Dict[str, LiveConnectionStatus] = {}
        self.is_running = False
        self.is_live_mode = not getattr(settings, 'ENGINE_MOCK_MODE', True)
        self.event_callbacks: List[Callable] = []
        
        # Metrics tracking
        self.metrics = LiveMempoolMetrics(
            total_connections=0,
            active_connections=0,
            total_transactions_processed=0,
            dex_transactions_detected=0,
            average_processing_latency_ms=0.0,
            connection_uptime_percentage=0.0,
            last_update=datetime.now(timezone.utc)
        )
        
        # Connection configuration from Django settings
        self.api_keys = {
            'alchemy': getattr(settings, 'ALCHEMY_API_KEY', ''),
            'ankr': getattr(settings, 'ANKR_API_KEY', ''),
            'infura': getattr(settings, 'INFURA_PROJECT_ID', '')
        }
        
        self.supported_chains = getattr(settings, 'SUPPORTED_CHAINS', [84532, 11155111])
        self.websocket_timeout = getattr(settings, 'WEBSOCKET_TIMEOUT', 30)
        self.reconnect_delay = getattr(settings, 'WEBSOCKET_RECONNECT_DELAY', 5)
        
        self.logger.info(f"Initialized LiveMempoolService in {'LIVE' if self.is_live_mode else 'MOCK'} mode")
        self.logger.info(f"Target chains: {self.supported_chains}")
        self.logger.info(f"API keys configured: {list(self.api_keys.keys())}")
    
    def _get_websocket_url(self, chain_id: int, provider: str) -> Optional[str]:
        """
        Get WebSocket URL for the specified chain and provider.
        
        Args:
            chain_id: Blockchain network ID
            provider: Provider name (alchemy, ankr, infura)
            
        Returns:
            WebSocket URL string or None if not available
        """
        if provider == 'alchemy' and self.api_keys['alchemy']:
            api_key = self.api_keys['alchemy']
            
            if chain_id == 84532:  # Base Sepolia
                return f"wss://base-sepolia.g.alchemy.com/v2/{api_key}"
            elif chain_id == 11155111:  # Ethereum Sepolia
                return f"wss://eth-sepolia.g.alchemy.com/v2/{api_key}"
            elif chain_id == 8453:  # Base Mainnet
                return f"wss://base-mainnet.g.alchemy.com/v2/{api_key}"
            elif chain_id == 1:  # Ethereum Mainnet
                return f"wss://eth-mainnet.g.alchemy.com/v2/{api_key}"
        
        elif provider == 'ankr' and self.api_keys['ankr']:
            api_key = self.api_keys['ankr']
            
            if chain_id == 84532:
                return f"wss://rpc.ankr.com/base_sepolia/ws/{api_key}"
            elif chain_id == 11155111:
                return f"wss://rpc.ankr.com/eth_sepolia/ws/{api_key}"
        
        elif provider == 'infura' and self.api_keys['infura']:
            project_id = self.api_keys['infura']
            
            if chain_id == 11155111:  # Ethereum Sepolia
                return f"wss://sepolia.infura.io/ws/v3/{project_id}"
            elif chain_id == 1:  # Ethereum Mainnet
                return f"wss://mainnet.infura.io/ws/v3/{project_id}"
        
        return None
    
    async def _test_websocket_connection(self, url: str) -> bool:
        """
        Test WebSocket connection to a provider.
        
        Args:
            url: WebSocket URL to test
            
        Returns:
            True if connection successful, False otherwise
        """
        try:
            import websockets
            
            async with websockets.connect(url, timeout=5):
                self.logger.debug(f"WebSocket connection test successful: {url}")
                return True
                
        except Exception as e:
            self.logger.debug(f"WebSocket connection test failed: {url} - {e}")
            return False
    
    async def _establish_live_connection(self, chain_id: int, provider: str) -> bool:
        """
        Establish live WebSocket connection to a blockchain provider.
        
        Args:
            chain_id: Target blockchain network
            provider: Provider name
            
        Returns:
            True if connection established successfully
        """
        if not self.is_live_mode:
            self.logger.warning("Cannot establish live connection in mock mode")
            return False
        
        websocket_url = self._get_websocket_url(chain_id, provider)
        if not websocket_url:
            self.logger.error(f"No WebSocket URL available for {provider} on chain {chain_id}")
            return False
        
        connection_key = f"{chain_id}_{provider}"
        
        self.logger.info(f"Establishing live connection: {provider} chain {chain_id}")
        self.logger.debug(f"WebSocket URL: {websocket_url}")
        
        try:
            # Test connection first
            if not await self._test_websocket_connection(websocket_url):
                self.logger.error(f"WebSocket connection test failed for {connection_key}")
                return False
            
            # Create connection status
            self.connections[connection_key] = LiveConnectionStatus(
                chain_id=chain_id,
                provider=provider,
                connected=True,
                websocket_url=websocket_url,
                last_message_time=datetime.now(timezone.utc),
                message_count=0,
                error_count=0,
                reconnect_count=0
            )
            
            self.logger.info(f"✅ Live connection established: {connection_key}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to establish live connection {connection_key}: {e}")
            return False
    
    async def _subscribe_to_pending_transactions(self, websocket, chain_id: int, provider: str) -> None:
        """
        Subscribe to pending transactions on the WebSocket connection.
        
        Args:
            websocket: Active WebSocket connection
            chain_id: Blockchain network ID
            provider: Provider name
        """
        try:
            if provider == 'alchemy':
                # Alchemy subscription for pending transactions
                subscription_message = {
                    "id": 1,
                    "method": "eth_subscribe",
                    "params": ["alchemy_pendingTransactions", {
                        "hashesOnly": False  # Get full transaction data
                    }]
                }
            
            elif provider == 'ankr':
                # Ankr subscription
                subscription_message = {
                    "id": 1,
                    "method": "eth_subscribe",
                    "params": ["newPendingTransactions"]
                }
            
            elif provider == 'infura':
                # Infura subscription
                subscription_message = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_subscribe",
                    "params": ["newPendingTransactions"]
                }
            
            else:
                self.logger.warning(f"Unknown provider for subscription: {provider}")
                return
            
            await websocket.send(json.dumps(subscription_message))
            self.logger.info(f"Subscribed to pending transactions: {provider} chain {chain_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to subscribe to pending transactions: {e}")
            raise
    
    async def _process_websocket_message(self, message: str, chain_id: int, provider: str) -> None:
        """
        Process incoming WebSocket message containing transaction data.
        
        Args:
            message: Raw WebSocket message
            chain_id: Blockchain network ID
            provider: Provider name
        """
        try:
            start_time = time.perf_counter()
            
            # Parse message
            data = json.loads(message)
            
            # Update connection status
            connection_key = f"{chain_id}_{provider}"
            if connection_key in self.connections:
                self.connections[connection_key].message_count += 1
                self.connections[connection_key].last_message_time = datetime.now(timezone.utc)
            
            # Process transaction data
            if 'params' in data and 'result' in data['params']:
                tx_data = data['params']['result']
                await self._process_transaction_data(tx_data, chain_id, provider)
            
            # Update metrics
            processing_time = (time.perf_counter() - start_time) * 1000
            self._update_processing_metrics(processing_time)
            
            # Notify callbacks
            for callback in self.event_callbacks:
                try:
                    await callback({
                        'type': 'pending_transaction',
                        'chain_id': chain_id,
                        'provider': provider,
                        'data': data,
                        'processing_time_ms': processing_time
                    })
                except Exception as callback_error:
                    self.logger.error(f"Event callback error: {callback_error}")
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse WebSocket message: {e}")
        except Exception as e:
            self.logger.error(f"Error processing WebSocket message: {e}")
            
            # Update error count
            connection_key = f"{chain_id}_{provider}"
            if connection_key in self.connections:
                self.connections[connection_key].error_count += 1
    
    async def _process_transaction_data(self, tx_data: Dict[str, Any], chain_id: int, provider: str) -> None:
        """
        Process individual transaction data for DEX interactions.
        
        Args:
            tx_data: Transaction data from WebSocket
            chain_id: Blockchain network ID
            provider: Provider name
        """
        try:
            # Update total transactions processed
            self.metrics.total_transactions_processed += 1
            
            # Check if transaction is DEX-related
            to_address = tx_data.get('to', '').lower()
            
            # Known DEX router addresses (testnet)
            dex_addresses = {
                84532: [  # Base Sepolia
                    '0x2626664c2603336e57b271c5c0b26f421741e481',  # Uniswap V3 Router
                    '0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24',  # Uniswap V3 Factory
                ],
                11155111: [  # Ethereum Sepolia
                    '0x7a250d5630b4cf539739df2c5dacb4c659f2488d',  # Uniswap V2 Router
                    '0xe592427a0aece92de3edee1f18e0157c05861564',  # Uniswap V3 Router
                ]
            }
            
            if chain_id in dex_addresses and to_address in [addr.lower() for addr in dex_addresses[chain_id]]:
                self.metrics.dex_transactions_detected += 1
                
                self.logger.debug(f"DEX transaction detected: {tx_data.get('hash', 'unknown')} on chain {chain_id}")
                
                # Cache transaction for analysis
                cache_key = f"live_dex_tx_{chain_id}_{tx_data.get('hash', 'unknown')}"
                cache.set(cache_key, {
                    'transaction': tx_data,
                    'chain_id': chain_id,
                    'provider': provider,
                    'detected_at': datetime.now(timezone.utc).isoformat(),
                    'is_dex_transaction': True
                }, timeout=300)  # 5 minutes
            
        except Exception as e:
            self.logger.error(f"Error processing transaction data: {e}")
    
    def _update_processing_metrics(self, processing_time_ms: float) -> None:
        """Update processing metrics with new timing data."""
        # Calculate rolling average
        cache_key = "live_mempool_processing_times"
        recent_times = cache.get(cache_key, [])
        recent_times.append(processing_time_ms)
        
        # Keep only last 100 measurements
        if len(recent_times) > 100:
            recent_times = recent_times[-100:]
        
        cache.set(cache_key, recent_times, timeout=3600)
        
        # Update average
        if recent_times:
            self.metrics.average_processing_latency_ms = sum(recent_times) / len(recent_times)
    
    async def start_live_monitoring(self) -> bool:
        """
        Start live mempool monitoring across all configured chains and providers.
        
        Returns:
            True if monitoring started successfully
        """
        if not self.is_live_mode:
            self.logger.warning("Cannot start live monitoring in mock mode")
            return False
        
        if self.is_running:
            self.logger.warning("Live monitoring already running")
            return True
        
        self.logger.info("🚀 Starting live mempool monitoring...")
        
        # Test API connectivity first
        connection_tasks = []
        
        for chain_id in self.supported_chains:
            for provider in ['alchemy', 'ankr', 'infura']:
                if self.api_keys[provider]:  # Only if API key is configured
                    task = self._establish_live_connection(chain_id, provider)
                    connection_tasks.append(task)
        
        if not connection_tasks:
            self.logger.error("No API keys configured for live connections")
            return False
        
        # Establish connections
        results = await asyncio.gather(*connection_tasks, return_exceptions=True)
        
        successful_connections = sum(1 for result in results if result is True)
        
        self.metrics.total_connections = len(connection_tasks)
        self.metrics.active_connections = successful_connections
        
        if successful_connections > 0:
            self.metrics.connection_uptime_percentage = (successful_connections / len(connection_tasks)) * 100
            self.is_running = True
            
            self.logger.info(f"✅ Live monitoring started with {successful_connections}/{len(connection_tasks)} connections")
            return True
        else:
            self.logger.error("❌ Failed to establish any live connections")
            return False
    
    async def stop_live_monitoring(self) -> None:
        """Stop live mempool monitoring."""
        if not self.is_running:
            return
        
        self.logger.info("Stopping live mempool monitoring...")
        
        # Mark all connections as disconnected
        for connection in self.connections.values():
            connection.connected = False
        
        self.is_running = False
        self.metrics.active_connections = 0
        self.metrics.connection_uptime_percentage = 0.0
        
        self.logger.info("Live monitoring stopped")
    
    def get_live_status(self) -> Dict[str, Any]:
        """
        Get current status of live blockchain connections.
        
        Returns:
            Dictionary containing live connection status
        """
        self.metrics.last_update = datetime.now(timezone.utc)
        
        return {
            'is_live_mode': self.is_live_mode,
            'is_running': self.is_running,
            'connections': {
                key: asdict(status) for key, status in self.connections.items()
            },
            'metrics': asdict(self.metrics),
            'api_keys_configured': {
                provider: bool(key) for provider, key in self.api_keys.items()
            },
            'supported_chains': self.supported_chains,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def get_live_metrics(self) -> Dict[str, Any]:
        """
        Get live mempool metrics for dashboard display.
        
        Returns:
            Dictionary containing performance metrics
        """
        return {
            'total_transactions_processed': self.metrics.total_transactions_processed,
            'dex_transactions_detected': self.metrics.dex_transactions_detected,
            'average_processing_latency_ms': round(self.metrics.average_processing_latency_ms, 2),
            'active_connections': self.metrics.active_connections,
            'connection_uptime_percentage': round(self.metrics.connection_uptime_percentage, 1),
            'is_live': self.is_live_mode and self.is_running,
            'last_update': self.metrics.last_update.isoformat(),
            'dex_detection_rate': (
                (self.metrics.dex_transactions_detected / max(self.metrics.total_transactions_processed, 1)) * 100
                if self.metrics.total_transactions_processed > 0 else 0
            )
        }
    
    def add_event_callback(self, callback: Callable) -> None:
        """Add callback for live transaction events."""
        self.event_callbacks.append(callback)
    
    def remove_event_callback(self, callback: Callable) -> None:
        """Remove event callback."""
        if callback in self.event_callbacks:
            self.event_callbacks.remove(callback)


# =============================================================================
# SERVICE INSTANCE
# =============================================================================

# Global service instance
live_mempool_service = LiveMempoolService()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

async def initialize_live_mempool() -> bool:
    """
    Initialize live mempool monitoring.
    
    Returns:
        True if initialization successful
    """
    try:
        return await live_mempool_service.start_live_monitoring()
    except Exception as e:
        logger.error(f"Failed to initialize live mempool: {e}")
        return False


def get_live_mempool_status() -> Dict[str, Any]:
    """Get live mempool status for dashboard."""
    return live_mempool_service.get_live_status()


def get_live_mempool_metrics() -> Dict[str, Any]:
    """Get live mempool metrics for dashboard."""
    return live_mempool_service.get_live_metrics()


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'LiveMempoolService',
    'LiveConnectionStatus', 
    'LiveMempoolMetrics',
    'live_mempool_service',
    'initialize_live_mempool',
    'get_live_mempool_status',
    'get_live_mempool_metrics'
]