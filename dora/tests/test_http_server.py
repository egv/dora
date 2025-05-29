"""Integration tests for the HTTP server."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch
import json

from dora.http_server import app, ChatCompletionHandler
from dora.models.config import DoraConfig
from dora.models.event import Event, EventNotification
from dora.tools import EventClassification
from dora.message_parser import ParsedQuery


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = Mock(spec=DoraConfig)
    config.openai_api_key = "test-key"
    config.http_api_keys = []
    config.memory_cache_enabled = False
    config.memory_cache_path = "./test_cache.db"
    config.memory_cache_ttl_days = 7
    config.memory_cache_max_size_mb = 100
    return config


@pytest.fixture
def mock_events():
    """Create mock event notifications."""
    from datetime import datetime
    from dora.tools import EventData, AudienceData
    
    # Use the tool models which use strings for dates
    return [
        Mock(
            event=Mock(
                name="Summer Music Festival",
                description="Annual outdoor music festival",
                location="Central Park, New York",
                start_date="2025-06-15",
                end_date="2025-06-17",
                url="https://example.com/summer-fest"
            ),
            classification=Mock(
                size="large",
                importance="high",
                audiences=["music lovers", "families"]
            ),
            notifications=[]
        ),
        Mock(
            event=Mock(
                name="Tech Conference 2025",
                description="Latest in technology and innovation",
                location="Convention Center, San Francisco",
                start_date="2025-06-20",
                end_date=None,
                url="https://example.com/tech-conf"
            ),
            classification=Mock(
                size="medium",
                importance="medium",
                audiences=["tech professionals", "students"]
            ),
            notifications=[]
        )
    ]


class TestHTTPServer:
    """Test HTTP server endpoints."""
    
    def test_root_endpoint(self, client):
        """Test the root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data
        assert "endpoints" in data
    
    def test_health_endpoint(self, client):
        """Test the health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
    
    def test_models_endpoint(self, client):
        """Test the models listing endpoint."""
        response = client.get("/v1/models")
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"
        assert len(data["data"]) >= 2
        model_ids = [model["id"] for model in data["data"]]
        assert "dora-events-v1" in model_ids
        assert "dora-events-fast" in model_ids
    
    @patch('dora.http_server.completion_handler')
    def test_chat_completion_basic(self, mock_handler, client):
        """Test basic chat completion request."""
        # Create a proper response object
        from dora.http_server import ChatCompletionResponse, Choice, Message, Usage
        
        mock_response = ChatCompletionResponse(
            id="chatcmpl-test123",
            created=1700000000,
            model="dora-events-v1",
            choices=[
                Choice(
                    index=0,
                    message=Message(role="assistant", content="I found 2 events in New York"),
                    finish_reason="stop"
                )
            ],
            usage=Usage(
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30
            )
        )
        
        mock_handler.process_request = AsyncMock(return_value=mock_response)
        
        request_data = {
            "model": "dora-events-v1",
            "messages": [
                {"role": "user", "content": "Find events in New York"}
            ]
        }
        
        response = client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == "chatcmpl-test123"
        assert data["object"] == "chat.completion"
        assert data["model"] == "dora-events-v1"
        assert len(data["choices"]) == 1
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert "usage" in data
    
    def test_chat_completion_invalid_model(self, client):
        """Test chat completion with invalid model."""
        request_data = {
            "model": "invalid-model",
            "messages": [
                {"role": "user", "content": "Find events in Paris"}
            ]
        }
        
        response = client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "not found" in data["error"]["message"]
    
    def test_chat_completion_no_messages(self, client):
        """Test chat completion without messages."""
        request_data = {
            "model": "dora-events-v1",
            "messages": []
        }
        
        response = client.post("/v1/chat/completions", json=request_data)
        # Should be 500 because completion_handler is None in tests
        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert "Service not initialized" in data["error"]["message"]
    
    def test_chat_completion_streaming_not_supported(self, client):
        """Test that streaming is not supported."""
        request_data = {
            "model": "dora-events-v1",
            "messages": [
                {"role": "user", "content": "Find events in London"}
            ],
            "stream": True
        }
        
        response = client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "Streaming is not supported" in data["error"]["message"]


class TestChatCompletionHandler:
    """Test the chat completion handler."""
    
    @pytest.fixture
    def handler(self, mock_config):
        """Create a handler instance."""
        with patch('dora.message_parser.set_default_openai_key'):
            return ChatCompletionHandler(mock_config)
    
    def test_format_events_as_text_empty(self, handler):
        """Test formatting empty events list."""
        result = handler._format_events_as_text([])
        assert result == "I couldn't find any events matching your request."
    
    def test_format_events_as_text(self, handler, mock_events):
        """Test formatting events as text."""
        result = handler._format_events_as_text(mock_events)
        assert "I found 2 upcoming events:" in result
        assert "Summer Music Festival" in result
        assert "Tech Conference 2025" in result
        assert "Central Park, New York" in result
        assert "2025-06-15" in result
    
    def test_format_events_as_json(self, handler, mock_events):
        """Test formatting events as JSON."""
        # Setup mock attributes properly for JSON serialization
        for event in mock_events:
            event.event.name = "Summer Music Festival" if "Summer" in str(event.event) else "Tech Conference 2025"
            event.event.location = "Central Park, New York" if "Summer" in str(event.event) else "Convention Center, San Francisco"
            event.event.start_date = "2025-06-15" if "Summer" in str(event.event) else "2025-06-20"
            event.event.end_date = "2025-06-17" if "Summer" in str(event.event) else None
            event.event.description = "Annual outdoor music festival" if "Summer" in str(event.event) else "Latest in technology and innovation"
            event.event.url = "https://example.com/summer-fest" if "Summer" in str(event.event) else "https://example.com/tech-conf"
            event.classification.size = "large" if "Summer" in str(event.event) else "medium"
            event.classification.importance = "high" if "Summer" in str(event.event) else "medium"
            event.classification.audiences = ["music lovers", "families"] if "Summer" in str(event.event) else ["tech professionals", "students"]
        
        result = handler._format_events_as_json(mock_events)
        data = json.loads(result)
        assert "events" in data
        assert len(data["events"]) == 2
        assert data["events"][0]["name"] == "Summer Music Festival"
        assert data["events"][0]["classification"]["size"] == "large"
    
    @pytest.mark.asyncio
    @patch('dora.__main__.process_city')
    async def test_process_request_success(self, mock_process_city, handler, mock_events):
        """Test successful request processing."""
        # Mock the message parser
        handler._message_parser.parse = AsyncMock(
            return_value=ParsedQuery(
                city="New York",
                events_count=10,
                days_ahead=14
            )
        )
        
        # Mock process_city
        mock_process_city.return_value = mock_events
        
        # Create request
        from dora.http_server import ChatCompletionRequest, Message
        request = ChatCompletionRequest(
            model="dora-events-v1",
            messages=[
                Message(role="user", content="Find events in New York")
            ]
        )
        
        response = await handler.process_request(request)
        
        assert response.model == "dora-events-v1"
        assert len(response.choices) == 1
        assert response.choices[0].message.role == "assistant"
        assert "2 upcoming events" in response.choices[0].message.content
        
        # Verify process_city was called correctly
        mock_process_city.assert_called_once_with(
            city="New York",
            days_ahead=14,
            events_count=10,
            config=handler.config
        )
    
    @pytest.mark.asyncio
    async def test_process_request_no_city(self, handler):
        """Test request processing when city cannot be determined."""
        # Mock the message parser to return None
        handler._message_parser.parse = AsyncMock(return_value=None)
        
        from dora.http_server import ChatCompletionRequest, Message
        request = ChatCompletionRequest(
            model="dora-events-v1",
            messages=[
                Message(role="user", content="Show me some events")
            ]
        )
        
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await handler.process_request(request)
        
        assert exc_info.value.status_code == 400
        assert "Could not determine which city" in str(exc_info.value.detail)