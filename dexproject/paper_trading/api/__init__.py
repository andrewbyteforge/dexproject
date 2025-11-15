"""
Paper Trading API Package
...
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
    api_reset_account,
    api_sessions_history,
)

from .session_delete_api import api_delete_session
from .session_export_api import api_export_session_csv

from .strategy_status import (
    api_active_strategies,
    api_strategy_detail,
)

from .strategy_controls import (
    api_pause_strategy,
    api_resume_strategy,
    api_cancel_strategy,
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

    # Bot Control API - TEMPORARILY DISABLED
    'api_start_bot',
    'api_stop_bot',
    'api_bot_status',

    # Account Management API
    'api_sessions_history',
    'api_delete_session',
    'api_export_session_csv',
    'api_reset_account',
    
    # Strategy Management API (Phase 7B - Day 7)
    'api_active_strategies',
    'api_strategy_detail',
    'api_pause_strategy',
    'api_resume_strategy',
    'api_cancel_strategy',
]