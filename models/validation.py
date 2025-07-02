"""
Message Validation System for A2A Communication

This module provides comprehensive validation for A2A messages including
JSON schema validation, payload validation, and security checks.
"""

import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import jsonschema
import structlog
from pydantic import ValidationError

from models.a2a import Capability
from models.jsonrpc import (
    A2AMessageEnvelope,
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCErrorResponse,
    JSONRPCNotification,
    JSONRPCError,
    JSONRPCErrorCode,
    A2AMethod,
)


logger = structlog.get_logger(__name__)


class ValidationResult:
    """Result of message validation"""
    
    def __init__(self, is_valid: bool = True, errors: Optional[List[str]] = None, 
                 warnings: Optional[List[str]] = None):
        self.is_valid = is_valid
        self.errors = errors or []
        self.warnings = warnings or []
    
    def add_error(self, error: str):
        """Add an error to the validation result"""
        self.errors.append(error)
        self.is_valid = False
    
    def add_warning(self, warning: str):
        """Add a warning to the validation result"""
        self.warnings.append(warning)
    
    def __bool__(self):
        """Return True if validation passed"""
        return self.is_valid
    
    def __str__(self):
        """String representation of validation result"""
        if self.is_valid:
            warnings_str = f" ({len(self.warnings)} warnings)" if self.warnings else ""
            return f"Valid{warnings_str}"
        else:
            return f"Invalid: {'; '.join(self.errors)}"


class MessageValidator:
    """
    Validates A2A messages for format compliance, security, and business rules.
    """
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__).bind(component="message_validator")
        
        # Known capabilities and their schemas
        self._capability_schemas: Dict[str, Capability] = {}
        
        # Security settings
        self.max_message_size = 10 * 1024 * 1024  # 10MB
        self.max_ttl = 3600  # 1 hour
        self.min_ttl = 1  # 1 second
        self.max_payload_depth = 10
        self.allowed_agent_id_pattern = re.compile(r'^[a-zA-Z0-9._-]+$')
        
        # Rate limiting tracking
        self._agent_message_counts: Dict[str, List[datetime]] = {}
        self.rate_limit_window = 60  # seconds
        self.rate_limit_max_messages = 1000  # per agent per minute
    
    def register_capability(self, capability: Capability):
        """
        Register a capability with its validation schema.
        
        Args:
            capability: Capability definition with input/output schemas
        """
        self._capability_schemas[capability.name] = capability
        self.logger.debug("Capability registered for validation", 
                         capability_name=capability.name)
    
    def unregister_capability(self, capability_name: str):
        """
        Unregister a capability.
        
        Args:
            capability_name: Name of capability to unregister
        """
        if capability_name in self._capability_schemas:
            del self._capability_schemas[capability_name]
            self.logger.debug("Capability unregistered from validation", 
                            capability_name=capability_name)
    
    def validate_envelope(self, envelope: A2AMessageEnvelope) -> ValidationResult:
        """
        Validate a complete message envelope.
        
        Args:
            envelope: Message envelope to validate
            
        Returns:
            ValidationResult indicating success/failure and any issues
        """
        result = ValidationResult()
        
        try:
            # Basic structure validation (already done by Pydantic, but double-check)
            self._validate_envelope_structure(envelope, result)
            
            # Security validation
            self._validate_security(envelope, result)
            
            # Business rules validation
            self._validate_business_rules(envelope, result)
            
            # JSON-RPC message validation
            self._validate_jsonrpc_message(envelope, result)
            
            # Capability-specific validation
            self._validate_capability_payload(envelope, result)
            
            # Rate limiting check
            self._validate_rate_limits(envelope, result)
            
        except Exception as e:
            result.add_error(f"Validation error: {str(e)}")
            self.logger.error("Message validation failed", 
                            envelope_id=envelope.envelope_id, 
                            error=str(e))
        
        return result
    
    def _validate_envelope_structure(self, envelope: A2AMessageEnvelope, result: ValidationResult):
        """Validate basic envelope structure"""
        
        # Check required fields
        if not envelope.sender_id:
            result.add_error("sender_id is required")
        
        if not envelope.recipient_id:
            result.add_error("recipient_id is required")
        
        if not envelope.jsonrpc_message:
            result.add_error("jsonrpc_message is required")
        
        # Validate agent ID format
        if envelope.sender_id and not self.allowed_agent_id_pattern.match(envelope.sender_id):
            result.add_error(f"Invalid sender_id format: {envelope.sender_id}")
        
        if envelope.recipient_id and not self.allowed_agent_id_pattern.match(envelope.recipient_id):
            result.add_error(f"Invalid recipient_id format: {envelope.recipient_id}")
        
        # Check timestamp is not too far in the past or future
        now = datetime.utcnow()
        if envelope.timestamp:
            time_diff = abs((now - envelope.timestamp).total_seconds())
            if time_diff > 300:  # 5 minutes tolerance
                result.add_warning(f"Message timestamp differs from current time by {time_diff:.1f} seconds")
    
    def _validate_security(self, envelope: A2AMessageEnvelope, result: ValidationResult):
        """Validate security aspects of the message"""
        
        # Check TTL bounds
        if envelope.ttl < self.min_ttl:
            result.add_error(f"TTL too small: {envelope.ttl} < {self.min_ttl}")
        
        if envelope.ttl > self.max_ttl:
            result.add_error(f"TTL too large: {envelope.ttl} > {self.max_ttl}")
        
        # Check priority bounds
        if not 1 <= envelope.priority <= 10:
            result.add_error(f"Priority out of range: {envelope.priority} (must be 1-10)")
        
        # Check for self-messaging (potential loop)
        if envelope.sender_id == envelope.recipient_id:
            result.add_warning("Agent sending message to itself")
        
        # Validate protocol version
        if envelope.protocol_version != "1.0":
            result.add_warning(f"Unsupported protocol version: {envelope.protocol_version}")
    
    def _validate_business_rules(self, envelope: A2AMessageEnvelope, result: ValidationResult):
        """Validate business logic rules"""
        
        # Check message age against TTL
        if envelope.timestamp:
            message_age = (datetime.utcnow() - envelope.timestamp).total_seconds()
            if message_age > envelope.ttl:
                result.add_error(f"Message expired: age {message_age:.1f}s > TTL {envelope.ttl}s")
        
        # Validate correlation_id format if present
        if envelope.correlation_id and not re.match(r'^[a-zA-Z0-9._-]+$', envelope.correlation_id):
            result.add_error(f"Invalid correlation_id format: {envelope.correlation_id}")
    
    def _validate_jsonrpc_message(self, envelope: A2AMessageEnvelope, result: ValidationResult):
        """Validate the JSON-RPC message content"""
        
        jsonrpc_msg = envelope.jsonrpc_message
        
        # Validate JSON-RPC version
        if hasattr(jsonrpc_msg, 'jsonrpc') and jsonrpc_msg.jsonrpc != "2.0":
            result.add_error(f"Invalid JSON-RPC version: {jsonrpc_msg.jsonrpc}")
        
        # Request-specific validation
        if isinstance(jsonrpc_msg, JSONRPCRequest):
            self._validate_jsonrpc_request(jsonrpc_msg, result)
        
        # Response-specific validation
        elif isinstance(jsonrpc_msg, JSONRPCResponse):
            self._validate_jsonrpc_response(jsonrpc_msg, result)
        
        # Error response validation
        elif isinstance(jsonrpc_msg, JSONRPCErrorResponse):
            self._validate_jsonrpc_error_response(jsonrpc_msg, result)
        
        # Notification validation
        elif isinstance(jsonrpc_msg, JSONRPCNotification):
            self._validate_jsonrpc_notification(jsonrpc_msg, result)
    
    def _validate_jsonrpc_request(self, request: JSONRPCRequest, result: ValidationResult):
        """Validate JSON-RPC request"""
        
        # Validate method name
        if not request.method:
            result.add_error("Request method is required")
        elif not isinstance(request.method, str):
            result.add_error("Request method must be a string")
        elif request.method.startswith('rpc.'):
            result.add_error("Method names starting with 'rpc.' are reserved")
        
        # Validate request ID
        if request.id is None:
            result.add_error("Request ID is required for requests")
        
        # Validate known A2A methods
        if request.method in A2AMethod.__members__.values():
            self._validate_a2a_method(request.method, request.params, result)
    
    def _validate_jsonrpc_response(self, response: JSONRPCResponse, result: ValidationResult):
        """Validate JSON-RPC response"""
        
        # Validate response ID
        if response.id is None:
            result.add_error("Response ID is required")
        
        # Result can be any JSON value, so no specific validation needed
    
    def _validate_jsonrpc_error_response(self, error_response: JSONRPCErrorResponse, result: ValidationResult):
        """Validate JSON-RPC error response"""
        
        # Validate error object
        error = error_response.error
        if not error:
            result.add_error("Error object is required in error response")
            return
        
        # Validate error code
        if error.code == 0:
            result.add_error("Error code cannot be 0")
        
        # Check if error code is in valid ranges
        valid_ranges = [
            (-32768, -32000),  # JSON-RPC reserved
            (-32099, -32000),  # Implementation defined
            (-32000, -1),      # Custom errors
            (1, 32767)         # Custom errors
        ]
        
        code_in_range = any(start <= error.code <= end for start, end in valid_ranges)
        if not code_in_range:
            result.add_warning(f"Error code {error.code} not in standard ranges")
        
        # Validate error message
        if not error.message or not isinstance(error.message, str):
            result.add_error("Error message must be a non-empty string")
    
    def _validate_jsonrpc_notification(self, notification: JSONRPCNotification, result: ValidationResult):
        """Validate JSON-RPC notification"""
        
        # Same method validation as requests
        if not notification.method:
            result.add_error("Notification method is required")
        elif not isinstance(notification.method, str):
            result.add_error("Notification method must be a string")
        elif notification.method.startswith('rpc.'):
            result.add_error("Method names starting with 'rpc.' are reserved")
    
    def _validate_a2a_method(self, method: str, params: Any, result: ValidationResult):
        """Validate A2A-specific method parameters"""
        
        if method == A2AMethod.EXECUTE_CAPABILITY:
            if not isinstance(params, dict):
                result.add_error("EXECUTE_CAPABILITY params must be an object")
                return
            
            if 'capability_name' not in params:
                result.add_error("capability_name is required for EXECUTE_CAPABILITY")
            
            if 'parameters' not in params:
                result.add_warning("parameters not specified for EXECUTE_CAPABILITY")
        
        elif method == A2AMethod.DISCOVER_AGENTS:
            if params is not None and not isinstance(params, dict):
                result.add_error("DISCOVER_AGENTS params must be an object or null")
        
        elif method == A2AMethod.HEARTBEAT:
            # Heartbeat typically has no parameters or minimal info
            pass
    
    def _validate_capability_payload(self, envelope: A2AMessageEnvelope, result: ValidationResult):
        """Validate capability-specific payload against registered schemas"""
        
        jsonrpc_msg = envelope.jsonrpc_message
        
        # Only validate capability execution requests
        if not isinstance(jsonrpc_msg, JSONRPCRequest):
            return
        
        if jsonrpc_msg.method != A2AMethod.EXECUTE_CAPABILITY:
            return
        
        params = jsonrpc_msg.params
        if not isinstance(params, dict):
            return
        
        capability_name = params.get('capability_name')
        if not capability_name:
            return
        
        # Check if we have schema for this capability
        capability = self._capability_schemas.get(capability_name)
        if not capability:
            result.add_warning(f"No validation schema registered for capability: {capability_name}")
            return
        
        # Validate input parameters against capability input schema
        capability_params = params.get('parameters', {})
        try:
            jsonschema.validate(capability_params, capability.input_schema)
        except jsonschema.ValidationError as e:
            result.add_error(f"Capability parameter validation failed: {e.message}")
        except jsonschema.SchemaError as e:
            result.add_error(f"Invalid capability input schema: {e.message}")
    
    def _validate_rate_limits(self, envelope: A2AMessageEnvelope, result: ValidationResult):
        """Validate rate limiting for sender"""
        
        sender_id = envelope.sender_id
        now = datetime.utcnow()
        
        # Clean old entries
        if sender_id in self._agent_message_counts:
            cutoff_time = now - timedelta(seconds=self.rate_limit_window)
            self._agent_message_counts[sender_id] = [
                timestamp for timestamp in self._agent_message_counts[sender_id]
                if timestamp > cutoff_time
            ]
        else:
            self._agent_message_counts[sender_id] = []
        
        # Add current message
        self._agent_message_counts[sender_id].append(now)
        
        # Check rate limit
        message_count = len(self._agent_message_counts[sender_id])
        if message_count > self.rate_limit_max_messages:
            result.add_error(f"Rate limit exceeded: {message_count} messages in {self.rate_limit_window}s")
    
    def validate_payload_depth(self, payload: Any, max_depth: int = None) -> bool:
        """
        Validate that payload doesn't exceed maximum nesting depth.
        
        Args:
            payload: Payload to check
            max_depth: Maximum allowed depth (uses instance default if None)
            
        Returns:
            True if payload depth is acceptable
        """
        if max_depth is None:
            max_depth = self.max_payload_depth
        
        def _check_depth(obj, current_depth):
            if current_depth > max_depth:
                return False
            
            if isinstance(obj, dict):
                return all(_check_depth(value, current_depth + 1) for value in obj.values())
            elif isinstance(obj, list):
                return all(_check_depth(item, current_depth + 1) for item in obj)
            else:
                return True
        
        return _check_depth(payload, 0)
    
    def validate_message_size(self, message_bytes: bytes) -> bool:
        """
        Validate message size is within limits.
        
        Args:
            message_bytes: Serialized message
            
        Returns:
            True if message size is acceptable
        """
        return len(message_bytes) <= self.max_message_size
    
    def get_validation_stats(self) -> Dict[str, Any]:
        """
        Get validation statistics.
        
        Returns:
            Dictionary containing validation statistics
        """
        return {
            "registered_capabilities": len(self._capability_schemas),
            "tracked_agents": len(self._agent_message_counts),
            "rate_limit_window": self.rate_limit_window,
            "rate_limit_max_messages": self.rate_limit_max_messages,
            "max_message_size": self.max_message_size,
            "max_ttl": self.max_ttl,
            "max_payload_depth": self.max_payload_depth,
        }


class CapabilityValidator:
    """
    Specialized validator for capability execution results.
    """
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__).bind(component="capability_validator")
    
    def validate_capability_result(self, capability: Capability, result: Any) -> ValidationResult:
        """
        Validate capability execution result against output schema.
        
        Args:
            capability: Capability definition with output schema
            result: Result to validate
            
        Returns:
            ValidationResult indicating success/failure
        """
        validation_result = ValidationResult()
        
        try:
            jsonschema.validate(result, capability.output_schema)
            self.logger.debug("Capability result validation passed", 
                            capability_name=capability.name)
        except jsonschema.ValidationError as e:
            validation_result.add_error(f"Result validation failed: {e.message}")
            self.logger.warning("Capability result validation failed",
                              capability_name=capability.name,
                              error=e.message)
        except jsonschema.SchemaError as e:
            validation_result.add_error(f"Invalid output schema: {e.message}")
            self.logger.error("Invalid capability output schema",
                            capability_name=capability.name,
                            error=e.message)
        
        return validation_result


# Global validator instances
_message_validator = MessageValidator()
_capability_validator = CapabilityValidator()


def get_message_validator() -> MessageValidator:
    """Get the global message validator instance"""
    return _message_validator


def get_capability_validator() -> CapabilityValidator:
    """Get the global capability validator instance"""
    return _capability_validator


def validate_message(envelope: A2AMessageEnvelope) -> ValidationResult:
    """Validate a message envelope using the global validator"""
    return _message_validator.validate_envelope(envelope)


def validate_capability_result(capability: Capability, result: Any) -> ValidationResult:
    """Validate capability result using the global validator"""
    return _capability_validator.validate_capability_result(capability, result)