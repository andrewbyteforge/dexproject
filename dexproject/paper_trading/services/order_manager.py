"""
Paper Trading Order Manager Service

This service provides centralized order management for the paper trading system,
handling order placement, cancellation, validation, and querying.

Features:
- Order placement with validation
- Order cancellation with reason tracking
- Active orders querying with filters
- Order history with pagination
- Parameter validation for all order types
- Integration with PaperOrder model and constants

File: paper_trading/services/order_manager.py
"""

import logging
import uuid
from typing import List, Optional, Dict, Any
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError

# Import models
from paper_trading.models import PaperTradingAccount, PaperOrder, PaperTrade

# Import constants from Day 1
from paper_trading.constants import (
    OrderType,
    OrderStatus,
    OrderFields,
    validate_order_type,
    validate_order_status,
    is_order_active,
    is_order_terminal
)

logger = logging.getLogger(__name__)


# =============================================================================
# ORDER MANAGER SERVICE
# =============================================================================

class OrderManager:
    """
    Centralized service for managing paper trading orders.
    
    This service handles the complete lifecycle of orders including:
    - Validation of order parameters
    - Order placement and creation
    - Order cancellation
    - Querying active and historical orders
    
    All operations use the OrderType, OrderStatus, and OrderFields constants
    to ensure type safety and prevent field name mismatches.
    """
    
    def __init__(self, account: PaperTradingAccount):
        """
        Initialize order manager for a specific account.
        
        Args:
            account: Paper trading account to manage orders for
        """
        self.account = account
        self.logger = logging.getLogger('paper_trading.order_manager')
        
        self.logger.info(
            f"[ORDER MANAGER] Initialized for account {account.account_id}"
        )
    
    # =========================================================================
    # ORDER PLACEMENT
    # =========================================================================
    
    @transaction.atomic
    def place_order(
        self,
        order_type: str,
        token_address: str,
        token_symbol: str,
        amount_usd: Decimal,
        token_name: str = '',
        trigger_price: Optional[Decimal] = None,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        trail_percent: Optional[Decimal] = None,
        trail_amount: Optional[Decimal] = None,
        expires_at: Optional[datetime] = None,
        notes: str = ''
    ) -> PaperOrder:
        """
        Place a new order with validation.
        
        This method validates all parameters, creates the order record,
        and logs the creation for monitoring.
        
        Args:
            order_type: Type of order (from OrderType constants)
            token_address: Token contract address
            token_symbol: Token symbol (e.g., 'WETH')
            amount_usd: Order amount in USD
            token_name: Token name (optional)
            trigger_price: Price to trigger the order (for STOP_LIMIT, TRAILING_STOP)
            limit_price: Execution price (for LIMIT orders)
            stop_price: Stop price (for STOP_LIMIT orders)
            trail_percent: Trailing percentage (for TRAILING_STOP)
            trail_amount: Trailing amount (for TRAILING_STOP)
            expires_at: Expiration datetime (optional)
            notes: User notes (optional)
        
        Returns:
            Created PaperOrder instance
        
        Raises:
            ValidationError: If order parameters are invalid
        """
        # Validate order type
        if not validate_order_type(order_type):
            raise ValidationError(f"Invalid order type: {order_type}")
        
        # Validate order parameters for this order type
        validation_result = self.validate_order_parameters(
            order_type=order_type,
            amount_usd=amount_usd,
            trigger_price=trigger_price,
            limit_price=limit_price,
            stop_price=stop_price,
            trail_percent=trail_percent,
            trail_amount=trail_amount
        )
        
        if not validation_result['valid']:
            raise ValidationError(validation_result['error'])
        
        # Create order instance
        order = PaperOrder(
            **{
                OrderFields.ORDER_ID: uuid.uuid4(),
                OrderFields.ACCOUNT: self.account,
                OrderFields.ORDER_TYPE: order_type,
                OrderFields.TOKEN_ADDRESS: token_address.lower(),
                OrderFields.TOKEN_SYMBOL: token_symbol.upper(),
                OrderFields.TOKEN_NAME: token_name or token_symbol,
                OrderFields.AMOUNT_USD: amount_usd,
                OrderFields.AMOUNT_TOKEN: Decimal('0'),  # Will be calculated on execution
                OrderFields.TRIGGER_PRICE: trigger_price,
                OrderFields.LIMIT_PRICE: limit_price,
                OrderFields.STOP_PRICE: stop_price,
                OrderFields.TRAIL_PERCENT: trail_percent,
                OrderFields.TRAIL_AMOUNT: trail_amount,
                OrderFields.STATUS: OrderStatus.PENDING,
                OrderFields.EXPIRES_AT: expires_at,
                OrderFields.NOTES: notes,
                OrderFields.CREATED_AT: timezone.now()
            }
        )
        
        # Save order
        order.save()
        
        self.logger.info(
            f"[ORDER MANAGER] Order placed: "
            f"order_id={order.order_id}, type={order_type}, "
            f"token={token_symbol}, amount_usd=${amount_usd}"
        )
        
        return order
    
    # =========================================================================
    # ORDER CANCELLATION
    # =========================================================================
    
    @transaction.atomic
    def cancel_order(
        self,
        order_id: uuid.UUID,
        reason: str = 'User cancelled'
    ) -> bool:
        """
        Cancel an active order.
        
        Args:
            order_id: UUID of the order to cancel
            reason: Cancellation reason
        
        Returns:
            True if cancelled successfully, False if order not found or already terminal
        """
        try:
            # Get order with row lock
            order = PaperOrder.objects.select_for_update().get(
                **{
                    OrderFields.ORDER_ID: order_id,
                    OrderFields.ACCOUNT: self.account
                }
            )
            
            # Check if order can be cancelled
            if is_order_terminal(order.status):
                self.logger.warning(
                    f"[ORDER MANAGER] Cannot cancel order {order_id}: "
                    f"already in terminal state {order.status}"
                )
                return False
            
            # Cancel the order using model method
            success = order.cancel(reason=reason)
            
            if success:
                self.logger.info(
                    f"[ORDER MANAGER] Order cancelled: "
                    f"order_id={order_id}, reason={reason}"
                )
            
            return success
            
        except PaperOrder.DoesNotExist:
            self.logger.warning(
                f"[ORDER MANAGER] Order not found: {order_id}"
            )
            return False
    
    # =========================================================================
    # ORDER QUERYING
    # =========================================================================
    
    def get_active_orders(
        self,
        order_type: Optional[str] = None,
        token_address: Optional[str] = None
    ) -> List[PaperOrder]:
        """
        Get all active orders with optional filtering.
        
        Args:
            order_type: Filter by order type (optional)
            token_address: Filter by token address (optional)
        
        Returns:
            List of active PaperOrder instances
        """
        # Base query - all active orders for this account
        query = PaperOrder.objects.filter(
            **{OrderFields.ACCOUNT: self.account}
        )
        
        # Filter to only active statuses
        query = query.filter(
            **{f"{OrderFields.STATUS}__in": [
                OrderStatus.PENDING,
                OrderStatus.TRIGGERED,
                OrderStatus.PARTIALLY_FILLED
            ]}
        )
        
        # Apply optional filters
        if order_type:
            query = query.filter(**{OrderFields.ORDER_TYPE: order_type})
        
        if token_address:
            query = query.filter(
                **{OrderFields.TOKEN_ADDRESS: token_address.lower()}
            )
        
        # Order by creation date
        orders = query.order_by(f'-{OrderFields.CREATED_AT}').all()
        
        self.logger.debug(
            f"[ORDER MANAGER] Retrieved {len(orders)} active orders "
            f"(type={order_type}, token={token_address})"
        )
        
        return list(orders)
    
    def get_order_history(
        self,
        limit: int = 100,
        order_type: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[PaperOrder]:
        """
        Get order history with optional filtering.
        
        Args:
            limit: Maximum number of orders to return
            order_type: Filter by order type (optional)
            status: Filter by status (optional)
        
        Returns:
            List of PaperOrder instances
        """
        # Base query
        query = PaperOrder.objects.filter(
            **{OrderFields.ACCOUNT: self.account}
        )
        
        # Apply optional filters
        if order_type:
            query = query.filter(**{OrderFields.ORDER_TYPE: order_type})
        
        if status:
            query = query.filter(**{OrderFields.STATUS: status})
        
        # Order by creation date (newest first) and limit
        orders = query.order_by(
            f'-{OrderFields.CREATED_AT}'
        )[:limit]
        
        self.logger.debug(
            f"[ORDER MANAGER] Retrieved {len(orders)} historical orders "
            f"(limit={limit}, type={order_type}, status={status})"
        )
        
        return list(orders)
    
    def get_order_by_id(
        self,
        order_id: uuid.UUID
    ) -> Optional[PaperOrder]:
        """
        Get a specific order by ID.
        
        Args:
            order_id: UUID of the order
        
        Returns:
            PaperOrder instance if found, None otherwise
        """
        try:
            order = PaperOrder.objects.get(
                **{
                    OrderFields.ORDER_ID: order_id,
                    OrderFields.ACCOUNT: self.account
                }
            )
            return order
        except PaperOrder.DoesNotExist:
            self.logger.warning(
                f"[ORDER MANAGER] Order not found: {order_id}"
            )
            return None
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    def validate_order_parameters(
        self,
        order_type: str,
        amount_usd: Decimal,
        trigger_price: Optional[Decimal] = None,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        trail_percent: Optional[Decimal] = None,
        trail_amount: Optional[Decimal] = None
    ) -> Dict[str, Any]:
        """
        Validate order parameters based on order type.
        
        Args:
            order_type: Type of order
            amount_usd: Order amount in USD
            trigger_price: Trigger price (optional)
            limit_price: Limit price (optional)
            stop_price: Stop price (optional)
            trail_percent: Trail percentage (optional)
            trail_amount: Trail amount (optional)
        
        Returns:
            Dictionary with 'valid' (bool) and 'error' (str) keys
        """
        # Validate amount
        if amount_usd <= Decimal('0'):
            return {
                'valid': False,
                'error': 'Amount must be greater than zero'
            }
        
        # Check account balance
        if amount_usd > self.account.current_balance_usd:
            return {
                'valid': False,
                'error': f'Insufficient balance: ${self.account.current_balance_usd} available'
            }
        
        # Validate based on order type
        if order_type in [OrderType.LIMIT_BUY, OrderType.LIMIT_SELL]:
            # Limit orders require limit_price
            if limit_price is None or limit_price <= Decimal('0'):
                return {
                    'valid': False,
                    'error': 'Limit orders require a valid limit price'
                }
        
        elif order_type in [OrderType.STOP_LIMIT_BUY, OrderType.STOP_LIMIT_SELL]:
            # Stop-limit orders require both trigger and limit prices
            if trigger_price is None or trigger_price <= Decimal('0'):
                return {
                    'valid': False,
                    'error': 'Stop-limit orders require a valid trigger price'
                }
            if limit_price is None or limit_price <= Decimal('0'):
                return {
                    'valid': False,
                    'error': 'Stop-limit orders require a valid limit price'
                }
            
            # Validate price relationship for buy orders
            if order_type == OrderType.STOP_LIMIT_BUY and trigger_price < limit_price:
                return {
                    'valid': False,
                    'error': 'For stop-limit buy: trigger price must be >= limit price'
                }
            
            # Validate price relationship for sell orders
            if order_type == OrderType.STOP_LIMIT_SELL and trigger_price > limit_price:
                return {
                    'valid': False,
                    'error': 'For stop-limit sell: trigger price must be <= limit price'
                }
        
        elif order_type == OrderType.TRAILING_STOP:
            # Trailing stops require either trail_percent or trail_amount
            if trail_percent is None and trail_amount is None:
                return {
                    'valid': False,
                    'error': 'Trailing stop requires either trail_percent or trail_amount'
                }
            
            if trail_percent is not None:
                if trail_percent <= Decimal('0') or trail_percent > Decimal('50'):
                    return {
                        'valid': False,
                        'error': 'Trail percentage must be between 0 and 50'
                    }
        
        # All validations passed
        return {'valid': True, 'error': None}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_order_manager(account: PaperTradingAccount) -> OrderManager:
    """
    Get an OrderManager instance for the given account.
    
    Args:
        account: Paper trading account
    
    Returns:
        OrderManager instance
    
    Example:
        manager = get_order_manager(account)
        order = manager.place_order(...)
    """
    return OrderManager(account)