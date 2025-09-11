"""
Discovery Service

Monitors blockchain for new token pairs via WebSocket subscriptions
and HTTP polling fallback. Handles Uniswap V3 PairCreated events
and liquidity addition events for trade opportunity detection.
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

from .config import config, ChainConfig
from .utils import ProviderManager, CircuitBreaker, RateLimiter
from . import EngineStatus

logger = logging.getLogger(__name__)


@dataclass
class NewPairEvent:
    """Represents a new trading pair discovery event."""
    chain_id: int
    pair_address: str
    token0_address: str
    token1_address: str
    fee_tier: int
    pool_address: str
    block_number: int
    transaction_hash: str
    timestamp: datetime
    initial_liquidity_usd: Optional[Decimal] = None
    token0_symbol: Optional[str] = None
    token1_symbol: Optional[str] = None
    is_weth_pair: bool = False


class PairDiscoveryService:
    """
    Service for discovering new trading pairs on DEXs.
    
    Monitors Uniswap V3 factory contracts for PairCreated events
    and tracks liquidity additions to identify trading opportunities.
    """
    
    def __init__(self, chain_config: ChainConfig, pair_callback: Callable[[NewPairEvent], None]):
        """
        Initialize discovery service for a specific chain.
        
        Args:
            chain_config: Configuration for the target blockchain
            pair_callback: Callback function to handle discovered pairs
        """
        self.chain_config = chain_config
        self.pair_callback = pair_callback
        self.provider_manager = ProviderManager(chain_config)
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, timeout=30)
        self.rate_limiter = RateLimiter(max_requests=10, time_window=60)
        
        self.status = EngineStatus.STOPPED
        self.websocket = None
        self.factory_contract = None
        self.last_processed_block = 0
        self.processed_pairs = set()  # Track to avoid duplicates
        
        self.logger = logging.getLogger(f'engine.discovery.{chain_config.name.lower()}')
        
        # Uniswap V3 Factory ABI (simplified for events)
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
        
        # Pool ABI for liquidity tracking
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
            }
        ]
    
    async def start(self) -> None:
        """Start the discovery service."""
        self.logger.info(f"Starting discovery service for {self.chain_config.name}")
        self.status = EngineStatus.STARTING
        
        try:
            # Initialize Web3 connection
            web3 = await self.provider_manager.get_web3()
            if not web3:
                raise Exception("Failed to get Web3 connection")
            
            # Initialize factory contract
            self.factory_contract = web3.eth.contract(
                address=self.chain_config.uniswap_v3_factory,
                abi=self.factory_abi
            )
            
            # Get current block number
            self.last_processed_block = web3.eth.block_number
            self.logger.info(f"Starting from block {self.last_processed_block}")
            
            self.status = EngineStatus.RUNNING
            
            # Start discovery tasks
            if config.discovery_enabled:
                await asyncio.gather(
                    self._websocket_listener(),
                    self._http_polling_task(),
                    return_exceptions=True
                )
            else:
                self.logger.info("Discovery disabled in configuration")
                
        except Exception as e:
            self.logger.error(f"Failed to start discovery service: {e}")
            self.status = EngineStatus.ERROR
            raise
    
    async def stop(self) -> None:
        """Stop the discovery service."""
        self.logger.info("Stopping discovery service")
        self.status = EngineStatus.STOPPING
        
        if self.websocket:
            await self.websocket.close()
        
        await self.provider_manager.close()
        self.status = EngineStatus.STOPPED
    
    async def _websocket_listener(self) -> None:
        """Listen for real-time events via WebSocket."""
        self.logger.info("Starting WebSocket listener")
        
        while self.status == EngineStatus.RUNNING:
            try:
                await self.circuit_breaker.call(self._maintain_websocket_connection)
            except Exception as e:
                self.logger.error(f"WebSocket listener error: {e}")
                await asyncio.sleep(5)  # Wait before retry
    
    async def _maintain_websocket_connection(self) -> None:
        """Maintain WebSocket connection and handle events."""
        primary_provider = config.get_primary_provider(self.chain_config.chain_id)
        if not primary_provider or not primary_provider.websocket_url:
            self.logger.warning("No WebSocket URL configured, skipping WebSocket listener")
            await asyncio.sleep(60)  # Check again later
            return
        
        try:
            self.websocket = await self.provider_manager.websocket_connect(primary_provider.websocket_url)
            if not self.websocket:
                raise Exception("Failed to establish WebSocket connection")
            
            # Subscribe to new blocks and factory events
            await self._subscribe_to_events()
            
            # Listen for messages
            async for message in self.websocket:
                await self._handle_websocket_message(message)
                
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("WebSocket connection closed")
        except Exception as e:
            self.logger.error(f"WebSocket connection error: {e}")
            raise
        finally:
            self.websocket = None
    
    async def _subscribe_to_events(self) -> None:
        """Subscribe to relevant blockchain events."""
        if not self.websocket:
            return
        
        # Subscribe to new blocks
        block_subscription = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_subscribe",
            "params": ["newHeads"]
        }
        await self.websocket.send(json.dumps(block_subscription))
        
        # Subscribe to factory events (PoolCreated)
        factory_subscription = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "eth_subscribe",
            "params": [
                "logs",
                {
                    "address": self.chain_config.uniswap_v3_factory,
                    "topics": ["0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"]  # PoolCreated event signature
                }
            ]
        }
        await self.websocket.send(json.dumps(factory_subscription))
        
        self.logger.info("Subscribed to blockchain events")
    
    async def _handle_websocket_message(self, message: str) -> None:
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(message)
            
            if "params" in data and "result" in data["params"]:
                result = data["params"]["result"]
                
                # Handle new block
                if "number" in result:
                    await self._handle_new_block(result)
                
                # Handle log events (factory events)
                elif "topics" in result:
                    await self._handle_factory_event(result)
                    
        except Exception as e:
            self.logger.error(f"Error handling WebSocket message: {e}")
    
    async def _handle_new_block(self, block_data: Dict[str, Any]) -> None:
        """Handle new block notifications."""
        block_number = int(block_data["number"], 16)
        self.last_processed_block = max(self.last_processed_block, block_number)
        
        # Log periodically to show we're receiving blocks
        if block_number % 10 == 0:
            self.logger.debug(f"Processed block {block_number}")
    
    async def _handle_factory_event(self, log_data: Dict[str, Any]) -> None:
        """Handle Uniswap V3 factory events."""
        try:
            # Decode the PoolCreated event
            web3 = await self.provider_manager.get_web3()
            if not web3:
                return
            
            # Parse event data
            receipt = web3.eth.get_transaction_receipt(log_data["transactionHash"])
            events = self.factory_contract.events.PoolCreated().processReceipt(receipt)
            
            for event in events:
                await self._process_pool_created_event(event, log_data)
                
        except Exception as e:
            self.logger.error(f"Error processing factory event: {e}")
    
    async def _process_pool_created_event(self, event: Any, log_data: Dict[str, Any]) -> None:
        """Process a PoolCreated event."""
        try:
            args = event["args"]
            
            # Create new pair event
            pair_event = NewPairEvent(
                chain_id=self.chain_config.chain_id,
                pair_address=f"{args['token0']}-{args['token1']}-{args['fee']}",  # Unique identifier
                token0_address=args["token0"],
                token1_address=args["token1"],
                fee_tier=args["fee"],
                pool_address=args["pool"],
                block_number=int(log_data["blockNumber"], 16),
                transaction_hash=log_data["transactionHash"],
                timestamp=datetime.now(timezone.utc)
            )
            
            # Check if this is a WETH pair (more likely to be tradeable)
            weth_address = self.chain_config.weth_address.lower()
            pair_event.is_weth_pair = (
                pair_event.token0_address.lower() == weth_address or
                pair_event.token1_address.lower() == weth_address
            )
            
            # Avoid duplicate processing
            if pair_event.pair_address in self.processed_pairs:
                return
            
            self.processed_pairs.add(pair_event.pair_address)
            
            # Enrich with token metadata
            await self._enrich_pair_event(pair_event)
            
            # Send to processing pipeline
            self.logger.info(f"Discovered new pair: {pair_event.token0_symbol}/{pair_event.token1_symbol} (Fee: {pair_event.fee_tier})")
            self.pair_callback(pair_event)
            
        except Exception as e:
            self.logger.error(f"Error processing PoolCreated event: {e}")
    
    async def _enrich_pair_event(self, pair_event: NewPairEvent) -> None:
        """Enrich pair event with additional metadata."""
        try:
            web3 = await self.provider_manager.get_web3()
            if not web3:
                return
            
            # Basic ERC20 ABI for symbol lookup
            erc20_abi = [
                {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"}
            ]
            
            # Get token symbols
            try:
                token0_contract = web3.eth.contract(address=pair_event.token0_address, abi=erc20_abi)
                pair_event.token0_symbol = token0_contract.functions.symbol().call()
            except:
                pair_event.token0_symbol = "UNKNOWN"
            
            try:
                token1_contract = web3.eth.contract(address=pair_event.token1_address, abi=erc20_abi)
                pair_event.token1_symbol = token1_contract.functions.symbol().call()
            except:
                pair_event.token1_symbol = "UNKNOWN"
                
        except Exception as e:
            self.logger.error(f"Error enriching pair event: {e}")
    
    async def _http_polling_task(self) -> None:
        """Fallback HTTP polling for missed events."""
        self.logger.info("Starting HTTP polling task")
        
        while self.status == EngineStatus.RUNNING:
            try:
                await self.rate_limiter.wait_if_needed()
                await self._poll_for_missed_events()
                await asyncio.sleep(config.http_poll_interval)
                
            except Exception as e:
                self.logger.error(f"HTTP polling error: {e}")
                await asyncio.sleep(10)
    
    async def _poll_for_missed_events(self) -> None:
        """Poll for events that may have been missed via WebSocket."""
        web3 = await self.provider_manager.get_web3()
        if not web3:
            return
        
        current_block = web3.eth.block_number
        
        # Only look back a few blocks to catch recent missed events
        from_block = max(self.last_processed_block - 5, 0)
        
        if from_block >= current_block:
            return
        
        try:
            # Get PoolCreated events from recent blocks
            events = self.factory_contract.events.PoolCreated.createFilter(
                fromBlock=from_block,
                toBlock=current_block
            ).get_all_entries()
            
            for event in events:
                # Create log data structure similar to WebSocket
                log_data = {
                    "blockNumber": hex(event["blockNumber"]),
                    "transactionHash": event["transactionHash"].hex(),
                    "topics": [topic.hex() for topic in event["topics"]]
                }
                
                await self._process_pool_created_event(event, log_data)
            
            self.last_processed_block = current_block
            
        except Exception as e:
            self.logger.error(f"Error polling for missed events: {e}")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get discovery service status."""
        provider_health = await self.provider_manager.health_check()
        
        return {
            "service": "discovery",
            "chain": self.chain_config.name,
            "status": self.status,
            "last_processed_block": self.last_processed_block,
            "processed_pairs_count": len(self.processed_pairs),
            "websocket_connected": self.websocket is not None,
            "provider_health": provider_health
        }


class MultiChainDiscoveryManager:
    """
    Manages discovery services across multiple chains.
    
    Coordinates discovery services for all configured chains
    and routes discovered pairs to the risk assessment pipeline.
    """
    
    def __init__(self, pair_callback: Callable[[NewPairEvent], None]):
        """Initialize multi-chain discovery manager."""
        self.pair_callback = pair_callback
        self.discovery_services: Dict[int, PairDiscoveryService] = {}
        self.logger = logging.getLogger('engine.discovery.manager')
        self.status = EngineStatus.STOPPED
    
    async def start(self) -> None:
        """Start discovery services for all configured chains."""
        self.logger.info(f"Starting discovery for {len(config.target_chains)} chains")
        self.status = EngineStatus.STARTING
        
        # Create discovery services for each chain
        for chain_id in config.target_chains:
            chain_config = config.get_chain_config(chain_id)
            if chain_config:
                service = PairDiscoveryService(chain_config, self.pair_callback)
                self.discovery_services[chain_id] = service
        
        # Start all services
        tasks = []
        for chain_id, service in self.discovery_services.items():
            task = asyncio.create_task(service.start())
            tasks.append(task)
        
        self.status = EngineStatus.RUNNING
        
        # Wait for all services to complete (or fail)
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            self.logger.error(f"Discovery manager error: {e}")
            self.status = EngineStatus.ERROR
        finally:
            await self.stop()
    
    async def stop(self) -> None:
        """Stop all discovery services."""
        self.logger.info("Stopping all discovery services")
        self.status = EngineStatus.STOPPING
        
        # Stop all services
        tasks = []
        for service in self.discovery_services.values():
            task = asyncio.create_task(service.stop())
            tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
        self.status = EngineStatus.STOPPED
    
    async def get_status(self) -> Dict[str, Any]:
        """Get status of all discovery services."""
        service_statuses = {}
        
        for chain_id, service in self.discovery_services.items():
            service_statuses[chain_id] = await service.get_status()
        
        return {
            "manager_status": self.status,
            "total_chains": len(self.discovery_services),
            "services": service_statuses
        }