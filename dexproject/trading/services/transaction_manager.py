"""
Transaction Manager Service - Phase 6B Core Component

Central coordinator for all trading transaction operations, integrating gas optimization,
DEX routing, circuit breaker protection, and real-time status tracking into a unified 
transaction lifecycle manager.

This service bridges the excellent Phase 6A gas optimizer with DEX execution and provides
real-time WebSocket updates for transaction status monitoring.

UPDATED: Added circuit breaker integration for production hardening
- Pre-trade circuit breaker validation
- Automatic breaker triggering on failures
- WebSocket notifications for breaker events
- Portfolio-based breaker checks

File: dexproject/trading/services/transaction_manager.py
"""

import logging
import asyncio
import json
import time
from typing import Dict, Any, Optional, Callable, List, Tuple
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
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

# Import circuit breaker components
from engine.utils import (
    CircuitBreaker,
    CircuitBreakerState,
    CircuitBreakerOpenError
)
from engine.portfolio import (
    CircuitBreakerManager,
    CircuitBreakerType,
    CircuitBreakerEvent
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
    CIRCUIT_BREAKER_CHECK = "circuit_breaker_check"  # Checking circuit breakers
    READY_TO_SUBMIT = "ready_to_submit"  # Ready for submission
    SUBMITTED = "submitted"          # Submitted to network
    PENDING = "pending"              # Waiting for confirmation
    CONFIRMING = "confirming"        # Being confirmed
    CONFIRMED = "confirmed"          # Transaction confirmed
    COMPLETED = "completed"          # Trade completed and recorded
    FAILED = "failed"                # Transaction failed
    RETRYING = "retrying"            # Retrying with higher gas
    CANCELLED = "cancelled"          # User cancelled
    BLOCKED_BY_CIRCUIT_BREAKER = "blocked_by_circuit_breaker"  # Blocked by circuit breaker


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
    
    # Swap details
    swap_params: Optional[SwapParams] = None
    swap_result: Optional[SwapResult] = None
    
    # Gas optimization
    gas_optimization_result: Optional[GasOptimizationResult] = None
    gas_savings_percent: Optional[Decimal] = None
    
    # Circuit breaker information
    circuit_breaker_status: Optional[str] = None
    blocked_by_breakers: Optional[List[str]] = None
    
    # Timing and metrics
    created_at: datetime = None
    submitted_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    execution_time_ms: Optional[float] = None
    
    # Error handling
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    consecutive_failures: int = 0
    
    def __post_init__(self):
        """Initialize default values."""
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


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
    bypass_circuit_breaker: bool = False  # For emergency overrides only


@dataclass
class TransactionManagerResult:
    """Result of transaction manager operation."""
    success: bool
    transaction_id: str
    transaction_state: Optional[TransactionState] = None
    error_message: Optional[str] = None
    gas_savings_achieved: Optional[Decimal] = None
    circuit_breaker_triggered: bool = False
    circuit_breaker_reasons: Optional[List[str]] = None


class TransactionManager:
    """
    Central coordinator for trading transaction lifecycle management.
    
    Features:
    - Integration with Phase 6A gas optimizer for 23.1% cost savings
    - Circuit breaker protection for risk management
    - DEX router service integration for swap execution
    - Real-time transaction status monitoring
    - WebSocket broadcasts for live UI updates
    - Retry logic with gas escalation
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
        self.logger = logging.getLogger(f'trading.tx_manager.{chain_config.name.lower()}')
        
        # Service instances (initialized on first use)
        self._web3_client: Optional[Web3Client] = None
        self._wallet_manager: Optional[WalletManager] = None
        self._dex_router_service: Optional[DEXRouterService] = None
        self._portfolio_service: Optional[PortfolioTrackingService] = None
        
        # Circuit breaker components
        self._circuit_breaker_manager: Optional[CircuitBreakerManager] = None
        self._transaction_circuit_breaker: Optional[CircuitBreaker] = None
        self._dex_circuit_breaker: Optional[CircuitBreaker] = None
        self._gas_circuit_breaker: Optional[CircuitBreaker] = None
        
        # WebSocket layer for real-time updates (optional)
        self.channel_layer = get_channel_layer() if CHANNELS_AVAILABLE else None
        
        # Transaction state management
        self._active_transactions: Dict[str, TransactionState] = {}
        self._transaction_callbacks: Dict[str, List[Callable]] = {}
        self._user_failure_counts: Dict[int, int] = {}  # Track failures per user
        
        # Performance metrics
        self.total_transactions = 0
        self.successful_transactions = 0
        self.circuit_breaker_blocks = 0
        self.gas_savings_total = Decimal('0')
        self.average_execution_time_ms = 0.0
        
        # Configuration
        self.max_concurrent_transactions = getattr(settings, 'TRADING_MAX_CONCURRENT_TX', 10)
        self.default_timeout_seconds = getattr(settings, 'TRADING_TX_TIMEOUT', 300)
        self.enable_websocket_updates = getattr(settings, 'TRADING_ENABLE_WEBSOCKET_UPDATES', True)
        self.circuit_breaker_enabled = getattr(settings, 'CIRCUIT_BREAKER_ENABLED', True)
        
        self.logger.info(f"[INIT] Transaction Manager initialized for {chain_config.name}")
    
    async def initialize(self) -> bool:
        """
        Initialize all required services and connections.
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # Initialize Web3 client
            self._web3_client = Web3Client(self.chain_config)
            await self._web3_client.connect()
            
            # Initialize wallet manager
            self._wallet_manager = WalletManager(self.chain_config)
            await self._wallet_manager.initialize(self._web3_client)
            
            # Initialize DEX router service
            self._dex_router_service = await create_dex_router_service(
                self._web3_client, self._wallet_manager
            )
            
            # Initialize portfolio service
            self._portfolio_service = create_portfolio_service(self.chain_config)
            
            # Initialize circuit breakers
            self._circuit_breaker_manager = CircuitBreakerManager()
            
            # Create specific circuit breakers for different failure types
            self._transaction_circuit_breaker = CircuitBreaker(
                name=f"tx_breaker_{self.chain_config.name}",
                failure_threshold=5,
                timeout_seconds=300,  # 5 minutes
                success_threshold=2
            )
            
            self._dex_circuit_breaker = CircuitBreaker(
                name=f"dex_breaker_{self.chain_config.name}",
                failure_threshold=3,
                timeout_seconds=180,  # 3 minutes
                success_threshold=1
            )
            
            self._gas_circuit_breaker = CircuitBreaker(
                name=f"gas_breaker_{self.chain_config.name}",
                failure_threshold=10,  # More tolerant for gas issues
                timeout_seconds=60,   # 1 minute
                success_threshold=3
            )
            
            self.logger.info(
                f"✅ Transaction Manager services initialized for {self.chain_config.name} "
                f"(Circuit breakers: {'ENABLED' if self.circuit_breaker_enabled else 'DISABLED'})"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"[ERROR] Failed to initialize Transaction Manager services: {e}")
            return False
    
    async def submit_transaction(
        self, 
        request: TransactionSubmissionRequest
    ) -> TransactionManagerResult:
        """
        Submit a transaction through the complete lifecycle with gas optimization and circuit breaker protection.
        
        This is the main entry point that coordinates all transaction operations:
        1. Circuit breaker validation
        2. Gas optimization (Phase 6A integration)
        3. Transaction preparation
        4. DEX router execution
        5. Status monitoring
        6. Portfolio tracking
        7. WebSocket updates
        
        Args:
            request: Transaction submission request with all parameters
            
        Returns:
            TransactionManagerResult with transaction ID and initial state
        """
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
                swap_params=request.swap_params
            )
            
            # Store transaction state
            self._active_transactions[transaction_id] = transaction_state
            
            # Broadcast initial status
            await self._broadcast_transaction_update(transaction_state)
            
            # Step 1: Check circuit breakers (unless bypassed for emergency)
            if not request.bypass_circuit_breaker:
                breaker_check = await self._check_circuit_breakers(transaction_state, request)
                if not breaker_check[0]:  # Circuit breaker triggered
                    return TransactionManagerResult(
                        success=False,
                        transaction_id=transaction_id,
                        transaction_state=transaction_state,
                        error_message="Transaction blocked by circuit breaker",
                        circuit_breaker_triggered=True,
                        circuit_breaker_reasons=breaker_check[1]
                    )
            
            # Step 2: Gas Optimization (Phase 6A Integration)
            await self._optimize_transaction_gas(transaction_state, request)
            
            # Step 3: Execute transaction through DEX router with circuit breaker protection
            swap_result = await self._execute_swap_with_circuit_breaker(transaction_state, request)
            
            # Step 4: Update transaction state with results
            transaction_state.swap_result = swap_result
            transaction_state.transaction_hash = swap_result.transaction_hash
            transaction_state.block_number = swap_result.block_number
            transaction_state.gas_used = swap_result.gas_used
            transaction_state.gas_price_gwei = swap_result.gas_price_gwei
            transaction_state.execution_time_ms = swap_result.execution_time_ms
            
            # Step 5: Start transaction monitoring
            asyncio.create_task(self._monitor_transaction_status(transaction_id))
            
            # Step 6: Calculate gas savings achieved
            gas_savings = self._calculate_gas_savings(transaction_state)
            
            # Update performance metrics
            self.total_transactions += 1
            if swap_result.success:
                self.successful_transactions += 1
                self._user_failure_counts[request.user.id] = 0  # Reset failure count on success
                if gas_savings:
                    self.gas_savings_total += gas_savings
            else:
                # Track failures for circuit breaker
                self._user_failure_counts[request.user.id] = self._user_failure_counts.get(request.user.id, 0) + 1
                transaction_state.consecutive_failures = self._user_failure_counts[request.user.id]
            
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
            
        except CircuitBreakerOpenError as e:
            # Circuit breaker prevented execution
            self.logger.warning(f"⚡ Circuit breaker blocked transaction: {transaction_id} - {e}")
            self.circuit_breaker_blocks += 1
            
            if transaction_id in self._active_transactions:
                transaction_state = self._active_transactions[transaction_id]
                transaction_state.status = TransactionStatus.BLOCKED_BY_CIRCUIT_BREAKER
                transaction_state.error_message = str(e)
                transaction_state.circuit_breaker_status = "BLOCKED"
                await self._broadcast_transaction_update(transaction_state)
            
            return TransactionManagerResult(
                success=False,
                transaction_id=transaction_id,
                error_message=str(e),
                circuit_breaker_triggered=True,
                circuit_breaker_reasons=[str(e)]
            )
            
        except Exception as e:
            self.logger.error(f"❌ Transaction submission failed: {transaction_id} - {e}")
            
            # Update transaction state with error
            if transaction_id in self._active_transactions:
                transaction_state = self._active_transactions[transaction_id]
                transaction_state.status = TransactionStatus.FAILED
                transaction_state.error_message = str(e)
                await self._broadcast_transaction_update(transaction_state)
            
            return TransactionManagerResult(
                success=False,
                transaction_id=transaction_id,
                error_message=str(e)
            )
    
    async def _check_circuit_breakers(
        self, 
        transaction_state: TransactionState,
        request: TransactionSubmissionRequest
    ) -> Tuple[bool, Optional[List[str]]]:
        """
        Check all circuit breakers before transaction execution.
        
        Args:
            transaction_state: Current transaction state
            request: Transaction submission request
            
        Returns:
            Tuple of (can_proceed, list_of_triggered_breakers)
        """
        try:
            # Update status
            transaction_state.status = TransactionStatus.CIRCUIT_BREAKER_CHECK
            await self._broadcast_transaction_update(transaction_state)
            
            self.logger.info(f"⚡ Checking circuit breakers for transaction: {transaction_state.transaction_id}")
            
            if not self.circuit_breaker_enabled or not self._circuit_breaker_manager:
                return (True, None)
            
            # Get portfolio state for circuit breaker checks
            portfolio_state = await self._get_portfolio_state_for_breakers(request.user.id)
            
            # Check portfolio-based circuit breakers
            can_trade, reasons = self._circuit_breaker_manager.can_trade()
            
            if not can_trade:
                transaction_state.status = TransactionStatus.BLOCKED_BY_CIRCUIT_BREAKER
                transaction_state.circuit_breaker_status = "BLOCKED"
                transaction_state.blocked_by_breakers = reasons
                await self._broadcast_transaction_update(transaction_state)
                
                # Send WebSocket notification about circuit breaker
                await self._broadcast_circuit_breaker_event(request.user.id, reasons)
                
                self.logger.warning(
                    f"🛑 Transaction blocked by circuit breakers: {transaction_state.transaction_id} "
                    f"- Reasons: {', '.join(reasons)}"
                )
                return (False, reasons)
            
            # Check user-specific failure count
            user_failures = self._user_failure_counts.get(request.user.id, 0)
            max_consecutive_failures = getattr(settings, 'MAX_CONSECUTIVE_FAILURES', 5)
            
            if user_failures >= max_consecutive_failures:
                reason = f"User has {user_failures} consecutive failures (max: {max_consecutive_failures})"
                transaction_state.status = TransactionStatus.BLOCKED_BY_CIRCUIT_BREAKER
                transaction_state.circuit_breaker_status = "BLOCKED"
                transaction_state.blocked_by_breakers = [reason]
                await self._broadcast_transaction_update(transaction_state)
                
                self.logger.warning(
                    f"🛑 Transaction blocked due to consecutive failures: {transaction_state.transaction_id}"
                )
                return (False, [reason])
            
            # All checks passed
            transaction_state.circuit_breaker_status = "PASSED"
            self.logger.info(f"✅ Circuit breaker checks passed: {transaction_state.transaction_id}")
            return (True, None)
            
        except Exception as e:
            self.logger.error(f"❌ Circuit breaker check error: {transaction_state.transaction_id} - {e}")
            # Allow transaction to proceed if circuit breaker check fails
            return (True, None)
    
    async def _get_portfolio_state_for_breakers(self, user_id: int) -> Dict[str, Any]:
        """
        Get portfolio state for circuit breaker evaluation.
        
        Args:
            user_id: User ID to get portfolio for
            
        Returns:
            Portfolio state dictionary
        """
        try:
            if not self._portfolio_service:
                return {}
            
            # Get user's portfolio metrics
            from django.contrib.auth.models import User
            user = User.objects.get(id=user_id)
            
            # Get portfolio summary from portfolio service
            portfolio_summary = await self._portfolio_service.get_portfolio_summary(user)
            
            # Get consecutive failures from our tracking
            consecutive_losses = self._user_failure_counts.get(user_id, 0)
            
            return {
                'daily_pnl': portfolio_summary.get('daily_pnl', Decimal('0')),
                'total_pnl': portfolio_summary.get('total_pnl', Decimal('0')),
                'consecutive_losses': consecutive_losses,
                'portfolio_value': portfolio_summary.get('total_value', Decimal('0'))
            }
            
        except Exception as e:
            self.logger.error(f"Error getting portfolio state for circuit breakers: {e}")
            return {}
    
    async def _execute_swap_with_circuit_breaker(
        self, 
        transaction_state: TransactionState,
        request: TransactionSubmissionRequest
    ) -> SwapResult:
        """
        Execute swap transaction with circuit breaker protection.
        
        Args:
            transaction_state: Current transaction state
            request: Transaction submission request
            
        Returns:
            SwapResult from execution
        """
        try:
            # Use DEX circuit breaker for swap execution
            if self._dex_circuit_breaker and self.circuit_breaker_enabled:
                return await self._dex_circuit_breaker.call(
                    self._execute_swap_transaction,
                    transaction_state,
                    request
                )
            else:
                # Execute without circuit breaker if disabled
                return await self._execute_swap_transaction(transaction_state, request)
                
        except CircuitBreakerOpenError as e:
            # Circuit breaker is open, create failed result
            self.logger.error(f"⚡ DEX circuit breaker open: {transaction_state.transaction_id}")
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
                error_message=f"Circuit breaker open: {e}"
            )
    
    async def _optimize_transaction_gas(
        self, 
        transaction_state: TransactionState,
        request: TransactionSubmissionRequest
    ) -> None:
        """
        Optimize gas parameters using Phase 6A gas optimizer with circuit breaker protection.
        
        Args:
            transaction_state: Current transaction state to update
            request: Original transaction request
        """
        try:
            # Update status to gas optimizing
            transaction_state.status = TransactionStatus.GAS_OPTIMIZING
            await self._broadcast_transaction_update(transaction_state)
            
            self.logger.info(f"⚡ Optimizing gas for transaction: {transaction_state.transaction_id}")
            
            # Use gas circuit breaker if enabled
            if self._gas_circuit_breaker and self.circuit_breaker_enabled:
                gas_optimization_result = await self._gas_circuit_breaker.call(
                    optimize_trade_gas,
                    chain_id=request.chain_id,
                    trade_type=request.swap_params.swap_type.value,
                    amount_usd=self._estimate_trade_amount_usd(request.swap_params),
                    strategy=request.gas_strategy.value,
                    is_paper_trade=request.is_paper_trade
                )
            else:
                # Call Phase 6A gas optimizer directly
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
            
        except CircuitBreakerOpenError as e:
            self.logger.warning(f"⚡ Gas optimization circuit breaker open: {transaction_state.transaction_id}")
            # Continue with default gas parameters
            transaction_state.status = TransactionStatus.READY_TO_SUBMIT
            transaction_state.error_message = f"Gas optimization skipped (circuit breaker): {e}"
            await self._broadcast_transaction_update(transaction_state)
            
        except Exception as e:
            self.logger.error(f"❌ Gas optimization error: {transaction_state.transaction_id} - {e}")
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
            from_address = await self._wallet_manager.get_default_address()
            
            # Execute swap through DEX router service
            swap_result = await self._dex_router_service.execute_swap(
                swap_params=transaction_state.swap_params,
                from_address=from_address
            )
            
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
                
                # Update circuit breaker manager with failure
                if self._circuit_breaker_manager:
                    portfolio_state = await self._get_portfolio_state_for_breakers(transaction_state.user_id)
                    self._circuit_breaker_manager.check_circuit_breakers(portfolio_state)
                
                self.logger.error(
                    f"❌ Swap execution failed: {transaction_state.transaction_id} "
                    f"- {swap_result.error_message}"
                )
            
            await self._broadcast_transaction_update(transaction_state)
            return swap_result
            
        except Exception as e:
            self.logger.error(f"❌ Swap execution error: {transaction_state.transaction_id} - {e}")
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
    
    async def _broadcast_circuit_breaker_event(
        self, 
        user_id: int, 
        reasons: List[str]
    ) -> None:
        """
        Broadcast circuit breaker event via WebSocket.
        
        Args:
            user_id: User ID affected by circuit breaker
            reasons: List of reasons for circuit breaker activation
        """
        if not self.enable_websocket_updates or not CHANNELS_AVAILABLE or not self.channel_layer:
            return
        
        try:
            # Create circuit breaker event message
            breaker_message = {
                'type': 'circuit_breaker_event',
                'user_id': user_id,
                'reasons': reasons,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'action': 'TRADING_BLOCKED'
            }
            
            # Send to user's dashboard group
            group_name = f"dashboard_{user_id}"
            await self.channel_layer.group_send(group_name, {
                'type': 'circuit_breaker_notification',
                'data': breaker_message
            })
            
            self.logger.info(f"📡 Circuit breaker event broadcast to user {user_id}")
            
        except Exception as e:
            self.logger.error(f"❌ Circuit breaker broadcast failed: {e}")
    
    async def reset_circuit_breakers(
        self, 
        user_id: Optional[int] = None, 
        breaker_type: Optional[str] = None
    ) -> bool:
        """
        Reset circuit breakers (admin function).
        
        Args:
            user_id: User ID to reset breakers for (None for all)
            breaker_type: Specific breaker type to reset (None for all)
            
        Returns:
            True if reset successful
        """
        try:
            if self._circuit_breaker_manager:
                if breaker_type:
                    # Reset specific breaker type
                    breaker_enum = CircuitBreakerType[breaker_type.upper()]
                    success = self._circuit_breaker_manager.manual_reset(breaker_enum)
                else:
                    # Reset all breakers
                    success = self._circuit_breaker_manager.manual_reset()
                
                if success:
                    self.logger.info(f"✅ Circuit breakers reset successfully")
                    
                    # Reset user failure counts if specified
                    if user_id:
                        self._user_failure_counts[user_id] = 0
                    elif user_id is None and breaker_type is None:
                        # Reset all user failure counts if resetting everything
                        self._user_failure_counts.clear()
                    
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"❌ Circuit breaker reset error: {e}")
            return False
    
    async def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """
        Get current circuit breaker status.
        
        Returns:
            Circuit breaker status dictionary
        """
        status = {
            'enabled': self.circuit_breaker_enabled,
            'portfolio_breakers': {},
            'service_breakers': {},
            'user_failure_counts': dict(self._user_failure_counts),
            'total_blocks': self.circuit_breaker_blocks
        }
        
        # Get portfolio circuit breaker status
        if self._circuit_breaker_manager:
            status['portfolio_breakers'] = self._circuit_breaker_manager.get_status()
        
        # Get service circuit breaker status
        if self._transaction_circuit_breaker:
            status['service_breakers']['transaction'] = self._transaction_circuit_breaker.get_stats()
        if self._dex_circuit_breaker:
            status['service_breakers']['dex'] = self._dex_circuit_breaker.get_stats()
        if self._gas_circuit_breaker:
            status['service_breakers']['gas'] = self._gas_circuit_breaker.get_stats()
        
        return status
    
    # [Previous methods remain the same: _monitor_transaction_status, _update_portfolio_tracking, etc.]
    async def _monitor_transaction_status(self, transaction_id: str) -> None:
        """
        Monitor transaction status until completion or failure.
        
        Args:
            transaction_id: ID of transaction to monitor
        """
        try:
            if transaction_id not in self._active_transactions:
                return
            
            transaction_state = self._active_transactions[transaction_id]
            
            if not transaction_state.transaction_hash:
                return
            
            self.logger.info(f"📊 Starting status monitoring: {transaction_id}")
            
            start_time = time.time()
            timeout_seconds = self.default_timeout_seconds
            check_interval = 5  # Check every 5 seconds
            
            while time.time() - start_time < timeout_seconds:
                try:
                    # Get transaction receipt
                    receipt = await self._web3_client.web3.eth.get_transaction_receipt(
                        transaction_state.transaction_hash
                    )
                    
                    if receipt:
                        # Transaction confirmed
                        transaction_state.status = TransactionStatus.CONFIRMED
                        transaction_state.confirmed_at = datetime.now(timezone.utc)
                        transaction_state.block_number = receipt.blockNumber
                        transaction_state.gas_used = receipt.gasUsed
                        
                        await self._broadcast_transaction_update(transaction_state)
                        
                        # Update portfolio tracking
                        await self._update_portfolio_tracking(transaction_state)
                        
                        # Mark as completed
                        transaction_state.status = TransactionStatus.COMPLETED
                        await self._broadcast_transaction_update(transaction_state)
                        
                        self.logger.info(
                            f"✅ Transaction completed: {transaction_id} "
                            f"(Block: {receipt.blockNumber}, Gas: {receipt.gasUsed})"
                        )
                        return
                    
                except Exception as receipt_error:
                    # Transaction not yet mined, continue monitoring
                    pass
                
                # Wait before next check
                await asyncio.sleep(check_interval)
            
            # Timeout reached
            transaction_state.status = TransactionStatus.FAILED
            transaction_state.error_message = f"Transaction monitoring timeout after {timeout_seconds}s"
            await self._broadcast_transaction_update(transaction_state)
            
            self.logger.warning(f"⏰ Transaction monitoring timeout: {transaction_id}")
            
        except Exception as e:
            self.logger.error(f"❌ Transaction monitoring error: {transaction_id} - {e}")
            if transaction_id in self._active_transactions:
                transaction_state = self._active_transactions[transaction_id]
                transaction_state.status = TransactionStatus.FAILED
                transaction_state.error_message = f"Monitoring error: {e}"
                await self._broadcast_transaction_update(transaction_state)
    
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
                f"❌ Portfolio tracking update failed: {transaction_state.transaction_id} - {e}"
            )
    
    async def _broadcast_transaction_update(self, transaction_state: TransactionState) -> None:
        """
        Broadcast transaction status update via WebSocket (if available).
        
        Args:
            transaction_state: Current transaction state to broadcast
        """
        if not self.enable_websocket_updates or not CHANNELS_AVAILABLE or not self.channel_layer:
            # WebSocket broadcasting not available, log instead
            self.logger.info(
                f"📊 Transaction Update: {transaction_state.transaction_id} "
                f"({transaction_state.status.value})"
            )
            return
        
        try:
            # Create update message
            update_message = {
                'type': 'transaction_update',
                'transaction_id': transaction_state.transaction_id,
                'status': transaction_state.status.value,
                'chain_id': transaction_state.chain_id,
                'transaction_hash': transaction_state.transaction_hash,
                'block_number': transaction_state.block_number,
                'gas_used': transaction_state.gas_used,
                'gas_price_gwei': str(transaction_state.gas_price_gwei) if transaction_state.gas_price_gwei else None,
                'execution_time_ms': transaction_state.execution_time_ms,
                'gas_savings_percent': str(transaction_state.gas_savings_percent) if transaction_state.gas_savings_percent else None,
                'circuit_breaker_status': transaction_state.circuit_breaker_status,
                'error_message': transaction_state.error_message,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # Send to user's dashboard group
            group_name = f"dashboard_{transaction_state.user_id}"
            await self.channel_layer.group_send(group_name, {
                'type': 'status_update',
                'data': update_message
            })
            
            self.logger.debug(
                f"📡 WebSocket update sent: {transaction_state.transaction_id} "
                f"({transaction_state.status.value})"
            )
            
        except Exception as e:
            self.logger.error(f"❌ WebSocket broadcast failed: {transaction_state.transaction_id} - {e}")
    
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
            
            # Can only cancel if not yet submitted
            if transaction_state.status in [
                TransactionStatus.PREPARING, 
                TransactionStatus.GAS_OPTIMIZING, 
                TransactionStatus.CIRCUIT_BREAKER_CHECK,
                TransactionStatus.READY_TO_SUBMIT
            ]:
                transaction_state.status = TransactionStatus.CANCELLED
                await self._broadcast_transaction_update(transaction_state)
                self.logger.info(f"✅ Transaction cancelled: {transaction_id}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"❌ Transaction cancellation error: {transaction_id} - {e}")
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
        
        circuit_breaker_rate = (
            (self.circuit_breaker_blocks / self.total_transactions * 100)
            if self.total_transactions > 0 else 0.0
        )
        
        return {
            'chain_id': self.chain_id,
            'chain_name': self.chain_config.name,
            'total_transactions': self.total_transactions,
            'successful_transactions': self.successful_transactions,
            'success_rate_percent': round(success_rate, 2),
            'average_gas_savings_percent': round(float(average_gas_savings), 2),
            'total_gas_savings_percent': round(float(self.gas_savings_total), 2),
            'circuit_breaker_blocks': self.circuit_breaker_blocks,
            'circuit_breaker_rate_percent': round(circuit_breaker_rate, 2),
            'active_transactions': len(self._active_transactions),
            'average_execution_time_ms': round(self.average_execution_time_ms, 2)
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
                    TransactionStatus.CANCELLED,
                    TransactionStatus.BLOCKED_BY_CIRCUIT_BREAKER
                ] and tx_state.created_at < cutoff_time):
                    to_remove.append(tx_id)
            
            # Remove old transactions
            for tx_id in to_remove:
                del self._active_transactions[tx_id]
                if tx_id in self._transaction_callbacks:
                    del self._transaction_callbacks[tx_id]
                cleaned_count += 1
            
            if cleaned_count > 0:
                self.logger.info(f"🧹 Cleaned up {cleaned_count} old transactions")
            
            return cleaned_count
            
        except Exception as e:
            self.logger.error(f"❌ Transaction cleanup error: {e}")
            return 0


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
                # Create minimal chain config for testing
                from dataclasses import dataclass
                
                @dataclass
                class MinimalChainConfig:
                    chain_id: int
                    name: str
                    
                chain_config = MinimalChainConfig(
                    chain_id=chain_id,
                    name=f"Chain_{chain_id}"
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
    slippage_tolerance: Decimal = Decimal('0.005'),
    deadline_minutes: int = 20,
    bypass_circuit_breaker: bool = False
) -> TransactionSubmissionRequest:
    """
    Create a transaction submission request with all required parameters.
    
    This is a convenience function for creating properly formatted transaction requests.
    
    Args:
        user: Django user making the transaction
        chain_id: Target chain ID
        token_in: Input token address
        token_out: Output token address
        amount_in: Amount to swap (in wei)
        amount_out_minimum: Minimum tokens to receive
        swap_type: Type of swap operation
        dex_version: DEX version to use
        gas_strategy: Gas optimization strategy
        is_paper_trade: Whether this is a paper trade
        slippage_tolerance: Slippage tolerance (0.005 = 0.5%)
        deadline_minutes: Transaction deadline in minutes
        bypass_circuit_breaker: Whether to bypass circuit breaker checks (emergency only)
        
    Returns:
        Configured TransactionSubmissionRequest
    """
    from eth_utils import to_checksum_address
    from datetime import timedelta
    
    # Calculate deadline timestamp
    deadline = int((datetime.now(timezone.utc) + timedelta(minutes=deadline_minutes)).timestamp())
    
    # Create swap parameters
    swap_params = SwapParams(
        token_in=to_checksum_address(token_in),
        token_out=to_checksum_address(token_out),
        amount_in=amount_in,
        amount_out_minimum=amount_out_minimum,
        swap_type=swap_type,
        dex_version=dex_version,
        recipient=to_checksum_address(user.wallet.address),  # Assume user has wallet
        deadline=deadline,
        slippage_tolerance=slippage_tolerance
    )
    
    return TransactionSubmissionRequest(
        user=user,
        chain_id=chain_id,
        swap_params=swap_params,
        gas_strategy=gas_strategy,
        is_paper_trade=is_paper_trade,
        bypass_circuit_breaker=bypass_circuit_breaker
    )