#!/bin/bash

# Calendar Cache MCP Server Startup Script
# This script starts the Dora Calendar Cache MCP server

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CACHE_SERVER_MODULE="dora.mcp.calendar_cache_server"
LOG_FILE="/tmp/dora_calendar_cache_server.log"

# Environment variables with defaults
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export CALENDAR_CACHE_TTL_SECONDS="${CALENDAR_CACHE_TTL_SECONDS:-86400}"
export REDIS_POOL_SIZE="${REDIS_POOL_SIZE:-10}"

echo "Starting Dora Calendar Cache MCP Server..."
echo "Project Root: $PROJECT_ROOT"
echo "Redis URL: $REDIS_URL"
echo "Default TTL: ${CALENDAR_CACHE_TTL_SECONDS}s"
echo "Pool Size: $REDIS_POOL_SIZE"
echo "Log File: $LOG_FILE"

# Change to project directory
cd "$PROJECT_ROOT"

# Check if Redis is available
echo "Checking Redis connectivity..."
if command -v redis-cli &> /dev/null; then
    if ! redis-cli -u "$REDIS_URL" ping &> /dev/null; then
        echo "Warning: Redis server may not be available at $REDIS_URL"
        echo "Make sure Redis is running and accessible"
    else
        echo "Redis connection successful"
    fi
else
    echo "redis-cli not found, skipping connectivity check"
fi

# Create log directory
mkdir -p "$(dirname "$LOG_FILE")"

# Clear previous log
> "$LOG_FILE"

echo "Starting Calendar Cache Server..."
echo "Server output will be logged to: $LOG_FILE"
echo "Use Ctrl+C to stop the server"

# Start the server using uv
exec uv run python -m "$CACHE_SERVER_MODULE"