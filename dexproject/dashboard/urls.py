"""
Dashboard URL Configuration

Defines URL patterns for the dashboard application including trading sessions,
configuration management, and real-time updates.

Path: dashboard/urls.py
"""

from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    # Main dashboard views
    path('', views.dashboard_home, name='home'),
    path('mode-selection/', views.mode_selection, name='mode_selection'),
    path('config/<str:mode>/', views.configuration_panel, name='configuration_panel'),
    path('settings/', views.dashboard_settings, name='settings'),
    path('analytics/', views.dashboard_analytics, name='analytics'),
    
    # Configuration management API endpoints
    path('api/save-configuration/', views.save_configuration, name='save_configuration'),
    path('api/load-configuration/', views.load_configuration, name='load_configuration'),
    path('api/delete-configuration/', views.delete_configuration, name='delete_configuration'),
    path('api/get-configurations/', views.get_configurations, name='get_configurations'),
    
    # Session management API endpoints
    path('api/start-session/', views.start_session, name='start_session'),
    path('api/stop-session/', views.stop_session, name='stop_session'),
    path('api/session-status/', views.get_session_status, name='session_status'),
    
    # Performance metrics API endpoint
    path('api/performance-metrics/', views.get_performance_metrics, name='performance_metrics'),
    
    # Smart Lane URLs
    path('smart-lane/', views.smart_lane_dashboard, name='smart_lane_dashboard'),
    path('smart-lane/demo/', views.smart_lane_demo, name='smart_lane_demo'),
    path('smart-lane/config/', views.smart_lane_config, name='smart_lane_config'),
    path('smart-lane/analyze/', views.smart_lane_analyze, name='smart_lane_analyze'),
    path('api/smart-lane/analyze/', views.api_smart_lane_analyze, name='api_smart_lane_analyze'),
    path('api/smart-lane/thought-log/<str:analysis_id>/', views.api_get_thought_log, name='api_get_thought_log'),
]