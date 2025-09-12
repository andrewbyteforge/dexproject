"""
Risk assessment reporting and formatting module.

Handles generation of thought logs, summaries, and user-friendly
reports for risk assessment results.

File: risk/tasks/reporting.py
"""

import logging
from typing import Dict, Any, List
from decimal import Decimal
from django.utils import timezone
from .scoring import analyze_risk_factors, determine_risk_level

logger = logging.getLogger(__name__)


def generate_thought_log(
    successful_checks: List[Dict[str, Any]], 
    failed_checks: List[Dict[str, Any]], 
    overall_risk_score: Decimal, 
    trading_decision: str, 
    risk_profile: str
) -> Dict[str, Any]:
    """
    Generate AI thought log explaining the reasoning behind the decision.
    
    Args:
        successful_checks: Successful check results
        failed_checks: Failed check results
        overall_risk_score: Overall risk score
        trading_decision: Final trading decision
        risk_profile: Risk profile used
        
    Returns:
        Dict with structured thought log
    """
    # Analyze key signals from check results
    signals = _extract_key_signals(successful_checks)
    
    # Generate decision narrative
    narrative = _generate_decision_narrative(
        trading_decision, overall_risk_score, successful_checks, failed_checks, risk_profile
    )
    
    # Create counterfactual analysis
    counterfactuals = _generate_counterfactuals(successful_checks, risk_profile)
    
    thought_log = {
        'timestamp': timezone.now().isoformat(),
        'decision': trading_decision,
        'risk_score': float(overall_risk_score),
        'risk_level': determine_risk_level(overall_risk_score),
        'risk_profile': risk_profile,
        'signals': signals,
        'narrative': narrative,
        'counterfactuals': counterfactuals,
        'checks_completed': len(successful_checks),
        'checks_failed': len(failed_checks),
        'reasoning_version': '1.0'
    }
    
    logger.debug(f"Generated thought log with {len(signals)} signals")
    
    return thought_log


def generate_assessment_summary(
    successful_checks: List[Dict[str, Any]], 
    failed_checks: List[Dict[str, Any]], 
    overall_risk_score: Decimal, 
    trading_decision: str, 
    risk_profile: str
) -> Dict[str, Any]:
    """
    Generate comprehensive summary of assessment results.
    
    Args:
        successful_checks: Successful check results
        failed_checks: Failed check results
        overall_risk_score: Overall risk score
        trading_decision: Final trading decision
        risk_profile: Risk profile used
        
    Returns:
        Dict with assessment summary
    """
    # Summarize individual checks
    checks_summary = _summarize_individual_checks(successful_checks, failed_checks)
    
    # Create risk summary
    risk_summary = {
        'overall_score': float(overall_risk_score),
        'risk_level': determine_risk_level(overall_risk_score),
        'profile_used': risk_profile,
        'within_tolerance': _is_within_risk_tolerance(overall_risk_score, risk_profile),
        'risk_factors': analyze_risk_factors(successful_checks)
    }
    
    # Generate recommendation
    from .scoring import get_decision_reasoning
    recommendation = {
        'action': trading_decision,
        'confidence': _calculate_recommendation_confidence(successful_checks, failed_checks),
        'reasoning': get_decision_reasoning(
            trading_decision, overall_risk_score, successful_checks, failed_checks
        ),
        'next_steps': _generate_next_steps(trading_decision, overall_risk_score)
    }
    
    # Performance metrics
    performance = _calculate_performance_metrics(successful_checks, failed_checks)
    
    return {
        'checks_summary': checks_summary,
        'risk_summary': risk_summary,
        'recommendation': recommendation,
        'performance': performance,
        'total_checks': len(successful_checks) + len(failed_checks),
        'successful_checks': len(successful_checks),
        'failed_checks': len(failed_checks),
        'summary_version': '1.0'
    }


def generate_human_readable_report(
    assessment_result: Dict[str, Any]
) -> str:
    """
    Generate human-readable text report from assessment result.
    
    Args:
        assessment_result: Complete assessment result dict
        
    Returns:
        Formatted text report
    """
    lines = []
    
    # Header
    decision = assessment_result.get('trading_decision', 'UNKNOWN')
    risk_score = assessment_result.get('overall_risk_score', 0)
    token_address = assessment_result.get('token_address', 'Unknown')
    
    lines.append(f"RISK ASSESSMENT REPORT")
    lines.append(f"Token: {token_address}")
    lines.append(f"Decision: {decision}")
    lines.append(f"Risk Score: {risk_score:.1f}/100")
    lines.append("-" * 50)
    
    # Key findings
    thought_log = assessment_result.get('thought_log', {})
    signals = thought_log.get('signals', [])
    
    if signals:
        lines.append("KEY FINDINGS:")
        for signal in signals[:5]:  # Top 5 signals
            lines.append(f"  • {signal}")
        lines.append("")
    
    # Decision reasoning
    narrative = thought_log.get('narrative', '')
    if narrative:
        lines.append("REASONING:")
        lines.append(f"  {narrative}")
        lines.append("")
    
    # Individual check results
    summary = assessment_result.get('summary', {})
    checks_summary = summary.get('checks_summary', {})
    
    if checks_summary:
        lines.append("CHECK RESULTS:")
        for check_type, check_info in checks_summary.items():
            status = check_info.get('status', 'UNKNOWN')
            score = check_info.get('risk_score', 0)
            
            if status == 'COMPLETED':
                lines.append(f"  {check_type}: {status} (Risk: {score:.1f})")
            else:
                lines.append(f"  {check_type}: {status}")
        lines.append("")
    
    # Recommendation
    recommendation = summary.get('recommendation', {})
    if recommendation:
        confidence = recommendation.get('confidence', 'UNKNOWN')
        reasoning = recommendation.get('reasoning', '')
        
        lines.append("RECOMMENDATION:")
        lines.append(f"  Action: {decision} (Confidence: {confidence})")
        if reasoning:
            lines.append(f"  {reasoning}")
    
    return "\n".join(lines)


def _extract_key_signals(successful_checks: List[Dict[str, Any]]) -> List[str]:
    """Extract key signals from check results for thought log."""
    signals = []
    
    for check in successful_checks:
        check_type = check.get('check_type')
        details = check.get('details', {})
        risk_score = check.get('risk_score', 0)
        
        # Honeypot signals
        if check_type == 'HONEYPOT':
            if details.get('is_honeypot', False):
                signals.append("🚨 HONEYPOT DETECTED - Cannot sell tokens")
            elif details.get('can_sell', True):
                signals.append("✅ Can buy and sell - Not a honeypot")
            
            buy_tax = details.get('buy_tax_percent', 0)
            sell_tax = details.get('sell_tax_percent', 0)
            if buy_tax > 10 or sell_tax > 10:
                signals.append(f"⚠️ High taxes: Buy {buy_tax}%, Sell {sell_tax}%")
        
        # Liquidity signals
        elif check_type == 'LIQUIDITY':
            total_liquidity = details.get('total_liquidity_usd', 0)
            if total_liquidity >= 100000:
                signals.append(f"✅ Strong liquidity: ${total_liquidity:,.0f}")
            elif total_liquidity >= 50000:
                signals.append(f"✅ Good liquidity: ${total_liquidity:,.0f}")
            elif total_liquidity >= 10000:
                signals.append(f"⚠️ Medium liquidity: ${total_liquidity:,.0f}")
            else:
                signals.append(f"🚨 Low liquidity: ${total_liquidity:,.0f}")
        
        # Ownership signals
        elif check_type == 'OWNERSHIP':
            ownership = details.get('ownership', {})
            if ownership.get('is_renounced', False):
                signals.append("✅ Ownership renounced - Reduced rug risk")
            elif ownership.get('has_owner', False):
                signals.append("⚠️ Owner can still control contract")
                
                admin_functions = details.get('admin_functions', {})
                if admin_functions.get('has_mint_function', False):
                    signals.append("🚨 Owner can mint new tokens")
        
        # Tax analysis signals
        elif check_type == 'TAX_ANALYSIS':
            if details.get('has_transfer_restrictions', False):
                signals.append("⚠️ Transfer restrictions detected")
            
            max_tax = details.get('max_tax_percent', 0)
            if max_tax > 20:
                signals.append(f"🚨 Very high taxes: {max_tax}%")
            elif max_tax > 10:
                signals.append(f"⚠️ High taxes: {max_tax}%")
            
            if details.get('has_reflection', False):
                signals.append("ℹ️ Reflection token - may affect gas costs")
    
    return signals


def _generate_decision_narrative(
    trading_decision: str, 
    overall_risk_score: Decimal, 
    successful_checks: List[Dict[str, Any]], 
    failed_checks: List[Dict[str, Any]], 
    risk_profile: str
) -> str:
    """Generate narrative explanation of the trading decision."""
    score = float(overall_risk_score)
    narrative_parts = []
    
    # Decision explanation
    if trading_decision == 'APPROVE':
        narrative_parts.append(f"✅ APPROVED for trading under {risk_profile} profile.")
        narrative_parts.append(f"Risk score of {score:.1f} is within acceptable range.")
        
        # Highlight positive factors
        honeypot_check = next(
            (c for c in successful_checks if c.get('check_type') == 'HONEYPOT'), None
        )
        if honeypot_check and not honeypot_check.get('details', {}).get('is_honeypot', False):
            narrative_parts.append("Token passed honeypot verification.")
            
    elif trading_decision == 'SKIP':
        narrative_parts.append(f"⚠️ SKIPPING token due to elevated risk.")
        narrative_parts.append(f"Risk score of {score:.1f} exceeds {risk_profile} profile limits.")
        narrative_parts.append("Consider manual review or wait for better conditions.")
        
    else:  # BLOCK
        narrative_parts.append(f"🚨 BLOCKING token due to critical risks detected.")
        narrative_parts.append(f"Risk score of {score:.1f} indicates unsafe trading conditions.")
        
        # Identify specific blocking reasons
        honeypot_check = next(
            (c for c in successful_checks if c.get('check_type') == 'HONEYPOT'), None
        )
        if honeypot_check and honeypot_check.get('details', {}).get('is_honeypot', False):
            narrative_parts.append("Primary concern: Token is a honeypot.")
    
    # Add context about failed checks
    if failed_checks:
        narrative_parts.append(f"Note: {len(failed_checks)} checks failed to complete.")
    
    # Add execution context
    total_checks = len(successful_checks) + len(failed_checks)
    if total_checks > 0:
        completion_rate = len(successful_checks) / total_checks * 100
        narrative_parts.append(f"Assessment based on {completion_rate:.0f}% check completion rate.")
    
    return ' '.join(narrative_parts)


def _generate_counterfactuals(
    successful_checks: List[Dict[str, Any]], 
    risk_profile: str
) -> List[str]:
    """Generate counterfactual scenarios for decision analysis."""
    counterfactuals = []
    
    # Analyze what would change the decision
    for check in successful_checks:
        check_type = check.get('check_type')
        details = check.get('details', {})
        
        if check_type == 'HONEYPOT':
            buy_tax = details.get('buy_tax_percent', 0)
            sell_tax = details.get('sell_tax_percent', 0)
            if buy_tax > 5 or sell_tax > 5:
                counterfactuals.append(
                    f"Would be more favorable with lower taxes (currently {buy_tax}%/{sell_tax}%)"
                )
        
        elif check_type == 'LIQUIDITY':
            liquidity = details.get('total_liquidity_usd', 0)
            if liquidity < 50000:
                counterfactuals.append(
                    f"Would approve with higher liquidity (need ${50000:,}, have ${liquidity:,})"
                )
        
        elif check_type == 'OWNERSHIP':
            ownership = details.get('ownership', {})
            if ownership.get('has_owner', False) and not ownership.get('is_renounced', False):
                if risk_profile == 'Conservative':
                    counterfactuals.append("Would approve if ownership was renounced")
    
    # Add profile-specific counterfactuals
    if risk_profile == 'Conservative':
        counterfactuals.append("Would accept higher risk with Moderate or Aggressive profile")
    elif risk_profile == 'Aggressive':
        counterfactuals.append("Conservative profile would likely block this token")
    
    return counterfactuals[:3]  # Limit to top 3 counterfactuals


def _summarize_individual_checks(
    successful_checks: List[Dict[str, Any]], 
    failed_checks: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Summarize individual check results."""
    checks_summary = {}
    
    # Process successful checks
    for check in successful_checks:
        check_type = check.get('check_type')
        checks_summary[check_type] = {
            'status': check.get('status', 'UNKNOWN'),
            'risk_score': check.get('risk_score', 0),
            'execution_time_ms': check.get('execution_time_ms', 0),
            'details_available': bool(check.get('details'))
        }
    
    # Process failed checks
    for check in failed_checks:
        check_type = check.get('check_type')
        checks_summary[check_type] = {
            'status': 'FAILED',
            'error': check.get('error_message', 'Unknown error'),
            'execution_time_ms': check.get('execution_time_ms', 0),
            'details_available': False
        }
    
    return checks_summary


def _is_within_risk_tolerance(overall_risk_score: Decimal, risk_profile: str) -> bool:
    """Check if risk score is within profile tolerance."""
    from .profiles import get_risk_profile_config
    
    config = get_risk_profile_config(risk_profile)
    max_acceptable = config.get('max_acceptable_risk', 50)
    
    return float(overall_risk_score) <= max_acceptable


def _calculate_recommendation_confidence(
    successful_checks: List[Dict[str, Any]], 
    failed_checks: List[Dict[str, Any]]
) -> str:
    """Calculate confidence level for recommendation."""
    total_checks = len(successful_checks) + len(failed_checks)
    
    if total_checks == 0:
        return 'NONE'
    
    completion_rate = len(successful_checks) / total_checks
    
    # Check for critical check completion
    critical_checks = ['HONEYPOT', 'LIQUIDITY']
    critical_completed = len([
        c for c in successful_checks 
        if c.get('check_type') in critical_checks
    ])
    
    if completion_rate >= 0.9 and critical_completed >= 2:
        return 'HIGH'
    elif completion_rate >= 0.7 and critical_completed >= 1:
        return 'MEDIUM'
    elif completion_rate >= 0.5:
        return 'LOW'
    else:
        return 'VERY_LOW'
    

"""
Reporting module helper functions - continuation.

Additional helper functions for the reporting module.
"""

def _generate_next_steps(trading_decision: str, overall_risk_score: float) -> List[str]:
    """Generate recommended next steps based on decision."""
    next_steps = []
    
    if trading_decision == 'APPROVE':
        next_steps.append("Proceed with trade execution")
        next_steps.append("Monitor position after entry")
        if overall_risk_score > 20:
            next_steps.append("Consider smaller position size due to moderate risk")
    
    elif trading_decision == 'SKIP':
        next_steps.append("Wait for better market conditions")
        next_steps.append("Re-assess token in 1-4 hours")
        next_steps.append("Consider manual review of risk factors")
        if overall_risk_score < 60:
            next_steps.append("May approve with less conservative profile")
    
    else:  # BLOCK
        next_steps.append("Do not trade this token")
        next_steps.append("Add to watchlist for monitoring")
        if overall_risk_score < 90:
            next_steps.append("Re-assess if fundamental conditions change")
    
    return next_steps


def _calculate_performance_metrics(
    successful_checks: List[Dict[str, Any]], 
    failed_checks: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Calculate performance metrics for the assessment."""
    total_checks = len(successful_checks) + len(failed_checks)
    
    if total_checks == 0:
        return {
            'completion_rate': 0.0,
            'average_execution_time_ms': 0.0,
            'fastest_check_ms': 0.0,
            'slowest_check_ms': 0.0,
            'total_execution_time_ms': 0.0
        }
    
    # Calculate execution times
    execution_times = []
    total_time = 0.0
    
    for check in successful_checks + failed_checks:
        exec_time = check.get('execution_time_ms', 0)
        execution_times.append(exec_time)
        total_time += exec_time
    
    completion_rate = len(successful_checks) / total_checks
    avg_time = total_time / total_checks if total_checks > 0 else 0.0
    
    return {
        'completion_rate': completion_rate,
        'average_execution_time_ms': avg_time,
        'fastest_check_ms': min(execution_times) if execution_times else 0.0,
        'slowest_check_ms': max(execution_times) if execution_times else 0.0,
        'total_execution_time_ms': total_time,
        'checks_per_second': total_checks / (total_time / 1000) if total_time > 0 else 0.0
    }