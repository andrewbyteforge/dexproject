"""
Strategy Execution Tasks - Celery Background Tasks

Handles background execution of trading strategies:
- DCA interval execution
- Grid strategy monitoring and rebalancing
- Strategy monitoring and health checks
- Progress updates and notifications
- Strategy completion handling

Phase 7B - Day 2: DCA Strategy Execution Tasks
Phase 7B - Day 4: Grid Strategy Execution Tasks

File: dexproject/paper_trading/tasks/strategy_execution.py
"""

import logging
from decimal import Decimal
from typing import Optional, List, Dict, Any
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django.db import transaction

from paper_trading.models import (
    StrategyRun,
    StrategyOrder,
    PaperOrder,
    PaperTradingAccount,
)
from paper_trading.constants import (
    StrategyType,
    StrategyStatus,
    OrderType,
    OrderStatus,
)


logger = logging.getLogger(__name__)


# =============================================================================
# DCA INTERVAL EXECUTION
# =============================================================================

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='paper_trading.execute_dca_interval'
)
def execute_dca_interval(self, strategy_id: str, interval_number: int) -> dict:
    """
    Execute a single DCA buy interval.
    
    This task is scheduled by the DCA strategy to execute one buy order
    at the configured interval. It creates the order, links it to the strategy,
    updates progress, and schedules the next interval if needed.
    
    Args:
        strategy_id: UUID of the StrategyRun
        interval_number: Which interval this is (1, 2, 3, ...)
    
    Returns:
        Dictionary with execution results
        
    Example:
        execute_dca_interval.apply_async(
            args=['uuid-here', 1],
            countdown=86400  # 24 hours
        )
    """
    logger.info(f"Executing DCA interval {interval_number} for strategy {strategy_id}")
    
    try:
        # Get strategy run
        strategy_run = StrategyRun.objects.select_related('account').get(
            strategy_id=strategy_id
        )
        
        # Check if strategy is still running
        if strategy_run.status != StrategyStatus.RUNNING:
            logger.warning(
                f"Strategy {strategy_id} is {strategy_run.status}, "
                f"skipping interval {interval_number}"
            )
            return {
                'success': False,
                'reason': f"Strategy not running (status: {strategy_run.status})",
                'interval': interval_number,
            }
        
        # Parse DCA configuration
        config = strategy_run.config
        token_address = config.get('token_address')
        token_symbol = config.get('token_symbol')
        total_amount = Decimal(str(config.get('total_amount_usd', '0')))
        num_intervals = int(config.get('num_intervals', 0))
        interval_hours = int(config.get('interval_hours', 0))
        
        # Calculate amount for this interval
        amount_per_interval = total_amount / Decimal(str(num_intervals))
        
        logger.debug(
            f"DCA interval {interval_number}: buying ${amount_per_interval} of {token_symbol}"
        )
        
        # Create the buy order
        with transaction.atomic():
            # Lock the strategy run to prevent race conditions
            strategy_run = StrategyRun.objects.select_for_update().get(
                strategy_id=strategy_id
            )
            
            # Create paper order
            order = PaperOrder.objects.create(
                account=strategy_run.account,
                order_type=OrderType.MARKET,
                side='BUY',
                token_address=token_address,
                token_symbol=token_symbol,
                amount_usd=amount_per_interval,
                status=OrderStatus.PENDING,
                notes=f"DCA Strategy Interval {interval_number}/{num_intervals}",
            )
            
            # Link order to strategy
            StrategyOrder.objects.create(
                strategy_run=strategy_run,
                order=order,
                order_sequence=interval_number,
            )
            
            logger.info(
                f"Created order {order.order_id} for DCA interval {interval_number}"
            )
        
        # Execute the order (this would normally trigger order execution flow)
        # For now, we'll mark it as filled immediately for paper trading
        # In production, this would integrate with your order execution system
        try:
            from paper_trading.services.order_executor import OrderExecutor
            
            executor = OrderExecutor()
            execution_result = executor.execute_order(order)
            
            if execution_result.get('success'):
                logger.info(f"Order {order.order_id} executed successfully")
                
                # Update strategy performance
                strategy_run.refresh_from_db()
                strategy_run.update_performance()
                
                # Calculate progress
                completed = strategy_run.completed_orders
                progress_percent = (Decimal(str(completed)) / Decimal(str(num_intervals))) * Decimal('100')
                
                # Update progress
                strategy_run.progress_percent = progress_percent
                strategy_run.current_step = f"Completed interval {completed}/{num_intervals}"
                strategy_run.save()
                
                logger.info(
                    f"DCA strategy {strategy_id} progress: {progress_percent}% "
                    f"({completed}/{num_intervals} intervals)"
                )
            else:
                logger.error(f"Order {order.order_id} execution failed")
                strategy_run.failed_orders += 1
                strategy_run.save()
                
        except Exception as e:
            logger.exception(f"Error executing order {order.order_id}: {e}")
            strategy_run.failed_orders += 1
            strategy_run.save()
        
        # Schedule next interval if not complete
        if interval_number < num_intervals:
            next_interval = interval_number + 1
            next_execution_time = interval_hours * 3600  # Convert hours to seconds
            
            execute_dca_interval.apply_async(
                args=[strategy_id, next_interval],
                countdown=next_execution_time,
            )
            
            logger.info(
                f"Scheduled DCA interval {next_interval} for strategy {strategy_id} "
                f"in {interval_hours} hours"
            )
        else:
            # Strategy complete!
            strategy_run.status = StrategyStatus.COMPLETED
            strategy_run.completed_at = timezone.now()
            strategy_run.progress_percent = Decimal('100.00')
            strategy_run.current_step = f"Completed all {num_intervals} intervals"
            strategy_run.save()
            
            logger.info(f"DCA strategy {strategy_id} completed successfully!")
            
            # Send completion notification
            send_strategy_notification.apply_async(
                args=[strategy_id, 'completed'],
            )
        
        return {
            'success': True,
            'interval': interval_number,
            'order_id': str(order.order_id),
            'amount': str(amount_per_interval),
            'next_interval': interval_number + 1 if interval_number < num_intervals else None,
        }
        
    except StrategyRun.DoesNotExist:
        logger.error(f"Strategy {strategy_id} not found")
        return {
            'success': False,
            'reason': 'Strategy not found',
            'interval': interval_number,
        }
        
    except Exception as e:
        logger.exception(f"Error in DCA interval execution: {e}")
        
        # Retry with exponential backoff
        try:
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for DCA interval {interval_number}")
            
            # Mark strategy as failed
            try:
                strategy_run = StrategyRun.objects.get(strategy_id=strategy_id)
                strategy_run.status = StrategyStatus.FAILED
                strategy_run.error_message = f"Failed to execute interval {interval_number}: {str(e)}"
                strategy_run.save()
            except Exception as save_error:
                logger.exception(f"Error marking strategy as failed: {save_error}")
            
            return {
                'success': False,
                'reason': str(e),
                'interval': interval_number,
            }


# =============================================================================
# GRID STRATEGY EXECUTION
# =============================================================================

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='paper_trading.execute_grid_strategy'
)
def execute_grid_strategy(self, strategy_id: str) -> dict:
    """
    Initialize and execute a Grid trading strategy.
    
    This task:
    1. Places initial buy orders at all grid levels
    2. Sets up monitoring for order fills
    3. Tracks profit cycles
    4. Detects breakouts from grid range
    
    Args:
        strategy_id: UUID of the StrategyRun
    
    Returns:
        Dictionary with execution results
        
    Example:
        execute_grid_strategy.apply_async(
            args=['uuid-here']
        )
    """
    logger.info(f"Initializing Grid strategy {strategy_id}")
    
    try:
        # Get strategy run
        strategy_run = StrategyRun.objects.select_related('account').get(
            strategy_id=strategy_id
        )
        
        # Check if strategy is still running
        if strategy_run.status != StrategyStatus.RUNNING:
            logger.warning(
                f"Strategy {strategy_id} is {strategy_run.status}, cannot initialize"
            )
            return {
                'success': False,
                'reason': f"Strategy not running (status: {strategy_run.status})",
            }
        
        # Parse Grid configuration
        config = strategy_run.config
        token_address = config.get('token_address')
        token_symbol = config.get('token_symbol')
        price_lower = Decimal(str(config.get('price_lower', '0')))
        price_upper = Decimal(str(config.get('price_upper', '0')))
        grid_levels = int(config.get('grid_levels', 0))
        total_investment = Decimal(str(config.get('total_investment_usd', '0')))
        
        # Calculate grid parameters
        grid_step = (price_upper - price_lower) / Decimal(str(grid_levels - 1))
        investment_per_level = total_investment / Decimal(str(grid_levels))
        
        logger.info(
            f"Grid setup: {grid_levels} levels from ${price_lower} to ${price_upper}, "
            f"step: ${grid_step}, investment per level: ${investment_per_level}"
        )
        
        # Create initial buy orders at all grid levels
        orders_created = []
        
        with transaction.atomic():
            # Lock the strategy run
            strategy_run = StrategyRun.objects.select_for_update().get(
                strategy_id=strategy_id
            )
            
            for level in range(grid_levels):
                grid_price = price_lower + (grid_step * Decimal(str(level)))
                
                # Create limit buy order at this grid level
                order = PaperOrder.objects.create(
                    account=strategy_run.account,
                    order_type=OrderType.LIMIT,
                    side='BUY',
                    token_address=token_address,
                    token_symbol=token_symbol,
                    amount_usd=investment_per_level,
                    limit_price=grid_price,
                    status=OrderStatus.PENDING,
                    notes=f"Grid Level {level + 1}/{grid_levels} @ ${grid_price}",
                )
                
                # Link order to strategy
                StrategyOrder.objects.create(
                    strategy_run=strategy_run,
                    order=order,
                    order_sequence=level + 1,
                )
                
                orders_created.append({
                    'order_id': str(order.order_id),
                    'level': level + 1,
                    'price': str(grid_price),
                })
                
                logger.debug(f"Created grid buy order at level {level + 1}: ${grid_price}")
            
            # Update strategy metadata
            strategy_run.total_orders = grid_levels
            strategy_run.current_step = f"Placed {grid_levels} grid orders"
            strategy_run.progress_percent = Decimal('10.00')  # Initial setup
            strategy_run.save()
        
        logger.info(f"Grid strategy {strategy_id} initialized with {len(orders_created)} orders")
        
        # Schedule monitoring task
        monitor_grid_orders.apply_async(
            args=[strategy_id],
            countdown=30,  # Check after 30 seconds
        )
        
        return {
            'success': True,
            'strategy_id': strategy_id,
            'orders_created': len(orders_created),
            'grid_levels': grid_levels,
            'orders': orders_created,
        }
        
    except StrategyRun.DoesNotExist:
        logger.error(f"Strategy {strategy_id} not found")
        return {
            'success': False,
            'reason': 'Strategy not found',
        }
        
    except Exception as e:
        logger.exception(f"Error initializing Grid strategy: {e}")
        
        # Retry with exponential backoff
        try:
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for Grid strategy initialization")
            
            # Mark strategy as failed
            try:
                strategy_run = StrategyRun.objects.get(strategy_id=strategy_id)
                strategy_run.status = StrategyStatus.FAILED
                strategy_run.error_message = f"Failed to initialize: {str(e)}"
                strategy_run.save()
            except Exception as save_error:
                logger.exception(f"Error marking strategy as failed: {save_error}")
            
            return {
                'success': False,
                'reason': str(e),
            }


@shared_task(name='paper_trading.monitor_grid_orders')
def monitor_grid_orders(strategy_id: str) -> dict:
    """
    Monitor Grid strategy orders for fills and trigger rebalancing.
    
    This task runs periodically to:
    1. Check which grid orders have been filled
    2. Create sell orders above filled buy orders
    3. Track profit cycles
    4. Detect breakouts from grid range
    5. Update strategy progress
    
    Args:
        strategy_id: UUID of the StrategyRun
    
    Returns:
        Dictionary with monitoring results
    """
    logger.debug(f"Monitoring Grid orders for strategy {strategy_id}")
    
    try:
        # Get strategy run with related orders
        strategy_run = StrategyRun.objects.select_related('account').get(
            strategy_id=strategy_id
        )
        
        # Check if strategy is still running
        if strategy_run.status not in [StrategyStatus.RUNNING, StrategyStatus.PAUSED]:
            logger.debug(f"Strategy {strategy_id} is {strategy_run.status}, stopping monitoring")
            return {
                'success': True,
                'reason': 'Strategy no longer active',
                'continue_monitoring': False,
            }
        
        # Get all strategy orders
        strategy_orders = StrategyOrder.objects.filter(
            strategy_run=strategy_run
        ).select_related('order')
        
        # Parse Grid configuration
        config = strategy_run.config
        token_symbol = config.get('token_symbol')
        price_lower = Decimal(str(config.get('price_lower', '0')))
        price_upper = Decimal(str(config.get('price_upper', '0')))
        
        # Fetch current token price
        try:
            from paper_trading.services.price_feed_service import get_default_price_feed_service
            price_service = get_default_price_feed_service()
            current_price = price_service.get_token_price(
                address=config.get('token_address'),
                symbol=token_symbol
            )
        except Exception as price_error:
            logger.exception(f"Error fetching price for {token_symbol}: {price_error}")
            current_price = None
        
        # Check for filled orders
        filled_count = 0
        rebalance_needed = []
        
        for strategy_order in strategy_orders:
            order = strategy_order.order
            
            # Check if buy order was filled
            if order.side == 'BUY' and order.status == OrderStatus.FILLED:
                # Check if we need to create a sell order above this level
                # (Grid rebalancing logic)
                
                # Check if a corresponding sell order already exists
                has_sell_order = StrategyOrder.objects.filter(
                    strategy_run=strategy_run,
                    order__side='SELL',
                    order__token_symbol=token_symbol,
                    order__limit_price__gt=order.limit_price,
                ).exists()
                
                if not has_sell_order:
                    rebalance_needed.append({
                        'buy_order_id': str(order.order_id),
                        'buy_price': order.limit_price,
                        'amount': order.amount_usd,
                    })
                    filled_count += 1
        
        # Handle rebalancing
        if rebalance_needed:
            logger.info(
                f"Grid rebalancing needed for {len(rebalance_needed)} filled orders"
            )
            
            # Trigger rebalancing task
            rebalance_grid_orders.apply_async(
                args=[strategy_id, rebalance_needed]
            )
        
        # Check for breakout conditions
        breakout_detected = False
        breakout_direction = None
        
        if current_price:
            if current_price > price_upper:
                breakout_detected = True
                breakout_direction = 'UPWARD'
                logger.warning(
                    f"Grid breakout detected: {token_symbol} price ${current_price} "
                    f"above upper bound ${price_upper}"
                )
            elif current_price < price_lower:
                breakout_detected = True
                breakout_direction = 'DOWNWARD'
                logger.warning(
                    f"Grid breakout detected: {token_symbol} price ${current_price} "
                    f"below lower bound ${price_lower}"
                )
            
            if breakout_detected:
                # Handle breakout
                handle_grid_breakout.apply_async(
                    args=[strategy_id, breakout_direction, str(current_price)]
                )
        
        # Update progress
        total_orders = strategy_run.total_orders
        completed_orders = strategy_run.completed_orders
        
        if total_orders > 0:
            progress = (Decimal(str(completed_orders)) / Decimal(str(total_orders))) * Decimal('100')
            strategy_run.progress_percent = min(progress, Decimal('99.99'))  # Never 100% until complete
            strategy_run.save()
        
        # Schedule next monitoring run if strategy still active
        if strategy_run.status == StrategyStatus.RUNNING:
            monitor_grid_orders.apply_async(
                args=[strategy_id],
                countdown=60,  # Check every 60 seconds
            )
        
        return {
            'success': True,
            'strategy_id': strategy_id,
            'filled_orders': filled_count,
            'rebalance_needed': len(rebalance_needed),
            'breakout_detected': breakout_detected,
            'breakout_direction': breakout_direction,
            'current_price': str(current_price) if current_price else None,
            'continue_monitoring': strategy_run.status == StrategyStatus.RUNNING,
        }
        
    except StrategyRun.DoesNotExist:
        logger.error(f"Strategy {strategy_id} not found")
        return {
            'success': False,
            'reason': 'Strategy not found',
            'continue_monitoring': False,
        }
        
    except Exception as e:
        logger.exception(f"Error monitoring Grid orders: {e}")
        return {
            'success': False,
            'error': str(e),
            'continue_monitoring': True,  # Keep trying
        }


@shared_task(name='paper_trading.rebalance_grid_orders')
def rebalance_grid_orders(strategy_id: str, filled_orders: List[Dict[str, Any]]) -> dict:
    """
    Create sell orders for filled buy orders to complete profit cycles.
    
    When a buy order at a grid level is filled, this task creates a
    corresponding sell order at the next higher grid level to lock in profit.
    
    Args:
        strategy_id: UUID of the StrategyRun
        filled_orders: List of filled buy orders needing sell orders
    
    Returns:
        Dictionary with rebalancing results
    """
    logger.info(f"Rebalancing Grid for strategy {strategy_id}, {len(filled_orders)} orders")
    
    try:
        # Get strategy run
        strategy_run = StrategyRun.objects.select_related('account').get(
            strategy_id=strategy_id
        )
        
        # Parse Grid configuration
        config = strategy_run.config
        token_address = config.get('token_address')
        token_symbol = config.get('token_symbol')
        price_lower = Decimal(str(config.get('price_lower', '0')))
        price_upper = Decimal(str(config.get('price_upper', '0')))
        grid_levels = int(config.get('grid_levels', 0))
        
        # Calculate grid step
        grid_step = (price_upper - price_lower) / Decimal(str(grid_levels - 1))
        
        # Create sell orders
        sell_orders_created = []
        
        with transaction.atomic():
            # Lock the strategy run
            strategy_run = StrategyRun.objects.select_for_update().get(
                strategy_id=strategy_id
            )
            
            for filled_order_info in filled_orders:
                buy_price = Decimal(str(filled_order_info['buy_price']))
                amount_usd = Decimal(str(filled_order_info['amount']))
                
                # Calculate sell price (next grid level up)
                sell_price = buy_price + grid_step
                
                # Don't create sell order above upper bound
                if sell_price > price_upper:
                    logger.warning(
                        f"Sell price ${sell_price} exceeds upper bound ${price_upper}, skipping"
                    )
                    continue
                
                # Create limit sell order
                sell_order = PaperOrder.objects.create(
                    account=strategy_run.account,
                    order_type=OrderType.LIMIT,
                    side='SELL',
                    token_address=token_address,
                    token_symbol=token_symbol,
                    amount_usd=amount_usd,
                    limit_price=sell_price,
                    status=OrderStatus.PENDING,
                    notes=f"Grid Rebalance Sell @ ${sell_price} (bought @ ${buy_price})",
                )
                
                # Link to strategy
                StrategyOrder.objects.create(
                    strategy_run=strategy_run,
                    order=sell_order,
                    order_sequence=strategy_run.total_orders + 1,
                )
                
                # Update total orders count
                strategy_run.total_orders += 1
                
                sell_orders_created.append({
                    'order_id': str(sell_order.order_id),
                    'sell_price': str(sell_price),
                    'buy_price': str(buy_price),
                    'potential_profit_pct': str(((sell_price - buy_price) / buy_price) * Decimal('100')),
                })
                
                logger.info(
                    f"Created grid sell order at ${sell_price} "
                    f"(bought at ${buy_price}, +{((sell_price - buy_price) / buy_price) * 100:.2f}%)"
                )
            
            # Update strategy
            strategy_run.current_step = f"Rebalanced {len(sell_orders_created)} levels"
            strategy_run.save()
        
        logger.info(
            f"Grid rebalancing complete: created {len(sell_orders_created)} sell orders"
        )
        
        return {
            'success': True,
            'strategy_id': strategy_id,
            'sell_orders_created': len(sell_orders_created),
            'orders': sell_orders_created,
        }
        
    except StrategyRun.DoesNotExist:
        logger.error(f"Strategy {strategy_id} not found")
        return {
            'success': False,
            'reason': 'Strategy not found',
        }
        
    except Exception as e:
        logger.exception(f"Error rebalancing Grid orders: {e}")
        return {
            'success': False,
            'error': str(e),
        }


@shared_task(name='paper_trading.handle_grid_breakout')
def handle_grid_breakout(
    strategy_id: str,
    breakout_direction: str,
    current_price: str
) -> dict:
    """
    Handle breakout from grid trading range.
    
    When price breaks out of the configured grid range, this task
    determines the appropriate action based on strategy configuration:
    - Cancel unfilled orders
    - Optionally pause or stop the strategy
    - Send notifications
    - Update strategy status
    
    Args:
        strategy_id: UUID of the StrategyRun
        breakout_direction: 'UPWARD' or 'DOWNWARD'
        current_price: Current token price as string
    
    Returns:
        Dictionary with breakout handling results
    """
    logger.warning(
        f"Handling {breakout_direction} breakout for strategy {strategy_id} "
        f"at price ${current_price}"
    )
    
    try:
        # Get strategy run
        strategy_run = StrategyRun.objects.select_related('account').get(
            strategy_id=strategy_id
        )
        
        # Parse configuration
        config = strategy_run.config
        token_symbol = config.get('token_symbol')
        stop_on_breakout = config.get('stop_on_breakout', True)
        
        # Record breakout in strategy metadata
        breakout_info = {
            'detected_at': timezone.now().isoformat(),
            'direction': breakout_direction,
            'price': current_price,
        }
        
        # Update config with breakout info
        if 'breakouts' not in config:
            config['breakouts'] = []
        config['breakouts'].append(breakout_info)
        strategy_run.config = config
        
        # Determine action based on configuration
        if stop_on_breakout:
            # Cancel all pending orders
            pending_orders = PaperOrder.objects.filter(
                strategyorder__strategy_run=strategy_run,
                status=OrderStatus.PENDING,
            )
            
            cancelled_count = 0
            for order in pending_orders:
                order.status = OrderStatus.CANCELLED
                order.save()
                cancelled_count += 1
            
            logger.info(f"Cancelled {cancelled_count} pending orders due to breakout")
            
            # Pause or complete the strategy
            strategy_run.status = StrategyStatus.PAUSED
            strategy_run.current_step = (
                f"{breakout_direction.capitalize()} breakout detected at ${current_price}"
            )
            strategy_run.error_message = (
                f"Price broke {breakout_direction.lower()} out of grid range. "
                f"Strategy paused. Current price: ${current_price}"
            )
            strategy_run.paused_at = timezone.now()
            strategy_run.save()
            
            logger.warning(f"Strategy {strategy_id} paused due to {breakout_direction} breakout")
            
            # Send notification
            send_strategy_notification.apply_async(
                args=[strategy_id, 'breakout_paused']
            )
            
        else:
            # Just record the breakout but continue
            strategy_run.current_step = (
                f"{breakout_direction.capitalize()} breakout detected at ${current_price}, continuing..."
            )
            strategy_run.save()
            
            logger.info(f"Breakout recorded for strategy {strategy_id}, continuing execution")
        
        return {
            'success': True,
            'strategy_id': strategy_id,
            'breakout_direction': breakout_direction,
            'current_price': current_price,
            'action_taken': 'paused' if stop_on_breakout else 'recorded',
            'orders_cancelled': cancelled_count if stop_on_breakout else 0,
        }
        
    except StrategyRun.DoesNotExist:
        logger.error(f"Strategy {strategy_id} not found")
        return {
            'success': False,
            'reason': 'Strategy not found',
        }
        
    except Exception as e:
        logger.exception(f"Error handling Grid breakout: {e}")
        return {
            'success': False,
            'error': str(e),
        }


# =============================================================================
# STRATEGY MONITORING
# =============================================================================

@shared_task(name='paper_trading.monitor_active_strategies')
def monitor_active_strategies() -> dict:
    """
    Monitor all active strategies for health and progress.
    
    Runs every 60 seconds (configured in Celery beat schedule).
    Checks for stuck strategies, updates progress, and sends notifications.
    
    Returns:
        Dictionary with monitoring statistics
    """
    logger.debug("Monitoring active strategies...")
    
    try:
        # Get all running strategies
        active_strategies = StrategyRun.objects.filter(
            status=StrategyStatus.RUNNING
        ).select_related('account')
        
        monitored_count = 0
        issues_found = 0
        
        for strategy in active_strategies:
            try:
                # Check for stalled strategies
                if strategy.started_at:
                    time_since_start = timezone.now() - strategy.started_at
                    
                    # If DCA strategy has been running too long without progress
                    if strategy.strategy_type == StrategyType.DCA:
                        config = strategy.config
                        interval_hours = int(config.get('interval_hours', 24))
                        expected_duration = timedelta(
                            hours=interval_hours * int(config.get('num_intervals', 1))
                        )
                        
                        # Allow 2x expected duration before flagging as stuck
                        if time_since_start > (expected_duration * 2):
                            logger.warning(
                                f"Strategy {strategy.strategy_id} appears stuck: "
                                f"running for {time_since_start}, expected {expected_duration}"
                            )
                            issues_found += 1
                    
                    # If Grid strategy has no activity for too long
                    elif strategy.strategy_type == StrategyType.GRID:
                        # Check if any orders have been filled recently
                        recent_fills = StrategyOrder.objects.filter(
                            strategy_run=strategy,
                            order__status=OrderStatus.FILLED,
                            order__filled_at__gte=timezone.now() - timedelta(hours=24),
                        ).count()
                        
                        if recent_fills == 0 and time_since_start > timedelta(days=1):
                            logger.warning(
                                f"Grid strategy {strategy.strategy_id} has no recent fills "
                                f"in 24 hours"
                            )
                            issues_found += 1
                
                monitored_count += 1
                
            except Exception as e:
                logger.exception(f"Error monitoring strategy {strategy.strategy_id}: {e}")
                issues_found += 1
        
        logger.info(
            f"Strategy monitoring complete: {monitored_count} active, {issues_found} issues"
        )
        
        return {
            'success': True,
            'monitored': monitored_count,
            'issues': issues_found,
        }
        
    except Exception as e:
        logger.exception(f"Error in strategy monitoring: {e}")
        return {
            'success': False,
            'error': str(e),
        }


# =============================================================================
# STRATEGY NOTIFICATIONS
# =============================================================================

@shared_task(name='paper_trading.send_strategy_notification')
def send_strategy_notification(strategy_id: str, event_type: str) -> dict:
    """
    Send WebSocket notification for strategy events.
    
    Args:
        strategy_id: UUID of the StrategyRun
        event_type: Type of event ('started', 'completed', 'failed', 'paused', 
                                   'cancelled', 'breakout_paused')
    
    Returns:
        Dictionary with notification status
    """
    logger.info(f"Sending strategy notification: {event_type} for {strategy_id}")
    
    try:
        strategy = StrategyRun.objects.select_related('account').get(
            strategy_id=strategy_id
        )
        
        # Prepare notification message
        message = {
            'type': 'strategy_update',
            'event': event_type,
            'strategy_id': str(strategy.strategy_id),
            'strategy_type': strategy.strategy_type,
            'status': strategy.status,
            'progress_percent': str(strategy.progress_percent),
            'current_step': strategy.current_step,
            'completed_orders': strategy.completed_orders,
            'total_orders': strategy.total_orders,
            'error_message': strategy.error_message,
        }
        
        # Send via WebSocket
        from paper_trading.services.websocket_service import send_paper_trading_update
        
        send_paper_trading_update(
            account_id=strategy.account.account_id,
            message=message,
        )
        
        logger.info(f"Strategy notification sent for {strategy_id}")
        
        return {
            'success': True,
            'strategy_id': strategy_id,
            'event_type': event_type,
        }
        
    except StrategyRun.DoesNotExist:
        logger.error(f"Strategy {strategy_id} not found for notification")
        return {
            'success': False,
            'reason': 'Strategy not found',
        }
        
    except Exception as e:
        logger.exception(f"Error sending strategy notification: {e}")
        return {
            'success': False,
            'error': str(e),
        }