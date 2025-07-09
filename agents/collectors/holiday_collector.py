"""
Holiday Collector - Collects holiday and cultural event data
"""

import httpx
import structlog
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = structlog.get_logger(__name__)


class HolidayCollector:
    """Collects holiday and cultural event data"""
    
    def __init__(self):
        """Initialize HolidayCollector"""
        self.logger = logger.bind(component="holiday_collector")
        
        # Holiday data sources
        # In production, this would integrate with APIs like:
        # - Google Calendar API (for public holidays)
        # - Calendarific API
        # - Holiday API
        # - Local government APIs
        
        self._initialize_holiday_data()
    
    def _initialize_holiday_data(self):
        """Initialize static holiday data"""
        # Major holidays (simplified for MVP)
        # In production, this would be dynamic and location-specific
        self.fixed_holidays = {
            "01-01": ["New Year's Day"],
            "02-14": ["Valentine's Day"],
            "03-17": ["St. Patrick's Day"],
            "04-01": ["April Fool's Day"],
            "05-01": ["International Workers' Day"],
            "07-04": ["Independence Day (US)"],
            "10-31": ["Halloween"],
            "11-11": ["Veterans Day", "Singles Day"],
            "12-24": ["Christmas Eve"],
            "12-25": ["Christmas Day"],
            "12-31": ["New Year's Eve"]
        }
        
        # Movable holidays (simplified - would need proper calculation)
        self.movable_holidays = {
            "easter": "Easter Sunday",
            "thanksgiving": "Thanksgiving",
            "black_friday": "Black Friday",
            "cyber_monday": "Cyber Monday"
        }
        
        # Cultural events by location
        self.cultural_events = {
            "san francisco": {
                "02-**": ["Chinese New Year Festival"],
                "06-**": ["Pride Month"],
                "09-**": ["Folsom Street Fair"],
                "10-**": ["Fleet Week"]
            },
            "new york": {
                "01-**": ["Restaurant Week"],
                "06-**": ["Pride Month"],
                "09-**": ["Fashion Week"],
                "11-**": ["Marathon"]
            },
            "london": {
                "06-**": ["Trooping the Colour"],
                "08-**": ["Notting Hill Carnival"],
                "11-05": ["Guy Fawkes Night"],
                "12-**": ["Winter Wonderland"]
            },
            "tokyo": {
                "03-**": ["Cherry Blossom Season"],
                "05-05": ["Children's Day"],
                "07-**": ["Summer Festivals"],
                "11-15": ["Shichi-Go-San"]
            },
            "paris": {
                "07-14": ["Bastille Day"],
                "06-21": ["Fête de la Musique"],
                "10-**": ["Nuit Blanche"],
                "12-**": ["Christmas Markets"]
            }
        }
        
        # Shopping events
        self.shopping_events = {
            "11-**": ["Black Friday", "Cyber Monday"],
            "12-26": ["Boxing Day"],
            "01-**": ["New Year Sales"],
            "07-**": ["Summer Sales"],
            "09-**": ["Back to School"]
        }
    
    async def collect_holidays(
        self, 
        location: str, 
        date: datetime
    ) -> List[str]:
        """
        Collect holidays for a specific location and date
        
        Args:
            location: City/location name
            date: Date to check for holidays
            
        Returns:
            List of holiday names
        """
        self.logger.info(
            "Collecting holidays",
            location=location,
            date=date.isoformat()
        )
        
        holidays = []
        
        # Check fixed holidays
        month_day = f"{date.month:02d}-{date.day:02d}"
        if month_day in self.fixed_holidays:
            holidays.extend(self.fixed_holidays[month_day])
        
        # Check location-specific cultural events
        location_lower = location.lower()
        
        # Try exact location match
        if location_lower in self.cultural_events:
            holidays.extend(self._check_cultural_events(
                self.cultural_events[location_lower], 
                date
            ))
        
        # Try partial matches (e.g., "San Francisco Bay Area" matches "san francisco")
        for loc_key, events in self.cultural_events.items():
            if loc_key in location_lower or location_lower in loc_key:
                holidays.extend(self._check_cultural_events(events, date))
                break
        
        # Check shopping events
        holidays.extend(self._check_shopping_events(date))
        
        # Check movable holidays
        holidays.extend(self._check_movable_holidays(date))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_holidays = []
        for holiday in holidays:
            if holiday not in seen:
                seen.add(holiday)
                unique_holidays.append(holiday)
        
        self.logger.info(
            "Holidays found",
            location=location,
            date=date.isoformat(),
            holidays=unique_holidays
        )
        
        return unique_holidays
    
    async def get_cultural_significance(
        self,
        location: str,
        date: datetime,
        holidays: List[str]
    ) -> str:
        """
        Determine cultural significance level based on holidays and location
        
        Args:
            location: City/location
            date: Date to analyze
            holidays: List of holidays on that date
            
        Returns:
            Cultural significance level: "high", "medium", or "low"
        """
        # High significance criteria
        high_significance_holidays = [
            "Christmas", "New Year", "Thanksgiving", "Independence Day",
            "Chinese New Year", "Diwali", "Eid", "Easter",
            "Pride", "Carnival", "Festival"
        ]
        
        # Check if any high significance holidays
        for holiday in holidays:
            for high_holiday in high_significance_holidays:
                if high_holiday.lower() in holiday.lower():
                    return "high"
        
        # Medium significance if any holidays present
        if holidays:
            return "medium"
        
        # Check if it's a weekend
        if date.weekday() >= 5:  # Saturday or Sunday
            return "medium"
        
        # Check if it's near a major holiday (within 3 days)
        for delta in range(-3, 4):
            check_date = date + timedelta(days=delta)
            month_day = f"{check_date.month:02d}-{check_date.day:02d}"
            if month_day in self.fixed_holidays:
                for holiday in self.fixed_holidays[month_day]:
                    for high_holiday in high_significance_holidays:
                        if high_holiday.lower() in holiday.lower():
                            return "medium"
        
        return "low"
    
    async def get_days_to_next_holiday(
        self,
        location: str,
        date: datetime
    ) -> int:
        """
        Calculate days until the next holiday
        
        Args:
            location: City/location
            date: Current date
            
        Returns:
            Number of days to next holiday
        """
        # Check up to 30 days ahead
        for days_ahead in range(1, 31):
            check_date = date + timedelta(days=days_ahead)
            holidays = await self.collect_holidays(location, check_date)
            if holidays:
                return days_ahead
        
        # Default to 30 if no holidays found in next month
        return 30
    
    def _check_cultural_events(
        self, 
        events: Dict[str, List[str]], 
        date: datetime
    ) -> List[str]:
        """Check cultural events for a specific date"""
        holidays = []
        
        # Check exact date matches
        month_day = f"{date.month:02d}-{date.day:02d}"
        if month_day in events:
            holidays.extend(events[month_day])
        
        # Check month-wide events (marked with **)
        month_pattern = f"{date.month:02d}-**"
        if month_pattern in events:
            holidays.extend(events[month_pattern])
        
        return holidays
    
    def _check_shopping_events(self, date: datetime) -> List[str]:
        """Check for shopping events"""
        holidays = []
        
        # Black Friday (4th Thursday of November + 1)
        if date.month == 11:
            # Find 4th Thursday
            thursday_count = 0
            for day in range(1, 31):
                check_date = datetime(date.year, 11, day)
                if check_date.weekday() == 3:  # Thursday
                    thursday_count += 1
                    if thursday_count == 4:
                        # Black Friday is the day after
                        black_friday = check_date + timedelta(days=1)
                        if date.date() == black_friday.date():
                            holidays.append("Black Friday")
                        # Cyber Monday is 3 days after Black Friday
                        cyber_monday = black_friday + timedelta(days=3)
                        if date.date() == cyber_monday.date():
                            holidays.append("Cyber Monday")
                        break
        
        # Boxing Day
        month_day = f"{date.month:02d}-{date.day:02d}"
        for pattern, events in self.shopping_events.items():
            if pattern.endswith("**") and pattern.startswith(f"{date.month:02d}-"):
                # Skip Black Friday/Cyber Monday as we handle them specially
                filtered_events = [e for e in events if e not in ["Black Friday", "Cyber Monday"]]
                holidays.extend(filtered_events)
            elif pattern == month_day:
                holidays.extend(events)
        
        return holidays
    
    def _check_movable_holidays(self, date: datetime) -> List[str]:
        """Check for movable holidays (simplified)"""
        holidays = []
        
        # Easter (simplified - would need proper calculation)
        # Usually falls between March 22 and April 25
        if date.month in [3, 4] and date.day in range(20, 26):
            if date.weekday() == 6:  # Sunday
                # This is a very rough approximation
                holidays.append("Easter Sunday (approximate)")
        
        # Thanksgiving (4th Thursday of November in US)
        if date.month == 11:
            thursday_count = 0
            for day in range(1, 31):
                check_date = datetime(date.year, 11, day)
                if check_date.weekday() == 3:  # Thursday
                    thursday_count += 1
                    if thursday_count == 4 and date.date() == check_date.date():
                        holidays.append("Thanksgiving")
                        break
        
        # Add other movable holidays as needed
        
        return holidays