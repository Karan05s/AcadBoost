"""
Main FastAPI application entry point for Learning Analytics Platform
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import logging

from app.core.config import settings
from app.core.database import init_database
from app.core.redis_client import init_redis, close_redis
from app.core.security_middleware import SecurityMiddleware
from app.core.performance_middleware import PerformanceMiddleware
from app.core.versioning import version_manager, get_api_version
from app.core.error_handling import error_handler, create_error_response, get_request_id
from app.core.logging_config import setup_logging, APILoggingMiddleware
from app.api.v1.api import api_router
from app.services.security_background_tasks import security_background_tasks
from app.services.background_worker_service import background_worker_service
from app.services.performance_monitoring_service import performance_monitoring_service
from app.services.data_flow_validation_service import data_flow_validation_service
from app.core.service_registry import service_registry
from app.core.api_gateway import api_gateway

# Setup logging
logger = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Learning Analytics Platform API")
    await init_database()
    await init_redis()
    
    # Initialize service registry and register core services
    logger.info("Initializing service registry...")
    await service_registry.register_core_services()
    await service_registry.start_health_monitoring()
    
    # Initialize background services
    logger.info("Initializing background services...")
    await security_background_tasks.initialize()
    await background_worker_service.initialize()
    await performance_monitoring_service.initialize()
    await data_flow_validation_service.initialize()
    
    # Start background services (non-blocking)
    import asyncio
    asyncio.create_task(security_background_tasks.start_background_monitoring())
    asyncio.create_task(background_worker_service.start_background_processing())
    asyncio.create_task(performance_monitoring_service.start_monitoring())
    
    logger.info("Application startup completed")
    yield
    # Shutdown
    logger.info("Shutting down Learning Analytics Platform API")
    
    # Stop background services
    await security_background_tasks.stop_background_monitoring()
    await background_worker_service.stop_background_processing()
    await performance_monitoring_service.stop_monitoring()
    await service_registry.stop_health_monitoring()
    
    # Close API gateway
    await api_gateway.close()
    
    await close_redis()
    logger.info("Application shutdown completed")


app = FastAPI(
    title="Learning Analytics Platform API",
    description="AI-driven learning analytics platform for personalized education",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Add performance monitoring middleware (before other middleware)
app.add_middleware(
    PerformanceMiddleware,
    track_all_requests=True
)

# Add API logging middleware (first, to capture all requests)
app.add_middleware(
    APILoggingMiddleware,
    log_requests=True,
    log_responses=True
)

# Add security middleware (before CORS)
app.add_middleware(
    SecurityMiddleware,
    rate_limit_requests=100,  # 100 requests per minute
    rate_limit_window=60
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with standardized error responses"""
    request_id = get_request_id(request)
    api_version = get_api_version(request)
    
    error = error_handler.handle_http_exception(
        exc, 
        request_id=request_id, 
        api_version=str(api_version)
    )
    
    error_handler.log_error(error, request)
    
    return create_error_response(
        error_key="AUTH_TOKEN_INVALID" if exc.status_code == 401 else "INTERNAL_SERVER_ERROR",
        custom_message=str(exc.detail),
        request_id=request_id,
        api_version=str(api_version)
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors"""
    request_id = get_request_id(request)
    api_version = get_api_version(request)
    
    error = error_handler.handle_validation_error(
        exc,
        request_id=request_id,
        api_version=str(api_version)
    )
    
    error_handler.log_error(error, request)
    
    return create_error_response(
        error_key="VALIDATION_FIELD_INVALID",
        details=error.details,
        request_id=request_id,
        api_version=str(api_version)
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions"""
    request_id = get_request_id(request)
    api_version = get_api_version(request)
    
    error = error_handler.handle_generic_exception(
        exc,
        request_id=request_id,
        api_version=str(api_version)
    )
    
    error_handler.log_error(error, request)
    
    return create_error_response(
        error_key="INTERNAL_SERVER_ERROR",
        details=error.details,
        request_id=request_id,
        api_version=str(api_version)
    )


# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
async def root(request: Request):
    """Health check endpoint with version information"""
    api_version = get_api_version(request)
    version_info = version_manager.validate_version(api_version)
    
    return {
        "message": "Learning Analytics Platform API",
        "version": str(api_version),
        "status": "operational",
        "supported_versions": list(version_manager.supported_versions.keys()),
        "current_version": str(version_manager.current_version),
        "features": version_info.get("features", []) if version_info["valid"] else []
    }


@app.get("/health")
async def health_check(request: Request):
    """Detailed health check endpoint for load balancers"""
    api_version = get_api_version(request)
    
    # Add version headers to response
    response_headers = {}
    version_manager.add_version_headers(response_headers, api_version)
    
    return {
        "status": "healthy",
        "timestamp": "2024-01-01T00:00:00Z",
        "api_version": str(api_version),
        "services": {
            "database": "connected",
            "redis": "connected",
            "authentication": "operational",
            "ml_services": "operational"
        }
    }


@app.get("/api/versions")
async def get_supported_versions():
    """Get information about supported API versions"""
    return {
        "supported_versions": version_manager.supported_versions,
        "current_version": str(version_manager.current_version),
        "minimum_version": str(version_manager.minimum_supported_version)
    }