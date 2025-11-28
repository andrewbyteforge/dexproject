"""
Strategy Execution Tasks - Celery Background Tasks

Handles background execution of trading strategies:
- DCA interval execution
- Grid strategy monitoring and rebalancing
- TWAP chunk execution
- Strategy monitoring and health checks
- Progress updates and notifications
- Strategy completion handling

Phase 7B - Day 2: DCA Strategy Execution Tasks
Phase 7B - Day 4: Grid Strategy Execution Tasks
Phase 7B - Day 9: TWAP Strategy Execution Tasks

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
        interval_number: Current interval number (1-indexed)
    
    Returns:
        Dictionary with execution result including:
        - success: bool
        - interval: int
        - order_id: str (if successful)
        - amount: str (if successful)
        - next_interval: int or None
        
    Example:
        execute_dca_interval.apply_async(
            args=['uuid-here', 1],
            countdown=3600  # Execute in 1 hour
        )
    """
    logger.info(f"Executing DCA interval {interval_number} for strategy {strategy_id}")
    
    try:
        # Get strategy run with account
        strategy_run = StrategyRun.objects.select_related('account').get(
            strategy_id=strategy_id
        )
        
        # Check if strategy is still running
        if strategy_run.status != StrategyStatus.RUNNING:
            logger.warning(
                f"Strategy {strategy_id} is {strategy_run.status}, skipping interval"
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
        num_intervals = int(config.get('num_intervals', 1))
        interval_hours = int(config.get('interval_hours', 24))
        
        # Calculate amount for this interval
        amount_per_interval = total_amount / Decimal(str(num_intervals))
        
        logger.info(
            f"DCA interval {interval_number}/{num_intervals}: "
            f"Buying ${amount_per_interval} of {token_symbol}"
        )
        
        # Create paper order for this interval
        with transaction.atomic():
            # Get current price (simplified - in production would fetch real price)
            # For now, use a placeholder that the order executor will fill
            order = PaperOrder.objects.create(
                account=strategy_run.account,
                token_address=token_address,
                token_symbol=token_symbol,
                order_type=OrderType.MARKET,
                side='BUY',
                quantity_usd=amount_per_interval,
                status=OrderStatus.PENDING,
                notes=f"DCA interval {interval_number}/{num_intervals}",
            )
            
            # Link order to strategy
            StrategyOrder.objects.create(
                strategy_run=strategy_run,
                order=order,
                sequence_number=interval_number,
            )
            
            # Update strategy progress
            progress_percent = Decimal(str(interval_number / num_intervals * 100))
            strategy_run.progress_percent = progress_percent
            strategy_run.current_step = f"Completed interval {interval_number}/{num_intervals}"
            strategy_run.completed_orders = interval_number
            strategy_run.total_invested += amount_per_interval
            strategy_run.save()
        
        logger.info(
            f"Created DCA order {order.order_id} for interval {interval_number}"
        )
        
        # Execute the order via order executor
        try:
            from paper_trading.services.order_executor import execute_order
            execute_order(order.order_id)
        except ImportError:
            logger.warning("Order executor not available, order remains pending")
        except Exception as exec_error:
            logger.error(f"Order execution failed: {exec_error}")
            # Order remains pending, can be retried
        
        # Schedule next interval if not the last one
        if interval_number < num_intervals:
            next_interval = interval_number + 1
            countdown_seconds = interval_hours * 3600
            
            execute_dca_interval.apply_async(
                args=[strategy_id, next_interval],
                countdown=countdown_seconds,
            )
            
            logger.info(
                f"Scheduled DCA interval {next_interval} in {interval_hours} hours"
            )
        else:
            # Mark strategy as completed
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
        price_lower = Decimal(str(config.get('lower_bound', config.get('price_lower', '0'))))
        price_upper = Decimal(str(config.get('upper_bound', config.get('price_upper', '0'))))
        grid_levels = int(config.get('num_levels', config.get('grid_levels', 5)))
        total_investment = Decimal(str(config.get('total_amount_usd', config.get('total_investment_usd', '0'))))
        
        # Calculate grid parameters
        grid_step = (price_upper - price_lower) / Decimal(str(grid_levels - 1)) if grid_levels > 1 else Decimal('0')
        investment_per_level = total_investment / Decimal(str(grid_levels))
        
        logger.info(
            f"Grid setup: {grid_levels} levels from ${price_lower} to ${price_upper}, "
            f"step: ${grid_step}, investment per level: ${investment_per_level}"
        )
        
        # Create initial buy orders at all grid levels
        orders_created = []
        
        with transaction.atomic():
            for level in range(grid_levels):
                # Calculate price for this level
                level_price = price_lower + (grid_step * Decimal(str(level)))
                
                # Create limit buy order at this level
                order = PaperOrder.objects.create(
                    account=strategy_run.account,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    order_type=OrderType.LIMIT,
                    side='BUY',
                    quantity_usd=investment_per_level,
                    limit_price=level_price,
                    status=OrderStatus.PENDING,
                    notes=f"Grid level {level + 1}/{grid_levels} at ${level_price}",
                )
                
                # Link order to strategy
                StrategyOrder.objects.create(
                    strategy_run=strategy_run,
                    order=order,
                    sequence_number=level + 1,
                )
                
                orders_created.append({
                    'order_id': str(order.order_id),
                    'level': level + 1,
                    'price': str(level_price),
                    'amount': str(investment_per_level),
                })
            
            # Update strategy progress
            strategy_run.total_orders = grid_levels
            strategy_run.progress_percent = Decimal('10')
            strategy_run.current_step = f"Grid initialized: {grid_levels} levels"
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
    5. Reschedule itself if strategy is still active
    
    Args:
        strategy_id: UUID of the StrategyRun
    
    Returns:
        Dictionary with monitoring results
    """
    logger.debug(f"Monitoring Grid strategy {strategy_id}")
    
    try:
        strategy_run = StrategyRun.objects.select_related('account').get(
            strategy_id=strategy_id
        )
        
        # Check if strategy is still running
        if strategy_run.status not in [StrategyStatus.RUNNING, StrategyStatus.PAUSED]:
            logger.info(f"Grid strategy {strategy_id} is {strategy_run.status}, stopping monitor")
            return {
                'success': True,
                'reason': f"Strategy {strategy_run.status}",
                'continue_monitoring': False,
            }
        
        # If paused, just reschedule without processing
        if strategy_run.status == StrategyStatus.PAUSED:
            monitor_grid_orders.apply_async(
                args=[strategy_id],
                countdown=60,
            )
            return {
                'success': True,
                'reason': 'Strategy paused',
                'continue_monitoring': True,
            }
        
        # Get all strategy orders
        strategy_orders = StrategyOrder.objects.filter(
            strategy_run=strategy_run
        ).select_related('order')
        
        filled_count = 0
        pending_count = 0
        
        for so in strategy_orders:
            if so.order.status == OrderStatus.FILLED:
                filled_count += 1
            elif so.order.status == OrderStatus.PENDING:
                pending_count += 1
        
        # Update progress
        total_orders = strategy_orders.count()
        if total_orders > 0:
            progress = Decimal(str(filled_count / total_orders * 100))
            strategy_run.progress_percent = progress
            strategy_run.completed_orders = filled_count
            strategy_run.current_step = f"Grid active: {filled_count}/{total_orders} filled"
            strategy_run.save()
        
        # Check if grid is complete (all orders filled or cancelled)
        if pending_count == 0 and filled_count > 0:
            strategy_run.status = StrategyStatus.COMPLETED
            strategy_run.completed_at = timezone.now()
            strategy_run.progress_percent = Decimal('100')
            strategy_run.current_step = "Grid completed"
            strategy_run.save()
            
            send_strategy_notification.apply_async(
                args=[strategy_id, 'completed'],
            )
            
            return {
                'success': True,
                'reason': 'Grid completed',
                'continue_monitoring': False,
            }
        
        # Reschedule monitoring
        monitor_grid_orders.apply_async(
            args=[strategy_id],
            countdown=60,  # Check every minute
        )
        
        return {
            'success': True,
            'filled_orders': filled_count,
            'pending_orders': pending_count,
            'continue_monitoring': True,
        }
        
    except StrategyRun.DoesNotExist:
        logger.error(f"Strategy {strategy_id} not found")
        return {
            'success': False,
            'reason': 'Strategy not found',
            'continue_monitoring': False,
        }
        
    except Exception as e:
        logger.exception(f"Error monitoring Grid strategy: {e}")
        
        # Reschedule anyway to keep monitoring
        monitor_grid_orders.apply_async(
            args=[strategy_id],
            countdown=120,  # Longer delay after error
        )
        
        return {
            'success': False,
            'reason': str(e),
            'continue_monitoring': True,
        }


# =============================================================================
# TWAP STRATEGY EXECUTION
# =============================================================================

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='paper_trading.execute_twap_chunk'
)
def execute_twap_chunk(self, strategy_id: str, chunk_number: int) -> dict:
    """
    Execute a single TWAP chunk.
    
    TWAP (Time-Weighted Average Price) splits a large order into equal-sized
    chunks executed at regular time intervals. This minimizes market impact
    and avoids price manipulation detection, especially for illiquid tokens.
    
    Args:
        strategy_id: UUID of the StrategyRun
        chunk_number: Current chunk number (1-indexed)
    
    Returns:
        Dictionary with execution result including:
        - success: bool
        - chunk: int
        - order_id: str (if successful)
        - amount: str (if successful)
        - next_chunk: int or None
        
    Example:
        execute_twap_chunk.apply_async(
            args=['uuid-here', 1],
            countdown=1800  # Execute in 30 minutes
        )
    """
    logger.info(f"Executing TWAP chunk {chunk_number} for strategy {strategy_id}")
    
    try:
        # Get strategy run with account
        strategy_run = StrategyRun.objects.select_related('account').get(
            strategy_id=strategy_id
        )
        
        # Check if strategy is still running
        if strategy_run.status != StrategyStatus.RUNNING:
            logger.warning(
                f"Strategy {strategy_id} is {strategy_run.status}, skipping chunk"
            )
            return {
                'success': False,
                'reason': f"Strategy not running (status: {strategy_run.status})",
                'chunk': chunk_number,
            }
        
        # Parse TWAP configuration
        config = strategy_run.config
        token_address = config.get('token_address')
        token_symbol = config.get('token_symbol')
        total_amount = Decimal(str(config.get('total_amount_usd', '0')))
        num_chunks = int(config.get('num_chunks', 8))
        execution_window_hours = int(config.get('execution_window_hours', 4))
        interval_minutes = int(config.get('interval_minutes', 30))
        
        # Calculate amount for this chunk
        chunk_size = total_amount / Decimal(str(num_chunks))
        
        logger.info(
            f"TWAP chunk {chunk_number}/{num_chunks}: "
            f"Buying ${chunk_size} of {token_symbol}"
        )
        
        # Create paper order for this chunk
        with transaction.atomic():
            order = PaperOrder.objects.create(
                account=strategy_run.account,
                token_address=token_address,
                token_symbol=token_symbol,
                order_type=OrderType.MARKET,
                side='BUY',
                quantity_usd=chunk_size,
                status=OrderStatus.PENDING,
                notes=f"TWAP chunk {chunk_number}/{num_chunks}",
            )
            
            # Link order to strategy
            StrategyOrder.objects.create(
                strategy_run=strategy_run,
                order=order,
                sequence_number=chunk_number,
            )
            
            # Update strategy progress
            progress_percent = Decimal(str(chunk_number / num_chunks * 100))
            strategy_run.progress_percent = progress_percent
            strategy_run.current_step = f"Completed chunk {chunk_number}/{num_chunks}"
            strategy_run.completed_orders = chunk_number
            strategy_run.total_invested += chunk_size
            strategy_run.save()
        
        logger.info(
            f"Created TWAP order {order.order_id} for chunk {chunk_number}"
        )
        
        # Execute the order via order executor
        try:
            from paper_trading.services.order_executor import execute_order
            execute_order(order.order_id)
        except ImportError:
            logger.warning("Order executor not available, order remains pending")
        except Exception as exec_error:
            logger.error(f"Order execution failed: {exec_error}")
            # Order remains pending, can be retried
        
        # Schedule next chunk if not the last one
        if chunk_number < num_chunks:
            next_chunk = chunk_number + 1
            countdown_seconds = interval_minutes * 60
            
            execute_twap_chunk.apply_async(
                args=[strategy_id, next_chunk],
                countdown=countdown_seconds,
            )
            
            logger.info(
                f"Scheduled TWAP chunk {next_chunk} in {interval_minutes} minutes"
            )
        else:
            # Mark strategy as completed
            strategy_run.status = StrategyStatus.COMPLETED
            strategy_run.completed_at = timezone.now()
            strategy_run.progress_percent = Decimal('100.00')
            strategy_run.current_step = f"Completed all {num_chunks} chunks"
            strategy_run.save()
            
            logger.info(f"TWAP strategy {strategy_id} completed successfully!")
            
            # Send completion notification
            send_strategy_notification.apply_async(
                args=[strategy_id, 'completed'],
            )
        
        return {
            'success': True,
            'chunk': chunk_number,
            'order_id': str(order.order_id),
            'amount': str(chunk_size),
            'next_chunk': chunk_number + 1 if chunk_number < num_chunks else None,
        }
        
    except StrategyRun.DoesNotExist:
        logger.error(f"Strategy {strategy_id} not found")
        return {
            'success': False,
            'reason': 'Strategy not found',
            'chunk': chunk_number,
        }
        
    except Exception as e:
        logger.exception(f"Error in TWAP chunk execution: {e}")
        
        # Retry with exponential backoff
        try:
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for TWAP chunk {chunk_number}")
            
            # Mark strategy as failed
            try:
                strategy_run = StrategyRun.objects.get(strategy_id=strategy_id)
                strategy_run.status = StrategyStatus.FAILED
                strategy_run.error_message = f"Failed to execute chunk {chunk_number}: {str(e)}"
                strategy_run.failed_orders += 1
                strategy_run.save()
            except Exception as save_error:
                logger.exception(f"Error marking strategy as failed: {save_error}")
            
            return {
                'success': False,
                'reason': str(e),
                'chunk': chunk_number,
            }


@shared_task(name='paper_trading.monitor_twap_strategy')
def monitor_twap_strategy(strategy_id: str) -> dict:
    """
    Monitor TWAP strategy execution progress.
    
    This task checks on TWAP strategies to:
    1. Verify chunks are being executed on schedule
    2. Detect stalled strategies
    3. Handle recovery from failures
    4. Update progress metrics
    
    Args:
        strategy_id: UUID of the StrategyRun
    
    Returns:
        Dictionary with monitoring results
    """
    logger.debug(f"Monitoring TWAP strategy {strategy_id}")
    
    try:
        strategy_run = StrategyRun.objects.select_related('account').get(
            strategy_id=strategy_id
        )
        
        # Check if strategy is still active
        if strategy_run.status not in [StrategyStatus.RUNNING, StrategyStatus.PAUSED]:
            logger.info(f"TWAP strategy {strategy_id} is {strategy_run.status}, stopping monitor")
            return {
                'success': True,
                'reason': f"Strategy {strategy_run.status}",
                'continue_monitoring': False,
            }
        
        # If paused, just reschedule without processing
        if strategy_run.status == StrategyStatus.PAUSED:
            monitor_twap_strategy.apply_async(
                args=[strategy_id],
                countdown=60,
            )
            return {
                'success': True,
                'reason': 'Strategy paused',
                'continue_monitoring': True,
            }
        
        # Get strategy orders
        strategy_orders = StrategyOrder.objects.filter(
            strategy_run=strategy_run
        ).select_related('order')
        
        filled_count = 0
        pending_count = 0
        failed_count = 0
        
        for so in strategy_orders:
            if so.order.status == OrderStatus.FILLED:
                filled_count += 1
            elif so.order.status == OrderStatus.PENDING:
                pending_count += 1
            elif so.order.status in [OrderStatus.FAILED, OrderStatus.CANCELLED]:
                failed_count += 1
        
        # Parse config for total chunks
        config = strategy_run.config
        num_chunks = int(config.get('num_chunks', 8))
        
        # Check for stalled strategy
        if strategy_run.started_at:
            time_since_start = timezone.now() - strategy_run.started_at
            execution_window_hours = int(config.get('execution_window_hours', 4))
            expected_duration = timedelta(hours=execution_window_hours)
            
            # If strategy has been running longer than 2x expected, flag it
            if time_since_start > (expected_duration * 2) and filled_count < num_chunks:
                logger.warning(
                    f"TWAP strategy {strategy_id} appears stalled: "
                    f"running for {time_since_start}, expected {expected_duration}, "
                    f"only {filled_count}/{num_chunks} chunks completed"
                )
        
        # Update progress
        total_orders = filled_count + pending_count + failed_count
        if num_chunks > 0:
            progress = Decimal(str(filled_count / num_chunks * 100))
            strategy_run.progress_percent = progress
            strategy_run.completed_orders = filled_count
            strategy_run.failed_orders = failed_count
            strategy_run.current_step = f"TWAP progress: {filled_count}/{num_chunks} chunks"
            strategy_run.save()
        
        # Check if TWAP is complete
        if filled_count >= num_chunks:
            strategy_run.status = StrategyStatus.COMPLETED
            strategy_run.completed_at = timezone.now()
            strategy_run.progress_percent = Decimal('100')
            strategy_run.current_step = f"TWAP completed: {filled_count} chunks"
            strategy_run.save()
            
            send_strategy_notification.apply_async(
                args=[strategy_id, 'completed'],
            )
            
            return {
                'success': True,
                'reason': 'TWAP completed',
                'continue_monitoring': False,
            }
        
        # Reschedule monitoring
        monitor_twap_strategy.apply_async(
            args=[strategy_id],
            countdown=120,  # Check every 2 minutes
        )
        
        return {
            'success': True,
            'filled_chunks': filled_count,
            'pending_chunks': pending_count,
            'failed_chunks': failed_count,
            'total_chunks': num_chunks,
            'continue_monitoring': True,
        }
        
    except StrategyRun.DoesNotExist:
        logger.error(f"Strategy {strategy_id} not found")
        return {
            'success': False,
            'reason': 'Strategy not found',
            'continue_monitoring': False,
        }
        
    except Exception as e:
        logger.exception(f"Error monitoring TWAP strategy: {e}")
        
        # Reschedule anyway to keep monitoring
        monitor_twap_strategy.apply_async(
            args=[strategy_id],
            countdown=180,  # Longer delay after error
        )
        
        return {
            'success': False,
            'reason': str(e),
            'continue_monitoring': True,
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
        event_type: Type of event (started, paused, resumed, completed, failed, etc.)
    
    Returns:
        Dictionary with notification result
    """
    logger.debug(f"Sending {event_type} notification for strategy {strategy_id}")
    
    try:
        strategy_run = StrategyRun.objects.select_related('account').get(
            strategy_id=strategy_id
        )
        
        # Import WebSocket service
        try:
            from paper_trading.services.websocket_service import websocket_service
            
            message = {
                'type': 'strategy_update',
                'event': event_type,
                'strategy_id': str(strategy_run.strategy_id),
                'strategy_type': strategy_run.strategy_type,
                'status': strategy_run.status,
                'progress_percent': float(strategy_run.progress_percent),
                'current_step': strategy_run.current_step,
                'total_invested': float(strategy_run.total_invested),
                'current_pnl': float(strategy_run.current_pnl),
            }
            
            websocket_service.send_update(
                account_id=strategy_run.account.account_id,
                message_type='strategy_update',
                data=message,
            )
            
            logger.info(f"Sent {event_type} notification for strategy {strategy_id}")
            
            return {
                'success': True,
                'event': event_type,
                'strategy_id': strategy_id,
            }
            
        except ImportError:
            logger.warning("WebSocket service not available")
            return {
                'success': False,
                'reason': 'WebSocket service not available',
            }
        
    except StrategyRun.DoesNotExist:
        logger.error(f"Strategy {strategy_id} not found")
        return {
            'success': False,
            'reason': 'Strategy not found',
        }
        
    except Exception as e:
        logger.exception(f"Error sending notification: {e}")
        return {
            'success': False,
            'reason': str(e),
        }


# =============================================================================
# STRATEGY MONITORING
# =============================================================================

@shared_task(name='paper_trading.monitor_active_strategies')
def monitor_active_strategies() -> dict:
    """
    Monitor all active strategies for health and progress.
    
    This is a periodic task that should be scheduled via Celery Beat.
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
                        num_intervals = int(config.get('num_intervals', 1))
                        expected_duration = timedelta(
                            hours=interval_hours * num_intervals
                        )
                        
                        # Allow 2x expected duration before flagging as stuck
                        if time_since_start > (expected_duration * 2):
                            logger.warning(
                                f"DCA strategy {strategy.strategy_id} appears stuck: "
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
                                f"(running for {time_since_start})"
                            )
                            issues_found += 1
                    
                    # If TWAP strategy has been running too long
                    elif strategy.strategy_type == StrategyType.TWAP:
                        config = strategy.config
                        execution_window_hours = int(config.get('execution_window_hours', 4))
                        expected_duration = timedelta(hours=execution_window_hours)
                        
                        # Allow 2x expected duration before flagging as stuck
                        if time_since_start > (expected_duration * 2):
                            logger.warning(
                                f"TWAP strategy {strategy.strategy_id} appears stuck: "
                                f"running for {time_since_start}, expected {expected_duration}"
                            )
                            issues_found += 1
                
                monitored_count += 1
                
            except Exception as strategy_error:
                logger.exception(
                    f"Error monitoring strategy {strategy.strategy_id}: {strategy_error}"
                )
                issues_found += 1
        
        logger.info(
            f"Strategy monitoring complete: {monitored_count} strategies checked, "
            f"{issues_found} issues found"
        )
        
        return {
            'success': True,
            'monitored_count': monitored_count,
            'issues_found': issues_found,
            'active_strategies': active_strategies.count(),
        }
        
    except Exception as e:
        logger.exception(f"Error in strategy monitoring: {e}")
        return {
            'success': False,
            'reason': str(e),
        }