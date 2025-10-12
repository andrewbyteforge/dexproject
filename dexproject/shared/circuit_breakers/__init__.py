"""
Circuit Breakers Module

Production-hardened circuit breaker implementation for the DEX Auto-Trading Bot.
Provides resilient failure handling, automatic recovery, and comprehensive monitoring.

File: shared/circuit_breakers/__init__.py
"""

import logging

# Version info
__version__ = "2.0.0"
__author__ = "DEX Trading Team"

# Configure module logger
logger = logging.getLogger(__name__)

# Import main components for easier access
from .config import (
    CircuitBreakerType,
    CircuitBreakerPriority,
    RecoveryStrategy,
    CircuitBreakerConfig,
    CircuitBreakerDefaults,
    CircuitBreakerGroup,
    BREAKER_GROUPS,
    NotificationConfig,
    get_breakers_by_priority,
    get_critical_breakers,
    is_auto_recoverable,
    load_config_from_env,
)

# These will be imported once we create the files
try:
    from .enhanced_breaker import (
        EnhancedCircuitBreaker,
        CircuitBreakerState,
        CircuitBreakerOpenError,
        CircuitBreakerMetrics,
    )
    ENHANCED_BREAKER_AVAILABLE = True
except ImportError:
    logger.warning("Enhanced circuit breaker not available yet")
    ENHANCED_BREAKER_AVAILABLE = False

try:
    from .manager import (
        CircuitBreakerManager,
        CircuitBreakerEvent,
        CircuitBreakerRegistry,
    )
    MANAGER_AVAILABLE = True
except ImportError:
    logger.warning("Circuit breaker manager not available yet")
    MANAGER_AVAILABLE = False

# Delay model imports to avoid AppRegistryNotReady
PERSISTENCE_AVAILABLE = False
CircuitBreakerPersistence = None
CircuitBreakerEventModel = None
CircuitBreakerStateModel = None

def _import_persistence():
    """Import persistence models after Django is ready."""
    global PERSISTENCE_AVAILABLE, CircuitBreakerPersistence
    global CircuitBreakerEventModel, CircuitBreakerStateModel
    
    if PERSISTENCE_AVAILABLE:
        return
    
    try:
        from .persistence import (
            CircuitBreakerPersistence,
            CircuitBreakerEventModel,
            CircuitBreakerStateModel,
        )
        PERSISTENCE_AVAILABLE = True
    except ImportError:
        logger.warning("Circuit breaker persistence not available")
        PERSISTENCE_AVAILABLE = False

# Don't import models at module level - wait for Django to be ready

try:
    from .monitoring import (
        CircuitBreakerMonitor,
        CircuitBreakerMetricsExporter,
        PrometheusExporter,
    )
    MONITORING_AVAILABLE = True
except ImportError:
    logger.warning("Circuit breaker monitoring not available yet")
    MONITORING_AVAILABLE = False

# Function to get persistence classes after Django is ready
def get_persistence_classes():
    """Get persistence classes after Django initialization."""
    _import_persistence()
    return {
        'CircuitBreakerPersistence': CircuitBreakerPersistence,
        'CircuitBreakerEventModel': CircuitBreakerEventModel,
        'CircuitBreakerStateModel': CircuitBreakerStateModel,
    }

# Convenience imports - make the most important items directly accessible
__all__ = [
    # Core types and enums
    "CircuitBreakerType",
    "CircuitBreakerPriority",
    "RecoveryStrategy",
    "CircuitBreakerState",
    
    # Configuration
    "CircuitBreakerConfig",
    "CircuitBreakerDefaults",
    "CircuitBreakerGroup",
    "BREAKER_GROUPS",
    "NotificationConfig",
    
    # Main classes (when available)
    "EnhancedCircuitBreaker",
    "CircuitBreakerManager",
    "CircuitBreakerRegistry",
    "CircuitBreakerEvent",
    
    # Helper functions
    "get_breakers_by_priority",
    "get_critical_breakers",
    "is_auto_recoverable",
    "load_config_from_env",
    "get_persistence_classes",  # Function to get models after Django ready
    "_import_persistence",  # Function to trigger import
    
    # Exceptions
    "CircuitBreakerOpenError",
    
    # Monitoring (when available)
    "CircuitBreakerMonitor",
    "CircuitBreakerMetricsExporter",
    
    # Version info
    "__version__",
]

# Module initialization logging
logger.info(f"Circuit Breakers Module v{__version__} initialized")
logger.info(f"Enhanced Breaker: {'Available' if ENHANCED_BREAKER_AVAILABLE else 'Not Available'}")
logger.info(f"Manager: {'Available' if MANAGER_AVAILABLE else 'Not Available'}")
logger.info(f"Persistence: {'Available' if PERSISTENCE_AVAILABLE else 'Not Available'}")
logger.info(f"Monitoring: {'Available' if MONITORING_AVAILABLE else 'Not Available'}")