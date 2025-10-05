"""
Paper Trading Celery Tasks

This module provides Celery tasks for running and controlling the paper trading bot.
Integrates with the existing bot infrastructure to enable API-driven bot control.

File: dexproject/paper_trading/tasks.py
"""

import logging
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime, timedelta

from celery import shared_task
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction

from paper_trading.models import (
    PaperTradingAccount,
    PaperTradingSession,
    PaperStrategyConfiguration,
    PaperAIThoughtLog,
    PaperPerformanceMetrics
)
from paper_trading.bot.simple_trader import EnhancedPaperTradingBot

logger = logging.getLogger(__name__)


# =============================================================================
# BOT CONTROL TASKS
# =============================================================================


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue='paper_trading'
)
def run_paper_trading_bot(
    self,
    session_id: str,
    user_id: int,
    runtime_minutes: Optional[int] = None
) -> Dict[str, Any]:
    """
    Run the paper trading bot for a specific session.
    
    This task manages the bot lifecycle for a trading session, including
    initialization, execution, and cleanup. It can run indefinitely or
    for a specified duration.
    
    Args:
        session_id: UUID of the trading session
        user_id: ID of the user running the bot
        runtime_minutes: Optional runtime limit in minutes (None for unlimited)
    
    Returns:
        Dict containing execution results and statistics
    
    Raises:
        ValueError: If session not found or invalid
        RuntimeError: If bot initialization or execution fails
    """
    task_id = self.request.id
    logger.info(f"Starting paper trading bot task {task_id} for session {session_id}")
    
    try:
        # Retrieve session with error handling
        try:
            session = PaperTradingSession.objects.select_related(
                'account', 'strategy_config'
            ).get(session_id=session_id)
        except PaperTradingSession.DoesNotExist:
            error_msg = f"Trading session {session_id} not found"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Validate session state
        if session.status not in ['STARTING', 'RUNNING', 'PAUSED']:
            logger.warning(f"Session {session_id} in invalid state: {session.status}")
            return {
                'success': False,
                'error': f'Session in invalid state: {session.status}',
                'session_id': str(session_id)
            }
        
        # Validate user owns the session
        if session.account.user_id != user_id:
            logger.error(f"User {user_id} does not own session {session_id}")
            return {
                'success': False,
                'error': 'Unauthorized: User does not own this session',
                'session_id': str(session_id)
            }
        
        # Update session status
        with transaction.atomic():
            session.status = 'RUNNING'
            session.metadata = session.metadata or {}
            session.metadata['celery_task_id'] = task_id
            session.metadata['started_at'] = timezone.now().isoformat()
            session.save()
        
        # Cache bot status for monitoring
        cache_key = f"paper_bot:{session_id}:status"
        cache.set(cache_key, {
            'status': 'RUNNING',
            'task_id': task_id,
            'started': timezone.now().isoformat()
        }, timeout=3600)  # 1 hour timeout
        
        # Initialize the bot with session configuration
        logger.info(f"Initializing bot for account {session.account.account_id}")
        
        try:
            bot = EnhancedPaperTradingBot(account_id=session.account.pk)
            
            # Apply strategy configuration if available
            if session.strategy_config:
                bot.config = {
                    'intelligence_level': session.strategy_config.intel_level,
                    'strategy': session.strategy_config.strategy_type,
                    'risk_tolerance': float(session.strategy_config.risk_tolerance),
                    'max_position_size': float(session.strategy_config.max_position_size_percent),
                    'stop_loss_percent': float(session.strategy_config.stop_loss_percent),
                    'take_profit_percent': float(session.strategy_config.take_profit_percent),
                    'enable_trailing_stop': session.strategy_config.enable_trailing_stop,
                    'min_trade_interval': session.strategy_config.min_trade_interval_minutes
                }
                logger.info(f"Applied strategy configuration: {session.strategy_config.name}")
            
            # Initialize bot systems
            if not bot.initialize():
                raise RuntimeError("Bot initialization failed")
            
            logger.info(f"Bot initialized successfully for session {session_id}")
            
        except Exception as e:
            logger.error(f"Bot initialization failed: {e}", exc_info=True)
            session.status = 'ERROR'
            session.error_message = str(e)
            session.ended_at = timezone.now()
            session.save()
            raise RuntimeError(f"Bot initialization failed: {e}")
        
        # Calculate runtime
        start_time = timezone.now()
        end_time = None
        if runtime_minutes:
            end_time = start_time + timedelta(minutes=runtime_minutes)
            logger.info(f"Bot will run for {runtime_minutes} minutes until {end_time}")
        
        # Main execution loop
        tick_count = 0
        trades_executed = 0
        errors = []
        
        try:
            while True:
                # Check if we should stop
                if end_time and timezone.now() >= end_time:
                    logger.info(f"Runtime limit reached, stopping bot")
                    break
                
                # Check for stop signal in cache
                stop_signal = cache.get(f"paper_bot:{session_id}:stop")
                if stop_signal:
                    logger.info(f"Stop signal received, stopping bot")
                    break
                
                # Check session status (might be updated externally)
                session.refresh_from_db()
                if session.status in ['STOPPING', 'STOPPED', 'ERROR']:
                    logger.info(f"Session status changed to {session.status}, stopping bot")
                    break
                
                # Execute bot tick
                try:
                    tick_result = bot.tick()
                    tick_count += 1
                    
                    # Track trades
                    if tick_result and tick_result.get('trade_executed'):
                        trades_executed += 1
                    
                    # Update cache with latest status
                    cache.set(cache_key, {
                        'status': 'RUNNING',
                        'task_id': task_id,
                        'started': start_time.isoformat(),
                        'tick_count': tick_count,
                        'trades_executed': trades_executed,
                        'last_tick': timezone.now().isoformat()
                    }, timeout=3600)
                    
                    # Log progress every 10 ticks
                    if tick_count % 10 == 0:
                        logger.debug(f"Bot tick {tick_count} completed, {trades_executed} trades executed")
                    
                except Exception as e:
                    error_msg = f"Error in bot tick {tick_count}: {e}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)
                    
                    # Stop on critical errors
                    if len(errors) > 5:
                        raise RuntimeError(f"Too many errors ({len(errors)}), stopping bot")
        
        except KeyboardInterrupt:
            logger.info("Bot interrupted by keyboard")
        except Exception as e:
            logger.error(f"Bot execution error: {e}", exc_info=True)
            raise
        
        finally:
            # Finalize session
            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()
            
            # Update session with final state
            with transaction.atomic():
                session.refresh_from_db()
                session.status = 'COMPLETED'
                session.ended_at = end_time
                session.ending_balance_usd = session.account.current_balance_usd
                session.session_pnl_usd = (
                    session.account.current_balance_usd - session.starting_balance_usd
                )
                session.total_trades_executed = trades_executed
                session.save()
            
            # Clear cache
            cache.delete(cache_key)
            
            logger.info(
                f"Bot session {session_id} completed: "
                f"duration={duration:.1f}s, ticks={tick_count}, trades={trades_executed}"
            )
            
            return {
                'success': True,
                'session_id': str(session_id),
                'duration_seconds': duration,
                'tick_count': tick_count,
                'trades_executed': trades_executed,
                'final_balance': float(session.account.current_balance_usd),
                'pnl': float(session.session_pnl_usd),
                'errors': errors
            }
    
    except Exception as e:
        logger.error(f"Fatal error in bot task: {e}", exc_info=True)
        
        # Update session status on error
        try:
            session.status = 'ERROR'
            session.error_message = str(e)
            session.ended_at = timezone.now()
            session.save()
        except:
            pass
        
        # Retry if appropriate
        if self.request.retries < self.max_retries:
            retry_delay = 60 * (2 ** self.request.retries)  # Exponential backoff
            logger.info(f"Retrying task in {retry_delay} seconds...")
            raise self.retry(countdown=retry_delay, exc=e)
        
        return {
            'success': False,
            'error': str(e),
            'session_id': str(session_id) if 'session_id' in locals() else None
        }


@shared_task(queue='paper_trading')
def stop_paper_trading_bot(
    session_id: str,
    user_id: Optional[int] = None,
    reason: str = "User requested stop"
) -> Dict[str, Any]:
    """
    Stop a running paper trading bot session.
    
    Args:
        session_id: UUID of the session to stop
        user_id: Optional user ID for authorization
        reason: Reason for stopping the bot
    
    Returns:
        Dict with stop operation results
    """
    logger.info(f"Stopping paper trading bot for session {session_id}: {reason}")
    
    try:
        # Get session
        try:
            session = PaperTradingSession.objects.get(session_id=session_id)
        except PaperTradingSession.DoesNotExist:
            return {
                'success': False,
                'error': f'Session {session_id} not found'
            }
        
        # Validate user if provided
        if user_id and session.account.user_id != user_id:
            return {
                'success': False,
                'error': 'Unauthorized: User does not own this session'
            }
        
        # Set stop signal in cache
        cache.set(f"paper_bot:{session_id}:stop", True, timeout=300)
        
        # Update session status
        previous_status = session.status
        with transaction.atomic():
            session.status = 'STOPPING'
            session.metadata = session.metadata or {}
            session.metadata['stop_reason'] = reason
            session.metadata['stopped_at'] = timezone.now().isoformat()
            session.save()
        
        # Wait briefly for bot to acknowledge stop
        import time
        time.sleep(2)
        
        # Finalize session
        session.refresh_from_db()
        if session.status == 'STOPPING':
            session.status = 'STOPPED'
            session.ended_at = timezone.now()
            session.ending_balance_usd = session.account.current_balance_usd
            session.session_pnl_usd = (
                session.account.current_balance_usd - session.starting_balance_usd
            )
            session.save()
        
        logger.info(f"Successfully stopped session {session_id}")
        
        return {
            'success': True,
            'session_id': str(session_id),
            'previous_status': previous_status,
            'final_status': session.status,
            'reason': reason
        }
    
    except Exception as e:
        logger.error(f"Error stopping session: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'session_id': str(session_id)
        }


@shared_task(queue='paper_trading')
def get_bot_status(session_id: str) -> Dict[str, Any]:
    """
    Get the current status of a paper trading bot session.
    
    Args:
        session_id: UUID of the session to check
    
    Returns:
        Dict with current bot status
    """
    try:
        # Check cache first
        cache_key = f"paper_bot:{session_id}:status"
        cached_status = cache.get(cache_key)
        
        # Get session from database
        try:
            session = PaperTradingSession.objects.get(session_id=session_id)
        except PaperTradingSession.DoesNotExist:
            return {
                'success': False,
                'error': f'Session {session_id} not found'
            }
        
        # Calculate metrics
        metrics = {}
        if session.status in ['RUNNING', 'COMPLETED', 'STOPPED']:
            metrics = {
                'duration': str(timezone.now() - session.started_at),
                'current_balance': float(session.account.current_balance_usd),
                'starting_balance': float(session.starting_balance_usd),
                'pnl': float(
                    session.account.current_balance_usd - session.starting_balance_usd
                ),
                'trades_executed': session.total_trades_executed or 0
            }
        
        return {
            'success': True,
            'session_id': str(session_id),
            'status': session.status,
            'cached_status': cached_status,
            'metrics': metrics,
            'started_at': session.started_at.isoformat() if session.started_at else None,
            'ended_at': session.ended_at.isoformat() if session.ended_at else None
        }
    
    except Exception as e:
        logger.error(f"Error getting bot status: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'session_id': str(session_id)
        }


@shared_task(queue='paper_trading')
def cleanup_old_sessions(days: int = 30) -> Dict[str, Any]:
    """
    Clean up old paper trading sessions and related data.
    
    Args:
        days: Number of days to keep sessions
    
    Returns:
        Dict with cleanup statistics
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Find old completed/stopped sessions
        old_sessions = PaperTradingSession.objects.filter(
            ended_at__lt=cutoff_date,
            status__in=['COMPLETED', 'STOPPED', 'ERROR']
        )
        
        count = old_sessions.count()
        
        # Delete old sessions (cascade will handle related records)
        old_sessions.delete()
        
        logger.info(f"Cleaned up {count} old paper trading sessions")
        
        return {
            'success': True,
            'sessions_deleted': count,
            'cutoff_date': cutoff_date.isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error cleaning up sessions: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }