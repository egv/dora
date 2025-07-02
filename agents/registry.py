"""
Agent Registry for Capability Discovery

This module provides the agent registry system that enables agents to
discover each other and their capabilities through a centralized directory.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from uuid import uuid4

import structlog
from pydantic import BaseModel

from models.a2a import (
    AgentCard,
    AgentStatus,
    Capability,
    CapabilityType,
)


logger = structlog.get_logger(__name__)


class RegistryQuery(BaseModel):
    """Query parameters for agent discovery"""
    capability_name: Optional[str] = None
    capability_type: Optional[CapabilityType] = None
    agent_status: Optional[AgentStatus] = None
    exclude_agents: Set[str] = set()
    include_offline: bool = False
    max_results: int = 10


class RegistryEntry(BaseModel):
    """Registry entry for an agent"""
    agent_card: AgentCard
    registered_at: datetime
    last_heartbeat: datetime
    heartbeat_interval: int
    is_online: bool = True


class AgentRegistryInterface(ABC):
    """Abstract interface for agent registry implementations"""
    
    @abstractmethod
    async def register_agent(self, agent_card: AgentCard) -> bool:
        """Register an agent in the registry"""
        pass
    
    @abstractmethod
    async def unregister_agent(self, agent_id: str) -> bool:
        """Remove an agent from the registry"""
        pass
    
    @abstractmethod
    async def update_agent(self, agent_card: AgentCard) -> bool:
        """Update an agent's information"""
        pass
    
    @abstractmethod
    async def heartbeat(self, agent_id: str) -> bool:
        """Record agent heartbeat"""
        pass
    
    @abstractmethod
    async def discover_agents(self, query: RegistryQuery) -> List[AgentCard]:
        """Discover agents matching the query"""
        pass
    
    @abstractmethod
    async def get_agent(self, agent_id: str) -> Optional[AgentCard]:
        """Get a specific agent's information"""
        pass
    
    @abstractmethod
    async def list_capabilities(self, capability_type: Optional[CapabilityType] = None) -> List[Capability]:
        """List all available capabilities"""
        pass
    
    @abstractmethod
    async def find_agents_with_capability(self, capability_name: str) -> List[AgentCard]:
        """Find all agents that provide a specific capability"""
        pass


class InMemoryAgentRegistry(AgentRegistryInterface):
    """
    In-memory implementation of the agent registry.
    
    This is suitable for development and testing. For production,
    use a distributed registry like Redis or a database-backed implementation.
    """
    
    def __init__(self, cleanup_interval: int = 60):
        """
        Initialize the in-memory registry.
        
        Args:
            cleanup_interval: How often to run cleanup (seconds)
        """
        self._agents: Dict[str, RegistryEntry] = {}
        self._capabilities: Dict[str, Set[str]] = {}  # capability_name -> agent_ids
        self._capability_types: Dict[CapabilityType, Set[str]] = {}  # type -> agent_ids
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        self.logger = structlog.get_logger(__name__).bind(
            registry_type="in_memory"
        )
    
    async def start(self) -> None:
        """Start the registry and cleanup task"""
        if self._running:
            return
            
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.logger.info("Agent registry started")
    
    async def stop(self) -> None:
        """Stop the registry and cleanup task"""
        if not self._running:
            return
            
        self._running = False
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Agent registry stopped")
    
    async def register_agent(self, agent_card: AgentCard) -> bool:
        """Register an agent in the registry"""
        try:
            now = datetime.utcnow()
            
            # Create registry entry
            entry = RegistryEntry(
                agent_card=agent_card,
                registered_at=now,
                last_heartbeat=now,
                heartbeat_interval=agent_card.heartbeat_interval,
                is_online=True
            )
            
            # Store agent
            self._agents[agent_card.agent_id] = entry
            
            # Index capabilities
            await self._index_agent_capabilities(agent_card)
            
            self.logger.info(
                "Agent registered",
                agent_id=agent_card.agent_id,
                agent_name=agent_card.name,
                capabilities_count=len(agent_card.capabilities)
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to register agent",
                agent_id=agent_card.agent_id,
                error=str(e)
            )
            return False
    
    async def unregister_agent(self, agent_id: str) -> bool:
        """Remove an agent from the registry"""
        try:
            if agent_id not in self._agents:
                self.logger.warning("Agent not found for unregistration", agent_id=agent_id)
                return False
            
            entry = self._agents[agent_id]
            
            # Remove from capability indexes
            await self._unindex_agent_capabilities(entry.agent_card)
            
            # Remove agent
            del self._agents[agent_id]
            
            self.logger.info("Agent unregistered", agent_id=agent_id)
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to unregister agent",
                agent_id=agent_id,
                error=str(e)
            )
            return False
    
    async def update_agent(self, agent_card: AgentCard) -> bool:
        """Update an agent's information"""
        try:
            if agent_card.agent_id not in self._agents:
                # If agent doesn't exist, register it
                return await self.register_agent(agent_card)
            
            entry = self._agents[agent_card.agent_id]
            
            # Remove old capability indexes
            await self._unindex_agent_capabilities(entry.agent_card)
            
            # Update entry
            entry.agent_card = agent_card
            entry.last_heartbeat = datetime.utcnow()
            
            # Re-index capabilities
            await self._index_agent_capabilities(agent_card)
            
            self.logger.debug("Agent updated", agent_id=agent_card.agent_id)
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to update agent",
                agent_id=agent_card.agent_id,
                error=str(e)
            )
            return False
    
    async def heartbeat(self, agent_id: str) -> bool:
        """Record agent heartbeat"""
        try:
            if agent_id not in self._agents:
                self.logger.warning("Heartbeat from unknown agent", agent_id=agent_id)
                return False
            
            entry = self._agents[agent_id]
            entry.last_heartbeat = datetime.utcnow()
            entry.is_online = True
            
            # Update agent status if it was offline
            if entry.agent_card.status == AgentStatus.OFFLINE:
                entry.agent_card.status = AgentStatus.READY
            
            self.logger.debug("Heartbeat recorded", agent_id=agent_id)
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to record heartbeat",
                agent_id=agent_id,
                error=str(e)
            )
            return False
    
    async def discover_agents(self, query: RegistryQuery) -> List[AgentCard]:
        """Discover agents matching the query"""
        try:
            matching_agents = []
            
            for agent_id, entry in self._agents.items():
                # Skip excluded agents
                if agent_id in query.exclude_agents:
                    continue
                
                # Check online status
                if not query.include_offline and not entry.is_online:
                    continue
                
                # Check agent status
                if query.agent_status and entry.agent_card.status != query.agent_status:
                    continue
                
                # Check capabilities
                if query.capability_name or query.capability_type:
                    if not self._agent_matches_capability_query(entry.agent_card, query):
                        continue
                
                matching_agents.append(entry.agent_card)
                
                # Limit results
                if len(matching_agents) >= query.max_results:
                    break
            
            self.logger.debug(
                "Agents discovered",
                query_capability=query.capability_name,
                query_type=query.capability_type,
                matches_found=len(matching_agents)
            )
            
            return matching_agents
            
        except Exception as e:
            self.logger.error("Failed to discover agents", error=str(e))
            return []
    
    async def get_agent(self, agent_id: str) -> Optional[AgentCard]:
        """Get a specific agent's information"""
        entry = self._agents.get(agent_id)
        return entry.agent_card if entry else None
    
    async def list_capabilities(self, capability_type: Optional[CapabilityType] = None) -> List[Capability]:
        """List all available capabilities"""
        capabilities = []
        seen_capabilities = set()
        
        for entry in self._agents.values():
            for capability in entry.agent_card.capabilities:
                # Skip duplicates
                if capability.name in seen_capabilities:
                    continue
                
                # Filter by type if specified
                if capability_type and capability.capability_type != capability_type:
                    continue
                
                capabilities.append(capability)
                seen_capabilities.add(capability.name)
        
        return capabilities
    
    async def find_agents_with_capability(self, capability_name: str) -> List[AgentCard]:
        """Find all agents that provide a specific capability"""
        agent_ids = self._capabilities.get(capability_name, set())
        agents = []
        
        for agent_id in agent_ids:
            entry = self._agents.get(agent_id)
            if entry and entry.is_online:
                agents.append(entry.agent_card)
        
        return agents
    
    # Private methods
    
    async def _index_agent_capabilities(self, agent_card: AgentCard) -> None:
        """Add agent to capability indexes"""
        agent_id = agent_card.agent_id
        
        for capability in agent_card.capabilities:
            # Index by capability name
            if capability.name not in self._capabilities:
                self._capabilities[capability.name] = set()
            self._capabilities[capability.name].add(agent_id)
            
            # Index by capability type
            if capability.capability_type not in self._capability_types:
                self._capability_types[capability.capability_type] = set()
            self._capability_types[capability.capability_type].add(agent_id)
    
    async def _unindex_agent_capabilities(self, agent_card: AgentCard) -> None:
        """Remove agent from capability indexes"""
        agent_id = agent_card.agent_id
        
        for capability in agent_card.capabilities:
            # Remove from capability name index
            if capability.name in self._capabilities:
                self._capabilities[capability.name].discard(agent_id)
                if not self._capabilities[capability.name]:
                    del self._capabilities[capability.name]
            
            # Remove from capability type index
            if capability.capability_type in self._capability_types:
                self._capability_types[capability.capability_type].discard(agent_id)
                if not self._capability_types[capability.capability_type]:
                    del self._capability_types[capability.capability_type]
    
    def _agent_matches_capability_query(self, agent_card: AgentCard, query: RegistryQuery) -> bool:
        """Check if agent matches capability query criteria"""
        for capability in agent_card.capabilities:
            # Check capability name
            if query.capability_name and capability.name == query.capability_name:
                return True
            
            # Check capability type
            if query.capability_type and capability.capability_type == query.capability_type:
                return True
        
        return False
    
    async def _cleanup_loop(self) -> None:
        """Background task to clean up stale agents"""
        while self._running:
            try:
                await self._cleanup_stale_agents()
                await asyncio.sleep(self._cleanup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.warning("Cleanup error", error=str(e))
                await asyncio.sleep(5)  # Brief pause before retrying
    
    async def _cleanup_stale_agents(self) -> None:
        """Remove agents that haven't sent heartbeats"""
        now = datetime.utcnow()
        stale_agents = []
        
        for agent_id, entry in self._agents.items():
            # Calculate timeout based on heartbeat interval
            timeout = timedelta(seconds=entry.heartbeat_interval * 3)  # 3x grace period
            
            if now - entry.last_heartbeat > timeout:
                stale_agents.append(agent_id)
                entry.is_online = False
                entry.agent_card.status = AgentStatus.OFFLINE
        
        if stale_agents:
            self.logger.info(
                "Marked agents as offline",
                stale_agent_count=len(stale_agents),
                agent_ids=stale_agents
            )
    
    # Registry statistics and health
    
    async def get_stats(self) -> Dict[str, any]:
        """Get registry statistics"""
        online_agents = sum(1 for entry in self._agents.values() if entry.is_online)
        offline_agents = len(self._agents) - online_agents
        
        return {
            "total_agents": len(self._agents),
            "online_agents": online_agents,
            "offline_agents": offline_agents,
            "total_capabilities": len(self._capabilities),
            "capability_types": len(self._capability_types),
            "running": self._running,
        }


# Global registry instance (can be replaced with distributed implementation)
_default_registry: Optional[InMemoryAgentRegistry] = None


async def get_default_registry() -> InMemoryAgentRegistry:
    """Get the default agent registry instance"""
    global _default_registry
    
    if _default_registry is None:
        _default_registry = InMemoryAgentRegistry()
        await _default_registry.start()
    
    return _default_registry


async def shutdown_default_registry() -> None:
    """Shutdown the default registry"""
    global _default_registry
    
    if _default_registry:
        await _default_registry.stop()
        _default_registry = None