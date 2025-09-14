"""
Dashboard URL Configuration

URL patterns for the dashboard app including main dashboard,
mode selection, configuration panels, and API endpoints.

FIXED: Updated 'configuration' URL name to 'configuration_panel' to match 
       the reverse() calls in views.py and removed duplicate patterns.

File: dashboard/urls.py
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
    # FIXED: Changed name from 'configuration' to 'configuration_panel' 
    # to match the reverse() calls in configuration_summary view
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
    
    # =========================================================================
    # REAL-TIME DATA STREAMS (SERVER-SENT EVENTS)
    # WebSocket-like streaming endpoints for live dashboard updates
    # =========================================================================
    
    # Server-sent events endpoint for streaming real-time trading metrics
    path('metrics/stream/', views.metrics_stream, name='metrics_stream'),
    
    # =========================================================================
    # JSON API ENDPOINTS
    # RESTful API endpoints for AJAX calls and external integrations
    # =========================================================================
    
    # Get current trading engine status and health metrics
    path('api/engine-status/', views.api_engine_status, name='api_engine_status'),
    
    # Get performance metrics data for charts and dashboards
    path('api/metrics/', views.api_performance_metrics, name='api_metrics'),
    
    # Set active trading mode (Fast Lane vs Smart Lane)
    path('api/set-mode/', views.api_set_trading_mode, name='api_set_mode'),
    
    # =========================================================================
    # TRADING SESSION MANAGEMENT
    # Control active trading sessions and their lifecycle
    # =========================================================================
    
    # Start a new trading session with specified configuration
    path('session/start/', views.start_trading_session, name='start_session'),
    
    # Stop an active trading session by session ID
    path('session/stop/<uuid:session_id>/', views.stop_trading_session, name='stop_session'),
    
    # =========================================================================
    # DEVELOPMENT AND DEBUGGING ENDPOINTS
    # Testing and debugging tools - should be disabled in production
    # =========================================================================
    
    # Simple test endpoint for basic functionality verification
    path('test/', views.simple_test, name='simple_test'),
    
    # Template debugging tool - checks template loading and configuration
    path('debug-templates/', views.debug_templates, name='debug_templates'),
    
    # Minimal dashboard without template dependencies for emergency access
    path('minimal/', views.minimal_dashboard, name='minimal_dashboard'),
    
    # =========================================================================
    # COMMENTED DEBUG ENDPOINTS
    # Additional debug endpoints that can be enabled during development
    # =========================================================================
    
    # Debug mode selection page (uncomment if needed for testing)
    # path('debug-mode-selection/', views.debug_mode_selection, name='debug_mode_selection'),
    
    # Debug configuration panel (uncomment if needed for testing)
    # path('debug-config/<str:mode>/', views.debug_configuration_panel, name='debug_configuration'),
]