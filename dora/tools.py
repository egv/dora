"""Tools for Dora agents."""

import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx
from agents import function_tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EventSearchResult(BaseModel):
    """Result from event search."""
    content: str = Field(description="Search result content")
    error: Optional[str] = None


def perplexity_search(query: str, api_key: str, max_retries: int = 3, initial_delay: float = 1.0) -> EventSearchResult:
    """Search using Perplexity API with retry logic.
    
    Args:
        query: Search query
        api_key: Perplexity API key
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay between retries in seconds (default: 1.0)
    
    Returns:
        EventSearchResult with content or error
    """
    if not api_key:
        return EventSearchResult(content="", error="Perplexity API key is not configured")
    
    start_time = time.time()
    logger.info(f"[PERPLEXITY] Starting search query: {query}")
    
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    
    data = {
        "model": "sonar",
        "messages": [
            {"role": "system", "content": "You are a comprehensive event finder. Your job is to find exactly 10 UPCOMING events happening in the specified location. IMPORTANT: Only include events with SPECIFIC street addresses and EXACT dates. STRICTLY EXCLUDE ALL PAST EVENTS - only include events happening today or in the future. Do NOT include generic listings like 'various Broadway shows' or 'ongoing exhibitions'. Each event must have: 1) A specific name, 2) An exact date that is in the future, 3) A complete street address. Include concerts, sports, theater, festivals, exhibitions, conferences, comedy shows, food events, and more. List exactly 10 different events. Do not summarize - list each event separately. LANGUAGE REQUIREMENT: Provide all event information (names, descriptions, addresses) in the same language as the city name in the query."},
            {"role": "user", "content": query + " Please provide exactly 10 different UPCOMING events happening in the next 2 weeks with SPECIFIC addresses and EXACT dates. IMPORTANT: ONLY include events happening today or in the future - EXCLUDE ALL PAST EVENTS. Do NOT include generic listings like 'various shows' or events with vague dates like 'Thursdays' or 'ongoing'. Each event must be a specific occurrence with: 1) Event name, 2) Exact date in the future (e.g., May 20, 2025), 3) Complete venue address (e.g., 123 Main St, City). Include various types: concerts, sports, theater, comedy, festivals, museums, conferences, food/wine events, etc. Before providing the final list, verify that all events have future dates. RESPOND IN THE SAME LANGUAGE AS THE CITY NAME PROVIDED."},
        ],
        "temperature": 0.5,
        "max_tokens": 4000,
    }
    
    last_error = None
    delay = initial_delay
    
    for attempt in range(max_retries):
        try:
            logger.info(f"[PERPLEXITY] Attempt {attempt + 1}/{max_retries} - Sending request to API...")
            
            # Synchronous request since function_tool doesn't support async
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, headers=headers, json=data)
                
                # Check for rate limiting
                if response.status_code == 429:
                    retry_after = response.headers.get('Retry-After', str(int(delay)))
                    wait_time = float(retry_after)
                    logger.warning(f"[PERPLEXITY] Rate limited. Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    delay *= 2  # Exponential backoff
                    continue
                
                # Check for server errors that might be temporary
                if response.status_code >= 500:
                    logger.warning(f"[PERPLEXITY] Server error {response.status_code}. Retrying...")
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        delay *= 2  # Exponential backoff
                        continue
                
                response.raise_for_status()
                result = response.json()
                
                # Validate response structure
                if not result.get("choices") or not result["choices"][0].get("message"):
                    raise ValueError("Invalid response structure from Perplexity API")
                
                content = result["choices"][0]["message"].get("content", "")
                
                if not content:
                    raise ValueError("Empty content received from Perplexity API")
                
                duration = time.time() - start_time
                logger.info(f"[PERPLEXITY] Completed search in {duration:.2f} seconds, received {len(content)} characters")
                return EventSearchResult(content=content)
                
        except httpx.TimeoutException as e:
            last_error = e
            logger.warning(f"[PERPLEXITY] Timeout on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2
                
        except httpx.HTTPStatusError as e:
            last_error = e
            logger.warning(f"[PERPLEXITY] HTTP error on attempt {attempt + 1}: {e}")
            # Don't retry on client errors (4xx) except rate limiting
            if e.response.status_code < 500 and e.response.status_code != 429:
                break
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2
                
        except Exception as e:
            last_error = e
            logger.exception(f"[PERPLEXITY] Unexpected error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2
    
    # All retries exhausted
    duration = time.time() - start_time
    error_msg = f"Perplexity API error after {max_retries} attempts: {str(last_error)}"
    logger.error(f"[PERPLEXITY] {error_msg} (total time: {duration:.2f}s)")
    return EventSearchResult(content="", error=error_msg)


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