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
                {"role": "system", "content": "You are a comprehensive event finder. Your job is to find exactly 10 events happening in the specified location. Include concerts, sports, theater, festivals, exhibitions, conferences, comedy shows, food events, and more. List exactly 10 different events with their dates, locations, and URLs. Do not summarize - list each event separately."},
                {"role": "user", "content": query + " Please provide exactly 10 different events happening in the next 2 weeks. Include various types: concerts, sports, theater, comedy, festivals, museums, conferences, food/wine events, etc. Make sure to list exactly 10 events, no more and no less."},
            ],
            "temperature": 0.7,
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