"""
Paper Trading Bot Control Tasks

This module provides Celery tasks for running and controlling the paper trading bot.
Migrated from paper_trading/tasks.py and organized into the new tasks/ directory structure.

Tasks:
- run_paper_trading_bot: Run bot for a trading session
- stop_paper_trading_bot: Stop an active bot session
- get_bot_status: Get current status of a bot session
- cleanup_old_sessions: Clean up old completed sessions
- update_position_prices_task: Update all position prices periodically

File: paper_trading/tasks/bot_control.py
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal
from datetime import timedelta
from django.conf import settings
from celery import shared_task
from django.utils import timezone
from django.core.cache import cache
from django.db import transaction

from paper_trading.models import (
    PaperTradingSession,
    PaperPosition
)
from paper_trading.bot import EnhancedPaperTradingBot
from paper_trading.services.price_feed_service import PriceFeedService

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
    runtime_minutes: Optional[int] = None,
    config_params: Optional[Dict[str, Any]] = None,  
    intel_level: int = 5 
) -> Dict[str, Any]:
    """
    Run the paper trading bot for a specific session.

    This task manages the bot lifecycle for a trading session, including
    initialization, execution, and cleanup. It can run indefinitely or
    for a specified duration.

    FIXED: Now accepts intel_level and config_params from api_start_bot() to properly
    use the configuration from the dashboard instead of hardcoded values.

    Args:
        session_id: UUID of the trading session
        user_id: User ID who owns the session
        runtime_minutes: Optional runtime limit in minutes (None = unlimited)
        config_params: Optional configuration parameters from dashboard
        intel_level: Intelligence level (1-10) for decision-making

    Returns:
        Dict with execution results including trades, P&L, duration
    """
    bot = None  # Initialize to avoid 'possibly unbound' warning
    task_id = self.request.id
    
    logger.info("=" * 70)
    logger.info(f"🤖 Starting Paper Trading Bot Task")
    logger.info(f"   Session ID: {session_id}")
    logger.info(f"   Task ID: {task_id}")
    logger.info(f"   Intel Level: {intel_level}")
    logger.info(f"   Runtime: {runtime_minutes or 'Unlimited'} minutes")
    logger.info("=" * 70)

    try:
        # Get session and validate
        try:
            session = PaperTradingSession.objects.select_related('account', 'account__user').get(
                session_id=session_id
            )
        except PaperTradingSession.DoesNotExist:
            logger.error(f"❌ Session {session_id} not found")
            return {
                'success': False,
                'error': f'Session {session_id} not found'
            }

        # Validate user ownership
        if session.account.user.id != user_id:
            logger.error(f"❌ User {user_id} does not own session {session_id}")
            return {
                'success': False,
                'error': 'Unauthorized: User does not own this session'
            }

        # Update session to RUNNING
        with transaction.atomic():
            session.status = 'RUNNING'
            session.started_at = timezone.now()
            session.metadata = session.metadata or {}
            session.metadata['celery_task_id'] = task_id
            session.metadata['intel_level'] = intel_level
            session.metadata['starting_balance_usd'] = float(session.account.current_balance_usd)
            if config_params:
                session.metadata['config_params'] = config_params
            session.save()

        # Initialize bot with configuration
        logger.info(f"🔧 Initializing bot for account: {session.account.name}")
        
        bot = EnhancedPaperTradingBot(
            account_name=session.account.name,
            intel_level=intel_level,
            use_real_prices=True,
            chain_id=settings.PAPER_TRADING['DEFAULTS']['DEFAULT_CHAIN_ID']
        )

        # Initialize bot (loads account, creates/loads session)
        if not bot.initialize():
            logger.error("❌ Bot initialization failed")
            with transaction.atomic():
                session.status = 'ERROR'
                session.error_message = "Bot initialization failed"
                session.stopped_at = timezone.now()
                session.save()
            return {
                'success': False,
                'error': 'Bot initialization failed'
            }

        logger.info("✅ Bot initialized successfully")

        # Calculate end time if runtime is specified
        start_time = timezone.now()
        end_time = None
        if runtime_minutes:
            end_time = start_time + timedelta(minutes=runtime_minutes)
            logger.info(f"⏰ Bot will run until: {end_time.isoformat()}")

        # Set up cache for status updates
        cache_key = f"paper_bot:{session_id}:status"
        cache.set(cache_key, {
            'status': 'RUNNING',
            'task_id': task_id,
            'started': start_time.isoformat(),
            'tick_count': 0,
            'trades_executed': 0
        }, timeout=3600)

        # Track metrics
        tick_count = 0
        initial_trades = session.total_trades or 0
        trades_executed = 0
        errors = 0

        # Main bot execution loop
        try:
            logger.info("🔄 Starting bot execution loop...")
            
            while True:
                # Check if we should stop
                if end_time and timezone.now() >= end_time:
                    logger.info("⏰ Runtime limit reached, stopping bot")
                    break

                # Check for stop signal in cache
                stop_signal = cache.get(f"paper_bot:{session_id}:stop")
                if stop_signal:
                    logger.info("🛑 Stop signal received, stopping bot")
                    break

                # Check session status (might be updated externally)
                session.refresh_from_db()
                if session.status in ['STOPPING', 'STOPPED', 'ERROR']:
                    logger.info(f"Session status changed to {session.status}, stopping bot")
                    break

                # Execute bot tick via market_analyzer
                try:
                    # Call market_analyzer.tick() to execute one trading cycle
                    bot.market_analyzer.tick(
                        price_manager=bot.price_manager,
                        position_manager=bot.position_manager,
                        trade_executor=bot.trade_executor
                    )
                    tick_count += 1

                    # Track new trades executed since start
                    session.refresh_from_db()
                    trades_executed = (session.total_trades or 0) - initial_trades

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
                        logger.info(
                            f"📊 Progress: {tick_count} ticks, "
                            f"{trades_executed} trades, "
                            f"Balance: ${session.account.current_balance_usd}"
                        )

                except Exception as tick_error:
                    errors += 1
                    logger.error(f"❌ Error in bot tick: {tick_error}", exc_info=True)
                    
                    # Stop if too many errors
                    if errors >= 10:
                        logger.error("💥 Too many errors, stopping bot")
                        break

                # Sleep for tick interval (bot's configured interval)
                import time
                time.sleep(bot.tick_interval if hasattr(bot, 'tick_interval') else 30)

        except KeyboardInterrupt:
            logger.info("⚠️  Bot interrupted by user")
        except Exception as loop_error:
            logger.error(f"💥 Fatal error in bot loop: {loop_error}", exc_info=True)
            errors += 1

        # Finalize session
        finally:
            # Ensure bot cleanup
            if bot:
                try:
                    bot.shutdown()
                except Exception as shutdown_error:
                    logger.error(f"Error during bot shutdown: {shutdown_error}")

            # Update session status
            duration = (timezone.now() - start_time).total_seconds()
            session.refresh_from_db()
            
            with transaction.atomic():
                if session.status == 'STOPPING':
                    session.status = 'STOPPED'
                elif session.status not in ['ERROR', 'STOPPED']:
                    session.status = 'COMPLETED'
                
                session.stopped_at = timezone.now()
                session.metadata = session.metadata or {}
                session.metadata['tick_count'] = tick_count
                session.metadata['trades_executed'] = trades_executed
                session.metadata['duration_seconds'] = duration
                session.metadata['errors'] = errors
                session.metadata['ending_balance_usd'] = float(session.account.current_balance_usd)
                session.save()

            # Clear cache
            cache.delete(cache_key)
            cache.delete(f"paper_bot:{session_id}:stop")

            # Log final summary
            session_pnl = float(session.metadata.get('session_pnl_usd', 0)) or float(
                session.account.current_balance_usd - 
                Decimal(str(session.metadata.get('starting_balance_usd', session.account.initial_balance_usd)))
            )

            logger.info("=" * 70)
            logger.info(f"✅ Bot session {session_id} completed")
            logger.info(f"   Duration: {duration:.1f}s")
            logger.info(f"   Ticks: {tick_count}")
            logger.info(f"   Trades: {trades_executed}")
            logger.info(f"   Intel Level: {intel_level}")
            logger.info(f"   Final Balance: ${session.account.current_balance_usd}")
            logger.info(f"   P&L: ${session_pnl}")
            logger.info("=" * 70)

            return {
                'success': True,
                'session_id': str(session_id),
                'duration_seconds': duration,
                'tick_count': tick_count,
                'trades_executed': trades_executed,
                'final_balance': float(session.account.current_balance_usd),
                'pnl': float(session_pnl),
                'intel_level': intel_level,
                'errors': errors
            }

    except Exception as e:
        logger.error(f"💥 Fatal error in bot task: {e}", exc_info=True)

        # Update session status on error
        try:
            session.status = 'ERROR'
            session.error_message = str(e)
            session.stopped_at = timezone.now()
            session.save()
        except Exception:
            pass

        # Retry if appropriate
        if self.request.retries < self.max_retries:
            retry_delay = 60 * (2 ** self.request.retries)  # Exponential backoff
            logger.info(f"🔄 Retrying task in {retry_delay} seconds...")
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

    This task sets a stop signal that the running bot will detect,
    causing it to gracefully shut down and finalize the session.

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
        if user_id and session.account.user.id != user_id:
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

        # Get starting balance from metadata
        starting_balance = Decimal(str(
            session.metadata.get('starting_balance_usd', session.account.initial_balance_usd)
        ))

        # Finalize session
        session.refresh_from_db()
        if session.status == 'STOPPING':
            session.status = 'STOPPED'
            session.stopped_at = timezone.now()

            # Store ending balance and P&L in metadata
            session.metadata['ending_balance_usd'] = float(session.account.current_balance_usd)
            session.metadata['session_pnl_usd'] = float(
                session.account.current_balance_usd - starting_balance
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

        # Get starting balance from metadata
        starting_balance = Decimal(str(
            session.metadata.get('starting_balance_usd', session.account.initial_balance_usd)
        ))

        # Calculate metrics
        metrics = {}
        if session.status in ['RUNNING', 'COMPLETED', 'STOPPED']:
            metrics = {
                'duration': str(timezone.now() - session.started_at),
                'current_balance': float(session.account.current_balance_usd),
                'starting_balance': float(starting_balance),
                'pnl': float(session.account.current_balance_usd - starting_balance),
                'trades_executed': session.total_trades or 0
            }

        return {
            'success': True,
            'session_id': str(session_id),
            'status': session.status,
            'cached_status': cached_status,
            'metrics': metrics,
            'started_at': session.started_at.isoformat() if session.started_at else None,
            'stopped_at': session.stopped_at.isoformat() if session.stopped_at else None
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

    This task removes sessions older than the specified number of days
    to keep the database clean and performant.

    Args:
        days: Number of days to keep sessions

    Returns:
        Dict with cleanup statistics
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=days)

        # Find old completed/stopped sessions
        old_sessions = PaperTradingSession.objects.filter(
            stopped_at__lt=cutoff_date,
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


# =============================================================================
# POSITION PRICE UPDATE TASKS
# =============================================================================


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue='paper_trading'
)
def update_position_prices_task(
    self,
    chain_id: int = 84532,
    batch_size: int = 20
) -> Dict[str, Any]:
    """
    Update all open positions with real-time token prices.

    This task periodically fetches current market prices for all tokens
    in open positions and updates the position values and unrealized P&L.

    Args:
        chain_id: Blockchain chain ID (default: 84532 = Base Sepolia)
        batch_size: Number of positions to process in each batch

    Returns:
        Dict with update statistics
    """
    logger.info(f"[POSITION_PRICE_UPDATE] Starting position price updates for chain {chain_id}")

    try:
        # Initialize price feed service
        price_service = PriceFeedService(chain_id=chain_id)

        # Get all open positions
        open_positions = PaperPosition.objects.filter(
            status='OPEN',
            account__chain_id=chain_id
        ).select_related('account')

        if not open_positions.exists():
            logger.info("[POSITION_PRICE_UPDATE] No open positions to update")
            return {
                'success': True,
                'positions_updated': 0,
                'message': 'No open positions found'
            }

        total_positions = open_positions.count()
        logger.info(f"[POSITION_PRICE_UPDATE] Found {total_positions} open positions to update")

        # Collect all unique token addresses
        token_addresses = list(set(pos.token_address for pos in open_positions))
        logger.info(f"[POSITION_PRICE_UPDATE] Fetching prices for {len(token_addresses)} unique tokens")

        # Fetch all prices in bulk (much more efficient than individual calls)
        token_prices = {}
        try:
            for token_address in token_addresses:
                price_data = price_service.get_token_price(token_address)
                if price_data and price_data.get('price_usd'):
                    token_prices[token_address.lower()] = Decimal(str(price_data['price_usd']))
                    logger.debug(
                        f"[POSITION_PRICE_UPDATE] Fetched price for {token_address[:10]}...: "
                        f"${price_data['price_usd']}"
                    )
        except Exception as price_error:
            logger.error(f"[POSITION_PRICE_UPDATE] Error fetching prices: {price_error}", exc_info=True)
            # Continue with whatever prices we got

        if not token_prices:
            logger.warning("[POSITION_PRICE_UPDATE] No prices fetched, skipping update")
            return {
                'success': False,
                'error': 'Failed to fetch any token prices',
                'positions_updated': 0
            }

        # Update positions with new prices
        positions_updated = 0
        total_unrealized_pnl = Decimal('0')

        for position in open_positions:
            token_addr = position.token_address.lower()
            
            if token_addr not in token_prices:
                logger.debug(
                    f"[POSITION_PRICE_UPDATE] No price for position {position.position_id}, skipping"
                )
                continue

            current_price = token_prices[token_addr]
            
            # Calculate new values
            current_value_usd = position.current_amount_token * current_price
            unrealized_pnl_usd = current_value_usd - position.total_cost_usd
            unrealized_pnl_percent = (
                (unrealized_pnl_usd / position.total_cost_usd * 100)
                if position.total_cost_usd > 0 else Decimal('0')
            )

            # Update position
            with transaction.atomic():
                position.current_price_usd = current_price
                position.current_value_usd = current_value_usd
                position.unrealized_pnl_usd = unrealized_pnl_usd
                position.unrealized_pnl_percent = unrealized_pnl_percent
                position.last_price_update = timezone.now()
                position.save()

            positions_updated += 1
            total_unrealized_pnl += unrealized_pnl_usd

            logger.debug(
                f"[POSITION_PRICE_UPDATE] Updated position {position.token_symbol}: "
                f"${current_price:.6f}, P&L: ${unrealized_pnl_usd:.2f} ({unrealized_pnl_percent:.2f}%)"
            )

        logger.info(
            f"[POSITION_PRICE_UPDATE] ✅ Updated {positions_updated}/{total_positions} positions. "
            f"Total unrealized P&L: ${total_unrealized_pnl:.2f}"
        )

        return {
            'success': True,
            'positions_updated': positions_updated,
            'total_positions': total_positions,
            'unique_tokens': len(token_addresses),
            'prices_fetched': len(token_prices),
            'total_unrealized_pnl': float(total_unrealized_pnl),
            'chain_id': chain_id
        }

    except Exception as e:
        logger.error(f"[POSITION_PRICE_UPDATE] Fatal error: {e}", exc_info=True)
        
        # Retry if appropriate
        if self.request.retries < self.max_retries:
            retry_delay = 30 * (2 ** self.request.retries)
            logger.info(f"[POSITION_PRICE_UPDATE] Retrying in {retry_delay}s...")
            raise self.retry(countdown=retry_delay, exc=e)

        return {
            'success': False,
            'error': str(e),
            'positions_updated': 0
        }
    @shared_task(queue='paper_trading')
def update_single_position_price(
    position_id: str,
    chain_id: int = 84532
) -> Dict[str, Any]:
    """
    Update a single position with real-time token price.

    Useful for on-demand position updates or testing.

    Args:
        position_id: UUID of the position to update
        chain_id: Blockchain chain ID (default: 84532 for Base Sepolia)

    Returns:
        Dict with update results

    Example:
        result = update_single_position_price.apply_async(
            args=['550e8400-e29b-41d4-a716-446655440000']
        )
    """
    logger.info(f"[POSITION UPDATER] Updating single position {position_id}")

    try:
        # Fetch position
        try:
            position = PaperPosition.objects.select_related('account').get(
                position_id=position_id,
                is_open=True
            )
        except PaperPosition.DoesNotExist:
            error_msg = f"Position {position_id} not found or not open"
            logger.error(f"[POSITION UPDATER] {error_msg}")
            return {
                'success': False,
                'error': error_msg
            }

        # Initialize price service
        price_service = PriceFeedService(chain_id=chain_id)

        # Fetch price
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            price = loop.run_until_complete(
                price_service.get_token_price(
                    position.token_address,
                    position.token_symbol
                )
            )
        finally:
            loop.close()

        if price is None:
            error_msg = f"Failed to fetch price for {position.token_symbol}"
            logger.error(f"[POSITION UPDATER] {error_msg}")
            return {
                'success': False,
                'error': error_msg
            }

        # Store old values
        old_price = position.current_price_usd
        old_pnl = position.unrealized_pnl_usd

        # Update position
        position.update_price(price)

        logger.info(
            f"[POSITION UPDATER] ✅ Updated position {position_id}: "
            f"{position.token_symbol} ${old_price:.6f} → ${price:.6f}, "
            f"P&L ${old_pnl:.2f} → ${position.unrealized_pnl_usd:.2f}"
        )

        return {
            'success': True,
            'position_id': str(position_id),
            'token_symbol': position.token_symbol,
            'old_price': float(old_price) if old_price else 0,
            'new_price': float(price),
            'new_pnl': float(position.unrealized_pnl_usd)
        }

    except Exception as e:
        error_msg = f"Error updating position {position_id}: {e}"
        logger.error(f"[POSITION UPDATER] {error_msg}", exc_info=True)
        return {
            'success': False,
            'error': error_msg,
            'position_id': str(position_id)
        }
    
    
