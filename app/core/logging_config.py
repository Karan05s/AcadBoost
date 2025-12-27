"""
Comprehensive API Logging Configuration
Provides structured logging for API requests, responses, and errors
"""
import logging
import logging.config
import json
import time
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import uuid

# Structured logging formatter
class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add extra fields if present
        if hasattr(record, 'request_id'):
            log_entry['request_id'] = record.request_id
        
        if hasattr(record, 'user_id'):
            log_entry['user_id'] = record.user_id
        
        if hasattr(record, 'api_version'):
            log_entry['api_version'] = record.api_version
        
        if hasattr(record, 'error_id'):
            log_entry['error_id'] = record.error_id
        
        if hasattr(record, 'performance_metrics'):
            log_entry['performance_metrics'] = record.performance_metrics
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry)


# Logging configuration
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": JSONFormatter,
        },
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        }
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout"
        },
        "file": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "json",
            "filename": "logs/api.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5
        },
        "error_file": {
            "level": "ERROR",
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "json",
            "filename": "logs/errors.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 10
        }
    },
    "loggers": {
        "app": {
            "level": "DEBUG",
            "handlers": ["console", "file", "error_file"],
            "propagate": False
        },
        "uvicorn": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False
        },
        "uvicorn.error": {
            "level": "INFO",
            "handlers": ["console", "error_file"],
            "propagate": False
        },
        "uvicorn.access": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False
        }
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"]
    }
}


class APILoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for comprehensive API request/response logging"""
    
    def __init__(self, app, log_requests: bool = True, log_responses: bool = True):
        super().__init__(app)
        self.log_requests = log_requests
        self.log_responses = log_responses
        self.logger = logging.getLogger("app.api")
    
    async def dispatch(self, request: Request, call_next):
        """Log API requests and responses"""
        start_time = time.time()
        request_id = self._get_request_id(request)
        
        # Log incoming request
        if self.log_requests:
            await self._log_request(request, request_id)
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Add headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time)
            
            # Log response
            if self.log_responses:
                await self._log_response(request, response, request_id, process_time)
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            
            # Log exception
            self.logger.error(
                f"Request processing failed: {str(e)}",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "url": str(request.url),
                    "process_time": process_time,
                    "exception_type": type(e).__name__
                },
                exc_info=True
            )
            
            raise
    
    def _get_request_id(self, request: Request) -> str:
        """Get or generate request ID"""
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())
        return request_id
    
    async def _log_request(self, request: Request, request_id: str):
        """Log incoming request details"""
        # Get client information
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Get API version
        api_version = request.headers.get("X-API-Version", "1.0.0")
        
        # Log request
        self.logger.info(
            f"Incoming request: {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "url": str(request.url),
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "client_ip": client_ip,
                "user_agent": user_agent,
                "api_version": api_version,
                "headers": dict(request.headers),
                "event_type": "request_received"
            }
        )
    
    async def _log_response(
        self,
        request: Request,
        response: Response,
        request_id: str,
        process_time: float
    ):
        """Log response details"""
        # Get client information
        client_ip = self._get_client_ip(request)
        
        # Get API version
        api_version = request.headers.get("X-API-Version", "1.0.0")
        
        # Determine log level based on status code
        if response.status_code >= 500:
            log_level = logging.ERROR
        elif response.status_code >= 400:
            log_level = logging.WARNING
        else:
            log_level = logging.INFO
        
        # Log response
        self.logger.log(
            log_level,
            f"Response sent: {response.status_code} for {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "url": str(request.url),
                "path": request.url.path,
                "status_code": response.status_code,
                "client_ip": client_ip,
                "api_version": api_version,
                "process_time": process_time,
                "response_headers": dict(response.headers),
                "event_type": "response_sent",
                "performance_metrics": {
                    "process_time_ms": round(process_time * 1000, 2),
                    "status_code": response.status_code
                }
            }
        )
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address"""
        # Check for forwarded headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"


class PerformanceLogger:
    """Logger for performance metrics"""
    
    def __init__(self):
        self.logger = logging.getLogger("app.performance")
    
    def log_database_query(
        self,
        query_type: str,
        collection: str,
        duration: float,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        """Log database query performance"""
        self.logger.info(
            f"Database query executed: {query_type} on {collection}",
            extra={
                "request_id": request_id,
                "user_id": user_id,
                "query_type": query_type,
                "collection": collection,
                "duration_ms": round(duration * 1000, 2),
                "event_type": "database_query",
                "performance_metrics": {
                    "query_duration_ms": round(duration * 1000, 2),
                    "query_type": query_type,
                    "collection": collection
                }
            }
        )
    
    def log_ml_inference(
        self,
        model_name: str,
        duration: float,
        input_size: int,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        """Log ML model inference performance"""
        self.logger.info(
            f"ML inference completed: {model_name}",
            extra={
                "request_id": request_id,
                "user_id": user_id,
                "model_name": model_name,
                "duration_ms": round(duration * 1000, 2),
                "input_size": input_size,
                "event_type": "ml_inference",
                "performance_metrics": {
                    "inference_duration_ms": round(duration * 1000, 2),
                    "model_name": model_name,
                    "input_size": input_size
                }
            }
        )
    
    def log_cache_operation(
        self,
        operation: str,
        key: str,
        hit: bool,
        duration: float,
        request_id: Optional[str] = None
    ):
        """Log cache operation performance"""
        self.logger.info(
            f"Cache {operation}: {'HIT' if hit else 'MISS'} for key {key}",
            extra={
                "request_id": request_id,
                "operation": operation,
                "cache_key": key,
                "cache_hit": hit,
                "duration_ms": round(duration * 1000, 2),
                "event_type": "cache_operation",
                "performance_metrics": {
                    "cache_duration_ms": round(duration * 1000, 2),
                    "cache_hit": hit,
                    "operation": operation
                }
            }
        )


class SecurityLogger:
    """Logger for security events"""
    
    def __init__(self):
        self.logger = logging.getLogger("app.security")
    
    def log_authentication_attempt(
        self,
        username: str,
        success: bool,
        client_ip: str,
        user_agent: str,
        request_id: Optional[str] = None
    ):
        """Log authentication attempts"""
        log_level = logging.INFO if success else logging.WARNING
        
        self.logger.log(
            log_level,
            f"Authentication {'successful' if success else 'failed'} for user {username}",
            extra={
                "request_id": request_id,
                "username": username,
                "success": success,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "event_type": "authentication_attempt"
            }
        )
    
    def log_authorization_failure(
        self,
        user_id: str,
        resource: str,
        action: str,
        client_ip: str,
        request_id: Optional[str] = None
    ):
        """Log authorization failures"""
        self.logger.warning(
            f"Authorization failed: user {user_id} attempted {action} on {resource}",
            extra={
                "request_id": request_id,
                "user_id": user_id,
                "resource": resource,
                "action": action,
                "client_ip": client_ip,
                "event_type": "authorization_failure"
            }
        )
    
    def log_suspicious_activity(
        self,
        activity_type: str,
        client_ip: str,
        details: Dict[str, Any],
        request_id: Optional[str] = None
    ):
        """Log suspicious activities"""
        self.logger.error(
            f"Suspicious activity detected: {activity_type}",
            extra={
                "request_id": request_id,
                "activity_type": activity_type,
                "client_ip": client_ip,
                "details": details,
                "event_type": "suspicious_activity"
            }
        )


def setup_logging():
    """Setup logging configuration"""
    import os
    
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Apply logging configuration
    logging.config.dictConfig(LOGGING_CONFIG)
    
    # Create logger instances
    logger = logging.getLogger("app")
    logger.info("Logging system initialized")
    
    return logger


# Global logger instances
performance_logger = PerformanceLogger()
security_logger = SecurityLogger()