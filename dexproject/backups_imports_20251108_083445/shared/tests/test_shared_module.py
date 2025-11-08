"""
Unit tests for the shared module.

Run with: python -m pytest shared/tests/test_shared_module.py -v

File: shared/tests/test_shared_module.py
"""

import pytest
import json
import uuid
from datetime import datetime
from typing import Dict, Any

# Test imports
def test_shared_constants_import():
    """Test that constants can be imported."""
    from shared.constants import REDIS_CHANNELS, REDIS_KEYS, MESSAGE_TYPES
    
    assert isinstance(REDIS_CHANNELS, dict)
    assert isinstance(REDIS_KEYS, dict) 
    assert isinstance(MESSAGE_TYPES, dict)
    assert len(REDIS_CHANNELS) > 0
    assert len(REDIS_KEYS) > 0
    assert len(MESSAGE_TYPES) > 0

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

def test_main_shared_import():
    """Test the main shared module import (the one that was failing)."""
    from shared import RedisClient, REDIS_CHANNELS, MessageType
    
    # RedisClient might be None if not available, but import should work
    assert REDIS_CHANNELS is not None
    assert MessageType is not None

class TestConstants:
    """Test constants module functionality."""
    
    def test_redis_channel_lookup(self):
        """Test Redis channel lookup function."""
        from shared.constants import get_redis_channel, MESSAGE_TYPES
        
        channel = get_redis_channel(MESSAGE_TYPES['NEW_PAIR_DISCOVERED'])
        assert channel is not None
        assert isinstance(channel, str)
        assert 'dex_bot' in channel
    
    def test_redis_key_generation(self):
        """Test Redis key generation."""
        from shared.constants import get_redis_key
        
        # Test key without identifier
        key = get_redis_key('risk_cache')
        assert key == 'dex_bot:risk:token'
        
        # Test key with identifier
        key_with_id = get_redis_key('risk_cache', 'test_token')
        assert key_with_id == 'dex_bot:risk:token:test_token'
    
    def test_ethereum_address_validation(self):
        """Test Ethereum address validation."""
        from shared.constants import validate_ethereum_address
        
        # Valid address
        valid_addr = '0x1234567890123456789012345678901234567890'
        assert validate_ethereum_address(valid_addr) == True
        
        # Invalid addresses
        assert validate_ethereum_address('invalid') == False
        assert validate_ethereum_address('0x123') == False  # Too short
        assert validate_ethereum_address('1234567890123456789012345678901234567890') == False  # No 0x
    
    def test_transaction_hash_validation(self):
        """Test transaction hash validation."""
        from shared.constants import validate_transaction_hash
        
        # Valid hash
        valid_hash = '0x1234567890123456789012345678901234567890123456789012345678901234'
        assert validate_transaction_hash(valid_hash) == True
        
        # Invalid hashes
        assert validate_transaction_hash('invalid') == False
        assert validate_transaction_hash('0x123') == False  # Too short

class TestSchemas:
    """Test schemas module functionality."""
    
    def test_correlation_id_generation(self):
        """Test correlation ID generation."""
        from shared.schemas import create_correlation_id
        
        corr_id = create_correlation_id()
        assert isinstance(corr_id, str)
        assert len(corr_id) > 10  # Should be a UUID string
        
        # Test uniqueness
        corr_id2 = create_correlation_id()
        assert corr_id != corr_id2
    
    def test_base_message_creation(self):
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
    
    def test_message_serialization(self):
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
    
    def test_message_deserialization(self):
        """Test message deserialization."""
        from shared.schemas import deserialize_message, BaseMessage
        
        # Test JSON data
        test_data = {
            "message_type": "engine_status",
            "timestamp": "2025-01-15T12:00:00",
            "correlation_id": "test-123",
            "source_service": "test",
            "engine_id": "engine-1"
        }
        
        json_str = json.dumps(test_data)
        result = deserialize_message(json_str)
        
        assert isinstance(result, dict)
        assert result['message_type'] == "engine_status"
        assert result['source_service'] == "test"
    
    def test_message_types_enum(self):
        """Test MessageType enum values."""
        from shared.schemas import MessageType
        
        assert MessageType.NEW_PAIR_DISCOVERED == "new_pair_discovered"
        assert MessageType.FAST_RISK_COMPLETE == "fast_risk_complete"
        assert MessageType.ENGINE_STATUS == "engine_status"
    
    def test_risk_level_enum(self):
        """Test RiskLevel enum values."""
        from shared.schemas import RiskLevel
        
        assert RiskLevel.CRITICAL == "critical"
        assert RiskLevel.HIGH == "high"
        assert RiskLevel.LOW == "low"
    
    def test_decision_type_enum(self):
        """Test DecisionType enum values."""
        from shared.schemas import DecisionType
        
        assert DecisionType.BUY == "buy"
        assert DecisionType.SELL == "sell"
        assert DecisionType.SKIP == "skip"
        assert DecisionType.HOLD == "hold"

class TestValidationHelpers:
    """Test validation helper functions."""
    
    def test_risk_score_validation(self):
        """Test risk score validation."""
        from shared.schemas import validate_risk_score
        
        # Valid scores
        assert float(validate_risk_score(50)) == 50.0
        assert float(validate_risk_score(0)) == 0.0
        assert float(validate_risk_score(100)) == 100.0
        
        # Out of range scores
        assert float(validate_risk_score(-10)) == 0.0
        assert float(validate_risk_score(150)) == 100.0
    
    def test_confidence_score_validation(self):
        """Test confidence score validation."""
        from shared.schemas import validate_confidence_score
        
        # Valid scores
        assert float(validate_confidence_score(75)) == 75.0
        assert float(validate_confidence_score(0)) == 0.0
        assert float(validate_confidence_score(100)) == 100.0
        
        # Out of range scores  
        assert float(validate_confidence_score(-5)) == 0.0
        assert float(validate_confidence_score(120)) == 100.0
    
    def test_ethereum_validation_helpers(self):
        """Test Ethereum validation helper functions."""
        from shared.schemas import validate_ethereum_address, validate_transaction_hash
        
        # Valid Ethereum address
        valid_addr = '0x1234567890123456789012345678901234567890'
        assert validate_ethereum_address(valid_addr) == True
        
        # Valid transaction hash
        valid_hash = '0x1234567890123456789012345678901234567890123456789012345678901234'
        assert validate_transaction_hash(valid_hash) == True
        
        # Invalid formats
        assert validate_ethereum_address('invalid') == False
        assert validate_transaction_hash('invalid') == False

class TestIntegration:
    """Test integration between components."""
    
    def test_full_message_workflow(self):
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
    
    def test_redis_constants_integration(self):
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

if __name__ == "__main__":
    # Run a basic test if called directly
    print("Running basic shared module tests...")
    
    try:
        test_shared_constants_import()
        print("✅ Constants import test passed")
        
        test_shared_schemas_import()
        print("✅ Schemas import test passed")
        
        test_main_shared_import()
        print("✅ Main shared import test passed")
        
        print("\n🎉 Basic tests passed! Run with pytest for full test suite:")
        print("   python -m pytest shared/tests/test_shared_module.py -v")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()