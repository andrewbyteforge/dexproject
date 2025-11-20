"""
Market Helpers for Paper Trading Bot - Utility Functions

This module provides utility functions for the market analyzer. It handles:
- AI thought logging
- Pending transaction monitoring
- Arbitrage statistics
- Bot status formatting
- Helper utilities

CRITICAL: This module does NOT make trading decisions. It only provides
supporting functionality for the market analyzer.

File: dexproject/paper_trading/bot/market_helpers.py
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Any

from django.utils import timezone

from paper_trading.models import (
    PaperTradingAccount,
    PaperTradingSession,
    PaperAIThoughtLog
)

logger = logging.getLogger(__name__)


class MarketHelpers:
    """
    Utility functions for market analysis operations.

    This class provides helper functions that don't make trading decisions
    but support the market analyzer's operations:
    - Logging AI thoughts
    - Checking pending transactions
    - Calculating statistics
    - Formatting status updates

    Example usage:
        helpers = MarketHelpers(
            account=account,
            session=session
        )

        # Log an AI thought
        helpers.log_thought(
            action='BUY',
            reasoning='Strong bullish signals',
            confidence=85.0,
            decision_type='TRADE_DECISION',
            metadata={'token': 'WETH'}
        )
    """

    def __init__(
        self,
        account: PaperTradingAccount,
        session: PaperTradingSession,
        use_tx_manager: bool = False
    ) -> None:
        """
        Initialize the Market Helpers.

        Args:
            account: Paper trading account
            session: Current trading session
            use_tx_manager: Whether Transaction Manager is enabled
        """
        self.account = account
        self.session = session
        self.use_tx_manager = use_tx_manager

        logger.info("[MARKET HELPERS] Initialized market helpers")

    # =========================================================================
    # AI THOUGHT LOGGING
    # =========================================================================

    def log_thought(
        self,
        action: str,
        reasoning: str,
        confidence: float,
        decision_type: str = "TRADE_DECISION",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[PaperAIThoughtLog]:
        """
        Log an AI thought/decision to the database for transparency.

        This creates a PaperAIThoughtLog record that can be viewed in the
        AI Thought Logs dashboard to understand why the bot made decisions.

        Args:
            action: Decision action (BUY, SELL, HOLD, SKIP)
            reasoning: Primary reasoning for the decision
            confidence: Confidence level (0-100)
            decision_type: Type of decision being logged
            metadata: Additional metadata dict

        Returns:
            PaperAIThoughtLog object if successful, None otherwise
        """
        try:
            if not metadata:
                metadata = {}

            # Extract common fields from metadata
            token_symbol = metadata.get('token', 'UNKNOWN')
            token_address = metadata.get('token_address', '')
            risk_score = metadata.get('risk_score', 0.0)
            opportunity_score = metadata.get('opportunity_score', 0.0)

            # Determine confidence level category
            if confidence >= 80:
                confidence_level = 'VERY_HIGH'
            elif confidence >= 65:
                confidence_level = 'HIGH'
            elif confidence >= 50:
                confidence_level = 'MEDIUM'
            elif confidence >= 35:
                confidence_level = 'LOW'
            else:
                confidence_level = 'VERY_LOW'

            # Create thought log
            thought = PaperAIThoughtLog.objects.create(
                account=self.account,
                decision_type=action,
                token_symbol=token_symbol,
                token_address=token_address,
                confidence_level=confidence_level,
                confidence_percent=Decimal(str(confidence)),
                risk_score=Decimal(str(risk_score)),
                opportunity_score=Decimal(str(opportunity_score)),
                primary_reasoning=reasoning[:500],  # Limit to 500 chars
                key_factors=metadata.get('key_factors', []),
                positive_signals=metadata.get('positive_signals', []),
                negative_signals=metadata.get('negative_signals', []),
                market_data=metadata,
                strategy_name=decision_type,
                lane_used=metadata.get('analysis_path', 'UNKNOWN'),
                created_at=timezone.now()
            )

            logger.debug(
                f"[THOUGHT LOG] Logged {action} decision for {token_symbol} "
                f"(Confidence: {confidence:.1f}%)"
            )

            return thought

        except Exception as e:
            logger.error(
                f"[THOUGHT LOG] Failed to log thought: {e}",
                exc_info=True
            )
            return None

    # =========================================================================
    # TRANSACTION MONITORING
    # =========================================================================

    def check_pending_transactions(
        self,
        pending_transactions: List[Any]
    ) -> List[Any]:
        """
        Check status of pending transactions (TX Manager integration).

        Args:
            pending_transactions: List of pending transaction objects

        Returns:
            Updated list of still-pending transactions
        """
        if not self.use_tx_manager:
            return []

        try:
            # Try to import transaction manager
            try:
                from trading.services.transaction_manager import get_transaction_manager
                tx_manager = get_transaction_manager()
            except ImportError:
                logger.debug("[TX CHECK] Transaction Manager not available")
                return []

            if not tx_manager:
                return []

            # Check each pending transaction
            still_pending = []
            for tx in pending_transactions:
                tx_hash = getattr(tx, 'tx_hash', None)
                if not tx_hash:
                    continue

                # Check transaction status
                status = tx_manager.check_transaction_status(tx_hash)

                if status == 'pending':
                    still_pending.append(tx)
                elif status == 'confirmed':
                    logger.info(f"[TX CHECK] ✅ Transaction confirmed: {tx_hash}")
                elif status == 'failed':
                    logger.warning(f"[TX CHECK] ❌ Transaction failed: {tx_hash}")
                else:
                    logger.debug(f"[TX CHECK] Unknown status for {tx_hash}: {status}")

            logger.debug(
                f"[TX CHECK] Checked {len(pending_transactions)} transactions, "
                f"{len(still_pending)} still pending"
            )

            return still_pending

        except Exception as e:
            logger.error(
                f"[TX CHECK] Error checking transactions: {e}",
                exc_info=True
            )
            return pending_transactions  # Return original list on error

    # =========================================================================
    # ARBITRAGE STATISTICS
    # =========================================================================

    def get_arbitrage_stats(
        self,
        check_arbitrage: bool,
        opportunities_found: int,
        trades_executed: int,
        arbitrage_detector: Optional[Any] = None,
        dex_comparator: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Get arbitrage statistics for reporting.

        Args:
            check_arbitrage: Whether arbitrage detection is enabled
            opportunities_found: Number of opportunities found
            trades_executed: Number of arbitrage trades executed
            arbitrage_detector: Optional arbitrage detector instance
            dex_comparator: Optional DEX comparator instance

        Returns:
            Dictionary with arbitrage statistics
        """
        try:
            stats = {
                'enabled': check_arbitrage,
                'opportunities_found': opportunities_found,
                'trades_executed': trades_executed,
                'success_rate': 0.0,
                'detector_available': arbitrage_detector is not None,
                'comparator_available': dex_comparator is not None
            }

            # Calculate success rate
            if opportunities_found > 0:
                stats['success_rate'] = (
                    trades_executed / opportunities_found * 100
                )

            # Get detector stats if available
            if arbitrage_detector:
                detector_stats = getattr(arbitrage_detector, 'stats', {})
                stats.update({
                    'detector_stats': detector_stats
                })

            # Get comparator stats if available
            if dex_comparator:
                comparator_stats = getattr(dex_comparator, 'stats', {})
                stats.update({
                    'comparator_stats': comparator_stats
                })

            return stats

        except Exception as e:
            logger.error(
                f"[ARB STATS] Error getting arbitrage stats: {e}",
                exc_info=True
            )
            return {
                'enabled': check_arbitrage,
                'opportunities_found': opportunities_found,
                'trades_executed': trades_executed,
                'success_rate': 0.0,
                'error': str(e)
            }

    # =========================================================================
    # STATUS FORMATTING
    # =========================================================================

    def format_bot_status(
        self,
        status: str,
        tick_count: int,
        positions: Dict[str, Any],
        arbitrage_stats: Dict[str, Any],
        circuit_breaker_enabled: bool = False,
        pending_tx_count: int = 0
    ) -> Dict[str, Any]:
        """
        Format bot status data for WebSocket updates.

        Args:
            status: Bot status string
            tick_count: Current tick count
            positions: Dictionary of open positions
            arbitrage_stats: Arbitrage statistics
            circuit_breaker_enabled: Whether circuit breaker is enabled
            pending_tx_count: Number of pending transactions

        Returns:
            Formatted status dictionary
        """
        try:
            # Calculate portfolio values
            account_cash = float(self.account.current_balance_usd)
            total_positions_value = sum(
                float(pos.current_value_usd)
                for pos in positions.values()
            )
            total_portfolio_value = account_cash + total_positions_value

            # Format positions data
            positions_data = []
            for token_symbol, position in positions.items():
                position_value = float(position.current_value_usd)
                invested = float(position.total_invested_usd)
                pnl_percent = (
                    ((position_value - invested) / invested * 100)
                    if invested > 0
                    else 0.0
                )

                positions_data.append({
                    'token_symbol': token_symbol,
                    'quantity': float(position.quantity),
                    'invested_usd': invested,
                    'current_value_usd': position_value,
                    'pnl_percent': pnl_percent
                })

            # Build status data
            status_data = {
                'bot_status': status,
                'account_balance': account_cash,
                'total_portfolio_value': total_portfolio_value,
                'positions_value': total_positions_value,
                'open_positions': positions_data,
                'position_count': len(positions),
                'tick_count': tick_count,
                'circuit_breaker_enabled': circuit_breaker_enabled,
                'tx_manager_enabled': self.use_tx_manager,
                'pending_transactions': pending_tx_count,
                'timestamp': timezone.now().isoformat(),
                # Arbitrage stats
                'arbitrage_enabled': arbitrage_stats.get('enabled', False),
                'arbitrage_opportunities_found': arbitrage_stats.get('opportunities_found', 0),
                'arbitrage_trades_executed': arbitrage_stats.get('trades_executed', 0),
                'arbitrage_success_rate': arbitrage_stats.get('success_rate', 0.0)
            }

            return status_data

        except Exception as e:
            logger.error(
                f"[STATUS FORMAT] Error formatting bot status: {e}",
                exc_info=True
            )
            return {
                'bot_status': 'ERROR',
                'error': str(e),
                'timestamp': timezone.now().isoformat()
            }

    # =========================================================================
    # TRADE SIZE CALCULATIONS
    # =========================================================================

    def calculate_trade_size(
        self,
        token_symbol: str,
        current_price: Decimal,
        position_manager: Any,
        max_position_size_percent: Decimal = Decimal('20.0')
    ) -> Decimal:
        """
        Calculate appropriate trade size for a token.

        Takes into account:
        - Available account balance
        - Maximum position size percentage
        - Existing position (if any)
        - Minimum trade size

        Args:
            token_symbol: Token symbol
            current_price: Current token price
            position_manager: PositionManager instance
            max_position_size_percent: Max position size as % of account

        Returns:
            Trade size in USD
        """
        try:
            # Get account balance
            available_balance = self.account.current_balance_usd

            # Calculate max position size
            max_position_size_usd = (
                available_balance * max_position_size_percent / Decimal('100')
            )

            # Check if we already have a position
            existing_position = position_manager.get_position(token_symbol)
            if existing_position:
                # Already have position - reduce trade size
                current_investment = existing_position.total_invested_usd
                remaining_allocation = max_position_size_usd - current_investment

                if remaining_allocation <= Decimal('0'):
                    logger.debug(
                        f"[TRADE SIZE] Position for {token_symbol} already at max size"
                    )
                    return Decimal('0')

                trade_size = min(remaining_allocation, max_position_size_usd)
            else:
                # No position - use full allocation
                trade_size = max_position_size_usd

            # Apply minimum trade size
            min_trade_size = Decimal('50.0')  # $50 minimum
            if trade_size < min_trade_size:
                logger.debug(
                    f"[TRADE SIZE] Trade size ${trade_size:.2f} below minimum "
                    f"${min_trade_size:.2f}"
                )
                return Decimal('0')

            # Ensure we have enough balance
            if trade_size > available_balance:
                logger.warning(
                    f"[TRADE SIZE] Trade size ${trade_size:.2f} exceeds "
                    f"available balance ${available_balance:.2f}"
                )
                trade_size = available_balance

            logger.debug(
                f"[TRADE SIZE] Calculated ${trade_size:.2f} for {token_symbol}"
            )

            return trade_size

        except Exception as e:
            logger.error(
                f"[TRADE SIZE] Error calculating trade size: {e}",
                exc_info=True
            )
            return Decimal('0')

    # =========================================================================
    # COOLDOWN CHECKS
    # =========================================================================

    def is_token_in_cooldown(
        self,
        token_symbol: str,
        last_trade_time: Optional[Any],
        cooldown_minutes: int
    ) -> bool:
        """
        Check if a token is in cooldown period.

        Args:
            token_symbol: Token symbol to check
            last_trade_time: Timestamp of last trade
            cooldown_minutes: Cooldown period in minutes

        Returns:
            True if in cooldown, False otherwise
        """
        if not last_trade_time:
            return False

        if cooldown_minutes == 0:
            return False

        try:
            from datetime import timedelta

            time_since_trade = timezone.now() - last_trade_time
            cooldown_period = timedelta(minutes=cooldown_minutes)

            in_cooldown = time_since_trade < cooldown_period

            if in_cooldown:
                remaining_minutes = (cooldown_period - time_since_trade).total_seconds() / 60
                logger.debug(
                    f"[COOLDOWN] {token_symbol} in cooldown "
                    f"({remaining_minutes:.1f} minutes remaining)"
                )

            return in_cooldown

        except Exception as e:
            logger.error(
                f"[COOLDOWN] Error checking cooldown: {e}",
                exc_info=True
            )
            return False

    # =========================================================================
    # PERFORMANCE CALCULATIONS
    # =========================================================================

    def calculate_session_performance(
        self,
        session: PaperTradingSession
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive session performance metrics.

        Args:
            session: Trading session object

        Returns:
            Dictionary with performance metrics
        """
        try:
            from paper_trading.models import PaperPosition, PaperTrade

            # Get all trades for this session
            trades = PaperTrade.objects.filter(
                account=self.account,
                created_at__gte=session.started_at,
                status='EXECUTED'
            )

            total_trades = trades.count()
            buy_trades = trades.filter(trade_type='buy').count()
            sell_trades = trades.filter(trade_type='sell').count()

            # Get closed positions for this session
            closed_positions = PaperPosition.objects.filter(
                account=self.account,
                is_open=False,
                closed_at__gte=session.started_at
            )

            total_closed = closed_positions.count()
            profitable_closed = closed_positions.filter(
                realized_pnl_usd__gt=0
            ).count()

            win_rate = (
                (profitable_closed / total_closed * 100)
                if total_closed > 0
                else 0.0
            )

            # Calculate total P&L
            total_realized_pnl = sum(
                pos.realized_pnl_usd or Decimal('0')
                for pos in closed_positions
            )

            # Get open positions P&L
            open_positions = PaperPosition.objects.filter(
                account=self.account,
                is_open=True
            )

            total_unrealized_pnl = sum(
                pos.unrealized_pnl_usd or Decimal('0')
                for pos in open_positions
            )

            total_pnl = total_realized_pnl + total_unrealized_pnl

            # Calculate session duration
            if session.stopped_at:
                duration = session.stopped_at - session.started_at
            else:
                duration = timezone.now() - session.started_at

            duration_hours = duration.total_seconds() / 3600

            return {
                'total_trades': total_trades,
                'buy_trades': buy_trades,
                'sell_trades': sell_trades,
                'closed_positions': total_closed,
                'profitable_positions': profitable_closed,
                'losing_positions': total_closed - profitable_closed,
                'win_rate': float(win_rate),
                'total_realized_pnl': float(total_realized_pnl),
                'total_unrealized_pnl': float(total_unrealized_pnl),
                'total_pnl': float(total_pnl),
                'duration_hours': float(duration_hours),
                'trades_per_hour': (
                    total_trades / duration_hours
                    if duration_hours > 0
                    else 0.0
                )
            }

        except Exception as e:
            logger.error(
                f"[PERFORMANCE] Error calculating session performance: {e}",
                exc_info=True
            )
            return {
                'error': str(e)
            }