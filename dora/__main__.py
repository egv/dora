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
from agents import Agent, FunctionTool, ModelSettings, Runner
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from dora.models.config import DoraConfig
from dora.models.event import (
    AudienceDemographic,
    ClassifiedEvent,
    Event,
    EventImportance,
    EventNotification,
    EventSize,
    NotificationContent,
)
from dora.tools import perplexity_search_tool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

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
    
    events: List[Dict] = Field(description="List of events found in the city")


class ClassificationOutputSchema(BaseModel):
    """Schema for event classification output."""
    
    classification: Dict = Field(description="Classification of the event")


class LanguagesOutputSchema(BaseModel):
    """Schema for languages output."""
    
    languages: List[str] = Field(description="Languages spoken in the city")


class NotificationsOutputSchema(BaseModel):
    """Schema for notifications output."""
    
    notifications: List[Dict] = Field(description="Generated notifications for the event")


class FinalOutputSchema(BaseModel):
    """Schema for final output."""
    
    results: List[Dict] = Field(description="Final processed results with events and notifications")


def create_event_finder_agent(config: DoraConfig) -> Agent:
    """Create an event finder agent.
    
    Args:
        config: Application configuration
        
    Returns:
        Event finder agent
    """
    # Create Perplexity search tool
    search_tool = perplexity_search_tool(config.perplexity_api_key)
    
    instructions = """
    You are an event finder agent that discovers events in cities.
    
    When given a city name, search for major events, concerts, festivals, sports events, and cultural events 
    taking place in the next two weeks.
    
    For each event, provide:
    1. Event name
    2. Description
    3. Location
    4. Date and time (start and end if available)
    5. URL for more information if available
    
    Use the search_perplexity tool to find information.
    """
    
    return Agent(
        name="EventFinder",
        instructions=instructions,
        model=config.event_finder_config.model,
        model_settings=ModelSettings(temperature=config.event_finder_config.temperature),
        tools=[search_tool],
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
       Identify exactly 3 primary demographic groups that would be most interested in this event.
       For each group, specify:
       - Gender (if relevant, or "any")
       - Age range (e.g., "18-25", "30-45")
       - Income level (low, middle, high)
       - Any other relevant attributes (e.g., "music enthusiasts", "sports fans", "art lovers")
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
    
    When given a city name, identify:
    1. The top 3 most widely spoken languages in that city, in order of prevalence
    2. Include both official languages and those spoken by significant portions of the population
    3. Include languages commonly used in business or tourism
    
    Use standard language names (English, Spanish, Mandarin, etc.) and ensure the list has at least 1 and at most 3 languages.
    If there is only one main language, just include that one.
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


def create_orchestrator_agent(config: DoraConfig) -> Agent:
    """Create an orchestrator agent.
    
    Args:
        config: Application configuration
        
    Returns:
        Orchestrator agent
    """
    instructions = """
    You are an orchestration agent that coordinates the process of discovering events in cities, 
    classifying them, finding languages spoken in the city, and generating targeted push notifications.
    
    Your goal is to:
    1. Find events in the specified city
    2. Classify each event by size, importance, and target audiences
    3. Determine languages commonly spoken in the city
    4. Generate personalized push notifications for each event, audience, and language combination
    
    Return the complete results with all events and their notifications.
    """
    
    return Agent(
        name="Orchestrator",
        instructions=instructions,
        model=config.orchestrator_config.model,
        model_settings=ModelSettings(temperature=config.orchestrator_config.temperature),
        output_type=FinalOutputSchema,
    )


def format_notification_for_display(notification: Dict) -> Dict:
    """Format a notification for display.
    
    Args:
        notification: The event notification to format
        
    Returns:
        A dictionary with formatted event notification data
    """
    event = notification.get("event", {})
    classification = notification.get("classification", {})
    notifications = notification.get("notifications", [])
    
    # Format dates
    start_date = event.get("start_date", "")
    if isinstance(start_date, str):
        try:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00')).strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            pass
    
    end_date = event.get("end_date", "")
    if isinstance(end_date, str) and end_date:
        try:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00')).strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            end_date = None
    else:
        end_date = None
    
    return {
        "event": {
            "name": event.get("name", "Unknown Event"),
            "description": event.get("description", ""),
            "location": event.get("location", ""),
            "start_date": start_date,
            "end_date": end_date,
            "url": event.get("url"),
        },
        "classification": {
            "size": classification.get("size", "medium"),
            "importance": classification.get("importance", "medium"),
            "target_audiences": classification.get("target_audiences", []),
        },
        "notifications": notifications,
    }


def create_venv_if_needed():
    """Create a virtual environment if it doesn't exist."""
    if not os.path.exists(".venv"):
        logger.info("Creating virtual environment...")
        os.system("uv venv")


async def process_city(city: str, days_ahead: int = 14, config: Optional[DoraConfig] = None):
    """Process a city to find events and generate notifications.
    
    Args:
        city: The city to process
        days_ahead: Number of days ahead to search for events
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
    event_finder = create_event_finder_agent(config)
    event_classifier = create_event_classifier_agent(config)
    language_selector = create_language_selector_agent(config)
    text_writer = create_text_writer_agent(config)
    orchestrator = create_orchestrator_agent(config)
    
    # Create function tools for the orchestrator
    async def find_events_tool(city: str) -> str:
        """Find events in a city.
        
        Args:
            city: The city to search
            
        Returns:
            JSON string with found events
        """
        prompt = f"Find events in {city} for the next {days_ahead} days."
        result = await Runner.run(event_finder, prompt, context=context)
        return json.dumps(result.output.events)
    
    async def classify_event_tool(event_json: str) -> str:
        """Classify an event.
        
        Args:
            event_json: JSON string representing an event
            
        Returns:
            JSON string with classification
        """
        result = await Runner.run(event_classifier, f"Classify this event: {event_json}", context=context)
        return json.dumps(result.output.classification)
    
    async def get_languages_tool(city: str) -> str:
        """Get languages spoken in a city.
        
        Args:
            city: The city to get languages for
            
        Returns:
            JSON string with languages
        """
        result = await Runner.run(language_selector, f"What languages are spoken in {city}?", context=context)
        return json.dumps(result.output.languages)
    
    async def generate_notification_tool(event_json: str, audience_json: str, language: str) -> str:
        """Generate a notification for an event.
        
        Args:
            event_json: JSON string with event data
            audience_json: JSON string with audience data
            language: Language to generate the notification in
            
        Returns:
            JSON string with notification
        """
        prompt = f"""
        Generate a push notification for this event: {event_json}
        Target audience: {audience_json}
        Language: {language}
        """
        result = await Runner.run(text_writer, prompt, context=context)
        return json.dumps(result.output.notifications)
    
    # Create tool definitions
    tools = [
        FunctionTool(
            name="find_events",
            description="Find events in a city",
            function=find_events_tool,
            args_schema={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "The city to search for events"}
                },
                "required": ["city"]
            }
        ),
        FunctionTool(
            name="classify_event",
            description="Classify an event by size, importance, and target audiences",
            function=classify_event_tool,
            args_schema={
                "type": "object",
                "properties": {
                    "event_json": {"type": "string", "description": "JSON string with event data"}
                },
                "required": ["event_json"]
            }
        ),
        FunctionTool(
            name="get_languages",
            description="Get languages spoken in a city",
            function=get_languages_tool,
            args_schema={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "The city to get languages for"}
                },
                "required": ["city"]
            }
        ),
        FunctionTool(
            name="generate_notification",
            description="Generate a notification for an event",
            function=generate_notification_tool,
            args_schema={
                "type": "object",
                "properties": {
                    "event_json": {"type": "string", "description": "JSON string with event data"},
                    "audience_json": {"type": "string", "description": "JSON string with audience data"},
                    "language": {"type": "string", "description": "Language to generate the notification in"}
                },
                "required": ["event_json", "audience_json", "language"]
            }
        ),
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
    
    # Run the orchestrator
    prompt = f"Process events in {city} for the next {days_ahead} days."
    result = await Runner.run(orchestrator_with_tools, prompt, context=context)
    
    return result.output.results


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
    
    args = parser.parse_args()
    
    try:
        # Create virtual environment if needed
        create_venv_if_needed()
        
        # Load configuration
        config = DoraConfig()
        
        if not config.openai_api_key:
            logger.error("OPENAI_API_KEY environment variable is required")
            sys.exit(1)
        
        # Process the city
        logger.info(f"Processing city: {args.city}")
        results = await process_city(args.city, args.days, config)
        
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