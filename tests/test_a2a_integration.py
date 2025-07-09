"""
Integration tests for A2A communication between EventSearchAgent and EventCollector
"""

import asyncio
import pytest
from datetime import datetime, timedelta

from agents.event_search import EventSearchAgent
from agents.collectors.event_collector import EventCollector


class TestA2AIntegration:
    """Test A2A protocol integration between agents"""
    
    @pytest.fixture
    async def event_search_agent(self):
        """Create and start EventSearchAgent for testing"""
        agent = EventSearchAgent()
        
        # Start server in background
        import uvicorn
        config = uvicorn.Config(
            agent.build_fastapi_app(),
            host="localhost",
            port=8001,
            log_level="error"  # Reduce noise
        )
        server = uvicorn.Server(config)
        
        # Start server in background task
        server_task = asyncio.create_task(server.serve())
        
        # Give server time to start
        await asyncio.sleep(1)
        
        yield agent
        
        # Cleanup
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
    
    @pytest.mark.asyncio
    async def test_event_collector_a2a_communication(self, event_search_agent):
        """Test that EventCollector can communicate with EventSearchAgent via A2A"""
        collector = EventCollector()
        
        # Test event collection
        events = await collector.collect_events(
            location="San Francisco",
            date=datetime.now() + timedelta(days=1),
            events_count=3
        )
        
        # Verify results
        assert isinstance(events, list)
        assert len(events) > 0  # Should have at least some events
        
        # Check event structure
        for event in events:
            assert "name" in event
            assert "description" in event
            assert "location" in event
            assert "start_time" in event
            assert "end_time" in event
            assert "category" in event
            assert "attendance_estimate" in event
            assert "source" in event
            assert event["source"] == "EventSearchAgent"
    
    @pytest.mark.asyncio
    async def test_event_collector_retry_logic(self, event_search_agent):
        """Test retry logic when EventSearchAgent is temporarily unavailable"""
        collector = EventCollector()
        
        # Test with working agent first
        events = await collector.collect_events(
            location="New York",
            date=datetime.now() + timedelta(days=2),
            events_count=2
        )
        
        assert len(events) > 0
        
        # Test with invalid URL (should return empty list after retries)
        bad_collector = EventCollector(event_search_agent_url="http://localhost:9999")
        
        events = await bad_collector.collect_events(
            location="London",
            date=datetime.now() + timedelta(days=1),
            events_count=2
        )
        
        # Should return empty list after retries fail
        assert isinstance(events, list)
        assert len(events) == 0
    
    @pytest.mark.asyncio
    async def test_event_categorization(self, event_search_agent):
        """Test that events are properly categorized"""
        collector = EventCollector()
        
        events = await collector.collect_events(
            location="Seattle",
            date=datetime.now() + timedelta(days=1),
            events_count=5
        )
        
        # Check that events have valid categories
        valid_categories = [
            "music", "market", "sports", "art", "food", 
            "technology", "festival", "general"
        ]
        
        for event in events:
            assert event["category"] in valid_categories
            assert isinstance(event["attendance_estimate"], int)
            assert event["attendance_estimate"] > 0
    
    @pytest.mark.asyncio
    async def test_multiple_concurrent_requests(self, event_search_agent):
        """Test that multiple concurrent requests work properly"""
        collector = EventCollector()
        
        # Make multiple concurrent requests
        tasks = []
        cities = ["Boston", "Chicago", "Miami", "Denver"]
        
        for city in cities:
            task = collector.collect_events(
                location=city,
                date=datetime.now() + timedelta(days=1),
                events_count=2
            )
            tasks.append(task)
        
        # Wait for all requests to complete
        results = await asyncio.gather(*tasks)
        
        # Verify all requests succeeded
        assert len(results) == len(cities)
        
        for events in results:
            assert isinstance(events, list)
            assert len(events) > 0  # Should have some events
    
    @pytest.mark.asyncio
    async def test_event_data_transformation(self, event_search_agent):
        """Test that event data is properly transformed to our format"""
        collector = EventCollector()
        
        events = await collector.collect_events(
            location="Austin",
            date=datetime.now() + timedelta(days=1),
            events_count=1
        )
        
        assert len(events) > 0
        event = events[0]
        
        # Check required fields
        required_fields = [
            "name", "description", "location", "start_time", 
            "end_time", "category", "attendance_estimate", 
            "source", "url"
        ]
        
        for field in required_fields:
            assert field in event, f"Missing field: {field}"
        
        # Check data types
        assert isinstance(event["name"], str)
        assert isinstance(event["description"], str)
        assert isinstance(event["location"], str)
        assert isinstance(event["start_time"], str)
        assert isinstance(event["end_time"], str)
        assert isinstance(event["category"], str)
        assert isinstance(event["attendance_estimate"], int)
        assert isinstance(event["source"], str)
        assert isinstance(event["url"], str)
        
        # Check that dates are in ISO format
        assert "2025-" in event["start_time"]  # Should be future date
        assert "2025-" in event["end_time"]