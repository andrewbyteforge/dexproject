"""
Dashboard Views Utilities

Shared utility functions and helpers for dashboard views.
Split from the original monolithic views.py file for better organization.

File: dashboard/views/utils.py
"""

import asyncio
import logging
from typing import Any, Optional, Coroutine

logger = logging.getLogger(__name__)


async def ensure_engine_initialized() -> None:
    """
    Ensure the Fast Lane engine is initialized.
    
    Initializes the engine if not already done and handles initialization errors
    gracefully by falling back to mock mode if necessary.
    
    Raises:
        Exception: Logs but does not re-raise engine initialization errors
    """
    from ..engine_service import engine_service
    
    if not engine_service.engine_initialized and not engine_service.mock_mode:
        try:
            success = await engine_service.initialize_engine(chain_id=1)  # Ethereum mainnet
            if success:
                logger.info("Fast Lane engine initialized successfully")
            else:
                logger.warning("Failed to initialize Fast Lane engine - falling back to mock mode")
        except Exception as e:
            logger.error(f"Engine initialization error: {e}", exc_info=True)


def run_async_in_view(coro: Coroutine) -> Optional[Any]:
    """
    Helper to run async code in Django views.
    
    Creates a new event loop to execute async functions within synchronous
    Django view functions. Fixed to handle Django's multi-threaded environment.
    
    Args:
        coro: Coroutine to execute
        
    Returns:
        Result of the coroutine execution, or None if failed
    """
    try:
        # In Django's multi-threaded environment, we need to create a new event loop
        # for each thread since threads don't have event loops by default
        
        # First, try to see if there's already a running loop
        try:
            current_loop = asyncio.get_running_loop()
            # If there's a running loop, we need to run in a different thread
            import concurrent.futures
            import threading
            
            def run_in_new_loop():
                """Run the coroutine in a new event loop in a new thread."""
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_in_new_loop)
                return future.result(timeout=10)  # 10 second timeout
                
        except RuntimeError:
            # No running loop, we can create one and run directly
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
                # Don't leave the loop set for the thread
                asyncio.set_event_loop(None)
                
    except Exception as e:
        logger.error(f"Error running async code in view: {e}", exc_info=True)
        # Final fallback - try asyncio.run which creates its own loop
        try:
            return asyncio.run(coro)
        except Exception as fallback_error:
            logger.error(f"Fallback async execution also failed: {fallback_error}")
            # Return None gracefully so the application doesn't crash
            return None