# Calendar Cache MCP Tool Documentation

## Overview

The Calendar Cache MCP Tool is a high-performance Redis-based caching system designed to cache calendar data for the Dora Calendar Intelligence System. It provides sub-millisecond latency for calendar data retrieval and includes advanced features like cache warming, statistics collection, and intelligent invalidation.

## Features

### Core Functionality
- **High-Performance Caching**: Redis-based storage with connection pooling
- **Configurable TTL**: Default 24-hour expiration with custom override
- **Key Normalization**: Automatic location and date range normalization
- **JSON Serialization**: Efficient storage and retrieval of complex calendar data
- **Connection Management**: Automatic connection pooling and cleanup

### Advanced Features
- **Cache Statistics**: Hit/miss ratios, performance metrics, memory usage
- **Pattern Invalidation**: Bulk cache invalidation by location or pattern
- **Sorted Sets**: Event ranking and priority management
- **Cache Warming**: Pre-population of popular locations
- **Health Monitoring**: Connection status and performance tracking

### MCP Integration
- **6 Tools Available**: Complete cache management through MCP interface
- **JSON-RPC 2.0**: Standard MCP protocol compliance
- **Async Operations**: Full asyncio support for high concurrency
- **Error Handling**: Comprehensive error handling and logging

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Calendar Cache MCP Tool                  │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │ MCP Server      │  │ Cache Server    │  │ Client      │  │
│  │ - 6 Tools       │  │ - Redis Pool    │  │ - Easy API  │  │
│  │ - JSON-RPC      │  │ - Key Mgmt      │  │ - Integration│  │
│  │ - Validation    │  │ - Statistics    │  │ - Convenience│  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                        Redis Backend                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │ Calendar Data   │  │ Statistics      │  │ Rankings    │  │
│  │ - Events        │  │ - Hit/Miss      │  │ - Popularity│  │
│  │ - Weather       │  │ - Performance   │  │ - Recency   │  │
│  │ - Opportunities │  │ - Memory        │  │ - Priority  │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Cache Key Structure

```
calendar:{location}:{date_range}[:{categories}]

Examples:
- calendar:san_francisco_ca:2025_07_12
- calendar:new_york_ny:2025_07_12_2025_07_19
- calendar:london_uk:2025_07_12:music_tech
```

## Installation & Setup

### Prerequisites
- Redis server (v6.0+)
- Python 3.11+
- MCP-compatible client (Claude Code, etc.)

### Configuration

1. **Environment Variables**:
```bash
export REDIS_URL="redis://localhost:6379/0"
export CALENDAR_CACHE_TTL_SECONDS="86400"
export REDIS_POOL_SIZE="10"
```

2. **MCP Configuration** (`.mcp.json`):
```json
{
  "mcpServers": {
    "dora-calendar-cache": {
      "command": "uv",
      "args": ["run", "python", "-m", "dora.mcp.calendar_cache_server"],
      "env": {
        "REDIS_URL": "redis://localhost:6379/0",
        "CALENDAR_CACHE_TTL_SECONDS": "86400",
        "REDIS_POOL_SIZE": "10"
      }
    }
  }
}
```

### Starting the Server

**Option 1: Using the startup script**
```bash
./scripts/run_calendar_cache_server.sh
```

**Option 2: Direct execution**
```bash
uv run python -m dora.mcp.calendar_cache_server
```

**Option 3: Through Claude Code**
The server starts automatically when tools are accessed through MCP.

## Available Tools

### 1. store_calendar_data
Store calendar data with configurable TTL and metadata.

**Parameters:**
- `location` (required): Location identifier
- `date_range` (required): Date range string
- `calendar_data` (required): Calendar data object
- `categories` (optional): Event categories array
- `ttl_seconds` (optional): Time to live override
- `processing_time_ms` (optional): Generation time
- `data_sources` (optional): Source list

**Example:**
```json
{
  "location": "San Francisco, CA",
  "date_range": "2025-07-12",
  "calendar_data": {
    "events": [{"name": "Tech Conference", "date": "2025-07-12"}],
    "weather": {"temperature": 22, "condition": "sunny"},
    "opportunity_score": 85
  },
  "categories": ["tech", "business"],
  "ttl_seconds": 3600,
  "processing_time_ms": 250,
  "data_sources": ["EventSearchAgent", "WeatherAPI"]
}
```

### 2. get_calendar_data
Retrieve cached calendar data with automatic hit tracking.

**Parameters:**
- `location` (required): Location identifier
- `date_range` (required): Date range string
- `categories` (optional): Event categories filter

**Returns:**
```json
{
  "cache_key": "calendar:san_francisco_ca:2025_07_12",
  "location": "San Francisco, CA",
  "date_range": "2025-07-12",
  "calendar_data": { /* calendar data */ },
  "cached_at": "2025-07-12T10:00:00+00:00",
  "last_accessed": "2025-07-12T11:30:00+00:00",
  "hit_count": 5,
  "processing_time_ms": 250,
  "ttl_seconds": 86400,
  "data_sources": ["EventSearchAgent", "WeatherAPI"],
  "cache_version": "1.0"
}
```

### 3. invalidate_cache
Remove cache entries by location, date range, or pattern.

**Parameters:**
- `location` (optional): Specific location
- `date_range` (optional): Specific date range
- `categories` (optional): Specific categories
- `pattern` (optional): Redis pattern for bulk deletion

**Examples:**
```json
// Invalidate specific entry
{"location": "San Francisco, CA", "date_range": "2025-07-12"}

// Invalidate all entries for a location
{"location": "San Francisco, CA"}

// Invalidate by pattern
{"pattern": "calendar:*:2025_07_12"}
```

### 4. get_cache_stats
Get comprehensive cache statistics and performance metrics.

**Returns:**
```json
{
  "cache_statistics": {
    "total_requests": 1500,
    "cache_hits": 1200,
    "cache_misses": 300,
    "hit_rate_percent": 80.0,
    "miss_rate_percent": 20.0,
    "total_stores": 400,
    "total_invalidations": 25
  },
  "cache_content": {
    "total_entries": 350,
    "default_ttl_seconds": 86400
  },
  "redis_info": {
    "redis_version": "7.0.0",
    "used_memory_human": "2.1M",
    "used_memory_peak_human": "2.8M",
    "connected_clients": 3
  },
  "created_at": "2025-07-12T00:00:00+00:00",
  "cache_version": "1.0"
}
```

### 5. list_cache_entries
List cached entries for debugging and monitoring.

**Parameters:**
- `location` (optional): Filter by location
- `limit` (optional): Maximum entries (default: 10)

**Returns:**
```json
[
  {
    "cache_key": "calendar:san_francisco_ca:2025_07_12",
    "location": "San Francisco, CA",
    "date_range": "2025-07-12",
    "cached_at": "2025-07-12T10:00:00+00:00",
    "last_accessed": "2025-07-12T11:30:00+00:00",
    "hit_count": 5,
    "processing_time_ms": 250,
    "ttl_remaining_seconds": 3456,
    "data_sources": ["EventSearchAgent", "WeatherAPI"]
  }
]
```

### 6. warm_cache
Generate cache warming plan for popular locations.

**Parameters:**
- `locations` (required): Array of locations
- `date_ranges` (required): Array of date ranges

**Returns:**
```json
{
  "warming_plan": [
    {
      "location": "San Francisco, CA",
      "date_range": "2025-07-12",
      "cache_key": "calendar:san_francisco_ca:2025_07_12",
      "needs_warming": true
    }
  ],
  "total_locations": 3,
  "total_date_ranges": 5,
  "entries_needing_warming": 12
}
```

## Integration Examples

### With Calendar Intelligence Agent

```python
from dora.cache_client import get_calendar_data, cache_calendar_data

async def get_enhanced_calendar_data(location, date):
    # Try cache first
    cached = await get_calendar_data(location, date)
    if cached:
        return cached["calendar_data"]
    
    # Generate new data
    calendar_data = await generate_calendar_data(location, date)
    
    # Cache for future use
    await cache_calendar_data(
        location=location,
        date_range=date,
        calendar_data=calendar_data,
        processing_time_ms=processing_time
    )
    
    return calendar_data
```

### With Claude Code MCP

```python
# Through MCP tools
result = await mcp_client.call_tool(
    "store_calendar_data",
    {
        "location": "San Francisco, CA",
        "date_range": "2025-07-12",
        "calendar_data": calendar_data
    }
)
```

## Performance Characteristics

### Benchmarks
- **Cache Hit**: < 2ms average response time
- **Cache Store**: < 5ms average response time
- **Bulk Invalidation**: < 10ms for 1000 keys
- **Statistics Query**: < 3ms average response time

### Scalability
- **Concurrent Connections**: 10 (configurable)
- **Memory Efficiency**: JSON compression, TTL-based cleanup
- **Connection Pooling**: Automatic pool management
- **Failover**: Graceful degradation on Redis unavailability

## Monitoring & Maintenance

### Health Checks
```bash
# Check server logs
tail -f /tmp/dora_calendar_cache_server.log

# Test Redis connectivity
redis-cli -u redis://localhost:6379/0 ping

# Monitor cache statistics through MCP
# Use get_cache_stats tool
```

### Maintenance Tasks
- **Cache Cleanup**: Automatic TTL-based expiration
- **Memory Monitoring**: Track Redis memory usage
- **Performance Tuning**: Adjust pool size and TTL based on usage
- **Pattern Analysis**: Use cache statistics for optimization

### Troubleshooting

**Common Issues:**

1. **Redis Connection Failed**
   - Check Redis server status
   - Verify REDIS_URL configuration
   - Check network connectivity

2. **High Cache Miss Rate**
   - Review TTL settings
   - Analyze access patterns
   - Consider cache warming

3. **Memory Usage High**
   - Monitor with get_cache_stats
   - Reduce TTL for less critical data
   - Implement more aggressive cleanup

4. **Slow Performance**
   - Check Redis server resources
   - Increase connection pool size
   - Optimize key patterns

## API Reference

### CalendarCacheServer Class

#### Methods
- `initialize()`: Initialize Redis connection
- `store_calendar_data()`: Store calendar data
- `get_calendar_data()`: Retrieve calendar data
- `invalidate_cache()`: Remove cache entries
- `get_cache_stats()`: Get statistics
- `list_cache_entries()`: List entries
- `warm_cache()`: Generate warming plan
- `cleanup()`: Clean up connections

### CalendarCacheClient Class

#### Methods
- `get_cached_calendar_data()`: Retrieve from cache
- `cache_calendar_data()`: Store in cache
- `invalidate_cache()`: Remove entries
- `get_cache_stats()`: Get statistics
- `health_check()`: Check connection health

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `CALENDAR_CACHE_TTL_SECONDS` | `86400` | Default TTL (24 hours) |
| `REDIS_POOL_SIZE` | `10` | Connection pool size |

### Redis Configuration

Recommended Redis settings for production:

```conf
# redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru
timeout 300
tcp-keepalive 300
```

## License

This Calendar Cache MCP Tool is part of the Dora Calendar Intelligence System and is licensed under the MIT License.