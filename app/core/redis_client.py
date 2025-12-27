"""
Redis client configuration for caching and session management
"""
import redis.asyncio as redis
import json
import logging
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Global Redis client instance
redis_client: redis.Redis = None


async def init_redis():
    """Initialize Redis connection"""
    global redis_client
    
    try:
        # Create Redis client
        redis_client = redis.from_url(
            settings.REDIS_URL,
            db=settings.REDIS_DB,
            decode_responses=True
        )
        
        # Test connection
        await redis_client.ping()
        logger.info("Successfully connected to Redis")
        
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise


async def get_redis() -> redis.Redis:
    """Get Redis client instance"""
    return redis_client


async def close_redis():
    """Close Redis connection"""
    global redis_client
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")


class CacheManager:
    """Redis cache manager for common operations"""
    
    @staticmethod
    async def set_cache(key: str, value: Any, expire: int = 3600) -> bool:
        """Set cache value with expiration"""
        try:
            serialized_value = json.dumps(value) if not isinstance(value, str) else value
            await redis_client.setex(key, expire, serialized_value)
            return True
        except Exception as e:
            logger.error(f"Failed to set cache for key {key}: {e}")
            return False
    
    @staticmethod
    async def get_cache(key: str) -> Optional[Any]:
        """Get cache value"""
        try:
            value = await redis_client.get(key)
            if value is None:
                return None
            
            # Try to deserialize JSON, fallback to string
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        except Exception as e:
            logger.error(f"Failed to get cache for key {key}: {e}")
            return None
    
    @staticmethod
    async def delete_cache(key: str) -> bool:
        """Delete cache value"""
        try:
            result = await redis_client.delete(key)
            return result > 0
        except Exception as e:
            logger.error(f"Failed to delete cache for key {key}: {e}")
            return False
    
    @staticmethod
    async def set_session(session_id: str, user_data: dict, expire: int = 86400) -> bool:
        """Set user session data"""
        return await CacheManager.set_cache(f"session:{session_id}", user_data, expire)
    
    @staticmethod
    async def get_session(session_id: str) -> Optional[dict]:
        """Get user session data"""
        return await CacheManager.get_cache(f"session:{session_id}")
    
    @staticmethod
    async def delete_session(session_id: str) -> bool:
        """Delete user session"""
        return await CacheManager.delete_cache(f"session:{session_id}")
    
    @staticmethod
    async def cache_dashboard_data(user_id: str, dashboard_data: dict, expire: int = 300) -> bool:
        """Cache dashboard data for quick retrieval"""
        return await CacheManager.set_cache(f"dashboard:{user_id}", dashboard_data, expire)
    
    @staticmethod
    async def get_dashboard_data(user_id: str) -> Optional[dict]:
        """Get cached dashboard data"""
        return await CacheManager.get_cache(f"dashboard:{user_id}")


# Create cache manager instance
cache_manager = CacheManager()