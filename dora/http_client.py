"""HTTP client for communicating with Dora HTTP server."""

import aiohttp
import logging
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class DoraHTTPClient:
    """Client for communicating with Dora HTTP server."""
    
    def __init__(self, base_url: str, api_key: Optional[str] = None):
        """Initialize the HTTP client.
        
        Args:
            base_url: Base URL of the Dora HTTP server (e.g., "http://localhost:8000")
            api_key: Optional API key for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'Content-Type': 'application/json'
        }
        if api_key:
            self.headers['Authorization'] = f'Bearer {api_key}'
    
    async def chat_completion(
        self, 
        message: str,
        model: str = "dora",
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        response_format: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send a chat completion request to the Dora server.
        
        Args:
            message: The user message to process
            model: Model to use (default: "dora")
            temperature: Temperature for response generation
            max_tokens: Maximum tokens in response
            stream: Whether to stream the response
            
        Returns:
            The server response as a dictionary
            
        Raises:
            aiohttp.ClientError: If the request fails
        """
        url = urljoin(self.base_url, '/v1/chat/completions')
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": message
                }
            ],
            "temperature": temperature,
            "stream": stream
        }
        
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        
        if response_format is not None:
            payload["response_format"] = response_format
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url, 
                    json=payload, 
                    headers=self.headers
                ) as response:
                    response.raise_for_status()
                    return await response.json()
            except aiohttp.ClientError as e:
                logger.error(f"HTTP request failed: {e}")
                raise
    
    async def get_models(self) -> List[Dict[str, Any]]:
        """Get list of available models.
        
        Returns:
            List of model information dictionaries
        """
        url = urljoin(self.base_url, '/v1/models')
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data.get('data', [])
            except aiohttp.ClientError as e:
                logger.error(f"Failed to get models: {e}")
                raise
    
    async def health_check(self) -> bool:
        """Check if the server is healthy.
        
        Returns:
            True if server is healthy, False otherwise
        """
        url = urljoin(self.base_url, '/health')
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as response:
                    return response.status == 200
            except aiohttp.ClientError:
                return False
    
    async def chat_completion_with_json(
        self,
        message: str,
        model: str = "dora",
        temperature: float = 0.0,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """Send a chat completion request with JSON response format.
        
        Args:
            message: The user message to process
            model: Model to use (default: "dora")
            temperature: Temperature for response generation
            max_tokens: Maximum tokens in response
            
        Returns:
            The server response as a dictionary
        """
        return await self.chat_completion(
            message=message,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "event_notifications",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "notifications": {
                                "type": "array",
                                "items": {
                                    "type": "object"
                                }
                            }
                        },
                        "required": ["notifications"]
                    }
                }
            }
        )