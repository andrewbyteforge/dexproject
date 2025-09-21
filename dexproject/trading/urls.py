"""
Trading App URL Configuration - Phase 5.1C Complete Implementation

Complete URL routing for trading API endpoints, providing REST-ful access
to all trading functionality including execution, position management,
and portfolio tracking.

File: dexproject/trading/urls.py
"""

from django.urls import path
from . import views

app_name = 'trading'

urlpatterns = [
    # =========================================================================
    # TRADE EXECUTION ENDPOINTS
    # Real-time buy/sell order execution with DEX integration
    # =========================================================================
    
    # Execute buy order for tokens
    path('buy/', views.api_execute_buy_order, name='api_execute_buy_order'),
    
    # Execute sell order for tokens  
    path('sell/', views.api_execute_sell_order, name='api_execute_sell_order'),
    
    # =========================================================================
    # POSITION MANAGEMENT ENDPOINTS
    # Real-time position tracking and management
    # =========================================================================
    
    # Get user's current trading positions
    path('positions/', views.api_get_positions, name='api_get_positions'),
    
    # Close a trading position
    path('positions/close/', views.api_close_position, name='api_close_position'),
    
    # =========================================================================
    # TRADE HISTORY AND PORTFOLIO ENDPOINTS
    # Historical data and portfolio analysis
    # =========================================================================
    
    # Get trading history with filtering
    path('history/', views.api_get_trade_history, name='api_get_trade_history'),
    
    # Get portfolio summary with real-time data
    path('portfolio/', views.api_get_portfolio_summary, name='api_get_portfolio_summary'),
    
    # =========================================================================
    # TRADING SESSION MANAGEMENT
    # Session lifecycle and configuration management
    # =========================================================================
    
    # Start a new trading session
    path('session/start/', views.api_start_trading_session, name='api_start_trading_session'),
    
    # Stop active trading session
    path('session/stop/', views.api_stop_trading_session, name='api_stop_trading_session'),
    
    # Get current session status
    path('session/status/', views.api_get_trading_session_status, name='api_get_trading_session_status'),
    
    # =========================================================================
    # UTILITY AND INFORMATION ENDPOINTS
    # Supporting data and system information
    # =========================================================================
    
    # Get list of supported tokens
    path('tokens/', views.api_get_supported_tokens, name='api_get_supported_tokens'),
    
    # Trading API health check
    path('health/', views.api_health_check, name='api_health_check'),
]

"""
API Endpoint Documentation:

TRADE EXECUTION:
POST /api/trading/buy/
- Execute buy orders with real DEX integration
- Requires: token_address, amount_eth
- Optional: slippage_tolerance, gas_price_gwei, strategy_id, chain_id
- Returns: trade_id, task_id, execution status

POST /api/trading/sell/
- Execute sell orders with real DEX integration  
- Requires: token_address, token_amount
- Optional: slippage_tolerance, gas_price_gwei, chain_id
- Returns: trade_id, task_id, execution status

POSITION MANAGEMENT:
GET /api/trading/positions/
- Get current positions with real-time P&L
- Query params: status, chain_id, limit, offset
- Returns: positions list with current values and unrealized P&L

POST /api/trading/positions/close/
- Close positions by selling tokens
- Requires: position_id
- Optional: percentage (default 100%), slippage_tolerance, gas_price_gwei
- Returns: position closure execution status

PORTFOLIO AND HISTORY:
GET /api/trading/history/
- Get trading history with filtering
- Query params: status, trade_type, chain_id, limit, offset, date_from, date_to
- Returns: trades list with execution details and summary statistics

GET /api/trading/portfolio/
- Get portfolio summary with real-time data
- Returns: total value, P&L, positions summary, trades summary, recent activity

TRADING SESSIONS:
POST /api/trading/session/start/
- Start new trading session
- Optional: strategy_id, max_position_size_usd, risk_tolerance, auto_execution
- Returns: session configuration and status

POST /api/trading/session/stop/
- Stop active trading session
- Returns: session termination confirmation

GET /api/trading/session/status/
- Get current session status
- Returns: active session details or null if no session

UTILITY ENDPOINTS:
GET /api/trading/tokens/
- Get supported tokens for trading
- Query params: chain_id, search, limit
- Returns: tokens list with metadata and trading pair information

GET /api/trading/health/
- API health check
- Returns: service status and health metrics

AUTHENTICATION:
- All endpoints except /health/ and /tokens/ require user authentication
- Trading execution endpoints require active SIWE wallet session
- Position and portfolio endpoints validate wallet ownership

ERROR HANDLING:
All endpoints return consistent error responses:
{
    "success": false,
    "error": "Error description",
    "code": "ERROR_CODE",
    "details": "Additional details (optional)"
}

Success responses follow REST conventions with appropriate HTTP status codes.

RATE LIMITING:
- Execution endpoints: 10 requests/minute per user
- Read endpoints: 100 requests/minute per user
- Health endpoint: No rate limiting

CORS POLICY:
- Configured in Django settings for frontend integration
- Supports preflight requests for complex operations

INTEGRATION:
These endpoints integrate with:
- DEX Router Service (trading/services/dex_router_service.py)
- Portfolio Service (trading/services/portfolio_service.py)
- Celery Tasks (trading/tasks.py)
- Trading Models (trading/models.py)
- Wallet Authentication (wallet/auth.py)
"""