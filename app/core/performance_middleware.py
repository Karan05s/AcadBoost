"""
Performance Monitoring Middleware
Tracks request performance metrics for monitoring and optimization
"""
import time
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.performance_monitoring_service import performance_monitoring_service

logger = logging.getLogger(__name__)


class PerformanceMiddleware(BaseHTTPMiddleware):
    """Middleware for tracking request performance metrics"""
    
    def __init__(self, app, track_all_requests: bool = True):
        super().__init__(app)
        self.track_all_requests = track_all_requests
        
        # Endpoints to exclude from tracking (health checks, etc.)
        self.excluded_paths = {
            "/health",
            "/",
            "/docs",
            "/openapi.json",
            "/redoc"
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and track performance metrics"""
        
        # Skip tracking for excluded paths
        if not self.track_all_requests or request.url.path in self.excluded_paths:
            return await call_next(request)
        
        # Track request start
        start_time = time.time()
        performance_monitoring_service.track_request_start()
        
        # Add request start time to request state
        request.state.start_time = start_time
        
        try:
            # Process the request
            response = await call_next(request)
            
            # Calculate response time
            response_time = time.time() - start_time
            
            # Determine if request was successful
            success = 200 <= response.status_code < 400
            
            # Track request completion
            performance_monitoring_service.track_request_end(response_time, success)
            
            # Add performance headers to response
            response.headers["X-Response-Time"] = f"{response_time:.3f}s"
            response.headers["X-Request-ID"] = getattr(request.state, "request_id", "unknown")
            
            # Log slow requests
            if response_time > 2.0:  # Log requests slower than 2 seconds
                logger.warning(
                    f"Slow request: {request.method} {request.url.path} "
                    f"took {response_time:.3f}s (status: {response.status_code})"
                )
            
            return response
            
        except Exception as e:
            # Calculate response time for failed requests
            response_time = time.time() - start_time
            
            # Track failed request
            performance_monitoring_service.track_request_end(response_time, success=False)
            
            # Log the error
            logger.error(
                f"Request failed: {request.method} {request.url.path} "
                f"after {response_time:.3f}s - {str(e)}"
            )
            
            # Re-raise the exception
            raise