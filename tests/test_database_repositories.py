"""Tests for database repositories and data persistence layer."""

import pytest
from datetime import datetime, date, timedelta
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch
import asyncpg

from dora.database.connections import DatabaseManager
from dora.database.repositories.base import BaseRepository
from dora.database.repositories.event_repository import EventRepository
from dora.database.repositories.weather_repository import WeatherRepository, WeatherData
from dora.database.repositories.calendar_insights_repository import CalendarInsightsRepository, CalendarInsights
from dora.models.database_event import Event
from dora.models.config import DoraConfig


@pytest.fixture
def mock_config():
    """Mock Dora configuration."""
    return DoraConfig(
        database_url="postgresql://test:test@localhost:5432/test_db",
        redis_url="redis://localhost:6379/1",
        db_pool_size=5,
        redis_pool_size=5
    )


@pytest.fixture
def mock_db_manager(mock_config):
    """Mock database manager."""
    manager = MagicMock(spec=DatabaseManager)
    manager.config = mock_config
    
    # Mock connection context managers
    mock_conn = AsyncMock()
    manager.get_postgres_connection.return_value.__aenter__.return_value = mock_conn
    manager.get_postgres_transaction.return_value.__aenter__.return_value = mock_conn
    
    # Mock Redis client
    mock_redis = AsyncMock()
    manager.get_redis_client.return_value = mock_redis
    
    return manager


@pytest.fixture
def sample_event():
    """Sample event for testing."""
    return Event(
        event_id="test_event_123",
        name="Test Event",
        description="A test event for pytest",
        location="Test Location",
        start_time=datetime(2024, 1, 15, 14, 0),
        end_time=datetime(2024, 1, 15, 16, 0),
        category="test",
        attendance_estimate=100,
        source="pytest",
        url="https://example.com/event"
    )


@pytest.fixture
def sample_weather():
    """Sample weather data for testing."""
    return WeatherData(
        location="Test Location",
        date=date(2024, 1, 15),
        temperature=22.5,
        weather_condition="sunny",
        humidity=65.0,
        wind_speed=10.5,
        precipitation=0.0
    )


@pytest.fixture
def sample_insights():
    """Sample calendar insights for testing."""
    return CalendarInsights(
        location="Test Location",
        insight_date=date(2024, 1, 15),
        insights={"key": "value", "analysis": "test"},
        opportunity_score=0.85,
        marketing_recommendations=["Recommendation 1", "Recommendation 2"],
        conflict_warnings=["Warning 1"],
        weather_impact="positive",
        event_density="medium",
        peak_hours=["14:00", "15:00"],
        generated_by="test_agent",
        confidence_score=0.9
    )


class TestEventRepository:
    """Test EventRepository functionality."""
    
    def test_init(self, mock_db_manager):
        """Test repository initialization."""
        repo = EventRepository(mock_db_manager)
        assert repo.db_manager == mock_db_manager
        assert repo.table_name == "events"
    
    @pytest.mark.asyncio
    async def test_row_to_model(self, mock_db_manager, sample_event):
        """Test converting database row to Event model."""
        repo = EventRepository(mock_db_manager)
        
        # Mock database row
        mock_row = {
            'id': 1,
            'event_id': sample_event.event_id,
            'name': sample_event.name,
            'description': sample_event.description,
            'location': sample_event.location,
            'start_time': sample_event.start_time,
            'end_time': sample_event.end_time,
            'category': sample_event.category,
            'attendance_estimate': sample_event.attendance_estimate,
            'source': sample_event.source,
            'url': sample_event.url,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        event = repo._row_to_model(mock_row)
        assert event.event_id == sample_event.event_id
        assert event.name == sample_event.name
        assert event.location == sample_event.location
    
    @pytest.mark.asyncio
    async def test_find_by_event_id(self, mock_db_manager, sample_event):
        """Test finding event by event_id."""
        repo = EventRepository(mock_db_manager)
        
        # Mock database response
        mock_conn = mock_db_manager.get_postgres_connection.return_value.__aenter__.return_value
        mock_conn.fetchrow.return_value = {
            'id': 1,
            'event_id': sample_event.event_id,
            'name': sample_event.name,
            'description': sample_event.description,
            'location': sample_event.location,
            'start_time': sample_event.start_time,
            'end_time': sample_event.end_time,
            'category': sample_event.category,
            'attendance_estimate': sample_event.attendance_estimate,
            'source': sample_event.source,
            'url': sample_event.url,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        result = await repo.find_by_event_id(sample_event.event_id)
        
        assert result is not None
        assert result.event_id == sample_event.event_id
        mock_conn.fetchrow.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_find_by_event_id_not_found(self, mock_db_manager):
        """Test finding event by event_id when not found."""
        repo = EventRepository(mock_db_manager)
        
        mock_conn = mock_db_manager.get_postgres_connection.return_value.__aenter__.return_value
        mock_conn.fetchrow.return_value = None
        
        result = await repo.find_by_event_id("nonexistent")
        
        assert result is None
        mock_conn.fetchrow.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_search_events(self, mock_db_manager):
        """Test event search functionality."""
        repo = EventRepository(mock_db_manager)
        
        mock_conn = mock_db_manager.get_postgres_connection.return_value.__aenter__.return_value
        mock_conn.fetch.return_value = []  # Empty result
        
        results = await repo.search_events(
            query="test",
            location="Test Location",
            category="conference"
        )
        
        assert isinstance(results, list)
        mock_conn.fetch.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_bulk_upsert_empty(self, mock_db_manager):
        """Test bulk upsert with empty list."""
        repo = EventRepository(mock_db_manager)
        
        result = await repo.bulk_upsert([])
        
        assert result == {"inserted": 0, "updated": 0}


class TestWeatherRepository:
    """Test WeatherRepository functionality."""
    
    def test_init(self, mock_db_manager):
        """Test repository initialization."""
        repo = WeatherRepository(mock_db_manager)
        assert repo.db_manager == mock_db_manager
        assert repo.table_name == "weather_data"
    
    @pytest.mark.asyncio
    async def test_row_to_model(self, mock_db_manager, sample_weather):
        """Test converting database row to WeatherData model."""
        repo = WeatherRepository(mock_db_manager)
        
        mock_row = {
            'location': sample_weather.location,
            'date': sample_weather.date,
            'temperature': sample_weather.temperature,
            'weather_condition': sample_weather.weather_condition,
            'humidity': sample_weather.humidity,
            'wind_speed': sample_weather.wind_speed,
            'precipitation': sample_weather.precipitation,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        weather = repo._row_to_model(mock_row)
        assert weather.location == sample_weather.location
        assert weather.temperature == sample_weather.temperature
        assert weather.weather_condition == sample_weather.weather_condition
    
    @pytest.mark.asyncio
    async def test_find_by_location_and_date(self, mock_db_manager, sample_weather):
        """Test finding weather by location and date."""
        repo = WeatherRepository(mock_db_manager)
        
        mock_conn = mock_db_manager.get_postgres_connection.return_value.__aenter__.return_value
        mock_conn.fetchrow.return_value = {
            'location': sample_weather.location,
            'date': sample_weather.date,
            'temperature': sample_weather.temperature,
            'weather_condition': sample_weather.weather_condition,
            'humidity': sample_weather.humidity,
            'wind_speed': sample_weather.wind_speed,
            'precipitation': sample_weather.precipitation,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        result = await repo.find_by_location_and_date(
            sample_weather.location, 
            sample_weather.date
        )
        
        assert result is not None
        assert result.location == sample_weather.location
        assert result.date == sample_weather.date
        mock_conn.fetchrow.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_find_by_temperature_range(self, mock_db_manager):
        """Test finding weather by temperature range."""
        repo = WeatherRepository(mock_db_manager)
        
        # Mock the find_by_criteria method
        with patch.object(repo, 'find_by_criteria', return_value=[]):
            results = await repo.find_by_temperature_range(20.0, 25.0)
            
            assert isinstance(results, list)
            repo.find_by_criteria.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_weather_stats(self, mock_db_manager):
        """Test getting weather statistics."""
        repo = WeatherRepository(mock_db_manager)
        
        mock_conn = mock_db_manager.get_postgres_connection.return_value.__aenter__.return_value
        
        # Mock different query results
        mock_conn.fetchrow.side_effect = [
            # Temperature stats
            {
                'total_records': 100,
                'avg_temperature': 22.5,
                'min_temperature': 15.0,
                'max_temperature': 30.0,
                'temp_stddev': 5.2
            },
            # Humidity stats  
            {
                'avg_humidity': 65.0,
                'min_humidity': 40.0,
                'max_humidity': 90.0
            }
        ]
        
        # Mock condition distribution
        mock_conn.fetch.return_value = [
            {'weather_condition': 'sunny', 'count': 60},
            {'weather_condition': 'cloudy', 'count': 30},
            {'weather_condition': 'rainy', 'count': 10}
        ]
        
        stats = await repo.get_weather_stats(location="Test Location")
        
        assert isinstance(stats, dict)
        assert 'total_records' in stats
        assert 'temperature' in stats
        assert 'humidity' in stats
        assert 'conditions' in stats
    
    @pytest.mark.asyncio
    async def test_upsert_weather(self, mock_db_manager, sample_weather):
        """Test upserting weather data."""
        repo = WeatherRepository(mock_db_manager)
        
        mock_conn = mock_db_manager.get_postgres_connection.return_value.__aenter__.return_value
        mock_conn.fetchrow.return_value = {
            'location': sample_weather.location,
            'date': sample_weather.date,
            'temperature': sample_weather.temperature,
            'weather_condition': sample_weather.weather_condition,
            'humidity': sample_weather.humidity,
            'wind_speed': sample_weather.wind_speed,
            'precipitation': sample_weather.precipitation,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        result = await repo.upsert_weather(sample_weather)
        
        assert result is not None
        assert result.location == sample_weather.location
        mock_conn.fetchrow.assert_called_once()


class TestCalendarInsightsRepository:
    """Test CalendarInsightsRepository functionality."""
    
    def test_init(self, mock_db_manager):
        """Test repository initialization."""
        repo = CalendarInsightsRepository(mock_db_manager)
        assert repo.db_manager == mock_db_manager
        assert repo.table_name == "calendar_insights"
    
    @pytest.mark.asyncio
    async def test_row_to_model(self, mock_db_manager, sample_insights):
        """Test converting database row to CalendarInsights model."""
        repo = CalendarInsightsRepository(mock_db_manager)
        
        mock_row = {
            'location': sample_insights.location,
            'insight_date': sample_insights.insight_date,
            'insights': sample_insights.insights,
            'opportunity_score': sample_insights.opportunity_score,
            'marketing_recommendations': sample_insights.marketing_recommendations,
            'conflict_warnings': sample_insights.conflict_warnings,
            'weather_impact': sample_insights.weather_impact,
            'event_density': sample_insights.event_density,
            'peak_hours': sample_insights.peak_hours,
            'generated_by': sample_insights.generated_by,
            'confidence_score': sample_insights.confidence_score,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        insights = repo._row_to_model(mock_row)
        assert insights.location == sample_insights.location
        assert insights.opportunity_score == sample_insights.opportunity_score
        assert insights.weather_impact == sample_insights.weather_impact
    
    @pytest.mark.asyncio
    async def test_find_by_location_and_date(self, mock_db_manager, sample_insights):
        """Test finding insights by location and date."""
        repo = CalendarInsightsRepository(mock_db_manager)
        
        mock_conn = mock_db_manager.get_postgres_connection.return_value.__aenter__.return_value
        mock_conn.fetchrow.return_value = {
            'location': sample_insights.location,
            'insight_date': sample_insights.insight_date,
            'insights': sample_insights.insights,
            'opportunity_score': sample_insights.opportunity_score,
            'marketing_recommendations': sample_insights.marketing_recommendations,
            'conflict_warnings': sample_insights.conflict_warnings,
            'weather_impact': sample_insights.weather_impact,
            'event_density': sample_insights.event_density,
            'peak_hours': sample_insights.peak_hours,
            'generated_by': sample_insights.generated_by,
            'confidence_score': sample_insights.confidence_score,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        result = await repo.find_by_location_and_date(
            sample_insights.location,
            sample_insights.insight_date
        )
        
        assert result is not None
        assert result.location == sample_insights.location
        assert result.insight_date == sample_insights.insight_date
        mock_conn.fetchrow.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_find_high_opportunity_insights(self, mock_db_manager):
        """Test finding high opportunity insights."""
        repo = CalendarInsightsRepository(mock_db_manager)
        
        with patch.object(repo, 'find_by_criteria', return_value=[]):
            results = await repo.find_high_opportunity_insights(
                threshold=0.8,
                location="Test Location"
            )
            
            assert isinstance(results, list)
            repo.find_by_criteria.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_find_insights_with_conflicts(self, mock_db_manager):
        """Test finding insights with conflicts."""
        repo = CalendarInsightsRepository(mock_db_manager)
        
        with patch.object(repo, 'find_by_criteria', return_value=[]):
            results = await repo.find_insights_with_conflicts(location="Test Location")
            
            assert isinstance(results, list)
            repo.find_by_criteria.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_insights_stats(self, mock_db_manager):
        """Test getting insights statistics."""
        repo = CalendarInsightsRepository(mock_db_manager)
        
        mock_conn = mock_db_manager.get_postgres_connection.return_value.__aenter__.return_value
        
        # Mock stats query result
        mock_conn.fetchrow.return_value = {
            'total_insights': 50,
            'avg_opportunity_score': 0.75,
            'min_opportunity_score': 0.2,
            'max_opportunity_score': 0.95,
            'avg_confidence_score': 0.85,
            'insights_with_conflicts': 5
        }
        
        # Mock distribution queries
        mock_conn.fetch.side_effect = [
            [{'event_density': 'high', 'count': 20}, {'event_density': 'medium', 'count': 25}],
            [{'weather_impact': 'positive', 'count': 30}, {'weather_impact': 'neutral', 'count': 20}],
            [{'generated_by': 'agent_1', 'count': 40}, {'generated_by': 'agent_2', 'count': 10}]
        ]
        
        stats = await repo.get_insights_stats(location="Test Location")
        
        assert isinstance(stats, dict)
        assert 'total_insights' in stats
        assert 'opportunity_score' in stats
        assert 'event_density_distribution' in stats
        assert stats['total_insights'] == 50
    
    @pytest.mark.asyncio
    async def test_upsert_insights(self, mock_db_manager, sample_insights):
        """Test upserting insights data."""
        repo = CalendarInsightsRepository(mock_db_manager)
        
        mock_conn = mock_db_manager.get_postgres_connection.return_value.__aenter__.return_value
        mock_conn.fetchrow.return_value = {
            'location': sample_insights.location,
            'insight_date': sample_insights.insight_date,
            'insights': sample_insights.insights,
            'opportunity_score': sample_insights.opportunity_score,
            'marketing_recommendations': sample_insights.marketing_recommendations,
            'conflict_warnings': sample_insights.conflict_warnings,
            'weather_impact': sample_insights.weather_impact,
            'event_density': sample_insights.event_density,
            'peak_hours': sample_insights.peak_hours,
            'generated_by': sample_insights.generated_by,
            'confidence_score': sample_insights.confidence_score,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        result = await repo.upsert_insights(sample_insights)
        
        assert result is not None
        assert result.location == sample_insights.location
        mock_conn.fetchrow.assert_called_once()


class TestCachingFunctionality:
    """Test caching functionality across repositories."""
    
    @pytest.mark.asyncio
    async def test_event_cache_operations(self, mock_db_manager, sample_event):
        """Test event caching operations."""
        repo = EventRepository(mock_db_manager)
        
        mock_redis = mock_db_manager.get_redis_client.return_value
        mock_redis.get.return_value = None  # Cache miss
        
        # Test cache miss
        result = await repo.get_cached_events("Test Location", date.today())
        assert result is None
        
        # Test cache set
        await repo.cache_events("Test Location", date.today(), [sample_event])
        mock_redis.setex.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_weather_cache_operations(self, mock_db_manager, sample_weather):
        """Test weather caching operations."""
        repo = WeatherRepository(mock_db_manager)
        
        mock_redis = mock_db_manager.get_redis_client.return_value
        mock_redis.get.return_value = None  # Cache miss
        
        # Test cache miss
        result = await repo.get_cached_weather("Test Location", date.today())
        assert result is None
        
        # Test cache set
        await repo.cache_weather("Test Location", date.today(), sample_weather)
        mock_redis.setex.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_insights_cache_operations(self, mock_db_manager, sample_insights):
        """Test insights caching operations."""
        repo = CalendarInsightsRepository(mock_db_manager)
        
        mock_redis = mock_db_manager.get_redis_client.return_value
        mock_redis.get.return_value = None  # Cache miss
        
        # Test cache miss
        result = await repo.get_cached_insights("Test Location", date.today())
        assert result is None
        
        # Test cache set
        await repo.cache_insights("Test Location", date.today(), sample_insights)
        mock_redis.setex.assert_called_once()


class TestDataModels:
    """Test data model functionality."""
    
    def test_weather_data_dict(self, sample_weather):
        """Test WeatherData dict conversion."""
        data_dict = sample_weather.dict()
        
        assert isinstance(data_dict, dict)
        assert data_dict['location'] == sample_weather.location
        assert data_dict['temperature'] == sample_weather.temperature
        assert data_dict['weather_condition'] == sample_weather.weather_condition
    
    def test_calendar_insights_dict(self, sample_insights):
        """Test CalendarInsights dict conversion."""
        data_dict = sample_insights.dict()
        
        assert isinstance(data_dict, dict)
        assert data_dict['location'] == sample_insights.location
        assert data_dict['opportunity_score'] == sample_insights.opportunity_score
        assert data_dict['insights'] == sample_insights.insights