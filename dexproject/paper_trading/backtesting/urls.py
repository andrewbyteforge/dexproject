"""
Backtesting URL Configuration

URL patterns for backtesting views and API endpoints.

File: dexproject/paper_trading/backtesting/urls.py
"""

from django.urls import path
from paper_trading.backtesting.views import (
    backtest_dashboard_view,
    backtest_detail_view,
)
from paper_trading.backtesting.api import (
    run_backtest_api,
    get_backtest_status_api,
    list_backtests_api,
    compare_strategies_api,
    delete_backtest_api,
)


app_name = 'backtest'

urlpatterns = [
    # Dashboard Views
    path('', backtest_dashboard_view, name='dashboard'),
    path('<uuid:backtest_id>/', backtest_detail_view, name='detail'),
    
    # API Endpoints
    path('api/run/', run_backtest_api, name='api_run'),
    path('api/status/<uuid:backtest_id>/', get_backtest_status_api, name='api_status'),
    path('api/list/', list_backtests_api, name='api_list'),
    path('api/compare/', compare_strategies_api, name='api_compare'),
    path('api/delete/<uuid:backtest_id>/', delete_backtest_api, name='api_delete'),
    
    
]