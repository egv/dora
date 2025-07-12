# Testing Guide for Dora Calendar Intelligence System

This document describes the testing strategy and how to run different types of tests in the Dora project.

## Test Structure

### Unit Tests
Unit tests mock external dependencies and test individual components in isolation.

**Location**: `tests/test_*.py` (except integration tests)

**Run unit tests**:
```bash
# Run all unit tests
uv run python -m pytest tests/ -v

# Run specific test file
uv run python -m pytest tests/test_database_repositories.py -v

# Run with coverage
uv run python -m pytest tests/ --cov=dora --cov-report=html
```

### Integration Tests
Integration tests use real database connections to verify the complete data persistence layer.

**Location**: `tests/test_database_integration.py`

**Requirements**:
- PostgreSQL database server
- Redis server
- Proper credentials and connectivity

## Running Integration Tests

### Option 1: Automatic Setup with Docker/Podman (Recommended)

The easiest way to run integration tests is using the provided script that sets up test databases automatically:

```bash
# Run integration tests with automatic database setup
./scripts/run_integration_tests.sh
```

This script will:
1. Start PostgreSQL and Redis containers
2. Initialize the database schema
3. Run all integration tests
4. Clean up containers when finished

### Option 2: Manual Database Setup

If you have existing PostgreSQL and Redis instances:

```bash
# Set environment variables
export TEST_DATABASE_URL="postgresql://user:password@localhost:5432/test_db"
export TEST_REDIS_URL="redis://localhost:6379/1"
export RUN_INTEGRATION_TESTS=1

# Initialize test database schema
psql $TEST_DATABASE_URL < scripts/init_db.sql

# Run integration tests
uv run python -m pytest tests/test_database_integration.py -v
```

### Option 3: Skip Integration Tests

By default, integration tests are skipped if `RUN_INTEGRATION_TESTS` is not set:

```bash
# This will skip integration tests (default behavior)
uv run python -m pytest tests/test_database_integration.py -v
# Output: 12 skipped
```

## Test Categories

### Database Repository Tests

**Unit Tests** (`test_database_repositories.py`):
- ✅ Repository initialization
- ✅ Data model conversions
- ✅ Mocked database operations
- ✅ Caching functionality
- ✅ Error handling

**Integration Tests** (`test_database_integration.py`):
- ✅ Real database CRUD operations
- ✅ Search and filtering functionality
- ✅ Statistics generation
- ✅ Cross-repository workflows
- ✅ Database health checks
- ✅ Connection pool management

### A2A Integration Tests

**Location**: `tests/test_a2a_integration.py`
- Agent-to-Agent communication
- Service discovery
- Notification systems
- Workflow orchestration

### Component Tests

**Calendar Intelligence**: `tests/test_calendar_intelligence.py`
**Event Search**: `tests/test_event_search.py`
**Event Management**: `tests/test_event_manager.py`
**Enhanced Calendar Builder**: `tests/test_enhanced_calendar_builder.py`

## Test Configuration

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `RUN_INTEGRATION_TESTS` | Enable integration tests | `False` |
| `TEST_DATABASE_URL` | Test PostgreSQL connection | `postgresql://dora:dora_password@localhost:5432/dora_test` |
| `TEST_REDIS_URL` | Test Redis connection | `redis://localhost:6379/1` |

### Test Database Schema

Integration tests use the same schema as production but with test data:

- **Events table**: Sample tech conferences and music festivals
- **Weather data table**: Sample weather for test locations
- **Calendar insights table**: Sample AI-generated insights

## Continuous Integration

### GitHub Actions (Future)

```yaml
# Example CI configuration
- name: Run Unit Tests
  run: uv run python -m pytest tests/ --ignore=tests/test_database_integration.py

- name: Setup Test Databases
  run: |
    docker run -d --name postgres-test -e POSTGRES_PASSWORD=test postgres:15
    docker run -d --name redis-test redis:7

- name: Run Integration Tests
  run: ./scripts/run_integration_tests.sh
```

## Test Data Management

### Fixtures and Sample Data

All tests use consistent sample data:

```python
# Sample event
Event(
    event_id="test_event_123",
    name="Integration Test Event",
    location="Test City, Test State",
    start_time=datetime.now() + timedelta(days=1),
    category="integration_test"
)

# Sample weather
WeatherData(
    location="Test City, Test State",
    date=date.today(),
    temperature=25.5,
    weather_condition="sunny"
)

# Sample insights
CalendarInsights(
    location="Test City, Test State",
    opportunity_score=0.85,
    confidence_score=0.92
)
```

### Test Cleanup

Integration tests automatically clean up test data after each test to ensure isolation.

## Performance Testing

### Database Performance

Integration tests include performance-related checks:
- Connection pool efficiency
- Query execution timing
- Bulk operations
- Cache hit/miss ratios

### Load Testing (Future)

```bash
# Example load testing with locust
pip install locust
locust -f tests/load_tests/api_load_test.py
```

## Debugging Tests

### Running with Debug Output

```bash
# Verbose output with logs
uv run python -m pytest tests/ -v -s --log-cli-level=DEBUG

# Stop on first failure
uv run python -m pytest tests/ -x

# Run specific test method
uv run python -m pytest tests/test_database_integration.py::TestEventRepositoryIntegration::test_event_crud_operations -v
```

### Database Debugging

```bash
# Connect to test database for manual inspection
psql postgresql://dora:dora_test_password@localhost:5433/dora_test

# Check Redis test data
redis-cli -p 6380
```

## Test Results Summary

### Current Status

| Test Suite | Tests | Status |
|------------|-------|---------|
| Database Repositories (Unit) | 24 | ✅ Passing |
| Database Integration | 12 | ✅ Ready (requires DB) |
| A2A Integration | 35 | ✅ Passing |
| Calendar Intelligence | 8 | ✅ Passing |
| Event Search | 10 | ✅ Passing |
| Enhanced Calendar Builder | 15 | ✅ Passing |

### Coverage Goals

- **Unit Tests**: >90% line coverage
- **Integration Tests**: All major workflows covered
- **Error Scenarios**: Database failures, connection issues
- **Performance**: Response time thresholds verified

## Contributing

When adding new features:

1. **Write unit tests first** with mocked dependencies
2. **Add integration tests** for database-related features
3. **Update test documentation** if adding new test categories
4. **Ensure cleanup** in integration tests to prevent data pollution

## Troubleshooting

### Common Issues

**"Database not available"**: Ensure PostgreSQL is running and accessible
**"Redis connection failed"**: Check Redis server status and port configuration
**"Permission denied"**: Verify database user has sufficient privileges
**"Port already in use"**: Change test ports in the integration script

### Test Environment Reset

```bash
# Reset test environment
./scripts/run_integration_tests.sh

# Or manually clean up
podman stop dora-test-postgres dora-test-redis
podman rm dora-test-postgres dora-test-redis
```