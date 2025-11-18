"""
Market Analyzer for Paper Trading Bot - Core Orchestration Module

This module handles the main coordination and orchestration for the paper trading bot.
It manages the bot lifecycle, market tick coordination, and system-level operations.

RESPONSIBILITIES:
- Initialize and coordinate all trading components
- Execute main market tick cycle
- Update market prices
- Update performance metrics
- Manage pending transactions (TX Manager integration)
- Send bot status updates via WebSocket
- Clean up resources on shutdown

DELEGATED RESPONSIBILITIES (see other modules):
- Token analysis → token_analyzer.py
- Position sell evaluation → position_evaluator.py
- Strategy selection → strategy_selector.py
- Strategy execution → strategy_launcher.py
- Helper utilities → market_helpers.py

File: dexproject/paper_trading/bot/market_analyzer.py
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Any

from django.utils import timezone

from paper_trading.models import (
    PaperTradingAccount,
    PaperTradingSession,
    PaperStrategyConfiguration,
    PaperPerformanceMetrics,
    PaperTrade,
    PaperPosition
)

# Import intelligence types
from paper_trading.intelligence.core.base import TradingDecision
from paper_trading.intelligence.core.intel_slider import IntelSliderEngine

# Import arbitrage detection components
try:
    from paper_trading.intelligence.dex.dex_price_comparator import DEXPriceComparator
    from paper_trading.intelligence.strategies.arbitrage_engine import ArbitrageDetector
    ARBITRAGE_AVAILABLE = True
except ImportError:
    ARBITRAGE_AVAILABLE = False

# Import WebSocket service
from paper_trading.services.websocket_service import websocket_service

# Import Transaction Manager status (optional)
try:
    import trading.services.transaction_manager  # noqa: F401
    TRANSACTION_MANAGER_AVAILABLE = True
except ImportError:
    TRANSACTION_MANAGER_AVAILABLE = False

# Import delegated components
from paper_trading.bot.token_analyzer import TokenAnalyzer
from paper_trading.bot.position_evaluator import PositionEvaluator
from paper_trading.bot.market_helpers import MarketHelpers

logger = logging.getLogger(__name__)


# =============================================================================
# MARKET ANALYZER CLASS - Core Orchestration
# =============================================================================

class MarketAnalyzer:
    """
    Handles market analysis and tick coordination for paper trading bot.

    This class manages the main bot loop and coordinates all market-related
    operations including price updates, token analysis, and decision making.

    ARCHITECTURE:
    - Core orchestration and coordination (this file)
    - Token analysis delegated to TokenAnalyzer
    - Position evaluation delegated to PositionEvaluator
    - Helper utilities delegated to MarketHelpers

    NOW WITH REAL DATA INTEGRATION: Calls CompositeMarketAnalyzer to get
    actual blockchain data for gas, liquidity, volatility, and MEV analysis.

    ENHANCED WITH INTELLIGENT SELLS: Evaluates existing positions for smart
    exit decisions based on changing market conditions, not just fixed thresholds.

    PHASE 7B: INTELLIGENT STRATEGY SELECTION: Bot automatically selects optimal
    entry strategy (SPOT/DCA/GRID/TWAP) based on market conditions.

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
    ) -> None:
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
        
        # Initialize arbitrage detection components
        self.arbitrage_detector: Optional[ArbitrageDetector] = None
        self.dex_comparator: Optional[DEXPriceComparator] = None
        self.check_arbitrage = False
        self.arbitrage_opportunities_found = 0
        self.arbitrage_trades_executed = 0
        
        # Initialize arbitrage detection if available and enabled
        if ARBITRAGE_AVAILABLE:
            enable_arb = getattr(
                strategy_config, 
                'enable_arbitrage_detection', 
                True
            ) if strategy_config else True
            
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
                logger.info(
                    "[MARKET ANALYZER] Arbitrage detection disabled by config"
                )
        else:
            logger.warning(
                "[MARKET ANALYZER] Arbitrage detection not available"
            )
        
        # Initialize delegated components
        self.token_analyzer = TokenAnalyzer(
            account=account,
            intelligence_engine=intelligence_engine,
            strategy_config=strategy_config,
            arbitrage_detector=self.arbitrage_detector,
            dex_comparator=self.dex_comparator,
            check_arbitrage=self.check_arbitrage
        )
        
        self.position_evaluator = PositionEvaluator(
            account=account,
            intelligence_engine=intelligence_engine,
            arbitrage_detector=self.arbitrage_detector,
            dex_comparator=self.dex_comparator,
            check_arbitrage=self.check_arbitrage
        )
        
        self.helpers = MarketHelpers(
            account=account,
            intelligence_engine=intelligence_engine,
            strategy_config=strategy_config
        )
        
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
    ) -> None:
        """
        Execute one market tick cycle.

        This method coordinates all trading operations including:
        - Updating prices
        - Checking circuit breakers
        - Evaluating positions for intelligent sells
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
            self.position_evaluator.check_position_sells(
                price_manager=price_manager,
                position_manager=position_manager,
                trade_executor=trade_executor
            )

            # Check for auto-close triggers (stop-loss/take-profit)
            # This is the SAFETY NET - hard thresholds that override intelligent decisions
            self.helpers.check_auto_close_positions(
                price_manager=price_manager,
                position_manager=position_manager,
                trade_executor=trade_executor
            )

            # Get tokens to analyze
            tokens = price_manager.get_all_tokens()
            logger.info(f"[TICK] Analyzing {len(tokens)} tokens")

            # Analyze each token
            for token_data in tokens:
                self.token_analyzer.analyze_token(
                    token_data=token_data,
                    price_manager=price_manager,
                    position_manager=position_manager,
                    trade_executor=trade_executor
                )

            # Update arbitrage stats from delegated components
            self.arbitrage_opportunities_found = self.token_analyzer.arbitrage_opportunities_found
            self.arbitrage_trades_executed = self.token_analyzer.arbitrage_trades_executed

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

    def _check_pending_transactions(self) -> None:
        """
        Check status of pending transactions via Transaction Manager.

        This method queries the Transaction Manager to check if any pending
        transactions have been confirmed or failed. Updates local state accordingly.
        """
        try:
            if not self.use_tx_manager or not TRANSACTION_MANAGER_AVAILABLE:
                return

            # Import here to avoid circular dependency
            try:
                from trading.services import transaction_manager
            except ImportError:
                logger.debug("[TX MANAGER] Transaction manager module not available")
                return

            # Get status of all pending transactions
            for tx_hash in list(self.pending_transactions):
                try:
                    # Type ignore: transaction_manager is optional and dynamically imported
                    status = transaction_manager.get_transaction_status(tx_hash)  # type: ignore[attr-defined]

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
    # PRICE & METRICS UPDATES
    # =========================================================================

    def _update_market_prices(self, price_manager: Any) -> None:
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
                            self.helpers.update_gas_price(
                                Decimal(str(gas_price_gwei)),
                                self.arbitrage_detector
                            )
                    else:
                        # Use conservative default if not available
                        # On Base, gas is typically very low (< 1 gwei)
                        self.helpers.update_gas_price(
                            Decimal('0.5'),
                            self.arbitrage_detector
                        )
                except Exception as gas_error:
                    logger.debug(f"[PRICES] Could not update gas price: {gas_error}")

        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Failed to update market prices: {e}",
                exc_info=True
            )

    def _update_metrics(self, position_manager: Any) -> None:
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

            # Get all trades for this account
            all_trades = PaperTrade.objects.filter(
                account=self.account,
                status='EXECUTED'
            )

            total_trades = all_trades.count()

            # Calculate realized P&L from CLOSED positions only
            closed_positions = PaperPosition.objects.filter(
                account=self.account,
                is_open=False
            )

            total_realized_pnl = sum(
                pos.realized_pnl_usd or Decimal('0')
                for pos in closed_positions
            )

            # Calculate win rate from closed positions
            profitable_positions = closed_positions.filter(
                realized_pnl_usd__gt=0
            ).count()
            total_closed = closed_positions.count()

            win_rate = Decimal('0')
            if total_closed > 0:
                win_rate = Decimal(str((profitable_positions / total_closed) * 100))

            # Update or create metrics - use SESSION, not account!
            metrics, created = PaperPerformanceMetrics.objects.get_or_create(
                session=self.session,
                defaults={
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'win_rate': Decimal('0'),
                    'total_pnl_usd': Decimal('0'),
                    'period_start': self.session.started_at if self.session else timezone.now(),
                    'period_end': timezone.now()
                }
            )

            # Update metrics with correct field names
            metrics.total_trades = total_trades
            metrics.winning_trades = profitable_positions
            metrics.losing_trades = total_closed - profitable_positions
            metrics.win_rate = win_rate
            metrics.total_pnl_usd = Decimal(str(total_realized_pnl + total_unrealized_pnl))
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
    # BOT STATUS UPDATES
    # =========================================================================

    def _send_bot_status_update(
        self,
        status: str,
        price_manager: Any,
        position_manager: Any,
        trade_executor: Any
    ) -> None:
        """
        Send bot status update via WebSocket.
        
        Args:
            status: Bot status string
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
        """
        try:
            logger.debug(f"[STATUS UPDATE] Starting portfolio update for account {self.account.account_id}")
            
            # Get current positions
            positions = position_manager.get_all_positions()
            logger.debug(f"[STATUS UPDATE] Retrieved {len(positions)} open positions")
            
            # Format positions for WebSocket
            positions_data = []
            total_positions_value = 0.0
            
            for token_symbol, position in positions.items():
                position_value = float(position.current_value_usd)
                total_positions_value += position_value
                
                positions_data.append({
                    'token_symbol': token_symbol,
                    'quantity': float(position.quantity),
                    'invested_usd': float(position.total_invested_usd),
                    'current_value_usd': position_value,
                    'pnl_percent': float(
                        ((position.current_value_usd - position.total_invested_usd)
                         / position.total_invested_usd * 100)
                        if position.total_invested_usd > 0
                        else 0
                    )
                })
            
            account_cash = float(self.account.current_balance_usd)
            total_portfolio_value = account_cash + total_positions_value
            
            logger.debug(
                f"[STATUS UPDATE] Portfolio breakdown: "
                f"Cash=${account_cash:.2f}, "
                f"Positions=${total_positions_value:.2f}, "
                f"Total=${total_portfolio_value:.2f}"
            )
            
            # Prepare status data
            status_data = {
                'bot_status': str(status) if hasattr(status, 'value') else status,
                'intel_level': self.intelligence_engine.intel_level,
                'tx_manager_enabled': self.use_tx_manager,
                'circuit_breaker_enabled': self.circuit_breaker_manager is not None,
                'account_balance': account_cash,
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
            
            logger.debug(f"[STATUS UPDATE] Sending portfolio.update message via WebSocket")
            
            # Send WebSocket update
            success = websocket_service.send_portfolio_update(
                account_id=str(self.account.account_id),
                portfolio_data=status_data
            )
            
            if success:
                logger.info(
                    f"[STATUS UPDATE] ✅ Portfolio update sent successfully - "
                    f"Total=${total_portfolio_value:.2f} "
                    f"(Cash=${account_cash:.2f} + Positions=${total_positions_value:.2f})"
                )
            else:
                logger.warning(
                    f"[STATUS UPDATE] ⚠️ WebSocket service returned False - "
                    f"update may not have been sent"
                )
            
        except Exception as e:
            logger.error(
                f"[STATUS UPDATE] ❌ Failed to send bot status: {e}",
                exc_info=True
            )

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
                arb_stats = self.helpers.get_arbitrage_stats(
                    self.check_arbitrage,
                    self.arbitrage_opportunities_found,
                    self.arbitrage_trades_executed,
                    self.arbitrage_detector,
                    self.dex_comparator
                )
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