"""Orchestration agent implementation."""

import logging
from typing import Dict, List, Type

from dora.agents.base import BaseAgent
from dora.models.config import DoraConfig
from dora.models.event import EventNotification
from dora.models.messages import (
    ClassifyEventRequest,
    ClassifyEventResponse,
    FindEventsRequest,
    FindEventsResponse,
    GenerateNotificationRequest,
    GenerateNotificationResponse,
    GetCityLanguagesRequest,
    GetCityLanguagesResponse,
    ProcessCityRequest,
    ProcessCityResponse,
)

logger = logging.getLogger(__name__)


class OrchestratorAgent(BaseAgent):
    """Agent that orchestrates the event discovery and notification process."""

    def __init__(
        self,
        config: DoraConfig,
        event_finder: BaseAgent,
        event_classifier: BaseAgent,
        language_selector: BaseAgent,
        text_writer: BaseAgent,
    ):
        """Initialize the orchestrator agent.
        
        Args:
            config: Application configuration
            event_finder: Event finder agent
            event_classifier: Event classifier agent
            language_selector: Language selector agent
            text_writer: Text writer agent
        """
        super().__init__(
            name="Orchestrator",
            config=config.orchestrator_config,
            api_config=config.get_api_config(),
        )
        
        self.event_finder = event_finder
        self.event_classifier = event_classifier
        self.language_selector = language_selector
        self.text_writer = text_writer
        
        logger.info("Orchestrator agent initialized with all sub-agents")

    def process(self, request: ProcessCityRequest, response_model: Type[ProcessCityResponse]) -> ProcessCityResponse:
        """Process a city to find events and generate notifications.
        
        Args:
            request: The request containing the city to process
            response_model: The response model (ProcessCityResponse)
            
        Returns:
            The response with event notifications
        """
        logger.info(f"Processing city: {request.city}")
        
        try:
            # Step 1: Find events in the city
            find_events_request = FindEventsRequest(city=request.city)
            find_events_response = self.event_finder.process(
                find_events_request, FindEventsResponse
            )
            
            if find_events_response.error:
                return ProcessCityResponse(
                    city=request.city,
                    error=f"Error finding events: {find_events_response.error}",
                )
            
            logger.info(f"Found {len(find_events_response.events)} events in {request.city}")
            
            if not find_events_response.events:
                return ProcessCityResponse(
                    city=request.city,
                    event_notifications=[],
                )
            
            # Step 2: Get languages spoken in the city
            languages_request = GetCityLanguagesRequest(city=request.city)
            languages_response = self.language_selector.process(
                languages_request, GetCityLanguagesResponse
            )
            
            if languages_response.error:
                return ProcessCityResponse(
                    city=request.city,
                    error=f"Error finding languages: {languages_response.error}",
                )
            
            logger.info(f"Found {len(languages_response.languages)} languages in {request.city}")
            
            # Step 3: Process each event
            event_notifications: List[EventNotification] = []
            
            for event in find_events_response.events:
                # Step 3.1: Classify the event
                classify_request = ClassifyEventRequest(event=event)
                classify_response = self.event_classifier.process(
                    classify_request, ClassifyEventResponse
                )
                
                if classify_response.error:
                    logger.warning(f"Error classifying event {event.name}: {classify_response.error}")
                    continue
                
                classified_event = classify_response.classified_event
                
                # Step 3.2: Generate notifications for each audience and language
                notifications = []
                
                for audience in classified_event.target_audiences:
                    for language in languages_response.languages:
                        notification_request = GenerateNotificationRequest(
                            event=classified_event,
                            audience=audience,
                            language=language,
                        )
                        
                        notification_response = self.text_writer.process(
                            notification_request, GenerateNotificationResponse
                        )
                        
                        if notification_response.error:
                            logger.warning(
                                f"Error generating notification for {event.name}, "
                                f"audience {audience}, language {language}: "
                                f"{notification_response.error}"
                            )
                            continue
                        
                        notifications.append(notification_response.notification)
                
                # Add the event with its notifications
                event_notification = EventNotification(
                    event=classified_event,
                    notifications=notifications,
                )
                
                event_notifications.append(event_notification)
            
            return ProcessCityResponse(
                city=request.city,
                event_notifications=event_notifications,
            )
            
        except Exception as e:
            logger.exception(f"Error processing city {request.city}")
            return ProcessCityResponse(
                city=request.city,
                error=f"Error processing city: {str(e)}",
            )