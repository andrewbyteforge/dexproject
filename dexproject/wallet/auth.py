"""
SIWE Authentication Backend

Custom Django authentication backend for Sign-In with Ethereum (SIWE).
Integrates wallet-based authentication with Django's authentication system
while maintaining compatibility with existing Django auth.

Phase 5.1B Implementation:
- SIWE session validation
- Automatic user provisioning
- Session management integration
- Security event logging

File: dexproject/wallet/auth.py
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import SIWESession, Wallet

logger = logging.getLogger(__name__)


class SIWEAuthenticationBackend(BaseBackend):
    """
    Authentication backend for SIWE (Sign-In with Ethereum) sessions.
    
    This backend validates SIWE sessions and provides seamless integration
    with Django's authentication system. It supports automatic user creation
    and session management for wallet-based authentication.
    """
    
    def authenticate(self, request, siwe_session_id=None, **kwargs) -> Optional[User]:
        """
        Authenticate a user based on a SIWE session.
        
        Args:
            request: Django request object
            siwe_session_id: SIWE session identifier
            **kwargs: Additional authentication parameters
            
        Returns:
            User instance if authentication successful, None otherwise
        """
        if not siwe_session_id:
            return None
        
        try:
            # Get SIWE session
            siwe_session = SIWESession.objects.get(
                session_id=siwe_session_id,
                status=SIWESession.SessionStatus.VERIFIED
            )
            
            # Validate session is still valid
            if not siwe_session.is_valid():
                logger.info(f"SIWE session {siwe_session_id} is no longer valid")
                siwe_session.mark_expired()
                return None
            
            # Get or create user
            user = siwe_session.user
            if not user:
                # This shouldn't happen in normal flow, but handle gracefully
                user = self._get_or_create_user_for_wallet(siwe_session.wallet_address)
                siwe_session.user = user
                siwe_session.save(update_fields=['user'])
            
            # Validate user is active
            if not user.is_active:
                logger.warning(f"Authentication denied for inactive user: {user.username}")
                return None
            
            # Update session metadata if request is available
            if request:
                self._update_session_metadata(siwe_session, request)
            
            logger.info(f"SIWE authentication successful for user {user.username}")
            return user
            
        except SIWESession.DoesNotExist:
            logger.info(f"SIWE session {siwe_session_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error during SIWE authentication: {e}")
            return None
    
    def get_user(self, user_id: int) -> Optional[User]:
        """
        Get user by ID for session persistence.
        
        Args:
            user_id: Django user ID
            
        Returns:
            User instance if found, None otherwise
        """
        try:
            User = get_user_model()
            return User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None
    
    def _get_or_create_user_for_wallet(self, wallet_address: str) -> User:
        """
        Get or create a Django user for a wallet address.
        
        Args:
            wallet_address: Ethereum wallet address
            
        Returns:
            User instance
        """
        User = get_user_model()
        username = f"wallet_{wallet_address.lower()}"
        
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            # Create new user
            user = User.objects.create_user(
                username=username,
                email=f"{wallet_address.lower()}@wallet.local",
                first_name="Wallet",
                last_name=f"{wallet_address[:6]}...{wallet_address[-4:]}"
            )
            logger.info(f"Created new user for wallet {wallet_address}")
            return user
    
    def _update_session_metadata(self, siwe_session: SIWESession, request) -> None:
        """
        Update SIWE session metadata from request.
        
        Args:
            siwe_session: SIWE session instance
            request: Django request object
        """
        try:
            # Update Django session key
            if hasattr(request, 'session') and request.session.session_key:
                siwe_session.django_session_key = request.session.session_key
            
            # Update IP address if not set
            if not siwe_session.ip_address:
                x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                if x_forwarded_for:
                    ip = x_forwarded_for.split(',')[0]
                else:
                    ip = request.META.get('REMOTE_ADDR')
                siwe_session.ip_address = ip
            
            # Update user agent if not set
            if not siwe_session.user_agent:
                siwe_session.user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            siwe_session.save(update_fields=['django_session_key', 'ip_address', 'user_agent'])
            
        except Exception as e:
            logger.error(f"Error updating SIWE session metadata: {e}")


class WalletPermissionMixin:
    """
    Mixin to add wallet-related permission checking to views.
    
    Provides methods to check wallet ownership, trading permissions,
    and security restrictions for authenticated users.
    """
    
    def has_wallet_permission(self, user: User, wallet_address: str) -> bool:
        """
        Check if user has permission to access a specific wallet.
        
        Args:
            user: Django user instance
            wallet_address: Wallet address to check
            
        Returns:
            True if user has permission, False otherwise
        """
        try:
            wallet = user.wallets.get(
                address__iexact=wallet_address,
                status=Wallet.WalletStatus.CONNECTED
            )
            return True
        except Wallet.DoesNotExist:
            return False
        except Exception:
            return False
    
    def has_trading_permission(self, user: User) -> bool:
        """
        Check if user has trading permissions.
        
        Args:
            user: Django user instance
            
        Returns:
            True if user can trade, False otherwise
        """
        try:
            # Check if user has any active trading-enabled wallets
            return user.wallets.filter(
                status=Wallet.WalletStatus.CONNECTED,
                is_trading_enabled=True
            ).exists()
        except Exception:
            return False
    
    def get_user_primary_wallet(self, user: User) -> Optional[Wallet]:
        """
        Get user's primary connected wallet.
        
        Args:
            user: Django user instance
            
        Returns:
            Primary wallet instance or None
        """
        try:
            return user.wallets.filter(
                status=Wallet.WalletStatus.CONNECTED
            ).order_by('-last_connected_at').first()
        except Exception:
            return None


class SIWESessionMiddleware:
    """
    Middleware to validate SIWE sessions on each request.
    
    Ensures that wallet-authenticated users maintain valid SIWE sessions
    and automatically logs out users with expired sessions.
    """
    
    def __init__(self, get_response):
        """Initialize middleware."""
        self.get_response = get_response
    
    def __call__(self, request):
        """Process request and validate SIWE session if present."""
        # Check if user is authenticated and has SIWE session
        if (request.user.is_authenticated and 
            hasattr(request, 'session') and 
            'siwe_session_id' in request.session):
            
            try:
                siwe_session_id = request.session['siwe_session_id']
                siwe_session = SIWESession.objects.get(
                    session_id=siwe_session_id,
                    user=request.user
                )
                
                # Check if session is still valid
                if not siwe_session.is_valid():
                    # Session expired, log user out
                    self._logout_expired_session(request, siwe_session)
                
            except SIWESession.DoesNotExist:
                # SIWE session not found, log user out
                self._logout_missing_session(request)
            except Exception as e:
                logger.error(f"Error validating SIWE session: {e}")
        
        response = self.get_response(request)
        return response
    
    def _logout_expired_session(self, request, siwe_session: SIWESession) -> None:
        """Log out user with expired SIWE session."""
        try:
            from django.contrib.auth import logout
            
            # Mark session as expired
            siwe_session.mark_expired()
            
            # Clear session data
            request.session.pop('siwe_session_id', None)
            request.session.pop('wallet_address', None)
            
            # Log out user
            logout(request)
            
            logger.info(f"Logged out user {request.user.username} due to expired SIWE session")
            
        except Exception as e:
            logger.error(f"Error logging out expired session: {e}")
    
    def _logout_missing_session(self, request) -> None:
        """Log out user with missing SIWE session."""
        try:
            from django.contrib.auth import logout
            
            # Clear session data
            request.session.pop('siwe_session_id', None)
            request.session.pop('wallet_address', None)
            
            # Log out user
            logout(request)
            
            logger.info(f"Logged out user {request.user.username} due to missing SIWE session")
            
        except Exception as e:
            logger.error(f"Error logging out missing session: {e}")


def get_wallet_from_request(request) -> Optional[Wallet]:
    """
    Get the authenticated user's primary wallet from request.
    
    Args:
        request: Django request object
        
    Returns:
        Wallet instance if found, None otherwise
    """
    if not request.user.is_authenticated:
        return None
    
    try:
        return request.user.wallets.filter(
            status=Wallet.WalletStatus.CONNECTED
        ).order_by('-last_connected_at').first()
    except Exception:
        return None


def require_wallet_auth(view_func):
    """
    Decorator to require wallet authentication for views.
    
    Ensures the user is authenticated and has a connected wallet.
    Returns 401 if not authenticated or no wallet connected.
    """
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.http import JsonResponse
            return JsonResponse(
                {'error': 'Authentication required'}, 
                status=401
            )
        
        wallet = get_wallet_from_request(request)
        if not wallet:
            from django.http import JsonResponse
            return JsonResponse(
                {'error': 'No connected wallet found'}, 
                status=400
            )
        
        # Add wallet to request for view access
        request.wallet = wallet
        return view_func(request, *args, **kwargs)
    
    return wrapper


def require_trading_permission(view_func):
    """
    Decorator to require trading permissions for views.
    
    Ensures the user has a connected wallet with trading enabled.
    """
    @require_wallet_auth
    def wrapper(request, *args, **kwargs):
        if not request.wallet.is_trading_enabled:
            from django.http import JsonResponse
            return JsonResponse(
                {'error': 'Trading not enabled for this wallet'}, 
                status=403
            )
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


# Export authentication backend for Django settings
__all__ = [
    'SIWEAuthenticationBackend',
    'WalletPermissionMixin', 
    'SIWESessionMiddleware',
    'get_wallet_from_request',
    'require_wallet_auth',
    'require_trading_permission'
]