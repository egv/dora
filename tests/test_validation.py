"""
Tests for Message Validation System

This module contains comprehensive tests for the message validation
functionality including security checks, rate limiting, and schema validation.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from models.a2a import Capability, CapabilityType
from models.jsonrpc import (
    A2AMessageEnvelope,
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCErrorResponse,
    JSONRPCNotification,
    JSONRPCError,
    JSONRPCErrorCode,
    A2AMethod,
    create_capability_request,
    create_success_response,
    create_error_response,
    create_notification,
)
from models.validation import (
    ValidationResult,
    MessageValidator,
    CapabilityValidator,
    get_message_validator,
    get_capability_validator,
    validate_message,
    validate_capability_result,
)


class TestValidationResult:
    """Test ValidationResult class"""
    
    def test_valid_result(self):
        """Test creating a valid result"""
        result = ValidationResult()
        
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
        assert bool(result) is True
        assert str(result) == "Valid"
    
    def test_result_with_warnings(self):
        """Test result with warnings"""
        result = ValidationResult()
        result.add_warning("This is a warning")
        result.add_warning("Another warning")
        
        assert result.is_valid is True
        assert len(result.warnings) == 2
        assert bool(result) is True
        assert str(result) == "Valid (2 warnings)"
    
    def test_invalid_result(self):
        """Test invalid result with errors"""
        result = ValidationResult()
        result.add_error("This is an error")
        result.add_error("Another error")
        
        assert result.is_valid is False
        assert len(result.errors) == 2
        assert bool(result) is False
        assert str(result) == "Invalid: This is an error; Another error"
    
    def test_result_with_errors_and_warnings(self):
        """Test result with both errors and warnings"""
        result = ValidationResult(is_valid=False, errors=["Error 1"], warnings=["Warning 1"])
        result.add_error("Error 2")
        result.add_warning("Warning 2")
        
        assert result.is_valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 2
        assert bool(result) is False


class TestMessageValidator:
    """Test MessageValidator class"""
    
    @pytest.fixture
    def validator(self):
        """Create a message validator for testing"""
        return MessageValidator()
    
    def test_valid_envelope(self, validator):
        """Test validation of a valid message envelope"""
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"}
        )
        
        result = validator.validate_envelope(envelope)
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_missing_sender_id(self, validator):
        """Test validation with missing sender_id"""
        envelope = create_capability_request(
            sender_id="",  # Empty sender_id
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"}
        )
        
        result = validator.validate_envelope(envelope)
        assert result.is_valid is False
        assert any("sender_id is required" in error for error in result.errors)
    
    def test_missing_recipient_id(self, validator):
        """Test validation with missing recipient_id"""
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="",  # Empty recipient_id
            capability_name="test_capability",
            parameters={"key": "value"}
        )
        
        result = validator.validate_envelope(envelope)
        assert result.is_valid is False
        assert any("recipient_id is required" in error for error in result.errors)
    
    def test_invalid_agent_id_format(self, validator):
        """Test validation with invalid agent ID format"""
        envelope = create_capability_request(
            sender_id="agent@invalid!",  # Invalid characters
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"}
        )
        
        result = validator.validate_envelope(envelope)
        assert result.is_valid is False
        assert any("Invalid sender_id format" in error for error in result.errors)
    
    def test_ttl_validation(self, validator):
        """Test TTL validation"""
        # Valid envelope first
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"}
        )
        
        # TTL too small - manually set after creation
        envelope.ttl = 0  # Below minimum
        result = validator.validate_envelope(envelope)
        assert result.is_valid is False
        assert any("TTL too small" in error for error in result.errors)
        
        # TTL too large
        envelope.ttl = 7200  # Above maximum
        result = validator.validate_envelope(envelope)
        assert result.is_valid is False
        assert any("TTL too large" in error for error in result.errors)
    
    def test_priority_validation(self, validator):
        """Test priority validation"""
        # Valid envelope first
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"}
        )
        
        # Priority too low - manually set after creation
        envelope.priority = 0  # Below minimum
        result = validator.validate_envelope(envelope)
        assert result.is_valid is False
        assert any("Priority out of range" in error for error in result.errors)
        
        # Priority too high
        envelope.priority = 11  # Above maximum
        result = validator.validate_envelope(envelope)
        assert result.is_valid is False
        assert any("Priority out of range" in error for error in result.errors)
    
    def test_self_messaging_warning(self, validator):
        """Test warning for self-messaging"""
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent1",  # Same as sender
            capability_name="test_capability",
            parameters={"key": "value"}
        )
        
        result = validator.validate_envelope(envelope)
        assert result.is_valid is True
        assert any("Agent sending message to itself" in warning for warning in result.warnings)
    
    def test_unsupported_protocol_version_warning(self, validator):
        """Test warning for unsupported protocol version"""
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"}
        )
        envelope.protocol_version = "2.0"  # Unsupported version
        
        result = validator.validate_envelope(envelope)
        assert result.is_valid is True
        assert any("Unsupported protocol version" in warning for warning in result.warnings)
    
    def test_expired_message(self, validator):
        """Test validation of expired messages"""
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"},
            timeout=60
        )
        
        # Set timestamp to past
        envelope.timestamp = datetime.utcnow() - timedelta(seconds=120)
        
        result = validator.validate_envelope(envelope)
        assert result.is_valid is False
        assert any("Message expired" in error for error in result.errors)
    
    def test_invalid_correlation_id_format(self, validator):
        """Test validation of correlation ID format"""
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"}
        )
        envelope.correlation_id = "invalid@correlation!"  # Invalid characters
        
        result = validator.validate_envelope(envelope)
        assert result.is_valid is False
        assert any("Invalid correlation_id format" in error for error in result.errors)
    
    def test_jsonrpc_version_validation(self, validator):
        """Test JSON-RPC version validation"""
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"}
        )
        
        # Manually set invalid JSON-RPC version
        envelope.jsonrpc_message.jsonrpc = "1.0"  # Invalid version
        
        result = validator.validate_envelope(envelope)
        assert result.is_valid is False
        assert any("Invalid JSON-RPC version" in error for error in result.errors)
    
    def test_jsonrpc_request_validation(self, validator):
        """Test JSON-RPC request specific validation"""
        # Test reserved method name
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"}
        )
        envelope.jsonrpc_message.method = "rpc.reserved"  # Reserved method
        
        result = validator.validate_envelope(envelope)
        assert result.is_valid is False
        assert any("Method names starting with 'rpc.' are reserved" in error for error in result.errors)
    
    def test_jsonrpc_error_response_validation(self, validator):
        """Test JSON-RPC error response validation"""
        # Valid error response
        envelope = create_error_response(
            sender_id="agent1",
            recipient_id="agent2",
            request_id="req-123",
            error_code=JSONRPCErrorCode.INTERNAL_ERROR,
            error_message="Test error"
        )
        
        result = validator.validate_envelope(envelope)
        assert result.is_valid is True
        
        # Error with code 0 (invalid)
        envelope.jsonrpc_message.error.code = 0
        result = validator.validate_envelope(envelope)
        assert result.is_valid is False
        assert any("Error code cannot be 0" in error for error in result.errors)
    
    def test_capability_registration(self, validator):
        """Test capability registration for validation"""
        capability = Capability(
            name="test_capability",
            description="Test capability",
            capability_type=CapabilityType.DATA_COLLECTION,
            input_schema={
                "type": "object",
                "properties": {
                    "input": {"type": "string"}
                },
                "required": ["input"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "output": {"type": "string"}
                }
            }
        )
        
        validator.register_capability(capability)
        assert "test_capability" in validator._capability_schemas
        
        validator.unregister_capability("test_capability")
        assert "test_capability" not in validator._capability_schemas
    
    def test_capability_payload_validation(self, validator):
        """Test validation of capability parameters against schema"""
        # Register capability with schema
        capability = Capability(
            name="test_capability",
            description="Test capability",
            capability_type=CapabilityType.DATA_COLLECTION,
            input_schema={
                "type": "object",
                "properties": {
                    "input": {"type": "string"},
                    "count": {"type": "integer", "minimum": 0}
                },
                "required": ["input"]
            },
            output_schema={"type": "object"}
        )
        
        validator.register_capability(capability)
        
        # Valid parameters
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"input": "test", "count": 5}
        )
        
        result = validator.validate_envelope(envelope)
        assert result.is_valid is True
        
        # Invalid parameters - missing required field
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"count": 5}  # Missing required "input"
        )
        
        result = validator.validate_envelope(envelope)
        assert result.is_valid is False
        assert any("Capability parameter validation failed" in error for error in result.errors)
        
        # Invalid parameters - wrong type
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"input": "test", "count": -1}  # Negative count
        )
        
        result = validator.validate_envelope(envelope)
        assert result.is_valid is False
        assert any("Capability parameter validation failed" in error for error in result.errors)
    
    def test_rate_limiting(self, validator):
        """Test rate limiting validation"""
        # Send messages rapidly from same agent
        for i in range(5):
            envelope = create_capability_request(
                sender_id="agent1",
                recipient_id="agent2",
                capability_name="test_capability",
                parameters={"key": f"value{i}"}
            )
            
            result = validator.validate_envelope(envelope)
            # First few should be valid
            if i < 3:
                assert result.is_valid is True
    
    def test_payload_depth_validation(self, validator):
        """Test payload depth validation"""
        # Create deeply nested payload
        deep_payload = {"level": 1}
        current = deep_payload
        for i in range(15):  # Create very deep nesting
            current["nested"] = {"level": i + 2}
            current = current["nested"]
        
        valid = validator.validate_payload_depth(deep_payload, max_depth=10)
        assert valid is False
        
        # Shallow payload should be valid
        shallow_payload = {"key": "value", "nested": {"inner": "data"}}
        valid = validator.validate_payload_depth(shallow_payload, max_depth=10)
        assert valid is True
    
    def test_message_size_validation(self, validator):
        """Test message size validation"""
        # Small message should be valid
        small_message = b"small message"
        valid = validator.validate_message_size(small_message)
        assert valid is True
        
        # Large message should be invalid
        large_message = b"x" * (11 * 1024 * 1024)  # 11MB
        valid = validator.validate_message_size(large_message)
        assert valid is False
    
    def test_validation_stats(self, validator):
        """Test validation statistics"""
        # Register a capability
        capability = Capability(
            name="test_capability",
            description="Test capability",
            capability_type=CapabilityType.DATA_COLLECTION,
            input_schema={"type": "object"},
            output_schema={"type": "object"}
        )
        validator.register_capability(capability)
        
        # Validate a message to add to agent tracking
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"}
        )
        validator.validate_envelope(envelope)
        
        stats = validator.get_validation_stats()
        
        assert stats["registered_capabilities"] == 1
        assert stats["tracked_agents"] >= 1
        assert "rate_limit_window" in stats
        assert "max_message_size" in stats


class TestCapabilityValidator:
    """Test CapabilityValidator class"""
    
    @pytest.fixture
    def validator(self):
        """Create a capability validator for testing"""
        return CapabilityValidator()
    
    def test_valid_capability_result(self, validator):
        """Test validation of valid capability result"""
        capability = Capability(
            name="test_capability",
            description="Test capability",
            capability_type=CapabilityType.DATA_COLLECTION,
            input_schema={"type": "object"},
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "string"},
                    "count": {"type": "integer"}
                },
                "required": ["result"]
            }
        )
        
        # Valid result
        result = {"result": "success", "count": 42}
        validation_result = validator.validate_capability_result(capability, result)
        
        assert validation_result.is_valid is True
        assert len(validation_result.errors) == 0
    
    def test_invalid_capability_result(self, validator):
        """Test validation of invalid capability result"""
        capability = Capability(
            name="test_capability",
            description="Test capability",
            capability_type=CapabilityType.DATA_COLLECTION,
            input_schema={"type": "object"},
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "string"},
                    "count": {"type": "integer"}
                },
                "required": ["result"]
            }
        )
        
        # Invalid result - missing required field
        result = {"count": 42}  # Missing "result"
        validation_result = validator.validate_capability_result(capability, result)
        
        assert validation_result.is_valid is False
        assert any("Result validation failed" in error for error in validation_result.errors)
        
        # Invalid result - wrong type
        result = {"result": 123, "count": 42}  # result should be string
        validation_result = validator.validate_capability_result(capability, result)
        
        assert validation_result.is_valid is False
        assert any("Result validation failed" in error for error in validation_result.errors)
    
    def test_invalid_output_schema(self, validator):
        """Test handling of invalid output schema"""
        capability = Capability(
            name="test_capability",
            description="Test capability",
            capability_type=CapabilityType.DATA_COLLECTION,
            input_schema={"type": "object"},
            output_schema={"invalid": "schema"}  # Invalid JSON schema
        )
        
        result = {"any": "data"}
        validation_result = validator.validate_capability_result(capability, result)
        
        assert validation_result.is_valid is False
        assert any("Invalid output schema" in error for error in validation_result.errors)


class TestGlobalValidatorFunctions:
    """Test global validator functions and instances"""
    
    def test_get_message_validator(self):
        """Test getting global message validator instance"""
        validator1 = get_message_validator()
        validator2 = get_message_validator()
        
        # Should return the same instance
        assert validator1 is validator2
        assert isinstance(validator1, MessageValidator)
    
    def test_get_capability_validator(self):
        """Test getting global capability validator instance"""
        validator1 = get_capability_validator()
        validator2 = get_capability_validator()
        
        # Should return the same instance
        assert validator1 is validator2
        assert isinstance(validator1, CapabilityValidator)
    
    def test_validate_message_function(self):
        """Test global validate_message function"""
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"}
        )
        
        result = validate_message(envelope)
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
    
    def test_validate_capability_result_function(self):
        """Test global validate_capability_result function"""
        capability = Capability(
            name="test_capability",
            description="Test capability",
            capability_type=CapabilityType.DATA_COLLECTION,
            input_schema={"type": "object"},
            output_schema={
                "type": "object",
                "properties": {
                    "output": {"type": "string"}
                }
            }
        )
        
        result = {"output": "success"}
        validation_result = validate_capability_result(capability, result)
        
        assert isinstance(validation_result, ValidationResult)
        assert validation_result.is_valid is True


class TestValidationIntegration:
    """Integration tests for validation system"""
    
    def test_complete_validation_flow(self):
        """Test complete validation flow with capability registration"""
        validator = MessageValidator()
        
        # Register capability
        capability = Capability(
            name="text_processor",
            description="Process text data",
            capability_type=CapabilityType.DATA_COLLECTION,
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "minLength": 1},
                    "operation": {"type": "string", "enum": ["uppercase", "lowercase"]}
                },
                "required": ["text", "operation"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "processed_text": {"type": "string"},
                    "original_length": {"type": "integer"}
                },
                "required": ["processed_text"]
            }
        )
        
        validator.register_capability(capability)
        
        # Test valid request
        envelope = create_capability_request(
            sender_id="client_agent",
            recipient_id="processor_agent",
            capability_name="text_processor",
            parameters={"text": "Hello World", "operation": "uppercase"}
        )
        
        result = validator.validate_envelope(envelope)
        assert result.is_valid is True
        
        # Test invalid request - missing required parameter
        envelope = create_capability_request(
            sender_id="client_agent",
            recipient_id="processor_agent",
            capability_name="text_processor",
            parameters={"text": "Hello World"}  # Missing "operation"
        )
        
        result = validator.validate_envelope(envelope)
        assert result.is_valid is False
        assert any("Capability parameter validation failed" in error for error in result.errors)
        
        # Test capability result validation
        cap_validator = CapabilityValidator()
        
        # Valid result
        valid_result = {"processed_text": "HELLO WORLD", "original_length": 11}
        result = cap_validator.validate_capability_result(capability, valid_result)
        assert result.is_valid is True
        
        # Invalid result
        invalid_result = {"original_length": 11}  # Missing required "processed_text"
        result = cap_validator.validate_capability_result(capability, invalid_result)
        assert result.is_valid is False


if __name__ == "__main__":
    pytest.main([__file__])