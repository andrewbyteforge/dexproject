"""
Enhanced Discovery Service

Real blockchain integration with WebSocket subscriptions, HTTP polling fallback,
circuit breakers, and comprehensive error handling for production use.

File: dexproject/engine/discovery.py
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import websockets
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import Web3Exception, BlockNotFound, TransactionNotFound
from eth_utils import is_address, to_checksum_address

from .config import config, ChainConfig
from .utils import ProviderManager, setup_logging, get_token_info, get_latest_block
from . import EngineStatus

logger = logging.getLogger(__name__)


@dataclass
class NewPairEvent:
    """Represents a new trading pair discovery event with comprehensive metadata."""
    chain_id: int
    pair_address: str
    token0_address: str
    token1_address: str
    fee_tier: int
    pool_address: str
    block_number: int
    transaction_hash: str
    timestamp: datetime
    tick_spacing: int
    
    # Enriched metadata
    initial_liquidity_usd: Optional[Decimal] = None
    token0_symbol: Optional[str] = None
    token1_symbol: Optional[str] = None
    token0_decimals: Optional[int] = None
    token1_decimals: Optional[int] = None
    is_weth_pair: bool = False
    is_stablecoin_pair: bool = False
    discovery_latency_ms: Optional[float] = None
    
    def get_pair_identifier(self) -> str:
        """Get unique identifier for this pair."""
        return f"{self.chain_id}-{self.token0_address}-{self.token1_address}-{self.fee_tier}"
    
    def is_tradeable(self) -> bool:
        """Check if this pair is likely tradeable."""
        # Prefer WETH pairs for immediate liquidity
        if self.is_weth_pair:
            return True
        
        # Stablecoin pairs are also good for arbitrage
        if self.is_stablecoin_pair:
            return True
        
        # Check if we have minimum metadata
        return (self.token0_symbol and self.token1_symbol and 
                self.token0_symbol != "UNKNOWN" and self.token1_symbol != "UNKNOWN")


class PairDiscoveryService:
    """
    Enhanced service for discovering new trading pairs with real blockchain integration.
    
    Features:
    - Real WebSocket connections with automatic reconnection
    - HTTP polling fallback for missed events
    - Circuit breaker patterns for reliability
    - Comprehensive event enrichment
    - Rate limiting and provider failover
    """
    
    def __init__(self, chain_config: ChainConfig, pair_callback: Callable[[NewPairEvent], None]):
        """
        Initialize enhanced discovery service.
        
        Args:
            chain_config: Configuration for the target blockchain
            pair_callback: Callback function to handle discovered pairs
        """
        self.chain_config = chain_config
        self.pair_callback = pair_callback
        self.provider_manager = ProviderManager(chain_config)
        
        self.status = EngineStatus.STOPPED
        self.last_processed_block = 0
        self.processed_pairs = set()  # Track to avoid duplicates
        self.discovery_start_time = None
        
        # Performance tracking
        self.total_events_processed = 0
        self.successful_discoveries = 0
        self.failed_enrichments = 0
        
        # Event processing queue
        self.event_queue = asyncio.Queue(maxsize=config.event_batch_size * 2)
        self.processing_task = None
        
        self.logger = logging.getLogger(f'engine.discovery.{chain_config.name.lower()}')
        
        # Contract interfaces
        self._initialize_contracts()
        
        # Stablecoin addresses for pair classification
        self.stablecoin_addresses = self._get_stablecoin_addresses()
    
    def _initialize_contracts(self) -> None:
        """Initialize contract ABIs and interfaces."""
        
        # Uniswap V3 Factory ABI (for PoolCreated events)
        self.factory_abi = [
            {
                "anonymous": False,
                "inputs": [
                    {"indexed": True, "name": "token0", "type": "address"},
                    {"indexed": True, "name": "token1", "type": "address"},
                    {"indexed": True, "name": "fee", "type": "uint24"},
                    {"indexed": False, "name": "tickSpacing", "type": "int24"},
                    {"indexed": False, "name": "pool", "type": "address"}
                ],
                "name": "PoolCreated",
                "type": "event"
            }
        ]
        
        # Uniswap V3 Pool ABI (for liquidity events)
        self.pool_abi = [
            {
                "anonymous": False,
                "inputs": [
                    {"indexed": True, "name": "owner", "type": "address"},
                    {"indexed": True, "name": "tickLower", "type": "int24"},
                    {"indexed": True, "name": "tickUpper", "type": "int24"},
                    {"indexed": False, "name": "amount", "type": "uint128"},
                    {"indexed": False, "name": "amount0", "type": "uint256"},
                    {"indexed": False, "name": "amount1", "type": "uint256"}
                ],
                "name": "Mint",
                "type": "event"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "liquidity",
                "outputs": [{"name": "", "type": "uint128"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "slot0",
                "outputs": [
                    {"name": "sqrtPriceX96", "type": "uint160"},
                    {"name": "tick", "type": "int24"},
                    {"name": "observationIndex", "type": "uint16"},
                    {"name": "observationCardinality", "type": "uint16"},
                    {"name": "observationCardinalityNext", "type": "uint16"},
                    {"name": "feeProtocol", "type": "uint8"},
                    {"name": "unlocked", "type": "bool"}
                ],
                "type": "function"
            }
        ]
        
        # ERC20 ABI for token metadata
        self.erc20_abi = [
            {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"},
            {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
            {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
            {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}
        ]
    
    def _get_stablecoin_addresses(self) -> set:
        """Get known stablecoin addresses for the chain."""
        stablecoins = set()
        
        # Add USDC address
        if self.chain_config.usdc_address:
            stablecoins.add(self.chain_config.usdc_address.lower())
        
        # Add other common stablecoins based on chain
        if self.chain_config.chain_id == 1:  # Ethereum
            stablecoins.update([
                "0xa0b86a33e6e67c6e2b2eb44630b58cf95e5e7d77",  # USDC
                "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
                "0x6b175474e89094c44da98b954eedeac495271d0f",  # DAI
                "0x4fabb145d64652a948d72533023f6e7a623c7c53",  # BUSD
                "0x853d955acef822db058eb8505911ed77f175b99e",  # FRAX
            ])
        elif self.chain_config.chain_id == 8453:  # Base
            stablecoins.update([
                "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",  # USDC
                "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca",  # USDbC
            ])
        
        return stablecoins
    
    async def start(self) -> None:
        """Start the enhanced discovery service."""
        self.logger.info(f"Starting enhanced discovery service for {self.chain_config.name}")
        self.status = EngineStatus.STARTING
        self.discovery_start_time = datetime.now(timezone.utc)
        
        try:
            # Initialize Web3 connection using provider manager
            w3 = await self.provider_manager.get_web3()
            if not w3:
                raise Exception("Failed to establish Web3 connection")
            
            # Get current block number
            self.last_processed_block = await get_latest_block(self.provider_manager)
            if not self.last_processed_block:
                raise Exception("Failed to get current block number")
            
            self.logger.info(f"Starting discovery from block {self.last_processed_block}")
            
            self.status = EngineStatus.RUNNING
            
            # Start event processing queue
            self.processing_task = asyncio.create_task(self._event_processor())
            
            # Start discovery tasks if enabled
            if config.discovery_enabled:
                await asyncio.gather(
                    self._websocket_listener(),
                    self._http_polling_task(),
                    return_exceptions=True
                )
            else:
                self.logger.info("Discovery disabled in configuration - entering standby mode")
                while self.status == EngineStatus.RUNNING:
                    await asyncio.sleep(60)
                    
        except Exception as e:
            self.logger.error(f"Failed to start discovery service: {e}")
            self.status = EngineStatus.ERROR
            raise
    
    async def stop(self) -> None:
        """Stop the discovery service with cleanup."""
        self.logger.info("Stopping discovery service")
        self.status = EngineStatus.STOPPING
        
        # Cancel processing task
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
        
        # Clean up provider manager
        await self.provider_manager.close()
        
        self.status = EngineStatus.STOPPED
        self.logger.info("Discovery service stopped")
    
    async def _websocket_listener(self) -> None:
        """Enhanced WebSocket listener with automatic reconnection."""
        self.logger.info("Starting WebSocket listener with automatic reconnection")
        
        async def on_message(message: str) -> None:
            """Handle WebSocket messages."""
            try:
                await self._handle_websocket_message(message)
            except Exception as e:
                self.logger.error(f"Error processing WebSocket message: {e}")
        
        while self.status == EngineStatus.RUNNING:
            try:
                # Use provider manager's WebSocket connection with reconnection
                await self.provider_manager.websocket_connect(on_message)
            except Exception as e:
                self.logger.error(f"WebSocket listener error: {e}")
                await asyncio.sleep(config.websocket_reconnect_delay)
    
    async def _handle_websocket_message(self, message: str) -> None:
        """Handle incoming WebSocket messages with enhanced processing."""
        try:
            data = json.loads(message)
            
            if "params" in data and "result" in data["params"]:
                result = data["params"]["result"]
                
                # Handle new block headers
                if "number" in result:
                    await self._handle_new_block(result)
                
                # Handle log events (factory events)
                elif "topics" in result and "address" in result:
                    await self.event_queue.put(("log_event", result))
                    
        except Exception as e:
            self.logger.error(f"Error handling WebSocket message: {e}")
    
    async def _handle_new_block(self, block_data: Dict[str, Any]) -> None:
        """Handle new block notifications with performance tracking."""
        try:
            block_number = int(block_data["number"], 16)
            self.last_processed_block = max(self.last_processed_block, block_number)
            
            # Log block processing periodically
            if block_number % 20 == 0:
                self.logger.debug(f"Processing block {block_number} on {self.chain_config.name}")
            
            # Update metrics every 100 blocks
            if block_number % 100 == 0:
                await self._log_performance_metrics()
                
        except Exception as e:
            self.logger.error(f"Error handling new block: {e}")
    
    async def _event_processor(self) -> None:
        """Process events from the queue in batches."""
        batch = []
        
        while self.status == EngineStatus.RUNNING:
            try:
                # Collect events for batch processing
                while len(batch) < config.event_batch_size:
                    try:
                        event_type, event_data = await asyncio.wait_for(
                            self.event_queue.get(), timeout=1.0
                        )
                        batch.append((event_type, event_data))
                    except asyncio.TimeoutError:
                        break  # Process current batch
                
                if batch:
                    await self._process_event_batch(batch)
                    batch.clear()
                
            except Exception as e:
                self.logger.error(f"Error in event processor: {e}")
                batch.clear()  # Clear potentially corrupted batch
                await asyncio.sleep(1)
    
    async def _process_event_batch(self, events: List[tuple]) -> None:
        """Process a batch of events efficiently."""
        for event_type, event_data in events:
            try:
                if event_type == "log_event":
                    await self._handle_factory_event(event_data)
                    
                self.total_events_processed += 1
                
            except Exception as e:
                self.logger.error(f"Error processing {event_type}: {e}")
    
    async def _handle_factory_event(self, log_data: Dict[str, Any]) -> None:
        """Handle Uniswap V3 factory events with enhanced error handling."""
        try:
            # Check if this is a PoolCreated event
            pool_created_topic = "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"
            
            if (log_data.get("topics") and 
                len(log_data["topics"]) > 0 and 
                log_data["topics"][0] == pool_created_topic):
                
                await self._process_pool_created_event(log_data)
                
        except Exception as e:
            self.logger.error(f"Error processing factory event: {e}")
    
    async def _process_pool_created_event(self, log_data: Dict[str, Any]) -> None:
        """Process PoolCreated event with comprehensive enrichment."""
        discovery_start = datetime.now(timezone.utc)
        
        try:
            # Decode event using provider manager
            async def decode_event(w3: Web3) -> NewPairEvent:
                # Create factory contract instance
                factory_contract = w3.eth.contract(
                    address=self.chain_config.uniswap_v3_factory,
                    abi=self.factory_abi
                )
                
                # Get transaction receipt
                tx_hash = log_data["transactionHash"]
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                
                # Process the event
                events = factory_contract.events.PoolCreated().processReceipt(receipt)
                
                if not events:
                    raise Exception("No PoolCreated events found in receipt")
                
                event_args = events[0]["args"]
                
                # Create pair event
                pair_event = NewPairEvent(
                    chain_id=self.chain_config.chain_id,
                    pair_address=f"{event_args['token0']}-{event_args['token1']}-{event_args['fee']}",
                    token0_address=to_checksum_address(event_args["token0"]),
                    token1_address=to_checksum_address(event_args["token1"]),
                    fee_tier=event_args["fee"],
                    pool_address=to_checksum_address(event_args["pool"]),
                    tick_spacing=event_args["tickSpacing"],
                    block_number=int(log_data["blockNumber"], 16),
                    transaction_hash=tx_hash,
                    timestamp=datetime.now(timezone.utc)
                )
                
                return pair_event
            
            # Decode the event
            pair_event = await self.provider_manager.execute_with_failover(decode_event)
            if not pair_event:
                self.logger.warning("Failed to decode PoolCreated event")
                return
            
            # Check for duplicates
            pair_id = pair_event.get_pair_identifier()
            if pair_id in self.processed_pairs:
                return
            
            self.processed_pairs.add(pair_id)
            
            # Classify pair type
            await self._classify_pair(pair_event)
            
            # Enrich with token metadata
            await self._enrich_pair_event(pair_event)
            
            # Calculate discovery latency
            discovery_end = datetime.now(timezone.utc)
            pair_event.discovery_latency_ms = (discovery_end - discovery_start).total_seconds() * 1000
            
            # Log discovery
            self.logger.info(
                f"Discovered pair: {pair_event.token0_symbol}/{pair_event.token1_symbol} "
                f"(Fee: {pair_event.fee_tier/10000:.2f}%, Pool: {pair_event.pool_address[:8]}..., "
                f"Latency: {pair_event.discovery_latency_ms:.1f}ms)"
            )
            
            # Send to processing pipeline
            self.pair_callback(pair_event)
            self.successful_discoveries += 1
            
        except Exception as e:
            self.logger.error(f"Error processing PoolCreated event: {e}")
            self.failed_enrichments += 1
    
    async def _classify_pair(self, pair_event: NewPairEvent) -> None:
        """Classify pair type (WETH, stablecoin, etc.)."""
        weth_address = self.chain_config.weth_address.lower()
        
        # Check if WETH pair
        pair_event.is_weth_pair = (
            pair_event.token0_address.lower() == weth_address or
            pair_event.token1_address.lower() == weth_address
        )
        
        # Check if stablecoin pair
        pair_event.is_stablecoin_pair = (
            pair_event.token0_address.lower() in self.stablecoin_addresses or
            pair_event.token1_address.lower() in self.stablecoin_addresses
        )
    
    async def _enrich_pair_event(self, pair_event: NewPairEvent) -> None:
        """Enrich pair event with comprehensive token metadata."""
        try:
            # Get token info for both tokens in parallel
            token0_info, token1_info = await asyncio.gather(
                get_token_info(self.provider_manager, pair_event.token0_address),
                get_token_info(self.provider_manager, pair_event.token1_address),
                return_exceptions=True
            )
            
            # Process token0 info
            if isinstance(token0_info, dict):
                pair_event.token0_symbol = token0_info.get("symbol", "UNKNOWN")
                pair_event.token0_decimals = token0_info.get("decimals", 18)
            else:
                pair_event.token0_symbol = "UNKNOWN"
                pair_event.token0_decimals = 18
                self.logger.debug(f"Failed to get token0 info: {token0_info}")
            
            # Process token1 info
            if isinstance(token1_info, dict):
                pair_event.token1_symbol = token1_info.get("symbol", "UNKNOWN")
                pair_event.token1_decimals = token1_info.get("decimals", 18)
            else:
                pair_event.token1_symbol = "UNKNOWN"
                pair_event.token1_decimals = 18
                self.logger.debug(f"Failed to get token1 info: {token1_info}")
            
            # Try to get initial liquidity (optional, might fail for new pools)
            try:
                await self._get_initial_liquidity(pair_event)
            except Exception as e:
                self.logger.debug(f"Could not get initial liquidity for new pair: {e}")
                
        except Exception as e:
            self.logger.error(f"Error enriching pair event: {e}")
            # Set defaults
            pair_event.token0_symbol = "UNKNOWN"
            pair_event.token1_symbol = "UNKNOWN"
            pair_event.token0_decimals = 18
            pair_event.token1_decimals = 18
    
    async def _get_initial_liquidity(self, pair_event: NewPairEvent) -> None:
        """Get initial liquidity for the pool (if available)."""
        async def get_liquidity(w3: Web3) -> Optional[Decimal]:
            pool_contract = w3.eth.contract(
                address=pair_event.pool_address,
                abi=self.pool_abi
            )
            
            try:
                liquidity = pool_contract.functions.liquidity().call()
                if liquidity > 0:
                    # This is a rough approximation - actual USD value calculation 
                    # would require price feeds
                    return Decimal(str(liquidity))
            except:
                pass
            
            return None
        
        liquidity = await self.provider_manager.execute_with_failover(get_liquidity)
        if liquidity:
            pair_event.initial_liquidity_usd = liquidity
    
    async def _http_polling_task(self) -> None:
        """HTTP polling fallback for missed events."""
        self.logger.info("Starting HTTP polling fallback task")
        
        while self.status == EngineStatus.RUNNING:
            try:
                await self._poll_for_missed_events()
                await asyncio.sleep(config.http_poll_interval)
                
            except Exception as e:
                self.logger.error(f"HTTP polling error: {e}")
                await asyncio.sleep(min(config.http_poll_interval * 2, 60))
    
    async def _poll_for_missed_events(self) -> None:
        """Poll for events that may have been missed via WebSocket."""
        async def poll_events(w3: Web3) -> None:
            current_block = w3.eth.block_number
            
            # Look back a few blocks to catch missed events
            from_block = max(self.last_processed_block - 10, 0)
            
            if from_block >= current_block:
                return
            
            # Create factory contract
            factory_contract = w3.eth.contract(
                address=self.chain_config.uniswap_v3_factory,
                abi=self.factory_abi
            )
            
            # Get recent PoolCreated events
            try:
                events = factory_contract.events.PoolCreated.createFilter(
                    fromBlock=from_block,
                    toBlock=current_block
                ).get_all_entries()
                
                for event in events:
                    # Create synthetic log data for processing
                    log_data = {
                        "blockNumber": hex(event["blockNumber"]),
                        "transactionHash": event["transactionHash"].hex(),
                        "topics": [topic.hex() for topic in event["topics"]],
                        "address": event["address"]
                    }
                    
                    await self.event_queue.put(("log_event", log_data))
                
                if events:
                    self.logger.debug(f"HTTP polling found {len(events)} missed events")
                
                self.last_processed_block = current_block
                
            except Exception as e:
                self.logger.debug(f"HTTP polling query failed: {e}")
        
        await self.provider_manager.execute_with_failover(poll_events)
    
    async def _log_performance_metrics(self) -> None:
        """Log performance metrics for monitoring."""
        if self.discovery_start_time:
            uptime = (datetime.now(timezone.utc) - self.discovery_start_time).total_seconds()
            events_per_second = self.total_events_processed / max(uptime, 1)
            
            self.logger.info(
                f"Discovery metrics: {self.total_events_processed} events processed, "
                f"{self.successful_discoveries} pairs discovered, "
                f"{self.failed_enrichments} enrichment failures, "
                f"{events_per_second:.2f} events/sec"
            )
    
    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive discovery service status."""
        health_summary = self.provider_manager.get_health_summary()
        
        uptime_seconds = 0
        if self.discovery_start_time:
            uptime_seconds = (datetime.now(timezone.utc) - self.discovery_start_time).total_seconds()
        
        return {
            "service": "discovery",
            "chain": self.chain_config.name,
            "chain_id": self.chain_config.chain_id,
            "status": self.status.value,
            "uptime_seconds": uptime_seconds,
            "last_processed_block": self.last_processed_block,
            "total_events_processed": self.total_events_processed,
            "successful_discoveries": self.successful_discoveries,
            "failed_enrichments": self.failed_enrichments,
            "processed_pairs_count": len(self.processed_pairs),
            "event_queue_size": self.event_queue.qsize(),
            "provider_health": health_summary
        }


class MultiChainDiscoveryManager:
    """
    Enhanced manager for coordinating discovery across multiple chains.
    
    Manages discovery services for all configured chains and provides
    unified monitoring and control interfaces.
    """
    
    def __init__(self, pair_callback: Callable[[NewPairEvent], None]):
        """Initialize multi-chain discovery manager."""
        self.pair_callback = pair_callback
        self.discovery_services: Dict[int, PairDiscoveryService] = {}
        self.status = EngineStatus.STOPPED
        
        self.logger = logging.getLogger('engine.discovery.manager')
        
        # Initialize discovery services for each configured chain
        for chain_id in config.target_chains:
            chain_config = config.get_chain_config(chain_id)
            if chain_config:
                service = PairDiscoveryService(chain_config, self._handle_discovered_pair)
                self.discovery_services[chain_id] = service
            else:
                self.logger.error(f"No configuration found for chain ID: {chain_id}")
    
    def _handle_discovered_pair(self, pair_event: NewPairEvent) -> None:
        """Handle discovered pairs with additional filtering."""
        try:
            # Apply filtering logic
            if not pair_event.is_tradeable():
                self.logger.debug(f"Skipping non-tradeable pair: {pair_event.pair_address}")
                return
            
            # Rate limiting check
            if self._should_rate_limit():
                self.logger.warning(f"Rate limiting discovery - skipping pair: {pair_event.pair_address}")
                return
            
            # Forward to callback
            self.pair_callback(pair_event)
            
        except Exception as e:
            self.logger.error(f"Error handling discovered pair: {e}")
    
    def _should_rate_limit(self) -> bool:
        """Check if we should rate limit new discoveries."""
        # Implement rate limiting logic based on config.max_pairs_per_hour
        # This is a placeholder - implement proper rate limiting
        return False
    
    async def start(self) -> None:
        """Start all discovery services."""
        self.logger.info(f"Starting multi-chain discovery for {len(self.discovery_services)} chains")
        self.status = EngineStatus.STARTING
        
        try:
            # Start all discovery services in parallel
            start_tasks = [
                service.start() for service in self.discovery_services.values()
            ]
            
            if start_tasks:
                await asyncio.gather(*start_tasks, return_exceptions=True)
            
            self.status = EngineStatus.RUNNING
            self.logger.info("Multi-chain discovery started successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to start multi-chain discovery: {e}")
            self.status = EngineStatus.ERROR
            raise
    
    async def stop(self) -> None:
        """Stop all discovery services."""
        self.logger.info("Stopping multi-chain discovery")
        self.status = EngineStatus.STOPPING
        
        # Stop all services in parallel
        stop_tasks = [
            service.stop() for service in self.discovery_services.values()
        ]
        
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)
        
        self.status = EngineStatus.STOPPED
        self.logger.info("Multi-chain discovery stopped")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status for all discovery services."""
        services_status = {}
        
        for chain_id, service in self.discovery_services.items():
            services_status[str(chain_id)] = await service.get_status()
        
        return {
            "manager_status": self.status.value,
            "total_chains": len(self.discovery_services),
            "services": services_status
        }
    
    def get_service(self, chain_id: int) -> Optional[PairDiscoveryService]:
        """Get discovery service for a specific chain."""
        return self.discovery_services.get(chain_id)