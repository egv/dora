"""Test the event finder agent."""
import asyncio
from dora.__main__ import create_event_finder_agent
from dora.models.config import DoraConfig
from openai_agents import Runner

async def test_event_finder():
    config = DoraConfig()
    
    # Set the OpenAI API key
    import openai_agents as agents
    agents.set_default_openai_key(config.openai_api_key)
    
    # Create the event finder agent
    event_finder = create_event_finder_agent(config)
    
    # Test with New York
    prompt = "Find events in New York for the next 14 days. Include concerts, festivals, sports events, and cultural events."
    result = await Runner.run(event_finder, prompt)
    
    print(f"Events found: {len(result.final_output.events)}")
    for i, event in enumerate(result.final_output.events, 1):
        print(f"\nEvent {i}:")
        print(f"  Name: {event.name}")
        print(f"  Description: {event.description}")
        print(f"  Location: {event.location}")
        print(f"  Date: {event.start_date}")

if __name__ == "__main__":
    asyncio.run(test_event_finder())