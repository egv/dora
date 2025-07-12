"""Calendar insights repository for managing AI-generated calendar insights."""

from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Union
from uuid import UUID
from dataclasses import dataclass
import asyncpg
import structlog

from dora.database.repositories.base import BaseRepository
from dora.database.connections import DatabaseManager


logger = structlog.get_logger(__name__)


@dataclass
class CalendarInsights:
    """Calendar insights data model."""
    location: str
    insight_date: date
    insights: Dict[str, Any]
    opportunity_score: Optional[float] = None
    marketing_recommendations: Optional[List[str]] = None
    conflict_warnings: Optional[List[str]] = None
    weather_impact: Optional[str] = None
    event_density: Optional[str] = None
    peak_hours: Optional[List[str]] = None
    generated_by: Optional[str] = None
    confidence_score: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'location': self.location,
            'insight_date': self.insight_date,
            'insights': self.insights,
            'opportunity_score': self.opportunity_score,
            'marketing_recommendations': self.marketing_recommendations,
            'conflict_warnings': self.conflict_warnings,
            'weather_impact': self.weather_impact,
            'event_density': self.event_density,
            'peak_hours': self.peak_hours,
            'generated_by': self.generated_by,
            'confidence_score': self.confidence_score,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class CalendarInsightsRepository(BaseRepository[CalendarInsights]):
    """Repository for managing calendar insights data in PostgreSQL."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize calendar insights repository."""
        super().__init__(db_manager, "calendar_insights")
        self.logger = logger.bind(component="calendar_insights_repository")
    
    def _row_to_model(self, row: asyncpg.Record) -> CalendarInsights:
        """Convert database row to CalendarInsights model."""
        return CalendarInsights(
            location=row['location'],
            insight_date=row['insight_date'],
            insights=row['insights'],
            opportunity_score=row['opportunity_score'],
            marketing_recommendations=row['marketing_recommendations'],
            conflict_warnings=row['conflict_warnings'],
            weather_impact=row['weather_impact'],
            event_density=row['event_density'],
            peak_hours=row['peak_hours'],
            generated_by=row['generated_by'],
            confidence_score=row['confidence_score'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )
    
    def _model_to_dict(self, model: CalendarInsights) -> Dict[str, Any]:
        """Convert CalendarInsights model to dictionary for database storage."""
        return {
            'location': model.location,
            'insight_date': model.insight_date,
            'insights': model.insights,
            'opportunity_score': model.opportunity_score,
            'marketing_recommendations': model.marketing_recommendations,
            'conflict_warnings': model.conflict_warnings,
            'weather_impact': model.weather_impact,
            'event_density': model.event_density,
            'peak_hours': model.peak_hours,
            'generated_by': model.generated_by,
            'confidence_score': model.confidence_score,
            'created_at': model.created_at or datetime.utcnow(),
            'updated_at': model.updated_at or datetime.utcnow()
        }
    
    async def find_by_location_and_date(self, location: str, insight_date: date) -> Optional[CalendarInsights]:
        """
        Find calendar insights by location and date.
        
        Args:
            location: Location name
            insight_date: Date for insights
            
        Returns:
            CalendarInsights if found, None otherwise
        """
        try:
            async with self.db_manager.get_postgres_connection() as conn:
                query = "SELECT * FROM calendar_insights WHERE LOWER(location) = LOWER($1) AND insight_date = $2"
                row = await conn.fetchrow(query, location, insight_date)
                
                if row:
                    return self._row_to_model(row)
                return None
                
        except Exception as e:
            self.logger.error("Error finding insights by location and date",
                            location=location, date=insight_date.isoformat(), error=str(e))
            raise
    
    async def find_by_location_date_range(self, 
                                        location: str,
                                        start_date: date,
                                        end_date: date) -> List[CalendarInsights]:
        """
        Find calendar insights for a location within a date range.
        
        Args:
            location: Location name
            start_date: Start date
            end_date: End date
            
        Returns:
            List of calendar insights within the date range
        """
        try:
            async with self.db_manager.get_postgres_connection() as conn:
                query = """
                    SELECT * FROM calendar_insights 
                    WHERE LOWER(location) = LOWER($1)
                    AND insight_date >= $2 
                    AND insight_date <= $3
                    ORDER BY insight_date ASC
                """
                
                rows = await conn.fetch(query, location, start_date, end_date)
                
                insights = [self._row_to_model(row) for row in rows]
                
                self.logger.info("Found insights by location and date range",
                               location=location,
                               start_date=start_date.isoformat(),
                               end_date=end_date.isoformat(),
                               count=len(insights))
                
                return insights
                
        except Exception as e:
            self.logger.error("Error finding insights by location and date range",
                            location=location, error=str(e))
            raise
    
    async def find_recent_insights(self, 
                                 location: str,
                                 days_back: int = 7) -> List[CalendarInsights]:
        """
        Find recent calendar insights for a location.
        
        Args:
            location: Location name
            days_back: Number of days back to search
            
        Returns:
            List of recent calendar insights
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days_back)
        
        return await self.find_by_location_date_range(location, start_date, end_date)
    
    async def find_by_opportunity_score_range(self, 
                                            min_score: float,
                                            max_score: float,
                                            location: Optional[str] = None,
                                            limit: int = 1000) -> List[CalendarInsights]:
        """
        Find calendar insights within an opportunity score range.
        
        Args:
            min_score: Minimum opportunity score
            max_score: Maximum opportunity score
            location: Optional location filter
            limit: Maximum number of records
            
        Returns:
            List of insights within the score range
        """
        try:
            where_conditions = ["opportunity_score >= $1 AND opportunity_score <= $2"]
            params = [min_score, max_score]
            param_count = 2
            
            if location:
                param_count += 1
                where_conditions.append(f"LOWER(location) = LOWER(${param_count})")
                params.append(location)
            
            where_clause = " AND ".join(where_conditions)
            
            return await self.find_by_criteria(
                where_clause,
                params,
                order_by="opportunity_score DESC",
                limit=limit
            )
            
        except Exception as e:
            self.logger.error("Error finding insights by opportunity score range",
                            min_score=min_score, max_score=max_score, error=str(e))
            raise
    
    async def find_high_opportunity_insights(self, 
                                           threshold: float = 0.7,
                                           location: Optional[str] = None,
                                           days_ahead: int = 30,
                                           limit: int = 100) -> List[CalendarInsights]:
        """
        Find high-opportunity insights for upcoming dates.
        
        Args:
            threshold: Minimum opportunity score threshold
            location: Optional location filter
            days_ahead: Number of days ahead to search
            limit: Maximum number of insights
            
        Returns:
            List of high-opportunity insights
        """
        try:
            start_date = date.today()
            end_date = start_date + timedelta(days=days_ahead)
            
            where_conditions = [
                "opportunity_score >= $1",
                "insight_date >= $2",
                "insight_date <= $3"
            ]
            params = [threshold, start_date, end_date]
            param_count = 3
            
            if location:
                param_count += 1
                where_conditions.append(f"LOWER(location) = LOWER(${param_count})")
                params.append(location)
            
            where_clause = " AND ".join(where_conditions)
            
            return await self.find_by_criteria(
                where_clause,
                params,
                order_by="opportunity_score DESC, insight_date ASC",
                limit=limit
            )
            
        except Exception as e:
            self.logger.error("Error finding high opportunity insights",
                            threshold=threshold, location=location, error=str(e))
            raise
    
    async def find_insights_with_conflicts(self, 
                                         location: Optional[str] = None,
                                         limit: int = 1000) -> List[CalendarInsights]:
        """
        Find insights that have conflict warnings.
        
        Args:
            location: Optional location filter
            limit: Maximum number of insights
            
        Returns:
            List of insights with conflicts
        """
        try:
            where_conditions = ["conflict_warnings IS NOT NULL AND array_length(conflict_warnings, 1) > 0"]
            params = []
            param_count = 0
            
            if location:
                param_count += 1
                where_conditions.append(f"LOWER(location) = LOWER(${param_count})")
                params.append(location)
            
            where_clause = " AND ".join(where_conditions)
            
            return await self.find_by_criteria(
                where_clause,
                params,
                order_by="insight_date DESC",
                limit=limit
            )
            
        except Exception as e:
            self.logger.error("Error finding insights with conflicts",
                            location=location, error=str(e))
            raise
    
    async def get_insights_stats(self, 
                               location: Optional[str] = None,
                               start_date: Optional[date] = None,
                               end_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Get calendar insights statistics.
        
        Args:
            location: Optional location filter
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Dictionary with insights statistics
        """
        try:
            async with self.db_manager.get_postgres_connection() as conn:
                where_conditions = []
                params = []
                param_count = 0
                
                if location:
                    param_count += 1
                    where_conditions.append(f"LOWER(location) = LOWER(${param_count})")
                    params.append(location)
                
                if start_date:
                    param_count += 1
                    where_conditions.append(f"insight_date >= ${param_count}")
                    params.append(start_date)
                
                if end_date:
                    param_count += 1
                    where_conditions.append(f"insight_date <= ${param_count}")
                    params.append(end_date)
                
                where_clause = ""
                if where_conditions:
                    where_clause = "WHERE " + " AND ".join(where_conditions)
                
                # Basic statistics
                stats_query = f"""
                    SELECT 
                        COUNT(*) as total_insights,
                        AVG(opportunity_score) as avg_opportunity_score,
                        MIN(opportunity_score) as min_opportunity_score,
                        MAX(opportunity_score) as max_opportunity_score,
                        AVG(confidence_score) as avg_confidence_score,
                        COUNT(CASE WHEN conflict_warnings IS NOT NULL AND array_length(conflict_warnings, 1) > 0 THEN 1 END) as insights_with_conflicts
                    FROM calendar_insights {where_clause}
                """
                
                stats = await conn.fetchrow(stats_query, *params)
                
                # Event density distribution
                density_query = f"""
                    SELECT event_density, COUNT(*) as count
                    FROM calendar_insights {where_clause}
                    WHERE event_density IS NOT NULL
                    GROUP BY event_density
                    ORDER BY count DESC
                """
                
                density_rows = await conn.fetch(density_query, *params)
                density_distribution = {row['event_density']: row['count'] for row in density_rows}
                
                # Weather impact distribution
                weather_query = f"""
                    SELECT weather_impact, COUNT(*) as count
                    FROM calendar_insights {where_clause}
                    WHERE weather_impact IS NOT NULL
                    GROUP BY weather_impact
                    ORDER BY count DESC
                """
                
                weather_rows = await conn.fetch(weather_query, *params)
                weather_distribution = {row['weather_impact']: row['count'] for row in weather_rows}
                
                # Generated by distribution
                generator_query = f"""
                    SELECT generated_by, COUNT(*) as count
                    FROM calendar_insights {where_clause}
                    WHERE generated_by IS NOT NULL
                    GROUP BY generated_by
                    ORDER BY count DESC
                """
                
                generator_rows = await conn.fetch(generator_query, *params)
                generator_distribution = {row['generated_by']: row['count'] for row in generator_rows}
                
                result = {
                    "total_insights": stats['total_insights'] or 0,
                    "opportunity_score": {
                        "average": float(stats['avg_opportunity_score']) if stats['avg_opportunity_score'] else None,
                        "minimum": float(stats['min_opportunity_score']) if stats['min_opportunity_score'] else None,
                        "maximum": float(stats['max_opportunity_score']) if stats['max_opportunity_score'] else None
                    },
                    "confidence_score": {
                        "average": float(stats['avg_confidence_score']) if stats['avg_confidence_score'] else None
                    },
                    "insights_with_conflicts": stats['insights_with_conflicts'] or 0,
                    "event_density_distribution": density_distribution,
                    "weather_impact_distribution": weather_distribution,
                    "generator_distribution": generator_distribution,
                    "filters": {
                        "location": location,
                        "start_date": start_date.isoformat() if start_date else None,
                        "end_date": end_date.isoformat() if end_date else None
                    }
                }
                
                self.logger.info("Generated insights statistics",
                               location=location,
                               total_insights=result["total_insights"])
                
                return result
                
        except Exception as e:
            self.logger.error("Error getting insights statistics", 
                            location=location, error=str(e))
            raise
    
    async def upsert_insights(self, insights: CalendarInsights) -> CalendarInsights:
        """
        Insert or update calendar insights (upsert by location and date).
        
        Args:
            insights: Calendar insights to upsert
            
        Returns:
            Upserted calendar insights
        """
        try:
            data = self._model_to_dict(insights)
            
            async with self.db_manager.get_postgres_connection() as conn:
                query = """
                    INSERT INTO calendar_insights (
                        location, insight_date, insights, opportunity_score,
                        marketing_recommendations, conflict_warnings, weather_impact,
                        event_density, peak_hours, generated_by, confidence_score,
                        created_at, updated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    ON CONFLICT (location, insight_date)
                    DO UPDATE SET
                        insights = EXCLUDED.insights,
                        opportunity_score = EXCLUDED.opportunity_score,
                        marketing_recommendations = EXCLUDED.marketing_recommendations,
                        conflict_warnings = EXCLUDED.conflict_warnings,
                        weather_impact = EXCLUDED.weather_impact,
                        event_density = EXCLUDED.event_density,
                        peak_hours = EXCLUDED.peak_hours,
                        generated_by = EXCLUDED.generated_by,
                        confidence_score = EXCLUDED.confidence_score,
                        updated_at = EXCLUDED.updated_at
                    RETURNING *
                """
                
                row = await conn.fetchrow(
                    query,
                    data['location'], data['insight_date'], data['insights'],
                    data['opportunity_score'], data['marketing_recommendations'],
                    data['conflict_warnings'], data['weather_impact'],
                    data['event_density'], data['peak_hours'], data['generated_by'],
                    data['confidence_score'], data['created_at'], data['updated_at']
                )
                
                result = self._row_to_model(row)
                
                self.logger.info("Calendar insights upserted",
                               location=insights.location,
                               date=insights.insight_date.isoformat())
                
                return result
                
        except Exception as e:
            self.logger.error("Error upserting calendar insights",
                            location=insights.location, 
                            date=insights.insight_date.isoformat(), 
                            error=str(e))
            raise
    
    async def bulk_upsert_insights(self, insights_list: List[CalendarInsights]) -> int:
        """
        Bulk upsert calendar insights.
        
        Args:
            insights_list: List of calendar insights to upsert
            
        Returns:
            Number of records processed
        """
        if not insights_list:
            return 0
        
        try:
            processed = 0
            
            async with self.db_manager.get_postgres_transaction() as conn:
                for insights in insights_list:
                    await self.upsert_insights(insights)
                    processed += 1
            
            self.logger.info("Bulk insights upsert completed",
                           total_records=len(insights_list),
                           processed=processed)
            
            return processed
            
        except Exception as e:
            self.logger.error("Error in bulk insights upsert",
                            record_count=len(insights_list), error=str(e))
            raise
    
    async def delete_old_insights(self, days_to_keep: int = 90) -> int:
        """
        Delete old calendar insights beyond specified days.
        
        Args:
            days_to_keep: Number of days of insights to keep
            
        Returns:
            Number of records deleted
        """
        try:
            cutoff_date = date.today() - timedelta(days=days_to_keep)
            
            async with self.db_manager.get_postgres_connection() as conn:
                result = await conn.execute(
                    "DELETE FROM calendar_insights WHERE insight_date < $1",
                    cutoff_date
                )
                
                deleted_count = int(result.split()[-1])  # Extract count from "DELETE N"
                
                self.logger.info("Old insights deleted",
                               cutoff_date=cutoff_date.isoformat(),
                               deleted_count=deleted_count)
                
                return deleted_count
                
        except Exception as e:
            self.logger.error("Error deleting old insights", 
                            days_to_keep=days_to_keep, error=str(e))
            raise
    
    # Cache-specific methods
    async def get_cached_insights(self, location: str, insight_date: date) -> Optional[CalendarInsights]:
        """Get cached insights for a location and date."""
        cache_key = f"insights:{location.lower()}:{insight_date.isoformat()}"
        cached_data = await self.cache_get(cache_key)
        
        if cached_data:
            return CalendarInsights(**cached_data)
        
        return None
    
    async def cache_insights(self, 
                           location: str, 
                           insight_date: date,
                           insights: CalendarInsights,
                           expiry: int = 3600) -> None:
        """Cache insights for a location and date."""
        cache_key = f"insights:{location.lower()}:{insight_date.isoformat()}"
        await self.cache_set(cache_key, insights.dict(), expiry)
    
    async def clear_insights_cache(self, location: Optional[str] = None) -> int:
        """Clear cached insights data."""
        if location:
            pattern = f"insights:{location.lower()}:*"
        else:
            pattern = "insights:*"
        
        return await self.cache_clear_pattern(pattern)