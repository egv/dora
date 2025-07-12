"""Weather repository for managing weather data."""

from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
import asyncpg
import structlog

from dora.database.repositories.base import BaseRepository
from dora.database.connections import DatabaseManager


logger = structlog.get_logger(__name__)


@dataclass
class WeatherData:
    """Weather data model."""
    location: str
    date: date
    temperature: Optional[float] = None
    weather_condition: Optional[str] = None
    humidity: Optional[float] = None
    wind_speed: Optional[float] = None
    precipitation: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'location': self.location,
            'date': self.date,
            'temperature': self.temperature,
            'weather_condition': self.weather_condition,
            'humidity': self.humidity,
            'wind_speed': self.wind_speed,
            'precipitation': self.precipitation,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class WeatherRepository(BaseRepository[WeatherData]):
    """Repository for managing weather data in PostgreSQL."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize weather repository."""
        super().__init__(db_manager, "weather_data")
        self.logger = logger.bind(component="weather_repository")
    
    def _row_to_model(self, row: asyncpg.Record) -> WeatherData:
        """Convert database row to WeatherData model."""
        return WeatherData(
            location=row['location'],
            date=row['date'],
            temperature=row['temperature'],
            weather_condition=row['weather_condition'],
            humidity=row['humidity'],
            wind_speed=row['wind_speed'],
            precipitation=row['precipitation'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )
    
    def _model_to_dict(self, model: WeatherData) -> Dict[str, Any]:
        """Convert WeatherData model to dictionary for database storage."""
        return {
            'location': model.location,
            'date': model.date,
            'temperature': model.temperature,
            'weather_condition': model.weather_condition,
            'humidity': model.humidity,
            'wind_speed': model.wind_speed,
            'precipitation': model.precipitation,
            'created_at': model.created_at or datetime.utcnow(),
            'updated_at': model.updated_at or datetime.utcnow()
        }
    
    async def find_by_location_and_date(self, location: str, date: date) -> Optional[WeatherData]:
        """
        Find weather data by location and date.
        
        Args:
            location: Location name
            date: Date for weather data
            
        Returns:
            WeatherData if found, None otherwise
        """
        try:
            async with self.db_manager.get_postgres_connection() as conn:
                query = "SELECT * FROM weather_data WHERE LOWER(location) = LOWER($1) AND date = $2"
                row = await conn.fetchrow(query, location, date)
                
                if row:
                    return self._row_to_model(row)
                return None
                
        except Exception as e:
            self.logger.error("Error finding weather by location and date",
                            location=location, date=date.isoformat(), error=str(e))
            raise
    
    async def find_by_location_date_range(self, 
                                        location: str,
                                        start_date: date,
                                        end_date: date) -> List[WeatherData]:
        """
        Find weather data for a location within a date range.
        
        Args:
            location: Location name
            start_date: Start date
            end_date: End date
            
        Returns:
            List of weather data within the date range
        """
        try:
            async with self.db_manager.get_postgres_connection() as conn:
                query = """
                    SELECT * FROM weather_data 
                    WHERE LOWER(location) = LOWER($1)
                    AND date >= $2 
                    AND date <= $3
                    ORDER BY date ASC
                """
                
                rows = await conn.fetch(query, location, start_date, end_date)
                
                weather_data = [self._row_to_model(row) for row in rows]
                
                self.logger.info("Found weather data by location and date range",
                               location=location,
                               start_date=start_date.isoformat(),
                               end_date=end_date.isoformat(),
                               count=len(weather_data))
                
                return weather_data
                
        except Exception as e:
            self.logger.error("Error finding weather by location and date range",
                            location=location, error=str(e))
            raise
    
    async def find_recent_weather(self, 
                                location: str,
                                days_back: int = 7) -> List[WeatherData]:
        """
        Find recent weather data for a location.
        
        Args:
            location: Location name
            days_back: Number of days back to search
            
        Returns:
            List of recent weather data
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days_back)
        
        return await self.find_by_location_date_range(location, start_date, end_date)
    
    async def find_by_condition(self, 
                              weather_condition: str,
                              start_date: Optional[date] = None,
                              end_date: Optional[date] = None,
                              limit: int = 1000) -> List[WeatherData]:
        """
        Find weather data by weather condition.
        
        Args:
            weather_condition: Weather condition to search for
            start_date: Optional start date filter
            end_date: Optional end date filter
            limit: Maximum number of records
            
        Returns:
            List of weather data matching the condition
        """
        try:
            where_conditions = ["LOWER(weather_condition) = LOWER($1)"]
            params = [weather_condition]
            param_count = 1
            
            if start_date:
                param_count += 1
                where_conditions.append(f"date >= ${param_count}")
                params.append(start_date)
            
            if end_date:
                param_count += 1
                where_conditions.append(f"date <= ${param_count}")
                params.append(end_date)
            
            where_clause = " AND ".join(where_conditions)
            
            return await self.find_by_criteria(
                where_clause,
                params,
                order_by="date DESC",
                limit=limit
            )
            
        except Exception as e:
            self.logger.error("Error finding weather by condition",
                            condition=weather_condition, error=str(e))
            raise
    
    async def find_by_temperature_range(self, 
                                      min_temp: float,
                                      max_temp: float,
                                      location: Optional[str] = None,
                                      limit: int = 1000) -> List[WeatherData]:
        """
        Find weather data within a temperature range.
        
        Args:
            min_temp: Minimum temperature
            max_temp: Maximum temperature
            location: Optional location filter
            limit: Maximum number of records
            
        Returns:
            List of weather data within temperature range
        """
        try:
            where_conditions = ["temperature >= $1 AND temperature <= $2"]
            params = [min_temp, max_temp]
            param_count = 2
            
            if location:
                param_count += 1
                where_conditions.append(f"LOWER(location) = LOWER(${param_count})")
                params.append(location)
            
            where_clause = " AND ".join(where_conditions)
            
            return await self.find_by_criteria(
                where_clause,
                params,
                order_by="date DESC",
                limit=limit
            )
            
        except Exception as e:
            self.logger.error("Error finding weather by temperature range",
                            min_temp=min_temp, max_temp=max_temp, error=str(e))
            raise
    
    async def get_weather_stats(self, 
                              location: Optional[str] = None,
                              start_date: Optional[date] = None,
                              end_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Get weather statistics.
        
        Args:
            location: Optional location filter
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Dictionary with weather statistics
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
                    where_conditions.append(f"date >= ${param_count}")
                    params.append(start_date)
                
                if end_date:
                    param_count += 1
                    where_conditions.append(f"date <= ${param_count}")
                    params.append(end_date)
                
                where_clause = ""
                if where_conditions:
                    where_clause = "WHERE " + " AND ".join(where_conditions)
                
                # Temperature statistics
                temp_query = f"""
                    SELECT 
                        COUNT(*) as total_records,
                        AVG(temperature) as avg_temperature,
                        MIN(temperature) as min_temperature,
                        MAX(temperature) as max_temperature,
                        STDDEV(temperature) as temp_stddev
                    FROM weather_data {where_clause}
                    WHERE temperature IS NOT NULL
                """
                
                temp_stats = await conn.fetchrow(temp_query, *params)
                
                # Weather conditions distribution
                condition_query = f"""
                    SELECT weather_condition, COUNT(*) as count
                    FROM weather_data {where_clause}
                    WHERE weather_condition IS NOT NULL
                    GROUP BY weather_condition
                    ORDER BY count DESC
                """
                
                condition_rows = await conn.fetch(condition_query, *params)
                conditions = {row['weather_condition']: row['count'] for row in condition_rows}
                
                # Humidity statistics
                humidity_query = f"""
                    SELECT 
                        AVG(humidity) as avg_humidity,
                        MIN(humidity) as min_humidity,
                        MAX(humidity) as max_humidity
                    FROM weather_data {where_clause}
                    WHERE humidity IS NOT NULL
                """
                
                humidity_stats = await conn.fetchrow(humidity_query, *params)
                
                stats = {
                    "total_records": temp_stats['total_records'] or 0,
                    "temperature": {
                        "average": float(temp_stats['avg_temperature']) if temp_stats['avg_temperature'] else None,
                        "minimum": float(temp_stats['min_temperature']) if temp_stats['min_temperature'] else None,
                        "maximum": float(temp_stats['max_temperature']) if temp_stats['max_temperature'] else None,
                        "standard_deviation": float(temp_stats['temp_stddev']) if temp_stats['temp_stddev'] else None
                    },
                    "humidity": {
                        "average": float(humidity_stats['avg_humidity']) if humidity_stats['avg_humidity'] else None,
                        "minimum": float(humidity_stats['min_humidity']) if humidity_stats['min_humidity'] else None,
                        "maximum": float(humidity_stats['max_humidity']) if humidity_stats['max_humidity'] else None
                    },
                    "conditions": conditions,
                    "filters": {
                        "location": location,
                        "start_date": start_date.isoformat() if start_date else None,
                        "end_date": end_date.isoformat() if end_date else None
                    }
                }
                
                self.logger.info("Generated weather statistics",
                               location=location,
                               total_records=stats["total_records"])
                
                return stats
                
        except Exception as e:
            self.logger.error("Error getting weather statistics", 
                            location=location, error=str(e))
            raise
    
    async def upsert_weather(self, weather: WeatherData) -> WeatherData:
        """
        Insert or update weather data (upsert by location and date).
        
        Args:
            weather: Weather data to upsert
            
        Returns:
            Upserted weather data
        """
        try:
            data = self._model_to_dict(weather)
            
            async with self.db_manager.get_postgres_connection() as conn:
                query = """
                    INSERT INTO weather_data (
                        location, date, temperature, weather_condition, 
                        humidity, wind_speed, precipitation, created_at, updated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (location, date)
                    DO UPDATE SET
                        temperature = EXCLUDED.temperature,
                        weather_condition = EXCLUDED.weather_condition,
                        humidity = EXCLUDED.humidity,
                        wind_speed = EXCLUDED.wind_speed,
                        precipitation = EXCLUDED.precipitation,
                        updated_at = EXCLUDED.updated_at
                    RETURNING *
                """
                
                row = await conn.fetchrow(
                    query,
                    data['location'], data['date'], data['temperature'],
                    data['weather_condition'], data['humidity'], data['wind_speed'],
                    data['precipitation'], data['created_at'], data['updated_at']
                )
                
                result = self._row_to_model(row)
                
                self.logger.info("Weather data upserted",
                               location=weather.location,
                               date=weather.date.isoformat())
                
                return result
                
        except Exception as e:
            self.logger.error("Error upserting weather data",
                            location=weather.location, 
                            date=weather.date.isoformat(), 
                            error=str(e))
            raise
    
    async def bulk_upsert_weather(self, weather_data: List[WeatherData]) -> int:
        """
        Bulk upsert weather data.
        
        Args:
            weather_data: List of weather data to upsert
            
        Returns:
            Number of records processed
        """
        if not weather_data:
            return 0
        
        try:
            processed = 0
            
            async with self.db_manager.get_postgres_transaction() as conn:
                for weather in weather_data:
                    await self.upsert_weather(weather)
                    processed += 1
            
            self.logger.info("Bulk weather upsert completed",
                           total_records=len(weather_data),
                           processed=processed)
            
            return processed
            
        except Exception as e:
            self.logger.error("Error in bulk weather upsert",
                            record_count=len(weather_data), error=str(e))
            raise
    
    async def delete_old_weather(self, days_to_keep: int = 90) -> int:
        """
        Delete old weather data beyond specified days.
        
        Args:
            days_to_keep: Number of days of data to keep
            
        Returns:
            Number of records deleted
        """
        try:
            cutoff_date = date.today() - timedelta(days=days_to_keep)
            
            async with self.db_manager.get_postgres_connection() as conn:
                result = await conn.execute(
                    "DELETE FROM weather_data WHERE date < $1",
                    cutoff_date
                )
                
                deleted_count = int(result.split()[-1])  # Extract count from "DELETE N"
                
                self.logger.info("Old weather data deleted",
                               cutoff_date=cutoff_date.isoformat(),
                               deleted_count=deleted_count)
                
                return deleted_count
                
        except Exception as e:
            self.logger.error("Error deleting old weather data", 
                            days_to_keep=days_to_keep, error=str(e))
            raise
    
    # Cache-specific methods
    async def get_cached_weather(self, location: str, date: date) -> Optional[WeatherData]:
        """Get cached weather for a location and date."""
        cache_key = f"weather:{location.lower()}:{date.isoformat()}"
        cached_data = await self.cache_get(cache_key)
        
        if cached_data:
            return WeatherData(**cached_data)
        
        return None
    
    async def cache_weather(self, 
                          location: str, 
                          date: date,
                          weather: WeatherData,
                          expiry: int = 3600) -> None:
        """Cache weather data for a location and date."""
        cache_key = f"weather:{location.lower()}:{date.isoformat()}"
        await self.cache_set(cache_key, weather.dict(), expiry)
    
    async def clear_weather_cache(self, location: Optional[str] = None) -> int:
        """Clear cached weather data."""
        if location:
            pattern = f"weather:{location.lower()}:*"
        else:
            pattern = "weather:*"
        
        return await self.cache_clear_pattern(pattern)