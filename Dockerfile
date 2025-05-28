FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install UV
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml uv.lock README.md ./

# Create cache and logs directories
RUN mkdir -p /app/cache /app/logs

# Install Python dependencies using UV
RUN uv sync --frozen

# Copy application code
COPY dora ./dora

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Create a non-root user to run the application
RUN useradd -m dora && \
    chown -R dora:dora /app

USER dora

# Default command (can be overridden in docker-compose)
CMD ["uv", "run", "python", "-m", "dora", "--help"]