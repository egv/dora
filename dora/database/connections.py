"""Database connection management for Dora application."""

import asyncio
import logging
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
import asyncpg
import redis.asyncio as redis
import structlog

from dora.models.config import DoraConfig


logger = structlog.get_logger(__name__)


class DatabaseManager:
    """Manages database connections and pools for PostgreSQL and Redis."""
    
    def __init__(self, config: DoraConfig):
        """
        Initialize database manager with configuration.
        
        Args:
            config: Application configuration containing database settings
        """
        self.config = config
        self.logger = logger.bind(component="database_manager")
        
        # Connection pools
        self._postgres_pool: Optional[asyncpg.Pool] = None
        self._redis_client: Optional[redis.Redis] = None
        
        # Pool configuration
        self._postgres_pool_config = {
            "min_size": max(1, config.db_pool_size // 2),
            "max_size": config.db_pool_size,
            "max_queries": 50000,
            "max_inactive_connection_lifetime": 300,
            "timeout": config.db_pool_timeout,
            "command_timeout": 60,
            "server_settings": {
                "application_name": "dora_calendar_intelligence",
                "timezone": "UTC"
            }
        }
        
        self._redis_pool_config = {
            "max_connections": config.redis_pool_size,
            "retry_on_timeout": True,
            "health_check_interval": 30
        }
    
    async def initialize(self) -> None:
        """Initialize database connections and pools."""
        try:
            self.logger.info("Initializing database connections")
            
            # Initialize PostgreSQL pool
            await self._initialize_postgres()
            
            # Initialize Redis client
            await self._initialize_redis()
            
            # Verify connections
            await self._verify_connections()
            
            self.logger.info(
                "Database connections initialized successfully",
                postgres_pool_size=self._postgres_pool.get_size() if self._postgres_pool else 0,
                redis_connected=self._redis_client is not None
            )
            
        except Exception as e:
            self.logger.error("Failed to initialize database connections", error=str(e))
            await self.cleanup()
            raise
    
    async def _initialize_postgres(self) -> None:
        """Initialize PostgreSQL connection pool."""
        try:
            self.logger.info("Creating PostgreSQL connection pool", 
                           database_url=self._mask_password(self.config.database_url))
            
            self._postgres_pool = await asyncpg.create_pool(
                self.config.database_url,
                **self._postgres_pool_config
            )
            
            self.logger.info("PostgreSQL connection pool created successfully")
            
        except Exception as e:
            self.logger.error("Failed to create PostgreSQL connection pool", error=str(e))
            raise
    
    async def _initialize_redis(self) -> None:
        """Initialize Redis client with connection pool."""
        try:
            self.logger.info("Creating Redis connection", redis_url=self.config.redis_url)
            
            self._redis_client = redis.from_url(
                self.config.redis_url,
                **self._redis_pool_config,
                decode_responses=True
            )
            
            self.logger.info("Redis client created successfully")
            
        except Exception as e:
            self.logger.error("Failed to create Redis client", error=str(e))
            raise
    
    async def _verify_connections(self) -> None:
        """Verify that database connections are working."""
        # Test PostgreSQL
        if self._postgres_pool:
            async with self._postgres_pool.acquire() as conn:
                version = await conn.fetchval("SELECT version()")
                self.logger.info("PostgreSQL connection verified", version=version[:50])
        
        # Test Redis
        if self._redis_client:
            await self._redis_client.ping()
            info = await self._redis_client.info("server")
            self.logger.info("Redis connection verified", version=info.get("redis_version"))
    
    async def cleanup(self) -> None:
        """Clean up database connections and pools."""
        self.logger.info("Cleaning up database connections")
        
        # Close Redis client
        if self._redis_client:
            try:
                await self._redis_client.close()
                self.logger.info("Redis client closed")
            except Exception as e:
                self.logger.error("Error closing Redis client", error=str(e))
            finally:
                self._redis_client = None
        
        # Close PostgreSQL pool
        if self._postgres_pool:
            try:
                await self._postgres_pool.close()
                self.logger.info("PostgreSQL pool closed")
            except Exception as e:
                self.logger.error("Error closing PostgreSQL pool", error=str(e))
            finally:
                self._postgres_pool = None
    
    @asynccontextmanager
    async def get_postgres_connection(self):
        """
        Get a PostgreSQL connection from the pool.
        
        Yields:
            asyncpg.Connection: Database connection
        """
        if not self._postgres_pool:
            raise RuntimeError("PostgreSQL pool not initialized")
        
        async with self._postgres_pool.acquire() as connection:
            try:
                yield connection
            except Exception as e:
                self.logger.error("Database operation error", error=str(e))
                raise
    
    @asynccontextmanager
    async def get_postgres_transaction(self):
        """
        Get a PostgreSQL transaction from the pool.
        
        Yields:
            asyncpg.Connection: Database connection with active transaction
        """
        async with self.get_postgres_connection() as conn:
            async with conn.transaction():
                yield conn
    
    def get_redis_client(self) -> redis.Redis:
        """
        Get the Redis client.
        
        Returns:
            redis.Redis: Redis client instance
            
        Raises:
            RuntimeError: If Redis client not initialized
        """
        if not self._redis_client:
            raise RuntimeError("Redis client not initialized")
        return self._redis_client
    
    async def get_postgres_pool_stats(self) -> Dict[str, Any]:
        """Get PostgreSQL pool statistics."""
        if not self._postgres_pool:
            return {"status": "not_initialized"}
        
        return {
            "status": "initialized",
            "size": self._postgres_pool.get_size(),
            "min_size": self._postgres_pool.get_min_size(),
            "max_size": self._postgres_pool.get_max_size(),
            "idle_size": self._postgres_pool.get_idle_size()
        }
    
    async def get_redis_info(self) -> Dict[str, Any]:
        """Get Redis server information."""
        if not self._redis_client:
            return {"status": "not_initialized"}
        
        try:
            info = await self._redis_client.info()
            return {
                "status": "connected",
                "version": info.get("redis_version"),
                "connected_clients": info.get("connected_clients"),
                "used_memory": info.get("used_memory_human"),
                "uptime": info.get("uptime_in_seconds")
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all database connections."""
        health = {
            "postgres": {"status": "unknown"},
            "redis": {"status": "unknown"},
            "overall": "unknown"
        }
        
        # Check PostgreSQL
        try:
            if self._postgres_pool:
                async with self.get_postgres_connection() as conn:
                    await conn.fetchval("SELECT 1")
                health["postgres"] = {"status": "healthy"}
            else:
                health["postgres"] = {"status": "not_initialized"}
        except Exception as e:
            health["postgres"] = {"status": "unhealthy", "error": str(e)}
        
        # Check Redis
        try:
            if self._redis_client:
                await self._redis_client.ping()
                health["redis"] = {"status": "healthy"}
            else:
                health["redis"] = {"status": "not_initialized"}
        except Exception as e:
            health["redis"] = {"status": "unhealthy", "error": str(e)}
        
        # Overall health
        postgres_healthy = health["postgres"]["status"] == "healthy"
        redis_healthy = health["redis"]["status"] == "healthy"
        
        if postgres_healthy and redis_healthy:
            health["overall"] = "healthy"
        elif postgres_healthy or redis_healthy:
            health["overall"] = "degraded"
        else:
            health["overall"] = "unhealthy"
        
        return health
    
    def _mask_password(self, database_url: str) -> str:
        """Mask password in database URL for logging."""
        try:
            if "://" in database_url and "@" in database_url:
                scheme, rest = database_url.split("://", 1)
                if "@" in rest:
                    auth, host_part = rest.split("@", 1)
                    if ":" in auth:
                        user, _ = auth.split(":", 1)
                        return f"{scheme}://{user}:***@{host_part}"
            return database_url
        except Exception:
            return "***"


# Global database manager instance
_database_manager: Optional[DatabaseManager] = None


async def initialize_database_manager(config: DoraConfig) -> DatabaseManager:
    """
    Initialize the global database manager.
    
    Args:
        config: Application configuration
        
    Returns:
        DatabaseManager: Initialized database manager
    """
    global _database_manager
    
    if _database_manager is not None:
        await _database_manager.cleanup()
    
    _database_manager = DatabaseManager(config)
    await _database_manager.initialize()
    
    return _database_manager


def get_database_manager() -> DatabaseManager:
    """
    Get the global database manager instance.
    
    Returns:
        DatabaseManager: The global database manager
        
    Raises:
        RuntimeError: If database manager not initialized
    """
    if _database_manager is None:
        raise RuntimeError("Database manager not initialized. Call initialize_database_manager() first.")
    
    return _database_manager


async def cleanup_database_manager() -> None:
    """Clean up the global database manager."""
    global _database_manager
    
    if _database_manager is not None:
        await _database_manager.cleanup()
        _database_manager = None