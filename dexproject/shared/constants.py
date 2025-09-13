"""
Shared constants for the DEX project.

This module contains common constants used across multiple Django apps
to reduce duplication and ensure consistency.
"""

# =============================================================================
# COMMON MODEL CHOICES
# =============================================================================

# Common choices for models
RISK_LEVELS = [
    ('LOW', 'Low'),
    ('MEDIUM', 'Medium'),
    ('HIGH', 'High'),
    ('CRITICAL', 'Critical'),
]

STATUS_CHOICES = [
    ('ACTIVE', 'Active'),
    ('INACTIVE', 'Inactive'),
    ('PENDING', 'Pending'),
    ('COMPLETED', 'Completed'),
    ('FAILED', 'Failed'),
    ('ERROR', 'Error'),
]

# Trading status choices
TRADING_STATUS_CHOICES = [
    ('OPEN', 'Open'),
    ('CLOSED', 'Closed'),
    ('CANCELLED', 'Cancelled'),
    ('PARTIAL', 'Partial'),
    ('REJECTED', 'Rejected'),
]

# Transaction status choices
TRANSACTION_STATUS_CHOICES = [
    ('PENDING', 'Pending'),
    ('SUBMITTED', 'Submitted'),
    ('CONFIRMED', 'Confirmed'),
    ('FAILED', 'Failed'),
    ('CANCELLED', 'Cancelled'),
    ('REPLACED', 'Replaced'),
]

# =============================================================================
# FIELD LENGTHS AND CONSTRAINTS
# =============================================================================

# Common field lengths
SHORT_TEXT_LENGTH = 100
MEDIUM_TEXT_LENGTH = 255
LONG_TEXT_LENGTH = 500
ADDRESS_LENGTH = 42  # Ethereum address length
HASH_LENGTH = 66     # Ethereum transaction hash length
SYMBOL_LENGTH = 20   # Token symbol length
NAME_LENGTH = 100    # Token name length

# Decimal precision settings
DECIMAL_PLACES = 18
MAX_DIGITS = 32
PRICE_DECIMAL_PLACES = 8
PRICE_MAX_DIGITS = 20

# =============================================================================
# VALIDATION PATTERNS
# =============================================================================

# Common regex patterns
ETHEREUM_ADDRESS_PATTERN = r'^0x[a-fA-F0-9]{40}$'
TRANSACTION_HASH_PATTERN = r'^0x[a-fA-F0-9]{64}$'
BLOCK_HASH_PATTERN = r'^0x[a-fA-F0-9]{64}$'
PRIVATE_KEY_PATTERN = r'^0x[a-fA-F0-9]{64}$'

# =============================================================================
# TIMEOUT SETTINGS
# =============================================================================

# Default timeouts (in seconds)
DEFAULT_TIMEOUT_SECONDS = 30
LONG_TIMEOUT_SECONDS = 60
SHORT_TIMEOUT_SECONDS = 10
VERY_SHORT_TIMEOUT_SECONDS = 5

# Trading specific timeouts
RISK_ASSESSMENT_TIMEOUT = 30
TRADE_EXECUTION_TIMEOUT = 60
WALLET_OPERATION_TIMEOUT = 45
PRICE_FETCH_TIMEOUT = 15

# =============================================================================
# REDIS CONFIGURATION
# =============================================================================

# Redis Channels for pub/sub communication between Engine and Django
REDIS_CHANNELS = {
    # Engine to Django channels
    'pair_discovery': 'dex:pair_discovery',
    'fast_risk_complete': 'dex:fast_risk_complete',
    'trading_decision': 'dex:trading_decision',
    'trade_execution': 'dex:trade_execution',
    'engine_status': 'dex:engine_status',
    'engine_alerts': 'dex:engine_alerts',
    
    # Django to Engine channels
    'comprehensive_risk_complete': 'dex:comprehensive_risk_complete',
    'trading_config_update': 'dex:trading_config_update',
    'emergency_stop': 'dex:emergency_stop',
    'risk_profile_update': 'dex:risk_profile_update',
}

# Redis Keys for caching and data storage
REDIS_KEYS = {
    'engine_status': 'dex:engine_status',
    'risk_cache': 'dex:risk_cache',
    'price_cache': 'dex:price_cache',
    'trade_cache': 'dex:trade_cache',
    'pair_cache': 'dex:pair_cache',
    'wallet_cache': 'dex:wallet_cache',
    'gas_cache': 'dex:gas_cache',
    'config_cache': 'dex:config_cache',
}

# Helper function to get Redis channel by message type
def get_redis_channel(message_type: str) -> str:
    """
    Get Redis channel name for a message type.
    
    Args:
        message_type: Type of message (e.g., 'pair_discovery', 'trading_decision')
        
    Returns:
        Redis channel name
        
    Raises:
        KeyError: If message type is not found
    """
    if message_type not in REDIS_CHANNELS:
        raise KeyError(f"Unknown message type: {message_type}")
    
    return REDIS_CHANNELS[message_type]

# =============================================================================
# TRADING CONFIGURATION
# =============================================================================

# Trading modes
TRADING_MODES = [
    ('PAPER', 'Paper Trading'),
    ('LIVE', 'Live Trading'),
]

# Execution lanes
EXECUTION_LANES = [
    ('FAST', 'Fast Lane'),
    ('SMART', 'Smart Lane'),
]

# Order types
ORDER_TYPES = [
    ('MARKET', 'Market Order'),
    ('LIMIT', 'Limit Order'),
    ('STOP_LOSS', 'Stop Loss'),
    ('TAKE_PROFIT', 'Take Profit'),
]

# Trade types
TRADE_TYPES = [
    ('BUY', 'Buy'),
    ('SELL', 'Sell'),
]

# Position types
POSITION_TYPES = [
    ('LONG', 'Long'),
    ('SHORT', 'Short'),
]

# Risk assessment results
RISK_ASSESSMENT_RESULTS = [
    ('SAFE', 'Safe to Trade'),
    ('CAUTION', 'Trade with Caution'),
    ('WARNING', 'High Risk - Warning'),
    ('BLOCKED', 'Blocked - Do Not Trade'),
]

# Strategy types
STRATEGY_TYPES = [
    ('ARBITRAGE', 'Arbitrage'),
    ('MARKET_MAKING', 'Market Making'),
    ('TREND_FOLLOWING', 'Trend Following'),
    ('MEAN_REVERSION', 'Mean Reversion'),
    ('MOMENTUM', 'Momentum'),
    ('SCALPING', 'Scalping'),
]

# =============================================================================
# BLOCKCHAIN AND DEX CONFIGURATION
# =============================================================================

# Supported blockchain networks
SUPPORTED_CHAINS = {
    1: 'Ethereum',
    8453: 'Base',
    42161: 'Arbitrum',
    137: 'Polygon',
    56: 'BSC',
    43114: 'Avalanche',
    # Testnets
    11155111: 'Sepolia',
    84532: 'Base Sepolia',
    421614: 'Arbitrum Sepolia',
    80001: 'Polygon Mumbai',
}

# DEX types
DEX_TYPES = [
    ('uniswap_v2', 'Uniswap V2'),
    ('uniswap_v3', 'Uniswap V3'),
    ('sushiswap', 'SushiSwap'),
    ('pancakeswap', 'PancakeSwap'),
    ('quickswap', 'QuickSwap'),
    ('traderjoe', 'Trader Joe'),
]

# Wallet types
WALLET_TYPES = [
    ('HOT', 'Hot Wallet'),
    ('COLD', 'Cold Wallet'),
    ('HARDWARE', 'Hardware Wallet'),
    ('MULTISIG', 'Multisig Wallet'),
    ('SYSTEM', 'System Wallet'),
]

# =============================================================================
# ERROR CODES AND MESSAGES
# =============================================================================

# Error codes for standardized error handling
ERROR_CODES = {
    # Network errors (1000-1099)
    'NETWORK_ERROR': 1001,
    'RPC_ERROR': 1002,
    'TIMEOUT_ERROR': 1003,
    'CONNECTION_ERROR': 1004,
    
    # Wallet errors (1100-1199)
    'INSUFFICIENT_BALANCE': 1101,
    'WALLET_NOT_AVAILABLE': 1102,
    'PRIVATE_KEY_ERROR': 1103,
    'WALLET_LOCKED': 1104,
    
    # Transaction errors (1200-1299)
    'GAS_PRICE_TOO_HIGH': 1201,
    'TRANSACTION_FAILED': 1202,
    'NONCE_ERROR': 1203,
    'SLIPPAGE_TOO_HIGH': 1204,
    
    # Risk errors (2000-2099)
    'HONEYPOT_DETECTED': 2001,
    'HIGH_RISK_TOKEN': 2002,
    'LIQUIDITY_TOO_LOW': 2003,
    'OWNERSHIP_RISK': 2004,
    'TAX_TOO_HIGH': 2005,
    'CONTRACT_NOT_VERIFIED': 2006,
    
    # API errors (4000-4099)
    'RATE_LIMITED': 4001,
    'API_ERROR': 4002,
    'AUTHENTICATION_ERROR': 4003,
    'PERMISSION_DENIED': 4004,
}

# Error messages corresponding to error codes
ERROR_MESSAGES = {
    1001: 'Network connection error occurred',
    1002: 'RPC endpoint error',
    1003: 'Operation timed out',
    1004: 'Connection failed',
    1101: 'Insufficient wallet balance for transaction',
    1102: 'Trading wallet not available or locked',
    1103: 'Private key error - cannot sign transaction',
    1104: 'Wallet is locked',
    1201: 'Gas price exceeds maximum allowed limit',
    1202: 'Transaction execution failed',
    1203: 'Transaction nonce error',
    1204: 'Slippage tolerance exceeded',
    2001: 'Honeypot token detected - trading blocked',
    2002: 'High-risk token - trading not recommended',
    2003: 'Liquidity too low for safe trading',
    2004: 'Token ownership structure presents risks',
    2005: 'Token taxes exceed acceptable limits',
    2006: 'Contract not verified - potential risk',
    4001: 'Rate limit exceeded - please wait',
    4002: 'External API error',
    4003: 'Authentication failed',
    4004: 'Permission denied',
}

def get_error_message(error_code: int) -> str:
    """
    Get human-readable error message for error code.
    
    Args:
        error_code: Numeric error code
        
    Returns:
        Human-readable error message
    """
    return ERROR_MESSAGES.get(error_code, f'Unknown error code: {error_code}')

# =============================================================================
# PERFORMANCE AND MONITORING
# =============================================================================

# Performance thresholds (in milliseconds)
PERFORMANCE_THRESHOLDS = {
    'fast_lane_execution': 500,
    'smart_lane_execution': 5000,
    'risk_assessment': 3000,
    'price_fetch': 1000,
    'wallet_balance': 2000,
    'gas_estimation': 1500,
    'database_query': 100,
    'redis_operation': 50,
}

# Health check intervals (in seconds)
HEALTH_CHECK_INTERVALS = {
    'engine_status': 30,
    'wallet_balance': 60,
    'gas_prices': 30,
    'rpc_connectivity': 45,
    'redis_connectivity': 15,
    'database_connectivity': 60,
}

# =============================================================================
# NOTIFICATION AND ALERT TYPES
# =============================================================================

ALERT_TYPES = [
    ('INFO', 'Information'),
    ('SUCCESS', 'Success'),
    ('WARNING', 'Warning'),
    ('ERROR', 'Error'),
    ('CRITICAL', 'Critical'),
]

NOTIFICATION_TYPES = [
    ('TRADE_EXECUTED', 'Trade Executed'),
    ('RISK_ALERT', 'Risk Alert'),
    ('SYSTEM_STATUS', 'System Status'),
    ('BALANCE_LOW', 'Low Balance'),
    ('ERROR_OCCURRED', 'Error Occurred'),
    ('POSITION_OPENED', 'Position Opened'),
    ('POSITION_CLOSED', 'Position Closed'),
    ('STOP_LOSS_TRIGGERED', 'Stop Loss Triggered'),
    ('TAKE_PROFIT_HIT', 'Take Profit Hit'),
]

# =============================================================================
# DEFAULT VALUES AND LIMITS
# =============================================================================

# Default trading parameters
DEFAULT_SLIPPAGE_TOLERANCE = 0.05  # 5%
DEFAULT_GAS_LIMIT = 200000
DEFAULT_GAS_PRICE_MULTIPLIER = 1.1  # 10% above base
DEFAULT_TRADE_AMOUNT_ETH = 0.01  # 0.01 ETH
DEFAULT_POSITION_SIZE_PERCENT = 0.1  # 10% of portfolio

# Risk management defaults
DEFAULT_STOP_LOSS_PERCENT = 0.1  # 10% loss
DEFAULT_TAKE_PROFIT_PERCENT = 0.2  # 20% profit
DEFAULT_MAX_DRAWDOWN_PERCENT = 0.05  # 5% portfolio drawdown
DEFAULT_RISK_SCORE_THRESHOLD = 70  # Out of 100

# Portfolio limits
MAX_OPEN_POSITIONS = 10
MAX_DAILY_TRADES = 100
MAX_POSITION_SIZE_PERCENT = 0.2  # 20% of portfolio
MIN_TRADE_AMOUNT_USD = 10

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_chain_name(chain_id: int) -> str:
    """
    Get chain name from chain ID.
    
    Args:
        chain_id: Blockchain chain ID
        
    Returns:
        Chain name or 'Unknown'
    """
    return SUPPORTED_CHAINS.get(chain_id, f'Unknown Chain ({chain_id})')

def is_testnet(chain_id: int) -> bool:
    """
    Check if chain ID is a testnet.
    
    Args:
        chain_id: Blockchain chain ID
        
    Returns:
        True if testnet, False if mainnet
    """
    testnet_chains = {11155111, 84532, 421614, 80001}
    return chain_id in testnet_chains

def is_mainnet(chain_id: int) -> bool:
    """
    Check if chain ID is a mainnet.
    
    Args:
        chain_id: Blockchain chain ID
        
    Returns:
        True if mainnet, False if testnet
    """
    return not is_testnet(chain_id)

def format_address(address: str, length: int = 10) -> str:
    """
    Format Ethereum address for display.
    
    Args:
        address: Full Ethereum address
        length: Number of characters to show from start/end
        
    Returns:
        Formatted address (e.g., "0x1234...7890")
    """
    if not address or len(address) < 10:
        return address
    
    return f"{address[:length]}...{address[-4:]}"

def format_hash(tx_hash: str, length: int = 10) -> str:
    """
    Format transaction hash for display.
    
    Args:
        tx_hash: Full transaction hash
        length: Number of characters to show from start
        
    Returns:
        Formatted hash (e.g., "0x1234567...")
    """
    if not tx_hash or len(tx_hash) < 10:
        return tx_hash
    
    return f"{tx_hash[:length]}..."

def validate_ethereum_address(address: str) -> bool:
    """
    Validate Ethereum address format.
    
    Args:
        address: Address to validate
        
    Returns:
        True if valid format, False otherwise
    """
    import re
    return bool(re.match(ETHEREUM_ADDRESS_PATTERN, address))

def validate_transaction_hash(tx_hash: str) -> bool:
    """
    Validate transaction hash format.
    
    Args:
        tx_hash: Transaction hash to validate
        
    Returns:
        True if valid format, False otherwise
    """
    import re
    return bool(re.match(TRANSACTION_HASH_PATTERN, tx_hash))

def get_risk_level_color(risk_level: str) -> str:
    """
    Get color code for risk level display.
    
    Args:
        risk_level: Risk level string
        
    Returns:
        CSS color class or hex color
    """
    colors = {
        'LOW': '#28a745',      # Green
        'MEDIUM': '#ffc107',   # Yellow
        'HIGH': '#fd7e14',     # Orange
        'CRITICAL': '#dc3545', # Red
    }
    return colors.get(risk_level.upper(), '#6c757d')  # Default gray

def get_status_color(status: str) -> str:
    """
    Get color code for status display.
    
    Args:
        status: Status string
        
    Returns:
        CSS color class or hex color
    """
    colors = {
        'ACTIVE': '#28a745',     # Green
        'COMPLETED': '#28a745',  # Green
        'PENDING': '#ffc107',    # Yellow
        'FAILED': '#dc3545',     # Red
        'ERROR': '#dc3545',      # Red
        'CANCELLED': '#6c757d',  # Gray
        'INACTIVE': '#6c757d',   # Gray
    }
    return colors.get(status.upper(), '#6c757d')  # Default gray