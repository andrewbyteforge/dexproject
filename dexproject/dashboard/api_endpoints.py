"""
API Endpoints Views - Real-time Data & JSON Responses

Contains all JSON API endpoints, real-time streaming endpoints, and AJAX handlers.
Split from the original monolithic views.py file (1400+ lines) for better organization.

File: dexproject/dashboard/api_endpoints.py
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Union, List
from decimal import Decimal

from django.http import HttpResponse, StreamingHttpResponse, JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings

from .models import BotConfiguration, TradingSession, UserProfile
from .engine_service import engine_service

logger = logging.getLogger(__name__)


# =========================================================================
# UTILITY FUNCTIONS FOR API ENDPOINTS
# =========================================================================

def run_async_in_view(coro) -> Optional[Any]:
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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Async execution error: {e}", exc_info=True)
        return None


async def ensure_engine_initialized() -> None:
    """
    Ensure the Fast Lane engine is initialized.
    
    Initializes the engine if not already done and handles initialization errors
    gracefully by falling back to mock mode if necessary.
    
    Raises:
        Exception: Logs but does not re-raise engine initialization errors
    """
    if not engine_service.engine_initialized and not engine_service.mock_mode:
        try:
            success = await engine_service.initialize_engine(chain_id=1)  # Ethereum mainnet
            if success:
                logger.info("Fast Lane engine initialized successfully")
            else:
                logger.warning("Failed to initialize Fast Lane engine - falling back to mock mode")
        except Exception as e:
            logger.error(f"Engine initialization error: {e}", exc_info=True)


# =========================================================================
# SMART LANE STATUS HELPERS
# =========================================================================

def get_smart_lane_status() -> Dict[str, Any]:
    """
    Get current Smart Lane status for API responses.
    
    Returns:
        Dict containing Smart Lane status information
    """
    try:
        # Import Smart Lane components if available
        from .smart_lane_features import smart_lane_available, smart_lane_pipeline, smart_lane_metrics
        
        if not smart_lane_available:
            return {
                'status': 'UNAVAILABLE',
                'pipeline_initialized': False,
                'pipeline_active': False,
                'analyzers_count': 0,
                'analysis_ready': False,
                'capabilities': [],
                'last_analysis': None,
                '_mock': True
            }
        
        return {
            'status': 'OPERATIONAL' if smart_lane_pipeline else 'READY',
            'pipeline_initialized': smart_lane_pipeline is not None,
            'pipeline_active': smart_lane_pipeline is not None,
            'analyzers_count': 5 if smart_lane_pipeline else 0,
            'analysis_ready': smart_lane_pipeline is not None,
            'capabilities': [
                'HONEYPOT_DETECTION',
                'LIQUIDITY_ANALYSIS', 
                'SOCIAL_SENTIMENT',
                'TECHNICAL_ANALYSIS',
                'CONTRACT_SECURITY'
            ] if smart_lane_pipeline else [],
            'analyses_completed': smart_lane_metrics.get('analyses_completed', 0),
            'average_analysis_time_ms': smart_lane_metrics.get('average_analysis_time_ms', 0.0),
            'last_analysis': smart_lane_metrics.get('last_analysis'),
            'thought_log_enabled': True,
            '_mock': False
        }
        
    except ImportError:
        return {
            'status': 'UNAVAILABLE',
            'pipeline_initialized': False,
            'pipeline_active': False,
            'analyzers_count': 0,
            'analysis_ready': False,
            'capabilities': [],
            'last_analysis': None,
            '_mock': True
        }


# =========================================================================
# REAL-TIME STREAMING ENDPOINTS (SERVER-SENT EVENTS)
# =========================================================================

def metrics_stream(request: HttpRequest) -> StreamingHttpResponse:
    """
    Server-sent events endpoint for real-time trading metrics with Smart Lane integration.
    
    ENHANCED: Added Smart Lane metrics to the stream
    
    Provides continuous stream of performance metrics and engine status for real-time
    dashboard updates using server-sent events protocol.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        StreamingHttpResponse with server-sent events
    """
    def event_stream():
        """Generator for server-sent events."""
        iteration_count = 0
        max_iterations = getattr(settings, 'SSE_MAX_ITERATIONS', 150)
        
        while iteration_count < max_iterations:
            try:
                # Get current metrics and status
                metrics = engine_service.get_performance_metrics()
                status = engine_service.get_engine_status()
                smart_lane_status = get_smart_lane_status()
                
                # Format as server-sent event
                data = {
                    'timestamp': datetime.now().isoformat(),
                    
                    # Fast Lane metrics
                    'execution_time_ms': metrics.get('execution_time_ms', 0),
                    'success_rate': metrics.get('success_rate', 0),
                    'trades_per_minute': metrics.get('trades_per_minute', 0),
                    'fast_lane_active': status.get('fast_lane_active', False),
                    
                    # Smart Lane metrics (NEW)
                    'smart_lane_active': smart_lane_status.get('pipeline_initialized', False),
                    'smart_lane_analysis_time_ms': smart_lane_status.get('average_analysis_time_ms', 0),
                    'smart_lane_analyses_count': smart_lane_status.get('analyses_completed', 0),
                    'smart_lane_last_analysis': smart_lane_status.get('last_analysis'),
                    
                    # System status
                    'mempool_connected': status.get('mempool_connected', False),
                    'data_source': 'LIVE' if not metrics.get('_mock', False) else 'MOCK',
                    'pairs_monitored': status.get('pairs_monitored', 0),
                    'pending_transactions': status.get('pending_transactions', 0)
                }
                
                yield f"data: {json.dumps(data)}\n\n"
                iteration_count += 1
                
            except Exception as e:
                logger.error(f"Error in metrics stream (iteration {iteration_count}): {e}")
                error_data = {
                    'error': 'Stream error',
                    'timestamp': datetime.now().isoformat()
                }
                yield f"data: {json.dumps(error_data)}\n\n"
            
            time.sleep(2)  # Update every 2 seconds
    
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['Connection'] = 'keep-alive'
    response['Access-Control-Allow-Origin'] = '*'  # For development - restrict in production
    return response


# =========================================================================
# JSON API ENDPOINTS (Enhanced with Smart Lane)
# =========================================================================

@require_http_methods(["GET"])
@login_required
def api_engine_status(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for engine status with Fast Lane and Smart Lane integration.
    
    ENHANCED: Added Smart Lane status information
    
    Returns current engine status including Fast Lane and Smart Lane availability,
    connection states, and system health metrics.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with engine status data or error message
    """
    try:
        # Initialize engines if needed
        run_async_in_view(ensure_engine_initialized())
        
        status = engine_service.get_engine_status()
        smart_lane_status = get_smart_lane_status()
        
        # Combine status information
        combined_status = {
            **status,
            'smart_lane': smart_lane_status
        }
        
        return JsonResponse({
            'success': True,
            'data': combined_status,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"API engine status error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, status=500)


@require_http_methods(["GET"])
@login_required
def api_performance_metrics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for performance metrics with Fast Lane and Smart Lane integration.
    
    Returns comprehensive performance data from both Fast Lane and Smart Lane
    systems for dashboard display and monitoring.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with performance metrics or error message
    """
    try:
        # Get Fast Lane metrics
        fast_lane_metrics = engine_service.get_performance_metrics()
        
        # Get Smart Lane metrics
        smart_lane_status = get_smart_lane_status()
        
        # Combine metrics
        combined_metrics = {
            'fast_lane': fast_lane_metrics,
            'smart_lane': {
                'analyses_completed': smart_lane_status.get('analyses_completed', 0),
                'average_analysis_time_ms': smart_lane_status.get('average_analysis_time_ms', 0.0),
                'last_analysis': smart_lane_status.get('last_analysis'),
                'pipeline_active': smart_lane_status.get('pipeline_active', False)
            },
            'system': {
                'data_source': 'LIVE' if not fast_lane_metrics.get('_mock', False) else 'MOCK',
                'timestamp': datetime.now().isoformat()
            }
        }
        
        return JsonResponse({
            'success': True,
            'metrics': combined_metrics
        })
        
    except Exception as e:
        logger.error(f"API performance metrics error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'metrics': {
                'fast_lane': {'_mock': True, '_error': True},
                'smart_lane': {'_mock': True, '_error': True},
                'system': {'data_source': 'ERROR', 'timestamp': datetime.now().isoformat()}
            }
        }, status=500)


@require_POST
@csrf_exempt
def api_set_trading_mode(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to set trading mode (Fast Lane or Smart Lane).
    
    Updates the user's preferred trading mode and initializes the appropriate
    engine components based on the selection.
    
    Args:
        request: Django HTTP request object containing mode data
        
    Returns:
        JsonResponse indicating success or failure of mode change
    """
    try:
        data = json.loads(request.body)
        mode = data.get('mode', '').upper()
        
        if mode not in ['FAST_LANE', 'SMART_LANE']:
            return JsonResponse({
                'success': False,
                'error': 'Invalid mode. Must be FAST_LANE or SMART_LANE'
            }, status=400)
        
        logger.info(f"Setting trading mode to {mode} for user: {request.user}")
        
        # Update user profile if exists
        try:
            profile, created = UserProfile.objects.get_or_create(user=request.user)
            profile.preferred_trading_mode = mode
            profile.save()
            logger.debug(f"Updated user profile with mode: {mode}")
        except Exception as e:
            logger.warning(f"Could not update user profile: {e}")
        
        # Initialize appropriate engine
        if mode == 'FAST_LANE':
            success = run_async_in_view(ensure_engine_initialized())
            if not success and not engine_service.mock_mode:
                return JsonResponse({
                    'success': False,
                    'error': 'Fast Lane engine initialization failed'
                }, status=500)
        
        elif mode == 'SMART_LANE':
            # Import and initialize Smart Lane
            try:
                from .smart_lane_features import initialize_smart_lane_pipeline
                success = run_async_in_view(initialize_smart_lane_pipeline())
                if not success:
                    return JsonResponse({
                        'success': False,
                        'error': 'Smart Lane pipeline initialization failed'
                    }, status=500)
            except ImportError:
                return JsonResponse({
                    'success': False,
                    'error': 'Smart Lane not available'
                }, status=503)
        
        return JsonResponse({
            'success': True,
            'mode': mode,
            'message': f'Trading mode set to {mode}',
            'timestamp': datetime.now().isoformat()
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    
    except Exception as e:
        logger.error(f"Error setting trading mode: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Internal server error'
        }, status=500)


@require_POST
@csrf_exempt
def api_smart_lane_analyze(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to run Smart Lane analysis on a token.
    
    Performs comprehensive token analysis using the Smart Lane pipeline
    and returns detailed analysis results with risk assessment.
    
    Args:
        request: Django HTTP request object containing token data
        
    Returns:
        JsonResponse with analysis results or error message
    """
    try:
        data = json.loads(request.body)
        token_address = data.get('token_address', '').strip()
        
        if not token_address:
            return JsonResponse({
                'success': False,
                'error': 'Token address is required'
            }, status=400)
        
        logger.info(f"Smart Lane analysis requested for token: {token_address}")
        
        # Import Smart Lane components
        try:
            from .smart_lane_features import run_smart_lane_analysis
            
            # Run analysis
            analysis_result = run_async_in_view(run_smart_lane_analysis(token_address))
            
            if analysis_result is None:
                return JsonResponse({
                    'success': False,
                    'error': 'Analysis failed or timed out'
                }, status=500)
            
            return JsonResponse({
                'success': True,
                'analysis_id': analysis_result.get('analysis_id'),
                'token_address': token_address,
                'results': analysis_result,
                'timestamp': datetime.now().isoformat()
            })
            
        except ImportError:
            return JsonResponse({
                'success': False,
                'error': 'Smart Lane not available'
            }, status=503)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    
    except Exception as e:
        logger.error(f"Error in Smart Lane analysis: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Analysis failed'
        }, status=500)


@require_http_methods(["GET"])
def api_get_thought_log(request: HttpRequest, analysis_id: str) -> JsonResponse:
    """
    API endpoint to retrieve Smart Lane thought log for an analysis.
    
    Returns the detailed thought process and reasoning steps for a specific
    Smart Lane analysis, providing transparency into AI decision-making.
    
    Args:
        request: Django HTTP request object
        analysis_id: Unique identifier for the analysis
        
    Returns:
        JsonResponse with thought log data or error message
    """
    try:
        logger.debug(f"Thought log requested for analysis: {analysis_id}")
        
        # Import Smart Lane components
        try:
            from .smart_lane_features import get_thought_log
            
            thought_log = get_thought_log(analysis_id)
            
            if thought_log is None:
                return JsonResponse({
                    'success': False,
                    'error': 'Thought log not found'
                }, status=404)
            
            return JsonResponse({
                'success': True,
                'analysis_id': analysis_id,
                'thought_log': thought_log,
                'timestamp': datetime.now().isoformat()
            })
            
        except ImportError:
            return JsonResponse({
                'success': False,
                'error': 'Smart Lane not available'
            }, status=503)
        
    except Exception as e:
        logger.error(f"Error retrieving thought log: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve thought log'
        }, status=500)


# =========================================================================
# SYSTEM HEALTH AND TESTING ENDPOINTS
# =========================================================================

@require_http_methods(["GET"])
def health_check(request: HttpRequest) -> JsonResponse:
    """
    System health check endpoint.
    
    Provides basic system health information including database connectivity,
    engine status, and overall system readiness for trading operations.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with health check data
    """
    try:
        # Check database connectivity
        db_healthy = True
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            db_healthy = False
        
        # Check engine status
        engine_status = engine_service.get_engine_status()
        engine_healthy = engine_status.get('fast_lane_active', False) or engine_service.mock_mode
        
        # Check Smart Lane status
        smart_lane_status = get_smart_lane_status()
        smart_lane_healthy = smart_lane_status.get('status') in ['OPERATIONAL', 'READY', 'UNAVAILABLE']
        
        # Overall health
        overall_healthy = db_healthy and (engine_healthy or smart_lane_healthy)
        
        return JsonResponse({
            'healthy': overall_healthy,
            'timestamp': datetime.now().isoformat(),
            'components': {
                'database': {
                    'healthy': db_healthy,
                    'status': 'OK' if db_healthy else 'ERROR'
                },
                'fast_lane': {
                    'healthy': engine_healthy,
                    'status': 'ACTIVE' if engine_status.get('fast_lane_active', False) else 'MOCK' if engine_service.mock_mode else 'INACTIVE'
                },
                'smart_lane': {
                    'healthy': smart_lane_healthy,
                    'status': smart_lane_status.get('status', 'UNKNOWN')
                }
            }
        })
        
    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return JsonResponse({
            'healthy': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, status=500)


@require_http_methods(["GET"])
def engine_test(request: HttpRequest) -> JsonResponse:
    """
    Engine testing endpoint for development and debugging.
    
    Provides detailed engine testing and diagnostic information including
    performance metrics, connection status, and configuration details.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with engine test results
    """
    try:
        logger.info("Engine test endpoint accessed")
        
        # Initialize engine if needed
        run_async_in_view(ensure_engine_initialized())
        
        # Collect test data
        test_results = {
            'fast_lane': {
                'status': engine_service.get_engine_status(),
                'metrics': engine_service.get_performance_metrics(),
                'initialized': engine_service.engine_initialized,
                'mock_mode': engine_service.mock_mode
            },
            'smart_lane': get_smart_lane_status(),
            'system': {
                'settings': {
                    'debug': settings.DEBUG,
                    'testnet_mode': getattr(settings, 'TESTNET_MODE', True),
                    'chain_id': getattr(settings, 'DEFAULT_CHAIN_ID', 84532)
                },
                'timestamp': datetime.now().isoformat()
            }
        }
        
        return JsonResponse({
            'success': True,
            'test_results': test_results
        })
        
    except Exception as e:
        logger.error(f"Engine test error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, status=500)