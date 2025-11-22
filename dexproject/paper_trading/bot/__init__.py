"""
Paper Trading Bot - Modular Architecture with Organized Subfolders

This package provides a complete paper trading bot organized into functional modules.
"""

# Main bot coordinator
from paper_trading.bot.enhanced_bot import EnhancedPaperTradingBot

# Buy operations
from paper_trading.bot.buy import MarketAnalyzer, TokenAnalyzer

# Sell operations
from paper_trading.bot.sell import PositionEvaluator

# Position management
from paper_trading.bot.positions import PositionManager

# Trade execution
from paper_trading.bot.execution import (
    TradeExecutor,
    create_paper_trade_record,
    create_ai_thought_log,
)

# Arbitrage operations
from paper_trading.bot.arbitrage import (
    ArbitrageExecutor,
    check_arbitrage_after_buy,
)

# Strategy operations
from paper_trading.bot.strategies import (
    select_optimal_strategy,
    StrategySelector,
    StrategyLauncher,
)

# Shared utilities
from paper_trading.bot.shared import (
    RealPriceManager,
    create_price_manager,
    validate_usd_amount,
    validate_quantity,
    validate_token_address,
    ValidationResult,
    ProfessionalSettings,
    MetricsLogger,
)

__all__ = [
    'EnhancedPaperTradingBot',
    'MarketAnalyzer',
    'TokenAnalyzer',
    'PositionEvaluator',
    'PositionManager',
    'TradeExecutor',
    'create_paper_trade_record',
    'create_ai_thought_log',
    'ArbitrageExecutor',
    'check_arbitrage_after_buy',
    'select_optimal_strategy',
    'StrategySelector',
    'StrategyLauncher',
    'RealPriceManager',
    'create_price_manager',
    'validate_usd_amount',
    'validate_quantity',
    'validate_token_address',
    'ValidationResult',
    'ProfessionalSettings',
    'MetricsLogger',
]

__version__ = '4.0.0'