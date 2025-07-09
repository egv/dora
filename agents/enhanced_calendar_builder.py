"""
Enhanced Calendar Builder Sub-Agent
Constructs and manages calendar events based on verified data
"""

import asyncio
import structlog
from datetime import datetime, timedelta, time
from typing import Any, Dict, List, Optional, Tuple, Set
from collections import defaultdict
import hashlib
import json

from models.calendar_data import CalendarData


logger = structlog.get_logger(__name__)


class EventConflict:
    """Represents a conflict between two or more events"""
    
    def __init__(self, events: List[Dict[str, Any]], conflict_type: str, severity: str):
        self.events = events
        self.conflict_type = conflict_type  # 'time_overlap', 'location_conflict', 'resource_conflict'
        self.severity = severity  # 'high', 'medium', 'low'
        self.resolution_strategy = None
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            'conflicting_events': [e.get('name', 'Unknown') for e in self.events],
            'conflict_type': self.conflict_type,
            'severity': self.severity,
            'resolution_strategy': self.resolution_strategy
        }


class CalendarLayer:
    """Represents a layer of the calendar (events, weather, holidays, etc.)"""
    
    def __init__(self, layer_type: str, priority: int = 0):
        self.layer_type = layer_type
        self.priority = priority  # Higher priority layers override lower ones
        self.data = {}
        self.metadata = {}
        
    def add_item(self, key: str, value: Any, metadata: Optional[Dict] = None):
        """Add an item to this layer"""
        self.data[key] = value
        if metadata:
            self.metadata[key] = metadata
            
    def get_items_for_time_range(self, start: datetime, end: datetime) -> List[Any]:
        """Get all items within a time range"""
        items = []
        for key, value in self.data.items():
            if isinstance(value, dict) and 'start_time' in value:
                try:
                    item_start = datetime.fromisoformat(value['start_time'].replace('Z', '+00:00'))
                    if start <= item_start <= end:
                        items.append(value)
                except:
                    pass
        return items


class EnhancedCalendarBuilder:
    """Enhanced sub-agent for building intelligent calendar data"""
    
    def __init__(self):
        self.logger = logger.bind(component="enhanced_calendar_builder")
        
        # Calendar layers with priorities
        self.layers = {
            'holidays': CalendarLayer('holidays', priority=100),
            'events': CalendarLayer('events', priority=50),
            'weather': CalendarLayer('weather', priority=30),
            'marketing': CalendarLayer('marketing', priority=20),
            'analytics': CalendarLayer('analytics', priority=10)
        }
        
        # Conflict resolution strategies
        self.conflict_strategies = {
            'time_overlap': self._resolve_time_overlap,
            'location_conflict': self._resolve_location_conflict,
            'resource_conflict': self._resolve_resource_conflict
        }
        
        # Event categories and their typical durations (hours)
        self.typical_durations = {
            'music': 2.5,
            'market': 5.0,
            'sports': 3.0,
            'art': 2.0,
            'food': 2.0,
            'technology': 8.0,
            'festival': 6.0,
            'community': 2.0,
            'general': 2.0
        }
    
    async def build_calendar_data(
        self, 
        location: str, 
        date: datetime,
        events: List[Dict[str, Any]],
        weather: Dict[str, Any],
        holidays: List[str],
        consistency_scores: Optional[Dict[str, float]] = None
    ) -> CalendarData:
        """Build comprehensive calendar data with conflict resolution and optimization"""
        self.logger.info("Building enhanced calendar data", 
                        location=location, 
                        date=date.isoformat(),
                        event_count=len(events))
        
        # Clear previous data
        self._clear_layers()
        
        # Process and add data to layers
        processed_events = await self._process_events(events, date)
        conflicts = await self._detect_conflicts(processed_events)
        resolved_events = await self._resolve_conflicts(processed_events, conflicts)
        
        # Add data to layers
        self._add_holidays_to_layer(holidays, date)
        self._add_events_to_layer(resolved_events)
        self._add_weather_to_layer(weather, date)
        
        # Create calendar data
        calendar_data = CalendarData(date, location)
        calendar_data.events = resolved_events
        calendar_data.weather = weather
        calendar_data.holidays = holidays
        
        # Enhanced metrics calculation
        calendar_data.cultural_significance = await self._calculate_cultural_significance(
            holidays, resolved_events, location, date
        )
        
        calendar_data.is_payday = self._is_payday(date, location)
        calendar_data.days_to_holiday = await self._calculate_days_to_holiday(location, date)
        calendar_data.historical_engagement = await self._calculate_historical_engagement(
            resolved_events, weather, holidays, date
        )
        
        # Calculate opportunity score with enhanced logic
        calendar_data.calculate_opportunity_score()
        
        # Add additional metadata
        calendar_metadata = {
            'conflicts_detected': len(conflicts),
            'conflicts_resolved': len([c for c in conflicts if c.resolution_strategy]),
            'event_density': self._calculate_event_density(resolved_events),
            'time_coverage': self._calculate_time_coverage(resolved_events),
            'consistency_scores': consistency_scores or {},
            'layer_summary': self._get_layer_summary()
        }
        
        # Store metadata in calendar data (extend CalendarData if needed)
        calendar_data.metadata = calendar_metadata
        
        self.logger.info("Enhanced calendar data built",
                        opportunity_score=calendar_data.opportunity_score,
                        cultural_significance=calendar_data.cultural_significance,
                        conflicts_resolved=calendar_metadata['conflicts_resolved'],
                        event_density=calendar_metadata['event_density'])
        
        return calendar_data
    
    async def _process_events(self, events: List[Dict[str, Any]], date: datetime) -> List[Dict[str, Any]]:
        """Process events to ensure consistency and add missing information"""
        processed_events = []
        
        for event in events:
            processed_event = event.copy()
            
            # Ensure end time exists
            if 'end_time' not in processed_event or not processed_event['end_time']:
                processed_event['end_time'] = self._estimate_end_time(processed_event)
            
            # Add unique ID if missing
            if 'id' not in processed_event:
                processed_event['id'] = self._generate_event_id(processed_event)
            
            # Normalize times to datetime objects for processing
            try:
                processed_event['_start_dt'] = datetime.fromisoformat(
                    processed_event['start_time'].replace('Z', '+00:00')
                )
                processed_event['_end_dt'] = datetime.fromisoformat(
                    processed_event['end_time'].replace('Z', '+00:00')
                )
            except:
                self.logger.warning("Invalid event times", event_name=processed_event.get('name'))
                continue
            
            # Add processing metadata
            processed_event['_processed'] = True
            processed_event['_processing_timestamp'] = datetime.utcnow().isoformat()
            
            processed_events.append(processed_event)
        
        # Sort by start time
        processed_events.sort(key=lambda e: e['_start_dt'])
        
        return processed_events
    
    async def _detect_conflicts(self, events: List[Dict[str, Any]]) -> List[EventConflict]:
        """Detect conflicts between events"""
        conflicts = []
        
        # Time overlap detection
        for i, event1 in enumerate(events):
            for event2 in events[i+1:]:
                if self._events_overlap(event1, event2):
                    conflict = EventConflict(
                        [event1, event2],
                        'time_overlap',
                        self._calculate_overlap_severity(event1, event2)
                    )
                    conflicts.append(conflict)
        
        # Location conflict detection
        location_groups = defaultdict(list)
        for event in events:
            location = event.get('location', '').lower().strip()
            if location:
                location_groups[location].append(event)
        
        for location, location_events in location_groups.items():
            if len(location_events) > 1:
                # Check if events at same location overlap
                for i, event1 in enumerate(location_events):
                    for event2 in location_events[i+1:]:
                        if self._events_overlap(event1, event2):
                            conflict = EventConflict(
                                [event1, event2],
                                'location_conflict',
                                'high'  # Same location conflicts are high severity
                            )
                            conflicts.append(conflict)
        
        return conflicts
    
    async def _resolve_conflicts(
        self, 
        events: List[Dict[str, Any]], 
        conflicts: List[EventConflict]
    ) -> List[Dict[str, Any]]:
        """Resolve detected conflicts"""
        if not conflicts:
            return events
        
        resolved_events = events.copy()
        
        for conflict in conflicts:
            strategy = self.conflict_strategies.get(conflict.conflict_type)
            if strategy:
                resolution = await strategy(conflict, resolved_events)
                conflict.resolution_strategy = resolution
        
        return resolved_events
    
    async def _resolve_time_overlap(
        self, 
        conflict: EventConflict, 
        events: List[Dict[str, Any]]
    ) -> str:
        """Resolve time overlap conflicts"""
        if conflict.severity == 'low':
            # Minor overlap - no action needed
            return 'accepted_minor_overlap'
        
        # For significant overlaps, prioritize by:
        # 1. Verification confidence
        # 2. Event category importance
        # 3. Attendance estimate
        
        event1, event2 = conflict.events
        
        score1 = self._calculate_event_priority_score(event1)
        score2 = self._calculate_event_priority_score(event2)
        
        if score1 > score2:
            # Keep event1, mark event2 as alternative
            event2['_conflict_status'] = 'alternative'
            event2['_conflict_with'] = event1['id']
            return 'prioritized_higher_score_event'
        else:
            # Keep event2, mark event1 as alternative
            event1['_conflict_status'] = 'alternative'
            event1['_conflict_with'] = event2['id']
            return 'prioritized_higher_score_event'
    
    async def _resolve_location_conflict(
        self, 
        conflict: EventConflict, 
        events: List[Dict[str, Any]]
    ) -> str:
        """Resolve location conflicts"""
        # For same location conflicts, adjust times if possible
        event1, event2 = conflict.events
        
        # Check if we can shift one event slightly
        overlap_duration = self._calculate_overlap_duration(event1, event2)
        
        if overlap_duration < 30:  # Less than 30 minutes overlap
            # Shift the later event
            if event1['_start_dt'] < event2['_start_dt']:
                # Shift event2 to start after event1 ends
                event2['_adjusted_start'] = event1['end_time']
                return 'shifted_later_event'
            else:
                # Shift event1 to start after event2 ends
                event1['_adjusted_start'] = event2['end_time']
                return 'shifted_later_event'
        
        # For larger conflicts, mark as concurrent events at same location
        event1['_concurrent_at_location'] = True
        event2['_concurrent_at_location'] = True
        return 'marked_as_concurrent'
    
    async def _resolve_resource_conflict(
        self, 
        conflict: EventConflict, 
        events: List[Dict[str, Any]]
    ) -> str:
        """Resolve resource conflicts"""
        # This would handle conflicts for shared resources
        # For now, just mark them
        for event in conflict.events:
            event['_has_resource_conflict'] = True
        return 'marked_resource_conflict'
    
    def _events_overlap(self, event1: Dict[str, Any], event2: Dict[str, Any]) -> bool:
        """Check if two events overlap in time"""
        if '_start_dt' not in event1 or '_start_dt' not in event2:
            return False
        
        start1, end1 = event1['_start_dt'], event1['_end_dt']
        start2, end2 = event2['_start_dt'], event2['_end_dt']
        
        return not (end1 <= start2 or end2 <= start1)
    
    def _calculate_overlap_severity(self, event1: Dict[str, Any], event2: Dict[str, Any]) -> str:
        """Calculate the severity of time overlap"""
        overlap_duration = self._calculate_overlap_duration(event1, event2)
        
        if overlap_duration < 15:
            return 'low'
        elif overlap_duration < 60:
            return 'medium'
        else:
            return 'high'
    
    def _calculate_overlap_duration(self, event1: Dict[str, Any], event2: Dict[str, Any]) -> float:
        """Calculate overlap duration in minutes"""
        if not self._events_overlap(event1, event2):
            return 0
        
        start1, end1 = event1['_start_dt'], event1['_end_dt']
        start2, end2 = event2['_start_dt'], event2['_end_dt']
        
        overlap_start = max(start1, start2)
        overlap_end = min(end1, end2)
        
        return (overlap_end - overlap_start).total_seconds() / 60
    
    def _calculate_event_priority_score(self, event: Dict[str, Any]) -> float:
        """Calculate priority score for an event"""
        score = 0.0
        
        # Verification confidence (0-40 points)
        score += event.get('verification_confidence', 0.5) * 40
        
        # Category importance (0-30 points)
        category_scores = {
            'festival': 30,
            'sports': 25,
            'music': 20,
            'market': 15,
            'food': 10,
            'art': 10,
            'technology': 5,
            'community': 5,
            'general': 0
        }
        score += category_scores.get(event.get('category', 'general'), 0)
        
        # Attendance estimate (0-30 points)
        attendance = event.get('attendance_estimate', 0)
        if attendance > 1000:
            score += 30
        elif attendance > 500:
            score += 20
        elif attendance > 100:
            score += 10
        else:
            score += 5
        
        return score
    
    def _estimate_end_time(self, event: Dict[str, Any]) -> str:
        """Estimate end time based on event category and typical durations"""
        try:
            start_time = datetime.fromisoformat(event['start_time'].replace('Z', '+00:00'))
            category = event.get('category', 'general')
            duration_hours = self.typical_durations.get(category, 2.0)
            
            end_time = start_time + timedelta(hours=duration_hours)
            return end_time.isoformat()
        except:
            # Fallback: 2 hours after start
            return event['start_time']
    
    def _generate_event_id(self, event: Dict[str, Any]) -> str:
        """Generate a unique ID for an event"""
        # Create ID from event properties
        id_string = f"{event.get('name', '')}_{event.get('location', '')}_{event.get('start_time', '')}"
        return hashlib.md5(id_string.encode()).hexdigest()[:12]
    
    def _clear_layers(self):
        """Clear all calendar layers"""
        for layer in self.layers.values():
            layer.data.clear()
            layer.metadata.clear()
    
    def _add_holidays_to_layer(self, holidays: List[str], date: datetime):
        """Add holidays to the holiday layer"""
        for holiday in holidays:
            self.layers['holidays'].add_item(
                holiday,
                {
                    'name': holiday,
                    'date': date.isoformat(),
                    'type': 'public_holiday'
                }
            )
    
    def _add_events_to_layer(self, events: List[Dict[str, Any]]):
        """Add events to the events layer"""
        for event in events:
            self.layers['events'].add_item(
                event.get('id', self._generate_event_id(event)),
                event,
                metadata={
                    'conflicts': event.get('_conflict_status'),
                    'adjusted': event.get('_adjusted_start') is not None
                }
            )
    
    def _add_weather_to_layer(self, weather: Dict[str, Any], date: datetime):
        """Add weather data to the weather layer"""
        self.layers['weather'].add_item(
            date.isoformat(),
            weather,
            metadata={'source': weather.get('source', 'unknown')}
        )
    
    async def _calculate_cultural_significance(
        self, 
        holidays: List[str], 
        events: List[Dict[str, Any]],
        location: str,
        date: datetime
    ) -> str:
        """Calculate cultural significance with enhanced logic"""
        significance_score = 0
        
        # Holiday impact (0-40 points)
        if holidays:
            significance_score += 40
        
        # Event diversity (0-30 points)
        unique_categories = set(e.get('category', 'general') for e in events)
        if len(unique_categories) >= 4:
            significance_score += 30
        elif len(unique_categories) >= 3:
            significance_score += 20
        elif len(unique_categories) >= 2:
            significance_score += 10
        
        # Event count (0-30 points)
        if len(events) >= 10:
            significance_score += 30
        elif len(events) >= 5:
            significance_score += 20
        elif len(events) >= 3:
            significance_score += 10
        
        # Determine significance level
        if significance_score >= 70:
            return "high"
        elif significance_score >= 40:
            return "medium"
        else:
            return "low"
    
    def _is_payday(self, date: datetime, location: str) -> bool:
        """Determine if it's a payday with location awareness"""
        # Common paydays
        common_paydays = [1, 15, 25, 30, 31]  # Extended from just 1st and 15th
        
        # Last day of month check
        next_day = date + timedelta(days=1)
        if next_day.month != date.month:
            return True  # Last day of month
        
        return date.day in common_paydays
    
    async def _calculate_days_to_holiday(self, location: str, date: datetime) -> int:
        """Calculate days to next holiday with actual holiday data"""
        # This would integrate with a holiday API or database
        # For now, simplified logic
        
        # Major holidays (month-day)
        major_holidays = [
            (1, 1),   # New Year
            (2, 14),  # Valentine's Day
            (3, 17),  # St. Patrick's Day
            (7, 4),   # Independence Day
            (10, 31), # Halloween
            (11, 24), # Thanksgiving (approximate)
            (12, 25), # Christmas
        ]
        
        current_date = date.date()
        current_year = date.year
        
        min_days = 365
        
        for month, day in major_holidays:
            holiday_date = datetime(current_year, month, day).date()
            
            # If holiday has passed this year, check next year
            if holiday_date < current_date:
                holiday_date = datetime(current_year + 1, month, day).date()
            
            days_until = (holiday_date - current_date).days
            min_days = min(min_days, days_until)
        
        return min_days
    
    async def _calculate_historical_engagement(
        self,
        events: List[Dict[str, Any]],
        weather: Dict[str, Any],
        holidays: List[str],
        date: datetime
    ) -> float:
        """Calculate historical engagement with enhanced logic"""
        engagement_score = 0.5  # Base score
        
        # Event factors
        event_score = len(events) * 0.05
        
        # High-attendance events boost
        high_attendance_events = [e for e in events if e.get('attendance_estimate', 0) > 500]
        event_score += len(high_attendance_events) * 0.1
        
        # Weather impact
        good_weather = weather.get('condition', '').lower() in ['sunny', 'clear', 'partly_cloudy']
        if good_weather:
            event_score *= 1.2
        
        # Holiday boost
        if holidays:
            event_score *= 1.5
        
        # Day of week factor (simplified - weekends get boost)
        if date.weekday() >= 5:  # Saturday or Sunday
            event_score *= 1.3
        
        engagement_score += min(event_score, 0.5)  # Cap additional score at 0.5
        
        return min(engagement_score, 1.0)
    
    def _calculate_event_density(self, events: List[Dict[str, Any]]) -> float:
        """Calculate event density (events per hour for the day)"""
        if not events:
            return 0.0
        
        # Consider a 16-hour active day (8 AM to midnight)
        active_hours = 16
        return len(events) / active_hours
    
    def _calculate_time_coverage(self, events: List[Dict[str, Any]]) -> float:
        """Calculate what percentage of the day has events"""
        if not events:
            return 0.0
        
        # Create time slots (hourly)
        time_slots = set()
        
        for event in events:
            if '_start_dt' in event and '_end_dt' in event:
                current = event['_start_dt']
                while current < event['_end_dt']:
                    time_slots.add(current.hour)
                    current += timedelta(hours=1)
        
        # Consider 16-hour active day
        return len(time_slots) / 16.0
    
    def _get_layer_summary(self) -> Dict[str, Any]:
        """Get a summary of all calendar layers"""
        summary = {}
        
        for name, layer in self.layers.items():
            summary[name] = {
                'item_count': len(layer.data),
                'priority': layer.priority
            }
        
        return summary
    
    async def query_calendar(
        self,
        date_range: Tuple[datetime, datetime],
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Query calendar data within a date range with filters"""
        start_date, end_date = date_range
        results = {
            'events': [],
            'holidays': [],
            'weather': [],
            'metadata': {}
        }
        
        # Get events in range
        for layer_name in ['events', 'holidays', 'weather']:
            if layer_name in self.layers:
                items = self.layers[layer_name].get_items_for_time_range(start_date, end_date)
                
                # Apply filters
                if filters:
                    items = self._apply_filters(items, filters)
                
                results[layer_name] = items
        
        # Add query metadata
        results['metadata'] = {
            'query_start': start_date.isoformat(),
            'query_end': end_date.isoformat(),
            'filters_applied': filters or {},
            'result_count': sum(len(results[k]) for k in ['events', 'holidays', 'weather'])
        }
        
        return results
    
    def _apply_filters(self, items: List[Any], filters: Dict[str, Any]) -> List[Any]:
        """Apply filters to a list of items"""
        filtered_items = []
        
        for item in items:
            include = True
            
            for key, value in filters.items():
                if key in item and item[key] != value:
                    include = False
                    break
            
            if include:
                filtered_items.append(item)
        
        return filtered_items
    
    async def update_calendar_event(
        self,
        event_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """Update a calendar event"""
        if 'events' in self.layers:
            if event_id in self.layers['events'].data:
                event = self.layers['events'].data[event_id]
                
                # Apply updates
                for key, value in updates.items():
                    if not key.startswith('_'):  # Don't update internal fields
                        event[key] = value
                
                # Update metadata
                self.layers['events'].metadata[event_id]['last_updated'] = datetime.utcnow().isoformat()
                
                self.logger.info("Event updated", event_id=event_id, updates=updates)
                return True
        
        self.logger.warning("Event not found for update", event_id=event_id)
        return False
    
    async def get_marketing_opportunities(
        self,
        calendar_data: CalendarData,
        target_audience: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Identify marketing opportunities from calendar data"""
        opportunities = []
        
        # High-score days are opportunities
        if calendar_data.opportunity_score >= 80:
            opportunities.append({
                'type': 'high_opportunity_day',
                'score': calendar_data.opportunity_score,
                'reason': 'High event density and favorable conditions',
                'recommended_actions': ['increase_ad_spend', 'launch_promotion', 'extend_hours']
            })
        
        # Holiday opportunities
        if calendar_data.holidays:
            opportunities.append({
                'type': 'holiday_marketing',
                'holidays': calendar_data.holidays,
                'reason': 'Holiday-specific marketing opportunity',
                'recommended_actions': ['holiday_themed_content', 'special_offers', 'early_bird_promotions']
            })
        
        # Event-based opportunities
        high_attendance_events = [
            e for e in calendar_data.events 
            if e.get('attendance_estimate', 0) > 1000
        ]
        
        if high_attendance_events:
            opportunities.append({
                'type': 'event_based_marketing',
                'events': [e.get('name') for e in high_attendance_events],
                'reason': 'Large events driving foot traffic',
                'recommended_actions': ['event_partnerships', 'location_based_ads', 'event_specials']
            })
        
        # Weather-based opportunities
        if calendar_data.weather.get('condition', '').lower() in ['sunny', 'clear']:
            opportunities.append({
                'type': 'weather_marketing',
                'weather': calendar_data.weather.get('condition'),
                'reason': 'Good weather driving outdoor activity',
                'recommended_actions': ['outdoor_promotions', 'patio_specials', 'recreational_offers']
            })
        
        return opportunities