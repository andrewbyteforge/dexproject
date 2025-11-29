"""
Backtesting Views Package

Django views for the backtesting dashboard and related pages.

File: dexproject/paper_trading/backtesting/views/__init__.py
"""

from paper_trading.backtesting.views.backtest_views import (
    backtest_dashboard_view,
    backtest_detail_view,
)

__all__ = [
    'backtest_dashboard_view',
    'backtest_detail_view',
]