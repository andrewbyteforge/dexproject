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
        logger.debug(f"Using risk profile: {risk_profile}")
        
        # Create assessment record
        assessment_record = _create_assessment_record(
            token_address, pair_address, assessment_id, risk_profile
        )
        
        # Execute risk checks (parallel or sequential)
        if parallel_execution:
            check_results = _execute_parallel_risk_checks(
                token_address, pair_address, risk_config, include_advanced_checks
            )
        else:
            check_results = _execute_sequential_risk_checks(
                token_address, pair_address, risk_config, include_advanced_checks
            )
        
        # Filter out failed checks and log issues
        successful_checks = []
        failed_checks = []
        
        for result in check_results:
            if result.get('status') in ['COMPLETED', 'WARNING']:
                successful_checks.append(result)
            else:
                failed_checks.append(result)
                logger.warning(f"Check {result.get('check_type')} failed: {result.get('error_message', 'Unknown error')}")
        
        # Calculate overall risk score
        overall_risk_score = _calculate_overall_risk_score(successful_checks, risk_config)
        
        # Determine risk level and trading decision
        risk_level = _determine_risk_level(overall_risk_score)
        trading_decision = _make_trading_decision(
            successful_checks, failed_checks, overall_risk_score, risk_config
        )
        
        # Calculate confidence score
        confidence_score = _calculate_confidence_score(successful_checks, failed_checks)
        
        # Generate thought log (AI reasoning)
        thought_log = _generate_thought_log(
            successful_checks, failed_checks, overall_risk_score, 
            trading_decision, risk_profile
        )
        
        # Generate summary
        summary = _generate_assessment_summary(
            successful_checks, failed_checks, overall_risk_score, 
            trading_decision, risk_profile
        )
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        # Prepare final result
        result = {
            'assessment_id': assessment_record['assessment_id'],
            'task_id': task_id,
            'token_address': token_address,
            'pair_address': pair_address,
            'risk_profile': risk_profile,
            'overall_risk_score': float(overall_risk_score),
            'risk_level': risk_level,
            'trading_decision': trading_decision,
            'confidence_score': float(confidence_score),
            'is_blocked': trading_decision == 'BLOCK',
            'check_results': successful_checks,
            'failed_checks': failed_checks,
            'checks_completed': len(successful_checks),
            'checks_failed': len(failed_checks),
            'thought_log': thought_log,
            'summary': summary,
            'execution_time_ms': execution_time_ms,
            'timestamp': timezone.now().isoformat(),
            'status': 'completed'
        }
        
        logger.info(f"Risk assessment completed for {token_address} in {execution_time_ms:.1f}ms - "
                   f"Decision: {trading_decision}, Risk: {overall_risk_score:.1f}, "
                   f"Confidence: {confidence_score:.1f}%")
        
        return result
        
    except Exception as exc:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"Risk assessment failed for {token_address}: {exc} (task: {task_id})")
        
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying risk assessment for {token_address} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=5 * (self.request.retries + 1))
        
        # Return safe fallback result on final failure
        return {
            'assessment_id': assessment_record.get('assessment_id', 'unknown') if 'assessment_record' in locals() else 'unknown',
            'task_id': task_id,
            'token_address': token_address,
            'pair_address': pair_address,
            'risk_profile': risk_profile,
            'overall_risk_score': 100.0,  # Maximum risk on failure
            'risk_level': 'CRITICAL',
            'trading_decision': 'BLOCK',
            'confidence_score': 0.0,
            'is_blocked': True,
            'check_results': [],
            'failed_checks': [],
            'checks_completed': 0,
            'checks_failed': 0,
            'error_message': str(exc),
            'execution_time_ms': execution_time_ms,
            'timestamp': timezone.now().isoformat(),
            'status': 'failed'
        }


@shared_task(
    bind=True,
    queue='risk.normal',
    name='risk.tasks.quick_honeypot_check',
    max_retries=2,
    default_retry_delay=2
)
def quick_honeypot_check(
    self,
    token_address: str,
    pair_address: str,
    timeout_seconds: int = 5
) -> Dict[str, Any]:
    """
    Perform a quick honeypot check for fast screening.
    
    This is a lightweight version of the full assessment that only
    checks for honeypot status to quickly filter out obvious scams.
    
    Args:
        token_address: The token contract address to check
        pair_address: The trading pair address
        timeout_seconds: Maximum time allowed for the check
        
    Returns:
        Dict with quick honeypot check result
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting quick honeypot check for token {token_address} (task: {task_id})")
    
    try:
        # Import honeypot module
        from . import honeypot
        
        # Execute honeypot check with timeout
        honeypot_result = honeypot.honeypot_check(
            token_address=token_address,
            pair_address=pair_address,
            use_advanced_simulation=False,  # Quick check only
            timeout_seconds=timeout_seconds
        )
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        # Extract key information
        is_honeypot = honeypot_result.get('details', {}).get('is_honeypot', True)
        can_sell = honeypot_result.get('details', {}).get('can_sell', False)
        risk_score = honeypot_result.get('risk_score', 100)
        
        result = {
            'task_id': task_id,
            'token_address': token_address,
            'pair_address': pair_address,
            'is_honeypot': is_honeypot,
            'can_sell': can_sell,
            'risk_score': risk_score,
            'decision': 'BLOCK' if is_honeypot else 'PROCEED',
            'execution_time_ms': execution_time_ms,
            'full_result': honeypot_result,
            'timestamp': timezone.now().isoformat(),
            'status': 'completed'
        }
        
        logger.info(f"Quick honeypot check completed for {token_address} in {execution_time_ms:.1f}ms - "
                   f"Honeypot: {is_honeypot}")
        
        return result
        
    except Exception as exc:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"Quick honeypot check failed for {token_address}: {exc} (task: {task_id})")
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2)
        
        return {
            'task_id': task_id,
            'token_address': token_address,
            'pair_address': pair_address,
            'is_honeypot': True,  # Assume honeypot on failure for safety
            'can_sell': False,
            'risk_score': 100.0,
            'decision': 'BLOCK',
            'error_message': str(exc),
            'execution_time_ms': execution_time_ms,
            'timestamp': timezone.now().isoformat(),
            'status': 'failed'
        }


@shared_task(
    bind=True,
    queue='risk.background',
    name='risk.tasks.bulk_assessment',
    max_retries=1,
    default_retry_delay=30
)
def bulk_assessment(
    self,
    token_pairs: List[Tuple[str, str]],
    risk_profile: str = 'Moderate',
    batch_size: int = 10,
    parallel_batches: bool = True
) -> Dict[str, Any]:
    """
    Perform bulk risk assessment for multiple token pairs.
    
    Efficiently processes multiple tokens with batching and parallel execution
    to avoid overwhelming the system while maintaining throughput.
    
    Args:
        token_pairs: List of (token_address, pair_address) tuples
        risk_profile: Risk profile to use for all assessments
        batch_size: Number of tokens to process per batch
        parallel_batches: Whether to process batches in parallel
        
    Returns:
        Dict with bulk assessment results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting bulk assessment for {len(token_pairs)} token pairs (task: {task_id})")
    
    try:
        results = []
        failed_assessments = []
        
        # Process in batches
        for i in range(0, len(token_pairs), batch_size):
            batch = token_pairs[i:i + batch_size]
            batch_number = i // batch_size + 1
            
            logger.info(f"Processing batch {batch_number} with {len(batch)} tokens")
            
            # Process batch
            batch_results = _process_assessment_batch(batch, risk_profile, parallel_batches)
            
            for result in batch_results:
                if result.get('status') == 'completed':
                    results.append(result)
                else:
                    failed_assessments.append(result)
            
            # Small delay between batches to prevent overwhelming
            if i + batch_size < len(token_pairs):
                time.sleep(0.1)
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        # Generate bulk summary
        summary = _generate_bulk_summary(results, failed_assessments)
        
        bulk_result = {
            'task_id': task_id,
            'total_tokens': len(token_pairs),
            'successful_assessments': len(results),
            'failed_assessments': len(failed_assessments),
            'risk_profile': risk_profile,
            'batch_size': batch_size,
            'results': results,
            'failed': failed_assessments,
            'summary': summary,
            'execution_time_ms': execution_time_ms,
            'timestamp': timezone.now().isoformat(),
            'status': 'completed'
        }
        
        logger.info(f"Bulk assessment completed in {execution_time_ms:.1f}ms - "
                   f"Success: {len(results)}, Failed: {len(failed_assessments)}")
        
        return bulk_result
        
    except Exception as exc:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"Bulk assessment failed: {exc} (task: {task_id})")
        
        return {
            'task_id': task_id,
            'total_tokens': len(token_pairs),
            'successful_assessments': 0,
            'failed_assessments': len(token_pairs),
            'error_message': str(exc),
            'execution_time_ms': execution_time_ms,
            'timestamp': timezone.now().isoformat(),
            'status': 'failed'
        }


# Helper functions for risk assessment coordination

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
        from . import honeypot, liquidity, ownership, tax
        
        # Build list of required checks
        required_checks = risk_config.get('required_checks', [])
        optional_checks = risk_config.get('optional_checks', []) if include_advanced else []
        all_checks = list(set(required_checks + optional_checks))
        
        # Create parallel task group
        task_list = []
        
        # Add checks based on configuration
        if 'HONEYPOT' in all_checks:
            task_list.append(
                honeypot.honeypot_check.s(
                    token_address, 
                    pair_address,
                    use_advanced_simulation=include_advanced
                )
            )
        
        if 'LIQUIDITY' in all_checks:
            task_list.append(
                liquidity.liquidity_check.s(
                    pair_address,
                    token_address,
                    risk_config.get('min_liquidity_usd', 10000),
                    risk_config.get('max_slippage_percent', 5.0)
                )
            )
        
        if 'OWNERSHIP' in all_checks:
            task_list.append(
                ownership.ownership_check.s(
                    token_address,
                    check_admin_functions=True,
                    check_timelock=include_advanced,
                    check_multisig=include_advanced
                )
            )
        
        if 'TAX_ANALYSIS' in all_checks:
            task_list.append(
                tax.tax_analysis.s(
                    token_address,
                    pair_address,
                    simulation_amount_usd=1000.0,
                    check_reflection=include_advanced,
                    check_antiwhale=include_advanced,
                    check_blacklist=include_advanced
                )
            )
        
        # Execute parallel checks with timeout
        if task_list:
            timeout = risk_config.get('timeout_seconds', 30)
            
            logger.info(f"Executing {len(task_list)} risk checks in parallel (timeout: {timeout}s)")
            
            parallel_job = group(task_list)
            result = parallel_job.apply_async()
            
            # Wait for results with timeout
            try:
                check_results = result.get(timeout=timeout)
                # Filter out None results
                check_results = [r for r in check_results if r is not None]
                
                logger.info(f"Completed {len(check_results)} parallel risk checks")
                return check_results
            except Exception as e:
                logger.warning(f"Parallel execution timeout or error: {e}")
                # Try to get partial results
                try:
                    check_results = result.get(timeout=5)  # Short timeout for partial results
                    return [r for r in check_results if r is not None]
                except:
                    # Fall back to sequential execution
                    return _execute_sequential_risk_checks(token_address, pair_address, risk_config, include_advanced)
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
        from . import honeypot, liquidity, ownership, tax
        
        required_checks = risk_config.get('required_checks', [])
        optional_checks = risk_config.get('optional_checks', []) if include_advanced else []
        all_checks = list(set(required_checks + optional_checks))
        
        # Execute checks one by one with individual error handling
        for check_type in all_checks:
            try:
                if check_type == 'HONEYPOT':
                    result = honeypot.honeypot_check(
                        token_address, pair_address, use_advanced_simulation=include_advanced
                    )
                elif check_type == 'LIQUIDITY':
                    result = liquidity.liquidity_check(
                        pair_address, token_address,
                        risk_config.get('min_liquidity_usd', 10000),
                        risk_config.get('max_slippage_percent', 5.0)
                    )
                elif check_type == 'OWNERSHIP':
                    result = ownership.ownership_check(
                        token_address, check_admin_functions=True,
                        check_timelock=include_advanced, check_multisig=include_advanced
                    )
                elif check_type == 'TAX_ANALYSIS':
                    result = tax.tax_analysis(
                        token_address, pair_address, simulation_amount_usd=1000.0,
                        check_reflection=include_advanced, check_antiwhale=include_advanced,
                        check_blacklist=include_advanced
                    )
                else:
                    logger.warning(f"Unknown check type: {check_type}")
                    continue
                
                if result:
                    results.append(result)
                    logger.debug(f"Completed {check_type} check")
                
            except Exception as e:
                logger.error(f"Sequential check {check_type} failed: {e}")
                # Create error result for failed check
                error_result = create_risk_check_result(
                    task_id='sequential',
                    check_type=check_type,
                    token_address=token_address,
                    pair_address=pair_address,
                    risk_score=100,  # Max risk on failure
                    status='FAILED',
                    error_message=str(e),
                    execution_time_ms=0
                )
                results.append(error_result)
        
        logger.info(f"Completed {len(results)} sequential risk checks")
        return results
        
    except Exception as e:
        logger.error(f"Sequential risk check execution failed: {e}")
        return []


def _calculate_overall_risk_score(check_results: List[Dict[str, Any]], risk_config: Dict[str, Any]) -> Decimal:
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
        return Decimal('100')  # Maximum risk if no checks completed
    
    # Weight factors for different check types
    check_weights = {
        'HONEYPOT': Decimal('0.35'),      # Highest weight - critical for scam detection
        'LIQUIDITY': Decimal('0.25'),     # High weight - affects trade execution
        'TAX_ANALYSIS': Decimal('0.20'),  # Medium weight - affects profitability
        'OWNERSHIP': Decimal('0.15'),     # Lower weight - affects long-term risk
        'CONTRACT_SECURITY': Decimal('0.05'),  # Lowest weight - additional security
    }
    
    total_weighted_score = Decimal('0')
    total_weight = Decimal('0')
    
    for result in check_results:
        check_type = result.get('check_type', 'UNKNOWN')
        risk_score = Decimal(str(result.get('risk_score', 100)))
        weight = check_weights.get(check_type, Decimal('0.1'))
        
        total_weighted_score += risk_score * weight
        total_weight += weight
    
    # Calculate weighted average
    if total_weight > 0:
        overall_score = total_weighted_score / total_weight
    else:
        overall_score = Decimal('100')
    
    return min(overall_score, Decimal('100'))


def _determine_risk_level(overall_risk_score: Decimal) -> str:
    """Determine risk level based on overall score."""
    if overall_risk_score >= 80:
        return 'CRITICAL'
    elif overall_risk_score >= 60:
        return 'HIGH'
    elif overall_risk_score >= 40:
        return 'MEDIUM'
    elif overall_risk_score >= 20:
        return 'LOW'
    else:
        return 'MINIMAL'


def _make_trading_decision(
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
    for check in successful_checks:
        check_type = check.get('check_type')
        if check_type == 'HONEYPOT':
            details = check.get('details', {})
            if details.get('is_honeypot', False):
                return 'BLOCK'  # Always block honeypots
    
    # Check profile-specific blocking rules
    blocking_decision = _apply_profile_blocking_rules(successful_checks, risk_config)
    if blocking_decision.get('should_block', False):
        return 'BLOCK'
    
    # Check if too many critical checks failed
    critical_checks_failed = len([c for c in failed_checks if c.get('check_type') in ['HONEYPOT', 'LIQUIDITY']])
    if critical_checks_failed >= 2:
        return 'BLOCK'  # Block if multiple critical checks failed
    
    # Make decision based on overall risk score
    if overall_risk_score >= 80:
        return 'BLOCK'
    elif overall_risk_score > max_acceptable_risk:
        return 'SKIP'  # Skip high-risk tokens
    else:
        return 'APPROVE'


def _apply_profile_blocking_rules(check_results: List[Dict[str, Any]], risk_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply profile-specific blocking rules.
    
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


def _calculate_confidence_score(successful_checks: List[Dict[str, Any]], failed_checks: List[Dict[str, Any]]) -> Decimal:
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
        return Decimal('0')
    
    # Base confidence from completion rate
    completion_rate = len(successful_checks) / total_checks
    base_confidence = Decimal(str(completion_rate * 80))  # Max 80 from completion
    
    # Bonus confidence for critical checks completing successfully
    critical_checks = ['HONEYPOT', 'LIQUIDITY']
    critical_completed = len([c for c in successful_checks if c.get('check_type') in critical_checks])
    critical_bonus = Decimal(str(critical_completed * 10))  # Max 20 bonus
    
    # Penalty for failed critical checks
    critical_failed = len([c for c in failed_checks if c.get('check_type') in critical_checks])
    critical_penalty = Decimal(str(critical_failed * 15))  # 15 point penalty per failed critical check
    
    final_confidence = base_confidence + critical_bonus - critical_penalty
    return max(Decimal('0'), min(final_confidence, Decimal('100')))


def _generate_thought_log(
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
        Dict with thought log
    """
    # Analyze key signals
    signals = []
    
    # Honeypot analysis
    honeypot_result = next((c for c in successful_checks if c.get('check_type') == 'HONEYPOT'), None)
    if honeypot_result:
        details = honeypot_result.get('details', {})
        if details.get('is_honeypot', False):
            signals.append("🚨 HONEYPOT DETECTED - Cannot sell tokens")
        elif details.get('can_sell', True):
            signals.append("✅ Can buy and sell - Not a honeypot")
        
        buy_tax = details.get('buy_tax_percent', 0)
        sell_tax = details.get('sell_tax_percent', 0)
        if buy_tax > 10 or sell_tax > 10:
            signals.append(f"⚠️ High taxes: Buy {buy_tax}%, Sell {sell_tax}%")
    
    # Liquidity analysis
    liquidity_result = next((c for c in successful_checks if c.get('check_type') == 'LIQUIDITY'), None)
    if liquidity_result:
        details = liquidity_result.get('details', {})
        total_liquidity = details.get('total_liquidity_usd', 0)
        if total_liquidity >= 100000:
            signals.append(f"✅ Strong liquidity: ${total_liquidity:,.0f}")
        elif total_liquidity >= 50000:
            signals.append(f"✅ Good liquidity: ${total_liquidity:,.0f}")
        elif total_liquidity >= 10000:
            signals.append(f"⚠️ Medium liquidity: ${total_liquidity:,.0f}")
        else:
            signals.append(f"🚨 Low liquidity: ${total_liquidity:,.0f}")
    
    # Ownership analysis
    ownership_result = next((c for c in successful_checks if c.get('check_type') == 'OWNERSHIP'), None)
    if ownership_result:
        details = ownership_result.get('details', {})
        ownership = details.get('ownership', {})
        if ownership.get('is_renounced', False):
            signals.append("✅ Ownership renounced - Reduced rug risk")
        elif ownership.get('has_owner', False):
            signals.append("⚠️ Owner can still control contract")
    
    # Tax analysis
    tax_result = next((c for c in successful_checks if c.get('check_type') == 'TAX_ANALYSIS'), None)
    if tax_result:
        details = tax_result.get('details', {})
        if details.get('has_transfer_restrictions', False):
            signals.append("⚠️ Transfer restrictions detected")
        
        max_tax = details.get('max_tax_percent', 0)
        if max_tax > 20:
            signals.append(f"🚨 Very high taxes: {max_tax}%")
        elif max_tax > 10:
            signals.append(f"⚠️ High taxes: {max_tax}%")
    
    # Generate narrative
    narrative_parts = []
    
    if trading_decision == 'APPROVE':
        narrative_parts.append(f"✅ APPROVED for trading under {risk_profile} profile.")
        narrative_parts.append(f"Risk score of {overall_risk_score:.1f} is within acceptable range.")
    elif trading_decision == 'SKIP':
        narrative_parts.append(f"⚠️ SKIPPING token due to elevated risk.")
        narrative_parts.append(f"Risk score of {overall_risk_score:.1f} exceeds {risk_profile} profile limits.")
    else:  # BLOCK
        narrative_parts.append(f"🚨 BLOCKING token due to critical risks detected.")
        narrative_parts.append(f"Risk score of {overall_risk_score:.1f} indicates unsafe trading conditions.")
    
    if failed_checks:
        narrative_parts.append(f"Note: {len(failed_checks)} checks failed to complete.")
    
    return {
        'timestamp': timezone.now().isoformat(),
        'decision': trading_decision,
        'risk_score': float(overall_risk_score),
        'risk_profile': risk_profile,
        'signals': signals,
        'narrative': ' '.join(narrative_parts),
        'checks_completed': len(successful_checks),
        'checks_failed': len(failed_checks)
    }


def _generate_assessment_summary(
    successful_checks: List[Dict[str, Any]], 
    failed_checks: List[Dict[str, Any]], 
    overall_risk_score: Decimal, 
    trading_decision: str, 
    risk_profile: str
) -> Dict[str, Any]:
    """
    Generate summary of the assessment results.
    
    Args:
        successful_checks: Successful check results
        failed_checks: Failed check results
        overall_risk_score: Overall risk score
        trading_decision: Final trading decision
        risk_profile: Risk profile used
        
    Returns:
        Dict with assessment summary
    """
    # Summarize checks
    checks_summary = {}
    for check in successful_checks:
        check_type = check.get('check_type')
        checks_summary[check_type] = {
            'status': check.get('status', 'UNKNOWN'),
            'risk_score': check.get('risk_score', 0),
            'execution_time_ms': check.get('execution_time_ms', 0)
        }
    
    for check in failed_checks:
        check_type = check.get('check_type')
        checks_summary[check_type] = {
            'status': 'FAILED',
            'error': check.get('error_message', 'Unknown error'),
            'execution_time_ms': check.get('execution_time_ms', 0)
        }
    
    # Risk summary
    risk_level = _determine_risk_level(overall_risk_score)
    risk_summary = {
        'overall_score': float(overall_risk_score),
        'risk_level': risk_level,
        'profile_used': risk_profile,
        'within_tolerance': overall_risk_score <= 50,  # General tolerance
    }
    
    # Recommendation
    recommendation = {
        'action': trading_decision,
        'confidence': 'HIGH' if len(failed_checks) == 0 else 'MEDIUM' if len(failed_checks) <= 1 else 'LOW',
        'reasoning': _get_decision_reasoning(trading_decision, overall_risk_score, successful_checks)
    }
    
    return {
        'checks_summary': checks_summary,
        'risk_summary': risk_summary,
        'recommendation': recommendation,
        'total_checks': len(successful_checks) + len(failed_checks),
        'successful_checks': len(successful_checks),
        'failed_checks': len(failed_checks)
    }


def _get_decision_reasoning(trading_decision: str, overall_risk_score: Decimal, successful_checks: List[Dict[str, Any]]) -> str:
    """Get human-readable reasoning for the trading decision."""
    if trading_decision == 'APPROVE':
        return f"Low risk score ({overall_risk_score:.1f}) and no critical issues detected. Safe to trade."
    elif trading_decision == 'SKIP':
        return f"Moderate risk score ({overall_risk_score:.1f}) suggests caution. Consider manual review."
    else:  # BLOCK
        # Find specific blocking reasons
        honeypot_check = next((c for c in successful_checks if c.get('check_type') == 'HONEYPOT'), None)
        if honeypot_check and honeypot_check.get('details', {}).get('is_honeypot', False):
            return "Honeypot detected - tokens cannot be sold. Avoid trading."
        
        return f"High risk score ({overall_risk_score:.1f}) indicates dangerous trading conditions. Do not trade."


def _process_assessment_batch(
    token_pairs: List[Tuple[str, str]], 
    risk_profile: str, 
    parallel_batches: bool
) -> List[Dict[str, Any]]:
    """Process a batch of token assessments."""
    batch_results = []
    
    try:
        if parallel_batches and len(token_pairs) > 1:
            # Process batch in parallel
            assessment_tasks = []
            for token_address, pair_address in token_pairs:
                task = assess_token_risk.s(
                    token_address=token_address,
                    pair_address=pair_address,
                    risk_profile=risk_profile,
                    parallel_execution=False,  # Avoid nested parallelism
                    include_advanced_checks=False  # Quick assessment for bulk
                )
                assessment_tasks.append(task)
            
            # Execute batch
            batch_job = group(assessment_tasks)
            results = batch_job.apply_async()
            batch_results = results.get(timeout=60)  # 1 minute timeout per batch
            
        else:
            # Process batch sequentially
            for token_address, pair_address in token_pairs:
                try:
                    result = assess_token_risk(
                        token_address=token_address,
                        pair_address=pair_address,
                        risk_profile=risk_profile,
                        parallel_execution=False,
                        include_advanced_checks=False
                    )
                    batch_results.append(result)
                except Exception as e:
                    # Create error result for failed assessment
                    error_result = {
                        'token_address': token_address,
                        'pair_address': pair_address,
                        'status': 'failed',
                        'error_message': str(e),
                        'overall_risk_score': 100.0,
                        'trading_decision': 'BLOCK'
                    }
                    batch_results.append(error_result)
    
    except Exception as e:
        logger.error(f"Batch processing failed: {e}")
        # Create error results for all tokens in batch
        for token_address, pair_address in token_pairs:
            error_result = {
                'token_address': token_address,
                'pair_address': pair_address,
                'status': 'failed',
                'error_message': str(e),
                'overall_risk_score': 100.0,
                'trading_decision': 'BLOCK'
            }
            batch_results.append(error_result)
    
    return batch_results


def _generate_bulk_summary(results: List[Dict[str, Any]], failed_assessments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate summary for bulk assessment results."""
    total_tokens = len(results) + len(failed_assessments)
    
    if not results:
        return {
            'total_processed': total_tokens,
            'success_rate': 0.0,
            'trading_decisions': {'BLOCK': total_tokens},
            'risk_distribution': {'CRITICAL': total_tokens},
            'average_risk_score': 100.0
        }
    
    # Analyze trading decisions
    decisions = {}
    for result in results:
        decision = result.get('trading_decision', 'BLOCK')
        decisions[decision] = decisions.get(decision, 0) + 1
    
    # Add failed assessments as BLOCK
    decisions['BLOCK'] = decisions.get('BLOCK', 0) + len(failed_assessments)
    
    # Analyze risk distribution
    risk_levels = {}
    total_risk_score = 0
    
    for result in results:
        risk_score = result.get('overall_risk_score', 100)
        total_risk_score += risk_score
        
        if risk_score >= 80:
            level = 'CRITICAL'
        elif risk_score >= 60:
            level = 'HIGH'
        elif risk_score >= 40:
            level = 'MEDIUM'
        elif risk_score >= 20:
            level = 'LOW'
        else:
            level = 'MINIMAL'
        
        risk_levels[level] = risk_levels.get(level, 0) + 1
    
    # Add failed assessments as CRITICAL
    risk_levels['CRITICAL'] = risk_levels.get('CRITICAL', 0) + len(failed_assessments)
    total_risk_score += len(failed_assessments) * 100
    
    average_risk_score = total_risk_score / total_tokens if total_tokens > 0 else 100.0
    success_rate = len(results) / total_tokens if total_tokens > 0 else 0.0
    
    return {
        'total_processed': total_tokens,
        'successful_assessments': len(results),
        'failed_assessments': len(failed_assessments),
        'success_rate': success_rate,
        'trading_decisions': decisions,
        'risk_distribution': risk_levels,
        'average_risk_score': average_risk_score,
        'approved_tokens': decisions.get('APPROVE', 0),
        'blocked_tokens': decisions.get('BLOCK', 0),
        'skipped_tokens': decisions.get('SKIP', 0)
    }