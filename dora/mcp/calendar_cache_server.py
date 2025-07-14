"""MCP Calendar Cache Server for Dora - High-performance Redis-based calendar data caching."""

import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import logging

import redis.asyncio as redis
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import structlog

logger = structlog.get_logger(__name__)


class CalendarCacheEntry:
    """Model for cached calendar data."""
    
    def __init__(self, **kwargs):
        self.cache_key = kwargs.get('cache_key')
        self.location = kwargs.get('location')
        self.date_range = kwargs.get('date_range')
        self.calendar_data = kwargs.get('calendar_data')
        self.cached_at = kwargs.get('cached_at')
        self.last_accessed = kwargs.get('last_accessed')
        self.hit_count = kwargs.get('hit_count', 0)
        self.processing_time_ms = kwargs.get('processing_time_ms', 0)
        self.ttl_seconds = kwargs.get('ttl_seconds', 86400)  # 24 hours default
        self.data_sources = kwargs.get('data_sources', [])
        self.cache_version = kwargs.get('cache_version', "1.0")


class CalendarCacheServer:
    """Redis-based high-performance calendar cache server."""
    
    def __init__(self, redis_url: str = None):
        """Initialize the calendar cache server with Redis backend."""
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.default_ttl = int(os.getenv("CALENDAR_CACHE_TTL_SECONDS", "86400"))  # 24 hours
        self.max_connections = int(os.getenv("REDIS_POOL_SIZE", "10"))
        self.cache_version = "1.0"
        self.stats_key = "calendar_cache:stats"
        
        # Connection pool configuration
        self.redis_pool = None
        self.redis_client: Optional[redis.Redis] = None
        
        self.logger = logger.bind(component="calendar_cache_server")
    
    async def initialize(self):
        """Initialize Redis connection pool."""
        try:
            # Create connection pool
            self.redis_pool = redis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.max_connections,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # Create Redis client
            self.redis_client = redis.Redis(connection_pool=self.redis_pool, decode_responses=True)
            
            # Test connection
            await self.redis_client.ping()
            
            # Initialize stats if they don't exist
            await self._initialize_stats()
            
            self.logger.info("Calendar cache server initialized successfully", 
                           redis_url=self._mask_url(self.redis_url))
            
        except Exception as e:
            self.logger.error("Failed to initialize calendar cache server", error=str(e))
            raise
    
    async def cleanup(self):
        """Clean up Redis connections."""
        if self.redis_client:
            await self.redis_client.close()
        if self.redis_pool:
            await self.redis_pool.disconnect()
    
    def _mask_url(self, url: str) -> str:
        """Mask sensitive information in Redis URL."""
        if "@" in url:
            parts = url.split("@")
            if len(parts) == 2:
                return f"{parts[0].split('//')[0]}//***@{parts[1]}"
        return url
    
    def _generate_cache_key(self, location: str, date_range: str, categories: List[str] = None) -> str:
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
    
    async def _initialize_stats(self):
        """Initialize cache statistics."""
        stats_exists = await self.redis_client.exists(self.stats_key)
        if not stats_exists:
            initial_stats = {
                "total_requests": 0,
                "cache_hits": 0,
                "cache_misses": 0,
                "total_stores": 0,
                "total_invalidations": 0,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await self.redis_client.hset(self.stats_key, mapping=initial_stats)
    
    async def _update_stats(self, operation: str, count: int = 1):
        """Update cache statistics."""
        await self.redis_client.hincrby(self.stats_key, operation, count)
    
    async def store_calendar_data(
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
        Store calendar data in Redis cache.
        
        Args:
            location: Location identifier (e.g., "San Francisco, CA")
            date_range: Date range (e.g., "2025-07-12" or "2025-07-12_2025-07-19")
            calendar_data: Calendar data to cache
            categories: Optional event categories for filtering
            ttl_seconds: Time to live in seconds (default: 24 hours)
            processing_time_ms: Time taken to generate this data
            data_sources: List of data sources used
        
        Returns:
            Cache key for the stored data
        """
        try:
            cache_key = self._generate_cache_key(location, date_range, categories)
            ttl = ttl_seconds or self.default_ttl
            now = datetime.now(timezone.utc)
            
            # Create cache entry
            entry = CalendarCacheEntry(
                cache_key=cache_key,
                location=location,
                date_range=date_range,
                calendar_data=calendar_data,
                cached_at=now,
                last_accessed=now,
                hit_count=0,
                processing_time_ms=processing_time_ms,
                ttl_seconds=ttl,
                data_sources=data_sources or [],
                cache_version=self.cache_version
            )
            
            # Prepare data for Redis
            cache_data = {
                "cache_key": entry.cache_key,
                "location": entry.location,
                "date_range": entry.date_range,
                "calendar_data": json.dumps(entry.calendar_data),
                "cached_at": entry.cached_at.isoformat(),
                "last_accessed": entry.last_accessed.isoformat(),
                "hit_count": entry.hit_count,
                "processing_time_ms": entry.processing_time_ms,
                "ttl_seconds": entry.ttl_seconds,
                "data_sources": json.dumps(entry.data_sources),
                "cache_version": entry.cache_version
            }
            
            # Store in Redis with TTL
            await self.redis_client.hset(cache_key, mapping=cache_data)
            await self.redis_client.expire(cache_key, ttl)
            
            # Add to sorted set for ranking (by cached timestamp)
            ranking_key = f"calendar:ranking:{location.lower().replace(' ', '_')}"
            await self.redis_client.zadd(ranking_key, {cache_key: now.timestamp()})
            await self.redis_client.expire(ranking_key, ttl)
            
            # Update statistics
            await self._update_stats("total_stores")
            
            self.logger.info("Calendar data cached successfully",
                           cache_key=cache_key, location=location, ttl=ttl)
            
            return cache_key
            
        except Exception as e:
            self.logger.error("Failed to store calendar data", 
                            location=location, date_range=date_range, error=str(e))
            raise
    
    async def get_calendar_data(
        self,
        location: str,
        date_range: str,
        categories: List[str] = None
    ) -> Optional[CalendarCacheEntry]:
        """
        Retrieve calendar data from cache.
        
        Args:
            location: Location identifier
            date_range: Date range
            categories: Optional event categories for filtering
        
        Returns:
            CalendarCacheEntry if found, None otherwise
        """
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
            
            # Parse the cached data
            entry = CalendarCacheEntry(
                cache_key=cached_data["cache_key"],
                location=cached_data["location"],
                date_range=cached_data["date_range"],
                calendar_data=json.loads(cached_data["calendar_data"]),
                cached_at=datetime.fromisoformat(cached_data["cached_at"]),
                last_accessed=now,  # Use current time
                hit_count=int(cached_data["hit_count"]) + 1,  # Increment for this access
                processing_time_ms=int(cached_data["processing_time_ms"]),
                ttl_seconds=int(cached_data["ttl_seconds"]),
                data_sources=json.loads(cached_data["data_sources"]),
                cache_version=cached_data["cache_version"]
            )
            
            await self._update_stats("cache_hits")
            await self._update_stats("total_requests")
            
            self.logger.info("Calendar data retrieved from cache",
                           cache_key=cache_key, hit_count=entry.hit_count)
            
            return entry
            
        except Exception as e:
            self.logger.error("Failed to retrieve calendar data",
                            location=location, date_range=date_range, error=str(e))
            await self._update_stats("cache_misses")
            await self._update_stats("total_requests")
            return None
    
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
            location: Specific location to invalidate
            date_range: Specific date range to invalidate
            categories: Specific categories to invalidate
            pattern: Custom pattern for bulk invalidation
        
        Returns:
            Number of keys deleted
        """
        try:
            deleted_count = 0
            
            if pattern:
                # Use custom pattern
                search_pattern = pattern
            elif location and date_range:
                # Specific cache key
                cache_key = self._generate_cache_key(location, date_range, categories)
                deleted = await self.redis_client.delete(cache_key)
                if deleted:
                    deleted_count = 1
                    await self._update_stats("total_invalidations")
                    self.logger.info("Cache entry invalidated", cache_key=cache_key)
                return deleted_count
            elif location:
                # All entries for a location
                location_normalized = location.lower().replace(" ", "_").replace(",", "")
                search_pattern = f"calendar:{location_normalized}:*"
            else:
                # All calendar cache entries
                search_pattern = "calendar:*"
            
            # Find matching keys
            keys = []
            async for key in self.redis_client.scan_iter(match=search_pattern):
                keys.append(key)
            
            # Delete in batches
            if keys:
                # Delete main keys
                deleted_count = await self.redis_client.delete(*keys)
                
                # Also clean up ranking sets
                ranking_keys = []
                for key in keys:
                    if key.startswith("calendar:") and not key.startswith("calendar:ranking:"):
                        # Extract location for ranking cleanup
                        parts = key.split(":")
                        if len(parts) >= 2:
                            loc_part = parts[1]
                            ranking_key = f"calendar:ranking:{loc_part}"
                            ranking_keys.append(ranking_key)
                
                if ranking_keys:
                    await self.redis_client.delete(*set(ranking_keys))  # Remove duplicates
                
                await self._update_stats("total_invalidations", deleted_count)
                
                self.logger.info("Cache entries invalidated",
                               pattern=search_pattern, deleted_count=deleted_count)
            
            return deleted_count
            
        except Exception as e:
            self.logger.error("Failed to invalidate cache", pattern=search_pattern, error=str(e))
            raise
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        try:
            # Get basic stats
            stats = await self.redis_client.hgetall(self.stats_key)
            
            # Calculate derived stats
            total_requests = int(stats.get("total_requests", 0))
            cache_hits = int(stats.get("cache_hits", 0))
            cache_misses = int(stats.get("cache_misses", 0))
            
            hit_rate = (cache_hits / total_requests * 100) if total_requests > 0 else 0
            miss_rate = (cache_misses / total_requests * 100) if total_requests > 0 else 0
            
            # Count current cache entries
            calendar_keys = []
            async for key in self.redis_client.scan_iter(match="calendar:*"):
                if not key.startswith("calendar:ranking:") and key != self.stats_key:
                    calendar_keys.append(key)
            
            # Get memory usage
            memory_info = await self.redis_client.info("memory")
            
            # Get Redis server info
            server_info = await self.redis_client.info("server")
            
            result = {
                "cache_statistics": {
                    "total_requests": total_requests,
                    "cache_hits": cache_hits,
                    "cache_misses": cache_misses,
                    "hit_rate_percent": round(hit_rate, 2),
                    "miss_rate_percent": round(miss_rate, 2),
                    "total_stores": int(stats.get("total_stores", 0)),
                    "total_invalidations": int(stats.get("total_invalidations", 0))
                },
                "cache_content": {
                    "total_entries": len(calendar_keys),
                    "default_ttl_seconds": self.default_ttl
                },
                "redis_info": {
                    "redis_version": server_info.get("redis_version"),
                    "used_memory_human": memory_info.get("used_memory_human"),
                    "used_memory_peak_human": memory_info.get("used_memory_peak_human"),
                    "connected_clients": server_info.get("connected_clients")
                },
                "created_at": stats.get("created_at"),
                "cache_version": self.cache_version
            }
            
            return result
            
        except Exception as e:
            self.logger.error("Failed to get cache statistics", error=str(e))
            raise
    
    async def list_cache_entries(self, location: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """List cached entries for debugging."""
        try:
            if location:
                location_normalized = location.lower().replace(" ", "_").replace(",", "")
                pattern = f"calendar:{location_normalized}:*"
            else:
                pattern = "calendar:*"
            
            entries = []
            count = 0
            
            async for key in self.redis_client.scan_iter(match=pattern):
                if key.startswith("calendar:ranking:") or key == self.stats_key:
                    continue
                
                if count >= limit:
                    break
                
                entry_data = await self.redis_client.hgetall(key)
                if entry_data:
                    # Get TTL
                    ttl = await self.redis_client.ttl(key)
                    
                    entries.append({
                        "cache_key": key,
                        "location": entry_data.get("location"),
                        "date_range": entry_data.get("date_range"),
                        "cached_at": entry_data.get("cached_at"),
                        "last_accessed": entry_data.get("last_accessed"),
                        "hit_count": int(entry_data.get("hit_count", 0)),
                        "processing_time_ms": int(entry_data.get("processing_time_ms", 0)),
                        "ttl_remaining_seconds": ttl,
                        "data_sources": json.loads(entry_data.get("data_sources", "[]"))
                    })
                
                count += 1
            
            # Sort by last accessed (most recent first)
            entries.sort(key=lambda x: x["last_accessed"], reverse=True)
            
            return entries
            
        except Exception as e:
            self.logger.error("Failed to list cache entries", error=str(e))
            raise
    
    async def warm_cache(self, locations: List[str], date_ranges: List[str]) -> Dict[str, Any]:
        """Prepare cache warming for popular locations (placeholder for integration)."""
        try:
            # This would typically integrate with the calendar intelligence agent
            # to pre-populate cache for popular locations
            
            warming_plan = []
            for location in locations:
                for date_range in date_ranges:
                    cache_key = self._generate_cache_key(location, date_range)
                    exists = await self.redis_client.exists(cache_key)
                    if not exists:
                        warming_plan.append({
                            "location": location,
                            "date_range": date_range,
                            "cache_key": cache_key,
                            "needs_warming": True
                        })
                    else:
                        warming_plan.append({
                            "location": location,
                            "date_range": date_range,
                            "cache_key": cache_key,
                            "needs_warming": False
                        })
            
            self.logger.info("Cache warming plan generated", 
                           total_entries=len(warming_plan),
                           needs_warming=len([p for p in warming_plan if p["needs_warming"]]))
            
            return {
                "warming_plan": warming_plan,
                "total_locations": len(locations),
                "total_date_ranges": len(date_ranges),
                "entries_needing_warming": len([p for p in warming_plan if p["needs_warming"]])
            }
            
        except Exception as e:
            self.logger.error("Failed to generate cache warming plan", error=str(e))
            raise


# Create MCP server
cache_server = CalendarCacheServer()
server = Server("dora-calendar-cache")


@server.list_tools()
async def list_tools() -> List[Tool]:
    """List available calendar cache tools."""
    return [
        Tool(
            name="store_calendar_data",
            description="Store calendar data in Redis cache with configurable TTL",
            inputSchema={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Location identifier (e.g., 'San Francisco, CA')"
                    },
                    "date_range": {
                        "type": "string",
                        "description": "Date range (e.g., '2025-07-12' or '2025-07-12_2025-07-19')"
                    },
                    "calendar_data": {
                        "type": "object",
                        "description": "Calendar data to cache"
                    },
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional event categories for filtering"
                    },
                    "ttl_seconds": {
                        "type": "integer",
                        "description": "Time to live in seconds (default: 86400 - 24 hours)"
                    },
                    "processing_time_ms": {
                        "type": "integer",
                        "description": "Time taken to generate this data"
                    },
                    "data_sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of data sources used"
                    }
                },
                "required": ["location", "date_range", "calendar_data"]
            }
        ),
        Tool(
            name="get_calendar_data",
            description="Retrieve cached calendar data",
            inputSchema={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Location identifier"
                    },
                    "date_range": {
                        "type": "string",
                        "description": "Date range"
                    },
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional event categories for filtering"
                    }
                },
                "required": ["location", "date_range"]
            }
        ),
        Tool(
            name="invalidate_cache",
            description="Invalidate cache entries by location, date range, or pattern",
            inputSchema={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Specific location to invalidate"
                    },
                    "date_range": {
                        "type": "string",
                        "description": "Specific date range to invalidate"
                    },
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific categories to invalidate"
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Custom Redis pattern for bulk invalidation"
                    }
                }
            }
        ),
        Tool(
            name="get_cache_stats",
            description="Get comprehensive cache statistics and performance metrics",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="list_cache_entries",
            description="List cached entries for debugging",
            inputSchema={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Filter by specific location"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of entries to return",
                        "default": 10
                    }
                }
            }
        ),
        Tool(
            name="warm_cache",
            description="Generate cache warming plan for popular locations",
            inputSchema={
                "type": "object",
                "properties": {
                    "locations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of locations to warm"
                    },
                    "date_ranges": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of date ranges to warm"
                    }
                },
                "required": ["locations", "date_ranges"]
            }
        )
    ]


@server.call_tool()
async def call_tool(tool_name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle calendar cache tool calls."""
    try:
        if tool_name == "store_calendar_data":
            cache_key = await cache_server.store_calendar_data(
                location=arguments["location"],
                date_range=arguments["date_range"],
                calendar_data=arguments["calendar_data"],
                categories=arguments.get("categories"),
                ttl_seconds=arguments.get("ttl_seconds"),
                processing_time_ms=arguments.get("processing_time_ms", 0),
                data_sources=arguments.get("data_sources")
            )
            return [TextContent(type="text", text=json.dumps({"cache_key": cache_key}))]
        
        elif tool_name == "get_calendar_data":
            entry = await cache_server.get_calendar_data(
                location=arguments["location"],
                date_range=arguments["date_range"],
                categories=arguments.get("categories")
            )
            
            if entry:
                result = {
                    "cache_key": entry.cache_key,
                    "location": entry.location,
                    "date_range": entry.date_range,
                    "calendar_data": entry.calendar_data,
                    "cached_at": entry.cached_at.isoformat(),
                    "last_accessed": entry.last_accessed.isoformat(),
                    "hit_count": entry.hit_count,
                    "processing_time_ms": entry.processing_time_ms,
                    "ttl_seconds": entry.ttl_seconds,
                    "data_sources": entry.data_sources,
                    "cache_version": entry.cache_version
                }
                return [TextContent(type="text", text=json.dumps(result))]
            else:
                return [TextContent(type="text", text=json.dumps(None))]
        
        elif tool_name == "invalidate_cache":
            deleted_count = await cache_server.invalidate_cache(
                location=arguments.get("location"),
                date_range=arguments.get("date_range"),
                categories=arguments.get("categories"),
                pattern=arguments.get("pattern")
            )
            return [TextContent(type="text", text=json.dumps({"deleted_count": deleted_count}))]
        
        elif tool_name == "get_cache_stats":
            stats = await cache_server.get_cache_stats()
            return [TextContent(type="text", text=json.dumps(stats))]
        
        elif tool_name == "list_cache_entries":
            entries = await cache_server.list_cache_entries(
                location=arguments.get("location"),
                limit=arguments.get("limit", 10)
            )
            return [TextContent(type="text", text=json.dumps(entries))]
        
        elif tool_name == "warm_cache":
            plan = await cache_server.warm_cache(
                locations=arguments["locations"],
                date_ranges=arguments["date_ranges"]
            )
            return [TextContent(type="text", text=json.dumps(plan))]
        
        else:
            return [TextContent(type="text", text=f"Unknown tool: {tool_name}")]
    
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# Run the server
async def main():
    """Run the MCP Calendar Cache server."""
    # Set up logging to file instead of stdout (since we use stdio for MCP)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        filename='/tmp/dora_calendar_cache_server.log',
        filemode='a'
    )
    
    # Initialize the cache server
    await cache_server.initialize()
    
    try:
        # Initialize server with options
        init_options = InitializationOptions(
            capabilities=NotificationOptions(
                prompts=False,
                resources=False
            )
        )
        
        # Run the stdio server
        async with stdio_server(init_options=init_options) as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                None  # No notifications
            )
    finally:
        # Cleanup
        await cache_server.cleanup()


if __name__ == "__main__":
    asyncio.run(main())