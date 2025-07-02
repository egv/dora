"""
A2A Message Serialization and Transport System

This module provides serialization, deserialization, and transport capabilities
for A2A messages using JSON-RPC 2.0 format with optional compression and encryption.
"""

import asyncio
import gzip
import json
import time
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

import structlog
from pydantic import ValidationError

from models.a2a import A2AMessage, A2ARequest, A2AResponse, A2AError, MessageType
from models.jsonrpc import (
    A2AMessageEnvelope,
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCErrorResponse,
    JSONRPCNotification,
    JSONRPCBatch,
    JSONRPCError,
    JSONRPCErrorCode,
    A2AMethod,
    create_capability_request,
    create_success_response,
    create_error_response,
    create_notification,
)


logger = structlog.get_logger(__name__)


class MessageSerializationError(Exception):
    """Raised when message serialization fails"""
    pass


class MessageDeserializationError(Exception):
    """Raised when message deserialization fails"""
    pass


class MessageValidationError(Exception):
    """Raised when message validation fails"""
    pass


class A2AMessageSerializer:
    """
    Handles serialization and deserialization of A2A messages to/from JSON-RPC format.
    """
    
    def __init__(self, 
                 enable_compression: bool = True,
                 compression_threshold: int = 1024,
                 enable_encryption: bool = False):
        """
        Initialize the message serializer.
        
        Args:
            enable_compression: Whether to enable compression for large messages
            compression_threshold: Minimum message size in bytes to trigger compression
            enable_encryption: Whether to enable message encryption (not implemented yet)
        """
        self.enable_compression = enable_compression
        self.compression_threshold = compression_threshold
        self.enable_encryption = enable_encryption
        
        self.logger = structlog.get_logger(__name__).bind(
            component="message_serializer"
        )
    
    def serialize_message(self, envelope: A2AMessageEnvelope) -> bytes:
        """
        Serialize an A2A message envelope to bytes.
        
        Args:
            envelope: A2A message envelope to serialize
            
        Returns:
            Serialized message as bytes
            
        Raises:
            MessageSerializationError: If serialization fails
        """
        try:
            # Convert to JSON
            envelope_dict = envelope.dict()
            json_data = json.dumps(envelope_dict, default=self._json_serializer, separators=(',', ':'))
            message_bytes = json_data.encode('utf-8')
            
            # Apply compression if enabled and message is large enough
            if (self.enable_compression and 
                len(message_bytes) > self.compression_threshold):
                message_bytes = gzip.compress(message_bytes)
                # Note: compression info is stored in envelope.compression field
            
            # TODO: Apply encryption if enabled
            if self.enable_encryption:
                # Placeholder for encryption implementation
                pass
            
            self.logger.debug(
                "Message serialized",
                envelope_id=envelope.envelope_id,
                original_size=len(json_data),
                compressed_size=len(message_bytes),
                compression_enabled=self.enable_compression and len(message_bytes) != len(json_data.encode('utf-8'))
            )
            
            return message_bytes
            
        except Exception as e:
            self.logger.error("Message serialization failed", error=str(e))
            raise MessageSerializationError(f"Failed to serialize message: {e}")
    
    def deserialize_message(self, message_bytes: bytes) -> A2AMessageEnvelope:
        """
        Deserialize bytes to an A2A message envelope.
        
        Args:
            message_bytes: Serialized message bytes
            
        Returns:
            Deserialized A2A message envelope
            
        Raises:
            MessageDeserializationError: If deserialization fails
        """
        try:
            # TODO: Handle decryption if enabled
            if self.enable_encryption:
                # Placeholder for decryption implementation
                pass
            
            # Handle decompression - we need to detect if it's compressed
            try:
                # Try to decompress first
                decompressed_bytes = gzip.decompress(message_bytes)
                self.logger.debug("Message decompressed", 
                                compressed_size=len(message_bytes),
                                decompressed_size=len(decompressed_bytes))
                message_bytes = decompressed_bytes
            except gzip.BadGzipFile:
                # Not compressed, use as-is
                pass
            
            # Convert from JSON
            json_data = message_bytes.decode('utf-8')
            envelope_dict = json.loads(json_data)
            
            # Deserialize to A2A message envelope
            envelope = A2AMessageEnvelope(**envelope_dict)
            
            self.logger.debug(
                "Message deserialized",
                envelope_id=envelope.envelope_id,
                sender_id=envelope.sender_id,
                recipient_id=envelope.recipient_id
            )
            
            return envelope
            
        except ValidationError as e:
            self.logger.error("Message validation failed", error=str(e))
            raise MessageDeserializationError(f"Message validation failed: {e}")
        except Exception as e:
            self.logger.error("Message deserialization failed", error=str(e))
            raise MessageDeserializationError(f"Failed to deserialize message: {e}")
    
    def _json_serializer(self, obj):
        """Custom JSON serializer for datetime and other objects"""
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


class A2AMessageConverter:
    """
    Converts between legacy A2A message formats and JSON-RPC envelope format.
    """
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__).bind(
            component="message_converter"
        )
    
    def a2a_to_envelope(self, a2a_message: A2AMessage) -> A2AMessageEnvelope:
        """
        Convert legacy A2A message to JSON-RPC envelope format.
        
        Args:
            a2a_message: Legacy A2A message
            
        Returns:
            JSON-RPC envelope containing the converted message
        """
        try:
            if isinstance(a2a_message, A2ARequest):
                return self._convert_request(a2a_message)
            elif isinstance(a2a_message, A2AResponse):
                return self._convert_response(a2a_message)
            elif isinstance(a2a_message, A2AError):
                return self._convert_error(a2a_message)
            else:
                return self._convert_generic_message(a2a_message)
                
        except Exception as e:
            self.logger.error("A2A to envelope conversion failed", error=str(e))
            raise MessageSerializationError(f"Failed to convert A2A message: {e}")
    
    def envelope_to_a2a(self, envelope: A2AMessageEnvelope) -> A2AMessage:
        """
        Convert JSON-RPC envelope to legacy A2A message format.
        
        Args:
            envelope: JSON-RPC envelope
            
        Returns:
            Legacy A2A message
        """
        try:
            jsonrpc_msg = envelope.jsonrpc_message
            
            if isinstance(jsonrpc_msg, JSONRPCRequest):
                return self._convert_from_request(envelope, jsonrpc_msg)
            elif isinstance(jsonrpc_msg, JSONRPCResponse):
                return self._convert_from_response(envelope, jsonrpc_msg)
            elif isinstance(jsonrpc_msg, JSONRPCErrorResponse):
                return self._convert_from_error_response(envelope, jsonrpc_msg)
            elif isinstance(jsonrpc_msg, JSONRPCNotification):
                return self._convert_from_notification(envelope, jsonrpc_msg)
            else:
                raise ValueError(f"Unsupported JSON-RPC message type: {type(jsonrpc_msg)}")
                
        except Exception as e:
            self.logger.error("Envelope to A2A conversion failed", error=str(e))
            raise MessageDeserializationError(f"Failed to convert envelope: {e}")
    
    def _convert_request(self, a2a_request: A2ARequest) -> A2AMessageEnvelope:
        """Convert A2A request to JSON-RPC envelope"""
        return create_capability_request(
            sender_id=a2a_request.sender_id,
            recipient_id=a2a_request.recipient_id,
            capability_name=a2a_request.capability,
            parameters=a2a_request.parameters,
            correlation_id=a2a_request.correlation_id,
            timeout=a2a_request.ttl,
            priority=a2a_request.priority
        )
    
    def _convert_response(self, a2a_response: A2AResponse) -> A2AMessageEnvelope:
        """Convert A2A response to JSON-RPC envelope"""
        if a2a_response.success:
            return create_success_response(
                sender_id=a2a_response.sender_id,
                recipient_id=a2a_response.recipient_id,
                request_id=a2a_response.correlation_id or a2a_response.message_id,
                result=a2a_response.result or {},
                correlation_id=a2a_response.correlation_id
            )
        else:
            return create_error_response(
                sender_id=a2a_response.sender_id,
                recipient_id=a2a_response.recipient_id,
                request_id=a2a_response.correlation_id or a2a_response.message_id,
                error_code=JSONRPCErrorCode.INTERNAL_ERROR,
                error_message=a2a_response.error or "Unknown error",
                correlation_id=a2a_response.correlation_id
            )
    
    def _convert_error(self, a2a_error: A2AError) -> A2AMessageEnvelope:
        """Convert A2A error to JSON-RPC envelope"""
        # Map A2A error codes to JSON-RPC error codes
        error_code_mapping = {
            "AGENT_NOT_FOUND": JSONRPCErrorCode.AGENT_NOT_FOUND,
            "CAPABILITY_NOT_FOUND": JSONRPCErrorCode.CAPABILITY_NOT_FOUND,
            "TIMEOUT": JSONRPCErrorCode.TIMEOUT_ERROR,
            "VALIDATION_ERROR": JSONRPCErrorCode.VALIDATION_ERROR,
        }
        
        error_code = error_code_mapping.get(
            a2a_error.error_code, 
            JSONRPCErrorCode.INTERNAL_ERROR
        )
        
        return create_error_response(
            sender_id=a2a_error.sender_id,
            recipient_id=a2a_error.recipient_id,
            request_id=a2a_error.correlation_id or a2a_error.message_id,
            error_code=error_code,
            error_message=a2a_error.error_message,
            error_data=a2a_error.details,
            correlation_id=a2a_error.correlation_id
        )
    
    def _convert_generic_message(self, a2a_message: A2AMessage) -> A2AMessageEnvelope:
        """Convert generic A2A message to JSON-RPC notification"""
        method = {
            MessageType.HEARTBEAT: A2AMethod.HEARTBEAT,
            MessageType.NOTIFICATION: "a2a.notify.generic"
        }.get(a2a_message.message_type, "a2a.notify.generic")
        
        return create_notification(
            sender_id=a2a_message.sender_id,
            recipient_id=a2a_message.recipient_id,
            method=method,
            params=a2a_message.payload,
            correlation_id=a2a_message.correlation_id
        )
    
    def _convert_from_request(self, envelope: A2AMessageEnvelope, request: JSONRPCRequest) -> A2ARequest:
        """Convert JSON-RPC request to A2A request"""
        params = request.params or {}
        if isinstance(params, dict):
            capability = params.get('capability_name', 'unknown')
            parameters = params.get('parameters', {})
        else:
            capability = 'unknown'
            parameters = {}
        
        return A2ARequest(
            sender_id=envelope.sender_id,
            recipient_id=envelope.recipient_id,
            capability=capability,
            parameters=parameters,
            correlation_id=envelope.correlation_id,
            timestamp=envelope.timestamp,
            ttl=envelope.ttl,
            priority=envelope.priority
        )
    
    def _convert_from_response(self, envelope: A2AMessageEnvelope, response: JSONRPCResponse) -> A2AResponse:
        """Convert JSON-RPC response to A2A response"""
        return A2AResponse(
            sender_id=envelope.sender_id,
            recipient_id=envelope.recipient_id,
            success=True,
            result=response.result,
            correlation_id=envelope.correlation_id,
            timestamp=envelope.timestamp,
            ttl=envelope.ttl,
            priority=envelope.priority
        )
    
    def _convert_from_error_response(self, envelope: A2AMessageEnvelope, error_response: JSONRPCErrorResponse) -> A2AError:
        """Convert JSON-RPC error response to A2A error"""
        return A2AError(
            sender_id=envelope.sender_id,
            recipient_id=envelope.recipient_id,
            error_code=str(error_response.error.code),
            error_message=error_response.error.message,
            details=error_response.error.data,
            correlation_id=envelope.correlation_id,
            timestamp=envelope.timestamp,
            ttl=envelope.ttl,
            priority=envelope.priority
        )
    
    def _convert_from_notification(self, envelope: A2AMessageEnvelope, notification: JSONRPCNotification) -> A2AMessage:
        """Convert JSON-RPC notification to A2A message"""
        message_type = MessageType.NOTIFICATION
        if notification.method == A2AMethod.HEARTBEAT:
            message_type = MessageType.HEARTBEAT
        
        return A2AMessage(
            sender_id=envelope.sender_id,
            recipient_id=envelope.recipient_id,
            message_type=message_type,
            capability=notification.method,
            payload=notification.params or {},
            correlation_id=envelope.correlation_id,
            timestamp=envelope.timestamp,
            ttl=envelope.ttl,
            priority=envelope.priority
        )


class MessageRouter:
    """
    Routes messages between agents and handles message delivery.
    """
    
    def __init__(self):
        self.serializer = A2AMessageSerializer()
        self.converter = A2AMessageConverter()
        self.message_handlers = {}
        self.pending_requests = {}  # For tracking request-response correlation
        
        self.logger = structlog.get_logger(__name__).bind(
            component="message_router"
        )
    
    def register_handler(self, agent_id: str, handler_func):
        """
        Register a message handler for an agent.
        
        Args:
            agent_id: ID of the agent
            handler_func: Async function to handle incoming messages
        """
        self.message_handlers[agent_id] = handler_func
        self.logger.debug("Message handler registered", agent_id=agent_id)
    
    def unregister_handler(self, agent_id: str):
        """
        Unregister a message handler for an agent.
        
        Args:
            agent_id: ID of the agent
        """
        if agent_id in self.message_handlers:
            del self.message_handlers[agent_id]
            self.logger.debug("Message handler unregistered", agent_id=agent_id)
    
    async def send_message(self, envelope: A2AMessageEnvelope, transport_send_func) -> Optional[A2AMessageEnvelope]:
        """
        Send a message through the transport layer.
        
        Args:
            envelope: Message envelope to send
            transport_send_func: Function to send serialized message bytes
            
        Returns:
            Response envelope if this is a request expecting a response
        """
        try:
            # Serialize message
            message_bytes = self.serializer.serialize_message(envelope)
            
            # Send through transport
            await transport_send_func(message_bytes)
            
            # If this is a request, track it for response correlation
            if isinstance(envelope.jsonrpc_message, JSONRPCRequest):
                request_id = envelope.jsonrpc_message.id
                correlation_key = f"{envelope.sender_id}:{request_id}"
                
                # Create future for response
                response_future = asyncio.Future()
                self.pending_requests[correlation_key] = response_future
                
                try:
                    # Wait for response with timeout
                    response = await asyncio.wait_for(response_future, timeout=envelope.ttl)
                    return response
                except asyncio.TimeoutError:
                    self.logger.warning("Request timeout", 
                                      envelope_id=envelope.envelope_id,
                                      timeout=envelope.ttl)
                    return None
                finally:
                    # Clean up pending request
                    self.pending_requests.pop(correlation_key, None)
            
            return None
            
        except Exception as e:
            self.logger.error("Message send failed", 
                            envelope_id=envelope.envelope_id,
                            error=str(e))
            raise
    
    async def receive_message(self, message_bytes: bytes):
        """
        Receive and process an incoming message.
        
        Args:
            message_bytes: Serialized message bytes
        """
        try:
            # Deserialize message
            envelope = self.serializer.deserialize_message(message_bytes)
            
            # Check if this is a response to a pending request
            if isinstance(envelope.jsonrpc_message, (JSONRPCResponse, JSONRPCErrorResponse)):
                request_id = envelope.jsonrpc_message.id
                correlation_key = f"{envelope.recipient_id}:{request_id}"
                
                if correlation_key in self.pending_requests:
                    # Complete the pending request
                    future = self.pending_requests[correlation_key]
                    if not future.done():
                        future.set_result(envelope)
                    return
            
            # Route to handler
            handler = self.message_handlers.get(envelope.recipient_id)
            if handler:
                await handler(envelope)
            else:
                self.logger.warning("No handler found for recipient", 
                                  recipient_id=envelope.recipient_id)
                
        except Exception as e:
            self.logger.error("Message receive failed", error=str(e))
            # TODO: Send error response if possible


# Global message router instance
_message_router = MessageRouter()


def get_message_router() -> MessageRouter:
    """Get the global message router instance"""
    return _message_router


def register_message_handler(agent_id: str, handler_func):
    """Register a message handler for an agent"""
    _message_router.register_handler(agent_id, handler_func)


def unregister_message_handler(agent_id: str):
    """Unregister a message handler for an agent"""
    _message_router.unregister_handler(agent_id)