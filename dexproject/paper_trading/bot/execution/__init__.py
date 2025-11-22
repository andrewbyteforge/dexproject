"""
Trade Execution Module

This module handles all trade execution operations for the paper trading bot.
"""

from paper_trading.bot.execution.trade_executor import TradeExecutor
from paper_trading.bot.execution.trade_record_manager import (
    create_paper_trade_record,
    create_ai_thought_log
)

__all__ = [
    'TradeExecutor',
    'create_paper_trade_record',
    'create_ai_thought_log',
]