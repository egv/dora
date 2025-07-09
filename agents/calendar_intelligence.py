"""
Local Calendar Intelligence Agent - Google A2A Implementation

This agent provides intelligent calendar analysis with marketing insights.
It orchestrates multiple sub-agents for data collection, verification, and calendar building.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import structlog
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication
from a2a.server.context import ServerCallContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers.request_handler import RequestHandler
from a2a.types import (
    AgentCard,
    AgentSkill,
    AgentCapabilities,
    Task,
    TaskQueryParams,
    TaskIdParams,
    Message,
    MessageSendParams,
    TaskPushNotificationConfig,
    GetTaskPushNotificationConfigParams,
    UnsupportedOperationError,
    Part,
    TextPart,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)

# Import enhanced collectors if available
try:
    from .collectors import EnhancedMultiSourceCollector
    USE_ENHANCED_COLLECTOR = True
except ImportError:
    USE_ENHANCED_COLLECTOR = False


logger = structlog.get_logger(__name__)


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
            "opportunity_score": self.opportunity_score
        }


class MultiSourceCollector:
    """Sub-agent for collecting data from multiple sources"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__).bind(component="multi_source_collector")
    
    async def collect_events(self, location: str, date: datetime) -> List[Dict[str, Any]]:
        """Collect events for a specific location and date"""
        self.logger.info("Collecting events", location=location, date=date.isoformat())
        
        # For MVP, return mock events data
        # In production, this would integrate with EventSearchAgent and other sources
        mock_events = [
            {
                "name": f"Local Market Day - {location}",
                "description": "Weekly farmers market",
                "location": f"Town Square, {location}",
                "start_time": (date + timedelta(hours=9)).isoformat(),
                "end_time": (date + timedelta(hours=14)).isoformat(),
                "category": "market",
                "attendance_estimate": 200
            },
            {
                "name": f"Evening Concert - {location}",
                "description": "Live music performance",
                "location": f"Community Center, {location}",
                "start_time": (date + timedelta(hours=19)).isoformat(),
                "end_time": (date + timedelta(hours=22)).isoformat(),
                "category": "entertainment",
                "attendance_estimate": 150
            }
        ]
        
        return mock_events
    
    async def collect_weather(self, location: str, date: datetime) -> Dict[str, Any]:
        """Collect weather data for location and date"""
        self.logger.info("Collecting weather", location=location, date=date.isoformat())
        
        # Mock weather data for MVP
        # In production, integrate with weather APIs
        import random
        conditions = ['clear', 'sunny', 'partly_cloudy', 'cloudy', 'rainy']
        
        return {
            "condition": random.choice(conditions),
            "temperature": random.randint(15, 30),
            "humidity": random.randint(40, 80),
            "wind_speed": random.randint(5, 20)
        }
    
    async def collect_holidays(self, location: str, date: datetime) -> List[str]:
        """Collect holiday information for location and date"""
        self.logger.info("Collecting holidays", location=location, date=date.isoformat())
        
        # Mock holiday data for MVP
        # In production, integrate with holiday APIs
        month_day = f"{date.month}-{date.day}"
        holidays_map = {
            "1-1": ["New Year's Day"],
            "7-4": ["Independence Day"],
            "12-25": ["Christmas Day"],
            "10-31": ["Halloween"]
        }
        
        return holidays_map.get(month_day, [])


class DataVerifier:
    """Enhanced sub-agent for verifying and validating collected data"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__).bind(component="data_verifier")
        
        # Known valid weather conditions for validation
        self.valid_weather_conditions = {
            'clear', 'sunny', 'partly_cloudy', 'cloudy', 'overcast',
            'light_rain', 'rain', 'heavy_rain', 'drizzle', 'showers',
            'snow', 'light_snow', 'heavy_snow', 'sleet', 'hail',
            'thunderstorm', 'fog', 'mist', 'windy', 'dust'
        }
        
        # Event category patterns for validation
        self.event_category_patterns = {
            'music': ['concert', 'music', 'band', 'orchestra', 'symphony', 'festival', 'jazz'],
            'market': ['market', 'fair', 'bazaar', 'farmers', 'flea', 'craft'],
            'sports': ['sport', 'game', 'match', 'marathon', 'race', 'tournament', 'championship'],
            'art': ['art', 'gallery', 'exhibition', 'museum', 'painting', 'sculpture'],
            'food': ['food', 'restaurant', 'culinary', 'wine', 'tasting', 'cooking'],
            'technology': ['tech', 'conference', 'summit', 'meetup', 'hackathon', 'workshop'],
            'festival': ['festival', 'celebration', 'carnival', 'parade', 'fiesta'],
            'community': ['community', 'meeting', 'gathering', 'social', 'networking']
        }
    
    async def verify_events(self, events: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], float]:
        """Verify events with enhanced validation and cross-checking"""
        self.logger.info("Verifying events", event_count=len(events))
        
        if not events:
            self.logger.warning("No events to verify")
            return [], 0.0
        
        verified_events = []
        total_confidence = 0.0
        
        # Detect duplicate events
        deduplicated_events = self._deduplicate_events(events)
        
        for event in deduplicated_events:
            confidence = await self._verify_single_event(event)
            
            # Add confidence score to event
            event['verification_confidence'] = min(1.0, max(0.0, confidence))
            verified_events.append(event)
            total_confidence += confidence
        
        avg_confidence = total_confidence / len(verified_events) if verified_events else 0.0
        
        self.logger.info("Events verified", 
                        original_count=len(events),
                        verified_count=len(verified_events),
                        duplicates_removed=len(events) - len(deduplicated_events),
                        average_confidence=avg_confidence)
        
        return verified_events, avg_confidence
    
    async def _verify_single_event(self, event: Dict[str, Any]) -> float:
        """Verify a single event with comprehensive validation"""
        confidence = 0.2  # Base confidence (reduced from 0.5)
        
        # 1. Required fields validation (25% of score - increased weight)
        required_fields = ['name', 'location', 'start_time']
        field_score = sum(1 for field in required_fields if field in event and event[field])
        field_confidence = (field_score / len(required_fields)) * 0.25
        confidence += field_confidence
        
        # If missing critical fields, heavily penalize
        if field_score < len(required_fields):
            confidence *= 0.7  # Reduce confidence by 30%
        
        # 2. Date and time validation (30% of score - increased weight)
        datetime_confidence = await self._validate_event_datetime(event) * 0.30
        confidence += datetime_confidence
        
        # If datetime is completely invalid, heavily penalize
        if datetime_confidence == 0:
            confidence *= 0.5  # Reduce confidence by 50%
        
        # 3. Location validation (15% of score)
        confidence += self._validate_event_location(event) * 0.15
        
        # 4. Event name and description validation (15% of score - reduced)
        confidence += self._validate_event_content(event) * 0.15
        
        # 5. Category validation (10% of score)
        confidence += self._validate_event_category(event) * 0.10
        
        # 6. Source reliability (5% of score - reduced)
        confidence += self._validate_event_source(event) * 0.05
        
        return min(1.0, max(0.0, confidence))
    
    async def _validate_event_datetime(self, event: Dict[str, Any]) -> float:
        """Validate event date and time"""
        try:
            start_time = datetime.fromisoformat(event.get('start_time', '').replace('Z', '+00:00'))
            now = datetime.now()
            
            # Check if event is in the future (but not too far)
            if start_time <= now:
                return 0.3  # Past events get low score
            
            # Check if event is within reasonable future (1 year)
            if start_time > now + timedelta(days=365):
                return 0.4  # Too far in future
            
            # Check end time if available
            if 'end_time' in event:
                end_time = datetime.fromisoformat(event['end_time'].replace('Z', '+00:00'))
                if end_time <= start_time:
                    return 0.5  # End before start
                
                # Check reasonable duration (not more than 72 hours)
                duration = end_time - start_time
                if duration > timedelta(hours=72):
                    return 0.6  # Too long duration
            
            return 1.0  # Valid datetime
            
        except (ValueError, TypeError):
            return 0.0  # Invalid datetime format
    
    def _validate_event_location(self, event: Dict[str, Any]) -> float:
        """Validate event location"""
        location = event.get('location', '').strip()
        
        if not location:
            return 0.0
        
        # Check for reasonable location length
        if len(location) < 3:
            return 0.3
        
        # Check for common location patterns
        location_indicators = ['street', 'avenue', 'road', 'center', 'hall', 'park', 'square', 'building']
        has_location_pattern = any(indicator in location.lower() for indicator in location_indicators)
        
        if has_location_pattern:
            return 1.0
        
        # Check if location contains city/address-like patterns
        if ',' in location or any(char.isdigit() for char in location):
            return 0.8
        
        return 0.6  # Generic location
    
    def _validate_event_content(self, event: Dict[str, Any]) -> float:
        """Validate event name and description"""
        name = event.get('name', '').strip()
        description = event.get('description', '').strip()
        
        if not name:
            return 0.0
        
        confidence = 0.5
        
        # Check name length and quality
        if len(name) < 3:
            confidence -= 0.3
        elif len(name) > 100:
            confidence -= 0.1
        
        # Check for meaningful description
        if description and len(description) > 10:
            confidence += 0.3
        
        # Check for spam-like content (case-insensitive)
        spam_indicators = ['buy now', 'click here', 'free money', 'urgent']
        spam_score = 0
        name_lower = name.lower()
        desc_lower = description.lower()
        
        for indicator in spam_indicators:
            if indicator in name_lower or indicator in desc_lower:
                spam_score += 0.2
        
        # Check for excessive exclamation marks
        if name.count('!') > 2 or description.count('!') > 2:
            spam_score += 0.1
        
        # Apply spam penalty
        confidence -= spam_score
        
        return max(0.0, min(1.0, confidence))
    
    def _validate_event_category(self, event: Dict[str, Any]) -> float:
        """Validate event category based on name/description"""
        name = event.get('name', '').lower()
        description = event.get('description', '').lower()
        category = event.get('category', '')
        
        # If no category, try to infer from content
        if not category:
            inferred_category = self._infer_event_category(name, description)
            if inferred_category:
                event['category'] = inferred_category
                return 0.7  # Inferred category
            return 0.3  # No category
        
        # Validate existing category
        if category in self.event_category_patterns:
            # Check if category matches content
            patterns = self.event_category_patterns[category]
            if any(pattern in name or pattern in description for pattern in patterns):
                return 1.0  # Category matches content
            return 0.5  # Category doesn't match content
        
        return 0.4  # Unknown category
    
    def _infer_event_category(self, name: str, description: str) -> str:
        """Infer event category from name and description"""
        content = f"{name} {description}"
        
        for category, patterns in self.event_category_patterns.items():
            if any(pattern in content for pattern in patterns):
                return category
        
        return 'general'
    
    def _validate_event_source(self, event: Dict[str, Any]) -> float:
        """Validate event source reliability"""
        source = event.get('source', '').lower()
        
        # Source reliability scores
        source_scores = {
            'eventsearchagent': 0.8,  # Our A2A agent
            'official': 0.9,
            'government': 0.9,
            'ticketing': 0.7,
            'social': 0.5,
            'user': 0.4,
            'unknown': 0.3
        }
        
        for source_type, score in source_scores.items():
            if source_type in source:
                return score
        
        return 0.5  # Default score
    
    def _deduplicate_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate events based on name, location, and time"""
        if not events:
            return events
        
        unique_events = []
        seen_signatures = set()
        
        for event in events:
            # Create signature for duplicate detection
            name = event.get('name', '').strip().lower()
            location = event.get('location', '').strip().lower()
            start_time = event.get('start_time', '').strip()
            
            signature = f"{name}|{location}|{start_time}"
            
            if signature not in seen_signatures:
                seen_signatures.add(signature)
                unique_events.append(event)
            else:
                self.logger.debug("Duplicate event removed", 
                                event_name=event.get('name'),
                                signature=signature)
        
        return unique_events
    
    async def verify_weather(self, weather: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
        """Verify weather data with enhanced validation"""
        self.logger.info("Verifying weather data")
        
        if not weather:
            self.logger.warning("No weather data to verify")
            return {}, 0.0
        
        confidence = 0.3  # Base confidence (reduced further)
        
        # 1. Required fields validation (25% of score)
        required_fields = ['condition', 'temperature']
        field_score = sum(1 for field in required_fields if field in weather and weather[field] is not None)
        confidence += (field_score / len(required_fields)) * 0.25
        
        # 2. Weather condition validation (25% of score)
        condition = weather.get('condition', '').lower()
        if condition in self.valid_weather_conditions:
            confidence += 0.25
        elif condition:
            confidence += 0.1  # Some condition provided
        
        # 3. Temperature validation (25% of score)
        temp = weather.get('temperature')
        if temp is not None:
            try:
                temp_val = float(temp)
                if -20 <= temp_val <= 40:  # Normal temperature range
                    confidence += 0.25
                elif -50 <= temp_val <= 60:  # Reasonable temperature range
                    confidence += 0.15
                elif -80 <= temp_val <= 80:  # Extreme but possible
                    confidence += 0.05
                else:  # Impossible temperature
                    confidence -= 0.2
            except (ValueError, TypeError):
                confidence -= 0.2
        
        # 4. Additional fields validation (25% of score)
        additional_fields = ['humidity', 'wind_speed', 'pressure']
        additional_score = 0
        fields_with_values = 0
        
        for field in additional_fields:
            if field in weather and weather[field] is not None:
                fields_with_values += 1
                try:
                    val = float(weather[field])
                    if field == 'humidity' and 0 <= val <= 100:
                        additional_score += 1
                    elif field == 'wind_speed' and 0 <= val <= 200:
                        additional_score += 1
                    elif field == 'pressure' and 800 <= val <= 1100:
                        additional_score += 1
                    else:
                        # Invalid value for this field - heavy penalty
                        additional_score -= 2  # Increased penalty
                except (ValueError, TypeError):
                    additional_score -= 2  # Increased penalty
        
        if fields_with_values > 0:
            confidence += (additional_score / fields_with_values) * 0.25
        
        # Ensure confidence is within valid range
        confidence = min(1.0, max(0.0, confidence))
        
        # Add confidence score to weather data
        weather['verification_confidence'] = confidence
        
        self.logger.info("Weather verified", confidence=confidence)
        
        return weather, confidence
    
    async def verify_holidays(self, holidays: List[str], location: str, date: datetime) -> Tuple[List[str], float]:
        """Verify holiday data"""
        self.logger.info("Verifying holidays", holiday_count=len(holidays))
        
        if not holidays:
            return [], 1.0  # No holidays is valid
        
        verified_holidays = []
        total_confidence = 0.0
        
        for holiday in holidays:
            confidence = self._verify_single_holiday(holiday, location, date)
            if confidence > 0.3:  # Only include holidays with reasonable confidence
                verified_holidays.append(holiday)
                total_confidence += confidence
        
        avg_confidence = total_confidence / len(verified_holidays) if verified_holidays else 0.0
        
        self.logger.info("Holidays verified", 
                        original_count=len(holidays),
                        verified_count=len(verified_holidays),
                        average_confidence=avg_confidence)
        
        return verified_holidays, avg_confidence
    
    def _verify_single_holiday(self, holiday: str, location: str, date: datetime) -> float:
        """Verify a single holiday"""
        if not holiday or not holiday.strip():
            return 0.0
        
        holiday = holiday.strip()
        confidence = 0.7  # Base confidence
        
        # Check for reasonable holiday name length
        if len(holiday) < 3:
            confidence -= 0.3
        elif len(holiday) > 50:
            confidence -= 0.1
        
        # Check for common holiday patterns
        holiday_patterns = [
            'day', 'eve', 'new year', 'christmas', 'easter', 'independence',
            'memorial', 'thanksgiving', 'halloween', 'valentine', 'mother',
            'father', 'labor', 'memorial', 'president', 'martin luther king'
        ]
        
        has_holiday_pattern = any(pattern in holiday.lower() for pattern in holiday_patterns)
        if has_holiday_pattern:
            confidence += 0.2
        
        # Check date appropriateness for known holidays
        month_day = f"{date.month}-{date.day}"
        known_holidays = {
            "1-1": ["new year"],
            "7-4": ["independence day", "fourth of july"],
            "12-25": ["christmas"],
            "10-31": ["halloween"],
            "2-14": ["valentine"]
        }
        
        if month_day in known_holidays:
            expected_holidays = known_holidays[month_day]
            if any(expected in holiday.lower() for expected in expected_holidays):
                confidence += 0.1
        
        return min(1.0, max(0.0, confidence))
    
    async def cross_verify_data(self, events: List[Dict[str, Any]], weather: Dict[str, Any], 
                               holidays: List[str], location: str, date: datetime) -> Dict[str, float]:
        """Cross-verify data across different sources for consistency"""
        self.logger.info("Cross-verifying data consistency")
        
        consistency_scores = {
            'event_weather_consistency': 0.0,
            'event_holiday_consistency': 0.0,
            'location_consistency': 0.0,
            'date_consistency': 0.0
        }
        
        # 1. Event-Weather consistency
        if events and weather:
            consistency_scores['event_weather_consistency'] = self._check_event_weather_consistency(events, weather)
        
        # 2. Event-Holiday consistency
        if events and holidays:
            consistency_scores['event_holiday_consistency'] = self._check_event_holiday_consistency(events, holidays)
        
        # 3. Location consistency
        if events:
            consistency_scores['location_consistency'] = self._check_location_consistency(events, location)
        
        # 4. Date consistency
        if events:
            consistency_scores['date_consistency'] = self._check_date_consistency(events, date)
        
        overall_consistency = sum(consistency_scores.values()) / len(consistency_scores)
        
        self.logger.info("Cross-verification completed", 
                        consistency_scores=consistency_scores,
                        overall_consistency=overall_consistency)
        
        return consistency_scores
    
    def _check_event_weather_consistency(self, events: List[Dict[str, Any]], weather: Dict[str, Any]) -> float:
        """Check if events are consistent with weather conditions"""
        weather_condition = weather.get('condition', '').lower()
        
        if not weather_condition:
            return 0.5  # No weather data to check against
        
        # Count outdoor vs indoor events
        outdoor_events = 0
        total_events = len(events)
        
        for event in events:
            name = event.get('name', '').lower()
            location = event.get('location', '').lower()
            
            outdoor_indicators = ['park', 'outdoor', 'festival', 'market', 'parade', 'garden', 'beach']
            if any(indicator in name or indicator in location for indicator in outdoor_indicators):
                outdoor_events += 1
        
        # Check consistency
        if weather_condition in ['rain', 'heavy_rain', 'thunderstorm', 'snow', 'heavy_snow']:
            # Bad weather should have fewer outdoor events
            if outdoor_events / total_events < 0.3:
                return 0.8  # Consistent - fewer outdoor events
            else:
                return 0.3  # Inconsistent - many outdoor events in bad weather
        
        return 0.7  # Neutral consistency
    
    def _check_event_holiday_consistency(self, events: List[Dict[str, Any]], holidays: List[str]) -> float:
        """Check if events are consistent with holidays"""
        if not holidays:
            return 0.7  # No holidays to check against
        
        holiday_related_events = 0
        total_events = len(events)
        
        # Create expanded holiday keywords
        holiday_keywords = set()
        for holiday in holidays:
            holiday_keywords.add(holiday.lower())
            # Add common holiday-related terms
            if 'christmas' in holiday.lower():
                holiday_keywords.update(['christmas', 'holiday', 'xmas'])
            elif 'independence' in holiday.lower():
                holiday_keywords.update(['independence', 'july', 'fourth'])
            elif 'thanksgiving' in holiday.lower():
                holiday_keywords.update(['thanksgiving', 'turkey'])
            elif 'halloween' in holiday.lower():
                holiday_keywords.update(['halloween', 'costume', 'trick'])
        
        for event in events:
            name = event.get('name', '').lower()
            description = event.get('description', '').lower()
            content = f"{name} {description}"
            
            # Check if event mentions any holiday-related keyword
            if any(keyword in content for keyword in holiday_keywords):
                holiday_related_events += 1
        
        # Calculate consistency based on proportion
        if total_events == 0:
            return 0.7
        
        holiday_proportion = holiday_related_events / total_events
        
        # Expect some holiday-related events if it's a holiday
        if holiday_proportion >= 0.5:
            return 0.9  # Good consistency - many holiday events
        elif holiday_proportion >= 0.2:
            return 0.8  # Decent consistency - some holiday events
        elif holiday_proportion > 0:
            return 0.7  # Some consistency - few holiday events
        elif total_events > 5:
            return 0.5  # Many events but none holiday-related
        else:
            return 0.7  # Few events, acceptable
    
    def _check_location_consistency(self, events: List[Dict[str, Any]], expected_location: str) -> float:
        """Check if event locations are consistent with expected location"""
        if not events:
            return 1.0
        
        consistent_events = 0
        total_events = len(events)
        expected_location_lower = expected_location.lower()
        
        for event in events:
            event_location = event.get('location', '').lower()
            
            # Check if event location mentions expected location
            if expected_location_lower in event_location:
                consistent_events += 1
        
        consistency_ratio = consistent_events / total_events
        return consistency_ratio
    
    def _check_date_consistency(self, events: List[Dict[str, Any]], expected_date: datetime) -> float:
        """Check if event dates are consistent with expected date"""
        if not events:
            return 1.0
        
        consistent_events = 0
        total_events = len(events)
        expected_date_str = expected_date.date().isoformat()
        
        for event in events:
            try:
                event_date = datetime.fromisoformat(event.get('start_time', '')).date()
                
                # Check if event is within reasonable range of expected date
                date_diff = abs((event_date - expected_date.date()).days)
                if date_diff <= 7:  # Within a week
                    consistent_events += 1
                    
            except (ValueError, TypeError):
                pass  # Skip invalid dates
        
        consistency_ratio = consistent_events / total_events
        return consistency_ratio


class CalendarBuilder:
    """Sub-agent for building intelligent calendar data"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__).bind(component="calendar_builder")
    
    async def build_calendar_data(
        self, 
        location: str, 
        date: datetime,
        events: List[Dict[str, Any]],
        weather: Dict[str, Any],
        holidays: List[str]
    ) -> CalendarData:
        """Build comprehensive calendar data for a day"""
        self.logger.info("Building calendar data", 
                        location=location, 
                        date=date.isoformat(),
                        event_count=len(events))
        
        # Create calendar data
        calendar_data = CalendarData(date, location)
        calendar_data.events = events
        calendar_data.weather = weather
        calendar_data.holidays = holidays
        
        # Determine cultural significance
        if holidays:
            calendar_data.cultural_significance = "high"
        elif len(events) >= 3:
            calendar_data.cultural_significance = "medium"
        else:
            calendar_data.cultural_significance = "low"
        
        # Check if it's payday (simplified - 1st and 15th)
        calendar_data.is_payday = date.day in [1, 15]
        
        # Calculate days to next holiday (simplified)
        # In production, this would check actual holiday calendar
        calendar_data.days_to_holiday = 30  # Default
        
        # Set historical engagement (mock data)
        # In production, this would come from historical analytics
        calendar_data.historical_engagement = 0.6 + (len(events) * 0.1)
        
        # Calculate opportunity score
        calendar_data.calculate_opportunity_score()
        
        self.logger.info("Calendar data built",
                        opportunity_score=calendar_data.opportunity_score,
                        cultural_significance=calendar_data.cultural_significance)
        
        return calendar_data


class CalendarIntelligenceExecutor(AgentExecutor):
    """Agent executor implementing calendar intelligence logic"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__).bind(component="calendar_intelligence_executor")
        
        # Initialize sub-agents
        if USE_ENHANCED_COLLECTOR:
            # Use enhanced collector with real data sources
            import os
            weather_api_key = os.getenv("WEATHER_API_KEY")
            self.collector = EnhancedMultiSourceCollector(
                event_search_agent_url="http://localhost:8001",
                weather_api_key=weather_api_key
            )
            self.logger.info("Using EnhancedMultiSourceCollector with real data sources")
        else:
            # Fall back to mock collector
            self.collector = MultiSourceCollector()
            self.logger.info("Using mock MultiSourceCollector")
            
        self.verifier = DataVerifier()
        self.builder = CalendarBuilder()
    
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute calendar intelligence operations"""
        try:
            message = context.message
            skill_id = message.get("skill_id")
            params = message.get("params", {})
            
            if skill_id == "get_calendar_data":
                result = await self._get_calendar_data(params)
            elif skill_id == "get_marketing_insights":
                result = await self._get_marketing_insights(params)
            elif skill_id == "analyze_opportunity":
                result = await self._analyze_opportunity(params)
            else:
                raise ValueError(f"Unknown skill: {skill_id}")
            
            # Publish task completion event
            await event_queue.publish(TaskStatusUpdateEvent(
                task_id=context.task_id,
                state=TaskState.completed,
                result=result
            ))
            
        except Exception as e:
            self.logger.error("Calendar intelligence execution failed", 
                            error=str(e), task_id=context.task_id)
            # Publish task failure event
            await event_queue.publish(TaskStatusUpdateEvent(
                task_id=context.task_id,
                state=TaskState.failed,
                error=str(e)
            ))
    
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel calendar intelligence operation"""
        self.logger.info("Cancelling calendar intelligence task", task_id=context.task_id)
        await event_queue.publish(TaskStatusUpdateEvent(
            task_id=context.task_id,
            state=TaskState.canceled
        ))
    
    async def _get_calendar_data(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get comprehensive calendar data for a location and date"""
        location = params.get("location")
        date_str = params.get("date")
        
        if not location:
            raise ValueError("Location parameter is required")
        
        # Parse date or use today
        if date_str:
            date = datetime.fromisoformat(date_str)
        else:
            date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        self.logger.info("Getting calendar data", location=location, date=date.isoformat())
        
        # Collect data from multiple sources
        if USE_ENHANCED_COLLECTOR:
            # Use enhanced collector's comprehensive data collection
            collected_data = await self.collector.collect_all_data(location, date)
            events = collected_data.get("events", [])
            weather = collected_data.get("weather", {})
            holidays = collected_data.get("holidays", [])
        else:
            # Use mock collector's individual methods
            events = await self.collector.collect_events(location, date)
            weather = await self.collector.collect_weather(location, date)
            holidays = await self.collector.collect_holidays(location, date)
        
        # Verify collected data with enhanced verification
        verified_events, event_confidence = await self.verifier.verify_events(events)
        verified_weather, weather_confidence = await self.verifier.verify_weather(weather)
        verified_holidays, holiday_confidence = await self.verifier.verify_holidays(holidays, location, date)
        
        # Cross-verify data for consistency
        consistency_scores = await self.verifier.cross_verify_data(
            verified_events, verified_weather, verified_holidays, location, date
        )
        
        # Build calendar data with verified data
        calendar_data = await self.builder.build_calendar_data(
            location, date, verified_events, verified_weather, verified_holidays
        )
        
        return {
            "calendar_data": calendar_data.to_dict(),
            "verification_scores": {
                "events_confidence": event_confidence,
                "weather_confidence": weather_confidence,
                "holidays_confidence": holiday_confidence,
                "consistency_scores": consistency_scores,
                "overall_confidence": (event_confidence + weather_confidence + holiday_confidence) / 3
            },
            "data_sources": {
                "events_count": len(verified_events),
                "weather_available": bool(verified_weather),
                "holidays_count": len(verified_holidays),
                "original_events_count": len(events),
                "original_holidays_count": len(holidays)
            }
        }
    
    async def _get_marketing_insights(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get marketing insights for a location and date range"""
        location = params.get("location")
        start_date_str = params.get("start_date")
        end_date_str = params.get("end_date")
        
        if not location:
            raise ValueError("Location parameter is required")
        
        # Parse dates
        start_date = datetime.fromisoformat(start_date_str) if start_date_str else datetime.now()
        end_date = datetime.fromisoformat(end_date_str) if end_date_str else start_date + timedelta(days=7)
        
        self.logger.info("Getting marketing insights", 
                        location=location, 
                        start_date=start_date.isoformat(),
                        end_date=end_date.isoformat())
        
        insights = []
        current_date = start_date
        
        while current_date <= end_date:
            # Get calendar data for each day
            calendar_result = await self._get_calendar_data({
                "location": location,
                "date": current_date.isoformat()
            })
            
            day_data = calendar_result["calendar_data"]
            insights.append({
                "date": current_date.isoformat(),
                "opportunity_score": day_data["opportunity_score"],
                "events_count": len(day_data["events"]),
                "weather_condition": day_data["weather"].get("condition", "unknown"),
                "holidays": day_data["holidays"],
                "cultural_significance": day_data["cultural_significance"]
            })
            
            current_date += timedelta(days=1)
        
        # Find best opportunities
        best_days = sorted(insights, key=lambda x: x["opportunity_score"], reverse=True)[:3]
        avg_score = sum(day["opportunity_score"] for day in insights) / len(insights)
        
        return {
            "location": location,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "insights": insights,
            "summary": {
                "average_opportunity_score": avg_score,
                "best_opportunities": best_days,
                "total_events": sum(day["events_count"] for day in insights),
                "holiday_days": sum(1 for day in insights if day["holidays"])
            }
        }
    
    async def _analyze_opportunity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze marketing opportunity for specific criteria"""
        location = params.get("location")
        date_str = params.get("date")
        criteria = params.get("criteria", {})
        
        if not location:
            raise ValueError("Location parameter is required")
        
        # Get calendar data
        calendar_result = await self._get_calendar_data({
            "location": location,
            "date": date_str
        })
        
        calendar_data = calendar_result["calendar_data"]
        
        # Analyze based on criteria
        analysis = {
            "location": location,
            "date": calendar_data["date"],
            "base_opportunity_score": calendar_data["opportunity_score"],
            "factors": {
                "events": {
                    "count": len(calendar_data["events"]),
                    "categories": list(set(event.get("category", "unknown") 
                                         for event in calendar_data["events"]))
                },
                "weather": {
                    "condition": calendar_data["weather"].get("condition"),
                    "favorability": "high" if calendar_data["weather"].get("condition") in ["clear", "sunny"] else "medium"
                },
                "cultural": {
                    "significance": calendar_data["cultural_significance"],
                    "holidays": calendar_data["holidays"]
                }
            },
            "recommendations": []
        }
        
        # Generate recommendations based on criteria
        if criteria.get("target_audience") == "families":
            if any("market" in event.get("category", "") for event in calendar_data["events"]):
                analysis["recommendations"].append("Family-friendly market events present - good for family-oriented campaigns")
        
        if criteria.get("campaign_type") == "outdoor":
            if calendar_data["weather"].get("condition") in ["clear", "sunny"]:
                analysis["recommendations"].append("Excellent weather conditions for outdoor campaigns")
        
        return analysis


class CalendarIntelligenceRequestHandler(RequestHandler):
    """Request handler for calendar intelligence operations"""
    
    def __init__(self, executor: CalendarIntelligenceExecutor):
        self.executor = executor
        self.tasks: Dict[str, Task] = {}
        self.logger = structlog.get_logger(__name__).bind(component="calendar_intelligence_handler")
    
    async def on_message_send(
        self, 
        params: MessageSendParams, 
        context: ServerCallContext | None = None
    ) -> Message:
        """Handle incoming messages for calendar intelligence"""
        # Create a new task for the message
        task_id = str(uuid4())
        
        # Extract parameters from message
        message_data = {}
        if params.message.parts:
            for part in params.message.parts:
                if hasattr(part.root, 'text'):
                    try:
                        message_data = json.loads(part.root.text)
                    except:
                        # If not JSON, try to extract location
                        text = part.root.text.strip()
                        message_data = {"location": text}
        
        # Determine skill based on message content
        skill_id = "get_calendar_data"  # Default skill
        if "insights" in message_data.get("request_type", ""):
            skill_id = "get_marketing_insights"
        elif "analyze" in message_data.get("request_type", ""):
            skill_id = "analyze_opportunity"
        
        # Create task
        task = Task(
            id=task_id,
            contextId=str(uuid4()),
            status=TaskStatus(
                state=TaskState.working,
                timestamp=datetime.utcnow().isoformat()
            )
        )
        
        self.tasks[task_id] = task
        
        # Execute via executor
        try:
            if skill_id == "get_calendar_data":
                result = await self.executor._get_calendar_data(message_data)
            elif skill_id == "get_marketing_insights":
                result = await self.executor._get_marketing_insights(message_data)
            elif skill_id == "analyze_opportunity":
                result = await self.executor._analyze_opportunity(message_data)
            else:
                raise ValueError(f"Unknown skill: {skill_id}")
            
            # Update task as completed
            task.status = TaskStatus(
                state=TaskState.completed,
                timestamp=datetime.utcnow().isoformat()
            )
            
            self.logger.info("Calendar intelligence request completed", 
                           task_id=task_id, 
                           skill_id=skill_id,
                           location=message_data.get("location"))
            
            # Return response message
            return Message(
                messageId=str(uuid4()),
                role="agent",
                parts=[
                    Part(
                        root=TextPart(
                            text=json.dumps(result, indent=2)
                        )
                    )
                ],
                taskId=task_id
            )
            
        except Exception as e:
            # Update task as failed
            task.status = TaskStatus(
                state=TaskState.failed,
                timestamp=datetime.utcnow().isoformat()
            )
            
            self.logger.error("Calendar intelligence request failed", 
                            task_id=task_id, 
                            skill_id=skill_id, 
                            error=str(e))
            
            return Message(
                messageId=str(uuid4()),
                role="agent", 
                parts=[
                    Part(
                        root=TextPart(
                            text=f"Failed to process calendar intelligence request: {str(e)}"
                        )
                    )
                ],
                taskId=task_id
            )
    
    async def on_message_send_stream(
        self,
        params: MessageSendParams,
        context: ServerCallContext | None = None
    ) -> Any:
        """Handle streaming message requests"""
        raise UnsupportedOperationError("Streaming not supported for calendar intelligence")
    
    async def on_get_task(
        self, 
        params: TaskQueryParams, 
        context: ServerCallContext | None = None
    ) -> Task | None:
        """Get task status"""
        return self.tasks.get(params.id)
    
    async def on_cancel_task(
        self, 
        params: TaskIdParams, 
        context: ServerCallContext | None = None
    ) -> Task | None:
        """Cancel a task"""
        task = self.tasks.get(params.id)
        if task:
            task.status = TaskStatus(
                state=TaskState.canceled,
                timestamp=datetime.utcnow().isoformat()
            )
            self.logger.info("Task cancelled", task_id=params.id)
        return task
    
    async def on_get_task_push_notification_config(
        self,
        params: GetTaskPushNotificationConfigParams,
        context: ServerCallContext | None = None,
    ) -> TaskPushNotificationConfig | None:
        """Get push notification config (not implemented)"""
        return None
    
    async def on_set_task_push_notification_config(
        self,
        params: Any,
        context: ServerCallContext | None = None,
    ) -> TaskPushNotificationConfig | None:
        """Set push notification config (not implemented)"""
        return None
    
    async def on_resubscribe_to_task(
        self,
        params: Any,
        context: ServerCallContext | None = None,
    ) -> None:
        """Resubscribe to task updates (not implemented)"""
        pass


class CalendarIntelligenceAgent:
    """
    Local Calendar Intelligence Agent using Google A2A SDK
    
    This agent provides intelligent calendar analysis and marketing insights.
    It orchestrates data collection, verification, and calendar building.
    """
    
    def __init__(self, name: str = "Calendar Intelligence", version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.logger = structlog.get_logger(__name__).bind(agent_name=name)
        
        # Create calendar intelligence skills
        self.skills = [
            AgentSkill(
                id="get_calendar_data",
                name="Get Calendar Data",
                description="Get comprehensive calendar data for a location and date",
                tags=["calendar", "data", "intelligence"],
                examples=[
                    '{"location": "San Francisco", "date": "2025-07-10"}',
                    '{"location": "New York"}',
                    "Get calendar data for Paris"
                ]
            ),
            AgentSkill(
                id="get_marketing_insights",
                name="Get Marketing Insights",
                description="Get marketing insights and opportunity analysis for a date range",
                tags=["marketing", "insights", "analytics"],
                examples=[
                    '{"location": "London", "start_date": "2025-07-01", "end_date": "2025-07-07"}',
                    '{"location": "Tokyo", "request_type": "insights"}'
                ]
            ),
            AgentSkill(
                id="analyze_opportunity",
                name="Analyze Opportunity",
                description="Analyze marketing opportunity for specific criteria and location",
                tags=["analysis", "opportunity", "marketing"],
                examples=[
                    '{"location": "Berlin", "date": "2025-07-15", "criteria": {"target_audience": "families"}}',
                    '{"location": "Sydney", "request_type": "analyze", "criteria": {"campaign_type": "outdoor"}}'
                ]
            )
        ]
        
        # Create agent card
        self.agent_card = AgentCard(
            name=self.name,
            description="Agent that provides intelligent calendar analysis and marketing insights",
            version=self.version,
            url="http://localhost:8002",  # Different port from other agents
            defaultInputModes=["text/plain", "application/json"],
            defaultOutputModes=["application/json"],
            capabilities=AgentCapabilities(),
            skills=self.skills
        )
        
        # Create executor and handler
        self.executor = CalendarIntelligenceExecutor()
        self.request_handler = CalendarIntelligenceRequestHandler(self.executor)
        
        # Create A2A FastAPI application
        self.a2a_app = A2AFastAPIApplication(
            agent_card=self.agent_card,
            http_handler=self.request_handler
        )
        
        self.logger.info("Calendar Intelligence Agent initialized", 
                        skills_count=len(self.skills))
    
    def build_fastapi_app(self):
        """Build and return FastAPI application"""
        return self.a2a_app.build(
            title="Calendar Intelligence Agent",
            description="A2A Agent for intelligent calendar analysis and marketing insights",
            version=self.version
        )
    
    async def start_server(self, host: str = "localhost", port: int = 8002):
        """Start the agent server"""
        import uvicorn
        
        app = self.build_fastapi_app()
        self.logger.info("Starting Calendar Intelligence Agent server", 
                        host=host, port=port)
        
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()


# Factory function for easy instantiation
def create_calendar_intelligence_agent(
    name: str = "Calendar Intelligence"
) -> CalendarIntelligenceAgent:
    """Create and return a configured Calendar Intelligence Agent"""
    return CalendarIntelligenceAgent(name=name)


if __name__ == "__main__":
    import uvicorn
    
    agent = CalendarIntelligenceAgent()
    app = agent.build_fastapi_app()
    
    # Add health check endpoint
    @app.get("/health")
    async def health():
        return {"status": "healthy", "agent": "CalendarIntelligenceAgent", "version": "1.0.0"}
    
    print("🚀 Starting CalendarIntelligenceAgent...")
    print("📍 Agent will be available at: http://localhost:8002")
    print("🔍 Example request: POST / with A2A message for calendar intelligence")
    print("❤️  Health check: GET /health")
    
    uvicorn.run(app, host="0.0.0.0", port=8002)