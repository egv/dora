"""
Event Manager Agent - Vanilla Google A2A Implementation

This agent manages events using Google's official A2A SDK patterns.
Built with RequestHandler and AgentExecutor interfaces.
"""

import asyncio
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
)


logger = structlog.get_logger(__name__)


class Event:
    """Simple event data structure"""
    def __init__(self, event_id: str, title: str, description: str, 
                 start_time: datetime, end_time: datetime, organizer: str):
        self.event_id = event_id
        self.title = title
        self.description = description
        self.start_time = start_time
        self.end_time = end_time
        self.organizer = organizer
        self.created_at = datetime.utcnow()
        self.attendees: List[str] = []
        self.status = "scheduled"  # scheduled, cancelled, completed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "description": self.description,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "organizer": self.organizer,
            "attendees": self.attendees,
            "status": self.status,
            "created_at": self.created_at.isoformat()
        }


class EventManagerExecutor(AgentExecutor):
    """Agent executor implementing event management logic"""
    
    def __init__(self):
        self.events: Dict[str, Event] = {}
        self.logger = structlog.get_logger(__name__).bind(component="event_executor")
    
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute event management operations"""
        try:
            message = context.message
            skill_id = message.get("skill_id")
            params = message.get("params", {})
            
            if skill_id == "create_event":
                result = await self._create_event(params)
            elif skill_id == "list_events":
                result = await self._list_events(params)
            elif skill_id == "get_event":
                result = await self._get_event(params)
            elif skill_id == "update_event":
                result = await self._update_event(params)
            elif skill_id == "cancel_event":
                result = await self._cancel_event(params)
            elif skill_id == "add_attendee":
                result = await self._add_attendee(params)
            else:
                raise ValueError(f"Unknown skill: {skill_id}")
            
            # Publish task completion event
            from a2a.types import TaskStatusUpdateEvent, TaskState
            await event_queue.publish(TaskStatusUpdateEvent(
                task_id=context.task_id,
                state=TaskState.completed,
                result=result
            ))
            
        except Exception as e:
            self.logger.error("Event execution failed", error=str(e), task_id=context.task_id)
            # Publish task failure event
            from a2a.types import TaskStatusUpdateEvent, TaskState
            await event_queue.publish(TaskStatusUpdateEvent(
                task_id=context.task_id,
                state=TaskState.failed,
                error=str(e)
            ))
    
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel event management operation"""
        self.logger.info("Cancelling task", task_id=context.task_id)
        from a2a.types import TaskStatusUpdateEvent, TaskState
        await event_queue.publish(TaskStatusUpdateEvent(
            task_id=context.task_id,
            state=TaskState.canceled
        ))
    
    async def _create_event(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new event"""
        event_id = str(uuid4())
        event = Event(
            event_id=event_id,
            title=params["title"],
            description=params.get("description", ""),
            start_time=datetime.fromisoformat(params["start_time"]),
            end_time=datetime.fromisoformat(params["end_time"]),
            organizer=params["organizer"]
        )
        
        self.events[event_id] = event
        self.logger.info("Event created", event_id=event_id, title=event.title)
        
        return {"event_id": event_id, "event": event.to_dict()}
    
    async def _list_events(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List events with optional filtering"""
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        
        events = []
        for event in self.events.values():
            # Apply date filtering if provided
            if start_date and event.start_time < datetime.fromisoformat(start_date):
                continue
            if end_date and event.end_time > datetime.fromisoformat(end_date):
                continue
            
            events.append(event.to_dict())
        
        return {"events": events, "count": len(events)}
    
    async def _get_event(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get specific event details"""
        event_id = params["event_id"]
        
        if event_id not in self.events:
            raise ValueError(f"Event not found: {event_id}")
        
        return {"event": self.events[event_id].to_dict()}
    
    async def _update_event(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Update event details"""
        event_id = params["event_id"]
        
        if event_id not in self.events:
            raise ValueError(f"Event not found: {event_id}")
        
        event = self.events[event_id]
        
        # Update fields if provided
        if "title" in params:
            event.title = params["title"]
        if "description" in params:
            event.description = params["description"]
        if "start_time" in params:
            event.start_time = datetime.fromisoformat(params["start_time"])
        if "end_time" in params:
            event.end_time = datetime.fromisoformat(params["end_time"])
        
        self.logger.info("Event updated", event_id=event_id)
        return {"event": event.to_dict()}
    
    async def _cancel_event(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel an event"""
        event_id = params["event_id"]
        
        if event_id not in self.events:
            raise ValueError(f"Event not found: {event_id}")
        
        event = self.events[event_id]
        event.status = "cancelled"
        
        self.logger.info("Event cancelled", event_id=event_id)
        return {"event": event.to_dict()}
    
    async def _add_attendee(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Add attendee to event"""
        event_id = params["event_id"]
        attendee = params["attendee"]
        
        if event_id not in self.events:
            raise ValueError(f"Event not found: {event_id}")
        
        event = self.events[event_id]
        if attendee not in event.attendees:
            event.attendees.append(attendee)
        
        self.logger.info("Attendee added", event_id=event_id, attendee=attendee)
        return {"event": event.to_dict()}


class EventManagerRequestHandler(RequestHandler):
    """Request handler for event management operations"""
    
    def __init__(self, executor: EventManagerExecutor):
        self.executor = executor
        self.tasks: Dict[str, Task] = {}
        self.logger = structlog.get_logger(__name__).bind(component="event_handler")
    
    async def on_message_send(
        self, 
        params: MessageSendParams, 
        context: ServerCallContext | None = None
    ) -> Message:
        """Handle incoming messages for event management"""
        # Create a new task for the message
        task_id = str(uuid4())
        
        # Extract text from message parts
        message_text = ""
        if params.message.parts:
            for part in params.message.parts:
                if hasattr(part.root, 'text'):
                    message_text += part.root.text + " "
        
        message_text = message_text.strip().lower()
        
        # Simple text-based skill detection (for demo purposes)
        skill_id = None
        skill_params = {}
        
        if "create" in message_text and "event" in message_text:
            skill_id = "create_event"
            skill_params = {
                "title": "Demo Event",
                "description": "Event created from message",
                "start_time": "2024-01-01T10:00:00",
                "end_time": "2024-01-01T11:00:00",
                "organizer": "demo@example.com"
            }
        elif "list" in message_text and "event" in message_text:
            skill_id = "list_events"
            skill_params = {}
        else:
            # Default to list events for demo
            skill_id = "list_events"
            skill_params = {}
        
        # Create task
        from a2a.types import TaskState, TaskStatus
        from datetime import datetime
        task = Task(
            id=task_id,
            contextId=str(uuid4()),
            status=TaskStatus(
                state=TaskState.working,
                timestamp=datetime.utcnow().isoformat()
            )
        )
        
        self.tasks[task_id] = task
        
        # Execute via executor
        try:
            if skill_id == "create_event":
                result = await self.executor._create_event(skill_params)
            elif skill_id == "list_events":
                result = await self.executor._list_events(skill_params)
            elif skill_id == "get_event":
                result = await self.executor._get_event(skill_params)
            elif skill_id == "update_event":
                result = await self.executor._update_event(skill_params)
            elif skill_id == "cancel_event":
                result = await self.executor._cancel_event(skill_params)
            elif skill_id == "add_attendee":
                result = await self.executor._add_attendee(skill_params)
            else:
                raise ValueError(f"Unknown skill: {skill_id}")
            
            # Update task as completed
            task.status = TaskStatus(
                state=TaskState.completed,
                timestamp=datetime.utcnow().isoformat()
            )
            
            self.logger.info("Message processed successfully", 
                           task_id=task_id, skill_id=skill_id)
            
            # Return response message - use correct Message structure
            from a2a.types import Part, TextPart
            import json
            return Message(
                messageId=str(uuid4()),
                role="agent",
                parts=[
                    Part(
                        root=TextPart(
                            text=f"Executed {skill_id}. Result: {json.dumps(result, indent=2)}"
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
            
            self.logger.error("Message processing failed", 
                            task_id=task_id, skill_id=skill_id, error=str(e))
            
            from a2a.types import Part, TextPart
            return Message(
                messageId=str(uuid4()),
                role="agent", 
                parts=[
                    Part(
                        root=TextPart(
                            text=f"Failed to execute {skill_id}: {str(e)}"
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
        raise UnsupportedOperationError("Streaming not supported for event management")
    
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
            from a2a.types import TaskState, TaskStatus
            from datetime import datetime
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


class EventManagerAgent:
    """
    Event Manager Agent using vanilla Google A2A SDK
    
    This agent manages events using official A2A patterns:
    - AgentExecutor for business logic
    - RequestHandler for HTTP/JSON-RPC handling  
    - A2AFastAPIApplication for server infrastructure
    """
    
    def __init__(self, name: str = "Event Manager", version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.logger = structlog.get_logger(__name__).bind(agent_name=name)
        
        # Create event management skills
        self.skills = [
            AgentSkill(
                id="create_event",
                name="Create Event",
                description="Create a new calendar event",
                tags=["calendar", "scheduling"],
                examples=["Create a meeting for tomorrow at 2pm"]
            ),
            AgentSkill(
                id="list_events",
                name="List Events", 
                description="List calendar events with optional date filtering",
                tags=["calendar", "query"],
                examples=["Show me events for this week"]
            ),
            AgentSkill(
                id="get_event",
                name="Get Event",
                description="Get details of a specific event",
                tags=["calendar", "query"],
                examples=["Show me details of event ID 123"]
            ),
            AgentSkill(
                id="update_event",
                name="Update Event",
                description="Update event details",
                tags=["calendar", "modification"],
                examples=["Change the meeting time to 3pm"]
            ),
            AgentSkill(
                id="cancel_event",
                name="Cancel Event",
                description="Cancel a calendar event",
                tags=["calendar", "modification"],
                examples=["Cancel the meeting with John"]
            ),
            AgentSkill(
                id="add_attendee",
                name="Add Attendee",
                description="Add attendee to an event",
                tags=["calendar", "attendees"],
                examples=["Add Sarah to the project meeting"]
            )
        ]
        
        # Create agent card
        self.agent_card = AgentCard(
            name=self.name,
            description="Agent that manages calendar events and scheduling",
            version=self.version,
            url="http://localhost:8000",
            defaultInputModes=["text/plain", "application/json"],
            defaultOutputModes=["text/plain", "application/json"],
            capabilities=AgentCapabilities(),  # AgentCapabilities doesn't have skills field
            skills=self.skills
        )
        
        # Create executor and handler
        self.executor = EventManagerExecutor()
        self.request_handler = EventManagerRequestHandler(self.executor)
        
        # Create A2A FastAPI application
        self.a2a_app = A2AFastAPIApplication(
            agent_card=self.agent_card,
            http_handler=self.request_handler
        )
        
        self.logger.info("Event Manager Agent initialized", 
                        skills_count=len(self.skills))
    
    def build_fastapi_app(self):
        """Build and return FastAPI application"""
        return self.a2a_app.build(
            title="Event Manager Agent",
            description="A2A Agent for calendar event management",
            version=self.version
        )
    
    async def start_server(self, host: str = "localhost", port: int = 8000):
        """Start the agent server"""
        import uvicorn
        
        app = self.build_fastapi_app()
        self.logger.info("Starting Event Manager Agent server", 
                        host=host, port=port)
        
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()


# Factory function for easy instantiation
def create_event_manager_agent(name: str = "Event Manager") -> EventManagerAgent:
    """Create and return a configured Event Manager Agent"""
    return EventManagerAgent(name=name)


if __name__ == "__main__":
    # Example usage
    async def main():
        agent = create_event_manager_agent()
        await agent.start_server()
    
    asyncio.run(main())