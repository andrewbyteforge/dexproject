"""
Data Tracker for Intel Slider System
Handles historical data tracking, ML data collection, and performance metrics.

This module manages:
- Price history tracking
- Market context history
- Volatility tracking
- Performance metrics collection
- ML training data collection (Level 10)

File: dexproject/paper_trading/intelligence/core/data_tracker.py
"""
import logging
from decimal import Decimal
from typing import Dict, List, Any, Optional

from django.utils import timezone

from paper_trading.intelligence.core.base import MarketContext
from paper_trading.intelligence.data.price_history import PriceHistory


logger = logging.getLogger(__name__)


class DataTracker:
    """
    Tracks historical data, performance metrics, and ML training samples.

    This class maintains various tracking caches to support:
    - Market analysis over time
    - Performance monitoring
    - Machine learning data collection
    - Trend detection and volatility tracking

    Attributes:
        price_history_cache: Cache of historical prices per token
        market_history: Historical market contexts per token
        price_trends: Tracked price trends per token
        volatility_tracker: Volatility measurements per token
        performance_history: Performance metrics over time
        logger: Logger instance for structured logging
    """

    def __init__(self):
        """Initialize the Data Tracker."""
        # Price history tracking
        self.price_history_cache: Dict[str, PriceHistory] = {}

        # Market tracking storage
        self.market_history: Dict[str, List[MarketContext]] = {}
        self.price_trends: Dict[str, Dict[str, Any]] = {}
        self.volatility_tracker: Dict[str, List[Decimal]] = {}

        # Performance tracking
        self.performance_history: List[Dict[str, Any]] = []

        self.logger = logger

    def update_price_history(
        self,
        token_symbol: str,
        current_price: Decimal
    ) -> Optional[PriceHistory]:
        """
        Update price history for a token.

        Note: Currently disabled due to unknown PriceHistory interface.
        To enable: implement proper PriceHistory constructor and methods.

        Args:
            token_symbol: Token symbol to track
            current_price: Current price to add to history

        Returns:
            PriceHistory instance or None if disabled
        """
        # Price history tracking disabled - interface unknown
        # Return None to indicate no history available
        return None

    def update_market_context(self, market_context: MarketContext) -> None:
        """
        Update market tracking with new context.

        This method stores market contexts, price trends, and volatility data
        for historical analysis and trend detection.

        Args:
            market_context: Market context to track
        """
        try:
            token_symbol = market_context.token_symbol

            # Store in history
            if token_symbol not in self.market_history:
                self.market_history[token_symbol] = []

            self.market_history[token_symbol].append(market_context)

            # Keep only last 50 contexts
            if len(self.market_history[token_symbol]) > 50:
                self.market_history[token_symbol].pop(0)

            # Update price trends
            if hasattr(market_context, 'trend_direction'):
                if token_symbol not in self.price_trends:
                    self.price_trends[token_symbol] = {}

                self.price_trends[token_symbol].update({
                    'trend_direction': market_context.trend_direction,
                    'momentum': market_context.momentum,
                    'volatility': market_context.volatility,
                    'last_updated': timezone.now()
                })

            # Track volatility
            if hasattr(market_context, 'volatility'):
                if token_symbol not in self.volatility_tracker:
                    self.volatility_tracker[token_symbol] = []

                self.volatility_tracker[token_symbol].append(
                    market_context.volatility
                )

                # Keep last 20 volatility measurements
                if len(self.volatility_tracker[token_symbol]) > 20:
                    self.volatility_tracker[token_symbol].pop(0)

            self.logger.debug(
                f"[MARKET CONTEXT] Updated tracking for {token_symbol}"
            )

        except Exception as update_error:
            self.logger.error(
                f"[MARKET CONTEXT] Error updating: {update_error}",
                exc_info=True
            )

    def track_performance(self, metrics: Dict[str, Any]) -> None:
        """
        Track performance metrics for analysis.

        This method stores performance metrics for monitoring and
        historical analysis of trading decisions.

        Args:
            metrics: Performance metrics to track
        """
        try:
            self.performance_history.append(metrics)

            # Keep only last 1000 metrics
            if len(self.performance_history) > 1000:
                self.performance_history.pop(0)

        except Exception as track_error:
            self.logger.error(
                f"[TRACK PERFORMANCE] Error: {track_error}",
                exc_info=True
            )

    def get_market_history(self, token_symbol: str) -> List[MarketContext]:
        """
        Get market history for a token.

        Args:
            token_symbol: Token symbol to query

        Returns:
            List of historical market contexts
        """
        return self.market_history.get(token_symbol, [])

    def get_price_trends(self, token_symbol: str) -> Dict[str, Any]:
        """
        Get price trends for a token.

        Args:
            token_symbol: Token symbol to query

        Returns:
            Dictionary of trend data
        """
        return self.price_trends.get(token_symbol, {})

    def get_volatility_history(self, token_symbol: str) -> List[Decimal]:
        """
        Get volatility history for a token.

        Args:
            token_symbol: Token symbol to query

        Returns:
            List of historical volatility measurements
        """
        return self.volatility_tracker.get(token_symbol, [])

    def get_performance_history(self) -> List[Dict[str, Any]]:
        """
        Get complete performance history.

        Returns:
            List of performance metrics
        """
        return self.performance_history

    def clear_history(self, token_symbol: Optional[str] = None) -> None:
        """
        Clear tracking history.

        Args:
            token_symbol: Optional token symbol to clear. If None, clears all.
        """
        try:
            if token_symbol:
                # Clear specific token
                self.market_history.pop(token_symbol, None)
                self.price_trends.pop(token_symbol, None)
                self.volatility_tracker.pop(token_symbol, None)
                self.logger.info(f"[DATA TRACKER] Cleared history for {token_symbol}")
            else:
                # Clear all
                self.market_history.clear()
                self.price_trends.clear()
                self.volatility_tracker.clear()
                self.performance_history.clear()
                self.logger.info("[DATA TRACKER] Cleared all tracking history")

        except Exception as clear_error:
            self.logger.error(
                f"[DATA TRACKER] Error clearing history: {clear_error}",
                exc_info=True
            )