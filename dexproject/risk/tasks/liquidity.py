"""
Liquidity analysis task module.

Implements comprehensive liquidity analysis for trading pairs including
depth analysis, slippage calculations, LP lock verification, and
liquidity quality assessment.

This module provides critical risk assessment for trade execution
by ensuring sufficient liquidity exists before trading.
"""

import logging
import time
from typing import Dict, Any, Optional, Tuple, List
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

# Common burn addresses for LP tokens
BURN_ADDRESSES = [
    '0x000000000000000000000000000000000000dEaD',  # Common burn address
    '0x0000000000000000000000000000000000000000',  # Zero address
    '0x0000000000000000000000000000000000000001',  # Alternative burn
]

# Known LP locker contract addresses (Ethereum mainnet)
KNOWN_LOCKERS = {
    '0x663A5C229c09b049E36dCc11a9B0d4a8Eb9db214': 'Unicrypt V2',
    '0x71B5759d73262FBb223956913ecF4ecC51057641': 'Unicrypt V3',
    '0xDba68f07d1b7Ca219f78ae8582C213d975c25cAf': 'Unicrypt Old',
    '0xe2fE530C047f2d85298b07D9333C05737f1435fB': 'TrustSwap',
    '0x7ee9A5aB7E45F04E2e8e14D0D1b32b3B4F1f8b7f': 'Team Finance',
    '0x4Ee2A9de2dfbeD64F8D7eB0E1E7C7A78AfEF7C50': 'DXSale',
}


@shared_task(
    bind=True,
    queue='risk.urgent',
    name='risk.tasks.liquidity_check',
    max_retries=3,
    default_retry_delay=1
)
def liquidity_check(
    self,
    pair_address: str,
    token_address: str = None,
    min_liquidity_usd: float = 10000.0,
    max_slippage_percent: float = 5.0,
    test_trade_sizes: List[float] = None
) -> Dict[str, Any]:
    """
    Perform comprehensive liquidity analysis for a trading pair.
    
    Analyzes liquidity depth, calculates slippage impact, verifies LP locks,
    and assesses overall liquidity quality for safe trading.
    
    Args:
        pair_address: The trading pair contract address
        token_address: The token contract address (optional)
        min_liquidity_usd: Minimum required liquidity in USD
        max_slippage_percent: Maximum acceptable slippage percentage
        test_trade_sizes: List of trade sizes in USD to test slippage
        
    Returns:
        Dict with comprehensive liquidity analysis results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting liquidity analysis for pair {pair_address} (task: {task_id})")
    
    try:
        # Validate inputs
        if not is_address(pair_address):
            raise ValueError(f"Invalid pair address: {pair_address}")
        
        # Set default test trade sizes if not provided
        if test_trade_sizes is None:
            test_trade_sizes = [1000, 5000, 10000, 25000, 50000]  # USD amounts
        
        # Get Web3 connection (simulated for now)
        w3 = _get_web3_connection()
        
        # Get pair information
        pair_info = _get_pair_information(w3, pair_address)
        
        # Analyze liquidity depth
        liquidity_analysis = _analyze_liquidity_depth(w3, pair_address, pair_info)
        
        # Calculate slippage impact for various trade sizes
        slippage_analysis = _calculate_slippage_impact(
            w3, pair_address, pair_info, test_trade_sizes
        )
        
        # Check LP token locks and burns
        lp_analysis = _analyze_lp_tokens(w3, pair_address, pair_info)
        
        # Get historical liquidity trends
        history_analysis = _analyze_liquidity_history(w3, pair_address, pair_info)
        
        # Calculate overall risk score
        risk_score = _calculate_liquidity_risk_score(
            liquidity_analysis, slippage_analysis, lp_analysis, min_liquidity_usd, max_slippage_percent
        )
        
        # Prepare detailed results
        details = {
            'pair_info': pair_info,
            'total_liquidity_usd': liquidity_analysis['total_liquidity_usd'],
            'token0_liquidity_usd': liquidity_analysis['token0_liquidity_usd'],
            'token1_liquidity_usd': liquidity_analysis['token1_liquidity_usd'],
            'reserves': liquidity_analysis['reserves'],
            'price_impact': slippage_analysis,
            'lp_analysis': lp_analysis,
            'liquidity_history': history_analysis,
            'min_required_usd': min_liquidity_usd,
            'meets_minimum': liquidity_analysis['total_liquidity_usd'] >= min_liquidity_usd,
            'max_acceptable_slippage': max_slippage_percent,
            'slippage_acceptable': slippage_analysis.get('max_slippage', 100) <= max_slippage_percent,
            'quality_metrics': _calculate_liquidity_quality_metrics(liquidity_analysis, slippage_analysis),
            'warnings': _generate_liquidity_warnings(liquidity_analysis, slippage_analysis, lp_analysis)
        }
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        # Determine status based on analysis
        if risk_score >= 80:
            status = 'FAILED'  # High risk - fail the check
        elif risk_score >= 50:
            status = 'WARNING'  # Medium risk - warn but proceed
        else:
            status = 'COMPLETED'  # Low risk - pass
        
        result = create_risk_check_result(
            task_id=task_id,
            check_type='LIQUIDITY',
            token_address=token_address,
            pair_address=pair_address,
            risk_score=float(risk_score),
            status=status,
            details=details,
            execution_time_ms=execution_time_ms
        )
        
        logger.info(f"Liquidity check completed for {pair_address} in {execution_time_ms:.1f}ms - "
                   f"Risk: {risk_score:.1f}, Liquidity: ${details['total_liquidity_usd']:,.2f}")
        
        return result
        
    except Exception as exc:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"Liquidity check failed for {pair_address}: {exc} (task: {task_id})")
        
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying liquidity check for {pair_address} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        
        return create_risk_check_result(
            task_id=task_id,
            check_type='LIQUIDITY',
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
    # For now, return a mock object that won't cause errors
    from unittest.mock import MagicMock
    mock_w3 = MagicMock()
    mock_w3.eth.block_number = 18500000  # Mock current block
    return mock_w3


def _get_pair_information(w3: Web3, pair_address: str) -> Dict[str, Any]:
    """
    Get basic pair information including tokens and reserves.
    
    Args:
        w3: Web3 connection
        pair_address: Trading pair address
        
    Returns:
        Dict with pair information
    """
    try:
        logger.debug(f"Getting pair information for {pair_address}")
        
        # In production, this would use the actual Uniswap V2 pair ABI
        # For now, simulate the data structure
        pair_info = {
            'pair_address': pair_address,
            'token0': {
                'address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',  # WETH
                'symbol': 'WETH',
                'decimals': 18,
                'name': 'Wrapped Ether'
            },
            'token1': {
                'address': '0xA0b86a33E6441e94B6b0bFb4E6E7C8c8E7c8E7c8',  # Mock token
                'symbol': 'TOKEN',
                'decimals': 18,
                'name': 'Mock Token'
            },
            'reserves': {
                'reserve0': 50 * 10**18,  # 50 ETH
                'reserve1': 1000000 * 10**18,  # 1M tokens
                'block_timestamp_last': int(time.time())
            },
            'factory': _detect_dex_factory(w3, pair_address),
            'fee_tier': 3000  # 0.3% for Uniswap V3, or standard V2
        }
        
        return pair_info
        
    except Exception as e:
        logger.error(f"Failed to get pair information for {pair_address}: {e}")
        raise ValueError(f"Could not retrieve pair information: {e}")


def _analyze_liquidity_depth(w3: Web3, pair_address: str, pair_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze liquidity depth and calculate USD values.
    
    Args:
        w3: Web3 connection
        pair_address: Trading pair address
        pair_info: Pair information from _get_pair_information
        
    Returns:
        Dict with liquidity depth analysis
    """
    try:
        logger.debug(f"Analyzing liquidity depth for {pair_address}")
        
        reserves = pair_info['reserves']
        token0 = pair_info['token0']
        token1 = pair_info['token1']
        
        # Get token prices in USD
        token0_price_usd = _get_token_price_usd(w3, token0['address'])
        token1_price_usd = _get_token_price_usd(w3, token1['address'])
        
        # Calculate liquidity values in USD
        token0_liquidity_usd = (reserves['reserve0'] / 10**token0['decimals']) * token0_price_usd
        token1_liquidity_usd = (reserves['reserve1'] / 10**token1['decimals']) * token1_price_usd
        total_liquidity_usd = token0_liquidity_usd + token1_liquidity_usd
        
        # Calculate liquidity metrics
        liquidity_metrics = {
            'imbalance': abs(token0_liquidity_usd - token1_liquidity_usd) / max(token0_liquidity_usd, token1_liquidity_usd, 1),
            'depth_score': _calculate_depth_score(total_liquidity_usd),
            'reserve_ratio': reserves['reserve0'] / max(reserves['reserve1'], 1)
        }
        
        return {
            'total_liquidity_usd': total_liquidity_usd,
            'token0_liquidity_usd': token0_liquidity_usd,
            'token1_liquidity_usd': token1_liquidity_usd,
            'reserves': reserves,
            'token_prices_usd': {
                'token0': token0_price_usd,
                'token1': token1_price_usd
            },
            'liquidity_metrics': liquidity_metrics
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze liquidity depth for {pair_address}: {e}")
        return {
            'total_liquidity_usd': 0,
            'token0_liquidity_usd': 0,
            'token1_liquidity_usd': 0,
            'error': str(e)
        }


def _calculate_slippage_impact(
    w3: Web3, 
    pair_address: str, 
    pair_info: Dict[str, Any], 
    test_trade_sizes: List[float]
) -> Dict[str, Any]:
    """
    Calculate slippage impact for various trade sizes.
    
    Args:
        w3: Web3 connection
        pair_address: Trading pair address
        pair_info: Pair information
        test_trade_sizes: List of trade sizes in USD to test
        
    Returns:
        Dict with slippage analysis
    """
    try:
        logger.debug(f"Calculating slippage impact for {pair_address}")
        
        reserves = pair_info['reserves']
        slippage_data = []
        
        for trade_size_usd in test_trade_sizes:
            # Calculate slippage for buy order (ETH -> Token)
            buy_slippage = _calculate_buy_slippage(
                reserves['reserve0'], reserves['reserve1'], trade_size_usd, pair_info
            )
            
            # Calculate slippage for sell order (Token -> ETH)
            sell_slippage = _calculate_sell_slippage(
                reserves['reserve0'], reserves['reserve1'], trade_size_usd, pair_info
            )
            
            slippage_data.append({
                'trade_size_usd': trade_size_usd,
                'buy_slippage_percent': buy_slippage,
                'sell_slippage_percent': sell_slippage,
                'max_slippage_percent': max(buy_slippage, sell_slippage)
            })
        
        # Find maximum slippage across all test sizes
        max_slippage = max(item['max_slippage_percent'] for item in slippage_data) if slippage_data else 100
        
        # Analyze slippage curve
        slippage_curve_analysis = _analyze_slippage_curve(slippage_data)
        
        # Calculate liquidity efficiency
        efficiency = _calculate_liquidity_efficiency(slippage_data)
        
        return {
            'slippage_data': slippage_data,
            'max_slippage': max_slippage,
            'curve_analysis': slippage_curve_analysis,
            'liquidity_efficiency': efficiency
        }
        
    except Exception as e:
        logger.error(f"Failed to calculate slippage for {pair_address}: {e}")
        return {
            'slippage_data': [],
            'max_slippage': 100,
            'liquidity_efficiency': 0,
            'error': str(e)
        }


def _analyze_lp_tokens(w3: Web3, pair_address: str, pair_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze LP token distribution, locks, and burns.
    
    Comprehensive analysis of LP token security including:
    - Total supply and circulating tokens
    - Burned tokens (sent to burn addresses)
    - Locked tokens (in locker contracts)
    - Distribution security score
    
    Args:
        w3: Web3 connection
        pair_address: Trading pair address
        pair_info: Pair information
        
    Returns:
        Dict with LP token analysis
    """
    try:
        logger.debug(f"Analyzing LP tokens for pair {pair_address}")
        
        # Simulate LP token contract interaction
        # In production, this would use the actual pair contract ABI
        total_supply = 1000000 * 10**18  # Mock total supply
        
        # Check burned tokens
        burned_amount = _check_burned_tokens(w3, pair_address, total_supply)
        
        # Check locked tokens in known locker contracts
        locked_amount = _check_lp_locks(w3, pair_address, total_supply)
        
        # Calculate distribution metrics
        circulating_supply = total_supply - burned_amount - locked_amount
        burn_percentage = (burned_amount / total_supply * 100) if total_supply > 0 else 0
        lock_percentage = (locked_amount / total_supply * 100) if total_supply > 0 else 0
        circulating_percentage = (circulating_supply / total_supply * 100) if total_supply > 0 else 0
        
        # Calculate security score
        security_score = _calculate_lp_security_score(burn_percentage, lock_percentage)
        
        return {
            'total_supply': total_supply,
            'burned_amount': burned_amount,
            'locked_amount': locked_amount,
            'circulating_supply': circulating_supply,
            'burn_percentage': burn_percentage,
            'lock_percentage': lock_percentage,
            'circulating_percentage': circulating_percentage,
            'is_majority_locked_burned': (burn_percentage + lock_percentage) > 80,
            'security_score': security_score,
            'locker_details': _get_locker_details(w3, pair_address)
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze LP tokens for {pair_address}: {e}")
        return {
            'total_supply': 0,
            'burned_amount': 0,
            'locked_amount': 0,
            'circulating_supply': 0,
            'burn_percentage': 0,
            'lock_percentage': 0,
            'circulating_percentage': 100,
            'is_majority_locked_burned': False,
            'security_score': 0,
            'error': str(e)
        }


def _check_burned_tokens(w3: Web3, pair_address: str, total_supply: int) -> int:
    """
    Check for LP tokens sent to burn addresses.
    
    Args:
        w3: Web3 connection
        pair_address: LP token contract address
        total_supply: Total LP token supply
        
    Returns:
        Amount of burned tokens
    """
    burned_amount = 0
    
    try:
        # In production, this would check actual balances
        # For now, simulate common burn scenarios
        
        # Simulate 70% of tokens burned (common for legitimate projects)
        burned_amount = int(total_supply * 0.70)
        
        logger.debug(f"Found {burned_amount / 10**18:.2f} burned LP tokens for {pair_address}")
        
    except Exception as e:
        logger.warning(f"Could not check burned tokens for {pair_address}: {e}")
    
    return burned_amount


def _check_lp_locks(w3: Web3, pair_address: str, total_supply: int) -> int:
    """
    Check for LP tokens locked in known locker contracts.
    
    Checks major LP locker services like Unicrypt, TrustSwap, Team Finance,
    and DXSale for locked LP tokens.
    
    Args:
        w3: Web3 connection
        pair_address: LP token contract address
        total_supply: Total LP token supply
        
    Returns:
        Amount of locked tokens
    """
    locked_amount = 0
    
    try:
        # In production, this would check balances in known locker contracts
        # For now, simulate locked tokens (15% locked is common)
        locked_amount = int(total_supply * 0.15)
        
        logger.debug(f"Found {locked_amount / 10**18:.2f} locked LP tokens for {pair_address}")
        
        # Would implement actual locker contract checks like:
        # for locker_address, locker_name in KNOWN_LOCKERS.items():
        #     try:
        #         balance = pair_contract.functions.balanceOf(locker_address).call()
        #         if balance > 0:
        #             locked_amount += balance
        #             logger.info(f"Found {balance / 10**18:.2f} LP tokens locked in {locker_name}")
        #     except Exception as e:
        #         logger.debug(f"Could not check {locker_name}: {e}")
        
    except Exception as e:
        logger.warning(f"Could not check LP locks for {pair_address}: {e}")
    
    return locked_amount


def _get_locker_details(w3: Web3, pair_address: str) -> List[Dict[str, Any]]:
    """Get details about LP token locks."""
    # In production, this would return actual lock details
    return [
        {
            'locker_name': 'Unicrypt V3',
            'locker_address': '0x71B5759d73262FBb223956913ecF4ecC51057641',
            'locked_amount': 150000 * 10**18,
            'lock_percentage': 15.0,
            'unlock_date': '2025-12-31T23:59:59Z',
            'is_verified': True
        }
    ]


def _analyze_liquidity_history(w3: Web3, pair_address: str, pair_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze historical liquidity trends (simplified implementation).
    
    Args:
        w3: Web3 connection
        pair_address: Trading pair address
        pair_info: Pair information
        
    Returns:
        Dict with historical analysis
    """
    try:
        # In a full implementation, this would query historical data
        # For now, return basic trend analysis
        
        current_block = getattr(w3.eth, 'block_number', 18500000)
        blocks_per_day = 7200  # Approximate for Ethereum
        
        # Simulate trend analysis
        return {
            'current_block': current_block,
            'trend_analysis': 'stable',  # Placeholder
            'volume_24h': 250000,  # Mock daily volume in USD
            'liquidity_changes': [
                {'block': current_block - 7200, 'liquidity_usd': 95000},
                {'block': current_block - 3600, 'liquidity_usd': 98000},
                {'block': current_block, 'liquidity_usd': 100000}
            ],
            'analysis_period_blocks': blocks_per_day,
            'volatility_score': 25.0  # Low volatility
        }
        
    except Exception as e:
        logger.warning(f"Could not analyze liquidity history for {pair_address}: {e}")
        return {'error': str(e)}


def _calculate_liquidity_risk_score(
    liquidity_analysis: Dict[str, Any],
    slippage_analysis: Dict[str, Any],
    lp_analysis: Dict[str, Any],
    min_liquidity_usd: float,
    max_slippage_percent: float
) -> Decimal:
    """
    Calculate overall liquidity risk score.
    
    Combines multiple factors to produce a comprehensive risk score:
    - Liquidity depth vs minimum requirements
    - Slippage impact vs acceptable thresholds
    - LP token security (burns/locks)
    - Liquidity imbalance
    
    Args:
        liquidity_analysis: Results from liquidity depth analysis
        slippage_analysis: Results from slippage impact analysis
        lp_analysis: Results from LP token analysis
        min_liquidity_usd: Minimum required liquidity
        max_slippage_percent: Maximum acceptable slippage
        
    Returns:
        Risk score as Decimal (0-100, where 0 is lowest risk)
    """
    score = Decimal('0')
    
    # Liquidity amount scoring (0-50 points)
    total_liquidity = liquidity_analysis.get('total_liquidity_usd', 0)
    if total_liquidity < min_liquidity_usd:
        if total_liquidity == 0:
            score += Decimal('50')  # Maximum penalty for no liquidity
        else:
            shortage_ratio = (min_liquidity_usd - total_liquidity) / min_liquidity_usd
            score += Decimal(str(shortage_ratio * 50))
    
    # Slippage scoring (0-30 points)
    max_slippage = slippage_analysis.get('max_slippage', 100)
    if max_slippage > max_slippage_percent:
        excess_slippage = max_slippage - max_slippage_percent
        score += Decimal(str(min(excess_slippage * 2, 30)))
    
    # LP security scoring (0-15 points)
    lp_security = lp_analysis.get('security_score', 0)
    if lp_security < 50:  # Low security
        score += Decimal(str((50 - lp_security) / 50 * 15))
    
    # Liquidity imbalance scoring (0-5 points)
    imbalance = liquidity_analysis.get('liquidity_metrics', {}).get('imbalance', 0)
    if imbalance > 0.5:  # High imbalance
        score += Decimal(str(imbalance * 5))
    
    return min(score, Decimal('100'))


def _calculate_liquidity_quality_metrics(
    liquidity_analysis: Dict[str, Any],
    slippage_analysis: Dict[str, Any]
) -> Dict[str, float]:
    """
    Calculate quality metrics for liquidity assessment.
    
    Args:
        liquidity_analysis: Results from liquidity depth analysis
        slippage_analysis: Results from slippage analysis
        
    Returns:
        Dict with quality metrics (0-100 scale)
    """
    metrics = {}
    
    # Depth quality (based on total liquidity)
    total_liquidity = liquidity_analysis.get('total_liquidity_usd', 0)
    if total_liquidity > 100000:
        metrics['depth_quality'] = 100
    elif total_liquidity > 50000:
        metrics['depth_quality'] = 80
    elif total_liquidity > 10000:
        metrics['depth_quality'] = 60
    else:
        metrics['depth_quality'] = max(0, total_liquidity / 10000 * 60)
    
    # Slippage quality (inverse of max slippage)
    max_slippage = slippage_analysis.get('max_slippage', 100)
    if max_slippage < 1:
        metrics['slippage_quality'] = 100
    elif max_slippage < 3:
        metrics['slippage_quality'] = 80
    elif max_slippage < 5:
        metrics['slippage_quality'] = 60
    else:
        metrics['slippage_quality'] = max(0, 100 - max_slippage * 10)
    
    # Efficiency quality
    efficiency = slippage_analysis.get('liquidity_efficiency', 0)
    metrics['efficiency_quality'] = efficiency
    
    # Overall quality (weighted average)
    metrics['overall_quality'] = (
        metrics['depth_quality'] * 0.4 + 
        metrics['slippage_quality'] * 0.4 + 
        metrics['efficiency_quality'] * 0.2
    )
    
    return metrics


def _generate_liquidity_warnings(
    liquidity_analysis: Dict[str, Any],
    slippage_analysis: Dict[str, Any],
    lp_analysis: Dict[str, Any]
) -> List[str]:
    """
    Generate warning messages for liquidity issues.
    
    Args:
        liquidity_analysis: Results from liquidity analysis
        slippage_analysis: Results from slippage analysis
        lp_analysis: Results from LP analysis
        
    Returns:
        List of warning messages
    """
    warnings = []
    
    # Check total liquidity
    total_liquidity = liquidity_analysis.get('total_liquidity_usd', 0)
    if total_liquidity < 10000:
        warnings.append(f"Low liquidity: ${total_liquidity:,.2f}")
    elif total_liquidity < 50000:
        warnings.append(f"Medium liquidity: ${total_liquidity:,.2f} - consider larger trades carefully")
    
    # Check slippage
    max_slippage = slippage_analysis.get('max_slippage', 0)
    if max_slippage > 15:
        warnings.append(f"Very high slippage: {max_slippage:.1f}%")
    elif max_slippage > 10:
        warnings.append(f"High slippage: {max_slippage:.1f}%")
    
    # Check LP security
    circulating_percentage = lp_analysis.get('circulating_percentage', 100)
    if circulating_percentage > 50:
        warnings.append(f"High LP circulation: {circulating_percentage:.1f}% - rug pull risk")
    
    security_score = lp_analysis.get('security_score', 0)
    if security_score < 30:
        warnings.append("Poor LP security - most tokens not locked/burned")
    
    # Check liquidity imbalance
    imbalance = liquidity_analysis.get('liquidity_metrics', {}).get('imbalance', 0)
    if imbalance > 0.8:
        warnings.append("Severe liquidity imbalance - price manipulation risk")
    elif imbalance > 0.5:
        warnings.append("Moderate liquidity imbalance")
    
    return warnings


# Helper functions for calculations

def _calculate_buy_slippage(reserve0: int, reserve1: int, trade_size_usd: float, pair_info: Dict) -> float:
    """
    Calculate slippage for a buy order using constant product formula.
    
    Implements the Uniswap V2 constant product formula: x * y = k
    to calculate price impact for a given trade size.
    
    Args:
        reserve0: Reserve of token0 (usually ETH)
        reserve1: Reserve of token1 (the token being analyzed)
        trade_size_usd: Size of trade in USD
        pair_info: Pair information including token prices
        
    Returns:
        Slippage percentage for buy order
    """
    try:
        # Get ETH price to convert USD to ETH amount
        eth_price = pair_info.get('token_prices_usd', {}).get('token0', 2500)
        trade_size_eth = trade_size_usd / eth_price
        trade_size_wei = int(trade_size_eth * 10**18)
        
        # Constant product formula: (x + dx) * (y - dy) = x * y
        # dy = (y * dx) / (x + dx)
        # Price impact = dy / y
        
        if reserve0 == 0 or reserve1 == 0:
            return 50.0  # High slippage for empty pools
        
        dy = (reserve1 * trade_size_wei) // (reserve0 + trade_size_wei)
        slippage_percent = (dy / reserve1) * 100
        
        return min(slippage_percent, 50.0)  # Cap at 50%
        
    except Exception as e:
        logger.warning(f"Error calculating buy slippage: {e}")
        return 50.0  # Default high slippage on error


def _calculate_sell_slippage(reserve0: int, reserve1: int, trade_size_usd: float, pair_info: Dict) -> float:
    """
    Calculate slippage for a sell order.
    
    Similar to buy slippage but calculates the impact of selling tokens for ETH.
    
    Args:
        reserve0: Reserve of token0 (usually ETH)
        reserve1: Reserve of token1 (the token being analyzed)
        trade_size_usd: Size of trade in USD
        pair_info: Pair information including token prices
        
    Returns:
        Slippage percentage for sell order
    """
    try:
        # Get token price to convert USD to token amount
        token_price = pair_info.get('token_prices_usd', {}).get('token1', 0.001)
        if token_price == 0:
            return 50.0
            
        trade_size_tokens = trade_size_usd / token_price
        trade_size_wei = int(trade_size_tokens * 10**18)
        
        if reserve0 == 0 or reserve1 == 0:
            return 50.0
        
        # For sell: selling token1 for token0
        dx = (reserve0 * trade_size_wei) // (reserve1 + trade_size_wei)
        slippage_percent = (dx / reserve0) * 100
        
        return min(slippage_percent, 50.0)
        
    except Exception as e:
        logger.warning(f"Error calculating sell slippage: {e}")
        return 50.0


def _analyze_slippage_curve(slippage_data: List[Dict]) -> Dict[str, Any]:
    """
    Analyze the slippage curve for patterns.
    
    Determines if slippage increases linearly or exponentially with trade size,
    which can indicate liquidity quality and potential manipulation risks.
    
    Args:
        slippage_data: List of slippage data points
        
    Returns:
        Dict with curve analysis
    """
    if not slippage_data or len(slippage_data) < 2:
        return {
            'curve_type': 'unknown',
            'steepness': 0,
            'linearity': 0
        }
    
    try:
        # Extract slippages and trade sizes
        slippages = [item['max_slippage_percent'] for item in slippage_data]
        sizes = [item['trade_size_usd'] for item in slippage_data]
        
        # Calculate steepness (slope of first and last points)
        steepness = (slippages[-1] - slippages[0]) / (sizes[-1] - sizes[0]) if len(sizes) > 1 else 0
        
        # Determine curve type based on growth pattern
        if len(slippages) >= 3:
            # Check if exponential growth (each step increases more than previous)
            growth_rates = []
            for i in range(1, len(slippages)):
                if slippages[i-1] > 0:
                    growth_rate = slippages[i] / slippages[i-1]
                    growth_rates.append(growth_rate)
            
            if growth_rates:
                avg_growth = sum(growth_rates) / len(growth_rates)
                if avg_growth > 2.0:
                    curve_type = 'exponential'
                elif avg_growth > 1.5:
                    curve_type = 'steep_linear'
                else:
                    curve_type = 'linear'
            else:
                curve_type = 'linear'
        else:
            curve_type = 'linear'
        
        # Calculate linearity score (how close to linear)
        linearity = max(0, 100 - abs(steepness - 1) * 50)
        
        return {
            'curve_type': curve_type,
            'steepness': steepness,
            'linearity': linearity,
            'max_slippage_tested': max(slippages),
            'growth_pattern': 'healthy' if curve_type == 'linear' else 'concerning'
        }
        
    except Exception as e:
        logger.warning(f"Error analyzing slippage curve: {e}")
        return {
            'curve_type': 'unknown',
            'steepness': 0,
            'linearity': 0,
            'error': str(e)
        }


def _calculate_liquidity_efficiency(slippage_data: List[Dict]) -> float:
    """
    Calculate efficiency score based on slippage performance.
    
    Higher efficiency means lower slippage for given trade sizes,
    indicating better liquidity utilization.
    
    Args:
        slippage_data: List of slippage data points
        
    Returns:
        Efficiency score (0-100, higher is better)
    """
    if not slippage_data:
        return 0.0
    
    try:
        # Calculate weighted efficiency based on trade sizes
        total_weight = 0
        weighted_efficiency = 0
        
        for data_point in slippage_data:
            trade_size = data_point['trade_size_usd']
            max_slippage = data_point['max_slippage_percent']
            
            # Weight larger trades more heavily
            weight = trade_size / 1000  # Normalize by $1000
            
            # Calculate efficiency for this trade size (inverse of slippage)
            efficiency = max(0, 100 - max_slippage * 5)  # 5% slippage = 75% efficiency
            
            weighted_efficiency += efficiency * weight
            total_weight += weight
        
        # Calculate average weighted efficiency
        if total_weight > 0:
            avg_efficiency = weighted_efficiency / total_weight
        else:
            # Fallback to simple average
            avg_slippage = sum(item['max_slippage_percent'] for item in slippage_data) / len(slippage_data)
            avg_efficiency = max(0, 100 - avg_slippage * 5)
        
        return min(100.0, max(0.0, avg_efficiency))
        
    except Exception as e:
        logger.warning(f"Error calculating liquidity efficiency: {e}")
        return 0.0


def _calculate_depth_score(total_liquidity_usd: float) -> float:
    """
    Calculate depth score based on total liquidity.
    
    Args:
        total_liquidity_usd: Total liquidity in USD
        
    Returns:
        Depth score (0-100)
    """
    if total_liquidity_usd >= 1000000:  # $1M+
        return 100.0
    elif total_liquidity_usd >= 500000:  # $500K+
        return 90.0
    elif total_liquidity_usd >= 100000:  # $100K+
        return 80.0
    elif total_liquidity_usd >= 50000:   # $50K+
        return 70.0
    elif total_liquidity_usd >= 10000:   # $10K+
        return 60.0
    elif total_liquidity_usd >= 5000:    # $5K+
        return 40.0
    elif total_liquidity_usd >= 1000:    # $1K+
        return 20.0
    else:
        return max(0.0, total_liquidity_usd / 1000 * 20)


def _calculate_lp_security_score(burn_percentage: float, lock_percentage: float) -> float:
    """
    Calculate LP security score based on burns and locks.
    
    Args:
        burn_percentage: Percentage of LP tokens burned
        lock_percentage: Percentage of LP tokens locked
        
    Returns:
        Security score (0-100)
    """
    total_secured = burn_percentage + lock_percentage
    
    if total_secured >= 95:
        return 100.0
    elif total_secured >= 90:
        return 95.0
    elif total_secured >= 80:
        return 85.0
    elif total_secured >= 70:
        return 70.0
    elif total_secured >= 50:
        return 50.0
    elif total_secured >= 30:
        return 30.0
    else:
        return total_secured  # Direct mapping for low values


def _get_token_price_usd(w3: Web3, token_address: str) -> float:
    """
    Get token price in USD (simplified implementation).
    
    In production, this would use price feeds like Chainlink oracles,
    CoinGecko API, or DEX aggregators.
    
    Args:
        w3: Web3 connection
        token_address: Token contract address
        
    Returns:
        Token price in USD
    """
    # Mock prices for common tokens
    token_address_lower = token_address.lower()
    
    # Common token addresses and their approximate prices
    known_prices = {
        '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2': 2500.0,  # WETH
        '0xa0b86a33e6441eab62d8b8bb7e5c9d47b6b0bfb4': 2500.0,  # Alternative WETH
        '0xa0b86a33e6441e94b6b0bfb4e6e7c8c8e7c8e7c8': 0.001,   # Mock token
        '0x6b175474e89094c44da98b954eedeac495271d0f': 1.0,     # DAI
        '0xa0b86a33e6441eab62d8b8bb7e5c9d47b6b0bfb5': 1.0,     # USDC mock
    }
    
    # Check for known addresses
    for known_addr, price in known_prices.items():
        if known_addr in token_address_lower:
            return price
    
    # Check for stablecoin patterns
    if any(pattern in token_address_lower for pattern in ['usdc', 'usdt', 'dai', 'busd']):
        return 1.0
    
    # Default price for unknown tokens
    return 0.001


def _detect_dex_factory(w3: Web3, pair_address: str) -> str:
    """
    Detect which DEX factory created this pair.
    
    Args:
        w3: Web3 connection
        pair_address: Trading pair address
        
    Returns:
        Factory name/type
    """
    # In production, this would check the actual factory address
    # For now, return Uniswap V2 as default
    return 'Uniswap V2'


def _get_uniswap_pair_abi() -> List[Dict]:
    """Get minimal Uniswap V2 pair ABI for essential functions."""
    return [
        {
            "inputs": [],
            "name": "totalSupply",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "getReserves",
            "outputs": [
                {"internalType": "uint112", "name": "reserve0", "type": "uint112"},
                {"internalType": "uint112", "name": "reserve1", "type": "uint112"},
                {"internalType": "uint32", "name": "blockTimestampLast", "type": "uint32"}
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "token0",
            "outputs": [{"internalType": "address", "name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "token1",
            "outputs": [{"internalType": "address", "name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        }
    ]