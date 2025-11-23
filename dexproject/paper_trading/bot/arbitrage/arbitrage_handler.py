"""
Arbitrage Handler for Paper Trading Bot

This module handles cross-DEX arbitrage detection and coordination.
It monitors price differences across multiple DEXs (Uniswap V2/V3, etc.)
and identifies profitable arbitrage opportunities.

Responsibilities:
- Initialize DEX price comparator and arbitrage detector
- Update gas prices for arbitrage calculations
- Track arbitrage opportunities and executed trades
- Provide arbitrage statistics

This module was extracted from market_analyzer.py as part of v4.0+ refactoring
to keep individual files under 800 lines and improve maintainability.

File: dexproject/paper_trading/bot/arbitrage_handler.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional

# Import arbitrage detection components
try:
    from paper_trading.intelligence.dex.dex_price_comparator import DEXPriceComparator
    from paper_trading.intelligence.strategies.arbitrage_engine import ArbitrageEngine
    ARBITRAGE_AVAILABLE = True
except ImportError as e:
    ARBITRAGE_AVAILABLE = False
    DEXPriceComparator = None
    ArbitrageEngine = None

# Type hints for external dependencies (avoid circular imports)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from paper_trading.intelligence.core.intel_slider import IntelSliderEngine
    from paper_trading.models import PaperStrategyConfiguration

logger = logging.getLogger(__name__)


class ArbitrageHandler:
    """
    Handles cross-DEX arbitrage detection and coordination.

    This class manages arbitrage detection infrastructure, including
    DEX price comparators and arbitrage opportunity analysis.

    Example usage:
        handler = ArbitrageHandler(
            intelligence_engine=engine,
            strategy_config=config,
            enable_arbitrage=True
        )

        # Check if arbitrage is enabled
        if handler.is_enabled():
            # Update gas price
            handler.update_gas_price(Decimal('1.5'))

            # Get arbitrage stats
            stats = handler.get_arbitrage_stats()
            print(f"Found {stats['opportunities_found']} opportunities")
    """

    def __init__(
        self,
        intelligence_engine: 'IntelSliderEngine',
        strategy_config: Optional['PaperStrategyConfiguration'] = None,
        enable_arbitrage: bool = True
    ) -> None:
        """
        Initialize the Arbitrage Handler.

        Args:
            intelligence_engine: Intelligence engine (for chain_id)
            strategy_config: Optional strategy configuration
            enable_arbitrage: Whether to enable arbitrage detection
        """
        self.intelligence_engine = intelligence_engine
        self.strategy_config = strategy_config
        self.check_arbitrage = False
        self.dex_comparator: Optional[Any] = None
        self.arbitrage_engine: Optional[Any] = None
        self.arbitrage_opportunities_found = 0
        self.arbitrage_trades_executed = 0

        # Initialize arbitrage detection if available and enabled
        if ARBITRAGE_AVAILABLE and enable_arbitrage:
            self._initialize_arbitrage_detection()
        elif not ARBITRAGE_AVAILABLE:
            logger.warning(
                "[ARBITRAGE HANDLER] Arbitrage components not available - "
                "arbitrage detection disabled"
            )
        else:
            logger.info("[ARBITRAGE HANDLER] Arbitrage detection disabled by configuration")

    def _initialize_arbitrage_detection(self) -> None:
        """Initialize arbitrage detection components."""
        try:
            # Get enable_arbitrage from config if available
            enable_arb = getattr(
                self.strategy_config,
                'enable_arbitrage_detection',
                True
            ) if self.strategy_config else True

            if not enable_arb:
                logger.info("[ARBITRAGE HANDLER] Arbitrage disabled in strategy config")
                return

            # Get chain_id from intelligence engine
            chain_id = getattr(self.intelligence_engine, 'chain_id', 84532)

            # Initialize DEX price comparator
            self.dex_comparator = DEXPriceComparator(chain_id=chain_id)

            # Initialize arbitrage detector with sensible defaults
            self.arbitrage_engine = ArbitrageEngine(
                gas_price_gwei=Decimal('1.0'),  # Will update dynamically
                min_spread_percent=Decimal('0.5'),  # 0.5% minimum spread
                min_profit_usd=Decimal('10')  # $10 minimum profit
            )

            self.check_arbitrage = True
            logger.info(
                f"[ARBITRAGE HANDLER] ✅ Arbitrage detection ENABLED (chain: {chain_id})"
            )

        except Exception as e:
            logger.warning(
                f"[ARBITRAGE HANDLER] Failed to initialize arbitrage: {e}",
                exc_info=True
            )
            self.check_arbitrage = False

    # =========================================================================
    # ARBITRAGE MANAGEMENT
    # =========================================================================

    def is_enabled(self) -> bool:
        """Check if arbitrage detection is enabled."""
        return self.check_arbitrage

    def update_gas_price(self, gas_price_gwei: Decimal) -> None:
        """
        Update gas price for arbitrage calculations.

        This should be called periodically to keep arbitrage profit
        calculations accurate with current network conditions.

        Args:
            gas_price_gwei: Current gas price in gwei
        """
        if self.arbitrage_engine:
            self.arbitrage_engine.update_gas_price(gas_price_gwei)
            logger.debug(f"[ARBITRAGE] Updated gas price to {gas_price_gwei} gwei")

    def increment_opportunities_found(self) -> None:
        """Increment the count of arbitrage opportunities found."""
        self.arbitrage_opportunities_found += 1

    def increment_trades_executed(self) -> None:
        """Increment the count of arbitrage trades executed."""
        self.arbitrage_trades_executed += 1

    def get_arbitrage_stats(self) -> Dict[str, Any]:
        """
        Get arbitrage detection statistics.

        Returns:
            Dictionary with arbitrage performance metrics
        """
        stats = {
            'enabled': self.check_arbitrage,
            'opportunities_found': self.arbitrage_opportunities_found,
            'trades_executed': self.arbitrage_trades_executed,
            'success_rate': 0.0
        }

        if self.arbitrage_opportunities_found > 0:
            stats['success_rate'] = (
                (self.arbitrage_trades_executed / self.arbitrage_opportunities_found) * 100
            )

        if self.arbitrage_engine:
            try:
                stats['detector_stats'] = self.arbitrage_engine.get_performance_stats()
            except Exception as e:
                logger.debug(f"[ARBITRAGE] Could not get detector stats: {e}")

        if self.dex_comparator:
            try:
                stats['comparator_stats'] = self.dex_comparator.get_performance_stats()
            except Exception as e:
                logger.debug(f"[ARBITRAGE] Could not get comparator stats: {e}")

        return stats

    # =========================================================================
    # CLEANUP
    # =========================================================================

    async def cleanup(self) -> None:
        """
        Clean up arbitrage resources (DEX connections, etc.).

        Call this when shutting down to properly close all DEX connections.
        """
        try:
            if self.dex_comparator:
                await self.dex_comparator.cleanup()
                logger.info("[ARBITRAGE HANDLER] DEX comparator cleaned up")

            # Log final stats
            if self.check_arbitrage:
                stats = self.get_arbitrage_stats()
                logger.info(
                    f"[ARBITRAGE] Final stats: "
                    f"{stats['opportunities_found']} opportunities found, "
                    f"{stats['trades_executed']} trades executed"
                )

        except Exception as e:
            logger.error(
                f"[ARBITRAGE HANDLER] Cleanup error: {e}",
                exc_info=True
            )