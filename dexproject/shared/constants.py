"""
Shared constants for the DEX trading bot system.

This module contains Redis channel names, cache keys, and other constants
used for communication between the Django backend and async engine.

File: dexproject/shared/constants.py
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# =============================================================================
# REDIS CHANNELS FOR PUB/SUB COMMUNICATION
# =============================================================================

REDIS_CHANNELS = {
    # Engine → Django messages
    'pair_discovery': 'dex_bot_pair_discovery',
    'fast_risk_complete': 'dex_bot_fast_risk_complete', 
    'trading_decision': 'dex_bot_trading_decision',
    'trade_execution': 'dex_bot_trade_execution',
    'engine_status': 'dex_bot_engine_status',
    'engine_alerts': 'dex_bot_engine_alerts',
    'engine_heartbeat': 'dex_bot_engine_heartbeat',
    
    # Django → Engine messages  
    'comprehensive_risk_complete': 'dex_bot_comprehensive_risk_complete',
    'trading_config_update': 'dex_bot_trading_config_update',
    'emergency_stop': 'dex_bot_emergency_stop',
    'risk_profile_update': 'dex_bot_risk_profile_update',
    'pair_whitelist_update': 'dex_bot_pair_whitelist_update',
    'pair_blacklist_update': 'dex_bot_pair_blacklist_update',
    
    # Bidirectional coordination
    'system_status': 'dex_bot_system_status',
    'health_check': 'dex_bot_health_check',
}

# =============================================================================
# REDIS CACHE KEYS
# =============================================================================

REDIS_KEYS = {
    # Engine status and health
    'engine_status': 'dex_bot:engine:status',
    'engine_heartbeat': 'dex_bot:engine:heartbeat',
    'engine_config': 'dex_bot:engine:config',
    
    # Risk assessment caching
    'risk_cache': 'dex_bot:risk:token',
    'pair_risk_cache': 'dex_bot:risk:pair', 
    'fast_risk_results': 'dex_bot:risk:fast_results',
    'comprehensive_risk_results': 'dex_bot:risk:comprehensive_results',
    
    # Price and market data caching
    'price_cache': 'dex_bot:price:token',
    'pair_cache': 'dex_bot:pairs:info',
    'market_data': 'dex_bot:market:data',
    
    # Trading and execution
    'trade_history': 'dex_bot:trades:history',
    'position_cache': 'dex_bot:positions',
    'portfolio_status': 'dex_bot:portfolio:status',
    
    # Configuration and settings
    'chain_config': 'dex_bot:config:chains',
    'dex_config': 'dex_bot:config:dexes',
    'rpc_status': 'dex_bot:rpc:status',
    'trading_pairs': 'dex_bot:config:trading_pairs',
    
    # Blacklists and whitelists
    'token_blacklist': 'dex_bot:blacklist:tokens',
    'pair_blacklist': 'dex_bot:blacklist:pairs', 
    'token_whitelist': 'dex_bot:whitelist:tokens',
    'pair_whitelist': 'dex_bot:whitelist:pairs',
    
    # Performance metrics
    'metrics': 'dex_bot:metrics',
    'alerts': 'dex_bot:alerts',
    'logs': 'dex_bot:logs',
}

# =============================================================================
# MESSAGE TYPES FOR TYPE SAFETY
# =============================================================================

MESSAGE_TYPES = {
    # Engine → Django
    'NEW_PAIR_DISCOVERED': 'new_pair_discovered',
    'FAST_RISK_COMPLETE': 'fast_risk_complete',
    'TRADING_DECISION': 'trading_decision', 
    'EXECUTION_COMPLETE': 'execution_complete',
    'ENGINE_STATUS': 'engine_status',
    'ENGINE_HEARTBEAT': 'engine_heartbeat',
    'ALERT_TRIGGERED': 'alert_triggered',
    
    # Django → Engine
    'COMPREHENSIVE_RISK_COMPLETE': 'comprehensive_risk_complete',
    'CONFIG_UPDATE': 'config_update',
    'EMERGENCY_STOP': 'emergency_stop',
    'RISK_PROFILE_UPDATE': 'risk_profile_update',
    'WHITELIST_UPDATE': 'whitelist_update',
    'BLACKLIST_UPDATE': 'blacklist_update',
}

# =============================================================================
# DJANGO MODEL CONSTANTS
# =============================================================================

# Risk levels used across the system
RISK_LEVELS = [
    ('MINIMAL', 'Minimal'),
    ('LOW', 'Low'),
    ('MEDIUM', 'Medium'),
    ('HIGH', 'High'),
    ('CRITICAL', 'Critical'),
]

# Status choices for various models
STATUS_CHOICES = [
    ('ACTIVE', 'Active'),
    ('INACTIVE', 'Inactive'),
    ('PENDING', 'Pending'),
    ('COMPLETED', 'Completed'),
    ('FAILED', 'Failed'),
    ('ERROR', 'Error'),
]

# Trading decision types
DECISION_TYPES = [
    ('BUY', 'Buy'),
    ('SELL', 'Sell'),
    ('HOLD', 'Hold'),
    ('SKIP', 'Skip'),
]

# =============================================================================
# FIELD LENGTHS AND CONSTRAINTS
# =============================================================================

# Common field lengths for Django models
SHORT_TEXT_LENGTH = 100
MEDIUM_TEXT_LENGTH = 255
LONG_TEXT_LENGTH = 500
ADDRESS_LENGTH = 42  # Ethereum address length
HASH_LENGTH = 66     # Ethereum transaction hash length

# Decimal precision settings
DECIMAL_PLACES = 18
MAX_DIGITS = 32

# =============================================================================
# REGEX PATTERNS
# =============================================================================

# Ethereum address and transaction hash patterns
ETHEREUM_ADDRESS_PATTERN = r'^0x[a-fA-F0-9]{40}$'
TRANSACTION_HASH_PATTERN = r'^0x[a-fA-F0-9]{64}$'

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_redis_channel(message_type: str) -> Optional[str]:
    """
    Get Redis channel name for a message type.
    
    Args:
        message_type: Type of message (from MESSAGE_TYPES)
        
    Returns:
        Redis channel name or None if not found
    """
    # Map message types to channels
    message_to_channel = {
        # Engine → Django
        MESSAGE_TYPES['NEW_PAIR_DISCOVERED']: REDIS_CHANNELS['pair_discovery'],
        MESSAGE_TYPES['FAST_RISK_COMPLETE']: REDIS_CHANNELS['fast_risk_complete'],
        MESSAGE_TYPES['TRADING_DECISION']: REDIS_CHANNELS['trading_decision'],
        MESSAGE_TYPES['EXECUTION_COMPLETE']: REDIS_CHANNELS['trade_execution'],
        MESSAGE_TYPES['ENGINE_STATUS']: REDIS_CHANNELS['engine_status'],
        MESSAGE_TYPES['ENGINE_HEARTBEAT']: REDIS_CHANNELS['engine_heartbeat'],
        MESSAGE_TYPES['ALERT_TRIGGERED']: REDIS_CHANNELS['engine_alerts'],
        
        # Django → Engine  
        MESSAGE_TYPES['COMPREHENSIVE_RISK_COMPLETE']: REDIS_CHANNELS['comprehensive_risk_complete'],
        MESSAGE_TYPES['CONFIG_UPDATE']: REDIS_CHANNELS['trading_config_update'],
        MESSAGE_TYPES['EMERGENCY_STOP']: REDIS_CHANNELS['emergency_stop'],
        MESSAGE_TYPES['RISK_PROFILE_UPDATE']: REDIS_CHANNELS['risk_profile_update'],
        MESSAGE_TYPES['WHITELIST_UPDATE']: REDIS_CHANNELS['pair_whitelist_update'],
        MESSAGE_TYPES['BLACKLIST_UPDATE']: REDIS_CHANNELS['pair_blacklist_update'],
    }
    
    return message_to_channel.get(message_type)

def get_redis_key(key_type: str, identifier: str = None) -> str:
    """
    Generate Redis key with optional identifier.
    
    Args:
        key_type: Type of key (from REDIS_KEYS)
        identifier: Optional identifier to append
        
    Returns:
        Complete Redis key
    """
    base_key = REDIS_KEYS.get(key_type, f'dex_bot:unknown:{key_type}')
    
    if identifier:
        return f"{base_key}:{identifier}"
    
    return base_key

def validate_ethereum_address(address: str) -> bool:
    """
    Validate Ethereum address format.
    
    Args:
        address: Address string to validate
        
    Returns:
        True if valid Ethereum address format
    """
    import re
    return bool(re.match(ETHEREUM_ADDRESS_PATTERN, address))

def validate_transaction_hash(tx_hash: str) -> bool:
    """
    Validate transaction hash format.
    
    Args:
        tx_hash: Transaction hash to validate
        
    Returns:
        True if valid transaction hash format  
    """
    import re
    return bool(re.match(TRANSACTION_HASH_PATTERN, tx_hash))

# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# Default timeouts and intervals
DEFAULT_REDIS_TIMEOUT = 5.0
DEFAULT_RPC_TIMEOUT = 10.0
DEFAULT_HEALTH_CHECK_INTERVAL = 30
DEFAULT_HEARTBEAT_INTERVAL = 10

# Cache TTL values (in seconds)
CACHE_TTL = {
    'risk_fast': 300,           # 5 minutes
    'risk_comprehensive': 3600, # 1 hour
    'price_data': 60,          # 1 minute
    'pair_info': 1800,         # 30 minutes
    'engine_status': 300,      # 5 minutes
    'chain_config': 3600,      # 1 hour
}

# Rate limiting
RATE_LIMITS = {
    'rpc_requests_per_second': 10,
    'redis_operations_per_second': 100,
    'risk_assessments_per_minute': 60,
    'trade_executions_per_minute': 10,
}

logger.info("Shared constants loaded successfully")