"""
Type conversion utilities for consistent Decimal/float handling.

This module provides production-level type conversion utilities to ensure
consistent handling of Decimal and float types throughout the trading system.

File: dexproject/paper_trading/utils/type_utils.py
"""

from decimal import Decimal, InvalidOperation
from typing import Union, Optional, Any
import logging

logger = logging.getLogger(__name__)

# Type aliases for clarity
NumericType = Union[int, float, Decimal, str]


class TypeConverter:
    """
    Production-level type converter for numeric operations.
    
    Ensures consistent type handling across the trading system with
    proper error handling and validation.
    """
    
    @staticmethod
    def to_decimal(value: NumericType,
                   default: Optional[Decimal] = None,
                   precision: Optional[int] = None) -> Decimal:
        """
        Convert any numeric type to Decimal safely.
        
        This method never raises exceptions - it always returns a valid Decimal.
        Perfect for production trading systems where stability is critical.
    
        Args:
            value: Value to convert (int, float, Decimal, or string)
            default: Default value if conversion fails (defaults to Decimal('0'))
            precision: Optional decimal places to round to
        
        Returns:
            Decimal representation of the value (always valid, never None)
            
        Examples:
            >>> to_decimal(123.45)
            Decimal('123.45')
            >>> to_decimal("1,234.56")
            Decimal('1234.56')
            >>> to_decimal(None)
            Decimal('0')
            >>> to_decimal("invalid", default=Decimal('100'))
            Decimal('100')
            >>> to_decimal(123.456789, precision=2)
            Decimal('123.46')
        """
        if default is None:
            default = Decimal('0')
        
        try:
            # Handle None
            if value is None:
                return default
            
            # Already a Decimal
            if isinstance(value, Decimal):
                result = value
            # String representation (most accurate for floats)
            elif isinstance(value, (int, float)):
                # Convert through string to avoid float precision issues
                result = Decimal(str(value))
            elif isinstance(value, str):
                # Clean the string first
                cleaned = value.strip().replace(',', '')
                if not cleaned:
                    return default
                result = Decimal(cleaned)
            else:
                # Try to convert unknown types
                try:
                    result = Decimal(str(value))
                except Exception:
                    logger.warning(f"Cannot convert {type(value)} to Decimal, using default")
                    return default
            
            # Apply precision if specified
            if precision is not None:
                quantize_str = '0.' + '0' * precision
                result = result.quantize(Decimal(quantize_str))
            
            return result
        
        except (InvalidOperation, ValueError, TypeError) as e:
            logger.error(f"Error converting {value} to Decimal: {e}")
            return default
    
    @staticmethod
    def to_float(value: NumericType, 
                 default: Optional[float] = None) -> float:
        """
        Convert any numeric type to float safely.
        
        Args:
            value: Value to convert
            default: Default value if conversion fails (defaults to 0.0)
            
        Returns:
            Float representation of the value
        """
        if default is None:
            default = 0.0
        
        try:
            if value is None:
                return default
            elif isinstance(value, float):
                return value
            elif isinstance(value, Decimal):
                return float(value)
            elif isinstance(value, (int, str)):
                return float(value)
            else:
                return float(str(value))
        except (ValueError, TypeError) as e:
            logger.error(f"Error converting {value} to float: {e}")
            return default
    
    @staticmethod
    def safe_multiply(a: NumericType, b: NumericType, 
                      precision: Optional[int] = None) -> Decimal:
        """
        Safely multiply two numeric values as Decimals.
        
        Args:
            a: First operand
            b: Second operand
            precision: Optional decimal places for result
            
        Returns:
            Product as Decimal
        """
        decimal_a = TypeConverter.to_decimal(a)
        decimal_b = TypeConverter.to_decimal(b)
        result = decimal_a * decimal_b
        
        if precision is not None:
            quantize_str = '0.' + '0' * precision
            result = result.quantize(Decimal(quantize_str))
        
        return result
    
    @staticmethod
    def safe_divide(numerator: NumericType, 
                    denominator: NumericType,
                    precision: Optional[int] = None,
                    default: Optional[Decimal] = None) -> Decimal:
        """
        Safely divide two numeric values as Decimals.
        
        Args:
            numerator: Numerator
            denominator: Denominator
            precision: Optional decimal places for result
            default: Value to return if division by zero
            
        Returns:
            Quotient as Decimal
        """
        if default is None:
            default = Decimal('0')
        
        decimal_num = TypeConverter.to_decimal(numerator)
        decimal_den = TypeConverter.to_decimal(denominator)
        
        if decimal_den == 0:
            logger.warning("Division by zero attempted, returning default")
            return default
        
        result = decimal_num / decimal_den
        
        if precision is not None:
            quantize_str = '0.' + '0' * precision
            result = result.quantize(Decimal(quantize_str))
        
        return result
    
    @staticmethod
    def safe_percentage(value: NumericType, 
                        percentage: NumericType,
                        precision: int = 2) -> Decimal:
        """
        Calculate percentage of a value safely.
        
        Args:
            value: Base value
            percentage: Percentage (e.g., 10 for 10%)
            precision: Decimal places for result
            
        Returns:
            Percentage of value as Decimal
        """
        decimal_value = TypeConverter.to_decimal(value)
        decimal_percentage = TypeConverter.to_decimal(percentage)
        
        result = (decimal_value * decimal_percentage) / Decimal('100')
        
        quantize_str = '0.' + '0' * precision
        return result.quantize(Decimal(quantize_str))


class MarketDataNormalizer:
    """
    Normalizes market data types for consistent processing.
    """
    
    @staticmethod
    def normalize_context(context: Any) -> Any:
        """
        Normalize all numeric fields in a market context object.
        
        Args:
            context: Market context object with mixed numeric types
            
        Returns:
            Context with all numeric fields as Decimals
        """
        # Fields that should be Decimals
        decimal_fields = [
            'liquidity_score', 'volatility_index', 'mev_threat_level',
            'slippage_risk', 'gas_optimization_score', 'confidence_score',
            'risk_score', 'opportunity_score', 'position_size_usd',
            'max_gas_price_gwei', 'overall_confidence'
        ]
        
        for field in decimal_fields:
            if hasattr(context, field):
                value = getattr(context, field)
                if value is not None and not isinstance(value, Decimal):
                    setattr(context, field, TypeConverter.to_decimal(value))
        
        return context
    
    @staticmethod
    def normalize_decision(decision: Any) -> Any:
        """
        Normalize all numeric fields in a trading decision object.
        
        Args:
            decision: Trading decision with mixed numeric types
            
        Returns:
            Decision with all numeric fields as Decimals
        """
        # Fields that should be Decimals
        decimal_fields = [
            'position_size_usd', 'risk_score', 'opportunity_score',
            'overall_confidence', 'max_gas_price_gwei', 'processing_time_ms'
        ]
        
        for field in decimal_fields:
            if hasattr(decision, field):
                value = getattr(decision, field)
                if value is not None and not isinstance(value, Decimal):
                    setattr(decision, field, TypeConverter.to_decimal(value))
        
        return decision


# Global converter instance
converter = TypeConverter()
normalizer = MarketDataNormalizer()


# Convenience functions
def to_decimal(value: NumericType, default: Optional[Decimal] = None) -> Decimal:
    """Convenience function for decimal conversion."""
    return converter.to_decimal(value, default)


def to_float(value: NumericType, default: Optional[float] = None) -> float:
    """Convenience function for float conversion."""
    return converter.to_float(value, default)


def safe_multiply(a: NumericType, b: NumericType) -> Decimal:
    """Convenience function for safe multiplication."""
    return converter.safe_multiply(a, b)


def safe_divide(a: NumericType, b: NumericType, default: Optional[Decimal] = None) -> Decimal:
    """Convenience function for safe division."""
    return converter.safe_divide(a, b, default=default)