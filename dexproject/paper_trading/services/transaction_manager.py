"""
Transaction Manager Service - Paper Trading App Core Component

Central coordinator for all trading transaction operations, integrating gas optimization,
DEX routing, real-time status tracking, comprehensive retry logic with gas escalation,
and production-hardened circuit breaker protection.

This is the main TransactionManager class that coordinates all transaction operations
using the base components and retry logic from the supporting modules.

File: dexproject/paper_trading/services/transaction_manager.py
"""

import logging
import asyncio
import time
from typing import Dict, Any, Optional, Callable, List
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from django.contrib.auth.models import User
from django.conf import settings

# WebSocket functionality - optional dependency
try:
    from channels.layers import get_channel_layer
    CHANNELS_AVAILABLE = True
except ImportError:
    CHANNELS_AVAILABLE = False
    get_channel_layer = None

from paper_trading.engine.config import ChainConfig
from paper_trading.engine.web3_client import Web3Client
from paper_trading.engine.wallet_manager import WalletManager

# Import base components from same app
from .transaction_manager_base import (
    TransactionStatus,
    TransactionState,
    TransactionSubmissionRequest,
    TransactionManagerResult,
    RetryConfiguration,
    PerformanceMetrics,
    ErrorClassification,
    classify_error
)

# Import retry and recovery components from same app
from .transaction_manager_retry import (
    TransactionRetryManager,
    StuckTransactionMonitor
)

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
    GasOptimizationResult
)

from .portfolio_service import (
    PortfolioTrackingService,
    create_portfolio_service
)

# Add enhanced circuit breaker imports
from shared.circuit_breakers import (
    EnhancedCircuitBreaker,
    CircuitBreakerType,
    CircuitBreakerConfig,
    CircuitBreakerGroup,
    get_manager as get_circuit_breaker_manager,
    CircuitBreakerOpenError
)

logger = logging.getLogger(__name__)


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
    - Production-hardened circuit breaker pattern for failure protection
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
        self.logger = logging.getLogger(f'paper_trading.tx_manager.{chain_config.name}')
        
        # Configuration
        self.retry_config = RetryConfiguration()
        
        # Service dependencies (initialized in initialize())
        self._web3_client: Optional[Web3Client] = None
        self._wallet_manager: Optional[WalletManager] = None
        self._dex_router_service: Optional[DEXRouterService] = None
        self._portfolio_service: Optional[PortfolioTrackingService] = None
        
        # Circuit breaker management (enhanced)
        self._circuit_breaker_manager = None
        self._tx_circuit_breaker: Optional[EnhancedCircuitBreaker] = None
        self._gas_circuit_breaker: Optional[EnhancedCircuitBreaker] = None
        self._dex_circuit_breaker: Optional[EnhancedCircuitBreaker] = None
        
        # Retry and recovery managers
        self._retry_manager = TransactionRetryManager(self.chain_id, self.retry_config)
        self._stuck_monitor = StuckTransactionMonitor(self.chain_id, self.retry_config)
        
        # Transaction state management
        self._active_transactions: Dict[str, TransactionState] = {}
        self._transaction_callbacks: Dict[str, List[Callable]] = {}
        
        # Performance metrics
        self.metrics = PerformanceMetrics()
        
        # WebSocket configuration
        self.channel_layer = get_channel_layer() if CHANNELS_AVAILABLE else None
        self.enable_websocket_updates = True
        
        self.logger.info(
            f"📊 Transaction Manager initialized for {chain_config.name} "
            f"(Chain ID: {chain_config.chain_id})"
        )
    
    async def initialize(self) -> None:
        """
        Initialize service dependencies and start background tasks.
        
        This must be called before using the transaction manager.
        """
        try:
            self.logger.info("🔧 Initializing Transaction Manager services...")
            
            # Initialize Web3 client
            self._web3_client = Web3Client(self.chain_config)
            await self._web3_client.connect()
            
            # Initialize wallet manager
            self._wallet_manager = WalletManager(self.chain_config)
            
            # Initialize DEX router service
            self._dex_router_service = await create_dex_router_service(self.chain_id)
            
            # Initialize portfolio service (optional)
            try:
                self._portfolio_service = await create_portfolio_service(self.chain_id)
            except Exception as e:
                self.logger.warning(f"⚠️ Portfolio service initialization failed (non-critical): {e}")
                self._portfolio_service = None
            
            # Initialize enhanced circuit breakers
            await self._initialize_circuit_breakers()
            
            # Set dependencies for retry manager and stuck monitor
            self._retry_manager.set_dependencies(self._web3_client, self._wallet_manager)
            self._stuck_monitor.set_dependencies(self._web3_client, self._wallet_manager)
            self._stuck_monitor.set_transactions(self._active_transactions)
            self._stuck_monitor.set_replacement_callback(self.replace_stuck_transaction)
            
            # Start stuck transaction monitor
            await self._stuck_monitor.start_monitoring()
            
            self.logger.info("Transaction Manager services initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Transaction Manager initialization failed: {e}")
            raise
    
    async def _initialize_circuit_breakers(self) -> None:
        """Initialize enhanced circuit breakers for transaction management."""
        try:
            # Get the circuit breaker manager
            self._circuit_breaker_manager = await get_circuit_breaker_manager()
            
            # Create transaction failure circuit breaker
            self._tx_circuit_breaker = await self._circuit_breaker_manager.create_breaker(
                name=f"tx_{self.chain_config.name}_{self.chain_id}",
                breaker_type=CircuitBreakerType.TRANSACTION_FAILURE,
                config=CircuitBreakerConfig(
                    breaker_type=CircuitBreakerType.TRANSACTION_FAILURE,
                    failure_threshold=5,
                    timeout_seconds=300,  # 5 minutes
                    success_threshold=2,
                    enable_jitter=True,
                    escalation_multiplier=1.5
                )
            )
            
            # Create gas price spike circuit breaker
            self._gas_circuit_breaker = await self._circuit_breaker_manager.create_breaker(
                name=f"gas_{self.chain_config.name}_{self.chain_id}",
                breaker_type=CircuitBreakerType.GAS_PRICE_SPIKE,
                config=CircuitBreakerConfig(
                    breaker_type=CircuitBreakerType.GAS_PRICE_SPIKE,
                    failure_threshold=3,
                    timeout_seconds=60,  # 1 minute
                    success_threshold=1,
                    custom_params={
                        "max_gas_price_gwei": float(self.chain_config.max_gas_price_gwei),
                        "spike_multiplier": 3.0
                    }
                )
            )
            
            # Create DEX failure circuit breaker
            self._dex_circuit_breaker = await self._circuit_breaker_manager.create_breaker(
                name=f"dex_{self.chain_config.name}_{self.chain_id}",
                breaker_type=CircuitBreakerType.DEX_FAILURE,
                config=CircuitBreakerConfig(
                    breaker_type=CircuitBreakerType.DEX_FAILURE,
                    failure_threshold=3,
                    timeout_seconds=180,  # 3 minutes
                    success_threshold=1,
                    half_open_max_calls=2
                ),
                chain_id=self.chain_id
            )
            
            self.logger.info(f"✅ Circuit breakers initialized for {self.chain_config.name}")
            
        except Exception as e:
            self.logger.error(f"❌ Circuit breaker initialization failed: {e}")
            # Continue without circuit breakers - non-critical but log warning
            self.logger.warning("⚠️ Operating without enhanced circuit breakers - reduced resilience")
    
    async def submit_transaction(
        self, 
        request: TransactionSubmissionRequest
    ) -> TransactionManagerResult:
        """
        Submit a new transaction with automatic gas optimization and retry logic.
        
        This is the main entry point that coordinates all transaction operations:
        1. Enhanced circuit breaker check
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
        # Validate request
        try:
            request.validate()
        except ValueError as e:
            return TransactionManagerResult(
                success=False,
                transaction_id="",
                error_message=str(e)
            )
        
        # Check enhanced circuit breakers
        if self._circuit_breaker_manager:
            can_proceed, blocking_reasons = await self._circuit_breaker_manager.check_breakers(
                breaker_types=[
                    CircuitBreakerType.TRANSACTION_FAILURE,
                    CircuitBreakerType.GAS_PRICE_SPIKE,
                    CircuitBreakerType.DEX_FAILURE
                ],
                user_id=request.user.id,
                chain_id=request.chain_id
            )
            
            if not can_proceed:
                self.logger.warning(f"⛔ Circuit breakers blocking transaction: {blocking_reasons}")
                return TransactionManagerResult(
                    success=False,
                    transaction_id="",
                    error_message=f"Circuit breakers active: {'; '.join(blocking_reasons)}"
                )
        
        # Also check legacy circuit breaker for backward compatibility
        if self._retry_manager.is_circuit_open():
            return TransactionManagerResult(
                success=False,
                transaction_id="",
                error_message="Legacy circuit breaker is open due to multiple failures"
            )
        
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
            
            # Step 1: Gas Optimization with circuit breaker protection
            if self._gas_circuit_breaker:
                try:
                    await self._gas_circuit_breaker.call(
                        self._optimize_transaction_gas,
                        transaction_state,
                        request
                    )
                except CircuitBreakerOpenError as e:
                    self.logger.warning(f"Gas optimization circuit breaker open: {e}")
                    # Continue with default gas settings
                    transaction_state.status = TransactionStatus.READY_TO_SUBMIT
            else:
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
                # Record success
                self._retry_manager.record_success()
                
                # Start transaction monitoring
                asyncio.create_task(self._monitor_transaction_status(transaction_id))
                
                # Calculate gas savings
                gas_savings = self._calculate_gas_savings(transaction_state)
                
                # Update metrics
                self.metrics.total_transactions += 1
                self.metrics.successful_transactions += 1
                if gas_savings:
                    self.metrics.gas_savings_total += gas_savings
                
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
                self.logger.error(f"Initial transaction submission failed: {transaction_id}")
                
                # Check if we should retry
                if request.auto_retry and await self._retry_manager.should_retry_transaction(
                    transaction_state, 
                    swap_result.error_message
                ):
                    self.logger.info(f"🔄 Scheduling automatic retry for transaction: {transaction_id}")
                    
                    await self._retry_manager.schedule_auto_retry(
                        transaction_id,
                        lambda: self._auto_retry_transaction(transaction_id, request)
                    )
                    
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
                    
                    # Record failure
                    self._retry_manager.record_failure()
                    
                    return TransactionManagerResult(
                        success=False,
                        transaction_id=transaction_id,
                        transaction_state=transaction_state,
                        error_message=swap_result.error_message
                    )
            
        except Exception as e:
            self.logger.error(f"Transaction submission failed: {transaction_id} - {e}", exc_info=True)
            
            # Update transaction state with error
            if transaction_id in self._active_transactions:
                transaction_state = self._active_transactions[transaction_id]
                transaction_state.status = TransactionStatus.FAILED
                transaction_state.error_message = str(e)
                transaction_state.error_type = classify_error(str(e)).value
                await self._broadcast_transaction_update(transaction_state)
            
            # Record failure
            self._retry_manager.record_failure()
            
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
            
            self.logger.info(
                f"🔄 Manually retrying transaction: {transaction_id} "
                f"(Attempt {transaction_state.retry_count + 1})"
            )
            
            # Update status
            transaction_state.status = TransactionStatus.RETRYING
            transaction_state.retry_count += 1
            transaction_state.last_retry_at = datetime.now(timezone.utc)
            await self._broadcast_transaction_update(transaction_state)
            
            # Calculate new gas price with escalation
            new_gas_price = self._retry_manager.calculate_retry_gas_price(transaction_state)
            
            # Update swap params with new gas price
            if transaction_state.swap_params:
                transaction_state.swap_params.gas_price_gwei = new_gas_price
                transaction_state.gas_price_gwei = new_gas_price
            
            self.logger.info(
                f"Retry gas price: {new_gas_price:.2f} gwei "
                f"(+{((new_gas_price / (transaction_state.original_gas_price or Decimal('1'))) - 1) * 100:.1f}%)"
            )
            
            # Re-execute swap with new parameters
            swap_result = await self._execute_swap_transaction(
                transaction_state,
                TransactionSubmissionRequest(
                    user=User.objects.get(id=transaction_state.user_id),
                    chain_id=transaction_state.chain_id,
                    swap_params=transaction_state.swap_params,
                    is_paper_trade=False
                )
            )
            
            # Update transaction state with retry results
            transaction_state.swap_result = swap_result
            if swap_result.success:
                transaction_state.status = TransactionStatus.PENDING
                transaction_state.transaction_hash = swap_result.transaction_hash
                self.metrics.retried_transactions += 1
                
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
                    backoff = self._retry_manager.calculate_backoff_delay(transaction_state.retry_count)
                    self.logger.info(f"⏱️ Scheduling next retry in {backoff:.1f} seconds")
                    
                    await asyncio.sleep(backoff)
                    return await self.retry_failed_transaction(transaction_id, gas_escalation_percent)
                else:
                    # Final failure
                    transaction_state.status = TransactionStatus.FAILED
                    await self._broadcast_transaction_update(transaction_state)
                    
                    self.logger.error(
                        f"Transaction retry failed after {transaction_state.retry_count} attempts: "
                        f"{transaction_id}"
                    )
                    
                    return TransactionManagerResult(
                        success=False,
                        transaction_id=transaction_id,
                        transaction_state=transaction_state,
                        error_message=f"Retry failed: {swap_result.error_message}",
                        was_retried=True
                    )
            
        except Exception as e:
            self.logger.error(f"Error during transaction retry: {transaction_id} - {e}", exc_info=True)
            
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
            
            self.logger.info(
                f"🔄 Replacing stuck transaction: {transaction_id} "
                f"(Nonce: {transaction_state.nonce})"
            )
            
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
                f"Replacement gas price: {new_gas_price:.2f} gwei "
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
                self.metrics.replaced_transactions += 1
                
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
            self.logger.error(f"Error replacing transaction: {transaction_id} - {e}", exc_info=True)
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
                backoff = self._retry_manager.calculate_backoff_delay(transaction_state.retry_count)
                self.logger.info(
                    f"⏱Auto-retry scheduled in {backoff:.1f}s for: {transaction_id} "
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
                    self.logger.info(f"Auto-retry successful: {transaction_id}")
                    break
                
                # Check if we should continue retrying
                if not await self._retry_manager.should_retry_transaction(
                    transaction_state,
                    result.error_message
                ):
                    self.logger.info(f"Stopping auto-retry: {transaction_id} - Not retryable error")
                    break
            
            # Clean up retry task
            self._retry_manager.cancel_retry(transaction_id)
            
        except Exception as e:
            self.logger.error(f"Auto-retry error: {transaction_id} - {e}", exc_info=True)
            
            # Clean up
            self._retry_manager.cancel_retry(transaction_id)
    
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
                    f"Gas optimization complete: {transaction_state.transaction_id} "
                    f"(Savings: {gas_price.cost_savings_percent:.2f}%)"
                )
                
                # Update status to ready
                transaction_state.status = TransactionStatus.READY_TO_SUBMIT
                
            else:
                # Gas optimization failed, log warning but continue with defaults
                self.logger.warning(
                    f"Gas optimization failed, using defaults: {transaction_state.transaction_id} "
                    f"- {gas_optimization_result.error_message}"
                )
                transaction_state.status = TransactionStatus.READY_TO_SUBMIT
            
            await self._broadcast_transaction_update(transaction_state)
            
        except Exception as e:
            self.logger.error(f"Gas optimization error: {transaction_state.transaction_id} - {e}", exc_info=True)
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
        Execute the swap transaction through DEX router service with circuit breaker protection.
        
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
            
            self.logger.info(f"Executing swap via DEX router: {transaction_state.transaction_id}")
            
            # Get user's wallet address
            if self._wallet_manager:
                from_address = await self._wallet_manager.get_default_address()
            else:
                # Use a default address for paper trading
                from_address = "0x0000000000000000000000000000000000000001"
            
            # Execute swap through circuit breaker if available
            if self._dex_circuit_breaker:
                try:
                    swap_result = await self._dex_circuit_breaker.call(
                        self._dex_router_service.execute_swap,
                        swap_params=transaction_state.swap_params,
                        from_address=from_address
                    )
                except CircuitBreakerOpenError as e:
                    self.logger.error(f"DEX circuit breaker open: {e}")
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
                        error_message=f"DEX temporarily unavailable: {e.message}"
                    )
            else:
                # Fallback to direct execution
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
                    f"Swap executed successfully: {transaction_state.transaction_id} "
                    f"(Hash: {swap_result.transaction_hash[:10] if swap_result.transaction_hash else 'N/A'}...)"
                )
            else:
                transaction_state.status = TransactionStatus.FAILED
                transaction_state.error_message = swap_result.error_message
                transaction_state.error_type = classify_error(swap_result.error_message).value
                self.logger.error(
                    f"Swap execution failed: {transaction_state.transaction_id} "
                    f"- {swap_result.error_message}"
                )
            
            await self._broadcast_transaction_update(transaction_state)
            return swap_result
            
        except Exception as e:
            self.logger.error(f"Swap execution error: {transaction_state.transaction_id} - {e}", exc_info=True)
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
            
            self.logger.info(f"Starting transaction monitoring: {transaction_id}")
            
            # Monitor for confirmation
            timeout_seconds = 600  # 10 minutes timeout
            check_interval = 5  # Check every 5 seconds
            start_time = time.time()
            
            while (time.time() - start_time) < timeout_seconds:
                # Check if cancelled
                if transaction_state.status == TransactionStatus.CANCELLED:
                    self.logger.info(f"Transaction monitoring cancelled: {transaction_id}")
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
                                    
                                    # Update average execution time
                                    if self.metrics.successful_transactions > 0:
                                        self.metrics.average_execution_time_ms = (
                                            (self.metrics.average_execution_time_ms * (self.metrics.successful_transactions - 1) +
                                             transaction_state.execution_time_ms) / self.metrics.successful_transactions
                                        )
                                
                                self.logger.info(
                                    f"Transaction confirmed: {transaction_id} "
                                    f"(Block: {receipt['blockNumber']}, Gas: {receipt['gasUsed']})"
                                )
                            else:
                                # Transaction reverted
                                transaction_state.status = TransactionStatus.FAILED
                                transaction_state.error_message = "Transaction reverted on chain"
                                self.metrics.failed_transactions += 1
                                
                                self.logger.error(f"Transaction reverted: {transaction_id}")
                                
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
            self.logger.error(f"Transaction monitoring error: {transaction_id} - {e}", exc_info=True)
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
            self.logger.info(f"Scheduling retry for reverted transaction: {transaction_id}")
            
            # Get original request (simplified version)
            request = TransactionSubmissionRequest(
                user=User.objects.get(id=transaction_state.user_id),
                chain_id=transaction_state.chain_id,
                swap_params=transaction_state.swap_params,
                auto_retry=True
            )
            
            # Schedule retry with increased gas
            await self._retry_manager.schedule_auto_retry(
                transaction_id,
                lambda: self._auto_retry_transaction(transaction_id, request)
            )
    
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
                    f"Portfolio updated: {transaction_state.transaction_id} "
                    f"(Trade ID: {portfolio_update.trade_id})"
                )
            
        except Exception as e:
            self.logger.error(
                f"Portfolio tracking update failed: {transaction_state.transaction_id} - {e}",
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
            self.logger.warning(f"Failed to broadcast transaction update: {e}")
    
    def _estimate_trade_amount_usd(self, swap_params: SwapParams) -> Decimal:
        """
        Estimate trade amount in USD for gas optimization.
        
        Args:
            swap_params: Swap parameters
            
        Returns:
            Estimated trade amount in USD
        """
        # Simplified estimation - in production, would use price oracles
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
                self._retry_manager.cancel_retry(transaction_id)
                
                self.logger.info(f"Transaction cancelled: {transaction_id}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Transaction cancellation error: {transaction_id} - {e}", exc_info=True)
            return False
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for this transaction manager with enhanced circuit breaker status.
        
        Returns:
            Dictionary with performance statistics
        """
        metrics_dict = self.metrics.to_dict()
        metrics_dict.update({
            'chain_id': self.chain_id,
            'chain_name': self.chain_config.name,
            'active_transactions': len(self._active_transactions),
            'active_retry_tasks': len([t for t in self._retry_manager._retry_tasks.values() if not t.done()]),
            'circuit_breaker_open': self._retry_manager.is_circuit_open(),
            'consecutive_failures': self._retry_manager._consecutive_failures
        })
        
        # Add enhanced circuit breaker status
        if self._circuit_breaker_manager:
            cb_status = self._circuit_breaker_manager.get_status()
            metrics_dict['circuit_breakers'] = {
                'total': cb_status.get('total_breakers', 0),
                'blocking': len(cb_status.get('blocking_breakers', [])),
                'can_trade': cb_status.get('can_trade', True),
                'cascade_risk': cb_status.get('cascade_detection_enabled', False)
            }
            
            # Add individual breaker status
            breaker_status = {}
            if self._tx_circuit_breaker:
                breaker_status['transaction'] = self._tx_circuit_breaker.state.value
            if self._gas_circuit_breaker:
                breaker_status['gas'] = self._gas_circuit_breaker.state.value
            if self._dex_circuit_breaker:
                breaker_status['dex'] = self._dex_circuit_breaker.state.value
            
            metrics_dict['circuit_breaker_states'] = breaker_status
        
        return metrics_dict
    
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
                self._retry_manager.cancel_retry(tx_id)
                cleaned_count += 1
            
            if cleaned_count > 0:
                self.logger.info(f"🧹 Cleaned up {cleaned_count} old transactions")
            
            return cleaned_count
            
        except Exception as e:
            self.logger.error(f"Transaction cleanup error: {e}", exc_info=True)
            return 0
    
    async def shutdown(self) -> None:
        """
        Gracefully shutdown the transaction manager with circuit breaker cleanup.
        
        Cancels all background tasks and cleans up resources.
        """
        try:
            self.logger.info("Shutting down Transaction Manager...")
            
            # Stop stuck monitor
            await self._stuck_monitor.stop_monitoring()
            
            # Cancel all retry tasks
            await self._retry_manager.cleanup_retry_tasks()
            
            # Reset circuit breakers if needed
            if self._circuit_breaker_manager:
                # Reset only execution-related breakers for this chain
                await self._circuit_breaker_manager.reset_breaker(
                    group=CircuitBreakerGroup.EXECUTION,
                    chain_id=self.chain_id
                )
                self.logger.info("Circuit breakers reset for shutdown")
            
            # Disconnect services
            if self._web3_client:
                await self._web3_client.disconnect()
            
            self.logger.info("✅ Transaction Manager shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}", exc_info=True)


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
            from paper_trading.engine.config import config
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
    logger.info("All transaction managers cleaned up")


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