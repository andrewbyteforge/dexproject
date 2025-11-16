"""
Metrics Logger for Paper Trading Bot

This module handles AI thought logging, performance metrics updates, and WebSocket
status broadcasts. It provides transparency by recording all AI decisions and
keeping users informed of bot status in real-time.

Responsibilities:
- Log AI thought processes and decision reasoning
- Update performance metrics (win rate, P&L, trade counts)
- Send WebSocket status updates to dashboard
- Sanitize data for JSON serialization
- Calculate confidence levels

This module was extracted from market_analyzer.py as part of v4.0+ refactoring
to keep individual files under 800 lines and improve maintainability.

File: dexproject/paper_trading/bot/metrics_logger.py
"""

import logging
import math
from decimal import Decimal
from typing import Dict, Any, Optional

from django.utils import timezone

from paper_trading.models import (
    PaperTradingAccount,
    PaperTradingSession,
    PaperPerformanceMetrics,
    PaperAIThoughtLog,
    PaperTrade,
    PaperPosition
)
from paper_trading.services.websocket_service import websocket_service

# Type hints for external dependencies (avoid circular imports)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from paper_trading.intelligence.core.intel_slider import IntelSliderEngine
    from paper_trading.bot.price_service_integration import RealPriceManager
    from paper_trading.bot.position_manager import PositionManager
    from paper_trading.bot.trade_executor import TradeExecutor

logger = logging.getLogger(__name__)


class MetricsLogger:
    """
    Handles metrics logging and bot status updates.

    This class provides transparency by logging all AI decisions with full
    reasoning, updating performance metrics, and broadcasting bot status
    via WebSocket to the dashboard.

    Example usage:
        metrics_logger = MetricsLogger(
            account=account,
            session=session,
            intelligence_engine=engine,
            use_tx_manager=False,
            circuit_breaker_manager=None
        )

        # Log an AI thought/decision
        metrics_logger.log_thought(
            action='BUY',
            reasoning='Strong uptrend detected with high confidence',
            confidence=85.5,
            decision_type='TRADE_DECISION',
            metadata={'token': 'WETH', 'intel_level': 7}
        )

        # Update performance metrics
        metrics_logger.update_performance_metrics()

        # Send status update via WebSocket
        metrics_logger.send_bot_status_update(
            status='running',
            price_manager=price_manager,
            position_manager=position_manager,
            trade_executor=trade_executor
        )
    """

    def __init__(
        self,
        account: PaperTradingAccount,
        session: PaperTradingSession,
        intelligence_engine: 'IntelSliderEngine',
        use_tx_manager: bool = False,
        circuit_breaker_manager: Optional[Any] = None,
        tick_count: int = 0,
        pending_transactions: Optional[list] = None,
        arbitrage_enabled: bool = False,
        arbitrage_opportunities_found: int = 0,
        arbitrage_trades_executed: int = 0
    ) -> None:
        """
        Initialize the Metrics Logger.

        Args:
            account: Paper trading account
            session: Current trading session
            intelligence_engine: Intelligence engine for intel level
            use_tx_manager: Whether TX Manager is enabled
            circuit_breaker_manager: Optional circuit breaker manager
            tick_count: Current tick count
            pending_transactions: List of pending transactions
            arbitrage_enabled: Whether arbitrage detection is enabled
            arbitrage_opportunities_found: Number of arbitrage opportunities found
            arbitrage_trades_executed: Number of arbitrage trades executed
        """
        self.account = account
        self.session = session
        self.intelligence_engine = intelligence_engine
        self.use_tx_manager = use_tx_manager
        self.circuit_breaker_manager = circuit_breaker_manager
        self.tick_count = tick_count
        self.pending_transactions = pending_transactions or []
        self.arbitrage_enabled = arbitrage_enabled
        self.arbitrage_opportunities_found = arbitrage_opportunities_found
        self.arbitrage_trades_executed = arbitrage_trades_executed

        logger.info("[METRICS LOGGER] Initialized metrics logger")

    # =========================================================================
    # AI THOUGHT LOGGING
    # =========================================================================

    def _sanitize_for_json(self, data: Any) -> Any:
        """
        Sanitize data for JSON serialization by converting NaN/Inf to None.

        Args:
            data: Data to sanitize (can be dict, list, or scalar)

        Returns:
            Sanitized data safe for JSON serialization
        """
        if isinstance(data, dict):
            return {k: self._sanitize_for_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._sanitize_for_json(item) for item in data]
        elif isinstance(data, float):
            if math.isnan(data) or math.isinf(data):
                return None
            return data
        elif isinstance(data, Decimal):
            if data.is_nan() or data.is_infinite():
                return None
            return float(data)
        else:
            return data

    def _calculate_confidence_level(self, confidence_percent: float) -> str:
        """
        Calculate confidence level category from percentage.

        Args:
            confidence_percent: Confidence as a percentage (0-100)

        Returns:
            Confidence level string (VERY_HIGH, HIGH, MEDIUM, LOW, VERY_LOW)
        """
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

    def log_thought(
        self,
        action: str,
        reasoning: str,
        confidence: float,
        decision_type: str = "TRADE_DECISION",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
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
            # Extract metadata
            metadata = metadata or {}
            token_symbol = metadata.get('token', 'UNKNOWN')
            token_address = metadata.get('token_address', '')

            # Calculate confidence level
            confidence_level = self._calculate_confidence_level(confidence)

            # Create thought log
            PaperAIThoughtLog.objects.create(
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
                market_data=self._sanitize_for_json(metadata),
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
    # PERFORMANCE METRICS
    # =========================================================================

    def update_performance_metrics(self) -> None:
        """
        Update performance metrics for the session.

        This method calculates current win rate, total P&L, and other
        performance indicators, then saves them to the database.
        Runs periodically (e.g., every 20 ticks) to avoid excessive DB writes.
        """
        try:
            logger.debug("[METRICS] Updating performance metrics...")

            # Get all trades for this session
            trades = PaperTrade.objects.filter(account=self.account)
            total_trades = trades.count()

            # Calculate realized P&L from closed positions
            closed_positions = PaperPosition.objects.filter(
                account=self.account,
                is_open=False
            )
            total_realized_pnl = sum(
                float(pos.realized_pnl_usd) for pos in closed_positions
            )

            # Calculate unrealized P&L from open positions
            open_positions = PaperPosition.objects.filter(
                account=self.account,
                is_open=True
            )
            total_unrealized_pnl = sum(
                float(pos.unrealized_pnl_usd) for pos in open_positions
            )

            # Calculate win rate
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
                f"[METRICS LOGGER] Failed to update metrics: {e}",
                exc_info=True
            )

    # =========================================================================
    # WEBSOCKET STATUS UPDATES
    # =========================================================================

    def send_bot_status_update(
        self,
        status: str,
        price_manager: 'RealPriceManager',
        position_manager: 'PositionManager',
        trade_executor: 'TradeExecutor'
    ) -> None:
        """
        Send bot status update via WebSocket.

        This broadcasts current bot state, portfolio value, open positions,
        and other metrics to the dashboard for real-time monitoring.

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
                'arbitrage_enabled': self.arbitrage_enabled,
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
    # STATE UPDATES (for external use)
    # =========================================================================

    def update_tick_count(self, tick_count: int) -> None:
        """Update tick count for status updates."""
        self.tick_count = tick_count

    def update_pending_transactions(self, pending_transactions: list) -> None:
        """Update pending transactions list for status updates."""
        self.pending_transactions = pending_transactions

    def update_arbitrage_stats(
        self,
        opportunities_found: int,
        trades_executed: int
    ) -> None:
        """Update arbitrage statistics for status updates."""
        self.arbitrage_opportunities_found = opportunities_found
        self.arbitrage_trades_executed = trades_executed