#!/usr/bin/env python3
"""
Unit tests for the shared module (fixed import paths).

Run from dexproject directory:
    python scripts/test_shared_unit_tests.py

File: scripts/test_shared_unit_tests.py
"""

import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_shared_constants_import():
    """Test that constants can be imported."""
    from shared.constants import REDIS_CHANNELS, REDIS_KEYS, MESSAGE_TYPES
    
    assert isinstance(REDIS_CHANNELS, dict)
    assert isinstance(REDIS_KEYS, dict) 
    assert isinstance(MESSAGE_TYPES, dict)
    assert len(REDIS_CHANNELS) > 0
    assert len(REDIS_KEYS) > 0
    assert len(MESSAGE_TYPES) > 0
    print("✅ Constants import test passed")

def test_shared_schemas_import():
    """Test that schemas can be imported."""
    from shared.schemas import (
        BaseMessage, MessageType, RiskLevel, DecisionType,
        serialize_message, deserialize_message, create_correlation_id
    )
    
    assert MessageType is not None
    assert RiskLevel is not None
    assert DecisionType is not None
    assert BaseMessage is not None
    print("✅ Schemas import test passed")

def test_main_shared_import():
    """Test the main shared module import (the one that was failing)."""
    from shared import RedisClient, REDIS_CHANNELS, MessageType, MESSAGE_TYPES
    
    # RedisClient might be None if not available, but import should work
    assert REDIS_CHANNELS is not None
    assert MessageType is not None
    assert MESSAGE_TYPES is not None
    print("✅ Main shared import test passed (including MESSAGE_TYPES)")

def test_redis_channel_lookup():
    """Test Redis channel lookup function."""
    from shared.constants import get_redis_channel, MESSAGE_TYPES
    
    channel = get_redis_channel(MESSAGE_TYPES['NEW_PAIR_DISCOVERED'])
    assert channel is not None
    assert isinstance(channel, str)
    assert 'dex_bot' in channel
    print(f"✅ Redis channel lookup test passed: {channel}")

def test_redis_key_generation():
    """Test Redis key generation."""
    from shared.constants import get_redis_key
    
    # Test key without identifier
    key = get_redis_key('risk_cache')
    assert key == 'dex_bot:risk:token'
    
    # Test key with identifier
    key_with_id = get_redis_key('risk_cache', 'test_token')
    assert key_with_id == 'dex_bot:risk:token:test_token'
    print("✅ Redis key generation test passed")

def test_ethereum_address_validation():
    """Test Ethereum address validation."""
    from shared.constants import validate_ethereum_address
    
    # Valid address
    valid_addr = '0x1234567890123456789012345678901234567890'
    assert validate_ethereum_address(valid_addr) == True
    
    # Invalid addresses
    assert validate_ethereum_address('invalid') == False
    assert validate_ethereum_address('0x123') == False  # Too short
    assert validate_ethereum_address('1234567890123456789012345678901234567890') == False  # No 0x
    print("✅ Ethereum address validation test passed")

def test_correlation_id_generation():
    """Test correlation ID generation."""
    from shared.schemas import create_correlation_id
    
    corr_id = create_correlation_id()
    assert isinstance(corr_id, str)
    assert len(corr_id) > 10  # Should be a UUID string
    
    # Test uniqueness
    corr_id2 = create_correlation_id()
    assert corr_id != corr_id2
    print(f"✅ Correlation ID generation test passed: {corr_id[:8]}...")

def test_base_message_creation():
    """Test base message creation."""
    from shared.schemas import create_base_message, MessageType
    
    msg = create_base_message(
        MessageType.ENGINE_STATUS,
        "test_service",
        "test_engine",
        "test_correlation"
    )
    
    assert msg.message_type == MessageType.ENGINE_STATUS.value
    assert msg.source_service == "test_service"
    assert msg.engine_id == "test_engine"
    assert msg.correlation_id == "test_correlation"
    assert msg.timestamp is not None
    print("✅ Base message creation test passed")

def test_message_serialization():
    """Test message serialization."""
    from shared.schemas import create_base_message, MessageType, serialize_message
    
    msg = create_base_message(
        MessageType.ENGINE_STATUS,
        "test_service"
    )
    
    json_str = serialize_message(msg)
    assert isinstance(json_str, str)
    assert len(json_str) > 0
    
    # Should be valid JSON
    data = json.loads(json_str)
    assert data['message_type'] == MessageType.ENGINE_STATUS.value
    assert data['source_service'] == "test_service"
    print(f"✅ Message serialization test passed ({len(json_str)} chars)")

def test_message_types_enum():
    """Test MessageType enum values."""
    from shared.schemas import MessageType
    
    assert MessageType.NEW_PAIR_DISCOVERED == "new_pair_discovered"
    assert MessageType.FAST_RISK_COMPLETE == "fast_risk_complete"
    assert MessageType.ENGINE_STATUS == "engine_status"
    print("✅ MessageType enum test passed")

def test_full_message_workflow():
    """Test complete message creation, serialization, and deserialization."""
    from shared.schemas import (
        create_base_message, MessageType, serialize_message, 
        deserialize_message, create_correlation_id
    )
    
    # Create message
    corr_id = create_correlation_id()
    msg = create_base_message(
        MessageType.ENGINE_STATUS,
        "test_engine",
        "engine-123",
        corr_id
    )
    
    # Serialize
    json_str = serialize_message(msg)
    
    # Deserialize
    data = deserialize_message(json_str)
    
    # Verify round trip
    assert data['message_type'] == MessageType.ENGINE_STATUS.value
    assert data['source_service'] == "test_engine"
    assert data['engine_id'] == "engine-123"
    assert data['correlation_id'] == corr_id
    print("✅ Full message workflow test passed")

def test_redis_constants_integration():
    """Test that constants work with schemas."""
    from shared.constants import get_redis_channel, MESSAGE_TYPES
    from shared.schemas import MessageType
    
    # Test that message types are consistent
    assert MESSAGE_TYPES['NEW_PAIR_DISCOVERED'] == MessageType.NEW_PAIR_DISCOVERED.value
    assert MESSAGE_TYPES['ENGINE_STATUS'] == MessageType.ENGINE_STATUS.value
    
    # Test channel lookup works
    channel = get_redis_channel(MESSAGE_TYPES['ENGINE_STATUS'])
    assert channel is not None
    assert 'engine_status' in channel
    print("✅ Redis constants integration test passed")

def main():
    """Run all tests."""
    print("=" * 70)
    print("SHARED MODULE UNIT TESTS")
    print("=" * 70)
    
    # Check if we're in the right directory
    if not (project_root / "manage.py").exists():
        print("❌ ERROR: Run this script from the dexproject directory (where manage.py is located)")
        return False
    
    tests = [
        test_shared_constants_import,
        test_shared_schemas_import,
        test_main_shared_import,
        test_redis_channel_lookup,
        test_redis_key_generation,
        test_ethereum_address_validation,
        test_correlation_id_generation,
        test_base_message_creation,
        test_message_serialization,
        test_message_types_enum,
        test_full_message_workflow,
        test_redis_constants_integration,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__} failed: {e}")
            failed += 1
    
    print("\n" + "=" * 70)
    print("TEST RESULTS")
    print("=" * 70)
    
    total = passed + failed
    success_rate = (passed / total) * 100 if total > 0 else 0
    
    print(f"Tests passed: {passed}/{total} ({success_rate:.1f}%)")
    
    if failed == 0:
        print("🎉 All unit tests passed!")
        print("\nYour shared module is working correctly.")
        print("You can now run your original tests with confidence.")
    else:
        print(f"❌ {failed} tests failed.")
        print("Check the error messages above for details.")
    
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)