"""
Risk scoring and decision-making module.

Handles overall risk score calculation, trading decisions,
confidence scoring, and risk level determination.

File: risk/tasks/scoring.py
"""

import logging
from typing import Dict, Any, List
from decimal import Decimal
from .profiles import get_profile_check_weights

logger = logging.getLogger(__name__)


def calculate_overall_risk_score(
    check_results: List[Dict[str, Any]], 
    risk_config: Dict[str, Any]
) -> Decimal:
    """
    Calculate overall risk score from individual check results.
    
    Uses weighted scoring based on check importance and risk profile.
    
    Args:
        check_results: List of individual check results
        risk_config: Risk profile configuration
        
    Returns:
        Overall risk score (0-100)
    """
    if not check_results:
        logger.warning("No check results provided, returning maximum risk")
        return Decimal('100')  # Maximum risk if no checks completed
    
    # Get profile-specific weights
    risk_profile = risk_config.get('name', 'Conservative')
    check_weights = get_profile_check_weights(risk_profile)
    
    total_weighted_score = Decimal('0')
    total_weight = Decimal('0')
    
    for result in check_results:
        check_type = result.get('check_type', 'UNKNOWN')
        risk_score = Decimal(str(result.get('risk_score', 100)))
        weight = check_weights.get(check_type, Decimal('0.1'))  # Default weight for unknown checks
        
        # Apply weight adjustments based on check status
        if result.get('status') == 'WARNING':
            weight *= Decimal('0.8')  # Reduce weight for warning status
        elif result.get('status') == 'FAILED':
            # Failed checks get maximum risk score
            risk_score = Decimal('100')
        
        total_weighted_score += risk_score * weight
        total_weight += weight
        
        logger.debug(f"Check {check_type}: score={risk_score}, weight={weight}")
    
    # Calculate weighted average
    if total_weight > 0:
        overall_score = total_weighted_score / total_weight
    else:
        logger.warning("No valid weights found, returning maximum risk")
        overall_score = Decimal('100')
    
    # Ensure score is within bounds
    final_score = min(max(overall_score, Decimal('0')), Decimal('100'))
    
    logger.info(f"Overall risk score: {final_score:.1f} (from {len(check_results)} checks)")
    
    return final_score


def determine_risk_level(overall_risk_score: Decimal) -> str:
    """
    Determine risk level based on overall score.
    
    Args:
        overall_risk_score: Overall risk score (0-100)
        
    Returns:
        Risk level string ('MINIMAL', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
    """
    score = float(overall_risk_score)
    
    if score >= 80:
        return 'CRITICAL'
    elif score >= 60:
        return 'HIGH'
    elif score >= 40:
        return 'MEDIUM'
    elif score >= 20:
        return 'LOW'
    else:
        return 'MINIMAL'


def make_trading_decision(
    successful_checks: List[Dict[str, Any]], 
    failed_checks: List[Dict[str, Any]], 
    overall_risk_score: Decimal, 
    risk_config: Dict[str, Any]
) -> str:
    """
    Make final trading decision based on all available information.
    
    Args:
        successful_checks: List of successful check results
        failed_checks: List of failed check results
        overall_risk_score: Overall calculated risk score
        risk_config: Risk profile configuration
        
    Returns:
        Trading decision: 'APPROVE', 'SKIP', or 'BLOCK'
    """
    max_acceptable_risk = risk_config.get('max_acceptable_risk', 50)
    
    # Check for critical failures first
    critical_blocking_result = _check_critical_blocking_conditions(successful_checks)
    if critical_blocking_result['should_block']:
        logger.info(f"BLOCKING due to critical condition: {critical_blocking_result['reason']}")
        return 'BLOCK'
    
    # Check profile-specific blocking rules
    from .profiles import apply_profile_blocking_rules
    blocking_decision = apply_profile_blocking_rules(successful_checks, risk_config)
    if blocking_decision.get('should_block', False):
        reasons = blocking_decision.get('reasons', [])
        logger.info(f"BLOCKING due to profile rules: {'; '.join(reasons)}")
        return 'BLOCK'
    
    # Check if too many critical checks failed
    critical_checks_failed = len([
        c for c in failed_checks 
        if c.get('check_type') in ['HONEYPOT', 'LIQUIDITY']
    ])
    if critical_checks_failed >= 2:
        logger.info(f"BLOCKING due to {critical_checks_failed} critical check failures")
        return 'BLOCK'
    
    # Make decision based on overall risk score
    score = float(overall_risk_score)
    if score >= 80:
        logger.info(f"BLOCKING due to high risk score: {score:.1f}")
        return 'BLOCK'
    elif score > max_acceptable_risk:
        logger.info(f"SKIPPING due to elevated risk: {score:.1f} > {max_acceptable_risk}")
        return 'SKIP'
    else:
        logger.info(f"APPROVING with acceptable risk: {score:.1f} <= {max_acceptable_risk}")
        return 'APPROVE'


def calculate_confidence_score(
    successful_checks: List[Dict[str, Any]], 
    failed_checks: List[Dict[str, Any]]
) -> Decimal:
    """
    Calculate confidence score based on check completion and reliability.
    
    Args:
        successful_checks: List of successful check results
        failed_checks: List of failed check results
        
    Returns:
        Confidence score (0-100)
    """
    total_checks = len(successful_checks) + len(failed_checks)
    if total_checks == 0:
        logger.warning("No checks performed, confidence is zero")
        return Decimal('0')
    
    # Base confidence from completion rate
    completion_rate = len(successful_checks) / total_checks
    base_confidence = Decimal(str(completion_rate * 80))  # Max 80 from completion
    
    # Bonus confidence for critical checks completing successfully
    critical_checks = ['HONEYPOT', 'LIQUIDITY']
    critical_completed = len([
        c for c in successful_checks 
        if c.get('check_type') in critical_checks
    ])
    critical_bonus = Decimal(str(critical_completed * 10))  # Max 20 bonus for 2 critical checks
    
    # Penalty for failed critical checks
    critical_failed = len([
        c for c in failed_checks 
        if c.get('check_type') in critical_checks
    ])
    critical_penalty = Decimal(str(critical_failed * 15))  # 15 point penalty per failed critical check
    
    # Quality bonus for checks with low execution time (reliability indicator)
    quality_bonus = Decimal('0')
    for check in successful_checks:
        exec_time = check.get('execution_time_ms', 5000)  # Default to high time if unknown
        if exec_time < 1000:  # Under 1 second indicates good performance
            quality_bonus += Decimal('2')  # Small bonus per fast check
    
    # Cap quality bonus
    quality_bonus = min(quality_bonus, Decimal('10'))
    
    final_confidence = base_confidence + critical_bonus + quality_bonus - critical_penalty
    
    # Ensure confidence is within bounds
    final_confidence = max(Decimal('0'), min(final_confidence, Decimal('100')))
    
    logger.debug(f"Confidence calculation: base={base_confidence}, "
                f"critical_bonus={critical_bonus}, quality_bonus={quality_bonus}, "
                f"critical_penalty={critical_penalty}, final={final_confidence}")
    
    return final_confidence


def get_decision_reasoning(
    trading_decision: str, 
    overall_risk_score: Decimal, 
    successful_checks: List[Dict[str, Any]],
    failed_checks: List[Dict[str, Any]]
) -> str:
    """
    Get human-readable reasoning for the trading decision.
    
    Args:
        trading_decision: The final trading decision
        overall_risk_score: Overall risk score
        successful_checks: Successful check results
        failed_checks: Failed check results
        
    Returns:
        Human-readable reasoning string
    """
    score = float(overall_risk_score)
    
    if trading_decision == 'APPROVE':
        return f"Low risk score ({score:.1f}) and no critical issues detected. Safe to trade."
    
    elif trading_decision == 'SKIP':
        # Find specific reasons for skipping
        reasons = []
        if score > 50:
            reasons.append(f"elevated risk score ({score:.1f})")
        if failed_checks:
            reasons.append(f"{len(failed_checks)} checks failed")
        
        if reasons:
            return f"Moderate risk: {', '.join(reasons)}. Consider manual review."
        else:
            return f"Moderate risk score ({score:.1f}) suggests caution."
    
    else:  # BLOCK
        # Find specific blocking reasons
        blocking_reasons = []
        
        # Check for honeypot
        honeypot_check = next(
            (c for c in successful_checks if c.get('check_type') == 'HONEYPOT'), 
            None
        )
        if honeypot_check and honeypot_check.get('details', {}).get('is_honeypot', False):
            blocking_reasons.append("honeypot detected (cannot sell)")
        
        # Check for high risk score
        if score >= 80:
            blocking_reasons.append(f"high risk score ({score:.1f})")
        
        # Check for critical failures
        critical_failures = [
            c.get('check_type') for c in failed_checks 
            if c.get('check_type') in ['HONEYPOT', 'LIQUIDITY']
        ]
        if critical_failures:
            blocking_reasons.append(f"critical checks failed: {', '.join(critical_failures)}")
        
        if blocking_reasons:
            return f"Dangerous conditions: {', '.join(blocking_reasons)}. Do not trade."
        else:
            return f"High risk score ({score:.1f}) indicates unsafe trading conditions."


def analyze_risk_factors(successful_checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze individual risk factors from check results.
    
    Args:
        successful_checks: List of successful check results
        
    Returns:
        Dict with categorized risk factor analysis
    """
    risk_factors = {
        'critical_risks': [],
        'major_concerns': [],
        'minor_issues': [],
        'positive_signals': []
    }
    
    for check in successful_checks:
        check_type = check.get('check_type')
        risk_score = check.get('risk_score', 0)
        details = check.get('details', {})
        
        # Analyze honeypot results
        if check_type == 'HONEYPOT':
            if details.get('is_honeypot', False):
                risk_factors['critical_risks'].append("Token is a honeypot - cannot sell")
            elif risk_score > 50:
                tax_info = f"Buy: {details.get('buy_tax_percent', 0)}%, Sell: {details.get('sell_tax_percent', 0)}%"
                risk_factors['major_concerns'].append(f"High honeypot risk: {tax_info}")
            else:
                risk_factors['positive_signals'].append("Passed honeypot checks")
        
        # Analyze liquidity results
        elif check_type == 'LIQUIDITY':
            liquidity_usd = details.get('total_liquidity_usd', 0)
            if liquidity_usd < 10000:
                risk_factors['critical_risks'].append(f"Very low liquidity: ${liquidity_usd:,.0f}")
            elif liquidity_usd < 50000:
                risk_factors['major_concerns'].append(f"Low liquidity: ${liquidity_usd:,.0f}")
            else:
                risk_factors['positive_signals'].append(f"Good liquidity: ${liquidity_usd:,.0f}")
        
        # Analyze ownership results
        elif check_type == 'OWNERSHIP':
            ownership = details.get('ownership', {})
            if ownership.get('is_renounced', False):
                risk_factors['positive_signals'].append("Ownership renounced")
            elif ownership.get('has_owner', False):
                admin_functions = details.get('admin_functions', {})
                if admin_functions.get('has_mint_function', False):
                    risk_factors['major_concerns'].append("Owner can mint new tokens")
                else:
                    risk_factors['minor_issues'].append("Owner has control but limited functions")
        
        # Analyze tax results
        elif check_type == 'TAX_ANALYSIS':
            max_tax = details.get('max_tax_percent', 0)
            if max_tax > 20:
                risk_factors['major_concerns'].append(f"High taxes: {max_tax}%")
            elif max_tax > 10:
                risk_factors['minor_issues'].append(f"Moderate taxes: {max_tax}%")
            
            if details.get('has_transfer_restrictions', False):
                risk_factors['major_concerns'].append("Transfer restrictions detected")
    
    return risk_factors


def _check_critical_blocking_conditions(successful_checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Check for critical conditions that should always block trading.
    
    Args:
        successful_checks: List of successful check results
        
    Returns:
        Dict with blocking decision and reason
    """
    for check in successful_checks:
        check_type = check.get('check_type')
        details = check.get('details', {})
        
        # Always block honeypots
        if check_type == 'HONEYPOT':
            if details.get('is_honeypot', False):
                return {
                    'should_block': True,
                    'reason': 'Honeypot detected - tokens cannot be sold',
                    'check_type': 'HONEYPOT'
                }
        
        # Block if liquidity is critically low
        elif check_type == 'LIQUIDITY':
            liquidity_usd = details.get('total_liquidity_usd', 0)
            if liquidity_usd < 1000:  # Critical threshold
                return {
                    'should_block': True,
                    'reason': f'Critically low liquidity: ${liquidity_usd:,.0f}',
                    'check_type': 'LIQUIDITY'
                }
        
        # Block if transfer is completely disabled
        elif check_type == 'TAX_ANALYSIS':
            if details.get('transfer_disabled', False):
                return {
                    'should_block': True,
                    'reason': 'Token transfers are disabled',
                    'check_type': 'TAX_ANALYSIS'
                }
    
    return {'should_block': False, 'reason': None}