"""Tools for Dora agents."""

import json
import logging
from typing import Any, Dict, List, Optional

import httpx
from agents import function_tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EventSearchResult(BaseModel):
    """Result from event search."""
    content: str = Field(description="Search result content")
    error: Optional[str] = None


def perplexity_search(query: str, api_key: str) -> EventSearchResult:
    """Search using Perplexity API - internal function."""
    if not api_key:
        return EventSearchResult(content="", error="Perplexity API key is not configured")
    
    import time
    start_time = time.time()
    logger.info(f"[PERPLEXITY] Starting search query: {query}")
    
    try:
        url = "https://api.perplexity.ai/chat/completions"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        
        data = {
            "model": "sonar",
            "messages": [
                {"role": "system", "content": "You are a comprehensive event finder. Your job is to find exactly 10 UPCOMING events happening in the specified location. IMPORTANT: Only include events with SPECIFIC street addresses and EXACT dates. STRICTLY EXCLUDE ALL PAST EVENTS - only include events happening today or in the future. Do NOT include generic listings like 'various Broadway shows' or 'ongoing exhibitions'. Each event must have: 1) A specific name, 2) An exact date that is in the future, 3) A complete street address. Include concerts, sports, theater, festivals, exhibitions, conferences, comedy shows, food events, and more. List exactly 10 different events. Do not summarize - list each event separately."},
                {"role": "user", "content": query + " Please provide exactly 10 different UPCOMING events happening in the next 2 weeks with SPECIFIC addresses and EXACT dates. IMPORTANT: ONLY include events happening today or in the future - EXCLUDE ALL PAST EVENTS. Do NOT include generic listings like 'various shows' or events with vague dates like 'Thursdays' or 'ongoing'. Each event must be a specific occurrence with: 1) Event name, 2) Exact date in the future (e.g., May 20, 2025), 3) Complete venue address (e.g., 123 Main St, City). Include various types: concerts, sports, theater, comedy, festivals, museums, conferences, food/wine events, etc. Before providing the final list, verify that all events have future dates."},
            ],
            "temperature": 0.5,
            "max_tokens": 4000,
        }
        
        # Synchronous request since function_tool doesn't support async
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            duration = time.time() - start_time
            logger.info(f"[PERPLEXITY] Completed search in {duration:.2f} seconds")
            return EventSearchResult(content=content)
            
    except Exception as e:
        duration = time.time() - start_time
        logger.exception(f"[PERPLEXITY] Error after {duration:.2f} seconds: {e}")
        return EventSearchResult(content="", error=f"Perplexity API error: {str(e)}")


class EventData(BaseModel):
    """Event data for tool use."""
    name: str = Field(description="Event name")
    description: str = Field(description="Event description")
    location: str = Field(description="Event location")
    start_date: str = Field(description="Event start date")
    end_date: Optional[str] = Field(default=None, description="Event end date")
    url: Optional[str] = Field(default=None, description="Event URL")


class AudienceData(BaseModel):
    """Target audience data."""
    gender: Optional[str] = Field(default=None, description="Gender")
    age_range: Optional[str] = Field(default=None, description="Age range")
    income_level: Optional[str] = Field(default=None, description="Income level")
    other_attributes: List[str] = Field(default_factory=list, description="Other attributes")


class EventClassification(BaseModel):
    """Event classification data."""
    size: str = Field(description="Event size category")
    importance: str = Field(description="Event importance level")
    target_audiences: List[AudienceData] = Field(description="Target audience demographics")


class LanguageList(BaseModel):
    """List of languages for a city."""
    languages: List[str] = Field(description="Languages spoken in the city")


class NotificationData(BaseModel):
    """Notification data."""
    language: str = Field(description="Notification language")
    audience: AudienceData = Field(description="Target audience")
    text: str = Field(description="Notification text")


class NotificationList(BaseModel):
    """List of notifications."""
    notifications: List[NotificationData] = Field(description="Generated notifications")