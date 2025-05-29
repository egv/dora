"""Main entry point for Dora."""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

from agents import Agent, ModelSettings, Runner, trace, function_tool, set_default_openai_key, WebSearchTool
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
import time

from dora.models.config import DoraConfig
from dora.trace_processor import DebugTraceProcessor
from dora.models.event import (
    AudienceDemographic,
    ClassifiedEvent,
    Event,
    EventImportance,
    EventNotification,
    EventSize,
    NotificationContent,
)
from dora.tools import (
    EventSearchResult,
    EventData,
    EventClassification,
    LanguageList,
    NotificationData,
    AudienceData,
)
from dora.memory_cache import MemoryCache

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

# Reduce verbosity for third-party libraries to avoid request body logging
logging.getLogger("openai_agents").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class DoraContext:
    """Context for Dora agents."""
    
    def __init__(self, city: str):
        """Initialize context.
        
        Args:
            city: The city to process
        """
        self.city = city
        self.events: List[Event] = []
        self.classified_events: List[ClassifiedEvent] = []
        self.languages: List[str] = []
        self.notifications: List[EventNotification] = []


class EventsOutputSchema(BaseModel):
    """Schema for events output."""
    
    events: List[EventData] = Field(description="List of events found in the city")


class ClassificationOutputSchema(BaseModel):
    """Schema for event classification output."""
    
    classification: EventClassification = Field(description="Classification of the event")


class LanguagesOutputSchema(BaseModel):
    """Schema for languages output."""
    
    languages: List[str] = Field(description="Languages spoken in the city")


class NotificationsOutputSchema(BaseModel):
    """Schema for notifications output."""
    
    notifications: List[NotificationData] = Field(description="Generated notifications for the event")


class BatchNotificationData(BaseModel):
    """Batch notification data for multiple events."""
    event_name: str = Field(description="Event name this notification is for")
    audience: AudienceData = Field(description="Target audience") 
    language: str = Field(description="Notification language")
    text: str = Field(description="Notification text")


class BatchNotificationsOutputSchema(BaseModel):
    """Schema for batch notifications output."""
    
    notifications: List[BatchNotificationData] = Field(description="Generated notifications for multiple events")


class FinalResult(BaseModel):
    """A single result with event and its notifications."""
    event: EventData = Field(description="Event information")
    classification: EventClassification = Field(description="Event classification")
    notifications: List[NotificationData] = Field(description="Event notifications")


class FinalOutputSchema(BaseModel):
    """Schema for final output."""
    
    results: List[FinalResult] = Field(description="Final processed results with events and notifications")


def create_event_finder_agent(config: DoraConfig, events_count: int = 10) -> Agent:
    """Create an event finder agent.
    
    Args:
        config: Application configuration
        events_count: Number of events to find
        
    Returns:
        Event finder agent
    """
    instructions = f"""
    You are an event finder agent that discovers events in cities.
    
    When given a city name, find EXACTLY {events_count} events happening in the next two weeks.
    
    Use the web search tool to search for: "[city name] upcoming events next 2 weeks concerts theater festivals sports" and similar queries.
    IMPORTANT: Search in the same language as the city name provided. If the city is "Paris", search in French. If "東京", search in Japanese.
    
    IMPORTANT REQUIREMENTS:
    - ONLY include events with SPECIFIC addresses (e.g., "123 Main St", "Golden Gate Park")
    - ONLY include events with SPECIFIC dates (e.g., "2025-05-20", not "various dates")
    - DO NOT include generic listings like "various shows", "multiple performances", or "ongoing exhibitions"
    - Each event must have a unique, specific occurrence with exact date and location
    - STRICTLY EXCLUDE all past events - ONLY include future events happening from today onwards
    - Check the date format and ensure all events have dates that are in the future
    
    From the search results, extract exactly {events_count} events with:
    1. Event name (specific event, not a generic listing)
    2. Description  
    3. Location (MUST include specific venue name AND street address)
    4. Date (MUST be exact date in YYYY-MM-DD format, not ranges or "various")
    5. URL (if available, or use "https://example.com" as default)
    
    Output exactly {events_count} events - no more, no less. Stop after {events_count} events.
    FINAL CHECK: Verify all event dates are in the future before returning results.
    """
    
    return Agent(
        name="EventFinder",
        instructions=instructions,
        model=config.event_finder_config.model,
        model_settings=ModelSettings(temperature=config.event_finder_config.temperature),
        tools=[WebSearchTool()],
        output_type=EventsOutputSchema,
    )


def create_event_classifier_agent(config: DoraConfig) -> Agent:
    """Create an event classifier agent.
    
    Args:
        config: Application configuration
        
    Returns:
        Event classifier agent
    """
    instructions = """
    You are an event classifier agent that analyzes events by size, importance, and target audiences.
    
    For each event, classify:
    
    1. SIZE:
       - SMALL: less than 100 people
       - MEDIUM: 100-1000 people
       - LARGE: 1000-10000 people
       - HUGE: more than 10000 people
    
    2. IMPORTANCE:
       - LOW: Local event with minimal impact
       - MEDIUM: Notable local event or small regional event
       - HIGH: Major regional event or small national event
       - CRITICAL: Major national or international event
    
    3. TARGET AUDIENCES:
       Identify UP TO 3 different demographic groups that would be most interested in this event.
       For each group, specify:
       - Gender: "male", "female", or "any"
       - Age range (e.g., "18-35", "25-50")
       - Income level: "low", "middle", "high", or "any"
       - One or more relevant attributes (e.g., "music lovers", "sports fans", "families")
       
       Only include audiences that actually make sense for the event.
       For specialized events, you might have only 1-2 audiences.
       For general events (like festivals), you might have 3 different audiences.
    """
    
    return Agent(
        name="EventClassifier",
        instructions=instructions,
        model=config.event_classifier_config.model,
        model_settings=ModelSettings(temperature=config.event_classifier_config.temperature),
        output_type=ClassificationOutputSchema,
    )


def create_language_selector_agent(config: DoraConfig) -> Agent:
    """Create a language selector agent.
    
    Args:
        config: Application configuration
        
    Returns:
        Language selector agent
    """
    instructions = """
    You are a language selector agent that determines languages commonly spoken in cities.
    
    When given a city name, identify THE TOP 3 most widely spoken languages in that city.
    Return exactly 3 languages ordered by how commonly they are spoken (most common first).
    
    Examples:
    - For New York City, return: ["English", "Spanish", "Chinese"]
    - For San Francisco, return: ["English", "Chinese", "Spanish"]
    - For Los Angeles, return: ["English", "Spanish", "Korean"]
    - For Lusaka, return: ["English", "Bemba", "Tonga"]
    - For Tokyo, return: ["Japanese", "English", "Chinese"]
    - For Paris, return: ["French", "English", "Arabic"]
    - For Abidjan, return: ["French", "English", "Dioula"]
    
    Use standard language names only. Research the actual language demographics of the city.
    """
    
    return Agent(
        name="LanguageSelector",
        instructions=instructions,
        model=config.language_selector_config.model,
        model_settings=ModelSettings(temperature=config.language_selector_config.temperature),
        output_type=LanguagesOutputSchema,
    )


def create_text_writer_agent(config: DoraConfig) -> Agent:
    """Create a text writer agent.
    
    Args:
        config: Application configuration
        
    Returns:
        Text writer agent
    """
    instructions = """
    You are a text writer agent that creates engaging push notifications for events.
    
    BULK PROCESSING: You receive a structured array of events and generate notifications for all of them in a single call.
    
    Input format: An array containing multiple events with their audiences and languages.
    
    For EACH event-audience-language combination in the input array:
    1. Generate a compelling push notification that promotes taking a taxi (with a 10% discount)
    2. Write in the specified language for that item
    3. Keep under 140 characters (like a tweet)
    4. Make it appealing to the specific target audience
    5. Include a clear call-to-action
    6. Create urgency without being pushy
    
    Return an array of notifications matching the input array order.
    """
    
    return Agent(
        name="TextWriter",
        instructions=instructions,
        model=config.text_writer_config.model,
        model_settings=ModelSettings(temperature=config.text_writer_config.temperature),
        output_type=BatchNotificationsOutputSchema,
    )


def create_orchestrator_agent(config: DoraConfig, events_count: int = 10) -> Agent:
    """Create an orchestrator agent.
    
    Args:
        config: Application configuration
        events_count: Number of events to process
        
    Returns:
        Orchestrator agent
    """
    instructions = f"""
    You are an orchestration agent that coordinates the process of discovering events and generating notifications.
    
    CRITICAL: Make ONLY ONE call to generate_notification with ALL event-audience-language combinations.
    
    Follow these steps and ANNOUNCE each step clearly:
    1. STEP 1: Use find_events to get {events_count} events in the specified city
       - Say "Finding events in [city]..."
    2. STEP 2: Use get_languages once to get the top 3 languages for the city
       - Say "Getting languages for [city]..."
    3. STEP 3: For each event, classify it using classify_event
       - Say "Classifying event X of Y: [event name]..."
       - Select up to 2 primary audiences from the classification
    4. STEP 4: Create notification combinations
       - Say "Creating notification combinations for all events..."
       - Each item: {{event, audience, language}}
       - {events_count} events × 2 audiences × 3 languages = up to {events_count * 6} items
    5. STEP 5: Make ONE call to generate_notification with this complete array
       - Say "Generating all notifications..."
    
    Your final output should include exactly {events_count} events, each with:
    - Event details
    - Classification (size, importance, up to 3 audiences)
    - Notifications (up to 2 audiences × 3 languages = up to 6 notifications per event)
    
    REMEMBER: Only ONE call to generate_notification with ALL combinations at once!
    """
    
    return Agent(
        name="Orchestrator",
        instructions=instructions,
        model=config.orchestrator_config.model,
        model_settings=ModelSettings(temperature=config.orchestrator_config.temperature),
        output_type=FinalOutputSchema,
    )


def format_notification_for_display(notification: FinalResult) -> Dict:
    """Format a notification for display.
    
    Args:
        notification: The event notification to format
        
    Returns:
        A dictionary with formatted event notification data
    """
    event = notification.event
    classification = notification.classification
    notifications = notification.notifications
    
    # Format dates and check they are not in the past
    start_date = event.start_date
    current_date = datetime.now()
    is_future_event = True
    
    if isinstance(start_date, str):
        try:
            date_obj = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            # Check if the event is in the past (before today)
            is_future_event = date_obj.date() >= current_date.date()
            start_date = date_obj.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            pass
    
    end_date = event.end_date
    if isinstance(end_date, str) and end_date:
        try:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00')).strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            end_date = None
    else:
        end_date = None
    
    # Skip events with dates in the past
    if not is_future_event:
        logger.warning(f"Skipping past event: {event.name} with date {start_date}")
        return None
    
    return {
        "event": {
            "name": event.name,
            "description": event.description,
            "location": event.location,
            "start_date": start_date,
            "end_date": end_date,
            "url": event.url,
        },
        "classification": {
            "size": classification.size,
            "importance": classification.importance,
            "target_audiences": [str(audience) for audience in classification.target_audiences],
        },
        "notifications": [
            {
                "language": n.language,
                "audience": str(n.audience),
                "text": n.text
            }
            for n in notifications
        ],
    }


def create_venv_if_needed():
    """Create a virtual environment if it doesn't exist."""
    if not os.path.exists(".venv"):
        logger.info("Creating virtual environment...")
        os.system("uv venv")


async def process_city_original(city: str, days_ahead: int = 14, events_count: int = 10, config: Optional[DoraConfig] = None, progress_callback: Optional[callable] = None):
    """Process a city to find events and generate notifications.
    
    Args:
        city: The city to process
        days_ahead: Number of days ahead to search for events
        events_count: Number of events to find and process
        config: Application configuration
        progress_callback: Optional callback function for progress updates
        
    Returns:
        Processed results
    """
    if config is None:
        config = DoraConfig()
    
    # Progress reporting helper
    async def report_progress(step: str, details: str = ""):
        if progress_callback:
            await progress_callback(step, details)
        logger.info(f"[PROGRESS] {step}: {details}")
    
    await report_progress("INITIALIZING", "Setting up OpenAI client and agents")
    
    # Set up OpenAI client
    set_default_openai_key(config.openai_api_key)
    
    # Create context
    context = DoraContext(city)
    
    await report_progress("CREATING_AGENTS", f"Setting up {events_count} event processing pipeline")
    
    # Create agents
    event_finder = create_event_finder_agent(config, events_count)
    event_classifier = create_event_classifier_agent(config)
    language_selector = create_language_selector_agent(config)
    text_writer = create_text_writer_agent(config)
    orchestrator = create_orchestrator_agent(config, events_count)
    
    await report_progress("BUILDING_TOOLS", "Creating agent tools and orchestrator")
    
    # Create event finder tool using agent.as_tool()
    event_finder_tool = event_finder.as_tool(
        tool_name="find_events",
        tool_description=f"Find events in a city for the next {days_ahead} days. Provide the city name as input."
    )
    
    # Create event classifier tool using agent.as_tool()
    event_classifier_tool = event_classifier.as_tool(
        tool_name="classify_event",
        tool_description="Classify an event by size, importance, and target audiences. Provide event details as input."
    )
    
    # Create language selector tool using agent.as_tool()
    language_selector_tool = language_selector.as_tool(
        tool_name="get_languages",
        tool_description="Get languages commonly spoken in a city. Provide the city name as input."
    )
    
    # Create text writer tool using agent.as_tool()
    text_writer_tool = text_writer.as_tool(
        tool_name="generate_notification",
        tool_description="Generate a push notification for an event. Provide event details, target audience, and language."
    )
    
    # List of tools for the orchestrator
    tools = [
        event_finder_tool,
        event_classifier_tool,
        language_selector_tool,
        text_writer_tool,
    ]
    
    # Update orchestrator with tools
    orchestrator_with_tools = Agent(
        name="Orchestrator",
        instructions=orchestrator.instructions,
        model=orchestrator.model,
        model_settings=orchestrator.model_settings,
        tools=tools,
        output_type=orchestrator.output_type,
    )
    
    await report_progress("STARTING_SEARCH", f"Searching for {events_count} events in {city}")
    
    # Run the orchestrator with tracing
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"Process events in {city} for the next {days_ahead} days, starting from today ({today}). ONLY include events happening today or in the future."
    
    with trace(f"ProcessCity:{city}") as process_trace:
        process_trace.metadata = {"city": city, "days_ahead": str(days_ahead), "events_count": str(events_count)}
        
        logger.info(f"[TRACE] Starting orchestrator with prompt: {prompt}")
        runner_start_time = time.time()
        
        await report_progress("RUNNING_ORCHESTRATOR", "Executing event discovery and notification pipeline")
        
        result = await Runner.run(
            orchestrator_with_tools, 
            prompt, 
            context=context
        )
        
        runner_duration = time.time() - runner_start_time
        logger.info(f"[TRACE] Orchestrator completed in {runner_duration:.2f} seconds")
        
        await report_progress("PROCESSING_RESULTS", f"Found {len(result.final_output.results) if result.final_output else 0} events, filtering and formatting")
        
        process_trace.metadata.update({
            "duration_seconds": f"{runner_duration:.2f}",
            "events_found": str(len(result.final_output.results) if result.final_output else 0)
        })
    
    await report_progress("COMPLETED", f"Successfully processed {len(result.final_output.results) if result.final_output else 0} events")
    
    return result.final_output.results


async def process_city(city: str, days_ahead: int = 14, events_count: int = 10, config: Optional[DoraConfig] = None):
    """Process a city to find events and generate notifications with caching.
    
    Args:
        city: The city to process
        days_ahead: Number of days ahead to search for events
        events_count: Number of events to find and process
        config: Application configuration
        
    Returns:
        Processed results
    """
    if config is None:
        config = DoraConfig()
    
    # Initialize memory cache
    cache = MemoryCache(config)
    
    # Set up OpenAI client
    set_default_openai_key(config.openai_api_key)
    
    # Create agents
    event_finder = create_event_finder_agent(config, events_count)
    event_classifier = create_event_classifier_agent(config)
    language_selector = create_language_selector_agent(config)
    text_writer = create_text_writer_agent(config)
    
    # Track timing
    total_start_time = time.time()
    cache_hits = 0
    cache_misses = 0
    
    with trace(f"ProcessCity:{city}") as process_trace:
        process_trace.metadata = {"city": city, "days_ahead": str(days_ahead), "events_count": str(events_count)}
        
        # Step 1: Find events
        logger.info(f"Finding events in {city}")
        find_events_start = time.time()
        
        event_result = await Runner.run(
            event_finder,
            city
        )
        
        find_events_duration = time.time() - find_events_start
        events = event_result.final_output.events if event_result.final_output else []
        logger.info(f"Found {len(events)} events in {find_events_duration:.2f}s")
        
        # Step 2: Get languages for the city
        logger.info(f"Getting languages for {city}")
        lang_start = time.time()
        
        language_result = await Runner.run(
            language_selector,
            city
        )
        
        languages = language_result.final_output.languages if language_result.final_output else ["en"]
        lang_duration = time.time() - lang_start
        logger.info(f"Found languages {languages} in {lang_duration:.2f}s")
        
        # Step 3: Process each event with caching
        results = []
        
        for i, event in enumerate(events):
            logger.info(f"Processing event {i+1}/{len(events)}: {event.name}")
            event_start = time.time()
            
            # Convert event to dict for cache lookup
            event_dict = event.model_dump()
            
            # Check cache first
            cached_data = cache.get_event(event_dict)
            
            if cached_data:
                # Use cached data
                logger.info(f"Cache hit for event: {event.name}")
                cache_hits += 1
                
                result = FinalResult(
                    event=event,
                    classification=EventClassification(**cached_data["classification"]),
                    notifications=[NotificationData(**n) for n in cached_data["notifications"]]
                )
                results.append(result)
                process_trace.metadata[f"event_{i}_cached"] = "true"
                continue
            
            # Process event if not in cache
            cache_misses += 1
            
            # Classify the event
            logger.info(f"Classifying event: {event.name}")
            classify_start = time.time()
            
            classification_result = await Runner.run(
                event_classifier,
                json.dumps(event_dict)
            )
            classification = classification_result.final_output.classification
            classify_duration = time.time() - classify_start
            logger.info(f"Classified event in {classify_duration:.2f}s")
            
            # Generate notifications for each language and audience
            notifications = []
            notify_start = time.time()
            
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
                            if "context" not in notif_dict:
                                notif_dict["context"] = {}
                            notif_dict["context"]["group_id"] = "general"
                            notifications.append(NotificationData(**notif_dict))
            
            notify_duration = time.time() - notify_start
            logger.info(f"Generated {len(notifications)} notifications in {notify_duration:.2f}s")
            
            event_duration = time.time() - event_start
            processing_time_ms = int(event_duration * 1000)
            
            # Store in cache
            cache.store_event(
                event_data=event_dict,
                classification=classification.model_dump(),
                notifications=[n.model_dump() for n in notifications],
                processing_time_ms=processing_time_ms
            )
            
            result = FinalResult(
                event=event,
                classification=classification,
                notifications=notifications
            )
            results.append(result)
            
            process_trace.metadata[f"event_{i}_cached"] = "false"
            process_trace.metadata[f"event_{i}_processing_ms"] = str(processing_time_ms)
        
        # Update trace metadata
        total_duration = time.time() - total_start_time
        process_trace.metadata.update({
            "duration_seconds": f"{total_duration:.2f}",
            "events_found": str(len(events)),
            "cache_hits": str(cache_hits),
            "cache_misses": str(cache_misses),
            "cache_hit_rate": f"{(cache_hits / len(events) * 100) if events else 0:.1f}%"
        })
        
        # Log cache statistics
        stats = cache.get_cache_stats()
        if stats:
            logger.info(
                f"Cache stats: {stats['total_entries']} entries, "
                f"{stats['hit_rate']:.1f}% hit rate, "
                f"{stats['database_size_mb']:.2f}MB"
            )
    
    return results


async def main_async():
    """Run the Dora application asynchronously."""
    parser = argparse.ArgumentParser(description="Dora - Event discovery and notification agent")
    parser.add_argument("--city", required=True, help="City to search for events")
    parser.add_argument(
        "--output",
        choices=["json", "pretty"],
        default="pretty",
        help="Output format (json or pretty-printed)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=14,
        help="Number of days ahead to search for events (default: 14)",
    )
    parser.add_argument(
        "--events",
        type=int,
        default=10,
        help="Number of events to find and process (default: 10)",
    )
    
    args = parser.parse_args()
    
    # Add debug trace processor if debug logging is enabled
    if os.getenv("LOG_LEVEL", "INFO").upper() == "DEBUG":
        from agents.tracing import add_trace_processor
        debug_processor = DebugTraceProcessor()
        add_trace_processor(debug_processor)
    
    try:
        # Create virtual environment if needed
        create_venv_if_needed()
        
        # Load configuration
        config = DoraConfig()
        
        if not config.openai_api_key:
            logger.error("OPENAI_API_KEY environment variable is required")
            sys.exit(1)
            
        # Initialize OpenAI agents SDK with API key
        set_default_openai_key(config.openai_api_key)
        
        # Tracing is enabled by default in the agents SDK
        if os.getenv("ENABLE_TRACING", "true").lower() == "true":
            logger.info("Tracing is enabled - traces will be exported to OpenAI console")
        
        # Process the city with tracing
        logger.info(f"Processing city: {args.city} for {args.events} events")
        
        with trace("DoraApp") as app_trace:
            app_trace.metadata = {
                "city": args.city, 
                "days": str(args.days),
                "events": str(args.events),
                "output_format": args.output
            }
            
            start_time = time.time()
            results = await process_city(args.city, args.days, args.events, config)
            elapsed_time = time.time() - start_time
            
            app_trace.metadata.update({
                "duration_seconds": f"{elapsed_time:.2f}",
                "events_processed": str(len(results) if results else 0)
            })
            
            logger.info(f"Processing completed in {elapsed_time:.2f} seconds")
        
        if not results:
            logger.info(f"No events found in {args.city}")
            print(f"No events found in {args.city}")
            return
        
        # Format results for display and filter out None values (past events)
        formatted_results = [format_notification_for_display(result) for result in results]
        formatted_results = [result for result in formatted_results if result is not None]
        
        if not formatted_results:
            logger.info(f"No valid future events found in {args.city}")
            print(f"No valid future events found in {args.city}")
            return
        
        if args.output == "json":
            print(json.dumps(formatted_results, indent=2))
        else:
            # Pretty print the results
            for i, result in enumerate(formatted_results, 1):
                event = result["event"]
                classification = result["classification"]
                
                print(f"\n{'=' * 50}")
                print(f"EVENT {i}: {event['name']}")
                print(f"{'=' * 50}")
                print(f"Description: {event['description']}")
                print(f"Location: {event['location']}")
                
                # Extract venue and address if the location contains a comma
                location_parts = event['location'].split(',', 1)
                if len(location_parts) > 1:
                    venue = location_parts[0].strip()
                    address = location_parts[1].strip()
                    print(f"Venue: {venue}")
                    print(f"Address: {address}")
                
                print(f"Date: {event['start_date']}")
                if event['end_date']:
                    print(f"End Date: {event['end_date']}")
                if event['url']:
                    print(f"URL: {event['url']}")
                
                print(f"\nClassification:")
                print(f"  Size: {classification['size']}")
                print(f"  Importance: {classification['importance']}")
                
                print(f"\nTarget Audiences:")
                for audience in classification['target_audiences']:
                    print(f"  - {audience}")
                
                print(f"\nNotifications:")
                for notification in result["notifications"]:
                    print(f"\n  Language: {notification['language']}")
                    print(f"  Audience: {notification['audience']}")
                    print(f"  Text: \"{notification['text']}\"")
                
                print(f"\n{'-' * 50}")
        
        logger.info(f"Successfully processed {args.city} with {len(results)} events")
        
    except Exception as e:
        logger.exception(f"Error running Dora: {e}")
        sys.exit(1)
    finally:
        # The agents SDK handles trace export automatically
        pass


def main():
    """Run the Dora application."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()