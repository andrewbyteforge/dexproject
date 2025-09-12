"""
Risk assessment tasks module (refactored coordinator).

Main Celery task definitions for risk assessment system.
This replaces the original coordinator.py with a cleaner, modular structure.

File: risk/tasks/tasks.py
"""

import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from celery import shared_task
from django.utils import timezone

# Import the new modular components
from .profiles import get_risk_profile_config, validate_risk_profile
from .execution import execute_parallel_risk_checks, execute_sequential_risk_checks, get_execution_strategy
from .scoring import calculate_overall_risk_score, determine_risk_level, make_trading_decision, calculate_confidence_score
from .reporting import generate_thought_log, generate_assessment_summary
from .batch import process_assessment_batch, generate_bulk_summary, split_into_batches
from .database import create_assessment_record, save_assessment_result, create_risk_event

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
        
        if not validate_risk_profile(risk_profile):
            logger.warning(f"Invalid risk profile '{risk_profile}', using Conservative")
            risk_profile = 'Conservative'
        
        # Get risk profile configuration
        risk_config = get_risk_profile_config(risk_profile)
        logger.debug(f"Using risk profile: {risk_profile}")
        
        # Create assessment record in database
        assessment_record = create_assessment_record(
            token_address, pair_address, assessment_id, risk_profile
        )
        
        # Determine execution strategy
        execution_strategy = get_execution_strategy(risk_config, include_advanced_checks, not parallel_execution)
        logger.debug(f"Execution strategy: {execution_strategy['strategy']} ({execution_strategy['reason']})")
        
        # Execute risk checks based on strategy
        if execution_strategy['strategy'] == 'parallel':
            check_results = execute_parallel_risk_checks(
                token_address, pair_address, risk_config, include_advanced_checks
            )
        else:
            check_results = execute_sequential_risk_checks(
                token_address, pair_address, risk_config, include_advanced_checks
            )
        
        # Separate successful and failed checks
        successful_checks = [r for r in check_results if r.get('status') in ['COMPLETED', 'WARNING']]
        failed_checks = [r for r in check_results if r.get('status') not in ['COMPLETED', 'WARNING']]
        
        # Log check completion status
        for result in failed_checks:
            logger.warning(f"Check {result.get('check_type')} failed: {result.get('error_message', 'Unknown error')}")
        
        # Calculate overall risk score
        overall_risk_score = calculate_overall_risk_score(successful_checks, risk_config)
        
        # Determine risk level and trading decision
        risk_level = determine_risk_level(overall_risk_score)
        trading_decision = make_trading_decision(
            successful_checks, failed_checks, overall_risk_score, risk_config
        )
        
        # Calculate confidence score
        confidence_score = calculate_confidence_score(successful_checks, failed_checks)
        
        # Generate thought log and summary
        thought_log = generate_thought_log(
            successful_checks, failed_checks, overall_risk_score, 
            trading_decision, risk_profile
        )
        
        summary = generate_assessment_summary(
            successful_checks, failed_checks, overall_risk_score, 
            trading_decision, risk_profile
        )
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        # Create final result
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
        
        # Save result to database
        save_assessment_result(assessment_record['assessment_id'], result)
        
        # Create risk event if high risk detected
        if trading_decision == 'BLOCK' and overall_risk_score >= 80:
            create_risk_event(
                token_address=token_address,
                event_type='HIGH_RISK_DETECTED',
                severity='HIGH',
                description=f'Token blocked with risk score {overall_risk_score:.1f}',
                metadata={'assessment_id': assessment_record['assessment_id'], 'risk_score': float(overall_risk_score)}
            )
        
        logger.info(f"Risk assessment completed for {token_address} in {execution_time_ms:.1f}ms - "
                   f"Decision: {trading_decision}, Risk: {overall_risk_score:.1f}, "
                   f"Confidence: {confidence_score:.1f}%")
        
        return result
        
    except Exception as exc:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"Risk assessment failed for {token_address}: {exc} (task: {task_id})")
        
        # Retry logic
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying risk assessment for {token_address} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=5 * (self.request.retries + 1))
        
        # Create risk event for assessment failure
        create_risk_event(
            token_address=token_address,
            event_type='ASSESSMENT_FAILED',
            severity='MEDIUM',
            description=f'Risk assessment failed: {str(exc)}',
            metadata={'task_id': task_id, 'error': str(exc)}
        )
        
        # Return safe fallback result on final failure
        fallback_assessment_id = assessment_record.get('assessment_id', 'unknown') if 'assessment_record' in locals() else 'unknown'
        
        return {
            'assessment_id': fallback_assessment_id,
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
        
        # Create risk event if honeypot detected
        if is_honeypot:
            create_risk_event(
                token_address=token_address,
                event_type='HONEYPOT_DETECTED',
                severity='CRITICAL',
                description='Quick scan detected honeypot token',
                metadata={'task_id': task_id, 'can_sell': can_sell}
            )
        
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
        
        # Create risk event for check failure
        create_risk_event(
            token_address=token_address,
            event_type='HONEYPOT_CHECK_FAILED',
            severity='MEDIUM',
            description=f'Quick honeypot check failed: {str(exc)}',
            metadata={'task_id': task_id, 'error': str(exc)}
        )
        
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
        # Validate risk profile
        if not validate_risk_profile(risk_profile):
            logger.warning(f"Invalid risk profile '{risk_profile}', using Moderate")
            risk_profile = 'Moderate'
        
        # Split into manageable batches
        batches = split_into_batches(token_pairs, batch_size)
        
        results = []
        failed_assessments = []
        
        # Process each batch
        for i, batch in enumerate(batches):
            batch_number = i + 1
            logger.info(f"Processing batch {batch_number}/{len(batches)} with {len(batch)} tokens")
            
            # Process batch
            batch_results = process_assessment_batch(batch, risk_profile, parallel_batches, batch_size)
            
            # Categorize results
            for result in batch_results:
                if result.get('status') == 'completed':
                    results.append(result)
                else:
                    failed_assessments.append(result)
            
            # Small delay between batches to prevent overwhelming
            if i + 1 < len(batches):
                time.sleep(0.1)
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        # Generate bulk summary
        summary = generate_bulk_summary(results, failed_assessments)
        
        bulk_result = {
            'task_id': task_id,
            'total_tokens': len(token_pairs),
            'successful_assessments': len(results),
            'failed_assessments': len(failed_assessments),
            'risk_profile': risk_profile,
            'batch_size': batch_size,
            'total_batches': len(batches),
            'results': results,
            'failed': failed_assessments,
            'summary': summary,
            'execution_time_ms': execution_time_ms,
            'timestamp': timezone.now().isoformat(),
            'status': 'completed'
        }
        
        # Save bulk summary to database
        from .database import save_bulk_assessment_summary
        save_bulk_assessment_summary(summary, task_id)
        
        # Create risk event if many failures
        failure_rate = len(failed_assessments) / len(token_pairs)
        if failure_rate > 0.5:
            create_risk_event(
                token_address='BULK_ASSESSMENT',
                event_type='HIGH_BULK_FAILURE_RATE',
                severity='MEDIUM',
                description=f'Bulk assessment had {failure_rate:.1%} failure rate',
                metadata={'task_id': task_id, 'failure_rate': failure_rate}
            )
        
        logger.info(f"Bulk assessment completed in {execution_time_ms:.1f}ms - "
                   f"Success: {len(results)}, Failed: {len(failed_assessments)}")
        
        return bulk_result
        
    except Exception as exc:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"Bulk assessment failed: {exc} (task: {task_id})")
        
        # Create risk event for bulk failure
        create_risk_event(
            token_address='BULK_ASSESSMENT',
            event_type='BULK_ASSESSMENT_FAILED',
            severity='HIGH',
            description=f'Bulk assessment completely failed: {str(exc)}',
            metadata={'task_id': task_id, 'error': str(exc)}
        )
        
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


# Health check and monitoring tasks

@shared_task(
    bind=True,
    queue='risk.normal',
    name='risk.tasks.system_health_check'
)
def system_health_check(self) -> Dict[str, Any]:
    """
    Perform system health check for risk assessment components.
    
    Returns:
        Dict with health check results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting system health check (task: {task_id})")
    
    health_status = {
        'task_id': task_id,
        'overall_status': 'HEALTHY',
        'checks': {},
        'timestamp': timezone.now().isoformat()
    }
    
    try:
        # Check database connectivity
        try:
            from .database import get_assessment_statistics
            stats = get_assessment_statistics(1)  # Last 1 day
            health_status['checks']['database'] = {
                'status': 'HEALTHY',
                'response_time_ms': 50,  # Placeholder
                'last_assessment_count': stats.get('total_assessments', 0)
            }
        except Exception as e:
            health_status['checks']['database'] = {
                'status': 'UNHEALTHY',
                'error': str(e)
            }
            health_status['overall_status'] = 'DEGRADED'
        
        # Check profile configuration
        try:
            from .profiles import get_available_profiles
            profiles = get_available_profiles()
            health_status['checks']['profiles'] = {
                'status': 'HEALTHY',
                'available_profiles': profiles,
                'profile_count': len(profiles)
            }
        except Exception as e:
            health_status['checks']['profiles'] = {
                'status': 'UNHEALTHY',
                'error': str(e)
            }
            health_status['overall_status'] = 'DEGRADED'
        
        # Check individual risk modules (basic import test)
        risk_modules = ['honeypot', 'liquidity', 'ownership', 'tax']
        module_status = {}
        
        for module_name in risk_modules:
            try:
                exec(f"from . import {module_name}")
                module_status[module_name] = 'AVAILABLE'
            except Exception as e:
                module_status[module_name] = f'UNAVAILABLE: {str(e)}'
                health_status['overall_status'] = 'DEGRADED'
        
        health_status['checks']['risk_modules'] = {
            'status': 'HEALTHY' if all(status == 'AVAILABLE' for status in module_status.values()) else 'DEGRADED',
            'modules': module_status
        }
        
        execution_time_ms = (time.time() - start_time) * 1000
        health_status['execution_time_ms'] = execution_time_ms
        
        logger.info(f"System health check completed in {execution_time_ms:.1f}ms - Status: {health_status['overall_status']}")
        
        return health_status
        
    except Exception as exc:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"System health check failed: {exc}")
        
        return {
            'task_id': task_id,
            'overall_status': 'UNHEALTHY',
            'error_message': str(exc),
            'execution_time_ms': execution_time_ms,
            'timestamp': timezone.now().isoformat()
        }