"""
Simple Contract Test Data

File: risk/tests/test_data/contracts.py

Basic contract test data for ownership analysis testing.
"""

from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class ContractTestData:
    """Container for contract test data."""
    
    address: str
    name: str
    category: str
    expected_owner_renounced: bool
    expected_admin_functions: int
    expected_risk_score_range: tuple
    expected_flags: List[str]
    description: str
    network: str = "ethereum"


class ContractAddresses:
    """Well-known contract addresses for testing."""
    
    SAFE_CONTRACTS = {
        'WETH': ContractTestData(
            address='0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
            name='Wrapped Ether',
            category='safe',
            expected_owner_renounced=True,
            expected_admin_functions=0,
            expected_risk_score_range=(5, 15),
            expected_flags=['owner_renounced'],
            description='Wrapped Ether - simple wrapper contract',
            network='ethereum'
        ),
        'USDC': ContractTestData(
            address='0xA0b86a33E6441E2BF3B7E5D95CCcd6D8DD6b8F73',
            name='USD Coin',
            category='safe',
            expected_owner_renounced=False,
            expected_admin_functions=5,
            expected_risk_score_range=(40, 70),
            expected_flags=['has_admin_functions'],
            description='USD Coin - centralized stablecoin',
            network='ethereum'
        )
    }
    
    @classmethod
    def get_all_contracts(cls) -> Dict[str, ContractTestData]:
        """Get all test contracts."""
        return cls.SAFE_CONTRACTS
    
    @classmethod
    def get_safe_contracts(cls) -> Dict[str, ContractTestData]:
        """Get safe contracts for testing."""
        return cls.SAFE_CONTRACTS