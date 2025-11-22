"""
Validation Module for Paper Trading Bot

This module contains all validation logic to prevent database corruption
and ensure data integrity across the paper trading system.

CRITICAL: These validations prevent wei values from being stored as USD amounts,
catch NaN/Infinity values, and ensure all decimal values are within realistic ranges.

Responsibilities:
- Define validation limits for all trading operations
- Validate USD amounts and balance updates
- Check decimal validity (no NaN, Infinity, scientific notation)
- Convert decimals to strings safely
- Provide token address validation

File: dexproject/paper_trading/bot/validation.py
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

# Import centralized token addresses
from shared.constants import get_token_address

# Import centralized defaults
from paper_trading.defaults import TradingDefaults

logger = logging.getLogger(__name__)


# =============================================================================
# VALIDATION CONSTANTS (Centralized)
# =============================================================================

class ValidationLimits:
    """
    Centralized validation limits to prevent database corruption.
    
    These limits ensure that values stored in the database are realistic
    and prevent issues like wei values being stored as USD amounts.
    
    All monetary values are in USD unless otherwise specified.
    Gas values are in USD or Gwei as indicated.
    """
    # Balance limits (USD)
    MIN_BALANCE_USD: Decimal = Decimal('0.00')
    MAX_BALANCE_USD: Decimal = Decimal('1000000.00')  # $1M max
    
    # Trade amount limits (USD)
    MIN_TRADE_USD: Decimal = TradingDefaults.MIN_POSITION_SIZE_USD
    MAX_TRADE_USD: Decimal = Decimal('100000.00')  # $100K max per trade
    
    # Price limits (USD)
    MIN_PRICE_USD: Decimal = Decimal('0.000000000000001')
    MAX_PRICE_USD: Decimal = Decimal('1000000.00')
    
    # Gas limits (USD)
    MIN_GAS_COST_USD: Decimal = Decimal('0.01')
    MAX_GAS_COST_USD: Decimal = Decimal('1000.00')
    
    # Arbitrage limits (USD)
    MIN_ARBITRAGE_PROFIT_USD: Decimal = Decimal('5.00')
    MAX_ARBITRAGE_PROFIT_USD: Decimal = Decimal('1000.00')
    
    # Trading limits
    MAX_DAILY_TRADES: int = TradingDefaults.MAX_DAILY_TRADES
    MAX_CONSECUTIVE_FAILURES: int = 5
    
    # Gas simulation limits
    MIN_GAS_UNITS: int = 21000
    MAX_GAS_UNITS: int = 5000000
    MIN_GAS_PRICE_GWEI: Decimal = Decimal('1.0')
    MAX_GAS_PRICE_GWEI: Decimal = Decimal('500.0')
    
    # Token decimal limits
    USDC_DECIMALS: Decimal = Decimal('1000000')  # 1e6
    TOKEN_DECIMALS: Decimal = Decimal('1000000000000000000')  # 1e18


# =============================================================================
# VALIDATION HELPER FUNCTIONS
# =============================================================================

def is_valid_decimal(value: Decimal) -> bool:
    """
    Check if a Decimal value is valid (not NaN, Inf, or in scientific notation range).
    
    Args:
        value: Decimal value to check
        
    Returns:
        True if valid, False otherwise
        
    Example:
        >>> is_valid_decimal(Decimal('100.50'))
        True
        >>> is_valid_decimal(Decimal('NaN'))
        False
    """
    try:
        # Check for NaN
        if value.is_nan():
            return False
        
        # Check for Infinity
        if value.is_infinite():
            return False
        
        # Check if the value is too large (likely scientific notation)
        if abs(value) > Decimal('1e20'):
            return False
        
        return True
    except (InvalidOperation, AttributeError):
        return False


def validate_usd_amount(
    amount: Decimal,
    field_name: str,
    min_value: Optional[Decimal] = None,
    max_value: Optional[Decimal] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate that a USD amount is reasonable and not corrupted.
    
    This is CRITICAL to prevent database corruption. If this validation
    fails, DO NOT proceed with the trade or balance update.
    
    Args:
        amount: Amount to validate
        field_name: Name of field for error message
        min_value: Minimum allowed value (optional)
        max_value: Maximum allowed value (optional)
        
    Returns:
        Tuple of (is_valid, error_message)
        
    Example:
        >>> is_valid, error = validate_usd_amount(Decimal('100.00'), 'trade_amount')
        >>> if not is_valid:
        >>>     logger.error(error)
        >>>     return False
    """
    try:
        # Check if value is a valid Decimal
        if not isinstance(amount, Decimal):
            return False, f"{field_name} must be a Decimal, got {type(amount)}"
        
        # Check for invalid Decimal states
        if not is_valid_decimal(amount):
            return False, f"{field_name} is invalid (NaN/Inf/scientific notation): {amount}"
        
        # Check minimum value
        if min_value is not None and amount < min_value:
            return False, f"{field_name} too small: {amount} < {min_value}"
        
        # Check maximum value
        if max_value is not None and amount > max_value:
            return False, f"{field_name} too large: {amount} > {max_value}"
        
        # Check if this looks like a wei value (too many digits)
        # USD amounts should have at most 2 decimal places
        if amount > Decimal('1000000'):  # $1M
            # Might be a wei value mistakenly used as USD
            return False, (
                f"{field_name} suspiciously large: {amount}. "
                "This might be a wei value mistakenly used as USD."
            )
        
        return True, None
        
    except Exception as e:
        return False, f"{field_name} validation error: {e}"


def validate_balance_update(
    current_balance: Decimal,
    amount_change: Decimal,
    operation: str
) -> Tuple[bool, Optional[str], Decimal]:
    """
    Validate a balance update operation before applying it.
    
    Args:
        current_balance: Current account balance
        amount_change: Amount to add or subtract
        operation: 'add' or 'subtract'
        
    Returns:
        Tuple of (is_valid, error_message, new_balance)
        
    Example:
        >>> is_valid, error, new_balance = validate_balance_update(
        ...     Decimal('1000.00'),
        ...     Decimal('100.00'),
        ...     'subtract'
        ... )
        >>> if is_valid:
        ...     account.current_balance_usd = new_balance
    """
    try:
        # Validate current balance
        is_valid, error = validate_usd_amount(
            current_balance,
            'current_balance',
            ValidationLimits.MIN_BALANCE_USD,
            ValidationLimits.MAX_BALANCE_USD
        )
        if not is_valid:
            return False, error, current_balance
        
        # Validate amount change
        is_valid, error = validate_usd_amount(
            abs(amount_change),
            'amount_change',
            Decimal('0.01'),
            ValidationLimits.MAX_TRADE_USD
        )
        if not is_valid:
            return False, error, current_balance
        
        # Calculate new balance
        if operation == 'subtract':
            new_balance = current_balance - amount_change
        elif operation == 'add':
            new_balance = current_balance + amount_change
        else:
            return False, f"Invalid operation: {operation}", current_balance
        
        # Validate new balance
        is_valid, error = validate_usd_amount(
            new_balance,
            'new_balance',
            ValidationLimits.MIN_BALANCE_USD,
            ValidationLimits.MAX_BALANCE_USD
        )
        if not is_valid:
            return False, error, current_balance
        
        return True, None, new_balance
        
    except Exception as e:
        return False, f"Balance validation error: {e}", current_balance


def decimal_to_str(value: Decimal) -> str:
    """
    Convert Decimal to string, ensuring no scientific notation.
    
    Args:
        value: Decimal value to convert
        
    Returns:
        String representation without scientific notation
        
    Example:
        >>> decimal_to_str(Decimal('1234.5678'))
        '1234.5678'
        >>> decimal_to_str(Decimal('1234.5000'))
        '1234.5'
    """
    # Check for NaN or Infinity
    if value.is_nan():
        logger.error("[DECIMAL_TO_STR] NaN value detected, returning '0'")
        return '0'
    if value.is_infinite():
        logger.error("[DECIMAL_TO_STR] Infinite value detected, returning '0'")
        return '0'
    
    # Format without scientific notation and strip trailing zeros
    formatted = format(value, 'f')
    if '.' in formatted:
        return formatted.rstrip('0').rstrip('.')
    return formatted


# =============================================================================
# TOKEN ADDRESS VALIDATION
# =============================================================================

def get_token_address_for_trade(symbol: str, chain_id: int) -> str:
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
        >>> address = get_token_address_for_trade('WETH', 8453)
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