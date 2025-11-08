"""
Price History Tracking for Paper Trading Bot

This module provides the PriceHistory dataclass for tracking historical
token prices and calculating trends for improved trading decisions.

File: dexproject/paper_trading/intelligence/price_history.py
"""

import logging
from decimal import Decimal
from typing import List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

# Django imports for timezone-aware datetimes
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class PriceHistory:
    """
    Historical price data for a token.
    
    Used to track price movements and calculate trends for better
    trading decisions.
    
    Attributes:
        token_address: Token contract address
        token_symbol: Token symbol (e.g., 'WETH')
        prices: List of recent prices
        timestamps: List of timestamps when prices were fetched
    """
    
    token_address: str
    token_symbol: str
    prices: List[Decimal]
    timestamps: List[datetime]
    
    def get_price_change_percent(self, period_minutes: int = 60) -> Optional[Decimal]:
        """
        Calculate price change percentage over a time period.
        
        Args:
            period_minutes: Time period to calculate change over
            
        Returns:
            Price change percentage, or None if insufficient data
        """
        try:
            if len(self.prices) < 2:
                logger.debug(
                    f"[PRICE HISTORY] Insufficient data for {self.token_symbol} "
                    f"(need 2+ prices, have {len(self.prices)})"
                )
                return None
            
            # Find price from period_minutes ago
            cutoff_time = timezone.now() - timedelta(minutes=period_minutes)
            
            for i, timestamp in enumerate(self.timestamps):
                if timestamp <= cutoff_time:
                    if i < len(self.prices) - 1:
                        old_price = self.prices[i]
                        current_price = self.prices[-1]
                        
                        if old_price == 0:
                            logger.warning(
                                f"[PRICE HISTORY] Zero old price for {self.token_symbol}"
                            )
                            return None
                        
                        change = ((current_price - old_price) / old_price) * Decimal('100')
                        
                        logger.debug(
                            f"[PRICE HISTORY] {self.token_symbol} change: {change:.2f}% "
                            f"over {period_minutes}min"
                        )
                        
                        return change
            
            logger.debug(
                f"[PRICE HISTORY] No price data old enough for {self.token_symbol} "
                f"({period_minutes}min period)"
            )
            return None
            
        except Exception as e:
            logger.error(
                f"[PRICE HISTORY] Error calculating price change for {self.token_symbol}: {e}",
                exc_info=True
            )
            return None
    
    def is_trending_up(self) -> bool:
        """
        Check if price is in upward trend.
        
        Returns:
            True if last 3 prices are increasing, False otherwise
        """
        try:
            if len(self.prices) < 3:
                logger.debug(
                    f"[PRICE HISTORY] Insufficient data for trend analysis of {self.token_symbol} "
                    f"(need 3+ prices, have {len(self.prices)})"
                )
                return False
            
            # Simple trend: last 3 prices increasing
            is_up = (
                self.prices[-1] > self.prices[-2] and
                self.prices[-2] > self.prices[-3]
            )
            
            if is_up:
                logger.debug(
                    f"[PRICE HISTORY] {self.token_symbol} trending UP: "
                    f"{self.prices[-3]} → {self.prices[-2]} → {self.prices[-1]}"
                )
            
            return is_up
            
        except Exception as e:
            logger.error(
                f"[PRICE HISTORY] Error checking uptrend for {self.token_symbol}: {e}",
                exc_info=True
            )
            return False
    
    def is_trending_down(self) -> bool:
        """
        Check if price is in downward trend.
        
        Returns:
            True if last 3 prices are decreasing, False otherwise
        """
        try:
            if len(self.prices) < 3:
                logger.debug(
                    f"[PRICE HISTORY] Insufficient data for trend analysis of {self.token_symbol} "
                    f"(need 3+ prices, have {len(self.prices)})"
                )
                return False
            
            # Simple trend: last 3 prices decreasing
            is_down = (
                self.prices[-1] < self.prices[-2] and
                self.prices[-2] < self.prices[-3]
            )
            
            if is_down:
                logger.debug(
                    f"[PRICE HISTORY] {self.token_symbol} trending DOWN: "
                    f"{self.prices[-3]} → {self.prices[-2]} → {self.prices[-1]}"
                )
            
            return is_down
            
        except Exception as e:
            logger.error(
                f"[PRICE HISTORY] Error checking downtrend for {self.token_symbol}: {e}",
                exc_info=True
            )
            return False
    
    def get_volatility(self) -> Decimal:
        """
        Calculate price volatility as percentage standard deviation.
        
        Returns:
            Volatility as a decimal (e.g., 0.15 = 15% volatility)
        """
        try:
            if len(self.prices) < 2:
                logger.debug(
                    f"[PRICE HISTORY] Insufficient data for volatility of {self.token_symbol}"
                )
                return Decimal('0')
            
            # Calculate mean
            mean = sum(self.prices) / len(self.prices)
            
            if mean == 0:
                logger.warning(
                    f"[PRICE HISTORY] Zero mean price for {self.token_symbol}"
                )
                return Decimal('0')
            
            # Calculate variance
            variance = sum((p - mean) ** 2 for p in self.prices) / len(self.prices)
            
            # Standard deviation
            std_dev = variance.sqrt()
            
            # Coefficient of variation (relative standard deviation)
            volatility = std_dev / mean
            
            logger.debug(
                f"[PRICE HISTORY] {self.token_symbol} volatility: {volatility:.2%}"
            )
            
            return volatility
            
        except Exception as e:
            logger.error(
                f"[PRICE HISTORY] Error calculating volatility for {self.token_symbol}: {e}",
                exc_info=True
            )
            return Decimal('0')