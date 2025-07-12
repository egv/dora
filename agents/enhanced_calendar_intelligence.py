"""
Enhanced Calendar Intelligence Agent with A2A Collaborative Capabilities

This enhanced version integrates with the discovery, notification, and orchestration services
to enable collaborative workflows and real-time agent communication.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
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
from models.calendar_data import CalendarData

# Import original components
from .calendar_intelligence import CalendarIntelligenceExecutor, MultiSourceCollector, DataVerifier, CalendarBuilder

# Import enhanced components if available
try:
    from .collectors import EnhancedMultiSourceCollector
    USE_ENHANCED_COLLECTOR = True
except ImportError:
    USE_ENHANCED_COLLECTOR = False

try:
    from .enhanced_calendar_builder import EnhancedCalendarBuilder
    USE_ENHANCED_BUILDER = True
except ImportError:
    USE_ENHANCED_BUILDER = False

# Import A2A collaboration services
from .discovery_service import get_discovery_service, RegisteredAgent
from .notification_service import get_notification_service, NotificationEvent
from .orchestration_service import get_orchestration_service


logger = structlog.get_logger(__name__)


class EnhancedCalendarIntelligenceExecutor(CalendarIntelligenceExecutor):
    """Enhanced executor with A2A collaborative capabilities"""
    
    def __init__(self):
        super().__init__()
        self.logger = logger.bind(component="enhanced_calendar_intelligence_executor")
        
        # A2A collaboration services (initialized on first use)
        self.discovery_service = None
        self.notification_service = None
        self.orchestration_service = None
        
        # Collaborative data collection flag
        self.use_collaborative_collection = True
        
        # Agent preferences for collaboration
        self.preferred_agents = {
            "events": ["EventSearchAgent"],
            "weather": ["WeatherAgent", "ExternalWeatherAPI"],
            "holidays": ["HolidayAgent", "CalendarAgent"]
        }
    
    async def _get_services(self):
        """Initialize A2A services if not already done"""
        if self.discovery_service is None:
            self.discovery_service = await get_discovery_service()
        if self.notification_service is None:
            self.notification_service = await get_notification_service()
        if self.orchestration_service is None:
            self.orchestration_service = await get_orchestration_service()
    
    async def _get_calendar_data(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced calendar data collection with collaborative capabilities"""
        await self._get_services()
        
        location = params.get('location')
        if not location:
            raise ValueError("Location parameter is required")
        
        # Parse date
        date_str = params.get('date')
        if date_str:
            try:
                date = datetime.fromisoformat(date_str)
            except ValueError:
                try:
                    date = datetime.strptime(date_str, '%Y-%m-%d')
                except ValueError:
                    raise ValueError(f"Invalid date format: {date_str}")
        else:
            date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        self.logger.info(
            "Starting enhanced calendar data collection",
            location=location,
            date=date.isoformat(),
            collaborative=self.use_collaborative_collection
        )
        
        if self.use_collaborative_collection:
            try:
                # Try collaborative workflow first
                return await self._collaborative_calendar_data_collection(location, date, params)
            except Exception as e:
                self.logger.warning(
                    "Collaborative collection failed, falling back to standard collection",
                    error=str(e)
                )
                # Fall back to standard collection
                return await super()._get_calendar_data(params)
        else:
            # Use standard collection
            return await super()._get_calendar_data(params)
    
    async def _collaborative_calendar_data_collection(
        self,
        location: str,
        date: datetime,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Collect calendar data using collaborative A2A workflows"""
        
        # Create collaborative workflow for data collection
        workflow_tasks = []
        
        # Task 1: Discover available data collection agents
        workflow_tasks.append({
            "task_id": "discover_agents",
            "skill_name": "get_capabilities_summary",
            "parameters": {},
            "agent_id": None  # Auto-assign
        })
        
        # Task 2: Collect events from EventSearchAgent
        event_agents = await self.discovery_service.find_agents_by_skill("search_events")
        if event_agents:
            workflow_tasks.append({
                "task_id": "collect_events",
                "skill_name": "search_events",
                "parameters": {
                    "city": location,
                    "date": date.strftime('%Y-%m-%d'),
                    "limit": 50
                },
                "agent_id": event_agents[0].agent_id,
                "dependencies": []
            })
        
        # Task 3: Collect weather data (if weather agents available)
        weather_agents = await self.discovery_service.find_agents_by_skill("get_weather")
        if weather_agents:
            workflow_tasks.append({
                "task_id": "collect_weather",
                "skill_name": "get_weather",
                "parameters": {
                    "location": location,
                    "date": date.strftime('%Y-%m-%d')
                },
                "agent_id": weather_agents[0].agent_id,
                "dependencies": []
            })
        
        # Task 4: Process and verify collected data
        workflow_tasks.append({
            "task_id": "verify_data",
            "skill_name": "process_collected_data",
            "parameters": {
                "location": location,
                "date": date.strftime('%Y-%m-%d')
            },
            "dependencies": ["collect_events", "collect_weather"],
            "agent_id": "calendar_intelligence"  # Self-process
        })
        
        # Create and execute workflow only if we have meaningful tasks
        meaningful_tasks = [t for t in workflow_tasks if t["task_id"] != "discover_agents"]
        
        if meaningful_tasks:
            try:
                workflow_id = await self.orchestration_service.create_workflow(
                    name=f"Calendar Data Collection - {location}",
                    description=f"Collaborative data collection for {location} on {date.strftime('%Y-%m-%d')}",
                    tasks=meaningful_tasks,
                    created_by="calendar_intelligence",
                    timeout=300,  # 5 minutes
                    metadata={
                        "location": location,
                        "date": date.isoformat(),
                        "collection_type": "collaborative"
                    }
                )
                
                # Execute workflow
                workflow_result = await self.orchestration_service.execute_workflow(
                    workflow_id,
                    {"location": location, "date": date.isoformat()}
                )
                
                # Process workflow results
                return await self._process_workflow_results(
                    workflow_result, location, date, params
                )
                
            except Exception as e:
                self.logger.error(
                    "Collaborative workflow execution failed",
                    location=location,
                    date=date.isoformat(),
                    error=str(e)
                )
                raise
        else:
            # No collaborative agents available, fall back to self-collection
            self.logger.info(
                "No collaborative agents available, using self-collection",
                location=location,
                date=date.isoformat()
            )
            return await self._self_collect_calendar_data(location, date, params)
    
    async def _process_workflow_results(
        self,
        workflow_result: Dict[str, Any],
        location: str,
        date: datetime,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process results from collaborative workflow"""
        
        workflow_results = workflow_result.get("results", {})
        
        # Extract data from workflow results
        events = []
        weather = {}
        holidays = []
        
        # Process events from workflow
        if "collect_events" in workflow_results:
            event_result = workflow_results["collect_events"]
            if isinstance(event_result, dict) and "events" in event_result:
                events = event_result["events"]
            elif isinstance(event_result, list):
                events = event_result
        
        # Process weather from workflow
        if "collect_weather" in workflow_results:
            weather_result = workflow_results["collect_weather"]
            if isinstance(weather_result, dict):
                weather = weather_result
        
        # Fallback to self-collection for missing data
        if not events:
            self.logger.info("No events from workflow, using fallback collection")
            collector = self._get_collector()
            events = await collector.collect_events(location, date)
        
        if not weather:
            self.logger.info("No weather from workflow, using fallback collection")
            collector = self._get_collector()
            weather = await collector.collect_weather(location, date)
        
        if not holidays:
            collector = self._get_collector()
            holidays = await collector.collect_holidays(location, date)
        
        # Verify collected data
        verifier = self._get_verifier()
        verified_events, events_confidence = await verifier.verify_events(events)
        verified_weather, weather_confidence = await verifier.verify_weather(weather)
        verified_holidays = holidays  # Holidays don't need separate verification
        
        # Cross-verify data consistency
        consistency_scores = await verifier.cross_verify_data(
            verified_events, verified_weather, verified_holidays, location, date
        )
        
        # Build calendar data
        builder = self._get_builder()
        if hasattr(builder, 'build_calendar_data') and callable(getattr(builder, 'build_calendar_data')):
            # Enhanced builder
            calendar_data = await builder.build_calendar_data(
                location, date, verified_events, verified_weather, verified_holidays, consistency_scores
            )
        else:
            # Basic builder
            calendar_data = await builder.build_calendar_data(
                location, date, verified_events, verified_weather, verified_holidays
            )
        
        # Publish calendar data update event
        await self.notification_service.publish_event(
            event_type="calendar_data.updated",
            data={
                "location": location,
                "date": date.isoformat(),
                "opportunity_score": calendar_data.opportunity_score,
                "event_count": len(verified_events),
                "collection_method": "collaborative"
            },
            source_agent="calendar_intelligence",
            metadata={
                "workflow_id": workflow_result.get("workflow_id"),
                "execution_time": workflow_result.get("execution_time")
            }
        )
        
        return {
            "calendar_data": calendar_data.to_dict(),
            "verification_scores": {
                "events_confidence": events_confidence,
                "weather_confidence": weather_confidence,
                "consistency_scores": consistency_scores
            },
            "data_sources": {
                "events": "collaborative_workflow",
                "weather": "collaborative_workflow" if weather_result else "fallback",
                "holidays": "self_collection"
            },
            "workflow_info": {
                "workflow_id": workflow_result.get("workflow_id"),
                "execution_time": workflow_result.get("execution_time"),
                "task_summary": workflow_result.get("task_summary")
            }
        }
    
    async def _self_collect_calendar_data(
        self,
        location: str,
        date: datetime,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Fallback to self-collection when collaboration is not available"""
        self.logger.info(
            "Using self-collection for calendar data",
            location=location,
            date=date.isoformat()
        )
        
        # Use the original implementation
        return await super()._get_calendar_data({
            "location": location,
            "date": date.isoformat(),
            **params
        })
    
    async def get_collaborative_insights(
        self,
        location: str,
        start_date: datetime,
        end_date: datetime,
        criteria: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Get marketing insights using collaborative agent analysis"""
        await self._get_services()
        
        # Create workflow for multi-day analysis
        workflow_tasks = []
        
        # Generate tasks for each day in the range
        current_date = start_date
        day_tasks = []
        
        while current_date <= end_date:
            day_task_id = f"analyze_day_{current_date.strftime('%Y_%m_%d')}"
            day_tasks.append(day_task_id)
            
            workflow_tasks.append({
                "task_id": day_task_id,
                "skill_name": "get_calendar_data",
                "parameters": {
                    "location": location,
                    "date": current_date.strftime('%Y-%m-%d')
                },
                "agent_id": "calendar_intelligence"
            })
            
            current_date += timedelta(days=1)
        
        # Task to aggregate and analyze all days
        workflow_tasks.append({
            "task_id": "aggregate_insights",
            "skill_name": "analyze_multi_day_insights",
            "parameters": {
                "location": location,
                "start_date": start_date.strftime('%Y-%m-%d'),
                "end_date": end_date.strftime('%Y-%m-%d'),
                "criteria": criteria or {}
            },
            "dependencies": day_tasks,
            "agent_id": "calendar_intelligence"
        })
        
        # Execute collaborative workflow
        workflow_id = await self.orchestration_service.create_workflow(
            name=f"Marketing Insights - {location}",
            description=f"Multi-day collaborative analysis for {location}",
            tasks=workflow_tasks,
            created_by="calendar_intelligence",
            timeout=600,  # 10 minutes
            metadata={
                "location": location,
                "date_range": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                "analysis_type": "marketing_insights"
            }
        )
        
        workflow_result = await self.orchestration_service.execute_workflow(workflow_id)
        
        # Extract insights from workflow results
        insights_result = workflow_result.get("results", {}).get("aggregate_insights", {})
        
        if not insights_result:
            # Fallback to standard insights
            return await super()._get_marketing_insights({
                "location": location,
                "start_date": start_date.strftime('%Y-%m-%d'),
                "end_date": end_date.strftime('%Y-%m-%d')
            })
        
        return insights_result
    
    async def subscribe_to_agent_updates(self, agent_types: List[str]) -> str:
        """Subscribe to updates from specific types of agents"""
        await self._get_services()
        
        # Subscribe to relevant events
        event_types = []
        for agent_type in agent_types:
            event_types.extend([
                f"{agent_type}.data_updated",
                f"{agent_type}.status_changed",
                f"{agent_type}.new_data_available"
            ])
        
        # Add general collaborative events
        event_types.extend([
            "workflow.completed",
            "calendar_data.updated",
            "agent.registered",
            "agent.unregistered"
        ])
        
        subscription_id = await self.notification_service.subscribe(
            agent_id="calendar_intelligence",
            event_types=event_types,
            callback=self._handle_agent_update
        )
        
        self.logger.info(
            "Subscribed to agent updates",
            subscription_id=subscription_id,
            agent_types=agent_types,
            event_types=event_types
        )
        
        return subscription_id
    
    async def _handle_agent_update(self, event: NotificationEvent):
        """Handle incoming agent update notifications"""
        self.logger.info(
            "Received agent update notification",
            event_type=event.event_type,
            source_agent=event.source_agent,
            event_id=event.event_id
        )
        
        # Process different types of updates
        if event.event_type.startswith("calendar_data."):
            await self._handle_calendar_data_update(event)
        elif event.event_type.startswith("workflow."):
            await self._handle_workflow_update(event)
        elif event.event_type.startswith("agent."):
            await self._handle_agent_registry_update(event)
    
    async def _handle_calendar_data_update(self, event: NotificationEvent):
        """Handle calendar data update notifications"""
        event_data = event.data
        location = event_data.get("location")
        date_str = event_data.get("date")
        
        if location and date_str:
            self.logger.info(
                "Calendar data updated by another agent",
                location=location,
                date=date_str,
                source_agent=event.source_agent
            )
            
            # Could trigger cache invalidation or data refresh here
    
    async def _handle_workflow_update(self, event: NotificationEvent):
        """Handle workflow update notifications"""
        workflow_data = event.data
        workflow_id = workflow_data.get("workflow_id")
        
        self.logger.info(
            "Workflow update received",
            workflow_id=workflow_id,
            event_type=event.event_type,
            source_agent=event.source_agent
        )
    
    async def _handle_agent_registry_update(self, event: NotificationEvent):
        """Handle agent registry update notifications"""
        agent_data = event.data
        
        if event.event_type == "agent.registered":
            self.logger.info(
                "New agent registered",
                agent_name=agent_data.get("name"),
                capabilities=agent_data.get("capabilities")
            )
        elif event.event_type == "agent.unregistered":
            self.logger.info(
                "Agent unregistered",
                agent_id=agent_data.get("agent_id")
            )


class EnhancedCalendarIntelligenceRequestHandler(RequestHandler):
    """Enhanced request handler with A2A collaboration support"""
    
    def __init__(self, executor: EnhancedCalendarIntelligenceExecutor):
        self.executor = executor
        self.logger = logger.bind(component="enhanced_calendar_intelligence_handler")
    
    async def on_get_task(self, params: TaskQueryParams) -> Task:
        """Handle task queries (not implemented for this agent)"""
        raise UnsupportedOperationError("This agent does not support task queries")
    
    async def on_cancel_task(self, params: TaskIdParams) -> None:
        """Handle task cancellation (not implemented for this agent)"""
        raise UnsupportedOperationError("This agent does not support task cancellation")
    
    async def on_resubscribe_to_task(self, params: TaskIdParams) -> None:
        """Handle task resubscription (not implemented for this agent)"""
        raise UnsupportedOperationError("This agent does not support task resubscription")
    
    async def on_get_task_push_notification_config(
        self, params: GetTaskPushNotificationConfigParams
    ) -> TaskPushNotificationConfig:
        """Handle push notification config requests (not implemented for this agent)"""
        raise UnsupportedOperationError("This agent does not support push notifications")
    
    async def on_set_task_push_notification_config(
        self, params: TaskPushNotificationConfig
    ) -> None:
        """Handle push notification config updates (not implemented for this agent)"""
        raise UnsupportedOperationError("This agent does not support push notifications")
    
    async def on_message_send_stream(self, params: MessageSendParams) -> Message:
        """Handle streaming message sends (not implemented for this agent)"""
        raise UnsupportedOperationError("This agent does not support streaming messages")
    
    async def on_message_send(self, params: MessageSendParams) -> Message:
        """Handle incoming A2A messages with collaboration awareness"""
        try:
            # Extract message content
            message_text = ""
            if params.message.parts:
                for part in params.message.parts:
                    if hasattr(part.root, 'text'):
                        message_text += part.root.text
            
            self.logger.info("Processing enhanced A2A message", 
                           message_id=params.message.messageId,
                           message_preview=message_text[:100])
            
            # Try to parse as JSON first
            try:
                request_data = json.loads(message_text)
                is_json = True
            except json.JSONDecodeError:
                # Treat as plain text location request
                request_data = {"location": message_text.strip()}
                is_json = False
            
            # Determine request type and handle accordingly
            request_type = request_data.get("request_type", "calendar_data")
            
            if request_type == "insights":
                result = await self.executor.get_collaborative_insights(
                    location=request_data["location"],
                    start_date=datetime.fromisoformat(request_data["start_date"]),
                    end_date=datetime.fromisoformat(request_data["end_date"]),
                    criteria=request_data.get("criteria")
                )
            elif request_type == "analyze":
                result = await self.executor._analyze_opportunity(request_data)
            else:
                # Default to calendar data with collaborative collection
                result = await self.executor._get_calendar_data(request_data)
            
            # Create response message
            response_content = json.dumps(result, indent=2)
            
            return Message(
                messageId=str(uuid4()),
                role="agent",
                parts=[
                    Part(root=TextPart(text=response_content))
                ]
            )
            
        except Exception as e:
            self.logger.error("Error processing enhanced A2A message", error=str(e))
            
            error_response = {
                "error": str(e),
                "message": "Failed to process calendar intelligence request"
            }
            
            return Message(
                messageId=str(uuid4()),
                role="agent",
                parts=[
                    Part(root=TextPart(text=json.dumps(error_response)))
                ]
            )


class EnhancedCalendarIntelligenceAgent:
    """
    Enhanced Calendar Intelligence Agent with A2A Collaborative Capabilities
    
    This agent extends the original calendar intelligence with:
    - Agent discovery and dynamic collaboration
    - Real-time notification subscriptions
    - Workflow orchestration for complex data collection
    - Cross-agent consistency verification
    """
    
    def __init__(self, name: str = "Enhanced Calendar Intelligence", version: str = "2.0.0"):
        self.name = name
        self.version = version
        self.logger = logger.bind(agent_name=name)
        
        # Create enhanced skills with collaboration
        self.skills = [
            AgentSkill(
                id="get_calendar_data",
                name="Get Calendar Data (Collaborative)",
                description="Get comprehensive calendar data using collaborative agent workflows",
                tags=["calendar", "data", "intelligence", "collaborative"],
                examples=[
                    '{"location": "San Francisco", "date": "2025-07-10", "collaborative": true}',
                    '{"location": "New York", "use_collaborative_collection": true}',
                    "Get calendar data for Paris using agent collaboration"
                ]
            ),
            AgentSkill(
                id="get_marketing_insights",
                name="Get Marketing Insights (Multi-Agent)",
                description="Get marketing insights using multi-agent collaborative analysis",
                tags=["marketing", "insights", "analytics", "collaborative"],
                examples=[
                    '{"location": "London", "start_date": "2025-07-01", "end_date": "2025-07-07", "collaborative": true}',
                    '{"location": "Tokyo", "request_type": "insights", "use_workflow": true}'
                ]
            ),
            AgentSkill(
                id="analyze_opportunity",
                name="Analyze Opportunity (Cross-Agent)",
                description="Analyze marketing opportunity using cross-agent verification",
                tags=["analysis", "opportunity", "marketing", "verification"],
                examples=[
                    '{"location": "Berlin", "date": "2025-07-15", "criteria": {"target_audience": "families"}}',
                    '{"location": "Sydney", "request_type": "analyze", "criteria": {"campaign_type": "outdoor"}}'
                ]
            ),
            AgentSkill(
                id="discover_agents",
                name="Discover Collaboration Agents",
                description="Discover available agents for collaborative workflows",
                tags=["discovery", "collaboration", "agents"],
                examples=[
                    '{"capability_filter": ["search_events", "get_weather"]}',
                    '{"agent_types": ["event", "weather", "holiday"]}'
                ]
            ),
            AgentSkill(
                id="subscribe_to_updates",
                name="Subscribe to Agent Updates",
                description="Subscribe to real-time updates from other agents",
                tags=["subscription", "notifications", "real-time"],
                examples=[
                    '{"agent_types": ["event", "weather"]}',
                    '{"event_types": ["data_updated", "new_data_available"]}'
                ]
            )
        ]
        
        # Create enhanced agent card
        self.agent_card = AgentCard(
            name=self.name,
            description="Enhanced agent with collaborative A2A capabilities for intelligent calendar analysis",
            version=self.version,
            url="http://localhost:8002",
            defaultInputModes=["text/plain", "application/json"],
            defaultOutputModes=["application/json"],
            capabilities=AgentCapabilities(),
            skills=self.skills
        )
        
        # Create enhanced executor and handler
        self.executor = EnhancedCalendarIntelligenceExecutor()
        self.request_handler = EnhancedCalendarIntelligenceRequestHandler(self.executor)
        
        # Create A2A FastAPI application
        self.a2a_app = A2AFastAPIApplication(
            agent_card=self.agent_card,
            http_handler=self.request_handler
        )
        
        self.logger.info("Enhanced Calendar Intelligence Agent initialized",
                        skills_count=len(self.skills),
                        collaborative_features=True)
    
    def build_fastapi_app(self):
        """Build and return enhanced FastAPI application"""
        return self.a2a_app.build(
            title="Enhanced Calendar Intelligence Agent",
            description="A2A Agent with collaborative capabilities for intelligent calendar analysis",
            version=self.version
        )
    
    async def start_server(self, host: str = "localhost", port: int = 8002):
        """Start the enhanced agent server with A2A registration"""
        import uvicorn
        
        # Register with discovery service
        try:
            discovery_service = await get_discovery_service()
            await discovery_service.register_agent(
                agent_card=self.agent_card,
                endpoint=f"http://{host}:{port}",
                metadata={
                    "enhanced": True,
                    "collaborative": True,
                    "started_at": datetime.utcnow().isoformat()
                }
            )
            
            # Subscribe to relevant agent updates
            await self.executor.subscribe_to_agent_updates(["event", "weather", "holiday"])
            
            self.logger.info("Agent registered with discovery service and subscribed to updates")
            
        except Exception as e:
            self.logger.warning("Failed to register with discovery service", error=str(e))
        
        # Start server
        app = self.build_fastapi_app()
        self.logger.info("Starting Enhanced Calendar Intelligence Agent server",
                        host=host, port=port)
        
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()


# Factory function for easy instantiation
def create_enhanced_calendar_intelligence_agent(
    name: str = "Enhanced Calendar Intelligence"
) -> EnhancedCalendarIntelligenceAgent:
    """Create and return a configured Enhanced Calendar Intelligence Agent"""
    return EnhancedCalendarIntelligenceAgent(name=name)


# Async main for testing
async def main():
    """Test the enhanced calendar intelligence agent"""
    agent = create_enhanced_calendar_intelligence_agent()
    await agent.start_server()


if __name__ == "__main__":
    asyncio.run(main())