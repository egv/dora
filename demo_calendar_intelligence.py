#!/usr/bin/env python3
"""
Demo script for Calendar Intelligence Agent

This script demonstrates how to use the Calendar Intelligence Agent 
for intelligent calendar analysis and marketing insights.
"""

import asyncio
import json
from uuid import uuid4
from datetime import datetime, timedelta

from agents.calendar_intelligence import create_calendar_intelligence_agent
from a2a.types import Message, MessageSendParams, Part, TextPart


async def demo_calendar_intelligence():
    """Demonstrate Calendar Intelligence Agent functionality"""
    print("🧠 Calendar Intelligence Agent Demo")
    print("=" * 60)
    
    # Create the agent
    agent = create_calendar_intelligence_agent()
    print(f"✅ Created {agent.name} v{agent.version}")
    print(f"📍 Agent URL: {agent.agent_card.url}")
    print(f"🎯 Skills: {[skill.id for skill in agent.skills]}")
    print()
    
    # Test scenarios
    test_scenarios = [
        {
            "name": "Basic Calendar Data",
            "request": {
                "location": "San Francisco",
                "date": "2025-07-15"
            }
        },
        {
            "name": "Calendar Data (No Date - Uses Today)",
            "request": {
                "location": "New York"
            }
        },
        {
            "name": "Marketing Insights (Week)",
            "request": {
                "location": "London",
                "request_type": "insights",
                "start_date": "2025-07-15",
                "end_date": "2025-07-21"
            }
        },
        {
            "name": "Opportunity Analysis",
            "request": {
                "location": "Tokyo",
                "date": "2025-07-20",
                "request_type": "analyze",
                "criteria": {
                    "target_audience": "families",
                    "campaign_type": "outdoor"
                }
            }
        }
    ]
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"🔍 Test {i}: {scenario['name']}")
        print("-" * 40)
        
        # Prepare message
        params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(text=json.dumps(scenario['request']))
                    )
                ]
            )
        )
        
        try:
            # Send message to agent
            response = await agent.request_handler.on_message_send(params)
            
            # Parse response
            response_data = json.loads(response.parts[0].root.text)
            
            # Display results based on scenario type
            if "calendar_data" in response_data:
                # Basic calendar data
                calendar_data = response_data["calendar_data"]
                print(f"📅 Date: {calendar_data['date']}")
                print(f"🌍 Location: {calendar_data['location']}")
                print(f"🎯 Opportunity Score: {calendar_data['opportunity_score']}/100")
                print(f"🎪 Events: {len(calendar_data['events'])}")
                print(f"🌤️  Weather: {calendar_data['weather'].get('condition', 'unknown')}")
                print(f"🎉 Holidays: {', '.join(calendar_data['holidays']) if calendar_data['holidays'] else 'None'}")
                print(f"📊 Cultural Significance: {calendar_data['cultural_significance']}")
                
                # Show events
                if calendar_data['events']:
                    print("\nEvents:")
                    for j, event in enumerate(calendar_data['events'], 1):
                        print(f"  {j}. {event['name']}")
                        print(f"     📍 {event['location']}")
                        print(f"     ⏰ {event.get('start_time', 'TBD')}")
                
            elif "insights" in response_data:
                # Marketing insights
                print(f"🌍 Location: {response_data['location']}")
                print(f"📅 Date Range: {response_data['date_range']['start']} to {response_data['date_range']['end']}")
                
                summary = response_data["summary"]
                print(f"📊 Average Opportunity Score: {summary['average_opportunity_score']:.1f}/100")
                print(f"🎪 Total Events: {summary['total_events']}")
                print(f"🎉 Holiday Days: {summary['holiday_days']}")
                
                print("\n🏆 Best Opportunities:")
                for j, day in enumerate(summary['best_opportunities'], 1):
                    print(f"  {j}. {day['date']} - Score: {day['opportunity_score']}")
                    print(f"     Events: {day['events_count']}, Weather: {day['weather_condition']}")
                
            elif "factors" in response_data:
                # Opportunity analysis
                print(f"🌍 Location: {response_data['location']}")
                print(f"📅 Date: {response_data['date']}")
                print(f"🎯 Base Opportunity Score: {response_data['base_opportunity_score']}/100")
                
                factors = response_data["factors"]
                print(f"\n📊 Analysis Factors:")
                print(f"  🎪 Events: {factors['events']['count']} ({', '.join(factors['events']['categories'])})")
                print(f"  🌤️  Weather: {factors['weather']['condition']} ({factors['weather']['favorability']} favorability)")
                print(f"  🎭 Cultural: {factors['cultural']['significance']} significance")
                
                if response_data["recommendations"]:
                    print(f"\n💡 Recommendations:")
                    for rec in response_data["recommendations"]:
                        print(f"  • {rec}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print()
    
    print("🎯 Demo completed!")
    print()
    print("💡 How to use in a multi-agent system:")
    print("   1. Start the Calendar Intelligence Agent server: agent.start_server()")
    print("   2. Other agents can call via A2A protocol for:")
    print("      • Calendar data analysis")
    print("      • Marketing opportunity insights")
    print("      • Event and cultural significance analysis")
    print("   3. Perfect for coordinating with EventSearchAgent for comprehensive intelligence")


async def demo_opportunity_scoring():
    """Show how opportunity scoring works"""
    print("\n🎯 Opportunity Scoring Explanation")
    print("=" * 60)
    
    from agents.calendar_intelligence import CalendarData
    from datetime import datetime
    
    # Create test scenarios
    scenarios = [
        {
            "name": "Perfect Day",
            "events": [{"name": f"Event {i}"} for i in range(5)],
            "weather": {"condition": "sunny"},
            "holidays": ["Summer Festival"],
            "cultural_significance": "high",
            "historical_engagement": 0.9
        },
        {
            "name": "Average Day", 
            "events": [{"name": f"Event {i}"} for i in range(2)],
            "weather": {"condition": "partly_cloudy"},
            "holidays": [],
            "cultural_significance": "medium",
            "historical_engagement": 0.5
        },
        {
            "name": "Poor Day",
            "events": [],
            "weather": {"condition": "rainy"},
            "holidays": [],
            "cultural_significance": "low",
            "historical_engagement": 0.2
        }
    ]
    
    print("Scoring Breakdown (max 100 points):")
    print("• Base Score: 50 points")
    print("• Events (0-20): 2 points per event")  
    print("• Weather (0-15): 15=sunny, 10=partly_cloudy, 5=cloudy, 0=rainy")
    print("• Holidays (0-25): 25=holiday, 15=near holiday, 10=payday")
    print("• Culture (0-15): 15=high, 10=medium, 0=low significance")
    print("• History (0-25): Based on past engagement data")
    print()
    
    for scenario in scenarios:
        calendar_data = CalendarData(datetime.now(), "Test City")
        calendar_data.events = scenario["events"]
        calendar_data.weather = scenario["weather"]
        calendar_data.holidays = scenario["holidays"]
        calendar_data.cultural_significance = scenario["cultural_significance"]
        calendar_data.historical_engagement = scenario["historical_engagement"]
        
        score = calendar_data.calculate_opportunity_score()
        
        print(f"📊 {scenario['name']}: {score}/100")
        print(f"   Events: {len(scenario['events'])}, Weather: {scenario['weather']['condition']}")
        print(f"   Holidays: {len(scenario['holidays'])}, Culture: {scenario['cultural_significance']}")
        print(f"   Historical Engagement: {scenario['historical_engagement']}")
        print()


async def demo_agent_capabilities():
    """Show the agent's capabilities"""
    print("\n🔧 Agent Capabilities")
    print("=" * 60)
    
    agent = create_calendar_intelligence_agent()
    card = agent.agent_card
    
    print(f"Agent: {card.name}")
    print(f"Description: {card.description}")
    print(f"Version: {card.version}")
    print(f"URL: {card.url}")
    print()
    
    print("Available Skills:")
    for skill in card.skills:
        print(f"\n🎯 {skill.name} ({skill.id})")
        print(f"   Description: {skill.description}")
        print(f"   Tags: {', '.join(skill.tags)}")
        print(f"   Examples:")
        for example in skill.examples:
            print(f"     • {example}")


if __name__ == "__main__":
    asyncio.run(demo_calendar_intelligence())
    asyncio.run(demo_opportunity_scoring())
    asyncio.run(demo_agent_capabilities())