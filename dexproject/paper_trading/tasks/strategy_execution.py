"""
Strategy Execution Tasks - Celery Background Tasks

Handles background execution of trading strategies:
- DCA interval execution
- Strategy monitoring and health checks
- Progress updates and notifications
- Strategy completion handling

Phase 7B - Day 2: Strategy Execution Tasks

File: dexproject/paper_trading/tasks/strategy_execution.py
"""

import logging
from decimal import Decimal
from typing import Optional
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django.db import transaction

from paper_trading.models import StrategyRun, StrategyOrder, PaperOrder, PaperTradingAccount
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
                        expected_duration = timedelta(hours=interval_hours * int(config.get('num_intervals', 1)))
                        
                        # Allow 2x expected duration before flagging as stuck
                        if time_since_start > (expected_duration * 2):
                            logger.warning(
                                f"Strategy {strategy.strategy_id} appears stuck: "
                                f"running for {time_since_start}, expected {expected_duration}"
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
        event_type: Type of event ('started', 'completed', 'failed', 'paused', 'cancelled')
    
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