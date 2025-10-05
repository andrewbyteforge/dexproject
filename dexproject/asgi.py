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

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')

# Initialize Django ASGI application early to ensure AppRegistry is populated
django_asgi_app = get_asgi_application()

# Import dashboard consumers after Django is set up
from dashboard.consumers import DashboardMetricsConsumer
# Import paper trading routing
from paper_trading.routing import websocket_urlpatterns as paper_trading_ws

# Define WebSocket URL patterns for dashboard
websocket_urlpatterns = [
    re_path(r'^ws/dashboard/metrics/?$', DashboardMetricsConsumer.as_asgi()),
    re_path(r'^ws/dashboard/charts/?$', DashboardMetricsConsumer.as_asgi()),
]


# Combine all WebSocket patterns
all_websocket_urlpatterns = websocket_urlpatterns + paper_trading_ws

# ASGI application with protocol routing
application = ProtocolTypeRouter({
    # HTTP requests (including SSE)
    "http": django_asgi_app,
   
    # WebSocket connections
    "websocket": AuthMiddlewareStack(
        URLRouter(all_websocket_urlpatterns)
    ),
})