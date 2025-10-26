"""
Paper Trading Constants - String Literals and Field Names

This module contains all constant values used throughout the paper trading system.
These prevent typos, enable IDE autocomplete, and serve as single source of truth.

Location: paper_trading/constants.py

Usage:
    from paper_trading.constants import DecisionType, ConfidenceLevel, ThoughtLogFields
    
    # Instead of:
    decision = "BUY"  # ❌ Typo-prone
    
    # Use:
    decision = DecisionType.BUY  # ✅ Type-safe, autocomplete
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
    """Trading execution modes."""
    BALANCED: Final[str] = 'BALANCED'
    AGGRESSIVE: Final[str] = 'AGGRESSIVE'
    CONSERVATIVE: Final[str] = 'CONSERVATIVE'
    SCALPER: Final[str] = 'SCALPER'
    SWING: Final[str] = 'SWING'
    
    ALL: Final[tuple] = (BALANCED, AGGRESSIVE, CONSERVATIVE, SCALPER, SWING)


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
    RUNNING: Final[str] = 'RUNNING'
    PAUSED: Final[str] = 'PAUSED'
    STOPPED: Final[str] = 'STOPPED'
    COMPLETED: Final[str] = 'COMPLETED'
    ERROR: Final[str] = 'ERROR'
    
    ALL: Final[tuple] = (RUNNING, PAUSED, STOPPED, COMPLETED, ERROR)


# =============================================================================
# MODEL FIELD NAMES - PaperAIThoughtLog
# =============================================================================

class ThoughtLogFields:
    """
    Field names for PaperAIThoughtLog model.
    
    Use these instead of string literals to prevent field name mismatches.
    
    Example:
        # Instead of:
        PaperAIThoughtLog.objects.create(
            confidence_percent=90,  # ❌ Might typo as "confidence_percentage"
            risk_score=50
        )
        
        # Use:
        PaperAIThoughtLog.objects.create(
            **{
                ThoughtLogFields.CONFIDENCE_PERCENT: 90,  # ✅ IDE autocomplete
                ThoughtLogFields.RISK_SCORE: 50
            }
        )
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
    NAME: Final[str] = 'name'
    TRADING_MODE: Final[str] = 'trading_mode'
    MAX_POSITION_SIZE_PERCENT: Final[str] = 'max_position_size_percent'
    STOP_LOSS_PERCENT: Final[str] = 'stop_loss_percent'
    TAKE_PROFIT_PERCENT: Final[str] = 'take_profit_percent'
    IS_ACTIVE: Final[str] = 'is_active'


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