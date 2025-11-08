"""
Paper Trading Bot - Modular Architecture

This package provides a complete paper trading bot with:
- Real-time price feeds (Alchemy, CoinGecko, DEX)
- Intelligent decision making (Intel Slider 1-10)
- Position management with auto-close
- Trade execution (TX Manager + Legacy)
- Circuit breaker protection
- Performance tracking

Usage:
    from paper_trading.bot import EnhancedPaperTradingBot
    
    bot = EnhancedPaperTradingBot(
        account_name='My_Bot',
        intel_level=5,
        use_real_prices=True,
        chain_id=84532
    )
    
    if bot.initialize():
        bot.run()

File: dexproject/paper_trading/bot/__init__.py
"""

from paper_trading.bot.enhanced_bot import EnhancedPaperTradingBot
from paper_trading.bot.price_service_integration import (
    RealPriceManager,
    create_price_manager
)
from paper_trading.bot.position_manager import PositionManager
from paper_trading.bot.trade_executor import TradeExecutor
from paper_trading.bot.market_analyzer import MarketAnalyzer

__all__ = [
    'EnhancedPaperTradingBot',
    'RealPriceManager',
    'create_price_manager',
    'PositionManager',
    'TradeExecutor',
    'MarketAnalyzer'
]

__version__ = '3.0.0'
