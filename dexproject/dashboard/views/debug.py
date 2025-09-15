"""
Debug and Development Views

Testing and debugging tools for development environment.
Split from the original monolithic views.py file for better organization.

File: dashboard/views/debug.py
"""

import logging
from datetime import datetime
from typing import Dict, Any

from django.http import HttpResponse, HttpRequest
from django.shortcuts import render
from django.conf import settings
from django.template.loader import get_template

from ..engine_service import engine_service

logger = logging.getLogger(__name__)


def simple_test(request: HttpRequest) -> HttpResponse:
    """
    Simple test endpoint for basic functionality verification.
    
    Provides a minimal response to verify that the Django application
    is running and basic view functionality is working.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse with simple test message
    """
    logger.debug("Simple test endpoint accessed")
    
    test_data = {
        'timestamp': datetime.now().isoformat(),
        'user': str(request.user) if request.user.is_authenticated else 'Anonymous',
        'method': request.method,
        'path': request.path,
        'status': 'OK'
    }
    
    html_content = f"""
    <html>
    <head>
        <title>Dashboard Test</title>
        <style>
            body {{ 
                font-family: Arial, sans-serif; 
                margin: 40px; 
                background: #f8f9fa; 
            }}
            .test-container {{ 
                background: white; 
                padding: 20px; 
                border-radius: 8px; 
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
            }}
            .success {{ color: #28a745; }}
            .info {{ color: #007bff; }}
            pre {{ 
                background: #f8f9fa; 
                padding: 15px; 
                border-radius: 4px; 
                border-left: 4px solid #007bff; 
            }}
        </style>
    </head>
    <body>
        <div class="test-container">
            <h1 class="success">✅ Dashboard Test Successful</h1>
            <p class="info">Django application is running correctly.</p>
            
            <h3>Test Data:</h3>
            <pre>{str(test_data)}</pre>
            
            <h3>Quick Links:</h3>
            <ul>
                <li><a href="/dashboard/">Dashboard Home</a></li>
                <li><a href="/dashboard/mode-selection/">Mode Selection</a></li>
                <li><a href="/dashboard/debug-templates/">Template Debug</a></li>
                <li><a href="/dashboard/minimal/">Minimal Dashboard</a></li>
            </ul>
        </div>
    </body>
    </html>
    """
    
    return HttpResponse(html_content)


def debug_templates(request: HttpRequest) -> HttpResponse:
    """
    Template debugging tool for checking template loading and configuration.
    
    Tests template loading functionality and provides detailed reporting
    on template availability and Django configuration.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse with template debug information
    """
    logger.debug("Template debug endpoint accessed")
    
    html = ["<h2 style='color:white;background:black;padding:20px;'>Template Debug Report</h2>"]
    html.append("<pre style='color:white;background:black;padding:20px;'>")
    
    # Test template loading
    templates_to_test = [
        'base.html',
        'dashboard/home.html',
        'dashboard/mode_selection.html',
        'dashboard/configuration_panel.html',
        'dashboard/configuration_summary.html',
        'dashboard/configuration_list.html',
        'dashboard/session_monitor.html',
        'dashboard/session_summary.html',
        'dashboard/error.html'
    ]
    
    for template_name in templates_to_test:
        try:
            get_template(template_name)
            html.append(f"✅ {template_name}: Found")
        except Exception as e:
            html.append(f"❌ {template_name}: Error - {e}")
    
    # Show Django settings
    html.append(f"\nDjango Settings:")
    html.append(f"  Debug Mode: {settings.DEBUG}")
    html.append(f"  Template Directories: {settings.TEMPLATES[0]['DIRS']}")
    html.append(f"  Template Debug: {settings.TEMPLATES[0]['OPTIONS'].get('debug', False)}")
    html.append(f"  App Directories: {settings.TEMPLATES[0]['OPTIONS'].get('APP_DIRS', False)}")
    
    # Engine status
    try:
        engine_status = engine_service.get_engine_status()
        html.append(f"\nEngine Status:")
        html.append(f"  Status: {engine_status.get('status', 'UNKNOWN')}")
        html.append(f"  Mock Mode: {engine_service.mock_mode}")
        html.append(f"  Fast Lane Active: {engine_status.get('fast_lane_active', False)}")
        html.append(f"  Smart Lane Active: {engine_status.get('smart_lane_active', False)}")
    except Exception as e:
        html.append(f"\nEngine Status: Error - {e}")
    
    # Phase status
    html.append(f"\nPhase Status:")
    html.append(f"  Fast Lane Enabled: {getattr(settings, 'FAST_LANE_ENABLED', False)}")
    html.append(f"  Smart Lane Enabled: {getattr(settings, 'SMART_LANE_ENABLED', False)}")
    html.append(f"  Engine Mock Mode: {getattr(settings, 'ENGINE_MOCK_MODE', True)}")
    
    html.append("</pre>")
    return HttpResponse(''.join(html))


def minimal_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Minimal dashboard without template dependencies for emergency access.
    
    Provides a fallback dashboard interface that doesn't rely on complex templates.
    Useful for debugging template issues or providing emergency access.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse with minimal dashboard HTML
    """
    logger.debug("Minimal dashboard accessed")
    
    # Get basic status information
    try:
        engine_status = engine_service.get_engine_status()
        performance_metrics = engine_service.get_performance_metrics()
        system_operational = True
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        engine_status = {'status': 'ERROR', '_mock': True}
        performance_metrics = {'execution_time_ms': 0, '_mock': True}
        system_operational = False
    
    # Generate minimal HTML interface
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>DEX Trading Bot - Minimal Dashboard</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0; 
                padding: 20px; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
            }}
            .container {{ 
                max-width: 1200px; 
                margin: 0 auto; 
            }}
            .header {{ 
                background: rgba(255,255,255,0.1); 
                padding: 20px; 
                border-radius: 10px; 
                margin-bottom: 20px;
                backdrop-filter: blur(10px);
            }}
            .status-grid {{ 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); 
                gap: 20px; 
                margin-bottom: 20px;
            }}
            .status-card {{ 
                background: rgba(255,255,255,0.1); 
                padding: 20px; 
                border-radius: 10px;
                backdrop-filter: blur(10px);
            }}
            .status-ok {{ border-left: 5px solid #28a745; }}
            .status-warning {{ border-left: 5px solid #ffc107; }}
            .status-error {{ border-left: 5px solid #dc3545; }}
            .metric {{ 
                display: flex; 
                justify-content: space-between; 
                margin: 10px 0;
                padding: 8px 0;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }}
            .metric:last-child {{ border-bottom: none; }}
            .nav-links {{ 
                background: rgba(255,255,255,0.1); 
                padding: 20px; 
                border-radius: 10px;
                backdrop-filter: blur(10px);
            }}
            .nav-links a {{ 
                color: white; 
                text-decoration: none; 
                margin-right: 20px; 
                padding: 10px 15px; 
                background: rgba(255,255,255,0.2); 
                border-radius: 5px; 
                display: inline-block; 
                margin-bottom: 10px;
            }}
            .nav-links a:hover {{ 
                background: rgba(255,255,255,0.3); 
            }}
            .timestamp {{ 
                font-size: 0.9em; 
                opacity: 0.8; 
                text-align: right; 
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 DEX Trading Bot - Minimal Dashboard</h1>
                <p>Emergency access interface | User: {request.user.username if request.user.is_authenticated else 'Anonymous'}</p>
                <div class="timestamp">Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</div>
            </div>
            
            <div class="status-grid">
                <div class="status-card {'status-ok' if system_operational else 'status-error'}">
                    <h3>🏁 Fast Lane Status</h3>
                    <div class="metric">
                        <span>Status:</span>
                        <strong>{engine_status.get('status', 'UNKNOWN')}</strong>
                    </div>
                    <div class="metric">
                        <span>Active:</span>
                        <strong>{'Yes' if engine_status.get('fast_lane_active', False) else 'No'}</strong>
                    </div>
                    <div class="metric">
                        <span>Execution Time:</span>
                        <strong>{performance_metrics.get('execution_time_ms', 0):.1f}ms</strong>
                    </div>
                    <div class="metric">
                        <span>Success Rate:</span>
                        <strong>{performance_metrics.get('success_rate', 0):.1f}%</strong>
                    </div>
                </div>
                
                <div class="status-card {'status-ok' if getattr(settings, 'SMART_LANE_ENABLED', False) else 'status-warning'}">
                    <h3>🧠 Smart Lane Status</h3>
                    <div class="metric">
                        <span>Enabled:</span>
                        <strong>{'Yes' if getattr(settings, 'SMART_LANE_ENABLED', False) else 'No (Phase 5)'}</strong>
                    </div>
                    <div class="metric">
                        <span>Active:</span>
                        <strong>{'Yes' if engine_status.get('smart_lane_active', False) else 'No'}</strong>
                    </div>
                    <div class="metric">
                        <span>Analyzers:</span>
                        <strong>{engine_status.get('analyzers_count', 5)}</strong>
                    </div>
                    <div class="metric">
                        <span>AI Thought Log:</span>
                        <strong>{'Ready' if getattr(settings, 'SMART_LANE_ENABLED', False) else 'Pending'}</strong>
                    </div>
                </div>
                
                <div class="status-card status-ok">
                    <h3>⚙️ System Info</h3>
                    <div class="metric">
                        <span>Data Source:</span>
                        <strong>{'LIVE' if not engine_status.get('_mock', False) else 'MOCK'}</strong>
                    </div>
                    <div class="metric">
                        <span>Mock Mode:</span>
                        <strong>{'Yes' if getattr(settings, 'ENGINE_MOCK_MODE', True) else 'No'}</strong>
                    </div>
                    <div class="metric">
                        <span>Debug Mode:</span>
                        <strong>{'Yes' if settings.DEBUG else 'No'}</strong>
                    </div>
                    <div class="metric">
                        <span>Mempool Connected:</span>
                        <strong>{'Yes' if engine_status.get('mempool_connected', False) else 'No'}</strong>
                    </div>
                </div>
            </div>
            
            <div class="nav-links">
                <h3>🔗 Navigation</h3>
                <a href="/dashboard/">Full Dashboard</a>
                <a href="/dashboard/mode-selection/">Mode Selection</a>
                <a href="/dashboard/configs/">Configurations</a>
                <a href="/dashboard/debug-templates/">Template Debug</a>
                <a href="/dashboard/test/">Simple Test</a>
                <a href="/admin/">Admin Panel</a>
                
                <h4 style="margin-top: 20px;">Phase Status:</h4>
                <div style="margin-top: 10px;">
                    ✅ Phase 0: Architecture Foundation<br>
                    ✅ Phase 1: Foundation URLs & Views<br>
                    ✅ Phase 2: Dashboard Integration<br>
                    ✅ Phase 3: Mempool Integration<br>
                    ✅ Phase 4: Fast Lane Engine<br>
                    {'✅' if getattr(settings, 'SMART_LANE_ENABLED', False) else '🔄'} Phase 5: Smart Lane Integration<br>
                    ⏳ Phase 6: Performance Optimization<br>
                    ⏳ Phase 7: Production Deployment
                </div>
            </div>
        </div>
        
        <script>
            // Auto-refresh every 30 seconds
            setTimeout(() => location.reload(), 30000);
        </script>
    </body>
    </html>
    """
    
    return HttpResponse(html_content)


def engine_debug(request: HttpRequest) -> HttpResponse:
    """
    Engine debugging interface for development.
    
    Provides detailed engine status, configuration, and diagnostic information
    for debugging engine integration issues.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        HttpResponse with engine debug information
    """
    logger.debug("Engine debug endpoint accessed")
    
    debug_data = _collect_engine_debug_data()
    
    context = {
        'page_title': 'Engine Debug',
        'debug_data': debug_data,
        'timestamp': datetime.now().isoformat(),
        'user': request.user
    }
    
    # Use minimal template or render directly
    try:
        return render(request, 'dashboard/engine_debug.html', context)
    except Exception:
        # Fallback to HTML response
        html_content = f"""
        <h1>Engine Debug Information</h1>
        <pre>{str(debug_data)}</pre>
        <p><a href="/dashboard/">Back to Dashboard</a></p>
        """
        return HttpResponse(html_content)


# =========================================================================
# HELPER FUNCTIONS
# =========================================================================

def _collect_engine_debug_data() -> Dict[str, Any]:
    """Collect comprehensive engine debug information."""
    debug_data = {
        'timestamp': datetime.now().isoformat(),
        'django_settings': {
            'DEBUG': settings.DEBUG,
            'ENGINE_MOCK_MODE': getattr(settings, 'ENGINE_MOCK_MODE', True),
            'FAST_LANE_ENABLED': getattr(settings, 'FAST_LANE_ENABLED', True),
            'SMART_LANE_ENABLED': getattr(settings, 'SMART_LANE_ENABLED', False),
        }
    }
    
    # Engine service status
    try:
        debug_data['engine_service'] = {
            'mock_mode': engine_service.mock_mode,
            'engine_initialized': engine_service.engine_initialized,
            'circuit_breaker_state': engine_service.circuit_breaker.state,
            'circuit_breaker_failures': engine_service.circuit_breaker.failure_count
        }
        
        debug_data['engine_status'] = engine_service.get_engine_status()
        debug_data['performance_metrics'] = engine_service.get_performance_metrics()
        
    except Exception as e:
        debug_data['engine_error'] = str(e)
    
    # Smart Lane status (if available)
    try:
        from ..smart_lane_service import smart_lane_service
        debug_data['smart_lane_service'] = {
            'mock_mode': smart_lane_service.mock_mode,
            'smart_lane_enabled': smart_lane_service.smart_lane_enabled,
            'pipeline_initialized': smart_lane_service.pipeline_initialized,
            'circuit_breaker_state': smart_lane_service.circuit_breaker.state
        }
        debug_data['smart_lane_status'] = smart_lane_service.get_pipeline_status()
        debug_data['smart_lane_metrics'] = smart_lane_service.get_analysis_metrics()
    except ImportError:
        debug_data['smart_lane_service'] = 'Not available (Phase 5 pending)'
    except Exception as e:
        debug_data['smart_lane_error'] = str(e)
    
    return debug_data