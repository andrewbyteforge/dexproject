"""
Backtesting API Package

REST API endpoints for running and managing backtests.

File: dexproject/paper_trading/backtesting/api/__init__.py
"""

from paper_trading.backtesting.api.backtest_api import (
    run_backtest_api,
    get_backtest_status_api,
    list_backtests_api,
    compare_strategies_api,
    delete_backtest_api,
)

__all__ = [
    'run_backtest_api',
    'get_backtest_status_api',
    'list_backtests_api',
    'compare_strategies_api',
    'delete_backtest_api',
]