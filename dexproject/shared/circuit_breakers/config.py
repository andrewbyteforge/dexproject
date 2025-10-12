"""
Circuit Breaker Configuration Module

Centralized configuration for all circuit breaker types, thresholds, and behaviors.
Provides a unified place to manage circuit breaker settings across the entire system.

File: shared/circuit_breakers/config.py
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional, Any, List
from datetime import timedelta

logger = logging.getLogger(__name__)


# =============================================================================
# CIRCUIT BREAKER TYPES
# =============================================================================

class CircuitBreakerType(Enum):
    """
    Comprehensive enum of all circuit breaker types.
    Extends the basic types with production-ready breakers.
    """
    # Portfolio Risk Breakers (existing)
    DAILY_LOSS = "DAILY_LOSS"
    PORTFOLIO_LOSS = "PORTFOLIO_LOSS"
    CONSECUTIVE_LOSSES = "CONSECUTIVE_LOSSES"
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"
    
    # Transaction & Execution Breakers (existing)
    TRANSACTION_FAILURE = "TRANSACTION_FAILURE"
    DEX_FAILURE = "DEX_FAILURE"
    
    # Gas & Network Breakers (NEW)
    GAS_PRICE_SPIKE = "GAS_PRICE_SPIKE"
    GAS_ESTIMATION_FAILURE = "GAS_ESTIMATION_FAILURE"
    MEMPOOL_CONGESTION = "MEMPOOL_CONGESTION"
    
    # RPC & Network Breakers (NEW)
    RPC_FAILURE = "RPC_FAILURE"
    RPC_LATENCY = "RPC_LATENCY"
    NETWORK_CONGESTION = "NETWORK_CONGESTION"
    CHAIN_REORG_DETECTED = "CHAIN_REORG_DETECTED"
    
    # Market Condition Breakers (NEW)
    SLIPPAGE_EXCESSIVE = "SLIPPAGE_EXCESSIVE"
    LIQUIDITY_CRISIS = "LIQUIDITY_CRISIS"
    PRICE_IMPACT_EXCESSIVE = "PRICE_IMPACT_EXCESSIVE"
    ORACLE_PRICE_DEVIATION = "ORACLE_PRICE_DEVIATION"
    
    # System & Resource Breakers (NEW)
    MEMORY_PRESSURE = "MEMORY_PRESSURE"
    CPU_OVERLOAD = "CPU_OVERLOAD"
    DATABASE_FAILURE = "DATABASE_FAILURE"
    REDIS_FAILURE = "REDIS_FAILURE"
    WEBSOCKET_FAILURE = "WEBSOCKET_FAILURE"
    
    # Security Breakers (NEW)
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY"
    AUTH_FAILURE_SPIKE = "AUTH_FAILURE_SPIKE"
    
    # Manual & External Triggers
    EXTERNAL_TRIGGER = "EXTERNAL_TRIGGER"
    MANUAL_EMERGENCY_STOP = "MANUAL_EMERGENCY_STOP"


class CircuitBreakerPriority(Enum):
    """Priority levels for circuit breaker activation."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4
    EMERGENCY = 5


class RecoveryStrategy(Enum):
    """Recovery strategies for circuit breakers."""
    AUTO_TIME_BASED = "AUTO_TIME_BASED"          # Recovers after timeout
    AUTO_HEALTH_CHECK = "AUTO_HEALTH_CHECK"      # Recovers after health check passes
    MANUAL_ONLY = "MANUAL_ONLY"                  # Requires manual intervention
    GRADUAL_RECOVERY = "GRADUAL_RECOVERY"        # Gradually increases allowed traffic
    CONDITIONAL = "CONDITIONAL"                   # Based on external conditions


# =============================================================================
# CIRCUIT BREAKER CONFIGURATIONS
# =============================================================================

@dataclass
class CircuitBreakerConfig:
    """
    Configuration for individual circuit breaker instances.
    
    Attributes:
        breaker_type: Type of circuit breaker
        failure_threshold: Number of failures before opening
        success_threshold: Successes needed to close from half-open
        timeout_seconds: Time to wait before attempting recovery
        recovery_strategy: How the breaker should recover
        priority: Priority level for this breaker
        error_rate_threshold: Optional error rate threshold (0-1)
        sliding_window_size: Number of recent calls to consider
        half_open_max_calls: Max calls allowed in half-open state
        enable_jitter: Add randomness to timeout to prevent thundering herd
        escalation_multiplier: Multiply timeout on repeated failures
        max_timeout_seconds: Maximum timeout after escalation
        custom_params: Additional parameters for specific breaker types
    """
    breaker_type: CircuitBreakerType
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: int = 60
    recovery_strategy: RecoveryStrategy = RecoveryStrategy.AUTO_TIME_BASED
    priority: CircuitBreakerPriority = CircuitBreakerPriority.MEDIUM
    error_rate_threshold: Optional[float] = None
    sliding_window_size: int = 100
    half_open_max_calls: int = 3
    enable_jitter: bool = True
    escalation_multiplier: float = 1.5
    max_timeout_seconds: int = 3600  # 1 hour max
    custom_params: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.failure_threshold < 1:
            raise ValueError(f"failure_threshold must be >= 1, got {self.failure_threshold}")
        if self.success_threshold < 1:
            raise ValueError(f"success_threshold must be >= 1, got {self.success_threshold}")
        if self.timeout_seconds < 0:
            raise ValueError(f"timeout_seconds must be >= 0, got {self.timeout_seconds}")
        if self.error_rate_threshold is not None:
            if not 0 <= self.error_rate_threshold <= 1:
                raise ValueError(f"error_rate_threshold must be between 0 and 1, got {self.error_rate_threshold}")


# =============================================================================
# DEFAULT CONFIGURATIONS
# =============================================================================

class CircuitBreakerDefaults:
    """
    Default configurations for all circuit breaker types.
    These can be overridden via environment variables or runtime configuration.
    """
    
    @staticmethod
    def get_default_configs() -> Dict[CircuitBreakerType, CircuitBreakerConfig]:
        """
        Get default configuration for each circuit breaker type.
        
        Returns:
            Dictionary mapping breaker types to their default configurations
        """
        return {
            # Portfolio Risk Breakers
            CircuitBreakerType.DAILY_LOSS: CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.DAILY_LOSS,
                failure_threshold=1,  # One daily loss limit hit
                timeout_seconds=86400,  # 24 hours
                recovery_strategy=RecoveryStrategy.AUTO_TIME_BASED,
                priority=CircuitBreakerPriority.HIGH,
                custom_params={"loss_percent_threshold": 5.0}
            ),
            
            CircuitBreakerType.PORTFOLIO_LOSS: CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.PORTFOLIO_LOSS,
                failure_threshold=1,
                timeout_seconds=0,  # Manual recovery only
                recovery_strategy=RecoveryStrategy.MANUAL_ONLY,
                priority=CircuitBreakerPriority.CRITICAL,
                custom_params={"loss_percent_threshold": 10.0}
            ),
            
            CircuitBreakerType.CONSECUTIVE_LOSSES: CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.CONSECUTIVE_LOSSES,
                failure_threshold=5,  # 5 consecutive losses
                timeout_seconds=14400,  # 4 hours
                recovery_strategy=RecoveryStrategy.AUTO_TIME_BASED,
                priority=CircuitBreakerPriority.MEDIUM,
                custom_params={"max_consecutive": 5}
            ),
            
            # Transaction Breakers
            CircuitBreakerType.TRANSACTION_FAILURE: CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.TRANSACTION_FAILURE,
                failure_threshold=5,
                success_threshold=2,
                timeout_seconds=300,  # 5 minutes
                recovery_strategy=RecoveryStrategy.AUTO_HEALTH_CHECK,
                priority=CircuitBreakerPriority.HIGH,
                escalation_multiplier=2.0,
                max_timeout_seconds=1800  # 30 minutes max
            ),
            
            CircuitBreakerType.DEX_FAILURE: CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.DEX_FAILURE,
                failure_threshold=3,
                success_threshold=1,
                timeout_seconds=180,  # 3 minutes
                recovery_strategy=RecoveryStrategy.AUTO_HEALTH_CHECK,
                priority=CircuitBreakerPriority.HIGH,
                half_open_max_calls=1
            ),
            
            # Gas Breakers
            CircuitBreakerType.GAS_PRICE_SPIKE: CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.GAS_PRICE_SPIKE,
                failure_threshold=1,
                timeout_seconds=60,  # 1 minute
                recovery_strategy=RecoveryStrategy.CONDITIONAL,
                priority=CircuitBreakerPriority.HIGH,
                custom_params={
                    "max_gas_price_gwei": 100,
                    "spike_multiplier": 3.0  # 3x normal gas price
                }
            ),
            
            CircuitBreakerType.MEMPOOL_CONGESTION: CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.MEMPOOL_CONGESTION,
                failure_threshold=10,  # 10 mempool drops
                timeout_seconds=120,  # 2 minutes
                recovery_strategy=RecoveryStrategy.AUTO_TIME_BASED,
                priority=CircuitBreakerPriority.MEDIUM,
                custom_params={"mempool_size_threshold": 50000}
            ),
            
            # RPC Breakers
            CircuitBreakerType.RPC_FAILURE: CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.RPC_FAILURE,
                failure_threshold=5,
                success_threshold=3,
                timeout_seconds=30,  # 30 seconds
                recovery_strategy=RecoveryStrategy.AUTO_HEALTH_CHECK,
                priority=CircuitBreakerPriority.CRITICAL,
                error_rate_threshold=0.5,  # 50% error rate
                sliding_window_size=20,
                escalation_multiplier=1.5
            ),
            
            CircuitBreakerType.RPC_LATENCY: CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.RPC_LATENCY,
                failure_threshold=10,
                timeout_seconds=60,
                recovery_strategy=RecoveryStrategy.GRADUAL_RECOVERY,
                priority=CircuitBreakerPriority.MEDIUM,
                custom_params={
                    "latency_threshold_ms": 5000,  # 5 seconds
                    "p99_threshold_ms": 10000  # 10 seconds for P99
                }
            ),
            
            # Market Condition Breakers
            CircuitBreakerType.SLIPPAGE_EXCESSIVE: CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.SLIPPAGE_EXCESSIVE,
                failure_threshold=3,
                timeout_seconds=300,  # 5 minutes
                recovery_strategy=RecoveryStrategy.CONDITIONAL,
                priority=CircuitBreakerPriority.MEDIUM,
                custom_params={
                    "max_slippage_percent": 5.0,
                    "critical_slippage_percent": 10.0
                }
            ),
            
            CircuitBreakerType.LIQUIDITY_CRISIS: CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.LIQUIDITY_CRISIS,
                failure_threshold=1,
                timeout_seconds=600,  # 10 minutes
                recovery_strategy=RecoveryStrategy.CONDITIONAL,
                priority=CircuitBreakerPriority.CRITICAL,
                custom_params={
                    "min_liquidity_usd": 10000,
                    "liquidity_drop_percent": 50.0
                }
            ),
            
            # System Resource Breakers
            CircuitBreakerType.MEMORY_PRESSURE: CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.MEMORY_PRESSURE,
                failure_threshold=1,
                timeout_seconds=30,
                recovery_strategy=RecoveryStrategy.AUTO_HEALTH_CHECK,
                priority=CircuitBreakerPriority.HIGH,
                custom_params={
                    "memory_threshold_percent": 90,
                    "gc_threshold_ms": 1000  # GC taking > 1 second
                }
            ),
            
            CircuitBreakerType.DATABASE_FAILURE: CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.DATABASE_FAILURE,
                failure_threshold=3,
                success_threshold=2,
                timeout_seconds=60,
                recovery_strategy=RecoveryStrategy.AUTO_HEALTH_CHECK,
                priority=CircuitBreakerPriority.CRITICAL,
                error_rate_threshold=0.3  # 30% error rate
            ),
            
            # Security Breakers
            CircuitBreakerType.RATE_LIMIT_EXCEEDED: CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.RATE_LIMIT_EXCEEDED,
                failure_threshold=1,
                timeout_seconds=60,
                recovery_strategy=RecoveryStrategy.AUTO_TIME_BASED,
                priority=CircuitBreakerPriority.MEDIUM,
                custom_params={"rate_limit_per_minute": 100}
            ),
            
            CircuitBreakerType.SUSPICIOUS_ACTIVITY: CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.SUSPICIOUS_ACTIVITY,
                failure_threshold=1,
                timeout_seconds=0,  # Manual review required
                recovery_strategy=RecoveryStrategy.MANUAL_ONLY,
                priority=CircuitBreakerPriority.EMERGENCY,
                custom_params={"auto_report": True}
            ),
            
            # Manual Triggers
            CircuitBreakerType.MANUAL_EMERGENCY_STOP: CircuitBreakerConfig(
                breaker_type=CircuitBreakerType.MANUAL_EMERGENCY_STOP,
                failure_threshold=1,
                timeout_seconds=0,
                recovery_strategy=RecoveryStrategy.MANUAL_ONLY,
                priority=CircuitBreakerPriority.EMERGENCY
            ),
        }
    
    @staticmethod
    def get_config(breaker_type: CircuitBreakerType) -> CircuitBreakerConfig:
        """
        Get configuration for a specific breaker type.
        
        Args:
            breaker_type: Type of circuit breaker
            
        Returns:
            Configuration for the specified breaker type
            
        Raises:
            KeyError: If breaker type has no default configuration
        """
        configs = CircuitBreakerDefaults.get_default_configs()
        if breaker_type not in configs:
            logger.warning(f"No default config for {breaker_type}, using generic defaults")
            return CircuitBreakerConfig(
                breaker_type=breaker_type,
                failure_threshold=5,
                timeout_seconds=60,
                recovery_strategy=RecoveryStrategy.AUTO_TIME_BASED
            )
        return configs[breaker_type]


# =============================================================================
# CIRCUIT BREAKER GROUPS
# =============================================================================

class CircuitBreakerGroup(Enum):
    """Groups of related circuit breakers for bulk operations."""
    PORTFOLIO = "PORTFOLIO"  # Risk and portfolio management
    EXECUTION = "EXECUTION"  # Transaction execution
    NETWORK = "NETWORK"      # Network and RPC related
    MARKET = "MARKET"        # Market conditions
    SYSTEM = "SYSTEM"        # System resources
    SECURITY = "SECURITY"    # Security related
    ALL = "ALL"              # All circuit breakers


# Group mappings
BREAKER_GROUPS: Dict[CircuitBreakerGroup, List[CircuitBreakerType]] = {
    CircuitBreakerGroup.PORTFOLIO: [
        CircuitBreakerType.DAILY_LOSS,
        CircuitBreakerType.PORTFOLIO_LOSS,
        CircuitBreakerType.CONSECUTIVE_LOSSES,
        CircuitBreakerType.VOLATILITY_SPIKE,
    ],
    CircuitBreakerGroup.EXECUTION: [
        CircuitBreakerType.TRANSACTION_FAILURE,
        CircuitBreakerType.DEX_FAILURE,
        CircuitBreakerType.GAS_PRICE_SPIKE,
        CircuitBreakerType.GAS_ESTIMATION_FAILURE,
        CircuitBreakerType.MEMPOOL_CONGESTION,
    ],
    CircuitBreakerGroup.NETWORK: [
        CircuitBreakerType.RPC_FAILURE,
        CircuitBreakerType.RPC_LATENCY,
        CircuitBreakerType.NETWORK_CONGESTION,
        CircuitBreakerType.CHAIN_REORG_DETECTED,
    ],
    CircuitBreakerGroup.MARKET: [
        CircuitBreakerType.SLIPPAGE_EXCESSIVE,
        CircuitBreakerType.LIQUIDITY_CRISIS,
        CircuitBreakerType.PRICE_IMPACT_EXCESSIVE,
        CircuitBreakerType.ORACLE_PRICE_DEVIATION,
    ],
    CircuitBreakerGroup.SYSTEM: [
        CircuitBreakerType.MEMORY_PRESSURE,
        CircuitBreakerType.CPU_OVERLOAD,
        CircuitBreakerType.DATABASE_FAILURE,
        CircuitBreakerType.REDIS_FAILURE,
        CircuitBreakerType.WEBSOCKET_FAILURE,
    ],
    CircuitBreakerGroup.SECURITY: [
        CircuitBreakerType.RATE_LIMIT_EXCEEDED,
        CircuitBreakerType.SUSPICIOUS_ACTIVITY,
        CircuitBreakerType.AUTH_FAILURE_SPIKE,
    ],
}

# Add ALL group
BREAKER_GROUPS[CircuitBreakerGroup.ALL] = [
    breaker for group_breakers in BREAKER_GROUPS.values() 
    for breaker in group_breakers
] + [
    CircuitBreakerType.EXTERNAL_TRIGGER,
    CircuitBreakerType.MANUAL_EMERGENCY_STOP,
]


# =============================================================================
# NOTIFICATION SETTINGS
# =============================================================================

@dataclass
class NotificationConfig:
    """
    Configuration for circuit breaker notifications.
    
    Attributes:
        websocket_enabled: Send real-time WebSocket notifications
        email_enabled: Send email alerts for critical breakers
        slack_enabled: Send Slack notifications
        discord_enabled: Send Discord alerts
        database_logging: Log all events to database
        metrics_export: Export metrics to monitoring system
    """
    websocket_enabled: bool = True
    email_enabled: bool = False
    slack_enabled: bool = False
    discord_enabled: bool = False
    database_logging: bool = True
    metrics_export: bool = True
    
    # Notification thresholds
    email_priority_threshold: CircuitBreakerPriority = CircuitBreakerPriority.HIGH
    slack_priority_threshold: CircuitBreakerPriority = CircuitBreakerPriority.MEDIUM
    
    # Rate limiting
    max_notifications_per_hour: int = 100
    notification_cooldown_seconds: int = 60  # Min time between similar notifications


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_breakers_by_priority(
    min_priority: CircuitBreakerPriority = CircuitBreakerPriority.LOW
) -> List[CircuitBreakerType]:
    """
    Get all circuit breakers at or above a certain priority level.
    
    Args:
        min_priority: Minimum priority level to include
        
    Returns:
        List of circuit breaker types meeting the priority threshold
    """
    configs = CircuitBreakerDefaults.get_default_configs()
    return [
        breaker_type
        for breaker_type, config in configs.items()
        if config.priority.value >= min_priority.value
    ]


def get_critical_breakers() -> List[CircuitBreakerType]:
    """Get all critical and emergency priority circuit breakers."""
    return get_breakers_by_priority(CircuitBreakerPriority.CRITICAL)


def is_auto_recoverable(breaker_type: CircuitBreakerType) -> bool:
    """
    Check if a circuit breaker type can auto-recover.
    
    Args:
        breaker_type: Type of circuit breaker
        
    Returns:
        True if the breaker can auto-recover, False if manual intervention required
    """
    config = CircuitBreakerDefaults.get_config(breaker_type)
    return config.recovery_strategy != RecoveryStrategy.MANUAL_ONLY


# =============================================================================
# ENVIRONMENT VARIABLE OVERRIDES
# =============================================================================

def load_config_from_env() -> Dict[str, Any]:
    """
    Load circuit breaker configuration overrides from environment variables.
    
    Environment variables should follow the pattern:
    CB_{BREAKER_TYPE}_{PARAM_NAME}
    
    Example:
        CB_RPC_FAILURE_THRESHOLD=10
        CB_GAS_PRICE_SPIKE_TIMEOUT=120
    
    Returns:
        Dictionary of configuration overrides
    """
    import os
    
    overrides = {}
    prefix = "CB_"
    
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
            
        # Parse the environment variable
        parts = key[len(prefix):].split('_')
        if len(parts) < 2:
            continue
            
        # Extract breaker type and parameter
        breaker_type_str = '_'.join(parts[:-1])
        param_name = parts[-1].lower()
        
        try:
            # Convert to breaker type enum
            breaker_type = CircuitBreakerType[breaker_type_str]
            
            # Store override
            if breaker_type not in overrides:
                overrides[breaker_type] = {}
            
            # Convert value to appropriate type
            if param_name in ['failure_threshold', 'success_threshold', 'timeout_seconds']:
                overrides[breaker_type][param_name] = int(value)
            elif param_name in ['error_rate_threshold', 'escalation_multiplier']:
                overrides[breaker_type][param_name] = float(value)
            elif param_name in ['enable_jitter']:
                overrides[breaker_type][param_name] = value.lower() == 'true'
            else:
                overrides[breaker_type][param_name] = value
                
        except (KeyError, ValueError) as e:
            logger.warning(f"Invalid circuit breaker env var {key}: {e}")
            continue
    
    return overrides


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================

# Log configuration on module import
logger.info("Circuit Breaker Configuration Module Initialized")
logger.info(f"Total breaker types defined: {len(CircuitBreakerType)}")
logger.info(f"Critical breakers: {len(get_critical_breakers())}")

# Load any environment overrides
env_overrides = load_config_from_env()
if env_overrides:
    logger.info(f"Loaded {len(env_overrides)} configuration overrides from environment")