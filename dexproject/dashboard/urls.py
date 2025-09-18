"""
Dashboard URL Configuration

Defines URL patterns for the dashboard application including trading sessions,
configuration management, and real-time updates.

FIXED: Updated URL names to match template expectations and added missing endpoints.

Path: dashboard/urls.py
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
    # FIXED: Added missing metrics stream endpoint
    # =========================================================================
    
    # Server-sent events endpoint for streaming real-time trading metrics
    path('metrics/stream/', views.metrics_stream, name='metrics_stream'),
   
    # =========================================================================
    # CONFIGURATION MANAGEMENT API ENDPOINTS
    # RESTful endpoints for bot configuration CRUD operations
    # =========================================================================
    
    # Configuration management API endpoints
    path('api/save-configuration/', views.save_configuration, name='save_configuration'),
    path('api/load-configuration/', views.load_configuration, name='load_configuration'),
    path('api/delete-configuration/', views.delete_configuration, name='delete_configuration'),
    path('api/get-configurations/', views.get_configurations, name='get_configurations'),
   
    # =========================================================================
    # SESSION MANAGEMENT API ENDPOINTS
    # Trading session lifecycle management endpoints
    # =========================================================================
    
    # Session management API endpoints
    path('api/start-session/', views.start_session, name='start_session'),
    path('api/stop-session/', views.stop_session, name='stop_session'),
    path('api/session-status/', views.get_session_status, name='session_status'),
   
    # =========================================================================
    # PERFORMANCE METRICS API ENDPOINTS
    # Real-time trading performance and analytics endpoints
    # =========================================================================
    
    # Performance metrics API endpoint
    path('api/performance-metrics/', views.get_performance_metrics, name='performance_metrics'),
   
    # =========================================================================
    # TRADING MODE MANAGEMENT
    # Fast Lane vs Smart Lane mode switching endpoint
    # FIXED: Updated URL name to match template expectations
    # =========================================================================
    
    # FIXED: Changed name from 'api_set_mode' to 'api_set_trading_mode' to match template
    # Template was looking for {% url 'dashboard:api_set_trading_mode' %}
    path('api/set-mode/', views.api_set_trading_mode, name='api_set_trading_mode'),
   
    # =========================================================================
    # SMART LANE SPECIFIC URLS
    # Smart Lane dashboard, configuration, and analysis endpoints
    # =========================================================================
    
    # Smart Lane URLs
    path('smart-lane/', views.smart_lane_dashboard, name='smart_lane_dashboard'),
    path('smart-lane/demo/', views.smart_lane_demo, name='smart_lane_demo'),
    path('smart-lane/config/', views.smart_lane_config, name='smart_lane_config'),
    path('smart-lane/analyze/', views.smart_lane_analyze, name='smart_lane_analyze'),
    path('api/smart-lane/analyze/', views.api_smart_lane_analyze, name='api_smart_lane_analyze'),
    path('api/smart-lane/thought-log/<str:analysis_id>/', views.api_get_thought_log, name='api_get_thought_log'),
    # Add this temporary URL pattern to test
path('api/test/', lambda request: JsonResponse({'test': 'works'}), name='test_api'),
]