"""
Position Evaluator for Paper Trading Bot - Intelligent Sell Logic Module

This module evaluates existing positions for intelligent sell opportunities.
Unlike hard stop-loss/take-profit thresholds, this uses AI analysis to make
smart exit decisions based on:
- Market conditions turning bearish
- Risk increasing beyond comfort levels
- Better opportunities elsewhere (including arbitrage)
- Technical signals deteriorating
- Position performance and hold time

File: dexproject/paper_trading/bot/position_evaluator.py
"""

import logging
from decimal import Decimal
from typing import Optional, Any

from django.utils import timezone
from asgiref.sync import async_to_sync

from paper_trading.models import PaperTradingAccount
from paper_trading.intelligence.core.base import MarketContext
from paper_trading.intelligence.core.intel_slider import IntelSliderEngine

logger = logging.getLogger(__name__)


class PositionEvaluator:
    """
    Evaluates existing positions for intelligent sell opportunities.
    
    This class uses the intelligence engine to analyze open positions and
    determine if market conditions suggest it's time to exit. This is
    DIFFERENT from auto-close (stop-loss/take-profit) which uses hard
    thresholds. This makes intelligent, AI-driven decisions.
    
    Key Features:
    - AI-powered exit timing analysis
    - Arbitrage opportunity detection for better exit prices
    - Market sentiment evaluation
    - Position performance tracking
    - Intelligent decision override (arbitrage > sentiment)
    """

    def __init__(
        self,
        account: PaperTradingAccount,
        intelligence_engine: IntelSliderEngine,
        arbitrage_detector: Optional[Any] = None,
        dex_comparator: Optional[Any] = None,
        check_arbitrage: bool = False
    ) -> None:
        """
        Initialize Position Evaluator.
        
        Args:
            account: Paper trading account
            intelligence_engine: Intelligence engine for decision making
            arbitrage_detector: Optional arbitrage detector
            dex_comparator: Optional DEX price comparator
            check_arbitrage: Whether to check for arbitrage opportunities
        """
        self.account = account
        self.intelligence_engine = intelligence_engine
        self.arbitrage_detector = arbitrage_detector
        self.dex_comparator = dex_comparator
        self.check_arbitrage = check_arbitrage
        
        # Track arbitrage stats
        self.arbitrage_opportunities_found = 0
        self.arbitrage_trades_executed = 0
        
        logger.info(
            f"[POSITION EVALUATOR] Initialized for account: {account.account_id}"
        )

    # =========================================================================
    # INTELLIGENT POSITION SELL CHECK
    # =========================================================================

    def check_position_sells(
        self,
        price_manager: Any,
        position_manager: Any,
        trade_executor: Any
    ) -> None:
        """
        Evaluate existing positions for intelligent sell opportunities.

        This method analyzes each open position using the same intelligence
        engine that makes buy decisions, but focused on exit timing:
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
        """
        try:
            # Get all open positions
            positions = position_manager.get_all_positions()

            if not positions:
                logger.debug("[SELL CHECK] No open positions to evaluate")
                return

            logger.info(f"[SELL CHECK] Evaluating {len(positions)} positions for sell signals")

            # Evaluate each position
            for token_symbol, position in positions.items():
                self._evaluate_position_for_sell(
                    token_symbol=token_symbol,
                    position=position,
                    price_manager=price_manager,
                    position_manager=position_manager,
                    trade_executor=trade_executor
                )

        except Exception as e:
            logger.error(
                f"[SELL CHECK] Error checking position sells: {e}",
                exc_info=True
            )

    def _evaluate_position_for_sell(
        self,
        token_symbol: str,
        position: Any,
        price_manager: Any,
        position_manager: Any,
        trade_executor: Any
    ) -> None:
        """
        Evaluate a single position for intelligent sell decision.

        Uses the intelligence engine to analyze whether market conditions
        suggest it's time to exit this position.

        Args:
            token_symbol: Token symbol
            position: Position object
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
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
            if self.check_arbitrage and self.dex_comparator and self.arbitrage_detector:
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

            # =====================================================================
            # DECISION OVERRIDE: Arbitrage takes precedence over market sentiment
            # =====================================================================
            should_sell = decision.action == 'SELL'
            sell_reason = decision.primary_reasoning
            decision_type = "INTELLIGENT_EXIT"

            # Override decision if profitable arbitrage exists
            if arbitrage_opportunity and arbitrage_opportunity.is_profitable:
                should_sell = True
                sell_reason = (
                    f"Arbitrage opportunity: {arbitrage_opportunity.price_spread_percent:.2f}% "
                    f"spread detected. Can sell on {arbitrage_opportunity.sell_dex} at "
                    f"${arbitrage_opportunity.sell_price:.4f} for "
                    f"${arbitrage_opportunity.net_profit_usd:.2f} profit after gas."
                )
                decision_type = "ARBITRAGE_EXIT"
                logger.info(
                    f"[ARBITRAGE] 🚀 Overriding decision to SELL {token_symbol} "
                    f"for arbitrage profit!"
                )

            # Check if we should execute the sell
            if should_sell:
                # Note: No cooldown for SELL trades - exit immediately when signals trigger
                # Cooldown is only applied to BUY trades to prevent overtrading
                # SELL trades should execute ASAP to lock in profits or cut losses
                
                logger.info(
                    f"[SELL CHECK] 🎯 SELL signal for {token_symbol}: "
                    f"P&L={pnl_percent:+.2f}%, Hold={hold_time_hours:.1f}h, "
                    f"Type={decision_type}"
                )

                # Log the sell decision (imported from market_helpers)
                from paper_trading.bot.market_helpers import MarketHelpers
                helpers = MarketHelpers(
                    account=self.account,
                    intelligence_engine=self.intelligence_engine
                )
                
                helpers.log_thought(
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
                    if decision_type == "ARBITRAGE_EXIT":
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