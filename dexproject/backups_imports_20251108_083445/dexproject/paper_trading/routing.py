"""
WebSocket URL routing for paper trading.

File: dexproject/paper_trading/routing.py
"""

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/paper-trading/$', consumers.PaperTradingConsumer.as_asgi()),
]