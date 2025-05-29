"""Unit tests for message parser."""

import pytest
from unittest.mock import Mock, AsyncMock

from dora.message_parser import MessageParser, ParsedQuery


class TestMessageParser:
    """Test message parsing functionality."""
    
    @pytest.fixture
    def parser(self):
        """Create a message parser instance."""
        return MessageParser("test-api-key")
    
    def test_parse_regex_simple_city(self, parser):
        """Test parsing simple city queries with regex."""
        test_cases = [
            ("events in Paris", "Paris"),
            ("Events in New York", "New York"),
            ("concerts in London", "London"),
            ("What's happening in Tokyo?", "Tokyo"),
            ("find events in Berlin", "Berlin"),
            ("Show me events in San Francisco", "San Francisco"),
        ]
        
        for query, expected_city in test_cases:
            result = parser.parse_regex(query)
            assert result is not None, f"Failed to parse: {query}"
            assert result.city == expected_city, f"Expected {expected_city}, got {result.city}"
    
    def test_parse_regex_with_count(self, parser):
        """Test parsing queries with event count."""
        test_cases = [
            ("5 events in Paris", 5),
            ("Show me 10 concerts in London", 10),
            ("Find 3 festivals in Barcelona", 3),
            ("events in Berlin", 10),  # Default
        ]
        
        for query, expected_count in test_cases:
            result = parser.parse_regex(query)
            assert result is not None, f"Failed to parse: {query}"
            assert result.events_count == expected_count, f"Expected {expected_count}, got {result.events_count}"
    
    def test_parse_regex_with_time_range(self, parser):
        """Test parsing queries with time ranges."""
        test_cases = [
            ("events in Paris next 5 days", 5),
            ("events in London for 3 days", 3),
            ("events in Tokyo next week", 7),
            ("events in Berlin this weekend", 3),
            ("events in Rome tomorrow", 1),
            ("events in Madrid today", 1),
            ("events in Barcelona next month", 30),
            ("events in Amsterdam", 14),  # Default
        ]
        
        for query, expected_days in test_cases:
            result = parser.parse_regex(query)
            assert result is not None, f"Failed to parse: {query}"
            assert result.days_ahead == expected_days, f"Expected {expected_days} days, got {result.days_ahead}"
    
    def test_parse_regex_with_event_types(self, parser):
        """Test parsing queries with event types."""
        result = parser.parse_regex("concerts and festivals in Paris")
        assert result is not None
        assert "concert" in result.event_types
        assert "festival" in result.event_types
        
        result = parser.parse_regex("sports events in London")
        assert result is not None
        assert "sport" in result.event_types
        
        result = parser.parse_regex("events in Berlin")
        assert result is not None
        assert result.event_types is None or len(result.event_types) == 0
    
    def test_parse_regex_no_city(self, parser):
        """Test parsing queries without a city."""
        test_cases = [
            "events tomorrow",
            "5 concerts",
            "what's happening",
            "show me festivals",
        ]
        
        for query in test_cases:
            result = parser.parse_regex(query)
            assert result is None, f"Should not parse query without city: {query}"
    
    def test_parse_regex_complex_queries(self, parser):
        """Test parsing complex queries."""
        result = parser.parse_regex("Find me 5 concerts and festivals in New York for the next 3 days")
        assert result is not None
        assert result.city == "New York"
        assert result.events_count == 5
        assert result.days_ahead == 3
        assert "concert" in result.event_types
        assert "festival" in result.event_types
    
    @pytest.mark.asyncio
    async def test_parse_with_messages(self, parser):
        """Test parsing with message history."""
        # Mock the LLM parser to avoid API calls
        parser._message_parser = Mock()
        parser.parse_llm = AsyncMock(return_value=None)
        
        messages = [
            {"role": "user", "content": "events in Paris"}
        ]
        
        result = await parser.parse(messages)
        assert result is not None  # Should fall back to regex
        assert result.city == "Paris"
    
    @pytest.mark.asyncio
    async def test_parse_no_user_messages(self, parser):
        """Test parsing with no user messages."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant"}
        ]
        
        result = await parser.parse(messages)
        assert result is None