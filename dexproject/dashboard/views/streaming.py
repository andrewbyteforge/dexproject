"""
Real-time Streaming Views

Handles Server-Sent Events (SSE) streaming for real-time dashboard updates.
Split from the original monolithic views.py file for better organization.

File: dashboard/views/streaming.py
"""

import json
import logging
import time
from datetime import datetime
from typing import Generator, Dict, Any

from django.http import StreamingHttpResponse, HttpRequest
from django.conf import settings

from ..engine_service import engine_service
from .utils import ensure_engine_initialized, run_async_in_view

logger = logging.getLogger(__name__)


def metrics_stream(request: HttpRequest) -> StreamingHttpResponse:
    """
    Server-Sent Events endpoint for real-time metrics with Fast Lane integration.
    
    Enhanced with comprehensive error handling, configuration checks, and proper
    resource management to prevent server hanging issues.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        StreamingHttpResponse with Server-Sent Events format
    """
    # Start time for performance monitoring
    stream_start_time = time.time()
    user_identifier = getattr(request.user, 'username', 'anonymous')
    
    logger.info(f"[SSE] Starting metrics stream for user: {user_identifier}")
    
    def event_stream() -> Generator[str, None, None]:
        """
        Generator function for SSE data stream with comprehensive error handling.
        
        Yields:
            str: Formatted SSE data strings
        """
        counter = 0
        error_count = 0
        max_consecutive_errors = 5
        consecutive_errors = 0
        
        try:
            # Check if SSE is enabled
            sse_enabled = getattr(settings, 'SSE_ENABLED', True)
            if not sse_enabled:
                logger.info(f"[SSE] SSE is disabled in configuration for user: {user_identifier}")
                yield f"data: {json.dumps({'type': 'disabled', 'message': 'SSE is disabled in server configuration', 'timestamp': datetime.now().isoformat()})}\n\n"
                return
            
            # Get configuration values with defaults
            max_iterations = getattr(settings, 'SSE_MAX_ITERATIONS', 10)  # Reduced from 100
            update_interval = getattr(settings, 'DASHBOARD_SSE_UPDATE_INTERVAL', 3)  # Increased from 2
            
            logger.info(f"[SSE] Configuration - Max iterations: {max_iterations}, Update interval: {update_interval}s")
            
            # Initialize engine if needed (with timeout)
            engine_initialized = False
            try:
                logger.debug("[SSE] Attempting engine initialization...")
                # Use a timeout to prevent hanging on initialization
                from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
                
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(run_async_in_view, ensure_engine_initialized())
                    try:
                        future.result(timeout=5)  # 5 second timeout
                        engine_initialized = True
                        logger.info("[SSE] Engine initialized successfully")
                    except FutureTimeoutError:
                        logger.warning("[SSE] Engine initialization timed out after 5 seconds")
                    except Exception as e:
                        logger.warning(f"[SSE] Engine initialization failed: {e}")
            except Exception as e:
                logger.error(f"[SSE] Critical error during engine initialization: {e}", exc_info=True)
            
            # Send initial connection confirmation
            initial_status = {'status': 'initializing', '_mock': True}
            data_source = 'MOCK'
            
            if engine_initialized:
                try:
                    initial_status = engine_service.get_engine_status()
                    data_source = 'LIVE' if not initial_status.get('_mock', False) else 'MOCK'
                    logger.debug(f"[SSE] Engine status retrieved: {initial_status.get('status', 'unknown')}")
                except Exception as e:
                    logger.warning(f"[SSE] Could not get engine status: {e}")
            
            initial_data = {
                'type': 'connection',
                'status': 'connected',
                'engine_status': initial_status.get('status', 'unavailable'),
                'engine_initialized': engine_initialized,
                'data_source': data_source,
                'timestamp': datetime.now().isoformat(),
                'config': {
                    'max_iterations': max_iterations,
                    'update_interval': update_interval
                }
            }
            
            yield f"data: {json.dumps(initial_data)}\n\n"
            logger.info(f"[SSE] Initial connection sent to user: {user_identifier} (Data source: {data_source})")
            
            # Main streaming loop
            while counter < max_iterations:
                loop_start = time.time()
                
                try:
                    # Prepare metrics data
                    metrics = None
                    status = None
                    is_mock = True
                    
                    if engine_initialized:
                        try:
                            # Get metrics with timeout
                            metrics = engine_service.get_performance_metrics()
                            status = engine_service.get_engine_status()
                            is_mock = status.get('_mock', False)
                            consecutive_errors = 0  # Reset on success
                            
                        except Exception as e:
                            consecutive_errors += 1
                            error_count += 1
                            logger.warning(f"[SSE] Error getting metrics (attempt {counter}, error {error_count}): {e}")
                            
                            if consecutive_errors >= max_consecutive_errors:
                                logger.error(f"[SSE] Max consecutive errors ({max_consecutive_errors}) reached. Terminating stream.")
                                yield f"data: {json.dumps({'type': 'error', 'message': 'Too many consecutive errors', 'timestamp': datetime.now().isoformat()})}\n\n"
                                break
                    
                    # Use fallback data if needed
                    if metrics is None:
                        metrics = {
                            'execution_time_ms': 0,
                            'success_rate': 0,
                            'trades_per_minute': 0,
                            'last_update': datetime.now().isoformat()
                        }
                    
                    if status is None:
                        status = {
                            'fast_lane_active': False,
                            'smart_lane_active': False,
                            'mempool_connected': False,
                            'pairs_monitored': 0,
                            'pending_transactions': 0,
                            '_mock': True
                        }
                    
                    # Construct message
                    message_data = {
                        'type': 'metrics_update',
                        'timestamp': datetime.now().isoformat(),
                        'iteration': counter,
                        'metrics': {
                            'execution_time_ms': metrics.get('execution_time_ms', 0),
                            'success_rate': metrics.get('success_rate', 0),
                            'trades_per_minute': metrics.get('trades_per_minute', 0),
                            'fast_lane_active': status.get('fast_lane_active', False),
                            'smart_lane_active': status.get('smart_lane_active', False),
                            'mempool_connected': status.get('mempool_connected', False),
                            'pairs_monitored': status.get('pairs_monitored', 0),
                            'pending_transactions': status.get('pending_transactions', 0)
                        },
                        'data_source': 'LIVE' if not is_mock else 'MOCK',
                        'health': {
                            'errors_total': error_count,
                            'consecutive_errors': consecutive_errors,
                            'uptime_seconds': int(time.time() - stream_start_time)
                        }
                    }
                    
                    yield f"data: {json.dumps(message_data)}\n\n"
                    
                    # Periodic logging
                    if counter % 10 == 0:
                        logger.debug(f"[SSE] Stream healthy - iteration {counter} for user {user_identifier} (errors: {error_count})")
                    
                    counter += 1
                    
                    # Calculate sleep time to maintain consistent interval
                    loop_duration = time.time() - loop_start
                    sleep_time = max(0, update_interval - loop_duration)
                    
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    else:
                        logger.warning(f"[SSE] Loop took {loop_duration:.2f}s, longer than interval {update_interval}s")
                    
                except KeyboardInterrupt:
                    logger.info(f"[SSE] Stream interrupted by user for: {user_identifier}")
                    break
                    
                except Exception as e:
                    error_count += 1
                    consecutive_errors += 1
                    logger.error(f"[SSE] Error in stream loop (iteration {counter}): {e}", exc_info=True)
                    
                    # Send error notification to client
                    error_data = {
                        'type': 'error',
                        'error': 'Stream error',
                        'message': str(e),
                        'timestamp': datetime.now().isoformat(),
                        'iteration': counter,
                        'will_retry': consecutive_errors < max_consecutive_errors
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                    
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(f"[SSE] Terminating stream due to excessive errors for user: {user_identifier}")
                        break
                    
                    # Brief pause before retry
                    time.sleep(1)
            
            # Send stream end notification
            stream_duration = time.time() - stream_start_time
            final_data = {
                'type': 'stream_end',
                'message': 'Stream ended normally',
                'total_iterations': counter,
                'total_errors': error_count,
                'duration_seconds': int(stream_duration),
                'timestamp': datetime.now().isoformat()
            }
            yield f"data: {json.dumps(final_data)}\n\n"
            
            logger.info(f"[SSE] Stream ended normally for user {user_identifier} - "
                       f"Duration: {stream_duration:.1f}s, Iterations: {counter}, Errors: {error_count}")
            
        except Exception as e:
            # Catch-all for any unhandled exceptions
            logger.error(f"[SSE] Fatal error in metrics stream for user {user_identifier}: {e}", exc_info=True)
            
            try:
                error_data = {
                    'type': 'fatal_error',
                    'error': 'Fatal stream error',
                    'message': str(e),
                    'timestamp': datetime.now().isoformat()
                }
                yield f"data: {json.dumps(error_data)}\n\n"
            except Exception as json_error:
                logger.error(f"[SSE] Could not send error message: {json_error}")
                yield f"data: {{'type': 'fatal_error', 'message': 'Critical failure'}}\n\n"
        
        finally:
            # Cleanup and final logging
            stream_duration = time.time() - stream_start_time
            logger.info(f"[SSE] Stream cleanup completed for user {user_identifier} - Total duration: {stream_duration:.1f}s")
    
    # Create the streaming response
    try:
        response = StreamingHttpResponse(
            event_stream(), 
            content_type='text/event-stream'
        )
        
        # Set appropriate headers for SSE
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['X-Accel-Buffering'] = 'no'  # Disable nginx buffering
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        
        # CORS headers (restrict in production)
        if settings.DEBUG:
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Headers'] = 'Cache-Control'
        
        logger.debug(f"[SSE] Response created successfully for user: {user_identifier}")
        return response
        
    except Exception as e:
        logger.error(f"[SSE] Failed to create streaming response for user {user_identifier}: {e}", exc_info=True)
        
        # Return error response
        from django.http import JsonResponse
        return JsonResponse({
            'error': 'Failed to initialize stream',
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }, status=500)













def smart_lane_stream(request: HttpRequest) -> StreamingHttpResponse:
    """
    Server-Sent Events endpoint for real-time Smart Lane metrics.
    
    Streams Smart Lane analysis results, thought logs, and performance data.
    New endpoint for Phase 5 Smart Lane integration.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        StreamingHttpResponse with Smart Lane SSE format
    """
    def event_stream() -> Generator[str, None, None]:
        """Generator for Smart Lane SSE data stream."""
        try:
            # Import Smart Lane service (will be created)
            from ..smart_lane_service import smart_lane_service
            
            # Send initial connection confirmation
            initial_status = smart_lane_service.get_pipeline_status()
            initial_data = {
                'type': 'smart_lane_connection',
                'status': 'connected',
                'pipeline_status': initial_status,
                'data_source': 'LIVE' if not initial_status.get('_mock', False) else 'MOCK',
                'timestamp': datetime.now().isoformat()
            }
            yield f"data: {json.dumps(initial_data)}\n\n"
            
            # Stream Smart Lane updates
            counter = 0
            max_iterations = getattr(settings, 'SSE_MAX_ITERATIONS', 100)
            update_interval = getattr(settings, 'DASHBOARD_SSE_UPDATE_INTERVAL', 2)
            
            while counter < max_iterations:
                try:
                    # Get Smart Lane metrics
                    metrics = smart_lane_service.get_analysis_metrics()
                    status = smart_lane_service.get_pipeline_status()
                    thought_logs = smart_lane_service.get_recent_thought_logs(limit=3)
                    
                    message_data = {
                        'type': 'smart_lane_update',
                        'timestamp': datetime.now().isoformat(),
                        'metrics': {
                            'total_analyses': metrics.get('total_analyses', 0),
                            'successful_analyses': metrics.get('successful_analyses', 0),
                            'average_analysis_time_ms': metrics.get('average_analysis_time_ms', 0),
                            'cache_hit_ratio': metrics.get('cache_hit_ratio', 0),
                            'analyzers_active': metrics.get('analyzers_active', 0),
                            'thought_logs_generated': metrics.get('thought_logs_generated', 0),
                            'is_live': not metrics.get('_mock', False)
                        },
                        'status': {
                            'status': status.get('status', 'UNKNOWN'),
                            'pipeline_active': status.get('pipeline_active', False),
                            'analyzers_count': status.get('analyzers_count', 0),
                            'analysis_depth': status.get('analysis_depth', 'UNKNOWN'),
                            'thought_log_enabled': status.get('thought_log_enabled', False),
                            'is_live': not status.get('_mock', False)
                        },
                        'recent_thought_logs': thought_logs,
                        'data_source': 'LIVE' if not metrics.get('_mock', False) else 'MOCK'
                    }
                    
                    yield f"data: {json.dumps(message_data)}\n\n"
                    time.sleep(update_interval)
                    counter += 1
                    
                except Exception as stream_error:
                    logger.error(f"Error in Smart Lane stream iteration: {stream_error}")
                    error_data = {
                        'type': 'smart_lane_error',
                        'message': 'Smart Lane stream interrupted',
                        'timestamp': datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                    break
                    
        except ImportError:
            # Smart Lane service not available yet
            logger.info("Smart Lane service not available, sending mock data")
            yield f"data: {json.dumps(_generate_mock_smart_lane_data())}\n\n"
        except Exception as e:
            logger.error(f"Critical error in Smart Lane stream: {e}", exc_info=True)
            error_data = {
                'type': 'smart_lane_fatal_error',
                'message': 'Smart Lane stream failed',
                'timestamp': datetime.now().isoformat()
            }
            yield f"data: {json.dumps(error_data)}\n\n"
    
    # Return SSE response with proper headers
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['Access-Control-Allow-Origin'] = '*'
    response['X-Accel-Buffering'] = 'no'
    return response


def combined_stream(request: HttpRequest) -> StreamingHttpResponse:
    """
    Combined SSE stream for both Fast Lane and Smart Lane metrics.
    
    Provides a unified stream containing data from both trading modes,
    allowing the dashboard to display comprehensive real-time information.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        StreamingHttpResponse with combined SSE format
    """
    def event_stream() -> Generator[str, None, None]:
        """Generator for combined SSE data stream."""
        try:
            # Initialize both services
            run_async_in_view(ensure_engine_initialized())
            
            # Send initial connection confirmation
            fast_lane_status = engine_service.get_engine_status()
            
            try:
                from ..smart_lane_service import smart_lane_service
                smart_lane_status = smart_lane_service.get_pipeline_status()
                smart_lane_available = True
            except ImportError:
                smart_lane_status = {'status': 'UNAVAILABLE', '_mock': True}
                smart_lane_available = False
            
            initial_data = {
                'type': 'combined_connection',
                'status': 'connected',
                'fast_lane_status': fast_lane_status,
                'smart_lane_status': smart_lane_status,
                'smart_lane_available': smart_lane_available,
                'timestamp': datetime.now().isoformat()
            }
            yield f"data: {json.dumps(initial_data)}\n\n"
            
            # Stream combined updates
            counter = 0
            max_iterations = getattr(settings, 'SSE_MAX_ITERATIONS', 100)
            update_interval = getattr(settings, 'DASHBOARD_SSE_UPDATE_INTERVAL', 2)
            
            while counter < max_iterations:
                try:
                    # Get Fast Lane data
                    fast_lane_metrics = engine_service.get_performance_metrics()
                    fast_lane_status = engine_service.get_engine_status()
                    
                    # Get Smart Lane data if available
                    if smart_lane_available:
                        smart_lane_metrics = smart_lane_service.get_analysis_metrics()
                        smart_lane_status = smart_lane_service.get_pipeline_status()
                        thought_logs = smart_lane_service.get_recent_thought_logs(limit=2)
                    else:
                        smart_lane_metrics = _generate_mock_smart_lane_metrics()
                        smart_lane_status = {'status': 'UNAVAILABLE', '_mock': True}
                        thought_logs = []
                    
                    message_data = {
                        'type': 'combined_update',
                        'timestamp': datetime.now().isoformat(),
                        'fast_lane': {
                            'metrics': {
                                'execution_time_ms': fast_lane_metrics.get('execution_time_ms', 0),
                                'success_rate': fast_lane_metrics.get('success_rate', 0),
                                'trades_per_minute': fast_lane_metrics.get('trades_per_minute', 0),
                                'total_executions': fast_lane_metrics.get('total_executions', 0),
                                'is_live': not fast_lane_metrics.get('_mock', False)
                            },
                            'status': {
                                'active': fast_lane_status.get('fast_lane_active', False),
                                'mempool_connected': fast_lane_status.get('mempool_connected', False),
                                'is_live': not fast_lane_status.get('_mock', False)
                            }
                        },
                        'smart_lane': {
                            'metrics': {
                                'total_analyses': smart_lane_metrics.get('total_analyses', 0),
                                'average_analysis_time_ms': smart_lane_metrics.get('average_analysis_time_ms', 0),
                                'thought_logs_generated': smart_lane_metrics.get('thought_logs_generated', 0),
                                'is_live': not smart_lane_metrics.get('_mock', False)
                            },
                            'status': {
                                'active': smart_lane_status.get('pipeline_active', False),
                                'analyzers_count': smart_lane_status.get('analyzers_count', 0),
                                'is_live': not smart_lane_status.get('_mock', False)
                            },
                            'recent_thought_logs': thought_logs
                        },
                        'system': {
                            'smart_lane_available': smart_lane_available,
                            'phase_5_active': getattr(settings, 'SMART_LANE_ENABLED', False)
                        }
                    }
                    
                    yield f"data: {json.dumps(message_data)}\n\n"
                    time.sleep(update_interval)
                    counter += 1
                    
                except Exception as stream_error:
                    logger.error(f"Error in combined stream iteration: {stream_error}")
                    error_data = {
                        'type': 'combined_error',
                        'message': 'Combined stream interrupted',
                        'timestamp': datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                    break
                    
        except Exception as e:
            logger.error(f"Critical error in combined stream: {e}", exc_info=True)
            error_data = {
                'type': 'combined_fatal_error',
                'message': 'Combined stream failed',
                'timestamp': datetime.now().isoformat()
            }
            yield f"data: {json.dumps(error_data)}\n\n"
    
    # Return SSE response with proper headers
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['Access-Control-Allow-Origin'] = '*'
    response['X-Accel-Buffering'] = 'no'
    return response


# =========================================================================
# HELPER FUNCTIONS
# =========================================================================

def _generate_mock_smart_lane_data() -> Dict[str, Any]:
    """Generate mock Smart Lane data when service is not available."""
    return {
        'type': 'smart_lane_mock',
        'status': 'Smart Lane components not yet integrated',
        'message': 'Phase 5 integration in progress',
        'timestamp': datetime.now().isoformat()
    }


def _generate_mock_smart_lane_metrics() -> Dict[str, Any]:
    """Generate mock Smart Lane metrics for fallback."""
    return {
        'total_analyses': 0,
        'successful_analyses': 0,
        'average_analysis_time_ms': 0,
        'thought_logs_generated': 0,
        '_mock': True
    }