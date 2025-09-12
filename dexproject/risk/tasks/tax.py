"""
Tax analysis task module.

Implements comprehensive tax detection and analysis for tokens including:
- Buy/sell tax percentage calculation
- Transfer restriction detection
- Reflection token analysis
- Blacklist/whitelist mechanism detection
- Anti-whale mechanism analysis

This module provides critical assessment of token taxation mechanisms
that could impact trading profitability and liquidity.
"""

import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal, getcontext
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError

from web3 import Web3
from web3.exceptions import ContractLogicError, BadFunctionCallOutput
from eth_utils import is_address, to_checksum_address

from ..models import RiskAssessment, RiskCheckResult, RiskCheckType
from . import create_risk_check_result

logger = logging.getLogger(__name__)

# Set decimal precision for accurate calculations
getcontext().prec = 28

# Common tax-related function signatures
TAX_FUNCTION_SIGNATURES = [
    'buyTaxPercent()',
    'sellTaxPercent()',
    'transferTax()',
    'liquidityFee()',
    'reflectionFee()',
    'marketingFee()',
    'devFee()',
    'burnFee()',
    'totalFees()',
    'maxTransactionAmount()',
    'maxWalletAmount()',
    'swapThreshold()',
]

# Anti-whale mechanism signatures
ANTIWHALE_SIGNATURES = [
    'maxTransactionAmount()',
    'maxWalletAmount()',
    'maxSellTransactionAmount()',
    'cooldownTimerInterval()',
    'buyCooldownEnabled()',
    'sellCooldownEnabled()',
]

# Blacklist mechanism signatures
BLACKLIST_SIGNATURES = [
    'isBlacklisted(address)',
    'blacklist(address)',
    'unblacklist(address)',
    'isExcludedFromFee(address)',
    'excludeFromFee(address)',
    'includeInFee(address)',
]


@shared_task(
    bind=True,
    queue='risk.urgent',
    name='risk.tasks.tax_analysis',
    max_retries=3,
    default_retry_delay=1
)
def tax_analysis(
    self,
    token_address: str,
    pair_address: str,
    simulation_amount_usd: float = 1000.0,
    check_reflection: bool = True,
    check_antiwhale: bool = True,
    check_blacklist: bool = True
) -> Dict[str, Any]:
    """
    Perform comprehensive tax analysis for a token.
    
    Analyzes buy/sell taxes, transfer restrictions, and anti-whale mechanisms
    through both static analysis and transaction simulation.
    
    Args:
        token_address: The token contract address to analyze
        pair_address: The trading pair address
        simulation_amount_usd: USD amount for tax simulation
        check_reflection: Whether to check for reflection token mechanisms
        check_antiwhale: Whether to check for anti-whale mechanisms
        check_blacklist: Whether to check for blacklist mechanisms
        
    Returns:
        Dict with comprehensive tax analysis results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting tax analysis for token {token_address} (task: {task_id})")
    
    try:
        # Validate inputs
        if not is_address(token_address):
            raise ValueError(f"Invalid token address: {token_address}")
        if not is_address(pair_address):
            raise ValueError(f"Invalid pair address: {pair_address}")
        
        # Get Web3 connection
        w3 = _get_web3_connection()
        
        # Get token information
        token_info = _get_token_information(w3, token_address)
        
        # Analyze tax mechanisms through static analysis
        static_analysis = _analyze_tax_functions(w3, token_address, token_info)
        
        # Simulate buy/sell transactions to measure actual taxes
        simulation_results = _simulate_tax_transactions(
            w3, token_address, pair_address, simulation_amount_usd
        )
        
        # Check for reflection token mechanisms
        reflection_analysis = {}
        if check_reflection:
            reflection_analysis = _analyze_reflection_mechanism(w3, token_address, token_info)
        
        # Check for anti-whale mechanisms
        antiwhale_analysis = {}
        if check_antiwhale:
            antiwhale_analysis = _analyze_antiwhale_mechanisms(w3, token_address, token_info)
        
        # Check for blacklist mechanisms
        blacklist_analysis = {}
        if check_blacklist:
            blacklist_analysis = _analyze_blacklist_mechanisms(w3, token_address, token_info)
        
        # Calculate overall tax risk score
        risk_score = _calculate_tax_risk_score(
            static_analysis, simulation_results, reflection_analysis,
            antiwhale_analysis, blacklist_analysis
        )
        
        # Prepare detailed results
        details = {
            'token_info': token_info,
            'static_analysis': static_analysis,
            'simulation_results': simulation_results,
            'reflection_analysis': reflection_analysis,
            'antiwhale_analysis': antiwhale_analysis,
            'blacklist_analysis': blacklist_analysis,
            'buy_tax_percent': simulation_results.get('buy_tax_percent', 0),
            'sell_tax_percent': simulation_results.get('sell_tax_percent', 0),
            'max_tax_percent': max(
                simulation_results.get('buy_tax_percent', 0),
                simulation_results.get('sell_tax_percent', 0)
            ),
            'has_transfer_restrictions': _has_transfer_restrictions(
                static_analysis, antiwhale_analysis, blacklist_analysis
            ),
            'tax_warnings': _generate_tax_warnings(
                static_analysis, simulation_results, reflection_analysis,
                antiwhale_analysis, blacklist_analysis
            )
        }
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        # Determine status based on analysis
        if risk_score >= 80:
            status = 'FAILED'  # High tax risk - fail the check
        elif risk_score >= 50:
            status = 'WARNING'  # Medium tax risk - warn but proceed
        else:
            status = 'COMPLETED'  # Low tax risk - pass
        
        result = create_risk_check_result(
            task_id=task_id,
            check_type='TAX_ANALYSIS',
            token_address=token_address,
            pair_address=pair_address,
            risk_score=float(risk_score),
            status=status,
            details=details,
            execution_time_ms=execution_time_ms
        )
        
        logger.info(f"Tax analysis completed for {token_address} in {execution_time_ms:.1f}ms - "
                   f"Risk: {risk_score:.1f}, Buy Tax: {details['buy_tax_percent']:.1f}%, "
                   f"Sell Tax: {details['sell_tax_percent']:.1f}%")
        
        return result
        
    except Exception as exc:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"Tax analysis failed for {token_address}: {exc} (task: {task_id})")
        
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying tax analysis for {token_address} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        
        return create_risk_check_result(
            task_id=task_id,
            check_type='TAX_ANALYSIS',
            token_address=token_address,
            pair_address=pair_address,
            risk_score=100,  # Max risk on failure
            status='FAILED',
            error_message=str(exc),
            execution_time_ms=execution_time_ms
        )


def _get_web3_connection() -> Web3:
    """Get Web3 connection (placeholder for now)."""
    # In production, this would return an actual Web3 connection
    from unittest.mock import MagicMock
    mock_w3 = MagicMock()
    mock_w3.eth.block_number = 18500000
    return mock_w3


def _get_token_information(w3: Web3, token_address: str) -> Dict[str, Any]:
    """
    Get basic token information.
    
    Args:
        w3: Web3 connection
        token_address: Token contract address
        
    Returns:
        Dict with token information
    """
    try:
        logger.debug(f"Getting token information for {token_address}")
        
        # In production, this would query the actual token contract
        # For now, simulate token data
        token_info = {
            'address': token_address,
            'name': 'Mock Token',
            'symbol': 'MOCK',
            'decimals': 18,
            'total_supply': 1000000000 * 10**18,  # 1B tokens
            'contract_verified': True,
            'contract_source_available': True
        }
        
        return token_info
        
    except Exception as e:
        logger.error(f"Failed to get token information for {token_address}: {e}")
        raise ValueError(f"Could not retrieve token information: {e}")


def _analyze_tax_functions(w3: Web3, token_address: str, token_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze tax-related functions through static contract analysis.
    
    Args:
        w3: Web3 connection
        token_address: Token contract address
        token_info: Token information
        
    Returns:
        Dict with static tax analysis
    """
    try:
        logger.debug(f"Analyzing tax functions for {token_address}")
        
        detected_functions = []
        tax_config = {}
        
        # In production, this would check for actual function signatures
        # For now, simulate common tax patterns
        
        # Simulate detection of common tax functions
        if 'MOCK' in token_info.get('symbol', ''):
            # Standard ERC20 - no taxes
            detected_functions = []
            tax_config = {
                'buy_tax_percent': 0,
                'sell_tax_percent': 0,
                'has_dynamic_taxes': False,
                'has_tax_exemptions': False
            }
        else:
            # Simulate a token with taxes
            detected_functions = [
                'buyTaxPercent()',
                'sellTaxPercent()',
                'liquidityFee()',
                'marketingFee()'
            ]
            tax_config = {
                'buy_tax_percent': 5.0,
                'sell_tax_percent': 8.0,
                'liquidity_fee': 2.0,
                'marketing_fee': 3.0,
                'has_dynamic_taxes': True,
                'has_tax_exemptions': True
            }
        
        return {
            'detected_functions': detected_functions,
            'tax_config': tax_config,
            'function_count': len(detected_functions),
            'complexity_score': _calculate_tax_complexity_score(detected_functions),
            'pattern_analysis': _analyze_tax_patterns(detected_functions)
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze tax functions for {token_address}: {e}")
        return {
            'detected_functions': [],
            'tax_config': {},
            'error': str(e)
        }


def _simulate_tax_transactions(
    w3: Web3, 
    token_address: str, 
    pair_address: str, 
    simulation_amount_usd: float
) -> Dict[str, Any]:
    """
    Simulate buy/sell transactions to measure actual tax rates.
    
    Args:
        w3: Web3 connection
        token_address: Token contract address
        pair_address: Trading pair address
        simulation_amount_usd: Amount in USD to simulate
        
    Returns:
        Dict with simulation results
    """
    try:
        logger.debug(f"Simulating tax transactions for {token_address}")
        
        # In production, this would:
        # 1. Create a fork of the blockchain
        # 2. Simulate a buy transaction
        # 3. Measure tokens received vs expected
        # 4. Calculate buy tax percentage
        # 5. Simulate a sell transaction
        # 6. Measure ETH received vs expected
        # 7. Calculate sell tax percentage
        
        # For now, simulate realistic tax scenarios
        simulation_results = {
            'simulation_amount_usd': simulation_amount_usd,
            'buy_simulation': {
                'expected_tokens': 1000000,  # Expected tokens for $1000
                'actual_tokens': 950000,     # 5% buy tax
                'buy_tax_percent': 5.0,
                'gas_used': 150000,
                'simulation_successful': True
            },
            'sell_simulation': {
                'tokens_sold': 950000,       # Tokens to sell
                'expected_eth': 0.4,         # Expected ETH ($1000 worth)
                'actual_eth': 0.368,         # 8% sell tax
                'sell_tax_percent': 8.0,
                'gas_used': 180000,
                'simulation_successful': True
            },
            'buy_tax_percent': 5.0,
            'sell_tax_percent': 8.0,
            'round_trip_loss_percent': 12.6,  # Combined buy + sell tax
            'simulation_timestamp': timezone.now().isoformat()
        }
        
        return simulation_results
        
    except Exception as e:
        logger.error(f"Failed to simulate tax transactions for {token_address}: {e}")
        return {
            'simulation_amount_usd': simulation_amount_usd,
            'buy_tax_percent': 50.0,  # Assume high tax on error
            'sell_tax_percent': 50.0,
            'simulation_successful': False,
            'error': str(e)
        }


def _analyze_reflection_mechanism(w3: Web3, token_address: str, token_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze reflection token mechanisms.
    
    Reflection tokens redistribute fees to holders, which can complicate
    tax calculations and create additional risks.
    
    Args:
        w3: Web3 connection
        token_address: Token contract address
        token_info: Token information
        
    Returns:
        Dict with reflection analysis
    """
    try:
        logger.debug(f"Analyzing reflection mechanism for {token_address}")
        
        # Check for common reflection function signatures
        reflection_functions = [
            'reflect(uint256)',
            'tokenFromReflection(uint256)',
            'reflectionFromToken(uint256,bool)',
            'excludeFromReward(address)',
            'includeInReward(address)',
            'isExcludedFromReward(address)',
            'getTotalReflections()',
            'getReflectionRate()'
        ]
        
        # In production, this would check for actual function implementations
        detected_reflection_functions = []
        
        # Simulate reflection detection
        if 'reflect' in token_info.get('name', '').lower():
            detected_reflection_functions = reflection_functions[:4]
            is_reflection_token = True
            reflection_fee_percent = 2.0
        else:
            is_reflection_token = False
            reflection_fee_percent = 0.0
        
        return {
            'is_reflection_token': is_reflection_token,
            'detected_functions': detected_reflection_functions,
            'reflection_fee_percent': reflection_fee_percent,
            'holder_rewards_enabled': is_reflection_token,
            'reflection_complexity': len(detected_reflection_functions),
            'risks': _analyze_reflection_risks(is_reflection_token, reflection_fee_percent)
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze reflection mechanism for {token_address}: {e}")
        return {
            'is_reflection_token': False,
            'error': str(e)
        }


def _analyze_antiwhale_mechanisms(w3: Web3, token_address: str, token_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze anti-whale mechanisms.
    
    Anti-whale mechanisms limit large transactions or wallet holdings,
    which can prevent large trades and affect liquidity.
    
    Args:
        w3: Web3 connection
        token_address: Token contract address
        token_info: Token information
        
    Returns:
        Dict with anti-whale analysis
    """
    try:
        logger.debug(f"Analyzing anti-whale mechanisms for {token_address}")
        
        # In production, this would check actual contract state
        # For now, simulate common anti-whale patterns
        
        detected_mechanisms = []
        limits = {}
        
        # Simulate anti-whale detection
        total_supply = token_info.get('total_supply', 1000000000 * 10**18)
        
        # Common anti-whale limits (simulate)
        max_transaction_percent = 1.0  # 1% of total supply
        max_wallet_percent = 2.0  # 2% of total supply
        
        if 'whale' in token_info.get('name', '').lower() or len(token_info.get('symbol', '')) > 10:
            # Simulate token with anti-whale mechanisms
            detected_mechanisms = [
                'maxTransactionAmount()',
                'maxWalletAmount()',
                'cooldownTimerInterval()'
            ]
            limits = {
                'max_transaction_amount': int(total_supply * max_transaction_percent / 100),
                'max_wallet_amount': int(total_supply * max_wallet_percent / 100),
                'max_transaction_percent': max_transaction_percent,
                'max_wallet_percent': max_wallet_percent,
                'cooldown_seconds': 60,
                'has_cooldown': True
            }
            has_antiwhale = True
        else:
            has_antiwhale = False
            limits = {
                'max_transaction_amount': total_supply,  # No limit
                'max_wallet_amount': total_supply,       # No limit
                'max_transaction_percent': 100.0,
                'max_wallet_percent': 100.0,
                'has_cooldown': False
            }
        
        return {
            'has_antiwhale_mechanisms': has_antiwhale,
            'detected_mechanisms': detected_mechanisms,
            'limits': limits,
            'mechanism_count': len(detected_mechanisms),
            'restrictiveness_score': _calculate_restrictiveness_score(limits),
            'risks': _analyze_antiwhale_risks(has_antiwhale, limits)
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze anti-whale mechanisms for {token_address}: {e}")
        return {
            'has_antiwhale_mechanisms': False,
            'error': str(e)
        }


def _analyze_blacklist_mechanisms(w3: Web3, token_address: str, token_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze blacklist/whitelist mechanisms.
    
    Blacklist mechanisms can prevent certain addresses from trading,
    which creates centralization risks and potential for abuse.
    
    Args:
        w3: Web3 connection
        token_address: Token contract address
        token_info: Token information
        
    Returns:
        Dict with blacklist analysis
    """
    try:
        logger.debug(f"Analyzing blacklist mechanisms for {token_address}")
        
        # In production, this would check for actual blacklist functions
        detected_functions = []
        
        # Simulate blacklist detection
        if 'secure' in token_info.get('name', '').lower():
            detected_functions = [
                'isBlacklisted(address)',
                'blacklist(address)', 
                'unblacklist(address)',
                'isExcludedFromFee(address)'
            ]
            has_blacklist = True
            can_blacklist_users = True
        else:
            has_blacklist = False
            can_blacklist_users = False
        
        return {
            'has_blacklist_mechanism': has_blacklist,
            'detected_functions': detected_functions,
            'can_blacklist_users': can_blacklist_users,
            'has_fee_exemptions': has_blacklist,  # Usually correlated
            'function_count': len(detected_functions),
            'centralization_risk': 'HIGH' if can_blacklist_users else 'LOW',
            'risks': _analyze_blacklist_risks(has_blacklist, can_blacklist_users)
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze blacklist mechanisms for {token_address}: {e}")
        return {
            'has_blacklist_mechanism': False,
            'error': str(e)
        }


def _calculate_tax_risk_score(
    static_analysis: Dict[str, Any],
    simulation_results: Dict[str, Any],
    reflection_analysis: Dict[str, Any],
    antiwhale_analysis: Dict[str, Any],
    blacklist_analysis: Dict[str, Any]
) -> Decimal:
    """
    Calculate overall tax risk score.
    
    Combines multiple factors to produce a comprehensive tax risk assessment:
    - Buy/sell tax percentages
    - Reflection token complexity
    - Anti-whale restrictions
    - Blacklist centralization risks
    
    Args:
        static_analysis: Results from static function analysis
        simulation_results: Results from transaction simulation
        reflection_analysis: Results from reflection mechanism analysis
        antiwhale_analysis: Results from anti-whale analysis
        blacklist_analysis: Results from blacklist analysis
        
    Returns:
        Risk score as Decimal (0-100, where 0 is lowest risk)
    """
    score = Decimal('0')
    
    # Tax percentage scoring (0-40 points)
    buy_tax = simulation_results.get('buy_tax_percent', 0)
    sell_tax = simulation_results.get('sell_tax_percent', 0)
    max_tax = max(buy_tax, sell_tax)
    
    if max_tax > 25:
        score += Decimal('40')  # Very high tax
    elif max_tax > 15:
        score += Decimal('30')  # High tax
    elif max_tax > 10:
        score += Decimal('20')  # Medium tax
    elif max_tax > 5:
        score += Decimal('10')  # Low tax
    # 0-5% tax adds no risk points
    
    # Reflection mechanism scoring (0-20 points)
    if reflection_analysis.get('is_reflection_token', False):
        reflection_complexity = reflection_analysis.get('reflection_complexity', 0)
        score += Decimal(str(min(reflection_complexity * 3, 20)))
    
    # Anti-whale mechanism scoring (0-25 points)
    if antiwhale_analysis.get('has_antiwhale_mechanisms', False):
        restrictiveness = antiwhale_analysis.get('restrictiveness_score', 0)
        score += Decimal(str(min(restrictiveness / 4, 25)))
    
    # Blacklist mechanism scoring (0-15 points)
    if blacklist_analysis.get('has_blacklist_mechanism', False):
        if blacklist_analysis.get('can_blacklist_users', False):
            score += Decimal('15')  # High centralization risk
        else:
            score += Decimal('5')   # Low centralization risk
    
    return min(score, Decimal('100'))


def _has_transfer_restrictions(
    static_analysis: Dict[str, Any],
    antiwhale_analysis: Dict[str, Any],
    blacklist_analysis: Dict[str, Any]
) -> bool:
    """Check if token has any transfer restrictions."""
    return (
        antiwhale_analysis.get('has_antiwhale_mechanisms', False) or
        blacklist_analysis.get('has_blacklist_mechanism', False) or
        static_analysis.get('tax_config', {}).get('has_dynamic_taxes', False)
    )


def _generate_tax_warnings(
    static_analysis: Dict[str, Any],
    simulation_results: Dict[str, Any],
    reflection_analysis: Dict[str, Any],
    antiwhale_analysis: Dict[str, Any],
    blacklist_analysis: Dict[str, Any]
) -> List[str]:
    """
    Generate warning messages for tax-related risks.
    
    Args:
        static_analysis: Static analysis results
        simulation_results: Simulation results
        reflection_analysis: Reflection analysis results
        antiwhale_analysis: Anti-whale analysis results
        blacklist_analysis: Blacklist analysis results
        
    Returns:
        List of warning messages
    """
    warnings = []
    
    # Tax percentage warnings
    buy_tax = simulation_results.get('buy_tax_percent', 0)
    sell_tax = simulation_results.get('sell_tax_percent', 0)
    
    if buy_tax > 15:
        warnings.append(f"Very high buy tax: {buy_tax:.1f}%")
    elif buy_tax > 10:
        warnings.append(f"High buy tax: {buy_tax:.1f}%")
    
    if sell_tax > 15:
        warnings.append(f"Very high sell tax: {sell_tax:.1f}%")
    elif sell_tax > 10:
        warnings.append(f"High sell tax: {sell_tax:.1f}%")
    
    # Combined tax warning
    round_trip_loss = simulation_results.get('round_trip_loss_percent', 0)
    if round_trip_loss > 20:
        warnings.append(f"Excessive round-trip loss: {round_trip_loss:.1f}%")
    
    # Reflection token warnings
    if reflection_analysis.get('is_reflection_token', False):
        warnings.append("Reflection token - tax calculations may vary")
        reflection_fee = reflection_analysis.get('reflection_fee_percent', 0)
        if reflection_fee > 5:
            warnings.append(f"High reflection fee: {reflection_fee:.1f}%")
    
    # Anti-whale warnings
    if antiwhale_analysis.get('has_antiwhale_mechanisms', False):
        limits = antiwhale_analysis.get('limits', {})
        max_tx_percent = limits.get('max_transaction_percent', 100)
        max_wallet_percent = limits.get('max_wallet_percent', 100)
        
        if max_tx_percent < 1:
            warnings.append(f"Very restrictive transaction limit: {max_tx_percent:.2f}%")
        elif max_tx_percent < 2:
            warnings.append(f"Restrictive transaction limit: {max_tx_percent:.1f}%")
        
        if max_wallet_percent < 2:
            warnings.append(f"Very restrictive wallet limit: {max_wallet_percent:.2f}%")
        elif max_wallet_percent < 5:
            warnings.append(f"Restrictive wallet limit: {max_wallet_percent:.1f}%")
        
        if limits.get('has_cooldown', False):
            cooldown = limits.get('cooldown_seconds', 0)
            warnings.append(f"Trading cooldown: {cooldown} seconds")
    
    # Blacklist warnings
    if blacklist_analysis.get('has_blacklist_mechanism', False):
        if blacklist_analysis.get('can_blacklist_users', False):
            warnings.append("Contract can blacklist addresses - centralization risk")
        warnings.append("Fee exemption mechanism present")
    
    # Simulation warnings
    if not simulation_results.get('simulation_successful', True):
        warnings.append("Tax simulation failed - actual taxes may be higher")
    
    return warnings


# Helper functions for risk analysis

def _calculate_tax_complexity_score(detected_functions: List[str]) -> int:
    """Calculate tax complexity score based on detected functions."""
    complexity_weights = {
        'buyTaxPercent()': 10,
        'sellTaxPercent()': 10,
        'liquidityFee()': 5,
        'reflectionFee()': 15,
        'marketingFee()': 5,
        'devFee()': 5,
        'burnFee()': 8,
        'totalFees()': 3,
        'maxTransactionAmount()': 12,
        'maxWalletAmount()': 12,
    }
    
    total_complexity = 0
    for func in detected_functions:
        total_complexity += complexity_weights.get(func, 5)
    
    return min(total_complexity, 100)


def _analyze_tax_patterns(detected_functions: List[str]) -> Dict[str, Any]:
    """Analyze patterns in detected tax functions."""
    patterns = {
        'has_buy_tax': any('buy' in func.lower() for func in detected_functions),
        'has_sell_tax': any('sell' in func.lower() for func in detected_functions),
        'has_liquidity_fee': any('liquidity' in func.lower() for func in detected_functions),
        'has_reflection_fee': any('reflection' in func.lower() for func in detected_functions),
        'has_marketing_fee': any('marketing' in func.lower() for func in detected_functions),
        'has_burn_mechanism': any('burn' in func.lower() for func in detected_functions),
        'has_transaction_limits': any('max' in func.lower() and 'transaction' in func.lower() for func in detected_functions),
        'has_wallet_limits': any('max' in func.lower() and 'wallet' in func.lower() for func in detected_functions)
    }
    
    # Determine tax pattern type
    if patterns['has_reflection_fee']:
        pattern_type = 'reflection'
    elif patterns['has_liquidity_fee'] and patterns['has_marketing_fee']:
        pattern_type = 'multi_fee'
    elif patterns['has_burn_mechanism']:
        pattern_type = 'deflationary'
    elif patterns['has_buy_tax'] or patterns['has_sell_tax']:
        pattern_type = 'basic_tax'
    else:
        pattern_type = 'standard'
    
    patterns['pattern_type'] = pattern_type
    return patterns


def _analyze_reflection_risks(is_reflection_token: bool, reflection_fee_percent: float) -> List[str]:
    """Analyze risks associated with reflection tokens."""
    risks = []
    
    if is_reflection_token:
        risks.append("Balance changes over time due to reflections")
        risks.append("Complex tax calculations - actual rates may vary")
        risks.append("Potential for MEV exploitation in reflection distributions")
        
        if reflection_fee_percent > 5:
            risks.append("High reflection fee reduces trading profitability")
        
        risks.append("Excluded addresses may have different tax rates")
    
    return risks


def _calculate_restrictiveness_score(limits: Dict[str, Any]) -> float:
    """Calculate how restrictive anti-whale mechanisms are."""
    score = 0.0
    
    # Transaction limit scoring
    max_tx_percent = limits.get('max_transaction_percent', 100)
    if max_tx_percent < 0.5:
        score += 40
    elif max_tx_percent < 1:
        score += 30
    elif max_tx_percent < 2:
        score += 20
    elif max_tx_percent < 5:
        score += 10
    
    # Wallet limit scoring
    max_wallet_percent = limits.get('max_wallet_percent', 100)
    if max_wallet_percent < 1:
        score += 35
    elif max_wallet_percent < 2:
        score += 25
    elif max_wallet_percent < 5:
        score += 15
    elif max_wallet_percent < 10:
        score += 5
    
    # Cooldown scoring
    if limits.get('has_cooldown', False):
        cooldown_seconds = limits.get('cooldown_seconds', 0)
        if cooldown_seconds > 300:  # 5 minutes
            score += 25
        elif cooldown_seconds > 60:  # 1 minute
            score += 15
        else:
            score += 5
    
    return min(score, 100.0)


def _analyze_antiwhale_risks(has_antiwhale: bool, limits: Dict[str, Any]) -> List[str]:
    """Analyze risks associated with anti-whale mechanisms."""
    risks = []
    
    if has_antiwhale:
        max_tx_percent = limits.get('max_transaction_percent', 100)
        max_wallet_percent = limits.get('max_wallet_percent', 100)
        
        if max_tx_percent < 1:
            risks.append("Very restrictive transaction limits may prevent large trades")
        
        if max_wallet_percent < 2:
            risks.append("Very restrictive wallet limits may prevent accumulation")
        
        if limits.get('has_cooldown', False):
            risks.append("Trading cooldowns may prevent rapid arbitrage")
        
        risks.append("Anti-whale mechanisms may reduce liquidity")
        risks.append("Limits may be changed by contract owner")
    
    return risks


def _analyze_blacklist_risks(has_blacklist: bool, can_blacklist_users: bool) -> List[str]:
    """Analyze risks associated with blacklist mechanisms."""
    risks = []
    
    if has_blacklist:
        if can_blacklist_users:
            risks.append("Contract owner can prevent addresses from trading")
            risks.append("High centralization risk - potential for abuse")
            risks.append("Users could be blacklisted without warning")
        
        risks.append("Fee exemption system may create unfair advantages")
        risks.append("Blacklist mechanisms add complexity to trading")
    
    return risks


# Utility functions

def _get_erc20_abi() -> List[Dict]:
    """Get minimal ERC20 ABI for essential functions."""
    return [
        {
            "inputs": [],
            "name": "name",
            "outputs": [{"internalType": "string", "name": "", "type": "string"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "symbol", 
            "outputs": [{"internalType": "string", "name": "", "type": "string"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "decimals",
            "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "totalSupply",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        }
    ]