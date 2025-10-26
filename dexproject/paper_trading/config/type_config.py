"""
Production configuration for type safety and consistency.

This module provides centralized type configuration, validation rules,
and type-safe configuration handling for the trading system.

NOTE: Decimal context is configured in apps.py during Django startup.
This module provides configuration constants and validation utilities.

File: dexproject/paper_trading/config/type_config.py
"""

from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Optional, Union, List, Tuple
import logging

# Import TypeConverter with fallback for safe operation
try:
    from paper_trading.utils.type_utils import TypeConverter
    TYPE_CONVERTER_AVAILABLE = True
except ImportError:
    TYPE_CONVERTER_AVAILABLE = False
    # Fallback will be handled in TypeSafeConfig

logger = logging.getLogger(__name__)


# =============================================================================
# TYPE CONFIGURATION
# =============================================================================

class TypeConfig:
    """
    Centralized type configuration for the trading system.
    
    Provides constants and utilities for consistent type handling across
    the application. Decimal context setup is handled by apps.py.
    """
    
    # Decimal precision constants
    DECIMAL_PRECISION = 18  # Matches Ethereum's wei precision (10^18)
    DISPLAY_PRECISION = 8   # For UI display (8 decimal places)
    USD_PRECISION = 2       # For USD amounts (2 decimal places)
    PERCENTAGE_PRECISION = 4  # For percentage calculations (4 decimal places)
    
    # Price validation constants
    MAX_PRICE = Decimal('1000000000')  # $1 billion maximum price
    MIN_PRICE = Decimal('0.00000001')  # Minimum price (1 satoshi-equivalent)
    
    # Gas constants
    MAX_GAS_PRICE_GWEI = Decimal('1000')  # 1000 Gwei max
    MIN_GAS_PRICE_GWEI = Decimal('1')     # 1 Gwei min
    
    @staticmethod
    def get_field_types() -> Dict[str, type]:
        """
        Define expected types for all numeric fields in the trading system.
        
        This mapping is used for validation and type checking throughout
        the application.
        
        Returns:
            Dictionary mapping field names to their expected Python types
        """
        return {
            # Price fields - always Decimal for accuracy
            'price': Decimal,
            'entry_price': Decimal,
            'exit_price': Decimal,
            'current_price': Decimal,
            'average_price': Decimal,
            'stop_loss_price': Decimal,
            'take_profit_price': Decimal,
            
            # Amount fields - always Decimal
            'amount': Decimal,
            'quantity': Decimal,
            'balance': Decimal,
            'position_size': Decimal,
            'position_size_usd': Decimal,
            'amount_in': Decimal,
            'amount_out': Decimal,
            'amount_in_usd': Decimal,
            
            # Percentage fields - always Decimal
            'confidence': Decimal,
            'risk_score': Decimal,
            'opportunity_score': Decimal,
            'slippage': Decimal,
            'slippage_percent': Decimal,
            'fee_percent': Decimal,
            'profit_loss_percent': Decimal,
            
            # Gas fields - Decimal for price, int for usage
            'gas_price': Decimal,
            'gas_price_gwei': Decimal,
            'gas_limit': int,
            'gas_used': int,
            'gas_cost_usd': Decimal,
            
            # Time fields - int (timestamps in seconds/milliseconds)
            'timestamp': int,
            'block_number': int,
            'execution_time_ms': int,
            
            # Score fields - Decimal
            'liquidity_score': Decimal,
            'volatility_score': Decimal,
            'overall_confidence': Decimal,
        }
    
    @staticmethod
    def get_precision_for_field(field_name: str) -> int:
        """
        Get the appropriate decimal precision for a given field.
        
        Args:
            field_name: Name of the field
            
        Returns:
            Number of decimal places for the field
        """
        # USD fields get 2 decimal places
        if 'usd' in field_name.lower() or 'dollar' in field_name.lower():
            return TypeConfig.USD_PRECISION
        
        # Percentage fields get 4 decimal places
        if 'percent' in field_name.lower() or 'score' in field_name.lower():
            return TypeConfig.PERCENTAGE_PRECISION
        
        # Price fields get 8 decimal places for display
        if 'price' in field_name.lower():
            return TypeConfig.DISPLAY_PRECISION
        
        # Default to display precision
        return TypeConfig.DISPLAY_PRECISION


# =============================================================================
# VALIDATION RULES
# =============================================================================

class ValidationRules:
    """
    Production-level validation rules for numeric fields.
    
    Provides comprehensive validation for prices, percentages, amounts,
    and other numeric values with proper error handling and logging.
    """
    
    @staticmethod
    def validate_percentage(
        value: Union[Decimal, int, float],
        field_name: str = "percentage",
        min_value: Optional[Decimal] = None,
        max_value: Optional[Decimal] = None
    ) -> Decimal:
        """
        Validate that a value is a valid percentage.
        
        Args:
            value: Value to validate
            field_name: Name of field for error messages
            min_value: Minimum allowed value (default: 0)
            max_value: Maximum allowed value (default: 100)
            
        Returns:
            Validated value as Decimal
            
        Raises:
            ValueError: If value is not valid
            TypeError: If value cannot be converted to Decimal
        """
        # Set defaults
        if min_value is None:
            min_value = Decimal('0')
        if max_value is None:
            max_value = Decimal('100')
        
        try:
            # Convert to Decimal
            if not isinstance(value, Decimal):
                decimal_value = Decimal(str(value))
            else:
                decimal_value = value
            
            # Validate range
            if decimal_value < min_value or decimal_value > max_value:
                error_msg = (
                    f"{field_name} must be between {min_value} and {max_value}, "
                    f"got {decimal_value}"
                )
                logger.error(f"Validation error: {error_msg}")
                raise ValueError(error_msg)
            
            logger.debug(f"Validated {field_name}: {decimal_value}")
            return decimal_value
            
        except (InvalidOperation, ValueError) as e:
            error_msg = f"Cannot validate {field_name} with value {value}: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e
    
    @staticmethod
    def validate_positive(
        value: Union[Decimal, int, float],
        field_name: str = "value",
        allow_zero: bool = False
    ) -> Decimal:
        """
        Validate that a value is positive.
        
        Args:
            value: Value to validate
            field_name: Name of field for error messages
            allow_zero: Whether to allow zero as a valid value
            
        Returns:
            Validated value as Decimal
            
        Raises:
            ValueError: If value is not positive
            TypeError: If value cannot be converted to Decimal
        """
        try:
            # Convert to Decimal
            if not isinstance(value, Decimal):
                decimal_value = Decimal(str(value))
            else:
                decimal_value = value
            
            # Check positivity
            if allow_zero:
                if decimal_value < Decimal('0'):
                    error_msg = f"{field_name} must be non-negative, got {decimal_value}"
                    logger.error(f"Validation error: {error_msg}")
                    raise ValueError(error_msg)
            else:
                if decimal_value <= Decimal('0'):
                    error_msg = f"{field_name} must be positive, got {decimal_value}"
                    logger.error(f"Validation error: {error_msg}")
                    raise ValueError(error_msg)
            
            logger.debug(f"Validated {field_name}: {decimal_value}")
            return decimal_value
            
        except (InvalidOperation, ValueError) as e:
            error_msg = f"Cannot validate {field_name} with value {value}: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e
    
    @staticmethod
    def validate_price(
        value: Union[Decimal, int, float],
        field_name: str = "price",
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None
    ) -> Decimal:
        """
        Validate that a price is realistic and within bounds.
        
        Args:
            value: Price to validate
            field_name: Name of field for error messages
            min_price: Minimum allowed price (default: MIN_PRICE constant)
            max_price: Maximum allowed price (default: MAX_PRICE constant)
            
        Returns:
            Validated price as Decimal
            
        Raises:
            ValueError: If price is not realistic
            TypeError: If value cannot be converted to Decimal
        """
        # Set defaults from TypeConfig
        if min_price is None:
            min_price = TypeConfig.MIN_PRICE
        if max_price is None:
            max_price = TypeConfig.MAX_PRICE
        
        try:
            # Convert to Decimal
            if not isinstance(value, Decimal):
                decimal_value = Decimal(str(value))
            else:
                decimal_value = value
            
            # Validate positive
            if decimal_value <= Decimal('0'):
                error_msg = f"{field_name} must be positive, got {decimal_value}"
                logger.error(f"Validation error: {error_msg}")
                raise ValueError(error_msg)
            
            # Validate minimum
            if decimal_value < min_price:
                error_msg = (
                    f"{field_name} below minimum ({min_price}), "
                    f"got {decimal_value}"
                )
                logger.warning(f"Validation warning: {error_msg}")
                raise ValueError(error_msg)
            
            # Validate maximum
            if decimal_value > max_price:
                error_msg = (
                    f"{field_name} exceeds maximum ({max_price}), "
                    f"got {decimal_value}"
                )
                logger.error(f"Validation error: {error_msg}")
                raise ValueError(error_msg)
            
            logger.debug(f"Validated {field_name}: {decimal_value}")
            return decimal_value
            
        except (InvalidOperation, ValueError) as e:
            error_msg = f"Cannot validate {field_name} with value {value}: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e
    
    @staticmethod
    def validate_gas_price(
        value: Union[Decimal, int, float],
        field_name: str = "gas_price_gwei"
    ) -> Decimal:
        """
        Validate that a gas price is realistic.
        
        Args:
            value: Gas price in Gwei to validate
            field_name: Name of field for error messages
            
        Returns:
            Validated gas price as Decimal
            
        Raises:
            ValueError: If gas price is not realistic
        """
        return ValidationRules.validate_price(
            value=value,
            field_name=field_name,
            min_price=TypeConfig.MIN_GAS_PRICE_GWEI,
            max_price=TypeConfig.MAX_GAS_PRICE_GWEI
        )
    
    @staticmethod
    def validate_amount(
        value: Union[Decimal, int, float],
        field_name: str = "amount",
        max_amount: Optional[Decimal] = None
    ) -> Decimal:
        """
        Validate that an amount is positive and within bounds.
        
        Args:
            value: Amount to validate
            field_name: Name of field for error messages
            max_amount: Optional maximum allowed amount
            
        Returns:
            Validated amount as Decimal
            
        Raises:
            ValueError: If amount is not valid
        """
        try:
            # First ensure it's positive
            decimal_value = ValidationRules.validate_positive(value, field_name)
            
            # Check maximum if provided
            if max_amount is not None and decimal_value > max_amount:
                error_msg = (
                    f"{field_name} exceeds maximum ({max_amount}), "
                    f"got {decimal_value}"
                )
                logger.error(f"Validation error: {error_msg}")
                raise ValueError(error_msg)
            
            return decimal_value
            
        except ValueError as e:
            logger.error(f"Amount validation failed for {field_name}: {e}")
            raise


# =============================================================================
# TYPE-SAFE CONFIGURATION WRAPPER
# =============================================================================

class TypeSafeConfig:
    """
    Type-safe configuration wrapper with automatic type normalization.
    
    Converts all numeric values to Decimal for consistency and provides
    safe access methods with comprehensive error handling.
    """
    
    def __init__(self, config_dict: Dict[str, Any]):
        """
        Initialize with a configuration dictionary.
        
        Args:
            config_dict: Raw configuration dictionary
            
        Raises:
            ImportError: If TypeConverter is not available
            ValueError: If configuration cannot be normalized
        """
        if not TYPE_CONVERTER_AVAILABLE:
            error_msg = (
                "TypeConverter not available. Cannot create TypeSafeConfig. "
                "Ensure paper_trading.utils.type_utils is installed."
            )
            logger.error(error_msg)
            raise ImportError(error_msg)
        
        # Create a single TypeConverter instance for efficiency
        self._converter = TypeConverter()
        
        # Normalize the configuration
        try:
            self._config = self._normalize_types(config_dict)
            logger.info(
                f"TypeSafeConfig initialized with {len(self._config)} top-level keys"
            )
        except Exception as e:
            error_msg = f"Failed to normalize configuration: {e}"
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg) from e
    
    def _normalize_types(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively normalize all numeric types in configuration.
        
        Args:
            config_dict: Raw configuration dictionary
            
        Returns:
            Configuration with normalized types
            
        Raises:
            ValueError: If normalization fails
        """
        if not isinstance(config_dict, dict):
            logger.error(f"Expected dict, got {type(config_dict)}")
            raise ValueError(f"Config must be a dictionary, got {type(config_dict)}")
        
        normalized = {}
        
        for key, value in config_dict.items():
            try:
                if isinstance(value, dict):
                    # Recursively normalize nested dictionaries
                    normalized[key] = self._normalize_types(value)
                    logger.debug(f"Normalized nested dict for key: {key}")
                    
                elif isinstance(value, (list, tuple)):
                    # Handle lists/tuples by normalizing each element
                    original_type = type(value)
                    normalized_list = [
                        self._normalize_value(v) for v in value
                    ]
                    normalized[key] = original_type(normalized_list)
                    logger.debug(
                        f"Normalized {original_type.__name__} for key: {key} "
                        f"with {len(normalized_list)} elements"
                    )
                    
                else:
                    # Normalize individual values
                    normalized[key] = self._normalize_value(value)
                    logger.debug(f"Normalized value for key: {key}")
                    
            except Exception as e:
                logger.error(
                    f"Error normalizing config key '{key}' with value {value}: {e}"
                )
                # Keep original value on error to avoid data loss
                normalized[key] = value
                
        return normalized
    
    def _normalize_value(self, value: Any) -> Any:
        """
        Normalize a single value based on its type.
        
        Args:
            value: Value to normalize
            
        Returns:
            Normalized value (Decimal for numbers, original for others)
        """
        # Don't convert strings, booleans, or None
        if isinstance(value, (str, bool)) or value is None:
            return value
        
        # Already a Decimal - return as-is
        if isinstance(value, Decimal):
            return value
        
        # Convert numeric types to Decimal for consistency
        if isinstance(value, (int, float)):
            try:
                converted = self._converter.to_decimal(value)
                logger.debug(
                    f"Converted {type(value).__name__} {value} to Decimal: {converted}"
                )
                return converted
            except Exception as e:
                logger.warning(
                    f"Failed to convert {value} to Decimal: {e}. "
                    f"Keeping original value."
                )
                return value
        
        # For any other type, return as-is
        logger.debug(f"Skipping normalization for type: {type(value).__name__}")
        return value
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value with optional default.
        
        Args:
            key: Configuration key (supports dot notation for nested keys)
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        # Support dot notation for nested keys (e.g., "trading.max_position_size")
        if '.' in key:
            keys = key.split('.')
            value = self._config
            
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    logger.debug(f"Key '{key}' not found, returning default: {default}")
                    return default
            
            logger.debug(f"Retrieved nested key '{key}': {value}")
            return value
        
        # Simple key lookup
        result = self._config.get(key, default)
        logger.debug(f"Retrieved key '{key}': {result}")
        return result
    
    def __getattr__(self, name: str) -> Any:
        """
        Allow attribute-style access to configuration.
        
        Args:
            name: Attribute name
            
        Returns:
            Configuration value
            
        Raises:
            AttributeError: If attribute not found
        """
        # Avoid recursion on special attributes
        if name.startswith('_'):
            raise AttributeError(f"Private attribute '{name}' not accessible")
        
        if name in self._config:
            value = self._config[name]
            logger.debug(f"Accessed config attribute '{name}': {value}")
            return value
        
        error_msg = f"Configuration has no attribute '{name}'"
        logger.warning(error_msg)
        raise AttributeError(error_msg)
    
    def __getitem__(self, key: str) -> Any:
        """
        Allow dictionary-style access to configuration.
        
        Args:
            key: Configuration key
            
        Returns:
            Configuration value
            
        Raises:
            KeyError: If key not found
        """
        if key in self._config:
            return self._config[key]
        
        error_msg = f"Configuration key '{key}' not found"
        logger.warning(error_msg)
        raise KeyError(error_msg)
    
    def keys(self) -> List[str]:
        """
        Get all configuration keys.
        
        Returns:
            List of configuration keys
        """
        return list(self._config.keys())
    
    def items(self) -> List[Tuple[str, Any]]:
        """
        Get all configuration items.
        
        Returns:
            List of (key, value) tuples
        """
        return list(self._config.items())
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Get the configuration as a plain dictionary.
        
        Returns:
            Configuration dictionary (copy)
        """
        return self._config.copy()