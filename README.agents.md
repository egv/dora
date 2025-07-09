# Dora Multi-Agent System - Container Deployment

This guide covers deploying the Dora multi-agent system using Podman containers.

## 🏗️ Architecture

The system consists of:
- **EventSearchAgent** (port 8001) - Searches for events using Google A2A protocol
- **CalendarIntelligenceAgent** (port 8002) - Analyzes calendar data and provides insights
- **Redis** (port 6379) - Caching layer for API responses
- **PostgreSQL** (port 5432) - Database for events, weather data, and insights

## 🚀 Quick Start

### Prerequisites

- Podman installed and running
- docker-compose or podman-compose available
- Python 3.11+ (for development)

### 1. Environment Setup

Create a `.env` file in the project root:

```bash
# Weather API (optional)
WEATHER_API_KEY=your_openweather_api_key_here

# Database credentials (used by containers)
POSTGRES_DB=dora
POSTGRES_USER=dora  
POSTGRES_PASSWORD=dora_password
```

### 2. Build and Run

```bash
# Start all services
./scripts/run-agents.sh

# Or manually with podman-compose
podman-compose -f docker-compose.agents.yml up -d
```

### 3. Verify Services

```bash
# Check EventSearchAgent
curl http://localhost:8001/health

# Check CalendarIntelligenceAgent
curl http://localhost:8002/health

# View logs
podman-compose -f docker-compose.agents.yml logs -f
```

### 4. Stop Services

```bash
# Stop all services
./scripts/stop-agents.sh

# Or manually
podman-compose -f docker-compose.agents.yml down
```

## 🔧 Development

### Running in Development Mode

```bash
# Start supporting services only (redis, postgres)
podman-compose -f docker-compose.agents.yml up -d redis postgres

# Run agents locally for development
uv run python -m agents.event_search &
uv run python -m agents.calendar_intelligence &
```

### Development Container

```bash
# Start development container with volume mounts
podman-compose -f docker-compose.agents.yml run --rm dev bash

# Inside container:
uv run python -m agents.event_search
uv run python -m agents.calendar_intelligence
```

## 🧪 Testing

### A2A Integration Tests

```bash
# Run integration tests
uv run pytest tests/test_a2a_integration.py -v

# Test specific agent
uv run pytest tests/test_event_search.py -v
uv run pytest tests/test_calendar_intelligence.py -v
```

### Manual Testing

```bash
# Test EventSearchAgent A2A communication
curl -X POST http://localhost:8001/ \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-123",
    "params": {
      "message": {
        "messageId": "msg-123",
        "role": "user",
        "parts": [
          {
            "text": "{\"city\": \"San Francisco\", \"events_count\": 3}"
          }
        ]
      }
    }
  }'

# Test CalendarIntelligenceAgent
curl -X POST http://localhost:8002/ \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-456",
    "params": {
      "message": {
        "messageId": "msg-456", 
        "role": "user",
        "parts": [
          {
            "text": "{\"location\": \"New York\", \"date\": \"2025-01-15\"}"
          }
        ]
      }
    }
  }'
```

## 📊 Database Schema

The PostgreSQL database includes:

- `events` - Event data with location, timing, and metadata
- `weather_data` - Weather information by location and date
- `calendar_insights` - Generated insights and opportunity scores

### Database Access

```bash
# Connect to PostgreSQL
podman exec -it dora-postgres psql -U dora -d dora

# View events
SELECT * FROM events LIMIT 5;

# View weather data
SELECT * FROM weather_data LIMIT 5;

# View insights
SELECT * FROM calendar_insights LIMIT 5;
```

## 🗃️ Data Persistence

Volumes are used for data persistence:
- `redis-data` - Redis cache data
- `postgres-data` - PostgreSQL database files

### Backup and Restore

```bash
# Backup database
podman exec dora-postgres pg_dump -U dora dora > backup.sql

# Restore database
podman exec -i dora-postgres psql -U dora -d dora < backup.sql
```

## 🔍 Monitoring

### Health Checks

Each agent provides health endpoints:
- EventSearchAgent: `GET /health`
- CalendarIntelligenceAgent: `GET /health`

### Logs

```bash
# View all service logs
podman-compose -f docker-compose.agents.yml logs -f

# View specific service logs
podman-compose -f docker-compose.agents.yml logs -f event-search-agent
podman-compose -f docker-compose.agents.yml logs -f calendar-intelligence-agent
```

### Performance Monitoring

```bash
# Monitor container resource usage
podman stats

# Monitor specific container
podman stats dora-event-search-agent
```

## 🛠️ Troubleshooting

### Common Issues

1. **Port conflicts**: Ensure ports 8001, 8002, 6379, 5432 are available
2. **Container build failures**: Check Containerfile syntax and dependencies
3. **A2A communication issues**: Verify agent health and request format
4. **Database connection issues**: Check PostgreSQL container status

### Debug Mode

```bash
# Run with debug logging
podman-compose -f docker-compose.agents.yml up --build

# Connect to container for debugging
podman exec -it dora-event-search-agent bash
```

### Reset Environment

```bash
# Stop all services and remove volumes
podman-compose -f docker-compose.agents.yml down -v

# Remove all containers and images
podman system prune -af

# Rebuild from scratch
./scripts/run-agents.sh
```

## 🚀 Production Deployment

For production deployment, consider:

1. **Environment variables**: Use secure secret management
2. **Reverse proxy**: Add nginx or traefik for load balancing
3. **SSL/TLS**: Enable HTTPS for external access
4. **Resource limits**: Set appropriate memory and CPU limits
5. **Monitoring**: Add Prometheus/Grafana for observability
6. **Backup strategy**: Regular database backups

### Example Production Override

```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  event-search-agent:
    restart: always
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
    environment:
      - LOG_LEVEL=INFO
      
  calendar-intelligence-agent:
    restart: always
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
    environment:
      - LOG_LEVEL=INFO
```

## 📚 API Documentation

### EventSearchAgent

- **Endpoint**: `POST /`
- **Protocol**: A2A JSON-RPC
- **Skills**: `search_events`
- **Parameters**:
  - `city` (required): City name
  - `events_count` (optional): Number of events (default: 10)
  - `days_ahead` (optional): Days to search ahead (default: 14)

### CalendarIntelligenceAgent

- **Endpoint**: `POST /`
- **Protocol**: A2A JSON-RPC
- **Skills**: `get_calendar_data`, `get_marketing_insights`, `analyze_opportunity`
- **Parameters**:
  - `location` (required): Location name
  - `date` (required): Date in YYYY-MM-DD format
  - `days_ahead` (optional): Days to analyze (default: 14)

---

For more information, see the main project README and agent-specific documentation.