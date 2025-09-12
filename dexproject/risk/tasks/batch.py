"""
Bulk assessment processing module.

Handles batch processing of multiple token assessments with
efficient batching, parallel execution, and result aggregation.

File: risk/tasks/batch.py
"""

import logging
import time
from typing import Dict, Any, List, Tuple
from celery import group

logger = logging.getLogger(__name__)


def process_assessment_batch(
    token_pairs: List[Tuple[str, str]], 
    risk_profile: str, 
    parallel_batches: bool,
    batch_size: int = 10
) -> List[Dict[str, Any]]:
    """
    Process a batch of token assessments efficiently.
    
    Args:
        token_pairs: List of (token_address, pair_address) tuples
        risk_profile: Risk profile to use for all assessments
        parallel_batches: Whether to process batch items in parallel
        batch_size: Maximum number of tokens per batch
        
    Returns:
        List of assessment results
    """
    if not token_pairs:
        logger.warning("No token pairs provided for batch processing")
        return []
    
    # Ensure batch doesn't exceed size limit
    if len(token_pairs) > batch_size:
        logger.warning(f"Batch size ({len(token_pairs)}) exceeds limit ({batch_size}), truncating")
        token_pairs = token_pairs[:batch_size]
    
    batch_results = []
    
    try:
        if parallel_batches and len(token_pairs) > 1:
            # Process batch in parallel
            logger.info(f"Processing {len(token_pairs)} tokens in parallel")
            batch_results = _process_parallel_batch(token_pairs, risk_profile)
        else:
            # Process batch sequentially
            logger.info(f"Processing {len(token_pairs)} tokens sequentially")
            batch_results = _process_sequential_batch(token_pairs, risk_profile)
        
        logger.info(f"Completed batch processing: {len(batch_results)} results")
        return batch_results
        
    except Exception as e:
        logger.error(f"Batch processing failed: {e}")
        # Create error results for all tokens in batch
        return _create_batch_error_results(token_pairs, str(e))


def generate_bulk_summary(
    results: List[Dict[str, Any]], 
    failed_assessments: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Generate comprehensive summary for bulk assessment results.
    
    Args:
        results: List of successful assessment results
        failed_assessments: List of failed assessment results
        
    Returns:
        Dict with bulk assessment summary
    """
    total_tokens = len(results) + len(failed_assessments)
    
    if total_tokens == 0:
        return _create_empty_bulk_summary()
    
    # Analyze trading decisions
    decision_counts = _count_trading_decisions(results, failed_assessments)
    
    # Analyze risk distribution
    risk_distribution = _analyze_risk_distribution(results, failed_assessments)
    
    # Calculate performance metrics
    performance_metrics = _calculate_bulk_performance_metrics(results, failed_assessments)
    
    # Generate insights
    insights = _generate_bulk_insights(results, failed_assessments, decision_counts)
    
    success_rate = len(results) / total_tokens if total_tokens > 0 else 0.0
    
    return {
        'total_processed': total_tokens,
        'successful_assessments': len(results),
        'failed_assessments': len(failed_assessments),
        'success_rate': success_rate,
        'trading_decisions': decision_counts,
        'risk_distribution': risk_distribution,
        'performance_metrics': performance_metrics,
        'insights': insights,
        'summary_timestamp': time.time()
    }


def split_into_batches(
    token_pairs: List[Tuple[str, str]], 
    batch_size: int
) -> List[List[Tuple[str, str]]]:
    """
    Split token pairs into smaller batches for processing.
    
    Args:
        token_pairs: List of token pair tuples
        batch_size: Maximum size per batch
        
    Returns:
        List of batches
    """
    if batch_size <= 0:
        raise ValueError("Batch size must be positive")
    
    batches = []
    for i in range(0, len(token_pairs), batch_size):
        batch = token_pairs[i:i + batch_size]
        batches.append(batch)
    
    logger.debug(f"Split {len(token_pairs)} tokens into {len(batches)} batches")
    return batches


def _process_parallel_batch(
    token_pairs: List[Tuple[str, str]], 
    risk_profile: str
) -> List[Dict[str, Any]]:
    """Process batch in parallel using Celery group."""
    from .tasks import assess_token_risk
    
    # Create parallel task group
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
    
    # Execute batch with timeout
    batch_job = group(assessment_tasks)
    try:
        results = batch_job.apply_async()
        batch_results = results.get(timeout=60)  # 1 minute timeout per batch
        
        # Filter out None results
        return [r for r in batch_results if r is not None]
        
    except Exception as e:
        logger.error(f"Parallel batch execution failed: {e}")
        return _create_batch_error_results(token_pairs, str(e))


def _process_sequential_batch(
    token_pairs: List[Tuple[str, str]], 
    risk_profile: str
) -> List[Dict[str, Any]]:
    """Process batch sequentially."""
    from .tasks import assess_token_risk
    
    batch_results = []
    
    for i, (token_address, pair_address) in enumerate(token_pairs):
        try:
            logger.debug(f"Processing token {i+1}/{len(token_pairs)}: {token_address}")
            
            result = assess_token_risk(
                token_address=token_address,
                pair_address=pair_address,
                risk_profile=risk_profile,
                parallel_execution=False,
                include_advanced_checks=False
            )
            
            if result:
                batch_results.append(result)
            else:
                logger.warning(f"No result for token {token_address}")
                
        except Exception as e:
            logger.error(f"Failed to assess token {token_address}: {e}")
            # Create error result for failed assessment
            error_result = _create_error_result(token_address, pair_address, str(e))
            batch_results.append(error_result)
    
    return batch_results


def _create_batch_error_results(
    token_pairs: List[Tuple[str, str]], 
    error_message: str
) -> List[Dict[str, Any]]:
    """Create error results for all tokens in a failed batch."""
    error_results = []
    
    for token_address, pair_address in token_pairs:
        error_result = _create_error_result(token_address, pair_address, error_message)
        error_results.append(error_result)
    
    return error_results


def _create_error_result(token_address: str, pair_address: str, error_message: str) -> Dict[str, Any]:
    """Create a standardized error result."""
    return {
        'token_address': token_address,
        'pair_address': pair_address,
        'status': 'failed',
        'error_message': error_message,
        'overall_risk_score': 100.0,
        'trading_decision': 'BLOCK',
        'is_blocked': True,
        'check_results': [],
        'failed_checks': [],
        'checks_completed': 0,
        'checks_failed': 0,
        'confidence_score': 0.0,
        'execution_time_ms': 0.0,
        'timestamp': time.time()
    }


def _create_empty_bulk_summary() -> Dict[str, Any]:
    """Create summary for empty bulk assessment."""
    return {
        'total_processed': 0,
        'successful_assessments': 0,
        'failed_assessments': 0,
        'success_rate': 0.0,
        'trading_decisions': {'BLOCK': 0},
        'risk_distribution': {'CRITICAL': 0},
        'performance_metrics': {
            'average_execution_time_ms': 0.0,
            'total_execution_time_ms': 0.0,
            'tokens_per_second': 0.0
        },
        'insights': ['No tokens processed'],
        'summary_timestamp': time.time()
    }


def _count_trading_decisions(
    results: List[Dict[str, Any]], 
    failed_assessments: List[Dict[str, Any]]
) -> Dict[str, int]:
    """Count trading decisions across all results."""
    decisions = {'APPROVE': 0, 'SKIP': 0, 'BLOCK': 0}
    
    # Count successful assessments
    for result in results:
        decision = result.get('trading_decision', 'BLOCK')
        decisions[decision] = decisions.get(decision, 0) + 1
    
    # All failed assessments are blocked
    decisions['BLOCK'] += len(failed_assessments)
    
    return decisions


def _analyze_risk_distribution(
    results: List[Dict[str, Any]], 
    failed_assessments: List[Dict[str, Any]]
) -> Dict[str, int]:
    """Analyze risk level distribution across results."""
    risk_levels = {'MINIMAL': 0, 'LOW': 0, 'MEDIUM': 0, 'HIGH': 0, 'CRITICAL': 0}
    
    # Analyze successful assessments
    for result in results:
        risk_score = result.get('overall_risk_score', 100)
        
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
        
        risk_levels[level] += 1
    
    # All failed assessments are critical risk
    risk_levels['CRITICAL'] += len(failed_assessments)
    
    return risk_levels


def _calculate_bulk_performance_metrics(
    results: List[Dict[str, Any]], 
    failed_assessments: List[Dict[str, Any]]
) -> Dict[str, float]:
    """Calculate performance metrics for bulk assessment."""
    all_results = results + failed_assessments
    
    if not all_results:
        return {
            'average_execution_time_ms': 0.0,
            'total_execution_time_ms': 0.0,
            'tokens_per_second': 0.0,
            'average_risk_score': 100.0
        }
    
    # Calculate execution times
    execution_times = []
    risk_scores = []
    
    for result in all_results:
        exec_time = result.get('execution_time_ms', 0)
        risk_score = result.get('overall_risk_score', 100)
        
        execution_times.append(exec_time)
        risk_scores.append(risk_score)
    
    total_time_ms = sum(execution_times)
    avg_time_ms = total_time_ms / len(execution_times) if execution_times else 0.0
    avg_risk_score = sum(risk_scores) / len(risk_scores) if risk_scores else 100.0
    
    # Calculate throughput
    total_time_seconds = total_time_ms / 1000.0
    tokens_per_second = len(all_results) / total_time_seconds if total_time_seconds > 0 else 0.0
    
    return {
        'average_execution_time_ms': avg_time_ms,
        'total_execution_time_ms': total_time_ms,
        'tokens_per_second': tokens_per_second,
        'average_risk_score': avg_risk_score
    }


def _generate_bulk_insights(
    results: List[Dict[str, Any]], 
    failed_assessments: List[Dict[str, Any]], 
    decision_counts: Dict[str, int]
) -> List[str]:
    """Generate insights from bulk assessment results."""
    insights = []
    total_tokens = len(results) + len(failed_assessments)
    
    if total_tokens == 0:
        return ["No tokens processed"]
    
    # Success rate insight
    success_rate = len(results) / total_tokens * 100
    if success_rate >= 90:
        insights.append(f"High assessment success rate: {success_rate:.1f}%")
    elif success_rate < 70:
        insights.append(f"Low assessment success rate: {success_rate:.1f}% - check system health")
    
    # Trading decision insights
    approved_count = decision_counts.get('APPROVE', 0)
    blocked_count = decision_counts.get('BLOCK', 0)
    
    if approved_count == 0:
        insights.append("No tokens approved - market conditions may be poor")
    elif approved_count / total_tokens > 0.5:
        insights.append(f"High approval rate: {approved_count}/{total_tokens} tokens approved")
    
    if blocked_count / total_tokens > 0.8:
        insights.append("Most tokens blocked - consider adjusting risk profile")
    
    # Risk distribution insights
    if results:
        high_risk_count = len([r for r in results if r.get('overall_risk_score', 0) >= 70])
        if high_risk_count / len(results) > 0.7:
            insights.append("High proportion of risky tokens detected")
    
    # Performance insights
    if results:
        avg_time = sum(r.get('execution_time_ms', 0) for r in results) / len(results)
        if avg_time > 5000:  # 5 seconds
            insights.append("Slow assessment times - consider optimization")
        elif avg_time < 1000:  # 1 second
            insights.append("Fast assessment performance")
    
    return insights or ["Assessment completed successfully"]