"""
Position Evaluator for Paper Trading Bot - SELL PATH ONLY

This module handles evaluation of existing positions to determine optimal exit timing.
It ONLY processes tokens that we currently OWN, ensuring clean separation from new
opportunity analysis.

CRITICAL RULES:
1. ONLY evaluates tokens WITH existing positions
2. ONLY returns SELL or HOLD decisions
3. NEVER returns BUY or SKIP decisions
4. Coordinates intelligent sells AND safety net triggers

This module was created as part of the buy/sell/hold logic refactoring to ensure
clear separation of concerns and prevent conflicting trading decisions.

File: dexproject/paper_trading/bot/position_evaluator.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import timedelta

from django.utils import timezone
from asgiref.sync import async_to_sync

from paper_trading.models import PaperPosition
from paper_trading.intelligence.core.base import MarketContext, TradingDecision
from paper_trading.intelligence.core.intel_slider import IntelSliderEngine
from paper_trading.constants import DecisionType

# Type hints for external dependencies (avoid circular imports)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from paper_trading.bot.price_service_integration import RealPriceManager
    from paper_trading.bot.position_manager import PositionManager
    from paper_trading.bot.trade_executor import TradeExecutor
    from paper_trading.models import PaperTradingAccount, PaperStrategyConfiguration
    from paper_trading.intelligence.dex.dex_price_comparator import DEXPriceComparator
    from paper_trading.intelligence.strategies.arbitrage_engine import ArbitrageDetector

logger = logging.getLogger(__name__)


class PositionEvaluator:
    """
    Evaluates existing positions for intelligent exit decisions (SELL path).

    This class is responsible for:
    - Evaluating positions we already own for SELL signals
    - Checking arbitrage exit opportunities
    - Monitoring auto-close triggers (stop-loss, take-profit, max hold time)
    - Returning SELL or HOLD decisions ONLY
    - Never analyzing tokens we don't own

    Example usage:
        evaluator = PositionEvaluator(
            account=account,
            intelligence_engine=engine,
            strategy_config=config,
            arbitrage_enabled=True
        )

        # Check all positions for sell signals
        evaluator.check_position_sells(
            price_manager=price_manager,
            position_manager=position_manager,
            trade_executor=trade_executor,
            thought_logger=thought_logger
        )
    """

    def __init__(
        self,
        account: 'PaperTradingAccount',
        intelligence_engine: IntelSliderEngine,
        strategy_config: Optional['PaperStrategyConfiguration'] = None,
        arbitrage_enabled: bool = False,
        dex_comparator: Optional['DEXPriceComparator'] = None,
        arbitrage_detector: Optional['ArbitrageDetector'] = None
    ) -> None:
        """
        Initialize the Position Evaluator.

        Args:
            account: Paper trading account
            intelligence_engine: Intelligence engine for decision making
            strategy_config: Optional strategy configuration
            arbitrage_enabled: Whether arbitrage detection is enabled
            dex_comparator: Optional DEX price comparator
            arbitrage_detector: Optional arbitrage detector
        """
        self.account = account
        self.intelligence_engine = intelligence_engine
        self.strategy_config = strategy_config
        self.arbitrage_enabled = arbitrage_enabled
        self.dex_comparator = dex_comparator
        self.arbitrage_detector = arbitrage_detector

        # Arbitrage statistics
        self.arbitrage_opportunities_found = 0
        self.arbitrage_trades_executed = 0

        # SELL cooldown tracking (0 minutes = no cooldown for exits)
        self.sell_cooldown_minutes = 0  # Allow rapid exits when needed

        logger.info("[POSITION EVALUATOR] Initialized position evaluator for SELL path")

    # =========================================================================
    # MAIN POSITION EVALUATION - INTELLIGENT SELLS
    # =========================================================================

    def check_position_sells(
        self,
        price_manager: 'RealPriceManager',
        position_manager: 'PositionManager',
        trade_executor: 'TradeExecutor',
        thought_logger: Any
    ) -> None:
        """
        Evaluate all existing positions for intelligent SELL opportunities.

        This method analyzes each open position using the intelligence engine
        to determine if market conditions suggest it's time to exit:
        - Market conditions turning bearish
        - Risk increasing beyond comfort levels
        - Better opportunities elsewhere
        - Technical signals deteriorating
        - Position performance and hold time

        This is DIFFERENT from auto-close (stop-loss/take-profit) which are
        hard thresholds. This makes intelligent decisions based on AI analysis.

        Args:
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
            thought_logger: Thought logging function from market_helpers
        """
        try:
            # Get all open positions
            positions = position_manager.get_all_positions()

            if not positions:
                logger.debug("[POSITION EVALUATOR] No open positions to evaluate")
                return

            logger.info(
                f"[POSITION EVALUATOR] Evaluating {len(positions)} positions for SELL signals"
            )

            # Evaluate each position
            for token_symbol, position in positions.items():
                self.evaluate_position_for_sell(
                    token_symbol=token_symbol,
                    position=position,
                    price_manager=price_manager,
                    position_manager=position_manager,
                    trade_executor=trade_executor,
                    thought_logger=thought_logger
                )

            logger.info("[POSITION EVALUATOR] Completed intelligent SELL evaluation")

        except Exception as e:
            logger.error(
                f"[POSITION EVALUATOR] Error checking position sells: {e}",
                exc_info=True
            )

    def evaluate_position_for_sell(
        self,
        token_symbol: str,
        position: PaperPosition,
        price_manager: 'RealPriceManager',
        position_manager: 'PositionManager',
        trade_executor: 'TradeExecutor',
        thought_logger: Any
    ) -> None:
        """
        Evaluate a single position for intelligent SELL decision.

        Uses the intelligence engine to analyze whether market conditions
        suggest it's time to exit this position.

        Args:
            token_symbol: Token symbol
            position: Position object from database
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
            thought_logger: Thought logging function
        """
        try:
            # Get current price
            token_data = price_manager.get_token_price(token_symbol)
            if not token_data:
                logger.debug(f"[POSITION EVALUATOR] No price data for {token_symbol}")
                return

            # Handle both dict and Decimal return types
            if isinstance(token_data, dict):
                current_price = token_data.get('price')
                token_address = token_data.get('address', position.token_address)
            else:
                current_price = token_data
                token_address = position.token_address

            if not current_price:
                logger.warning(f"[POSITION EVALUATOR] No current price for {token_symbol}")
                return

            # Type assertion
            assert isinstance(current_price, Decimal)

            # Get price history for trend analysis
            price_history = price_manager.get_price_history(token_symbol, limit=24)

            # Calculate position metrics
            avg_entry_price = position.average_entry_price_usd
            hold_time = timezone.now() - position.opened_at
            hold_time_hours = hold_time.total_seconds() / 3600

            # Calculate P&L
            invested = position.total_invested_usd
            current_value = position.current_value_usd
            pnl_percent = ((current_value - invested) / invested * 100) if invested > 0 else Decimal('0')

            logger.info(
                f"[POSITION EVALUATOR] Evaluating {token_symbol} position: "
                f"Entry=${avg_entry_price:.2f}, Current=${current_price:.2f}, "
                f"P&L={pnl_percent:+.2f}%, Hold={hold_time_hours:.1f}h"
            )

            # Check for arbitrage exit opportunity FIRST (highest priority)
            if self.arbitrage_enabled:
                arb_exit = self._check_arbitrage_exit(
                    token_symbol=token_symbol,
                    token_address=token_address,
                    position=position,
                    current_price=current_price,
                    position_manager=position_manager,
                    trade_executor=trade_executor,
                    thought_logger=thought_logger
                )
                if arb_exit:
                    logger.info(
                        f"[POSITION EVALUATOR] ✅ Arbitrage exit executed for {token_symbol}"
                    )
                    return  # Exit taken via arbitrage, done with this position

            # Get existing positions for context
            existing_positions = position_manager.get_all_positions()

            # Call intelligence engine with POSITION-SPECIFIC parameters
            decision = async_to_sync(self.intelligence_engine.make_decision)(
                market_context=MarketContext(
                    token_address=token_address,
                    token_symbol=token_symbol,
                    current_price=current_price
                ),
                account_balance=self.account.current_balance_usd,
                existing_positions=list(existing_positions.values()),
                token_address=token_address,
                token_symbol=token_symbol,
                # Position-specific parameters for SELL evaluation
                position_entry_price=avg_entry_price,
                position_current_value=current_value,
                position_invested=invested,
                position_hold_time_hours=hold_time_hours
            )

            # VALIDATION: Ensure we only get SELL or HOLD
            if decision.action not in [DecisionType.SELL, DecisionType.HOLD]:
                logger.error(
                    f"[POSITION EVALUATOR] ⚠️  INVALID DECISION TYPE: {decision.action} "
                    f"for {token_symbol}. PositionEvaluator should only return SELL or HOLD. "
                    "Converting to HOLD."
                )
                decision.action = DecisionType.HOLD
                decision.primary_reasoning = (
                    f"Invalid decision type {decision.action} converted to HOLD"
                )

            # Log the decision
            if thought_logger:
                thought_logger(
                    action=decision.action,
                    reasoning=decision.primary_reasoning,
                    confidence=float(decision.overall_confidence),
                    decision_type="SELL_PATH_ANALYSIS",
                    metadata={
                        'token': token_symbol,
                        'token_address': token_address,
                        'current_price': float(current_price),
                        'entry_price': float(avg_entry_price),
                        'pnl_percent': float(pnl_percent),
                        'hold_time_hours': float(hold_time_hours),
                        'intel_level': int(self.intelligence_engine.intel_level),
                        'risk_score': float(decision.risk_score),
                        'opportunity_score': float(decision.opportunity_score),
                        'has_position': True,  # We always have a position in SELL path
                        'analysis_path': 'SELL_PATH'
                    }
                )

            # Execute SELL if decision says so
            if decision.action == DecisionType.SELL:
                logger.info(
                    f"[POSITION EVALUATOR] 📉 SELL signal for {token_symbol} "
                    f"(Confidence: {decision.overall_confidence:.1f}%, "
                    f"P&L: {pnl_percent:+.2f}%, Reason: {decision.primary_reasoning[:50]}...)"
                )

                # Execute the trade
                success = trade_executor.execute_trade(
                    decision=decision,
                    token_symbol=token_symbol,
                    current_price=current_price,
                    position_manager=position_manager
                )

                if success:
                    logger.info(f"[POSITION EVALUATOR] ✅ SELL executed for {token_symbol}")
                else:
                    logger.warning(f"[POSITION EVALUATOR] ❌ SELL failed for {token_symbol}")

            else:
                logger.debug(
                    f"[POSITION EVALUATOR] Holding {token_symbol} "
                    f"(P&L={pnl_percent:+.2f}%, Action={decision.action})"
                )

        except Exception as e:
            logger.error(
                f"[POSITION EVALUATOR] Error evaluating position for {token_symbol}: {e}",
                exc_info=True
            )

    # =========================================================================
    # ARBITRAGE EXIT OPPORTUNITIES
    # =========================================================================

    def _check_arbitrage_exit(
        self,
        token_symbol: str,
        token_address: str,
        position: PaperPosition,
        current_price: Decimal,
        position_manager: 'PositionManager',
        trade_executor: 'TradeExecutor',
        thought_logger: Any
    ) -> bool:
        """
        Check if we can exit position via profitable arbitrage.

        If we bought on one DEX and can sell for more on another DEX,
        execute the arbitrage exit.

        Args:
            token_symbol: Token symbol
            token_address: Token contract address
            position: Position object
            current_price: Current market price
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
            thought_logger: Thought logging function

        Returns:
            True if arbitrage exit was executed, False otherwise
        """
        try:
            if not self.dex_comparator or not self.arbitrage_detector:
                return False

            logger.debug(
                f"[POSITION EVALUATOR] Checking arbitrage exit for {token_symbol}"
            )

            # Compare prices across DEXes
            comparison = async_to_sync(self.dex_comparator.compare_prices)(
                token_address=token_address,
                amount_in_usd=position.current_value_usd
            )

            if not comparison or 'error' in comparison:
                logger.debug(f"[POSITION EVALUATOR] No arbitrage data for {token_symbol}")
                return False

            # Check if there's a profitable exit opportunity
            best_price = comparison.get('best_price', Decimal('0'))
            spread_percent = comparison.get('spread_percent', Decimal('0'))

            # Need at least 0.5% spread to cover gas and slippage
            min_spread = Decimal('0.5')
            if spread_percent < min_spread:
                logger.debug(
                    f"[POSITION EVALUATOR] Arbitrage spread too low for {token_symbol}: "
                    f"{spread_percent:.2f}%"
                )
                return False

            # Calculate potential profit
            potential_profit = (best_price - current_price) * position.quantity
            if potential_profit <= Decimal('10'):  # Minimum $10 profit
                logger.debug(
                    f"[POSITION EVALUATOR] Arbitrage profit too low for {token_symbol}: "
                    f"${potential_profit:.2f}"
                )
                return False

            # Found profitable arbitrage exit!
            self.arbitrage_opportunities_found += 1

            logger.info(
                f"[POSITION EVALUATOR] 💰 Arbitrage exit opportunity for {token_symbol}: "
                f"Spread={spread_percent:.2f}%, Profit=${potential_profit:.2f}"
            )

            # Create SELL decision for arbitrage exit
            decision = TradingDecision(
                action=DecisionType.SELL,
                token_address=token_address,
                token_symbol=token_symbol,
                position_size_percent=Decimal('100'),  # Sell entire position
                position_size_usd=position.current_value_usd,
                stop_loss_percent=Decimal('0'),
                take_profit_targets=[],
                execution_mode='arbitrage',
                use_private_relay=True,  # Protect from MEV
                gas_strategy='fast',
                max_gas_price_gwei=Decimal('100'),
                overall_confidence=Decimal('90'),  # High confidence for arbitrage
                risk_score=Decimal('10'),  # Low risk
                opportunity_score=Decimal('90'),  # High opportunity
                primary_reasoning=f"Arbitrage exit: {spread_percent:.2f}% spread, ${potential_profit:.2f} profit",
                risk_factors=[],
                opportunity_factors=[
                    f"{spread_percent:.2f}% price spread",
                    f"${potential_profit:.2f} profit opportunity"
                ],
                mitigation_strategies=['Private RPC', 'Fast gas'],
                intel_level_used=self.intelligence_engine.intel_level,
                intel_adjustments={},
                time_sensitivity='high',
                max_execution_time_ms=5000,
                processing_time_ms=0
            )

            # Log the arbitrage opportunity
            if thought_logger:
                thought_logger(
                    action=DecisionType.SELL,
                    reasoning=decision.primary_reasoning,
                    confidence=float(decision.overall_confidence),
                    decision_type="ARBITRAGE_EXIT",
                    metadata={
                        'token': token_symbol,
                        'token_address': token_address,
                        'current_price': float(current_price),
                        'best_price': float(best_price),
                        'spread_percent': float(spread_percent),
                        'potential_profit': float(potential_profit),
                        'analysis_path': 'ARBITRAGE_EXIT'
                    }
                )

            # Execute the arbitrage exit
            success = trade_executor.execute_trade(
                decision=decision,
                token_symbol=token_symbol,
                current_price=best_price,  # Use best price, not current
                position_manager=position_manager
            )

            if success:
                self.arbitrage_trades_executed += 1
                logger.info(
                    f"[POSITION EVALUATOR] ✅ Arbitrage exit executed for {token_symbol}"
                )
                return True
            else:
                logger.warning(
                    f"[POSITION EVALUATOR] ❌ Arbitrage exit failed for {token_symbol}"
                )
                return False

        except Exception as e:
            logger.error(
                f"[POSITION EVALUATOR] Error checking arbitrage exit for {token_symbol}: {e}",
                exc_info=True
            )
            return False

    # =========================================================================
    # AUTO-CLOSE SAFETY NET (HARD THRESHOLDS)
    # =========================================================================

    def check_auto_close_positions(
        self,
        price_manager: 'RealPriceManager',
        position_manager: 'PositionManager',
        trade_executor: 'TradeExecutor',
        thought_logger: Any
    ) -> None:
        """
        Check all positions for auto-close triggers (safety net).

        This is the SAFETY NET that runs AFTER intelligent sells.
        It checks for hard threshold triggers:
        - Stop-loss (default: -5%)
        - Take-profit (default: +10%)
        - Max hold time (default: 72 hours)

        These are FORCED sells that override AI decisions.

        Args:
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
            thought_logger: Thought logging function
        """
        try:
            # Delegate to position_manager for threshold checks
            positions_to_close = position_manager.check_auto_close_positions(
                token_list=[]  # Will check all positions
            )

            if not positions_to_close:
                logger.debug("[POSITION EVALUATOR] No auto-close triggers")
                return

            logger.info(
                f"[POSITION EVALUATOR] 🛡️ Found {len(positions_to_close)} positions "
                "to auto-close (safety net)"
            )

            # Execute force closes
            for token_symbol, reason, pnl_percent in positions_to_close:
                self._execute_force_close(
                    token_symbol=token_symbol,
                    reason=reason,
                    pnl_percent=pnl_percent,
                    price_manager=price_manager,
                    position_manager=position_manager,
                    trade_executor=trade_executor,
                    thought_logger=thought_logger
                )

        except Exception as e:
            logger.error(
                f"[POSITION EVALUATOR] Error checking auto-close: {e}",
                exc_info=True
            )

    def _execute_force_close(
        self,
        token_symbol: str,
        reason: str,
        pnl_percent: Decimal,
        price_manager: 'RealPriceManager',
        position_manager: 'PositionManager',
        trade_executor: 'TradeExecutor',
        thought_logger: Any
    ) -> None:
        """
        Execute a forced position close (safety net trigger).

        Args:
            token_symbol: Token symbol
            reason: Reason for close (STOP_LOSS, TAKE_PROFIT, MAX_HOLD_TIME)
            pnl_percent: Current P&L percentage
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
            thought_logger: Thought logging function
        """
        try:
            logger.info(
                f"[POSITION EVALUATOR] 🛡️ Force closing {token_symbol} "
                f"(Reason: {reason}, P&L: {pnl_percent:+.2f}%)"
            )

            # Get position
            position = position_manager.get_position(token_symbol)
            if not position:
                logger.warning(
                    f"[POSITION EVALUATOR] Position not found for {token_symbol}"
                )
                return

            # Get current price
            token_data = price_manager.get_token_price(token_symbol)
            if not token_data:
                logger.warning(
                    f"[POSITION EVALUATOR] No price data for {token_symbol}"
                )
                return

            if isinstance(token_data, dict):
                current_price = token_data.get('price')
                token_address = token_data.get('address', position.token_address)
            else:
                current_price = token_data
                token_address = position.token_address

            if not current_price:
                return

            # Create FORCE_SELL decision
            decision = TradingDecision(
                action=DecisionType.SELL,
                token_address=token_address,
                token_symbol=token_symbol,
                position_size_percent=Decimal('100'),  # Sell entire position
                position_size_usd=position.current_value_usd,
                stop_loss_percent=Decimal('0'),
                take_profit_targets=[],
                execution_mode='force_close',
                use_private_relay=False,
                gas_strategy='standard',
                max_gas_price_gwei=Decimal('50'),
                overall_confidence=Decimal('100'),  # 100% confidence for safety triggers
                risk_score=Decimal('0'),
                opportunity_score=Decimal('0'),
                primary_reasoning=f"Auto-close trigger: {reason}",
                risk_factors=[reason],
                opportunity_factors=[],
                mitigation_strategies=['Forced exit'],
                intel_level_used=self.intelligence_engine.intel_level,
                intel_adjustments={},
                time_sensitivity='high',
                max_execution_time_ms=10000,
                processing_time_ms=0
            )

            # Log the force close
            if thought_logger:
                thought_logger(
                    action=DecisionType.SELL,
                    reasoning=decision.primary_reasoning,
                    confidence=100.0,
                    decision_type="FORCE_CLOSE",
                    metadata={
                        'token': token_symbol,
                        'reason': reason,
                        'pnl_percent': float(pnl_percent),
                        'current_price': float(current_price),
                        'analysis_path': 'SAFETY_NET'
                    }
                )

            # Execute the force close
            success = trade_executor.execute_trade(
                decision=decision,
                token_symbol=token_symbol,
                current_price=current_price,
                position_manager=position_manager
            )

            if success:
                logger.info(
                    f"[POSITION EVALUATOR] ✅ Force close executed for {token_symbol}"
                )
            else:
                logger.warning(
                    f"[POSITION EVALUATOR] ❌ Force close failed for {token_symbol}"
                )

        except Exception as e:
            logger.error(
                f"[POSITION EVALUATOR] Error executing force close for {token_symbol}: {e}",
                exc_info=True
            )