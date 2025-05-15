"""Event classifier agent implementation."""

import json
import logging
from typing import Any, Dict, List, Type

from dora.agents.base import BaseAgent
from dora.models.config import DoraConfig
from dora.models.event import (
    AudienceDemographic,
    ClassifiedEvent,
    EventImportance,
    EventSize,
)
from dora.models.messages import ClassifyEventRequest, ClassifyEventResponse

logger = logging.getLogger(__name__)


class EventClassifierAgent(BaseAgent):
    """Agent that classifies events by size, importance, and target audiences."""

    def __init__(self, config: DoraConfig):
        """Initialize the event classifier agent.
        
        Args:
            config: The application configuration
        """
        super().__init__(
            name="EventClassifier",
            config=config.event_classifier_config,
            api_config=config.get_api_config(),
        )

    def process(
        self, request: ClassifyEventRequest, response_model: Type[ClassifyEventResponse]
    ) -> ClassifyEventResponse:
        """Classify an event by size, importance, and target audiences.
        
        Args:
            request: The request containing the event to classify
            response_model: The response model type
            
        Returns:
            The response containing the classified event
        """
        logger.info(f"Classifying event: {request.event.name}")
        
        try:
            # Create a prompt for the model to classify the event
            event = request.event
            prompt = f"""
            Please analyze this event and provide classifications for its size, importance, and target audiences.

            EVENT DETAILS:
            Name: {event.name}
            Description: {event.description}
            Location: {event.location}
            City: {event.city}
            Date: {event.start_date.strftime('%Y-%m-%d')}
            
            Please classify this event according to the following criteria:

            1. SIZE (choose one):
               - SMALL: less than 100 people
               - MEDIUM: 100-1000 people
               - LARGE: 1000-10000 people
               - HUGE: more than 10000 people

            2. IMPORTANCE (choose one):
               - LOW: Local event with minimal impact
               - MEDIUM: Notable local event or small regional event
               - HIGH: Major regional event or small national event
               - CRITICAL: Major national or international event

            3. TARGET AUDIENCES:
               Identify exactly 3 primary demographic groups that would be most interested in this event.
               For each group, specify:
               - Gender (if relevant)
               - Age range
               - Income level (low, middle, high)
               - Any other relevant attributes (e.g., "music enthusiasts", "sports fans", "art lovers")

            Return your analysis as a JSON object with the following structure:
            {{
                "size": "SMALL/MEDIUM/LARGE/HUGE",
                "importance": "LOW/MEDIUM/HIGH/CRITICAL",
                "target_audiences": [
                    {{
                        "gender": "male/female/any",
                        "age_range": "e.g., 18-25, 30-45",
                        "income_level": "low/middle/high",
                        "other_attributes": ["attribute1", "attribute2"]
                    }},
                    // Repeat for all 3 target audiences
                ]
            }}

            Ensure the response is valid JSON and only contains the requested information.
            """
            
            messages = self._create_prompt(prompt)
            
            # Define a function to return the classification in proper format
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "return_classification",
                        "description": "Return the classification for an event",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "size": {
                                    "type": "string",
                                    "enum": ["SMALL", "MEDIUM", "LARGE", "HUGE"],
                                },
                                "importance": {
                                    "type": "string",
                                    "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                                },
                                "target_audiences": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "gender": {"type": "string"},
                                            "age_range": {"type": "string"},
                                            "income_level": {"type": "string"},
                                            "other_attributes": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
                                        },
                                    },
                                    "minItems": 1,
                                    "maxItems": 3,
                                },
                            },
                            "required": ["size", "importance", "target_audiences"],
                        },
                    },
                }
            ]
            
            response = self._call_llm(messages, tools)
            
            tool_calls = response.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
            
            if not tool_calls:
                # Fallback for when tool_calls is not returned
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                # Try to extract JSON from the content
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                
                if json_start == -1 or json_end == 0:
                    raise ValueError("No valid JSON classification found in response")
                
                classification_data = json.loads(content[json_start:json_end])
            else:
                classification_data = json.loads(
                    tool_calls[0].get("function", {}).get("arguments", "{}")
                )
            
            # Map the classification to our models
            size = EventSize(classification_data.get("size", "MEDIUM").lower())
            importance = EventImportance(classification_data.get("importance", "MEDIUM").lower())
            
            # Process target audiences
            audiences = []
            for audience_data in classification_data.get("target_audiences", [])[:3]:
                audience = AudienceDemographic(
                    gender=audience_data.get("gender"),
                    age_range=audience_data.get("age_range"),
                    income_level=audience_data.get("income_level"),
                    other_attributes=audience_data.get("other_attributes", []),
                )
                audiences.append(audience)
            
            # If for some reason we don't have enough audiences, add generic ones
            while len(audiences) < 1:
                audiences.append(AudienceDemographic(
                    gender="any",
                    age_range="25-45",
                    income_level="middle",
                    other_attributes=["general audience"],
                ))
            
            classified_event = ClassifiedEvent(
                event=event,
                size=size,
                importance=importance,
                target_audiences=audiences,
            )
            
            logger.info(
                f"Classified {event.name} as size={size}, importance={importance}, "
                f"with {len(audiences)} target audiences"
            )
            
            return ClassifyEventResponse(classified_event=classified_event)
            
        except Exception as e:
            logger.exception(f"Error classifying event {request.event.name}")
            return ClassifyEventResponse(
                classified_event=ClassifiedEvent(
                    event=request.event,
                    size=EventSize.MEDIUM,  # Default size
                    importance=EventImportance.MEDIUM,  # Default importance
                    target_audiences=[
                        AudienceDemographic(
                            gender="any",
                            age_range="25-45",
                            income_level="middle",
                            other_attributes=["general audience"],
                        )
                    ],
                ),
                error=f"Error classifying event: {str(e)}",
            )