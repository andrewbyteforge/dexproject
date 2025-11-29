"""
Backtest API Endpoints

REST API endpoints for backtesting operations:
- Run new backtests
- Check backtest status
- List historical backtests
- Compare strategies
- Delete backtests

Phase 7B - Day 13: Backtesting API

File: dexproject/paper_trading/backtesting/api/backtest_api.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.utils import timezone
import json

from paper_trading.backtesting.engine import BacktestEngine
from paper_trading.backtesting.models import BacktestRun, BacktestResult
from paper_trading.backtesting import YAHOO_TICKER_MAPPING


logger = logging.getLogger(__name__)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def run_backtest_api(request) -> JsonResponse:
    """
    Run a new backtest.
    
    POST /paper-trading/api/backtest/run/
    
    Request Body:
        {
            "strategy_type": "DCA",
            "token_symbol": "ETH",
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-31T23:59:59Z",
            "initial_balance_usd": "10000.00",
            "strategy_params": {
                "total_amount_usd": "1000.00",
                "num_intervals": 10
            },
            "interval": "1h",
            "fee_percent": "0.30"
        }
    
    Response:
        {
            "success": true,
            "backtest_id": "uuid",
            "status": "COMPLETED",
            "result": {...}
        }
    """
    try:
        # Parse request body
        data = json.loads(request.body)
        
        # Extract parameters
        strategy_type = data.get('strategy_type', '').upper()
        token_symbol = data.get('token_symbol', '').upper()
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        initial_balance_usd = Decimal(str(data.get('initial_balance_usd', '10000')))
        strategy_params = data.get('strategy_params', {})
        interval = data.get('interval', '1h')
        fee_percent = Decimal(str(data.get('fee_percent', '0.30')))
        
        # Validate required fields
        if not strategy_type:
            return JsonResponse({
                'success': False,
                'error': 'strategy_type is required'
            }, status=400)
        
        if not token_symbol:
            return JsonResponse({
                'success': False,
                'error': 'token_symbol is required'
            }, status=400)
        
        if not start_date_str or not end_date_str:
            return JsonResponse({
                'success': False,
                'error': 'start_date and end_date are required'
            }, status=400)
        
        # Parse dates
        try:
            start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
        except ValueError as e:
            return JsonResponse({
                'success': False,
                'error': f'Invalid date format: {e}'
            }, status=400)
        
        # Create BacktestRun record
        with transaction.atomic():
            backtest_run = BacktestRun.objects.create(
                strategy_type=strategy_type,
                token_symbol=token_symbol,
                start_date=start_date,
                end_date=end_date,
                interval=interval,
                initial_balance_usd=initial_balance_usd,
                strategy_params=strategy_params,
                fee_percent=fee_percent,
                status=BacktestRun.STATUS_RUNNING,
            )
            
            logger.info(
                f"[BACKTEST API] Created backtest run: {backtest_run.backtest_id}"
            )
        
        # Run backtest
        engine = BacktestEngine()
        
        result = engine.run_backtest(
            strategy_type=strategy_type,
            token_symbol=token_symbol,
            start_date=start_date,
            end_date=end_date,
            initial_balance_usd=initial_balance_usd,
            strategy_params=strategy_params,
            interval=interval,
            fee_percent=fee_percent
        )
        
        # Update BacktestRun with results
        with transaction.atomic():
            if result and result.get('success'):
                # Mark as completed
                backtest_run.status = BacktestRun.STATUS_COMPLETED
                backtest_run.completed_at = timezone.now()
                backtest_run.data_points = result.get('data_points', 0)
                backtest_run.save()
                
                # Create BacktestResult
                metrics = result.get('metrics', {})
                simulation = result.get('simulation_results', {})
                
                backtest_result = BacktestResult.objects.create(
                    backtest_run=backtest_run,
                    final_balance_usd=Decimal(metrics.get('final_balance_usd', '0')),
                    profit_loss_usd=Decimal(metrics.get('profit_loss_usd', '0')),
                    return_percent=Decimal(metrics.get('return_percent', '0')),
                    total_fees_usd=Decimal(metrics.get('total_fees_usd', '0')),
                    num_trades=metrics.get('num_trades', 0),
                    num_buys=metrics.get('num_buys', 0),
                    num_sells=metrics.get('num_sells', 0),
                    avg_entry_price=Decimal(simulation.get('avg_entry_price', '0')),
                    win_rate_percent=Decimal(metrics.get('win_rate_percent', '0')),
                    profit_factor=Decimal(metrics.get('profit_factor', '0')),
                    max_drawdown_percent=Decimal(metrics.get('max_drawdown_percent', '0')),
                    sharpe_ratio=Decimal(metrics.get('sharpe_ratio', '0')),
                    sortino_ratio=Decimal(metrics.get('sortino_ratio', '0')),
                    avg_holding_hours=Decimal(metrics.get('avg_holding_hours', '0')),
                    max_consecutive_wins=metrics.get('max_consecutive_wins', 0),
                    max_consecutive_losses=metrics.get('max_consecutive_losses', 0),
                    trades_data=simulation.get('trades', []),
                    metrics_data=metrics,
                )
                
                logger.info(
                    f"[BACKTEST API] ✅ Backtest completed: {backtest_run.backtest_id}, "
                    f"Return: {backtest_result.return_percent}%"
                )
                
                return JsonResponse({
                    'success': True,
                    'backtest_id': str(backtest_run.backtest_id),
                    'status': backtest_run.status,
                    'result': {
                        'return_percent': str(backtest_result.return_percent),
                        'profit_loss_usd': str(backtest_result.profit_loss_usd),
                        'win_rate_percent': str(backtest_result.win_rate_percent),
                        'sharpe_ratio': str(backtest_result.sharpe_ratio),
                        'num_trades': backtest_result.num_trades,
                        'max_drawdown_percent': str(backtest_result.max_drawdown_percent),
                    }
                })
            else:
                # Mark as failed
                error_msg = result.get('error', 'Unknown error') if result else 'Backtest engine returned None'
                backtest_run.status = BacktestRun.STATUS_FAILED
                backtest_run.error_message = error_msg
                backtest_run.completed_at = timezone.now()
                backtest_run.save()
                
                logger.error(
                    f"[BACKTEST API] ❌ Backtest failed: {backtest_run.backtest_id}, "
                    f"Error: {error_msg}"
                )
                
                return JsonResponse({
                    'success': False,
                    'backtest_id': str(backtest_run.backtest_id),
                    'status': backtest_run.status,
                    'error': error_msg
                }, status=500)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    
    except Exception as e:
        logger.error(
            f"[BACKTEST API] Unexpected error: {e}",
            exc_info=True
        )
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def get_backtest_status_api(request, backtest_id: str) -> JsonResponse:
    """
    Get status of a specific backtest.
    
    GET /paper-trading/api/backtest/status/<backtest_id>/
    
    Response:
        {
            "success": true,
            "backtest_id": "uuid",
            "status": "COMPLETED",
            "result": {...}
        }
    """
    try:
        # Fetch backtest run
        backtest_run = BacktestRun.objects.get(backtest_id=backtest_id)
        
        response_data = {
            'success': True,
            'backtest_id': str(backtest_run.backtest_id),
            'status': backtest_run.status,
            'strategy_type': backtest_run.strategy_type,
            'token_symbol': backtest_run.token_symbol,
            'start_date': backtest_run.start_date.isoformat(),
            'end_date': backtest_run.end_date.isoformat(),
            'created_at': backtest_run.created_at.isoformat(),
            'completed_at': backtest_run.completed_at.isoformat() if backtest_run.completed_at else None,
            'duration': backtest_run.duration_display(),
        }
        
        # Add result if completed
        if backtest_run.status == BacktestRun.STATUS_COMPLETED:
            try:
                result = backtest_run.result
                response_data['result'] = {
                    'return_percent': str(result.return_percent),
                    'profit_loss_usd': str(result.profit_loss_usd),
                    'final_balance_usd': str(result.final_balance_usd),
                    'win_rate_percent': str(result.win_rate_percent),
                    'sharpe_ratio': str(result.sharpe_ratio),
                    'sortino_ratio': str(result.sortino_ratio),
                    'num_trades': result.num_trades,
                    'max_drawdown_percent': str(result.max_drawdown_percent),
                    'profit_factor': str(result.profit_factor),
                    'performance_grade': result.performance_grade(),
                }
            except BacktestResult.DoesNotExist:
                response_data['result'] = None
        
        # Add error if failed
        if backtest_run.status == BacktestRun.STATUS_FAILED:
            response_data['error'] = backtest_run.error_message
        
        return JsonResponse(response_data)
        
    except BacktestRun.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': f'Backtest not found: {backtest_id}'
        }, status=404)
    
    except Exception as e:
        logger.error(
            f"[BACKTEST API] Error fetching backtest status: {e}",
            exc_info=True
        )
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def list_backtests_api(request) -> JsonResponse:
    """
    List all backtests with optional filtering.
    
    GET /paper-trading/api/backtest/list/
    
    Query Parameters:
        - strategy_type: Filter by strategy type
        - token_symbol: Filter by token
        - status: Filter by status
        - limit: Maximum results (default 50)
    
    Response:
        {
            "success": true,
            "count": 10,
            "backtests": [...]
        }
    """
    try:
        # Get query parameters
        strategy_type = request.GET.get('strategy_type', '').upper()
        token_symbol = request.GET.get('token_symbol', '').upper()
        status = request.GET.get('status', '').upper()
        limit = int(request.GET.get('limit', 50))
        
        # Build query
        queryset = BacktestRun.objects.all()
        
        if strategy_type:
            queryset = queryset.filter(strategy_type=strategy_type)
        
        if token_symbol:
            queryset = queryset.filter(token_symbol=token_symbol)
        
        if status:
            queryset = queryset.filter(status=status)
        
        # Apply limit
        queryset = queryset[:limit]
        
        # Fetch with related results
        queryset = queryset.select_related('result')
        
        # Build response
        backtests = []
        for run in queryset:
            backtest_data = {
                'backtest_id': str(run.backtest_id),
                'strategy_type': run.strategy_type,
                'token_symbol': run.token_symbol,
                'status': run.status,
                'start_date': run.start_date.isoformat(),
                'end_date': run.end_date.isoformat(),
                'created_at': run.created_at.isoformat(),
                'duration': run.duration_display(),
            }
            
            # Add result if available
            if run.status == BacktestRun.STATUS_COMPLETED:
                try:
                    result = run.result
                    backtest_data['result'] = {
                        'return_percent': str(result.return_percent),
                        'win_rate_percent': str(result.win_rate_percent),
                        'sharpe_ratio': str(result.sharpe_ratio),
                        'num_trades': result.num_trades,
                        'performance_grade': result.performance_grade(),
                    }
                except BacktestResult.DoesNotExist:
                    backtest_data['result'] = None
            
            backtests.append(backtest_data)
        
        return JsonResponse({
            'success': True,
            'count': len(backtests),
            'backtests': backtests
        })
        
    except Exception as e:
        logger.error(
            f"[BACKTEST API] Error listing backtests: {e}",
            exc_info=True
        )
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def compare_strategies_api(request) -> JsonResponse:
    """
    Compare multiple strategies on the same token and time period.
    
    POST /paper-trading/api/backtest/compare/
    
    Request Body:
        {
            "token_symbol": "ETH",
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-31T23:59:59Z",
            "initial_balance_usd": "10000.00",
            "strategies": [
                {
                    "type": "DCA",
                    "params": {"total_amount_usd": "1000", "num_intervals": 10}
                },
                {
                    "type": "GRID",
                    "params": {"total_amount_usd": "1000", "num_grids": 10}
                }
            ]
        }
    
    Response:
        {
            "success": true,
            "num_strategies": 2,
            "rankings": [...],
            "best_strategy": {...}
        }
    """
    try:
        # Parse request body
        data = json.loads(request.body)
        
        token_symbol = data.get('token_symbol', '').upper()
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        initial_balance_usd = Decimal(str(data.get('initial_balance_usd', '10000')))
        strategies = data.get('strategies', [])
        
        # Validate
        if not token_symbol or not start_date_str or not end_date_str or not strategies:
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields'
            }, status=400)
        
        # Parse dates
        start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
        
        # Run backtests for each strategy
        engine = BacktestEngine()
        results = []
        
        for strategy in strategies:
            strategy_type = strategy.get('type', '').upper()
            strategy_params = strategy.get('params', {})
            
            result = engine.run_backtest(
                strategy_type=strategy_type,
                token_symbol=token_symbol,
                start_date=start_date,
                end_date=end_date,
                initial_balance_usd=initial_balance_usd,
                strategy_params=strategy_params
            )
            
            if result and result.get('success'):
                results.append(result)
        
        # Compare results
        comparison = engine.compare_strategies(results)
        
        logger.info(
            f"[BACKTEST API] Strategy comparison complete: "
            f"{comparison['num_strategies']} strategies compared"
        )
        
        return JsonResponse({
            'success': True,
            'num_strategies': comparison['num_strategies'],
            'rankings': comparison['rankings'],
            'best_strategy': comparison['best_strategy'],
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    
    except Exception as e:
        logger.error(
            f"[BACKTEST API] Error comparing strategies: {e}",
            exc_info=True
        )
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_backtest_api(request, backtest_id: str) -> JsonResponse:
    """
    Delete a backtest run and its results.
    
    DELETE /paper-trading/api/backtest/delete/<backtest_id>/
    
    Response:
        {
            "success": true,
            "message": "Backtest deleted successfully"
        }
    """
    try:
        backtest_run = BacktestRun.objects.get(backtest_id=backtest_id)
        backtest_run.delete()
        
        logger.info(f"[BACKTEST API] Deleted backtest: {backtest_id}")
        
        return JsonResponse({
            'success': True,
            'message': 'Backtest deleted successfully'
        })
        
    except BacktestRun.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': f'Backtest not found: {backtest_id}'
        }, status=404)
    
    except Exception as e:
        logger.error(
            f"[BACKTEST API] Error deleting backtest: {e}",
            exc_info=True
        )
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)