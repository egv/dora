"""
A2A Protocol Data Models

This module defines the data models for Agent-to-Agent communication
using Pydantic for validation and serialization.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class CapabilityType(str, Enum):
    """Types of capabilities an agent can provide"""
    DATA_COLLECTION = "data_collection"
    DATA_VERIFICATION = "data_verification"
    MESSAGE_GENERATION = "message_generation"
    AUDIENCE_ANALYSIS = "audience_analysis"
    IMAGE_GENERATION = "image_generation"
    CALENDAR_BUILDING = "calendar_building"


class MessageType(str, Enum):
    """Types of A2A messages"""
    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"
    NOTIFICATION = "notification"
    HEARTBEAT = "heartbeat"


class AgentStatus(str, Enum):
    """Agent status indicators"""
    INITIALIZING = "initializing"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"


class Capability(BaseModel):
    """Represents a capability that an agent can provide"""
    name: str = Field(..., description="Unique name of the capability")
    description: str = Field(..., description="Human-readable description")
    capability_type: CapabilityType = Field(..., description="Type of capability")
    input_schema: Dict[str, Any] = Field(..., description="JSON schema for input validation")
    output_schema: Dict[str, Any] = Field(..., description="JSON schema for output validation")
    version: str = Field(default="1.0.0", description="Capability version")
    max_concurrent: int = Field(default=1, description="Maximum concurrent executions")
    timeout_seconds: int = Field(default=60, description="Default timeout for execution")


class AgentCard(BaseModel):
    """Agent identity and capability information"""
    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Human-readable agent name")
    description: str = Field(..., description="Agent description and purpose")
    version: str = Field(default="1.0.0", description="Agent version")
    capabilities: List[Capability] = Field(default_factory=list, description="Available capabilities")
    status: AgentStatus = Field(default=AgentStatus.INITIALIZING, description="Current agent status")
    endpoint: Optional[str] = Field(default=None, description="Agent communication endpoint")
    heartbeat_interval: int = Field(default=30, description="Heartbeat interval in seconds")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class A2AMessage(BaseModel):
    """Standard A2A message format"""
    message_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique message ID")
    sender_id: str = Field(..., description="Sender agent ID")
    recipient_id: str = Field(..., description="Recipient agent ID")
    message_type: MessageType = Field(..., description="Type of message")
    capability: Optional[str] = Field(default=None, description="Capability being invoked")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Message payload")
    correlation_id: Optional[str] = Field(default=None, description="Correlation ID for request tracking")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Message timestamp")
    ttl: int = Field(default=60, description="Time to live in seconds")
    priority: int = Field(default=5, description="Message priority (1=high, 10=low)")
    version: str = Field(default="1.0", description="Protocol version")


class A2ARequest(A2AMessage):
    """A2A request message"""
    message_type: MessageType = Field(default=MessageType.REQUEST, description="Message type")
    capability: str = Field(..., description="Capability being requested")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Request parameters")


class A2AResponse(A2AMessage):
    """A2A response message"""
    message_type: MessageType = Field(default=MessageType.RESPONSE, description="Message type")
    success: bool = Field(..., description="Whether the request was successful")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Response result")
    error: Optional[str] = Field(default=None, description="Error message if unsuccessful")
    execution_time_ms: Optional[int] = Field(default=None, description="Execution time in milliseconds")


class A2AError(A2AMessage):
    """A2A error message"""
    message_type: MessageType = Field(default=MessageType.ERROR, description="Message type")
    error_code: str = Field(..., description="Error code")
    error_message: str = Field(..., description="Error description")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional error details")


class TaskStatus(str, Enum):
    """Task execution status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class A2ATask(BaseModel):
    """Represents a task in the A2A system"""
    task_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique task ID")
    capability: str = Field(..., description="Capability to execute")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Task parameters")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current task status")
    assigned_agent: Optional[str] = Field(default=None, description="Agent assigned to execute task")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Task creation time")
    started_at: Optional[datetime] = Field(default=None, description="Task start time")
    completed_at: Optional[datetime] = Field(default=None, description="Task completion time")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Task result")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    priority: int = Field(default=5, description="Task priority (1=high, 10=low)")
    timeout_seconds: int = Field(default=300, description="Task timeout")
    retry_count: int = Field(default=0, description="Number of retries attempted")
    max_retries: int = Field(default=3, description="Maximum retry attempts")


class AgentMetrics(BaseModel):
    """Agent performance metrics"""
    total_requests: int = Field(default=0, description="Total requests processed")
    successful_requests: int = Field(default=0, description="Successful requests")
    failed_requests: int = Field(default=0, description="Failed requests")
    average_response_time_ms: float = Field(default=0.0, description="Average response time")
    concurrent_tasks: int = Field(default=0, description="Currently executing tasks")
    last_activity: Optional[datetime] = Field(default=None, description="Last activity timestamp")
    uptime_seconds: int = Field(default=0, description="Agent uptime in seconds")