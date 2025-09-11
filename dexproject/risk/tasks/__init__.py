"""
Missing helper functions for risk tasks.

File: dexproject/risk/tasks/__init__.py

This module provides shared helper functions used by all risk task modules.
"""

import logging
import uuid
from typing import Dict, Any, Optional
from decimal import Decimal
from django.utils import timezone
from django.db import transaction

from ..models import RiskCheckResult, RiskCheckType, RiskAssessment

logger = logging.getLogger('risk.tasks')


def create_risk_check_result(
    assessment: RiskAssessment,
    check_type: RiskCheckType,
    status: str,
    is_blocking: bool = False,
    score: Optional[Decimal] = None,
    confidence: Optional[Decimal] = None,
    details: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
    execution_time_ms: float = 0.0
) -> RiskCheckResult:
    """
    Create a risk check result record.
    
    Args:
        assessment: The risk assessment this result belongs to
        check_type: The type of risk check performed
        status: Status of the check (PENDING, RUNNING, PASSED, FAILED, ERROR, TIMEOUT, SKIPPED)
        is_blocking: Whether this result blocks trading
        score: Risk score (0-100, higher is riskier)
        confidence: Confidence in the assessment (0-100)
        details: Additional details about the check
        error_message: Error message if check failed
        execution_time_ms: How long the check took to execute
        
    Returns:
        RiskCheckResult instance
    """
    try:
        with transaction.atomic():
            result = RiskCheckResult.objects.create(
                assessment=assessment,
                check_type=check_type,
                status=status,
                is_blocking=is_blocking,
                score=score or Decimal('0'),
                confidence=confidence or Decimal('0'),
                weight=check_type.weight,
                details=details or {},
                error_message=error_message,
                started_at=timezone.now(),
                completed_at=timezone.now()
            )
            
            logger.info(
                f"Created risk check result - Type: {check_type.name}, "
                f"Status: {status}, Score: {score}, ID: {result.result_id}"
            )
            
            return result
            
    except Exception as e:
        logger.error(f"Failed to create risk check result: {e}", exc_info=True)
        raise


def get_or_create_risk_check_type(
    name: str,
    category: str,
    description: str,
    severity: str = 'MEDIUM',
    is_blocking: bool = False,
    timeout_seconds: int = 10,
    retry_count: int = 2,
    weight: Decimal = Decimal('1.0')
) -> RiskCheckType:
    """
    Get or create a risk check type.
    
    Args:
        name: Risk check name
        category: Category of the check
        description: Description of what the check does
        severity: Severity level (LOW, MEDIUM, HIGH, CRITICAL)
        is_blocking: Whether failures block trading
        timeout_seconds: Maximum execution time
        retry_count: Number of retries on failure
        weight: Weight in overall risk scoring
        
    Returns:
        RiskCheckType instance
    """
    check_type, created = RiskCheckType.objects.get_or_create(
        name=name,
        defaults={
            'category': category,
            'description': description,
            'severity': severity,
            'is_blocking': is_blocking,
            'timeout_seconds': timeout_seconds,
            'retry_count': retry_count,
            'weight': weight
        }
    )
    
    if created:
        logger.info(f"Created new risk check type: {name}")
    
    return check_type


def create_failed_check_result(
    check_type: str,
    token_address: str,
    error_message: str,
    execution_time_ms: float = 0.0
) -> Dict[str, Any]:
    """
    Create a standardized failed check result.
    
    Args:
        check_type: Type of check that failed
        token_address: Token that was being checked
        error_message: Description of the failure
        execution_time_ms: How long before failure
        
    Returns:
        Dict with failed check result
    """
    return {
        'check_type': check_type,
        'token_address': token_address,
        'status': 'FAILED',
        'error_message': error_message,
        'execution_time_ms': execution_time_ms,
        'timestamp': timezone.now().isoformat(),
        'result_id': str(uuid.uuid4())
    }


def validate_ethereum_address(address: str) -> bool:
    """
    Validate an Ethereum address format.
    
    Args:
        address: Address string to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not address:
        return False
    
    # Check if it's a valid hex string of correct length
    if not address.startswith('0x'):
        return False
    
    if len(address) != 42:  # 0x + 40 hex characters
        return False
    
    try:
        # Try to convert to int to validate hex format
        int(address, 16)
        return True
    except ValueError:
        return False


def format_execution_time(execution_time_ms: float) -> str:
    """
    Format execution time for human readability.
    
    Args:
        execution_time_ms: Execution time in milliseconds
        
    Returns:
        Formatted time string
    """
    if execution_time_ms < 1000:
        return f"{execution_time_ms:.1f}ms"
    elif execution_time_ms < 60000:
        return f"{execution_time_ms/1000:.2f}s"
    else:
        return f"{execution_time_ms/60000:.1f}m"


def calculate_weighted_risk_score(check_results: list) -> Decimal:
    """
    Calculate weighted average risk score from multiple check results.
    
    Args:
        check_results: List of check result dictionaries
        
    Returns:
        Weighted average risk score (0-100)
    """
    if not check_results:
        return Decimal('0')
    
    total_weighted_score = Decimal('0')
    total_weight = Decimal('0')
    
    for result in check_results:
        score = Decimal(str(result.get('risk_score', 0)))
        weight = Decimal(str(result.get('weight', 1)))
        
        total_weighted_score += score * weight
        total_weight += weight
    
    if total_weight == 0:
        return Decimal('0')
    
    return total_weighted_score / total_weight


def determine_risk_level(risk_score: Decimal) -> str:
    """
    Determine risk level based on numerical score.
    
    Args:
        risk_score: Risk score (0-100)
        
    Returns:
        Risk level string (VERY_LOW, LOW, MEDIUM, HIGH, VERY_HIGH, CRITICAL)
    """
    if risk_score <= 10:
        return 'VERY_LOW'
    elif risk_score <= 25:
        return 'LOW'
    elif risk_score <= 50:
        return 'MEDIUM'
    elif risk_score <= 75:
        return 'HIGH'
    elif risk_score <= 90:
        return 'VERY_HIGH'
    else:
        return 'CRITICAL'


def create_thought_log_entry(
    decision_type: str,
    outcome: str,
    confidence: Decimal,
    signals: Dict[str, Any],
    narrative: str,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a thought log entry for AI decision tracking.
    
    Args:
        decision_type: Type of decision (BUY, SELL, HOLD, SKIP)
        outcome: Decision outcome
        confidence: Confidence level (0-100)
        signals: Dictionary of signals that influenced the decision
        narrative: Human-readable explanation
        context: Additional context information
        
    Returns:
        Thought log entry dictionary
    """
    return {
        'timestamp': timezone.now().isoformat(),
        'decision_type': decision_type,
        'outcome': outcome,
        'confidence': float(confidence),
        'signals': signals,
        'narrative': narrative,
        'context': context or {},
        'thought_id': str(uuid.uuid4())
    }


# Export functions for other modules to import
__all__ = [
    'create_risk_check_result',
    'get_or_create_risk_check_type', 
    'create_failed_check_result',
    'validate_ethereum_address',
    'format_execution_time',
    'calculate_weighted_risk_score',
    'determine_risk_level',
    'create_thought_log_entry'
]


# Placeholder functions for other risk checks mentioned in the imports
def honeypot_check(token_address: str, pair_address: str, **kwargs) -> Dict[str, Any]:
    """Placeholder honeypot check - will be replaced by the full implementation."""
    return {
        'check_type': 'HONEYPOT',
        'token_address': token_address,
        'pair_address': pair_address,
        'status': 'COMPLETED',
        'risk_score': 25.0,
        'details': {
            'is_honeypot': False,
            'can_buy': True,
            'can_sell': True,
            'buy_tax_percent': 2.0,
            'sell_tax_percent': 5.0
        },
        'execution_time_ms': 150.0,
        'timestamp': timezone.now().isoformat()
    }


def liquidity_check(pair_address: str, token_address: str = None, **kwargs) -> Dict[str, Any]:
    """Placeholder liquidity check."""
    return {
        'check_type': 'LIQUIDITY',
        'token_address': token_address,
        'pair_address': pair_address,
        'status': 'COMPLETED',
        'risk_score': 30.0,
        'details': {
            'total_liquidity_usd': 50000,
            'meets_minimum': True,
            'slippage_acceptable': True
        },
        'execution_time_ms': 200.0,
        'timestamp': timezone.now().isoformat()
    }


def ownership_check(token_address: str, **kwargs) -> Dict[str, Any]:
    """Placeholder ownership check."""
    return {
        'check_type': 'OWNERSHIP',
        'token_address': token_address,
        'status': 'COMPLETED',
        'risk_score': 20.0,
        'details': {
            'ownership': {
                'has_owner': True,
                'is_renounced': True,
                'owner_address': '0x0000000000000000000000000000000000000000'
            }
        },
        'execution_time_ms': 100.0,
        'timestamp': timezone.now().isoformat()
    }