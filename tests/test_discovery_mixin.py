"""
Tests for the capability discovery mixin
"""

import asyncio
import pytest
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

from agents.discovery import CapabilityDiscoveryMixin
from agents.registry import InMemoryAgentRegistry, RegistryQuery
from models.a2a import (
    AgentCard,
    AgentStatus,
    Capability,
    CapabilityType,
)


class TestDiscoveryAgent(CapabilityDiscoveryMixin):
    """Test agent with discovery mixin"""
    
    def __init__(self, agent_id: str, name: str, **kwargs):
        self.agent_id = agent_id
        self.name = name
        self.description = f"Test agent {name}"
        self.version = "1.0.0"
        self.endpoint = None
        self.heartbeat_interval = 30
        self._capabilities = {}
        self._status = AgentStatus.READY
        
        super().__init__(**kwargs)
    
    @property
    def agent_card(self) -> AgentCard:
        """Get agent card"""
        return AgentCard(
            agent_id=self.agent_id,
            name=self.name,
            description=self.description,
            version=self.version,
            capabilities=list(self._capabilities.values()),
            status=self._status,
            endpoint=self.endpoint,
            heartbeat_interval=self.heartbeat_interval
        )
    
    def register_capability(self, capability: Capability) -> None:
        """Register a capability"""
        self._capabilities[capability.name] = capability


@pytest.fixture
def test_registry():
    """Create a test registry with sample agents"""
    return InMemoryAgentRegistry()


@pytest.fixture
def discovery_agent():
    """Create a test agent with discovery mixin"""
    return TestDiscoveryAgent(
        agent_id="discovery-agent-001",
        name="Discovery Agent"
    )


@pytest.fixture
def sample_agents():
    """Create sample agent cards for testing"""
    return [
        AgentCard(
            agent_id="agent-001",
            name="Agent 1",
            description="First test agent",
            version="1.0.0",
            capabilities=[
                Capability(
                    name="data_collection",
                    description="Collect data",
                    capability_type=CapabilityType.DATA_COLLECTION,
                    input_schema={"type": "object"},
                    output_schema={"type": "object"}
                )
            ],
            status=AgentStatus.READY,
            heartbeat_interval=30
        ),
        AgentCard(
            agent_id="agent-002",
            name="Agent 2",
            description="Second test agent",
            version="1.0.0",
            capabilities=[
                Capability(
                    name="data_analysis",
                    description="Analyze data",
                    capability_type=CapabilityType.DATA_VERIFICATION,
                    input_schema={"type": "object"},
                    output_schema={"type": "object"}
                ),
                Capability(
                    name="data_collection",
                    description="Also collect data",
                    capability_type=CapabilityType.DATA_COLLECTION,
                    input_schema={"type": "object"},
                    output_schema={"type": "object"}
                )
            ],
            status=AgentStatus.READY,
            heartbeat_interval=60
        ),
        AgentCard(
            agent_id="agent-003",
            name="Agent 3",
            description="Third test agent",
            version="1.0.0",
            capabilities=[
                Capability(
                    name="content_generation",
                    description="Generate content",
                    capability_type=CapabilityType.MESSAGE_GENERATION,
                    input_schema={"type": "object"},
                    output_schema={"type": "object"}
                )
            ],
            status=AgentStatus.READY,
            heartbeat_interval=45
        )
    ]


class TestCapabilityDiscoveryMixin:
    """Test cases for CapabilityDiscoveryMixin"""
    
    @pytest.mark.asyncio
    async def test_setup_discovery(self, discovery_agent, test_registry):
        """Test discovery setup"""
        await test_registry.start()
        
        # Setup discovery with provided registry
        await discovery_agent._setup_discovery(test_registry)
        
        assert discovery_agent._registry is test_registry
        
        # Should be registered if auto-registration is enabled
        if discovery_agent._auto_register:
            agent = await test_registry.get_agent(discovery_agent.agent_id)
            assert agent is not None
            assert agent.agent_id == discovery_agent.agent_id
        
        await test_registry.stop()
    
    @pytest.mark.asyncio
    async def test_cleanup_discovery(self, discovery_agent, test_registry):
        """Test discovery cleanup"""
        await test_registry.start()
        await discovery_agent._setup_discovery(test_registry)
        
        # Cleanup discovery
        await discovery_agent._cleanup_discovery()
        
        # Should be unregistered if auto-registration was enabled
        if discovery_agent._auto_register:
            agent = await test_registry.get_agent(discovery_agent.agent_id)
            assert agent is None
        
        # Cache should be cleared
        assert len(discovery_agent._discovery_cache) == 0
        assert len(discovery_agent._cache_timestamps) == 0
        
        await test_registry.stop()
    
    @pytest.mark.asyncio
    async def test_discover_agents_with_capability(self, discovery_agent, test_registry, sample_agents):
        """Test discovering agents by capability"""
        await test_registry.start()
        
        # Register sample agents
        for agent in sample_agents:
            await test_registry.register_agent(agent)
        
        await discovery_agent._setup_discovery(test_registry)
        
        # Discover agents with data_collection capability
        agents = await discovery_agent.discover_agents_with_capability("data_collection")
        
        assert len(agents) == 2  # agent-001 and agent-002
        agent_ids = {agent.agent_id for agent in agents}
        assert "agent-001" in agent_ids
        assert "agent-002" in agent_ids
        
        # Discover agents with non-existent capability
        agents = await discovery_agent.discover_agents_with_capability("non_existent")
        assert len(agents) == 0
        
        await discovery_agent._cleanup_discovery()
        await test_registry.stop()
    
    @pytest.mark.asyncio
    async def test_discover_agents_by_type(self, discovery_agent, test_registry, sample_agents):
        """Test discovering agents by capability type"""
        await test_registry.start()
        
        # Register sample agents
        for agent in sample_agents:
            await test_registry.register_agent(agent)
        
        await discovery_agent._setup_discovery(test_registry)
        
        # Discover agents with DATA_COLLECTION capabilities
        agents = await discovery_agent.discover_agents_by_type(CapabilityType.DATA_COLLECTION)
        
        assert len(agents) == 2  # agent-001 and agent-002
        
        # Discover agents with DATA_VERIFICATION capabilities
        agents = await discovery_agent.discover_agents_by_type(CapabilityType.DATA_VERIFICATION)
        
        assert len(agents) == 1
        assert agents[0].agent_id == "agent-002"
        
        # Discover agents with MESSAGE_GENERATION capabilities
        agents = await discovery_agent.discover_agents_by_type(CapabilityType.MESSAGE_GENERATION)
        
        assert len(agents) == 1
        assert agents[0].agent_id == "agent-003"
        
        await discovery_agent._cleanup_discovery()
        await test_registry.stop()
    
    @pytest.mark.asyncio
    async def test_get_agent_info(self, discovery_agent, test_registry, sample_agents):
        """Test getting specific agent information"""
        await test_registry.start()
        
        # Register sample agents
        for agent in sample_agents:
            await test_registry.register_agent(agent)
        
        await discovery_agent._setup_discovery(test_registry)
        
        # Get existing agent
        agent = await discovery_agent.get_agent_info("agent-001")
        assert agent is not None
        assert agent.agent_id == "agent-001"
        assert agent.name == "Agent 1"
        
        # Get non-existent agent
        agent = await discovery_agent.get_agent_info("non-existent")
        assert agent is None
        
        await discovery_agent._cleanup_discovery()
        await test_registry.stop()
    
    @pytest.mark.asyncio
    async def test_list_all_capabilities(self, discovery_agent, test_registry, sample_agents):
        """Test listing all capabilities"""
        await test_registry.start()
        
        # Register sample agents
        for agent in sample_agents:
            await test_registry.register_agent(agent)
        
        await discovery_agent._setup_discovery(test_registry)
        
        # List all capabilities
        capabilities = await discovery_agent.list_all_capabilities()
        
        assert len(capabilities) == 3  # data_collection, data_analysis, content_generation
        capability_names = {cap.name for cap in capabilities}
        assert "data_collection" in capability_names
        assert "data_analysis" in capability_names
        assert "content_generation" in capability_names
        
        # List capabilities by type
        data_capabilities = await discovery_agent.list_all_capabilities(CapabilityType.DATA_COLLECTION)
        assert len(data_capabilities) == 1
        assert data_capabilities[0].name == "data_collection"
        
        await discovery_agent._cleanup_discovery()
        await test_registry.stop()
    
    @pytest.mark.asyncio
    async def test_select_best_agent_for_capability(self, discovery_agent, test_registry, sample_agents):
        """Test selecting best agent for capability"""
        await test_registry.start()
        
        # Register sample agents
        for agent in sample_agents:
            await test_registry.register_agent(agent)
        
        await discovery_agent._setup_discovery(test_registry)
        
        # Select best agent for data_collection (should return first available)
        best_agent = await discovery_agent.select_best_agent_for_capability("data_collection")
        assert best_agent is not None
        assert best_agent.agent_id in ["agent-001", "agent-002"]
        
        # Select best agent with criteria
        criteria = {"prefer_agent_id": "agent-002"}
        best_agent = await discovery_agent.select_best_agent_for_capability(
            "data_collection", 
            criteria
        )
        assert best_agent is not None
        assert best_agent.agent_id == "agent-002"
        
        # Select agent for non-existent capability
        best_agent = await discovery_agent.select_best_agent_for_capability("non_existent")
        assert best_agent is None
        
        await discovery_agent._cleanup_discovery()
        await test_registry.stop()
    
    @pytest.mark.asyncio
    async def test_caching_behavior(self, discovery_agent, test_registry, sample_agents):
        """Test discovery caching behavior"""
        await test_registry.start()
        
        # Register sample agents
        for agent in sample_agents:
            await test_registry.register_agent(agent)
        
        await discovery_agent._setup_discovery(test_registry)
        
        # First call should populate cache
        agents1 = await discovery_agent.discover_agents_with_capability("data_collection", use_cache=True)
        assert len(agents1) == 2
        
        # Second call should use cache
        agents2 = await discovery_agent.discover_agents_with_capability("data_collection", use_cache=True)
        assert len(agents2) == 2
        assert agents1 == agents2
        
        # Call without cache should bypass cache
        agents3 = await discovery_agent.discover_agents_with_capability("data_collection", use_cache=False)
        assert len(agents3) == 2
        
        # Clear cache
        discovery_agent.clear_discovery_cache()
        assert len(discovery_agent._discovery_cache) == 0
        
        await discovery_agent._cleanup_discovery()
        await test_registry.stop()
    
    @pytest.mark.asyncio
    async def test_cache_ttl(self, discovery_agent, test_registry, sample_agents):
        """Test cache TTL behavior"""
        await test_registry.start()
        
        # Set very short TTL for testing
        discovery_agent._cache_ttl = 0.1  # 100ms
        
        # Register sample agents
        for agent in sample_agents:
            await test_registry.register_agent(agent)
        
        await discovery_agent._setup_discovery(test_registry)
        
        # Populate cache
        agents1 = await discovery_agent.discover_agents_with_capability("data_collection")
        assert len(agents1) == 2
        
        # Cache should be valid
        cache_key = "capability:data_collection"
        assert discovery_agent._is_cache_valid(cache_key)
        
        # Wait for TTL to expire
        await asyncio.sleep(0.2)
        
        # Cache should be invalid
        assert not discovery_agent._is_cache_valid(cache_key)
        
        await discovery_agent._cleanup_discovery()
        await test_registry.stop()
    
    @pytest.mark.asyncio
    async def test_update_registry_info(self, discovery_agent, test_registry):
        """Test updating registry information"""
        await test_registry.start()
        await discovery_agent._setup_discovery(test_registry)
        
        # Add a capability
        discovery_agent.register_capability(
            Capability(
                name="new_capability",
                description="A new capability",
                capability_type=CapabilityType.DATA_VERIFICATION,
                input_schema={"type": "object"},
                output_schema={"type": "object"}
            )
        )
        
        # Update registry
        success = await discovery_agent.update_registry_info()
        assert success
        
        # Verify update
        agent = await test_registry.get_agent(discovery_agent.agent_id)
        assert agent is not None
        assert len(agent.capabilities) == 1
        assert agent.capabilities[0].name == "new_capability"
        
        await discovery_agent._cleanup_discovery()
        await test_registry.stop()
    
    @pytest.mark.asyncio
    async def test_agent_scoring(self, discovery_agent):
        """Test agent scoring algorithm"""
        # Create test agent with metrics
        test_agent = AgentCard(
            agent_id="test-agent",
            name="Test Agent",
            description="Test agent",
            version="1.0.0",
            capabilities=[],
            status=AgentStatus.READY,
            heartbeat_interval=30,
            metadata={
                "metrics": {
                    "average_response_time_ms": 100.0,
                    "concurrent_tasks": 2,
                    "successful_requests": 90,
                    "total_requests": 100
                }
            }
        )
        
        # Test scoring with no criteria
        score = await discovery_agent._calculate_agent_score(test_agent, {})
        assert score > 0  # Should have positive score for READY agent
        
        # Test scoring with preference
        criteria = {"prefer_agent_id": "test-agent"}
        score_with_preference = await discovery_agent._calculate_agent_score(test_agent, criteria)
        assert score_with_preference > score
        
        # Test scoring with avoidance
        criteria = {"avoid_agent_id": "test-agent"}
        score_with_avoidance = await discovery_agent._calculate_agent_score(test_agent, criteria)
        assert score_with_avoidance < score
        
        # Test max concurrent tasks criteria
        criteria = {"max_concurrent_tasks": 1}
        score_max_tasks = await discovery_agent._calculate_agent_score(test_agent, criteria)
        assert score_max_tasks < score  # Should be lower due to too many concurrent tasks
    
    @pytest.mark.asyncio
    async def test_exclude_self_behavior(self, discovery_agent, test_registry, sample_agents):
        """Test exclude_self parameter behavior"""
        await test_registry.start()
        
        # Register sample agents and discovery agent
        for agent in sample_agents:
            await test_registry.register_agent(agent)
        
        # Give discovery agent a data_collection capability
        discovery_agent.register_capability(
            Capability(
                name="data_collection",
                description="Collect data",
                capability_type=CapabilityType.DATA_COLLECTION,
                input_schema={"type": "object"},
                output_schema={"type": "object"}
            )
        )
        
        await discovery_agent._setup_discovery(test_registry)
        
        # Update registry with new capability
        await discovery_agent.update_registry_info()
        
        # Discover with exclude_self=True (default)
        agents_excluded = await discovery_agent.discover_agents_with_capability(
            "data_collection", exclude_self=True
        )
        agent_ids_excluded = {agent.agent_id for agent in agents_excluded}
        assert discovery_agent.agent_id not in agent_ids_excluded
        
        # Clear cache and discover with exclude_self=False
        discovery_agent.clear_discovery_cache()
        agents_included = await discovery_agent.discover_agents_with_capability(
            "data_collection", exclude_self=False
        )
        agent_ids_included = {agent.agent_id for agent in agents_included}
        assert discovery_agent.agent_id in agent_ids_included
        
        await discovery_agent._cleanup_discovery()
        await test_registry.stop()
    
    @pytest.mark.asyncio
    async def test_heartbeat_integration(self, discovery_agent, test_registry):
        """Test heartbeat integration with registry"""
        await test_registry.start()
        await discovery_agent._setup_discovery(test_registry)
        
        # Send heartbeat
        success = await discovery_agent._send_heartbeat_to_registry()
        
        if discovery_agent._auto_heartbeat and discovery_agent._registry:
            assert success
        else:
            assert not success
        
        await discovery_agent._cleanup_discovery()
        await test_registry.stop()
    
    def test_discovery_mixin_initialization(self):
        """Test discovery mixin initialization"""
        agent = TestDiscoveryAgent("test-001", "Test Agent")
        
        assert agent._registry is None
        assert len(agent._discovery_cache) == 0
        assert len(agent._cache_timestamps) == 0
        assert agent._cache_ttl == 300  # 5 minutes
        assert agent._auto_register
        assert agent._auto_heartbeat
        # Discovery logger is initially None and created during _setup_discovery
        assert agent.discovery_logger is None