"""
Trade Record Manager for Paper Trading Bot

This module handles all database record creation operations including
paper trade records, AI thought logs, account balance updates, and
WebSocket notifications.

CRITICAL: All monetary values must pass validation before database storage
to prevent corruption from NaN, Infinity, or overflow.

KEY DESIGN DECISION: We store token amounts in their NATURAL DECIMAL UNITS,
not wei. This prevents overflow for low-priced tokens while maintaining
18 decimal precision in the database.

Example:
- Buying 957 VIRTUAL tokens: Store as 957.000000000000000000 (natural units)
- NOT as 957000000000000000000 wei (would overflow DecimalField)

Responsibilities:
- Create paper trade records with realistic simulation
- Update account balances with validation
- Create AI thought logs for transparency
- Send WebSocket notifications for real-time UI updates
- Update account statistics (total trades, win/loss counts)

File: dexproject/paper_trading/bot/execution/trade_record_manager.py
"""

import logging
import math
import random
from decimal import Decimal
from typing import Optional, Any, TYPE_CHECKING

from paper_trading.models import (
    PaperTradingAccount,
    PaperTrade,
    PaperAIThoughtLog,
    PaperStrategyConfiguration,
    PaperTradingSession
)

# Import intelligence types
from paper_trading.intelligence.core.base import TradingDecision

# Import WebSocket service
from paper_trading.services.websocket_service import websocket_service

# Import validation functions
from paper_trading.bot.shared.validation import (
    validate_usd_amount,
    validate_balance_update,
    decimal_to_str,
    get_token_address_for_trade,
    ValidationLimits
)

if TYPE_CHECKING:
    from paper_trading.bot.execution.trade_executor import TradeExecutor

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def validate_token_amount(
    amount: Decimal,
    field_name: str,
    token_symbol: str
) -> tuple[bool, Optional[str], Decimal]:
    """
    Validate token amount is reasonable and won't cause database issues.
    
    This validates NATURAL token amounts (not wei), ensuring they fit
    within DecimalField(max_digits=36, decimal_places=18) constraints.
    
    Args:
        amount: Token amount in natural units (e.g., 957.5 tokens)
        field_name: Name of field for error messages
        token_symbol: Token symbol for logging
        
    Returns:
        Tuple of (is_valid, error_message, sanitized_amount)
    """
    try:
        # Handle None
        if amount is None:
            logger.warning(f"[TOKEN VALIDATION] {field_name} is None, using 0")
            return True, None, Decimal('0')
        
        # Ensure it's a Decimal
        if not isinstance(amount, Decimal):
            try:
                amount = Decimal(str(amount))
            except Exception as e:
                return False, f"{field_name} cannot be converted to Decimal: {e}", Decimal('0')
        
        # Check for NaN
        if amount.is_nan():
            logger.error(f"[TOKEN VALIDATION] {field_name} is NaN")
            return False, f"{field_name} is NaN", Decimal('0')
        
        # Check for Infinity
        if amount.is_infinite():
            logger.error(f"[TOKEN VALIDATION] {field_name} is Infinite")
            return False, f"{field_name} is Infinite", Decimal('0')
        
        # Check for negative values
        if amount < 0:
            logger.error(f"[TOKEN VALIDATION] {field_name} is negative: {amount}")
            return False, f"{field_name} cannot be negative", Decimal('0')
        
        # Check database field constraints
        # DecimalField(max_digits=36, decimal_places=18) allows:
        # - Up to 18 digits before decimal point (36 - 18 = 18)
        # - Maximum value: 999999999999999999.999999999999999999
        max_value = Decimal('999999999999999999')  # 10^18 - 1
        
        if amount > max_value:
            logger.error(
                f"[TOKEN VALIDATION] {field_name} exceeds database limit: "
                f"{amount} > {max_value}. Token: {token_symbol}"
            )
            return False, (
                f"{field_name} value {amount} exceeds database limit {max_value}. "
                f"This is extremely large for {token_symbol}."
            ), Decimal('0')
        
        # Quantize to 18 decimal places to match database field
        quantized = amount.quantize(Decimal('0.000000000000000001'))
        
        logger.debug(
            f"[TOKEN VALIDATION] {field_name} validated: {quantized} {token_symbol}"
        )
        
        return True, None, quantized
        
    except Exception as e:
        logger.error(f"[TOKEN VALIDATION] Unexpected error validating {field_name}: {e}")
        return False, f"{field_name} validation error: {e}", Decimal('0')


# =============================================================================
# TRADE RECORD CREATION
# =============================================================================

def create_paper_trade_record(
    executor: 'TradeExecutor',
    decision: TradingDecision,
    token_symbol: str,
    current_price: Decimal,
    position_manager: Any,
    execution_dex: str = 'uniswap_v3',
    dex_price: Decimal = Decimal('0')
) -> Optional[PaperTrade]:
    """
    Create a paper trade record in the database.
    
    This function handles the complete paper trade creation process including:
    - Trade amount validation (USD)
    - Price validation (USD)
    - Token amount calculation (NATURAL UNITS, not wei)
    - Token amount validation (prevents overflow)
    - Gas cost simulation
    - Database record creation
    - Balance update with validation
    - Account statistics update
    - AI thought log creation
    - WebSocket notification
    
    IMPORTANT: Token amounts are stored in NATURAL DECIMAL UNITS, not wei.
    This prevents overflow for low-priced tokens while maintaining precision.
    
    Args:
        executor: TradeExecutor instance with account, session, config
        decision: Trading decision from intelligence engine
        token_symbol: Token being traded
        current_price: Current token price in USD
        position_manager: Position manager instance
        execution_dex: DEX where trade is executed
        dex_price: Price from DEX (may differ from current_price)
        
    Returns:
        PaperTrade: Created trade record or None if failed
    """
    try:
        # Determine trade type
        trade_type = decision.action.lower()
        
        logger.info(
            f"[TRADE RECORD] Starting {trade_type.upper()} trade creation for {token_symbol} "
            f"at ${current_price}"
        )
        
        # =====================================================================
        # STEP 1: VALIDATE TRADE AMOUNT (USD)
        # =====================================================================
        is_valid, error = validate_usd_amount(
            decision.position_size_usd,
            'position_size_usd',
            ValidationLimits.MIN_TRADE_USD,
            ValidationLimits.MAX_TRADE_USD
        )
        if not is_valid:
            logger.error(f"[TRADE RECORD] Invalid trade amount: {error}")
            return None
        
        # =====================================================================
        # STEP 2: VALIDATE TOKEN PRICE (USD)
        # =====================================================================
        is_valid, error = validate_usd_amount(
            current_price,
            'current_price',
            ValidationLimits.MIN_PRICE_USD,
            ValidationLimits.MAX_PRICE_USD
        )
        if not is_valid:
            logger.error(f"[TRADE RECORD] Invalid price: {error}")
            return None
        
        # Check for zero or near-zero price (prevents division by zero)
        if current_price <= ValidationLimits.MIN_PRICE_USD:
            logger.error(
                f"[TRADE RECORD] Price too low for {token_symbol}: ${current_price}. "
                f"Minimum is ${ValidationLimits.MIN_PRICE_USD}."
            )
            return None
        
        logger.debug(
            f"[TRADE RECORD] Validation passed: Amount=${decision.position_size_usd}, "
            f"Price=${current_price}"
        )
        
        # =====================================================================
        # STEP 3: DETERMINE TOKEN ADDRESSES
        # =====================================================================
        if trade_type == 'buy':
            token_in_symbol = 'USDC'
            token_in_address = get_token_address_for_trade('USDC', executor.chain_id)
            token_out_symbol = token_symbol
            token_out_address = decision.token_address
            amount_in_usd = decision.position_size_usd
        elif trade_type == 'sell':
            token_in_symbol = token_symbol
            token_in_address = decision.token_address
            token_out_symbol = 'USDC'
            token_out_address = get_token_address_for_trade('USDC', executor.chain_id)
            amount_in_usd = decision.position_size_usd
        else:
            logger.error(f"[TRADE RECORD] Unsupported action: {decision.action}")
            return None
        
        logger.debug(
            f"[TRADE RECORD] Token addresses: IN={token_in_symbol} ({token_in_address[:10]}...), "
            f"OUT={token_out_symbol} ({token_out_address[:10]}...)"
        )
        
        # =====================================================================
        # STEP 4: SIMULATE GAS COSTS
        # =====================================================================
        simulated_gas_used = random.randint(
            ValidationLimits.MIN_GAS_UNITS,
            ValidationLimits.MAX_GAS_UNITS // 10
        )
        simulated_gas_price_gwei = Decimal(
            str(random.uniform(
                float(ValidationLimits.MIN_GAS_PRICE_GWEI),
                float(ValidationLimits.MAX_GAS_PRICE_GWEI) / 10
            ))
        ).quantize(Decimal('0.01'))
        
        # Calculate gas cost in USD
        eth_price = Decimal('2500')
        gas_cost_eth = (Decimal(simulated_gas_used) * simulated_gas_price_gwei) / Decimal('1e9')
        simulated_gas_cost_usd = (gas_cost_eth * eth_price).quantize(Decimal('0.01'))
        
        # Validate gas cost
        is_valid, error = validate_usd_amount(
            simulated_gas_cost_usd,
            'gas_cost',
            ValidationLimits.MIN_GAS_COST_USD,
            ValidationLimits.MAX_GAS_COST_USD
        )
        if not is_valid:
            logger.warning(f"[TRADE RECORD] Invalid gas cost, using default: {error}")
            simulated_gas_cost_usd = Decimal('5.00')
        
        logger.debug(
            f"[TRADE RECORD] Gas simulation: {simulated_gas_used} units @ "
            f"{simulated_gas_price_gwei} gwei = ${simulated_gas_cost_usd}"
        )
        
        # =====================================================================
        # STEP 5: CALCULATE TOKEN AMOUNTS (NATURAL UNITS - NOT WEI)
        # =====================================================================
        # CRITICAL: We store token amounts in their NATURAL DECIMAL UNITS.
        # This prevents overflow for low-priced tokens.
        #
        # Example for $900 buy of VIRTUAL @ $0.94:
        # - Token amount: 900 / 0.94 = 957.4468... tokens
        # - Store as: 957.446808510638297872 (natural units)
        # - NOT as: 957446808510638297872 wei (would overflow!)
        #
        # The database DecimalField(max_digits=36, decimal_places=18) can handle
        # up to 999,999,999,999,999,999.999999999999999999 in natural units.
        
        if trade_type == 'buy':
            # Buying: spending USDC, receiving token
            # amount_in = USDC amount (natural units, 6 decimals but we store as 18)
            # expected_amount_out = Token amount (natural units, 18 decimals)
            amount_in = Decimal(amount_in_usd)  # USDC in natural units
            expected_amount_out = Decimal(amount_in_usd) / Decimal(str(current_price))
            
            logger.debug(
                f"[TRADE RECORD] BUY calculation: "
                f"Spending {amount_in} USDC, receiving {expected_amount_out} {token_symbol}"
            )
            
        else:  # sell
            # Selling: spending token, receiving USDC
            # amount_in = Token amount (natural units, 18 decimals)
            # expected_amount_out = USDC amount (natural units, 6 decimals but we store as 18)
            amount_in = Decimal(amount_in_usd) / Decimal(str(current_price))
            expected_amount_out = Decimal(amount_in_usd)  # USDC in natural units
            
            logger.debug(
                f"[TRADE RECORD] SELL calculation: "
                f"Spending {amount_in} {token_symbol}, receiving {expected_amount_out} USDC"
            )
        
        # =====================================================================
        # STEP 6: VALIDATE TOKEN AMOUNTS
        # =====================================================================
        # Validate amount_in
        is_valid, error, amount_in_validated = validate_token_amount(
            amount_in,
            'amount_in',
            token_in_symbol
        )
        if not is_valid:
            logger.error(f"[TRADE RECORD] amount_in validation failed: {error}")
            return None
        
        # Validate expected_amount_out
        is_valid, error, expected_amount_out_validated = validate_token_amount(
            expected_amount_out,
            'expected_amount_out',
            token_out_symbol
        )
        if not is_valid:
            logger.error(f"[TRADE RECORD] expected_amount_out validation failed: {error}")
            return None
        
        # Convert to strings for safe database storage (no scientific notation)
        amount_in_str = decimal_to_str(amount_in_validated)
        expected_amount_out_str = decimal_to_str(expected_amount_out_validated)
        
        # Final safety check - reject if conversion produced zero for non-zero trade
        if amount_in_str == '0' and amount_in_usd > 0:
            logger.error(
                f"[TRADE RECORD] amount_in conversion failed for {token_in_symbol}. "
                f"Input: {amount_in}, Validated: {amount_in_validated}"
            )
            return None
        
        if expected_amount_out_str == '0' and amount_in_usd > 0:
            logger.error(
                f"[TRADE RECORD] expected_amount_out conversion failed for {token_out_symbol}. "
                f"Input: {expected_amount_out}, Validated: {expected_amount_out_validated}"
            )
            return None
        
        logger.info(
            f"[TRADE RECORD] Token amounts validated successfully: "
            f"IN={amount_in_str} {token_in_symbol}, OUT={expected_amount_out_str} {token_out_symbol}"
        )
        
        # =====================================================================
        # STEP 7: HELPER FUNCTION FOR METADATA
        # =====================================================================
        def sanitize_float(value: float, default: float = 0.0) -> float:
            """Sanitize float values, replacing NaN/Inf with default."""
            if value is None or math.isnan(value) or math.isinf(value):
                logger.warning(f"[SANITIZE] Float value {value} is invalid, using {default}")
                return default
            return float(value)
        
        # =====================================================================
        # STEP 8: CREATE TRADE RECORD
        # =====================================================================
        logger.debug(
            f"[TRADE RECORD] Creating database record for {trade_type.upper()} "
            f"{token_out_symbol}"
        )
        
        try:
            trade = PaperTrade.objects.create(
                account=executor.account,
                trade_type=trade_type,
                token_in_symbol=token_in_symbol,
                token_in_address=token_in_address,
                token_out_symbol=token_out_symbol,
                token_out_address=token_out_address,
                amount_in=Decimal(amount_in_str),
                amount_in_usd=amount_in_usd,
                expected_amount_out=Decimal(expected_amount_out_str),
                actual_amount_out=Decimal(expected_amount_out_str),
                simulated_gas_used=simulated_gas_used,
                simulated_gas_price_gwei=simulated_gas_price_gwei,
                simulated_gas_cost_usd=simulated_gas_cost_usd,
                simulated_slippage_percent=Decimal('0.5'),
                status='completed',
                execution_dex=execution_dex,
                strategy_name=executor.strategy_config.name if executor.strategy_config else 'Default',
                metadata={
                    'price_at_execution': sanitize_float(float(current_price)),
                    'dex_price': sanitize_float(float(dex_price)) if dex_price > 0 else None,
                    'session_id': str(executor.session.session_id) if executor.session else None,
                    'intel_level': executor.intel_level,
                    'confidence': sanitize_float(float(getattr(decision, 'overall_confidence', 0))),
                    'risk_score': sanitize_float(float(getattr(decision, 'risk_score', 0))),
                    'opportunity_score': sanitize_float(float(getattr(decision, 'opportunity_score', 0)))
                }
            )
        except Exception as e:
            logger.error(
                f"[TRADE RECORD] Database creation failed: {e}. "
                f"Values: amount_in={amount_in_str}, expected_out={expected_amount_out_str}",
                exc_info=True
            )
            return None
        
        logger.info(
            f"[PAPER TRADE] ✅ Created: {trade_type.upper()} {token_out_symbol}, "
            f"Amount=${amount_in_usd:.2f}, Price=${current_price}, "
            f"Qty={expected_amount_out_str[:10]}... {token_out_symbol}, DEX={execution_dex}"
        )
        
        # =====================================================================
        # STEP 9: UPDATE ACCOUNT BALANCE
        # =====================================================================
        if trade_type == 'buy':
            operation = 'subtract'
            amount_change = amount_in_usd
        elif trade_type == 'sell':
            operation = 'add'
            amount_change = amount_in_usd
        else:
            logger.error(f"[TRADE RECORD] Unknown trade type: {trade_type}")
            return None
        
        logger.debug(
            f"[TRADE RECORD] Updating balance: {operation} ${amount_change} from "
            f"${executor.account.current_balance_usd}"
        )
        
        # Validate balance update before applying
        is_valid, error, new_balance = validate_balance_update(
            executor.account.current_balance_usd,
            amount_change,
            operation
        )
        
        if not is_valid:
            logger.error(
                f"[TRADE RECORD] Balance update failed validation: {error}. "
                f"Trade created but balance not updated!"
            )
            return trade
        
        # Apply validated balance update
        executor.account.current_balance_usd = new_balance
        
        # Update account statistics
        executor.account.total_trades += 1
        if trade.status == 'completed':
            executor.account.winning_trades += 1
        elif trade.status == 'failed':
            executor.account.losing_trades += 1
        
        try:
            executor.account.save(update_fields=[
                'total_trades',
                'winning_trades',
                'losing_trades',
                'current_balance_usd'
            ])
        except Exception as e:
            logger.error(
                f"[TRADE RECORD] Failed to save account updates: {e}",
                exc_info=True
            )
            return trade
        
        logger.debug(
            f"[ACCOUNT STATS] ✅ Updated: Total={executor.account.total_trades}, "
            f"Winning={executor.account.winning_trades}, "
            f"Losing={executor.account.losing_trades}, "
            f"Balance=${executor.account.current_balance_usd:.2f}"
        )
        
        # =====================================================================
        # STEP 10: CREATE AI THOUGHT LOG
        # =====================================================================
        try:
            create_ai_thought_log(
                executor=executor,
                paper_trade=trade,
                decision=decision,
                token_symbol=token_symbol,
                token_address=token_out_address if trade_type == 'buy' else token_in_address
            )
        except Exception as e:
            logger.error(
                f"[TRADE RECORD] Failed to create AI thought log: {e}",
                exc_info=True
            )
            # Don't fail the trade if thought log fails
        
        # =====================================================================
        # STEP 11: SEND WEBSOCKET UPDATE
        # =====================================================================
        try:
            trade_data = {
                'trade_id': str(trade.trade_id),
                'trade_type': trade_type,
                'token_in_symbol': token_in_symbol,
                'token_out_symbol': token_out_symbol,
                'amount_in_usd': float(amount_in_usd),
                'status': 'completed',
                'execution_dex': execution_dex,
                'created_at': trade.created_at.isoformat()
            }
            websocket_service.send_trade_update(
                account_id=str(executor.account.account_id),
                trade_data=trade_data
            )
            logger.debug("[TRADE RECORD] WebSocket update sent successfully")
        except Exception as e:
            logger.error(f"[TRADE RECORD] Failed to send WebSocket update: {e}")
            # Don't fail the trade if WebSocket fails
        
        logger.info(
            f"[TRADE RECORD] ✅ Trade creation complete: {trade.trade_id}"
        )
        
        return trade
        
    except Exception as e:
        logger.error(
            f"[TRADE RECORD] ❌ Failed to create trade record for {token_symbol}: {e}",
            exc_info=True
        )
        return None


# =============================================================================
# AI THOUGHT LOG CREATION
# =============================================================================

def create_ai_thought_log(
    executor: 'TradeExecutor',
    paper_trade: PaperTrade,
    decision: TradingDecision,
    token_symbol: str,
    token_address: str
) -> Optional[PaperAIThoughtLog]:
    """
    Create AI thought log for the trade.
    
    This provides transparency into the AI's decision-making process by
    logging confidence scores, risk assessments, and reasoning.
    
    Args:
        executor: TradeExecutor instance with account, session, config
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
        risk_score = float(getattr(decision, 'risk_score', 50))
        
        logger.debug(
            f"[AI THOUGHT] Creating thought log: {token_symbol}, "
            f"confidence={confidence:.1f}%, risk={risk_score:.1f}"
        )
        
        # Create thought log using factory function
        from paper_trading.factories import create_thought_log_from_decision
        
        thought_log = create_thought_log_from_decision(
            account=executor.account,
            decision=decision,
            token_symbol=token_symbol,
            token_address=token_address,
            paper_trade=paper_trade,
            strategy_name=executor.strategy_config.name if executor.strategy_config else '',
            lane_used='FAST',
        )
        
        logger.info(
            f"[AI THOUGHT] ✅ Created thought log: confidence={confidence:.1f}%, "
            f"risk={risk_score:.1f}, decision={decision.action}"
        )
        
        return thought_log
        
    except Exception as e:
        logger.error(
            f"[AI THOUGHT] ❌ Failed to create AI thought log: {e}",
            exc_info=True
        )
        return None