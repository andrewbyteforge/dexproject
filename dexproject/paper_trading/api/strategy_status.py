"""
Paper Trading API - Strategy Status Endpoint

Provides real-time status of currently active trading strategies.
Returns list of RUNNING and PAUSED strategies with progress metrics.

File: dexproject/paper_trading/api/strategy_status.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List

from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods

from ..models import StrategyRun
from ..utils import get_single_trading_account
from ..utils.type_utils import to_decimal

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def api_active_strategies(request: HttpRequest) -> JsonResponse:
    """
    Get all currently active trading strategies.
    
    Returns strategies with status RUNNING or PAUSED, along with
    their progress, P&L, and configuration details.
    
    Query Parameters:
        None
        
    Returns:
        JsonResponse with active strategies list
        
    Response Format:
        {
            "success": true,
            "strategies": [
                {
                    "strategy_id": "uuid-here",
                    "strategy_type": "DCA",
                    "status": "RUNNING",
                    "token_symbol": "AAVE",
                    "token_address": "0x1234...",
                    "progress_percent": 45.5,
                    "total_orders": 10,
                    "completed_orders": 5,
                    "total_invested": 500.00,
                    "current_pnl": 25.50,
                    "current_roi": 5.1,
                    "started_at": "2025-11-15T10:30:00Z",
                    "configuration": {
                        "dca_interval_minutes": 30,
                        "dca_order_count": 10,
                        "dca_amount_per_order": 50.00
                    }
                },
                ...
            ],
            "count": 3,
            "total_invested": 1500.00,
            "total_pnl": 125.50
        }
        
    Example:
        GET /paper-trading/api/strategies/active/
    """
    try:
        logger.info("Fetching active strategies")
        
        # Get account
        account = get_single_trading_account()
        
        # Query active strategies (RUNNING or PAUSED)
        active_strategies = StrategyRun.objects.filter(
            account=account,
            status__in=['RUNNING', 'PAUSED']
        ).select_related('account').order_by('-created_at')
        
        logger.info(f"Found {active_strategies.count()} active strategies")
        
        # Build response data
        strategies_data: List[Dict[str, Any]] = []
        total_invested = Decimal('0')
        total_pnl = Decimal('0')
        
        for strategy in active_strategies:
            # Calculate progress percentage
            progress_percent = Decimal('0')
            if strategy.total_orders and strategy.total_orders > 0:
                progress_percent = (
                    Decimal(str(strategy.completed_orders or 0)) / 
                    Decimal(str(strategy.total_orders))
                ) * Decimal('100')
            
            # Calculate ROI percentage
            roi_percent = Decimal('0')
            if strategy.total_invested and strategy.total_invested > 0:
                roi_percent = (
                    to_decimal(strategy.current_pnl or 0) / 
                    to_decimal(strategy.total_invested)
                ) * Decimal('100')
            
            # Extract configuration and token info from config JSONField
            token_symbol = strategy.config.get('token_symbol', 'UNKNOWN')
            token_address = strategy.config.get('token_address', '')
            
            # Extract configuration based on strategy type
            configuration = {}
            if strategy.config:
                if strategy.strategy_type == 'DCA':
                    configuration = {
                        'dca_interval_minutes': strategy.config.get('dca_interval_minutes'),
                        'dca_order_count': strategy.config.get('dca_order_count'),
                        'dca_amount_per_order': strategy.config.get('dca_amount_per_order'),
                    }
                elif strategy.strategy_type == 'GRID':
                    configuration = {
                        'grid_levels': strategy.config.get('grid_levels'),
                        'grid_price_range_percent': strategy.config.get('grid_price_range_percent'),
                        'grid_amount_per_level': strategy.config.get('grid_amount_per_level'),
                    }
                elif strategy.strategy_type == 'SPOT':
                    configuration = {
                        'spot_amount': strategy.config.get('spot_amount'),
                    }
            
            # Build strategy data
            strategy_data = {
                'strategy_id': str(strategy.strategy_id),
                'strategy_type': strategy.strategy_type,
                'status': strategy.status,
                'token_symbol': token_symbol,
                'token_address': token_address,
                'progress_percent': float(progress_percent),
                'total_orders': strategy.total_orders or 0,
                'completed_orders': strategy.completed_orders or 0,
                'total_invested': float(to_decimal(strategy.total_invested or 0)),
                'current_pnl': float(to_decimal(strategy.current_pnl or 0)),
                'current_roi': float(roi_percent),
                'started_at': strategy.created_at.isoformat() if strategy.created_at else None,
                'configuration': configuration,
            }
            
            strategies_data.append(strategy_data)
            
            # Accumulate totals
            total_invested += to_decimal(strategy.total_invested or 0)
            total_pnl += to_decimal(strategy.current_pnl or 0)
        
        logger.info(
            f"Active strategies summary: {len(strategies_data)} strategies, "
            f"${total_invested} invested, ${total_pnl} P&L"
        )
        
        # Return response
        return JsonResponse({
            'success': True,
            'strategies': strategies_data,
            'count': len(strategies_data),
            'total_invested': float(total_invested),
            'total_pnl': float(total_pnl),
        })
        
    except Exception as e:
        logger.error(f"Error fetching active strategies: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'strategies': [],
            'count': 0,
        }, status=500)


@require_http_methods(["GET"])
def api_strategy_detail(request: HttpRequest, strategy_id: str) -> JsonResponse:
    """
    Get detailed information about a specific strategy.
    
    Returns comprehensive details about a single strategy including
    all orders, timeline, and performance metrics.
    
    Args:
        request: Django HTTP request
        strategy_id: UUID of the strategy to retrieve
        
    Returns:
        JsonResponse with strategy details
        
    Response Format:
        {
            "success": true,
            "strategy": {
                "strategy_id": "uuid-here",
                "strategy_type": "DCA",
                "status": "RUNNING",
                "token_symbol": "AAVE",
                "token_address": "0x1234...",
                "started_at": "2025-11-15T10:30:00Z",
                "updated_at": "2025-11-15T12:00:00Z",
                "total_orders": 10,
                "completed_orders": 5,
                "failed_orders": 0,
                "total_invested": 500.00,
                "current_pnl": 25.50,
                "current_roi": 5.1,
                "configuration": {...},
                "orders": [
                    {
                        "order_number": 1,
                        "status": "COMPLETED",
                        "amount": 50.00,
                        "price": 150.50,
                        "executed_at": "2025-11-15T10:30:00Z"
                    },
                    ...
                ]
            }
        }
        
    Example:
        GET /paper-trading/api/strategies/<strategy_id>/
    """
    try:
        logger.info(f"Fetching strategy detail for {strategy_id}")
        
        # Get account
        account = get_single_trading_account()
        
        # Get strategy
        try:
            strategy = StrategyRun.objects.select_related('account').get(
                strategy_id=strategy_id,
                account=account
            )
        except StrategyRun.DoesNotExist:
            logger.warning(f"Strategy {strategy_id} not found")
            return JsonResponse({
                'success': False,
                'error': 'Strategy not found'
            }, status=404)
        
        # Calculate progress and ROI
        progress_percent = Decimal('0')
        if strategy.total_orders and strategy.total_orders > 0:
            progress_percent = (
                Decimal(str(strategy.completed_orders or 0)) / 
                Decimal(str(strategy.total_orders))
            ) * Decimal('100')
        
        roi_percent = Decimal('0')
        if strategy.total_invested and strategy.total_invested > 0:
            roi_percent = (
                to_decimal(strategy.current_pnl or 0) / 
                to_decimal(strategy.total_invested)
            ) * Decimal('100')
        
        # Get token info from config
        token_symbol = strategy.config.get('token_symbol', 'UNKNOWN')
        token_address = strategy.config.get('token_address', '')
        
        # Build detailed response
        strategy_data = {
            'strategy_id': str(strategy.strategy_id),
            'strategy_type': strategy.strategy_type,
            'status': strategy.status,
            'token_symbol': token_symbol,
            'token_address': token_address,
            'started_at': strategy.started_at.isoformat() if strategy.started_at else None,
            'created_at': strategy.created_at.isoformat() if strategy.created_at else None,
            'paused_at': strategy.paused_at.isoformat() if strategy.paused_at else None,
            'completed_at': strategy.completed_at.isoformat() if strategy.completed_at else None,
            'total_orders': strategy.total_orders or 0,
            'completed_orders': strategy.completed_orders or 0,
            'failed_orders': strategy.failed_orders or 0,
            'total_invested': float(to_decimal(strategy.total_invested or 0)),
            'current_pnl': float(to_decimal(strategy.current_pnl or 0)),
            'current_roi': float(roi_percent),
            'progress_percent': float(progress_percent),
            'config': strategy.config or {},
            'notes': strategy.notes or '',
        }
        
        logger.info(f"Strategy detail retrieved: {strategy.strategy_type} for {token_symbol}")
        
        return JsonResponse({
            'success': True,
            'strategy': strategy_data
        })
        
    except Exception as e:
        logger.error(f"Error fetching strategy detail {strategy_id}: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# Log module initialization
logger.info("Strategy status API endpoints loaded")