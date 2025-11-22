"""
Arbitrage Operations Module

This module handles arbitrage detection and execution for the paper trading bot.
"""

from paper_trading.bot.arbitrage.arbitrage_executor import (
    check_arbitrage_after_buy,
    ARBITRAGE_AVAILABLE
)

__all__ = [
    'check_arbitrage_after_buy',
    'ARBITRAGE_AVAILABLE',
]