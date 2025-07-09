"""
Tests for Enhanced Calendar Builder functionality
"""

import pytest
from datetime import datetime, timedelta
from agents.enhanced_calendar_builder import EnhancedCalendarBuilder, EventConflict, CalendarLayer
from models.calendar_data import CalendarData


class TestEnhancedCalendarBuilder:
    """Test the enhanced calendar builder"""

    @pytest.fixture
    def builder(self):
        """Create an enhanced calendar builder instance"""
        return EnhancedCalendarBuilder()

    @pytest.fixture
    def sample_events(self):
        """Sample events for testing"""
        return [
            {
                "name": "Morning Market",
                "location": "Town Square",
                "start_time": "2025-07-10T09:00:00",
                "end_time": "2025-07-10T12:00:00",
                "category": "market",
                "attendance_estimate": 300,
                "verification_confidence": 0.9
            },
            {
                "name": "Afternoon Concert",
                "location": "Music Hall",
                "start_time": "2025-07-10T15:00:00",
                "end_time": "2025-07-10T17:30:00",
                "category": "music",
                "attendance_estimate": 500,
                "verification_confidence": 0.8
            },
            {
                "name": "Evening Food Festival",
                "location": "Town Square",
                "start_time": "2025-07-10T11:30:00",  # Overlaps with market
                "end_time": "2025-07-10T14:00:00",
                "category": "food",
                "attendance_estimate": 400,
                "verification_confidence": 0.7
            }
        ]

    @pytest.fixture
    def sample_weather(self):
        """Sample weather data"""
        return {
            "condition": "sunny",
            "temperature": 25,
            "humidity": 65,
            "verification_confidence": 0.95
        }

    @pytest.fixture
    def sample_holidays(self):
        """Sample holidays"""
        return ["Independence Day"]

    @pytest.mark.asyncio
    async def test_build_calendar_data_basic(self, builder, sample_events, sample_weather, sample_holidays):
        """Test basic calendar data building"""
        test_date = datetime(2025, 7, 10, 12, 0, 0)
        location = "New York"
        
        calendar_data = await builder.build_calendar_data(
            location=location,
            date=test_date,
            events=sample_events,
            weather=sample_weather,
            holidays=sample_holidays
        )
        
        assert isinstance(calendar_data, CalendarData)
        assert calendar_data.location == location
        assert calendar_data.date == test_date
        assert len(calendar_data.events) == len(sample_events)
        assert calendar_data.weather == sample_weather
        assert calendar_data.holidays == sample_holidays
        assert calendar_data.metadata is not None

    @pytest.mark.asyncio
    async def test_conflict_detection(self, builder, sample_events):
        """Test conflict detection between events"""
        test_date = datetime(2025, 7, 10, 12, 0, 0)
        
        # Process events first
        processed_events = await builder._process_events(sample_events, test_date)
        
        # Detect conflicts
        conflicts = await builder._detect_conflicts(processed_events)
        
        # Should detect overlap between Morning Market and Evening Food Festival
        assert len(conflicts) > 0
        conflict_types = [c.conflict_type for c in conflicts]
        assert 'time_overlap' in conflict_types or 'location_conflict' in conflict_types

    @pytest.mark.asyncio
    async def test_conflict_resolution(self, builder, sample_events):
        """Test conflict resolution"""
        test_date = datetime(2025, 7, 10, 12, 0, 0)
        
        # Process events and detect conflicts
        processed_events = await builder._process_events(sample_events, test_date)
        conflicts = await builder._detect_conflicts(processed_events)
        
        # Resolve conflicts
        resolved_events = await builder._resolve_conflicts(processed_events, conflicts)
        
        # Should have resolution strategies for conflicts
        resolved_conflicts = [c for c in conflicts if c.resolution_strategy]
        assert len(resolved_conflicts) > 0

    @pytest.mark.asyncio
    async def test_event_processing(self, builder):
        """Test event processing and normalization"""
        test_date = datetime(2025, 7, 10, 12, 0, 0)
        
        # Event without end time
        events = [
            {
                "name": "Test Event",
                "location": "Test Location",
                "start_time": "2025-07-10T14:00:00",
                "category": "music"
            }
        ]
        
        processed_events = await builder._process_events(events, test_date)
        
        assert len(processed_events) == 1
        event = processed_events[0]
        
        # Should have generated end time
        assert 'end_time' in event
        assert event['end_time'] is not None
        
        # Should have added ID
        assert 'id' in event
        
        # Should have processing metadata
        assert event.get('_processed') is True
        assert '_start_dt' in event
        assert '_end_dt' in event

    @pytest.mark.asyncio
    async def test_cultural_significance_calculation(self, builder):
        """Test cultural significance calculation"""
        test_date = datetime(2025, 7, 10, 12, 0, 0)
        location = "New York"
        
        # High significance (holidays + many events)
        many_events = [
            {"name": f"Event {i}", "category": f"category_{i % 3}"} 
            for i in range(5)
        ]
        holidays = ["Independence Day"]
        
        significance = await builder._calculate_cultural_significance(
            holidays, many_events, location, test_date
        )
        assert significance in ["low", "medium", "high"]

    @pytest.mark.asyncio
    async def test_event_density_calculation(self, builder, sample_events):
        """Test event density calculation"""
        test_date = datetime(2025, 7, 10, 12, 0, 0)
        processed_events = await builder._process_events(sample_events, test_date)
        
        density = builder._calculate_event_density(processed_events)
        
        # Should be events per hour for 16-hour day
        expected_density = len(processed_events) / 16
        assert density == expected_density

    @pytest.mark.asyncio
    async def test_time_coverage_calculation(self, builder, sample_events):
        """Test time coverage calculation"""
        test_date = datetime(2025, 7, 10, 12, 0, 0)
        processed_events = await builder._process_events(sample_events, test_date)
        
        coverage = builder._calculate_time_coverage(processed_events)
        
        # Should be percentage of day with events
        assert 0 <= coverage <= 1.0

    @pytest.mark.asyncio
    async def test_historical_engagement_calculation(self, builder, sample_events, sample_weather, sample_holidays):
        """Test historical engagement calculation"""
        test_date = datetime(2025, 7, 10, 12, 0, 0)
        
        engagement = await builder._calculate_historical_engagement(
            sample_events, sample_weather, sample_holidays, test_date
        )
        
        assert 0 <= engagement <= 1.0

    @pytest.mark.asyncio
    async def test_days_to_holiday_calculation(self, builder):
        """Test days to holiday calculation"""
        test_date = datetime(2025, 7, 10, 12, 0, 0)
        location = "New York"
        
        days = await builder._calculate_days_to_holiday(location, test_date)
        
        # Should be a reasonable number
        assert 0 <= days <= 365

    @pytest.mark.asyncio
    async def test_payday_detection(self, builder):
        """Test payday detection"""
        # Test various dates
        test_dates = [
            datetime(2025, 7, 1),   # 1st of month
            datetime(2025, 7, 15),  # 15th of month
            datetime(2025, 7, 31),  # Last day of month
            datetime(2025, 7, 10),  # Random day
        ]
        
        for test_date in test_dates:
            is_payday = builder._is_payday(test_date, "New York")
            assert isinstance(is_payday, bool)

    @pytest.mark.asyncio
    async def test_event_priority_scoring(self, builder):
        """Test event priority scoring"""
        high_priority_event = {
            "name": "Major Festival",
            "category": "festival",
            "attendance_estimate": 2000,
            "verification_confidence": 0.9
        }
        
        low_priority_event = {
            "name": "Small Meetup",
            "category": "general",
            "attendance_estimate": 50,
            "verification_confidence": 0.6
        }
        
        high_score = builder._calculate_event_priority_score(high_priority_event)
        low_score = builder._calculate_event_priority_score(low_priority_event)
        
        assert high_score > low_score

    @pytest.mark.asyncio
    async def test_calendar_layers(self, builder):
        """Test calendar layer functionality"""
        # Test layer creation
        assert 'events' in builder.layers
        assert 'weather' in builder.layers
        assert 'holidays' in builder.layers
        
        # Test layer priorities
        assert builder.layers['holidays'].priority > builder.layers['events'].priority
        assert builder.layers['events'].priority > builder.layers['weather'].priority

    @pytest.mark.asyncio
    async def test_query_calendar(self, builder, sample_events, sample_weather, sample_holidays):
        """Test calendar querying functionality"""
        test_date = datetime(2025, 7, 10, 12, 0, 0)
        location = "New York"
        
        # Build calendar data first
        await builder.build_calendar_data(
            location=location,
            date=test_date,
            events=sample_events,
            weather=sample_weather,
            holidays=sample_holidays
        )
        
        # Query calendar
        start_date = datetime(2025, 7, 10, 0, 0, 0)
        end_date = datetime(2025, 7, 10, 23, 59, 59)
        
        results = await builder.query_calendar((start_date, end_date))
        
        assert 'events' in results
        assert 'holidays' in results
        assert 'weather' in results
        assert 'metadata' in results

    @pytest.mark.asyncio
    async def test_update_calendar_event(self, builder, sample_events):
        """Test event updating functionality"""
        test_date = datetime(2025, 7, 10, 12, 0, 0)
        
        # Process events first
        processed_events = await builder._process_events(sample_events, test_date)
        builder._add_events_to_layer(processed_events)
        
        # Update an event
        if processed_events:
            event_id = processed_events[0]['id']
            updates = {"name": "Updated Event Name"}
            
            success = await builder.update_calendar_event(event_id, updates)
            assert success is True

    @pytest.mark.asyncio
    async def test_marketing_opportunities(self, builder, sample_events, sample_weather, sample_holidays):
        """Test marketing opportunity identification"""
        test_date = datetime(2025, 7, 10, 12, 0, 0)
        location = "New York"
        
        # Build calendar data
        calendar_data = await builder.build_calendar_data(
            location=location,
            date=test_date,
            events=sample_events,
            weather=sample_weather,
            holidays=sample_holidays
        )
        
        # Get marketing opportunities
        opportunities = await builder.get_marketing_opportunities(calendar_data)
        
        assert isinstance(opportunities, list)
        
        # Should have opportunities due to holidays and events
        opportunity_types = [opp['type'] for opp in opportunities]
        assert 'holiday_marketing' in opportunity_types

    @pytest.mark.asyncio
    async def test_metadata_generation(self, builder, sample_events, sample_weather, sample_holidays):
        """Test metadata generation in calendar data"""
        test_date = datetime(2025, 7, 10, 12, 0, 0)
        location = "New York"
        
        calendar_data = await builder.build_calendar_data(
            location=location,
            date=test_date,
            events=sample_events,
            weather=sample_weather,
            holidays=sample_holidays
        )
        
        # Check metadata structure
        assert 'metadata' in calendar_data.to_dict()
        metadata = calendar_data.metadata
        
        expected_keys = [
            'conflicts_detected',
            'conflicts_resolved',
            'event_density',
            'time_coverage',
            'consistency_scores',
            'layer_summary'
        ]
        
        for key in expected_keys:
            assert key in metadata

    @pytest.mark.asyncio
    async def test_empty_data_handling(self, builder):
        """Test handling of empty data"""
        test_date = datetime(2025, 7, 10, 12, 0, 0)
        location = "New York"
        
        calendar_data = await builder.build_calendar_data(
            location=location,
            date=test_date,
            events=[],
            weather={},
            holidays=[]
        )
        
        assert calendar_data.events == []
        assert calendar_data.weather == {}
        assert calendar_data.holidays == []
        assert calendar_data.metadata is not None

    @pytest.mark.asyncio
    async def test_consistency_scores_integration(self, builder, sample_events, sample_weather, sample_holidays):
        """Test integration of consistency scores"""
        test_date = datetime(2025, 7, 10, 12, 0, 0)
        location = "New York"
        
        consistency_scores = {
            'event_weather_consistency': 0.8,
            'event_holiday_consistency': 0.9,
            'location_consistency': 0.7,
            'date_consistency': 0.95
        }
        
        calendar_data = await builder.build_calendar_data(
            location=location,
            date=test_date,
            events=sample_events,
            weather=sample_weather,
            holidays=sample_holidays,
            consistency_scores=consistency_scores
        )
        
        assert calendar_data.metadata['consistency_scores'] == consistency_scores


class TestEventConflict:
    """Test event conflict functionality"""

    def test_event_conflict_creation(self):
        """Test event conflict creation"""
        events = [
            {"name": "Event 1", "start_time": "2025-07-10T10:00:00"},
            {"name": "Event 2", "start_time": "2025-07-10T10:30:00"}
        ]
        
        conflict = EventConflict(events, "time_overlap", "medium")
        
        assert conflict.events == events
        assert conflict.conflict_type == "time_overlap"
        assert conflict.severity == "medium"
        assert conflict.resolution_strategy is None

    def test_event_conflict_to_dict(self):
        """Test event conflict serialization"""
        events = [
            {"name": "Event 1"},
            {"name": "Event 2"}
        ]
        
        conflict = EventConflict(events, "time_overlap", "high")
        conflict.resolution_strategy = "prioritized_higher_score_event"
        
        result = conflict.to_dict()
        
        assert result['conflict_type'] == "time_overlap"
        assert result['severity'] == "high"
        assert result['resolution_strategy'] == "prioritized_higher_score_event"
        assert result['conflicting_events'] == ["Event 1", "Event 2"]


class TestCalendarLayer:
    """Test calendar layer functionality"""

    def test_calendar_layer_creation(self):
        """Test calendar layer creation"""
        layer = CalendarLayer("events", priority=50)
        
        assert layer.layer_type == "events"
        assert layer.priority == 50
        assert layer.data == {}
        assert layer.metadata == {}

    def test_calendar_layer_add_item(self):
        """Test adding items to calendar layer"""
        layer = CalendarLayer("events")
        
        layer.add_item("event1", {"name": "Test Event"}, {"source": "test"})
        
        assert "event1" in layer.data
        assert layer.data["event1"]["name"] == "Test Event"
        assert layer.metadata["event1"]["source"] == "test"

    def test_calendar_layer_time_range_query(self):
        """Test querying items by time range"""
        layer = CalendarLayer("events")
        
        # Add items with different start times
        layer.add_item("event1", {
            "name": "Event 1",
            "start_time": "2025-07-10T10:00:00"
        })
        layer.add_item("event2", {
            "name": "Event 2",
            "start_time": "2025-07-10T15:00:00"
        })
        layer.add_item("event3", {
            "name": "Event 3",
            "start_time": "2025-07-11T10:00:00"
        })
        
        # Query for events on 2025-07-10
        start = datetime(2025, 7, 10, 0, 0, 0)
        end = datetime(2025, 7, 10, 23, 59, 59)
        
        items = layer.get_items_for_time_range(start, end)
        
        assert len(items) == 2
        event_names = [item["name"] for item in items]
        assert "Event 1" in event_names
        assert "Event 2" in event_names
        assert "Event 3" not in event_names