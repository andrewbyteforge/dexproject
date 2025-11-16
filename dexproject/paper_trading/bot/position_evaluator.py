"""
Position Evaluator for Paper Trading Bot

This module handles evaluation of existing positions to determine optimal exit timing.
It implements intelligent sell decisions based on market conditions, arbitrage opportunities,
and automatic safety triggers (stop-loss/take-profit).

Responsibilities:
- Evaluate existing positions for intelligent SELL decisions
- Detect profitable arbitrage opportunities for position exits
- Monitor positions for stop-loss and take-profit triggers
- Create sell decisions with proper reasoning and metadata
- Execute position exits through trade executor

This module was extracted from market_analyzer.py as part of v4.0+ refactoring
to keep individual files under 800 lines and improve maintainability.

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
from paper_trading.constants import DecisionType

# Type hints for external dependencies (avoid circular imports)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from paper_trading.intelligence.core.intel_slider import IntelSliderEngine
    from paper_trading.bot.price_service_integration import RealPriceManager
    from paper_trading.bot.position_manager import PositionManager
    from paper_trading.bot.trade_executor import TradeExecutor
    from paper_trading.models import PaperTradingAccount, PaperStrategyConfiguration

logger = logging.getLogger(__name__)


class PositionEvaluator:
    """
    Evaluates existing positions for intelligent exit decisions.

    This class analyzes open positions to determine if they should be closed
    based on changing market conditions, risk factors, arbitrage opportunities,
    or automatic safety triggers.

    Example usage:
        evaluator = PositionEvaluator(
            account=account,
            intelligence_engine=engine,
            strategy_config=config,
            arbitrage_enabled=True
        )

        # Check a specific position for sell signal
        evaluator.evaluate_position_for_sell(
            token_symbol='WETH',
            position=position,
            price_manager=price_manager,
            position_manager=position_manager,
            trade_executor=trade_executor,
            thought_logger=thought_logger
        )

        # Check all positions for auto-close triggers
        evaluator.check_auto_close_positions(
            price_manager=price_manager,
            position_manager=position_manager,
            trade_executor=trade_executor,
            thought_logger=thought_logger
        )
    """

    def __init__(
        self,
        account: 'PaperTradingAccount',
        intelligence_engine: 'IntelSliderEngine',
        strategy_config: Optional['PaperStrategyConfiguration'] = None,
        arbitrage_enabled: bool = False,
        dex_comparator: Optional[Any] = None,
        arbitrage_detector: Optional[Any] = None
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

        logger.info("[POSITION EVALUATOR] Initialized position evaluator")

    # =========================================================================
    # INTELLIGENT POSITION EVALUATION FOR SELLS
    # =========================================================================

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
        Evaluate an existing position for intelligent SELL decision.

        This is the INTELLIGENT sell check that runs BEFORE auto-close.
        It makes smart exit decisions based on:
        - Market conditions turning bearish
        - Risk increasing beyond comfort levels
        - Better opportunities elsewhere
        - Technical signals deteriorating
        - Profitable arbitrage opportunities

        Args:
            token_symbol: Token symbol to evaluate
            position: PaperPosition object
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
            thought_logger: Thought logger for AI decisions
        """
        try:
            # Get current price
            token_data = price_manager.get_token_price(token_symbol)
            if not token_data:
                logger.debug(f"[SELL CHECK] No price data for {token_symbol}")
                return

            # Handle both dict and Decimal return types
            if isinstance(token_data, dict):
                current_price = token_data.get('price')
                token_address = token_data.get('address', '')
            else:
                current_price = token_data
                token_address = getattr(position, 'token_address', '')

            if not current_price:
                logger.warning(f"[SELL CHECK] No current price for {token_symbol}")
                return

            # Get price history for volatility
            price_history = price_manager.get_price_history(token_symbol, limit=24)

            # Calculate position metrics
            avg_entry_price = position.average_entry_price_usd
            hold_time = timezone.now() - position.opened_at
            hold_time_hours = hold_time.total_seconds() / 3600

            # Calculate P&L
            invested = position.total_invested_usd
            current_value = position.current_value_usd
            pnl_percent = Decimal('0')
            if invested > 0:
                pnl_percent = ((current_value - invested) / invested) * Decimal('100')

            logger.debug(
                f"[SELL CHECK] Analyzing {token_symbol}: "
                f"entry=${avg_entry_price:.4f}, current=${current_price:.4f}, "
                f"P&L={pnl_percent:+.2f}%, hold={hold_time_hours:.1f}h"
            )

            # Get real market analysis for this token
            real_analysis = None
            try:
                real_analysis = async_to_sync(
                    self.intelligence_engine.analyzer.analyze_comprehensive
                )(
                    token_address=token_address,
                    trade_size_usd=Decimal(str(current_value)),
                    chain_id=self.intelligence_engine.chain_id,
                    price_history=[{'price': Decimal(str(p))} for p in price_history],
                    current_price=current_price
                )
            except Exception as e:
                logger.debug(f"[SELL CHECK] Could not get real analysis: {e}")

            # Build market context for sell evaluation
            if real_analysis:
                liquidity_data = real_analysis.get('liquidity', {})
                volatility_data = real_analysis.get('volatility', {})
                trend_data = real_analysis.get('trend', {})

                liquidity = Decimal(str(liquidity_data.get('total_liquidity_usd', 0)))
                volatility = Decimal(str(volatility_data.get('volatility_24h', 0)))
                trend_direction = trend_data.get('direction', 'unknown')
                data_quality = real_analysis.get('data_quality', 'UNKNOWN')
            else:
                # Fallback values
                liquidity = Decimal('0')
                volatility = Decimal('0')
                trend_direction = 'unknown'
                data_quality = 'INSUFFICIENT'

            # Create market context
            market_context = MarketContext(
                token_symbol=token_symbol,
                token_address=token_address,
                current_price=current_price,
                price_24h_ago=price_history[0] if price_history else current_price,
                liquidity_usd=liquidity,
                volatility=volatility,
                gas_price_gwei=Decimal('1.0'),
                trend_direction=trend_direction,
                confidence_in_data=100.0 if data_quality == 'GOOD' else 50.0
            )

            # Get existing positions for context
            all_positions = position_manager.get_all_positions()
            existing_positions = {
                sym: {
                    'quantity': float(pos.quantity),
                    'invested_usd': float(pos.total_invested_usd),
                    'current_value_usd': float(pos.current_value_usd)
                }
                for sym, pos in all_positions.items()
            }

            # Check for arbitrage opportunity (higher priority than market sentiment)
            arbitrage_opportunity = None
            if self.arbitrage_enabled and self.dex_comparator and self.arbitrage_detector:
                try:
                    # Check if we can sell this token at better price on another DEX
                    dex_prices = async_to_sync(self.dex_comparator.compare_prices)(
                        token_address=token_address,
                        token_symbol=token_symbol
                    )

                    if dex_prices and dex_prices.prices and len(dex_prices.prices) >= 2:
                        # Check arbitrage opportunity
                        arb_opp = self.arbitrage_detector.analyze_opportunity(
                            dex_prices=dex_prices.prices,
                            trade_size_usd=float(current_value)
                        )

                        if arb_opp and arb_opp.is_profitable:
                            arbitrage_opportunity = arb_opp
                            self.arbitrage_opportunities_found += 1
                            logger.info(
                                f"[ARBITRAGE] 🎯 Found profitable arbitrage for {token_symbol}: "
                                f"{arb_opp.price_spread_percent:.2f}% spread, "
                                f"${arb_opp.net_profit_usd:.2f} profit"
                            )

                except Exception as arb_error:
                    logger.debug(f"[ARBITRAGE] Could not check arbitrage: {arb_error}")

            # Ask intelligence engine: should we sell this position?
            decision = async_to_sync(self.intelligence_engine.make_decision)(
                market_context=market_context,
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

            # Calculate P&L for logging
            invested = position.total_invested_usd
            current_value = position.current_value_usd
            pnl_percent = Decimal('0')
            if invested > 0:
                pnl_percent = ((current_value - invested) / invested) * Decimal('100')

            # =====================================================================
            # DECISION OVERRIDE: Arbitrage takes precedence over market sentiment
            # =====================================================================
            should_sell = decision.action == 'SELL'
            sell_reason = decision.primary_reasoning
            decision_type = DecisionType.INTELLIGENT_EXIT

            # Override decision if profitable arbitrage exists
            if arbitrage_opportunity and arbitrage_opportunity.is_profitable:
                should_sell = True
                sell_reason = (
                    f"Arbitrage opportunity: {arbitrage_opportunity.price_spread_percent:.2f}% "
                    f"spread detected. Can sell on {arbitrage_opportunity.sell_dex} at "
                    f"${arbitrage_opportunity.sell_price:.4f} for "
                    f"${arbitrage_opportunity.net_profit_usd:.2f} profit after gas."
                )
                decision_type = DecisionType.ARBITRAGE_EXIT
                logger.info(
                    f"[ARBITRAGE] 🚀 Overriding decision to SELL {token_symbol} "
                    f"for arbitrage profit!"
                )

            # Check if we should execute the sell
            if should_sell:
                # No cooldown for SELL trades - exit immediately when signals trigger
                # Cooldown is only applied to BUY trades to prevent overtrading
                # SELL trades should execute ASAP to lock in profits or cut losses

                logger.info(
                    f"[SELL CHECK] 🎯 SELL signal for {token_symbol}: "
                    f"P&L={pnl_percent:+.2f}%, Hold={hold_time_hours:.1f}h, "
                    f"Type={decision_type}"
                )

                # Log the sell decision
                thought_logger.log_thought(
                    action='SELL',
                    reasoning=sell_reason,
                    confidence=float(decision.overall_confidence),
                    decision_type=decision_type,
                    metadata={
                        'token': token_symbol,
                        'token_address': token_address,
                        'current_price': float(current_price),
                        'entry_price': float(avg_entry_price),
                        'pnl_percent': float(pnl_percent),
                        'hold_hours': hold_time_hours,
                        'intel_level': int(self.intelligence_engine.intel_level),
                        'risk_score': float(decision.risk_score),
                        'opportunity_score': float(decision.opportunity_score),
                        'trend': trend_direction,
                        'data_quality': data_quality,
                        'arbitrage_opportunity': arbitrage_opportunity.to_dict() if arbitrage_opportunity else None
                    }
                )

                # Execute the sell
                success = trade_executor.execute_trade(
                    decision=decision,
                    token_symbol=token_symbol,
                    current_price=current_price,
                    position_manager=position_manager
                )

                if success:
                    # Track arbitrage trade if applicable
                    if decision_type == DecisionType.ARBITRAGE_EXIT:
                        self.arbitrage_trades_executed += 1

                    logger.info(
                        f"[SELL CHECK] ✅ Executed sell for {token_symbol}"
                    )
                else:
                    logger.warning(
                        f"[SELL CHECK] ❌ Failed to execute sell for {token_symbol}"
                    )
            else:
                logger.debug(
                    f"[SELL CHECK] Holding {token_symbol} "
                    f"(P&L={pnl_percent:+.2f}%, Action={decision.action})"
                )

        except Exception as e:
            logger.error(
                f"[SELL CHECK] Error evaluating position: {e}",
                exc_info=True
            )

    # =========================================================================
    # AUTO-CLOSE POSITIONS (STOP-LOSS / TAKE-PROFIT)
    # =========================================================================

    def check_auto_close_positions(
        self,
        price_manager: 'RealPriceManager',
        position_manager: 'PositionManager',
        trade_executor: 'TradeExecutor',
        thought_logger: Any
    ) -> None:
        """
        Check all open positions for stop-loss or take-profit triggers.

        This method runs on every tick to monitor position P&L and
        automatically close positions that hit configured thresholds.

        This is the SAFETY NET - hard thresholds that override intelligent decisions.
        The intelligent sell check (evaluate_position_for_sell) runs first and makes
        smarter decisions based on market conditions.

        Args:
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
            thought_logger: Thought logger for AI decisions
        """
        try:
            positions = position_manager.get_all_positions()

            for token_symbol, position in positions.items():
                # Get current price
                token_data = price_manager.get_token_price(token_symbol)
                if not token_data:
                    continue

                # Handle both dict and Decimal return types
                if isinstance(token_data, dict):
                    current_price = token_data.get('price')
                else:
                    # token_data is already a Decimal
                    current_price = token_data

                if not current_price:
                    continue

                # Calculate P&L percentage
                entry_price = position.average_entry_price_usd
                pnl_percent = ((current_price - entry_price) / entry_price) * Decimal('100')

                # Get configured thresholds
                if self.strategy_config:
                    stop_loss = self.strategy_config.stop_loss_percent
                    take_profit = self.strategy_config.take_profit_percent
                else:
                    # Use defaults if no config
                    stop_loss = Decimal('5.0')
                    take_profit = Decimal('15.0')

                # Check stop-loss
                if pnl_percent <= -stop_loss:
                    logger.warning(
                        f"[AUTO-CLOSE] Stop-loss triggered for {token_symbol}: "
                        f"{pnl_percent:.2f}% (threshold: -{stop_loss}%)"
                    )

                    token_address = getattr(position, 'token_address', '')

                    # Log the auto-close decision
                    thought_logger.log_thought(
                        action='SELL',
                        reasoning=f"Stop-loss triggered at {pnl_percent:.2f}% loss",
                        confidence=100.0,  # Hard threshold = 100% confidence
                        decision_type=DecisionType.STOP_LOSS,
                        metadata={
                            'token': token_symbol,
                            'current_price': float(current_price),
                            'entry_price': float(entry_price),
                            'pnl_percent': float(pnl_percent),
                            'stop_loss_threshold': float(stop_loss)
                        }
                    )

                    # Create a simple SELL decision for executor
                    sell_decision = TradingDecision(
                        action='SELL',
                        token_address=token_address or '',
                        token_symbol=token_symbol,
                        position_size_percent=Decimal('0'),
                        position_size_usd=Decimal('0'),
                        stop_loss_percent=Decimal('0'),
                        take_profit_targets=[],
                        execution_mode='FAST_LANE',
                        use_private_relay=False,
                        gas_strategy='standard',
                        max_gas_price_gwei=Decimal('50'),
                        overall_confidence=Decimal('100'),
                        risk_score=Decimal('0'),
                        opportunity_score=Decimal('0'),
                        primary_reasoning=f"Stop-loss triggered at {pnl_percent:.2f}% loss",
                        risk_factors=[f"Stop-loss triggered at {pnl_percent:.2f}%"],
                        opportunity_factors=[],
                        mitigation_strategies=[],
                        intel_level_used=self.intelligence_engine.intel_level,
                        intel_adjustments={},
                        time_sensitivity='critical',
                        max_execution_time_ms=5000
                    )

                    trade_executor.execute_trade(
                        decision=sell_decision,
                        token_symbol=token_symbol,
                        current_price=current_price,
                        position_manager=position_manager
                    )

                # Check take-profit
                elif pnl_percent >= take_profit:
                    logger.info(
                        f"[AUTO-CLOSE] Take-profit triggered for {token_symbol}: "
                        f"{pnl_percent:.2f}% (threshold: +{take_profit}%)"
                    )

                    token_address = getattr(position, 'token_address', '')

                    # Log the auto-close decision
                    thought_logger.log_thought(
                        action='SELL',
                        reasoning=f"Take-profit triggered at {pnl_percent:.2f}% gain",
                        confidence=100.0,  # Hard threshold = 100% confidence
                        decision_type=DecisionType.TAKE_PROFIT,
                        metadata={
                            'token': token_symbol,
                            'current_price': float(current_price),
                            'entry_price': float(entry_price),
                            'pnl_percent': float(pnl_percent),
                            'take_profit_threshold': float(take_profit)
                        }
                    )

                    # Create a simple SELL decision for executor
                    sell_decision = TradingDecision(
                        action='SELL',
                        token_address=token_address or '',
                        token_symbol=token_symbol,
                        position_size_percent=Decimal('0'),
                        position_size_usd=Decimal('0'),
                        stop_loss_percent=None,  # No stop-loss for exit trade
                        take_profit_targets=[],
                        execution_mode='FAST_LANE',
                        use_private_relay=False,
                        gas_strategy='standard',
                        max_gas_price_gwei=Decimal('50'),
                        overall_confidence=Decimal('100'),
                        risk_score=Decimal('0'),
                        opportunity_score=Decimal('0'),
                        primary_reasoning=f"Take-profit triggered at {pnl_percent:.2f}% gain",
                        risk_factors=[],
                        opportunity_factors=[f"Take-profit target reached: {pnl_percent:.2f}%"],
                        mitigation_strategies=[],
                        intel_level_used=self.intelligence_engine.intel_level,
                        intel_adjustments={},
                        time_sensitivity='high',
                        max_execution_time_ms=10000
                    )

                    trade_executor.execute_trade(
                        decision=sell_decision,
                        token_symbol=token_symbol,
                        current_price=current_price,
                        position_manager=position_manager
                    )

        except Exception as e:
            logger.error(
                f"[POSITION EVALUATOR] Failed to check auto-close positions: {e}",
                exc_info=True
            )

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_arbitrage_stats(self) -> Dict[str, Any]:
        """
        Get arbitrage detection statistics.

        Returns:
            Dictionary with arbitrage performance metrics
        """
        return {
            'opportunities_found': self.arbitrage_opportunities_found,
            'trades_executed': self.arbitrage_trades_executed,
            'success_rate': (
                (self.arbitrage_trades_executed / self.arbitrage_opportunities_found * 100)
                if self.arbitrage_opportunities_found > 0
                else 0.0
            )
        }