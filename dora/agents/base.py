"""Base agent implementation."""

import logging
from typing import Any, Dict, Optional, Type, TypeVar

from openai import OpenAI
from pydantic import BaseModel

from dora.models.config import AgentConfig, APIConfig

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
U = TypeVar("U", bound=BaseModel)


class BaseAgent:
    """Base class for all agents in Dora."""

    def __init__(
        self,
        name: str,
        config: AgentConfig,
        api_config: APIConfig,
    ):
        """Initialize the base agent.

        Args:
            name: The name of the agent
            config: The agent configuration
            api_config: API keys and configuration
        """
        self.name = name
        self.config = config
        self.api_config = api_config
        self.client = OpenAI(api_key=api_config.openai_api_key)
        
        logger.info(f"Initialized {name} agent")

    def _create_prompt(self, message_content: str) -> list[dict[str, str]]:
        """Create a prompt for the agent.
        
        Args:
            message_content: The content of the message
            
        Returns:
            List of message dictionaries for the OpenAI API
        """
        messages = []
        
        if self.config.system_prompt:
            messages.append({"role": "system", "content": self.config.system_prompt})
            
        messages.append({"role": "user", "content": message_content})
        
        return messages

    def _call_llm(self, messages: list[dict[str, str]], tools=None) -> Dict[str, Any]:
        """Call the LLM with the given messages.
        
        Args:
            messages: The messages to send to the LLM
            tools: Optional tools to provide to the LLM
            
        Returns:
            The LLM response
        """
        kwargs = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
        }
        
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        
        response = self.client.chat.completions.create(**kwargs)
        return response.model_dump()

    def process(self, request: T, response_model: Type[U]) -> U:
        """Process a request and return a response.
        
        Args:
            request: The request to process
            response_model: The type of response to return
            
        Returns:
            The processed response
        """
        raise NotImplementedError("Subclasses must implement this method")