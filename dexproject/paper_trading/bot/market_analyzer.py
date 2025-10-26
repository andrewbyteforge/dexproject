"""
Market Analyzer for Paper Trading Bot - REAL DATA INTEGRATION

FIXED: Now calls CompositeMarketAnalyzer to get REAL blockchain data instead
of using hardcoded mock values.

This module handles market analysis operations for the paper trading bot,
including tick coordination, token analysis, performance metrics, and
AI thought logging.

Responsibilities:
- Coordinate market ticks (main bot loop)
- Analyze individual tokens with REAL market data
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
    
    NOW WITH REAL DATA INTEGRATION: Calls CompositeMarketAnalyzer to get
    actual blockchain data for gas, liquidity, volatility, and MEV analysis.
    
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
        
        Args:
            token_data: Token data with current price
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
        """
        try:
            token_symbol = token_data['symbol']
            token_address = token_data['address']
            current_price = token_data['price']
            
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
                composite_scores = real_analysis.get('composite_scores', {})
                
                # Extract real values
                liquidity_usd = Decimal(str(
                    liquidity_analysis.get('pool_liquidity_usd', 5000000)
                ))
                volatility = Decimal(str(
                    volatility_analysis.get('volatility_24h_percent', 15.0)
                )) / Decimal('100')  # Convert to decimal (15% -> 0.15)
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
                composite_scores = {}
                
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
            
            # Update engine with market context (for trend tracking)
            self.intelligence_engine.update_market_context(market_context)
            
            # Make trading decision with real market data
            decision = async_to_sync(self.intelligence_engine.make_decision)(
                market_context=market_context,
                account_balance=self.account.current_balance_usd,
                existing_positions=existing_positions,
                token_address=token_address,  # ✅ Added
                token_symbol=token_symbol     # ✅ Added
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
                    'tx_manager_enabled': self.use_tx_manager
                }
            )
            
            # Execute if not HOLD
            if decision.action != 'HOLD':
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
                
                current_price = token_data['price']
                
                # Calculate P&L percentage
                avg_entry = position.average_entry_price
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
                token_symbol=token_symbol,         # <-- use your in-scope variable for the token (e.g. "WETH")
                current_price=current_price,  # <-- use your in-scope Decimal price (e.g. Decimal("2500"))
                position_manager=position_manager,
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
                f"{position.token_symbol}: {e}",
                exc_info=True
            )
    
    # =========================================================================
    # TRANSACTION MANAGER INTEGRATION
    # =========================================================================
    
    def _check_pending_transactions(self, trade_executor: Any):
        """
        Check status of pending transactions via TX Manager.
        
        Args:
            trade_executor: TradeExecutor instance
        """
        try:
            if not TRANSACTION_MANAGER_AVAILABLE:
                return
            
            # Import TransactionStatus inside the method to avoid unbound issues
            try:
                from trading.services.transaction_manager import TransactionStatus
            except ImportError:
                logger.warning("[TX MANAGER] TransactionStatus not available")
                return
            
            # Check each pending transaction
            for tx_hash, tx_data in list(self.pending_transactions.items()):
                # Get TX Manager status
                status = trade_executor.check_transaction_status(tx_hash)
                
                # ✅ FIX 1: Handle TransactionStatus safely with getattr
                # Check for CONFIRMED status
                if status == getattr(TransactionStatus, 'CONFIRMED', 'CONFIRMED'):
                    logger.info(
                        f"[TX MANAGER] Transaction confirmed: {tx_hash[:10]}..."
                    )
                    del self.pending_transactions[tx_hash]
                    
                # Check for FAILED status
                elif status == getattr(TransactionStatus, 'FAILED', 'FAILED'):
                    logger.warning(
                        f"[TX MANAGER] Transaction failed: {tx_hash[:10]}..."
                    )
                    del self.pending_transactions[tx_hash]
                    
                # Check for TIMEOUT status (safely with getattr)
                elif status == getattr(TransactionStatus, 'TIMEOUT', None):
                    logger.warning(
                        f"[TX MANAGER] Transaction timeout: {tx_hash[:10]}..."
                    )
                    del self.pending_transactions[tx_hash]
            
        except Exception as e:
            logger.error(
                f"[MARKET ANALYZER] Failed to check pending transactions: {e}",
                exc_info=True
            )
    
    # =========================================================================
    # PERFORMANCE METRICS
    # =========================================================================
    
    def _update_performance_metrics(self, trade_executor: Any):
        """
        Update session performance metrics in database.
        
        Args:
            trade_executor: TradeExecutor instance
        """
        try:
            # Get all trades for this session
            trades = PaperTrade.objects.filter(account=self.account)
            
            if trades.exists():
                total_trades = trades.count()
                winning_trades = trades.filter(pnl_usd__gt=0).count()
                
                win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
                
                # Calculate gas savings if using TX Manager
                avg_gas_savings = Decimal('0')
                if self.use_tx_manager and trade_executor.trades_with_tx_manager > 0:
                    avg_gas_savings = (
                        trade_executor.total_gas_savings /
                        trade_executor.trades_with_tx_manager
                    )
            else:
                total_trades = 0
                winning_trades = 0
                win_rate = 0
                avg_gas_savings = Decimal('0')
            
            # Get starting balance from metadata (migration 0005 change)
            # Note: starting_balance_usd was moved from session field to session.metadata
            starting_balance = Decimal(str(self.session.metadata.get(
                'starting_balance_usd',
                float(self.account.initial_balance_usd)
            )))
            
            # Update or create metrics
            metrics, created = PaperPerformanceMetrics.objects.update_or_create(
                account=self.account,
                defaults={
                    'total_trades': total_trades,
                    'winning_trades': winning_trades,
                    'losing_trades': total_trades - winning_trades,
                    'win_rate': Decimal(str(win_rate)),
                    'total_pnl_usd': (
                        self.account.current_balance_usd - starting_balance
                    ),
                    'total_pnl_percent': Decimal(str(
                        ((self.account.current_balance_usd / starting_balance) - 1) * 100
                        if starting_balance > 0
                        else 0
                    )),
                    'largest_win_usd': Decimal('0'),
                    'largest_loss_usd': Decimal('0'),
                    'sharpe_ratio': None,
                    'max_drawdown_percent': Decimal('0'),
                    'profit_factor': None,
                    'avg_execution_time_ms': 100,
                    'total_gas_fees_usd': Decimal(str(
                        Decimal('5') * total_trades *
                        (Decimal('1') - avg_gas_savings / 100)
                    )),
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
                
                # Use starting_balance calculated at top of function
                metrics.total_pnl_usd = (
                    self.account.current_balance_usd - starting_balance
                )
                metrics.total_pnl_percent = Decimal(str(
                    ((self.account.current_balance_usd / starting_balance) - 1) * 100
                    if starting_balance > 0
                    else 0
                ))
                
                # Use setattr to avoid Pylance issues with unknown attributes
                if hasattr(metrics, 'total_gas_fees_usd'):
                    setattr(metrics, 'total_gas_fees_usd', Decimal(str(
                        Decimal('5') * total_trades *
                        (Decimal('1') - avg_gas_savings / 100)
                    )))
                
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
                
                # Extract risk and opportunity scores from metadata
                risk_score = metadata.get('risk_score', 50)
                opportunity_score = metadata.get('opportunity_score', 50)
                
                # Map confidence to level string (matching trade_executor.py)
                confidence_level_str = self._get_confidence_level(confidence)
                
                # Build enhanced market data including risk metrics
                enhanced_market_data = {
                    **metadata,
                    'risk_score': float(risk_score),
                    'opportunity_score': float(opportunity_score),
                    'intel_level': int(self.intelligence_engine.intel_level),
                }
                
                # Create thought log record with STANDARDIZED field mappings (matching trade_executor.py)
                PaperAIThoughtLog.objects.create(
                    account=self.account,
                    paper_trade=None,
                    decision_type=decision_type_map.get(action, 'SKIP'),
                    token_address=token_address,
                    token_symbol=token_symbol,
                    confidence_level=confidence_level_str,  # ✅ STRING (VERY_HIGH, HIGH, MEDIUM, LOW, VERY_LOW)
                    confidence_percent=Decimal(str(confidence)),  # ✅ DECIMAL (0-100)
                    risk_score=Decimal(str(risk_score)),  # ✅ DECIMAL
                    opportunity_score=Decimal(str(opportunity_score)),  # ✅ DECIMAL
                    primary_reasoning=reasoning[:500],  # ✅ CORRECT FIELD NAME (truncated to 500 chars)
                    key_factors=[
                        f"Intel Level: {metadata.get('intel_level', self.intelligence_engine.intel_level)}",
                        f"Current Price: ${metadata.get('current_price', 0):.2f}" if 'current_price' in metadata else "System Event",
                        f"TX Manager: {'Enabled' if metadata.get('tx_manager_enabled', False) else 'Disabled'}",
                        f"Risk Score: {risk_score}",
                        f"Opportunity Score: {opportunity_score}"
                    ],
                    positive_signals=[],
                    negative_signals=[],
                    market_data=enhanced_market_data,  # JSON field - stores all metrics
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
        """
        Convert confidence percentage to level category.
        
        Args:
            confidence: Confidence percentage (0-100)
            
        Returns:
            Confidence level string ('VERY_LOW' to 'VERY_HIGH')
        """
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