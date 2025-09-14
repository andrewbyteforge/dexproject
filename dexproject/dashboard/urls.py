"""
Dashboard URL Configuration

URL patterns for the dashboard app including main dashboard,
mode selection, configuration panels, and API endpoints.

File: dashboard/urls.py
"""

from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    # Main dashboard pages
    path('', views.dashboard_home, name='home'),
    path('mode-selection/', views.mode_selection, name='mode_selection'),
    path('config/<str:mode>/', views.configuration_panel, name='configuration'),
    
    # Real-time data streams (SSE)
    path('metrics/stream/', views.metrics_stream, name='metrics_stream'),
    
    # JSON API endpoints
    path('api/engine-status/', views.api_engine_status, name='api_engine_status'),
    path('api/metrics/', views.api_performance_metrics, name='api_metrics'),
    path('api/set-mode/', views.api_set_trading_mode, name='api_set_mode'),
    
    # Session management
    path('session/start/', views.start_trading_session, name='start_session'),
    path('session/stop/<uuid:session_id>/', views.stop_trading_session, name='stop_session'),

    path('test/', views.simple_test, name='simple_test'),
    path('debug-templates/', views.debug_templates, name='debug_templates'),
    path('minimal/', views.minimal_dashboard, name='minimal_dashboard'),
    path('debug-mode-selection/', views.debug_mode_selection, name='debug_mode_selection'),

    path('config/<str:mode>/', views.configuration_panel, name='configuration'),
    path('debug-config/<str:mode>/', views.debug_configuration_panel, name='debug_configuration'),
]
