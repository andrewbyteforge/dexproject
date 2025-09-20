"""
Updated Dashboard URL Configuration with Wallet Integration

Enhanced URL patterns to include wallet management, fund allocation,
and trading control endpoints.

File: dexproject/dashboard/urls.py
"""

from django.urls import path
from . import views
from django.http import JsonResponse

app_name = 'dashboard'

urlpatterns = [
    # =========================================================================
    # MAIN DASHBOARD VIEWS
    # Core user interface pages for dashboard navigation and functionality
    # =========================================================================
    
    # Main dashboard views
    path('', views.dashboard_home, name='home'),
    path('mode-selection/', views.mode_selection, name='mode_selection'),
    path('config/<str:mode>/', views.configuration_panel, name='configuration_panel'),
    path('settings/', views.dashboard_settings, name='settings'),
    path('analytics/', views.dashboard_analytics, name='analytics'),
   
    # =========================================================================
    # REAL-TIME DATA STREAMS (SERVER-SENT EVENTS)
    # Enhanced with wallet data integration
    # =========================================================================
    
    # Server-sent events endpoint for streaming real-time trading metrics
    path('metrics/stream/', views.metrics_stream, name='metrics_stream'),
   
    # =========================================================================
    # CONFIGURATION MANAGEMENT API ENDPOINTS
    # RESTful endpoints for bot configuration CRUD operations
    # =========================================================================
    
    # Configuration CRUD operations
    path('api/configurations/', views.get_configurations, name='api_get_configurations'),
    path('api/configurations/save/', views.save_configuration, name='api_save_configuration'),
    path('api/configurations/<int:config_id>/', views.get_configuration, name='api_get_configuration'),
    path('api/configurations/<int:config_id>/delete/', views.delete_configuration, name='api_delete_configuration'),
    path('api/configurations/<int:config_id>/load/', views.load_configuration, name='api_load_configuration'),
    
    # Configuration management pages
    path('configs/', views.configuration_list, name='configuration_list'),
    path('configs/<int:config_id>/', views.configuration_summary, name='configuration_summary'),
    path('configs/<int:config_id>/delete/', views.delete_configuration, name='delete_configuration'),

    # =========================================================================
    # WALLET MANAGEMENT AND FUND ALLOCATION API ENDPOINTS
    # NEW: Wallet integration and fund allocation management
    # =========================================================================
    
    # Wallet status and information
    path('api/wallet/status/', views.api_wallet_status, name='api_wallet_status'),
    
    # Fund allocation management
    path('api/allocation/save/', views.api_save_allocation_settings, name='api_save_allocation_settings'),
    path('api/allocation/get/', views.api_get_allocation_settings, name='api_get_allocation_settings'),
    path('api/allocation/reset/', views.api_reset_allocation_settings, name='api_reset_allocation_settings'),
    
    # Trading control
    path('api/trading/start/', views.api_start_trading, name='api_start_trading'),
    path('api/trading/stop/', views.api_stop_trading, name='api_stop_trading'),
    path('api/trading/emergency-stop/', views.api_emergency_stop, name='api_emergency_stop'),
    path('api/trading/status/', views.api_trading_status, name='api_trading_status'),
    
    # =========================================================================
    # ENGINE AND PERFORMANCE API ENDPOINTS
    # Enhanced with wallet-aware metrics
    # =========================================================================
    
    # Engine status and control
    path('api/engine/status/', views.api_engine_status, name='api_engine_status'),
    path('api/engine/performance/', views.api_performance_metrics, name='api_performance_metrics'),
    path('api/engine/mode/<str:mode>/', views.api_set_trading_mode, name='api_set_trading_mode'),
    
    # =========================================================================
    # TRADING SESSION MANAGEMENT
    # Enhanced with wallet integration
    # =========================================================================
    
    # Session monitoring
    path('sessions/', views.session_list, name='session_list'),
    path('sessions/<int:session_id>/', views.session_detail, name='session_detail'),
    path('sessions/active/', views.active_sessions, name='active_sessions'),
    
    # =========================================================================
    # ANALYTICS AND REPORTING
    # Enhanced with wallet P&L tracking
    # =========================================================================
    
    # Analytics endpoints
    path('api/analytics/performance/', views.api_performance_analytics, name='api_performance_analytics'),
    path('api/analytics/pnl/', views.api_pnl_analytics, name='api_pnl_analytics'),
    path('api/analytics/risk/', views.api_risk_analytics, name='api_risk_analytics'),
    
    # =========================================================================
    # HEALTH AND MONITORING
    # System health with wallet service status
    # =========================================================================
    
    # Health check endpoint
    path('health/', views.health_check, name='health_check'),
    
    # =========================================================================
    # DEVELOPMENT AND DEBUG ENDPOINTS
    # Testing and debugging tools
    # =========================================================================
    
    # Debug endpoints
    path('debug/', views.debug_dashboard, name='debug_dashboard'),
    path('debug/templates/', views.debug_templates, name='debug_templates'),
    path('debug/engine/', views.engine_debug, name='engine_debug'),
    path('test/', views.simple_test, name='simple_test'),
    path('minimal/', views.minimal_dashboard, name='minimal_dashboard'),
]

# Error handlers for better user experience
handler404 = 'dashboard.views.custom_404'
handler500 = 'dashboard.views.custom_500'