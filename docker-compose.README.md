# Docker Compose Setup for Dora

This Docker Compose configuration allows you to run all Dora components together.

## Services

### 1. HTTP Server (`http-server`)
The HTTP API server that provides OpenAI-compatible endpoints for processing city queries.
- Runs on port 8000
- Provides `/v1/chat/completions` endpoint
- Health check endpoint at `/health`

### 2. Telegram Bot (`telegram-bot`)
The main Telegram bot that users interact with.
- Connects to the HTTP server for processing requests
- Depends on the HTTP server being healthy

### 3. CLI Interface (`dora-cli`)
Command-line interface for testing and debugging.

### 4. One-off Processing (`dora`)
For running single city queries.

## Usage

### Prerequisites
1. Make sure you have Docker and Docker Compose installed
2. Create a `.env` file with your API keys:
```bash
PERPLEXITY_API_KEY=your_perplexity_key
OPENAI_API_KEY=your_openai_key
TELEGRAM_API_KEY=your_telegram_bot_token
```

### Running the Services

Start both HTTP server and Telegram bot:
```bash
docker compose up -d
```

Start only the HTTP server:
```bash
docker compose up -d http-server
```

Start only the Telegram bot (will also start HTTP server):
```bash
docker compose up -d telegram-bot
```

View logs:
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f telegram-bot
docker compose logs -f http-server
```

Stop all services:
```bash
docker compose down
```

### Testing the HTTP Server

Test the HTTP server directly:
```bash
# Health check
curl http://localhost:8000/health

# List models
curl http://localhost:8000/v1/models

# Send a chat completion request
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dora-events-v1",
    "messages": [{"role": "user", "content": "San Francisco"}],
    "temperature": 0
  }'
```

### Using the CLI

Run a one-time city query:
```bash
docker compose run --rm dora-cli uv run python -m dora --city "London" --output pretty
```

Or use the interactive CLI:
```bash
docker compose run --rm dora-cli bash
# Then inside the container:
uv run python -m dora --city "Paris"
```

### One-off City Processing

Process a specific city:
```bash
docker compose run --rm dora uv run python -m dora --city "Tokyo" --events 5
```

## Volumes

- `./cache`: Persistent storage for the memory cache database
- `./logs`: Application logs (if configured)

## Environment Variables

All services support these environment variables:

- `MEMORY_CACHE_ENABLED`: Enable/disable memory caching (default: true)
- `MEMORY_CACHE_PATH`: Path to cache database (default: /app/cache/dora_memory.db)
- `MEMORY_CACHE_TTL_DAYS`: Days to keep cached entries (default: 7)
- `MEMORY_CACHE_MAX_SIZE_MB`: Maximum cache size (default: 100)
- `LOG_LEVEL`: Logging level (default: INFO)
- `ENABLE_TRACING`: Enable OpenAI tracing (default: true)
- `HTTP_ENABLED`: Enable HTTP server (default: true)
- `HTTP_HOST`: HTTP server host (default: 0.0.0.0)
- `HTTP_PORT`: HTTP server port (default: 8000)
- `HTTP_API_KEYS`: Comma-separated API keys for HTTP authentication (optional)

## Building Images

Build all images:
```bash
docker compose build
```

Build a specific service:
```bash
docker compose build telegram-bot
```

## Monitoring

View cache statistics:
```bash
docker compose exec telegram-bot sqlite3 /app/cache/dora_memory.db "SELECT * FROM cache_metadata;"
```

## Troubleshooting

1. **Permission issues**: Make sure the cache directory is writable
2. **API key errors**: Check your `.env` file has all required keys
3. **Memory issues**: Adjust Docker memory limits if needed

## Development

For development with hot-reloading:
```bash
docker compose run --rm -v $(pwd):/app dora-cli bash
```

This mounts your local code directory into the container for live updates.