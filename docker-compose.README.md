# Docker Compose Setup

This directory contains the Docker Compose configuration for running Dora with HTTPS support.

## Services

- **traefik**: Reverse proxy with automatic Let's Encrypt SSL certificates
- **http-server**: The main HTTP API server (behind Traefik)
- **telegram-bot**: The Telegram bot service

## HTTPS Configuration

The setup includes automatic HTTPS with Let's Encrypt certificates for the domain `al-vizier.haet.ru`.

### Features:
- Automatic SSL certificate generation and renewal
- HTTP to HTTPS redirect
- Traefik dashboard available at `https://al-vizier.haet.ru/dashboard/`

### Ports:
- **80**: HTTP (redirects to HTTPS)
- **443**: HTTPS (main API)
- **8080**: Traefik dashboard (insecure, for local access only)

## Running

```bash
# Make sure the domain points to your server
docker-compose up -d
```

## Configuration

Environment variables are loaded from `.env` file. Make sure to configure:

- `OPENAI_API_KEY`: Your OpenAI API key
- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token
- Other configuration variables as needed

## SSL Certificates

- Certificates are automatically managed by Let's Encrypt
- Certificate data is stored in `./traefik-data/` (excluded from git)
- Email for certificates: `g.evstratov@gmail.com`

## API Access

Once running, the API will be available at:
- `https://al-vizier.haet.ru/` (main API)
- `https://al-vizier.haet.ru/health` (health check)
- `https://al-vizier.haet.ru/v1/models` (OpenAI-compatible models endpoint)
- `https://al-vizier.haet.ru/v1/chat/completions` (OpenAI-compatible chat endpoint)

## Services

### 1. Traefik Reverse Proxy
- Handles SSL termination and certificate management
- Automatically redirects HTTP to HTTPS
- Provides dashboard at `/dashboard/`

### 2. HTTP Server (`http-server`)
The HTTP API server that provides OpenAI-compatible endpoints for processing city queries.
- Runs internally on port 8000
- Exposed via Traefik on port 443 (HTTPS)
- Provides `/v1/chat/completions` endpoint
- Health check endpoint at `/health`

### 3. Telegram Bot (`telegram-bot`)
The main Telegram bot that users interact with.
- Connects to the HTTP server for processing requests
- Depends on the HTTP server being healthy

## Usage

### Prerequisites
1. Make sure you have Docker and Docker Compose installed
2. Ensure the domain `al-vizier.haet.ru` points to your server's IP address
3. Create a `.env` file with your API keys:
```bash
PERPLEXITY_API_KEY=your_perplexity_key
OPENAI_API_KEY=your_openai_key
TELEGRAM_API_KEY=your_telegram_bot_token
```

### Running the Services

Start all services:
```bash
docker compose up -d
```

View logs:
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f telegram-bot
docker compose logs -f http-server
docker compose logs -f traefik
```

Stop all services:
```bash
docker compose down
```

### Testing the HTTPS API

Test the HTTPS API:
```bash
# Health check
curl https://al-vizier.haet.ru/health

# List models
curl https://al-vizier.haet.ru/v1/models

# Send a chat completion request
curl -X POST https://al-vizier.haet.ru/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dora-events-v1",
    "messages": [{"role": "user", "content": "Find events in San Francisco"}],
    "temperature": 0
  }'
```

## Volumes

- `./cache`: Persistent storage for the memory cache database
- `./logs`: Application logs (if configured)
- `./traefik-data`: SSL certificates and Traefik configuration

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

## Logs

Logs are stored in the `./logs` directory.

## Cache

Cache data is stored in the `./cache` directory.

## Troubleshooting

1. **Certificate issues**: Make sure the domain `al-vizier.haet.ru` points to your server's IP
2. **Permission issues**: Ensure `traefik-data/acme.json` has 600 permissions
3. **Port conflicts**: Make sure ports 80 and 443 are not used by other services
4. **API key errors**: Check your `.env` file has all required keys
5. **Memory issues**: Adjust Docker memory limits if needed

## Monitoring

View cache statistics:
```bash
docker compose exec telegram-bot sqlite3 /app/cache/dora_memory.db "SELECT * FROM cache_metadata;"
```

Access Traefik dashboard:
- Local: `http://localhost:8080/dashboard/`
- Remote: `https://al-vizier.haet.ru/dashboard/`

## Security Notes

- The Traefik dashboard is accessible via HTTPS with the same certificate
- ACME certificates are stored securely with 600 permissions
- HTTP traffic is automatically redirected to HTTPS
- Only necessary ports are exposed