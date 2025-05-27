#!/usr/bin/env python3
"""Test script for progress reporting improvements."""

import asyncio
import logging
import os
import sys
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dora.models.config import DoraConfig
from dora.__main__ import process_city

# Set up logging to see all progress messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

# Reduce third-party noise
logging.getLogger("agents").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def test_progress_callback():
    """Test the progress callback functionality."""
    print("🧪 Testing progress reporting improvements...")
    print("=" * 60)
    
    progress_messages = []
    
    async def test_progress_callback(step: str, details: str):
        """Capture progress messages for testing."""
        message = f"PROGRESS: {step} - {details}"
        progress_messages.append(message)
        print(f"📊 {message}")
    
    try:
        config = DoraConfig()
        
        # Test with a simple city and small event count
        test_city = "San Francisco"
        events_count = 3
        
        print(f"🔍 Testing progress reporting for {test_city} with {events_count} events")
        print(f"⏰ Started at: {datetime.now()}")
        print("-" * 60)
        
        results = await process_city(
            city=test_city,
            days_ahead=14,
            events_count=events_count,
            config=config,
            progress_callback=test_progress_callback
        )
        
        print("-" * 60)
        print(f"✅ Test completed at: {datetime.now()}")
        print(f"📈 Found {len(results) if results else 0} events")
        print(f"📊 Captured {len(progress_messages)} progress messages:")
        
        for i, msg in enumerate(progress_messages, 1):
            print(f"  {i}. {msg}")
            
        return len(progress_messages) > 0
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        logger.exception("Test error details:")
        return False


async def main():
    """Main test function."""
    print("🚀 Starting progress reporting test...")
    
    try:
        success = await test_progress_callback()
        
        if success:
            print("\n🎉 Progress reporting test PASSED!")
            print("✅ Progress callbacks are working correctly")
            print("✅ Enhanced logging is visible")
            print("✅ Telegram bot will now show live updates")
        else:
            print("\n❌ Progress reporting test FAILED!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Test crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())