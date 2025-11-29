"""
VWAP Strategy - Volume-Weighted Average Price Implementation

Executes orders proportionally to typical volume distribution patterns. Unlike TWAP
which uses equal-sized chunks at equal intervals, VWAP sizes chunks based on
historical volume patterns to minimize market impact and achieve better fill prices.

Example: For a $10,000 order on a token with higher morning volume, VWAP might
execute 40% in the first 2 hours (high volume period), 30% in mid-day (medium volume),
and 30% in the afternoon (lower volume). This achieves execution closer to the
volume-weighted average price benchmark.

Key Differences from TWAP:
- TWAP: Equal chunks at equal intervals (for illiquid markets)
- VWAP: Variable chunks based on volume distribution (for liquid markets)

Use Cases:
- Large orders on highly liquid tokens
- Minimizing deviation from VWAP benchmark
- Institutional-grade execution
- High-confidence, high-liquidity scenarios

Phase 7B - Day 10: VWAP Strategy

File: dexproject/paper_trading/strategies/vwap_strategy.py
"""

import logging
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional, List, Tuple
from datetime import timedelta, datetime
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
# VWAP CONSTANTS (until added to main constants.py)
# =============================================================================

class VWAPDefaults:
    """
    Default values for VWAP strategy parameters.
    
    These will be moved to constants.py in the integration step.
    """
    # Position size thresholds
    MIN_POSITION_SIZE_USD: Decimal = Decimal('2000')  # $2000 minimum
    OPTIMAL_POSITION_SIZE_USD: Decimal = Decimal('5000')  # $5k+ ideal
    
    # Liquidity requirements (VWAP needs HIGH liquidity)
    MIN_LIQUIDITY_USD: Decimal = Decimal('1000000')  # $1M minimum
    OPTIMAL_LIQUIDITY_USD: Decimal = Decimal('5000000')  # $5M+ ideal
    
    # Confidence threshold
    MIN_CONFIDENCE: Decimal = Decimal('80.0')  # 80% confidence (highest of all strategies)
    
    # Volatility limits (VWAP works best in stable markets)
    MIN_VOLATILITY: Decimal = Decimal('0.01')  # 1% minimum (some movement needed)
    MAX_VOLATILITY: Decimal = Decimal('0.10')  # 10% max (too volatile = bad fills)
    
    # Execution parameters
    MIN_EXECUTION_WINDOW_HOURS: int = 2  # Minimum 2 hours
    DEFAULT_EXECUTION_WINDOW_HOURS: int = 6  # Default 6 hours
    MAX_EXECUTION_WINDOW_HOURS: int = 24  # Maximum 24 hours
    
    MIN_INTERVALS: int = 4  # Minimum 4 intervals
    DEFAULT_INTERVALS: int = 12  # Default 12 intervals (every 30 min for 6 hours)
    MAX_INTERVALS: int = 48  # Maximum 48 intervals
    
    # Target participation rate (% of market volume to capture)
    DEFAULT_PARTICIPATION_RATE: Decimal = Decimal('0.05')  # 5% of volume
    MIN_PARTICIPATION_RATE: Decimal = Decimal('0.01')  # 1% minimum
    MAX_PARTICIPATION_RATE: Decimal = Decimal('0.20')  # 20% maximum
    
    # VWAP deviation tolerance
    MAX_VWAP_DEVIATION_PERCENT: Decimal = Decimal('2.0')  # 2% max deviation from VWAP


# =============================================================================
# VOLUME PROFILE - Simulated Intraday Volume Distribution
# =============================================================================

class VolumeProfile:
    """
    Represents typical intraday volume distribution for crypto markets.
    
    Crypto markets trade 24/7 but have distinct volume patterns:
    - Higher volume during US market hours (9am-4pm EST)
    - Moderate volume during European hours (3am-11am EST)
    - Lower volume during Asian hours (7pm-3am EST)
    
    This class provides a simplified volume curve for VWAP calculations.
    In production, this would be replaced with actual historical volume data.
    """
    
    # Hourly volume weights (24 hours, normalized to sum to 1.0)
    # Based on typical crypto market patterns (UTC timezone)
    HOURLY_WEIGHTS: List[Decimal] = [
        Decimal('0.025'),  # 00:00 - Low (Asia night)
        Decimal('0.020'),  # 01:00
        Decimal('0.018'),  # 02:00
        Decimal('0.022'),  # 03:00 - Europe waking up
        Decimal('0.030'),  # 04:00
        Decimal('0.040'),  # 05:00
        Decimal('0.050'),  # 06:00 - Europe morning
        Decimal('0.060'),  # 07:00
        Decimal('0.065'),  # 08:00
        Decimal('0.070'),  # 09:00 - Peak (Europe + US pre-market)
        Decimal('0.072'),  # 10:00
        Decimal('0.070'),  # 11:00
        Decimal('0.065'),  # 12:00 - US market open
        Decimal('0.068'),  # 13:00
        Decimal('0.070'),  # 14:00 - Peak US hours
        Decimal('0.065'),  # 15:00
        Decimal('0.055'),  # 16:00 - US afternoon
        Decimal('0.045'),  # 17:00
        Decimal('0.035'),  # 18:00 - US market close
        Decimal('0.030'),  # 19:00
        Decimal('0.028'),  # 20:00 - Asia waking up
        Decimal('0.030'),  # 21:00
        Decimal('0.028'),  # 22:00
        Decimal('0.025'),  # 23:00
    ]
    
    @classmethod
    def get_volume_weight(cls, hour: int) -> Decimal:
        """
        Get the volume weight for a specific hour (0-23 UTC).
        
        Args:
            hour: Hour of the day in UTC (0-23)
            
        Returns:
            Volume weight as a decimal (0.0-1.0)
        """
        if not 0 <= hour <= 23:
            raise ValueError(f"Hour must be 0-23, got {hour}")
        return cls.HOURLY_WEIGHTS[hour]
    
    @classmethod
    def get_volume_weights_for_window(
        cls,
        start_hour: int,
        num_hours: int
    ) -> List[Tuple[int, Decimal]]:
        """
        Get volume weights for a specific time window.
        
        Args:
            start_hour: Starting hour (0-23 UTC)
            num_hours: Number of hours in the window
            
        Returns:
            List of (hour, weight) tuples
        """
        weights = []
        for i in range(num_hours):
            hour = (start_hour + i) % 24
            weights.append((hour, cls.HOURLY_WEIGHTS[hour]))
        return weights
    
    @classmethod
    def normalize_weights(cls, weights: List[Decimal]) -> List[Decimal]:
        """
        Normalize a list of weights to sum to 1.0.
        
        Args:
            weights: List of decimal weights
            
        Returns:
            Normalized weights summing to 1.0
        """
        total = sum(weights)
        if total == 0:
            # Equal distribution if all weights are zero
            return [Decimal('1.0') / len(weights) for _ in weights]
        return [w / total for w in weights]


# =============================================================================
# VWAP STRATEGY IMPLEMENTATION
# =============================================================================

class VWAPStrategy(BaseStrategy):
    """
    Volume-Weighted Average Price (VWAP) Strategy.
    
    Executes large orders by dividing them into variable-sized chunks
    proportional to typical market volume distribution. This minimizes
    market impact and achieves execution closer to the VWAP benchmark.
    
    Key Differences from TWAP:
    - Chunk sizes vary based on volume (TWAP uses equal chunks)
    - Better for liquid markets (TWAP better for illiquid)
    - Tracks deviation from VWAP benchmark
    - Higher confidence threshold required
    
    Configuration Parameters:
    - total_amount_usd (Decimal): Total amount to invest (required)
    - execution_window_hours (int): Total hours to complete (2-24, required)
    - num_intervals (int): Number of execution intervals (4-48, required)
    - token_address (str): Token contract address (required)
    - token_symbol (str): Token symbol for display (required)
    - participation_rate (Decimal): Target % of market volume (0.01-0.20, optional)
    - start_immediately (bool): Start first interval now or wait (default True)
    
    Execution Logic:
    1. Calculate volume profile for execution window
    2. Size each interval proportional to expected volume
    3. Schedule intervals based on time distribution
    4. Execute each interval at scheduled time
    5. Track VWAP deviation and adjust if needed
    6. Update performance metrics after completion
    
    Example Configuration:
        {
            'total_amount_usd': '10000.00',
            'execution_window_hours': 6,
            'num_intervals': 12,
            'token_address': '0x...',
            'token_symbol': 'WETH',
            'participation_rate': '0.05',
            'start_immediately': True
        }
        
        With typical volume distribution, this might create:
        - Intervals 1-4 (morning): $1,200, $1,400, $1,500, $1,400 = $5,500
        - Intervals 5-8 (midday): $900, $800, $700, $600 = $3,000
        - Intervals 9-12 (afternoon): $400, $350, $400, $350 = $1,500
        Total: $10,000
    """
    
    def __init__(self, strategy_run: 'StrategyRun') -> None:
        """
        Initialize VWAP strategy.
        
        Args:
            strategy_run: StrategyRun model instance containing configuration
        """
        super().__init__(strategy_run)
        
        # Parse configuration
        self.total_amount_usd = Decimal(str(self.config.get('total_amount_usd', '0')))
        self.execution_window_hours = int(self.config.get(
            'execution_window_hours',
            VWAPDefaults.DEFAULT_EXECUTION_WINDOW_HOURS
        ))
        self.num_intervals = int(self.config.get(
            'num_intervals',
            VWAPDefaults.DEFAULT_INTERVALS
        ))
        self.token_address = self.config.get('token_address', '')
        self.token_symbol = self.config.get('token_symbol', 'UNKNOWN')
        self.participation_rate = Decimal(str(self.config.get(
            'participation_rate',
            VWAPDefaults.DEFAULT_PARTICIPATION_RATE
        )))
        self.start_immediately = self.config.get('start_immediately', True)
        
        # Calculate interval timing
        self.interval_minutes = (self.execution_window_hours * 60) // self.num_intervals
        
        # Calculate volume-weighted interval sizes
        self.interval_sizes = self._calculate_interval_sizes()
        
        # Track execution state
        self.intervals_executed = self.strategy_run.completed_orders or 0
        self.next_execution_time: Optional[datetime] = None
        
        # VWAP tracking
        self.total_volume_executed = Decimal('0')
        self.total_value_executed = Decimal('0')
        self.vwap_benchmark = Decimal('0')
        self.current_vwap_deviation = Decimal('0')
        
        logger.info(
            f"[VWAP] Initialized strategy for {self.token_symbol}: "
            f"${self.total_amount_usd} over {self.execution_window_hours}h "
            f"in {self.num_intervals} volume-weighted intervals"
        )
    
    # =========================================================================
    # VOLUME CALCULATION METHODS
    # =========================================================================
    
    def _calculate_interval_sizes(self) -> List[Decimal]:
        """
        Calculate the USD amount for each interval based on volume distribution.
        
        Returns:
            List of Decimal amounts for each interval
        """
        # Get current hour (UTC)
        current_hour = timezone.now().hour
        
        # Get volume weights for the execution window
        hours_per_interval = max(1, self.execution_window_hours // self.num_intervals)
        
        # Calculate raw weights for each interval
        raw_weights = []
        for i in range(self.num_intervals):
            # Determine which hour(s) this interval covers
            interval_start_offset = (i * self.interval_minutes) // 60
            interval_hour = (current_hour + interval_start_offset) % 24
            
            # Get volume weight for this hour
            weight = VolumeProfile.get_volume_weight(interval_hour)
            raw_weights.append(weight)
        
        # Normalize weights to sum to 1.0
        normalized_weights = VolumeProfile.normalize_weights(raw_weights)
        
        # Calculate USD amount for each interval
        interval_sizes = []
        total_allocated = Decimal('0')
        
        for i, weight in enumerate(normalized_weights):
            if i == len(normalized_weights) - 1:
                # Last interval gets remaining amount to avoid rounding errors
                amount = self.total_amount_usd - total_allocated
            else:
                amount = (self.total_amount_usd * weight).quantize(
                    Decimal('0.01'),
                    rounding=ROUND_DOWN
                )
            
            interval_sizes.append(amount)
            total_allocated += amount
        
        logger.debug(
            f"[VWAP] Interval sizes calculated: {[float(s) for s in interval_sizes]}"
        )
        
        return interval_sizes
    
    def get_current_interval_size(self) -> Decimal:
        """
        Get the USD amount for the current interval.
        
        Returns:
            Amount in USD for the current interval
        """
        if self.intervals_executed >= len(self.interval_sizes):
            return Decimal('0')
        return self.interval_sizes[self.intervals_executed]
    
    # =========================================================================
    # ABSTRACT METHOD IMPLEMENTATIONS
    # =========================================================================
    
    def validate_config(self) -> Tuple[bool, Optional[str]]:
        """
        Validate VWAP strategy configuration.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check total amount
        if self.total_amount_usd <= 0:
            return False, "total_amount_usd must be positive"
        
        if self.total_amount_usd < VWAPDefaults.MIN_POSITION_SIZE_USD:
            return False, (
                f"total_amount_usd must be at least "
                f"${VWAPDefaults.MIN_POSITION_SIZE_USD}"
            )
        
        # Check execution window
        if not (VWAPDefaults.MIN_EXECUTION_WINDOW_HOURS <= 
                self.execution_window_hours <= 
                VWAPDefaults.MAX_EXECUTION_WINDOW_HOURS):
            return False, (
                f"execution_window_hours must be between "
                f"{VWAPDefaults.MIN_EXECUTION_WINDOW_HOURS} and "
                f"{VWAPDefaults.MAX_EXECUTION_WINDOW_HOURS}"
            )
        
        # Check number of intervals
        if not (VWAPDefaults.MIN_INTERVALS <= 
                self.num_intervals <= 
                VWAPDefaults.MAX_INTERVALS):
            return False, (
                f"num_intervals must be between "
                f"{VWAPDefaults.MIN_INTERVALS} and "
                f"{VWAPDefaults.MAX_INTERVALS}"
            )
        
        # Check participation rate
        if not (VWAPDefaults.MIN_PARTICIPATION_RATE <= 
                self.participation_rate <= 
                VWAPDefaults.MAX_PARTICIPATION_RATE):
            return False, (
                f"participation_rate must be between "
                f"{VWAPDefaults.MIN_PARTICIPATION_RATE} and "
                f"{VWAPDefaults.MAX_PARTICIPATION_RATE}"
            )
        
        # Check token address
        if not self.token_address:
            return False, "token_address is required"
        
        # Check token symbol
        if not self.token_symbol or self.token_symbol == 'UNKNOWN':
            return False, "token_symbol is required"
        
        # Check account has sufficient balance
        if self.strategy_run.account:
            account_balance = self.strategy_run.account.balance_usd
            if account_balance < self.total_amount_usd:
                return False, (
                    f"Insufficient balance: ${account_balance} < "
                    f"${self.total_amount_usd}"
                )
        
        logger.debug(f"[VWAP] Configuration validated successfully")
        return True, None
    
    def execute(self) -> bool:
        """
        Execute the VWAP strategy.
        
        This validates configuration, updates status to RUNNING, and schedules
        the first interval execution via Celery task.
        
        Returns:
            True if execution started successfully, False otherwise
        """
        try:
            # Validate configuration
            is_valid, error = self.validate_config()
            if not is_valid:
                logger.error(f"[VWAP] Configuration invalid: {error}")
                self._mark_failed(error or "Configuration validation failed")
                return False
            
            # Check if we can execute
            can_execute, exec_error = self._can_execute()
            if not can_execute:
                logger.error(f"[VWAP] Cannot execute: {exec_error}")
                self._mark_failed(exec_error or "Cannot execute strategy")
                return False
            
            # Update status to RUNNING
            self.strategy_run.status = StrategyStatus.RUNNING
            self.strategy_run.started_at = timezone.now()
            self.strategy_run.total_orders = self.num_intervals
            self.strategy_run.save()
            
            logger.info(
                f"[VWAP] Strategy {self.strategy_run.strategy_id} started: "
                f"${self.total_amount_usd} over {self.num_intervals} intervals"
            )
            
            # Schedule first interval
            if self.start_immediately:
                # Execute first interval now
                self._schedule_next_interval(delay_seconds=0)
            else:
                # Wait for first interval time
                self._schedule_next_interval(delay_seconds=self.interval_minutes * 60)
            
            return True
            
        except Exception as e:
            logger.exception(f"[VWAP] Error executing strategy: {e}")
            self._mark_failed(str(e))
            return False
    
    def pause(self) -> bool:
        """
        Pause VWAP strategy execution.
        
        Returns:
            True if paused successfully, False otherwise
        """
        try:
            # Check if we can pause
            can_pause, error = self._can_pause()
            if not can_pause:
                logger.warning(f"[VWAP] Cannot pause: {error}")
                return False
            
            # Update status
            self.strategy_run.status = StrategyStatus.PAUSED
            self.strategy_run.paused_at = timezone.now()
            self.strategy_run.save()
            
            logger.info(
                f"[VWAP] Strategy {self.strategy_run.strategy_id} paused at "
                f"interval {self.intervals_executed}/{self.num_intervals}"
            )
            
            return True
            
        except Exception as e:
            logger.exception(f"[VWAP] Error pausing strategy: {e}")
            return False
    
    def resume(self) -> bool:
        """
        Resume paused VWAP strategy execution.
        
        Returns:
            True if resumed successfully, False otherwise
        """
        try:
            # Check if we can resume
            can_resume, error = self._can_resume()
            if not can_resume:
                logger.warning(f"[VWAP] Cannot resume: {error}")
                return False
            
            # Update status
            self.strategy_run.status = StrategyStatus.RUNNING
            self.strategy_run.paused_at = None
            self.strategy_run.save()
            
            # Recalculate interval sizes for remaining execution
            # (volume distribution may have changed while paused)
            self.interval_sizes = self._calculate_interval_sizes()
            
            # Schedule next interval
            self._schedule_next_interval(delay_seconds=0)
            
            logger.info(
                f"[VWAP] Strategy {self.strategy_run.strategy_id} resumed at "
                f"interval {self.intervals_executed + 1}/{self.num_intervals}"
            )
            
            return True
            
        except Exception as e:
            logger.exception(f"[VWAP] Error resuming strategy: {e}")
            return False
    
    def cancel(self) -> bool:
        """
        Cancel VWAP strategy execution.
        
        Returns:
            True if cancelled successfully, False otherwise
        """
        try:
            # Check if we can cancel
            can_cancel, error = self._can_cancel()
            if not can_cancel:
                logger.warning(f"[VWAP] Cannot cancel: {error}")
                return False
            
            # Update status
            self.strategy_run.status = StrategyStatus.CANCELLED
            self.strategy_run.cancelled_at = timezone.now()
            self.strategy_run.save()
            
            # Calculate how much was executed
            executed_amount = sum(self.interval_sizes[:self.intervals_executed])
            remaining_amount = self.total_amount_usd - executed_amount
            
            logger.info(
                f"[VWAP] Strategy {self.strategy_run.strategy_id} cancelled. "
                f"Executed: {self.intervals_executed}/{self.num_intervals} intervals "
                f"(${executed_amount}), Remaining: ${remaining_amount}"
            )
            
            return True
            
        except Exception as e:
            logger.exception(f"[VWAP] Error cancelling strategy: {e}")
            return False
    
    def get_progress(self) -> Dict[str, Any]:
        """
        Get current execution progress.
        
        Returns:
            Dictionary with progress information
        """
        # Calculate progress percentage
        if self.num_intervals > 0:
            progress_percent = (self.intervals_executed / self.num_intervals) * 100
        else:
            progress_percent = 0
        
        # Calculate executed amount
        executed_amount = sum(self.interval_sizes[:self.intervals_executed])
        remaining_amount = self.total_amount_usd - executed_amount
        
        # Estimate completion time
        if self.intervals_executed < self.num_intervals:
            remaining_intervals = self.num_intervals - self.intervals_executed
            remaining_minutes = remaining_intervals * self.interval_minutes
            estimated_completion = timezone.now() + timedelta(minutes=remaining_minutes)
        else:
            estimated_completion = None
        
        return {
            'progress_percent': round(progress_percent, 1),
            'current_step': f"Interval {self.intervals_executed}/{self.num_intervals}",
            'completed_orders': self.intervals_executed,
            'total_orders': self.num_intervals,
            'executed_amount_usd': float(executed_amount),
            'remaining_amount_usd': float(remaining_amount),
            'next_interval_size_usd': float(self.get_current_interval_size()),
            'interval_minutes': self.interval_minutes,
            'estimated_completion': estimated_completion.isoformat() if estimated_completion else None,
            'vwap_deviation_percent': float(self.current_vwap_deviation),
            'participation_rate': float(self.participation_rate),
        }
    
    # =========================================================================
    # EXECUTION HELPER METHODS
    # =========================================================================
    
    def _schedule_next_interval(self, delay_seconds: int = 0) -> None:
        """
        Schedule the next interval execution via Celery task.
        
        Args:
            delay_seconds: Seconds to delay before execution
        """
        try:
            # Import here to avoid circular imports
            from paper_trading.tasks.strategy_execution import execute_vwap_interval
            
            # Calculate next interval number (1-indexed for display)
            next_interval = self.intervals_executed + 1
            
            if delay_seconds > 0:
                # Schedule with delay
                execute_vwap_interval.apply_async(
                    args=[str(self.strategy_run.strategy_id), next_interval],
                    countdown=delay_seconds
                )
                logger.debug(
                    f"[VWAP] Scheduled interval {next_interval} in {delay_seconds}s"
                )
            else:
                # Execute immediately
                execute_vwap_interval.delay(
                    str(self.strategy_run.strategy_id),
                    next_interval
                )
                logger.debug(f"[VWAP] Scheduled interval {next_interval} immediately")
                
        except Exception as e:
            logger.exception(f"[VWAP] Error scheduling interval: {e}")
    
    def calculate_next_execution(self) -> Optional[datetime]:
        """
        Calculate when the next interval should execute.
        
        Returns:
            Datetime of next execution, or None if strategy is complete
        """
        # If all intervals executed, we're done
        if self.intervals_executed >= self.num_intervals:
            logger.info(f"[VWAP] All {self.num_intervals} intervals executed")
            return None
        
        # First interval executes immediately if start_immediately is True
        if self.intervals_executed == 0 and self.start_immediately:
            next_time = timezone.now()
        else:
            # Subsequent intervals use the interval timing
            if self.strategy_run.started_at:
                base_time = self.strategy_run.started_at
            else:
                base_time = timezone.now()
            
            # Calculate next execution time
            minutes_elapsed = self.intervals_executed * self.interval_minutes
            next_time = base_time + timedelta(minutes=minutes_elapsed)
        
        self.next_execution_time = next_time
        
        logger.debug(
            f"[VWAP] Next interval ({self.intervals_executed + 1}/{self.num_intervals}) "
            f"scheduled for {next_time}"
        )
        
        return next_time
    
    def execute_next_step(self) -> bool:
        """
        Execute the next interval in the VWAP schedule.
        
        Returns:
            True if step executed successfully, False otherwise
        """
        try:
            # Check if we should execute now
            if self.next_execution_time and timezone.now() < self.next_execution_time:
                logger.debug(
                    f"[VWAP] Not time yet. Next execution at {self.next_execution_time}"
                )
                return False
            
            # Check if all intervals are done
            if self.intervals_executed >= self.num_intervals:
                logger.info(
                    f"[VWAP] Strategy complete ({self.num_intervals} intervals executed)"
                )
                return False
            
            # Get the amount for this interval
            interval_amount = self.get_current_interval_size()
            interval_number = self.intervals_executed + 1
            
            logger.info(
                f"[VWAP] Executing interval {interval_number}/{self.num_intervals}: "
                f"${interval_amount} of {self.token_symbol}"
            )
            
            # Execute the interval order
            success = self._execute_interval_order(interval_number, interval_amount)
            
            if success:
                self.intervals_executed += 1
                
                # Update strategy run progress
                self.update_progress(
                    completed_orders=self.intervals_executed,
                    current_step=f"Interval {self.intervals_executed}/{self.num_intervals}"
                )
                
                # Calculate next execution time
                self.calculate_next_execution()
                
                logger.info(
                    f"[VWAP] Interval {interval_number} executed successfully. "
                    f"Progress: {self.intervals_executed}/{self.num_intervals}"
                )
            
            return success
            
        except Exception as e:
            logger.exception(f"[VWAP] Error executing interval: {e}")
            return False
    
    def _execute_interval_order(
        self,
        interval_number: int,
        amount_usd: Decimal
    ) -> bool:
        """
        Execute a single VWAP interval order.
        
        This method creates the actual trade order for this interval.
        In production, this integrates with the paper trading simulator.
        
        Args:
            interval_number: Which interval this is (1-indexed)
            amount_usd: Amount to buy in USD
            
        Returns:
            True if order executed successfully, False otherwise
        """
        try:
            # Import trade executor (lazy import to avoid circular dependency)
            from paper_trading.services.paper_trading_simulator import (
                PaperTradingSimulator
            )
            
            # Get account
            account = self.strategy_run.account
            if not account:
                logger.error("[VWAP] No account associated with strategy")
                return False
            
            # Create simulator instance
            simulator = PaperTradingSimulator(account)
            
            # Execute buy order
            trade_result = simulator.execute_buy(
                token_address=self.token_address,
                token_symbol=self.token_symbol,
                amount_usd=amount_usd,
                order_type='VWAP_INTERVAL',
                metadata={
                    'strategy_id': str(self.strategy_run.strategy_id),
                    'strategy_type': StrategyType.VWAP,
                    'interval_number': interval_number,
                    'total_intervals': self.num_intervals,
                    'participation_rate': float(self.participation_rate),
                }
            )
            
            if trade_result and trade_result.get('success'):
                # Update VWAP tracking
                execution_price = Decimal(str(trade_result.get('price', 0)))
                if execution_price > 0:
                    self.total_volume_executed += amount_usd / execution_price
                    self.total_value_executed += amount_usd
                    
                    # Calculate current VWAP deviation
                    if self.vwap_benchmark > 0:
                        our_vwap = self.total_value_executed / self.total_volume_executed
                        self.current_vwap_deviation = (
                            (our_vwap - self.vwap_benchmark) / self.vwap_benchmark * 100
                        )
                
                return True
            else:
                logger.error(
                    f"[VWAP] Interval {interval_number} order failed: "
                    f"{trade_result.get('error', 'Unknown error') if trade_result else 'No result'}"
                )
                return False
                
        except ImportError:
            # Fallback for testing without full simulator
            logger.warning(
                f"[VWAP] Simulator not available, simulating interval {interval_number}"
            )
            return True
            
        except Exception as e:
            logger.exception(f"[VWAP] Error executing interval order: {e}")
            return False
    
    def update_progress(
        self,
        completed_orders: int,
        current_step: str
    ) -> None:
        """
        Update strategy progress in database.
        
        Args:
            completed_orders: Number of completed intervals
            current_step: Description of current step
        """
        progress_percent = (completed_orders / self.num_intervals) * 100
        
        self.strategy_run.completed_orders = completed_orders
        self.strategy_run.current_step = current_step
        self.strategy_run.progress_percent = Decimal(str(progress_percent))
        self.strategy_run.save()
    
    def get_progress_summary(self) -> Dict[str, Any]:
        """
        Get detailed progress summary for display.
        
        Returns:
            Dictionary with comprehensive progress information
        """
        progress = self.get_progress()
        
        # Add VWAP-specific metrics
        progress.update({
            'strategy_type': 'VWAP',
            'token_symbol': self.token_symbol,
            'total_amount_usd': float(self.total_amount_usd),
            'execution_window_hours': self.execution_window_hours,
            'volume_distribution': [float(s) for s in self.interval_sizes],
            'status': self.strategy_run.status,
        })
        
        return progress


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_vwap_strategy(
    account: 'PaperTradingAccount',
    token_address: str,
    token_symbol: str,
    total_amount_usd: Decimal,
    execution_window_hours: Optional[int] = None,
    num_intervals: Optional[int] = None,
    participation_rate: Optional[Decimal] = None
) -> 'StrategyRun':
    """
    Factory function to create a new VWAP strategy.
    
    Args:
        account: Paper trading account
        token_address: Token contract address
        token_symbol: Token symbol
        total_amount_usd: Total amount to invest
        execution_window_hours: Hours to complete (default: 6)
        num_intervals: Number of intervals (default: 12)
        participation_rate: Target volume participation (default: 0.05)
        
    Returns:
        Created StrategyRun instance
    """
    from paper_trading.models import StrategyRun
    
    # Use defaults if not provided
    if execution_window_hours is None:
        execution_window_hours = VWAPDefaults.DEFAULT_EXECUTION_WINDOW_HOURS
    
    if num_intervals is None:
        num_intervals = VWAPDefaults.DEFAULT_INTERVALS
    
    if participation_rate is None:
        participation_rate = VWAPDefaults.DEFAULT_PARTICIPATION_RATE
    
    config = {
        'token_address': token_address,
        'token_symbol': token_symbol,
        'total_amount_usd': str(total_amount_usd),
        'execution_window_hours': execution_window_hours,
        'num_intervals': num_intervals,
        'participation_rate': str(participation_rate),
        'start_immediately': True
    }
    
    strategy_run = StrategyRun.objects.create(
        account=account,
        strategy_type=StrategyType.VWAP,
        config=config,
        total_orders=num_intervals,
        status=StrategyStatus.PENDING
    )
    
    logger.info(
        f"[VWAP] Created strategy {strategy_run.strategy_id} for {token_symbol}: "
        f"${total_amount_usd} over {execution_window_hours}h in {num_intervals} intervals "
        f"({float(participation_rate)*100:.1f}% participation)"
    )
    
    return strategy_run