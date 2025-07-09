# Multi-stage Containerfile for Dora Multi-Agent System
FROM python:3.11-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Copy source code
COPY . .

# EventSearchAgent stage
FROM base as event-search-agent
EXPOSE 8001
CMD ["uv", "run", "python", "-m", "agents.event_search"]

# CalendarIntelligenceAgent stage  
FROM base as calendar-intelligence-agent
EXPOSE 8002
CMD ["uv", "run", "python", "-m", "agents.calendar_intelligence"]

# Development stage with all tools
FROM base as development
RUN uv sync --all-extras
CMD ["bash"]