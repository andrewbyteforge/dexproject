"""
Trade Executor for Paper Trading Bot

This module handles all trade execution operations for the paper trading bot,
including transaction routing (TX Manager vs Legacy), paper trade record creation,
AI thought logging, and circuit breaker validation.

Responsibilities:
- Route trades to TX Manager or Legacy execution
- Create paper trade records in database
- Generate AI thought logs for transparency
- Validate circuit breaker status before trades
- Send WebSocket updates for real-time UI
- Track trade statistics and gas savings

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

        logger.info(
            f"[TRADE EXECUTOR] Initialized: "
            f"Account={account.account_id}, "
            f"TX Manager={'ENABLED' if self.use_tx_manager else 'DISABLED'}, "
            f"Circuit Breaker={'ENABLED' if circuit_breaker_manager else 'DISABLED'}"
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
            # Check circuit breakers before executing
            if not self._can_trade(trade_type=decision.action):
                logger.info(
                    f"[TRADE] Trade blocked for {token_symbol} - "
                    f"circuit breaker active"
                )
                return False

            # Check portfolio state for circuit breaker updates
            if self.circuit_breaker_manager:
                portfolio_state = self._get_portfolio_state(position_manager)
                new_breakers = self.circuit_breaker_manager.check_circuit_breakers(
                    portfolio_state
                )

                if new_breakers:
                    for breaker in new_breakers:
                        logger.warning(
                            f"[CB] New circuit breaker triggered: "
                            f"{breaker.breaker_type.value}"
                        )
                        logger.warning(f"[CB] Reason: {breaker.description}")

                    # Stop trading if new breakers triggered
                    return False

            # Execute trade
            trade_success = False

            # Use Transaction Manager if enabled
            if self.use_tx_manager and self.tx_manager:
                trade_success = self._execute_trade_with_tx_manager(
                    decision,
                    token_symbol,
                    current_price,
                    position_manager
                )
            else:
                trade_success = self._execute_trade_legacy(
                    decision,
                    token_symbol,
                    current_price,
                    position_manager
                )

            # Update failure tracking
            if trade_success:
                self.consecutive_failures = 0
                self.daily_trades_count += 1
                logger.info(
                    f"[TRADE] Successfully executed {decision.action} "
                    f"for {token_symbol}"
                )
            else:
                self.consecutive_failures += 1
                logger.warning(
                    f"[TRADE] Failed to execute {decision.action} "
                    f"for {token_symbol} "
                    f"(Consecutive failures: {self.consecutive_failures})"
                )

                # Check if circuit breakers should trigger after failure
                if self.circuit_breaker_manager:
                    portfolio_state = self._get_portfolio_state(position_manager)
                    self.circuit_breaker_manager.check_circuit_breakers(
                        portfolio_state
                    )

            return trade_success

        except Exception as e:
            logger.error(
                f"[TRADE EXECUTOR] {decision.action} execution failed: {e}",
                exc_info=True
            )
            self.consecutive_failures += 1
            return False

    # =========================================================================
    # TRANSACTION MANAGER EXECUTION
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

        IMPORTANT:
            Transaction Manager requires real blockchain wallets and is not
            compatible with paper trading mode. This method will automatically
            fall back to legacy mode for paper trading.

        Args:
            decision: Trading decision from intelligence engine
            token_symbol: Token to trade
            current_price: Current token price
            position_manager: PositionManager instance

        Returns:
            True if trade was successful, False otherwise
        """
        try:
            logger.info(
                f"[TX MANAGER] Executing {decision.action} via Transaction Manager"
            )

            # ✅ PAPER TRADING COMPATIBILITY CHECK
            if not hasattr(self.account.user, "wallet") or self.account.user.wallet is None:  # type: ignore[attr-defined]
                logger.warning(
                    "[TX MANAGER] Paper trading mode detected - Transaction Manager "
                    "requires a real wallet. Falling back to legacy mode."
                )
                return self._execute_trade_legacy(
                    decision,
                    token_symbol,
                    current_price,
                    position_manager
                )

            async def execute_with_tx_manager() -> bool:
                """Async wrapper to handle transaction submission."""
                try:
                    # Determine swap parameters
                    if decision.action == "BUY":
                        token_in = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"  # USDC
                        token_out = decision.token_address
                    else:  # SELL
                        token_in = decision.token_address
                        token_out = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"  # USDC

                    # Guard against missing SwapType
                    if not TRANSACTION_MANAGER_AVAILABLE or SwapType is None:
                        logger.error("[TX MANAGER] SwapType not available, cannot execute trade")
                        return False

                    swap_type = SwapType.EXACT_TOKENS_FOR_TOKENS

                    # Calculate amounts (in wei)
                    amount_in = int(decision.position_size_usd * 10**6)  # USDC = 6 decimals
                    amount_out_min = int(amount_in * 0.99)  # 1% slippage tolerance

                    # Gas strategy selection
                    if self.intel_level <= 3:
                        gas_strategy = TradingGasStrategy.COST_EFFICIENT  # type: ignore[possibly-unbound]
                    elif self.intel_level >= 7:
                        gas_strategy = TradingGasStrategy.AGGRESSIVE  # type: ignore[possibly-unbound]
                    else:
                        gas_strategy = TradingGasStrategy.BALANCED  # type: ignore[possibly-unbound]

                    logger.debug(
                        f"[TX MANAGER] Preparing TX: {decision.action} {token_symbol}, "
                        f"Amount: ${decision.position_size_usd:.2f}, "
                        f"Gas: {gas_strategy.value}"
                    )

                    # Create transaction request
                    tx_request = await create_transaction_submission_request(  # type: ignore[possibly-unbound]
                        user=self.account.user,  # type: ignore[attr-defined]
                        chain_id=self.chain_id,
                        token_in=token_in,
                        token_out=token_out,
                        amount_in=amount_in,
                        amount_out_minimum=amount_out_min,
                        swap_type=swap_type,
                        gas_strategy=gas_strategy,
                        is_paper_trade=True,
                        slippage_tolerance=Decimal("0.01"),
                    )

                    logger.info("[TX MANAGER] Submitting transaction...")

                    # Submit via Transaction Manager
                    # Type guard for tx_manager
                    # Runtime check: ensure tx_manager is available and has submit_transaction
                    if self.tx_manager is None:
                        logger.error("[TX MANAGER] Transaction manager is None")
                        return False

                    if not hasattr(self.tx_manager, 'submit_transaction'):
                        logger.error("[TX MANAGER] Transaction manager missing submit_transaction method")
                        return False

                    result = await self.tx_manager.submit_transaction(tx_request)  # type: ignore[misc]

                    if not result.success:
                        logger.error(
                            f"[TX MANAGER] Transaction failed: "
                            f"{result.error_message or 'Unknown error'}"
                        )
                        return False

                    # Circuit breaker check
                    if result.circuit_breaker_triggered:
                        logger.warning(
                            f"[CB] Trade blocked: "
                            f"{', '.join(result.circuit_breaker_reasons or ['Unknown'])}"
                        )
                        return False

                    logger.info(
                        f"[TX MANAGER] Transaction submitted successfully: "
                        f"{result.transaction_id}"
                    )

                    # Track pending transaction
                    self.pending_transactions[result.transaction_id] = {
                        "token_symbol": token_symbol,
                        "action": decision.action,
                        "amount": decision.position_size_usd,
                        "submitted_at": timezone.now(),
                    }

                    # Update gas savings tracking
                    if result.gas_savings_achieved:
                        self.total_gas_savings += result.gas_savings_achieved
                        self.trades_with_tx_manager += 1
                        avg_savings = (
                            self.total_gas_savings / self.trades_with_tx_manager
                        )
                        logger.info(
                            f"[TX MANAGER] Gas saved: {result.gas_savings_achieved:.2f}% "
                            f"(Average: {avg_savings:.2f}%)"
                        )

                    # Create paper trade record
                    trade = self._create_paper_trade_record(
                        decision,
                        token_symbol,
                        current_price,
                        transaction_id=result.transaction_id,
                        gas_savings=result.gas_savings_achieved,
                    )

                    if not trade:
                        logger.error(
                            "[TX MANAGER] Failed to create paper trade record"
                        )
                        return False

                    # Update positions
                    self._update_positions_after_trade(
                        decision,
                        token_symbol,
                        current_price,
                        position_manager
                    )

                    logger.info(
                        f"[TX MANAGER] Trade completed successfully: "
                        f"{decision.action} {token_symbol} "
                        f"${decision.position_size_usd:.2f}"
                    )
                    return True

                except Exception as e:
                    logger.error(
                        f"[TX MANAGER] Error during transaction execution: {e}",
                        exc_info=True,
                    )
                    return False

            # Execute async function synchronously
            return async_to_sync(execute_with_tx_manager)()

        except Exception as e:
            logger.error(
                f"[TX MANAGER] Fatal error in _execute_trade_with_tx_manager: {e}",
                exc_info=True,
            )

            # ✅ FALLBACK: Legacy mode on any fatal error
            logger.warning("[TX MANAGER] Falling back to legacy mode due to error")
            return self._execute_trade_legacy(
                decision,
                token_symbol,
                current_price,
                position_manager
            )

    # =========================================================================
    # LEGACY EXECUTION
    # =========================================================================

    def _execute_trade_legacy(
        self,
        decision: TradingDecision,
        token_symbol: str,
        current_price: Decimal,
        position_manager: Any
    ) -> bool:
        """
        Legacy trade execution without Transaction Manager.

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
                f"[LEGACY] Executing {decision.action} without Transaction Manager"
            )

            # Create paper trade record
            trade = self._create_paper_trade_record(
                decision,
                token_symbol,
                current_price
            )

            if not trade:
                return False

            # Update positions
            self._update_positions_after_trade(
                decision,
                token_symbol,
                current_price,
                position_manager
            )

            logger.info(
                f"[TRADE] Executed {decision.action} for {token_symbol}: "
                f"${decision.position_size_usd:.2f}"
            )
            return True

        except Exception as e:
            logger.error(f"[LEGACY] Trade execution failed: {e}", exc_info=True)
            return False

    # =========================================================================
    # PAPER TRADE RECORD CREATION
    # =========================================================================

    def _create_paper_trade_record(
        self,
        decision: TradingDecision,
        token_symbol: str,
        current_price: Decimal,
        transaction_id: Optional[str] = None,
        gas_savings: Optional[Decimal] = None
    ) -> Optional[PaperTrade]:
        """
        Create paper trade record in database with proper lowercase status values.

        This method creates and saves PaperTrade records that will appear in the dashboard.
        Updates account statistics including successful/failed trade counts.

        Args:
            decision: Trading decision from intelligence engine
            token_symbol: Symbol of token being traded
            current_price: Current price of the token
            transaction_id: Optional transaction ID from TX Manager
            gas_savings: Optional gas savings percentage from TX Manager

        Returns:
            PaperTrade: Created trade record or None if failed
        """
        try:
            # Map decision action to trade type (lowercase)
            trade_type_map = {
                'BUY': 'buy',
                'SELL': 'sell',
                'HOLD': None,  # Don't create trade for HOLD
            }

            trade_type = trade_type_map.get(decision.action)
            if not trade_type:
                logger.info("[TRADE] No trade created for HOLD action")
                return None

            # Token addresses mapping
            # Get token addresses from centralized constants (shared/constants.py)
            # This ensures we use the correct addresses for the current chain_id
            # We use error handling to prevent trades with invalid addresses
            try:
                if trade_type == 'buy':
                    # BUY: USDC -> Token
                    token_in_symbol = 'USDC'
                    token_in_address = _get_token_address_for_trade('USDC', self.chain_id)
                    token_out_symbol = token_symbol
                    token_out_address = _get_token_address_for_trade(token_symbol, self.chain_id)
                else:
                    # SELL: Token -> USDC
                    token_in_symbol = token_symbol
                    token_in_address = _get_token_address_for_trade(token_symbol, self.chain_id)
                    token_out_symbol = 'USDC'
                    token_out_address = _get_token_address_for_trade('USDC', self.chain_id)
            except ValueError as e:
                logger.error(
                    f"[TRADE] Cannot create trade for {token_symbol}: {e}"
                )
                return None

            # Calculate amounts
            amount_in_usd = decision.position_size_usd

            # Simulate slippage
            base_slippage = Decimal('0.5')
            volatility_slippage = Decimal(str(random.uniform(0, 1.5)))
            total_slippage = base_slippage + volatility_slippage

            # Calculate expected output
            if trade_type == 'buy':
                # Buying token with USDC
                token_quantity = amount_in_usd / current_price
                expected_amount_out = token_quantity * (
                    Decimal('1') - total_slippage / Decimal('100')
                )
                actual_amount_out = expected_amount_out  # For paper trading, actual equals expected
            else:
                # Selling token for USDC
                token_quantity = amount_in_usd / current_price
                expected_amount_out = amount_in_usd * (
                    Decimal('1') - total_slippage / Decimal('100')
                )
                actual_amount_out = expected_amount_out

            # Simulate gas costs
            gas_price_gwei = Decimal(str(random.uniform(20, 40)))
            gas_used = random.randint(120000, 200000)
            gas_cost_eth = (gas_price_gwei * gas_used) / Decimal('1e9')
            gas_cost_usd = gas_cost_eth * Decimal('3000')  # Assume ETH = $3000

            # Apply gas savings if using TX Manager
            if gas_savings and gas_savings > 0:
                gas_cost_usd = gas_cost_usd * (
                    Decimal('1') - gas_savings / Decimal('100')
                )

            # Create trade record with lowercase status
            trade = PaperTrade.objects.create(
                account=self.account,
                trade_type=trade_type,  # lowercase: 'buy' or 'sell'
                token_in_address=token_in_address,
                token_in_symbol=token_in_symbol,
                token_out_address=token_out_address,
                token_out_symbol=token_out_symbol,
                amount_in=amount_in_usd * Decimal('1e18'),  # Convert to wei
                amount_in_usd=amount_in_usd,
                expected_amount_out=expected_amount_out * Decimal('1e18'),
                actual_amount_out=actual_amount_out * Decimal('1e18'),
                simulated_gas_price_gwei=gas_price_gwei,
                simulated_gas_used=gas_used,
                simulated_gas_cost_usd=gas_cost_usd,
                simulated_slippage_percent=total_slippage,
                status='completed',  # IMPORTANT: Use lowercase 'completed'
                executed_at=timezone.now(),
                execution_time_ms=random.randint(500, 2000),
                mock_tx_hash='0x' + uuid.uuid4().hex,
                mock_block_number=random.randint(18000000, 18100000),
                strategy_name=(
                    self.strategy_config.name
                    if self.strategy_config
                    else f'Intel_{self.intel_level}'
                ),
                metadata={
                    'intel_level': self.intel_level,
                    'confidence_percent': float(
                        getattr(decision, 'overall_confidence', 75)
                    ),
                    'transaction_id': transaction_id,
                    'gas_savings': float(gas_savings) if gas_savings else None,
                    'decision_data': {
                        'action': decision.action,
                        'position_size_usd': float(decision.position_size_usd),
                        'risk_score': float(
                            getattr(decision, 'risk_score', 50)
                        ),
                        'primary_reasoning': getattr(
                            decision,
                            'primary_reasoning',
                            'Market opportunity detected'
                        )[:200]
                    }
                }
            )

            logger.info(
                f"[TRADE SAVED] {trade_type.upper()} trade created: "
                f"trade_id={trade.trade_id}, amount=${amount_in_usd:.2f}, "
                f"token={token_symbol}, slippage={total_slippage:.2f}%, "
                f"gas=${gas_cost_usd:.2f}, status=completed"
            )

            # ✅ UPDATE ACCOUNT STATISTICS
            # Refresh account data from database to prevent race conditions
            self.account.refresh_from_db()

            # Update trade counts based on status
            if trade.status == 'completed':
                self.account.winning_trades += 1
            elif trade.status == 'failed':
                self.account.losing_trades += 1

            # Update total trades counter
            self.account.total_trades += 1

            # Update account balance
            if trade_type == 'buy':
                # Deduct USDC and gas
                self.account.current_balance_usd -= (amount_in_usd + gas_cost_usd)
            else:  # sell
                # Add USDC minus gas
                self.account.current_balance_usd += (actual_amount_out - gas_cost_usd)

            # Save all account updates
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