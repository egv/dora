"""Event-related data models."""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class EventSize(str, Enum):
    """Event size classification."""

    SMALL = "small"  # < 100 people
    MEDIUM = "medium"  # 100-1000 people
    LARGE = "large"  # 1000-10000 people
    HUGE = "huge"  # > 10000 people


class EventImportance(str, Enum):
    """Event importance classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AudienceDemographic(BaseModel):
    """Target audience demographic information."""

    gender: Optional[str] = None
    age_range: Optional[str] = None
    income_level: Optional[str] = None
    other_attributes: Optional[List[str]] = Field(default_factory=list)

    def __str__(self) -> str:
        """Return a readable string representation of the demographic."""
        parts = []
        
        if self.gender:
            parts.append(self.gender)
        
        if self.age_range:
            parts.append(f"{self.age_range}")
        
        if self.income_level:
            parts.append(f"{self.income_level} income")
        
        if self.other_attributes:
            parts.extend(self.other_attributes)
        
        return ", ".join(parts) if parts else "General audience"


class Event(BaseModel):
    """Event information model."""

    name: str
    description: str
    location: str
    city: str
    start_date: datetime
    end_date: Optional[datetime] = None
    url: Optional[str] = None


class ClassifiedEvent(BaseModel):
    """Event with classification information."""

    event: Event
    size: EventSize
    importance: EventImportance
    target_audiences: List[AudienceDemographic] = Field(default_factory=list, min_items=1, max_items=3)


class NotificationContent(BaseModel):
    """Push notification content for an event."""

    language: str
    audience: AudienceDemographic
    text: str


class EventNotification(BaseModel):
    """Complete notification package for an event."""

    event: ClassifiedEvent
    notifications: List[NotificationContent] = Field(default_factory=list)