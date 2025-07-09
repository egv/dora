"""
Business Logic Validation

This module provides validation for business logic operations.
Google's A2A SDK handles protocol-level validation, so this focuses
on application-specific validation needs.
"""

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog


logger = structlog.get_logger(__name__)


class ValidationResult:
    """Result of validation operations"""
    
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


class BusinessValidator:
    """Validates business logic operations"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__).bind(component="business_validator")
        
        # Business validation settings
        self.max_payload_depth = 10
        self.max_string_length = 10000
        self.allowed_id_pattern = re.compile(r'^[a-zA-Z0-9._-]+$')
    
    def validate_event_data(self, event_data: Dict[str, Any]) -> ValidationResult:
        """
        Validate event data for business logic compliance.
        
        Args:
            event_data: Event data to validate
            
        Returns:
            ValidationResult indicating success/failure
        """
        result = ValidationResult()
        
        try:
            # Check required fields
            required_fields = ['title', 'start_time', 'end_time', 'organizer']
            for field in required_fields:
                if field not in event_data or not event_data[field]:
                    result.add_error(f"Required field '{field}' is missing or empty")
            
            # Validate field formats
            if 'title' in event_data:
                if len(event_data['title']) > self.max_string_length:
                    result.add_error(f"Title too long: {len(event_data['title'])} > {self.max_string_length}")
            
            if 'organizer' in event_data:
                if not self._is_valid_email(event_data['organizer']):
                    result.add_error(f"Invalid organizer email format: {event_data['organizer']}")
            
            # Validate datetime fields
            if 'start_time' in event_data and 'end_time' in event_data:
                try:
                    start_time = datetime.fromisoformat(event_data['start_time'].replace('Z', '+00:00'))
                    end_time = datetime.fromisoformat(event_data['end_time'].replace('Z', '+00:00'))
                    
                    if end_time <= start_time:
                        result.add_error("End time must be after start time")
                    
                    # Check if event is not too far in the future
                    now = datetime.now(start_time.tzinfo) if start_time.tzinfo else datetime.utcnow()
                    if start_time > now + timedelta(days=365):
                        result.add_warning("Event scheduled more than a year in the future")
                        
                except ValueError as e:
                    result.add_error(f"Invalid datetime format: {str(e)}")
            
            # Validate attendees if present
            if 'attendees' in event_data:
                attendees = event_data['attendees']
                if isinstance(attendees, list):
                    for attendee in attendees:
                        if not self._is_valid_email(attendee):
                            result.add_error(f"Invalid attendee email format: {attendee}")
                else:
                    result.add_error("Attendees must be a list")
                    
        except Exception as e:
            result.add_error(f"Validation error: {str(e)}")
            self.logger.error("Event data validation failed", error=str(e))
        
        return result
    
    def validate_id_format(self, id_value: str, field_name: str = "ID") -> ValidationResult:
        """
        Validate ID format for business objects.
        
        Args:
            id_value: ID to validate
            field_name: Name of the field for error messages
            
        Returns:
            ValidationResult indicating success/failure
        """
        result = ValidationResult()
        
        if not id_value:
            result.add_error(f"{field_name} cannot be empty")
        elif not isinstance(id_value, str):
            result.add_error(f"{field_name} must be a string")
        elif not self.allowed_id_pattern.match(id_value):
            result.add_error(f"Invalid {field_name} format: must contain only letters, numbers, dots, underscores, and hyphens")
        elif len(id_value) > 255:
            result.add_error(f"{field_name} too long: {len(id_value)} > 255")
            
        return result
    
    def validate_payload_depth(self, payload: Any, max_depth: int = None) -> ValidationResult:
        """
        Validate that payload doesn't exceed maximum nesting depth.
        
        Args:
            payload: Payload to check
            max_depth: Maximum allowed depth (uses instance default if None)
            
        Returns:
            ValidationResult with depth validation results
        """
        result = ValidationResult()
        
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
        
        if not _check_depth(payload, 0):
            result.add_error(f"Payload nesting too deep: exceeds maximum depth of {max_depth}")
            
        return result
    
    def _is_valid_email(self, email: str) -> bool:
        """Simple email validation"""
        if not isinstance(email, str):
            return False
        email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        return bool(email_pattern.match(email))


# Global validator instance
_business_validator = BusinessValidator()


def get_business_validator() -> BusinessValidator:
    """Get the global business validator instance"""
    return _business_validator


def validate_event_data(event_data: Dict[str, Any]) -> ValidationResult:
    """Validate event data using the global validator"""
    return _business_validator.validate_event_data(event_data)


def validate_id_format(id_value: str, field_name: str = "ID") -> ValidationResult:
    """Validate ID format using the global validator"""
    return _business_validator.validate_id_format(id_value, field_name)