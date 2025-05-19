#!/bin/bash

# Run the Dora Memory MCP Server

# Activate virtual environment if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Set environment variables
export MEMORY_CACHE_PATH="./cache/dora_memory.db"
export MEMORY_CACHE_TTL_DAYS="7"

# Run the MCP server
exec uv run python -m dora.mcp.memory_server