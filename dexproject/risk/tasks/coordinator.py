"""
Risk assessment coordinator task module.

Orchestrates all risk checks and provides the main entry point for
comprehensive token risk assessment. Manages parallel execution of
individual risk checks and aggregates results into final assessment.

This is the primary task that the trading engine calls to evaluate
whether a token is safe to trade.
"""

import logging
import time
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from celery import shared_task, group
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError

from ..models import RiskAssessment, RiskCheckResult, RiskCheckType, RiskEvent
from . import (
    create_risk_check_result, 
    calculate_weighted_risk_score, 
    should_block_trading
)

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    queue='risk.urgent',
    name='risk.tasks.assess_token_risk',
    max_retries=2,
    default_retry_delay=5
)
def assess_token_risk(
    self,
    token_address: str,
    pair_address: str,
    assessment_id: Optional[str] = None,
    risk_profile: str = 'Conservative',
    parallel_execution: bool = True,
    include_advanced_checks: bool = True
) -> Dict[str, Any]:
    """
    Perform comprehensive risk assessment for a token/pair.
    
    This is the main entry point for risk assessment that coordinates
    all individual risk checks and provides a final trading decision.
    
    Args:
        token_address: The token contract address to assess
        pair_address: The trading pair address
        assessment_id: Optional existing assessment ID to update
        risk_profile: Risk profile to use ('Conservative', 'Moderate', 'Aggressive')
        parallel_execution: Whether to run checks in parallel (default True)
        include_advanced_checks: Whether to include time-intensive advanced checks
        
    Returns:
        Dict with complete risk assessment and trading recommendation
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting comprehensive risk assessment for token {token_address} (task: {task_id})")
    
    try:
        # Validate inputs
        if not token_address or not pair_address:
            raise ValueError("Both token_address and pair_address are required")
        
        # Get risk profile configuration
        risk_config = _get_risk_profile_config(risk_profile)
        
        # Create assessment record
        assessment_record = _create_assessment_record(
            token_address, pair_address, assessment_id, risk_profile
        )
        assessment_id = assessment_record['assessment_id']
        
        # Execute risk checks
        if parallel_execution:
            check_results = _execute_parallel_risk_checks(
                token_address, pair_address, risk_config, include_advanced_checks
            )
        else:
            check_results = _execute_sequential_risk_checks(
                token_address, pair_address, risk_config, include_advanced_checks
            )
        
        # Analyze results and make trading decision
        final_assessment = _analyze_and_finalize_assessment(
            assessment_id, token_address, pair_address, check_results, risk_config
        )
        
        # Store final assessment in database
        _store_final_assessment(final_assessment)
        
        # Log completion
        execution_time_ms = (time.time() - start_time) * 1000
        final_assessment['execution_time_ms'] = execution_time_ms
        
        logger.info(
            f"Risk assessment completed for {token_address} - "
            f"Risk Score: {final_assessment['overall_risk_score']}, "
            f"Decision: {final_assessment['trading_decision']}, "
            f"Time: {execution_time_ms:.1f}ms"
        )
        
        return final_assessment
        
    except Exception as exc:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"Risk assessment failed for {token_address}: {exc} (task: {task_id})")
        
        # Retry logic for transient failures
        if self.request.retries < self.max_retries and _is_retryable_error(exc):
            countdown = min(2 ** self.request.retries * 5, 60)  # Max 60 seconds
            logger.warning(f"Retrying risk assessment for {token_address} in {countdown}s (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=countdown)
        
        # Final failure - return maximum risk assessment
        return _create_failure_assessment(
            token_address, pair_address, assessment_id, str(exc), execution_time_ms
        )


def _get_risk_profile_config(risk_profile: str) -> Dict[str, Any]:
    """
    Get configuration for the specified risk profile.
    
    Args:
        risk_profile: Risk profile name
        
    Returns:
        Dict with risk profile configuration
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
    
    return profiles.get(risk_profile, profiles['Conservative'])


def _create_assessment_record(
    token_address: str, 
    pair_address: str, 
    assessment_id: Optional[str], 
    risk_profile: str
) -> Dict[str, Any]:
    """Create or update assessment record in database."""
    try:
        with transaction.atomic():
            if assessment_id:
                # Update existing assessment
                logger.debug(f"Updating existing assessment {assessment_id}")
                return {'assessment_id': assessment_id, 'created': False}
            else:
                # Create new assessment record
                import uuid
                new_assessment_id = str(uuid.uuid4())
                
                # In production, this would create a RiskAssessment model instance
                logger.debug(f"Created new assessment {new_assessment_id}")
                
                return {
                    'assessment_id': new_assessment_id,
                    'created': True,
                    'token_address': token_address,
                    'pair_address': pair_address,
                    'risk_profile': risk_profile,
                    'created_at': timezone.now().isoformat()
                }
                
    except Exception as e:
        logger.error(f"Failed to create assessment record: {e}")
        # Generate fallback ID
        import uuid
        return {'assessment_id': str(uuid.uuid4()), 'created': False, 'error': str(e)}


def _execute_parallel_risk_checks(
    token_address: str, 
    pair_address: str, 
    risk_config: Dict[str, Any],
    include_advanced: bool
) -> List[Dict[str, Any]]:
    """
    Execute risk checks in parallel using Celery group.
    
    Args:
        token_address: Token contract address
        pair_address: Trading pair address
        risk_config: Risk profile configuration
        include_advanced: Whether to include advanced checks
        
    Returns:
        List of risk check results
    """
    try:
        from . import honeypot, liquidity, ownership
        
        # Build list of required checks
        required_checks = risk_config.get('required_checks', [])
        optional_checks = risk_config.get('optional_checks', []) if include_advanced else []
        
        # Create parallel task group
        task_list = []
        
        # Add required checks
        if 'HONEYPOT' in required_checks:
            task_list.append(
                honeypot.honeypot_check.s(
                    token_address, 
                    pair_address,
                    use_advanced_simulation=include_advanced
                )
            )
        
        if 'LIQUIDITY' in required_checks:
            task_list.append(
                liquidity.liquidity_check.s(
                    pair_address,
                    token_address,
                    risk_config.get('min_liquidity_usd', 10000),
                    risk_config.get('max_slippage_percent', 5.0)
                )
            )
        
        if 'OWNERSHIP' in required_checks:
            task_list.append(
                ownership.ownership_check.s(
                    token_address,
                    check_admin_functions=True,
                    check_timelock=include_advanced,
                    check_multisig=include_advanced
                )
            )
        
        # Add optional checks if advanced mode enabled
        if include_advanced:
            if 'TAX_ANALYSIS' in optional_checks:
                # Import taxation module when it's created
                pass  # taxation.tax_analysis.s(token_address, pair_address)
            
            if 'CONTRACT_SECURITY' in optional_checks:
                # Import security module when it's created
                pass  # security.security_check.s(token_address)
            
            if 'HOLDER_ANALYSIS' in optional_checks:
                # Import holders module when it's created  
                pass  # holders.holder_analysis.s(token_address)
        
        # Execute parallel checks with timeout
        if task_list:
            timeout = risk_config.get('timeout_seconds', 30)
            
            logger.info(f"Executing {len(task_list)} risk checks in parallel (timeout: {timeout}s)")
            
            parallel_job = group(task_list)
            result = parallel_job.apply_async()
            
            # Wait for results with timeout
            check_results = result.get(timeout=timeout)
            
            # Filter out None results
            check_results = [r for r in check_results if r is not None]
            
            logger.info(f"Completed {len(check_results)} parallel risk checks")
            return check_results
        else:
            logger.warning("No risk checks configured to run")
            return []
            
    except Exception as e:
        logger.error(f"Parallel risk check execution failed: {e}")
        # Fallback to sequential execution
        return _execute_sequential_risk_checks(token_address, pair_address, risk_config, include_advanced)


def _execute_sequential_risk_checks(
    token_address: str, 
    pair_address: str, 
    risk_config: Dict[str, Any],
    include_advanced: bool
) -> List[Dict[str, Any]]:
    """
    Execute risk checks sequentially (fallback method).
    
    Args:
        token_address: Token contract address
        pair_address: Trading pair address
        risk_config: Risk profile configuration
        include_advanced: Whether to include advanced checks
        
    Returns:
        List of risk check results
    """
    logger.info("Executing risk checks sequentially")
    
    results = []
    
    try:
        from . import honeypot, liquidity, ownership
        
        required_checks = risk_config.get('required_checks', [])
        
        # Execute each check individually
        if 'HONEYPOT' in required_checks:
            try:
                result = honeypot.honeypot_check(
                    token_address, pair_address, use_advanced_simulation=include_advanced
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Honeypot check failed: {e}")
                results.append(_create_failed_check_result('HONEYPOT', token_address, str(e)))
        
        if 'LIQUIDITY' in required_checks:
            try:
                result = liquidity.liquidity_check(
                    pair_address, token_address,
                    risk_config.get('min_liquidity_usd', 10000),
                    risk_config.get('max_slippage_percent', 5.0)
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Liquidity check failed: {e}")
                results.append(_create_failed_check_result('LIQUIDITY', token_address, str(e)))
        
        if 'OWNERSHIP' in required_checks:
            try:
                result = ownership.ownership_check(
                    token_address,
                    check_admin_functions=True,
                    check_timelock=include_advanced,
                    check_multisig=include_advanced
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Ownership check failed: {e}")
                results.append(_create_failed_check_result('OWNERSHIP', token_address, str(e)))
        
        logger.info(f"Completed {len(results)} sequential risk checks")
        return results
        
    except Exception as e:
        logger.error(f"Sequential risk check execution failed: {e}")
        return results  # Return partial results


def _analyze_and_finalize_assessment(
    assessment_id: str,
    token_address: str,
    pair_address: str,
    check_results: List[Dict[str, Any]],
    risk_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Analyze check results and create final assessment.
    
    Args:
        assessment_id: Assessment ID
        token_address: Token contract address
        pair_address: Trading pair address
        check_results: List of individual check results
        risk_config: Risk profile configuration
        
    Returns:
        Dict with final assessment
    """
    try:
        # Calculate overall risk score
        overall_risk_score, risk_level = calculate_weighted_risk_score(check_results)
        
        # Determine if trading should be blocked
        should_block, blocking_reasons = should_block_trading(check_results)
        
        # Apply risk profile specific rules
        profile_blocking = _apply_risk_profile_rules(check_results, risk_config)
        if profile_blocking['should_block']:
            should_block = True
            blocking_reasons.extend(profile_blocking['reasons'])
        
        # Determine trading decision
        max_acceptable_risk = risk_config.get('max_acceptable_risk', 30)
        
        if should_block:
            trading_decision = 'BLOCK'
            decision_reason = f"Blocked due to: {', '.join(blocking_reasons)}"
        elif overall_risk_score > max_acceptable_risk:
            trading_decision = 'SKIP'
            decision_reason = f"Risk score ({overall_risk_score}) exceeds maximum acceptable ({max_acceptable_risk})"
        else:
            trading_decision = 'APPROVE'
            decision_reason = f"Risk score ({overall_risk_score}) within acceptable range"
        
        # Calculate confidence score
        confidence_score = _calculate_confidence_score(check_results)
        
        # Generate AI thought log entry
        thought_log = _generate_thought_log_entry(
            token_address, check_results, overall_risk_score, trading_decision, decision_reason
        )
        
        # Compile final assessment
        final_assessment = {
            'assessment_id': assessment_id,
            'token_address': token_address,
            'pair_address': pair_address,
            'timestamp': timezone.now().isoformat(),
            
            # Overall results
            'overall_risk_score': float(overall_risk_score),
            'risk_level': risk_level,
            'confidence_score': confidence_score,
            
            # Trading decision
            'trading_decision': trading_decision,
            'decision_reason': decision_reason,
            'is_blocked': should_block,
            'blocking_reasons': blocking_reasons,
            
            # Individual check results
            'check_results': check_results,
            'checks_completed': len([r for r in check_results if r.get('status') == 'COMPLETED']),
            'checks_failed': len([r for r in check_results if r.get('status') == 'FAILED']),
            'checks_total': len(check_results),
            
            # Risk profile and configuration
            'risk_profile': risk_config,
            'profile_rules_applied': profile_blocking,
            
            # AI Thought Log
            'thought_log': thought_log,
            
            # Summary metrics
            'summary': _generate_assessment_summary(check_results, overall_risk_score, trading_decision)
        }
        
        return final_assessment
        
    except Exception as e:
        logger.error(f"Failed to analyze assessment results: {e}")
        return _create_failure_assessment(
            token_address, pair_address, assessment_id, f"Analysis failed: {str(e)}", 0
        )


def _apply_risk_profile_rules(
    check_results: List[Dict[str, Any]], 
    risk_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Apply risk profile specific blocking rules.
    
    Args:
        check_results: List of risk check results
        risk_config: Risk profile configuration
        
    Returns:
        Dict with profile-specific blocking decision
    """
    should_block = False
    reasons = []
    
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
        
        # Apply specific profile rules
        if risk_config.get('require_ownership_renounced'):
            ownership_result = next((r for r in check_results if r.get('check_type') == 'OWNERSHIP'), None)
            if ownership_result:
                details = ownership_result.get('details', {})
                ownership_info = details.get('ownership', {})
                if not ownership_info.get('is_renounced', False):
                    should_block = True
                    reasons.append("Ownership not renounced (required by profile)")
        
        # Check maximum sell tax
        max_sell_tax = risk_config.get('max_sell_tax_percent', 100)
        tax_result = next((r for r in check_results if r.get('check_type') == 'TAX_ANALYSIS'), None)
        if tax_result:
            details = tax_result.get('details', {})
            sell_tax = details.get('sell_tax_percent', 0)
            if sell_tax > max_sell_tax:
                should_block = True
                reasons.append(f"Sell tax ({sell_tax}%) exceeds maximum ({max_sell_tax}%)")
        
        # Check minimum liquidity
        min_liquidity = risk_config.get('min_liquidity_usd', 0)
        liquidity_result = next((r for r in check_results if r.get('check_type') == 'LIQUIDITY'), None)
        if liquidity_result:
            details = liquidity_result.get('details', {})
            total_liquidity = details.get('total_liquidity_usd', 0)
            if total_liquidity < min_liquidity:
                should_block = True
                reasons.append(f"Liquidity (${total_liquidity:,.2f}) below minimum (${min_liquidity:,.2f})")
        
        return {
            'should_block': should_block,
            'reasons': reasons,
            'rules_applied': len(blocking_thresholds) + (1 if risk_config.get('require_ownership_renounced') else 0)
        }
        
    except Exception as e:
        logger.error(f"Failed to apply risk profile rules: {e}")
        return {'should_block': False, 'reasons': [], 'error': str(e)}


def _calculate_confidence_score(check_results: List[Dict[str, Any]]) -> float:
    """
    Calculate confidence score based on check completion and reliability.
    
    Args:
        check_results: List of risk check results
        
    Returns:
        Confidence score from 0-100
    """
    if not check_results:
        return 0.0
    
    # Base confidence from completion rate
    completed_checks = len([r for r in check_results if r.get('status') == 'COMPLETED'])
    completion_rate = completed_checks / len(check_results)
    
    # Adjust for execution time (faster = more reliable)
    avg_execution_time = sum(r.get('execution_time_ms', 0) for r in check_results) / len(check_results)
    time_factor = max(0.5, 1.0 - (avg_execution_time / 10000))  # Reduce confidence if checks took >10s
    
    # Adjust for critical check completion
    critical_checks = ['HONEYPOT', 'LIQUIDITY', 'OWNERSHIP']
    critical_completed = len([
        r for r in check_results 
        if r.get('check_type') in critical_checks and r.get('status') == 'COMPLETED'
    ])
    critical_factor = critical_completed / len(critical_checks)
    
    # Calculate overall confidence
    confidence = (completion_rate * 0.4 + time_factor * 0.3 + critical_factor * 0.3) * 100
    
    return min(100.0, max(0.0, confidence))


def _generate_thought_log_entry(
    token_address: str,
    check_results: List[Dict[str, Any]],
    overall_risk_score: Decimal,
    trading_decision: str,
    decision_reason: str
) -> Dict[str, Any]:
    """
    Generate AI Thought Log entry for explainable decision making.
    
    Args:
        token_address: Token contract address
        check_results: List of risk check results
        overall_risk_score: Overall risk score
        trading_decision: Final trading decision
        decision_reason: Reason for the decision
        
    Returns:
        Dict with thought log entry
    """
    try:
        # Extract key signals from check results
        signals = []
        
        for result in check_results:
            check_type = result.get('check_type')
            status = result.get('status')
            risk_score = result.get('risk_score', 0)
            details = result.get('details', {})
            
            if status == 'COMPLETED':
                # Extract meaningful signals from each check
                if check_type == 'HONEYPOT':
                    if details.get('is_honeypot'):
                        signals.append(f"🚨 HONEYPOT DETECTED: Cannot sell after buying")
                    else:
                        sell_tax = details.get('sell_tax_percent', 0)
                        signals.append(f"✅ Not a honeypot, sell tax: {sell_tax}%")
                
                elif check_type == 'LIQUIDITY':
                    liquidity_usd = details.get('total_liquidity_usd', 0)
                    max_slippage = details.get('price_impact', {}).get('max_slippage', 0)
                    signals.append(f"💧 Liquidity: ${liquidity_usd:,.0f}, Max slippage: {max_slippage:.1f}%")
                
                elif check_type == 'OWNERSHIP':
                    ownership = details.get('ownership', {})
                    if ownership.get('is_renounced'):
                        signals.append(f"🔒 Ownership renounced")
                    else:
                        signals.append(f"⚠️ Owner: {ownership.get('owner_address', 'Unknown')}")
                
                elif check_type == 'TAX_ANALYSIS':
                    buy_tax = details.get('buy_tax_percent', 0)
                    sell_tax = details.get('sell_tax_percent', 0)
                    signals.append(f"💰 Taxes: Buy {buy_tax}%, Sell {sell_tax}%")
            
            elif status == 'FAILED':
                signals.append(f"❌ {check_type} check failed")
        
        # Generate narrative summary
        if trading_decision == 'APPROVE':
            narrative = f"Token passes safety checks with {overall_risk_score:.1f}/100 risk score. "
        elif trading_decision == 'SKIP':
            narrative = f"Token has elevated risk ({overall_risk_score:.1f}/100) but no critical issues. "
        else:  # BLOCK
            narrative = f"Token BLOCKED due to critical safety issues. "
        
        narrative += f"Key factors: {decision_reason}"
        
        # Generate counterfactuals
        counterfactuals = []
        
        for result in check_results:
            check_type = result.get('check_type')
            risk_score = result.get('risk_score', 0)
            details = result.get('details', {})
            
            if check_type == 'LIQUIDITY' and risk_score > 30:
                required_liquidity = details.get('min_required_usd', 0)
                current_liquidity = details.get('total_liquidity_usd', 0)
                if current_liquidity < required_liquidity:
                    counterfactuals.append(
                        f"Would trade if liquidity > ${required_liquidity:,.0f} "
                        f"(currently ${current_liquidity:,.0f})"
                    )
            
            if check_type == 'OWNERSHIP' and risk_score > 40:
                ownership = details.get('ownership', {})
                if not ownership.get('is_renounced'):
                    counterfactuals.append("Would trade if ownership was renounced")
        
        return {
            'timestamp': timezone.now().isoformat(),
            'token_address': token_address,
            'decision': trading_decision,
            'risk_score': float(overall_risk_score),
            'signals': signals,
            'narrative': narrative,
            'counterfactuals': counterfactuals,
            'reasoning_chain': [
                f"1. Executed {len(check_results)} risk checks",
                f"2. Calculated weighted risk score: {overall_risk_score:.1f}/100",
                f"3. Applied trading rules: {decision_reason}",
                f"4. Final decision: {trading_decision}"
            ]
        }
        
    except Exception as e:
        logger.error(f"Failed to generate thought log: {e}")
        return {
            'timestamp': timezone.now().isoformat(),
            'token_address': token_address,
            'decision': trading_decision,
            'error': str(e)
        }


def _generate_assessment_summary(
    check_results: List[Dict[str, Any]], 
    overall_risk_score: Decimal, 
    trading_decision: str
) -> Dict[str, Any]:
    """
    Generate a summary of the assessment for quick review.
    
    Args:
        check_results: List of risk check results
        overall_risk_score: Overall risk score
        trading_decision: Final trading decision
        
    Returns:
        Dict with assessment summary
    """
    try:
        # Count check outcomes
        completed = len([r for r in check_results if r.get('status') == 'COMPLETED'])
        failed = len([r for r in check_results if r.get('status') == 'FAILED'])
        warnings = len([r for r in check_results if r.get('status') == 'WARNING'])
        
        # Identify highest risk areas
        risk_areas = []
        for result in check_results:
            risk_score = result.get('risk_score', 0)
            if risk_score >= 70:
                risk_areas.append(f"{result.get('check_type')} ({risk_score:.0f})")
        
        # Generate recommendation
        if trading_decision == 'APPROVE':
            recommendation = "Safe to trade"
        elif trading_decision == 'SKIP':
            recommendation = "Consider manual review"
        else:
            recommendation = "Do not trade"
        
        return {
            'checks_summary': {
                'total': len(check_results),
                'completed': completed,
                'failed': failed,
                'warnings': warnings,
                'success_rate': f"{(completed / len(check_results) * 100):.1f}%" if check_results else "0%"
            },
            'risk_summary': {
                'overall_score': float(overall_risk_score),
                'risk_level': _score_to_risk_level(overall_risk_score),
                'high_risk_areas': risk_areas
            },
            'recommendation': recommendation,
            'key_points': _extract_key_points(check_results),
            'trade_readiness': trading_decision in ['APPROVE']
        }
        
    except Exception as e:
        logger.error(f"Failed to generate assessment summary: {e}")
        return {'error': str(e)}


def _extract_key_points(check_results: List[Dict[str, Any]]) -> List[str]:
    """Extract key points from check results for summary."""
    points = []
    
    try:
        for result in check_results:
            check_type = result.get('check_type')
            details = result.get('details', {})
            
            if check_type == 'HONEYPOT' and details.get('is_honeypot'):
                points.append("❌ Token is a honeypot")
            elif check_type == 'LIQUIDITY':
                liquidity = details.get('total_liquidity_usd', 0)
                if liquidity < 10000:
                    points.append(f"⚠️ Low liquidity: ${liquidity:,.0f}")
                else:
                    points.append(f"✅ Good liquidity: ${liquidity:,.0f}")
            elif check_type == 'OWNERSHIP':
                ownership = details.get('ownership', {})
                if ownership.get('is_renounced'):
                    points.append("✅ Ownership renounced")
                else:
                    points.append("⚠️ Owner still has control")
        
        return points[:5]  # Limit to top 5 points
        
    except Exception as e:
        logger.warning(f"Failed to extract key points: {e}")
        return []


def _score_to_risk_level(score: Decimal) -> str:
    """Convert risk score to risk level."""
    if score >= 80:
        return 'CRITICAL'
    elif score >= 60:
        return 'HIGH'
    elif score >= 30:
        return 'MEDIUM'
    else:
        return 'LOW'


def _create_failed_check_result(check_type: str, token_address: str, error_message: str) -> Dict[str, Any]:
    """Create a failed check result."""
    return create_risk_check_result(
        check_type=check_type,
        token_address=token_address,
        status='FAILED',
        risk_score=Decimal('100'),  # Maximum risk on failure
        error_message=error_message,
        execution_time_ms=0
    )


def _create_failure_assessment(
    token_address: str, 
    pair_address: str, 
    assessment_id: Optional[str], 
    error_message: str,
    execution_time_ms: float
) -> Dict[str, Any]:
    """Create a failure assessment when the entire process fails."""
    return {
        'assessment_id': assessment_id or 'failed',
        'token_address': token_address,
        'pair_address': pair_address,
        'timestamp': timezone.now().isoformat(),
        'overall_risk_score': 100.0,
        'risk_level': 'CRITICAL',
        'confidence_score': 0.0,
        'trading_decision': 'BLOCK',
        'decision_reason': f"Assessment failed: {error_message}",
        'is_blocked': True,
        'blocking_reasons': ['Assessment failure'],
        'check_results': [],
        'checks_completed': 0,
        'checks_failed': 0,
        'checks_total': 0,
        'execution_time_ms': execution_time_ms,
        'error': error_message,
        'thought_log': {
            'timestamp': timezone.now().isoformat(),
            'token_address': token_address,
            'decision': 'BLOCK',
            'narrative': f"Risk assessment failed with error: {error_message}",
            'signals': ['❌ Assessment system failure']
        }
    }


def _is_retryable_error(error: Exception) -> bool:
    """Determine if an error is worth retrying."""
    retryable_errors = [
        'ConnectionError',
        'TimeoutError',
        'TemporaryFailure',
        'RateLimitExceeded'
    ]
    
    error_type = type(error).__name__
    return any(retryable in error_type for retryable in retryable_errors)


def _store_final_assessment(assessment: Dict[str, Any]) -> None:
    """
    Store the final assessment in the database.
    
    Args:
        assessment: Final assessment dictionary
    """
    try:
        with transaction.atomic():
            # In production, this would:
            # 1. Create/update RiskAssessment model
            # 2. Store individual RiskCheckResult records
            # 3. Create RiskEvent if needed
            # 4. Update any related models
            
            assessment_id = assessment['assessment_id']
            token_address = assessment['token_address']
            
            logger.info(
                f"Storing assessment {assessment_id} for token {token_address} - "
                f"Decision: {assessment['trading_decision']}, "
                f"Risk: {assessment['overall_risk_score']}"
            )
            
            # Store check results
            for check_result in assessment.get('check_results', []):
                logger.debug(f"Storing {check_result.get('check_type')} result")
            
            # Store thought log entry
            thought_log = assessment.get('thought_log', {})
            if thought_log:
                logger.debug(f"Storing thought log entry")
            
    except Exception as e:
        logger.error(f"Failed to store final assessment: {e}")
        # Don't raise exception - assessment is complete even if storage fails


# Additional helper tasks for specific workflows

@shared_task(
    bind=True,
    queue='risk.urgent',
    name='risk.tasks.quick_honeypot_check',
    max_retries=2,
    default_retry_delay=1
)
def quick_honeypot_check(self, token_address: str, pair_address: str) -> Dict[str, Any]:
    """
    Quick honeypot-only check for time-critical decisions.
    
    Args:
        token_address: Token contract address
        pair_address: Trading pair address
        
    Returns:
        Dict with honeypot check result
    """
    try:
        from . import honeypot
        
        result = honeypot.honeypot_check(
            token_address, 
            pair_address, 
            use_advanced_simulation=False  # Skip advanced checks for speed
        )
        
        return {
            'check_type': 'QUICK_HONEYPOT',
            'token_address': token_address,
            'pair_address': pair_address,
            'is_honeypot': result.get('details', {}).get('is_honeypot', True),
            'risk_score': result.get('risk_score', 100),
            'status': result.get('status', 'FAILED'),
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=1)
        
        return {
            'check_type': 'QUICK_HONEYPOT',
            'token_address': token_address,
            'pair_address': pair_address,
            'is_honeypot': True,  # Assume honeypot on failure
            'risk_score': 100,
            'status': 'FAILED',
            'error': str(exc),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(
    bind=True,
    queue='analytics.background',
    name='risk.tasks.bulk_assessment',
    max_retries=1
)
def bulk_assessment(
    self, 
    token_pair_list: List[Tuple[str, str]], 
    risk_profile: str = 'Conservative'
) -> Dict[str, Any]:
    """
    Perform bulk risk assessment for multiple token pairs.
    
    Args:
        token_pair_list: List of (token_address, pair_address) tuples
        risk_profile: Risk profile to use for all assessments
        
    Returns:
        Dict with bulk assessment results
    """
    try:
        logger.info(f"Starting bulk assessment of {len(token_pair_list)} token pairs")
        
        results = []
        successful = 0
        failed = 0
        
        for token_address, pair_address in token_pair_list:
            try:
                # Call main assessment task
                result = assess_token_risk(
                    token_address=token_address,
                    pair_address=pair_address,
                    risk_profile=risk_profile,
                    parallel_execution=True,
                    include_advanced_checks=False  # Skip advanced for bulk processing
                )
                
                results.append(result)
                
                if result.get('trading_decision') != 'BLOCK':
                    successful += 1
                else:
                    failed += 1
                    
            except Exception as e:
                logger.error(f"Bulk assessment failed for {token_address}: {e}")
                failed += 1
                results.append({
                    'token_address': token_address,
                    'pair_address': pair_address,
                    'trading_decision': 'BLOCK',
                    'error': str(e)
                })
        
        return {
            'total_assessed': len(token_pair_list),
            'successful': successful,
            'failed': failed,
            'success_rate': f"{(successful / len(token_pair_list) * 100):.1f}%",
            'results': results,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Bulk assessment failed: {exc}")
        return {
            'total_assessed': len(token_pair_list),
            'successful': 0,
            'failed': len(token_pair_list),
            'error': str(exc),
            'timestamp': timezone.now().isoformat()
        }