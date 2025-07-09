"""
Enhanced Multi-Source Collector - Orchestrates all data collectors
"""

import asyncio
import structlog
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .event_collector import EventCollector
from .weather_collector import WeatherCollector
from .holiday_collector import HolidayCollector

logger = structlog.get_logger(__name__)


class EnhancedMultiSourceCollector:
    """
    Enhanced collector that aggregates data from multiple real sources
    """
    
    def __init__(
        self,
        event_search_agent_url: str = "http://localhost:8001",
        weather_api_key: Optional[str] = None
    ):
        """
        Initialize Enhanced Multi-Source Collector
        
        Args:
            event_search_agent_url: URL of EventSearchAgent
            weather_api_key: OpenWeatherMap API key
        """
        self.logger = logger.bind(component="enhanced_multi_source_collector")
        
        # Initialize individual collectors
        self.event_collector = EventCollector(event_search_agent_url)
        self.weather_collector = WeatherCollector(weather_api_key)
        self.holiday_collector = HolidayCollector()
        
        # Configuration
        self.default_events_count = 10
        self.default_days_ahead = 14
    
    async def collect_all_data(
        self,
        location: str,
        date: datetime,
        events_count: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Collect all data from multiple sources concurrently
        
        Args:
            location: City/location to collect data for
            date: Date to collect data for
            events_count: Number of events to collect
            
        Returns:
            Dictionary containing all collected data
        """
        self.logger.info(
            "Starting multi-source data collection",
            location=location,
            date=date.isoformat(),
            events_count=events_count or self.default_events_count
        )
        
        # Run all collectors concurrently
        tasks = [
            self.collect_events(location, date, events_count),
            self.collect_weather(location, date),
            self.collect_holidays(location, date)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle results
        events_result = results[0]
        weather_result = results[1]
        holidays_result = results[2]
        
        # Process any exceptions
        if isinstance(events_result, Exception):
            self.logger.error("Event collection failed - no fallback available", error=str(events_result))
            events_result = []
        
        if isinstance(weather_result, Exception):
            self.logger.error("Weather collection failed - no fallback available", error=str(weather_result))
            weather_result = {}
        
        if isinstance(holidays_result, Exception):
            self.logger.error("Holiday collection failed - no fallback available", error=str(holidays_result))
            holidays_result = []
        
        # Calculate additional metrics
        cultural_significance = await self.holiday_collector.get_cultural_significance(
            location, date, holidays_result
        )
        
        days_to_holiday = await self.holiday_collector.get_days_to_next_holiday(
            location, date
        )
        
        # Compile all data
        collected_data = {
            "location": location,
            "date": date.isoformat(),
            "events": events_result,
            "weather": weather_result,
            "holidays": holidays_result,
            "cultural_significance": cultural_significance,
            "days_to_holiday": days_to_holiday,
            "data_sources": {
                "events": {
                    "count": len(events_result),
                    "source": events_result[0].get("source", "unknown") if events_result else "none"
                },
                "weather": {
                    "source": weather_result.get("source", "unknown")
                },
                "holidays": {
                    "count": len(holidays_result)
                }
            },
            "collection_timestamp": datetime.utcnow().isoformat()
        }
        
        self.logger.info(
            "Multi-source data collection completed",
            location=location,
            events_count=len(events_result),
            holidays_count=len(holidays_result),
            weather_condition=weather_result.get("condition", "unknown")
        )
        
        return collected_data
    
    async def collect_events(
        self, 
        location: str, 
        date: datetime,
        events_count: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Collect events using EventCollector
        
        Args:
            location: City/location to search events
            date: Date to search around
            events_count: Number of events to retrieve
            
        Returns:
            List of event dictionaries
        """
        try:
            return await self.event_collector.collect_events(
                location=location,
                date=date,
                events_count=events_count or self.default_events_count,
                days_ahead=self.default_days_ahead
            )
        except Exception as e:
            self.logger.error(
                "Event collection failed - no fallback available",
                error=str(e),
                location=location
            )
            return []
    
    async def collect_weather(
        self, 
        location: str, 
        date: datetime
    ) -> Dict[str, Any]:
        """
        Collect weather using WeatherCollector
        
        Args:
            location: City/location
            date: Date for weather
            
        Returns:
            Weather data dictionary
        """
        try:
            return await self.weather_collector.collect_weather(location, date)
        except Exception as e:
            self.logger.error(
                "Weather collection failed - no fallback available",
                error=str(e),
                location=location
            )
            return {}
    
    async def collect_holidays(
        self, 
        location: str, 
        date: datetime
    ) -> List[str]:
        """
        Collect holidays using HolidayCollector
        
        Args:
            location: City/location
            date: Date to check
            
        Returns:
            List of holiday names
        """
        try:
            return await self.holiday_collector.collect_holidays(location, date)
        except Exception as e:
            self.logger.error(
                "Holiday collection failed",
                error=str(e),
                location=location
            )
            return []
    
    async def collect_range(
        self,
        location: str,
        start_date: datetime,
        end_date: datetime,
        events_per_day: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Collect data for a date range
        
        Args:
            location: City/location
            start_date: Start date
            end_date: End date
            events_per_day: Events to collect per day
            
        Returns:
            List of daily data collections
        """
        self.logger.info(
            "Collecting data for date range",
            location=location,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat()
        )
        
        # Generate list of dates
        current = start_date
        dates = []
        while current <= end_date:
            dates.append(current)
            current = current + timedelta(days=1)
        
        # Collect data for each date concurrently (with limit)
        # Limit concurrent requests to avoid overwhelming APIs
        semaphore = asyncio.Semaphore(3)
        
        async def collect_with_limit(date):
            async with semaphore:
                return await self.collect_all_data(
                    location, 
                    date, 
                    events_per_day
                )
        
        results = await asyncio.gather(
            *[collect_with_limit(date) for date in dates],
            return_exceptions=True
        )
        
        # Filter out any failed collections
        valid_results = []
        for result in results:
            if not isinstance(result, Exception):
                valid_results.append(result)
            else:
                self.logger.error(
                    "Date collection failed",
                    error=str(result)
                )
        
        return valid_results
    
    
    async def get_source_health(self) -> Dict[str, Any]:
        """
        Check health status of all data sources
        
        Returns:
            Dictionary with health status of each source
        """
        health_status = {
            "event_search_agent": "unknown",
            "weather_api": "unknown",
            "holiday_data": "healthy"  # Always healthy (static data)
        }
        
        # Check EventSearchAgent
        try:
            # Try to get a small number of events
            test_events = await self.event_collector.collect_events(
                "Test City", 
                datetime.now(), 
                events_count=1
            )
            if test_events:
                health_status["event_search_agent"] = "healthy"
            else:
                health_status["event_search_agent"] = "unhealthy"
        except:
            health_status["event_search_agent"] = "unhealthy"
        
        # Check Weather API
        try:
            test_weather = await self.weather_collector.collect_weather(
                "London",
                datetime.now()
            )
            if test_weather and "condition" in test_weather:
                health_status["weather_api"] = "healthy"
            else:
                health_status["weather_api"] = "unhealthy"
        except:
            health_status["weather_api"] = "unhealthy"
        
        return health_status