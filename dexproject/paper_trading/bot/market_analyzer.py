"""
Market Analyzer for Paper Trading Bot - REAL DATA INTEGRATION + INTELLIGENT SELLS

ENHANCED: Now evaluates existing positions for intelligent SELL decisions based on:
- Market conditions turning bearish
- Risk increasing beyond comfort levels
- Better opportunities elsewhere
- Technical signals deteriorating
- Position performance and hold time

This module handles market analysis operations for the paper trading bot,
including tick coordination, token analysis, performance metrics, and
AI thought logging.

Responsibilities:
- Coordinate market ticks (main bot loop)
- Analyze individual tokens with REAL market data
- Evaluate existing positions for intelligent sells (NEW!)
- Update market prices (via price service integration)
- Check pending transactions (TX Manager)
- Update performance metrics
- Log AI thought processes
- Send bot status updates via WebSocket

File: dexproject/paper_trading/bot/market_analyzer.py
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Any

from django.utils import timezone
from asgiref.sync import async_to_sync

from paper_trading.models import (
    PaperTradingAccount,
    PaperTradingSession,
    PaperStrategyConfiguration,
    PaperPerformanceMetrics,
    PaperTrade
)

# Import intelligence types
from paper_trading.intelligence.base import (
    MarketContext,
    TradingDecision
)
from paper_trading.intelligence.intel_slider import IntelSliderEngine

# Import WebSocket service
from paper_trading.services.websocket_service import websocket_service

# Import Transaction Manager status (optional)
try:
    import trading.services.transaction_manager  # noqa: F401
    TRANSACTION_MANAGER_AVAILABLE = True
except ImportError:
    TRANSACTION_MANAGER_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# MARKET ANALYZER CLASS
# =============================================================================

class MarketAnalyzer:
    """
    Handles market analysis and tick coordination for paper trading bot.

    This class manages the main bot loop and coordinates all market-related
    operations including price updates, token analysis, and decision making.

    NOW WITH REAL DATA INTEGRATION: Calls CompositeMarketAnalyzer to get
    actual blockchain data for gas, liquidity, volatility, and MEV analysis.

    ENHANCED WITH INTELLIGENT SELLS: Evaluates existing positions for smart
    exit decisions based on changing market conditions, not just fixed thresholds.

    Example usage:
        analyzer = MarketAnalyzer(
            account=account,
            session=session,
            intelligence_engine=engine,
            strategy_config=config
        )

        # Run a single market tick
        analyzer.tick(
            price_manager=price_manager,
            position_manager=position_manager,
            trade_executor=trade_executor
        )
    """

    def __init__(
        self,
        account: PaperTradingAccount,
        session: PaperTradingSession,
        intelligence_engine: IntelSliderEngine,
        strategy_config: Optional[PaperStrategyConfiguration] = None,
        circuit_breaker_manager: Optional[Any] = None,
        use_tx_manager: bool = False
    ):
        """
        Initialize the Market Analyzer.

        Args:
            account: Paper trading account
            session: Current trading session
            intelligence_engine: Intelligence engine for decision making
            strategy_config: Optional strategy configuration
            circuit_breaker_manager: Optional circuit breaker manager
            use_tx_manager: Whether to use Transaction Manager
        """
        self.account = account
        self.session = session
        self.intelligence_engine = intelligence_engine
        self.strategy_config = strategy_config
        self.circuit_breaker_manager = circuit_breaker_manager
        self.use_tx_manager = use_tx_manager

        self.tick_count = 0
        self.last_decisions: Dict[str, TradingDecision] = {}
        self.pending_transactions: List[Any] = []

        logger.info(
            f"[MARKET ANALYZER] Initialized for account: {account.account_id}"
        )

    # =========================================================================
    # MAIN TICK METHOD
    # =========================================================================

    def tick(
        self,
        price_manager: Any,
        position_manager: Any,
        trade_executor: Any
    ):
        """
        Execute one market tick cycle.

        This method coordinates all trading operations including:
        - Updating prices
        - Checking circuit breakers
        - Evaluating positions for intelligent sells (NEW!)
        - Checking auto-close positions (stop-loss/take-profit)
        - Analyzing tokens for buy opportunities
        - Executing trades
        - Updating metrics

        Args:
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
        """
        self.tick_count += 1
        logger.info("\n" + "=" * 60)
        logger.info(f"[TICK] Market tick #{self.tick_count}")

        # Check circuit breaker status
        if self.circuit_breaker_manager:
            can_trade, reasons = self.circuit_breaker_manager.can_trade()
            if not can_trade:
                logger.warning(
                    f"[CB] Circuit breakers active: {', '.join(reasons)}"
                )
                logger.info(
                    "[CB] Skipping trading analysis due to circuit breakers"
                )

                # Still update market prices for tracking
                self._update_market_prices(price_manager)
                position_manager.update_position_prices(
                    price_manager.get_token_list()
                )

                # Check for auto-close even when circuit breakers active
                self._check_auto_close_positions(
                    price_manager,
                    position_manager,
                    trade_executor
                )

                # Send status update
                self._send_bot_status_update(
                    'circuit_breaker_active',
                    price_manager,
                    position_manager,
                    trade_executor
                )
                return

        # Check pending transactions if TX Manager is enabled
        if self.use_tx_manager and self.pending_transactions:
            self._check_pending_transactions(trade_executor)

        # Normal tick processing
        self._update_market_prices(price_manager)
        position_manager.update_position_prices(price_manager.get_token_list())

        # =====================================================================
        # NEW: Check existing positions for intelligent SELL decisions
        # This evaluates positions based on market conditions, not just P&L
        # =====================================================================
        self._check_position_sells(
            price_manager,
            position_manager,
            trade_executor
        )

        # Check for positions to auto-close (stop-loss/take-profit)
        # This is the safety net - hard thresholds
        self._check_auto_close_positions(
            price_manager,
            position_manager,
            trade_executor
        )

        # Analyze each token for trading opportunities
        token_list = price_manager.get_token_list()
        for token_data in token_list:
            try:
                self._analyze_token(
                    token_data,
                    price_manager,
                    position_manager,
                    trade_executor
                )
            except Exception as e:
                logger.error(
                    f"[MARKET ANALYZER] Error analyzing token "
                    f"{token_data.get('symbol', 'UNKNOWN')}: {e}",
                    exc_info=True
                )

        # Update performance metrics periodically
        if self.tick_count % 20 == 0:
            self._update_performance_metrics(trade_executor)

        # Send bot status update
        self._send_bot_status_update(
            'running',
            price_manager,
            position_manager,
            trade_executor
        )

        logger.info(f"[TICK] Market tick #{self.tick_count} complete\n")

    # =========================================================================
    # INTELLIGENT POSITION SELL EVALUATION (NEW!)
    # =========================================================================

    def _check_position_sells(
        self,
        price_manager: Any,
        position_manager: Any,
        trade_executor: Any
    ):
        """
        Check all open positions for intelligent SELL decisions.

        This method evaluates each position using the intelligence engine
        to determine if market conditions warrant selling, considering:
        - Market trend changes (bearish turn)
        - Risk level increases
        - Opportunity deterioration
        - Position hold time
        - Current P&L performance

        This is DIFFERENT from auto-close (stop-loss/take-profit) because
        it uses intelligent market analysis, not just fixed thresholds.

        Args:
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
        """
        try:
            positions = position_manager.get_all_positions()
            
            if not positions:
                logger.debug("[SELL CHECK] No positions to evaluate")
                return

            logger.info(
                f"[SELL CHECK] Evaluating {len(positions)} position(s) "
                "for intelligent sell opportunities"
            )

            for token_symbol, position in positions.items():
                try:
                    self._evaluate_position_for_sell(
                        position,
                        price_manager,
                        position_manager,
                        trade_executor
                    )
                except Exception as e:
                    logger.error(
                        f"[SELL CHECK] Error evaluating {token_symbol} position: {e}",
                        exc_info=True
                    )

        except Exception as e:
            logger.error(
                f"[SELL CHECK] Failed to check position sells: {e}",
                exc_info=True
            )

    def _evaluate_position_for_sell(
        self,
        position: Any,
        price_manager: Any,
        position_manager: Any,
        trade_executor: Any
    ):
        """
        Evaluate a single position for intelligent sell decision.

        Args:
            position: Position object to evaluate
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
        """
        try:
            token_symbol = position.token_symbol
            token_address = position.token_address

            # Get current price
            token_data = price_manager.get_token_price(token_symbol)
            if not token_data:
                logger.debug(
                    f"[SELL CHECK] No price data for {token_symbol}, skipping"
                )
                return

            # Handle both dict and Decimal return types
            if isinstance(token_data, dict):
                current_price = token_data.get('price')
            else:
                current_price = token_data

            if not current_price:
                return

            logger.debug(
                f"[SELL CHECK] Evaluating {token_symbol} position at ${current_price:.2f}"
            )

            # Calculate position metrics
            avg_entry_price = position.average_entry_price_usd
            current_value = position.current_value_usd
            invested = position.total_invested_usd
            
            # Calculate hold time
            hold_time_hours = 0.0
            if hasattr(position, 'opened_at') and position.opened_at:
                hold_duration = timezone.now() - position.opened_at
                hold_time_hours = hold_duration.total_seconds() / 3600

            # Get price history for volatility
            price_history = price_manager.get_price_history(token_symbol, limit=24)
            price_24h_ago = price_history[0] if price_history else current_price

            # Get comprehensive market analysis
            initial_trade_size = current_value  # Size of position we'd be selling
            real_analysis = None
            
            try:
                logger.debug(
                    f"[SELL CHECK] Getting market analysis for {token_symbol}..."
                )
                
                real_analysis = async_to_sync(
                    self.intelligence_engine.analyzer.analyze_comprehensive
                )(
                    token_address=token_address,
                    trade_size_usd=initial_trade_size,
                    chain_id=self.intelligence_engine.chain_id,
                    price_history=[Decimal(str(p)) for p in price_history],
                    current_price=current_price
                )
                
            except Exception as e:
                logger.warning(
                    f"[SELL CHECK] Failed to get analysis for {token_symbol}: {e}"
                )

            # Build market context
            if real_analysis:
                liquidity_analysis = real_analysis.get('liquidity', {})
                volatility_analysis = real_analysis.get('volatility', {})
                
                liquidity_value = liquidity_analysis.get('pool_liquidity_usd')
                liquidity_usd = (
                    Decimal(str(liquidity_value))
                    if liquidity_value and liquidity_value == liquidity_value  # Check for NaN
                    else Decimal('5000000')
                )
                
                volatility_value = volatility_analysis.get('volatility_24h_percent', 15.0)
                volatility = (
                    Decimal(str(volatility_value)) / Decimal('100')
                    if volatility_value and volatility_value == volatility_value  # Check for NaN
                    else Decimal('0.15')
                )
                
                trend_direction = volatility_analysis.get('trend_direction', 'neutral')
                volume_24h = liquidity_usd * volatility * Decimal('10')
                data_quality = real_analysis.get('data_quality', 'UNKNOWN')
            else:
                liquidity_usd = Decimal('5000000')
                volume_24h = Decimal('1000000')
                volatility = Decimal('0.15')
                trend_direction = 'neutral'
                data_quality = 'FALLBACK'

            # Create market context
            market_context = MarketContext(
                token_address=token_address,
                token_symbol=token_symbol,
                current_price=current_price,
                price_24h_ago=price_24h_ago,
                volume_24h=volume_24h,
                liquidity_usd=liquidity_usd,
                holder_count=1000,
                market_cap=Decimal('50000000'),
                volatility=volatility,
                trend=trend_direction,
                momentum=Decimal('0'),
                support_levels=[],
                resistance_levels=[],
                timestamp=timezone.now()
            )

            # Get existing positions for context
            existing_positions = [
                {
                    'token_symbol': pos.token_symbol,
                    'quantity': float(pos.quantity),
                    'invested_usd': float(pos.total_invested_usd)
                }
                for pos in position_manager.get_all_positions().values()
            ]

            # Update engine with market context
            self.intelligence_engine.update_market_context(market_context)

            # Make intelligent decision with POSITION DATA
            # This is the key: we're passing position information!
            decision = async_to_sync(self.intelligence_engine.make_decision)(
                market_context=market_context,
                account_balance=self.account.current_balance_usd,
                existing_positions=existing_positions,
                token_address=token_address,
                token_symbol=token_symbol,
                # NEW: Pass position data for sell evaluation
                has_position=True,
                position_entry_price=avg_entry_price,
                position_current_value=current_value,
                position_invested=invested,
                position_hold_time_hours=hold_time_hours
            )

            # Calculate P&L for logging
            pnl_percent = Decimal('0')
            if invested > 0:
                pnl_percent = ((current_value - invested) / invested) * Decimal('100')

            # If decision is SELL, execute it
            if decision.action == 'SELL':
                logger.info(
                    f"[SELL CHECK] 🎯 Intelligent SELL signal for {token_symbol}: "
                    f"P&L={pnl_percent:+.2f}%, Hold={hold_time_hours:.1f}h"
                )
                
                # Log the intelligent sell decision
                self._log_thought(
                    action='SELL',
                    reasoning=decision.primary_reasoning,
                    confidence=float(decision.overall_confidence),
                    decision_type="INTELLIGENT_EXIT",
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
                        'data_quality': data_quality
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
                    logger.info(
                        f"[SELL CHECK] ✅ Executed intelligent sell for {token_symbol}"
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
    # TOKEN ANALYSIS WITH REAL DATA INTEGRATION
    # =========================================================================

    def _analyze_token(
        self,
        token_data: Dict[str, Any],
        price_manager: Any,
        position_manager: Any,
        trade_executor: Any
    ):
        """
        Analyze a single token and make trading decision using REAL blockchain data.

        FIXED: Now calls CompositeMarketAnalyzer.analyze_comprehensive() to get
        REAL data from:
        - Gas prices (from blockchain RPC)
        - Pool liquidity (from Uniswap V3)
        - Price volatility (from historical data)
        - MEV threats (smart heuristics based on real liquidity)

        ENHANCED: Now passes position information to decision maker for better
        position sizing and entry decisions.

        Args:
            token_data: Token data with current price
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
        """
        try:
            # Handle both dict and direct values
            if isinstance(token_data, dict):
                token_symbol = token_data.get('symbol')
                token_address = token_data.get('address')
                current_price = token_data.get('price')
            else:
                # If token_data is not a dict, skip this token
                logger.warning(
                    f"[ANALYZE] token_data is not a dict: {type(token_data)}. Skipping."
                )
                return

            # Validate we have the required data
            if not all([token_symbol, token_address, current_price]):
                logger.warning(
                    f"[ANALYZE] Missing required token data. "
                    f"Symbol={token_symbol}, Address={token_address}, Price={current_price}"
                )
                return

            logger.info(
                f"[ANALYZE] Analyzing {token_symbol} at ${current_price:.2f} "
                f"using REAL blockchain data"
            )

            # Get price history for volatility calculation
            price_history = price_manager.get_price_history(token_symbol, limit=24)
            price_24h_ago = price_history[0] if price_history else current_price

            # Calculate initial trade size (before real analysis)
            initial_trade_size = self._calculate_initial_trade_size(
                token_symbol,
                current_price,
                position_manager
            )

            # ✅ CALL REAL MARKET ANALYZER
            # This is the FIX - we now actually call the analyzer!
            real_analysis = None
            try:
                logger.info(
                    f"[REAL DATA] Calling CompositeMarketAnalyzer for {token_symbol}..."
                )

                # Call the comprehensive analysis with real data
                real_analysis = async_to_sync(
                    self.intelligence_engine.analyzer.analyze_comprehensive
                )(
                    token_address=token_address,
                    trade_size_usd=initial_trade_size,
                    chain_id=self.intelligence_engine.chain_id,
                    price_history=[Decimal(str(p)) for p in price_history],
                    current_price=current_price
                )

                logger.info(
                    f"[REAL DATA] ✅ Got real analysis for {token_symbol}: "
                    f"Quality={real_analysis.get('data_quality', 'UNKNOWN')}"
                )

            except Exception as e:
                logger.error(
                    f"[REAL DATA] Failed to get real analysis for {token_symbol}: {e}",
                    exc_info=True
                )
                real_analysis = None

            # Extract real data from analysis or use fallbacks
            if real_analysis:
                # Use REAL values from blockchain analysis
                liquidity_analysis = real_analysis.get('liquidity', {})
                volatility_analysis = real_analysis.get('volatility', {})
                # gas_analysis = real_analysis.get('gas_analysis', {})  # Available if needed
                # mev_analysis = real_analysis.get('mev_analysis', {})  # Available if needed

                # Extract real values - handle None properly
                liquidity_value = liquidity_analysis.get('pool_liquidity_usd')
                if liquidity_value is None or (isinstance(liquidity_value, float) and (liquidity_value != liquidity_value)):  # Check for None or NaN
                    liquidity_usd = Decimal('5000000')  # Default fallback
                else:
                    liquidity_usd = Decimal(str(liquidity_value))

                volatility_value = volatility_analysis.get('volatility_24h_percent', 15.0)
                if volatility_value is None or (isinstance(volatility_value, float) and (volatility_value != volatility_value)):  # Check for None or NaN
                    volatility = Decimal('0.15')  # 15% default
                else:
                    volatility = Decimal(str(volatility_value)) / Decimal('100')  # Convert to decimal (15% -> 0.15)
                trend_direction = volatility_analysis.get('trend_direction', 'neutral')

                # Calculate volume estimate from liquidity and volatility
                # Higher liquidity + higher volatility = more volume
                volume_24h = liquidity_usd * volatility * Decimal('10')

                data_quality = real_analysis.get('data_quality', 'UNKNOWN')

                logger.info(
                    f"[REAL DATA] {token_symbol} market data: "
                    f"Liquidity=${liquidity_usd:,.0f}, "
                    f"Volatility={float(volatility)*100:.1f}%, "
                    f"Trend={trend_direction}, "
                    f"Quality={data_quality}"
                )
            else:
                # Fallback to conservative estimates
                liquidity_usd = Decimal('5000000')
                volume_24h = Decimal('1000000')
                volatility = Decimal('0.15')
                trend_direction = 'neutral'
                data_quality = 'FALLBACK'

                logger.warning(
                    f"[REAL DATA] Using fallback data for {token_symbol}"
                )

            # Create market context with REAL or fallback data
            market_context = MarketContext(
                token_address=token_address,
                token_symbol=token_symbol,
                current_price=current_price,
                price_24h_ago=price_24h_ago,
                volume_24h=volume_24h,  # ✅ Real or calculated
                liquidity_usd=liquidity_usd,  # ✅ Real from Uniswap V3
                holder_count=1000,  # Still simulated (not on-chain for Base)
                market_cap=Decimal('50000000'),  # Still simulated
                volatility=volatility,  # ✅ Real from price history
                trend=trend_direction,  # ✅ Real from price analysis
                momentum=Decimal('0'),  # Could calculate from price history
                support_levels=[],  # Could calculate from price history
                resistance_levels=[],  # Could calculate from price history
                timestamp=timezone.now()
            )

            # Get existing positions for context
            existing_positions = [
                {
                    'token_symbol': pos.token_symbol,
                    'quantity': float(pos.quantity),
                    'invested_usd': float(pos.total_invested_usd)
                }
                for pos in position_manager.get_all_positions().values()
            ]

            # Check if we have a position in this token
            existing_position = position_manager.get_position(token_symbol)
            has_position = existing_position is not None

            # Update engine with market context (for trend tracking)
            self.intelligence_engine.update_market_context(market_context)

            # Make trading decision with real market data
            # ENHANCED: Now passes position information
            if has_position:
                # We have a position - pass position data
                hold_time_hours = 0.0
                if hasattr(existing_position, 'opened_at') and existing_position.opened_at:
                    hold_duration = timezone.now() - existing_position.opened_at
                    hold_time_hours = hold_duration.total_seconds() / 3600

                decision = async_to_sync(self.intelligence_engine.make_decision)(
                    market_context=market_context,
                    account_balance=self.account.current_balance_usd,
                    existing_positions=existing_positions,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    has_position=True,
                    position_entry_price=existing_position.average_entry_price_usd,
                    position_current_value=existing_position.current_value_usd,
                    position_invested=existing_position.total_invested_usd,
                    position_hold_time_hours=hold_time_hours
                )
            else:
                # No position - evaluate for BUY
                decision = async_to_sync(self.intelligence_engine.make_decision)(
                    market_context=market_context,
                    account_balance=self.account.current_balance_usd,
                    existing_positions=existing_positions,
                    token_address=token_address,
                    token_symbol=token_symbol
                )

            # Log the decision
            self._log_thought(
                action=decision.action,
                reasoning=decision.primary_reasoning,
                confidence=float(decision.overall_confidence),
                decision_type="TRADE_DECISION",
                metadata={
                    'token': token_symbol,
                    'token_address': token_address,
                    'current_price': float(current_price),
                    'intel_level': int(self.intelligence_engine.intel_level),
                    'risk_score': float(decision.risk_score),
                    'opportunity_score': float(decision.opportunity_score),
                    'data_quality': data_quality,
                    'liquidity_usd': float(liquidity_usd),
                    'volatility': float(volatility),
                    'trend': trend_direction,
                    'has_position': has_position,
                    'tx_manager_enabled': self.use_tx_manager
                }
            )

            # Execute if not HOLD or SKIP
            if decision.action != 'HOLD' and decision.action != 'SKIP':
                logger.info(
                    f"[DECISION] {decision.action} {token_symbol}: "
                    f"{decision.primary_reasoning}"
                )
            
            if decision.action in ['BUY', 'SELL']:
                trade_executor.execute_trade(
                    decision=decision,
                    token_symbol=token_symbol,
                    current_price=current_price,
                    position_manager=position_manager
                )

            # Track the decision
            self.last_decisions[token_symbol] = decision

        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Failed to analyze token {token_data.get('symbol', 'UNKNOWN')}: {e}",
                exc_info=True
            )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _update_market_prices(self, price_manager: Any):
        """
        Update market prices for all tokens.

        This method refreshes price data from the price service to ensure
        we have the latest market information.

        Args:
            price_manager: RealPriceManager instance
        """
        try:
            logger.debug("[PRICES] Updating market prices...")
            price_manager.update_prices()
            logger.debug("[PRICES] Market prices updated successfully")
        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Failed to update market prices: {e}",
                exc_info=True
            )

    def _calculate_initial_trade_size(
        self,
        token_symbol: str,
        current_price: Decimal,
        position_manager: Any
    ) -> Decimal:
        """
        Calculate initial trade size for a token before detailed analysis.

        This provides a preliminary trade size estimate used in the real
        market analysis call. The actual trade size may be adjusted based
        on risk analysis and intelligence level.

        Args:
            token_symbol: Token symbol
            current_price: Current token price
            position_manager: PositionManager instance

        Returns:
            Preliminary trade size in USD
        """
        try:
            # Base trade size is 5% of account balance
            base_trade_size = self.account.current_balance_usd * Decimal('0.05')

            # Check if we already have a position
            existing_position = position_manager.get_position(token_symbol)
            if existing_position:
                # Already have position, use smaller size for averaging
                return base_trade_size * Decimal('0.5')

            return base_trade_size

        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Error calculating trade size for {token_symbol}: {e}"
            )
            # Return safe default
            return Decimal('500')
        
    def _calculate_confidence_level(self, confidence_percent: float) -> str:
        """Calculate confidence level category from percentage."""
        if confidence_percent >= 90:
            return 'VERY_HIGH'
        elif confidence_percent >= 70:
            return 'HIGH'
        elif confidence_percent >= 50:
            return 'MEDIUM'
        elif confidence_percent >= 30:
            return 'LOW'
        else:
            return 'VERY_LOW'

    # =========================================================================
    # AUTO-CLOSE POSITIONS (STOP-LOSS / TAKE-PROFIT)
    # =========================================================================

    def _check_auto_close_positions(
        self,
        price_manager: Any,
        position_manager: Any,
        trade_executor: Any
    ):
        """
        Check all open positions for stop-loss or take-profit triggers.

        This method runs on every tick to monitor position P&L and
        automatically close positions that hit configured thresholds.

        This is the SAFETY NET - hard thresholds that override intelligent decisions.
        The intelligent sell check (_check_position_sells) runs first and makes
        smarter decisions based on market conditions.

        Args:
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
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
                avg_entry = position.average_entry_price_usd
                pnl_percent = ((current_price - avg_entry) / avg_entry) * 100

                # Check stop-loss
                if self.strategy_config and self.strategy_config.stop_loss_percent:
                    if pnl_percent <= -float(self.strategy_config.stop_loss_percent):
                        logger.warning(
                            f"[AUTO-CLOSE] Stop-loss triggered for {token_symbol}: "
                            f"{pnl_percent:.2f}% loss"
                        )
                        self._execute_auto_close(
                            position,
                            position_manager,
                            trade_executor,
                            current_price,
                            'STOP_LOSS',
                            pnl_percent
                        )
                        continue

                # Check take-profit
                if self.strategy_config and self.strategy_config.take_profit_percent:
                    if pnl_percent >= float(self.strategy_config.take_profit_percent):
                        logger.info(
                            f"[AUTO-CLOSE] Take-profit triggered for {token_symbol}: "
                            f"{pnl_percent:.2f}% profit"
                        )
                        self._execute_auto_close(
                            position,
                            position_manager,
                            trade_executor,
                            current_price,
                            'TAKE_PROFIT',
                            pnl_percent
                        )
                        continue

        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Failed to check auto-close positions: {e}",
                exc_info=True
            )



    def _execute_auto_close(
        self,
        position: Any,
        position_manager: Any,
        trade_executor: Any,
        current_price: Decimal,
        reason: str,
        pnl_percent: float
    ):
        """
        Execute an auto-close for a position.

        Args:
            position: Position object to close
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
            current_price: Current token price
            reason: Reason for close ('STOP_LOSS' or 'TAKE_PROFIT')
            pnl_percent: P&L percentage
        """
        try:
            token_symbol = position.token_symbol

            # Create SELL decision for auto-close
            decision = TradingDecision(
                action='SELL',
                token_address=position.token_address,
                token_symbol=token_symbol,
                position_size_percent=Decimal('100'),  # Close entire position
                position_size_usd=position.current_value_usd,
                stop_loss_percent=None,
                take_profit_targets=[],
                execution_mode='IMMEDIATE',
                use_private_relay=False,
                gas_strategy='standard',
                max_gas_price_gwei=Decimal('100'),
                overall_confidence=Decimal('100'),
                risk_score=Decimal('0'),
                opportunity_score=Decimal('100'),
                primary_reasoning=f"Auto-close triggered: {reason}. Position P&L: {pnl_percent:+.2f}%.",
                risk_factors=[],
                opportunity_factors=[f"Auto-close: {reason}"],
                mitigation_strategies=[],
                intel_level_used=self.intelligence_engine.intel_level,
                intel_adjustments={},
                time_sensitivity='NORMAL',
                max_execution_time_ms=1000,
                decision_id='AUTO_CLOSE',
                timestamp=timezone.now(),
                processing_time_ms=0
            )

            # Log the auto-close decision
            self._log_thought(
                action='SELL',
                reasoning=(
                    f"Auto-close triggered: {reason}. "
                    f"Position P&L: {pnl_percent:+.2f}%. "
                    f"Closing entire position of {position.quantity:.4f} {token_symbol}."
                ),
                confidence=100,
                decision_type="RISK_MANAGEMENT",
                metadata={
                    'token': token_symbol,
                    'token_address': position.token_address,
                    'reason': reason,
                    'pnl_percent': float(pnl_percent),
                    'position_size': float(position.current_value_usd),
                    'auto_close': True
                }
            )

            # Execute the close
            success = trade_executor.execute_trade(
                decision=decision,
                token_symbol=token_symbol,
                current_price=current_price,
                position_manager=position_manager,
            )

            if success:
                logger.info(
                    f"[AUTO-CLOSE] Successfully closed {token_symbol} position: "
                    f"{reason} at {pnl_percent:+.2f}% P&L"
                )
            else:
                logger.error(
                    f"[AUTO-CLOSE] Failed to close {token_symbol} position"
                )

        except Exception as e:
            logger.error(
                f"[AUTO-CLOSE] Error executing auto-close: {e}",
                exc_info=True
            )

    # =========================================================================
    # TRANSACTION MANAGER INTEGRATION
    # =========================================================================

    def _check_pending_transactions(self, trade_executor: Any):
        """
        Check status of pending transactions (TX Manager integration).

        Args:
            trade_executor: TradeExecutor instance
        """
        try:
            if not TRANSACTION_MANAGER_AVAILABLE:
                return

            logger.debug(
                f"[TX CHECK] Checking {len(self.pending_transactions)} "
                "pending transaction(s)"
            )

            # Implementation depends on Transaction Manager API
            # This is a placeholder for TX Manager integration

        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Error checking pending transactions: {e}",
                exc_info=True
            )

    # =========================================================================
    # PERFORMANCE METRICS
    # =========================================================================

    def _update_performance_metrics(self, trade_executor: Any):
        """
        Update performance metrics for the current session.

        Args:
            trade_executor: TradeExecutor instance
        """
        try:
            logger.debug("[METRICS] Updating performance metrics...")

            # Get all trades for this session
            trades = PaperTrade.objects.filter(session=self.session)

            if not trades.exists():
                logger.debug("[METRICS] No trades yet for this session")
                return

            # Calculate metrics
            total_trades = trades.count()
            winning_trades = trades.filter(pnl_usd__gt=0).count()
            losing_trades = trades.filter(pnl_usd__lt=0).count()

            win_rate = (
                (winning_trades / total_trades * 100)
                if total_trades > 0
                else Decimal('0')
            )

            total_pnl = sum(
                trade.pnl_usd or Decimal('0')
                for trade in trades
            )

            # Update or create metrics
            metrics, created = PaperPerformanceMetrics.objects.get_or_create(
                session=self.session,
                defaults={
                    'total_trades': total_trades,
                    'winning_trades': winning_trades,
                    'losing_trades': losing_trades,
                    'win_rate': win_rate,
                    'total_pnl_usd': total_pnl,
                    'current_balance_usd': self.account.current_balance_usd
                }
            )

            if not created:
                metrics.total_trades = total_trades
                metrics.winning_trades = winning_trades
                metrics.losing_trades = losing_trades
                metrics.win_rate = win_rate
                metrics.total_pnl_usd = total_pnl
                metrics.current_balance_usd = self.account.current_balance_usd
                metrics.save()

            logger.debug(
                f"[METRICS] Updated: Trades={total_trades}, "
                f"Win Rate={win_rate:.1f}%, P&L=${total_pnl:.2f}"
            )

        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Failed to update performance metrics: {e}",
                exc_info=True
            )

    # =========================================================================
    # AI THOUGHT LOGGING
    # =========================================================================

    def _log_thought(
        self,
        action: str,
        reasoning: str,
        confidence: float,
        decision_type: str = "ANALYSIS",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log an AI thought/decision to the database.

        Args:
            action: Trading action (BUY, SELL, SKIP, etc.)
            reasoning: Detailed reasoning for the decision
            confidence: Confidence level (0-100)
            decision_type: Type of decision
            metadata: Additional metadata
        """
        try:
            from paper_trading.models import PaperAIThoughtLog

            thought = PaperAIThoughtLog.objects.create(
                account=self.account,
                decision_type=decision_type,
                token_address=metadata.get('token_address', '0x0000000000000000000000000000000000000000'),
                token_symbol=metadata.get('token', 'UNKNOWN'),
                confidence_level=self._calculate_confidence_level(confidence),  # Need to add this method
                confidence_percent=Decimal(str(confidence)),
                risk_score=Decimal(str(metadata.get('risk_score', 50))),
                opportunity_score=Decimal(str(metadata.get('opportunity_score', 50))),
                primary_reasoning=reasoning,
                key_factors=metadata.get('key_factors', []),
                positive_signals=metadata.get('positive_signals', []),
                negative_signals=metadata.get('negative_signals', []),
                market_data=metadata or {},
                strategy_name=metadata.get('strategy', ''),
                lane_used=metadata.get('lane', 'FAST')
            )

            # Send WebSocket update
            # WebSocket update sent automatically via Django signal
            # No need to send manually here
            pass

        except Exception as e:
            logger.error(
                f"[THOUGHT LOG] Failed to log thought: {e}",
                exc_info=True
            )

    # =========================================================================
    # BOT STATUS UPDATES
    # =========================================================================

    def _send_bot_status_update(
        self,
        status: str,
        price_manager: Any,
        position_manager: Any,
        trade_executor: Any
    ):
        """
        Send bot status update via WebSocket.

        Args:
            status: Bot status string
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
        """
        try:
            # Get current positions
            positions = position_manager.get_all_positions()
            
            # Format positions for WebSocket
            positions_data = []
            for token_symbol, position in positions.items():
                positions_data.append({
                    'token_symbol': token_symbol,
                    'quantity': float(position.quantity),
                    'invested_usd': float(position.total_invested_usd),
                    'current_value_usd': float(position.current_value_usd),
                    'pnl_percent': float(
                        ((position.current_value_usd - position.total_invested_usd) 
                         / position.total_invested_usd * 100)
                        if position.total_invested_usd > 0
                        else 0
                    )
                })

            # Prepare status data
            status_data = {
                'bot_status': str(status) if hasattr(status, 'value') else status,
                'intel_level': self.intelligence_engine.intel_level,
                'tx_manager_enabled': self.use_tx_manager,
                'circuit_breaker_enabled': self.circuit_breaker_manager is not None,
                'account_balance': float(self.account.current_balance_usd),
                'open_positions': positions_data,
                'tick_count': self.tick_count,
                'total_gas_savings': 0,  # Placeholder
                'pending_transactions': len(self.pending_transactions),
                'consecutive_failures': 0,  # Placeholder
                'daily_trades': 0,  # Placeholder
                'timestamp': timezone.now().isoformat()
            }

            # Send WebSocket update
            websocket_service.send_portfolio_update(
                account_id=str(self.account.account_id),
                portfolio_data=status_data  # ✅ Changed parameter name
            )

        except Exception as e:
            logger.error(
                f"[STATUS UPDATE] Failed to send bot status: {e}",
                exc_info=True
            )