"""
Test Calendar Intelligence Agent
"""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from agents.calendar_intelligence import (
    CalendarIntelligenceAgent,
    CalendarIntelligenceExecutor,
    CalendarIntelligenceRequestHandler,
    CalendarData,
    MultiSourceCollector,
    DataVerifier,
    CalendarBuilder,
    create_calendar_intelligence_agent
)
from a2a.types import (
    Message,
    MessageSendParams,
    Part,
    TextPart,
    TaskState,
    TaskQueryParams
)


@pytest.fixture
def calendar_intelligence_agent():
    """Create test calendar intelligence agent"""
    return create_calendar_intelligence_agent()


@pytest.fixture
def calendar_intelligence_executor():
    """Create test calendar intelligence executor"""
    return CalendarIntelligenceExecutor()


@pytest.fixture
def calendar_intelligence_handler(calendar_intelligence_executor):
    """Create test calendar intelligence request handler"""
    return CalendarIntelligenceRequestHandler(calendar_intelligence_executor)


@pytest.fixture
def multi_source_collector():
    """Create test multi-source collector"""
    return MultiSourceCollector()


@pytest.fixture
def data_verifier():
    """Create test data verifier"""
    return DataVerifier()


@pytest.fixture
def calendar_builder():
    """Create test calendar builder"""
    return CalendarBuilder()


class TestCalendarData:
    """Test CalendarData functionality"""
    
    def test_calendar_data_initialization(self):
        """Test CalendarData initializes correctly"""
        date = datetime(2025, 7, 15)
        location = "San Francisco"
        
        calendar_data = CalendarData(date, location)
        
        assert calendar_data.date == date
        assert calendar_data.location == location
        assert calendar_data.events == []
        assert calendar_data.weather == {}
        assert calendar_data.holidays == []
        assert calendar_data.opportunity_score == 50
    
    def test_calculate_opportunity_score_basic(self):
        """Test basic opportunity score calculation"""
        date = datetime(2025, 7, 15)
        calendar_data = CalendarData(date, "Test City")
        
        # Add some events
        calendar_data.events = [
            {"name": "Event 1", "category": "music"},
            {"name": "Event 2", "category": "food"}
        ]
        
        # Set good weather
        calendar_data.weather = {"condition": "sunny"}
        
        # Add holiday
        calendar_data.holidays = ["Summer Festival"]
        
        score = calendar_data.calculate_opportunity_score()
        
        # Should be base (50) + events (4) + weather (15) + holiday (25) = 94
        assert score >= 90  # Allow some flexibility
        assert calendar_data.opportunity_score == score
    
    def test_calculate_opportunity_score_poor_conditions(self):
        """Test opportunity score with poor conditions"""
        date = datetime(2025, 7, 15)
        calendar_data = CalendarData(date, "Test City")
        
        # No events, bad weather, no holidays
        calendar_data.weather = {"condition": "rainy"}
        calendar_data.cultural_significance = "low"
        calendar_data.historical_engagement = 0.2
        
        score = calendar_data.calculate_opportunity_score()
        
        # Should be relatively low (base + low historical)
        assert score < 70
    
    def test_to_dict(self):
        """Test conversion to dictionary"""
        date = datetime(2025, 7, 15)
        calendar_data = CalendarData(date, "Test City")
        calendar_data.events = [{"name": "Test Event"}]
        calendar_data.weather = {"condition": "sunny"}
        calendar_data.holidays = ["Test Holiday"]
        
        data_dict = calendar_data.to_dict()
        
        assert data_dict["date"] == date.isoformat()
        assert data_dict["location"] == "Test City"
        assert data_dict["events"] == [{"name": "Test Event"}]
        assert data_dict["weather"] == {"condition": "sunny"}
        assert data_dict["holidays"] == ["Test Holiday"]
        assert "opportunity_score" in data_dict


class TestMultiSourceCollector:
    """Test MultiSourceCollector functionality"""
    
    @pytest.mark.asyncio
    async def test_collect_events(self, multi_source_collector):
        """Test event collection"""
        location = "San Francisco"
        date = datetime(2025, 7, 15)
        
        events = await multi_source_collector.collect_events(location, date)
        
        assert isinstance(events, list)
        assert len(events) >= 1
        
        # Check event structure
        for event in events:
            assert "name" in event
            assert "description" in event
            assert "location" in event
            assert "start_time" in event
            assert "end_time" in event
            assert location in event["location"]
    
    @pytest.mark.asyncio
    async def test_collect_weather(self, multi_source_collector):
        """Test weather collection"""
        location = "New York"
        date = datetime(2025, 7, 15)
        
        weather = await multi_source_collector.collect_weather(location, date)
        
        assert isinstance(weather, dict)
        assert "condition" in weather
        assert "temperature" in weather
        assert weather["condition"] in ["clear", "sunny", "partly_cloudy", "cloudy", "rainy"]
        assert isinstance(weather["temperature"], int)
    
    @pytest.mark.asyncio
    async def test_collect_holidays(self, multi_source_collector):
        """Test holiday collection"""
        location = "Test City"
        
        # Test known holiday date
        holiday_date = datetime(2025, 12, 25)  # Christmas
        holidays = await multi_source_collector.collect_holidays(location, holiday_date)
        
        assert isinstance(holidays, list)
        # Christmas should be detected
        assert any("Christmas" in holiday for holiday in holidays)
        
        # Test non-holiday date
        regular_date = datetime(2025, 3, 15)
        holidays = await multi_source_collector.collect_holidays(location, regular_date)
        
        assert isinstance(holidays, list)
        # Should be empty or very few holidays
        assert len(holidays) <= 1


class TestDataVerifier:
    """Test DataVerifier functionality"""
    
    @pytest.mark.asyncio
    async def test_verify_events_valid(self, data_verifier):
        """Test verification of valid events"""
        events = [
            {
                "name": "Test Event",
                "location": "Test Location",
                "start_time": "2025-07-15T10:00:00",
                "end_time": "2025-07-15T12:00:00"
            },
            {
                "name": "Another Event",
                "location": "Another Location",
                "start_time": "2025-07-16T14:00:00"
            }
        ]
        
        verified_events, confidence = await data_verifier.verify_events(events)
        
        assert len(verified_events) == 2
        assert confidence > 0.7  # Should have good confidence
        
        # Check that confidence scores were added
        for event in verified_events:
            assert "verification_confidence" in event
            assert 0 <= event["verification_confidence"] <= 1
    
    @pytest.mark.asyncio
    async def test_verify_events_invalid(self, data_verifier):
        """Test verification of invalid events"""
        events = [
            {
                "name": "Bad Event",
                # Missing required fields
                "start_time": "invalid-date"
            }
        ]
        
        verified_events, confidence = await data_verifier.verify_events(events)
        
        assert len(verified_events) == 1
        assert confidence < 0.7  # Should have lower confidence
        assert verified_events[0]["verification_confidence"] < 0.7
    
    @pytest.mark.asyncio
    async def test_verify_weather(self, data_verifier):
        """Test weather verification"""
        # Valid weather
        valid_weather = {
            "condition": "sunny",
            "temperature": 25,
            "humidity": 60
        }
        
        verified_weather, confidence = await data_verifier.verify_weather(valid_weather)
        
        assert confidence > 0.8
        assert "verification_confidence" in verified_weather
        
        # Invalid weather
        invalid_weather = {
            "temperature": 150  # Extreme temperature
        }
        
        verified_weather, confidence = await data_verifier.verify_weather(invalid_weather)
        
        assert confidence < 0.7


class TestCalendarBuilder:
    """Test CalendarBuilder functionality"""
    
    @pytest.mark.asyncio
    async def test_build_calendar_data(self, calendar_builder):
        """Test calendar data building"""
        location = "Test City"
        date = datetime(2025, 7, 15)
        events = [
            {"name": "Event 1", "category": "music"},
            {"name": "Event 2", "category": "food"},
            {"name": "Event 3", "category": "art"}
        ]
        weather = {"condition": "sunny", "temperature": 25}
        holidays = ["Summer Festival"]
        
        calendar_data = await calendar_builder.build_calendar_data(
            location, date, events, weather, holidays
        )
        
        assert isinstance(calendar_data, CalendarData)
        assert calendar_data.location == location
        assert calendar_data.date == date
        assert calendar_data.events == events
        assert calendar_data.weather == weather
        assert calendar_data.holidays == holidays
        assert calendar_data.cultural_significance == "high"  # Has holidays
        assert calendar_data.opportunity_score > 50  # Should be above baseline
    
    @pytest.mark.asyncio
    async def test_build_calendar_data_minimal(self, calendar_builder):
        """Test calendar data building with minimal data"""
        location = "Test City"
        date = datetime(2025, 7, 20)  # Not payday
        events = []
        weather = {"condition": "cloudy"}
        holidays = []
        
        calendar_data = await calendar_builder.build_calendar_data(
            location, date, events, weather, holidays
        )
        
        assert calendar_data.cultural_significance == "low"
        assert not calendar_data.is_payday
        assert calendar_data.opportunity_score <= 70  # Should be lower without events/holidays


class TestCalendarIntelligenceExecutor:
    """Test CalendarIntelligenceExecutor functionality"""
    
    @pytest.mark.asyncio
    async def test_get_calendar_data(self, calendar_intelligence_executor):
        """Test getting calendar data"""
        params = {
            "location": "San Francisco",
            "date": "2025-07-15"
        }
        
        result = await calendar_intelligence_executor._get_calendar_data(params)
        
        assert "calendar_data" in result
        assert "verification_scores" in result
        assert "data_sources" in result
        
        calendar_data = result["calendar_data"]
        assert calendar_data["location"] == "San Francisco"
        assert calendar_data["date"] == "2025-07-15T00:00:00"
        assert "events" in calendar_data
        assert "weather" in calendar_data
        assert "opportunity_score" in calendar_data
    
    @pytest.mark.asyncio
    async def test_get_calendar_data_no_date(self, calendar_intelligence_executor):
        """Test getting calendar data without date (should use today)"""
        params = {"location": "New York"}
        
        result = await calendar_intelligence_executor._get_calendar_data(params)
        
        assert "calendar_data" in result
        calendar_data = result["calendar_data"]
        assert calendar_data["location"] == "New York"
        
        # Should use today's date
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        assert calendar_data["date"] == today.isoformat()
    
    @pytest.mark.asyncio
    async def test_get_calendar_data_missing_location(self, calendar_intelligence_executor):
        """Test error handling for missing location"""
        params = {"date": "2025-07-15"}
        
        with pytest.raises(ValueError, match="Location parameter is required"):
            await calendar_intelligence_executor._get_calendar_data(params)
    
    @pytest.mark.asyncio
    async def test_get_marketing_insights(self, calendar_intelligence_executor):
        """Test getting marketing insights"""
        params = {
            "location": "London",
            "start_date": "2025-07-15",
            "end_date": "2025-07-17"
        }
        
        result = await calendar_intelligence_executor._get_marketing_insights(params)
        
        assert "location" in result
        assert "date_range" in result
        assert "insights" in result
        assert "summary" in result
        
        assert result["location"] == "London"
        assert len(result["insights"]) == 3  # 3 days
        
        # Check insights structure
        for insight in result["insights"]:
            assert "date" in insight
            assert "opportunity_score" in insight
            assert "events_count" in insight
            assert "weather_condition" in insight
        
        # Check summary
        summary = result["summary"]
        assert "average_opportunity_score" in summary
        assert "best_opportunities" in summary
        assert len(summary["best_opportunities"]) <= 3
    
    @pytest.mark.asyncio
    async def test_analyze_opportunity(self, calendar_intelligence_executor):
        """Test opportunity analysis"""
        params = {
            "location": "Berlin",
            "date": "2025-07-15",
            "criteria": {
                "target_audience": "families",
                "campaign_type": "outdoor"
            }
        }
        
        result = await calendar_intelligence_executor._analyze_opportunity(params)
        
        assert "location" in result
        assert "date" in result
        assert "base_opportunity_score" in result
        assert "factors" in result
        assert "recommendations" in result
        
        assert result["location"] == "Berlin"
        
        # Check factors structure
        factors = result["factors"]
        assert "events" in factors
        assert "weather" in factors
        assert "cultural" in factors


class TestCalendarIntelligenceRequestHandler:
    """Test CalendarIntelligenceRequestHandler functionality"""
    
    @pytest.mark.asyncio
    async def test_on_message_send_json_input(self, calendar_intelligence_handler):
        """Test message handling with JSON input"""
        message_data = {
            "location": "Paris",
            "date": "2025-07-15"
        }
        
        params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(
                            text=json.dumps(message_data)
                        )
                    )
                ]
            )
        )
        
        response = await calendar_intelligence_handler.on_message_send(params)
        
        assert response.role == "agent"
        assert len(response.parts) == 1
        
        # Parse response
        response_data = json.loads(response.parts[0].root.text)
        assert "calendar_data" in response_data
        assert response_data["calendar_data"]["location"] == "Paris"
    
    @pytest.mark.asyncio
    async def test_on_message_send_text_input(self, calendar_intelligence_handler):
        """Test message handling with plain text input"""
        params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(
                            text="Tokyo"
                        )
                    )
                ]
            )
        )
        
        response = await calendar_intelligence_handler.on_message_send(params)
        
        assert response.role == "agent"
        response_data = json.loads(response.parts[0].root.text)
        assert response_data["calendar_data"]["location"] == "Tokyo"
    
    @pytest.mark.asyncio
    async def test_on_message_send_insights_request(self, calendar_intelligence_handler):
        """Test message handling for insights request"""
        message_data = {
            "location": "Sydney",
            "request_type": "insights",
            "start_date": "2025-07-15",
            "end_date": "2025-07-16"
        }
        
        params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(
                            text=json.dumps(message_data)
                        )
                    )
                ]
            )
        )
        
        response = await calendar_intelligence_handler.on_message_send(params)
        
        response_data = json.loads(response.parts[0].root.text)
        assert "insights" in response_data
        assert "summary" in response_data
        assert response_data["location"] == "Sydney"


class TestCalendarIntelligenceAgent:
    """Test CalendarIntelligenceAgent functionality"""
    
    def test_agent_initialization(self, calendar_intelligence_agent):
        """Test agent initializes correctly"""
        assert calendar_intelligence_agent.name == "Calendar Intelligence"
        assert calendar_intelligence_agent.version == "1.0.0"
        assert len(calendar_intelligence_agent.skills) == 3
        
        skill_ids = [skill.id for skill in calendar_intelligence_agent.skills]
        assert "get_calendar_data" in skill_ids
        assert "get_marketing_insights" in skill_ids
        assert "analyze_opportunity" in skill_ids
    
    def test_agent_card_structure(self, calendar_intelligence_agent):
        """Test agent card is properly structured"""
        card = calendar_intelligence_agent.agent_card
        assert card.name == "Calendar Intelligence"
        assert "intelligent calendar analysis" in card.description
        assert card.url == "http://localhost:8002"
        assert "application/json" in card.defaultOutputModes
        assert len(card.skills) == 3
    
    def test_build_fastapi_app(self, calendar_intelligence_agent):
        """Test FastAPI app can be built"""
        app = calendar_intelligence_agent.build_fastapi_app()
        assert app is not None
        assert hasattr(app, 'routes')


class TestIntegration:
    """Integration tests for CalendarIntelligenceAgent"""
    
    @pytest.mark.asyncio
    async def test_full_calendar_intelligence_flow(self):
        """Test complete calendar intelligence flow"""
        agent = create_calendar_intelligence_agent()
        
        # Test calendar data request
        message_data = {
            "location": "Berlin",
            "date": "2025-07-15"
        }
        
        params = MessageSendParams(
            message=Message(
                messageId=str(uuid4()),
                role="user",
                parts=[
                    Part(
                        root=TextPart(
                            text=json.dumps(message_data)
                        )
                    )
                ]
            )
        )
        
        response = await agent.request_handler.on_message_send(params)
        
        # Verify response
        assert response.role == "agent"
        response_data = json.loads(response.parts[0].root.text)
        
        assert "calendar_data" in response_data
        calendar_data = response_data["calendar_data"]
        
        assert calendar_data["location"] == "Berlin"
        assert calendar_data["date"] == "2025-07-15T00:00:00"
        assert "opportunity_score" in calendar_data
        assert "events" in calendar_data
        assert "weather" in calendar_data
        
        # Verify verification scores
        assert "verification_scores" in response_data
        verification = response_data["verification_scores"]
        assert "events_confidence" in verification
        assert "weather_confidence" in verification


if __name__ == "__main__":
    pytest.main([__file__, "-v"])