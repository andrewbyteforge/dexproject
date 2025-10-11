"""
ASGI config for dexproject project.
Enhanced to support Server-Sent Events (SSE) for real-time dashboard updates.
Configured for production deployment with Daphne/Uvicorn workers.
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

# Import consumers after Django is set up
from dashboard.consumers import DashboardMetricsConsumer
from paper_trading.consumers import PaperTradingConsumer

# Define WebSocket URL patterns
websocket_urlpatterns = [
    # Dashboard WebSocket endpoints (without ^ anchor)
    re_path(r'ws/dashboard/metrics/?$', DashboardMetricsConsumer.as_asgi()),
    re_path(r'ws/dashboard/charts/?$', DashboardMetricsConsumer.as_asgi()),
    
    # Paper trading WebSocket endpoint
    re_path(r'ws/paper-trading/?$', PaperTradingConsumer.as_asgi()),
]

# ASGI application with protocol routing
application = ProtocolTypeRouter({
    # HTTP requests (including SSE)
    "http": django_asgi_app,
    
    # WebSocket connections with security
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})