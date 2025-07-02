"""
Tests for the base agent class
"""

import asyncio
import pytest
from datetime import datetime
from typing import Any, Dict

from agents.base import BaseAgent
from models.a2a import (
    AgentStatus,
    Capability,
    CapabilityType,
    TaskStatus,
)


class TestAgent(BaseAgent):
    """Test implementation of BaseAgent for testing"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initialized = False
        self.cleaned_up = False
        
    async def _initialize(self) -> None:
        """Test initialization"""
        self.initialized = True
        await asyncio.sleep(0.01)  # Simulate async work
        
    async def _cleanup(self) -> None:
        """Test cleanup"""
        self.cleaned_up = True
        await asyncio.sleep(0.01)  # Simulate async work
        
    async def _execute_capability_impl(
        self, 
        capability_name: str, 
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Test capability execution"""
        if capability_name == "test_capability":
            return {"result": "success", "input": parameters}
        elif capability_name == "slow_capability":
            await asyncio.sleep(0.1)
            return {"result": "slow_success"}
        elif capability_name == "error_capability":
            raise ValueError("Test error")
        else:
            raise ValueError(f"Unknown capability: {capability_name}")


@pytest.fixture
def test_agent():
    """Create a test agent instance"""
    return TestAgent(
        agent_id="test-agent-001",
        name="Test Agent",
        description="A test agent for unit testing",
        version="1.0.0"
    )


@pytest.fixture
def test_capability():
    """Create a test capability"""
    return Capability(
        name="test_capability",
        description="A test capability",
        capability_type=CapabilityType.DATA_COLLECTION,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"}
            }
        }
    )


class TestBaseAgent:
    """Test cases for BaseAgent"""
    
    def test_agent_initialization(self, test_agent):
        """Test agent initialization"""
        assert test_agent.agent_id == "test-agent-001"
        assert test_agent.name == "Test Agent"
        assert test_agent.description == "A test agent for unit testing"
        assert test_agent.version == "1.0.0"
        assert test_agent.status == AgentStatus.INITIALIZING
        assert len(test_agent.list_capabilities()) == 0
    
    def test_agent_card(self, test_agent):
        """Test agent card generation"""
        card = test_agent.agent_card
        assert card.agent_id == test_agent.agent_id
        assert card.name == test_agent.name
        assert card.description == test_agent.description
        assert card.version == test_agent.version
        assert card.status == AgentStatus.INITIALIZING
        assert "metrics" in card.metadata
        assert "active_tasks" in card.metadata
        assert "uptime" in card.metadata
    
    def test_capability_registration(self, test_agent, test_capability):
        """Test capability registration"""
        # Initially no capabilities
        assert not test_agent.has_capability("test_capability")
        assert test_agent.get_capability("test_capability") is None
        
        # Register capability
        test_agent.register_capability(test_capability)
        
        # Check capability is registered
        assert test_agent.has_capability("test_capability")
        assert test_agent.get_capability("test_capability") == test_capability
        assert len(test_agent.list_capabilities()) == 1
        
        # Check agent card includes capability
        card = test_agent.agent_card
        assert len(card.capabilities) == 1
        assert card.capabilities[0] == test_capability
    
    def test_metrics(self, test_agent):
        """Test agent metrics"""
        metrics = test_agent.metrics
        assert metrics.total_requests == 0
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 0
        assert metrics.concurrent_tasks == 0
        assert metrics.uptime_seconds >= 0
    
    @pytest.mark.asyncio
    async def test_agent_lifecycle(self, test_agent):
        """Test agent start and stop lifecycle"""
        # Initially not initialized
        assert not test_agent.initialized
        assert not test_agent.cleaned_up
        assert test_agent.status == AgentStatus.INITIALIZING
        
        # Start agent
        await test_agent.start()
        assert test_agent.initialized
        assert not test_agent.cleaned_up
        assert test_agent.status == AgentStatus.READY
        
        # Stop agent
        await test_agent.stop()
        assert test_agent.cleaned_up
        assert test_agent.status == AgentStatus.OFFLINE
    
    @pytest.mark.asyncio
    async def test_capability_execution(self, test_agent, test_capability):
        """Test capability execution"""
        # Register capability
        test_agent.register_capability(test_capability)
        
        # Start agent
        await test_agent.start()
        
        # Execute capability
        result = await test_agent.execute_capability(
            "test_capability",
            {"query": "test query"}
        )
        
        assert result["result"] == "success"
        assert result["input"]["query"] == "test query"
        
        # Check metrics updated
        metrics = test_agent.metrics
        assert metrics.total_requests == 1
        assert metrics.successful_requests == 1
        assert metrics.failed_requests == 0
        assert metrics.average_response_time_ms > 0
        
        await test_agent.stop()
    
    @pytest.mark.asyncio
    async def test_capability_execution_error(self, test_agent):
        """Test capability execution with error"""
        # Register error capability
        error_capability = Capability(
            name="error_capability",
            description="A capability that throws errors",
            capability_type=CapabilityType.DATA_COLLECTION,
            input_schema={"type": "object"},
            output_schema={"type": "object"}
        )
        test_agent.register_capability(error_capability)
        
        # Start agent
        await test_agent.start()
        
        # Execute capability that throws error
        with pytest.raises(ValueError, match="Test error"):
            await test_agent.execute_capability("error_capability", {})
        
        # Check metrics updated
        metrics = test_agent.metrics
        assert metrics.total_requests == 1
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 1
        
        await test_agent.stop()
    
    @pytest.mark.asyncio
    async def test_unknown_capability(self, test_agent):
        """Test execution of unknown capability"""
        await test_agent.start()
        
        with pytest.raises(ValueError, match="Unknown capability"):
            await test_agent.execute_capability("unknown_capability", {})
        
        await test_agent.stop()
    
    @pytest.mark.asyncio
    async def test_concurrent_capability_execution(self, test_agent):
        """Test concurrent capability execution"""
        # Register slow capability
        slow_capability = Capability(
            name="slow_capability",
            description="A slow capability",
            capability_type=CapabilityType.DATA_COLLECTION,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            max_concurrent=2
        )
        test_agent.register_capability(slow_capability)
        
        await test_agent.start()
        
        # Execute multiple capabilities concurrently
        tasks = [
            test_agent.execute_capability("slow_capability", {}),
            test_agent.execute_capability("slow_capability", {}),
        ]
        
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 2
        assert all(result["result"] == "slow_success" for result in results)
        
        # Check agent returned to ready state
        assert test_agent.status == AgentStatus.READY
        
        await test_agent.stop()
    
    @pytest.mark.asyncio
    async def test_agent_status_during_execution(self, test_agent):
        """Test agent status changes during capability execution"""
        # Register slow capability
        slow_capability = Capability(
            name="slow_capability",
            description="A slow capability",
            capability_type=CapabilityType.DATA_COLLECTION,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            max_concurrent=1
        )
        test_agent.register_capability(slow_capability)
        
        await test_agent.start()
        assert test_agent.status == AgentStatus.READY
        
        # Start capability execution
        task = asyncio.create_task(
            test_agent.execute_capability("slow_capability", {})
        )
        
        # Give it a moment to start
        await asyncio.sleep(0.01)
        
        # Agent should be busy
        assert test_agent.status == AgentStatus.BUSY
        
        # Wait for completion
        result = await task
        assert result["result"] == "slow_success"
        
        # Agent should be ready again
        assert test_agent.status == AgentStatus.READY
        
        await test_agent.stop()