"""
Fixed Dashboard Views for DEX Trading Bot

Corrected template variable names (no underscores).

File: dashboard/views.py
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.http import HttpResponse, StreamingHttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.conf import settings
from .models import BotConfiguration, TradingSession, UserProfile

logger = logging.getLogger(__name__)


def dashboard_home(request):
    """
    Simplified main dashboard page with corrected template variables.
    """
    try:
        # Simple context without underscore variables
        context = {
            'page_title': 'Trading Dashboard',
            'user_profile': {
                'display_name': 'Demo User'
            },
            'bot_configs': [],
            'active_sessions': [],
            'engine_status': {
                'status': 'OPERATIONAL',
                'message': 'Demo mode - all systems operational',
                'fast_lane_active': True,
                'smart_lane_active': False,
                'mempool_connected': True,
                'risk_cache_status': 'HEALTHY',
                'is_mock': True  # Changed from '_mock' to 'is_mock'
            },
            'performance_metrics': {
                'execution_time_ms': 78.5,
                'success_rate': 94.2,
                'trades_per_minute': 12.3,
                'risk_cache_hits': 98,
                'mempool_latency_ms': 1.2,
                'gas_optimization_ms': 15.8,
                'fast_lane_trades_today': 67,
                'smart_lane_trades_today': 23,
                'is_mock': True  # Changed from '_mock' to 'is_mock'
            },
            'show_onboarding': False,
            'user': {'username': 'demo_user', 'is_authenticated': True}
        }
        
        return render(request, 'dashboard/home.html', context)
        
    except Exception as e:
        logger.error(f"Error in dashboard_home: {e}")
        return render(request, 'dashboard/error.html', {'error': str(e)})


def mode_selection(request):
    """
    Simplified mode selection interface.
    """
    try:
        context = {
            'page_title': 'Mode Selection - Fast Lane vs Smart Lane',
            'fast_lane_metrics': {
                'execution_time_ms': 78.5,
                'success_rate': 94.2,
                'trades_per_minute': 12.3,
                'is_mock': True  # Changed from '_mock' to 'is_mock'
            },
            'smart_lane_metrics': {
                'execution_time_ms': 2500,
                'success_rate': 96.2,
                'risk_adjusted_return': 15.3,
                'is_mock': True  # Changed from '_mock' to 'is_mock'
            }
        }
        
        return render(request, 'dashboard/mode_selection.html', context)
        
    except Exception as e:
        logger.error(f"Error in mode_selection: {e}")
        messages.error(request, "Error loading mode selection.")
        return redirect('dashboard:home')


def configuration_panel(request, mode):
    """
    Simplified configuration panel.
    """
    if mode not in ['fast_lane', 'smart_lane']:
        messages.error(request, "Invalid trading mode specified.")
        return redirect('dashboard:home')
    
    try:
        mode_display = mode.replace('_', ' ').title()
        
        context = {
            'mode': mode,
            'mode_display': mode_display,
            'config': {
                'name': f'Default {mode_display} Config',
                'description': f'Default configuration for {mode_display} trading'
            },
            'page_title': f'{mode_display} Configuration',
        }
        
        return render(request, 'dashboard/configuration_panel.html', context)
        
    except Exception as e:
        logger.error(f"Error in configuration_panel: {e}")
        messages.error(request, f"Error loading {mode} configuration.")
        return redirect('dashboard:home')


def metrics_stream(request):
    """
    Fixed Server-Sent Events endpoint compatible with Django dev server.
    """
    def event_stream():
        """Generator function for SSE data stream."""
        import time
        import random
        
        # Send initial connection confirmation
        yield f"data: {json.dumps({'type': 'connection', 'status': 'connected', 'timestamp': datetime.now().isoformat()})}\n\n"
        
        # Simple metrics updates
        counter = 0
        while counter < 50:  # Limit to prevent long-running processes
            try:
                # Generate simple mock metrics
                base_time = 78
                execution_time = base_time + random.uniform(-5, 10)
                
                message_data = {
                    'type': 'metrics_update',
                    'timestamp': datetime.now().isoformat(),
                    'metrics': {
                        'execution_time_ms': round(execution_time, 2),
                        'success_rate': round(random.uniform(92, 98), 1),
                        'trades_per_minute': round(random.uniform(8, 15), 1),
                        'risk_cache_hits': random.randint(95, 100),
                        'mempool_latency_ms': round(random.uniform(0.5, 2.0), 2),
                        'is_mock': True
                    },
                    'status': {
                        'status': 'OPERATIONAL',
                        'fast_lane_active': True,
                        'smart_lane_active': False,
                        'is_mock': True
                    }
                }
                
                yield f"data: {json.dumps(message_data)}\n\n"
                time.sleep(3)  # Update every 3 seconds
                counter += 1
                
            except Exception as e:
                logger.error(f"Error in metrics stream: {e}")
                break
    
    # Return SSE response with corrected headers for Django dev server
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    # Remove the problematic Connection header for Django dev server
    response['Access-Control-Allow-Origin'] = '*'
    response['X-Accel-Buffering'] = 'no'  # For nginx compatibility
    return response


def api_engine_status(request):
    """Simplified API endpoint for engine status."""
    try:
        status = {
            'status': 'OPERATIONAL',
            'message': 'Demo mode active',
            'fast_lane_active': True,
            'smart_lane_active': False,
            'is_mock': True  # Changed from '_mock' to 'is_mock'
        }
        return JsonResponse({'success': True, 'data': status})
    except Exception as e:
        logger.error(f"Error getting engine status: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def api_performance_metrics(request):
    """Simplified API endpoint for performance metrics."""
    try:
        import random
        metrics = {
            'execution_time_ms': round(78 + random.uniform(-5, 10), 2),
            'success_rate': round(random.uniform(92, 98), 1),
            'trades_per_minute': round(random.uniform(8, 15), 1),
            'is_mock': True  # Changed from '_mock' to 'is_mock'
        }
        return JsonResponse({'success': True, 'data': metrics})
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_set_trading_mode(request):
    """Simplified API endpoint to change trading mode."""
    try:
        data = json.loads(request.body)
        mode = data.get('mode', '').upper()
        
        if mode not in ['FAST_LANE', 'SMART_LANE']:
            return JsonResponse({'success': False, 'error': 'Invalid trading mode'}, status=400)
        
        # Mock successful mode change
        logger.info(f"Mock mode change to: {mode}")
        return JsonResponse({'success': True, 'mode': mode})
            
    except Exception as e:
        logger.error(f"Error setting trading mode: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def start_trading_session(request):
    """Simplified session start."""
    if request.method == 'POST':
        messages.success(request, 'Demo session started successfully!')
    return redirect('dashboard:home')


def stop_trading_session(request, session_id):
    """Simplified session stop."""
    messages.success(request, 'Demo session stopped successfully!')
    return redirect('dashboard:home')


def simple_test(request):
    """Simple test that returns basic HTML."""
    from django.http import HttpResponse
    return HttpResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test</title>
        <style>body{background:#000;color:#0f0;font-family:monospace;padding:50px;}</style>
    </head>
    <body>
        <h1>🚀 Django is WORKING!</h1>
        <p>If you see this, Django views are working correctly.</p>
        <p>Time: """ + str(datetime.now()) + """</p>
        <a href="/dashboard/" style="color:#0f0;">Try Dashboard</a>
    </body>
    </html>
    """)



def debug_templates(request):
    """Debug template loading."""
    from django.http import HttpResponse
    from django.template.loader import get_template
    
    html = ["<h2>Template Debug</h2><pre>"]
    
    try:
        # Try to load base template
        base = get_template('base.html')
        html.append("✅ base.html found")
    except Exception as e:
        html.append(f"❌ base.html error: {e}")
    
    try:
        # Try to load home template  
        home = get_template('dashboard/home.html')
        html.append("✅ dashboard/home.html found")
    except Exception as e:
        html.append(f"❌ dashboard/home.html error: {e}")
    
    # Check settings
    from django.conf import settings
    html.append(f"\nTemplate dirs: {settings.TEMPLATES[0]['DIRS']}")
    
    html.append("</pre>")
    
    return HttpResponse(''.join(html))



def minimal_dashboard(request):
    """Minimal dashboard without template inheritance."""
    from django.http import HttpResponse
    return HttpResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>DEX Trading Bot - Minimal</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { background: #0d1117; color: white; }
            .fast-lane { color: #00d4aa; }
        </style>
    </head>
    <body>
        <div class="container mt-5">
            <h1>🚀 DEX Trading Bot</h1>
            <div class="row mt-4">
                <div class="col-md-6">
                    <div class="card bg-dark">
                        <div class="card-body">
                            <h5 class="fast-lane">⚡ Fast Lane</h5>
                            <h2 class="fast-lane">78ms</h2>
                            <p>Execution Time</p>
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="card bg-dark">
                        <div class="card-body">
                            <h5 class="text-primary">🧠 Smart Lane</h5>
                            <h2 class="text-primary">2.5s</h2>
                            <p>Coming Soon</p>
                        </div>
                    </div>
                </div>
            </div>
            <div class="mt-4">
                <p>✅ Bootstrap loaded</p>
                <p>✅ Templates working</p>
                <p>✅ Views working</p>
            </div>
        </div>
    </body>
    </html>
    """)





# Add these debug functions to the TOP of your dashboard\views.py file (after imports)

def simple_test(request):
    """Simple test that returns basic HTML."""
    from django.http import HttpResponse
    return HttpResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test</title>
        <style>body{background:#000;color:#0f0;font-family:monospace;padding:50px;}</style>
    </head>
    <body>
        <h1>🚀 Django is WORKING!</h1>
        <p>If you see this, Django views are working correctly.</p>
        <p>Time: """ + str(datetime.now()) + """</p>
        <a href="/dashboard/" style="color:#0f0;">Try Dashboard</a>
        <br><a href="/dashboard/debug-templates/" style="color:#0f0;">Debug Templates</a>
    </body>
    </html>
    """)

def debug_templates(request):
    """Debug template loading."""
    from django.http import HttpResponse
    from django.template.loader import get_template
    from django.conf import settings
    
    html = ["<h2 style='color:white;background:black;padding:20px;'>Template Debug</h2><pre style='color:white;background:black;padding:20px;'>"]
    
    try:
        # Try to load base template
        base = get_template('base.html')
        html.append("✅ base.html found")
    except Exception as e:
        html.append(f"❌ base.html error: {e}")
    
    try:
        # Try to load home template  
        home = get_template('dashboard/home.html')
        html.append("✅ dashboard/home.html found")
    except Exception as e:
        html.append(f"❌ dashboard/home.html error: {e}")
    
    # Check settings
    html.append(f"\nTemplate dirs: {settings.TEMPLATES[0]['DIRS']}")
    html.append(f"Template debug: {settings.TEMPLATES[0]['OPTIONS'].get('debug', False)}")
    
    # Try to render the error template
    try:
        error_template = get_template('dashboard/error.html')
        html.append("✅ dashboard/error.html found")
    except Exception as e:
        html.append(f"❌ dashboard/error.html error: {e}")
    
    html.append("</pre>")
    
    return HttpResponse(''.join(html))

def debug_dashboard_home(request):
    """Debug the dashboard_home view step by step."""
    from django.http import HttpResponse
    
    html = ["<h2 style='color:white;background:black;padding:20px;'>Dashboard Home Debug</h2><pre style='color:white;background:black;padding:20px;'>"]
    
    try:
        html.append("1. Testing context creation...")
        
        # Test the context creation step by step
        context = {}
        html.append("✅ Context initialized")
        
        context['page_title'] = 'Trading Dashboard'
        html.append("✅ Page title added")
        
        context['user_profile'] = {'display_name': 'Demo User'}
        html.append("✅ User profile added")
        
        context['bot_configs'] = []
        html.append("✅ Bot configs added")
        
        context['active_sessions'] = []
        html.append("✅ Active sessions added")
        
        context['engine_status'] = {
            'status': 'OPERATIONAL',
            'message': 'Demo mode - all systems operational',
            'fast_lane_active': True,
            'smart_lane_active': False,
            'mempool_connected': True,
            'risk_cache_status': 'HEALTHY',
            'is_mock': True
        }
        html.append("✅ Engine status added")
        
        context['performance_metrics'] = {
            'execution_time_ms': 78.5,
            'success_rate': 94.2,
            'trades_per_minute': 12.3,
            'risk_cache_hits': 98,
            'mempool_latency_ms': 1.2,
            'gas_optimization_ms': 15.8,
            'fast_lane_trades_today': 67,
            'smart_lane_trades_today': 23,
            'is_mock': True
        }
        html.append("✅ Performance metrics added")
        
        context['show_onboarding'] = False
        context['user'] = {'username': 'demo_user', 'is_authenticated': True}
        html.append("✅ All context created successfully")
        
        html.append("\n2. Testing template render...")
        
        # Try to render the template
        from django.shortcuts import render
        response = render(request, 'dashboard/home.html', context)
        html.append("✅ Template rendered successfully!")
        html.append(f"Response status: {response.status_code}")
        
    except Exception as e:
        html.append(f"❌ Error: {e}")
        import traceback
        html.append(f"\nTraceback:\n{traceback.format_exc()}")
    
    html.append("</pre>")
    return HttpResponse(''.join(html))



def debug_mode_selection(request):
    """Debug the mode selection view step by step."""
    from django.http import HttpResponse
    
    html = ["<h2 style='color:white;background:black;padding:20px;'>Mode Selection Debug</h2><pre style='color:white;background:black;padding:20px;'>"]
    
    try:
        html.append("1. Testing context creation...")
        
        # Test the context creation step by step
        fast_lane_metrics = {
            'execution_time_ms': 78.5,
            'success_rate': 94.2,
            'trades_per_minute': 12.3,
            'is_mock': True
        }
        html.append("✅ Fast lane metrics created")
        
        smart_lane_metrics = {
            'execution_time_ms': 2500,
            'success_rate': 96.2,
            'risk_adjusted_return': 15.3,
            'is_mock': True
        }
        html.append("✅ Smart lane metrics created")
        
        context = {
            'page_title': 'Mode Selection - Fast Lane vs Smart Lane',
            'fast_lane_metrics': fast_lane_metrics,
            'smart_lane_metrics': smart_lane_metrics
        }
        html.append("✅ Context created successfully")
        
        html.append("\n2. Testing template render...")
        
        # Try to render the template
        from django.shortcuts import render
        response = render(request, 'dashboard/mode_selection.html', context)
        html.append("✅ Template rendered successfully!")
        html.append(f"Response status: {response.status_code}")
        
    except Exception as e:
        html.append(f"❌ Error: {e}")
        import traceback
        html.append(f"\nTraceback:\n{traceback.format_exc()}")
    
    html.append("</pre>")
    return HttpResponse(''.join(html))



# Replace your existing configuration_panel function in dashboard/views.py with this:

def configuration_panel(request, mode):
    """
    Comprehensive configuration panel for specific trading mode.
    
    Includes thorough error handling, logging, form validation,
    and user feedback for production-ready configuration management.
    
    Args:
        mode: Either 'fast_lane' or 'smart_lane'
    """
    # Input validation and logging
    logger.info(f"Configuration panel accessed for mode: {mode} by user: {getattr(request.user, 'username', 'anonymous')}")
    
    if mode not in ['fast_lane', 'smart_lane']:
        logger.warning(f"Invalid trading mode attempted: {mode} by user: {getattr(request.user, 'username', 'anonymous')}")
        messages.error(request, "Invalid trading mode specified.")
        return redirect('dashboard:home')
    
    try:
        # Get or create demo user for testing
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
            logger.info(f"Created demo user for configuration panel")
        
        mode_display = mode.replace('_', ' ').title()
        logger.debug(f"Processing {mode_display} configuration for user: {request.user.username}")
        
        # Handle POST request (form submission)
        if request.method == 'POST':
            logger.info(f"Processing {mode_display} configuration form submission")
            return handle_configuration_update(request, mode, mode_display)
        
        # Handle GET request (display form)
        try:
            # Get or create default configuration for this mode
            default_config, config_created = BotConfiguration.objects.get_or_create(
                user=request.user,
                trading_mode=mode.upper(),
                is_default=True,
                defaults={
                    'name': f'Default {mode_display} Config',
                    'status': 'INACTIVE',
                    'description': f'Default configuration for {mode_display} trading',
                    'max_position_size_usd': 100.0,
                    'risk_tolerance_level': 'MEDIUM',
                    'execution_timeout_ms': 500 if mode == 'fast_lane' else 5000,
                    'auto_execution_enabled': False,
                    'require_manual_approval': True,
                    'max_slippage_percent': 2.0,
                    'mev_protection_enabled': True,
                    'analysis_depth': 'COMPREHENSIVE' if mode == 'smart_lane' else 'BASIC'
                }
            )
            
            if config_created:
                logger.info(f"Created new default {mode_display} configuration for user: {request.user.username}")
            else:
                logger.debug(f"Retrieved existing {mode_display} configuration for user: {request.user.username}")
            
        except Exception as db_error:
            logger.error(f"Database error creating/retrieving configuration: {db_error}")
            # Create a minimal fallback configuration
            default_config = type('Config', (), {
                'name': f'Default {mode_display} Config',
                'description': f'Default configuration for {mode_display} trading',
                'max_position_size_usd': 100.0,
                'risk_tolerance_level': 'MEDIUM',
                'execution_timeout_ms': 500 if mode == 'fast_lane' else 5000,
                'auto_execution_enabled': False,
                'require_manual_approval': True,
                'max_slippage_percent': 2.0,
                'mev_protection_enabled': True,
            })()
            messages.warning(request, "Using default settings due to database connectivity issues.")
        
        # Prepare template context
        context = {
            'mode': mode,
            'mode_display': mode_display,
            'config': default_config,
            'page_title': f'{mode_display} Configuration',
            'user': request.user,
        }
        
        logger.debug(f"Rendering {mode_display} configuration template with context")
        return render(request, 'dashboard/configuration_panel.html', context)
        
    except Exception as e:
        logger.error(f"Unexpected error in configuration_panel for {mode}: {e}", exc_info=True)
        messages.error(request, f"Error loading {mode.replace('_', ' ').lower()} configuration. Please try again.")
        return redirect('dashboard:home')



def handle_configuration_update(request, mode: str, mode_display: str):
    """
    Handle configuration form submission with comprehensive validation and error handling.
    
    Args:
        request: Django request object
        mode: Trading mode ('fast_lane' or 'smart_lane')
        mode_display: Display name for the mode
        
    Returns:
        JsonResponse with success/error status
    """
    try:
        logger.info(f"Processing {mode_display} configuration update for user: {request.user.username}")
        
        # Validate CSRF token
        if not request.POST.get('csrfmiddlewaretoken'):
            logger.warning(f"Missing CSRF token in {mode_display} configuration update")
            return JsonResponse({
                'success': False, 
                'error': 'Security token missing. Please refresh and try again.'
            })
        
        # Extract and validate form data
        form_data = {}
        errors = []
        
        # Required fields validation
        required_fields = {
            'name': 'Configuration name',
            'max_position_size_usd': 'Maximum position size',
            'risk_tolerance': 'Risk tolerance level'
        }
        
        for field, display_name in required_fields.items():
            value = request.POST.get(field, '').strip()
            if not value:
                errors.append(f'{display_name} is required.')
                logger.warning(f"Missing required field {field} in {mode_display} configuration")
            else:
                form_data[field] = value
        
        # Validate numeric fields
        try:
            position_size = float(request.POST.get('max_position_size_usd', 0))
            if position_size < 1 or position_size > 10000:
                errors.append('Position size must be between $1 and $10,000.')
                logger.warning(f"Invalid position size: {position_size} in {mode_display} configuration")
            else:
                form_data['max_position_size_usd'] = position_size
        except (ValueError, TypeError):
            errors.append('Position size must be a valid number.')
            logger.warning(f"Invalid position size format in {mode_display} configuration")
        
        # Mode-specific validation
        if mode == 'fast_lane':
            try:
                timeout = int(request.POST.get('execution_timeout_ms', 500))
                if timeout < 50 or timeout > 2000:
                    errors.append('Execution timeout must be between 50ms and 2000ms.')
                    logger.warning(f"Invalid execution timeout: {timeout} in Fast Lane configuration")
                else:
                    form_data['execution_timeout_ms'] = timeout
            except (ValueError, TypeError):
                errors.append('Execution timeout must be a valid number.')
                logger.warning(f"Invalid execution timeout format in Fast Lane configuration")
            
            # Validate slippage if provided
            slippage = request.POST.get('max_slippage_percent')
            if slippage:
                try:
                    slippage_val = float(slippage)
                    if slippage_val < 0.1 or slippage_val > 10.0:
                        errors.append('Slippage must be between 0.1% and 10.0%.')
                    else:
                        form_data['max_slippage_percent'] = slippage_val
                except (ValueError, TypeError):
                    errors.append('Slippage must be a valid number.')
        
        # Return validation errors if any
        if errors:
            logger.warning(f"Validation errors in {mode_display} configuration: {errors}")
            return JsonResponse({
                'success': False,
                'error': 'Please correct the following errors: ' + '; '.join(errors)
            })
        
        # Try to save configuration
        try:
            # Get or create configuration
            config, created = BotConfiguration.objects.get_or_create(
                user=request.user,
                trading_mode=mode.upper(),
                is_default=True,
                defaults={}
            )
            
            # Update configuration with validated data
            config.name = form_data['name']
            config.description = request.POST.get('description', '')
            config.max_position_size_usd = form_data['max_position_size_usd']
            config.risk_tolerance_level = form_data['risk_tolerance']
            
            # Mode-specific updates
            if mode == 'fast_lane':
                config.execution_timeout_ms = form_data.get('execution_timeout_ms', 500)
                config.max_slippage_percent = form_data.get('max_slippage_percent', 2.0)
                config.mev_protection_enabled = request.POST.get('mev_protection_enabled') == 'on'
                config.auto_execution_enabled = request.POST.get('auto_execution_enabled') == 'on'
                config.require_manual_approval = request.POST.get('require_manual_approval') == 'on'
            else:  # smart_lane
                config.analysis_depth = 'COMPREHENSIVE'  # Fixed for Phase 5
            
            # Update timestamps
            config.updated_at = datetime.now()
            config.version += 1
            
            # Save to database
            config.save()
            
            logger.info(f"Successfully saved {mode_display} configuration for user: {request.user.username}")
            
            # Log configuration details for audit
            logger.debug(f"Configuration saved - Name: {config.name}, "
                        f"Position Size: ${config.max_position_size_usd}, "
                        f"Risk Level: {config.risk_tolerance_level}")
            
            return JsonResponse({
                'success': True,
                'message': f'{mode_display} configuration saved successfully!',
                'config_id': config.id
            })
            
        except IntegrityError as db_error:
            logger.error(f"Database integrity error saving {mode_display} configuration: {db_error}")
            return JsonResponse({
                'success': False,
                'error': 'Configuration name already exists. Please choose a different name.'
            })
        except Exception as db_error:
            logger.error(f"Database error saving {mode_display} configuration: {db_error}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to save configuration due to database error. Please try again.'
            })
    
    except Exception as e:
        logger.error(f"Unexpected error in handle_configuration_update for {mode}: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'An unexpected error occurred. Please try again or contact support.'
        })
    



def debug_configuration_panel(request, mode):
    """Debug version to identify the configuration panel issue."""
    from django.http import HttpResponse
    
    html = [f"<h2 style='color:white;background:black;padding:20px;'>Configuration Panel Debug - {mode}</h2>"]
    html.append("<pre style='color:white;background:black;padding:20px;'>")
    
    try:
        html.append("1. Checking mode validation...")
        if mode not in ['fast_lane', 'smart_lane']:
            html.append("❌ Invalid mode")
            return HttpResponse(''.join(html))
        html.append("✅ Mode is valid")
        
        html.append("2. Setting up user...")
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
        html.append("✅ User setup complete")
        
        html.append("3. Creating mode display...")
        mode_display = mode.replace('_', ' ').title()
        html.append(f"✅ Mode display: {mode_display}")
        
        html.append("4. Testing database access...")
        from .models import BotConfiguration
        html.append("✅ BotConfiguration model imported")
        
        html.append("5. Testing configuration creation...")
        default_config, config_created = BotConfiguration.objects.get_or_create(
            user=request.user,
            trading_mode=mode.upper(),
            is_default=True,
            defaults={
                'name': f'Default {mode_display} Config',
                'status': 'INACTIVE',
                'description': f'Default configuration for {mode_display} trading',
                'max_position_size_usd': 100.0,
                'risk_tolerance_level': 'MEDIUM',
            }
        )
        html.append(f"✅ Configuration {'created' if config_created else 'retrieved'}")
        
        html.append("6. Testing template context...")
        context = {
            'mode': mode,
            'mode_display': mode_display,
            'config': default_config,
            'page_title': f'{mode_display} Configuration',
            'user': request.user,
        }
        html.append("✅ Context created")
        
        html.append("7. Testing template render...")
        from django.shortcuts import render
        response = render(request, 'dashboard/configuration_panel.html', context)
        html.append("✅ Template rendered successfully!")
        
        # If we get here, the template rendering worked
        return response
        
    except Exception as e:
        html.append(f"❌ Error at step: {e}")
        import traceback
        html.append(f"\nFull traceback:\n{traceback.format_exc()}")
    
    html.append("</pre>")
    return HttpResponse(''.join(html))