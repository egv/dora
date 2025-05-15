"""Language selector agent implementation."""

import json
import logging
from typing import Dict, List, Type

from dora.agents.base import BaseAgent
from dora.models.config import DoraConfig
from dora.models.messages import GetCityLanguagesRequest, GetCityLanguagesResponse

logger = logging.getLogger(__name__)


class LanguageSelectorAgent(BaseAgent):
    """Agent that determines languages commonly spoken in a city."""

    def __init__(self, config: DoraConfig):
        """Initialize the language selector agent.
        
        Args:
            config: The application configuration
        """
        super().__init__(
            name="LanguageSelector",
            config=config.language_selector_config,
            api_config=config.get_api_config(),
        )
        
        # Cache of city to languages mapping to reduce API calls
        self._language_cache: Dict[str, List[str]] = {}

    def process(
        self, request: GetCityLanguagesRequest, response_model: Type[GetCityLanguagesResponse]
    ) -> GetCityLanguagesResponse:
        """Get languages commonly spoken in a city.
        
        Args:
            request: The request containing the city to get languages for
            response_model: The response model type
            
        Returns:
            The response containing the languages spoken in the city
        """
        city = request.city
        logger.info(f"Finding languages for city: {city}")
        
        # Check cache first
        if city in self._language_cache:
            logger.info(f"Using cached languages for {city}")
            return GetCityLanguagesResponse(
                city=city,
                languages=self._language_cache[city],
            )
        
        try:
            # Create a prompt for the model to determine languages
            prompt = f"""
            What are the main languages spoken in {city}? 

            Consider:
            1. Official languages
            2. Languages spoken by significant portions of the population
            3. Languages used in business or tourism

            Return the top 3 most widely spoken languages in this city, listed in order of prevalence.
            
            Return your response as a JSON object with the following structure:
            {{
                "languages": ["language1", "language2", "language3"]
            }}

            Use standard language names (English, Spanish, Mandarin, etc.) and ensure the list has at least 1 and at most 3 languages. 
            If there is only one main language, just include that one.
            Ensure the response is valid JSON and only contains the requested information.
            """
            
            messages = self._create_prompt(prompt)
            
            # Define a function to return languages in proper format
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "return_languages",
                        "description": "Return the languages spoken in a city",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "languages": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "List of languages spoken in the city",
                                },
                            },
                            "required": ["languages"],
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
                    raise ValueError("No valid JSON languages found in response")
                
                languages_data = json.loads(content[json_start:json_end])
            else:
                languages_data = json.loads(
                    tool_calls[0].get("function", {}).get("arguments", "{}")
                )
            
            languages = languages_data.get("languages", ["English"])
            
            # Ensure we have at least one language
            if not languages:
                languages = ["English"]
            
            # Limit to the top 3 languages
            languages = languages[:3]
            
            # Cache the result
            self._language_cache[city] = languages
            
            logger.info(f"Found languages for {city}: {', '.join(languages)}")
            
            return GetCityLanguagesResponse(
                city=city,
                languages=languages,
            )
            
        except Exception as e:
            logger.exception(f"Error finding languages for {city}")
            
            # Return a fallback with English as the default language
            return GetCityLanguagesResponse(
                city=city,
                languages=["English"],
                error=f"Error finding languages: {str(e)}",
            )