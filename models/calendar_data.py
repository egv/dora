"""
Calendar Data Model
"""

from datetime import datetime
from typing import Any, Dict, List


class CalendarData:
    """Calendar data structure for a specific day and location"""
    
    def __init__(self, date: datetime, location: str):
        self.date = date
        self.location = location
        self.events: List[Dict[str, Any]] = []
        self.weather: Dict[str, Any] = {}
        self.holidays: List[str] = []
        self.cultural_significance = "low"  # low, medium, high
        self.is_payday = False
        self.days_to_holiday = 999
        self.historical_engagement = 0.5  # 0.0 to 1.0
        self.opportunity_score = 50  # 0 to 100
        self.metadata: Dict[str, Any] = {}
        
    def calculate_opportunity_score(self) -> int:
        """Calculate marketing opportunity score for this day"""
        base_score = 50  # Start with neutral score
        
        # Event density factor (0-20 points)
        event_count = len(self.events)
        event_score = min(20, event_count * 2)
        
        # Weather favorability (0-15 points)
        weather_condition = self.weather.get('condition', 'unknown')
        weather_score = 15 if weather_condition in ['clear', 'sunny'] else \
                       10 if weather_condition in ['partly_cloudy'] else \
                       5 if weather_condition in ['cloudy'] else \
                       0
        
        # Holiday/payday proximity (0-25 points)
        holiday_score = 25 if self.holidays else \
                       15 if self.days_to_holiday <= 3 else \
                       10 if self.is_payday else \
                       0
        
        # Cultural considerations (0-15 points)
        cultural_score = 15 if self.cultural_significance == 'high' else \
                        10 if self.cultural_significance == 'medium' else \
                        0
        
        # Historical engagement (0-25 points)
        historical_score = min(25, int(self.historical_engagement * 25))
        
        self.opportunity_score = base_score + event_score + weather_score + holiday_score + cultural_score + historical_score
        return self.opportunity_score
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "date": self.date.isoformat(),
            "location": self.location,
            "events": self.events,
            "weather": self.weather,
            "holidays": self.holidays,
            "cultural_significance": self.cultural_significance,
            "is_payday": self.is_payday,
            "days_to_holiday": self.days_to_holiday,
            "historical_engagement": self.historical_engagement,
            "opportunity_score": self.opportunity_score,
            "metadata": self.metadata
        }