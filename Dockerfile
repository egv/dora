FROM python:3.11-slim

WORKDIR /app

# Copy requirements file and install dependencies
COPY pyproject.toml .
COPY README.md .

# Install build dependencies
RUN pip install --no-cache-dir "uv==0.1.16" && \
    uv pip install --no-cache-dir -e .

# Copy application code
COPY dora ./dora

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Create a non-root user to run the application
RUN useradd -m dora && \
    chown -R dora:dora /app

USER dora

# Run the application
ENTRYPOINT ["python", "-m", "dora"]