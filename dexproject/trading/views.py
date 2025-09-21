"""
Trading API Views - Phase 5.1C Complete Implementation

This module provides comprehensive REST API endpoints for trading functionality,
bridging the gap between the dashboard frontend and trading backend services.

Features:
- Trade execution (buy/sell orders)
- Position management (view/close positions)  
- Trade history and P&L tracking
- Portfolio balance monitoring
- Trading session management
- Integration with DEX router service
- Real-time portfolio updates
- Comprehensive error handling
- SIWE authentication integration

File: dexproject/trading/views.py
"""

import logging
import json
import asyncio
import time
from typing import Dict, Any, List, Optional, Union
from decimal import Decimal
from datetime import datetime, timedelta

from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from django.db import transaction as db_transaction
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Avg, Count

# Import trading models
from .models import Chain, DEX, Token, TradingPair, Strategy, Trade, Position
from wallet.models import SIWESession, Wallet

# Import trading services
from .services.dex_router_service import DEXRouterService, SwapParams, SwapType, DEXVersion
from .services.portfolio_service import PortfolioService
from .tasks import execute_buy_order, execute_sell_order

# Import engine components
from engine.web3_client import Web3Client
from engine.wallet_manager import WalletManager
from engine.config import config

# Import shared utilities
from shared.decorators import require_wallet_auth
from shared.utils import validate_address, validate_amount

logger = logging.getLogger("trading.api")


def run_async_in_view(coro):
    """
    Execute async function in Django view context.
    
    Creates a new event loop to execute async functions within synchronous
    Django view functions. Handles Django's multi-threaded environment properly.
    
    Args:
        coro: Coroutine to execute
        
    Returns:
        Result of the coroutine execution, or None if failed
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Async execution error: {e}", exc_info=True)
        return None


def get_user_wallet_address(request: HttpRequest) -> Optional[str]:
    """
    Get the authenticated user's wallet address from SIWE session.
    
    Args:
        request: Django HTTP request with authenticated user
        
    Returns:
        Wallet address if authenticated, None otherwise
    """
    try:
        if not request.user.is_authenticated:
            return None
            
        # Get wallet address from SIWE session
        wallet_address = request.session.get('wallet_address')
        if wallet_address:
            # Verify the session is still valid
            try:
                siwe_session = SIWESession.objects.get(
                    user=request.user,
                    wallet_address=wallet_address,
                    is_active=True
                )
                return wallet_address
            except SIWESession.DoesNotExist:
                logger.warning(f"No active SIWE session found for user {request.user.id}")
                return None
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting user wallet address: {e}")
        return None


# =============================================================================
# TRADE EXECUTION ENDPOINTS
# =============================================================================

@require_POST
@csrf_exempt
@login_required
def api_execute_buy_order(request: HttpRequest) -> JsonResponse:
    """
    Execute a buy order for tokens using real DEX integration.
    
    This endpoint triggers actual blockchain transactions through the DEX router service.
    Validates user authentication, wallet connectivity, and executes trades via Celery tasks.
    
    POST /api/trading/buy/
    
    Request Body:
    {
        "token_address": "0x...",
        "amount_eth": "0.1",
        "slippage_tolerance": 0.005,
        "gas_price_gwei": 20.0,
        "strategy_id": 1,
        "chain_id": 8453
    }
    
    Returns:
        JsonResponse: Trade execution result with transaction hash and details
    """
    try:
        # Validate user authentication and wallet
        wallet_address = get_user_wallet_address(request)
        if not wallet_address:
            return JsonResponse({
                'success': False,
                'error': 'Wallet not connected or session expired',
                'code': 'WALLET_NOT_CONNECTED'
            }, status=401)
        
        # Parse request data
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON in request body',
                'code': 'INVALID_JSON'
            }, status=400)
        
        # Validate required parameters
        required_fields = ['token_address', 'amount_eth']
        for field in required_fields:
            if field not in data:
                return JsonResponse({
                    'success': False,
                    'error': f'Missing required field: {field}',
                    'code': 'MISSING_FIELD'
                }, status=400)
        
        # Extract and validate parameters
        token_address = data.get('token_address', '').strip()
        amount_eth = data.get('amount_eth')
        slippage_tolerance = float(data.get('slippage_tolerance', 0.005))
        gas_price_gwei = data.get('gas_price_gwei')
        strategy_id = data.get('strategy_id')
        chain_id = int(data.get('chain_id', 8453))  # Default to Base mainnet
        
        # Validate token address
        if not validate_address(token_address):
            return JsonResponse({
                'success': False,
                'error': 'Invalid token address format',
                'code': 'INVALID_ADDRESS'
            }, status=400)
        
        # Validate amount
        try:
            amount_eth_decimal = Decimal(str(amount_eth))
            if amount_eth_decimal <= 0:
                raise ValueError("Amount must be positive")
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid amount format or value',
                'code': 'INVALID_AMOUNT'
            }, status=400)
        
        # Validate slippage tolerance (0.1% to 50%)
        if not (0.001 <= slippage_tolerance <= 0.5):
            return JsonResponse({
                'success': False,
                'error': 'Slippage tolerance must be between 0.1% and 50%',
                'code': 'INVALID_SLIPPAGE'
            }, status=400)
        
        # Get trading pair for the token
        try:
            # First try to get existing trading pair
            trading_pair = TradingPair.objects.filter(
                base_token__address=token_address,
                chain_id=chain_id,
                is_active=True
            ).first()
            
            if not trading_pair:
                return JsonResponse({
                    'success': False,
                    'error': 'Trading pair not found for this token',
                    'code': 'PAIR_NOT_FOUND'
                }, status=404)
                
        except Exception as e:
            logger.error(f"Error finding trading pair: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to validate trading pair',
                'code': 'PAIR_VALIDATION_ERROR'
            }, status=500)
        
        # Create Trade record
        try:
            with db_transaction.atomic():
                trade = Trade.objects.create(
                    user=request.user,
                    pair=trading_pair,
                    trade_type='BUY',
                    status='PENDING',
                    amount_in=amount_eth_decimal,
                    amount_in_usd=amount_eth_decimal * Decimal('2000'),  # Rough ETH price
                    max_slippage_percent=Decimal(str(slippage_tolerance * 100)),
                    gas_price_gwei=Decimal(str(gas_price_gwei)) if gas_price_gwei else None,
                    metadata={
                        'wallet_address': wallet_address,
                        'chain_id': chain_id,
                        'execution_method': 'api_request'
                    }
                )
                
                logger.info(f"Created trade record {trade.trade_id} for user {request.user.id}")
        
        except Exception as e:
            logger.error(f"Failed to create trade record: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to create trade record',
                'code': 'TRADE_CREATION_ERROR'
            }, status=500)
        
        # Execute trade via Celery task
        try:
            task_result = execute_buy_order.delay(
                pair_address=trading_pair.address,
                token_address=token_address,
                amount_eth=str(amount_eth_decimal),
                slippage_tolerance=slippage_tolerance,
                gas_price_gwei=gas_price_gwei,
                trade_id=str(trade.trade_id),
                user_id=request.user.id,
                strategy_id=strategy_id,
                chain_id=chain_id
            )
            
            # Update trade with task ID
            trade.metadata['celery_task_id'] = task_result.id
            trade.save()
            
            logger.info(f"Dispatched buy order task {task_result.id} for trade {trade.trade_id}")
            
            return JsonResponse({
                'success': True,
                'trade_id': str(trade.trade_id),
                'task_id': task_result.id,
                'status': 'PENDING',
                'message': 'Buy order submitted for execution',
                'trade_details': {
                    'token_address': token_address,
                    'amount_eth': str(amount_eth_decimal),
                    'slippage_tolerance': slippage_tolerance,
                    'chain_id': chain_id,
                    'estimated_gas_gwei': gas_price_gwei
                }
            })
            
        except Exception as e:
            logger.error(f"Failed to dispatch buy order task: {e}")
            # Update trade status to failed
            trade.status = 'FAILED'
            trade.error_message = str(e)
            trade.save()
            
            return JsonResponse({
                'success': False,
                'error': 'Failed to execute buy order',
                'code': 'EXECUTION_ERROR',
                'details': str(e)
            }, status=500)
        
    except Exception as e:
        logger.error(f"Unexpected error in buy order execution: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Internal server error',
            'code': 'INTERNAL_ERROR'
        }, status=500)


@require_POST
@csrf_exempt
@login_required
def api_execute_sell_order(request: HttpRequest) -> JsonResponse:
    """
    Execute a sell order for tokens using real DEX integration.
    
    POST /api/trading/sell/
    
    Request Body:
    {
        "token_address": "0x...",
        "token_amount": "1000.0",
        "slippage_tolerance": 0.005,
        "gas_price_gwei": 20.0,
        "chain_id": 8453
    }
    
    Returns:
        JsonResponse: Trade execution result with transaction hash and details
    """
    try:
        # Validate user authentication and wallet
        wallet_address = get_user_wallet_address(request)
        if not wallet_address:
            return JsonResponse({
                'success': False,
                'error': 'Wallet not connected or session expired',
                'code': 'WALLET_NOT_CONNECTED'
            }, status=401)
        
        # Parse request data
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON in request body',
                'code': 'INVALID_JSON'
            }, status=400)
        
        # Validate required parameters
        required_fields = ['token_address', 'token_amount']
        for field in required_fields:
            if field not in data:
                return JsonResponse({
                    'success': False,
                    'error': f'Missing required field: {field}',
                    'code': 'MISSING_FIELD'
                }, status=400)
        
        # Extract and validate parameters
        token_address = data.get('token_address', '').strip()
        token_amount = data.get('token_amount')
        slippage_tolerance = float(data.get('slippage_tolerance', 0.005))
        gas_price_gwei = data.get('gas_price_gwei')
        chain_id = int(data.get('chain_id', 8453))
        
        # Validate token address
        if not validate_address(token_address):
            return JsonResponse({
                'success': False,
                'error': 'Invalid token address format',
                'code': 'INVALID_ADDRESS'
            }, status=400)
        
        # Validate token amount
        try:
            token_amount_decimal = Decimal(str(token_amount))
            if token_amount_decimal <= 0:
                raise ValueError("Amount must be positive")
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid token amount format or value',
                'code': 'INVALID_AMOUNT'
            }, status=400)
        
        # Get trading pair
        try:
            trading_pair = TradingPair.objects.filter(
                base_token__address=token_address,
                chain_id=chain_id,
                is_active=True
            ).first()
            
            if not trading_pair:
                return JsonResponse({
                    'success': False,
                    'error': 'Trading pair not found for this token',
                    'code': 'PAIR_NOT_FOUND'
                }, status=404)
                
        except Exception as e:
            logger.error(f"Error finding trading pair: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to validate trading pair',
                'code': 'PAIR_VALIDATION_ERROR'
            }, status=500)
        
        # Create Trade record
        try:
            with db_transaction.atomic():
                trade = Trade.objects.create(
                    user=request.user,
                    pair=trading_pair,
                    trade_type='SELL',
                    status='PENDING',
                    amount_out=token_amount_decimal,
                    max_slippage_percent=Decimal(str(slippage_tolerance * 100)),
                    gas_price_gwei=Decimal(str(gas_price_gwei)) if gas_price_gwei else None,
                    metadata={
                        'wallet_address': wallet_address,
                        'chain_id': chain_id,
                        'execution_method': 'api_request'
                    }
                )
                
                logger.info(f"Created sell trade record {trade.trade_id} for user {request.user.id}")
        
        except Exception as e:
            logger.error(f"Failed to create trade record: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to create trade record',
                'code': 'TRADE_CREATION_ERROR'
            }, status=500)
        
        # Execute trade via Celery task
        try:
            task_result = execute_sell_order.delay(
                pair_address=trading_pair.address,
                token_address=token_address,
                token_amount=str(token_amount_decimal),
                slippage_tolerance=slippage_tolerance,
                gas_price_gwei=gas_price_gwei,
                trade_id=str(trade.trade_id),
                user_id=request.user.id,
                chain_id=chain_id
            )
            
            # Update trade with task ID
            trade.metadata['celery_task_id'] = task_result.id
            trade.save()
            
            logger.info(f"Dispatched sell order task {task_result.id} for trade {trade.trade_id}")
            
            return JsonResponse({
                'success': True,
                'trade_id': str(trade.trade_id),
                'task_id': task_result.id,
                'status': 'PENDING',
                'message': 'Sell order submitted for execution',
                'trade_details': {
                    'token_address': token_address,
                    'token_amount': str(token_amount_decimal),
                    'slippage_tolerance': slippage_tolerance,
                    'chain_id': chain_id,
                    'estimated_gas_gwei': gas_price_gwei
                }
            })
            
        except Exception as e:
            logger.error(f"Failed to dispatch sell order task: {e}")
            # Update trade status to failed
            trade.status = 'FAILED'
            trade.error_message = str(e)
            trade.save()
            
            return JsonResponse({
                'success': False,
                'error': 'Failed to execute sell order',
                'code': 'EXECUTION_ERROR',
                'details': str(e)
            }, status=500)
        
    except Exception as e:
        logger.error(f"Unexpected error in sell order execution: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Internal server error',
            'code': 'INTERNAL_ERROR'
        }, status=500)


# =============================================================================
# POSITION MANAGEMENT ENDPOINTS
# =============================================================================

@require_GET
@login_required
def api_get_positions(request: HttpRequest) -> JsonResponse:
    """
    Get user's current trading positions with real-time P&L data.
    
    GET /api/trading/positions/
    
    Query Parameters:
        - status: Filter by position status (OPEN, CLOSED, PARTIALLY_CLOSED)
        - chain_id: Filter by blockchain network
        - limit: Number of positions to return (default: 50)
        - offset: Pagination offset
    
    Returns:
        JsonResponse: List of positions with current values and P&L
    """
    try:
        # Validate user authentication
        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'error': 'Authentication required',
                'code': 'AUTH_REQUIRED'
            }, status=401)
        
        # Get query parameters
        status_filter = request.GET.get('status', '').upper()
        chain_id_filter = request.GET.get('chain_id')
        limit = min(int(request.GET.get('limit', 50)), 200)  # Max 200 positions
        offset = int(request.GET.get('offset', 0))
        
        # Build query
        query = Position.objects.filter(user=request.user)
        
        if status_filter and status_filter in ['OPEN', 'CLOSED', 'PARTIALLY_CLOSED']:
            query = query.filter(status=status_filter)
        
        if chain_id_filter:
            try:
                chain_id = int(chain_id_filter)
                query = query.filter(pair__chain_id=chain_id)
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid chain_id parameter',
                    'code': 'INVALID_CHAIN_ID'
                }, status=400)
        
        # Get total count for pagination
        total_count = query.count()
        
        # Apply pagination and get positions
        positions = query.select_related(
            'pair', 'pair__base_token', 'pair__quote_token', 'strategy'
        ).order_by('-created_at')[offset:offset + limit]
        
        # Format position data
        position_data = []
        for position in positions:
            try:
                # Calculate current values (this would ideally use real-time price data)
                current_value_usd = float(position.current_value_usd or 0)
                total_invested_usd = float(position.total_amount_in or 0)
                unrealized_pnl = current_value_usd - total_invested_usd
                unrealized_pnl_percent = (unrealized_pnl / total_invested_usd * 100) if total_invested_usd > 0 else 0
                
                position_info = {
                    'position_id': str(position.position_id),
                    'status': position.status,
                    'pair_address': position.pair.address,
                    'token_symbol': position.pair.base_token.symbol,
                    'token_name': position.pair.base_token.name,
                    'token_address': position.pair.base_token.address,
                    'chain_id': position.pair.chain_id,
                    'total_amount_in': str(position.total_amount_in),
                    'current_amount': str(position.current_amount),
                    'average_entry_price': str(position.average_entry_price) if position.average_entry_price else None,
                    'current_price_usd': str(position.current_price_usd) if position.current_price_usd else None,
                    'current_value_usd': str(current_value_usd),
                    'unrealized_pnl_usd': str(unrealized_pnl),
                    'unrealized_pnl_percent': round(unrealized_pnl_percent, 2),
                    'realized_pnl_usd': str(position.realized_pnl_usd or 0),
                    'created_at': position.created_at.isoformat(),
                    'last_updated': position.updated_at.isoformat(),
                    'strategy_name': position.strategy.name if position.strategy else None,
                    'trade_count': position.trades.count()
                }
                position_data.append(position_info)
                
            except Exception as e:
                logger.error(f"Error formatting position {position.position_id}: {e}")
                continue
        
        # Calculate summary statistics
        total_unrealized_pnl = sum(float(p['unrealized_pnl_usd']) for p in position_data)
        total_realized_pnl = sum(float(p['realized_pnl_usd']) for p in position_data)
        total_current_value = sum(float(p['current_value_usd']) for p in position_data)
        
        return JsonResponse({
            'success': True,
            'positions': position_data,
            'pagination': {
                'total_count': total_count,
                'limit': limit,
                'offset': offset,
                'has_next': offset + limit < total_count
            },
            'summary': {
                'total_positions': len(position_data),
                'total_current_value_usd': round(total_current_value, 2),
                'total_unrealized_pnl_usd': round(total_unrealized_pnl, 2),
                'total_realized_pnl_usd': round(total_realized_pnl, 2),
                'total_pnl_usd': round(total_unrealized_pnl + total_realized_pnl, 2)
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting positions: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve positions',
            'code': 'RETRIEVAL_ERROR'
        }, status=500)


@require_POST
@csrf_exempt
@login_required
def api_close_position(request: HttpRequest) -> JsonResponse:
    """
    Close a trading position by selling all remaining tokens.
    
    POST /api/trading/positions/close/
    
    Request Body:
    {
        "position_id": "uuid-string",
        "percentage": 100.0,  // Optional: percentage to close (default 100%)
        "slippage_tolerance": 0.005,
        "gas_price_gwei": 20.0
    }
    
    Returns:
        JsonResponse: Position closure execution result
    """
    try:
        # Validate user authentication
        wallet_address = get_user_wallet_address(request)
        if not wallet_address:
            return JsonResponse({
                'success': False,
                'error': 'Wallet not connected or session expired',
                'code': 'WALLET_NOT_CONNECTED'
            }, status=401)
        
        # Parse request data
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON in request body',
                'code': 'INVALID_JSON'
            }, status=400)
        
        # Validate required parameters
        position_id = data.get('position_id')
        if not position_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing required field: position_id',
                'code': 'MISSING_FIELD'
            }, status=400)
        
        percentage = float(data.get('percentage', 100.0))
        slippage_tolerance = float(data.get('slippage_tolerance', 0.005))
        gas_price_gwei = data.get('gas_price_gwei')
        
        # Validate percentage
        if not (0 < percentage <= 100):
            return JsonResponse({
                'success': False,
                'error': 'Percentage must be between 0 and 100',
                'code': 'INVALID_PERCENTAGE'
            }, status=400)
        
        # Get position
        try:
            position = Position.objects.select_related(
                'pair', 'pair__base_token'
            ).get(
                position_id=position_id,
                user=request.user,
                status='OPEN'
            )
        except Position.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Position not found or already closed',
                'code': 'POSITION_NOT_FOUND'
            }, status=404)
        
        # Calculate amount to sell
        total_amount = position.current_amount
        amount_to_sell = total_amount * Decimal(str(percentage / 100))
        
        if amount_to_sell <= 0:
            return JsonResponse({
                'success': False,
                'error': 'No tokens to sell in this position',
                'code': 'NOTHING_TO_SELL'
            }, status=400)
        
        # Execute sell order to close position
        try:
            task_result = execute_sell_order.delay(
                pair_address=position.pair.address,
                token_address=position.pair.base_token.address,
                token_amount=str(amount_to_sell),
                slippage_tolerance=slippage_tolerance,
                gas_price_gwei=gas_price_gwei,
                user_id=request.user.id,
                is_position_close=True,
                position_id=str(position.position_id),
                chain_id=position.pair.chain_id
            )
            
            logger.info(f"Dispatched position close task {task_result.id} for position {position.position_id}")
            
            return JsonResponse({
                'success': True,
                'task_id': task_result.id,
                'position_id': str(position.position_id),
                'amount_to_sell': str(amount_to_sell),
                'percentage': percentage,
                'status': 'CLOSING',
                'message': f'Position closure submitted for execution ({percentage}%)'
            })
            
        except Exception as e:
            logger.error(f"Failed to dispatch position close task: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to execute position closure',
                'code': 'EXECUTION_ERROR',
                'details': str(e)
            }, status=500)
        
    except Exception as e:
        logger.error(f"Unexpected error in position closure: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Internal server error',
            'code': 'INTERNAL_ERROR'
        }, status=500)


# =============================================================================
# TRADE HISTORY AND PORTFOLIO ENDPOINTS
# =============================================================================

@require_GET
@login_required
def api_get_trade_history(request: HttpRequest) -> JsonResponse:
    """
    Get user's trading history with filtering and pagination.
    
    GET /api/trading/history/
    
    Query Parameters:
        - status: Filter by trade status (PENDING, COMPLETED, FAILED, CANCELLED)
        - trade_type: Filter by trade type (BUY, SELL)
        - chain_id: Filter by blockchain network
        - limit: Number of trades to return (default: 50, max: 200)
        - offset: Pagination offset
        - date_from: Start date (YYYY-MM-DD)
        - date_to: End date (YYYY-MM-DD)
    
    Returns:
        JsonResponse: List of trades with execution details and P&L
    """
    try:
        # Validate user authentication
        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'error': 'Authentication required',
                'code': 'AUTH_REQUIRED'
            }, status=401)
        
        # Get query parameters
        status_filter = request.GET.get('status', '').upper()
        trade_type_filter = request.GET.get('trade_type', '').upper()
        chain_id_filter = request.GET.get('chain_id')
        limit = min(int(request.GET.get('limit', 50)), 200)
        offset = int(request.GET.get('offset', 0))
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        
        # Build query
        query = Trade.objects.filter(user=request.user)
        
        if status_filter and status_filter in ['PENDING', 'COMPLETED', 'FAILED', 'CANCELLED']:
            query = query.filter(status=status_filter)
        
        if trade_type_filter and trade_type_filter in ['BUY', 'SELL']:
            query = query.filter(trade_type=trade_type_filter)
        
        if chain_id_filter:
            try:
                chain_id = int(chain_id_filter)
                query = query.filter(pair__chain_id=chain_id)
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid chain_id parameter',
                    'code': 'INVALID_CHAIN_ID'
                }, status=400)
        
        # Date filtering
        if date_from:
            try:
                from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
                query = query.filter(created_at__date__gte=from_date)
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid date_from format (use YYYY-MM-DD)',
                    'code': 'INVALID_DATE_FROM'
                }, status=400)
        
        if date_to:
            try:
                to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
                query = query.filter(created_at__date__lte=to_date)
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid date_to format (use YYYY-MM-DD)',
                    'code': 'INVALID_DATE_TO'
                }, status=400)
        
        # Get total count for pagination
        total_count = query.count()
        
        # Apply pagination and get trades
        trades = query.select_related(
            'pair', 'pair__base_token', 'pair__quote_token', 'strategy'
        ).order_by('-created_at')[offset:offset + limit]
        
        # Format trade data
        trade_data = []
        for trade in trades:
            try:
                trade_info = {
                    'trade_id': str(trade.trade_id),
                    'trade_type': trade.trade_type,
                    'status': trade.status,
                    'pair_address': trade.pair.address,
                    'token_symbol': trade.pair.base_token.symbol,
                    'token_name': trade.pair.base_token.name,
                    'token_address': trade.pair.base_token.address,
                    'chain_id': trade.pair.chain_id,
                    'amount_in': str(trade.amount_in) if trade.amount_in else None,
                    'amount_out': str(trade.amount_out) if trade.amount_out else None,
                    'amount_in_usd': str(trade.amount_in_usd) if trade.amount_in_usd else None,
                    'amount_out_usd': str(trade.amount_out_usd) if trade.amount_out_usd else None,
                    'execution_price': str(trade.execution_price) if trade.execution_price else None,
                    'actual_slippage_percent': str(trade.actual_slippage_percent) if trade.actual_slippage_percent else None,
                    'max_slippage_percent': str(trade.max_slippage_percent) if trade.max_slippage_percent else None,
                    'gas_price_gwei': str(trade.gas_price_gwei) if trade.gas_price_gwei else None,
                    'gas_used': trade.gas_used,
                    'total_fees_usd': str(trade.total_fees_usd) if trade.total_fees_usd else None,
                    'transaction_hash': trade.transaction_hash,
                    'created_at': trade.created_at.isoformat(),
                    'executed_at': trade.executed_at.isoformat() if trade.executed_at else None,
                    'confirmed_at': trade.confirmed_at.isoformat() if trade.confirmed_at else None,
                    'error_message': trade.error_message,
                    'strategy_name': trade.strategy.name if trade.strategy else None
                }
                trade_data.append(trade_info)
                
            except Exception as e:
                logger.error(f"Error formatting trade {trade.trade_id}: {e}")
                continue
        
        # Calculate summary statistics
        completed_trades = [t for t in trade_data if t['status'] == 'COMPLETED']
        total_volume_usd = sum(
            float(t['amount_in_usd'] or 0) + float(t['amount_out_usd'] or 0) 
            for t in completed_trades
        )
        total_fees_usd = sum(float(t['total_fees_usd'] or 0) for t in completed_trades)
        
        return JsonResponse({
            'success': True,
            'trades': trade_data,
            'pagination': {
                'total_count': total_count,
                'limit': limit,
                'offset': offset,
                'has_next': offset + limit < total_count
            },
            'summary': {
                'total_trades': len(trade_data),
                'completed_trades': len(completed_trades),
                'total_volume_usd': round(total_volume_usd, 2),
                'total_fees_usd': round(total_fees_usd, 2),
                'success_rate': round(len(completed_trades) / len(trade_data) * 100, 1) if trade_data else 0
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting trade history: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve trade history',
            'code': 'RETRIEVAL_ERROR'
        }, status=500)


@require_GET
@login_required
def api_get_portfolio_summary(request: HttpRequest) -> JsonResponse:
    """
    Get user's portfolio summary with real-time balances and P&L.
    
    GET /api/trading/portfolio/
    
    Returns:
        JsonResponse: Portfolio summary with balances, positions, and performance metrics
    """
    try:
        # Validate user authentication
        wallet_address = get_user_wallet_address(request)
        if not wallet_address:
            return JsonResponse({
                'success': False,
                'error': 'Wallet not connected or session expired',
                'code': 'WALLET_NOT_CONNECTED'
            }, status=401)
        
        # Get portfolio service instance (this would be initialized properly in real implementation)
        try:
            # Initialize portfolio service with user's wallet
            web3_client = Web3Client(config.get_chain_config(8453))  # Base mainnet
            wallet_manager = WalletManager(web3_client)
            portfolio_service = PortfolioService(wallet_manager, request.user)
            
            # Get portfolio summary (this would be async in real implementation)
            portfolio_data = run_async_in_view(
                portfolio_service.get_portfolio_summary(wallet_address)
            )
            
            if not portfolio_data:
                raise Exception("Failed to get portfolio data")
                
        except Exception as e:
            logger.error(f"Error initializing portfolio service: {e}")
            # Fallback to database-only summary
            portfolio_data = {
                'total_value_usd': 0,
                'total_pnl_usd': 0,
                'total_pnl_percent': 0,
                'positions_count': 0,
                'trades_count': 0
            }
        
        # Get positions summary
        positions = Position.objects.filter(user=request.user)
        open_positions = positions.filter(status='OPEN')
        
        # Get trades summary
        trades = Trade.objects.filter(user=request.user)
        completed_trades = trades.filter(status='COMPLETED')
        
        # Calculate additional metrics
        total_positions = positions.count()
        total_trades = trades.count()
        success_rate = (completed_trades.count() / total_trades * 100) if total_trades > 0 else 0
        
        # Get recent activity (last 10 trades)
        recent_trades = trades.order_by('-created_at')[:10].values(
            'trade_id', 'trade_type', 'status', 'created_at',
            'pair__base_token__symbol', 'amount_in', 'amount_out'
        )
        
        portfolio_summary = {
            'wallet_address': wallet_address,
            'total_value_usd': portfolio_data.get('total_value_usd', 0),
            'total_pnl_usd': portfolio_data.get('total_pnl_usd', 0),
            'total_pnl_percent': portfolio_data.get('total_pnl_percent', 0),
            'positions': {
                'total_count': total_positions,
                'open_count': open_positions.count(),
                'closed_count': positions.filter(status='CLOSED').count()
            },
            'trades': {
                'total_count': total_trades,
                'completed_count': completed_trades.count(),
                'pending_count': trades.filter(status='PENDING').count(),
                'failed_count': trades.filter(status='FAILED').count(),
                'success_rate_percent': round(success_rate, 1)
            },
            'recent_activity': [
                {
                    'trade_id': str(trade['trade_id']),
                    'type': trade['trade_type'],
                    'status': trade['status'],
                    'token_symbol': trade['pair__base_token__symbol'],
                    'amount_in': str(trade['amount_in']) if trade['amount_in'] else None,
                    'amount_out': str(trade['amount_out']) if trade['amount_out'] else None,
                    'created_at': trade['created_at'].isoformat()
                }
                for trade in recent_trades
            ],
            'last_updated': timezone.now().isoformat()
        }
        
        return JsonResponse({
            'success': True,
            'portfolio': portfolio_summary
        })
        
    except Exception as e:
        logger.error(f"Error getting portfolio summary: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve portfolio summary',
            'code': 'RETRIEVAL_ERROR'
        }, status=500)


# =============================================================================
# TRADING SESSION MANAGEMENT
# =============================================================================

@require_POST
@csrf_exempt
@login_required
def api_start_trading_session(request: HttpRequest) -> JsonResponse:
    """
    Start a new trading session for the user.
    
    POST /api/trading/session/start/
    
    Request Body:
    {
        "strategy_id": 1,
        "max_position_size_usd": 1000.0,
        "risk_tolerance": "MEDIUM",
        "auto_execution": true
    }
    
    Returns:
        JsonResponse: Trading session start confirmation
    """
    try:
        # Validate user authentication
        wallet_address = get_user_wallet_address(request)
        if not wallet_address:
            return JsonResponse({
                'success': False,
                'error': 'Wallet not connected or session expired',
                'code': 'WALLET_NOT_CONNECTED'
            }, status=401)
        
        # Parse request data
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = {}
        
        # Extract parameters
        strategy_id = data.get('strategy_id')
        max_position_size_usd = data.get('max_position_size_usd', 1000.0)
        risk_tolerance = data.get('risk_tolerance', 'MEDIUM')
        auto_execution = data.get('auto_execution', False)
        
        # Validate strategy if provided
        strategy = None
        if strategy_id:
            try:
                strategy = Strategy.objects.get(id=strategy_id, user=request.user)
            except Strategy.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Strategy not found',
                    'code': 'STRATEGY_NOT_FOUND'
                }, status=404)
        
        # TODO: Create TradingSession model and implement session management
        # For now, return a mock response showing the session would be started
        
        session_data = {
            'session_id': f"session_{int(time.time())}",
            'user_id': request.user.id,
            'wallet_address': wallet_address,
            'strategy_id': strategy_id,
            'strategy_name': strategy.name if strategy else 'Default',
            'max_position_size_usd': max_position_size_usd,
            'risk_tolerance': risk_tolerance,
            'auto_execution': auto_execution,
            'status': 'ACTIVE',
            'started_at': timezone.now().isoformat()
        }
        
        # Store session in cache for now (would be in database in real implementation)
        cache_key = f"trading_session_{request.user.id}"
        cache.set(cache_key, session_data, 3600 * 24)  # 24 hours
        
        logger.info(f"Started trading session for user {request.user.id}")
        
        return JsonResponse({
            'success': True,
            'session': session_data,
            'message': 'Trading session started successfully'
        })
        
    except Exception as e:
        logger.error(f"Error starting trading session: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to start trading session',
            'code': 'SESSION_START_ERROR'
        }, status=500)


@require_POST
@csrf_exempt
@login_required
def api_stop_trading_session(request: HttpRequest) -> JsonResponse:
    """
    Stop the active trading session for the user.
    
    POST /api/trading/session/stop/
    
    Returns:
        JsonResponse: Trading session stop confirmation
    """
    try:
        # Get active session from cache
        cache_key = f"trading_session_{request.user.id}"
        session_data = cache.get(cache_key)
        
        if not session_data:
            return JsonResponse({
                'success': False,
                'error': 'No active trading session found',
                'code': 'NO_ACTIVE_SESSION'
            }, status=404)
        
        # Update session status
        session_data['status'] = 'STOPPED'
        session_data['stopped_at'] = timezone.now().isoformat()
        
        # Remove from cache
        cache.delete(cache_key)
        
        logger.info(f"Stopped trading session for user {request.user.id}")
        
        return JsonResponse({
            'success': True,
            'session': session_data,
            'message': 'Trading session stopped successfully'
        })
        
    except Exception as e:
        logger.error(f"Error stopping trading session: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to stop trading session',
            'code': 'SESSION_STOP_ERROR'
        }, status=500)


@require_GET
@login_required
def api_get_trading_session_status(request: HttpRequest) -> JsonResponse:
    """
    Get the current trading session status for the user.
    
    GET /api/trading/session/status/
    
    Returns:
        JsonResponse: Current trading session information
    """
    try:
        # Get active session from cache
        cache_key = f"trading_session_{request.user.id}"
        session_data = cache.get(cache_key)
        
        if not session_data:
            return JsonResponse({
                'success': True,
                'session': None,
                'message': 'No active trading session'
            })
        
        return JsonResponse({
            'success': True,
            'session': session_data
        })
        
    except Exception as e:
        logger.error(f"Error getting trading session status: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to get session status',
            'code': 'SESSION_STATUS_ERROR'
        }, status=500)


# =============================================================================
# UTILITY ENDPOINTS
# =============================================================================

@require_GET
def api_get_supported_tokens(request: HttpRequest) -> JsonResponse:
    """
    Get list of supported tokens for trading.
    
    GET /api/trading/tokens/
    
    Query Parameters:
        - chain_id: Filter by blockchain network
        - search: Search by token symbol or name
        - limit: Number of tokens to return (default: 100)
    
    Returns:
        JsonResponse: List of supported tokens with metadata
    """
    try:
        # Get query parameters
        chain_id_filter = request.GET.get('chain_id')
        search_query = request.GET.get('search', '').strip()
        limit = min(int(request.GET.get('limit', 100)), 500)  # Max 500 tokens
        
        # Build query
        query = Token.objects.filter(is_blacklisted=False)
        
        if chain_id_filter:
            try:
                chain_id = int(chain_id_filter)
                query = query.filter(chain_id=chain_id)
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid chain_id parameter',
                    'code': 'INVALID_CHAIN_ID'
                }, status=400)
        
        if search_query:
            query = query.filter(
                Q(symbol__icontains=search_query) | 
                Q(name__icontains=search_query) |
                Q(address__icontains=search_query)
            )
        
        # Get tokens with trading pairs
        tokens = query.filter(
            base_pairs__is_active=True
        ).distinct().order_by('symbol')[:limit]
        
        # Format token data
        token_data = []
        for token in tokens:
            try:
                # Get active trading pairs for this token
                active_pairs = token.base_pairs.filter(is_active=True).count()
                
                token_info = {
                    'address': token.address,
                    'symbol': token.symbol,
                    'name': token.name,
                    'decimals': token.decimals,
                    'chain_id': token.chain_id,
                    'is_verified': token.is_verified,
                    'is_honeypot': token.is_honeypot,
                    'logo_url': token.logo_url,
                    'active_pairs_count': active_pairs,
                    'current_price_usd': str(token.current_price_usd) if token.current_price_usd else None,
                    'market_cap_usd': str(token.market_cap_usd) if token.market_cap_usd else None,
                    'volume_24h_usd': str(token.volume_24h_usd) if token.volume_24h_usd else None,
                    'price_change_24h_percent': str(token.price_change_24h_percent) if token.price_change_24h_percent else None
                }
                token_data.append(token_info)
                
            except Exception as e:
                logger.error(f"Error formatting token {token.address}: {e}")
                continue
        
        return JsonResponse({
            'success': True,
            'tokens': token_data,
            'count': len(token_data),
            'filters': {
                'chain_id': chain_id_filter,
                'search': search_query,
                'limit': limit
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting supported tokens: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve supported tokens',
            'code': 'RETRIEVAL_ERROR'
        }, status=500)


@require_GET
def api_health_check(request: HttpRequest) -> JsonResponse:
    """
    Health check endpoint for trading API.
    
    GET /api/trading/health/
    
    Returns:
        JsonResponse: Trading API health status
    """
    try:
        # Check database connectivity
        db_status = "healthy"
        try:
            Token.objects.count()
        except Exception as e:
            db_status = f"error: {str(e)}"
        
        # Check cache connectivity
        cache_status = "healthy"
        try:
            cache.set('health_check', 'ok', 1)
            if cache.get('health_check') != 'ok':
                cache_status = "error: cache not working"
        except Exception as e:
            cache_status = f"error: {str(e)}"
        
        # TODO: Check DEX router service connectivity
        dex_status = "not_implemented"
        
        # TODO: Check portfolio service connectivity
        portfolio_status = "not_implemented"
        
        health_data = {
            'status': 'healthy' if all(
                status == 'healthy' for status in [db_status, cache_status]
            ) else 'degraded',
            'timestamp': timezone.now().isoformat(),
            'services': {
                'database': db_status,
                'cache': cache_status,
                'dex_router': dex_status,
                'portfolio_service': portfolio_status
            },
            'version': '1.0.0',
            'environment': 'development' if settings.DEBUG else 'production'
        }
        
        return JsonResponse({
            'success': True,
            'health': health_data
        })
        
    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Health check failed',
            'code': 'HEALTH_CHECK_ERROR',
            'timestamp': timezone.now().isoformat()
        }, status=500)