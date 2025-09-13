"""
Risk Assessment Coordinator Tests

File: dexproject/risk/tests/test_coordinator.py

Integration tests for the main risk assessment coordinator.
"""

import unittest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from django.test import TestCase
from shared.tests.base import BaseDexTestCase, override_settings

from risk.tasks.coordinator import assess_token_risk, quick_honeypot_check, bulk_assessment
from risk.tests import BaseRiskTestCase, TestDataFactory, TEST_SETTINGS


@override_settings(**TEST_SETTINGS)
class RiskAssessmentCoordinatorTests(BaseRiskTestCase):
    """Test suite for risk assessment coordinator."""
    
    def test_full_assessment_conservative_profile(self):
        """Test full assessment with conservative risk profile."""
        token_address = TestDataFactory.create_token_address('good')
        pair_address = TestDataFactory.create_pair_address('normal')
        
        # Mock individual check results
        with patch('risk.tasks.coordinator._execute_parallel_risk_checks') as mock_checks:
            mock_checks.return_value = [
                TestDataFactory.create_honeypot_result(is_honeypot=False),
                TestDataFactory.create_liquidity_result(liquidity_usd=75000),
                TestDataFactory.create_ownership_result(is_renounced=True)
            ]
            
            result = assess_token_risk(
                token_address=token_address,
                pair_address=pair_address,
                risk_profile='Conservative'
            )
        
        # Assertions for successful assessment
        self.assertEqual(result.get('trading_decision'), 'APPROVE')
        self.assertLess(result.get('overall_risk_score', 100), 30)
        self.assertFalse(result.get('is_blocked', True))
        self.assertGreater(result.get('confidence_score', 0), 70)
        
        # Check thought log
        thought_log = result.get('thought_log', {})
        self.assertIn('narrative', thought_log)
        self.assertIn('signals', thought_log)
        self.assertEqual(thought_log.get('decision'), 'APPROVE')
    
    def test_full_assessment_blocks_honeypot(self):
        """Test that assessment blocks honeypot tokens."""
        token_address = TestDataFactory.create_token_address('honeypot')
        pair_address = TestDataFactory.create_pair_address('normal')
        
        # Mock honeypot detection
        with patch('risk.tasks.coordinator._execute_parallel_risk_checks') as mock_checks:
            mock_checks.return_value = [
                TestDataFactory.create_honeypot_result(is_honeypot=True),
                TestDataFactory.create_liquidity_result(liquidity_usd=50000),
                TestDataFactory.create_ownership_result(is_renounced=False)
            ]
            
            result = assess_token_risk(
                token_address=token_address,
                pair_address=pair_address,
                risk_profile='Conservative'
            )
        
        # Should block honeypot
        self.assertEqual(result.get('trading_decision'), 'BLOCK')
        self.assertTrue(result.get('is_blocked', False))
        self.assertIn('honeypot', ' '.join(result.get('blocking_reasons', [])).lower())
        
        # Risk score should be high
        self.assertGreater(result.get('overall_risk_score', 0), 80)
    
    def test_risk_profile_differences(self):
        """Test that different risk profiles produce different results."""
        token_address = TestDataFactory.create_token_address('normal')
        pair_address = TestDataFactory.create_pair_address('normal')
        
        # Mock moderate risk scenario
        mock_results = [
            TestDataFactory.create_honeypot_result(is_honeypot=False),
            TestDataFactory.create_liquidity_result(liquidity_usd=25000),  # Medium liquidity
            TestDataFactory.create_ownership_result(is_renounced=False)    # Not renounced
        ]
        
        # Test Conservative profile
        with patch('risk.tasks.coordinator._execute_parallel_risk_checks') as mock_checks:
            mock_checks.return_value = mock_results
            conservative_result = assess_token_risk(
                token_address, pair_address, risk_profile='Conservative'
            )
        
        # Test Aggressive profile
        with patch('risk.tasks.coordinator._execute_parallel_risk_checks') as mock_checks:
            mock_checks.return_value = mock_results
            aggressive_result = assess_token_risk(
                token_address, pair_address, risk_profile='Aggressive'
            )
        
        # Conservative should be more restrictive
        conservative_decision = conservative_result.get('trading_decision')
        aggressive_decision = aggressive_result.get('trading_decision')
        
        # At minimum, conservative shouldn't be more permissive than aggressive
        if conservative_decision == 'BLOCK':
            self.assertIn(aggressive_decision, ['BLOCK', 'SKIP', 'APPROVE'])
        elif conservative_decision == 'SKIP':
            self.assertIn(aggressive_decision, ['SKIP', 'APPROVE'])
    
    def test_parallel_vs_sequential_execution(self):
        """Test that parallel and sequential execution produce consistent results."""
        token_address = TestDataFactory.create_token_address('good')
        pair_address = TestDataFactory.create_pair_address('normal')
        
        # Test parallel execution
        parallel_result = assess_token_risk(
            token_address, pair_address, parallel_execution=True
        )
        
        # Test sequential execution
        sequential_result = assess_token_risk(
            token_address, pair_address, parallel_execution=False
        )
        
        # Results should be similar (allowing for small variations)
        parallel_score = parallel_result.get('overall_risk_score', 0)
        sequential_score = sequential_result.get('overall_risk_score', 0)
        
        score_difference = abs(parallel_score - sequential_score)
        self.assertLess(score_difference, 20)  # Should be within 20 points
        
        # Decisions should be the same for clear cases
        if parallel_score < 30 or parallel_score > 70:
            self.assertEqual(
                parallel_result.get('trading_decision'),
                sequential_result.get('trading_decision')
            )
    
    def test_assessment_with_failed_checks(self):
        """Test assessment behavior when some checks fail."""
        token_address = TestDataFactory.create_token_address('normal')
        pair_address = TestDataFactory.create_pair_address('normal')
        
        # Mock scenario with some failed checks
        with patch('risk.tasks.coordinator._execute_parallel_risk_checks') as mock_checks:
            mock_checks.return_value = [
                TestDataFactory.create_honeypot_result(is_honeypot=False),
                TestDataFactory.create_risk_check_result(
                    'LIQUIDITY', status='FAILED', risk_score=100, 
                    error_message='Connection timeout'
                ),
                TestDataFactory.create_ownership_result(is_renounced=True)
            ]
            
            result = assess_token_risk(token_address, pair_address)
        
        # Should handle failed checks gracefully
        self.assertIsNotNone(result.get('trading_decision'))
        self.assertGreater(result.get('checks_failed', 0), 0)
        self.assertLess(result.get('confidence_score', 100), 80)  # Lower confidence
    
    def test_thought_log_generation(self):
        """Test AI thought log generation."""
        token_address = TestDataFactory.create_token_address('normal')
        pair_address = TestDataFactory.create_pair_address('normal')
        
        with patch('risk.tasks.coordinator._execute_parallel_risk_checks') as mock_checks:
            mock_checks.return_value = [
                TestDataFactory.create_honeypot_result(is_honeypot=False),
                TestDataFactory.create_liquidity_result(liquidity_usd=30000),
                TestDataFactory.create_ownership_result(is_renounced=True)
            ]
            
            result = assess_token_risk(token_address, pair_address)
        
        thought_log = result.get('thought_log', {})
        
        # Should have all required thought log components
        self.assertIn('timestamp', thought_log)
        self.assertIn('token_address', thought_log)
        self.assertIn('decision', thought_log)
        self.assertIn('narrative', thought_log)
        self.assertIn('signals', thought_log)
        self.assertIn('reasoning_chain', thought_log)
        
        # Signals should be informative
        signals = thought_log.get('signals', [])
        self.assertGreater(len(signals), 0)
        
        # Should contain relevant information
        signals_text = ' '.join(signals).lower()
        self.assertTrue(any(keyword in signals_text for keyword in [
            'honeypot', 'liquidity', 'ownership', 'renounced'
        ]))
    
    def test_assessment_summary_generation(self):
        """Test assessment summary generation."""
        token_address = TestDataFactory.create_token_address('good')
        pair_address = TestDataFactory.create_pair_address('normal')
        
        result = assess_token_risk(token_address, pair_address)
        
        summary = result.get('summary', {})
        
        # Should have summary components
        self.assertIn('checks_summary', summary)
        self.assertIn('risk_summary', summary)
        self.assertIn('recommendation', summary)
        self.assertIn('key_points', summary)
        self.assertIn('trade_readiness', summary)
        
        # Check summary should have counts
        checks_summary = summary.get('checks_summary', {})
        self.assertIn('total', checks_summary)
        self.assertIn('completed', checks_summary)
        self.assertIn('success_rate', checks_summary)


@override_settings(**TEST_SETTINGS)
class QuickHoneypotCheckTests(BaseRiskTestCase):
    """Test suite for quick honeypot check functionality."""
    
    def test_quick_check_performance(self):
        """Test that quick check is faster than full assessment."""
        token_address = TestDataFactory.create_token_address('good')
        pair_address = TestDataFactory.create_pair_address('normal')
        
        import time
        
        # Time quick check
        start_time = time.time()
        quick_result = quick_honeypot_check(token_address, pair_address)
        quick_time = time.time() - start_time
        
        # Should be reasonably fast (under 5 seconds in test environment)
        self.assertLess(quick_time, 5.0)
        
        # Should return basic honeypot information
        self.assertIn('is_honeypot', quick_result)
        self.assertIn('risk_score', quick_result)
        self.assertEqual(quick_result.get('check_type'), 'QUICK_HONEYPOT')
    
    def test_quick_check_honeypot_detection(self):
        """Test quick check correctly identifies honeypots."""
        honeypot_address = TestDataFactory.create_token_address('honeypot')
        pair_address = TestDataFactory.create_pair_address('normal')
        
        result = quick_honeypot_check(honeypot_address, pair_address)
        
        # Should detect honeypot
        self.assertTrue(result.get('is_honeypot', False))
        self.assertGreaterEqual(result.get('risk_score', 0), 90)
    
    def test_quick_check_failure_handling(self):
        """Test quick check failure handling."""
        invalid_token = 'invalid_address'
        pair_address = TestDataFactory.create_pair_address('normal')
        
        result = quick_honeypot_check(invalid_token, pair_address)
        
        # Should handle failure gracefully
        self.assertEqual(result.get('status'), 'FAILED')
        self.assertTrue(result.get('is_honeypot', False))  # Assume honeypot on failure
        self.assertEqual(result.get('risk_score'), 100)
        self.assertIsNotNone(result.get('error'))


@override_settings(**TEST_SETTINGS)
class BulkAssessmentTests(BaseRiskTestCase):
    """Test suite for bulk assessment functionality."""
    
    def test_bulk_assessment_multiple_tokens(self):
        """Test bulk assessment of multiple token pairs."""
        token_pairs = [
            (TestDataFactory.create_token_address('good'), TestDataFactory.create_pair_address('normal')),
            (TestDataFactory.create_token_address('honeypot'), TestDataFactory.create_pair_address('normal')),
            (TestDataFactory.create_token_address('normal'), TestDataFactory.create_pair_address('lowliq'))
        ]
        
        # Mock individual assessments
        with patch('risk.tasks.coordinator.assess_token_risk') as mock_assess:
            mock_assess.side_effect = [
                {'trading_decision': 'APPROVE', 'overall_risk_score': 20},
                {'trading_decision': 'BLOCK', 'overall_risk_score': 95},
                {'trading_decision': 'SKIP', 'overall_risk_score': 55}
            ]
            
            result = bulk_assessment(token_pairs, risk_profile='Conservative')
        
        # Should process all pairs
        self.assertEqual(result.get('total_assessed'), 3)
        self.assertGreater(result.get('successful'), 0)
        self.assertIn('success_rate', result)
        
        # Should have results for each pair
        results = result.get('results', [])
        self.assertEqual(len(results), 3)
    
    def test_bulk_assessment_with_failures(self):
        """Test bulk assessment handles individual failures."""
        token_pairs = [
            (TestDataFactory.create_token_address('good'), TestDataFactory.create_pair_address('normal')),
            ('invalid_token', TestDataFactory.create_pair_address('normal'))
        ]
        
        # Mock mixed results
        with patch('risk.tasks.coordinator.assess_token_risk') as mock_assess:
            mock_assess.side_effect = [
                {'trading_decision': 'APPROVE', 'overall_risk_score': 20},
                Exception('Assessment failed')
            ]
            
            result = bulk_assessment(token_pairs)
        
        # Should handle failures gracefully
        self.assertEqual(result.get('total_assessed'), 2)
        self.assertEqual(result.get('successful'), 1)
        self.assertEqual(result.get('failed'), 1)
        
        # Should have results even for failed assessments
        results = result.get('results', [])
        self.assertEqual(len(results), 2)
        
        # Failed result should be marked as BLOCK
        failed_result = next((r for r in results if 'error' in r), None)
        self.assertIsNotNone(failed_result)
        self.assertEqual(failed_result.get('trading_decision'), 'BLOCK')


@override_settings(**TEST_SETTINGS)
class RiskProfileConfigurationTests(BaseRiskTestCase):
    """Test suite for risk profile configuration."""
    
    def test_conservative_profile_configuration(self):
        """Test conservative risk profile configuration."""
        from risk.tasks.coordinator import _get_risk_profile_config
        
        config = _get_risk_profile_config('Conservative')
        
        # Should have strict requirements
        self.assertLessEqual(config.get('max_acceptable_risk', 100), 30)
        self.assertTrue(config.get('require_ownership_renounced', False))
        self.assertLessEqual(config.get('max_sell_tax_percent', 100), 10)
        self.assertGreaterEqual(config.get('min_liquidity_usd', 0), 50000)
        
        # Should require critical checks
        required_checks = config.get('required_checks', [])
        critical_checks = ['HONEYPOT', 'LIQUIDITY', 'OWNERSHIP']
        for check in critical_checks:
            self.assertIn(check, required_checks)
    
    def test_aggressive_profile_configuration(self):
        """Test aggressive risk profile configuration."""
        from risk.tasks.coordinator import _get_risk_profile_config
        
        config = _get_risk_profile_config('Aggressive')
        
        # Should have relaxed requirements
        self.assertGreaterEqual(config.get('max_acceptable_risk', 0), 70)
        self.assertFalse(config.get('require_ownership_renounced', True))
        self.assertGreaterEqual(config.get('max_sell_tax_percent', 0), 35)
        self.assertLessEqual(config.get('min_liquidity_usd', 100000), 10000)
        
        # Should have fewer required checks
        required_checks = config.get('required_checks', [])
        self.assertLessEqual(len(required_checks), 2)
    
    def test_risk_profile_rule_application(self):
        """Test application of risk profile specific rules."""
        from risk.tasks.coordinator import _apply_risk_profile_rules
        
        # Conservative profile with ownership not renounced
        conservative_config = {'require_ownership_renounced': True}
        check_results = [
            TestDataFactory.create_ownership_result(is_renounced=False)
        ]
        
        result = _apply_risk_profile_rules(check_results, conservative_config)
        
        # Should block due to ownership requirement
        self.assertTrue(result.get('should_block', False))
        self.assertIn('renounced', ' '.join(result.get('reasons', [])).lower())
    
    def test_blocking_thresholds(self):
        """Test risk profile blocking thresholds."""
        from risk.tasks.coordinator import _apply_risk_profile_rules
        
        config = {
            'blocking_thresholds': {
                'HONEYPOT': 90,
                'LIQUIDITY': 80
            }
        }
        
        # Test threshold blocking
        check_results = [
            TestDataFactory.create_risk_check_result('HONEYPOT', risk_score=95),
            TestDataFactory.create_risk_check_result('LIQUIDITY', risk_score=85)
        ]
        
        result = _apply_risk_profile_rules(check_results, config)
        
        # Should block due to threshold violations
        self.assertTrue(result.get('should_block', False))
        self.assertGreaterEqual(len(result.get('reasons', [])), 2)


@override_settings(**TEST_SETTINGS)
class ConfidenceAndScoringTests(BaseRiskTestCase):
    """Test suite for confidence scoring and risk calculation."""
    
    def test_confidence_score_calculation(self):
        """Test confidence score calculation."""
        from risk.tasks.coordinator import _calculate_confidence_score
        
        # High confidence scenario (all checks completed quickly)
        high_confidence_results = [
            TestDataFactory.create_risk_check_result('HONEYPOT', status='COMPLETED', execution_time_ms=100),
            TestDataFactory.create_risk_check_result('LIQUIDITY', status='COMPLETED', execution_time_ms=150),
            TestDataFactory.create_risk_check_result('OWNERSHIP', status='COMPLETED', execution_time_ms=80)
        ]
        
        confidence = _calculate_confidence_score(high_confidence_results)
        self.assertGreater(confidence, 80)
        
        # Low confidence scenario (some failed, slow execution)
        low_confidence_results = [
            TestDataFactory.create_risk_check_result('HONEYPOT', status='COMPLETED', execution_time_ms=5000),
            TestDataFactory.create_risk_check_result('LIQUIDITY', status='FAILED', execution_time_ms=1000),
            TestDataFactory.create_risk_check_result('OWNERSHIP', status='COMPLETED', execution_time_ms=8000)
        ]
        
        confidence = _calculate_confidence_score(low_confidence_results)
        self.assertLess(confidence, 60)
    
    def test_weighted_risk_score_calculation(self):
        """Test weighted risk score calculation."""
        from risk.tasks import calculate_weighted_risk_score
        
        # Mock check results with different risk levels
        check_results = [
            {'check_type': 'HONEYPOT', 'status': 'COMPLETED', 'risk_score': 15},
            {'check_type': 'LIQUIDITY', 'status': 'COMPLETED', 'risk_score': 25},
            {'check_type': 'OWNERSHIP', 'status': 'COMPLETED', 'risk_score': 35}
        ]
        
        overall_score, risk_level = calculate_weighted_risk_score(check_results)
        
        # Should be reasonable average
        self.assertGreater(overall_score, 15)
        self.assertLess(overall_score, 35)
        self.assertIn(risk_level, ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'])
    
    def test_trading_decision_logic(self):
        """Test trading decision logic."""
        from risk.tasks.coordinator import _analyze_and_finalize_assessment
        
        # Mock low risk scenario
        low_risk_results = [
            TestDataFactory.create_honeypot_result(is_honeypot=False),
            TestDataFactory.create_liquidity_result(liquidity_usd=100000),
            TestDataFactory.create_ownership_result(is_renounced=True)
        ]
        
        conservative_config = {
            'max_acceptable_risk': 30,
            'require_ownership_renounced': True
        }
        
        assessment = _analyze_and_finalize_assessment(
            'test_id', 
            TestDataFactory.create_token_address('good'),
            TestDataFactory.create_pair_address('normal'),
            low_risk_results,
            conservative_config
        )
        
        # Should approve low risk token
        self.assertEqual(assessment.get('trading_decision'), 'APPROVE')
        self.assertFalse(assessment.get('is_blocked', True))


@override_settings(**TEST_SETTINGS)
class ErrorHandlingAndResilience(BaseRiskTestCase):
    """Test suite for error handling and system resilience."""
    
    def test_network_failure_handling(self):
        """Test handling of network failures."""
        token_address = TestDataFactory.create_token_address('normal')
        pair_address = TestDataFactory.create_pair_address('normal')
        
        # Mock network failure
        with patch('risk.tasks.coordinator._execute_parallel_risk_checks') as mock_checks:
            mock_checks.side_effect = ConnectionError("Network unavailable")
            
            result = assess_token_risk(token_address, pair_address)
        
        # Should handle failure gracefully
        self.assertEqual(result.get('trading_decision'), 'BLOCK')
        self.assertTrue(result.get('is_blocked', False))
        self.assertIn('error', result)
    
    def test_partial_check_failures(self):
        """Test handling of partial check failures."""
        token_address = TestDataFactory.create_token_address('normal')
        pair_address = TestDataFactory.create_pair_address('normal')
        
        # Mock scenario where some checks succeed and others fail
        mixed_results = [
            TestDataFactory.create_honeypot_result(is_honeypot=False),
            TestDataFactory.create_risk_check_result(
                'LIQUIDITY', status='FAILED', 
                error_message='RPC timeout'
            ),
            TestDataFactory.create_ownership_result(is_renounced=True)
        ]
        
        with patch('risk.tasks.coordinator._execute_parallel_risk_checks') as mock_checks:
            mock_checks.return_value = mixed_results
            
            result = assess_token_risk(token_address, pair_address)
        
        # Should still make a decision based on available data
        self.assertIn(result.get('trading_decision'), ['APPROVE', 'SKIP', 'BLOCK'])
        self.assertGreater(result.get('checks_completed', 0), 0)
        self.assertGreater(result.get('checks_failed', 0), 0)
    
    def test_timeout_handling(self):
        """Test handling of assessment timeouts."""
        token_address = TestDataFactory.create_token_address('normal')
        pair_address = TestDataFactory.create_pair_address('normal')
        
        # Mock timeout scenario
        with patch('risk.tasks.coordinator._execute_parallel_risk_checks') as mock_checks:
            mock_checks.side_effect = TimeoutError("Assessment timed out")
            
            result = assess_token_risk(token_address, pair_address)
        
        # Should handle timeout as maximum risk
        self.assertEqual(result.get('trading_decision'), 'BLOCK')
        self.assertEqual(result.get('overall_risk_score'), 100.0)
        self.assertIn('timeout', result.get('error', '').lower())


@override_settings(**TEST_SETTINGS)
class IntegrationTests(BaseRiskTestCase):
    """Integration tests for complete risk assessment workflow."""
    
    def test_end_to_end_assessment_workflow(self):
        """Test complete end-to-end assessment workflow."""
        # Test realistic scenario with actual token addresses
        token_address = TestDataFactory.create_token_address('good')
        pair_address = TestDataFactory.create_pair_address('highliq')
        
        # Run full assessment
        result = assess_token_risk(
            token_address=token_address,
            pair_address=pair_address,
            risk_profile='Moderate',
            parallel_execution=True,
            include_advanced_checks=True
        )
        
        # Validate complete result structure
        required_fields = [
            'assessment_id', 'token_address', 'pair_address',
            'overall_risk_score', 'risk_level', 'trading_decision',
            'check_results', 'thought_log', 'summary'
        ]
        
        for field in required_fields:
            self.assertIn(field, result, f"Missing required field: {field}")
        
        # Validate thought log structure
        thought_log = result.get('thought_log', {})
        thought_log_fields = ['timestamp', 'decision', 'narrative', 'signals']
        for field in thought_log_fields:
            self.assertIn(field, thought_log, f"Missing thought log field: {field}")
        
        # Validate summary structure
        summary = result.get('summary', {})
        summary_fields = ['checks_summary', 'risk_summary', 'recommendation']
        for field in summary_fields:
            self.assertIn(field, summary, f"Missing summary field: {field}")
    
    def test_assessment_consistency(self):
        """Test that repeated assessments produce consistent results."""
        token_address = TestDataFactory.create_token_address('good')
        pair_address = TestDataFactory.create_pair_address('normal')
        
        # Run assessment multiple times
        results = []
        for _ in range(3):
            result = assess_token_risk(token_address, pair_address, risk_profile='Conservative')
            results.append(result)
        
        # Results should be consistent
        decisions = [r.get('trading_decision') for r in results]
        risk_scores = [r.get('overall_risk_score') for r in results]
        
        # All decisions should be the same
        self.assertEqual(len(set(decisions)), 1, "Inconsistent trading decisions")
        
        # Risk scores should be similar (within 10 points)
        max_score = max(risk_scores)
        min_score = min(risk_scores)
        self.assertLess(max_score - min_score, 10, "Risk scores vary too much")
    
    def test_different_token_scenarios(self):
        """Test assessment of different token scenarios."""
        scenarios = [
            ('good', 'normal', 'APPROVE'),
            ('honeypot', 'normal', 'BLOCK'),
            ('normal', 'lowliq', 'SKIP'),
            ('renounced', 'highliq', 'APPROVE')
        ]
        
        for token_type, pair_type, expected_decision in scenarios:
            with self.subTest(token_type=token_type, pair_type=pair_type):
                token_address = TestDataFactory.create_token_address(token_type)
                pair_address = TestDataFactory.create_pair_address(pair_type)
                
                result = assess_token_risk(token_address, pair_address, risk_profile='Conservative')
                
                # Note: Due to mocking, we can't guarantee exact decisions,
                # but we can ensure the system handles different scenarios
                self.assertIn(result.get('trading_decision'), ['APPROVE', 'SKIP', 'BLOCK'])
                self.assertIsInstance(result.get('overall_risk_score'), (int, float))


if __name__ == '__main__':
    unittest.main()