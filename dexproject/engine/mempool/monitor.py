"""
Mempool Monitoring Module

This module provides real-time mempool monitoring and analysis capabilities
for the Fast Lane execution path. It integrates with private relay management
and MEV protection to provide comprehensive transaction pool intelligence.

Key Features:
- WebSocket-based mempool streaming from multiple providers
- Pending transaction analysis and classification
- MEV threat detection in real-time transaction flow
- Integration with private relay routing decisions
- Gas price trend analysis from mempool data
- Performance metrics and alerting
- Multi-chain mempool support

File: dexproject/engine/mempool/monitor.py
Django App: N/A (Pure engine component)
"""

import asyncio
import json
import logging
import time
import websockets
from collections import defaultdict, deque
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any, Callable, Union
from datetime import datetime, timedelta

import aiohttp
from web3 import Web3
from web3.types import TxParams, BlockData
from eth_typing import ChecksumAddress, HexStr
from eth_utils import to_checksum_address, to_hex

# Import engine components
from ..config import EngineConfig, get_config
from .relay import PrivateRelayManager, PriorityLevel
from .protection import (
    MEVProtectionEngine, PendingTransaction, MEVThreat, 
    ProtectionRecommendation, MEVThreatType
)
from ..execution.gas_optimizer import GasOptimizationEngine, GasMetrics, NetworkCongestion
from ..communications.django_bridge import DjangoBridge
from ...shared.schemas import ChainType, PairSource


logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class MempoolProvider(str, Enum):
    """Supported mempool data providers."""
    ALCHEMY = "alchemy"
    ANKR = "ankr"
    INFURA = "infura"
    QUICKNODE = "quicknode"
    LOCAL_NODE = "local_node"


class TransactionStatus(str, Enum):
    """Transaction status in mempool monitoring."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DROPPED = "dropped"
    REPLACED = "replaced"


class MonitoringMode(str, Enum):
    """Mempool monitoring operational modes."""
    FULL_STREAM = "full_stream"        # Monitor all transactions
    DEX_ONLY = "dex_only"             # Only DEX-related transactions
    TARGET_TOKENS = "target_tokens"    # Only specific token interactions
    HIGH_VALUE = "high_value"          # Only high-value transactions


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class MempoolConfig:
    """Configuration for mempool monitoring."""
    
    chain_id: int
    providers: List[MempoolProvider]
    mode: MonitoringMode = MonitoringMode.DEX_ONLY
    max_pending_transactions: int = 10000
    transaction_ttl_seconds: int = 300
    
    # Filtering criteria
    min_value_wei: int = 0
    target_addresses: Set[str] = field(default_factory=set)
    target_tokens: Set[str] = field(default_factory=set)
    
    # Performance settings
    batch_size: int = 100
    processing_interval_ms: int = 50
    websocket_timeout: int = 30
    max_retries: int = 5


@dataclass
class MempoolTransaction:
    """Enhanced mempool transaction with analysis data."""
    
    # Basic transaction data
    hash: str
    from_address: str
    to_address: Optional[str]
    value: Decimal
    gas_price: Decimal
    gas_limit: int
    nonce: int
    data: str
    
    # Timestamps
    first_seen: datetime
    last_seen: datetime
    
    # Analysis results
    is_dex_interaction: bool = False
    dex_name: Optional[str] = None
    target_token: Optional[str] = None
    swap_amount_in: Optional[Decimal] = None
    swap_amount_out: Optional[Decimal] = None
    function_signature: Optional[str] = None
    
    # MEV analysis
    mev_threats: List[MEVThreat] = field(default_factory=list)
    protection_recommendation: Optional[ProtectionRecommendation] = None
    
    # Status tracking
    status: TransactionStatus = TransactionStatus.PENDING
    confirmation_block: Optional[int] = None
    
    def to_pending_transaction(self) -> PendingTransaction:
        """Convert to PendingTransaction for MEV analysis."""
        return PendingTransaction(
            hash=self.hash,
            from_address=self.from_address,
            to_address=self.to_address,
            value=self.value,
            gas_price=self.gas_price,
            gas_limit=self.gas_limit,
            nonce=self.nonce,
            data=self.data,
            timestamp=self.first_seen,
            is_dex_interaction=self.is_dex_interaction,
            target_token=self.target_token,
            swap_amount_in=self.swap_amount_in,
            swap_amount_out=self.swap_amount_out,
            dex_name=self.dex_name
        )


@dataclass
class MempoolStats:
    """Mempool monitoring statistics."""
    
    chain_id: int
    total_transactions_seen: int = 0
    dex_transactions_seen: int = 0
    mev_threats_detected: int = 0
    current_pending_count: int = 0
    
    # Performance metrics
    avg_processing_latency_ms: float = 0.0
    websocket_reconnects: int = 0
    missed_transactions: int = 0
    
    # Gas analysis
    avg_gas_price: Optional[Decimal] = None
    gas_price_percentiles: Dict[int, Decimal] = field(default_factory=dict)
    congestion_level: NetworkCongestion = NetworkCongestion.LOW
    
    # Provider status
    active_providers: List[MempoolProvider] = field(default_factory=list)
    failed_providers: List[MempoolProvider] = field(default_factory=list)


# =============================================================================
# MEMPOOL MONITOR ENGINE
# =============================================================================

class MempoolMonitor:
    """
    Advanced mempool monitoring system for real-time transaction analysis.
    
    This monitor provides comprehensive mempool intelligence by streaming
    pending transactions, analyzing MEV opportunities/threats, and feeding
    real-time data to the gas optimization and relay management systems.
    """
    
    def __init__(self, engine_config: EngineConfig):
        """
        Initialize the mempool monitor.
        
        Args:
            engine_config: Engine configuration instance
        """
        self.config = engine_config
        self.logger = logging.getLogger(f"{__name__}.MempoolMonitor")
        
        # Monitoring configurations for each chain
        self._chain_configs: Dict[int, MempoolConfig] = {}
        
        # Active WebSocket connections
        self._websocket_connections: Dict[str, websockets.WebSocketServerProtocol] = {}
        self._connection_tasks: Dict[str, asyncio.Task] = {}
        
        # Transaction storage and analysis
        self._pending_transactions: Dict[int, Dict[str, MempoolTransaction]] = defaultdict(dict)
        self._transaction_queues: Dict[int, asyncio.Queue] = defaultdict(asyncio.Queue)
        
        # Analysis components (will be injected)
        self._mev_engine: Optional[MEVProtectionEngine] = None
        self._gas_optimizer: Optional[GasOptimizationEngine] = None
        self._relay_manager: Optional[PrivateRelayManager] = None
        
        # Statistics and performance tracking
        self._stats: Dict[int, MempoolStats] = {}
        self._processing_latencies: deque = deque(maxlen=100)
        
        # Event callbacks
        self._transaction_callbacks: List[Callable] = []
        self._threat_callbacks: List[Callable] = []
        
        # HTTP session for REST APIs
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Django communication bridge
        self._django_bridge: Optional[DjangoBridge] = None
        
        # Initialize configurations
        self._initialize_chain_configs()
        
        self.logger.info("Mempool monitor initialized")
    
    async def initialize(
        self,
        mev_engine: MEVProtectionEngine,
        gas_optimizer: GasOptimizationEngine,
        relay_manager: PrivateRelayManager
    ) -> None:
        """
        Initialize the mempool monitor with analysis components.
        
        Args:
            mev_engine: MEV protection engine
            gas_optimizer: Gas optimization engine
            relay_manager: Private relay manager
        """
        self._mev_engine = mev_engine
        self._gas_optimizer = gas_optimizer
        self._relay_manager = relay_manager
        
        # Create HTTP session
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self._session = aiohttp.ClientSession(timeout=timeout)
        
        # Initialize Django bridge
        try:
            self._django_bridge = DjangoBridge("mempool_monitor")
            await self._django_bridge.initialize()
            self.logger.info("Django bridge initialized for mempool monitor")
        except Exception as e:
            self.logger.warning(f"Could not initialize Django bridge: {e}")
        
        # Initialize statistics
        for chain_id in self._chain_configs.keys():
            self._stats[chain_id] = MempoolStats(chain_id=chain_id)
        
        self.logger.info("Mempool monitor async initialization complete")
    
    async def start_monitoring(self, chain_ids: Optional[List[int]] = None) -> None:
        """
        Start mempool monitoring for specified chains.
        
        Args:
            chain_ids: List of chain IDs to monitor (None for all configured)
        """
        if chain_ids is None:
            chain_ids = list(self._chain_configs.keys())
        
        self.logger.info(f"Starting mempool monitoring for chains: {chain_ids}")
        
        # Start monitoring tasks for each chain
        for chain_id in chain_ids:
            if chain_id not in self._chain_configs:
                self.logger.warning(f"No configuration for chain {chain_id}, skipping")
                continue
            
            # Start WebSocket connections for each provider
            chain_config = self._chain_configs[chain_id]
            for provider in chain_config.providers:
                task_key = f"{chain_id}_{provider.value}"
                
                # Start WebSocket connection task
                self._connection_tasks[task_key] = asyncio.create_task(
                    self._maintain_websocket_connection(chain_id, provider)
                )
            
            # Start transaction processing task for the chain
            processing_task_key = f"{chain_id}_processor"
            self._connection_tasks[processing_task_key] = asyncio.create_task(
                self._process_transaction_queue(chain_id)
            )
        
        self.logger.info(f"Started {len(self._connection_tasks)} monitoring tasks")
    
    async def stop_monitoring(self) -> None:
        """Stop all mempool monitoring activities."""
        self.logger.info("Stopping mempool monitoring...")
        
        # Cancel all tasks
        for task_key, task in self._connection_tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Close WebSocket connections
        for connection in self._websocket_connections.values():
            if not connection.closed:
                await connection.close()
        
        # Close HTTP session
        if self._session:
            await self._session.close()
        
        # Close Django bridge
        if self._django_bridge:
            await self._django_bridge.disconnect()
        
        self.logger.info("Mempool monitoring stopped")
    
    def _initialize_chain_configs(self) -> None:
        """Initialize mempool monitoring configurations for each chain."""
        # Ethereum Mainnet configuration
        if 1 in self.config.chain_configs:
            eth_config = MempoolConfig(
                chain_id=1,
                providers=[MempoolProvider.ALCHEMY, MempoolProvider.ANKR],
                mode=MonitoringMode.DEX_ONLY,
                max_pending_transactions=5000,
                transaction_ttl_seconds=300,
                min_value_wei=int(0.01 * 1e18),  # 0.01 ETH minimum
                batch_size=50,
                processing_interval_ms=100
            )
            
            # Add major DEX addresses for Ethereum
            eth_config.target_addresses.update({
                '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',  # Uniswap V2 Router
                '0xE592427A0AEce92De3Edee1F18E0157C05861564',  # Uniswap V3 Router
                '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F',  # Sushiswap Router
            })
            
            self._chain_configs[1] = eth_config
        
        # Base Mainnet configuration
        if 8453 in self.config.chain_configs:
            base_config = MempoolConfig(
                chain_id=8453,
                providers=[MempoolProvider.ALCHEMY],
                mode=MonitoringMode.DEX_ONLY,
                max_pending_transactions=2000,
                transaction_ttl_seconds=180,
                min_value_wei=int(0.001 * 1e18),  # 0.001 ETH minimum
                batch_size=100,
                processing_interval_ms=50
            )
            
            # Add Base DEX addresses
            base_config.target_addresses.update({
                '0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24',  # Base DEX Router
            })
            
            self._chain_configs[8453] = base_config
        
        self.logger.info(f"Initialized mempool configs for {len(self._chain_configs)} chains")
    
    async def _maintain_websocket_connection(
        self, 
        chain_id: int, 
        provider: MempoolProvider
    ) -> None:
        """
        Maintain WebSocket connection to a mempool provider.
        
        Args:
            chain_id: Target blockchain network
            provider: Mempool data provider
        """
        connection_key = f"{chain_id}_{provider.value}"
        retry_count = 0
        max_retries = self._chain_configs[chain_id].max_retries
        
        while retry_count < max_retries:
            try:
                websocket_url = self._get_websocket_url(chain_id, provider)
                
                self.logger.info(f"Connecting to {provider.value} WebSocket for chain {chain_id}")
                
                async with websockets.connect(
                    websocket_url,
                    timeout=self._chain_configs[chain_id].websocket_timeout,
                    ping_interval=20,
                    ping_timeout=10
                ) as websocket:
                    
                    self._websocket_connections[connection_key] = websocket
                    self._stats[chain_id].active_providers.append(provider)
                    
                    # Subscribe to mempool events
                    await self._subscribe_to_mempool(websocket, chain_id, provider)
                    
                    # Reset retry counter on successful connection
                    retry_count = 0
                    
                    # Handle incoming messages
                    async for message in websocket:
                        await self._handle_websocket_message(
                            message, chain_id, provider
                        )
                        
            except Exception as e:
                retry_count += 1
                self.logger.error(
                    f"WebSocket connection failed for {provider.value} "
                    f"(chain {chain_id}): {e}. Retry {retry_count}/{max_retries}"
                )
                
                # Update statistics
                self._stats[chain_id].websocket_reconnects += 1
                if provider in self._stats[chain_id].active_providers:
                    self._stats[chain_id].active_providers.remove(provider)
                if provider not in self._stats[chain_id].failed_providers:
                    self._stats[chain_id].failed_providers.append(provider)
                
                if retry_count < max_retries:
                    # Exponential backoff
                    wait_time = min(2 ** retry_count, 60)
                    await asyncio.sleep(wait_time)
        
        self.logger.error(f"Max retries exceeded for {provider.value} on chain {chain_id}")
    
    def _get_websocket_url(self, chain_id: int, provider: MempoolProvider) -> str:
        """
        Get WebSocket URL for the specified provider and chain.
        
        Args:
            chain_id: Target blockchain network
            provider: Mempool data provider
            
        Returns:
            WebSocket URL for the provider
        """
        if provider == MempoolProvider.ALCHEMY:
            api_key = getattr(self.config, 'alchemy_api_key', 'demo')
            if chain_id == 1:  # Ethereum mainnet
                return f"wss://eth-mainnet.g.alchemy.com/v2/{api_key}"
            elif chain_id == 8453:  # Base mainnet
                return f"wss://base-mainnet.g.alchemy.com/v2/{api_key}"
        
        elif provider == MempoolProvider.ANKR:
            if chain_id == 1:  # Ethereum mainnet
                return "wss://rpc.ankr.com/eth/ws"
        
        # Add more providers as needed
        raise ValueError(f"No WebSocket URL configured for {provider.value} on chain {chain_id}")
    
    async def _subscribe_to_mempool(
        self, 
        websocket: websockets.WebSocketServerProtocol, 
        chain_id: int, 
        provider: MempoolProvider
    ) -> None:
        """
        Subscribe to mempool events on the WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            chain_id: Target blockchain network
            provider: Mempool data provider
        """
        if provider == MempoolProvider.ALCHEMY:
            # Alchemy subscription for pending transactions
            subscription = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_subscribe",
                "params": ["alchemy_pendingTransactions"]
            }
        elif provider == MempoolProvider.ANKR:
            # Ankr subscription for pending transactions
            subscription = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_subscribe",
                "params": ["newPendingTransactions"]
            }
        else:
            raise ValueError(f"Unsupported provider: {provider.value}")
        
        await websocket.send(json.dumps(subscription))
        
        # Wait for subscription confirmation
        response = await websocket.recv()
        response_data = json.loads(response)
        
        if "result" in response_data:
            self.logger.info(
                f"Successfully subscribed to {provider.value} mempool "
                f"for chain {chain_id}: {response_data['result']}"
            )
        else:
            raise Exception(f"Subscription failed: {response_data}")
    
    async def _handle_websocket_message(
        self, 
        message: str, 
        chain_id: int, 
        provider: MempoolProvider
    ) -> None:
        """
        Handle incoming WebSocket message from mempool provider.
        
        Args:
            message: Raw WebSocket message
            chain_id: Source blockchain network
            provider: Source mempool provider
        """
        try:
            data = json.loads(message)
            
            # Handle subscription notifications
            if "params" in data and "result" in data["params"]:
                transaction_data = data["params"]["result"]
                
                # Convert to our internal transaction format
                mempool_tx = await self._parse_transaction_data(
                    transaction_data, chain_id, provider
                )
                
                if mempool_tx:
                    # Add to processing queue
                    await self._transaction_queues[chain_id].put(mempool_tx)
                    
                    # Update statistics
                    self._stats[chain_id].total_transactions_seen += 1
                    if mempool_tx.is_dex_interaction:
                        self._stats[chain_id].dex_transactions_seen += 1
        
        except Exception as e:
            self.logger.error(f"Error handling WebSocket message: {e}")
    
    async def _parse_transaction_data(
        self, 
        tx_data: Dict[str, Any], 
        chain_id: int, 
        provider: MempoolProvider
    ) -> Optional[MempoolTransaction]:
        """
        Parse raw transaction data into MempoolTransaction.
        
        Args:
            tx_data: Raw transaction data from provider
            chain_id: Source blockchain network
            provider: Source mempool provider
            
        Returns:
            Parsed MempoolTransaction or None if filtered out
        """
        try:
            # Extract basic transaction fields
            tx_hash = tx_data.get("hash", "")
            from_addr = tx_data.get("from", "")
            to_addr = tx_data.get("to")
            value = Decimal(int(tx_data.get("value", "0x0"), 16))
            gas_price = Decimal(int(tx_data.get("gasPrice", "0x0"), 16))
            gas_limit = int(tx_data.get("gas", "0x0"), 16)
            nonce = int(tx_data.get("nonce", "0x0"), 16)
            data = tx_data.get("input", "0x")
            
            # Apply filtering based on configuration
            chain_config = self._chain_configs[chain_id]
            
            # Value filter
            if value < chain_config.min_value_wei and data == "0x":
                return None  # Skip low-value simple transfers
            
            # Address filter
            if (chain_config.target_addresses and 
                to_addr and to_addr not in chain_config.target_addresses):
                # Only interested in specific addresses
                if chain_config.mode == MonitoringMode.TARGET_TOKENS:
                    return None
            
            # Create mempool transaction
            now = datetime.utcnow()
            mempool_tx = MempoolTransaction(
                hash=tx_hash,
                from_address=from_addr,
                to_address=to_addr,
                value=value,
                gas_price=gas_price,
                gas_limit=gas_limit,
                nonce=nonce,
                data=data,
                first_seen=now,
                last_seen=now
            )
            
            # Analyze transaction for DEX interactions
            await self._analyze_transaction_type(mempool_tx, chain_id)
            
            # Apply mode-specific filtering
            if (chain_config.mode == MonitoringMode.DEX_ONLY and 
                not mempool_tx.is_dex_interaction):
                return None
            
            return mempool_tx
            
        except Exception as e:
            self.logger.error(f"Error parsing transaction data: {e}")
            return None
    
    async def _analyze_transaction_type(
        self, 
        transaction: MempoolTransaction, 
        chain_id: int
    ) -> None:
        """
        Analyze transaction to identify type and extract DEX interaction data.
        
        Args:
            transaction: Transaction to analyze
            chain_id: Blockchain network
        """
        if not transaction.data or transaction.data == "0x":
            return  # Simple ETH transfer
        
        # Extract function selector
        if len(transaction.data) >= 10:
            function_selector = transaction.data[:10]
            transaction.function_signature = function_selector
            
            # Common DEX function selectors
            dex_functions = {
                "0x7ff36ab5": ("swapExactETHForTokens", "uniswap_v2"),
                "0x18cbafe5": ("swapExactTokensForETH", "uniswap_v2"),
                "0x38ed1739": ("swapExactTokensForTokens", "uniswap_v2"),
                "0x414bf389": ("exactInputSingle", "uniswap_v3"),
                "0xc04b8d59": ("exactInput", "uniswap_v3"),
                "0x5c11d795": ("swapExactTokensForTokensSupportingFeeOnTransferTokens", "uniswap_v2"),
            }
            
            if function_selector in dex_functions:
                function_name, dex_name = dex_functions[function_selector]
                transaction.is_dex_interaction = True
                transaction.dex_name = dex_name
                
                # Extract swap parameters (simplified)
                # In production, this would use proper ABI decoding
                await self._extract_swap_parameters(transaction, function_name)
    
    async def _extract_swap_parameters(
        self, 
        transaction: MempoolTransaction, 
        function_name: str
    ) -> None:
        """
        Extract swap parameters from transaction data.
        
        Args:
            transaction: Transaction with DEX interaction
            function_name: Name of the DEX function
        """
        # Simplified parameter extraction
        # In production, this would use proper ABI decoding with libraries like web3.py
        
        if function_name in ["swapExactETHForTokens", "swapExactTokensForETH"]:
            # Extract amounts and token addresses
            # This is a placeholder - actual implementation would decode ABI
            transaction.swap_amount_in = transaction.value if transaction.value > 0 else None
        
        elif function_name == "exactInputSingle":
            # Uniswap V3 single swap
            # Would extract tokenIn, tokenOut, amountIn from transaction data
            pass
    
    async def _process_transaction_queue(self, chain_id: int) -> None:
        """
        Process transaction queue for MEV analysis and threat detection.
        
        Args:
            chain_id: Blockchain network to process
        """
        self.logger.info(f"Starting transaction processing for chain {chain_id}")
        
        chain_config = self._chain_configs[chain_id]
        processing_batch = []
        
        while True:
            try:
                # Collect transactions for batch processing
                while len(processing_batch) < chain_config.batch_size:
                    try:
                        # Wait for new transaction or timeout
                        timeout_seconds = chain_config.processing_interval_ms / 1000
                        transaction = await asyncio.wait_for(
                            self._transaction_queues[chain_id].get(), 
                            timeout=timeout_seconds
                        )
                        processing_batch.append(transaction)
                        
                    except asyncio.TimeoutError:
                        break  # Process current batch
                
                if processing_batch:
                    await self._process_transaction_batch(processing_batch, chain_id)
                    processing_batch.clear()
                    
                    # Update current pending count
                    self._stats[chain_id].current_pending_count = len(
                        self._pending_transactions[chain_id]
                    )
                
            except Exception as e:
                self.logger.error(f"Error in transaction processing for chain {chain_id}: {e}")
                processing_batch.clear()
                await asyncio.sleep(1)
    
    async def _process_transaction_batch(
        self, 
        transactions: List[MempoolTransaction], 
        chain_id: int
    ) -> None:
        """
        Process a batch of transactions for MEV analysis.
        
        Args:
            transactions: Batch of transactions to process
            chain_id: Blockchain network
        """
        start_time = time.time()
        
        try:
            # Store transactions in pending pool
            for tx in transactions:
                self._pending_transactions[chain_id][tx.hash] = tx
            
            # Clean up old transactions
            await self._cleanup_old_transactions(chain_id)
            
            # Perform MEV analysis if engine is available
            if self._mev_engine:
                await self._analyze_batch_for_mev(transactions, chain_id)
            
            # Update gas price statistics
            await self._update_gas_statistics(transactions, chain_id)
            
            # Send notifications for high-priority transactions
            await self._process_transaction_callbacks(transactions, chain_id)
            
            # Track processing performance
            processing_time = (time.time() - start_time) * 1000
            self._processing_latencies.append(processing_time)
            
            if len(self._processing_latencies) > 0:
                avg_latency = sum(self._processing_latencies) / len(self._processing_latencies)
                self._stats[chain_id].avg_processing_latency_ms = avg_latency
            
        except Exception as e:
            self.logger.error(f"Error processing transaction batch: {e}")
    
    async def _analyze_batch_for_mev(
        self, 
        new_transactions: List[MempoolTransaction], 
        chain_id: int
    ) -> None:
        """
        Analyze new transactions for MEV threats and opportunities.
        
        Args:
            new_transactions: New transactions to analyze
            chain_id: Blockchain network
        """
        if not self._mev_engine:
            return
        
        # Get current mempool state for analysis
        current_mempool = [
            tx.to_pending_transaction() 
            for tx in self._pending_transactions[chain_id].values()
        ]
        
        # Analyze each new transaction
        for tx in new_transactions:
            if tx.is_dex_interaction:
                try:
                    # Convert to format expected by MEV engine
                    tx_params = self._convert_to_tx_params(tx)
                    
                    # Analyze for MEV threats
                    threats, recommendation = await self._mev_engine.analyze_transaction_for_mev_threats(
                        tx_params, current_mempool
                    )
                    
                    # Store analysis results
                    tx.mev_threats = threats
                    tx.protection_recommendation = recommendation
                    
                    if threats:
                        self._stats[chain_id].mev_threats_detected += len(threats)
                        
                        # Send threat notifications
                        await self._process_threat_callbacks(tx, threats, chain_id)
                
                except Exception as e:
                    self.logger.error(f"MEV analysis failed for tx {tx.hash}: {e}")
    
    def _convert_to_tx_params(self, transaction: MempoolTransaction) -> TxParams:
        """Convert MempoolTransaction to TxParams format."""
        return {
            'from': transaction.from_address,
            'to': transaction.to_address,
            'value': int(transaction.value),
            'gasPrice': int(transaction.gas_price),
            'gas': transaction.gas_limit,
            'nonce': transaction.nonce,
            'data': transaction.data
        }
    
    async def _cleanup_old_transactions(self, chain_id: int) -> None:
        """
        Remove old transactions from the pending pool.
        
        Args:
            chain_id: Blockchain network
        """
        chain_config = self._chain_configs[chain_id]
        cutoff_time = datetime.utcnow() - timedelta(seconds=chain_config.transaction_ttl_seconds)
        
        # Find transactions to remove
        to_remove = [
            tx_hash for tx_hash, tx in self._pending_transactions[chain_id].items()
            if tx.last_seen < cutoff_time
        ]
        
        # Remove old transactions
        for tx_hash in to_remove:
            del self._pending_transactions[chain_id][tx_hash]
        
        # Limit total transactions if needed
        if len(self._pending_transactions[chain_id]) > chain_config.max_pending_transactions:
            # Remove oldest transactions
            sorted_txs = sorted(
                self._pending_transactions[chain_id].items(),
                key=lambda x: x[1].first_seen
            )
            
            excess_count = len(sorted_txs) - chain_config.max_pending_transactions
            for i in range(excess_count):
                tx_hash = sorted_txs[i][0]
                del self._pending_transactions[chain_id][tx_hash]
    
    async def _update_gas_statistics(
        self, 
        transactions: List[MempoolTransaction], 
        chain_id: int
    ) -> None:
        """
        Update gas price statistics from new transactions.
        
        Args:
            transactions: New transactions
            chain_id: Blockchain network
        """
        if not transactions:
            return
        
        gas_prices = [float(tx.gas_price) for tx in transactions if tx.gas_price > 0]
        
        if gas_prices:
            # Update average gas price
            self._stats[chain_id].avg_gas_price = Decimal(str(sum(gas_prices) / len(gas_prices)))
            
            # Update percentiles
            gas_prices.sort()
            self._stats[chain_id].gas_price_percentiles = {
                10: Decimal(str(gas_prices[int(len(gas_prices) * 0.1)])),
                50: Decimal(str(gas_prices[int(len(gas_prices) * 0.5)])),
                90: Decimal(str(gas_prices[int(len(gas_prices) * 0.9)]))
            }
            
            # Estimate congestion level
            current_pending = len(self._pending_transactions[chain_id])
            max_pending = self._chain_configs[chain_id].max_pending_transactions
            
            congestion_ratio = current_pending / max_pending
            
            if congestion_ratio < 0.3:
                self._stats[chain_id].congestion_level = NetworkCongestion.LOW
            elif congestion_ratio < 0.7:
                self._stats[chain_id].congestion_level = NetworkCongestion.MEDIUM
            elif congestion_ratio < 0.9:
                self._stats[chain_id].congestion_level = NetworkCongestion.HIGH
            else:
                self._stats[chain_id].congestion_level = NetworkCongestion.CRITICAL
    
    async def _process_transaction_callbacks(
        self, 
        transactions: List[MempoolTransaction], 
        chain_id: int
    ) -> None:
        """Process registered transaction callbacks."""
        for callback in self._transaction_callbacks:
            try:
                await callback(transactions, chain_id)
            except Exception as e:
                self.logger.error(f"Transaction callback error: {e}")
    
    async def _process_threat_callbacks(
        self, 
        transaction: MempoolTransaction, 
        threats: List[MEVThreat], 
        chain_id: int
    ) -> None:
        """Process registered threat detection callbacks."""
        for callback in self._threat_callbacks:
            try:
                await callback(transaction, threats, chain_id)
            except Exception as e:
                self.logger.error(f"Threat callback error: {e}")
    
    # =============================================================================
    # PUBLIC API METHODS
    # =============================================================================
    
    def register_transaction_callback(self, callback: Callable) -> None:
        """
        Register callback for new transaction notifications.
        
        Args:
            callback: Async function to call with (transactions, chain_id)
        """
        self._transaction_callbacks.append(callback)
    
    def register_threat_callback(self, callback: Callable) -> None:
        """
        Register callback for MEV threat notifications.
        
        Args:
            callback: Async function to call with (transaction, threats, chain_id)
        """
        self._threat_callbacks.append(callback)
    
    def get_pending_transactions(
        self, 
        chain_id: int, 
        limit: Optional[int] = None
    ) -> List[MempoolTransaction]:
        """
        Get current pending transactions for a chain.
        
        Args:
            chain_id: Blockchain network
            limit: Maximum number of transactions to return
            
        Returns:
            List of pending transactions
        """
        transactions = list(self._pending_transactions[chain_id].values())
        
        # Sort by first seen (most recent first)
        transactions.sort(key=lambda x: x.first_seen, reverse=True)
        
        if limit:
            transactions = transactions[:limit]
        
        return transactions
    
    def get_statistics(self, chain_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get mempool monitoring statistics.
        
        Args:
            chain_id: Specific chain ID or None for all chains
            
        Returns:
            Statistics dictionary
        """
        if chain_id is not None:
            if chain_id in self._stats:
                stats = self._stats[chain_id]
                return {
                    "chain_id": stats.chain_id,
                    "total_transactions_seen": stats.total_transactions_seen,
                    "dex_transactions_seen": stats.dex_transactions_seen,
                    "mev_threats_detected": stats.mev_threats_detected,
                    "current_pending_count": stats.current_pending_count,
                    "avg_processing_latency_ms": stats.avg_processing_latency_ms,
                    "websocket_reconnects": stats.websocket_reconnects,
                    "avg_gas_price_gwei": float(stats.avg_gas_price or 0) / 1e9,
                    "congestion_level": stats.congestion_level.value,
                    "active_providers": [p.value for p in stats.active_providers],
                    "failed_providers": [p.value for p in stats.failed_providers]
                }
            else:
                return {"error": f"No statistics available for chain {chain_id}"}
        else:
            # Return statistics for all chains
            return {
                str(chain_id): self.get_statistics(chain_id)
                for chain_id in self._stats.keys()
            }


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

async def create_mempool_monitor(
    mev_engine: MEVProtectionEngine,
    gas_optimizer: GasOptimizationEngine,
    relay_manager: PrivateRelayManager
) -> MempoolMonitor:
    """
    Factory function to create and initialize a MempoolMonitor.
    
    Args:
        mev_engine: MEV protection engine
        gas_optimizer: Gas optimization engine
        relay_manager: Private relay manager
        
    Returns:
        Fully initialized MempoolMonitor instance
    """
    config = await get_config()
    monitor = MempoolMonitor(config)
    await monitor.initialize(mev_engine, gas_optimizer, relay_manager)
    return monitor


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'MempoolMonitor',
    'MempoolTransaction',
    'MempoolConfig',
    'MempoolStats',
    'MempoolProvider',
    'TransactionStatus',
    'MonitoringMode',
    'create_mempool_monitor'
]