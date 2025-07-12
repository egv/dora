"""
Agent Notification Service

Provides pub/sub notification system for real-time inter-agent communication.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Callable
from uuid import uuid4
from dataclasses import dataclass, asdict
from collections import defaultdict
import aiohttp
import structlog


logger = structlog.get_logger(__name__)


@dataclass
class NotificationEvent:
    """Represents a notification event"""
    event_id: str
    event_type: str
    source_agent: str
    timestamp: datetime
    data: Dict[str, Any]
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source_agent": self.source_agent,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "metadata": self.metadata
        }


@dataclass
class Subscription:
    """Represents an agent's subscription to events"""
    subscription_id: str
    agent_id: str
    event_types: List[str]
    webhook_url: Optional[str] = None
    filters: Dict[str, Any] = None
    active: bool = True
    created_at: datetime = None
    last_delivery: Optional[datetime] = None
    delivery_count: int = 0
    
    def __post_init__(self):
        if self.filters is None:
            self.filters = {}
        if self.created_at is None:
            self.created_at = datetime.utcnow()
    
    def matches_event(self, event: NotificationEvent) -> bool:
        """Check if this subscription matches the given event"""
        # Check event type
        if event.event_type not in self.event_types and "*" not in self.event_types:
            return False
        
        # Check filters
        for filter_key, filter_value in self.filters.items():
            if filter_key in event.data:
                if event.data[filter_key] != filter_value:
                    return False
            elif filter_key in event.metadata:
                if event.metadata[filter_key] != filter_value:
                    return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "subscription_id": self.subscription_id,
            "agent_id": self.agent_id,
            "event_types": self.event_types,
            "webhook_url": self.webhook_url,
            "filters": self.filters,
            "active": self.active,
            "created_at": self.created_at.isoformat(),
            "last_delivery": self.last_delivery.isoformat() if self.last_delivery else None,
            "delivery_count": self.delivery_count
        }


class NotificationService:
    """Pub/Sub notification system for inter-agent communication"""
    
    def __init__(self, max_event_history: int = 1000, delivery_timeout: int = 30):
        """
        Initialize the notification service
        
        Args:
            max_event_history: Maximum number of events to keep in history
            delivery_timeout: Timeout for webhook deliveries in seconds
        """
        self.logger = logger.bind(component="notification_service")
        self.max_event_history = max_event_history
        self.delivery_timeout = delivery_timeout
        
        # Storage
        self.subscriptions: Dict[str, Subscription] = {}  # subscription_id -> Subscription
        self.agent_subscriptions: Dict[str, Set[str]] = defaultdict(set)  # agent_id -> set of subscription_ids
        self.event_history: List[NotificationEvent] = []
        
        # Event type indexing for faster lookups
        self.event_type_index: Dict[str, Set[str]] = defaultdict(set)  # event_type -> set of subscription_ids
        
        # Delivery queue and workers
        self.delivery_queue: asyncio.Queue = asyncio.Queue()
        self.delivery_workers: List[asyncio.Task] = []
        self.worker_count = 3
        
        # Callbacks for in-process subscriptions
        self.callback_subscriptions: Dict[str, Callable] = {}
    
    async def start(self):
        """Start the notification service and delivery workers"""
        self.logger.info("Starting Notification Service")
        
        # Start delivery workers
        for i in range(self.worker_count):
            worker = asyncio.create_task(self._delivery_worker(f"worker-{i}"))
            self.delivery_workers.append(worker)
        
        self.logger.info("Notification service started", worker_count=self.worker_count)
    
    async def stop(self):
        """Stop the notification service and cleanup workers"""
        self.logger.info("Stopping Notification Service")
        
        # Cancel delivery workers
        for worker in self.delivery_workers:
            try:
                worker.cancel()
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    self.logger.debug("Event loop closed during cleanup")
                else:
                    raise
        
        # Wait for workers to finish
        if self.delivery_workers:
            try:
                await asyncio.gather(*self.delivery_workers, return_exceptions=True)
            except RuntimeError as e:
                if "got Future" in str(e) and "attached to a different loop" in str(e):
                    self.logger.debug("Workers attached to different event loop during cleanup")
                else:
                    raise
        
        self.delivery_workers.clear()
        self.logger.info("Notification service stopped")
    
    async def subscribe(
        self,
        agent_id: str,
        event_types: List[str],
        webhook_url: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        callback: Optional[Callable] = None
    ) -> str:
        """
        Subscribe to specific event types
        
        Args:
            agent_id: ID of the subscribing agent
            event_types: List of event types to subscribe to (use "*" for all)
            webhook_url: Optional webhook URL for HTTP delivery
            filters: Optional filters to apply to events
            callback: Optional callback function for in-process delivery
            
        Returns:
            Subscription ID
        """
        try:
            subscription_id = str(uuid4())
            
            subscription = Subscription(
                subscription_id=subscription_id,
                agent_id=agent_id,
                event_types=event_types,
                webhook_url=webhook_url,
                filters=filters or {}
            )
            
            # Store subscription
            self.subscriptions[subscription_id] = subscription
            self.agent_subscriptions[agent_id].add(subscription_id)
            
            # Update event type index
            for event_type in event_types:
                self.event_type_index[event_type].add(subscription_id)
            
            # Store callback if provided
            if callback:
                self.callback_subscriptions[subscription_id] = callback
            
            self.logger.info(
                "Agent subscribed to events",
                subscription_id=subscription_id,
                agent_id=agent_id,
                event_types=event_types,
                webhook_url=webhook_url,
                has_callback=callback is not None,
                filter_count=len(filters or {})
            )
            
            return subscription_id
            
        except Exception as e:
            self.logger.error(
                "Failed to create subscription",
                agent_id=agent_id,
                event_types=event_types,
                error=str(e)
            )
            raise
    
    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from events
        
        Args:
            subscription_id: ID of the subscription to remove
            
        Returns:
            True if unsubscription successful, False otherwise
        """
        try:
            if subscription_id not in self.subscriptions:
                self.logger.warning("Subscription not found", subscription_id=subscription_id)
                return False
            
            subscription = self.subscriptions[subscription_id]
            
            # Remove from agent subscriptions
            self.agent_subscriptions[subscription.agent_id].discard(subscription_id)
            if not self.agent_subscriptions[subscription.agent_id]:
                del self.agent_subscriptions[subscription.agent_id]
            
            # Remove from event type index
            for event_type in subscription.event_types:
                self.event_type_index[event_type].discard(subscription_id)
                if not self.event_type_index[event_type]:
                    del self.event_type_index[event_type]
            
            # Remove callback if exists
            self.callback_subscriptions.pop(subscription_id, None)
            
            # Remove subscription
            del self.subscriptions[subscription_id]
            
            self.logger.info(
                "Agent unsubscribed from events",
                subscription_id=subscription_id,
                agent_id=subscription.agent_id
            )
            
            return True
            
        except Exception as e:
            self.logger.error("Failed to unsubscribe", subscription_id=subscription_id, error=str(e))
            return False
    
    async def publish_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        source_agent: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Publish an event to all subscribers
        
        Args:
            event_type: Type of the event
            data: Event data
            source_agent: ID of the agent publishing the event
            metadata: Optional event metadata
            
        Returns:
            Event ID
        """
        try:
            event_id = str(uuid4())
            
            event = NotificationEvent(
                event_id=event_id,
                event_type=event_type,
                source_agent=source_agent,
                timestamp=datetime.utcnow(),
                data=data,
                metadata=metadata or {}
            )
            
            # Add to event history
            self.event_history.append(event)
            
            # Trim history if needed
            if len(self.event_history) > self.max_event_history:
                self.event_history = self.event_history[-self.max_event_history:]
            
            # Find matching subscriptions
            matching_subscriptions = self._find_matching_subscriptions(event)
            
            # Queue deliveries
            for subscription in matching_subscriptions:
                await self.delivery_queue.put((event, subscription))
            
            self.logger.info(
                "Event published",
                event_id=event_id,
                event_type=event_type,
                source_agent=source_agent,
                subscriber_count=len(matching_subscriptions)
            )
            
            return event_id
            
        except Exception as e:
            self.logger.error(
                "Failed to publish event",
                event_type=event_type,
                source_agent=source_agent,
                error=str(e)
            )
            raise
    
    async def notify_agent(
        self,
        agent_id: str,
        message: Dict[str, Any],
        source_agent: str,
        message_type: str = "direct_message"
    ) -> bool:
        """
        Send direct notification to a specific agent
        
        Args:
            agent_id: ID of the target agent
            message: Message data
            source_agent: ID of the source agent
            message_type: Type of the message
            
        Returns:
            True if notification sent successfully, False otherwise
        """
        try:
            # Create a direct message event
            event_type = f"direct_message.{agent_id}"
            
            await self.publish_event(
                event_type=event_type,
                data={
                    "target_agent": agent_id,
                    "message_type": message_type,
                    "message": message
                },
                source_agent=source_agent,
                metadata={
                    "delivery_type": "direct",
                    "target_agent": agent_id
                }
            )
            
            self.logger.info(
                "Direct message sent",
                target_agent=agent_id,
                source_agent=source_agent,
                message_type=message_type
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to send direct notification",
                target_agent=agent_id,
                source_agent=source_agent,
                error=str(e)
            )
            return False
    
    async def get_subscriptions(self, agent_id: Optional[str] = None) -> List[Subscription]:
        """
        Get subscriptions, optionally filtered by agent
        
        Args:
            agent_id: Optional agent ID to filter by
            
        Returns:
            List of subscriptions
        """
        if agent_id:
            subscription_ids = self.agent_subscriptions.get(agent_id, set())
            return [self.subscriptions[sub_id] for sub_id in subscription_ids if sub_id in self.subscriptions]
        else:
            return list(self.subscriptions.values())
    
    async def get_event_history(
        self,
        event_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[NotificationEvent]:
        """
        Get event history with optional filtering
        
        Args:
            event_type: Optional event type filter
            since: Optional timestamp filter
            limit: Maximum number of events to return
            
        Returns:
            List of events
        """
        events = self.event_history.copy()
        
        # Filter by event type
        if event_type:
            events = [event for event in events if event.event_type == event_type]
        
        # Filter by timestamp
        if since:
            events = [event for event in events if event.timestamp >= since]
        
        # Apply limit
        events = events[-limit:] if len(events) > limit else events
        
        return events
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get notification service statistics
        
        Returns:
            Dictionary with statistics
        """
        return {
            "total_subscriptions": len(self.subscriptions),
            "active_subscriptions": len([s for s in self.subscriptions.values() if s.active]),
            "unique_agents": len(self.agent_subscriptions),
            "event_history_size": len(self.event_history),
            "event_types": list(self.event_type_index.keys()),
            "delivery_queue_size": self.delivery_queue.qsize(),
            "callback_subscriptions": len(self.callback_subscriptions)
        }
    
    def _find_matching_subscriptions(self, event: NotificationEvent) -> List[Subscription]:
        """Find subscriptions that match the given event"""
        matching_subscriptions = []
        
        # Check wildcard subscriptions
        wildcard_subscription_ids = self.event_type_index.get("*", set())
        
        # Check event type specific subscriptions
        type_subscription_ids = self.event_type_index.get(event.event_type, set())
        
        # Combine subscription IDs
        all_subscription_ids = wildcard_subscription_ids | type_subscription_ids
        
        # Check each subscription
        for subscription_id in all_subscription_ids:
            if subscription_id in self.subscriptions:
                subscription = self.subscriptions[subscription_id]
                if subscription.active and subscription.matches_event(event):
                    matching_subscriptions.append(subscription)
        
        return matching_subscriptions
    
    async def _delivery_worker(self, worker_name: str):
        """Background worker to deliver events to subscribers"""
        self.logger.info("Starting delivery worker", worker_name=worker_name)
        
        try:
            while True:
                # Get next delivery from queue
                event, subscription = await self.delivery_queue.get()
                
                try:
                    await self._deliver_event(event, subscription)
                except Exception as e:
                    self.logger.error(
                        "Event delivery failed",
                        worker_name=worker_name,
                        event_id=event.event_id,
                        subscription_id=subscription.subscription_id,
                        error=str(e)
                    )
                finally:
                    self.delivery_queue.task_done()
        
        except asyncio.CancelledError:
            self.logger.info("Delivery worker cancelled", worker_name=worker_name)
            raise
        except Exception as e:
            self.logger.error("Delivery worker error", worker_name=worker_name, error=str(e))
    
    async def _deliver_event(self, event: NotificationEvent, subscription: Subscription):
        """Deliver an event to a specific subscription"""
        try:
            delivery_success = False
            
            # Try callback delivery first (in-process)
            if subscription.subscription_id in self.callback_subscriptions:
                try:
                    callback = self.callback_subscriptions[subscription.subscription_id]
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                    delivery_success = True
                    
                    self.logger.debug(
                        "Event delivered via callback",
                        event_id=event.event_id,
                        subscription_id=subscription.subscription_id
                    )
                
                except Exception as e:
                    self.logger.error(
                        "Callback delivery failed",
                        event_id=event.event_id,
                        subscription_id=subscription.subscription_id,
                        error=str(e)
                    )
            
            # Try webhook delivery
            elif subscription.webhook_url:
                try:
                    payload = {
                        "subscription_id": subscription.subscription_id,
                        "event": event.to_dict()
                    }
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            subscription.webhook_url,
                            json=payload,
                            timeout=self.delivery_timeout
                        ) as response:
                            if 200 <= response.status < 300:
                                delivery_success = True
                                
                                self.logger.debug(
                                    "Event delivered via webhook",
                                    event_id=event.event_id,
                                    subscription_id=subscription.subscription_id,
                                    webhook_url=subscription.webhook_url,
                                    status_code=response.status
                                )
                            else:
                                self.logger.warning(
                                    "Webhook delivery failed",
                                    event_id=event.event_id,
                                    subscription_id=subscription.subscription_id,
                                    webhook_url=subscription.webhook_url,
                                    status_code=response.status
                                )
                
                except Exception as e:
                    self.logger.error(
                        "Webhook delivery failed",
                        event_id=event.event_id,
                        subscription_id=subscription.subscription_id,
                        webhook_url=subscription.webhook_url,
                        error=str(e)
                    )
            
            # Update delivery statistics
            if delivery_success:
                subscription.delivery_count += 1
                subscription.last_delivery = datetime.utcnow()
        
        except Exception as e:
            self.logger.error(
                "Event delivery error",
                event_id=event.event_id,
                subscription_id=subscription.subscription_id,
                error=str(e)
            )


# Global notification service instance
_notification_service: Optional[NotificationService] = None


async def get_notification_service() -> NotificationService:
    """Get the global notification service instance"""
    global _notification_service
    
    if _notification_service is None:
        _notification_service = NotificationService()
        await _notification_service.start()
    
    return _notification_service


async def cleanup_notification_service():
    """Cleanup the global notification service instance"""
    global _notification_service
    
    if _notification_service is not None:
        await _notification_service.stop()
        _notification_service = None