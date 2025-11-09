"""
Paper Trading Services Package - Phase 7A Update

This package contains paper trading services for price feeds,
trade simulation, WebSocket notifications, and order management.

Services:
- Price Feed Service: Real-time token price aggregation with caching
- Simulator: Paper trade execution with real market data
- WebSocket Service: Real-time client notifications
- Order Manager Service: Advanced order type management (Phase 7A Day 2)
- Order Executor Service: Order execution engine (Phase 7A Day 4)

File: paper_trading/services/__init__.py
"""

# Import price feed service components
from .price_feed_service import (
    PriceFeedService,
    get_default_price_feed_service,
    get_bulk_token_prices_simple,
)

# Import simulator components
from .simulator import (
    SimplePaperTradingSimulator,
    SimplePaperTradeRequest,
    SimplePaperTradeResult,
    get_simulator,
)

# Import WebSocket service components
from .websocket_service import (
    websocket_service as PaperTradingWebSocketService,
    websocket_service,
)

# Import Order Manager components (Phase 7A Day 2)
from .order_manager import (
    OrderManager,
    get_order_manager,
)

# Import Order Executor components (Phase 7A Day 4)
from .order_executor import (
    OrderExecutor,
    get_order_executor,
    execute_order,
)

# Define public API
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
    'websocket_service',
    
    # Order Manager Service - Phase 7A Day 2
    'OrderManager',
    'get_order_manager',
    
    # Order Executor Service - Phase 7A Day 4
    'OrderExecutor',
    'get_order_executor',
    'execute_order',
]