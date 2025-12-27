"""
Enhanced Cache Service
Provides advanced caching capabilities for frequently accessed data
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional, Union, Callable
from datetime import datetime, timedelta
import json
import hashlib
from functools import wraps

from app.core.redis_client import cache_manager, get_redis
from app.core.database import get_database

logger = logging.getLogger(__name__)


class EnhancedCacheService:
    """Enhanced caching service with advanced features"""
    
    def __init__(self):
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "last_reset": datetime.utcnow()
        }
        
        # Cache configuration
        self.default_ttl = 3600  # 1 hour
        self.max_cache_size = 10000  # Maximum number of cached items
        
        # Cache prefixes for different data types
        self.prefixes = {
            "user_analytics": "analytics:user:",
            "dashboard_data": "dashboard:",
            "learning_gaps": "gaps:",
            "recommendations": "recommendations:",
            "performance_data": "performance:",
            "ml_models": "models:",
            "aggregated_data": "aggregated:",
            "session_data": "session:",
            "api_responses": "api:",
            "computed_results": "computed:"
        }
    
    async def get_or_compute(
        self,
        key: str,
        compute_func: Callable,
        ttl: int = None,
        cache_type: str = "computed_results"
    ) -> Any:
        """
        Get data from cache or compute it if not cached
        """
        full_key = f"{self.prefixes.get(cache_type, '')}{key}"
        ttl = ttl or self.default_ttl
        
        try:
            # Try to get from cache first
            cached_data = await cache_manager.get_cache(full_key)
            
            if cached_data is not None:
                self.cache_stats["hits"] += 1
                logger.debug(f"Cache hit for key: {full_key}")
                return cached_data
            
            # Cache miss - compute the data
            self.cache_stats["misses"] += 1
            logger.debug(f"Cache miss for key: {full_key}, computing...")
            
            # Compute the data
            if asyncio.iscoroutinefunction(compute_func):
                computed_data = await compute_func()
            else:
                computed_data = compute_func()
            
            # Cache the computed data
            await self.set_cache(key, computed_data, ttl, cache_type)
            
            return computed_data
            
        except Exception as e:
            logger.error(f"Error in get_or_compute for key {full_key}: {e}")
            # If caching fails, still try to compute and return the data
            try:
                if asyncio.iscoroutinefunction(compute_func):
                    return await compute_func()
                else:
                    return compute_func()
            except Exception as compute_error:
                logger.error(f"Error computing data for key {full_key}: {compute_error}")
                raise
    
    async def set_cache(
        self,
        key: str,
        value: Any,
        ttl: int = None,
        cache_type: str = "computed_results"
    ) -> bool:
        """Set cache value with enhanced features"""
        full_key = f"{self.prefixes.get(cache_type, '')}{key}"
        ttl = ttl or self.default_ttl
        
        try:
            # Add metadata to cached value
            cache_data = {
                "value": value,
                "cached_at": datetime.utcnow().isoformat(),
                "ttl": ttl,
                "cache_type": cache_type
            }
            
            success = await cache_manager.set_cache(full_key, cache_data, ttl)
            
            if success:
                self.cache_stats["sets"] += 1
                logger.debug(f"Cached data for key: {full_key} (TTL: {ttl}s)")
            
            return success
            
        except Exception as e:
            logger.error(f"Error setting cache for key {full_key}: {e}")
            return False
    
    async def get_cache(
        self,
        key: str,
        cache_type: str = "computed_results"
    ) -> Optional[Any]:
        """Get cache value with enhanced features"""
        full_key = f"{self.prefixes.get(cache_type, '')}{key}"
        
        try:
            cached_data = await cache_manager.get_cache(full_key)
            
            if cached_data is None:
                self.cache_stats["misses"] += 1
                return None
            
            self.cache_stats["hits"] += 1
            
            # Extract value from metadata
            if isinstance(cached_data, dict) and "value" in cached_data:
                return cached_data["value"]
            else:
                # Backward compatibility for old cache format
                return cached_data
                
        except Exception as e:
            logger.error(f"Error getting cache for key {full_key}: {e}")
            return None
    
    async def delete_cache(
        self,
        key: str,
        cache_type: str = "computed_results"
    ) -> bool:
        """Delete cache value"""
        full_key = f"{self.prefixes.get(cache_type, '')}{key}"
        
        try:
            success = await cache_manager.delete_cache(full_key)
            
            if success:
                self.cache_stats["deletes"] += 1
                logger.debug(f"Deleted cache for key: {full_key}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error deleting cache for key {full_key}: {e}")
            return False
    
    async def cache_user_analytics(
        self,
        user_id: str,
        analytics_data: Dict[str, Any],
        ttl: int = 1800
    ) -> bool:
        """Cache user analytics data with optimized structure"""
        try:
            # Structure analytics data for efficient retrieval
            structured_data = {
                "user_id": user_id,
                "learning_gaps": analytics_data.get("learning_gaps", {}),
                "performance_summary": analytics_data.get("performance_summary", {}),
                "progress_trends": analytics_data.get("progress_trends", {}),
                "recommendations": analytics_data.get("recommendations", {}),
                "last_updated": datetime.utcnow().isoformat()
            }
            
            return await self.set_cache(user_id, structured_data, ttl, "user_analytics")
            
        except Exception as e:
            logger.error(f"Error caching user analytics for {user_id}: {e}")
            return False
    
    async def get_user_analytics(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get cached user analytics data"""
        return await self.get_cache(user_id, "user_analytics")
    
    async def cache_dashboard_data(
        self,
        user_id: str,
        dashboard_data: Dict[str, Any],
        ttl: int = 300
    ) -> bool:
        """Cache dashboard data for quick login"""
        try:
            # Optimize dashboard data structure
            optimized_data = {
                "user_profile": dashboard_data.get("user_profile", {}),
                "recent_activity": dashboard_data.get("recent_activity", []),
                "current_gaps": dashboard_data.get("current_gaps", [])[:5],  # Top 5 gaps
                "active_recommendations": dashboard_data.get("active_recommendations", [])[:3],  # Top 3 recommendations
                "progress_summary": dashboard_data.get("progress_summary", {}),
                "notifications": dashboard_data.get("notifications", [])[:10],  # Recent 10 notifications
                "cached_at": datetime.utcnow().isoformat()
            }
            
            return await self.set_cache(user_id, optimized_data, ttl, "dashboard_data")
            
        except Exception as e:
            logger.error(f"Error caching dashboard data for {user_id}: {e}")
            return False
    
    async def get_dashboard_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get cached dashboard data"""
        return await self.get_cache(user_id, "dashboard_data")
    
    async def cache_learning_gaps(
        self,
        user_id: str,
        gaps: List[Dict[str, Any]],
        ttl: int = 1800
    ) -> bool:
        """Cache learning gaps data"""
        try:
            gaps_data = {
                "gaps": gaps,
                "total_gaps": len(gaps),
                "high_priority_gaps": len([g for g in gaps if g.get("gap_severity", 0) > 0.7]),
                "gap_categories": self._categorize_gaps(gaps),
                "last_updated": datetime.utcnow().isoformat()
            }
            
            return await self.set_cache(user_id, gaps_data, ttl, "learning_gaps")
            
        except Exception as e:
            logger.error(f"Error caching learning gaps for {user_id}: {e}")
            return False
    
    async def get_learning_gaps(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get cached learning gaps data"""
        return await self.get_cache(user_id, "learning_gaps")
    
    async def cache_recommendations(
        self,
        user_id: str,
        recommendations: List[Dict[str, Any]],
        ttl: int = 3600
    ) -> bool:
        """Cache recommendations data"""
        try:
            recommendations_data = {
                "recommendations": recommendations,
                "total_recommendations": len(recommendations),
                "active_recommendations": len([r for r in recommendations if not r.get("completed", False)]),
                "recommendation_types": self._categorize_recommendations(recommendations),
                "last_updated": datetime.utcnow().isoformat()
            }
            
            return await self.set_cache(user_id, recommendations_data, ttl, "recommendations")
            
        except Exception as e:
            logger.error(f"Error caching recommendations for {user_id}: {e}")
            return False
    
    async def get_recommendations(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get cached recommendations data"""
        return await self.get_cache(user_id, "recommendations")
    
    async def cache_ml_model_results(
        self,
        model_name: str,
        input_hash: str,
        results: Dict[str, Any],
        ttl: int = 7200
    ) -> bool:
        """Cache ML model inference results"""
        cache_key = f"{model_name}:{input_hash}"
        
        try:
            model_data = {
                "model_name": model_name,
                "input_hash": input_hash,
                "results": results,
                "cached_at": datetime.utcnow().isoformat()
            }
            
            return await self.set_cache(cache_key, model_data, ttl, "ml_models")
            
        except Exception as e:
            logger.error(f"Error caching ML model results for {model_name}: {e}")
            return False
    
    async def get_ml_model_results(
        self,
        model_name: str,
        input_hash: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached ML model results"""
        cache_key = f"{model_name}:{input_hash}"
        return await self.get_cache(cache_key, "ml_models")
    
    async def cache_aggregated_data(
        self,
        aggregation_key: str,
        data: Dict[str, Any],
        ttl: int = 1800
    ) -> bool:
        """Cache aggregated analytics data"""
        try:
            aggregated_data = {
                "aggregation_key": aggregation_key,
                "data": data,
                "cached_at": datetime.utcnow().isoformat()
            }
            
            return await self.set_cache(aggregation_key, aggregated_data, ttl, "aggregated_data")
            
        except Exception as e:
            logger.error(f"Error caching aggregated data for {aggregation_key}: {e}")
            return False
    
    async def get_aggregated_data(self, aggregation_key: str) -> Optional[Dict[str, Any]]:
        """Get cached aggregated data"""
        return await self.get_cache(aggregation_key, "aggregated_data")
    
    async def cache_api_response(
        self,
        endpoint: str,
        params_hash: str,
        response_data: Dict[str, Any],
        ttl: int = 600
    ) -> bool:
        """Cache API response data"""
        cache_key = f"{endpoint}:{params_hash}"
        
        try:
            api_data = {
                "endpoint": endpoint,
                "params_hash": params_hash,
                "response_data": response_data,
                "cached_at": datetime.utcnow().isoformat()
            }
            
            return await self.set_cache(cache_key, api_data, ttl, "api_responses")
            
        except Exception as e:
            logger.error(f"Error caching API response for {endpoint}: {e}")
            return False
    
    async def get_api_response(
        self,
        endpoint: str,
        params_hash: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached API response"""
        cache_key = f"{endpoint}:{params_hash}"
        return await self.get_cache(cache_key, "api_responses")
    
    async def invalidate_user_cache(self, user_id: str) -> bool:
        """Invalidate all cache entries for a user"""
        try:
            cache_types = ["user_analytics", "dashboard_data", "learning_gaps", "recommendations"]
            
            results = []
            for cache_type in cache_types:
                result = await self.delete_cache(user_id, cache_type)
                results.append(result)
            
            success = all(results)
            
            if success:
                logger.info(f"Invalidated all cache entries for user {user_id}")
            else:
                logger.warning(f"Partial cache invalidation for user {user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error invalidating user cache for {user_id}: {e}")
            return False
    
    async def warm_cache_for_user(self, user_id: str) -> bool:
        """Pre-warm cache for a user with essential data"""
        try:
            from app.services.analytics_precompute_service import AnalyticsPrecomputeService
            from app.core.database import get_database
            
            db = await get_database()
            precompute_service = AnalyticsPrecomputeService(db)
            
            # Pre-compute and cache analytics data
            analytics_data = await precompute_service.precompute_user_analytics(user_id)
            
            if analytics_data:
                # Cache individual components
                await self.cache_user_analytics(user_id, analytics_data)
                await self.cache_dashboard_data(user_id, analytics_data)
                
                if analytics_data.get("learning_gaps", {}).get("gaps"):
                    await self.cache_learning_gaps(
                        user_id,
                        analytics_data["learning_gaps"]["gaps"]
                    )
                
                if analytics_data.get("recommendations", {}).get("recommendations"):
                    await self.cache_recommendations(
                        user_id,
                        analytics_data["recommendations"]["recommendations"]
                    )
                
                logger.info(f"Cache warmed for user {user_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error warming cache for user {user_id}: {e}")
            return False
    
    async def get_cache_statistics(self) -> Dict[str, Any]:
        """Get cache usage statistics"""
        try:
            redis_client = await get_redis()
            
            # Get Redis info
            redis_info = await redis_client.info("memory")
            
            # Calculate hit rate
            total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
            hit_rate = (self.cache_stats["hits"] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                "cache_stats": self.cache_stats,
                "hit_rate_percentage": round(hit_rate, 2),
                "redis_memory_usage": redis_info.get("used_memory_human", "unknown"),
                "redis_memory_peak": redis_info.get("used_memory_peak_human", "unknown"),
                "cache_prefixes": list(self.prefixes.keys()),
                "default_ttl": self.default_ttl,
                "max_cache_size": self.max_cache_size
            }
            
        except Exception as e:
            logger.error(f"Error getting cache statistics: {e}")
            return {"error": str(e)}
    
    async def cleanup_expired_cache(self) -> Dict[str, Any]:
        """Clean up expired cache entries"""
        try:
            redis_client = await get_redis()
            
            # Get all keys with TTL
            all_keys = await redis_client.keys("*")
            expired_keys = []
            
            for key in all_keys:
                ttl = await redis_client.ttl(key)
                if ttl == -1:  # No expiration set
                    continue
                elif ttl == -2:  # Key doesn't exist or expired
                    expired_keys.append(key)
            
            # Clean up expired keys
            if expired_keys:
                deleted_count = await redis_client.delete(*expired_keys)
                logger.info(f"Cleaned up {deleted_count} expired cache entries")
            
            return {
                "total_keys_checked": len(all_keys),
                "expired_keys_found": len(expired_keys),
                "keys_deleted": len(expired_keys)
            }
            
        except Exception as e:
            logger.error(f"Error cleaning up expired cache: {e}")
            return {"error": str(e)}
    
    def reset_cache_statistics(self):
        """Reset cache statistics"""
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "last_reset": datetime.utcnow()
        }
        logger.info("Cache statistics reset")
    
    def _categorize_gaps(self, gaps: List[Dict[str, Any]]) -> Dict[str, int]:
        """Categorize learning gaps by concept area"""
        categories = {}
        for gap in gaps:
            concept_id = gap.get('concept_id', 'unknown')
            category = concept_id.split('.')[0] if '.' in concept_id else concept_id
            categories[category] = categories.get(category, 0) + 1
        return categories
    
    def _categorize_recommendations(self, recommendations: List[Dict[str, Any]]) -> Dict[str, int]:
        """Categorize recommendations by resource type"""
        categories = {}
        for rec in recommendations:
            resource_type = rec.get('resource_type', 'unknown')
            categories[resource_type] = categories.get(resource_type, 0) + 1
        return categories
    
    @staticmethod
    def generate_cache_key(*args) -> str:
        """Generate a consistent cache key from arguments"""
        key_string = ":".join(str(arg) for arg in args)
        return hashlib.md5(key_string.encode()).hexdigest()


def cache_result(
    ttl: int = 3600,
    cache_type: str = "computed_results",
    key_func: Optional[Callable] = None
):
    """
    Decorator for caching function results
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = EnhancedCacheService.generate_cache_key(
                    func.__name__, *args, *kwargs.values()
                )
            
            # Use enhanced cache service
            enhanced_cache = EnhancedCacheService()
            
            return await enhanced_cache.get_or_compute(
                cache_key,
                lambda: func(*args, **kwargs),
                ttl,
                cache_type
            )
        
        return wrapper
    return decorator


# Global instance for enhanced cache service
enhanced_cache_service = EnhancedCacheService()