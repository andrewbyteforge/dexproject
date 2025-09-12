"""
Risk profile configuration and management module.

Handles all risk profile related logic including configuration data,
validation, and profile-specific blocking rules.

File: risk/tasks/profiles.py
"""

import logging
from typing import Dict, Any, List
from decimal import Decimal

logger = logging.getLogger(__name__)


def get_risk_profile_config(risk_profile: str) -> Dict[str, Any]:
    """
    Get configuration for the specified risk profile.
    
    Args:
        risk_profile: Risk profile name ('Conservative', 'Moderate', 'Aggressive')
        
    Returns:
        Dict with risk profile configuration
        
    Raises:
        ValueError: If risk profile is not recognized
    """
    profiles = {
        'Conservative': {
            'max_acceptable_risk': 30,
            'required_checks': ['HONEYPOT', 'LIQUIDITY', 'OWNERSHIP', 'TAX_ANALYSIS'],
            'optional_checks': ['CONTRACT_SECURITY', 'HOLDER_ANALYSIS'],
            'blocking_thresholds': {
                'HONEYPOT': 90,
                'LIQUIDITY': 80,
                'OWNERSHIP': 70,
                'TAX_ANALYSIS': 75
            },
            'min_liquidity_usd': 50000,
            'max_slippage_percent': 3.0,
            'require_ownership_renounced': True,
            'max_sell_tax_percent': 10,
            'timeout_seconds': 30
        },
        'Moderate': {
            'max_acceptable_risk': 50,
            'required_checks': ['HONEYPOT', 'LIQUIDITY', 'OWNERSHIP'],
            'optional_checks': ['TAX_ANALYSIS', 'CONTRACT_SECURITY', 'HOLDER_ANALYSIS'],
            'blocking_thresholds': {
                'HONEYPOT': 90,
                'LIQUIDITY': 85,
                'OWNERSHIP': 80,
                'TAX_ANALYSIS': 85
            },
            'min_liquidity_usd': 20000,
            'max_slippage_percent': 5.0,
            'require_ownership_renounced': False,
            'max_sell_tax_percent': 20,
            'timeout_seconds': 25
        },
        'Aggressive': {
            'max_acceptable_risk': 70,
            'required_checks': ['HONEYPOT', 'LIQUIDITY'],
            'optional_checks': ['OWNERSHIP', 'TAX_ANALYSIS', 'CONTRACT_SECURITY'],
            'blocking_thresholds': {
                'HONEYPOT': 95,
                'LIQUIDITY': 90,
                'OWNERSHIP': 90,
                'TAX_ANALYSIS': 95
            },
            'min_liquidity_usd': 10000,
            'max_slippage_percent': 8.0,
            'require_ownership_renounced': False,
            'max_sell_tax_percent': 35,
            'timeout_seconds': 20
        }
    }
    
    if risk_profile not in profiles:
        logger.warning(f"Unknown risk profile '{risk_profile}', defaulting to Conservative")
        return profiles['Conservative']
    
    return profiles[risk_profile]


def validate_risk_profile(risk_profile: str) -> bool:
    """
    Validate if a risk profile name is supported.
    
    Args:
        risk_profile: Risk profile name to validate
        
    Returns:
        True if profile is valid, False otherwise
    """
    valid_profiles = ['Conservative', 'Moderate', 'Aggressive']
    return risk_profile in valid_profiles


def get_available_profiles() -> List[str]:
    """
    Get list of available risk profile names.
    
    Returns:
        List of available risk profile names
    """
    return ['Conservative', 'Moderate', 'Aggressive']


def apply_profile_blocking_rules(
    check_results: List[Dict[str, Any]], 
    risk_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Apply profile-specific blocking rules to check results.
    
    Args:
        check_results: List of risk check results
        risk_config: Risk profile configuration
        
    Returns:
        Dict with blocking decision and reasons
    """
    should_block = False
    reasons = []
    rules_applied = 0
    
    try:
        blocking_thresholds = risk_config.get('blocking_thresholds', {})
        
        # Check each result against profile thresholds
        for result in check_results:
            check_type = result.get('check_type')
            risk_score = result.get('risk_score', 0)
            
            threshold = blocking_thresholds.get(check_type)
            if threshold and risk_score >= threshold:
                should_block = True
                reasons.append(f"{check_type} score ({risk_score}) exceeds threshold ({threshold})")
                rules_applied += 1
        
        # Apply ownership requirements
        if risk_config.get('require_ownership_renounced'):
            ownership_result = next(
                (r for r in check_results if r.get('check_type') == 'OWNERSHIP'), 
                None
            )
            if ownership_result:
                details = ownership_result.get('details', {})
                ownership_info = details.get('ownership', {})
                if not ownership_info.get('is_renounced', False):
                    should_block = True
                    reasons.append("Ownership not renounced (required by profile)")
                    rules_applied += 1
        
        # Check maximum sell tax
        max_sell_tax = risk_config.get('max_sell_tax_percent', 100)
        tax_result = next(
            (r for r in check_results if r.get('check_type') == 'TAX_ANALYSIS'), 
            None
        )
        if tax_result:
            details = tax_result.get('details', {})
            sell_tax = details.get('sell_tax_percent', 0)
            if sell_tax > max_sell_tax:
                should_block = True
                reasons.append(f"Sell tax ({sell_tax}%) exceeds maximum ({max_sell_tax}%)")
                rules_applied += 1
        
        # Check minimum liquidity requirement
        min_liquidity = risk_config.get('min_liquidity_usd', 0)
        liquidity_result = next(
            (r for r in check_results if r.get('check_type') == 'LIQUIDITY'), 
            None
        )
        if liquidity_result:
            details = liquidity_result.get('details', {})
            total_liquidity = details.get('total_liquidity_usd', 0)
            if total_liquidity < min_liquidity:
                should_block = True
                reasons.append(
                    f"Liquidity (${total_liquidity:,.2f}) below minimum (${min_liquidity:,.2f})"
                )
                rules_applied += 1
        
        # Check maximum slippage
        max_slippage = risk_config.get('max_slippage_percent', 100)
        if liquidity_result:
            details = liquidity_result.get('details', {})
            estimated_slippage = details.get('estimated_slippage_percent', 0)
            if estimated_slippage > max_slippage:
                should_block = True
                reasons.append(
                    f"Slippage ({estimated_slippage}%) exceeds maximum ({max_slippage}%)"
                )
                rules_applied += 1
        
        logger.debug(f"Applied {rules_applied} profile rules, blocking: {should_block}")
        
        return {
            'should_block': should_block,
            'reasons': reasons,
            'rules_applied': rules_applied,
            'profile_name': risk_config.get('name', 'Unknown')
        }
        
    except Exception as e:
        logger.error(f"Failed to apply risk profile rules: {e}")
        return {
            'should_block': False,
            'reasons': [],
            'rules_applied': 0,
            'error': str(e)
        }


def get_profile_check_weights(risk_profile: str) -> Dict[str, Decimal]:
    """
    Get check weight factors for the specified risk profile.
    
    Different profiles may weight certain checks more heavily.
    
    Args:
        risk_profile: Risk profile name
        
    Returns:
        Dict mapping check types to weight factors
    """
    # Base weight factors (Conservative profile)
    base_weights = {
        'HONEYPOT': Decimal('0.35'),      # Highest weight - critical for scam detection
        'LIQUIDITY': Decimal('0.25'),     # High weight - affects trade execution
        'TAX_ANALYSIS': Decimal('0.20'),  # Medium weight - affects profitability
        'OWNERSHIP': Decimal('0.15'),     # Lower weight - affects long-term risk
        'CONTRACT_SECURITY': Decimal('0.05'),  # Lowest weight - additional security
    }
    
    # Profile-specific adjustments
    if risk_profile == 'Aggressive':
        # Aggressive profile focuses more on liquidity and less on ownership/security
        base_weights.update({
            'HONEYPOT': Decimal('0.40'),
            'LIQUIDITY': Decimal('0.35'),
            'TAX_ANALYSIS': Decimal('0.15'),
            'OWNERSHIP': Decimal('0.08'),
            'CONTRACT_SECURITY': Decimal('0.02'),
        })
    elif risk_profile == 'Moderate':
        # Moderate profile balances all factors more evenly
        base_weights.update({
            'HONEYPOT': Decimal('0.30'),
            'LIQUIDITY': Decimal('0.25'),
            'TAX_ANALYSIS': Decimal('0.25'),
            'OWNERSHIP': Decimal('0.15'),
            'CONTRACT_SECURITY': Decimal('0.05'),
        })
    
    return base_weights


def get_profile_summary(risk_profile: str) -> Dict[str, Any]:
    """
    Get a human-readable summary of a risk profile.
    
    Args:
        risk_profile: Risk profile name
        
    Returns:
        Dict with profile summary information
    """
    config = get_risk_profile_config(risk_profile)
    
    return {
        'name': risk_profile,
        'description': _get_profile_description(risk_profile),
        'max_acceptable_risk': config.get('max_acceptable_risk', 50),
        'required_checks': len(config.get('required_checks', [])),
        'optional_checks': len(config.get('optional_checks', [])),
        'min_liquidity_usd': config.get('min_liquidity_usd', 0),
        'max_sell_tax_percent': config.get('max_sell_tax_percent', 100),
        'require_ownership_renounced': config.get('require_ownership_renounced', False),
        'timeout_seconds': config.get('timeout_seconds', 30)
    }


def _get_profile_description(risk_profile: str) -> str:
    """Get human-readable description for a risk profile."""
    descriptions = {
        'Conservative': (
            "Conservative profile prioritizes safety over speed. "
            "Requires ownership renouncing, low taxes, high liquidity, "
            "and passes all major security checks."
        ),
        'Moderate': (
            "Moderate profile balances safety and opportunity. "
            "Accepts moderate risks for potentially higher returns "
            "while maintaining core security requirements."
        ),
        'Aggressive': (
            "Aggressive profile focuses on early opportunities. "
            "Accepts higher risks for potentially high returns "
            "but still blocks obvious scams and honeypots."
        )
    }
    
    return descriptions.get(risk_profile, "Unknown risk profile")