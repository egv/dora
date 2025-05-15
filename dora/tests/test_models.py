"""Tests for data models."""

import pytest
from datetime import datetime

from dora.models.event import (
    AudienceDemographic,
    ClassifiedEvent,
    Event,
    EventImportance,
    EventNotification,
    EventSize,
    NotificationContent,
)


def test_audience_demographic():
    """Test AudienceDemographic model."""
    # Test with minimal data
    audience = AudienceDemographic()
    assert str(audience) == "General audience"
    
    # Test with all fields
    audience = AudienceDemographic(
        gender="male",
        age_range="25-35",
        income_level="high",
        other_attributes=["tech enthusiasts", "early adopters"],
    )
    audience_str = str(audience)
    assert "male" in audience_str
    assert "25-35" in audience_str
    assert "high income" in audience_str
    assert "tech enthusiasts" in audience_str
    assert "early adopters" in audience_str


def test_event():
    """Test Event model."""
    event = Event(
        name="Tech Conference 2023",
        description="A conference about technology",
        location="Convention Center",
        city="San Francisco",
        start_date=datetime(2023, 9, 1, 9, 0),
        end_date=datetime(2023, 9, 3, 17, 0),
        url="https://example.com/tech-conf",
    )
    
    assert event.name == "Tech Conference 2023"
    assert event.city == "San Francisco"
    assert event.start_date.day == 1
    assert event.end_date.day == 3


def test_classified_event():
    """Test ClassifiedEvent model."""
    event = Event(
        name="Jazz Festival",
        description="Annual jazz music festival",
        location="City Park",
        city="New Orleans",
        start_date=datetime(2023, 7, 15, 18, 0),
    )
    
    audience = AudienceDemographic(
        gender="any",
        age_range="30-60",
        income_level="middle",
        other_attributes=["music lovers", "jazz enthusiasts"],
    )
    
    classified_event = ClassifiedEvent(
        event=event,
        size=EventSize.LARGE,
        importance=EventImportance.HIGH,
        target_audiences=[audience],
    )
    
    assert classified_event.event.name == "Jazz Festival"
    assert classified_event.size == EventSize.LARGE
    assert classified_event.importance == EventImportance.HIGH
    assert len(classified_event.target_audiences) == 1
    assert "jazz enthusiasts" in str(classified_event.target_audiences[0])


def test_notification_content():
    """Test NotificationContent model."""
    audience = AudienceDemographic(
        gender="female",
        age_range="20-35",
        income_level="middle",
        other_attributes=["fashion enthusiasts"],
    )
    
    notification = NotificationContent(
        language="English",
        audience=audience,
        text="Get 10% off your taxi to the Fashion Show tonight!",
    )
    
    assert notification.language == "English"
    assert notification.audience.gender == "female"
    assert "fashion enthusiasts" in notification.audience.other_attributes
    assert "10% off" in notification.text


def test_event_notification():
    """Test EventNotification model."""
    event = Event(
        name="Business Conference",
        description="Annual business conference",
        location="Business Center",
        city="New York",
        start_date=datetime(2023, 11, 10, 8, 0),
    )
    
    audience1 = AudienceDemographic(
        gender="any",
        age_range="30-50",
        income_level="high",
        other_attributes=["executives"],
    )
    
    audience2 = AudienceDemographic(
        gender="any",
        age_range="22-30",
        income_level="middle",
        other_attributes=["entrepreneurs", "startups"],
    )
    
    classified_event = ClassifiedEvent(
        event=event,
        size=EventSize.MEDIUM,
        importance=EventImportance.HIGH,
        target_audiences=[audience1, audience2],
    )
    
    notification1 = NotificationContent(
        language="English",
        audience=audience1,
        text="Executives: Save 10% on taxi to the Business Conference!",
    )
    
    notification2 = NotificationContent(
        language="English",
        audience=audience2,
        text="Startup founders: 10% off taxi to networking at Business Conference!",
    )
    
    event_notification = EventNotification(
        event=classified_event,
        notifications=[notification1, notification2],
    )
    
    assert event_notification.event.event.name == "Business Conference"
    assert len(event_notification.notifications) == 2
    assert "Executives" in event_notification.notifications[0].text
    assert "Startup" in event_notification.notifications[1].text