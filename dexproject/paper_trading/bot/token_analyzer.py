"""
Token Analyzer for Paper Trading Bot - Token Analysis Module

This module handles the analysis of individual tokens for buy opportunities.
It integrates real blockchain data and coordinates with the strategy selector
to determine the optimal entry approach.

RESPONSIBILITIES:
- Analyze tokens with REAL blockchain data
- Calculate initial trade sizes
- Build market context from real data
- Coordinate with intelligence engine for decisions
- Delegate strategy selection and execution
- Track cooldowns for trading decisions
- Log AI thought processes

File: dexproject/paper_trading/bot/token_analyzer.py
"""

import logging
from decimal import Decimal
from typing import Dict, Optional, Any

from django.utils import timezone
from asgiref.sync import async_to_sync

from paper_trading.models import (
    PaperTradingAccount,
    PaperStrategyConfiguration
)

from paper_trading.intelligence.core.base import (
    MarketContext,
    TradingDecision
)
from paper_trading.intelligence.core.intel_slider import IntelSliderEngine
from paper_trading.constants import StrategyType

logger = logging.getLogger(__name__)


class TokenAnalyzer:
    """
    Analyzes individual tokens for trading opportunities.
    
    This class performs comprehensive token analysis using:
    - Real blockchain data (gas, liquidity, volatility)
    - Intelligence engine for decision making
    - Strategy selection for optimal entry
    - Cooldown management to prevent overtrading
    
    Key Features:
    - REAL data integration from CompositeMarketAnalyzer
    - Position-aware analysis (different logic for existing vs new positions)
    - Intelligent strategy selection (SPOT/DCA/GRID/TWAP)
    - Trade cooldown enforcement
    - Arbitrage opportunity tracking
    """

    def __init__(
        self,
        account: PaperTradingAccount,
        intelligence_engine: IntelSliderEngine,
        strategy_config: Optional[PaperStrategyConfiguration] = None,
        arbitrage_detector: Optional[Any] = None,
        dex_comparator: Optional[Any] = None,
        check_arbitrage: bool = False
    ) -> None:
        """
        Initialize Token Analyzer.
        
        Args:
            account: Paper trading account
            intelligence_engine: Intelligence engine for decision making
            strategy_config: Optional strategy configuration
            arbitrage_detector: Optional arbitrage detector
            dex_comparator: Optional DEX price comparator
            check_arbitrage: Whether to check for arbitrage opportunities
        """
        self.account = account
        self.intelligence_engine = intelligence_engine
        self.strategy_config = strategy_config
        self.arbitrage_detector = arbitrage_detector
        self.dex_comparator = dex_comparator
        self.check_arbitrage = check_arbitrage
        
        # Track decisions and arbitrage stats
        self.last_decisions: Dict[str, TradingDecision] = {}
        self.arbitrage_opportunities_found = 0
        self.arbitrage_trades_executed = 0
        
        logger.info(
            f"[TOKEN ANALYZER] Initialized for account: {account.account_id}"
        )

    # =========================================================================
    # TOKEN ANALYSIS WITH REAL DATA INTEGRATION + STRATEGY SELECTION
    # =========================================================================

    def analyze_token(
        self,
        token_data: Dict[str, Any],
        price_manager: Any,
        position_manager: Any,
        trade_executor: Any
    ) -> None:
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
        SPOT, DCA, GRID, and TWAP strategies based on market conditions.

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

            # Type assertions - tell Pylance these are not None after validation
            assert token_symbol is not None
            assert token_address is not None
            assert isinstance(current_price, Decimal)

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
                    price_history=[{'price': Decimal(str(p))} for p in price_history] if price_history else None,
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
                # Use correct field names from analyzers
                liquidity_usd = Decimal(str(liquidity_analysis.get('pool_liquidity_usd', 0)))
                volatility = Decimal(str(volatility_analysis.get('volatility_percent', 0)))
                gas_price = Decimal(str(gas_analysis.get('gas_price_gwei', 1.0)))
                trend_direction = volatility_analysis.get('trend_direction', 'unknown')
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
                token_symbol=token_symbol,
                token_address=token_address,
                current_price=current_price,
                price_24h_ago=price_24h_ago,
                liquidity_usd=liquidity_usd,
                volatility=volatility,
                gas_price_gwei=gas_price,
                trend_direction=trend_direction,
                confidence_in_data=100.0 if data_quality == 'GOOD' else 50.0
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
                # Already have position - pass position data to decision engine for SELL evaluation
                position = all_positions[token_symbol]
                
                # Calculate hold time in hours
                position_age = timezone.now() - position.opened_at
                hold_time_hours = position_age.total_seconds() / 3600.0
                
                # Call make_decision with position parameters
                decision = async_to_sync(self.intelligence_engine.make_decision)(
                    market_context=market_context,
                    account_balance=self.account.current_balance_usd,
                    existing_positions=list(existing_positions.values()),
                    token_address=token_address,
                    token_symbol=token_symbol,
                    # Position-specific parameters for SELL evaluation
                    position_entry_price=position.average_entry_price_usd,
                    position_current_value=position.current_value_usd,
                    position_invested=position.total_invested_usd,
                    position_hold_time_hours=hold_time_hours
                )
            else:
                # No position - evaluate for BUY
                decision = async_to_sync(self.intelligence_engine.make_decision)(
                    market_context=market_context,
                    account_balance=self.account.current_balance_usd,
                    existing_positions=list(existing_positions.values()),
                    token_address=token_address,
                    token_symbol=token_symbol
                )

            # Log the decision
            from paper_trading.bot.market_helpers import MarketHelpers
            helpers = MarketHelpers(
                account=self.account,
                intelligence_engine=self.intelligence_engine
            )
            
            helpers.log_thought(
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
                    'has_position': has_position
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
                if helpers.is_on_cooldown(token_symbol, trade_type='BUY'):
                    cooldown_remaining = helpers.get_cooldown_remaining(token_symbol, trade_type='BUY')
                    logger.info(
                        f"[COOLDOWN] Skipping BUY on {token_symbol} - "
                        f"cooldown active ({cooldown_remaining:.1f} min remaining)"
                    )
                else:
                    # Import strategy components
                    from paper_trading.bot.strategy_selector import StrategySelector
                    from paper_trading.bot.strategy_launcher import StrategyLauncher
                    
                    # Select optimal strategy based on market conditions
                    strategy_selector = StrategySelector(
                        strategy_config=self.strategy_config
                    )
                    
                    selected_strategy = strategy_selector.select_strategy(
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
                    
                    strategy_launcher = StrategyLauncher(
                        account=self.account,
                        strategy_config=self.strategy_config,
                        intelligence_engine=self.intelligence_engine
                    )

                    if selected_strategy == StrategyType.TWAP:
                        success = strategy_launcher.start_twap_strategy(
                            token_address=token_address,
                            token_symbol=token_symbol,
                            decision=decision
                        )

                    elif selected_strategy == StrategyType.DCA:
                        success = strategy_launcher.start_dca_strategy(
                            token_address=token_address,
                            token_symbol=token_symbol,
                            decision=decision
                        )

                    elif selected_strategy == StrategyType.GRID:
                        success = strategy_launcher.start_grid_strategy(
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
                        helpers.set_trade_cooldown(token_symbol)

            elif decision.action == 'SELL':
                # SELL logic remains unchanged (spot execution)
                if helpers.is_on_cooldown(token_symbol, trade_type='SELL'):
                    cooldown_remaining = helpers.get_cooldown_remaining(token_symbol, trade_type='SELL')
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
                        helpers.set_trade_cooldown(token_symbol)

            # Track the decision
            self.last_decisions[token_symbol] = decision

        except Exception as e:
            logger.error(
                f"[TOKEN ANALYZER] Failed to analyze token {token_data.get('symbol', 'UNKNOWN')}: {e}",
                exc_info=True
            )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

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
                f"[TOKEN ANALYZER] Error calculating trade size for {token_symbol}: {e}"
            )
            # Return safe default
            return Decimal('500')