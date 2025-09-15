"""
Dashboard Views Module

Exports all dashboard view functions for URL routing.

Path: dashboard/views/__init__.py
"""

# Import Django components first
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

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
    @login_required
    def configuration_panel(request, mode='FAST_LANE'):
        """Configuration panel view for Fast Lane or Smart Lane."""
        from trading.models import BotConfiguration
        
        user_configs = BotConfiguration.objects.filter(user=request.user)
        
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
    @login_required
    def dashboard_settings(request):
        """Placeholder settings view."""
        return render(request, 'dashboard/settings.html', {
            'user': request.user,
            'page_title': 'Settings',
            'active_page': 'settings',
        })
    
    @login_required
    def dashboard_analytics(request):
        """Placeholder analytics view."""
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
    import json
    from django.views.decorators.http import require_http_methods
    from django.views.decorators.csrf import csrf_exempt
    
    @login_required
    @require_http_methods(["POST"])
    def save_configuration(request):
        """Save bot configuration."""
        try:
            from trading.models import BotConfiguration
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
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    @login_required
    @require_http_methods(["POST"])
    def load_configuration(request):
        """Load a bot configuration."""
        try:
            from trading.models import BotConfiguration
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
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    @login_required
    @require_http_methods(["POST"])
    def delete_configuration(request):
        """Delete a bot configuration."""
        try:
            from trading.models import BotConfiguration
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
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    @login_required
    @require_http_methods(["GET"])
    def get_configurations(request):
        """Get all user configurations."""
        try:
            from trading.models import BotConfiguration
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
    @login_required
    def start_session(request):
        """Placeholder start session view."""
        return JsonResponse({'success': False, 'error': 'Session management not implemented'})
    
    @login_required
    def stop_session(request):
        """Placeholder stop session view."""
        return JsonResponse({'success': False, 'error': 'Session management not implemented'})
    
    @login_required
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
    @login_required
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
    @login_required
    def smart_lane_dashboard(request):
        """Placeholder Smart Lane dashboard."""
        return render(request, 'dashboard/smart_lane_dashboard.html', {
            'page_title': 'Smart Lane Intelligence',
            'smart_lane_enabled': False,
            'error': 'Smart Lane views not available'
        })
    
    @login_required
    def smart_lane_demo(request):
        """Placeholder Smart Lane demo."""
        return render(request, 'dashboard/smart_lane_demo.html', {
            'page_title': 'Smart Lane Demo',
            'smart_lane_enabled': False,
            'error': 'Smart Lane views not available'
        })
    
    @login_required
    def smart_lane_config(request):
        """Placeholder Smart Lane config."""
        return render(request, 'dashboard/smart_lane_config.html', {
            'page_title': 'Smart Lane Configuration',
            'error': 'Smart Lane views not available'
        })
    
    @login_required
    def smart_lane_analyze(request):
        """Placeholder Smart Lane analyze."""
        return render(request, 'dashboard/smart_lane_analyze.html', {
            'page_title': 'Smart Lane Analysis',
            'error': 'Smart Lane views not available'
        })
    
    @login_required
    def api_smart_lane_analyze(request):
        """Placeholder Smart Lane API."""
        return JsonResponse({
            'success': False,
            'error': 'Smart Lane API not available'
        })
    
    @login_required
    def api_get_thought_log(request, analysis_id):
        """Placeholder thought log API."""
        return JsonResponse({
            'success': False,
            'error': 'Thought log API not available'
        })

# Export all views
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
    
    # Smart Lane views - NEW ADDITION
    'smart_lane_dashboard',
    'smart_lane_demo',
    'smart_lane_config',
    'smart_lane_analyze',
    'api_smart_lane_analyze',
    'api_get_thought_log',
]