"""
Trading execution Celery tasks for the DEX auto-trading bot.

These tasks handle trade execution, position monitoring, and emergency exits.
All tasks are designed for the 'execution.critical' queue with very fast
execution times and minimal retry delays.
"""

import logging
import time
from typing import Dict, Any, Optional
from decimal import Decimal
from celery import shared_task
from django.utils import timezone
from django.db import transaction

from .models import Trade, Position, TradingPair, Strategy

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    queue='execution.critical',
    name='trading.tasks.execute_buy_order',
    max_retries=2,
    default_retry_delay=0.5
)
def execute_buy_order(
    self,
    pair_address: str,
    token_address: str,
    amount_eth: str,
    slippage_tolerance: float = 0.05,
    gas_price_gwei: Optional[float] = None,
    trade_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute a buy order for a token.
    
    Args:
        pair_address: The trading pair address
        token_address: The token to buy
        amount_eth: Amount of ETH to spend (as string for precision)
        slippage_tolerance: Maximum slippage allowed (0.05 = 5%)
        gas_price_gwei: Gas price in Gwei (auto if None)
        trade_id: Optional existing trade ID to update
        
    Returns:
        Dict with execution results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(
        f"Executing buy order for {token_address} - Amount: {amount_eth} ETH, "
        f"Slippage: {slippage_tolerance*100}% (task: {task_id})"
    )
    
    try:
        # Simulate trade execution
        time.sleep(0.1)  # Simulate network latency
        
        # Placeholder logic - in real implementation:
        # 1. Get current gas price or use provided gas_price_gwei
        # 2. Calculate minimum tokens to receive based on slippage
        # 3. Prepare swap transaction (e.g., Uniswap swapExactETHForTokens)
        # 4. Sign and submit transaction via preferred relay/RPC
        # 5. Monitor transaction for confirmation
        # 6. Update trade record with results
        
        amount_eth_decimal = Decimal(amount_eth)
        estimated_gas_price = gas_price_gwei or 20.0  # Default 20 Gwei
        estimated_gas_limit = 200000  # Typical for DEX swaps
        
        # Simulate successful execution
        transaction_hash = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        tokens_received = Decimal('1000000.5')  # Placeholder amount
        actual_price_per_token = amount_eth_decimal / tokens_received
        
        # Calculate actual slippage (placeholder)
        expected_tokens = tokens_received * Decimal('1.02')  # Assume 2% better than expected
        actual_slippage = float((expected_tokens - tokens_received) / expected_tokens)
        
        duration = time.time() - start_time
        
        result = {
            'task_id': task_id,
            'trade_id': trade_id,
            'operation': 'BUY',
            'pair_address': pair_address,
            'token_address': token_address,
            'amount_eth': amount_eth,
            'tokens_received': str(tokens_received),
            'transaction_hash': transaction_hash,
            'gas_price_gwei': estimated_gas_price,
            'gas_limit': estimated_gas_limit,
            'estimated_gas_cost_eth': str(Decimal(estimated_gas_price) * estimated_gas_limit / 1e9),
            'actual_slippage': actual_slippage,
            'slippage_tolerance': slippage_tolerance,
            'price_per_token_eth': str(actual_price_per_token),
            'execution_time_seconds': duration,
            'status': 'completed',
            'timestamp': timezone.now().isoformat()
        }
        
        logger.info(
            f"Buy order executed successfully - TX: {transaction_hash}, "
            f"Tokens: {tokens_received}, Time: {duration:.3f}s"
        )
        
        return result
        
    except Exception as exc:
        duration = time.time() - start_time
        logger.error(f"Buy order execution failed: {exc} (task: {task_id})")
        
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying buy order execution (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=0.5)
        
        return {
            'task_id': task_id,
            'trade_id': trade_id,
            'operation': 'BUY',
            'pair_address': pair_address,
            'token_address': token_address,
            'amount_eth': amount_eth,
            'error': str(exc),
            'execution_time_seconds': duration,
            'status': 'failed',
            'timestamp': timezone.now().isoformat()
        }


@shared_task(
    bind=True,
    queue='execution.critical',
    name='trading.tasks.execute_sell_order',
    max_retries=2,
    default_retry_delay=0.5
)
def execute_sell_order(
    self,
    pair_address: str,
    token_address: str,
    token_amount: str,
    slippage_tolerance: float = 0.05,
    gas_price_gwei: Optional[float] = None,
    trade_id: Optional[str] = None,
    is_emergency: bool = False
) -> Dict[str, Any]:
    """
    Execute a sell order for tokens.
    
    Args:
        pair_address: The trading pair address
        token_address: The token to sell
        token_amount: Amount of tokens to sell (as string for precision)
        slippage_tolerance: Maximum slippage allowed (0.05 = 5%)
        gas_price_gwei: Gas price in Gwei (auto if None)
        trade_id: Optional existing trade ID to update
        is_emergency: Whether this is an emergency exit (higher gas)
        
    Returns:
        Dict with execution results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(
        f"Executing sell order for {token_address} - Amount: {token_amount} tokens, "
        f"Emergency: {is_emergency} (task: {task_id})"
    )
    
    try:
        # Simulate trade execution
        time.sleep(0.08)  # Simulate network latency
        
        # Placeholder logic - in real implementation:
        # 1. Check token balance and allowance
        # 2. Approve token spending if needed (separate transaction)
        # 3. Calculate minimum ETH to receive based on slippage
        # 4. Prepare swap transaction (e.g., Uniswap swapExactTokensForETH)
        # 5. Use higher gas price if emergency exit
        # 6. Sign and submit transaction
        # 7. Monitor for confirmation
        
        token_amount_decimal = Decimal(token_amount)
        base_gas_price = 25.0 if is_emergency else 20.0
        estimated_gas_price = gas_price_gwei or base_gas_price
        estimated_gas_limit = 250000  # Higher for token swaps (approval might be needed)
        
        # Simulate successful execution
        transaction_hash = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        eth_received = Decimal('2.45')  # Placeholder amount
        actual_price_per_token = eth_received / token_amount_decimal
        
        # Calculate actual slippage (placeholder)
        expected_eth = eth_received * Decimal('0.97')  # Assume 3% worse than expected
        actual_slippage = float((expected_eth - eth_received) / expected_eth) if expected_eth > 0 else 0
        
        duration = time.time() - start_time
        
        result = {
            'task_id': task_id,
            'trade_id': trade_id,
            'operation': 'SELL',
            'pair_address': pair_address,
            'token_address': token_address,
            'token_amount': token_amount,
            'eth_received': str(eth_received),
            'transaction_hash': transaction_hash,
            'gas_price_gwei': estimated_gas_price,
            'gas_limit': estimated_gas_limit,
            'estimated_gas_cost_eth': str(Decimal(estimated_gas_price) * estimated_gas_limit / 1e9),
            'actual_slippage': actual_slippage,
            'slippage_tolerance': slippage_tolerance,
            'price_per_token_eth': str(actual_price_per_token),
            'is_emergency': is_emergency,
            'execution_time_seconds': duration,
            'status': 'completed',
            'timestamp': timezone.now().isoformat()
        }
        
        logger.info(
            f"Sell order executed successfully - TX: {transaction_hash}, "
            f"ETH received: {eth_received}, Time: {duration:.3f}s"
        )
        
        return result
        
    except Exception as exc:
        duration = time.time() - start_time
        logger.error(f"Sell order execution failed: {exc} (task: {task_id})")
        
        if self.request.retries < self.max_retries:
            retry_delay = 0.2 if is_emergency else 0.5
            logger.warning(f"Retrying sell order execution (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=retry_delay)
        
        return {
            'task_id': task_id,
            'trade_id': trade_id,
            'operation': 'SELL',
            'pair_address': pair_address,
            'token_address': token_address,
            'token_amount': token_amount,
            'is_emergency': is_emergency,
            'error': str(exc),
            'execution_time_seconds': duration,
            'status': 'failed',
            'timestamp': timezone.now().isoformat()
        }


@shared_task(
    bind=True,
    queue='execution.critical',
    name='trading.tasks.emergency_exit',
    max_retries=3,
    default_retry_delay=0.2
)
def emergency_exit(
    self,
    position_id: str,
    reason: str,
    max_slippage: float = 0.15
) -> Dict[str, Any]:
    """
    Execute an emergency exit from a position.
    
    Args:
        position_id: The position ID to exit
        reason: Reason for emergency exit
        max_slippage: Maximum slippage allowed (15% default for emergencies)
        
    Returns:
        Dict with emergency exit results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.warning(f"EMERGENCY EXIT initiated for position {position_id} - Reason: {reason} (task: {task_id})")
    
    try:
        # Simulate emergency exit
        time.sleep(0.05)  # Minimize delay for emergencies
        
        # Placeholder logic - in real implementation:
        # 1. Query current position details
        # 2. Calculate total token balance to exit
        # 3. Use highest priority gas (front-run if necessary)
        # 4. Accept higher slippage for immediate execution
        # 5. Submit emergency sell order
        # 6. Update position status immediately
        
        # Placeholder position data
        token_balance = Decimal('500000')
        token_address = "0x1234567890123456789012345678901234567890"
        pair_address = "0x0987654321098765432109876543210987654321"
        
        # Execute emergency sell with high gas price
        emergency_gas_price = 50.0  # High gas for front-running
        
        # Call sell order task with emergency parameters
        sell_result = execute_sell_order(
            pair_address=pair_address,
            token_address=token_address,
            token_amount=str(token_balance),
            slippage_tolerance=max_slippage,
            gas_price_gwei=emergency_gas_price,
            is_emergency=True
        )
        
        duration = time.time() - start_time
        
        result = {
            'task_id': task_id,
            'operation': 'EMERGENCY_EXIT',
            'position_id': position_id,
            'reason': reason,
            'token_balance_exited': str(token_balance),
            'max_slippage_allowed': max_slippage,
            'emergency_gas_price': emergency_gas_price,
            'sell_order_result': sell_result,
            'total_execution_time_seconds': duration,
            'status': 'completed' if sell_result.get('status') == 'completed' else 'failed',
            'timestamp': timezone.now().isoformat()
        }
        
        if result['status'] == 'completed':
            logger.warning(f"EMERGENCY EXIT completed for position {position_id} in {duration:.3f}s")
        else:
            logger.error(f"EMERGENCY EXIT FAILED for position {position_id}")
        
        return result
        
    except Exception as exc:
        duration = time.time() - start_time
        logger.error(f"Emergency exit failed for position {position_id}: {exc} (task: {task_id})")
        
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying emergency exit for position {position_id} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=0.1)  # Very fast retry for emergencies
        
        return {
            'task_id': task_id,
            'operation': 'EMERGENCY_EXIT',
            'position_id': position_id,
            'reason': reason,
            'error': str(exc),
            'total_execution_time_seconds': duration,
            'status': 'failed',
            'timestamp': timezone.now().isoformat()
        }


@shared_task(
    bind=True,
    queue='execution.critical',
    name='trading.tasks.update_stop_loss',
    max_retries=2,
    default_retry_delay=1
)
def update_stop_loss(
    self,
    position_id: str,
    new_stop_loss_price: str,
    trailing_percentage: Optional[float] = None
) -> Dict[str, Any]:
    """
    Update stop-loss for an active position.
    
    Args:
        position_id: The position ID to update
        new_stop_loss_price: New stop-loss price (as string for precision)
        trailing_percentage: Optional trailing stop percentage
        
    Returns:
        Dict with stop-loss update results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Updating stop-loss for position {position_id} to {new_stop_loss_price} (task: {task_id})")
    
    try:
        # Simulate stop-loss update
        time.sleep(0.02)  # Very fast for stop-loss updates
        
        # Placeholder logic - in real implementation:
        # 1. Validate new stop-loss price
        # 2. Update position record in database
        # 3. Update monitoring system
        # 4. Log the change for audit trail
        
        old_stop_loss = Decimal('1.50')  # Placeholder old value
        new_stop_loss = Decimal(new_stop_loss_price)
        
        # Validate stop-loss change
        if new_stop_loss <= 0:
            raise ValueError("Stop-loss price must be positive")
        
        duration = time.time() - start_time
        
        result = {
            'task_id': task_id,
            'operation': 'UPDATE_STOP_LOSS',
            'position_id': position_id,
            'old_stop_loss_price': str(old_stop_loss),
            'new_stop_loss_price': new_stop_loss_price,
            'trailing_percentage': trailing_percentage,
            'price_change': str(new_stop_loss - old_stop_loss),
            'execution_time_seconds': duration,
            'status': 'completed',
            'timestamp': timezone.now().isoformat()
        }
        
        logger.info(f"Stop-loss updated for position {position_id} in {duration:.3f}s")
        return result
        
    except Exception as exc:
        duration = time.time() - start_time
        logger.error(f"Stop-loss update failed for position {position_id}: {exc} (task: {task_id})")
        
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying stop-loss update for position {position_id} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=1)
        
        return {
            'task_id': task_id,
            'operation': 'UPDATE_STOP_LOSS',
            'position_id': position_id,
            'new_stop_loss_price': new_stop_loss_price,
            'error': str(exc),
            'execution_time_seconds': duration,
            'status': 'failed',
            'timestamp': timezone.now().isoformat()
        }


@shared_task(
    bind=True,
    queue='execution.critical',
    name='trading.tasks.monitor_position',
    max_retries=1,
    default_retry_delay=2
)
def monitor_position(
    self,
    position_id: str,
    check_stop_loss: bool = True,
    check_take_profit: bool = True
) -> Dict[str, Any]:
    """
    Monitor a position for stop-loss and take-profit triggers.
    
    Args:
        position_id: The position ID to monitor
        check_stop_loss: Whether to check stop-loss triggers
        check_take_profit: Whether to check take-profit triggers
        
    Returns:
        Dict with monitoring results and any triggered actions
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.debug(f"Monitoring position {position_id} (task: {task_id})")
    
    try:
        # Simulate position monitoring
        time.sleep(0.03)  # Very fast monitoring check
        
        # Placeholder logic - in real implementation:
        # 1. Get current token price
        # 2. Get position details (entry price, stop-loss, take-profit)
        # 3. Calculate current P&L
        # 4. Check if stop-loss or take-profit should trigger
        # 5. Execute exit orders if triggered
        
        # Placeholder position data
        entry_price = Decimal('2.50')
        current_price = Decimal('3.10')  # 24% gain
        stop_loss_price = Decimal('2.00')  # 20% loss limit
        take_profit_price = Decimal('3.75')  # 50% gain target
        position_size = Decimal('100000')
        
        current_pnl = (current_price - entry_price) * position_size
        current_pnl_percent = float((current_price - entry_price) / entry_price * 100)
        
        triggered_actions = []
        
        # Check stop-loss trigger
        if check_stop_loss and current_price <= stop_loss_price:
            logger.warning(f"Stop-loss triggered for position {position_id} at price {current_price}")
            # Would trigger emergency_exit here
            triggered_actions.append({
                'action': 'STOP_LOSS_TRIGGERED',
                'trigger_price': str(current_price),
                'stop_loss_price': str(stop_loss_price)
            })
        
        # Check take-profit trigger
        if check_take_profit and current_price >= take_profit_price:
            logger.info(f"Take-profit triggered for position {position_id} at price {current_price}")
            # Would trigger sell order here
            triggered_actions.append({
                'action': 'TAKE_PROFIT_TRIGGERED',
                'trigger_price': str(current_price),
                'take_profit_price': str(take_profit_price)
            })
        
        duration = time.time() - start_time
        
        result = {
            'task_id': task_id,
            'operation': 'MONITOR_POSITION',
            'position_id': position_id,
            'current_price': str(current_price),
            'entry_price': str(entry_price),
            'stop_loss_price': str(stop_loss_price),
            'take_profit_price': str(take_profit_price),
            'current_pnl': str(current_pnl),
            'current_pnl_percent': current_pnl_percent,
            'triggered_actions': triggered_actions,
            'execution_time_seconds': duration,
            'status': 'completed',
            'timestamp': timezone.now().isoformat()
        }
        
        if triggered_actions:
            logger.info(f"Position {position_id} monitoring completed with {len(triggered_actions)} triggers in {duration:.3f}s")
        else:
            logger.debug(f"Position {position_id} monitoring completed - no triggers in {duration:.3f}s")
        
        return result
        
    except Exception as exc:
        duration = time.time() - start_time
        logger.error(f"Position monitoring failed for {position_id}: {exc} (task: {task_id})")
        
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying position monitoring for {position_id} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=2)
        
        return {
            'task_id': task_id,
            'operation': 'MONITOR_POSITION',
            'position_id': position_id,
            'error': str(exc),
            'execution_time_seconds': duration,
            'status': 'failed',
            'timestamp': timezone.now().isoformat()
        }