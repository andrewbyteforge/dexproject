"""
Trade Executor for Paper Trading Bot

This module handles all trade execution operations for the paper trading bot,
including transaction routing (TX Manager vs Legacy), paper trade record creation,
AI thought logging, and circuit breaker validation.

PHASE 2 UPDATE: Added arbitrage integration for cross-DEX profit opportunities.

Responsibilities:
- Route trades to TX Manager or Legacy execution
- Create paper trade records in database
- Generate AI thought logs for transparency
- Validate circuit breaker status before trades
- Send WebSocket updates for real-time UI
- Track trade statistics and gas savings
- Check and execute arbitrage opportunities (Phase 2)

File: dexproject/paper_trading/bot/trade_executor.py
"""

import logging
import random
import uuid
from decimal import Decimal
from typing import Dict, Any, Optional

from django.utils import timezone
from asgiref.sync import async_to_sync

from paper_trading.models import (
    PaperTradingAccount,
    PaperTrade,
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    PaperTradingSession
)

# Import intelligence types
from paper_trading.intelligence.base import TradingDecision

# Import WebSocket service
from paper_trading.services.websocket_service import websocket_service

# Import centralized token addresses
from shared.constants import get_token_address

# Import Transaction Manager (optional)
try:
    from trading.services.transaction_manager import (
        get_transaction_manager,
        create_transaction_submission_request,
        TransactionStatus,
        TransactionSubmissionRequest,
        TransactionManagerResult
    )
    from trading.services.dex_router_service import (
        SwapType,
        DEXVersion,
        TradingGasStrategy,
        SwapParams
    )
    TRANSACTION_MANAGER_AVAILABLE = True
except ImportError:
    TRANSACTION_MANAGER_AVAILABLE = False
    # Type stubs to satisfy Pylance when Transaction Manager is not available
    get_transaction_manager = None  # type: ignore
    create_transaction_submission_request = None  # type: ignore
    TransactionStatus = None  # type: ignore
    TransactionSubmissionRequest = None  # type: ignore
    TransactionManagerResult = None  # type: ignore
    SwapType = None  # type: ignore
    DEXVersion = None  # type: ignore
    TradingGasStrategy = None  # type: ignore
    SwapParams = None  # type: ignore

# Import Circuit Breaker (optional) - availability checked via CIRCUIT_BREAKER_AVAILABLE
try:
    import engine.portfolio  # noqa: F401
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False

# PHASE 2: Import Arbitrage Components (optional)
try:
    from paper_trading.intelligence.arbitrage_detector import ArbitrageDetector
    from paper_trading.intelligence.dex_price_comparator import DEXPriceComparator
    ARBITRAGE_AVAILABLE = True
except ImportError:
    ARBITRAGE_AVAILABLE = False
    ArbitrageDetector = None  # type: ignore
    DEXPriceComparator = None  # type: ignore

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_token_address_for_trade(symbol: str, chain_id: int) -> str:
    """
    Get token address from centralized constants with proper error handling.
    
    This function ensures that trades are only created with valid addresses
    from our centralized constants, preventing the use of placeholder or
    incorrect addresses.
    
    Args:
        symbol: Token symbol (e.g., 'WETH', 'USDC')
        chain_id: Blockchain network ID
        
    Returns:
        Token contract address
        
    Raises:
        ValueError: If token not available on this chain
        
    Example:
        >>> address = _get_token_address_for_trade('WETH', 8453)
        >>> address
        '0x4200000000000000000000000000000000000006'
    """
    address = get_token_address(symbol, chain_id)
    if not address:
        raise ValueError(
            f"Token {symbol} not available on chain {chain_id}. "
            f"Check TOKEN_ADDRESSES_BY_CHAIN in shared/constants.py"
        )
    return address


# =============================================================================
# TRADE EXECUTOR CLASS
# =============================================================================

class TradeExecutor:
    """
    Handles all trade execution operations for paper trading bot.

    This class manages the complete trade execution pipeline:
    - Circuit breaker validation
    - Transaction routing (TX Manager vs Legacy)
    - Paper trade record creation
    - AI thought logging
    - WebSocket notifications
    - Gas savings tracking
    - Arbitrage opportunity detection (Phase 2)

    Example usage:
        executor = TradeExecutor(
            account=account,
            session=session,
            strategy_config=strategy_config,
            intel_level=5
        )

        # Execute a trade
        success = executor.execute_trade(
            decision=trading_decision,
            token_symbol='WETH',
            current_price=Decimal('2500')
        )
    """

    def __init__(
        self,
        account: PaperTradingAccount,
        session: PaperTradingSession,
        strategy_config: Optional[PaperStrategyConfiguration] = None,
        intel_level: int = 5,
        use_tx_manager: bool = False,
        circuit_breaker_manager: Optional[Any] = None,
        chain_id: int = 1
    ):
        """
        Initialize the Trade Executor.

        Args:
            account: Paper trading account
            session: Current trading session
            strategy_config: Strategy configuration
            intel_level: Intelligence level (1-10)
            use_tx_manager: Whether to use Transaction Manager
            circuit_breaker_manager: Circuit breaker manager instance
            chain_id: Blockchain network ID
        """
        self.account = account
        self.session = session
        self.strategy_config = strategy_config
        self.intel_level = intel_level
        self.use_tx_manager = use_tx_manager and TRANSACTION_MANAGER_AVAILABLE
        self.circuit_breaker_manager = circuit_breaker_manager
        self.chain_id = chain_id

        # Transaction Manager instance (initialized lazily)
        self.tx_manager = None

        # Performance tracking
        self.total_gas_savings = Decimal('0')
        self.trades_with_tx_manager = 0
        self.pending_transactions: Dict[str, Dict[str, Any]] = {}

        # Trade statistics
        self.consecutive_failures = 0
        self.daily_trades_count = 0
        self.last_trade_date = None

        # PHASE 2: Arbitrage components (initialized lazily)
        self.arbitrage_detector = None
        self.dex_price_comparator = None
        self.arbitrage_opportunities_found = 0
        self.arbitrage_opportunities_executed = 0

        logger.info(
            f"[TRADE EXECUTOR] Initialized: "
            f"Account={account.account_id}, "
            f"TX Manager={'ENABLED' if self.use_tx_manager else 'DISABLED'}, "
            f"Circuit Breaker={'ENABLED' if circuit_breaker_manager else 'DISABLED'}, "
            f"Arbitrage={'ENABLED' if ARBITRAGE_AVAILABLE else 'DISABLED'}"
        )

    # =========================================================================
    # MAIN TRADE EXECUTION
    # =========================================================================

    def execute_trade(
        self,
        decision: TradingDecision,
        token_symbol: str,
        current_price: Decimal,
        position_manager: Any  # Avoid circular import
    ) -> bool:
        """
        Execute a paper trade with circuit breaker and Transaction Manager integration.

        Args:
            decision: Trading decision from intelligence engine
            token_symbol: Token to trade
            current_price: Current token price
            position_manager: PositionManager instance for position updates

        Returns:
            True if trade was successful, False otherwise
        """
        try:
            # Validate circuit breaker allows trading
            if not self._can_trade(trade_type=decision.action):
                logger.warning(
                    f"[TRADE EXECUTOR] Trade blocked by circuit breaker: "
                    f"{decision.action} {token_symbol}"
                )
                self.consecutive_failures += 1
                return False

            # Increment daily trade count
            self.daily_trades_count += 1

            # Route to TX Manager or Legacy
            if self.use_tx_manager:
                success = self._execute_trade_with_tx_manager(
                    decision=decision,
                    token_symbol=token_symbol,
                    current_price=current_price,
                    position_manager=position_manager
                )
            else:
                success = self._execute_trade_legacy(
                    decision=decision,
                    token_symbol=token_symbol,
                    current_price=current_price,
                    position_manager=position_manager
                )

            # Update failure tracking
            if success:
                self.consecutive_failures = 0
            else:
                self.consecutive_failures += 1

            return success

        except Exception as e:
            logger.error(
                f"[TRADE EXECUTOR] Trade execution failed: {e}",
                exc_info=True
            )
            self.consecutive_failures += 1
            return False

    # =========================================================================
    # TX MANAGER EXECUTION PATH
    # =========================================================================

    def _execute_trade_with_tx_manager(
        self,
        decision: TradingDecision,
        token_symbol: str,
        current_price: Decimal,
        position_manager: Any
    ) -> bool:
        """
        Execute trade using Transaction Manager for gas optimization.

        Args:
            decision: Trading decision
            token_symbol: Token to trade
            current_price: Current price
            position_manager: PositionManager instance

        Returns:
            True if trade was successful, False otherwise
        """
        try:
            logger.info(
                f"[TX MANAGER] Executing {decision.action} trade: "
                f"{token_symbol} @ ${current_price:.2f}"
            )

            # Create trade record
            trade = self._create_paper_trade_record(
                decision=decision,
                token_symbol=token_symbol,
                current_price=current_price
            )

            if not trade:
                return False

            # Update positions
            self._update_positions_after_trade(
                decision=decision,
                token_symbol=token_symbol,
                current_price=current_price,
                position_manager=position_manager
            )

            # Track gas savings (paper trading simulation)
            estimated_gas_savings = Decimal('0.231')  # 23.1% average savings
            self.total_gas_savings += estimated_gas_savings
            self.trades_with_tx_manager += 1

            logger.info(
                f"[TX MANAGER] Trade successful: "
                f"Gas savings={estimated_gas_savings:.1%}, "
                f"Total savings={self.total_gas_savings:.1%}"
            )

            # PHASE 2: Check for arbitrage opportunities after BUY
            if decision.action == 'BUY' and ARBITRAGE_AVAILABLE:
                self._check_arbitrage_after_buy(
                    token_address=decision.token_address,
                    token_symbol=token_symbol,
                    our_buy_price=current_price,
                    trade_amount_usd=decision.position_size_usd
                )

            return True

        except Exception as e:
            logger.error(
                f"[TX MANAGER] Trade execution failed: {e}",
                exc_info=True
            )
            return False

    # =========================================================================
    # LEGACY EXECUTION PATH
    # =========================================================================

    def _execute_trade_legacy(
        self,
        decision: TradingDecision,
        token_symbol: str,
        current_price: Decimal,
        position_manager: Any
    ) -> bool:
        """
        Execute trade using legacy path (without Transaction Manager).

        Args:
            decision: Trading decision
            token_symbol: Token to trade
            current_price: Current price
            position_manager: PositionManager instance

        Returns:
            True if trade was successful, False otherwise
        """
        try:
            logger.info(
                f"[LEGACY] Executing {decision.action} trade: "
                f"{token_symbol} @ ${current_price:.2f}"
            )

            # Create trade record
            trade = self._create_paper_trade_record(
                decision=decision,
                token_symbol=token_symbol,
                current_price=current_price
            )

            if not trade:
                return False

            # Update positions
            self._update_positions_after_trade(
                decision=decision,
                token_symbol=token_symbol,
                current_price=current_price,
                position_manager=position_manager
            )

            logger.info(f"[LEGACY] Trade successful: {decision.action} {token_symbol}")

            # PHASE 2: Check for arbitrage opportunities after BUY
            if decision.action == 'BUY' and ARBITRAGE_AVAILABLE:
                self._check_arbitrage_after_buy(
                    token_address=decision.token_address,
                    token_symbol=token_symbol,
                    our_buy_price=current_price,
                    trade_amount_usd=decision.position_size_usd
                )

            return True

        except Exception as e:
            logger.error(
                f"[LEGACY] Trade execution failed: {e}",
                exc_info=True
            )
            return False

    # =========================================================================
    # PHASE 2: ARBITRAGE INTEGRATION
    # =========================================================================

    def _check_arbitrage_after_buy(
        self,
        token_address: str,
        token_symbol: str,
        our_buy_price: Decimal,
        trade_amount_usd: Decimal
    ) -> None:
        """
        Check for arbitrage opportunities after executing a BUY trade.

        PHASE 2: After buying on one DEX, check if we can immediately sell
        at a higher price on another DEX for instant profit.

        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            our_buy_price: Price we just bought at
            trade_amount_usd: Amount we just bought (USD)
        """
        try:
            # Skip if arbitrage components not available
            if not ARBITRAGE_AVAILABLE:
                return

            # Initialize arbitrage components lazily
            if not self.arbitrage_detector:
                self.arbitrage_detector = ArbitrageDetector()
                logger.info("[ARBITRAGE] Detector initialized")

            if not self.dex_price_comparator:
                self.dex_price_comparator = DEXPriceComparator(chain_id=self.chain_id)
                logger.info("[ARBITRAGE] Price comparator initialized")

            # Get current prices from multiple DEXs using compare_prices()
            logger.debug(f"[ARBITRAGE] Checking prices for {token_symbol}")
            
            price_comparison = async_to_sync(self.dex_price_comparator.compare_prices)(
                token_address=token_address,
                token_symbol=token_symbol,
                use_cache=False  # Don't use cache for arbitrage checks
            )

            if not price_comparison or price_comparison.successful_queries < 2:
                logger.debug("[ARBITRAGE] Insufficient DEX price data")
                return

            # ⚠️ CRITICAL: Validate prices to filter out testnet bad data
            # Filter out prices that are clearly invalid (zero or near-zero)
            MIN_VALID_PRICE = Decimal('0.01')  # Minimum $0.01
            MAX_VALID_PRICE = Decimal('100000')  # Maximum $100k per token
            
            valid_prices = [
                p for p in price_comparison.prices
                if p.success and p.price_usd and 
                MIN_VALID_PRICE <= p.price_usd <= MAX_VALID_PRICE
            ]
            
            if len(valid_prices) < 2:
                logger.debug(
                    f"[ARBITRAGE] Insufficient valid prices for {token_symbol} "
                    f"(got {len(valid_prices)}, need 2+)"
                )
                return
            
            # Recreate price comparison with only valid prices
            price_comparison.prices = valid_prices
            price_comparison.__post_init__()  # Recalculate best/worst

            # Detect arbitrage opportunity using detect_arbitrage()
            opportunity = self.arbitrage_detector.detect_arbitrage(
                price_comparison=price_comparison,
                trade_amount_usd=trade_amount_usd
            )

            if opportunity and opportunity.is_profitable:
                self.arbitrage_opportunities_found += 1
                
                # ⚠️ CRITICAL: Cap maximum arbitrage profit to prevent runaway growth
                MAX_ARBITRAGE_PROFIT = Decimal('1000')  # Maximum $1000 profit per trade
                
                if opportunity.net_profit_usd > MAX_ARBITRAGE_PROFIT:
                    logger.warning(
                        f"[ARBITRAGE] Profit capped: ${opportunity.net_profit_usd:.2f} → "
                        f"${MAX_ARBITRAGE_PROFIT:.2f} (likely bad data from testnet)"
                    )
                    opportunity.net_profit_usd = MAX_ARBITRAGE_PROFIT
                    opportunity.profit_margin_percent = (
                        (opportunity.net_profit_usd / opportunity.trade_amount_usd) * Decimal('100')
                    )
                
                logger.info(
                    f"[ARBITRAGE] 🎯 Opportunity found! "
                    f"Buy {opportunity.buy_dex} @ ${opportunity.buy_price:.4f}, "
                    f"Sell {opportunity.sell_dex} @ ${opportunity.sell_price:.4f}, "
                    f"Profit: ${opportunity.net_profit_usd:.2f} "
                    f"({opportunity.profit_margin_percent:.2f}%)"
                )

                # Check if arbitrage meets minimum profit threshold
                min_profit_usd = Decimal('5.00')  # Minimum $5 profit
                if opportunity.net_profit_usd >= min_profit_usd:
                    # Execute arbitrage trade (in paper trading, just log it)
                    self._execute_arbitrage_trade(opportunity)
                else:
                    logger.debug(
                        f"[ARBITRAGE] Profit too small: "
                        f"${opportunity.net_profit_usd:.2f} < ${min_profit_usd:.2f}"
                    )
            else:
                logger.debug(f"[ARBITRAGE] No profitable opportunity for {token_symbol}")

        except Exception as e:
            logger.error(f"[ARBITRAGE] Error checking arbitrage: {e}", exc_info=True)

    def _execute_arbitrage_trade(self, opportunity: Any) -> None:
        """
        Execute an arbitrage trade opportunity.

        PHASE 2: In paper trading, this creates a virtual sell trade
        at the higher DEX price to capture the arbitrage profit.

        Args:
            opportunity: ArbitrageOpportunity object with trade details
        """
        try:
            logger.info(
                f"[ARBITRAGE] 💰 Executing arbitrage: "
                f"Selling on {opportunity.sell_dex} for "
                f"${opportunity.net_profit_usd:.2f} profit"
            )

            # In paper trading, update account balance with profit
            self.account.current_balance_usd += opportunity.net_profit_usd
            self.account.save(update_fields=['current_balance_usd'])

            # Track arbitrage statistics
            self.arbitrage_opportunities_executed += 1

            # Log the arbitrage trade as a separate trade record
            try:
                # Calculate amounts in wei
                token_decimals = Decimal('1000000000000000000')  # 1e18
                usdc_decimals = Decimal('1000000')  # 1e6

                # Convert to string FIRST to avoid scientific notation
                amount_in_wei_str = str(int(
                    (opportunity.trade_amount_usd / opportunity.sell_price) * token_decimals
                ))
                amount_out_wei_str = str(int(
                    (opportunity.trade_amount_usd + opportunity.net_profit_usd) * usdc_decimals
                ))
                
                # Simulate gas costs for arbitrage
                simulated_gas_used = random.randint(300000, 400000)  # Higher for arb
                simulated_gas_price_gwei = Decimal('1.0')
                
                arbitrage_trade = PaperTrade.objects.create(
                    account=self.account,
                    trade_type='sell',  # Arbitrage is a sell on different DEX
                    token_in_symbol=opportunity.token_symbol,
                    token_in_address=opportunity.token_address,
                    token_out_symbol='USDC',
                    token_out_address=get_token_address('USDC', self.chain_id),
                    amount_in=Decimal(amount_in_wei_str),
                    amount_in_usd=opportunity.trade_amount_usd,
                    expected_amount_out=Decimal(amount_out_wei_str),
                    actual_amount_out=Decimal(amount_out_wei_str),
                    simulated_gas_used=simulated_gas_used,
                    simulated_gas_price_gwei=simulated_gas_price_gwei,
                    simulated_gas_cost_usd=Decimal('0.10'),  # Minimal gas on Base
                    simulated_slippage_percent=Decimal('0.3'),
                    status='completed',
                    strategy_name='Arbitrage',
                    metadata={
                        'arbitrage': True,
                        'buy_dex': opportunity.buy_dex,
                        'sell_dex': opportunity.sell_dex,
                        'buy_price': float(opportunity.buy_price),
                        'sell_price': float(opportunity.sell_price),
                        'price_spread_percent': float(opportunity.price_spread_percent),
                        'net_profit_usd': float(opportunity.net_profit_usd),
                        'session_id': str(self.session.session_id) if self.session else None
                    }
                )

                logger.info(
                    f"[ARBITRAGE] ✅ Arbitrage trade created: "
                    f"ID={arbitrage_trade.trade_id}, "
                    f"Profit=${opportunity.net_profit_usd:.2f}"
                )

            except Exception as e:
                logger.error(f"[ARBITRAGE] Failed to create trade record: {e}")

            logger.info(
                f"[ARBITRAGE] Total: Found={self.arbitrage_opportunities_found}, "
                f"Executed={self.arbitrage_opportunities_executed}"
            )

        except Exception as e:
            logger.error(f"[ARBITRAGE] Failed to execute arbitrage: {e}", exc_info=True)

    # =========================================================================
    # TRADE RECORD CREATION
    # =========================================================================

    def _create_paper_trade_record(
        self,
        decision: TradingDecision,
        token_symbol: str,
        current_price: Decimal
    ) -> Optional[PaperTrade]:
        """
        Create a paper trade record in the database.

        Args:
            decision: Trading decision
            token_symbol: Token being traded
            current_price: Current token price

        Returns:
            PaperTrade: Created trade record or None if failed
        """
        try:
            # Determine trade type
            trade_type = decision.action.lower()

            # Get token addresses
            if trade_type == 'buy':
                token_in_symbol = 'USDC'
                token_in_address = _get_token_address_for_trade('USDC', self.chain_id)
                token_out_symbol = token_symbol
                token_out_address = decision.token_address
                amount_in_usd = decision.position_size_usd
            elif trade_type == 'sell':
                token_in_symbol = token_symbol
                token_in_address = decision.token_address
                token_out_symbol = 'USDC'
                token_out_address = _get_token_address_for_trade('USDC', self.chain_id)
                amount_in_usd = decision.position_size_usd
            else:
                logger.error(f"[TRADE EXECUTOR] Unsupported action: {decision.action}")
                return None

            # Simulate gas costs (realistic estimates)
            simulated_gas_used = random.randint(150000, 250000)
            simulated_gas_price_gwei = Decimal(str(random.uniform(15, 45)))
            
            # Calculate gas cost in USD (simplified)
            eth_price = Decimal('2500')  # Approximate ETH price
            gas_cost_eth = (Decimal(simulated_gas_used) * simulated_gas_price_gwei) / Decimal('1e9')
            simulated_gas_cost_usd = gas_cost_eth * eth_price

            # Calculate amounts in wei (for model fields)
            # CRITICAL FIX: Use proper decimals per token to avoid scientific notation
            # USDC uses 6 decimals, most other tokens use 18 decimals
            usdc_decimals = Decimal('1000000')  # 1e6 for USDC
            token_decimals = Decimal('1000000000000000000')  # 1e18 for most tokens
            
            if trade_type == 'buy':
                # Buying: spending USDC (6 decimals), receiving token (18 decimals)
                # Convert to string FIRST to avoid scientific notation, then to Decimal
                amount_in_wei_str = str(int(amount_in_usd * usdc_decimals))
                expected_amount_out_wei_str = str(int((amount_in_usd / current_price) * token_decimals))
            else:  # sell
                # Selling: spending token (18 decimals), receiving USDC (6 decimals)
                amount_in_wei_str = str(int((amount_in_usd / current_price) * token_decimals))
                expected_amount_out_wei_str = str(int(amount_in_usd * usdc_decimals))

            # Create trade record with CORRECT field names
            trade = PaperTrade.objects.create(
                account=self.account,
                trade_type=trade_type,
                token_in_symbol=token_in_symbol,
                token_in_address=token_in_address,
                token_out_symbol=token_out_symbol,
                token_out_address=token_out_address,
                amount_in=Decimal(amount_in_wei_str),
                amount_in_usd=amount_in_usd,
                expected_amount_out=Decimal(expected_amount_out_wei_str),
                actual_amount_out=Decimal(expected_amount_out_wei_str),
                simulated_gas_used=simulated_gas_used,
                simulated_gas_price_gwei=simulated_gas_price_gwei,
                simulated_gas_cost_usd=simulated_gas_cost_usd,
                simulated_slippage_percent=Decimal('0.5'),
                status='completed',
                strategy_name=self.strategy_config.name if self.strategy_config else 'Default',
                metadata={
                    'price_at_execution': float(current_price),
                    'session_id': str(self.session.session_id) if self.session else None,
                    'intel_level': self.intel_level,
                    'confidence': float(getattr(decision, 'overall_confidence', 0)),
                    'risk_score': float(getattr(decision, 'risk_score', 0)),
                    'opportunity_score': float(getattr(decision, 'opportunity_score', 0))
                }
            )

            logger.info(
                f"[PAPER TRADE] Created: {trade_type.upper()} {token_out_symbol}, "
                f"Amount=${amount_in_usd:.2f}, Price=${current_price:.4f}"
            )
           
            # Update account balance
            if trade_type == 'buy':
                self.account.current_balance_usd -= amount_in_usd
            elif trade_type == 'sell':
                self.account.current_balance_usd += amount_in_usd  # ← FIXED! Use amount_in_usd

            # Update account statistics
            self.account.total_trades += 1
            if trade.status == 'completed':
                self.account.winning_trades += 1
            elif trade.status == 'failed':
                self.account.losing_trades += 1

            self.account.save(update_fields=[
                'total_trades',
                'winning_trades',
                'losing_trades',
                'current_balance_usd'
            ])

            logger.debug(
                f"[ACCOUNT STATS] Updated: Total={self.account.total_trades}, "
                f"Winning={self.account.winning_trades}, "
                f"Losing={self.account.losing_trades}, "
                f"Balance=${self.account.current_balance_usd:.2f}"
            )

            # Create AI thought log for this trade
            self._create_ai_thought_log(
                paper_trade=trade,
                decision=decision,
                token_symbol=token_symbol,
                token_address=token_out_address if trade_type == 'buy' else token_in_address
            )

            # Send WebSocket update
            try:
                trade_data = {
                    'trade_id': str(trade.trade_id),
                    'trade_type': trade_type,
                    'token_in_symbol': token_in_symbol,
                    'token_out_symbol': token_out_symbol,
                    'amount_in_usd': float(amount_in_usd),
                    'status': 'completed',
                    'created_at': trade.created_at.isoformat()
                }
                websocket_service.send_trade_update(
                    account_id=str(self.account.account_id),
                    trade_data=trade_data
                )
            except Exception as e:
                logger.error(f"Failed to send WebSocket update: {e}")

            return trade

        except Exception as e:
            logger.error(
                f"[TRADE EXECUTOR] Failed to create trade record: {e}",
                exc_info=True
            )
            return None

    def _create_ai_thought_log(
        self,
        paper_trade: PaperTrade,
        decision: TradingDecision,
        token_symbol: str,
        token_address: str
    ) -> Optional[PaperAIThoughtLog]:
        """
        Create AI thought log for the trade.

        Args:
            paper_trade: The paper trade record
            decision: Trading decision that was made
            token_symbol: Token symbol
            token_address: Token address

        Returns:
            PaperAIThoughtLog: Created thought log or None if failed
        """
        try:
            # Get confidence for logging
            confidence = float(getattr(decision, 'overall_confidence', 75))

            # Create thought log
            from paper_trading.factories import create_thought_log_from_decision

            thought_log = create_thought_log_from_decision(
                account=self.account,
                decision=decision,
                token_symbol=token_symbol,
                token_address=token_address,
                paper_trade=paper_trade,
                strategy_name=self.strategy_config.name if self.strategy_config else '',
                lane_used='FAST',
            )

            logger.info(
                f"[AI THOUGHT] Created thought log: confidence={confidence:.1f}%, "
                f"risk={getattr(decision, 'risk_score', 50):.1f}, "
                f"decision={decision.action}"
            )

            return thought_log

        except Exception as e:
            logger.error(
                f"[TRADE EXECUTOR] Failed to create AI thought log: {e}",
                exc_info=True
            )
            return None

    # =========================================================================
    # POSITION UPDATES
    # =========================================================================

    def _update_positions_after_trade(
        self,
        decision: TradingDecision,
        token_symbol: str,
        current_price: Decimal,
        position_manager: Any
    ):
        """
        Update positions after trade execution.

        Args:
            decision: Trading decision
            token_symbol: Token traded
            current_price: Current price
            position_manager: PositionManager instance
        """
        if decision.action == 'BUY':
            position_manager.open_or_add_position(
                token_symbol=token_symbol,
                token_address=decision.token_address,
                position_size_usd=decision.position_size_usd,
                current_price=current_price
            )
        elif decision.action == 'SELL':
            position_manager.close_or_reduce_position(
                token_symbol=token_symbol,
                sell_amount_usd=decision.position_size_usd,
                current_price=current_price
            )

    # =========================================================================
    # CIRCUIT BREAKER CHECKS
    # =========================================================================

    def _can_trade(self, trade_type: str = 'BUY') -> bool:
        """
        Check if bot can execute a trade based on circuit breakers and limits.

        Args:
            trade_type: Type of trade (BUY, SELL, ARBITRAGE)

        Returns:
            True if trading is allowed, False otherwise
        """
        try:
            # Check if circuit breaker is enabled
            if not self.circuit_breaker_manager:
                return True

            # Check portfolio circuit breakers
            can_trade, reasons = self.circuit_breaker_manager.can_trade()
            if not can_trade:
                logger.warning(
                    f"[CB] Trading blocked by circuit breaker: {', '.join(reasons)}"
                )
                return False

            # Check daily trade limit
            current_date = timezone.now().date()
            if self.last_trade_date != current_date:
                self.daily_trades_count = 0
                self.last_trade_date = current_date

            max_daily_trades = 20
            if self.strategy_config:
                max_daily_trades = getattr(
                    self.strategy_config,
                    'max_daily_trades',
                    20
                )

            if self.daily_trades_count >= max_daily_trades:
                logger.warning(
                    f"[CB] Daily trade limit reached: "
                    f"{self.daily_trades_count}/{max_daily_trades}"
                )
                return False

            # Check consecutive failures
            max_consecutive_failures = 5
            if self.consecutive_failures >= max_consecutive_failures:
                logger.warning(
                    f"[CB] Too many consecutive failures: "
                    f"{self.consecutive_failures}"
                )
                return False

            # Check account balance minimum
            min_balance = Decimal('100')  # Minimum $100 to trade
            if trade_type in ['BUY', 'LONG']:
                if self.account.current_balance_usd < min_balance:
                    logger.warning("[CB] Insufficient balance for BUY")
                    return False
            elif trade_type == 'ARBITRAGE':
                # PHASE 2: For arbitrage, we need enough balance for potential rebalancing
                if self.account.current_balance_usd < Decimal('50'):
                    logger.warning("[CB] Insufficient balance for ARBITRAGE")
                    return False
            else:
                logger.debug(f"[CB] Balance check skipped for {trade_type}")

            return True

        except Exception as e:
            logger.error(f"[CB] Error checking trade permission: {e}")
            return True  # Fail open if circuit breaker check fails

    def _get_portfolio_state(self, position_manager: Any) -> Dict[str, Any]:
        """
        Get current portfolio state for circuit breaker checks.

        Note: starting_balance_usd was moved to session.metadata in migration 0005
        """
        try:
            # Get starting balance from metadata (migration 0005 change)
            starting_balance = self.session.metadata.get(
                'starting_balance_usd',
                float(self.account.initial_balance_usd)
            )

            return {
                'account_id': str(self.account.account_id),
                'current_balance': self.account.current_balance_usd,
                'starting_balance': Decimal(str(starting_balance)),
                'total_value': position_manager.get_total_value(),
                'position_count': position_manager.get_position_count(),
                'open_positions': position_manager.positions,
            }
        except Exception as e:
            logger.error(f"[CB] Error getting portfolio state: {e}")
            return {}