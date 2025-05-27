"""Quick test to see how many events are found."""
import asyncio
from dora.__main__ import create_event_finder_agent
from dora.models.config import DoraConfig
from openai_agents import Runner

async def test_event_count():
    config = DoraConfig()
    import openai_agents as agents
    agents.set_default_openai_key(config.openai_api_key)
    
    event_finder = create_event_finder_agent(config)
    
    print("Finding events in New York...")
    result = await Runner.run(event_finder, "New York")
    
    events = result.final_output.events
    print(f"\nFound {len(events)} events!")
    
    # Show first 3 events
    for i, event in enumerate(events[:3], 1):
        print(f"\nEvent {i}: {event.name}")
        print(f"  Date: {event.start_date}")
        print(f"  Location: {event.location}")

if __name__ == "__main__":
    asyncio.run(test_event_count())