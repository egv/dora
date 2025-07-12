"""Event repository for managing event data."""

from datetime import datetime, date
from typing import Any, Dict, List, Optional, Union
from uuid import UUID
import asyncpg
import structlog

from dora.database.repositories.base import BaseRepository
from dora.database.connections import DatabaseManager
from dora.models.database_event import Event


logger = structlog.get_logger(__name__)


class EventRepository(BaseRepository[Event]):
    """Repository for managing event data in PostgreSQL."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize event repository."""
        super().__init__(db_manager, "events")
        self.logger = logger.bind(component="event_repository")
    
    def _row_to_model(self, row: asyncpg.Record) -> Event:
        """Convert database row to Event model."""
        return Event(
            id=row['id'],
            event_id=row['event_id'],
            name=row['name'],
            description=row['description'],
            location=row['location'],
            start_time=row['start_time'],
            end_time=row['end_time'],
            category=row['category'],
            attendance_estimate=row['attendance_estimate'],
            source=row['source'],
            url=row['url'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )
    
    def _model_to_dict(self, model: Event) -> Dict[str, Any]:
        """Convert Event model to dictionary for database storage."""
        return {
            'event_id': model.event_id,
            'name': model.name,
            'description': model.description,
            'location': model.location,
            'start_time': model.start_time,
            'end_time': model.end_time,
            'category': model.category,
            'attendance_estimate': model.attendance_estimate,
            'source': model.source,
            'url': model.url,
            'created_at': model.created_at or datetime.utcnow(),
            'updated_at': model.updated_at or datetime.utcnow()
        }
    
    async def find_by_event_id(self, event_id: str) -> Optional[Event]:
        """
        Find an event by its event_id (external ID).
        
        Args:
            event_id: External event identifier
            
        Returns:
            Event if found, None otherwise
        """
        try:
            async with self.db_manager.get_postgres_connection() as conn:
                query = "SELECT * FROM events WHERE event_id = $1"
                row = await conn.fetchrow(query, event_id)
                
                if row:
                    return self._row_to_model(row)
                return None
                
        except Exception as e:
            self.logger.error("Error finding event by event_id", 
                            event_id=event_id, error=str(e))
            raise
    
    async def find_by_location_and_date_range(self, 
                                            location: str,
                                            start_date: datetime,
                                            end_date: datetime,
                                            limit: int = 1000) -> List[Event]:
        """
        Find events by location within a date range.
        
        Args:
            location: Location to search (case-insensitive contains)
            start_date: Start of date range
            end_date: End of date range
            limit: Maximum number of events to return
            
        Returns:
            List of events matching criteria
        """
        try:
            async with self.db_manager.get_postgres_connection() as conn:
                query = """
                    SELECT * FROM events 
                    WHERE LOWER(location) LIKE LOWER($1)
                    AND start_time >= $2 
                    AND start_time <= $3
                    ORDER BY start_time ASC
                    LIMIT $4
                """
                
                location_pattern = f"%{location}%"
                rows = await conn.fetch(query, location_pattern, start_date, end_date, limit)
                
                events = [self._row_to_model(row) for row in rows]
                
                self.logger.info("Found events by location and date range",
                               location=location,
                               start_date=start_date.isoformat(),
                               end_date=end_date.isoformat(),
                               count=len(events))
                
                return events
                
        except Exception as e:
            self.logger.error("Error finding events by location and date range",
                            location=location, error=str(e))
            raise
    
    async def find_by_category(self, 
                              category: str,
                              limit: int = 1000,
                              offset: int = 0) -> List[Event]:
        """
        Find events by category.
        
        Args:
            category: Event category
            limit: Maximum number of events
            offset: Number of events to skip
            
        Returns:
            List of events in the category
        """
        return await self.find_by_criteria(
            "category = $1",
            [category],
            order_by="start_time ASC",
            limit=limit,
            offset=offset
        )
    
    async def find_upcoming_events(self, 
                                  location: Optional[str] = None,
                                  days_ahead: int = 30,
                                  limit: int = 1000) -> List[Event]:
        """
        Find upcoming events.
        
        Args:
            location: Optional location filter
            days_ahead: Number of days ahead to search
            limit: Maximum number of events
            
        Returns:
            List of upcoming events
        """
        try:
            now = datetime.utcnow()
            end_date = now.replace(hour=23, minute=59, second=59) + \
                      datetime.timedelta(days=days_ahead)
            
            if location:
                where_clause = "LOWER(location) LIKE LOWER($1) AND start_time >= $2 AND start_time <= $3"
                params = [f"%{location}%", now, end_date]
            else:
                where_clause = "start_time >= $1 AND start_time <= $2"
                params = [now, end_date]
            
            return await self.find_by_criteria(
                where_clause,
                params,
                order_by="start_time ASC",
                limit=limit
            )
            
        except Exception as e:
            self.logger.error("Error finding upcoming events", 
                            location=location, days_ahead=days_ahead, error=str(e))
            raise
    
    async def find_by_source(self, 
                           source: str,
                           limit: int = 1000,
                           offset: int = 0) -> List[Event]:
        """
        Find events by source.
        
        Args:
            source: Event source
            limit: Maximum number of events
            offset: Number of events to skip
            
        Returns:
            List of events from the source
        """
        return await self.find_by_criteria(
            "source = $1",
            [source],
            order_by="start_time DESC",
            limit=limit,
            offset=offset
        )
    
    async def search_events(self, 
                          query: str,
                          location: Optional[str] = None,
                          category: Optional[str] = None,
                          start_date: Optional[datetime] = None,
                          end_date: Optional[datetime] = None,
                          limit: int = 100) -> List[Event]:
        """
        Search events with full-text search and filters.
        
        Args:
            query: Search query for name and description
            location: Optional location filter
            category: Optional category filter
            start_date: Optional start date filter
            end_date: Optional end date filter
            limit: Maximum number of events
            
        Returns:
            List of matching events
        """
        try:
            where_conditions = []
            params = []
            param_count = 0
            
            # Text search
            if query:
                param_count += 1
                where_conditions.append(f"""
                    (LOWER(name) LIKE LOWER(${param_count}) 
                     OR LOWER(description) LIKE LOWER(${param_count}))
                """)
                params.append(f"%{query}%")
            
            # Location filter
            if location:
                param_count += 1
                where_conditions.append(f"LOWER(location) LIKE LOWER(${param_count})")
                params.append(f"%{location}%")
            
            # Category filter
            if category:
                param_count += 1
                where_conditions.append(f"category = ${param_count}")
                params.append(category)
            
            # Date range filters
            if start_date:
                param_count += 1
                where_conditions.append(f"start_time >= ${param_count}")
                params.append(start_date)
            
            if end_date:
                param_count += 1
                where_conditions.append(f"start_time <= ${param_count}")
                params.append(end_date)
            
            if not where_conditions:
                # No filters, return recent events
                return await self.find_by_criteria(
                    "start_time >= $1",
                    [datetime.utcnow()],
                    order_by="start_time ASC",
                    limit=limit
                )
            
            where_clause = " AND ".join(where_conditions)
            
            events = await self.find_by_criteria(
                where_clause,
                params,
                order_by="start_time ASC",
                limit=limit
            )
            
            self.logger.info("Event search completed",
                           query=query,
                           location=location,
                           category=category,
                           results_count=len(events))
            
            return events
            
        except Exception as e:
            self.logger.error("Error searching events", 
                            query=query, location=location, error=str(e))
            raise
    
    async def get_events_stats(self, location: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics about events.
        
        Args:
            location: Optional location filter
            
        Returns:
            Dictionary with event statistics
        """
        try:
            async with self.db_manager.get_postgres_connection() as conn:
                base_conditions = ""
                params = []
                
                if location:
                    base_conditions = "WHERE LOWER(location) LIKE LOWER($1)"
                    params = [f"%{location}%"]
                
                # Total events
                total_query = f"SELECT COUNT(*) FROM events {base_conditions}"
                total_events = await conn.fetchval(total_query, *params)
                
                # Events by category
                category_query = f"""
                    SELECT category, COUNT(*) as count 
                    FROM events {base_conditions}
                    GROUP BY category 
                    ORDER BY count DESC
                """
                category_rows = await conn.fetch(category_query, *params)
                categories = {row['category']: row['count'] for row in category_rows}
                
                # Events by source
                source_query = f"""
                    SELECT source, COUNT(*) as count 
                    FROM events {base_conditions}
                    GROUP BY source 
                    ORDER BY count DESC
                """
                source_rows = await conn.fetch(source_query, *params)
                sources = {row['source']: row['count'] for row in source_rows}
                
                # Upcoming events (next 30 days)
                now = datetime.utcnow()
                upcoming_end = now + datetime.timedelta(days=30)
                
                upcoming_conditions = f"start_time >= $1 AND start_time <= $2"
                upcoming_params = [now, upcoming_end]
                
                if location:
                    upcoming_conditions += f" AND LOWER(location) LIKE LOWER($3)"
                    upcoming_params.append(f"%{location}%")
                
                upcoming_query = f"SELECT COUNT(*) FROM events WHERE {upcoming_conditions}"
                upcoming_events = await conn.fetchval(upcoming_query, *upcoming_params)
                
                stats = {
                    "total_events": total_events,
                    "upcoming_events": upcoming_events,
                    "categories": categories,
                    "sources": sources,
                    "location_filter": location
                }
                
                self.logger.info("Generated event statistics", 
                               location=location, total_events=total_events)
                
                return stats
                
        except Exception as e:
            self.logger.error("Error getting event statistics", 
                            location=location, error=str(e))
            raise
    
    async def bulk_upsert(self, events: List[Event]) -> Dict[str, int]:
        """
        Bulk upsert events (insert or update on conflict).
        
        Args:
            events: List of events to upsert
            
        Returns:
            Dictionary with counts of inserted and updated records
        """
        if not events:
            return {"inserted": 0, "updated": 0}
        
        try:
            inserted = 0
            updated = 0
            
            async with self.db_manager.get_postgres_transaction() as conn:
                for event in events:
                    data = self._model_to_dict(event)
                    
                    # Check if event exists
                    existing = await conn.fetchval(
                        "SELECT id FROM events WHERE event_id = $1",
                        event.event_id
                    )
                    
                    if existing:
                        # Update existing event
                        update_fields = {k: v for k, v in data.items() 
                                       if k not in ['created_at']}
                        update_fields['updated_at'] = datetime.utcnow()
                        
                        set_clauses = [f"{col} = ${i+2}" for i, col in enumerate(update_fields.keys())]
                        values = [event.event_id] + list(update_fields.values())
                        
                        update_query = f"""
                            UPDATE events 
                            SET {', '.join(set_clauses)}
                            WHERE event_id = $1
                        """
                        
                        await conn.execute(update_query, *values)
                        updated += 1
                    else:
                        # Insert new event
                        columns = list(data.keys())
                        placeholders = [f"${i+1}" for i in range(len(columns))]
                        values = list(data.values())
                        
                        insert_query = f"""
                            INSERT INTO events ({', '.join(columns)})
                            VALUES ({', '.join(placeholders)})
                        """
                        
                        await conn.execute(insert_query, *values)
                        inserted += 1
            
            result = {"inserted": inserted, "updated": updated}
            
            self.logger.info("Bulk upsert completed", 
                           total_events=len(events), **result)
            
            return result
            
        except Exception as e:
            self.logger.error("Error in bulk upsert", 
                            event_count=len(events), error=str(e))
            raise
    
    # Cache-specific methods
    async def get_cached_events(self, 
                              location: str, 
                              date: date) -> Optional[List[Event]]:
        """Get cached events for a location and date."""
        cache_key = f"events:{location.lower()}:{date.isoformat()}"
        cached_data = await self.cache_get(cache_key)
        
        if cached_data:
            return [Event(**event_data) for event_data in cached_data]
        
        return None
    
    async def cache_events(self, 
                         location: str, 
                         date: date, 
                         events: List[Event],
                         expiry: int = 3600) -> None:
        """Cache events for a location and date."""
        cache_key = f"events:{location.lower()}:{date.isoformat()}"
        event_data = [event.dict() for event in events]
        await self.cache_set(cache_key, event_data, expiry)
    
    async def clear_location_cache(self, location: str) -> int:
        """Clear all cached events for a location."""
        pattern = f"events:{location.lower()}:*"
        return await self.cache_clear_pattern(pattern)