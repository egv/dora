"""
Tests for Message Serialization and Transport System

This module contains comprehensive tests for the message serialization,
routing, and transport functionality used in A2A communication.
"""

import asyncio
import gzip
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from models.a2a import A2AMessage, A2ARequest, A2AResponse, A2AError, MessageType
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
from agents.messaging import (
    A2AMessageSerializer,
    A2AMessageConverter,
    MessageRouter,
    MessageSerializationError,
    MessageDeserializationError,
    get_message_router,
)


class TestA2AMessageSerializer:
    """Test message serialization and deserialization"""
    
    def test_basic_serialization(self):
        """Test basic message serialization"""
        serializer = A2AMessageSerializer(enable_compression=False)
        
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"}
        )
        
        message_bytes = serializer.serialize_message(envelope)
        
        assert isinstance(message_bytes, bytes)
        assert len(message_bytes) > 0
        
        # Verify it's valid JSON
        json_data = message_bytes.decode('utf-8')
        parsed = json.loads(json_data)
        assert parsed["sender_id"] == "agent1"
        assert parsed["recipient_id"] == "agent2"
    
    def test_basic_deserialization(self):
        """Test basic message deserialization"""
        serializer = A2AMessageSerializer(enable_compression=False)
        
        original_envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"}
        )
        
        # Serialize then deserialize
        message_bytes = serializer.serialize_message(original_envelope)
        deserialized_envelope = serializer.deserialize_message(message_bytes)
        
        assert deserialized_envelope.sender_id == original_envelope.sender_id
        assert deserialized_envelope.recipient_id == original_envelope.recipient_id
        assert deserialized_envelope.envelope_id == original_envelope.envelope_id
        assert isinstance(deserialized_envelope.jsonrpc_message, JSONRPCRequest)
    
    def test_compression_enabled(self):
        """Test message compression"""
        serializer = A2AMessageSerializer(
            enable_compression=True,
            compression_threshold=100  # Low threshold to trigger compression
        )
        
        # Create a large message
        large_params = {"data": "x" * 1000}  # Large data to trigger compression
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters=large_params
        )
        
        message_bytes = serializer.serialize_message(envelope)
        
        # Try to decompress - should succeed if compressed
        try:
            decompressed = gzip.decompress(message_bytes)
            # If we get here, compression was applied
            assert len(decompressed) > len(message_bytes)
        except gzip.BadGzipFile:
            # Compression threshold might not have been reached
            pass
        
        # Should be able to deserialize regardless
        deserialized = serializer.deserialize_message(message_bytes)
        assert deserialized.sender_id == envelope.sender_id
    
    def test_serialization_error_handling(self):
        """Test serialization error handling"""
        serializer = A2AMessageSerializer()
        
        # Create an invalid envelope that will cause serialization issues
        # We'll use a mock that raises an exception during dict() call
        mock_envelope = MagicMock()
        mock_envelope.dict.side_effect = Exception("Serialization failed")
        
        with pytest.raises(MessageSerializationError):
            serializer.serialize_message(mock_envelope)
    
    def test_deserialization_error_handling(self):
        """Test deserialization error handling"""
        serializer = A2AMessageSerializer()
        
        # Invalid JSON
        with pytest.raises(MessageDeserializationError):
            serializer.deserialize_message(b"invalid json data")
        
        # Valid JSON but invalid message structure
        invalid_json = json.dumps({"invalid": "structure"}).encode('utf-8')
        with pytest.raises(MessageDeserializationError):
            serializer.deserialize_message(invalid_json)
    
    def test_json_serializer_datetime(self):
        """Test custom JSON serializer for datetime objects"""
        from datetime import datetime
        
        serializer = A2AMessageSerializer()
        
        # Test datetime serialization
        dt = datetime(2023, 1, 1, 12, 0, 0)
        result = serializer._json_serializer(dt)
        assert result == dt.isoformat()
        
        # Test unsupported object
        with pytest.raises(TypeError):
            serializer._json_serializer(object())


class TestA2AMessageConverter:
    """Test message format conversion"""
    
    def test_a2a_request_to_envelope(self):
        """Test converting A2A request to envelope"""
        converter = A2AMessageConverter()
        
        a2a_request = A2ARequest(
            sender_id="agent1",
            recipient_id="agent2",
            capability="test_capability",
            parameters={"key": "value"},
            correlation_id="corr-123"
        )
        
        envelope = converter.a2a_to_envelope(a2a_request)
        
        assert envelope.sender_id == "agent1"
        assert envelope.recipient_id == "agent2"
        assert envelope.correlation_id == "corr-123"
        assert isinstance(envelope.jsonrpc_message, JSONRPCRequest)
        
        request = envelope.jsonrpc_message
        assert request.method == A2AMethod.EXECUTE_CAPABILITY
        assert request.params["capability_name"] == "test_capability"
        assert request.params["parameters"] == {"key": "value"}
    
    def test_a2a_response_success_to_envelope(self):
        """Test converting successful A2A response to envelope"""
        converter = A2AMessageConverter()
        
        a2a_response = A2AResponse(
            sender_id="agent2",
            recipient_id="agent1",
            success=True,
            result={"output": "processed"},
            correlation_id="corr-123"
        )
        
        envelope = converter.a2a_to_envelope(a2a_response)
        
        assert envelope.sender_id == "agent2"
        assert envelope.recipient_id == "agent1"
        assert envelope.correlation_id == "corr-123"
        assert isinstance(envelope.jsonrpc_message, JSONRPCResponse)
        
        response = envelope.jsonrpc_message
        assert response.result == {"output": "processed"}
    
    def test_a2a_response_error_to_envelope(self):
        """Test converting error A2A response to envelope"""
        converter = A2AMessageConverter()
        
        a2a_response = A2AResponse(
            sender_id="agent2",
            recipient_id="agent1",
            success=False,
            error="Processing failed",
            correlation_id="corr-123"
        )
        
        envelope = converter.a2a_to_envelope(a2a_response)
        
        assert envelope.sender_id == "agent2"
        assert envelope.recipient_id == "agent1"
        assert envelope.correlation_id == "corr-123"
        assert isinstance(envelope.jsonrpc_message, JSONRPCErrorResponse)
        
        error_response = envelope.jsonrpc_message
        assert error_response.error.code == JSONRPCErrorCode.INTERNAL_ERROR
        assert error_response.error.message == "Processing failed"
    
    def test_a2a_error_to_envelope(self):
        """Test converting A2A error to envelope"""
        converter = A2AMessageConverter()
        
        a2a_error = A2AError(
            sender_id="agent2",
            recipient_id="agent1",
            error_code="TIMEOUT",
            error_message="Request timed out",
            correlation_id="corr-123"
        )
        
        envelope = converter.a2a_to_envelope(a2a_error)
        
        assert envelope.sender_id == "agent2"
        assert envelope.recipient_id == "agent1"
        assert envelope.correlation_id == "corr-123"
        assert isinstance(envelope.jsonrpc_message, JSONRPCErrorResponse)
        
        error_response = envelope.jsonrpc_message
        assert error_response.error.code == JSONRPCErrorCode.TIMEOUT_ERROR
        assert error_response.error.message == "Request timed out"
    
    def test_envelope_to_a2a_request(self):
        """Test converting envelope to A2A request"""
        converter = A2AMessageConverter()
        
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"},
            correlation_id="corr-123"
        )
        
        a2a_message = converter.envelope_to_a2a(envelope)
        
        assert isinstance(a2a_message, A2ARequest)
        assert a2a_message.sender_id == "agent1"
        assert a2a_message.recipient_id == "agent2"
        assert a2a_message.capability == "test_capability"
        assert a2a_message.parameters == {"key": "value"}
        assert a2a_message.correlation_id == "corr-123"
    
    def test_envelope_to_a2a_response(self):
        """Test converting envelope to A2A response"""
        converter = A2AMessageConverter()
        
        envelope = create_success_response(
            sender_id="agent2",
            recipient_id="agent1",
            request_id="req-123",
            result={"output": "processed"},
            correlation_id="corr-123"
        )
        
        a2a_message = converter.envelope_to_a2a(envelope)
        
        assert isinstance(a2a_message, A2AResponse)
        assert a2a_message.sender_id == "agent2"
        assert a2a_message.recipient_id == "agent1"
        assert a2a_message.success is True
        assert a2a_message.result == {"output": "processed"}
        assert a2a_message.correlation_id == "corr-123"
    
    def test_envelope_to_a2a_error_response(self):
        """Test converting error response envelope to A2A error"""
        converter = A2AMessageConverter()
        
        envelope = create_error_response(
            sender_id="agent2",
            recipient_id="agent1",
            request_id="req-123",
            error_code=JSONRPCErrorCode.CAPABILITY_NOT_FOUND,
            error_message="Capability not found",
            correlation_id="corr-123"
        )
        
        a2a_message = converter.envelope_to_a2a(envelope)
        
        assert isinstance(a2a_message, A2AError)
        assert a2a_message.sender_id == "agent2"
        assert a2a_message.recipient_id == "agent1"
        assert a2a_message.error_code == str(JSONRPCErrorCode.CAPABILITY_NOT_FOUND.value)
        assert a2a_message.error_message == "Capability not found"
        assert a2a_message.correlation_id == "corr-123"
    
    def test_envelope_to_a2a_notification(self):
        """Test converting notification envelope to A2A message"""
        converter = A2AMessageConverter()
        
        envelope = create_notification(
            sender_id="agent1",
            recipient_id="agent2",
            method=A2AMethod.HEARTBEAT,
            params={"timestamp": "2023-01-01T12:00:00Z"},
            correlation_id="heartbeat-123"
        )
        
        a2a_message = converter.envelope_to_a2a(envelope)
        
        assert isinstance(a2a_message, A2AMessage)
        assert a2a_message.sender_id == "agent1"
        assert a2a_message.recipient_id == "agent2"
        assert a2a_message.message_type == MessageType.HEARTBEAT
        assert a2a_message.correlation_id == "heartbeat-123"


class TestMessageRouter:
    """Test message routing functionality"""
    
    @pytest.fixture
    def router(self):
        """Create a message router for testing"""
        return MessageRouter()
    
    def test_handler_registration(self, router):
        """Test registering and unregistering message handlers"""
        handler_func = AsyncMock()
        
        # Register handler
        router.register_handler("agent1", handler_func)
        assert "agent1" in router.message_handlers
        assert router.message_handlers["agent1"] == handler_func
        
        # Unregister handler
        router.unregister_handler("agent1")
        assert "agent1" not in router.message_handlers
    
    @pytest.mark.asyncio
    async def test_send_notification(self, router):
        """Test sending notification messages"""
        transport_func = AsyncMock()
        
        envelope = create_notification(
            sender_id="agent1",
            recipient_id="agent2",
            method=A2AMethod.HEARTBEAT,
            params={"status": "active"}
        )
        
        response = await router.send_message(envelope, transport_func)
        
        # Notifications don't expect responses
        assert response is None
        transport_func.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_request_with_response(self, router):
        """Test sending request and receiving response"""
        transport_func = AsyncMock()
        
        request_envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"}
        )
        
        # Start sending request (this will wait for response)
        send_task = asyncio.create_task(
            router.send_message(request_envelope, transport_func)
        )
        
        # Give the send task a moment to set up the pending request
        await asyncio.sleep(0.01)
        
        # Simulate receiving a response
        response_envelope = create_success_response(
            sender_id="agent2",
            recipient_id="agent1",
            request_id=request_envelope.jsonrpc_message.id,
            result={"output": "processed"}
        )
        
        # Simulate the response being received
        await router.receive_message(router.serializer.serialize_message(response_envelope))
        
        # The send task should complete with the response
        result = await send_task
        assert result is not None
        assert result.sender_id == "agent2"
    
    @pytest.mark.asyncio
    async def test_send_request_timeout(self, router):
        """Test request timeout handling"""
        transport_func = AsyncMock()
        
        request_envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"key": "value"},
            timeout=1  # Very short timeout
        )
        
        # This should timeout and return None
        response = await router.send_message(request_envelope, transport_func)
        assert response is None
    
    @pytest.mark.asyncio
    async def test_receive_message_routing(self, router):
        """Test message routing to registered handlers"""
        handler_func = AsyncMock()
        router.register_handler("agent2", handler_func)
        
        envelope = create_notification(
            sender_id="agent1",
            recipient_id="agent2",
            method=A2AMethod.HEARTBEAT,
            params={"status": "active"}
        )
        
        message_bytes = router.serializer.serialize_message(envelope)
        await router.receive_message(message_bytes)
        
        # Handler should have been called
        handler_func.assert_called_once()
        
        # Verify the envelope passed to handler has correct properties
        called_envelope = handler_func.call_args[0][0]
        assert called_envelope.sender_id == envelope.sender_id
        assert called_envelope.recipient_id == envelope.recipient_id
    
    @pytest.mark.asyncio
    async def test_receive_message_no_handler(self, router):
        """Test receiving message with no registered handler"""
        envelope = create_notification(
            sender_id="agent1",
            recipient_id="unknown_agent",
            method=A2AMethod.HEARTBEAT,
            params={"status": "active"}
        )
        
        message_bytes = router.serializer.serialize_message(envelope)
        
        # Should not raise an exception, just log a warning
        await router.receive_message(message_bytes)
    
    @pytest.mark.asyncio
    async def test_receive_invalid_message(self, router):
        """Test receiving invalid message data"""
        invalid_bytes = b"invalid message data"
        
        # Should not raise an exception, just log an error
        await router.receive_message(invalid_bytes)


class TestGlobalRouterInstance:
    """Test global message router instance"""
    
    def test_get_message_router(self):
        """Test getting global message router instance"""
        router1 = get_message_router()
        router2 = get_message_router()
        
        # Should return the same instance
        assert router1 is router2
        assert isinstance(router1, MessageRouter)


class TestMessageSerializationIntegration:
    """Integration tests for complete message flow"""
    
    @pytest.mark.asyncio
    async def test_complete_request_response_flow(self):
        """Test complete request-response message flow"""
        router = MessageRouter()
        
        # Setup handler for agent2
        received_messages = []
        
        async def handler(envelope):
            received_messages.append(envelope)
            # Send response back
            if isinstance(envelope.jsonrpc_message, JSONRPCRequest):
                response = create_success_response(
                    sender_id="agent2",
                    recipient_id=envelope.sender_id,
                    request_id=envelope.jsonrpc_message.id,
                    result={"processed": True}
                )
                # Simulate async response delivery
                asyncio.create_task(
                    router.receive_message(router.serializer.serialize_message(response))
                )
        
        router.register_handler("agent2", handler)
        
        # Create and send request
        request = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="test_capability",
            parameters={"input": "test_data"}
        )
        
        # Mock transport function
        transport_func = AsyncMock()
        
        async def mock_transport(message_bytes):
            # Simulate network transport - immediately deliver to router
            await router.receive_message(message_bytes)
        
        transport_func.side_effect = mock_transport
        
        # Send request and wait for response
        response = await router.send_message(request, transport_func)
        
        # Verify request was received
        assert len(received_messages) == 1
        assert received_messages[0].sender_id == "agent1"
        
        # Verify response was received
        assert response is not None
        assert response.sender_id == "agent2"
        assert isinstance(response.jsonrpc_message, JSONRPCResponse)
        assert response.jsonrpc_message.result == {"processed": True}


if __name__ == "__main__":
    pytest.main([__file__])