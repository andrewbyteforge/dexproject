"""
DEX Operations for Intel Slider System (Phase 2)
Handles multi-DEX price comparison and arbitrage detection.

This module implements Phase 2 features:
- Multi-DEX price comparison across Uniswap V3, SushiSwap, Curve
- Arbitrage opportunity detection for optimal sell prices
- Routing trades to best-priced DEX

File: dexproject/paper_trading/intelligence/core/dex_operations.py
"""
import logging
from decimal import Decimal
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class DEXOperations:
    """
    Manages DEX price comparison and arbitrage detection.

    This class provides Phase 2 functionality for comparing prices across
    multiple DEXs and detecting profitable arbitrage opportunities.

    Attributes:
        dex_comparator: DEXPriceComparator instance (if Phase 2 available)
        arbitrage_detector: ArbitrageDetector instance (if Phase 2 available)
        chain_id: Chain ID for price queries
        phase_2_available: Whether Phase 2 components are loaded
        logger: Logger instance for structured logging
    """

    def __init__(
        self,
        dex_comparator: Optional[Any] = None,
        arbitrage_detector: Optional[Any] = None,
        chain_id: int = 84532
    ):
        """
        Initialize DEX Operations handler.

        Args:
            dex_comparator: Optional DEXPriceComparator instance
            arbitrage_detector: Optional ArbitrageDetector instance
            chain_id: Chain ID for operations (default: Base Sepolia 84532)
        """
        self.dex_comparator = dex_comparator
        self.arbitrage_detector = arbitrage_detector
        self.chain_id = chain_id
        self.phase_2_available = (dex_comparator is not None and arbitrage_detector is not None)
        self.logger = logger

        if self.phase_2_available:
            self.logger.info(
                "[DEX OPERATIONS] Phase 2 initialized: Multi-DEX comparison + Arbitrage detection"
            )
        else:
            self.logger.info("[DEX OPERATIONS] Phase 2 not available, single price source mode")

    async def compare_dex_prices(
        self,
        token_address: str,
        token_symbol: str,
        trade_size_usd: Decimal
    ) -> Optional[Dict[str, Any]]:
        """
        Compare prices across multiple DEXs to find the best execution price.

        This method queries Uniswap V3, SushiSwap, and Curve to find the best
        price for buying or selling a token. It returns the best price along
        with comparison data from all available DEXs.

        Args:
            token_address: Token contract address
            token_symbol: Token symbol for logging
            trade_size_usd: Trade size in USD for accurate price quotes

        Returns:
            Dictionary with price comparison results, or None if Phase 2 unavailable
        """
        if not self.dex_comparator:
            self.logger.debug(
                f"[DEX COMPARISON] Phase 2 not available for {token_symbol}, "
                "using single price source"
            )
            return None

        try:
            self.logger.info(
                f"[DEX COMPARISON] Comparing prices across DEXs for {token_symbol} "
                f"(${trade_size_usd:.2f})"
            )

            if hasattr(self.dex_comparator, 'compare_prices'):
                comparison_result = await self.dex_comparator.compare_prices(
                    token_address,
                    token_symbol,
                    trade_size_usd
                )
            else:
                self.logger.warning(
                    "[DEX COMPARISON] DEXPriceComparator.compare_prices method not found"
                )
                return None

            if comparison_result and comparison_result.get('best_price'):
                best_price = comparison_result['best_price']
                best_dex = comparison_result.get('best_dex', 'unknown')
                advantage = comparison_result.get('price_advantage_percent', Decimal('0'))

                self.logger.info(
                    f"[DEX COMPARISON] Best price for {token_symbol}: "
                    f"${best_price:.2f} on {best_dex} "
                    f"({advantage:.2f}% better than average)"
                )

                return comparison_result
            else:
                self.logger.warning(
                    f"[DEX COMPARISON] No valid prices found for {token_symbol}"
                )
                return None

        except Exception as comparison_error:
            self.logger.error(
                f"[DEX COMPARISON] Error comparing prices for {token_symbol}: "
                f"{comparison_error}",
                exc_info=True
            )
            return None

    async def detect_arbitrage_opportunity(
        self,
        token_address: str,
        token_symbol: str,
        current_price: Decimal,
        trade_size_usd: Decimal,
        gas_price_gwei: Optional[Decimal] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Detect arbitrage opportunities by comparing current position price
        with available sell prices across multiple DEXs.

        This method helps the bot decide where to sell tokens for maximum profit.
        It calculates net profit after gas costs and validates profitability.

        Args:
            token_address: Token contract address
            token_symbol: Token symbol for logging
            current_price: Current price we bought at (or holding price)
            trade_size_usd: Size of position to sell in USD
            gas_price_gwei: Current gas price for cost calculation

        Returns:
            Dictionary with arbitrage opportunity details, or None if not profitable
        """
        if not self.arbitrage_detector:
            self.logger.debug(
                f"[ARBITRAGE] Phase 2 not available for {token_symbol}, "
                "no arbitrage detection"
            )
            return None

        try:
            self.logger.info(
                f"[ARBITRAGE] Checking for arbitrage opportunity on {token_symbol} "
                f"(entry: ${current_price:.2f}, size: ${trade_size_usd:.2f})"
            )

            if hasattr(self.arbitrage_detector, 'find_opportunity'):
                opportunity = await self.arbitrage_detector.find_opportunity(
                    token_address=token_address,
                    buy_price=current_price,
                    trade_size_usd=trade_size_usd,
                    gas_price_gwei=gas_price_gwei
                )
            else:
                self.logger.warning(
                    "[ARBITRAGE] ArbitrageDetector.find_opportunity method not found"
                )
                return None

            if opportunity and opportunity.get('is_profitable'):
                net_profit = opportunity.get('net_profit_usd', Decimal('0'))
                margin = opportunity.get('profit_margin_percent', Decimal('0'))
                sell_dex = opportunity.get('sell_dex', 'unknown')

                self.logger.info(
                    f"[ARBITRAGE] 💰 Profitable opportunity found for {token_symbol}! "
                    f"Sell on {sell_dex} for ${net_profit:.2f} profit ({margin:.2f}% margin)"
                )

                return opportunity
            else:
                self.logger.debug(
                    f"[ARBITRAGE] No profitable arbitrage found for {token_symbol}"
                )
                return None

        except Exception as arbitrage_error:
            self.logger.error(
                f"[ARBITRAGE] Error detecting arbitrage for {token_symbol}: "
                f"{arbitrage_error}",
                exc_info=True
            )
            return None

    async def cleanup(self) -> None:
        """Clean up DEX operations resources."""
        try:
            # Clean up DEX comparator
            if self.dex_comparator:
                try:
                    if hasattr(self.dex_comparator, 'cleanup'):
                        await self.dex_comparator.cleanup()
                        self.logger.info("[DEX OPERATIONS] DEX comparator cleaned up")
                except Exception as dex_cleanup_error:
                    self.logger.error(
                        f"[DEX OPERATIONS] Error cleaning up DEX comparator: "
                        f"{dex_cleanup_error}"
                    )

            # Clean up arbitrage detector
            if self.arbitrage_detector:
                try:
                    if hasattr(self.arbitrage_detector, 'cleanup'):
                        await self.arbitrage_detector.cleanup()
                        self.logger.info("[DEX OPERATIONS] Arbitrage detector cleaned up")
                except Exception as arb_cleanup_error:
                    self.logger.error(
                        f"[DEX OPERATIONS] Error cleaning up arbitrage detector: "
                        f"{arb_cleanup_error}"
                    )

            self.logger.info("[DEX OPERATIONS] Cleanup complete")

        except Exception as cleanup_error:
            self.logger.error(
                f"[DEX OPERATIONS] Cleanup error: {cleanup_error}",
                exc_info=True
            )