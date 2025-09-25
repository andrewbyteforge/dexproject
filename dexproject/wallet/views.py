"""
Wallet API Views - Fixed Database Field Issues

Fixed all database field mismatches causing startup errors:
- Changed 'metadata' to 'data' field references
- Fixed WalletBalance field names to match actual model
- Fixed incomplete function implementations
- Added proper error handling throughout

File: dexproject/wallet/views.py
"""

import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from decimal import Decimal
import uuid
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.utils.decorators import method_decorator
from django.views.generic import View
from django.utils import timezone
from django.conf import settings
from asgiref.sync import sync_to_async

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

# Import our models
from .models import SIWESession, Wallet, WalletBalance, WalletTransaction, WalletActivity
import secrets

logger = logging.getLogger(__name__)

# Import wallet service (will be None if not available)
try:
    from .services import wallet_service
except ImportError:
    wallet_service = None


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_client_ip(request: HttpRequest) -> Optional[str]:
    """Extract client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def get_user_agent(request: HttpRequest) -> str:
    """Extract user agent from request."""
    return request.META.get('HTTP_USER_AGENT', 'Unknown')


# =============================================================================
# SIWE AUTHENTICATION ENDPOINTS
# =============================================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def generate_siwe_message(request) -> Response:
    """
    Generate SIWE (Sign-In with Ethereum) message for wallet authentication.
    
    Request body:
    {
        "wallet_address": "0x...",
        "chain_id": 1,
        "nonce": "optional_custom_nonce"
    }
    
    Returns:
        Response: SIWE message to be signed by the wallet
    """
    try:
        data = json.loads(request.body)
        wallet_address = data.get('wallet_address', '').lower()
        chain_id = data.get('chain_id', 1)
        custom_nonce = data.get('nonce')
        
        # Validate wallet address
        if not wallet_address or len(wallet_address) != 42 or not wallet_address.startswith('0x'):
            return Response(
                {'error': 'Invalid wallet address format'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate chain ID
        if not isinstance(chain_id, int) or chain_id <= 0:
            return Response(
                {'error': 'Invalid chain ID'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate nonce if not provided
        nonce = custom_nonce or secrets.token_hex(16)
        
        # Create SIWE message
        domain = request.get_host()
        issued_at = datetime.now().isoformat()
        
        # Create the SIWE message according to EIP-4361
        siwe_message = (
            f"{domain} wants you to sign in with your Ethereum account:\n"
            f"{wallet_address}\n\n"
            f"Welcome to DEX Trading Platform! Sign in to access advanced trading features.\n\n"
            f"URI: https://{domain}\n"
            f"Version: 1\n"
            f"Chain ID: {chain_id}\n"
            f"Nonce: {nonce}\n"
            f"Issued At: {issued_at}"
        )
        
        if wallet_service:
            # Use the actual SIWE service to create the message
            try:
                # Call the synchronous method directly (not async)
                message_data = wallet_service.siwe_service.create_siwe_message(
                    wallet_address=wallet_address,
                    chain_id=chain_id,
                    nonce=nonce
                )
                
                logger.info(f"Generated SIWE message for {wallet_address} on chain {chain_id}")
                
                return Response({
                    'message': message_data['message'],
                    'nonce': message_data['nonce'],
                    'domain': domain,
                    'chain_id': chain_id,
                    'wallet_address': wallet_address
                })
                
            except Exception as e:
                logger.error(f"Error generating SIWE message via service: {e}")
                # Fall back to manual message creation
        
        # Fallback: create message manually
        logger.info(f"Generated SIWE message for {wallet_address} on chain {chain_id}")
        
        return Response({
            'message': siwe_message,
            'nonce': nonce,
            'domain': domain,
            'chain_id': chain_id,
            'wallet_address': wallet_address
        })
        
    except json.JSONDecodeError:
        return Response(
            {'error': 'Invalid JSON format'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error generating SIWE message: {e}")
        return Response(
            {'error': 'Failed to generate SIWE message'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def authenticate_wallet(request) -> Response:
    """
    Authenticate wallet using SIWE signature.
    
    FIXED: Updated to use 'data' field instead of 'metadata'
    
    Request body:
    {
        "wallet_address": "0x...",
        "signature": "0x...",
        "message": "SIWE message that was signed",
        "chain_id": 1,
        "wallet_type": "METAMASK"
    }
    
    Returns:
        Response: Authentication result with user and wallet information
    """
    try:
        data = json.loads(request.body)
        wallet_address = data.get('wallet_address', '').lower()
        signature = data.get('signature', '')
        message = data.get('message', '')
        chain_id = data.get('chain_id', 1)
        wallet_type = data.get('wallet_type', 'UNKNOWN')
        
        # Validate required fields
        if not all([wallet_address, signature, message]):
            return Response(
                {'error': 'Missing required fields: wallet_address, signature, message'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get client information
        ip_address = get_client_ip(request)
        user_agent = get_user_agent(request)
        
        logger.info(f"Attempting wallet authentication for {wallet_address} from IP {ip_address}")
        
        # Use real wallet service if available
        if wallet_service:
            try:
                # Run the async authentication method
                async def authenticate():
                    return await wallet_service.authenticate_wallet(
                        wallet_address=wallet_address,
                        chain_id=chain_id,
                        signature=signature,
                        message=message,
                        wallet_type=wallet_type,
                        ip_address=ip_address,
                        user_agent=user_agent
                    )
                
                auth_result = asyncio.run(authenticate())
                user, wallet, siwe_session = auth_result
                
                if not user or not wallet:
                    logger.warning(f"Authentication failed for {wallet_address} - invalid signature or user creation failed")
                    return Response(
                        {'error': 'Authentication failed - invalid signature'},
                        status=status.HTTP_401_UNAUTHORIZED
                    )
                
            except Exception as e:
                logger.error(f"Error during wallet service authentication: {e}")
                return Response(
                    {'error': 'Authentication service error'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            # Fallback authentication without full verification
            logger.warning("Using fallback authentication - signature not verified")
            
            # Get or create user (simplified for demo)
            username = f"wallet_{wallet_address[-8:]}"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': 'Wallet',
                    'last_name': 'User',
                    'email': f"{username}@wallet.local"
                }
            )
            
            # Get or create wallet record
            wallet, created = Wallet.objects.get_or_create(
                address=wallet_address,
                defaults={
                    'user': user,
                    'wallet_type': wallet_type,
                    'primary_chain_id': chain_id,
                    'status': Wallet.WalletStatus.CONNECTED
                }
            )
            
            # Create a basic SIWE session with all required fields
            siwe_session = SIWESession.objects.create(
                session_id=uuid.uuid4(),  # Use UUID instead of hex string
                wallet_address=wallet_address,
                user=user,
                status=SIWESession.SessionStatus.VERIFIED,
                message=message,
                signature=signature,
                chain_id=chain_id,
                ip_address=ip_address,
                user_agent=user_agent,
                # Add required SIWE message fields
                domain=request.get_host(),
                uri=f"https://{request.get_host()}",
                version='1',
                nonce=secrets.token_hex(16),  # Generate a nonce
                issued_at=timezone.now(),  # Required field - set to current time
                statement="Sign in to access advanced trading features."
            )
        
        # **CRITICAL FIX: Login user with specified backend**
        # This is the fix for the "multiple authentication backends" error
        login(request, user, backend='wallet.auth.SIWEAuthenticationBackend')
        
        # Store session information
        request.session['siwe_session_id'] = str(siwe_session.session_id)
        request.session['wallet_address'] = wallet.address
        request.session['wallet_id'] = str(wallet.wallet_id)
        
        # Log successful authentication
        logger.info(f"Wallet authentication successful for {wallet_address} - User: {user.username}")
        
        # Create wallet activity log - FIXED: Use 'data' field
        try:
            WalletActivity.objects.create(
                wallet=wallet,
                user=user,
                activity_type=WalletActivity.ActivityType.SIWE_LOGIN,
                description=f"Wallet connected via {wallet_type}",
                ip_address=ip_address,
                user_agent=user_agent,
                data={  # FIXED: Use 'data' instead of 'metadata'
                    'chain_id': chain_id,
                    'session_id': str(siwe_session.session_id),
                    'wallet_type': wallet_type
                }
            )
        except Exception as e:
            logger.warning(f"Failed to create wallet activity log: {e}")
        
        return Response({
            'success': True,
            'user_id': user.id,
            'wallet_id': str(wallet.wallet_id),
            'session_id': str(siwe_session.session_id),
            'wallet_address': wallet.address,
            'wallet_type': wallet.wallet_type,
            'primary_chain_id': wallet.primary_chain_id,
            'wallet_name': wallet.get_display_name()
        })
        
    except json.JSONDecodeError:
        return Response(
            {'error': 'Invalid JSON format'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Unexpected error in authenticate_wallet: {e}")
        return Response(
            {'error': 'Authentication failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_wallet(request) -> Response:
    """
    Logout and disconnect wallet.
    
    FIXED: Updated to use 'data' field instead of 'metadata'
    
    Cleans up SIWE sessions and logs out the user.
    
    Returns:
        Response: Logout confirmation
    """
    try:
        wallet_address = request.session.get('wallet_address')
        siwe_session_id = request.session.get('siwe_session_id')
        
        # Invalidate SIWE session
        if siwe_session_id:
            try:
                siwe_session = SIWESession.objects.get(session_id=siwe_session_id)
                siwe_session.status = SIWESession.SessionStatus.LOGGED_OUT
                siwe_session.logged_out_at = timezone.now()
                siwe_session.save(update_fields=['status', 'logged_out_at'])
                logger.info(f"Invalidated SIWE session {siwe_session_id}")
            except SIWESession.DoesNotExist:
                logger.warning(f"SIWE session {siwe_session_id} not found during logout")
        
        # Create logout activity log - FIXED: Use 'data' field
        if wallet_address:
            try:
                wallet = Wallet.objects.get(address=wallet_address)
                WalletActivity.objects.create(
                    wallet=wallet,
                    user=request.user,
                    activity_type=WalletActivity.ActivityType.DISCONNECTION,
                    description="Wallet disconnected",
                    ip_address=get_client_ip(request),
                    user_agent=get_user_agent(request),
                    data={'session_id': siwe_session_id}  # FIXED: Use 'data' instead of 'metadata'
                )
            except Wallet.DoesNotExist:
                logger.warning(f"Wallet {wallet_address} not found during logout")
        
        # Clear session data
        request.session.flush()
        
        # Logout user
        logout(request)
        
        logger.info(f"User logged out successfully - wallet: {wallet_address}")
        
        return Response({
            'success': True,
            'message': 'Wallet disconnected successfully'
        })
        
    except Exception as e:
        logger.error(f"Error during wallet logout: {e}")
        return Response(
            {'error': 'Logout failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# =============================================================================
# WALLET MANAGEMENT ENDPOINTS
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_wallet_info(request) -> Response:
    """
    Get current wallet information and summary.
    
    FIXED: Updated database field references to match actual model fields
    
    Returns:
        Response: Wallet information including balances and status
    """
    try:
        wallet_address = request.session.get('wallet_address')
        if not wallet_address:
            return Response(
                {'error': 'No wallet connected'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            wallet = Wallet.objects.get(address=wallet_address, user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {'error': 'Wallet not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get wallet balances - FIXED: Use correct field names from model
        balances = list(WalletBalance.objects.filter(
            wallet=wallet,
            balance_wei__gt=0  # FIXED: Use actual field name from model
        ).values(
            'token_symbol',
            'balance_wei',        # FIXED: Use actual field name
            'balance_formatted',  # FIXED: Use actual field name  
            'usd_value',
            'chain_id',
            'last_updated'
        ))
        
        # Get recent activity - FIXED: Use 'data' field instead of 'metadata'
        recent_activity = list(WalletActivity.objects.filter(
            wallet=wallet
        ).order_by('-created_at')[:10].values(
            'activity_type',
            'description',
            'created_at',
            'data'  # FIXED: Use 'data' instead of 'metadata'
        ))
        
        wallet_info = {
            'wallet_id': str(wallet.wallet_id),
            'address': wallet.address,
            'wallet_type': wallet.wallet_type,
            'primary_chain_id': wallet.primary_chain_id,
            'status': wallet.status,
            'display_name': wallet.get_display_name(),
            'created_at': wallet.created_at,
            'last_connected_at': wallet.last_connected_at,
            'balances': balances,
            'recent_activity': recent_activity,
            'total_usd_value': sum(float(b['usd_value'] or 0) for b in balances)
        }
        
        return Response(wallet_info)
        
    except Exception as e:
        logger.error(f"Error getting wallet info: {e}")
        return Response(
            {'error': 'Failed to get wallet information'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_wallet_settings(request) -> Response:
    """
    Update wallet settings and preferences.
    
    FIXED: Completed function implementation and fixed field references
    
    Request body:
    {
        "display_name": "My Trading Wallet",
        "is_trading_enabled": true,
        "notifications_enabled": true
    }
    
    Returns:
        Response: Updated wallet settings
    """
    try:
        wallet_address = request.session.get('wallet_address')
        if not wallet_address:
            return Response(
                {'error': 'No wallet connected'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            wallet = Wallet.objects.get(address=wallet_address, user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {'error': 'Wallet not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        data = json.loads(request.body)
        
        # Update allowed fields
        if 'display_name' in data:
            wallet.display_name = data['display_name'][:100]  # Limit length
        
        if 'is_trading_enabled' in data:
            wallet.is_trading_enabled = bool(data['is_trading_enabled'])
        
        if 'notifications_enabled' in data:
            wallet.notifications_enabled = bool(data['notifications_enabled'])
        
        wallet.save()
        
        # Log the settings update - FIXED: Use 'data' field and correct activity type
        try:
            WalletActivity.objects.create(
                wallet=wallet,
                user=request.user,
                activity_type=WalletActivity.ActivityType.CONFIG_CHANGE,
                description="Wallet settings updated",
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request),
                data={  # FIXED: Use 'data' instead of 'metadata'
                    'settings_updated': {
                        'display_name': data.get('display_name'),
                        'is_trading_enabled': data.get('is_trading_enabled'),
                        'notifications_enabled': data.get('notifications_enabled')
                    }
                }
            )
        except Exception as e:
            logger.warning(f"Failed to create settings update activity log: {e}")
        
        logger.info(f"Updated settings for wallet {wallet_address}")
        
        return Response({
            'success': True,
            'wallet_id': str(wallet.wallet_id),
            'display_name': wallet.display_name,
            'is_trading_enabled': wallet.is_trading_enabled,
            'notifications_enabled': wallet.notifications_enabled
        })
        
    except json.JSONDecodeError:
        return Response(
            {'error': 'Invalid JSON format'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error updating wallet settings: {e}")
        return Response(
            {'error': 'Failed to update wallet settings'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# =============================================================================
# BALANCE AND PORTFOLIO ENDPOINTS
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_wallet_balances(request) -> Response:
    """
    Get wallet balances across all supported chains.
    
    FIXED: Updated database field references to match actual model fields
    
    Query parameters:
        refresh: boolean - Force refresh from blockchain
        chain_id: integer - Filter by specific chain
    
    Returns:
        Response: Wallet balances with current USD values
    """
    try:
        wallet_address = request.session.get('wallet_address')
        if not wallet_address:
            return Response(
                {'error': 'No wallet connected'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            wallet = Wallet.objects.get(address=wallet_address, user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {'error': 'Wallet not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get query parameters
        force_refresh = request.GET.get('refresh', '').lower() == 'true'
        chain_id_filter = request.GET.get('chain_id')
        
        # Build query
        balance_query = WalletBalance.objects.filter(wallet=wallet)
        if chain_id_filter:
            try:
                chain_id_filter = int(chain_id_filter)
                balance_query = balance_query.filter(chain_id=chain_id_filter)
            except ValueError:
                return Response(
                    {'error': 'Invalid chain_id parameter'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Refresh balances if requested
        if force_refresh and wallet_service:
            try:
                async def refresh_balances():
                    return await wallet_service.refresh_wallet_balances(wallet_address)
                
                asyncio.run(refresh_balances())
                logger.info(f"Refreshed balances for wallet {wallet_address}")
            except Exception as e:
                logger.warning(f"Failed to refresh balances: {e}")
        
        # Get balances - FIXED: Use correct field names from model
        balances = list(balance_query.order_by('chain_id', 'token_symbol').values(
            'balance_id',
            'token_address',
            'token_symbol',
            'token_name',
            'balance_wei',        # FIXED: Use actual field name from model
            'balance_formatted',  # FIXED: Use actual field name from model
            'usd_value',
            'chain_id',
            'last_updated',
            'is_stale'           # FIXED: Use actual field name from model
        ))
        
        # Calculate totals - FIXED: Use correct field for calculations
        total_usd_value = sum(float(b['usd_value'] or 0) for b in balances)
        non_zero_balances = [b for b in balances if float(b['balance_formatted'] or 0) > 0]
        
        return Response({
            'wallet_address': wallet.address,
            'balances': balances,
            'non_zero_balances': non_zero_balances,
            'total_usd_value': total_usd_value,
            'balance_count': len(balances),
            'non_zero_count': len(non_zero_balances),
            'last_updated': max((b['last_updated'] for b in balances), default=None)
        })
        
    except Exception as e:
        logger.error(f"Error getting wallet balances: {e}")
        return Response(
            {'error': 'Failed to get wallet balances'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# =============================================================================
# TRANSACTION MONITORING ENDPOINTS  
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_wallet_transactions(request) -> Response:
    """
    Get wallet transaction history.
    
    Query parameters:
        page: integer - Page number (default: 1)
        page_size: integer - Items per page (default: 50, max: 200)
        chain_id: integer - Filter by chain
        status: string - Filter by status
        transaction_type: string - Filter by transaction type
    
    Returns:
        Response: Paginated transaction history
    """
    try:
        wallet_address = request.session.get('wallet_address')
        if not wallet_address:
            return Response(
                {'error': 'No wallet connected'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            wallet = Wallet.objects.get(address=wallet_address, user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {'error': 'Wallet not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get query parameters
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(200, max(1, int(request.GET.get('page_size', 50))))
        chain_id_filter = request.GET.get('chain_id')
        status_filter = request.GET.get('status')
        type_filter = request.GET.get('transaction_type')
        
        # Build query
        tx_query = WalletTransaction.objects.filter(wallet=wallet)
        
        if chain_id_filter:
            try:
                tx_query = tx_query.filter(chain_id=int(chain_id_filter))
            except ValueError:
                return Response(
                    {'error': 'Invalid chain_id parameter'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        if status_filter:
            tx_query = tx_query.filter(status=status_filter)
        
        if type_filter:
            tx_query = tx_query.filter(transaction_type=type_filter)
        
        # Order by timestamp (newest first) - FIXED: Use correct field name
        tx_query = tx_query.order_by('-block_timestamp')
        
        # Paginate
        total_count = tx_query.count()
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        transactions = list(tx_query[start_idx:end_idx].values(
            'transaction_id',
            'transaction_hash',  # FIXED: Use correct field name
            'chain_id',
            'transaction_type',
            'status',
            'from_address',
            'to_address',
            'value',
            'gas_used',
            'gas_price',
            'block_timestamp',   # FIXED: Use correct field name
            'block_number'
        ))
        
        return Response({
            'wallet_address': wallet.address,
            'transactions': transactions,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': (total_count + page_size - 1) // page_size,
                'has_next': end_idx < total_count,
                'has_prev': page > 1
            }
        })
        
    except ValueError as e:
        return Response(
            {'error': f'Invalid parameter: {e}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error getting wallet transactions: {e}")
        return Response(
            {'error': 'Failed to get wallet transactions'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# =============================================================================
# SECURITY AND AUDIT ENDPOINTS
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_wallet_activity(request) -> Response:
    """
    Get wallet activity log for security monitoring.
    
    FIXED: Updated to use 'data' field instead of 'metadata'
    
    Query parameters:
        page: integer - Page number (default: 1)
        page_size: integer - Items per page (default: 50)
        activity_type: string - Filter by activity type
    
    Returns:
        Response: Paginated activity log
    """
    try:
        wallet_address = request.session.get('wallet_address')
        if not wallet_address:
            return Response(
                {'error': 'No wallet connected'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            wallet = Wallet.objects.get(address=wallet_address, user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {'error': 'Wallet not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get query parameters
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(100, max(1, int(request.GET.get('page_size', 50))))
        activity_type_filter = request.GET.get('activity_type')
        
        # Build query
        activity_query = WalletActivity.objects.filter(wallet=wallet)
        if activity_type_filter:
            activity_query = activity_query.filter(activity_type=activity_type_filter)
        
        # Order by timestamp (newest first)
        activity_query = activity_query.order_by('-created_at')
        
        # Paginate
        total_count = activity_query.count()
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        activities = list(activity_query[start_idx:end_idx].values(
            'activity_id',
            'activity_type',
            'description',
            'ip_address',
            'user_agent',
            'created_at',
            'data'  # FIXED: Use 'data' instead of 'metadata'
        ))
        
        return Response({
            'wallet_address': wallet.address,
            'activities': activities,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': (total_count + page_size - 1) // page_size,
                'has_next': end_idx < total_count,
                'has_prev': page > 1
            }
        })
        
    except ValueError as e:
        return Response(
            {'error': f'Invalid parameter: {e}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error getting wallet activity: {e}")
        return Response(
            {'error': 'Failed to get wallet activity'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_siwe_sessions(request) -> Response:
    """
    Get active SIWE sessions for the user.
    
    Returns:
        Response: List of active SIWE sessions
    """
    try:
        sessions = list(SIWESession.objects.filter(
            user=request.user,
            status__in=[SIWESession.SessionStatus.VERIFIED, SIWESession.SessionStatus.ACTIVE]
        ).order_by('-created_at').values(
            'session_id',
            'wallet_address',
            'status',
            'chain_id',
            'ip_address',
            'user_agent',
            'created_at',
            'expires_at'
        ))
        
        return Response({
            'sessions': sessions,
            'active_count': len(sessions)
        })
        
    except Exception as e:
        logger.error(f"Error getting SIWE sessions: {e}")
        return Response(
            {'error': 'Failed to get SIWE sessions'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def revoke_siwe_session(request) -> Response:
    """
    Revoke a specific SIWE session.
    
    Request body:
    {
        "session_id": "session_id_to_revoke"
    }
    
    Returns:
        Response: Revocation confirmation
    """
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        
        if not session_id:
            return Response(
                {'error': 'session_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            siwe_session = SIWESession.objects.get(
                session_id=session_id,
                user=request.user
            )
        except SIWESession.DoesNotExist:
            return Response(
                {'error': 'SIWE session not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Revoke the session
        siwe_session.status = SIWESession.SessionStatus.REVOKED
        siwe_session.logged_out_at = timezone.now()
        siwe_session.save(update_fields=['status', 'logged_out_at'])
        
        logger.info(f"Revoked SIWE session {session_id} for user {request.user.username}")
        
        return Response({
            'success': True,
            'message': 'SIWE session revoked successfully'
        })
        
    except json.JSONDecodeError:
        return Response(
            {'error': 'Invalid JSON format'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error revoking SIWE session: {e}")
        return Response(
            {'error': 'Failed to revoke SIWE session'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# =============================================================================
# UTILITY AND HEALTH ENDPOINTS
# =============================================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def get_supported_chains(request) -> Response:
    """
    Get supported blockchain networks.
    
    Returns:
        Response: List of supported networks with their configurations
    """
    try:
        # Define supported chains (this could come from settings or database)
        supported_chains = [
            {
                'chain_id': 1,
                'name': 'Ethereum Mainnet',
                'symbol': 'ETH',
                'rpc_url': 'https://mainnet.infura.io/v3/YOUR_PROJECT_ID',
                'explorer_url': 'https://etherscan.io',
                'is_testnet': False
            },
            {
                'chain_id': 11155111,
                'name': 'Sepolia Testnet',
                'symbol': 'SepoliaETH',
                'rpc_url': 'https://sepolia.infura.io/v3/YOUR_PROJECT_ID',
                'explorer_url': 'https://sepolia.etherscan.io',
                'is_testnet': True
            },
            {
                'chain_id': 137,
                'name': 'Polygon Mainnet',
                'symbol': 'MATIC',
                'rpc_url': 'https://polygon-mainnet.infura.io/v3/YOUR_PROJECT_ID',
                'explorer_url': 'https://polygonscan.com',
                'is_testnet': False
            },
            {
                'chain_id': 84532,
                'name': 'Base Sepolia',
                'symbol': 'ETH',
                'rpc_url': 'https://sepolia.base.org',
                'explorer_url': 'https://sepolia.basescan.org',
                'is_testnet': True
            }
        ]
        
        return Response({
            'supported_chains': supported_chains,
            'default_chain_id': 84532  # Base Sepolia for testing
        })
        
    except Exception as e:
        logger.error(f"Error getting supported chains: {e}")
        return Response(
            {'error': 'Failed to get supported chains'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request) -> Response:
    """
    Health check for wallet service.
    
    Returns:
        Response: Service health status
    """
    try:
        health_status = {
            'status': 'HEALTHY',
            'timestamp': timezone.now().isoformat(),
            'version': '1.0.0',
            'services': {
                'database': 'CONNECTED',
                'wallet_service': 'AVAILABLE' if wallet_service else 'UNAVAILABLE',
                'siwe_service': 'AVAILABLE' if wallet_service and hasattr(wallet_service, 'siwe_service') else 'UNAVAILABLE'
            }
        }
        
        # Test database connection
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            health_status['services']['database'] = 'CONNECTED'
        except Exception:
            health_status['services']['database'] = 'ERROR'
            health_status['status'] = 'DEGRADED'
        
        # Determine overall status
        if any(status == 'ERROR' for status in health_status['services'].values()):
            health_status['status'] = 'ERROR'
        elif any(status == 'UNAVAILABLE' for status in health_status['services'].values()):
            health_status['status'] = 'DEGRADED'
        
        status_code = status.HTTP_200_OK
        if health_status['status'] == 'ERROR':
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif health_status['status'] == 'DEGRADED':
            status_code = status.HTTP_200_OK  # Still return 200 for degraded
        
        return Response(health_status, status=status_code)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return Response(
            {
                'status': 'ERROR',
                'error': 'Health check failed',
                'timestamp': timezone.now().isoformat()
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )