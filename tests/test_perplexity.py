"""Test Perplexity tool."""
import asyncio
from dora.tools import perplexity_search
from dora.models.config import DoraConfig

async def main():
    config = DoraConfig()
    result = perplexity_search("Find upcoming events in San Francisco for the next 2 weeks", config.perplexity_api_key)
    print(f"Result: {result}")
    print(f"Content: {result.content}")
    print(f"Error: {result.error}")

if __name__ == "__main__":
    asyncio.run(main())