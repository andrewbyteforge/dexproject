"""
Risk check execution coordination module.

Handles both parallel and sequential execution of risk checks,
manages timeouts, and provides fallback mechanisms.

File: risk/tasks/execution.py
"""

import logging
import time
from typing import Dict, Any, List
from celery import group

logger = logging.getLogger(__name__)


def execute_parallel_risk_checks(
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
        
    Raises:
        Exception: If parallel execution fails completely
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
                    filtered_results = [r for r in check_results if r is not None]
                    if filtered_results:
                        logger.info(f"Retrieved {len(filtered_results)} partial results")
                        return filtered_results
                except:
                    pass
                
                # Fall back to sequential execution
                logger.info("Falling back to sequential execution")
                return execute_sequential_risk_checks(
                    token_address, pair_address, risk_config, include_advanced
                )
        else:
            logger.warning("No risk checks configured to run")
            return []
            
    except Exception as e:
        logger.error(f"Parallel risk check execution failed: {e}")
        # Fallback to sequential execution
        logger.info("Falling back to sequential execution due to error")
        return execute_sequential_risk_checks(
            token_address, pair_address, risk_config, include_advanced
        )


def execute_sequential_risk_checks(
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
        from . import create_risk_check_result
        
        required_checks = risk_config.get('required_checks', [])
        optional_checks = risk_config.get('optional_checks', []) if include_advanced else []
        all_checks = list(set(required_checks + optional_checks))
        
        # Execute checks one by one with individual error handling
        for check_type in all_checks:
            check_start_time = time.time()
            
            try:
                logger.debug(f"Starting {check_type} check")
                
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
                
                check_time_ms = (time.time() - check_start_time) * 1000
                
                if result:
                    results.append(result)
                    logger.debug(f"Completed {check_type} check in {check_time_ms:.1f}ms")
                else:
                    logger.warning(f"{check_type} check returned no result")
                
            except Exception as e:
                check_time_ms = (time.time() - check_start_time) * 1000
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
                    execution_time_ms=check_time_ms
                )
                results.append(error_result)
        
        logger.info(f"Completed {len(results)} sequential risk checks")
        return results
        
    except Exception as e:
        logger.error(f"Sequential risk check execution failed: {e}")
        return []


def validate_check_configuration(risk_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate risk check configuration.
    
    Args:
        risk_config: Risk profile configuration to validate
        
    Returns:
        Dict with validation results
    """
    validation_result = {
        'is_valid': True,
        'warnings': [],
        'errors': []
    }
    
    try:
        # Check for required configuration keys
        required_keys = ['required_checks', 'timeout_seconds']
        for key in required_keys:
            if key not in risk_config:
                validation_result['errors'].append(f"Missing required config key: {key}")
                validation_result['is_valid'] = False
        
        # Validate check types
        valid_check_types = ['HONEYPOT', 'LIQUIDITY', 'OWNERSHIP', 'TAX_ANALYSIS', 'CONTRACT_SECURITY', 'HOLDER_ANALYSIS']
        
        required_checks = risk_config.get('required_checks', [])
        for check in required_checks:
            if check not in valid_check_types:
                validation_result['warnings'].append(f"Unknown required check type: {check}")
        
        optional_checks = risk_config.get('optional_checks', [])
        for check in optional_checks:
            if check not in valid_check_types:
                validation_result['warnings'].append(f"Unknown optional check type: {check}")
        
        # Check timeout values
        timeout = risk_config.get('timeout_seconds', 30)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            validation_result['errors'].append(f"Invalid timeout value: {timeout}")
            validation_result['is_valid'] = False
        elif timeout > 120:
            validation_result['warnings'].append(f"Long timeout ({timeout}s) may affect performance")
        
        # Check liquidity thresholds
        min_liquidity = risk_config.get('min_liquidity_usd', 0)
        if not isinstance(min_liquidity, (int, float)) or min_liquidity < 0:
            validation_result['errors'].append(f"Invalid min_liquidity_usd: {min_liquidity}")
            validation_result['is_valid'] = False
        
        # Check slippage values
        max_slippage = risk_config.get('max_slippage_percent', 5.0)
        if not isinstance(max_slippage, (int, float)) or max_slippage < 0 or max_slippage > 100:
            validation_result['errors'].append(f"Invalid max_slippage_percent: {max_slippage}")
            validation_result['is_valid'] = False
        
        # Check if at least one check is configured
        total_checks = len(required_checks) + len(optional_checks)
        if total_checks == 0:
            validation_result['warnings'].append("No risk checks configured")
        
        logger.debug(f"Configuration validation: {validation_result}")
        
    except Exception as e:
        validation_result['is_valid'] = False
        validation_result['errors'].append(f"Validation error: {str(e)}")
        logger.error(f"Configuration validation failed: {e}")
    
    return validation_result


def estimate_execution_time(risk_config: Dict[str, Any], include_advanced: bool) -> float:
    """
    Estimate execution time for risk checks based on configuration.
    
    Args:
        risk_config: Risk profile configuration
        include_advanced: Whether advanced checks are included
        
    Returns:
        Estimated execution time in seconds
    """
    # Estimated time per check type (in seconds)
    check_times = {
        'HONEYPOT': 3.0,
        'LIQUIDITY': 2.0,
        'OWNERSHIP': 4.0 if include_advanced else 2.5,
        'TAX_ANALYSIS': 5.0 if include_advanced else 3.0,
        'CONTRACT_SECURITY': 6.0,
        'HOLDER_ANALYSIS': 8.0
    }
    
    required_checks = risk_config.get('required_checks', [])
    optional_checks = risk_config.get('optional_checks', []) if include_advanced else []
    all_checks = list(set(required_checks + optional_checks))
    
    # For parallel execution, time is dominated by the slowest check
    # For sequential execution, time is sum of all checks
    
    if len(all_checks) <= 1:
        # Single check or no checks
        total_time = sum(check_times.get(check, 2.0) for check in all_checks)
    else:
        # Assume parallel execution - time is max of individual checks plus overhead
        max_check_time = max(check_times.get(check, 2.0) for check in all_checks)
        parallel_overhead = 1.0  # Overhead for parallel coordination
        total_time = max_check_time + parallel_overhead
    
    # Add safety margin
    safety_margin = 1.2  # 20% safety margin
    estimated_time = total_time * safety_margin
    
    logger.debug(f"Estimated execution time: {estimated_time:.1f}s for {len(all_checks)} checks")
    
    return estimated_time


def get_execution_strategy(
    risk_config: Dict[str, Any], 
    include_advanced: bool,
    force_sequential: bool = False
) -> Dict[str, Any]:
    """
    Determine optimal execution strategy based on configuration.
    
    Args:
        risk_config: Risk profile configuration
        include_advanced: Whether to include advanced checks
        force_sequential: Force sequential execution
        
    Returns:
        Dict with execution strategy recommendation
    """
    required_checks = risk_config.get('required_checks', [])
    optional_checks = risk_config.get('optional_checks', []) if include_advanced else []
    all_checks = list(set(required_checks + optional_checks))
    
    total_checks = len(all_checks)
    estimated_time = estimate_execution_time(risk_config, include_advanced)
    
    # Decision logic for execution strategy
    if force_sequential or total_checks <= 1:
        strategy = 'sequential'
        reason = 'Forced sequential or single check'
    elif total_checks <= 3 and not include_advanced:
        strategy = 'parallel'
        reason = 'Small number of basic checks'
    elif estimated_time > 30:
        strategy = 'parallel'
        reason = 'Long execution time benefits from parallelization'
    else:
        strategy = 'parallel'
        reason = 'Default parallel execution for multiple checks'
    
    return {
        'strategy': strategy,
        'reason': reason,
        'total_checks': total_checks,
        'estimated_time_seconds': estimated_time,
        'include_advanced': include_advanced,
        'timeout_seconds': risk_config.get('timeout_seconds', 30)
    }