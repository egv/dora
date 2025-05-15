"""Main entry point for Dora."""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List

from dora.agents.event_classifier import EventClassifierAgent
from dora.agents.event_finder import EventFinderAgent
from dora.agents.language_selector import LanguageSelectorAgent
from dora.agents.orchestrator import OrchestratorAgent
from dora.agents.text_writer import TextWriterAgent
from dora.models.config import DoraConfig
from dora.models.event import EventNotification
from dora.models.messages import ProcessCityRequest, ProcessCityResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)


def format_notification_for_display(notification: EventNotification) -> Dict:
    """Format a notification for display.
    
    Args:
        notification: The event notification to format
        
    Returns:
        A dictionary with formatted event notification data
    """
    event = notification.event.event
    
    # Format the date for display
    start_date = event.start_date.strftime("%Y-%m-%d %H:%M")
    end_date = event.end_date.strftime("%Y-%m-%d %H:%M") if event.end_date else None
    
    formatted_audiences = []
    
    for audience in notification.event.target_audiences:
        audience_str = str(audience)
        formatted_audiences.append(audience_str)
    
    formatted_notifications = []
    
    for notif in notification.notifications:
        formatted_notifications.append({
            "language": notif.language,
            "audience": str(notif.audience),
            "text": notif.text,
        })
    
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
            "size": notification.event.size.value,
            "importance": notification.event.importance.value,
            "target_audiences": formatted_audiences,
        },
        "notifications": formatted_notifications,
    }


def main():
    """Run the Dora application."""
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
        # Load configuration
        config = DoraConfig()
        
        if not config.openai_api_key:
            logger.error("OPENAI_API_KEY environment variable is required")
            sys.exit(1)
        
        # Initialize agents
        event_finder = EventFinderAgent(config)
        event_classifier = EventClassifierAgent(config)
        language_selector = LanguageSelectorAgent(config)
        text_writer = TextWriterAgent(config)
        
        orchestrator = OrchestratorAgent(
            config=config,
            event_finder=event_finder,
            event_classifier=event_classifier,
            language_selector=language_selector,
            text_writer=text_writer,
        )
        
        # Process the city
        logger.info(f"Processing city: {args.city}")
        
        request = ProcessCityRequest(city=args.city)
        response = orchestrator.process(request, ProcessCityResponse)
        
        if response.error:
            logger.error(f"Error processing city: {response.error}")
            sys.exit(1)
        
        if not response.event_notifications:
            logger.info(f"No events found in {args.city}")
            print(f"No events found in {args.city}")
            return
        
        # Format and display results
        formatted_results = []
        
        for notification in response.event_notifications:
            formatted_results.append(format_notification_for_display(notification))
        
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
        
        logger.info(f"Successfully processed {args.city} with {len(response.event_notifications)} events")
        
    except Exception as e:
        logger.exception(f"Error running Dora: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()