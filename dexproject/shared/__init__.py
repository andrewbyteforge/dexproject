"""
Shared module for the DEX auto-trading bot.

This module provides common schemas, constants, and utilities used by both
the async engine and the Django backend for seamless communication.
"""

import logging

# Import key components for easy access
from .constants import (
    CHAIN_IDS, CHAIN_NAMES, REDIS_CHANNELS, RISK_THRESHOLDS,
    get_chain_name, get_chain_id, get_risk_level_from_score
)
from .schemas import (
    BaseMessage, TokenInfo, PairInfo, NewPairDiscovered,
    FastRiskAssessment, TradingDecision, ExecutionResult,
    serialize_message, deserialize_message
)
from .redis_client import RedisClient

# Version information
__version__ = "1.0.0"
__author__ = "DEX Trading Bot Team"

# Configure logging for the shared module
logger = logging.getLogger(__name__)

# Export key components
__all__ = [
    # Constants
    'CHAIN_IDS',
    'CHAIN_NAMES', 
    'REDIS_CHANNELS',
    'RISK_THRESHOLDS',
    'get_chain_name',
    'get_chain_id',
    'get_risk_level_from_score',
    
    # Schemas
    'BaseMessage',
    'TokenInfo',
    'PairInfo', 
    'NewPairDiscovered',
    'FastRiskAssessment',
    'TradingDecision',
    'ExecutionResult',
    'serialize_message',
    'deserialize_message',
    
    # Redis Communication
    'RedisClient',
]