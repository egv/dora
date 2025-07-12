"""
Agent Discovery Service

Provides centralized agent discovery and capability management for A2A collaboration.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4
import aiohttp
import structlog
from dataclasses import dataclass, asdict

from a2a.types import AgentCard, AgentSkill


logger = structlog.get_logger(__name__)


@dataclass
class RegisteredAgent:
    """Represents a registered agent with discovery metadata"""
    agent_id: str
    name: str
    endpoint: str
    agent_card: AgentCard
    capabilities: List[str]  # List of skill IDs
    last_heartbeat: datetime
    status: str = "active"  # active, inactive, unhealthy
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "endpoint": self.endpoint,
            "capabilities": self.capabilities,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "status": self.status,
            "metadata": self.metadata
        }


class AgentDiscoveryService:
    """Central registry for agent discovery and capability management"""
    
    def __init__(self, heartbeat_timeout: int = 300):
        """
        Initialize the discovery service
        
        Args:
            heartbeat_timeout: Seconds after which an agent is considered unhealthy
        """
        self.logger = logger.bind(component="agent_discovery_service")
        self.heartbeat_timeout = heartbeat_timeout
        
        # In-memory registry (could be backed by database in production)
        self.agents: Dict[str, RegisteredAgent] = {}
        self.capability_index: Dict[str, Set[str]] = {}  # capability -> set of agent_ids
        
        # Health monitoring
        self._health_check_task = None
        self._health_check_interval = 60  # Check every minute
        
        # Known agent configurations (for auto-discovery)
        self.known_agents = [
            {
                "name": "EventSearchAgent",
                "endpoint": "http://localhost:8001",
                "expected_capabilities": ["search_events"]
            },
            {
                "name": "CalendarIntelligenceAgent", 
                "endpoint": "http://localhost:8002",
                "expected_capabilities": ["get_calendar_data", "get_marketing_insights", "analyze_opportunity"]
            },
            {
                "name": "EventManagerAgent",
                "endpoint": "http://localhost:8003", 
                "expected_capabilities": ["create_event", "get_event", "update_event", "delete_event", "list_events"]
            }
        ]
    
    async def start(self):
        """Start the discovery service and background tasks"""
        self.logger.info("Starting Agent Discovery Service")
        
        # Start health checking task
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        # Auto-discover known agents
        await self._auto_discover_agents()
    
    async def stop(self):
        """Stop the discovery service and cleanup tasks"""
        self.logger.info("Stopping Agent Discovery Service")
        
        if self._health_check_task:
            try:
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    self.logger.debug("Event loop closed during cleanup")
                else:
                    raise
    
    async def register_agent(
        self, 
        agent_card: AgentCard, 
        endpoint: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Register an agent with the discovery service
        
        Args:
            agent_card: Agent's capability card
            endpoint: Agent's HTTP endpoint
            metadata: Additional metadata about the agent
            
        Returns:
            True if registration successful, False otherwise
        """
        try:
            agent_id = agent_card.name.lower().replace(" ", "_")
            capabilities = [skill.id for skill in agent_card.skills]
            
            registered_agent = RegisteredAgent(
                agent_id=agent_id,
                name=agent_card.name,
                endpoint=endpoint,
                agent_card=agent_card,
                capabilities=capabilities,
                last_heartbeat=datetime.utcnow(),
                status="active",
                metadata=metadata or {}
            )
            
            # Register agent
            self.agents[agent_id] = registered_agent
            
            # Update capability index
            for capability in capabilities:
                if capability not in self.capability_index:
                    self.capability_index[capability] = set()
                self.capability_index[capability].add(agent_id)
            
            self.logger.info(
                "Agent registered successfully",
                agent_id=agent_id,
                name=agent_card.name,
                endpoint=endpoint,
                capabilities=capabilities
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to register agent",
                agent_name=agent_card.name if agent_card else "unknown",
                endpoint=endpoint,
                error=str(e)
            )
            return False
    
    async def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent from the discovery service
        
        Args:
            agent_id: ID of the agent to unregister
            
        Returns:
            True if unregistration successful, False otherwise
        """
        try:
            if agent_id not in self.agents:
                self.logger.warning("Agent not found for unregistration", agent_id=agent_id)
                return False
            
            agent = self.agents[agent_id]
            
            # Remove from capability index
            for capability in agent.capabilities:
                if capability in self.capability_index:
                    self.capability_index[capability].discard(agent_id)
                    if not self.capability_index[capability]:
                        del self.capability_index[capability]
            
            # Remove agent
            del self.agents[agent_id]
            
            self.logger.info("Agent unregistered successfully", agent_id=agent_id)
            return True
            
        except Exception as e:
            self.logger.error("Failed to unregister agent", agent_id=agent_id, error=str(e))
            return False
    
    async def discover_agents(
        self, 
        capability_filter: Optional[List[str]] = None,
        status_filter: Optional[List[str]] = None
    ) -> List[RegisteredAgent]:
        """
        Discover available agents with optional filtering
        
        Args:
            capability_filter: Filter by required capabilities
            status_filter: Filter by agent status (default: ["active"])
            
        Returns:
            List of matching registered agents
        """
        try:
            status_filter = status_filter or ["active"]
            
            # Start with all agents
            candidates = list(self.agents.values())
            
            # Filter by status
            candidates = [agent for agent in candidates if agent.status in status_filter]
            
            # Filter by capabilities
            if capability_filter:
                filtered_candidates = []
                for agent in candidates:
                    # Agent must have all required capabilities
                    if all(cap in agent.capabilities for cap in capability_filter):
                        filtered_candidates.append(agent)
                candidates = filtered_candidates
            
            self.logger.info(
                "Agent discovery completed",
                total_agents=len(self.agents),
                matching_agents=len(candidates),
                capability_filter=capability_filter,
                status_filter=status_filter
            )
            
            return candidates
            
        except Exception as e:
            self.logger.error(
                "Failed to discover agents",
                capability_filter=capability_filter,
                status_filter=status_filter,
                error=str(e)
            )
            return []
    
    async def find_agents_by_skill(self, skill_name: str) -> List[RegisteredAgent]:
        """
        Find agents that provide a specific skill
        
        Args:
            skill_name: Name of the skill to search for
            
        Returns:
            List of agents that provide the skill
        """
        try:
            if skill_name not in self.capability_index:
                self.logger.debug("No agents found for skill", skill_name=skill_name)
                return []
            
            agent_ids = self.capability_index[skill_name]
            agents = [
                self.agents[agent_id] 
                for agent_id in agent_ids 
                if agent_id in self.agents and self.agents[agent_id].status == "active"
            ]
            
            self.logger.info(
                "Found agents for skill",
                skill_name=skill_name,
                agent_count=len(agents),
                agent_ids=[agent.agent_id for agent in agents]
            )
            
            return agents
            
        except Exception as e:
            self.logger.error("Failed to find agents by skill", skill_name=skill_name, error=str(e))
            return []
    
    async def get_agent(self, agent_id: str) -> Optional[RegisteredAgent]:
        """
        Get a specific agent by ID
        
        Args:
            agent_id: ID of the agent
            
        Returns:
            RegisteredAgent if found, None otherwise
        """
        return self.agents.get(agent_id)
    
    async def get_agent_health(self, agent_id: str) -> Dict[str, Any]:
        """
        Check health status of a specific agent
        
        Args:
            agent_id: ID of the agent to check
            
        Returns:
            Health status information
        """
        try:
            if agent_id not in self.agents:
                return {
                    "agent_id": agent_id,
                    "status": "not_found",
                    "error": "Agent not registered"
                }
            
            agent = self.agents[agent_id]
            
            # Check if agent is responsive
            is_healthy = await self._check_agent_health(agent)
            
            # Update agent status
            if is_healthy:
                agent.status = "active"
                agent.last_heartbeat = datetime.utcnow()
            else:
                agent.status = "unhealthy"
            
            health_info = {
                "agent_id": agent_id,
                "name": agent.name,
                "endpoint": agent.endpoint,
                "status": agent.status,
                "last_heartbeat": agent.last_heartbeat.isoformat(),
                "capabilities": agent.capabilities,
                "is_healthy": is_healthy
            }
            
            self.logger.debug("Agent health check completed", **health_info)
            
            return health_info
            
        except Exception as e:
            self.logger.error("Failed to check agent health", agent_id=agent_id, error=str(e))
            return {
                "agent_id": agent_id,
                "status": "error",
                "error": str(e)
            }
    
    async def update_agent_heartbeat(self, agent_id: str) -> bool:
        """
        Update the heartbeat timestamp for an agent
        
        Args:
            agent_id: ID of the agent
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            if agent_id not in self.agents:
                self.logger.warning("Agent not found for heartbeat update", agent_id=agent_id)
                return False
            
            self.agents[agent_id].last_heartbeat = datetime.utcnow()
            self.agents[agent_id].status = "active"
            
            self.logger.debug("Agent heartbeat updated", agent_id=agent_id)
            return True
            
        except Exception as e:
            self.logger.error("Failed to update agent heartbeat", agent_id=agent_id, error=str(e))
            return False
    
    async def get_capabilities_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all available capabilities
        
        Returns:
            Summary of capabilities and agent counts
        """
        try:
            summary = {
                "total_agents": len(self.agents),
                "active_agents": len([a for a in self.agents.values() if a.status == "active"]),
                "capabilities": {},
                "agent_status_counts": {}
            }
            
            # Count agents by status
            for agent in self.agents.values():
                status = agent.status
                summary["agent_status_counts"][status] = summary["agent_status_counts"].get(status, 0) + 1
            
            # Count capabilities
            for capability, agent_ids in self.capability_index.items():
                active_agents = [
                    agent_id for agent_id in agent_ids 
                    if agent_id in self.agents and self.agents[agent_id].status == "active"
                ]
                summary["capabilities"][capability] = {
                    "total_agents": len(agent_ids),
                    "active_agents": len(active_agents),
                    "agent_ids": list(active_agents)
                }
            
            return summary
            
        except Exception as e:
            self.logger.error("Failed to get capabilities summary", error=str(e))
            return {"error": str(e)}
    
    async def _auto_discover_agents(self):
        """Automatically discover and register known agents"""
        self.logger.info("Starting auto-discovery of known agents")
        
        for agent_config in self.known_agents:
            try:
                await self._discover_agent(agent_config)
            except Exception as e:
                self.logger.warning(
                    "Failed to auto-discover agent",
                    agent_name=agent_config["name"],
                    endpoint=agent_config["endpoint"],
                    error=str(e)
                )
    
    async def _discover_agent(self, agent_config: Dict[str, Any]):
        """Discover and register a specific agent"""
        try:
            endpoint = agent_config["endpoint"]
            
            # Try to get agent card from the agent
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{endpoint}/agent-card", timeout=5) as response:
                    if response.status == 200:
                        card_data = await response.json()
                        
                        # Convert to AgentCard (basic conversion, may need refinement)
                        agent_card = AgentCard(
                            name=card_data.get("name", agent_config["name"]),
                            description=card_data.get("description", ""),
                            url=endpoint,
                            skills=[],  # Will be populated from actual card
                            defaultOutputModes=card_data.get("defaultOutputModes", ["application/json"])
                        )
                        
                        # Register the agent
                        await self.register_agent(agent_card, endpoint)
                        
                        self.logger.info(
                            "Auto-discovered agent successfully",
                            agent_name=agent_config["name"],
                            endpoint=endpoint
                        )
                    else:
                        self.logger.warning(
                            "Agent endpoint not responsive for auto-discovery",
                            agent_name=agent_config["name"],
                            endpoint=endpoint,
                            status_code=response.status
                        )
        
        except Exception as e:
            self.logger.debug(
                "Could not auto-discover agent (may not be running)",
                agent_name=agent_config["name"],
                endpoint=endpoint,
                error=str(e)
            )
    
    async def _health_check_loop(self):
        """Background task to check agent health periodically"""
        self.logger.info("Starting agent health check loop")
        
        try:
            while True:
                await asyncio.sleep(self._health_check_interval)
                await self._check_all_agents_health()
        
        except asyncio.CancelledError:
            self.logger.info("Health check loop cancelled")
            raise
        except Exception as e:
            self.logger.error("Health check loop error", error=str(e))
    
    async def _check_all_agents_health(self):
        """Check health of all registered agents"""
        if not self.agents:
            return
        
        self.logger.debug("Checking health of all registered agents", agent_count=len(self.agents))
        
        # Check each agent concurrently
        health_tasks = []
        for agent_id in list(self.agents.keys()):
            task = asyncio.create_task(self._update_agent_health(agent_id))
            health_tasks.append(task)
        
        if health_tasks:
            await asyncio.gather(*health_tasks, return_exceptions=True)
    
    async def _update_agent_health(self, agent_id: str):
        """Update health status for a specific agent"""
        try:
            if agent_id not in self.agents:
                return
                
            agent = self.agents[agent_id]
            
            # Check if heartbeat is too old
            time_since_heartbeat = datetime.utcnow() - agent.last_heartbeat
            
            if time_since_heartbeat.total_seconds() > self.heartbeat_timeout:
                # Try to ping the agent
                is_healthy = await self._check_agent_health(agent)
                
                if is_healthy:
                    agent.status = "active"
                    agent.last_heartbeat = datetime.utcnow()
                else:
                    agent.status = "unhealthy"
                    self.logger.warning(
                        "Agent marked as unhealthy",
                        agent_id=agent_id,
                        time_since_heartbeat=time_since_heartbeat.total_seconds()
                    )
            
        except Exception as e:
            self.logger.error("Failed to update agent health", agent_id=agent_id, error=str(e))
    
    async def _check_agent_health(self, agent: RegisteredAgent) -> bool:
        """Check if an agent is healthy by pinging its health endpoint"""
        try:
            async with aiohttp.ClientSession() as session:
                # Try health endpoint first
                health_url = f"{agent.endpoint}/health"
                async with session.get(health_url, timeout=5) as response:
                    if response.status == 200:
                        return True
                
                # Fallback to agent-card endpoint
                card_url = f"{agent.endpoint}/agent-card"
                async with session.get(card_url, timeout=5) as response:
                    return response.status == 200
                        
        except Exception as e:
            self.logger.debug(
                "Agent health check failed",
                agent_id=agent.agent_id,
                endpoint=agent.endpoint,
                error=str(e)
            )
            return False


# Global discovery service instance
_discovery_service: Optional[AgentDiscoveryService] = None


async def get_discovery_service() -> AgentDiscoveryService:
    """Get the global discovery service instance"""
    global _discovery_service
    
    if _discovery_service is None:
        _discovery_service = AgentDiscoveryService()
        await _discovery_service.start()
    
    return _discovery_service


async def cleanup_discovery_service():
    """Cleanup the global discovery service instance"""
    global _discovery_service
    
    if _discovery_service is not None:
        await _discovery_service.stop()
        _discovery_service = None