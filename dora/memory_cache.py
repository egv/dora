"""Memory cache integration for Dora using direct database access."""

import os
import sqlite3
import json
import hashlib
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

from dora.models.config import DoraConfig

logger = logging.getLogger(__name__)


class MemoryCache:
    """Direct database access to the memory cache."""
    
    def __init__(self, config: DoraConfig):
        """Initialize the memory cache client."""
        self.config = config
        self.cache_enabled = config.memory_cache_enabled
        self.db_path = config.memory_cache_path
        self.ttl_days = config.memory_cache_ttl_days
        self.cache_version = "1.0"
        
        if self.cache_enabled:
            # Ensure cache directory exists
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Initialize database
            self._init_db()
            
            # Clean up expired entries on startup
            self._cleanup_expired()
    
    def _init_db(self):
        """Initialize SQLite database with schema."""
        try:
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
        except Exception as e:
            logger.error(f"Failed to initialize cache database: {e}")
            self.cache_enabled = False
    
    def _cleanup_expired(self):
        """Remove expired cache entries."""
        if not self.cache_enabled:
            return
            
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.ttl_days)
            
            with sqlite3.connect(self.db_path) as conn:
                deleted = conn.execute(
                    "DELETE FROM events WHERE cached_at < ?",
                    (cutoff_date.isoformat(),)
                ).rowcount
                conn.commit()
                
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} expired cache entries")
        except Exception as e:
            logger.error(f"Failed to cleanup expired entries: {e}")
    
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
    
    def check_event(self, event_data: Dict[str, Any]) -> bool:
        """Check if an event exists in cache."""
        if not self.cache_enabled:
            return False
            
        try:
            event_id = self.generate_event_id(event_data)
            
            with sqlite3.connect(self.db_path) as conn:
                result = conn.execute(
                    "SELECT 1 FROM events WHERE event_id = ?",
                    (event_id,)
                ).fetchone()
                
            return result is not None
        except Exception as e:
            logger.error(f"Error checking event in cache: {e}")
            return False
    
    def get_event(self, event_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get cached event data."""
        if not self.cache_enabled:
            return None
            
        try:
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
                
                # Parse and return the result
                return {
                    "event_id": result[0],
                    "event_data": json.loads(result[1]),
                    "classification": json.loads(result[2]),
                    "notifications": json.loads(result[3]),
                    "cached_at": result[4],
                    "last_accessed": result[5],
                    "hit_count": result[6],
                    "processing_time_ms": result[7],
                    "cache_version": result[8]
                }
        except Exception as e:
            logger.error(f"Error getting event from cache: {e}")
            return None
    
    def store_event(
        self,
        event_data: Dict[str, Any],
        classification: Dict[str, Any],
        notifications: List[Dict[str, Any]],
        processing_time_ms: int = 0
    ) -> Optional[str]:
        """Store event data in cache."""
        if not self.cache_enabled:
            return None
            
        try:
            event_id = self.generate_event_id(event_data)
            now = datetime.now(timezone.utc)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO events 
                    (event_id, event_data, classification, notifications, cached_at, 
                     last_accessed, hit_count, processing_time_ms, cache_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event_id,
                    json.dumps(event_data),
                    json.dumps(classification),
                    json.dumps(notifications),
                    now.isoformat(),
                    now.isoformat(),
                    0,
                    processing_time_ms,
                    self.cache_version
                ))
                conn.commit()
            
            return event_id
        except Exception as e:
            logger.error(f"Error storing event in cache: {e}")
            return None
    
    def get_cache_stats(self) -> Optional[Dict[str, Any]]:
        """Get cache statistics."""
        if not self.cache_enabled:
            return None
            
        try:
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
                db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            
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
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return None