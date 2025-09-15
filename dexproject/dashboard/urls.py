"""
Dashboard URL Configuration

URL patterns for the dashboard app - cleaned to only reference
functions that actually exist in views.py

File: dexproject/dashboard/urls.py
"""

from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    # =========================================================================
    # MAIN DASHBOARD PAGES
    # Core user interface pages for dashboard navigation and functionality
    # =========================================================================
    
    # Dashboard home page - main landing page with overview metrics
    path('', views.dashboard_home, name='home'),
    
    # Mode selection page - choose between Fast Lane and Smart Lane trading
    path('mode-selection/', views.mode_selection, name='mode_selection'),
    
    # Configuration panel for selected trading mode (Fast Lane or Smart Lane)
    path('config/<str:mode>/', views.configuration_panel, name='configuration_panel'),
    
    # =========================================================================
    # CONFIGURATION MANAGEMENT
    # URLs for managing saved bot configurations
    # =========================================================================
    
    # Configuration summary page - shows details of a saved configuration
    path('config/summary/<int:config_id>/', views.configuration_summary, name='configuration_summary'),
    
    # Configuration list page - shows all user's saved configurations
    path('configs/', views.configuration_list, name='configuration_list'),
    
    # Delete configuration with confirmation
    path('config/delete/<int:config_id>/', views.delete_configuration, name='delete_configuration'),
    
    # Clone configuration (exists in views.py based on diagnostic)
    path('config/clone/<int:config_id>/', views.clone_configuration, name='clone_configuration'),
    
    # =========================================================================
    # REAL-TIME DATA STREAMS (SERVER-SENT EVENTS)
    # Live streaming endpoints for real-time dashboard updates
    # =========================================================================
    
    # Server-sent events endpoint for streaming real-time trading metrics
    path('metrics/stream/', views.metrics_stream, name='metrics_stream'),
    
    # Combined stream endpoint
    path('combined/stream/', views.combined_stream, name='combined_stream'),
    
    # Smart Lane streaming endpoint
    path('smart-lane/stream/', views.smart_lane_stream, name='smart_lane_stream'),
    
    # =========================================================================
    # JSON API ENDPOINTS
    # RESTful API endpoints for AJAX calls and external integrations
    # =========================================================================
    
    # Get current trading engine status and health metrics
    path('api/engine-status/', views.api_engine_status, name='api_engine_status'),
    
    # Get performance metrics data for charts and dashboards
    path('api/performance-metrics/', views.api_performance_metrics, name='api_performance_metrics'),
    
    # Set active trading mode (Fast Lane vs Smart Lane)
    path('api/set-trading-mode/', views.api_set_trading_mode, name='api_set_trading_mode'),
    
    # Token analysis API endpoint (exists as api_analyze_token)
    path('api/analyze-token/', views.api_analyze_token, name='api_analyze_token'),
    
    # Smart Lane analysis API (correct function name: api_smart_lane_analysis)
    path('api/smart-lane/analysis/', views.api_smart_lane_analysis, name='api_smart_lane_analysis'),
    
    # =========================================================================
    # TRADING SESSION MANAGEMENT
    # Control active trading sessions and their lifecycle
    # =========================================================================
    
    # Start a new trading session
    path('session/start/', views.start_trading_session, name='start_trading_session'),
    
    # Stop an active trading session
    path('session/stop/<int:session_id>/', views.stop_trading_session, name='stop_trading_session'),
    
    # Session list view
    path('sessions/', views.session_list, name='session_list'),
    
    # Session summary view
    path('session/<int:session_id>/', views.session_summary, name='session_summary'),
    
    # Session monitoring view
    path('session/monitor/<int:session_id>/', views.session_monitor, name='session_monitor'),
    
    # =========================================================================
    # DEBUG AND TESTING ENDPOINTS
    # System monitoring and development testing endpoints
    # =========================================================================
    
    # Engine debug endpoint
    path('debug/engine/', views.engine_debug, name='engine_debug'),
    
    # Template debug view
    path('debug/templates/', views.debug_templates, name='debug_templates'),
    
    # Simple test view
    path('test/', views.simple_test, name='simple_test'),
    
    # Minimal dashboard view
    path('minimal/', views.minimal_dashboard, name='minimal_dashboard'),
]