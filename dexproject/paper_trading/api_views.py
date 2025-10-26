"""
Paper Trading API Views - REST API Endpoints

This module provides all API endpoints for the paper trading system including
real-time data feeds, bot control, and configuration management.

File: dexproject/paper_trading/api_views.py
"""

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from .services.price_feed_service import PriceFeedService
import asyncio
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Sum, Avg, Count
from django.utils import timezone
from django.core.cache import cache
from django.contrib.auth.models import User

# Import all models
from .models import (
    PaperTradingAccount,
    PaperTrade,
    PaperPosition,
    PaperTradingConfig,
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    PaperTradingSession,
    PaperPerformanceMetrics
)

# Import Celery tasks for bot control with proper type hints
if TYPE_CHECKING:
    # For type checking, import as Celery Task type
    from celery import Task
    run_paper_trading_bot: Task  # type: ignore
    stop_paper_trading_bot: Task  # type: ignore
    # Help Pylance recognize Django User model has id attribute
    from django.contrib.auth.models import AbstractUser
    User = AbstractUser
else:
    # At runtime, import the actual shared_task decorated functions
    from .tasks import run_paper_trading_bot, stop_paper_trading_bot

# Import centralized account utilities (REFACTORED: removed duplicate get_default_user)
from .utils import get_default_user, get_single_trading_account

logger = logging.getLogger(__name__)


# =============================================================================
# DATA API ENDPOINTS
# =============================================================================

@require_http_methods(["GET"])
def api_ai_thoughts(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for AI thought logs with real-time updates.
    
    Returns recent AI decision-making thoughts for transparency.
    
    Query Parameters:
        limit (int): Maximum number of thoughts to return (default: 10)
        since (str): ISO datetime to get thoughts after
    
    Returns:
        JsonResponse: AI thoughts data with metadata
    """
    try:
        # Get the single trading account (creates if doesn't exist)
        account: PaperTradingAccount = get_single_trading_account()
        
        # Get query parameters
        limit = int(request.GET.get('limit', 10))
        since = request.GET.get('since')
        
        # Build query
        thoughts_query = PaperAIThoughtLog.objects.filter(account=account)
        
        if since:
            since_datetime = datetime.fromisoformat(since)
            thoughts_query = thoughts_query.filter(created_at__gt=since_datetime)
        
        # Get thoughts ordered by creation time
        thoughts = thoughts_query.order_by('-created_at')[:limit]
        
        # Build response data
        thoughts_data = {
            'thoughts': [
                {
                    'id': str(thought.thought_id),
                    'metadata': thought.market_data or {},  # FIXED: Use market_data instead of metadata
                    'created_at': thought.created_at.isoformat(),
                    'importance': float(thought.confidence_level),  # FIXED: Use confidence_level instead of importance_score
                    # Additional fields for dashboard display
                    'decision_type': thought.market_data.get('decision_type', 'ANALYSIS') if thought.market_data else 'ANALYSIS',
                    'token_symbol': thought.market_data.get('token_symbol', '') if thought.market_data else '',
                    'lane_used': thought.market_data.get('lane_used', 'SMART') if thought.market_data else 'SMART',
                    'confidence_percent': thought.market_data.get('confidence', 50) if thought.market_data else 50,
                    'primary_reasoning': thought.reasoning[:200] if thought.reasoning else '',  # FIXED: Use reasoning instead of thought_content
                    'timestamp': thought.created_at.isoformat(),
                }
                for thought in thoughts
            ],
            'count': len(thoughts),
            'timestamp': timezone.now().isoformat(),
        }
        
        return JsonResponse(thoughts_data)
        
    except Exception as e:
        logger.error(f"Error in AI thoughts API: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_portfolio_data(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for portfolio data.
    
    Returns current portfolio state including positions,
    balance, and performance metrics.
    
    Returns:
        JsonResponse: Portfolio data with positions and metrics
    """
    try:
        # Get the single trading account (creates if doesn't exist)
        account: PaperTradingAccount = get_single_trading_account()
        
        # Get open positions
        positions = PaperPosition.objects.filter(
            account=account,
            is_open=True
        )
        
        # Build portfolio data
        portfolio_data: Dict[str, Any] = {
            'account': {
                'id': str(account.account_id),
                'name': account.name,
                'balance': float(account.current_balance_usd),
                'initial_balance': float(account.initial_balance_usd),
                'total_pnl': float(account.total_profit_loss_usd),
                'return_percent': float(account.get_roi()),
                'win_rate': float(account.get_win_rate()),
            },
            'positions': [],
            'summary': {
                'total_value': float(account.current_balance_usd),
                'positions_count': positions.count(),
                'cash_percentage': 100.0,
            },
            'timestamp': timezone.now().isoformat(),
        }
        
        # Process positions with calculated fields
        total_position_value = Decimal('0')
        for pos in positions:
            # Calculate unrealized_pnl_percent dynamically
            if pos.total_invested_usd and pos.total_invested_usd > 0:
                unrealized_pnl_percent = (pos.unrealized_pnl_usd / pos.total_invested_usd) * 100
            else:
                unrealized_pnl_percent = Decimal('0')
            
            position_dict = {
                'id': str(pos.position_id),
                'token_symbol': pos.token_symbol,
                'token_address': pos.token_address,
                'quantity': float(pos.quantity),
                'entry_price': float(pos.average_entry_price_usd) if pos.average_entry_price_usd else 0,
                'current_price': float(pos.current_price_usd) if pos.current_price_usd else 0,
                'current_value': float(pos.current_value_usd) if pos.current_value_usd else 0,
                'unrealized_pnl': float(pos.unrealized_pnl_usd),
                'unrealized_pnl_percent': float(unrealized_pnl_percent),
                'opened_at': pos.opened_at.isoformat(),
            }
            portfolio_data['positions'].append(position_dict)
            total_position_value += pos.current_value_usd or Decimal('0')
        
        # Update summary
        total_value = account.current_balance_usd + total_position_value
        portfolio_data['summary']['total_value'] = float(total_value)
        portfolio_data['summary']['cash_percentage'] = float(
            (account.current_balance_usd / total_value * 100) if total_value > 0 else 100
        )
        
        logger.debug("Portfolio data fetched")
        return JsonResponse(portfolio_data)
        
    except Exception as e:
        logger.error(f"Error in portfolio API: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_trades_data(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for trade history data with filtering support.
    
    Returns trade history with pagination and filtering options.
    
    Query Parameters:
        limit (int): Maximum number of trades to return (default: 10, max: 50)
        since (str): ISO datetime to get trades after
        status (str): Filter by trade status
    
    Returns:
        JsonResponse: Trade history data with filters applied
    """
    try:
        # Get the single trading account (creates if doesn't exist)
        account: PaperTradingAccount = get_single_trading_account()
        
        # Build query for trades
        trades_query = PaperTrade.objects.filter(account=account)
        
        # Apply filters from query parameters
        status_filter = request.GET.get('status')
        if status_filter:
            trades_query = trades_query.filter(status=status_filter)
        
        since = request.GET.get('since')
        if since:
            try:
                since_datetime = datetime.fromisoformat(since)
                trades_query = trades_query.filter(created_at__gt=since_datetime)
            except (ValueError, TypeError):
                logger.warning(f"Invalid since parameter: {since}")
        
        # Get recent trades with limit
        limit = min(int(request.GET.get('limit', 10)), 50)
        trades = trades_query.order_by('-created_at')[:limit]
        
        # Build response data
        trades_data: List[Dict[str, Any]] = []
        for trade in trades:
            trade_data = {
                'trade_id': str(trade.trade_id),
                'trade_type': trade.trade_type.upper() if trade.trade_type else 'UNKNOWN',
                'token_symbol': trade.token_out_symbol if trade.trade_type == 'buy' else trade.token_in_symbol,
                'token_out_symbol': trade.token_out_symbol,
                'token_in_symbol': trade.token_in_symbol,
                'amount_in_usd': float(trade.amount_in_usd) if trade.amount_in_usd else 0,
                'amount_usd': float(trade.amount_in_usd) if trade.amount_in_usd else 0,
                'price': float(trade.amount_in_usd) if trade.amount_in_usd else 0,
                'status': trade.status.upper() if trade.status else 'PENDING',
                'created_at': trade.created_at.isoformat(),
                'execution_time_ms': trade.execution_time_ms,
            }
            
            # FIXED: Use getattr() with default values instead of direct attribute access
            # Add P&L if available - safely check and retrieve attributes
            pnl_usd = getattr(trade, 'pnl_usd', None)
            if pnl_usd is not None:
                trade_data['pnl_usd'] = float(pnl_usd)
                # Also safely get pnl_percent with default
                pnl_percent = getattr(trade, 'pnl_percent', 0)
                trade_data['pnl_percent'] = float(pnl_percent) if pnl_percent else 0
            
            trades_data.append(trade_data)
        
        logger.debug(f"Recent trades fetched: {len(trades_data)} trades")
        
        return JsonResponse({
            'success': True,
            'trades': trades_data,
            'count': len(trades_data),
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in api_recent_trades: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch recent trades',
            'trades': []
        }, status=500)


# Alias for backward compatibility with urls.py
api_recent_trades = api_trades_data



# =============================================================================
# HELPER FUNCTION: TOKEN ADDRESS RESOLUTION
# =============================================================================

def _get_token_address(token_symbol: str, chain_id: int = 84532) -> Optional[str]:
    """
    Get token contract address for a given symbol and chain.
    
    Supports multiple chains with their respective token addresses.
    
    Args:
        token_symbol: Token symbol (e.g., 'WETH', 'USDC')
        chain_id: Blockchain network ID (default: 84532 - Base Sepolia)
    
    Returns:
        Token contract address or None if not found
    """
    # Base Sepolia (84532) - Default testnet
    if chain_id == 84532:
        token_addresses = {
            'WETH': '0x4200000000000000000000000000000000000006',
            'ETH': '0x4200000000000000000000000000000000000006',  # Same as WETH
            'USDC': '0x036CbD53842c5426634e7929541eC2318f3dCF7e',
            'DAI': '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb',
        }
        return token_addresses.get(token_symbol.upper())
    
    # Ethereum Sepolia (11155111)
    elif chain_id == 11155111:
        token_addresses = {
            'WETH': '0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14',
            'USDC': '0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238',
            'DAI': '0x3e622317f8C93f7328350cF0B56d9eD4C620C5d6',
            'LINK': '0x779877A7B0D9E8603169DdbD7836e478b4624789',
        }
        return token_addresses.get(token_symbol.upper())
    
    # Base Mainnet (8453)
    elif chain_id == 8453:
        token_addresses = {
            'WETH': '0x4200000000000000000000000000000000000006',
            'USDC': '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
            'DAI': '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb',
            'cbETH': '0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22',
        }
        return token_addresses.get(token_symbol.upper())
    
    # Ethereum Mainnet (1)
    elif chain_id == 1:
        token_addresses = {
            'WETH': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
            'USDC': '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',
            'USDT': '0xdAC17F958D2ee523a2206206994597C13D831ec7',
            'DAI': '0x6B175474E89094C44Da98b954EedeAC495271d0F',
            'WBTC': '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599',
        }
        return token_addresses.get(token_symbol.upper())
    
    return None


@require_http_methods(["GET"])
def api_token_price(request: HttpRequest, token_symbol: str) -> JsonResponse:
    """
    API endpoint to get current token price from REAL sources only.
    
    Fetches live prices from Alchemy/CoinGecko APIs.
    NO MOCK DATA - returns error if price unavailable.
    
    Args:
        token_symbol: Token symbol (e.g., 'WETH', 'USDC')
    
    Query Parameters:
        chain_id (int): Optional chain ID (default: 84532 - Base Sepolia)
    
    Returns:
        JsonResponse: Token price data from live sources
        
    Response Format (Success):
        {
            'success': true,
            'token_symbol': 'WETH',
            'token_address': '0x4200...',
            'price_usd': 2543.50,
            'chain_id': 84532,
            'timestamp': '2025-01-...',
            'source': 'live'
        }
    
    Response Format (Error):
        {
            'success': false,
            'error': 'Error message',
            'token_symbol': 'WETH',
            'chain_id': 84532
        }
    """
    try:
        # Get chain_id from query params or use default
        chain_id = int(request.GET.get('chain_id', 84532))
        token_symbol_upper = token_symbol.upper()
        
        logger.info(
            f"[API] Fetching price for {token_symbol_upper} on chain {chain_id}"
        )
        
        # Get token contract address
        token_address = _get_token_address(token_symbol_upper, chain_id)
        
        if not token_address:
            logger.warning(
                f"[API] Token {token_symbol_upper} not supported on chain {chain_id}"
            )
            
            # Get list of supported tokens for this chain
            supported_tokens = []
            if chain_id == 84532:
                supported_tokens = ['WETH', 'ETH', 'USDC', 'DAI']
            elif chain_id == 11155111:
                supported_tokens = ['WETH', 'USDC', 'DAI', 'LINK']
            elif chain_id == 8453:
                supported_tokens = ['WETH', 'USDC', 'DAI', 'cbETH']
            elif chain_id == 1:
                supported_tokens = ['WETH', 'USDC', 'USDT', 'DAI', 'WBTC']
            
            return JsonResponse({
                'success': False,
                'error': f'Token {token_symbol_upper} not supported on chain {chain_id}',
                'token_symbol': token_symbol_upper,
                'chain_id': chain_id,
                'supported_tokens': supported_tokens
            }, status=404)
        
        # Initialize PriceFeedService with correct chain_id (FIXED!)
        try:
            price_feed = PriceFeedService(chain_id=chain_id)
            
            # Fetch real price using correct method signature (FIXED!)
            price = asyncio.run(
                price_feed.get_token_price(
                    token_address=token_address,
                    token_symbol=token_symbol_upper
                )
            )
            
            # Close the service to cleanup resources
            asyncio.run(price_feed.close())
            
            if price is not None and price > 0:
                logger.info(
                    f"[API] ✅ Successfully fetched {token_symbol_upper} price: "
                    f"${float(price):.2f}"
                )
                return JsonResponse({
                    'success': True,
                    'token_symbol': token_symbol_upper,
                    'token_address': token_address,
                    'price_usd': float(price),
                    'chain_id': chain_id,
                    'timestamp': timezone.now().isoformat(),
                    'source': 'live'
                })
            else:
                # Price fetch returned None or 0 - service is down or rate limited
                logger.warning(
                    f"[API] Price service returned no data for {token_symbol_upper}"
                )
                return JsonResponse({
                    'success': False,
                    'error': f'Price data temporarily unavailable for {token_symbol_upper}',
                    'token_symbol': token_symbol_upper,
                    'token_address': token_address,
                    'chain_id': chain_id,
                    'message': 'Try again in a few moments. API may be rate limited or temporarily down.'
                }, status=503)
                
        except asyncio.TimeoutError:
            logger.error(f"[API] Timeout fetching price for {token_symbol_upper}")
            return JsonResponse({
                'success': False,
                'error': 'Price fetch timeout - API request took too long',
                'token_symbol': token_symbol_upper,
                'chain_id': chain_id
            }, status=504)
            
        except Exception as price_error:
            logger.error(
                f"[API] Error fetching price for {token_symbol_upper}: {price_error}",
                exc_info=True
            )
            return JsonResponse({
                'success': False,
                'error': f'Could not fetch price: {str(price_error)}',
                'token_symbol': token_symbol_upper,
                'chain_id': chain_id
            }, status=500)
        
    except ValueError as ve:
        logger.error(f"[API] Invalid chain_id parameter: {ve}")
        return JsonResponse({
            'success': False,
            'error': 'Invalid chain_id parameter - must be an integer',
            'token_symbol': token_symbol
        }, status=400)
        
    except Exception as e:
        logger.error(
            f"[API] Unexpected error in api_token_price for {token_symbol}: {e}",
            exc_info=True
        )
        return JsonResponse({
            'success': False,
            'error': f'Internal server error: {str(e)}',
            'token_symbol': token_symbol
        }, status=500)




@require_http_methods(["GET"])
def api_open_positions(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to get current open positions.
    
    Returns all open positions with current values and P&L calculations.
    
    Returns:
        JsonResponse: Open positions with current market values
    """
    try:
        # Get the single trading account (creates if doesn't exist)
        account: PaperTradingAccount = get_single_trading_account()
        
        # Get open positions
        positions = PaperPosition.objects.filter(
            account=account,
            is_open=True
        )
        
        # Build positions data
        positions_data: List[Dict[str, Any]] = []
        total_value = Decimal('0')
        total_pnl = Decimal('0')
        total_invested = Decimal('0')
        
        for position in positions:
            # Calculate current values
            current_value = position.current_value_usd or Decimal('0')
            unrealized_pnl = position.unrealized_pnl_usd
            invested = position.total_invested_usd or Decimal('0')
            
            # Calculate P&L percentage
            if invested > 0:
                pnl_percent = (unrealized_pnl / invested) * 100
            else:
                pnl_percent = Decimal('0')
            
            position_data = {
                'position_id': str(position.position_id),
                'token_symbol': position.token_symbol,
                'token_address': position.token_address,
                'quantity': float(position.quantity),
                'average_entry_price': float(position.average_entry_price_usd) if position.average_entry_price_usd else 0,
                'current_price': float(position.current_price_usd) if position.current_price_usd else 0,
                'cost_basis_usd': float(invested),
                'current_value_usd': float(current_value),
                'unrealized_pnl_usd': float(unrealized_pnl),
                'unrealized_pnl_percent': float(pnl_percent),
                'opened_at': position.opened_at.isoformat(),
                'last_updated': position.last_updated.isoformat() if position.last_updated else None  # FIXED: Use last_updated instead of last_updated_at
            }
            
            positions_data.append(position_data)
            total_value += current_value
            total_pnl += unrealized_pnl
            total_invested += invested
        
        # Calculate summary metrics
        total_unrealized_pnl_percent = float(
            (total_pnl / total_invested * 100) if total_invested > 0 else 0
        )
        
        summary = {
            'total_positions': len(positions_data),
            'total_value_usd': float(total_value),
            'total_cost_basis_usd': float(total_invested),
            'total_unrealized_pnl_usd': float(total_pnl),
            'total_unrealized_pnl_percent': total_unrealized_pnl_percent
        }
        
        logger.debug(f"Open positions fetched: {len(positions_data)} positions")
        
        return JsonResponse({
            'success': True,
            'positions': positions_data,
            'summary': summary,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in api_open_positions: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch open positions',
            'positions': []
        }, status=500)


@require_http_methods(["GET"])
def api_metrics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for dashboard metrics summary.
    
    Returns key performance indicators for the dashboard display.
    
    Returns:
        JsonResponse: Metrics data including P&L, win rate, and trading volume
    """
    try:
        # Get the single trading account (creates if doesn't exist)
        account: PaperTradingAccount = get_single_trading_account()
        
        # Calculate positions value
        open_positions = PaperPosition.objects.filter(account=account, is_open=True)
        positions_value = sum(pos.current_value_usd or Decimal('0') for pos in open_positions)
        portfolio_value = account.current_balance_usd + positions_value
        
        # Calculate correct return percentage
        return_percent = float(
            ((portfolio_value - account.initial_balance_usd) / account.initial_balance_usd * 100)
            if account.initial_balance_usd > 0 else 0
        )
        
        # Get 24h stats
        time_24h_ago = timezone.now() - timedelta(hours=24)
        trades_24h_data = PaperTrade.objects.filter(
            account=account,
            created_at__gte=time_24h_ago
        ).aggregate(
            count=Count('trade_id'),
            total_volume=Sum('amount_in_usd')
        )
        
        metrics = {
            'success': True,
            'current_balance': float(account.current_balance_usd),
            'initial_balance': float(account.initial_balance_usd),
            'positions_value': float(positions_value),
            'portfolio_value': float(portfolio_value),
            'total_pnl': float(account.total_profit_loss_usd),
            'return_percent': return_percent,
            'win_rate': float(account.get_win_rate()) if account.get_win_rate() else 0,
            'trades_24h': trades_24h_data['count'] or 0,
            'volume_24h': float(trades_24h_data['total_volume']) if trades_24h_data['total_volume'] else 0,
            'total_trades': account.total_trades,
            'successful_trades': account.winning_trades,
            'failed_trades': account.losing_trades,
            'timestamp': timezone.now().isoformat()
        }
        
        logger.debug(f"Metrics fetched: portfolio=${portfolio_value:.2f}, pnl=${account.total_profit_loss_usd:.2f}")
        return JsonResponse(metrics)
        
    except Exception as e:
        logger.error(f"Error in api_metrics: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch metrics'
        }, status=500)


@require_http_methods(["GET"])
def api_performance_metrics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for performance metrics.
    
    Returns detailed performance analytics and statistics.
    
    Returns:
        JsonResponse: Performance metrics including Sharpe ratio, max drawdown, etc.
    """
    try:
        # Get the single trading account (creates if doesn't exist)
        account: PaperTradingAccount = get_single_trading_account()
        
        # Get latest performance metrics
        latest_metrics = PaperPerformanceMetrics.objects.filter(
            account=account
        ).order_by('-created_at').first()
        
        # Build metrics response
        if latest_metrics:
            metrics_data = {
                'sharpe_ratio': float(latest_metrics.sharpe_ratio) if latest_metrics.sharpe_ratio else 0,
                'max_drawdown': float(latest_metrics.max_drawdown_percent) if latest_metrics.max_drawdown_percent else 0,
                'win_rate': float(latest_metrics.win_rate) if latest_metrics.win_rate else 0,
                'profit_factor': float(latest_metrics.profit_factor) if latest_metrics.profit_factor else 0,
                'average_win': float(latest_metrics.average_win_usd) if latest_metrics.average_win_usd else 0,
                'average_loss': float(latest_metrics.average_loss_usd) if latest_metrics.average_loss_usd else 0,
                'best_trade': float(latest_metrics.largest_win_usd) if latest_metrics.largest_win_usd else 0,
                'worst_trade': float(latest_metrics.largest_loss_usd) if latest_metrics.largest_loss_usd else 0,
                'total_trades': latest_metrics.total_trades,
                'winning_trades': latest_metrics.winning_trades,
                'losing_trades': latest_metrics.losing_trades,
                'total_pnl_usd': float(latest_metrics.total_pnl_usd),
                'total_pnl_percent': float(latest_metrics.total_pnl_percent),
                'period_start': latest_metrics.period_start.isoformat(),
                'period_end': latest_metrics.period_end.isoformat(),
                'calculated_at': latest_metrics.created_at.isoformat(),
            }
        else:
            # Return default metrics if none exist
            metrics_data = {
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'win_rate': float(account.get_win_rate()) if account.get_win_rate() else 0,
                'profit_factor': 0,
                'average_win': 0,
                'average_loss': 0,
                'best_trade': 0,
                'worst_trade': 0,
                'total_trades': account.total_trades,
                'winning_trades': account.winning_trades,
                'losing_trades': account.losing_trades,
                'total_pnl_usd': float(account.total_profit_loss_usd),
                'total_pnl_percent': float(account.get_roi()),
                'message': 'No performance metrics calculated yet'
            }
        
        # Add account-level stats
        metrics_data['account_stats'] = {
            'total_pnl': float(account.total_profit_loss_usd),
            'total_return': float(account.get_roi()),
            'current_balance': float(account.current_balance_usd),
            'initial_balance': float(account.initial_balance_usd),
            'total_trades': account.total_trades,
            'successful_trades': account.winning_trades,
            'failed_trades': account.losing_trades,
            'win_rate': float(account.get_win_rate()) if account.get_win_rate() else 0,
        }
        
        logger.debug("Performance metrics fetched")
        return JsonResponse(metrics_data)
        
    except Exception as e:
        logger.error(f"Error in performance metrics API: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# CONFIGURATION API
# =============================================================================

@require_http_methods(["GET", "POST"])
@csrf_exempt
def api_configuration(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for strategy configuration management.
    
    GET: Returns current configuration
    POST: Updates configuration with new settings
    
    Returns:
        JsonResponse: Configuration data or update confirmation
    """
    try:
        # Get default user
        user = get_default_user()
        
        # Get account
        account = PaperTradingAccount.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        if not account:
            return JsonResponse({
                'error': 'No active account found'
            }, status=404)
        
        if request.method == 'GET':
            # Return current configuration
            config = PaperStrategyConfiguration.objects.filter(
                account=account,
                is_active=True
            ).first()
            
            if config:
                config_data = {
                    'config_id': str(config.config_id),
                    'name': config.name,
                    'trading_mode': config.trading_mode,  # FIXED: Use trading_mode (exists in model)
                    # REMOVED: intel_level, risk_tolerance - don't exist in model
                    'max_position_size_percent': float(config.max_position_size_percent),
                    'stop_loss_percent': float(config.stop_loss_percent),
                    'take_profit_percent': float(config.take_profit_percent),
                    # REMOVED: enable_trailing_stop, min_trade_interval_minutes - don't exist in model
                    'created_at': config.created_at.isoformat(),
                }
            else:
                # Return default config
                config_data = {
                    'name': 'Default Strategy',
                    'trading_mode': 'BALANCED',  # FIXED: Use trading_mode instead of strategy_type
                    # REMOVED: intel_level, risk_tolerance, enable_trailing_stop, min_trade_interval_minutes
                    'max_position_size_percent': 10.0,
                    'stop_loss_percent': 5.0,
                    'take_profit_percent': 15.0,
                }
            
            return JsonResponse({
                'success': True,
                'configuration': config_data
            })
        
        elif request.method == 'POST':
            # Update configuration
            try:
                body_data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid JSON in request body'
                }, status=400)
            
            # Create or update configuration
            config, created = PaperStrategyConfiguration.objects.update_or_create(
                account=account,
                is_active=True,
                defaults={
                    'name': body_data.get('name', 'Custom Strategy'),
                    'trading_mode': body_data.get('trading_mode', 'BALANCED'),  # FIXED: Use trading_mode
                    # REMOVED: intel_level, risk_tolerance, enable_trailing_stop, min_trade_interval_minutes
                    'max_position_size_percent': Decimal(str(body_data.get('max_position_size_percent', 10.0))),
                    'stop_loss_percent': Decimal(str(body_data.get('stop_loss_percent', 5.0))),
                    'take_profit_percent': Decimal(str(body_data.get('take_profit_percent', 15.0))),
                }
            )
            
            logger.info(f"Configuration {'created' if created else 'updated'}: {config.config_id}")
            
            return JsonResponse({
                'success': True,
                'message': 'Configuration updated successfully',
                'config_id': str(config.config_id),
                'created': created
            })
        
        # Should not reach here due to @require_http_methods, but add for type safety
        return JsonResponse({
            'success': False,
            'error': 'Method not allowed'
        }, status=405)
        
    except Exception as e:
        logger.error(f"Error in configuration API: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# BOT CONTROL API - NO AUTHENTICATION REQUIRED
# =============================================================================

@require_http_methods(["POST"])
@csrf_exempt
def api_start_bot(request: HttpRequest) -> JsonResponse:
    """
    Start paper trading bot.
    
    Creates a new trading session and initiates the bot process via Celery.
    
    Request Body (JSON):
        runtime_minutes (int, optional): Duration to run bot in minutes
        strategy_config (dict, optional): Custom strategy configuration
    
    Returns:
        JsonResponse: Bot start confirmation with session and task IDs
    """
    try:
        # Get the single trading account (creates if doesn't exist)
        account: PaperTradingAccount = get_single_trading_account()
        user = account.user  # Get user from account for task call
        
        # Check if bot is already running
        active_sessions = PaperTradingSession.objects.filter(
            account=account,
            status__in=['STARTING', 'RUNNING', 'PAUSED']
        )
        
        if active_sessions.exists():
            return JsonResponse({
                'success': False,
                'error': 'Bot is already running',
                'active_sessions': [str(s.session_id) for s in active_sessions]
            }, status=400)
        
        # Parse request body
        runtime_minutes: Optional[int] = None
        session_config: Dict[str, Any] = {}
        
        if request.body:
            try:
                body_data = json.loads(request.body)
                runtime_minutes = body_data.get('runtime_minutes')
                session_config = body_data.get('config', {})
            except json.JSONDecodeError:
                logger.warning("Invalid JSON in request body, using defaults")
        
        # Get or create strategy configuration
        strategy_config = PaperStrategyConfiguration.objects.filter(
            account=account,
            is_active=True
        ).first()
        
        # Create new trading session
        session = PaperTradingSession.objects.create(
            account=account,
            strategy_config=strategy_config,
            status='STARTING',
            metadata={
                'config_snapshot': session_config,
                'starting_balance_usd': float(account.current_balance_usd),
                'session_name': session_config.get('name', f'Session {timezone.now().strftime("%Y%m%d_%H%M%S")}')
            }
        )
        
        # FIXED: Start the bot via Celery task - now properly typed
        task_result = run_paper_trading_bot.delay(
            session_id=str(session.session_id),
            user_id=user.pk,  # FIXED: Use pk instead of id for Pylance compatibility
            runtime_minutes=runtime_minutes
        )
        
        # Store task ID in session metadata
        session.metadata = session.metadata or {}
        session.metadata['celery_task_id'] = task_result.id
        session.save()
        
        logger.info(
            f"Started paper trading session {session.session_id} with task {task_result.id}"
        )
        
        return JsonResponse({
            'success': True,
            'session_id': str(session.session_id),
            'task_id': task_result.id,
            'message': 'Paper trading bot started',
            'status': 'starting',
            'account_balance': float(account.current_balance_usd)
        })
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def api_stop_bot(request: HttpRequest) -> JsonResponse:
    """
    Stop paper trading bot.
    
    Ends active trading sessions and stops the bot process via Celery.
    
    Request Body (JSON, optional):
        reason (str): Reason for stopping the bot
    
    Returns:
        JsonResponse: Bot status with number of sessions ended
    """
    try:
        # Get the single trading account (creates if doesn't exist)
        account: PaperTradingAccount = get_single_trading_account()
        user = account.user  # Get user from account for task call
        
        # Find active sessions for this user
        active_sessions = PaperTradingSession.objects.filter(
            account=account,
            status__in=['STARTING', 'RUNNING', 'PAUSED']
        )
        
        sessions_ended = 0
        tasks_stopped: List[Dict[str, str]] = []
        
        if active_sessions.count() == 0:
            return JsonResponse({
                'success': False,
                'error': 'No active bot session found',
                'sessions_ended': 0
            }, status=400)
        
        # Parse request body for stop reason
        stop_reason = "User requested stop"
        if request.body:
            try:
                body_data = json.loads(request.body)
                stop_reason = body_data.get('reason', stop_reason)
            except json.JSONDecodeError:
                pass
        
        # Stop each active session via Celery
        for session in active_sessions:
            # FIXED: Call stop task - now properly typed
            task_result = stop_paper_trading_bot.delay(
                session_id=str(session.session_id),
                user_id=user.pk,  # FIXED: Use pk instead of id for Pylance compatibility
                reason=stop_reason
            )
            
            tasks_stopped.append({
                'session_id': str(session.session_id),
                'task_id': task_result.id
            })
            
            sessions_ended += 1
            
            logger.info(
                f"Stopping paper trading session {session.session_id} with task {task_result.id}"
            )
        
        return JsonResponse({
            'success': True,
            'sessions_ended': sessions_ended,
            'tasks_stopped': tasks_stopped,
            'message': f'Stopped {sessions_ended} paper trading bot session(s)',
            'status': 'stopped'
        })
        
    except Exception as e:
        logger.error(f"Error stopping bot: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_bot_status(request: HttpRequest) -> JsonResponse:
    """
    Get paper trading bot status.
    
    Returns current bot status with session information.
    
    Returns:
        JsonResponse: Bot status and metrics
    """
    try:
        # Get the single trading account (creates if doesn't exist)
        account: PaperTradingAccount = get_single_trading_account()
        
        # Find active sessions
        active_sessions = PaperTradingSession.objects.filter(
            account=account,
            status__in=['STARTING', 'RUNNING', 'PAUSED']
        ).order_by('-started_at')
        
        # Get recent completed sessions
        recent_sessions = PaperTradingSession.objects.filter(
            account=account,
            status__in=['COMPLETED', 'STOPPED']
        ).order_by('-stopped_at')[:5]
        
        # Build response
        sessions_data: List[Dict[str, Any]] = []
        for session in active_sessions:
            # Get starting balance from metadata (stored during session creation)
            starting_balance = Decimal(str(session.metadata.get('starting_balance_usd', account.initial_balance_usd)))
            session_name = session.metadata.get('session_name', f'Session {str(session.session_id)[:8]}')
            
            session_data: Dict[str, Any] = {
                'session_id': str(session.session_id),
                'status': session.status,
                'name': session_name,
                'started_at': session.started_at.isoformat() if session.started_at else None,
                'current_pnl': float(account.current_balance_usd - starting_balance),
                'trades_executed': session.total_trades or 0
            }
            
            # Add Celery task status if available
            if session.metadata and 'celery_task_id' in session.metadata:
                from celery.result import AsyncResult
                task_id = session.metadata['celery_task_id']
                task_result = AsyncResult(task_id)
                session_data['task_status'] = task_result.status
                session_data['task_id'] = task_id
            
            sessions_data.append(session_data)
        
        # Add recent sessions summary
        recent_data: List[Dict[str, Any]] = []
        for session in recent_sessions:
            session_name = session.metadata.get('session_name', f'Session {str(session.session_id)[:8]}')
            # Calculate final P&L if we have starting balance stored
            starting_balance = Decimal(str(session.metadata.get('starting_balance_usd', 0)))
            # Note: We don't have ending balance, so P&L calculation would need to be done differently
            
            recent_data.append({
                'session_id': str(session.session_id),
                'name': session_name,
                'stopped_at': session.stopped_at.isoformat() if session.stopped_at else None,
                'final_pnl': 0.0,  # Would need ending_balance_usd field to calculate accurately
                'trades': session.total_trades or 0
            })
        
        logger.debug("Bot status fetched")
        
        return JsonResponse({
            'success': True,
            'account_balance': float(account.current_balance_usd),
            'active_sessions': sessions_data,
            'recent_sessions': recent_data,
            'bot_running': len(sessions_data) > 0
        })
        
    except Exception as e:
        logger.error(f"Error getting bot status: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)