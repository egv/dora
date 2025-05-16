"""Tools for Dora agents."""

import json
import logging
from typing import Any, Dict, List, Optional

import httpx
from agents import FunctionTool

logger = logging.getLogger(__name__)


def perplexity_search_tool(api_key: str) -> FunctionTool:
    """Create a tool for searching with Perplexity API.
    
    Args:
        api_key: Perplexity API key
        
    Returns:
        Search tool
    """
    async def search_perplexity(query: str) -> str:
        """Search for information using Perplexity API.
        
        Args:
            query: The search query
            
        Returns:
            Search results
        """
        if not api_key:
            return json.dumps({"error": "Perplexity API key is not configured"})
        
        try:
            url = "https://api.perplexity.ai/chat/completions"
            
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            
            data = {
                "model": "pplx-7b-online",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant that helps find events."},
                    {"role": "user", "content": query},
                ],
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=data)
                response.raise_for_status()
                result = response.json()
                
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return content
                
        except Exception as e:
            logger.exception(f"Error querying Perplexity API: {e}")
            return json.dumps({"error": f"Perplexity API error: {str(e)}"})
    
    return FunctionTool(
        name="search_perplexity",
        description="Search for events in a city using Perplexity API",
        function=search_perplexity,
        args_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to send to Perplexity"
                }
            },
            "required": ["query"]
        }
    )