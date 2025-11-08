"""
Async Trading Engine Package

This package contains the standalone async trading engine that handles
the latency-critical trading operations separate from Django.

The engine is responsible for:
- Discovery: Monitoring new token pairs via WebSocket/HTTP
- Risk Assessment: Running critical risk checks in parallel
- Execution: Paper trading and live trade execution
- Portfolio Management: Circuit breakers and risk limits
"""

__version__ = "0.1.0"
__author__ = "DEX Trading Bot"

# Engine status constants
class EngineStatus:
    """Engine operational status constants."""
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"

# Risk severity levels
class RiskLevel:
    """Risk assessment severity levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM" 
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

# Trading modes
class TradingMode:
    """Trading execution modes."""
    PAPER = "PAPER"          # Simulate trades only
    SHADOW = "SHADOW"        # Run paper + live in parallel
    LIVE = "LIVE"            # Execute real trades

# Chain identifiers
class Chain:
    """Supported blockchain networks."""
    ETHEREUM = 1
    BASE = 8453
    
    # Human-readable names
    NAMES = {
        ETHEREUM: "Ethereum",
        BASE: "Base"
    }