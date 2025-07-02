"""
Tests for the agent registry system
"""

import asyncio
import pytest
from datetime import datetime, timedelta

from agents.registry import (
    InMemoryAgentRegistry,
    RegistryQuery,
    RegistryEntry,
    get_default_registry,
    shutdown_default_registry,
)
from models.a2a import (
    AgentCard,
    AgentStatus,
    Capability,
    CapabilityType,
)


@pytest.fixture
def registry():
    """Create a test registry instance"""
    return InMemoryAgentRegistry(cleanup_interval=1)


@pytest.fixture
def test_agent_card():
    """Create a test agent card"""
    return AgentCard(
        agent_id="test-agent-001",
        name="Test Agent",
        description="A test agent",
        version="1.0.0",
        capabilities=[
            Capability(
                name="test_capability",
                description="A test capability",
                capability_type=CapabilityType.DATA_COLLECTION,
                input_schema={"type": "object"},
                output_schema={"type": "object"}
            )
        ],
        status=AgentStatus.READY,
        heartbeat_interval=30
    )


@pytest.fixture
def another_agent_card():
    """Create another test agent card"""
    return AgentCard(
        agent_id="test-agent-002",
        name="Another Test Agent",
        description="Another test agent",
        version="1.0.0",
        capabilities=[
            Capability(
                name="analysis_capability",
                description="An analysis capability",
                capability_type=CapabilityType.DATA_VERIFICATION,
                input_schema={"type": "object"},
                output_schema={"type": "object"}
            ),
            Capability(
                name="shared_capability",
                description="A shared capability",
                capability_type=CapabilityType.DATA_COLLECTION,
                input_schema={"type": "object"},
                output_schema={"type": "object"}
            )
        ],
        status=AgentStatus.READY,
        heartbeat_interval=60
    )


class TestInMemoryAgentRegistry:
    """Test cases for InMemoryAgentRegistry"""
    
    @pytest.mark.asyncio
    async def test_registry_lifecycle(self, registry):
        """Test registry start and stop"""
        assert not registry._running
        
        await registry.start()
        assert registry._running
        assert registry._cleanup_task is not None
        
        await registry.stop()
        assert not registry._running
    
    @pytest.mark.asyncio
    async def test_agent_registration(self, registry, test_agent_card):
        """Test agent registration"""
        await registry.start()
        
        # Register agent
        success = await registry.register_agent(test_agent_card)
        assert success
        
        # Check agent is in registry
        retrieved_agent = await registry.get_agent(test_agent_card.agent_id)
        assert retrieved_agent is not None
        assert retrieved_agent.agent_id == test_agent_card.agent_id
        assert retrieved_agent.name == test_agent_card.name
        
        await registry.stop()
    
    @pytest.mark.asyncio
    async def test_agent_unregistration(self, registry, test_agent_card):
        """Test agent unregistration"""
        await registry.start()
        
        # Register agent first
        await registry.register_agent(test_agent_card)
        assert await registry.get_agent(test_agent_card.agent_id) is not None
        
        # Unregister agent
        success = await registry.unregister_agent(test_agent_card.agent_id)
        assert success
        
        # Check agent is removed
        retrieved_agent = await registry.get_agent(test_agent_card.agent_id)
        assert retrieved_agent is None
        
        await registry.stop()
    
    @pytest.mark.asyncio
    async def test_agent_update(self, registry, test_agent_card):
        """Test agent update"""
        await registry.start()
        
        # Register agent
        await registry.register_agent(test_agent_card)
        
        # Update agent
        test_agent_card.description = "Updated description"
        test_agent_card.status = AgentStatus.BUSY
        
        success = await registry.update_agent(test_agent_card)
        assert success
        
        # Check updates
        retrieved_agent = await registry.get_agent(test_agent_card.agent_id)
        assert retrieved_agent.description == "Updated description"
        assert retrieved_agent.status == AgentStatus.BUSY
        
        await registry.stop()
    
    @pytest.mark.asyncio
    async def test_heartbeat(self, registry, test_agent_card):
        """Test heartbeat functionality"""
        await registry.start()
        
        # Register agent
        await registry.register_agent(test_agent_card)
        
        # Get initial heartbeat time
        entry = registry._agents[test_agent_card.agent_id]
        initial_heartbeat = entry.last_heartbeat
        
        # Wait a bit and send heartbeat
        await asyncio.sleep(0.01)
        success = await registry.heartbeat(test_agent_card.agent_id)
        assert success
        
        # Check heartbeat updated
        updated_entry = registry._agents[test_agent_card.agent_id]
        assert updated_entry.last_heartbeat > initial_heartbeat
        assert updated_entry.is_online
        
        await registry.stop()
    
    @pytest.mark.asyncio
    async def test_discover_agents_by_capability(self, registry, test_agent_card, another_agent_card):
        """Test discovering agents by capability"""
        await registry.start()
        
        # Register both agents
        await registry.register_agent(test_agent_card)
        await registry.register_agent(another_agent_card)
        
        # Discover agents with test_capability
        query = RegistryQuery(capability_name="test_capability")
        agents = await registry.discover_agents(query)
        
        assert len(agents) == 1
        assert agents[0].agent_id == test_agent_card.agent_id
        
        # Discover agents with shared_capability
        query = RegistryQuery(capability_name="shared_capability")
        agents = await registry.discover_agents(query)
        
        assert len(agents) == 1
        assert agents[0].agent_id == another_agent_card.agent_id
        
        await registry.stop()
    
    @pytest.mark.asyncio
    async def test_discover_agents_by_type(self, registry, test_agent_card, another_agent_card):
        """Test discovering agents by capability type"""
        await registry.start()
        
        # Register both agents
        await registry.register_agent(test_agent_card)
        await registry.register_agent(another_agent_card)
        
        # Discover agents with DATA_COLLECTION capabilities
        query = RegistryQuery(capability_type=CapabilityType.DATA_COLLECTION)
        agents = await registry.discover_agents(query)
        
        # Both agents have DATA_COLLECTION capabilities
        assert len(agents) == 2
        agent_ids = {agent.agent_id for agent in agents}
        assert test_agent_card.agent_id in agent_ids
        assert another_agent_card.agent_id in agent_ids
        
        # Discover agents with DATA_VERIFICATION capabilities
        query = RegistryQuery(capability_type=CapabilityType.DATA_VERIFICATION)
        agents = await registry.discover_agents(query)
        
        assert len(agents) == 1
        assert agents[0].agent_id == another_agent_card.agent_id
        
        await registry.stop()
    
    @pytest.mark.asyncio
    async def test_discover_agents_with_filters(self, registry, test_agent_card, another_agent_card):
        """Test discovering agents with various filters"""
        await registry.start()
        
        # Register agents with different statuses
        test_agent_card.status = AgentStatus.READY
        another_agent_card.status = AgentStatus.BUSY
        
        await registry.register_agent(test_agent_card)
        await registry.register_agent(another_agent_card)
        
        # Discover only READY agents
        query = RegistryQuery(agent_status=AgentStatus.READY)
        agents = await registry.discover_agents(query)
        
        assert len(agents) == 1
        assert agents[0].agent_id == test_agent_card.agent_id
        assert agents[0].status == AgentStatus.READY
        
        # Discover with exclusions
        query = RegistryQuery(exclude_agents={test_agent_card.agent_id})
        agents = await registry.discover_agents(query)
        
        assert len(agents) == 1
        assert agents[0].agent_id == another_agent_card.agent_id
        
        # Test max results
        query = RegistryQuery(max_results=1)
        agents = await registry.discover_agents(query)
        
        assert len(agents) == 1
        
        await registry.stop()
    
    @pytest.mark.asyncio
    async def test_list_capabilities(self, registry, test_agent_card, another_agent_card):
        """Test listing capabilities"""
        await registry.start()
        
        # Register both agents
        await registry.register_agent(test_agent_card)
        await registry.register_agent(another_agent_card)
        
        # List all capabilities
        capabilities = await registry.list_capabilities()
        
        # Should have 3 unique capabilities
        assert len(capabilities) == 3
        capability_names = {cap.name for cap in capabilities}
        assert "test_capability" in capability_names
        assert "analysis_capability" in capability_names
        assert "shared_capability" in capability_names
        
        # List capabilities by type
        data_capabilities = await registry.list_capabilities(CapabilityType.DATA_COLLECTION)
        assert len(data_capabilities) == 2
        
        verification_capabilities = await registry.list_capabilities(CapabilityType.DATA_VERIFICATION)
        assert len(verification_capabilities) == 1
        
        await registry.stop()
    
    @pytest.mark.asyncio
    async def test_find_agents_with_capability(self, registry, test_agent_card, another_agent_card):
        """Test finding agents with specific capability"""
        await registry.start()
        
        # Register both agents
        await registry.register_agent(test_agent_card)
        await registry.register_agent(another_agent_card)
        
        # Find agents with test_capability
        agents = await registry.find_agents_with_capability("test_capability")
        assert len(agents) == 1
        assert agents[0].agent_id == test_agent_card.agent_id
        
        # Find agents with shared_capability
        agents = await registry.find_agents_with_capability("shared_capability")
        assert len(agents) == 1
        assert agents[0].agent_id == another_agent_card.agent_id
        
        # Find agents with non-existent capability
        agents = await registry.find_agents_with_capability("non_existent")
        assert len(agents) == 0
        
        await registry.stop()
    
    @pytest.mark.asyncio
    async def test_cleanup_stale_agents(self, registry, test_agent_card):
        """Test cleanup of stale agents"""
        # Use very short cleanup interval
        registry = InMemoryAgentRegistry(cleanup_interval=0.1)
        await registry.start()
        
        # Register agent
        await registry.register_agent(test_agent_card)
        
        # Manually set old heartbeat
        entry = registry._agents[test_agent_card.agent_id]
        entry.last_heartbeat = datetime.utcnow() - timedelta(seconds=200)
        entry.heartbeat_interval = 30  # 30 second interval, so 200 seconds is stale
        
        # Wait for cleanup to run
        await asyncio.sleep(0.2)
        
        # Agent should be marked offline
        updated_entry = registry._agents[test_agent_card.agent_id]
        assert not updated_entry.is_online
        assert updated_entry.agent_card.status == AgentStatus.OFFLINE
        
        await registry.stop()
    
    @pytest.mark.asyncio
    async def test_registry_stats(self, registry, test_agent_card, another_agent_card):
        """Test registry statistics"""
        await registry.start()
        
        # Initially empty
        stats = await registry.get_stats()
        assert stats["total_agents"] == 0
        assert stats["online_agents"] == 0
        assert stats["offline_agents"] == 0
        assert stats["total_capabilities"] == 0
        assert stats["running"]
        
        # Register agents
        await registry.register_agent(test_agent_card)
        await registry.register_agent(another_agent_card)
        
        # Check updated stats
        stats = await registry.get_stats()
        assert stats["total_agents"] == 2
        assert stats["online_agents"] == 2
        assert stats["offline_agents"] == 0
        assert stats["total_capabilities"] == 3  # test, analysis, shared
        
        await registry.stop()


class TestDefaultRegistry:
    """Test cases for default registry management"""
    
    @pytest.mark.asyncio
    async def test_get_default_registry(self):
        """Test getting default registry instance"""
        try:
            # Clean up any existing registry
            await shutdown_default_registry()
            
            # Get default registry
            registry1 = await get_default_registry()
            assert registry1 is not None
            assert registry1._running
            
            # Get it again - should be same instance
            registry2 = await get_default_registry()
            assert registry1 is registry2
            
        finally:
            # Clean up
            try:
                await shutdown_default_registry()
            except:
                pass  # Ignore cleanup errors
    
    @pytest.mark.asyncio
    async def test_shutdown_default_registry(self):
        """Test shutting down default registry"""
        try:
            # Clean up any existing registry first
            await shutdown_default_registry()
            
            # Get default registry
            registry = await get_default_registry()
            assert registry._running
            
            # Shutdown
            await shutdown_default_registry()
            assert not registry._running
            
            # Getting again should create new instance
            new_registry = await get_default_registry()
            assert new_registry is not registry
            assert new_registry._running
            
        finally:
            # Clean up
            try:
                await shutdown_default_registry()
            except:
                pass  # Ignore cleanup errors


class TestRegistryQuery:
    """Test cases for RegistryQuery"""
    
    def test_registry_query_defaults(self):
        """Test RegistryQuery default values"""
        query = RegistryQuery()
        
        assert query.capability_name is None
        assert query.capability_type is None
        assert query.agent_status is None
        assert query.exclude_agents == set()
        assert not query.include_offline
        assert query.max_results == 10
    
    def test_registry_query_with_values(self):
        """Test RegistryQuery with specific values"""
        query = RegistryQuery(
            capability_name="test_capability",
            capability_type=CapabilityType.DATA_VERIFICATION,
            agent_status=AgentStatus.READY,
            exclude_agents={"agent1", "agent2"},
            include_offline=True,
            max_results=5
        )
        
        assert query.capability_name == "test_capability"
        assert query.capability_type == CapabilityType.DATA_VERIFICATION
        assert query.agent_status == AgentStatus.READY
        assert query.exclude_agents == {"agent1", "agent2"}
        assert query.include_offline
        assert query.max_results == 5


class TestRegistryEntry:
    """Test cases for RegistryEntry"""
    
    def test_registry_entry_creation(self, test_agent_card):
        """Test RegistryEntry creation"""
        now = datetime.utcnow()
        entry = RegistryEntry(
            agent_card=test_agent_card,
            registered_at=now,
            last_heartbeat=now,
            heartbeat_interval=30
        )
        
        assert entry.agent_card == test_agent_card
        assert entry.registered_at == now
        assert entry.last_heartbeat == now
        assert entry.heartbeat_interval == 30
        assert entry.is_online  # Default is True