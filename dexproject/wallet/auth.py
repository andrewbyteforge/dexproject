"""
SIWE Authentication Backend and Middleware

Custom Django authentication backend and middleware for Sign-In with Ethereum (SIWE).
Integrates wallet-based authentication with Django's authentication system
while maintaining compatibility with existing Django auth.

Phase 5.1B Implementation:
- SIWE session validation
- Automatic user provisioning
- Session management integration
- Security event logging
- SIWE token authentication for API

File: dexproject/wallet/auth.py
"""

import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime

from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.sessions.models import Session
from django.http import HttpRequest
from django.utils.deprecation import MiddlewareMixin

# REST Framework imports
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import status

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
                siwe_session.status = SIWESession.SessionStatus.EXPIRED
                siwe_session.save(update_fields=['status'])
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
            user_id: User ID to retrieve
            
        Returns:
            User instance if found, None otherwise
        """
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
    
    def _get_or_create_user_for_wallet(self, wallet_address: str) -> User:
        """Get or create a Django user for the wallet address."""
        username = f"wallet_{wallet_address.lower()}"
        
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            # Create new user
            user = User.objects.create_user(
                username=username,
                email='',  # No email required for wallet users
                first_name='Wallet',
                last_name=wallet_address[:10] + '...'
            )
            logger.info(f"Created new user for wallet {wallet_address}")
            return user
    
    def _update_session_metadata(self, siwe_session: SIWESession, request: HttpRequest) -> None:
        """Update SIWE session with request metadata."""
        try:
            from .views import get_client_ip, get_user_agent
            
            # Update IP and user agent if they've changed
            current_ip = get_client_ip(request)
            current_ua = get_user_agent(request)
            
            if current_ip != siwe_session.ip_address or current_ua != siwe_session.user_agent:
                siwe_session.ip_address = current_ip
                siwe_session.user_agent = current_ua
                siwe_session.save(update_fields=['ip_address', 'user_agent'])
                
        except Exception as e:
            logger.error(f"Error updating session metadata: {e}")


class SIWESessionMiddleware(MiddlewareMixin):
    """
    Middleware to validate SIWE sessions on each request.
    
    Ensures that wallet-authenticated users maintain valid SIWE sessions
    and automatically logs out users with expired sessions. Also handles
    session rotation after SIWE authentication.
    """
    
    def __init__(self, get_response):
        """Initialize middleware."""
        super().__init__(get_response)
        self.get_response = get_response
    
    def process_request(self, request):
        """Process request and validate SIWE session if present."""
        # Skip validation for SIWE auth endpoints to avoid circular dependencies
        if self._is_siwe_auth_endpoint(request):
            return None
        
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
                else:
                    # Session is valid, update last activity
                    self._update_session_activity(siwe_session)
                
            except SIWESession.DoesNotExist:
                # SIWE session not found, log user out
                self._logout_missing_session(request)
            except Exception as e:
                logger.error(f"Error validating SIWE session: {e}")
        
        return None
    
    def _is_siwe_auth_endpoint(self, request: HttpRequest) -> bool:
        """Check if request is to a SIWE authentication endpoint."""
        siwe_endpoints = [
            '/api/wallet/auth/siwe/generate/',
            '/api/wallet/auth/siwe/authenticate/',
            '/api/wallet/auth/logout/',
        ]
        return request.path in siwe_endpoints
    
    def _update_session_activity(self, siwe_session: SIWESession) -> None:
        """Update session last activity timestamp."""
        try:
            # Update timestamp (handled by auto_now on model)
            siwe_session.save(update_fields=['updated_at'])
        except Exception as e:
            logger.error(f"Error updating session activity: {e}")
    
    def _logout_expired_session(self, request, siwe_session: SIWESession) -> None:
        """Log out user with expired SIWE session."""
        try:
            from django.contrib.auth import logout
            
            # Mark session as expired
            siwe_session.status = SIWESession.SessionStatus.EXPIRED
            siwe_session.save(update_fields=['status'])
            
            # Clear session data
            self._clear_siwe_session_data(request)
            
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
            self._clear_siwe_session_data(request)
            
            # Log out user
            logout(request)
            
            logger.info(f"Logged out user {request.user.username} due to missing SIWE session")
            
        except Exception as e:
            logger.error(f"Error logging out missing session: {e}")
    
    def _clear_siwe_session_data(self, request) -> None:
        """Clear SIWE-related session data."""
        try:
            siwe_keys = ['siwe_session_id', 'wallet_address', 'chain_id', 'siwe_nonce']
            for key in siwe_keys:
                request.session.pop(key, None)
        except Exception as e:
            logger.error(f"Error clearing SIWE session data: {e}")

    @staticmethod
    def rotate_session_on_siwe_login(request, siwe_session: SIWESession) -> None:
        """
        Rotate Django session after successful SIWE authentication.
        
        This is a security best practice to prevent session fixation attacks.
        Should be called from views after successful SIWE authentication.
        """
        try:
            # Store SIWE session data before rotation
            old_session_data = {
                'siwe_session_id': str(siwe_session.session_id),
                'wallet_address': siwe_session.wallet_address,
                'chain_id': siwe_session.chain_id,
            }
            
            # Rotate session (creates new session key)
            request.session.cycle_key()
            
            # Restore SIWE session data
            for key, value in old_session_data.items():
                request.session[key] = value
            
            # Update Django session key in SIWE session
            siwe_session.django_session_key = request.session.session_key
            siwe_session.save(update_fields=['django_session_key'])
            
            logger.info(f"Session rotated for SIWE authentication: {siwe_session.wallet_address}")
            
        except Exception as e:
            logger.error(f"Error rotating session: {e}")


class SIWETokenAuthentication(BaseAuthentication):
    """
    Token authentication for SIWE sessions in DRF API endpoints.
    
    Supports authentication via:
    1. Session-based (for web interface)
    2. SIWE session ID in headers (for API clients)
    """
    
    def authenticate(self, request) -> Optional[Tuple[User, SIWESession]]:
        """
        Authenticate request using SIWE session.
        
        Args:
            request: DRF request object
            
        Returns:
            Tuple of (user, siwe_session) if authenticated, None otherwise
        """
        # Try session-based authentication first
        siwe_session_id = self._get_siwe_session_id_from_session(request)
        
        # Fall back to header-based authentication
        if not siwe_session_id:
            siwe_session_id = self._get_siwe_session_id_from_header(request)
        
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
                logger.info(f"SIWE token authentication failed: session {siwe_session_id} expired")
                siwe_session.status = SIWESession.SessionStatus.EXPIRED
                siwe_session.save(update_fields=['status'])
                raise AuthenticationFailed('SIWE session expired')
            
            # Get user
            user = siwe_session.user
            if not user or not user.is_active:
                logger.warning(f"SIWE token authentication failed: invalid user for session {siwe_session_id}")
                raise AuthenticationFailed('Invalid user')
            
            logger.info(f"SIWE token authentication successful for user {user.username}")
            return (user, siwe_session)
            
        except SIWESession.DoesNotExist:
            logger.info(f"SIWE token authentication failed: session {siwe_session_id} not found")
            raise AuthenticationFailed('Invalid SIWE session')
        except Exception as e:
            logger.error(f"Error during SIWE token authentication: {e}")
            raise AuthenticationFailed('Authentication failed')
    
    def _get_siwe_session_id_from_session(self, request) -> Optional[str]:
        """Get SIWE session ID from Django session."""
        try:
            if hasattr(request, 'session') and 'siwe_session_id' in request.session:
                return request.session['siwe_session_id']
        except Exception:
            pass
        return None
    
    def _get_siwe_session_id_from_header(self, request) -> Optional[str]:
        """Get SIWE session ID from request headers."""
        try:
            # Check Authorization header: "SIWE <session_id>"
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('SIWE '):
                return auth_header[5:]  # Remove "SIWE " prefix
            
            # Check custom header
            return request.META.get('HTTP_X_SIWE_SESSION_ID')
        except Exception:
            pass
        return None

    def authenticate_header(self, request) -> str:
        """Return authentication header for 401 responses."""
        return 'SIWE'


class WalletPermissionMixin:
    """
    Mixin class for wallet-related permission checks.
    
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
        # Try to get wallet address from session
        wallet_address = request.session.get('wallet_address')
        if wallet_address:
            return request.user.wallets.get(
                address=wallet_address,
                status=Wallet.WalletStatus.CONNECTED
            )
        
        # Fall back to primary wallet
        permission_mixin = WalletPermissionMixin()
        return permission_mixin.get_user_primary_wallet(request.user)
        
    except Exception as e:
        logger.error(f"Error getting wallet from request: {e}")
        return None


def require_wallet_permission(wallet_address: str):
    """
    Decorator to require wallet permission for views.
    
    Args:
        wallet_address: Required wallet address (can be dynamic)
        
    Returns:
        Decorated view function
    """
    def decorator(view_func):
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.decorators import login_required
                return login_required(view_func)(request, *args, **kwargs)
            
            # Extract wallet address from kwargs if dynamic
            address = wallet_address
            if wallet_address.startswith('{') and wallet_address.endswith('}'):
                param_name = wallet_address[1:-1]  # Remove {}
                address = kwargs.get(param_name)
            
            if not address:
                from django.http import HttpResponseForbidden
                return HttpResponseForbidden("Wallet address required")
            
            permission_mixin = WalletPermissionMixin()
            if not permission_mixin.has_wallet_permission(request.user, address):
                from django.http import HttpResponseForbidden
                return HttpResponseForbidden("Wallet access denied")
            
            return view_func(request, *args, **kwargs)
        
        return wrapped_view
    return decorator


def require_trading_permission(view_func):
    """
    Decorator to require trading permission for views.
    
    Args:
        view_func: View function to decorate
        
    Returns:
        Decorated view function
    """
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.decorators import login_required
            return login_required(view_func)(request, *args, **kwargs)
        
        permission_mixin = WalletPermissionMixin()
        if not permission_mixin.has_trading_permission(request.user):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Trading permission required")
        
        return view_func(request, *args, **kwargs)
    
    return wrapped_view


# Export important classes and functions for easy importing
__all__ = [
    'SIWEAuthenticationBackend',
    'SIWESessionMiddleware', 
    'SIWETokenAuthentication',
    'WalletPermissionMixin',
    'get_wallet_from_request',
    'require_wallet_permission',
    'require_trading_permission',
]