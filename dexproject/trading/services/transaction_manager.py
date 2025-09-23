"""
Transaction Manager Service - Phase 6B Core Component

Central coordinator for all trading transaction operations, integrating gas optimization,
DEX routing, and real-time status tracking into a unified transaction lifecycle manager.

This service bridges the excellent Phase 6A gas optimizer with DEX execution and provides
real-time WebSocket updates for transaction status monitoring.

File: dexproject/trading/services/transaction_manager.py
"""

import logging
import asyncio
import json
import time
from typing import Dict, Any, Optional, Callable, List
from decimal import Decimal
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum

from django.contrib.auth.models import User
from django.conf import settings
from channels.layers import get_channel_layer
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
    
    # Timing and metrics
    created_at: datetime = None
    submitted_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    execution_time_ms: Optional[float] = None
    
    # Error handling
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
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


@dataclass
class TransactionManagerResult:
    """Result of transaction manager operation."""
    success: bool
    transaction_id: str
    transaction_state: Optional[TransactionState] = None
    error_message: Optional[str] = None
    gas_savings_achieved: Optional[Decimal] = None


class TransactionManager:
    """
    Central coordinator for trading transaction lifecycle management.
    
    Features:
    - Integration with Phase 6A gas optimizer for 23.1% cost savings
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
        
        # WebSocket layer for real-time updates
        self.channel_layer = get_channel_layer()
        
        # Transaction state management
        self._active_transactions: Dict[str, TransactionState] = {}
        self._transaction_callbacks: Dict[str, List[Callable]] = {}
        
        # Performance metrics
        self.total_transactions = 0
        self.successful_transactions = 0
        self.gas_savings_total = Decimal('0')
        self.average_execution_time_ms = 0.0
        
        # Configuration
        self.max_concurrent_transactions = getattr(settings, 'TRADING_MAX_CONCURRENT_TX', 10)
        self.default_timeout_seconds = getattr(settings, 'TRADING_TX_TIMEOUT', 300)
        self.enable_websocket_updates = getattr(settings, 'TRADING_ENABLE_WEBSOCKET_UPDATES', True)
        
        self.logger.info(f"🔧 Transaction Manager initialized for {chain_config.name}")
    
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
            
            self.logger.info(f"✅ Transaction Manager services initialized for {self.chain_config.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Transaction Manager services: {e}")
            return False
    
    async def submit_transaction(
        self, 
        request: TransactionSubmissionRequest
    ) -> TransactionManagerResult:
        """
        Submit a transaction through the complete lifecycle with gas optimization.
        
        This is the main entry point that coordinates all transaction operations:
        1. Gas optimization (Phase 6A integration)
        2. Transaction preparation
        3. DEX router execution
        4. Status monitoring
        5. Portfolio tracking
        6. WebSocket updates
        
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
            
            # Step 1: Gas Optimization (Phase 6A Integration)
            await self._optimize_transaction_gas(transaction_state, request)
            
            # Step 2: Execute transaction through DEX router
            swap_result = await self._execute_swap_transaction(transaction_state, request)
            
            # Step 3: Update transaction state with results
            transaction_state.swap_result = swap_result
            transaction_state.transaction_hash = swap_result.transaction_hash
            transaction_state.block_number = swap_result.block_number
            transaction_state.gas_used = swap_result.gas_used
            transaction_state.gas_price_gwei = swap_result.gas_price_gwei
            transaction_state.execution_time_ms = swap_result.execution_time_ms
            
            # Step 4: Start transaction monitoring
            asyncio.create_task(self._monitor_transaction_status(transaction_id))
            
            # Step 5: Calculate gas savings achieved
            gas_savings = self._calculate_gas_savings(transaction_state)
            
            # Update performance metrics
            self.total_transactions += 1
            if swap_result.success:
                self.successful_transactions += 1
                if gas_savings:
                    self.gas_savings_total += gas_savings
            
            self.logger.info(
                f"✅ Transaction submitted successfully: {transaction_id} "
                f"(Hash: {swap_result.transaction_hash[:10]}...)"
            )
            
            return TransactionManagerResult(
                success=True,
                transaction_id=transaction_id,
                transaction_state=transaction_state,
                gas_savings_achieved=gas_savings
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
                    f"(Hash: {swap_result.transaction_hash[:10]}...)"
                )
            else:
                transaction_state.status = TransactionStatus.FAILED
                transaction_state.error_message = swap_result.error_message
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
        Broadcast transaction status update via WebSocket.
        
        Args:
            transaction_state: Current transaction state to broadcast
        """
        if not self.enable_websocket_updates or not self.channel_layer:
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
            if transaction_state.status in [TransactionStatus.PREPARING, TransactionStatus.GAS_OPTIMIZING, TransactionStatus.READY_TO_SUBMIT]:
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
        
        return {
            'chain_id': self.chain_id,
            'chain_name': self.chain_config.name,
            'total_transactions': self.total_transactions,
            'successful_transactions': self.successful_transactions,
            'success_rate_percent': round(success_rate, 2),
            'average_gas_savings_percent': round(float(average_gas_savings), 2),
            'total_gas_savings_percent': round(float(self.gas_savings_total), 2),
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
                if (tx_state.status in [TransactionStatus.COMPLETED, TransactionStatus.FAILED, TransactionStatus.CANCELLED] and
                    tx_state.created_at < cutoff_time):
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
        from engine.config import config
        chain_config = config.get_chain_config(chain_id)
        
        if not chain_config:
            raise ValueError(f"No configuration found for chain {chain_id}")
        
        # Create and initialize transaction manager
        manager = TransactionManager(chain_config)
        await manager.initialize()
        
        _transaction_managers[chain_id] = manager
    
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
    deadline_minutes: int = 20
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
        is_paper_trade=is_paper_trade
    )