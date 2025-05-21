# Docker Compose Setup for Dora

This Docker Compose configuration allows you to run all Dora components together.

## Services

### 1. Telegram Bot (`telegram-bot`)
The main Telegram bot that users interact with.

### 2. CLI Interface (`dora-cli`)
Command-line interface for testing and debugging.

### 3. One-off Processing (`dora`)
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

### Running the Telegram Bot

Start the Telegram bot:
```bash
docker-compose up -d telegram-bot
```

View logs:
```bash
docker-compose logs -f telegram-bot
```

Stop the bot:
```bash
docker-compose down
```

### Using the CLI

Run a one-time city query:
```bash
docker-compose run --rm dora-cli uv run python -m dora --city "London" --output pretty
```

Or use the interactive CLI:
```bash
docker-compose run --rm dora-cli bash
# Then inside the container:
uv run python -m dora --city "Paris"
```

### One-off City Processing

Process a specific city:
```bash
docker-compose run --rm dora uv run python -m dora --city "Tokyo" --events 5
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

## Building Images

Build all images:
```bash
docker-compose build
```

Build a specific service:
```bash
docker-compose build telegram-bot
```

## Monitoring

View cache statistics:
```bash
docker-compose exec telegram-bot sqlite3 /app/cache/dora_memory.db "SELECT * FROM cache_metadata;"
```

## Troubleshooting

1. **Permission issues**: Make sure the cache directory is writable
2. **API key errors**: Check your `.env` file has all required keys
3. **Memory issues**: Adjust Docker memory limits if needed

## Development

For development with hot-reloading:
```bash
docker-compose run --rm -v $(pwd):/app dora-cli bash
```

This mounts your local code directory into the container for live updates.