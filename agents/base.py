"""
Base Agent Class for A2A Protocol

This module provides the foundational agent class that all specialized agents
inherit from, implementing core A2A protocol functionality.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

import structlog
from pydantic import BaseModel
from fasta2a import FastA2A, Skill
from fasta2a.storage import InMemoryStorage
from fasta2a.broker import InMemoryBroker

from agents.discovery import CapabilityDiscoveryMixin
from models.a2a import (
    AgentCard,
    AgentMetrics,
    AgentStatus,
    A2AMessage,
    A2ARequest,
    A2AResponse,
    A2AError,
    A2ATask,
    Capability,
    MessageType,
    TaskStatus,
)
from models.jsonrpc import (
    A2AMessageEnvelope,
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCErrorResponse,
    JSONRPCNotification,
    JSONRPCError,
    JSONRPCErrorCode,
    A2AMethod,
    create_success_response,
    create_error_response,
)
from models.validation import validate_message, ValidationResult
from agents.messaging import get_message_router, register_message_handler


logger = structlog.get_logger(__name__)


class BaseAgent(CapabilityDiscoveryMixin, ABC):
    """
    Base class for all A2A agents in the multi-agent system.
    
    Provides core functionality for:
    - Agent identity and lifecycle management
    - Capability registration and discovery
    - Message handling and communication
    - Task execution and monitoring
    - Error handling and recovery
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str,
        version: str = "1.0.0",
        endpoint: Optional[str] = None,
        heartbeat_interval: int = 30,
    ):
        """
        Initialize the base agent.
        
        Args:
            agent_id: Unique identifier for this agent
            name: Human-readable name
            description: Agent description and purpose
            version: Agent version
            endpoint: Communication endpoint URL
            heartbeat_interval: Heartbeat interval in seconds
        """
        # Call parent constructors for proper multiple inheritance
        super().__init__()
        
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.version = version
        self.endpoint = endpoint
        self.heartbeat_interval = heartbeat_interval
        
        # Agent state
        self._status = AgentStatus.INITIALIZING
        self._capabilities: Dict[str, Capability] = {}
        self._active_tasks: Dict[str, A2ATask] = {}
        self._metrics = AgentMetrics()
        self._start_time = time.time()
        
        # Communication
        self._fasta2a: Optional[FastA2A] = None
        self._message_handlers: Dict[MessageType, Any] = {}
        self._running_tasks: Set[str] = set()
        self._message_router = get_message_router()
        
        # Background tasks
        self._background_tasks: Set[asyncio.Task] = set()
        
        # Logging
        self.logger = structlog.get_logger(__name__).bind(
            agent_id=self.agent_id,
            agent_name=self.name
        )
        
        # Initialize message handlers
        self._setup_message_handlers()
        
        self.logger.info("Agent initialized", version=version)

    @property
    def status(self) -> AgentStatus:
        """Get current agent status"""
        return self._status

    @property
    def agent_card(self) -> AgentCard:
        """Get agent card with current information"""
        return AgentCard(
            agent_id=self.agent_id,
            name=self.name,
            description=self.description,
            version=self.version,
            capabilities=list(self._capabilities.values()),
            status=self._status,
            endpoint=self.endpoint,
            heartbeat_interval=self.heartbeat_interval,
            metadata={
                "metrics": self._metrics.model_dump(),
                "active_tasks": len(self._active_tasks),
                "uptime": time.time() - self._start_time,
            }
        )

    @property
    def metrics(self) -> AgentMetrics:
        """Get current agent metrics"""
        self._metrics.uptime_seconds = int(time.time() - self._start_time)
        self._metrics.concurrent_tasks = len(self._active_tasks)
        self._metrics.last_activity = datetime.utcnow()
        return self._metrics

    def register_capability(self, capability: Capability) -> None:
        """
        Register a capability that this agent can provide.
        
        Args:
            capability: Capability definition
        """
        self._capabilities[capability.name] = capability
        self.logger.info(
            "Capability registered",
            capability_name=capability.name,
            capability_type=capability.capability_type
        )

    def get_capability(self, name: str) -> Optional[Capability]:
        """Get a registered capability by name"""
        return self._capabilities.get(name)

    def list_capabilities(self) -> List[Capability]:
        """Get all registered capabilities"""
        return list(self._capabilities.values())

    def has_capability(self, name: str) -> bool:
        """Check if agent has a specific capability"""
        return name in self._capabilities

    async def start(self) -> None:
        """Start the agent and A2A communication"""
        try:
            self.logger.info("Starting agent")
            
            # Initialize agent-specific components
            await self._initialize()
            
            # Setup A2A communication
            await self._setup_a2a()
            
            # Setup capability discovery
            await self._setup_discovery()
            
            # Register with message router
            register_message_handler(self.agent_id, self._handle_incoming_message)
            
            # Start background tasks
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            cleanup_task = asyncio.create_task(self._cleanup_loop())
            self._background_tasks.add(heartbeat_task)
            self._background_tasks.add(cleanup_task)
            
            self._status = AgentStatus.READY
            self.logger.info("Agent started successfully")
            
        except Exception as e:
            self._status = AgentStatus.ERROR
            self.logger.error("Failed to start agent", error=str(e))
            raise

    async def stop(self) -> None:
        """Stop the agent gracefully"""
        try:
            self.logger.info("Stopping agent")
            self._status = AgentStatus.OFFLINE
            
            # Cancel background tasks
            for task in self._background_tasks:
                task.cancel()
            
            # Wait for background tasks to complete
            if self._background_tasks:
                await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()
            
            # Cancel active tasks
            for task_id in list(self._active_tasks.keys()):
                await self._cancel_task(task_id)
            
            # Cleanup A2A
            if self._fasta2a:
                # FastA2A cleanup - this may not have a stop method
                # We'll just set it to None for now
                self._fasta2a = None
            
            # Cleanup discovery
            await self._cleanup_discovery()
            
            # Agent-specific cleanup
            await self._cleanup()
            
            self.logger.info("Agent stopped")
            
        except Exception as e:
            self.logger.error("Error stopping agent", error=str(e))
            raise

    async def send_message(self, envelope: A2AMessageEnvelope) -> Optional[A2AMessageEnvelope]:
        """
        Send a JSON-RPC message envelope to another agent.
        
        Args:
            envelope: Message envelope to send
            
        Returns:
            Response envelope if expecting a response
        """
        try:
            self.logger.debug(
                "Sending message",
                envelope_id=envelope.envelope_id,
                recipient=envelope.recipient_id,
                method=getattr(envelope.jsonrpc_message, 'method', 'response'),
                correlation_id=envelope.correlation_id
            )
            
            # Validate outgoing message
            validation_result = validate_message(envelope)
            if not validation_result.is_valid:
                raise ValueError(f"Invalid outgoing message: {validation_result}")
            
            # Send via message router
            response = await self._message_router.send_message(
                envelope, 
                self._transport_send_func
            )
            
            return response
            
        except Exception as e:
            self.logger.error("Failed to send message", error=str(e))
            raise

    async def _transport_send_func(self, message_bytes: bytes):
        """Transport function for sending serialized messages"""
        # This is a placeholder - in a real implementation this would
        # send via HTTP, WebSocket, or other transport mechanism
        # For now we'll just log that we would send
        self.logger.debug("Would send message", size_bytes=len(message_bytes))

    async def execute_capability(
        self,
        capability_name: str,
        parameters: Dict[str, Any],
        correlation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a capability with given parameters.
        
        Args:
            capability_name: Name of capability to execute
            parameters: Parameters for the capability
            correlation_id: Optional correlation ID for tracking
            
        Returns:
            Execution result
        """
        start_time = time.time()
        
        # Update total requests metric immediately
        self._metrics.total_requests += 1
        
        try:
            # Validate capability exists
            capability = self.get_capability(capability_name)
            if not capability:
                raise ValueError(f"Unknown capability: {capability_name}")
            
            # Check if agent is busy and capability allows concurrent execution
            if (self._status == AgentStatus.BUSY and 
                len(self._running_tasks) >= capability.max_concurrent):
                raise RuntimeError("Agent is at maximum capacity")
            
            # Create task
            task = A2ATask(
                capability=capability_name,
                parameters=parameters,
                assigned_agent=self.agent_id,
                started_at=datetime.utcnow()
            )
            
            self._active_tasks[task.task_id] = task
            self._running_tasks.add(task.task_id)
            
            if len(self._running_tasks) > 0:
                self._status = AgentStatus.BUSY
            
            self.logger.info(
                "Executing capability",
                capability=capability_name,
                task_id=task.task_id,
                correlation_id=correlation_id
            )
            
            # Execute the capability
            result = await self._execute_capability_impl(capability_name, parameters)
            
            # Update task
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            task.result = result
            
            # Update metrics
            execution_time = (time.time() - start_time) * 1000
            self._metrics.successful_requests += 1
            self._update_average_response_time(execution_time)
            
            self.logger.info(
                "Capability executed successfully",
                capability=capability_name,
                task_id=task.task_id,
                execution_time_ms=execution_time
            )
            
            return result
            
        except Exception as e:
            # Update task with error
            if 'task' in locals():
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.completed_at = datetime.utcnow()
            
            self._metrics.failed_requests += 1
            
            self.logger.error(
                "Capability execution failed",
                capability=capability_name,
                error=str(e),
                correlation_id=correlation_id
            )
            raise
            
        finally:
            # Cleanup
            if 'task' in locals():
                self._running_tasks.discard(task.task_id)
                
            if len(self._running_tasks) == 0:
                self._status = AgentStatus.READY

    # Abstract methods that subclasses must implement

    @abstractmethod
    async def _initialize(self) -> None:
        """Initialize agent-specific components"""
        pass

    @abstractmethod
    async def _cleanup(self) -> None:
        """Cleanup agent-specific resources"""
        pass

    @abstractmethod
    async def _execute_capability_impl(
        self, 
        capability_name: str, 
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a specific capability implementation"""
        pass

    # Private methods

    def _setup_message_handlers(self) -> None:
        """Setup message type handlers"""
        self._message_handlers = {
            MessageType.REQUEST: self._handle_request,
            MessageType.RESPONSE: self._handle_response,
            MessageType.ERROR: self._handle_error,
            MessageType.NOTIFICATION: self._handle_notification,
            MessageType.HEARTBEAT: self._handle_heartbeat,
        }

    async def _setup_a2a(self) -> None:
        """Setup FastA2A communication"""
        try:
            # Create storage and broker instances
            storage = InMemoryStorage()
            broker = InMemoryBroker()
            
            # Create FastA2A instance
            self._fasta2a = FastA2A(
                storage=storage,
                broker=broker,
                name=self.name,
                description=self.description,
                version=self.version,
                url=self.endpoint or "http://localhost:8000",
            )
            
            # Register agent capabilities as skills
            for capability in self._capabilities.values():
                skill = Skill(
                    name=capability.name,
                    description=capability.description,
                    # Additional skill configuration would go here
                )
                # Register skill with FastA2A
                # This would depend on the actual FastA2A skill registration API
                
            self.logger.info("A2A communication setup complete")
            
        except Exception as e:
            self.logger.error("Failed to setup A2A communication", error=str(e))
            raise

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat messages"""
        while self._status != AgentStatus.OFFLINE:
            try:
                # Send heartbeat to registry or other agents
                await self._send_heartbeat()
                await asyncio.sleep(self.heartbeat_interval)
                
            except Exception as e:
                self.logger.warning("Heartbeat failed", error=str(e))
                await asyncio.sleep(5)  # Retry after 5 seconds

    async def _cleanup_loop(self) -> None:
        """Cleanup expired tasks and old data"""
        while self._status != AgentStatus.OFFLINE:
            try:
                await self._cleanup_expired_tasks()
                await asyncio.sleep(60)  # Run every minute
                
            except Exception as e:
                self.logger.warning("Cleanup failed", error=str(e))

    async def _send_heartbeat(self) -> None:
        """Send heartbeat message"""
        # Implementation depends on discovery mechanism
        pass

    async def _cleanup_expired_tasks(self) -> None:
        """Remove expired and completed tasks"""
        current_time = datetime.utcnow()
        expired_tasks = []
        
        for task_id, task in self._active_tasks.items():
            # Remove completed tasks older than 1 hour
            if (task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED] and
                task.completed_at and 
                (current_time - task.completed_at).total_seconds() > 3600):
                expired_tasks.append(task_id)
        
        for task_id in expired_tasks:
            del self._active_tasks[task_id]
            
        if expired_tasks:
            self.logger.debug("Cleaned up expired tasks", count=len(expired_tasks))

    async def _cancel_task(self, task_id: str) -> None:
        """Cancel an active task"""
        if task_id in self._active_tasks:
            task = self._active_tasks[task_id]
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.utcnow()
            self._running_tasks.discard(task_id)

    def _update_average_response_time(self, execution_time_ms: float) -> None:
        """Update average response time metric"""
        total_requests = self._metrics.successful_requests
        if total_requests == 1:
            self._metrics.average_response_time_ms = execution_time_ms
        else:
            # Exponential moving average
            alpha = 0.1
            self._metrics.average_response_time_ms = (
                alpha * execution_time_ms + 
                (1 - alpha) * self._metrics.average_response_time_ms
            )

    # JSON-RPC Message handlers

    async def _handle_incoming_message(self, envelope: A2AMessageEnvelope) -> None:
        """
        Handle incoming JSON-RPC message envelope.
        
        Args:
            envelope: Incoming message envelope
        """
        try:
            # Validate incoming message
            validation_result = validate_message(envelope)
            if not validation_result.is_valid:
                self.logger.warning(
                    "Received invalid message",
                    envelope_id=envelope.envelope_id,
                    errors=validation_result.errors
                )
                # Send error response if possible
                if isinstance(envelope.jsonrpc_message, JSONRPCRequest):
                    await self._send_validation_error_response(envelope, validation_result)
                return
            
            self.logger.debug(
                "Handling incoming message",
                envelope_id=envelope.envelope_id,
                sender=envelope.sender_id,
                message_type=type(envelope.jsonrpc_message).__name__
            )
            
            # Route to appropriate handler
            jsonrpc_msg = envelope.jsonrpc_message
            
            if isinstance(jsonrpc_msg, JSONRPCRequest):
                await self._handle_jsonrpc_request(envelope, jsonrpc_msg)
            elif isinstance(jsonrpc_msg, JSONRPCResponse):
                await self._handle_jsonrpc_response(envelope, jsonrpc_msg)
            elif isinstance(jsonrpc_msg, JSONRPCErrorResponse):
                await self._handle_jsonrpc_error_response(envelope, jsonrpc_msg)
            elif isinstance(jsonrpc_msg, JSONRPCNotification):
                await self._handle_jsonrpc_notification(envelope, jsonrpc_msg)
            else:
                self.logger.warning(
                    "Unknown message type",
                    envelope_id=envelope.envelope_id,
                    message_type=type(jsonrpc_msg).__name__
                )
                
        except Exception as e:
            self.logger.error(
                "Error handling incoming message",
                envelope_id=envelope.envelope_id,
                error=str(e)
            )

    async def _handle_jsonrpc_request(self, envelope: A2AMessageEnvelope, request: JSONRPCRequest) -> None:
        """Handle JSON-RPC request messages"""
        try:
            method = request.method
            params = request.params or {}
            
            if method == A2AMethod.EXECUTE_CAPABILITY:
                await self._handle_capability_execution_request(envelope, request)
            elif method == A2AMethod.LIST_CAPABILITIES:
                await self._handle_list_capabilities_request(envelope, request)
            elif method == A2AMethod.GET_CAPABILITY_INFO:
                await self._handle_capability_info_request(envelope, request)
            elif method == A2AMethod.GET_AGENT_INFO:
                await self._handle_agent_info_request(envelope, request)
            elif method == A2AMethod.GET_AGENT_STATUS:
                await self._handle_agent_status_request(envelope, request)
            elif method == A2AMethod.HEARTBEAT:
                await self._handle_heartbeat_request(envelope, request)
            else:
                # Unknown method
                error_response = create_error_response(
                    sender_id=self.agent_id,
                    recipient_id=envelope.sender_id,
                    request_id=request.id,
                    error_code=JSONRPCErrorCode.METHOD_NOT_FOUND,
                    error_message=f"Method not found: {method}",
                    correlation_id=envelope.correlation_id
                )
                await self.send_message(error_response)
                
        except Exception as e:
            self.logger.error("Error handling JSON-RPC request", error=str(e))
            # Send internal error response
            error_response = create_error_response(
                sender_id=self.agent_id,
                recipient_id=envelope.sender_id,
                request_id=request.id,
                error_code=JSONRPCErrorCode.INTERNAL_ERROR,
                error_message=f"Internal error: {str(e)}",
                correlation_id=envelope.correlation_id
            )
            await self.send_message(error_response)

    async def _handle_capability_execution_request(self, envelope: A2AMessageEnvelope, request: JSONRPCRequest) -> None:
        """Handle capability execution request"""
        try:
            params = request.params or {}
            capability_name = params.get('capability_name')
            parameters = params.get('parameters', {})
            
            if not capability_name:
                error_response = create_error_response(
                    sender_id=self.agent_id,
                    recipient_id=envelope.sender_id,
                    request_id=request.id,
                    error_code=JSONRPCErrorCode.INVALID_PARAMS,
                    error_message="capability_name is required",
                    correlation_id=envelope.correlation_id
                )
                await self.send_message(error_response)
                return
            
            # Execute capability
            result = await self.execute_capability(
                capability_name=capability_name,
                parameters=parameters,
                correlation_id=envelope.correlation_id
            )
            
            # Send success response
            success_response = create_success_response(
                sender_id=self.agent_id,
                recipient_id=envelope.sender_id,
                request_id=request.id,
                result=result,
                correlation_id=envelope.correlation_id
            )
            await self.send_message(success_response)
            
        except ValueError as e:
            # Capability not found or invalid parameters
            error_response = create_error_response(
                sender_id=self.agent_id,
                recipient_id=envelope.sender_id,
                request_id=request.id,
                error_code=JSONRPCErrorCode.CAPABILITY_NOT_FOUND,
                error_message=str(e),
                correlation_id=envelope.correlation_id
            )
            await self.send_message(error_response)
        except Exception as e:
            # Internal execution error
            error_response = create_error_response(
                sender_id=self.agent_id,
                recipient_id=envelope.sender_id,
                request_id=request.id,
                error_code=JSONRPCErrorCode.INTERNAL_ERROR,
                error_message=f"Execution failed: {str(e)}",
                correlation_id=envelope.correlation_id
            )
            await self.send_message(error_response)

    async def _handle_list_capabilities_request(self, envelope: A2AMessageEnvelope, request: JSONRPCRequest) -> None:
        """Handle list capabilities request"""
        capabilities_data = [cap.model_dump() for cap in self.list_capabilities()]
        
        success_response = create_success_response(
            sender_id=self.agent_id,
            recipient_id=envelope.sender_id,
            request_id=request.id,
            result={"capabilities": capabilities_data},
            correlation_id=envelope.correlation_id
        )
        await self.send_message(success_response)

    async def _handle_capability_info_request(self, envelope: A2AMessageEnvelope, request: JSONRPCRequest) -> None:
        """Handle capability info request"""
        params = request.params or {}
        capability_name = params.get('capability_name')
        
        if not capability_name:
            error_response = create_error_response(
                sender_id=self.agent_id,
                recipient_id=envelope.sender_id,
                request_id=request.id,
                error_code=JSONRPCErrorCode.INVALID_PARAMS,
                error_message="capability_name is required",
                correlation_id=envelope.correlation_id
            )
            await self.send_message(error_response)
            return
        
        capability = self.get_capability(capability_name)
        if not capability:
            error_response = create_error_response(
                sender_id=self.agent_id,
                recipient_id=envelope.sender_id,
                request_id=request.id,
                error_code=JSONRPCErrorCode.CAPABILITY_NOT_FOUND,
                error_message=f"Capability not found: {capability_name}",
                correlation_id=envelope.correlation_id
            )
            await self.send_message(error_response)
            return
        
        success_response = create_success_response(
            sender_id=self.agent_id,
            recipient_id=envelope.sender_id,
            request_id=request.id,
            result=capability.model_dump(),
            correlation_id=envelope.correlation_id
        )
        await self.send_message(success_response)

    async def _handle_agent_info_request(self, envelope: A2AMessageEnvelope, request: JSONRPCRequest) -> None:
        """Handle agent info request"""
        success_response = create_success_response(
            sender_id=self.agent_id,
            recipient_id=envelope.sender_id,
            request_id=request.id,
            result=self.agent_card.model_dump(),
            correlation_id=envelope.correlation_id
        )
        await self.send_message(success_response)

    async def _handle_agent_status_request(self, envelope: A2AMessageEnvelope, request: JSONRPCRequest) -> None:
        """Handle agent status request"""
        status_data = {
            "status": self._status.value,
            "metrics": self.metrics.model_dump(),
            "active_tasks": len(self._active_tasks),
            "uptime_seconds": time.time() - self._start_time
        }
        
        success_response = create_success_response(
            sender_id=self.agent_id,
            recipient_id=envelope.sender_id,
            request_id=request.id,
            result=status_data,
            correlation_id=envelope.correlation_id
        )
        await self.send_message(success_response)

    async def _handle_heartbeat_request(self, envelope: A2AMessageEnvelope, request: JSONRPCRequest) -> None:
        """Handle heartbeat request"""
        heartbeat_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "status": self._status.value,
            "agent_id": self.agent_id
        }
        
        success_response = create_success_response(
            sender_id=self.agent_id,
            recipient_id=envelope.sender_id,
            request_id=request.id,
            result=heartbeat_data,
            correlation_id=envelope.correlation_id
        )
        await self.send_message(success_response)

    async def _handle_jsonrpc_response(self, envelope: A2AMessageEnvelope, response: JSONRPCResponse) -> None:
        """Handle JSON-RPC response messages"""
        # Responses are typically handled by the message router for request correlation
        # This is mainly for logging and metrics
        self.logger.debug(
            "Received response",
            envelope_id=envelope.envelope_id,
            request_id=response.id
        )

    async def _handle_jsonrpc_error_response(self, envelope: A2AMessageEnvelope, error_response: JSONRPCErrorResponse) -> None:
        """Handle JSON-RPC error response messages"""
        self.logger.warning(
            "Received error response",
            envelope_id=envelope.envelope_id,
            request_id=error_response.id,
            error_code=error_response.error.code,
            error_message=error_response.error.message
        )

    async def _handle_jsonrpc_notification(self, envelope: A2AMessageEnvelope, notification: JSONRPCNotification) -> None:
        """Handle JSON-RPC notification messages"""
        try:
            method = notification.method
            params = notification.params or {}
            
            if method == A2AMethod.HEARTBEAT:
                await self._handle_heartbeat_notification(envelope, notification)
            elif method == A2AMethod.TASK_STATUS_CHANGED:
                await self._handle_task_status_notification(envelope, notification)
            elif method == A2AMethod.AGENT_STATUS_CHANGED:
                await self._handle_agent_status_notification(envelope, notification)
            elif method == A2AMethod.CAPABILITY_UPDATED:
                await self._handle_capability_updated_notification(envelope, notification)
            else:
                self.logger.debug(
                    "Received unknown notification",
                    method=method,
                    params=params
                )
                
        except Exception as e:
            self.logger.error("Error handling notification", error=str(e))

    async def _handle_heartbeat_notification(self, envelope: A2AMessageEnvelope, notification: JSONRPCNotification) -> None:
        """Handle heartbeat notification"""
        self.logger.debug(
            "Received heartbeat",
            sender=envelope.sender_id,
            params=notification.params
        )

    async def _handle_task_status_notification(self, envelope: A2AMessageEnvelope, notification: JSONRPCNotification) -> None:
        """Handle task status change notification"""
        self.logger.info(
            "Task status changed",
            sender=envelope.sender_id,
            params=notification.params
        )

    async def _handle_agent_status_notification(self, envelope: A2AMessageEnvelope, notification: JSONRPCNotification) -> None:
        """Handle agent status change notification"""
        self.logger.info(
            "Agent status changed",
            sender=envelope.sender_id,
            params=notification.params
        )

    async def _handle_capability_updated_notification(self, envelope: A2AMessageEnvelope, notification: JSONRPCNotification) -> None:
        """Handle capability updated notification"""
        self.logger.info(
            "Capability updated",
            sender=envelope.sender_id,
            params=notification.params
        )

    async def _send_validation_error_response(self, envelope: A2AMessageEnvelope, validation_result: ValidationResult) -> None:
        """Send validation error response"""
        if isinstance(envelope.jsonrpc_message, JSONRPCRequest):
            error_response = create_error_response(
                sender_id=self.agent_id,
                recipient_id=envelope.sender_id,
                request_id=envelope.jsonrpc_message.id,
                error_code=JSONRPCErrorCode.VALIDATION_ERROR,
                error_message="Message validation failed",
                error_data={"errors": validation_result.errors},
                correlation_id=envelope.correlation_id
            )
            await self.send_message(error_response)

    # Legacy message handlers (for backward compatibility)

    async def _handle_request(self, message: A2ARequest) -> None:
        """Handle incoming request messages (legacy)"""
        # Convert to JSON-RPC and delegate
        pass

    async def _handle_response(self, message: A2AResponse) -> None:
        """Handle response messages (legacy)"""
        # Convert to JSON-RPC and delegate
        pass

    async def _handle_error(self, message: A2AError) -> None:
        """Handle error messages (legacy)"""
        # Convert to JSON-RPC and delegate
        pass

    async def _handle_notification(self, message: A2AMessage) -> None:
        """Handle notification messages (legacy)"""
        # Convert to JSON-RPC and delegate
        pass

    async def _handle_heartbeat(self, message: A2AMessage) -> None:
        """Handle heartbeat messages (legacy)"""
        # Convert to JSON-RPC and delegate
        pass