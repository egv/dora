"""Database-compatible event model for data persistence layer."""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class Event(BaseModel):
    """Database-compatible event model matching the events table schema."""
    
    id: Optional[int] = None
    event_id: str = Field(..., description="External event identifier")
    name: str = Field(..., description="Event name")
    description: Optional[str] = Field(None, description="Event description")
    location: Optional[str] = Field(None, description="Event location")
    start_time: datetime = Field(..., description="Event start time")
    end_time: datetime = Field(..., description="Event end time")
    category: str = Field(default="general", description="Event category")
    attendance_estimate: Optional[int] = Field(default=0, description="Estimated attendance")
    source: str = Field(..., description="Data source")
    url: Optional[str] = Field(None, description="Event URL")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Update timestamp")
    
    def dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'event_id': self.event_id,
            'name': self.name,
            'description': self.description,
            'location': self.location,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'category': self.category,
            'attendance_estimate': self.attendance_estimate,
            'source': self.source,
            'url': self.url,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
    
    class Config:
        """Pydantic configuration."""
        from_attributes = True
        arbitrary_types_allowed = True