"""
Paper Trading API Package

Organized API endpoints split into logical modules for maintainability.

Structure:
- data_api.py: Read-only data retrieval endpoints
- config_api.py: Configuration management endpoints
- bot_control_api.py: Bot lifecycle control endpoints
- account_management_api.py: Account management and session control endpoints

File: paper_trading/api/__init__.py
"""

# Import all API functions for easy access
from .data_api import (
    api_ai_thoughts,
    api_portfolio_data,
    api_trades_data,
    api_recent_trades,
    api_open_positions,
    api_metrics,
    api_performance_metrics,
    api_token_price,
)

from .config_api import (
    api_configuration,
)

from .bot_control_api import (
    api_start_bot,
    api_stop_bot,
    api_bot_status,
)

from .account_management_api import (
    api_reset_and_add_funds,
    api_sessions_history,
)

__all__ = [
    # Data API endpoints
    'api_ai_thoughts',
    'api_portfolio_data',
    'api_trades_data',
    'api_recent_trades',
    'api_open_positions',
    'api_metrics',
    'api_performance_metrics',
    'api_token_price',

    # Configuration API
    'api_configuration',

    # Bot Control API
    'api_start_bot',
    'api_stop_bot',
    'api_bot_status',

    # Account Management API
    'api_reset_and_add_funds',
    'api_sessions_history',
]