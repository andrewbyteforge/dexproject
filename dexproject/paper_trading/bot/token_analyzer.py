"""
Token Analyzer for Paper Trading Bot - BUY PATH ONLY

This module handles analysis of tokens for BUY opportunities. It ONLY processes
tokens that we DON'T currently own, ensuring clean separation from position
evaluation logic.

CRITICAL RULES:
1. ONLY analyzes tokens WITHOUT existing positions
2. ONLY returns BUY or SKIP decisions
3. NEVER returns SELL or HOLD decisions
4. Filters out owned tokens before analysis

This module was created as part of the buy/sell/hold logic refactoring to ensure
clear separation of concerns and prevent conflicting trading decisions.

File: dexproject/paper_trading/bot/token_analyzer.py
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Any

from asgiref.sync import async_to_sync

from paper_trading.models import PaperTradingAccount
from paper_trading.intelligence.core.base import MarketContext, TradingDecision
from paper_trading.intelligence.core.intel_slider import IntelSliderEngine
from paper_trading.constants import DecisionType

# Type hints for external dependencies (avoid circular imports)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from paper_trading.bot.price_service_integration import RealPriceManager
    from paper_trading.bot.position_manager import PositionManager
    from paper_trading.bot.trade_executor import TradeExecutor
    from paper_trading.intelligence.dex.dex_price_comparator import DEXPriceComparator
    from paper_trading.intelligence.strategies.arbitrage_engine import ArbitrageDetector

logger = logging.getLogger(__name__)


class TokenAnalyzer:
    """
    Analyzes tokens for BUY opportunities (tokens we DON'T own).

    This class is responsible for:
    - Filtering tokens to exclude positions we already have
    - Analyzing remaining tokens using intelligence engine
    - Returning BUY or SKIP decisions ONLY
    - Never analyzing tokens we already own

    Example usage:
        analyzer = TokenAnalyzer(
            account=account,
            intelligence_engine=engine,
            strategy_config=config
        )

        # Analyze all available tokens for buy opportunities
        analyzer.analyze_tokens_for_buy(
            tokens=all_tokens,
            price_manager=price_manager,
            position_manager=position_manager,
            trade_executor=trade_executor,
            thought_logger=thought_logger
        )
    """

    def __init__(
        self,
        account: PaperTradingAccount,
        intelligence_engine: IntelSliderEngine,
        strategy_config: Optional[Any] = None,
        arbitrage_detector: Optional['ArbitrageDetector'] = None,
        dex_comparator: Optional['DEXPriceComparator'] = None,
        check_arbitrage: bool = False
    ) -> None:
        """
        Initialize the Token Analyzer.

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

        # BUY cooldown tracking (Professional bot standard: 15 min)
        self.buy_cooldown_minutes = 15  # Unibot/Maestro: 10-15 min to prevent FOMO
        self.last_buy_attempts: Dict[str, Any] = {}  # token_symbol -> timestamp

        logger.info(
            "[TOKEN ANALYZER] Initialized token analyzer for BUY path "
            f"(Cooldown: {self.buy_cooldown_minutes} min)"
        )

    # =========================================================================
    # MAIN ANALYSIS METHOD
    # =========================================================================

    def analyze_tokens_for_buy(
        self,
        tokens: List[Dict[str, Any]],
        price_manager: 'RealPriceManager',
        position_manager: 'PositionManager',
        trade_executor: 'TradeExecutor',
        thought_logger: Any
    ) -> None:
        """
        Analyze all available tokens for BUY opportunities.

        This is the main entry point for token analysis. It:
        1. Filters OUT tokens we already have positions in
        2. Filters OUT tokens in cooldown period
        3. Analyzes remaining tokens with intelligence engine
        4. Executes BUY decisions if confidence is high enough

        Args:
            tokens: List of token data dicts
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
            thought_logger: Thought logging function from market_helpers
        """
        try:
            logger.info(f"[TOKEN ANALYZER] Analyzing {len(tokens)} tokens for BUY opportunities")

            # Get current positions to filter out
            current_positions = position_manager.get_all_positions()
            owned_tokens = set(current_positions.keys())

            logger.info(f"[TOKEN ANALYZER] Filtering out {len(owned_tokens)} owned tokens: {owned_tokens}")

            # Analyze each token
            for token_data in tokens:
                # Validate token_data
                if not isinstance(token_data, dict):
                    logger.warning(f"[TOKEN ANALYZER] Invalid token_data type: {type(token_data)}")
                    continue

                token_symbol = token_data.get('symbol')
                if not token_symbol:
                    logger.warning("[TOKEN ANALYZER] Token missing symbol, skipping")
                    continue

                # CRITICAL: Skip if we already own this token
                if token_symbol in owned_tokens:
                    logger.debug(
                        f"[TOKEN ANALYZER] Skipping {token_symbol} - "
                        "already have position (BUY path doesn't process owned tokens)"
                    )
                    continue

                # Check if token is in cooldown
                if not self._can_buy_token(token_symbol):
                    logger.debug(
                        f"[TOKEN ANALYZER] Skipping {token_symbol} - "
                        f"in BUY cooldown ({self.buy_cooldown_minutes} min)"
                    )
                    continue

                # Analyze this token for BUY
                self._analyze_single_token(
                    token_data=token_data,
                    price_manager=price_manager,
                    position_manager=position_manager,
                    trade_executor=trade_executor,
                    thought_logger=thought_logger
                )

            logger.info("[TOKEN ANALYZER] Completed BUY path analysis")

        except Exception as e:
            logger.error(
                f"[TOKEN ANALYZER] Error analyzing tokens for buy: {e}",
                exc_info=True
            )

    # =========================================================================
    # SINGLE TOKEN ANALYSIS
    # =========================================================================

    def _analyze_single_token(
        self,
        token_data: Dict[str, Any],
        price_manager: 'RealPriceManager',
        position_manager: 'PositionManager',
        trade_executor: 'TradeExecutor',
        thought_logger: Any
    ) -> None:
        """
        Analyze a single token for BUY opportunity.

        This method:
        1. Gets real market data (gas, liquidity, volatility, MEV)
        2. Creates market context
        3. Calls intelligence engine for decision
        4. Logs the decision
        5. Executes if decision is BUY

        Args:
            token_data: Token data dict (symbol, address, price)
            price_manager: RealPriceManager instance
            position_manager: PositionManager instance
            trade_executor: TradeExecutor instance
            thought_logger: Thought logging function
        """
        try:
            # Extract token info
            token_symbol = token_data.get('symbol')
            token_address = token_data.get('address')
            current_price = token_data.get('price')

            # Validate required data
            if not all([token_symbol, token_address, current_price]):
                logger.warning(
                    f"[TOKEN ANALYZER] Missing required token data. "
                    f"Symbol={token_symbol}, Address={token_address}, Price={current_price}"
                )
                return

            # Type assertions
            assert token_symbol is not None
            assert token_address is not None
            assert isinstance(current_price, Decimal)

            logger.info(
                f"[TOKEN ANALYZER] Analyzing {token_symbol} for BUY at ${current_price:.2f}"
            )

            # Get price history for trend analysis
            price_history = price_manager.get_price_history(token_symbol, limit=24)

            # Get existing positions for context (but won't include this token)
            existing_positions = position_manager.get_all_positions()

            # Calculate initial trade size
            account_balance = self.account.current_balance_usd
            max_position_size_percent = Decimal('20.0')  # Default 20% of account
            if self.strategy_config:
                max_position_size_percent = getattr(
                    self.strategy_config,
                    'max_position_size_percent',
                    Decimal('20.0')
                )

            initial_trade_size = (account_balance * max_position_size_percent) / Decimal('100')

            # Call intelligence engine to get comprehensive market analysis and decision
            # The engine will handle calling CompositeMarketAnalyzer internally
            decision = async_to_sync(self.intelligence_engine.make_decision)(
                market_context=MarketContext(
                    token_address=token_address,
                    token_symbol=token_symbol,
                    current_price=current_price
                ),
                account_balance=account_balance,
                existing_positions=list(existing_positions.values()),
                token_address=token_address,
                token_symbol=token_symbol
            )

            # VALIDATION: Ensure we only get BUY or SKIP
            if decision.action not in [DecisionType.BUY, DecisionType.SKIP]:
                logger.error(
                    f"[TOKEN ANALYZER] ⚠️  INVALID DECISION TYPE: {decision.action} "
                    f"for {token_symbol}. TokenAnalyzer should only return BUY or SKIP. "
                    "Converting to SKIP."
                )
                decision.action = DecisionType.SKIP
                decision.primary_reasoning = (
                    f"Invalid decision type {decision.action} converted to SKIP"
                )

            # Log the decision
            if thought_logger:
                thought_logger(
                    action=decision.action,
                    reasoning=decision.primary_reasoning,
                    confidence=float(decision.overall_confidence),
                    decision_type="BUY_PATH_ANALYSIS",
                    metadata={
                        'token': token_symbol,
                        'token_address': token_address,
                        'current_price': float(current_price),
                        'intel_level': int(self.intelligence_engine.intel_level),
                        'risk_score': float(decision.risk_score),
                        'opportunity_score': float(decision.opportunity_score),
                        'position_size_usd': float(decision.position_size_usd),
                        'has_position': False,  # We never analyze tokens we own
                        'analysis_path': 'BUY_PATH'
                    }
                )

            # Execute BUY if decision says so
            if decision.action == DecisionType.BUY:
                logger.info(
                    f"[TOKEN ANALYZER] 💰 BUY signal for {token_symbol} "
                    f"(Confidence: {decision.overall_confidence:.1f}%, "
                    f"Size: ${decision.position_size_usd:.2f})"
                )

                # Record buy attempt for cooldown
                from django.utils import timezone
                self.last_buy_attempts[token_symbol] = timezone.now()

                # Execute the trade
                success = trade_executor.execute_trade(
                    decision=decision,
                    token_symbol=token_symbol,
                    current_price=current_price,
                    position_manager=position_manager
                )

                if success:
                    logger.info(f"[TOKEN ANALYZER] ✅ BUY executed for {token_symbol}")
                else:
                    logger.warning(f"[TOKEN ANALYZER] ❌ BUY failed for {token_symbol}")

            else:
                logger.debug(
                    f"[TOKEN ANALYZER] Skipping {token_symbol} "
                    f"(Confidence: {decision.overall_confidence:.1f}%, "
                    f"Reason: {decision.primary_reasoning[:50]}...)"
                )

        except Exception as e:
            logger.error(
                f"[TOKEN ANALYZER] Error analyzing {token_data.get('symbol', 'UNKNOWN')}: {e}",
                exc_info=True
            )

    # =========================================================================
    # COOLDOWN MANAGEMENT
    # =========================================================================

    def _can_buy_token(self, token_symbol: str) -> bool:
        """
        Check if token is not in BUY cooldown period.

        Prevents rapid re-buying of the same token that might have
        been sold or skipped recently.

        Args:
            token_symbol: Token symbol to check

        Returns:
            True if can buy, False if in cooldown
        """
        from django.utils import timezone
        from datetime import timedelta

        if token_symbol not in self.last_buy_attempts:
            return True

        last_attempt = self.last_buy_attempts[token_symbol]
        cooldown_period = timedelta(minutes=self.buy_cooldown_minutes)
        time_since_attempt = timezone.now() - last_attempt

        return time_since_attempt > cooldown_period