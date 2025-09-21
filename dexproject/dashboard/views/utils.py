"""
Fixed Views Utils - Async Safe Version

Updated utility functions for dashboard views that handle async operations
properly without causing event loop issues.

FIXED: Removed chain_id parameter from initialize_engine calls

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


async def ensure_engine_initialized() -> bool:
    """
    Ensure engine is initialized for dashboard use.
    
    FIXED: Removed chain_id parameter to match actual method signature
    
    Returns:
        True if engine initialized successfully
    """
    try:
        # Use the async initialization without chain_id parameter
        success = await engine_service.initialize_engine()
        if success:
            logger.debug("Engine initialized successfully")
        else:
            logger.warning("Engine initialization failed")
        return success
        
    except Exception as e:
        logger.error(f"Engine initialization error: {e}")
        return False


def ensure_engine_initialized_safe() -> bool:
    """
    Safe version of engine initialization that doesn't require async context.
    
    This version can be called from Django views without async issues.
    
    FIXED: Removed chain_id parameter to match actual method signature
    
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
        request: HTTP request object to modify
    """
    if not request.user.is_authenticated:
        from django.contrib.auth.models import User
        try:
            user, created = User.objects.get_or_create(
                username='demo_user',
                defaults={
                    'first_name': 'Demo',
                    'last_name': 'User',
                    'email': 'demo@example.com'
                }
            )
            request.user = user
            if created:
                logger.info("Created demo user for anonymous session")
            else:
                logger.info("Anonymous user accessing dashboard, creating demo user")
        except Exception as e:
            logger.error(f"Error creating demo user: {e}")


def get_engine_status_safe() -> Dict[str, Any]:
    """
    Get engine status safely without throwing exceptions.
    
    Returns:
        Engine status dictionary or fallback data
    """
    try:
        return engine_service.get_engine_status()
    except Exception as e:
        logger.error(f"Error getting engine status: {e}")
        return {
            'status': 'ERROR',
            'error': str(e),
            'fast_lane_active': False,
            'smart_lane_active': False,
            'mode': 'FALLBACK',
            '_mock': True
        }


def get_performance_metrics_safe() -> Dict[str, Any]:
    """
    Get performance metrics safely without throwing exceptions.
    
    Returns:
        Performance metrics dictionary or fallback data
    """
    try:
        return engine_service.get_performance_metrics()
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        return {
            'execution_time_ms': 0,
            'success_rate': 0.0,
            'trades_per_minute': 0.0,
            'error_rate': 100.0,
            'error': str(e),
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
        'supported_chains': getattr(settings, 'TARGET_CHAINS', [84532, 11155111]),
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
    
    target_chains = getattr(settings, 'TARGET_CHAINS', [84532, 11155111])
    # Convert to list of integers if it's a string
    if isinstance(target_chains, str):
        target_chains = [int(x.strip()) for x in target_chains.split(',') if x.strip()]
    
    if chain_id in target_chains:
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
            return {
                'is_live_mode': True,
                'is_running': engine_service._live_service_initialized,
                'status': 'CONNECTED',
                'timestamp': '2025-09-21T10:00:00Z'
            }
        else:
            return {
                'is_live_mode': False,
                'is_running': False,
                'status': 'MOCK_MODE',
                'timestamp': '2025-09-21T10:00:00Z'
            }
    except Exception as e:
        logger.error(f"Failed to get live data status: {e}")
        return {
            'is_live_mode': False,
            'is_running': False,
            'error': str(e),
            'status': 'ERROR',
            'timestamp': '2025-09-21T10:00:00Z'
        }


# =============================================================================
# BACKWARD COMPATIBILITY
# =============================================================================

# Keep original function names for backward compatibility
def ensure_engine_initialized_original() -> bool:
    """Backward compatibility wrapper."""
    return ensure_engine_initialized_safe()


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