"""
SIWE Authentication Backend and Middleware

Custom Django authentication backend and middleware for Sign-In with Ethereum (SIWE).
Integrates wallet-based authentication with Django's authentication system
while maintaining compatibility with existing Django auth.

Phase 5.1C Implementation:
- SIWE session validation
- Automatic user provisioning
- Session management integration
- Security event logging
- SIWE token authentication for API (FIXED - Added missing SIWEAuthentication class)

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


class SIWEAuthentication(BaseAuthentication):
    """
    REST Framework authentication class for SIWE sessions.
    
    This class handles SIWE-based authentication for API requests,
    supporting both session-based and header-based authentication.
    """
    
    def authenticate(self, request) -> Optional[Tuple[User, str]]:
        """
        Authenticate the request using SIWE session.
        
        Args:
            request: DRF request object
            
        Returns:
            Tuple of (user, auth_token) if successful, None otherwise
        """
        try:
            # Try to get SIWE session ID from various sources
            siwe_session_id = self._get_siwe_session_id(request)
            
            if not siwe_session_id:
                return None
            
            # Get SIWE session
            siwe_session = SIWESession.objects.get(
                session_id=siwe_session_id,
                status=SIWESession.SessionStatus.VERIFIED
            )
            
            # Validate session is still valid
            if not siwe_session.is_valid():
                logger.info(f"SIWE session {siwe_session_id} expired during authentication")
                siwe_session.status = SIWESession.SessionStatus.EXPIRED
                siwe_session.save(update_fields=['status'])
                raise AuthenticationFailed('SIWE session has expired')
            
            # Get user
            user = siwe_session.user
            if not user or not user.is_active:
                raise AuthenticationFailed('User account is disabled')
            
            # Update session activity
            self._update_session_activity(siwe_session)
            
            logger.debug(f"SIWE API authentication successful for user {user.username}")
            return (user, siwe_session_id)
            
        except SIWESession.DoesNotExist:
            return None
        except AuthenticationFailed:
            raise
        except Exception as e:
            logger.error(f"Error during SIWE API authentication: {e}")
            raise AuthenticationFailed('Authentication failed')
    
    def _get_siwe_session_id(self, request) -> Optional[str]:
        """
        Extract SIWE session ID from request.
        
        Checks multiple sources:
        1. Authorization header: "SIWE <session_id>"
        2. Custom header: X-SIWE-Session-ID
        3. Django session (for web requests)
        """
        # Try Authorization header first
        siwe_session_id = self._get_siwe_session_id_from_header(request)
        if siwe_session_id:
            return siwe_session_id
        
        # Try Django session for web requests
        return self._get_siwe_session_id_from_session(request)
    
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
    
    def _update_session_activity(self, siwe_session: SIWESession) -> None:
        """Update session last activity timestamp."""
        try:
            # Update timestamp (handled by auto_now on model)
            siwe_session.save(update_fields=['updated_at'])
        except Exception as e:
            logger.error(f"Error updating session activity: {e}")

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
            Primary wallet if found, None otherwise
        """
        try:
            return user.wallets.filter(
                status=Wallet.WalletStatus.CONNECTED
            ).first()
        except Exception:
            return None


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
            
            logger.info(f"Logging out user due to expired SIWE session: {siwe_session.session_id}")
            
            # Update session status
            siwe_session.status = SIWESession.SessionStatus.EXPIRED
            siwe_session.save(update_fields=['status'])
            
            # Clear Django session
            if hasattr(request, 'session'):
                request.session.flush()
            
            # Log user out
            logout(request)
            
        except Exception as e:
            logger.error(f"Error logging out expired session: {e}")
    
    def _logout_missing_session(self, request) -> None:
        """Log out user with missing SIWE session."""
        try:
            from django.contrib.auth import logout
            
            logger.warning("Logging out user due to missing SIWE session")
            
            # Clear Django session
            if hasattr(request, 'session'):
                request.session.flush()
            
            # Log user out
            logout(request)
            
        except Exception as e:
            logger.error(f"Error logging out missing session: {e}")