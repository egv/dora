"""Tests for Calendar Cache MCP Server."""

import asyncio
import json
import os
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Dict, Any

import redis.asyncio as redis

from dora.mcp.calendar_cache_server import CalendarCacheServer, CalendarCacheEntry


@pytest.fixture
async def mock_redis():
    """Create a mock Redis client for testing."""
    mock_client = AsyncMock(spec=redis.Redis)
    
    # Mock basic Redis operations - all async
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.hset = AsyncMock(return_value=None)
    mock_client.hgetall = AsyncMock(return_value={})
    mock_client.delete = AsyncMock(return_value=0)
    mock_client.exists = AsyncMock(return_value=False)
    mock_client.expire = AsyncMock(return_value=True)
    mock_client.ttl = AsyncMock(return_value=3600)
    mock_client.hincrby = AsyncMock(return_value=1)
    mock_client.zadd = AsyncMock(return_value=1)
    mock_client.close = AsyncMock(return_value=None)
    
    # Mock scan_iter
    async def mock_scan_iter(match=None):
        """Mock scan_iter method."""
        test_keys = [
            "calendar:san_francisco_ca:2025_07_12",
            "calendar:new_york_ny:2025_07_13",
            "calendar:ranking:san_francisco_ca"
        ]
        for key in test_keys:
            if match and not key.startswith(match.replace("*", "")):
                continue
            yield key
    
    mock_client.scan_iter = mock_scan_iter
    
    # Mock info methods
    mock_client.info = AsyncMock(return_value={
        "redis_version": "7.0.0",
        "used_memory_human": "1.2M",
        "used_memory_peak_human": "1.5M",
        "connected_clients": 5
    })
    
    return mock_client


@pytest.fixture
async def cache_server(mock_redis):
    """Create a calendar cache server with mocked Redis."""
    server = CalendarCacheServer(redis_url="redis://localhost:6379/0")
    
    # Mock the connection pool and client
    with patch('redis.asyncio.ConnectionPool.from_url') as mock_pool_from_url, \
         patch('redis.asyncio.Redis') as mock_redis_class:
        
        mock_pool = AsyncMock()
        mock_pool.disconnect = AsyncMock(return_value=None)
        mock_pool_from_url.return_value = mock_pool
        mock_redis_class.return_value = mock_redis
        
        server.redis_pool = mock_pool
        server.redis_client = mock_redis
        
        # Initialize
        await server.initialize()
        
        yield server
        
        # Cleanup
        await server.cleanup()


class TestCalendarCacheServer:
    """Test the calendar cache server functionality."""
    
    @pytest.mark.asyncio
    async def test_initialization(self, cache_server, mock_redis):
        """Test cache server initialization."""
        assert cache_server.redis_client is not None
        assert cache_server.cache_version == "1.0"
        assert cache_server.default_ttl == 86400
        
        # Verify Redis ping was called
        mock_redis.ping.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_cache_key(self, cache_server):
        """Test cache key generation."""
        # Basic key
        key1 = cache_server._generate_cache_key("San Francisco, CA", "2025-07-12")
        assert key1 == "calendar:san_francisco_ca:2025_07_12"
        
        # With categories
        key2 = cache_server._generate_cache_key(
            "New York, NY", "2025-07-12_2025-07-19", ["music", "tech"]
        )
        assert key2 == "calendar:new_york_ny:2025_07_12_2025_07_19:music_tech"
        
        # Normalize spaces and special characters
        key3 = cache_server._generate_cache_key("Los Angeles, CA", "2025-07-12")
        assert key3 == "calendar:los_angeles_ca:2025_07_12"
    
    @pytest.mark.asyncio
    async def test_store_calendar_data(self, cache_server, mock_redis):
        """Test storing calendar data."""
        test_data = {
            "events": [
                {"name": "Test Event", "date": "2025-07-12", "location": "San Francisco"}
            ],
            "weather": {"temperature": 22, "condition": "sunny"},
            "opportunity_score": 85
        }
        
        cache_key = await cache_server.store_calendar_data(
            location="San Francisco, CA",
            date_range="2025-07-12",
            calendar_data=test_data,
            processing_time_ms=150,
            data_sources=["EventSearchAgent", "WeatherAPI"]
        )
        
        # Verify the cache key format
        assert cache_key == "calendar:san_francisco_ca:2025_07_12"
        
        # Verify Redis operations were called
        mock_redis.hset.assert_called()
        mock_redis.expire.assert_called()
        mock_redis.zadd.assert_called()
        mock_redis.hincrby.assert_called()  # For statistics
    
    @pytest.mark.asyncio
    async def test_get_calendar_data_hit(self, cache_server, mock_redis):
        """Test retrieving calendar data from cache (cache hit)."""
        # Mock cached data
        cached_data = {
            "cache_key": "calendar:san_francisco_ca:2025_07_12",
            "location": "San Francisco, CA",
            "date_range": "2025-07-12",
            "calendar_data": json.dumps({"events": [], "opportunity_score": 75}),
            "cached_at": "2025-07-12T10:00:00+00:00",
            "last_accessed": "2025-07-12T10:00:00+00:00",
            "hit_count": "5",
            "processing_time_ms": "200",
            "ttl_seconds": "86400",
            "data_sources": json.dumps(["EventSearchAgent"]),
            "cache_version": "1.0"
        }
        
        mock_redis.hgetall.return_value = cached_data
        
        result = await cache_server.get_calendar_data("San Francisco, CA", "2025-07-12")
        
        assert result is not None
        assert isinstance(result, CalendarCacheEntry)
        assert result.location == "San Francisco, CA"
        assert result.date_range == "2025-07-12"
        assert result.hit_count == 6  # Should be incremented
        assert result.data_sources == ["EventSearchAgent"]
        
        # Verify cache hit was recorded
        mock_redis.hset.assert_called()  # Update last_accessed
        mock_redis.hincrby.assert_called()  # Update hit_count
    
    @pytest.mark.asyncio
    async def test_get_calendar_data_miss(self, cache_server, mock_redis):
        """Test retrieving calendar data from cache (cache miss)."""
        # Mock empty result (cache miss)
        mock_redis.hgetall.return_value = {}
        
        result = await cache_server.get_calendar_data("San Francisco, CA", "2025-07-12")
        
        assert result is None
        
        # Verify statistics were updated
        mock_redis.hincrby.assert_called()
    
    @pytest.mark.asyncio
    async def test_invalidate_cache_specific(self, cache_server, mock_redis):
        """Test invalidating specific cache entry."""
        mock_redis.delete.return_value = 1
        
        deleted_count = await cache_server.invalidate_cache(
            location="San Francisco, CA",
            date_range="2025-07-12"
        )
        
        assert deleted_count == 1
        mock_redis.delete.assert_called_once()
        mock_redis.hincrby.assert_called()  # Statistics update
    
    @pytest.mark.asyncio
    async def test_invalidate_cache_pattern(self, cache_server, mock_redis):
        """Test invalidating cache entries by pattern."""
        # Mock scan_iter to return test keys
        async def mock_scan_iter(match=None):
            test_keys = [
                "calendar:san_francisco_ca:2025_07_12",
                "calendar:san_francisco_ca:2025_07_13"
            ]
            for key in test_keys:
                yield key
        
        mock_redis.scan_iter = mock_scan_iter
        mock_redis.delete.return_value = 2
        
        deleted_count = await cache_server.invalidate_cache(location="San Francisco, CA")
        
        assert deleted_count == 2
        mock_redis.delete.assert_called()
    
    @pytest.mark.asyncio
    async def test_get_cache_stats(self, cache_server, mock_redis):
        """Test getting cache statistics."""
        # Mock statistics data
        mock_stats = {
            "total_requests": "100",
            "cache_hits": "75",
            "cache_misses": "25",
            "total_stores": "50",
            "total_invalidations": "5",
            "created_at": "2025-07-12T00:00:00+00:00"
        }
        
        mock_redis.hgetall.return_value = mock_stats
        
        # Mock scan_iter for counting entries
        async def mock_scan_iter(match=None):
            test_keys = ["calendar:test1", "calendar:test2"]
            for key in test_keys:
                yield key
        
        mock_redis.scan_iter = mock_scan_iter
        
        stats = await cache_server.get_cache_stats()
        
        assert stats["cache_statistics"]["total_requests"] == 100
        assert stats["cache_statistics"]["cache_hits"] == 75
        assert stats["cache_statistics"]["hit_rate_percent"] == 75.0
        assert stats["cache_content"]["total_entries"] == 2
        assert "redis_info" in stats
        assert stats["cache_version"] == "1.0"
    
    @pytest.mark.asyncio
    async def test_list_cache_entries(self, cache_server, mock_redis):
        """Test listing cache entries."""
        # Mock entry data
        mock_entry_data = {
            "location": "San Francisco, CA",
            "date_range": "2025-07-12",
            "cached_at": "2025-07-12T10:00:00+00:00",
            "last_accessed": "2025-07-12T11:00:00+00:00",
            "hit_count": "3",
            "processing_time_ms": "150",
            "data_sources": json.dumps(["EventSearchAgent", "WeatherAPI"])
        }
        
        mock_redis.hgetall.return_value = mock_entry_data
        mock_redis.ttl.return_value = 3600
        
        # Mock scan_iter
        async def mock_scan_iter(match=None):
            yield "calendar:san_francisco_ca:2025_07_12"
        
        mock_redis.scan_iter = mock_scan_iter
        
        entries = await cache_server.list_cache_entries(limit=5)
        
        assert len(entries) == 1
        assert entries[0]["location"] == "San Francisco, CA"
        assert entries[0]["hit_count"] == 3
        assert entries[0]["ttl_remaining_seconds"] == 3600
        assert entries[0]["data_sources"] == ["EventSearchAgent", "WeatherAPI"]
    
    @pytest.mark.asyncio
    async def test_warm_cache(self, cache_server, mock_redis):
        """Test cache warming plan generation."""
        # Mock some existing and some missing entries
        def mock_exists(key):
            return key == "calendar:san_francisco_ca:2025_07_12"
        
        mock_redis.exists.side_effect = mock_exists
        
        locations = ["San Francisco, CA", "New York, NY"]
        date_ranges = ["2025-07-12", "2025-07-13"]
        
        result = await cache_server.warm_cache(locations, date_ranges)
        
        assert result["total_locations"] == 2
        assert result["total_date_ranges"] == 2
        assert len(result["warming_plan"]) == 4
        assert result["entries_needing_warming"] == 3  # 4 total - 1 existing
        
        # Check specific plan entries
        plan = result["warming_plan"]
        existing_entry = next(p for p in plan if not p["needs_warming"])
        assert existing_entry["location"] == "San Francisco, CA"
        assert existing_entry["date_range"] == "2025-07-12"
    
    @pytest.mark.asyncio
    async def test_cache_key_normalization(self, cache_server):
        """Test that cache keys are properly normalized."""
        # Test various input formats
        key1 = cache_server._generate_cache_key("San Francisco, CA", "2025-07-12")
        key2 = cache_server._generate_cache_key("SAN FRANCISCO, CA", "2025-07-12")
        key3 = cache_server._generate_cache_key("san francisco, ca", "2025-07-12")
        
        # All should produce the same normalized key
        assert key1 == key2 == key3 == "calendar:san_francisco_ca:2025_07_12"
        
        # Test date range normalization
        key4 = cache_server._generate_cache_key("Test City", "2025-07-12 - 2025-07-19")
        key5 = cache_server._generate_cache_key("Test City", "2025_07_12_2025_07_19")
        
        assert "test_city" in key4
        assert "test_city" in key5
    
    @pytest.mark.asyncio
    async def test_error_handling(self, cache_server, mock_redis):
        """Test error handling in cache operations."""
        # Test Redis connection error
        mock_redis.hset.side_effect = redis.ConnectionError("Connection failed")
        
        with pytest.raises(redis.ConnectionError):
            await cache_server.store_calendar_data(
                location="Test Location",
                date_range="2025-07-12",
                calendar_data={"test": "data"}
            )
        
        # Test invalid JSON in cached data
        mock_redis.hset.side_effect = None  # Reset
        mock_redis.hgetall.return_value = {
            "cache_key": "test",
            "location": "Test",
            "date_range": "2025-07-12",
            "calendar_data": "invalid json",  # This will cause JSON decode error
            "cached_at": "2025-07-12T10:00:00+00:00",
            "last_accessed": "2025-07-12T10:00:00+00:00",
            "hit_count": "1",
            "processing_time_ms": "100",
            "ttl_seconds": "3600",
            "data_sources": "[]",
            "cache_version": "1.0"
        }
        
        result = await cache_server.get_calendar_data("Test", "2025-07-12")
        # Should return None and log error rather than crash
        assert result is None


class TestCalendarCacheEntry:
    """Test the CalendarCacheEntry model."""
    
    def test_cache_entry_initialization(self):
        """Test cache entry initialization."""
        now = datetime.now(timezone.utc)
        
        entry = CalendarCacheEntry(
            cache_key="test_key",
            location="Test Location",
            date_range="2025-07-12",
            calendar_data={"events": []},
            cached_at=now,
            last_accessed=now,
            hit_count=5,
            processing_time_ms=200,
            ttl_seconds=3600,
            data_sources=["TestAgent"],
            cache_version="1.0"
        )
        
        assert entry.cache_key == "test_key"
        assert entry.location == "Test Location"
        assert entry.hit_count == 5
        assert entry.processing_time_ms == 200
        assert entry.ttl_seconds == 3600
        assert entry.data_sources == ["TestAgent"]
        assert entry.cache_version == "1.0"
    
    def test_cache_entry_defaults(self):
        """Test cache entry default values."""
        entry = CalendarCacheEntry()
        
        assert entry.hit_count == 0
        assert entry.processing_time_ms == 0
        assert entry.ttl_seconds == 86400
        assert entry.data_sources == []
        assert entry.cache_version == "1.0"


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""
    
    @pytest.mark.asyncio
    async def test_full_cache_workflow(self, cache_server, mock_redis):
        """Test a complete cache workflow."""
        # 1. Store calendar data
        test_data = {
            "events": [
                {"name": "Tech Conference", "date": "2025-07-12"},
                {"name": "Music Festival", "date": "2025-07-13"}
            ],
            "weather": {"temperature": 25, "condition": "sunny"},
            "opportunity_score": 92
        }
        
        cache_key = await cache_server.store_calendar_data(
            location="San Francisco, CA",
            date_range="2025-07-12_2025-07-13",
            calendar_data=test_data,
            categories=["tech", "music"],
            processing_time_ms=250,
            data_sources=["EventSearchAgent", "WeatherAPI", "HolidayAPI"]
        )
        
        assert cache_key == "calendar:san_francisco_ca:2025_07_12_2025_07_13:music_tech"
        
        # 2. Retrieve from cache (simulate cache hit)
        mock_redis.hgetall.return_value = {
            "cache_key": cache_key,
            "location": "San Francisco, CA",
            "date_range": "2025-07-12_2025-07-13",
            "calendar_data": json.dumps(test_data),
            "cached_at": "2025-07-12T10:00:00+00:00",
            "last_accessed": "2025-07-12T10:00:00+00:00",
            "hit_count": "0",
            "processing_time_ms": "250",
            "ttl_seconds": "86400",
            "data_sources": json.dumps(["EventSearchAgent", "WeatherAPI", "HolidayAPI"]),
            "cache_version": "1.0"
        }
        
        retrieved = await cache_server.get_calendar_data(
            location="San Francisco, CA",
            date_range="2025-07-12_2025-07-13",
            categories=["tech", "music"]
        )
        
        assert retrieved is not None
        assert retrieved.calendar_data["opportunity_score"] == 92
        assert len(retrieved.calendar_data["events"]) == 2
        assert retrieved.processing_time_ms == 250
        
        # 3. Check statistics
        mock_redis.hgetall.return_value = {
            "total_requests": "1",
            "cache_hits": "1",
            "cache_misses": "0",
            "total_stores": "1",
            "total_invalidations": "0"
        }
        
        async def mock_scan_iter(match=None):
            yield cache_key
        
        mock_redis.scan_iter = mock_scan_iter
        
        stats = await cache_server.get_cache_stats()
        assert stats["cache_statistics"]["hit_rate_percent"] == 100.0
        assert stats["cache_content"]["total_entries"] == 1
        
        # 4. Invalidate cache
        mock_redis.delete.return_value = 1
        deleted = await cache_server.invalidate_cache(
            location="San Francisco, CA",
            date_range="2025-07-12_2025-07-13",
            categories=["tech", "music"]
        )
        
        assert deleted == 1
    
    @pytest.mark.asyncio
    async def test_cache_performance_simulation(self, cache_server, mock_redis):
        """Test cache performance under simulated load."""
        # Simulate storing multiple cache entries
        locations = ["San Francisco, CA", "New York, NY", "Los Angeles, CA"]
        dates = ["2025-07-12", "2025-07-13", "2025-07-14"]
        
        store_calls = 0
        
        for location in locations:
            for date in dates:
                await cache_server.store_calendar_data(
                    location=location,
                    date_range=date,
                    calendar_data={"events": [], "opportunity_score": 75},
                    processing_time_ms=100
                )
                store_calls += 1
        
        # Verify all stores were called
        assert mock_redis.hset.call_count >= store_calls
        assert mock_redis.expire.call_count >= store_calls
        
        # Simulate cache warming
        result = await cache_server.warm_cache(locations, dates)
        assert result["total_locations"] == 3
        assert result["total_date_ranges"] == 3
        assert len(result["warming_plan"]) == 9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])