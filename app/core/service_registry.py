"""
Service Registry and Discovery
Manages microservice registration, discovery, and health checking
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum

from app.core.redis_client import cache_manager

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """Service status enumeration"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPING = "stopping"
    UNKNOWN = "unknown"


@dataclass
class ServiceInfo:
    """Service information data structure"""
    service_name: str
    service_type: str
    version: str
    host: str
    port: int
    health_check_url: str
    status: ServiceStatus
    last_health_check: datetime
    metadata: Dict[str, Any]
    dependencies: List[str]


class ServiceRegistry:
    """Service registry for microservice discovery and health management"""
    
    def __init__(self):
        self.services: Dict[str, ServiceInfo] = {}
        self.health_check_interval = 30  # seconds
        self.health_check_timeout = 5  # seconds
        self.is_monitoring = False
        self.background_tasks = set()
        
        # Service dependencies mapping
        self.service_dependencies = {
            "user_service": ["database", "redis", "auth_service"],
            "analytics_service": ["database", "redis", "ml_service"],
            "recommendation_service": ["database", "redis", "analytics_service"],
            "data_collection_service": ["database", "redis"],
            "gap_analysis_service": ["database", "redis", "ml_service"],
            "security_service": ["database", "redis"],
            "background_worker_service": ["database", "redis"],
            "performance_monitoring_service": ["database", "redis"]
        }
    
    async def register_service(
        self,
        service_name: str,
        service_type: str,
        version: str,
        host: str = "localhost",
        port: int = 8000,
        health_check_url: str = "/health",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Register a service in the registry"""
        try:
            service_info = ServiceInfo(
                service_name=service_name,
                service_type=service_type,
                version=version,
                host=host,
                port=port,
                health_check_url=health_check_url,
                status=ServiceStatus.STARTING,
                last_health_check=datetime.utcnow(),
                metadata=metadata or {},
                dependencies=self.service_dependencies.get(service_name, [])
            )
            
            self.services[service_name] = service_info
            
            # Cache service info in Redis
            await cache_manager.set_cache(
                f"service_registry:{service_name}",
                asdict(service_info),
                expire=300
            )
            
            logger.info(f"Registered service: {service_name} ({service_type}) at {host}:{port}")
            return True
            
        except Exception as e:
            logger.error(f"Error registering service {service_name}: {e}")
            return False
    
    async def unregister_service(self, service_name: str) -> bool:
        """Unregister a service from the registry"""
        try:
            if service_name in self.services:
                self.services[service_name].status = ServiceStatus.STOPPING
                del self.services[service_name]
                
                # Remove from Redis cache
                await cache_manager.delete_cache(f"service_registry:{service_name}")
                
                logger.info(f"Unregistered service: {service_name}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error unregistering service {service_name}: {e}")
            return False
    
    async def get_service(self, service_name: str) -> Optional[ServiceInfo]:
        """Get service information"""
        try:
            # Try local registry first
            if service_name in self.services:
                return self.services[service_name]
            
            # Try Redis cache
            cached_service = await cache_manager.get_cache(f"service_registry:{service_name}")
            if cached_service:
                # Convert back to ServiceInfo object
                cached_service['status'] = ServiceStatus(cached_service['status'])
                cached_service['last_health_check'] = datetime.fromisoformat(cached_service['last_health_check'])
                return ServiceInfo(**cached_service)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting service {service_name}: {e}")
            return None
    
    async def get_healthy_services(self, service_type: Optional[str] = None) -> List[ServiceInfo]:
        """Get list of healthy services, optionally filtered by type"""
        try:
            healthy_services = []
            
            for service in self.services.values():
                if service.status == ServiceStatus.HEALTHY:
                    if service_type is None or service.service_type == service_type:
                        healthy_services.append(service)
            
            return healthy_services
            
        except Exception as e:
            logger.error(f"Error getting healthy services: {e}")
            return []
    
    async def check_service_health(self, service_name: str) -> bool:
        """Check health of a specific service"""
        try:
            service = await self.get_service(service_name)
            if not service:
                return False
            
            # For now, we'll simulate health checks
            # In a real implementation, this would make HTTP requests to health endpoints
            
            # Check dependencies first
            for dependency in service.dependencies:
                dependency_service = await self.get_service(dependency)
                if not dependency_service or dependency_service.status != ServiceStatus.HEALTHY:
                    logger.warning(f"Service {service_name} dependency {dependency} is not healthy")
                    service.status = ServiceStatus.UNHEALTHY
                    return False
            
            # Simulate health check (in real implementation, make HTTP request)
            # For this implementation, we'll assume services are healthy if they're registered
            service.status = ServiceStatus.HEALTHY
            service.last_health_check = datetime.utcnow()
            
            # Update cache
            await cache_manager.set_cache(
                f"service_registry:{service_name}",
                asdict(service),
                expire=300
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking health for service {service_name}: {e}")
            return False
    
    async def start_health_monitoring(self):
        """Start health monitoring for all registered services"""
        if self.is_monitoring:
            logger.warning("Health monitoring already running")
            return
        
        self.is_monitoring = True
        logger.info("Starting service health monitoring")
        
        # Start health monitoring task
        task = asyncio.create_task(self._health_monitoring_loop())
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)
    
    async def stop_health_monitoring(self):
        """Stop health monitoring"""
        self.is_monitoring = False
        logger.info("Stopping service health monitoring")
        
        # Cancel all background tasks
        for task in self.background_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
    
    async def _health_monitoring_loop(self):
        """Main health monitoring loop"""
        while self.is_monitoring:
            try:
                # Check health of all registered services
                for service_name in list(self.services.keys()):
                    await self.check_service_health(service_name)
                
                # Wait for next check
                await asyncio.sleep(self.health_check_interval)
                
            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}")
                await asyncio.sleep(self.health_check_interval)
    
    async def get_service_topology(self) -> Dict[str, Any]:
        """Get service dependency topology"""
        try:
            topology = {
                "services": {},
                "dependencies": {},
                "health_summary": {
                    "total_services": len(self.services),
                    "healthy_services": 0,
                    "unhealthy_services": 0,
                    "unknown_services": 0
                }
            }
            
            for service_name, service in self.services.items():
                topology["services"][service_name] = {
                    "type": service.service_type,
                    "version": service.version,
                    "status": service.status.value,
                    "last_health_check": service.last_health_check.isoformat(),
                    "metadata": service.metadata
                }
                
                topology["dependencies"][service_name] = service.dependencies
                
                # Update health summary
                if service.status == ServiceStatus.HEALTHY:
                    topology["health_summary"]["healthy_services"] += 1
                elif service.status == ServiceStatus.UNHEALTHY:
                    topology["health_summary"]["unhealthy_services"] += 1
                else:
                    topology["health_summary"]["unknown_services"] += 1
            
            return topology
            
        except Exception as e:
            logger.error(f"Error getting service topology: {e}")
            return {"error": str(e)}
    
    async def validate_service_dependencies(self, service_name: str) -> Dict[str, Any]:
        """Validate that all service dependencies are healthy"""
        try:
            service = await self.get_service(service_name)
            if not service:
                return {"valid": False, "error": f"Service {service_name} not found"}
            
            validation_result = {
                "service_name": service_name,
                "valid": True,
                "dependencies": {},
                "missing_dependencies": [],
                "unhealthy_dependencies": []
            }
            
            for dependency in service.dependencies:
                dependency_service = await self.get_service(dependency)
                
                if not dependency_service:
                    validation_result["valid"] = False
                    validation_result["missing_dependencies"].append(dependency)
                    validation_result["dependencies"][dependency] = "missing"
                elif dependency_service.status != ServiceStatus.HEALTHY:
                    validation_result["valid"] = False
                    validation_result["unhealthy_dependencies"].append(dependency)
                    validation_result["dependencies"][dependency] = dependency_service.status.value
                else:
                    validation_result["dependencies"][dependency] = "healthy"
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error validating dependencies for service {service_name}: {e}")
            return {"valid": False, "error": str(e)}
    
    async def get_load_balancing_candidates(self, service_type: str) -> List[ServiceInfo]:
        """Get healthy services for load balancing"""
        try:
            candidates = await self.get_healthy_services(service_type)
            
            # Sort by last health check (most recently checked first)
            candidates.sort(key=lambda s: s.last_health_check, reverse=True)
            
            return candidates
            
        except Exception as e:
            logger.error(f"Error getting load balancing candidates for {service_type}: {e}")
            return []
    
    async def register_core_services(self):
        """Register core application services"""
        try:
            core_services = [
                {
                    "service_name": "user_service",
                    "service_type": "api",
                    "version": "1.0.0",
                    "metadata": {"endpoints": ["/users", "/auth", "/profile"]}
                },
                {
                    "service_name": "analytics_service",
                    "service_type": "api",
                    "version": "1.0.0",
                    "metadata": {"endpoints": ["/analytics", "/dashboard"]}
                },
                {
                    "service_name": "recommendation_service",
                    "service_type": "api",
                    "version": "1.0.0",
                    "metadata": {"endpoints": ["/recommendations"]}
                },
                {
                    "service_name": "data_collection_service",
                    "service_type": "api",
                    "version": "1.0.0",
                    "metadata": {"endpoints": ["/data"]}
                },
                {
                    "service_name": "gap_analysis_service",
                    "service_type": "api",
                    "version": "1.0.0",
                    "metadata": {"endpoints": ["/gap-analysis"]}
                },
                {
                    "service_name": "security_service",
                    "service_type": "api",
                    "version": "1.0.0",
                    "metadata": {"endpoints": ["/security"]}
                },
                {
                    "service_name": "background_worker_service",
                    "service_type": "worker",
                    "version": "1.0.0",
                    "metadata": {"queues": ["ml_training", "analytics", "cache_refresh"]}
                },
                {
                    "service_name": "performance_monitoring_service",
                    "service_type": "monitoring",
                    "version": "1.0.0",
                    "metadata": {"metrics": ["system", "database", "cache", "application"]}
                },
                {
                    "service_name": "database",
                    "service_type": "infrastructure",
                    "version": "7.0.0",
                    "metadata": {"type": "mongodb"}
                },
                {
                    "service_name": "redis",
                    "service_type": "infrastructure",
                    "version": "7.0.0",
                    "metadata": {"type": "cache"}
                }
            ]
            
            for service_config in core_services:
                await self.register_service(**service_config)
            
            logger.info(f"Registered {len(core_services)} core services")
            
        except Exception as e:
            logger.error(f"Error registering core services: {e}")


# Global service registry instance
service_registry = ServiceRegistry()