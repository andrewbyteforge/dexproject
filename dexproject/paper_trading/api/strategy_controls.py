"""
Paper Trading API - Strategy Control Endpoints

Provides endpoints to control active trading strategies:
- Pause strategy execution
- Resume paused strategy
- Cancel/terminate strategy

File: dexproject/paper_trading/api/strategy_controls.py
"""

import logging
from typing import Dict, Any

from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import transaction

from ..models import StrategyRun
from ..utils import get_single_trading_account

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
@csrf_exempt
def api_pause_strategy(request: HttpRequest, strategy_id: str) -> JsonResponse:
    """
    Pause a currently running strategy.
    
    Changes strategy status from RUNNING to PAUSED. The strategy will
    stop executing new orders but maintains its current state and can
    be resumed later.
    
    Args:
        request: Django HTTP request
        strategy_id: UUID of the strategy to pause
        
    Returns:
        JsonResponse with success status
        
    Response Format:
        {
            "success": true,
            "message": "Strategy paused successfully",
            "strategy": {
                "strategy_id": "uuid-here",
                "status": "PAUSED",
                "paused_at": "2025-11-15T12:00:00Z"
            }
        }
        
    Example:
        POST /paper-trading/api/strategies/<strategy_id>/pause/
    """
    try:
        logger.info(f"Pause request for strategy {strategy_id}")
        
        # Get account
        account = get_single_trading_account()
        
        # Get strategy
        try:
            strategy = StrategyRun.objects.select_for_update().get(
                strategy_id=strategy_id,
                account=account
            )
        except StrategyRun.DoesNotExist:
            logger.warning(f"Strategy {strategy_id} not found")
            return JsonResponse({
                'success': False,
                'error': 'Strategy not found'
            }, status=404)
        
        # Validate current status
        if strategy.status != 'RUNNING':
            logger.warning(
                f"Cannot pause strategy {strategy_id} with status {strategy.status}"
            )
            return JsonResponse({
                'success': False,
                'error': f'Cannot pause strategy with status {strategy.status}. '
                        f'Only RUNNING strategies can be paused.'
            }, status=400)
        
        # Update strategy to PAUSED
        with transaction.atomic():
            strategy.status = 'PAUSED'
            strategy.paused_at = timezone.now()
            strategy.save()
        
        # Get token symbol from config for logging
        token_symbol = strategy.config.get('token_symbol', 'UNKNOWN')
        
        logger.info(
            f"Strategy {strategy_id} ({strategy.strategy_type} for {token_symbol}) "
            f"paused successfully"
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Strategy paused successfully',
            'strategy': {
                'strategy_id': str(strategy.strategy_id),
                'strategy_type': strategy.strategy_type,
                'token_symbol': token_symbol,
                'status': strategy.status,
                'paused_at': strategy.paused_at.isoformat() if strategy.paused_at else None,
            }
        })
        
    except Exception as e:
        logger.error(f"Error pausing strategy {strategy_id}: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def api_resume_strategy(request: HttpRequest, strategy_id: str) -> JsonResponse:
    """
    Resume a paused strategy.
    
    Changes strategy status from PAUSED to RUNNING. The strategy will
    continue executing orders from where it left off.
    
    Args:
        request: Django HTTP request
        strategy_id: UUID of the strategy to resume
        
    Returns:
        JsonResponse with success status
        
    Response Format:
        {
            "success": true,
            "message": "Strategy resumed successfully",
            "strategy": {
                "strategy_id": "uuid-here",
                "status": "RUNNING",
                "resumed_at": "2025-11-15T12:30:00Z"
            }
        }
        
    Example:
        POST /paper-trading/api/strategies/<strategy_id>/resume/
    """
    try:
        logger.info(f"Resume request for strategy {strategy_id}")
        
        # Get account
        account = get_single_trading_account()
        
        # Get strategy
        try:
            strategy = StrategyRun.objects.select_for_update().get(
                strategy_id=strategy_id,
                account=account
            )
        except StrategyRun.DoesNotExist:
            logger.warning(f"Strategy {strategy_id} not found")
            return JsonResponse({
                'success': False,
                'error': 'Strategy not found'
            }, status=404)
        
        # Validate current status
        if strategy.status != 'PAUSED':
            logger.warning(
                f"Cannot resume strategy {strategy_id} with status {strategy.status}"
            )
            return JsonResponse({
                'success': False,
                'error': f'Cannot resume strategy with status {strategy.status}. '
                        f'Only PAUSED strategies can be resumed.'
            }, status=400)
        
        # Update strategy to RUNNING
        with transaction.atomic():
            strategy.status = 'RUNNING'
            # Set started_at if this is the first time running
            if not strategy.started_at:
                strategy.started_at = timezone.now()
            # Clear paused_at when resuming
            strategy.paused_at = None
            strategy.save()
        
        # Get token symbol from config for logging
        token_symbol = strategy.config.get('token_symbol', 'UNKNOWN')
        
        logger.info(
            f"Strategy {strategy_id} ({strategy.strategy_type} for {token_symbol}) "
            f"resumed successfully"
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Strategy resumed successfully',
            'strategy': {
                'strategy_id': str(strategy.strategy_id),
                'strategy_type': strategy.strategy_type,
                'token_symbol': token_symbol,
                'status': strategy.status,
                'started_at': strategy.started_at.isoformat() if strategy.started_at else None,
            }
        })
        
    except Exception as e:
        logger.error(f"Error resuming strategy {strategy_id}: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def api_cancel_strategy(request: HttpRequest, strategy_id: str) -> JsonResponse:
    """
    Cancel/terminate a strategy.
    
    Changes strategy status to CANCELLED. The strategy will stop
    executing orders and cannot be resumed. Any open positions
    will remain open (they must be closed separately).
    
    This is a permanent action - cancelled strategies cannot be restarted.
    
    Args:
        request: Django HTTP request
        strategy_id: UUID of the strategy to cancel
        
    Returns:
        JsonResponse with success status
        
    Response Format:
        {
            "success": true,
            "message": "Strategy cancelled successfully",
            "strategy": {
                "strategy_id": "uuid-here",
                "status": "CANCELLED",
                "cancelled_at": "2025-11-15T13:00:00Z",
                "final_stats": {
                    "total_invested": 500.00,
                    "current_pnl": 25.50,
                    "completed_orders": 5,
                    "total_orders": 10
                }
            }
        }
        
    Example:
        POST /paper-trading/api/strategies/<strategy_id>/cancel/
    """
    try:
        logger.info(f"Cancel request for strategy {strategy_id}")
        
        # Get account
        account = get_single_trading_account()
        
        # Get strategy
        try:
            strategy = StrategyRun.objects.select_for_update().get(
                strategy_id=strategy_id,
                account=account
            )
        except StrategyRun.DoesNotExist:
            logger.warning(f"Strategy {strategy_id} not found")
            return JsonResponse({
                'success': False,
                'error': 'Strategy not found'
            }, status=404)
        
        # Validate current status - can cancel RUNNING or PAUSED strategies
        if strategy.status not in ['RUNNING', 'PAUSED']:
            logger.warning(
                f"Cannot cancel strategy {strategy_id} with status {strategy.status}"
            )
            return JsonResponse({
                'success': False,
                'error': f'Cannot cancel strategy with status {strategy.status}. '
                        f'Only RUNNING or PAUSED strategies can be cancelled.'
            }, status=400)
        
        # Capture final stats before cancellation
        final_stats = {
            'total_invested': float(strategy.total_invested or 0),
            'current_pnl': float(strategy.current_pnl or 0),
            'completed_orders': strategy.completed_orders or 0,
            'total_orders': strategy.total_orders or 0,
            'progress_percent': (
                (strategy.completed_orders / strategy.total_orders * 100)
                if strategy.total_orders and strategy.total_orders > 0
                else 0
            ),
        }
        
        # Update strategy to CANCELLED
        with transaction.atomic():
            strategy.status = 'CANCELLED'
            strategy.cancelled_at = timezone.now()
            strategy.save()
        
        # Get token symbol from config for logging
        token_symbol = strategy.config.get('token_symbol', 'UNKNOWN')
        
        logger.info(
            f"Strategy {strategy_id} ({strategy.strategy_type} for {token_symbol}) "
            f"cancelled successfully. Final P&L: ${final_stats['current_pnl']}"
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Strategy cancelled successfully',
            'strategy': {
                'strategy_id': str(strategy.strategy_id),
                'strategy_type': strategy.strategy_type,
                'token_symbol': token_symbol,
                'status': strategy.status,
                'cancelled_at': strategy.cancelled_at.isoformat() if strategy.cancelled_at else None,
                'final_stats': final_stats,
            }
        })
        
    except Exception as e:
        logger.error(f"Error cancelling strategy {strategy_id}: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# Log module initialization
logger.info("Strategy controls API endpoints loaded")