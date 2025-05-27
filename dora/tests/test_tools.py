"""Test the tools module."""

import pytest
from unittest.mock import MagicMock, patch

from dora.tools import (
    perplexity_search,
    EventSearchResult,
    EventData,
    AudienceData,
    EventClassification,
    LanguageList,
    NotificationData,
)


class TestPerplexitySearch:
    """Test the perplexity_search function."""
    
    def test_no_api_key(self):
        """Test search without API key."""
        result = perplexity_search("test query", "")
        assert isinstance(result, EventSearchResult)
        assert result.content == ""
        assert result.error == "Perplexity API key is not configured"
    
    @patch('httpx.Client')
    def test_successful_search(self, mock_client_class):
        """Test successful search."""
        # Mock the response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Event 1: Concert at Madison Square Garden..."
                }
            }]
        }
        
        # Mock the client
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        result = perplexity_search("Find events in New York", "test_api_key")
        
        assert isinstance(result, EventSearchResult)
        assert result.content == "Event 1: Concert at Madison Square Garden..."
        assert result.error is None
    
    @patch('httpx.Client')
    def test_rate_limiting(self, mock_client_class):
        """Test rate limiting with retry."""
        # Mock rate limit response, then success
        mock_rate_limit_response = MagicMock()
        mock_rate_limit_response.status_code = 429
        mock_rate_limit_response.headers = {'Retry-After': '0.1'}
        
        mock_success_response = MagicMock()
        mock_success_response.status_code = 200
        mock_success_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Events found after retry"
                }
            }]
        }
        
        # Mock the client
        mock_client = MagicMock()
        mock_client.post.side_effect = [mock_rate_limit_response, mock_success_response]
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        result = perplexity_search("Find events", "test_api_key", max_retries=2, initial_delay=0.1)
        
        assert isinstance(result, EventSearchResult)
        assert result.content == "Events found after retry"
        assert result.error is None
        assert mock_client.post.call_count == 2
    
    @patch('httpx.Client')
    def test_server_error_with_retry(self, mock_client_class):
        """Test server error with retry."""
        # Mock server error response
        mock_error_response = MagicMock()
        mock_error_response.status_code = 500
        mock_error_response.raise_for_status.side_effect = Exception("Server error")
        
        # Mock the client
        mock_client = MagicMock()
        mock_client.post.return_value = mock_error_response
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        result = perplexity_search("Find events", "test_api_key", max_retries=2, initial_delay=0.01)
        
        assert isinstance(result, EventSearchResult)
        assert result.content == ""
        assert "Server error" in result.error
        assert mock_client.post.call_count == 2  # Should retry once
    
    @patch('httpx.Client')
    def test_timeout_with_retry(self, mock_client_class):
        """Test timeout with retry."""
        import httpx
        
        # Mock the client
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.TimeoutException("Request timeout")
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        result = perplexity_search("Find events", "test_api_key", max_retries=2, initial_delay=0.01)
        
        assert isinstance(result, EventSearchResult)
        assert result.content == ""
        assert "Request timeout" in result.error
        assert mock_client.post.call_count == 2


class TestDataModels:
    """Test the Pydantic models."""
    
    def test_event_data(self):
        """Test EventData model."""
        event = EventData(
            name="Test Concert",
            description="A great concert",
            location="Madison Square Garden",
            start_date="2025-05-30"
        )
        assert event.name == "Test Concert"
        assert event.end_date is None
        assert event.url is None
    
    def test_audience_data(self):
        """Test AudienceData model."""
        audience = AudienceData(
            gender="All",
            age_range="18-35",
            income_level="Medium",
            other_attributes=["Music lovers", "Tech enthusiasts"]
        )
        assert audience.gender == "All"
        assert len(audience.other_attributes) == 2
    
    def test_event_classification(self):
        """Test EventClassification model."""
        audience1 = AudienceData(age_range="18-35")
        audience2 = AudienceData(age_range="35-50")
        
        classification = EventClassification(
            size="Large",
            importance="High",
            target_audiences=[audience1, audience2]
        )
        assert classification.size == "Large"
        assert len(classification.target_audiences) == 2
    
    def test_language_list(self):
        """Test LanguageList model."""
        languages = LanguageList(languages=["English", "Spanish", "French"])
        assert len(languages.languages) == 3
        assert "Spanish" in languages.languages
    
    def test_notification_data(self):
        """Test NotificationData model."""
        audience = AudienceData(age_range="25-40")
        notification = NotificationData(
            language="English",
            audience=audience,
            text="Don't miss the concert this weekend!"
        )
        assert notification.language == "English"
        assert notification.audience.age_range == "25-40"