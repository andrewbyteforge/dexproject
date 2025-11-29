"""
Strategy Selector for Paper Trading Bot - Strategy Selection Module

This module handles intelligent strategy selection for token purchases.
It analyzes market conditions and automatically selects the optimal entry
strategy based on volatility, trend, liquidity, and confidence.

STRATEGY DECISION MATRIX (Priority Order):
1. TWAP: Very large orders in illiquid markets (minimize price impact)
2. VWAP: Large orders in liquid markets (volume-weighted execution)
3. GRID: High volatility + range-bound market (profit from oscillation)
4. DCA: Strong bullish trend + high confidence (build position over time)
5. SPOT: Standard conditions (fast execution, default fallback)

This module was extracted from market_analyzer.py as part of v4.0+ refactoring
to keep individual files under 800 lines and improve maintainability.

Phase 7B - Day 10: Added VWAP strategy selection

File: dexproject/paper_trading/bot/strategies/strategy_selector.py
"""

import logging
from decimal import Decimal
from typing import Optional

from paper_trading.models import PaperStrategyConfiguration
from paper_trading.intelligence.core.base import (
    MarketContext,
    TradingDecision
)
from paper_trading.constants import (
    StrategyType,
    StrategySelectionThresholds,
    MarketTrend
)

logger = logging.getLogger(__name__)


class StrategySelector:
    """
    Selects optimal trading strategy based on market conditions.
    
    This is the CORE intelligence of Phase 7B. The bot analyzes market
    conditions (volatility, trend, liquidity, confidence) and automatically
    selects the best entry strategy.
    
    Decision Matrix (Priority Order):
    1. TWAP: Very large position + LOW liquidity -> minimize market impact
    2. VWAP: Large position + HIGH liquidity -> volume-weighted execution
    3. GRID: High volatility + range-bound -> profit from oscillation
    4. DCA: Strong bullish trend + high confidence -> build position gradually
    5. SPOT: Default/fallback -> fast execution for standard conditions
    
    Key Difference between TWAP and VWAP:
    - TWAP: Equal chunks at equal intervals for ILLIQUID markets
    - VWAP: Variable chunks based on volume for LIQUID markets
    """

    def __init__(
        self,
        strategy_config: Optional[PaperStrategyConfiguration] = None
    ) -> None:
        """
        Initialize Strategy Selector.
        
        Args:
            strategy_config: Optional strategy configuration
        """
        self.strategy_config = strategy_config
        
        logger.info("[STRATEGY SELECTOR] Initialized")

    # =========================================================================
    # STRATEGY SELECTION - Phase 7B
    # =========================================================================

    def select_strategy(
        self,
        token_address: str,
        token_symbol: str,
        decision: TradingDecision,
        market_context: MarketContext
    ) -> str:
        """
        Select optimal trading strategy based on market conditions.

        This is the CORE intelligence of Phase 7B. The bot analyzes market
        conditions (volatility, trend, liquidity, confidence) and automatically
        selects the best entry strategy.

        Decision Matrix (Priority Order):
        1. TWAP: Very large position + LOW liquidity -> minimize market impact
        2. VWAP: Large position + HIGH liquidity -> volume-weighted execution
        3. GRID: High volatility + range-bound -> profit from oscillation
        4. DCA: Strong bullish trend + high confidence -> build position gradually
        5. SPOT: Standard conditions (fast execution, default fallback)

        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            decision: Trading decision from intelligence engine
            market_context: Market context with volatility, trend, liquidity

        Returns:
            StrategyType constant (SPOT, DCA, GRID, TWAP, or VWAP)
        """
        try:
            # Get strategy preferences from config
            enable_dca = getattr(self.strategy_config, 'enable_dca', True) if self.strategy_config else True
            enable_grid = getattr(self.strategy_config, 'enable_grid', True) if self.strategy_config else True
            enable_twap = getattr(self.strategy_config, 'enable_twap', True) if self.strategy_config else True
            enable_vwap = getattr(self.strategy_config, 'enable_vwap', True) if self.strategy_config else True

            # Extract market conditions
            volatility = getattr(market_context, 'volatility', Decimal('0'))
            trend = getattr(market_context, 'trend', 'unknown')
            liquidity = getattr(market_context, 'liquidity', Decimal('0'))
            confidence = Decimal(str(decision.overall_confidence))
            position_size = Decimal(str(decision.position_size_usd))

            logger.info(
                f"[STRATEGY SELECT] Evaluating {token_symbol}: "
                f"volatility={float(volatility):.3f}, trend={trend}, "
                f"liquidity=${float(liquidity):,.0f}, confidence={float(confidence):.1f}%, "
                f"size=${float(position_size):.2f}"
            )

            # ===================================================================
            # DECISION 1: Check if TWAP strategy is appropriate
            # ===================================================================
            # TWAP is highest priority for very large orders in ILLIQUID markets
            if enable_twap:
                # TWAP requires: very large position + LOW liquidity + high confidence
                if (position_size >= StrategySelectionThresholds.TWAP_MIN_POSITION_SIZE_USD and
                    liquidity < StrategySelectionThresholds.TWAP_MAX_LIQUIDITY_USD and
                    confidence >= StrategySelectionThresholds.TWAP_MIN_CONFIDENCE and
                    StrategySelectionThresholds.TWAP_MIN_VOLATILITY <= volatility <= StrategySelectionThresholds.TWAP_MAX_VOLATILITY):

                    logger.info(
                        f"[STRATEGY SELECT] TWAP selected for {token_symbol}: "
                        f"Large order (${float(position_size):,.0f}) + "
                        f"LOW liquidity (${float(liquidity):,.0f}) + "
                        f"{float(confidence):.1f}% confidence"
                    )
                    return StrategyType.TWAP

            # ===================================================================
            # DECISION 2: Check if VWAP strategy is appropriate
            # ===================================================================
            # VWAP is for large orders in HIGH liquidity markets
            if enable_vwap:
                # VWAP requires: large position + HIGH liquidity + very high confidence + low volatility
                if (position_size >= StrategySelectionThresholds.VWAP_MIN_POSITION_SIZE_USD and
                    liquidity >= StrategySelectionThresholds.VWAP_MIN_LIQUIDITY_USD and
                    confidence >= StrategySelectionThresholds.VWAP_MIN_CONFIDENCE and
                    StrategySelectionThresholds.VWAP_MIN_VOLATILITY <= volatility <= StrategySelectionThresholds.VWAP_MAX_VOLATILITY):

                    logger.info(
                        f"[STRATEGY SELECT] VWAP selected for {token_symbol}: "
                        f"Large order (${float(position_size):,.0f}) + "
                        f"HIGH liquidity (${float(liquidity):,.0f}) + "
                        f"{float(confidence):.1f}% confidence + "
                        f"low volatility ({float(volatility):.1%})"
                    )
                    return StrategyType.VWAP

            # ===================================================================
            # DECISION 3: Check if GRID strategy is appropriate
            # ===================================================================
            if enable_grid:
                # Grid requires: high volatility + range-bound + good liquidity
                if (volatility >= StrategySelectionThresholds.GRID_MIN_VOLATILITY and
                    trend in MarketTrend.NEUTRAL and
                    liquidity >= StrategySelectionThresholds.GRID_MIN_LIQUIDITY_USD and
                    confidence >= StrategySelectionThresholds.GRID_MIN_CONFIDENCE):

                    logger.info(
                        f"[STRATEGY SELECT] GRID selected for {token_symbol}: "
                        f"High volatility ({float(volatility):.1%}) + {trend} trend + "
                        f"strong liquidity (${float(liquidity):,.0f})"
                    )
                    return StrategyType.GRID

            # ===================================================================
            # DECISION 4: Check if DCA strategy is appropriate
            # ===================================================================
            if enable_dca:
                # DCA requires: strong trend + high confidence + meaningful position size
                if (trend in MarketTrend.BULLISH and
                    confidence >= StrategySelectionThresholds.DCA_MIN_CONFIDENCE and
                    position_size >= StrategySelectionThresholds.DCA_MIN_POSITION_SIZE_USD):

                    logger.info(
                        f"[STRATEGY SELECT] DCA selected for {token_symbol}: "
                        f"{trend} trend + {float(confidence):.1f}% confidence + "
                        f"${float(position_size):.2f} position"
                    )
                    return StrategyType.DCA

            # ===================================================================
            # DECISION 5: Default to SPOT buy (fast execution)
            # ===================================================================
            logger.info(
                f"[STRATEGY SELECT] SPOT selected for {token_symbol}: "
                f"Standard conditions (no special strategy criteria met)"
            )
            return StrategyType.SPOT

        except Exception as e:
            logger.error(
                f"[STRATEGY SELECT] Error selecting strategy for {token_symbol}: {e}",
                exc_info=True
            )
            # Always fallback to SPOT on error
            return StrategyType.SPOT

    def get_strategy_summary(self) -> dict:
        """
        Get a summary of available strategies and their thresholds.
        
        Returns:
            Dictionary with strategy information for debugging/UI display
        """
        return {
            'strategies': {
                StrategyType.TWAP: {
                    'name': 'Time-Weighted Average Price',
                    'description': 'Equal chunks at equal intervals for ILLIQUID markets',
                    'min_position_usd': float(StrategySelectionThresholds.TWAP_MIN_POSITION_SIZE_USD),
                    'max_liquidity_usd': float(StrategySelectionThresholds.TWAP_MAX_LIQUIDITY_USD),
                    'min_confidence': float(StrategySelectionThresholds.TWAP_MIN_CONFIDENCE),
                    'volatility_range': f"{float(StrategySelectionThresholds.TWAP_MIN_VOLATILITY):.0%}-{float(StrategySelectionThresholds.TWAP_MAX_VOLATILITY):.0%}",
                    'enabled': getattr(self.strategy_config, 'enable_twap', True) if self.strategy_config else True,
                },
                StrategyType.VWAP: {
                    'name': 'Volume-Weighted Average Price',
                    'description': 'Variable chunks based on volume for LIQUID markets',
                    'min_position_usd': float(StrategySelectionThresholds.VWAP_MIN_POSITION_SIZE_USD),
                    'min_liquidity_usd': float(StrategySelectionThresholds.VWAP_MIN_LIQUIDITY_USD),
                    'min_confidence': float(StrategySelectionThresholds.VWAP_MIN_CONFIDENCE),
                    'volatility_range': f"{float(StrategySelectionThresholds.VWAP_MIN_VOLATILITY):.0%}-{float(StrategySelectionThresholds.VWAP_MAX_VOLATILITY):.0%}",
                    'enabled': getattr(self.strategy_config, 'enable_vwap', True) if self.strategy_config else True,
                },
                StrategyType.GRID: {
                    'name': 'Grid Trading',
                    'description': 'Multiple orders at price levels for range-bound markets',
                    'min_volatility': float(StrategySelectionThresholds.GRID_MIN_VOLATILITY),
                    'min_liquidity_usd': float(StrategySelectionThresholds.GRID_MIN_LIQUIDITY_USD),
                    'min_confidence': float(StrategySelectionThresholds.GRID_MIN_CONFIDENCE),
                    'required_trend': 'NEUTRAL (sideways/range-bound)',
                    'enabled': getattr(self.strategy_config, 'enable_grid', True) if self.strategy_config else True,
                },
                StrategyType.DCA: {
                    'name': 'Dollar Cost Averaging',
                    'description': 'Split buys over time for trending markets',
                    'min_position_usd': float(StrategySelectionThresholds.DCA_MIN_POSITION_SIZE_USD),
                    'min_confidence': float(StrategySelectionThresholds.DCA_MIN_CONFIDENCE),
                    'required_trend': 'BULLISH (uptrend/strong_uptrend)',
                    'enabled': getattr(self.strategy_config, 'enable_dca', True) if self.strategy_config else True,
                },
                StrategyType.SPOT: {
                    'name': 'Spot Buy',
                    'description': 'Immediate execution (default fallback)',
                    'min_confidence': float(StrategySelectionThresholds.SPOT_MIN_CONFIDENCE),
                    'min_liquidity_usd': float(StrategySelectionThresholds.SPOT_MIN_LIQUIDITY_USD),
                    'enabled': True,  # Always enabled as fallback
                },
            },
            'priority_order': [
                StrategyType.TWAP,
                StrategyType.VWAP,
                StrategyType.GRID,
                StrategyType.DCA,
                StrategyType.SPOT,
            ],
        }