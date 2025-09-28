"""
Paper Trading URL Configuration
Complete URL routing for paper trading dashboard and API endpoints.
File: dexproject/paper_trading/urls.py
"""
from django.urls import path
from . import views

app_name = 'paper_trading'

urlpatterns = [
    # ==========================================================================
    # DASHBOARD VIEWS
    # Main user interface pages for paper trading
    # ==========================================================================
   
    # Main dashboard page
    path('', views.paper_trading_dashboard, name='dashboard'),
   
    # Trade history page with filtering and pagination
    path('trades/', views.trade_history, name='trades'),
   
    # Portfolio view with positions and analytics
    path('portfolio/', views.portfolio_view, name='portfolio'),
   
    # Strategy configuration management
    path('configuration/', views.configuration_view, name='configuration'),
   
    # ==========================================================================
    # API ENDPOINTS
    # RESTful API for data access and bot control
    # ==========================================================================
   
    # AI Thoughts API - THE STAR FEATURE!
    path('api/ai-thoughts/', views.api_ai_thoughts, name='api_ai_thoughts'),
   
    # Portfolio data API
    path('api/portfolio/', views.api_portfolio_data, name='api_portfolio'),
   
    # Trade history API with filtering
    path('api/trades/', views.api_trades_data, name='api_trades'),
    
    # ADD THESE TWO NEW ENDPOINTS FOR REAL-TIME UPDATES
    path('api/trades/recent/', views.api_recent_trades, name='api_recent_trades'),
    path('api/positions/open/', views.api_open_positions, name='api_open_positions'),
   
    # Configuration management API (GET/POST)
    path('api/config/', views.api_configuration, name='api_config'),
   
    # Performance metrics API
    path('api/metrics/', views.api_performance_metrics, name='api_metrics'),
   
    # Bot control APIs
    path('api/bot/start/', views.api_start_bot, name='api_start_bot'),
    path('api/bot/stop/', views.api_stop_bot, name='api_stop_bot'),
    path('api/bot/status/', views.api_bot_status, name='api_bot_status'),
]