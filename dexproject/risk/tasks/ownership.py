"""
Ownership check task module.

Implements comprehensive contract ownership analysis including:
- Owner renouncement verification
- Admin function detection and analysis
- Multi-signature wallet detection
- Timelock contract verification
- Dangerous function identification

This module provides critical security assessment by analyzing
contract control structures and identifying potential rug pull vectors.
"""

import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal
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


@shared_task(
    bind=True,
    queue='risk.urgent',
    name='risk.tasks.ownership_check',
    max_retries=3,
    default_retry_delay=1
)
def ownership_check(
    self,
    token_address: str,
    check_admin_functions: bool = True,
    check_timelock: bool = True,
    check_multisig: bool = True
) -> Dict[str, Any]:
    """
    Perform comprehensive ownership and control analysis for a token contract.
    
    Analyzes contract ownership structure, admin functions, and potential
    centralization risks that could lead to rug pulls or malicious changes.
    
    Args:
        token_address: The token contract address to analyze
        check_admin_functions: Whether to analyze admin functions (default True)
        check_timelock: Whether to check for timelock mechanisms (default True)
        check_multisig: Whether to check for multisig wallets (default True)
        
    Returns:
        Dict with comprehensive ownership analysis results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting ownership check for token {token_address} (task: {task_id})")
    
    try:
        # Validate input
        if not is_address(token_address):
            raise ValueError(f"Invalid token address: {token_address}")
        
        token_address = to_checksum_address(token_address)
        
        # Initialize Web3 connection
        w3 = _get_web3_connection()
        if not w3.is_connected():
            raise ConnectionError("Failed to connect to blockchain node")
        
        # Get contract bytecode to verify it exists
        bytecode = w3.eth.get_code(token_address)
        if bytecode == b'':
            raise ValueError(f"No contract found at address {token_address}")
        
        # Analyze ownership structure
        ownership_analysis = _analyze_ownership_structure(w3, token_address)
        
        # Analyze admin functions (if enabled)
        admin_analysis = {}
        if check_admin_functions:
            admin_analysis = _analyze_admin_functions(w3, token_address)
        
        # Check for timelock mechanisms (if enabled)
        timelock_analysis = {}
        if check_timelock:
            timelock_analysis = _analyze_timelock_mechanisms(w3, token_address)
        
        # Check for multisig wallets (if enabled)
        multisig_analysis = {}
        if check_multisig and ownership_analysis.get('owner_address'):
            multisig_analysis = _analyze_multisig_wallet(w3, ownership_analysis['owner_address'])
        
        # Analyze contract upgradeability
        upgrade_analysis = _analyze_contract_upgradeability(w3, token_address)
        
        # Calculate risk score
        risk_score = _calculate_ownership_risk_score(
            ownership_analysis, admin_analysis, timelock_analysis, 
            multisig_analysis, upgrade_analysis
        )
        
        # Prepare detailed results
        details = {
            'contract_address': token_address,
            'ownership': ownership_analysis,
            'admin_functions': admin_analysis,
            'timelock': timelock_analysis,
            'multisig': multisig_analysis,
            'upgradeability': upgrade_analysis,
            'risk_factors': _identify_risk_factors(
                ownership_analysis, admin_analysis, upgrade_analysis
            ),
            'security_recommendations': _generate_security_recommendations(
                ownership_analysis, admin_analysis, timelock_analysis
            ),
            'centralization_score': _calculate_centralization_score(
                ownership_analysis, admin_analysis, multisig_analysis
            )
        }
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        # Determine status based on risk score
        if risk_score >= 80:
            status = 'FAILED'  # High centralization risk
        elif risk_score >= 60:
            status = 'WARNING'  # Medium risk
        else:
            status = 'COMPLETED'  # Acceptable risk
        
        logger.info(f"Ownership check completed for {token_address} - Risk Score: {risk_score}")
        
        result = create_risk_check_result(
            check_type='OWNERSHIP',
            token_address=token_address,
            status=status,
            risk_score=risk_score,
            details=details,
            execution_time_ms=execution_time_ms
        )
        
        # Store result in database
        _store_ownership_result(result)
        
        return result
        
    except Exception as exc:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"Ownership check failed for {token_address}: {exc} (task: {task_id})")
        
        # Retry logic with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = min(2 ** self.request.retries, 30)
            logger.warning(f"Retrying ownership check for {token_address} in {countdown}s (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=countdown)
        
        # Final failure
        return create_risk_check_result(
            check_type='OWNERSHIP',
            token_address=token_address,
            status='FAILED',
            risk_score=Decimal('100'),
            error_message=str(exc),
            execution_time_ms=execution_time_ms
        )


def _get_web3_connection() -> Web3:
    """Get configured Web3 connection for ownership analysis."""
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


def _analyze_ownership_structure(w3: Web3, token_address: str) -> Dict[str, Any]:
    """
    Analyze the ownership structure of the token contract.
    
    Args:
        w3: Web3 connection
        token_address: Token contract address
        
    Returns:
        Dict with ownership analysis
    """
    try:
        # Try common ownership function signatures
        ownership_functions = [
            'owner()',
            'getOwner()',
            '_owner()',
            'admin()',
            'governance()'
        ]
        
        owner_address = None
        ownership_function = None
        
        # Try each ownership function
        for func_sig in ownership_functions:
            try:
                # Create function call data
                func_selector = w3.keccak(text=func_sig)[:4]
                
                # Call the function
                result = w3.eth.call({
                    'to': token_address,
                    'data': func_selector
                })
                
                # Parse result as address (32 bytes, last 20 are the address)
                if len(result) >= 32:
                    potential_address = '0x' + result[-20:].hex()
                    if is_address(potential_address):
                        owner_address = to_checksum_address(potential_address)
                        ownership_function = func_sig
                        break
                        
            except Exception:
                continue
        
        # Check if ownership is renounced
        is_renounced = False
        renounced_method = None
        
        if owner_address:
            # Check if owner is zero address (common renouncement pattern)
            zero_addresses = [
                '0x0000000000000000000000000000000000000000',
                '0x000000000000000000000000000000000000dEaD'
            ]
            
            if owner_address.lower() in [addr.lower() for addr in zero_addresses]:
                is_renounced = True
                renounced_method = 'zero_address'
            
            # Check if owner is a known burn address
            elif 'dead' in owner_address.lower():
                is_renounced = True
                renounced_method = 'burn_address'
        
        # Analyze owner activity (if not renounced)
        owner_activity = {}
        if owner_address and not is_renounced:
            owner_activity = _analyze_owner_activity(w3, owner_address)
        
        # Check for additional control mechanisms
        control_mechanisms = _check_control_mechanisms(w3, token_address)
        
        return {
            'has_owner': owner_address is not None,
            'owner_address': owner_address,
            'ownership_function': ownership_function,
            'is_renounced': is_renounced,
            'renounced_method': renounced_method,
            'owner_activity': owner_activity,
            'control_mechanisms': control_mechanisms,
            'ownership_type': _classify_ownership_type(
                owner_address, is_renounced, control_mechanisms
            )
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze ownership structure for {token_address}: {e}")
        return {
            'has_owner': False,
            'error': str(e)
        }


def _analyze_admin_functions(w3: Web3, token_address: str) -> Dict[str, Any]:
    """
    Analyze admin functions that could be used maliciously.
    
    Args:
        w3: Web3 connection
        token_address: Token contract address
        
    Returns:
        Dict with admin function analysis
    """
    try:
        # Common dangerous function signatures
        dangerous_functions = {
            # Minting functions
            'mint(address,uint256)': 'Can mint new tokens',
            'mint(uint256)': 'Can mint new tokens',
            'mintTo(address,uint256)': 'Can mint tokens to specific address',
            
            # Burning functions (less dangerous but worth noting)
            'burn(uint256)': 'Can burn tokens',
            'burnFrom(address,uint256)': 'Can burn tokens from any address',
            
            # Transfer restrictions
            'setTransfersPaused(bool)': 'Can pause all transfers',
            'pause()': 'Can pause contract',
            'unpause()': 'Can unpause contract',
            'blacklist(address)': 'Can blacklist addresses',
            'whitelist(address)': 'Can control whitelist',
            
            # Tax/fee modifications
            'setTaxFee(uint256)': 'Can modify tax rates',
            'setBuyFee(uint256)': 'Can modify buy fees',
            'setSellFee(uint256)': 'Can modify sell fees',
            'setFees(uint256,uint256)': 'Can modify trading fees',
            
            # Liquidity manipulation
            'setSwapAndLiquifyEnabled(bool)': 'Can control liquidity swaps',
            'withdrawETH()': 'Can withdraw ETH from contract',
            'withdrawTokens(address)': 'Can withdraw any tokens',
            
            # Ownership transfers
            'transferOwnership(address)': 'Can transfer ownership',
            'renounceOwnership()': 'Can renounce ownership',
            
            # Emergency functions
            'emergencyWithdraw()': 'Emergency withdrawal function',
            'rugPull()': 'Explicit rug pull function (red flag!)',
        }
        
        detected_functions = []
        high_risk_functions = []
        medium_risk_functions = []
        
        # Check for each dangerous function
        for func_sig, description in dangerous_functions.items():
            try:
                func_selector = w3.keccak(text=func_sig)[:4]
                
                # Try to call the function with dummy data to see if it exists
                # This won't execute, just checks if function exists
                try:
                    w3.eth.call({
                        'to': token_address,
                        'data': func_selector + b'\x00' * 64  # Dummy parameters
                    })
                    
                    # If we get here, function exists
                    detected_functions.append({
                        'signature': func_sig,
                        'description': description,
                        'selector': func_selector.hex()
                    })
                    
                    # Classify risk level
                    if any(keyword in func_sig.lower() for keyword in ['mint', 'rug', 'withdraw', 'emergency']):
                        high_risk_functions.append(func_sig)
                    elif any(keyword in func_sig.lower() for keyword in ['pause', 'blacklist', 'fee', 'tax']):
                        medium_risk_functions.append(func_sig)
                        
                except ContractLogicError:
                    # Function exists but reverted (still counts as detected)
                    detected_functions.append({
                        'signature': func_sig,
                        'description': description,
                        'selector': func_selector.hex(),
                        'note': 'Function reverted with dummy data'
                    })
                    
                except BadFunctionCallOutput:
                    # Function doesn't exist
                    pass
                    
            except Exception:
                continue
        
        # Analyze function accessibility
        accessibility_analysis = _analyze_function_accessibility(w3, token_address, detected_functions)
        
        return {
            'total_dangerous_functions': len(detected_functions),
            'high_risk_functions': high_risk_functions,
            'medium_risk_functions': medium_risk_functions,
            'detected_functions': detected_functions,
            'accessibility': accessibility_analysis,
            'has_mint_function': any('mint' in func['signature'].lower() for func in detected_functions),
            'has_pause_function': any('pause' in func['signature'].lower() for func in detected_functions),
            'has_blacklist_function': any('blacklist' in func['signature'].lower() for func in detected_functions),
            'has_fee_modification': any('fee' in func['signature'].lower() or 'tax' in func['signature'].lower() for func in detected_functions),
            'has_emergency_functions': any('emergency' in func['signature'].lower() or 'withdraw' in func['signature'].lower() for func in detected_functions)
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze admin functions for {token_address}: {e}")
        return {
            'total_dangerous_functions': 0,
            'error': str(e)
        }


def _analyze_timelock_mechanisms(w3: Web3, token_address: str) -> Dict[str, Any]:
    """
    Check for timelock mechanisms that could provide additional security.
    
    Args:
        w3: Web3 connection
        token_address: Token contract address
        
    Returns:
        Dict with timelock analysis
    """
    try:
        # Common timelock function signatures
        timelock_functions = [
            'timelock()',
            'timelockAddress()',
            'delay()',
            'getDelay()',
            'proposalDelay()',
            'executionDelay()'
        ]
        
        timelock_detected = False
        timelock_address = None
        delay_period = None
        
        # Check for timelock functions
        for func_sig in timelock_functions:
            try:
                func_selector = w3.keccak(text=func_sig)[:4]
                result = w3.eth.call({
                    'to': token_address,
                    'data': func_selector
                })
                
                if len(result) >= 32:
                    # Could be an address or a delay value
                    if 'address' in func_sig.lower():
                        potential_address = '0x' + result[-20:].hex()
                        if is_address(potential_address) and potential_address != '0x0000000000000000000000000000000000000000':
                            timelock_address = to_checksum_address(potential_address)
                            timelock_detected = True
                    elif 'delay' in func_sig.lower():
                        delay_value = int.from_bytes(result, byteorder='big')
                        if 0 < delay_value < 365 * 24 * 3600:  # Between 0 and 1 year
                            delay_period = delay_value
                            timelock_detected = True
                            
            except Exception:
                continue
        
        # If timelock address detected, analyze the timelock contract
        timelock_contract_analysis = {}
        if timelock_address:
            timelock_contract_analysis = _analyze_timelock_contract(w3, timelock_address)
        
        return {
            'has_timelock': timelock_detected,
            'timelock_address': timelock_address,
            'delay_period_seconds': delay_period,
            'delay_period_hours': delay_period / 3600 if delay_period else None,
            'timelock_contract': timelock_contract_analysis,
            'security_level': _assess_timelock_security(delay_period, timelock_contract_analysis)
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze timelock mechanisms for {token_address}: {e}")
        return {
            'has_timelock': False,
            'error': str(e)
        }


def _analyze_multisig_wallet(w3: Web3, wallet_address: str) -> Dict[str, Any]:
    """
    Analyze if the owner address is a multisig wallet.
    
    Args:
        w3: Web3 connection
        wallet_address: Wallet address to analyze
        
    Returns:
        Dict with multisig analysis
    """
    try:
        # Check if address has contract code
        bytecode = w3.eth.get_code(wallet_address)
        is_contract = len(bytecode) > 0
        
        if not is_contract:
            return {
                'is_multisig': False,
                'is_eoa': True,
                'analysis': 'Externally owned account (single private key)'
            }
        
        # Common multisig function signatures
        multisig_functions = [
            'getOwners()',
            'owners(uint256)',
            'getThreshold()',
            'required()',
            'confirmTransaction(uint256)',
            'executeTransaction(uint256)'
        ]
        
        multisig_indicators = 0
        owners_count = None
        threshold = None
        
        # Check for multisig indicators
        for func_sig in multisig_functions:
            try:
                func_selector = w3.keccak(text=func_sig)[:4]
                result = w3.eth.call({
                    'to': wallet_address,
                    'data': func_selector
                })
                
                if len(result) > 0:
                    multisig_indicators += 1
                    
                    # Try to extract specific values
                    if func_sig == 'getThreshold()' or func_sig == 'required()':
                        threshold = int.from_bytes(result[-32:], byteorder='big')
                        
            except Exception:
                continue
        
        # Determine if it's likely a multisig
        is_multisig = multisig_indicators >= 2
        
        # Try to get owners count if it's a multisig
        if is_multisig:
            try:
                # Try different methods to get owners count
                for method in ['getOwners()', 'owners()']:
                    try:
                        func_selector = w3.keccak(text=method)[:4]
                        result = w3.eth.call({
                            'to': wallet_address,
                            'data': func_selector
                        })
                        
                        if method == 'getOwners()' and len(result) >= 32:
                            # Parse array of addresses
                            owners_count = len(result) // 32
                            break
                            
                    except Exception:
                        continue
                        
            except Exception:
                pass
        
        return {
            'is_multisig': is_multisig,
            'is_eoa': False,
            'is_contract': True,
            'multisig_indicators': multisig_indicators,
            'owners_count': owners_count,
            'threshold': threshold,
            'security_level': _assess_multisig_security(is_multisig, owners_count, threshold)
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze multisig wallet {wallet_address}: {e}")
        return {
            'is_multisig': False,
            'error': str(e)
        }


def _analyze_contract_upgradeability(w3: Web3, token_address: str) -> Dict[str, Any]:
    """
    Analyze if the contract is upgradeable (proxy pattern).
    
    Args:
        w3: Web3 connection
        token_address: Token contract address
        
    Returns:
        Dict with upgradeability analysis
    """
    try:
        # Check for proxy patterns
        proxy_functions = [
            'implementation()',
            'getImplementation()',
            'upgradeTo(address)',
            'upgradeToAndCall(address,bytes)',
            'admin()',
            'getAdmin()'
        ]
        
        is_proxy = False
        implementation_address = None
        admin_address = None
        upgrade_functions = []
        
        # Check for proxy function signatures
        for func_sig in proxy_functions:
            try:
                func_selector = w3.keccak(text=func_sig)[:4]
                result = w3.eth.call({
                    'to': token_address,
                    'data': func_selector
                })
                
                if len(result) >= 32:
                    is_proxy = True
                    upgrade_functions.append(func_sig)
                    
                    # Extract specific addresses
                    if 'implementation' in func_sig.lower():
                        potential_address = '0x' + result[-20:].hex()
                        if is_address(potential_address):
                            implementation_address = to_checksum_address(potential_address)
                    elif 'admin' in func_sig.lower():
                        potential_address = '0x' + result[-20:].hex()
                        if is_address(potential_address):
                            admin_address = to_checksum_address(potential_address)
                            
            except Exception:
                continue
        
        # Check storage slots for proxy patterns (EIP-1967)
        proxy_storage_analysis = _check_proxy_storage_slots(w3, token_address)
        
        return {
            'is_upgradeable': is_proxy or proxy_storage_analysis['has_proxy_slots'],
            'is_proxy': is_proxy,
            'implementation_address': implementation_address,
            'admin_address': admin_address,
            'upgrade_functions': upgrade_functions,
            'storage_analysis': proxy_storage_analysis,
            'risk_level': 'HIGH' if is_proxy else 'LOW'
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze contract upgradeability for {token_address}: {e}")
        return {
            'is_upgradeable': False,
            'error': str(e)
        }


def _calculate_ownership_risk_score(
    ownership: Dict[str, Any],
    admin_functions: Dict[str, Any],
    timelock: Dict[str, Any],
    multisig: Dict[str, Any],
    upgrade: Dict[str, Any]
) -> Decimal:
    """Calculate overall ownership risk score."""
    score = Decimal('0')
    
    # Ownership risk
    if not ownership.get('has_owner'):
        score += Decimal('5')  # No clear owner is slightly risky
    elif not ownership.get('is_renounced'):
        score += Decimal('30')  # Non-renounced ownership is risky
        
        # Additional risk if owner is EOA
        if ownership.get('owner_activity', {}).get('is_eoa'):
            score += Decimal('20')  # Single private key control
    
    # Admin function risk
    dangerous_funcs = admin_functions.get('total_dangerous_functions', 0)
    if dangerous_funcs > 0:
        score += Decimal(str(min(dangerous_funcs * 10, 40)))  # Up to 40 points
        
        # Extra risk for high-risk functions
        if admin_functions.get('has_mint_function'):
            score += Decimal('15')
        if admin_functions.get('has_emergency_functions'):
            score += Decimal('10')
    
    # Timelock benefits (reduces risk)
    if timelock.get('has_timelock'):
        delay_hours = timelock.get('delay_period_hours', 0)
        if delay_hours >= 24:
            score -= Decimal('15')  # Good timelock
        elif delay_hours >= 1:
            score -= Decimal('5')   # Some timelock protection
    
    # Multisig benefits (reduces risk)
    if multisig.get('is_multisig'):
        threshold = multisig.get('threshold', 0)
        owners = multisig.get('owners_count', 0)
        if threshold >= 2 and owners >= 3:
            score -= Decimal('20')  # Good multisig setup
        elif threshold >= 2:
            score -= Decimal('10')  # Basic multisig
    
    # Upgradeability risk
    if upgrade.get('is_upgradeable'):
        score += Decimal('25')  # Upgradeable contracts are risky
    
    # Ensure score is within bounds
    return max(Decimal('0'), min(score, Decimal('100')))


# Helper functions

def _analyze_owner_activity(w3: Web3, owner_address: str) -> Dict[str, Any]:
    """Analyze the activity and characteristics of the owner address."""
    try:
        # Check if it's an EOA or contract
        bytecode = w3.eth.get_code(owner_address)
        is_eoa = len(bytecode) == 0
        
        # Get transaction count
        tx_count = w3.eth.get_transaction_count(owner_address)
        
        # Get current balance
        balance = w3.eth.get_balance(owner_address)
        balance_eth = float(w3.from_wei(balance, 'ether'))
        
        return {
            'is_eoa': is_eoa,
            'transaction_count': tx_count,
            'balance_eth': balance_eth,
            'is_active': tx_count > 0,
            'activity_level': 'HIGH' if tx_count > 100 else 'MEDIUM' if tx_count > 10 else 'LOW'
        }
        
    except Exception as e:
        logger.warning(f"Failed to analyze owner activity for {owner_address}: {e}")
        return {'error': str(e)}


def _check_control_mechanisms(w3: Web3, token_address: str) -> Dict[str, Any]:
    """Check for additional control mechanisms in the contract."""
    try:
        control_functions = [
            'pause()',
            'unpause()',
            'blacklist(address)',
            'whitelist(address)',
            'excludeFromFee(address)',
            'includeInFee(address)'
        ]
        
        detected_controls = []
        
        for func_sig in control_functions:
            try:
                func_selector = w3.keccak(text=func_sig)[:4]
                # Just check if function exists
                w3.eth.call({
                    'to': token_address,
                    'data': func_selector + b'\x00' * 64
                })
                detected_controls.append(func_sig)
            except BadFunctionCallOutput:
                pass  # Function doesn't exist
            except Exception:
                detected_controls.append(func_sig)  # Function exists but reverted
        
        return {
            'detected_controls': detected_controls,
            'has_pause_mechanism': any('pause' in func for func in detected_controls),
            'has_blacklist_mechanism': any('blacklist' in func for func in detected_controls),
            'has_whitelist_mechanism': any('whitelist' in func for func in detected_controls),
            'control_count': len(detected_controls)
        }
        
    except Exception as e:
        return {'error': str(e)}


def _classify_ownership_type(owner_address: str, is_renounced: bool, control_mechanisms: Dict) -> str:
    """Classify the type of ownership structure."""
    if is_renounced:
        return 'RENOUNCED'
    elif not owner_address:
        return 'NO_OWNER'
    elif control_mechanisms.get('control_count', 0) > 3:
        return 'CENTRALIZED_CONTROLLED'
    else:
        return 'OWNED'


def _analyze_function_accessibility(w3: Web3, token_address: str, functions: List[Dict]) -> Dict[str, Any]:
    """Analyze who can access the detected dangerous functions."""
    # This is a simplified analysis
    # In production, you'd analyze function modifiers and access controls
    
    return {
        'analysis_method': 'simplified',
        'assumption': 'Functions likely restricted to owner/admin',
        'recommendation': 'Manual verification needed for precise access control analysis'
    }


def _analyze_timelock_contract(w3: Web3, timelock_address: str) -> Dict[str, Any]:
    """Analyze the timelock contract details."""
    try:
        bytecode = w3.eth.get_code(timelock_address)
        if len(bytecode) == 0:
            return {'is_contract': False}
        
        # Basic analysis of timelock contract
        return {
            'is_contract': True,
            'has_bytecode': True,
            'analysis': 'Timelock contract detected'
        }
        
    except Exception as e:
        return {'error': str(e)}


def _check_proxy_storage_slots(w3: Web3, token_address: str) -> Dict[str, Any]:
    """Check EIP-1967 proxy storage slots."""
    try:
        # EIP-1967 standard storage slots
        implementation_slot = '0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'
        admin_slot = '0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103'
        
        # Read storage slots
        impl_data = w3.eth.get_storage_at(token_address, implementation_slot)
        admin_data = w3.eth.get_storage_at(token_address, admin_slot)
        
        has_implementation = impl_data != b'\x00' * 32
        has_admin = admin_data != b'\x00' * 32
        
        return {
            'has_proxy_slots': has_implementation or has_admin,
            'has_implementation_slot': has_implementation,
            'has_admin_slot': has_admin,
            'implementation_data': impl_data.hex() if has_implementation else None,
            'admin_data': admin_data.hex() if has_admin else None
        }
        
    except Exception as e:
        return {'error': str(e)}


def _assess_timelock_security(delay_period: Optional[int], timelock_analysis: Dict) -> str:
    """Assess the security level provided by timelock."""
    if not delay_period:
        return 'NONE'
    
    hours = delay_period / 3600
    if hours >= 72:  # 3+ days
        return 'HIGH'
    elif hours >= 24:  # 1+ day
        return 'MEDIUM'
    elif hours >= 1:  # 1+ hour
        return 'LOW'
    else:
        return 'MINIMAL'


def _assess_multisig_security(is_multisig: bool, owners_count: Optional[int], threshold: Optional[int]) -> str:
    """Assess the security level provided by multisig."""
    if not is_multisig:
        return 'NONE'
    
    if not owners_count or not threshold:
        return 'UNKNOWN'
    
    if threshold >= 3 and owners_count >= 5:
        return 'HIGH'
    elif threshold >= 2 and owners_count >= 3:
        return 'MEDIUM'
    elif threshold >= 2:
        return 'LOW'
    else:
        return 'MINIMAL'


def _identify_risk_factors(ownership: Dict, admin_functions: Dict, upgrade: Dict) -> List[str]:
    """Identify specific risk factors."""
    risks = []
    
    if not ownership.get('is_renounced') and ownership.get('has_owner'):
        risks.append('Ownership not renounced')
    
    if admin_functions.get('has_mint_function'):
        risks.append('Can mint new tokens')
    
    if admin_functions.get('has_pause_function'):
        risks.append('Can pause trading')
    
    if admin_functions.get('has_blacklist_function'):
        risks.append('Can blacklist addresses')
    
    if upgrade.get('is_upgradeable'):
        risks.append('Contract is upgradeable')
    
    if ownership.get('owner_activity', {}).get('is_eoa'):
        risks.append('Owner is single private key (EOA)')
    
    return risks


def _generate_security_recommendations(ownership: Dict, admin_functions: Dict, timelock: Dict) -> List[str]:
    """Generate security recommendations."""
    recommendations = []
    
    if not ownership.get('is_renounced'):
        recommendations.append('Owner should renounce ownership')
    
    if admin_functions.get('total_dangerous_functions', 0) > 0 and not timelock.get('has_timelock'):
        recommendations.append('Add timelock for admin functions')
    
    if ownership.get('owner_activity', {}).get('is_eoa'):
        recommendations.append('Use multisig wallet for ownership')
    
    if admin_functions.get('has_mint_function'):
        recommendations.append('Consider removing mint function or adding strict controls')
    
    return recommendations


def _calculate_centralization_score(ownership: Dict, admin_functions: Dict, multisig: Dict) -> float:
    """Calculate centralization score (0-100, higher = more centralized)."""
    score = 0
    
    # Base centralization from ownership
    if ownership.get('has_owner') and not ownership.get('is_renounced'):
        score += 40
        
        if ownership.get('owner_activity', {}).get('is_eoa'):
            score += 30  # Single private key is highly centralized
    
    # Admin functions add centralization
    dangerous_funcs = admin_functions.get('total_dangerous_functions', 0)
    score += min(dangerous_funcs * 5, 30)
    
    # Multisig reduces centralization
    if multisig.get('is_multisig'):
        threshold = multisig.get('threshold', 0)
        owners = multisig.get('owners_count', 0)
        if threshold >= 2 and owners >= 3:
            score -= 25
        elif threshold >= 2:
            score -= 15
    
    return max(0, min(score, 100))


def _store_ownership_result(result: Dict[str, Any]) -> None:
    """Store ownership check result in database."""
    try:
        with transaction.atomic():
            # This would create/update RiskCheckResult model
            logger.debug(f"Storing ownership result for {result['token_address']}")
    except Exception as e:
        logger.error(f"Failed to store ownership result: {e}")