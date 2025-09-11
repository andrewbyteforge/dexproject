"""
Simple Risk Assessment Test Setup

Simplified test configuration to get started quickly.
"""

import os
import sys
from unittest.mock import MagicMock, patch
from decimal import Decimal
from typing import Dict, Any

# Mock Web3 before any imports
sys.modules['web3'] = MagicMock()
sys.modules['web3.Web3'] = MagicMock()
sys.modules['web3.exceptions'] = MagicMock()
sys.modules['eth_account'] = MagicMock()
sys.modules['eth_utils'] = MagicMock()

# Create basic mocks
class MockWeb3:
    def __init__(self):
        self.eth = MockEth()
        self._connected = True
    
    def is_connected(self):
        return self._connected
    
    def keccak(self, text: str):
        return b'\x01' * 32
    
    @staticmethod
    def is_address(address: str) -> bool:
        return (isinstance(address, str) and 
                len(address) == 42 and 
                address.startswith('0x') and
                all(c in '0123456789abcdefABCDEF' for c in address[2:]))

class MockEth:
    def __init__(self):
        self.block_number = 18500000
        self.gas_price = 20 * 10**9
    
    def get_code(self, address: str):
        return b'\x60\x80\x60\x40' if 'contract' in address.lower() else b''
    
    def call(self, transaction_data):
        return b'\x00' * 32

# Test data factory
class TestDataFactory:
    @staticmethod
    def create_token_address(token_type: str = 'normal') -> str:
        addresses = {
            'normal': '0x1234567890123456789012345678901234567890',
            'honeypot': '0x1234567890123456789012345678901234567891',  # Fixed: exactly 42 chars
            'good': '0x1234567890123456789012345678901234567892',      # Fixed: exactly 42 chars
        }
        return addresses.get(token_type, addresses['normal'])
    
    @staticmethod
    def create_pair_address(pair_type: str = 'normal') -> str:
        return '0xabcdefabcdefabcdefabcdefabcdefabcdefabcd'
    
    @staticmethod
    def create_risk_check_result(
        check_type: str,
        status: str = 'COMPLETED',
        risk_score: float = 25.0,
        details: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        if details is None:
            details = {}
        
        return {
            'check_type': check_type,
            'token_address': TestDataFactory.create_token_address(),
            'pair_address': TestDataFactory.create_pair_address(),
            'status': status,
            'risk_score': risk_score,
            'details': details,
            'execution_time_ms': 150.0,
            'timestamp': '2025-09-11T12:00:00Z'
        }

# Export the classes so they can be imported
__all__ = ['MockWeb3', 'MockEth', 'TestDataFactory']