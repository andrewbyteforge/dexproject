"""
Dashboard URL Configuration - COMPLETE WORKING VERSION

URL patterns that only reference confirmed existing view functions.
This will allow migrations and Django to run without import errors.

File: dexproject/dashboard/urls.py
"""

from django.urls import path
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime
from . import views


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
    # REAL-TIME DATA STREAMS (SERVER-SENT EVENTS)
    # =========================================================================
    
    # Server-sent events endpoint for streaming real-time trading metrics
    path('metrics/stream/', views.metrics_stream, name='metrics_stream'),
   
    # =========================================================================
    # CONFIGURATION MANAGEMENT API ENDPOINTS
    # RESTful endpoints for bot configuration CRUD operations
    # =========================================================================
    
    # Configuration management API endpoints (confirmed existing)
    path('api/save-configuration/', views.save_configuration, name='save_configuration'),
    path('api/load-configuration/', views.load_configuration, name='load_configuration'),
    path('api/delete-configuration/', views.delete_configuration, name='delete_configuration'),
    path('api/get-configurations/', views.get_configurations, name='get_configurations'),
   
    # =========================================================================
    # SESSION MANAGEMENT API ENDPOINTS
    # Trading session lifecycle management endpoints
    # =========================================================================
    
    # Session management API endpoints (confirmed existing)
    path('api/start-session/', views.start_session, name='start_session'),
    path('api/stop-session/', views.stop_session, name='stop_session'),
    path('api/session-status/', views.get_session_status, name='session_status'),
   
    # =========================================================================
    # PERFORMANCE METRICS API ENDPOINTS
    # Real-time trading performance and analytics endpoints
    # =========================================================================
    
    # Performance metrics API endpoint (confirmed existing)
    path('api/performance-metrics/', views.get_performance_metrics, name='performance_metrics'),
   
    # =========================================================================
    # TRADING MODE MANAGEMENT
    # Fast Lane vs Smart Lane mode switching endpoint
    # =========================================================================
    
    # Trading mode API (confirmed existing)
    path('api/set-mode/', views.api_set_trading_mode, name='api_set_trading_mode'),
   
    # =========================================================================
    # ENGINE AND SYSTEM API ENDPOINTS
    # =========================================================================
    
    # Engine status and performance (confirmed existing)
    # path('api/engine/status/', views.api_engine_status, name='api_engine_status'),
    # path('api/engine/performance/', views.api_performance_metrics, name='api_performance_metrics'),
    
    # =========================================================================
    # SMART LANE SPECIFIC URLS
    # Smart Lane dashboard, configuration, and analysis endpoints
    # =========================================================================
    
    # Smart Lane URLs (confirmed existing)
    path('smart-lane/', views.smart_lane_dashboard, name='smart_lane_dashboard'),
    path('smart-lane/demo/', views.smart_lane_demo, name='smart_lane_demo'),
    path('smart-lane/config/', views.smart_lane_config, name='smart_lane_config'),
    path('smart-lane/analyze/', views.smart_lane_analyze, name='smart_lane_analyze'),
    path('api/smart-lane/analyze/', views.api_smart_lane_analyze, name='api_smart_lane_analyze'),
    path('api/smart-lane/thought-log/<str:analysis_id>/', views.api_get_thought_log, name='api_get_thought_log'),
    
    # =========================================================================
    # CONFIGURATION MANAGEMENT PAGES
    # =========================================================================
    
    # Configuration management pages (confirmed existing)
    # path('configs/', views.configuration_list, name='configuration_list'),
    # path('configs/<int:config_id>/', views.configuration_summary, name='configuration_summary'),
    
    
    # =========================================================================
    # TEST AND DEBUG ENDPOINTS
    # =========================================================================
    
    # Test endpoint to verify Django is working
    path('test/', lambda request: JsonResponse({
        'status': 'ok', 
        'message': 'Django dashboard is working',
        'app': 'dashboard',
        'timestamp': str(datetime.now())
    }), name='test_api'),
    
    # Debug endpoints (if needed)
    # path('debug/', views.debug_dashboard, name='debug_dashboard'),
    # path('debug/templates/', views.debug_templates, name='debug_templates'),
    # path('minimal/', views.minimal_dashboard, name='minimal_dashboard'),




    # =========================================================================
    # HEALTH CHECK AND SYSTEM ENDPOINTS - CONFIRMED EXISTING
    # =========================================================================
    
    # System health endpoint that exists in views.py
    # path('health/', views.dashboard_health_check, name='health_check'),




















]