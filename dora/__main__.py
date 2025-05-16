"""Main entry point for Dora."""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

import agents
from agents import Agent, ModelSettings, Runner, trace
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

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

# Enable debug logging for agents library when tracing is enabled
if os.getenv("ENABLE_TRACING", "true").lower() == "true":
    logging.getLogger("agents").setLevel(logging.DEBUG)
    logging.getLogger("openai").setLevel(logging.DEBUG)

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
    # Import the internal function
    from dora.tools import perplexity_search
    
    # Create a Perplexity search tool with the API key bound
    from agents import function_tool
    
    @function_tool
    def search_events_perplexity(query: str) -> EventSearchResult:
        """Search for events using Perplexity API."""
        return perplexity_search(query, config.perplexity_api_key)
    
    instructions = f"""
    You are an event finder agent that discovers events in cities.
    
    When given a city name, find EXACTLY {events_count} events happening in the next two weeks.
    
    Use the search_events_perplexity tool with the query: "[city name] events next 2 weeks".
    
    From the search results, extract exactly {events_count} events with:
    1. Event name
    2. Description  
    3. Location (venue and address)
    4. Date (as YYYY-MM-DD format)
    5. URL (if available, or use "https://example.com" as default)
    
    Output exactly {events_count} events - no more, no less. Stop after {events_count} events.
    """
    
    return Agent(
        name="EventFinder",
        instructions=instructions,
        model=config.event_finder_config.model,
        model_settings=ModelSettings(temperature=config.event_finder_config.temperature),
        tools=[search_events_perplexity],
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
       Identify exactly 1 primary demographic group that would be most interested in this event.
       For the group, specify:
       - Gender: "any"
       - Age range (e.g., "18-35", "25-50")
       - Income level: "middle"
       - One relevant attribute (e.g., "music lovers" or "sports fans")
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
    
    When given a city name, identify ONLY THE TOP 1 most widely spoken language in that city.
    Return exactly 1 language - no more, no less.
    
    For New York, return: ["English"]
    For San Francisco, return: ["English"]
    For Los Angeles, return: ["English"]
    
    Use standard language names only.
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
    
    When given an event, target audience, and language:
    1. Generate a compelling push notification that promotes taking a taxi (with a 10% discount) to the event
    2. Make sure the notification is written in the specified language
    3. Keep the notification under 140 characters (like a tweet)
    4. Make it appealing specifically to the target audience
    5. Include a clear call-to-action
    6. Create urgency without being pushy
    """
    
    return Agent(
        name="TextWriter",
        instructions=instructions,
        model=config.text_writer_config.model,
        model_settings=ModelSettings(temperature=config.text_writer_config.temperature),
        output_type=NotificationsOutputSchema,
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
    
    Follow these steps:
    1. Use find_events to get {events_count} events in the specified city
    2. Use get_languages once to get the main language for the city
    3. For EACH event:
       - Classify it using classify_event
       - Generate a notification using generate_notification for the identified audience and language
    
    Your final output should include exactly {events_count} events, each with:
    - Event details
    - Classification (size, importance, 1 audience)
    - 1 notification (1 audience × 1 language)
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
    
    # Format dates
    start_date = event.start_date
    if isinstance(start_date, str):
        try:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00')).strftime("%Y-%m-%d %H:%M")
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


async def process_city(city: str, days_ahead: int = 14, events_count: int = 10, config: Optional[DoraConfig] = None):
    """Process a city to find events and generate notifications.
    
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
    
    # Set up OpenAI client
    agents.set_default_openai_key(config.openai_api_key)
    
    # Create context
    context = DoraContext(city)
    
    # Create agents
    event_finder = create_event_finder_agent(config, events_count)
    event_classifier = create_event_classifier_agent(config)
    language_selector = create_language_selector_agent(config)
    text_writer = create_text_writer_agent(config)
    orchestrator = create_orchestrator_agent(config, events_count)
    
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
    
    # Run the orchestrator with tracing
    prompt = f"Process events in {city} for the next {days_ahead} days."
    
    with trace(f"ProcessCity:{city}") as process_trace:
        process_trace.metadata = {"city": city, "days_ahead": str(days_ahead), "events_count": str(events_count)}
        
        logger.info(f"[TRACE] Starting orchestrator with prompt: {prompt}")
        runner_start_time = time.time()
        
        result = await Runner.run(
            orchestrator_with_tools, 
            prompt, 
            context=context
        )
        
        runner_duration = time.time() - runner_start_time
        logger.info(f"[TRACE] Orchestrator completed in {runner_duration:.2f} seconds")
        
        process_trace.metadata.update({
            "duration_seconds": f"{runner_duration:.2f}",
            "events_found": str(len(result.final_output.results) if result.final_output else 0)
        })
    
    return result.final_output.results


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
    
    # Register custom trace processor if debug logging is enabled
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
        
        # Format results for display
        formatted_results = [format_notification_for_display(result) for result in results]
        
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


def main():
    """Run the Dora application."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()