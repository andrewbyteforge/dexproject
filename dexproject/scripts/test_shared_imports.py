#!/usr/bin/env python3
"""
Quick test script to validate shared module imports work correctly.

Run this from the dexproject root directory:
    python scripts/test_shared_imports.py

File: scripts/test_shared_imports.py
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_basic_imports():
    """Test that basic shared imports work."""
    print("🧪 Testing basic shared module imports...")
    
    try:
        # Test constants import
        from shared.constants import REDIS_CHANNELS, REDIS_KEYS, MESSAGE_TYPES
        print("✅ Constants imported successfully")
        print(f"   - Found {len(REDIS_CHANNELS)} Redis channels")
        print(f"   - Found {len(REDIS_KEYS)} Redis keys")
        print(f"   - Found {len(MESSAGE_TYPES)} message types")
    except Exception as e:
        print(f"❌ Constants import failed: {e}")
        return False
    
    try:
        # Test schemas import
        from shared.schemas import (
            BaseMessage, MessageType, RiskLevel, 
            NewPairDiscovered, FastRiskAssessment, 
            serialize_message, create_correlation_id
        )
        print("✅ Schemas imported successfully")
        print(f"   - Pydantic available: {'Yes' if hasattr(BaseMessage, 'json') else 'No (using dataclasses)'}")
    except Exception as e:
        print(f"❌ Schemas import failed: {e}")
        return False
    
    try:
        # Test main shared import (the one that was failing)
        from shared import RedisClient, REDIS_CHANNELS, MessageType
        print("✅ Main shared imports work!")
        print(f"   - RedisClient: {'Available' if RedisClient else 'Not available'}")
    except Exception as e:
        print(f"❌ Main shared import failed: {e}")
        return False
    
    return True

def test_message_creation():
    """Test creating and serializing messages."""
    print("\n🧪 Testing message creation and serialization...")
    
    try:
        from shared.schemas import (
            create_base_message, MessageType, 
            serialize_message, create_correlation_id,
            NewPairDiscovered
        )
        
        # Test base message creation
        base_msg = create_base_message(
            MessageType.ENGINE_STATUS,
            "test_engine",
            "engine-123"
        )
        print("✅ Base message created successfully")
        
        # Test serialization
        json_str = serialize_message(base_msg)
        print("✅ Message serialization works")
        print(f"   - JSON length: {len(json_str)} chars")
        
        # Test correlation ID generation
        corr_id = create_correlation_id()
        print(f"✅ Correlation ID generated: {corr_id[:8]}...")
        
    except Exception as e:
        print(f"❌ Message creation failed: {e}")
        return False
    
    return True

def test_redis_constants():
    """Test Redis constant lookup functions."""
    print("\n🧪 Testing Redis constants and utilities...")
    
    try:
        from shared.constants import (
            get_redis_channel, get_redis_key,
            validate_ethereum_address, MESSAGE_TYPES
        )
        
        # Test channel lookup
        channel = get_redis_channel(MESSAGE_TYPES['NEW_PAIR_DISCOVERED'])
        print(f"✅ Redis channel lookup: {channel}")
        
        # Test key generation
        key = get_redis_key('risk_cache', '0x1234567890123456789012345678901234567890')
        print(f"✅ Redis key generation: {key}")
        
        # Test address validation
        valid_addr = validate_ethereum_address('0x1234567890123456789012345678901234567890')
        invalid_addr = validate_ethereum_address('invalid')
        print(f"✅ Address validation: valid={valid_addr}, invalid={invalid_addr}")
        
    except Exception as e:
        print(f"❌ Redis constants test failed: {e}")
        return False
    
    return True

def main():
    """Run all import tests."""
    print("=" * 60)
    print("SHARED MODULE IMPORT TESTS")
    print("=" * 60)
    
    # Check if we're in the right directory
    if not (project_root / "manage.py").exists():
        print("❌ ERROR: Run this script from the dexproject directory (where manage.py is located)")
        return False
    
    tests_passed = 0
    total_tests = 3
    
    # Run tests
    if test_basic_imports():
        tests_passed += 1
    
    if test_message_creation():
        tests_passed += 1
    
    if test_redis_constants():
        tests_passed += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    if tests_passed == total_tests:
        print(f"🎉 All tests passed! ({tests_passed}/{total_tests})")
        print("\n✅ Your shared module imports are working correctly!")
        print("   You can now run: python scripts/quick_phase3_test.py")
        return True
    else:
        print(f"❌ Some tests failed ({tests_passed}/{total_tests})")
        print("\n🔧 Check the error messages above and verify:")
        print("   1. You've updated shared/__init__.py")
        print("   2. You've updated shared/constants.py") 
        print("   3. You've updated shared/schemas.py")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)