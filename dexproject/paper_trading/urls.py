"""
Paper Trading URL Configuration

Complete URL routing for paper trading dashboard and API endpoints.
Imports from both views.py (dashboard views) and api_views.py (API endpoints).

File Path: dexproject/paper_trading/urls.py
"""

from django.urls import path
from . import views, api_views  # Import from both files

app_name = 'paper_trading'

urlpatterns = [
    # ==========================================================================
    # DASHBOARD VIEWS (from views.py)
    # Main user interface pages for paper trading
    # ==========================================================================
    
    # Main dashboard page - displays portfolio summary, trades, and metrics
    path('', views.paper_trading_dashboard, name='dashboard'),
    
    # Trade history page with filtering and pagination
    path('trades/', views.trade_history, name='trades'),
    
    # Portfolio view with positions and analytics
    path('portfolio/', views.portfolio_view, name='portfolio'),
    
    # Strategy configuration management
    path('configuration/', views.configuration_view, name='configuration'),
    
    # NEW: Analytics dashboard page - comprehensive performance analysis
    # GET: /paper-trading/analytics/
    path('analytics/', views.analytics_view, name='analytics'),  # FIXED: Changed from paper_trading_analytics_view to analytics_view
    
    # ==========================================================================
    # DATA API ENDPOINTS (from api_views.py)
    # RESTful APIs for real-time data access
    # ==========================================================================
    
    # AI Thoughts API - Real-time AI decision stream
    # GET: /paper-trading/api/ai-thoughts/?limit=10&since=2024-01-01T00:00:00Z
    path('api/ai-thoughts/', api_views.api_ai_thoughts, name='api_ai_thoughts'),
    
    # Portfolio data API - Complete portfolio state
    # GET: /paper-trading/api/portfolio/
    path('api/portfolio/', api_views.api_portfolio_data, name='api_portfolio'),
    
    # Trade history API with filtering
    # GET: /paper-trading/api/trades/?status=completed&trade_type=buy&limit=50
    path('api/trades/', api_views.api_trades_data, name='api_trades'),
    
    # Recent trades API - Simplified for dashboard
    # GET: /paper-trading/api/trades/recent/?limit=10&since=2024-01-01T00:00:00Z
    path('api/trades/recent/', api_views.api_recent_trades, name='api_recent_trades'),
    
    # Open positions API - Current holdings
    # GET: /paper-trading/api/positions/open/
    path('api/positions/open/', api_views.api_open_positions, name='api_open_positions'),
    
    # Dashboard metrics API - Key performance indicators
    # GET: /paper-trading/api/metrics/
    path('api/metrics/', api_views.api_metrics, name='api_metrics'),
    
    # Performance metrics API - Detailed statistics
    # GET: /paper-trading/api/performance/
    path('api/performance/', api_views.api_performance_metrics, name='api_performance'),
    
    # ==========================================================================
    # ANALYTICS API ENDPOINTS (from views.py)
    # Analytics-specific data and export APIs
    # ==========================================================================
    
    # NEW: Analytics data API - Real-time analytics updates
    # GET: /paper-trading/api/analytics/data/
    # Returns JSON with latest analytics metrics for chart updates
    path('api/analytics/data/', views.api_analytics_data, name='api_analytics_data'),  # FIXED: Removed paper_trading_ prefix
    
    # NEW: Analytics export API - Export analytics to CSV
    # GET: /paper-trading/api/analytics/export/
    # Downloads analytics data as CSV file
    path('api/analytics/export/', views.api_analytics_export, name='api_analytics_export'),  # FIXED: Removed paper_trading_ prefix
    
    # ==========================================================================
    # CONFIGURATION API (from api_views.py)
    # Strategy and settings management
    # ==========================================================================
    
    # Configuration management API
    # GET: /paper-trading/api/configuration/ - Get current config
    # POST: /paper-trading/api/configuration/ - Update config
    path('api/configuration/', api_views.api_configuration, name='api_configuration'),
    
    # Alternative shorter URL for configuration
    path('api/config/', api_views.api_configuration, name='api_config'),
    
    # ==========================================================================
    # BOT CONTROL API (from api_views.py)
    # Paper trading bot management endpoints
    # ==========================================================================
    
    # Start paper trading bot
    # POST: /paper-trading/api/bot/start/
    path('api/bot/start/', api_views.api_start_bot, name='api_start_bot'),
    
    # Stop paper trading bot
    # POST: /paper-trading/api/bot/stop/
    path('api/bot/stop/', api_views.api_stop_bot, name='api_stop_bot'),
    
    # Get bot status
    # GET: /paper-trading/api/bot/status/
    path('api/bot/status/', api_views.api_bot_status, name='api_bot_status'),
]