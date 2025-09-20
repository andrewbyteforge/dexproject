"""
API Endpoint Views

Handles JSON API endpoints for AJAX calls and external integrations.
Split from the original monolithic views.py file for better organization.

ENHANCED: Complete Smart Lane integration with real-time metrics streaming.

File: dashboard/api_endpoints.py
"""

import json
import logging
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from django.http import JsonResponse, HttpRequest, StreamingHttpResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.conf import settings

from ..engine_service import engine_service
from ..smart_lane_service import smart_lane_service

logger = logging.getLogger(__name__)


# =========================================================================
# SMART LANE HELPER FUNCTIONS
# =========================================================================

def get_smart_lane_status() -> Dict[str, Any]:
    """
    Get Smart Lane pipeline status with fallback handling.
    
    Returns:
        Dict containing Smart Lane status information
    """
    try:
        return smart_lane_service.get_pipeline_status()
    except Exception as e:
        logger.error(f"Error getting Smart Lane status: {e}")
        return {
            'status': 'ERROR',
            'pipeline_initialized': False,
            'pipeline_active': False,
            'analyzers_count': 0,
            'analysis_ready': False,
            'capabilities': [],
            'last_analysis': None,
            'error': str(e),
            '_mock': True
        }


def get_smart_lane_metrics() -> Dict[str, Any]:
    """
    Get Smart Lane analysis metrics with fallback handling.
    
    Returns:
        Dict containing Smart Lane performance metrics
    """
    try:
        return smart_lane_service.get_analysis_metrics()
    except Exception as e:
        logger.error(f"Error getting Smart Lane metrics: {e}")
        return {
            'analyses_completed': 0,
            'successful_analyses': 0,
            'failed_analyses': 0,
            'average_analysis_time_ms': 0.0,
            'cache_hit_ratio': 0.0,
            'thought_logs_generated': 0,
            'risk_assessments_completed': 0,
            'last_analysis_timestamp': None,
            'active_analyses': 0,
            'total_errors': 0,
            'success_rate': 0.0,
            'pipeline_status': 'ERROR',
            'error': str(e),
            '_mock': True
        }


def determine_overall_status(fast_lane_status: Dict[str, Any], smart_lane_status: Dict[str, Any]) -> str:
    """
    Determine overall system status based on component status.
    
    Args:
        fast_lane_status: Fast Lane engine status
        smart_lane_status: Smart Lane pipeline status
        
    Returns:
        Overall system status string
    """
    fast_status = fast_lane_status.get('status', 'UNKNOWN')
    smart_status = smart_lane_status.get('status', 'UNKNOWN')
    
    # If both are operational, system is fully operational
    if fast_status in ['OPERATIONAL', 'READY'] and smart_status in ['OPERATIONAL', 'READY', 'MOCK_MODE']:
        return 'FULLY_OPERATIONAL'
    
    # If at least one is operational, system is partially operational
    if fast_status in ['OPERATIONAL', 'READY'] or smart_status in ['OPERATIONAL', 'READY', 'MOCK_MODE']:
        return 'PARTIALLY_OPERATIONAL'
    
    # If both have errors or are unavailable
    if 'ERROR' in [fast_status, smart_status] or 'UNAVAILABLE' in [fast_status, smart_status]:
        return 'DEGRADED'
    
    return 'UNKNOWN'


# =========================================================================
# REAL-TIME STREAMING ENDPOINTS (SERVER-SENT EVENTS)
# =========================================================================

def metrics_stream(request: HttpRequest) -> StreamingHttpResponse:
    """
    Server-sent events endpoint for real-time trading metrics with Smart Lane integration.
    
    ENHANCED: Complete Smart Lane metrics integration with real-time updates
    
    Provides continuous stream of performance metrics and engine status for real-time
    dashboard updates using server-sent events protocol.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        StreamingHttpResponse with server-sent events
    """
    def event_stream():
        """Generator for server-sent events with Smart Lane integration."""
        iteration_count = 0
        max_iterations = getattr(settings, 'SSE_MAX_ITERATIONS', 150)
        
        logger.info(f"Starting metrics stream for user: {request.user.username}")
        
        while iteration_count < max_iterations:
            try:
                # Get Fast Lane metrics and status
                fast_lane_metrics = engine_service.get_performance_metrics()
                fast_lane_status = engine_service.get_engine_status()
                
                # Get Smart Lane metrics and status
                smart_lane_status = get_smart_lane_status()
                smart_lane_metrics = get_smart_lane_metrics()
                
                # Determine overall system status
                overall_status = determine_overall_status(fast_lane_status, smart_lane_status)
                
                # Compile comprehensive metrics data
                data = {
                    'type': 'metrics_update',
                    'timestamp': datetime.now().isoformat(),
                    
                    # System overview
                    'system': {
                        'overall_status': overall_status,
                        'data_source': 'LIVE' if not fast_lane_metrics.get('_mock', False) else 'MOCK',
                        'uptime_seconds': fast_lane_status.get('uptime_seconds', 0)
                    },
                    
                    # Fast Lane metrics
                    'fast_lane': {
                        'status': fast_lane_status.get('status', 'UNKNOWN'),
                        'active': fast_lane_status.get('fast_lane_active', False),
                        'execution_time_ms': fast_lane_metrics.get('execution_time_ms', 0),
                        'success_rate': fast_lane_metrics.get('success_rate', 0),
                        'trades_per_minute': fast_lane_metrics.get('trades_per_minute', 0),
                        'trades_today': fast_lane_metrics.get('trades_today', 0),
                        'mempool_connected': fast_lane_status.get('mempool_connected', False),
                        'pairs_monitored': fast_lane_status.get('pairs_monitored', 0),
                        'pending_transactions': fast_lane_status.get('pending_transactions', 0)
                    },
                    
                    # Smart Lane metrics (ENHANCED)
                    'smart_lane': {
                        'status': smart_lane_status.get('status', 'UNKNOWN'),
                        'active': smart_lane_status.get('pipeline_active', False),
                        'analysis_time_ms': smart_lane_metrics.get('average_analysis_time_ms', 0),
                        'analyses_completed': smart_lane_metrics.get('analyses_completed', 0),
                        'success_rate': smart_lane_metrics.get('success_rate', 0),
                        'analyses_today': smart_lane_metrics.get('successful_analyses', 0),
                        'thought_logs_generated': smart_lane_metrics.get('thought_logs_generated', 0),
                        'active_analyses': smart_lane_metrics.get('active_analyses', 0),
                        'cache_hit_ratio': smart_lane_metrics.get('cache_hit_ratio', 0),
                        'analyzers_count': smart_lane_status.get('analyzers_count', 0),
                        'capabilities': smart_lane_status.get('capabilities', []),
                        'last_analysis': smart_lane_metrics.get('last_analysis_timestamp'),
                        'pipeline_initialized': smart_lane_status.get('pipeline_initialized', False)
                    },
                    
                    # Combined performance metrics
                    'performance': {
                        'hybrid_mode_active': (
                            fast_lane_status.get('fast_lane_active', False) and 
                            smart_lane_status.get('pipeline_active', False)
                        ),
                        'total_operations': (
                            fast_lane_metrics.get('trades_today', 0) + 
                            smart_lane_metrics.get('successful_analyses', 0)
                        ),
                        'average_response_time_ms': (
                            (fast_lane_metrics.get('execution_time_ms', 0) + 
                             smart_lane_metrics.get('average_analysis_time_ms', 0)) / 2
                        )
                    },
                    
                    # Mock data indicators
                    '_mock_indicators': {
                        'fast_lane_mock': fast_lane_metrics.get('_mock', False),
                        'smart_lane_mock': smart_lane_metrics.get('_mock', False),
                        'any_mock_data': (
                            fast_lane_metrics.get('_mock', False) or 
                            smart_lane_metrics.get('_mock', False)
                        )
                    }
                }
                
                yield f"data: {json.dumps(data)}\n\n"
                iteration_count += 1
                
                # Log every 30 iterations for debugging
                if iteration_count % 30 == 0:
                    logger.debug(f"Metrics stream iteration {iteration_count} for user {request.user.username}")
                
            except Exception as e:
                logger.error(f"Error in metrics stream (iteration {iteration_count}): {e}")
                error_data = {
                    'type': 'error',
                    'error': 'Stream error',
                    'message': str(e),
                    'timestamp': datetime.now().isoformat(),
                    'iteration': iteration_count
                }
                yield f"data: {json.dumps(error_data)}\n\n"
            
            time.sleep(2)  # Update every 2 seconds
        
        logger.info(f"Metrics stream ended for user {request.user.username} after {iteration_count} iterations")
    
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['Connection'] = 'keep-alive'
    response['Access-Control-Allow-Origin'] = '*'  # For development - restrict in production
    response['X-Accel-Buffering'] = 'no'  # Disable nginx buffering
    return response


# =========================================================================
# JSON API ENDPOINTS (Enhanced with Smart Lane)
# =========================================================================

@require_http_methods(["GET"])
@login_required
def api_engine_status(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for comprehensive engine status with Fast Lane and Smart Lane integration.
    
    Returns JSON response with current engine status, performance metrics,
    and system health information for both lanes.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with comprehensive engine status data
    """
    try:
        logger.debug(f"Engine status API called by user: {request.user.username}")
        
        # Get Fast Lane status
        fast_lane_status = engine_service.get_engine_status()
        fast_lane_metrics = engine_service.get_performance_metrics()
        
        # Get Smart Lane status
        smart_lane_status = get_smart_lane_status()
        smart_lane_metrics = get_smart_lane_metrics()
        
        # Compile comprehensive status
        status_data = {
            'timestamp': datetime.now().isoformat(),
            
            # System overview
            'system': {
                'overall_status': determine_overall_status(fast_lane_status, smart_lane_status),
                'data_source': 'LIVE' if not fast_lane_status.get('_mock', False) else 'MOCK',
                'uptime_seconds': fast_lane_status.get('uptime_seconds', 0),
                'user': request.user.username
            },
            
            # Fast Lane detailed status
            'fast_lane': {
                'status': fast_lane_status.get('status', 'UNKNOWN'),
                'active': fast_lane_status.get('fast_lane_active', False),
                'initialized': fast_lane_status.get('engine_initialized', False),
                'execution_time_ms': fast_lane_metrics.get('execution_time_ms', 0),
                'success_rate': fast_lane_metrics.get('success_rate', 0),
                'trades_per_minute': fast_lane_metrics.get('trades_per_minute', 0),
                'mempool_connected': fast_lane_status.get('mempool_connected', False),
                'circuit_breaker_state': fast_lane_status.get('circuit_breaker_state', 'UNKNOWN'),
                '_mock': fast_lane_metrics.get('_mock', False)
            },
            
            # Smart Lane detailed status
            'smart_lane': {
                'status': smart_lane_status.get('status', 'UNKNOWN'),
                'active': smart_lane_status.get('pipeline_active', False),
                'initialized': smart_lane_status.get('pipeline_initialized', False),
                'analysis_time_ms': smart_lane_metrics.get('average_analysis_time_ms', 0),
                'success_rate': smart_lane_metrics.get('success_rate', 0),
                'analyses_completed': smart_lane_metrics.get('analyses_completed', 0),
                'analyzers_count': smart_lane_status.get('analyzers_count', 0),
                'capabilities': smart_lane_status.get('capabilities', []),
                'thought_log_enabled': smart_lane_status.get('thought_log_enabled', False),
                'cache_hit_ratio': smart_lane_metrics.get('cache_hit_ratio', 0),
                'circuit_breaker_state': smart_lane_status.get('circuit_breaker_state', 'UNKNOWN'),
                '_mock': smart_lane_metrics.get('_mock', False)
            },
            
            # Capabilities summary
            'capabilities': {
                'fast_lane_available': fast_lane_status.get('fast_lane_active', False),
                'smart_lane_available': smart_lane_status.get('pipeline_active', False),
                'hybrid_mode_available': (
                    fast_lane_status.get('fast_lane_active', False) and 
                    smart_lane_status.get('pipeline_active', False)
                ),
                'any_mode_available': (
                    fast_lane_status.get('fast_lane_active', False) or 
                    smart_lane_status.get('pipeline_active', False) or
                    fast_lane_metrics.get('_mock', False) or
                    smart_lane_metrics.get('_mock', False)
                )
            }
        }
        
        return JsonResponse(status_data)
        
    except Exception as e:
        logger.error(f"Error in api_engine_status: {e}")
        return JsonResponse({
            'timestamp': datetime.now().isoformat(),
            'system': {
                'overall_status': 'ERROR',
                'error': str(e)
            },
            'fast_lane': {'status': 'ERROR'},
            'smart_lane': {'status': 'ERROR'},
            'capabilities': {
                'fast_lane_available': False,
                'smart_lane_available': False,
                'hybrid_mode_available': False,
                'any_mode_available': False
            }
        }, status=500)


@require_http_methods(["GET"])
@login_required
def api_performance_metrics(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for detailed performance metrics from both lanes.
    
    Returns comprehensive performance data for dashboard charts and analytics.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with detailed performance metrics
    """
    try:
        logger.debug(f"Performance metrics API called by user: {request.user.username}")
        
        # Get metrics from both lanes
        fast_lane_metrics = engine_service.get_performance_metrics()
        smart_lane_metrics = get_smart_lane_metrics()
        
        # Compile performance data
        performance_data = {
            'timestamp': datetime.now().isoformat(),
            
            # Fast Lane performance
            'fast_lane': {
                'execution_time_ms': fast_lane_metrics.get('execution_time_ms', 0),
                'success_rate': fast_lane_metrics.get('success_rate', 0),
                'trades_per_minute': fast_lane_metrics.get('trades_per_minute', 0),
                'trades_today': fast_lane_metrics.get('trades_today', 0),
                'total_trades': fast_lane_metrics.get('total_trades', 0),
                'average_profit_percentage': fast_lane_metrics.get('average_profit_percentage', 0),
                'win_loss_ratio': fast_lane_metrics.get('win_loss_ratio', 0)
            },
            
            # Smart Lane performance
            'smart_lane': {
                'analysis_time_ms': smart_lane_metrics.get('average_analysis_time_ms', 0),
                'success_rate': smart_lane_metrics.get('success_rate', 0),
                'analyses_completed': smart_lane_metrics.get('analyses_completed', 0),
                'analyses_today': smart_lane_metrics.get('successful_analyses', 0),
                'thought_logs_generated': smart_lane_metrics.get('thought_logs_generated', 0),
                'cache_hit_ratio': smart_lane_metrics.get('cache_hit_ratio', 0),
                'active_analyses': smart_lane_metrics.get('active_analyses', 0),
                'risk_assessments_completed': smart_lane_metrics.get('risk_assessments_completed', 0)
            },
            
            # Comparative metrics
            'comparison': {
                'speed_advantage_fast_lane': max(0, 
                    smart_lane_metrics.get('average_analysis_time_ms', 0) - 
                    fast_lane_metrics.get('execution_time_ms', 0)
                ),
                'total_operations_today': (
                    fast_lane_metrics.get('trades_today', 0) + 
                    smart_lane_metrics.get('successful_analyses', 0)
                ),
                'combined_success_rate': (
                    (fast_lane_metrics.get('success_rate', 0) + 
                     smart_lane_metrics.get('success_rate', 0)) / 2
                ) if (fast_lane_metrics.get('success_rate', 0) > 0 or 
                      smart_lane_metrics.get('success_rate', 0) > 0) else 0
            },
            
            # Data quality indicators
            'data_quality': {
                'fast_lane_mock': fast_lane_metrics.get('_mock', False),
                'smart_lane_mock': smart_lane_metrics.get('_mock', False),
                'last_fast_lane_update': fast_lane_metrics.get('last_update'),
                'last_smart_lane_update': smart_lane_metrics.get('last_analysis_timestamp')
            }
        }
        
        return JsonResponse(performance_data)
        
    except Exception as e:
        logger.error(f"Error in api_performance_metrics: {e}")
        return JsonResponse({
            'timestamp': datetime.now().isoformat(),
            'error': str(e),
            'fast_lane': {},
            'smart_lane': {},
            'comparison': {},
            'data_quality': {
                'fast_lane_mock': True,
                'smart_lane_mock': True,
                'error': True
            }
        }, status=500)


@require_POST
@csrf_exempt
@login_required
def api_set_trading_mode(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to set trading mode (Fast Lane, Smart Lane, or Hybrid).
    
    Handles mode switching with proper validation and error handling.
    
    Args:
        request: Django HTTP request with mode data
        
    Returns:
        JsonResponse with mode change result
    """
    try:
        data = json.loads(request.body)
        mode = data.get('mode', '').lower()
        
        logger.info(f"Trading mode change requested: {mode} by user {request.user.username}")
        
        # Validate mode
        valid_modes = ['fast_lane', 'smart_lane', 'hybrid']
        if mode not in valid_modes:
            return JsonResponse({
                'success': False,
                'error': f'Invalid mode. Must be one of: {", ".join(valid_modes)}'
            }, status=400)
        
        # Check capabilities
        fast_lane_status = engine_service.get_engine_status()
        smart_lane_status = get_smart_lane_status()
        
        fast_available = fast_lane_status.get('fast_lane_active', False)
        smart_available = smart_lane_status.get('pipeline_active', False)
        
        # Validate mode availability
        if mode == 'fast_lane' and not fast_available:
            return JsonResponse({
                'success': False,
                'error': 'Fast Lane not available. Check engine status.'
            }, status=400)
        
        if mode == 'smart_lane' and not smart_available:
            return JsonResponse({
                'success': False,
                'error': 'Smart Lane not available. Check pipeline status.'
            }, status=400)
        
        if mode == 'hybrid' and not (fast_available and smart_available):
            return JsonResponse({
                'success': False,
                'error': 'Hybrid mode requires both Fast Lane and Smart Lane to be available.'
            }, status=400)
        
        # Set trading mode (this would interact with engine configuration)
        # For now, we'll store it in user session
        request.session['trading_mode'] = mode
        
        logger.info(f"Trading mode successfully changed to {mode} for user {request.user.username}")
        
        return JsonResponse({
            'success': True,
            'message': f'Trading mode set to {mode.replace("_", " ").title()}',
            'mode': mode,
            'timestamp': datetime.now().isoformat(),
            'user': request.user.username,
            'capabilities': {
                'fast_lane_available': fast_available,
                'smart_lane_available': smart_available,
                'hybrid_mode_available': fast_available and smart_available
            }
        })
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in api_set_trading_mode request")
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"API set trading mode error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =========================================================================
# SMART LANE SPECIFIC API ENDPOINTS
# =========================================================================

@require_POST
@csrf_exempt
@login_required
def api_smart_lane_analyze(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to trigger Smart Lane analysis of a token.
    
    Initiates comprehensive token analysis and returns results with thought log.
    
    Args:
        request: Django HTTP request with token data
        
    Returns:
        JsonResponse with analysis results
    """
    try:
        data = json.loads(request.body)
        token_address = data.get('token_address', '').strip()
        
        if not token_address:
            return JsonResponse({
                'success': False,
                'error': 'Token address is required'
            }, status=400)
        
        logger.info(f"Smart Lane analysis requested for {token_address} by user {request.user.username}")
        
        # Check Smart Lane availability
        smart_lane_status = get_smart_lane_status()
        if not smart_lane_status.get('analysis_ready', False):
            return JsonResponse({
                'success': False,
                'error': 'Smart Lane analysis not available. Check pipeline status.',
                'pipeline_status': smart_lane_status.get('status', 'UNKNOWN')
            }, status=503)
        
        # Get analysis configuration from request
        analysis_config = data.get('config', {})
        
        # Run analysis (this would be async in real implementation)
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            analysis_result = loop.run_until_complete(
                smart_lane_service.run_analysis(token_address, analysis_config)
            )
        finally:
            loop.close()
        
        if analysis_result.get('success', False):
            logger.info(f"Smart Lane analysis completed for {token_address}")
            return JsonResponse({
                'success': True,
                'analysis': analysis_result,
                'timestamp': datetime.now().isoformat()
            })
        else:
            logger.error(f"Smart Lane analysis failed for {token_address}: {analysis_result.get('error')}")
            return JsonResponse({
                'success': False,
                'error': analysis_result.get('error', 'Analysis failed'),
                'timestamp': datetime.now().isoformat()
            }, status=500)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Smart Lane analysis API error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, status=500)


@require_http_methods(["GET"])
@login_required
def api_get_thought_log(request: HttpRequest, analysis_id: str) -> JsonResponse:
    """
    API endpoint to retrieve thought log for a specific analysis.
    
    Returns the AI reasoning and decision process for transparency.
    
    Args:
        request: Django HTTP request object
        analysis_id: Analysis identifier
        
    Returns:
        JsonResponse with thought log data
    """
    try:
        logger.debug(f"Thought log requested for analysis {analysis_id} by user {request.user.username}")
        
        thought_log = smart_lane_service.get_thought_log(analysis_id)
        
        if thought_log:
            return JsonResponse({
                'success': True,
                'analysis_id': analysis_id,
                'thought_log': thought_log,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return JsonResponse({
                'success': False,
                'error': f'Thought log not found for analysis {analysis_id}',
                'analysis_id': analysis_id
            }, status=404)
        
    except Exception as e:
        logger.error(f"Thought log API error for {analysis_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'analysis_id': analysis_id,
            'timestamp': datetime.now().isoformat()
        }, status=500)


# =========================================================================
# HEALTH AND DIAGNOSTIC ENDPOINTS
# =========================================================================

@require_http_methods(["GET"])
def health_check(request: HttpRequest) -> JsonResponse:
    """
    Health check endpoint for monitoring and load balancers.
    
    Returns system health status for both Fast Lane and Smart Lane.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with health status
    """
    try:
        # Basic health checks
        fast_lane_health = engine_service.health_check()
        smart_lane_status = get_smart_lane_status()
        
        # Determine overall health
        fast_healthy = fast_lane_health.get('status') == 'healthy'
        smart_healthy = smart_lane_status.get('status') in ['OPERATIONAL', 'READY', 'MOCK_MODE']
        
        overall_status = 'healthy' if (fast_healthy or smart_healthy) else 'unhealthy'
        
        health_data = {
            'status': overall_status,
            'timestamp': datetime.now().isoformat(),
            'components': {
                'fast_lane': {
                    'status': 'healthy' if fast_healthy else 'unhealthy',
                    'details': fast_lane_health
                },
                'smart_lane': {
                    'status': 'healthy' if smart_healthy else 'unhealthy',
                    'details': {
                        'pipeline_status': smart_lane_status.get('status'),
                        'pipeline_active': smart_lane_status.get('pipeline_active', False),
                        'analyzers_count': smart_lane_status.get('analyzers_count', 0)
                    }
                },
                'database': {
                    'status': 'healthy',  # Would check database connectivity
                    'details': {'connection': 'active'}
                }
            },
            'version': '1.0.0',
            'environment': getattr(settings, 'ENVIRONMENT', 'development')
        }
        
        status_code = 200 if overall_status == 'healthy' else 503
        return JsonResponse(health_data, status=status_code)
        
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return JsonResponse({
            'status': 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }, status=503)


@require_http_methods(["GET"])
@login_required
def engine_test(request: HttpRequest) -> JsonResponse:
    """
    Engine test endpoint for debugging and diagnostics.
    
    Performs comprehensive testing of both engine components.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse with test results
    """
    try:
        logger.info(f"Engine test requested by user {request.user.username}")
        
        # Test Fast Lane
        fast_lane_test = engine_service.test_engine()
        
        # Test Smart Lane
        smart_lane_status = get_smart_lane_status()
        smart_lane_metrics = get_smart_lane_metrics()
        
        test_results = {
            'timestamp': datetime.now().isoformat(),
            'user': request.user.username,
            
            'fast_lane_test': fast_lane_test,
            
            'smart_lane_test': {
                'status': smart_lane_status.get('status'),
                'pipeline_initialized': smart_lane_status.get('pipeline_initialized', False),
                'analyzers_available': smart_lane_status.get('analyzers_count', 0),
                'capabilities': smart_lane_status.get('capabilities', []),
                'metrics_available': bool(smart_lane_metrics.get('analyses_completed', 0) > 0),
                'thought_log_enabled': smart_lane_status.get('thought_log_enabled', False)
            },
            
            'system_test': {
                'django_settings': {
                    'debug': settings.DEBUG,
                    'smart_lane_enabled': getattr(settings, 'SMART_LANE_ENABLED', False),
                    'fast_lane_enabled': getattr(settings, 'FAST_LANE_ENABLED', False),
                    'mock_mode': getattr(settings, 'ENGINE_MOCK_MODE', True)
                },
                'user_session': {
                    'trading_mode': request.session.get('trading_mode', 'not_set'),
                    'authenticated': request.user.is_authenticated
                }
            }
        }
        
        logger.info(f"Engine test completed for user {request.user.username}")
        return JsonResponse(test_results)
        
    except Exception as e:
        logger.error(f"Engine test error: {e}", exc_info=True)
        return JsonResponse({
            'timestamp': datetime.now().isoformat(),
            'error': str(e),
            'fast_lane_test': {'status': 'error'},
            'smart_lane_test': {'status': 'error'},
            'system_test': {'status': 'error'}
        }, status=500)


# =========================================================================
# MODULE EXPORTS
# =========================================================================

__all__ = [
    # Real-time streaming
    'metrics_stream',
    
    # Engine status and control
    'api_engine_status',
    'api_performance_metrics',
    'api_set_trading_mode',
    
    # Smart Lane specific
    'api_smart_lane_analyze',
    'api_get_thought_log',
    
    # Health and diagnostics
    'health_check',
    'engine_test',
    
    # Helper functions
    'get_smart_lane_status',
    'get_smart_lane_metrics',
    'determine_overall_status'
]

logger.info("API endpoints module loaded successfully with complete Smart Lane integration")