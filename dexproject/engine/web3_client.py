"""
Web3 Client Implementation for DEX Auto-Trading Bot

This module provides the core Web3 client functionality with automatic
provider failover, connection management, and blockchain interaction.
Integrates with the existing ProviderManager for reliable connectivity.

File: dexproject/engine/web3_client.py
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Union, Tuple, Callable
from decimal import Decimal
from dataclasses import dataclass
from contextlib import asynccontextmanager

from web3 import Web3
from web3.exceptions import Web3Exception, BlockNotFound, TransactionNotFound
from web3.types import BlockData, TxData, LogReceipt, FilterParams
from web3.contract import Contract
from eth_utils import to_checksum_address, is_address
from eth_typing import Address, HexStr, ChecksumAddress
import websockets
import json

from .config import ChainConfig, config
from .utils import ProviderManager

logger = logging.getLogger(__name__)


@dataclass
class TokenInfo:
    """Token information retrieved from blockchain."""
    address: ChecksumAddress
    symbol: str
    name: str
    decimals: int
    total_supply: int
    is_verified: bool = False
    
    def __post_init__(self):
        """Validate token info after initialization."""
        if not is_address(self.address):
            raise ValueError(f"Invalid token address: {self.address}")
        if self.decimals < 0 or self.decimals > 77:
            raise ValueError(f"Invalid decimals: {self.decimals}")


@dataclass
class PairInfo:
    """Trading pair information from Uniswap."""
    pair_address: ChecksumAddress
    token0: TokenInfo
    token1: TokenInfo
    fee_tier: int
    liquidity: int
    sqrt_price_x96: int
    tick: int
    protocol: str  # 'uniswap_v2' or 'uniswap_v3'
    
    def get_price_ratio(self) -> Decimal:
        """Calculate price ratio for this pair."""
        if self.protocol == 'uniswap_v3' and self.sqrt_price_x96:
            # Convert from sqrt price to actual price
            price_ratio = (self.sqrt_price_x96 / (2**96)) ** 2
            return Decimal(str(price_ratio))
        return Decimal('0')


class Web3Client:
    """
    Production-ready Web3 client with automatic failover and comprehensive error handling.
    
    Features:
    - Automatic provider failover through ProviderManager
    - Connection health monitoring and recovery
    - Rate limiting and request optimization
    - Comprehensive error handling with retries
    - Real-time event subscription capabilities
    - Token and pair information retrieval
    - Gas estimation and transaction utilities
    """
    
    def __init__(self, chain_config: ChainConfig):
        """
        Initialize Web3 client with automatic provider management.
        
        Args:
            chain_config: Chain configuration with RPC providers
        """
        self.chain_config = chain_config
        self.provider_manager = ProviderManager(chain_config)
        self.logger = logging.getLogger(f'engine.web3.{chain_config.name.lower()}')
        
        # Connection state
        self._current_web3: Optional[Web3] = None
        self._is_connected = False
        self._connection_lock = asyncio.Lock()
        
        # WebSocket connection for real-time events
        self._websocket: Optional[websockets.WebSocketServerProtocol] = None
        self._ws_subscriptions: Dict[str, str] = {}  # subscription_id -> filter_id
        self._event_handlers: Dict[str, Callable] = {}
        
        # Performance tracking
        self._total_requests = 0
        self._failed_requests = 0
        self._last_request_time = 0.0
        
        # Standard contract ABIs for common operations
        self._initialize_contract_abis()
        
        self.logger.info(f"Initialized Web3Client for {chain_config.name}")
    
    def _initialize_contract_abis(self) -> None:
        """Initialize standard contract ABIs for common operations."""
        
        # ERC20 Token ABI (minimal)
        self.erc20_abi = [
            {
                "constant": True,
                "inputs": [],
                "name": "name",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "symbol",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "totalSupply",
                "outputs": [{"name": "", "type": "uint256"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            }
        ]
        
        # Uniswap V3 Pool ABI (minimal)
        self.uniswap_v3_pool_abi = [
            {
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
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "liquidity",
                "outputs": [{"name": "", "type": "uint128"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "token0",
                "outputs": [{"name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "token1",
                "outputs": [{"name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "fee",
                "outputs": [{"name": "", "type": "uint24"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        # Uniswap V3 Factory ABI (for PoolCreated events)
        self.uniswap_v3_factory_abi = [
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
            },
            {
                "inputs": [
                    {"name": "tokenA", "type": "address"},
                    {"name": "tokenB", "type": "address"},
                    {"name": "fee", "type": "uint24"}
                ],
                "name": "getPool",
                "outputs": [{"name": "pool", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        # Uniswap V2 Pair ABI (minimal)
        self.uniswap_v2_pair_abi = [
            {
                "constant": True,
                "inputs": [],
                "name": "getReserves",
                "outputs": [
                    {"name": "reserve0", "type": "uint112"},
                    {"name": "reserve1", "type": "uint112"},
                    {"name": "blockTimestampLast", "type": "uint32"}
                ],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "token0",
                "outputs": [{"name": "", "type": "address"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "token1",
                "outputs": [{"name": "", "type": "address"}],
                "type": "function"
            }
        ]

    async def connect(self) -> bool:
        """
        Establish connection to blockchain with automatic provider selection.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        async with self._connection_lock:
            try:
                # Get Web3 instance from provider manager
                self._current_web3 = await self.provider_manager.get_web3()
                
                if self._current_web3 and self._current_web3.is_connected():
                    self._is_connected = True
                    
                    # Test connection with a simple call
                    block_number = await self.get_latest_block_number()
                    if block_number > 0:
                        self.logger.info(
                            f"✅ Connected to {self.chain_config.name} at block {block_number} "
                            f"via {self.provider_manager.current_provider}"
                        )
                        return True
                
                self._is_connected = False
                self.logger.error(f"❌ Failed to connect to {self.chain_config.name}")
                return False
                
            except Exception as e:
                self._is_connected = False
                self.logger.error(f"Connection error for {self.chain_config.name}: {e}")
                return False

    async def disconnect(self) -> None:
        """Clean up connections and resources."""
        async with self._connection_lock:
            self._is_connected = False
            
            # Close WebSocket connections
            if self._websocket:
                try:
                    await self._websocket.close()
                except Exception as e:
                    self.logger.warning(f"Error closing WebSocket: {e}")
                finally:
                    self._websocket = None
            
            # Clean up provider manager
            await self.provider_manager.close()
            
            self.logger.info(f"Disconnected from {self.chain_config.name}")

    @property
    def is_connected(self) -> bool:
        """Check if client is connected to blockchain."""
        return self._is_connected and self._current_web3 is not None

    @property
    def web3(self) -> Optional[Web3]:
        """Get current Web3 instance."""
        return self._current_web3

    async def _ensure_connection(self) -> Web3:
        """Ensure connection is active, reconnect if necessary."""
        if not self.is_connected:
            success = await self.connect()
            if not success:
                raise Web3Exception(f"Failed to connect to {self.chain_config.name}")
        
        return self._current_web3

    async def _execute_with_retry(self, operation: Callable, *args, **kwargs) -> Any:
        """Execute operation with automatic retry and failover."""
        last_exception = None
        
        for attempt in range(3):  # Max 3 attempts
            try:
                w3 = await self._ensure_connection()
                self._total_requests += 1
                self._last_request_time = time.time()
                
                # Execute the operation
                if asyncio.iscoroutinefunction(operation):
                    result = await operation(w3, *args, **kwargs)
                else:
                    result = operation(w3, *args, **kwargs)
                
                return result
                
            except Exception as e:
                last_exception = e
                self._failed_requests += 1
                self.logger.warning(f"Request failed (attempt {attempt + 1}/3): {e}")
                
                # Trigger provider failover on connection issues
                if "connection" in str(e).lower() or "timeout" in str(e).lower():
                    self._is_connected = False
                
                # Wait before retry
                if attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
        
        # All retries failed
        raise Web3Exception(f"All retry attempts failed. Last error: {last_exception}")

    # ====================
    # BLOCKCHAIN DATA RETRIEVAL
    # ====================

    async def get_latest_block_number(self) -> int:
        """Get the latest block number."""
        async def _get_block_number(w3: Web3) -> int:
            return w3.eth.block_number
        
        return await self._execute_with_retry(_get_block_number)

    async def get_block(self, block_identifier: Union[int, str, HexStr]) -> BlockData:
        """Get block data by number or hash."""
        async def _get_block(w3: Web3, block_id: Union[int, str, HexStr]) -> BlockData:
            return w3.eth.get_block(block_id, full_transactions=False)
        
        return await self._execute_with_retry(_get_block, block_identifier)

    async def get_transaction(self, tx_hash: HexStr) -> TxData:
        """Get transaction data by hash."""
        async def _get_transaction(w3: Web3, hash: HexStr) -> TxData:
            return w3.eth.get_transaction(hash)
        
        return await self._execute_with_retry(_get_transaction, tx_hash)

    async def get_logs(self, filter_params: FilterParams) -> List[LogReceipt]:
        """Get logs matching the filter parameters."""
        async def _get_logs(w3: Web3, params: FilterParams) -> List[LogReceipt]:
            return w3.eth.get_logs(params)
        
        return await self._execute_with_retry(_get_logs, filter_params)

    async def call_contract_function(
        self, 
        contract_address: ChecksumAddress, 
        function_abi: Dict[str, Any], 
        function_inputs: List[Any] = None,
        block_identifier: Union[int, str] = 'latest'
    ) -> Any:
        """Call a read-only contract function."""
        async def _call_function(
            w3: Web3, 
            addr: ChecksumAddress, 
            abi: Dict[str, Any], 
            inputs: List[Any], 
            block: Union[int, str]
        ) -> Any:
            contract = w3.eth.contract(address=addr, abi=[abi])
            function_name = abi['name']
            contract_function = getattr(contract.functions, function_name)
            
            if inputs:
                return contract_function(*inputs).call(block_identifier=block)
            else:
                return contract_function().call(block_identifier=block)
        
        return await self._execute_with_retry(
            _call_function, 
            contract_address, 
            function_abi, 
            function_inputs or [], 
            block_identifier
        )

    # ====================
    # TOKEN OPERATIONS
    # ====================

    async def get_token_info(self, token_address: str) -> Optional[TokenInfo]:
        """
        Get comprehensive token information from blockchain.
        
        Args:
            token_address: Token contract address
            
        Returns:
            TokenInfo object or None if token is invalid
        """
        try:
            # Validate and checksum address
            if not is_address(token_address):
                self.logger.warning(f"Invalid token address: {token_address}")
                return None
            
            address = to_checksum_address(token_address)
            
            # Check if contract exists
            w3 = await self._ensure_connection()
            code = w3.eth.get_code(address)
            if not code or code == b'':
                self.logger.warning(f"No contract code at address: {address}")
                return None
            
            # Get token information using contract calls
            contract = w3.eth.contract(address=address, abi=self.erc20_abi)
            
            # Execute multiple calls concurrently
            tasks = [
                self._safe_contract_call(contract.functions.symbol().call, "UNKNOWN"),
                self._safe_contract_call(contract.functions.name().call, "Unknown Token"),
                self._safe_contract_call(contract.functions.decimals().call, 18),
                self._safe_contract_call(contract.functions.totalSupply().call, 0)
            ]
            
            symbol, name, decimals, total_supply = await asyncio.gather(*tasks)
            
            # Create TokenInfo object
            token_info = TokenInfo(
                address=address,
                symbol=symbol,
                name=name,
                decimals=decimals,
                total_supply=total_supply,
                is_verified=await self._check_token_verification(address)
            )
            
            self.logger.debug(f"Retrieved token info for {symbol}: {name}")
            return token_info
            
        except Exception as e:
            self.logger.error(f"Failed to get token info for {token_address}: {e}")
            return None

    async def _safe_contract_call(self, call_func: Callable, default_value: Any) -> Any:
        """Execute contract call with error handling and default value."""
        try:
            return call_func()
        except Exception as e:
            self.logger.debug(f"Contract call failed, using default: {e}")
            return default_value

    async def _check_token_verification(self, token_address: ChecksumAddress) -> bool:
        """Check if token is verified (simplified implementation)."""
        # In production, this could check against verification services
        # For now, we'll consider well-known tokens as verified
        well_known_tokens = {
            self.chain_config.weth_address.lower(),
            self.chain_config.usdc_address.lower(),
        }
        
        return token_address.lower() in well_known_tokens

    async def get_token_balance(self, token_address: str, wallet_address: str) -> int:
        """Get token balance for a specific wallet."""
        try:
            token_addr = to_checksum_address(token_address)
            wallet_addr = to_checksum_address(wallet_address)
            
            balance_abi = {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            }
            
            balance = await self.call_contract_function(
                token_addr, 
                balance_abi, 
                [wallet_addr]
            )
            
            return balance
            
        except Exception as e:
            self.logger.error(f"Failed to get token balance: {e}")
            return 0

    # ====================
    # UNISWAP OPERATIONS
    # ====================

    async def get_uniswap_v3_pool_info(self, pool_address: str) -> Optional[PairInfo]:
        """Get Uniswap V3 pool information."""
        try:
            pool_addr = to_checksum_address(pool_address)
            w3 = await self._ensure_connection()
            pool_contract = w3.eth.contract(address=pool_addr, abi=self.uniswap_v3_pool_abi)
            
            # Get pool data concurrently
            tasks = [
                self._safe_contract_call(pool_contract.functions.token0().call, None),
                self._safe_contract_call(pool_contract.functions.token1().call, None),
                self._safe_contract_call(pool_contract.functions.fee().call, 0),
                self._safe_contract_call(pool_contract.functions.liquidity().call, 0),
                self._safe_contract_call(pool_contract.functions.slot0().call, (0, 0, 0, 0, 0, 0, False))
            ]
            
            token0_addr, token1_addr, fee, liquidity, slot0 = await asyncio.gather(*tasks)
            
            if not token0_addr or not token1_addr:
                return None
            
            # Get token information
            token0_info = await self.get_token_info(token0_addr)
            token1_info = await self.get_token_info(token1_addr)
            
            if not token0_info or not token1_info:
                return None
            
            # Extract slot0 data
            sqrt_price_x96, tick = slot0[0], slot0[1]
            
            return PairInfo(
                pair_address=pool_addr,
                token0=token0_info,
                token1=token1_info,
                fee_tier=fee,
                liquidity=liquidity,
                sqrt_price_x96=sqrt_price_x96,
                tick=tick,
                protocol='uniswap_v3'
            )
            
        except Exception as e:
            self.logger.error(f"Failed to get Uniswap V3 pool info: {e}")
            return None

    async def get_uniswap_v2_pair_info(self, pair_address: str) -> Optional[PairInfo]:
        """Get Uniswap V2 pair information."""
        try:
            pair_addr = to_checksum_address(pair_address)
            w3 = await self._ensure_connection()
            pair_contract = w3.eth.contract(address=pair_addr, abi=self.uniswap_v2_pair_abi)
            
            # Get pair data
            tasks = [
                self._safe_contract_call(pair_contract.functions.token0().call, None),
                self._safe_contract_call(pair_contract.functions.token1().call, None),
                self._safe_contract_call(pair_contract.functions.getReserves().call, (0, 0, 0))
            ]
            
            token0_addr, token1_addr, reserves = await asyncio.gather(*tasks)
            
            if not token0_addr or not token1_addr:
                return None
            
            # Get token information
            token0_info = await self.get_token_info(token0_addr)
            token1_info = await self.get_token_info(token1_addr)
            
            if not token0_info or not token1_info:
                return None
            
            reserve0, reserve1 = reserves[0], reserves[1]
            
            return PairInfo(
                pair_address=pair_addr,
                token0=token0_info,
                token1=token1_info,
                fee_tier=3000,  # V2 has fixed 0.3% fee
                liquidity=reserve0 + reserve1,  # Simplified liquidity calculation
                sqrt_price_x96=0,  # V2 doesn't use sqrt pricing
                tick=0,  # V2 doesn't use ticks
                protocol='uniswap_v2'
            )
            
        except Exception as e:
            self.logger.error(f"Failed to get Uniswap V2 pair info: {e}")
            return None

    # ====================
    # EVENT SUBSCRIPTIONS
    # ====================

    async def subscribe_to_new_blocks(self, callback: Callable[[BlockData], None]) -> str:
        """Subscribe to new block events."""
        subscription_id = f"blocks_{int(time.time())}"
        
        async def block_listener():
            last_block = await self.get_latest_block_number()
            
            while subscription_id in self._event_handlers:
                try:
                    current_block = await self.get_latest_block_number()
                    
                    if current_block > last_block:
                        # Get new blocks
                        for block_num in range(last_block + 1, current_block + 1):
                            block_data = await self.get_block(block_num)
                            if callback:
                                await callback(block_data)
                        
                        last_block = current_block
                    
                    # Wait for next block
                    await asyncio.sleep(self.chain_config.block_time_ms / 1000)
                    
                except Exception as e:
                    self.logger.error(f"Block subscription error: {e}")
                    await asyncio.sleep(5)
        
        self._event_handlers[subscription_id] = asyncio.create_task(block_listener())
        return subscription_id

    async def subscribe_to_contract_events(
        self, 
        contract_address: str, 
        event_abi: Dict[str, Any],
        callback: Callable[[LogReceipt], None],
        from_block: Union[int, str] = 'latest'
    ) -> str:
        """Subscribe to specific contract events."""
        subscription_id = f"events_{contract_address}_{int(time.time())}"
        
        async def event_listener():
            last_block = await self.get_latest_block_number() if from_block == 'latest' else from_block
            
            while subscription_id in self._event_handlers:
                try:
                    current_block = await self.get_latest_block_number()
                    
                    if current_block > last_block:
                        # Get logs for new blocks
                        filter_params = {
                            'address': to_checksum_address(contract_address),
                            'fromBlock': last_block + 1,
                            'toBlock': current_block,
                            'topics': [Web3.keccak(text=f"{event_abi['name']}(...)").hex()]
                        }
                        
                        logs = await self.get_logs(filter_params)
                        for log in logs:
                            if callback:
                                await callback(log)
                        
                        last_block = current_block
                    
                    await asyncio.sleep(2)  # Check every 2 seconds
                    
                except Exception as e:
                    self.logger.error(f"Event subscription error: {e}")
                    await asyncio.sleep(5)
        
        self._event_handlers[subscription_id] = asyncio.create_task(event_listener())
        return subscription_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from events."""
        if subscription_id in self._event_handlers:
            task = self._event_handlers.pop(subscription_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return True
        return False

    # ====================
    # UTILITIES
    # ====================

    async def estimate_gas(
        self, 
        to_address: str, 
        data: str = None, 
        value: int = 0,
        from_address: str = None
    ) -> int:
        """Estimate gas for a transaction."""
        async def _estimate_gas(w3: Web3, to: str, data_hex: str, val: int, from_addr: str) -> int:
            tx_params = {
                'to': to_checksum_address(to),
                'value': val
            }
            
            if data_hex:
                tx_params['data'] = data_hex
            if from_addr:
                tx_params['from'] = to_checksum_address(from_addr)
            
            return w3.eth.estimate_gas(tx_params)
        
        return await self._execute_with_retry(_estimate_gas, to_address, data, value, from_address)

    async def get_gas_price(self) -> int:
        """Get current gas price."""
        async def _get_gas_price(w3: Web3) -> int:
            return w3.eth.gas_price
        
        return await self._execute_with_retry(_get_gas_price)

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get client performance statistics."""
        success_rate = 0.0
        if self._total_requests > 0:
            success_rate = ((self._total_requests - self._failed_requests) / self._total_requests) * 100
        
        return {
            'chain_name': self.chain_config.name,
            'chain_id': self.chain_config.chain_id,
            'is_connected': self.is_connected,
            'current_provider': self.provider_manager.current_provider,
            'total_requests': self._total_requests,
            'failed_requests': self._failed_requests,
            'success_rate_percent': round(success_rate, 2),
            'last_request_time': self._last_request_time,
            'provider_health': self.provider_manager.get_health_summary()
        }

    @asynccontextmanager
    async def connection_context(self):
        """Context manager for ensuring connection lifecycle."""
        try:
            if not self.is_connected:
                await self.connect()
            yield self
        finally:
            # Note: We don't disconnect here as the client might be used elsewhere
            # Call disconnect() explicitly when completely done
            pass

    def __repr__(self) -> str:
        """String representation of Web3Client."""
        status = "Connected" if self.is_connected else "Disconnected"
        provider = self.provider_manager.current_provider or "None"
        return f"Web3Client({self.chain_config.name}, {status}, Provider: {provider})"


# ====================
# CONVENIENCE FUNCTIONS
# ====================

async def create_web3_client(chain_id: int) -> Optional[Web3Client]:
    """
    Convenience function to create and connect a Web3Client.
    
    Args:
        chain_id: Target blockchain chain ID
        
    Returns:
        Connected Web3Client or None if failed
    """
    chain_config = config.get_chain_config(chain_id)
    if not chain_config:
        logger.error(f"No configuration found for chain ID: {chain_id}")
        return None
    
    client = Web3Client(chain_config)
    success = await client.connect()
    
    if success:
        return client
    else:
        await client.disconnect()
        return None


async def get_token_info_simple(chain_id: int, token_address: str) -> Optional[TokenInfo]:
    """
    Simple function to get token information.
    
    Args:
        chain_id: Target blockchain chain ID
        token_address: Token contract address
        
    Returns:
        TokenInfo object or None if failed
    """
    client = await create_web3_client(chain_id)
    if not client:
        return None
    
    try:
        return await client.get_token_info(token_address)
    finally:
        await client.disconnect()