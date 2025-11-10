"""
DCA Strategy - Dollar Cost Averaging Implementation

Automatically splits large purchases into smaller recurring buys over time.
This reduces timing risk and achieves better average entry prices.

Example: Instead of buying $1,000 of ETH at once, buy $100 every day for 10 days.

Phase 7B - Day 2: DCA Strategy

File: dexproject/paper_trading/strategies/dca_strategy.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import timedelta
from django.utils import timezone

from paper_trading.strategies.base_strategy import BaseStrategy
from paper_trading.constants import (
    StrategyType,
    StrategyStatus,
    OrderType,
    OrderStatus,
)


logger = logging.getLogger(__name__)


# =============================================================================
# DCA STRATEGY IMPLEMENTATION
# =============================================================================

class DCAStrategy(BaseStrategy):
    """
    Dollar Cost Averaging (DCA) Strategy.
    
    Splits a total investment amount into equal-sized purchases executed
    at regular intervals over time. This approach reduces the impact of
    volatility and timing risk.
    
    Configuration Parameters:
    - total_amount_usd (Decimal): Total amount to invest (required)
    - interval_hours (int): Hours between each buy (1-168, required)
    - num_intervals (int): Number of buy intervals (2-100, required)
    - token_address (str): Token contract address (required)
    - token_symbol (str): Token symbol for display (required)
    
    Execution Logic:
    1. Calculate amount per interval (total / num_intervals)
    2. Schedule first buy immediately
    3. Schedule remaining buys at specified intervals
    4. Track completion progress and average entry price
    5. Update performance metrics after each execution
    
    Example Configuration:
        {
            'total_amount_usd': '1000.00',
            'interval_hours': 24,
            'num_intervals': 10,
            'token_address': '0x...',
            'token_symbol': 'ETH',
        }
        
        This creates 10 buys of $100 each, spaced 24 hours apart.
    """
    
    def __init__(self, strategy_run: 'StrategyRun') -> None:
        """
        Initialize DCA strategy.
        
        Args:
            strategy_run: StrategyRun model instance
        """
        super().__init__(strategy_run)
        
        # Parse configuration
        self.total_amount_usd: Decimal = Decimal('0')
        self.interval_hours: int = 0
        self.num_intervals: int = 0
        self.token_address: str = ''
        self.token_symbol: str = ''
        self.amount_per_interval: Decimal = Decimal('0')
        
        if self.config:
            self._parse_config()
    
    def _parse_config(self) -> None:
        """Parse and store configuration parameters."""
        try:
            self.total_amount_usd = Decimal(str(self.config.get('total_amount_usd', '0')))
            self.interval_hours = int(self.config.get('interval_hours', 0))
            self.num_intervals = int(self.config.get('num_intervals', 0))
            self.token_address = str(self.config.get('token_address', ''))
            self.token_symbol = str(self.config.get('token_symbol', ''))
            
            # Calculate amount per interval
            if self.num_intervals > 0:
                self.amount_per_interval = self.total_amount_usd / Decimal(str(self.num_intervals))
            
            logger.debug(
                f"DCA config parsed: ${self.total_amount_usd} split into "
                f"{self.num_intervals} buys of ${self.amount_per_interval} each, "
                f"every {self.interval_hours}h"
            )
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Error parsing DCA config: {e}")
            raise ValueError(f"Invalid DCA configuration: {e}")
    
    # =========================================================================
    # ABSTRACT METHOD IMPLEMENTATIONS
    # =========================================================================
    
    def validate_config(self) -> tuple[bool, Optional[str]]:
        """
        Validate DCA strategy configuration.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check required fields
        required_fields = ['total_amount_usd', 'interval_hours', 'num_intervals', 'token_address', 'token_symbol']
        for field in required_fields:
            if field not in self.config:
                return False, f"Missing required field: {field}"
        
        # Validate total amount
        if self.total_amount_usd <= 0:
            return False, "total_amount_usd must be greater than 0"
        
        if self.total_amount_usd > Decimal('100000.00'):
            return False, "total_amount_usd cannot exceed $100,000"
        
        # Validate interval hours (1 hour to 1 week)
        if not (1 <= self.interval_hours <= 168):
            return False, "interval_hours must be between 1 and 168 (1 week)"
        
        # Validate number of intervals
        if not (2 <= self.num_intervals <= 100):
            return False, "num_intervals must be between 2 and 100"
        
        # Validate token address format
        if not self.token_address.startswith('0x') or len(self.token_address) != 42:
            return False, "Invalid token address format"
        
        # Validate token symbol
        if not self.token_symbol or len(self.token_symbol) > 20:
            return False, "token_symbol must be 1-20 characters"
        
        # Validate amount per interval is reasonable
        if self.amount_per_interval < Decimal('1.00'):
            return False, "Amount per interval must be at least $1.00"
        
        # Check account has sufficient balance
        account_balance = self.strategy_run.account.current_balance_usd
        if account_balance < self.total_amount_usd:
            return False, f"Insufficient balance: ${account_balance} < ${self.total_amount_usd}"
        
        return True, None
    
    async def execute(self) -> bool:
        """
        Execute DCA strategy.
        
        Steps:
        1. Validate configuration
        2. Update status to RUNNING
        3. Schedule first buy immediately
        4. Schedule remaining buys at intervals
        5. Return success
        
        Returns:
            True if execution started successfully
        """
        try:
            # Validate configuration
            is_valid, error = self.validate_config()
            if not is_valid:
                self._mark_failed(f"Configuration validation failed: {error}")
                return False
            
            # Check if we can execute
            can_execute, error = self._can_execute()
            if not can_execute:
                self._mark_failed(f"Cannot execute: {error}")
                return False
            
            # Update status to RUNNING
            self._update_status(StrategyStatus.RUNNING)
            
            # Update total_orders if not set
            if self.strategy_run.total_orders == 0:
                self.strategy_run.total_orders = self.num_intervals
                self.strategy_run.save()
            
            # Schedule first buy immediately
            logger.info(
                f"Starting DCA strategy {self.strategy_run.strategy_id}: "
                f"{self.num_intervals} buys of ${self.amount_per_interval} "
                f"every {self.interval_hours}h"
            )
            
            # Import and schedule Celery task
            from paper_trading.tasks.strategy_execution import execute_dca_interval
            
            # Schedule first interval immediately
            execute_dca_interval.apply_async(
                args=[str(self.strategy_run.strategy_id), 1],
                countdown=5,  # Start in 5 seconds
            )
            
            self._update_progress(
                Decimal('0.00'),
                f"Scheduled interval 1 of {self.num_intervals}"
            )
            
            logger.info(f"DCA strategy {self.strategy_run.strategy_id} execution started")
            return True
            
        except Exception as e:
            logger.exception(f"Error executing DCA strategy: {e}")
            self._mark_failed(f"Execution error: {str(e)}")
            return False
    
    async def pause(self) -> bool:
        """
        Pause DCA strategy execution.
        
        Stops scheduling new orders but allows current orders to complete.
        
        Returns:
            True if paused successfully
        """
        # Check if we can pause
        can_pause, error = self._can_pause()
        if not can_pause:
            logger.warning(f"Cannot pause DCA strategy: {error}")
            return False
        
        # Update status
        self._update_status(StrategyStatus.PAUSED)
        
        logger.info(f"DCA strategy {self.strategy_run.strategy_id} paused")
        return True
    
    async def resume(self) -> bool:
        """
        Resume paused DCA strategy.
        
        Resumes scheduling remaining buy intervals.
        
        Returns:
            True if resumed successfully
        """
        # Check if we can resume
        can_resume, error = self._can_resume()
        if not can_resume:
            logger.warning(f"Cannot resume DCA strategy: {error}")
            return False
        
        # Update status
        self._update_status(StrategyStatus.RUNNING)
        
        # Schedule next interval
        next_interval = self.strategy_run.completed_orders + 1
        
        if next_interval <= self.num_intervals:
            from paper_trading.tasks.strategy_execution import execute_dca_interval
            
            execute_dca_interval.apply_async(
                args=[str(self.strategy_run.strategy_id), next_interval],
                countdown=5,
            )
            
            logger.info(
                f"DCA strategy {self.strategy_run.strategy_id} resumed, "
                f"scheduling interval {next_interval}"
            )
        
        return True
    
    async def cancel(self) -> bool:
        """
        Cancel DCA strategy execution.
        
        Cancels all pending orders and stops execution.
        
        Returns:
            True if cancelled successfully
        """
        # Check if we can cancel
        can_cancel, error = self._can_cancel()
        if not can_cancel:
            logger.warning(f"Cannot cancel DCA strategy: {error}")
            return False
        
        # Cancel all pending orders
        from paper_trading.models import PaperOrder
        
        pending_orders = PaperOrder.objects.filter(
            strategy_links__strategy_run=self.strategy_run,
            status=OrderStatus.PENDING
        )
        
        cancelled_count = 0
        for order in pending_orders:
            order.status = OrderStatus.CANCELLED
            order.cancelled_at = timezone.now()
            order.save()
            cancelled_count += 1
        
        # Update status
        self._update_status(StrategyStatus.CANCELLED)
        
        logger.info(
            f"DCA strategy {self.strategy_run.strategy_id} cancelled, "
            f"{cancelled_count} pending orders cancelled"
        )
        return True
    
    def get_progress(self) -> Dict[str, Any]:
        """
        Get DCA execution progress.
        
        Returns:
            Dictionary with progress information
        """
        completed = self.strategy_run.completed_orders
        total = self.strategy_run.total_orders or self.num_intervals
        
        progress_percent = Decimal('0.00')
        if total > 0:
            progress_percent = (Decimal(str(completed)) / Decimal(str(total))) * Decimal('100')
        
        # Calculate estimated completion time
        estimated_completion = None
        if self.strategy_run.started_at and completed < total:
            remaining_intervals = total - completed
            time_per_interval = timedelta(hours=self.interval_hours)
            estimated_completion = timezone.now() + (time_per_interval * remaining_intervals)
        
        return {
            'progress_percent': progress_percent,
            'current_step': f"Interval {completed + 1} of {total}",
            'completed_orders': completed,
            'total_orders': total,
            'intervals_remaining': max(0, total - completed),
            'amount_per_interval': str(self.amount_per_interval),
            'total_invested': str(self.strategy_run.total_invested),
            'average_entry_price': str(self.strategy_run.average_entry),
            'estimated_completion': estimated_completion.isoformat() if estimated_completion else None,
        }
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"DCAStrategy(strategy_id={self.strategy_run.strategy_id}, "
            f"total=${self.total_amount_usd}, intervals={self.num_intervals}, "
            f"status={self.strategy_run.status})"
        )