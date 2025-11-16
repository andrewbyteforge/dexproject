"""
Paper Trading Bot Control API - WITH CONFIGURATION WIRING

This module handles bot lifecycle management (start/stop/status) and
CRITICALLY wires the saved configuration from the dashboard to the bot.

The configuration flow:
1. User saves config via configuration page → PaperStrategyConfiguration
2. User clicks "Start Bot" → api_start_bot()
3. api_start_bot() loads active config and extracts parameters
4. Parameters passed to Celery task → run_paper_trading_bot.delay()
5. Task passes config to EnhancedPaperTradingBot initialization
6. Bot uses config values to control trading behavior

File: paper_trading/api/bot_control_api.py
"""

import json
import logging
from typing import Dict, Any, Optional, TYPE_CHECKING
from decimal import Decimal

from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.core.cache import cache

# Import models
from ..models import (
    PaperTradingAccount,
    PaperTradingSession,
    PaperStrategyConfiguration,
)

# Import constants for field names
from ..constants import (
    BotControlFields,
    SessionMetadataFields,
    SessionStatus,
    StrategyConfigFields,
    get_intel_level_from_trading_mode,
)

# Import Celery tasks
# Celery tasks - imported lazily to avoid blocking during Django startup
if TYPE_CHECKING:
    from celery import Task
    run_paper_trading_bot: Task  # type: ignore
    stop_paper_trading_bot: Task  # type: ignore
# Note: Actual imports moved inside functions to prevent module-level blocking

# Import utilities
from ..utils import get_default_user, get_single_trading_account

logger = logging.getLogger(__name__)


# =============================================================================
# BOT START API - WITH CONFIGURATION WIRING
# =============================================================================

@require_http_methods(["POST"])
@csrf_exempt
def api_start_bot(request: HttpRequest) -> JsonResponse:
    """
    Start paper trading bot with configuration from dashboard.
    
    This is the KEY FUNCTION that wires the configuration to the bot!
    
    Flow:
    1. Load active PaperStrategyConfiguration
    2. Extract all configuration parameters
    3. Create PaperTradingSession with config snapshot
    4. Pass parameters to Celery task
    5. Task passes parameters to EnhancedPaperTradingBot
    
    Request Body (optional):
        {
            "runtime_minutes": 60,  # Optional runtime limit
            "session_name": "My Trading Session"  # Optional custom name
        }
    
    Response:
        {
            "success": true,
            "session_id": "uuid",
            "task_id": "celery-task-id",
            "message": "Paper trading bot started",
            "status": "starting",
            "account_balance": 10000.0,
            "config_used": {
                "name": "My Strategy",
                "trading_mode": "MODERATE",
                ...
            }
        }
    
    Returns:
        JsonResponse: Bot start confirmation with session details
    """
    try:
        # Lazy import to prevent blocking during Django startup
        from ..tasks import run_paper_trading_bot  # noqa: F811
        # Get default user and account
        user = get_default_user()
        account = get_single_trading_account()
        
        logger.info(f"Starting bot for account {account.account_id}")
        
        # Check if bot is already running
        existing_session = PaperTradingSession.objects.filter(
            account=account,
            status__in=[SessionStatus.RUNNING, SessionStatus.STARTING]
        ).first()
        
        if existing_session:
            return JsonResponse({
                'success': False,
                'error': 'Bot is already running',
                'session_id': str(existing_session.session_id)
            }, status=400)
        
        # Parse optional request body
        runtime_minutes = None
        session_name = None
        
        if request.body:
            try:
                body_data = json.loads(request.body)
                runtime_minutes = body_data.get(BotControlFields.RUNTIME_MINUTES)
                session_name = body_data.get(BotControlFields.SESSION_NAME)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON in request body, using defaults")
        
        # =====================================================================
        # CONFIGURATION WIRING - THE KEY STEP!
        # =====================================================================
        
        # Load active strategy configuration
        strategy_config = PaperStrategyConfiguration.objects.filter(
            account=account,
            is_active=True
        ).first()
        
        if not strategy_config:
            # Create default configuration if none exists
            logger.warning("No active configuration found, creating default")
            strategy_config = PaperStrategyConfiguration.objects.create(
                account=account,
                name='Default Strategy',
                is_active=True,
                trading_mode='MODERATE',
                max_position_size_percent=Decimal('25.0'),
                stop_loss_percent=Decimal('5.0'),
                take_profit_percent=Decimal('10.0'),
                max_daily_trades=20,
                confidence_threshold=Decimal('60.0'),
            )
        
        # Extract configuration parameters
        config_params = _extract_config_parameters(strategy_config)
        
        logger.info(
            f"Using configuration '{strategy_config.name}' "
            f"(mode: {strategy_config.trading_mode})"
        )
        
        # =====================================================================
        # SESSION CREATION WITH CONFIG SNAPSHOT
        # =====================================================================
        
        # Create session metadata with configuration snapshot
        session_metadata = {
            SessionMetadataFields.CONFIG_SNAPSHOT: config_params,
            SessionMetadataFields.STARTING_BALANCE_USD: float(account.current_balance_usd),
            SessionMetadataFields.SESSION_NAME: session_name or f'Session {timezone.now().strftime("%Y%m%d_%H%M%S")}',
        }
        
        # Create new trading session
        session = PaperTradingSession.objects.create(
            account=account,
            strategy_config=strategy_config,
            status=SessionStatus.STARTING,
            metadata=session_metadata
        )
        
        logger.info(f"Created session {session.session_id}")
        
        # =====================================================================
        # START BOT VIA CELERY WITH CONFIGURATION
        # =====================================================================
        
        # Calculate intel level from trading mode
        intel_level = get_intel_level_from_trading_mode(strategy_config.trading_mode)
        
        # Start the bot via Celery task - NOW WITH CONFIGURATION!
        task_result = run_paper_trading_bot.delay(
            session_id=str(session.session_id),
            user_id=user.pk,
            runtime_minutes=runtime_minutes,
            config_params=config_params,  # ← CONFIGURATION WIRED IN!
            intel_level=intel_level,  # ← Calculated from trading mode
        )
        
        # Store task ID in session metadata
        session.metadata[SessionMetadataFields.CELERY_TASK_ID] = task_result.id
        session.metadata[SessionMetadataFields.STARTED_AT] = timezone.now().isoformat()
        session.save()
        
        # Cache bot status for monitoring
        cache_key = f"paper_bot:{session.session_id}:status"
        cache.set(cache_key, {
            BotControlFields.STATUS: SessionStatus.RUNNING,
            BotControlFields.TASK_ID: task_result.id,
            BotControlFields.STARTED_AT: timezone.now().isoformat()
        }, timeout=3600)
        
        logger.info(
            f"Started paper trading session {session.session_id} "
            f"with task {task_result.id} using config '{strategy_config.name}'"
        )
        
        return JsonResponse({
            'success': True,
            BotControlFields.SESSION_ID: str(session.session_id),
            BotControlFields.TASK_ID: task_result.id,
            BotControlFields.MESSAGE: 'Paper trading bot started',
            BotControlFields.STATUS: SessionStatus.STARTING,
            BotControlFields.ACCOUNT_BALANCE: float(account.current_balance_usd),
            'config_used': {
                'name': strategy_config.name,
                'trading_mode': strategy_config.trading_mode,
                'intel_level': intel_level,
                'max_position_size_percent': float(strategy_config.max_position_size_percent),
                'stop_loss_percent': float(strategy_config.stop_loss_percent),
                'take_profit_percent': float(strategy_config.take_profit_percent),
            }
        })
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def _extract_config_parameters(config: PaperStrategyConfiguration) -> Dict[str, Any]:
    """
    Extract configuration parameters from PaperStrategyConfiguration.
    
    This helper function converts the configuration model into a dictionary
    that can be passed to the bot and stored in session metadata.
    
    Args:
        config: Strategy configuration model instance
        
    Returns:
        Dictionary with all configuration parameters
    """
    return {
        # Basic settings
        StrategyConfigFields.NAME: config.name,
        StrategyConfigFields.TRADING_MODE: config.trading_mode,
        StrategyConfigFields.IS_ACTIVE: config.is_active,
        
        # Lane configuration
        StrategyConfigFields.USE_FAST_LANE: config.use_fast_lane,
        StrategyConfigFields.USE_SMART_LANE: config.use_smart_lane,
        StrategyConfigFields.FAST_LANE_THRESHOLD_USD: float(config.fast_lane_threshold_usd),
        
        # Position sizing
        StrategyConfigFields.MAX_POSITION_SIZE_PERCENT: float(config.max_position_size_percent),
        StrategyConfigFields.MAX_TRADE_SIZE_USD: float(config.max_trade_size_usd),  # ← FIX THIS LINE
        StrategyConfigFields.MAX_DAILY_TRADES: config.max_daily_trades,
        StrategyConfigFields.MAX_CONCURRENT_POSITIONS: config.max_concurrent_positions,
        
        # Risk management
        StrategyConfigFields.STOP_LOSS_PERCENT: float(config.stop_loss_percent),
        StrategyConfigFields.TAKE_PROFIT_PERCENT: float(config.take_profit_percent),
        StrategyConfigFields.MIN_LIQUIDITY_USD: float(config.min_liquidity_usd),
        StrategyConfigFields.MAX_SLIPPAGE_PERCENT: float(config.max_slippage_percent),
        
        # ⭐ CRITICAL: Confidence threshold - THIS IS WHAT WAS MISSING!
        StrategyConfigFields.CONFIDENCE_THRESHOLD: float(config.confidence_threshold),
        
        # Token filters
        StrategyConfigFields.ALLOWED_TOKENS: config.allowed_tokens or [],
        StrategyConfigFields.BLOCKED_TOKENS: config.blocked_tokens or [],
        
        # Custom parameters
        StrategyConfigFields.CUSTOM_PARAMETERS: config.custom_parameters or {},
        
        # Timestamps
        StrategyConfigFields.CREATED_AT: config.created_at.isoformat(),
        StrategyConfigFields.UPDATED_AT: config.updated_at.isoformat(),
    }

# =============================================================================
# BOT STOP API
# =============================================================================

@require_http_methods(["POST"])
@csrf_exempt
def api_stop_bot(request: HttpRequest) -> JsonResponse:
    """
    Stop paper trading bot.
    
    Ends active trading sessions and stops the bot process via Celery.
    
    Request Body (optional):
        {
            "reason": "User requested stop"
        }
    
    Response:
        {
            "success": true,
            "message": "Bot stopped successfully",
            "sessions_stopped": 1
        }
    
    Returns:
        JsonResponse: Stop confirmation
    """
    try:
        # Lazy import to prevent blocking during Django startup
        from ..tasks import stop_paper_trading_bot  # noqa: F811
        # Get default user and account
        user = get_default_user()
        account = get_single_trading_account()
        
        # Parse optional request body
        reason = "User requested stop"
        if request.body:
            try:
                body_data = json.loads(request.body)
                reason = body_data.get(BotControlFields.REASON, reason)
            except json.JSONDecodeError:
                pass
        
        # Find active sessions
        active_sessions = PaperTradingSession.objects.filter(
            account=account,
            status__in=[SessionStatus.RUNNING, SessionStatus.STARTING]
        )
        
        if not active_sessions.exists():
            return JsonResponse({
                'success': False,
                'error': 'No active bot sessions found'
            }, status=404)
        
        # Stop each session
        sessions_stopped = 0
        for session in active_sessions:
            try:
                # Update session status
                session.status = SessionStatus.STOPPED
                session.stopped_at = timezone.now()
                session.metadata = session.metadata or {}
                session.metadata['stop_reason'] = reason
                session.save()
                
                # Clear cache
                cache_key = f"paper_bot:{session.session_id}:status"
                cache.delete(cache_key)
                
                # Attempt to stop Celery task if task_id exists
                task_id = session.metadata.get(SessionMetadataFields.CELERY_TASK_ID)
                if task_id:
                    try:
                        # Send stop signal to Celery task
                        stop_paper_trading_bot.delay(
                            session_id=str(session.session_id),
                            user_id=user.pk,
                            reason=reason
                        )
                    except Exception as e:
                        logger.warning(f"Could not stop Celery task {task_id}: {e}")
                
                sessions_stopped += 1
                logger.info(f"Stopped session {session.session_id}: {reason}")
                
            except Exception as e:
                logger.error(f"Error stopping session {session.session_id}: {e}")
        
        return JsonResponse({
            'success': True,
            BotControlFields.MESSAGE: 'Bot stopped successfully',
            'sessions_stopped': sessions_stopped,
            BotControlFields.REASON: reason
        })
        
    except Exception as e:
        logger.error(f"Error stopping bot: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# BOT STATUS API
# =============================================================================

@require_http_methods(["GET"])
def api_bot_status(request: HttpRequest) -> JsonResponse:
    """
    Get paper trading bot status.
    
    Returns current bot session status and statistics.
    
    Response:
        {
            "success": true,
            "status": "RUNNING" | "STOPPED" | "STARTING" | "ERROR",
            "session_id": "uuid",
            "started_at": "2024-01-01T00:00:00Z",
            "runtime_seconds": 3600,
            "trades_count": 25,
            "current_balance": 10500.0,
            "config": {...}
        }
    
    Returns:
        JsonResponse: Current bot status and metrics
    """
    try:
        # Get default user and account
        user = get_default_user()
        account = get_single_trading_account()
        
        # Find active or most recent session
        session = PaperTradingSession.objects.filter(
            account=account
        ).order_by('-started_at').first()
        
        if not session:
            return JsonResponse({
                'success': True,
                BotControlFields.STATUS: SessionStatus.STOPPED,
                BotControlFields.MESSAGE: 'No bot sessions found'
            })
        
        # Check cache for real-time status
        cache_key = f"paper_bot:{session.session_id}:status"
        cached_status = cache.get(cache_key)
        
        if cached_status:
            status = cached_status.get(BotControlFields.STATUS, session.status)
        else:
            status = session.status
        
        # Calculate runtime
        runtime_seconds = None
        if session.started_at:
            if session.stopped_at:
                runtime_seconds = (session.stopped_at - session.started_at).total_seconds()
            else:
                runtime_seconds = (timezone.now() - session.started_at).total_seconds()
        
        # Get session statistics
        trades_count = session.total_trades if hasattr(session, 'total_trades') else 0
        
        # Build response
        response_data = {
            'success': True,
            BotControlFields.STATUS: status,
            BotControlFields.SESSION_ID: str(session.session_id),
            BotControlFields.STARTED_AT: session.started_at.isoformat() if session.started_at else None,
            BotControlFields.STOPPED_AT: session.stopped_at.isoformat() if session.stopped_at else None,
            'runtime_seconds': runtime_seconds,
            'trades_count': trades_count,
            BotControlFields.ACCOUNT_BALANCE: float(account.current_balance_usd),
        }
        
        # Add configuration info if available
        if session.strategy_config:
            response_data['config'] = {
                'name': session.strategy_config.name,
                'trading_mode': session.strategy_config.trading_mode,
            }
        
        # Add metadata snapshot if available
        if session.metadata and SessionMetadataFields.CONFIG_SNAPSHOT in session.metadata:
            response_data['config_snapshot'] = session.metadata[SessionMetadataFields.CONFIG_SNAPSHOT]
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error getting bot status: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)