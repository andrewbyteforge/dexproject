"""
Strategy Selector for Paper Trading Bot

This module handles intelligent strategy selection and execution initialization.
It analyzes market conditions and automatically selects the optimal entry strategy:
- SPOT: Standard fast execution for normal conditions
- DCA: Dollar Cost Averaging for strong trends
- GRID: Grid trading for volatile, range-bound markets
- TWAP: Time-Weighted Average Price for large orders in illiquid markets

Responsibilities:
- Analyze market conditions (volatility, trend, liquidity, confidence)
- Select optimal entry strategy based on market state
- Initialize and start selected strategies via strategy executor
- Log strategy selection reasoning for AI transparency

This module was extracted from market_analyzer.py as part of v4.0+ refactoring
to keep individual files under 800 lines and improve maintainability.

File: dexproject/paper_trading/bot/strategy_selector.py
"""

import logging
from decimal import Decimal
from typing import Optional, Any

from paper_trading.intelligence.core.base import TradingDecision, MarketContext
from paper_trading.constants import (
    StrategyType,
    StrategySelectionThresholds,
    MarketTrend,
    DecisionType
)

# Type hints for external dependencies (avoid circular imports)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from paper_trading.models import PaperTradingAccount, PaperStrategyConfiguration

logger = logging.getLogger(__name__)


class StrategySelector:
    """
    Intelligent strategy selector based on market conditions.

    This class implements Phase 7B functionality - automatic strategy selection
    based on real-time market analysis. It evaluates volatility, trend strength,
    liquidity, and confidence to choose between SPOT, DCA, GRID, and TWAP strategies.

    Decision Matrix:
    - High volatility + range-bound → GRID Strategy
    - Strong trend + high confidence + large position → DCA Strategy
    - Very large order + low liquidity → TWAP Strategy
    - Standard conditions → SPOT Buy (fast execution)

    Example usage:
        selector = StrategySelector(
            account=account,
            strategy_config=config,
            thought_logger=thought_logger
        )

        # Select optimal strategy
        strategy = selector.select_optimal_strategy(
            token_address='0x...',
            token_symbol='WETH',
            decision=decision,
            market_context=market_context
        )

        # Execute selected strategy
        success = selector.execute_strategy(
            strategy_type=strategy,
            token_address='0x...',
            token_symbol='WETH',
            decision=decision,
            market_context=market_context
        )
    """

    def __init__(
        self,
        account: 'PaperTradingAccount',
        strategy_config: Optional['PaperStrategyConfiguration'] = None,
        thought_logger: Optional[Any] = None
    ) -> None:
        """
        Initialize the Strategy Selector.

        Args:
            account: Paper trading account
            strategy_config: Optional strategy configuration
            thought_logger: Optional thought logger for AI decisions
        """
        self.account = account
        self.strategy_config = strategy_config
        self.thought_logger = thought_logger

        logger.info("[STRATEGY SELECTOR] Initialized strategy selector")

    # =========================================================================
    # STRATEGY SELECTION - Phase 7B
    # =========================================================================

    def select_optimal_strategy(
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
        selects the best entry strategy:

        Decision Matrix:
        - High volatility + range-bound → GRID Strategy
        - Strong trend + high confidence + large position → DCA Strategy
        - Very large order + low liquidity → TWAP Strategy
        - Standard conditions → SPOT Buy (fast execution)

        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            decision: Trading decision from intelligence engine
            market_context: Market context with volatility, trend, liquidity

        Returns:
            StrategyType constant (SPOT, DCA, GRID, or TWAP)
        """
        try:
            # Get strategy preferences from config
            enable_dca = getattr(self.strategy_config, 'enable_dca', True) if self.strategy_config else True
            enable_grid = getattr(self.strategy_config, 'enable_grid', True) if self.strategy_config else True
            enable_twap = getattr(self.strategy_config, 'enable_twap', True) if self.strategy_config else True

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
            # TWAP is highest priority for very large orders in illiquid markets
            if enable_twap:
                # TWAP requires: very large position + low/medium liquidity + high confidence
                if (position_size >= StrategySelectionThresholds.TWAP_MIN_POSITION_SIZE_USD and
                    liquidity < StrategySelectionThresholds.TWAP_MAX_LIQUIDITY_USD and
                    confidence >= StrategySelectionThresholds.TWAP_MIN_CONFIDENCE and
                    StrategySelectionThresholds.TWAP_MIN_VOLATILITY <= volatility <= StrategySelectionThresholds.TWAP_MAX_VOLATILITY):

                    logger.info(
                        f"[STRATEGY SELECT] ✅ TWAP selected for {token_symbol}: "
                        f"Large order (${float(position_size):,.0f}) + "
                        f"low liquidity (${float(liquidity):,.0f}) + "
                        f"{float(confidence):.1f}% confidence"
                    )
                    return StrategyType.TWAP

            # ===================================================================
            # DECISION 2: Check if GRID strategy is appropriate
            # ===================================================================
            if enable_grid:
                # Grid requires: high volatility + range-bound + good liquidity
                if (volatility >= StrategySelectionThresholds.GRID_MIN_VOLATILITY and
                    trend in MarketTrend.NEUTRAL and
                    liquidity >= StrategySelectionThresholds.GRID_MIN_LIQUIDITY_USD and
                    confidence >= StrategySelectionThresholds.GRID_MIN_CONFIDENCE):

                    logger.info(
                        f"[STRATEGY SELECT] ✅ GRID selected for {token_symbol}: "
                        f"High volatility ({float(volatility):.1%}) + {trend} trend + "
                        f"strong liquidity (${float(liquidity):,.0f})"
                    )
                    return StrategyType.GRID

            # ===================================================================
            # DECISION 3: Check if DCA strategy is appropriate
            # ===================================================================
            if enable_dca:
                # DCA requires: strong trend + high confidence + meaningful position size
                if (trend in MarketTrend.BULLISH and
                    confidence >= StrategySelectionThresholds.DCA_MIN_CONFIDENCE and
                    position_size >= StrategySelectionThresholds.DCA_MIN_POSITION_SIZE_USD):

                    logger.info(
                        f"[STRATEGY SELECT] ✅ DCA selected for {token_symbol}: "
                        f"{trend} trend + {float(confidence):.1f}% confidence + "
                        f"${float(position_size):.2f} position"
                    )
                    return StrategyType.DCA

            # ===================================================================
            # DECISION 4: Default to SPOT buy (fast execution)
            # ===================================================================
            logger.info(
                f"[STRATEGY SELECT] ✅ SPOT selected for {token_symbol}: "
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

    # =========================================================================
    # STRATEGY EXECUTION INITIALIZATION
    # =========================================================================

    def execute_strategy(
        self,
        strategy_type: str,
        token_address: str,
        token_symbol: str,
        decision: TradingDecision,
        market_context: MarketContext
    ) -> bool:
        """
        Execute the selected strategy.

        Args:
            strategy_type: Strategy type (SPOT, DCA, GRID, TWAP)
            token_address: Token contract address
            token_symbol: Token symbol
            decision: Trading decision
            market_context: Market context

        Returns:
            True if strategy started successfully, False otherwise
        """
        try:
            if strategy_type == StrategyType.TWAP:
                return self._start_twap_strategy(
                    token_address=token_address,
                    token_symbol=token_symbol,
                    decision=decision
                )
            elif strategy_type == StrategyType.DCA:
                return self._start_dca_strategy(
                    token_address=token_address,
                    token_symbol=token_symbol,
                    decision=decision
                )
            elif strategy_type == StrategyType.GRID:
                return self._start_grid_strategy(
                    token_address=token_address,
                    token_symbol=token_symbol,
                    decision=decision,
                    market_context=market_context
                )
            else:
                # SPOT strategy is handled by trade_executor, not here
                logger.debug(f"[STRATEGY] SPOT strategy for {token_symbol} - executor will handle")
                return True

        except Exception as e:
            logger.error(
                f"[STRATEGY] Error executing {strategy_type} for {token_symbol}: {e}",
                exc_info=True
            )
            return False

    def _start_dca_strategy(
        self,
        token_address: str,
        token_symbol: str,
        decision: TradingDecision
    ) -> bool:
        """
        Start a Dollar Cost Averaging (DCA) strategy for this token.

        DCA spreads a large buy order across multiple smaller purchases over time.
        This reduces impact on price and averages entry cost, ideal for trending markets.

        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            decision: Trading decision from intelligence engine

        Returns:
            True if strategy started successfully, False otherwise
        """
        try:
            # Import strategy executor (lazy import to avoid circular dependency)
            from paper_trading.services.strategy_executor import get_strategy_executor

            # Get DCA preferences from config
            num_intervals = getattr(self.strategy_config, 'dca_num_intervals', 5) if self.strategy_config else 5
            interval_hours = getattr(self.strategy_config, 'dca_interval_hours', 2) if self.strategy_config else 2

            # Calculate DCA parameters
            total_amount = Decimal(str(decision.position_size_usd))
            amount_per_interval = total_amount / Decimal(str(num_intervals))

            logger.info(
                f"[DCA STRATEGY] Starting DCA for {token_symbol}: "
                f"${float(total_amount):.2f} split into {num_intervals} buys "
                f"of ${float(amount_per_interval):.2f} every {interval_hours}h"
            )

            # Start the strategy via executor
            executor = get_strategy_executor()

            strategy_run = executor.start_strategy(
                account=self.account,
                strategy_type=StrategyType.DCA,
                config={
                    'token_address': token_address,
                    'token_symbol': token_symbol,
                    'total_amount_usd': str(total_amount),
                    'num_intervals': num_intervals,
                    'interval_hours': interval_hours,
                    'amount_per_interval': str(amount_per_interval)
                }
            )

            # Log AI thought if logger available
            if self.thought_logger:
                self.thought_logger.log_thought(
                    action='BUY',
                    reasoning=(
                        f"Bot selected DCA strategy: Spreading ${float(total_amount):.2f} "
                        f"across {num_intervals} intervals to average entry price"
                    ),
                    confidence=float(decision.overall_confidence),
                    decision_type=DecisionType.DCA_STRATEGY,
                    metadata={
                        'token': token_symbol,
                        'token_address': token_address,
                        'strategy_id': str(strategy_run.strategy_id),
                        'total_amount': float(total_amount),
                        'num_intervals': num_intervals,
                        'interval_hours': interval_hours
                    }
                )

            logger.info(
                f"[DCA STRATEGY] ✅ Started DCA {strategy_run.strategy_id} for {token_symbol}"
            )
            return True

        except Exception as e:
            logger.error(
                f"[DCA STRATEGY] ❌ Failed to start DCA for {token_symbol}: {e}",
                exc_info=True
            )
            return False

    def _start_grid_strategy(
        self,
        token_address: str,
        token_symbol: str,
        decision: TradingDecision,
        market_context: MarketContext
    ) -> bool:
        """
        Start a Grid Trading strategy for this token.

        Grid places multiple buy/sell orders at different price levels to profit
        from price oscillations in range-bound markets.

        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            decision: Trading decision from intelligence engine
            market_context: Market context with price ranges

        Returns:
            True if strategy started successfully, False otherwise
        """
        try:
            # Import strategy executor (lazy import)
            from paper_trading.services.strategy_executor import get_strategy_executor

            # Get Grid preferences from config
            num_levels = getattr(self.strategy_config, 'grid_num_levels', 7) if self.strategy_config else 7
            profit_target = getattr(self.strategy_config, 'grid_profit_target_percent', Decimal('2.0')) if self.strategy_config else Decimal('2.0')

            # Calculate grid parameters based on current price and volatility
            current_price = market_context.current_price
            volatility = market_context.volatility

            # Use volatility to determine price range
            # Higher volatility → wider grid range
            range_percent = max(Decimal('0.05'), volatility * Decimal('2'))  # Minimum 5%, scale with volatility

            lower_bound = current_price * (Decimal('1') - range_percent)
            upper_bound = current_price * (Decimal('1') + range_percent)

            total_amount = Decimal(str(decision.position_size_usd))

            logger.info(
                f"[GRID STRATEGY] Starting Grid for {token_symbol}: "
                f"{num_levels} levels from ${float(lower_bound):.4f} to ${float(upper_bound):.4f}, "
                f"total capital: ${float(total_amount):.2f}"
            )

            # Start the strategy via executor
            executor = get_strategy_executor()

            strategy_run = executor.start_strategy(
                account=self.account,
                strategy_type=StrategyType.GRID,
                config={
                    'token_address': token_address,
                    'token_symbol': token_symbol,
                    'total_amount_usd': str(total_amount),
                    'num_levels': num_levels,
                    'lower_bound': str(lower_bound),
                    'upper_bound': str(upper_bound),
                    'profit_target_percent': str(profit_target)
                }
            )

            # Log AI thought if logger available
            if self.thought_logger:
                self.thought_logger.log_thought(
                    action='BUY',
                    reasoning=(
                        f"Bot selected GRID strategy: High volatility ({float(volatility):.1%}) "
                        f"+ {market_context.trend} market ideal for grid trading. "
                        f"Placing {num_levels} orders in ${float(lower_bound):.4f}-${float(upper_bound):.4f} range"
                    ),
                    confidence=float(decision.overall_confidence),
                    decision_type=DecisionType.GRID_STRATEGY,
                    metadata={
                        'token': token_symbol,
                        'token_address': token_address,
                        'strategy_id': str(strategy_run.strategy_id),
                        'num_levels': num_levels,
                        'lower_bound': float(lower_bound),
                        'upper_bound': float(upper_bound),
                        'volatility': float(volatility),
                        'trend': market_context.trend
                    }
                )

            logger.info(
                f"[GRID STRATEGY] ✅ Started Grid {strategy_run.strategy_id} for {token_symbol}"
            )
            return True

        except Exception as e:
            logger.error(
                f"[GRID STRATEGY] ❌ Failed to start Grid for {token_symbol}: {e}",
                exc_info=True
            )
            return False

    def _start_twap_strategy(
        self,
        token_address: str,
        token_symbol: str,
        decision: TradingDecision
    ) -> bool:
        """
        Start a Time-Weighted Average Price (TWAP) strategy for this token.

        TWAP splits a very large order into equal-sized chunks executed at regular
        time intervals over hours. This minimizes market impact and price slippage,
        especially critical for illiquid tokens.

        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            decision: Trading decision from intelligence engine

        Returns:
            True if strategy started successfully, False otherwise
        """
        try:
            # Import strategy executor (lazy import to avoid circular dependency)
            from paper_trading.services.strategy_executor import get_strategy_executor

            # Get TWAP preferences from config or use defaults
            execution_window_hours = getattr(
                self.strategy_config,
                'twap_execution_window_hours',
                StrategySelectionThresholds.TWAP_DEFAULT_EXECUTION_WINDOW_HOURS
            ) if self.strategy_config else StrategySelectionThresholds.TWAP_DEFAULT_EXECUTION_WINDOW_HOURS

            num_chunks = getattr(
                self.strategy_config,
                'twap_num_chunks',
                StrategySelectionThresholds.TWAP_DEFAULT_CHUNKS
            ) if self.strategy_config else StrategySelectionThresholds.TWAP_DEFAULT_CHUNKS

            # Calculate TWAP parameters
            total_amount = Decimal(str(decision.position_size_usd))
            chunk_size = total_amount / Decimal(str(num_chunks))

            # Calculate interval between chunks
            if num_chunks > 1:
                total_minutes = execution_window_hours * 60
                interval_minutes = int(total_minutes / (num_chunks - 1))
            else:
                interval_minutes = 0

            logger.info(
                f"[TWAP STRATEGY] Starting TWAP for {token_symbol}: "
                f"${float(total_amount):,.0f} split into {num_chunks} chunks "
                f"of ${float(chunk_size):,.0f} every {interval_minutes} minutes "
                f"over {execution_window_hours}h"
            )

            # Start the strategy via executor
            executor = get_strategy_executor()

            strategy_run = executor.start_strategy(
                account=self.account,
                strategy_type=StrategyType.TWAP,
                config={
                    'token_address': token_address,
                    'token_symbol': token_symbol,
                    'total_amount_usd': str(total_amount),
                    'execution_window_hours': execution_window_hours,
                    'num_chunks': num_chunks,
                    'chunk_size_usd': str(chunk_size),
                    'interval_minutes': interval_minutes,
                    'start_immediately': True
                }
            )

            # Log AI thought if logger available
            if self.thought_logger:
                self.thought_logger.log_thought(
                    action='BUY',
                    reasoning=(
                        f"Bot selected TWAP strategy: Large order ${float(total_amount):,.0f} "
                        f"in illiquid market. Splitting into {num_chunks} chunks over "
                        f"{execution_window_hours}h to minimize market impact"
                    ),
                    confidence=float(decision.overall_confidence),
                    decision_type='TWAP_STRATEGY',  # Add this to DecisionType constants later
                    metadata={
                        'token': token_symbol,
                        'token_address': token_address,
                        'strategy_id': str(strategy_run.strategy_id),
                        'total_amount': float(total_amount),
                        'num_chunks': num_chunks,
                        'execution_window_hours': execution_window_hours,
                        'interval_minutes': interval_minutes
                    }
                )

            logger.info(
                f"[TWAP STRATEGY] ✅ Started TWAP {strategy_run.strategy_id} for {token_symbol}"
            )
            return True

        except Exception as e:
            logger.error(
                f"[TWAP STRATEGY] ❌ Failed to start TWAP for {token_symbol}: {e}",
                exc_info=True
            )
            return False