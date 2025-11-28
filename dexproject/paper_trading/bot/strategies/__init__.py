"""
Strategy Operations Module

This module handles strategy selection and launching for the paper trading bot.
It includes all Phase 7B trading strategies:
- SPOT: Standard spot buy (fast execution, default fallback)
- DCA: Dollar Cost Averaging (build position over time)
- GRID: Grid Trading (profit from oscillation in range-bound markets)
- TWAP: Time-Weighted Average Price (equal chunks for illiquid markets)
- VWAP: Volume-Weighted Average Price (variable chunks for liquid markets)

Phase 7B - Day 10: Added VWAP strategy support

File: dexproject/paper_trading/bot/strategies/__init__.py
"""

from paper_trading.bot.strategies.strategy_selector import StrategySelector
from paper_trading.bot.strategies.strategy_launcher import StrategyLauncher


__all__ = [
    'StrategySelector',
    'StrategyLauncher',
]