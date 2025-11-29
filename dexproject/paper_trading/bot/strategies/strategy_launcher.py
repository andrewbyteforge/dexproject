"""
Strategy Launcher for Paper Trading Bot - Strategy Execution Module

This module handles the initialization and launch of advanced trading strategies.
It calculates strategy parameters and coordinates with the strategy executor
to start DCA, GRID, TWAP, and VWAP strategies.

STRATEGIES:
- DCA (Dollar Cost Averaging): Spreads large orders over time intervals
- GRID: Places multiple orders at different price levels for range-bound markets
- TWAP (Time-Weighted Average Price): Splits very large orders to minimize slippage (ILLIQUID)
- VWAP (Volume-Weighted Average Price): Volume-based execution for better fills (LIQUID)

Phase 7B - Day 10: Added VWAP strategy launcher

File: dexproject/paper_trading/bot/strategies/strategy_launcher.py
"""

import logging
from decimal import Decimal
from typing import Optional

from paper_trading.models import (
    PaperTradingAccount,
    PaperStrategyConfiguration
)

from paper_trading.intelligence.core.base import (
    MarketContext,
    TradingDecision
)
from paper_trading.intelligence.core.intel_slider import IntelSliderEngine
from paper_trading.constants import (
    StrategyType,
    StrategySelectionThresholds,
    DecisionType
)

logger = logging.getLogger(__name__)


class StrategyLauncher:
    """
    Launches and configures advanced trading strategies.
    
    This class handles the initialization of DCA, GRID, TWAP, and VWAP strategies
    by calculating appropriate parameters and coordinating with the strategy
    executor service.
    
    Key Responsibilities:
    - Calculate strategy-specific parameters
    - Initialize strategy runs
    - Log strategy decisions
    - Handle strategy launch errors
    """

    def __init__(
        self,
        account: PaperTradingAccount,
        strategy_config: Optional[PaperStrategyConfiguration] = None,
        intelligence_engine: Optional[IntelSliderEngine] = None
    ) -> None:
        """
        Initialize Strategy Launcher.
        
        Args:
            account: Paper trading account
            strategy_config: Optional strategy configuration
            intelligence_engine: Optional intelligence engine (for logging)
        """
        self.account = account
        self.strategy_config = strategy_config
        self.intelligence_engine = intelligence_engine
        
        logger.info(
            f"[STRATEGY LAUNCHER] Initialized for account: {account.account_id}"
        )

    # =========================================================================
    # DCA STRATEGY
    # =========================================================================

    def start_dca_strategy(
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

            # Log AI thought
            self._log_strategy_thought(
                token_symbol=token_symbol,
                token_address=token_address,
                strategy_type=DecisionType.DCA_STRATEGY,
                strategy_id=str(strategy_run.strategy_id),
                confidence=float(decision.overall_confidence),
                reasoning=(
                    f"Bot selected DCA strategy: Spreading ${float(total_amount):.2f} "
                    f"across {num_intervals} intervals to average entry price"
                ),
                metadata={
                    'total_amount': float(total_amount),
                    'num_intervals': num_intervals,
                    'interval_hours': interval_hours
                }
            )

            logger.info(
                f"[DCA STRATEGY] Started DCA {strategy_run.strategy_id} for {token_symbol}"
            )
            return True

        except Exception as e:
            logger.error(
                f"[DCA STRATEGY] Failed to start DCA for {token_symbol}: {e}",
                exc_info=True
            )
            return False

    # =========================================================================
    # GRID STRATEGY
    # =========================================================================

    def start_grid_strategy(
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
            # Higher volatility -> wider grid range
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

            # Log AI thought
            self._log_strategy_thought(
                token_symbol=token_symbol,
                token_address=token_address,
                strategy_type=DecisionType.GRID_STRATEGY,
                strategy_id=str(strategy_run.strategy_id),
                confidence=float(decision.overall_confidence),
                reasoning=(
                    f"Bot selected GRID strategy: High volatility ({float(volatility):.1%}) "
                    f"+ {market_context.trend} market ideal for grid trading. "
                    f"Placing {num_levels} orders in ${float(lower_bound):.4f}-${float(upper_bound):.4f} range"
                ),
                metadata={
                    'num_levels': num_levels,
                    'lower_bound': float(lower_bound),
                    'upper_bound': float(upper_bound),
                    'volatility': float(volatility),
                    'trend': market_context.trend
                }
            )

            logger.info(
                f"[GRID STRATEGY] Started Grid {strategy_run.strategy_id} for {token_symbol}"
            )
            return True

        except Exception as e:
            logger.error(
                f"[GRID STRATEGY] Failed to start Grid for {token_symbol}: {e}",
                exc_info=True
            )
            return False

    # =========================================================================
    # TWAP STRATEGY
    # =========================================================================

    def start_twap_strategy(
        self,
        token_address: str,
        token_symbol: str,
        decision: TradingDecision
    ) -> bool:
        """
        Start a Time-Weighted Average Price (TWAP) strategy for this token.

        TWAP splits a very large order into equal-sized chunks executed at regular
        time intervals over hours. This minimizes market impact and price slippage,
        especially critical for ILLIQUID tokens.

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

            # Log AI thought
            self._log_strategy_thought(
                token_symbol=token_symbol,
                token_address=token_address,
                strategy_type=DecisionType.TWAP_STRATEGY,
                strategy_id=str(strategy_run.strategy_id),
                confidence=float(decision.overall_confidence),
                reasoning=(
                    f"Bot selected TWAP strategy: Large order ${float(total_amount):,.0f} "
                    f"in illiquid market. Splitting into {num_chunks} equal chunks over "
                    f"{execution_window_hours}h to minimize market impact"
                ),
                metadata={
                    'total_amount': float(total_amount),
                    'num_chunks': num_chunks,
                    'execution_window_hours': execution_window_hours,
                    'interval_minutes': interval_minutes
                }
            )

            logger.info(
                f"[TWAP STRATEGY] Started TWAP {strategy_run.strategy_id} for {token_symbol}"
            )
            return True

        except Exception as e:
            logger.error(
                f"[TWAP STRATEGY] Failed to start TWAP for {token_symbol}: {e}",
                exc_info=True
            )
            return False

    # =========================================================================
    # VWAP STRATEGY (Phase 7B - Day 10)
    # =========================================================================

    def start_vwap_strategy(
        self,
        token_address: str,
        token_symbol: str,
        decision: TradingDecision
    ) -> bool:
        """
        Start a Volume-Weighted Average Price (VWAP) strategy for this token.

        VWAP splits a large order into variable-sized chunks based on typical
        market volume distribution. Unlike TWAP which uses equal chunks for
        illiquid markets, VWAP executes more during high-volume periods and
        less during low-volume periods to achieve better fill prices in
        LIQUID markets.

        Key Differences from TWAP:
        - TWAP: Equal chunks at equal intervals (for LOW liquidity)
        - VWAP: Variable chunks based on volume (for HIGH liquidity)
        - TWAP: Minimize market impact in thin markets
        - VWAP: Achieve better fills by matching volume patterns

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

            # Get VWAP preferences from config or use defaults
            execution_window_hours = getattr(
                self.strategy_config,
                'vwap_execution_window_hours',
                StrategySelectionThresholds.VWAP_DEFAULT_EXECUTION_WINDOW_HOURS
            ) if self.strategy_config else StrategySelectionThresholds.VWAP_DEFAULT_EXECUTION_WINDOW_HOURS

            num_intervals = getattr(
                self.strategy_config,
                'vwap_num_intervals',
                StrategySelectionThresholds.VWAP_DEFAULT_INTERVALS
            ) if self.strategy_config else StrategySelectionThresholds.VWAP_DEFAULT_INTERVALS

            participation_rate = getattr(
                self.strategy_config,
                'vwap_participation_rate',
                StrategySelectionThresholds.VWAP_DEFAULT_PARTICIPATION_RATE
            ) if self.strategy_config else StrategySelectionThresholds.VWAP_DEFAULT_PARTICIPATION_RATE

            # Calculate VWAP parameters
            total_amount = Decimal(str(decision.position_size_usd))

            # Calculate interval timing
            if num_intervals > 1:
                total_minutes = execution_window_hours * 60
                interval_minutes = int(total_minutes / (num_intervals - 1))
            else:
                interval_minutes = 0

            logger.info(
                f"[VWAP STRATEGY] Starting VWAP for {token_symbol}: "
                f"${float(total_amount):,.0f} split into {num_intervals} volume-weighted intervals "
                f"over {execution_window_hours}h (participation rate: {float(participation_rate)*100:.1f}%)"
            )

            # Start the strategy via executor
            executor = get_strategy_executor()

            strategy_run = executor.start_strategy(
                account=self.account,
                strategy_type=StrategyType.VWAP,
                config={
                    'token_address': token_address,
                    'token_symbol': token_symbol,
                    'total_amount_usd': str(total_amount),
                    'execution_window_hours': execution_window_hours,
                    'num_intervals': num_intervals,
                    'interval_minutes': interval_minutes,
                    'participation_rate': str(participation_rate),
                    'start_immediately': True
                }
            )

            # Log AI thought
            self._log_strategy_thought(
                token_symbol=token_symbol,
                token_address=token_address,
                strategy_type=DecisionType.VWAP_STRATEGY,
                strategy_id=str(strategy_run.strategy_id),
                confidence=float(decision.overall_confidence),
                reasoning=(
                    f"Bot selected VWAP strategy: Large order ${float(total_amount):,.0f} "
                    f"in liquid market. Splitting into {num_intervals} volume-weighted intervals "
                    f"over {execution_window_hours}h to achieve better fills during high-volume periods"
                ),
                metadata={
                    'total_amount': float(total_amount),
                    'num_intervals': num_intervals,
                    'execution_window_hours': execution_window_hours,
                    'interval_minutes': interval_minutes,
                    'participation_rate': float(participation_rate)
                }
            )

            logger.info(
                f"[VWAP STRATEGY] Started VWAP {strategy_run.strategy_id} for {token_symbol}"
            )
            return True

        except Exception as e:
            logger.error(
                f"[VWAP STRATEGY] Failed to start VWAP for {token_symbol}: {e}",
                exc_info=True
            )
            return False

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _log_strategy_thought(
        self,
        token_symbol: str,
        token_address: str,
        strategy_type: str,
        strategy_id: str,
        confidence: float,
        reasoning: str,
        metadata: dict
    ) -> None:
        """
        Log an AI thought for the strategy decision.
        
        Args:
            token_symbol: Token symbol
            token_address: Token contract address
            strategy_type: DecisionType constant for the strategy
            strategy_id: UUID of the strategy run
            confidence: Confidence percentage
            reasoning: Human-readable reasoning for the decision
            metadata: Additional metadata dictionary
        """
        try:
            from paper_trading.bot.market_helpers import MarketHelpers
            
            if self.intelligence_engine:
                helpers = MarketHelpers(
                    account=self.account,
                    intelligence_engine=self.intelligence_engine
                )
                
                # Merge metadata with standard fields
                full_metadata = {
                    'token': token_symbol,
                    'token_address': token_address,
                    'strategy_id': strategy_id,
                    **metadata
                }
                
                helpers.log_thought(
                    action='BUY',
                    reasoning=reasoning,
                    confidence=confidence,
                    decision_type=strategy_type,
                    metadata=full_metadata
                )
                
        except ImportError:
            logger.warning(
                f"[STRATEGY LAUNCHER] MarketHelpers not available, skipping thought log"
            )
        except Exception as e:
            logger.warning(
                f"[STRATEGY LAUNCHER] Failed to log thought: {e}"
            )

    def _calculate_position_size(
        self,
        decision: TradingDecision,
        default_percent: Decimal = Decimal('5.0')
    ) -> Decimal:
        """
        Calculate position size from decision or account balance.
        
        Args:
            decision: Trading decision containing position size
            default_percent: Default percentage of balance if not specified
            
        Returns:
            Position size in USD
        """
        # Use decision's position size if available
        if hasattr(decision, 'position_size_usd') and decision.position_size_usd:
            return Decimal(str(decision.position_size_usd))
        
        # Otherwise calculate from account balance
        if self.account and self.account.balance_usd:
            return self.account.balance_usd * (default_percent / Decimal('100'))
        
        # Fallback to minimum position
        return Decimal('100.00')