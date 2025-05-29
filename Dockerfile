# Use uv's official image based on Python 3.11
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# No additional system dependencies needed - the base image has everything we need

# Copy project files
COPY pyproject.toml uv.lock README.md ./

# Create cache and logs directories
RUN mkdir -p /app/cache /app/logs

# Install Python dependencies using UV
RUN uv sync --frozen --no-cache

# Copy application code
COPY dora ./dora
COPY run_bot.py run_http_server.py ./

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default command (can be overridden in docker-compose)
CMD ["uv", "run", "python", "-m", "dora", "--help"]