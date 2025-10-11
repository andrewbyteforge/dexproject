"""
Transaction Manager Base Components - Paper Trading App

Core data structures, enums, and configuration classes for the transaction management system.
This module contains all the foundational elements used across the transaction manager.

File: dexproject/paper_trading/services/transaction_manager_base.py
"""

import logging
from typing import Dict, Any, Optional, Callable, List, Tuple
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum

from django.contrib.auth.models import User
from eth_typing import HexStr

from .dex_router_service import SwapParams, SwapResult
from .gas_optimizer import GasOptimizationResult, TradingGasStrategy

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
    """
    Current state of a managed transaction.
    
    This comprehensive state object tracks all aspects of a transaction's
    lifecycle including execution details, retry attempts, and gas optimization.
    """
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
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert transaction state to dictionary for serialization.
        
        Returns:
            Dictionary representation of transaction state
        """
        return {
            'transaction_id': self.transaction_id,
            'user_id': self.user_id,
            'chain_id': self.chain_id,
            'status': self.status.value,
            'transaction_hash': self.transaction_hash,
            'block_number': self.block_number,
            'gas_used': self.gas_used,
            'gas_price_gwei': float(self.gas_price_gwei) if self.gas_price_gwei else None,
            'nonce': self.nonce,
            'gas_savings_percent': float(self.gas_savings_percent) if self.gas_savings_percent else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'submitted_at': self.submitted_at.isoformat() if self.submitted_at else None,
            'confirmed_at': self.confirmed_at.isoformat() if self.confirmed_at else None,
            'execution_time_ms': self.execution_time_ms,
            'error_message': self.error_message,
            'error_type': self.error_type,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
        }


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
    
    def validate(self) -> bool:
        """
        Validate the submission request.
        
        Returns:
            True if request is valid
            
        Raises:
            ValueError: If request validation fails
        """
        if not self.user:
            raise ValueError("User is required")
        
        if not self.chain_id:
            raise ValueError("Chain ID is required")
        
        if not self.swap_params:
            raise ValueError("Swap parameters are required")
        
        if self.priority not in ["normal", "high", "emergency"]:
            raise ValueError(f"Invalid priority: {self.priority}")
        
        # Validate swap params
        if self.swap_params.amount_in <= 0:
            raise ValueError("Amount in must be positive")
        
        return True


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
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert result to dictionary for API responses.
        
        Returns:
            Dictionary representation of result
        """
        return {
            'success': self.success,
            'transaction_id': self.transaction_id,
            'transaction_state': self.transaction_state.to_dict() if self.transaction_state else None,
            'error_message': self.error_message,
            'gas_savings_achieved': float(self.gas_savings_achieved) if self.gas_savings_achieved else None,
            'was_retried': self.was_retried,
            'final_gas_price': float(self.final_gas_price) if self.final_gas_price else None,
        }


class CircuitBreakerState(Enum):
    """Circuit breaker state for failure protection."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class PerformanceMetrics:
    """Transaction manager performance metrics."""
    total_transactions: int = 0
    successful_transactions: int = 0
    failed_transactions: int = 0
    retried_transactions: int = 0
    replaced_transactions: int = 0
    gas_savings_total: Decimal = Decimal('0')
    average_execution_time_ms: float = 0.0
    success_rate_percent: float = 0.0
    retry_rate_percent: float = 0.0
    average_gas_savings_percent: float = 0.0
    
    def update_success_rate(self) -> None:
        """Update calculated success rate."""
        if self.total_transactions > 0:
            self.success_rate_percent = (
                self.successful_transactions / self.total_transactions * 100
            )
    
    def update_retry_rate(self) -> None:
        """Update calculated retry rate."""
        if self.total_transactions > 0:
            self.retry_rate_percent = (
                self.retried_transactions / self.total_transactions * 100
            )
    
    def update_average_gas_savings(self) -> None:
        """Update average gas savings."""
        if self.successful_transactions > 0:
            self.average_gas_savings_percent = float(
                self.gas_savings_total / self.successful_transactions
            )
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert metrics to dictionary.
        
        Returns:
            Dictionary representation of metrics
        """
        self.update_success_rate()
        self.update_retry_rate()
        self.update_average_gas_savings()
        
        return {
            'total_transactions': self.total_transactions,
            'successful_transactions': self.successful_transactions,
            'failed_transactions': self.failed_transactions,
            'retried_transactions': self.retried_transactions,
            'replaced_transactions': self.replaced_transactions,
            'gas_savings_total': float(self.gas_savings_total),
            'average_execution_time_ms': round(self.average_execution_time_ms, 2),
            'success_rate_percent': round(self.success_rate_percent, 2),
            'retry_rate_percent': round(self.retry_rate_percent, 2),
            'average_gas_savings_percent': round(self.average_gas_savings_percent, 2),
        }


class ErrorClassification(Enum):
    """Classification of transaction errors for retry logic."""
    OUT_OF_GAS = "out_of_gas"
    NONCE_ERROR = "nonce_error"
    CONTRACT_REVERT = "contract_revert"
    NETWORK_ERROR = "network_error"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    GAS_TOO_LOW = "gas_too_low"
    UNKNOWN = "unknown"


def classify_error(error_message: str) -> ErrorClassification:
    """
    Classify an error message for retry decision logic.
    
    Args:
        error_message: Error message to classify
        
    Returns:
        Error classification
    """
    if not error_message:
        return ErrorClassification.UNKNOWN
    
    error_lower = error_message.lower()
    
    if "out of gas" in error_lower:
        return ErrorClassification.OUT_OF_GAS
    elif "nonce" in error_lower:
        return ErrorClassification.NONCE_ERROR
    elif any(term in error_lower for term in ["revert", "require", "assert"]):
        return ErrorClassification.CONTRACT_REVERT
    elif any(term in error_lower for term in ["timeout", "connection", "network"]):
        return ErrorClassification.NETWORK_ERROR
    elif "insufficient" in error_lower:
        return ErrorClassification.INSUFFICIENT_FUNDS
    elif "gas" in error_lower and "low" in error_lower:
        return ErrorClassification.GAS_TOO_LOW
    else:
        return ErrorClassification.UNKNOWN


# Utility functions for gas calculations
def calculate_gas_escalation(
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
    escalation_multiplier = Decimal('1') + (escalation_percent / Decimal('100'))
    new_gas_price = original_gas_price * (escalation_multiplier ** retry_count)
    
    logger.debug(
        f"Gas escalation: Original={original_gas_price:.2f}, "
        f"Retry={retry_count}, New={new_gas_price:.2f} gwei"
    )
    
    return new_gas_price


def calculate_retry_backoff(
    retry_count: int,
    initial_backoff: float,
    max_backoff: float,
    multiplier: float = 2.0
) -> float:
    """
    Calculate exponential backoff delay with jitter.
    
    Args:
        retry_count: Current retry attempt number
        initial_backoff: Initial backoff in seconds
        max_backoff: Maximum backoff in seconds
        multiplier: Backoff multiplier
        
    Returns:
        Delay in seconds before retry
    """
    import random
    
    # Exponential backoff
    base_delay = initial_backoff * (multiplier ** (retry_count - 1))
    delay = min(base_delay, max_backoff)
    
    # Add jitter (±10%) to prevent thundering herd
    jitter = delay * 0.1 * (2 * random.random() - 1)
    final_delay = delay + jitter
    
    logger.debug(f"Backoff calculation: Retry={retry_count}, Delay={final_delay:.1f}s")
    
    return final_delay