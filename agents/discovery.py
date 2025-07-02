"""
Capability Discovery Mixin for Agents

This module provides the discovery capabilities that agents can use
to find and communicate with other agents in the system.
"""

import asyncio
from typing import Dict, List, Optional, Set
from uuid import uuid4

import structlog

from models.a2a import (
    AgentCard,
    AgentStatus,
    A2AMessage,
    A2ARequest,
    A2AResponse,
    Capability,
    CapabilityType,
    MessageType,
)
from agents.registry import (
    AgentRegistryInterface,
    RegistryQuery,
    get_default_registry,
)


logger = structlog.get_logger(__name__)


class CapabilityDiscoveryMixin:
    """
    Mixin class that provides capability discovery functionality for agents.
    
    This mixin can be added to any agent to enable them to:
    - Register themselves with the agent registry
    - Discover other agents and their capabilities
    - Select appropriate agents for task delegation
    - Maintain agent directory and routing information
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Discovery state
        self._registry: Optional[AgentRegistryInterface] = None
        self._discovery_cache: Dict[str, List[AgentCard]] = {}
        self._cache_ttl: int = 300  # 5 minutes
        self._cache_timestamps: Dict[str, float] = {}
        
        # Auto-registration settings
        self._auto_register = True
        self._auto_heartbeat = True
        
        # Discovery logger will be created in _setup_discovery when agent_id is available
        self.discovery_logger = None
    
    async def _setup_discovery(self, registry: Optional[AgentRegistryInterface] = None) -> None:
        """Setup capability discovery system"""
        try:
            # Create discovery logger now that agent_id is available
            if not hasattr(self, 'discovery_logger') or self.discovery_logger is None:
                self.discovery_logger = structlog.get_logger(__name__).bind(
                    agent_id=getattr(self, 'agent_id', 'unknown'),
                    component="discovery"
                )
            
            # Use provided registry or get default
            self._registry = registry or await get_default_registry()
            
            # Register this agent if auto-registration is enabled
            if self._auto_register:
                await self._register_with_registry()
            
            self.discovery_logger.info("Capability discovery setup complete")
            
        except Exception as e:
            if hasattr(self, 'discovery_logger') and self.discovery_logger:
                self.discovery_logger.error("Failed to setup discovery", error=str(e))
            else:
                logger.error("Failed to setup discovery", agent_id=getattr(self, 'agent_id', 'unknown'), error=str(e))
            raise
    
    async def _cleanup_discovery(self) -> None:
        """Cleanup discovery resources"""
        try:
            if self._registry and self._auto_register:
                await self._unregister_from_registry()
            
            self._discovery_cache.clear()
            self._cache_timestamps.clear()
            
            self.discovery_logger.info("Discovery cleanup complete")
            
        except Exception as e:
            self.discovery_logger.warning("Discovery cleanup error", error=str(e))
    
    async def _register_with_registry(self) -> bool:
        """Register this agent with the registry"""
        if not self._registry:
            return False
        
        try:
            agent_card = self.agent_card
            success = await self._registry.register_agent(agent_card)
            
            if success:
                self.discovery_logger.info("Registered with agent registry")
            else:
                self.discovery_logger.warning("Failed to register with registry")
            
            return success
            
        except Exception as e:
            self.discovery_logger.error("Registry registration error", error=str(e))
            return False
    
    async def _unregister_from_registry(self) -> bool:
        """Unregister this agent from the registry"""
        if not self._registry:
            return False
        
        try:
            success = await self._registry.unregister_agent(self.agent_id)
            
            if success:
                self.discovery_logger.info("Unregistered from agent registry")
            else:
                self.discovery_logger.warning("Failed to unregister from registry")
            
            return success
            
        except Exception as e:
            self.discovery_logger.error("Registry unregistration error", error=str(e))
            return False
    
    async def _send_heartbeat_to_registry(self) -> bool:
        """Send heartbeat to registry"""
        if not self._registry or not self._auto_heartbeat:
            return False
        
        try:
            success = await self._registry.heartbeat(self.agent_id)
            
            if success:
                self.discovery_logger.debug("Heartbeat sent to registry")
            else:
                self.discovery_logger.debug("Failed to send heartbeat to registry")
            
            return success
            
        except Exception as e:
            self.discovery_logger.warning("Registry heartbeat error", error=str(e))
            return False
    
    # Public discovery methods
    
    async def discover_agents_with_capability(
        self,
        capability_name: str,
        exclude_self: bool = True,
        max_results: int = 10,
        use_cache: bool = True
    ) -> List[AgentCard]:
        """
        Discover agents that provide a specific capability.
        
        Args:
            capability_name: Name of the capability to search for
            exclude_self: Whether to exclude this agent from results
            max_results: Maximum number of agents to return
            use_cache: Whether to use cached results
            
        Returns:
            List of agent cards that provide the capability
        """
        try:
            cache_key = f"capability:{capability_name}"
            
            # Check cache first
            if use_cache and self._is_cache_valid(cache_key):
                agents = self._discovery_cache[cache_key]
                self.discovery_logger.debug(
                    "Using cached discovery results",
                    capability=capability_name,
                    cached_count=len(agents)
                )
            else:
                # Query registry
                if not self._registry:
                    await self._setup_discovery()
                
                query = RegistryQuery(
                    capability_name=capability_name,
                    agent_status=AgentStatus.READY,
                    exclude_agents={self.agent_id} if exclude_self else set(),
                    include_offline=False,
                    max_results=max_results
                )
                
                agents = await self._registry.discover_agents(query)
                
                # Cache results
                if use_cache:
                    self._update_cache(cache_key, agents)
                
                self.discovery_logger.info(
                    "Discovered agents with capability",
                    capability=capability_name,
                    agents_found=len(agents)
                )
            
            return agents
            
        except Exception as e:
            self.discovery_logger.error(
                "Failed to discover agents with capability",
                capability=capability_name,
                error=str(e)
            )
            return []
    
    async def discover_agents_by_type(
        self,
        capability_type: CapabilityType,
        exclude_self: bool = True,
        max_results: int = 10,
        use_cache: bool = True
    ) -> List[AgentCard]:
        """
        Discover agents that provide capabilities of a specific type.
        
        Args:
            capability_type: Type of capability to search for
            exclude_self: Whether to exclude this agent from results
            max_results: Maximum number of agents to return
            use_cache: Whether to use cached results
            
        Returns:
            List of agent cards that provide capabilities of the specified type
        """
        try:
            cache_key = f"type:{capability_type.value}"
            
            # Check cache first
            if use_cache and self._is_cache_valid(cache_key):
                agents = self._discovery_cache[cache_key]
                self.discovery_logger.debug(
                    "Using cached discovery results",
                    capability_type=capability_type,
                    cached_count=len(agents)
                )
            else:
                # Query registry
                if not self._registry:
                    await self._setup_discovery()
                
                query = RegistryQuery(
                    capability_type=capability_type,
                    agent_status=AgentStatus.READY,
                    exclude_agents={self.agent_id} if exclude_self else set(),
                    include_offline=False,
                    max_results=max_results
                )
                
                agents = await self._registry.discover_agents(query)
                
                # Cache results
                if use_cache:
                    self._update_cache(cache_key, agents)
                
                self.discovery_logger.info(
                    "Discovered agents by type",
                    capability_type=capability_type,
                    agents_found=len(agents)
                )
            
            return agents
            
        except Exception as e:
            self.discovery_logger.error(
                "Failed to discover agents by type",
                capability_type=capability_type,
                error=str(e)
            )
            return []
    
    async def get_agent_info(self, agent_id: str, use_cache: bool = True) -> Optional[AgentCard]:
        """
        Get information about a specific agent.
        
        Args:
            agent_id: ID of the agent to look up
            use_cache: Whether to use cached results
            
        Returns:
            Agent card if found, None otherwise
        """
        try:
            cache_key = f"agent:{agent_id}"
            
            # Check cache first
            if use_cache and self._is_cache_valid(cache_key):
                cached_agents = self._discovery_cache[cache_key]
                if cached_agents:
                    return cached_agents[0]
            
            # Query registry
            if not self._registry:
                await self._setup_discovery()
            
            agent_card = await self._registry.get_agent(agent_id)
            
            # Cache result
            if use_cache and agent_card:
                self._update_cache(cache_key, [agent_card])
            
            return agent_card
            
        except Exception as e:
            self.discovery_logger.error(
                "Failed to get agent info",
                target_agent_id=agent_id,
                error=str(e)
            )
            return None
    
    async def list_all_capabilities(
        self,
        capability_type: Optional[CapabilityType] = None,
        use_cache: bool = True
    ) -> List[Capability]:
        """
        List all capabilities available in the system.
        
        Args:
            capability_type: Optional filter by capability type
            use_cache: Whether to use cached results
            
        Returns:
            List of all available capabilities
        """
        try:
            cache_key = f"capabilities:{capability_type.value if capability_type else 'all'}"
            
            # Check cache first
            if use_cache and self._is_cache_valid(cache_key):
                # For capabilities, we store them differently in cache
                if cache_key in self._discovery_cache:
                    return self._discovery_cache[cache_key]
            
            # Query registry
            if not self._registry:
                await self._setup_discovery()
            
            capabilities = await self._registry.list_capabilities(capability_type)
            
            # Cache results
            if use_cache:
                self._discovery_cache[cache_key] = capabilities
                self._cache_timestamps[cache_key] = asyncio.get_event_loop().time()
            
            self.discovery_logger.info(
                "Listed capabilities",
                capability_type=capability_type,
                capabilities_found=len(capabilities)
            )
            
            return capabilities
            
        except Exception as e:
            self.discovery_logger.error(
                "Failed to list capabilities",
                capability_type=capability_type,
                error=str(e)
            )
            return []
    
    async def select_best_agent_for_capability(
        self,
        capability_name: str,
        selection_criteria: Optional[Dict[str, any]] = None
    ) -> Optional[AgentCard]:
        """
        Select the best agent for a specific capability based on criteria.
        
        Args:
            capability_name: Name of the capability needed
            selection_criteria: Optional criteria for selection (e.g., load, performance)
            
        Returns:
            Best agent card for the capability, or None if none found
        """
        try:
            # Discover all agents with the capability
            agents = await self.discover_agents_with_capability(capability_name)
            
            if not agents:
                return None
            
            # If no criteria specified, return first available agent
            if not selection_criteria:
                return agents[0]
            
            # Apply selection criteria
            best_agent = None
            best_score = float('-inf')
            
            for agent in agents:
                score = await self._calculate_agent_score(agent, selection_criteria)
                if score > best_score:
                    best_score = score
                    best_agent = agent
            
            self.discovery_logger.info(
                "Selected best agent for capability",
                capability=capability_name,
                selected_agent=best_agent.agent_id if best_agent else None,
                candidates_evaluated=len(agents)
            )
            
            return best_agent
            
        except Exception as e:
            self.discovery_logger.error(
                "Failed to select best agent",
                capability=capability_name,
                error=str(e)
            )
            return None
    
    async def update_registry_info(self) -> bool:
        """Update this agent's information in the registry"""
        if not self._registry:
            return False
        
        try:
            agent_card = self.agent_card
            success = await self._registry.update_agent(agent_card)
            
            if success:
                self.discovery_logger.debug("Updated registry information")
            
            return success
            
        except Exception as e:
            self.discovery_logger.error("Failed to update registry info", error=str(e))
            return False
    
    # Cache management
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid"""
        if cache_key not in self._cache_timestamps:
            return False
        
        current_time = asyncio.get_event_loop().time()
        cache_time = self._cache_timestamps[cache_key]
        
        return (current_time - cache_time) < self._cache_ttl
    
    def _update_cache(self, cache_key: str, agents: List[AgentCard]) -> None:
        """Update cache with new agent data"""
        self._discovery_cache[cache_key] = agents.copy()
        self._cache_timestamps[cache_key] = asyncio.get_event_loop().time()
    
    def clear_discovery_cache(self) -> None:
        """Clear all cached discovery data"""
        self._discovery_cache.clear()
        self._cache_timestamps.clear()
        self.discovery_logger.debug("Discovery cache cleared")
    
    # Agent selection scoring
    
    async def _calculate_agent_score(
        self,
        agent: AgentCard,
        criteria: Dict[str, any]
    ) -> float:
        """
        Calculate selection score for an agent based on criteria.
        
        This is a basic implementation that can be extended with more
        sophisticated selection algorithms.
        """
        score = 0.0
        
        # Prefer agents with READY status
        if agent.status == AgentStatus.READY:
            score += 10.0
        elif agent.status == AgentStatus.BUSY:
            score += 5.0
        
        # Consider agent metrics if available
        if "metrics" in agent.metadata:
            metrics = agent.metadata["metrics"]
            
            # Prefer agents with lower average response time
            if "average_response_time_ms" in metrics:
                response_time = metrics["average_response_time_ms"]
                if response_time > 0:
                    score += max(0, 10.0 - (response_time / 100.0))
            
            # Prefer agents with fewer concurrent tasks
            if "concurrent_tasks" in metrics:
                concurrent_tasks = metrics["concurrent_tasks"]
                score += max(0, 5.0 - concurrent_tasks)
            
            # Prefer agents with higher success rate
            if "successful_requests" in metrics and "total_requests" in metrics:
                total = metrics["total_requests"]
                successful = metrics["successful_requests"]
                if total > 0:
                    success_rate = successful / total
                    score += success_rate * 15.0
        
        # Apply custom criteria
        for criterion, value in criteria.items():
            if criterion == "prefer_agent_id" and agent.agent_id == value:
                score += 20.0
            elif criterion == "avoid_agent_id" and agent.agent_id == value:
                score -= 50.0
            elif criterion == "max_concurrent_tasks":
                concurrent = agent.metadata.get("metrics", {}).get("concurrent_tasks", 0)
                if concurrent <= value:
                    score += 5.0
                else:
                    score -= 10.0
        
        return score