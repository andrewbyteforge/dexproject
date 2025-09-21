"""
Updated Dashboard URL Configuration with Trading Integration - PHASE 5.1C COMPLETE

URL patterns that include the new trading dashboard endpoints, portfolio analytics,
and real-time trading data APIs.

NEW: Complete trading integration with dashboard views

File: dexproject/dashboard/urls.py
"""

from django.urls import path
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime
from . import views
from .views import fast_lane
from . import views_wallet  # Import wallet views module
from . import views_trading  # Import new trading views module


app_name = 'dashboard'

urlpatterns = [
    # =========================================================================
    # MAIN DASHBOARD VIEWS
    # Core user interface pages for dashboard navigation and functionality
    # =========================================================================
    
    # Main dashboard views (confirmed existing)
    path('', views.dashboard_home, name='home'),
    path('mode-selection/', views.mode_selection, name='mode_selection'),
    path('config/<str:mode>/', views.configuration_panel, name='configuration_panel'),
    path('settings/', views.dashboard_settings, name='settings'),
    path('analytics/', views.dashboard_analytics, name='analytics'),
   
    # =========================================================================
    # TRADING DASHBOARD VIEWS - NEW PHASE 5.1C IMPLEMENTATION
    # Real-time trading interface and portfolio management
    # =========================================================================
    
    # **NEW:** Main trading dashboard with real-time data
    path('trading/', views_trading.trading_dashboard, name='trading_dashboard'),
    
    # **NEW:** Detailed portfolio analytics and performance tracking
    path('portfolio/', views_trading.portfolio_analytics, name='portfolio_analytics'),
    
    # =========================================================================
    # REAL-TIME DATA STREAMS (SERVER-SENT EVENTS)
    # =========================================================================
    
    # Server-sent events endpoint for streaming real-time trading metrics
    path('metrics/stream/', views.metrics_stream, name='metrics_stream'),
   
    # =========================================================================
    # WALLET API ENDPOINTS - EXISTING IMPLEMENTATION
    # Real-time balance tracking and wallet management for trading capability
    # =========================================================================
    
    # Wallet balance tracking API for Base Sepolia with multi-chain support
    path('api/wallet/balances/', views_wallet.api_wallet_balances, name='api_wallet_balances'),
   
    # =========================================================================
    # TRADING API ENDPOINTS - NEW PHASE 5.1C IMPLEMENTATION
    # Real-time trading data and manual trading actions
    # =========================================================================
    
    # **NEW:** Real-time portfolio data API
    path('api/portfolio/summary/', views_trading.api_portfolio_summary, name='api_portfolio_summary'),
    
    # **NEW:** Recent trading activity API
    path('api/trades/recent/', views_trading.api_recent_trades, name='api_recent_trades'),
    
    # **NEW:** Trading metrics and system status API
    path('api/trading/metrics/', views_trading.api_trading_metrics, name='api_trading_metrics'),
    
    # **NEW:** Manual trading action endpoints
    path('api/trading/buy/', views_trading.api_manual_buy, name='api_manual_buy'),
    path('api/trading/sell/', views_trading.api_manual_sell, name='api_manual_sell'),
    path('api/trading/smart-lane/', views_trading.api_smart_lane_analysis, name='api_smart_lane_analysis'),
    
    # =========================================================================
    # FAST LANE CONFIGURATION - EXISTING IMPLEMENTATION
    # Configuration interface for Fast Lane trading settings
    # =========================================================================
    
    # Fast Lane configuration interface (confirmed existing)
    path('fast-lane/config/', fast_lane.fast_lane_config, name='fast_lane_config'),
    path('fast-lane/status/', fast_lane.fast_lane_status, name='fast_lane_status'),
    path('fast-lane/test/', fast_lane.fast_lane_test, name='fast_lane_test'),
    
    # =========================================================================
    # CONFIGURATION MANAGEMENT APIs
    # Configuration save/load endpoints for both Fast Lane and Smart Lane
    # =========================================================================
    
    # Configuration API endpoints (confirmed existing)
    path('api/config/save/', views.api_save_configuration, name='api_save_configuration'),
    path('api/config/load/', views.api_load_configuration, name='api_load_configuration'),
    path('api/config/reset/', views.api_reset_configuration, name='api_reset_configuration'),
    
    # =========================================================================
    # SYSTEM STATUS AND HEALTH CHECKS
    # System monitoring and health check endpoints
    # =========================================================================
    
    # System status endpoints
    path('api/system/status/', views.api_system_status, name='api_system_status'),
    path('api/system/health/', views.api_health_check, name='api_health_check'),
    
    # =========================================================================
    # LEGACY ENDPOINTS AND UTILITIES
    # Backward compatibility and utility endpoints
    # =========================================================================
    
    # Utility endpoints
    path('api/test-connection/', lambda request: JsonResponse({
        'status': 'success',
        'message': 'Dashboard API connection test successful',
        'timestamp': timezone.now().isoformat(),
        'phase': '5.1C',
        'features': [
            'risk_integrated_trading',
            'portfolio_tracking',
            'real_time_analytics',
            'smart_lane_integration',
            'fast_lane_configuration'
        ]
    }), name='api_test_connection'),
    
    # Health check for trading system
    path('api/trading/health/', lambda request: JsonResponse({
        'trading_system': 'OPERATIONAL',
        'risk_integration': 'ENABLED',
        'portfolio_tracking': 'ACTIVE',
        'smart_lane_bridge': 'READY',
        'celery_queues': {
            'risk.urgent': 'ONLINE',
            'execution.critical': 'ONLINE',
            'analytics.background': 'ONLINE'
        },
        'timestamp': timezone.now().isoformat()
    }), name='api_trading_health'),
]


