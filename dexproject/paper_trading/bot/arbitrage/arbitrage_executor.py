"""
Arbitrage Executor for Paper Trading Bot (Phase 2)

This module handles arbitrage opportunity detection and execution for
cross-DEX profit opportunities. It identifies price discrepancies between
different DEXs and simulates arbitrage trades.

PHASE 2 FEATURE: This module enables the bot to detect and execute
arbitrage opportunities by comparing prices across multiple DEXs after
regular buy trades.

Responsibilities:
- Check for arbitrage opportunities after BUY trades
- Validate price data from multiple DEXs
- Calculate potential arbitrage profits
- Execute arbitrage trades (simulated in paper trading)
- Track arbitrage statistics and performance
- Validate profit amounts to prevent database corruption

FIXED: Now uses decimal_to_str() to prevent scientific notation corruption

File: dexproject/paper_trading/bot/arbitrage/arbitrage_executor.py
"""

import logging
import random
from decimal import Decimal
from typing import Any, Optional, TYPE_CHECKING

from asgiref.sync import async_to_sync

from paper_trading.models import PaperTrade
from shared.constants import get_token_address

# Import validation functions - INCLUDING decimal_to_str
from paper_trading.bot.shared.validation import (
    validate_usd_amount,
    validate_balance_update,
    decimal_to_str,  # ✅ ADDED: Import decimal_to_str to fix corruption
    ValidationLimits
)

# Import Arbitrage Components (optional)
try:
    from paper_trading.intelligence.strategies.arbitrage_engine import ArbitrageEngine
    from paper_trading.intelligence.dex.dex_price_comparator import DEXPriceComparator
    ARBITRAGE_AVAILABLE = True
except ImportError:
    ARBITRAGE_AVAILABLE = False
    ArbitrageEngine = None  # type: ignore
    DEXPriceComparator = None  # type: ignore

if TYPE_CHECKING:
    from paper_trading.bot.execution.trade_executor import TradeExecutor

logger = logging.getLogger(__name__)


# =============================================================================
# ARBITRAGE OPPORTUNITY DETECTION
# =============================================================================

def check_arbitrage_after_buy(
    executor: 'TradeExecutor',
    token_address: str,
    token_symbol: str,
    our_buy_price: Decimal,
    trade_amount_usd: Decimal
) -> None:
    """
    Check for arbitrage opportunities after executing a BUY trade.
    
    PHASE 2: After buying on one DEX, check if we can immediately sell
    at a higher price on another DEX for instant profit.
    
    This function:
    1. Initializes arbitrage components (detector, price comparator)
    2. Fetches current prices from multiple DEXs
    3. Validates price data to filter out testnet bad data
    4. Detects arbitrage opportunities
    5. Executes profitable arbitrage trades if profit meets threshold
    
    Args:
        executor: TradeExecutor instance with account, session, config
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
        if not executor.arbitrage_engine:
            executor.arbitrage_engine = ArbitrageEngine()
            logger.info("[ARBITRAGE] Detector initialized")
        
        if not executor.dex_price_comparator:
            executor.dex_price_comparator = DEXPriceComparator(chain_id=executor.chain_id)
            logger.info("[ARBITRAGE] Price comparator initialized")
        
        # Get current prices from multiple DEXs using compare_prices()
        logger.debug(f"[ARBITRAGE] Checking prices for {token_symbol}")
        
        price_comparison = async_to_sync(executor.dex_price_comparator.compare_prices)(
            token_address=token_address,
            token_symbol=token_symbol,
            use_cache=False  # Don't use cache for arbitrage checks
        )
        
        if not price_comparison or price_comparison.successful_queries < 2:
            logger.debug("[ARBITRAGE] Insufficient DEX price data")
            return
        
        # ⚠️ CRITICAL: Validate prices to filter out testnet bad data
        # Filter out prices that are clearly invalid (zero or near-zero)
        valid_prices = [
            p for p in price_comparison.prices
            if p.success and p.price_usd and 
            ValidationLimits.MIN_PRICE_USD <= p.price_usd <= ValidationLimits.MAX_PRICE_USD
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
        opportunity = executor.arbitrage_engine.detect_from_comparison(
            price_comparison=price_comparison,
            trade_amount_usd=trade_amount_usd
        )
        
        if opportunity and opportunity.is_profitable:
            executor.arbitrage_opportunities_found += 1
            
            # ⚠️ CRITICAL: Cap maximum arbitrage profit to prevent runaway growth
            if opportunity.net_profit_usd > ValidationLimits.MAX_ARBITRAGE_PROFIT_USD:
                logger.warning(
                    f"[ARBITRAGE] Profit capped: ${opportunity.net_profit_usd:.2f} → "
                    f"${ValidationLimits.MAX_ARBITRAGE_PROFIT_USD:.2f} (likely bad data from testnet)"
                )
                opportunity.net_profit_usd = ValidationLimits.MAX_ARBITRAGE_PROFIT_USD
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
            if opportunity.net_profit_usd >= ValidationLimits.MIN_ARBITRAGE_PROFIT_USD:
                # Execute arbitrage trade (in paper trading, just log it)
                execute_arbitrage_trade(executor, opportunity)
            else:
                logger.debug(
                    f"[ARBITRAGE] Profit too small: "
                    f"${opportunity.net_profit_usd:.2f} < ${ValidationLimits.MIN_ARBITRAGE_PROFIT_USD:.2f}"
                )
        else:
            logger.debug(f"[ARBITRAGE] No profitable opportunity for {token_symbol}")
    
    except Exception as e:
        logger.error(f"[ARBITRAGE] Error checking arbitrage: {e}", exc_info=True)


# =============================================================================
# ARBITRAGE TRADE EXECUTION
# =============================================================================

def execute_arbitrage_trade(
    executor: 'TradeExecutor',
    opportunity: Any
) -> None:
    """
    Execute an arbitrage trade opportunity.
    
    PHASE 2: In paper trading, this creates a virtual sell trade
    at the higher DEX price to capture the arbitrage profit.
    
    This function:
    1. Validates the arbitrage profit amount
    2. Updates account balance with profit
    3. Creates a PaperTrade record for the arbitrage
    4. Tracks arbitrage statistics
    
    Args:
        executor: TradeExecutor instance with account, session, config
        opportunity: ArbitrageOpportunity object with trade details
    """
    try:
        logger.info(
            f"[ARBITRAGE] 💰 Executing arbitrage: "
            f"Selling on {opportunity.sell_dex} for "
            f"${opportunity.net_profit_usd:.2f} profit"
        )
        
        # ⚠️ CRITICAL: Validate profit before updating balance
        is_valid, error = validate_usd_amount(
            opportunity.net_profit_usd,
            'arbitrage_profit',
            ValidationLimits.MIN_ARBITRAGE_PROFIT_USD,
            ValidationLimits.MAX_ARBITRAGE_PROFIT_USD
        )
        
        if not is_valid:
            logger.error(f"[ARBITRAGE] Invalid profit amount: {error}")
            return
        
        # Validate balance update
        is_valid, error, new_balance = validate_balance_update(
            executor.account.current_balance_usd,
            opportunity.net_profit_usd,
            'add'
        )
        
        if not is_valid:
            logger.error(f"[ARBITRAGE] Balance update failed validation: {error}")
            return
        
        # In paper trading, update account balance with profit
        executor.account.current_balance_usd = new_balance
        executor.account.save(update_fields=['current_balance_usd'])
        
        # Track arbitrage statistics
        executor.arbitrage_opportunities_executed += 1
        
        # Log the arbitrage trade as a separate trade record
        try:
            # ✅ FIXED: Calculate amounts in wei using proper Decimal conversion
            # Calculate as Decimal first, then use decimal_to_str() to prevent scientific notation
            amount_in_wei = (
                (opportunity.trade_amount_usd / opportunity.sell_price) * 
                ValidationLimits.TOKEN_DECIMALS
            )
            amount_out_wei = (
                (opportunity.trade_amount_usd + opportunity.net_profit_usd) * 
                ValidationLimits.USDC_DECIMALS
            )
            
            # ⚠️ CRITICAL: Check for NaN/Infinity before converting to string
            if amount_in_wei.is_nan() or amount_in_wei.is_infinite():
                logger.error(f"[ARBITRAGE] Invalid amount_in_wei: {amount_in_wei}")
                return
            if amount_out_wei.is_nan() or amount_out_wei.is_infinite():
                logger.error(f"[ARBITRAGE] Invalid amount_out_wei: {amount_out_wei}")
                return
            
            # ✅ FIXED: Use decimal_to_str() instead of str(int()) to prevent scientific notation
            amount_in_wei_str = decimal_to_str(amount_in_wei)
            amount_out_wei_str = decimal_to_str(amount_out_wei)
            
            # Debug logging
            logger.debug(f"[ARBITRAGE] amount_in_wei_str: '{amount_in_wei_str}'")
            logger.debug(f"[ARBITRAGE] amount_out_wei_str: '{amount_out_wei_str}'")
            
            # Simulate gas costs for arbitrage (higher than normal)
            simulated_gas_used = random.randint(300000, 400000)
            simulated_gas_price_gwei = Decimal('1.0')
            
            arbitrage_trade = PaperTrade.objects.create(
                account=executor.account,
                trade_type='sell',  # Arbitrage is a sell on different DEX
                token_in_symbol=opportunity.token_symbol,
                token_in_address=opportunity.token_address,
                token_out_symbol='USDC',
                token_out_address=get_token_address('USDC', executor.chain_id),
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
                    'session_id': str(executor.session.session_id) if executor.session else None
                }
            )
            
            logger.info(
                f"[ARBITRAGE] ✅ Arbitrage trade created: "
                f"ID={arbitrage_trade.trade_id}, "
                f"Profit=${opportunity.net_profit_usd:.2f}"
            )
        
        except Exception as e:
            logger.error(f"[ARBITRAGE] Failed to create trade record: {e}", exc_info=True)
        
        logger.info(
            f"[ARBITRAGE] Total: Found={executor.arbitrage_opportunities_found}, "
            f"Executed={executor.arbitrage_opportunities_executed}"
        )
    
    except Exception as e:
        logger.error(f"[ARBITRAGE] Failed to execute arbitrage: {e}", exc_info=True)