"""
Shared constants and configuration values for the DEX auto-trading bot.

This module contains constants used across both the async engine
and the Django backend for consistency and maintainability.
"""

import logging
from decimal import Decimal
from typing import Dict, List


logger = logging.getLogger(__name__)


# =============================================================================
# BLOCKCHAIN CONSTANTS (Matches your existing engine/config.py)
# =============================================================================

CHAIN_IDS = {
    'ethereum': 1,
    'base': 8453,
    'polygon': 137,
    'bsc': 56,
    'arbitrum': 42161,
    'optimism': 10,
}

CHAIN_NAMES = {v: k for k, v in CHAIN_IDS.items()}

# Native tokens for each chain
NATIVE_TOKENS = {
    1: 'ETH',      # Ethereum
    8453: 'ETH',   # Base
    137: 'MATIC',  # Polygon
    56: 'BNB',     # BSC
    42161: 'ETH',  # Arbitrum
    10: 'ETH',     # Optimism
}

# Wrapped native token addresses (from your engine config)
WRAPPED_NATIVE = {
    1: '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',      # WETH
    8453: '0x4200000000000000000000000000000000000006',    # WETH (Base)
    137: '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270',    # WMATIC
    56: '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c',     # WBNB
    42161: '0x82aF49447D8a07e3bd95BD0d56f35241523fBab1',  # WETH (Arbitrum)
    10: '0x4200000000000000000000000000000000000006',     # WETH (Optimism)
}

# Stable coin addresses for price reference (from your engine config)
STABLECOINS = {
    1: {
        'USDC': '0xA0b86a33E6E67c6e2B2EB44630b58cf95e5e7d77',
        'USDT': '0xdAC17F958D2ee523a2206206994597C13D831ec7',
        'DAI': '0x6B175474E89094C44Da98b954EedeAC495271d0F',
    },
    8453: {  # Base
        'USDC': '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
        'USDT': '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb',
        'DAI': '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb',
    },
    137: {
        'USDC': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',
        'USDT': '0xc2132D05D31c914a87C6611C10748AEb04B58e8F',
        'DAI': '0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063',
    },
}


# =============================================================================
# DEX CONSTANTS (From your existing setup)
# =============================================================================

# Supported DEX protocols
SUPPORTED_DEXES = {
    'uniswap_v2': {
        'name': 'Uniswap V2',
        'chains': [1],
        'factory': '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',
        'router': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
        'fee_tiers': [3000],  # 0.3%
    },
    'uniswap_v3': {
        'name': 'Uniswap V3',
        'chains': [1, 8453],
        'factories': {
            1: '0x1F98431c8aD98523631AE4a59f267346ea31F984',
            8453: '0x33128a8fC17869897dcE68Ed026d694621f6FDfD',
        },
        'routers': {
            1: '0xE592427A0AEce92De3Edee1F18E0157C05861564',
            8453: '0x2626664c2603336E57B271c5C0b26F421741e481',
        },
        'fee_tiers': [100, 500, 3000, 10000],  # 0.01%, 0.05%, 0.3%, 1%
    },
    'baseswap': {
        'name': 'BaseSwap',
        'chains': [8453],
        'factory': '0x8909dc15e40173ff4699343b6eb8132c65e18ec6',
        'router': '0x327df1e6de05895d2ab08513aadd9313fe505d86',
        'fee_tiers': [2500],  # 0.25%
    },
}


# =============================================================================
# RISK ASSESSMENT CONSTANTS (Matches your Django risk system)
# =============================================================================

# Risk score thresholds (0-100 scale, lower is better)
RISK_THRESHOLDS = {
    'CRITICAL': Decimal('90'),     # Above 90 = Critical risk
    'HIGH': Decimal('70'),         # 70-90 = High risk
    'MEDIUM': Decimal('50'),       # 50-70 = Medium risk
    'LOW': Decimal('30'),          # 30-50 = Low risk
    'MINIMAL': Decimal('0'),       # 0-30 = Minimal risk
}

# Confidence score thresholds (0-100 scale, higher is better)
CONFIDENCE_THRESHOLDS = {
    'HIGH': Decimal('85'),         # Above 85 = High confidence
    'MEDIUM': Decimal('70'),       # 70-85 = Medium confidence
    'LOW': Decimal('50'),          # 50-70 = Low confidence
    'VERY_LOW': Decimal('0'),      # 0-50 = Very low confidence
}

# Fast risk check timeouts (milliseconds) - For Engine speed
FAST_RISK_TIMEOUTS = {
    'basic_validation': 100,       # Address format, basic checks
    'honeypot_quick': 500,         # Quick honeypot detection
    'liquidity_check': 300,        # Basic liquidity validation
    'ownership_check': 200,        # Contract ownership check
    'tax_quick_check': 400,        # Quick tax analysis
    'total_timeout': 2000,         # Total fast risk timeout
}

# Comprehensive risk check timeouts (seconds) - For Django Celery
COMPREHENSIVE_RISK_TIMEOUTS = {
    'honeypot_full': 30,           # Full honeypot simulation
    'liquidity_analysis': 20,      # Deep liquidity analysis
    'holder_analysis': 45,         # Token holder distribution
    'contract_security': 60,       # Full contract security scan
    'social_signals': 15,          # Social media analysis
    'total_timeout': 300,          # Total comprehensive timeout
}


# =============================================================================
# TRADING CONSTANTS (From your engine config)
# =============================================================================

# Position size limits (in ETH) - Matches your engine config
POSITION_LIMITS = {
    'conservative': {
        'min_position_eth': Decimal('0.001'),
        'max_position_eth': Decimal('0.05'),
        'max_daily_exposure_eth': Decimal('0.2'),
    },
    'moderate': {
        'min_position_eth': Decimal('0.005'),
        'max_position_eth': Decimal('0.1'),
        'max_daily_exposure_eth': Decimal('0.5'),
    },
    'aggressive': {
        'min_position_eth': Decimal('0.01'),
        'max_position_eth': Decimal('0.2'),
        'max_daily_exposure_eth': Decimal('1.0'),
    },
}

# Slippage tolerances (percentage)
SLIPPAGE_LIMITS = {
    'conservative': {
        'max_slippage': Decimal('2.0'),
        'warning_slippage': Decimal('1.0'),
    },
    'moderate': {
        'max_slippage': Decimal('5.0'),
        'warning_slippage': Decimal('3.0'),
    },
    'aggressive': {
        'max_slippage': Decimal('10.0'),
        'warning_slippage': Decimal('7.0'),
    },
}

# Liquidity requirements (USD) - From your risk profiles
LIQUIDITY_REQUIREMENTS = {
    'conservative': Decimal('100000'),    # $100k minimum liquidity
    'moderate': Decimal('50000'),         # $50k minimum liquidity
    'aggressive': Decimal('25000'),       # $25k minimum liquidity
}


# =============================================================================
# REDIS COMMUNICATION CHANNELS
# =============================================================================

# Redis pub/sub channel names - NEW for Engine ↔ Django communication
REDIS_CHANNELS = {
    # From Engine to Django
    'pair_discovery': 'dex_bot:pair_discovery',
    'fast_risk_complete': 'dex_bot:fast_risk_complete',
    'trading_decision': 'dex_bot:trading_decision',
    'trade_execution': 'dex_bot:trade_execution',
    'engine_status': 'dex_bot:engine_status',
    'engine_alerts': 'dex_bot:engine_alerts',
    
    # From Django to Engine
    'comprehensive_risk_complete': 'dex_bot:comprehensive_risk_complete',
    'trading_config_update': 'dex_bot:config_update',
    'emergency_stop': 'dex_bot:emergency_stop',
    'risk_profile_update': 'dex_bot:risk_profile_update',
    
    # Bidirectional
    'system_events': 'dex_bot:system_events',
}

# Redis key prefixes
REDIS_KEYS = {
    'engine_status': 'dex_bot:status:engine',
    'django_status': 'dex_bot:status:django',
    'active_trades': 'dex_bot:trades:active',
    'risk_cache': 'dex_bot:cache:risk',
    'price_cache': 'dex_bot:cache:prices',
    'pair_cache': 'dex_bot:cache:pairs',
    'liquidity_cache': 'dex_bot:cache:liquidity',
    'config': 'dex_bot:config',
}


# =============================================================================
# PERFORMANCE & MONITORING CONSTANTS
# =============================================================================

# Performance thresholds (matches your Overview.md latency SLAs)
PERFORMANCE_THRESHOLDS = {
    'discovery_to_risk_max_ms': 150,      # Discovery → risk start ≤ 150ms
    'risk_eval_max_ms': 1200,             # Risk eval ≤ 1200ms (P95)
    'decision_to_submit_max_ms': 300,     # Decision → tx submit ≤ 300ms
    'end_to_end_l1_max_ms': 2000,        # End-to-end ≤ 2s on L1
    'end_to_end_base_max_ms': 1200,      # End-to-end ≤ 1.2s on Base
}

# Error rate thresholds
ERROR_THRESHOLDS = {
    'discovery_error_rate': 0.05,    # 5% error rate threshold
    'risk_error_rate': 0.02,         # 2% error rate threshold
    'execution_error_rate': 0.01,    # 1% error rate threshold
}

# Alert severities (matches your Dashboard alerts)
ALERT_SEVERITIES = {
    'CRITICAL': 'critical',    # System down, immediate action required
    'HIGH': 'high',           # Major functionality impacted
    'MEDIUM': 'medium',       # Minor functionality impacted
    'LOW': 'low',             # Performance degradation
    'INFO': 'info',           # Informational only
}


# =============================================================================
# MESSAGE TYPES FOR REDIS COMMUNICATION
# =============================================================================

MESSAGE_TYPES = {
    # Discovery messages
    'NEW_PAIR_DISCOVERED': 'new_pair_discovered',
    'PAIR_LIQUIDITY_UPDATED': 'pair_liquidity_updated',
    
    # Risk assessment messages
    'FAST_RISK_STARTED': 'fast_risk_started',
    'FAST_RISK_COMPLETE': 'fast_risk_complete',
    'COMPREHENSIVE_RISK_COMPLETE': 'comprehensive_risk_complete',
    
    # Trading decision messages
    'TRADING_DECISION_MADE': 'trading_decision_made',
    'EXECUTION_STARTED': 'execution_started',
    'EXECUTION_COMPLETE': 'execution_complete',
    
    # Status and monitoring
    'ENGINE_STATUS_UPDATE': 'engine_status_update',
    'ENGINE_HEARTBEAT': 'engine_heartbeat',
    'ALERT_TRIGGERED': 'alert_triggered',
    
    # Configuration
    'CONFIG_UPDATED': 'config_updated',
    'RISK_PROFILE_UPDATED': 'risk_profile_updated',
    'EMERGENCY_STOP': 'emergency_stop',
}


# =============================================================================
# VALIDATION CONSTANTS
# =============================================================================

# Address validation patterns
ADDRESS_PATTERNS = {
    'ethereum': r'^0x[a-fA-F0-9]{40}$',
    'transaction': r'^0x[a-fA-F0-9]{64}$',
}

# Numeric validation limits
NUMERIC_LIMITS = {
    'max_uint256': 2**256 - 1,
    'max_gas_limit': 30000000,
    'max_gas_price_gwei': 1000,
    'max_slippage_percent': 50.0,
    'max_position_eth': 10.0,
}

# String validation limits
STRING_LIMITS = {
    'max_symbol_length': 20,
    'max_name_length': 100,
    'max_description_length': 1000,
    'max_error_message_length': 2000,
}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_chain_name(chain_id: int) -> str:
    """Get chain name from chain ID."""
    return CHAIN_NAMES.get(chain_id, f"unknown_chain_{chain_id}")


def get_chain_id(chain_name: str) -> int:
    """Get chain ID from chain name."""
    return CHAIN_IDS.get(chain_name.lower(), 0)


def get_native_token(chain_id: int) -> str:
    """Get native token symbol for a chain."""
    return NATIVE_TOKENS.get(chain_id, "UNKNOWN")


def get_wrapped_native(chain_id: int) -> str:
    """Get wrapped native token address for a chain."""
    return WRAPPED_NATIVE.get(chain_id, "")


def is_supported_chain(chain_id: int) -> bool:
    """Check if a chain is supported."""
    return chain_id in CHAIN_NAMES


def get_dex_info(dex_name: str) -> Dict:
    """Get DEX configuration information."""
    return SUPPORTED_DEXES.get(dex_name, {})


def get_risk_level_from_score(score: Decimal) -> str:
    """Determine risk level from numeric score."""
    if score >= RISK_THRESHOLDS['CRITICAL']:
        return 'CRITICAL'
    elif score >= RISK_THRESHOLDS['HIGH']:
        return 'HIGH'
    elif score >= RISK_THRESHOLDS['MEDIUM']:
        return 'MEDIUM'
    elif score >= RISK_THRESHOLDS['LOW']:
        return 'LOW'
    else:
        return 'MINIMAL'


def get_confidence_level_from_score(score: Decimal) -> str:
    """Determine confidence level from numeric score."""
    if score >= CONFIDENCE_THRESHOLDS['HIGH']:
        return 'HIGH'
    elif score >= CONFIDENCE_THRESHOLDS['MEDIUM']:
        return 'MEDIUM'
    elif score >= CONFIDENCE_THRESHOLDS['LOW']:
        return 'LOW'
    else:
        return 'VERY_LOW'


def get_redis_channel(message_type: str) -> str:
    """Get Redis channel for a message type."""
    channel_mapping = {
        MESSAGE_TYPES['NEW_PAIR_DISCOVERED']: REDIS_CHANNELS['pair_discovery'],
        MESSAGE_TYPES['FAST_RISK_COMPLETE']: REDIS_CHANNELS['fast_risk_complete'],
        MESSAGE_TYPES['COMPREHENSIVE_RISK_COMPLETE']: REDIS_CHANNELS['comprehensive_risk_complete'],
        MESSAGE_TYPES['TRADING_DECISION_MADE']: REDIS_CHANNELS['trading_decision'],
        MESSAGE_TYPES['EXECUTION_COMPLETE']: REDIS_CHANNELS['trade_execution'],
        MESSAGE_TYPES['ENGINE_STATUS_UPDATE']: REDIS_CHANNELS['engine_status'],
        MESSAGE_TYPES['ALERT_TRIGGERED']: REDIS_CHANNELS['engine_alerts'],
        MESSAGE_TYPES['EMERGENCY_STOP']: REDIS_CHANNELS['emergency_stop'],
    }
    return channel_mapping.get(message_type, REDIS_CHANNELS['system_events'])


def is_fast_risk_timeout_exceeded(elapsed_ms: int) -> bool:
    """Check if fast risk assessment timeout is exceeded."""
    return elapsed_ms > FAST_RISK_TIMEOUTS['total_timeout']


def is_comprehensive_risk_timeout_exceeded(elapsed_seconds: int) -> bool:
    """Check if comprehensive risk assessment timeout is exceeded."""
    return elapsed_seconds > COMPREHENSIVE_RISK_TIMEOUTS['total_timeout']