"""
Grid Trading Strategy - Profit from Price Oscillations

Grid trading places buy and sell orders at regular intervals within a price range.
When price oscillates, orders get filled generating profit from each cycle.

Strategy Logic:
1. Define price range (lower_price to upper_price)
2. Split range into num_grids levels
3. Place buy orders at each level below current price
4. Place sell orders at each level above current price
5. When buy order fills → place sell order at next level up
6. When sell order fills → place buy order at next level down
7. Accumulate profit from each buy-sell cycle

Phase 7B - Day 3

File: dexproject/paper_trading/strategies/grid_strategy.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List, Tuple
from datetime import timedelta
from django.utils import timezone

from paper_trading.constants import (
    StrategyType,
    StrategyStatus,
)
from paper_trading.strategies.base_strategy import BaseStrategy


logger = logging.getLogger(__name__)


# =============================================================================
# GRID STRATEGY IMPLEMENTATION
# =============================================================================

class GridStrategy(BaseStrategy):
    """
    Grid Trading Strategy Implementation.
    
    Profits from price oscillations by placing buy/sell orders at regular
    intervals within a defined price range.
    
    Configuration Parameters:
        lower_price (Decimal): Bottom of grid range (must be < upper_price)
        upper_price (Decimal): Top of grid range (must be > lower_price)
        num_grids (int): Number of grid levels (2-100)
        amount_per_grid_usd (Decimal): USD amount per grid level
        token_address (str): Token contract address
        token_symbol (str): Token symbol (e.g., 'WETH')
        rebalance_on_fill (bool): Re-place orders after fill (default: True)
        max_cycles (int, optional): Maximum buy-sell cycles before stop
        profit_target_usd (Decimal, optional): Stop when profit reaches target
    
    Example Configuration:
        {
            'lower_price': 2000.00,
            'upper_price': 2400.00,
            'num_grids': 10,
            'amount_per_grid_usd': 100.00,
            'token_address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
            'token_symbol': 'WETH',
            'rebalance_on_fill': True,
            'max_cycles': 50,
            'profit_target_usd': 500.00
        }
    
    Lifecycle:
        1. Validate config (price range, grid count, amounts)
        2. Calculate grid levels (evenly distributed)
        3. Execute: Place all initial grid orders
        4. Monitor: Track fills and rebalance
        5. Complete: When max_cycles or profit_target reached
    """
    
    def __init__(self, strategy_run: 'StrategyRun') -> None:
        """
        Initialize Grid Trading Strategy.
        
        Args:
            strategy_run: StrategyRun model instance
            
        Raises:
            ValueError: If strategy_run is invalid
        """
        super().__init__(strategy_run)
        
        # Validate this is a GRID strategy
        if self.strategy_type != StrategyType.GRID:
            raise ValueError(
                f"GridStrategy requires strategy_type=GRID, got {self.strategy_type}"
            )
        
        # Grid state tracking
        self.grid_levels: List[Decimal] = []
        self.completed_cycles: int = 0
        self.total_profit_usd: Decimal = Decimal('0')
        
        logger.info(
            f"Initialized GridStrategy for strategy_id={strategy_run.strategy_id}"
        )
    
    # =========================================================================
    # CONFIGURATION VALIDATION
    # =========================================================================
    
    def validate_config(self) -> tuple[bool, Optional[str]]:
        """
        Validate grid trading configuration.
        
        Checks:
        - All required fields present
        - Price range valid (lower < upper)
        - Number of grids reasonable (2-100)
        - Amounts positive
        - Token information valid
        - Account has sufficient balance
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check required fields
            required_fields = [
                'lower_price',
                'upper_price',
                'num_grids',
                'amount_per_grid_usd',
                'token_address',
                'token_symbol'
            ]
            
            for field in required_fields:
                if field not in self.config:
                    return False, f"Missing required field: {field}"
            
            # Validate price range
            lower_price = Decimal(str(self.config['lower_price']))
            upper_price = Decimal(str(self.config['upper_price']))
            
            if lower_price <= 0:
                return False, "lower_price must be positive"
            
            if upper_price <= 0:
                return False, "upper_price must be positive"
            
            if lower_price >= upper_price:
                return False, "lower_price must be less than upper_price"
            
            # Validate grid range is reasonable (at least 5% range)
            price_range_percent = ((upper_price - lower_price) / lower_price) * 100
            if price_range_percent < 5:
                return False, (
                    f"Price range too narrow ({price_range_percent:.2f}%). "
                    "Minimum 5% range required for profitable grid trading"
                )
            
            # Validate number of grids
            num_grids = int(self.config['num_grids'])
            if num_grids < 2:
                return False, "num_grids must be at least 2"
            
            if num_grids > 100:
                return False, "num_grids cannot exceed 100"
            
            # Validate amount per grid
            amount_per_grid = Decimal(str(self.config['amount_per_grid_usd']))
            if amount_per_grid <= 0:
                return False, "amount_per_grid_usd must be positive"
            
            # Calculate total capital required
            # Need capital for all buy orders (approximately half the grids)
            estimated_buy_grids = num_grids // 2
            total_capital_required = amount_per_grid * estimated_buy_grids
            
            # Add 10% buffer for gas and slippage
            total_capital_required *= Decimal('1.10')
            
            # Check account balance
            if self.strategy_run.account:
                account_balance = self.strategy_run.account.current_balance_usd
                if account_balance < total_capital_required:
                    return False, (
                        f"Insufficient balance. Required: ${total_capital_required:.2f}, "
                        f"Available: ${account_balance:.2f}"
                    )
            
            # Validate token address format
            token_address = str(self.config['token_address'])
            if not token_address.startswith('0x') or len(token_address) != 42:
                return False, "Invalid token_address format (must be 0x... 42 chars)"
            
            # Validate optional fields
            if 'max_cycles' in self.config:
                max_cycles = int(self.config['max_cycles'])
                if max_cycles < 1:
                    return False, "max_cycles must be at least 1"
            
            if 'profit_target_usd' in self.config:
                profit_target = Decimal(str(self.config['profit_target_usd']))
                if profit_target <= 0:
                    return False, "profit_target_usd must be positive"
            
            logger.info(
                f"Grid config validated: {lower_price}-{upper_price}, "
                f"{num_grids} grids, ${amount_per_grid}/grid"
            )
            
            return True, None
            
        except (ValueError, KeyError, TypeError) as e:
            logger.error(f"Grid config validation error: {e}", exc_info=True)
            return False, f"Configuration validation failed: {str(e)}"
    
    # =========================================================================
    # GRID CALCULATION
    # =========================================================================
    
    def calculate_grid_levels(self) -> List[Decimal]:
        """
        Calculate evenly distributed grid price levels.
        
        Formula:
            price_step = (upper_price - lower_price) / (num_grids - 1)
            levels = [lower_price + (i * price_step) for i in range(num_grids)]
        
        Returns:
            List of price levels from lowest to highest
        
        Example:
            lower=2000, upper=2400, grids=5
            → [2000, 2100, 2200, 2300, 2400]
        """
        try:
            lower_price = Decimal(str(self.config['lower_price']))
            upper_price = Decimal(str(self.config['upper_price']))
            num_grids = int(self.config['num_grids'])
            
            # Calculate step size between grids
            price_range = upper_price - lower_price
            price_step = price_range / (num_grids - 1)
            
            # Generate grid levels
            grid_levels = []
            for i in range(num_grids):
                level_price = lower_price + (price_step * i)
                # Round to 4 decimal places for reasonable precision
                level_price = level_price.quantize(Decimal('0.0001'))
                grid_levels.append(level_price)
            
            logger.info(
                f"Calculated {len(grid_levels)} grid levels: "
                f"{grid_levels[0]} to {grid_levels[-1]}, "
                f"step=${price_step:.4f}"
            )
            
            return grid_levels
            
        except Exception as e:
            logger.error(f"Error calculating grid levels: {e}", exc_info=True)
            return []
    
    # =========================================================================
    # STRATEGY EXECUTION
    # =========================================================================
    
    def execute(self) -> bool:
        """
        Execute grid trading strategy.
        
        Steps:
        1. Validate configuration
        2. Calculate grid levels
        3. Get current token price
        4. Place buy orders below current price
        5. Place sell orders above current price
        6. Update strategy status to RUNNING
        7. Schedule monitoring task
        
        Returns:
            True if execution started successfully, False otherwise
        """
        try:
            logger.info(f"Executing Grid Strategy: {self.strategy_run.strategy_id}")
            
            # Validate execution is allowed
            can_execute, error = self._can_execute()
            if not can_execute:
                self._mark_failed(error)
                return False
            
            # Calculate grid levels
            self.grid_levels = self.calculate_grid_levels()
            if not self.grid_levels:
                self._mark_failed("Failed to calculate grid levels")
                return False
            
            # Update status to RUNNING
            self._update_status(StrategyStatus.RUNNING)
            
            # TODO: Get current token price from price service
            # For now, use middle of range as starting point
            current_price = (
                Decimal(str(self.config['lower_price'])) +
                Decimal(str(self.config['upper_price']))
            ) / 2
            
            # Place initial grid orders
            success = self._place_initial_orders(current_price)
            if not success:
                self._mark_failed("Failed to place initial grid orders")
                return False
            
            # Update progress
            self._update_progress(
                Decimal('10'),
                f"Grid initialized: {len(self.grid_levels)} levels"
            )
            
            # TODO: Schedule monitoring task via Celery
            # from paper_trading.tasks.strategy_execution import monitor_grid_strategy
            # monitor_grid_strategy.apply_async(
            #     args=[str(self.strategy_run.strategy_id)],
            #     countdown=60
            # )
            
            logger.info(
                f"Grid strategy {self.strategy_run.strategy_id} started successfully"
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Error executing grid strategy: {e}",
                exc_info=True
            )
            self._mark_failed(f"Execution error: {str(e)}")
            return False
    
    async def _place_initial_orders(self, current_price: Decimal) -> bool:
        """
        Place initial buy and sell orders at grid levels.
        
        Args:
            current_price: Current token price
            
        Returns:
            True if orders placed successfully
        """
        try:
            buy_orders_placed = 0
            sell_orders_placed = 0
            
            amount_per_grid = Decimal(str(self.config['amount_per_grid_usd']))
            token_symbol = str(self.config['token_symbol'])
            
            # Place orders at each grid level
            for level_price in self.grid_levels:
                if level_price < current_price:
                    # Place buy order below current price
                    # TODO: Create actual PaperOrder via order service
                    logger.debug(
                        f"BUY order: {token_symbol} at ${level_price:.4f}, "
                        f"${amount_per_grid}"
                    )
                    buy_orders_placed += 1
                    
                elif level_price > current_price:
                    # Place sell order above current price
                    # TODO: Create actual PaperOrder via order service
                    logger.debug(
                        f"SELL order: {token_symbol} at ${level_price:.4f}, "
                        f"${amount_per_grid}"
                    )
                    sell_orders_placed += 1
            
            # Update strategy metadata
            total_orders = buy_orders_placed + sell_orders_placed
            self.strategy_run.total_orders = total_orders
            self.strategy_run.save()
            
            logger.info(
                f"Placed {buy_orders_placed} buy orders and "
                f"{sell_orders_placed} sell orders"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error placing initial orders: {e}", exc_info=True)
            return False
    
    # =========================================================================
    # PAUSE / RESUME / CANCEL
    # =========================================================================
    
    def pause(self) -> bool:
        """
        Pause grid strategy execution.
        
        Actions:
        - Stops placing new orders
        - Allows existing orders to complete
        - Updates status to PAUSED
        
        Returns:
            True if paused successfully
        """
        try:
            # Validate can pause
            can_pause, error = self._can_pause()
            if not can_pause:
                logger.warning(f"Cannot pause strategy: {error}")
                return False
            
            # Update status
            self.strategy_run.status = StrategyStatus.PAUSED
            self.strategy_run.paused_at = timezone.now()
            self.strategy_run.save()
            
            # TODO: Cancel scheduled monitoring tasks
            
            logger.info(f"Grid strategy {self.strategy_run.strategy_id} paused")
            return True
            
        except Exception as e:
            logger.error(f"Error pausing grid strategy: {e}", exc_info=True)
            return False
    
    def resume(self) -> bool:
        """
        Resume paused grid strategy.
        
        Actions:
        - Validates current state
        - Resumes order placement
        - Updates status to RUNNING
        
        Returns:
            True if resumed successfully
        """
        try:
            # Validate can resume
            can_resume, error = self._can_resume()
            if not can_resume:
                logger.warning(f"Cannot resume strategy: {error}")
                return False
            
            # Update status
            self.strategy_run.status = StrategyStatus.RUNNING
            self.strategy_run.paused_at = None
            self.strategy_run.save()
            
            # TODO: Restart monitoring tasks
            
            logger.info(f"Grid strategy {self.strategy_run.strategy_id} resumed")
            return True
            
        except Exception as e:
            logger.error(f"Error resuming grid strategy: {e}", exc_info=True)
            return False
    
    def cancel(self) -> bool:
        """
        Cancel grid strategy execution.
        
        Actions:
        - Cancel all pending orders
        - Stop all scheduled tasks
        - Update status to CANCELLED
        
        Returns:
            True if cancelled successfully
        """
        try:
            # Validate can cancel
            can_cancel, error = self._can_cancel()
            if not can_cancel:
                logger.warning(f"Cannot cancel strategy: {error}")
                return False
            
            # TODO: Cancel all pending orders
            # from paper_trading.models import PaperOrder, OrderStatus
            # pending_orders = self.strategy_run.orders.filter(
            #     status=OrderStatus.PENDING
            # )
            # for order in pending_orders:
            #     order.status = OrderStatus.CANCELLED
            #     order.save()
            
            # Update status
            self.strategy_run.status = StrategyStatus.CANCELLED
            self.strategy_run.cancelled_at = timezone.now()
            self.strategy_run.save()
            
            logger.info(f"Grid strategy {self.strategy_run.strategy_id} cancelled")
            return True
            
        except Exception as e:
            logger.error(f"Error cancelling grid strategy: {e}", exc_info=True)
            return False
    
    # =========================================================================
    # PROGRESS TRACKING
    # =========================================================================
    
    def get_progress(self) -> Dict[str, Any]:
        """
        Get grid strategy execution progress.
        
        Returns:
            Dictionary with:
            - progress_percent: Completion percentage
            - current_step: Current execution phase
            - completed_orders: Orders filled
            - total_orders: Total orders placed
            - completed_cycles: Buy-sell cycles completed
            - total_profit_usd: Accumulated profit
        """
        try:
            # Calculate progress based on cycles or profit target
            progress_percent = Decimal('0')
            
            if 'max_cycles' in self.config:
                max_cycles = int(self.config['max_cycles'])
                progress_percent = (
                    Decimal(self.completed_cycles) / max_cycles * 100
                )
            elif 'profit_target_usd' in self.config:
                profit_target = Decimal(str(self.config['profit_target_usd']))
                progress_percent = (
                    self.total_profit_usd / profit_target * 100
                )
            else:
                # No target set, use order completion rate
                if self.strategy_run.total_orders > 0:
                    progress_percent = (
                        Decimal(self.strategy_run.completed_orders) /
                        self.strategy_run.total_orders * 100
                    )
            
            # Cap at 100%
            progress_percent = min(progress_percent, Decimal('100'))
            
            return {
                'progress_percent': float(progress_percent),
                'current_step': self.strategy_run.current_step or "Monitoring grid",
                'completed_orders': self.strategy_run.completed_orders,
                'total_orders': self.strategy_run.total_orders,
                'completed_cycles': self.completed_cycles,
                'total_profit_usd': float(self.total_profit_usd),
                'grid_levels': len(self.grid_levels),
            }
            
        except Exception as e:
            logger.error(f"Error getting progress: {e}", exc_info=True)
            return {
                'progress_percent': 0,
                'current_step': 'Error',
                'completed_orders': 0,
                'total_orders': 0,
            }
    
    # =========================================================================
    # GRID-SPECIFIC LOGIC
    # =========================================================================
    
    async def handle_order_fill(
        self,
        filled_order: 'PaperOrder',
        fill_price: Decimal
    ) -> bool:
        """
        Handle a filled grid order.
        
        When buy order fills:
        - Place sell order at next level up
        - Track position
        
        When sell order fills:
        - Place buy order at next level down
        - Calculate profit for cycle
        - Increment cycle counter
        
        Args:
            filled_order: The order that was filled
            fill_price: Price at which order filled
            
        Returns:
            True if handled successfully
        """
        try:
            rebalance_on_fill = self.config.get('rebalance_on_fill', True)
            
            if not rebalance_on_fill:
                logger.debug("Rebalancing disabled, order fill acknowledged")
                return True
            
            # TODO: Implement rebalancing logic
            # 1. Determine if this was a buy or sell
            # 2. Find the grid level
            # 3. Place opposite order
            # 4. Update metrics
            
            logger.info(
                f"Order filled at ${fill_price:.4f}, "
                f"rebalance={rebalance_on_fill}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling order fill: {e}", exc_info=True)
            return False
    
    def calculate_cycle_profit(
        self,
        buy_price: Decimal,
        sell_price: Decimal,
        amount: Decimal
    ) -> Decimal:
        """
        Calculate profit from a complete buy-sell cycle.
        
        Args:
            buy_price: Price bought at
            sell_price: Price sold at
            amount: Amount traded
            
        Returns:
            Profit in USD (can be negative for loss)
        """
        try:
            profit = (sell_price - buy_price) * amount
            
            # Subtract estimated fees (0.5% total)
            fee_rate = Decimal('0.005')
            estimated_fees = amount * (buy_price + sell_price) * fee_rate / 2
            net_profit = profit - estimated_fees
            
            logger.debug(
                f"Cycle profit: ${net_profit:.2f} "
                f"(buy=${buy_price:.4f}, sell=${sell_price:.4f}, "
                f"amount={amount:.4f})"
            )
            
            return net_profit
            
        except Exception as e:
            logger.error(f"Error calculating cycle profit: {e}", exc_info=True)
            return Decimal('0')
    
    def check_price_breakout(self, current_price: Decimal) -> Optional[str]:
        """
        Check if price has broken out of grid range.
        
        Args:
            current_price: Current token price
            
        Returns:
            'ABOVE' if price above upper bound
            'BELOW' if price below lower bound
            None if within range
        """
        try:
            lower_price = Decimal(str(self.config['lower_price']))
            upper_price = Decimal(str(self.config['upper_price']))
            
            if current_price > upper_price:
                logger.warning(
                    f"Price breakout ABOVE: ${current_price:.4f} > ${upper_price:.4f}"
                )
                return 'ABOVE'
            elif current_price < lower_price:
                logger.warning(
                    f"Price breakout BELOW: ${current_price:.4f} < ${lower_price:.4f}"
                )
                return 'BELOW'
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking breakout: {e}", exc_info=True)
            return None
    
    def should_stop_strategy(self) -> tuple[bool, Optional[str]]:
        """
        Check if strategy should stop based on completion criteria.
        
        Checks:
        - Max cycles reached
        - Profit target reached
        - Price breakout
        
        Returns:
            Tuple of (should_stop, reason)
        """
        try:
            # Check max cycles
            if 'max_cycles' in self.config:
                max_cycles = int(self.config['max_cycles'])
                if self.completed_cycles >= max_cycles:
                    return True, f"Max cycles reached: {max_cycles}"
            
            # Check profit target
            if 'profit_target_usd' in self.config:
                profit_target = Decimal(str(self.config['profit_target_usd']))
                if self.total_profit_usd >= profit_target:
                    return True, f"Profit target reached: ${profit_target:.2f}"
            
            # Check for price breakout
            # TODO: Get current price and check breakout
            
            return False, None
            
        except Exception as e:
            logger.error(f"Error checking stop conditions: {e}", exc_info=True)
            return False, None