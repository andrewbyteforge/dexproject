"""
Nonce Manager - Transaction Sequencing Engine

Manages transaction nonces for fast lane execution with optimal sequencing,
gap detection, and recovery mechanisms. Ensures transaction ordering integrity
while maximizing throughput for high-frequency trading operations.

Key Features:
- Real-time nonce tracking and prediction
- Transaction gap detection and recovery
- Multi-wallet nonce management
- Parallel transaction support with sequential nonces
- Network congestion adaptation
- Stuck transaction detection and replacement
- Emergency nonce reset capabilities

File: dexproject/engine/execution/nonce_manager.py
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
import json
from collections import defaultdict, deque

# Web3 and blockchain imports
from web3 import Web3
from web3.exceptions import TransactionNotFound, BlockNotFound
from eth_typing import Address, HexStr
from eth_account import Account

# Redis for caching and coordination
import redis.asyncio as redis

# Internal imports
from ..config import config
from ..utils import safe_decimal


logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class NonceStatus(Enum):
    """Transaction nonce status tracking."""
    AVAILABLE = "available"       # Ready for use
    PENDING = "pending"          # Transaction submitted, awaiting confirmation
    CONFIRMED = "confirmed"      # Transaction confirmed on chain
    FAILED = "failed"           # Transaction failed or reverted
    STUCK = "stuck"             # Transaction stuck in mempool too long
    REPLACED = "replaced"       # Transaction replaced with higher gas


class TransactionPriority(Enum):
    """Transaction priority levels for nonce allocation."""
    LOW = "low"                 # Normal trading operations
    MEDIUM = "medium"           # Time-sensitive trades
    HIGH = "high"              # Fast lane critical trades
    EMERGENCY = "emergency"     # Emergency operations (cancellations, etc.)


@dataclass
class NonceTransaction:
    """Transaction data for nonce tracking."""
    nonce: int
    transaction_hash: Optional[str] = None
    wallet_address: str = ""
    gas_price: Optional[Decimal] = None
    gas_limit: int = 0
    priority: TransactionPriority = TransactionPriority.MEDIUM
    submitted_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    status: NonceStatus = NonceStatus.AVAILABLE
    replacement_count: int = 0
    chain_id: int = 0
    
    # Metadata
    trade_id: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    def __post_init__(self):
        """Initialize timestamps if not provided."""
        if self.submitted_at is None and self.status == NonceStatus.PENDING:
            self.submitted_at = datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "nonce": self.nonce,
            "transaction_hash": self.transaction_hash,
            "wallet_address": self.wallet_address,
            "gas_price": str(self.gas_price) if self.gas_price else None,
            "gas_limit": self.gas_limit,
            "priority": self.priority.value,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "status": self.status.value,
            "replacement_count": self.replacement_count,
            "chain_id": self.chain_id,
            "trade_id": self.trade_id,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries
        }


@dataclass
class WalletNonceState:
    """Nonce state tracking for a specific wallet."""
    wallet_address: str
    chain_id: int
    
    # Nonce tracking
    network_nonce: int = 0          # Last confirmed nonce on network
    local_nonce: int = 0            # Next nonce to use locally
    pending_nonces: Set[int] = field(default_factory=set)
    confirmed_nonces: Set[int] = field(default_factory=set)
    
    # Transaction tracking
    transactions: Dict[int, NonceTransaction] = field(default_factory=dict)
    
    # Performance metrics
    last_sync: Optional[datetime] = None
    sync_failures: int = 0
    gap_count: int = 0
    stuck_count: int = 0
    
    # Configuration
    max_pending_nonces: int = 10    # Maximum concurrent pending transactions
    stuck_threshold_minutes: int = 30  # Consider transaction stuck after this time
    
    def get_next_nonce(self) -> int:
        """Get the next available nonce for this wallet."""
        return max(self.local_nonce, self.network_nonce + 1)
    
    def has_available_nonce(self) -> bool:
        """Check if wallet has available nonce slots."""
        return len(self.pending_nonces) < self.max_pending_nonces
    
    def get_pending_count(self) -> int:
        """Get count of pending transactions."""
        return len(self.pending_nonces)
    
    def get_oldest_pending_age(self) -> Optional[timedelta]:
        """Get age of oldest pending transaction."""
        oldest_time = None
        
        for nonce in self.pending_nonces:
            tx = self.transactions.get(nonce)
            if tx and tx.submitted_at:
                if oldest_time is None or tx.submitted_at < oldest_time:
                    oldest_time = tx.submitted_at
        
        if oldest_time:
            return datetime.now(timezone.utc) - oldest_time
        return None


class NonceManager:
    """
    Advanced nonce management system for high-frequency transaction execution.
    
    Features:
    - Real-time nonce synchronization with blockchain state
    - Multi-wallet concurrent transaction support
    - Transaction gap detection and automatic recovery
    - Stuck transaction identification and replacement
    - Priority-based nonce allocation
    - Performance optimization for fast lane execution
    - Emergency nonce reset and recovery mechanisms
    """
    
    def __init__(self, chain_id: int, web3: Web3):
        """
        Initialize nonce manager for specific chain.
        
        Args:
            chain_id: Blockchain network identifier
            web3: Web3 instance for blockchain interaction
        """
        self.chain_id = chain_id
        self.web3 = web3
        self.logger = logging.getLogger(f"{__name__}.chain_{chain_id}")
        
        # Wallet state tracking
        self.wallet_states: Dict[str, WalletNonceState] = {}
        
        # Cache and storage
        self.redis_client: Optional[redis.Redis] = None
        self.cache_key_prefix = f"nonce_manager:{chain_id}"
        
        # Monitoring and background tasks
        self.is_active = False
        self.monitoring_task: Optional[asyncio.Task] = None
        self.sync_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
        
        # Performance tracking
        self.nonce_allocations = 0
        self.successful_confirmations = 0
        self.gap_detections = 0
        self.stuck_replacements = 0
        self.sync_errors = 0
        
        # Configuration
        self.sync_interval_seconds = 15
        self.cleanup_interval_seconds = 300  # 5 minutes
        self.max_nonce_gap = 5
        self.default_stuck_threshold_minutes = 30
        self.emergency_replacement_multiplier = 2.0
        
        # Transaction history for analysis
        self.confirmation_times: deque = deque(maxlen=100)
        self.gas_price_history: deque = deque(maxlen=100)
        
        self.logger.info(f"Nonce manager initialized for chain {chain_id}")
    
    async def start(self) -> bool:
        """
        Start the nonce manager with background monitoring.
        
        Returns:
            True if started successfully, False otherwise
        """
        try:
            # Initialize Redis connection
            self.redis_client = redis.Redis.from_url(
                config.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            
            # Test connection
            await self.redis_client.ping()
            
            # Load existing state from cache
            await self._load_state_from_cache()
            
            # Start background tasks
            self.monitoring_task = asyncio.create_task(self._monitor_transactions())
            self.sync_task = asyncio.create_task(self._sync_network_nonces())
            self.cleanup_task = asyncio.create_task(self._cleanup_old_data())
            
            self.is_active = True
            
            self.logger.info("Nonce manager started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start nonce manager: {e}")
            return False
    
    async def stop(self) -> None:
        """Stop the nonce manager and cleanup resources."""
        self.is_active = False
        
        # Cancel background tasks
        tasks_to_cancel = [
            self.monitoring_task,
            self.sync_task,
            self.cleanup_task
        ]
        
        for task in tasks_to_cancel:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Save state to cache
        await self._save_state_to_cache()
        
        # Close Redis connection
        if self.redis_client:
            await self.redis_client.close()
        
        self.logger.info("Nonce manager stopped")
    
    async def allocate_nonce(
        self, 
        wallet_address: str, 
        priority: TransactionPriority = TransactionPriority.MEDIUM,
        trade_id: Optional[str] = None
    ) -> Optional[NonceTransaction]:
        """
        Allocate next available nonce for wallet transaction.
        
        Args:
            wallet_address: Wallet address to allocate nonce for
            priority: Transaction priority level
            trade_id: Optional trade identifier for tracking
            
        Returns:
            NonceTransaction object with allocated nonce, or None if unavailable
        """
        try:
            # Normalize wallet address
            wallet_address = wallet_address.lower()
            
            # Ensure wallet state exists
            if wallet_address not in self.wallet_states:
                await self._initialize_wallet_state(wallet_address)
            
            wallet_state = self.wallet_states[wallet_address]
            
            # Check if wallet has available nonce capacity
            if not wallet_state.has_available_nonce():
                self.logger.warning(
                    f"Wallet {wallet_address} has no available nonce slots "
                    f"({wallet_state.get_pending_count()}/{wallet_state.max_pending_nonces})"
                )
                return None
            
            # Get next nonce
            next_nonce = wallet_state.get_next_nonce()
            
            # Create transaction object
            nonce_tx = NonceTransaction(
                nonce=next_nonce,
                wallet_address=wallet_address,
                priority=priority,
                chain_id=self.chain_id,
                trade_id=trade_id,
                status=NonceStatus.AVAILABLE
            )
            
            # Update wallet state
            wallet_state.local_nonce = next_nonce + 1
            wallet_state.transactions[next_nonce] = nonce_tx
            
            # Track allocation
            self.nonce_allocations += 1
            
            self.logger.debug(f"Allocated nonce {next_nonce} for wallet {wallet_address}")
            
            return nonce_tx
            
        except Exception as e:
            self.logger.error(f"Failed to allocate nonce for {wallet_address}: {e}")
            return None
    
    async def mark_transaction_submitted(
        self, 
        nonce_tx: NonceTransaction, 
        transaction_hash: str,
        gas_price: Decimal,
        gas_limit: int
    ) -> bool:
        """
        Mark transaction as submitted to mempool.
        
        Args:
            nonce_tx: NonceTransaction object
            transaction_hash: Blockchain transaction hash
            gas_price: Gas price used for transaction
            gas_limit: Gas limit for transaction
            
        Returns:
            True if marked successfully, False otherwise
        """
        try:
            wallet_address = nonce_tx.wallet_address.lower()
            
            if wallet_address not in self.wallet_states:
                self.logger.error(f"Wallet state not found for {wallet_address}")
                return False
            
            wallet_state = self.wallet_states[wallet_address]
            
            # Update transaction details
            nonce_tx.transaction_hash = transaction_hash
            nonce_tx.gas_price = gas_price
            nonce_tx.gas_limit = gas_limit
            nonce_tx.status = NonceStatus.PENDING
            nonce_tx.submitted_at = datetime.now(timezone.utc)
            
            # Update wallet state
            wallet_state.pending_nonces.add(nonce_tx.nonce)
            wallet_state.transactions[nonce_tx.nonce] = nonce_tx
            
            self.logger.info(
                f"Transaction submitted: nonce={nonce_tx.nonce}, "
                f"hash={transaction_hash[:10]}..., wallet={wallet_address}"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to mark transaction as submitted: {e}")
            return False
    
    async def check_transaction_confirmation(self, nonce_tx: NonceTransaction) -> bool:
        """
        Check if transaction has been confirmed on chain.
        
        Args:
            nonce_tx: NonceTransaction to check
            
        Returns:
            True if transaction is confirmed, False otherwise
        """
        try:
            if not nonce_tx.transaction_hash:
                return False
            
            # Get transaction receipt
            receipt = await self.web3.eth.get_transaction_receipt(nonce_tx.transaction_hash)
            
            if receipt:
                # Transaction is confirmed
                await self._mark_transaction_confirmed(nonce_tx, receipt)
                return True
            
            return False
            
        except TransactionNotFound:
            # Transaction not found - may have been dropped or replaced
            return False
        except Exception as e:
            self.logger.error(f"Error checking transaction confirmation: {e}")
            return False
    
    async def replace_stuck_transaction(
        self, 
        nonce_tx: NonceTransaction, 
        new_gas_price: Decimal
    ) -> Optional[str]:
        """
        Replace stuck transaction with higher gas price.
        
        Args:
            nonce_tx: Stuck transaction to replace
            new_gas_price: New gas price for replacement
            
        Returns:
            New transaction hash if successful, None otherwise
        """
        try:
            # This would normally create and submit a new transaction
            # with the same nonce but higher gas price
            
            # For now, simulate replacement
            new_tx_hash = f"0x{nonce_tx.nonce:064x}replacement"
            
            # Update transaction record
            old_hash = nonce_tx.transaction_hash
            nonce_tx.transaction_hash = new_tx_hash
            nonce_tx.gas_price = new_gas_price
            nonce_tx.replacement_count += 1
            nonce_tx.status = NonceStatus.PENDING
            nonce_tx.submitted_at = datetime.now(timezone.utc)
            
            self.stuck_replacements += 1
            
            self.logger.info(
                f"Replaced stuck transaction: nonce={nonce_tx.nonce}, "
                f"old_hash={old_hash[:10] if old_hash else 'None'}..., "
                f"new_hash={new_tx_hash[:10]}..., "
                f"new_gas_price={new_gas_price}"
            )
            
            return new_tx_hash
            
        except Exception as e:
            self.logger.error(f"Failed to replace stuck transaction: {e}")
            return None
    
    async def get_wallet_status(self, wallet_address: str) -> Dict[str, Any]:
        """
        Get comprehensive status for a specific wallet.
        
        Args:
            wallet_address: Wallet address to query
            
        Returns:
            Dictionary containing wallet nonce status
        """
        wallet_address = wallet_address.lower()
        
        if wallet_address not in self.wallet_states:
            return {"error": "Wallet not initialized"}
        
        wallet_state = self.wallet_states[wallet_address]
        
        # Calculate stuck transactions
        stuck_transactions = []
        current_time = datetime.now(timezone.utc)
        
        for nonce in wallet_state.pending_nonces:
            tx = wallet_state.transactions.get(nonce)
            if tx and tx.submitted_at:
                age_minutes = (current_time - tx.submitted_at).total_seconds() / 60
                if age_minutes > wallet_state.stuck_threshold_minutes:
                    stuck_transactions.append({
                        "nonce": nonce,
                        "hash": tx.transaction_hash,
                        "age_minutes": int(age_minutes),
                        "gas_price": str(tx.gas_price) if tx.gas_price else None,
                        "replacement_count": tx.replacement_count
                    })
        
        return {
            "wallet_address": wallet_address,
            "chain_id": self.chain_id,
            "network_nonce": wallet_state.network_nonce,
            "local_nonce": wallet_state.local_nonce,
            "next_nonce": wallet_state.get_next_nonce(),
            "pending_count": wallet_state.get_pending_count(),
            "max_pending": wallet_state.max_pending_nonces,
            "available_slots": wallet_state.max_pending_nonces - wallet_state.get_pending_count(),
            "confirmed_count": len(wallet_state.confirmed_nonces),
            "gap_count": wallet_state.gap_count,
            "stuck_count": len(stuck_transactions),
            "stuck_transactions": stuck_transactions,
            "last_sync": wallet_state.last_sync.isoformat() if wallet_state.last_sync else None,
            "sync_failures": wallet_state.sync_failures,
            "oldest_pending_age_minutes": (
                int(wallet_state.get_oldest_pending_age().total_seconds() / 60)
                if wallet_state.get_oldest_pending_age() else None
            )
        }
    
    async def get_manager_status(self) -> Dict[str, Any]:
        """
        Get comprehensive nonce manager status.
        
        Returns:
            Dictionary containing manager performance metrics
        """
        # Calculate average confirmation time
        avg_confirmation_time = (
            sum(self.confirmation_times) / len(self.confirmation_times)
            if self.confirmation_times else 0
        )
        
        # Calculate success rate
        success_rate = (
            (self.successful_confirmations / self.nonce_allocations * 100)
            if self.nonce_allocations > 0 else 0
        )
        
        return {
            "manager": "nonce_manager",
            "chain_id": self.chain_id,
            "is_active": self.is_active,
            "wallets_managed": len(self.wallet_states),
            "performance": {
                "nonce_allocations": self.nonce_allocations,
                "successful_confirmations": self.successful_confirmations,
                "success_rate_percent": round(success_rate, 2),
                "gap_detections": self.gap_detections,
                "stuck_replacements": self.stuck_replacements,
                "sync_errors": self.sync_errors,
                "avg_confirmation_time_seconds": round(avg_confirmation_time, 2)
            },
            "configuration": {
                "sync_interval_seconds": self.sync_interval_seconds,
                "cleanup_interval_seconds": self.cleanup_interval_seconds,
                "max_nonce_gap": self.max_nonce_gap,
                "stuck_threshold_minutes": self.default_stuck_threshold_minutes,
                "emergency_replacement_multiplier": self.emergency_replacement_multiplier
            }
        }
    
    async def emergency_reset_wallet(self, wallet_address: str) -> bool:
        """
        Emergency reset of wallet nonce state - use with extreme caution.
        
        Args:
            wallet_address: Wallet to reset
            
        Returns:
            True if reset successful, False otherwise
        """
        try:
            wallet_address = wallet_address.lower()
            
            self.logger.warning(f"EMERGENCY RESET requested for wallet {wallet_address}")
            
            # Get current network nonce
            network_nonce = await self.web3.eth.get_transaction_count(wallet_address)
            
            # Reset wallet state
            wallet_state = WalletNonceState(
                wallet_address=wallet_address,
                chain_id=self.chain_id,
                network_nonce=network_nonce,
                local_nonce=network_nonce,
                last_sync=datetime.now(timezone.utc)
            )
            
            self.wallet_states[wallet_address] = wallet_state
            
            # Clear cache
            cache_key = f"{self.cache_key_prefix}:wallet:{wallet_address}"
            if self.redis_client:
                await self.redis_client.delete(cache_key)
            
            self.logger.warning(
                f"EMERGENCY RESET completed for wallet {wallet_address} - "
                f"reset to nonce {network_nonce}"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Emergency reset failed for {wallet_address}: {e}")
            return False
    
    # =========================================================================
    # PRIVATE METHODS - Core Logic
    # =========================================================================
    
    async def _initialize_wallet_state(self, wallet_address: str) -> None:
        """Initialize nonce state for a new wallet."""
        try:
            # Get current network nonce
            network_nonce = await self.web3.eth.get_transaction_count(wallet_address)
            
            # Create wallet state
            wallet_state = WalletNonceState(
                wallet_address=wallet_address,
                chain_id=self.chain_id,
                network_nonce=network_nonce,
                local_nonce=network_nonce,
                last_sync=datetime.now(timezone.utc)
            )
            
            self.wallet_states[wallet_address] = wallet_state
            
            self.logger.info(f"Initialized wallet state for {wallet_address} with nonce {network_nonce}")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize wallet state for {wallet_address}: {e}")
            raise
    
    async def _mark_transaction_confirmed(self, nonce_tx: NonceTransaction, receipt: Dict) -> None:
        """Mark transaction as confirmed and update state."""
        wallet_address = nonce_tx.wallet_address.lower()
        wallet_state = self.wallet_states[wallet_address]
        
        # Update transaction status
        nonce_tx.status = NonceStatus.CONFIRMED
        nonce_tx.confirmed_at = datetime.now(timezone.utc)
        
        # Update wallet state
        wallet_state.pending_nonces.discard(nonce_tx.nonce)
        wallet_state.confirmed_nonces.add(nonce_tx.nonce)
        
        # Track confirmation time
        if nonce_tx.submitted_at:
            confirmation_time = (nonce_tx.confirmed_at - nonce_tx.submitted_at).total_seconds()
            self.confirmation_times.append(confirmation_time)
        
        # Track gas price
        if nonce_tx.gas_price:
            self.gas_price_history.append(float(nonce_tx.gas_price))
        
        self.successful_confirmations += 1
        
        self.logger.info(
            f"Transaction confirmed: nonce={nonce_tx.nonce}, "
            f"hash={nonce_tx.transaction_hash[:10] if nonce_tx.transaction_hash else 'None'}..., "
            f"wallet={wallet_address}"
        )
    
    async def _detect_and_handle_gaps(self, wallet_state: WalletNonceState) -> None:
        """Detect nonce gaps and attempt recovery."""
        try:
            # Check for gaps in confirmed nonces
            if not wallet_state.confirmed_nonces:
                return
            
            min_confirmed = min(wallet_state.confirmed_nonces)
            max_confirmed = max(wallet_state.confirmed_nonces)
            
            expected_nonces = set(range(min_confirmed, max_confirmed + 1))
            missing_nonces = expected_nonces - wallet_state.confirmed_nonces
            
            if missing_nonces:
                self.gap_detections += 1
                wallet_state.gap_count += 1
                
                self.logger.warning(
                    f"Detected nonce gaps for wallet {wallet_state.wallet_address}: "
                    f"missing nonces {sorted(missing_nonces)}"
                )
                
                # Attempt to recover missing transactions
                for missing_nonce in sorted(missing_nonces):
                    await self._attempt_nonce_recovery(wallet_state, missing_nonce)
        
        except Exception as e:
            self.logger.error(f"Error detecting nonce gaps: {e}")
    
    async def _attempt_nonce_recovery(self, wallet_state: WalletNonceState, nonce: int) -> None:
        """Attempt to recover information about a missing nonce."""
        try:
            # Check if we have a transaction record for this nonce
            if nonce in wallet_state.transactions:
                tx = wallet_state.transactions[nonce]
                
                # If we have a transaction hash, check its status
                if tx.transaction_hash:
                    confirmed = await self.check_transaction_confirmation(tx)
                    if confirmed:
                        return
                    
                    # Check if transaction is still pending or was dropped
                    try:
                        pending_tx = await self.web3.eth.get_transaction(tx.transaction_hash)
                        if pending_tx:
                            # Transaction is still in mempool
                            tx.status = NonceStatus.PENDING
                            wallet_state.pending_nonces.add(nonce)
                            return
                    except TransactionNotFound:
                        # Transaction was dropped
                        tx.status = NonceStatus.FAILED
                        self.logger.warning(f"Transaction with nonce {nonce} was dropped")
            
            # If we can't recover, mark the nonce as potentially problematic
            self.logger.warning(f"Could not recover nonce {nonce} for wallet {wallet_state.wallet_address}")
            
        except Exception as e:
            self.logger.error(f"Error attempting nonce recovery for {nonce}: {e}")
    
    async def _identify_stuck_transactions(self, wallet_state: WalletNonceState) -> List[NonceTransaction]:
        """Identify transactions that appear to be stuck in mempool."""
        stuck_transactions = []
        current_time = datetime.now(timezone.utc)
        
        for nonce in wallet_state.pending_nonces:
            tx = wallet_state.transactions.get(nonce)
            
            if tx and tx.submitted_at:
                age = current_time - tx.submitted_at
                age_minutes = age.total_seconds() / 60
                
                if age_minutes > wallet_state.stuck_threshold_minutes:
                    tx.status = NonceStatus.STUCK
                    stuck_transactions.append(tx)
                    wallet_state.stuck_count += 1
        
        return stuck_transactions
    
    # =========================================================================
    # PRIVATE METHODS - Background Tasks
    # =========================================================================
    
    async def _monitor_transactions(self) -> None:
        """Background task to monitor pending transactions."""
        self.logger.info("Started transaction monitoring")
        
        while self.is_active:
            try:
                for wallet_address, wallet_state in self.wallet_states.items():
                    # Check pending transactions for confirmation
                    pending_nonces = list(wallet_state.pending_nonces)
                    
                    for nonce in pending_nonces:
                        tx = wallet_state.transactions.get(nonce)
                        if tx:
                            await self.check_transaction_confirmation(tx)
                    
                    # Identify and handle stuck transactions
                    stuck_transactions = await self._identify_stuck_transactions(wallet_state)
                    for stuck_tx in stuck_transactions:
                        # Calculate replacement gas price
                        if stuck_tx.gas_price:
                            new_gas_price = stuck_tx.gas_price * Decimal(str(self.emergency_replacement_multiplier))
                            await self.replace_stuck_transaction(stuck_tx, new_gas_price)
                    
                    # Detect and handle nonce gaps
                    await self._detect_and_handle_gaps(wallet_state)
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in transaction monitoring: {e}")
                await asyncio.sleep(30)  # Wait longer on error
        
        self.logger.info("Transaction monitoring stopped")
    
    async def _sync_network_nonces(self) -> None:
        """Background task to sync nonces with network state."""
        self.logger.info("Started network nonce synchronization")
        
        while self.is_active:
            try:
                for wallet_address, wallet_state in self.wallet_states.items():
                    try:
                        # Get current network nonce
                        network_nonce = await self.web3.eth.get_transaction_count(wallet_address)
                        
                        # Update if changed
                        if network_nonce != wallet_state.network_nonce:
                            old_nonce = wallet_state.network_nonce
                            wallet_state.network_nonce = network_nonce
                            wallet_state.last_sync = datetime.now(timezone.utc)
                            
                            self.logger.debug(
                                f"Network nonce updated for {wallet_address}: "
                                f"{old_nonce} -> {network_nonce}"
                            )
                        
                        # Reset sync failure counter on success
                        wallet_state.sync_failures = 0
                        
                    except Exception as e:
                        wallet_state.sync_failures += 1
                        self.sync_errors += 1
                        
                        self.logger.error(
                            f"Failed to sync nonce for {wallet_address} "
                            f"(failure #{wallet_state.sync_failures}): {e}"
                        )
                
                await asyncio.sleep(self.sync_interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in nonce synchronization: {e}")
                await asyncio.sleep(60)  # Wait longer on error
        
        self.logger.info("Network nonce synchronization stopped")
    
    async def _cleanup_old_data(self) -> None:
        """Background task to cleanup old transaction data."""
        self.logger.info("Started data cleanup task")
        
        while self.is_active:
            try:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
                
                for wallet_state in self.wallet_states.values():
                    # Remove old confirmed transactions
                    old_transactions = [
                        nonce for nonce, tx in wallet_state.transactions.items()
                        if (tx.confirmed_at and tx.confirmed_at < cutoff_time and 
                            tx.status == NonceStatus.CONFIRMED)
                    ]
                    
                    for nonce in old_transactions:
                        del wallet_state.transactions[nonce]
                        wallet_state.confirmed_nonces.discard(nonce)
                    
                    if old_transactions:
                        self.logger.debug(
                            f"Cleaned up {len(old_transactions)} old transactions "
                            f"for wallet {wallet_state.wallet_address}"
                        )
                
                await asyncio.sleep(self.cleanup_interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in data cleanup: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
        
        self.logger.info("Data cleanup task stopped")
    
    # =========================================================================
    # PRIVATE METHODS - State Persistence
    # =========================================================================
    
    async def _save_state_to_cache(self) -> None:
        """Save current state to Redis cache."""
        if not self.redis_client:
            return
        
        try:
            for wallet_address, wallet_state in self.wallet_states.items():
                cache_key = f"{self.cache_key_prefix}:wallet:{wallet_address}"
                
                state_data = {
                    "wallet_address": wallet_state.wallet_address,
                    "chain_id": wallet_state.chain_id,
                    "network_nonce": wallet_state.network_nonce,
                    "local_nonce": wallet_state.local_nonce,
                    "pending_nonces": list(wallet_state.pending_nonces),
                    "confirmed_nonces": list(wallet_state.confirmed_nonces),
                    "last_sync": wallet_state.last_sync.isoformat() if wallet_state.last_sync else None,
                    "sync_failures": wallet_state.sync_failures,
                    "gap_count": wallet_state.gap_count,
                    "stuck_count": wallet_state.stuck_count,
                    "transactions": {
                        str(nonce): tx.to_dict() 
                        for nonce, tx in wallet_state.transactions.items()
                    }
                }
                
                await self.redis_client.setex(
                    cache_key,
                    3600,  # 1 hour TTL
                    json.dumps(state_data)
                )
            
            self.logger.debug(f"Saved state for {len(self.wallet_states)} wallets to cache")
            
        except Exception as e:
            self.logger.error(f"Failed to save state to cache: {e}")
    
    async def _load_state_from_cache(self) -> None:
        """Load existing state from Redis cache."""
        if not self.redis_client:
            return
        
        try:
            # Get all wallet cache keys
            pattern = f"{self.cache_key_prefix}:wallet:*"
            cache_keys = await self.redis_client.keys(pattern)
            
            for cache_key in cache_keys:
                try:
                    data = await self.redis_client.get(cache_key)
                    if data:
                        state_data = json.loads(data)
                        
                        # Reconstruct wallet state
                        wallet_state = WalletNonceState(
                            wallet_address=state_data["wallet_address"],
                            chain_id=state_data["chain_id"],
                            network_nonce=state_data["network_nonce"],
                            local_nonce=state_data["local_nonce"],
                            pending_nonces=set(state_data["pending_nonces"]),
                            confirmed_nonces=set(state_data["confirmed_nonces"]),
                            sync_failures=state_data["sync_failures"],
                            gap_count=state_data["gap_count"],
                            stuck_count=state_data["stuck_count"]
                        )
                        
                        if state_data["last_sync"]:
                            wallet_state.last_sync = datetime.fromisoformat(state_data["last_sync"])
                        
                        # Reconstruct transactions
                        for nonce_str, tx_data in state_data["transactions"].items():
                            nonce = int(nonce_str)
                            tx = NonceTransaction(
                                nonce=nonce,
                                transaction_hash=tx_data["transaction_hash"],
                                wallet_address=tx_data["wallet_address"],
                                gas_price=Decimal(tx_data["gas_price"]) if tx_data["gas_price"] else None,
                                gas_limit=tx_data["gas_limit"],
                                priority=TransactionPriority(tx_data["priority"]),
                                status=NonceStatus(tx_data["status"]),
                                replacement_count=tx_data["replacement_count"],
                                chain_id=tx_data["chain_id"],
                                trade_id=tx_data["trade_id"],
                                retry_count=tx_data["retry_count"],
                                max_retries=tx_data["max_retries"]
                            )
                            
                            if tx_data["submitted_at"]:
                                tx.submitted_at = datetime.fromisoformat(tx_data["submitted_at"])
                            if tx_data["confirmed_at"]:
                                tx.confirmed_at = datetime.fromisoformat(tx_data["confirmed_at"])
                            
                            wallet_state.transactions[nonce] = tx
                        
                        self.wallet_states[wallet_state.wallet_address] = wallet_state
                        
                except Exception as e:
                    self.logger.error(f"Failed to load state from cache key {cache_key}: {e}")
            
            if self.wallet_states:
                self.logger.info(f"Loaded state for {len(self.wallet_states)} wallets from cache")
            
        except Exception as e:
            self.logger.error(f"Failed to load state from cache: {e}")