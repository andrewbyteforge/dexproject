"""
Paper Trading Orders Views

Django view handlers for order management pages including order placement,
active orders monitoring, and order history with filtering.

Integrates with:
- OrderManager service (Day 2) for order operations
- PaperOrder model (Day 1) for database queries
- OrderType, OrderStatus, OrderFields constants (Day 1)

File: paper_trading/views_orders.py
"""

import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum
from django.utils import timezone

from .models import PaperOrder, PaperTradingAccount
from .services.order_manager import OrderManager
from .constants import OrderType, OrderStatus, OrderFields
from .utils import get_single_trading_account

logger = logging.getLogger(__name__)

# =============================================================================
# PAGE VIEWS
# =============================================================================

@require_GET
def orders_place_view(request: HttpRequest) -> HttpResponse:
    """
    Display the order placement form.
    
    GET /paper-trading/orders/place/
    
    Shows form for creating new orders with:
    - Order type selection (LIMIT, STOP_LIMIT, TRAILING_STOP)
    - Token selection
    - Amount and price inputs
    - Real-time price display
    - Order summary
    
    Returns:
        HttpResponse: Rendered order placement template
    """
    try:
        logger.info("Loading order placement page")
        
        # Get account
        account = get_single_trading_account()
        
        # Context for template
        context = {
            'account': account,
            'account_balance': account.current_balance_usd,
            'order_types': OrderType.ALL,
            'page_title': 'Place Order',
        }
        
        return render(request, 'paper_trading/orders_place.html', context)
        
    except Exception as e:
        logger.error(f"Error loading order placement page: {e}", exc_info=True)
        messages.error(request, f"Failed to load order placement page: {str(e)}")
        return redirect('paper_trading:dashboard')


@require_http_methods(["GET", "POST"])
def orders_place_submit(request: HttpRequest) -> HttpResponse:
    """
    Handle order placement form submission.
    
    POST /paper-trading/orders/place/
    
    Creates a new order using OrderManager service.
    Validates all inputs and provides user feedback.
    
    Form Data:
        order_type: str - Order type constant
        token_address: str - Token contract address
        token_symbol: str - Token symbol (optional)
        amount_usd: Decimal - USD amount to trade
        trigger_price: Decimal - Trigger price (optional)
        limit_price: Decimal - Limit price
        trail_percent: Decimal - Trail percentage (for trailing stops)
        expires_at: datetime - Expiration time (optional)
        notes: str - User notes (optional)
    
    Returns:
        HttpResponse: Redirect to active orders or re-render form with errors
    """
    if request.method == 'GET':
        return orders_place_view(request)
    
    try:
        logger.info("Processing order placement submission")
        
        # Get account
        account = get_single_trading_account()
        
        # Extract form data
        order_type = request.POST.get('order_type')
        token_address = request.POST.get('token_address', '').strip()
        token_symbol = request.POST.get('token_symbol', '').strip() or 'UNKNOWN'
        amount_usd = request.POST.get('amount_usd')
        trigger_price = request.POST.get('trigger_price')
        limit_price = request.POST.get('limit_price')
        trail_percent = request.POST.get('trail_percent')
        expires_at_str = request.POST.get('expires_at')
        notes = request.POST.get('notes', '').strip()
        
        # Validate order type
        if not order_type or order_type not in OrderType.ALL:
            messages.error(request, f"Invalid order type: {order_type}")
            return redirect('paper_trading:orders_place')
        
        # Validate token address
        if not token_address or not token_address.startswith('0x') or len(token_address) != 42:
            messages.error(request, "Invalid token address format")
            return redirect('paper_trading:orders_place')
        
        # Validate amount
        try:
            amount_usd_decimal = Decimal(str(amount_usd))
            if amount_usd_decimal <= 0:
                raise ValueError("Amount must be positive")
        except (ValueError, TypeError) as e:
            messages.error(request, f"Invalid amount: {str(e)}")
            return redirect('paper_trading:orders_place')
        
        # Build order parameters
        order_params = {
            OrderFields.ORDER_TYPE: order_type,
            OrderFields.TOKEN_ADDRESS: token_address,
            OrderFields.TOKEN_SYMBOL: token_symbol,
            OrderFields.AMOUNT_USD: amount_usd_decimal,
        }
        
        # Add limit price (required for most order types)
        if limit_price:
            try:
                order_params[OrderFields.LIMIT_PRICE] = Decimal(str(limit_price))
            except (ValueError, TypeError):
                messages.error(request, "Invalid limit price")
                return redirect('paper_trading:orders_place')
        
        # Add trigger price (for stop orders)
        if trigger_price and order_type in [OrderType.STOP_LIMIT_BUY, OrderType.STOP_LIMIT_SELL]:
            try:
                order_params[OrderFields.TRIGGER_PRICE] = Decimal(str(trigger_price))
            except (ValueError, TypeError):
                messages.error(request, "Invalid trigger price")
                return redirect('paper_trading:orders_place')
        
        # Add trail percent (for trailing stops)
        if trail_percent and order_type == OrderType.TRAILING_STOP:
            try:
                order_params[OrderFields.TRAIL_PERCENT] = Decimal(str(trail_percent))
            except (ValueError, TypeError):
                messages.error(request, "Invalid trail percentage")
                return redirect('paper_trading:orders_place')
        
        # Add expiration (optional)
        if expires_at_str:
            try:
                order_params[OrderFields.EXPIRES_AT] = datetime.fromisoformat(expires_at_str)
            except ValueError:
                messages.error(request, "Invalid expiration date format")
                return redirect('paper_trading:orders_place')
        
        # Add notes (optional)
        if notes:
            order_params[OrderFields.NOTES] = notes
        
        # Create order using OrderManager
        order_manager = OrderManager(account)
        order = order_manager.place_order(**order_params)
        
        if order:
            messages.success(
                request,
                f"Order placed successfully! Order ID: {str(order.order_id)[:8]}..."
            )
            logger.info(f"Order created successfully: {order.order_id}")
            return redirect('paper_trading:orders_active')
        else:
            messages.error(request, "Failed to place order. Please try again.")
            return redirect('paper_trading:orders_place')
        
    except Exception as e:
        logger.error(f"Error placing order: {e}", exc_info=True)
        messages.error(request, f"Failed to place order: {str(e)}")
        return redirect('paper_trading:orders_place')


@require_GET
def orders_active_view(request: HttpRequest) -> HttpResponse:
    """
    Display active orders page with filtering and pagination.
    
    GET /paper-trading/orders/active/
    
    Query Parameters:
        order_type: str - Filter by order type
        status: str - Filter by status
        token: str - Filter by token symbol or address
        page: int - Pagination page number
    
    Returns:
        HttpResponse: Rendered active orders template
    """
    try:
        logger.info("Loading active orders page")
        
        # Get account
        account = get_single_trading_account()
        
        # Build query for active orders
        query = PaperOrder.objects.filter(
            account=account,
            status__in=[OrderStatus.PENDING, OrderStatus.TRIGGERED, OrderStatus.PARTIALLY_FILLED]
        ).select_related('account', 'related_trade')
        
        # Apply filters
        order_type_filter = request.GET.get('order_type')
        if order_type_filter and order_type_filter in OrderType.ALL:
            query = query.filter(order_type=order_type_filter)
        
        status_filter = request.GET.get('status')
        if status_filter and status_filter in [OrderStatus.PENDING, OrderStatus.TRIGGERED, OrderStatus.PARTIALLY_FILLED]:
            query = query.filter(status=status_filter)
        
        token_filter = request.GET.get('token')
        if token_filter:
            query = query.filter(
                Q(token_symbol__icontains=token_filter) |
                Q(token_address__icontains=token_filter)
            )
        
        # Order by creation date (newest first)
        query = query.order_by('-created_at')
        
        # Calculate summary stats
        pending_count = query.filter(status=OrderStatus.PENDING).count()
        triggered_count = query.filter(status=OrderStatus.TRIGGERED).count()
        total_value = query.aggregate(Sum('amount_usd'))['amount_usd__sum'] or Decimal('0')
        
        # Pagination
        paginator = Paginator(query, 20)  # 20 orders per page
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        
        # Context
        context = {
            'account': account,
            'active_orders': page_obj,
            'page_obj': page_obj,
            'is_paginated': paginator.num_pages > 1,
            'pending_count': pending_count,
            'triggered_count': triggered_count,
            'total_value': total_value,
            'page_title': 'Active Orders',
        }
        
        return render(request, 'paper_trading/orders_active.html', context)
        
    except Exception as e:
        logger.error(f"Error loading active orders page: {e}", exc_info=True)
        messages.error(request, f"Failed to load active orders: {str(e)}")
        return redirect('paper_trading:dashboard')


@require_GET
def orders_history_view(request: HttpRequest) -> HttpResponse:
    """
    Display order history page with filtering and pagination.
    
    GET /paper-trading/orders/history/
    
    Query Parameters:
        status: str - Filter by status (FILLED, CANCELLED, EXPIRED, FAILED)
        order_type: str - Filter by order type
        token: str - Filter by token symbol or address
        date_from: date - Start date filter
        date_to: date - End date filter
        page: int - Pagination page number
    
    Returns:
        HttpResponse: Rendered order history template
    """
    try:
        logger.info("Loading order history page")
        
        # Get account
        account = get_single_trading_account()
        
        # Build query for completed orders
        query = PaperOrder.objects.filter(
            account=account,
            status__in=[OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.FAILED]
        ).select_related('account', 'related_trade')
        
        # Apply filters
        status_filter = request.GET.get('status')
        if status_filter and status_filter in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.FAILED]:
            query = query.filter(status=status_filter)
        
        order_type_filter = request.GET.get('order_type')
        if order_type_filter and order_type_filter in OrderType.ALL:
            query = query.filter(order_type=order_type_filter)
        
        token_filter = request.GET.get('token')
        if token_filter:
            query = query.filter(
                Q(token_symbol__icontains=token_filter) |
                Q(token_address__icontains=token_filter)
            )
        
        # Date range filters
        date_from = request.GET.get('date_from')
        if date_from:
            try:
                date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
                query = query.filter(created_at__gte=date_from_dt)
            except ValueError:
                messages.warning(request, "Invalid start date format")
        
        date_to = request.GET.get('date_to')
        if date_to:
            try:
                date_to_dt = datetime.strptime(date_to, '%Y-%m-%d')
                # Include the entire day
                date_to_dt = date_to_dt.replace(hour=23, minute=59, second=59)
                query = query.filter(created_at__lte=date_to_dt)
            except ValueError:
                messages.warning(request, "Invalid end date format")
        
        # Order by completion date (newest first)
        query = query.order_by('-filled_at', '-cancelled_at', '-created_at')
        
        # Calculate summary stats
        total_count = query.count()
        filled_count = query.filter(status=OrderStatus.FILLED).count()
        cancelled_count = query.filter(status=OrderStatus.CANCELLED).count()
        failed_count = query.filter(status__in=[OrderStatus.EXPIRED, OrderStatus.FAILED]).count()
        
        # Add calculated duration field to each order
        orders_list = list(query)
        for order in orders_list:
            if order.filled_at:
                duration = order.filled_at - order.created_at
            elif order.cancelled_at:
                duration = order.cancelled_at - order.created_at
            else:
                duration = None
            
            if duration:
                total_seconds = int(duration.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                if hours > 0:
                    order.duration = f"{hours}h {minutes}m"
                else:
                    order.duration = f"{minutes}m"
            else:
                order.duration = "--"
        
        # Pagination
        paginator = Paginator(orders_list, 25)  # 25 orders per page
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        
        # Context
        context = {
            'account': account,
            'orders': page_obj,
            'page_obj': page_obj,
            'is_paginated': paginator.num_pages > 1,
            'total_count': total_count,
            'filled_count': filled_count,
            'cancelled_count': cancelled_count,
            'failed_count': failed_count,
            'page_title': 'Order History',
        }
        
        return render(request, 'paper_trading/orders_history.html', context)
        
    except Exception as e:
        logger.error(f"Error loading order history page: {e}", exc_info=True)
        messages.error(request, f"Failed to load order history: {str(e)}")
        return redirect('paper_trading:dashboard')


# =============================================================================
# API ENDPOINTS
# =============================================================================

@require_POST
def api_cancel_order(request: HttpRequest) -> JsonResponse:
    """
    Cancel an active order via API.
    
    POST /paper-trading/api/orders/cancel/
    
    JSON Body:
        order_id: str - UUID of order to cancel
        reason: str - Cancellation reason (optional)
    
    Returns:
        JsonResponse: Success status and message
    """
    try:
        import json
        data = json.loads(request.body)
        
        order_id = data.get('order_id')
        reason = data.get('reason', 'User requested cancellation')
        
        if not order_id:
            return JsonResponse({
                'success': False,
                'error': 'Order ID required'
            }, status=400)
        
        # Get account
        account = get_single_trading_account()
        
        # Cancel order using OrderManager
        order_manager = OrderManager(account)
        success = order_manager.cancel_order(order_id, reason)
        
        if success:
            logger.info(f"Order {order_id} cancelled successfully")
            return JsonResponse({
                'success': True,
                'message': 'Order cancelled successfully'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to cancel order'
            }, status=400)
        
    except Exception as e:
        logger.error(f"Error cancelling order: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_GET
def api_order_details(request: HttpRequest, order_id: str) -> JsonResponse:
    """
    Get detailed information about a specific order.
    
    GET /paper-trading/api/orders/<order_id>/
    
    Returns:
        JsonResponse: Order details
    """
    try:
        # Get account
        account = get_single_trading_account()
        
        # Get order
        order = PaperOrder.objects.filter(
            account=account,
            order_id=order_id
        ).select_related('account', 'related_trade').first()
        
        if not order:
            return JsonResponse({
                'success': False,
                'error': 'Order not found'
            }, status=404)
        
        # Build response
        order_data = {
            'order_id': str(order.order_id),
            'order_type': order.order_type,
            'status': order.status,
            'token_address': order.token_address,
            'token_symbol': order.token_symbol,
            'token_name': order.token_name,
            'amount_usd': str(order.amount_usd),
            'amount_token': str(order.amount_token) if order.amount_token else None,
            'trigger_price': str(order.trigger_price) if order.trigger_price else None,
            'limit_price': str(order.limit_price) if order.limit_price else None,
            'stop_price': str(order.stop_price) if order.stop_price else None,
            'trail_percent': str(order.trail_percent) if order.trail_percent else None,
            'highest_price': str(order.highest_price) if order.highest_price else None,
            'current_stop_price': str(order.current_stop_price) if order.current_stop_price else None,
            'filled_amount_usd': str(order.filled_amount_usd) if order.filled_amount_usd else None,
            'filled_amount_token': str(order.filled_amount_token) if order.filled_amount_token else None,
            'average_fill_price': str(order.average_fill_price) if order.average_fill_price else None,
            'created_at': order.created_at.isoformat(),
            'expires_at': order.expires_at.isoformat() if order.expires_at else None,
            'triggered_at': order.triggered_at.isoformat() if order.triggered_at else None,
            'filled_at': order.filled_at.isoformat() if order.filled_at else None,
            'cancelled_at': order.cancelled_at.isoformat() if order.cancelled_at else None,
            'notes': order.notes,
            'error_message': order.error_message,
            'is_active': order.is_active(),
            'is_expired': order.is_expired(),
        }
        
        return JsonResponse({
            'success': True,
            'order': order_data
        })
        
    except Exception as e:
        logger.error(f"Error fetching order details: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)