#!/usr/bin/env python
"""Run the Dora Telegram bot."""

import asyncio
import logging
import sys
from pathlib import Path

# Add the parent directory to the path so we can import dora
sys.path.insert(0, str(Path(__file__).parent))

from dora.telegram_bot import main

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    try:
        main()
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        logging.error(f"Bot error: {e}")
        sys.exit(1)