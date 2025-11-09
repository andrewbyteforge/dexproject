"""
Paper Trading Order Models - Phase 7A Advanced Order Types

This module defines the order models for advanced order types:
- Limit orders (buy below/sell above market price)
- Stop-limit orders (trigger at stop, execute at limit)
- Trailing stop orders (dynamic stops that follow price)

All order types use a single unified PaperOrder model with type-specific fields.

File: dexproject/paper_trading/models/orders.py
"""

import uuid
import logging
from decimal import Decimal
from typing import Optional

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

from .base import PaperTradingAccount, PaperTrade
from ..constants import OrderType, OrderStatus, OrderFields

logger = logging.getLogger(__name__)


# =============================================================================
# PAPER ORDER MODEL (Unified for all order types)
# =============================================================================

class PaperOrder(models.Model):
    """
    Unified order model for all advanced order types.
    
    Supports:
    - Limit orders: Execute when price reaches target
    - Stop-limit orders: Trigger at stop price, execute at limit
    - Trailing stops: Dynamic stop that follows price upward
    
    Lifecycle:
    1. PENDING: Order placed, monitoring price
    2. TRIGGERED: Stop price hit (stop-limit only)
    3. PARTIALLY_FILLED: Partial execution (if supported)
    4. FILLED: Order fully executed
    5. CANCELLED: User cancelled
    6. EXPIRED: Time-based expiration
    7. FAILED: Execution error
    
    Example Usage:
        # Limit buy order
        order = PaperOrder.objects.create(
            account=account,
            order_type=OrderType.LIMIT_BUY,
            token_address='0x123...',
            token_symbol='AAVE',
            amount_usd=Decimal('100.00'),
            trigger_price=Decimal('150.00'),  # Buy when price drops to $150
            expires_at=timezone.now() + timedelta(days=7)
        )
        
        # Trailing stop order
        order = PaperOrder.objects.create(
            account=account,
            order_type=OrderType.TRAILING_STOP,
            token_address='0x123...',
            token_symbol='LINK',
            amount_usd=Decimal('200.00'),
            trail_percent=Decimal('5.0'),  # Trail 5% below highest price
            highest_price=Decimal('20.00')  # Initialize with current price
        )
    """
    
    # =========================================================================
    # IDENTITY FIELDS
    # =========================================================================
    
    order_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique order identifier"
    )
    
    account = models.ForeignKey(
        PaperTradingAccount,
        on_delete=models.CASCADE,
        related_name='orders',
        help_text="Paper trading account that placed this order"
    )
    
    order_type = models.CharField(
        max_length=20,
        choices=[
            (OrderType.LIMIT_BUY, 'Limit Buy'),
            (OrderType.LIMIT_SELL, 'Limit Sell'),
            (OrderType.STOP_LIMIT_BUY, 'Stop-Limit Buy'),
            (OrderType.STOP_LIMIT_SELL, 'Stop-Limit Sell'),
            (OrderType.TRAILING_STOP, 'Trailing Stop'),
        ],
        help_text="Type of order"
    )
    
    # =========================================================================
    # TOKEN DETAILS
    # =========================================================================
    
    token_address = models.CharField(
        max_length=42,
        help_text="Token contract address"
    )
    
    token_symbol = models.CharField(
        max_length=20,
        help_text="Token symbol (e.g., AAVE, LINK)"
    )
    
    token_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Token full name"
    )
    
    # =========================================================================
    # ORDER PARAMETERS
    # =========================================================================
    
    amount_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('1.00'))],
        help_text="Order size in USD"
    )
    
    amount_token = models.DecimalField(
        max_digits=36,
        decimal_places=18,
        null=True,
        blank=True,
        help_text="Order size in tokens (calculated from amount_usd)"
    )
    
    # =========================================================================
    # PRICE PARAMETERS (Different fields used by different order types)
    # =========================================================================
    
    trigger_price = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00000001'))],
        help_text="Trigger price for limit orders and stop-limit orders"
    )
    
    limit_price = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00000001'))],
        help_text="Limit price for stop-limit orders (execution price)"
    )
    
    stop_price = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00000001'))],
        help_text="Stop price for stop-limit orders (same as trigger_price)"
    )
    
    # =========================================================================
    # TRAILING STOP PARAMETERS
    # =========================================================================
    
    trail_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal('0.1')),
            MaxValueValidator(Decimal('50.0'))
        ],
        help_text="Trailing stop percentage (e.g., 5.0 = 5% trail)"
    )
    
    trail_amount = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Trailing stop fixed amount (alternative to trail_percent)"
    )
    
    highest_price = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00000001'))],
        help_text="Highest price seen (for trailing stops)"
    )
    
    current_stop_price = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00000001'))],
        help_text="Current trailing stop price (updated as price rises)"
    )
    
    # =========================================================================
    # EXECUTION STATUS
    # =========================================================================
    
    status = models.CharField(
        max_length=20,
        choices=[
            (OrderStatus.PENDING, 'Pending'),
            (OrderStatus.TRIGGERED, 'Triggered'),
            (OrderStatus.PARTIALLY_FILLED, 'Partially Filled'),
            (OrderStatus.FILLED, 'Filled'),
            (OrderStatus.CANCELLED, 'Cancelled'),
            (OrderStatus.EXPIRED, 'Expired'),
            (OrderStatus.FAILED, 'Failed'),
        ],
        default=OrderStatus.PENDING,
        help_text="Current order status"
    )
    
    filled_amount_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Amount filled in USD (for partial fills)"
    )
    
    filled_amount_token = models.DecimalField(
        max_digits=36,
        decimal_places=18,
        default=Decimal('0'),
        help_text="Amount filled in tokens (for partial fills)"
    )
    
    average_fill_price = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Average execution price"
    )
    
    # =========================================================================
    # TIMING
    # =========================================================================
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Order placement timestamp"
    )
    
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Order expiration timestamp (optional)"
    )
    
    triggered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when stop price was triggered"
    )
    
    filled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when order was filled"
    )
    
    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when order was cancelled"
    )
    
    # =========================================================================
    # METADATA
    # =========================================================================
    
    notes = models.TextField(
        blank=True,
        help_text="User notes or order description"
    )
    
    error_message = models.TextField(
        blank=True,
        help_text="Error message if execution failed"
    )
    
    related_trade = models.ForeignKey(
        PaperTrade,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='originating_order',
        help_text="Link to the trade that executed this order"
    )
    
    # =========================================================================
    # META OPTIONS
    # =========================================================================
    
    class Meta:
        db_table = 'paper_orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', 'status']),
            models.Index(fields=['order_type', 'status']),
            models.Index(fields=['token_address', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['expires_at']),  # For expiration checks
        ]
        verbose_name = 'Paper Order'
        verbose_name_plural = 'Paper Orders'
    
    # =========================================================================
    # METHODS
    # =========================================================================
    
    def __str__(self) -> str:
        """String representation."""
        return f"{self.order_type}: {self.token_symbol} @ ${self.trigger_price or self.current_stop_price}"
    
    def is_active(self) -> bool:
        """Check if order is still active."""
        return self.status in OrderStatus.ACTIVE
    
    def is_terminal(self) -> bool:
        """Check if order is in terminal state."""
        return self.status in OrderStatus.TERMINAL
    
    def is_expired(self) -> bool:
        """Check if order has expired."""
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at
    
    def cancel(self, reason: str = '') -> bool:
        """
        Cancel this order.
        
        Args:
            reason: Optional cancellation reason
            
        Returns:
            True if cancelled successfully, False if already terminal
        """
        if self.is_terminal():
            logger.warning(
                f"Cannot cancel order {self.order_id} - "
                f"already in terminal state: {self.status}"
            )
            return False
        
        self.status = OrderStatus.CANCELLED
        self.cancelled_at = timezone.now()
        if reason:
            self.notes = f"{self.notes}\nCancelled: {reason}".strip()
        self.save()
        
        logger.info(
            f"Order {self.order_id} cancelled: {self.order_type} "
            f"{self.token_symbol} @ ${self.trigger_price}"
        )
        return True
    
    def update_trailing_stop(self, current_price: Decimal) -> bool:
        """
        Update trailing stop price based on current market price.
        
        Args:
            current_price: Current token price
            
        Returns:
            True if stop was updated, False otherwise
        """
        if self.order_type != OrderType.TRAILING_STOP:
            return False
        
        if not self.highest_price:
            self.highest_price = current_price
        
        # Update highest price if current price is higher
        if current_price > self.highest_price:
            self.highest_price = current_price
            
            # Calculate new stop price
            if self.trail_percent:
                trail_decimal = self.trail_percent / Decimal('100')
                new_stop = self.highest_price * (Decimal('1') - trail_decimal)
            elif self.trail_amount:
                new_stop = self.highest_price - self.trail_amount
            else:
                logger.error(
                    f"Trailing stop order {self.order_id} has no trail "
                    f"percent or amount"
                )
                return False
            
            # Only update if new stop is higher than current stop
            if not self.current_stop_price or new_stop > self.current_stop_price:
                self.current_stop_price = new_stop
                self.save()
                
                logger.debug(
                    f"Updated trailing stop for {self.token_symbol}: "
                    f"highest=${self.highest_price}, "
                    f"stop=${self.current_stop_price}"
                )
                return True
        
        return False
    
    def check_trigger(self, current_price: Decimal) -> bool:
        """
        Check if order should be triggered at current price.
        
        Args:
            current_price: Current token price
            
        Returns:
            True if order should execute, False otherwise
        """
        if not self.is_active():
            return False
        
        # Check expiration
        if self.is_expired():
            self.status = OrderStatus.EXPIRED
            self.save()
            logger.info(
                f"Order {self.order_id} expired: {self.order_type} "
                f"{self.token_symbol}"
            )
            return False
        
        # Check trigger conditions based on order type
        if self.order_type == OrderType.LIMIT_BUY:
            # Buy when price drops to or below trigger
            return current_price <= self.trigger_price
        
        elif self.order_type == OrderType.LIMIT_SELL:
            # Sell when price rises to or above trigger
            return current_price >= self.trigger_price
        
        elif self.order_type == OrderType.STOP_LIMIT_BUY:
            # Trigger when price rises to stop, then buy at limit
            if self.status == OrderStatus.PENDING:
                if current_price >= self.stop_price:
                    self.status = OrderStatus.TRIGGERED
                    self.triggered_at = timezone.now()
                    self.save()
                    logger.info(
                        f"Stop-limit buy triggered for {self.token_symbol} "
                        f"at ${current_price}"
                    )
                return False
            elif self.status == OrderStatus.TRIGGERED:
                # Execute at limit price or better
                return current_price <= self.limit_price
        
        elif self.order_type == OrderType.STOP_LIMIT_SELL:
            # Trigger when price drops to stop, then sell at limit
            if self.status == OrderStatus.PENDING:
                if current_price <= self.stop_price:
                    self.status = OrderStatus.TRIGGERED
                    self.triggered_at = timezone.now()
                    self.save()
                    logger.info(
                        f"Stop-limit sell triggered for {self.token_symbol} "
                        f"at ${current_price}"
                    )
                return False
            elif self.status == OrderStatus.TRIGGERED:
                # Execute at limit price or better
                return current_price >= self.limit_price
        
        elif self.order_type == OrderType.TRAILING_STOP:
            # Update trailing stop first
            self.update_trailing_stop(current_price)
            
            # Trigger when price drops to or below current stop
            if self.current_stop_price:
                return current_price <= self.current_stop_price
        
        return False
    
    def save(self, *args, **kwargs):
        """
        Override save to validate order parameters.
        
        Raises:
            ValueError: If order parameters are invalid
        """
        # Validate order type
        if self.order_type not in OrderType.ALL:
            raise ValueError(f"Invalid order type: {self.order_type}")
        
        # Validate limit orders have trigger price
        if self.order_type in OrderType.LIMIT_ORDERS:
            if not self.trigger_price:
                raise ValueError(
                    f"{self.order_type} requires trigger_price"
                )
        
        # Validate stop-limit orders have both stop and limit prices
        if self.order_type in OrderType.STOP_LIMIT_ORDERS:
            if not self.stop_price or not self.limit_price:
                raise ValueError(
                    f"{self.order_type} requires both stop_price and limit_price"
                )
            # Sync stop_price to trigger_price for consistency
            if not self.trigger_price:
                self.trigger_price = self.stop_price
        
        # Validate trailing stops have trail parameter
        if self.order_type == OrderType.TRAILING_STOP:
            if not self.trail_percent and not self.trail_amount:
                raise ValueError(
                    "Trailing stop requires either trail_percent or trail_amount"
                )
        
        super().save(*args, **kwargs)