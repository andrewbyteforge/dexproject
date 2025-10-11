"""
Transaction Manager Retry and Recovery Components - Paper Trading App

Advanced retry logic, stuck transaction monitoring, nonce management, and recovery mechanisms.
This module handles all transaction recovery scenarios including gas escalation and replacement.

File: dexproject/paper_trading/services/transaction_manager_retry.py
"""

import os
import logging
import asyncio
from typing import Dict, Optional, List, Tuple
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from django.contrib.auth.models import User

from .transaction_manager_base import (
    TransactionState,
    TransactionStatus,
    RetryConfiguration,
    ErrorClassification,
    classify_error,
    calculate_gas_escalation,
    calculate_retry_backoff
)

logger = logging.getLogger(__name__)


class TransactionRetryManager:
    """
    Manages retry logic and stuck transaction recovery.
    
    This class handles:
    - Automatic retry with gas escalation
    - Stuck transaction detection and replacement
    - Nonce gap detection and resolution
    - Circuit breaker pattern implementation
    """
    
    def __init__(self, chain_id: int, retry_config: RetryConfiguration):
        """
        Initialize the retry manager.
        
        Args:
            chain_id: Blockchain chain ID
            retry_config: Retry configuration settings
        """
        self.chain_id = chain_id
        self.retry_config = retry_config
        self.logger = logging.getLogger(f'paper_trading.retry_manager.{chain_id}')
        
        # Active retry tasks
        self._retry_tasks: Dict[str, asyncio.Task] = {}
        
        # Circuit breaker state
        self._consecutive_failures = 0
        self._circuit_open = False
        self._circuit_open_until: Optional[datetime] = None
        
        # Web3 client (injected from main manager)
        self._web3_client = None
        self._wallet_manager = None
    
    def set_dependencies(self, web3_client, wallet_manager):
        """
        Set required dependencies.
        
        Args:
            web3_client: Web3 client instance
            wallet_manager: Wallet manager instance
        """
        self._web3_client = web3_client
        self._wallet_manager = wallet_manager
    
    def is_circuit_open(self) -> bool:
        """
        Check if circuit breaker is open.
        
        Returns:
            True if circuit is open and blocking requests
        """
        if self._circuit_open and self._circuit_open_until:
            if datetime.now(timezone.utc) < self._circuit_open_until:
                return True
            else:
                # Reset circuit breaker
                self._circuit_open = False
                self._circuit_open_until = None
                self._consecutive_failures = 0
                self.logger.info("🔄 Circuit breaker reset")
        
        return False
    
    def record_failure(self) -> None:
        """Record a failure and potentially open circuit breaker."""
        self._consecutive_failures += 1
        
        if self._consecutive_failures >= self.retry_config.circuit_breaker_threshold:
            self.open_circuit_breaker()
    
    def record_success(self) -> None:
        """Record a success and reset failure counter."""
        self._consecutive_failures = 0
    
    def open_circuit_breaker(self) -> None:
        """Open the circuit breaker to prevent cascade failures."""
        self._circuit_open = True
        self._circuit_open_until = datetime.now(timezone.utc) + timedelta(minutes=5)
        
        self.logger.error(
            f"🛑 Circuit breaker OPEN due to {self._consecutive_failures} consecutive failures. "
            f"Will reset at {self._circuit_open_until}"
        )
    
    async def should_retry_transaction(
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
            self.logger.info(f"Max retries ({transaction_state.max_retries}) reached")
            return False
        
        # Check circuit breaker
        if self.is_circuit_open():
            self.logger.info("Circuit breaker is open, not retrying")
            return False
        
        # If no error, don't retry
        if not error and not transaction_state.error_message:
            return False
        
        error_msg = error or transaction_state.error_message or ""
        error_class = classify_error(error_msg)
        
        # Check error type against configuration
        if error_class == ErrorClassification.CONTRACT_REVERT:
            return self.retry_config.retry_on_revert
        elif error_class == ErrorClassification.OUT_OF_GAS:
            return self.retry_config.retry_on_out_of_gas
        elif error_class == ErrorClassification.NETWORK_ERROR:
            return self.retry_config.retry_on_network_error
        elif error_class == ErrorClassification.NONCE_ERROR:
            return self.retry_config.retry_on_nonce_error
        elif error_class == ErrorClassification.INSUFFICIENT_FUNDS:
            return False  # Never retry insufficient funds
        
        # Default: retry on generic errors
        return True
    
    def calculate_retry_gas_price(
        self,
        transaction_state: TransactionState
    ) -> Decimal:
        """
        Calculate escalated gas price for retry.
        
        Args:
            transaction_state: Current transaction state
            
        Returns:
            New gas price in gwei
        """
        original_gas = transaction_state.original_gas_price or transaction_state.gas_price_gwei or Decimal('30')
        
        new_gas_price = calculate_gas_escalation(
            original_gas,
            transaction_state.retry_count,
            self.retry_config.gas_escalation_percent
        )
        
        # Apply ceiling
        if new_gas_price > self.retry_config.max_gas_price_gwei:
            self.logger.warning(
                f"⚠️ Capping gas price at {self.retry_config.max_gas_price_gwei} gwei "
                f"(calculated: {new_gas_price} gwei)"
            )
            new_gas_price = self.retry_config.max_gas_price_gwei
        
        return new_gas_price
    
    def calculate_backoff_delay(self, retry_count: int) -> float:
        """
        Calculate retry backoff delay.
        
        Args:
            retry_count: Current retry attempt
            
        Returns:
            Delay in seconds
        """
        return calculate_retry_backoff(
            retry_count,
            self.retry_config.initial_backoff_seconds,
            self.retry_config.max_backoff_seconds,
            self.retry_config.backoff_multiplier
        )
    
    async def schedule_auto_retry(
        self,
        transaction_id: str,
        retry_callback
    ) -> None:
        """
        Schedule automatic retry for a transaction.
        
        Args:
            transaction_id: Transaction to retry
            retry_callback: Callback function to perform retry
        """
        if transaction_id in self._retry_tasks:
            self.logger.warning(f"Retry already scheduled for {transaction_id}")
            return
        
        retry_task = asyncio.create_task(retry_callback())
        self._retry_tasks[transaction_id] = retry_task
    
    def cancel_retry(self, transaction_id: str) -> bool:
        """
        Cancel a scheduled retry.
        
        Args:
            transaction_id: Transaction ID
            
        Returns:
            True if retry was cancelled
        """
        if transaction_id in self._retry_tasks:
            self._retry_tasks[transaction_id].cancel()
            del self._retry_tasks[transaction_id]
            return True
        return False
    
    async def cleanup_retry_tasks(self) -> None:
        """Cancel all active retry tasks."""
        for task in self._retry_tasks.values():
            task.cancel()
        
        if self._retry_tasks:
            await asyncio.gather(
                *self._retry_tasks.values(),
                return_exceptions=True
            )
        
        self._retry_tasks.clear()


class StuckTransactionMonitor:
    """
    Monitors and handles stuck transactions.
    
    Features:
    - Intelligent stuck detection based on multiple criteria
    - Nonce gap detection and recovery
    - Smart replacement decisions
    - Mempool monitoring
    """
    
    def __init__(self, chain_id: int, retry_config: RetryConfiguration):
        """
        Initialize the stuck transaction monitor.
        
        Args:
            chain_id: Blockchain chain ID
            retry_config: Retry configuration
        """
        self.chain_id = chain_id
        self.retry_config = retry_config
        self.logger = logging.getLogger(f'paper_trading.stuck_monitor.{chain_id}')
        
        # Dependencies (injected)
        self._web3_client = None
        self._wallet_manager = None
        
        # Monitoring task
        self._monitor_task: Optional[asyncio.Task] = None
        self._active_transactions: Dict[str, TransactionState] = {}
        self._replacement_callback = None
    
    def set_dependencies(self, web3_client, wallet_manager):
        """
        Set required dependencies.
        
        Args:
            web3_client: Web3 client instance
            wallet_manager: Wallet manager instance
        """
        self._web3_client = web3_client
        self._wallet_manager = wallet_manager
    
    def set_transactions(self, transactions: Dict[str, TransactionState]):
        """
        Set reference to active transactions.
        
        Args:
            transactions: Dictionary of active transactions
        """
        self._active_transactions = transactions
    
    def set_replacement_callback(self, callback):
        """
        Set callback for transaction replacement.
        
        Args:
            callback: Async function to call for replacement
        """
        self._replacement_callback = callback
    
    async def start_monitoring(self) -> None:
        """Start the stuck transaction monitoring task."""
        if self._monitor_task and not self._monitor_task.done():
            self.logger.warning("Monitor already running")
            return
        
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self.logger.info("🔍 Started stuck transaction monitor")
    
    async def stop_monitoring(self) -> None:
        """Stop the monitoring task."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
            self.logger.info("🛑 Stopped stuck transaction monitor")
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                current_time = datetime.now(timezone.utc)
                current_gas_price = await self._get_current_gas_price()
                
                # Group transactions by user for nonce management
                user_transactions = self._group_transactions_by_user()
                
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
    
    def _group_transactions_by_user(self) -> Dict[int, List[Tuple[str, TransactionState]]]:
        """
        Group pending transactions by user.
        
        Returns:
            Dictionary of user_id to list of (tx_id, tx_state) tuples
        """
        user_transactions = {}
        
        for tx_id, tx_state in self._active_transactions.items():
            if tx_state.status in [TransactionStatus.PENDING, TransactionStatus.SUBMITTED]:
                user_id = tx_state.user_id
                if user_id not in user_transactions:
                    user_transactions[user_id] = []
                user_transactions[user_id].append((tx_id, tx_state))
        
        return user_transactions
    
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
            transactions: List of (tx_id, tx_state) tuples
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
            
            # Get expected next nonce
            expected_nonce = await self._get_user_next_nonce(user_id)
            
            # Check for nonce gaps
            if transactions_with_nonce:
                await self._check_nonce_gaps(transactions_with_nonce, expected_nonce)
            
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
            Reason why transaction is stuck, or None
        """
        if not tx_state.submitted_at:
            return None
        
        time_pending = current_time - tx_state.submitted_at
        
        # 1. Time-based check with gas price adjustment
        base_threshold = timedelta(minutes=self.retry_config.stuck_transaction_minutes)
        
        if tx_state.gas_price_gwei and current_gas_price > 0:
            gas_ratio = float(tx_state.gas_price_gwei / current_gas_price)
            if gas_ratio < 0.5:
                adjusted_threshold = base_threshold * 2
            elif gas_ratio < 0.8:
                adjusted_threshold = base_threshold * 1.5
            else:
                adjusted_threshold = base_threshold
        else:
            adjusted_threshold = base_threshold
        
        if time_pending > adjusted_threshold:
            return f"pending_too_long ({time_pending.total_seconds() / 60:.1f} minutes)"
        
        # 2. Gas price too low check
        if tx_state.gas_price_gwei and current_gas_price > 0:
            if tx_state.gas_price_gwei < (current_gas_price * Decimal('0.5')):
                return f"gas_too_low ({tx_state.gas_price_gwei:.2f} vs {current_gas_price:.2f} gwei)"
        
        # 3. Check if dropped from mempool
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
        Handle a stuck transaction.
        
        Args:
            tx_id: Transaction ID
            tx_state: Transaction state
            stuck_reason: Reason for being stuck
            current_gas_price: Current gas price
        """
        self.logger.warning(
            f"⚠️ Stuck transaction detected: {tx_id} "
            f"(Reason: {stuck_reason})"
        )
        
        # Mark as stuck
        tx_state.status = TransactionStatus.STUCK
        tx_state.error_message = f"Transaction stuck: {stuck_reason}"
        
        if not self.retry_config.auto_retry_enabled:
            return
        
        # Check recent retry
        if tx_state.last_retry_at:
            time_since_retry = datetime.now(timezone.utc) - tx_state.last_retry_at
            if time_since_retry < timedelta(minutes=5):
                return
        
        # Calculate replacement gas
        if stuck_reason.startswith("gas_too_low"):
            gas_multiplier = Decimal('1.5')
        elif stuck_reason == "dropped_from_mempool":
            gas_multiplier = Decimal('1.3')
        elif stuck_reason == "nonce_conflict":
            await self._resolve_nonce_conflict(tx_id, tx_state)
            return
        else:
            gas_multiplier = self.retry_config.replacement_gas_multiplier
        
        # Calculate new gas price
        new_gas_price = self._calculate_replacement_gas_price(
            tx_state.gas_price_gwei or current_gas_price,
            current_gas_price,
            gas_multiplier
        )
        
        # Check if worthwhile
        if not await self._is_replacement_worthwhile(tx_state, new_gas_price):
            return
        
        # Request replacement via callback
        if self._replacement_callback:
            self.logger.info(f"🔄 Auto-replacing stuck transaction: {tx_id}")
            await self._replacement_callback(tx_id, gas_multiplier)
    
    async def _get_current_gas_price(self) -> Decimal:
        """Get current network gas price."""
        try:
            if self._web3_client:
                gas_price_wei = await self._web3_client.web3.eth.gas_price
                return Decimal(gas_price_wei) / Decimal(10**9)
            else:
                return Decimal(os.getenv('DEFAULT_GAS_PRICE_GWEI', '30'))
        except Exception as e:
            self.logger.error(f"Error getting gas price: {e}")
            return Decimal('30')
    
    async def _get_user_next_nonce(self, user_id: int) -> int:
        """Get next expected nonce for user."""
        try:
            if self._wallet_manager and self._web3_client:
                user = await User.objects.aget(id=user_id)
                
                if not hasattr(user, 'wallet') or not user.wallet:
                    return 0
                
                wallet_address = user.wallet.address
                nonce = await self._web3_client.web3.eth.get_transaction_count(
                    wallet_address,
                    'pending'
                )
                return nonce
            return 0
        except Exception as e:
            self.logger.error(f"Error getting nonce for user {user_id}: {e}")
            return 0
    
    async def _check_nonce_gaps(
        self,
        transactions: List[Tuple[str, TransactionState]],
        expected_nonce: int
    ) -> None:
        """Check for gaps in transaction nonces."""
        if not transactions:
            return
        
        first_tx_id, first_tx_state = transactions[0]
        if first_tx_state.nonce > expected_nonce:
            self.logger.warning(
                f"⚠️ Nonce gap detected: Expected {expected_nonce}, "
                f"but first transaction has nonce {first_tx_state.nonce}"
            )
        
        for i in range(len(transactions) - 1):
            current_tx_id, current_tx_state = transactions[i]
            next_tx_id, next_tx_state = transactions[i + 1]
            
            if next_tx_state.nonce > current_tx_state.nonce + 1:
                self.logger.warning(
                    f"⚠️ Nonce gap between transactions: "
                    f"{current_tx_id} (nonce {current_tx_state.nonce}) and "
                    f"{next_tx_id} (nonce {next_tx_state.nonce})"
                )
                next_tx_state.error_message = f"Blocked by nonce gap"
    
    async def _transaction_dropped_from_mempool(
        self,
        tx_state: TransactionState
    ) -> bool:
        """Check if transaction was dropped from mempool."""
        try:
            if not tx_state.transaction_hash or not self._web3_client:
                return False
            
            try:
                tx = await self._web3_client.web3.eth.get_transaction(tx_state.transaction_hash)
                return False  # Still exists
            except Exception as e:
                if "not found" in str(e).lower():
                    try:
                        receipt = await self._web3_client.web3.eth.get_transaction_receipt(
                            tx_state.transaction_hash
                        )
                        return False  # Was mined
                    except:
                        return True  # Not found anywhere
                return False
                
        except Exception as e:
            self.logger.error(f"Error checking mempool: {e}")
            return False
    
    async def _has_nonce_conflict(self, tx_state: TransactionState) -> bool:
        """Check if transaction has a nonce conflict."""
        if tx_state.nonce is None:
            return False
        
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
        """Resolve a nonce conflict."""
        self.logger.info(f"🔧 Resolving nonce conflict for {tx_id}")
        
        tx_state.status = TransactionStatus.FAILED
        tx_state.error_message = "Nonce conflict - another transaction used this nonce"
    
    def _calculate_replacement_gas_price(
        self,
        original_gas: Decimal,
        current_gas: Decimal,
        multiplier: Decimal
    ) -> Decimal:
        """Calculate replacement gas price."""
        replacement_price = max(
            current_gas * multiplier,
            original_gas * multiplier
        )
        
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
        """Determine if replacement is worthwhile."""
        # Don't replace if already retried multiple times
        if tx_state.retry_count >= 2:
            return False
        
        # Ensure significant increase (at least 10%)
        if tx_state.gas_price_gwei:
            increase_ratio = (new_gas_price - tx_state.gas_price_gwei) / tx_state.gas_price_gwei
            if increase_ratio < Decimal('0.1'):
                return False
        
        # Check gas cost vs trade value
        if tx_state.swap_params:
            estimated_gas_cost_usd = self._estimate_gas_cost_usd(new_gas_price)
            trade_value_usd = self._estimate_trade_value_usd(tx_state.swap_params)
            
            if estimated_gas_cost_usd > (trade_value_usd * Decimal('0.05')):
                self.logger.warning(
                    f"⚠️ Replacement gas cost exceeds 5% of trade value"
                )
                return False
        
        return True
    
    def _estimate_gas_cost_usd(self, gas_price_gwei: Decimal) -> Decimal:
        """Estimate gas cost in USD."""
        gas_limit = 150000
        eth_price = Decimal('2000')  # Simplified estimate
        
        gas_cost_eth = (gas_price_gwei * Decimal(gas_limit)) / Decimal(10**9)
        return gas_cost_eth * eth_price
    
    def _estimate_trade_value_usd(self, swap_params) -> Decimal:
        """Estimate trade value in USD."""
        # Simplified - would use price oracles in production
        from .dex_router_service import SwapType
        
        if swap_params.swap_type == SwapType.EXACT_ETH_FOR_TOKENS:
            eth_amount = Decimal(swap_params.amount_in) / Decimal(10**18)
            return eth_amount * Decimal('2000')
        else:
            return Decimal('100')  # Default estimate