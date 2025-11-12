"""
Paper Trading Constants - Enhanced with API Field Names + Phase 7A Order Support

This module contains all constant values used throughout the paper trading system.
These prevent typos, enable IDE autocomplete, and serve as single source of truth.

ENHANCED: Added API request/response field names and configuration constants
PHASE 7A: Added order-related constants for advanced order types

Location: paper_trading/constants.py

Usage:
    from paper_trading.constants import (
        DecisionType, ConfidenceLevel, ThoughtLogFields,
        ConfigAPIFields, BotControlFields, OrderType, OrderStatus
    )
"""

from decimal import Decimal
from typing import Final


# =============================================================================
# DECISION TYPES
# =============================================================================

class DecisionType:
    """
    Trading decision types.
    
    These match the DecisionType.choices in PaperAIThoughtLog model.
    """
    BUY: Final[str] = 'BUY'
    SELL: Final[str] = 'SELL'
    HOLD: Final[str] = 'HOLD'
    SKIP: Final[str] = 'SKIP'
    STOP_LOSS: Final[str] = 'STOP_LOSS'
    TAKE_PROFIT: Final[str] = 'TAKE_PROFIT'
    
    # Strategy-related decisions (Phase 7B)
    DCA_STRATEGY: Final[str] = 'DCA_STRATEGY'
    GRID_STRATEGY: Final[str] = 'GRID_STRATEGY'
    SPOT_BUY: Final[str] = 'SPOT_BUY'
    
    # All valid decision types
    ALL: Final[tuple] = (
        BUY, SELL, HOLD, SKIP, STOP_LOSS, TAKE_PROFIT,
        DCA_STRATEGY, GRID_STRATEGY, SPOT_BUY
    )
    
    # Actionable decisions (require execution)
    ACTIONABLE: Final[tuple] = (BUY, SELL, STOP_LOSS, TAKE_PROFIT)
    
    # Non-actionable decisions
    NON_ACTIONABLE: Final[tuple] = (HOLD, SKIP)
    
    # Strategy decisions
    STRATEGY_DECISIONS: Final[tuple] = (DCA_STRATEGY, GRID_STRATEGY, SPOT_BUY)


# =============================================================================
# CONFIDENCE LEVELS
# =============================================================================

class ConfidenceLevel:
    """
    Confidence level categories and thresholds.
    
    These match the confidence_level field in PaperAIThoughtLog model.
    """
    # String labels (for database storage)
    VERY_HIGH: Final[str] = 'VERY_HIGH'
    HIGH: Final[str] = 'HIGH'
    MEDIUM: Final[str] = 'MEDIUM'
    LOW: Final[str] = 'LOW'
    VERY_LOW: Final[str] = 'VERY_LOW'
    
    # Numeric thresholds (for conversion from percentage)
    THRESHOLD_VERY_HIGH: Final[Decimal] = Decimal('90.0')
    THRESHOLD_HIGH: Final[Decimal] = Decimal('70.0')
    THRESHOLD_MEDIUM: Final[Decimal] = Decimal('50.0')
    THRESHOLD_LOW: Final[Decimal] = Decimal('30.0')
    
    # All valid levels
    ALL: Final[tuple] = (VERY_HIGH, HIGH, MEDIUM, LOW, VERY_LOW)
    
    @staticmethod
    def from_percentage(confidence_percent: Decimal) -> str:
        """
        Convert confidence percentage to level string.
        
        Args:
            confidence_percent: Confidence as decimal (0-100)
            
        Returns:
            Confidence level string (VERY_HIGH, HIGH, MEDIUM, LOW, VERY_LOW)
        """
        if confidence_percent >= ConfidenceLevel.THRESHOLD_VERY_HIGH:
            return ConfidenceLevel.VERY_HIGH
        elif confidence_percent >= ConfidenceLevel.THRESHOLD_HIGH:
            return ConfidenceLevel.HIGH
        elif confidence_percent >= ConfidenceLevel.THRESHOLD_MEDIUM:
            return ConfidenceLevel.MEDIUM
        elif confidence_percent >= ConfidenceLevel.THRESHOLD_LOW:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW


# =============================================================================
# TRADING MODES
# =============================================================================

class TradingMode:
    """Trading execution modes for PaperStrategyConfiguration."""
    CONSERVATIVE: Final[str] = 'CONSERVATIVE'
    MODERATE: Final[str] = 'MODERATE'
    AGGRESSIVE: Final[str] = 'AGGRESSIVE'
    CUSTOM: Final[str] = 'CUSTOM'
    
    ALL: Final[tuple] = (CONSERVATIVE, MODERATE, AGGRESSIVE, CUSTOM)


# =============================================================================
# LANE TYPES
# =============================================================================

class LaneType:
    """Intelligence lane types."""
    FAST: Final[str] = 'FAST'
    SMART: Final[str] = 'SMART'
    
    ALL: Final[tuple] = (FAST, SMART)


# =============================================================================
# TRADE STATUS
# =============================================================================

class TradeStatus:
    """Paper trade execution status."""
    PENDING: Final[str] = 'PENDING'
    EXECUTED: Final[str] = 'EXECUTED'
    FAILED: Final[str] = 'FAILED'
    CANCELLED: Final[str] = 'CANCELLED'
    
    ALL: Final[tuple] = (PENDING, EXECUTED, FAILED, CANCELLED)


# =============================================================================
# SESSION STATUS
# =============================================================================

class SessionStatus:
    """Paper trading session status."""
    STARTING: Final[str] = 'STARTING'
    RUNNING: Final[str] = 'RUNNING'
    PAUSED: Final[str] = 'PAUSED'
    STOPPED: Final[str] = 'STOPPED'
    COMPLETED: Final[str] = 'COMPLETED'
    ERROR: Final[str] = 'ERROR'
    
    ALL: Final[tuple] = (STARTING, RUNNING, PAUSED, STOPPED, COMPLETED, ERROR)


# =============================================================================
# MODEL FIELD NAMES - PaperAIThoughtLog
# =============================================================================

class ThoughtLogFields:
    """
    Field names for PaperAIThoughtLog model.
    
    Use these instead of string literals to prevent field name mismatches.
    """
    # Identity
    THOUGHT_ID: Final[str] = 'thought_id'
    ACCOUNT: Final[str] = 'account'
    PAPER_TRADE: Final[str] = 'paper_trade'
    
    # Decision
    DECISION_TYPE: Final[str] = 'decision_type'
    TOKEN_ADDRESS: Final[str] = 'token_address'
    TOKEN_SYMBOL: Final[str] = 'token_symbol'
    
    # Confidence and scores
    CONFIDENCE_LEVEL: Final[str] = 'confidence_level'
    CONFIDENCE_PERCENT: Final[str] = 'confidence_percent'
    RISK_SCORE: Final[str] = 'risk_score'
    OPPORTUNITY_SCORE: Final[str] = 'opportunity_score'
    
    # Reasoning
    PRIMARY_REASONING: Final[str] = 'primary_reasoning'
    KEY_FACTORS: Final[str] = 'key_factors'
    POSITIVE_SIGNALS: Final[str] = 'positive_signals'
    NEGATIVE_SIGNALS: Final[str] = 'negative_signals'
    
    # Context
    MARKET_DATA: Final[str] = 'market_data'
    STRATEGY_NAME: Final[str] = 'strategy_name'
    LANE_USED: Final[str] = 'lane_used'
    
    # Timing
    CREATED_AT: Final[str] = 'created_at'
    ANALYSIS_TIME_MS: Final[str] = 'analysis_time_ms'


# =============================================================================
# MODEL FIELD NAMES - PaperTrade
# =============================================================================

class TradeFields:
    """Field names for PaperTrade model."""
    TRADE_ID: Final[str] = 'trade_id'
    ACCOUNT: Final[str] = 'account'
    SESSION: Final[str] = 'session'
    DECISION_TYPE: Final[str] = 'decision_type'
    TOKEN_ADDRESS: Final[str] = 'token_address'
    TOKEN_SYMBOL: Final[str] = 'token_symbol'
    AMOUNT_TOKEN: Final[str] = 'amount_token'
    AMOUNT_USD: Final[str] = 'amount_usd'
    ENTRY_PRICE: Final[str] = 'entry_price'
    EXIT_PRICE: Final[str] = 'exit_price'
    STATUS: Final[str] = 'status'
    EXECUTED_AT: Final[str] = 'executed_at'
    PROFIT_LOSS_USD: Final[str] = 'profit_loss_usd'
    PROFIT_LOSS_PERCENT: Final[str] = 'profit_loss_percent'


# =============================================================================
# MODEL FIELD NAMES - PaperStrategyConfiguration
# =============================================================================

class StrategyConfigFields:
    """Field names for PaperStrategyConfiguration model."""
    CONFIG_ID: Final[str] = 'config_id'
    ACCOUNT: Final[str] = 'account'
    NAME: Final[str] = 'name'
    IS_ACTIVE: Final[str] = 'is_active'
    TRADING_MODE: Final[str] = 'trading_mode'
    USE_FAST_LANE: Final[str] = 'use_fast_lane'
    USE_SMART_LANE: Final[str] = 'use_smart_lane'
    FAST_LANE_THRESHOLD_USD: Final[str] = 'fast_lane_threshold_usd'
    MAX_POSITION_SIZE_PERCENT: Final[str] = 'max_position_size_percent'
    MAX_POSITION_SIZE_PER_TOKEN_PERCENT: Final[str] = 'max_position_size_per_token_percent'
    STOP_LOSS_PERCENT: Final[str] = 'stop_loss_percent'
    TAKE_PROFIT_PERCENT: Final[str] = 'take_profit_percent'
    MAX_DAILY_TRADES: Final[str] = 'max_daily_trades'
    MAX_CONCURRENT_POSITIONS: Final[str] = 'max_concurrent_positions'
    MIN_LIQUIDITY_USD: Final[str] = 'min_liquidity_usd'
    MAX_SLIPPAGE_PERCENT: Final[str] = 'max_slippage_percent'
    
    # Phase 7B: Strategy preferences
    ENABLE_DCA: Final[str] = 'enable_dca'
    ENABLE_GRID: Final[str] = 'enable_grid'
    ENABLE_TWAP: Final[str] = 'enable_twap'
    ENABLE_VWAP: Final[str] = 'enable_vwap'
    DCA_NUM_INTERVALS: Final[str] = 'dca_num_intervals'
    DCA_INTERVAL_HOURS: Final[str] = 'dca_interval_hours'
    GRID_NUM_LEVELS: Final[str] = 'grid_num_levels'
    GRID_PROFIT_TARGET_PERCENT: Final[str] = 'grid_profit_target_percent'
    CONFIDENCE_THRESHOLD: Final[str] = 'confidence_threshold'
    ALLOWED_TOKENS: Final[str] = 'allowed_tokens'
    BLOCKED_TOKENS: Final[str] = 'blocked_tokens'
    CUSTOM_PARAMETERS: Final[str] = 'custom_parameters'
    CREATED_AT: Final[str] = 'created_at'
    UPDATED_AT: Final[str] = 'updated_at'
    MAX_HOLD_HOURS: Final[str] = 'max_hold_hours'


# =============================================================================
# API REQUEST/RESPONSE FIELD NAMES
# =============================================================================

class ConfigAPIFields:
    """
    Field names for Configuration API requests and responses.
    
    Used in api/config_api.py for GET/POST /api/configuration/
    """
    # Request fields (POST body)
    NAME: Final[str] = 'name'
    TRADING_MODE: Final[str] = 'trading_mode'
    MAX_POSITION_SIZE_PERCENT: Final[str] = 'max_position_size_percent'
    STOP_LOSS_PERCENT: Final[str] = 'stop_loss_percent'
    TAKE_PROFIT_PERCENT: Final[str] = 'take_profit_percent'
    MAX_HOLD_HOURS: Final[str] = 'max_hold_hours'
    MAX_DAILY_TRADES: Final[str] = 'max_daily_trades'
    MAX_CONCURRENT_POSITIONS: Final[str] = 'max_concurrent_positions'
    CONFIDENCE_THRESHOLD: Final[str] = 'confidence_threshold'
    USE_FAST_LANE: Final[str] = 'use_fast_lane'
    USE_SMART_LANE: Final[str] = 'use_smart_lane'
    
    # Response fields (GET response)
    CONFIG_ID: Final[str] = 'config_id'
    IS_ACTIVE: Final[str] = 'is_active'
    CREATED_AT: Final[str] = 'created_at'
    UPDATED_AT: Final[str] = 'updated_at'


class BotControlFields:
    """
    Field names for Bot Control API requests and responses.
    
    Used in api/bot_control_api.py for bot lifecycle management.
    """
    # Start bot request fields
    RUNTIME_MINUTES: Final[str] = 'runtime_minutes'
    CONFIG: Final[str] = 'config'
    SESSION_NAME: Final[str] = 'session_name'
    
    # Bot status response fields
    SESSION_ID: Final[str] = 'session_id'
    TASK_ID: Final[str] = 'task_id'
    STATUS: Final[str] = 'status'
    MESSAGE: Final[str] = 'message'
    ACCOUNT_BALANCE: Final[str] = 'account_balance'
    STARTED_AT: Final[str] = 'started_at'
    STOPPED_AT: Final[str] = 'stopped_at'
    
    # Stop bot request fields
    REASON: Final[str] = 'reason'


class SessionMetadataFields:
    """
    Field names for PaperTradingSession.metadata JSON field.
    
    Stores runtime configuration and state information.
    """
    CONFIG_SNAPSHOT: Final[str] = 'config_snapshot'
    STARTING_BALANCE_USD: Final[str] = 'starting_balance_usd'
    SESSION_NAME: Final[str] = 'session_name'
    CELERY_TASK_ID: Final[str] = 'celery_task_id'
    STARTED_AT: Final[str] = 'started_at'
    
    # Configuration parameters passed to bot
    INTEL_LEVEL: Final[str] = 'intel_level'
    TRADING_MODE: Final[str] = 'trading_mode'
    MAX_POSITION_SIZE_PERCENT: Final[str] = 'max_position_size_percent'
    STOP_LOSS_PERCENT: Final[str] = 'stop_loss_percent'
    TAKE_PROFIT_PERCENT: Final[str] = 'take_profit_percent'
    MAX_HOLD_HOURS: Final[str] = 'max_hold_hours'
    MAX_DAILY_TRADES: Final[str] = 'max_daily_trades'
    CONFIDENCE_THRESHOLD: Final[str] = 'confidence_threshold'


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_decision_type(decision_type: str) -> bool:
    """
    Validate if decision type is valid.
    
    Args:
        decision_type: Decision type string
        
    Returns:
        True if valid, False otherwise
    """
    return decision_type in DecisionType.ALL


def validate_confidence_level(confidence_level: str) -> bool:
    """
    Validate if confidence level is valid.
    
    Args:
        confidence_level: Confidence level string
        
    Returns:
        True if valid, False otherwise
    """
    return confidence_level in ConfidenceLevel.ALL


def validate_trading_mode(trading_mode: str) -> bool:
    """
    Validate if trading mode is valid.
    
    Args:
        trading_mode: Trading mode string
        
    Returns:
        True if valid, False otherwise
    """
    return trading_mode in TradingMode.ALL


def validate_lane_type(lane_type: str) -> bool:
    """
    Validate if lane type is valid.
    
    Args:
        lane_type: Lane type string
        
    Returns:
        True if valid, False otherwise
    """
    return lane_type in LaneType.ALL


def validate_session_status(status: str) -> bool:
    """
    Validate if session status is valid.
    
    Args:
        status: Session status string
        
    Returns:
        True if valid, False otherwise
    """
    return status in SessionStatus.ALL


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_confidence_level_from_percent(percent: float) -> str:
    """
    Convert confidence percentage to level string (convenience function).
    
    Args:
        percent: Confidence percentage (0-100)
        
    Returns:
        Confidence level string
    """
    return ConfidenceLevel.from_percentage(Decimal(str(percent)))


def get_intel_level_from_trading_mode(trading_mode: str) -> int:
    """
    Map trading mode to intel level for bot initialization.
    
    Args:
        trading_mode: Trading mode (CONSERVATIVE, MODERATE, AGGRESSIVE, CUSTOM)
        
    Returns:
        Intel level (1-10)
    """
    mode_to_intel = {
        TradingMode.CONSERVATIVE: 3,  # Low risk, careful analysis
        TradingMode.MODERATE: 5,      # Balanced approach
        TradingMode.AGGRESSIVE: 8,    # High risk, faster execution
        TradingMode.CUSTOM: 5,        # Default to moderate for custom
    }
    return mode_to_intel.get(trading_mode, 5)  # Default to 5 if unknown


# =============================================================================
# PHASE 2: MULTI-DEX PRICE COMPARISON CONSTANTS
# =============================================================================

class DEXNames:
    """Supported DEX names for multi-DEX price comparison."""
    UNISWAP_V3: Final[str] = 'uniswap_v3'
    UNISWAP_V2: Final[str] = 'uniswap_v2'
    SUSHISWAP: Final[str] = 'sushiswap'
    CURVE: Final[str] = 'curve'
    
    ALL: Final[tuple] = (UNISWAP_V3, UNISWAP_V2, SUSHISWAP, CURVE)
    
    # Primary DEXs for Phase 2 launch
    PRIMARY: Final[tuple] = (UNISWAP_V3, SUSHISWAP, CURVE)


class ArbitrageFields:
    """Field names for arbitrage detection and execution."""
    # Opportunity identification
    BUY_DEX: Final[str] = 'buy_dex'
    SELL_DEX: Final[str] = 'sell_dex'
    BUY_PRICE: Final[str] = 'buy_price'
    SELL_PRICE: Final[str] = 'sell_price'
    PRICE_SPREAD_PERCENT: Final[str] = 'price_spread_percent'
    
    # Profitability calculation
    GROSS_PROFIT_USD: Final[str] = 'gross_profit_usd'
    GAS_COST_USD: Final[str] = 'gas_cost_usd'
    NET_PROFIT_USD: Final[str] = 'net_profit_usd'
    PROFIT_MARGIN_PERCENT: Final[str] = 'profit_margin_percent'
    
    # Execution parameters
    IS_PROFITABLE: Final[str] = 'is_profitable'
    EXECUTION_TIME_MS: Final[str] = 'execution_time_ms'
    MIN_PROFIT_THRESHOLD: Final[str] = 'min_profit_threshold'
    
    # Risk assessment
    SLIPPAGE_RISK: Final[str] = 'slippage_risk'
    LIQUIDITY_RISK: Final[str] = 'liquidity_risk'
    TIMING_RISK: Final[str] = 'timing_risk'


class DEXPriceFields:
    """Field names for DEX price comparison results."""
    DEX_NAME: Final[str] = 'dex_name'
    TOKEN_PRICE: Final[str] = 'token_price'
    LIQUIDITY_USD: Final[str] = 'liquidity_usd'
    QUOTE_TIMESTAMP: Final[str] = 'quote_timestamp'
    QUERY_SUCCESS: Final[str] = 'query_success'
    ERROR_MESSAGE: Final[str] = 'error_message'
    RESPONSE_TIME_MS: Final[str] = 'response_time_ms'
    
    # Best price selection
    BEST_PRICE: Final[str] = 'best_price'
    BEST_DEX: Final[str] = 'best_dex'
    PRICE_ADVANTAGE_PERCENT: Final[str] = 'price_advantage_percent'


class DEXIntegrationStatus:
    """Status indicators for DEX integration health."""
    OPERATIONAL: Final[str] = 'operational'
    DEGRADED: Final[str] = 'degraded'
    UNAVAILABLE: Final[str] = 'unavailable'
    TIMEOUT: Final[str] = 'timeout'
    ERROR: Final[str] = 'error'
    
    ALL: Final[tuple] = (OPERATIONAL, DEGRADED, UNAVAILABLE, TIMEOUT, ERROR)


# =============================================================================
# DEX-SPECIFIC CONSTANTS
# =============================================================================

class UniswapV3Constants:
    """Uniswap V3 specific constants."""
    FEE_TIER_LOW: Final[int] = 500      # 0.05%
    FEE_TIER_MEDIUM: Final[int] = 3000   # 0.30%
    FEE_TIER_HIGH: Final[int] = 10000    # 1.00%
    
    DEFAULT_FEE_TIER: Final[int] = FEE_TIER_MEDIUM
    ALL_FEE_TIERS: Final[tuple] = (FEE_TIER_LOW, FEE_TIER_MEDIUM, FEE_TIER_HIGH)


class SushiSwapConstants:
    """SushiSwap specific constants."""
    DEFAULT_FEE: Final[int] = 3000  # 0.30%
    ROUTER_VERSION: Final[str] = 'v2'


class CurveConstants:
    """Curve Finance specific constants."""
    STABLE_SWAP_TYPE: Final[str] = 'stable'
    CRYPTO_SWAP_TYPE: Final[str] = 'crypto'
    MIN_LIQUIDITY_USD: Final[int] = 50000  # $50K minimum pool size


# =============================================================================
# VALIDATION FUNCTIONS FOR DEX OPERATIONS
# =============================================================================

def validate_dex_name(dex_name: str) -> bool:
    """
    Validate if DEX name is supported.
    
    Args:
        dex_name: DEX name to validate
        
    Returns:
        True if valid, False otherwise
    """
    return dex_name in DEXNames.ALL


def validate_arbitrage_opportunity(arb_data: dict) -> bool:
    """
    Validate arbitrage opportunity data structure.
    
    Args:
        arb_data: Arbitrage data dictionary
        
    Returns:
        True if valid structure, False otherwise
    """
    required_fields = [
        ArbitrageFields.BUY_DEX,
        ArbitrageFields.SELL_DEX,
        ArbitrageFields.BUY_PRICE,
        ArbitrageFields.SELL_PRICE,
        ArbitrageFields.NET_PROFIT_USD
    ]
    
    return all(field in arb_data for field in required_fields)


# =============================================================================
# DEX HELPER FUNCTIONS
# =============================================================================

def get_dex_display_name(dex_name: str) -> str:
    """
    Get human-readable display name for DEX.
    
    Args:
        dex_name: Internal DEX name
        
    Returns:
        Display name for UI
    """
    display_names = {
        DEXNames.UNISWAP_V3: 'Uniswap V3',
        DEXNames.UNISWAP_V2: 'Uniswap V2',
        DEXNames.SUSHISWAP: 'SushiSwap',
        DEXNames.CURVE: 'Curve Finance'
    }
    
    return display_names.get(dex_name, dex_name.upper())


# =============================================================================
# ORDER TYPES (Phase 7A - Advanced Order Types)
# =============================================================================

class OrderType:
    """
    Advanced order types for Phase 7A.
    
    These define the different types of orders users can place.
    """
    # Limit orders - execute at specific price or better
    LIMIT_BUY: Final[str] = 'LIMIT_BUY'      # Buy when price drops to limit or below
    LIMIT_SELL: Final[str] = 'LIMIT_SELL'    # Sell when price rises to limit or above
    
    # Stop-limit orders - trigger at stop, execute at limit
    STOP_LIMIT_BUY: Final[str] = 'STOP_LIMIT_BUY'    # Buy when price rises to stop, execute at limit
    STOP_LIMIT_SELL: Final[str] = 'STOP_LIMIT_SELL'  # Sell when price drops to stop, execute at limit
    
    # Trailing stop - dynamic stop that follows price
    TRAILING_STOP: Final[str] = 'TRAILING_STOP'      # Stop loss that trails price upward
    
    # All valid order types
    ALL: Final[tuple] = (
        LIMIT_BUY, LIMIT_SELL,
        STOP_LIMIT_BUY, STOP_LIMIT_SELL,
        TRAILING_STOP
    )
    
    # Order types that buy
    BUY_ORDERS: Final[tuple] = (LIMIT_BUY, STOP_LIMIT_BUY)
    
    # Order types that sell
    SELL_ORDERS: Final[tuple] = (LIMIT_SELL, STOP_LIMIT_SELL, TRAILING_STOP)
    
    # Limit-based orders
    LIMIT_ORDERS: Final[tuple] = (LIMIT_BUY, LIMIT_SELL)
    
    # Stop-limit orders
    STOP_LIMIT_ORDERS: Final[tuple] = (STOP_LIMIT_BUY, STOP_LIMIT_SELL)


# =============================================================================
# ORDER STATUS (Phase 7A)
# =============================================================================

class OrderStatus:
    """
    Order execution status for advanced order types.
    
    Tracks the lifecycle of an order from placement to completion.
    """
    # Active states
    PENDING: Final[str] = 'PENDING'                    # Order placed, waiting for trigger
    TRIGGERED: Final[str] = 'TRIGGERED'                # Stop price hit, ready to execute
    PARTIALLY_FILLED: Final[str] = 'PARTIALLY_FILLED'  # Some quantity executed
    
    # Terminal states
    FILLED: Final[str] = 'FILLED'          # Order fully executed
    CANCELLED: Final[str] = 'CANCELLED'    # User cancelled order
    EXPIRED: Final[str] = 'EXPIRED'        # Order expired (time-based)
    FAILED: Final[str] = 'FAILED'          # Execution failed
    
    # All valid statuses
    ALL: Final[tuple] = (
        PENDING, TRIGGERED, PARTIALLY_FILLED,
        FILLED, CANCELLED, EXPIRED, FAILED
    )
    
    # Active statuses (order still in play)
    ACTIVE: Final[tuple] = (PENDING, TRIGGERED, PARTIALLY_FILLED)
    
    # Terminal statuses (order complete)
    TERMINAL: Final[tuple] = (FILLED, CANCELLED, EXPIRED, FAILED)


# =============================================================================
# MODEL FIELD NAMES - Orders (Phase 7A)
# =============================================================================

class OrderFields:
    """
    Field names for order models (Phase 7A).
    
    These apply to PaperLimitOrder, PaperStopLimitOrder, and PaperTrailingStopOrder.
    """
    # Identity
    ORDER_ID: Final[str] = 'order_id'
    ACCOUNT: Final[str] = 'account'
    ORDER_TYPE: Final[str] = 'order_type'
    
    # Token details
    TOKEN_ADDRESS: Final[str] = 'token_address'
    TOKEN_SYMBOL: Final[str] = 'token_symbol'
    TOKEN_NAME: Final[str] = 'token_name'
    
    # Order parameters
    AMOUNT_USD: Final[str] = 'amount_usd'
    AMOUNT_TOKEN: Final[str] = 'amount_token'
    
    # Price parameters
    TRIGGER_PRICE: Final[str] = 'trigger_price'        # For limit/stop-limit orders
    LIMIT_PRICE: Final[str] = 'limit_price'            # For stop-limit orders
    STOP_PRICE: Final[str] = 'stop_price'              # For stop-limit orders
    
    # Trailing stop parameters
    TRAIL_PERCENT: Final[str] = 'trail_percent'        # For trailing stops
    TRAIL_AMOUNT: Final[str] = 'trail_amount'          # Alternative: fixed trail amount
    HIGHEST_PRICE: Final[str] = 'highest_price'        # Tracks highest price seen
    CURRENT_STOP_PRICE: Final[str] = 'current_stop_price'  # Current trailing stop
    
    # Execution
    STATUS: Final[str] = 'status'
    FILLED_AMOUNT_USD: Final[str] = 'filled_amount_usd'
    FILLED_AMOUNT_TOKEN: Final[str] = 'filled_amount_token'
    AVERAGE_FILL_PRICE: Final[str] = 'average_fill_price'
    
    # Timing
    CREATED_AT: Final[str] = 'created_at'
    EXPIRES_AT: Final[str] = 'expires_at'
    TRIGGERED_AT: Final[str] = 'triggered_at'
    FILLED_AT: Final[str] = 'filled_at'
    CANCELLED_AT: Final[str] = 'cancelled_at'
    
    # Metadata
    NOTES: Final[str] = 'notes'
    ERROR_MESSAGE: Final[str] = 'error_message'
    RELATED_TRADE: Final[str] = 'related_trade'        # Link to executed trade


# =============================================================================
# VALIDATION FUNCTIONS - Phase 7A Orders
# =============================================================================

def validate_order_type(order_type: str) -> bool:
    """
    Validate if order type is valid.
    
    Args:
        order_type: Order type string
        
    Returns:
        True if valid, False otherwise
    """
    return order_type in OrderType.ALL


def validate_order_status(status: str) -> bool:
    """
    Validate if order status is valid.
    
    Args:
        status: Order status string
        
    Returns:
        True if valid, False otherwise
    """
    return status in OrderStatus.ALL


def is_order_active(status: str) -> bool:
    """
    Check if order status indicates an active order.
    
    Args:
        status: Order status string
        
    Returns:
        True if order is still active, False if terminal
    """
    return status in OrderStatus.ACTIVE


def is_order_terminal(status: str) -> bool:
    """
    Check if order status indicates a completed order.
    
    Args:
        status: Order status string
        
    Returns:
        True if order is in terminal state, False if still active
    """
    return status in OrderStatus.TERMINAL

# =============================================================================
# STRATEGY TYPES - Phase 7B
# =============================================================================

class StrategyType:
    """
    Trading strategy types for automated execution.
    
    Phase 7B: Advanced trading strategies with backtesting capabilities.
    """
    SPOT: Final[str] = 'SPOT'  # Standard spot buy (existing behavior)
    DCA: Final[str] = 'DCA'  # Dollar Cost Averaging
    GRID: Final[str] = 'GRID'  # Grid Trading Bot
    TWAP: Final[str] = 'TWAP'  # Time-Weighted Average Price
    VWAP: Final[str] = 'VWAP'  # Volume-Weighted Average Price
    CUSTOM: Final[str] = 'CUSTOM'  # User-defined custom strategies
    
    # All valid strategy types
    ALL: Final[tuple] = (SPOT, DCA, GRID, TWAP, VWAP, CUSTOM)
    
    # Automated strategies (bot-selected)
    AUTOMATED: Final[tuple] = (DCA, GRID, TWAP, VWAP)


# =============================================================================
# STRATEGY STATUS - Phase 7B
# =============================================================================

class StrategyStatus:
    """Strategy execution status for StrategyRun model."""
    PENDING: Final[str] = 'PENDING'  # Created but not started
    RUNNING: Final[str] = 'RUNNING'  # Currently executing
    PAUSED: Final[str] = 'PAUSED'  # Temporarily paused
    COMPLETED: Final[str] = 'COMPLETED'  # Finished successfully
    CANCELLED: Final[str] = 'CANCELLED'  # Manually cancelled
    FAILED: Final[str] = 'FAILED'  # Failed with error
    
    # All valid statuses
    ALL: Final[tuple] = (PENDING, RUNNING, PAUSED, COMPLETED, CANCELLED, FAILED)
    
    # Active statuses (strategy is in progress)
    ACTIVE: Final[tuple] = (RUNNING,)
    
    # Terminal statuses (strategy has finished)
    TERMINAL: Final[tuple] = (COMPLETED, CANCELLED, FAILED)


# =============================================================================
# MODEL FIELD NAMES - StrategyRun (Phase 7B)
# =============================================================================

class StrategyRunFields:
    """Field names for StrategyRun model."""
    # Identity
    STRATEGY_ID: Final[str] = 'strategy_id'
    ACCOUNT: Final[str] = 'account'
    STRATEGY_TYPE: Final[str] = 'strategy_type'
    
    # Configuration
    CONFIG: Final[str] = 'config'
    
    # Execution status
    STATUS: Final[str] = 'status'
    PROGRESS_PERCENT: Final[str] = 'progress_percent'
    CURRENT_STEP: Final[str] = 'current_step'
    
    # Performance tracking
    TOTAL_ORDERS: Final[str] = 'total_orders'
    COMPLETED_ORDERS: Final[str] = 'completed_orders'
    FAILED_ORDERS: Final[str] = 'failed_orders'
    TOTAL_INVESTED: Final[str] = 'total_invested'
    AVERAGE_ENTRY: Final[str] = 'average_entry'
    CURRENT_PNL: Final[str] = 'current_pnl'
    
    # Timing
    CREATED_AT: Final[str] = 'created_at'
    STARTED_AT: Final[str] = 'started_at'
    PAUSED_AT: Final[str] = 'paused_at'
    COMPLETED_AT: Final[str] = 'completed_at'
    CANCELLED_AT: Final[str] = 'cancelled_at'
    
    # Metadata
    NOTES: Final[str] = 'notes'
    ERROR_MESSAGE: Final[str] = 'error_message'


# =============================================================================
# MODEL FIELD NAMES - StrategyOrder (Phase 7B)
# =============================================================================

class StrategyOrderFields:
    """Field names for StrategyOrder linking model."""
    ID: Final[str] = 'id'
    STRATEGY_RUN: Final[str] = 'strategy_run'
    ORDER: Final[str] = 'order'
    ORDER_SEQUENCE: Final[str] = 'order_sequence'
    CREATED_AT: Final[str] = 'created_at'


# =============================================================================
# VALIDATION FUNCTIONS - Phase 7B Strategies
# =============================================================================

def validate_strategy_type(strategy_type: str) -> bool:
    """
    Validate if strategy type is valid.
    
    Args:
        strategy_type: Strategy type string
        
    Returns:
        True if valid, False otherwise
    """
    return strategy_type in StrategyType.ALL


def validate_strategy_status(status: str) -> bool:
    """
    Validate if strategy status is valid.
    
    Args:
        status: Strategy status string
        
    Returns:
        True if valid, False otherwise
    """
    return status in StrategyStatus.ALL


def is_strategy_active(status: str) -> bool:
    """
    Check if strategy status indicates an active strategy.
    
    Args:
        status: Strategy status string
        
    Returns:
        True if strategy is still running, False if not
    """
    return status in StrategyStatus.ACTIVE



# =============================================================================
# MARKET TREND CLASSIFICATIONS - Phase 7B
# =============================================================================

class MarketTrend:
    """
    Market trend classifications for strategy selection.
    
    Used by bot to determine which strategy is optimal based on
    current market conditions and price action.
    """
    STRONG_UPTREND: Final[str] = 'strong_uptrend'  # Clear bullish momentum
    UPTREND: Final[str] = 'uptrend'  # Moderate upward movement
    SIDEWAYS: Final[str] = 'sideways'  # Ranging, no clear direction
    RANGE_BOUND: Final[str] = 'range_bound'  # Trading in defined range
    DOWNTREND: Final[str] = 'downtrend'  # Moderate downward movement
    STRONG_DOWNTREND: Final[str] = 'strong_downtrend'  # Clear bearish momentum
    
    # All valid trend types
    ALL: Final[tuple] = (
        STRONG_UPTREND,
        UPTREND,
        SIDEWAYS,
        RANGE_BOUND,
        DOWNTREND,
        STRONG_DOWNTREND
    )
    
    # Bullish trends (DCA favorable)
    BULLISH: Final[tuple] = (STRONG_UPTREND, UPTREND)
    
    # Neutral trends (Grid favorable)
    NEUTRAL: Final[tuple] = (SIDEWAYS, RANGE_BOUND)
    
    # Bearish trends (caution)
    BEARISH: Final[tuple] = (DOWNTREND, STRONG_DOWNTREND)


# =============================================================================
# STRATEGY SELECTION THRESHOLDS - Phase 7B
# =============================================================================

class StrategySelectionThresholds:
    """
    Decision thresholds for bot's strategy selection logic.
    
    These constants define when the bot should choose each strategy type
    based on market conditions (volatility, trend, liquidity, confidence).
    
    Usage in market_analyzer.py's _select_strategy() method.
    """
    
    # =========================================================================
    # GRID STRATEGY THRESHOLDS
    # =========================================================================
    
    # Grid Trading requires:
    # - High volatility (price oscillates frequently)
    # - Range-bound or sideways market (not trending)
    # - Sufficient liquidity for multiple orders
    
    GRID_MIN_VOLATILITY: Final[Decimal] = Decimal('0.05')  # 5% volatility minimum
    GRID_OPTIMAL_VOLATILITY: Final[Decimal] = Decimal('0.08')  # 8% is ideal
    GRID_MIN_LIQUIDITY_USD: Final[Decimal] = Decimal('100000')  # $100k minimum liquidity
    GRID_MIN_CONFIDENCE: Final[Decimal] = Decimal('50.0')  # 50% confidence threshold
    
    # =========================================================================
    # DCA STRATEGY THRESHOLDS
    # =========================================================================
    
    # DCA (Dollar Cost Averaging) requires:
    # - Strong trending market (uptrend preferred)
    # - High confidence in direction
    # - Position size large enough to split meaningfully
    
    DCA_MIN_CONFIDENCE: Final[Decimal] = Decimal('70.0')  # 70% confidence minimum
    DCA_MIN_POSITION_SIZE_USD: Final[Decimal] = Decimal('100')  # $100 minimum to DCA
    DCA_OPTIMAL_POSITION_SIZE_USD: Final[Decimal] = Decimal('500')  # $500+ ideal for DCA
    
    # =========================================================================
    # SPOT BUY THRESHOLDS (Fallback)
    # =========================================================================
    
    # Spot Buy is the default/fallback strategy:
    # - Quick execution needed
    # - Clear trading signal
    # - Good liquidity
    # - Lower bar than specialized strategies
    
    SPOT_MIN_CONFIDENCE: Final[Decimal] = Decimal('40.0')  # Lower bar for spot buys
    SPOT_MIN_LIQUIDITY_USD: Final[Decimal] = Decimal('50000')  # $50k minimum liquidity
    
    # =========================================================================
    # GENERAL THRESHOLDS
    # =========================================================================
    
    # Minimum confidence for ANY strategy
    ABSOLUTE_MIN_CONFIDENCE: Final[Decimal] = Decimal('40.0')
    
    # Minimum liquidity for ANY strategy
    ABSOLUTE_MIN_LIQUIDITY_USD: Final[Decimal] = Decimal('50000')
    

def is_strategy_terminal(status: str) -> bool:
    """
    Check if strategy status indicates a completed strategy.
    
    Args:
        status: Strategy status string
        
    Returns:
        True if strategy is in terminal state, False if still active
    """
    return status in StrategyStatus.TERMINAL