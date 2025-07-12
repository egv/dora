"""Integration tests for database repositories with real database connections."""

import pytest
import asyncio
import os
from datetime import datetime, date, timedelta
from typing import Dict, Any

from dora.database.connections import DatabaseManager, initialize_database_manager
from dora.database.repositories.event_repository import EventRepository
from dora.database.repositories.weather_repository import WeatherRepository, WeatherData
from dora.database.repositories.calendar_insights_repository import CalendarInsightsRepository, CalendarInsights
from dora.models.database_event import Event
from dora.models.config import DoraConfig


# Skip integration tests if no database available
DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql://dora:dora_password@localhost:5432/dora_test")
REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1")

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS", False),
    reason="Integration tests skipped. Set RUN_INTEGRATION_TESTS=1 to run."
)


@pytest.fixture
async def db_manager():
    """Create a database manager for integration tests."""
    config = DoraConfig(
        database_url=DATABASE_URL,
        redis_url=REDIS_URL,
        db_pool_size=3,
        redis_pool_size=3
    )
    
    manager = await initialize_database_manager(config)
    
    # Verify connections
    health = await manager.health_check()
    if health["overall"] != "healthy":
        pytest.skip(f"Database not available: {health}")
    
    yield manager
    
    await manager.cleanup()


@pytest.fixture
async def event_repo(db_manager):
    """Create event repository."""
    return EventRepository(db_manager)


@pytest.fixture
async def weather_repo(db_manager):
    """Create weather repository."""
    return WeatherRepository(db_manager)


@pytest.fixture
async def insights_repo(db_manager):
    """Create calendar insights repository."""
    return CalendarInsightsRepository(db_manager)


@pytest.fixture
def sample_event_data():
    """Sample event data for testing."""
    return Event(
        event_id="integration_test_event_001",
        name="Integration Test Event",
        description="An event created during integration testing",
        location="Test City, Test State",
        start_time=datetime.now() + timedelta(days=1),
        end_time=datetime.now() + timedelta(days=1, hours=2),
        category="integration_test",
        attendance_estimate=150,
        source="integration_test",
        url="https://example.com/integration-test"
    )


@pytest.fixture
def sample_weather_data():
    """Sample weather data for testing."""
    return WeatherData(
        location="Test City, Test State",
        date=date.today() + timedelta(days=1),
        temperature=25.5,
        weather_condition="sunny",
        humidity=55.0,
        wind_speed=8.5,
        precipitation=0.0
    )


@pytest.fixture
def sample_insights_data():
    """Sample insights data for testing."""
    return CalendarInsights(
        location="Test City, Test State",
        insight_date=date.today() + timedelta(days=1),
        insights={"test": "integration", "analysis": "automated"},
        opportunity_score=0.82,
        marketing_recommendations=["Integration test recommendation"],
        conflict_warnings=[],
        weather_impact="positive",
        event_density="low",
        peak_hours=["14:00", "16:00"],
        generated_by="integration_test_agent",
        confidence_score=0.95
    )


class TestEventRepositoryIntegration:
    """Integration tests for EventRepository."""
    
    @pytest.mark.asyncio
    async def test_event_crud_operations(self, event_repo, sample_event_data):
        """Test complete CRUD operations for events."""
        # Create
        created_event = await event_repo.create(sample_event_data)
        assert created_event.id is not None
        assert created_event.event_id == sample_event_data.event_id
        assert created_event.name == sample_event_data.name
        
        # Read
        found_event = await event_repo.find_by_event_id(sample_event_data.event_id)
        assert found_event is not None
        assert found_event.event_id == sample_event_data.event_id
        
        # Update
        updated_event = await event_repo.update(created_event.id, {
            "description": "Updated during integration test"
        })
        assert updated_event is not None
        assert updated_event.description == "Updated during integration test"
        
        # Delete
        deleted = await event_repo.delete(created_event.id)
        assert deleted is True
        
        # Verify deletion
        not_found = await event_repo.find_by_event_id(sample_event_data.event_id)
        assert not_found is None
    
    @pytest.mark.asyncio
    async def test_event_search_functionality(self, event_repo, sample_event_data):
        """Test event search capabilities."""
        # Create test event
        created_event = await event_repo.create(sample_event_data)
        
        try:
            # Search by query
            results = await event_repo.search_events(
                query="Integration",
                location="Test City",
                category="integration_test"
            )
            assert len(results) >= 1
            assert any(e.event_id == sample_event_data.event_id for e in results)
            
            # Search by location and date range
            start_date = datetime.now()
            end_date = datetime.now() + timedelta(days=2)
            location_results = await event_repo.find_by_location_and_date_range(
                "Test City", start_date, end_date
            )
            assert len(location_results) >= 1
            
        finally:
            # Cleanup
            await event_repo.delete(created_event.id)
    
    @pytest.mark.asyncio
    async def test_event_statistics(self, event_repo, sample_event_data):
        """Test event statistics generation."""
        # Create test event
        created_event = await event_repo.create(sample_event_data)
        
        try:
            # Get statistics
            stats = await event_repo.get_events_stats(location="Test City")
            
            assert isinstance(stats, dict)
            assert "total_events" in stats
            assert "categories" in stats
            assert "sources" in stats
            assert stats["total_events"] >= 1
            
        finally:
            # Cleanup
            await event_repo.delete(created_event.id)


class TestWeatherRepositoryIntegration:
    """Integration tests for WeatherRepository."""
    
    @pytest.mark.asyncio
    async def test_weather_upsert_operations(self, weather_repo, sample_weather_data):
        """Test weather upsert functionality."""
        # First upsert (insert)
        result1 = await weather_repo.upsert_weather(sample_weather_data)
        assert result1.location == sample_weather_data.location
        assert result1.temperature == sample_weather_data.temperature
        
        # Second upsert (update)
        sample_weather_data.temperature = 28.0
        sample_weather_data.weather_condition = "partly_cloudy"
        result2 = await weather_repo.upsert_weather(sample_weather_data)
        
        assert result2.temperature == 28.0
        assert result2.weather_condition == "partly_cloudy"
        
        # Cleanup - delete test data
        async with weather_repo.db_manager.get_postgres_connection() as conn:
            await conn.execute(
                "DELETE FROM weather_data WHERE location = $1 AND date = $2",
                sample_weather_data.location, sample_weather_data.date
            )
    
    @pytest.mark.asyncio
    async def test_weather_search_and_stats(self, weather_repo, sample_weather_data):
        """Test weather search and statistics."""
        # Create test weather data
        await weather_repo.upsert_weather(sample_weather_data)
        
        try:
            # Find by location and date
            found_weather = await weather_repo.find_by_location_and_date(
                sample_weather_data.location, sample_weather_data.date
            )
            assert found_weather is not None
            assert found_weather.temperature == sample_weather_data.temperature
            
            # Find by temperature range
            temp_results = await weather_repo.find_by_temperature_range(
                20.0, 30.0, location=sample_weather_data.location
            )
            assert len(temp_results) >= 1
            
            # Get statistics
            stats = await weather_repo.get_weather_stats(
                location=sample_weather_data.location
            )
            assert isinstance(stats, dict)
            assert "total_records" in stats
            assert stats["total_records"] >= 1
            
        finally:
            # Cleanup
            async with weather_repo.db_manager.get_postgres_connection() as conn:
                await conn.execute(
                    "DELETE FROM weather_data WHERE location = $1 AND date = $2",
                    sample_weather_data.location, sample_weather_data.date
                )
    
    @pytest.mark.asyncio
    async def test_weather_caching(self, weather_repo, sample_weather_data):
        """Test weather data caching."""
        # Store weather data
        await weather_repo.upsert_weather(sample_weather_data)
        
        try:
            # Cache the weather data
            await weather_repo.cache_weather(
                sample_weather_data.location,
                sample_weather_data.date,
                sample_weather_data,
                expiry=60
            )
            
            # Retrieve from cache
            cached_weather = await weather_repo.get_cached_weather(
                sample_weather_data.location,
                sample_weather_data.date
            )
            
            assert cached_weather is not None
            assert cached_weather.temperature == sample_weather_data.temperature
            
            # Clear cache
            cleared_count = await weather_repo.clear_weather_cache(
                sample_weather_data.location
            )
            assert cleared_count >= 0
            
        finally:
            # Cleanup
            async with weather_repo.db_manager.get_postgres_connection() as conn:
                await conn.execute(
                    "DELETE FROM weather_data WHERE location = $1 AND date = $2",
                    sample_weather_data.location, sample_weather_data.date
                )


class TestCalendarInsightsRepositoryIntegration:
    """Integration tests for CalendarInsightsRepository."""
    
    @pytest.mark.asyncio
    async def test_insights_upsert_operations(self, insights_repo, sample_insights_data):
        """Test insights upsert functionality."""
        # First upsert (insert)
        result1 = await insights_repo.upsert_insights(sample_insights_data)
        assert result1.location == sample_insights_data.location
        assert result1.opportunity_score == sample_insights_data.opportunity_score
        
        # Second upsert (update)
        sample_insights_data.opportunity_score = 0.95
        sample_insights_data.confidence_score = 0.88
        result2 = await insights_repo.upsert_insights(sample_insights_data)
        
        assert result2.opportunity_score == 0.95
        assert result2.confidence_score == 0.88
        
        # Cleanup
        async with insights_repo.db_manager.get_postgres_connection() as conn:
            await conn.execute(
                "DELETE FROM calendar_insights WHERE location = $1 AND insight_date = $2",
                sample_insights_data.location, sample_insights_data.insight_date
            )
    
    @pytest.mark.asyncio
    async def test_insights_search_functionality(self, insights_repo, sample_insights_data):
        """Test insights search capabilities."""
        # Create test insights
        await insights_repo.upsert_insights(sample_insights_data)
        
        try:
            # Find by location and date
            found_insights = await insights_repo.find_by_location_and_date(
                sample_insights_data.location, sample_insights_data.insight_date
            )
            assert found_insights is not None
            assert found_insights.opportunity_score == sample_insights_data.opportunity_score
            
            # Find high opportunity insights
            high_opp = await insights_repo.find_high_opportunity_insights(
                threshold=0.8, location=sample_insights_data.location
            )
            assert len(high_opp) >= 1
            
            # Find by opportunity score range
            score_range = await insights_repo.find_by_opportunity_score_range(
                0.7, 1.0, location=sample_insights_data.location
            )
            assert len(score_range) >= 1
            
        finally:
            # Cleanup
            async with insights_repo.db_manager.get_postgres_connection() as conn:
                await conn.execute(
                    "DELETE FROM calendar_insights WHERE location = $1 AND insight_date = $2",
                    sample_insights_data.location, sample_insights_data.insight_date
                )
    
    @pytest.mark.asyncio
    async def test_insights_statistics(self, insights_repo, sample_insights_data):
        """Test insights statistics generation."""
        # Create test insights
        await insights_repo.upsert_insights(sample_insights_data)
        
        try:
            # Get statistics
            stats = await insights_repo.get_insights_stats(
                location=sample_insights_data.location
            )
            
            assert isinstance(stats, dict)
            assert "total_insights" in stats
            assert "opportunity_score" in stats
            assert "generator_distribution" in stats
            assert stats["total_insights"] >= 1
            
        finally:
            # Cleanup
            async with insights_repo.db_manager.get_postgres_connection() as conn:
                await conn.execute(
                    "DELETE FROM calendar_insights WHERE location = $1 AND insight_date = $2",
                    sample_insights_data.location, sample_insights_data.insight_date
                )


class TestCrossRepositoryIntegration:
    """Test interactions between multiple repositories."""
    
    @pytest.mark.asyncio
    async def test_multi_repository_workflow(self, event_repo, weather_repo, insights_repo, 
                                           sample_event_data, sample_weather_data, sample_insights_data):
        """Test a complete workflow using all repositories."""
        created_event = None
        
        try:
            # Step 1: Create an event
            created_event = await event_repo.create(sample_event_data)
            assert created_event.id is not None
            
            # Step 2: Add weather data for the same location/date
            weather_result = await weather_repo.upsert_weather(sample_weather_data)
            assert weather_result.location == sample_weather_data.location
            
            # Step 3: Generate insights for the location/date
            insights_result = await insights_repo.upsert_insights(sample_insights_data)
            assert insights_result.location == sample_insights_data.location
            
            # Step 4: Verify all data is consistent
            events = await event_repo.find_by_location_and_date_range(
                sample_event_data.location,
                sample_event_data.start_time,
                sample_event_data.end_time
            )
            
            weather = await weather_repo.find_by_location_and_date(
                sample_weather_data.location,
                sample_weather_data.date
            )
            
            insights = await insights_repo.find_by_location_and_date(
                sample_insights_data.location,
                sample_insights_data.insight_date
            )
            
            assert len(events) >= 1
            assert weather is not None
            assert insights is not None
            
            # All should be for the same location
            assert events[0].location == weather.location == insights.location
            
        finally:
            # Cleanup all test data
            if created_event:
                await event_repo.delete(created_event.id)
            
            async with weather_repo.db_manager.get_postgres_connection() as conn:
                await conn.execute(
                    "DELETE FROM weather_data WHERE location = $1 AND date = $2",
                    sample_weather_data.location, sample_weather_data.date
                )
                await conn.execute(
                    "DELETE FROM calendar_insights WHERE location = $1 AND insight_date = $2",
                    sample_insights_data.location, sample_insights_data.insight_date
                )


class TestDatabaseHealthAndConnectivity:
    """Test database health and connectivity."""
    
    @pytest.mark.asyncio
    async def test_database_health_check(self, db_manager):
        """Test database health check functionality."""
        health = await db_manager.health_check()
        
        assert isinstance(health, dict)
        assert "postgres" in health
        assert "redis" in health
        assert "overall" in health
        
        assert health["postgres"]["status"] == "healthy"
        assert health["redis"]["status"] == "healthy"
        assert health["overall"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_connection_pool_stats(self, db_manager):
        """Test connection pool statistics."""
        postgres_stats = await db_manager.get_postgres_pool_stats()
        redis_info = await db_manager.get_redis_info()
        
        assert postgres_stats["status"] == "initialized"
        assert "size" in postgres_stats
        assert "max_size" in postgres_stats
        
        assert redis_info["status"] == "connected"
        assert "version" in redis_info