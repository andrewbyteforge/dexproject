"""
Base Strategy - Abstract Base Class for Trading Strategies

This module provides the foundation for all automated trading strategies.
All strategy implementations (DCA, Grid, TWAP, VWAP, Custom) must inherit from
BaseStrategy and implement the required abstract methods.

Phase 7B - Advanced Strategies

File: dexproject/paper_trading/strategies/base_strategy.py
"""

import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Any, Optional
from django.utils import timezone

from paper_trading.constants import (
    StrategyType,
    StrategyStatus,
    StrategyRunFields,
    validate_strategy_type,
    validate_strategy_status,
)


logger = logging.getLogger(__name__)


# =============================================================================
# BASE STRATEGY - Abstract Class
# =============================================================================

class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    All strategies must implement:
    - validate_config() - Validate strategy configuration
    - execute() - Execute the strategy
    - pause() - Pause strategy execution
    - resume() - Resume paused strategy
    - cancel() - Cancel strategy execution
    - get_progress() - Get execution progress
    
    Attributes:
        strategy_run: StrategyRun model instance
        config: Strategy configuration dictionary
        strategy_type: Type of strategy (DCA, GRID, etc.)
    
    Example:
        class DCAStrategy(BaseStrategy):
            def validate_config(self) -> tuple[bool, Optional[str]]:
                # Validate DCA-specific config
                return True, None
            
            async def execute(self) -> bool:
                # Execute DCA strategy
                return True
    """
    
    def __init__(self, strategy_run: 'StrategyRun') -> None:
        """
        Initialize base strategy.
        
        Args:
            strategy_run: StrategyRun model instance containing configuration
            
        Raises:
            ValueError: If strategy_run is None or invalid
        """
        if strategy_run is None:
            raise ValueError("strategy_run cannot be None")
        
        self.strategy_run = strategy_run
        self.config: Dict[str, Any] = strategy_run.config or {}
        self.strategy_type: str = strategy_run.strategy_type
        
        logger.info(
            f"Initialized {self.__class__.__name__} for strategy_id={strategy_run.strategy_id}"
        )
    
    # =========================================================================
    # ABSTRACT METHODS - Must be implemented by subclasses
    # =========================================================================
    
    @abstractmethod
    def validate_config(self) -> tuple[bool, Optional[str]]:
        """
        Validate strategy configuration.
        
        Each strategy must implement its own validation logic to ensure
        all required configuration parameters are present and valid.
        
        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if configuration is valid
            - error_message: Error description if invalid, None if valid
        
        Example:
            def validate_config(self) -> tuple[bool, Optional[str]]:
                if 'total_amount_usd' not in self.config:
                    return False, "Missing required field: total_amount_usd"
                
                amount = Decimal(str(self.config['total_amount_usd']))
                if amount <= 0:
                    return False, "total_amount_usd must be positive"
                
                return True, None
        """
        pass
    
    @abstractmethod
    def execute(self) -> bool:
        """
        Execute the trading strategy.
        
        This is the main entry point for strategy execution. It should:
        1. Validate configuration
        2. Update strategy status to RUNNING
        3. Execute strategy logic (place orders, schedule tasks, etc.)
        4. Handle errors gracefully
        5. Update strategy status on completion
        
        Returns:
            True if execution started successfully, False otherwise
        
        Example:
            async def execute(self) -> bool:
                try:
                    # Validate config
                    is_valid, error = self.validate_config()
                    if not is_valid:
                        self._mark_failed(error)
                        return False
                    
                    # Update status
                    self._update_status(StrategyStatus.RUNNING)
                    
                    # Execute strategy logic
                    await self._schedule_first_order()
                    
                    return True
                except Exception as e:
                    self._mark_failed(str(e))
                    return False
        """
        pass
    
    @abstractmethod
    def pause(self) -> bool:
        """
        Pause strategy execution.
        
        Pausing should:
        1. Stop scheduling new orders
        2. Allow current orders to complete
        3. Update status to PAUSED
        4. Record pause timestamp
        
        Returns:
            True if paused successfully, False otherwise
        
        Example:
            async def pause(self) -> bool:
                if self.strategy_run.status != StrategyStatus.RUNNING:
                    return False
                
                self.strategy_run.status = StrategyStatus.PAUSED
                self.strategy_run.paused_at = timezone.now()
                self.strategy_run.save()
                
                return True
        """
        pass
    
    @abstractmethod
    def resume(self) -> bool:
        """
        Resume paused strategy execution.
        
        Resuming should:
        1. Validate strategy can be resumed
        2. Update status to RUNNING
        3. Clear pause timestamp
        4. Resume scheduling orders
        
        Returns:
            True if resumed successfully, False otherwise
        
        Example:
            async def resume(self) -> bool:
                if self.strategy_run.status != StrategyStatus.PAUSED:
                    return False
                
                self.strategy_run.status = StrategyStatus.RUNNING
                self.strategy_run.paused_at = None
                self.strategy_run.save()
                
                await self._schedule_next_order()
                return True
        """
        pass
    
    @abstractmethod
    def cancel(self) -> bool:
        """
        Cancel strategy execution.
        
        Cancelling should:
        1. Stop all pending orders
        2. Cancel scheduled tasks
        3. Update status to CANCELLED
        4. Record cancellation timestamp
        5. Clean up resources
        
        Returns:
            True if cancelled successfully, False otherwise
        
        Example:
            async def cancel(self) -> bool:
                # Cancel pending orders
                pending_orders = self.strategy_run.orders.filter(
                    status=OrderStatus.PENDING
                )
                for order in pending_orders:
                    order.status = OrderStatus.CANCELLED
                    order.save()
                
                # Update strategy status
                self.strategy_run.status = StrategyStatus.CANCELLED
                self.strategy_run.cancelled_at = timezone.now()
                self.strategy_run.save()
                
                return True
        """
        pass
    
    @abstractmethod
    def get_progress(self) -> Dict[str, Any]:
        """
        Get current execution progress.
        
        Returns:
            Dictionary containing progress information:
            - progress_percent: Completion percentage (0-100)
            - current_step: Current execution step description
            - completed_orders: Number of completed orders
            - total_orders: Total number of orders planned
            - estimated_completion: Estimated completion datetime (optional)
        
        Example:
            def get_progress(self) -> Dict[str, Any]:
                completed = self.strategy_run.completed_orders
                total = self.strategy_run.total_orders
                
                return {
                    'progress_percent': (completed / total * 100) if total > 0 else 0,
                    'current_step': f"Order {completed + 1} of {total}",
                    'completed_orders': completed,
                    'total_orders': total,
                }
        """
        pass
    
    # =========================================================================
    # HELPER METHODS - Available to all subclasses
    # =========================================================================
    
    def _update_status(self, new_status: str) -> None:
        """
        Update strategy status with validation.
        
        Args:
            new_status: New status value (must be valid StrategyStatus)
            
        Raises:
            ValueError: If status is invalid
        """
        if not validate_strategy_status(new_status):
            raise ValueError(f"Invalid strategy status: {new_status}")
        
        old_status = self.strategy_run.status
        self.strategy_run.status = new_status
        
        # Update timestamps based on status
        if new_status == StrategyStatus.RUNNING and old_status == StrategyStatus.PENDING:
            self.strategy_run.started_at = timezone.now()
        elif new_status == StrategyStatus.PAUSED:
            self.strategy_run.paused_at = timezone.now()
        elif new_status == StrategyStatus.COMPLETED:
            self.strategy_run.completed_at = timezone.now()
        elif new_status == StrategyStatus.CANCELLED:
            self.strategy_run.cancelled_at = timezone.now()
        
        self.strategy_run.save()
        
        logger.info(
            f"Strategy {self.strategy_run.strategy_id} status: {old_status} → {new_status}"
        )
    
    def _mark_failed(self, error_message: str) -> None:
        """
        Mark strategy as failed with error message.
        
        Args:
            error_message: Description of the failure
        """
        self.strategy_run.status = StrategyStatus.FAILED
        self.strategy_run.error_message = error_message
        self.strategy_run.save()
        
        logger.error(
            f"Strategy {self.strategy_run.strategy_id} failed: {error_message}"
        )
    
    def _update_progress(self, progress_percent: Decimal, current_step: str) -> None:
        """
        Update strategy execution progress.
        
        Args:
            progress_percent: Completion percentage (0-100)
            current_step: Description of current step
        """
        self.strategy_run.progress_percent = progress_percent
        self.strategy_run.current_step = current_step
        self.strategy_run.save()
        
        logger.debug(
            f"Strategy {self.strategy_run.strategy_id} progress: "
            f"{progress_percent}% - {current_step}"
        )
    
    def _can_execute(self) -> tuple[bool, Optional[str]]:
        """
        Check if strategy can be executed.
        
        Returns:
            Tuple of (can_execute, error_message)
        """
        # Check status
        if self.strategy_run.status not in [StrategyStatus.PENDING]:
            return False, f"Cannot execute strategy in {self.strategy_run.status} status"
        
        # Validate account
        if not self.strategy_run.account:
            return False, "Strategy has no associated account"
        
        # Validate configuration
        is_valid, error = self.validate_config()
        if not is_valid:
            return False, f"Invalid configuration: {error}"
        
        return True, None
    
    def _can_pause(self) -> tuple[bool, Optional[str]]:
        """
        Check if strategy can be paused.
        
        Returns:
            Tuple of (can_pause, error_message)
        """
        if self.strategy_run.status != StrategyStatus.RUNNING:
            return False, f"Cannot pause strategy in {self.strategy_run.status} status"
        
        return True, None
    
    def _can_resume(self) -> tuple[bool, Optional[str]]:
        """
        Check if strategy can be resumed.
        
        Returns:
            Tuple of (can_resume, error_message)
        """
        if self.strategy_run.status != StrategyStatus.PAUSED:
            return False, f"Cannot resume strategy in {self.strategy_run.status} status"
        
        return True, None
    
    def _can_cancel(self) -> tuple[bool, Optional[str]]:
        """
        Check if strategy can be cancelled.
        
        Returns:
            Tuple of (can_cancel, error_message)
        """
        # Can cancel if running or paused
        if self.strategy_run.status not in [StrategyStatus.RUNNING, StrategyStatus.PAUSED, StrategyStatus.PENDING]:
            return False, f"Cannot cancel strategy in {self.strategy_run.status} status"
        
        return True, None
    
    def __repr__(self) -> str:
        """String representation of strategy."""
        return (
            f"{self.__class__.__name__}("
            f"strategy_id={self.strategy_run.strategy_id}, "
            f"type={self.strategy_type}, "
            f"status={self.strategy_run.status})"
        )