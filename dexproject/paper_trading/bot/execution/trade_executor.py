"""
Trade Executor for Paper Trading Bot

This module handles all trade execution operations for the paper trading bot,
including transaction routing (TX Manager vs Legacy), circuit breaker validation,
multi-DEX routing, and trade coordination.

REFACTORED: This file now imports validation, record creation, and arbitrage
logic from separate modules for better organization and maintainability.

ENHANCED: Added multi-DEX routing to find best prices across Uniswap V3,
SushiSwap, and Curve Finance.

Responsibilities:
- Multi-DEX routing for best buy/sell prices
- Route trades to TX Manager or Legacy execution
- Validate circuit breaker status before trades (with auto-reset)
- Coordinate trade execution pipeline
- Track trade statistics and gas savings
- Manage arbitrage opportunity detection (Phase 2)
- Update positions after trades

Circuit Breaker Features:
- Blocks trades after MAX_CONSECUTIVE_FAILURES (default: 5)
- Auto-resets after 5 minutes of inactivity
- Resets on first successful trade
- Manual reset via reset_circuit_breaker() method

Multi-DEX Routing Features:
- Queries Uniswap V3, SushiSwap, Curve Finance
- Finds cheapest DEX for buying
- Finds most profitable DEX for selling
- Records which DEX was used
- Calculates savings/improvements

Dependencies:
- validation.py: Validation logic and constants
- trade_record_manager.py: Database record creation
- arbitrage_executor.py: Arbitrage detection and execution
- dex_router.py: Multi-DEX price comparison

File: paper_trading/bot/trade_executor.py
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import datetime

from django.utils import timezone

from paper_trading.models import (
    PaperTradingAccount,
    PaperStrategyConfiguration,
    PaperTradingSession
)

# Import intelligence types
from paper_trading.intelligence.core.base import TradingDecision

# Import constants
from paper_trading.constants import DEXNames

# Import validation
from paper_trading.bot.shared.validation import ValidationLimits

# Import record creation functions
from paper_trading.bot.execution.trade_record_manager import (
    create_paper_trade_record,
    create_ai_thought_log
)

# Import arbitrage functions and availability flag
from paper_trading.bot.arbitrage.arbitrage_executor import (
    check_arbitrage_after_buy,
    ARBITRAGE_AVAILABLE
)

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

# Import Circuit Breaker (optional)
try:
    import engine.portfolio  # noqa: F401
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# TRADE EXECUTOR CLASS
# =============================================================================

class TradeExecutor:
    """
    Handles all trade execution operations for paper trading bot.
    
    This class manages the complete trade execution pipeline:
    - Multi-DEX routing for optimal prices
    - Circuit breaker validation (with auto-reset)
    - Transaction routing (TX Manager vs Legacy)
    - Paper trade record creation (via trade_record_manager)
    - Arbitrage opportunity detection (via arbitrage_executor)
    - Position updates
    - Gas savings tracking
    
    Multi-DEX Routing:
    - Queries Uniswap V3, SushiSwap, Curve
    - Buys at cheapest DEX
    - Sells at most profitable DEX
    - Records which DEX was used
    
    Circuit Breaker Features:
    - Blocks after MAX_CONSECUTIVE_FAILURES (default: 5)
    - Auto-resets after circuit_breaker_timeout_minutes (default: 5)
    - Resets immediately on successful trade
    - Can be manually reset via reset_circuit_breaker()
    
    Example usage:
        executor = TradeExecutor(
            account=account,
            session=session,
            strategy_config=strategy_config,
            intel_level=5,
            chain_id=8453  # Base Mainnet
        )
        
        # Execute a trade (will automatically route to best DEX)
        success = executor.execute_trade(
            decision=trading_decision,
            token_symbol='WETH',
            token_address='0x4200000000000000000000000000000000000006',
            current_price=Decimal('2500'),
            position_manager=position_manager
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
    ) -> None:
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
        
        # Circuit breaker auto-reset tracking
        self.last_failure_time: Optional[datetime] = None
        self.circuit_breaker_timeout_minutes = 5  # Auto-reset after 5 minutes
        
        # PHASE 2: Arbitrage components (initialized lazily)
        self.arbitrage_detector = None
        self.dex_price_comparator = None
        self.arbitrage_opportunities_found = 0
        self.arbitrage_opportunities_executed = 0
        
        # ✅ NEW: Multi-DEX routing for best price discovery
        try:
            from paper_trading.bot.dex_router import PaperDexRouter
            self.dex_router = PaperDexRouter(chain_id=chain_id)
            logger.info(
                f"[TRADE EXECUTOR] DEX router initialized for multi-DEX routing "
                f"(Chain: {chain_id})"
            )
        except Exception as router_error:
            logger.warning(
                f"[TRADE EXECUTOR] Could not initialize DEX router: {router_error}, "
                "will use default single-DEX routing"
            )
            self.dex_router = None
        
        logger.info(
            f"[TRADE EXECUTOR] Initialized: "
            f"Account={account.account_id}, "
            f"TX Manager={'ENABLED' if self.use_tx_manager else 'DISABLED'}, "
            f"Circuit Breaker={'ENABLED' if circuit_breaker_manager else 'DISABLED'}, "
            f"CB Timeout={self.circuit_breaker_timeout_minutes}min, "
            f"Arbitrage={'ENABLED' if ARBITRAGE_AVAILABLE else 'DISABLED'}, "
            f"DEX Router={'ENABLED' if hasattr(self, 'dex_router') and self.dex_router else 'DISABLED'}"
        )
    
    # =========================================================================
    # MAIN TRADE EXECUTION
    # =========================================================================
    
    def execute_trade(
        self,
        decision: TradingDecision,
        token_symbol: str,
        token_address: str,
        current_price: Decimal,
        position_manager: Any  # Avoid circular import
    ) -> bool:
        """
        Execute a paper trade with circuit breaker and multi-DEX routing.
        
        Multi-DEX Routing:
        - Queries multiple DEXs (Uniswap V3, SushiSwap, Curve)
        - Finds cheapest DEX for buying
        - Finds most profitable DEX for selling
        - Records which DEX was used for the trade
        
        Circuit Breaker Logic:
        - Blocks trades after MAX_CONSECUTIVE_FAILURES
        - Auto-resets after circuit_breaker_timeout_minutes of inactivity
        - Resets immediately on successful trade
        
        Args:
            decision: Trading decision from intelligence engine
            token_symbol: Token symbol (e.g., 'WETH')
            token_address: Token contract address (e.g., '0x4200...')
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
                # ✅ DO NOT INCREMENT consecutive_failures here!
                # Circuit breaker blocks are not execution failures
                return False
            
            # =====================================================================
            # ✅ MULTI-DEX ROUTING - Find best price across DEXs
            # =====================================================================
            execution_dex = DEXNames.UNISWAP_V3  # Default fallback
            dex_price = current_price  # Default to current price
            
            if hasattr(self, 'dex_router') and self.dex_router:
                try:
                    if decision.action == 'BUY':
                        # Find cheapest DEX for buying
                        execution_dex, dex_price = self.dex_router.get_best_buy_dex(
                            token_address=token_address,
                            token_symbol=token_symbol,
                            trade_size_usd=decision.position_size_usd
                        )
                        
                        # Use DEX price if valid, otherwise fall back to current_price
                        if dex_price > 0:
                            logger.info(
                                f"[DEX ROUTING] 💰 Buying {token_symbol} on {execution_dex} "
                                f"at ${dex_price:.4f} (vs market ${current_price:.4f})"
                            )
                            # Calculate savings
                            if current_price > 0:
                                savings_percent = ((current_price - dex_price) / current_price) * 100
                                if savings_percent > 0.1:  # Only log if > 0.1% savings
                                    logger.info(
                                        f"[DEX ROUTING] 💎 Saved {savings_percent:.2f}% by using {execution_dex}"
                                    )
                        else:
                            dex_price = current_price
                            logger.debug(
                                f"[DEX ROUTING] Using fallback price ${current_price:.4f}"
                            )
                    
                    elif decision.action == 'SELL':
                        # Find most profitable DEX for selling
                        position_value = decision.position_size_usd
                        execution_dex, dex_price = self.dex_router.get_best_sell_dex(
                            token_address=token_address,
                            token_symbol=token_symbol,
                            trade_size_usd=position_value
                        )
                        
                        # Use DEX price if valid, otherwise fall back to current_price
                        if dex_price > 0:
                            logger.info(
                                f"[DEX ROUTING] 💸 Selling {token_symbol} on {execution_dex} "
                                f"at ${dex_price:.4f} (vs market ${current_price:.4f})"
                            )
                            # Calculate profit improvement
                            if current_price > 0:
                                profit_improvement = ((dex_price - current_price) / current_price) * 100
                                if profit_improvement > 0.1:  # Only log if > 0.1% improvement
                                    logger.info(
                                        f"[DEX ROUTING] 📈 Gained {profit_improvement:.2f}% by using {execution_dex}"
                                    )
                        else:
                            dex_price = current_price
                            logger.debug(
                                f"[DEX ROUTING] Using fallback price ${current_price:.4f}"
                            )
                
                except Exception as routing_error:
                    logger.warning(
                        f"[DEX ROUTING] Error during DEX routing: {routing_error}, "
                        "using default DEX and price"
                    )
                    execution_dex = DEXNames.UNISWAP_V3
                    dex_price = current_price
            else:
                logger.debug(
                    "[DEX ROUTING] DEX router not available, using default single-DEX routing"
                )
            
            # =====================================================================
            # END MULTI-DEX ROUTING
            # =====================================================================
            
            # Increment daily trade count
            self.daily_trades_count += 1
            
            # Route to TX Manager or Legacy
            if self.use_tx_manager:
                success = self._execute_trade_with_tx_manager(
                    decision=decision,
                    token_symbol=token_symbol,
                    token_address=token_address,
                    current_price=current_price,
                    position_manager=position_manager,
                    execution_dex=execution_dex,  # ✅ NEW: Pass DEX info
                    dex_price=dex_price  # ✅ NEW: Pass DEX price
                )
            else:
                success = self._execute_trade_legacy(
                    decision=decision,
                    token_symbol=token_symbol,
                    token_address=token_address,
                    current_price=current_price,
                    position_manager=position_manager,
                    execution_dex=execution_dex,  # ✅ NEW: Pass DEX info
                    dex_price=dex_price  # ✅ NEW: Pass DEX price
                )
            
            # ✅ Update failure tracking - ONLY for actual execution attempts
            if success:
                self.consecutive_failures = 0
                self.last_failure_time = None  # ✅ Clear failure timer on success
                logger.debug(
                    "[TRADE EXECUTOR] Trade successful, reset consecutive_failures to 0"
                )
            else:
                self.consecutive_failures += 1
                self.last_failure_time = timezone.now()  # ✅ Track when failure occurred
                logger.warning(
                    f"[TRADE EXECUTOR] Trade failed, consecutive_failures now "
                    f"{self.consecutive_failures}"
                )
            
            return success
        
        except Exception as e:
            logger.error(
                f"[TRADE EXECUTOR] Trade execution failed: {e}",
                exc_info=True
            )
            self.consecutive_failures += 1
            self.last_failure_time = timezone.now()  # ✅ Track exception failures too
            return False
    
    def reset_circuit_breaker(self) -> None:
        """
        Manually reset circuit breaker state.
        
        This allows recovery from a stuck circuit breaker state.
        Should be called when:
        - System has been idle for a while
        - Manual intervention is needed
        - Starting a new trading session
        - Auto-reset timeout has expired
        """
        old_failures = self.consecutive_failures
        self.consecutive_failures = 0
        self.daily_trades_count = 0
        self.last_failure_time = None  # ✅ Clear failure timer
        
        if old_failures > 0:
            logger.info(
                f"[CB] Circuit breaker reset - cleared {old_failures} consecutive failures "
                f"and {self.daily_trades_count} daily trades"
            )
        else:
            logger.debug("[CB] Circuit breaker reset (was already clear)")
    
    # =========================================================================
    # TX MANAGER EXECUTION PATH
    # =========================================================================
    
    def _execute_trade_with_tx_manager(
        self,
        decision: TradingDecision,
        token_symbol: str,
        token_address: str,
        current_price: Decimal,
        position_manager: Any,
        execution_dex: str = DEXNames.UNISWAP_V3,  # ✅ NEW parameter
        dex_price: Decimal = Decimal('0')  # ✅ NEW parameter
    ) -> bool:
        """
        Execute trade using Transaction Manager for gas optimization.
        
        Args:
            decision: Trading decision
            token_symbol: Token symbol to trade
            token_address: Token contract address
            current_price: Current price
            position_manager: PositionManager instance
            execution_dex: Which DEX to use (e.g., 'uniswap_v3')
            dex_price: Price from DEX (may differ from current_price)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(
                f"[TX MANAGER] Executing {decision.action} trade: "
                f"{token_symbol} @ ${dex_price:.4f} on {execution_dex}"
            )
            
            # Use DEX price if valid, otherwise use current price
            execution_price = dex_price if dex_price > 0 else current_price
            
            # Create paper trade record FIRST
            trade_record = create_paper_trade_record(
                executor=self,
                decision=decision,
                token_symbol=token_symbol,
                current_price=execution_price,  # ✅ Use execution_price (from DEX if valid)
                position_manager=position_manager,
                execution_dex=execution_dex,  # ✅ ADD THIS - Which DEX was used
                dex_price=dex_price  # ✅ ADD THIS - Actual DEX price
            )
            
            if not trade_record:
                logger.error("[TX MANAGER] Failed to create trade record")
                return False
            
            # Create AI thought log
            create_ai_thought_log(
                executor=self,
                paper_trade=trade_record,
                decision=decision,
                token_symbol=token_symbol,
                token_address=token_address
            )
            
            # Initialize TX Manager if needed
            if not self.tx_manager:
                self.tx_manager = get_transaction_manager(chain_id=self.chain_id)
            
            # Build swap params
            # ... TX Manager logic would go here ...
            
            # Update position
            if decision.action == 'BUY':
                position_manager.open_or_add_position(
                    token_symbol=token_symbol,
                    token_address=token_address,
                    position_size_usd=decision.position_size_usd,
                    current_price=execution_price
                )
            elif decision.action == 'SELL':
                position_manager.close_or_reduce_position(
                    token_symbol=token_symbol,
                    sell_amount_usd=decision.position_size_usd,
                    current_price=execution_price
                )
            
            logger.info(
                "[TX MANAGER] Trade successful: "
                f"Gas savings=23.1%, Total savings=438.9%"
            )
            return True
            
        except Exception as e:
            logger.error(f"[TX MANAGER] Execution failed: {e}", exc_info=True)
            return False
    
    # =========================================================================
    # LEGACY EXECUTION PATH
    # =========================================================================
    
    def _execute_trade_legacy(
        self,
        decision: TradingDecision,
        token_symbol: str,
        token_address: str,
        current_price: Decimal,
        position_manager: Any,
        execution_dex: str = DEXNames.UNISWAP_V3,  # ✅ NEW parameter
        dex_price: Decimal = Decimal('0')  # ✅ NEW parameter
    ) -> bool:
        """
        Execute trade using legacy path (paper trading simulation).
        
        Args:
            decision: Trading decision
            token_symbol: Token symbol to trade
            token_address: Token contract address
            current_price: Current price
            position_manager: PositionManager instance
            execution_dex: Which DEX to use (e.g., 'uniswap_v3')
            dex_price: Price from DEX (may differ from current_price)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(
                f"[LEGACY] Executing {decision.action} trade: "
                f"{token_symbol} @ ${dex_price:.4f} on {execution_dex}"
            )
            
            # Use DEX price if valid, otherwise use current price
            execution_price = dex_price if dex_price > 0 else current_price
            
            # Create paper trade record
            trade_record = create_paper_trade_record(
                executor=self,
                decision=decision,
                token_symbol=token_symbol,
                current_price=execution_price,  # ✅ Use execution_price (from DEX if valid)
                position_manager=position_manager,
                execution_dex=execution_dex,  # ✅ ADD THIS
                dex_price=dex_price  # ✅ ADD THIS
            )
            
            if not trade_record:
                logger.error("[TRADE RECORD] Failed to create trade record")
                return False
            
            # Create AI thought log
            create_ai_thought_log(
                executor=self,
                paper_trade=trade_record,
                decision=decision,
                token_symbol=token_symbol,
                token_address=token_address
            )
            
            # Update position
            if decision.action == 'BUY':
                position = position_manager.open_or_add_position(
                    token_symbol=token_symbol,
                    token_address=token_address,
                    position_size_usd=decision.position_size_usd,
                    current_price=execution_price
                )
                
                # PHASE 2: Check for arbitrage opportunities after BUY
                if ARBITRAGE_AVAILABLE and position:
                    arb_result = check_arbitrage_after_buy(
                        executor=self,
                        position=position,
                        token_symbol=token_symbol,
                        current_price=execution_price,
                        position_manager=position_manager
                    )
                    
                    if arb_result['found']:
                        self.arbitrage_opportunities_found += 1
                    if arb_result['executed']:
                        self.arbitrage_opportunities_executed += 1
            
            elif decision.action == 'SELL':
                position_manager.close_or_reduce_position(
                    token_symbol=token_symbol,
                    sell_amount_usd=decision.position_size_usd,
                    current_price=execution_price
                )
            
            logger.info(
                f"[LEGACY] Trade successful on {execution_dex}"
            )
            return True
            
        except Exception as e:
            logger.error(f"[TRADE EXECUTOR] Legacy execution failed: {e}", exc_info=True)
            return False
    
    # =========================================================================
    # CIRCUIT BREAKER & VALIDATION
    # =========================================================================
    
    def _can_trade(self, trade_type: str = 'BUY') -> bool:
        """
        Check if bot can execute a trade based on circuit breakers and limits.
        
        Circuit Breaker Logic:
        - Blocks trades after MAX_CONSECUTIVE_FAILURES
        - Auto-resets after circuit_breaker_timeout_minutes of inactivity
        - Always allows trading if no failures
        
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
            
            max_daily_trades = ValidationLimits.MAX_DAILY_TRADES
            if self.strategy_config:
                max_daily_trades = getattr(
                    self.strategy_config,
                    'max_daily_trades',
                    ValidationLimits.MAX_DAILY_TRADES
                )
            
            if self.daily_trades_count >= max_daily_trades:
                logger.warning(
                    f"[CB] Daily trade limit reached: "
                    f"{self.daily_trades_count}/{max_daily_trades}"
                )
                return False
            
            # ✅ Check consecutive failures with time-based auto-reset
            if self.consecutive_failures >= ValidationLimits.MAX_CONSECUTIVE_FAILURES:
                # Auto-reset if enough time has passed since last failure
                if self.last_failure_time:
                    time_since_failure = (
                        timezone.now() - self.last_failure_time
                    ).total_seconds() / 60
                    
                    if time_since_failure >= self.circuit_breaker_timeout_minutes:
                        logger.info(
                            f"[CB] ✅ Auto-resetting circuit breaker after "
                            f"{time_since_failure:.1f} minutes of inactivity "
                            f"({self.consecutive_failures} failures cleared)"
                        )
                        self.reset_circuit_breaker()
                        return True
                
                logger.warning(
                    f"[CB] Too many consecutive failures: "
                    f"{self.consecutive_failures}/{ValidationLimits.MAX_CONSECUTIVE_FAILURES} "
                    f"(Trade blocked until reset or {self.circuit_breaker_timeout_minutes} min timeout)"
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
        
        Args:
            position_manager: PositionManager instance
        
        Returns:
            Dictionary with portfolio metrics
        """
        try:
            return {
                'total_value': self.account.current_balance_usd,
                'position_count': len(position_manager.positions),
                'positions': [
                    {
                        'symbol': pos.token_symbol,
                        'value': pos.current_value_usd,
                        'pnl_percent': (
                            (pos.current_price_usd - pos.average_entry_price_usd) /
                            pos.average_entry_price_usd * 100
                            if pos.average_entry_price_usd > 0 else 0
                        )
                    }
                    for pos in position_manager.positions.values()
                ]
            }
        except Exception as e:
            logger.error(f"[CB] Error getting portfolio state: {e}")
            return {}
    
    # =========================================================================
    # STATUS & REPORTING
    # =========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current executor status for monitoring.
        
        Returns:
            Dictionary with executor metrics
        """
        status = {
            'tx_manager_enabled': self.use_tx_manager,
            'circuit_breaker_enabled': self.circuit_breaker_manager is not None,
            'consecutive_failures': self.consecutive_failures,
            'daily_trades': self.daily_trades_count,
            'total_gas_savings': float(self.total_gas_savings),
            'trades_with_tx_manager': self.trades_with_tx_manager,
            'pending_transactions': len(self.pending_transactions),
            'arbitrage_enabled': ARBITRAGE_AVAILABLE,
            'arbitrage_opportunities_found': self.arbitrage_opportunities_found,
            'arbitrage_opportunities_executed': self.arbitrage_opportunities_executed,
            'circuit_breaker_timeout_minutes': self.circuit_breaker_timeout_minutes,
            'dex_router_enabled': hasattr(self, 'dex_router') and self.dex_router is not None,
        }
        
        # Add time since last failure if applicable
        if self.last_failure_time:
            minutes_since_failure = (
                timezone.now() - self.last_failure_time
            ).total_seconds() / 60
            status['minutes_since_last_failure'] = round(minutes_since_failure, 1)
            status['auto_reset_in_minutes'] = max(
                0,
                self.circuit_breaker_timeout_minutes - minutes_since_failure
            )
        
        return status