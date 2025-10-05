"""
Paper Trading Celery Tasks - Complete Implementation

Provides Celery task automation for paper trading bot operations, integrating
with the Transaction Manager from Phase 6B for unified trade execution.

This module bridges the gap between API endpoints and bot execution, enabling:
- Automated bot lifecycle management via Celery
- Transaction Manager integration for paper trades
- Real-time status monitoring and updates
- Proper user authentication handling

File: dexproject/paper_trading/tasks.py
"""

import logging
import asyncio
import time
from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import datetime, timedelta

from celery import shared_task, Task
from celery.exceptions import SoftTimeLimitExceeded
from django.utils import timezone
from django.db import transaction
from django.contrib.auth.models import User
from django.conf import settings
from asgiref.sync import async_to_sync

# Import paper trading models
from paper_trading.models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingSession,
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    PaperPerformanceMetrics
)

# Import the enhanced bot
from paper_trading.bot.simple_trader import EnhancedPaperTradingBot

# Import services
from paper_trading.services.websocket_service import websocket_service
# Note: SimplePaperTradingSimulator is the actual class name in simulator.py
from paper_trading.services.simulator import SimplePaperTradingSimulator as TradingSimulator

# Import Transaction Manager for Phase 6B integration
from trading.services.transaction_manager import (
    TransactionManager,
    TransactionSubmissionRequest,
    TransactionStatus,
    get_transaction_manager,
    create_transaction_submission_request
)

# Import trading services
from trading.services.dex_router_service import (
    SwapParams, SwapType, DEXVersion, TradingGasStrategy
)

# Import engine configuration
from engine.config import config

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def run_async_task(coro):
    """Helper to run async code in sync Celery task."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(coro)


async def get_transaction_manager_for_paper_trading(chain_id: int) -> Optional[TransactionManager]:
    """
    Get transaction manager configured for paper trading.
    
    Args:
        chain_id: Blockchain network ID
        
    Returns:
        Transaction manager instance or None if unavailable
    """
    try:
        tx_manager = await get_transaction_manager(chain_id)
        logger.info(f"[PAPER] Transaction Manager initialized for chain {chain_id}")
        return tx_manager
    except Exception as e:
        logger.warning(f"[PAPER] Transaction Manager not available: {e}")
        return None


# =============================================================================
# BOT LIFECYCLE TASKS
# =============================================================================

@shared_task(
    bind=True,
    name='paper_trading.tasks.run_paper_trading_bot',
    queue='paper_trading.bot',
    max_retries=3,
    soft_time_limit=3600,  # 1 hour soft limit
    time_limit=3900,  # 1 hour 5 min hard limit
)
def run_paper_trading_bot(
    self,
    session_id: str,
    user_id: Optional[int] = None,
    use_transaction_manager: bool = True
) -> Dict[str, Any]:
    """
    Run the paper trading bot for a specific session.
    
    This task manages the complete lifecycle of a paper trading bot session,
    including Transaction Manager integration for Phase 6B benefits.
    
    Args:
        session_id: Trading session UUID
        user_id: Optional user ID (uses session.account.user if not provided)
        use_transaction_manager: Whether to use Transaction Manager for trades
        
    Returns:
        Dictionary with bot execution results
    """
    task_id = self.request.id
    start_time = time.time()
    bot_instance = None
    
    try:
        logger.info(f"[BOT] Starting paper trading bot for session {session_id}")
        
        # Get session
        try:
            session = PaperTradingSession.objects.get(session_id=session_id)
        except PaperTradingSession.DoesNotExist:
            raise ValueError(f"Session {session_id} not found")
        
        # Validate session state
        if session.status not in ['STARTING', 'RUNNING']:
            logger.warning(f"[BOT] Session {session_id} not in startable state: {session.status}")
            return {
                'success': False,
                'error': f'Session is {session.status}, cannot start bot',
                'session_id': session_id
            }
        
        # Update session status
        session.status = 'RUNNING'
        session.save()
        
        # Get user (use provided user_id or session's account user)
        if user_id:
            user = User.objects.get(id=user_id)
        else:
            user = session.account.user
        
        # Initialize bot
        logger.info(f"[BOT] Initializing bot for account {session.account.account_id}")
        bot_instance = EnhancedPaperTradingBot(account_id=session.account.pk)
        
        # Configure bot with Transaction Manager if available
        if use_transaction_manager:
            try:
                chain_id = getattr(settings, 'DEFAULT_CHAIN_ID', 8453)  # Base mainnet
                tx_manager = run_async_task(
                    get_transaction_manager_for_paper_trading(chain_id)
                )
                
                if tx_manager:
                    bot_instance.transaction_manager = tx_manager
                    bot_instance.use_transaction_manager = True
                    logger.info("[BOT] Transaction Manager integrated successfully")
                else:
                    logger.warning("[BOT] Transaction Manager not available, using direct execution")
            except Exception as e:
                logger.warning(f"[BOT] Failed to integrate Transaction Manager: {e}")
        
        # Initialize bot systems
        if not bot_instance.initialize():
            raise RuntimeError("Bot initialization failed")
        
        # Send WebSocket update
        async_to_sync(websocket_service.send_bot_status_update)(
            session_id=str(session.session_id),
            status='running',
            message='Paper trading bot is running'
        )
        
        # Run bot main loop
        logger.info(f"[BOT] Entering main trading loop for session {session_id}")
        
        tick_count = 0
        max_ticks = 720  # 1 hour at 5-second ticks
        tick_interval = 5  # seconds
        
        while tick_count < max_ticks:
            # Check if we should stop
            session.refresh_from_db()
            if session.status in ['STOPPING', 'STOPPED', 'ERROR']:
                logger.info(f"[BOT] Session {session_id} requested stop: {session.status}")
                break
            
            # Check for soft time limit
            if time.time() - start_time > 3500:  # Stop before soft limit
                logger.warning(f"[BOT] Approaching time limit, stopping gracefully")
                break
            
            # Execute bot tick
            try:
                bot_instance.tick()
                tick_count += 1
                
                # Send periodic status updates
                if tick_count % 12 == 0:  # Every minute
                    _send_bot_metrics_update(session, bot_instance)
                
                # Sleep between ticks
                time.sleep(tick_interval)
                
            except Exception as tick_error:
                logger.error(f"[BOT] Error during tick {tick_count}: {tick_error}")
                # Continue running unless it's critical
                if "critical" in str(tick_error).lower():
                    break
        
        # Finalize session
        duration = time.time() - start_time
        
        # Calculate final metrics
        final_metrics = _calculate_session_metrics(session)
        
        # Update session
        session.status = 'COMPLETED'
        session.ended_at = timezone.now()
        session.ending_balance_usd = session.account.current_balance_usd
        session.session_pnl_usd = session.account.current_balance_usd - session.starting_balance_usd
        session.total_trades_executed = final_metrics['total_trades']
        session.save()
        
        logger.info(
            f"[BOT] Session {session_id} completed: "
            f"Duration={duration:.1f}s, Trades={final_metrics['total_trades']}, "
            f"P&L=${session.session_pnl_usd:.2f}"
        )
        
        return {
            'success': True,
            'session_id': str(session.session_id),
            'duration_seconds': duration,
            'tick_count': tick_count,
            'metrics': final_metrics,
            'final_balance': float(session.account.current_balance_usd),
            'pnl': float(session.session_pnl_usd),
            'status': 'completed'
        }
        
    except SoftTimeLimitExceeded:
        logger.warning(f"[BOT] Soft time limit exceeded for session {session_id}")
        if session:
            session.status = 'STOPPED'
            session.ended_at = timezone.now()
            session.save()
        return {
            'success': False,
            'error': 'Time limit exceeded',
            'session_id': session_id
        }
        
    except Exception as e:
        logger.error(f"[BOT] Fatal error in session {session_id}: {e}", exc_info=True)
        
        # Update session status
        try:
            session.status = 'ERROR'
            session.ended_at = timezone.now()
            session.error_message = str(e)
            session.save()
        except:
            pass
        
        # Retry if appropriate
        if self.request.retries < self.max_retries:
            retry_delay = 2 ** self.request.retries
            logger.info(f"[BOT] Retrying session {session_id} in {retry_delay}s")
            raise self.retry(countdown=retry_delay, exc=e)
        
        return {
            'success': False,
            'error': str(e),
            'session_id': session_id,
            'task_id': task_id
        }
        
    finally:
        # Cleanup
        if bot_instance:
            try:
                bot_instance.shutdown()
            except:
                pass


@shared_task(
    bind=True,
    name='paper_trading.tasks.stop_paper_trading_bot',
    queue='paper_trading.control',
    max_retries=3
)
def stop_paper_trading_bot(
    self,
    session_id: str,
    reason: str = "User requested stop"
) -> Dict[str, Any]:
    """
    Stop a running paper trading bot session.
    
    Args:
        session_id: Trading session UUID to stop
        reason: Reason for stopping the bot
        
    Returns:
        Dictionary with stop operation results
    """
    try:
        logger.info(f"[BOT] Stopping session {session_id}: {reason}")
        
        # Get session
        try:
            session = PaperTradingSession.objects.get(session_id=session_id)
        except PaperTradingSession.DoesNotExist:
            return {
                'success': False,
                'error': f'Session {session_id} not found'
            }
        
        # Update session status
        previous_status = session.status
        session.status = 'STOPPING'
        session.save()
        
        # Calculate final metrics
        final_metrics = _calculate_session_metrics(session)
        
        # Finalize session
        with transaction.atomic():
            session.status = 'STOPPED'
            session.ended_at = timezone.now()
            session.ending_balance_usd = session.account.current_balance_usd
            session.session_pnl_usd = session.account.current_balance_usd - session.starting_balance_usd
            session.total_trades_executed = final_metrics['total_trades']
            session.save()
        
        # Send WebSocket notification
        async_to_sync(websocket_service.send_bot_status_update)(
            session_id=str(session.session_id),
            status='stopped',
            message=reason
        )
        
        logger.info(
            f"[BOT] Session {session_id} stopped successfully. "
            f"Previous status: {previous_status}, "
            f"P&L: ${session.session_pnl_usd:.2f}"
        )
        
        return {
            'success': True,
            'session_id': str(session.session_id),
            'previous_status': previous_status,
            'reason': reason,
            'final_metrics': final_metrics,
            'pnl': float(session.session_pnl_usd)
        }
        
    except Exception as e:
        logger.error(f"[BOT] Error stopping session {session_id}: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'session_id': session_id
        }


@shared_task(
    name='paper_trading.tasks.monitor_paper_trading_session',
    queue='paper_trading.monitor'
)
def monitor_paper_trading_session(session_id: str) -> Dict[str, Any]:
    """
    Monitor and update the status of a paper trading session.
    
    This task checks session health, updates metrics, and handles
    stuck or failed sessions.
    
    Args:
        session_id: Trading session UUID to monitor
        
    Returns:
        Dictionary with monitoring results
    """
    try:
        session = PaperTradingSession.objects.get(session_id=session_id)
        
        # Check session age
        session_age = timezone.now() - session.started_at
        
        # Handle stuck sessions
        if session.status == 'RUNNING' and session_age > timedelta(hours=2):
            logger.warning(f"[MONITOR] Session {session_id} stuck, auto-stopping")
            return stop_paper_trading_bot.apply_async(
                args=[session_id, "Auto-stopped due to timeout"]
            ).get()
        
        # Calculate current metrics
        metrics = _calculate_session_metrics(session)
        
        # Update performance metrics
        _update_performance_metrics(session, metrics)
        
        # Send status update
        async_to_sync(websocket_service.send_session_metrics)(
            session_id=str(session.session_id),
            metrics=metrics
        )
        
        return {
            'success': True,
            'session_id': str(session.session_id),
            'status': session.status,
            'age_minutes': session_age.total_seconds() / 60,
            'metrics': metrics
        }
        
    except Exception as e:
        logger.error(f"[MONITOR] Error monitoring session {session_id}: {e}")
        return {
            'success': False,
            'error': str(e),
            'session_id': session_id
        }


# =============================================================================
# PAPER TRADING WITH TRANSACTION MANAGER
# =============================================================================

@shared_task(
    bind=True,
    name='paper_trading.tasks.execute_paper_trade_with_tx_manager',
    queue='paper_trading.execution',
    max_retries=3
)
def execute_paper_trade_with_tx_manager(
    self,
    account_id: int,
    trade_type: str,  # 'BUY' or 'SELL'
    token_address: str,
    amount: str,
    chain_id: int = 8453,
    slippage_tolerance: float = 0.005
) -> Dict[str, Any]:
    """
    Execute a paper trade using the Transaction Manager from Phase 6B.
    
    This provides paper trades with the same gas optimization analytics
    and transaction lifecycle management as live trades.
    
    Args:
        account_id: Paper trading account ID
        trade_type: 'BUY' or 'SELL'
        token_address: Token to trade
        amount: Amount in USD (for buys) or tokens (for sells)
        chain_id: Blockchain network ID
        slippage_tolerance: Maximum acceptable slippage
        
    Returns:
        Dictionary with trade execution results including gas metrics
    """
    try:
        logger.info(
            f"[TX PAPER] Executing {trade_type} via Transaction Manager: "
            f"Token={token_address[:10]}..., Amount={amount}"
        )
        
        # Get account and user
        account = PaperTradingAccount.objects.get(pk=account_id)
        user = account.user
        
        # Execute through Transaction Manager
        async def execute_with_tx_manager():
            # Get transaction manager
            tx_manager = await get_transaction_manager_for_paper_trading(chain_id)
            
            if not tx_manager:
                # Fallback to simulator if Transaction Manager unavailable
                logger.warning("[TX PAPER] Transaction Manager unavailable, using simulator")
                return _execute_simulated_trade(account, trade_type, token_address, amount)
            
            # Prepare swap parameters based on trade type
            chain_config = config.get_chain_config(chain_id)
            weth_address = chain_config.weth_address if chain_config else None
            
            if trade_type == 'BUY':
                # Convert USD to ETH amount (mock price)
                eth_price = Decimal('2000')
                eth_amount = Decimal(amount) / eth_price
                amount_in_wei = int(eth_amount * Decimal('1e18'))
                
                swap_params = SwapParams(
                    token_in=weth_address,
                    token_out=token_address,
                    amount_in=amount_in_wei,
                    amount_out_minimum=0,  # Will be calculated by TX manager
                    swap_type=SwapType.EXACT_ETH_FOR_TOKENS,
                    dex_version=DEXVersion.UNISWAP_V3,
                    fee_tier=3000,
                    slippage_tolerance=Decimal(str(slippage_tolerance))
                )
            else:  # SELL
                amount_in_wei = int(Decimal(amount) * Decimal('1e18'))
                
                swap_params = SwapParams(
                    token_in=token_address,
                    token_out=weth_address,
                    amount_in=amount_in_wei,
                    amount_out_minimum=0,
                    swap_type=SwapType.EXACT_TOKENS_FOR_ETH,
                    dex_version=DEXVersion.UNISWAP_V3,
                    fee_tier=3000,
                    slippage_tolerance=Decimal(str(slippage_tolerance))
                )
            
            # Create transaction submission request
            tx_request = TransactionSubmissionRequest(
                user=user,
                chain_id=chain_id,
                swap_params=swap_params,
                gas_strategy=TradingGasStrategy.PAPER_TRADING,
                is_paper_trade=True,
                priority="normal"
            )
            
            # Submit through transaction manager
            result = await tx_manager.submit_transaction(tx_request)
            
            if result.success:
                # Create paper trade record
                paper_trade = PaperTrade.objects.create(
                    account=account,
                    trade_type=trade_type,
                    token_address=token_address,
                    amount_usd=Decimal(amount) if trade_type == 'BUY' else None,
                    token_amount=Decimal(amount) if trade_type == 'SELL' else None,
                    price_usd=Decimal('0.001'),  # Mock price
                    transaction_id=result.transaction_id,
                    status='COMPLETED',
                    gas_used=result.transaction_state.gas_used if result.transaction_state else 0,
                    gas_price_gwei=result.transaction_state.gas_price_gwei if result.transaction_state else 20,
                    metadata={
                        'tx_manager': True,
                        'gas_savings': float(result.gas_savings_achieved) if result.gas_savings_achieved else 0
                    }
                )
                
                # Update account balance
                if trade_type == 'BUY':
                    account.current_balance_usd -= Decimal(amount)
                else:
                    # Mock conversion to USD
                    account.current_balance_usd += Decimal(amount) * Decimal('0.001')
                account.save()
                
                return {
                    'success': True,
                    'trade_id': paper_trade.trade_id,
                    'transaction_id': result.transaction_id,
                    'gas_savings_percent': float(result.gas_savings_achieved or 0),
                    'execution_time_ms': result.transaction_state.execution_time_ms if result.transaction_state else 100
                }
            else:
                return {
                    'success': False,
                    'error': result.error_message
                }
        
        result = run_async_task(execute_with_tx_manager())
        return result
        
    except Exception as e:
        logger.error(f"[TX PAPER] Trade execution failed: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }


def _execute_simulated_trade(
    account: PaperTradingAccount,
    trade_type: str,
    token_address: str,
    amount: str
) -> Dict[str, Any]:
    """Fallback simulated trade execution without Transaction Manager."""
    from paper_trading.services.simulator import (
        SimplePaperTradingSimulator,
        SimplePaperTradeRequest
    )
    
    simulator = SimplePaperTradingSimulator()
    
    # Create trade request
    request = SimplePaperTradeRequest(
        account=account,
        trade_type=trade_type.lower(),
        token_in='WETH' if trade_type == 'BUY' else token_address,
        token_out=token_address if trade_type == 'BUY' else 'WETH',
        amount_in_usd=Decimal(amount)
    )
    
    # Execute through simulator
    result = simulator.execute_trade(request)
    
    if result.success:
        return {
            'success': True,
            'trade_id': result.trade_id,
            'simulated': True
        }
    
    return {
        'success': False,
        'error': result.error_message or 'Simulation failed'
    }


# =============================================================================
# METRICS AND ANALYTICS
# =============================================================================

@shared_task(
    name='paper_trading.tasks.calculate_paper_trading_analytics',
    queue='paper_trading.analytics'
)
def calculate_paper_trading_analytics(
    account_id: Optional[int] = None,
    session_id: Optional[str] = None,
    time_period_hours: int = 24
) -> Dict[str, Any]:
    """
    Calculate comprehensive analytics for paper trading.
    
    Args:
        account_id: Optional account ID to filter by
        session_id: Optional session ID to filter by
        time_period_hours: Time period for analytics calculation
        
    Returns:
        Dictionary with analytics data
    """
    try:
        cutoff_time = timezone.now() - timedelta(hours=time_period_hours)
        
        # Build query filters
        filters = {'created_at__gte': cutoff_time}
        if account_id:
            filters['account_id'] = account_id
        if session_id:
            filters['account__papertradingsession__session_id'] = session_id
        
        # Get trades
        trades = PaperTrade.objects.filter(**filters)
        
        # Calculate metrics
        total_trades = trades.count()
        buy_trades = trades.filter(trade_type='BUY').count()
        sell_trades = trades.filter(trade_type='SELL').count()
        
        # Calculate volumes
        from django.db.models import Sum
        total_volume = trades.aggregate(
            volume=Sum('amount_usd')
        )['volume'] or Decimal('0')
        
        # Get positions
        position_filters = {'created_at__gte': cutoff_time}
        if account_id:
            position_filters['account_id'] = account_id
            
        positions = PaperPosition.objects.filter(**position_filters)
        open_positions = positions.filter(is_open=True).count()
        closed_positions = positions.filter(is_open=False).count()
        
        # Calculate P&L
        total_pnl = positions.filter(is_open=False).aggregate(
            pnl=Sum('realized_pnl_usd')
        )['pnl'] or Decimal('0')
        
        # Win rate
        profitable_positions = positions.filter(
            is_open=False,
            realized_pnl_usd__gt=0
        ).count()
        
        win_rate = (profitable_positions / max(closed_positions, 1)) * 100
        
        analytics = {
            'period_hours': time_period_hours,
            'total_trades': total_trades,
            'buy_trades': buy_trades,
            'sell_trades': sell_trades,
            'total_volume': float(total_volume),
            'open_positions': open_positions,
            'closed_positions': closed_positions,
            'total_pnl': float(total_pnl),
            'win_rate': float(win_rate),
            'timestamp': timezone.now().isoformat()
        }
        
        logger.info(f"[ANALYTICS] Calculated: {total_trades} trades, P&L=${total_pnl:.2f}")
        
        return analytics
        
    except Exception as e:
        logger.error(f"[ANALYTICS] Error calculating analytics: {e}")
        return {
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _calculate_session_metrics(session: PaperTradingSession) -> Dict[str, Any]:
    """Calculate comprehensive metrics for a trading session."""
    try:
        # Get trades for this session
        trades = PaperTrade.objects.filter(
            account=session.account,
            created_at__gte=session.started_at
        )
        
        # Get positions
        positions = PaperPosition.objects.filter(
            account=session.account,
            created_at__gte=session.started_at
        )
        
        # Calculate metrics
        total_trades = trades.count()
        total_volume = sum(t.amount_usd or 0 for t in trades)
        
        closed_positions = positions.filter(is_open=False)
        profitable_trades = closed_positions.filter(realized_pnl_usd__gt=0).count()
        
        win_rate = (profitable_trades / max(closed_positions.count(), 1)) * 100
        
        return {
            'total_trades': total_trades,
            'total_volume': float(total_volume),
            'win_rate': float(win_rate),
            'open_positions': positions.filter(is_open=True).count(),
            'closed_positions': closed_positions.count(),
            'session_pnl': float(session.account.current_balance_usd - session.starting_balance_usd)
        }
        
    except Exception as e:
        logger.error(f"Error calculating session metrics: {e}")
        return {
            'total_trades': 0,
            'total_volume': 0.0,
            'win_rate': 0.0,
            'open_positions': 0,
            'closed_positions': 0,
            'session_pnl': 0.0
        }


def _update_performance_metrics(
    session: PaperTradingSession,
    metrics: Dict[str, Any]
) -> None:
    """Update or create performance metrics for a session."""
    try:
        PaperPerformanceMetrics.objects.update_or_create(
            session=session,
            period_start=session.started_at,
            period_end=timezone.now(),
            defaults={
                'total_trades': metrics['total_trades'],
                'winning_trades': int(metrics['win_rate'] * metrics.get('closed_positions', 0) / 100),
                'losing_trades': metrics.get('closed_positions', 0) - int(metrics['win_rate'] * metrics.get('closed_positions', 0) / 100),
                'win_rate': Decimal(str(metrics['win_rate'])),
                'total_pnl_usd': Decimal(str(metrics['session_pnl'])),
                'total_pnl_percent': (Decimal(str(metrics['session_pnl'])) / session.starting_balance_usd * 100) if session.starting_balance_usd > 0 else 0
            }
        )
    except Exception as e:
        logger.error(f"Failed to update performance metrics: {e}")


def _send_bot_metrics_update(
    session: PaperTradingSession,
    bot_instance: EnhancedPaperTradingBot
) -> None:
    """Send real-time metrics update via WebSocket."""
    try:
        metrics = _calculate_session_metrics(session)
        
        # Add bot-specific metrics if available
        if hasattr(bot_instance, 'get_current_metrics'):
            bot_metrics = bot_instance.get_current_metrics()
            metrics.update(bot_metrics)
        
        async_to_sync(websocket_service.send_session_metrics)(
            session_id=str(session.session_id),
            metrics=metrics
        )
    except Exception as e:
        logger.error(f"Failed to send metrics update: {e}")


# =============================================================================
# PERIODIC CLEANUP TASKS
# =============================================================================

@shared_task(
    name='paper_trading.tasks.cleanup_old_sessions',
    queue='paper_trading.maintenance'
)
def cleanup_old_sessions(max_age_days: int = 30) -> Dict[str, int]:
    """
    Clean up old paper trading sessions and related data.
    
    Args:
        max_age_days: Maximum age of sessions to keep
        
    Returns:
        Dictionary with cleanup statistics
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=max_age_days)
        
        # Find old sessions
        old_sessions = PaperTradingSession.objects.filter(
            created_at__lt=cutoff_date,
            status__in=['COMPLETED', 'STOPPED', 'ERROR']
        )
        
        session_count = old_sessions.count()
        
        # Delete related data
        for session in old_sessions:
            # Delete AI thoughts
            PaperAIThoughtLog.objects.filter(
                session=session
            ).delete()
            
            # Delete performance metrics
            PaperPerformanceMetrics.objects.filter(
                session=session
            ).delete()
        
        # Delete sessions
        old_sessions.delete()
        
        logger.info(f"[CLEANUP] Deleted {session_count} old sessions")
        
        return {
            'sessions_deleted': session_count,
            'cutoff_date': cutoff_date.isoformat()
        }
        
    except Exception as e:
        logger.error(f"[CLEANUP] Error: {e}")
        return {
            'error': str(e)
        }
    



"""
Trading Celery Tasks - Stub Implementations

Provides Celery task entry points for trade execution (buy/sell orders)
so that imports in trading/views.py work correctly.

These will later be upgraded to integrate with the Transaction Manager
and DEX Router Service (Phase 6B), but for now they return mock results
so your Django project runs cleanly.
"""

import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="trading.tasks.execute_buy_order")
def execute_buy_order(
    pair_address: str,
    token_address: str,
    amount_eth: str,
    slippage_tolerance: float,
    gas_price_gwei: float,
    trade_id: str,
    user_id: int,
    strategy_id: str = None,
    chain_id: int = 8453,
):
    """
    Stub Celery task for executing a BUY order.
    Logs parameters and returns a mock successful result.
    """
    logger.info(
        f"[TRADING] (Stub) BUY order | Trade ID={trade_id} | "
        f"Token={token_address[:10]}... | Amount={amount_eth} ETH | Chain={chain_id}"
    )

    return {
        "success": True,
        "trade_id": trade_id,
        "pair_address": pair_address,
        "token_address": token_address,
        "executed_price_usd": 2000.0,  # Mock ETH price
        "chain_id": chain_id,
        "message": "Stub execute_buy_order executed successfully"
    }


@shared_task(name="trading.tasks.execute_sell_order")
def execute_sell_order(
    pair_address: str,
    token_address: str,
    token_amount: str,
    slippage_tolerance: float,
    gas_price_gwei: float,
    trade_id: str = None,
    user_id: int = None,
    is_position_close: bool = False,
    position_id: str = None,
    chain_id: int = 8453,
):
    """
    Stub Celery task for executing a SELL order.
    Logs parameters and returns a mock successful result.
    """
    logger.info(
        f"[TRADING] (Stub) SELL order | Trade ID={trade_id} | "
        f"Token={token_address[:10]}... | Amount={token_amount} | Chain={chain_id}"
    )

    return {
        "success": True,
        "trade_id": trade_id,
        "pair_address": pair_address,
        "token_address": token_address,
        "sold_amount": token_amount,
        "is_position_close": is_position_close,
        "position_id": position_id,
        "chain_id": chain_id,
        "message": "Stub execute_sell_order executed successfully"
    }


