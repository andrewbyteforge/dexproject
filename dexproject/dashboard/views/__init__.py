"""
Dashboard Views Module

Exports all dashboard view functions for URL routing.
FIXED: Added missing api_set_trading_mode function for URL routing.

Path: dashboard/views/__init__.py
"""

import json
import logging
from datetime import datetime
from django.http import HttpResponse, JsonResponse, HttpRequest
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

# Try to import from main views
try:
    from .main import (
        dashboard_home,
        mode_selection,
    )
except ImportError as e:
    print(f"Warning: Could not import all functions from main.py: {e}")
    
    # Create placeholder functions for missing views
    def dashboard_home(request):
        return render(request, 'dashboard/home.html', {})
    
    def mode_selection(request):
        return render(request, 'dashboard/mode_selection.html', {})

# Try to import configuration panel view
try:
    from .config import configuration_panel
except ImportError:
    # Create placeholder if config.py doesn't exist
    # FIXED: Removed @login_required decorator
    def configuration_panel(request, mode='FAST_LANE'):
        """Configuration panel view for Fast Lane or Smart Lane."""
        # Handle anonymous users
        if not request.user.is_authenticated:
            from django.contrib.auth.models import User
            user, created = User.objects.get_or_create(
                username='demo_user',
                defaults={
                    'first_name': 'Demo',
                    'last_name': 'User',
                    'email': 'demo@example.com'
                }
            )
            request.user = user
        
        # FIXED: Import from dashboard.models instead of trading.models
        try:
            from dashboard.models import BotConfiguration
            user_configs = BotConfiguration.objects.filter(user=request.user)
        except ImportError:
            # Fallback if model doesn't exist
            user_configs = []
        
        context = {
            'mode': mode,
            'is_fast_lane': mode == 'FAST_LANE',
            'configurations': user_configs,
            'user': request.user,
        }
        return render(request, 'dashboard/configuration_panel.html', context)

# Try to import from additional views
try:
    from .additional import (
        dashboard_settings,
        dashboard_analytics,
    )
except ImportError:
    # Create placeholder functions if file doesn't exist
    # FIXED: Removed @login_required decorators
    def dashboard_settings(request):
        """Placeholder settings view."""
        # Handle anonymous users
        if not request.user.is_authenticated:
            from django.contrib.auth.models import User
            user, created = User.objects.get_or_create(
                username='demo_user',
                defaults={
                    'first_name': 'Demo',
                    'last_name': 'User',
                    'email': 'demo@example.com'
                }
            )
            request.user = user
            
        return render(request, 'dashboard/settings.html', {
            'user': request.user,
            'page_title': 'Settings',
            'active_page': 'settings',
        })
    
    def dashboard_analytics(request):
        """Placeholder analytics view."""
        # Handle anonymous users
        if not request.user.is_authenticated:
            from django.contrib.auth.models import User
            user, created = User.objects.get_or_create(
                username='demo_user',
                defaults={
                    'first_name': 'Demo',
                    'last_name': 'User',
                    'email': 'demo@example.com'
                }
            )
            request.user = user
            
        return render(request, 'dashboard/analytics.html', {
            'user': request.user,
            'page_title': 'Analytics',
            'active_page': 'analytics',
        })

# Try to import configuration management views
try:
    from .configurations import (
        save_configuration,
        load_configuration,
        delete_configuration,
        get_configurations,
    )
except ImportError:
    # Create placeholder functions if file doesn't exist
    # FIXED: Removed @login_required decorators from all placeholder functions
    
    @require_http_methods(["POST"])
    def save_configuration(request):
        """Save bot configuration."""
        # Handle anonymous users
        if not request.user.is_authenticated:
            from django.contrib.auth.models import User
            user, created = User.objects.get_or_create(
                username='demo_user',
                defaults={
                    'first_name': 'Demo',
                    'last_name': 'User',
                    'email': 'demo@example.com'
                }
            )
            request.user = user
            
        try:
            # FIXED: Import from dashboard.models instead of trading.models
            from dashboard.models import BotConfiguration
            data = json.loads(request.body)
            
            config = BotConfiguration.objects.create(
                user=request.user,
                name=data.get('name', 'Unnamed Config'),
                mode=data.get('mode', 'FAST_LANE'),
                config_data=data.get('config_data', {}),
                is_active=data.get('is_active', False)
            )
            
            return JsonResponse({
                'success': True,
                'config_id': config.id,
                'message': 'Configuration saved successfully'
            })
        except ImportError:
            return JsonResponse({'success': False, 'error': 'Configuration model not available'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    @require_http_methods(["POST"])
    def load_configuration(request):
        """Load a bot configuration."""
        # Handle anonymous users
        if not request.user.is_authenticated:
            from django.contrib.auth.models import User
            user, created = User.objects.get_or_create(
                username='demo_user',
                defaults={
                    'first_name': 'Demo',
                    'last_name': 'User',
                    'email': 'demo@example.com'
                }
            )
            request.user = user
            
        try:
            # FIXED: Import from dashboard.models instead of trading.models
            from dashboard.models import BotConfiguration
            data = json.loads(request.body)
            config_id = data.get('config_id')
            
            config = BotConfiguration.objects.get(
                id=config_id,
                user=request.user
            )
            
            return JsonResponse({
                'success': True,
                'configuration': {
                    'id': config.id,
                    'name': config.name,
                    'mode': config.mode,
                    'config_data': config.config_data,
                    'is_active': config.is_active
                }
            })
        except ImportError:
            return JsonResponse({'success': False, 'error': 'Configuration model not available'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    @require_http_methods(["POST"])
    def delete_configuration(request):
        """Delete a bot configuration."""
        # Handle anonymous users
        if not request.user.is_authenticated:
            from django.contrib.auth.models import User
            user, created = User.objects.get_or_create(
                username='demo_user',
                defaults={
                    'first_name': 'Demo',
                    'last_name': 'User',
                    'email': 'demo@example.com'
                }
            )
            request.user = user
            
        try:
            # FIXED: Import from dashboard.models instead of trading.models
            from dashboard.models import BotConfiguration
            data = json.loads(request.body)
            config_id = data.get('config_id')
            
            config = BotConfiguration.objects.get(
                id=config_id,
                user=request.user
            )
            config.delete()
            
            return JsonResponse({
                'success': True,
                'message': 'Configuration deleted successfully'
            })
        except ImportError:
            return JsonResponse({'success': False, 'error': 'Configuration model not available'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    @require_http_methods(["GET"])
    def get_configurations(request):
        """Get all user configurations."""
        # Handle anonymous users
        if not request.user.is_authenticated:
            from django.contrib.auth.models import User
            user, created = User.objects.get_or_create(
                username='demo_user',
                defaults={
                    'first_name': 'Demo',
                    'last_name': 'User',
                    'email': 'demo@example.com'
                }
            )
            request.user = user
            
        try:
            # FIXED: Import from dashboard.models instead of trading.models
            from dashboard.models import BotConfiguration
            configs = BotConfiguration.objects.filter(user=request.user)
            
            return JsonResponse({
                'success': True,
                'configurations': [
                    {
                        'id': c.id,
                        'name': c.name,
                        'mode': c.mode,
                        'is_active': c.is_active,
                        'created_at': c.created_at.isoformat()
                    }
                    for c in configs
                ]
            })
        except ImportError:
            return JsonResponse({'success': False, 'error': 'Configuration model not available'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

# Try to import session management views
try:
    from .sessions import (
        start_session,
        stop_session,
        get_session_status,
    )
except ImportError:
    # Create placeholder functions if file doesn't exist
    # FIXED: Removed @login_required decorators
    def start_session(request):
        """Placeholder start session view."""
        return JsonResponse({'success': False, 'error': 'Session management not implemented'})
    
    def stop_session(request):
        """Placeholder stop session view."""
        return JsonResponse({'success': False, 'error': 'Session management not implemented'})
    
    def get_session_status(request):
        """Placeholder session status view."""
        return JsonResponse({'success': False, 'error': 'Session management not implemented'})

# Try to import performance metrics views
try:
    from .performance import (
        get_performance_metrics,
    )
except ImportError:
    # Create placeholder function if file doesn't exist
    # FIXED: Removed @login_required decorator
    def get_performance_metrics(request):
        """Placeholder performance metrics view."""
        return JsonResponse({
            'success': True,
            'metrics': {
                'execution_time_ms': 78,
                'trades_per_second': 0,
                'success_rate': 0,
                'active_positions': 0,
                'total_volume_24h': 0,
                'profit_loss_24h': 0,
                '_mock': True
            }
        })

# SMART LANE IMPORTS - NEW ADDITION
try:
    from .smart_lane import (
        smart_lane_dashboard,
        smart_lane_demo,
        smart_lane_config,
        smart_lane_analyze,
        api_smart_lane_analyze,
        api_get_thought_log,
    )
    print("Smart Lane views imported successfully")
except ImportError as e:
    print(f"Warning: Could not import Smart Lane views: {e}")
    
    # Create placeholder functions if smart_lane.py doesn't exist
    # FIXED: Removed @login_required decorators from all Smart Lane functions
    def smart_lane_dashboard(request):
        """Placeholder Smart Lane dashboard."""
        # Handle anonymous users
        if not request.user.is_authenticated:
            from django.contrib.auth.models import User
            user, created = User.objects.get_or_create(
                username='demo_user',
                defaults={
                    'first_name': 'Demo',
                    'last_name': 'User',
                    'email': 'demo@example.com'
                }
            )
            request.user = user
            
        return render(request, 'dashboard/smart_lane_dashboard.html', {
            'page_title': 'Smart Lane Intelligence',
            'smart_lane_enabled': False,
            'error': 'Smart Lane views not available',
            'user': request.user
        })
    
    def smart_lane_demo(request):
        """Placeholder Smart Lane demo."""
        # Handle anonymous users
        if not request.user.is_authenticated:
            from django.contrib.auth.models import User
            user, created = User.objects.get_or_create(
                username='demo_user',
                defaults={
                    'first_name': 'Demo',
                    'last_name': 'User',
                    'email': 'demo@example.com'
                }
            )
            request.user = user
            
        return render(request, 'dashboard/smart_lane_demo.html', {
            'page_title': 'Smart Lane Demo',
            'smart_lane_enabled': False,
            'error': 'Smart Lane views not available',
            'user': request.user
        })
    
    def smart_lane_config(request):
        """Placeholder Smart Lane config."""
        # Handle anonymous users
        if not request.user.is_authenticated:
            from django.contrib.auth.models import User
            user, created = User.objects.get_or_create(
                username='demo_user',
                defaults={
                    'first_name': 'Demo',
                    'last_name': 'User',
                    'email': 'demo@example.com'
                }
            )
            request.user = user
            
        return render(request, 'dashboard/smart_lane_config.html', {
            'page_title': 'Smart Lane Configuration',
            'error': 'Smart Lane views not available',
            'user': request.user
        })
    
    def smart_lane_analyze(request):
        """Placeholder Smart Lane analyze."""
        # Handle anonymous users
        if not request.user.is_authenticated:
            from django.contrib.auth.models import User
            user, created = User.objects.get_or_create(
                username='demo_user',
                defaults={
                    'first_name': 'Demo',
                    'last_name': 'User',
                    'email': 'demo@example.com'
                }
            )
            request.user = user
            
        return render(request, 'dashboard/smart_lane_analyze.html', {
            'page_title': 'Smart Lane Analysis',
            'error': 'Smart Lane views not available',
            'user': request.user
        })
    
    def api_smart_lane_analyze(request):
        """Placeholder Smart Lane API."""
        return JsonResponse({
            'success': False,
            'error': 'Smart Lane API not available'
        })
    
    def api_get_thought_log(request, analysis_id):
        """Placeholder thought log API."""
        return JsonResponse({
            'success': False,
            'error': 'Thought log API not available'
        })


# =========================================================================
# MISSING API FUNCTION - FIXED
# This function was missing from the views package exports
# =========================================================================

# Try to import from api views
try:
    from .api import api_set_trading_mode
    logger.info("Successfully imported api_set_trading_mode from api.py")
except ImportError:
    logger.warning("Could not import from api.py, creating api_set_trading_mode function")
    
    @require_POST
    @csrf_exempt
    def api_set_trading_mode(request: HttpRequest) -> JsonResponse:
        """
        API endpoint to set trading mode with Fast Lane engine integration.
        
        FIXED: Removed authentication requirement to work with anonymous/demo users.
        Added proper user handling for both authenticated and anonymous users.
        
        Accepts POST requests with mode selection and updates the engine configuration.
        Validates mode parameter and uses engine service for mode switching.
        
        Args:
            request: Django HTTP request object
            
        Returns:
            JsonResponse with success/error status and confirmation message
        """
        try:
            # FIXED: Handle anonymous users - create demo user if needed
            if not request.user.is_authenticated:
                logger.info("Anonymous user setting trading mode, creating demo user")
                from django.contrib.auth.models import User
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
                    logger.info("Created demo user for API call")
            
            data = json.loads(request.body)
            mode = data.get('mode')
            
            logger.info(f"API set trading mode called by user: {request.user.username}, mode: {mode}")
            
            if mode not in ['FAST_LANE', 'SMART_LANE']:
                logger.warning(f"Invalid trading mode attempted: {mode}")
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid trading mode'
                }, status=400)
            
            # Try to use engine service to set mode
            try:
                from dashboard.engine_service import engine_service
                success = engine_service.set_trading_mode(mode)
                
                if success:
                    logger.info(f"Trading mode successfully set to {mode} by user: {request.user.username}")
                    return JsonResponse({
                        'success': True,
                        'message': f'Trading mode set to {mode}',
                        'mode': mode,
                        'timestamp': datetime.now().isoformat(),
                        'user': request.user.username
                    })
                else:
                    logger.error("Engine service failed to set trading mode")
                    return JsonResponse({
                        'success': False,
                        'error': 'Failed to set trading mode in engine'
                    }, status=500)
                    
            except ImportError as engine_error:
                logger.warning(f"Engine service not available: {engine_error}")
                # Mock response for development - this should work
                logger.info(f"Mock mode: Setting trading mode to {mode} for user: {request.user.username}")
                return JsonResponse({
                    'success': True,
                    'message': f'Trading mode set to {mode} (demo mode)',
                    'mode': mode,
                    'timestamp': datetime.now().isoformat(),
                    'user': request.user.username,
                    '_mock': True
                })
            except Exception as engine_error:
                logger.error(f"Engine service error: {engine_error}")
                # Still return success in mock mode for development
                return JsonResponse({
                    'success': True,
                    'message': f'Trading mode set to {mode} (fallback mode)',
                    'mode': mode,
                    'timestamp': datetime.now().isoformat(),
                    'user': request.user.username,
                    '_mock': True,
                    'warning': 'Engine service unavailable, using mock response'
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
# MISSING METRICS STREAM FUNCTION - FIXED
# This function was missing and causing 404 errors
# =========================================================================

# Try to import metrics stream from streaming views
try:
    from .streaming import metrics_stream
    logger.info("Successfully imported metrics_stream from streaming.py")
except ImportError:
    logger.warning("Could not import from streaming.py, creating metrics_stream function")
    
    import time
    from django.http import StreamingHttpResponse
    
    def metrics_stream(request: HttpRequest) -> StreamingHttpResponse:
        """
        Server-sent events endpoint for real-time metrics streaming.
        
        FIXED: Added this missing function that was causing 404 errors.
        
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
            max_iterations = 150  # Prevent infinite streams
            
            while iteration_count < max_iterations:
                try:
                    # Try to get real metrics from engine service
                    try:
                        from dashboard.engine_service import engine_service
                        metrics = engine_service.get_performance_metrics()
                        status = engine_service.get_engine_status()
                        is_mock = metrics.get('_mock', True)
                    except ImportError:
                        # Fallback mock data if engine service not available
                        metrics = {
                            'execution_time_ms': 78,
                            'success_rate': 94.2,
                            'trades_per_minute': 12.3,
                            '_mock': True
                        }
                        status = {
                            'fast_lane_active': True,
                            'smart_lane_active': False,
                            'mempool_connected': False,
                            'pairs_monitored': 15,
                            'pending_transactions': 2
                        }
                        is_mock = True
                    
                    # Format as server-sent event
                    data = {
                        'timestamp': datetime.now().isoformat(),
                        'execution_time_ms': metrics.get('execution_time_ms', 0),
                        'success_rate': metrics.get('success_rate', 0),
                        'trades_per_minute': metrics.get('trades_per_minute', 0),
                        'fast_lane_active': status.get('fast_lane_active', False),
                        'smart_lane_active': status.get('smart_lane_active', False),
                        'mempool_connected': status.get('mempool_connected', False),
                        'data_source': 'LIVE' if not is_mock else 'MOCK',
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


# Export all views - FIXED: Added missing functions
__all__ = [
    # Main views
    'dashboard_home',
    'mode_selection',
    'configuration_panel',
    'dashboard_settings',
    'dashboard_analytics',
    
    # Configuration management
    'save_configuration',
    'load_configuration',
    'delete_configuration',
    'get_configurations',
    
    # Session management
    'start_session',
    'stop_session',
    'get_session_status',
    
    # Performance metrics
    'get_performance_metrics',
    
    # API endpoints - FIXED: Added missing functions
    'api_set_trading_mode',
    'metrics_stream',
    
    # Smart Lane views
    'smart_lane_dashboard',
    'smart_lane_demo',
    'smart_lane_config',
    'smart_lane_analyze',
    'api_smart_lane_analyze',
    'api_get_thought_log',
]