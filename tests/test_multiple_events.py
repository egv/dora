"""Test finding multiple events directly."""
import asyncio
from dora.tools import perplexity_search
from dora.models.config import DoraConfig

async def test_multiple_searches():
    config = DoraConfig()
    
    queries = [
        "concerts in New York next 2 weeks",
        "sports events in New York next 2 weeks", 
        "theater shows Broadway New York next 2 weeks",
        "museums exhibitions New York next 2 weeks",
        "festivals New York next 2 weeks",
        "comedy shows New York next 2 weeks"
    ]
    
    all_events = []
    for query in queries:
        print(f"\nSearching: {query}")
        result = perplexity_search(query, config.perplexity_api_key)
        if result.content:
            print(f"Found content: {result.content[:200]}...")
            # In real implementation, we'd parse events from content
            all_events.append(result.content)
    
    print(f"\nTotal search results: {len(all_events)}")

if __name__ == "__main__":
    asyncio.run(test_multiple_searches())