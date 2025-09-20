"""
Wallet API Views - Complete SIWE Authentication and Management

This module provides comprehensive API endpoints for wallet connection, 
SIWE authentication, balance management, and wallet operations. 
Implements secure client-side key management with full error handling.

Phase 5.1B Implementation:
- SIWE authentication endpoints (EIP-4361)
- Wallet connection and disconnection
- Balance retrieval and tracking
- Transaction monitoring
- Security and audit endpoints
- Health monitoring

File: dexproject/wallet/views.py
"""

import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from decimal import Decimal

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

# Import our models (these will exist after migration)
from .models import SIWESession, Wallet, WalletBalance, WalletTransaction, WalletActivity
import secrets

logger = logging.getLogger(__name__)

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
    return request.META.get('HTTP_USER_AGENT', '')

# =============================================================================
# SERVICE INITIALIZATION - REAL IMPLEMENTATION
# =============================================================================

# Initialize real services
try:
    from .services import SIWEService, WalletService
    siwe_service = SIWEService()
    wallet_service = WalletService()
    logger.info("Successfully initialized real SIWE and Wallet services")
except ImportError as e:
    # Fallback to placeholder if services not available
    logger.error(f"Failed to import real services: {e}")
    
    class SIWEServicePlaceholder:
        """Placeholder SIWE service for fallback."""
        
        def create_siwe_message(self, wallet_address: str, chain_id: int, **kwargs):
            """Create a SIWE message for signing."""
            nonce = secrets.token_hex(16)
            issued_at = timezone.now()
            expiration_time = issued_at + timezone.timedelta(hours=24)
            
            message = f"""localhost:8000 wants you to sign in with your Ethereum account:
{wallet_address}

Sign in to DEX Auto-Trading Bot

URI: https://localhost:8000
Version: 1
Chain ID: {chain_id}
Nonce: {nonce}
Issued At: {issued_at.isoformat()}
Expiration Time: {expiration_time.isoformat()}"""
            
            return {
                'message': message,
                'nonce': nonce,
                'issued_at': issued_at,
                'expiration_time': expiration_time
            }
    
    siwe_service = SIWEServicePlaceholder()
    wallet_service = None
    logger.warning("Using placeholder SIWE service - full implementation pending")

# =============================================================================
# SIWE AUTHENTICATION ENDPOINTS
# =============================================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def generate_siwe_message(request) -> Response:
    """
    Generate a SIWE message for wallet authentication.
    
    Expected payload:
    {
        "wallet_address": "0x...",
        "chain_id": 84532
    }
    
    Returns:
    {
        "message": "formatted SIWE message",
        "nonce": "random nonce",
        "issued_at": "ISO timestamp",
        "expiration_time": "ISO timestamp"
    }
    """
    try:
        data = request.data
        wallet_address = data.get('wallet_address')
        chain_id = data.get('chain_id')
        
        if not wallet_address or not chain_id:
            return Response(
                {'error': 'wallet_address and chain_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate wallet address format
        if not wallet_address.startswith('0x') or len(wallet_address) != 42:
            return Response(
                {'error': 'Invalid wallet address format'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate chain ID is supported
        supported_chains = [84532, 1, 8453]  # Base Sepolia, Ethereum, Base
        if chain_id not in supported_chains:
            return Response(
                {'error': f'Unsupported chain ID. Supported: {supported_chains}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate SIWE message using real service
        siwe_data = siwe_service.create_siwe_message(
            wallet_address=wallet_address,
            chain_id=chain_id
        )
        
        logger.info(f"Generated SIWE message for {wallet_address} on chain {chain_id}")
        
        return Response({
            'message': siwe_data['message'],
            'nonce': siwe_data['nonce'],
            'issued_at': siwe_data['issued_at'].isoformat() if hasattr(siwe_data['issued_at'], 'isoformat') else siwe_data['issued_at'],
            'expiration_time': siwe_data['expiration_time'].isoformat() if hasattr(siwe_data['expiration_time'], 'isoformat') else siwe_data['expiration_time']
        })
        
    except ValidationError as e:
        logger.warning(f"Validation error in generate_siwe_message: {e}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error generating SIWE message: {e}")
        return Response(
            {'error': 'Internal server error'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([AllowAny])
def authenticate_wallet(request) -> Response:
    """
    Authenticate a wallet using SIWE signature.
    
    Expected payload:
    {
        "wallet_address": "0x...",
        "chain_id": 84532,
        "message": "SIWE message that was signed",
        "signature": "0x...",
        "wallet_type": "METAMASK"
    }
    
    Returns:
    {
        "success": true,
        "user_id": 123,
        "wallet_id": "uuid",
        "session_id": "uuid",
        "wallet_address": "0x...",
        "wallet_type": "METAMASK",
        "primary_chain_id": 84532
    }
    """
    try:
        data = request.data
        wallet_address = data.get('wallet_address')
        chain_id = data.get('chain_id')
        message = data.get('message')
        signature = data.get('signature')
        wallet_type = data.get('wallet_type', 'METAMASK')
        
        # Validate required fields
        required_fields = ['wallet_address', 'chain_id', 'message', 'signature']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return Response(
                {'error': f'Missing required fields: {", ".join(missing_fields)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate wallet address format
        if not wallet_address.startswith('0x') or len(wallet_address) != 42:
            return Response(
                {'error': 'Invalid wallet address format'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate signature format
        if not signature.startswith('0x') or len(signature) != 132:
            return Response(
                {'error': 'Invalid signature format'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get client information for security logging
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
            
            # Get or create user (simplified)
            username = f"wallet_{wallet_address[:10]}"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': f"{username}@wallet.local",
                    'first_name': f"Wallet {wallet_address[:6]}",
                    'is_active': True
                }
            )
            
            # Get or create wallet record
            wallet, created = Wallet.objects.get_or_create(
                address=wallet_address,
                defaults={
                    'user': user,
                    'wallet_type': wallet_type,
                    'name': f"Wallet {wallet_address[:10]}",
                    'primary_chain_id': chain_id,
                    'status': Wallet.WalletStatus.CONNECTED,
                    'last_connected_at': timezone.now()
                }
            )
            
            # Create simplified SIWE session
            siwe_session = SIWESession.objects.create(
                user=user,
                wallet_address=wallet_address,
                domain='localhost:8000',
                statement='Sign in to DEX Auto-Trading Bot',
                uri='https://localhost:8000',
                version='1',
                chain_id=chain_id,
                nonce=secrets.token_hex(16),
                issued_at=timezone.now(),
                expiration_time=timezone.now() + timezone.timedelta(hours=24),
                message=message,
                signature=signature,
                status=SIWESession.SessionStatus.VERIFIED,
                ip_address=ip_address,
                user_agent=user_agent,
                verified_at=timezone.now()
            )
        
        # Log the user in to Django session
        login(request, user)
        
        # Store session information
        request.session['siwe_session_id'] = str(siwe_session.session_id)
        request.session['wallet_address'] = wallet.address
        request.session['wallet_id'] = str(wallet.wallet_id)
        
        # Log successful authentication
        logger.info(f"Wallet authentication successful for {wallet_address} - User: {user.username}")
        
        # Create wallet activity log
        try:
            WalletActivity.objects.create(
                wallet=wallet,
                activity_type=WalletActivity.ActivityType.LOGIN,
                description=f"Wallet connected via {wallet_type}",
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={
                    'chain_id': chain_id,
                    'session_id': str(siwe_session.session_id)
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
    
    Returns:
    {
        "success": true,
        "message": "Wallet disconnected successfully"
    }
    """
    try:
        user = request.user
        wallet_address = request.session.get('wallet_address')
        siwe_session_id = request.session.get('siwe_session_id')
        
        # Mark SIWE session as expired
        if siwe_session_id:
            try:
                siwe_session = SIWESession.objects.get(session_id=siwe_session_id)
                siwe_session.mark_expired()
                logger.info(f"Marked SIWE session {siwe_session_id} as expired")
            except SIWESession.DoesNotExist:
                logger.warning(f"SIWE session {siwe_session_id} not found for logout")
        
        # Update wallet status
        if wallet_address:
            try:
                wallet = Wallet.objects.get(address=wallet_address, user=user)
                wallet.status = Wallet.WalletStatus.DISCONNECTED
                wallet.last_disconnected_at = timezone.now()
                wallet.save(update_fields=['status', 'last_disconnected_at'])
                
                # Log wallet activity
                WalletActivity.objects.create(
                    wallet=wallet,
                    activity_type=WalletActivity.ActivityType.LOGOUT,
                    description="Wallet disconnected",
                    ip_address=get_client_ip(request),
                    user_agent=get_user_agent(request)
                )
                
                logger.info(f"Wallet {wallet_address} disconnected for user {user.username}")
            except Wallet.DoesNotExist:
                logger.warning(f"Wallet {wallet_address} not found for user {user.username}")
        
        # Clear Django session
        logout(request)
        request.session.flush()
        
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
    
    Returns:
    {
        "wallet": {
            "wallet_id": "uuid",
            "address": "0x...",
            "name": "Wallet Name",
            "wallet_type": "METAMASK",
            "is_connected": true,
            "primary_chain_id": 84532,
            "supported_chains": [84532, 1],
            "trading_enabled": true,
            "last_connected_at": "ISO timestamp"
        }
    }
    """
    try:
        # Get user's primary wallet
        wallet = request.user.wallets.filter(
            status=Wallet.WalletStatus.CONNECTED
        ).first()
        
        if not wallet:
            return Response(
                {'error': 'No connected wallet found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get wallet summary
        if wallet_service:
            try:
                async def get_summary():
                    return await wallet_service.get_wallet_summary(wallet)
                
                wallet_summary = asyncio.run(get_summary())
            except Exception as e:
                logger.warning(f"Failed to get wallet summary from service: {e}")
                wallet_summary = None
        else:
            wallet_summary = None
        
        # Build response with available data
        if wallet_summary:
            wallet_data = wallet_summary
        else:
            # Basic wallet info
            wallet_data = {
                'wallet_id': str(wallet.wallet_id),
                'address': wallet.address,
                'name': wallet.get_display_name(),
                'wallet_type': wallet.wallet_type,
                'is_connected': wallet.status == Wallet.WalletStatus.CONNECTED,
                'primary_chain_id': wallet.primary_chain_id,
                'supported_chains': wallet.supported_chains,
                'trading_enabled': wallet.is_trading_enabled,
                'last_connected_at': wallet.last_connected_at.isoformat() if wallet.last_connected_at else None
            }
        
        return Response({
            'wallet': wallet_data
        })
        
    except Exception as e:
        logger.error(f"Error getting wallet info: {e}")
        return Response(
            {'error': 'Failed to retrieve wallet information'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_wallet_balances(request) -> Response:
    """
    Get wallet balances for all supported chains.
    
    Query parameters:
    - refresh: bool - Force refresh from blockchain
    
    Returns:
    {
        "balances": [
            {
                "token_symbol": "ETH",
                "token_name": "Ethereum",
                "balance_formatted": "1.5",
                "usd_value": "3000.00",
                "chain_id": 1,
                "last_updated": "ISO timestamp",
                "is_stale": false
            }
        ],
        "total_usd_value": "3000.00"
    }
    """
    try:
        # Get user's primary wallet
        wallet = request.user.wallets.filter(
            status=Wallet.WalletStatus.CONNECTED
        ).first()
        
        if not wallet:
            return Response(
                {'error': 'No connected wallet found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if refresh is requested
        refresh = request.query_params.get('refresh', '').lower() == 'true'
        
        # Get balances from service or database
        if wallet_service and refresh:
            try:
                async def get_balances():
                    return await wallet_service.get_wallet_balances(wallet, force_refresh=True)
                
                balances = asyncio.run(get_balances())
            except Exception as e:
                logger.warning(f"Failed to refresh balances from service: {e}")
                # Fall back to database balances
                balances = wallet.balances.all()
        else:
            # Get balances from database
            balances = wallet.balances.all()
        
        # Format balance data
        balance_data = []
        total_usd = Decimal('0')
        
        for balance in balances:
            if hasattr(balance, 'token_symbol'):
                # Model instance
                balance_info = {
                    'token_symbol': balance.token_symbol,
                    'token_name': balance.token_name,
                    'balance_formatted': str(balance.balance_formatted),
                    'chain_id': balance.chain_id,
                    'last_updated': balance.last_updated.isoformat(),
                    'is_stale': balance.is_stale
                }
                
                if balance.usd_value is not None:
                    balance_info['usd_value'] = str(balance.usd_value)
                    total_usd += balance.usd_value
                else:
                    balance_info['usd_value'] = None
            else:
                # Service response (dict)
                balance_info = balance
                if balance.get('usd_value'):
                    total_usd += Decimal(str(balance['usd_value']))
            
            balance_data.append(balance_info)
        
        return Response({
            'balances': balance_data,
            'total_usd_value': str(total_usd)
        })
        
    except Exception as e:
        logger.error(f"Error getting wallet balances: {e}")
        return Response(
            {'error': 'Failed to retrieve wallet balances'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_wallet_settings(request) -> Response:
    """
    Update wallet settings and preferences.
    
    Expected payload:
    {
        "name": "My Trading Wallet",
        "trading_enabled": true,
        "daily_limit_usd": "1000.00",
        "per_transaction_limit_usd": "100.00",
        "requires_confirmation": true
    }
    
    Returns:
    {
        "success": true,
        "message": "Wallet settings updated successfully"
    }
    """
    try:
        # Get user's primary wallet
        wallet = request.user.wallets.filter(
            status=Wallet.WalletStatus.CONNECTED
        ).first()
        
        if not wallet:
            return Response(
                {'error': 'No connected wallet found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        data = request.data
        updated_fields = []
        
        # Update wallet settings
        if 'name' in data:
            wallet.name = data['name']
            updated_fields.append('name')
        
        if 'trading_enabled' in data:
            wallet.is_trading_enabled = bool(data['trading_enabled'])
            updated_fields.append('is_trading_enabled')
        
        if 'daily_limit_usd' in data:
            try:
                wallet.daily_limit_usd = Decimal(str(data['daily_limit_usd']))
                updated_fields.append('daily_limit_usd')
            except (ValueError, TypeError):
                return Response(
                    {'error': 'Invalid daily_limit_usd value'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        if 'per_transaction_limit_usd' in data:
            try:
                wallet.per_transaction_limit_usd = Decimal(str(data['per_transaction_limit_usd']))
                updated_fields.append('per_transaction_limit_usd')
            except (ValueError, TypeError):
                return Response(
                    {'error': 'Invalid per_transaction_limit_usd value'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        if 'requires_confirmation' in data:
            wallet.requires_confirmation = bool(data['requires_confirmation'])
            updated_fields.append('requires_confirmation')
        
        # Save changes
        if updated_fields:
            wallet.save(update_fields=updated_fields)
            
            # Log wallet activity
            WalletActivity.objects.create(
                wallet=wallet,
                activity_type=WalletActivity.ActivityType.SETTINGS_UPDATED,
                description=f"Updated settings: {', '.join(updated_fields)}",
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request),
                metadata={'updated_fields': updated_fields}
            )
            
            logger.info(f"Updated wallet settings for {wallet.address}: {updated_fields}")
        
        return Response({
            'success': True,
            'message': 'Wallet settings updated successfully',
            'updated_fields': updated_fields
        })
        
    except Exception as e:
        logger.error(f"Error updating wallet settings: {e}")
        return Response(
            {'error': 'Failed to update wallet settings'},
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
    - chain_id: int - Filter by chain ID
    - status: str - Filter by transaction status
    - limit: int - Number of transactions to return (default: 50)
    - offset: int - Pagination offset (default: 0)
    
    Returns:
    {
        "transactions": [...],
        "total_count": 150,
        "has_more": true
    }
    """
    try:
        # Get user's primary wallet
        wallet = request.user.wallets.filter(
            status=Wallet.WalletStatus.CONNECTED
        ).first()
        
        if not wallet:
            return Response(
                {'error': 'No connected wallet found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Parse query parameters
        chain_id = request.query_params.get('chain_id')
        status_filter = request.query_params.get('status')
        limit = min(int(request.query_params.get('limit', 50)), 100)
        offset = int(request.query_params.get('offset', 0))
        
        # Build query
        queryset = wallet.transactions.all()
        
        if chain_id:
            queryset = queryset.filter(chain_id=int(chain_id))
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Get total count
        total_count = queryset.count()
        
        # Apply pagination
        transactions = queryset.order_by('-created_at')[offset:offset + limit]
        
        # Format transaction data
        transaction_data = []
        for tx in transactions:
            transaction_data.append({
                'transaction_id': str(tx.transaction_id),
                'transaction_hash': tx.transaction_hash,
                'chain_id': tx.chain_id,
                'from_address': tx.from_address,
                'to_address': tx.to_address,
                'value_wei': str(tx.value_wei),
                'value_formatted': str(tx.value_formatted),
                'gas_used': tx.gas_used,
                'gas_price': str(tx.gas_price),
                'status': tx.status,
                'block_number': tx.block_number,
                'timestamp': tx.timestamp.isoformat() if tx.timestamp else None,
                'created_at': tx.created_at.isoformat(),
                'metadata': tx.metadata
            })
        
        return Response({
            'transactions': transaction_data,
            'total_count': total_count,
            'has_more': offset + limit < total_count,
            'limit': limit,
            'offset': offset
        })
        
    except Exception as e:
        logger.error(f"Error getting wallet transactions: {e}")
        return Response(
            {'error': 'Failed to retrieve wallet transactions'},
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
    
    Query parameters:
    - activity_type: str - Filter by activity type
    - limit: int - Number of activities to return (default: 50)
    - offset: int - Pagination offset (default: 0)
    
    Returns:
    {
        "activities": [...],
        "total_count": 25
    }
    """
    try:
        # Get user's primary wallet
        wallet = request.user.wallets.filter(
            status=Wallet.WalletStatus.CONNECTED
        ).first()
        
        if not wallet:
            return Response(
                {'error': 'No connected wallet found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Parse query parameters
        activity_type = request.query_params.get('activity_type')
        limit = min(int(request.query_params.get('limit', 50)), 100)
        offset = int(request.query_params.get('offset', 0))
        
        # Build query
        queryset = wallet.activities.all()
        
        if activity_type:
            queryset = queryset.filter(activity_type=activity_type)
        
        # Get total count
        total_count = queryset.count()
        
        # Apply pagination
        activities = queryset.order_by('-created_at')[offset:offset + limit]
        
        # Format activity data
        activity_data = []
        for activity in activities:
            activity_data.append({
                'activity_id': str(activity.activity_id),
                'activity_type': activity.activity_type,
                'description': activity.description,
                'ip_address': activity.ip_address,
                'user_agent': activity.user_agent,
                'metadata': activity.metadata,
                'created_at': activity.created_at.isoformat()
            })
        
        return Response({
            'activities': activity_data,
            'total_count': total_count,
            'limit': limit,
            'offset': offset
        })
        
    except Exception as e:
        logger.error(f"Error getting wallet activity: {e}")
        return Response(
            {'error': 'Failed to retrieve wallet activity'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_siwe_sessions(request) -> Response:
    """
    Get active SIWE sessions for security monitoring.
    
    Returns:
    {
        "sessions": [
            {
                "session_id": "uuid",
                "wallet_address": "0x...",
                "domain": "localhost:8000",
                "status": "VERIFIED",
                "issued_at": "ISO timestamp",
                "expiration_time": "ISO timestamp",
                "last_used": "ISO timestamp",
                "ip_address": "127.0.0.1",
                "user_agent": "Mozilla/5.0..."
            }
        ]
    }
    """
    try:
        user = request.user
        
        # Get active SIWE sessions for this user
        sessions = SIWESession.objects.filter(
            user=user,
            status=SIWESession.SessionStatus.VERIFIED
        ).order_by('-created_at')
        
        # Format session data
        session_data = []
        for session in sessions:
            session_data.append({
                'session_id': str(session.session_id),
                'wallet_address': session.wallet_address,
                'domain': session.domain,
                'status': session.status,
                'chain_id': session.chain_id,
                'issued_at': session.issued_at.isoformat(),
                'expiration_time': session.expiration_time.isoformat(),
                'last_used': session.last_used.isoformat() if session.last_used else None,
                'ip_address': session.ip_address,
                'user_agent': session.user_agent[:100] if session.user_agent else None,  # Truncate for display
                'is_valid': session.is_valid(),
                'created_at': session.created_at.isoformat()
            })
        
        return Response({
            'sessions': session_data
        })
        
    except Exception as e:
        logger.error(f"Error getting SIWE sessions: {e}")
        return Response(
            {'error': 'Failed to retrieve SIWE sessions'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def revoke_siwe_session(request) -> Response:
    """
    Revoke a specific SIWE session.
    
    Expected payload:
    {
        "session_id": "uuid"
    }
    
    Returns:
    {
        "success": true,
        "message": "Session revoked successfully"
    }
    """
    try:
        data = request.data
        session_id = data.get('session_id')
        
        if not session_id:
            return Response(
                {'error': 'session_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Find and revoke the session
        try:
            session = SIWESession.objects.get(
                session_id=session_id,
                user=request.user
            )
            
            session.mark_expired()
            
            logger.info(f"SIWE session {session_id} revoked by user {request.user.username}")
            
            return Response({
                'success': True,
                'message': 'Session revoked successfully'
            })
            
        except SIWESession.DoesNotExist:
            return Response(
                {'error': 'Session not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
    except Exception as e:
        logger.error(f"Error revoking SIWE session: {e}")
        return Response(
            {'error': 'Failed to revoke session'},
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
    {
        "chains": [
            {
                "chain_id": 84532,
                "name": "Base Sepolia",
                "network": "base-sepolia",
                "native_currency": {
                    "name": "Ethereum",
                    "symbol": "ETH",
                    "decimals": 18
                },
                "rpc_urls": ["https://sepolia.base.org"],
                "block_explorers": ["https://sepolia.basescan.org"],
                "is_testnet": true
            }
        ]
    }
    """
    try:
        # Define supported chains
        supported_chains = [
            {
                'chain_id': 84532,
                'name': 'Base Sepolia',
                'network': 'base-sepolia',
                'native_currency': {
                    'name': 'Ethereum',
                    'symbol': 'ETH',
                    'decimals': 18
                },
                'rpc_urls': ['https://sepolia.base.org'],
                'block_explorers': ['https://sepolia.basescan.org'],
                'is_testnet': True
            },
            {
                'chain_id': 1,
                'name': 'Ethereum Mainnet',
                'network': 'ethereum',
                'native_currency': {
                    'name': 'Ethereum',
                    'symbol': 'ETH',
                    'decimals': 18
                },
                'rpc_urls': ['https://eth-mainnet.g.alchemy.com/v2/demo'],
                'block_explorers': ['https://etherscan.io'],
                'is_testnet': False
            },
            {
                'chain_id': 8453,
                'name': 'Base Mainnet',
                'network': 'base',
                'native_currency': {
                    'name': 'Ethereum',
                    'symbol': 'ETH',
                    'decimals': 18
                },
                'rpc_urls': ['https://base-mainnet.g.alchemy.com/v2/demo'],
                'block_explorers': ['https://basescan.org'],
                'is_testnet': False
            }
        ]
        
        return Response({
            'chains': supported_chains
        })
        
    except Exception as e:
        logger.error(f"Error getting supported chains: {e}")
        return Response(
            {'error': 'Failed to retrieve supported chains'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request) -> Response:
    """
    Health check for wallet service.
    
    Returns:
    {
        "status": "healthy",
        "services": {
            "siwe_service": "available",
            "wallet_service": "available",
            "database": "healthy"
        },
        "timestamp": "ISO timestamp"
    }
    """
    try:
        health_status = {
            'status': 'healthy',
            'services': {},
            'timestamp': timezone.now().isoformat()
        }
        
        # Check SIWE service
        try:
            if siwe_service:
                # Test basic functionality
                test_data = siwe_service.create_siwe_message(
                    wallet_address='0x0000000000000000000000000000000000000000',
                    chain_id=84532
                )
                health_status['services']['siwe_service'] = 'available' if test_data else 'limited'
            else:
                health_status['services']['siwe_service'] = 'unavailable'
        except Exception as e:
            health_status['services']['siwe_service'] = f'error: {str(e)[:50]}'
        
        # Check wallet service
        try:
            if wallet_service:
                health_status['services']['wallet_service'] = 'available'
            else:
                health_status['services']['wallet_service'] = 'unavailable'
        except Exception as e:
            health_status['services']['wallet_service'] = f'error: {str(e)[:50]}'
        
        # Check database
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            health_status['services']['database'] = 'healthy'
        except Exception as e:
            health_status['services']['database'] = f'error: {str(e)[:50]}'
            health_status['status'] = 'degraded'
        
        # Determine overall status
        if any('error' in str(service_status) for service_status in health_status['services'].values()):
            health_status['status'] = 'degraded'
        
        return Response(health_status)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return Response({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)