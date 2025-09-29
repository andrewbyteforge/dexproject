"""
ASGI config for dexproject project.

Enhanced to support Server-Sent Events (SSE) for real-time dashboard updates
and WebSocket connections for paper trading real-time updates.
Configured for production deployment with Daphne/Uvicorn workers.

FIXED: Added AllowedHostsOriginValidator and proper WebSocket configuration

File: dexproject/asgi.py
"""

import os
from django.core.asgi import get_asgi_application
from django.urls import re_path
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')

# Initialize Django ASGI application early to ensure AppRegistry is populated
django_asgi_app = get_asgi_application()

# Import consumers after Django is set up to avoid circular imports
from dashboard.consumers import DashboardMetricsConsumer
from paper_trading.consumers import PaperTradingConsumer

# =============================================================================
# WEBSOCKET URL PATTERNS
# =============================================================================

websocket_urlpatterns = [
    # Dashboard metrics WebSocket (Phase 2)
    re_path(
        r'ws/dashboard/metrics/$',
        DashboardMetricsConsumer.as_asgi(),
        name='ws_dashboard_metrics'
    ),
    
    # Paper trading real-time updates WebSocket (PTphase 3)
    re_path(
        r'ws/paper-trading/$',
        PaperTradingConsumer.as_asgi(),
        name='ws_paper_trading'
    ),
]

# =============================================================================
# ASGI APPLICATION WITH PROTOCOL ROUTING
# =============================================================================

application = ProtocolTypeRouter({
    # HTTP requests (including SSE)
    "http": django_asgi_app,
    
    # WebSocket connections with proper validation
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})