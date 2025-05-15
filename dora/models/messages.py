"""Message models for communication between agents."""

from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field

from dora.models.event import (
    AudienceDemographic,
    ClassifiedEvent,
    Event,
    EventNotification,
    NotificationContent,
)


class FindEventsRequest(BaseModel):
    """Request to find events in a city."""

    city: str
    days_ahead: int = 14  # Default to looking 2 weeks ahead


class FindEventsResponse(BaseModel):
    """Response with events found in a city."""

    city: str
    events: List[Event] = Field(default_factory=list)
    error: Optional[str] = None


class ClassifyEventRequest(BaseModel):
    """Request to classify an event."""

    event: Event


class ClassifyEventResponse(BaseModel):
    """Response with classified event information."""

    classified_event: ClassifiedEvent
    error: Optional[str] = None


class GetCityLanguagesRequest(BaseModel):
    """Request to get languages spoken in a city."""

    city: str


class GetCityLanguagesResponse(BaseModel):
    """Response with languages spoken in a city."""

    city: str
    languages: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class GenerateNotificationRequest(BaseModel):
    """Request to generate a notification for an event."""

    event: ClassifiedEvent
    audience: AudienceDemographic
    language: str


class GenerateNotificationResponse(BaseModel):
    """Response with generated notification."""

    notification: NotificationContent
    error: Optional[str] = None


class ProcessCityRequest(BaseModel):
    """Request to process a city."""

    city: str


class ProcessCityResponse(BaseModel):
    """Response with all processed events for a city."""

    city: str
    event_notifications: List[EventNotification] = Field(default_factory=list)
    error: Optional[str] = None


# Define a union type for all possible messages
AgentMessage = Union[
    FindEventsRequest,
    FindEventsResponse,
    ClassifyEventRequest,
    ClassifyEventResponse,
    GetCityLanguagesRequest,
    GetCityLanguagesResponse,
    GenerateNotificationRequest,
    GenerateNotificationResponse,
    ProcessCityRequest,
    ProcessCityResponse,
]