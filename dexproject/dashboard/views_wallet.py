"""
Wallet API Views for Dashboard

Provides wallet-specific API endpoints including balance tracking, transaction monitoring,
and wallet management functionality. Implements secure SIWE authentication validation.

File: dexproject/dashboard/views_wallet.py
"""

import logging
import json
import asyncio
import time
from typing import Dict, Any, List, Optional, Set
from decimal import Decimal
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from django.db import transaction as db_transaction

# Import models
from wallet.models import SIWESession, Wallet, WalletBalance
from trading.models import Token

# Import Web3 infrastructure
from engine.web3_client import Web3Client
from engine.wallet_manager import WalletManager
from engine.config import config

logger = logging.getLogger("dashboard.api.wallet")


def run_async_in_view(coro):
    """
    Execute async function in Django view context.
    
    Creates a new event loop to execute async functions within synchronous
    Django view functions. Handles Django's multi-threaded environment.
    
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


@require_http_methods(["GET"])

def api_wallet_balances(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for wallet balance tracking with real-time ETH and ERC-20 token balances.
    
    This endpoint provides real-time wallet balances using SIWE authentication validation
    and live blockchain data from Base Sepolia (default) with multi-chain support.
    
    Query Parameters:
        chain_id (int, optional): Chain ID to query balances from (default: 84532 Base Sepolia)
        tokens (str, optional): Comma-separated list of ERC-20 token addresses to include
        refresh (bool, optional): If true, bypass cache and fetch fresh data
    
    Returns:
        JsonResponse with balance data:
        {
            "success": bool,
            "address": str,
            "chain_id": int,
            "native": {"symbol": str, "decimals": int, "raw": str, "formatted": str},
            "tokens": [{"address": str, "symbol": str, "decimals": int, "raw": str, "formatted": str, "usd_value": float}],
            "updated_at": str,
            "source": str,
            "limits": {"rate_limit_remaining": int, "cache_ttl_seconds": int}
        }
    
    Error Responses:
        401: Not authenticated or invalid SIWE session
        400: Invalid parameters or SIWE/chain mismatch
        503: Wallet service unavailable
    """
    try:
        start_time = time.time()
        
        # 1. Authentication & Connection Check
        logger.debug(f"Balance API called by user: {request.user.username}")
        
        # Get active SIWE session (following existing pattern from get_user_wallet_info)
        siwe_session = SIWESession.objects.filter(
            user=request.user,
            status=SIWESession.SessionStatus.VERIFIED,
            expiration_time__gt=timezone.now()
        ).first()
        
        if not siwe_session:
            logger.warning(f"No valid SIWE session for user: {request.user.username}")
            return JsonResponse({
                'success': False,
                'error': 'No valid wallet session found',
                'error_code': 'NO_WALLET_SESSION'
            }, status=401)
        
        wallet_address = siwe_session.wallet_address
        session_chain_id = siwe_session.chain_id
        
        # 2. Input Processing (query params)
        try:
            chain_id = int(request.GET.get('chain_id', 84532))  # Default to Base Sepolia
            tokens_param = request.GET.get('tokens', '')
            refresh = request.GET.get('refresh', '').lower() in ('true', '1', 'yes')
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid query parameters: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Invalid query parameters',
                'error_code': 'INVALID_PARAMS'
            }, status=400)
        
        # Validate chain compatibility with SIWE session
        if chain_id != session_chain_id:
            logger.warning(f"Chain mismatch: session={session_chain_id}, requested={chain_id}")
            return JsonResponse({
                'success': False,
                'error': f'Chain mismatch: wallet connected to chain {session_chain_id}, requested {chain_id}',
                'error_code': 'CHAIN_MISMATCH'
            }, status=400)
        
        # Parse requested token addresses
        requested_tokens: Set[str] = set()
        if tokens_param:
            try:
                raw_tokens = [addr.strip().lower() for addr in tokens_param.split(',') if addr.strip()]
                # Validate token addresses
                for addr in raw_tokens:
                    if not addr.startswith('0x') or len(addr) != 42:
                        raise ValueError(f"Invalid token address: {addr}")
                    requested_tokens.add(addr)
            except ValueError as e:
                logger.warning(f"Invalid token addresses: {e}")
                return JsonResponse({
                    'success': False,
                    'error': str(e),
                    'error_code': 'INVALID_TOKEN_ADDRESSES'
                }, status=400)
        
        # 3. Check cache (unless refresh requested)
        cache_key = f"wallet_balances:{request.user.id}:{chain_id}:{hash(frozenset(requested_tokens))}"
        cache_ttl_seconds = 15  # 15-second cache for real-time feel
        
        if not refresh:
            cached_data = cache.get(cache_key)
            if cached_data:
                cached_data['source'] = 'CACHE'
                cached_data['limits'] = {
                    'rate_limit_remaining': 100,  # Simplified rate limiting
                    'cache_ttl_seconds': cache_ttl_seconds
                }
                logger.debug(f"Returning cached balances for {wallet_address[:10]}...")
                return JsonResponse(cached_data)
        
        # 4. Get tracked tokens from database
        tracked_tokens = _get_tracked_tokens_for_chain(chain_id, requested_tokens)
        
        # 5. Balance retrieval using existing infrastructure
        try:
            balance_data = run_async_in_view(_fetch_wallet_balances(
                wallet_address, chain_id, tracked_tokens
            ))
            
            if not balance_data:
                raise Exception("Failed to fetch balance data from blockchain")
                
        except Exception as e:
            logger.error(f"Balance retrieval failed for {wallet_address}: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Wallet service temporarily unavailable',
                'error_code': 'SERVICE_UNAVAILABLE'
            }, status=503)
        
        # 6. Update database cache if we have wallet balance records
        try:
            _update_wallet_balance_records(wallet_address, chain_id, balance_data)
        except Exception as e:
            logger.warning(f"Failed to update balance cache in database: {e}")
            # Don't fail the request if cache update fails
        
        # 7. Format response
        execution_time_ms = (time.time() - start_time) * 1000
        response_data = {
            'success': True,
            'address': wallet_address,
            'chain_id': chain_id,
            'native': balance_data['native'],
            'tokens': balance_data['tokens'],
            'updated_at': timezone.now().isoformat(),
            'source': 'LIVE',
            'limits': {
                'rate_limit_remaining': 95,  # Simplified rate limiting
                'cache_ttl_seconds': cache_ttl_seconds
            },
            'meta': {
                'execution_time_ms': round(execution_time_ms, 2),
                'tokens_requested': len(requested_tokens),
                'tokens_returned': len(balance_data['tokens'])
            }
        }
        
        # 8. Cache the response
        cache.set(cache_key, response_data, cache_ttl_seconds)
        
        logger.info(f"✅ Balance data retrieved for {wallet_address[:10]}... on chain {chain_id} ({execution_time_ms:.2f}ms)")
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Unexpected error in api_wallet_balances: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Internal server error',
            'error_code': 'INTERNAL_ERROR'
        }, status=500)


def _get_tracked_tokens_for_chain(chain_id: int, requested_tokens: Set[str]) -> List[Dict[str, Any]]:
    """
    Get tracked tokens for the specified chain using database-first approach with settings fallback.
    
    Args:
        chain_id: Chain ID to get tokens for
        requested_tokens: Set of specific token addresses requested
        
    Returns:
        List of token info dictionaries
    """
    try:
        tracked_tokens = []
        
        # If specific tokens requested, get those
        if requested_tokens:
            db_tokens = Token.objects.filter(
                chain_id=chain_id,
                address__in=[addr.lower() for addr in requested_tokens]
            ).values('address', 'symbol', 'name', 'decimals')
            
            for token in db_tokens:
                tracked_tokens.append({
                    'address': token['address'],
                    'symbol': token['symbol'] or 'UNKNOWN',
                    'name': token['name'] or 'Unknown Token',
                    'decimals': token['decimals'] or 18
                })
        else:
            # Get all tracked tokens from database (primary source)
            # Note: Since there's no is_tracked field, we'll use a different approach
            # For now, get verified tokens or tokens with symbols as "tracked"
            db_tokens = Token.objects.filter(
                chain_id=chain_id,
                is_verified=True
            ).exclude(
                symbol__isnull=True
            ).exclude(
                symbol__exact=''
            ).order_by('symbol')[:10]  # Limit to 10 tokens for performance
            
            for token in db_tokens:
                tracked_tokens.append({
                    'address': token.address,
                    'symbol': token.symbol or 'UNKNOWN',
                    'name': token.name or 'Unknown Token',
                    'decimals': token.decimals or 18
                })
            
            # Fallback to settings if no DB tokens found
            if not tracked_tokens:
                fallback_tokens = getattr(settings, 'DEFAULT_TRACKED_TOKENS', {}).get(chain_id, [])
                logger.info(f"Using fallback tokens for chain {chain_id}: {len(fallback_tokens)} tokens")
                tracked_tokens = fallback_tokens
        
        logger.debug(f"Found {len(tracked_tokens)} tracked tokens for chain {chain_id}")
        return tracked_tokens
        
    except Exception as e:
        logger.error(f"Failed to get tracked tokens for chain {chain_id}: {e}")
        return []


async def _fetch_wallet_balances(
    wallet_address: str, 
    chain_id: int, 
    tracked_tokens: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Fetch wallet balances using existing WalletManager and Web3Client infrastructure.
    
    Args:
        wallet_address: Wallet address to fetch balances for
        chain_id: Chain ID to fetch from
        tracked_tokens: List of tokens to fetch balances for
        
    Returns:
        Dictionary with native and token balance data
    """
    try:
        # Initialize Web3 client and wallet manager
        chain_config = config.get_chain_config(chain_id)
        if not chain_config:
            raise ValueError(f"Unsupported chain ID: {chain_id}")
        
        web3_client = Web3Client(chain_config)
        await web3_client.connect()
        
        if not web3_client.is_connected:
            raise Exception(f"Failed to connect to chain {chain_id}")
        
        wallet_manager = WalletManager(chain_config)
        await wallet_manager.initialize(web3_client)
        
        # Fetch native ETH balance
        native_balance_data = await wallet_manager.get_wallet_balance(wallet_address)
        if native_balance_data['status'] != 'success':
            raise Exception(f"Failed to get native balance: {native_balance_data.get('error', 'Unknown error')}")
        
        # Format native balance
        native_balance = {
            'symbol': 'ETH',
            'decimals': 18,
            'raw': str(native_balance_data['eth_balance_wei']),
            'formatted': str(native_balance_data['eth_balance'])
        }
        
        # Fetch ERC-20 token balances
        token_balances = []
        for token_info in tracked_tokens:
            try:
                # Use Web3Client's get_token_balance method
                balance_wei = await web3_client.get_token_balance(
                    token_info['address'], 
                    wallet_address
                )
                
                # Format balance
                decimals = token_info.get('decimals', 18)
                balance_formatted = Decimal(balance_wei) / (10 ** decimals)
                
                token_balances.append({
                    'address': token_info['address'],
                    'symbol': token_info.get('symbol', 'UNKNOWN'),
                    'name': token_info.get('name', 'Unknown Token'),
                    'decimals': decimals,
                    'raw': str(balance_wei),
                    'formatted': str(balance_formatted),
                    'usd_value': None  # TODO: Add price feed integration
                })
                
            except Exception as e:
                logger.warning(f"Failed to get balance for token {token_info['address']}: {e}")
                # Continue with other tokens
                continue
        
        # Close connections
        await web3_client.disconnect()
        
        return {
            'native': native_balance,
            'tokens': token_balances
        }
        
    except Exception as e:
        logger.error(f"Failed to fetch wallet balances: {e}")
        raise


def _update_wallet_balance_records(
    wallet_address: str, 
    chain_id: int, 
    balance_data: Dict[str, Any]
) -> None:
    """
    Update WalletBalance records in database for caching and historical tracking.
    
    Args:
        wallet_address: Wallet address
        chain_id: Chain ID
        balance_data: Balance data from blockchain
    """
    try:
        # Get wallet record
        wallet = Wallet.objects.filter(address=wallet_address).first()
        if not wallet:
            logger.warning(f"No wallet record found for {wallet_address}")
            return
        
        current_time = timezone.now()
        
        with db_transaction.atomic():
            # Update native ETH balance
            native_data = balance_data['native']
            WalletBalance.objects.update_or_create(
                wallet=wallet,
                chain_id=chain_id,
                token_address='ETH',
                defaults={
                    'token_symbol': native_data['symbol'],
                    'token_name': 'Ethereum',
                    'token_decimals': native_data['decimals'],
                    'balance_wei': native_data['raw'],
                    'balance_formatted': Decimal(native_data['formatted']),
                    'usd_value': None,  # TODO: Add price conversion
                    'last_updated': current_time,
                    'is_stale': False,
                    'update_error': ''
                }
            )
            
            # Update token balances
            for token_data in balance_data['tokens']:
                WalletBalance.objects.update_or_create(
                    wallet=wallet,
                    chain_id=chain_id,
                    token_address=token_data['address'],
                    defaults={
                        'token_symbol': token_data['symbol'],
                        'token_name': token_data['name'],
                        'token_decimals': token_data['decimals'],
                        'balance_wei': token_data['raw'],
                        'balance_formatted': Decimal(token_data['formatted']),
                        'usd_value': token_data.get('usd_value'),
                        'last_updated': current_time,
                        'is_stale': False,
                        'update_error': ''
                    }
                )
        
        logger.debug(f"Updated balance records for {wallet_address}")
        
    except Exception as e:
        logger.error(f"Failed to update wallet balance records: {e}")
        # Don't re-raise as this is a cache operation