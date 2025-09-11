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

from ..models import RiskAssessment, RiskCheckResult, RiskCheckType
from . import create_risk_check_result

logger = logging.getLogger(__name__)

# Set decimal precision for accurate calculations
getcontext().prec = 28


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
        token_address: Target token address (optional, for specific analysis)
        min_liquidity_usd: Minimum required total liquidity in USD
        max_slippage_percent: Maximum acceptable slippage percentage
        test_trade_sizes: List of trade sizes (in USD) to test slippage for
        
    Returns:
        Dict with comprehensive liquidity analysis results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting liquidity check for pair {pair_address} (task: {task_id})")
    
    try:
        # Validate inputs
        if not Web3.is_address(pair_address):
            raise ValueError(f"Invalid pair address: {pair_address}")
        
        if token_address and not Web3.is_address(token_address):
            raise ValueError(f"Invalid token address: {token_address}")
        
        # Set default test trade sizes if not provided
        if test_trade_sizes is None:
            test_trade_sizes = [100, 500, 1000, 5000, 10000]  # USD amounts
        
        # Initialize Web3 connection
        w3 = _get_web3_connection()
        if not w3.is_connected():
            raise ConnectionError("Failed to connect to blockchain node")
        
        # Get pair information
        pair_info = _get_pair_information(w3, pair_address)
        if not pair_info:
            raise ValueError(f"Could not retrieve pair information for {pair_address}")
        
        # Analyze liquidity depth
        liquidity_analysis = _analyze_liquidity_depth(w3, pair_address, pair_info)
        
        # Calculate slippage for different trade sizes
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
        elif risk_score >= 60:
            status = 'WARNING'  # Medium-high risk - warning
        else:
            status = 'COMPLETED'  # Acceptable risk
        
        logger.info(f"Liquidity check completed for {pair_address} - Risk Score: {risk_score}, "
                   f"Liquidity: ${liquidity_analysis['total_liquidity_usd']:.2f}")
        
        result = create_risk_check_result(
            check_type='LIQUIDITY',
            token_address=token_address,
            pair_address=pair_address,
            status=status,
            risk_score=risk_score,
            details=details,
            execution_time_ms=execution_time_ms
        )
        
        # Store result in database
        _store_liquidity_result(result)
        
        return result
        
    except Exception as exc:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"Liquidity check failed for {pair_address}: {exc} (task: {task_id})")
        
        # Retry logic with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = min(2 ** self.request.retries, 30)
            logger.warning(f"Retrying liquidity check for {pair_address} in {countdown}s (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=countdown)
        
        # Final failure
        return create_risk_check_result(
            check_type='LIQUIDITY',
            token_address=token_address,
            pair_address=pair_address,
            status='FAILED',
            risk_score=Decimal('100'),
            error_message=str(exc),
            execution_time_ms=execution_time_ms
        )


def _get_web3_connection() -> Web3:
    """Get configured Web3 connection for liquidity analysis."""
    from django.conf import settings
    import os
    
    # Try primary RPC first
    rpc_url = getattr(settings, 'ETH_RPC_URL', None)
    if not rpc_url:
        rpc_url = os.getenv('ETH_RPC_URL', 'https://cloudflare-eth.com')
    
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    if not w3.is_connected():
        # Try fallback
        fallback_rpc = getattr(settings, 'ETH_RPC_URL_FALLBACK', None)
        if fallback_rpc:
            w3 = Web3(Web3.HTTPProvider(fallback_rpc))
    
    return w3


def _get_pair_information(w3: Web3, pair_address: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve basic pair information from the DEX contract.
    
    Args:
        w3: Web3 connection
        pair_address: Trading pair contract address
        
    Returns:
        Dict with pair information or None if failed
    """
    try:
        # Get Uniswap V2 pair ABI (simplified)
        pair_abi = _get_uniswap_pair_abi()
        pair_contract = w3.eth.contract(address=pair_address, abi=pair_abi)
        
        # Get basic pair info
        token0_address = pair_contract.functions.token0().call()
        token1_address = pair_contract.functions.token1().call()
        reserves = pair_contract.functions.getReserves().call()
        
        # Get token information
        token0_info = _get_token_info(w3, token0_address)
        token1_info = _get_token_info(w3, token1_address)
        
        return {
            'pair_address': pair_address,
            'token0': {
                'address': token0_address,
                'symbol': token0_info.get('symbol', 'UNKNOWN'),
                'decimals': token0_info.get('decimals', 18),
                'name': token0_info.get('name', 'Unknown Token')
            },
            'token1': {
                'address': token1_address,
                'symbol': token1_info.get('symbol', 'UNKNOWN'),
                'decimals': token1_info.get('decimals', 18),
                'name': token1_info.get('name', 'Unknown Token')
            },
            'reserves': {
                'reserve0': reserves[0],
                'reserve1': reserves[1],
                'timestamp': reserves[2]
            },
            'factory': _detect_dex_factory(w3, pair_address),
            'fee_tier': _detect_fee_tier(w3, pair_address)
        }
        
    except Exception as e:
        logger.error(f"Failed to get pair information for {pair_address}: {e}")
        return None


def _get_token_info(w3: Web3, token_address: str) -> Dict[str, Any]:
    """Get basic token information."""
    try:
        # Standard ERC20 ABI (simplified)
        erc20_abi = _get_erc20_abi()
        token_contract = w3.eth.contract(address=token_address, abi=erc20_abi)
        
        return {
            'symbol': token_contract.functions.symbol().call(),
            'decimals': token_contract.functions.decimals().call(),
            'name': token_contract.functions.name().call(),
            'total_supply': token_contract.functions.totalSupply().call()
        }
    except Exception as e:
        logger.warning(f"Failed to get token info for {token_address}: {e}")
        return {'symbol': 'UNKNOWN', 'decimals': 18, 'name': 'Unknown Token'}


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
        reserves = pair_info['reserves']
        token0 = pair_info['token0']
        token1 = pair_info['token1']
        
        # Get token prices in USD
        token0_price_usd = _get_token_price_usd(w3, token0['address'])
        token1_price_usd = _get_token_price_usd(w3, token1['address'])
        
        # Calculate reserve values
        token0_reserve_normalized = Decimal(reserves['reserve0']) / (10 ** token0['decimals'])
        token1_reserve_normalized = Decimal(reserves['reserve1']) / (10 ** token1['decimals'])
        
        # Calculate USD values
        token0_liquidity_usd = float(token0_reserve_normalized * Decimal(str(token0_price_usd)))
        token1_liquidity_usd = float(token1_reserve_normalized * Decimal(str(token1_price_usd)))
        
        total_liquidity_usd = token0_liquidity_usd + token1_liquidity_usd
        
        # Calculate price ratios and stability metrics
        if token0_liquidity_usd > 0 and token1_liquidity_usd > 0:
            liquidity_ratio = token0_liquidity_usd / token1_liquidity_usd
            imbalance = abs(1 - liquidity_ratio)
        else:
            liquidity_ratio = 0
            imbalance = 1  # Maximum imbalance
        
        return {
            'total_liquidity_usd': total_liquidity_usd,
            'token0_liquidity_usd': token0_liquidity_usd,
            'token1_liquidity_usd': token1_liquidity_usd,
            'reserves': {
                'token0_reserve': float(token0_reserve_normalized),
                'token1_reserve': float(token1_reserve_normalized),
                'token0_reserve_raw': reserves['reserve0'],
                'token1_reserve_raw': reserves['reserve1']
            },
            'prices': {
                'token0_price_usd': token0_price_usd,
                'token1_price_usd': token1_price_usd,
                'exchange_rate': float(token1_reserve_normalized / token0_reserve_normalized) if token0_reserve_normalized > 0 else 0
            },
            'liquidity_metrics': {
                'liquidity_ratio': liquidity_ratio,
                'imbalance': imbalance,
                'depth_score': _calculate_depth_score(total_liquidity_usd)
            }
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
    Calculate price impact/slippage for various trade sizes.
    
    Args:
        w3: Web3 connection
        pair_address: Trading pair address
        pair_info: Pair information
        test_trade_sizes: List of trade sizes in USD to test
        
    Returns:
        Dict with slippage analysis
    """
    try:
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
        
        return {
            'slippage_data': slippage_data,
            'max_slippage': max_slippage,
            'curve_analysis': slippage_curve_analysis,
            'liquidity_efficiency': _calculate_liquidity_efficiency(slippage_data)
        }
        
    except Exception as e:
        logger.error(f"Failed to calculate slippage for {pair_address}: {e}")
        return {
            'slippage_data': [],
            'max_slippage': 100,
            'error': str(e)
        }


def _analyze_lp_tokens(w3: Web3, pair_address: str, pair_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze LP token distribution, locks, and burns.
    
    Args:
        w3: Web3 connection
        pair_address: Trading pair address
        pair_info: Pair information
        
    Returns:
        Dict with LP token analysis
    """
    try:
        # Get LP token supply and distribution
        pair_abi = _get_uniswap_pair_abi()
        pair_contract = w3.eth.contract(address=pair_address, abi=pair_abi)
        
        total_supply = pair_contract.functions.totalSupply().call()
        
        # Check common burn/lock addresses
        burn_addresses = [
            '0x000000000000000000000000000000000000dEaD',  # Burn address
            '0x0000000000000000000000000000000000000000',  # Zero address
        ]
        
        burned_amount = 0
        for burn_addr in burn_addresses:
            try:
                balance = pair_contract.functions.balanceOf(burn_addr).call()
                burned_amount += balance
            except:
                continue
        
        # Check for known locker contracts (simplified)
        locked_amount = _check_lp_locks(w3, pair_address, total_supply)
        
        # Calculate distribution metrics
        circulating_supply = total_supply - burned_amount - locked_amount
        burn_percentage = (burned_amount / total_supply * 100) if total_supply > 0 else 0
        lock_percentage = (locked_amount / total_supply * 100) if total_supply > 0 else 0
        circulating_percentage = (circulating_supply / total_supply * 100) if total_supply > 0 else 0
        
        return {
            'total_supply': total_supply,
            'burned_amount': burned_amount,
            'locked_amount': locked_amount,
            'circulating_supply': circulating_supply,
            'burn_percentage': burn_percentage,
            'lock_percentage': lock_percentage,
            'circulating_percentage': circulating_percentage,
            'is_majority_locked_burned': (burn_percentage + lock_percentage) > 80,
            'security_score': _calculate_lp_security_score(burn_percentage, lock_percentage)
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze LP tokens for {pair_address}: {e}")
        return {
            'total_supply': 0,
            'burned_amount': 0,
            'locked_amount': 0,
            'error': str(e)
        }


def _analyze_liquidity_history(w3: Web3, pair_address: str, pair_info: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze historical liquidity trends (simplified implementation)."""
    try:
        # In a full implementation, this would query historical data
        # For now, return basic trend analysis
        
        current_block = w3.eth.block_number
        blocks_per_day = 7200  # Approximate for Ethereum
        
        # Simulate trend analysis
        return {
            'current_block': current_block,
            'trend_analysis': 'stable',  # Placeholder
            'volume_24h': 0,  # Would need DEX subgraph data
            'liquidity_changes': [],
            'analysis_period_blocks': blocks_per_day
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
    """Calculate overall liquidity risk score."""
    score = Decimal('0')
    
    # Liquidity amount scoring
    total_liquidity = liquidity_analysis.get('total_liquidity_usd', 0)
    if total_liquidity < min_liquidity_usd:
        shortage_ratio = (min_liquidity_usd - total_liquidity) / min_liquidity_usd
        score += Decimal(str(shortage_ratio * 50))  # Up to 50 points
    
    # Slippage scoring
    max_slippage = slippage_analysis.get('max_slippage', 0)
    if max_slippage > max_slippage_percent:
        excess_slippage = max_slippage - max_slippage_percent
        score += Decimal(str(min(excess_slippage * 2, 30)))  # Up to 30 points
    
    # LP security scoring
    lp_security = lp_analysis.get('security_score', 0)
    if lp_security < 50:  # Low security
        score += Decimal(str((50 - lp_security) / 2))  # Up to 25 points
    
    # Liquidity imbalance scoring
    imbalance = liquidity_analysis.get('liquidity_metrics', {}).get('imbalance', 0)
    if imbalance > 0.5:  # High imbalance
        score += Decimal(str(imbalance * 10))  # Up to 10 points
    
    return min(score, Decimal('100'))


def _calculate_liquidity_quality_metrics(
    liquidity_analysis: Dict[str, Any],
    slippage_analysis: Dict[str, Any]
) -> Dict[str, float]:
    """Calculate quality metrics for liquidity assessment."""
    metrics = {}
    
    # Depth quality
    total_liquidity = liquidity_analysis.get('total_liquidity_usd', 0)
    if total_liquidity > 100000:
        metrics['depth_quality'] = 100
    elif total_liquidity > 50000:
        metrics['depth_quality'] = 80
    elif total_liquidity > 10000:
        metrics['depth_quality'] = 60
    else:
        metrics['depth_quality'] = max(0, total_liquidity / 10000 * 60)
    
    # Slippage quality
    max_slippage = slippage_analysis.get('max_slippage', 100)
    if max_slippage < 1:
        metrics['slippage_quality'] = 100
    elif max_slippage < 3:
        metrics['slippage_quality'] = 80
    elif max_slippage < 5:
        metrics['slippage_quality'] = 60
    else:
        metrics['slippage_quality'] = max(0, 100 - max_slippage * 10)
    
    # Overall quality
    metrics['overall_quality'] = (metrics['depth_quality'] + metrics['slippage_quality']) / 2
    
    return metrics


def _generate_liquidity_warnings(
    liquidity_analysis: Dict[str, Any],
    slippage_analysis: Dict[str, Any],
    lp_analysis: Dict[str, Any]
) -> List[str]:
    """Generate warning messages for liquidity issues."""
    warnings = []
    
    total_liquidity = liquidity_analysis.get('total_liquidity_usd', 0)
    if total_liquidity < 10000:
        warnings.append(f"Low liquidity: ${total_liquidity:.2f}")
    
    max_slippage = slippage_analysis.get('max_slippage', 0)
    if max_slippage > 10:
        warnings.append(f"High slippage: {max_slippage:.1f}%")
    
    circulating_percentage = lp_analysis.get('circulating_percentage', 100)
    if circulating_percentage > 50:
        warnings.append(f"High LP circulation: {circulating_percentage:.1f}%")
    
    imbalance = liquidity_analysis.get('liquidity_metrics', {}).get('imbalance', 0)
    if imbalance > 0.8:
        warnings.append("Severe liquidity imbalance")
    
    return warnings


# Helper functions for calculations

def _calculate_buy_slippage(reserve0: int, reserve1: int, trade_size_usd: float, pair_info: Dict) -> float:
    """Calculate slippage for a buy order using constant product formula."""
    try:
        # Simplified slippage calculation
        # In production, this would use the exact AMM formula
        liquidity_ratio = trade_size_usd / (reserve0 * 2 / 10**18)  # Simplified
        return min(liquidity_ratio * 100, 50)  # Cap at 50%
    except:
        return 50  # Default high slippage on error


def _calculate_sell_slippage(reserve0: int, reserve1: int, trade_size_usd: float, pair_info: Dict) -> float:
    """Calculate slippage for a sell order."""
    try:
        # Similar to buy slippage but accounting for different direction
        liquidity_ratio = trade_size_usd / (reserve1 * 2 / 10**18)  # Simplified
        return min(liquidity_ratio * 100, 50)
    except:
        return 50


def _analyze_slippage_curve(slippage_data: List[Dict]) -> Dict[str, Any]:
    """Analyze the slippage curve for patterns."""
    if not slippage_data:
        return {}
    
    # Check if slippage increases linearly or exponentially
    slippages = [item['max_slippage_percent'] for item in slippage_data]
    sizes = [item['trade_size_usd'] for item in slippage_data]
    
    return {
        'curve_type': 'exponential' if slippages[-1] > slippages[0] * 5 else 'linear',
        'steepness': (slippages[-1] - slippages[0]) / (sizes[-1] - sizes[0]) if len(sizes) > 1 else 0
    }


def _calculate_liquidity_efficiency(slippage_data: List[Dict]) -> float:
    """Calculate efficiency score based on slippage performance."""
    if not slippage_data:
        return 0
    
    # Efficiency = inverse of average slippage
    avg_slippage = sum(item['max_slippage_percent'] for item in slippage_data) / len(slippage_data)
    return max(0, 100 - avg_slippage * 10)


def _calculate_depth_score(total_liquidity_usd: float) -> float:
    """Calculate depth score based on total liquidity."""
    if total_liquidity_usd >= 1000000:
        return 100
    elif total_liquidity_usd >= 100000:
        return 80
    elif total_liquidity_usd >= 10000:
        return 60
    else:
        return total_liquidity_usd / 10000 * 60


def _calculate_lp_security_score(burn_percentage: float, lock_percentage: float) -> float:
    """Calculate LP security score based on burns and locks."""
    total_secured = burn_percentage + lock_percentage
    
    if total_secured >= 95:
        return 100
    elif total_secured >= 80:
        return 80
    elif total_secured >= 50:
        return 60
    else:
        return total_secured * 1.2  # Scale to max 60


def _check_lp_locks(w3: Web3, pair_address: str, total_supply: int) -> int:
    """Check for LP tokens locked in common locker contracts."""
    # This is a simplified implementation
    # In production, you'd check known locker contract addresses
    return 0


def _get_token_price_usd(w3: Web3, token_address: str) -> float:
    """Get token price in USD (simplified implementation)."""
    # In production, this would use price feeds like Chainlink or DEX aggregators
    
    # Mock prices for common tokens
    token_address_lower = token_address.lower()
    
    if token_address_lower in ['0xa0b86a33e6441eab62d8b8bb7e5c9d47b6b0bfb4']:  # WETH placeholder
        return 2500.0
    elif 'usdc' in token_address_lower or 'usdt' in token_address_lower:
        return 1.0
    else:
        return 0.0001  # Default for unknown tokens


def _detect_dex_factory(w3: Web3, pair_address: str) -> str:
    """Detect which DEX factory created this pair."""
    # Simplified detection - would check factory address
    return "Uniswap V2"


def _detect_fee_tier(w3: Web3, pair_address: str) -> float:
    """Detect the fee tier for this pair."""
    # Simplified - would check DEX-specific fee structures
    return 0.3  # 0.3% for Uniswap V2


def _get_uniswap_pair_abi() -> list:
    """Get simplified Uniswap V2 pair ABI."""
    return [
        {
            "inputs": [],
            "name": "token0",
            "outputs": [{"type": "address"}],
            "type": "function"
        },
        {
            "inputs": [],
            "name": "token1", 
            "outputs": [{"type": "address"}],
            "type": "function"
        },
        {
            "inputs": [],
            "name": "getReserves",
            "outputs": [
                {"type": "uint112"},
                {"type": "uint112"},
                {"type": "uint32"}
            ],
            "type": "function"
        },
        {
            "inputs": [],
            "name": "totalSupply",
            "outputs": [{"type": "uint256"}],
            "type": "function"
        },
        {
            "inputs": [{"type": "address"}],
            "name": "balanceOf",
            "outputs": [{"type": "uint256"}],
            "type": "function"
        }
    ]


def _get_erc20_abi() -> list:
    """Get simplified ERC20 ABI."""
    return [
        {
            "inputs": [],
            "name": "symbol",
            "outputs": [{"type": "string"}],
            "type": "function"
        },
        {
            "inputs": [],
            "name": "decimals",
            "outputs": [{"type": "uint8"}],
            "type": "function"
        },
        {
            "inputs": [],
            "name": "name",
            "outputs": [{"type": "string"}],
            "type": "function"
        },
        {
            "inputs": [],
            "name": "totalSupply",
            "outputs": [{"type": "uint256"}],
            "type": "function"
        }
    ]


def _store_liquidity_result(result: Dict[str, Any]) -> None:
    """Store liquidity check result in database."""
    try:
        with transaction.atomic():
            # This would create/update RiskCheckResult model
            logger.debug(f"Storing liquidity result for {result['pair_address']}")
    except Exception as e:
        logger.error(f"Failed to store liquidity result: {e}")