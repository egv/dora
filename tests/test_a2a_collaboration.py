"""
Tests for A2A Collaboration Services

Tests the discovery, notification, and orchestration services for agent collaboration.
"""

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from agents.discovery_service import (
    AgentDiscoveryService, RegisteredAgent, get_discovery_service, cleanup_discovery_service
)
from agents.notification_service import (
    NotificationService, NotificationEvent, Subscription, 
    get_notification_service, cleanup_notification_service
)
from agents.orchestration_service import (
    OrchestrationService, Workflow, WorkflowTask, WorkflowStatus, TaskStatus,
    get_orchestration_service, cleanup_orchestration_service
)
from agents.enhanced_calendar_intelligence import (
    EnhancedCalendarIntelligenceAgent, create_enhanced_calendar_intelligence_agent
)
from a2a.types import AgentCard, AgentSkill, AgentCapabilities


@pytest.fixture
async def discovery_service():
    """Create a test discovery service"""
    service = AgentDiscoveryService(heartbeat_timeout=60)
    await service.start()
    yield service
    await service.stop()


@pytest.fixture
async def notification_service():
    """Create a test notification service"""
    service = NotificationService(max_event_history=100, delivery_timeout=10)
    await service.start()
    yield service
    await service.stop()


@pytest.fixture
async def orchestration_service():
    """Create a test orchestration service"""
    service = OrchestrationService(max_concurrent_tasks=5, task_timeout=30)
    await service.start()
    yield service
    await service.stop()


@pytest.fixture
def sample_agent_card():
    """Create a sample agent card for testing"""
    return AgentCard(
        name="Test Agent",
        description="A test agent for collaboration testing",
        version="1.0.0",
        url="http://localhost:8001",
        defaultInputModes=["text/plain", "application/json"],
        defaultOutputModes=["application/json"],
        capabilities=AgentCapabilities(),
        skills=[
            AgentSkill(
                id="test_skill",
                name="Test Skill",
                description="A test skill",
                tags=["test"]
            )
        ]
    )


@pytest.fixture
def enhanced_calendar_agent():
    """Create an enhanced calendar intelligence agent for testing"""
    return create_enhanced_calendar_intelligence_agent("Test Enhanced Calendar")


class TestAgentDiscoveryService:
    """Test the agent discovery service"""
    
    @pytest.mark.asyncio
    async def test_service_lifecycle(self):
        """Test discovery service start/stop lifecycle"""
        service = AgentDiscoveryService()
        
        # Service should start successfully
        await service.start()
        assert service._health_check_task is not None
        
        # Service should stop cleanly
        await service.stop()
        assert service._health_check_task.cancelled()
    
    @pytest.mark.asyncio
    async def test_agent_registration(self, discovery_service, sample_agent_card):
        """Test agent registration and unregistration"""
        endpoint = "http://localhost:8001"
        
        # Register agent
        success = await discovery_service.register_agent(
            sample_agent_card, endpoint, {"test": True}
        )
        assert success is True
        
        # Check agent is registered
        agent_id = sample_agent_card.name.lower().replace(" ", "_")
        agent = await discovery_service.get_agent(agent_id)
        assert agent is not None
        assert agent.name == sample_agent_card.name
        assert agent.endpoint == endpoint
        assert agent.metadata["test"] is True
        
        # Unregister agent
        success = await discovery_service.unregister_agent(agent_id)
        assert success is True
        
        # Check agent is no longer registered
        agent = await discovery_service.get_agent(agent_id)
        assert agent is None
    
    @pytest.mark.asyncio
    async def test_agent_discovery(self, discovery_service, sample_agent_card):
        """Test agent discovery with filtering"""
        # Register multiple agents
        await discovery_service.register_agent(sample_agent_card, "http://localhost:8001")
        
        card2 = AgentCard(
            name="Another Agent",
            description="Another test agent",
            version="1.0.0",
            url="http://localhost:8002",
            defaultInputModes=["text/plain", "application/json"],
            defaultOutputModes=["application/json"],
            capabilities=AgentCapabilities(),
            skills=[
                AgentSkill(id="another_skill", name="Another Skill", description="Another skill", tags=["other"])
            ]
        )
        await discovery_service.register_agent(card2, "http://localhost:8002")
        
        # Discover all agents
        all_agents = await discovery_service.discover_agents()
        assert len(all_agents) >= 2
        
        # Discover agents by capability
        test_skill_agents = await discovery_service.discover_agents(capability_filter=["test_skill"])
        assert len(test_skill_agents) == 1
        assert test_skill_agents[0].name == "Test Agent"
        
        # Discover agents by status
        active_agents = await discovery_service.discover_agents(status_filter=["active"])
        assert len(active_agents) >= 2
    
    @pytest.mark.asyncio
    async def test_find_agents_by_skill(self, discovery_service, sample_agent_card):
        """Test finding agents by specific skill"""
        await discovery_service.register_agent(sample_agent_card, "http://localhost:8001")
        
        # Find agents with test_skill
        agents = await discovery_service.find_agents_by_skill("test_skill")
        assert len(agents) == 1
        assert agents[0].name == "Test Agent"
        
        # Find agents with non-existent skill
        agents = await discovery_service.find_agents_by_skill("non_existent_skill")
        assert len(agents) == 0
    
    @pytest.mark.asyncio
    async def test_heartbeat_management(self, discovery_service, sample_agent_card):
        """Test agent heartbeat management"""
        agent_id = sample_agent_card.name.lower().replace(" ", "_")
        await discovery_service.register_agent(sample_agent_card, "http://localhost:8001")
        
        # Update heartbeat
        success = await discovery_service.update_agent_heartbeat(agent_id)
        assert success is True
        
        agent = await discovery_service.get_agent(agent_id)
        assert agent.status == "active"
        
        # Test heartbeat for non-existent agent
        success = await discovery_service.update_agent_heartbeat("non_existent")
        assert success is False
    
    @pytest.mark.asyncio
    async def test_capabilities_summary(self, discovery_service, sample_agent_card):
        """Test getting capabilities summary"""
        await discovery_service.register_agent(sample_agent_card, "http://localhost:8001")
        
        summary = await discovery_service.get_capabilities_summary()
        
        assert "total_agents" in summary
        assert "active_agents" in summary
        assert "capabilities" in summary
        assert "agent_status_counts" in summary
        
        assert summary["total_agents"] >= 1
        assert summary["active_agents"] >= 1
        assert "test_skill" in summary["capabilities"]


class TestNotificationService:
    """Test the notification service"""
    
    @pytest.mark.asyncio
    async def test_service_lifecycle(self):
        """Test notification service start/stop lifecycle"""
        service = NotificationService()
        
        # Service should start successfully
        await service.start()
        assert len(service.delivery_workers) > 0
        
        # Service should stop cleanly
        await service.stop()
        assert len(service.delivery_workers) == 0
    
    @pytest.mark.asyncio
    async def test_subscription_management(self, notification_service):
        """Test subscription creation and management"""
        agent_id = "test_agent"
        event_types = ["test_event", "another_event"]
        
        # Create subscription
        subscription_id = await notification_service.subscribe(
            agent_id=agent_id,
            event_types=event_types,
            filters={"location": "test"}
        )
        
        assert subscription_id is not None
        
        # Check subscription exists
        subscriptions = await notification_service.get_subscriptions(agent_id)
        assert len(subscriptions) == 1
        assert subscriptions[0].agent_id == agent_id
        assert subscriptions[0].event_types == event_types
        
        # Unsubscribe
        success = await notification_service.unsubscribe(subscription_id)
        assert success is True
        
        # Check subscription is removed
        subscriptions = await notification_service.get_subscriptions(agent_id)
        assert len(subscriptions) == 0
    
    @pytest.mark.asyncio
    async def test_event_publishing(self, notification_service):
        """Test event publishing and delivery"""
        # Set up callback tracking
        received_events = []
        
        async def test_callback(event):
            received_events.append(event)
        
        # Create subscription with callback
        subscription_id = await notification_service.subscribe(
            agent_id="test_agent",
            event_types=["test_event"],
            callback=test_callback
        )
        
        # Publish event
        event_id = await notification_service.publish_event(
            event_type="test_event",
            data={"message": "test"},
            source_agent="publisher"
        )
        
        assert event_id is not None
        
        # Wait for delivery
        await asyncio.sleep(0.1)
        
        # Check event was delivered
        assert len(received_events) == 1
        assert received_events[0].event_type == "test_event"
        assert received_events[0].data["message"] == "test"
        assert received_events[0].source_agent == "publisher"
    
    @pytest.mark.asyncio
    async def test_event_filtering(self, notification_service):
        """Test event filtering with subscription filters"""
        received_events = []
        
        async def test_callback(event):
            received_events.append(event)
        
        # Create subscription with filters
        await notification_service.subscribe(
            agent_id="test_agent",
            event_types=["test_event"],
            filters={"location": "san_francisco"},
            callback=test_callback
        )
        
        # Publish matching event
        await notification_service.publish_event(
            event_type="test_event",
            data={"location": "san_francisco", "message": "match"},
            source_agent="publisher"
        )
        
        # Publish non-matching event
        await notification_service.publish_event(
            event_type="test_event",
            data={"location": "new_york", "message": "no_match"},
            source_agent="publisher"
        )
        
        # Wait for delivery
        await asyncio.sleep(0.1)
        
        # Check only matching event was delivered
        assert len(received_events) == 1
        assert received_events[0].data["message"] == "match"
    
    @pytest.mark.asyncio
    async def test_direct_messaging(self, notification_service):
        """Test direct agent-to-agent messaging"""
        received_events = []
        
        async def test_callback(event):
            received_events.append(event)
        
        # Subscribe to direct messages
        await notification_service.subscribe(
            agent_id="target_agent",
            event_types=["direct_message.target_agent"],
            callback=test_callback
        )
        
        # Send direct message
        success = await notification_service.notify_agent(
            agent_id="target_agent",
            message={"content": "Hello target!"},
            source_agent="sender_agent"
        )
        
        assert success is True
        
        # Wait for delivery
        await asyncio.sleep(0.1)
        
        # Check message was delivered
        assert len(received_events) == 1
        event = received_events[0]
        assert event.event_type == "direct_message.target_agent"
        assert event.data["message"]["content"] == "Hello target!"
        assert event.source_agent == "sender_agent"
    
    @pytest.mark.asyncio
    async def test_event_history(self, notification_service):
        """Test event history functionality"""
        # Publish some events
        await notification_service.publish_event("type1", {"data": 1}, "agent1")
        await notification_service.publish_event("type2", {"data": 2}, "agent2")
        await notification_service.publish_event("type1", {"data": 3}, "agent1")
        
        # Get all history
        all_events = await notification_service.get_event_history()
        assert len(all_events) >= 3
        
        # Get filtered history
        type1_events = await notification_service.get_event_history(event_type="type1")
        assert len(type1_events) >= 2
        
        # Get recent history
        recent_events = await notification_service.get_event_history(
            since=datetime.utcnow() - timedelta(minutes=1)
        )
        assert len(recent_events) >= 3


class TestOrchestrationService:
    """Test the orchestration service"""
    
    @pytest.mark.asyncio
    async def test_service_lifecycle(self):
        """Test orchestration service start/stop lifecycle"""
        service = OrchestrationService()
        
        # Service should start successfully
        await service.start()
        assert service.discovery_service is not None
        assert service.notification_service is not None
        
        # Service should stop cleanly
        await service.stop()
        assert len(service.executor_tasks) == 0
    
    @pytest.mark.asyncio
    async def test_workflow_creation(self, orchestration_service):
        """Test workflow creation and validation"""
        # Create simple workflow with specific agent assignments to avoid validation errors
        tasks = [
            {
                "task_id": "task1",
                "skill_name": "test_skill",
                "parameters": {"param1": "value1"},
                "agent_id": "test_agent_1"  # Specify agent to bypass skill validation
            },
            {
                "task_id": "task2", 
                "skill_name": "another_skill",
                "parameters": {"param2": "value2"},
                "dependencies": ["task1"],
                "agent_id": "test_agent_2"  # Specify agent to bypass skill validation
            }
        ]
        
        workflow_id = await orchestration_service.create_workflow(
            name="Test Workflow",
            description="A test workflow",
            tasks=tasks,
            created_by="test_agent"
        )
        
        assert workflow_id is not None
        
        # Get workflow
        workflow = await orchestration_service.get_workflow(workflow_id)
        assert workflow is not None
        assert workflow.name == "Test Workflow"
        assert len(workflow.tasks) == 2
        assert workflow.status == WorkflowStatus.PENDING
    
    @pytest.mark.asyncio
    async def test_workflow_validation(self, orchestration_service):
        """Test workflow validation"""
        # Test circular dependency
        tasks = [
            {
                "task_id": "task1",
                "skill_name": "test_skill",
                "parameters": {},
                "dependencies": ["task2"]
            },
            {
                "task_id": "task2",
                "skill_name": "test_skill", 
                "parameters": {},
                "dependencies": ["task1"]
            }
        ]
        
        with pytest.raises(ValueError, match="Circular dependencies detected"):
            await orchestration_service.create_workflow(
                name="Invalid Workflow",
                description="Has circular dependencies",
                tasks=tasks
            )
    
    @pytest.mark.asyncio
    async def test_task_dependency_resolution(self, orchestration_service):
        """Test task dependency resolution"""
        # Create workflow with dependencies
        tasks = [
            {
                "task_id": "task1",
                "skill_name": "test_skill",
                "parameters": {}
            },
            {
                "task_id": "task2",
                "skill_name": "test_skill",
                "parameters": {},
                "dependencies": ["task1"]
            },
            {
                "task_id": "task3",
                "skill_name": "test_skill", 
                "parameters": {},
                "dependencies": ["task1", "task2"]
            }
        ]
        
        workflow_id = await orchestration_service.create_workflow(
            name="Dependency Test",
            description="Test task dependencies",
            tasks=tasks
        )
        
        workflow = await orchestration_service.get_workflow(workflow_id)
        
        # Initially only task1 should be ready
        ready_tasks = workflow.get_ready_tasks()
        assert len(ready_tasks) == 1
        assert ready_tasks[0].task_id == "task1"
        
        # Complete task1
        workflow.tasks[0].status = TaskStatus.COMPLETED
        ready_tasks = workflow.get_ready_tasks()
        assert len(ready_tasks) == 1
        assert ready_tasks[0].task_id == "task2"
        
        # Complete task2
        workflow.tasks[1].status = TaskStatus.COMPLETED
        ready_tasks = workflow.get_ready_tasks()
        assert len(ready_tasks) == 1
        assert ready_tasks[0].task_id == "task3"
    
    @pytest.mark.asyncio
    async def test_workflow_cancellation(self, orchestration_service):
        """Test workflow cancellation"""
        tasks = [
            {
                "task_id": "task1",
                "skill_name": "long_running_task",
                "parameters": {}
            }
        ]
        
        workflow_id = await orchestration_service.create_workflow(
            name="Cancellation Test",
            description="Test workflow cancellation",
            tasks=tasks
        )
        
        # Set workflow to running
        workflow = await orchestration_service.get_workflow(workflow_id)
        workflow.status = WorkflowStatus.RUNNING
        orchestration_service.active_workflows.add(workflow_id)
        
        # Cancel workflow
        success = await orchestration_service.cancel_workflow(workflow_id)
        assert success is True
        
        # Check workflow is cancelled
        workflow = await orchestration_service.get_workflow(workflow_id)
        assert workflow.status == WorkflowStatus.CANCELLED
        assert workflow_id not in orchestration_service.active_workflows
    
    @pytest.mark.asyncio
    async def test_workflow_listing(self, orchestration_service):
        """Test workflow listing with filters"""
        # Create multiple workflows
        await orchestration_service.create_workflow(
            name="Workflow 1", description="Test 1", tasks=[], created_by="agent1"
        )
        await orchestration_service.create_workflow(
            name="Workflow 2", description="Test 2", tasks=[], created_by="agent2"
        )
        
        # List all workflows
        all_workflows = await orchestration_service.list_workflows()
        assert len(all_workflows) >= 2
        
        # List workflows by creator
        agent1_workflows = await orchestration_service.list_workflows(created_by="agent1")
        assert len(agent1_workflows) >= 1
        assert all(w["created_by"] == "agent1" for w in agent1_workflows)
        
        # List workflows by status
        pending_workflows = await orchestration_service.list_workflows(
            status_filter=[WorkflowStatus.PENDING]
        )
        assert len(pending_workflows) >= 2
        assert all(w["status"] == "pending" for w in pending_workflows)


class TestEnhancedCalendarIntelligence:
    """Test the enhanced calendar intelligence agent with A2A collaboration"""
    
    @pytest.mark.asyncio
    async def test_agent_initialization(self, enhanced_calendar_agent):
        """Test enhanced agent initialization"""
        assert enhanced_calendar_agent.name == "Test Enhanced Calendar"
        assert enhanced_calendar_agent.version == "2.0.0"
        assert len(enhanced_calendar_agent.skills) == 5  # Enhanced skills
        
        # Check for collaborative skills
        skill_ids = [skill.id for skill in enhanced_calendar_agent.skills]
        assert "discover_agents" in skill_ids
        assert "subscribe_to_updates" in skill_ids
    
    @pytest.mark.asyncio
    async def test_collaborative_data_collection(self, enhanced_calendar_agent):
        """Test collaborative data collection capabilities"""
        executor = enhanced_calendar_agent.executor
        
        # Mock the services to avoid actual network calls
        mock_discovery = AsyncMock()
        mock_notification = AsyncMock()
        mock_orchestration = AsyncMock()
        
        executor.discovery_service = mock_discovery
        executor.notification_service = mock_notification
        executor.orchestration_service = mock_orchestration
        
        # Mock agent discovery
        mock_discovery.find_agents_by_skill.return_value = []
        
        # Test collaborative collection falls back to self-collection
        with patch.object(executor, '_self_collect_calendar_data') as mock_self_collect:
            mock_self_collect.return_value = {
                "calendar_data": {"location": "Test", "date": "2025-07-10"},
                "collection_method": "self"
            }
            
            result = await executor._collaborative_calendar_data_collection(
                "Test City", datetime(2025, 7, 10), {}
            )
            
            assert result["collection_method"] == "self"
            mock_self_collect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_subscription_management(self, enhanced_calendar_agent):
        """Test agent update subscription management"""
        executor = enhanced_calendar_agent.executor
        
        # Mock notification service
        mock_notification = AsyncMock()
        mock_notification.subscribe.return_value = "subscription_123"
        executor.notification_service = mock_notification
        
        # Test subscription
        subscription_id = await executor.subscribe_to_agent_updates(["event", "weather"])
        
        assert subscription_id == "subscription_123"
        mock_notification.subscribe.assert_called_once()
        
        # Check subscription parameters
        call_args = mock_notification.subscribe.call_args
        assert call_args[1]["agent_id"] == "calendar_intelligence"
        assert "event.data_updated" in call_args[1]["event_types"]
        assert "weather.data_updated" in call_args[1]["event_types"]
    
    @pytest.mark.asyncio
    async def test_notification_handling(self, enhanced_calendar_agent):
        """Test handling of agent update notifications"""
        executor = enhanced_calendar_agent.executor
        
        # Create test notification events
        calendar_event = NotificationEvent(
            event_id="event_1",
            event_type="calendar_data.updated",
            source_agent="another_agent",
            timestamp=datetime.utcnow(),
            data={
                "location": "Test City",
                "date": "2025-07-10",
                "opportunity_score": 85
            }
        )
        
        workflow_event = NotificationEvent(
            event_id="event_2",
            event_type="workflow.completed",
            source_agent="orchestration_service",
            timestamp=datetime.utcnow(),
            data={
                "workflow_id": "workflow_123",
                "name": "Test Workflow"
            }
        )
        
        # Test handling (should not raise exceptions)
        await executor._handle_agent_update(calendar_event)
        await executor._handle_agent_update(workflow_event)


class TestIntegrationScenarios:
    """Test integrated scenarios across multiple services"""
    
    @pytest.mark.asyncio
    async def test_full_collaborative_workflow(self):
        """Test a complete collaborative workflow scenario"""
        # Initialize services
        discovery = AgentDiscoveryService(heartbeat_timeout=300)
        notification = NotificationService()
        orchestration = OrchestrationService()
        
        await discovery.start()
        await notification.start()
        await orchestration.start()
        
        try:
            # Register a mock agent
            mock_agent_card = AgentCard(
                name="Mock Event Agent",
                description="Mock agent for testing",
                version="1.0.0",
                url="http://localhost:9999",
                defaultInputModes=["text/plain", "application/json"],
                defaultOutputModes=["application/json"],
                capabilities=AgentCapabilities(),
                skills=[
                    AgentSkill(
                        id="search_events",
                        name="Search Events",
                        description="Search for events",
                        tags=["events"]
                    )
                ]
            )
            
            await discovery.register_agent(mock_agent_card, "http://localhost:9999")
            
            # Create collaborative workflow
            tasks = [
                {
                    "task_id": "discover_agents",
                    "skill_name": "get_capabilities_summary",
                    "parameters": {},
                    "agent_id": "mock_event_agent"  # Use specific agent to bypass validation
                },
                {
                    "task_id": "search_events",
                    "skill_name": "search_events",
                    "parameters": {"city": "San Francisco", "date": "2025-07-10"},
                    "agent_id": "mock_event_agent"
                }
            ]
            
            workflow_id = await orchestration.create_workflow(
                name="Test Collaboration",
                description="Test collaborative data collection",
                tasks=tasks,
                created_by="test_system"
            )
            
            # Verify workflow was created
            workflow = await orchestration.get_workflow(workflow_id)
            assert workflow is not None
            assert workflow.name == "Test Collaboration"
            assert len(workflow.tasks) == 2
            
            # Verify agent was discovered
            agents = await discovery.find_agents_by_skill("search_events")
            assert len(agents) == 1
            assert agents[0].name == "Mock Event Agent"
            
            # Test notification publishing
            event_id = await notification.publish_event(
                event_type="workflow.created",
                data={"workflow_id": workflow_id},
                source_agent="test_system"
            )
            
            assert event_id is not None
            
            # Get statistics
            discovery_stats = await discovery.get_capabilities_summary()
            notification_stats = await notification.get_statistics()
            orchestration_stats = await orchestration.get_statistics()
            
            assert discovery_stats["total_agents"] >= 1
            assert notification_stats["event_history_size"] >= 1
            assert orchestration_stats["total_workflows"] >= 1
            
        finally:
            # Cleanup
            await orchestration.stop()
            await notification.stop()
            await discovery.stop()
    
    @pytest.mark.asyncio
    async def test_service_cleanup(self):
        """Test proper cleanup of global service instances"""
        # Get service instances
        discovery = await get_discovery_service()
        notification = await get_notification_service()
        orchestration = await get_orchestration_service()
        
        assert discovery is not None
        assert notification is not None
        assert orchestration is not None
        
        # Cleanup services
        await cleanup_discovery_service()
        await cleanup_notification_service()
        await cleanup_orchestration_service()
        
        # Verify cleanup (services should be recreated when requested again)
        new_discovery = await get_discovery_service()
        new_notification = await get_notification_service()
        new_orchestration = await get_orchestration_service()
        
        assert new_discovery is not discovery  # Should be new instance
        assert new_notification is not notification
        assert new_orchestration is not orchestration
        
        # Final cleanup
        await cleanup_discovery_service()
        await cleanup_notification_service()
        await cleanup_orchestration_service()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])