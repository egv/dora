"""
Test Event Search Agent
"""

import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from agents.event_search import (
    EventSearchAgent,
    EventSearchExecutor,
    EventSearchRequestHandler,
    create_event_search_agent
)
from a2a.types import (
    Message,
    MessageSendParams,
    Part,
    TextPart,
    TaskState,
    TaskQueryParams
)


@pytest.fixture
def event_search_agent():
    """Create test event search agent"""
    return create_event_search_agent(events_count=5)


@pytest.fixture
def event_search_executor():
    """Create test event search executor"""
    return EventSearchExecutor(events_count=3)


@pytest.fixture
def event_search_handler(event_search_executor):
    """Create test event search request handler"""
    return EventSearchRequestHandler(event_search_executor)


class TestEventSearchAgent:
    """Test EventSearchAgent functionality"""
    
    def test_agent_initialization(self, event_search_agent):
        """Test agent initializes correctly"""
        assert event_search_agent.name == "Event Search"
        assert event_search_agent.version == "1.0.0"
        assert event_search_agent.events_count == 5
        assert len(event_search_agent.skills) == 1
        assert event_search_agent.skills[0].id == "search_events"
        
    def test_agent_card_structure(self, event_search_agent):
        """Test agent card is properly structured"""
        card = event_search_agent.agent_card
        assert card.name == "Event Search"
        assert card.description == "Agent that searches for upcoming events in cities using web search"
        assert card.url == "http://localhost:8001"
        assert "application/json" in card.defaultOutputModes
        assert len(card.skills) == 1
        
    def test_build_fastapi_app(self, event_search_agent):
        """Test FastAPI app can be built"""
        app = event_search_agent.build_fastapi_app()
        assert app is not None
        # FastAPI app should have routes
        assert hasattr(app, 'routes')


class TestEventSearchExecutor:
    """Test EventSearchExecutor functionality"""
    
    @pytest.mark.asyncio
    async def test_search_events_basic(self, event_search_executor):
        """Test basic event search functionality"""
        params = {"city": "San Francisco"}
        
        # Mock the web search tool
        with patch.object(event_search_executor.web_search_tool, 'run', new_callable=AsyncMock) as mock_search:
            mock_search.return_value = "Mock search results"
            
            result = await event_search_executor._search_events(params)
            
            # Verify search was called
            mock_search.assert_called_once()
            
            # Verify result structure
            assert "events" in result
            assert "count" in result
            assert "city" in result
            assert result["city"] == "San Francisco"
            assert isinstance(result["events"], list)
            assert result["count"] == len(result["events"])
            assert result["count"] <= 3  # Limited by events_count
    
    @pytest.mark.asyncio
    async def test_search_events_with_parameters(self, event_search_executor):
        """Test event search with custom parameters"""
        params = {
            "city": "New York",
            "events_count": 2,
            "days_ahead": 7
        }
        
        with patch.object(event_search_executor.web_search_tool, 'run', new_callable=AsyncMock) as mock_search:
            mock_search.return_value = "Mock search results"
            
            result = await event_search_executor._search_events(params)
            
            assert result["city"] == "New York"
            assert result["count"] <= 2  # Limited by requested count
    
    @pytest.mark.asyncio
    async def test_search_events_missing_city(self, event_search_executor):
        """Test error handling when city is missing"""
        params = {}
        
        with pytest.raises(ValueError, match="City parameter is required"):
            await event_search_executor._search_events(params)
    
    @pytest.mark.asyncio
    async def test_search_events_web_search_failure(self, event_search_executor):
        """Test handling of web search failures"""
        params = {"city": "TestCity"}
        
        with patch.object(event_search_executor.web_search_tool, 'run', new_callable=AsyncMock) as mock_search:
            mock_search.side_effect = Exception("Search failed")
            
            result = await event_search_executor._search_events(params)
            
            # Should return empty results with error info
            assert result["events"] == []
            assert result["count"] == 0
            assert "error" in result
    
    def test_parse_events_from_search(self, event_search_executor):
        """Test parsing events from search results"""
        search_results = "Mock search results"
        city = "TestCity"
        max_events = 3
        
        events = event_search_executor._parse_events_from_search(
            search_results, city, max_events
        )
        
        assert isinstance(events, list)
        assert len(events) <= max_events
        
        # Check event structure
        for event in events:
            assert "name" in event
            assert "description" in event
            assert "location" in event
            assert "start_date" in event
            assert "end_date" in event
            assert "url" in event
            assert city in event["location"]  # City should be in location


class TestEventSearchRequestHandler:
    """Test EventSearchRequestHandler functionality"""
    
    @pytest.mark.asyncio
    async def test_on_message_send_json_input(self, event_search_handler):
        """Test message handling with JSON input"""
        # Create message with JSON city parameter
        message_data = {"city": "Paris", "events_count": 2}
        
        params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(
                            text=json.dumps(message_data)
                        )
                    )
                ]
            )
        )
        
        with patch.object(event_search_handler.executor, '_search_events', new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {
                "events": [{"name": "Test Event"}],
                "count": 1,
                "city": "Paris"
            }
            
            response = await event_search_handler.on_message_send(params)
            
            # Verify search was called with correct parameters
            mock_search.assert_called_once_with(message_data)
            
            # Verify response structure
            assert response.role == "agent"
            assert len(response.parts) == 1
            assert hasattr(response.parts[0].root, 'text')
            
            # Parse response text as JSON
            response_data = json.loads(response.parts[0].root.text)
            assert response_data["city"] == "Paris"
            assert response_data["count"] == 1
    
    @pytest.mark.asyncio
    async def test_on_message_send_text_input(self, event_search_handler):
        """Test message handling with plain text input"""
        params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(
                            text="Tokyo"
                        )
                    )
                ]
            )
        )
        
        with patch.object(event_search_handler.executor, '_search_events', new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {
                "events": [],
                "count": 0,
                "city": "Tokyo"
            }
            
            response = await event_search_handler.on_message_send(params)
            
            # Verify search was called with city extracted from text
            mock_search.assert_called_once_with({"city": "Tokyo"})
            
            assert response.role == "agent"
    
    @pytest.mark.asyncio
    async def test_on_message_send_error_handling(self, event_search_handler):
        """Test error handling in message processing"""
        params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(
                            text='{"city": "ErrorCity"}'
                        )
                    )
                ]
            )
        )
        
        with patch.object(event_search_handler.executor, '_search_events', new_callable=AsyncMock) as mock_search:
            mock_search.side_effect = Exception("Search failed")
            
            response = await event_search_handler.on_message_send(params)
            
            # Should return error message
            assert response.role == "agent"
            assert "Failed to search events" in response.parts[0].root.text
    
    @pytest.mark.asyncio
    async def test_task_management(self, event_search_handler):
        """Test task creation and retrieval"""
        # First, create a task by sending a message
        params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(
                            text='{"city": "TestCity"}'
                        )
                    )
                ]
            )
        )
        
        with patch.object(event_search_handler.executor, '_search_events', new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {"events": [], "count": 0, "city": "TestCity"}
            
            response = await event_search_handler.on_message_send(params)
            task_id = response.taskId
            
            # Verify task was created and can be retrieved
            task_query = TaskQueryParams(id=task_id)
            task = await event_search_handler.on_get_task(task_query)
            
            assert task is not None
            assert task.id == task_id
            assert task.status.state == TaskState.completed


class TestIntegration:
    """Integration tests for EventSearchAgent"""
    
    @pytest.mark.asyncio 
    async def test_full_event_search_flow(self):
        """Test complete event search flow"""
        agent = create_event_search_agent(events_count=3)
        
        # Create a mock message
        message_data = {"city": "London", "events_count": 2}
        params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(
                            text=json.dumps(message_data)
                        )
                    )
                ]
            )
        )
        
        # Mock the web search
        with patch.object(agent.executor.web_search_tool, 'run', new_callable=AsyncMock) as mock_search:
            mock_search.return_value = "Mock search results for London events"
            
            # Process the message
            response = await agent.request_handler.on_message_send(params)
            
            # Verify response
            assert response.role == "agent"
            response_data = json.loads(response.parts[0].root.text)
            
            assert response_data["city"] == "London"
            assert response_data["count"] <= 2
            assert isinstance(response_data["events"], list)
            
            # Verify all events have required fields
            for event in response_data["events"]:
                assert "name" in event
                assert "description" in event
                assert "location" in event
                assert "start_date" in event
                assert "end_date" in event
                assert "url" in event
                
                # Verify dates are in the future
                start_date = datetime.fromisoformat(event["start_date"])
                assert start_date.date() >= datetime.now().date()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])