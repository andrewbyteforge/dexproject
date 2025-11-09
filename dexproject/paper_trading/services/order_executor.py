"""
Order Executor Service for Paper Trading Orders - Phase 7A Day 4

This service handles the execution of orders that have been triggered by the
order monitoring task. It integrates with the SimplePaperTradingSimulator to
execute actual paper trades and manages the complete order execution lifecycle.

Responsibilities:
- Execute triggered orders through simulator
- Create PaperTrade records for executed orders
- Update PaperOrder status (TRIGGERED → FILLED/FAILED)
- Update PaperPosition records via simulator
- Handle partial fills for large orders
- Send WebSocket notifications for executions
- Log all execution attempts and results

Integration Points:
- SimplePaperTradingSimulator: Actual trade execution
- PriceFeedService: Current price validation
- WebSocketNotificationService: Real-time notifications
- PaperOrder model: Order status updates
- PaperTrade model: Trade record creation
- PaperPosition model: Position updates (via simulator)

File: dexproject/paper_trading/services/order_executor.py
"""

import logging
import uuid
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
from datetime import datetime

from django.db import transaction as db_transaction
from django.utils import timezone

# Import models
from paper_trading.models import (
    PaperTradingAccount,
    PaperOrder,
    PaperTrade,
    PaperPosition,
)

# Import constants
from paper_trading.constants import (
    OrderStatus,
    OrderFields,
    OrderType,
)

# Import services
from paper_trading.services.simulator import (
    SimplePaperTradingSimulator,
    SimplePaperTradeRequest,
    SimplePaperTradeResult,
)
from paper_trading.services.price_feed_service import PriceFeedService
from paper_trading.services.websocket_service import websocket_service

logger = logging.getLogger(__name__)


# =============================================================================
# ORDER EXECUTOR CLASS
# =============================================================================

class OrderExecutor:
    """
    Service for executing triggered paper trading orders.
    
    This service is called by the order monitoring task when an order's
    trigger conditions are met. It executes the order through the simulator,
    creates trade records, and updates all related models.
    
    Example usage:
        executor = OrderExecutor(account)
        success, message = executor.execute_order(order, current_price)
        
        if success:
            print(f"Order {order.order_id} executed successfully")
        else:
            print(f"Execution failed: {message}")
    """
    
    def __init__(self, account: PaperTradingAccount):
        """
        Initialize the Order Executor.
        
        Args:
            account: Paper trading account for order execution
        """
        self.account = account
        self.simulator = SimplePaperTradingSimulator()
        self.price_service = PriceFeedService()
        
        logger.info(
            f"[ORDER EXECUTOR] Initialized for account: {account.account_id}"
        )
    
    # =========================================================================
    # MAIN EXECUTION METHOD
    # =========================================================================
    
    @db_transaction.atomic
    def execute_order(
        self,
        order: PaperOrder,
        current_price: Decimal
    ) -> Tuple[bool, str]:
        """
        Execute a triggered order.
        
        This is the main entry point for order execution. It:
        1. Validates the order can be executed
        2. Determines trade direction (buy/sell)
        3. Executes trade through simulator
        4. Updates order status
        5. Sends notifications
        
        Args:
            order: PaperOrder instance to execute
            current_price: Current market price of the token
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            logger.info(
                f"[ORDER EXECUTOR] Executing order {order.order_id} "
                f"({order.order_type}) at price ${current_price}"
            )
            
            # Validate order is in correct state
            if not self._validate_order_for_execution(order):
                error_msg = f"Order {order.order_id} not in valid state for execution"
                logger.error(f"[ORDER EXECUTOR] {error_msg}")
                return False, error_msg
            
            # Mark order as triggered if not already
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.TRIGGERED
                order.triggered_at = timezone.now()
                order.save(update_fields=['status', 'triggered_at'])
                logger.info(
                    f"[ORDER EXECUTOR] Order {order.order_id} marked as TRIGGERED"
                )
            
            # Determine trade direction
            trade_type = self._determine_trade_type(order)
            
            # Execute the trade through simulator
            result = self._execute_trade_via_simulator(
                order=order,
                trade_type=trade_type,
                execution_price=current_price
            )
            
            # Handle execution result
            if result.success:
                # Mark order as filled
                self._mark_order_filled(
                    order=order,
                    trade=result.trade,
                    execution_price=current_price,
                    amount_token=result.trade.amount_in if result.trade else Decimal('0')
                )
                
                # Send notification
                self._send_execution_notification(
                    order=order,
                    trade=result.trade,
                    success=True
                )
                
                success_msg = (
                    f"Order {order.order_id} executed successfully. "
                    f"Trade ID: {result.trade_id}"
                )
                logger.info(f"[ORDER EXECUTOR] ✅ {success_msg}")
                return True, success_msg
            
            else:
                # Mark order as failed
                self._mark_order_failed(
                    order=order,
                    error_message=result.error_message or "Trade execution failed"
                )
                
                # Send notification
                self._send_execution_notification(
                    order=order,
                    trade=None,
                    success=False,
                    error=result.error_message
                )
                
                error_msg = f"Order {order.order_id} execution failed: {result.error_message}"
                logger.error(f"[ORDER EXECUTOR] ❌ {error_msg}")
                return False, error_msg
        
        except Exception as e:
            error_msg = f"Exception during order execution: {e}"
            logger.error(
                f"[ORDER EXECUTOR] ❌ Order {order.order_id}: {error_msg}",
                exc_info=True
            )
            
            # Try to mark order as failed
            try:
                self._mark_order_failed(order, error_msg)
            except Exception as inner_e:
                logger.error(
                    f"[ORDER EXECUTOR] Failed to mark order as failed: {inner_e}"
                )
            
            return False, error_msg
    
    # =========================================================================
    # VALIDATION METHODS
    # =========================================================================
    
    def _validate_order_for_execution(self, order: PaperOrder) -> bool:
        """
        Validate that an order can be executed.
        
        Args:
            order: PaperOrder to validate
            
        Returns:
            True if order can be executed, False otherwise
        """
        # Check order is active
        if not order.is_active():
            logger.warning(
                f"[ORDER EXECUTOR] Order {order.order_id} is not active "
                f"(status: {order.status})"
            )
            return False
        
        # Check order is not expired
        if order.is_expired():
            logger.warning(
                f"[ORDER EXECUTOR] Order {order.order_id} has expired"
            )
            return False
        
        # Check account has sufficient balance
        if order.amount_usd > self.account.balance:
            logger.warning(
                f"[ORDER EXECUTOR] Insufficient balance for order {order.order_id}. "
                f"Required: ${order.amount_usd}, Available: ${self.account.balance}"
            )
            return False
        
        return True
    
    # =========================================================================
    # TRADE EXECUTION METHODS
    # =========================================================================
    
    def _determine_trade_type(self, order: PaperOrder) -> str:
        """
        Determine the trade type (buy/sell) based on order type.
        
        Args:
            order: PaperOrder instance
            
        Returns:
            Trade type: 'buy' or 'sell'
        """
        # Buy orders: LIMIT_BUY, STOP_LIMIT_BUY
        if order.order_type in [OrderType.LIMIT_BUY, OrderType.STOP_LIMIT_BUY]:
            return 'buy'
        
        # Sell orders: LIMIT_SELL, STOP_LIMIT_SELL, TRAILING_STOP
        elif order.order_type in [
            OrderType.LIMIT_SELL,
            OrderType.STOP_LIMIT_SELL,
            OrderType.TRAILING_STOP
        ]:
            return 'sell'
        
        else:
            # Default to buy if unknown
            logger.warning(
                f"[ORDER EXECUTOR] Unknown order type: {order.order_type}, "
                f"defaulting to 'buy'"
            )
            return 'buy'
    
    def _execute_trade_via_simulator(
        self,
        order: PaperOrder,
        trade_type: str,
        execution_price: Decimal
    ) -> SimplePaperTradeResult:
        """
        Execute the trade through the SimplePaperTradingSimulator.
        
        Args:
            order: PaperOrder to execute
            trade_type: 'buy' or 'sell'
            execution_price: Current market price
            
        Returns:
            SimplePaperTradeResult with execution outcome
        """
        try:
            # Determine token addresses based on trade type
            if trade_type == 'buy':
                # Buying token with USD (USDC)
                # USDC address on Base Sepolia
                token_in = '0x036CbD53842c5426634e7929541eC2318f3dCF7e'
                token_out = order.token_address
                token_in_symbol = 'USDC'
                token_out_symbol = order.token_symbol
            else:
                # Selling token for USD (USDC)
                token_in = order.token_address
                # USDC address on Base Sepolia
                token_out = '0x036CbD53842c5426634e7929541eC2318f3dCF7e'
                token_in_symbol = order.token_symbol
                token_out_symbol = 'USDC'
            
            # Create trade request
            trade_request = SimplePaperTradeRequest(
                account=self.account,
                trade_type=trade_type,
                token_in=token_in,
                token_out=token_out,
                amount_in_usd=order.amount_usd,
                slippage_tolerance=Decimal('0.005')  # 0.5% slippage
            )
            
            logger.info(
                f"[ORDER EXECUTOR] Executing {trade_type} trade: "
                f"{token_in_symbol} → {token_out_symbol}, "
                f"Amount: ${order.amount_usd}"
            )
            
            # Execute through simulator
            result = self.simulator.execute_trade(trade_request)
            
            if result.success:
                logger.info(
                    f"[ORDER EXECUTOR] ✅ Trade executed successfully. "
                    f"Trade ID: {result.trade_id}, "
                    f"Gas Cost: ${result.gas_cost_usd}, "
                    f"Slippage: {result.slippage_percent}%"
                )
            else:
                logger.error(
                    f"[ORDER EXECUTOR] ❌ Trade execution failed: "
                    f"{result.error_message}"
                )
            
            return result
        
        except Exception as e:
            logger.error(
                f"[ORDER EXECUTOR] Exception during simulator execution: {e}",
                exc_info=True
            )
            
            # Return failed result
            return SimplePaperTradeResult(
                success=False,
                trade_id=str(uuid.uuid4()),
                error_message=f"Simulator exception: {e}"
            )
    
    # =========================================================================
    # ORDER STATUS UPDATE METHODS
    # =========================================================================
    
    def _mark_order_filled(
        self,
        order: PaperOrder,
        trade: Optional[PaperTrade],
        execution_price: Decimal,
        amount_token: Decimal
    ) -> None:
        """
        Mark an order as filled.
        
        Updates order status, filled amounts, average fill price, and timestamps.
        
        Args:
            order: PaperOrder to update
            trade: Associated PaperTrade record
            execution_price: Price at which order was executed
            amount_token: Amount of tokens filled
        """
        try:
            order.status = OrderStatus.FILLED
            order.filled_amount_usd = order.amount_usd
            order.filled_amount_token = amount_token
            order.average_fill_price = execution_price
            order.filled_at = timezone.now()
            
            # Link to trade if available
            if trade:
                order.related_trade = trade
            
            order.save(update_fields=[
                'status',
                'filled_amount_usd',
                'filled_amount_token',
                'average_fill_price',
                'filled_at',
                'related_trade'
            ])
            
            logger.info(
                f"[ORDER EXECUTOR] Order {order.order_id} marked as FILLED. "
                f"Fill price: ${execution_price}, Amount: {amount_token}"
            )
        
        except Exception as e:
            logger.error(
                f"[ORDER EXECUTOR] Failed to mark order {order.order_id} as filled: {e}",
                exc_info=True
            )
    
    def _mark_order_failed(
        self,
        order: PaperOrder,
        error_message: str
    ) -> None:
        """
        Mark an order as failed.
        
        Args:
            order: PaperOrder to update
            error_message: Reason for failure
        """
        try:
            order.status = OrderStatus.FAILED
            order.error_message = error_message
            order.save(update_fields=['status', 'error_message'])
            
            logger.info(
                f"[ORDER EXECUTOR] Order {order.order_id} marked as FAILED. "
                f"Reason: {error_message}"
            )
        
        except Exception as e:
            logger.error(
                f"[ORDER EXECUTOR] Failed to mark order {order.order_id} as failed: {e}",
                exc_info=True
            )
    
    # =========================================================================
    # NOTIFICATION METHODS
    # =========================================================================
    
    def _send_execution_notification(
        self,
        order: PaperOrder,
        trade: Optional[PaperTrade],
        success: bool,
        error: Optional[str] = None
    ) -> None:
        """
        Send WebSocket notification for order execution.
        
        Args:
            order: Executed PaperOrder
            trade: Associated PaperTrade (if successful)
            success: Whether execution was successful
            error: Error message (if failed)
        """
        try:
            # Build notification data
            notification_data = {
                'order_id': str(order.order_id),
                'order_type': order.order_type,
                'token_symbol': order.token_symbol,
                'token_address': order.token_address,
                'amount_usd': float(order.amount_usd),
                'status': order.status,
                'success': success,
                'executed_at': timezone.now().isoformat(),
            }
            
            # Add trade data if successful
            if success and trade:
                notification_data.update({
                    'trade_id': str(trade.trade_id),
                    'execution_price': float(order.average_fill_price) if order.average_fill_price else None,
                    'filled_amount_token': float(order.filled_amount_token) if order.filled_amount_token else None,
                    'gas_cost_usd': float(trade.simulated_gas_cost_usd),
                    'slippage_percent': float(trade.simulated_slippage_percent),
                })
            
            # Add error if failed
            if not success and error:
                notification_data['error_message'] = error
            
            # Send via WebSocket service
            websocket_service.send_update(
                account_id=self.account.account_id,
                message_type='order_executed',
                data=notification_data
            )
            
            logger.info(
                f"[ORDER EXECUTOR] Sent WebSocket notification for order "
                f"{order.order_id} (success={success})"
            )
        
        except Exception as e:
            logger.error(
                f"[ORDER EXECUTOR] Failed to send execution notification: {e}",
                exc_info=True
            )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_order_executor(account: PaperTradingAccount) -> OrderExecutor:
    """
    Get an OrderExecutor instance for the given account.
    
    Args:
        account: PaperTradingAccount for order execution
        
    Returns:
        OrderExecutor instance
        
    Example:
        executor = get_order_executor(account)
        success, message = executor.execute_order(order, current_price)
    """
    return OrderExecutor(account)


def execute_order(
    account: PaperTradingAccount,
    order: PaperOrder,
    current_price: Decimal
) -> Tuple[bool, str]:
    """
    Convenience function to execute an order.
    
    Args:
        account: PaperTradingAccount
        order: PaperOrder to execute
        current_price: Current market price
        
    Returns:
        Tuple of (success: bool, message: str)
        
    Example:
        success, message = execute_order(account, order, Decimal('2350.00'))
        if success:
            print(f"Order executed: {message}")
    """
    executor = OrderExecutor(account)
    return executor.execute_order(order, current_price)