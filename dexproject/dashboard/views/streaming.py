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
    
    Streams live trading metrics from the Fast Lane engine to the dashboard.
    Falls back to mock data if engine is unavailable.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        StreamingHttpResponse with Server-Sent Events format
    """
    def event_stream() -> Generator[str, None, None]:
        """
        Generator function for SSE data stream with Fast Lane integration.
        
        Yields formatted SSE data with real-time metrics and status updates.
        Includes connection confirmation, periodic updates, and error handling.
        
        Yields:
            str: Formatted SSE data strings
        """
        try:
            # Initialize engine if needed
            run_async_in_view(ensure_engine_initialized())
            
            # Send initial connection confirmation
            initial_status = engine_service.get_engine_status()
            initial_data = {
                'type': 'connection',
                'status': 'connected',
                'engine_status': initial_status,
                'data_source': 'LIVE' if not initial_status.get('_mock', False) else 'MOCK',
                'timestamp': datetime.now().isoformat()
            }
            yield f"data: {json.dumps(initial_data)}\n\n"
            
            # Stream metrics updates
            counter = 0
            max_iterations = getattr(settings, 'SSE_MAX_ITERATIONS', 100)
            update_interval = getattr(settings, 'DASHBOARD_SSE_UPDATE_INTERVAL', 2)
            
            while counter < max_iterations:  # Limit to prevent long-running processes
                try:
                    # Get real-time metrics from engine service
                    metrics = engine_service.get_performance_metrics()
                    status = engine_service.get_engine_status()
                    
                    message_data = {
                        'type': 'metrics_update',
                        'timestamp': datetime.now().isoformat(),
                        'metrics': {
                            'execution_time_ms': metrics.get('execution_time_ms', 0),
                            'success_rate': metrics.get('success_rate', 0),
                            'trades_per_minute': metrics.get('trades_per_minute', 0),
                            'risk_cache_hits': metrics.get('risk_cache_hits', 0),
                            'mempool_latency_ms': metrics.get('mempool_latency_ms', 0),
                            'gas_optimization_ms': metrics.get('gas_optimization_ms', 0),
                            'total_executions': metrics.get('total_executions', 0),
                            'is_live': not metrics.get('_mock', False)
                        },
                        'status': {
                            'status': status.get('status', 'UNKNOWN'),
                            'fast_lane_active': status.get('fast_lane_active', False),
                            'smart_lane_active': status.get('smart_lane_active', False),
                            'mempool_connected': status.get('mempool_connected', False),
                            'uptime_seconds': status.get('uptime_seconds', 0),
                            'is_live': not status.get('_mock', False)
                        },
                        'data_source': 'LIVE' if not metrics.get('_mock', False) else 'MOCK'
                    }
                    
                    yield f"data: {json.dumps(message_data)}\n\n"
                    time.sleep(update_interval)  # Update interval from settings
                    counter += 1
                    
                except Exception as stream_error:
                    logger.error(f"Error in metrics stream iteration: {stream_error}")
                    # Send error message to client
                    error_data = {
                        'type': 'error',
                        'message': 'Metrics stream interrupted',
                        'timestamp': datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                    break
                    
        except Exception as e:
            logger.error(f"Critical error in metrics stream: {e}", exc_info=True)
            # Send final error message
            error_data = {
                'type': 'fatal_error',
                'message': 'Metrics stream failed',
                'timestamp': datetime.now().isoformat()
            }
            yield f"data: {json.dumps(error_data)}\n\n"
    
    # Return SSE response with proper headers
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['Access-Control-Allow-Origin'] = '*'
    response['X-Accel-Buffering'] = 'no'
    return response


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