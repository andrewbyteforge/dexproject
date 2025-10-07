"""
Transaction Manager Service - Phase 6B Core Component with Enhanced Retry Logic

Central coordinator for all trading transaction operations, integrating gas optimization,
DEX routing, real-time status tracking, and comprehensive retry logic with gas escalation.

This service bridges the excellent Phase 6A gas optimizer with DEX execution and provides
real-time WebSocket updates for transaction status monitoring.

ENHANCED: Added complete retry logic with gas escalation, exponential backoff, and circuit breaker

File: dexproject/trading/services/transaction_manager.py
"""

import logging
import asyncio
import json
import time
from typing import Dict, Any, Optional, Callable, List, Tuple
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict, field
from enum import Enum

from django.contrib.auth.models import User
from django.conf import settings

# WebSocket functionality - optional dependency
try:
    from channels.layers import get_channel_layer
    CHANNELS_AVAILABLE = True
except ImportError:
    CHANNELS_AVAILABLE = False
    get_channel_layer = None

from eth_typing import ChecksumAddress, HexStr
from web3.types import TxReceipt

from engine.config import ChainConfig
from engine.web3_client import Web3Client
from engine.wallet_manager import WalletManager

# Import existing services for integration
from .dex_router_service import (
    DEXRouterService,
    SwapParams,
    SwapResult,
    SwapType,
    DEXVersion,
    create_dex_router_service
)
from .gas_optimizer import (
    optimize_trade_gas,
    TradingGasStrategy,
    GasOptimizationResult,
    TradingGasPrice
)
from .portfolio_service import (
    PortfolioTrackingService,
    create_portfolio_service,
    PortfolioUpdate
)

logger = logging.getLogger(__name__)


class TransactionStatus(Enum):
    """Transaction lifecycle status states."""
    PREPARING = "preparing"          # Building transaction
    GAS_OPTIMIZING = "gas_optimizing"  # Optimizing gas parameters
    READY_TO_SUBMIT = "ready_to_submit"  # Ready for submission
    SUBMITTED = "submitted"          # Submitted to network
    PENDING = "pending"              # Waiting for confirmation
    CONFIRMING = "confirming"        # Being confirmed
    CONFIRMED = "confirmed"          # Transaction confirmed
    COMPLETED = "completed"          # Trade completed and recorded
    FAILED = "failed"                # Transaction failed
    RETRYING = "retrying"            # Retrying with higher gas
    CANCELLED = "cancelled"          # User cancelled
    STUCK = "stuck"                  # Transaction stuck, needs replacement
    REPLACED = "replaced"            # Transaction replaced with higher gas


@dataclass
class RetryConfiguration:
    """Configuration for transaction retry logic."""
    max_retries: int = 3
    initial_backoff_seconds: float = 5.0
    max_backoff_seconds: float = 60.0
    backoff_multiplier: float = 2.0
    gas_escalation_percent: Decimal = Decimal('15')
    max_gas_price_gwei: Decimal = Decimal('500')  # Safety ceiling
    auto_retry_enabled: bool = True
    retry_on_revert: bool = False  # Don't retry logic errors
    retry_on_out_of_gas: bool = True
    retry_on_network_error: bool = True
    retry_on_nonce_error: bool = True
    stuck_transaction_minutes: int = 10  # Consider stuck after this time
    circuit_breaker_threshold: int = 5  # Stop after consecutive failures
    replacement_gas_multiplier: Decimal = Decimal('1.5')  # For stuck transactions


@dataclass
class TransactionState:
    """Current state of a managed transaction."""
    transaction_id: str
    user_id: int
    chain_id: int
    status: TransactionStatus
    
    # Transaction details
    transaction_hash: Optional[HexStr] = None
    block_number: Optional[int] = None
    gas_used: Optional[int] = None
    gas_price_gwei: Optional[Decimal] = None
    nonce: Optional[int] = None
    
    # Swap details
    swap_params: Optional[SwapParams] = None
    swap_result: Optional[SwapResult] = None
    
    # Gas optimization
    gas_optimization_result: Optional[GasOptimizationResult] = None
    gas_savings_percent: Optional[Decimal] = None
    original_gas_price: Optional[Decimal] = None  # For retry escalation
    
    # Timing and metrics
    created_at: datetime = None
    submitted_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    last_retry_at: Optional[datetime] = None
    execution_time_ms: Optional[float] = None
    
    # Error handling and retry logic
    error_message: Optional[str] = None
    error_type: Optional[str] = None  # For retry decision logic
    retry_count: int = 0
    max_retries: int = 3
    consecutive_failures: int = 0  # For circuit breaker
    replacement_tx_hash: Optional[HexStr] = None  # If transaction was replaced
    
    def __post_init__(self):
        """Initialize default values."""
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.original_gas_price is None and self.gas_price_gwei:
            self.original_gas_price = self.gas_price_gwei


@dataclass
class TransactionSubmissionRequest:
    """Request to submit a transaction through the manager."""
    user: User
    chain_id: int
    swap_params: SwapParams
    gas_strategy: TradingGasStrategy = TradingGasStrategy.BALANCED
    is_paper_trade: bool = False
    callback_url: Optional[str] = None
    priority: str = "normal"  # normal, high, emergency
    auto_retry: bool = True  # Enable automatic retry on failure


@dataclass
class TransactionManagerResult:
    """Result of transaction manager operation."""
    success: bool
    transaction_id: str
    transaction_state: Optional[TransactionState] = None
    error_message: Optional[str] = None
    gas_savings_achieved: Optional[Decimal] = None
    was_retried: bool = False
    final_gas_price: Optional[Decimal] = None


class TransactionManager:
    """
    Central coordinator for trading transaction lifecycle management.
    
    Features:
    - Integration with Phase 6A gas optimizer for 23.1% cost savings
    - DEX router service integration for swap execution
    - Real-time transaction status monitoring
    - WebSocket broadcasts for live UI updates
    - Comprehensive retry logic with gas escalation
    - Stuck transaction replacement
    - Circuit breaker pattern for failure protection
    - Portfolio tracking integration
    - Paper trading simulation support
    """
    
    def __init__(self, chain_config: ChainConfig):
        """
        Initialize transaction manager for specific chain.
        
        Args:
            chain_config: Chain configuration for this manager instance
        """
        self.chain_config = chain_config
        self.chain_id = chain_config.chain_id
        self.logger = logging.getLogger(f'trading.tx_manager.{chain_config.name}')
        
        # Retry configuration
        self.retry_config = RetryConfiguration()
        
        # Service dependencies (initialized in initialize())
        self._web3_client: Optional[Web3Client] = None
        self._wallet_manager: Optional[WalletManager] = None
        self._dex_router_service: Optional[DEXRouterService] = None
        self._portfolio_service: Optional[PortfolioTrackingService] = None
        
        # Transaction state management
        self._active_transactions: Dict[str, TransactionState] = {}
        self._transaction_callbacks: Dict[str, List[Callable]] = {}
        self._retry_tasks: Dict[str, asyncio.Task] = {}  # Active retry tasks
        self._stuck_monitor_task: Optional[asyncio.Task] = None
        
        # Circuit breaker state
        self._consecutive_failures = 0
        self._circuit_open = False
        self._circuit_open_until: Optional[datetime] = None
        
        # Performance metrics
        self.total_transactions = 0
        self.successful_transactions = 0
        self.failed_transactions = 0
        self.retried_transactions = 0
        self.replaced_transactions = 0
        self.gas_savings_total = Decimal('0')
        self.average_execution_time_ms = 0.0
        
        # WebSocket configuration
        self.channel_layer = get_channel_layer() if CHANNELS_AVAILABLE else None
        self.enable_websocket_updates = True
        
        self.logger.info(f"📊 Transaction Manager initialized for {chain_config.name} (Chain ID: {chain_config.chain_id})")
    
    async def initialize(self) -> None:
        """
        Initialize service dependencies and start background tasks.
        
        This must be called before using the transaction manager.
        """
        try:
            self.logger.info("🔧 Initializing Transaction Manager services...")
            
            # Initialize Web3 client
            from engine.web3_client import Web3Client
            self._web3_client = Web3Client(self.chain_config)
            await self._web3_client.connect()
            
            # Initialize wallet manager
            from engine.wallet_manager import WalletManager
            self._wallet_manager = WalletManager(self.chain_config)
            
            # Initialize DEX router service
            self._dex_router_service = await create_dex_router_service(self.chain_id)
            
            # Initialize portfolio service (optional)
            try:
                self._portfolio_service = await create_portfolio_service(self.chain_id)
            except Exception as e:
                self.logger.warning(f"⚠️ Portfolio service initialization failed (non-critical): {e}")
                self._portfolio_service = None
            
            # Start stuck transaction monitor
            self._stuck_monitor_task = asyncio.create_task(self._monitor_stuck_transactions())
            
            self.logger.info("✅ Transaction Manager services initialized successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Transaction Manager initialization failed: {e}")
            raise
    
    async def submit_transaction(
        self, 
        request: TransactionSubmissionRequest
    ) -> TransactionManagerResult:
        """
        Submit a new transaction with automatic gas optimization and retry logic.
        
        This is the main entry point that coordinates all transaction operations:
        1. Circuit breaker check
        2. Gas optimization (Phase 6A integration)
        3. Transaction preparation
        4. DEX router execution
        5. Status monitoring with auto-retry
        6. Portfolio tracking
        7. WebSocket updates
        
        Args:
            request: Transaction submission request with all parameters
            
        Returns:
            TransactionManagerResult with transaction ID and initial state
        """
        # Check circuit breaker
        if self._circuit_open and self._circuit_open_until:
            if datetime.now(timezone.utc) < self._circuit_open_until:
                self.logger.error(f"🛑 Circuit breaker open until {self._circuit_open_until}")
                return TransactionManagerResult(
                    success=False,
                    transaction_id="",
                    error_message="Transaction manager circuit breaker is open due to multiple failures"
                )
            else:
                # Reset circuit breaker
                self._circuit_open = False
                self._circuit_open_until = None
                self._consecutive_failures = 0
                self.logger.info("🔄 Circuit breaker reset")
        
        # Generate unique transaction ID
        transaction_id = f"tx_{int(time.time() * 1000)}_{request.user.id}"
        
        try:
            self.logger.info(
                f"🚀 Starting transaction submission: {transaction_id} "
                f"({request.swap_params.swap_type.value})"
            )
            
            # Create initial transaction state
            transaction_state = TransactionState(
                transaction_id=transaction_id,
                user_id=request.user.id,
                chain_id=request.chain_id,
                status=TransactionStatus.PREPARING,
                swap_params=request.swap_params,
                max_retries=self.retry_config.max_retries if request.auto_retry else 0
            )
            
            # Store transaction state
            self._active_transactions[transaction_id] = transaction_state
            
            # Broadcast initial status
            await self._broadcast_transaction_update(transaction_state)
            
            # Step 1: Gas Optimization (Phase 6A Integration)
            await self._optimize_transaction_gas(transaction_state, request)
            
            # Step 2: Execute transaction through DEX router
            swap_result = await self._execute_swap_transaction(transaction_state, request)
            
            # Step 3: Update transaction state with results
            transaction_state.swap_result = swap_result
            if swap_result.transaction_hash and swap_result.transaction_hash != "0x":
                transaction_state.transaction_hash = swap_result.transaction_hash
            transaction_state.block_number = swap_result.block_number
            transaction_state.gas_used = swap_result.gas_used
            transaction_state.gas_price_gwei = swap_result.gas_price_gwei
            transaction_state.execution_time_ms = swap_result.execution_time_ms
            
            # Step 4: Handle success or failure
            if swap_result.success:
                # Reset circuit breaker on success
                self._consecutive_failures = 0
                
                # Start transaction monitoring
                asyncio.create_task(self._monitor_transaction_status(transaction_id))
                
                # Calculate gas savings achieved
                gas_savings = self._calculate_gas_savings(transaction_state)
                
                # Update performance metrics
                self.total_transactions += 1
                self.successful_transactions += 1
                if gas_savings:
                    self.gas_savings_total += gas_savings
                
                self.logger.info(
                    f"✅ Transaction submitted successfully: {transaction_id} "
                    f"(Hash: {swap_result.transaction_hash[:10] if swap_result.transaction_hash else 'N/A'}...)"
                )
                
                return TransactionManagerResult(
                    success=True,
                    transaction_id=transaction_id,
                    transaction_state=transaction_state,
                    gas_savings_achieved=gas_savings
                )
            else:
                # Handle failure with potential retry
                self.logger.error(f"❌ Initial transaction submission failed: {transaction_id}")
                
                # Check if we should retry
                if request.auto_retry and await self._should_retry_transaction(transaction_state, swap_result.error_message):
                    self.logger.info(f"🔄 Scheduling automatic retry for transaction: {transaction_id}")
                    retry_task = asyncio.create_task(
                        self._auto_retry_transaction(transaction_id, request)
                    )
                    self._retry_tasks[transaction_id] = retry_task
                    
                    return TransactionManagerResult(
                        success=False,
                        transaction_id=transaction_id,
                        transaction_state=transaction_state,
                        error_message=f"Transaction failed, retry scheduled: {swap_result.error_message}"
                    )
                else:
                    # No retry, mark as failed
                    transaction_state.status = TransactionStatus.FAILED
                    transaction_state.error_message = swap_result.error_message
                    await self._broadcast_transaction_update(transaction_state)
                    
                    # Update circuit breaker
                    self._consecutive_failures += 1
                    if self._consecutive_failures >= self.retry_config.circuit_breaker_threshold:
                        self._open_circuit_breaker()
                    
                    return TransactionManagerResult(
                        success=False,
                        transaction_id=transaction_id,
                        transaction_state=transaction_state,
                        error_message=swap_result.error_message
                    )
            
        except Exception as e:
            self.logger.error(f"❌ Transaction submission failed: {transaction_id} - {e}", exc_info=True)
            
            # Update transaction state with error
            if transaction_id in self._active_transactions:
                transaction_state = self._active_transactions[transaction_id]
                transaction_state.status = TransactionStatus.FAILED
                transaction_state.error_message = str(e)
                transaction_state.error_type = type(e).__name__
                await self._broadcast_transaction_update(transaction_state)
            
            # Update circuit breaker
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.retry_config.circuit_breaker_threshold:
                self._open_circuit_breaker()
            
            return TransactionManagerResult(
                success=False,
                transaction_id=transaction_id,
                error_message=str(e)
            )
    
    async def retry_failed_transaction(
        self,
        transaction_id: str,
        gas_escalation_percent: Optional[Decimal] = None
    ) -> TransactionManagerResult:
        """
        Manually retry a failed transaction with gas escalation.
        
        Args:
            transaction_id: ID of transaction to retry
            gas_escalation_percent: Gas price increase percentage (default from config)
            
        Returns:
            TransactionManagerResult with retry outcome
        """
        try:
            # Get transaction state
            transaction_state = self._active_transactions.get(transaction_id)
            if not transaction_state:
                return TransactionManagerResult(
                    success=False,
                    transaction_id=transaction_id,
                    error_message="Transaction not found"
                )
            
            # Check if already retrying
            if transaction_state.status == TransactionStatus.RETRYING:
                return TransactionManagerResult(
                    success=False,
                    transaction_id=transaction_id,
                    error_message="Transaction is already being retried"
                )
            
            # Check retry limit
            if transaction_state.retry_count >= transaction_state.max_retries:
                return TransactionManagerResult(
                    success=False,
                    transaction_id=transaction_id,
                    error_message=f"Maximum retry limit ({transaction_state.max_retries}) reached"
                )
            
            self.logger.info(f"🔄 Manually retrying transaction: {transaction_id} (Attempt {transaction_state.retry_count + 1})")
            
            # Update status
            transaction_state.status = TransactionStatus.RETRYING
            transaction_state.retry_count += 1
            transaction_state.last_retry_at = datetime.now(timezone.utc)
            await self._broadcast_transaction_update(transaction_state)
            
            # Calculate new gas price with escalation
            escalation = gas_escalation_percent or self.retry_config.gas_escalation_percent
            new_gas_price = await self._calculate_retry_gas_price(
                transaction_state.original_gas_price or transaction_state.gas_price_gwei,
                transaction_state.retry_count,
                escalation
            )
            
            # Apply gas price ceiling
            if new_gas_price > self.retry_config.max_gas_price_gwei:
                self.logger.warning(
                    f"⚠️ Capping gas price at {self.retry_config.max_gas_price_gwei} gwei "
                    f"(calculated: {new_gas_price} gwei)"
                )
                new_gas_price = self.retry_config.max_gas_price_gwei
            
            # Update swap params with new gas price
            if transaction_state.swap_params:
                transaction_state.swap_params.gas_price_gwei = new_gas_price
                transaction_state.gas_price_gwei = new_gas_price
            
            self.logger.info(
                f"⛽ Retry gas price: {new_gas_price:.2f} gwei "
                f"(+{((new_gas_price / (transaction_state.original_gas_price or Decimal('1'))) - 1) * 100:.1f}%)"
            )
            
            # Re-execute swap with new parameters
            swap_result = await self._execute_swap_transaction(
                transaction_state,
                TransactionSubmissionRequest(
                    user=User.objects.get(id=transaction_state.user_id),
                    chain_id=transaction_state.chain_id,
                    swap_params=transaction_state.swap_params,
                    is_paper_trade=False  # Assume real retry
                )
            )
            
            # Update transaction state with retry results
            transaction_state.swap_result = swap_result
            if swap_result.success:
                transaction_state.status = TransactionStatus.PENDING
                transaction_state.transaction_hash = swap_result.transaction_hash
                self.retried_transactions += 1
                
                # Start monitoring
                asyncio.create_task(self._monitor_transaction_status(transaction_id))
                
                self.logger.info(f"✅ Transaction retry successful: {transaction_id}")
                
                return TransactionManagerResult(
                    success=True,
                    transaction_id=transaction_id,
                    transaction_state=transaction_state,
                    was_retried=True,
                    final_gas_price=new_gas_price
                )
            else:
                # Retry failed
                transaction_state.error_message = swap_result.error_message
                
                # Check if we should retry again
                if transaction_state.retry_count < transaction_state.max_retries:
                    # Schedule another retry with backoff
                    backoff = await self._calculate_retry_backoff(transaction_state.retry_count)
                    self.logger.info(f"⏱️ Scheduling next retry in {backoff:.1f} seconds")
                    
                    await asyncio.sleep(backoff)
                    return await self.retry_failed_transaction(transaction_id, gas_escalation_percent)
                else:
                    # Final failure
                    transaction_state.status = TransactionStatus.FAILED
                    await self._broadcast_transaction_update(transaction_state)
                    
                    self.logger.error(f"❌ Transaction retry failed after {transaction_state.retry_count} attempts: {transaction_id}")
                    
                    return TransactionManagerResult(
                        success=False,
                        transaction_id=transaction_id,
                        transaction_state=transaction_state,
                        error_message=f"Retry failed: {swap_result.error_message}",
                        was_retried=True
                    )
            
        except Exception as e:
            self.logger.error(f"❌ Error during transaction retry: {transaction_id} - {e}", exc_info=True)
            
            if transaction_id in self._active_transactions:
                transaction_state = self._active_transactions[transaction_id]
                transaction_state.status = TransactionStatus.FAILED
                transaction_state.error_message = f"Retry error: {str(e)}"
                await self._broadcast_transaction_update(transaction_state)
            
            return TransactionManagerResult(
                success=False,
                transaction_id=transaction_id,
                error_message=str(e)
            )
    
    async def replace_stuck_transaction(
        self,
        transaction_id: str,
        gas_multiplier: Optional[Decimal] = None
    ) -> TransactionManagerResult:
        """
        Replace a stuck transaction with a new one using the same nonce but higher gas.
        
        Args:
            transaction_id: ID of stuck transaction to replace
            gas_multiplier: Gas price multiplier (default from config)
            
        Returns:
            TransactionManagerResult with replacement outcome
        """
        try:
            # Get transaction state
            transaction_state = self._active_transactions.get(transaction_id)
            if not transaction_state:
                return TransactionManagerResult(
                    success=False,
                    transaction_id=transaction_id,
                    error_message="Transaction not found"
                )
            
            # Check if transaction has a nonce
            if transaction_state.nonce is None:
                return TransactionManagerResult(
                    success=False,
                    transaction_id=transaction_id,
                    error_message="Cannot replace transaction without nonce"
                )
            
            self.logger.info(f"🔄 Replacing stuck transaction: {transaction_id} (Nonce: {transaction_state.nonce})")
            
            # Update status
            transaction_state.status = TransactionStatus.REPLACED
            await self._broadcast_transaction_update(transaction_state)
            
            # Calculate replacement gas price
            multiplier = gas_multiplier or self.retry_config.replacement_gas_multiplier
            new_gas_price = (transaction_state.gas_price_gwei or Decimal('30')) * multiplier
            
            # Apply ceiling
            if new_gas_price > self.retry_config.max_gas_price_gwei:
                new_gas_price = self.retry_config.max_gas_price_gwei
            
            self.logger.info(
                f"⛽ Replacement gas price: {new_gas_price:.2f} gwei "
                f"(x{multiplier} multiplier)"
            )
            
            # Create replacement transaction with same nonce
            if transaction_state.swap_params:
                transaction_state.swap_params.gas_price_gwei = new_gas_price
                transaction_state.swap_params.nonce = transaction_state.nonce  # Use same nonce
            
            # Execute replacement
            swap_result = await self._execute_swap_transaction(
                transaction_state,
                TransactionSubmissionRequest(
                    user=User.objects.get(id=transaction_state.user_id),
                    chain_id=transaction_state.chain_id,
                    swap_params=transaction_state.swap_params,
                    is_paper_trade=False
                )
            )
            
            if swap_result.success:
                transaction_state.replacement_tx_hash = swap_result.transaction_hash
                transaction_state.status = TransactionStatus.PENDING
                self.replaced_transactions += 1
                
                # Start monitoring replacement
                asyncio.create_task(self._monitor_transaction_status(transaction_id))
                
                self.logger.info(
                    f"✅ Transaction replaced successfully: {transaction_id} "
                    f"(New hash: {swap_result.transaction_hash[:10]}...)"
                )
                
                return TransactionManagerResult(
                    success=True,
                    transaction_id=transaction_id,
                    transaction_state=transaction_state,
                    was_retried=True,
                    final_gas_price=new_gas_price
                )
            else:
                transaction_state.status = TransactionStatus.FAILED
                transaction_state.error_message = f"Replacement failed: {swap_result.error_message}"
                await self._broadcast_transaction_update(transaction_state)
                
                return TransactionManagerResult(
                    success=False,
                    transaction_id=transaction_id,
                    error_message=swap_result.error_message
                )
            
        except Exception as e:
            self.logger.error(f"❌ Error replacing transaction: {transaction_id} - {e}", exc_info=True)
            return TransactionManagerResult(
                success=False,
                transaction_id=transaction_id,
                error_message=str(e)
            )
    
    async def _auto_retry_transaction(
        self,
        transaction_id: str,
        original_request: TransactionSubmissionRequest
    ) -> None:
        """
        Automatically retry a failed transaction with backoff and gas escalation.
        
        Args:
            transaction_id: Transaction ID to retry
            original_request: Original submission request
        """
        try:
            transaction_state = self._active_transactions.get(transaction_id)
            if not transaction_state:
                return
            
            while transaction_state.retry_count < transaction_state.max_retries:
                # Calculate backoff delay
                backoff = await self._calculate_retry_backoff(transaction_state.retry_count)
                self.logger.info(
                    f"⏱️ Auto-retry scheduled in {backoff:.1f}s for: {transaction_id} "
                    f"(Attempt {transaction_state.retry_count + 1}/{transaction_state.max_retries})"
                )
                
                # Wait with backoff
                await asyncio.sleep(backoff)
                
                # Perform retry
                result = await self.retry_failed_transaction(
                    transaction_id,
                    self.retry_config.gas_escalation_percent
                )
                
                if result.success:
                    self.logger.info(f"✅ Auto-retry successful: {transaction_id}")
                    break
                
                # Check if we should continue retrying
                if not await self._should_retry_transaction(
                    transaction_state,
                    result.error_message
                ):
                    self.logger.info(f"🛑 Stopping auto-retry: {transaction_id} - Not retryable error")
                    break
            
            # Clean up retry task
            if transaction_id in self._retry_tasks:
                del self._retry_tasks[transaction_id]
            
        except Exception as e:
            self.logger.error(f"❌ Auto-retry error: {transaction_id} - {e}", exc_info=True)
            
            # Clean up
            if transaction_id in self._retry_tasks:
                del self._retry_tasks[transaction_id]
    
        """
    Enhanced stuck transaction monitoring and nonce management methods for TransactionManager.

    These methods replace the existing basic implementation with sophisticated logic for:
    - Detecting genuinely stuck transactions (not just slow)
    - Smart nonce management to prevent nonce conflicts
    - Gas price analysis to determine if replacement is needed
    - Automatic recovery from nonce gaps

    Add these methods to your TransactionManager class, replacing the existing
    _monitor_stuck_transactions method and adding the new helper methods.

    File: dexproject/trading/services/transaction_manager.py (partial update)
    """

    async def _monitor_stuck_transactions(self) -> None:
        """
        Enhanced background task to monitor and handle stuck transactions.
        
        Features:
        - Detects stuck transactions using multiple criteria
        - Smart replacement decisions based on gas price analysis
        - Nonce gap detection and recovery
        - Prevents excessive replacements
        """
        self.logger.info("🔍 Starting enhanced stuck transaction monitor")
        
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds for efficiency
                
                current_time = datetime.now(timezone.utc)
                
                # Get current network gas price for comparison
                current_gas_price = await self._get_current_gas_price()
                
                # Group transactions by user for nonce management
                user_transactions = {}
                for tx_id, tx_state in self._active_transactions.items():
                    if tx_state.status in [TransactionStatus.PENDING, TransactionStatus.SUBMITTED]:
                        user_id = tx_state.user_id
                        if user_id not in user_transactions:
                            user_transactions[user_id] = []
                        user_transactions[user_id].append((tx_id, tx_state))
                
                # Process each user's transactions
                for user_id, transactions in user_transactions.items():
                    await self._process_user_stuck_transactions(
                        user_id, 
                        transactions, 
                        current_time, 
                        current_gas_price
                    )
                
            except Exception as e:
                self.logger.error(f"❌ Error in stuck transaction monitor: {e}")
                await asyncio.sleep(60)  # Wait longer on error

    async def _process_user_stuck_transactions(
        self,
        user_id: int,
        transactions: List[Tuple[str, TransactionState]],
        current_time: datetime,
        current_gas_price: Decimal
    ) -> None:
        """
        Process stuck transactions for a specific user.
        
        Args:
            user_id: User ID
            transactions: List of (tx_id, tx_state) tuples for this user
            current_time: Current timestamp
            current_gas_price: Current network gas price
        """
        try:
            # Sort transactions by nonce if available
            transactions_with_nonce = [
                (tx_id, tx_state) for tx_id, tx_state in transactions 
                if tx_state.nonce is not None
            ]
            transactions_with_nonce.sort(key=lambda x: x[1].nonce)
            
            # Get expected next nonce for user
            expected_nonce = await self._get_user_next_nonce(user_id)
            
            # Check for nonce gaps
            if transactions_with_nonce:
                await self._check_nonce_gaps(
                    transactions_with_nonce, 
                    expected_nonce
                )
            
            # Process each transaction
            for tx_id, tx_state in transactions:
                stuck_reason = await self._check_if_stuck(
                    tx_state, 
                    current_time, 
                    current_gas_price
                )
                
                if stuck_reason:
                    await self._handle_stuck_transaction(
                        tx_id, 
                        tx_state, 
                        stuck_reason,
                        current_gas_price
                    )
                    
        except Exception as e:
            self.logger.error(f"❌ Error processing user {user_id} stuck transactions: {e}")

    async def _check_if_stuck(
        self,
        tx_state: TransactionState,
        current_time: datetime,
        current_gas_price: Decimal
    ) -> Optional[str]:
        """
        Determine if a transaction is stuck and why.
        
        Args:
            tx_state: Transaction state to check
            current_time: Current timestamp
            current_gas_price: Current network gas price
            
        Returns:
            Reason why transaction is stuck, or None if not stuck
        """
        if not tx_state.submitted_at:
            return None
        
        time_pending = current_time - tx_state.submitted_at
        
        # Check various stuck conditions
        
        # 1. Time-based: Transaction pending too long
        base_threshold = timedelta(minutes=self.retry_config.stuck_transaction_minutes)
        
        # Adjust threshold based on gas price (lower gas = longer wait expected)
        if tx_state.gas_price_gwei and current_gas_price > 0:
            gas_ratio = float(tx_state.gas_price_gwei / current_gas_price)
            if gas_ratio < 0.5:  # Gas price is less than 50% of current
                adjusted_threshold = base_threshold * 2  # Double the wait time
            elif gas_ratio < 0.8:  # Gas price is 50-80% of current
                adjusted_threshold = base_threshold * 1.5
            else:
                adjusted_threshold = base_threshold
        else:
            adjusted_threshold = base_threshold
        
        if time_pending > adjusted_threshold:
            return f"pending_too_long ({time_pending.total_seconds() / 60:.1f} minutes)"
        
        # 2. Gas price too low: Transaction gas is significantly below current price
        if tx_state.gas_price_gwei and current_gas_price > 0:
            if tx_state.gas_price_gwei < (current_gas_price * Decimal('0.5')):
                return f"gas_too_low ({tx_state.gas_price_gwei:.2f} vs {current_gas_price:.2f} gwei)"
        
        # 3. Check if transaction still exists in mempool
        if await self._transaction_dropped_from_mempool(tx_state):
            return "dropped_from_mempool"
        
        # 4. Nonce conflict detection
        if await self._has_nonce_conflict(tx_state):
            return "nonce_conflict"
        
        return None

    async def _handle_stuck_transaction(
        self,
        tx_id: str,
        tx_state: TransactionState,
        stuck_reason: str,
        current_gas_price: Decimal
    ) -> None:
        """
        Handle a stuck transaction based on the reason it's stuck.
        
        Args:
            tx_id: Transaction ID
            tx_state: Transaction state
            stuck_reason: Reason why transaction is stuck
            current_gas_price: Current network gas price
        """
        self.logger.warning(
            f"⚠️ Stuck transaction detected: {tx_id} "
            f"(Reason: {stuck_reason}, "
            f"Pending for {(datetime.now(timezone.utc) - tx_state.submitted_at).total_seconds() / 60:.1f} minutes)"
        )
        
        # Mark as stuck
        tx_state.status = TransactionStatus.STUCK
        tx_state.error_message = f"Transaction stuck: {stuck_reason}"
        await self._broadcast_transaction_update(tx_state)
        
        # Determine action based on stuck reason and configuration
        if not self.retry_config.auto_retry_enabled:
            self.logger.info(f"ℹ️ Auto-retry disabled, not replacing stuck transaction {tx_id}")
            return
        
        # Check if we've already tried to replace this transaction recently
        if tx_state.last_retry_at:
            time_since_last_retry = datetime.now(timezone.utc) - tx_state.last_retry_at
            if time_since_last_retry < timedelta(minutes=5):
                self.logger.info(f"ℹ️ Recently tried to replace {tx_id}, waiting before next attempt")
                return
        
        # Decide on replacement strategy
        if stuck_reason.startswith("gas_too_low"):
            # Need significant gas increase
            gas_multiplier = Decimal('1.5')  # 50% increase
        elif stuck_reason == "dropped_from_mempool":
            # Transaction was dropped, need to resubmit with higher gas
            gas_multiplier = Decimal('1.3')  # 30% increase
        elif stuck_reason == "nonce_conflict":
            # Handle nonce conflict specially
            await self._resolve_nonce_conflict(tx_id, tx_state)
            return
        else:
            # Standard replacement
            gas_multiplier = self.retry_config.replacement_gas_multiplier
        
        # Calculate new gas price
        new_gas_price = self._calculate_replacement_gas_price(
            tx_state.gas_price_gwei or current_gas_price,
            current_gas_price,
            gas_multiplier
        )
        
        # Check if new gas price is worth it
        if not await self._is_replacement_worthwhile(tx_state, new_gas_price):
            self.logger.info(f"ℹ️ Replacement not worthwhile for {tx_id}, keeping original")
            return
        
        # Attempt replacement
        self.logger.info(f"🔄 Auto-replacing stuck transaction: {tx_id}")
        await self.replace_stuck_transaction(tx_id, gas_multiplier)

    async def _get_current_gas_price(self) -> Decimal:
        """
        Get current network gas price.
        
        Returns:
            Current gas price in gwei
        """
        try:
            if self._web3_client:
                # Get gas price from network
                gas_price_wei = await self._web3_client.web3.eth.gas_price
                gas_price_gwei = Decimal(gas_price_wei) / Decimal(10**9)
                return gas_price_gwei
            else:
                # Fallback to configured default
                return Decimal(os.getenv('DEFAULT_GAS_PRICE_GWEI', '30'))
        except Exception as e:
            self.logger.error(f"Error getting current gas price: {e}")
            return Decimal('30')  # Safe default

    async def _get_user_next_nonce(self, user_id: int) -> int:
        """
        Get the next expected nonce for a user's wallet.
        
        Args:
            user_id: User ID
            
        Returns:
            Next expected nonce
        """
        try:
            if self._wallet_manager and self._web3_client:
                # Get user's wallet address
                from django.contrib.auth.models import User
                user = await User.objects.aget(id=user_id)
                
                # For paper trading or if wallet not available, return 0
                if not hasattr(user, 'wallet') or not user.wallet:
                    return 0
                
                wallet_address = user.wallet.address
                
                # Get pending transaction count (includes pending transactions)
                nonce = await self._web3_client.web3.eth.get_transaction_count(
                    wallet_address, 
                    'pending'
                )
                return nonce
            else:
                return 0
        except Exception as e:
            self.logger.error(f"Error getting next nonce for user {user_id}: {e}")
            return 0

    async def _check_nonce_gaps(
        self,
        transactions: List[Tuple[str, TransactionState]],
        expected_nonce: int
    ) -> None:
        """
        Check for gaps in transaction nonces that could block later transactions.
        
        Args:
            transactions: List of transactions with nonces, sorted by nonce
            expected_nonce: Expected next nonce from blockchain
        """
        if not transactions:
            return
        
        # Check if first transaction has the expected nonce
        first_tx_id, first_tx_state = transactions[0]
        if first_tx_state.nonce > expected_nonce:
            self.logger.warning(
                f"⚠️ Nonce gap detected: Expected {expected_nonce}, "
                f"but first pending transaction has nonce {first_tx_state.nonce}"
            )
            # This indicates a missing transaction that needs to be filled
        
        # Check for gaps between transactions
        for i in range(len(transactions) - 1):
            current_tx_id, current_tx_state = transactions[i]
            next_tx_id, next_tx_state = transactions[i + 1]
            
            if next_tx_state.nonce > current_tx_state.nonce + 1:
                self.logger.warning(
                    f"⚠️ Nonce gap between transactions: "
                    f"{current_tx_id} (nonce {current_tx_state.nonce}) and "
                    f"{next_tx_id} (nonce {next_tx_state.nonce})"
                )
                # Mark the later transaction as stuck due to nonce gap
                next_tx_state.error_message = f"Blocked by nonce gap (waiting for nonce {current_tx_state.nonce + 1})"

    async def _transaction_dropped_from_mempool(
        self,
        tx_state: TransactionState
    ) -> bool:
        """
        Check if a transaction has been dropped from the mempool.
        
        Args:
            tx_state: Transaction state to check
            
        Returns:
            True if transaction was dropped from mempool
        """
        try:
            if not tx_state.transaction_hash or not self._web3_client:
                return False
            
            # Try to get the transaction from mempool
            try:
                tx = await self._web3_client.web3.eth.get_transaction(tx_state.transaction_hash)
                # Transaction still exists
                return False
            except Exception as e:
                if "not found" in str(e).lower():
                    # Transaction not found in mempool or blockchain
                    # Check if it was mined
                    try:
                        receipt = await self._web3_client.web3.eth.get_transaction_receipt(
                            tx_state.transaction_hash
                        )
                        # Transaction was mined (shouldn't happen if we're monitoring correctly)
                        return False
                    except:
                        # Not mined and not in mempool = dropped
                        return True
                return False
                
        except Exception as e:
            self.logger.error(f"Error checking mempool for transaction: {e}")
            return False

    async def _has_nonce_conflict(self, tx_state: TransactionState) -> bool:
        """
        Check if transaction has a nonce conflict.
        
        Args:
            tx_state: Transaction state to check
            
        Returns:
            True if there's a nonce conflict
        """
        if tx_state.nonce is None:
            return False
        
        # Check if another transaction with the same nonce was confirmed
        for other_tx_id, other_tx_state in self._active_transactions.items():
            if (other_tx_state.user_id == tx_state.user_id and
                other_tx_state.nonce == tx_state.nonce and
                other_tx_state.transaction_id != tx_state.transaction_id and
                other_tx_state.status == TransactionStatus.CONFIRMED):
                return True
        
        return False

    async def _resolve_nonce_conflict(
        self,
        tx_id: str,
        tx_state: TransactionState
    ) -> None:
        """
        Resolve a nonce conflict by cancelling or replacing the transaction.
        
        Args:
            tx_id: Transaction ID with conflict
            tx_state: Transaction state
        """
        self.logger.info(f"🔧 Resolving nonce conflict for transaction {tx_id}")
        
        # Mark as failed due to nonce conflict
        tx_state.status = TransactionStatus.FAILED
        tx_state.error_message = "Nonce conflict - another transaction used this nonce"
        await self._broadcast_transaction_update(tx_state)
        
        # Clean up the transaction
        if tx_id in self._retry_tasks:
            self._retry_tasks[tx_id].cancel()
            del self._retry_tasks[tx_id]

    def _calculate_replacement_gas_price(
        self,
        original_gas: Decimal,
        current_gas: Decimal,
        multiplier: Decimal
    ) -> Decimal:
        """
        Calculate replacement gas price intelligently.
        
        Args:
            original_gas: Original transaction gas price
            current_gas: Current network gas price
            multiplier: Gas multiplier
            
        Returns:
            Replacement gas price
        """
        # Use the higher of: current gas * multiplier OR original gas * multiplier
        replacement_price = max(
            current_gas * multiplier,
            original_gas * multiplier
        )
        
        # Apply ceiling
        if replacement_price > self.retry_config.max_gas_price_gwei:
            self.logger.warning(
                f"⚠️ Capping replacement gas at {self.retry_config.max_gas_price_gwei} gwei"
            )
            replacement_price = self.retry_config.max_gas_price_gwei
        
        return replacement_price

    async def _is_replacement_worthwhile(
        self,
        tx_state: TransactionState,
        new_gas_price: Decimal
    ) -> bool:
        """
        Determine if replacing a transaction is worthwhile.
        
        Args:
            tx_state: Current transaction state
            new_gas_price: Proposed new gas price
            
        Returns:
            True if replacement is worthwhile
        """
        # Don't replace if we've already replaced multiple times
        if tx_state.retry_count >= 2:
            return False
        
        # Don't replace if new gas price isn't significantly higher (at least 10%)
        if tx_state.gas_price_gwei:
            increase_ratio = (new_gas_price - tx_state.gas_price_gwei) / tx_state.gas_price_gwei
            if increase_ratio < Decimal('0.1'):
                return False
        
        # Don't replace if gas cost would exceed a threshold relative to trade value
        if tx_state.swap_params:
            estimated_gas_cost_usd = self._estimate_gas_cost_usd(new_gas_price)
            trade_value_usd = self._estimate_trade_amount_usd(tx_state.swap_params)
            
            # Don't spend more than 5% of trade value on gas
            if estimated_gas_cost_usd > (trade_value_usd * Decimal('0.05')):
                self.logger.warning(
                    f"⚠️ Replacement gas cost (${estimated_gas_cost_usd:.2f}) exceeds "
                    f"5% of trade value (${trade_value_usd:.2f})"
                )
                return False
        
        return True

    def _estimate_gas_cost_usd(self, gas_price_gwei: Decimal) -> Decimal:
        """
        Estimate gas cost in USD.
        
        Args:
            gas_price_gwei: Gas price in gwei
            
        Returns:
            Estimated cost in USD
        """
        # Assume 150k gas for a swap and $2000 ETH price
        gas_limit = 150000
        eth_price = Decimal('2000')
        
        gas_cost_eth = (gas_price_gwei * Decimal(gas_limit)) / Decimal(10**9)
        gas_cost_usd = gas_cost_eth * eth_price
        
        return gas_cost_usd







    async def _should_retry_transaction(
        self,
        transaction_state: TransactionState,
        error: Optional[str] = None
    ) -> bool:
        """
        Determine if a transaction should be retried based on error type.
        
        Args:
            transaction_state: Current transaction state
            error: Error message to analyze
            
        Returns:
            True if transaction should be retried
        """
        # Check retry count
        if transaction_state.retry_count >= transaction_state.max_retries:
            return False
        
        # Check circuit breaker
        if self._circuit_open:
            return False
        
        # If no error, don't retry
        if not error and not transaction_state.error_message:
            return False
        
        error_msg = (error or transaction_state.error_message or "").lower()
        
        # Don't retry on logic/revert errors
        if any(term in error_msg for term in ["revert", "require", "assert", "invalid", "insufficient funds"]):
            if not self.retry_config.retry_on_revert:
                self.logger.info(f"ℹ️ Not retrying logic error: {error_msg[:100]}")
                return False
        
        # Retry on out of gas
        if "out of gas" in error_msg:
            return self.retry_config.retry_on_out_of_gas
        
        # Retry on network errors
        if any(term in error_msg for term in ["timeout", "connection", "network", "unavailable"]):
            return self.retry_config.retry_on_network_error
        
        # Retry on nonce errors
        if "nonce" in error_msg:
            return self.retry_config.retry_on_nonce_error
        
        # Default: retry on generic errors
        return True
    
    async def _calculate_retry_gas_price(
        self,
        original_gas_price: Decimal,
        retry_count: int,
        escalation_percent: Decimal
    ) -> Decimal:
        """
        Calculate escalated gas price for retry attempt.
        
        Args:
            original_gas_price: Original gas price in gwei
            retry_count: Current retry attempt number
            escalation_percent: Percentage to increase per retry
            
        Returns:
            New gas price in gwei
        """
        # Compound escalation: each retry increases by escalation_percent
        escalation_multiplier = Decimal('1') + (escalation_percent / Decimal('100'))
        new_gas_price = original_gas_price * (escalation_multiplier ** retry_count)
        
        self.logger.debug(
            f"📊 Gas escalation calculation: "
            f"Original: {original_gas_price:.2f} gwei, "
            f"Retry: {retry_count}, "
            f"Escalation: {escalation_percent}%, "
            f"New: {new_gas_price:.2f} gwei"
        )
        
        return new_gas_price
    
    async def _calculate_retry_backoff(self, retry_count: int) -> float:
        """
        Calculate exponential backoff delay for retry.
        
        Args:
            retry_count: Current retry attempt number
            
        Returns:
            Delay in seconds before retry
        """
        # Exponential backoff with jitter
        base_delay = self.retry_config.initial_backoff_seconds
        multiplier = self.retry_config.backoff_multiplier ** (retry_count - 1)
        delay = min(base_delay * multiplier, self.retry_config.max_backoff_seconds)
        
        # Add jitter (±10%) to prevent thundering herd
        import random
        jitter = delay * 0.1 * (2 * random.random() - 1)
        final_delay = delay + jitter
        
        self.logger.debug(
            f"⏱️ Backoff calculation: "
            f"Retry: {retry_count}, "
            f"Base: {base_delay}s, "
            f"Delay: {final_delay:.1f}s"
        )
        
        return final_delay
    
    def _open_circuit_breaker(self) -> None:
        """Open the circuit breaker to prevent cascade failures."""
        self._circuit_open = True
        self._circuit_open_until = datetime.now(timezone.utc) + timedelta(minutes=5)
        
        self.logger.error(
            f"🛑 Circuit breaker OPEN due to {self._consecutive_failures} consecutive failures. "
            f"Will reset at {self._circuit_open_until}"
        )
    
    async def _optimize_transaction_gas(
        self, 
        transaction_state: TransactionState,
        request: TransactionSubmissionRequest
    ) -> None:
        """
        Optimize gas parameters using Phase 6A gas optimizer.
        
        Args:
            transaction_state: Current transaction state to update
            request: Original transaction request
        """
        try:
            # Update status to gas optimizing
            transaction_state.status = TransactionStatus.GAS_OPTIMIZING
            await self._broadcast_transaction_update(transaction_state)
            
            self.logger.info(f"⚡ Optimizing gas for transaction: {transaction_state.transaction_id}")
            
            # Call Phase 6A gas optimizer
            gas_optimization_result = await optimize_trade_gas(
                chain_id=request.chain_id,
                trade_type=request.swap_params.swap_type.value,
                amount_usd=self._estimate_trade_amount_usd(request.swap_params),
                strategy=request.gas_strategy.value,
                is_paper_trade=request.is_paper_trade
            )
            
            # Store gas optimization results
            transaction_state.gas_optimization_result = gas_optimization_result
            
            if gas_optimization_result.success and gas_optimization_result.gas_price:
                # Apply optimized gas parameters to swap params
                gas_price = gas_optimization_result.gas_price
                
                if gas_price.max_fee_per_gas_gwei:
                    # EIP-1559 transaction
                    transaction_state.swap_params.gas_price_gwei = gas_price.max_fee_per_gas_gwei
                elif gas_price.gas_price_gwei:
                    # Legacy transaction
                    transaction_state.swap_params.gas_price_gwei = gas_price.gas_price_gwei
                
                # Store original gas price for retry escalation
                transaction_state.original_gas_price = transaction_state.swap_params.gas_price_gwei
                transaction_state.gas_price_gwei = transaction_state.swap_params.gas_price_gwei
                
                if gas_price.estimated_gas_limit:
                    transaction_state.swap_params.gas_limit = gas_price.estimated_gas_limit
                
                transaction_state.gas_savings_percent = gas_price.cost_savings_percent
                
                self.logger.info(
                    f"✅ Gas optimization complete: {transaction_state.transaction_id} "
                    f"(Savings: {gas_price.cost_savings_percent:.2f}%)"
                )
                
                # Update status to ready
                transaction_state.status = TransactionStatus.READY_TO_SUBMIT
                
            else:
                # Gas optimization failed, log warning but continue with defaults
                self.logger.warning(
                    f"⚠️ Gas optimization failed, using defaults: {transaction_state.transaction_id} "
                    f"- {gas_optimization_result.error_message}"
                )
                transaction_state.status = TransactionStatus.READY_TO_SUBMIT
            
            await self._broadcast_transaction_update(transaction_state)
            
        except Exception as e:
            self.logger.error(f"❌ Gas optimization error: {transaction_state.transaction_id} - {e}", exc_info=True)
            # Continue with default gas parameters
            transaction_state.status = TransactionStatus.READY_TO_SUBMIT
            transaction_state.error_message = f"Gas optimization failed: {e}"
            await self._broadcast_transaction_update(transaction_state)
    
    async def _execute_swap_transaction(
        self, 
        transaction_state: TransactionState,
        request: TransactionSubmissionRequest
    ) -> SwapResult:
        """
        Execute the swap transaction through DEX router service.
        
        Args:
            transaction_state: Current transaction state
            request: Original transaction request
            
        Returns:
            SwapResult from DEX router service
        """
        try:
            # Update status to submitted
            transaction_state.status = TransactionStatus.SUBMITTED
            transaction_state.submitted_at = datetime.now(timezone.utc)
            await self._broadcast_transaction_update(transaction_state)
            
            self.logger.info(f"🔄 Executing swap via DEX router: {transaction_state.transaction_id}")
            
            # Get user's wallet address
            if self._wallet_manager:
                from_address = await self._wallet_manager.get_default_address()
            else:
                # Use a default address for paper trading
                from_address = "0x0000000000000000000000000000000000000001"
            
            # Execute swap through DEX router service
            swap_result = await self._dex_router_service.execute_swap(
                swap_params=transaction_state.swap_params,
                from_address=from_address
            )
            
            # Extract nonce if available
            if hasattr(swap_result, 'nonce'):
                transaction_state.nonce = swap_result.nonce
            
            # Update status based on result
            if swap_result.success:
                transaction_state.status = TransactionStatus.PENDING
                self.logger.info(
                    f"✅ Swap executed successfully: {transaction_state.transaction_id} "
                    f"(Hash: {swap_result.transaction_hash[:10] if swap_result.transaction_hash else 'N/A'}...)"
                )
            else:
                transaction_state.status = TransactionStatus.FAILED
                transaction_state.error_message = swap_result.error_message
                transaction_state.error_type = self._classify_error(swap_result.error_message)
                self.logger.error(
                    f"❌ Swap execution failed: {transaction_state.transaction_id} "
                    f"- {swap_result.error_message}"
                )
            
            await self._broadcast_transaction_update(transaction_state)
            return swap_result
            
        except Exception as e:
            self.logger.error(f"❌ Swap execution error: {transaction_state.transaction_id} - {e}", exc_info=True)
            # Create failed swap result
            return SwapResult(
                transaction_hash="0x",
                block_number=None,
                gas_used=None,
                gas_price_gwei=Decimal('0'),
                amount_in=transaction_state.swap_params.amount_in,
                amount_out=0,
                actual_slippage_percent=Decimal('0'),
                execution_time_ms=0.0,
                dex_version=transaction_state.swap_params.dex_version,
                success=False,
                error_message=str(e)
            )
    
    def _classify_error(self, error_message: str) -> str:
        """
        Classify error type for retry decision logic.
        
        Args:
            error_message: Error message to classify
            
        Returns:
            Error type classification
        """
        if not error_message:
            return "unknown"
        
        error_lower = error_message.lower()
        
        if "out of gas" in error_lower:
            return "out_of_gas"
        elif "nonce" in error_lower:
            return "nonce_error"
        elif any(term in error_lower for term in ["revert", "require", "assert"]):
            return "contract_revert"
        elif any(term in error_lower for term in ["timeout", "connection", "network"]):
            return "network_error"
        elif "insufficient" in error_lower:
            return "insufficient_funds"
        else:
            return "general_error"
    
    async def _monitor_transaction_status(self, transaction_id: str) -> None:
        """
        Monitor transaction status until completion or failure.
        
        Args:
            transaction_id: Transaction ID to monitor
        """
        try:
            transaction_state = self._active_transactions.get(transaction_id)
            if not transaction_state:
                return
            
            self.logger.info(f"👁️ Starting transaction monitoring: {transaction_id}")
            
            # Monitor for confirmation
            timeout_seconds = 600  # 10 minutes timeout
            check_interval = 5  # Check every 5 seconds
            start_time = time.time()
            
            while (time.time() - start_time) < timeout_seconds:
                # Check if cancelled
                if transaction_state.status == TransactionStatus.CANCELLED:
                    self.logger.info(f"🛑 Transaction monitoring cancelled: {transaction_id}")
                    break
                
                # Check transaction status on blockchain
                if transaction_state.transaction_hash and self._web3_client:
                    try:
                        # Get transaction receipt
                        receipt = await self._web3_client.get_transaction_receipt(
                            transaction_state.transaction_hash
                        )
                        
                        if receipt:
                            # Transaction confirmed
                            transaction_state.status = TransactionStatus.CONFIRMED
                            transaction_state.confirmed_at = datetime.now(timezone.utc)
                            transaction_state.block_number = receipt['blockNumber']
                            transaction_state.gas_used = receipt['gasUsed']
                            
                            # Check if transaction succeeded
                            if receipt.get('status', 0) == 1:
                                transaction_state.status = TransactionStatus.COMPLETED
                                
                                # Update portfolio if available
                                await self._update_portfolio_tracking(transaction_state)
                                
                                # Calculate execution time
                                if transaction_state.submitted_at:
                                    transaction_state.execution_time_ms = (
                                        (transaction_state.confirmed_at - transaction_state.submitted_at).total_seconds() * 1000
                                    )
                                    self.average_execution_time_ms = (
                                        (self.average_execution_time_ms * (self.successful_transactions - 1) +
                                         transaction_state.execution_time_ms) / self.successful_transactions
                                    )
                                
                                self.logger.info(
                                    f"✅ Transaction confirmed: {transaction_id} "
                                    f"(Block: {receipt['blockNumber']}, Gas: {receipt['gasUsed']})"
                                )
                            else:
                                # Transaction reverted
                                transaction_state.status = TransactionStatus.FAILED
                                transaction_state.error_message = "Transaction reverted on chain"
                                self.failed_transactions += 1
                                
                                self.logger.error(f"❌ Transaction reverted: {transaction_id}")
                                
                                # Check if we should retry
                                if self.retry_config.auto_retry_enabled:
                                    await self._handle_reverted_transaction(transaction_id)
                            
                            await self._broadcast_transaction_update(transaction_state)
                            break
                            
                    except Exception as e:
                        self.logger.debug(f"Transaction not yet confirmed: {transaction_id} - {e}")
                
                # Wait before next check
                await asyncio.sleep(check_interval)
            
            # Timeout reached
            if transaction_state.status == TransactionStatus.PENDING:
                transaction_state.status = TransactionStatus.STUCK
                transaction_state.error_message = f"Transaction monitoring timeout after {timeout_seconds}s"
                await self._broadcast_transaction_update(transaction_state)
                
                self.logger.warning(f"⏰ Transaction monitoring timeout: {transaction_id}")
                
                # Attempt replacement if configured
                if self.retry_config.auto_retry_enabled:
                    await self.replace_stuck_transaction(transaction_id)
            
        except Exception as e:
            self.logger.error(f"❌ Transaction monitoring error: {transaction_id} - {e}", exc_info=True)
            if transaction_id in self._active_transactions:
                transaction_state = self._active_transactions[transaction_id]
                transaction_state.status = TransactionStatus.FAILED
                transaction_state.error_message = f"Monitoring error: {e}"
                await self._broadcast_transaction_update(transaction_state)
    
    async def _handle_reverted_transaction(self, transaction_id: str) -> None:
        """
        Handle a transaction that reverted on chain.
        
        Args:
            transaction_id: Transaction ID that reverted
        """
        transaction_state = self._active_transactions.get(transaction_id)
        if not transaction_state:
            return
        
        # Only retry if configured to retry reverts
        if self.retry_config.retry_on_revert and transaction_state.retry_count < transaction_state.max_retries:
            self.logger.info(f"🔄 Scheduling retry for reverted transaction: {transaction_id}")
            
            # Get original request (simplified version)
            request = TransactionSubmissionRequest(
                user=User.objects.get(id=transaction_state.user_id),
                chain_id=transaction_state.chain_id,
                swap_params=transaction_state.swap_params,
                auto_retry=True
            )
            
            # Schedule retry with increased gas
            retry_task = asyncio.create_task(
                self._auto_retry_transaction(transaction_id, request)
            )
            self._retry_tasks[transaction_id] = retry_task
    
    async def _update_portfolio_tracking(self, transaction_state: TransactionState) -> None:
        """
        Update portfolio tracking with completed transaction.
        
        Args:
            transaction_state: Completed transaction state
        """
        try:
            if not self._portfolio_service or not transaction_state.swap_result:
                return
            
            # Get user from transaction state
            from django.contrib.auth.models import User
            user = User.objects.get(id=transaction_state.user_id)
            
            # Record trade in portfolio
            portfolio_update = await self._portfolio_service.record_swap_trade(
                swap_result=transaction_state.swap_result,
                swap_type=transaction_state.swap_params.swap_type,
                token_in_address=transaction_state.swap_params.token_in,
                token_out_address=transaction_state.swap_params.token_out,
                pair_address="",  # DEX router will determine this
                user=user,
                trade_id=transaction_state.transaction_id
            )
            
            if portfolio_update.trade_created:
                self.logger.info(
                    f"📊 Portfolio updated: {transaction_state.transaction_id} "
                    f"(Trade ID: {portfolio_update.trade_id})"
                )
            
        except Exception as e:
            self.logger.error(
                f"❌ Portfolio tracking update failed: {transaction_state.transaction_id} - {e}",
                exc_info=True
            )
    
    async def _broadcast_transaction_update(self, transaction_state: TransactionState) -> None:
        """
        Broadcast transaction status update via WebSocket (if available).
        
        Args:
            transaction_state: Current transaction state to broadcast
        """
        try:
            if not self.channel_layer or not self.enable_websocket_updates:
                return
            
            # Prepare update message
            update_message = {
                'type': 'transaction_update',
                'transaction_id': transaction_state.transaction_id,
                'status': transaction_state.status.value,
                'chain_id': transaction_state.chain_id,
                'user_id': transaction_state.user_id,
                'transaction_hash': transaction_state.transaction_hash,
                'gas_savings_percent': float(transaction_state.gas_savings_percent) if transaction_state.gas_savings_percent else None,
                'error_message': transaction_state.error_message,
                'retry_count': transaction_state.retry_count,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # Send to user's channel group
            group_name = f"user_{transaction_state.user_id}_transactions"
            
            await self.channel_layer.group_send(
                group_name,
                {
                    'type': 'send_transaction_update',
                    'message': update_message
                }
            )
            
            self.logger.debug(f"📡 Broadcasted transaction update: {transaction_state.transaction_id} - {transaction_state.status.value}")
            
        except Exception as e:
            # Non-critical error, log but don't fail
            self.logger.warning(f"⚠️ Failed to broadcast transaction update: {e}")
    
    def _estimate_trade_amount_usd(self, swap_params: SwapParams) -> Decimal:
        """
        Estimate trade amount in USD for gas optimization.
        
        Args:
            swap_params: Swap parameters
            
        Returns:
            Estimated trade amount in USD
        """
        # Simplified estimation - in production, would use price oracles
        # For now, assume reasonable default based on amount_in
        try:
            if swap_params.swap_type == SwapType.EXACT_ETH_FOR_TOKENS:
                # Convert Wei to ETH and estimate USD (assuming ~$2000 ETH)
                eth_amount = Decimal(swap_params.amount_in) / Decimal(10**18)
                return eth_amount * Decimal('2000')
            else:
                # For token swaps, estimate based on typical trade sizes
                return Decimal('100')  # Default $100 trade
        except:
            return Decimal('100')  # Safe default
    
    def _calculate_gas_savings(self, transaction_state: TransactionState) -> Optional[Decimal]:
        """
        Calculate actual gas savings achieved vs naive implementation.
        
        Args:
            transaction_state: Transaction state with results
            
        Returns:
            Gas savings percentage or None if not calculable
        """
        try:
            if (transaction_state.gas_optimization_result and 
                transaction_state.gas_optimization_result.success and
                transaction_state.gas_optimization_result.gas_price):
                
                return transaction_state.gas_optimization_result.gas_price.cost_savings_percent
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error calculating gas savings: {e}")
            return None
    
    async def get_transaction_status(self, transaction_id: str) -> Optional[TransactionState]:
        """
        Get current status of a managed transaction.
        
        Args:
            transaction_id: Transaction ID to query
            
        Returns:
            Current transaction state or None if not found
        """
        return self._active_transactions.get(transaction_id)
    
    async def cancel_transaction(self, transaction_id: str, user_id: int) -> bool:
        """
        Cancel a pending transaction (if possible).
        
        Args:
            transaction_id: Transaction ID to cancel
            user_id: User ID for authorization
            
        Returns:
            True if cancelled successfully, False otherwise
        """
        try:
            transaction_state = self._active_transactions.get(transaction_id)
            
            if not transaction_state or transaction_state.user_id != user_id:
                return False
            
            # Can only cancel if not yet submitted or if stuck
            if transaction_state.status in [
                TransactionStatus.PREPARING,
                TransactionStatus.GAS_OPTIMIZING,
                TransactionStatus.READY_TO_SUBMIT,
                TransactionStatus.STUCK
            ]:
                transaction_state.status = TransactionStatus.CANCELLED
                await self._broadcast_transaction_update(transaction_state)
                
                # Cancel any active retry tasks
                if transaction_id in self._retry_tasks:
                    self._retry_tasks[transaction_id].cancel()
                    del self._retry_tasks[transaction_id]
                
                self.logger.info(f"✅ Transaction cancelled: {transaction_id}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"❌ Transaction cancellation error: {transaction_id} - {e}", exc_info=True)
            return False
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for this transaction manager.
        
        Returns:
            Dictionary with performance statistics
        """
        success_rate = (
            (self.successful_transactions / self.total_transactions * 100)
            if self.total_transactions > 0 else 0.0
        )
        
        average_gas_savings = (
            (self.gas_savings_total / self.successful_transactions)
            if self.successful_transactions > 0 else Decimal('0')
        )
        
        retry_rate = (
            (self.retried_transactions / self.total_transactions * 100)
            if self.total_transactions > 0 else 0.0
        )
        
        return {
            'chain_id': self.chain_id,
            'chain_name': self.chain_config.name,
            'total_transactions': self.total_transactions,
            'successful_transactions': self.successful_transactions,
            'failed_transactions': self.failed_transactions,
            'retried_transactions': self.retried_transactions,
            'replaced_transactions': self.replaced_transactions,
            'success_rate_percent': round(success_rate, 2),
            'retry_rate_percent': round(retry_rate, 2),
            'average_gas_savings_percent': round(float(average_gas_savings), 2),
            'total_gas_savings_percent': round(float(self.gas_savings_total), 2),
            'active_transactions': len(self._active_transactions),
            'active_retry_tasks': len(self._retry_tasks),
            'average_execution_time_ms': round(self.average_execution_time_ms, 2),
            'circuit_breaker_open': self._circuit_open,
            'consecutive_failures': self._consecutive_failures
        }
    
    async def cleanup_completed_transactions(self, max_age_hours: int = 24) -> int:
        """
        Clean up completed transactions older than max_age_hours.
        
        Args:
            max_age_hours: Maximum age of transactions to keep
            
        Returns:
            Number of transactions cleaned up
        """
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
            cleaned_count = 0
            
            # Find transactions to clean up
            to_remove = []
            for tx_id, tx_state in self._active_transactions.items():
                if (tx_state.status in [
                    TransactionStatus.COMPLETED,
                    TransactionStatus.FAILED,
                    TransactionStatus.CANCELLED
                ] and tx_state.created_at < cutoff_time):
                    to_remove.append(tx_id)
            
            # Remove old transactions
            for tx_id in to_remove:
                del self._active_transactions[tx_id]
                if tx_id in self._transaction_callbacks:
                    del self._transaction_callbacks[tx_id]
                if tx_id in self._retry_tasks:
                    self._retry_tasks[tx_id].cancel()
                    del self._retry_tasks[tx_id]
                cleaned_count += 1
            
            if cleaned_count > 0:
                self.logger.info(f"🧹 Cleaned up {cleaned_count} old transactions")
            
            return cleaned_count
            
        except Exception as e:
            self.logger.error(f"❌ Transaction cleanup error: {e}", exc_info=True)
            return 0
    
    async def shutdown(self) -> None:
        """
        Gracefully shutdown the transaction manager.
        
        Cancels all background tasks and cleans up resources.
        """
        try:
            self.logger.info("🛑 Shutting down Transaction Manager...")
            
            # Cancel stuck monitor task
            if self._stuck_monitor_task:
                self._stuck_monitor_task.cancel()
                try:
                    await self._stuck_monitor_task
                except asyncio.CancelledError:
                    pass
            
            # Cancel all retry tasks
            for task in self._retry_tasks.values():
                task.cancel()
            
            # Wait for tasks to complete
            if self._retry_tasks:
                await asyncio.gather(
                    *self._retry_tasks.values(),
                    return_exceptions=True
                )
            
            # Disconnect services
            if self._web3_client:
                await self._web3_client.disconnect()
            
            self.logger.info("✅ Transaction Manager shutdown complete")
            
        except Exception as e:
            self.logger.error(f"❌ Error during shutdown: {e}", exc_info=True)


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

# Global transaction manager instances (one per chain)
_transaction_managers: Dict[int, TransactionManager] = {}


async def get_transaction_manager(chain_id: int) -> TransactionManager:
    """
    Get or create transaction manager for specific chain.
    
    Args:
        chain_id: Chain ID to get manager for
        
    Returns:
        Initialized TransactionManager instance
    """
    global _transaction_managers
    
    if chain_id not in _transaction_managers:
        try:
            from engine.config import config
            chain_config = config.get_chain_config(chain_id) if config else None
            
            if not chain_config:
                # Create proper chain config with required attributes
                from dataclasses import dataclass
                from typing import List, Optional
                from decimal import Decimal
                
                @dataclass
                class ProperChainConfig:
                    chain_id: int
                    name: str
                    rpc_providers: List[str]
                    weth_address: str
                    native_token_symbol: str = "ETH"
                    block_time_seconds: int = 12
                    max_gas_price_gwei: Decimal = Decimal('100')
                    ws_providers: Optional[List[str]] = None
                    uniswap_v2_router: Optional[str] = None
                    uniswap_v3_router: Optional[str] = None
                
                # Use appropriate defaults based on chain_id
                if chain_id == 1:  # Ethereum Mainnet
                    chain_config = ProperChainConfig(
                        chain_id=chain_id,
                        name="Ethereum",
                        rpc_providers=["https://eth-mainnet.g.alchemy.com/v2/demo"],
                        weth_address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                        uniswap_v2_router="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
                        uniswap_v3_router="0xE592427A0AEce92De3Edee1F18E0157C05861564"
                    )
                elif chain_id == 8453:  # Base Mainnet
                    chain_config = ProperChainConfig(
                        chain_id=chain_id,
                        name="Base",
                        rpc_providers=["https://mainnet.base.org"],
                        weth_address="0x4200000000000000000000000000000000000006",
                        block_time_seconds=2,
                        max_gas_price_gwei=Decimal('10')
                    )
                else:  # Default config
                    chain_config = ProperChainConfig(
                        chain_id=chain_id,
                        name=f"Chain_{chain_id}",
                        rpc_providers=["https://rpc.example.com"],
                        weth_address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
                    )
            
            # Create and initialize transaction manager
            manager = TransactionManager(chain_config)
            await manager.initialize()
            
            _transaction_managers[chain_id] = manager
            
        except Exception as e:
            raise ValueError(f"Failed to initialize transaction manager for chain {chain_id}: {e}")
    
    return _transaction_managers[chain_id]

async def create_transaction_submission_request(
    user: User,
    chain_id: int,
    token_in: str,
    token_out: str,
    amount_in: int,
    amount_out_minimum: int,
    swap_type: SwapType,
    dex_version: DEXVersion = DEXVersion.UNISWAP_V3,
    gas_strategy: TradingGasStrategy = TradingGasStrategy.BALANCED,
    is_paper_trade: bool = False,
    auto_retry: bool = True,
    slippage_tolerance: Decimal = Decimal('0.005'),
    deadline_minutes: int = 20
) -> TransactionSubmissionRequest:
    """
    Create a transaction submission request with all required parameters.
    
    This is a convenience function for creating properly formatted transaction requests.
    
    Args:
        user: Django user object
        chain_id: Blockchain chain ID
        token_in: Input token address
        token_out: Output token address
        amount_in: Amount of input tokens (in smallest unit)
        amount_out_minimum: Minimum acceptable output amount
        swap_type: Type of swap operation
        dex_version: DEX version to use
        gas_strategy: Gas optimization strategy
        is_paper_trade: Whether this is a paper trade
        auto_retry: Enable automatic retry on failure
        slippage_tolerance: Maximum acceptable slippage
        deadline_minutes: Transaction deadline in minutes
        
    Returns:
        Properly formatted TransactionSubmissionRequest
    """
    try:
        # Create swap parameters
        swap_params = SwapParams(
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            amount_out_minimum=amount_out_minimum,
            swap_type=swap_type,
            dex_version=dex_version,
            slippage_tolerance=slippage_tolerance,
            deadline_minutes=deadline_minutes,
            is_paper_trade=is_paper_trade
        )
        
        # Create submission request
        request = TransactionSubmissionRequest(
            user=user,
            chain_id=chain_id,
            swap_params=swap_params,
            gas_strategy=gas_strategy,
            is_paper_trade=is_paper_trade,
            auto_retry=auto_retry
        )
        
        return request
        
    except Exception as e:
        logger.error(f"Error creating transaction submission request: {e}")
        raise


# =============================================================================
# CLEANUP ON MODULE UNLOAD
# =============================================================================

async def cleanup_all_transaction_managers():
    """
    Clean up all transaction manager instances.
    
    Should be called on application shutdown.
    """
    global _transaction_managers
    
    logger.info("🧹 Cleaning up all transaction managers...")
    
    for chain_id, manager in _transaction_managers.items():
        try:
            await manager.shutdown()
        except Exception as e:
            logger.error(f"Error shutting down transaction manager for chain {chain_id}: {e}")
    
    _transaction_managers.clear()
    logger.info("✅ All transaction managers cleaned up")


# Register cleanup on module unload (for Django)
try:
    from django.dispatch import Signal
    
    # Create a custom signal for app shutdown
    app_shutdown = Signal()
    
    def handle_shutdown(sender, **kwargs):
        """Handle Django application shutdown."""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(cleanup_all_transaction_managers())
    
    # Connect to shutdown signal
    app_shutdown.connect(handle_shutdown)
    
except ImportError:
    # Not in Django environment
    pass