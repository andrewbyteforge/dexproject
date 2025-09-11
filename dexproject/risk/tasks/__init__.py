"""
Risk assessment task modules.

This package contains all Celery tasks for performing risk assessments
on trading pairs and tokens. Each module handles a specific category
of risk checks with comprehensive error handling and logging.

Modules:
- honeypot: Honeypot detection through transaction simulation
- liquidity: Liquidity depth and quality analysis  
- ownership: Contract ownership and renouncement checks
- taxation: Buy/sell tax analysis
- security: Contract security and admin function analysis
- holders: Token holder concentration and distribution analysis
- coordinator: Main assessment coordinator that orchestrates all checks
"""

import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError

from ..models import RiskAssessment, RiskCheckResult, RiskCheckType, RiskEvent

logger = logging.getLogger(__name__)

# Import all task modules
from . import honeypot
from . import liquidity  
from . import ownership
from . import taxation
from . import security
from . import holders
from . import coordinator

# Export main assessment task
from .coordinator import assess_token_risk

__all__ = [
    'assess_token_risk',
    'honeypot',
    'liquidity', 
    'ownership',
    'taxation',
    'security',
    'holders',
    'coordinator'
]


def create_risk_check_result(
    check_type: str,
    token_address: str,
    pair_address: str = None,
    status: str = 'PENDING',
    risk_score: Decimal = Decimal('0'),
    details: Dict[str, Any] = None,
    error_message: str = None,
    execution_time_ms: float = 0.0
) -> Dict[str, Any]:
    """
    Create a standardized risk check result dictionary.
    
    Args:
        check_type: Type of risk check performed
        token_address: Token contract address
        pair_address: Trading pair address (optional)
        status: Check status (PENDING, COMPLETED, FAILED)
        risk_score: Risk score from 0-100 (higher = riskier)
        details: Additional check-specific details
        error_message: Error message if check failed
        execution_time_ms: Time taken to execute check
        
    Returns:
        Standardized risk check result dictionary
    """
    if details is None:
        details = {}
    
    return {
        'check_type': check_type,
        'token_address': token_address,
        'pair_address': pair_address,
        'status': status,
        'risk_score': float(risk_score),
        'details': details,
        'error_message': error_message,
        'execution_time_ms': execution_time_ms,
        'timestamp': timezone.now().isoformat()
    }


def calculate_weighted_risk_score(check_results: List[Dict[str, Any]]) -> Tuple[Decimal, str]:
    """
    Calculate overall weighted risk score from individual check results.
    
    Args:
        check_results: List of risk check result dictionaries
        
    Returns:
        Tuple of (overall_risk_score, risk_level)
    """
    if not check_results:
        return Decimal('0'), 'LOW'
    
    total_weighted_score = Decimal('0')
    total_weight = Decimal('0')
    
    for result in check_results:
        if result.get('status') == 'COMPLETED':
            # Get weight from RiskCheckType model or default
            try:
                check_type = RiskCheckType.objects.get(name=result['check_type'])
                weight = check_type.weight
            except RiskCheckType.DoesNotExist:
                weight = Decimal('1.0')  # Default weight
            
            score = Decimal(str(result.get('risk_score', 0)))
            total_weighted_score += score * weight
            total_weight += weight
    
    if total_weight == 0:
        return Decimal('100'), 'CRITICAL'  # All checks failed
    
    overall_score = total_weighted_score / total_weight
    
    # Determine risk level based on score
    if overall_score >= 80:
        risk_level = 'CRITICAL'
    elif overall_score >= 60:
        risk_level = 'HIGH'
    elif overall_score >= 30:
        risk_level = 'MEDIUM'
    else:
        risk_level = 'LOW'
    
    return overall_score, risk_level


def should_block_trading(check_results: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """
    Determine if trading should be blocked based on check results.
    
    Args:
        check_results: List of risk check result dictionaries
        
    Returns:
        Tuple of (should_block, blocking_reasons)
    """
    blocking_reasons = []
    
    for result in check_results:
        check_type = result.get('check_type', 'UNKNOWN')
        
        # Check if this is a blocking check type
        try:
            risk_check_type = RiskCheckType.objects.get(name=check_type)
            if risk_check_type.is_blocking:
                if result.get('status') == 'FAILED':
                    blocking_reasons.append(f"{check_type} check failed")
                elif result.get('status') == 'COMPLETED':
                    # Check if risk score exceeds blocking threshold
                    risk_score = result.get('risk_score', 0)
                    if risk_score >= 90:  # High risk threshold for blocking checks
                        blocking_reasons.append(f"{check_type} risk score too high ({risk_score})")
        except RiskCheckType.DoesNotExist:
            logger.warning(f"Unknown risk check type: {check_type}")
    
    # Additional blocking conditions
    failed_count = sum(1 for r in check_results if r.get('status') == 'FAILED')
    if failed_count >= 3:  # Too many failed checks
        blocking_reasons.append(f"Too many failed checks ({failed_count})")
    
    # Check for specific high-risk indicators
    for result in check_results:
        details = result.get('details', {})
        
        # Honeypot detection
        if result.get('check_type') == 'HONEYPOT' and details.get('is_honeypot'):
            blocking_reasons.append("Token identified as honeypot")
        
        # Extremely high taxes
        if result.get('check_type') == 'TAX_ANALYSIS':
            if details.get('sell_tax_percent', 0) > 50:
                blocking_reasons.append(f"Excessive sell tax ({details.get('sell_tax_percent')}%)")
    
    should_block = len(blocking_reasons) > 0
    return should_block, blocking_reasons