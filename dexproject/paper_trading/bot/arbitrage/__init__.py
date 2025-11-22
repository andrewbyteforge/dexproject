"""
Arbitrage Operations Module

This module handles arbitrage detection and execution for the paper trading bot.
"""

from paper_trading.bot.arbitrage.arbitrage_executor import ArbitrageExecutor
from paper_trading.bot.arbitrage.arbitrage_handler import check_arbitrage_after_buy

__all__ = [
    'ArbitrageExecutor',
    'check_arbitrage_after_buy',
]