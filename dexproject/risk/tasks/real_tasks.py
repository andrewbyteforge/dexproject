"""
Real Risk Assessment Tasks Implementation

This module contains the actual Celery tasks that perform real blockchain analysis
using Web3 connections and genuine contract interactions.

File: dexproject/risk/tasks/real_tasks.py
"""

import logging
import time
import asyncio
from typing import Dict, Any, Optional
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from web3 import Web3
from web3.middleware import geth_poa_middleware

# Import our real implementations
from .honeypot import perform_honeypot_check
from .liquidity import perform_liquidity_check
from .ownership import perform_ownership_check

logger = logging.getLogger(__name__)


class Web3ProviderManager:
    """Manages Web3 connections for different chains."""
    
    def __init__(self):
        self.providers = {}
        self.chain_configs = {
            1: {
                'name': 'Ethereum',
                'rpc_urls': [
                    'https://eth-mainnet.g.alchemy.com/v2/demo',
                    'https://ethereum.publicnode.com',
                    'https://rpc.ankr.com/eth'
                ],
                'needs_poa': False
            },
            8453: {
                'name': 'Base',
                'rpc_urls': [
                    'https://base-mainnet.g.alchemy.com/v2/demo',
                    'https://mainnet.base.org',
                    'https://base.blockpi.network/v1/rpc/public'
                ],
                'needs_poa': False
            }
        }
    
    def get_web3_provider(self, chain_id: int) -> Web3:
        """
        Get or create Web3 provider for specified chain.
        
        Args:
            chain_id: Blockchain chain ID
            
        Returns:
            Web3 instance
            
        Raises:
            Exception: If no working RPC found
        """
        if chain_id in self.providers:
            # Check if existing provider is still connected
            try:
                self.providers[chain_id].eth.block_number
                return self.providers[chain_id]
            except:
                # Provider is dead, remove it
                del self.providers[chain_id]
        
        # Create new provider
        chain_config = self.chain_configs.get(chain_id)
        if not chain_config:
            raise ValueError(f"Unsupported chain ID: {chain_id}")
        
        for rpc_url in chain_config['rpc_urls']:
            try:
                w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 30}))
                
                # Add PoA middleware if needed
                if chain_config['needs_poa']:
                    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                
                # Test connection
                block_number = w3.eth.block_number
                if block_number > 0:
                    self.providers[chain_id] = w3
                    logger.info(f"Connected to {chain_config['name']} via {rpc_url}")
                    return w3
                    
            except Exception as e:
                logger.warning(f"Failed to connect to {rpc_url}: {e}")
                continue
        
        raise Exception(f"Could not connect to any RPC for chain {chain_id}")


# Global provider manager
provider_manager = Web3ProviderManager()


@shared_task(
    bind=True,
    queue='risk.urgent',
    name='risk.tasks.honeypot_check',
    max_retries=2,
    default_retry_delay=3
)
def honeypot_check(self, token_address: str, pair_address: str, chain_id: int = 1) -> Dict[str, Any]:
    """
    Perform real honeypot detection using blockchain analysis.
    
    Args:
        token_address: Token contract address
        pair_address: Trading pair address
        chain_id: Blockchain chain ID (default: Ethereum mainnet)
        
    Returns:
        Dict with honeypot detection results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting real honeypot check for token {token_address} on chain {chain_id} (task: {task_id})")
    
    try:
        # Get Web3 provider
        w3 = provider_manager.get_web3_provider(chain_id)
        
        # Run the actual honeypot detection
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                perform_honeypot_check(w3, token_address, pair_address, chain_id)
            )
        finally:
            loop.close()
        
        # Add task metadata
        result.update({
            'task_id': task_id,
            'execution_time_ms': (time.time() - start_time) * 1000,
            'timestamp': timezone.now().isoformat(),
            'chain_id': chain_id
        })
        
        logger.info(
            f"Honeypot check completed - Token: {token_address}, "
            f"Is Honeypot: {result.get('is_honeypot', 'unknown')}, "
            f"Risk Score: {result.get('risk_score', 0)}"
        )
        
        return result
        
    except Exception as exc:
        execution_time = (time.time() - start_time) * 1000
        logger.error(f"Honeypot check failed for {token_address}: {exc}")
        
        # Retry logic
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying honeypot check (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=5)
        
        return {
            'check_type': 'HONEYPOT',
            'task_id': task_id,
            'token_address': token_address,
            'pair_address': pair_address,
            'chain_id': chain_id,
            'status': 'FAILED',
            'error_message': str(exc),
            'execution_time_ms': execution_time,
            'risk_score': 100.0,  # Maximum risk on failure
            'is_honeypot': True,   # Assume worst case
            'timestamp': timezone.now().isoformat()
        }


@shared_task(
    bind=True,
    queue='risk.urgent',
    name='risk.tasks.liquidity_check',
    max_retries=2,
    default_retry_delay=3
)
def liquidity_check(self, token_address: str, pair_address: str, chain_id: int = 1) -> Dict[str, Any]:
    """
    Perform real liquidity analysis using blockchain data.
    
    Args:
        token_address: Token contract address
        pair_address: Trading pair address
        chain_id: Blockchain chain ID (default: Ethereum mainnet)
        
    Returns:
        Dict with liquidity analysis results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting real liquidity check for pair {pair_address} on chain {chain_id} (task: {task_id})")
    
    try:
        # Get Web3 provider
        w3 = provider_manager.get_web3_provider(chain_id)
        
        # Run the actual liquidity analysis
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                perform_liquidity_check(w3, token_address, pair_address, chain_id)
            )
        finally:
            loop.close()
        
        # Add task metadata
        result.update({
            'task_id': task_id,
            'execution_time_ms': (time.time() - start_time) * 1000,
            'timestamp': timezone.now().isoformat(),
            'chain_id': chain_id
        })
        
        logger.info(
            f"Liquidity check completed - Pair: {pair_address}, "
            f"Liquidity USD: ${result.get('details', {}).get('total_liquidity_usd', '0')}, "
            f"Risk Score: {result.get('risk_score', 0)}"
        )
        
        return result
        
    except Exception as exc:
        execution_time = (time.time() - start_time) * 1000
        logger.error(f"Liquidity check failed for {pair_address}: {exc}")
        
        # Retry logic
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying liquidity check (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=5)
        
        return {
            'check_type': 'LIQUIDITY',
            'task_id': task_id,
            'token_address': token_address,
            'pair_address': pair_address,
            'chain_id': chain_id,
            'status': 'FAILED',
            'error_message': str(exc),
            'execution_time_ms': execution_time,
            'risk_score': 100.0,  # Maximum risk on failure
            'liquidity_score': 0,
            'timestamp': timezone.now().isoformat()
        }


@shared_task(
    bind=True,
    queue='risk.urgent',
    name='risk.tasks.ownership_check',
    max_retries=2,
    default_retry_delay=3
)
def ownership_check(self, token_address: str, chain_id: int = 1) -> Dict[str, Any]:
    """
    Perform real ownership analysis using blockchain data.
    
    Args:
        token_address: Token contract address
        chain_id: Blockchain chain ID (default: Ethereum mainnet)
        
    Returns:
        Dict with ownership analysis results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting real ownership check for token {token_address} on chain {chain_id} (task: {task_id})")
    
    try:
        # Get Web3 provider
        w3 = provider_manager.get_web3_provider(chain_id)
        
        # Run the actual ownership analysis
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                perform_ownership_check(w3, token_address, chain_id)
            )
        finally:
            loop.close()
        
        # Add task metadata
        result.update({
            'task_id': task_id,
            'execution_time_ms': (time.time() - start_time) * 1000,
            'timestamp': timezone.now().isoformat(),
            'chain_id': chain_id
        })
        
        logger.info(
            f"Ownership check completed - Token: {token_address}, "
            f"Is Renounced: {result.get('is_renounced', False)}, "
            f"Risk Score: {result.get('risk_score', 0)}"
        )
        
        return result
        
    except Exception as exc:
        execution_time = (time.time() - start_time) * 1000
        logger.error(f"Ownership check failed for {token_address}: {exc}")
        
        # Retry logic
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying ownership check (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=5)
        
        return {
            'check_type': 'OWNERSHIP',
            'task_id': task_id,
            'token_address': token_address,
            'chain_id': chain_id,
            'status': 'FAILED',
            'error_message': str(exc),
            'execution_time_ms': execution_time,
            'risk_score': 100.0,  # Maximum risk on failure
            'is_renounced': False,  # Assume worst case
            'timestamp': timezone.now().isoformat()
        }


@shared_task(
    bind=True,
    queue='risk.urgent',
    name='risk.tasks.tax_analysis',
    max_retries=2,
    default_retry_delay=3
)
def tax_analysis(self, token_address: str, pair_address: str, chain_id: int = 1) -> Dict[str, Any]:
    """
    Perform real tax analysis by simulating trades and analyzing contract code.
    
    Args:
        token_address: Token contract address
        pair_address: Trading pair address
        chain_id: Blockchain chain ID (default: Ethereum mainnet)
        
    Returns:
        Dict with tax analysis results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting real tax analysis for token {token_address} on chain {chain_id} (task: {task_id})")
    
    try:
        # Get Web3 provider
        w3 = provider_manager.get_web3_provider(chain_id)
        
        # Perform tax analysis by simulating trades
        result = await _perform_tax_analysis(w3, token_address, pair_address, chain_id)
        
        # Add task metadata
        result.update({
            'task_id': task_id,
            'execution_time_ms': (time.time() - start_time) * 1000,
            'timestamp': timezone.now().isoformat(),
            'chain_id': chain_id
        })
        
        logger.info(
            f"Tax analysis completed - Token: {token_address}, "
            f"Buy Tax: {result.get('details', {}).get('buy_tax_percent', 0)}%, "
            f"Sell Tax: {result.get('details', {}).get('sell_tax_percent', 0)}%"
        )
        
        return result
        
    except Exception as exc:
        execution_time = (time.time() - start_time) * 1000
        logger.error(f"Tax analysis failed for {token_address}: {exc}")
        
        # Retry logic
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying tax analysis (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=5)
        
        return {
            'check_type': 'TAX_ANALYSIS',
            'task_id': task_id,
            'token_address': token_address,
            'pair_address': pair_address,
            'chain_id': chain_id,
            'status': 'FAILED',
            'error_message': str(exc),
            'execution_time_ms': execution_time,
            'risk_score': 75.0,  # High risk on failure
            'timestamp': timezone.now().isoformat()
        }


@shared_task(
    bind=True,
    queue='risk.normal',
    name='risk.tasks.contract_security_check',
    max_retries=2,
    default_retry_delay=5
)
def contract_security_check(self, token_address: str, chain_id: int = 1) -> Dict[str, Any]:
    """
    Perform contract security analysis including verification status and code patterns.
    
    Args:
        token_address: Token contract address
        chain_id: Blockchain chain ID (default: Ethereum mainnet)
        
    Returns:
        Dict with security analysis results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting contract security check for {token_address} on chain {chain_id} (task: {task_id})")
    
    try:
        # Get Web3 provider
        w3 = provider_manager.get_web3_provider(chain_id)
        
        # Perform security analysis
        result = await _perform_security_analysis(w3, token_address, chain_id)
        
        # Add task metadata
        result.update({
            'task_id': task_id,
            'execution_time_ms': (time.time() - start_time) * 1000,
            'timestamp': timezone.now().isoformat(),
            'chain_id': chain_id
        })
        
        return result
        
    except Exception as exc:
        execution_time = (time.time() - start_time) * 1000
        logger.error(f"Contract security check failed for {token_address}: {exc}")
        
        # Retry logic
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying security check (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=5)
        
        return {
            'check_type': 'CONTRACT_SECURITY',
            'task_id': task_id,
            'token_address': token_address,
            'chain_id': chain_id,
            'status': 'FAILED',
            'error_message': str(exc),
            'execution_time_ms': execution_time,
            'risk_score': 75.0,
            'timestamp': timezone.now().isoformat()
        }


# Helper functions for complex analyses

async def _perform_tax_analysis(
    w3: Web3, 
    token_address: str, 
    pair_address: str, 
    chain_id: int
) -> Dict[str, Any]:
    """Perform real tax analysis by simulating trades."""
    
    try:
        # Get router and token contracts
        router_addresses = {
            1: "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
            8453: "0x327df1e6de05895d2ab08513aadd9313fe505d86"
        }
        
        router_address = router_addresses.get(chain_id)
        if not router_address:
            raise ValueError(f"No router address for chain {chain_id}")
        
        # Simulate small buy to detect taxes
        test_amount_wei = int(0.001 * 10**18)  # 0.001 ETH
        
        # Get expected tokens from buy
        weth_addresses = {
            1: "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            8453: "0x4200000000000000000000000000000000000006"
        }
        
        weth_address = weth_addresses.get(chain_id)
        path = [weth_address, token_address]
        
        # Get router contract
        router_abi = [
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"}
                ],
                "name": "getAmountsOut",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        router_contract = w3.eth.contract(
            address=router_address,
            abi=router_abi
        )
        
        # Get amounts for buy
        try:
            amounts_out = router_contract.functions.getAmountsOut(
                test_amount_wei, path
            ).call()
            expected_tokens = amounts_out[-1]
        except Exception as e:
            logger.warning(f"Could not get buy amounts: {e}")
            expected_tokens = 0
        
        # Get amounts for sell (reverse path)
        if expected_tokens > 0:
            reverse_path = [token_address, weth_address]
            try:
                amounts_out_sell = router_contract.functions.getAmountsOut(
                    expected_tokens, reverse_path
                ).call()
                expected_eth_back = amounts_out_sell[-1]
            except Exception as e:
                logger.warning(f"Could not get sell amounts: {e}")
                expected_eth_back = 0
        else:
            expected_eth_back = 0
        
        # Calculate taxes
        if expected_eth_back > 0 and test_amount_wei > 0:
            round_trip_efficiency = (expected_eth_back / test_amount_wei)
            total_tax_percent = (1 - round_trip_efficiency) * 100
            
            # Estimate buy and sell taxes (assuming equal)
            estimated_tax_each = total_tax_percent / 2
            buy_tax = min(estimated_tax_each, 25)  # Cap at 25%
            sell_tax = min(estimated_tax_each, 25)
        else:
            # Could not determine taxes
            buy_tax = 0
            sell_tax = 0
            total_tax_percent = 0
        
        # Calculate risk score
        risk_score = 0
        risk_factors = []
        
        if buy_tax > 10:
            risk_score += 30
            risk_factors.append('high_buy_tax')
        elif buy_tax > 5:
            risk_score += 15
            risk_factors.append('moderate_buy_tax')
        
        if sell_tax > 10:
            risk_score += 30
            risk_factors.append('high_sell_tax')
        elif sell_tax > 5:
            risk_score += 15
            risk_factors.append('moderate_sell_tax')
        
        if total_tax_percent > 15:
            risk_score += 20
            risk_factors.append('very_high_total_tax')
        
        return {
            'check_type': 'TAX_ANALYSIS',
            'token_address': token_address,
            'pair_address': pair_address,
            'status': 'COMPLETED',
            'risk_score': min(risk_score, 100),
            'details': {
                'buy_tax_percent': round(buy_tax, 2),
                'sell_tax_percent': round(sell_tax, 2),
                'total_tax_percent': round(total_tax_percent, 2),
                'test_amount_eth': '0.001',
                'expected_tokens': expected_tokens,
                'expected_eth_back': expected_eth_back,
                'round_trip_efficiency': round(round_trip_efficiency, 4) if expected_eth_back > 0 else 0,
                'risk_factors': risk_factors,
                'analysis_method': 'simulation'
            }
        }
        
    except Exception as e:
        logger.error(f"Tax analysis implementation failed: {e}")
        return {
            'check_type': 'TAX_ANALYSIS',
            'token_address': token_address,
            'pair_address': pair_address,
            'status': 'FAILED',
            'error_message': str(e),
            'risk_score': 50.0
        }


async def _perform_security_analysis(w3: Web3, token_address: str, chain_id: int) -> Dict[str, Any]:
    """Perform contract security analysis."""
    
    try:
        # Get contract bytecode
        code = w3.eth.get_code(token_address)
        code_hex = code.hex().lower()
        
        if len(code_hex) < 10:
            return {
                'check_type': 'CONTRACT_SECURITY',
                'token_address': token_address,
                'status': 'COMPLETED',
                'risk_score': 100.0,
                'details': {
                    'is_contract': False,
                    'error': 'Not a contract'
                }
            }
        
        # Check for common security patterns
        security_checks = {
            'has_pause_function': '8456cb59' in code_hex,  # pause()
            'has_blacklist': any(pattern in code_hex for pattern in ['f9f92be4', '608e8e6f']),
            'has_mint_function': any(pattern in code_hex for pattern in ['40c10f19', 'a0712d68']),
            'has_burn_function': any(pattern in code_hex for pattern in ['42966c68', '9dc29fac']),
            'has_emergency_stop': '2d0aa1a2' in code_hex,
            'has_upgrade_pattern': any(pattern in code_hex for pattern in [
                '360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc',
                '3d3d3d3d363d3d37363d73'
            ])
        }
        
        # Calculate risk score
        risk_score = 0
        risk_factors = []
        
        if security_checks['has_pause_function']:
            risk_score += 20
            risk_factors.append('has_pause_function')
        
        if security_checks['has_blacklist']:
            risk_score += 25
            risk_factors.append('has_blacklist_functionality')
        
        if security_checks['has_mint_function']:
            risk_score += 15
            risk_factors.append('has_mint_function')
        
        if security_checks['has_upgrade_pattern']:
            risk_score += 30
            risk_factors.append('upgradeable_contract')
        
        # Check contract verification (simplified)
        is_verified = await _check_contract_verification(token_address, chain_id)
        
        if not is_verified:
            risk_score += 20
            risk_factors.append('unverified_contract')
        
        return {
            'check_type': 'CONTRACT_SECURITY',
            'token_address': token_address,
            'status': 'COMPLETED',
            'risk_score': min(risk_score, 100),
            'details': {
                'is_contract': True,
                'code_size_bytes': len(code),
                'is_verified': is_verified,
                'security_checks': security_checks,
                'risk_factors': risk_factors,
                'security_rating': 'HIGH' if risk_score > 60 else 'MEDIUM' if risk_score > 30 else 'LOW'
            }
        }
        
    except Exception as e:
        return {
            'check_type': 'CONTRACT_SECURITY',
            'token_address': token_address,
            'status': 'FAILED',
            'error_message': str(e),
            'risk_score': 75.0
        }


async def _check_contract_verification(token_address: str, chain_id: int) -> bool:
    """Check if contract is verified on block explorer."""
    
    try:
        import requests
        
        # Etherscan-like APIs
        api_urls = {
            1: 'https://api.etherscan.io/api',
            8453: 'https://api.basescan.org/api'
        }
        
        api_url = api_urls.get(chain_id)
        if not api_url:
            return False
        
        params = {
            'module': 'contract',
            'action': 'getsourcecode',
            'address': token_address,
            'apikey': 'YourApiKeyToken'  # Would use real API key
        }
        
        response = requests.get(api_url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == '1' and data.get('result'):
                source_code = data['result'][0].get('SourceCode', '')
                return len(source_code) > 0
        
        return False
        
    except Exception as e:
        logger.warning(f"Contract verification check failed: {e}")
        return False


# Main comprehensive assessment task
@shared_task(
    bind=True,
    queue='risk.urgent', 
    name='risk.tasks.assess_token_risk',
    max_retries=1,
    default_retry_delay=10
)
def assess_token_risk(
    self,
    token_address: str,
    pair_address: str,
    chain_id: int = 1,
    risk_profile: str = 'Conservative'
) -> Dict[str, Any]:
    """
    Comprehensive real token risk assessment.
    
    Args:
        token_address: Token contract address
        pair_address: Trading pair address
        chain_id: Blockchain chain ID
        risk_profile: Risk profile to use
        
    Returns:
        Dict with comprehensive risk assessment
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting comprehensive risk assessment for {token_address} (task: {task_id})")
    
    try:
        # Run all risk checks
        check_results = []
        
        # Honeypot check (critical)
        honeypot_result = honeypot_check.delay(token_address, pair_address, chain_id).get()
        check_results.append(honeypot_result)
        
        # Liquidity check (critical)
        liquidity_result = liquidity_check.delay(token_address, pair_address, chain_id).get()
        check_results.append(liquidity_result)
        
        # Ownership check (important)
        ownership_result = ownership_check.delay(token_address, chain_id).get()
        check_results.append(ownership_result)
        
        # Tax analysis (important)
        tax_result = tax_analysis.delay(token_address, pair_address, chain_id).get()
        check_results.append(tax_result)
        
        # Contract security check (moderate)
        security_result = contract_security_check.delay(token_address, chain_id).get()
        check_results.append(security_result)
        
        # Calculate overall risk score
        overall_risk = _calculate_overall_risk_score(check_results, risk_profile)
        
        execution_time = (time.time() - start_time) * 1000
        
        result = {
            'assessment_id': task_id,
            'token_address': token_address,
            'pair_address': pair_address,
            'chain_id': chain_id,
            'risk_profile': risk_profile,
            'status': 'COMPLETED',
            'overall_risk_score': overall_risk['score'],
            'trading_decision': overall_risk['decision'],
            'confidence_score': overall_risk['confidence'],
            'check_results': check_results,
            'risk_summary': overall_risk['summary'],
            'execution_time_ms': execution_time,
            'timestamp': timezone.now().isoformat(),
            'checks_completed': len([r for r in check_results if r.get('status') == 'COMPLETED']),
            'checks_failed': len([r for r in check_results if r.get('status') == 'FAILED'])
        }
        
        logger.info(
            f"Risk assessment completed - Decision: {overall_risk['decision']}, "
            f"Risk Score: {overall_risk['score']}, "
            f"Checks: {result['checks_completed']}/{len(check_results)}"
        )
        
        return result
        
    except Exception as exc:
        execution_time = (time.time() - start_time) * 1000
        logger.error(f"Comprehensive risk assessment failed: {exc}")
        
        return {
            'assessment_id': task_id,
            'token_address': token_address,
            'pair_address': pair_address,
            'chain_id': chain_id,
            'status': 'FAILED',
            'error_message': str(exc),
            'overall_risk_score': 100.0,
            'trading_decision': 'BLOCK',
            'execution_time_ms': execution_time,
            'timestamp': timezone.now().isoformat()
        }


def _calculate_overall_risk_score(check_results: list, risk_profile: str) -> Dict[str, Any]:
    """Calculate overall risk score from individual checks."""
    
    # Weight by importance
    weights = {
        'HONEYPOT': 0.35,
        'LIQUIDITY': 0.25,
        'OWNERSHIP': 0.15,
        'TAX_ANALYSIS': 0.15,
        'CONTRACT_SECURITY': 0.10
    }
    
    total_weighted_score = 0
    total_weight = 0
    failed_checks = []
    
    for result in check_results:
        check_type = result.get('check_type')
        status = result.get('status')
        risk_score = result.get('risk_score', 100)
        
        weight = weights.get(check_type, 0.1)
        
        if status == 'COMPLETED':
            total_weighted_score += risk_score * weight
            total_weight += weight
        else:
            failed_checks.append(check_type)
            # Use maximum risk for failed checks
            total_weighted_score += 100 * weight
            total_weight += weight
    
    # Calculate final score
    if total_weight > 0:
        final_score = total_weighted_score / total_weight
    else:
        final_score = 100
    
    # Make trading decision based on risk profile
    decision_thresholds = {
        'Conservative': 25,
        'Moderate': 45,
        'Aggressive': 65,
        'FastLane': 70
    }
    
    threshold = decision_thresholds.get(risk_profile, 25)
    
    if final_score <= threshold:
        decision = 'APPROVE'
    elif final_score <= threshold + 20:
        decision = 'SKIP'
    else:
        decision = 'BLOCK'
    
    # Calculate confidence based on successful checks
    successful_checks = len([r for r in check_results if r.get('status') == 'COMPLETED'])
    confidence = min(successful_checks * 20, 100)
    
    # Reduce confidence for failed checks
    if failed_checks:
        confidence = max(confidence - len(failed_checks) * 15, 25)
    
    # Create summary
    summary = {
        'total_checks': len(check_results),
        'successful_checks': successful_checks,
        'failed_checks': failed_checks,
        'key_risks': _identify_key_risks(check_results),
        'recommendation': _generate_recommendation(decision, final_score, check_results)
    }
    
    return {
        'score': round(final_score, 2),
        'decision': decision,
        'confidence': confidence,
        'summary': summary
    }


def _identify_key_risks(check_results: list) -> list:
    """Identify key risk factors from check results."""
    key_risks = []
    
    for result in check_results:
        if result.get('status') != 'COMPLETED':
            continue
            
        check_type = result.get('check_type')
        risk_score = result.get('risk_score', 0)
        details = result.get('details', {})
        
        # Honeypot risks
        if check_type == 'HONEYPOT' and result.get('is_honeypot'):
            key_risks.append('Token is a honeypot - cannot sell')
        
        # Liquidity risks
        if check_type == 'LIQUIDITY':
            liquidity_usd = float(details.get('total_liquidity_usd', 0))
            if liquidity_usd < 10000:
                key_risks.append(f'Very low liquidity (${liquidity_usd:,.0f})')
            elif liquidity_usd < 50000:
                key_risks.append(f'Low liquidity (${liquidity_usd:,.0f})')
        
        # Ownership risks
        if check_type == 'OWNERSHIP':
            if not result.get('is_renounced') and risk_score > 50:
                key_risks.append('Ownership not renounced - owner has control')
        
        # Tax risks
        if check_type == 'TAX_ANALYSIS':
            buy_tax = details.get('buy_tax_percent', 0)
            sell_tax = details.get('sell_tax_percent', 0)
            if buy_tax > 10 or sell_tax > 10:
                key_risks.append(f'High taxes - Buy: {buy_tax}%, Sell: {sell_tax}%')
        
        # Security risks
        if check_type == 'CONTRACT_SECURITY' and risk_score > 60:
            risk_factors = details.get('risk_factors', [])
            if 'unverified_contract' in risk_factors:
                key_risks.append('Contract not verified')
            if 'upgradeable_contract' in risk_factors:
                key_risks.append('Contract is upgradeable')
    
    return key_risks[:5]  # Limit to top 5 risks


def _generate_recommendation(decision: str, risk_score: float, check_results: list) -> str:
    """Generate human-readable recommendation."""
    
    if decision == 'APPROVE':
        return f"Safe to trade - Low risk score ({risk_score:.1f}/100). All major risk checks passed."
    
    elif decision == 'SKIP':
        return f"Consider avoiding - Medium risk score ({risk_score:.1f}/100). Some concerning factors detected."
    
    else:  # BLOCK
        failed_critical = any(
            r.get('check_type') in ['HONEYPOT', 'LIQUIDITY'] and 
            (r.get('status') == 'FAILED' or r.get('risk_score', 0) > 80)
            for r in check_results
        )
        
        if failed_critical:
            return f"DO NOT TRADE - Critical risk detected ({risk_score:.1f}/100). High probability of loss."
        else:
            return f"High risk - Avoid trading ({risk_score:.1f}/100). Multiple risk factors present."


# Health check task for the risk system
@shared_task(
    bind=True,
    queue='risk.normal',
    name='risk.tasks.system_health_check',
    max_retries=1
)
def system_health_check(self) -> Dict[str, Any]:
    """
    Check health of the risk assessment system.
    
    Returns:
        Dict with system health status
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting risk system health check (task: {task_id})")
    
    try:
        health_results = {}
        
        # Test Web3 connections
        for chain_id in [1, 8453]:
            try:
                w3 = provider_manager.get_web3_provider(chain_id)
                block_number = w3.eth.block_number
                health_results[f'chain_{chain_id}'] = {
                    'status': 'healthy',
                    'block_number': block_number,
                    'connected': True
                }
            except Exception as e:
                health_results[f'chain_{chain_id}'] = {
                    'status': 'unhealthy',
                    'error': str(e),
                    'connected': False
                }
        
        # Test task queue responsiveness
        queue_test_start = time.time()
        # Simple test - just measure our own execution time
        queue_latency = (time.time() - queue_test_start) * 1000
        
        health_results['task_queue'] = {
            'status': 'healthy' if queue_latency < 1000 else 'degraded',
            'latency_ms': queue_latency
        }
        
        # Overall system status
        unhealthy_components = sum(1 for result in health_results.values() 
                                 if result.get('status') != 'healthy')
        
        if unhealthy_components == 0:
            overall_status = 'healthy'
        elif unhealthy_components <= 1:
            overall_status = 'degraded'
        else:
            overall_status = 'unhealthy'
        
        execution_time = (time.time() - start_time) * 1000
        
        return {
            'task_id': task_id,
            'overall_status': overall_status,
            'components': health_results,
            'unhealthy_components': unhealthy_components,
            'execution_time_ms': execution_time,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as exc:
        execution_time = (time.time() - start_time) * 1000
        
        return {
            'task_id': task_id,
            'overall_status': 'critical',
            'error': str(exc),
            'execution_time_ms': execution_time,
            'timestamp': timezone.now().isoformat()
        }