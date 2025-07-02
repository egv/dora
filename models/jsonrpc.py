"""
JSON-RPC 2.0 Message Models for A2A Communication

This module implements JSON-RPC 2.0 compliant message formats for Agent-to-Agent
communication as specified in the JSON-RPC 2.0 specification.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field, validator


class JSONRPCVersion(str, Enum):
    """JSON-RPC version"""
    V2_0 = "2.0"


class JSONRPCErrorCode(int, Enum):
    """Standard JSON-RPC error codes"""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    
    # Custom A2A error codes (range -32099 to -32000 reserved for implementation)
    AGENT_NOT_FOUND = -32001
    CAPABILITY_NOT_FOUND = -32002
    AGENT_UNAVAILABLE = -32003
    TIMEOUT_ERROR = -32004
    AUTHENTICATION_ERROR = -32005
    AUTHORIZATION_ERROR = -32006
    RATE_LIMIT_EXCEEDED = -32007
    QUOTA_EXCEEDED = -32008
    VALIDATION_ERROR = -32009
    PROTOCOL_VERSION_MISMATCH = -32010


class JSONRPCError(BaseModel):
    """JSON-RPC 2.0 error object"""
    code: int = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    data: Optional[Any] = Field(default=None, description="Additional error data")

    @validator('code')
    def validate_error_code(cls, v):
        """Validate error code is within acceptable ranges"""
        if v == 0:
            raise ValueError("Error code cannot be 0")
        return v


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 request message"""
    jsonrpc: JSONRPCVersion = Field(default=JSONRPCVersion.V2_0, description="JSON-RPC version")
    method: str = Field(..., description="Method name to invoke")
    params: Optional[Union[Dict[str, Any], List[Any]]] = Field(default=None, description="Method parameters")
    id: Optional[Union[str, int]] = Field(default_factory=lambda: str(uuid4()), description="Request identifier")

    @validator('method')
    def validate_method_name(cls, v):
        """Validate method name format"""
        if not v or not isinstance(v, str):
            raise ValueError("Method name must be a non-empty string")
        if v.startswith('rpc.'):
            raise ValueError("Method names starting with 'rpc.' are reserved")
        return v


class JSONRPCNotification(BaseModel):
    """JSON-RPC 2.0 notification message (request without id)"""
    jsonrpc: JSONRPCVersion = Field(default=JSONRPCVersion.V2_0, description="JSON-RPC version")
    method: str = Field(..., description="Method name to invoke")
    params: Optional[Union[Dict[str, Any], List[Any]]] = Field(default=None, description="Method parameters")

    @validator('method')
    def validate_method_name(cls, v):
        """Validate method name format"""
        if not v or not isinstance(v, str):
            raise ValueError("Method name must be a non-empty string")
        if v.startswith('rpc.'):
            raise ValueError("Method names starting with 'rpc.' are reserved")
        return v


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 success response"""
    jsonrpc: JSONRPCVersion = Field(default=JSONRPCVersion.V2_0, description="JSON-RPC version")
    result: Any = Field(..., description="Result of the method call")
    id: Union[str, int] = Field(..., description="Request identifier")


class JSONRPCErrorResponse(BaseModel):
    """JSON-RPC 2.0 error response"""
    jsonrpc: JSONRPCVersion = Field(default=JSONRPCVersion.V2_0, description="JSON-RPC version")
    error: JSONRPCError = Field(..., description="Error information")
    id: Optional[Union[str, int]] = Field(..., description="Request identifier (null if parse error)")


class JSONRPCBatch(BaseModel):
    """JSON-RPC 2.0 batch request/response"""
    requests: List[Union[JSONRPCRequest, JSONRPCNotification]] = Field(..., description="Batch of requests")

    @validator('requests')
    def validate_batch_not_empty(cls, v):
        """Validate batch is not empty"""
        if not v:
            raise ValueError("Batch must contain at least one request")
        return v


class A2AMessageEnvelope(BaseModel):
    """
    A2A message envelope wrapping JSON-RPC messages with additional metadata.
    This provides the transport layer information needed for agent communication.
    """
    # Transport metadata
    envelope_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique envelope ID")
    sender_id: str = Field(..., description="Sender agent ID")
    recipient_id: str = Field(..., description="Recipient agent ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Message timestamp")
    
    # Message routing and delivery
    correlation_id: Optional[str] = Field(default=None, description="Correlation ID for request tracking")
    reply_to: Optional[str] = Field(default=None, description="Agent ID to send response to")
    ttl: int = Field(default=60, description="Time to live in seconds")
    priority: int = Field(default=5, description="Message priority (1=high, 10=low)")
    
    # Protocol and versioning
    protocol_version: str = Field(default="1.0", description="A2A protocol version")
    compression: Optional[str] = Field(default=None, description="Compression algorithm used")
    encryption: Optional[str] = Field(default=None, description="Encryption algorithm used")
    
    # JSON-RPC payload
    jsonrpc_message: Union[
        JSONRPCRequest, 
        JSONRPCNotification, 
        JSONRPCResponse, 
        JSONRPCErrorResponse,
        JSONRPCBatch
    ] = Field(..., description="JSON-RPC message payload")

    @validator('priority')
    def validate_priority(cls, v):
        """Validate priority is within acceptable range"""
        if not 1 <= v <= 10:
            raise ValueError("Priority must be between 1 (high) and 10 (low)")
        return v

    @validator('ttl')
    def validate_ttl(cls, v):
        """Validate TTL is positive"""
        if v <= 0:
            raise ValueError("TTL must be positive")
        return v


# A2A-specific method names for JSON-RPC
class A2AMethod(str, Enum):
    """Standard A2A method names for JSON-RPC calls"""
    # Capability management
    EXECUTE_CAPABILITY = "a2a.capability.execute"
    LIST_CAPABILITIES = "a2a.capability.list"
    GET_CAPABILITY_INFO = "a2a.capability.info"
    
    # Agent management
    GET_AGENT_INFO = "a2a.agent.info"
    GET_AGENT_STATUS = "a2a.agent.status"
    HEARTBEAT = "a2a.agent.heartbeat"
    
    # Discovery
    DISCOVER_AGENTS = "a2a.discovery.agents"
    DISCOVER_CAPABILITIES = "a2a.discovery.capabilities"
    
    # Task management
    CREATE_TASK = "a2a.task.create"
    GET_TASK_STATUS = "a2a.task.status"
    CANCEL_TASK = "a2a.task.cancel"
    
    # Notifications
    TASK_STATUS_CHANGED = "a2a.notify.task_status_changed"
    AGENT_STATUS_CHANGED = "a2a.notify.agent_status_changed"
    CAPABILITY_UPDATED = "a2a.notify.capability_updated"


# Common parameter schemas for A2A methods
class A2ACapabilityExecuteParams(BaseModel):
    """Parameters for capability execution"""
    capability_name: str = Field(..., description="Name of capability to execute")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Capability parameters")
    timeout: Optional[int] = Field(default=None, description="Execution timeout in seconds")
    priority: int = Field(default=5, description="Execution priority")


class A2ADiscoverAgentsParams(BaseModel):
    """Parameters for agent discovery"""
    capability_name: Optional[str] = Field(default=None, description="Required capability name")
    capability_type: Optional[str] = Field(default=None, description="Required capability type")
    status: Optional[str] = Field(default=None, description="Required agent status")
    exclude_agents: List[str] = Field(default_factory=list, description="Agent IDs to exclude")
    max_results: int = Field(default=10, description="Maximum number of results")


class A2ATaskParams(BaseModel):
    """Parameters for task operations"""
    task_id: str = Field(..., description="Task identifier")
    capability: Optional[str] = Field(default=None, description="Capability name for new tasks")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="Task parameters for new tasks")
    timeout: Optional[int] = Field(default=None, description="Task timeout in seconds")


def create_capability_request(
    sender_id: str,
    recipient_id: str,
    capability_name: str,
    parameters: Dict[str, Any],
    correlation_id: Optional[str] = None,
    timeout: int = 60,
    priority: int = 5
) -> A2AMessageEnvelope:
    """
    Helper function to create a capability execution request.
    
    Args:
        sender_id: ID of the sending agent
        recipient_id: ID of the recipient agent
        capability_name: Name of capability to execute
        parameters: Parameters for capability execution
        correlation_id: Optional correlation ID for tracking
        timeout: Request timeout in seconds
        priority: Message priority (1=high, 10=low)
        
    Returns:
        A2AMessageEnvelope containing the JSON-RPC request
    """
    request_params = A2ACapabilityExecuteParams(
        capability_name=capability_name,
        parameters=parameters,
        timeout=timeout,
        priority=priority
    )
    
    jsonrpc_request = JSONRPCRequest(
        method=A2AMethod.EXECUTE_CAPABILITY,
        params=request_params.dict()
    )
    
    return A2AMessageEnvelope(
        sender_id=sender_id,
        recipient_id=recipient_id,
        correlation_id=correlation_id,
        ttl=timeout,
        priority=priority,
        jsonrpc_message=jsonrpc_request
    )


def create_success_response(
    sender_id: str,
    recipient_id: str,
    request_id: Union[str, int],
    result: Any,
    correlation_id: Optional[str] = None
) -> A2AMessageEnvelope:
    """
    Helper function to create a success response.
    
    Args:
        sender_id: ID of the sending agent
        recipient_id: ID of the recipient agent
        request_id: ID of the original request
        result: Result data
        correlation_id: Optional correlation ID for tracking
        
    Returns:
        A2AMessageEnvelope containing the JSON-RPC response
    """
    jsonrpc_response = JSONRPCResponse(
        result=result,
        id=request_id
    )
    
    return A2AMessageEnvelope(
        sender_id=sender_id,
        recipient_id=recipient_id,
        correlation_id=correlation_id,
        jsonrpc_message=jsonrpc_response
    )


def create_error_response(
    sender_id: str,
    recipient_id: str,
    request_id: Optional[Union[str, int]],
    error_code: int,
    error_message: str,
    error_data: Optional[Any] = None,
    correlation_id: Optional[str] = None
) -> A2AMessageEnvelope:
    """
    Helper function to create an error response.
    
    Args:
        sender_id: ID of the sending agent
        recipient_id: ID of the recipient agent
        request_id: ID of the original request (None for parse errors)
        error_code: JSON-RPC error code
        error_message: Error message
        error_data: Optional additional error data
        correlation_id: Optional correlation ID for tracking
        
    Returns:
        A2AMessageEnvelope containing the JSON-RPC error response
    """
    error = JSONRPCError(
        code=error_code,
        message=error_message,
        data=error_data
    )
    
    jsonrpc_error_response = JSONRPCErrorResponse(
        error=error,
        id=request_id
    )
    
    return A2AMessageEnvelope(
        sender_id=sender_id,
        recipient_id=recipient_id,
        correlation_id=correlation_id,
        jsonrpc_message=jsonrpc_error_response
    )


def create_notification(
    sender_id: str,
    recipient_id: str,
    method: str,
    params: Optional[Union[Dict[str, Any], List[Any]]] = None,
    correlation_id: Optional[str] = None
) -> A2AMessageEnvelope:
    """
    Helper function to create a notification.
    
    Args:
        sender_id: ID of the sending agent
        recipient_id: ID of the recipient agent
        method: Notification method name
        params: Optional notification parameters
        correlation_id: Optional correlation ID for tracking
        
    Returns:
        A2AMessageEnvelope containing the JSON-RPC notification
    """
    jsonrpc_notification = JSONRPCNotification(
        method=method,
        params=params
    )
    
    return A2AMessageEnvelope(
        sender_id=sender_id,
        recipient_id=recipient_id,
        correlation_id=correlation_id,
        jsonrpc_message=jsonrpc_notification
    )