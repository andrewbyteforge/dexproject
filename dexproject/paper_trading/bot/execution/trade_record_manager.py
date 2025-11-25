"""
Trade Record Manager for Paper Trading Bot

This module handles all database record creation operations including
paper trade records, AI thought logs, account balance updates, and
WebSocket notifications.

CRITICAL: All monetary values must pass validation before database storage
to prevent corruption from wei values, NaN, or Infinity.

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
    validate_wei_amount,
    validate_token_price_for_trade,
    validate_balance_update,
    decimal_to_str,
    get_token_address_for_trade,
    ValidationLimits
)

if TYPE_CHECKING:
    from paper_trading.bot.execution.trade_executor import TradeExecutor

logger = logging.getLogger(__name__)


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
    - Trade amount validation
    - Price validation (with overflow check)
    - Wei amount validation (prevents database corruption)
    - Gas cost simulation
    - Database record creation
    - Balance update with validation
    - Account statistics update
    - AI thought log creation
    - WebSocket notification
    
    Args:
        executor: TradeExecutor instance with account, session, config
        decision: Trading decision from intelligence engine
        token_symbol: Token being traded
        current_price: Current token price
        execution_dex: DEX where trade is executed
        dex_price: Price from DEX (may differ from current_price)
        
    Returns:
        PaperTrade: Created trade record or None if failed
    """
    try:
        # Determine trade type
        trade_type = decision.action.lower()
        
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
        
        # =====================================================================
        # STEP 3: CHECK IF PRICE WILL CAUSE WEI OVERFLOW (CRITICAL)
        # =====================================================================
        is_valid, error = validate_token_price_for_trade(
            current_price,
            decision.position_size_usd,
            token_symbol
        )
        if not is_valid:
            logger.error(f"[TRADE RECORD] {error}")
            return None
        
        # =====================================================================
        # STEP 4: DETERMINE TOKEN ADDRESSES
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
        
        # =====================================================================
        # STEP 5: SIMULATE GAS COSTS
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
        
        # =====================================================================
        # STEP 6: CALCULATE WEI AMOUNTS WITH VALIDATION (CRITICAL)
        # =====================================================================
        if trade_type == 'buy':
            # Buying: spending USDC (6 decimals), receiving token (18 decimals)
            amount_in_wei = Decimal(amount_in_usd) * ValidationLimits.USDC_DECIMALS
            expected_amount_out_wei = (
                Decimal(amount_in_usd) / Decimal(str(current_price))
            ) * ValidationLimits.TOKEN_DECIMALS
            
        else:  # sell
            # Selling: spending token (18 decimals), receiving USDC (6 decimals)
            amount_in_wei = (
                Decimal(amount_in_usd) / Decimal(str(current_price))
            ) * ValidationLimits.TOKEN_DECIMALS
            expected_amount_out_wei = Decimal(amount_in_usd) * ValidationLimits.USDC_DECIMALS
        
        # CRITICAL: Validate wei amounts before database storage
        is_valid, error, amount_in_wei = validate_wei_amount(
            amount_in_wei, 'amount_in'
        )
        if not is_valid:
            logger.error(f"[TRADE RECORD] {error}")
            return None
        
        is_valid, error, expected_amount_out_wei = validate_wei_amount(
            expected_amount_out_wei, 'expected_amount_out'
        )
        if not is_valid:
            logger.error(f"[TRADE RECORD] {error}")
            return None
        
        # Convert to strings without scientific notation
        amount_in_wei_str = decimal_to_str(amount_in_wei)
        expected_amount_out_wei_str = decimal_to_str(expected_amount_out_wei)
        
        # Final safety check - reject if conversion failed
        if amount_in_wei_str == '0' and amount_in_usd > 0:
            logger.error(
                f"[TRADE RECORD] amount_in_wei conversion failed for {token_symbol}"
            )
            return None
        if expected_amount_out_wei_str == '0' and amount_in_usd > 0:
            logger.error(
                f"[TRADE RECORD] expected_amount_out_wei conversion failed for {token_symbol}"
            )
            return None
        
        # =====================================================================
        # STEP 7: DEBUG LOGGING
        # =====================================================================
        logger.info(f"[TRADE RECORD] Creating {trade_type.upper()} trade for {token_symbol}")
        logger.debug(f"  amount_in_wei: {amount_in_wei_str}")
        logger.debug(f"  expected_amount_out_wei: {expected_amount_out_wei_str}")
        logger.debug(f"  amount_in_usd: {amount_in_usd}")
        logger.debug(f"  price: ${current_price}")
        logger.debug(f"  dex: {execution_dex}")
        
        # =====================================================================
        # STEP 8: HELPER FUNCTION FOR METADATA
        # =====================================================================
        def sanitize_float(value: float, default: float = 0.0) -> float:
            """Sanitize float values, replacing NaN/Inf with default."""
            if value is None or math.isnan(value) or math.isinf(value):
                return default
            return float(value)
        
        # =====================================================================
        # STEP 9: CREATE TRADE RECORD
        # =====================================================================
        trade = PaperTrade.objects.create(
            account=executor.account,
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
        
        logger.info(
            f"[PAPER TRADE] Created: {trade_type.upper()} {token_out_symbol}, "
            f"Amount=${amount_in_usd:.2f}, Price=${current_price:.4f}, DEX={execution_dex}"
        )
        
        # =====================================================================
        # STEP 10: UPDATE ACCOUNT BALANCE
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
        
        executor.account.save(update_fields=[
            'total_trades',
            'winning_trades',
            'losing_trades',
            'current_balance_usd'
        ])
        
        logger.debug(
            f"[ACCOUNT STATS] Updated: Total={executor.account.total_trades}, "
            f"Winning={executor.account.winning_trades}, "
            f"Losing={executor.account.losing_trades}, "
            f"Balance=${executor.account.current_balance_usd:.2f}"
        )
        
        # =====================================================================
        # STEP 11: CREATE AI THOUGHT LOG
        # =====================================================================
        create_ai_thought_log(
            executor=executor,
            paper_trade=trade,
            decision=decision,
            token_symbol=token_symbol,
            token_address=token_out_address if trade_type == 'buy' else token_in_address
        )
        
        # =====================================================================
        # STEP 12: SEND WEBSOCKET UPDATE
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
        except Exception as e:
            logger.error(f"[TRADE RECORD] Failed to send WebSocket update: {e}")
        
        return trade
        
    except Exception as e:
        logger.error(
            f"[TRADE RECORD] Failed to create trade record: {e}",
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
            f"[AI THOUGHT] Created thought log: confidence={confidence:.1f}%, "
            f"risk={getattr(decision, 'risk_score', 50):.1f}, "
            f"decision={decision.action}"
        )
        
        return thought_log
        
    except Exception as e:
        logger.error(
            f"[TRADE RECORD] Failed to create AI thought log: {e}",
            exc_info=True
        )
        return None