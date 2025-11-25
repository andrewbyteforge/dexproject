"""
Validation Module for Paper Trading Bot

This module contains all validation logic to prevent database corruption
and ensure data integrity across the paper trading system.

CRITICAL: These validations prevent wei values from being stored as USD amounts,
catch NaN/Infinity values, and ensure all decimal values are within realistic ranges.

Responsibilities:
- Define validation limits for all trading operations
- Validate USD amounts and balance updates
- Validate wei amounts for database storage
- Check decimal validity (no NaN, Infinity, scientific notation)
- Convert decimals to strings safely
- Provide token address validation

File: dexproject/paper_trading/bot/shared/validation.py
"""

import logging
from decimal import Decimal, InvalidOperation, ROUND_DOWN
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
    
    # Price limits (USD) - Supports micro-cap tokens
    MIN_PRICE_USD: Decimal = Decimal('0.0000001')  # $0.0000001 = 1e-7 minimum
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
    MAX_TOKEN_QUANTITY: Decimal = Decimal('1000000000000')  # 1 trillion max
    
    # Gas simulation limits
    MIN_GAS_UNITS: int = 21000
    MAX_GAS_UNITS: int = 5000000
    MIN_GAS_PRICE_GWEI: Decimal = Decimal('1.0')
    MAX_GAS_PRICE_GWEI: Decimal = Decimal('500.0')
    
    # Token decimal limits
    USDC_DECIMALS: Decimal = Decimal('1000000')  # 1e6
    TOKEN_DECIMALS: Decimal = Decimal('1000000000000000000')  # 1e18
    
    # ==========================================================================
    # DATABASE FIELD CONSTRAINTS - CRITICAL FOR PREVENTING CORRUPTION
    # ==========================================================================
    # DecimalField(max_digits=36, decimal_places=18) allows:
    # - 18 digits after decimal point
    # - 18 digits before decimal point (36 - 18 = 18)
    # - Maximum integer part: 10^18 - 1
    # - We use 10^17 as safe limit to have margin for rounding
    MAX_WEI_FOR_DB: Decimal = Decimal('10') ** 17  # Safe limit for DB storage
    
    # Minimum token price to avoid overflow when calculating wei amounts
    # If price < this, wei amount could exceed MAX_WEI_FOR_DB
    # Calculated as: MIN_TRADE_USD / MAX_WEI_FOR_DB * TOKEN_DECIMALS
    MIN_SAFE_TOKEN_PRICE: Decimal = Decimal('0.0001')  # $0.0001 minimum


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


def validate_wei_amount(
    value: Decimal,
    field_name: str,
    max_value: Optional[Decimal] = None
) -> Tuple[bool, Optional[str], Decimal]:
    """
    Validate and sanitize a wei amount for database storage.
    
    CRITICAL: This function prevents the decimal.InvalidOperation error
    that occurs when reading back values that exceed the DecimalField constraints.
    
    The PaperTrade model uses DecimalField(max_digits=36, decimal_places=18),
    which can only store values up to 10^18 - 1 in the integer part.
    
    Args:
        value: Wei amount to validate
        field_name: Name of field for logging
        max_value: Maximum allowed value (defaults to MAX_WEI_FOR_DB)
        
    Returns:
        Tuple of (is_valid, error_message, sanitized_value)
        - is_valid: True if value is valid and within limits
        - error_message: Error description if invalid, None otherwise
        - sanitized_value: Cleaned value (or Decimal('0') if invalid)
        
    Example:
        >>> is_valid, error, clean_val = validate_wei_amount(
        ...     Decimal('1000000000000000000'),  # 1e18
        ...     'amount_in'
        ... )
        >>> print(is_valid, clean_val)
        True 1000000000000000000
    """
    if max_value is None:
        max_value = ValidationLimits.MAX_WEI_FOR_DB
    
    try:
        # Handle None
        if value is None:
            logger.warning(f"[WEI VALIDATION] {field_name} is None, using 0")
            return True, None, Decimal('0')
        
        # Ensure it's a Decimal
        if not isinstance(value, Decimal):
            try:
                value = Decimal(str(value))
            except (InvalidOperation, ValueError) as e:
                return False, f"{field_name} cannot be converted to Decimal: {e}", Decimal('0')
        
        # Check for NaN
        if value.is_nan():
            logger.error(f"[WEI VALIDATION] {field_name} is NaN")
            return False, f"{field_name} is NaN", Decimal('0')
        
        # Check for Infinity
        if value.is_infinite():
            logger.error(f"[WEI VALIDATION] {field_name} is Infinite")
            return False, f"{field_name} is Infinite", Decimal('0')
        
        # Check for negative values
        if value < 0:
            logger.error(f"[WEI VALIDATION] {field_name} is negative: {value}")
            return False, f"{field_name} cannot be negative", Decimal('0')
        
        # CRITICAL: Check if value exceeds database field constraints
        if value > max_value:
            logger.error(
                f"[WEI VALIDATION] {field_name} exceeds database limit: "
                f"{value:.2e} > {max_value:.2e}. "
                f"This would cause decimal.InvalidOperation on read."
            )
            return False, (
                f"{field_name} value {value:.2e} exceeds database limit {max_value:.2e}. "
                f"Token price may be too low for this trade size."
            ), Decimal('0')
        
        # Round down to integer (wei should be whole numbers)
        sanitized = value.to_integral_value(rounding=ROUND_DOWN)
        
        # Final check - ensure no scientific notation in string representation
        value_str = format(sanitized, 'f')
        if 'e' in value_str.lower():
            logger.error(
                f"[WEI VALIDATION] {field_name} still has scientific notation after "
                f"sanitization: {value_str}"
            )
            return False, f"{field_name} has invalid format", Decimal('0')
        
        return True, None, sanitized
        
    except Exception as e:
        logger.error(f"[WEI VALIDATION] Unexpected error validating {field_name}: {e}")
        return False, f"{field_name} validation error: {e}", Decimal('0')


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


def validate_token_price_for_trade(
    price: Decimal,
    trade_size_usd: Decimal,
    token_symbol: str
) -> Tuple[bool, Optional[str]]:
    """
    Validate that a token price won't cause wei overflow for a given trade size.
    
    When the token price is very low, the calculated wei amount can exceed
    the database field constraints, causing corruption.
    
    Args:
        price: Token price in USD
        trade_size_usd: Trade size in USD
        token_symbol: Token symbol for logging
        
    Returns:
        Tuple of (is_valid, error_message)
        
    Example:
        >>> is_valid, error = validate_token_price_for_trade(
        ...     Decimal('0.00000001'),  # Very low price
        ...     Decimal('1000'),         # $1000 trade
        ...     'PEPE'
        ... )
        >>> print(is_valid)
        False  # Would overflow
    """
    try:
        if price <= 0:
            return False, f"Price must be positive, got {price}"
        
        # Calculate what the wei amount would be
        # For a BUY: wei = (trade_size_usd / price) * 10^18
        token_amount = trade_size_usd / price
        wei_amount = token_amount * ValidationLimits.TOKEN_DECIMALS
        
        # Check if it would overflow
        if wei_amount > ValidationLimits.MAX_WEI_FOR_DB:
            return False, (
                f"Token price ${price} is too low for ${trade_size_usd} trade. "
                f"Would produce {wei_amount:.2e} wei, exceeding database limit of "
                f"{ValidationLimits.MAX_WEI_FOR_DB:.2e}. "
                f"Try a smaller trade size or skip {token_symbol}."
            )
        
        return True, None
        
    except Exception as e:
        return False, f"Price validation error for {token_symbol}: {e}"


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
    
    CRITICAL: This function ensures values are stored in fixed-point
    notation to prevent SQLite from storing them in a format that
    Django cannot read back.
    
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
    try:
        # Check for NaN or Infinity
        if value.is_nan():
            logger.error("[DECIMAL_TO_STR] NaN value detected, returning '0'")
            return '0'
        if value.is_infinite():
            logger.error("[DECIMAL_TO_STR] Infinite value detected, returning '0'")
            return '0'
        
        # CRITICAL: Check if value exceeds database limits
        if abs(value) > ValidationLimits.MAX_WEI_FOR_DB:
            logger.error(
                f"[DECIMAL_TO_STR] Value {value:.2e} exceeds database limit. "
                f"This would cause corruption. Returning '0'."
            )
            return '0'
        
        # Format without scientific notation
        formatted = format(value, 'f')
        
        # Verify no scientific notation slipped through
        if 'e' in formatted.lower():
            logger.error(
                f"[DECIMAL_TO_STR] Scientific notation in output: {formatted}. "
                f"Returning '0'."
            )
            return '0'
        
        # Strip trailing zeros after decimal point
        if '.' in formatted:
            return formatted.rstrip('0').rstrip('.')
        return formatted
        
    except Exception as e:
        logger.error(f"[DECIMAL_TO_STR] Error converting {value}: {e}")
        return '0'


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