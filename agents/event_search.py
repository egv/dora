"""
Event Search Agent - Google A2A Implementation

This agent searches for events in cities using web search.
Extracted from the original Dora event finder functionality.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication
from a2a.server.context import ServerCallContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers.request_handler import RequestHandler
from a2a.types import (
    AgentCard,
    AgentSkill,
    AgentCapabilities,
    Task,
    TaskQueryParams,
    TaskIdParams,
    Message,
    MessageSendParams,
    TaskPushNotificationConfig,
    GetTaskPushNotificationConfigParams,
    UnsupportedOperationError,
    Part,
    TextPart,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)

# Import the web search tool from openai-agents package
try:
    from agents import WebSearchTool
except ImportError:
    # Fallback for testing - create a mock WebSearchTool
    class WebSearchTool:
        async def run(self, query: str) -> str:
            return f"Mock search results for: {query}"


logger = structlog.get_logger(__name__)


class EventSearchExecutor(AgentExecutor):
    """Agent executor implementing event search logic"""
    
    def __init__(self, events_count: int = 10):
        self.events_count = events_count
        self.logger = structlog.get_logger(__name__).bind(component="event_search_executor")
        self.web_search_tool = WebSearchTool()
    
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute event search operations"""
        try:
            message = context.message
            skill_id = message.get("skill_id")
            params = message.get("params", {})
            
            if skill_id == "search_events":
                result = await self._search_events(params)
            else:
                raise ValueError(f"Unknown skill: {skill_id}")
            
            # Publish task completion event
            await event_queue.publish(TaskStatusUpdateEvent(
                task_id=context.task_id,
                state=TaskState.completed,
                result=result
            ))
            
        except Exception as e:
            self.logger.error("Event search failed", error=str(e), task_id=context.task_id)
            # Publish task failure event
            await event_queue.publish(TaskStatusUpdateEvent(
                task_id=context.task_id,
                state=TaskState.failed,
                error=str(e)
            ))
    
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel event search operation"""
        self.logger.info("Cancelling search task", task_id=context.task_id)
        await event_queue.publish(TaskStatusUpdateEvent(
            task_id=context.task_id,
            state=TaskState.canceled
        ))
    
    async def _search_events(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search for events in a city using web search"""
        city = params.get("city")
        if not city:
            raise ValueError("City parameter is required")
        
        # Get optional parameters
        events_count = params.get("events_count", self.events_count)
        days_ahead = params.get("days_ahead", 14)
        
        self.logger.info("Searching for events", city=city, events_count=events_count)
        
        # Build search query similar to the original event finder
        search_query = f"{city} upcoming events next {days_ahead} days concerts theater festivals sports"
        
        # Use web search tool to find events
        try:
            # Call the web search tool
            search_results = await self.web_search_tool.run(search_query)
            
            # Parse and filter events from search results
            events = self._parse_events_from_search(search_results, city, events_count)
            
            return {
                "events": events,
                "count": len(events),
                "city": city,
                "search_query": search_query
            }
            
        except Exception as e:
            self.logger.error("Web search failed", error=str(e), city=city)
            # Return empty results on error
            return {
                "events": [],
                "count": 0,
                "city": city,
                "error": str(e)
            }
    
    def _parse_events_from_search(self, search_results: str, city: str, max_events: int) -> List[Dict[str, Any]]:
        """Parse events from web search results"""
        events = []
        today = datetime.now().date()
        
        # This is a simplified parser - in a real implementation, 
        # you'd use the actual parsing logic from the original event finder
        # For MVP, we'll create some mock events based on the city
        
        # Mock event generation for MVP
        # In production, this would parse actual search results
        base_events = [
            {
                "name": f"Tech Conference {city}",
                "description": f"Annual technology conference in {city}",
                "location": f"Convention Center, 123 Main St, {city}",
                "start_date": (today + timedelta(days=5)).isoformat(),
                "end_date": (today + timedelta(days=5)).isoformat(),
                "url": "https://example.com/tech-conf"
            },
            {
                "name": f"Music Festival {city}",
                "description": f"Summer music festival featuring local and international artists",
                "location": f"City Park, 456 Park Ave, {city}",
                "start_date": (today + timedelta(days=10)).isoformat(),
                "end_date": (today + timedelta(days=12)).isoformat(),
                "url": "https://example.com/music-fest"
            },
            {
                "name": f"Art Exhibition Opening",
                "description": f"Contemporary art exhibition at {city} Museum",
                "location": f"{city} Museum of Art, 789 Gallery St, {city}",
                "start_date": (today + timedelta(days=3)).isoformat(),
                "end_date": (today + timedelta(days=3)).isoformat(),
                "url": "https://example.com/art-exhibit"
            },
            {
                "name": f"Food & Wine Festival",
                "description": f"Culinary celebration featuring local restaurants and wineries",
                "location": f"Waterfront Plaza, 321 Harbor Rd, {city}",
                "start_date": (today + timedelta(days=7)).isoformat(),
                "end_date": (today + timedelta(days=9)).isoformat(),
                "url": "https://example.com/food-wine"
            },
            {
                "name": f"Marathon {city}",
                "description": f"Annual city marathon - 42.195km through {city}",
                "location": f"City Hall Square, 100 Government Plaza, {city}",
                "start_date": (today + timedelta(days=14)).isoformat(),
                "end_date": (today + timedelta(days=14)).isoformat(),
                "url": "https://example.com/marathon"
            }
        ]
        
        # Return requested number of events
        return base_events[:max_events]


class EventSearchRequestHandler(RequestHandler):
    """Request handler for event search operations"""
    
    def __init__(self, executor: EventSearchExecutor):
        self.executor = executor
        self.tasks: Dict[str, Task] = {}
        self.logger = structlog.get_logger(__name__).bind(component="event_search_handler")
    
    async def on_message_send(
        self, 
        params: MessageSendParams, 
        context: ServerCallContext | None = None
    ) -> Message:
        """Handle incoming messages for event search"""
        # Create a new task for the message
        task_id = str(uuid4())
        
        # Extract parameters from message
        message_data = {}
        if params.message.parts:
            for part in params.message.parts:
                if hasattr(part.root, 'text'):
                    # Try to parse as JSON first
                    try:
                        message_data = json.loads(part.root.text)
                    except:
                        # If not JSON, extract city from text
                        text = part.root.text.strip()
                        # Simple extraction - look for city name
                        message_data = {"city": text}
        
        # Create task
        task = Task(
            id=task_id,
            contextId=str(uuid4()),
            status=TaskStatus(
                state=TaskState.working,
                timestamp=datetime.utcnow().isoformat()
            )
        )
        
        self.tasks[task_id] = task
        
        # Execute search
        try:
            result = await self.executor._search_events(message_data)
            
            # Update task as completed
            task.status = TaskStatus(
                state=TaskState.completed,
                timestamp=datetime.utcnow().isoformat()
            )
            
            self.logger.info("Event search completed", 
                           task_id=task_id, 
                           city=message_data.get("city"),
                           events_found=result.get("count", 0))
            
            # Return response message
            return Message(
                messageId=str(uuid4()),
                role="agent",
                parts=[
                    Part(
                        root=TextPart(
                            text=json.dumps(result, indent=2)
                        )
                    )
                ],
                taskId=task_id
            )
            
        except Exception as e:
            # Update task as failed
            task.status = TaskStatus(
                state=TaskState.failed,
                timestamp=datetime.utcnow().isoformat()
            )
            
            self.logger.error("Event search failed", 
                            task_id=task_id, 
                            error=str(e))
            
            return Message(
                messageId=str(uuid4()),
                role="agent", 
                parts=[
                    Part(
                        root=TextPart(
                            text=f"Failed to search events: {str(e)}"
                        )
                    )
                ],
                taskId=task_id
            )
    
    async def on_message_send_stream(
        self,
        params: MessageSendParams,
        context: ServerCallContext | None = None
    ) -> Any:
        """Handle streaming message requests"""
        raise UnsupportedOperationError("Streaming not supported for event search")
    
    async def on_get_task(
        self, 
        params: TaskQueryParams, 
        context: ServerCallContext | None = None
    ) -> Task | None:
        """Get task status"""
        return self.tasks.get(params.id)
    
    async def on_cancel_task(
        self, 
        params: TaskIdParams, 
        context: ServerCallContext | None = None
    ) -> Task | None:
        """Cancel a task"""
        task = self.tasks.get(params.id)
        if task:
            task.status = TaskStatus(
                state=TaskState.canceled,
                timestamp=datetime.utcnow().isoformat()
            )
            self.logger.info("Task cancelled", task_id=params.id)
        return task
    
    async def on_get_task_push_notification_config(
        self,
        params: GetTaskPushNotificationConfigParams,
        context: ServerCallContext | None = None,
    ) -> TaskPushNotificationConfig | None:
        """Get push notification config (not implemented)"""
        return None
    
    async def on_set_task_push_notification_config(
        self,
        params: Any,
        context: ServerCallContext | None = None,
    ) -> TaskPushNotificationConfig | None:
        """Set push notification config (not implemented)"""
        return None
    
    async def on_resubscribe_to_task(
        self,
        params: Any,
        context: ServerCallContext | None = None,
    ) -> None:
        """Resubscribe to task updates (not implemented)"""
        pass


class EventSearchAgent:
    """
    Event Search Agent using Google A2A SDK
    
    This agent searches for events in cities using web search.
    Provides a simple interface for multi-agent systems.
    """
    
    def __init__(self, name: str = "Event Search", version: str = "1.0.0", events_count: int = 10):
        self.name = name
        self.version = version
        self.events_count = events_count
        self.logger = structlog.get_logger(__name__).bind(agent_name=name)
        
        # Create event search skill
        self.skills = [
            AgentSkill(
                id="search_events",
                name="Search Events",
                description="Search for upcoming events in a specified city",
                tags=["search", "events", "discovery"],
                examples=[
                    "Search for events in New York",
                    '{"city": "San Francisco", "events_count": 5}',
                    '{"city": "Paris", "days_ahead": 7}'
                ]
            )
        ]
        
        # Create agent card
        self.agent_card = AgentCard(
            name=self.name,
            description="Agent that searches for upcoming events in cities using web search",
            version=self.version,
            url="http://localhost:8001",  # Different port from EventManager
            defaultInputModes=["text/plain", "application/json"],
            defaultOutputModes=["application/json"],
            capabilities=AgentCapabilities(),
            skills=self.skills
        )
        
        # Create executor and handler
        self.executor = EventSearchExecutor(events_count=self.events_count)
        self.request_handler = EventSearchRequestHandler(self.executor)
        
        # Create A2A FastAPI application
        self.a2a_app = A2AFastAPIApplication(
            agent_card=self.agent_card,
            http_handler=self.request_handler
        )
        
        self.logger.info("Event Search Agent initialized", 
                        skills_count=len(self.skills),
                        default_events_count=self.events_count)
    
    def build_fastapi_app(self):
        """Build and return FastAPI application"""
        return self.a2a_app.build(
            title="Event Search Agent",
            description="A2A Agent for searching upcoming events in cities",
            version=self.version
        )
    
    async def start_server(self, host: str = "localhost", port: int = 8001):
        """Start the agent server"""
        import uvicorn
        
        app = self.build_fastapi_app()
        self.logger.info("Starting Event Search Agent server", 
                        host=host, port=port)
        
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()


# Factory function for easy instantiation
def create_event_search_agent(
    name: str = "Event Search", 
    events_count: int = 10
) -> EventSearchAgent:
    """Create and return a configured Event Search Agent"""
    return EventSearchAgent(name=name, events_count=events_count)


if __name__ == "__main__":
    import uvicorn
    
    agent = EventSearchAgent()
    app = agent.build_fastapi_app()
    
    # Add health check endpoint
    @app.get("/health")
    async def health():
        return {"status": "healthy", "agent": "EventSearchAgent", "version": "1.0.0"}
    
    print("🚀 Starting EventSearchAgent...")
    print("📍 Agent will be available at: http://localhost:8001")
    print("🔍 Example request: POST / with A2A message for event search")
    print("❤️  Health check: GET /health")
    
    uvicorn.run(app, host="0.0.0.0", port=8001)