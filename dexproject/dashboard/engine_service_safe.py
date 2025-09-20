"""
Engine Service Import Fix

Safe import wrapper that avoids async issues during Django module loading.
This ensures the engine service can be imported without event loop errors.

File: dashboard/engine_service_safe.py
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class SafeEngineServiceWrapper:
    """
    Safe wrapper for engine service that handles import-time async issues.
    
    This wrapper delays the creation of the actual engine service until
    it's actually needed, avoiding the event loop issues during Django startup.
    """
    
    def __init__(self):
        """Initialize wrapper without creating async tasks."""
        self._engine_service = None
        self._initialization_attempted = False
        self.logger = logging.getLogger(__name__)
    
    def _get_engine_service(self):
        """Get or create the engine service lazily."""
        if self._engine_service is None and not self._initialization_attempted:
            self._initialization_attempted = True
            try:
                # Import the actual engine service here to avoid import-time issues
                from .live_engine_service import EnhancedEngineService
                self._engine_service = EnhancedEngineService()
                self.logger.info("Engine service created successfully")
            except Exception as e:
                self.logger.error(f"Failed to create engine service: {e}")
                # Create a fallback mock service
                self._engine_service = self._create_fallback_service()
        
        return self._engine_service
    
    def _create_fallback_service(self):
        """Create a fallback service for when engine service fails."""
        class FallbackEngineService:
            def __init__(self):
                self.engine_initialized = False
                self.mock_mode = True
                self.live_data_enabled = False
                
            def get_engine_status(self):
                return {
                    'timestamp': '2025-09-20T10:00:00Z',
                    'status': 'FALLBACK',
                    'initialized': False,
                    'live_mode': False,
                    'is_live': False,
                    'mock_mode': True,
                    'error': 'Engine service initialization failed',
                    '_mock': True
                }
            
            def get_performance_metrics(self):
                return {
                    'timestamp': '2025-09-20T10:00:00Z',
                    'execution_time_ms': 0,
                    'success_rate': 0,
                    'trades_per_minute': 0,
                    'total_executions': 0,
                    'data_source': 'FALLBACK',
                    'is_live': False,
                    'error': 'Engine service initialization failed',
                    '_mock': True
                }
            
            async def initialize_engine(self, force_reinit=False):
                return False
        
        return FallbackEngineService()
    
    def __getattr__(self, name):
        """Delegate all attribute access to the actual engine service."""
        engine_service = self._get_engine_service()
        if engine_service:
            return getattr(engine_service, name)
        else:
            raise AttributeError(f"Engine service not available and attribute '{name}' not found")


# Create the safe wrapper instance
safe_engine_service = SafeEngineServiceWrapper()

# Export functions that delegate to the safe wrapper
def get_engine_status() -> Dict[str, Any]:
    """Get engine status safely."""
    return safe_engine_service.get_engine_status()

def get_performance_metrics() -> Dict[str, Any]:
    """Get performance metrics safely."""
    return safe_engine_service.get_performance_metrics()

def is_live_mode() -> bool:
    """Check if engine is in live mode."""
    try:
        return safe_engine_service.live_data_enabled
    except:
        return False

def get_data_source() -> str:
    """Get current data source."""
    try:
        if safe_engine_service.live_data_enabled and safe_engine_service.engine_initialized:
            return 'LIVE'
        return 'MOCK'
    except:
        return 'FALLBACK'

# Export the safe wrapper as the main engine service
engine_service = safe_engine_service