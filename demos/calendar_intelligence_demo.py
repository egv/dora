#!/usr/bin/env python3
"""
Calendar Intelligence Agent Demo - Real Data Sources Integration

This demo showcases the Calendar Intelligence Agent with integrated real data sources:
- EventSearchAgent for event discovery
- OpenWeatherMap API for weather data  
- Comprehensive holiday and cultural event data

Usage:
    uv run demos/calendar_intelligence_demo.py

Environment Variables (optional):
    WEATHER_API_KEY - OpenWeatherMap API key for real weather data
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.calendar_intelligence import CalendarIntelligenceAgent
from agents.event_search import EventSearchAgent


async def start_event_search_agent():
    """Start EventSearchAgent in background"""
    print("🚀 Starting EventSearchAgent...")
    event_agent = EventSearchAgent()
    
    # Start server in background (we'll let it run for the demo)
    import uvicorn
    config = uvicorn.Config(
        event_agent.build_fastapi_app(),
        host="localhost",
        port=8001,
        log_level="warning"  # Reduce noise
    )
    server = uvicorn.Server(config)
    
    # Start server in a background task
    server_task = asyncio.create_task(server.serve())
    
    # Give it a moment to start up
    await asyncio.sleep(2)
    print("✅ EventSearchAgent running on http://localhost:8001")
    
    return server_task


async def demo_calendar_intelligence():
    """Main demo function"""
    print("=" * 60)
    print("🧠 Calendar Intelligence Agent Demo")
    print("🔗 Real Data Sources Integration")
    print("=" * 60)
    
    # Check for API keys
    weather_api_key = os.getenv("WEATHER_API_KEY")
    if weather_api_key:
        print(f"🌤️  Weather API: Configured (key: {weather_api_key[:8]}...)")
    else:
        print("🌤️  Weather API: Using mock data (set WEATHER_API_KEY for real data)")
    
    # Start EventSearchAgent
    event_server_task = await start_event_search_agent()
    
    try:
        # Initialize Calendar Intelligence Agent
        print("\n🧠 Initializing Calendar Intelligence Agent...")
        calendar_agent = CalendarIntelligenceAgent()
        
        # Test locations and dates
        test_scenarios = [
            {
                "location": "San Francisco",
                "date": datetime.now() + timedelta(days=1),
                "description": "Major tech hub with events"
            },
            {
                "location": "New York",
                "date": datetime.now() + timedelta(days=3),
                "description": "Cultural center with entertainment"
            },
            {
                "location": "London",
                "date": datetime.now() + timedelta(days=5),
                "description": "Historic city with festivals"
            }
        ]
        
        print("\n" + "=" * 60)
        print("📊 CALENDAR DATA COLLECTION DEMO")
        print("=" * 60)
        
        for i, scenario in enumerate(test_scenarios, 1):
            location = scenario["location"]
            date = scenario["date"]
            description = scenario["description"]
            
            print(f"\n🏙️  Scenario {i}: {location}")
            print(f"📅 Date: {date.strftime('%Y-%m-%d')}")
            print(f"📝 Description: {description}")
            print("-" * 40)
            
            # Get calendar data
            result = await calendar_agent.executor._get_calendar_data({
                "location": location,
                "date": date.isoformat()
            })
            
            calendar_data = result["calendar_data"]
            verification = result["verification_scores"]
            sources = result["data_sources"]
            
            # Display results
            print(f"🎯 Opportunity Score: {calendar_data['opportunity_score']}/100")
            print(f"🌡️  Weather: {calendar_data['weather'].get('condition', 'unknown')} "
                  f"({calendar_data['weather'].get('temperature', 'N/A')}°C)")
            print(f"🎉 Events Found: {len(calendar_data['events'])}")
            print(f"🎊 Holidays: {', '.join(calendar_data['holidays']) if calendar_data['holidays'] else 'None'}")
            print(f"⭐ Cultural Significance: {calendar_data['cultural_significance']}")
            
            # Show sample events
            if calendar_data['events']:
                print("\n📅 Sample Events:")
                for event in calendar_data['events'][:2]:  # Show first 2 events
                    print(f"  • {event['name']} ({event['category']})")
                    print(f"    📍 {event['location']}")
                    print(f"    🕒 {event['start_time'][:16]}")
            
            # Show data source quality
            print(f"\n📊 Data Quality:")
            print(f"  • Events Confidence: {verification['events_confidence']:.2f}")
            print(f"  • Weather Confidence: {verification['weather_confidence']:.2f}")
            print(f"  • Weather Source: {calendar_data['weather'].get('source', 'unknown')}")
            
            if i < len(test_scenarios):
                print()
        
        print("\n" + "=" * 60)
        print("📈 MARKETING INSIGHTS DEMO")
        print("=" * 60)
        
        # Test marketing insights
        insights_result = await calendar_agent.executor._get_marketing_insights({
            "location": "San Francisco",
            "start_date": datetime.now().isoformat(),
            "end_date": (datetime.now() + timedelta(days=7)).isoformat()
        })
        
        print(f"\n🏙️  Marketing Insights for San Francisco (Next 7 Days)")
        print("-" * 50)
        
        summary = insights_result["summary"]
        print(f"📊 Average Opportunity Score: {summary['average_opportunity_score']:.1f}/100")
        print(f"🎉 Total Events: {summary['total_events']}")
        print(f"🎊 Holiday Days: {summary['holiday_days']}")
        
        print(f"\n🎯 Best Opportunities:")
        for i, day in enumerate(summary['best_opportunities'], 1):
            print(f"  {i}. {day['date'][:10]} - Score: {day['opportunity_score']}/100")
            print(f"     🌤️  {day['weather_condition']}, 🎉 {day['events_count']} events")
        
        print("\n" + "=" * 60)
        print("🔍 OPPORTUNITY ANALYSIS DEMO")
        print("=" * 60)
        
        # Test opportunity analysis
        analysis_result = await calendar_agent.executor._analyze_opportunity({
            "location": "New York",
            "date": (datetime.now() + timedelta(days=2)).isoformat(),
            "criteria": {
                "target_audience": "families",
                "campaign_type": "outdoor"
            }
        })
        
        print(f"\n🏙️  Opportunity Analysis for New York")
        print(f"📅 Date: {analysis_result['date'][:10]}")
        print(f"🎯 Base Score: {analysis_result['base_opportunity_score']}/100")
        print("-" * 40)
        
        factors = analysis_result["factors"]
        print(f"🎉 Events: {factors['events']['count']} events")
        print(f"   Categories: {', '.join(factors['events']['categories'])}")
        print(f"🌤️  Weather: {factors['weather']['condition']} ({factors['weather']['favorability']} favorability)")
        print(f"⭐ Cultural: {factors['cultural']['significance']} significance")
        
        if analysis_result["recommendations"]:
            print(f"\n💡 Recommendations:")
            for rec in analysis_result["recommendations"]:
                print(f"  • {rec}")
        else:
            print(f"\n💡 No specific recommendations for given criteria")
        
        print("\n" + "=" * 60)
        print("✅ DEMO COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print("\n🔗 Data Sources Used:")
        print("  • EventSearchAgent (A2A Protocol)")
        if weather_api_key:
            print("  • OpenWeatherMap API (Real Weather)")
        else:
            print("  • Mock Weather Data")
        print("  • Comprehensive Holiday Database")
        print("  • Cultural Events by Location")
        print("\n🚀 The Calendar Intelligence Agent is ready for multi-agent systems!")
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up
        print("\n🧹 Cleaning up...")
        event_server_task.cancel()
        try:
            await event_server_task
        except asyncio.CancelledError:
            pass
        print("✅ Cleanup complete")


if __name__ == "__main__":
    # Run the demo
    try:
        asyncio.run(demo_calendar_intelligence())
    except KeyboardInterrupt:
        print("\n\n👋 Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        sys.exit(1)