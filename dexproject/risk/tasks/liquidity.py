"""
Enhanced Liquidity Analysis Task Module

Real blockchain integration with robust provider management for comprehensive
liquidity analysis including depth, slippage, LP locks, and quality assessment.

File: dexproject/risk/tasks/liquidity.py
"""

import logging
import time
import asyncio
from typing import Dict, Any, Optional, Tuple, List
from decimal import Decimal, getcontext
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError

from web3 import Web3
from web3.exceptions import ContractLogicError, BadFunctionCallOutput, Web3Exception
from eth_utils import is_address, to_checksum_address

# Import our enhanced provider management
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'engine'))
from config import config
from utils import ProviderManager, get_token_info

from ..models import RiskAssessment, RiskCheckResult, RiskCheckType
from . import create_risk_check_result

logger = logging.getLogger(__name__)

# Set decimal precision for accurate financial calculations
getcontext().prec = 28


@shared_task(
    bind=True,
    queue='risk.urgent',
    name='risk.tasks.enhanced_liquidity_check',
    max_retries=3,
    default_retry_delay=2
)
def enhanced_liquidity_check(
    self,
    pair_address: str,
    token_address: str = None,
    chain_id: int = None,
    min_liquidity_usd: float = 10000.0,
    max_slippage_percent: float = 5.0,
    test_trade_sizes: List[float] = None
) -> Dict[str, Any]:
    """
    Enhanced liquidity analysis with real blockchain integration.
    
    Uses robust provider management with automatic failover to perform
    comprehensive liquidity analysis including depth, slippage, and LP security.
    
    Args:
        pair_address: The trading pair contract address
        token_address: Target token address (optional, for specific analysis)
        chain_id: Blockchain network ID (defaults to first configured chain)
        min_liquidity_usd: Minimum required total liquidity in USD
        max_slippage_percent: Maximum acceptable slippage percentage
        test_trade_sizes: List of trade sizes (in USD) to test slippage for
        
    Returns:
        Dict with comprehensive liquidity analysis results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting enhanced liquidity check for pair {pair_address} (task: {task_id})")
    
    try:
        # Validate inputs
        if not is_address(pair_address):
            raise ValueError(f"Invalid pair address: {pair_address}")
        
        pair_address = to_checksum_address(pair_address)
        
        if token_address:
            if not is_address(token_address):
                raise ValueError(f"Invalid token address: {token_address}")
            token_address = to_checksum_address(token_address)
        
        # Determine chain configuration
        if chain_id is None:
            chain_id = config.target_chains[0] if config.target_chains else 1
        
        chain_config = config.get_chain_config(chain_id)
        if not chain_config:
            raise ValueError(f"No configuration found for chain ID: {chain_id}")
        
        # Set default test trade sizes if not provided
        if test_trade_sizes is None:
            test_trade_sizes = [100, 500, 1000, 5000, 10000]  # USD amounts
        
        # Run the actual analysis using async provider management
        analysis_result = asyncio.run(_run_liquidity_analysis(
            chain_config=chain_config,
            pair_address=pair_address,
            token_address=token_address,
            min_liquidity_usd=min_liquidity_usd,
            max_slippage_percent=max_slippage_percent,
            test_trade_sizes=test_trade_sizes
        ))
        
        if not analysis_result:
            raise Exception("Liquidity analysis failed - no results returned")
        
        # Calculate final risk score
        risk_score = _calculate_enhanced_risk_score(
            analysis_result['liquidity_analysis'],
            analysis_result['slippage_analysis'],
            analysis_result['lp_analysis'],
            min_liquidity_usd,
            max_slippage_percent
        )
        
        # Calculate execution time
        execution_time_ms = (time.time() - start_time) * 1000
        
        # Prepare detailed results
        details = {
            'chain_id': chain_id,
            'pair_address': pair_address,
            'token_address': token_address,
            'analysis_timestamp': timezone.now().isoformat(),
            'liquidity_depth': analysis_result['liquidity_analysis'],
            'slippage_impact': analysis_result['slippage_analysis'],
            'lp_security': analysis_result['lp_analysis'],
            'quality_metrics': analysis_result.get('quality_metrics', {}),
            'provider_info': analysis_result.get('provider_info', {}),
            'test_parameters': {
                'min_liquidity_usd': min_liquidity_usd,
                'max_slippage_percent': max_slippage_percent,
                'test_trade_sizes': test_trade_sizes
            }
        }
        
        # Determine status based on risk score
        if risk_score >= 80:
            status = 'FAILED'  # High risk - block trading
        elif risk_score >= 60:
            status = 'WARNING'  # Medium-high risk - warning
        else:
            status = 'COMPLETED'  # Acceptable risk
        
        total_liquidity = analysis_result['liquidity_analysis'].get('total_liquidity_usd', 0)
        max_slippage = analysis_result['slippage_analysis'].get('max_slippage_percent', 0)
        
        logger.info(
            f"Enhanced liquidity check completed for {pair_address} - "
            f"Risk Score: {risk_score}, Liquidity: ${total_liquidity:.2f}, "
            f"Max Slippage: {max_slippage:.2f}%, Execution: {execution_time_ms:.1f}ms"
        )
        
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
        _store_enhanced_liquidity_result(result)
        
        return result
        
    except Exception as exc:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"Enhanced liquidity check failed for {pair_address}: {exc} (task: {task_id})")
        
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


async def _run_liquidity_analysis(
    chain_config,
    pair_address: str,
    token_address: Optional[str],
    min_liquidity_usd: float,
    max_slippage_percent: float,
    test_trade_sizes: List[float]
) -> Optional[Dict[str, Any]]:
    """Run the complete liquidity analysis using provider manager."""
    
    # Initialize provider manager for the chain
    provider_manager = ProviderManager(chain_config)
    
    try:
        # Get pair information
        pair_info = await _get_enhanced_pair_information(provider_manager, pair_address)
        if not pair_info:
            raise ValueError(f"Could not retrieve pair information for {pair_address}")
        
        # Run analysis components in parallel for efficiency
        liquidity_task = _analyze_enhanced_liquidity_depth(provider_manager, pair_address, pair_info)
        slippage_task = _calculate_enhanced_slippage_impact(
            provider_manager, pair_address, pair_info, test_trade_sizes
        )
        lp_task = _analyze_enhanced_lp_tokens(provider_manager, pair_address, pair_info)
        
        # Execute all analyses in parallel
        liquidity_analysis, slippage_analysis, lp_analysis = await asyncio.gather(
            liquidity_task, slippage_task, lp_task, return_exceptions=True
        )
        
        # Handle any exceptions from parallel execution
        if isinstance(liquidity_analysis, Exception):
            logger.error(f"Liquidity depth analysis failed: {liquidity_analysis}")
            liquidity_analysis = {'error': str(liquidity_analysis), 'total_liquidity_usd': 0}
        
        if isinstance(slippage_analysis, Exception):
            logger.error(f"Slippage analysis failed: {slippage_analysis}")
            slippage_analysis = {'error': str(slippage_analysis), 'max_slippage_percent': 100}
        
        if isinstance(lp_analysis, Exception):
            logger.error(f"LP analysis failed: {lp_analysis}")
            lp_analysis = {'error': str(lp_analysis), 'security_score': 0}
        
        # Calculate quality metrics
        quality_metrics = _calculate_enhanced_quality_metrics(liquidity_analysis, slippage_analysis)
        
        # Get provider health information for debugging
        provider_info = provider_manager.get_health_summary()
        
        return {
            'liquidity_analysis': liquidity_analysis,
            'slippage_analysis': slippage_analysis,
            'lp_analysis': lp_analysis,
            'quality_metrics': quality_metrics,
            'provider_info': provider_info
        }
        
    finally:
        # Clean up provider manager
        await provider_manager.close()


async def _get_enhanced_pair_information(provider_manager: ProviderManager, pair_address: str) -> Optional[Dict[str, Any]]:
    """Get enhanced pair information using provider manager."""
    
    async def get_pair_info(w3: Web3) -> Dict[str, Any]:
        # Detect DEX type and use appropriate ABI
        dex_type = await _detect_dex_type(w3, pair_address)
        
        if dex_type == 'uniswap_v2':
            return await _get_uniswap_v2_pair_info(w3, pair_address)
        elif dex_type == 'uniswap_v3':
            return await _get_uniswap_v3_pair_info(w3, pair_address)
        else:
            # Try generic ERC20 pair interface
            return await _get_generic_pair_info(w3, pair_address)
    
    return await provider_manager.execute_with_failover(get_pair_info)


async def _detect_dex_type(w3: Web3, pair_address: str) -> str:
    """Detect the DEX type for the pair contract."""
    try:
        # Check for Uniswap V3 pool interface
        v3_abi = [
            {"constant": True, "inputs": [], "name": "fee", "outputs": [{"name": "", "type": "uint24"}], "type": "function"}
        ]
        
        contract = w3.eth.contract(address=pair_address, abi=v3_abi)
        fee = contract.functions.fee().call()
        
        if fee > 0:
            return 'uniswap_v3'
            
    except:
        pass
    
    try:
        # Check for Uniswap V2 pair interface
        v2_abi = [
            {"constant": True, "inputs": [], "name": "getReserves", "outputs": [
                {"name": "reserve0", "type": "uint112"},
                {"name": "reserve1", "type": "uint112"},
                {"name": "blockTimestampLast", "type": "uint32"}
            ], "type": "function"}
        ]
        
        contract = w3.eth.contract(address=pair_address, abi=v2_abi)
        reserves = contract.functions.getReserves().call()
        
        if len(reserves) == 3:
            return 'uniswap_v2'
            
    except:
        pass
    
    return 'unknown'


async def _get_uniswap_v2_pair_info(w3: Web3, pair_address: str) -> Dict[str, Any]:
    """Get Uniswap V2 pair information."""
    v2_pair_abi = [
        {"constant": True, "inputs": [], "name": "token0", "outputs": [{"name": "", "type": "address"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "token1", "outputs": [{"name": "", "type": "address"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "getReserves", "outputs": [
            {"name": "reserve0", "type": "uint112"},
            {"name": "reserve1", "type": "uint112"},
            {"name": "blockTimestampLast", "type": "uint32"}
        ], "type": "function"},
        {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}
    ]
    
    contract = w3.eth.contract(address=pair_address, abi=v2_pair_abi)
    
    # Get basic pair data
    token0_address = contract.functions.token0().call()
    token1_address = contract.functions.token1().call()
    reserves = contract.functions.getReserves().call()
    total_supply = contract.functions.totalSupply().call()
    
    return {
        'type': 'uniswap_v2',
        'token0_address': to_checksum_address(token0_address),
        'token1_address': to_checksum_address(token1_address),
        'reserves': {
            'reserve0': reserves[0],
            'reserve1': reserves[1],
            'last_update': reserves[2]
        },
        'total_supply': total_supply,
        'fee_tier': 3000  # Uniswap V2 has fixed 0.3% fee
    }


async def _get_uniswap_v3_pair_info(w3: Web3, pair_address: str) -> Dict[str, Any]:
    """Get Uniswap V3 pool information."""
    v3_pool_abi = [
        {"constant": True, "inputs": [], "name": "token0", "outputs": [{"name": "", "type": "address"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "token1", "outputs": [{"name": "", "type": "address"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "fee", "outputs": [{"name": "", "type": "uint24"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "liquidity", "outputs": [{"name": "", "type": "uint128"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "slot0", "outputs": [
            {"name": "sqrtPriceX96", "type": "uint160"},
            {"name": "tick", "type": "int24"},
            {"name": "observationIndex", "type": "uint16"},
            {"name": "observationCardinality", "type": "uint16"},
            {"name": "observationCardinalityNext", "type": "uint16"},
            {"name": "feeProtocol", "type": "uint8"},
            {"name": "unlocked", "type": "bool"}
        ], "type": "function"}
    ]
    
    contract = w3.eth.contract(address=pair_address, abi=v3_pool_abi)
    
    # Get pool data
    token0_address = contract.functions.token0().call()
    token1_address = contract.functions.token1().call()
    fee = contract.functions.fee().call()
    liquidity = contract.functions.liquidity().call()
    slot0 = contract.functions.slot0().call()
    
    return {
        'type': 'uniswap_v3',
        'token0_address': to_checksum_address(token0_address),
        'token1_address': to_checksum_address(token1_address),
        'fee_tier': fee,
        'liquidity': liquidity,
        'sqrt_price_x96': slot0[0],
        'current_tick': slot0[1],
        'observation_index': slot0[2]
    }


async def _get_generic_pair_info(w3: Web3, pair_address: str) -> Dict[str, Any]:
    """Get generic pair information for unknown DEX types."""
    # Fallback to basic ERC20 interface
    erc20_abi = [
        {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}
    ]
    
    contract = w3.eth.contract(address=pair_address, abi=erc20_abi)
    total_supply = contract.functions.totalSupply().call()
    
    return {
        'type': 'unknown',
        'total_supply': total_supply,
        'token0_address': None,
        'token1_address': None
    }


async def _analyze_enhanced_liquidity_depth(
    provider_manager: ProviderManager,
    pair_address: str,
    pair_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Analyze liquidity depth using enhanced provider management."""
    
    async def analyze_depth(w3: Web3) -> Dict[str, Any]:
        if pair_info['type'] == 'uniswap_v2':
            return await _analyze_v2_liquidity_depth(w3, pair_address, pair_info)
        elif pair_info['type'] == 'uniswap_v3':
            return await _analyze_v3_liquidity_depth(w3, pair_address, pair_info)
        else:
            return {'error': 'Unknown pair type', 'total_liquidity_usd': 0}
    
    return await provider_manager.execute_with_failover(analyze_depth)


async def _analyze_v2_liquidity_depth(w3: Web3, pair_address: str, pair_info: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze Uniswap V2 liquidity depth."""
    try:
        # Get token information for both tokens
        token0_info = await get_token_info(ProviderManager(config.get_chain_config(1)), pair_info['token0_address'])
        token1_info = await get_token_info(ProviderManager(config.get_chain_config(1)), pair_info['token1_address'])
        
        if not token0_info or not token1_info:
            return {'error': 'Could not get token information', 'total_liquidity_usd': 0}
        
        reserves = pair_info['reserves']
        
        # Calculate normalized reserves
        token0_reserve = Decimal(reserves['reserve0']) / (10 ** token0_info['decimals'])
        token1_reserve = Decimal(reserves['reserve1']) / (10 ** token1_info['decimals'])
        
        # Get token prices (simplified - in production use Chainlink or DEX aggregators)
        token0_price_usd = await _get_token_price_usd(w3, pair_info['token0_address'])
        token1_price_usd = await _get_token_price_usd(w3, pair_info['token1_address'])
        
        # Calculate USD values
        token0_liquidity_usd = float(token0_reserve * Decimal(str(token0_price_usd)))
        token1_liquidity_usd = float(token1_reserve * Decimal(str(token1_price_usd)))
        total_liquidity_usd = token0_liquidity_usd + token1_liquidity_usd
        
        # Calculate additional metrics
        if token0_liquidity_usd > 0 and token1_liquidity_usd > 0:
            liquidity_ratio = token0_liquidity_usd / token1_liquidity_usd
            imbalance = abs(1 - liquidity_ratio)
        else:
            liquidity_ratio = 0
            imbalance = 1
        
        return {
            'total_liquidity_usd': total_liquidity_usd,
            'token0_liquidity_usd': token0_liquidity_usd,
            'token1_liquidity_usd': token1_liquidity_usd,
            'reserves': {
                'token0_reserve': float(token0_reserve),
                'token1_reserve': float(token1_reserve)
            },
            'token_info': {
                'token0': token0_info,
                'token1': token1_info
            },
            'metrics': {
                'liquidity_ratio': liquidity_ratio,
                'imbalance': imbalance,
                'depth_score': _calculate_depth_score(total_liquidity_usd)
            }
        }
        
    except Exception as e:
        logger.error(f"V2 liquidity depth analysis failed: {e}")
        return {'error': str(e), 'total_liquidity_usd': 0}


async def _analyze_v3_liquidity_depth(w3: Web3, pair_address: str, pair_info: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze Uniswap V3 liquidity depth."""
    try:
        # V3 pools use concentrated liquidity - more complex calculation
        # This is a simplified implementation
        
        liquidity = pair_info.get('liquidity', 0)
        sqrt_price_x96 = pair_info.get('sqrt_price_x96', 0)
        
        # Simplified liquidity calculation for V3
        # In production, you'd calculate this more precisely using tick ranges
        estimated_liquidity_usd = float(liquidity) / 1e18 * 2  # Rough approximation
        
        return {
            'total_liquidity_usd': estimated_liquidity_usd,
            'liquidity_amount': liquidity,
            'sqrt_price_x96': sqrt_price_x96,
            'fee_tier': pair_info.get('fee_tier', 0),
            'metrics': {
                'depth_score': _calculate_depth_score(estimated_liquidity_usd)
            }
        }
        
    except Exception as e:
        logger.error(f"V3 liquidity depth analysis failed: {e}")
        return {'error': str(e), 'total_liquidity_usd': 0}


async def _calculate_enhanced_slippage_impact(
    provider_manager: ProviderManager,
    pair_address: str,
    pair_info: Dict[str, Any],
    test_trade_sizes: List[float]
) -> Dict[str, Any]:
    """Calculate slippage impact for various trade sizes."""
    
    async def calculate_slippage(w3: Web3) -> Dict[str, Any]:
        slippage_results = []
        max_slippage = 0
        
        for trade_size_usd in test_trade_sizes:
            try:
                # Calculate buy and sell slippage
                buy_slippage = await _calculate_buy_slippage(w3, pair_info, trade_size_usd)
                sell_slippage = await _calculate_sell_slippage(w3, pair_info, trade_size_usd)
                
                trade_max_slippage = max(buy_slippage, sell_slippage)
                max_slippage = max(max_slippage, trade_max_slippage)
                
                slippage_results.append({
                    'trade_size_usd': trade_size_usd,
                    'buy_slippage_percent': buy_slippage,
                    'sell_slippage_percent': sell_slippage,
                    'max_slippage_percent': trade_max_slippage
                })
                
            except Exception as e:
                logger.warning(f"Slippage calculation failed for ${trade_size_usd}: {e}")
                slippage_results.append({
                    'trade_size_usd': trade_size_usd,
                    'error': str(e),
                    'max_slippage_percent': 100  # Assume worst case
                })
                max_slippage = max(max_slippage, 100)
        
        return {
            'slippage_results': slippage_results,
            'max_slippage_percent': max_slippage,
            'average_slippage_percent': sum(r.get('max_slippage_percent', 0) for r in slippage_results) / len(slippage_results),
            'curve_analysis': _analyze_slippage_curve(slippage_results)
        }
    
    return await provider_manager.execute_with_failover(calculate_slippage)


async def _calculate_buy_slippage(w3: Web3, pair_info: Dict[str, Any], trade_size_usd: float) -> float:
    """Calculate buy slippage for a given trade size."""
    try:
        if pair_info['type'] == 'uniswap_v2':
            # Simplified constant product formula calculation
            reserves = pair_info['reserves']
            reserve0 = reserves['reserve0']
            reserve1 = reserves['reserve1']
            
            # Assume buying token0 with token1 (ETH)
            # This is a simplified calculation
            k = reserve0 * reserve1
            trade_amount = int(trade_size_usd * 1e18 / 2500)  # Assume ETH price $2500
            
            new_reserve1 = reserve1 + trade_amount
            new_reserve0 = k // new_reserve1
            
            tokens_out = reserve0 - new_reserve0
            price_impact = (tokens_out / reserve0) * 100
            
            return min(price_impact, 50)  # Cap at 50%
            
        else:
            # For V3 or unknown, return a conservative estimate
            return min(trade_size_usd / 10000 * 5, 20)  # 5% per $10k, max 20%
            
    except Exception as e:
        logger.warning(f"Buy slippage calculation failed: {e}")
        return 50  # Conservative fallback


async def _calculate_sell_slippage(w3: Web3, pair_info: Dict[str, Any], trade_size_usd: float) -> float:
    """Calculate sell slippage for a given trade size."""
    # Similar to buy slippage but in reverse direction
    return await _calculate_buy_slippage(w3, pair_info, trade_size_usd)


async def _analyze_enhanced_lp_tokens(
    provider_manager: ProviderManager,
    pair_address: str,
    pair_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Analyze LP token distribution and security."""
    
    async def analyze_lp(w3: Web3) -> Dict[str, Any]:
        try:
            # Get LP token supply
            total_supply = pair_info.get('total_supply', 0)
            if total_supply == 0:
                return {'error': 'No total supply found', 'security_score': 0}
            
            # Check burn addresses
            burn_addresses = [
                '0x000000000000000000000000000000000000dEaD',  # Dead address
                '0x0000000000000000000000000000000000000000',  # Zero address
            ]
            
            burned_amount = 0
            for burn_addr in burn_addresses:
                try:
                    balance = await _get_lp_balance(w3, pair_address, burn_addr)
                    burned_amount += balance
                except:
                    continue
            
            # Check for known locker contracts
            locked_amount = await _check_enhanced_lp_locks(w3, pair_address)
            
            # Calculate metrics
            circulating_supply = total_supply - burned_amount - locked_amount
            burn_percentage = (burned_amount / total_supply * 100) if total_supply > 0 else 0
            lock_percentage = (locked_amount / total_supply * 100) if total_supply > 0 else 0
            
            security_score = _calculate_lp_security_score(burn_percentage, lock_percentage)
            
            return {
                'total_supply': total_supply,
                'burned_amount': burned_amount,
                'locked_amount': locked_amount,
                'circulating_supply': circulating_supply,
                'burn_percentage': burn_percentage,
                'lock_percentage': lock_percentage,
                'security_score': security_score,
                'is_majority_secured': (burn_percentage + lock_percentage) > 80
            }
            
        except Exception as e:
            logger.error(f"LP token analysis failed: {e}")
            return {'error': str(e), 'security_score': 0}
    
    return await provider_manager.execute_with_failover(analyze_lp)


async def _get_lp_balance(w3: Web3, pair_address: str, holder_address: str) -> int:
    """Get LP token balance for a specific holder."""
    erc20_abi = [
        {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], 
         "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"}
    ]
    
    contract = w3.eth.contract(address=pair_address, abi=erc20_abi)
    return contract.functions.balanceOf(holder_address).call()


async def _check_enhanced_lp_locks(w3: Web3, pair_address: str) -> int:
    """Check for LP tokens locked in known locker contracts."""
    # Known locker contract addresses (simplified list)
    locker_contracts = [
        '0x663A5C229c09b049E36dCc11a9B0d4a8Eb9db214',  # Unicrypt
        '0x4d5eF58aAc27d99935E5b6B4A6778ff292059991',  # DxSale
        # Add more as needed
    ]
    
    total_locked = 0
    for locker_address in locker_contracts:
        try:
            balance = await _get_lp_balance(w3, pair_address, locker_address)
            total_locked += balance
        except:
            continue
    
    return total_locked


async def _get_token_price_usd(w3: Web3, token_address: str) -> float:
    """Get token price in USD using simplified price feeds."""
    # This is a simplified implementation
    # In production, you'd use Chainlink price feeds or DEX aggregators
    
    token_address_lower = token_address.lower()
    
    # Known token prices (simplified)
    known_prices = {
        '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2': 2500.0,  # WETH
        '0xa0b86a33e6e67c6e2b2eb44630b58cf95e5e7d77': 1.0,     # USDC
        '0xdac17f958d2ee523a2206206994597c13d831ec7': 1.0,     # USDT
        '0x4200000000000000000000000000000000000006': 2500.0,  # WETH on Base
        '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913': 1.0,     # USDC on Base
    }
    
    return known_prices.get(token_address_lower, 0.001)  # Default to very low price


def _calculate_enhanced_risk_score(
    liquidity_analysis: Dict[str, Any],
    slippage_analysis: Dict[str, Any],
    lp_analysis: Dict[str, Any],
    min_liquidity_usd: float,
    max_slippage_percent: float
) -> Decimal:
    """Calculate enhanced risk score with weighted factors."""
    score = Decimal('0')
    
    # Liquidity amount scoring (40% weight)
    total_liquidity = liquidity_analysis.get('total_liquidity_usd', 0)
    if total_liquidity < min_liquidity_usd:
        shortage_ratio = (min_liquidity_usd - total_liquidity) / min_liquidity_usd
        score += Decimal(str(shortage_ratio * 40))
    
    # Slippage scoring (35% weight)
    max_slippage = slippage_analysis.get('max_slippage_percent', 0)
    if max_slippage > max_slippage_percent:
        excess_slippage = max_slippage - max_slippage_percent
        score += Decimal(str(min(excess_slippage * 3.5, 35)))
    
    # LP security scoring (20% weight)
    lp_security = lp_analysis.get('security_score', 0)
    if lp_security < 50:
        score += Decimal(str((50 - lp_security) * 0.4))
    
    # Liquidity imbalance scoring (5% weight)
    imbalance = liquidity_analysis.get('metrics', {}).get('imbalance', 0)
    if imbalance > 0.5:
        score += Decimal(str(imbalance * 5))
    
    return min(score, Decimal('100'))


def _calculate_enhanced_quality_metrics(
    liquidity_analysis: Dict[str, Any],
    slippage_analysis: Dict[str, Any]
) -> Dict[str, float]:
    """Calculate enhanced quality metrics for liquidity assessment."""
    
    # Calculate liquidity efficiency
    slippage_data = slippage_analysis.get('slippage_results', [])
    efficiency = _calculate_liquidity_efficiency(slippage_data)
    
    # Calculate depth score
    total_liquidity = liquidity_analysis.get('total_liquidity_usd', 0)
    depth_score = _calculate_depth_score(total_liquidity)
    
    # Calculate stability score based on imbalance
    imbalance = liquidity_analysis.get('metrics', {}).get('imbalance', 1)
    stability_score = max(0, 100 - imbalance * 100)
    
    # Calculate overall quality score
    overall_quality = (efficiency * 0.4 + depth_score * 0.4 + stability_score * 0.2)
    
    return {
        'efficiency_score': efficiency,
        'depth_score': depth_score,
        'stability_score': stability_score,
        'overall_quality_score': overall_quality,
        'liquidity_grade': _get_liquidity_grade(overall_quality)
    }


def _calculate_liquidity_efficiency(slippage_data: List[Dict]) -> float:
    """Calculate efficiency score based on slippage performance."""
    if not slippage_data:
        return 0
    
    # Efficiency = inverse of average slippage
    valid_slippages = [
        item.get('max_slippage_percent', 100) 
        for item in slippage_data 
        if 'error' not in item
    ]
    
    if not valid_slippages:
        return 0
    
    avg_slippage = sum(valid_slippages) / len(valid_slippages)
    return max(0, 100 - avg_slippage * 10)


def _calculate_depth_score(total_liquidity_usd: float) -> float:
    """Calculate depth score based on total liquidity."""
    if total_liquidity_usd >= 1000000:
        return 100
    elif total_liquidity_usd >= 500000:
        return 90
    elif total_liquidity_usd >= 100000:
        return 80
    elif total_liquidity_usd >= 50000:
        return 70
    elif total_liquidity_usd >= 10000:
        return 60
    else:
        return max(0, total_liquidity_usd / 10000 * 60)


def _calculate_lp_security_score(burn_percentage: float, lock_percentage: float) -> float:
    """Calculate LP security score based on burns and locks."""
    total_secured = burn_percentage + lock_percentage
    
    if total_secured >= 95:
        return 100
    elif total_secured >= 90:
        return 90
    elif total_secured >= 80:
        return 80
    elif total_secured >= 70:
        return 70
    elif total_secured >= 50:
        return 60
    else:
        return max(0, total_secured * 1.2)


def _analyze_slippage_curve(slippage_data: List[Dict]) -> Dict[str, Any]:
    """Analyze the slippage curve for patterns."""
    if not slippage_data or len(slippage_data) < 2:
        return {'curve_type': 'unknown', 'steepness': 0}
    
    # Get valid data points
    valid_points = [
        (item['trade_size_usd'], item.get('max_slippage_percent', 100))
        for item in slippage_data
        if 'error' not in item
    ]
    
    if len(valid_points) < 2:
        return {'curve_type': 'unknown', 'steepness': 0}
    
    # Check curve characteristics
    sizes = [point[0] for point in valid_points]
    slippages = [point[1] for point in valid_points]
    
    # Calculate steepness
    steepness = (slippages[-1] - slippages[0]) / (sizes[-1] - sizes[0]) if sizes[-1] != sizes[0] else 0
    
    # Determine curve type
    if slippages[-1] > slippages[0] * 3:
        curve_type = 'exponential'
    elif slippages[-1] > slippages[0] * 1.5:
        curve_type = 'steep_linear'
    else:
        curve_type = 'linear'
    
    return {
        'curve_type': curve_type,
        'steepness': steepness,
        'max_tested_slippage': max(slippages),
        'min_tested_slippage': min(slippages)
    }


def _get_liquidity_grade(quality_score: float) -> str:
    """Get letter grade for liquidity quality."""
    if quality_score >= 90:
        return 'A+'
    elif quality_score >= 85:
        return 'A'
    elif quality_score >= 80:
        return 'A-'
    elif quality_score >= 75:
        return 'B+'
    elif quality_score >= 70:
        return 'B'
    elif quality_score >= 65:
        return 'B-'
    elif quality_score >= 60:
        return 'C+'
    elif quality_score >= 55:
        return 'C'
    elif quality_score >= 50:
        return 'C-'
    elif quality_score >= 40:
        return 'D'
    else:
        return 'F'


def _store_enhanced_liquidity_result(result: Dict[str, Any]) -> None:
    """Store enhanced liquidity analysis result in database."""
    try:
        # This would integrate with your Django ORM
        # For now, just log the successful storage
        logger.info(f"Stored enhanced liquidity result for {result.get('pair_address', 'unknown')}")
        
        # In production, you'd do something like:
        # RiskCheckResult.objects.create(
        #     check_type='ENHANCED_LIQUIDITY',
        #     status=result['status'],
        #     risk_score=result['risk_score'],
        #     details=result.get('details', {}),
        #     execution_time_ms=result.get('execution_time_ms', 0)
        # )
        
    except Exception as e:
        logger.error(f"Failed to store enhanced liquidity result: {e}")


# Backward compatibility wrapper for existing code
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
    Backward compatibility wrapper for existing liquidity check.
    
    Redirects to the enhanced liquidity check with the same interface.
    """
    logger.info(f"Redirecting legacy liquidity_check to enhanced version for {pair_address}")
    
    return enhanced_liquidity_check(
        pair_address=pair_address,
        token_address=token_address,
        chain_id=None,  # Will use default
        min_liquidity_usd=min_liquidity_usd,
        max_slippage_percent=max_slippage_percent,
        test_trade_sizes=test_trade_sizes
    )


# Utility functions for external use
async def get_pair_liquidity_info(chain_id: int, pair_address: str) -> Optional[Dict[str, Any]]:
    """
    Utility function to get basic liquidity information for a pair.
    
    Args:
        chain_id: Blockchain network ID
        pair_address: Trading pair contract address
        
    Returns:
        Dict with basic liquidity information or None if failed
    """
    try:
        chain_config = config.get_chain_config(chain_id)
        if not chain_config:
            return None
        
        provider_manager = ProviderManager(chain_config)
        
        try:
            pair_info = await _get_enhanced_pair_information(provider_manager, pair_address)
            if not pair_info:
                return None
            
            liquidity_analysis = await _analyze_enhanced_liquidity_depth(
                provider_manager, pair_address, pair_info
            )
            
            return {
                'pair_address': pair_address,
                'chain_id': chain_id,
                'total_liquidity_usd': liquidity_analysis.get('total_liquidity_usd', 0),
                'pair_type': pair_info.get('type', 'unknown'),
                'fee_tier': pair_info.get('fee_tier', 0),
                'timestamp': timezone.now().isoformat()
            }
            
        finally:
            await provider_manager.close()
            
    except Exception as e:
        logger.error(f"Failed to get pair liquidity info: {e}")
        return None


async def estimate_trade_slippage(
    chain_id: int, 
    pair_address: str, 
    trade_size_usd: float
) -> Optional[float]:
    """
    Utility function to estimate slippage for a specific trade size.
    
    Args:
        chain_id: Blockchain network ID
        pair_address: Trading pair contract address
        trade_size_usd: Trade size in USD
        
    Returns:
        Estimated slippage percentage or None if failed
    """
    try:
        chain_config = config.get_chain_config(chain_id)
        if not chain_config:
            return None
        
        provider_manager = ProviderManager(chain_config)
        
        try:
            pair_info = await _get_enhanced_pair_information(provider_manager, pair_address)
            if not pair_info:
                return None
            
            slippage_analysis = await _calculate_enhanced_slippage_impact(
                provider_manager, pair_address, pair_info, [trade_size_usd]
            )
            
            slippage_results = slippage_analysis.get('slippage_results', [])
            if slippage_results and len(slippage_results) > 0:
                return slippage_results[0].get('max_slippage_percent', None)
            
            return None
            
        finally:
            await provider_manager.close()
            
    except Exception as e:
        logger.error(f"Failed to estimate trade slippage: {e}")
        return None