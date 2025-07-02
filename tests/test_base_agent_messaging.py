"""
Tests for Base Agent JSON-RPC Message Handling

This module contains comprehensive tests for the JSON-RPC message handling
functionality in the base agent class.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from agents.base import BaseAgent
from models.a2a import Capability, CapabilityType, AgentStatus
from models.jsonrpc import (
    A2AMessageEnvelope,
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCErrorResponse,
    JSONRPCNotification,
    JSONRPCErrorCode,
    A2AMethod,
    create_capability_request,
    create_success_response,
    create_error_response,
    create_notification,
)


class TestAgent(BaseAgent):
    """Test agent implementation for testing"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initialized = False
        self.cleaned_up = False
        self.executed_capabilities = []
    
    async def _initialize(self):
        """Test implementation of agent initialization"""
        self.initialized = True
    
    async def _cleanup(self):
        """Test implementation of agent cleanup"""
        self.cleaned_up = True
    
    async def _execute_capability_impl(self, capability_name: str, parameters: dict) -> dict:
        """Test implementation of capability execution"""
        self.executed_capabilities.append((capability_name, parameters))
        
        if capability_name == "test_capability":
            return {"result": "success", "input": parameters}
        elif capability_name == "error_capability":
            raise ValueError("Test error from capability")
        elif capability_name == "slow_capability":
            await asyncio.sleep(0.1)
            return {"result": "slow_success"}
        else:
            raise ValueError(f"Unknown capability: {capability_name}")


class TestBaseAgentMessaging:
    """Test base agent JSON-RPC message handling"""
    
    @pytest.fixture
    async def agent(self):
        """Create a test agent"""
        agent = TestAgent(
            agent_id="test_agent",
            name="Test Agent",
            description="Agent for testing",
            version="1.0.0"
        )
        
        # Register test capabilities
        test_capability = Capability(
            name="test_capability",
            description="Test capability",
            capability_type=CapabilityType.DATA_COLLECTION,
            input_schema={
                "type": "object",
                "properties": {
                    "input": {"type": "string"}
                }
            },
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "string"}
                }
            }
        )
        
        error_capability = Capability(
            name="error_capability",
            description="Capability that throws errors",
            capability_type=CapabilityType.DATA_COLLECTION,
            input_schema={"type": "object"},
            output_schema={"type": "object"}
        )
        
        slow_capability = Capability(
            name="slow_capability",
            description="Slow capability for testing timeouts",
            capability_type=CapabilityType.DATA_COLLECTION,
            input_schema={"type": "object"},
            output_schema={"type": "object"}
        )
        
        agent.register_capability(test_capability)
        agent.register_capability(error_capability)
        agent.register_capability(slow_capability)
        
        # Mock the discovery and A2A setup to avoid external dependencies
        with patch.object(agent, '_setup_discovery', new_callable=AsyncMock), \
             patch.object(agent, '_cleanup_discovery', new_callable=AsyncMock), \
             patch.object(agent, '_setup_a2a', new_callable=AsyncMock):
            
            await agent.start()
            yield agent
            await agent.stop()
    
    @pytest.mark.asyncio
    async def test_capability_execution_request_success(self, agent):
        """Test successful capability execution request"""
        envelope = create_capability_request(
            sender_id="client_agent",
            recipient_id="test_agent",
            capability_name="test_capability",
            parameters={"input": "test_data"}
        )
        
        # Mock send_message to capture the response
        sent_messages = []
        
        async def mock_send_message(response_envelope):
            sent_messages.append(response_envelope)
        
        agent.send_message = mock_send_message
        
        # Handle the incoming request
        await agent._handle_incoming_message(envelope)
        
        # Verify capability was executed
        assert len(agent.executed_capabilities) == 1
        assert agent.executed_capabilities[0] == ("test_capability", {"input": "test_data"})
        
        # Verify response was sent
        assert len(sent_messages) == 1
        response_envelope = sent_messages[0]
        assert response_envelope.sender_id == "test_agent"
        assert response_envelope.recipient_id == "client_agent"
        assert isinstance(response_envelope.jsonrpc_message, JSONRPCResponse)
        
        response = response_envelope.jsonrpc_message
        assert response.result == {"result": "success", "input": {"input": "test_data"}}
    
    @pytest.mark.asyncio
    async def test_capability_execution_request_capability_not_found(self, agent):
        """Test capability execution request for unknown capability"""
        envelope = create_capability_request(
            sender_id="client_agent",
            recipient_id="test_agent",
            capability_name="unknown_capability",
            parameters={"input": "test_data"}
        )
        
        sent_messages = []
        agent.send_message = AsyncMock(side_effect=lambda env: sent_messages.append(env))
        
        await agent._handle_incoming_message(envelope)
        
        # Verify error response was sent
        assert len(sent_messages) == 1
        response_envelope = sent_messages[0]
        assert isinstance(response_envelope.jsonrpc_message, JSONRPCErrorResponse)
        
        error_response = response_envelope.jsonrpc_message
        assert error_response.error.code == JSONRPCErrorCode.CAPABILITY_NOT_FOUND
        assert "Unknown capability" in error_response.error.message
    
    @pytest.mark.asyncio
    async def test_capability_execution_request_missing_capability_name(self, agent):
        """Test capability execution request with missing capability name"""
        request = JSONRPCRequest(
            method=A2AMethod.EXECUTE_CAPABILITY,
            params={"parameters": {"input": "test_data"}},  # Missing capability_name
            id="req-123"
        )
        
        envelope = A2AMessageEnvelope(
            sender_id="client_agent",
            recipient_id="test_agent",
            jsonrpc_message=request
        )
        
        sent_messages = []
        agent.send_message = AsyncMock(side_effect=lambda env: sent_messages.append(env))
        
        await agent._handle_incoming_message(envelope)
        
        # Verify error response was sent
        assert len(sent_messages) == 1
        response_envelope = sent_messages[0]
        assert isinstance(response_envelope.jsonrpc_message, JSONRPCErrorResponse)
        
        error_response = response_envelope.jsonrpc_message
        assert error_response.error.code == JSONRPCErrorCode.INVALID_PARAMS
        assert "capability_name is required" in error_response.error.message
    
    @pytest.mark.asyncio
    async def test_capability_execution_request_internal_error(self, agent):
        """Test capability execution request with internal error"""
        envelope = create_capability_request(
            sender_id="client_agent",
            recipient_id="test_agent",
            capability_name="error_capability",
            parameters={"input": "test_data"}
        )
        
        sent_messages = []
        agent.send_message = AsyncMock(side_effect=lambda env: sent_messages.append(env))
        
        await agent._handle_incoming_message(envelope)
        
        # Verify error response was sent
        assert len(sent_messages) == 1
        response_envelope = sent_messages[0]
        assert isinstance(response_envelope.jsonrpc_message, JSONRPCErrorResponse)
        
        error_response = response_envelope.jsonrpc_message
        assert error_response.error.code == JSONRPCErrorCode.INTERNAL_ERROR
        assert "Execution failed" in error_response.error.message
    
    @pytest.mark.asyncio
    async def test_list_capabilities_request(self, agent):
        """Test list capabilities request"""
        request = JSONRPCRequest(
            method=A2AMethod.LIST_CAPABILITIES,
            id="req-456"
        )
        
        envelope = A2AMessageEnvelope(
            sender_id="client_agent",
            recipient_id="test_agent",
            jsonrpc_message=request
        )
        
        sent_messages = []
        agent.send_message = AsyncMock(side_effect=lambda env: sent_messages.append(env))
        
        await agent._handle_incoming_message(envelope)
        
        # Verify response was sent
        assert len(sent_messages) == 1
        response_envelope = sent_messages[0]
        assert isinstance(response_envelope.jsonrpc_message, JSONRPCResponse)
        
        response = response_envelope.jsonrpc_message
        assert "capabilities" in response.result
        capabilities = response.result["capabilities"]
        assert len(capabilities) == 3  # test_capability, error_capability, slow_capability
        
        capability_names = [cap["name"] for cap in capabilities]
        assert "test_capability" in capability_names
        assert "error_capability" in capability_names
        assert "slow_capability" in capability_names
    
    @pytest.mark.asyncio
    async def test_get_capability_info_request(self, agent):
        """Test get capability info request"""
        request = JSONRPCRequest(
            method=A2AMethod.GET_CAPABILITY_INFO,
            params={"capability_name": "test_capability"},
            id="req-789"
        )
        
        envelope = A2AMessageEnvelope(
            sender_id="client_agent",
            recipient_id="test_agent",
            jsonrpc_message=request
        )
        
        sent_messages = []
        agent.send_message = AsyncMock(side_effect=lambda env: sent_messages.append(env))
        
        await agent._handle_incoming_message(envelope)
        
        # Verify response was sent
        assert len(sent_messages) == 1
        response_envelope = sent_messages[0]
        assert isinstance(response_envelope.jsonrpc_message, JSONRPCResponse)
        
        response = response_envelope.jsonrpc_message
        assert response.result["name"] == "test_capability"
        assert response.result["description"] == "Test capability"
    
    @pytest.mark.asyncio
    async def test_get_capability_info_not_found(self, agent):
        """Test get capability info for unknown capability"""
        request = JSONRPCRequest(
            method=A2AMethod.GET_CAPABILITY_INFO,
            params={"capability_name": "unknown_capability"},
            id="req-999"
        )
        
        envelope = A2AMessageEnvelope(
            sender_id="client_agent",
            recipient_id="test_agent",
            jsonrpc_message=request
        )
        
        sent_messages = []
        agent.send_message = AsyncMock(side_effect=lambda env: sent_messages.append(env))
        
        await agent._handle_incoming_message(envelope)
        
        # Verify error response was sent
        assert len(sent_messages) == 1
        response_envelope = sent_messages[0]
        assert isinstance(response_envelope.jsonrpc_message, JSONRPCErrorResponse)
        
        error_response = response_envelope.jsonrpc_message
        assert error_response.error.code == JSONRPCErrorCode.CAPABILITY_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_get_agent_info_request(self, agent):
        """Test get agent info request"""
        request = JSONRPCRequest(
            method=A2AMethod.GET_AGENT_INFO,
            id="req-111"
        )
        
        envelope = A2AMessageEnvelope(
            sender_id="client_agent",
            recipient_id="test_agent",
            jsonrpc_message=request
        )
        
        sent_messages = []
        agent.send_message = AsyncMock(side_effect=lambda env: sent_messages.append(env))
        
        await agent._handle_incoming_message(envelope)
        
        # Verify response was sent
        assert len(sent_messages) == 1
        response_envelope = sent_messages[0]
        assert isinstance(response_envelope.jsonrpc_message, JSONRPCResponse)
        
        response = response_envelope.jsonrpc_message
        agent_info = response.result
        assert agent_info["agent_id"] == "test_agent"
        assert agent_info["name"] == "Test Agent"
        assert agent_info["description"] == "Agent for testing"
        assert len(agent_info["capabilities"]) == 3
    
    @pytest.mark.asyncio
    async def test_get_agent_status_request(self, agent):
        """Test get agent status request"""
        request = JSONRPCRequest(
            method=A2AMethod.GET_AGENT_STATUS,
            id="req-222"
        )
        
        envelope = A2AMessageEnvelope(
            sender_id="client_agent",
            recipient_id="test_agent",
            jsonrpc_message=request
        )
        
        sent_messages = []
        agent.send_message = AsyncMock(side_effect=lambda env: sent_messages.append(env))
        
        await agent._handle_incoming_message(envelope)
        
        # Verify response was sent
        assert len(sent_messages) == 1
        response_envelope = sent_messages[0]
        assert isinstance(response_envelope.jsonrpc_message, JSONRPCResponse)
        
        response = response_envelope.jsonrpc_message
        status_data = response.result
        assert status_data["status"] == AgentStatus.READY.value
        assert "metrics" in status_data
        assert "active_tasks" in status_data
        assert "uptime_seconds" in status_data
    
    @pytest.mark.asyncio
    async def test_heartbeat_request(self, agent):
        """Test heartbeat request"""
        request = JSONRPCRequest(
            method=A2AMethod.HEARTBEAT,
            id="req-333"
        )
        
        envelope = A2AMessageEnvelope(
            sender_id="client_agent",
            recipient_id="test_agent",
            jsonrpc_message=request
        )
        
        sent_messages = []
        agent.send_message = AsyncMock(side_effect=lambda env: sent_messages.append(env))
        
        await agent._handle_incoming_message(envelope)
        
        # Verify response was sent
        assert len(sent_messages) == 1
        response_envelope = sent_messages[0]
        assert isinstance(response_envelope.jsonrpc_message, JSONRPCResponse)
        
        response = response_envelope.jsonrpc_message
        heartbeat_data = response.result
        assert heartbeat_data["agent_id"] == "test_agent"
        assert heartbeat_data["status"] == AgentStatus.READY.value
        assert "timestamp" in heartbeat_data
    
    @pytest.mark.asyncio
    async def test_unknown_method_request(self, agent):
        """Test request with unknown method"""
        request = JSONRPCRequest(
            method="unknown.method",
            id="req-444"
        )
        
        envelope = A2AMessageEnvelope(
            sender_id="client_agent",
            recipient_id="test_agent",
            jsonrpc_message=request
        )
        
        sent_messages = []
        agent.send_message = AsyncMock(side_effect=lambda env: sent_messages.append(env))
        
        await agent._handle_incoming_message(envelope)
        
        # Verify error response was sent
        assert len(sent_messages) == 1
        response_envelope = sent_messages[0]
        assert isinstance(response_envelope.jsonrpc_message, JSONRPCErrorResponse)
        
        error_response = response_envelope.jsonrpc_message
        assert error_response.error.code == JSONRPCErrorCode.METHOD_NOT_FOUND
        assert "Method not found" in error_response.error.message
    
    @pytest.mark.asyncio
    async def test_notification_handling(self, agent):
        """Test handling of notification messages"""
        notification = create_notification(
            sender_id="other_agent",
            recipient_id="test_agent",
            method=A2AMethod.HEARTBEAT,
            params={"status": "active", "timestamp": "2023-01-01T12:00:00Z"}
        )
        
        # Should not raise any exceptions
        await agent._handle_incoming_message(notification)
    
    @pytest.mark.asyncio
    async def test_response_handling(self, agent):
        """Test handling of response messages"""
        response = create_success_response(
            sender_id="other_agent",
            recipient_id="test_agent",
            request_id="req-555",
            result={"data": "response_data"}
        )
        
        # Should not raise any exceptions (responses are handled by message router)
        await agent._handle_incoming_message(response)
    
    @pytest.mark.asyncio
    async def test_error_response_handling(self, agent):
        """Test handling of error response messages"""
        error_response = create_error_response(
            sender_id="other_agent",
            recipient_id="test_agent",
            request_id="req-666",
            error_code=JSONRPCErrorCode.INTERNAL_ERROR,
            error_message="Some error occurred"
        )
        
        # Should not raise any exceptions
        await agent._handle_incoming_message(error_response)
    
    @pytest.mark.asyncio
    async def test_invalid_message_handling(self, agent):
        """Test handling of invalid messages"""
        # Create envelope with invalid message (missing required fields)
        envelope = A2AMessageEnvelope(
            sender_id="",  # Invalid empty sender
            recipient_id="test_agent",
            jsonrpc_message=JSONRPCRequest(method="test.method")
        )
        
        sent_messages = []
        agent.send_message = AsyncMock(side_effect=lambda env: sent_messages.append(env))
        
        # Should handle gracefully and send validation error if possible
        await agent._handle_incoming_message(envelope)
        
        # Since it's a request, should send validation error response
        assert len(sent_messages) == 1
        response_envelope = sent_messages[0]
        assert isinstance(response_envelope.jsonrpc_message, JSONRPCErrorResponse)
        
        error_response = response_envelope.jsonrpc_message
        assert error_response.error.code == JSONRPCErrorCode.VALIDATION_ERROR
    
    @pytest.mark.asyncio
    async def test_request_handling_exception(self, agent):
        """Test exception handling during request processing"""
        # Mock the capability execution to raise an exception
        original_execute = agent.execute_capability
        
        async def failing_execute(*args, **kwargs):
            raise Exception("Unexpected error")
        
        agent.execute_capability = failing_execute
        
        envelope = create_capability_request(
            sender_id="client_agent",
            recipient_id="test_agent",
            capability_name="test_capability",
            parameters={"input": "test_data"}
        )
        
        sent_messages = []
        agent.send_message = AsyncMock(side_effect=lambda env: sent_messages.append(env))
        
        await agent._handle_incoming_message(envelope)
        
        # Should send internal error response
        assert len(sent_messages) == 1
        response_envelope = sent_messages[0]
        assert isinstance(response_envelope.jsonrpc_message, JSONRPCErrorResponse)
        
        error_response = response_envelope.jsonrpc_message
        assert error_response.error.code == JSONRPCErrorCode.INTERNAL_ERROR
        
        # Restore original method
        agent.execute_capability = original_execute
    
    @pytest.mark.asyncio
    async def test_send_message_validation(self, agent):
        """Test outgoing message validation"""
        # Mock validation to fail
        with patch('models.validation.validate_message') as mock_validate:
            from models.validation import ValidationResult
            
            # Create a failed validation result
            failed_result = ValidationResult(is_valid=False, errors=["Test validation error"])
            mock_validate.return_value = failed_result
            
            envelope = create_capability_request(
                sender_id="test_agent",
                recipient_id="other_agent",
                capability_name="test_capability",
                parameters={"input": "test_data"}
            )
            
            # Should raise ValueError due to validation failure
            with pytest.raises(ValueError, match="Invalid outgoing message"):
                await agent.send_message(envelope)


if __name__ == "__main__":
    pytest.main([__file__])