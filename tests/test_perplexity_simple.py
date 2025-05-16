"""Test Perplexity search."""
from dora.tools import perplexity_search
from dora.models.config import DoraConfig

config = DoraConfig()
result = perplexity_search("Find upcoming events in San Francisco for the next 2 weeks", config.perplexity_api_key)
print(f"Content: {result.content}")
print(f"Error: {result.error}")