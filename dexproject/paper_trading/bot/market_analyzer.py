"""
Market Analyzer for Paper Trading Bot - REAL DATA INTEGRATION + INTELLIGENT SELLS + STRATEGY SELECTION

ENHANCED: Now evaluates existing positions for intelligent SELL decisions based on:
- Market conditions turning bearish
- Risk increasing beyond comfort levels
- Better opportunities elsewhere
- Technical signals deteriorating
- Position performance and hold time

PHASE 7B: Intelligent strategy selection - bot automatically selects optimal entry strategy:
- SPOT buy for standard conditions (fast execution)
- DCA for strong trends with high confidence
- GRID for volatile, range-bound markets

This module handles market analysis operations for the paper trading bot,
including tick coordination, token analysis, performance metrics, and
AI thought logging.

Responsibilities:
- Coordinate market ticks (main bot loop)
- Analyze individual tokens with REAL market data
- Evaluate existing positions for intelligent sells
- SELECT OPTIMAL TRADING STRATEGIES (Phase 7B - NEW!)
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
from datetime import timedelta

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
from paper_trading.intelligence.core.base import (
    MarketContext,
    TradingDecision
)
from paper_trading.intelligence.core.intel_slider import IntelSliderEngine

# Import Phase 7B strategy constants
from paper_trading.constants import (
    StrategyType,
    StrategySelectionThresholds,
    MarketTrend,
    DecisionType
)

# Import arbitrage detection components
try:
    from paper_trading.intelligence.dex.dex_price_comparator import DEXPriceComparator
    from paper_trading.intelligence.strategies.arbitrage_engine import ArbitrageDetector
    ARBITRAGE_AVAILABLE = True
except ImportError as e:
    ARBITRAGE_AVAILABLE = False
    # Will log warning after logger is initialized

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

    PHASE 7B: INTELLIGENT STRATEGY SELECTION: Bot automatically selects optimal
    entry strategy (SPOT/DCA/GRID) based on market conditions.

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

        # Trade cooldowns - prevent overtrading same token
        self.trade_cooldowns: Dict[str, Any] = {}  # token_symbol -> last_trade_time
        self.cooldown_minutes = 15  # Wait 15 minutes between trades on same token

        # Arbitrage detection components
        self.arbitrage_detector = None
        self.dex_comparator = None
        self.check_arbitrage = False
        self.arbitrage_opportunities_found = 0
        self.arbitrage_trades_executed = 0

        # Initialize arbitrage detection if available and enabled
        if ARBITRAGE_AVAILABLE:
            enable_arb = getattr(strategy_config, 'enable_arbitrage_detection', True) if strategy_config else True
            
            if enable_arb:
                try:
                    # Get chain_id from intelligence engine
                    chain_id = getattr(intelligence_engine, 'chain_id', 84532)
                    
                    # Initialize DEX price comparator
                    self.dex_comparator = DEXPriceComparator(
                        chain_id=chain_id
                    )
                    
                    # Initialize arbitrage detector with sensible defaults
                    self.arbitrage_detector = ArbitrageDetector(
                        gas_price_gwei=Decimal('1.0'),  # Will update dynamically
                        min_spread_percent=Decimal('0.5'),  # 0.5% minimum spread
                        min_profit_usd=Decimal('10')  # $10 minimum profit
                    )
                    
                    self.check_arbitrage = True
                    
                    logger.info(
                        "[MARKET ANALYZER] ✅ Arbitrage detection ENABLED "
                        f"(chain: {chain_id})"
                    )
                except Exception as e:
                    logger.warning(
                        f"[MARKET ANALYZER] Failed to initialize arbitrage: {e}",
                        exc_info=True
                    )
                    self.check_arbitrage = False
            else:
                logger.info("[MARKET ANALYZER] Arbitrage detection disabled by config")
        else:
            logger.warning("[MARKET ANALYZER] Arbitrage detection not available")

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
        - Executing trades (with strategy selection - Phase 7B)
        - Updating metrics

        Args:
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
        """
        try:
            self.tick_count += 1
            logger.info(f"[TICK {self.tick_count}] Starting market analysis tick...")

            # Update prices first
            self._update_market_prices(price_manager)

            # Check circuit breakers
            if self.circuit_breaker_manager:
                if not self.circuit_breaker_manager.can_trade():
                    logger.warning("[TICK] Circuit breaker is OPEN - skipping trading")
                    return

            # Check pending transactions if using TX Manager
            if self.use_tx_manager and TRANSACTION_MANAGER_AVAILABLE:
                self._check_pending_transactions()

            # INTELLIGENT SELLS: Check existing positions for smart exit opportunities
            # This runs BEFORE auto-close to make smarter decisions based on market conditions
            self._check_position_sells(
                price_manager=price_manager,
                position_manager=position_manager,
                trade_executor=trade_executor
            )

            # Check for auto-close triggers (stop-loss/take-profit)
            # This is the SAFETY NET - hard thresholds that override intelligent decisions
            self._check_auto_close_positions(
                price_manager=price_manager,
                position_manager=position_manager,
                trade_executor=trade_executor
            )

            # Get tokens to analyze
            tokens = price_manager.get_all_tokens()
            logger.info(f"[TICK] Analyzing {len(tokens)} tokens")

            # Analyze each token
            for token_data in tokens:
                self._analyze_token(
                    token_data=token_data,
                    price_manager=price_manager,
                    position_manager=position_manager,
                    trade_executor=trade_executor
                )

            # Update performance metrics
            self._update_metrics(position_manager)

            # Send status update via WebSocket
            self._send_bot_status_update(
                status='RUNNING',
                price_manager=price_manager,
                position_manager=position_manager,
                trade_executor=trade_executor
            )

            logger.info(f"[TICK {self.tick_count}] Market analysis tick completed")

        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Tick failed: {e}",
                exc_info=True
            )

    # =========================================================================
    # TRANSACTION MANAGER INTEGRATION
    # =========================================================================

    def _check_pending_transactions(self):
        """
        Check status of pending transactions via Transaction Manager.

        This method queries the Transaction Manager to check if any pending
        transactions have been confirmed or failed. Updates local state accordingly.
        """
        try:
            if not self.use_tx_manager or not TRANSACTION_MANAGER_AVAILABLE:
                return

            # Import here to avoid circular dependency
            from trading.services.transaction_manager import transaction_manager

            # Get status of all pending transactions
            for tx_hash in list(self.pending_transactions):
                try:
                    status = transaction_manager.get_transaction_status(tx_hash)

                    if status == 'confirmed':
                        logger.info(f"[TX MANAGER] Transaction {tx_hash} confirmed")
                        self.pending_transactions.remove(tx_hash)

                    elif status == 'failed':
                        logger.warning(f"[TX MANAGER] Transaction {tx_hash} failed")
                        self.pending_transactions.remove(tx_hash)

                    # 'pending' status - keep monitoring

                except Exception as e:
                    logger.error(
                        f"[TX MANAGER] Error checking transaction {tx_hash}: {e}"
                    )

        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Failed to check pending transactions: {e}",
                exc_info=True
            )

    # =========================================================================
    # UPDATE METRICS
    # =========================================================================

    def _update_metrics(self, position_manager: Any):
        """
        Update performance metrics for the current session.

        Args:
            position_manager: PositionManager instance
        """
        try:
            # Get current positions for unrealized P&L
            positions = position_manager.get_all_positions()
            total_unrealized_pnl = sum(
                pos.unrealized_pnl_usd for pos in positions.values()
            )

            # Get completed trades for realized P&L
            completed_trades = PaperTrade.objects.filter(
                account=self.account,
                session=self.session,
                status='EXECUTED'
            )

            total_realized_pnl = sum(
                trade.profit_loss_usd or Decimal('0')
                for trade in completed_trades
            )

            # Calculate win rate
            profitable_trades = completed_trades.filter(
                profit_loss_usd__gt=0
            ).count()
            total_trades = completed_trades.count()
            win_rate = (
                (profitable_trades / total_trades * 100)
                if total_trades > 0
                else Decimal('0')
            )

            # Update or create metrics
            metrics, created = PaperPerformanceMetrics.objects.get_or_create(
                account=self.account,
                session=self.session,
                defaults={
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'win_rate': Decimal('0'),
                    'total_profit_loss': Decimal('0'),
                    'unrealized_pnl': Decimal('0'),
                    'realized_pnl': Decimal('0')
                }
            )

            # Update metrics
            metrics.total_trades = total_trades
            metrics.winning_trades = profitable_trades
            metrics.losing_trades = total_trades - profitable_trades
            metrics.win_rate = win_rate
            metrics.realized_pnl = total_realized_pnl
            metrics.unrealized_pnl = total_unrealized_pnl
            metrics.total_profit_loss = total_realized_pnl + total_unrealized_pnl
            metrics.save()

            logger.debug(
                f"[METRICS] Updated: {total_trades} trades, "
                f"{win_rate:.1f}% win rate, "
                f"${total_realized_pnl + total_unrealized_pnl:.2f} total P&L"
            )

        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Failed to update metrics: {e}",
                exc_info=True
            )

    # =========================================================================
    # INTELLIGENT POSITION SELL CHECK - NEW!
    # =========================================================================

    def _check_position_sells(
        self,
        price_manager: Any,
        position_manager: Any,
        trade_executor: Any
    ):
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
    ):
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
            avg_entry_price = position.average_entry_price
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
                    trade_size_usd=float(current_value),
                    chain_id=self.intelligence_engine.chain_id,
                    price_history=[Decimal(str(p)) for p in price_history],
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
                current_price=current_price,
                price_24h_ago=price_history[0] if price_history else current_price,
                liquidity=liquidity,
                volatility=volatility,
                gas_price=Decimal('1.0'),
                trend=trend_direction,
                data_quality=data_quality
            )

            # Add position-specific context
            market_context.position_pnl_percent = pnl_percent
            market_context.position_hold_hours = Decimal(str(hold_time_hours))
            market_context.position_entry_price = avg_entry_price

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
                        amount_in=float(position.quantity)
                    )

                    if dex_prices and len(dex_prices) >= 2:
                        # Check arbitrage opportunity
                        arb_opp = self.arbitrage_detector.analyze_opportunity(
                            dex_prices=dex_prices,
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
            decision = async_to_sync(self.intelligence_engine.evaluate_position_exit)(
                market_context=market_context,
                position_data={
                    'token_symbol': token_symbol,
                    'token_address': token_address,
                    'quantity': float(position.quantity),
                    'entry_price': float(avg_entry_price),
                    'current_price': float(current_price),
                    'invested_usd': float(invested),
                    'current_value_usd': float(current_value),
                    'pnl_percent': float(pnl_percent),
                    'hold_time_hours': hold_time_hours
                },
                account_balance=self.account.current_balance_usd,
                existing_positions=existing_positions
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
                # Check trade cooldown
                if self._is_on_cooldown(token_symbol):
                    cooldown_remaining = self._get_cooldown_remaining(token_symbol)
                    logger.info(
                        f"[COOLDOWN] Skipping {token_symbol} sell - "
                        f"cooldown active ({cooldown_remaining:.1f} min remaining)"
                    )
                    return
                
                logger.info(
                    f"[SELL CHECK] 🎯 SELL signal for {token_symbol}: "
                    f"P&L={pnl_percent:+.2f}%, Hold={hold_time_hours:.1f}h, "
                    f"Type={decision_type}"
                )
                
                # Log the sell decision
                self._log_thought(
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
                    # Set cooldown for this token
                    self._set_trade_cooldown(token_symbol)
                    
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

    # =========================================================================
    # TOKEN ANALYSIS WITH REAL DATA INTEGRATION + STRATEGY SELECTION
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

        PHASE 7B: Implements intelligent strategy selection - bot chooses between
        SPOT, DCA, and GRID strategies based on market conditions.

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
                gas_analysis = real_analysis.get('gas', {})
                trend_analysis = real_analysis.get('trend', {})

                liquidity_usd = Decimal(str(liquidity_analysis.get('total_liquidity_usd', 0)))
                volatility = Decimal(str(volatility_analysis.get('volatility_24h', 0)))
                gas_price = Decimal(str(gas_analysis.get('current_gwei', 1.0)))
                trend_direction = trend_analysis.get('direction', 'unknown')
                data_quality = real_analysis.get('data_quality', 'GOOD')

                logger.info(
                    f"[REAL DATA] {token_symbol} metrics: "
                    f"Liquidity=${liquidity_usd:,.0f}, "
                    f"Volatility={volatility:.2%}, "
                    f"Gas={gas_price} gwei, "
                    f"Trend={trend_direction}, "
                    f"Quality={data_quality}"
                )
            else:
                # FALLBACK: Use conservative estimates if real analysis unavailable
                liquidity_usd = Decimal('0')
                volatility = Decimal('0')
                gas_price = Decimal('1.0')
                trend_direction = 'unknown'
                data_quality = 'INSUFFICIENT'

                logger.warning(
                    f"[REAL DATA] Using fallback data for {token_symbol} "
                    f"(real analysis unavailable)"
                )

            # Create market context with REAL or fallback data
            market_context = MarketContext(
                current_price=current_price,
                price_24h_ago=price_24h_ago,
                liquidity=liquidity_usd,
                volatility=volatility,
                gas_price=gas_price,
                trend=trend_direction,
                data_quality=data_quality
            )

            # Get existing positions for better decision making
            all_positions = position_manager.get_all_positions()
            existing_positions = {
                sym: {
                    'quantity': float(pos.quantity),
                    'invested_usd': float(pos.total_invested_usd),
                    'current_value_usd': float(pos.current_value_usd)
                }
                for sym, pos in all_positions.items()
            }

            # Check if we already have a position in this token
            has_position = token_symbol in all_positions

            # Make trading decision based on whether we have a position
            if has_position:
                # Already have position - decision engine will recommend HOLD or SELL
                decision = async_to_sync(self.intelligence_engine.evaluate_position_exit)(
                    market_context=market_context,
                    position_data={
                        'token_symbol': token_symbol,
                        'token_address': token_address,
                        'quantity': float(all_positions[token_symbol].quantity),
                        'entry_price': float(all_positions[token_symbol].average_entry_price),
                        'current_price': float(current_price),
                        'invested_usd': float(all_positions[token_symbol].total_invested_usd),
                        'current_value_usd': float(all_positions[token_symbol].current_value_usd)
                    },
                    account_balance=self.account.current_balance_usd,
                    existing_positions=existing_positions
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
            
            # ===================================================================
            # PHASE 7B: INTELLIGENT STRATEGY SELECTION
            # ===================================================================
            if decision.action == 'BUY':
                # Check trade cooldown before executing
                if self._is_on_cooldown(token_symbol):
                    cooldown_remaining = self._get_cooldown_remaining(token_symbol)
                    logger.info(
                        f"[COOLDOWN] Skipping BUY on {token_symbol} - "
                        f"cooldown active ({cooldown_remaining:.1f} min remaining)"
                    )
                else:
                    # NEW: Select optimal strategy based on market conditions
                    selected_strategy = self._select_strategy(
                        token_address=token_address,
                        token_symbol=token_symbol,
                        decision=decision,
                        market_context=market_context
                    )
                    
                    logger.info(
                        f"[STRATEGY] Selected {selected_strategy} strategy for {token_symbol}"
                    )
                    
                    # Execute based on selected strategy
                    success = False
                    
                    if selected_strategy == StrategyType.DCA:
                        # Start DCA strategy
                        success = self._start_dca_strategy(
                            token_address=token_address,
                            token_symbol=token_symbol,
                            decision=decision
                        )
                    
                    elif selected_strategy == StrategyType.GRID:
                        # Start Grid strategy
                        success = self._start_grid_strategy(
                            token_address=token_address,
                            token_symbol=token_symbol,
                            decision=decision,
                            market_context=market_context
                        )
                    
                    else:  # SPOT buy (default/fallback)
                        # Execute standard spot buy
                        success = trade_executor.execute_trade(
                            decision=decision,
                            token_symbol=token_symbol,
                            current_price=current_price,
                            position_manager=position_manager
                        )
                    
                    # Set cooldown if trade/strategy was successful
                    if success:
                        self._set_trade_cooldown(token_symbol)
            
            elif decision.action == 'SELL':
                # SELL logic remains unchanged (spot execution)
                if self._is_on_cooldown(token_symbol):
                    cooldown_remaining = self._get_cooldown_remaining(token_symbol)
                    logger.info(
                        f"[COOLDOWN] Skipping SELL on {token_symbol} - "
                        f"cooldown active ({cooldown_remaining:.1f} min remaining)"
                    )
                else:
                    success = trade_executor.execute_trade(
                        decision=decision,
                        token_symbol=token_symbol,
                        current_price=current_price,
                        position_manager=position_manager
                    )
                    
                    if success:
                        self._set_trade_cooldown(token_symbol)

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
        we have the latest market information. Also updates gas prices for
        arbitrage calculations.

        Args:
            price_manager: RealPriceManager instance
        """
        try:
            logger.debug("[PRICES] Updating market prices...")
            price_manager.update_prices()
            logger.debug("[PRICES] Market prices updated successfully")
            
            # Update gas price for arbitrage calculations
            if self.arbitrage_detector:
                try:
                    # Try to get gas price from price manager
                    if hasattr(price_manager, 'get_gas_price'):
                        gas_price_gwei = price_manager.get_gas_price()
                        if gas_price_gwei:
                            self.update_gas_price(Decimal(str(gas_price_gwei)))
                    else:
                        # Use conservative default if not available
                        # On Base, gas is typically very low (< 1 gwei)
                        self.update_gas_price(Decimal('0.5'))
                except Exception as gas_error:
                    logger.debug(f"[PRICES] Could not update gas price: {gas_error}")
                    
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
                entry_price = position.average_entry_price
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
                    
                    # Log the auto-close decision
                    self._log_thought(
                        action='SELL',
                        reasoning=f"Stop-loss triggered at {pnl_percent:.2f}% loss",
                        confidence=100.0,  # Hard threshold = 100% confidence
                        decision_type="STOP_LOSS",
                        metadata={
                            'token': token_symbol,
                            'current_price': float(current_price),
                            'entry_price': float(entry_price),
                            'pnl_percent': float(pnl_percent),
                            'stop_loss_threshold': float(stop_loss)
                        }
                    )
                    
                    # Create a simple SELL decision for executor
                    from paper_trading.intelligence.core.base import TradingDecision
                    sell_decision = TradingDecision(
                        action='SELL',
                        primary_reasoning=f"Stop-loss triggered at {pnl_percent:.2f}% loss",
                        overall_confidence=Decimal('100'),
                        risk_score=Decimal('0'),
                        opportunity_score=Decimal('0'),
                        position_size_usd=Decimal('0')
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
                    
                    # Log the auto-close decision
                    self._log_thought(
                        action='SELL',
                        reasoning=f"Take-profit triggered at {pnl_percent:.2f}% gain",
                        confidence=100.0,  # Hard threshold = 100% confidence
                        decision_type="TAKE_PROFIT",
                        metadata={
                            'token': token_symbol,
                            'current_price': float(current_price),
                            'entry_price': float(entry_price),
                            'pnl_percent': float(pnl_percent),
                            'take_profit_threshold': float(take_profit)
                        }
                    )
                    
                    # Create a simple SELL decision for executor
                    from paper_trading.intelligence.core.base import TradingDecision
                    sell_decision = TradingDecision(
                        action='SELL',
                        primary_reasoning=f"Take-profit triggered at {pnl_percent:.2f}% gain",
                        overall_confidence=Decimal('100'),
                        risk_score=Decimal('0'),
                        opportunity_score=Decimal('0'),
                        position_size_usd=Decimal('0')
                    )
                    
                    trade_executor.execute_trade(
                        decision=sell_decision,
                        token_symbol=token_symbol,
                        current_price=current_price,
                        position_manager=position_manager
                    )

        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Failed to check auto-close positions: {e}",
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
        decision_type: str = "TRADE_DECISION",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log an AI thought/decision to the database.

        This creates a transparent record of why the bot made a particular
        decision, enabling users to understand and trust the AI's reasoning.

        Args:
            action: Decision action (BUY, SELL, HOLD, SKIP)
            reasoning: Primary reasoning for the decision
            confidence: Confidence level (0-100)
            decision_type: Type of decision being logged
            metadata: Additional metadata about the decision
        """
        try:
            from paper_trading.models import PaperAIThoughtLog

            # Extract metadata
            metadata = metadata or {}
            token_symbol = metadata.get('token', 'UNKNOWN')
            token_address = metadata.get('token_address', '')

            # Calculate confidence level
            confidence_level = self._calculate_confidence_level(confidence)

            # Create thought log
            thought = PaperAIThoughtLog.objects.create(
                account=self.account,
                decision_type=action,
                token_address=token_address,
                token_symbol=token_symbol,
                confidence_level=confidence_level,
                confidence_percent=Decimal(str(confidence)),
                risk_score=Decimal(str(metadata.get('risk_score', 0))),
                opportunity_score=Decimal(str(metadata.get('opportunity_score', 0))),
                primary_reasoning=reasoning,
                key_factors=[decision_type],
                positive_signals=metadata.get('positive_signals', []),
                negative_signals=metadata.get('negative_signals', []),
                market_data=metadata,
                strategy_name=f"Intel Level {metadata.get('intel_level', 'Unknown')}",
                lane_used='SMART' if metadata.get('data_quality') == 'GOOD' else 'FAST',
                analysis_time_ms=0
            )

            logger.debug(
                f"[THOUGHT LOG] Logged {action} decision for {token_symbol}: "
                f"{confidence:.1f}% confidence"
            )

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
                'timestamp': timezone.now().isoformat(),
                # Arbitrage stats
                'arbitrage_enabled': self.check_arbitrage,
                'arbitrage_opportunities_found': self.arbitrage_opportunities_found,
                'arbitrage_trades_executed': self.arbitrage_trades_executed
            }

            # Send WebSocket update
            websocket_service.send_portfolio_update(
                account_id=str(self.account.account_id),
                portfolio_data=status_data
            )

        except Exception as e:
            logger.error(
                f"[STATUS UPDATE] Failed to send bot status: {e}",
                exc_info=True
            )

    # =========================================================================
    # TRADE COOLDOWN MANAGEMENT
    # =========================================================================

    def _is_on_cooldown(self, token_symbol: str) -> bool:
        """
        Check if token is on trade cooldown.
        
        Args:
            token_symbol: Token symbol to check
            
        Returns:
            True if on cooldown, False otherwise
        """
        if token_symbol not in self.trade_cooldowns:
            return False
        
        last_trade_time = self.trade_cooldowns[token_symbol]
        cooldown_until = last_trade_time + timedelta(minutes=self.cooldown_minutes)
        
        return timezone.now() < cooldown_until

    def _get_cooldown_remaining(self, token_symbol: str) -> float:
        """
        Get remaining cooldown time in minutes.
        
        Args:
            token_symbol: Token symbol
            
        Returns:
            Remaining cooldown time in minutes
        """
        if token_symbol not in self.trade_cooldowns:
            return 0.0
        
        last_trade_time = self.trade_cooldowns[token_symbol]
        cooldown_until = last_trade_time + timedelta(minutes=self.cooldown_minutes)
        remaining = cooldown_until - timezone.now()
        
        return max(0.0, remaining.total_seconds() / 60)

    def _set_trade_cooldown(self, token_symbol: str) -> None:
        """
        Set trade cooldown for token.
        
        Args:
            token_symbol: Token symbol
        """
        self.trade_cooldowns[token_symbol] = timezone.now()
        logger.debug(
            f"[COOLDOWN] Set {self.cooldown_minutes}min cooldown for {token_symbol}"
        )

    # =========================================================================
    # ARBITRAGE MANAGEMENT
    # =========================================================================

    def update_gas_price(self, gas_price_gwei: Decimal) -> None:
        """
        Update gas price for arbitrage calculations.
        
        This should be called periodically to keep arbitrage profit
        calculations accurate with current network conditions.
        
        Args:
            gas_price_gwei: Current gas price in gwei
        """
        if self.arbitrage_detector:
            self.arbitrage_detector.update_gas_price(gas_price_gwei)
            logger.debug(f"[ARBITRAGE] Updated gas price to {gas_price_gwei} gwei")

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
        
        if self.arbitrage_detector:
            stats['detector_stats'] = self.arbitrage_detector.get_performance_stats()
        
        if self.dex_comparator:
            stats['comparator_stats'] = self.dex_comparator.get_performance_stats()
        
        return stats

    # =========================================================================
    # STRATEGY SELECTION - Phase 7B
    # =========================================================================

    def _select_strategy(
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
        - Standard conditions → SPOT Buy (fast execution)
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            decision: Trading decision from intelligence engine
            market_context: Market context with volatility, trend, liquidity
            
        Returns:
            StrategyType constant (SPOT, DCA, or GRID)
        """
        try:
            # Get strategy preferences from config
            enable_dca = getattr(self.strategy_config, 'enable_dca', False) if self.strategy_config else False
            enable_grid = getattr(self.strategy_config, 'enable_grid', False) if self.strategy_config else False
            
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
            # DECISION 1: Check if GRID strategy is appropriate
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
            # DECISION 2: Check if DCA strategy is appropriate
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
            # DECISION 3: Default to SPOT buy (fast execution)
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
            
            # Log AI thought
            self._log_thought(
                action='BUY',
                reasoning=(
                    f"Bot selected DCA strategy: Spreading ${float(total_amount):.2f} "
                    f"across {num_intervals} intervals to average entry price in "
                    f"{decision.market_context.trend} market"
                ),
                confidence=float(decision.overall_confidence),
                decision_type=DecisionType.DCA_STRATEGY,
                metadata={
                    'token': token_symbol,
                    'token_address': token_address,
                    'strategy_id': str(strategy_run.strategy_id),
                    'total_amount': float(total_amount),
                    'num_intervals': num_intervals,
                    'interval_hours': interval_hours,
                    'trend': decision.market_context.trend
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
            
            # Log AI thought
            self._log_thought(
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

    # =========================================================================
    # CLEANUP
    # =========================================================================

    async def cleanup(self) -> None:
        """
        Clean up resources (DEX connections, etc.).
        
        Call this when shutting down the bot to properly close
        all DEX connections and clean up resources.
        """
        try:
            logger.info("[MARKET ANALYZER] Starting cleanup...")
            
            # Clean up DEX comparator
            if self.dex_comparator:
                await self.dex_comparator.cleanup()
                logger.info("[MARKET ANALYZER] DEX comparator cleaned up")
            
            # Log final arbitrage stats
            if self.check_arbitrage:
                arb_stats = self.get_arbitrage_stats()
                logger.info(
                    f"[ARBITRAGE] Final stats: "
                    f"{arb_stats['opportunities_found']} opportunities found, "
                    f"{arb_stats['trades_executed']} trades executed"
                )
            
            logger.info("[MARKET ANALYZER] Cleanup complete")
            
        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Cleanup error: {e}",
                exc_info=True
            )