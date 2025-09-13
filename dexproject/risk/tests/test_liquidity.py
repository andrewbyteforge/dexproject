"""
Liquidity Analysis Tests

File: dexproject/risk/tests/test_liquidity.py

Comprehensive unit tests for liquidity analysis functionality.
"""

import unittest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from django.test import TestCase
from shared.tests.base import BaseDexTestCase, override_settings

from risk.tasks.liquidity import liquidity_check
from risk.tests import BaseRiskTestCase, TestDataFactory, TEST_SETTINGS


@override_settings(**TEST_SETTINGS)
class LiquidityAnalysisTests(BaseRiskTestCase):
    """Test suite for liquidity analysis."""
    
    def test_sufficient_liquidity_passes_check(self):
        """Test that sufficient liquidity passes the check."""
        pair_address = TestDataFactory.create_pair_address('highliq')
        token_address = TestDataFactory.create_token_address('normal')
        
        # Mock high liquidity scenario
        with patch('risk.tasks.liquidity._analyze_liquidity_depth') as mock_depth:
            mock_depth.return_value = {
                'total_liquidity_usd': 100000,
                'token0_liquidity_usd': 50000,
                'token1_liquidity_usd': 50000,
                'liquidity_metrics': {'imbalance': 0.1}
            }
            
            with patch('risk.tasks.liquidity._calculate_slippage_impact') as mock_slippage:
                mock_slippage.return_value = {
                    'max_slippage': 2.5,
                    'slippage_data': [],
                    'liquidity_efficiency': 85
                }
                
                result = liquidity_check(pair_address, token_address, min_liquidity_usd=50000)
        
        # Assertions
        self.assertCheckStatus(result, 'COMPLETED')
        self.assertRiskScore(result, 0, 30)
        
        details = result.get('details', {})
        self.assertTrue(details.get('meets_minimum', False))
        self.assertTrue(details.get('slippage_acceptable', False))
    
    def test_insufficient_liquidity_fails_check(self):
        """Test that insufficient liquidity fails the check."""
        pair_address = TestDataFactory.create_pair_address('lowliq')
        token_address = TestDataFactory.create_token_address('normal')
        
        # Mock low liquidity scenario
        with patch('risk.tasks.liquidity._analyze_liquidity_depth') as mock_depth:
            mock_depth.return_value = {
                'total_liquidity_usd': 5000,  # Below minimum
                'token0_liquidity_usd': 2500,
                'token1_liquidity_usd': 2500,
                'liquidity_metrics': {'imbalance': 0.1}
            }
            
            with patch('risk.tasks.liquidity._calculate_slippage_impact') as mock_slippage:
                mock_slippage.return_value = {
                    'max_slippage': 15.0,  # High slippage
                    'slippage_data': [],
                    'liquidity_efficiency': 30
                }
                
                result = liquidity_check(pair_address, token_address, min_liquidity_usd=10000)
        
        # Assertions
        self.assertCheckStatus(result, 'FAILED')
        self.assertRiskScore(result, 70, 100)
        
        details = result.get('details', {})
        self.assertFalse(details.get('meets_minimum', True))
        self.assertFalse(details.get('slippage_acceptable', True))
    
    def test_high_slippage_increases_risk(self):
        """Test that high slippage increases risk score."""
        pair_address = TestDataFactory.create_pair_address('normal')
        token_address = TestDataFactory.create_token_address('normal')
        
        # Mock high slippage scenario
        with patch('risk.tasks.liquidity._calculate_slippage_impact') as mock_slippage:
            mock_slippage.return_value = {
                'max_slippage': 12.0,  # High slippage
                'slippage_data': [
                    {'trade_size_usd': 1000, 'max_slippage_percent': 8.0},
                    {'trade_size_usd': 5000, 'max_slippage_percent': 12.0}
                ],
                'liquidity_efficiency': 40
            }
            
            result = liquidity_check(pair_address, token_address, max_slippage_percent=5.0)
        
        # Should have elevated risk due to high slippage
        self.assertRiskScore(result, 40, 80)
        
        details = result.get('details', {})
        self.assertFalse(details.get('slippage_acceptable', True))
    
    def test_lp_token_analysis(self):
        """Test LP token lock and burn analysis."""
        pair_address = TestDataFactory.create_pair_address('normal')
        token_address = TestDataFactory.create_token_address('normal')
        
        # Mock LP analysis with good security
        with patch('risk.tasks.liquidity._analyze_lp_tokens') as mock_lp:
            mock_lp.return_value = {
                'total_supply': 1000000,
                'burned_amount': 800000,  # 80% burned
                'locked_amount': 150000,  # 15% locked
                'burn_percentage': 80.0,
                'lock_percentage': 15.0,
                'is_majority_locked_burned': True,
                'security_score': 95
            }
            
            result = liquidity_check(pair_address, token_address)
        
        details = result.get('details', {})
        lp_analysis = details.get('lp_analysis', {})
        
        self.assertTrue(lp_analysis.get('is_majority_locked_burned', False))
        self.assertGreater(lp_analysis.get('security_score', 0), 90)
    
    def test_liquidity_quality_metrics(self):
        """Test liquidity quality metrics calculation."""
        pair_address = TestDataFactory.create_pair_address('normal')
        token_address = TestDataFactory.create_token_address('normal')
        
        result = liquidity_check(pair_address, token_address)
        
        details = result.get('details', {})
        quality_metrics = details.get('quality_metrics', {})
        
        # Should have quality metrics
        self.assertIn('depth_quality', quality_metrics)
        self.assertIn('slippage_quality', quality_metrics)
        self.assertIn('overall_quality', quality_metrics)
        
        # Values should be between 0 and 100
        for metric, value in quality_metrics.items():
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 100)
    
    def test_invalid_pair_address_handling(self):
        """Test handling of invalid pair addresses."""
        invalid_pair = 'invalid_address'
        token_address = TestDataFactory.create_token_address('normal')
        
        result = liquidity_check(invalid_pair, token_address)
        
        # Should fail gracefully
        self.assertCheckStatus(result, 'FAILED')
        self.assertEqual(result.get('risk_score'), 100)
        self.assertIsNotNone(result.get('error_message'))
    
    def test_price_impact_calculation(self):
        """Test price impact calculation for various trade sizes."""
        from risk.tasks.liquidity import _calculate_slippage_impact
        
        mock_w3 = MagicMock()
        pair_address = TestDataFactory.create_pair_address('normal')
        
        # Mock pair info
        pair_info = {
            'reserves': {
                'reserve0': 1000 * 10**18,
                'reserve1': 2500000 * 10**6
            },
            'token0': {'decimals': 18},
            'token1': {'decimals': 6}
        }
        
        test_sizes = [100, 1000, 5000, 10000]
        
        result = _calculate_slippage_impact(mock_w3, pair_address, pair_info, test_sizes)
        
        # Should have slippage data for each test size
        slippage_data = result.get('slippage_data', [])
        self.assertEqual(len(slippage_data), len(test_sizes))
        
        # Slippage should generally increase with trade size
        slippages = [item['max_slippage_percent'] for item in slippage_data]
        self.assertLessEqual(slippages[0], slippages[-1])
    
    def test_liquidity_warnings_generation(self):
        """Test generation of liquidity warnings."""
        pair_address = TestDataFactory.create_pair_address('lowliq')
        token_address = TestDataFactory.create_token_address('normal')
        
        # Mock problematic liquidity scenario
        with patch('risk.tasks.liquidity._analyze_liquidity_depth') as mock_depth:
            mock_depth.return_value = {
                'total_liquidity_usd': 8000,  # Low
                'liquidity_metrics': {'imbalance': 0.9}  # High imbalance
            }
            
            with patch('risk.tasks.liquidity._calculate_slippage_impact') as mock_slippage:
                mock_slippage.return_value = {'max_slippage': 15.0}  # High slippage
                
                result = liquidity_check(pair_address, token_address)
        
        details = result.get('details', {})
        warnings = details.get('warnings', [])
        
        # Should have multiple warnings
        self.assertGreater(len(warnings), 0)
        
        # Check for specific warning types
        warning_text = ' '.join(warnings).lower()
        self.assertTrue(any(keyword in warning_text for keyword in ['low', 'high', 'slippage', 'liquidity']))


@override_settings(**TEST_SETTINGS)
class LiquidityDepthAnalysisTests(BaseRiskTestCase):
    """Test suite for liquidity depth analysis."""
    
    def test_pair_information_retrieval(self):
        """Test retrieval of pair information."""
        from risk.tasks.liquidity import _get_pair_information
        
        mock_w3 = MagicMock()
        pair_address = TestDataFactory.create_pair_address('normal')
        
        # Mock successful pair info retrieval
        with patch('risk.tasks.liquidity._get_token_info') as mock_token:
            mock_token.return_value = {
                'symbol': 'TEST',
                'decimals': 18,
                'name': 'Test Token'
            }
            
            result = _get_pair_information(mock_w3, pair_address)
        
        # Should return pair information
        self.assertIsNotNone(result)
        self.assertIn('pair_address', result)
        self.assertIn('token0', result)
        self.assertIn('token1', result)
        self.assertIn('reserves', result)
    
    def test_token_price_usd_calculation(self):
        """Test USD price calculation for tokens."""
        from risk.tasks.liquidity import _get_token_price_usd
        
        mock_w3 = MagicMock()
        
        # Test known token prices
        weth_price = _get_token_price_usd(mock_w3, '0xa0b86a33e6441eab62d8b8bb7e5c9d47b6b0bfb4')
        self.assertGreater(weth_price, 1000)  # ETH should be > $1000
        
        usdc_address = TestDataFactory.create_token_address('normal').replace('1234', 'usdc')
        usdc_price = _get_token_price_usd(mock_w3, usdc_address)
        self.assertAlmostEqual(usdc_price, 1.0, places=1)  # USDC should be ~$1
    
    def test_liquidity_depth_score_calculation(self):
        """Test liquidity depth score calculation."""
        from risk.tasks.liquidity import _calculate_depth_score
        
        # Test various liquidity levels
        test_cases = [
            (1000000, 100),   # Very high liquidity
            (100000, 80),     # High liquidity
            (10000, 60),      # Medium liquidity
            (5000, 30),       # Low liquidity
            (1000, 6)         # Very low liquidity
        ]
        
        for liquidity_usd, expected_min_score in test_cases:
            score = _calculate_depth_score(liquidity_usd)
            self.assertGreaterEqual(score, expected_min_score - 10)
            self.assertLessEqual(score, 100)
    
    def test_slippage_curve_analysis(self):
        """Test slippage curve analysis."""
        from risk.tasks.liquidity import _analyze_slippage_curve
        
        # Test linear slippage curve
        linear_data = [
            {'trade_size_usd': 1000, 'max_slippage_percent': 2.0},
            {'trade_size_usd': 5000, 'max_slippage_percent': 4.0},
            {'trade_size_usd': 10000, 'max_slippage_percent': 6.0}
        ]
        
        result = _analyze_slippage_curve(linear_data)
        self.assertIn('curve_type', result)
        self.assertIn('steepness', result)
        
        # Test exponential slippage curve
        exponential_data = [
            {'trade_size_usd': 1000, 'max_slippage_percent': 1.0},
            {'trade_size_usd': 5000, 'max_slippage_percent': 8.0},
            {'trade_size_usd': 10000, 'max_slippage_percent': 25.0}
        ]
        
        result = _analyze_slippage_curve(exponential_data)
        self.assertEqual(result.get('curve_type'), 'exponential')


@override_settings(**TEST_SETTINGS)
class LPTokenAnalysisTests(BaseRiskTestCase):
    """Test suite for LP token analysis."""
    
    def test_lp_security_score_calculation(self):
        """Test LP security score calculation."""
        from risk.tasks.liquidity import _calculate_lp_security_score
        
        # Test high security (95% burned/locked)
        high_security_score = _calculate_lp_security_score(80.0, 15.0)
        self.assertGreaterEqual(high_security_score, 90)
        
        # Test medium security (50% burned/locked)
        medium_security_score = _calculate_lp_security_score(30.0, 20.0)
        self.assertGreaterEqual(medium_security_score, 50)
        self.assertLess(medium_security_score, 80)
        
        # Test low security (20% burned/locked)
        low_security_score = _calculate_lp_security_score(10.0, 10.0)
        self.assertLess(low_security_score, 50)
    
    def test_lp_lock_detection(self):
        """Test LP lock detection functionality."""
        from risk.tasks.liquidity import _check_lp_locks
        
        mock_w3 = MagicMock()
        pair_address = TestDataFactory.create_pair_address('normal')
        total_supply = 1000000 * 10**18
        
        # Currently returns 0 (placeholder implementation)
        locked_amount = _check_lp_locks(mock_w3, pair_address, total_supply)
        self.assertIsInstance(locked_amount, int)
        self.assertGreaterEqual(locked_amount, 0)
    
    def test_liquidity_efficiency_calculation(self):
        """Test liquidity efficiency calculation."""
        from risk.tasks.liquidity import _calculate_liquidity_efficiency
        
        # Test efficient liquidity (low slippage)
        efficient_data = [
            {'max_slippage_percent': 1.0},
            {'max_slippage_percent': 2.0},
            {'max_slippage_percent': 3.0}
        ]
        
        efficiency = _calculate_liquidity_efficiency(efficient_data)
        self.assertGreater(efficiency, 70)
        
        # Test inefficient liquidity (high slippage)
        inefficient_data = [
            {'max_slippage_percent': 10.0},
            {'max_slippage_percent': 15.0},
            {'max_slippage_percent': 20.0}
        ]
        
        efficiency = _calculate_liquidity_efficiency(inefficient_data)
        self.assertLess(efficiency, 50)


@override_settings(**TEST_SETTINGS)
class LiquidityRiskScoringTests(BaseRiskTestCase):
    """Test suite for liquidity risk scoring."""
    
    def test_risk_score_calculation_comprehensive(self):
        """Test comprehensive risk score calculation."""
        from risk.tasks.liquidity import _calculate_liquidity_risk_score
        
        # Test low risk scenario
        low_risk_liquidity = {
            'total_liquidity_usd': 100000,
            'liquidity_metrics': {'imbalance': 0.1}
        }
        low_risk_slippage = {'max_slippage': 2.0}
        low_risk_lp = {'security_score': 95}
        
        score = _calculate_liquidity_risk_score(
            low_risk_liquidity, low_risk_slippage, low_risk_lp, 50000, 5.0
        )
        self.assertLess(score, Decimal('30'))
        
        # Test high risk scenario
        high_risk_liquidity = {
            'total_liquidity_usd': 5000,
            'liquidity_metrics': {'imbalance': 0.8}
        }
        high_risk_slippage = {'max_slippage': 15.0}
        high_risk_lp = {'security_score': 20}
        
        score = _calculate_liquidity_risk_score(
            high_risk_liquidity, high_risk_slippage, high_risk_lp, 50000, 5.0
        )
        self.assertGreater(score, Decimal('60'))
    
    def test_buy_sell_slippage_calculation(self):
        """Test buy and sell slippage calculations."""
        from risk.tasks.liquidity import _calculate_buy_slippage, _calculate_sell_slippage
        
        # Mock reserves
        reserve0 = 1000 * 10**18  # 1000 tokens
        reserve1 = 2500000 * 10**6  # 2.5M USDC
        trade_size = 10000  # $10k trade
        pair_info = {}
        
        buy_slippage = _calculate_buy_slippage(reserve0, reserve1, trade_size, pair_info)
        sell_slippage = _calculate_sell_slippage(reserve0, reserve1, trade_size, pair_info)
        
        # Both should be reasonable percentages
        self.assertGreaterEqual(buy_slippage, 0)
        self.assertLessEqual(buy_slippage, 50)
        self.assertGreaterEqual(sell_slippage, 0)
        self.assertLessEqual(sell_slippage, 50)


if __name__ == '__main__':
    unittest.main()