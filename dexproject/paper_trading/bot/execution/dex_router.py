"""
DEX Router for Paper Trading Bot

This module handles multi-DEX price comparison and routing to find the best
execution prices across Uniswap V3, SushiSwap, and Curve Finance.

The router queries multiple DEXs to find:
- Best BUY price (cheapest DEX)
- Best SELL price (most profitable DEX)

This ensures the bot always gets optimal execution prices, just like professional
trading platforms (UNIBOT, MAESTRO) that route across multiple DEXs.

Key Features:
- Queries Uniswap V3, SushiSwap, Curve in parallel
- Finds cheapest DEX for buying
- Finds most profitable DEX for selling
- Validates prices to filter bad data
- Falls back to defaults on errors
- Comprehensive logging for transparency

File: paper_trading/bot/execution/dex_router.py
"""

import logging
from decimal import Decimal
from typing import Tuple, Optional

from asgiref.sync import async_to_sync

from paper_trading.constants import DEXNames

logger = logging.getLogger(__name__)


class PaperDexRouter:
    """
    Multi-DEX router for finding best execution prices.
    
    This router compares prices across multiple DEXs to find the best
    execution price for paper trades, mimicking the behavior of professional
    trading bots like UNIBOT and MAESTRO.
    
    Features:
    - Queries Uniswap V3, SushiSwap, Curve Finance
    - Finds cheapest DEX for buying (lowest price)
    - Finds most profitable DEX for selling (highest price)
    - Validates prices to filter testnet/bad data
    - Comprehensive error handling with fallbacks
    
    Example:
        router = PaperDexRouter(chain_id=8453)
        
        # Find best DEX for buying
        best_dex, best_price = router.get_best_buy_dex(
            token_address='0x...',
            token_symbol='WETH',
            trade_size_usd=Decimal('1000')
        )
        
        # Find best DEX for selling
        best_dex, best_price = router.get_best_sell_dex(
            token_address='0x...',
            token_symbol='WETH',
            trade_size_usd=Decimal('1000')
        )
    """
    
    def __init__(self, chain_id: int = 8453):
        """
        Initialize the DEX router.
        
        Args:
            chain_id: Blockchain network ID (default: 8453 = Base Mainnet)
        """
        self.chain_id = chain_id
        self.logger = logger
        
        # Initialize DEX price comparator (optional, graceful degradation)
        self.dex_comparator = None
        self._initialize_comparator()
        
        # Performance tracking
        self.total_queries = 0
        self.successful_queries = 0
        self.fallback_count = 0
        
        self.logger.info(
            f"[DEX ROUTER] Initialized for chain {chain_id}, "
            f"Comparator: {'AVAILABLE' if self.dex_comparator else 'UNAVAILABLE'}"
        )
    
    def _initialize_comparator(self) -> None:
        """
        Initialize the DEX price comparator.
        
        This attempts to load the DEXPriceComparator from the intelligence
        module. If it fails, the router will fall back to single-DEX mode.
        """
        try:
            from paper_trading.intelligence.dex.dex_price_comparator import (
                DEXPriceComparator
            )
            
            self.dex_comparator = DEXPriceComparator(chain_id=self.chain_id)
            self.logger.info(
                "[DEX ROUTER] DEXPriceComparator initialized successfully"
            )
        
        except ImportError as import_error:
            self.logger.warning(
                f"[DEX ROUTER] Could not import DEXPriceComparator: {import_error}, "
                "will use fallback single-DEX routing"
            )
            self.dex_comparator = None
        
        except Exception as init_error:
            self.logger.error(
                f"[DEX ROUTER] Error initializing DEXPriceComparator: {init_error}, "
                "will use fallback single-DEX routing",
                exc_info=True
            )
            self.dex_comparator = None
    
    # =========================================================================
    # MAIN ROUTING METHODS
    # =========================================================================
    
    def get_best_buy_dex(
        self,
        token_address: str,
        token_symbol: str,
        trade_size_usd: Decimal
    ) -> Tuple[str, Decimal]:
        """
        Find the cheapest DEX for buying a token.
        
        This method queries all available DEXs and returns the one with the
        lowest price (best for buying).
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol (for logging)
            trade_size_usd: Trade size in USD
        
        Returns:
            Tuple of (dex_name, price):
            - dex_name: Name of the cheapest DEX (e.g., 'uniswap_v3')
            - price: Token price on that DEX (Decimal)
            
            If comparison fails, returns (DEXNames.UNISWAP_V3, Decimal('0'))
            
        Example:
            dex, price = router.get_best_buy_dex(
                '0x4200...0006',
                'WETH',
                Decimal('1000')
            )
            # Returns: ('sushiswap', Decimal('2499.50'))
        """
        self.total_queries += 1
        
        if not self.dex_comparator:
            self.logger.debug(
                "[DEX ROUTER] No comparator available, using fallback"
            )
            self.fallback_count += 1
            return self._get_fallback_dex()
        
        try:
            # Compare prices across all DEXs
            self.logger.debug(
                f"[DEX ROUTER] Comparing BUY prices for {token_symbol} "
                f"(size: ${trade_size_usd:.2f})"
            )
            
            comparison = async_to_sync(self.dex_comparator.compare_prices)(
                token_address=token_address,
                token_symbol=token_symbol,
                use_cache=False  # Always get fresh prices for trading decisions
            )
            
            if not comparison or comparison.successful_queries < 1:
                self.logger.warning(
                    f"[DEX ROUTER] No successful DEX queries for {token_symbol}, "
                    "using fallback"
                )
                self.fallback_count += 1
                return self._get_fallback_dex()
            
            # Filter valid prices (exclude zeros, NaN, extreme values)
            valid_prices = [
                p for p in comparison.prices
                if p.success and p.price_usd and 
                Decimal('0.000001') <= p.price_usd <= Decimal('1000000000')
            ]
            
            if not valid_prices:
                self.logger.warning(
                    f"[DEX ROUTER] No valid prices found for {token_symbol}, "
                    "using fallback"
                )
                self.fallback_count += 1
                return self._get_fallback_dex()
            
            # Find cheapest DEX (lowest price = best for buying)
            cheapest = min(valid_prices, key=lambda p: p.price_usd)
            
            self.successful_queries += 1
            
            self.logger.info(
                f"[DEX ROUTER] 💰 Best BUY: {token_symbol} on {cheapest.dex_name} "
                f"at ${cheapest.price_usd:.4f} "
                f"({len(valid_prices)} DEXs compared)"
            )
            
            return (cheapest.dex_name, cheapest.price_usd)
        
        except Exception as e:
            self.logger.error(
                f"[DEX ROUTER] Error comparing BUY prices for {token_symbol}: {e}",
                exc_info=True
            )
            self.fallback_count += 1
            return self._get_fallback_dex()
    
    def get_best_sell_dex(
        self,
        token_address: str,
        token_symbol: str,
        trade_size_usd: Decimal
    ) -> Tuple[str, Decimal]:
        """
        Find the most profitable DEX for selling a token.
        
        This method queries all available DEXs and returns the one with the
        highest price (best for selling).
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol (for logging)
            trade_size_usd: Trade size in USD
        
        Returns:
            Tuple of (dex_name, price):
            - dex_name: Name of the highest-paying DEX (e.g., 'curve')
            - price: Token price on that DEX (Decimal)
            
            If comparison fails, returns (DEXNames.UNISWAP_V3, Decimal('0'))
            
        Example:
            dex, price = router.get_best_sell_dex(
                '0x4200...0006',
                'WETH',
                Decimal('1000')
            )
            # Returns: ('curve', Decimal('2500.50'))
        """
        self.total_queries += 1
        
        if not self.dex_comparator:
            self.logger.debug(
                "[DEX ROUTER] No comparator available, using fallback"
            )
            self.fallback_count += 1
            return self._get_fallback_dex()
        
        try:
            # Compare prices across all DEXs
            self.logger.debug(
                f"[DEX ROUTER] Comparing SELL prices for {token_symbol} "
                f"(size: ${trade_size_usd:.2f})"
            )
            
            comparison = async_to_sync(self.dex_comparator.compare_prices)(
                token_address=token_address,
                token_symbol=token_symbol,
                use_cache=False  # Always get fresh prices for trading decisions
            )
            
            if not comparison or comparison.successful_queries < 1:
                self.logger.warning(
                    f"[DEX ROUTER] No successful DEX queries for {token_symbol}, "
                    "using fallback"
                )
                self.fallback_count += 1
                return self._get_fallback_dex()
            
            # Filter valid prices (exclude zeros, NaN, extreme values)
            valid_prices = [
                p for p in comparison.prices
                if p.success and p.price_usd and 
                Decimal('0.000001') <= p.price_usd <= Decimal('1000000000')
            ]
            
            if not valid_prices:
                self.logger.warning(
                    f"[DEX ROUTER] No valid prices found for {token_symbol}, "
                    "using fallback"
                )
                self.fallback_count += 1
                return self._get_fallback_dex()
            
            # Find most profitable DEX (highest price = best for selling)
            most_profitable = max(valid_prices, key=lambda p: p.price_usd)
            
            self.successful_queries += 1
            
            self.logger.info(
                f"[DEX ROUTER] 💸 Best SELL: {token_symbol} on {most_profitable.dex_name} "
                f"at ${most_profitable.price_usd:.4f} "
                f"({len(valid_prices)} DEXs compared)"
            )
            
            return (most_profitable.dex_name, most_profitable.price_usd)
        
        except Exception as e:
            self.logger.error(
                f"[DEX ROUTER] Error comparing SELL prices for {token_symbol}: {e}",
                exc_info=True
            )
            self.fallback_count += 1
            return self._get_fallback_dex()
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _get_fallback_dex(self) -> Tuple[str, Decimal]:
        """
        Get fallback DEX when comparison fails.
        
        Returns:
            Tuple of (DEXNames.UNISWAP_V3, Decimal('0'))
        """
        return (DEXNames.UNISWAP_V3, Decimal('0'))
    
    def get_performance_stats(self) -> dict:
        """
        Get performance statistics for the router.
        
        Returns:
            Dictionary with performance metrics:
            - total_queries: Total number of routing queries
            - successful_queries: Number of successful multi-DEX comparisons
            - fallback_count: Number of times fallback was used
            - success_rate_percent: Success rate percentage
        """
        success_rate = (
            (self.successful_queries / max(self.total_queries, 1)) * 100
            if self.total_queries > 0
            else 0
        )
        
        return {
            'total_queries': self.total_queries,
            'successful_queries': self.successful_queries,
            'fallback_count': self.fallback_count,
            'success_rate_percent': round(success_rate, 2),
            'comparator_available': self.dex_comparator is not None
        }