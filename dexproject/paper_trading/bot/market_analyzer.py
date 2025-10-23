"""
Market Analyzer for Paper Trading Bot

This module handles market analysis operations for the paper trading bot,
including tick coordination, token analysis, performance metrics, and
AI thought logging.

Responsibilities:
- Coordinate market ticks (main bot loop)
- Analyze individual tokens for trading opportunities
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
from datetime import datetime, timedelta

from django.utils import timezone
from asgiref.sync import async_to_sync

from paper_trading.models import (
    PaperTradingAccount,
    PaperTradingSession,
    PaperStrategyConfiguration,
    PaperAIThoughtLog,
    PaperPerformanceMetrics,
    PaperTrade
)

# Import intelligence types
from paper_trading.intelligence.base import (
    IntelligenceLevel,
    MarketContext,
    TradingDecision
)
from paper_trading.intelligence.intel_slider import IntelSliderEngine

# Import WebSocket service
from paper_trading.services.websocket_service import websocket_service

# Import Transaction Manager status (optional)
try:
    from trading.services.transaction_manager import TransactionStatus
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
            intelligence_engine: Intelligence engine for decisions
            strategy_config: Strategy configuration
            circuit_breaker_manager: Circuit breaker manager (optional)
            use_tx_manager: Whether TX Manager is enabled
        """
        self.account = account
        self.session = session
        self.intelligence_engine = intelligence_engine
        self.strategy_config = strategy_config
        self.circuit_breaker_manager = circuit_breaker_manager
        self.use_tx_manager = use_tx_manager
        
        # Tick tracking
        self.tick_count = 0
        self.tick_interval = 15  # seconds between ticks
        
        # Price history for trend analysis
        self.price_history: Dict[str, List[Decimal]] = {}
        
        # Last decisions for tracking
        self.last_decisions: Dict[str, TradingDecision] = {}
        
        # Pending transactions (TX Manager)
        self.pending_transactions: Dict[str, Dict[str, Any]] = {}
        
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
        Execute a single market analysis tick.
        
        This is the main coordination method called on each bot loop iteration.
        It orchestrates all market analysis activities including:
        - Updating prices
        - Checking circuit breakers
        - Analyzing tokens
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
        
        # Check for positions to auto-close
        self._check_auto_close_positions(
            price_manager,
            position_manager,
            trade_executor
        )
        
        # Analyze each token for trading opportunities
        token_list = price_manager.get_token_list()
        for token_data in token_list:
            self._analyze_token(
                token_data,
                price_manager,
                position_manager,
                trade_executor
            )
        
        # Update performance metrics
        self._update_performance_metrics(trade_executor)
        
        # Send status update
        self._send_bot_status_update(
            'running',
            price_manager,
            position_manager,
            trade_executor
        )
    
    # =========================================================================
    # PRICE UPDATES
    # =========================================================================
    
    def _update_market_prices(self, price_manager: Any):
        """
        Update all token prices via the price manager.
        
        Args:
            price_manager: RealPriceManager instance
        """
        try:
            from paper_trading.bot.price_service_integration import update_prices_sync
            
            # Update prices through price manager
            results = update_prices_sync(price_manager)
            
            # Update price history for each token
            token_list = price_manager.get_token_list()
            for token in token_list:
                symbol = token['symbol']
                price = token['price']
                
                if symbol not in self.price_history:
                    self.price_history[symbol] = []
                
                self.price_history[symbol].append(price)
                
                # Keep only last 100 prices for memory efficiency
                if len(self.price_history[symbol]) > 100:
                    self.price_history[symbol].pop(0)
            
            logger.debug(
                f"[MARKET] Updated prices for {len(token_list)} tokens"
            )
            
        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Failed to update market prices: {e}",
                exc_info=True
            )
    
    # =========================================================================
    # AUTO-CLOSE CHECKS
    # =========================================================================
    
    def _check_auto_close_positions(
        self,
        price_manager: Any,
        position_manager: Any,
        trade_executor: Any
    ):
        """
        Check all positions for auto-close conditions and execute closes.
        
        Args:
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
        """
        try:
            token_list = price_manager.get_token_list()
            
            # Get positions to close
            positions_to_close = position_manager.check_auto_close_positions(
                token_list
            )
            
            # Execute auto-closes
            for token_symbol, reason, pnl_percent in positions_to_close:
                self._execute_auto_close(
                    token_symbol,
                    reason,
                    pnl_percent,
                    price_manager,
                    position_manager,
                    trade_executor
                )
            
        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Failed to check auto-close positions: {e}",
                exc_info=True
            )
    
    def _execute_auto_close(
        self,
        token_symbol: str,
        reason: str,
        pnl_percent: float,
        price_manager: Any,
        position_manager: Any,
        trade_executor: Any
    ):
        """
        Execute an automatic position close.
        
        Args:
            token_symbol: Token symbol to close
            reason: Reason for auto-close
            pnl_percent: Current P&L percentage
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
        """
        try:
            # Get position
            position = position_manager.get_position(token_symbol)
            if not position:
                logger.warning(
                    f"[AUTO-CLOSE] Position {token_symbol} not found"
                )
                return
            
            # Get current price
            current_price = price_manager.get_token_price(token_symbol)
            if not current_price:
                logger.error(
                    f"[AUTO-CLOSE] Could not get price for {token_symbol}"
                )
                return
            
            # Create a SELL decision for auto-close
            decision = TradingDecision(
                action='SELL',
                token_address=position.token_address,
                token_symbol=token_symbol,
                position_size_percent=Decimal('100'),  # Close entire position
                position_size_usd=position.current_value_usd,
                stop_loss_percent=(
                    self.strategy_config.stop_loss_percent
                    if self.strategy_config
                    else Decimal('5')
                ),
                take_profit_targets=[],
                execution_mode='IMMEDIATE',
                use_private_relay=False,
                gas_strategy='standard',
                max_gas_price_gwei=Decimal('50'),
                overall_confidence=Decimal('100'),
                risk_score=Decimal('0'),
                opportunity_score=Decimal('0'),
                primary_reasoning=(
                    f"Auto-close triggered: {reason}. P&L: {pnl_percent:+.2f}%"
                ),
                risk_factors=[f"Auto-close: {reason}"],
                opportunity_factors=[],
                mitigation_strategies=[],
                intel_level_used=self.intelligence_engine.intel_level,
                intel_adjustments={},
                time_sensitivity='HIGH',
                max_execution_time_ms=1000,
                processing_time_ms=100
            )
            
            # Log the auto-close decision
            self._log_thought(
                action="SELL",
                reasoning=(
                    f"Auto-close: {reason}. Position P&L: {pnl_percent:+.2f}%. "
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
                position_manager=position_manager
            )
            
            if success:
                logger.info(
                    f"[AUTO-CLOSE] Successfully closed {token_symbol} position: "
                    f"Reason={reason}, P&L={pnl_percent:+.2f}%"
                )
            else:
                logger.error(
                    f"[AUTO-CLOSE] Failed to close {token_symbol} position"
                )
            
        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Failed to execute auto-close for "
                f"{token_symbol}: {e}",
                exc_info=True
            )
    
    # =========================================================================
    # TOKEN ANALYSIS
    # =========================================================================
    
    def _analyze_token(
        self,
        token_data: Dict[str, Any],
        price_manager: Any,
        position_manager: Any,
        trade_executor: Any
    ):
        """
        Analyze a single token for trading opportunities.
        
        Args:
            token_data: Token data with current price
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
        """
        try:
            token_symbol = token_data['symbol']
            current_price = token_data['price']
            
            # Prepare market context
            price_history = price_manager.get_price_history(token_symbol, limit=24)
            price_24h_ago = price_history[0] if price_history else current_price
            
            market_context = MarketContext(
                token_address=token_data['address'],
                token_symbol=token_symbol,
                current_price=current_price,
                price_24h_ago=price_24h_ago,
                volume_24h=Decimal('1000000'),  # Would be real in production
                liquidity_usd=Decimal('5000000'),  # Would be real in production
                holder_count=1000,  # Would be real in production
                market_cap=Decimal('50000000'),  # Would be real in production
                volatility=Decimal('0.15'),  # Calculate from price history
                trend='neutral',
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

            self.intelligence_engine.update_market_context(market_context)
            
            # Make trading decision
            decision = async_to_sync(self.intelligence_engine.make_decision)(
                market_context=market_context,
                account_balance=self.account.current_balance_usd,
                existing_positions=existing_positions,
                token_address=token_data['address'],
                token_symbol=token_symbol
            )
            
            # Log thought process
            thought_log = self.intelligence_engine.generate_thought_log(decision)
            self._log_thought(
                action=decision.action,
                reasoning=thought_log,
                confidence=float(decision.overall_confidence),
                decision_type="TRADE_DECISION",
                metadata={
                    'token': token_symbol,
                    'token_address': token_data['address'],
                    'intel_level': self.intelligence_engine.intel_level,
                    'risk_score': float(decision.risk_score),
                    'opportunity_score': float(decision.opportunity_score),
                    'current_price': float(current_price),
                    'tx_manager_enabled': self.use_tx_manager
                }
            )
            
            # Execute trade if decided
            if decision.action in ['BUY', 'SELL']:
                trade_executor.execute_trade(
                    decision=decision,
                    token_symbol=token_symbol,
                    current_price=current_price,
                    position_manager=position_manager
                )
            
            # Store decision for tracking
            self.last_decisions[token_symbol] = decision
            
        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Failed to analyze {token_data.get('symbol', 'unknown')}: {e}",
                exc_info=True
            )
    
    # =========================================================================
    # TRANSACTION MANAGER STATUS CHECKS
    # =========================================================================
    
    def _check_pending_transactions(self, trade_executor: Any):
        """
        Check status of pending transactions from Transaction Manager.
        
        Args:
            trade_executor: TradeExecutor instance with TX Manager
        """
        if not self.use_tx_manager or not trade_executor.tx_manager:
            return
        
        async def check_transactions():
            completed = []
            for tx_id, tx_info in trade_executor.pending_transactions.items():
                try:
                    tx_state = await trade_executor.tx_manager.get_transaction_status(
                        tx_id
                    )
                    if tx_state:
                        if tx_state.status == TransactionStatus.COMPLETED:
                            logger.info(
                                f"[TX MANAGER] Transaction completed: {tx_id}"
                            )
                            if tx_state.gas_savings_percent:
                                trade_executor.total_gas_savings += tx_state.gas_savings_percent
                                logger.info(
                                    f"[TX MANAGER] Gas saved: "
                                    f"{tx_state.gas_savings_percent:.2f}%"
                                )
                            completed.append(tx_id)
                        elif tx_state.status == TransactionStatus.FAILED:
                            logger.error(
                                f"[TX MANAGER] Transaction failed: {tx_id}"
                            )
                            completed.append(tx_id)
                            trade_executor.consecutive_failures += 1
                        elif tx_state.status == TransactionStatus.BLOCKED_BY_CIRCUIT_BREAKER:
                            logger.warning(
                                f"[TX MANAGER] Transaction blocked by "
                                f"circuit breaker: {tx_id}"
                            )
                            completed.append(tx_id)
                except Exception as e:
                    logger.error(
                        f"[TX MANAGER] Error checking transaction {tx_id}: {e}"
                    )
            
            # Remove completed transactions
            for tx_id in completed:
                del trade_executor.pending_transactions[tx_id]
        
        async_to_sync(check_transactions)()
    
    # =========================================================================
    # PERFORMANCE METRICS
    # =========================================================================
    
    def _update_performance_metrics(self, trade_executor: Any):
        """
        Update performance metrics for the session.
        
        Args:
            trade_executor: TradeExecutor instance
        """
        try:
            # Calculate metrics
            total_trades = PaperTrade.objects.filter(
                account=self.account,
                created_at__gte=self.session.started_at
            ).count()
            
            if total_trades == 0:
                return
            
            winning_trades = PaperTrade.objects.filter(
                account=self.account,
                created_at__gte=self.session.started_at,
                status='completed'
            ).count()
            
            win_rate = (
                (winning_trades / total_trades * 100)
                if total_trades > 0
                else 0
            )
            
            # Calculate gas savings metrics if TX Manager is used
            avg_gas_savings = Decimal('0')
            if trade_executor.trades_with_tx_manager > 0:
                avg_gas_savings = (
                    trade_executor.total_gas_savings /
                    trade_executor.trades_with_tx_manager
                )
            
            # Create or update metrics
            metrics, created = PaperPerformanceMetrics.objects.get_or_create(
                session=self.session,
                period_start=self.session.started_at,
                period_end=timezone.now(),
                defaults={
                    'total_trades': total_trades,
                    'winning_trades': winning_trades,
                    'losing_trades': total_trades - winning_trades,
                    'win_rate': Decimal(str(win_rate)),
                    'total_pnl_usd': (
                        self.account.current_balance_usd -
                        self.session.starting_balance_usd
                    ),
                    'total_pnl_percent': (
                        ((self.account.current_balance_usd /
                          self.session.starting_balance_usd) - 1) * 100
                        if self.session.starting_balance_usd > 0
                        else 0
                    ),
                    'avg_win_usd': Decimal('0'),
                    'avg_loss_usd': Decimal('0'),
                    'largest_win_usd': Decimal('0'),
                    'largest_loss_usd': Decimal('0'),
                    'sharpe_ratio': None,
                    'max_drawdown_percent': Decimal('0'),
                    'profit_factor': None,
                    'avg_execution_time_ms': 100,
                    'total_gas_fees_usd': (
                        Decimal('5') * total_trades *
                        (Decimal('1') - avg_gas_savings / 100)
                    ),
                    'avg_slippage_percent': Decimal('1'),
                    'fast_lane_trades': 0,
                    'smart_lane_trades': total_trades,
                    'fast_lane_win_rate': Decimal('0'),
                    'smart_lane_win_rate': Decimal(str(win_rate))
                }
            )
            
            if not created:
                metrics.total_trades = total_trades
                metrics.winning_trades = winning_trades
                metrics.losing_trades = total_trades - winning_trades
                metrics.win_rate = Decimal(str(win_rate))
                metrics.total_pnl_usd = (
                    self.account.current_balance_usd -
                    self.session.starting_balance_usd
                )
                metrics.total_pnl_percent = (
                    ((self.account.current_balance_usd /
                      self.session.starting_balance_usd) - 1) * 100
                    if self.session.starting_balance_usd > 0
                    else 0
                )
                metrics.total_gas_fees_usd = (
                    Decimal('5') * total_trades *
                    (Decimal('1') - avg_gas_savings / 100)
                )
                metrics.save()
            
            # Log TX Manager performance if enabled
            if self.use_tx_manager and trade_executor.trades_with_tx_manager > 0:
                logger.info(
                    f"[TX MANAGER] Performance: "
                    f"{trade_executor.trades_with_tx_manager} trades, "
                    f"Avg gas savings: {avg_gas_savings:.2f}%"
                )
            
        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Failed to update performance metrics: {e}",
                exc_info=True
            )
    
    # =========================================================================
    # THOUGHT LOGGING
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
        Log AI thought process to database.
        
        Args:
            action: Action being taken
            reasoning: Reasoning behind the action
            confidence: Confidence level (0-100)
            decision_type: Type of decision
            metadata: Additional metadata
        """
        try:
            metadata = metadata or {}
            
            # Map action to decision type
            decision_type_map = {
                'BUY': 'BUY',
                'SELL': 'SELL',
                'HOLD': 'HOLD',
                'SKIP': 'SKIP',
                'STARTUP': 'SKIP',
                'TRADE_DECISION': 'HOLD',
                'BLOCKED': 'SKIP',
                'CB_RESET': 'SKIP',
                'RISK_MANAGEMENT': 'SKIP'
            }
            
            # Get token info from metadata
            token_symbol = metadata.get('token', 'SYSTEM')
            token_address = metadata.get('token_address', '0x' + '0' * 40)
            
            # Create thought log record
            thought_log = PaperAIThoughtLog.objects.create(
                account=self.account,
                paper_trade=None,
                decision_type=decision_type_map.get(action, 'SKIP'),
                token_address=token_address,
                token_symbol=token_symbol,
                confidence_level=self._get_confidence_level(confidence),
                confidence_percent=Decimal(str(confidence)),
                risk_score=Decimal(str(metadata.get('risk_score', 50))),
                opportunity_score=Decimal(str(metadata.get('opportunity_score', 50))),
                primary_reasoning=reasoning[:500],
                key_factors=[
                    f"Intel Level: {metadata.get('intel_level', self.intelligence_engine.intel_level)}",
                    f"Current Price: ${metadata.get('current_price', 0):.2f}" if 'current_price' in metadata else "System Event",
                    f"TX Manager: {'Enabled' if metadata.get('tx_manager_enabled', False) else 'Disabled'}"
                ],
                positive_signals=[],
                negative_signals=[],
                market_data=metadata,
                strategy_name=f"Intel_{self.intelligence_engine.intel_level}",
                lane_used='SMART',
                analysis_time_ms=100
            )
            
            logger.debug(
                f"[THOUGHT] Logged: {action} for {token_symbol} "
                f"({confidence:.0f}% confidence)"
            )
            
        except Exception as e:
            logger.error(f"[MARKET ANALYZER] Failed to log thought: {e}")
    
    def _get_confidence_level(self, confidence: float) -> str:
        """Convert confidence percentage to level category."""
        if confidence >= 90:
            return 'VERY_HIGH'
        elif confidence >= 70:
            return 'HIGH'
        elif confidence >= 50:
            return 'MEDIUM'
        elif confidence >= 30:
            return 'LOW'
        else:
            return 'VERY_LOW'
    
    # =========================================================================
    # WEBSOCKET STATUS UPDATES
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
            status: Current bot status
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
        """
        try:
            # Ensure status is a string, not an enum
            # This prevents WebSocket serialization errors
            status_str = str(status) if not isinstance(status, str) else status
            
            # Build portfolio data with all primitives (no enums, no Decimals)
            portfolio_data = {
                'bot_status': status_str,  # ✅ Guaranteed string
                'intel_level': int(self.intelligence_engine.intel_level),
                'tx_manager_enabled': bool(self.use_tx_manager),
                'circuit_breaker_enabled': bool(self.circuit_breaker_manager is not None),
                'account_balance': float(self.account.current_balance_usd),
                'open_positions': int(position_manager.get_position_count()),
                'tick_count': int(self.tick_count),
                'total_gas_savings': (
                    float(trade_executor.total_gas_savings)
                    if self.use_tx_manager
                    else 0.0
                ),
                'pending_transactions': int(len(trade_executor.pending_transactions)),
                'consecutive_failures': int(trade_executor.consecutive_failures),
                'daily_trades': int(trade_executor.daily_trades_count)
            }
            
            # Send the update
            websocket_service.send_portfolio_update(
                account_id=str(self.account.account_id),
                portfolio_data=portfolio_data
            )
            
        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Failed to send status update: {e}",
                exc_info=True  # Include stack trace for debugging
            )