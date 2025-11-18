"""
Position Manager for Intel Slider System
Handles position sizing, portfolio limits, and concentration checks.

This module implements Phase 1 position-aware trading by enforcing
position limits per token to prevent over-concentration in the portfolio.

File: dexproject/paper_trading/intelligence/core/position_manager.py
"""
import logging
from decimal import Decimal
from typing import List, Tuple, Any, Optional

from paper_trading.intelligence.core.base import MarketContext


logger = logging.getLogger(__name__)


class PositionManager:
    """
    Manages position limits and portfolio concentration.

    This class enforces position sizing rules to prevent over-concentration
    in any single token, implementing risk management at the portfolio level.

    Attributes:
        strategy_config: Optional strategy configuration from dashboard
        logger: Logger instance for structured logging
    """

    def __init__(self, strategy_config=None):
        """
        Initialize the Position Manager.

        Args:
            strategy_config: Optional PaperStrategyConfiguration for position limits
        """
        self.strategy_config = strategy_config
        self.logger = logger

    def check_position_limits(
        self,
        market_context: MarketContext,
        existing_positions: List[Any],
        portfolio_value: Decimal
    ) -> Tuple[bool, str]:
        """
        Check if we can buy more of this token without exceeding position limits.

        This method implements Phase 1 position-aware trading by checking if the
        current position in a token exceeds the configured maximum percentage of
        the portfolio.

        Args:
            market_context: Market context containing token information
            existing_positions: List of existing positions
            portfolio_value: Current portfolio value in USD

        Returns:
            Tuple of (can_buy: bool, reason: str)
        """
        try:
            # Get max position size per token from strategy config
            if not self.strategy_config or \
               not hasattr(self.strategy_config, 'max_position_size_per_token_percent'):
                # No limit configured, allow the trade
                return True, "No position limit configured"

            max_position_per_token_percent = Decimal(
                str(self.strategy_config.max_position_size_per_token_percent)
            )

            # If limit is 0 or negative, no restriction
            if max_position_per_token_percent <= 0:
                return True, "Position limit disabled (0%)"

            # Find if we already have a position in this token
            token_symbol = market_context.token_symbol
            current_invested = Decimal('0')

            for pos in existing_positions:
                if pos.get('token_symbol') == token_symbol:
                    current_invested += Decimal(str(pos.get('invested_usd', 0)))

            # Calculate current position as percentage of portfolio
            if portfolio_value <= 0:
                # Can't calculate percentage with zero portfolio
                return True, "Portfolio value is zero, allowing trade"

            current_position_percent = (current_invested / portfolio_value) * Decimal('100')

            self.logger.info(
                f"[POSITION CHECK] Current {token_symbol} position: "
                f"${current_invested:.2f} ({current_position_percent:.2f}% of portfolio)"
            )

            # Check if we're at or over the limit
            if current_position_percent >= max_position_per_token_percent:
                reason = (
                    f"Already own {current_position_percent:.2f}% of portfolio in {token_symbol} "
                    f"(limit: {max_position_per_token_percent}%). "
                    "Will HOLD to prevent over-concentration."
                )
                self.logger.warning(f"[POSITION CHECK] ❌ {reason}")
                return False, reason

            # We can still buy more (under the limit)
            remaining_percent = max_position_per_token_percent - current_position_percent
            reason = (
                f"Can still buy {token_symbol}: currently {current_position_percent:.2f}%, "
                f"can add up to {remaining_percent:.2f}% more "
                f"(limit: {max_position_per_token_percent}%)"
            )
            self.logger.info(f"[POSITION CHECK] ✅ {reason}")
            return True, reason

        except Exception as check_error:
            self.logger.error(
                f"[POSITION CHECK] Error checking position limits: {check_error}",
                exc_info=True
            )
            # On error, allow the trade (fail-safe)
            return True, f"Position check error, allowing trade: {str(check_error)}"