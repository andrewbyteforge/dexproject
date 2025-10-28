"""
Paper Trading Views - Main Module

This module maintains backward compatibility by re-exporting all view functions
from their new split modules. This allows existing URL patterns and imports
to continue working without modification.

REFACTORED: Split into logical modules for better organization:
- views_helpers.py: Template formatting and utility functions
- views_dashboard.py: Main dashboard view
- views_trades.py: Trade history with filtering
- views_portfolio.py: Portfolio positions view
- views_configuration.py: Configuration management
- views_analytics.py: Analytics dashboard and API endpoints

File: dexproject/paper_trading/views.py
"""

import logging

# Import all helper functions
from .views_helpers import (
    format_trade_for_template,
    format_position_for_template,
    calculate_portfolio_metrics
)

# Import all view functions
from .views_dashboard import paper_trading_dashboard
from .views_trades import trade_history
from .views_portfolio import portfolio_view
from .views_configuration import configuration_view
from .views_analytics import (
    analytics_view,
    api_analytics_data,
    api_analytics_export
)

logger = logging.getLogger(__name__)

# =============================================================================
# PUBLIC API - All functions are re-exported for backward compatibility
# =============================================================================

__all__ = [
    # Helper functions
    'format_trade_for_template',
    'format_position_for_template',
    'calculate_portfolio_metrics',
    
    # View functions
    'paper_trading_dashboard',
    'trade_history',
    'portfolio_view',
    'configuration_view',
    'analytics_view',
    
    # API functions
    'api_analytics_data',
    'api_analytics_export',
]

logger.info("Paper trading views module loaded - all functions available via split modules")