"""
Unit Tests for Ownership Analysis

File: dexproject/risk/tests/test_ownership.py

Comprehensive unit tests for ownership analysis functions using mocked Web3 responses.
Tests all enhanced ownership analysis functionality with deterministic mock data.
"""

import pytest
import logging
from unittest.mock import Mock, MagicMock, patch
from decimal import Decimal
from typing import Dict, Any, List

import django
from django.test import TestCase
from shared.tests.base import BaseDexTestCase, override_settings
from django.conf import settings

# Import test data
from .test_data.contracts import (
    ContractAddresses, 
    MockContractResponses, 
    TestScenarios,
    RiskScoreValidation
)

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Test settings
TEST_SETTINGS = {
    'DATABASES': {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    },
    'CELERY_TASK_ALWAYS_EAGER': True,
    'CELERY_TASK_EAGER_PROPAGATES': True,
}


class BaseOwnershipTestCase(BaseDexTestCase):
    """Base test case for ownership analysis tests."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_w3 = self._create_mock_web3()
        self.test_contracts = ContractAddresses.get_all_contracts()
        
    def _create_mock_web3(self) -> Mock:
        """Create a properly configured Mock Web3 instance."""
        mock_w3 = Mock()
        mock_w3.is_connected.return_value = True
        mock_w3.keccak.return_value = b'\x01' * 32
        mock_w3.eth = Mock()
        mock_w3.eth.get_code.return_value = b'\x60\x80\x60\x40'  # Valid bytecode
        mock_w3.eth.call.return_value = b'\x00' * 32
        return mock_w3
        
    def _setup_contract_mocks(self, contract_name: str, category: str) -> None:
        """Set up mock responses for a specific contract."""
        if category == 'safe':
            mock_data = MockContractResponses.get_safe_contract_mocks(contract_name)
        elif category == 'risky':
            mock_data = MockContractResponses.get_risky_contract_mocks(contract_name)
        else:
            mock_data = MockContractResponses.get_edge_case_mocks(contract_name)
            
        # Configure mock responses based on test data
        self.mock_w3.eth.get_code.return_value = mock_data['bytecode']
        
        # Mock owner address calls
        if mock_data['owner'] == '0x0000000000000000000000000000000000000000':
            # Renounced ownership
            self.mock_w3.eth.call.return_value = b'\x00' * 32
        else:
            # Active ownership - return padded address
            owner_bytes = bytes.fromhex(mock_data['owner'][2:])
            self.mock_w3.eth.call.return_value = b'\x00' * 12 + owner_bytes
    
    def assertRiskScoreInRange(self, score: Decimal, expected_range: tuple, msg: str = None):
        """Assert that risk score falls within expected range."""
        min_score, max_score = expected_range
        self.assertGreaterEqual(float(score), min_score, msg)
        self.assertLessEqual(float(score), max_score, msg)


@override_settings(**TEST_SETTINGS)
class OwnershipStructureTests(BaseOwnershipTestCase):
    """Test suite for ownership structure analysis."""
    
    def test_analyze_ownership_structure_renounced(self):
        """Test ownership analysis for renounced contracts."""
        from risk.tasks.ownership import _analyze_ownership_structure
        
        # Test WETH (renounced ownership)
        self._setup_contract_mocks('WETH', 'safe')
        contract_data = self.test_contracts['WETH']
        
        result = _analyze_ownership_structure(self.mock_w3, contract_data.address)
        
        # Verify ownership analysis
        self.assertIsInstance(result, dict)
        self.assertIn('has_owner', result)
        self.assertIn('is_renounced', result)
        self.assertIn('ownership_type', result)
        
        # For renounced ownership
        if contract_data.expected_owner_renounced:
            self.assertTrue(result.get('is_renounced', False))
            self.assertEqual(result.get('ownership_type'), 'RENOUNCED')
    
    def test_analyze_ownership_structure_active_owner(self):
        """Test ownership analysis for contracts with active owners."""
        from risk.tasks.ownership import _analyze_ownership_structure
        
        # Test SafeMoon (active owner)
        self._setup_contract_mocks('SAFEMOON', 'risky')
        contract_data = self.test_contracts['SAFEMOON']
        
        result = _analyze_ownership_structure(self.mock_w3, contract_data.address)
        
        # Verify active ownership
        self.assertTrue(result.get('has_owner', False))
        self.assertFalse(result.get('is_renounced', True))
        self.assertIsNotNone(result.get('owner_address'))
        self.assertIn(result.get('ownership_type'), ['OWNED', 'CENTRALIZED_CONTROLLED'])
    
    def test_ownership_function_detection(self):
        """Test detection of ownership functions (owner, admin, etc.)."""
        from risk.tasks.ownership import _analyze_ownership_structure
        
        # Mock different ownership function responses
        test_cases = [
            ('owner()', 'OWNER_FUNCTION'),
            ('admin()', 'ADMIN_FUNCTION'),
            ('getOwner()', 'GET_OWNER_FUNCTION')
        ]
        
        for func_sig, expected_type in test_cases:
            with self.subTest(function=func_sig):
                # Mock successful function call
                self.mock_w3.eth.call.return_value = b'\x00' * 12 + b'\x01' * 20
                
                result = _analyze_ownership_structure(self.mock_w3, self.test_contracts['DAI'].address)
                
                # Should detect ownership function
                self.assertIn('ownership_function', result)
    
    def test_owner_activity_analysis(self):
        """Test analysis of owner activity and transaction history."""
        from risk.tasks.ownership import _analyze_owner_activity
        
        # Mock active owner address
        owner_address = '0x1234567890123456789012345678901234567890'
        
        # Mock transaction count and recent activity
        self.mock_w3.eth.get_transaction_count.return_value = 150
        self.mock_w3.eth.get_block.return_value = {'timestamp': 1693737600}  # Recent timestamp
        
        result = _analyze_owner_activity(self.mock_w3, owner_address)
        
        # Verify activity analysis
        self.assertIsInstance(result, dict)
        self.assertIn('transaction_count', result)
        self.assertIn('last_activity', result)
        self.assertIn('activity_level', result)
    
    def test_control_mechanisms_detection(self):
        """Test detection of control mechanisms."""
        from risk.tasks.ownership import _check_control_mechanisms
        
        # Test contract with control mechanisms
        self._setup_contract_mocks('SAFEMOON', 'risky')
        
        result = _check_control_mechanisms(self.mock_w3, self.test_contracts['SAFEMOON'].address)
        
        # Verify control mechanism detection
        self.assertIsInstance(result, dict)
        self.assertIn('detected_controls', result)
        self.assertIn('has_pause_mechanism', result)
        self.assertIn('has_blacklist_mechanism', result)
        self.assertIn('control_count', result)
        
        # SafeMoon should have multiple control mechanisms
        self.assertGreater(result.get('control_count', 0), 0)


@override_settings(**TEST_SETTINGS)
class AdminFunctionTests(BaseOwnershipTestCase):
    """Test suite for admin function analysis."""
    
    def test_analyze_admin_functions_detection(self):
        """Test detection of admin functions."""
        from risk.tasks.ownership import _analyze_admin_functions
        
        # Test risky contract with many admin functions
        self._setup_contract_mocks('SAFEMOON', 'risky')
        contract_data = self.test_contracts['SAFEMOON']
        
        # Mock admin function detection
        with patch('risk.tasks.ownership._detect_dangerous_functions') as mock_detect:
            mock_detect.return_value = [
                {'signature': 'setTaxFeePercent(uint256)', 'risk_level': 'HIGH'},
                {'signature': 'excludeFromFee(address)', 'risk_level': 'MEDIUM'},
                {'signature': 'pause()', 'risk_level': 'HIGH'},
                {'signature': 'blacklist(address)', 'risk_level': 'HIGH'}
            ]
            
            result = _analyze_admin_functions(self.mock_w3, contract_data.address)
            
            # Verify admin function analysis
            self.assertIsInstance(result, dict)
            self.assertIn('total_dangerous_functions', result)
            self.assertIn('high_risk_functions', result)
            self.assertIn('detected_functions', result)
            
            # Should detect multiple dangerous functions
            self.assertGreater(result.get('total_dangerous_functions', 0), 3)
            self.assertTrue(result.get('has_pause_function', False))
            self.assertTrue(result.get('has_blacklist_function', False))
    
    def test_dangerous_function_categorization(self):
        """Test categorization of dangerous functions by risk level."""
        from risk.tasks.ownership import _detect_dangerous_functions
        
        # Mock function detection responses
        dangerous_functions = [
            'mint(address,uint256)',
            'burn(uint256)',
            'pause()',
            'setFeePercent(uint256)',
            'blacklist(address)',
            'emergencyWithdraw()'
        ]
        
        # Mock successful detection for each function
        with patch.object(self.mock_w3.eth, 'call') as mock_call:
            mock_call.return_value = b'\x00' * 32  # Successful call
            
            result = _detect_dangerous_functions(self.mock_w3, self.test_contracts['SAFEMOON'].address)
            
            # Verify function categorization
            self.assertIsInstance(result, list)
            
            # Check that functions are properly categorized
            for func_data in result:
                self.assertIn('signature', func_data)
                self.assertIn('risk_level', func_data)
                self.assertIn(func_data['risk_level'], ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'])
    
    def test_function_accessibility_analysis(self):
        """Test analysis of function accessibility and access controls."""
        from risk.tasks.ownership import _analyze_function_accessibility
        
        mock_functions = [
            {'signature': 'setTaxFeePercent(uint256)', 'risk_level': 'HIGH'},
            {'signature': 'pause()', 'risk_level': 'HIGH'}
        ]
        
        result = _analyze_function_accessibility(self.mock_w3, self.test_contracts['USDT'].address, mock_functions)
        
        # Verify accessibility analysis
        self.assertIsInstance(result, dict)
        self.assertIn('analysis_method', result)
        
        # Should provide recommendations for manual verification
        self.assertIn('recommendation', result)
    
    def test_admin_function_risk_scoring(self):
        """Test risk scoring based on admin functions."""
        from risk.tasks.ownership import _analyze_admin_functions
        
        # Test different admin function scenarios
        test_scenarios = [
            ('WETH', 0),      # No admin functions - low risk
            ('DAI', 2),       # Limited admin functions - moderate risk  
            ('SAFEMOON', 8),  # Many admin functions - high risk
        ]
        
        for contract_name, expected_function_count in test_scenarios:
            with self.subTest(contract=contract_name):
                contract_data = self.test_contracts[contract_name]
                category = contract_data.category
                
                self._setup_contract_mocks(contract_name, category)
                
                # Mock function detection based on expected count
                with patch('risk.tasks.ownership._detect_dangerous_functions') as mock_detect:
                    mock_functions = [
                        {'signature': f'function_{i}()', 'risk_level': 'HIGH'}
                        for i in range(expected_function_count)
                    ]
                    mock_detect.return_value = mock_functions
                    
                    result = _analyze_admin_functions(self.mock_w3, contract_data.address)
                    
                    # Verify function count
                    actual_count = result.get('total_dangerous_functions', 0)
                    self.assertEqual(actual_count, expected_function_count)


@override_settings(**TEST_SETTINGS)
class TimelockAnalysisTests(BaseOwnershipTestCase):
    """Test suite for timelock mechanism analysis."""
    
    def test_analyze_timelock_mechanisms(self):
        """Test detection and analysis of timelock mechanisms."""
        from risk.tasks.ownership import _analyze_timelock_mechanisms
        
        # Test Compound (has timelock)
        self._setup_contract_mocks('COMPOUND', 'edge_case')
        contract_data = self.test_contracts['COMPOUND']
        
        # Mock timelock detection
        with patch('risk.tasks.ownership._detect_timelock_contract') as mock_detect:
            mock_detect.return_value = '0x6d903f6003cca6255d85cca4d3b5e5146dc33925'
            
            with patch('risk.tasks.ownership._analyze_timelock_contract') as mock_analyze:
                mock_analyze.return_value = {
                    'is_contract': True,
                    'has_bytecode': True,
                    'delay_seconds': 172800,  # 2 days
                    'admin_address': '0x6d903f6003cca6255d85cca4d3b5e5146dc33925'
                }
                
                result = _analyze_timelock_mechanisms(self.mock_w3, contract_data.address)
                
                # Verify timelock analysis
                self.assertIsInstance(result, dict)
                self.assertIn('has_timelock', result)
                self.assertIn('timelock_address', result)
                self.assertIn('timelock_analysis', result)
                
                # Should detect timelock
                self.assertTrue(result.get('has_timelock', False))
                self.assertIsNotNone(result.get('timelock_address'))
    
    def test_timelock_contract_analysis(self):
        """Test detailed analysis of timelock contracts."""
        from risk.tasks.ownership import _analyze_timelock_contract
        
        timelock_address = '0x6d903f6003cca6255d85cca4d3b5e5146dc33925'
        
        # Mock timelock contract bytecode
        self.mock_w3.eth.get_code.return_value = b'\x60\x80\x60\x40\x52'  # Valid contract
        
        result = _analyze_timelock_contract(self.mock_w3, timelock_address)
        
        # Verify timelock contract analysis
        self.assertIsInstance(result, dict)
        self.assertIn('is_contract', result)
        self.assertTrue(result.get('is_contract', False))
        self.assertTrue(result.get('has_bytecode', False))
    
    def test_timelock_detection_methods(self):
        """Test different methods of timelock detection."""
        from risk.tasks.ownership import _detect_timelock_contract
        
        # Test various timelock detection methods
        test_cases = [
            ('admin()', True),       # Proxy admin pattern
            ('timelock()', True),    # Direct timelock function
            ('owner()', False),      # Regular owner (no timelock)
        ]
        
        for function_sig, should_detect in test_cases:
            with self.subTest(function=function_sig):
                if should_detect:
                    # Mock successful timelock detection
                    timelock_bytes = bytes.fromhex('6d903f6003cca6255d85cca4d3b5e5146dc33925')
                    self.mock_w3.eth.call.return_value = b'\x00' * 12 + timelock_bytes
                else:
                    # Mock no timelock
                    self.mock_w3.eth.call.return_value = b'\x00' * 32
                
                result = _detect_timelock_contract(self.mock_w3, self.test_contracts['COMPOUND'].address)
                
                if should_detect:
                    self.assertIsNotNone(result)
                else:
                    self.assertIsNone(result)


@override_settings(**TEST_SETTINGS)
class MultisigAnalysisTests(BaseOwnershipTestCase):
    """Test suite for multisig ownership analysis."""
    
    def test_analyze_multisig_ownership(self):
        """Test detection and analysis of multisig ownership."""
        from risk.tasks.ownership import _analyze_multisig_ownership
        
        # Test multisig contract
        self._setup_contract_mocks('MULTIOWNER', 'edge_case')
        contract_data = self.test_contracts['MULTIOWNER']
        
        # Mock multisig detection
        with patch('risk.tasks.ownership._detect_multisig_pattern') as mock_detect:
            mock_detect.return_value = {
                'is_multisig': True,
                'owner_count': 5,
                'required_confirmations': 3,
                'multisig_type': 'GNOSIS_SAFE'
            }
            
            result = _analyze_multisig_ownership(self.mock_w3, contract_data.address)
            
            # Verify multisig analysis
            self.assertIsInstance(result, dict)
            self.assertIn('is_multisig', result)
            self.assertIn('multisig_details', result)
            
            # Should detect multisig
            self.assertTrue(result.get('is_multisig', False))
            
            details = result.get('multisig_details', {})
            self.assertIn('owner_count', details)
            self.assertIn('required_confirmations', details)
    
    def test_multisig_pattern_detection(self):
        """Test detection of different multisig patterns."""
        from risk.tasks.ownership import _detect_multisig_pattern
        
        # Mock different multisig patterns
        multisig_functions = [
            'getOwners()',
            'getThreshold()', 
            'isOwner(address)',
            'required()'
        ]
        
        # Mock successful multisig function calls
        with patch.object(self.mock_w3.eth, 'call') as mock_call:
            mock_call.return_value = b'\x00' * 32  # Successful call
            
            result = _detect_multisig_pattern(self.mock_w3, self.test_contracts['MULTIOWNER'].address)
            
            # Verify multisig pattern detection
            self.assertIsInstance(result, dict)
            self.assertIn('is_multisig', result)
    
    def test_multisig_security_assessment(self):
        """Test security assessment of multisig configurations."""
        from risk.tasks.ownership import _assess_multisig_security
        
        # Test different multisig configurations
        test_configs = [
            {'owner_count': 5, 'required_confirmations': 3, 'expected_security': 'HIGH'},
            {'owner_count': 3, 'required_confirmations': 2, 'expected_security': 'MEDIUM'},
            {'owner_count': 2, 'required_confirmations': 1, 'expected_security': 'LOW'},
        ]
        
        for config in test_configs:
            with self.subTest(config=config):
                result = _assess_multisig_security(
                    config['owner_count'], 
                    config['required_confirmations']
                )
                
                self.assertIsInstance(result, dict)
                self.assertIn('security_level', result)
                self.assertEqual(result['security_level'], config['expected_security'])


@override_settings(**TEST_SETTINGS)
class UpgradeabilityTests(BaseOwnershipTestCase):
    """Test suite for contract upgradeability analysis."""
    
    def test_analyze_contract_upgradeability(self):
        """Test detection and analysis of contract upgradeability."""
        from risk.tasks.ownership import _analyze_contract_upgradeability
        
        # Test USDT (proxy contract)
        self._setup_contract_mocks('USDT', 'edge_case')
        contract_data = self.test_contracts['USDT']
        
        # Mock proxy detection
        with patch('risk.tasks.ownership._check_proxy_storage_slots') as mock_storage:
            mock_storage.return_value = {
                'has_proxy_slots': True,
                'implementation_slot': '0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc',
                'admin_slot': '0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103'
            }
            
            # Mock implementation address detection
            impl_bytes = bytes.fromhex('5d24c7e42b42d7c75d2f4c2f8b6c8f8c8f8c8f8c')
            self.mock_w3.eth.call.return_value = b'\x00' * 12 + impl_bytes
            
            result = _analyze_contract_upgradeability(self.mock_w3, contract_data.address)
            
            # Verify upgradeability analysis
            self.assertIsInstance(result, dict)
            self.assertIn('is_upgradeable', result)
            self.assertIn('is_proxy', result)
            self.assertIn('implementation_address', result)
            self.assertIn('risk_level', result)
            
            # USDT should be detected as upgradeable
            self.assertTrue(result.get('is_upgradeable', False))
            self.assertTrue(result.get('is_proxy', False))
            self.assertEqual(result.get('risk_level'), 'HIGH')
    
    def test_proxy_storage_slots_check(self):
        """Test checking of EIP-1967 proxy storage slots."""
        from risk.tasks.ownership import _check_proxy_storage_slots
        
        # Mock storage slot responses
        with patch.object(self.mock_w3.eth, 'get_storage_at') as mock_storage:
            # Mock implementation slot response
            mock_storage.return_value = b'\x00' * 12 + b'\x01' * 20  # Non-zero = proxy
            
            result = _check_proxy_storage_slots(self.mock_w3, self.test_contracts['USDT'].address)
            
            # Verify storage slot analysis
            self.assertIsInstance(result, dict)
            self.assertIn('has_proxy_slots', result)
            self.assertTrue(result.get('has_proxy_slots', False))
    
    def test_upgrade_function_detection(self):
        """Test detection of upgrade functions.""" 
        from risk.tasks.ownership import _analyze_contract_upgradeability
        
        # Test different upgrade function patterns
        upgrade_functions = [
            'upgradeTo(address)',
            'upgradeToAndCall(address,bytes)',
            'setImplementation(address)'
        ]
        
        # Mock successful upgrade function detection
        with patch.object(self.mock_w3.eth, 'call') as mock_call:
            mock_call.return_value = b'\x00' * 32  # Successful call
            
            result = _analyze_contract_upgradeability(self.mock_w3, self.test_contracts['USDT'].address)
            
            # Should detect upgrade functions
            upgrade_funcs = result.get('upgrade_functions', [])
            self.assertIsInstance(upgrade_funcs, list)


@override_settings(**TEST_SETTINGS)
class RiskScoringTests(BaseOwnershipTestCase):
    """Test suite for ownership risk scoring calculations."""
    
    def test_calculate_ownership_risk_score(self):
        """Test comprehensive ownership risk score calculation."""
        from risk.tasks.ownership import _calculate_ownership_risk_score
        
        # Test different risk scenarios
        test_scenarios = [
            {
                'name': 'Renounced ownership - low risk',
                'ownership': {'is_renounced': True, 'ownership_type': 'RENOUNCED'},
                'admin_functions': {'total_dangerous_functions': 0},
                'timelock': {'has_timelock': False},
                'multisig': {'is_multisig': False},
                'upgrade': {'is_upgradeable': False},
                'expected_range': (5, 20)
            },
            {
                'name': 'High centralization - high risk',
                'ownership': {'is_renounced': False, 'ownership_type': 'CENTRALIZED_CONTROLLED'},
                'admin_functions': {'total_dangerous_functions': 8, 'has_mint_function': True},
                'timelock': {'has_timelock': False},
                'multisig': {'is_multisig': False},
                'upgrade': {'is_upgradeable': True, 'risk_level': 'HIGH'},
                'expected_range': (75, 95)
            },
            {
                'name': 'Moderate risk with timelock',
                'ownership': {'is_renounced': False, 'ownership_type': 'OWNED'},
                'admin_functions': {'total_dangerous_functions': 3},
                'timelock': {'has_timelock': True, 'timelock_verified': True},
                'multisig': {'is_multisig': False},
                'upgrade': {'is_upgradeable': False},
                'expected_range': (30, 50)
            }
        ]
        
        for scenario in test_scenarios:
            with self.subTest(scenario=scenario['name']):
                score = _calculate_ownership_risk_score(
                    scenario['ownership'],
                    scenario['admin_functions'],
                    scenario['timelock'],
                    scenario['multisig'],
                    scenario['upgrade']
                )
                
                # Verify risk score
                self.assertIsInstance(score, Decimal)
                self.assertRiskScoreInRange(score, scenario['expected_range'])
    
    def test_risk_score_components(self):
        """Test individual risk score components."""
        from risk.tasks.ownership import _calculate_ownership_risk_score
        
        # Base scenario
        base_ownership = {'is_renounced': False, 'ownership_type': 'OWNED'}
        base_admin = {'total_dangerous_functions': 0}
        base_timelock = {'has_timelock': False}
        base_multisig = {'is_multisig': False}
        base_upgrade = {'is_upgradeable': False}
        
        base_score = _calculate_ownership_risk_score(
            base_ownership, base_admin, base_timelock, base_multisig, base_upgrade
        )
        
        # Test admin function impact
        admin_functions = {'total_dangerous_functions': 5, 'has_mint_function': True}
        admin_score = _calculate_ownership_risk_score(
            base_ownership, admin_functions, base_timelock, base_multisig, base_upgrade
        )
        
        self.assertGreater(admin_score, base_score, "Admin functions should increase risk score")
        
        # Test timelock impact (risk reduction)
        timelock_protection = {'has_timelock': True, 'timelock_verified': True}
        timelock_score = _calculate_ownership_risk_score(
            base_ownership, base_admin, timelock_protection, base_multisig, base_upgrade
        )
        
        self.assertLess(timelock_score, base_score, "Timelock should reduce risk score")
        
        # Test upgradeability impact
        upgradeable = {'is_upgradeable': True, 'risk_level': 'HIGH'}
        upgrade_score = _calculate_ownership_risk_score(
            base_ownership, base_admin, base_timelock, base_multisig, upgradeable
        )
        
        self.assertGreater(upgrade_score, base_score, "Upgradeability should increase risk score")
    
    def test_risk_score_bounds(self):
        """Test that risk scores stay within valid bounds (0-100)."""
        from risk.tasks.ownership import _calculate_ownership_risk_score
        
        # Extreme low risk scenario
        minimal_risk = {
            'ownership': {'is_renounced': True, 'ownership_type': 'RENOUNCED'},
            'admin_functions': {'total_dangerous_functions': 0},
            'timelock': {'has_timelock': True, 'timelock_verified': True},
            'multisig': {'is_multisig': True, 'security_level': 'HIGH'},
            'upgrade': {'is_upgradeable': False}
        }
        
        min_score = _calculate_ownership_risk_score(**minimal_risk)
        self.assertGreaterEqual(float(min_score), 0)
        
        # Extreme high risk scenario
        maximal_risk = {
            'ownership': {'is_renounced': False, 'ownership_type': 'CENTRALIZED_CONTROLLED'},
            'admin_functions': {'total_dangerous_functions': 15, 'has_mint_function': True, 'has_pause_function': True},
            'timelock': {'has_timelock': False},
            'multisig': {'is_multisig': False},
            'upgrade': {'is_upgradeable': True, 'risk_level': 'HIGH'}
        }
        
        max_score = _calculate_ownership_risk_score(**maximal_risk)
        self.assertLessEqual(float(max_score), 100)


@override_settings(**TEST_SETTINGS)
class ErrorHandlingTests(BaseOwnershipTestCase):
    """Test suite for ownership analysis error handling."""
    
    def test_web3_connection_errors(self):
        """Test handling of Web3 connection errors."""
        from risk.tasks.ownership import _analyze_ownership_structure
        
        # Mock connection error
        self.mock_w3.is_connected.return_value = False
        
        result = _analyze_ownership_structure(self.mock_w3, self.test_contracts['WETH'].address)
        
        # Should handle connection error gracefully
        self.assertIsInstance(result, dict)
        self.assertIn('error', result)
    
    def test_invalid_contract_address(self):
        """Test handling of invalid contract addresses."""
        from risk.tasks.ownership import _analyze_ownership_structure
        
        # Mock no bytecode (invalid contract)
        self.mock_w3.eth.get_code.return_value = b''
        
        result = _analyze_ownership_structure(self.mock_w3, '0x0000000000000000000000000000000000000000')
        
        # Should handle invalid contract gracefully
        self.assertIsInstance(result, dict)
        self.assertIn('error', result)
    
    def test_rpc_call_failures(self):
        """Test handling of failed RPC calls."""
        from risk.tasks.ownership import _analyze_admin_functions
        
        # Mock RPC call failure
        from web3.exceptions import BadFunctionCallOutput
        self.mock_w3.eth.call.side_effect = BadFunctionCallOutput("Function call failed")
        
        result = _analyze_admin_functions(self.mock_w3, self.test_contracts['DAI'].address)
        
        # Should handle RPC failures gracefully
        self.assertIsInstance(result, dict)
        # Should still return some result, even if limited
        self.assertIn('total_dangerous_functions', result)
    
    def test_timeout_handling(self):
        """Test handling of request timeouts."""
        from risk.tasks.ownership import _analyze_timelock_mechanisms
        
        # Mock timeout error
        import requests
        self.mock_w3.eth.call.side_effect = requests.exceptions.Timeout("Request timed out")
        
        result = _analyze_timelock_mechanisms(self.mock_w3, self.test_contracts['COMPOUND'].address)
        
        # Should handle timeout gracefully
        self.assertIsInstance(result, dict)
        self.assertIn('has_timelock', result)


@override_settings(**TEST_SETTINGS)
class IntegrationHelperTests(BaseOwnershipTestCase):
    """Test suite for integration helper functions."""
    
    def test_classification_logic(self):
        """Test ownership type classification logic."""
        from risk.tasks.ownership import _classify_ownership_type
        
        # Test different classification scenarios
        test_cases = [
            ('0x0000000000000000000000000000000000000000', True, {}, 'RENOUNCED'),
            ('', False, {}, 'NO_OWNER'),
            ('0x1234567890123456789012345678901234567890', False, {'control_count': 5}, 'CENTRALIZED_CONTROLLED'),
            ('0x1234567890123456789012345678901234567890', False, {'control_count': 1}, 'OWNED'),
        ]
        
        for owner_address, is_renounced, control_mechanisms, expected_type in test_cases:
            with self.subTest(owner=owner_address, renounced=is_renounced):
                result = _classify_ownership_type(owner_address, is_renounced, control_mechanisms)
                self.assertEqual(result, expected_type)
    
    def test_web3_connection_helper(self):
        """Test Web3 connection helper function."""
        from risk.tasks.ownership import _get_web3_connection
        
        # Test Web3 connection creation
        with patch('risk.tasks.ownership.Web3') as mock_web3_class:
            mock_instance = Mock()
            mock_instance.is_connected.return_value = True
            mock_web3_class.return_value = mock_instance
            
            w3 = _get_web3_connection()
            
            # Should return connected Web3 instance
            self.assertIsNotNone(w3)
            mock_web3_class.assert_called()


if __name__ == '__main__':
    # Run tests with pytest for better output
    pytest.main([__file__, '-v', '--tb=short'])