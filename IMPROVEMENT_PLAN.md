# Dora Codebase Improvement Plan

## Overview
This document outlines improvements for the Dora event discovery system, taking into account the deliberate sequential processing to manage API quotas.

## Current Architecture Analysis

### Strengths
- Well-structured Pydantic models for type safety
- Good separation of agents with specific responsibilities
- Proper use of OpenAI agents framework
- Debug tracing capability for troubleshooting

### Key Constraint
**Sequential Processing is Intentional**: Event processing is deliberately sequential to stay within LLM API quotas. This constraint must be respected in all improvements.

## Priority Improvements

### 1. Code Organization & Modularity (High Priority)

#### Issue: Large monolithic functions
- `main_async()` in `__main__.py` is 150+ lines
- `handle_city()` in `telegram_bot.py` is complex and does multiple things

#### Solution:
```python
# Extract to separate service classes:
class EventDiscoveryService:
    """Handles event discovery logic"""
    async def discover_events(self, city: str, days_ahead: int, event_count: int) -> List[Event]

class NotificationService:
    """Handles notification generation"""
    def generate_notifications(self, events: List[Event], languages: List[str]) -> Dict[str, List[str]]

class EventFormatter:
    """Centralizes event formatting logic"""
    def format_for_telegram(self, event: Event) -> str
    def format_for_notification(self, event: Event) -> str
```

### 2. Error Handling & Resilience (High Priority)

#### Issue: Generic exception handling, no retry for OpenAI
#### Solution:
```python
# Create specific exceptions
class EventDiscoveryError(Exception): pass
class APIQuotaExceededError(EventDiscoveryError): pass
class EventValidationError(EventDiscoveryError): pass

# Add retry decorator for all API calls
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((APIError, RateLimitError))
)
async def call_with_retry(func, *args, **kwargs):
    return await func(*args, **kwargs)
```

### 3. Caching Layer (High Priority)

#### Issue: Repeated API calls for same queries
#### Solution: Add Redis or in-memory caching
```python
from functools import lru_cache
from datetime import datetime, timedelta

class EventCache:
    def __init__(self, ttl_hours: int = 24):
        self.ttl = timedelta(hours=ttl_hours)
        self._cache = {}
    
    def get_events(self, city: str, date_range: tuple) -> Optional[List[Event]]:
        key = f"{city}:{date_range}"
        if key in self._cache:
            data, timestamp = self._cache[key]
            if datetime.now() - timestamp < self.ttl:
                return data
        return None
    
    def set_events(self, city: str, date_range: tuple, events: List[Event]):
        key = f"{city}:{date_range}"
        self._cache[key] = (events, datetime.now())
```

### 4. Configuration Management (Medium Priority)

#### Issue: Hardcoded values throughout code
#### Solution: Centralize configuration
```python
# config.py
class AppConfig(BaseSettings):
    # API Settings
    max_events_per_request: int = 10
    days_ahead_default: int = 14
    
    # Notification Settings
    notification_char_limit: int = 140
    languages_per_city: int = 3
    
    # Telegram Settings
    authorized_users: List[str] = Field(default_factory=list)
    
    # Rate Limiting
    requests_per_minute: int = 10
    concurrent_requests: int = 1  # Keep sequential
    
    class Config:
        env_file = ".env"
```

### 5. Improve Trace Processor (Medium Priority)

#### Current: Basic logging only
#### Enhancement: Add metrics and performance tracking
```python
class EnhancedTraceProcessor(DebugTraceProcessor):
    def __init__(self):
        super().__init__()
        self.metrics = {
            'api_calls': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'errors': defaultdict(int),
            'processing_times': []
        }
    
    def on_span_end(self, span: Span[Any]) -> None:
        super().on_span_end(span)
        # Track metrics
        if "api_call" in span.name.lower():
            self.metrics['api_calls'] += 1
        # Record processing time
        if hasattr(span, 'duration'):
            self.metrics['processing_times'].append(span.duration)
    
    def get_report(self) -> Dict[str, Any]:
        return {
            **self.metrics,
            'avg_processing_time': statistics.mean(self.metrics['processing_times']) if self.metrics['processing_times'] else 0
        }
```

### 6. Input Validation (Medium Priority)

#### Issue: No validation of user inputs
#### Solution: Add comprehensive validation
```python
class InputValidator:
    @staticmethod
    def validate_city(city: str) -> str:
        if not city or len(city) < 2:
            raise EventValidationError("City name too short")
        if len(city) > 100:
            raise EventValidationError("City name too long")
        # Sanitize for API calls
        return city.strip()
    
    @staticmethod
    def validate_date_range(days_ahead: int) -> int:
        if days_ahead < 1:
            raise EventValidationError("Days ahead must be positive")
        if days_ahead > 365:
            raise EventValidationError("Cannot search more than 365 days ahead")
        return days_ahead
```

### 7. Resource Management (Low Priority)

#### Issue: No connection pooling for HTTP clients
#### Solution: Reuse HTTP sessions
```python
# Create singleton HTTP client
class HTTPClientManager:
    _instance = None
    _client = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_keepalive_connections=5)
            )
        return cls._instance
    
    @property
    def client(self):
        return self._client
```

## Implementation Plan

### Phase 1: Foundation (Week 1)
1. Extract service classes from `__main__.py`
2. Centralize configuration
3. Add input validation
4. Create custom exceptions

### Phase 2: Resilience (Week 2)
1. Implement retry logic for all API calls
2. Add circuit breaker pattern
3. Enhance error messages
4. Add structured logging

### Phase 3: Performance (Week 3)
1. Implement caching layer
2. Add connection pooling
3. Enhance trace processor with metrics
4. Add performance monitoring

### Phase 4: Polish (Week 4)
1. Add comprehensive tests
2. Update documentation
3. Add health check endpoint
4. Performance profiling

## Testing Strategy

### Unit Tests
- Test each service class independently
- Mock external API calls
- Test error scenarios

### Integration Tests
- Test full event discovery flow
- Test caching behavior
- Test rate limiting

### Performance Tests
- Measure API call counts
- Verify sequential processing
- Monitor memory usage

## Monitoring & Observability

### Metrics to Track
- API calls per minute (ensure within quota)
- Cache hit/miss ratio
- Error rates by type
- Processing time per event
- Memory usage

### Logging Standards
```python
# Use structured logging
logger.info("Event discovered", extra={
    "city": city,
    "event_name": event.name,
    "event_date": event.date,
    "processing_time": elapsed
})
```

## Migration Notes

### Backward Compatibility
- Keep existing CLI interface
- Maintain current API contracts
- Gradual refactoring approach

### Configuration Migration
```bash
# Old way
python -m dora "New York"

# New way (same interface, better internals)
python -m dora "New York"
```

## Success Criteria

1. **Maintainability**: Code complexity reduced by 50%
2. **Performance**: 80% cache hit rate for repeated queries
3. **Reliability**: 99% success rate with retry logic
4. **Observability**: Full visibility into API usage and quotas
5. **Testability**: 80%+ code coverage

## Notes on Sequential Processing

The sequential processing constraint is respected throughout this plan:
- No parallel API calls to LLM services
- Caching reduces need for API calls, not parallelization
- Rate limiting ensures we stay within quotas
- Retry logic includes exponential backoff

This approach maintains API quota compliance while improving other aspects of the system.