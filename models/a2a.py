"""
Internal Business Models

This module contains models for internal business logic that are not part 
of the official Google A2A specification. Official A2A models (AgentCard, 
AgentSkill, Task, etc.) are imported from a2a.types.

Only models needed for business logic (metrics, status tracking) are kept here.
Custom A2A protocol models have been removed in favor of Google's official implementation.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    """Agent status indicators for internal monitoring"""
    INITIALIZING = "initializing"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"


class AgentMetrics(BaseModel):
    """Agent performance metrics for monitoring and analytics"""
    total_requests: int = Field(default=0, description="Total requests processed")
    successful_requests: int = Field(default=0, description="Successful requests")
    failed_requests: int = Field(default=0, description="Failed requests")
    average_response_time_ms: float = Field(default=0.0, description="Average response time")
    concurrent_tasks: int = Field(default=0, description="Currently executing tasks")
    last_activity: Optional[datetime] = Field(default=None, description="Last activity timestamp")
    uptime_seconds: int = Field(default=0, description="Agent uptime in seconds")