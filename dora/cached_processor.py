"""Cached event processor for Dora."""

import asyncio
import json
import time
import logging
from typing import Dict, List, Optional, Any

from agents import Agent, Runner, trace
from pydantic import BaseModel, Field

from dora.memory_cache import MemoryCache
from dora.models.config import DoraConfig
from dora.tools import (
    EventData,
    EventClassification,
    NotificationData,
)

logger = logging.getLogger(__name__)


class CachedResult(BaseModel):
    """Cached event result."""
    event: EventData
    classification: EventClassification
    notifications: List[NotificationData]
    from_cache: bool = False
    cache_hit_count: int = 0


async def process_events_with_cache(
    events: List[EventData],
    city: str,
    days_ahead: int,
    config: DoraConfig,
    event_classifier: Agent,
    language_selector: Agent,
    text_writer: Agent,
) -> List[CachedResult]:
    """Process events with caching support.
    
    Args:
        events: List of events to process
        city: City name for language selection
        days_ahead: Days ahead for context
        config: Application configuration
        event_classifier: Event classifier agent
        language_selector: Language selector agent
        text_writer: Text writer agent
        
    Returns:
        List of processed results with cache information
    """
    # Initialize memory cache
    cache = MemoryCache(config)
    
    # Get languages for the city
    language_result = await Runner.run(
        language_selector,
        city
    )
    languages = language_result.final_output.languages if language_result.final_output else ["en"]
    
    results = []
    
    for event in events:
        start_time = time.time()
        
        # Convert event to dict for cache lookup
        event_dict = event.model_dump()
        
        # Check cache first
        cached_data = cache.get_event(event_dict)
        
        if cached_data:
            # Use cached data
            logger.info(f"Cache hit for event: {event.name}")
            result = CachedResult(
                event=event,
                classification=EventClassification(**cached_data["classification"]),
                notifications=[NotificationData(**n) for n in cached_data["notifications"]],
                from_cache=True,
                cache_hit_count=cached_data["hit_count"]
            )
            results.append(result)
            continue
        
        # Process event if not in cache
        logger.info(f"Processing event: {event.name}")
        
        # Classify the event
        classification_result = await Runner.run(
            event_classifier,
            json.dumps(event_dict)
        )
        classification = classification_result.final_output.classification
        
        # Generate notifications for each language and audience
        notifications = []
        
        for language in languages:
            for audience in classification.target_audiences:
                notification_input = {
                    "event": event_dict,
                    "audience": {
                        "demographic": audience.model_dump() if hasattr(audience, 'model_dump') else audience,
                        "interests": [],
                        "tech_savvy": True,
                        "local": True
                    },
                    "language": language,
                    "context": {
                        "group_id": "general",
                        "season": "winter",
                        "time_of_day": "evening"
                    }
                }
                
                notification_result = await Runner.run(
                    text_writer,
                    json.dumps(notification_input)
                )
                
                if notification_result.final_output and notification_result.final_output.notifications:
                    for notif in notification_result.final_output.notifications:
                        # Add language and group info to notification
                        notif_dict = notif.model_dump()
                        notif_dict["language"] = language
                        notif_dict["context"]["group_id"] = "general"
                        notifications.append(NotificationData(**notif_dict))
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        # Store in cache
        cache.store_event(
            event_data=event_dict,
            classification=classification.model_dump(),
            notifications=[n.model_dump() for n in notifications],
            processing_time_ms=processing_time_ms
        )
        
        result = CachedResult(
            event=event,
            classification=classification,
            notifications=notifications,
            from_cache=False,
            cache_hit_count=0
        )
        results.append(result)
    
    # Log cache statistics
    stats = cache.get_cache_stats()
    if stats:
        logger.info(
            f"Cache stats: {stats['total_entries']} entries, "
            f"{stats['hit_rate']:.1f}% hit rate, "
            f"{stats['database_size_mb']:.2f}MB"
        )
    
    return results