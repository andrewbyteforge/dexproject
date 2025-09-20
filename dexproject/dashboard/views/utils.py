"""
Fixed Views Utils - Async Safe Version

Updated utility functions for dashboard views that handle async operations
properly without causing event loop issues.

File: dashboard/views/utils.py
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from django.http import HttpRequest
from django.contrib.auth.models import User
from django.conf import settings

from ..engine_service import engine_service, ensure_engine_initialized_sync

logger = logging.getLogger(__name__)


async def ensure_engine_initialized(chain_id: Optional[int] = None) -> bool:
    """
    Ensure engine is initialized for dashboard use.
    
    Args:
        chain_id: Optional chain ID for initialization
        
    Returns:
        True if engine initialized successfully
    """
    try:
        # Use the async-safe initialization
        success = await engine_service.initialize_engine(chain_id=chain_id)
        if success:
            logger.debug(f"Engine initialized successfully for chain {chain_id}")
        else:
            logger.warning(f"Engine initialization failed for chain {chain_id}")
        return success
        
    except Exception as e:
        logger.error(f"Engine initialization error: {e}")
        return False


def ensure_engine_initialized_safe(chain_id: Optional[int] = None) -> bool:
    """
    Safe version of engine initialization that doesn't require async context.
    
    This version can be called from Django views without async issues.
    
    Args:
        chain_id: Optional chain ID for initialization
        
    Returns:
        Current initialization status
    """
    try:
        # Check if already initialized
        if engine_service.engine_initialized:
            return True
        
        # Try to initialize in background if possible
        return ensure_engine_initialized_sync()
        
    except Exception as e:
        logger.error(f"Safe engine initialization error: {e}")
        return False


def run_async_in_view(coro):
    """
    Safely run async coroutine in Django view context.
    
    Args:
        coro: Async coroutine to run
        
    Returns:
        Result of coroutine or None if failed
    """
    try:
        # Check if there's already a running event loop
        try:
            current_loop = asyncio.get_running_loop()
            logger.warning("Event loop already running - cannot run async operation")
            return None
        except RuntimeError:
            # No running loop - safe to create new one
            pass
        
        # Run the coroutine in a new event loop
        return asyncio.run(coro)
        
    except Exception as e:
        logger.error(f"Async operation failed: {e}")
        return None


def handle_anonymous_user(request: HttpRequest) -> None:
    """
    Handle anonymous user requests by creating a demo user if needed.
    
    Args:
        request: Django HTTP request object
    """
    if not request.user.is_authenticated:
        try:
            # Create or get demo user
            demo_user, created = User.objects.get_or_create(
                username='demo_user',
                defaults={
                    'email': 'demo@example.com',
                    'first_name': 'Demo',
                    'last_name': 'User'
                }
            )
            
            # Log in the demo user
            from django.contrib.auth import login
            login(request, demo_user)
            
            if created:
                logger.info("Created new demo user for anonymous access")
            else:
                logger.debug("Using existing demo user for anonymous access")
                
        except Exception as e:
            logger.error(f"Failed to handle anonymous user: {e}")


def get_engine_status_safe() -> Dict[str, Any]:
    """
    Get engine status safely without async issues.
    
    Returns:
        Engine status dictionary
    """
    try:
        return engine_service.get_engine_status()
    except Exception as e:
        logger.error(f"Failed to get engine status: {e}")
        return {
            'timestamp': '2025-09-20T10:00:00Z',
            'status': 'ERROR',
            'error': str(e),
            'initialized': False,
            'live_mode': False,
            'is_live': False,
            '_mock': True
        }


def get_performance_metrics_safe() -> Dict[str, Any]:
    """
    Get performance metrics safely without async issues.
    
    Returns:
        Performance metrics dictionary
    """
    try:
        return engine_service.get_performance_metrics()
    except Exception as e:
        logger.error(f"Failed to get performance metrics: {e}")
        return {
            'timestamp': '2025-09-20T10:00:00Z',
            'execution_time_ms': 0,
            'success_rate': 0,
            'trades_per_minute': 0,
            'total_executions': 0,
            'data_source': 'ERROR',
            'error': str(e),
            'is_live': False,
            '_mock': True
        }


def get_user_context(request: HttpRequest) -> Dict[str, Any]:
    """
    Get user context for dashboard views.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        Dictionary containing user context
    """
    return {
        'user': request.user,
        'is_authenticated': request.user.is_authenticated,
        'username': request.user.username if request.user.is_authenticated else 'Anonymous',
        'is_demo_user': request.user.username == 'demo_user' if request.user.is_authenticated else False
    }


def get_system_context() -> Dict[str, Any]:
    """
    Get system context for dashboard views.
    
    Returns:
        Dictionary containing system context
    """
    return {
        'debug': settings.DEBUG,
        'live_mode': engine_service.live_data_enabled,
        'mock_mode': engine_service.mock_mode,
        'supported_chains': getattr(settings, 'SUPPORTED_CHAINS', []),
        'default_chain': getattr(settings, 'DEFAULT_CHAIN_ID', 84532),
        'api_keys_configured': {
            'alchemy': bool(getattr(settings, 'ALCHEMY_API_KEY', '')),
            'ankr': bool(getattr(settings, 'ANKR_API_KEY', '')),
            'infura': bool(getattr(settings, 'INFURA_PROJECT_ID', ''))
        }
    }


def safe_async_call(async_func, *args, **kwargs):
    """
    Safely call an async function from sync context.
    
    Args:
        async_func: Async function to call
        *args: Positional arguments
        **kwargs: Keyword arguments
        
    Returns:
        Result of async function or None if failed
    """
    try:
        # Check for running event loop
        try:
            asyncio.get_running_loop()
            logger.warning("Cannot run async function - event loop already running")
            return None
        except RuntimeError:
            # No loop running - safe to proceed
            pass
        
        # Create coroutine and run it
        coro = async_func(*args, **kwargs)
        return asyncio.run(coro)
        
    except Exception as e:
        logger.error(f"Safe async call failed: {e}")
        return None


def validate_chain_id(chain_id: Optional[int]) -> int:
    """
    Validate and return a proper chain ID.
    
    Args:
        chain_id: Chain ID to validate
        
    Returns:
        Valid chain ID
    """
    if chain_id is None:
        return getattr(settings, 'DEFAULT_CHAIN_ID', 84532)
    
    supported_chains = getattr(settings, 'SUPPORTED_CHAINS', [84532, 11155111])
    
    if chain_id in supported_chains:
        return chain_id
    
    logger.warning(f"Chain ID {chain_id} not supported, using default")
    return getattr(settings, 'DEFAULT_CHAIN_ID', 84532)


def get_live_data_status() -> Dict[str, Any]:
    """
    Get live data status safely.
    
    Returns:
        Live data status dictionary
    """
    try:
        # Try to get live service
        live_service = engine_service._get_live_service()
        if live_service:
            return live_service.get_live_status()
        else:
            return {
                'is_live_mode': False,
                'is_running': False,
                'error': 'Live service not available',
                'timestamp': '2025-09-20T10:00:00Z'
            }
    except Exception as e:
        logger.error(f"Failed to get live data status: {e}")
        return {
            'is_live_mode': False,
            'is_running': False,
            'error': str(e),
            'timestamp': '2025-09-20T10:00:00Z'
        }


# =============================================================================
# BACKWARD COMPATIBILITY
# =============================================================================

# Keep original function names for backward compatibility
def ensure_engine_initialized_original(chain_id: Optional[int] = None) -> bool:
    """Backward compatibility wrapper."""
    return ensure_engine_initialized_safe(chain_id)


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'ensure_engine_initialized',
    'ensure_engine_initialized_safe', 
    'run_async_in_view',
    'handle_anonymous_user',
    'get_engine_status_safe',
    'get_performance_metrics_safe',
    'get_user_context',
    'get_system_context',
    'safe_async_call',
    'validate_chain_id',
    'get_live_data_status'
]