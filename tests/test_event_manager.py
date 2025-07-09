"""
Test Event Manager Agent - Vanilla Google A2A Implementation

Tests for the new EventManagerAgent using official A2A SDK patterns.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from agents.event_manager import (
    EventManagerAgent,
    EventManagerExecutor,
    EventManagerRequestHandler,
    Event,
    create_event_manager_agent
)
from a2a.types import (
    AgentCard,
    AgentSkill,
    Message,
    MessageSendParams,
    Part,
    TextPart,
    TaskQueryParams,
    TaskIdParams,
    TaskState
)


class TestEvent:
    """Test the Event data structure"""
    
    def test_event_creation(self):
        """Test creating a basic event"""
        start_time = datetime.now()
        end_time = start_time + timedelta(hours=1)
        
        event = Event(
            event_id="test-123",
            title="Test Meeting",
            description="A test meeting",
            start_time=start_time,
            end_time=end_time,
            organizer="test@example.com"
        )
        
        assert event.event_id == "test-123"
        assert event.title == "Test Meeting"
        assert event.description == "A test meeting"
        assert event.start_time == start_time
        assert event.end_time == end_time
        assert event.organizer == "test@example.com"
        assert event.status == "scheduled"
        assert event.attendees == []
    
    def test_event_to_dict(self):
        """Test event serialization"""
        start_time = datetime(2024, 1, 1, 10, 0)
        end_time = datetime(2024, 1, 1, 11, 0)
        
        event = Event(
            event_id="test-123",
            title="Test Meeting",
            description="A test meeting",
            start_time=start_time,
            end_time=end_time,
            organizer="test@example.com"
        )
        
        event_dict = event.to_dict()
        
        assert event_dict["event_id"] == "test-123"
        assert event_dict["title"] == "Test Meeting"
        assert event_dict["start_time"] == "2024-01-01T10:00:00"
        assert event_dict["end_time"] == "2024-01-01T11:00:00"
        assert event_dict["organizer"] == "test@example.com"
        assert event_dict["status"] == "scheduled"
        assert event_dict["attendees"] == []


class TestEventManagerExecutor:
    """Test the EventManagerExecutor"""
    
    @pytest.fixture
    def executor(self):
        """Create a test executor"""
        return EventManagerExecutor()
    
    @pytest.mark.asyncio
    async def test_create_event(self, executor):
        """Test creating an event"""
        params = {
            "title": "Test Meeting",
            "description": "A test meeting",
            "start_time": "2024-01-01T10:00:00",
            "end_time": "2024-01-01T11:00:00",
            "organizer": "test@example.com"
        }
        
        result = await executor._create_event(params)
        
        assert "event_id" in result
        assert "event" in result
        assert result["event"]["title"] == "Test Meeting"
        assert result["event"]["organizer"] == "test@example.com"
        
        # Verify event is stored
        event_id = result["event_id"]
        assert event_id in executor.events
    
    @pytest.mark.asyncio
    async def test_list_events_empty(self, executor):
        """Test listing events when none exist"""
        result = await executor._list_events({})
        
        assert result["events"] == []
        assert result["count"] == 0
    
    @pytest.mark.asyncio
    async def test_list_events_with_data(self, executor):
        """Test listing events with existing data"""
        # Create test events
        await executor._create_event({
            "title": "Meeting 1",
            "start_time": "2024-01-01T10:00:00",
            "end_time": "2024-01-01T11:00:00",
            "organizer": "test1@example.com"
        })
        
        await executor._create_event({
            "title": "Meeting 2", 
            "start_time": "2024-01-02T14:00:00",
            "end_time": "2024-01-02T15:00:00",
            "organizer": "test2@example.com"
        })
        
        result = await executor._list_events({})
        
        assert result["count"] == 2
        assert len(result["events"]) == 2
        
        titles = [event["title"] for event in result["events"]]
        assert "Meeting 1" in titles
        assert "Meeting 2" in titles
    
    @pytest.mark.asyncio
    async def test_get_event(self, executor):
        """Test getting a specific event"""
        # Create an event first
        create_result = await executor._create_event({
            "title": "Test Meeting",
            "start_time": "2024-01-01T10:00:00",
            "end_time": "2024-01-01T11:00:00",
            "organizer": "test@example.com"
        })
        
        event_id = create_result["event_id"]
        
        # Get the event
        result = await executor._get_event({"event_id": event_id})
        
        assert "event" in result
        assert result["event"]["event_id"] == event_id
        assert result["event"]["title"] == "Test Meeting"
    
    @pytest.mark.asyncio
    async def test_get_event_not_found(self, executor):
        """Test getting a non-existent event"""
        with pytest.raises(ValueError, match="Event not found"):
            await executor._get_event({"event_id": "non-existent"})
    
    @pytest.mark.asyncio
    async def test_update_event(self, executor):
        """Test updating an event"""
        # Create an event first
        create_result = await executor._create_event({
            "title": "Original Title",
            "start_time": "2024-01-01T10:00:00",
            "end_time": "2024-01-01T11:00:00",
            "organizer": "test@example.com"
        })
        
        event_id = create_result["event_id"]
        
        # Update the event
        result = await executor._update_event({
            "event_id": event_id,
            "title": "Updated Title",
            "description": "Updated description"
        })
        
        assert result["event"]["title"] == "Updated Title"
        assert result["event"]["description"] == "Updated description"
        assert result["event"]["organizer"] == "test@example.com"  # Unchanged
    
    @pytest.mark.asyncio
    async def test_cancel_event(self, executor):
        """Test cancelling an event"""
        # Create an event first
        create_result = await executor._create_event({
            "title": "Test Meeting",
            "start_time": "2024-01-01T10:00:00",
            "end_time": "2024-01-01T11:00:00",
            "organizer": "test@example.com"
        })
        
        event_id = create_result["event_id"]
        
        # Cancel the event
        result = await executor._cancel_event({"event_id": event_id})
        
        assert result["event"]["status"] == "cancelled"
        assert result["event"]["title"] == "Test Meeting"  # Other fields unchanged
    
    @pytest.mark.asyncio
    async def test_add_attendee(self, executor):
        """Test adding an attendee to an event"""
        # Create an event first
        create_result = await executor._create_event({
            "title": "Test Meeting",
            "start_time": "2024-01-01T10:00:00",
            "end_time": "2024-01-01T11:00:00",
            "organizer": "test@example.com"
        })
        
        event_id = create_result["event_id"]
        
        # Add attendee
        result = await executor._add_attendee({
            "event_id": event_id,
            "attendee": "attendee@example.com"
        })
        
        assert "attendee@example.com" in result["event"]["attendees"]
        
        # Add another attendee
        result2 = await executor._add_attendee({
            "event_id": event_id,
            "attendee": "attendee2@example.com"
        })
        
        attendees = result2["event"]["attendees"]
        assert "attendee@example.com" in attendees
        assert "attendee2@example.com" in attendees
        assert len(attendees) == 2


class TestEventManagerRequestHandler:
    """Test the EventManagerRequestHandler"""
    
    @pytest.fixture
    def handler(self):
        """Create a test handler"""
        executor = EventManagerExecutor()
        return EventManagerRequestHandler(executor)
    
    @pytest.mark.asyncio
    async def test_message_send_create_event(self, handler):
        """Test handling a create event message"""
        params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(
                            text="create event"
                        )
                    )
                ]
            )
        )
        
        response = await handler.on_message_send(params)
        
        assert isinstance(response, Message)
        assert response.role == "agent"
        assert len(response.parts) > 0
        assert hasattr(response.parts[0].root, 'text')
        assert "create_event" in response.parts[0].root.text
    
    @pytest.mark.asyncio
    async def test_message_send_list_events(self, handler):
        """Test handling a list events message"""
        params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(
                            text="list events"
                        )
                    )
                ]
            )
        )
        
        response = await handler.on_message_send(params)
        
        assert isinstance(response, Message)
        assert response.role == "agent"
        assert len(response.parts) > 0
        assert hasattr(response.parts[0].root, 'text')
        assert "list_events" in response.parts[0].root.text
    
    @pytest.mark.asyncio
    async def test_message_send_invalid_skill(self, handler):
        """Test handling a message with invalid skill"""
        params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(
                            text="invalid unknown command"
                        )
                    )
                ]
            )
        )
        
        response = await handler.on_message_send(params)
        
        assert isinstance(response, Message)
        assert response.role == "agent"
        assert len(response.parts) > 0
        assert hasattr(response.parts[0].root, 'text')
        # Should default to list_events for unknown commands
        assert "list_events" in response.parts[0].root.text
    
    @pytest.mark.asyncio
    async def test_get_task(self, handler):
        """Test getting task status"""
        # First create a task by sending a message
        params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(
                            text="list events"
                        )
                    )
                ]
            )
        )
        
        response = await handler.on_message_send(params)
        task_id = response.taskId
        
        # Now get the task
        task_params = TaskQueryParams(id=task_id)
        task = await handler.on_get_task(task_params)
        
        assert task is not None
        assert task.id == task_id
        assert task.status.state == TaskState.completed
    
    @pytest.mark.asyncio
    async def test_cancel_task(self, handler):
        """Test cancelling a task"""
        # First create a task by sending a message
        params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(
                            text="list events"
                        )
                    )
                ]
            )
        )
        
        response = await handler.on_message_send(params)
        task_id = response.taskId
        
        # Cancel the task
        cancel_params = TaskIdParams(id=task_id)
        task = await handler.on_cancel_task(cancel_params)
        
        assert task is not None
        assert task.id == task_id
        assert task.status.state == TaskState.canceled


class TestEventManagerAgent:
    """Test the EventManagerAgent"""
    
    def test_agent_creation(self):
        """Test creating the agent"""
        agent = EventManagerAgent(name="Test Agent", version="2.0.0")
        
        assert agent.name == "Test Agent"
        assert agent.version == "2.0.0"
        assert isinstance(agent.agent_card, AgentCard)
        assert agent.agent_card.name == "Test Agent"
        assert agent.agent_card.version == "2.0.0"
        assert len(agent.skills) == 6  # All event management skills
    
    def test_agent_skills(self):
        """Test agent skills configuration"""
        agent = EventManagerAgent()
        
        skill_ids = [skill.id for skill in agent.skills]
        expected_skills = [
            "create_event", "list_events", "get_event", 
            "update_event", "cancel_event", "add_attendee"
        ]
        
        for expected_skill in expected_skills:
            assert expected_skill in skill_ids
    
    def test_agent_card_structure(self):
        """Test agent card structure matches A2A spec"""
        agent = EventManagerAgent()
        card = agent.agent_card
        
        # Required fields
        assert hasattr(card, 'name')
        assert hasattr(card, 'description')
        assert hasattr(card, 'version')
        assert hasattr(card, 'url')
        assert hasattr(card, 'skills')
        assert hasattr(card, 'capabilities')
        assert hasattr(card, 'defaultInputModes')
        assert hasattr(card, 'defaultOutputModes')
        
        # Values
        assert card.name == "Event Manager"
        assert "calendar" in card.description.lower()
        assert len(card.skills) == 6
        # AgentCapabilities doesn't have skills field in the official SDK
        assert card.capabilities is not None
        assert "text/plain" in card.defaultInputModes
        assert "application/json" in card.defaultInputModes
    
    def test_build_fastapi_app(self):
        """Test building FastAPI application"""
        agent = EventManagerAgent()
        app = agent.build_fastapi_app()
        
        # Should return a FastAPI instance
        from fastapi import FastAPI
        assert isinstance(app, FastAPI)
    
    def test_factory_function(self):
        """Test the factory function"""
        agent = create_event_manager_agent("Custom Agent")
        
        assert isinstance(agent, EventManagerAgent)
        assert agent.name == "Custom Agent"
        assert agent.version == "1.0.0"


class TestIntegration:
    """Integration tests for the complete system"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_event_workflow(self):
        """Test complete event management workflow"""
        agent = EventManagerAgent()
        handler = agent.request_handler
        
        # 1. Create an event
        create_params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(
                            text="create event"
                        )
                    )
                ]
            )
        )
        
        create_response = await handler.on_message_send(create_params)
        assert isinstance(create_response, Message)
        assert create_response.role == "agent"
        assert "create_event" in create_response.parts[0].root.text
        
        # 2. List events 
        list_params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(
                            text="list events"
                        )
                    )
                ]
            )
        )
        
        list_response = await handler.on_message_send(list_params)
        assert isinstance(list_response, Message)
        assert list_response.role == "agent"
        assert "list_events" in list_response.parts[0].root.text