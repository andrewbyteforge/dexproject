"""
Fast Lane Execution Engine

High-speed execution loop optimized for sub-500ms trade execution.
Bypasses Django ORM for direct Web3 connectivity and minimal latency.

File: dexproject/engine/execution/fast_engine.py
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import json
from uuid import uuid4, UUID

# Web3 and blockchain imports
from web3 import Web3
from web3.exceptions import ContractLogicError, TransactionNotFound
from eth_account import Account
from eth_typing import Address, HexStr

# Redis for caching and pub/sub
import redis.asyncio as redis

# Internal imports
from ..config import config
from ..utils import ProviderManager, safe_decimal, format_currency
from .gas_optimizer import GasOptimizer
from .nonce_manager import NonceManager
from ..cache.risk_cache import FastRiskCache


logger = logging.getLogger(__name__)


class FastLaneStatus(Enum):
    """Fast lane engine status states."""
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    ERROR = "ERROR"


class TradeExecutionResult(Enum):
    """Fast lane trade execution results."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    SLIPPAGE_EXCEEDED = "SLIPPAGE_EXCEEDED"


@dataclass
class FastTradeRequest:
    """Fast lane trade request data structure."""
    request_id: str
    pair_address: str
    token_address: str
    token_symbol: str
    chain_id: int
    action: str  # "BUY" or "SELL"
    amount_eth: Decimal
    max_slippage_percent: Decimal
    gas_price_gwei: Optional[Decimal] = None
    priority_fee_gwei: Optional[Decimal] = None
    deadline_seconds: int = 300
    risk_score: Optional[Decimal] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FastExecutionResult:
    """Fast lane execution result data structure."""
    request_id: str
    result: TradeExecutionResult
    transaction_hash: Optional[str] = None
    execution_time_ms: Optional[float] = None
    gas_used: Optional[int] = None
    actual_amount_out: Optional[Decimal] = None
    actual_slippage_percent: Optional[Decimal] = None
    error_message: Optional[str] = None
    block_number: Optional[int] = None
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class FastLaneExecutionEngine:
    """
    High-speed execution engine for time-critical trading opportunities.
    
    Optimized for sub-500ms execution with minimal overhead:
    - Direct Web3 calls bypassing Django ORM
    - In-memory risk caching for instant decisions
    - Async execution with concurrent trade processing
    - Gas optimization and nonce management
    - Real-time performance monitoring
    """
    
    def __init__(self, chain_id: int):
        """
        Initialize fast lane execution engine for specific chain.
        
        Args:
            chain_id: Blockchain network identifier
        """
        self.chain_id = chain_id
        self.status = FastLaneStatus.STOPPED
        self.logger = logging.getLogger(f"{__name__}.chain_{chain_id}")
        
        # Performance tracking
        self.execution_count = 0
        self.success_count = 0
        self.total_execution_time_ms = 0.0
        self.last_execution_time_ms = 0.0
        self.average_execution_time_ms = 0.0
        self.started_at: Optional[datetime] = None
        
        # Execution queue and processing
        self.execution_queue: asyncio.Queue[FastTradeRequest] = asyncio.Queue(maxsize=1000)
        self.pending_executions: Dict[str, FastTradeRequest] = {}
        self.execution_results: Dict[str, FastExecutionResult] = {}
        
        # Core components (initialized in start())
        self.provider_manager: Optional[ProviderManager] = None
        self.web3: Optional[Web3] = None
        self.gas_optimizer: Optional[GasOptimizer] = None
        self.nonce_manager: Optional[NonceManager] = None
        self.risk_cache: Optional[FastRiskCache] = None
        self.redis_client: Optional[redis.Redis] = None
        
        # Wallet configuration
        self.wallet_address: Optional[str] = None
        self.private_key: Optional[str] = None
        
        # Circuit breakers and limits
        self.max_concurrent_trades = 5
        self.max_queue_size = 1000
        self.execution_timeout_ms = 500  # Target max execution time
        self.emergency_stop = False
        
        # Task management
        self.processing_task: Optional[asyncio.Task] = None
        self.monitoring_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
        
        self.logger.info(f"Fast lane engine initialized for chain {chain_id}")
    
    async def start(self) -> bool:
        """
        Start the fast lane execution engine.
        
        Returns:
            True if started successfully, False otherwise
        """
        if self.status != FastLaneStatus.STOPPED:
            self.logger.warning(f"Engine already running with status: {self.status}")
            return False
        
        self.status = FastLaneStatus.STARTING
        self.logger.info("Starting fast lane execution engine...")
        
        try:
            # Initialize core components
            await self._initialize_components()
            
            # Validate wallet configuration
            if not await self._validate_wallet():
                raise ValueError("Wallet validation failed")
            
            # Start background tasks
            self.processing_task = asyncio.create_task(self._process_execution_queue())
            self.monitoring_task = asyncio.create_task(self._monitor_performance())
            self.cleanup_task = asyncio.create_task(self._cleanup_old_results())
            
            self.status = FastLaneStatus.RUNNING
            self.started_at = datetime.now(timezone.utc)
            
            self.logger.info("Fast lane execution engine started successfully")
            return True
            
        except Exception as e:
            self.status = FastLaneStatus.ERROR
            self.logger.error(f"Failed to start fast lane engine: {e}")
            await self._cleanup_on_error()
            return False
    
    async def stop(self) -> bool:
        """
        Stop the fast lane execution engine gracefully.
        
        Returns:
            True if stopped successfully, False otherwise
        """
        if self.status == FastLaneStatus.STOPPED:
            return True
        
        self.status = FastLaneStatus.STOPPING
        self.logger.info("Stopping fast lane execution engine...")
        
        try:
            # Set emergency stop flag
            self.emergency_stop = True
            
            # Cancel background tasks
            tasks_to_cancel = [
                self.processing_task,
                self.monitoring_task,
                self.cleanup_task
            ]
            
            for task in tasks_to_cancel:
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            # Wait for pending executions to complete (with timeout)
            await self._wait_for_pending_executions(timeout_seconds=10)
            
            # Close connections
            if self.redis_client:
                await self.redis_client.close()
            
            self.status = FastLaneStatus.STOPPED
            self.logger.info("Fast lane execution engine stopped successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping fast lane engine: {e}")
            self.status = FastLaneStatus.ERROR
            return False
    
    async def submit_trade(self, trade_request: FastTradeRequest) -> bool:
        """
        Submit a trade request for fast lane execution.
        
        Args:
            trade_request: Trade request to execute
            
        Returns:
            True if submitted successfully, False otherwise
        """
        if self.status != FastLaneStatus.RUNNING:
            self.logger.warning(f"Cannot submit trade - engine status: {self.status}")
            return False
        
        if self.emergency_stop:
            self.logger.warning("Emergency stop active - rejecting trade submission")
            return False
        
        try:
            # Pre-execution validation
            if not await self._validate_trade_request(trade_request):
                return False
            
            # Check queue capacity
            if self.execution_queue.qsize() >= self.max_queue_size:
                self.logger.warning("Execution queue full - rejecting trade")
                return False
            
            # Add to queue
            await self.execution_queue.put(trade_request)
            self.pending_executions[trade_request.request_id] = trade_request
            
            self.logger.debug(f"Trade submitted: {trade_request.request_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error submitting trade: {e}")
            return False
    
    async def get_execution_result(self, request_id: str) -> Optional[FastExecutionResult]:
        """
        Get execution result for a specific trade request.
        
        Args:
            request_id: Trade request identifier
            
        Returns:
            Execution result if available, None otherwise
        """
        return self.execution_results.get(request_id)
    
    async def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive engine status and performance metrics.
        
        Returns:
            Status dictionary with performance metrics
        """
        uptime_seconds = 0
        if self.started_at:
            uptime_seconds = (datetime.now(timezone.utc) - self.started_at).total_seconds()
        
        return {
            "engine": "fast_lane",
            "chain_id": self.chain_id,
            "status": self.status.value,
            "emergency_stop": self.emergency_stop,
            "uptime_seconds": uptime_seconds,
            "queue": {
                "pending": self.execution_queue.qsize(),
                "max_size": self.max_queue_size,
                "pending_executions": len(self.pending_executions)
            },
            "performance": {
                "total_executions": self.execution_count,
                "successful_executions": self.success_count,
                "success_rate_percent": (
                    (self.success_count / self.execution_count * 100) 
                    if self.execution_count > 0 else 0
                ),
                "average_execution_time_ms": self.average_execution_time_ms,
                "last_execution_time_ms": self.last_execution_time_ms,
                "target_execution_time_ms": self.execution_timeout_ms
            },
            "wallet": {
                "address": self.wallet_address,
                "configured": self.wallet_address is not None
            },
            "components": {
                "provider_manager": self.provider_manager is not None,
                "gas_optimizer": self.gas_optimizer is not None,
                "nonce_manager": self.nonce_manager is not None,
                "risk_cache": self.risk_cache is not None,
                "redis": self.redis_client is not None
            }
        }
    
    # =========================================================================
    # PRIVATE METHODS - Initialization and Setup
    # =========================================================================
    
    async def _initialize_components(self) -> None:
        """Initialize all engine components."""
        # Provider manager for Web3 connectivity
        self.provider_manager = ProviderManager(chain_id=self.chain_id)
        self.web3 = await self.provider_manager.get_web3()
        
        # Gas optimization
        self.gas_optimizer = GasOptimizer(chain_id=self.chain_id, web3=self.web3)
        await self.gas_optimizer.start()
        
        # Nonce management
        self.nonce_manager = NonceManager(chain_id=self.chain_id, web3=self.web3)
        await self.nonce_manager.start()
        
        # Fast risk cache
        self.risk_cache = FastRiskCache(chain_id=self.chain_id)
        await self.risk_cache.start()
        
        # Redis connection
        self.redis_client = redis.Redis.from_url(
            config.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        
        self.logger.debug("All components initialized successfully")
    
    async def _validate_wallet(self) -> bool:
        """Validate wallet configuration and connectivity."""
        try:
            # Get wallet configuration from config
            wallet_config = config.get_wallet_config(self.chain_id)
            if not wallet_config:
                self.logger.error("No wallet configuration found")
                return False
            
            self.wallet_address = wallet_config.get("address")
            self.private_key = wallet_config.get("private_key")
            
            if not self.wallet_address or not self.private_key:
                self.logger.error("Wallet address or private key not configured")
                return False
            
            # Validate private key format
            try:
                account = Account.from_key(self.private_key)
                if account.address.lower() != self.wallet_address.lower():
                    self.logger.error("Private key does not match wallet address")
                    return False
            except Exception as e:
                self.logger.error(f"Invalid private key format: {e}")
                return False
            
            # Check wallet balance
            balance_wei = await self.web3.eth.get_balance(self.wallet_address)
            balance_eth = self.web3.from_wei(balance_wei, 'ether')
            
            if balance_eth < Decimal('0.01'):  # Minimum 0.01 ETH for gas
                self.logger.warning(f"Low wallet balance: {balance_eth} ETH")
            
            self.logger.info(f"Wallet validated - Address: {self.wallet_address}, Balance: {balance_eth} ETH")
            return True
            
        except Exception as e:
            self.logger.error(f"Wallet validation failed: {e}")
            return False
    
    # =========================================================================
    # PRIVATE METHODS - Background Task Processing
    # =========================================================================
    
    async def _process_execution_queue(self) -> None:
        """Background task to process trade execution queue."""
        self.logger.info("Started execution queue processing")
        
        while not self.emergency_stop:
            try:
                # Get trade request with timeout
                trade_request = await asyncio.wait_for(
                    self.execution_queue.get(),
                    timeout=1.0
                )
                
                # Execute trade
                await self._execute_trade(trade_request)
                
            except asyncio.TimeoutError:
                # Normal timeout - continue loop
                continue
            except asyncio.CancelledError:
                # Task cancelled - break loop
                break
            except Exception as e:
                self.logger.error(f"Error in execution queue processing: {e}")
                await asyncio.sleep(0.1)  # Brief pause on error
        
        self.logger.info("Execution queue processing stopped")
    
    async def _monitor_performance(self) -> None:
        """Background task to monitor engine performance."""
        self.logger.info("Started performance monitoring")
        
        while not self.emergency_stop:
            try:
                await asyncio.sleep(10)  # Monitor every 10 seconds
                
                # Log performance metrics
                status = await self.get_status()
                performance = status["performance"]
                
                self.logger.info(
                    f"Performance - Executions: {performance['total_executions']}, "
                    f"Success Rate: {performance['success_rate_percent']:.1f}%, "
                    f"Avg Time: {performance['average_execution_time_ms']:.1f}ms"
                )
                
                # Check for performance degradation
                if performance["average_execution_time_ms"] > self.execution_timeout_ms * 1.5:
                    self.logger.warning("Performance degradation detected - execution time exceeding target")
                
                # Publish status to Redis
                if self.redis_client:
                    await self.redis_client.publish(
                        "dex:fast_engine_status",
                        json.dumps(status)
                    )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in performance monitoring: {e}")
        
        self.logger.info("Performance monitoring stopped")
    
    async def _cleanup_old_results(self) -> None:
        """Background task to cleanup old execution results."""
        self.logger.info("Started result cleanup task")
        
        while not self.emergency_stop:
            try:
                await asyncio.sleep(300)  # Cleanup every 5 minutes
                
                # Remove results older than 1 hour
                cutoff_time = datetime.now(timezone.utc).timestamp() - 3600
                
                expired_results = [
                    request_id for request_id, result in self.execution_results.items()
                    if result.completed_at.timestamp() < cutoff_time
                ]
                
                for request_id in expired_results:
                    del self.execution_results[request_id]
                
                if expired_results:
                    self.logger.debug(f"Cleaned up {len(expired_results)} old execution results")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in result cleanup: {e}")
        
        self.logger.info("Result cleanup task stopped")
    
    # =========================================================================
    # PRIVATE METHODS - Trade Execution Core Logic
    # =========================================================================
    
    async def _execute_trade(self, trade_request: FastTradeRequest) -> None:
        """
        Execute a single trade request with performance tracking.
        
        Args:
            trade_request: Trade request to execute
        """
        start_time = time.perf_counter()
        request_id = trade_request.request_id
        
        try:
            self.logger.debug(f"Executing trade: {request_id}")
            
            # Fast risk check using cached data
            risk_check_passed = await self._fast_risk_check(trade_request)
            if not risk_check_passed:
                result = FastExecutionResult(
                    request_id=request_id,
                    result=TradeExecutionResult.REJECTED,
                    error_message="Failed fast risk check"
                )
                await self._store_execution_result(result, start_time)
                return
            
            # Get optimized gas parameters
            gas_params = await self.gas_optimizer.get_optimal_gas_params(
                priority_level="high"
            )
            
            # Execute the actual trade
            if trade_request.action == "BUY":
                result = await self._execute_buy_trade(trade_request, gas_params)
            elif trade_request.action == "SELL":
                result = await self._execute_sell_trade(trade_request, gas_params)
            else:
                result = FastExecutionResult(
                    request_id=request_id,
                    result=TradeExecutionResult.FAILED,
                    error_message=f"Invalid action: {trade_request.action}"
                )
            
            await self._store_execution_result(result, start_time)
            
        except Exception as e:
            self.logger.error(f"Trade execution error for {request_id}: {e}")
            
            result = FastExecutionResult(
                request_id=request_id,
                result=TradeExecutionResult.FAILED,
                error_message=str(e)
            )
            await self._store_execution_result(result, start_time)
        
        finally:
            # Remove from pending executions
            self.pending_executions.pop(request_id, None)
    
    async def _fast_risk_check(self, trade_request: FastTradeRequest) -> bool:
        """
        Perform fast risk check using cached risk data.
        
        Args:
            trade_request: Trade request to validate
            
        Returns:
            True if risk check passes, False otherwise
        """
        try:
            # Check cached risk score
            if trade_request.risk_score is not None:
                if trade_request.risk_score > 80:  # High risk threshold
                    self.logger.warning(f"High risk score: {trade_request.risk_score}")
                    return False
            
            # Check token in risk cache
            risk_data = await self.risk_cache.get_token_risk(trade_request.token_address)
            if risk_data:
                if risk_data.get("is_honeypot", False):
                    self.logger.warning("Token flagged as honeypot")
                    return False
                
                if risk_data.get("is_scam", False):
                    self.logger.warning("Token flagged as scam")
                    return False
            
            # Check position size limits
            max_position_usd = config.get_chain_config(self.chain_id).max_position_size_usd
            trade_value_usd = trade_request.amount_eth * config.eth_price_usd  # Approximate
            
            if trade_value_usd > max_position_usd:
                self.logger.warning(f"Trade size exceeds limit: {trade_value_usd} > {max_position_usd}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Fast risk check error: {e}")
            return False  # Fail safe
    
    async def _execute_buy_trade(
        self, 
        trade_request: FastTradeRequest, 
        gas_params: Dict[str, Any]
    ) -> FastExecutionResult:
        """
        Execute a buy trade on DEX.
        
        Args:
            trade_request: Buy trade request
            gas_params: Optimized gas parameters
            
        Returns:
            Execution result
        """
        # This is a simplified implementation - real implementation would include:
        # - DEX router contract interaction
        # - Swap execution with slippage protection
        # - Transaction signing and broadcasting
        # - Receipt confirmation and parsing
        
        # For now, return a simulated successful execution
        return FastExecutionResult(
            request_id=trade_request.request_id,
            result=TradeExecutionResult.SUCCESS,
            transaction_hash=f"0x{uuid4().hex}",  # Simulated tx hash
            gas_used=150000,  # Typical DEX swap gas usage
            actual_amount_out=trade_request.amount_eth * Decimal('1000'),  # Simulated tokens received
            actual_slippage_percent=Decimal('0.5')  # Simulated slippage
        )
    
    async def _execute_sell_trade(
        self, 
        trade_request: FastTradeRequest, 
        gas_params: Dict[str, Any]
    ) -> FastExecutionResult:
        """
        Execute a sell trade on DEX.
        
        Args:
            trade_request: Sell trade request
            gas_params: Optimized gas parameters
            
        Returns:
            Execution result
        """
        # Similar to buy trade - simplified implementation
        return FastExecutionResult(
            request_id=trade_request.request_id,
            result=TradeExecutionResult.SUCCESS,
            transaction_hash=f"0x{uuid4().hex}",  # Simulated tx hash
            gas_used=120000,  # Typical DEX swap gas usage
            actual_amount_out=trade_request.amount_eth * Decimal('0.99'),  # Simulated ETH received
            actual_slippage_percent=Decimal('1.0')  # Simulated slippage
        )
    
    # =========================================================================
    # PRIVATE METHODS - Utilities and Helpers
    # =========================================================================
    
    async def _validate_trade_request(self, trade_request: FastTradeRequest) -> bool:
        """
        Validate trade request parameters.
        
        Args:
            trade_request: Trade request to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            # Basic validation
            if not trade_request.request_id:
                self.logger.error("Missing request ID")
                return False
            
            if trade_request.action not in ["BUY", "SELL"]:
                self.logger.error(f"Invalid action: {trade_request.action}")
                return False
            
            if trade_request.amount_eth <= 0:
                self.logger.error(f"Invalid amount: {trade_request.amount_eth}")
                return False
            
            if trade_request.max_slippage_percent < 0 or trade_request.max_slippage_percent > 50:
                self.logger.error(f"Invalid slippage: {trade_request.max_slippage_percent}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Trade request validation error: {e}")
            return False
    
    async def _store_execution_result(
        self, 
        result: FastExecutionResult, 
        start_time: float
    ) -> None:
        """
        Store execution result and update performance metrics.
        
        Args:
            result: Execution result to store
            start_time: Execution start time for performance calculation
        """
        # Calculate execution time
        execution_time_ms = (time.perf_counter() - start_time) * 1000
        result.execution_time_ms = execution_time_ms
        
        # Store result
        self.execution_results[result.request_id] = result
        
        # Update performance metrics
        self.execution_count += 1
        self.last_execution_time_ms = execution_time_ms
        self.total_execution_time_ms += execution_time_ms
        self.average_execution_time_ms = self.total_execution_time_ms / self.execution_count
        
        if result.result == TradeExecutionResult.SUCCESS:
            self.success_count += 1
        
        # Log execution result
        self.logger.info(
            f"Trade executed: {result.request_id} - "
            f"Result: {result.result.value}, "
            f"Time: {execution_time_ms:.1f}ms"
        )
        
        # Publish result to Redis
        if self.redis_client:
            try:
                await self.redis_client.publish(
                    "dex:fast_execution_result",
                    json.dumps({
                        "request_id": result.request_id,
                        "result": result.result.value,
                        "execution_time_ms": execution_time_ms,
                        "transaction_hash": result.transaction_hash,
                        "chain_id": self.chain_id
                    })
                )
            except Exception as e:
                self.logger.error(f"Failed to publish result to Redis: {e}")
    
    async def _wait_for_pending_executions(self, timeout_seconds: int = 10) -> None:
        """Wait for pending executions to complete with timeout."""
        start_time = time.time()
        
        while self.pending_executions and (time.time() - start_time) < timeout_seconds:
            await asyncio.sleep(0.1)
        
        if self.pending_executions:
            self.logger.warning(f"Timeout waiting for {len(self.pending_executions)} pending executions")
    
    async def _cleanup_on_error(self) -> None:
        """Cleanup resources on error during startup."""
        try:
            if self.redis_client:
                await self.redis_client.close()
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")