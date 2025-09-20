"""
Wallet API Views - Authentication and Management

This module provides API endpoints for wallet connection, SIWE authentication,
balance management, and wallet operations. Implements secure client-side
key management with comprehensive error handling and logging.

Phase 5.1B Implementation:
- SIWE authentication endpoints
- Wallet connection and disconnection
- Balance retrieval and tracking
- Transaction monitoring
- Security and audit endpoints
"""

import json
import logging
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
from asgiref.sync import sync_to_async
import asyncio

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import SIWESession, Wallet, WalletBalance, WalletActivity
from .services import wallet_service, siwe_service

logger = logging.getLogger(__name__)


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
        
        # Validate chain ID is supported
        supported_chains = [84532, 1, 8453]  # Base Sepolia, Ethereum, Base
        if chain_id not in supported_chains:
            return Response(
                {'error': f'Unsupported chain ID. Supported: {supported_chains}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate SIWE message
        siwe_data = siwe_service.create_siwe_message(
            wallet_address=wallet_address,
            chain_id=chain_id
        )
        
        logger.info(f"Generated SIWE message for {wallet_address} on chain {chain_id}")
        
        return Response({
            'message': siwe_data['message'],
            'nonce': siwe_data['nonce'],
            'issued_at': siwe_data['issued_at'].isoformat(),
            'expiration_time': siwe_data['expiration_time'].isoformat()
        })
        
    except ValidationError as e:
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
        "session_id": "uuid"
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
        
        # Get client information
        ip_address = get_client_ip(request)
        user_agent = get_user_agent(request)
        
        # Authenticate wallet using async service
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
        
        # Run authentication
        user, wallet, siwe_session = asyncio.run(authenticate())
        
        if not user or not wallet or not siwe_session:
            return Response(
                {'error': 'Authentication failed'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Log the user in to Django session
        login(request, user)
        
        # Store SIWE session ID in Django session
        request.session['siwe_session_id'] = str(siwe_session.session_id)
        request.session['wallet_address'] = wallet.address
        
        logger.info(f"Wallet authentication successful for {wallet_address}")
        
        return Response({
            'success': True,
            'user_id': user.id,
            'wallet_id': str(wallet.wallet_id),
            'session_id': str(siwe_session.session_id),
            'wallet_address': wallet.address,
            'wallet_type': wallet.wallet_type,
            'primary_chain_id': wallet.primary_chain_id
        })
        
    except Exception as e:
        logger.error(f"Error authenticating wallet: {e}")
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
        # Get client information
        ip_address = get_client_ip(request)
        user_agent = get_user_agent(request)
        
        # Get user's active wallet
        if hasattr(request.user, 'wallets'):
            wallet = request.user.wallets.filter(
                status=Wallet.WalletStatus.CONNECTED
            ).first()
            
            if wallet:
                # Disconnect wallet using async service
                async def disconnect():
                    return await wallet_service.disconnect_wallet(
                        wallet, ip_address, user_agent
                    )
                
                success = asyncio.run(disconnect())
                
                if not success:
                    logger.warning(f"Failed to disconnect wallet {wallet.address}")
        
        # Clear session data
        request.session.pop('siwe_session_id', None)
        request.session.pop('wallet_address', None)
        
        # Django logout
        logout(request)
        
        logger.info(f"User {request.user.username} logged out successfully")
        
        return Response({
            'success': True,
            'message': 'Wallet disconnected successfully'
        })
    except:
        print("error")

