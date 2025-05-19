"""MCP client for Dora's memory cache."""

import json
import asyncio
import subprocess
import time
from typing import Dict, Any, Optional, List

from mcp.client import ClientSession
from mcp.client.stdio import StdioTransport

from dora.models.config import DoraConfig


class MemoryCacheClient:
    """Client for Dora's MCP memory cache server."""
    
    def __init__(self, config: DoraConfig):
        """Initialize the memory cache client."""
        self.config = config
        self.cache_enabled = config.memory_cache_enabled
        self.session: Optional[ClientSession] = None
        self.transport: Optional[StdioTransport] = None
        self.process: Optional[subprocess.Popen] = None
    
    async def connect(self):
        """Connect to the MCP memory server."""
        if not self.cache_enabled:
            return
        
        try:
            # Start the memory server process
            self.process = subprocess.Popen(
                ["./run_memory_server.sh"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Create transport and session
            self.transport = StdioTransport(
                self.process.stdin,
                self.process.stdout
            )
            
            # Start transport
            await self.transport.start()
            
            # Create session
            self.session = ClientSession(self.transport.receive_messages())
            await self.session.initialize()
            
        except Exception as e:
            print(f"Failed to connect to memory cache: {e}")
            self.cache_enabled = False
    
    async def disconnect(self):
        """Disconnect from the MCP memory server."""
        if self.session:
            await self.session.close()
        
        if self.transport:
            await self.transport.close()
        
        if self.process:
            self.process.terminate()
            self.process.wait()
    
    async def check_event(self, event_data: Dict[str, Any]) -> bool:
        """Check if an event exists in the cache."""
        if not self.cache_enabled or not self.session:
            return False
        
        try:
            result = await self.session.call_tool(
                "check_event",
                arguments={"event_data": event_data}
            )
            
            # Parse the result
            result_data = json.loads(result[0].text)
            return result_data.get("exists", False)
            
        except Exception as e:
            print(f"Error checking event in cache: {e}")
            return False
    
    async def get_event(self, event_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get cached event data."""
        if not self.cache_enabled or not self.session:
            return None
        
        try:
            result = await self.session.call_tool(
                "get_event",
                arguments={"event_data": event_data}
            )
            
            # Parse the result
            result_data = json.loads(result[0].text)
            return result_data if result_data else None
            
        except Exception as e:
            print(f"Error getting event from cache: {e}")
            return None
    
    async def store_event(
        self,
        event_data: Dict[str, Any],
        classification: Dict[str, Any],
        notifications: List[Dict[str, Any]],
        processing_time_ms: int = 0
    ) -> Optional[str]:
        """Store event data in cache."""
        if not self.cache_enabled or not self.session:
            return None
        
        try:
            result = await self.session.call_tool(
                "store_event",
                arguments={
                    "event_data": event_data,
                    "classification": classification,
                    "notifications": notifications,
                    "processing_time_ms": processing_time_ms
                }
            )
            
            # Parse the result
            result_data = json.loads(result[0].text)
            return result_data.get("event_id")
            
        except Exception as e:
            print(f"Error storing event in cache: {e}")
            return None
    
    async def get_cache_stats(self) -> Optional[Dict[str, Any]]:
        """Get cache statistics."""
        if not self.cache_enabled or not self.session:
            return None
        
        try:
            result = await self.session.call_tool(
                "cache_stats",
                arguments={}
            )
            
            # Parse the result
            return json.loads(result[0].text)
            
        except Exception as e:
            print(f"Error getting cache stats: {e}")
            return None