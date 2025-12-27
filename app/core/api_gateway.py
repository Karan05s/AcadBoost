"""
API Gateway Service
Handles request routing, load balancing, and service integration
"""
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
import httpx

from app.core.service_registry import service_registry, ServiceStatus
from app.core.redis_client import cache_manager
from app.services.performance_monitoring_service import performance_monitoring_service

logger = logging.getLogger(__name__)


class APIGateway:
    """API Gateway for request routing and service integration"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.circuit_breakers = {}
        self.rate_limiters = {}
        
        # Gateway configuration
        self.max_retries = 3
        self.retry_delay = 1.0  # seconds
        self.circuit_breaker_threshold = 5  # failures
        self.circuit_breaker_timeout = 60  # seconds
        self.rate_limit_window = 60  # seconds
        self.default_rate_limit = 100  # requests per window
        
        # Request routing rules
        self.routing_rules = {
            "/api/v1/auth": "user_service",
            "/api/v1/users": "user_service",
            "/api/v1/data": "data_collection_service",
            "/api/v1/analytics": "analytics_service",
            "/api/v1/recommendations": "recommendation_service",
            "/api/v1/gap-analysis": "gap_analysis_service",
            "/api/v1/security": "security_service",
            "/api/v1/monitoring": "performance_monitoring_service"
        }
        
        # Load balancing strategies
        self.load_balancing_strategies = {
            "round_robin": self._round_robin_strategy,
            "least_connections": self._least_connections_strategy,
            "health_based": self._health_based_strategy
        }
        
        self.current_strategy = "health_based"
        self.service_counters = {}  # For round robin
    
    async def route_request(
        self,
        request: Request,
        path: str,
        method: str,
        headers: Dict[str, str],
        body: bytes = None
    ) -> Response:
        """Route request to appropriate service"""
        try:
            # Determine target service
            service_name = self._get_target_service(path)
            if not service_name:
                raise HTTPException(status_code=404, detail="Service not found for path")
            
            # Check circuit breaker
            if self._is_circuit_breaker_open(service_name):
                raise HTTPException(status_code=503, detail="Service temporarily unavailable")
            
            # Check rate limiting
            if not await self._check_rate_limit(request, service_name):
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            
            # Get service instance for load balancing
            service_instance = await self._select_service_instance(service_name)
            if not service_instance:
                raise HTTPException(status_code=503, detail="No healthy service instances available")
            
            # Forward request with retries
            response = await self._forward_request_with_retry(
                service_instance,
                path,
                method,
                headers,
                body
            )
            
            # Update circuit breaker on success
            self._record_success(service_name)
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error routing request to {path}: {e}")
            raise HTTPException(status_code=500, detail="Internal gateway error")
    
    def _get_target_service(self, path: str) -> Optional[str]:
        """Determine target service based on request path"""
        for route_prefix, service_name in self.routing_rules.items():
            if path.startswith(route_prefix):
                return service_name
        return None
    
    async def _select_service_instance(self, service_name: str):
        """Select service instance using load balancing strategy"""
        try:
            # Get healthy service instances
            candidates = await service_registry.get_load_balancing_candidates("api")
            service_candidates = [s for s in candidates if s.service_name == service_name]
            
            if not service_candidates:
                return None
            
            # Apply load balancing strategy
            strategy_func = self.load_balancing_strategies.get(self.current_strategy)
            if strategy_func:
                return strategy_func(service_candidates)
            
            # Fallback to first available
            return service_candidates[0]
            
        except Exception as e:
            logger.error(f"Error selecting service instance for {service_name}: {e}")
            return None
    
    def _round_robin_strategy(self, candidates: List) -> Optional[Any]:
        """Round robin load balancing strategy"""
        if not candidates:
            return None
        
        service_name = candidates[0].service_name
        counter = self.service_counters.get(service_name, 0)
        selected = candidates[counter % len(candidates)]
        self.service_counters[service_name] = counter + 1
        
        return selected
    
    def _least_connections_strategy(self, candidates: List) -> Optional[Any]:
        """Least connections load balancing strategy"""
        if not candidates:
            return None
        
        # For simplicity, we'll use round robin
        # In a real implementation, this would track active connections
        return self._round_robin_strategy(candidates)
    
    def _health_based_strategy(self, candidates: List) -> Optional[Any]:
        """Health-based load balancing strategy"""
        if not candidates:
            return None
        
        # Sort by last health check (most recent first)
        candidates.sort(key=lambda s: s.last_health_check, reverse=True)
        return candidates[0]
    
    async def _forward_request_with_retry(
        self,
        service_instance,
        path: str,
        method: str,
        headers: Dict[str, str],
        body: bytes = None
    ) -> Response:
        """Forward request to service with retry logic"""
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                # Build target URL
                target_url = f"http://{service_instance.host}:{service_instance.port}{path}"
                
                # Prepare request
                request_kwargs = {
                    "method": method,
                    "url": target_url,
                    "headers": headers,
                    "timeout": 30.0
                }
                
                if body:
                    request_kwargs["content"] = body
                
                # Make request
                start_time = time.time()
                response = await self.client.request(**request_kwargs)
                response_time = time.time() - start_time
                
                # Track performance
                performance_monitoring_service.track_request_end(
                    response_time,
                    success=200 <= response.status_code < 400
                )
                
                # Convert to FastAPI Response
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.headers.get("content-type", "application/json")
                )
                
            except Exception as e:
                last_exception = e
                logger.warning(f"Request attempt {attempt + 1} failed for {path}: {e}")
                
                # Record failure for circuit breaker
                self._record_failure(service_instance.service_name)
                
                # Wait before retry (except on last attempt)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        # All retries failed
        raise HTTPException(
            status_code=503,
            detail=f"Service unavailable after {self.max_retries} attempts: {str(last_exception)}"
        )
    
    def _is_circuit_breaker_open(self, service_name: str) -> bool:
        """Check if circuit breaker is open for service"""
        breaker = self.circuit_breakers.get(service_name)
        if not breaker:
            return False
        
        # Check if circuit breaker should be reset
        if breaker["open_until"] < datetime.utcnow():
            breaker["failures"] = 0
            breaker["open"] = False
            breaker["open_until"] = None
            return False
        
        return breaker["open"]
    
    def _record_failure(self, service_name: str):
        """Record service failure for circuit breaker"""
        if service_name not in self.circuit_breakers:
            self.circuit_breakers[service_name] = {
                "failures": 0,
                "open": False,
                "open_until": None
            }
        
        breaker = self.circuit_breakers[service_name]
        breaker["failures"] += 1
        
        # Open circuit breaker if threshold exceeded
        if breaker["failures"] >= self.circuit_breaker_threshold:
            breaker["open"] = True
            breaker["open_until"] = datetime.utcnow() + timedelta(seconds=self.circuit_breaker_timeout)
            logger.warning(f"Circuit breaker opened for service {service_name}")
    
    def _record_success(self, service_name: str):
        """Record service success for circuit breaker"""
        if service_name in self.circuit_breakers:
            self.circuit_breakers[service_name]["failures"] = 0
    
    async def _check_rate_limit(self, request: Request, service_name: str) -> bool:
        """Check rate limiting for request"""
        try:
            # Get client identifier (IP address or user ID)
            client_id = request.client.host if request.client else "unknown"
            if hasattr(request.state, "user_id"):
                client_id = request.state.user_id
            
            # Create rate limit key
            rate_limit_key = f"rate_limit:{service_name}:{client_id}"
            
            # Get current count from cache
            current_count = await cache_manager.get_cache(rate_limit_key)
            if current_count is None:
                current_count = 0
            
            # Check if limit exceeded
            if current_count >= self.default_rate_limit:
                return False
            
            # Increment counter
            await cache_manager.set_cache(
                rate_limit_key,
                current_count + 1,
                expire=self.rate_limit_window
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            # Allow request on error
            return True
    
    async def get_gateway_status(self) -> Dict[str, Any]:
        """Get API gateway status and metrics"""
        try:
            # Get service topology
            topology = await service_registry.get_service_topology()
            
            # Get circuit breaker status
            circuit_breaker_status = {}
            for service_name, breaker in self.circuit_breakers.items():
                circuit_breaker_status[service_name] = {
                    "open": breaker["open"],
                    "failures": breaker["failures"],
                    "open_until": breaker["open_until"].isoformat() if breaker["open_until"] else None
                }
            
            # Get routing rules
            routing_info = {
                "rules": self.routing_rules,
                "load_balancing_strategy": self.current_strategy,
                "max_retries": self.max_retries,
                "circuit_breaker_threshold": self.circuit_breaker_threshold
            }
            
            return {
                "gateway_status": "operational",
                "service_topology": topology,
                "circuit_breakers": circuit_breaker_status,
                "routing_configuration": routing_info,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting gateway status: {e}")
            return {"error": str(e)}
    
    async def validate_service_integration(self) -> Dict[str, Any]:
        """Validate end-to-end service integration"""
        try:
            validation_results = {
                "overall_status": "healthy",
                "service_validations": {},
                "integration_tests": {},
                "issues": []
            }
            
            # Validate each service
            for service_name in self.routing_rules.values():
                validation = await service_registry.validate_service_dependencies(service_name)
                validation_results["service_validations"][service_name] = validation
                
                if not validation.get("valid", False):
                    validation_results["overall_status"] = "degraded"
                    validation_results["issues"].extend([
                        f"Service {service_name}: {issue}"
                        for issue in validation.get("missing_dependencies", []) + 
                                   validation.get("unhealthy_dependencies", [])
                    ])
            
            # Test critical integration paths
            integration_tests = [
                {
                    "name": "user_authentication_flow",
                    "services": ["user_service", "database", "redis"],
                    "description": "User login and session management"
                },
                {
                    "name": "analytics_computation_flow",
                    "services": ["analytics_service", "background_worker_service", "database"],
                    "description": "Analytics computation and caching"
                },
                {
                    "name": "recommendation_generation_flow",
                    "services": ["recommendation_service", "gap_analysis_service", "database"],
                    "description": "Learning gap analysis and recommendation generation"
                }
            ]
            
            for test in integration_tests:
                test_result = await self._test_integration_path(test)
                validation_results["integration_tests"][test["name"]] = test_result
                
                if not test_result.get("success", False):
                    validation_results["overall_status"] = "critical"
                    validation_results["issues"].append(
                        f"Integration test failed: {test['name']}"
                    )
            
            return validation_results
            
        except Exception as e:
            logger.error(f"Error validating service integration: {e}")
            return {"error": str(e)}
    
    async def _test_integration_path(self, test_config: Dict[str, Any]) -> Dict[str, Any]:
        """Test a specific integration path"""
        try:
            test_result = {
                "test_name": test_config["name"],
                "success": True,
                "services_tested": test_config["services"],
                "results": {},
                "errors": []
            }
            
            # Check each service in the integration path
            for service_name in test_config["services"]:
                service = await service_registry.get_service(service_name)
                
                if not service:
                    test_result["success"] = False
                    test_result["errors"].append(f"Service {service_name} not found")
                    test_result["results"][service_name] = "not_found"
                elif service.status != ServiceStatus.HEALTHY:
                    test_result["success"] = False
                    test_result["errors"].append(f"Service {service_name} is not healthy")
                    test_result["results"][service_name] = service.status.value
                else:
                    test_result["results"][service_name] = "healthy"
            
            return test_result
            
        except Exception as e:
            logger.error(f"Error testing integration path {test_config['name']}: {e}")
            return {
                "test_name": test_config["name"],
                "success": False,
                "error": str(e)
            }
    
    async def update_routing_rules(self, new_rules: Dict[str, str]) -> bool:
        """Update routing rules dynamically"""
        try:
            # Validate new rules
            for path, service_name in new_rules.items():
                service = await service_registry.get_service(service_name)
                if not service:
                    logger.warning(f"Service {service_name} not found for route {path}")
            
            # Update routing rules
            self.routing_rules.update(new_rules)
            
            # Cache updated rules
            await cache_manager.set_cache(
                "api_gateway_routing_rules",
                self.routing_rules,
                expire=3600
            )
            
            logger.info(f"Updated routing rules: {new_rules}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating routing rules: {e}")
            return False
    
    async def set_load_balancing_strategy(self, strategy: str) -> bool:
        """Set load balancing strategy"""
        try:
            if strategy not in self.load_balancing_strategies:
                return False
            
            self.current_strategy = strategy
            
            # Cache strategy setting
            await cache_manager.set_cache(
                "api_gateway_lb_strategy",
                strategy,
                expire=3600
            )
            
            logger.info(f"Load balancing strategy set to: {strategy}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting load balancing strategy: {e}")
            return False
    
    async def close(self):
        """Close the API gateway and cleanup resources"""
        try:
            await self.client.aclose()
            logger.info("API Gateway closed")
        except Exception as e:
            logger.error(f"Error closing API Gateway: {e}")


# Global API gateway instance
api_gateway = APIGateway()