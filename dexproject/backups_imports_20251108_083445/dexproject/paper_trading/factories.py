"""
Paper Trading Factories - Type-Safe Model Creation

This module provides factory functions for creating model instances with type safety.
These prevent field name mismatch errors and ensure consistent data validation.

Location: paper_trading/factories.py

Usage:
    from paper_trading.factories import create_thought_log, create_paper_trade

    # Instead of:
    thought = PaperAIThoughtLog.objects.create(
        confidence_percent=90,  # Might typo field name
        ...
    )

    # Use:
    thought = create_thought_log(
        account=account,
        decision_type='BUY',
        confidence_percent=90,
        ...
    )
"""
import math  # Add to imports at top
from decimal import Decimal
from typing import Optional, Dict, Any, List
import logging

from django.utils import timezone

from paper_trading.constants import (
    DecisionType,
    ConfidenceLevel,
    TradeFields,
    LaneType,
    TradeStatus,
    validate_decision_type,
)

logger = logging.getLogger(__name__)

# =============================================================================
# JSON SANITIZER
# =============================================================================

def sanitize_for_json(data: Any) -> Any:
    """
    Sanitize data for JSON serialization by converting NaN, Infinity, and None.
    
    Args:
        data: Any data structure (dict, list, or primitive)
        
    Returns:
        JSON-safe version of the data
    """
    if isinstance(data, dict):
        return {k: sanitize_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_for_json(item) for item in data]
    elif isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            return None  # Convert NaN/Infinity to None
        return data
    elif data is None:
        return None
    else:
        return data



# =============================================================================
# THOUGHTLOG FACTORY
# =============================================================================

def create_thought_log(
    account,
    decision_type: str,
    token_address: str,
    token_symbol: str,
    confidence_percent: Decimal,
    risk_score: Decimal,
    opportunity_score: Decimal,
    primary_reasoning: str,
    *,
    paper_trade=None,
    key_factors: Optional[List[str]] = None,
    positive_signals: Optional[List[str]] = None,
    negative_signals: Optional[List[str]] = None,
    market_data: Optional[Dict[str, Any]] = None,
    strategy_name: str = '',
    lane_used: str = LaneType.FAST,
    analysis_time_ms: int = 0
):
    """
    Create a PaperAIThoughtLog with validated fields.

    This factory prevents field name mismatches and ensures proper data types.
    All field names match the actual PaperAIThoughtLog model definition.

    Args:
        account: PaperTradingAccount instance
        decision_type: Decision type (use DecisionType constants)
        token_address: Token contract address
        token_symbol: Token symbol
        confidence_percent: Confidence as Decimal (0-100)
        risk_score: Risk score as Decimal (0-100)
        opportunity_score: Opportunity score as Decimal (0-100)
        primary_reasoning: Primary reasoning string (will be truncated to 500 chars)
        paper_trade: Optional PaperTrade instance
        key_factors: List of key factors (default: empty list)
        positive_signals: List of positive signals (default: empty list)
        negative_signals: List of negative signals (default: empty list)
        market_data: Market data dictionary (default: empty dict)
        strategy_name: Strategy name (default: empty string)
        lane_used: Lane type (default: FAST)
        analysis_time_ms: Analysis time in milliseconds (default: 0)

    Returns:
        PaperAIThoughtLog instance

    Raises:
        ValueError: If decision_type is invalid
        ImportError: If PaperAIThoughtLog model cannot be imported

    Note:
        This function was updated to match the actual PaperAIThoughtLog model fields.
        Key changes:
        - Uses 'primary_reasoning' (not 'reasoning')
        - Uses separate 'risk_score' and 'opportunity_score' fields
        - Converts 'confidence_percent' to 'confidence_level' string
        - Removed 'risk_assessment' field (doesn't exist in model)
    """
    try:
        from paper_trading.models.intelligence import PaperAIThoughtLog
    except ImportError as e:
        logger.error(f"Failed to import PaperAIThoughtLog: {e}")
        raise ImportError(
            "Cannot create thought log: PaperAIThoughtLog model not available"
        ) from e

    # Validate decision type
    if not validate_decision_type(decision_type):
        raise ValueError(
            f"Invalid decision type: {decision_type}. "
            f"Must be one of: {DecisionType.ALL}"
        )

    # Set defaults for optional parameters
    if key_factors is None:
        key_factors = []
    if positive_signals is None:
        positive_signals = []
    if negative_signals is None:
        negative_signals = []
    if market_data is None:
        market_data = {}

    # Truncate primary_reasoning to avoid text field overflow
    reasoning_text = primary_reasoning[:500]

    # Build risk assessment summary text for market_data reference
    risk_assessment_text = (
        f"Risk Score: {risk_score}/100\n"
        f"Opportunity Score: {opportunity_score}/100\n"
        f"Confidence: {confidence_percent}%"
    )

    # Store risk assessment summary in market_data for reference
    # (The model doesn't have a 'risk_assessment' field, so we store it here)
    market_data['risk_assessment_summary'] = risk_assessment_text
    # Add risk and opportunity scores to market_data since they're not separate fields
    market_data['risk_score'] = float(risk_score)
    market_data['opportunity_score'] = float(opportunity_score)

    market_data = sanitize_for_json(market_data)

    # Convert confidence percentage to confidence level string
    # Converts 75.0 -> 'HIGH', 90.0 -> 'VERY_HIGH', etc.
    confidence_level_str = ConfidenceLevel.from_percentage(confidence_percent)

    # Build kwargs using ACTUAL model field names from PaperAIThoughtLog
    # Every field here matches exactly what's defined in models/intelligence.py
    kwargs = {
        'account': account,  # ForeignKey
        'paper_trade': paper_trade,  # ForeignKey (nullable)
        'decision_type': decision_type,  # CharField with choices
        'token_address': token_address,  # CharField(max_length=42)
        'token_symbol': token_symbol,  # CharField(max_length=20)
        'confidence_level': confidence_level_str,  # CharField: 'VERY_HIGH', 'HIGH', 'MEDIUM', 'LOW', 'VERY_LOW'
        'confidence_percent': confidence_percent,  # DecimalField: 0-100
        'risk_score': risk_score,  # DecimalField: 0-100
        'opportunity_score': opportunity_score,  # DecimalField: 0-100
        'primary_reasoning': reasoning_text,  # TextField: main reasoning text
        'key_factors': key_factors,  # JSONField: list of strings
        'positive_signals': positive_signals,  # JSONField: list of strings
        'negative_signals': negative_signals,  # JSONField: list of strings
        'market_data': market_data,  # JSONField: dict
        'strategy_name': strategy_name,  # CharField(max_length=100)
        'lane_used': lane_used,  # CharField: 'FAST' or 'SMART'
        'analysis_time_ms': analysis_time_ms,  # IntegerField: milliseconds
    }

    try:
        thought_log = PaperAIThoughtLog.objects.create(**kwargs)
        logger.debug(
            f"Created thought log: {decision_type} for {token_symbol} "
            f"with confidence {confidence_percent}% (level: {confidence_level_str})"
        )
        return thought_log
    except Exception as e:
        logger.error(
            f"Failed to create thought log: {e}",
            exc_info=True,
            extra={
                'decision_type': decision_type,
                'token_symbol': token_symbol,
                'confidence_percent': float(confidence_percent),
                'confidence_level': confidence_level_str,
                'risk_score': float(risk_score),
                'opportunity_score': float(opportunity_score),
            }
        )
        raise


# =============================================================================
# PAPER TRADE FACTORY
# =============================================================================

def create_paper_trade(
    account,
    session,
    decision_type: str,
    token_address: str,
    token_symbol: str,
    amount_token: Decimal,
    amount_usd: Decimal,
    entry_price: Decimal,
    *,
    exit_price: Optional[Decimal] = None,
    status: str = TradeStatus.PENDING,
    executed_at=None,
    profit_loss_usd: Optional[Decimal] = None,
    profit_loss_percent: Optional[Decimal] = None,
    gas_cost_usd: Decimal = Decimal('0.00'),
    slippage_percent: Decimal = Decimal('0.5'),
    lane_used: str = LaneType.FAST,
    intel_level: int = 3,
    confidence_score: Decimal = Decimal('75.0'),
    risk_assessment: Optional[Dict[str, Any]] = None
):
    """
    Create a PaperTrade with validated fields.

    Args:
        account: PaperTradingAccount instance
        session: PaperTradingSession instance
        decision_type: Decision type (use DecisionType constants)
        token_address: Token contract address
        token_symbol: Token symbol
        amount_token: Amount in tokens
        amount_usd: Amount in USD
        entry_price: Entry price
        exit_price: Exit price (optional)
        status: Trade status (default: PENDING)
        executed_at: Execution timestamp (default: now if EXECUTED)
        profit_loss_usd: P&L in USD (optional)
        profit_loss_percent: P&L percentage (optional)
        gas_cost_usd: Gas cost in USD (default: 0)
        slippage_percent: Slippage percentage (default: 0.5)
        lane_used: Lane type (default: FAST)
        intel_level: Intelligence level (default: 3)
        confidence_score: Confidence score (default: 75.0)
        risk_assessment: Risk assessment data (optional)

    Returns:
        PaperTrade instance

    Raises:
        ValueError: If decision_type is invalid
        ImportError: If PaperTrade model cannot be imported
    """
    try:
        from paper_trading.models.trades import PaperTrade  # type: ignore[import-not-found]
    except ImportError as e:
        logger.error(f"Failed to import PaperTrade: {e}")
        raise ImportError(
            "Cannot create paper trade: PaperTrade model not available"
        ) from e

    # Validate decision type
    if not validate_decision_type(decision_type):
        raise ValueError(
            f"Invalid decision type: {decision_type}. "
            f"Must be one of: {DecisionType.ALL}"
        )

    # Set executed_at if status is EXECUTED and not provided
    if status == TradeStatus.EXECUTED and executed_at is None:
        executed_at = timezone.now()

    # Set risk_assessment default
    if risk_assessment is None:
        risk_assessment = {}

    # Build kwargs using field name constants
    kwargs = {
        TradeFields.ACCOUNT: account,
        TradeFields.SESSION: session,
        TradeFields.DECISION_TYPE: decision_type,
        TradeFields.TOKEN_ADDRESS: token_address,
        TradeFields.TOKEN_SYMBOL: token_symbol,
        TradeFields.AMOUNT_TOKEN: amount_token,
        TradeFields.AMOUNT_USD: amount_usd,
        TradeFields.ENTRY_PRICE: entry_price,
        TradeFields.STATUS: status,
        'gas_cost_usd': gas_cost_usd,
        'slippage_percent': slippage_percent,
        'lane_used': lane_used,
        'intel_level': intel_level,
        'confidence_score': confidence_score,
        'risk_assessment': risk_assessment,
    }

    # Add optional fields
    if exit_price is not None:
        kwargs[TradeFields.EXIT_PRICE] = exit_price
    if executed_at is not None:
        kwargs[TradeFields.EXECUTED_AT] = executed_at
    if profit_loss_usd is not None:
        kwargs[TradeFields.PROFIT_LOSS_USD] = profit_loss_usd
    if profit_loss_percent is not None:
        kwargs[TradeFields.PROFIT_LOSS_PERCENT] = profit_loss_percent

    try:
        trade = PaperTrade.objects.create(**kwargs)
        logger.debug(
            f"Created paper trade: {decision_type} {amount_token} {token_symbol} "
            f"at ${entry_price}"
        )
        return trade
    except Exception as e:
        logger.error(
            f"Failed to create paper trade: {e}",
            exc_info=True,
            extra={
                'decision_type': decision_type,
                'token_symbol': token_symbol,
                'amount_usd': float(amount_usd),
            }
        )
        raise


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_thought_log_from_decision(
    account,
    decision,
    token_symbol: str,
    token_address: str,
    *,
    paper_trade=None,
    strategy_name: str = '',
    lane_used: str = LaneType.FAST,
    analysis_time_ms: int = 0
):
    """
    Create a thought log from a TradingDecision object.

    This is a convenience function that extracts fields from a decision object.

    Args:
        account: PaperTradingAccount instance
        decision: TradingDecision object
        token_symbol: Token symbol
        token_address: Token address
        paper_trade: Optional PaperTrade instance
        strategy_name: Strategy name
        lane_used: Lane type
        analysis_time_ms: Analysis time in milliseconds

    Returns:
        PaperAIThoughtLog instance
    """
    # Extract fields from decision object
    confidence = float(getattr(decision, 'overall_confidence', 75))
    risk_score = float(getattr(decision, 'risk_score', 50))
    opportunity_score = float(getattr(decision, 'opportunity_score', 70))

    # Get reasoning
    primary_reasoning = getattr(
        decision,
        'primary_reasoning',
        'Market analysis suggests favorable conditions'
    )

    # Build key factors
    key_factors = [
        f"Action: {decision.action}",
        f"Confidence: {confidence:.1f}%",
        f"Risk Score: {risk_score:.1f}",
    ]

    # Build market data
    market_data = {
        'decision_action': decision.action,
        'confidence': confidence,
        'risk_score': risk_score,
        'opportunity_score': opportunity_score,
    }

    # Add position size if available
    if hasattr(decision, 'position_size_usd'):
        market_data['position_size_usd'] = float(decision.position_size_usd)

    return create_thought_log(
        account=account,
        decision_type=decision.action,
        token_address=token_address,
        token_symbol=token_symbol,
        confidence_percent=Decimal(str(confidence)),
        risk_score=Decimal(str(risk_score)),
        opportunity_score=Decimal(str(opportunity_score)),
        primary_reasoning=primary_reasoning,
        paper_trade=paper_trade,
        key_factors=key_factors,
        positive_signals=[],
        negative_signals=[],
        market_data=market_data,
        strategy_name=strategy_name,
        lane_used=lane_used,
        analysis_time_ms=analysis_time_ms,
        
    )


def safe_create_thought_log(
    account,
    decision_type: str,
    token_address: str,
    token_symbol: str,
    confidence_percent: Decimal,
    reasoning: str,
    **kwargs
) -> Optional[object]:
    """
    Safely create a thought log with error handling.

    This version catches exceptions and returns None on failure,
    logging the error but not raising it. Useful when thought logging
    is optional and shouldn't break the main flow.

    Args:
        account: PaperTradingAccount instance
        decision_type: Decision type
        token_address: Token address
        token_symbol: Token symbol
        confidence_percent: Confidence percentage
        reasoning: Primary reasoning (will be used as primary_reasoning)
        **kwargs: Additional arguments for create_thought_log

    Returns:
        PaperAIThoughtLog instance or None if creation failed

    Note:
        The 'reasoning' parameter is mapped to 'primary_reasoning'
        to match the model field name.
    """
    try:
        # Set defaults for required fields if not provided
        risk_score = kwargs.pop('risk_score', Decimal('50.0'))
        opportunity_score = kwargs.pop('opportunity_score', Decimal('70.0'))

        return create_thought_log(
            account=account,
            decision_type=decision_type,
            token_address=token_address,
            token_symbol=token_symbol,
            confidence_percent=confidence_percent,
            risk_score=risk_score,
            opportunity_score=opportunity_score,
            primary_reasoning=reasoning,  # Map 'reasoning' to 'primary_reasoning'
            **kwargs
        )
    except Exception as e:
        logger.error(
            f"Failed to create thought log (safe mode): {e}",
            exc_info=True,
            extra={
                'decision_type': decision_type,
                'token_symbol': token_symbol,
            }
        )
        return None


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'create_thought_log',
    'create_paper_trade',
    'create_thought_log_from_decision',
    'safe_create_thought_log',
]
