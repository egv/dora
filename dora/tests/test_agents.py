"""Tests for agents."""

import os
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from dora.agents.base import BaseAgent
from dora.agents.event_classifier import EventClassifierAgent
from dora.agents.event_finder import EventFinderAgent
from dora.agents.language_selector import LanguageSelectorAgent
from dora.agents.orchestrator import OrchestratorAgent
from dora.agents.text_writer import TextWriterAgent
from dora.models.config import APIConfig, AgentConfig, DoraConfig
from dora.models.event import (
    AudienceDemographic,
    ClassifiedEvent,
    Event,
    EventImportance,
    EventSize,
)
from dora.models.messages import (
    ClassifyEventRequest,
    ClassifyEventResponse,
    FindEventsRequest,
    FindEventsResponse,
    GenerateNotificationRequest,
    GenerateNotificationResponse,
    GetCityLanguagesRequest,
    GetCityLanguagesResponse,
    ProcessCityRequest,
    ProcessCityResponse,
)


@pytest.fixture
def api_config():
    """Create an API config for testing."""
    return APIConfig(
        openai_api_key="test_openai_key",
        perplexity_api_key="test_perplexity_key",
    )


@pytest.fixture
def agent_config():
    """Create an agent config for testing."""
    return AgentConfig(
        model="gpt-3.5-turbo",
        temperature=0.0,
        system_prompt="You are a test agent",
    )


@pytest.fixture
def sample_event():
    """Create a sample event for testing."""
    return Event(
        name="Test Event",
        description="This is a test event",
        location="Test Location",
        city="Test City",
        start_date=datetime(2023, 10, 1, 10, 0),
        end_date=datetime(2023, 10, 1, 18, 0),
        url="https://example.com/test-event",
    )


@pytest.fixture
def sample_classified_event(sample_event):
    """Create a sample classified event for testing."""
    return ClassifiedEvent(
        event=sample_event,
        size=EventSize.MEDIUM,
        importance=EventImportance.MEDIUM,
        target_audiences=[
            AudienceDemographic(
                gender="any",
                age_range="25-45",
                income_level="middle",
                other_attributes=["test audience"],
            )
        ],
    )


class TestBaseAgent:
    """Tests for the BaseAgent class."""

    def test_init(self, api_config, agent_config):
        """Test the initialization of BaseAgent."""
        agent = BaseAgent("TestAgent", agent_config, api_config)
        assert agent.name == "TestAgent"
        assert agent.config == agent_config
        assert agent.api_config == api_config

    def test_create_prompt(self, api_config, agent_config):
        """Test the _create_prompt method."""
        agent = BaseAgent("TestAgent", agent_config, api_config)
        messages = agent._create_prompt("Test message")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a test agent"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Test message"

    @patch("openai.OpenAI")
    def test_call_llm(self, mock_openai, api_config, agent_config):
        """Test the _call_llm method."""
        # Set up the mock
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_completion = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_completion.model_dump.return_value = {"test": "response"}
        
        agent = BaseAgent("TestAgent", agent_config, api_config)
        result = agent._call_llm([{"role": "user", "content": "test"}])
        
        assert result == {"test": "response"}
        mock_client.chat.completions.create.assert_called_once()

    def test_process_not_implemented(self, api_config, agent_config):
        """Test that process raises NotImplementedError."""
        agent = BaseAgent("TestAgent", agent_config, api_config)
        with pytest.raises(NotImplementedError):
            agent.process(None, None)


@patch("openai.OpenAI")
class TestEventFinderAgent:
    """Tests for the EventFinderAgent class."""

    @patch("httpx.post")
    def test_query_perplexity(self, mock_post, mock_openai, api_config):
        """Test the _query_perplexity method."""
        # Set up the mock
        mock_response = MagicMock()
        mock_response.json.return_value = {"test": "response"}
        mock_post.return_value = mock_response
        
        config = DoraConfig(
            openai_api_key="test_openai_key",
            perplexity_api_key="test_perplexity_key",
        )
        
        agent = EventFinderAgent(config)
        result = agent._query_perplexity("test query")
        
        assert result == {"test": "response"}
        mock_post.assert_called_once()

    def test_format_events_query(self, mock_openai):
        """Test the _format_events_query method."""
        config = DoraConfig(
            openai_api_key="test_openai_key",
            perplexity_api_key="test_perplexity_key",
        )
        
        agent = EventFinderAgent(config)
        query = agent._format_events_query("New York", 7)
        
        assert "New York" in query
        assert "JSON array" in query
        assert "location" in query


@patch("openai.OpenAI")
class TestEventClassifierAgent:
    """Tests for the EventClassifierAgent class."""

    def test_process(self, mock_openai, sample_event):
        """Test the process method with mocked OpenAI."""
        # Set up the mock
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        
        # Mock a successful response with tool calls
        mock_completion = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_completion.model_dump.return_value = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "arguments": '{"size": "MEDIUM", "importance": "HIGH", "target_audiences": [{"gender": "any", "age_range": "25-40", "income_level": "middle", "other_attributes": ["tech enthusiasts"]}]}'
                                }
                            }
                        ]
                    }
                }
            ]
        }
        
        config = DoraConfig(
            openai_api_key="test_openai_key",
        )
        
        agent = EventClassifierAgent(config)
        request = ClassifyEventRequest(event=sample_event)
        response = agent.process(request, ClassifyEventResponse)
        
        assert response.classified_event.event.name == "Test Event"
        assert response.classified_event.size == EventSize.MEDIUM
        assert response.classified_event.importance == EventImportance.HIGH
        assert len(response.classified_event.target_audiences) == 1
        assert "tech enthusiasts" in response.classified_event.target_audiences[0].other_attributes


@patch("openai.OpenAI")
class TestLanguageSelectorAgent:
    """Tests for the LanguageSelectorAgent class."""

    def test_process(self, mock_openai):
        """Test the process method with mocked OpenAI."""
        # Set up the mock
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        
        # Mock a successful response with tool calls
        mock_completion = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_completion.model_dump.return_value = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "arguments": '{"languages": ["English", "Spanish", "Chinese"]}'
                                }
                            }
                        ]
                    }
                }
            ]
        }
        
        config = DoraConfig(
            openai_api_key="test_openai_key",
        )
        
        agent = LanguageSelectorAgent(config)
        request = GetCityLanguagesRequest(city="San Francisco")
        response = agent.process(request, GetCityLanguagesResponse)
        
        assert response.city == "San Francisco"
        assert len(response.languages) == 3
        assert "English" in response.languages
        assert "Spanish" in response.languages
        assert "Chinese" in response.languages


@patch("openai.OpenAI")
class TestTextWriterAgent:
    """Tests for the TextWriterAgent class."""

    def test_process(self, mock_openai, sample_classified_event):
        """Test the process method with mocked OpenAI."""
        # Set up the mock
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        
        # Mock a successful response with tool calls
        mock_completion = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_completion.model_dump.return_value = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "arguments": '{"text": "Don\'t miss Test Event! 10% off taxi rides to Test Location. Limited seats available!"}'
                                }
                            }
                        ]
                    }
                }
            ]
        }
        
        config = DoraConfig(
            openai_api_key="test_openai_key",
        )
        
        agent = TextWriterAgent(config)
        audience = sample_classified_event.target_audiences[0]
        request = GenerateNotificationRequest(
            event=sample_classified_event,
            audience=audience,
            language="English",
        )
        response = agent.process(request, GenerateNotificationResponse)
        
        assert response.notification.language == "English"
        assert response.notification.audience == audience
        assert "10% off taxi" in response.notification.text


@patch("openai.OpenAI")
class TestOrchestratorAgent:
    """Tests for the OrchestratorAgent class."""

    def test_process(self, mock_openai, sample_event, sample_classified_event):
        """Test the process method with mocked agent responses."""
        # Create mocked agents
        event_finder = MagicMock()
        event_finder.process.return_value = FindEventsResponse(
            city="Test City",
            events=[sample_event],
        )
        
        event_classifier = MagicMock()
        event_classifier.process.return_value = ClassifyEventResponse(
            classified_event=sample_classified_event,
        )
        
        language_selector = MagicMock()
        language_selector.process.return_value = GetCityLanguagesResponse(
            city="Test City",
            languages=["English", "Spanish"],
        )
        
        text_writer = MagicMock()
        text_writer.process.return_value = GenerateNotificationResponse(
            notification={
                "language": "English",
                "audience": sample_classified_event.target_audiences[0],
                "text": "Test notification",
            },
        )
        
        config = DoraConfig(
            openai_api_key="test_openai_key",
        )
        
        orchestrator = OrchestratorAgent(
            config=config,
            event_finder=event_finder,
            event_classifier=event_classifier,
            language_selector=language_selector,
            text_writer=text_writer,
        )
        
        request = ProcessCityRequest(city="Test City")
        response = orchestrator.process(request, ProcessCityResponse)
        
        assert response.city == "Test City"
        assert not response.error
        
        # Check that all agents were called with appropriate requests
        event_finder.process.assert_called_once()
        event_classifier.process.assert_called_once()
        language_selector.process.assert_called_once()
        text_writer.process.assert_called()  # Called multiple times