"""Base repository class for common database operations."""

import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, TypeVar, Generic
from uuid import UUID
import asyncpg
import redis.asyncio as redis
import structlog

from dora.database.connections import DatabaseManager


logger = structlog.get_logger(__name__)

T = TypeVar('T')


class BaseRepository(ABC, Generic[T]):
    """Base repository class providing common database operations."""
    
    def __init__(self, db_manager: DatabaseManager, table_name: str):
        """
        Initialize base repository.
        
        Args:
            db_manager: Database manager instance
            table_name: Name of the database table
        """
        self.db_manager = db_manager
        self.table_name = table_name
        self.logger = logger.bind(component=f"{table_name}_repository")
    
    @abstractmethod
    def _row_to_model(self, row: asyncpg.Record) -> T:
        """Convert database row to model instance."""
        pass
    
    @abstractmethod
    def _model_to_dict(self, model: T) -> Dict[str, Any]:
        """Convert model instance to dictionary for database storage."""
        pass
    
    async def find_by_id(self, id_value: Union[str, int, UUID]) -> Optional[T]:
        """
        Find a record by its ID.
        
        Args:
            id_value: The ID to search for
            
        Returns:
            Model instance if found, None otherwise
        """
        try:
            async with self.db_manager.get_postgres_connection() as conn:
                query = f"SELECT * FROM {self.table_name} WHERE id = $1"
                row = await conn.fetchrow(query, id_value)
                
                if row:
                    return self._row_to_model(row)
                return None
                
        except Exception as e:
            self.logger.error("Error finding record by ID", 
                            table=self.table_name, id=id_value, error=str(e))
            raise
    
    async def find_all(self, limit: int = 1000, offset: int = 0) -> List[T]:
        """
        Find all records with pagination.
        
        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip
            
        Returns:
            List of model instances
        """
        try:
            async with self.db_manager.get_postgres_connection() as conn:
                query = f"SELECT * FROM {self.table_name} ORDER BY id LIMIT $1 OFFSET $2"
                rows = await conn.fetch(query, limit, offset)
                
                return [self._row_to_model(row) for row in rows]
                
        except Exception as e:
            self.logger.error("Error finding all records", 
                            table=self.table_name, error=str(e))
            raise
    
    async def count(self, where_clause: str = "", params: List[Any] = None) -> int:
        """
        Count records in the table.
        
        Args:
            where_clause: Optional WHERE clause (without WHERE keyword)
            params: Parameters for the WHERE clause
            
        Returns:
            Number of records
        """
        try:
            params = params or []
            
            if where_clause:
                query = f"SELECT COUNT(*) FROM {self.table_name} WHERE {where_clause}"
            else:
                query = f"SELECT COUNT(*) FROM {self.table_name}"
            
            async with self.db_manager.get_postgres_connection() as conn:
                return await conn.fetchval(query, *params)
                
        except Exception as e:
            self.logger.error("Error counting records", 
                            table=self.table_name, error=str(e))
            raise
    
    async def create(self, model: T) -> T:
        """
        Create a new record.
        
        Args:
            model: Model instance to create
            
        Returns:
            Created model instance with updated fields (e.g., ID, timestamps)
        """
        try:
            data = self._model_to_dict(model)
            
            # Remove None values and prepare for insert
            filtered_data = {k: v for k, v in data.items() if v is not None}
            
            columns = list(filtered_data.keys())
            placeholders = [f"${i+1}" for i in range(len(columns))]
            values = list(filtered_data.values())
            
            query = f"""
                INSERT INTO {self.table_name} ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
                RETURNING *
            """
            
            async with self.db_manager.get_postgres_connection() as conn:
                row = await conn.fetchrow(query, *values)
                created_model = self._row_to_model(row)
                
                self.logger.info("Record created", 
                               table=self.table_name, id=getattr(created_model, 'id', None))
                
                return created_model
                
        except Exception as e:
            self.logger.error("Error creating record", 
                            table=self.table_name, error=str(e))
            raise
    
    async def update(self, id_value: Union[str, int, UUID], updates: Dict[str, Any]) -> Optional[T]:
        """
        Update a record by ID.
        
        Args:
            id_value: ID of the record to update
            updates: Dictionary of fields to update
            
        Returns:
            Updated model instance if found, None otherwise
        """
        try:
            if not updates:
                return await self.find_by_id(id_value)
            
            # Remove None values
            filtered_updates = {k: v for k, v in updates.items() if v is not None}
            
            if not filtered_updates:
                return await self.find_by_id(id_value)
            
            # Add updated_at timestamp if not explicitly provided
            if 'updated_at' not in filtered_updates:
                filtered_updates['updated_at'] = datetime.utcnow()
            
            set_clauses = [f"{col} = ${i+2}" for i, col in enumerate(filtered_updates.keys())]
            values = [id_value] + list(filtered_updates.values())
            
            query = f"""
                UPDATE {self.table_name}
                SET {', '.join(set_clauses)}
                WHERE id = $1
                RETURNING *
            """
            
            async with self.db_manager.get_postgres_connection() as conn:
                row = await conn.fetchrow(query, *values)
                
                if row:
                    updated_model = self._row_to_model(row)
                    self.logger.info("Record updated", 
                                   table=self.table_name, id=id_value)
                    return updated_model
                
                return None
                
        except Exception as e:
            self.logger.error("Error updating record", 
                            table=self.table_name, id=id_value, error=str(e))
            raise
    
    async def delete(self, id_value: Union[str, int, UUID]) -> bool:
        """
        Delete a record by ID.
        
        Args:
            id_value: ID of the record to delete
            
        Returns:
            True if record was deleted, False if not found
        """
        try:
            query = f"DELETE FROM {self.table_name} WHERE id = $1"
            
            async with self.db_manager.get_postgres_connection() as conn:
                result = await conn.execute(query, id_value)
                
                deleted = result.split()[-1] == "1"  # "DELETE 1" or "DELETE 0"
                
                if deleted:
                    self.logger.info("Record deleted", 
                                   table=self.table_name, id=id_value)
                
                return deleted
                
        except Exception as e:
            self.logger.error("Error deleting record", 
                            table=self.table_name, id=id_value, error=str(e))
            raise
    
    async def find_by_criteria(self, 
                              where_clause: str, 
                              params: List[Any] = None,
                              order_by: str = "id",
                              limit: int = 1000,
                              offset: int = 0) -> List[T]:
        """
        Find records matching criteria.
        
        Args:
            where_clause: WHERE clause (without WHERE keyword)
            params: Parameters for the WHERE clause
            order_by: ORDER BY clause
            limit: Maximum number of records
            offset: Number of records to skip
            
        Returns:
            List of matching model instances
        """
        try:
            params = params or []
            
            query = f"""
                SELECT * FROM {self.table_name}
                WHERE {where_clause}
                ORDER BY {order_by}
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """
            
            async with self.db_manager.get_postgres_connection() as conn:
                rows = await conn.fetch(query, *params, limit, offset)
                
                return [self._row_to_model(row) for row in rows]
                
        except Exception as e:
            self.logger.error("Error finding records by criteria", 
                            table=self.table_name, error=str(e))
            raise
    
    async def exists(self, id_value: Union[str, int, UUID]) -> bool:
        """
        Check if a record exists by ID.
        
        Args:
            id_value: ID to check
            
        Returns:
            True if record exists, False otherwise
        """
        try:
            query = f"SELECT 1 FROM {self.table_name} WHERE id = $1 LIMIT 1"
            
            async with self.db_manager.get_postgres_connection() as conn:
                result = await conn.fetchval(query, id_value)
                return result is not None
                
        except Exception as e:
            self.logger.error("Error checking record existence", 
                            table=self.table_name, id=id_value, error=str(e))
            raise
    
    # Cache methods
    async def cache_set(self, key: str, value: Any, expiry: int = 3600) -> None:
        """
        Set a value in Redis cache.
        
        Args:
            key: Cache key
            value: Value to cache
            expiry: Expiry time in seconds
        """
        try:
            redis_client = self.db_manager.get_redis_client()
            
            if isinstance(value, (dict, list)):
                value = json.dumps(value, default=str)
            
            await redis_client.setex(key, expiry, value)
            
        except Exception as e:
            self.logger.warning("Cache set failed", key=key, error=str(e))
    
    async def cache_get(self, key: str) -> Optional[Any]:
        """
        Get a value from Redis cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        try:
            redis_client = self.db_manager.get_redis_client()
            value = await redis_client.get(key)
            
            if value is None:
                return None
            
            # Try to parse as JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
                
        except Exception as e:
            self.logger.warning("Cache get failed", key=key, error=str(e))
            return None
    
    async def cache_delete(self, key: str) -> None:
        """
        Delete a value from Redis cache.
        
        Args:
            key: Cache key to delete
        """
        try:
            redis_client = self.db_manager.get_redis_client()
            await redis_client.delete(key)
            
        except Exception as e:
            self.logger.warning("Cache delete failed", key=key, error=str(e))
    
    async def cache_clear_pattern(self, pattern: str) -> int:
        """
        Clear cache keys matching a pattern.
        
        Args:
            pattern: Pattern to match (e.g., "events:*")
            
        Returns:
            Number of keys deleted
        """
        try:
            redis_client = self.db_manager.get_redis_client()
            keys = await redis_client.keys(pattern)
            
            if keys:
                deleted = await redis_client.delete(*keys)
                self.logger.info("Cache pattern cleared", pattern=pattern, deleted=deleted)
                return deleted
            
            return 0
            
        except Exception as e:
            self.logger.warning("Cache pattern clear failed", pattern=pattern, error=str(e))
            return 0
    
    def _serialize_for_cache(self, obj: Any) -> str:
        """Serialize object for cache storage."""
        if hasattr(obj, 'dict'):  # Pydantic model
            return json.dumps(obj.dict(), default=str)
        elif hasattr(obj, '__dict__'):  # Regular object
            return json.dumps(obj.__dict__, default=str)
        else:
            return json.dumps(obj, default=str)