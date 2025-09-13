#!/usr/bin/env python3
"""
Quick Mempool Test Runner

Simple script to quickly test mempool integration with common configurations.
Provides pre-configured test scenarios for different use cases.

Usage:
    python scripts/quick_mempool_test.py [scenario]
    
Scenarios:
    connection-test    - Test WebSocket connections only (30s)
    quick-test        - Quick mempool monitoring test (60s)
    performance-test  - Performance validation test (300s)  
    demo-test         - Demo mode with fake API keys (60s)

Path: scripts/quick_mempool_test.py
"""

import asyncio
import sys
from pathlib import Path
import argparse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import our test script
from scripts.test_mempool_integration import MempoolTester


class QuickTestRunner:
    """Quick test runner with predefined scenarios."""
    
    SCENARIOS = {
        'connection-test': {
            'description': 'Test WebSocket connections only',
            'duration': 30,
            'verbose': True,
            'focus': 'connections'
        },
        'quick-test': {
            'description': 'Quick mempool monitoring test',
            'duration': 60,
            'verbose': False,
            'focus': 'basic_monitoring'
        },
        'performance-test': {
            'description': 'Performance validation test',
            'duration': 300,
            'verbose': True,
            'focus': 'performance'
        },
        'demo-test': {
            'description': 'Demo mode with test API keys',
            'duration': 60,
            'verbose': True,
            'demo_mode': True,
            'focus': 'demo'
        }
    }
    
    @staticmethod
    def print_scenarios():
        """Print available test scenarios."""
        print("📋 Available Test Scenarios:")
        print("=" * 50)
        
        for name, config in QuickTestRunner.SCENARIOS.items():
            duration = config['duration']
            desc = config['description']
            print(f"  {name:<18} - {desc} ({duration}s)")
        
        print("\nUsage:")
        print("  python scripts/quick_mempool_test.py [scenario]")
        print("  python scripts/quick_mempool_test.py --list")
        print("\nExamples:")
        print("  python scripts/quick_mempool_test.py connection-test")
        print("  python scripts/quick_mempool_test.py quick-test")
    
    @staticmethod
    async def run_scenario(scenario_name: str):
        """Run a specific test scenario."""
        if scenario_name not in QuickTestRunner.SCENARIOS:
            print(f"❌ Unknown scenario: {scenario_name}")
            print("\nAvailable scenarios:")
            QuickTestRunner.print_scenarios()
            return False
        
        config = QuickTestRunner.SCENARIOS[scenario_name]
        
        print(f"🚀 Running {scenario_name}: {config['description']}")
        print(f"⏱️  Duration: {config['duration']} seconds")
        print("=" * 60)
        
        # Create tester with scenario configuration
        tester = MempoolTester(
            test_duration=config['duration'],
            verbose=config.get('verbose', False),
            demo_mode=config.get('demo_mode', False)
        )
        
        try:
            # Run the test
            results = await tester.run_comprehensive_test()
            
            # Determine success
            errors = len(results.get('errors', []))
            if errors == 0:
                print(f"\n✅ {scenario_name} completed successfully!")
                return True
            else:
                print(f"\n⚠️  {scenario_name} completed with {errors} errors")
                return False
                
        except Exception as e:
            print(f"\n❌ {scenario_name} failed: {e}")
            return False


async def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(description="Quick mempool integration testing")
    parser.add_argument("scenario", nargs='?', default='quick-test', help="Test scenario to run")
    parser.add_argument("--list", action="store_true", help="List available scenarios")
    
    args = parser.parse_args()
    
    if args.list:
        QuickTestRunner.print_scenarios()
        return
    
    # Run the specified scenario
    success = await QuickTestRunner.run_scenario(args.scenario)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())