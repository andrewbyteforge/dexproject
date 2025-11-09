"""
Paper Trading Order Monitoring Task - Phase 7A Day 3

This module provides the Celery task for monitoring and executing paper trading orders.
Runs periodically to check order conditions and trigger executions.

Features:
- Monitors all active orders every 30 seconds
- Updates trailing stop prices automatically
- Triggers orders when price conditions are met
- Handles order expiration
- Sends real-time WebSocket notifications

File: paper_trading/tasks/order_monitoring.py
"""

import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache

# Import models
from paper_trading.models import (
    PaperTradingAccount,
    PaperOrder,
    PaperTrade,
)

# Import constants for field names and statuses
from paper_trading.constants import (
    OrderType,
    OrderStatus,
    OrderFields,
)

# Import services
from paper_trading.services.order_manager import OrderManager
from paper_trading.services.price_feed_service import PriceFeedService
from paper_trading.services.websocket_service import send_order_update

logger = logging.getLogger(__name__)


# =============================================================================
# ORDER MONITORING TASK
# =============================================================================


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue='paper_trading'
)
def monitor_orders_task(
    self,
    chain_id: int = 84532,
    batch_size: int = 50
) -> Dict[str, Any]:
    """
    Monitor all active orders and execute when conditions are met.

    This task runs periodically (every 30 seconds via Celery Beat) to:
    1. Check all active orders for trigger conditions
    2. Update trailing stop prices based on current market prices
    3. Execute orders when trigger prices are hit
    4. Mark orders as expired if past expiration time
    5. Send WebSocket notifications for order status changes

    Args:
        chain_id: Blockchain chain ID (default: 84532 = Base Sepolia)
        batch_size: Maximum number of orders to process per run

    Returns:
        Dict with monitoring statistics
    """
    logger.info("[ORDER_MONITOR] Starting order monitoring cycle")
    
    try:
        # Initialize price feed service
        price_service = PriceFeedService(chain_id=chain_id)
        
        # Tracking statistics
        stats = {
            'orders_checked': 0,
            'trailing_stops_updated': 0,
            'orders_triggered': 0,
            'orders_executed': 0,
            'orders_expired': 0,
            'orders_failed': 0,
            'errors': []
        }
        
        # Get all active orders (PENDING, TRIGGERED, PARTIALLY_FILLED)
        active_orders = PaperOrder.objects.filter(
            status__in=[
                OrderStatus.PENDING,
                OrderStatus.TRIGGERED,
                OrderStatus.PARTIALLY_FILLED
            ]
        ).select_related('account').order_by('created_at')[:batch_size]
        
        if not active_orders.exists():
            logger.info("[ORDER_MONITOR] No active orders to monitor")
            return {
                'success': True,
                'message': 'No active orders',
                **stats
            }
        
        total_orders = active_orders.count()
        logger.info(f"[ORDER_MONITOR] Monitoring {total_orders} active orders")
        
        # Collect unique token addresses for bulk price fetching
        token_addresses = list(set(order.token_address for order in active_orders))
        logger.info(f"[ORDER_MONITOR] Fetching prices for {len(token_addresses)} unique tokens")
        
        # Fetch all prices in bulk (efficient)
        token_prices: Dict[str, Decimal] = {}
        try:
            for token_address in token_addresses:
                price_data = price_service.get_token_price(token_address)
                if price_data and price_data.get('price_usd'):
                    token_prices[token_address.lower()] = Decimal(str(price_data['price_usd']))
                    logger.debug(
                        f"[ORDER_MONITOR] Price for {token_address[:10]}...: "
                        f"${price_data['price_usd']}"
                    )
        except Exception as price_error:
            logger.error(f"[ORDER_MONITOR] Error fetching prices: {price_error}", exc_info=True)
            stats['errors'].append(f"Price fetch error: {str(price_error)}")
        
        if not token_prices:
            logger.warning("[ORDER_MONITOR] No prices fetched, aborting monitoring cycle")
            return {
                'success': False,
                'error': 'Failed to fetch any token prices',
                **stats
            }
        
        # Process each order
        for order in active_orders:
            try:
                stats['orders_checked'] += 1
                
                # Get current price for this token
                token_addr = order.token_address.lower()
                if token_addr not in token_prices:
                    logger.debug(
                        f"[ORDER_MONITOR] No price for order {order.order_id}, skipping"
                    )
                    continue
                
                current_price = token_prices[token_addr]
                logger.debug(
                    f"[ORDER_MONITOR] Processing order {order.order_id} "
                    f"({order.order_type}) at price ${current_price}"
                )
                
                # Check if order has expired
                if order.expires_at and timezone.now() >= order.expires_at:
                    logger.info(
                        f"[ORDER_MONITOR] Order {order.order_id} expired, cancelling"
                    )
                    if _mark_order_expired(order):
                        stats['orders_expired'] += 1
                        _send_order_notification(order, 'expired')
                    continue
                
                # Handle order based on type
                order_manager = OrderManager(order.account)
                
                if order.order_type == OrderType.TRAILING_STOP:
                    # Update trailing stop price
                    if _update_trailing_stop(order, current_price):
                        stats['trailing_stops_updated'] += 1
                        logger.debug(
                            f"[ORDER_MONITOR] Updated trailing stop for {order.order_id}: "
                            f"${order.current_stop_price}"
                        )
                
                # Check if order should be triggered
                should_trigger, trigger_reason = _check_trigger_condition(
                    order, current_price
                )
                
                if should_trigger:
                    logger.info(
                        f"[ORDER_MONITOR] Order {order.order_id} triggered: {trigger_reason}"
                    )
                    stats['orders_triggered'] += 1
                    
                    # Execute the order
                    if _execute_order(order_manager, order, current_price):
                        stats['orders_executed'] += 1
                        _send_order_notification(order, 'executed')
                        logger.info(
                            f"[ORDER_MONITOR] ✅ Successfully executed order {order.order_id}"
                        )
                    else:
                        stats['orders_failed'] += 1
                        logger.warning(
                            f"[ORDER_MONITOR] ❌ Failed to execute order {order.order_id}"
                        )
            
            except Exception as order_error:
                logger.error(
                    f"[ORDER_MONITOR] Error processing order {order.order_id}: {order_error}",
                    exc_info=True
                )
                stats['errors'].append(
                    f"Order {order.order_id}: {str(order_error)}"
                )
                stats['orders_failed'] += 1
        
        # Log summary
        logger.info(
            f"[ORDER_MONITOR] ✅ Monitoring cycle complete. "
            f"Checked: {stats['orders_checked']}, "
            f"Triggered: {stats['orders_triggered']}, "
            f"Executed: {stats['orders_executed']}, "
            f"Failed: {stats['orders_failed']}, "
            f"Expired: {stats['orders_expired']}, "
            f"Trailing Updates: {stats['trailing_stops_updated']}"
        )
        
        return {
            'success': True,
            'chain_id': chain_id,
            **stats
        }
    
    except Exception as e:
        logger.error(f"[ORDER_MONITOR] Fatal error in monitoring task: {e}", exc_info=True)
        
        # Retry if appropriate
        if self.request.retries < self.max_retries:
            retry_delay = 30 * (2 ** self.request.retries)
            logger.info(f"[ORDER_MONITOR] Retrying in {retry_delay}s...")
            raise self.retry(countdown=retry_delay, exc=e)
        
        return {
            'success': False,
            'error': str(e),
            'orders_checked': 0
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _check_trigger_condition(
    order: PaperOrder,
    current_price: Decimal
) -> tuple[bool, str]:
    """
    Check if an order should be triggered based on current price.
    
    Args:
        order: The order to check
        current_price: Current market price of the token
        
    Returns:
        Tuple of (should_trigger: bool, reason: str)
    """
    try:
        # LIMIT_BUY: Trigger when price <= limit_price
        if order.order_type == OrderType.LIMIT_BUY:
            if current_price <= order.limit_price:
                return True, f"Price ${current_price} <= limit ${order.limit_price}"
        
        # LIMIT_SELL: Trigger when price >= limit_price
        elif order.order_type == OrderType.LIMIT_SELL:
            if current_price >= order.limit_price:
                return True, f"Price ${current_price} >= limit ${order.limit_price}"
        
        # STOP_LIMIT_BUY: First check stop_price, then limit_price
        elif order.order_type == OrderType.STOP_LIMIT_BUY:
            if order.status == OrderStatus.PENDING:
                # Check if stop price is hit (price >= stop_price)
                if current_price >= order.stop_price:
                    # Mark as TRIGGERED
                    with transaction.atomic():
                        order.status = OrderStatus.TRIGGERED
                        order.triggered_at = timezone.now()
                        order.save()
                    return False, f"Stop triggered at ${current_price}"
            elif order.status == OrderStatus.TRIGGERED:
                # Now check if limit price is favorable (price <= limit_price)
                if current_price <= order.limit_price:
                    return True, f"Limit reached: ${current_price} <= ${order.limit_price}"
        
        # STOP_LIMIT_SELL: First check stop_price, then limit_price
        elif order.order_type == OrderType.STOP_LIMIT_SELL:
            if order.status == OrderStatus.PENDING:
                # Check if stop price is hit (price <= stop_price)
                if current_price <= order.stop_price:
                    # Mark as TRIGGERED
                    with transaction.atomic():
                        order.status = OrderStatus.TRIGGERED
                        order.triggered_at = timezone.now()
                        order.save()
                    return False, f"Stop triggered at ${current_price}"
            elif order.status == OrderStatus.TRIGGERED:
                # Now check if limit price is favorable (price >= limit_price)
                if current_price >= order.limit_price:
                    return True, f"Limit reached: ${current_price} >= ${order.limit_price}"
        
        # TRAILING_STOP: Check if current stop price is hit
        elif order.order_type == OrderType.TRAILING_STOP:
            if order.current_stop_price and current_price <= order.current_stop_price:
                return True, f"Price ${current_price} <= stop ${order.current_stop_price}"
        
        return False, "Conditions not met"
    
    except Exception as e:
        logger.error(f"Error checking trigger condition: {e}", exc_info=True)
        return False, f"Error: {str(e)}"


def _update_trailing_stop(
    order: PaperOrder,
    current_price: Decimal
) -> bool:
    """
    Update trailing stop price if current price is higher.
    
    For trailing stop orders, we track the highest price seen and calculate
    the stop price as: highest_price - trail_amount (or highest_price * (1 - trail_percent))
    
    Args:
        order: The trailing stop order
        current_price: Current market price
        
    Returns:
        True if stop price was updated, False otherwise
    """
    try:
        # Initialize highest_price if not set
        if not order.highest_price:
            order.highest_price = current_price
        
        # Update highest price if current price is higher
        if current_price > order.highest_price:
            order.highest_price = current_price
            
            # Calculate new stop price
            if order.trail_percent:
                # Percentage-based trailing stop
                trail_multiplier = Decimal('1') - (order.trail_percent / Decimal('100'))
                new_stop_price = order.highest_price * trail_multiplier
            elif order.trail_amount:
                # Fixed amount trailing stop
                new_stop_price = order.highest_price - order.trail_amount
            else:
                logger.error(f"Trailing stop order {order.order_id} has no trail parameters")
                return False
            
            # Only update if new stop price is higher than current
            if not order.current_stop_price or new_stop_price > order.current_stop_price:
                with transaction.atomic():
                    order.current_stop_price = new_stop_price
                    order.save()
                
                logger.debug(
                    f"Updated trailing stop for {order.order_id}: "
                    f"Highest: ${order.highest_price}, "
                    f"Stop: ${new_stop_price}"
                )
                return True
        
        return False
    
    except Exception as e:
        logger.error(f"Error updating trailing stop: {e}", exc_info=True)
        return False


def _execute_order(
    order_manager: OrderManager,
    order: PaperOrder,
    execution_price: Decimal
) -> bool:
    """
    Execute an order at the current price.
    
    This will eventually integrate with SimplePaperTradingSimulator
    to create actual trades. For now, it marks the order as filled.
    
    Args:
        order_manager: OrderManager instance
        order: The order to execute
        execution_price: Price at which to execute
        
    Returns:
        True if execution succeeded, False otherwise
    """
    try:
        logger.info(
            f"[ORDER_EXECUTE] Executing order {order.order_id} "
            f"at ${execution_price}"
        )
        
        # TODO: Integrate with SimplePaperTradingSimulator to create actual trade
        # For now, just mark the order as filled
        
        with transaction.atomic():
            order.status = OrderStatus.FILLED
            order.filled_at = timezone.now()
            order.filled_amount_usd = order.amount_usd
            order.filled_amount_token = order.amount_token
            order.average_fill_price = execution_price
            order.save()
        
        logger.info(
            f"[ORDER_EXECUTE] ✅ Order {order.order_id} marked as FILLED"
        )
        
        return True
    
    except Exception as e:
        logger.error(f"[ORDER_EXECUTE] Error executing order: {e}", exc_info=True)
        
        # Mark order as failed
        try:
            with transaction.atomic():
                order.status = OrderStatus.FAILED
                order.error_message = str(e)
                order.save()
        except Exception:
            pass
        
        return False


def _mark_order_expired(order: PaperOrder) -> bool:
    """
    Mark an order as expired.
    
    Args:
        order: The order to mark as expired
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with transaction.atomic():
            order.status = OrderStatus.EXPIRED
            order.cancelled_at = timezone.now()
            order.notes = (order.notes or "") + "\nOrder expired at " + str(timezone.now())
            order.save()
        
        logger.info(f"[ORDER_EXPIRE] Order {order.order_id} marked as EXPIRED")
        return True
    
    except Exception as e:
        logger.error(f"Error marking order as expired: {e}", exc_info=True)
        return False


def _send_order_notification(order: PaperOrder, event_type: str) -> None:
    """
    Send WebSocket notification for order status change.
    
    Args:
        order: The order that changed
        event_type: Type of event ('triggered', 'executed', 'expired', 'failed')
    """
    try:
        # Prepare order data for WebSocket message
        order_data = {
            'order_id': str(order.order_id),
            'order_type': order.order_type,
            'token_symbol': order.token_symbol,
            'amount_usd': float(order.amount_usd),
            'status': order.status,
            'event_type': event_type,
            'timestamp': timezone.now().isoformat()
        }
        
        # Send WebSocket update
        send_order_update(order_data)
        
        logger.debug(
            f"[ORDER_NOTIFY] Sent {event_type} notification for order {order.order_id}"
        )
    
    except Exception as e:
        logger.error(f"Error sending order notification: {e}", exc_info=True)