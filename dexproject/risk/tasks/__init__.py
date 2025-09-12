"""
Risk Tasks Module - Updated Imports

Updated __init__.py to work with the new modular structure.
Maintains backward compatibility while enabling the new architecture.

File: risk/tasks/__init__.py
"""

from typing import Dict, Any, Optional
from decimal import Decimal
from django.utils import timezone

# Import main task functions (these are the public API)
from .tasks import (
    assess_token_risk,
    quick_honeypot_check,
    bulk_assessment,
    system_health_check
)

# Import utility functions for backward compatibility
from .profiles import (
    get_risk_profile_config,
    validate_risk_profile,
    get_available_profiles,
    apply_profile_blocking_rules,
    get_profile_check_weights
)

from .scoring import (
    calculate_overall_risk_score,
    determine_risk_level,
    make_trading_decision,
    calculate_confidence_score,
    get_decision_reasoning
)

from .reporting import (
    generate_thought_log,
    generate_assessment_summary,
    generate_human_readable_report
)

from .database import (
    create_assessment_record,
    save_assessment_result,
    create_risk_event
)

# Keep existing utility functions for backward compatibility
def create_risk_check_result(
    check_type: str,
    status: str,
    risk_score: Decimal,
    details: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
    execution_time_ms: float = 0,
    **kwargs  # Accept additional parameters like token_address
) -> Dict[str, Any]:
    """
    Create a standardized risk check result.
    
    Args:
        check_type: Type of risk check (e.g., 'OWNERSHIP', 'HONEYPOT')
        status: Check status ('COMPLETED', 'FAILED', 'WARNING')
        risk_score: Risk score from 0-100
        details: Additional check-specific details
        error_message: Error message if check failed
        execution_time_ms: Execution time in milliseconds
        **kwargs: Additional parameters (like token_address, pair_address)
        
    Returns:
        Dict with standardized risk check result
    """
    if details is None:
        details = {}
    
    result = {
        'check_type': check_type,
        'status': status,
        'risk_score': float(risk_score),
        'details': details,
        'execution_time_ms': execution_time_ms,
        'timestamp': timezone.now().isoformat()
    }
    
    # Add optional fields
    if error_message:
        result['error_message'] = error_message
    
    # Add any additional kwargs (like token_address, pair_address)
    result.update(kwargs)
    
    return result


def calculate_weighted_risk_score(check_results: list, weights: Optional[Dict[str, float]] = None) -> float:
    """
    Calculate weighted risk score (backward compatibility function).
    
    Args:
        check_results: List of check results
        weights: Optional weight overrides
        
    Returns:
        Weighted risk score
    """
    # Use the new scoring module
    from .scoring import calculate_overall_risk_score
    from .profiles import get_risk_profile_config
    
    # Default to Conservative profile for backward compatibility
    risk_config = get_risk_profile_config('Conservative')
    
    # Override weights if provided
    if weights:
        # Convert to the new format expected by the scoring module
        risk_config['profile_weights'] = weights
    
    score = calculate_overall_risk_score(check_results, risk_config)
    return float(score)


def should_block_trading(check_results: list, risk_profile: str = 'Conservative') -> bool:
    """
    Determine if trading should be blocked (backward compatibility function).
    
    Args:
        check_results: List of check results
        risk_profile: Risk profile to use
        
    Returns:
        True if trading should be blocked
    """
    # Use the new decision-making module
    from .scoring import make_trading_decision, calculate_overall_risk_score
    from .profiles import get_risk_profile_config
    
    risk_config = get_risk_profile_config(risk_profile)
    
    # Separate successful and failed checks
    successful_checks = [r for r in check_results if r.get('status') in ['COMPLETED', 'WARNING']]
    failed_checks = [r for r in check_results if r.get('status') not in ['COMPLETED', 'WARNING']]
    
    # Calculate risk score and make decision
    overall_risk_score = calculate_overall_risk_score(successful_checks, risk_config)
    decision = make_trading_decision(successful_checks, failed_checks, overall_risk_score, risk_config)
    
    return decision == 'BLOCK'


# Placeholder functions for risk check modules (these should be implemented in separate files)
def honeypot_check(token_address, pair_address, **kwargs):
    """Placeholder honeypot check."""
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


def liquidity_check(pair_address, token_address=None, **kwargs):
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


def ownership_check(token_address, **kwargs):
    """Placeholder ownership check."""
    return {
        'check_type': 'OWNERSHIP',
        'token_address': token_address,
        'status': 'COMPLETED',
        'risk_score': 35.0,
        'details': {
            'ownership': {
                'has_owner': True,
                'is_renounced': False,
                'owner_address': '0x1234567890123456789012345678901234567890'
            },
            'admin_functions': {
                'has_mint_function': False,
                'has_pause_function': True,
                'has_blacklist_function': False
            }
        },
        'execution_time_ms': 300.0,
        'timestamp': timezone.now().isoformat()
    }


def tax_analysis(token_address, pair_address, **kwargs):
    """Placeholder tax analysis."""
    return {
        'check_type': 'TAX_ANALYSIS',
        'token_address': token_address,
        'pair_address': pair_address,
        'status': 'COMPLETED',
        'risk_score': 20.0,
        'details': {
            'buy_tax_percent': 3.0,
            'sell_tax_percent': 7.0,
            'max_tax_percent': 7.0,
            'has_transfer_restrictions': False,
            'has_reflection': False,
            'has_antiwhale': True
        },
        'execution_time_ms': 400.0,
        'timestamp': timezone.now().isoformat()
    }


# Export all public functions and classes
__all__ = [
    # Main task functions
    'assess_token_risk',
    'quick_honeypot_check',
    'bulk_assessment',
    'system_health_check',
    
    # Profile management
    'get_risk_profile_config',
    'validate_risk_profile',
    'get_available_profiles',
    'apply_profile_blocking_rules',
    'get_profile_check_weights',
    
    # Scoring and decision making
    'calculate_overall_risk_score',
    'determine_risk_level',
    'make_trading_decision',
    'calculate_confidence_score',
    'get_decision_reasoning',
    
    # Reporting
    'generate_thought_log',
    'generate_assessment_summary',
    'generate_human_readable_report',
    
    # Database operations
    'create_assessment_record',
    'save_assessment_result',
    'create_risk_event',
    
    # Backward compatibility functions
    'create_risk_check_result',
    'calculate_weighted_risk_score',
    'should_block_trading',
    
    # Placeholder check functions (to be replaced with actual implementations)
    'honeypot_check',
    'liquidity_check',
    'ownership_check',
    'tax_analysis'
]