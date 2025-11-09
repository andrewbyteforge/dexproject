"""
Paper Trading Services Package - Phase 7A Update

This package contains paper trading services for price feeds,
trade simulation, WebSocket notifications, and order management.

Services:
- Price Feed Service: Real-time token price aggregation with caching
- Simulator: Paper trade execution with real market data
- WebSocket Service: Real-time client notifications
- Order Manager Service: Advanced order type management (Phase 7A)

UPDATED: Added OrderManager service for Phase 7A (Advanced Order Types)

File: paper_trading/services/__init__.py
"""

# Price Feed Service
from .price_feed_service import (
    PriceFeedService,
    get_default_price_feed_service,
    get_bulk_token_prices_simple
)

# Simulator Service
from .simulator import (
    SimplePaperTradingSimulator,
    SimplePaperTradeRequest,
    SimplePaperTradeResult,
    get_simulator
)

# WebSocket Service
from .websocket_service import (
    PaperTradingWebSocketService,
    get_websocket_service
)

# Order Manager Service - Phase 7A (NEW)
from .order_manager import (
    OrderManager,
    get_order_manager
)

__all__ = [
    # Price Feed Service
    'PriceFeedService',
    'get_default_price_feed_service',
    'get_bulk_token_prices_simple',
    
    # Simulator Service
    'SimplePaperTradingSimulator',
    'SimplePaperTradeRequest',
    'SimplePaperTradeResult',
    'get_simulator',
    
    # WebSocket Service
    'PaperTradingWebSocketService',
    'get_websocket_service',
    
    # Order Manager Service - Phase 7A
    'OrderManager',
    'get_order_manager',
]