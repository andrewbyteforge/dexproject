"""
Historical Data Fetcher - Yahoo Finance Integration

Fetches historical OHLCV (Open, High, Low, Close, Volume) data from Yahoo Finance
for backtesting trading strategies. Uses yfinance library with caching to minimize
API calls.

Phase 7B - Day 12: Backtesting Engine

File: dexproject/paper_trading/backtesting/data_fetcher.py
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
from django.core.cache import cache
from django.utils import timezone

# Import yfinance for historical data
try:
    import yfinance as yf
except ImportError:
    yf = None

from paper_trading.backtesting.constants import (
    YAHOO_TICKER_MAPPING,
    STABLECOIN_PRICE,
    BACKTEST_DEFAULTS,
)


logger = logging.getLogger(__name__)


# =============================================================================
# HISTORICAL DATA FETCHER
# =============================================================================

class HistoricalDataFetcher:
    """
    Fetches historical price data from Yahoo Finance for backtesting.
    
    Features:
    - Fetches OHLCV data for supported tokens
    - Caches data to minimize API calls
    - Handles stablecoins with constant prices
    - Validates date ranges
    - Returns data in consistent format
    
    Example:
        fetcher = HistoricalDataFetcher()
        data = fetcher.fetch_historical_data(
            token_symbol='ETH',
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            interval='1h'
        )
    """
    
    def __init__(self) -> None:
        """Initialize the historical data fetcher."""
        if yf is None:
            logger.error(
                "[BACKTEST] yfinance library not installed. "
                "Install with: pip install yfinance --break-system-packages"
            )
        
        self.cache_prefix: str = "backtest_historical_data"
        self.cache_expiry_hours: int = BACKTEST_DEFAULTS['cache_expiry_hours']
        
        logger.info("[BACKTEST] HistoricalDataFetcher initialized")
    
    # =========================================================================
    # PUBLIC METHODS
    # =========================================================================
    
    def fetch_historical_data(
        self,
        token_symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = '1h'
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical OHLCV data for a token.
        
        Args:
            token_symbol: Token symbol (e.g., 'ETH', 'WBTC')
            start_date: Start date for historical data
            end_date: End date for historical data
            interval: Data interval ('1h', '1d', '5m', etc.)
            
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
            Returns None if data fetch fails
            
        Raises:
            ValueError: If date range is invalid
        """
        try:
            # Validate inputs
            self._validate_date_range(start_date, end_date)
            self._validate_interval(interval)
            
            # Check if token is supported
            if token_symbol not in YAHOO_TICKER_MAPPING:
                logger.error(
                    f"[BACKTEST] Unsupported token: {token_symbol}. "
                    f"Supported tokens: {list(YAHOO_TICKER_MAPPING.keys())}"
                )
                return None
            
            # Handle stablecoins (constant price)
            if token_symbol in STABLECOIN_PRICE:
                return self._generate_stablecoin_data(
                    token_symbol=token_symbol,
                    start_date=start_date,
                    end_date=end_date,
                    interval=interval
                )
            
            # Check cache first
            cache_key = self._get_cache_key(token_symbol, start_date, end_date, interval)
            cached_data = cache.get(cache_key)
            
            if cached_data is not None:
                logger.info(
                    f"[BACKTEST] ✅ Using cached data for {token_symbol} "
                    f"{start_date.date()} to {end_date.date()}"
                )
                return cached_data
            
            # Fetch from Yahoo Finance
            logger.info(
                f"[BACKTEST] Fetching historical data for {token_symbol} "
                f"from {start_date.date()} to {end_date.date()}"
            )
            
            data = self._fetch_from_yahoo(
                token_symbol=token_symbol,
                start_date=start_date,
                end_date=end_date,
                interval=interval
            )
            
            if data is not None and not data.empty:
                # Cache the data
                cache.set(
                    cache_key,
                    data,
                    timeout=self.cache_expiry_hours * 3600
                )
                
                logger.info(
                    f"[BACKTEST] ✅ Fetched {len(data)} data points for {token_symbol}"
                )
                return data
            else:
                logger.warning(
                    f"[BACKTEST] No data returned for {token_symbol}"
                )
                return None
            
        except Exception as e:
            logger.error(
                f"[BACKTEST] Error fetching historical data for {token_symbol}: {e}",
                exc_info=True
            )
            return None
    
    def get_latest_price(
        self,
        token_symbol: str,
        as_of_date: Optional[datetime] = None
    ) -> Optional[Decimal]:
        """
        Get the latest price for a token at a specific date.
        
        Args:
            token_symbol: Token symbol
            as_of_date: Date to get price for (default: now)
            
        Returns:
            Price as Decimal, or None if unavailable
        """
        try:
            # Handle stablecoins
            if token_symbol in STABLECOIN_PRICE:
                return Decimal(str(STABLECOIN_PRICE[token_symbol]))
            
            # Default to current date
            if as_of_date is None:
                as_of_date = timezone.now()
            
            # Fetch 1 day of data to get latest price
            start_date = as_of_date - timedelta(days=1)
            data = self.fetch_historical_data(
                token_symbol=token_symbol,
                start_date=start_date,
                end_date=as_of_date,
                interval='1h'
            )
            
            if data is not None and not data.empty:
                latest_close = data['close'].iloc[-1]
                return Decimal(str(latest_close))
            
            return None
            
        except Exception as e:
            logger.error(
                f"[BACKTEST] Error getting latest price for {token_symbol}: {e}",
                exc_info=True
            )
            return None
    
    # =========================================================================
    # PRIVATE METHODS - Data Fetching
    # =========================================================================
    
    def _fetch_from_yahoo(
        self,
        token_symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str
    ) -> Optional[pd.DataFrame]:
        """
        Fetch data from Yahoo Finance API.
        
        Args:
            token_symbol: Token symbol
            start_date: Start date
            end_date: End date
            interval: Data interval
            
        Returns:
            DataFrame with OHLCV data or None
        """
        if yf is None:
            logger.error("[BACKTEST] yfinance not installed")
            return None
        
        try:
            # Get Yahoo Finance ticker
            yahoo_ticker = YAHOO_TICKER_MAPPING.get(token_symbol)
            
            if yahoo_ticker is None:
                logger.error(
                    f"[BACKTEST] No Yahoo ticker mapping for {token_symbol}"
                )
                return None
            
            # Download data
            ticker = yf.Ticker(yahoo_ticker)
            hist = ticker.history(
                start=start_date,
                end=end_date,
                interval=interval
            )
            
            if hist.empty:
                logger.warning(
                    f"[BACKTEST] No data returned from Yahoo for {yahoo_ticker}"
                )
                return None
            
            # Convert to standard format
            df = pd.DataFrame({
                'timestamp': hist.index,
                'open': hist['Open'].values,
                'high': hist['High'].values,
                'low': hist['Low'].values,
                'close': hist['Close'].values,
                'volume': hist['Volume'].values,
            })
            
            # Reset index to make timestamp a column
            df = df.reset_index(drop=True)
            
            logger.debug(
                f"[BACKTEST] Fetched {len(df)} rows for {yahoo_ticker}"
            )
            
            return df
            
        except Exception as e:
            logger.error(
                f"[BACKTEST] Yahoo Finance API error for {token_symbol}: {e}",
                exc_info=True
            )
            return None
    
    def _generate_stablecoin_data(
        self,
        token_symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str
    ) -> pd.DataFrame:
        """
        Generate constant price data for stablecoins.
        
        Args:
            token_symbol: Stablecoin symbol
            start_date: Start date
            end_date: End date
            interval: Data interval
            
        Returns:
            DataFrame with constant $1.00 prices
        """
        price = STABLECOIN_PRICE[token_symbol]
        
        # Generate timestamp range based on interval
        timestamps = self._generate_timestamps(start_date, end_date, interval)
        
        # Create DataFrame with constant prices
        df = pd.DataFrame({
            'timestamp': timestamps,
            'open': [price] * len(timestamps),
            'high': [price] * len(timestamps),
            'low': [price] * len(timestamps),
            'close': [price] * len(timestamps),
            'volume': [0] * len(timestamps),  # No volume for stablecoins
        })
        
        logger.debug(
            f"[BACKTEST] Generated {len(df)} stablecoin data points "
            f"for {token_symbol}"
        )
        
        return df
    
    def _generate_timestamps(
        self,
        start_date: datetime,
        end_date: datetime,
        interval: str
    ) -> List[datetime]:
        """
        Generate timestamp list based on interval.
        
        Args:
            start_date: Start date
            end_date: End date
            interval: Data interval
            
        Returns:
            List of timestamps
        """
        # Parse interval to timedelta
        interval_delta = self._parse_interval(interval)
        
        timestamps: List[datetime] = []
        current = start_date
        
        while current <= end_date:
            timestamps.append(current)
            current += interval_delta
        
        return timestamps
    
    def _parse_interval(self, interval: str) -> timedelta:
        """
        Parse interval string to timedelta.
        
        Args:
            interval: Interval string ('1h', '1d', '5m', etc.)
            
        Returns:
            Timedelta object
        """
        # Extract number and unit
        if interval.endswith('m'):
            minutes = int(interval[:-1])
            return timedelta(minutes=minutes)
        elif interval.endswith('h'):
            hours = int(interval[:-1])
            return timedelta(hours=hours)
        elif interval.endswith('d'):
            days = int(interval[:-1])
            return timedelta(days=days)
        else:
            # Default to 1 hour
            return timedelta(hours=1)
    
    # =========================================================================
    # PRIVATE METHODS - Validation
    # =========================================================================
    
    def _validate_date_range(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> None:
        """
        Validate date range is valid.
        
        Args:
            start_date: Start date
            end_date: End date
            
        Raises:
            ValueError: If date range is invalid
        """
        if start_date >= end_date:
            raise ValueError(
                f"start_date ({start_date}) must be before end_date ({end_date})"
            )
        
        # Check minimum days
        days_diff = (end_date - start_date).days
        min_days = BACKTEST_DEFAULTS['min_historical_days']
        
        if days_diff < min_days:
            raise ValueError(
                f"Date range must be at least {min_days} days, got {days_diff} days"
            )
        
        # Check maximum days
        max_days = BACKTEST_DEFAULTS['max_historical_days']
        
        if days_diff > max_days:
            raise ValueError(
                f"Date range cannot exceed {max_days} days, got {days_diff} days"
            )
        
        # Check end date is not in the future
        if end_date > timezone.now():
            raise ValueError("end_date cannot be in the future")
    
    def _validate_interval(self, interval: str) -> None:
        """
        Validate interval is supported.
        
        Args:
            interval: Data interval
            
        Raises:
            ValueError: If interval is not supported
        """
        valid_intervals = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']
        
        if interval not in valid_intervals:
            raise ValueError(
                f"Invalid interval '{interval}'. "
                f"Valid intervals: {valid_intervals}"
            )
    
    # =========================================================================
    # PRIVATE METHODS - Caching
    # =========================================================================
    
    def _get_cache_key(
        self,
        token_symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str
    ) -> str:
        """
        Generate cache key for historical data.
        
        Args:
            token_symbol: Token symbol
            start_date: Start date
            end_date: End date
            interval: Data interval
            
        Returns:
            Cache key string
        """
        return (
            f"{self.cache_prefix}:{token_symbol}:"
            f"{start_date.date()}:{end_date.date()}:{interval}"
        )