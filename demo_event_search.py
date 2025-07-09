#!/usr/bin/env python3
"""
Demo script for EventSearchAgent

This script demonstrates how to use the EventSearchAgent in a multi-agent system.
"""

import asyncio
import json
from uuid import uuid4

from agents.event_search import create_event_search_agent
from a2a.types import Message, MessageSendParams, Part, TextPart


async def demo_event_search():
    """Demonstrate EventSearchAgent functionality"""
    print("🔍 EventSearchAgent Demo")
    print("=" * 50)
    
    # Create the agent
    agent = create_event_search_agent(events_count=5)
    print(f"✅ Created {agent.name} v{agent.version}")
    print(f"📍 Agent URL: {agent.agent_card.url}")
    print(f"🎯 Skills: {[skill.id for skill in agent.skills]}")
    print()
    
    # Test cities
    test_cities = [
        {"city": "San Francisco", "events_count": 3},
        {"city": "New York"},
        "Tokyo",  # Plain text input
        {"city": "London", "days_ahead": 7}
    ]
    
    for i, city_input in enumerate(test_cities, 1):
        print(f"🌍 Test {i}: Searching events for {city_input}")
        print("-" * 30)
        
        # Prepare message
        if isinstance(city_input, dict):
            message_text = json.dumps(city_input)
        else:
            message_text = city_input
        
        params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(text=message_text)
                    )
                ]
            )
        )
        
        try:
            # Send message to agent
            response = await agent.request_handler.on_message_send(params)
            
            # Parse response
            response_data = json.loads(response.parts[0].root.text)
            
            print(f"🎪 Found {response_data['count']} events in {response_data['city']}")
            
            # Display events
            for j, event in enumerate(response_data['events'], 1):
                print(f"  {j}. {event['name']}")
                print(f"     📅 {event['start_date']}")
                print(f"     📍 {event['location']}")
                print(f"     🔗 {event['url']}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print()
    
    print("🎯 Demo completed!")
    print()
    print("💡 How to use in a multi-agent system:")
    print("   1. Start the EventSearchAgent server: agent.start_server()")
    print("   2. Other agents can call via A2A protocol")
    print("   3. Send JSON: {'city': 'Paris', 'events_count': 10}")
    print("   4. Receive events data for further processing")


async def demo_agent_card():
    """Show the agent card structure"""
    print("\n📋 Agent Card Structure")
    print("=" * 50)
    
    agent = create_event_search_agent()
    card = agent.agent_card
    
    print(f"Name: {card.name}")
    print(f"Description: {card.description}")
    print(f"Version: {card.version}")
    print(f"URL: {card.url}")
    print(f"Input Modes: {card.defaultInputModes}")
    print(f"Output Modes: {card.defaultOutputModes}")
    print()
    
    print("Skills:")
    for skill in card.skills:
        print(f"  • {skill.name} ({skill.id})")
        print(f"    Description: {skill.description}")
        print(f"    Tags: {skill.tags}")
        print(f"    Examples: {skill.examples}")
        print()


if __name__ == "__main__":
    asyncio.run(demo_event_search())
    asyncio.run(demo_agent_card())