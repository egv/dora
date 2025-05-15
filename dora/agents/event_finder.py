"""Event finder agent implementation using Perplexity API."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Type

import httpx
from openai._types import NotGiven, NOT_GIVEN

from dora.agents.base import BaseAgent
from dora.models.config import DoraConfig
from dora.models.event import Event
from dora.models.messages import FindEventsRequest, FindEventsResponse

logger = logging.getLogger(__name__)


class EventFinderAgent(BaseAgent):
    """Agent that finds events in a city using Perplexity API."""

    def __init__(self, config: DoraConfig):
        """Initialize the event finder agent.
        
        Args:
            config: The application configuration
        """
        super().__init__(
            name="EventFinder",
            config=config.event_finder_config,
            api_config=config.get_api_config(),
        )
        
        self.perplexity_api_key = config.perplexity_api_key
        
        if not self.perplexity_api_key:
            logger.warning("Perplexity API key not provided, some functionality may be limited")

    def _query_perplexity(self, query: str) -> Dict[str, Any]:
        """Query the Perplexity API.
        
        Args:
            query: The query to send to Perplexity
            
        Returns:
            The Perplexity API response
            
        Raises:
            Exception: If there's an error with the API request
        """
        if not self.perplexity_api_key:
            raise ValueError("Perplexity API key is required")
        
        url = "https://api.perplexity.ai/chat/completions"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.perplexity_api_key}",
        }
        
        data = {
            "model": "pplx-7b-online",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that helps find events."},
                {"role": "user", "content": query},
            ],
        }
        
        try:
            response = httpx.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.exception(f"Error querying Perplexity API: {e}")
            raise Exception(f"Perplexity API error: {str(e)}")

    def _format_events_query(self, city: str, days_ahead: int) -> str:
        """Format a query for events in a city.
        
        Args:
            city: The city to search for events
            days_ahead: Number of days ahead to search
            
        Returns:
            The formatted query
        """
        today = datetime.now().strftime("%Y-%m-%d")
        future_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        
        return (
            f"Find major events, concerts, festivals, sports events, and cultural events in {city} "
            f"from {today} to {future_date}. For each event, provide: "
            "1. Event name, 2. Description, 3. Location, 4. Date and time, 5. URL or where to find more info. "
            "Format as JSON array with fields: name, description, location, start_date, end_date (if available), url (if available). "
            "Use ISO format for dates (YYYY-MM-DD) and include time if available. "
            "Only include events that are confirmed to be happening."
        )

    def _parse_perplexity_response(self, response: Dict[str, Any], city: str) -> List[Event]:
        """Parse the Perplexity API response to extract events.
        
        Args:
            response: The Perplexity API response
            city: The city the events are in
            
        Returns:
            List of Event objects
        """
        try:
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Try to extract JSON from the response content
            # Look for JSON array in the content
            json_start = content.find("[")
            json_end = content.rfind("]") + 1
            
            if json_start == -1 or json_end == 0:
                logger.warning("Could not find JSON array in Perplexity response")
                
                # Try to use a more flexible approach to extract JSON
                # Create a tool call for OpenAI to extract structured data
                extraction_prompt = f"""
                I received this response about events in {city}, but it's not in a structured format:
                
                {content}
                
                Please extract the events from this text and format them as a JSON array with these fields:
                - name
                - description
                - location
                - start_date (ISO format YYYY-MM-DD)
                - end_date (ISO format YYYY-MM-DD, optional)
                - url (optional)
                
                Return only the JSON array, nothing else.
                """
                
                extraction_messages = self._create_prompt(extraction_prompt)
                extraction_response = self._call_llm(extraction_messages)
                
                extracted_content = extraction_response.get("choices", [{}])[0].get("message", {}).get("content", "")
                json_start = extracted_content.find("[")
                json_end = extracted_content.rfind("]") + 1
                
                if json_start == -1 or json_end == 0:
                    logger.error("Could not extract JSON from extraction response")
                    return []
                
                json_str = extracted_content[json_start:json_end]
            else:
                json_str = content[json_start:json_end]
            
            events_data = json.loads(json_str)
            
            events = []
            for event_data in events_data:
                # Parse dates
                try:
                    start_date = datetime.fromisoformat(event_data.get("start_date"))
                except (ValueError, TypeError):
                    # Try to parse with more flexible format handling
                    try:
                        start_date = datetime.strptime(event_data.get("start_date"), "%Y-%m-%d")
                    except (ValueError, TypeError):
                        logger.warning(f"Could not parse start date for event: {event_data.get('name')}")
                        continue  # Skip events without valid dates
                
                end_date = None
                if "end_date" in event_data and event_data.get("end_date"):
                    try:
                        end_date = datetime.fromisoformat(event_data.get("end_date"))
                    except (ValueError, TypeError):
                        try:
                            end_date = datetime.strptime(event_data.get("end_date"), "%Y-%m-%d")
                        except (ValueError, TypeError):
                            # It's okay if end_date can't be parsed, it's optional
                            pass
                
                event = Event(
                    name=event_data.get("name", "Unknown Event"),
                    description=event_data.get("description", "No description available"),
                    location=event_data.get("location", "Unknown Location"),
                    city=city,
                    start_date=start_date,
                    end_date=end_date,
                    url=event_data.get("url"),
                )
                
                events.append(event)
            
            return events
            
        except Exception as e:
            logger.exception(f"Error parsing Perplexity response: {e}")
            return []

    def process(self, request: FindEventsRequest, response_model: Type[FindEventsResponse]) -> FindEventsResponse:
        """Find events in a city.
        
        Args:
            request: The request containing the city to search
            response_model: The response model type
            
        Returns:
            The response containing found events
        """
        logger.info(f"Finding events in {request.city} for the next {request.days_ahead} days")
        
        try:
            if not self.perplexity_api_key:
                # Fallback to OpenAI if Perplexity API key is not available
                return self._process_with_openai(request, response_model)
            
            query = self._format_events_query(request.city, request.days_ahead)
            perplexity_response = self._query_perplexity(query)
            
            events = self._parse_perplexity_response(perplexity_response, request.city)
            
            logger.info(f"Found {len(events)} events in {request.city}")
            
            return FindEventsResponse(
                city=request.city,
                events=events,
            )
            
        except Exception as e:
            logger.exception(f"Error finding events in {request.city}")
            return FindEventsResponse(
                city=request.city,
                error=f"Error finding events: {str(e)}",
            )

    def _process_with_openai(self, request: FindEventsRequest, response_model: Type[FindEventsResponse]) -> FindEventsResponse:
        """Fallback to OpenAI if Perplexity API is not available.
        
        Args:
            request: The request containing the city to search
            response_model: The response model type
            
        Returns:
            The response containing found events
        """
        logger.info(f"Using OpenAI fallback for finding events in {request.city}")
        
        try:
            query = self._format_events_query(request.city, request.days_ahead)
            
            messages = self._create_prompt(query)
            
            # Define a function to return events in proper format
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "return_events",
                        "description": "Return a list of events in the city",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "events": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "description": {"type": "string"},
                                            "location": {"type": "string"},
                                            "start_date": {"type": "string", "format": "date-time"},
                                            "end_date": {"type": "string", "format": "date-time"},
                                            "url": {"type": "string"},
                                        },
                                        "required": ["name", "description", "location", "start_date"]
                                    }
                                }
                            },
                            "required": ["events"]
                        }
                    }
                }
            ]
            
            response = self._call_llm(messages, tools)
            
            tool_calls = response.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
            
            if not tool_calls:
                return FindEventsResponse(
                    city=request.city,
                    error="Could not find events (no tool calls returned)",
                )
            
            events_data = json.loads(tool_calls[0].get("function", {}).get("arguments", "{}"))
            
            events = []
            for event_data in events_data.get("events", []):
                # Parse dates
                try:
                    start_date = datetime.fromisoformat(event_data.get("start_date"))
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse start date for event: {event_data.get('name')}")
                    continue  # Skip events without valid dates
                
                end_date = None
                if "end_date" in event_data and event_data.get("end_date"):
                    try:
                        end_date = datetime.fromisoformat(event_data.get("end_date"))
                    except (ValueError, TypeError):
                        pass
                
                event = Event(
                    name=event_data.get("name", "Unknown Event"),
                    description=event_data.get("description", "No description available"),
                    location=event_data.get("location", "Unknown Location"),
                    city=request.city,
                    start_date=start_date,
                    end_date=end_date,
                    url=event_data.get("url"),
                )
                
                events.append(event)
            
            logger.info(f"Found {len(events)} events in {request.city} using OpenAI fallback")
            
            return FindEventsResponse(
                city=request.city,
                events=events,
            )
            
        except Exception as e:
            logger.exception(f"Error finding events with OpenAI in {request.city}")
            return FindEventsResponse(
                city=request.city,
                error=f"Error finding events with OpenAI: {str(e)}",
            )