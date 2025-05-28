#!/usr/bin/env python
"""Entry point for running the HTTP server."""

import asyncio
import logging
import os
import sys

import uvicorn
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dora.models.config import DoraConfig

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def main():
    """Run the HTTP server."""
    config = DoraConfig()
    
    if not config.openai_api_key:
        logger.error("OPENAI_API_KEY environment variable is required")
        sys.exit(1)
    
    if not config.http_enabled:
        logger.info("HTTP server is disabled in configuration")
        sys.exit(0)
    
    logger.info(f"Starting HTTP server on {config.http_host}:{config.http_port}")
    
    # Run the FastAPI app with uvicorn
    uvicorn.run(
        "dora.http_server:app",
        host=config.http_host,
        port=config.http_port,
        reload=os.getenv("DEBUG", "false").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()