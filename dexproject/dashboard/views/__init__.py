"""
Dashboard Views Package

Modular view structure for better organization and maintainability.
Replaces the monolithic views.py file with logical, smaller modules.

File: dashboard/views/__init__.py
"""

# Import all view functions from modules
from .main import (
    dashboard_home,
    mode_selection,
    configuration_panel
)

from .config import (
    configuration_list,
    configuration_summary,
    delete_configuration,
    clone_configuration
)

from .streaming import (
    metrics_stream,
    smart_lane_stream,
    combined_stream
)

from .api import (
    api_engine_status,
    api_performance_metrics,
    api_set_trading_mode,
    api_smart_lane_analysis,
    api_analyze_token
)

from .sessions import (
    start_trading_session,
    stop_trading_session,
    session_monitor,
    session_summary,
    session_list
)

from .debug import (
    simple_test,
    debug_templates,
    minimal_dashboard,
    engine_debug
)

from .utils import (
    ensure_engine_initialized,
    run_async_in_view
)

# Export all view functions for URL routing
__all__ = [
    # Main dashboard views
    'dashboard_home',
    'mode_selection', 
    'configuration_panel',
    
    # Configuration management
    'configuration_list',
    'configuration_summary',
    'delete_configuration',
    'clone_configuration',
    
    # Real-time streaming
    'metrics_stream',
    'smart_lane_stream', 
    'combined_stream',
    
    # API endpoints
    'api_engine_status',
    'api_performance_metrics',
    'api_set_trading_mode',
    'api_smart_lane_analysis',
    'api_analyze_token',
    
    # Trading sessions
    'start_trading_session',
    'stop_trading_session',
    'session_monitor',
    'session_summary',
    'session_list',
    
    # Debug and development
    'simple_test',
    'debug_templates',
    'minimal_dashboard',
    'engine_debug',
    
    # Utilities
    'ensure_engine_initialized',
    'run_async_in_view'
]