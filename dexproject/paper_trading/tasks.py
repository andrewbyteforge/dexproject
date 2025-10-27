"""
Paper Trading Celery Tasks

This module provides Celery tasks for running and controlling the paper trading bot.
Integrates with the existing bot infrastructure to enable API-driven bot control.

UPDATED: Added periodic position price update task with real-time price fetching

File: dexproject/paper_trading/tasks.py
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal
from datetime import timedelta
from django.conf import settings  # Add at top
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
        if session.account.user.pk != user_id:
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
            # Initialize bot with account_name (required parameter)
            
            bot = EnhancedPaperTradingBot(
                account_name=session.account.name,
                intel_level=5,
                use_real_prices=True,
                chain_id=settings.PAPER_TRADING['DEFAULTS']['DEFAULT_CHAIN_ID']  # ← NEW
            )

            # Initialize bot systems
            if not bot.initialize():
                raise RuntimeError("Bot initialization failed")

            logger.info(f"Bot initialized successfully for session {session_id}")

        except Exception as e:
            logger.error(f"Bot initialization failed: {e}", exc_info=True)
            session.status = 'ERROR'
            session.error_message = str(e)
            session.stopped_at = timezone.now()
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
        initial_trades = session.total_trades or 0  # Store initial count before loop
        trades_executed = 0
        errors = []

        try:
            while True:
                # Check if we should stop
                if end_time and timezone.now() >= end_time:
                    logger.info("Runtime limit reached, stopping bot")
                    break

                # Check for stop signal in cache
                stop_signal = cache.get(f"paper_bot:{session_id}:stop")
                if stop_signal:
                    logger.info("Stop signal received, stopping bot")
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
                        logger.debug(f"Bot tick {tick_count} completed, {trades_executed} trades executed")

                except Exception as e:
                    error_msg = f"Error in bot tick {tick_count}: {e}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)

                    # Stop on critical errors
                    if len(errors) > 5:
                        raise RuntimeError(f"Too many errors ({len(errors)}), stopping bot")

                # Sleep between ticks
                import time
                time.sleep(bot.tick_interval)

        except KeyboardInterrupt:
            logger.info("Bot interrupted by keyboard")
        except Exception as e:
            logger.error(f"Bot execution error: {e}", exc_info=True)
            raise

        finally:
            # Finalize session
            end_time_actual = timezone.now()
            duration = (end_time_actual - start_time).total_seconds()

            # Get starting balance from metadata
            starting_balance = Decimal(str(
                session.metadata.get('starting_balance_usd', session.account.initial_balance_usd)
            ))

            with transaction.atomic():
                session.status = 'COMPLETED'
                session.stopped_at = end_time_actual

                # Store ending balance and P&L in metadata
                session.metadata['ending_balance_usd'] = float(session.account.current_balance_usd)
                session.metadata['session_pnl_usd'] = float(
                    session.account.current_balance_usd - starting_balance
                )
                session.save()

            # Clear cache
            cache.delete(cache_key)

            # Get session P&L from metadata
            session_pnl = Decimal(str(session.metadata.get('session_pnl_usd', 0)))

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
                'pnl': float(session_pnl),
                'errors': errors
            }

    except Exception as e:
        logger.error(f"Fatal error in bot task: {e}", exc_info=True)

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

    Features:
    - Bulk price fetching (efficient API usage)
    - Individual position error handling
    - Comprehensive logging and metrics
    - Transaction-safe updates
    - Automatic retry on failures

    Args:
        chain_id: Blockchain chain ID (default: 84532 for Base Sepolia)
        batch_size: Maximum number of positions to process per batch

    Returns:
        Dict containing update statistics and results:
        {
            'success': bool,
            'positions_found': int,
            'positions_updated': int,
            'positions_failed': int,
            'tokens_processed': int,
            'api_calls_made': int,
            'duration_seconds': float,
            'errors': List[str]
        }

    Example:
        # Call directly
        result = update_position_prices_task.apply()

        # Schedule via Celery Beat (in settings.py)
        CELERY_BEAT_SCHEDULE = {
            'update-position-prices': {
                'task': 'paper_trading.tasks.update_position_prices_task',
                'schedule': 300.0,  # Every 5 minutes
            },
        }
    """
    task_id = self.request.id
    start_time = timezone.now()

    logger.info(
        f"[POSITION UPDATER] Starting position price update task {task_id} "
        f"(chain_id={chain_id}, batch_size={batch_size})"
    )

    # Initialize metrics
    metrics = {
        'positions_found': 0,
        'positions_updated': 0,
        'positions_failed': 0,
        'positions_skipped': 0,
        'tokens_processed': 0,
        'api_calls_made': 0,
        'errors': [],
        'updated_positions': []
    }

    try:
        # =====================================================================
        # STEP 1: FETCH ALL OPEN POSITIONS
        # =====================================================================
        logger.info("[POSITION UPDATER] Fetching open positions...")

        try:
            open_positions = PaperPosition.objects.filter(
                is_open=True
            ).select_related('account').order_by('-current_value_usd')

            positions_count = open_positions.count()
            metrics['positions_found'] = positions_count

            if positions_count == 0:
                logger.info("[POSITION UPDATER] No open positions found, nothing to update")
                return {
                    'success': True,
                    'message': 'No open positions to update',
                    **metrics,
                    'duration_seconds': 0
                }

            logger.info(
                f"[POSITION UPDATER] Found {positions_count} open positions to update"
            )

        except Exception as e:
            error_msg = f"Failed to fetch open positions: {e}"
            logger.error(f"[POSITION UPDATER] {error_msg}", exc_info=True)
            metrics['errors'].append(error_msg)
            raise

        # =====================================================================
        # STEP 2: INITIALIZE PRICE FEED SERVICE
        # =====================================================================
        logger.info(f"[POSITION UPDATER] Initializing PriceFeedService (chain_id={chain_id})...")

        try:
            price_service = PriceFeedService(chain_id=chain_id)
            logger.info("[POSITION UPDATER] ✅ PriceFeedService initialized successfully")
        except Exception as e:
            error_msg = f"Failed to initialize PriceFeedService: {e}"
            logger.error(f"[POSITION UPDATER] {error_msg}", exc_info=True)
            metrics['errors'].append(error_msg)
            raise

        # =====================================================================
        # STEP 3: COLLECT UNIQUE TOKENS FOR BULK PRICE FETCH
        # =====================================================================
        logger.info("[POSITION UPDATER] Collecting unique tokens for bulk price fetch...")

        # Build list of (token_symbol, token_address) tuples
        tokens_to_fetch: List[Tuple[str, str]] = []
        token_symbols_seen = set()

        for position in open_positions:
            if position.token_symbol not in token_symbols_seen:
                tokens_to_fetch.append((
                    position.token_symbol,
                    position.token_address
                ))
                token_symbols_seen.add(position.token_symbol)

        unique_tokens = len(tokens_to_fetch)
        metrics['tokens_processed'] = unique_tokens

        logger.info(
            f"[POSITION UPDATER] Found {unique_tokens} unique tokens to fetch: "
            f"{', '.join([t[0] for t in tokens_to_fetch])}"
        )

        # =====================================================================
        # STEP 4: FETCH PRICES IN BULK
        # =====================================================================
        logger.info("[POSITION UPDATER] Fetching bulk token prices from APIs...")

        token_prices = {}
        try:
            # Create event loop for async operation
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                # Fetch all prices in one or two API calls
                token_prices = loop.run_until_complete(
                    price_service.get_bulk_token_prices(tokens_to_fetch)
                )

                # Track API calls (bulk fetch is very efficient)
                metrics['api_calls_made'] = 2  # Typically Alchemy + CoinGecko fallback

                prices_fetched = len(token_prices)
                logger.info(
                    f"[POSITION UPDATER] ✅ Fetched {prices_fetched}/{unique_tokens} prices "
                    f"in {metrics['api_calls_made']} API calls"
                )

                # Log price details
                for symbol, price in token_prices.items():
                    logger.debug(
                        f"[POSITION UPDATER] Price fetched: {symbol} = ${price:.6f}"
                    )

            finally:
                loop.close()

        except Exception as e:
            error_msg = f"Bulk price fetch failed: {e}"
            logger.error(f"[POSITION UPDATER] {error_msg}", exc_info=True)
            metrics['errors'].append(error_msg)

            # Continue with whatever prices we got
            if not token_prices:
                logger.warning(
                    "[POSITION UPDATER] No prices available, cannot update positions"
                )
                return {
                    'success': False,
                    'error': 'Failed to fetch any token prices',
                    **metrics,
                    'duration_seconds': (timezone.now() - start_time).total_seconds()
                }

        # =====================================================================
        # STEP 5: UPDATE EACH POSITION WITH NEW PRICES
        # =====================================================================
        logger.info("[POSITION UPDATER] Updating positions with new prices...")

        for position in open_positions:
            try:
                # Get price for this token
                new_price = token_prices.get(position.token_symbol)

                if new_price is None:
                    logger.warning(
                        f"[POSITION UPDATER] ⚠️  No price available for "
                        f"{position.token_symbol} (position {position.position_id}), skipping"
                    )
                    metrics['positions_skipped'] += 1
                    metrics['errors'].append(
                        f"No price for {position.token_symbol} ({position.position_id})"
                    )
                    continue

                # Store old values for logging
                old_price = position.current_price_usd
                old_value = position.current_value_usd
                old_pnl = position.unrealized_pnl_usd

                # Calculate price change
                price_change = Decimal('0')
                price_change_percent = Decimal('0')
                if old_price and old_price > 0:
                    price_change = new_price - old_price
                    price_change_percent = (price_change / old_price) * 100

                # Update position using the model's update_price method
                # This automatically recalculates current_value_usd and unrealized_pnl_usd
                position.update_price(new_price)

                # Calculate P&L change
                pnl_change = position.unrealized_pnl_usd - old_pnl

                # Log update details
                logger.info(
                    f"[POSITION UPDATER] ✅ Updated {position.token_symbol} "
                    f"(position {position.position_id}): "
                    f"price ${old_price:.6f} → ${new_price:.6f} "
                    f"({price_change_percent:+.2f}%), "
                    f"value ${old_value:.2f} → ${position.current_value_usd:.2f}, "
                    f"P&L ${old_pnl:.2f} → ${position.unrealized_pnl_usd:.2f} "
                    f"({pnl_change:+.2f})"
                )

                metrics['positions_updated'] += 1
                metrics['updated_positions'].append({
                    'position_id': str(position.position_id),
                    'token_symbol': position.token_symbol,
                    'old_price': float(old_price) if old_price else 0,
                    'new_price': float(new_price),
                    'price_change_percent': float(price_change_percent),
                    'new_value_usd': float(position.current_value_usd),
                    'new_pnl_usd': float(position.unrealized_pnl_usd)
                })

            except Exception as e:
                error_msg = (
                    f"Failed to update position {position.position_id} "
                    f"({position.token_symbol}): {e}"
                )
                logger.error(f"[POSITION UPDATER] ❌ {error_msg}", exc_info=True)
                metrics['positions_failed'] += 1
                metrics['errors'].append(error_msg)

                # Continue to next position (don't let one failure stop all updates)
                continue

        # =====================================================================
        # STEP 6: FINALIZE AND REPORT
        # =====================================================================
        duration = (timezone.now() - start_time).total_seconds()

        success_rate = (
            (metrics['positions_updated'] / metrics['positions_found'] * 100)
            if metrics['positions_found'] > 0 else 0
        )

        logger.info(
            f"[POSITION UPDATER] ✅ Position price update completed: "
            f"{metrics['positions_updated']}/{metrics['positions_found']} updated "
            f"({success_rate:.1f}% success rate), "
            f"{metrics['positions_failed']} failed, "
            f"{metrics['positions_skipped']} skipped, "
            f"duration={duration:.2f}s, "
            f"API calls={metrics['api_calls_made']}"
        )

        # Log any errors
        if metrics['errors']:
            logger.warning(
                f"[POSITION UPDATER] Encountered {len(metrics['errors'])} errors during update"
            )

        return {
            'success': True,
            'message': f"Updated {metrics['positions_updated']}/{metrics['positions_found']} positions",
            **metrics,
            'duration_seconds': duration,
            'success_rate_percent': float(success_rate)
        }

    except Exception as e:
        duration = (timezone.now() - start_time).total_seconds()
        error_msg = f"Fatal error in position price update task: {e}"
        logger.error(f"[POSITION UPDATER] ❌ {error_msg}", exc_info=True)
        metrics['errors'].append(error_msg)

        # Retry if appropriate
        if self.request.retries < self.max_retries:
            retry_delay = 30 * (2 ** self.request.retries)  # Exponential backoff
            logger.info(
                f"[POSITION UPDATER] Retrying task in {retry_delay} seconds "
                f"(attempt {self.request.retries + 1}/{self.max_retries})..."
            )
            raise self.retry(countdown=retry_delay, exc=e)

        return {
            'success': False,
            'error': error_msg,
            **metrics,
            'duration_seconds': duration
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