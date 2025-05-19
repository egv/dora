"""MCP Memory Server for Dora - Persistent event cache."""

import asyncio
import os
import sqlite3
import json
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

logger = logging.getLogger(__name__)


class EventCacheEntry:
    """Model for cached event data."""
    def __init__(self, **kwargs):
        self.event_id = kwargs.get('event_id')
        self.event_data = kwargs.get('event_data')
        self.classification = kwargs.get('classification')
        self.notifications = kwargs.get('notifications')
        self.cached_at = kwargs.get('cached_at')
        self.last_accessed = kwargs.get('last_accessed')
        self.hit_count = kwargs.get('hit_count', 0)
        self.processing_time_ms = kwargs.get('processing_time_ms', 0)
        self.cache_version = kwargs.get('cache_version', "1.0")


class MemoryServer:
    """MCP server for persistent event memory cache."""
    
    def __init__(self, db_path: str = None):
        """Initialize the memory server with SQLite backend."""
        self.db_path = db_path or os.getenv("MEMORY_CACHE_PATH", "./cache/dora_memory.db")
        self.ttl_days = int(os.getenv("MEMORY_CACHE_TTL_DAYS", "7"))
        self.cache_version = "1.0"
        
        # Ensure cache directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_db()
        
        # Clean up expired entries on startup
        self._cleanup_expired()
    
    def _init_db(self):
        """Initialize SQLite database with schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    event_data TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    notifications TEXT NOT NULL,
                    cached_at TIMESTAMP NOT NULL,
                    last_accessed TIMESTAMP NOT NULL,
                    hit_count INTEGER DEFAULT 0,
                    processing_time_ms INTEGER DEFAULT 0,
                    cache_version TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cached_at ON events(cached_at)
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            
            conn.commit()
    
    def _cleanup_expired(self):
        """Remove expired cache entries."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.ttl_days)
        
        with sqlite3.connect(self.db_path) as conn:
            deleted = conn.execute(
                "DELETE FROM events WHERE cached_at < ?",
                (cutoff_date.isoformat(),)
            ).rowcount
            conn.commit()
            
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired cache entries")
    
    @staticmethod
    def generate_event_id(event_data: Dict[str, Any]) -> str:
        """Generate unique ID for an event based on key attributes."""
        # Use name, start_date, location, and URL (if available)
        key_parts = [
            event_data.get("name", ""),
            event_data.get("start_date", ""),
            event_data.get("location", ""),
            event_data.get("url", "")
        ]
        
        key_string = "|".join(str(part) for part in key_parts)
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]
    
    async def check_event(self, event_data: Dict[str, Any]) -> bool:
        """Check if an event exists in cache."""
        event_id = self.generate_event_id(event_data)
        
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "SELECT 1 FROM events WHERE event_id = ?",
                (event_id,)
            ).fetchone()
            
        return result is not None
    
    async def get_event(self, event_data: Dict[str, Any]) -> Optional[EventCacheEntry]:
        """Retrieve cached event data."""
        event_id = self.generate_event_id(event_data)
        
        with sqlite3.connect(self.db_path) as conn:
            # Get the event
            result = conn.execute(
                "SELECT * FROM events WHERE event_id = ?",
                (event_id,)
            ).fetchone()
            
            if not result:
                return None
            
            # Update access time and hit count
            now = datetime.now(timezone.utc)
            conn.execute(
                "UPDATE events SET last_accessed = ?, hit_count = hit_count + 1 WHERE event_id = ?",
                (now.isoformat(), event_id)
            )
            conn.commit()
            
            # Parse the result
            return EventCacheEntry(
                event_id=result[0],
                event_data=json.loads(result[1]),
                classification=json.loads(result[2]),
                notifications=json.loads(result[3]),
                cached_at=datetime.fromisoformat(result[4]),
                last_accessed=datetime.fromisoformat(result[5]),
                hit_count=result[6],
                processing_time_ms=result[7],
                cache_version=result[8]
            )
    
    async def store_event(
        self,
        event_data: Dict[str, Any],
        classification: Dict[str, Any],
        notifications: List[Dict[str, Any]],
        processing_time_ms: int = 0
    ) -> str:
        """Store processed event data in cache."""
        event_id = self.generate_event_id(event_data)
        now = datetime.now(timezone.utc)
        
        entry = EventCacheEntry(
            event_id=event_id,
            event_data=event_data,
            classification=classification,
            notifications=notifications,
            cached_at=now,
            last_accessed=now,
            hit_count=0,
            processing_time_ms=processing_time_ms,
            cache_version=self.cache_version
        )
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO events 
                (event_id, event_data, classification, notifications, cached_at, 
                 last_accessed, hit_count, processing_time_ms, cache_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.event_id,
                json.dumps(entry.event_data),
                json.dumps(entry.classification),
                json.dumps(entry.notifications),
                entry.cached_at.isoformat(),
                entry.last_accessed.isoformat(),
                entry.hit_count,
                entry.processing_time_ms,
                entry.cache_version
            ))
            conn.commit()
        
        return event_id
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with sqlite3.connect(self.db_path) as conn:
            # Total entries
            total_entries = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            
            # Cache hit rate (entries with hit_count > 0)
            hits = conn.execute("SELECT COUNT(*) FROM events WHERE hit_count > 0").fetchone()[0]
            
            # Average hit count
            avg_hits = conn.execute("SELECT AVG(hit_count) FROM events").fetchone()[0] or 0
            
            # Oldest and newest entries
            oldest = conn.execute("SELECT MIN(cached_at) FROM events").fetchone()[0]
            newest = conn.execute("SELECT MAX(cached_at) FROM events").fetchone()[0]
            
            # Average processing time
            avg_processing_time = conn.execute("SELECT AVG(processing_time_ms) FROM events").fetchone()[0] or 0
            
            # Database size
            db_size = os.path.getsize(self.db_path)
        
        return {
            "total_entries": total_entries,
            "cache_hits": hits,
            "hit_rate": (hits / total_entries * 100) if total_entries > 0 else 0,
            "average_hits_per_entry": avg_hits,
            "oldest_entry": oldest,
            "newest_entry": newest,
            "average_processing_time_ms": avg_processing_time,
            "database_size_bytes": db_size,
            "database_size_mb": db_size / (1024 * 1024),
            "ttl_days": self.ttl_days,
            "cache_version": self.cache_version
        }
    
    async def clear_cache(self, older_than_days: Optional[int] = None) -> int:
        """Clear cache entries older than specified days."""
        if older_than_days is None:
            # Clear all
            with sqlite3.connect(self.db_path) as conn:
                deleted = conn.execute("DELETE FROM events").rowcount
                conn.commit()
        else:
            # Clear entries older than specified days
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)
            with sqlite3.connect(self.db_path) as conn:
                deleted = conn.execute(
                    "DELETE FROM events WHERE cached_at < ?",
                    (cutoff_date.isoformat(),)
                ).rowcount
                conn.commit()
        
        return deleted
    
    async def list_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List cached events for debugging."""
        with sqlite3.connect(self.db_path) as conn:
            results = conn.execute("""
                SELECT event_id, event_data, cached_at, last_accessed, hit_count
                FROM events
                ORDER BY last_accessed DESC
                LIMIT ?
            """, (limit,)).fetchall()
        
        events = []
        for row in results:
            event_data = json.loads(row[1])
            events.append({
                "event_id": row[0],
                "name": event_data.get("name"),
                "location": event_data.get("location"),
                "start_date": event_data.get("start_date"),
                "cached_at": row[2],
                "last_accessed": row[3],
                "hit_count": row[4]
            })
        
        return events


# Create MCP server
memory_server = MemoryServer()
server = Server("dora-memory")


@server.list_tools()
async def list_tools() -> List[Tool]:
    """List available tools."""
    return [
        Tool(
            name="check_event",
            description="Check if an event exists in the cache",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_data": {
                        "type": "object",
                        "description": "Event data containing name, start_date, location, and optionally url",
                        "properties": {
                            "name": {"type": "string"},
                            "start_date": {"type": "string"},
                            "location": {"type": "string"},
                            "url": {"type": "string"}
                        },
                        "required": ["name", "start_date", "location"]
                    }
                },
                "required": ["event_data"]
            }
        ),
        Tool(
            name="get_event",
            description="Retrieve cached event data",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_data": {
                        "type": "object",
                        "description": "Event data containing name, start_date, location, and optionally url",
                        "properties": {
                            "name": {"type": "string"},
                            "start_date": {"type": "string"},
                            "location": {"type": "string"},
                            "url": {"type": "string"}
                        },
                        "required": ["name", "start_date", "location"]
                    }
                },
                "required": ["event_data"]
            }
        ),
        Tool(
            name="store_event",
            description="Store processed event data in cache",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_data": {
                        "type": "object",
                        "description": "Original event data"
                    },
                    "classification": {
                        "type": "object",
                        "description": "Event classification (size, importance, audiences)"
                    },
                    "notifications": {
                        "type": "array",
                        "description": "List of generated notifications",
                        "items": {"type": "object"}
                    },
                    "processing_time_ms": {
                        "type": "integer",
                        "description": "Time taken to process the event",
                        "default": 0
                    }
                },
                "required": ["event_data", "classification", "notifications"]
            }
        ),
        Tool(
            name="cache_stats",
            description="Get cache statistics",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="clear_cache",
            description="Clear cache entries",
            inputSchema={
                "type": "object",
                "properties": {
                    "older_than_days": {
                        "type": "integer",
                        "description": "Clear entries older than this many days. If not provided, clear all."
                    }
                }
            }
        ),
        Tool(
            name="list_events",
            description="List cached events for debugging",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of events to return",
                        "default": 10
                    }
                }
            }
        )
    ]


@server.call_tool()
async def call_tool(tool_name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls."""
    try:
        if tool_name == "check_event":
            result = await memory_server.check_event(arguments["event_data"])
            return [TextContent(type="text", text=json.dumps({"exists": result}))]
        
        elif tool_name == "get_event":
            entry = await memory_server.get_event(arguments["event_data"])
            if entry:
                result = {
                    "event_id": entry.event_id,
                    "event_data": entry.event_data,
                    "classification": entry.classification,
                    "notifications": entry.notifications,
                    "cached_at": entry.cached_at.isoformat() if isinstance(entry.cached_at, datetime) else entry.cached_at,
                    "last_accessed": entry.last_accessed.isoformat() if isinstance(entry.last_accessed, datetime) else entry.last_accessed,
                    "hit_count": entry.hit_count,
                    "processing_time_ms": entry.processing_time_ms,
                    "cache_version": entry.cache_version
                }
                return [TextContent(type="text", text=json.dumps(result))]
            else:
                return [TextContent(type="text", text=json.dumps(None))]
        
        elif tool_name == "store_event":
            event_id = await memory_server.store_event(
                event_data=arguments["event_data"],
                classification=arguments["classification"],
                notifications=arguments["notifications"],
                processing_time_ms=arguments.get("processing_time_ms", 0)
            )
            return [TextContent(type="text", text=json.dumps({"event_id": event_id}))]
        
        elif tool_name == "cache_stats":
            stats = await memory_server.get_cache_stats()
            return [TextContent(type="text", text=json.dumps(stats))]
        
        elif tool_name == "clear_cache":
            deleted = await memory_server.clear_cache(arguments.get("older_than_days"))
            return [TextContent(type="text", text=json.dumps({"deleted_entries": deleted}))]
        
        elif tool_name == "list_events":
            events = await memory_server.list_events(arguments.get("limit", 10))
            return [TextContent(type="text", text=json.dumps(events))]
        
        else:
            return [TextContent(type="text", text=f"Unknown tool: {tool_name}")]
    
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# Run the server
async def main():
    """Run the MCP server."""
    # Set up logging to file instead of stdout (since we use stdio for MCP)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        filename='/tmp/dora_memory_server.log',
        filemode='a'
    )
    
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


if __name__ == "__main__":
    asyncio.run(main())