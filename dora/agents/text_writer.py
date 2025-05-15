"""Text writer agent implementation."""

import json
import logging
from typing import Dict, Type

from dora.agents.base import BaseAgent
from dora.models.config import DoraConfig
from dora.models.event import NotificationContent
from dora.models.messages import GenerateNotificationRequest, GenerateNotificationResponse

logger = logging.getLogger(__name__)


class TextWriterAgent(BaseAgent):
    """Agent that generates push notification text for events."""

    def __init__(self, config: DoraConfig):
        """Initialize the text writer agent.
        
        Args:
            config: The application configuration
        """
        super().__init__(
            name="TextWriter",
            config=config.text_writer_config,
            api_config=config.get_api_config(),
        )
        
        # Optional cache to avoid regenerating the same content
        self._notification_cache: Dict[str, NotificationContent] = {}

    def _get_cache_key(self, request: GenerateNotificationRequest) -> str:
        """Generate a cache key for a notification request.
        
        Args:
            request: The notification request
            
        Returns:
            A unique cache key
        """
        event_name = request.event.event.name
        audience_str = str(request.audience)
        language = request.language
        return f"{event_name}|{audience_str}|{language}"

    def process(
        self, request: GenerateNotificationRequest, response_model: Type[GenerateNotificationResponse]
    ) -> GenerateNotificationResponse:
        """Generate a push notification for an event.
        
        Args:
            request: The request containing the event, audience, and language
            response_model: The response model type
            
        Returns:
            The response containing the generated notification
        """
        event = request.event
        audience = request.audience
        language = request.language
        
        logger.info(
            f"Generating notification for event '{event.event.name}' "
            f"for audience '{audience}' in language '{language}'"
        )
        
        # Check cache first
        cache_key = self._get_cache_key(request)
        if cache_key in self._notification_cache:
            logger.info(f"Using cached notification for {cache_key}")
            return GenerateNotificationResponse(
                notification=self._notification_cache[cache_key],
            )
        
        try:
            # Create a prompt for the model to generate a notification
            event_details = event.event
            
            # Format the date for display
            start_date_format = event_details.start_date.strftime("%B %d, %Y")
            time_format = event_details.start_date.strftime("%I:%M %p")
            
            prompt = f"""
            Generate a compelling push notification to promote taking a taxi (with a 10% discount) to the following event.
            The notification must be written in {language}.

            EVENT DETAILS:
            Name: {event_details.name}
            Description: {event_details.description}
            Location: {event_details.location}
            City: {event_details.city}
            Date: {start_date_format}
            Time: {time_format}
            Event Size: {event.size.value}
            Event Importance: {event.importance.value}

            TARGET AUDIENCE:
            {audience}

            REQUIREMENTS:
            1. Write the notification in {language}
            2. Maximum 140 characters (like a tweet)
            3. Include a mention of the 10% taxi discount to the event
            4. Make it appealing specifically to the target audience
            5. Include a clear call-to-action
            6. Create urgency without being pushy

            Return your push notification as a JSON object with the following structure:
            {{
                "text": "Your notification text here"
            }}

            Ensure the response is valid JSON, only contains the requested information, and the text is in {language}.
            """
            
            messages = self._create_prompt(prompt)
            
            # Define a function to return the notification in proper format
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "return_notification",
                        "description": f"Return a push notification in {language}",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "text": {
                                    "type": "string",
                                    "description": f"The push notification text in {language}",
                                },
                            },
                            "required": ["text"],
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
                    # If no JSON found, treat the whole content as the notification text
                    notification_text = content.strip()
                else:
                    notification_data = json.loads(content[json_start:json_end])
                    notification_text = notification_data.get("text", content.strip())
            else:
                notification_data = json.loads(
                    tool_calls[0].get("function", {}).get("arguments", "{}")
                )
                notification_text = notification_data.get("text", "")
            
            # Ensure the text isn't empty
            if not notification_text:
                raise ValueError("Generated notification text is empty")
            
            # Create the notification content
            notification = NotificationContent(
                language=language,
                audience=audience,
                text=notification_text,
            )
            
            # Cache the result
            self._notification_cache[cache_key] = notification
            
            logger.info(f"Generated notification for {event_details.name} in {language}")
            
            return GenerateNotificationResponse(notification=notification)
            
        except Exception as e:
            logger.exception(
                f"Error generating notification for {event.event.name} "
                f"for audience {audience} in {language}"
            )
            
            # Create a fallback notification
            fallback_text = f"10% discount on taxi to {event.event.name} at {event.event.location}!"
            
            # Try to translate the fallback text if language is not English
            if language.lower() != "english":
                try:
                    translate_prompt = f"Translate this text to {language}: '{fallback_text}'"
                    translate_messages = self._create_prompt(translate_prompt)
                    translate_response = self._call_llm(translate_messages)
                    translated_text = translate_response.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if translated_text:
                        fallback_text = translated_text.strip()
                except Exception:
                    # If translation fails, use English fallback
                    logger.exception(f"Error translating fallback text to {language}")
            
            fallback_notification = NotificationContent(
                language=language,
                audience=audience,
                text=fallback_text,
            )
            
            return GenerateNotificationResponse(
                notification=fallback_notification,
                error=f"Error generating notification: {str(e)}",
            )