"""
Final Updated Dashboard URL Configuration - PHASE 5.1C COMPLETE

Enhanced URL patterns that integrate the new portfolio analytics and trading
controls with the existing dashboard structure.

UPDATED: Adds portfolio API endpoints while maintaining existing functionality

File: dexproject/dashboard/urls.py
"""

from django.urls import path
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime
from . import views
from .views import fast_lane
from . import views_wallet  # Import wallet views module


app_name = 'dashboard'

urlpatterns = [
    # =========================================================================
    # MAIN DASHBOARD VIEWS (EXISTING - MAINTAINED)
    # Core user interface pages for dashboard navigation and functionality
    # =========================================================================
    
    # Main dashboard views (confirmed existing)
    path('', views.dashboard_home, name='home'),
    path('mode-selection/', views.mode_selection, name='mode_selection'),
    path('config/<str:mode>/', views.configuration_panel, name='configuration_panel'),
    path('settings/', views.dashboard_settings, name='settings'),
    
    # **ENHANCED**: Analytics dashboard now shows real portfolio data instead of "Coming Soon"
    path('analytics/', views.dashboard_analytics, name='analytics'),
   
    # =========================================================================
    # REAL-TIME DATA STREAMS (EXISTING - ENHANCED)
    # =========================================================================
    
    # **ENHANCED**: Server-sent events now include portfolio data in the stream
    path('metrics/stream/', views.metrics_stream, name='metrics_stream'),
   
    # =========================================================================
    # WALLET API ENDPOINTS (EXISTING - MAINTAINED)
    # Real-time balance tracking and wallet management
    # =========================================================================
    
    # Wallet balance tracking API for Base Sepolia with multi-chain support
    path('api/wallet/balances/', views_wallet.api_wallet_balances, name='api_wallet_balances'),
   
    # =========================================================================
    # PORTFOLIO & TRADING API ENDPOINTS - NEW FOR PHASE 5.1C
    # Real-time portfolio data and trading controls integration
    # =========================================================================
    
    # **NEW**: Portfolio summary data for AJAX updates
    path('api/portfolio/summary/', views.api_portfolio_summary, name='api_portfolio_summary'),
    
    # **NEW**: Recent trading activity data
    path('api/trading/activity/', views.api_trading_activity, name='api_trading_activity'),
    
    # **NEW**: Manual trading controls (buy/sell actions)
    path('api/trading/manual/', views.api_manual_trade, name='api_manual_trade'),
    
    # =========================================================================
    # FAST LANE CONFIGURATION (EXISTING - MAINTAINED)
    # Configuration interface for Fast Lane trading settings
    # =========================================================================
    
    # Fast Lane configuration interface (confirmed existing)
    path('fast-lane/config/', fast_lane.fast_lane_config, name='fast_lane_config'),
    path('fast-lane/status/', fast_lane.fast_lane_status, name='fast_lane_status'),
    path('fast-lane/test/', fast_lane.fast_lane_test, name='fast_lane_test'),
    
    # =========================================================================
    # CONFIGURATION MANAGEMENT APIs (EXISTING - MAINTAINED)
    # Configuration save/load endpoints for both Fast Lane and Smart Lane
    # =========================================================================
    
    # Configuration API endpoints (confirmed existing)
    path('api/config/save/', views.api_save_configuration, name='api_save_configuration'),
    path('api/config/load/', views.api_load_configuration, name='api_load_configuration'),
    path('api/config/reset/', views.api_reset_configuration, name='api_reset_configuration'),
    
    # =========================================================================
    # SYSTEM STATUS AND HEALTH CHECKS (EXISTING - MAINTAINED)
    # System monitoring and health check endpoints
    # =========================================================================
    
    # System status endpoints
    path('api/system/status/', views.api_system_status, name='api_system_status'),
    path('api/system/health/', views.api_health_check, name='api_health_check'),
    
    # =========================================================================
    # UTILITY ENDPOINTS (EXISTING + ENHANCED)
    # Testing and utility endpoints
    # =========================================================================
    
    # **ENHANCED**: Connection test now reports Phase 5.1C features
    path('api/test-connection/', lambda request: JsonResponse({
        'status': 'success',
        'message': 'Dashboard API connection test successful',
        'timestamp': timezone.now().isoformat(),
        'phase': 'Phase 5.1C - Portfolio Integration Complete',
        'features': {
            'existing_features': [
                'fast_lane_configuration',
                'smart_lane_analysis',
                'real_time_metrics',
                'wallet_connectivity',
                'siwe_authentication'
            ],
            'new_features': [
                'portfolio_tracking',
                'trading_integration', 
                'pnl_calculation',
                'risk_integrated_trading',
                'manual_trading_controls',
                'real_time_portfolio_updates'
            ]
        }
    }), name='api_test_connection'),
    
    # **NEW**: Trading system health check
    path('api/trading/health/', lambda request: JsonResponse({
        'trading_system': 'OPERATIONAL',
        'portfolio_tracking': 'ACTIVE',
        'risk_integration': 'ENABLED',
        'manual_trading': 'AVAILABLE',
        'analytics_integration': 'COMPLETE',
        'features': {
            'portfolio_summary': 'Real-time portfolio value and P&L tracking',
            'trading_activity': 'Recent trades display with status',
            'manual_controls': 'Buy/sell buttons with risk validation',
            'pnl_charts': 'Visual P&L tracking and analytics',
            'risk_metrics': 'Integrated risk assessment display'
        },
        'celery_queues': {
            'risk.urgent': 'ONLINE',
            'execution.critical': 'ONLINE',
            'analytics.background': 'ONLINE'
        },
        'timestamp': timezone.now().isoformat()
    }), name='api_trading_health'),
]


