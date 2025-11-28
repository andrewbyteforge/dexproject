"""
TWAP Strategy - Time-Weighted Average Price Implementation

Executes large orders by splitting them into equal-sized chunks executed at
regular time intervals. This minimizes market impact and avoids price manipulation
detection, especially useful for illiquid markets.

Example: Instead of buying $10,000 of a low-liquidity token at once (which could
spike the price 20%+), buy $1,250 every 30 minutes over 4 hours.

Phase 7B - Day 9: TWAP Strategy

File: dexproject/paper_trading/strategies/twap_strategy.py
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
    StrategySelectionThresholds,
    OrderType,
    OrderStatus,
)


logger = logging.getLogger(__name__)


# =============================================================================
# TWAP STRATEGY IMPLEMENTATION
# =============================================================================

class TWAPStrategy(BaseStrategy):
    """
    Time-Weighted Average Price (TWAP) Strategy.

    Executes large orders by dividing them into smaller equal-sized chunks
    executed at regular time intervals. Unlike DCA (which focuses on cost
    averaging over days/weeks), TWAP executes over hours to minimize market
    impact within a single trading session.

    Key Differences from DCA:
    - Shorter execution window (1-24 hours vs days/weeks)
    - Designed for illiquid markets (minimize price impact)
    - Equal time intervals (not volume-weighted like VWAP)
    - Focus on stealth execution rather than cost averaging

    Configuration Parameters:
    - total_amount_usd (Decimal): Total amount to invest (required)
    - execution_window_hours (int): Total hours to complete execution (1-24, required)
    - num_chunks (int): Number of equal-sized orders (3-24, required)
    - token_address (str): Token contract address (required)
    - token_symbol (str): Token symbol for display (required)
    - start_immediately (bool): Start first order now or wait (optional, default True)

    Execution Logic:
    1. Calculate chunk size (total / num_chunks)
    2. Calculate time interval (execution_window / num_chunks)
    3. Schedule orders at equal time intervals
    4. Execute each chunk at scheduled time
    5. Track progress and adjust if market conditions change
    6. Update performance metrics after completion

    Example Configuration:
        {
            'total_amount_usd': '10000.00',
            'execution_window_hours': 4,
            'num_chunks': 8,
            'token_address': '0x...',
            'token_symbol': 'PEPE',
            'start_immediately': True
        }

        This creates 8 buys of $1,250 each, spaced 30 minutes apart,
        completing in 4 hours total.

    Use Cases:
    - Large orders in illiquid tokens (< $500k liquidity)
    - Avoiding price impact and front-running
    - Institutional-style execution for retail traders
    - Accumulating positions without alerting market makers
    """

    def __init__(self, strategy_run: 'StrategyRun') -> None:
        """
        Initialize TWAP strategy.

        Args:
            strategy_run: StrategyRun model instance
        """
        super().__init__(strategy_run)

        # Parse configuration
        self.total_amount_usd: Decimal = Decimal('0')
        self.execution_window_hours: int = 0
        self.num_chunks: int = 0
        self.token_address: str = ''
        self.token_symbol: str = ''
        self.start_immediately: bool = True

        # Calculated values
        self.chunk_size_usd: Decimal = Decimal('0')
        self.interval_minutes: int = 0
        self.next_execution_time: Optional[Any] = None
        self.chunks_executed: int = 0

        if self.config:
            self._parse_config()

    def _parse_config(self) -> None:
        """Parse and store configuration parameters."""
        try:
            self.total_amount_usd = Decimal(str(self.config.get('total_amount_usd', '0')))
            self.execution_window_hours = int(self.config.get('execution_window_hours', 0))
            self.num_chunks = int(self.config.get('num_chunks', 0))
            self.token_address = str(self.config.get('token_address', ''))
            self.token_symbol = str(self.config.get('token_symbol', ''))
            self.start_immediately = bool(self.config.get('start_immediately', True))

            # Calculate chunk size
            if self.num_chunks > 0:
                self.chunk_size_usd = self.total_amount_usd / Decimal(str(self.num_chunks))

            # Calculate interval in minutes
            if self.num_chunks > 1:
                total_minutes = self.execution_window_hours * 60
                # Divide total time by (num_chunks - 1) because first executes immediately
                self.interval_minutes = int(total_minutes / (self.num_chunks - 1))
            else:
                self.interval_minutes = 0

            logger.debug(
                f"[TWAP] Config parsed: ${self.total_amount_usd} split into "
                f"{self.num_chunks} chunks of ${self.chunk_size_usd} each, "
                f"every {self.interval_minutes} minutes over {self.execution_window_hours}h"
            )
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"[TWAP] Error parsing config: {e}")
            raise ValueError(f"Invalid TWAP configuration: {e}")

    # =========================================================================
    # ABSTRACT METHOD IMPLEMENTATIONS (Required by BaseStrategy)
    # =========================================================================

    def validate_config(self) -> tuple[bool, Optional[str]]:
        """
        Validate TWAP strategy configuration.

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check required fields
        required_fields = [
            'total_amount_usd',
            'execution_window_hours',
            'num_chunks',
            'token_address',
            'token_symbol'
        ]
        for field in required_fields:
            if field not in self.config:
                return False, f"Missing required field: {field}"

        # Validate total amount - must be large (TWAP is for big orders)
        if self.total_amount_usd < StrategySelectionThresholds.TWAP_MIN_POSITION_SIZE_USD:
            return False, f"total_amount_usd must be >= ${StrategySelectionThresholds.TWAP_MIN_POSITION_SIZE_USD} for TWAP"

        if self.total_amount_usd > Decimal('1000000.00'):
            return False, "total_amount_usd cannot exceed $1,000,000"

        # Validate execution window (1 to 24 hours)
        min_hours = StrategySelectionThresholds.TWAP_MIN_EXECUTION_WINDOW_HOURS
        max_hours = StrategySelectionThresholds.TWAP_MAX_EXECUTION_WINDOW_HOURS

        if not (min_hours <= self.execution_window_hours <= max_hours):
            return False, f"execution_window_hours must be between {min_hours} and {max_hours}"

        # Validate number of chunks
        min_chunks = StrategySelectionThresholds.TWAP_MIN_CHUNKS
        max_chunks = StrategySelectionThresholds.TWAP_MAX_CHUNKS

        if not (min_chunks <= self.num_chunks <= max_chunks):
            return False, f"num_chunks must be between {min_chunks} and {max_chunks}"

        # Validate chunk size isn't too small
        min_chunk_size = Decimal('100.00')  # $100 minimum per chunk
        if self.chunk_size_usd < min_chunk_size:
            return False, f"Each chunk must be >= ${min_chunk_size} (reduce num_chunks)"

        # Validate interval isn't too short (prevents spam)
        min_interval_minutes = 5
        if self.interval_minutes > 0 and self.interval_minutes < min_interval_minutes:
            return False, f"Interval too short (minimum {min_interval_minutes} minutes)"

        # Validate token address format
        if not self.token_address.startswith('0x') or len(self.token_address) != 42:
            return False, "Invalid token address format"

        # Validate token symbol
        if not self.token_symbol or len(self.token_symbol) > 20:
            return False, "token_symbol must be 1-20 characters"

        return True, None

    def execute(self) -> bool:
        """
        Execute the TWAP strategy.

        This method:
        1. Validates configuration
        2. Updates status to RUNNING
        3. Schedules the first chunk via Celery task
        4. Returns success

        Returns:
            True if execution started successfully, False otherwise
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
                self.strategy_run.total_orders = self.num_chunks
                self.strategy_run.save()

            logger.info(
                f"[TWAP] Starting TWAP strategy {self.strategy_run.strategy_id}: "
                f"{self.num_chunks} chunks of ${self.chunk_size_usd} "
                f"every {self.interval_minutes} minutes over {self.execution_window_hours}h"
            )

            # Import and schedule Celery task for first chunk
            from paper_trading.tasks.strategy_execution import execute_twap_chunk

            # Schedule first chunk
            if self.start_immediately:
                # Execute first chunk in 5 seconds
                execute_twap_chunk.apply_async(
                    args=[str(self.strategy_run.strategy_id), 1],
                    countdown=5,
                )
                logger.info(f"[TWAP] Scheduled chunk 1 to execute in 5 seconds")
            else:
                # Execute first chunk after one interval
                execute_twap_chunk.apply_async(
                    args=[str(self.strategy_run.strategy_id), 1],
                    countdown=self.interval_minutes * 60,
                )
                logger.info(f"[TWAP] Scheduled chunk 1 to execute in {self.interval_minutes} minutes")

            self._update_progress(
                Decimal('0.00'),
                f"Scheduled chunk 1 of {self.num_chunks}"
            )

            logger.info(f"[TWAP] Strategy {self.strategy_run.strategy_id} execution started")
            return True

        except Exception as e:
            logger.exception(f"[TWAP] Error executing strategy: {e}")
            self._mark_failed(f"Execution error: {str(e)}")
            return False

    def pause(self) -> bool:
        """
        Pause TWAP strategy execution.

        Stops scheduling new chunks but allows current chunk to complete.
        Can be resumed later with resume().

        Returns:
            True if paused successfully, False otherwise
        """
        # Check if we can pause
        can_pause, error = self._can_pause()
        if not can_pause:
            logger.warning(f"[TWAP] Cannot pause strategy: {error}")
            return False

        # Update status to PAUSED
        self._update_status(StrategyStatus.PAUSED)

        # Note: Celery tasks check strategy status before executing,
        # so paused strategies will have their scheduled chunks skipped

        logger.info(
            f"[TWAP] Strategy {self.strategy_run.strategy_id} paused at "
            f"chunk {self.strategy_run.completed_orders}/{self.num_chunks}"
        )
        return True

    def resume(self) -> bool:
        """
        Resume paused TWAP strategy.

        Restarts execution from where it was paused by scheduling the next chunk.

        Returns:
            True if resumed successfully, False otherwise
        """
        # Check if we can resume
        can_resume, error = self._can_resume()
        if not can_resume:
            logger.warning(f"[TWAP] Cannot resume strategy: {error}")
            return False

        # Update status to RUNNING
        self._update_status(StrategyStatus.RUNNING)

        # Determine next chunk number
        next_chunk = self.strategy_run.completed_orders + 1

        if next_chunk > self.num_chunks:
            # All chunks already completed
            self._update_status(StrategyStatus.COMPLETED)
            logger.info(f"[TWAP] Strategy {self.strategy_run.strategy_id} already complete")
            return True

        # Schedule next chunk
        from paper_trading.tasks.strategy_execution import execute_twap_chunk

        execute_twap_chunk.apply_async(
            args=[str(self.strategy_run.strategy_id), next_chunk],
            countdown=10,  # Resume in 10 seconds
        )

        logger.info(
            f"[TWAP] Strategy {self.strategy_run.strategy_id} resumed, "
            f"scheduling chunk {next_chunk}/{self.num_chunks}"
        )
        return True

    def cancel(self) -> bool:
        """
        Cancel TWAP strategy execution.

        Stops all execution and marks strategy as CANCELLED.
        This action cannot be undone.

        Returns:
            True if cancelled successfully, False otherwise
        """
        # Check if we can cancel
        can_cancel, error = self._can_cancel()
        if not can_cancel:
            logger.warning(f"[TWAP] Cannot cancel strategy: {error}")
            return False

        # Update status to CANCELLED
        self._update_status(StrategyStatus.CANCELLED)

        # Note: Celery tasks check strategy status before executing,
        # so cancelled strategies will have their scheduled chunks skipped

        chunks_remaining = self.num_chunks - self.strategy_run.completed_orders

        logger.info(
            f"[TWAP] Strategy {self.strategy_run.strategy_id} cancelled. "
            f"Completed {self.strategy_run.completed_orders}/{self.num_chunks} chunks, "
            f"{chunks_remaining} chunks cancelled"
        )
        return True

    def get_progress(self) -> Dict[str, Any]:
        """
        Get current execution progress.

        Returns:
            Dictionary containing progress information
        """
        completed = self.strategy_run.completed_orders
        total = self.num_chunks if self.num_chunks > 0 else self.strategy_run.total_orders

        if total > 0:
            progress_percent = (completed / total) * 100
        else:
            progress_percent = 0

        # Calculate time remaining
        chunks_remaining = total - completed
        time_remaining_minutes = chunks_remaining * self.interval_minutes

        # Calculate estimated completion
        estimated_completion = None
        if chunks_remaining > 0 and self.interval_minutes > 0:
            estimated_completion = timezone.now() + timedelta(minutes=time_remaining_minutes)

        return {
            'progress_percent': round(progress_percent, 2),
            'current_step': f"Chunk {completed}/{total}",
            'completed_orders': completed,
            'total_orders': total,
            'chunks_remaining': chunks_remaining,
            'chunk_size_usd': float(self.chunk_size_usd),
            'interval_minutes': self.interval_minutes,
            'time_remaining_minutes': time_remaining_minutes,
            'estimated_completion': estimated_completion.isoformat() if estimated_completion else None,
            'token_symbol': self.token_symbol,
            'execution_window_hours': self.execution_window_hours,
        }

    # =========================================================================
    # TWAP-SPECIFIC METHODS
    # =========================================================================

    def calculate_next_execution(self) -> Optional[Any]:
        """
        Calculate when the next chunk should be executed.

        Returns:
            Datetime of next execution, or None if strategy is complete
        """
        # If all chunks executed, we're done
        if self.chunks_executed >= self.num_chunks:
            logger.info(f"[TWAP] All {self.num_chunks} chunks executed")
            return None

        # First chunk executes immediately if start_immediately is True
        if self.chunks_executed == 0 and self.start_immediately:
            next_time = timezone.now()
        else:
            # Subsequent chunks use the interval
            if self.strategy_run.started_at:
                base_time = self.strategy_run.started_at
            else:
                base_time = timezone.now()

            # Calculate next execution time
            minutes_elapsed = self.chunks_executed * self.interval_minutes
            next_time = base_time + timedelta(minutes=minutes_elapsed)

        self.next_execution_time = next_time

        logger.debug(
            f"[TWAP] Next chunk ({self.chunks_executed + 1}/{self.num_chunks}) "
            f"scheduled for {next_time}"
        )

        return next_time

    def execute_next_step(self) -> bool:
        """
        Execute the next chunk in the TWAP schedule.

        Returns:
            True if step executed successfully, False otherwise
        """
        try:
            # Check if we should execute now
            if self.next_execution_time and timezone.now() < self.next_execution_time:
                logger.debug(
                    f"[TWAP] Not time yet. Next execution at {self.next_execution_time}"
                )
                return False

            # Check if all chunks are done
            if self.chunks_executed >= self.num_chunks:
                logger.info(f"[TWAP] Strategy complete ({self.num_chunks} chunks executed)")
                return False

            # Execute the chunk
            chunk_number = self.chunks_executed + 1

            logger.info(
                f"[TWAP] Executing chunk {chunk_number}/{self.num_chunks}: "
                f"${self.chunk_size_usd} of {self.token_symbol}"
            )

            # Create the trade (this will be handled by the executor/trade_executor)
            # For now, we just log and update our tracking
            success = self._execute_chunk_order(chunk_number)

            if success:
                self.chunks_executed += 1

                # Update strategy run progress
                self.update_progress(
                    completed_orders=self.chunks_executed,
                    current_step=f"Chunk {self.chunks_executed}/{self.num_chunks}"
                )

                # Calculate next execution time
                self.calculate_next_execution()

                logger.info(
                    f"[TWAP] Chunk {chunk_number} executed successfully. "
                    f"Progress: {self.chunks_executed}/{self.num_chunks}"
                )

                return True
            else:
                logger.error(f"[TWAP] Failed to execute chunk {chunk_number}")
                return False

        except Exception as e:
            logger.error(f"[TWAP] Error executing next step: {e}", exc_info=True)
            return False

    def _execute_chunk_order(self, chunk_number: int) -> bool:
        """
        Execute a single chunk order.

        Args:
            chunk_number: Which chunk this is (1-indexed)

        Returns:
            True if order executed, False otherwise
        """
        try:
            # Import here to avoid circular dependencies
            from paper_trading.intelligence.core.base import TradingDecision

            # Create a simple BUY decision for this chunk
            decision = TradingDecision(
                action='BUY',
                token_address=self.token_address,
                token_symbol=self.token_symbol,
                position_size_percent=Decimal('0'),
                position_size_usd=self.chunk_size_usd,
                stop_loss_percent=Decimal('0'),
                take_profit_targets=[],
                execution_mode='TWAP',
                use_private_relay=False,
                gas_strategy='standard',
                max_gas_price_gwei=Decimal('50'),
                overall_confidence=Decimal('100'),  # TWAP chunks are pre-approved
                risk_score=Decimal('0'),
                opportunity_score=Decimal('100'),
                primary_reasoning=f"TWAP chunk {chunk_number}/{self.num_chunks}",
                risk_factors=[],
                opportunity_factors=[f"TWAP execution chunk {chunk_number}"],
                mitigation_strategies=[],
                intel_level_used=5,
                intel_adjustments={},
                time_sensitivity='low',
                max_execution_time_ms=60000  # 1 minute max
            )

            # Log the chunk execution
            logger.info(
                f"[TWAP] Created BUY decision for chunk {chunk_number}: "
                f"${self.chunk_size_usd} of {self.token_symbol}"
            )

            # Note: Actual execution will be handled by the strategy executor
            # which will call trade_executor.execute_trade()
            # For now, we consider this successful

            return True

        except Exception as e:
            logger.error(
                f"[TWAP] Error creating chunk order {chunk_number}: {e}",
                exc_info=True
            )
            return False

    def update_progress(
        self,
        completed_orders: int,
        current_step: str
    ) -> None:
        """
        Update strategy progress in the database.

        Args:
            completed_orders: Number of completed orders
            current_step: Description of current step
        """
        try:
            progress_percent = Decimal(str(completed_orders / self.num_chunks * 100))

            self.strategy_run.completed_orders = completed_orders
            self.strategy_run.progress_percent = progress_percent
            self.strategy_run.current_step = current_step
            self.strategy_run.total_invested = self.chunk_size_usd * Decimal(str(completed_orders))
            self.strategy_run.save()

            logger.debug(
                f"[TWAP] Progress updated: {completed_orders}/{self.num_chunks} "
                f"({float(progress_percent):.1f}%)"
            )
        except Exception as e:
            logger.error(f"[TWAP] Error updating progress: {e}")

    def should_continue(self) -> bool:
        """
        Determine if the strategy should continue executing.

        Returns:
            True if strategy should continue, False if it should stop
        """
        # Stop if all chunks executed
        if self.chunks_executed >= self.num_chunks:
            return False

        # Stop if strategy is paused or cancelled
        if self.strategy_run.status in [StrategyStatus.PAUSED, StrategyStatus.CANCELLED]:
            return False

        # Stop if execution window has expired (with 10% grace period)
        if self.strategy_run.started_at:
            elapsed_hours = (timezone.now() - self.strategy_run.started_at).total_seconds() / 3600
            max_hours = self.execution_window_hours * 1.1  # 10% grace

            if elapsed_hours > max_hours:
                logger.warning(
                    f"[TWAP] Execution window exceeded: {elapsed_hours:.1f}h / {self.execution_window_hours}h"
                )
                return False

        # Continue if we still have chunks to execute
        return True

    def get_progress_summary(self) -> Dict[str, Any]:
        """
        Get current progress summary (detailed version).

        Returns:
            Dictionary with progress metrics
        """
        progress_percent = (self.chunks_executed / self.num_chunks * 100) if self.num_chunks > 0 else 0

        # Calculate time remaining
        time_remaining_minutes = (self.num_chunks - self.chunks_executed) * self.interval_minutes

        # Calculate average execution time per chunk
        if self.strategy_run.started_at and self.chunks_executed > 0:
            elapsed_seconds = (timezone.now() - self.strategy_run.started_at).total_seconds()
            avg_seconds_per_chunk = elapsed_seconds / self.chunks_executed
        else:
            avg_seconds_per_chunk = 0

        return {
            'strategy_type': 'TWAP',
            'total_chunks': self.num_chunks,
            'chunks_executed': self.chunks_executed,
            'chunks_remaining': self.num_chunks - self.chunks_executed,
            'progress_percent': round(progress_percent, 2),
            'chunk_size_usd': float(self.chunk_size_usd),
            'total_amount_usd': float(self.total_amount_usd),
            'amount_executed_usd': float(self.chunk_size_usd * self.chunks_executed),
            'amount_remaining_usd': float(self.chunk_size_usd * (self.num_chunks - self.chunks_executed)),
            'interval_minutes': self.interval_minutes,
            'execution_window_hours': self.execution_window_hours,
            'time_remaining_minutes': time_remaining_minutes,
            'avg_seconds_per_chunk': round(avg_seconds_per_chunk, 2),
            'next_execution_time': self.next_execution_time.isoformat() if self.next_execution_time else None,
            'token_symbol': self.token_symbol,
            'token_address': self.token_address,
        }

    def adjust_schedule(self, market_conditions: Dict[str, Any]) -> bool:
        """
        Adjust TWAP schedule based on changing market conditions.

        This method can pause, speed up, or slow down execution based on:
        - Sudden volatility spikes (pause and wait)
        - Liquidity changes (adjust chunk size)
        - Price movement (adjust timing)

        Args:
            market_conditions: Dictionary with current market data

        Returns:
            True if schedule was adjusted, False if no changes made
        """
        try:
            volatility = Decimal(str(market_conditions.get('volatility', 0)))
            liquidity = Decimal(str(market_conditions.get('liquidity_usd', 0)))

            # Check if volatility is too high (pause until it calms down)
            if volatility > StrategySelectionThresholds.TWAP_MAX_VOLATILITY:
                logger.warning(
                    f"[TWAP] High volatility detected ({float(volatility):.2%}), "
                    f"pausing execution"
                )
                # Add delay to next execution
                if self.next_execution_time:
                    self.next_execution_time += timedelta(minutes=15)
                return True

            # Check if liquidity dropped significantly (increase interval)
            min_liquidity = StrategySelectionThresholds.TWAP_MAX_LIQUIDITY_USD
            if liquidity < min_liquidity * Decimal('0.5'):  # 50% drop
                logger.warning(
                    f"[TWAP] Low liquidity detected (${float(liquidity):,.0f}), "
                    f"extending interval"
                )
                # Increase interval by 50%
                self.interval_minutes = int(self.interval_minutes * 1.5)
                return True

            return False

        except Exception as e:
            logger.error(f"[TWAP] Error adjusting schedule: {e}")
            return False


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_twap_strategy(
    account: 'PaperTradingAccount',
    token_address: str,
    token_symbol: str,
    total_amount_usd: Decimal,
    execution_window_hours: int = None,
    num_chunks: int = None
) -> 'StrategyRun':
    """
    Helper function to create a TWAP strategy with sensible defaults.

    Args:
        account: Paper trading account
        token_address: Token contract address
        token_symbol: Token symbol
        total_amount_usd: Total amount to invest
        execution_window_hours: Hours to complete (default: 4)
        num_chunks: Number of chunks (default: 8)

    Returns:
        Created StrategyRun instance
    """
    from paper_trading.models import StrategyRun

    # Use defaults from constants
    if execution_window_hours is None:
        execution_window_hours = StrategySelectionThresholds.TWAP_DEFAULT_EXECUTION_WINDOW_HOURS

    if num_chunks is None:
        num_chunks = StrategySelectionThresholds.TWAP_DEFAULT_CHUNKS

    config = {
        'token_address': token_address,
        'token_symbol': token_symbol,
        'total_amount_usd': str(total_amount_usd),
        'execution_window_hours': execution_window_hours,
        'num_chunks': num_chunks,
        'start_immediately': True
    }

    strategy_run = StrategyRun.objects.create(
        account=account,
        strategy_type=StrategyType.TWAP,
        config=config,
        total_orders=num_chunks,
        status=StrategyStatus.PENDING
    )

    logger.info(
        f"[TWAP] Created strategy {strategy_run.strategy_id} for {token_symbol}: "
        f"${total_amount_usd} over {execution_window_hours}h in {num_chunks} chunks"
    )

    return strategy_run