"""
Real-time mempool monitoring via WebSocket connections to Alchemy/Ankr.

This module provides high-performance mempool monitoring capabilities for the Fast Lane,
streaming pending transactions in real-time for immediate analysis and execution.
Critical for sub-500ms execution requirements.

Path: engine/mempool/monitor.py
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Callable, Any
from dataclasses import dataclass, field

import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from web3 import Web3

from shared.schemas import ChainType
from engine.provider_manager import ProviderManager


logger = logging.getLogger(__name__)


class MempoolEventType(Enum):
    """Types of mempool events we monitor."""
    PENDING_TRANSACTION = "pending_transaction"
    CONFIRMED_TRANSACTION = "confirmed_transaction"
    DROPPED_TRANSACTION = "dropped_transaction"
    REPLACED_TRANSACTION = "replaced_transaction"


@dataclass
class MempoolTransaction:
    """
    Represents a pending transaction from the mempool.
    Optimized for fast processing and minimal memory usage.
    """
    hash: str
    from_address: str
    to_address: Optional[str]
    value: int  # Wei amount
    gas_price: int  # Wei per gas
    gas_limit: int
    nonce: int
    input_data: str
    timestamp: float
    chain_id: int
    
    # Fast Lane analysis fields (populated by analyzer)
    is_dex_transaction: Optional[bool] = None
    target_token_address: Optional[str] = None
    trade_type: Optional[str] = None  # 'buy', 'sell', 'add_liquidity', 'remove_liquidity'
    estimated_impact: Optional[float] = None
    risk_score: Optional[float] = None
    
    def age_seconds(self) -> float:
        """Get age of transaction in seconds."""
        return time.time() - self.timestamp
    
    def is_high_value(self, threshold_eth: float = 1.0) -> bool:
        """Check if transaction value exceeds threshold."""
        return self.value / 1e18 >= threshold_eth
    
    def is_high_gas(self, threshold_gwei: float = 50.0) -> bool:
        """Check if gas price exceeds threshold."""
        return self.gas_price / 1e9 >= threshold_gwei


@dataclass
class MempoolConfig:
    """Configuration for mempool monitoring."""
    
    # WebSocket endpoints by chain
    websocket_endpoints: Dict[int, List[str]] = field(default_factory=dict)
    
    # Filtering configuration
    min_value_eth: float = 0.01  # Minimum transaction value to track
    min_gas_gwei: float = 10.0   # Minimum gas price to track
    max_age_seconds: float = 300.0  # Maximum age before dropping from cache
    
    # Performance configuration
    max_concurrent_connections: int = 10
    connection_timeout_seconds: float = 30.0
    heartbeat_interval_seconds: float = 30.0
    
    # DEX-specific filtering
    track_dex_transactions_only: bool = True
    known_router_addresses: Set[str] = field(default_factory=set)
    known_factory_addresses: Set[str] = field(default_factory=set)
    
    # Fast Lane optimization
    enable_pre_filtering: bool = True
    max_pending_transactions: int = 10000  # Memory limit


class MempoolMonitor:
    """
    High-performance mempool monitor for Fast Lane execution.
    
    Streams pending transactions from multiple providers with automatic failover,
    pre-filtering, and real-time analysis integration.
    """
    
    def __init__(
        self,
        config: MempoolConfig,
        provider_manager: ProviderManager,
        event_callback: Optional[Callable[[MempoolEventType, MempoolTransaction], None]] = None
    ):
        """
        Initialize mempool monitor.
        
        Args:
            config: Mempool monitoring configuration
            provider_manager: Provider manager for failover support
            event_callback: Optional callback for mempool events
        """
        self.config = config
        self.provider_manager = provider_manager
        self.event_callback = event_callback
        
        # Connection management
        self.active_connections: Dict[int, websockets.WebSocketServerProtocol] = {}
        self.connection_tasks: Dict[int, asyncio.Task] = {}
        self.is_running = False
        
        # Transaction tracking
        self.pending_transactions: Dict[str, MempoolTransaction] = {}
        self.transaction_lock = asyncio.Lock()
        
        # Performance metrics
        self.stats = {
            'total_transactions_seen': 0,
            'transactions_filtered_out': 0,
            'transactions_processed': 0,
            'connection_drops': 0,
            'reconnections': 0,
            'last_transaction_time': None,
        }
        
        # Initialize WebSocket endpoints from provider manager
        self._initialize_websocket_endpoints()
        
        logger.info(f"MempoolMonitor initialized for {len(self.config.websocket_endpoints)} chains")
    
    def _initialize_websocket_endpoints(self) -> None:
        """Initialize WebSocket endpoints from provider configurations."""
        for chain_id, chain_config in self.provider_manager.chain_configs.items():
            endpoints = []
            
            for provider in chain_config.rpc_providers:
                if provider.websocket_url:
                    endpoints.append(provider.websocket_url)
                else:
                    # Generate WebSocket URL from HTTP URL for Alchemy/Ankr
                    ws_url = self._http_to_websocket_url(provider.url)
                    if ws_url:
                        endpoints.append(ws_url)
            
            if endpoints:
                self.config.websocket_endpoints[chain_id] = endpoints
                logger.debug(f"Chain {chain_id}: {len(endpoints)} WebSocket endpoints configured")
    
    def _http_to_websocket_url(self, http_url: str) -> Optional[str]:
        """Convert HTTP RPC URL to WebSocket URL for known providers."""
        if 'alchemy.com' in http_url:
            return http_url.replace('https://', 'wss://').replace('http://', 'ws://')
        elif 'ankr.com' in http_url:
            return http_url.replace('https://', 'wss://').replace('http://', 'ws://')
        elif 'infura.io' in http_url:
            return http_url.replace('https://', 'wss://').replace('http://', 'ws://')
        
        return None
    
    async def start_monitoring(self) -> None:
        """Start mempool monitoring for all configured chains."""
        if self.is_running:
            logger.warning("MempoolMonitor already running")
            return
        
        logger.info("Starting mempool monitoring...")
        self.is_running = True
        
        # Start monitoring tasks for each chain
        for chain_id, endpoints in self.config.websocket_endpoints.items():
            if endpoints:
                task = asyncio.create_task(self._monitor_chain(chain_id, endpoints))
                self.connection_tasks[chain_id] = task
                logger.info(f"Started monitoring chain {chain_id} with {len(endpoints)} endpoints")
        
        # Start cleanup task
        asyncio.create_task(self._cleanup_old_transactions())
        
        logger.info(f"MempoolMonitor started for {len(self.connection_tasks)} chains")
    
    async def stop_monitoring(self) -> None:
        """Stop all mempool monitoring."""
        if not self.is_running:
            return
        
        logger.info("Stopping mempool monitoring...")
        self.is_running = False
        
        # Cancel all connection tasks
        for chain_id, task in self.connection_tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                logger.debug(f"Stopped monitoring chain {chain_id}")
        
        # Close active connections
        for chain_id, websocket in self.active_connections.items():
            try:
                await websocket.close()
            except Exception as e:
                logger.debug(f"Error closing WebSocket for chain {chain_id}: {e}")
        
        self.connection_tasks.clear()
        self.active_connections.clear()
        
        logger.info("MempoolMonitor stopped")
    
    async def _monitor_chain(self, chain_id: int, endpoints: List[str]) -> None:
        """Monitor mempool for a specific chain with automatic failover."""
        retry_count = 0
        max_retries = 3
        
        while self.is_running and retry_count < max_retries:
            for endpoint in endpoints:
                if not self.is_running:
                    break
                
                try:
                    logger.info(f"Connecting to mempool WebSocket for chain {chain_id}: {endpoint}")
                    
                    async with websockets.connect(
                        endpoint,
                        timeout=self.config.connection_timeout_seconds,
                        ping_interval=self.config.heartbeat_interval_seconds,
                        ping_timeout=10
                    ) as websocket:
                        self.active_connections[chain_id] = websocket
                        self.stats['reconnections'] += 1
                        retry_count = 0  # Reset retry count on successful connection
                        
                        # Subscribe to pending transactions
                        await self._subscribe_to_mempool(websocket, chain_id)
                        
                        # Process incoming messages
                        await self._process_websocket_messages(websocket, chain_id)
                
                except (ConnectionClosedError, ConnectionClosedOK) as e:
                    logger.warning(f"WebSocket connection closed for chain {chain_id}: {e}")
                    self.stats['connection_drops'] += 1
                except Exception as e:
                    logger.error(f"Error monitoring chain {chain_id} via {endpoint}: {e}")
                    self.stats['connection_drops'] += 1
                
                # Clean up connection
                if chain_id in self.active_connections:
                    del self.active_connections[chain_id]
                
                # Wait before trying next endpoint
                await asyncio.sleep(2)
            
            # Increment retry count and wait longer before retrying all endpoints
            retry_count += 1
            if retry_count < max_retries:
                wait_time = min(retry_count * 10, 60)
                logger.info(f"Retrying chain {chain_id} in {wait_time} seconds (attempt {retry_count}/{max_retries})")
                await asyncio.sleep(wait_time)
        
        logger.error(f"Failed to establish stable connection for chain {chain_id} after {max_retries} retries")
    
    async def _subscribe_to_mempool(self, websocket: websockets.WebSocketServerProtocol, chain_id: int) -> None:
        """Subscribe to pending transactions for the mempool."""
        # Subscription message format for Alchemy/standard providers
        subscription_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_subscribe",
            "params": ["newPendingTransactions", True]  # True for full transaction details
        }
        
        await websocket.send(json.dumps(subscription_msg))
        logger.info(f"Subscribed to mempool for chain {chain_id}")
    
    async def _process_websocket_messages(self, websocket: websockets.WebSocketServerProtocol, chain_id: int) -> None:
        """Process incoming WebSocket messages from mempool subscription."""
        async for message in websocket:
            try:
                data = json.loads(message)
                
                # Handle subscription confirmation
                if 'id' in data and data.get('id') == 1:
                    logger.info(f"Mempool subscription confirmed for chain {chain_id}: {data.get('result')}")
                    continue
                
                # Handle pending transaction notifications
                if 'params' in data and 'result' in data['params']:
                    tx_data = data['params']['result']
                    await self._process_pending_transaction(tx_data, chain_id)
                
            except json.JSONDecodeError as e:
                logger.debug(f"Failed to parse WebSocket message: {e}")
            except Exception as e:
                logger.error(f"Error processing WebSocket message for chain {chain_id}: {e}")
    
    async def _process_pending_transaction(self, tx_data: Dict, chain_id: int) -> None:
        """Process a pending transaction from the mempool."""
        try:
            self.stats['total_transactions_seen'] += 1
            
            # Fast pre-filtering to reduce processing load
            if self.config.enable_pre_filtering:
                if not self._should_process_transaction(tx_data):
                    self.stats['transactions_filtered_out'] += 1
                    return
            
            # Create MempoolTransaction object
            tx = self._parse_transaction(tx_data, chain_id)
            if not tx:
                return
            
            # Store in pending transactions cache
            async with self.transaction_lock:
                self.pending_transactions[tx.hash] = tx
                
                # Enforce memory limits
                if len(self.pending_transactions) > self.config.max_pending_transactions:
                    # Remove oldest transaction
                    oldest_hash = min(self.pending_transactions.keys(), 
                                    key=lambda h: self.pending_transactions[h].timestamp)
                    del self.pending_transactions[oldest_hash]
            
            # Update stats
            self.stats['transactions_processed'] += 1
            self.stats['last_transaction_time'] = datetime.now(timezone.utc)
            
            # Trigger callback if provided
            if self.event_callback:
                try:
                    self.event_callback(MempoolEventType.PENDING_TRANSACTION, tx)
                except Exception as e:
                    logger.error(f"Error in mempool event callback: {e}")
            
            logger.debug(f"Processed pending transaction: {tx.hash[:10]}... (Chain: {chain_id})")
            
        except Exception as e:
            logger.error(f"Error processing pending transaction: {e}")
    
    def _should_process_transaction(self, tx_data: Dict) -> bool:
        """Fast pre-filtering to determine if transaction should be processed."""
        try:
            # Check minimum value threshold
            value = int(tx_data.get('value', '0x0'), 16)
            if value < self.config.min_value_eth * 1e18:
                return False
            
            # Check minimum gas price threshold  
            gas_price = int(tx_data.get('gasPrice', '0x0'), 16)
            if gas_price < self.config.min_gas_gwei * 1e9:
                return False
            
            # Check if targeting DEX contracts (if enabled)
            if self.config.track_dex_transactions_only:
                to_address = tx_data.get('to', '').lower()
                if to_address not in self.config.known_router_addresses:
                    return False
            
            return True
            
        except (ValueError, KeyError):
            return False
    
    def _parse_transaction(self, tx_data: Dict, chain_id: int) -> Optional[MempoolTransaction]:
        """Parse transaction data into MempoolTransaction object."""
        try:
            return MempoolTransaction(
                hash=tx_data['hash'],
                from_address=tx_data['from'].lower(),
                to_address=tx_data.get('to', '').lower() if tx_data.get('to') else None,
                value=int(tx_data.get('value', '0x0'), 16),
                gas_price=int(tx_data.get('gasPrice', '0x0'), 16),
                gas_limit=int(tx_data.get('gas', '0x0'), 16),
                nonce=int(tx_data.get('nonce', '0x0'), 16),
                input_data=tx_data.get('input', ''),
                timestamp=time.time(),
                chain_id=chain_id,
            )
        except (KeyError, ValueError) as e:
            logger.debug(f"Failed to parse transaction: {e}")
            return None
    
    async def _cleanup_old_transactions(self) -> None:
        """Periodically clean up old transactions from memory."""
        while self.is_running:
            try:
                current_time = time.time()
                expired_hashes = []
                
                async with self.transaction_lock:
                    for tx_hash, tx in self.pending_transactions.items():
                        if current_time - tx.timestamp > self.config.max_age_seconds:
                            expired_hashes.append(tx_hash)
                    
                    for tx_hash in expired_hashes:
                        del self.pending_transactions[tx_hash]
                
                if expired_hashes:
                    logger.debug(f"Cleaned up {len(expired_hashes)} expired transactions")
                
                # Run cleanup every 60 seconds
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in transaction cleanup: {e}")
                await asyncio.sleep(60)
    
    async def get_pending_transactions(
        self, 
        chain_id: Optional[int] = None,
        max_age_seconds: Optional[float] = None
    ) -> List[MempoolTransaction]:
        """
        Get current pending transactions from cache.
        
        Args:
            chain_id: Optional chain ID to filter by
            max_age_seconds: Optional maximum age filter
            
        Returns:
            List of pending transactions matching criteria
        """
        async with self.transaction_lock:
            transactions = list(self.pending_transactions.values())
        
        # Apply filters
        if chain_id is not None:
            transactions = [tx for tx in transactions if tx.chain_id == chain_id]
        
        if max_age_seconds is not None:
            current_time = time.time()
            transactions = [tx for tx in transactions 
                          if current_time - tx.timestamp <= max_age_seconds]
        
        return transactions
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get mempool monitoring statistics."""
        stats = self.stats.copy()
        stats.update({
            'is_running': self.is_running,
            'active_connections': len(self.active_connections),
            'pending_transactions_count': len(self.pending_transactions),
            'chains_monitored': list(self.config.websocket_endpoints.keys()),
        })
        return stats
    
    def is_connected(self, chain_id: Optional[int] = None) -> bool:
        """Check if monitor is connected to mempool."""
        if chain_id is not None:
            return chain_id in self.active_connections
        return len(self.active_connections) > 0


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def create_mempool_config_from_settings() -> MempoolConfig:
    """Create mempool configuration from Django settings."""
    import os
    from django.conf import settings
    
    config = MempoolConfig()
    
    # Load settings with defaults
    config.min_value_eth = float(os.getenv('MEMPOOL_MIN_VALUE_ETH', '0.01'))
    config.min_gas_gwei = float(os.getenv('MEMPOOL_MIN_GAS_GWEI', '10.0'))
    config.max_age_seconds = float(os.getenv('MEMPOOL_MAX_AGE_SECONDS', '300.0'))
    config.track_dex_transactions_only = os.getenv('MEMPOOL_TRACK_DEX_ONLY', 'True').lower() == 'true'
    config.max_pending_transactions = int(os.getenv('MEMPOOL_MAX_PENDING', '10000'))
    
    # Add known DEX router addresses from Django settings
    router_addresses = set()
    if hasattr(settings, 'UNISWAP_V2_ROUTER'):
        router_addresses.add(settings.UNISWAP_V2_ROUTER.lower())
    if hasattr(settings, 'UNISWAP_V3_ROUTER'):
        router_addresses.add(settings.UNISWAP_V3_ROUTER.lower())
    if hasattr(settings, 'BASE_UNISWAP_V3_ROUTER'):
        router_addresses.add(settings.BASE_UNISWAP_V3_ROUTER.lower())
    
    config.known_router_addresses = router_addresses
    
    return config


async def create_mempool_monitor(
    provider_manager: ProviderManager,
    event_callback: Optional[Callable[[MempoolEventType, MempoolTransaction], None]] = None
) -> MempoolMonitor:
    """
    Factory function to create a properly configured mempool monitor.
    
    Args:
        provider_manager: Provider manager instance
        event_callback: Optional callback for mempool events
        
    Returns:
        Configured MempoolMonitor instance
    """
    config = create_mempool_config_from_settings()
    return MempoolMonitor(config, provider_manager, event_callback)