"""
Analytics App URL Configuration

URL routing for analytics monitoring and Prometheus metrics endpoints.

File: dexproject/analytics/urls.py
"""

from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    # =========================================================================
    # VISUAL MONITORING DASHBOARD
    # =========================================================================
    
    # Visual monitoring dashboard page
    # GET /analytics/monitoring/
    path('monitoring/', views.monitoring_dashboard_view, name='monitoring_dashboard'),
    
    # =========================================================================
    # API ENDPOINTS (accessible from /analytics/api/...)
    # =========================================================================
    
    # Prometheus metrics endpoint - No authentication required for scraping
    # GET /analytics/api/metrics/
    path('api/metrics/', views.prometheus_metrics_view, name='prometheus_metrics'),
    
    # Monitoring data API - Returns JSON for dashboard charts
    # GET /analytics/api/monitoring/data/?timeframe=24h
    path('api/monitoring/data/', views.monitoring_data_api, name='monitoring_data'),
    
    # Health check endpoint
    # GET /analytics/api/health/
    path('api/health/', views.health_check_view, name='health_check'),
]