"""
Backtesting Constants

Yahoo Finance ticker mappings and configuration defaults.

File: dexproject/paper_trading/backtesting/constants.py
"""

from typing import Dict, Optional, Any


# Yahoo Finance ticker mapping for supported tokens
# Maps token symbols to Yahoo Finance tickers for historical data
# None means use constant stablecoin price instead of fetching
YAHOO_TICKER_MAPPING: Dict[str, Optional[str]] = {
    'WETH': 'ETH-USD',
    'ETH': 'ETH-USD',
    'WBTC': 'BTC-USD',
    'BTC': 'BTC-USD',
    'UNI': 'UNI-USD',
    'LINK': 'LINK-USD',
    'AAVE': 'AAVE-USD',
    'MATIC': 'MATIC-USD',
    'ARB': 'ARB-USD',
    # Stablecoins (use constant $1.00 instead of API)
    'USDC': None,
    'USDT': None,
    'DAI': None,
    'USDbC': None,
}

# Stablecoin constant prices
STABLECOIN_PRICE: Dict[str, float] = {
    'USDC': 1.00,
    'USDT': 1.00,
    'DAI': 1.00,
    'USDbC': 1.00,
}

# Backtest configuration defaults
BACKTEST_DEFAULTS: Dict[str, Any] = {
    'cache_expiry_hours': 24,  # Cache historical data for 24 hours
    'max_historical_days': 365,  # Maximum 1 year of historical data
    'min_historical_days': 7,  # Minimum 1 week of historical data
    'default_interval': '1h',  # Default 1-hour candles
}