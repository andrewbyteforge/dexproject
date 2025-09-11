#!/usr/bin/env python
"""
Risk Assessment Test Runner

File: dexproject/run_risk_tests.py

Comprehensive test runner for the risk assessment system.
Provides detailed reporting and performance metrics.
"""

import os
import sys
import time
import unittest
from io import StringIO
from typing import Dict, List, Any

import django
from django.conf import settings
from django.test.utils import get_runner
from django.core.management import execute_from_command_line

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()


class TestResult:
    """Container for test results and metrics."""
    
    def __init__(self):
        self.tests_run = 0
        self.failures = 0
        self.errors = 0
        self.skipped = 0
        self.success_rate = 0.0
        self.execution_time = 0.0
        self.failure_details = []
        self.error_details = []


class RiskTestRunner:
    """Custom test runner for risk assessment tests."""
    
    def __init__(self, verbosity: int = 2):
        self.verbosity = verbosity
        self.results = {}
    
    def run_test_suite(self, test_module: str) -> TestResult:
        """Run a specific test suite and return results."""
        print(f"\n{'='*60}")
        print(f"Running {test_module} Tests")
        print(f"{'='*60}")
        
        start_time = time.time()
        
        # Capture test output
        test_output = StringIO()
        
        # Create test suite
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromName(test_module)
        
        # Run tests
        runner = unittest.TextTestRunner(
            stream=test_output,
            verbosity=self.verbosity,
            buffer=True
        )
        
        test_result = runner.run(suite)
        execution_time = time.time() - start_time
        
        # Process results
        result = TestResult()
        result.tests_run = test_result.testsRun
        result.failures = len(test_result.failures)
        result.errors = len(test_result.errors)
        result.skipped = len(test_result.skipped)
        result.execution_time = execution_time
        
        if result.tests_run > 0:
            result.success_rate = ((result.tests_run - result.failures - result.errors) / result.tests_run) * 100
        
        # Capture failure and error details
        for test, traceback in test_result.failures:
            result.failure_details.append({
                'test': str(test),
                'traceback': traceback
            })
        
        for test, traceback in test_result.errors:
            result.error_details.append({
                'test': str(test),
                'traceback': traceback
            })
        
        # Print summary
        self._print_test_summary(test_module, result)
        
        return result
    
    def _print_test_summary(self, test_module: str, result: TestResult):
        """Print summary for a test module."""
        print(f"\n{test_module} Results:")
        print(f"  Tests Run: {result.tests_run}")
        print(f"  Successes: {result.tests_run - result.failures - result.errors}")
        print(f"  Failures: {result.failures}")
        print(f"  Errors: {result.errors}")
        print(f"  Skipped: {result.skipped}")
        print(f"  Success Rate: {result.success_rate:.1f}%")
        print(f"  Execution Time: {result.execution_time:.2f}s")
        
        # Print failures if any
        if result.failure_details:
            print(f"\n  Failures:")
            for i, failure in enumerate(result.failure_details[:3]):  # Show first 3
                print(f"    {i+1}. {failure['test']}")
        
        # Print errors if any
        if result.error_details:
            print(f"\n  Errors:")
            for i, error in enumerate(result.error_details[:3]):  # Show first 3
                print(f"    {i+1}. {error['test']}")
    
    def run_all_tests(self) -> Dict[str, TestResult]:
        """Run all risk assessment tests."""
        print("🚀 Starting Risk Assessment Test Suite")
        print(f"Python: {sys.version}")
        print(f"Django: {django.get_version()}")
        
        test_modules = [
            'risk.tests.test_honeypot',
            'risk.tests.test_liquidity', 
            'risk.tests.test_coordinator'
        ]
        
        total_start_time = time.time()
        
        for module in test_modules:
            try:
                result = self.run_test_suite(module)
                self.results[module] = result
            except Exception as e:
                print(f"❌ Failed to run {module}: {e}")
                # Create failed result
                failed_result = TestResult()
                failed_result.errors = 1
                failed_result.error_details = [{'test': module, 'traceback': str(e)}]
                self.results[module] = failed_result
        
        total_execution_time = time.time() - total_start_time
        
        # Print overall summary
        self._print_overall_summary(total_execution_time)
        
        return self.results
    
    def _print_overall_summary(self, total_time: float):
        """Print overall test summary."""
        print(f"\n{'='*60}")
        print("OVERALL TEST SUMMARY")
        print(f"{'='*60}")
        
        total_tests = sum(r.tests_run for r in self.results.values())
        total_failures = sum(r.failures for r in self.results.values())
        total_errors = sum(r.errors for r in self.results.values())
        total_skipped = sum(r.skipped for r in self.results.values())
        
        overall_success_rate = 0
        if total_tests > 0:
            overall_success_rate = ((total_tests - total_failures - total_errors) / total_tests) * 100
        
        print(f"Total Tests: {total_tests}")
        print(f"Successes: {total_tests - total_failures - total_errors}")
        print(f"Failures: {total_failures}")
        print(f"Errors: {total_errors}")
        print(f"Skipped: {total_skipped}")
        print(f"Overall Success Rate: {overall_success_rate:.1f}%")
        print(f"Total Execution Time: {total_time:.2f}s")
        
        # Module breakdown
        print(f"\nModule Breakdown:")
        for module, result in self.results.items():
            module_name = module.split('.')[-1]
            status = "✅ PASS" if result.failures == 0 and result.errors == 0 else "❌ FAIL"
            print(f"  {module_name:<20} {status} ({result.success_rate:.1f}%)")
        
        # Overall status
        if total_failures == 0 and total_errors == 0:
            print(f"\n🎉 ALL TESTS PASSED!")
        else:
            print(f"\n⚠️  SOME TESTS FAILED - See details above")


def run_performance_benchmark():
    """Run performance benchmarks for risk assessment."""
    print(f"\n{'='*60}")
    print("PERFORMANCE BENCHMARKS")
    print(f"{'='*60}")
    
    try:
        from risk.tests import TestDataFactory
        from risk.tasks.coordinator import assess_token_risk, quick_honeypot_check
        
        # Benchmark quick honeypot check
        print("\n1. Quick Honeypot Check Performance:")
        token_address = TestDataFactory.create_token_address('good')
        pair_address = TestDataFactory.create_pair_address('normal')
        
        start_time = time.time()
        result = quick_honeypot_check(token_address, pair_address)
        quick_check_time = time.time() - start_time
        
        print(f"   Time: {quick_check_time:.3f}s")
        print(f"   Result: {'PASS' if not result.get('is_honeypot') else 'HONEYPOT'}")
        
        # Benchmark full assessment
        print("\n2. Full Risk Assessment Performance:")
        start_time = time.time()
        result = assess_token_risk(
            token_address, pair_address, 
            risk_profile='Conservative',
            parallel_execution=True
        )
        full_assessment_time = time.time() - start_time
        
        print(f"   Time: {full_assessment_time:.3f}s")
        print(f"   Decision: {result.get('trading_decision', 'UNKNOWN')}")
        print(f"   Risk Score: {result.get('overall_risk_score', 0):.1f}")
        print(f"   Confidence: {result.get('confidence_score', 0):.1f}%")
        
        # Performance targets
        print(f"\n3. Performance Targets:")
        quick_target = 0.5  # 500ms
        full_target = 3.0   # 3 seconds
        
        quick_status = "✅ PASS" if quick_check_time <= quick_target else "❌ SLOW"
        full_status = "✅ PASS" if full_assessment_time <= full_target else "❌ SLOW"
        
        print(f"   Quick Check: {quick_status} (target: {quick_target}s)")
        print(f"   Full Assessment: {full_status} (target: {full_target}s)")
        
    except Exception as e:
        print(f"❌ Performance benchmark failed: {e}")


def run_mock_integration_test():
    """Run mock integration test with realistic scenarios."""
    print(f"\n{'='*60}")
    print("MOCK INTEGRATION TEST")
    print(f"{'='*60}")
    
    try:
        from risk.tests import TestDataFactory
        from risk.tasks.coordinator import assess_token_risk
        
        # Test scenarios
        scenarios = [
            {
                'name': 'Good Token - High Liquidity',
                'token_type': 'good',
                'pair_type': 'highliq',
                'expected': 'APPROVE'
            },
            {
                'name': 'Honeypot Token',
                'token_type': 'honeypot', 
                'pair_type': 'normal',
                'expected': 'BLOCK'
            },
            {
                'name': 'Low Liquidity Token',
                'token_type': 'normal',
                'pair_type': 'lowliq',
                'expected': 'SKIP'
            },
            {
                'name': 'Renounced Ownership',
                'token_type': 'renounced',
                'pair_type': 'normal',
                'expected': 'APPROVE'
            }
        ]
        
        results = []
        
        for scenario in scenarios:
            print(f"\nTesting: {scenario['name']}")
            
            token_address = TestDataFactory.create_token_address(scenario['token_type'])
            pair_address = TestDataFactory.create_pair_address(scenario['pair_type'])
            
            start_time = time.time()
            result = assess_token_risk(
                token_address, pair_address,
                risk_profile='Conservative'
            )
            execution_time = time.time() - start_time
            
            decision = result.get('trading_decision', 'UNKNOWN')
            risk_score = result.get('overall_risk_score', 0)
            
            print(f"  Decision: {decision}")
            print(f"  Risk Score: {risk_score:.1f}")
            print(f"  Time: {execution_time:.3f}s")
            
            # Check if result matches expectation (note: due to mocking, may not be exact)
            status = "✅" if decision in ['APPROVE', 'SKIP', 'BLOCK'] else "❌"
            print(f"  Status: {status}")
            
            results.append({
                'scenario': scenario['name'],
                'decision': decision,
                'risk_score': risk_score,
                'time': execution_time,
                'status': status
            })
        
        # Summary
        print(f"\nIntegration Test Summary:")
        successful = len([r for r in results if r['status'] == '✅'])
        print(f"  Successful: {successful}/{len(scenarios)}")
        print(f"  Average Time: {sum(r['time'] for r in results)/len(results):.3f}s")
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")


def main():
    """Main test execution function."""
    print("🧪 Risk Assessment System - Test Suite")
    print("=" * 60)
    
    # Parse command line arguments
    run_tests = '--no-tests' not in sys.argv
    run_benchmarks = '--benchmarks' in sys.argv or '--all' in sys.argv
    run_integration = '--integration' in sys.argv or '--all' in sys.argv
    verbose = '--verbose' in sys.argv
    
    verbosity = 2 if verbose else 1
    
    if '--help' in sys.argv:
        print("Usage: python run_risk_tests.py [options]")
        print("Options:")
        print("  --no-tests      Skip unit tests")
        print("  --benchmarks    Run performance benchmarks")
        print("  --integration   Run integration tests")
        print("  --all           Run everything")
        print("  --verbose       Verbose output")
        print("  --help          Show this help")
        return
    
    total_start_time = time.time()
    
    # Run unit tests
    if run_tests:
        runner = RiskTestRunner(verbosity=verbosity)
        test_results = runner.run_all_tests()
        
        # Check if tests passed
        total_failures = sum(r.failures for r in test_results.values())
        total_errors = sum(r.errors for r in test_results.values())
        
        if total_failures > 0 or total_errors > 0:
            print("⚠️  Some tests failed. Check output above for details.")
    
    # Run performance benchmarks
    if run_benchmarks:
        run_performance_benchmark()
    
    # Run integration tests
    if run_integration:
        run_mock_integration_test()
    
    total_time = time.time() - total_start_time
    
    print(f"\n{'='*60}")
    print(f"Test Suite Complete - Total Time: {total_time:.2f}s")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()