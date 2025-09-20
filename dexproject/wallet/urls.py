"""
Wallet App URL Configuration

API endpoints for wallet connection, SIWE authentication, balance management,
and wallet operations. Implements secure routing with proper authentication
and comprehensive error handling.

Phase 5.1B Implementation:
- SIWE authentication endpoints
- Wallet management and configuration
- Balance and transaction endpoints
- Security and audit endpoints
- Health monitoring and utilities

File: dexproject/wallet/urls.py
"""

from django.urls import path
from . import views

app_name = 'wallet'

urlpatterns = [
    # =========================================================================
    # SIWE AUTHENTICATION ENDPOINTS
    # Core authentication flow for wallet-based login
    # =========================================================================
    
    # Generate SIWE message for signing
    path('auth/siwe/generate/', views.generate_siwe_message, name='generate_siwe_message'),
    
    # Authenticate wallet with SIWE signature
    path('auth/siwe/authenticate/', views.authenticate_wallet, name='authenticate_wallet'),
    
    # Logout and disconnect wallet
    path('auth/logout/', views.logout_wallet, name='logout_wallet'),
    
    # =========================================================================
    # WALLET MANAGEMENT ENDPOINTS
    # Wallet information, settings, and configuration management
    # =========================================================================
    
    # Get current wallet information and summary
    path('info/', views.get_wallet_info, name='get_wallet_info'),
    
    # Update wallet settings and preferences
    path('settings/', views.update_wallet_settings, name='update_wallet_settings'),
    
    # =========================================================================
    # BALANCE AND PORTFOLIO ENDPOINTS
    # Real-time balance tracking and portfolio management
    # =========================================================================
    
    # Get wallet balances across all supported chains
    path('balances/', views.get_wallet_balances, name='get_wallet_balances'),
    
    # =========================================================================
    # TRANSACTION MONITORING ENDPOINTS
    # Transaction history and monitoring
    # =========================================================================
    
    # Get wallet transaction history
    path('transactions/', views.get_wallet_transactions, name='get_wallet_transactions'),
    
    # =========================================================================
    # SECURITY AND AUDIT ENDPOINTS
    # Security monitoring, session management, and audit logging
    # =========================================================================
    
    # Get wallet activity log for security monitoring
    path('activity/', views.get_wallet_activity, name='get_wallet_activity'),
    
    # Get active SIWE sessions
    path('sessions/', views.get_siwe_sessions, name='get_siwe_sessions'),
    
    # Revoke specific SIWE session
    path('sessions/revoke/', views.revoke_siwe_session, name='revoke_siwe_session'),
    
    # =========================================================================
    # UTILITY AND HEALTH ENDPOINTS
    # System information and health monitoring
    # =========================================================================
    
    # Get supported blockchain networks
    path('chains/', views.get_supported_chains, name='get_supported_chains'),
    
    # Health check for wallet service
    path('health/', views.health_check, name='health_check'),
]

"""
API Endpoint Documentation:

AUTHENTICATION FLOW:
1. GET /api/wallet/chains/ - Get supported networks
2. POST /api/wallet/auth/siwe/generate/ - Generate SIWE message
3. POST /api/wallet/auth/siwe/authenticate/ - Authenticate with signature
4. Authenticated endpoints available
5. POST /api/wallet/auth/logout/ - Disconnect wallet

WALLET MANAGEMENT:
- GET /api/wallet/info/ - Get wallet summary
- POST /api/wallet/settings/ - Update wallet preferences
- GET /api/wallet/balances/ - Get current balances
- GET /api/wallet/balances/?refresh=true - Force refresh from blockchain

TRANSACTION MONITORING:
- GET /api/wallet/transactions/ - Get transaction history
- GET /api/wallet/transactions/?chain_id=1 - Filter by chain
- GET /api/wallet/transactions/?status=CONFIRMED - Filter by status

SECURITY MONITORING:
- GET /api/wallet/activity/ - Get activity log
- GET /api/wallet/sessions/ - Get active sessions
- POST /api/wallet/sessions/revoke/ - Revoke session

SYSTEM HEALTH:
- GET /api/wallet/health/ - Service health check

AUTHENTICATION REQUIREMENTS:
- /auth/siwe/generate/ - No authentication required
- /auth/siwe/authenticate/ - No authentication required  
- /chains/ - No authentication required
- All other endpoints - Authentication required

ERROR HANDLING:
All endpoints return consistent error responses:
{
    "error": "Error description",
    "details": "Additional details (optional)"
}

Success responses vary by endpoint but follow REST conventions:
- GET requests return data objects
- POST requests return success confirmations
- All responses include appropriate HTTP status codes

RATE LIMITING:
- Anonymous endpoints: 100/hour
- Authenticated endpoints: 1000/hour
- Per Django REST Framework configuration

CORS POLICY:
- Allows requests from configured frontend domains
- Supports preflight requests for complex operations
- Configured in Django settings.py
"""