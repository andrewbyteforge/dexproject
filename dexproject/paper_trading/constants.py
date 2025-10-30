"""
Paper Trading Constants - Enhanced with API Field Names

This module contains all constant values used throughout the paper trading system.
These prevent typos, enable IDE autocomplete, and serve as single source of truth.

ENHANCED: Added API request/response field names and configuration constants

Location: paper_trading/constants.py

Usage:
    from paper_trading.constants import (
        DecisionType, ConfidenceLevel, ThoughtLogFields,
        ConfigAPIFields, BotControlFields
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
    
    # All valid decision types
    ALL: Final[tuple] = (BUY, SELL, HOLD, SKIP, STOP_LOSS, TAKE_PROFIT)
    
    # Actionable decisions (require execution)
    ACTIONABLE: Final[tuple] = (BUY, SELL, STOP_LOSS, TAKE_PROFIT)
    
    # Non-actionable decisions
    NON_ACTIONABLE: Final[tuple] = (HOLD, SKIP)


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
    STOP_LOSS_PERCENT: Final[str] = 'stop_loss_percent'
    TAKE_PROFIT_PERCENT: Final[str] = 'take_profit_percent'
    MAX_DAILY_TRADES: Final[str] = 'max_daily_trades'
    MAX_CONCURRENT_POSITIONS: Final[str] = 'max_concurrent_positions'
    MIN_LIQUIDITY_USD: Final[str] = 'min_liquidity_usd'
    MAX_SLIPPAGE_PERCENT: Final[str] = 'max_slippage_percent'
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