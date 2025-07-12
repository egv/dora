"""
Agent Orchestration Service

Provides workflow orchestration and collaborative task delegation across multiple agents.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Set
from uuid import uuid4
from dataclasses import dataclass, asdict
from enum import Enum
import aiohttp
import structlog

from .discovery_service import get_discovery_service, RegisteredAgent
from .notification_service import get_notification_service


logger = structlog.get_logger(__name__)


class WorkflowStatus(Enum):
    """Workflow execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(Enum):
    """Individual task status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowTask:
    """Represents a task within a workflow"""
    task_id: str
    agent_id: Optional[str]  # Can be None for auto-assignment
    skill_name: str
    parameters: Dict[str, Any]
    dependencies: List[str] = None  # List of task IDs this task depends on
    timeout: int = 300  # Task timeout in seconds
    retry_count: int = 3
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    assigned_agent: Optional[str] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "skill_name": self.skill_name,
            "parameters": self.parameters,
            "dependencies": self.dependencies,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "assigned_agent": self.assigned_agent
        }


@dataclass
class Workflow:
    """Represents a collaborative workflow"""
    workflow_id: str
    name: str
    description: str
    tasks: List[WorkflowTask]
    status: WorkflowStatus = WorkflowStatus.PENDING
    created_at: datetime = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[str] = None
    timeout: int = 3600  # Overall workflow timeout in seconds
    metadata: Dict[str, Any] = None
    results: Dict[str, Any] = None  # Final aggregated results
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}
        if self.results is None:
            self.results = {}
    
    def get_ready_tasks(self) -> List[WorkflowTask]:
        """Get tasks that are ready to execute (dependencies satisfied)"""
        ready_tasks = []
        
        for task in self.tasks:
            if task.status != TaskStatus.PENDING:
                continue
            
            # Check if all dependencies are completed
            dependencies_satisfied = True
            for dep_task_id in task.dependencies:
                dep_task = self.get_task(dep_task_id)
                if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                    dependencies_satisfied = False
                    break
            
            if dependencies_satisfied:
                ready_tasks.append(task)
        
        return ready_tasks
    
    def get_task(self, task_id: str) -> Optional[WorkflowTask]:
        """Get a task by ID"""
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        return None
    
    def is_completed(self) -> bool:
        """Check if workflow is completed"""
        return all(task.status in [TaskStatus.COMPLETED, TaskStatus.SKIPPED] for task in self.tasks)
    
    def has_failed_tasks(self) -> bool:
        """Check if workflow has any failed tasks"""
        return any(task.status == TaskStatus.FAILED for task in self.tasks)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_by": self.created_by,
            "timeout": self.timeout,
            "metadata": self.metadata,
            "results": self.results,
            "tasks": [task.to_dict() for task in self.tasks],
            "task_count": len(self.tasks),
            "completed_tasks": len([t for t in self.tasks if t.status == TaskStatus.COMPLETED]),
            "failed_tasks": len([t for t in self.tasks if t.status == TaskStatus.FAILED])
        }


class OrchestrationService:
    """Orchestrate collaborative workflows across multiple agents"""
    
    def __init__(self, max_concurrent_tasks: int = 10, task_timeout: int = 300):
        """
        Initialize the orchestration service
        
        Args:
            max_concurrent_tasks: Maximum number of tasks to run concurrently
            task_timeout: Default timeout for tasks in seconds
        """
        self.logger = logger.bind(component="orchestration_service")
        self.max_concurrent_tasks = max_concurrent_tasks
        self.default_task_timeout = task_timeout
        
        # Storage
        self.workflows: Dict[str, Workflow] = {}
        self.active_workflows: Set[str] = set()
        
        # Execution control
        self.execution_semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self.executor_tasks: Dict[str, asyncio.Task] = {}  # workflow_id -> execution task
        
        # Services
        self.discovery_service = None
        self.notification_service = None
    
    async def start(self):
        """Start the orchestration service"""
        self.logger.info("Starting Orchestration Service")
        
        # Get service instances
        self.discovery_service = await get_discovery_service()
        self.notification_service = await get_notification_service()
        
        self.logger.info("Orchestration service started")
    
    async def stop(self):
        """Stop the orchestration service and cleanup"""
        self.logger.info("Stopping Orchestration Service")
        
        # Cancel active workflow executions
        for workflow_id, task in self.executor_tasks.items():
            if not task.done():
                self.logger.info("Cancelling workflow execution", workflow_id=workflow_id)
                task.cancel()
        
        # Wait for all executions to finish
        if self.executor_tasks:
            await asyncio.gather(*self.executor_tasks.values(), return_exceptions=True)
        
        self.executor_tasks.clear()
        self.active_workflows.clear()
        
        self.logger.info("Orchestration service stopped")
    
    async def create_workflow(
        self,
        name: str,
        description: str,
        tasks: List[Dict[str, Any]],
        created_by: Optional[str] = None,
        timeout: int = 3600,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new collaborative workflow
        
        Args:
            name: Workflow name
            description: Workflow description
            tasks: List of task definitions
            created_by: ID of the agent/user creating the workflow
            timeout: Overall workflow timeout in seconds
            metadata: Additional workflow metadata
            
        Returns:
            Workflow ID
        """
        try:
            workflow_id = str(uuid4())
            
            # Convert task definitions to WorkflowTask objects
            workflow_tasks = []
            for i, task_def in enumerate(tasks):
                task_id = task_def.get("task_id", f"task_{i}")
                
                workflow_task = WorkflowTask(
                    task_id=task_id,
                    agent_id=task_def.get("agent_id"),
                    skill_name=task_def["skill_name"],
                    parameters=task_def.get("parameters", {}),
                    dependencies=task_def.get("dependencies", []),
                    timeout=task_def.get("timeout", self.default_task_timeout),
                    retry_count=task_def.get("retry_count", 3)
                )
                
                workflow_tasks.append(workflow_task)
            
            # Create workflow
            workflow = Workflow(
                workflow_id=workflow_id,
                name=name,
                description=description,
                tasks=workflow_tasks,
                created_by=created_by,
                timeout=timeout,
                metadata=metadata or {}
            )
            
            # Validate workflow
            validation_errors = await self._validate_workflow(workflow)
            if validation_errors:
                raise ValueError(f"Workflow validation failed: {validation_errors}")
            
            # Store workflow
            self.workflows[workflow_id] = workflow
            
            self.logger.info(
                "Workflow created",
                workflow_id=workflow_id,
                name=name,
                task_count=len(workflow_tasks),
                created_by=created_by
            )
            
            # Publish workflow created event
            await self.notification_service.publish_event(
                event_type="workflow.created",
                data={"workflow_id": workflow_id, "name": name, "task_count": len(workflow_tasks)},
                source_agent="orchestration_service"
            )
            
            return workflow_id
            
        except Exception as e:
            self.logger.error("Failed to create workflow", name=name, error=str(e))
            raise
    
    async def execute_workflow(
        self,
        workflow_id: str,
        input_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a workflow with task delegation
        
        Args:
            workflow_id: ID of the workflow to execute
            input_data: Input data for the workflow
            
        Returns:
            Workflow execution results
        """
        try:
            if workflow_id not in self.workflows:
                raise ValueError(f"Workflow {workflow_id} not found")
            
            workflow = self.workflows[workflow_id]
            
            if workflow.status != WorkflowStatus.PENDING:
                raise ValueError(f"Workflow {workflow_id} is not in pending status")
            
            # Update workflow status
            workflow.status = WorkflowStatus.RUNNING
            workflow.started_at = datetime.utcnow()
            self.active_workflows.add(workflow_id)
            
            # Add input data to workflow metadata
            if input_data:
                workflow.metadata["input_data"] = input_data
            
            self.logger.info(
                "Starting workflow execution",
                workflow_id=workflow_id,
                name=workflow.name,
                task_count=len(workflow.tasks)
            )
            
            # Publish workflow started event
            await self.notification_service.publish_event(
                event_type="workflow.started",
                data={"workflow_id": workflow_id, "name": workflow.name},
                source_agent="orchestration_service"
            )
            
            # Create execution task
            execution_task = asyncio.create_task(self._execute_workflow_tasks(workflow))
            self.executor_tasks[workflow_id] = execution_task
            
            # Wait for completion
            execution_result = await execution_task
            
            # Cleanup
            self.executor_tasks.pop(workflow_id, None)
            self.active_workflows.discard(workflow_id)
            
            return execution_result
            
        except Exception as e:
            self.logger.error("Failed to execute workflow", workflow_id=workflow_id, error=str(e))
            
            # Update workflow status on error
            if workflow_id in self.workflows:
                workflow = self.workflows[workflow_id]
                workflow.status = WorkflowStatus.FAILED
                workflow.completed_at = datetime.utcnow()
                self.active_workflows.discard(workflow_id)
            
            raise
    
    async def delegate_task(
        self,
        task: WorkflowTask,
        target_agent: Optional[str] = None,
        input_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Delegate a task to another agent
        
        Args:
            task: Task to delegate
            target_agent: Specific agent to delegate to (if None, auto-select)
            input_data: Additional input data for the task
            
        Returns:
            Task execution result
        """
        try:
            # Find target agent if not specified
            if not target_agent:
                target_agent = await self._find_suitable_agent(task.skill_name)
                if not target_agent:
                    raise ValueError(f"No suitable agent found for skill: {task.skill_name}")
            
            task.assigned_agent = target_agent
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.utcnow()
            
            self.logger.info(
                "Delegating task to agent",
                task_id=task.task_id,
                skill_name=task.skill_name,
                target_agent=target_agent
            )
            
            # Get agent details
            agent = await self.discovery_service.get_agent(target_agent)
            if not agent:
                raise ValueError(f"Agent {target_agent} not found in registry")
            
            # Prepare task parameters
            task_params = task.parameters.copy()
            if input_data:
                task_params.update(input_data)
            
            # Execute task via A2A protocol
            result = await self._execute_agent_skill(agent, task.skill_name, task_params, task.timeout)
            
            # Update task status
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            task.result = result
            
            self.logger.info(
                "Task completed successfully",
                task_id=task.task_id,
                target_agent=target_agent,
                execution_time=(task.completed_at - task.started_at).total_seconds()
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "Task delegation failed",
                task_id=task.task_id,
                target_agent=target_agent,
                error=str(e)
            )
            
            # Update task status
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.utcnow()
            task.error = str(e)
            
            # Check if we should retry
            if task.retry_count > 0:
                task.retry_count -= 1
                task.status = TaskStatus.PENDING
                self.logger.info(
                    "Task will be retried",
                    task_id=task.task_id,
                    remaining_retries=task.retry_count
                )
            
            raise
    
    async def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """Get a workflow by ID"""
        return self.workflows.get(workflow_id)
    
    async def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """Get detailed status of a workflow"""
        if workflow_id not in self.workflows:
            return {"error": "Workflow not found"}
        
        workflow = self.workflows[workflow_id]
        return workflow.to_dict()
    
    async def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a running workflow"""
        try:
            if workflow_id not in self.workflows:
                return False
            
            workflow = self.workflows[workflow_id]
            
            if workflow.status != WorkflowStatus.RUNNING:
                return False
            
            # Cancel execution task
            if workflow_id in self.executor_tasks:
                execution_task = self.executor_tasks[workflow_id]
                execution_task.cancel()
            
            # Update workflow status
            workflow.status = WorkflowStatus.CANCELLED
            workflow.completed_at = datetime.utcnow()
            self.active_workflows.discard(workflow_id)
            
            self.logger.info("Workflow cancelled", workflow_id=workflow_id)
            
            # Publish workflow cancelled event
            await self.notification_service.publish_event(
                event_type="workflow.cancelled",
                data={"workflow_id": workflow_id, "name": workflow.name},
                source_agent="orchestration_service"
            )
            
            return True
            
        except Exception as e:
            self.logger.error("Failed to cancel workflow", workflow_id=workflow_id, error=str(e))
            return False
    
    async def list_workflows(
        self,
        status_filter: Optional[List[WorkflowStatus]] = None,
        created_by: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List workflows with optional filtering"""
        workflows = []
        
        for workflow in self.workflows.values():
            # Apply status filter
            if status_filter and workflow.status not in status_filter:
                continue
            
            # Apply creator filter
            if created_by and workflow.created_by != created_by:
                continue
            
            workflows.append(workflow.to_dict())
        
        return workflows
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get orchestration service statistics"""
        return {
            "total_workflows": len(self.workflows),
            "active_workflows": len(self.active_workflows),
            "workflow_status_counts": {
                status.value: len([w for w in self.workflows.values() if w.status == status])
                for status in WorkflowStatus
            },
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "current_executions": len(self.executor_tasks)
        }
    
    async def _validate_workflow(self, workflow: Workflow) -> List[str]:
        """Validate workflow definition"""
        errors = []
        
        # Check for duplicate task IDs
        task_ids = [task.task_id for task in workflow.tasks]
        if len(task_ids) != len(set(task_ids)):
            errors.append("Duplicate task IDs found")
        
        # Check dependency references
        for task in workflow.tasks:
            for dep_id in task.dependencies:
                if dep_id not in task_ids:
                    errors.append(f"Task {task.task_id} depends on non-existent task {dep_id}")
        
        # Check for circular dependencies
        if self._has_circular_dependencies(workflow.tasks):
            errors.append("Circular dependencies detected")
        
        # Validate required skills exist
        for task in workflow.tasks:
            if not task.agent_id:  # Will be auto-assigned
                available_agents = await self.discovery_service.find_agents_by_skill(task.skill_name)
                if not available_agents:
                    errors.append(f"No agents available for skill: {task.skill_name}")
        
        return errors
    
    def _has_circular_dependencies(self, tasks: List[WorkflowTask]) -> bool:
        """Check for circular dependencies in tasks"""
        # Build dependency graph
        graph = {task.task_id: task.dependencies for task in tasks}
        
        # Use DFS to detect cycles
        def has_cycle(node, visited, rec_stack):
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor, visited, rec_stack):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        visited = set()
        for task_id in graph:
            if task_id not in visited:
                if has_cycle(task_id, visited, set()):
                    return True
        
        return False
    
    async def _execute_workflow_tasks(self, workflow: Workflow) -> Dict[str, Any]:
        """Execute all tasks in a workflow"""
        try:
            start_time = datetime.utcnow()
            
            while not workflow.is_completed() and not workflow.has_failed_tasks():
                # Check workflow timeout
                if (datetime.utcnow() - start_time).total_seconds() > workflow.timeout:
                    raise asyncio.TimeoutError("Workflow execution timeout")
                
                # Get ready tasks
                ready_tasks = workflow.get_ready_tasks()
                
                if not ready_tasks:
                    # No ready tasks - check if we're stuck
                    pending_tasks = [t for t in workflow.tasks if t.status == TaskStatus.PENDING]
                    if pending_tasks:
                        raise RuntimeError("Workflow is stuck - no ready tasks but pending tasks exist")
                    break
                
                # Execute ready tasks concurrently (with semaphore limit)
                task_coroutines = []
                for task in ready_tasks:
                    coroutine = self._execute_task_with_semaphore(task, workflow)
                    task_coroutines.append(coroutine)
                
                if task_coroutines:
                    await asyncio.gather(*task_coroutines, return_exceptions=True)
                
                # Small delay to prevent busy waiting
                await asyncio.sleep(0.1)
            
            # Determine final workflow status
            if workflow.has_failed_tasks():
                workflow.status = WorkflowStatus.FAILED
            else:
                workflow.status = WorkflowStatus.COMPLETED
            
            workflow.completed_at = datetime.utcnow()
            
            # Aggregate results
            workflow.results = {
                task.task_id: task.result 
                for task in workflow.tasks 
                if task.result is not None
            }
            
            execution_time = (workflow.completed_at - workflow.started_at).total_seconds()
            
            self.logger.info(
                "Workflow execution completed",
                workflow_id=workflow.workflow_id,
                status=workflow.status.value,
                execution_time=execution_time,
                completed_tasks=len([t for t in workflow.tasks if t.status == TaskStatus.COMPLETED]),
                failed_tasks=len([t for t in workflow.tasks if t.status == TaskStatus.FAILED])
            )
            
            # Publish workflow completed event
            await self.notification_service.publish_event(
                event_type=f"workflow.{workflow.status.value}",
                data={
                    "workflow_id": workflow.workflow_id,
                    "name": workflow.name,
                    "execution_time": execution_time,
                    "results": workflow.results
                },
                source_agent="orchestration_service"
            )
            
            return {
                "workflow_id": workflow.workflow_id,
                "status": workflow.status.value,
                "execution_time": execution_time,
                "results": workflow.results,
                "task_summary": {
                    "total": len(workflow.tasks),
                    "completed": len([t for t in workflow.tasks if t.status == TaskStatus.COMPLETED]),
                    "failed": len([t for t in workflow.tasks if t.status == TaskStatus.FAILED])
                }
            }
            
        except Exception as e:
            workflow.status = WorkflowStatus.FAILED
            workflow.completed_at = datetime.utcnow()
            
            self.logger.error(
                "Workflow execution failed",
                workflow_id=workflow.workflow_id,
                error=str(e)
            )
            
            raise
    
    async def _execute_task_with_semaphore(self, task: WorkflowTask, workflow: Workflow):
        """Execute a task with semaphore control"""
        async with self.execution_semaphore:
            try:
                await self.delegate_task(task)
                
                # Publish task completed event
                await self.notification_service.publish_event(
                    event_type="task.completed",
                    data={
                        "workflow_id": workflow.workflow_id,
                        "task_id": task.task_id,
                        "agent_id": task.assigned_agent,
                        "result": task.result
                    },
                    source_agent="orchestration_service"
                )
                
            except Exception as e:
                # Publish task failed event
                await self.notification_service.publish_event(
                    event_type="task.failed",
                    data={
                        "workflow_id": workflow.workflow_id,
                        "task_id": task.task_id,
                        "agent_id": task.assigned_agent,
                        "error": str(e)
                    },
                    source_agent="orchestration_service"
                )
                
                # Re-raise to be handled by workflow executor
                raise
    
    async def _find_suitable_agent(self, skill_name: str) -> Optional[str]:
        """Find a suitable agent for a given skill"""
        try:
            agents = await self.discovery_service.find_agents_by_skill(skill_name)
            
            # Filter for healthy agents
            healthy_agents = []
            for agent in agents:
                health = await self.discovery_service.get_agent_health(agent.agent_id)
                if health.get("is_healthy", False):
                    healthy_agents.append(agent)
            
            if healthy_agents:
                # For now, just return the first healthy agent
                # Could implement load balancing logic here
                return healthy_agents[0].agent_id
            
            return None
            
        except Exception as e:
            self.logger.error("Failed to find suitable agent", skill_name=skill_name, error=str(e))
            return None
    
    async def _execute_agent_skill(
        self,
        agent: RegisteredAgent,
        skill_name: str,
        parameters: Dict[str, Any],
        timeout: int
    ) -> Dict[str, Any]:
        """Execute a skill on a specific agent via A2A protocol"""
        try:
            # Prepare A2A JSON-RPC request
            request_payload = {
                "jsonrpc": "2.0",
                "method": skill_name,
                "params": parameters,
                "id": str(uuid4())
            }
            
            # Make HTTP request to agent
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{agent.endpoint}/execute",
                    json=request_payload,
                    timeout=timeout
                ) as response:
                    if response.status != 200:
                        response_text = await response.text()
                        raise RuntimeError(f"Agent request failed: {response.status} - {response_text}")
                    
                    result = await response.json()
                    
                    # Check for JSON-RPC error
                    if "error" in result:
                        raise RuntimeError(f"Agent skill error: {result['error']}")
                    
                    return result.get("result", {})
        
        except Exception as e:
            self.logger.error(
                "Agent skill execution failed",
                agent_id=agent.agent_id,
                skill_name=skill_name,
                error=str(e)
            )
            raise


# Global orchestration service instance
_orchestration_service: Optional[OrchestrationService] = None


async def get_orchestration_service() -> OrchestrationService:
    """Get the global orchestration service instance"""
    global _orchestration_service
    
    if _orchestration_service is None:
        _orchestration_service = OrchestrationService()
        await _orchestration_service.start()
    
    return _orchestration_service


async def cleanup_orchestration_service():
    """Cleanup the global orchestration service instance"""
    global _orchestration_service
    
    if _orchestration_service is not None:
        await _orchestration_service.stop()
        _orchestration_service = None