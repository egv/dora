"""
Weather Collector - Integrates with OpenWeatherMap API
"""

import os
import httpx
import structlog
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import quote

logger = structlog.get_logger(__name__)


class WeatherCollector:
    """Collects weather data from OpenWeatherMap API"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize WeatherCollector
        
        Args:
            api_key: OpenWeatherMap API key (or uses WEATHER_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("WEATHER_API_KEY", "")
        self.base_url = "https://api.openweathermap.org/data/2.5"
        self.logger = logger.bind(component="weather_collector")
        
        if not self.api_key:
            self.logger.warning("No weather API key configured, will use mock data")
    
    async def collect_weather(
        self, 
        location: str, 
        date: datetime
    ) -> Dict[str, Any]:
        """
        Collect weather data for a location
        
        Args:
            location: City/location name
            date: Date for weather (uses forecast if future)
            
        Returns:
            Weather data dictionary
        """
        self.logger.info(
            "Collecting weather data",
            location=location,
            date=date.isoformat()
        )
        
        if not self.api_key:
            self.logger.error("No weather API key configured - cannot collect weather data")
            return {}
        
        try:
            # Determine if we need current weather or forecast
            now = datetime.now()
            days_ahead = (date - now).days
            
            if days_ahead <= 0:
                # Get current weather
                weather_data = await self._get_current_weather(location)
            elif days_ahead <= 5:
                # Get forecast (OpenWeatherMap provides 5-day forecast)
                weather_data = await self._get_forecast_weather(location, date)
            else:
                # Too far in future, use seasonal estimates
                weather_data = self._get_seasonal_weather(location, date)
            
            return weather_data
            
        except Exception as e:
            self.logger.error(
                "Error collecting weather data - no fallback available",
                error=str(e),
                location=location
            )
            return {}
    
    async def _get_current_weather(self, location: str) -> Dict[str, Any]:
        """Get current weather for location"""
        url = f"{self.base_url}/weather"
        params = {
            "q": location,
            "appid": self.api_key,
            "units": "metric"  # Use Celsius
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            
            if response.status_code == 200:
                data = response.json()
                return self._transform_weather_data(data)
            else:
                self.logger.error(
                    "Weather API request failed",
                    status_code=response.status_code,
                    location=location
                )
                raise Exception(f"Weather API error: {response.status_code}")
    
    async def _get_forecast_weather(
        self, 
        location: str, 
        target_date: datetime
    ) -> Dict[str, Any]:
        """Get weather forecast for specific date"""
        url = f"{self.base_url}/forecast"
        params = {
            "q": location,
            "appid": self.api_key,
            "units": "metric"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            
            if response.status_code == 200:
                data = response.json()
                
                # Find forecast closest to target date
                target_timestamp = target_date.timestamp()
                closest_forecast = None
                min_diff = float('inf')
                
                for forecast in data.get("list", []):
                    forecast_timestamp = forecast.get("dt", 0)
                    diff = abs(forecast_timestamp - target_timestamp)
                    
                    if diff < min_diff:
                        min_diff = diff
                        closest_forecast = forecast
                
                if closest_forecast:
                    return self._transform_forecast_data(closest_forecast)
                else:
                    raise Exception("No forecast data found")
            else:
                self.logger.error(
                    "Weather forecast API request failed",
                    status_code=response.status_code,
                    location=location
                )
                raise Exception(f"Weather API error: {response.status_code}")
    
    def _get_seasonal_weather(self, location: str, date: datetime) -> Dict[str, Any]:
        """Get seasonal weather estimate for dates beyond forecast range"""
        month = date.month
        
        # Simple seasonal patterns (Northern Hemisphere bias)
        # In production, this would use historical climate data
        if month in [12, 1, 2]:  # Winter
            return {
                "condition": "cloudy",
                "temperature": 5,
                "humidity": 70,
                "wind_speed": 15,
                "precipitation_chance": 0.4,
                "source": "seasonal_estimate"
            }
        elif month in [3, 4, 5]:  # Spring
            return {
                "condition": "partly_cloudy",
                "temperature": 15,
                "humidity": 60,
                "wind_speed": 10,
                "precipitation_chance": 0.3,
                "source": "seasonal_estimate"
            }
        elif month in [6, 7, 8]:  # Summer
            return {
                "condition": "sunny",
                "temperature": 25,
                "humidity": 50,
                "wind_speed": 8,
                "precipitation_chance": 0.2,
                "source": "seasonal_estimate"
            }
        else:  # Fall
            return {
                "condition": "partly_cloudy",
                "temperature": 12,
                "humidity": 65,
                "wind_speed": 12,
                "precipitation_chance": 0.35,
                "source": "seasonal_estimate"
            }
    
    def _transform_weather_data(self, api_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform OpenWeatherMap current weather data to our format"""
        weather = api_data.get("weather", [{}])[0]
        main = api_data.get("main", {})
        wind = api_data.get("wind", {})
        
        # Map OpenWeatherMap conditions to our simplified conditions
        condition_map = {
            "clear sky": "clear",
            "few clouds": "partly_cloudy",
            "scattered clouds": "partly_cloudy",
            "broken clouds": "cloudy",
            "overcast clouds": "cloudy",
            "shower rain": "rainy",
            "rain": "rainy",
            "thunderstorm": "stormy",
            "snow": "snowy",
            "mist": "foggy"
        }
        
        weather_desc = weather.get("description", "").lower()
        condition = "unknown"
        
        for key, value in condition_map.items():
            if key in weather_desc:
                condition = value
                break
        
        # If still unknown, try main weather type
        if condition == "unknown":
            main_weather = weather.get("main", "").lower()
            if "clear" in main_weather:
                condition = "clear"
            elif "cloud" in main_weather:
                condition = "cloudy"
            elif "rain" in main_weather:
                condition = "rainy"
            else:
                condition = "partly_cloudy"  # Default
        
        return {
            "condition": condition,
            "temperature": round(main.get("temp", 20)),
            "humidity": main.get("humidity", 50),
            "wind_speed": round(wind.get("speed", 0) * 3.6),  # Convert m/s to km/h
            "precipitation_chance": 0.0,  # Not available in current weather
            "description": weather.get("description", ""),
            "source": "openweathermap_current"
        }
    
    def _transform_forecast_data(self, forecast_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform OpenWeatherMap forecast data to our format"""
        weather = forecast_data.get("weather", [{}])[0]
        main = forecast_data.get("main", {})
        wind = forecast_data.get("wind", {})
        
        # Similar transformation as current weather
        condition_map = {
            "clear sky": "clear",
            "few clouds": "partly_cloudy",
            "scattered clouds": "partly_cloudy",
            "broken clouds": "cloudy",
            "overcast clouds": "cloudy",
            "shower rain": "rainy",
            "rain": "rainy",
            "thunderstorm": "stormy",
            "snow": "snowy",
            "mist": "foggy"
        }
        
        weather_desc = weather.get("description", "").lower()
        condition = "partly_cloudy"  # Default
        
        for key, value in condition_map.items():
            if key in weather_desc:
                condition = value
                break
        
        # Calculate precipitation chance from pop (probability of precipitation)
        precipitation_chance = forecast_data.get("pop", 0.0)
        
        return {
            "condition": condition,
            "temperature": round(main.get("temp", 20)),
            "humidity": main.get("humidity", 50),
            "wind_speed": round(wind.get("speed", 0) * 3.6),  # Convert m/s to km/h
            "precipitation_chance": precipitation_chance,
            "description": weather.get("description", ""),
            "source": "openweathermap_forecast"
        }
    
