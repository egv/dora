"""Message parser for extracting event search parameters from chat messages."""

import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

from pydantic import BaseModel, Field
from agents import Agent, ModelSettings, Runner, set_default_openai_key

logger = logging.getLogger(__name__)


class ParsedQuery(BaseModel):
    """Parsed query parameters from chat messages."""
    city: str = Field(..., description="City to search for events")
    events_count: int = Field(10, description="Number of events to find")
    days_ahead: int = Field(14, description="Number of days ahead to search")
    event_types: Optional[List[str]] = Field(None, description="Specific event types to search for")
    language: Optional[str] = Field(None, description="Preferred response language")
    date_range: Optional[Tuple[datetime, datetime]] = Field(None, description="Specific date range if mentioned")


class MessageParser:
    """Parser for extracting event search parameters from chat messages."""
    
    def __init__(self, openai_api_key: str):
        """Initialize the parser."""
        self.openai_api_key = openai_api_key
        set_default_openai_key(openai_api_key)
        self._parser_agent = None
    
    def _create_parser_agent(self) -> Agent:
        """Create an agent for parsing messages."""
        instructions = """
        You are a message parser that extracts event search parameters from user messages.
        
        From the user's message, extract:
        1. City name (REQUIRED) - The city where events should be found
        2. Number of events (default: 10) - How many events to find
        3. Days ahead (default: 14) - How many days in the future to search
        4. Event types (optional) - Specific types like concerts, sports, festivals
        5. Language (optional) - Preferred language for response
        
        Common patterns:
        - "events in Paris" -> city: Paris
        - "10 concerts in London" -> city: London, events_count: 10, event_types: ["concerts"]
        - "what's happening in Tokyo next week" -> city: Tokyo, days_ahead: 7
        - "find 5 events in Berlin for the next 3 days" -> city: Berlin, events_count: 5, days_ahead: 3
        - "festivals in Barcelona this weekend" -> city: Barcelona, event_types: ["festivals"], days_ahead: 3
        
        If no city is clearly mentioned, return None for city.
        Always provide reasonable defaults for missing parameters.
        """
        
        return Agent(
            name="MessageParser",
            instructions=instructions,
            model="gpt-3.5-turbo",
            model_settings=ModelSettings(temperature=0),
            output_type=ParsedQuery
        )
    
    async def parse_llm(self, messages: List[Dict[str, str]]) -> Optional[ParsedQuery]:
        """Parse messages using LLM."""
        if not self._parser_agent:
            self._parser_agent = self._create_parser_agent()
        
        # Get the last user message
        user_messages = [msg for msg in messages if msg.get("role") == "user"]
        if not user_messages:
            return None
        
        last_message = user_messages[-1].get("content", "")
        
        # Add context from previous messages if available
        context = ""
        if len(messages) > 1:
            context = "Previous conversation:\n"
            for msg in messages[:-1]:
                context += f"{msg.get('role', 'unknown')}: {msg.get('content', '')}\n"
            context += "\nCurrent message to parse:\n"
        
        prompt = f"{context}{last_message}"
        
        try:
            result = await Runner.run(self._parser_agent, prompt)
            return result.final_output
        except Exception as e:
            logger.error(f"LLM parsing failed: {e}")
            return None
    
    def parse_regex(self, text: str) -> Optional[ParsedQuery]:
        """Parse message using regex patterns (fallback)."""
        # Normalize text
        text_lower = text.lower()
        
        # Extract city using common patterns
        city = None
        city_patterns = [
            r"(?:events?|concerts?|festivals?|shows?|happening) (?:in|at|near) ([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)",
            r"(?:find|show me|search|look for|what's happening in) ([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)",
            r"in ([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)",
        ]
        
        for pattern in city_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                city = match.group(1).strip()
                # Clean up common suffixes
                suffix_pattern = r'\s*(?:events?|concerts?|festivals?|shows?|next|this|for|tomorrow|today|\d+|days?).*$'
                city = re.sub(suffix_pattern, '', city, flags=re.IGNORECASE).strip()
                # Validate it's a proper city name (starts with capital letter)
                if city and city[0].isupper():
                    break
                else:
                    city = None
        
        if not city:
            return None
        
        # Extract event count
        events_count = 10
        count_match = re.search(r'(\d+)\s*(?:events?|concerts?|festivals?|shows?)', text_lower)
        if count_match:
            events_count = min(int(count_match.group(1)), 50)  # Cap at 50
        
        # Extract time range
        days_ahead = 14
        time_patterns = [
            (r'next (\d+) days?', lambda m: int(m.group(1))),
            (r'(?:for|in) (\d+) days?', lambda m: int(m.group(1))),
            (r'next week', lambda m: 7),
            (r'this week(?:end)?', lambda m: 3),
            (r'tomorrow', lambda m: 1),
            (r'today', lambda m: 1),
            (r'next month', lambda m: 30),
        ]
        
        for pattern, extractor in time_patterns:
            match = re.search(pattern, text_lower)
            if match:
                days_ahead = extractor(match)
                break
        
        # Extract event types
        event_types = []
        type_keywords = ['concerts', 'festivals', 'sports', 'theater', 'exhibitions', 'shows', 'cultural']
        for keyword in type_keywords:
            if keyword in text_lower:
                event_types.append(keyword.rstrip('s'))  # Remove plural
        
        return ParsedQuery(
            city=city.title(),
            events_count=events_count,
            days_ahead=days_ahead,
            event_types=event_types if event_types else None
        )
    
    async def parse(self, messages: List[Dict[str, str]]) -> Optional[ParsedQuery]:
        """Parse messages to extract event search parameters."""
        # Try LLM parsing first
        result = await self.parse_llm(messages)
        
        if result and result.city:
            return result
        
        # Fallback to regex parsing
        user_messages = [msg for msg in messages if msg.get("role") == "user"]
        if user_messages:
            last_message = user_messages[-1].get("content", "")
            result = self.parse_regex(last_message)
            if result:
                return result
        
        return None