"""
Paper Trading Data API - Read-Only Endpoints

This module provides all read-only API endpoints for data retrieval including
AI thoughts, portfolio data, trades, positions, and performance metrics.

File: paper_trading/api/data_api.py
"""

import logging
from datetime import datetime, timedelta
import asyncio
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.db.models import Sum
from django.utils import timezone
import decimal
# Import models
from ..models import (
    PaperTrade,
    PaperPosition,
    PaperAIThoughtLog,
    PaperPerformanceMetrics,
)

# Import constants for field names
from ..constants import (
    ThoughtLogFields,
)

# Import utilities
from ..utils import get_single_trading_account
from ..services.price_feed_service import PriceFeedService

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS FOR SAFE DECIMAL HANDLING
# =============================================================================

def safe_float(value, default: float = 0.0) -> float:
    """
    Safely convert a value to float, handling None, invalid decimals, and empty strings.
    
    Args:
        value: The value to convert (can be None, Decimal, float, string, etc.)
        default: Default value to return if conversion fails
        
    Returns:
        float: The converted value or default
    """
    if value is None or value == '':
        return default
    
    try:
        # Handle Decimal type explicitly
        if isinstance(value, Decimal):
            return float(value)
        # Try to convert other types
        return float(value)
    except (TypeError, ValueError, decimal.InvalidOperation) as e:
        logger.warning(f"Invalid decimal/numeric value encountered: {value}, error: {e}")
        return default


def safe_decimal(value, default: str = '0.0') -> Decimal:
    """
    Safely convert a value to Decimal, handling None, invalid values, and empty strings.
    
    Args:
        value: The value to convert
        default: Default value as string to return if conversion fails
        
    Returns:
        Decimal: The converted value or default
    """
    if value is None or value == '':
        return Decimal(default)
    
    try:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
    except (TypeError, ValueError, decimal.InvalidOperation) as e:
        logger.warning(f"Invalid decimal value encountered: {value}, error: {e}")
        return Decimal(default)


# =============================================================================
# AI THOUGHTS API
# =============================================================================

@require_http_methods(["GET"])
def api_ai_thoughts(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for AI thought logs with real-time updates.

    Returns recent AI decision-making thoughts for transparency.

    Query Parameters:
        limit: Number of thoughts to return (default: 20, max: 100)

    Returns:
        JsonResponse: List of AI thoughts
    """
    try:
        # Get query parameters
        limit = min(int(request.GET.get('limit', 20)), 100)

        # Get thoughts ordered by timestamp
        thoughts = PaperAIThoughtLog.objects.all().order_by('-created_at')[:limit]

        # Format thoughts for response
        thoughts_data = []
        for thought in thoughts:
            thought_data = {
                'thought_id': str(thought.thought_id),
                'thought_type': thought.thought_type,
                'intelligence_level': thought.intelligence_level,
                'content': thought.content,
                'metadata': thought.metadata or {},
                'created_at': thought.created_at.isoformat(),
            }

            # Add token symbol from metadata if available
            if thought.metadata and 'token_symbol' in thought.metadata:
                thought_data['token_symbol'] = thought.metadata['token_symbol']

            thoughts_data.append(thought_data)

        return JsonResponse({
            'success': True,
            'thoughts': thoughts_data,
            'count': len(thoughts_data)
        })

    except Exception as e:
        logger.error(f"Error in AI thoughts API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# PORTFOLIO DATA API
# =============================================================================

@require_http_methods(["GET"])
def api_portfolio_data(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for complete portfolio overview.

    Returns account balance, positions, and performance metrics.

    Returns:
        JsonResponse: Portfolio data including balance and positions
    """
    try:
        account = get_single_trading_account()

        # Get open positions with safe decimal handling
        positions = PaperPosition.objects.filter(
            account=account,
            is_open=True
        ).values(
            'position_id',
            'token_symbol',
            'quantity',
            'average_entry_price_usd',
            'current_price_usd',
            'current_value_usd',
            'unrealized_pnl_usd',
            'opened_at'
        )

        # Format positions with safe conversion
        positions_data = []
        total_positions_value = 0.0
        
        for position in positions:
            try:
                quantity = safe_float(position['quantity'])
                if quantity <= 0:
                    logger.warning(f"Skipping position {position['position_id']} with invalid quantity")
                    continue
                    
                current_value = safe_float(position['current_value_usd'])
                total_positions_value += current_value
                
                positions_data.append({
                    'position_id': str(position['position_id']),
                    'token_symbol': position['token_symbol'] or 'UNKNOWN',
                    'quantity': quantity,
                    'average_entry_price_usd': safe_float(position['average_entry_price_usd']),
                    'current_price_usd': safe_float(position['current_price_usd']),
                    'current_value_usd': current_value,
                    'unrealized_pnl_usd': safe_float(position['unrealized_pnl_usd']),
                    'opened_at': position['opened_at'].isoformat() if position['opened_at'] else None,
                })
            except Exception as e:
                logger.error(f"Error processing position {position.get('position_id')}: {e}")
                continue

        # Calculate portfolio metrics with safe conversion
        cash_balance = safe_float(account.current_balance_usd, 10000.0)
        portfolio_value = cash_balance + total_positions_value
        total_pnl = safe_float(account.total_profit_loss_usd)
        
        return JsonResponse({
            'success': True,
            'portfolio': {
                'account_id': str(account.account_id),
                'cash_balance': cash_balance,
                'positions_value': total_positions_value,
                'total_value': portfolio_value,
                'total_pnl': total_pnl,
                'positions_count': len(positions_data),
                'winning_trades': account.winning_trades,
                'losing_trades': account.losing_trades,
            },
            'positions': positions_data
        })

    except Exception as e:
        logger.error(f"Error in portfolio data API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# TRADES DATA API
# =============================================================================

@require_http_methods(["GET"])
def api_trades_data(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for trade history with filtering options.

    Query Parameters:
        status: Filter by trade status (executed, pending, failed)
        limit: Number of trades to return (default: 50, max: 200)
        token: Filter by token symbol

    Returns:
        JsonResponse: List of trades
    """
    try:
        account = get_single_trading_account()

        # Build query with filters
        trades_query = PaperTrade.objects.filter(account=account)

        # Apply filters
        status = request.GET.get('status')
        if status:
            trades_query = trades_query.filter(status=status.upper())

        token = request.GET.get('token')
        if token:
            trades_query = trades_query.filter(token_out_symbol__iexact=token)

        # Apply limit
        limit = min(int(request.GET.get('limit', 50)), 200)
        
        # Get trades using values to avoid decimal issues
        trades = trades_query.values(
            'trade_id',
            'trade_type',
            'token_in_symbol',
            'token_in_address',
            'token_out_symbol',
            'token_out_address',
            'amount_in',
            'amount_in_usd',
            'expected_amount_out',
            'actual_amount_out',
            'status',
            'executed_at',
            'simulated_gas_cost_usd',
            'simulated_slippage_percent',
            'created_at'
        ).order_by('-created_at')[:limit]

        # Format trades with safe decimal conversion
        trades_data = []
        for trade in trades:
            try:
                trades_data.append({
                    'trade_id': str(trade['trade_id']),
                    'trade_type': trade['trade_type'],
                    'token_in_symbol': trade['token_in_symbol'],
                    'token_in_address': trade['token_in_address'],
                    'token_out_symbol': trade['token_out_symbol'],
                    'token_out_address': trade['token_out_address'],
                    'amount_in': safe_float(trade['amount_in']),
                    'amount_in_usd': safe_float(trade['amount_in_usd']),
                    'expected_amount_out': safe_float(trade['expected_amount_out']),
                    'actual_amount_out': safe_float(trade['actual_amount_out']) if trade['actual_amount_out'] else None,
                    'status': trade['status'],
                    'executed_at': trade['executed_at'].isoformat() if trade['executed_at'] else None,
                    'simulated_gas_cost_usd': safe_float(trade['simulated_gas_cost_usd']),
                    'simulated_slippage_percent': safe_float(trade['simulated_slippage_percent']),
                })
            except Exception as e:
                logger.error(f"Error processing trade {trade.get('trade_id')}: {e}")
                continue

        return JsonResponse({
            'success': True,
            'trades': trades_data,
            'count': len(trades_data)
        })

    except Exception as e:
        logger.error(f"Error in trades data API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# RECENT TRADES API
# =============================================================================

@require_http_methods(["GET"])
def api_recent_trades(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for most recent trades (last 24 hours).
    
    Uses values() query to avoid decimal conversion errors with corrupted data.
    Individual trades with invalid decimals are skipped with warnings.
    
    Returns:
        JsonResponse: Recent trades list with success status
    """
    try:
        account = get_single_trading_account()
        
        # Get trades from last 24 hours using values() to avoid model conversion
        cutoff_time = timezone.now() - timedelta(hours=24)
        
        trades = PaperTrade.objects.filter(
            account=account,
            created_at__gte=cutoff_time
        ).values(
            'trade_id',
            'trade_type', 
            'token_out_symbol',
            'amount_in_usd',
            'status',
            'created_at'
        ).order_by('-created_at')[:10]
        
        # Format trades with safe decimal handling
        trades_data = []
        for trade in trades:
            try:
                trades_data.append({
                    'trade_id': str(trade['trade_id']),
                    'type': trade['trade_type'],
                    'token': trade['token_out_symbol'],
                    'amount_usd': safe_float(trade['amount_in_usd']),
                    'status': trade['status'],
                    'time': trade['created_at'].isoformat() if trade['created_at'] else None
                })
            except Exception as e:
                logger.warning(f"Skipping trade {trade.get('trade_id')} due to error: {e}")
                continue
        
        return JsonResponse({
            'success': True,
            'trades': trades_data
        })
        
    except Exception as e:
        logger.error(f"Error fetching recent trades: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'trades': []
        }, status=500)


# =============================================================================
# OPEN POSITIONS API
# =============================================================================

@require_http_methods(["GET"])
def api_open_positions(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for current open positions with safe decimal handling.

    Returns:
        JsonResponse: List of open positions with current values
    """
    try:
        account = get_single_trading_account()

        # Get all open positions - Using values() to avoid decimal conversion issues
        # This fetches data as native Python types, avoiding Django's decimal converter
        open_positions = PaperPosition.objects.filter(
            account=account,
            is_open=True
        ).values(
            'position_id',
            'token_symbol',
            'quantity',
            'average_entry_price_usd',
            'current_price_usd',
            'current_value_usd',
            'unrealized_pnl_usd',
            'opened_at'
        )

        # Format positions with safe decimal handling
        positions_data = []
        for position in open_positions:
            try:
                # Safe conversion with validation
                quantity = safe_float(position['quantity'])
                
                # Skip positions with invalid quantity
                if quantity <= 0:
                    logger.warning(f"Skipping position {position['position_id']} with zero/invalid quantity")
                    continue
                
                position_data = {
                    'position_id': str(position['position_id']),
                    'token_symbol': position['token_symbol'] or 'UNKNOWN',
                    'quantity': quantity,
                    'average_entry_price_usd': safe_float(position['average_entry_price_usd']),
                    'current_price_usd': safe_float(position['current_price_usd']),
                    'current_value_usd': safe_float(position['current_value_usd']),
                    'unrealized_pnl_usd': safe_float(position['unrealized_pnl_usd']),
                    'opened_at': position['opened_at'].isoformat() if position['opened_at'] else None,
                }
                
                positions_data.append(position_data)
                    
            except Exception as pos_error:
                logger.error(f"Error processing position {position.get('position_id', 'unknown')}: {pos_error}")
                continue

        # Sort by current_value_usd descending (done in Python since DB sort might fail with NULL values)
        positions_data.sort(key=lambda x: x['current_value_usd'], reverse=True)

        return JsonResponse({
            'success': True,
            'positions': positions_data,
            'count': len(positions_data)
        })

    except Exception as e:
        logger.error(f"Error in open positions API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# METRICS API
# =============================================================================

@require_http_methods(["GET"])
def api_metrics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for key performance metrics with safe decimal handling.

    Returns:
        JsonResponse: Dashboard KPIs and statistics
    """
    try:
        account = get_single_trading_account()

        # Calculate basic metrics
        total_trades = PaperTrade.objects.filter(account=account).count()

        # Use account-level statistics
        winning_trades = account.winning_trades
        losing_trades = account.losing_trades

        # Calculate win rate
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        # Get initial balance for P&L calculation
        initial_balance = safe_float(account.initial_balance_usd, 10000.0)
        
        # Get current cash balance
        cash_balance = safe_float(account.current_balance_usd, 10000.0)

        # Get open positions value with safe aggregation
        open_positions_result = PaperPosition.objects.filter(
            account=account,
            is_open=True
        ).aggregate(total=Sum('current_value_usd'))
        
        open_positions_value = safe_float(open_positions_result['total'])

        # Calculate portfolio value (cash + positions)
        portfolio_value = cash_balance + open_positions_value
        
        # ✅ CALCULATE total P&L from actual portfolio value vs initial balance
        # This gives the true profit/loss, not relying on account.total_profit_loss_usd
        total_pnl = portfolio_value - initial_balance
        
        # ✅ CALCULATE ROI from actual values
        roi = (total_pnl / initial_balance * 100) if initial_balance > 0 else 0

        return JsonResponse({
            'success': True,
            'metrics': {
                'portfolio_value': portfolio_value,
                'cash_balance': cash_balance,
                'total_pnl': total_pnl,  # ✅ Now calculated correctly
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': round(win_rate, 2),
                'roi': round(roi, 2),  # ✅ Now calculated correctly
            }
        })

    except Exception as e:
        logger.error(f"Error in metrics API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# PERFORMANCE METRICS API
# =============================================================================

@require_http_methods(["GET"])
def api_performance_metrics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for detailed performance metrics.

    Returns:
        JsonResponse: Detailed performance analytics
    """
    try:
        account = get_single_trading_account()

        # Get or create performance metrics
        metrics, created = PaperPerformanceMetrics.objects.get_or_create(
            account=account,
            defaults={
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown_percent': 0.0,
                'avg_win_usd': 0.0,
                'avg_loss_usd': 0.0,
                'best_trade_pnl_usd': 0.0,
                'worst_trade_pnl_usd': 0.0,
                'total_volume_usd': 0.0,
                'trades_last_24h': 0,
                'trades_last_7d': 0,
                'trades_last_30d': 0,
            }
        )

        # Format metrics with safe decimal conversion
        return JsonResponse({
            'success': True,
            'metrics': {
                'win_rate': safe_float(metrics.win_rate),
                'profit_factor': safe_float(metrics.profit_factor),
                'sharpe_ratio': safe_float(metrics.sharpe_ratio),
                'max_drawdown_percent': safe_float(metrics.max_drawdown_percent),
                'avg_win_usd': safe_float(metrics.avg_win_usd),
                'avg_loss_usd': safe_float(metrics.avg_loss_usd),
                'best_trade_pnl_usd': safe_float(metrics.best_trade_pnl_usd),
                'worst_trade_pnl_usd': safe_float(metrics.worst_trade_pnl_usd),
                'total_volume_usd': safe_float(metrics.total_volume_usd),
                'trades_last_24h': metrics.trades_last_24h,
                'trades_last_7d': metrics.trades_last_7d,
                'trades_last_30d': metrics.trades_last_30d,
                'last_updated': metrics.last_updated.isoformat() if metrics.last_updated else None,
            }
        })

    except Exception as e:
        logger.error(f"Error in performance metrics API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# REAL-TIME PRICE UPDATES API
# =============================================================================

@require_http_methods(["GET"])
async def api_price_updates(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for real-time token price updates.

    Query Parameters:
        tokens: Comma-separated list of token symbols

    Returns:
        JsonResponse: Current prices for requested tokens
    """
    try:
        tokens = request.GET.get('tokens', '').split(',')
        tokens = [t.strip().upper() for t in tokens if t.strip()]

        if not tokens:
            return JsonResponse({
                'success': False,
                'error': 'No tokens specified'
            }, status=400)

        # Get price feed service
        price_service = PriceFeedService()

        # Fetch prices asynchronously
        prices = {}
        for token in tokens:
            try:
                price_data = await price_service.get_token_price(token)
                if price_data:
                    prices[token] = {
                        'price_usd': safe_float(price_data.get('price_usd')),
                        'change_24h': safe_float(price_data.get('change_24h')),
                        'volume_24h': safe_float(price_data.get('volume_24h')),
                        'market_cap': safe_float(price_data.get('market_cap')),
                        'last_updated': price_data.get('last_updated'),
                    }
            except Exception as e:
                logger.error(f"Error fetching price for {token}: {e}")
                prices[token] = {'error': str(e)}

        return JsonResponse({
            'success': True,
            'prices': prices,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in price updates API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# TOKEN PRICE API
# =============================================================================

@require_http_methods(["GET"])
def api_token_price(request: HttpRequest, token_symbol: str) -> JsonResponse:
    """
    API endpoint for single token price lookup.
    
    Args:
        token_symbol: Token symbol to look up (e.g., 'WETH', 'USDC')
    
    Returns:
        JsonResponse: Current token price data
    """
    # Initialize to None to avoid unbound variable warning
    price_service = None
    
    try:
        # Import DEFAULT_CHAIN_ID from Django settings
        from django.conf import settings
        chain_id = getattr(settings, 'DEFAULT_CHAIN_ID', 8453)  # Default to Base mainnet
        
        # Initialize price service with required chain_id
        price_service = PriceFeedService(chain_id=chain_id)
        
        # Get token address from the service's token mapping
        token_addresses = price_service.token_addresses
        token_address = token_addresses.get(token_symbol.upper())
        
        if not token_address:
            return JsonResponse({
                'success': False,
                'error': f'Token {token_symbol} not found in configured tokens for chain {chain_id}'
            }, status=404)
        
        # Get token price using correct method signature
        price = asyncio.run(price_service.get_token_price(
            token_address=token_address,
            token_symbol=token_symbol.upper()
        ))
        
        if not price:
            return JsonResponse({
                'success': False,
                'error': f'Price not available for {token_symbol}'
            }, status=404)
        
        # Use safe_float for price conversion
        return JsonResponse({
            'success': True,
            'token': token_symbol.upper(),
            'price': safe_float(price),
            'chain_id': chain_id
        })
    
    except Exception as e:
        logger.error(f"Error in token price API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
    finally:
        # Cleanup: Close the price service session if it was created
        if price_service is not None:
            try:
                asyncio.run(price_service.close())
            except Exception as cleanup_error:
                logger.debug(f"Error closing price service: {cleanup_error}")


# =============================================================================
# POSITION HISTORY API
# =============================================================================

@require_http_methods(["GET"])
def api_position_history(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for closed position history.

    Query Parameters:
        days: Number of days of history (default: 30)
        limit: Maximum positions to return (default: 100)

    Returns:
        JsonResponse: List of closed positions
    """
    try:
        account = get_single_trading_account()

        # Get query parameters
        days = int(request.GET.get('days', 30))
        limit = min(int(request.GET.get('limit', 100)), 500)

        # Calculate cutoff date
        cutoff_date = timezone.now() - timedelta(days=days)

        # Get closed positions using values() for safe decimal handling
        closed_positions = PaperPosition.objects.filter(
            account=account,
            is_open=False,
            closed_at__gte=cutoff_date
        ).values(
            'position_id',
            'token_symbol',
            'quantity',
            'average_entry_price_usd',
            'average_exit_price_usd',
            'realized_pnl_usd',
            'total_fees_usd',
            'opened_at',
            'closed_at'
        ).order_by('-closed_at')[:limit]

        # Format positions with safe conversion
        positions_data = []
        for position in closed_positions:
            try:
                positions_data.append({
                    'position_id': str(position['position_id']),
                    'token_symbol': position['token_symbol'] or 'UNKNOWN',
                    'quantity': safe_float(position['quantity']),
                    'entry_price': safe_float(position['average_entry_price_usd']),
                    'exit_price': safe_float(position['average_exit_price_usd']),
                    'realized_pnl': safe_float(position['realized_pnl_usd']),
                    'fees': safe_float(position['total_fees_usd']),
                    'opened_at': position['opened_at'].isoformat() if position['opened_at'] else None,
                    'closed_at': position['closed_at'].isoformat() if position['closed_at'] else None,
                    'duration_hours': (
                        (position['closed_at'] - position['opened_at']).total_seconds() / 3600
                        if position['closed_at'] and position['opened_at'] else 0
                    ),
                })
            except Exception as e:
                logger.error(f"Error processing closed position {position.get('position_id')}: {e}")
                continue

        # Calculate summary statistics
        total_pnl = sum(p['realized_pnl'] for p in positions_data)
        winning_positions = [p for p in positions_data if p['realized_pnl'] > 0]
        losing_positions = [p for p in positions_data if p['realized_pnl'] < 0]

        return JsonResponse({
            'success': True,
            'positions': positions_data,
            'summary': {
                'total_positions': len(positions_data),
                'winning_positions': len(winning_positions),
                'losing_positions': len(losing_positions),
                'total_pnl': total_pnl,
                'avg_pnl': total_pnl / len(positions_data) if positions_data else 0,
                'best_trade': max((p['realized_pnl'] for p in positions_data), default=0),
                'worst_trade': min((p['realized_pnl'] for p in positions_data), default=0),
            }
        })

    except Exception as e:
        logger.error(f"Error in position history API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)