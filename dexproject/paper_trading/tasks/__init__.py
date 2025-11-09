"""
Paper Trading Celery Tasks - Organized Structure

This module exports all Celery tasks for the paper trading system.
Tasks are organized into separate files by functionality:
- bot_control.py: Bot lifecycle management tasks
- order_monitoring.py: Order monitoring and execution tasks (Phase 7A)

File: paper_trading/tasks/__init__.py
"""

# Import bot control tasks
from .bot_control import (
    run_paper_trading_bot,
    stop_paper_trading_bot,
    get_bot_status,
    cleanup_old_sessions,
    update_position_prices_task,
    update_single_position_price,  # ← ADD THIS LINE
)

# Import order monitoring tasks (Phase 7A)
from .order_monitoring import (
    monitor_orders_task,
)

# Export all tasks for Celery autodiscovery
__all__ = [
    # Bot control tasks
    'run_paper_trading_bot',
    'stop_paper_trading_bot',
    'get_bot_status',
    'cleanup_old_sessions',
    'update_position_prices_task',
    'update_single_position_price',
    
    # Order monitoring tasks
    'monitor_orders_task',
    
]