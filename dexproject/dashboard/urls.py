"""
Dashboard URL Configuration

Complete URL patterns for the dashboard app including main dashboard,
mode selection, configuration panels, and API endpoints.

COMPLETE VERSION: Now includes all Smart Lane functionality since 
the functions have been added to views.py

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
    
    # Dashboard home page - main landing page with dual-engine overview
    path('', views.dashboard_home, name='home'),
    
    # Mode selection page - choose between Fast Lane and Smart Lane trading
    path('mode-selection/', views.mode_selection, name='mode_selection'),
    
    # Configuration panel for selected trading mode (Fast Lane or Smart Lane)
    path('config/<str:mode>/', views.configuration_panel, name='configuration_panel'),
    
    # =========================================================================
    # CONFIGURATION MANAGEMENT
    # URLs for managing saved bot configurations (enhanced for dual-engine)
    # =========================================================================
    
    # Configuration summary page - shows details of a saved configuration
    path('config/summary/<int:config_id>/', views.configuration_summary, name='configuration_summary'),
    
    # Configuration list page - shows all user's saved configurations with filtering
    path('configs/', views.configuration_list, name='configuration_list'), 
    
    # Delete configuration with confirmation
    path('config/delete/<int:config_id>/', views.delete_configuration, name='delete_configuration'),
    
    # =========================================================================
    # SMART LANE SPECIFIC PAGES
    # URLs for Smart Lane analysis and demonstration features
    # =========================================================================
    
    # Smart Lane demonstration page with sample analysis
    path('smart-lane/demo/', views.smart_lane_demo, name='smart_lane_demo'),
    
    # =========================================================================
    # API ENDPOINTS
    # RESTful API endpoints for real-time data and engine control
    # =========================================================================
    
    # Engine status API - comprehensive status for both Fast Lane and Smart Lane
    path('api/engine-status/', views.api_engine_status, name='api_engine_status'),
    
    # Performance metrics API - metrics for both engines
    path('api/metrics/', views.api_performance_metrics, name='api_metrics'),
    
    # Trading mode control API - set mode for dual-engine system
    path('api/set-mode/', views.api_set_trading_mode, name='api_set_mode'),
    
    # Smart Lane analysis API - comprehensive token analysis
    path('api/smart-lane/analyze/', views.api_smart_lane_analyze, name='api_smart_lane_analyze'),
    
    # =========================================================================
    # REAL-TIME DATA STREAMS
    # Server-Sent Events endpoints for live dashboard updates
    # =========================================================================
    
    # Live dashboard feed - SSE stream with dual-engine metrics
    path('metrics/stream/', views.metrics_stream, name='metrics_stream'),
    
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
]