"""
Real Ownership Analysis Implementation

This module performs actual ownership analysis by checking contract ownership,
renouncement status, and analyzing owner privileges and potential risks.

File: dexproject/risk/tasks/ownership.py
"""

import logging
import asyncio
import time
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timezone
from web3 import Web3
from web3.exceptions import Web3Exception
from eth_utils import is_address, to_checksum_address

logger = logging.getLogger(__name__)


class OwnershipAnalyzer:
    """Real ownership analysis for token contracts."""
    
    def __init__(self, web3_provider: Web3, chain_id: int):
        """
        Initialize ownership analyzer.
        
        Args:
            web3_provider: Web3 instance with RPC connection
            chain_id: Chain ID for network-specific analysis
        """
        self.w3 = web3_provider
        self.chain_id = chain_id
        self.logger = logger.getChild(self.__class__.__name__)
        
        # Common ownership function signatures
        self.ownership_signatures = {
            'owner': '0x8da5cb5b',           # owner()
            'transferOwnership': '0xf2fde38b',  # transferOwnership(address)
            'renounceOwnership': '0x715018a6',  # renounceOwnership()
            'getOwner': '0x893d20e8',        # getOwner() - BSC standard
        }
        
        # Known burn/renounce addresses
        self.burn_addresses = {
            '0x000000000000000000000000000000000000dead',
            '0x0000000000000000000000000000000000000000',
            '0x0000000000000000000000000000000000000001',
        }
    
    async def analyze_ownership(
        self, 
        token_address: str
    ) -> Dict[str, Any]:
        """
        Perform comprehensive ownership analysis.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Dict with ownership analysis results
        """
        start_time = time.time()
        
        try:
            # Validate address
            if not is_address(token_address):
                return self._create_error_result("Invalid token address")
            
            token_address = to_checksum_address(token_address)
            
            # Get contract bytecode
            bytecode_analysis = await self._analyze_contract_bytecode(token_address)
            
            # Check ownership functions
            ownership_functions = await self._check_ownership_functions(token_address)
            
            # Analyze current owner
            current_owner_analysis = await self._analyze_current_owner(token_address)
            
            # Check for privileged functions
            privileged_functions = await self._analyze_privileged_functions(token_address)
            
            # Check ownership history
            ownership_history = await self._analyze_ownership_history(token_address)
            
            # Analyze contract upgradability
            upgradability_analysis = await self._analyze_upgradability(token_address)
            
            # Calculate overall ownership risk
            overall_risk = self._calculate_ownership_risk(
                ownership_functions, current_owner_analysis, 
                privileged_functions, upgradability_analysis
            )
            
            execution_time = (time.time() - start_time) * 1000
            
            return {
                'check_type': 'OWNERSHIP',
                'token_address': token_address,
                'status': 'COMPLETED',
                'risk_score': overall_risk['risk_score'],
                'is_renounced': overall_risk['is_renounced'],
                'details': {
                    'bytecode_analysis': bytecode_analysis,
                    'ownership_functions': ownership_functions,
                    'current_owner_analysis': current_owner_analysis,
                    'privileged_functions': privileged_functions,
                    'ownership_history': ownership_history,
                    'upgradability_analysis': upgradability_analysis,
                    'risk_factors': overall_risk['risk_factors'],
                    'ownership_rating': overall_risk['rating'],
                },
                'execution_time_ms': execution_time,
                'chain_id': self.chain_id,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self.logger.error(f"Ownership analysis failed for {token_address}: {e}")
            
            return {
                'check_type': 'OWNERSHIP',
                'token_address': token_address,
                'status': 'FAILED',
                'error_message': str(e),
                'execution_time_ms': execution_time,
                'risk_score': 75.0,  # High risk on failure
                'is_renounced': False,
                'chain_id': self.chain_id,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
    
    async def _analyze_contract_bytecode(self, token_address: str) -> Dict[str, Any]:
        """
        Analyze contract bytecode for ownership patterns.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Dict with bytecode analysis results
        """
        try:
            code = self.w3.eth.get_code(token_address)
            code_hex = code.hex()
            
            if len(code_hex) < 10:
                return {
                    'has_code': False,
                    'is_contract': False,
                    'analysis': 'not_a_contract'
                }
            
            # Check for ownership patterns in bytecode
            has_owner_function = self.ownership_signatures['owner'][2:] in code_hex
            has_transfer_ownership = self.ownership_signatures['transferOwnership'][2:] in code_hex
            has_renounce_ownership = self.ownership_signatures['renounceOwnership'][2:] in code_hex
            
            # Check for common ownership patterns
            patterns_found = []
            
            if has_owner_function:
                patterns_found.append('owner_function')
            if has_transfer_ownership:
                patterns_found.append('transfer_ownership')
            if has_renounce_ownership:
                patterns_found.append('renounce_ownership')
            
            # Check for Ownable pattern (OpenZeppelin)
            ownable_pattern = '8da5cb5b' in code_hex and 'f2fde38b' in code_hex
            if ownable_pattern:
                patterns_found.append('ownable_pattern')
            
            return {
                'has_code': True,
                'is_contract': True,
                'code_size_bytes': len(code),
                'has_owner_function': has_owner_function,
                'has_transfer_ownership': has_transfer_ownership,
                'has_renounce_ownership': has_renounce_ownership,
                'ownable_pattern': ownable_pattern,
                'patterns_found': patterns_found
            }
            
        except Exception as e:
            self.logger.error(f"Bytecode analysis failed: {e}")
            return {
                'has_code': False,
                'error': str(e)
            }
    
    async def _check_ownership_functions(self, token_address: str) -> Dict[str, Any]:
        """
        Check for ownership-related functions by calling them.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Dict with function check results
        """
        try:
            results = {}
            
            # Check owner() function
            owner_address = await self._call_owner_function(token_address)
            results['owner_function'] = {
                'exists': owner_address is not None,
                'owner_address': owner_address,
                'is_burn_address': owner_address in self.burn_addresses if owner_address else False
            }
            
            # Check getOwner() function (BSC standard)
            get_owner_address = await self._call_get_owner_function(token_address)
            results['get_owner_function'] = {
                'exists': get_owner_address is not None,
                'owner_address': get_owner_address,
                'is_burn_address': get_owner_address in self.burn_addresses if get_owner_address else False
            }
            
            # Determine the actual owner
            actual_owner = owner_address or get_owner_address
            results['actual_owner'] = actual_owner
            results['is_renounced'] = actual_owner in self.burn_addresses if actual_owner else False
            
            return results
            
        except Exception as e:
            self.logger.error(f"Ownership function check failed: {e}")
            return {
                'error': str(e),
                'is_renounced': False
            }
    
    async def _call_owner_function(self, token_address: str) -> Optional[str]:
        """Call owner() function."""
        try:
            # Create minimal contract interface
            owner_abi = [{
                "constant": True,
                "inputs": [],
                "name": "owner",
                "outputs": [{"name": "", "type": "address"}],
                "type": "function"
            }]
            
            contract = self.w3.eth.contract(
                address=to_checksum_address(token_address),
                abi=owner_abi
            )
            
            owner = contract.functions.owner().call()
            return to_checksum_address(owner) if owner else None
            
        except Exception as e:
            self.logger.debug(f"owner() call failed: {e}")
            return None
    
    async def _call_get_owner_function(self, token_address: str) -> Optional[str]:
        """Call getOwner() function (BSC standard)."""
        try:
            # Create minimal contract interface
            get_owner_abi = [{
                "constant": True,
                "inputs": [],
                "name": "getOwner",
                "outputs": [{"name": "", "type": "address"}],
                "type": "function"
            }]
            
            contract = self.w3.eth.contract(
                address=to_checksum_address(token_address),
                abi=get_owner_abi
            )
            
            owner = contract.functions.getOwner().call()
            return to_checksum_address(owner) if owner else None
            
        except Exception as e:
            self.logger.debug(f"getOwner() call failed: {e}")
            return None
    
    async def _analyze_current_owner(self, token_address: str) -> Dict[str, Any]:
        """
        Analyze the current owner address.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Dict with owner analysis
        """
        try:
            # Get owner from functions
            owner_address = await self._call_owner_function(token_address)
            
            if not owner_address:
                return {
                    'has_owner': False,
                    'analysis': 'no_owner_function'
                }
            
            # Check if owner is a burn address
            is_burn = owner_address.lower() in [addr.lower() for addr in self.burn_addresses]
            
            if is_burn:
                return {
                    'has_owner': True,
                    'owner_address': owner_address,
                    'is_renounced': True,
                    'owner_type': 'burn_address',
                    'risk_level': 'LOW'
                }
            
            # Analyze owner address
            owner_analysis = await self._analyze_owner_address(owner_address)
            
            return {
                'has_owner': True,
                'owner_address': owner_address,
                'is_renounced': False,
                'owner_analysis': owner_analysis,
                'risk_level': owner_analysis.get('risk_level', 'HIGH')
            }
            
        except Exception as e:
            self.logger.error(f"Current owner analysis failed: {e}")
            return {
                'has_owner': False,
                'error': str(e),
                'risk_level': 'HIGH'
            }
    
    async def _analyze_owner_address(self, owner_address: str) -> Dict[str, Any]:
        """
        Analyze the owner address for patterns and risks.
        
        Args:
            owner_address: Owner address to analyze
            
        Returns:
            Dict with address analysis
        """
        try:
            # Check if owner is a contract
            code = self.w3.eth.get_code(owner_address)
            is_contract = len(code) > 2
            
            # Get ETH balance
            balance_wei = self.w3.eth.get_balance(owner_address)
            balance_eth = Decimal(balance_wei) / (10**18)
            
            # Check transaction count
            tx_count = self.w3.eth.get_transaction_count(owner_address)
            
            # Analyze patterns
            risk_factors = []
            risk_level = 'MEDIUM'
            
            if is_contract:
                risk_factors.append('owner_is_contract')
                # Could be a multisig or governance contract (lower risk)
                # or could be an upgradeable proxy (higher risk)
                risk_level = 'MEDIUM'
            else:
                # EOA (Externally Owned Account)
                if tx_count == 0:
                    risk_factors.append('unused_address')
                    risk_level = 'HIGH'
                elif tx_count < 10:
                    risk_factors.append('low_activity_address')
                    risk_level = 'HIGH'
                elif balance_eth < Decimal('0.001'):
                    risk_factors.append('low_balance_owner')
                    risk_level = 'MEDIUM'
                else:
                    risk_level = 'MEDIUM'
            
            return {
                'is_contract': is_contract,
                'balance_eth': str(balance_eth),
                'transaction_count': tx_count,
                'risk_factors': risk_factors,
                'risk_level': risk_level
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'risk_level': 'HIGH'
            }
    
    async def _analyze_privileged_functions(self, token_address: str) -> Dict[str, Any]:
        """
        Analyze privileged functions that could be dangerous.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Dict with privileged function analysis
        """
        try:
            # Get contract bytecode
            code = self.w3.eth.get_code(token_address)
            code_hex = code.hex().lower()
            
            # Common dangerous function signatures
            dangerous_functions = {
                'mint': ['40c10f19', 'a0712d68'],  # mint(address,uint256), mint(uint256)
                'burn': ['42966c68', '9dc29fac'],  # burn(uint256), burn(address,uint256)
                'pause': ['8456cb59'],              # pause()
                'unpause': ['3f4ba83a'],            # unpause()
                'blacklist': ['f9f92be4', '608e8e6f'], # Various blacklist functions
                'setTaxes': ['8a8c523c', '7d1db4a5'],  # Tax modification functions
                'setFees': ['6d1b229d'],            # Fee modification
                'transfer': ['a9059cbb'],           # transfer (if restricted)
                'withdraw': ['3ccfd60b', '2e1a7d4d'], # withdraw functions
                'changeRouter': ['8f9a55c0'],       # Router changes
                'setLimits': ['7d1db4a5'],          # Trading limits
            }
            
            found_functions = {}
            risk_score = 0
            
            for func_name, signatures in dangerous_functions.items():
                found = any(sig in code_hex for sig in signatures)
                found_functions[func_name] = found
                
                if found:
                    # Add risk based on function danger level
                    risk_additions = {
                        'mint': 25,
                        'burn': 15,
                        'pause': 20,
                        'blacklist': 30,
                        'setTaxes': 25,
                        'setFees': 20,
                        'withdraw': 15,
                        'changeRouter': 20,
                        'setLimits': 15
                    }
                    risk_score += risk_additions.get(func_name, 10)
            
            # Check for modifier patterns (onlyOwner, etc.)
            has_access_control = any(pattern in code_hex for pattern in [
                '8da5cb5b',  # owner()
                '715018a6',  # renounceOwnership()
                'f2fde38b'   # transferOwnership()
            ])
            
            return {
                'found_functions': found_functions,
                'has_access_control': has_access_control,
                'privilege_risk_score': min(risk_score, 100),
                'dangerous_functions_count': sum(found_functions.values()),
                'risk_level': self._get_privilege_risk_level(risk_score)
            }
            
        except Exception as e:
            self.logger.error(f"Privileged function analysis failed: {e}")
            return {
                'error': str(e),
                'privilege_risk_score': 50,
                'risk_level': 'MEDIUM'
            }
    
    async def _analyze_ownership_history(self, token_address: str) -> Dict[str, Any]:
        """
        Analyze ownership transfer history.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Dict with ownership history
        """
        try:
            # This would typically involve scanning event logs
            # For now, we'll implement a basic version
            
            current_block = self.w3.eth.block_number
            
            # Look for OwnershipTransferred events
            ownership_events = []
            
            # Event signature for OwnershipTransferred(address,address)
            ownership_transfer_topic = self.w3.keccak(text="OwnershipTransferred(address,address)").hex()
            
            try:
                # Search recent blocks for ownership transfer events
                events = self.w3.eth.get_logs({
                    'address': token_address,
                    'topics': [ownership_transfer_topic],
                    'fromBlock': max(0, current_block - 10000),  # Last ~10k blocks
                    'toBlock': 'latest'
                })
                
                for event in events:
                    # Decode the event data
                    previous_owner = '0x' + event['topics'][1].hex()[26:]  # Remove padding
                    new_owner = '0x' + event['topics'][2].hex()[26:]      # Remove padding
                    
                    ownership_events.append({
                        'block_number': event['blockNumber'],
                        'transaction_hash': event['transactionHash'].hex(),
                        'previous_owner': to_checksum_address(previous_owner),
                        'new_owner': to_checksum_address(new_owner),
                        'is_renouncement': new_owner.lower() in [addr.lower() for addr in self.burn_addresses]
                    })
                
            except Exception as e:
                self.logger.debug(f"Event log search failed: {e}")
            
            # Analyze the history
            transfer_count = len(ownership_events)
            has_renouncement = any(event['is_renouncement'] for event in ownership_events)
            
            return {
                'transfer_count': transfer_count,
                'has_renouncement': has_renouncement,
                'recent_transfers': ownership_events[-5:],  # Last 5 transfers
                'history_risk_score': min(transfer_count * 10, 50) if transfer_count > 2 else 0
            }
            
        except Exception as e:
            self.logger.error(f"Ownership history analysis failed: {e}")
            return {
                'error': str(e),
                'transfer_count': 0,
                'has_renouncement': False,
                'history_risk_score': 25
            }
    
    async def _analyze_upgradability(self, token_address: str) -> Dict[str, Any]:
        """
        Analyze if contract is upgradeable.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Dict with upgradability analysis
        """
        try:
            code = self.w3.eth.get_code(token_address)
            code_hex = code.hex().lower()
            
            # Check for proxy patterns
            proxy_patterns = {
                'eip1967': '360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc',  # Implementation slot
                'eip1822': 'c5f16f0fcc639fa48a6947836d9850f504798523bf8c9a3a87d5876cf622bcf7',   # Proxiable UUID
                'eip1538': '455a40ca4db8c2c74fed8cc36b7d29a4b29e5c1ccecf5e5a5bd9bed9cfcdf1ec',   # Diamond storage
                'minimal_proxy': '363d3d373d3d3d363d73',  # Minimal proxy bytecode pattern
                'delegate_call': '3d3d3d3d363d3d37363d73'   # Delegate call pattern
            }
            
            found_patterns = []
            is_proxy = False
            
            for pattern_name, pattern in proxy_patterns.items():
                if pattern in code_hex:
                    found_patterns.append(pattern_name)
                    is_proxy = True
            
            # Check for implementation slot reading
            has_implementation_slot = any(pattern in code_hex for pattern in [
                '360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc',
                'sload',  # Storage load operations
                'delegatecall'
            ])
            
            # Calculate upgradability risk
            upgrade_risk = 0
            if is_proxy:
                upgrade_risk += 40
            if has_implementation_slot:
                upgrade_risk += 20
            if len(found_patterns) > 1:
                upgrade_risk += 15
            
            return {
                'is_proxy': is_proxy,
                'proxy_patterns': found_patterns,
                'has_implementation_slot': has_implementation_slot,
                'upgrade_risk_score': min(upgrade_risk, 100),
                'risk_level': 'HIGH' if upgrade_risk > 50 else 'MEDIUM' if upgrade_risk > 20 else 'LOW'
            }
            
        except Exception as e:
            self.logger.error(f"Upgradability analysis failed: {e}")
            return {
                'error': str(e),
                'is_proxy': False,
                'upgrade_risk_score': 25,
                'risk_level': 'MEDIUM'
            }
    
    def _calculate_ownership_risk(
        self,
        ownership_functions: Dict,
        current_owner_analysis: Dict,
        privileged_functions: Dict,
        upgradability_analysis: Dict
    ) -> Dict[str, Any]:
        """Calculate overall ownership risk score."""
        
        risk_score = 0
        risk_factors = []
        is_renounced = False
        
        # Check if ownership is renounced
        if ownership_functions.get('is_renounced') or current_owner_analysis.get('is_renounced'):
            is_renounced = True
            risk_score = 5  # Very low risk when renounced
        else:
            # Owner exists and not renounced
            risk_score += 30  # Base risk for having an owner
            risk_factors.append('has_active_owner')
            
            # Add owner-specific risks
            owner_risk = current_owner_analysis.get('risk_level', 'HIGH')
            if owner_risk == 'HIGH':
                risk_score += 25
                risk_factors.append('high_risk_owner')
            elif owner_risk == 'MEDIUM':
                risk_score += 15
                risk_factors.append('medium_risk_owner')
        
        # Add privileged function risks
        privilege_risk = privileged_functions.get('privilege_risk_score', 0)
        risk_score += min(privilege_risk * 0.4, 30)  # Scale down privilege risk
        
        if privileged_functions.get('dangerous_functions_count', 0) > 3:
            risk_factors.append('many_dangerous_functions')
        
        # Add upgradability risks
        upgrade_risk = upgradability_analysis.get('upgrade_risk_score', 0)
        risk_score += min(upgrade_risk * 0.3, 20)  # Scale down upgrade risk
        
        if upgradability_analysis.get('is_proxy'):
            risk_factors.append('upgradeable_contract')
        
        # Cap the risk score
        final_risk_score = min(risk_score, 100)
        
        # Determine rating
        if final_risk_score <= 20:
            rating = "EXCELLENT"
        elif final_risk_score <= 40:
            rating = "GOOD"
        elif final_risk_score <= 60:
            rating = "FAIR"
        else:
            rating = "POOR"
        
        return {
            'risk_score': final_risk_score,
            'is_renounced': is_renounced,
            'risk_factors': risk_factors,
            'rating': rating
        }
    
    def _get_privilege_risk_level(self, risk_score: float) -> str:
        """Get risk level for privileged functions."""
        if risk_score >= 60:
            return "CRITICAL"
        elif risk_score >= 40:
            return "HIGH"
        elif risk_score >= 20:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _create_error_result(self, error_message: str) -> Dict[str, Any]:
        """Create standardized error result."""
        return {
            'check_type': 'OWNERSHIP',
            'status': 'FAILED',
            'error_message': error_message,
            'risk_score': 75.0,
            'is_renounced': False,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }


# =============================================================================
# COMPATIBILITY WRAPPER FOR MANAGEMENT COMMAND TESTS
# =============================================================================

def ownership_check(
    token_address: str,
    check_admin_functions: bool = True,
    check_timelock: bool = True,
    check_multisig: bool = True,
    timeout_seconds: int = None
) -> Dict[str, Any]:
    """
    Synchronous wrapper for ownership analysis to maintain compatibility with tests.
    
    This function provides the interface expected by the management command test
    while delegating to the comprehensive OwnershipAnalyzer when Web3 is available.
    
    Args:
        token_address: The token contract address to analyze
        check_admin_functions: Whether to check for dangerous admin functions
        check_timelock: Whether to check for timelock mechanisms
        check_multisig: Whether to check for multisig ownership
        timeout_seconds: Maximum time to spend on analysis
        
    Returns:
        Dictionary containing risk assessment results
    """
    
    start_time = time.time()
    
    try:
        # Try to get a Web3 connection for real analysis
        web3_instance = _get_web3_connection()
        
        if web3_instance and web3_instance.is_connected():
            # Use real analysis with Web3 connection
            from django.conf import settings
            chain_id = getattr(settings, 'DEFAULT_CHAIN_ID', 1)
            
            analyzer = OwnershipAnalyzer(web3_instance, chain_id)
            
            # Run async analysis in sync context
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            result = loop.run_until_complete(analyzer.analyze_ownership(token_address))
            
            # Add the specific fields the test expects
            result.update({
                'details': {
                    **result.get('details', {}),
                    'ownership_analysis': result.get('details', {}).get('current_owner_analysis', {}),
                    'admin_analysis': result.get('details', {}).get('privileged_functions', {}),
                    'timelock_analysis': {'has_timelock': None, 'confidence_level': 'LOW'},
                    'multisig_analysis': {'is_multisig': None, 'confidence_level': 'LOW'},
                    'upgrade_analysis': result.get('details', {}).get('upgradability_analysis', {}),
                }
            })
            
            return result
            
        else:
            # Fallback to minimal analysis when Web3 is not available
            return _minimal_ownership_check(
                token_address, check_admin_functions, check_timelock, 
                check_multisig, timeout_seconds, start_time
            )
            
    except Exception as e:
        logger.warning(f"Real ownership analysis failed, falling back to minimal: {e}")
        return _minimal_ownership_check(
            token_address, check_admin_functions, check_timelock, 
            check_multisig, timeout_seconds, start_time
        )


def _get_web3_connection() -> Optional[Web3]:
    """
    Get a Web3 connection for ownership analysis.
    
    Returns:
        Web3 instance or None if connection fails
    """
    try:
        from django.conf import settings
        
        # Determine which RPC URL to use based on testnet mode
        testnet_mode = getattr(settings, 'TESTNET_MODE', False)
        default_chain_id = getattr(settings, 'DEFAULT_CHAIN_ID', 1)
        
        rpc_url = None
        
        if testnet_mode:
            if default_chain_id == 84532:  # Base Sepolia
                rpc_url = getattr(settings, 'BASE_SEPOLIA_RPC_URL', None)
            elif default_chain_id == 11155111:  # Sepolia
                rpc_url = getattr(settings, 'SEPOLIA_RPC_URL', None)
            elif default_chain_id == 421614:  # Arbitrum Sepolia
                rpc_url = getattr(settings, 'ARBITRUM_SEPOLIA_RPC_URL', None)
        else:
            if default_chain_id == 8453:  # Base
                rpc_url = getattr(settings, 'BASE_RPC_URL', None)
            elif default_chain_id == 1:  # Ethereum
                rpc_url = getattr(settings, 'ETH_RPC_URL', None)
            elif default_chain_id == 42161:  # Arbitrum
                rpc_url = getattr(settings, 'ARBITRUM_RPC_URL', None)
        
        if not rpc_url:
            logger.debug("No RPC URL configured for Web3 connection")
            return None
        
        # Create Web3 instance
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        # Test connection
        if w3.is_connected():
            logger.debug(f"Web3 connected to {rpc_url[:50]}...")
            return w3
        else:
            logger.debug("Web3 connection failed")
            return None
            
    except Exception as e:
        logger.debug(f"Could not create Web3 connection: {e}")
        return None


def _minimal_ownership_check(
    token_address: str,
    check_admin_functions: bool,
    check_timelock: bool,
    check_multisig: bool,
    timeout_seconds: int,
    start_time: float
) -> Dict[str, Any]:
    """
    Minimal ownership check for when Web3 is not available.
    
    This provides the expected interface and structure while indicating
    that full analysis requires blockchain connectivity.
    """
    
    logger.info(f"Performing minimal ownership check for token {token_address}")
    
    # Validate input
    if not is_address(token_address):
        return _create_error_result(
            "INVALID_ADDRESS",
            f"Invalid token address format: {token_address}",
            start_time
        )
    
    # Create minimal analysis structure
    details = {
        'ownership_analysis': {
            'owner_address': None,
            'is_renounced': None,
            'ownership_type': 'UNKNOWN',
            'can_change_ownership': None,
            'analysis_method': 'MINIMAL',
            'confidence_level': 'LOW',
            'warnings': ['Blockchain connection required for full ownership analysis']
        },
        'admin_analysis': {
            'dangerous_functions': [],
            'total_dangerous_functions': 0,
            'has_mint_function': None,
            'has_burn_function': None,
            'has_pause_function': None,
            'analysis_method': 'MINIMAL',
            'confidence_level': 'LOW',
            'warnings': ['Contract ABI and blockchain connection required for function analysis']
        } if check_admin_functions else {},
        'timelock_analysis': {
            'has_timelock': None,
            'timelock_address': None,
            'delay_seconds': None,
            'timelock_type': 'UNKNOWN',
            'analysis_method': 'MINIMAL',
            'confidence_level': 'LOW',
            'warnings': ['Blockchain connection required for timelock verification']
        } if check_timelock else {},
        'multisig_analysis': {
            'is_multisig': None,
            'multisig_address': None,
            'required_signatures': None,
            'total_signers': None,
            'multisig_type': 'UNKNOWN',
            'analysis_method': 'MINIMAL',
            'confidence_level': 'LOW',
            'warnings': ['Blockchain connection required for multisig detection']
        } if check_multisig else {},
        'upgrade_analysis': {
            'is_upgradeable': None,
            'risk_level': 'UNKNOWN',
            'analysis_method': 'MINIMAL',
            'confidence_level': 'LOW',
            'warnings': ['Blockchain connection required for upgradability analysis']
        }
    }
    
    # Calculate execution time
    execution_time_ms = int((time.time() - start_time) * 1000)
    
    # Return standardized result
    return {
        'check_type': 'OWNERSHIP',
        'status': 'COMPLETED',
        'token_address': token_address,
        'risk_score': 50,  # Neutral score when analysis is limited
        'details': details,
        'execution_time_ms': execution_time_ms,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'warnings': ['Limited analysis - full ownership assessment requires blockchain connectivity']
    }


def _create_error_result(error_code: str, error_message: str, start_time: float) -> Dict[str, Any]:
    """Create a standardized error result."""
    
    execution_time_ms = int((time.time() - start_time) * 1000)
    
    return {
        'check_type': 'OWNERSHIP',
        'status': 'ERROR',
        'error_code': error_code,
        'error_message': error_message,
        'risk_score': 100,  # Maximum risk for errors
        'details': {
            'error': {
                'code': error_code,
                'message': error_message,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        },
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'execution_time_ms': execution_time_ms,
    }


# =============================================================================
# ADDITIONAL UTILITY FUNCTIONS
# =============================================================================

def create_risk_check_result(
    check_type: str,
    status: str,
    risk_score: Decimal,
    details: Dict[str, Any],
    execution_time_ms: int,
    token_address: str = None
) -> Dict[str, Any]:
    """
    Create a standardized risk check result structure.
    
    This function provides a consistent format for all risk check results.
    """
    
    result = {
        'check_type': check_type,
        'status': status,
        'risk_score': float(risk_score),
        'details': details,
        'execution_time_ms': execution_time_ms,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    
    if token_address:
        result['token_address'] = token_address
    
    return result


# Celery task wrapper for async execution
async def perform_ownership_check(
    web3_provider: Web3,
    token_address: str,
    chain_id: int
) -> Dict[str, Any]:
    """
    Perform real ownership analysis.
    
    Args:
        web3_provider: Web3 instance
        token_address: Token contract address
        chain_id: Blockchain chain ID
        
    Returns:
        Dict with ownership analysis results
    """
    analyzer = OwnershipAnalyzer(web3_provider, chain_id)
    return await analyzer.analyze_ownership(token_address)