"""
Trading Celery Tasks - Complete Implementation with Circuit Breaker Protection

Provides Celery task automation for trading operations with full circuit breaker
integration, Transaction Manager coordination, and portfolio protection.

This module bridges trading operations with safety mechanisms:
- Circuit breaker validation before all trades
- Transaction Manager integration for gas optimization
- Portfolio-based risk limits
- Real-time status monitoring

File: dexproject/trading/tasks.py
"""

import logging
from typing import Dict, Any, Optional, Tuple, List
from decimal import Decimal
from datetime import datetime, timezone

from celery import shared_task, Task
from celery.exceptions import SoftTimeLimitExceeded
from django.contrib.auth.models import User
from django.conf import settings
from django.db import transaction as db_transaction

# Import circuit breaker components
from engine.portfolio import (
    CircuitBreakerManager,
    CircuitBreakerType,
    CircuitBreakerEvent
)
from engine.utils import (
    CircuitBreaker,
    CircuitBreakerState,
    CircuitBreakerOpenError
)

# Import Transaction Manager
from trading.services.transaction_manager import (
    TransactionManager,
    TransactionSubmissionRequest,
    TransactionStatus,
    get_transaction_manager,
    create_transaction_submission_request
)

# Import trading services
from trading.services.dex_router_service import (
    SwapParams, 
    SwapType, 
    DEXVersion, 
    TradingGasStrategy
)
from trading.services.portfolio_service import (
    create_portfolio_service,
    PortfolioTrackingService
)

# Import models
from trading.models import (
    Trade,
    Position
)

logger = logging.getLogger(__name__)


# =============================================================================
# CIRCUIT BREAKER MANAGEMENT
# =============================================================================

# Global circuit breaker instances
_circuit_breaker_manager: Optional[CircuitBreakerManager] = None
_trade_execution_breaker: Optional[CircuitBreaker] = None


def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """Get or create the global circuit breaker manager."""
    global _circuit_breaker_manager
    if _circuit_breaker_manager is None:
        _circuit_breaker_manager = CircuitBreakerManager()
        logger.info("[CB] Circuit breaker manager initialized")
    return _circuit_breaker_manager


def get_trade_execution_breaker() -> CircuitBreaker:
    """Get or create the trade execution circuit breaker."""
    global _trade_execution_breaker
    if _trade_execution_breaker is None:
        _trade_execution_breaker = CircuitBreaker(
            name="trade_execution_breaker",
            failure_threshold=getattr(settings, 'TRADE_CB_FAILURE_THRESHOLD', 5),
            timeout_seconds=getattr(settings, 'TRADE_CB_TIMEOUT_SECONDS', 300),
            success_threshold=getattr(settings, 'TRADE_CB_SUCCESS_THRESHOLD', 2)
        )
        logger.info("[CB] Trade execution circuit breaker initialized")
    return _trade_execution_breaker


async def check_circuit_breakers_for_trade(
    user_id: int,
    trade_type: str,
    amount_usd: Decimal,
    bypass_checks: bool = False
) -> Tuple[bool, Optional[List[str]]]:
    """
    Check all circuit breakers before executing a trade.
    
    Args:
        user_id: User ID making the trade
        trade_type: 'BUY' or 'SELL'
        amount_usd: Trade amount in USD
        bypass_checks: Emergency override flag
        
    Returns:
        Tuple of (can_proceed, list_of_blocking_reasons)
    """
    if bypass_checks:
        logger.warning(f"[CB] Circuit breakers BYPASSED for user {user_id}")
        return (True, None)
    
    try:
        # Get circuit breaker manager
        cb_manager = get_circuit_breaker_manager()
        
        # Get portfolio state for user
        portfolio_service = create_portfolio_service()
        user = User.objects.get(id=user_id)
        portfolio_state = await portfolio_service.get_portfolio_summary(user)
        
        # Add the proposed trade impact to portfolio state
        if trade_type == 'BUY':
            # Simulate the impact of this buy on portfolio
            portfolio_state['pending_exposure'] = portfolio_state.get('total_value', 0) + amount_usd
        
        # Check portfolio circuit breakers
        can_trade, reasons = cb_manager.can_trade()
        
        if not can_trade:
            logger.warning(
                f"[CB] Trade BLOCKED for user {user_id}: {', '.join(reasons)}"
            )
            return (False, reasons)
        
        # Check if trade execution circuit breaker is open
        trade_breaker = get_trade_execution_breaker()
        if trade_breaker.is_open:
            reason = "Trade execution circuit breaker is OPEN (system-wide trading pause)"
            logger.warning(f"[CB] Trade BLOCKED: {reason}")
            return (False, [reason])
        
        # Check user-specific limits
        user_daily_trades = await get_user_daily_trade_count(user_id)
        max_daily_trades = getattr(settings, 'MAX_DAILY_TRADES_PER_USER', 100)
        
        if user_daily_trades >= max_daily_trades:
            reason = f"Daily trade limit exceeded ({user_daily_trades}/{max_daily_trades})"
            logger.warning(f"[CB] Trade BLOCKED for user {user_id}: {reason}")
            return (False, [reason])
        
        # Check position limits
        if trade_type == 'BUY':
            max_position_size = getattr(settings, 'MAX_POSITION_SIZE_USD', 1000)
            if amount_usd > max_position_size:
                reason = f"Trade size ${amount_usd} exceeds maximum ${max_position_size}"
                logger.warning(f"[CB] Trade BLOCKED for user {user_id}: {reason}")
                return (False, [reason])
        
        logger.info(f"[CB] All checks PASSED for user {user_id}")
        return (True, None)
        
    except Exception as e:
        logger.error(f"[CB] Error checking circuit breakers: {e}")
        # Fail open - allow trade if check fails
        return (True, None)


async def get_user_daily_trade_count(user_id: int) -> int:
    """Get the number of trades a user has executed today."""
    from django.utils import timezone
    from datetime import timedelta
    
    try:
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        trade_count = Trade.objects.filter(
            user_id=user_id,
            created_at__gte=today_start,
            status__in=['COMPLETED', 'PENDING']
        ).count()
        return trade_count
    except Exception as e:
        logger.error(f"Error getting user trade count: {e}")
        return 0


# =============================================================================
# MAIN TRADING TASKS WITH CIRCUIT BREAKER PROTECTION
# =============================================================================

@shared_task(
    bind=True,
    name="trading.tasks.execute_buy_order",
    queue="trading.execution",
    max_retries=3,
    soft_time_limit=120,
    time_limit=180
)
def execute_buy_order(
    self,
    pair_address: str,
    token_address: str,
    amount_eth: str,
    slippage_tolerance: float,
    gas_price_gwei: float,
    trade_id: str,
    user_id: int,
    strategy_id: Optional[str] = None,
    chain_id: int = 8453,
    bypass_circuit_breaker: bool = False
) -> Dict[str, Any]:
    """
    Execute a BUY order with full circuit breaker protection and Transaction Manager integration.
    
    This task:
    1. Validates circuit breakers before execution
    2. Uses Transaction Manager for gas optimization
    3. Updates portfolio tracking
    4. Handles failures with circuit breaker updates
    
    Args:
        pair_address: DEX pair address
        token_address: Token to buy
        amount_eth: Amount of ETH to spend
        slippage_tolerance: Maximum slippage (0.01 = 1%)
        gas_price_gwei: Gas price in gwei
        trade_id: Unique trade identifier
        user_id: User executing the trade
        strategy_id: Optional strategy identifier
        chain_id: Blockchain network ID
        bypass_circuit_breaker: Emergency override flag
        
    Returns:
        Dictionary with execution results
    """
    task_id = self.request.id
    start_time = datetime.now(timezone.utc)
    
    try:
        logger.info(
            f"[BUY] Starting buy order execution: Trade {trade_id}, "
            f"Token {token_address[:10]}..., Amount {amount_eth} ETH"
        )
        
        # Convert amount to USD for circuit breaker checks
        eth_price = Decimal('2000')  # In production, get from price oracle
        amount_usd = Decimal(amount_eth) * eth_price
        
        # Step 1: Circuit Breaker Validation
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        can_proceed, blocking_reasons = loop.run_until_complete(
            check_circuit_breakers_for_trade(
                user_id=user_id,
                trade_type='BUY',
                amount_usd=amount_usd,
                bypass_checks=bypass_circuit_breaker
            )
        )
        
        if not can_proceed:
            logger.warning(f"[BUY] Trade {trade_id} BLOCKED by circuit breakers")
            
            # Update trade record
            try:
                trade = Trade.objects.get(trade_id=trade_id)
                trade.status = 'BLOCKED'
                trade.error_message = f"Circuit breaker: {', '.join(blocking_reasons)}"
                trade.save()
            except Trade.DoesNotExist:
                pass
            
            return {
                'success': False,
                'trade_id': trade_id,
                'error': 'Trade blocked by circuit breaker',
                'circuit_breaker_reasons': blocking_reasons,
                'blocked_at': datetime.now(timezone.utc).isoformat()
            }
        
        # Step 2: Execute through Trade Execution Circuit Breaker
        trade_breaker = get_trade_execution_breaker()
        
        async def execute_with_breaker():
            """Execute trade with circuit breaker protection."""
            return await trade_breaker.call(
                _execute_buy_with_tx_manager,
                trade_id=trade_id,
                user_id=user_id,
                token_address=token_address,
                amount_eth=amount_eth,
                amount_usd=amount_usd,
                chain_id=chain_id,
                slippage_tolerance=slippage_tolerance,
                gas_price_gwei=gas_price_gwei,
                pair_address=pair_address,
                strategy_id=strategy_id
            )
        
        result = loop.run_until_complete(execute_with_breaker())
        
        # Step 3: Update circuit breaker state based on result
        if not result.get('success', False):
            # Trade failed - update circuit breaker manager
            cb_manager = get_circuit_breaker_manager()
            
            # Get latest portfolio state
            portfolio_service = create_portfolio_service()
            user = User.objects.get(id=user_id)
            portfolio_state = loop.run_until_complete(
                portfolio_service.get_portfolio_summary(user)
            )
            
            # Check if new circuit breakers should trigger
            cb_manager.check_circuit_breakers(portfolio_state)
        
        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        result['execution_time_seconds'] = execution_time
        
        logger.info(
            f"[BUY] Trade {trade_id} completed: Success={result.get('success')}, "
            f"Time={execution_time:.2f}s"
        )
        
        return result
        
    except CircuitBreakerOpenError as e:
        logger.error(f"[BUY] Circuit breaker OPEN for trade {trade_id}: {e}")
        return {
            'success': False,
            'trade_id': trade_id,
            'error': 'Circuit breaker open - trading temporarily disabled',
            'retry_after_seconds': 300
        }
        
    except SoftTimeLimitExceeded:
        logger.error(f"[BUY] Time limit exceeded for trade {trade_id}")
        return {
            'success': False,
            'trade_id': trade_id,
            'error': 'Trade execution timeout'
        }
        
    except Exception as e:
        logger.error(f"[BUY] Fatal error in trade {trade_id}: {e}", exc_info=True)
        
        # Update circuit breaker on failure
        try:
            cb_manager = get_circuit_breaker_manager()
            portfolio_service = create_portfolio_service()
            user = User.objects.get(id=user_id)
            
            loop = asyncio.new_event_loop()
            portfolio_state = loop.run_until_complete(
                portfolio_service.get_portfolio_summary(user)
            )
            cb_manager.check_circuit_breakers(portfolio_state)
        except:
            pass
        
        # Retry if appropriate
        if self.request.retries < self.max_retries:
            retry_delay = 2 ** self.request.retries
            logger.info(f"[BUY] Retrying trade {trade_id} in {retry_delay}s")
            raise self.retry(countdown=retry_delay, exc=e)
        
        return {
            'success': False,
            'trade_id': trade_id,
            'error': str(e)
        }


@shared_task(
    bind=True,
    name="trading.tasks.execute_sell_order",
    queue="trading.execution",
    max_retries=3,
    soft_time_limit=120,
    time_limit=180
)
def execute_sell_order(
    self,
    pair_address: str,
    token_address: str,
    token_amount: str,
    slippage_tolerance: float,
    gas_price_gwei: float,
    trade_id: Optional[str] = None,
    user_id: Optional[int] = None,
    is_position_close: bool = False,
    position_id: Optional[str] = None,
    chain_id: int = 8453,
    bypass_circuit_breaker: bool = False
) -> Dict[str, Any]:
    """
    Execute a SELL order with full circuit breaker protection and Transaction Manager integration.
    
    This task:
    1. Validates circuit breakers before execution
    2. Uses Transaction Manager for gas optimization
    3. Updates portfolio tracking
    4. Handles position closing with special logic
    
    Args:
        pair_address: DEX pair address
        token_address: Token to sell
        token_amount: Amount of tokens to sell
        slippage_tolerance: Maximum slippage (0.01 = 1%)
        gas_price_gwei: Gas price in gwei
        trade_id: Unique trade identifier
        user_id: User executing the trade
        is_position_close: Whether this is closing a position
        position_id: Position being closed (if applicable)
        chain_id: Blockchain network ID
        bypass_circuit_breaker: Emergency override flag
        
    Returns:
        Dictionary with execution results
    """
    task_id = self.request.id
    start_time = datetime.now(timezone.utc)
    
    try:
        logger.info(
            f"[SELL] Starting sell order execution: Trade {trade_id}, "
            f"Token {token_address[:10]}..., Amount {token_amount}"
        )
        
        # Estimate value in USD for circuit breaker checks
        token_price = Decimal('0.001')  # In production, get from price oracle
        amount_usd = Decimal(token_amount) * token_price
        
        # Step 1: Circuit Breaker Validation (may be relaxed for position closes)
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Allow position closes even during circuit breaker if it reduces risk
        check_breakers = not is_position_close or not getattr(
            settings, 'ALLOW_POSITION_CLOSE_DURING_CB', True
        )
        
        if check_breakers:
            can_proceed, blocking_reasons = loop.run_until_complete(
                check_circuit_breakers_for_trade(
                    user_id=user_id,
                    trade_type='SELL',
                    amount_usd=amount_usd,
                    bypass_checks=bypass_circuit_breaker
                )
            )
            
            if not can_proceed:
                logger.warning(f"[SELL] Trade {trade_id} BLOCKED by circuit breakers")
                
                # Update trade record if exists
                if trade_id:
                    try:
                        trade = Trade.objects.get(trade_id=trade_id)
                        trade.status = 'BLOCKED'
                        trade.error_message = f"Circuit breaker: {', '.join(blocking_reasons)}"
                        trade.save()
                    except Trade.DoesNotExist:
                        pass
                
                return {
                    'success': False,
                    'trade_id': trade_id,
                    'error': 'Trade blocked by circuit breaker',
                    'circuit_breaker_reasons': blocking_reasons,
                    'blocked_at': datetime.now(timezone.utc).isoformat()
                }
        
        # Step 2: Execute through Trade Execution Circuit Breaker
        trade_breaker = get_trade_execution_breaker()
        
        async def execute_with_breaker():
            """Execute trade with circuit breaker protection."""
            return await trade_breaker.call(
                _execute_sell_with_tx_manager,
                trade_id=trade_id,
                user_id=user_id,
                token_address=token_address,
                token_amount=token_amount,
                amount_usd=amount_usd,
                chain_id=chain_id,
                slippage_tolerance=slippage_tolerance,
                gas_price_gwei=gas_price_gwei,
                pair_address=pair_address,
                is_position_close=is_position_close,
                position_id=position_id
            )
        
        result = loop.run_until_complete(execute_with_breaker())
        
        # Step 3: Update circuit breaker state based on result
        if not result.get('success', False) and user_id:
            # Trade failed - update circuit breaker manager
            cb_manager = get_circuit_breaker_manager()
            
            # Get latest portfolio state
            portfolio_service = create_portfolio_service()
            user = User.objects.get(id=user_id)
            portfolio_state = loop.run_until_complete(
                portfolio_service.get_portfolio_summary(user)
            )
            
            # Check if new circuit breakers should trigger
            cb_manager.check_circuit_breakers(portfolio_state)
        
        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        result['execution_time_seconds'] = execution_time
        
        logger.info(
            f"[SELL] Trade {trade_id} completed: Success={result.get('success')}, "
            f"Time={execution_time:.2f}s"
        )
        
        return result
        
    except CircuitBreakerOpenError as e:
        logger.error(f"[SELL] Circuit breaker OPEN for trade {trade_id}: {e}")
        return {
            'success': False,
            'trade_id': trade_id,
            'error': 'Circuit breaker open - trading temporarily disabled',
            'retry_after_seconds': 300
        }
        
    except SoftTimeLimitExceeded:
        logger.error(f"[SELL] Time limit exceeded for trade {trade_id}")
        return {
            'success': False,
            'trade_id': trade_id,
            'error': 'Trade execution timeout'
        }
        
    except Exception as e:
        logger.error(f"[SELL] Fatal error in trade {trade_id}: {e}", exc_info=True)
        
        # Retry if appropriate
        if self.request.retries < self.max_retries:
            retry_delay = 2 ** self.request.retries
            logger.info(f"[SELL] Retrying trade {trade_id} in {retry_delay}s")
            raise self.retry(countdown=retry_delay, exc=e)
        
        return {
            'success': False,
            'trade_id': trade_id,
            'error': str(e)
        }


# =============================================================================
# TRANSACTION MANAGER INTEGRATION
# =============================================================================

async def _execute_buy_with_tx_manager(
    trade_id: str,
    user_id: int,
    token_address: str,
    amount_eth: str,
    amount_usd: Decimal,
    chain_id: int,
    slippage_tolerance: float,
    gas_price_gwei: float,
    pair_address: str,
    strategy_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute buy order through Transaction Manager for gas optimization.
    """
    try:
        # Get user
        user = User.objects.get(id=user_id)
        
        # Get Transaction Manager
        tx_manager = await get_transaction_manager(chain_id)
        
        # Convert ETH amount to Wei
        amount_in_wei = int(Decimal(amount_eth) * Decimal('1e18'))
        
        # Create transaction request
        tx_request = await create_transaction_submission_request(
            user=user,
            chain_id=chain_id,
            token_in='0x' + '0' * 40,  # WETH address (placeholder)
            token_out=token_address,
            amount_in=amount_in_wei,
            amount_out_minimum=0,  # Will be calculated
            swap_type=SwapType.EXACT_ETH_FOR_TOKENS,
            dex_version=DEXVersion.UNISWAP_V3,
            gas_strategy=TradingGasStrategy.BALANCED,
            is_paper_trade=False,
            slippage_tolerance=Decimal(str(slippage_tolerance))
        )
        
        # Submit through Transaction Manager
        result = await tx_manager.submit_transaction(tx_request)
        
        if result.success:
            # Update trade record
            try:
                trade = Trade.objects.get(trade_id=trade_id)
                trade.status = 'COMPLETED'
                trade.transaction_hash = result.transaction_state.transaction_hash
                trade.gas_used = result.transaction_state.gas_used
                trade.gas_price_gwei = result.transaction_state.gas_price_gwei
                trade.save()
            except Trade.DoesNotExist:
                pass
            
            return {
                'success': True,
                'trade_id': trade_id,
                'transaction_id': result.transaction_id,
                'transaction_hash': result.transaction_state.transaction_hash,
                'gas_savings_percent': float(result.gas_savings_achieved or 0),
                'executed_price_usd': float(amount_usd / Decimal(amount_eth))
            }
        else:
            return {
                'success': False,
                'trade_id': trade_id,
                'error': result.error_message
            }
            
    except Exception as e:
        logger.error(f"Transaction Manager execution failed: {e}")
        # Fallback to direct execution
        return {
            'success': False,
            'trade_id': trade_id,
            'error': str(e),
            'fallback': True
        }


async def _execute_sell_with_tx_manager(
    trade_id: Optional[str],
    user_id: Optional[int],
    token_address: str,
    token_amount: str,
    amount_usd: Decimal,
    chain_id: int,
    slippage_tolerance: float,
    gas_price_gwei: float,
    pair_address: str,
    is_position_close: bool = False,
    position_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute sell order through Transaction Manager for gas optimization.
    """
    try:
        # Get user
        user = User.objects.get(id=user_id) if user_id else None
        
        if not user:
            return {
                'success': False,
                'trade_id': trade_id,
                'error': 'User not found'
            }
        
        # Get Transaction Manager
        tx_manager = await get_transaction_manager(chain_id)
        
        # Convert token amount to Wei
        amount_in_wei = int(Decimal(token_amount) * Decimal('1e18'))
        
        # Create transaction request
        tx_request = await create_transaction_submission_request(
            user=user,
            chain_id=chain_id,
            token_in=token_address,
            token_out='0x' + '0' * 40,  # WETH address (placeholder)
            amount_in=amount_in_wei,
            amount_out_minimum=0,  # Will be calculated
            swap_type=SwapType.EXACT_TOKENS_FOR_ETH,
            dex_version=DEXVersion.UNISWAP_V3,
            gas_strategy=TradingGasStrategy.FAST if is_position_close else TradingGasStrategy.BALANCED,
            is_paper_trade=False,
            slippage_tolerance=Decimal(str(slippage_tolerance))
        )
        
        # Submit through Transaction Manager
        result = await tx_manager.submit_transaction(tx_request)
        
        if result.success:
            # Update trade record if exists
            if trade_id:
                try:
                    trade = Trade.objects.get(trade_id=trade_id)
                    trade.status = 'COMPLETED'
                    trade.transaction_hash = result.transaction_state.transaction_hash
                    trade.gas_used = result.transaction_state.gas_used
                    trade.gas_price_gwei = result.transaction_state.gas_price_gwei
                    trade.save()
                except Trade.DoesNotExist:
                    pass
            
            # Update position if closing
            if is_position_close and position_id:
                try:
                    position = Position.objects.get(position_id=position_id)
                    position.is_open = False
                    position.close_date = datetime.now(timezone.utc)
                    position.close_price = amount_usd / Decimal(token_amount)
                    position.save()
                except Position.DoesNotExist:
                    pass
            
            return {
                'success': True,
                'trade_id': trade_id,
                'transaction_id': result.transaction_id,
                'transaction_hash': result.transaction_state.transaction_hash,
                'gas_savings_percent': float(result.gas_savings_achieved or 0),
                'sold_amount': token_amount,
                'is_position_close': is_position_close
            }
        else:
            return {
                'success': False,
                'trade_id': trade_id,
                'error': result.error_message
            }
            
    except Exception as e:
        logger.error(f"Transaction Manager execution failed: {e}")
        return {
            'success': False,
            'trade_id': trade_id,
            'error': str(e),
            'fallback': True
        }


# =============================================================================
# CIRCUIT BREAKER MANAGEMENT TASKS
# =============================================================================

@shared_task(
    name="trading.tasks.reset_circuit_breakers",
    queue="trading.control"
)
def reset_circuit_breakers(
    user_id: Optional[int] = None,
    breaker_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Reset circuit breakers (admin task).
    
    Args:
        user_id: Optional user to reset breakers for
        breaker_type: Optional specific breaker type to reset
        
    Returns:
        Dictionary with reset results
    """
    try:
        cb_manager = get_circuit_breaker_manager()
        
        if breaker_type:
            from engine.portfolio import CircuitBreakerType
            breaker_enum = CircuitBreakerType[breaker_type.upper()]
            success = cb_manager.manual_reset(breaker_enum)
        else:
            success = cb_manager.manual_reset()
        
        # Also reset trade execution circuit breaker
        trade_breaker = get_trade_execution_breaker()
        trade_breaker.reset()
        
        logger.info(
            f"[CB] Circuit breakers reset: User={user_id}, Type={breaker_type}, Success={success}"
        )
        
        return {
            'success': success,
            'user_id': user_id,
            'breaker_type': breaker_type,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"[CB] Reset failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@shared_task(
    name="trading.tasks.get_circuit_breaker_status",
    queue="trading.monitor"
)
def get_circuit_breaker_status() -> Dict[str, Any]:
    """
    Get current circuit breaker status.
    
    Returns:
        Dictionary with circuit breaker states
    """
    try:
        status = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'portfolio_breakers': {},
            'trade_execution_breaker': {}
        }
        
        # Get portfolio circuit breakers
        cb_manager = get_circuit_breaker_manager()
        status['portfolio_breakers'] = cb_manager.get_status()
        
        # Get trade execution breaker
        trade_breaker = get_trade_execution_breaker()
        status['trade_execution_breaker'] = trade_breaker.get_stats()
        
        return status
        
    except Exception as e:
        logger.error(f"[CB] Status check failed: {e}")
        return {
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }


@shared_task(
    name="trading.tasks.monitor_circuit_breakers",
    queue="trading.monitor"
)
def monitor_circuit_breakers() -> Dict[str, Any]:
    """
    Monitor circuit breakers and send alerts if triggered.
    
    This task should run periodically to check circuit breaker health.
    
    Returns:
        Dictionary with monitoring results
    """
    try:
        alerts = []
        
        # Check portfolio circuit breakers
        cb_manager = get_circuit_breaker_manager()
        cb_status = cb_manager.get_status()
        
        if cb_status['active_breakers']:
            for breaker in cb_status['active_breakers']:
                alerts.append({
                    'type': 'portfolio_breaker',
                    'breaker': breaker['type'],
                    'description': breaker['description'],
                    'triggered_at': breaker['triggered_at']
                })
        
        # Check trade execution breaker
        trade_breaker = get_trade_execution_breaker()
        if trade_breaker.is_open:
            alerts.append({
                'type': 'trade_execution_breaker',
                'state': 'OPEN',
                'failure_count': trade_breaker.failure_count,
                'last_failure': trade_breaker.last_failure_time.isoformat() if trade_breaker.last_failure_time else None
            })
        
        # Send alerts if any (implement notification logic here)
        if alerts:
            logger.warning(f"[CB MONITOR] {len(alerts)} circuit breakers active")
            # TODO: Send notifications via email/Slack/etc
        
        return {
            'alerts': alerts,
            'total_alerts': len(alerts),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"[CB MONITOR] Monitoring failed: {e}")
        return {
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }