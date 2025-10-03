"""
Production configuration for type safety and consistency.

File: dexproject/paper_trading/config/type_config.py
"""

from decimal import Decimal, getcontext
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class TypeConfig:
    """
    Centralized type configuration for the trading system.
    """
    
    # Set decimal precision for the entire application
    DECIMAL_PRECISION = 18  # Matches Ethereum's wei precision
    DISPLAY_PRECISION = 8   # For UI display
    USD_PRECISION = 2       # For USD amounts
    
    # Decimal context settings
    @staticmethod
    def setup_decimal_context():
        """
        Configure decimal context for production use.
        
        This should be called once at application startup.
        """
        # Set precision high enough for crypto calculations
        getcontext().prec = 28
        
        # Set rounding mode to banker's rounding (reduces bias)
        getcontext().rounding = ROUND_HALF_EVEN
        
        # Enable traps for important errors
        getcontext().traps[InvalidOperation] = True
        getcontext().traps[DivisionByZero] = True
        getcontext().traps[Overflow] = True
        
        logger.info("Decimal context configured for production")
    
    @staticmethod
    def get_field_types() -> Dict[str, type]:
        """
        Define expected types for all numeric fields.
        
        Returns:
            Dictionary mapping field names to their expected types
        """
        return {
            # Price fields - always Decimal for accuracy
            'price': Decimal,
            'entry_price': Decimal,
            'exit_price': Decimal,
            'current_price': Decimal,
            'average_price': Decimal,
            
            # Amount fields - always Decimal
            'amount': Decimal,
            'quantity': Decimal,
            'balance': Decimal,
            'position_size': Decimal,
            'position_size_usd': Decimal,
            
            # Percentage fields - always Decimal
            'confidence': Decimal,
            'risk_score': Decimal,
            'opportunity_score': Decimal,
            'slippage': Decimal,
            'fee_percent': Decimal,
            
            # Gas fields - can be int or Decimal
            'gas_price': Decimal,
            'gas_limit': int,
            'gas_used': int,
            
            # Time fields - int
            'timestamp': int,
            'block_number': int,
            'execution_time_ms': int,
        }


class ValidationRules:
    """
    Validation rules for numeric fields.
    """
    
    @staticmethod
    def validate_percentage(value: Decimal, field_name: str = "percentage") -> Decimal:
        """
        Validate that a value is a valid percentage (0-100).
        
        Args:
            value: Value to validate
            field_name: Name of field for error messages
            
        Returns:
            Validated value
            
        Raises:
            ValueError: If value is not valid
        """
        if value < Decimal('0') or value > Decimal('100'):
            raise ValueError(f"{field_name} must be between 0 and 100, got {value}")
        return value
    
    @staticmethod
    def validate_positive(value: Decimal, field_name: str = "value") -> Decimal:
        """
        Validate that a value is positive.
        
        Args:
            value: Value to validate
            field_name: Name of field for error messages
            
        Returns:
            Validated value
            
        Raises:
            ValueError: If value is not positive
        """
        if value <= Decimal('0'):
            raise ValueError(f"{field_name} must be positive, got {value}")
        return value
    
    @staticmethod
    def validate_price(value: Decimal, field_name: str = "price") -> Decimal:
        """
        Validate that a price is realistic.
        
        Args:
            value: Price to validate
            field_name: Name of field for error messages
            
        Returns:
            Validated price
            
        Raises:
            ValueError: If price is not realistic
        """
        # Prices should be positive and not absurdly high
        MAX_PRICE = Decimal('1000000000')  # $1 billion max
        
        if value <= Decimal('0'):
            raise ValueError(f"{field_name} must be positive, got {value}")
        
        if value > MAX_PRICE:
            raise ValueError(f"{field_name} exceeds maximum ({MAX_PRICE}), got {value}")
            
        return value


class TypeSafeConfig:
    """
    Type-safe configuration wrapper.
    """
    
    def __init__(self, config_dict: Dict[str, Any]):
        """
        Initialize with a configuration dictionary.
        
        Args:
            config_dict: Raw configuration dictionary
        """
        self._config = self._normalize_types(config_dict)
    
    def _normalize_types(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize all numeric types in configuration.
        
        Args:
            config_dict: Raw configuration
            
        Returns:
            Configuration with normalized types
        """
        from paper_trading.utils.type_utils import TypeConverter
        
        converter = TypeConverter()
        normalized = {}
        
        for key, value in config_dict.items():
            if isinstance(value, dict):
                # Recursively normalize nested dictionaries
                normalized[key] = self._normalize_types(value)
            elif isinstance(value, (list, tuple)):
                # Handle lists/tuples
                normalized[key] = type(value)(
                    self._normalize_value(v) for v in value
                )
            else:
                # Normalize individual values
                normalized[key] = self._normalize_value(value)
                
        return normalized
    
    def _normalize_value(self, value: Any) -> Any:
        """
        Normalize a single value based on its content.
        
        Args:
            value: Value to normalize
            
        Returns:
            Normalized value
        """
        from paper_trading.utils.type_utils import TypeConverter
        
        converter = TypeConverter()
        
        # Don't convert strings, booleans, None
        if isinstance(value, (str, bool)) or value is None:
            return value
            
        # Convert numeric types to Decimal for consistency
        if isinstance(value, (int, float)):
            return converter.to_decimal(value)
            
        return value
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        return self._config.get(key, default)
    
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
        if name in self._config:
            return self._config[name]
        raise AttributeError(f"Configuration has no attribute '{name}'")