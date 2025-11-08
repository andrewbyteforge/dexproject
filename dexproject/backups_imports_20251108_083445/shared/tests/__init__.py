"""
Shared Module Initialization - Export Public API

This module exports the public API for the shared components used across
the DEX trading bot system, providing clean imports for other modules.

File: dexproject/shared/__init__.py
"""

import sys
import os
from pathlib import Path

# Ensure the project root is in the Python path for absolute imports
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    # Core Redis communication - using absolute imports to avoid relative import issues
    from shared.redis_client import (
        RedisClient,
        DjangoRedisHandler,
        create_redis_client,
        get_django_redis_client,
        test_redis_connection
    )
except ImportError:
    # Fallback for when modules are not yet complete
    RedisClient = None
    DjangoRedisHandler = None
    create_redis_client = None
    get_django_redis_client = None
    test_redis_connection = None

try:
    # Constants and configuration
    from shared.constants import (
        REDIS_CHANNELS,
        REDIS_KEYS,
        MESSAGE_TYPES,
        get_redis_channel
    )
except ImportError:
    # Provide defaults if constants not available
    REDIS_CHANNELS = {}
    REDIS_KEYS = {}
    MESSAGE_TYPES = {}
    def get_redis_channel(message_type):
        return f"dex_bot_{message_type}"

try:
    # Message schemas for communication
    from shared.schemas import (
        BaseMessage,
        MessageType,
        NewPairDiscovered,
        FastRiskAssessment,
        TradingDecision,
        ExecutionResult,
        EngineStatus,
        AlertTriggered,
        serialize_message,
        deserialize_message,
        create_correlation_id
    )
except ImportError:
    # Fallback for when schemas are not complete
    BaseMessage = None
    MessageType = None
    NewPairDiscovered = None
    FastRiskAssessment = None
    TradingDecision = None
    ExecutionResult = None
    EngineStatus = None
    AlertTriggered = None
    serialize_message = None
    deserialize_message = None
    create_correlation_id = None

try:
    # Chain configuration bridge
    from shared.chain_config_bridge import (
        ChainConfigBridge,
        ChainConfig,
        RPCProvider,
        get_engine_chain_configs
    )
except ImportError:
    # Fallback for when bridge is not complete
    ChainConfigBridge = None
    ChainConfig = None
    RPCProvider = None
    get_engine_chain_configs = None

# Version information
__version__ = "1.0.0"

# Public API exports - Only include what's actually available
__all__ = []

# Add available components to __all__
if RedisClient is not None:
    __all__.extend([
        "RedisClient",
        "DjangoRedisHandler", 
        "create_redis_client",
        "get_django_redis_client",
        "test_redis_connection",
    ])

if REDIS_CHANNELS:
    __all__.extend([
        "REDIS_CHANNELS",
        "REDIS_KEYS",
        "MESSAGE_TYPES",
        "get_redis_channel",
    ])

if BaseMessage is not None:
    __all__.extend([
        "BaseMessage",
        "MessageType", 
        "NewPairDiscovered",
        "FastRiskAssessment",
        "TradingDecision",
        "ExecutionResult",
        "EngineStatus",
        "AlertTriggered",
        "serialize_message",
        "deserialize_message",
        "create_correlation_id",
    ])

if ChainConfigBridge is not None:
    __all__.extend([
        "ChainConfigBridge",
        "ChainConfig",
        "RPCProvider", 
        "get_engine_chain_configs",
    ])

# Module metadata
__author__ = "DEX Trading Bot Team"
__description__ = "Shared components for Django ↔ Engine communication"