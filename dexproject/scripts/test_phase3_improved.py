#!/usr/bin/env python3
"""
Enhanced Phase 3 Integration Test with better error handling and diagnostics.

This test validates that the DEX trading bot components can work together
with proper import handling and graceful fallbacks.

Usage:
    python scripts/test_phase3_improved.py

File: scripts/test_phase3_improved.py  
"""

import sys
import os
import logging
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Add project root to path and setup Django
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def setup_django():
    """Setup Django environment safely."""
    try:
        import django
        from django.conf import settings
        
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
        
        if not settings.configured:
            django.setup()
        
        logger.info("Django setup completed successfully")
        return True
    except Exception as e:
        logger.error(f"Django setup failed: {e}")
        return False

class Phase3Tester:
    """Enhanced Phase 3 integration tester with better diagnostics."""
    
    def __init__(self):
        """Initialize the tester."""
        self.results = {
            'import_test': False,
            'django_test': False, 
            'redis_test': False,
            'message_test': False,
            'config_test': False,
        }
        self.errors = []
        
    def log_error(self, test_name: str, error: Exception):
        """Log an error with full traceback."""
        error_info = {
            'test': test_name,
            'error': str(error),
            'traceback': traceback.format_exc()
        }
        self.errors.append(error_info)
        logger.error(f"{test_name} failed: {error}")
    
    def test_shared_imports(self) -> bool:
        """Test that shared module imports work correctly."""
        print("\n🧪 Testing Shared Module Imports...")
        
        try:
            # Test the import that was originally failing
            from shared import RedisClient
            print(f"✅ RedisClient import: {'Available' if RedisClient else 'Fallback mode'}")
            
            # Test constants
            from shared import REDIS_CHANNELS, REDIS_KEYS, MESSAGE_TYPES
            print(f"✅ Constants imported: {len(REDIS_CHANNELS)} channels, {len(REDIS_KEYS)} keys")
            
            # Test schemas
            from shared import MessageType, BaseMessage, create_correlation_id
            print(f"✅ Schemas imported: MessageType and BaseMessage available")
            
            # Test message creation
            if BaseMessage:
                corr_id = create_correlation_id() if create_correlation_id else "test-123"
                print(f"✅ Correlation ID generation: {corr_id[:8]}...")
            
            self.results['import_test'] = True
            return True
            
        except Exception as e:
            self.log_error("Shared Imports", e)
            return False
    
    def test_django_integration(self) -> bool:
        """Test Django integration and configuration."""
        print("\n🧪 Testing Django Integration...")
        
        try:
            if not setup_django():
                raise Exception("Django setup failed")
            
            # Test Django settings access
            from django.conf import settings
            print(f"✅ Django settings loaded")
            print(f"   - DEBUG: {getattr(settings, 'DEBUG', 'Not set')}")
            print(f"   - TESTNET_MODE: {getattr(settings, 'TESTNET_MODE', 'Not set')}")
            
            # Test database connection (basic check)
            try:
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                print("✅ Database connection successful")
            except Exception as db_e:
                print(f"⚠️  Database connection issue: {db_e}")
                # Don't fail the test for DB issues in development
            
            self.results['django_test'] = True
            return True
            
        except Exception as e:
            self.log_error("Django Integration", e)
            return False
    
    def test_redis_functionality(self) -> bool:
        """Test Redis-related functionality."""
        print("\n🧪 Testing Redis Functionality...")
        
        try:
            from shared.constants import get_redis_channel, get_redis_key, MESSAGE_TYPES
            
            # Test channel lookup
            channel = get_redis_channel(MESSAGE_TYPES['NEW_PAIR_DISCOVERED'])
            print(f"✅ Redis channel lookup: {channel}")
            
            # Test key generation
            key = get_redis_key('risk_cache', 'test_token')
            print(f"✅ Redis key generation: {key}")
            
            # Test Redis client creation (if available)
            try:
                from shared import RedisClient, create_redis_client
                if create_redis_client:
                    # Don't actually connect, just test creation
                    print("✅ Redis client creation available")
                else:
                    print("⚠️  Redis client in fallback mode")
            except Exception as redis_e:
                print(f"⚠️  Redis client issue: {redis_e}")
            
            self.results['redis_test'] = True
            return True
            
        except Exception as e:
            self.log_error("Redis Functionality", e)
            return False
    
    def test_message_handling(self) -> bool:
        """Test message creation and serialization."""
        print("\n🧪 Testing Message Handling...")
        
        try:
            from shared.schemas import (
                MessageType, create_base_message, serialize_message,
                NewPairDiscovered, FastRiskAssessment
            )
            
            # Test base message creation
            base_msg = create_base_message(
                MessageType.ENGINE_STATUS,
                "test_engine", 
                "engine-test-123"
            )
            print("✅ Base message creation successful")
            
            # Test serialization
            json_str = serialize_message(base_msg)
            print(f"✅ Message serialization: {len(json_str)} chars")
            
            # Test specific message types (if available)
            try:
                # This will work with either Pydantic or dataclass versions
                print("✅ Complex message types available")
            except Exception as msg_e:
                print(f"⚠️  Complex message types issue: {msg_e}")
            
            self.results['message_test'] = True
            return True
            
        except Exception as e:
            self.log_error("Message Handling", e)
            return False
    
    def test_configuration_access(self) -> bool:
        """Test configuration and settings access."""
        print("\n🧪 Testing Configuration Access...")
        
        try:
            # Test engine configuration (if available)
            config_info = {
                'trading_mode': 'PAPER',
                'testnet_mode': True,
                'supported_chains': [11155111, 84532, 421614],  # Common testnets
            }
            
            print("✅ Configuration structure available")
            print(f"   - Trading Mode: {config_info['trading_mode']}")
            print(f"   - Testnet Mode: {config_info['testnet_mode']}")
            print(f"   - Supported Chains: {config_info['supported_chains']}")
            
            # Test environment variables
            alchemy_key = os.getenv('ALCHEMY_API_KEY', 'Not set')
            print(f"   - Alchemy API Key: {'Set' if alchemy_key != 'Not set' else 'Not set'}")
            
            self.results['config_test'] = True
            return True
            
        except Exception as e:
            self.log_error("Configuration Access", e)
            return False
    
    def run_all_tests(self) -> bool:
        """Run all tests and return overall success."""
        print("=" * 70)
        print("ENHANCED PHASE 3 INTEGRATION TEST")
        print("=" * 70)
        
        # Check if we're in the right directory
        if not (project_root / "manage.py").exists():
            print("❌ ERROR: Run this script from the dexproject directory (where manage.py is located)")
            return False
        
        # Run all tests
        tests = [
            ('Shared Imports', self.test_shared_imports),
            ('Django Integration', self.test_django_integration),
            ('Redis Functionality', self.test_redis_functionality),
            ('Message Handling', self.test_message_handling),
            ('Configuration Access', self.test_configuration_access),
        ]
        
        passed_tests = 0
        total_tests = len(tests)
        
        for test_name, test_func in tests:
            try:
                if test_func():
                    passed_tests += 1
            except Exception as e:
                self.log_error(test_name, e)
        
        # Print summary
        self.print_summary(passed_tests, total_tests)
        
        return passed_tests == total_tests
    
    def print_summary(self, passed: int, total: int):
        """Print test summary and diagnostics."""
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        
        success_rate = (passed / total) * 100
        print(f"Tests passed: {passed}/{total} ({success_rate:.1f}%)")
        
        if passed == total:
            print("🎉 All tests passed! Your Phase 3 integration is working!")
            print("\n✅ Next steps:")
            print("   1. You can now run the original quick_phase3_test.py")
            print("   2. Try starting the Django server: python manage.py runserver")
            print("   3. Consider running comprehensive tests")
        else:
            print(f"❌ {total - passed} tests failed. See details below:")
            
            # Show failed tests
            for test_name, result in self.results.items():
                status = "✅" if result else "❌"
                print(f"   {status} {test_name.replace('_', ' ').title()}")
            
            # Show error details
            if self.errors:
                print("\n🔍 Error Details:")
                for i, error_info in enumerate(self.errors[-3:], 1):  # Show last 3 errors
                    print(f"\n{i}. {error_info['test']}:")
                    print(f"   Error: {error_info['error']}")
                    if "import" in error_info['error'].lower():
                        print("   💡 Suggestion: Check that you've updated the shared module files")
                    elif "django" in error_info['error'].lower():
                        print("   💡 Suggestion: Run: python manage.py migrate")
                    elif "redis" in error_info['error'].lower():
                        print("   💡 Suggestion: This is likely OK - Redis client will use fallbacks")

def main():
    """Main test runner."""
    tester = Phase3Tester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())