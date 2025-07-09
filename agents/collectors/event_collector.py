"""
Event Collector - Integrates with EventSearchAgent via A2A protocol
"""

import json
import httpx
import structlog
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from a2a.types import Message, MessageSendParams, Part, TextPart


logger = structlog.get_logger(__name__)


class EventCollector:
    """Collects event data from EventSearchAgent via A2A protocol"""
    
    def __init__(self, event_search_agent_url: str = "http://localhost:8001"):
        """
        Initialize EventCollector
        
        Args:
            event_search_agent_url: URL of the EventSearchAgent
        """
        self.agent_url = event_search_agent_url
        self.logger = logger.bind(component="event_collector")
        self.a2a_endpoint = f"{self.agent_url}/"  # A2A FastAPI app uses root endpoint
        
        # Retry configuration
        self.max_retries = 3
        self.base_delay = 1.0  # seconds
        self.max_delay = 10.0  # seconds
        self.timeout = 30.0  # seconds
    
    async def _retry_with_backoff(self, operation, *args, **kwargs):
        """Execute operation with exponential backoff retry logic"""
        for attempt in range(self.max_retries):
            try:
                return await operation(*args, **kwargs)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if attempt == self.max_retries - 1:
                    # Last attempt failed, re-raise the exception
                    raise e
                
                # Calculate delay with exponential backoff
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                
                self.logger.warning(
                    "Request failed, retrying",
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    delay=delay,
                    error=str(e)
                )
                
                await asyncio.sleep(delay)
        
        # This should never be reached, but just in case
        raise Exception("Max retries exceeded")
    
    async def _make_event_request(
        self, 
        location: str, 
        date: datetime,
        events_count: int,
        days_ahead: int
    ) -> List[Dict[str, Any]]:
        """Make HTTP request to EventSearchAgent with A2A protocol"""
        # Create A2A message data
        message_data = {
            "city": location,
            "events_count": events_count,
            "days_ahead": days_ahead
        }
        
        # Create proper A2A JSON-RPC request structure
        request_id = str(uuid4())
        message = {
            "id": request_id,
            "params": {
                "message": {
                    "messageId": str(uuid4()),
                    "role": "user",
                    "parts": [
                        {
                            "text": json.dumps(message_data)
                        }
                    ]
                }
            }
        }
        
        # Make HTTP request to EventSearchAgent
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.a2a_endpoint,
                json=message,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                self.logger.error(
                    "EventSearchAgent request failed",
                    status_code=response.status_code,
                    response_text=response.text
                )
                raise httpx.HTTPStatusError(
                    f"HTTP {response.status_code}",
                    request=response.request,
                    response=response
                )
            
            # Parse A2A JSON-RPC response
            result = response.json()
            
            # Extract events from A2A JSON-RPC response
            if "result" in result and "parts" in result["result"]:
                message = result["result"]
                if "parts" in message:
                    for part in message["parts"]:
                        if "text" in part:
                            try:
                                data = json.loads(part["text"])
                                events = data.get("events", [])
                                
                                # Transform events to our format
                                transformed_events = []
                                for event in events:
                                    transformed_event = {
                                        "name": event.get("name", "Unknown Event"),
                                        "description": event.get("description", ""),
                                        "location": event.get("location", f"Unknown, {location}"),
                                        "start_time": event.get("start_date", event.get("start_time", date.isoformat())),
                                        "end_time": event.get("end_date", event.get("end_time", date.isoformat())),
                                        "category": self._categorize_event(event.get("name", "")),
                                        "attendance_estimate": self._estimate_attendance(event.get("name", "")),
                                        "source": "EventSearchAgent",
                                        "url": event.get("url", "")
                                    }
                                    transformed_events.append(transformed_event)
                                
                                self.logger.info(
                                    "Successfully collected events",
                                    location=location,
                                    event_count=len(transformed_events)
                                )
                                
                                return transformed_events
                            except json.JSONDecodeError:
                                self.logger.error("Failed to parse event data from response")
                                raise json.JSONDecodeError("Invalid JSON in event data", "", 0)
            
            # If we couldn't parse events, raise an error
            self.logger.error("Could not parse events from EventSearchAgent response")
            raise ValueError("Invalid response format from EventSearchAgent")
    
    async def collect_events(
        self, 
        location: str, 
        date: datetime,
        events_count: int = 10,
        days_ahead: int = 14
    ) -> List[Dict[str, Any]]:
        """
        Collect events from EventSearchAgent
        
        Args:
            location: City/location to search events
            date: Date to search around
            events_count: Number of events to retrieve
            days_ahead: How many days ahead to search
            
        Returns:
            List of event dictionaries
        """
        self.logger.info(
            "Collecting events from EventSearchAgent",
            location=location,
            date=date.isoformat(),
            events_count=events_count
        )
        
        try:
            # Use retry logic for the HTTP request
            return await self._retry_with_backoff(
                self._make_event_request,
                location,
                date,
                events_count,
                days_ahead
            )
                
        except Exception as e:
            self.logger.error(
                "Error collecting events after retries - no fallback available",
                error=str(e),
                location=location,
                agent_url=self.agent_url
            )
            return []
    
    def _categorize_event(self, event_name: str) -> str:
        """Categorize event based on name"""
        event_name_lower = event_name.lower()
        
        if any(word in event_name_lower for word in ["concert", "music", "band", "orchestra"]):
            return "music"
        elif any(word in event_name_lower for word in ["market", "fair", "bazaar"]):
            return "market"
        elif any(word in event_name_lower for word in ["sport", "game", "match", "marathon", "race"]):
            return "sports"
        elif any(word in event_name_lower for word in ["art", "gallery", "exhibition", "museum"]):
            return "art"
        elif any(word in event_name_lower for word in ["food", "restaurant", "culinary", "wine"]):
            return "food"
        elif any(word in event_name_lower for word in ["tech", "conference", "summit", "meetup"]):
            return "technology"
        elif any(word in event_name_lower for word in ["festival", "celebration", "carnival"]):
            return "festival"
        else:
            return "general"
    
    def _estimate_attendance(self, event_name: str) -> int:
        """Estimate attendance based on event type"""
        event_name_lower = event_name.lower()
        
        if any(word in event_name_lower for word in ["festival", "marathon", "parade"]):
            return 5000
        elif any(word in event_name_lower for word in ["concert", "game", "match"]):
            return 2000
        elif any(word in event_name_lower for word in ["conference", "summit"]):
            return 500
        elif any(word in event_name_lower for word in ["market", "fair"]):
            return 300
        elif any(word in event_name_lower for word in ["exhibition", "gallery"]):
            return 100
        else:
            return 150
    
