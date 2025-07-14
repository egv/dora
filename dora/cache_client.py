"""Calendar Cache Client for integration with calendar intelligence agents."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
import asyncio

import redis.asyncio as redis
import structlog

from dora.models.config import DoraConfig


logger = structlog.get_logger(__name__)


class CalendarCacheClient:
    """Client for interacting with the calendar cache."""
    
    def __init__(self, config: DoraConfig = None, redis_url: str = None):
        """
        Initialize calendar cache client.
        
        Args:
            config: Dora configuration object
            redis_url: Direct Redis URL (overrides config)
        """
        if config:
            self.redis_url = config.redis_url
            self.pool_size = config.redis_pool_size
        else:
            self.redis_url = redis_url or "redis://localhost:6379/0"
            self.pool_size = 10
        
        self.redis_client: Optional[redis.Redis] = None
        self.redis_pool = None
        self.logger = logger.bind(component="calendar_cache_client")
        
        # Cache settings
        self.default_ttl = 86400  # 24 hours
        self.stats_key = "calendar_cache:stats"
    
    async def initialize(self):
        """Initialize Redis connection."""
        try:
            # Create connection pool
            self.redis_pool = redis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.pool_size,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # Create Redis client
            self.redis_client = redis.Redis(
                connection_pool=self.redis_pool,
                decode_responses=True
            )
            
            # Test connection
            await self.redis_client.ping()
            
            self.logger.info("Calendar cache client initialized")
            
        except Exception as e:
            self.logger.error("Failed to initialize calendar cache client", error=str(e))
            raise
    
    async def cleanup(self):
        """Clean up Redis connections."""
        if self.redis_client:
            await self.redis_client.close()
        if self.redis_pool:
            await self.redis_pool.disconnect()
    
    def _generate_cache_key(
        self, 
        location: str, 
        date_range: str, 
        categories: List[str] = None
    ) -> str:
        """Generate cache key for calendar data."""
        # Normalize location and date range
        location_normalized = location.lower().replace(" ", "_").replace(",", "")
        date_normalized = date_range.replace(" ", "").replace("-", "_")
        
        # Add categories if provided
        if categories:
            categories_str = "_".join(sorted(categories))
            return f"calendar:{location_normalized}:{date_normalized}:{categories_str}"
        else:
            return f"calendar:{location_normalized}:{date_normalized}"
    
    async def get_cached_calendar_data(
        self,
        location: str,
        date_range: str,
        categories: List[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get calendar data from cache.
        
        Args:
            location: Location identifier
            date_range: Date range
            categories: Optional event categories
        
        Returns:
            Cached calendar data or None if not found
        """
        if not self.redis_client:
            await self.initialize()
        
        try:
            cache_key = self._generate_cache_key(location, date_range, categories)
            
            # Get data from Redis
            cached_data = await self.redis_client.hgetall(cache_key)
            
            if not cached_data:
                await self._update_stats("cache_misses")
                return None
            
            # Update access time and hit count
            now = datetime.now(timezone.utc)
            await self.redis_client.hset(cache_key, "last_accessed", now.isoformat())
            await self.redis_client.hincrby(cache_key, "hit_count", 1)
            
            # Parse calendar data
            calendar_data = json.loads(cached_data["calendar_data"])
            
            await self._update_stats("cache_hits")
            await self._update_stats("total_requests")
            
            self.logger.info("Calendar data retrieved from cache",
                           cache_key=cache_key, location=location)
            
            # Return enriched result with cache metadata
            return {
                "calendar_data": calendar_data,
                "cache_metadata": {
                    "cache_key": cache_key,
                    "cached_at": cached_data["cached_at"],
                    "last_accessed": now.isoformat(),
                    "hit_count": int(cached_data["hit_count"]) + 1,
                    "processing_time_ms": int(cached_data.get("processing_time_ms", 0)),
                    "data_sources": json.loads(cached_data.get("data_sources", "[]")),
                    "from_cache": True
                }
            }
            
        except Exception as e:
            self.logger.error("Failed to retrieve calendar data from cache",
                            location=location, error=str(e))
            await self._update_stats("cache_misses")
            await self._update_stats("total_requests")
            return None
    
    async def cache_calendar_data(
        self,
        location: str,
        date_range: str,
        calendar_data: Dict[str, Any],
        categories: List[str] = None,
        ttl_seconds: int = None,
        processing_time_ms: int = 0,
        data_sources: List[str] = None
    ) -> str:
        """
        Cache calendar data.
        
        Args:
            location: Location identifier
            date_range: Date range
            calendar_data: Calendar data to cache
            categories: Optional event categories
            ttl_seconds: Time to live (default: 24 hours)
            processing_time_ms: Processing time for this data
            data_sources: List of data sources used
        
        Returns:
            Cache key
        """
        if not self.redis_client:
            await self.initialize()
        
        try:
            cache_key = self._generate_cache_key(location, date_range, categories)
            ttl = ttl_seconds or self.default_ttl
            now = datetime.now(timezone.utc)
            
            # Prepare cache entry
            cache_entry = {
                "cache_key": cache_key,
                "location": location,
                "date_range": date_range,
                "calendar_data": json.dumps(calendar_data),
                "cached_at": now.isoformat(),
                "last_accessed": now.isoformat(),
                "hit_count": 0,
                "processing_time_ms": processing_time_ms,
                "ttl_seconds": ttl,
                "data_sources": json.dumps(data_sources or []),
                "cache_version": "1.0"
            }
            
            # Store in Redis
            await self.redis_client.hset(cache_key, mapping=cache_entry)
            await self.redis_client.expire(cache_key, ttl)
            
            # Add to ranking (for cache management)
            ranking_key = f"calendar:ranking:{location.lower().replace(' ', '_')}"
            await self.redis_client.zadd(ranking_key, {cache_key: now.timestamp()})
            await self.redis_client.expire(ranking_key, ttl)
            
            # Update statistics
            await self._update_stats("total_stores")
            
            self.logger.info("Calendar data cached",
                           cache_key=cache_key, location=location, ttl=ttl)
            
            return cache_key
            
        except Exception as e:
            self.logger.error("Failed to cache calendar data",
                            location=location, error=str(e))
            raise
    
    async def invalidate_cache(
        self,
        location: str = None,
        date_range: str = None,
        categories: List[str] = None,
        pattern: str = None
    ) -> int:
        """
        Invalidate cache entries.
        
        Args:
            location: Specific location
            date_range: Specific date range
            categories: Specific categories
            pattern: Custom pattern
        
        Returns:
            Number of keys deleted
        """
        if not self.redis_client:
            await self.initialize()
        
        try:
            if location and date_range:
                # Specific entry
                cache_key = self._generate_cache_key(location, date_range, categories)
                deleted = await self.redis_client.delete(cache_key)
                if deleted:
                    await self._update_stats("total_invalidations")
                    self.logger.info("Cache entry invalidated", cache_key=cache_key)
                return deleted
            
            # Pattern-based invalidation
            if pattern:
                search_pattern = pattern
            elif location:
                location_normalized = location.lower().replace(" ", "_").replace(",", "")
                search_pattern = f"calendar:{location_normalized}:*"
            else:
                search_pattern = "calendar:*"
            
            # Find and delete matching keys
            keys = []
            async for key in self.redis_client.scan_iter(match=search_pattern):
                if not key.startswith("calendar:ranking:") and key != self.stats_key:
                    keys.append(key)
            
            deleted_count = 0
            if keys:
                deleted_count = await self.redis_client.delete(*keys)
                await self._update_stats("total_invalidations", deleted_count)
                
                self.logger.info("Cache entries invalidated",
                               pattern=search_pattern, deleted_count=deleted_count)
            
            return deleted_count
            
        except Exception as e:
            self.logger.error("Failed to invalidate cache", error=str(e))
            raise
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not self.redis_client:
            await self.initialize()
        
        try:
            # Get basic stats
            stats = await self.redis_client.hgetall(self.stats_key)
            
            if not stats:
                return {"error": "No statistics available"}
            
            # Calculate metrics
            total_requests = int(stats.get("total_requests", 0))
            cache_hits = int(stats.get("cache_hits", 0))
            cache_misses = int(stats.get("cache_misses", 0))
            
            hit_rate = (cache_hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                "total_requests": total_requests,
                "cache_hits": cache_hits,
                "cache_misses": cache_misses,
                "hit_rate_percent": round(hit_rate, 2),
                "total_stores": int(stats.get("total_stores", 0)),
                "total_invalidations": int(stats.get("total_invalidations", 0)),
                "created_at": stats.get("created_at")
            }
            
        except Exception as e:
            self.logger.error("Failed to get cache statistics", error=str(e))
            return {"error": str(e)}
    
    async def _update_stats(self, operation: str, count: int = 1):
        """Update cache statistics."""
        try:
            if self.redis_client:
                await self.redis_client.hincrby(self.stats_key, operation, count)
        except Exception as e:
            self.logger.warning("Failed to update cache statistics", 
                              operation=operation, error=str(e))
    
    async def health_check(self) -> Dict[str, Any]:
        """Check cache health."""
        try:
            if not self.redis_client:
                return {"status": "disconnected", "error": "Client not initialized"}
            
            # Test basic operation
            start_time = asyncio.get_event_loop().time()
            await self.redis_client.ping()
            ping_time = (asyncio.get_event_loop().time() - start_time) * 1000
            
            # Get Redis info
            info = await self.redis_client.info()
            
            return {
                "status": "healthy",
                "ping_time_ms": round(ping_time, 2),
                "redis_version": info.get("redis_version"),
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human")
            }
            
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


# Global cache client instance
_cache_client: Optional[CalendarCacheClient] = None


async def get_cache_client(config: DoraConfig = None) -> CalendarCacheClient:
    """Get or create the global cache client."""
    global _cache_client
    
    if _cache_client is None:
        _cache_client = CalendarCacheClient(config)
        await _cache_client.initialize()
    
    return _cache_client


async def cleanup_cache_client():
    """Clean up the global cache client."""
    global _cache_client
    
    if _cache_client is not None:
        await _cache_client.cleanup()
        _cache_client = None


# Convenience functions for direct use
async def get_calendar_data(
    location: str,
    date_range: str,
    categories: List[str] = None,
    config: DoraConfig = None
) -> Optional[Dict[str, Any]]:
    """Convenience function to get calendar data from cache."""
    client = await get_cache_client(config)
    return await client.get_cached_calendar_data(location, date_range, categories)


async def cache_calendar_data(
    location: str,
    date_range: str,
    calendar_data: Dict[str, Any],
    categories: List[str] = None,
    ttl_seconds: int = None,
    processing_time_ms: int = 0,
    data_sources: List[str] = None,
    config: DoraConfig = None
) -> str:
    """Convenience function to cache calendar data."""
    client = await get_cache_client(config)
    return await client.cache_calendar_data(
        location, date_range, calendar_data, categories,
        ttl_seconds, processing_time_ms, data_sources
    )


async def invalidate_calendar_cache(
    location: str = None,
    date_range: str = None,
    categories: List[str] = None,
    pattern: str = None,
    config: DoraConfig = None
) -> int:
    """Convenience function to invalidate calendar cache."""
    client = await get_cache_client(config)
    return await client.invalidate_cache(location, date_range, categories, pattern)