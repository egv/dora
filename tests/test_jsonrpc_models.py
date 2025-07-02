"""
Tests for JSON-RPC 2.0 Message Models

This module contains comprehensive tests for the JSON-RPC message models
and helper functions used in A2A communication.
"""

import pytest
from datetime import datetime
from uuid import uuid4

from models.jsonrpc import (
    JSONRPCVersion,
    JSONRPCErrorCode,
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCNotification,
    JSONRPCResponse,
    JSONRPCErrorResponse,
    JSONRPCBatch,
    A2AMessageEnvelope,
    A2AMethod,
    A2ACapabilityExecuteParams,
    A2ADiscoverAgentsParams,
    A2ATaskParams,
    create_capability_request,
    create_success_response,
    create_error_response,
    create_notification,
)


class TestJSONRPCError:
    """Test JSON-RPC error object"""
    
    def test_valid_error(self):
        """Test creating a valid error object"""
        error = JSONRPCError(
            code=-32603,
            message="Internal error",
            data={"details": "Something went wrong"}
        )
        
        assert error.code == -32603
        assert error.message == "Internal error"
        assert error.data == {"details": "Something went wrong"}
    
    def test_error_without_data(self):
        """Test creating error without data field"""
        error = JSONRPCError(
            code=-32602,
            message="Invalid params"
        )
        
        assert error.code == -32602
        assert error.message == "Invalid params"
        assert error.data is None
    
    def test_zero_error_code_validation(self):
        """Test that error code cannot be zero"""
        with pytest.raises(ValueError, match="Error code cannot be 0"):
            JSONRPCError(code=0, message="Invalid")


class TestJSONRPCRequest:
    """Test JSON-RPC request message"""
    
    def test_valid_request(self):
        """Test creating a valid request"""
        request = JSONRPCRequest(
            method="a2a.capability.execute",
            params={"capability_name": "test", "parameters": {"key": "value"}},
            id="test-123"
        )
        
        assert request.jsonrpc == JSONRPCVersion.V2_0
        assert request.method == "a2a.capability.execute"
        assert request.params == {"capability_name": "test", "parameters": {"key": "value"}}
        assert request.id == "test-123"
    
    def test_request_with_default_id(self):
        """Test request with auto-generated ID"""
        request = JSONRPCRequest(method="test.method")
        
        assert request.id is not None
        assert isinstance(request.id, str)
        assert len(request.id) > 0
    
    def test_request_without_params(self):
        """Test request without parameters"""
        request = JSONRPCRequest(method="test.method", id="123")
        
        assert request.params is None
    
    def test_invalid_method_name(self):
        """Test validation of method names"""
        # Empty method name
        with pytest.raises(ValueError, match="Method name must be a non-empty string"):
            JSONRPCRequest(method="")
        
        # Reserved method name
        with pytest.raises(ValueError, match="Method names starting with 'rpc.' are reserved"):
            JSONRPCRequest(method="rpc.test")


class TestJSONRPCNotification:
    """Test JSON-RPC notification message"""
    
    def test_valid_notification(self):
        """Test creating a valid notification"""
        notification = JSONRPCNotification(
            method="a2a.agent.heartbeat",
            params={"timestamp": "2023-01-01T00:00:00Z"}
        )
        
        assert notification.jsonrpc == JSONRPCVersion.V2_0
        assert notification.method == "a2a.agent.heartbeat"
        assert notification.params == {"timestamp": "2023-01-01T00:00:00Z"}
    
    def test_notification_without_params(self):
        """Test notification without parameters"""
        notification = JSONRPCNotification(method="test.notify")
        
        assert notification.params is None
    
    def test_invalid_notification_method(self):
        """Test validation of notification method names"""
        with pytest.raises(ValueError, match="Method names starting with 'rpc.' are reserved"):
            JSONRPCNotification(method="rpc.internal")


class TestJSONRPCResponse:
    """Test JSON-RPC response message"""
    
    def test_valid_response(self):
        """Test creating a valid response"""
        response = JSONRPCResponse(
            result={"status": "success", "data": [1, 2, 3]},
            id="request-123"
        )
        
        assert response.jsonrpc == JSONRPCVersion.V2_0
        assert response.result == {"status": "success", "data": [1, 2, 3]}
        assert response.id == "request-123"
    
    def test_response_with_null_result(self):
        """Test response with null result"""
        response = JSONRPCResponse(result=None, id="request-456")
        
        assert response.result is None
        assert response.id == "request-456"


class TestJSONRPCErrorResponse:
    """Test JSON-RPC error response message"""
    
    def test_valid_error_response(self):
        """Test creating a valid error response"""
        error = JSONRPCError(code=-32601, message="Method not found")
        response = JSONRPCErrorResponse(error=error, id="request-789")
        
        assert response.jsonrpc == JSONRPCVersion.V2_0
        assert response.error == error
        assert response.id == "request-789"
    
    def test_error_response_with_null_id(self):
        """Test error response with null ID (parse error)"""
        error = JSONRPCError(code=-32700, message="Parse error")
        response = JSONRPCErrorResponse(error=error, id=None)
        
        assert response.id is None


class TestJSONRPCBatch:
    """Test JSON-RPC batch request"""
    
    def test_valid_batch(self):
        """Test creating a valid batch request"""
        request1 = JSONRPCRequest(method="test.method1", id="1")
        request2 = JSONRPCRequest(method="test.method2", id="2")
        notification = JSONRPCNotification(method="test.notify")
        
        batch = JSONRPCBatch(requests=[request1, request2, notification])
        
        assert len(batch.requests) == 3
        assert batch.requests[0] == request1
        assert batch.requests[1] == request2
        assert batch.requests[2] == notification
    
    def test_empty_batch_validation(self):
        """Test that empty batch is not allowed"""
        with pytest.raises(ValueError, match="Batch must contain at least one request"):
            JSONRPCBatch(requests=[])


class TestA2AMessageEnvelope:
    """Test A2A message envelope"""
    
    def test_valid_envelope(self):
        """Test creating a valid message envelope"""
        request = JSONRPCRequest(method="test.method", id="123")
        envelope = A2AMessageEnvelope(
            sender_id="agent1",
            recipient_id="agent2",
            jsonrpc_message=request,
            correlation_id="corr-123",
            ttl=300,
            priority=3
        )
        
        assert envelope.sender_id == "agent1"
        assert envelope.recipient_id == "agent2"
        assert envelope.jsonrpc_message == request
        assert envelope.correlation_id == "corr-123"
        assert envelope.ttl == 300
        assert envelope.priority == 3
        assert envelope.protocol_version == "1.0"
        assert isinstance(envelope.timestamp, datetime)
        assert isinstance(envelope.envelope_id, str)
    
    def test_envelope_with_defaults(self):
        """Test envelope with default values"""
        request = JSONRPCRequest(method="test.method")
        envelope = A2AMessageEnvelope(
            sender_id="agent1",
            recipient_id="agent2",
            jsonrpc_message=request
        )
        
        assert envelope.ttl == 60
        assert envelope.priority == 5
        assert envelope.correlation_id is None
        assert envelope.reply_to is None
        assert envelope.compression is None
        assert envelope.encryption is None
    
    def test_invalid_priority_validation(self):
        """Test priority validation"""
        request = JSONRPCRequest(method="test.method")
        
        # Priority too low
        with pytest.raises(ValueError, match="Priority must be between 1"):
            A2AMessageEnvelope(
                sender_id="agent1",
                recipient_id="agent2",
                jsonrpc_message=request,
                priority=0
            )
        
        # Priority too high
        with pytest.raises(ValueError, match="Priority must be between 1"):
            A2AMessageEnvelope(
                sender_id="agent1",
                recipient_id="agent2",
                jsonrpc_message=request,
                priority=11
            )
    
    def test_invalid_ttl_validation(self):
        """Test TTL validation"""
        request = JSONRPCRequest(method="test.method")
        
        with pytest.raises(ValueError, match="TTL must be positive"):
            A2AMessageEnvelope(
                sender_id="agent1",
                recipient_id="agent2",
                jsonrpc_message=request,
                ttl=0
            )


class TestA2AParameterModels:
    """Test A2A parameter models"""
    
    def test_capability_execute_params(self):
        """Test capability execution parameters"""
        params = A2ACapabilityExecuteParams(
            capability_name="data_processing",
            parameters={"input": "test_data", "format": "json"},
            timeout=120,
            priority=3
        )
        
        assert params.capability_name == "data_processing"
        assert params.parameters == {"input": "test_data", "format": "json"}
        assert params.timeout == 120
        assert params.priority == 3
    
    def test_discover_agents_params(self):
        """Test agent discovery parameters"""
        params = A2ADiscoverAgentsParams(
            capability_name="text_analysis",
            capability_type="nlp",
            status="active",
            exclude_agents=["agent1", "agent2"],
            max_results=5
        )
        
        assert params.capability_name == "text_analysis"
        assert params.capability_type == "nlp"
        assert params.status == "active"
        assert params.exclude_agents == ["agent1", "agent2"]
        assert params.max_results == 5
    
    def test_task_params(self):
        """Test task parameters"""
        params = A2ATaskParams(
            task_id="task-123",
            capability="image_processing",
            parameters={"format": "png", "quality": 95},
            timeout=600
        )
        
        assert params.task_id == "task-123"
        assert params.capability == "image_processing"
        assert params.parameters == {"format": "png", "quality": 95}
        assert params.timeout == 600


class TestHelperFunctions:
    """Test helper functions for creating messages"""
    
    def test_create_capability_request(self):
        """Test creating capability execution request"""
        envelope = create_capability_request(
            sender_id="agent1",
            recipient_id="agent2",
            capability_name="text_processing",
            parameters={"text": "hello world", "lang": "en"},
            correlation_id="corr-456",
            timeout=180,
            priority=2
        )
        
        assert envelope.sender_id == "agent1"
        assert envelope.recipient_id == "agent2"
        assert envelope.correlation_id == "corr-456"
        assert envelope.ttl == 180
        assert envelope.priority == 2
        
        assert isinstance(envelope.jsonrpc_message, JSONRPCRequest)
        request = envelope.jsonrpc_message
        assert request.method == A2AMethod.EXECUTE_CAPABILITY
        assert request.params["capability_name"] == "text_processing"
        assert request.params["parameters"] == {"text": "hello world", "lang": "en"}
        assert request.params["timeout"] == 180
        assert request.params["priority"] == 2
    
    def test_create_success_response(self):
        """Test creating success response"""
        result_data = {"processed_text": "HELLO WORLD", "word_count": 2}
        envelope = create_success_response(
            sender_id="agent2",
            recipient_id="agent1",
            request_id="req-123",
            result=result_data,
            correlation_id="corr-456"
        )
        
        assert envelope.sender_id == "agent2"
        assert envelope.recipient_id == "agent1"
        assert envelope.correlation_id == "corr-456"
        
        assert isinstance(envelope.jsonrpc_message, JSONRPCResponse)
        response = envelope.jsonrpc_message
        assert response.result == result_data
        assert response.id == "req-123"
    
    def test_create_error_response(self):
        """Test creating error response"""
        envelope = create_error_response(
            sender_id="agent2",
            recipient_id="agent1",
            request_id="req-456",
            error_code=JSONRPCErrorCode.CAPABILITY_NOT_FOUND,
            error_message="Capability 'unknown_capability' not found",
            error_data={"available_capabilities": ["text_processing", "image_analysis"]},
            correlation_id="corr-789"
        )
        
        assert envelope.sender_id == "agent2"
        assert envelope.recipient_id == "agent1"
        assert envelope.correlation_id == "corr-789"
        
        assert isinstance(envelope.jsonrpc_message, JSONRPCErrorResponse)
        error_response = envelope.jsonrpc_message
        assert error_response.id == "req-456"
        assert error_response.error.code == JSONRPCErrorCode.CAPABILITY_NOT_FOUND
        assert error_response.error.message == "Capability 'unknown_capability' not found"
        assert error_response.error.data == {"available_capabilities": ["text_processing", "image_analysis"]}
    
    def test_create_notification(self):
        """Test creating notification"""
        envelope = create_notification(
            sender_id="agent1",
            recipient_id="agent2",
            method=A2AMethod.HEARTBEAT,
            params={"timestamp": "2023-01-01T12:00:00Z", "status": "active"},
            correlation_id="heartbeat-123"
        )
        
        assert envelope.sender_id == "agent1"
        assert envelope.recipient_id == "agent2"
        assert envelope.correlation_id == "heartbeat-123"
        
        assert isinstance(envelope.jsonrpc_message, JSONRPCNotification)
        notification = envelope.jsonrpc_message
        assert notification.method == A2AMethod.HEARTBEAT
        assert notification.params == {"timestamp": "2023-01-01T12:00:00Z", "status": "active"}


class TestA2AMethodEnum:
    """Test A2A method enumeration"""
    
    def test_all_methods_defined(self):
        """Test that all expected A2A methods are defined"""
        expected_methods = [
            "a2a.capability.execute",
            "a2a.capability.list", 
            "a2a.capability.info",
            "a2a.agent.info",
            "a2a.agent.status",
            "a2a.agent.heartbeat",
            "a2a.discovery.agents",
            "a2a.discovery.capabilities",
            "a2a.task.create",
            "a2a.task.status",
            "a2a.task.cancel",
            "a2a.notify.task_status_changed",
            "a2a.notify.agent_status_changed",
            "a2a.notify.capability_updated"
        ]
        
        for method in expected_methods:
            assert method in A2AMethod.__members__.values()
    
    def test_method_values(self):
        """Test specific method values"""
        assert A2AMethod.EXECUTE_CAPABILITY == "a2a.capability.execute"
        assert A2AMethod.HEARTBEAT == "a2a.agent.heartbeat"
        assert A2AMethod.DISCOVER_AGENTS == "a2a.discovery.agents"


class TestJSONRPCErrorCodes:
    """Test JSON-RPC error code enumeration"""
    
    def test_standard_error_codes(self):
        """Test standard JSON-RPC error codes"""
        assert JSONRPCErrorCode.PARSE_ERROR == -32700
        assert JSONRPCErrorCode.INVALID_REQUEST == -32600
        assert JSONRPCErrorCode.METHOD_NOT_FOUND == -32601
        assert JSONRPCErrorCode.INVALID_PARAMS == -32602
        assert JSONRPCErrorCode.INTERNAL_ERROR == -32603
    
    def test_custom_a2a_error_codes(self):
        """Test custom A2A error codes"""
        assert JSONRPCErrorCode.AGENT_NOT_FOUND == -32001
        assert JSONRPCErrorCode.CAPABILITY_NOT_FOUND == -32002
        assert JSONRPCErrorCode.TIMEOUT_ERROR == -32004
        assert JSONRPCErrorCode.VALIDATION_ERROR == -32009


if __name__ == "__main__":
    pytest.main([__file__])