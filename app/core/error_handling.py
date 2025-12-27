"""
Comprehensive Error Handling System
Provides standardized error responses and logging
"""
from typing import Dict, Any, Optional, List, Union
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from datetime import datetime
import logging
import traceback
import uuid
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """Error categories for classification"""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMIT = "rate_limit"
    EXTERNAL_SERVICE = "external_service"
    DATABASE = "database"
    INTERNAL = "internal"
    BUSINESS_LOGIC = "business_logic"


class ErrorSeverity(str, Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class APIError(BaseModel):
    """Standardized API error response model"""
    error_id: str
    error_code: str
    error_category: ErrorCategory
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime
    api_version: str
    request_id: Optional[str] = None
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    
    # Additional context for debugging (only in development)
    debug_info: Optional[Dict[str, Any]] = None


class ValidationErrorDetail(BaseModel):
    """Detailed validation error information"""
    field: str
    message: str
    invalid_value: Any
    constraint: Optional[str] = None


class ErrorHandler:
    """Centralized error handling system"""
    
    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode
        self.error_codes = {
            # Authentication errors (1000-1099)
            "AUTH_TOKEN_MISSING": {
                "code": "AUTH_1001",
                "message": "Authentication token is required",
                "category": ErrorCategory.AUTHENTICATION,
                "severity": ErrorSeverity.MEDIUM
            },
            "AUTH_TOKEN_INVALID": {
                "code": "AUTH_1002",
                "message": "Invalid authentication token",
                "category": ErrorCategory.AUTHENTICATION,
                "severity": ErrorSeverity.MEDIUM
            },
            "AUTH_TOKEN_EXPIRED": {
                "code": "AUTH_1003",
                "message": "Authentication token has expired",
                "category": ErrorCategory.AUTHENTICATION,
                "severity": ErrorSeverity.MEDIUM
            },
            "AUTH_CREDENTIALS_INVALID": {
                "code": "AUTH_1004",
                "message": "Invalid credentials provided",
                "category": ErrorCategory.AUTHENTICATION,
                "severity": ErrorSeverity.MEDIUM
            },
            
            # Authorization errors (1100-1199)
            "AUTHZ_INSUFFICIENT_PERMISSIONS": {
                "code": "AUTHZ_1101",
                "message": "Insufficient permissions for this operation",
                "category": ErrorCategory.AUTHORIZATION,
                "severity": ErrorSeverity.MEDIUM
            },
            "AUTHZ_ROLE_REQUIRED": {
                "code": "AUTHZ_1102",
                "message": "Required role not found",
                "category": ErrorCategory.AUTHORIZATION,
                "severity": ErrorSeverity.MEDIUM
            },
            "AUTHZ_DATA_ACCESS_DENIED": {
                "code": "AUTHZ_1103",
                "message": "Access denied to requested data",
                "category": ErrorCategory.AUTHORIZATION,
                "severity": ErrorSeverity.HIGH
            },
            
            # Validation errors (1200-1299)
            "VALIDATION_FIELD_REQUIRED": {
                "code": "VAL_1201",
                "message": "Required field is missing",
                "category": ErrorCategory.VALIDATION,
                "severity": ErrorSeverity.LOW
            },
            "VALIDATION_FIELD_INVALID": {
                "code": "VAL_1202",
                "message": "Field value is invalid",
                "category": ErrorCategory.VALIDATION,
                "severity": ErrorSeverity.LOW
            },
            "VALIDATION_DATA_INTEGRITY": {
                "code": "VAL_1203",
                "message": "Data integrity validation failed",
                "category": ErrorCategory.VALIDATION,
                "severity": ErrorSeverity.MEDIUM
            },
            
            # Resource errors (1300-1399)
            "RESOURCE_NOT_FOUND": {
                "code": "RES_1301",
                "message": "Requested resource not found",
                "category": ErrorCategory.NOT_FOUND,
                "severity": ErrorSeverity.LOW
            },
            "RESOURCE_ALREADY_EXISTS": {
                "code": "RES_1302",
                "message": "Resource already exists",
                "category": ErrorCategory.CONFLICT,
                "severity": ErrorSeverity.LOW
            },
            
            # Rate limiting errors (1400-1499)
            "RATE_LIMIT_EXCEEDED": {
                "code": "RATE_1401",
                "message": "Rate limit exceeded",
                "category": ErrorCategory.RATE_LIMIT,
                "severity": ErrorSeverity.MEDIUM
            },
            "RATE_LIMIT_BURST_EXCEEDED": {
                "code": "RATE_1402",
                "message": "Burst rate limit exceeded",
                "category": ErrorCategory.RATE_LIMIT,
                "severity": ErrorSeverity.MEDIUM
            },
            
            # External service errors (1500-1599)
            "EXTERNAL_SERVICE_UNAVAILABLE": {
                "code": "EXT_1501",
                "message": "External service is unavailable",
                "category": ErrorCategory.EXTERNAL_SERVICE,
                "severity": ErrorSeverity.HIGH
            },
            "EXTERNAL_SERVICE_TIMEOUT": {
                "code": "EXT_1502",
                "message": "External service request timed out",
                "category": ErrorCategory.EXTERNAL_SERVICE,
                "severity": ErrorSeverity.MEDIUM
            },
            
            # Database errors (1600-1699)
            "DATABASE_CONNECTION_ERROR": {
                "code": "DB_1601",
                "message": "Database connection failed",
                "category": ErrorCategory.DATABASE,
                "severity": ErrorSeverity.CRITICAL
            },
            "DATABASE_QUERY_ERROR": {
                "code": "DB_1602",
                "message": "Database query failed",
                "category": ErrorCategory.DATABASE,
                "severity": ErrorSeverity.HIGH
            },
            
            # Business logic errors (1700-1799)
            "BUSINESS_RULE_VIOLATION": {
                "code": "BIZ_1701",
                "message": "Business rule violation",
                "category": ErrorCategory.BUSINESS_LOGIC,
                "severity": ErrorSeverity.MEDIUM
            },
            "INSUFFICIENT_DATA": {
                "code": "BIZ_1702",
                "message": "Insufficient data for operation",
                "category": ErrorCategory.BUSINESS_LOGIC,
                "severity": ErrorSeverity.LOW
            },
            
            # Internal errors (1800-1899)
            "INTERNAL_SERVER_ERROR": {
                "code": "INT_1801",
                "message": "Internal server error occurred",
                "category": ErrorCategory.INTERNAL,
                "severity": ErrorSeverity.CRITICAL
            },
            "CONFIGURATION_ERROR": {
                "code": "INT_1802",
                "message": "System configuration error",
                "category": ErrorCategory.INTERNAL,
                "severity": ErrorSeverity.HIGH
            }
        }
    
    def create_error_response(
        self,
        error_key: str,
        details: Optional[Dict[str, Any]] = None,
        custom_message: Optional[str] = None,
        request_id: Optional[str] = None,
        api_version: str = "1.0.0"
    ) -> APIError:
        """Create standardized error response"""
        
        if error_key not in self.error_codes:
            # Fallback to internal error
            error_key = "INTERNAL_SERVER_ERROR"
        
        error_info = self.error_codes[error_key]
        error_id = str(uuid.uuid4())
        
        # Use custom message if provided
        message = custom_message or error_info["message"]
        
        error_response = APIError(
            error_id=error_id,
            error_code=error_info["code"],
            error_category=error_info["category"],
            message=message,
            details=details,
            timestamp=datetime.utcnow(),
            api_version=api_version,
            request_id=request_id,
            severity=error_info["severity"]
        )
        
        # Add debug info in development mode
        if self.debug_mode and details:
            error_response.debug_info = {
                "error_key": error_key,
                "stack_trace": details.get("stack_trace"),
                "additional_context": details.get("debug_context")
            }
        
        return error_response
    
    def handle_validation_error(
        self,
        validation_error: Union[RequestValidationError, ValidationError],
        request_id: Optional[str] = None,
        api_version: str = "1.0.0"
    ) -> APIError:
        """Handle Pydantic validation errors"""
        
        validation_details = []
        
        for error in validation_error.errors():
            field_path = " -> ".join(str(loc) for loc in error["loc"])
            validation_details.append(
                ValidationErrorDetail(
                    field=field_path,
                    message=error["msg"],
                    invalid_value=error.get("input"),
                    constraint=error.get("type")
                ).dict()
            )
        
        return self.create_error_response(
            error_key="VALIDATION_FIELD_INVALID",
            details={
                "validation_errors": validation_details,
                "error_count": len(validation_details)
            },
            request_id=request_id,
            api_version=api_version
        )
    
    def handle_http_exception(
        self,
        http_exception: HTTPException,
        request_id: Optional[str] = None,
        api_version: str = "1.0.0"
    ) -> APIError:
        """Handle FastAPI HTTP exceptions"""
        
        # Map HTTP status codes to error keys
        status_code_mapping = {
            401: "AUTH_TOKEN_INVALID",
            403: "AUTHZ_INSUFFICIENT_PERMISSIONS",
            404: "RESOURCE_NOT_FOUND",
            409: "RESOURCE_ALREADY_EXISTS",
            429: "RATE_LIMIT_EXCEEDED",
            500: "INTERNAL_SERVER_ERROR"
        }
        
        error_key = status_code_mapping.get(http_exception.status_code, "INTERNAL_SERVER_ERROR")
        
        return self.create_error_response(
            error_key=error_key,
            custom_message=str(http_exception.detail),
            details={"status_code": http_exception.status_code},
            request_id=request_id,
            api_version=api_version
        )
    
    def handle_generic_exception(
        self,
        exception: Exception,
        request_id: Optional[str] = None,
        api_version: str = "1.0.0"
    ) -> APIError:
        """Handle generic exceptions"""
        
        details = {
            "exception_type": type(exception).__name__,
            "exception_message": str(exception)
        }
        
        if self.debug_mode:
            details["stack_trace"] = traceback.format_exc()
        
        return self.create_error_response(
            error_key="INTERNAL_SERVER_ERROR",
            details=details,
            request_id=request_id,
            api_version=api_version
        )
    
    def log_error(self, error: APIError, request: Optional[Request] = None):
        """Log error with appropriate level based on severity"""
        
        log_data = {
            "error_id": error.error_id,
            "error_code": error.error_code,
            "category": error.error_category,
            "message": error.message,
            "severity": error.severity,
            "timestamp": error.timestamp.isoformat()
        }
        
        if request:
            log_data.update({
                "method": request.method,
                "url": str(request.url),
                "client_ip": request.client.host if request.client else "unknown",
                "user_agent": request.headers.get("user-agent")
            })
        
        if error.details:
            log_data["details"] = error.details
        
        # Log with appropriate level
        if error.severity == ErrorSeverity.CRITICAL:
            logger.critical("Critical error occurred", extra=log_data)
        elif error.severity == ErrorSeverity.HIGH:
            logger.error("High severity error occurred", extra=log_data)
        elif error.severity == ErrorSeverity.MEDIUM:
            logger.warning("Medium severity error occurred", extra=log_data)
        else:
            logger.info("Low severity error occurred", extra=log_data)


# Global error handler instance
error_handler = ErrorHandler(debug_mode=False)  # Set based on environment


def create_error_response(
    error_key: str,
    details: Optional[Dict[str, Any]] = None,
    custom_message: Optional[str] = None,
    request_id: Optional[str] = None,
    api_version: str = "1.0.0"
) -> JSONResponse:
    """Create JSON error response"""
    
    error = error_handler.create_error_response(
        error_key=error_key,
        details=details,
        custom_message=custom_message,
        request_id=request_id,
        api_version=api_version
    )
    
    # Map error category to HTTP status code
    status_code_mapping = {
        ErrorCategory.AUTHENTICATION: status.HTTP_401_UNAUTHORIZED,
        ErrorCategory.AUTHORIZATION: status.HTTP_403_FORBIDDEN,
        ErrorCategory.VALIDATION: status.HTTP_400_BAD_REQUEST,
        ErrorCategory.NOT_FOUND: status.HTTP_404_NOT_FOUND,
        ErrorCategory.CONFLICT: status.HTTP_409_CONFLICT,
        ErrorCategory.RATE_LIMIT: status.HTTP_429_TOO_MANY_REQUESTS,
        ErrorCategory.EXTERNAL_SERVICE: status.HTTP_502_BAD_GATEWAY,
        ErrorCategory.DATABASE: status.HTTP_503_SERVICE_UNAVAILABLE,
        ErrorCategory.BUSINESS_LOGIC: status.HTTP_422_UNPROCESSABLE_ENTITY,
        ErrorCategory.INTERNAL: status.HTTP_500_INTERNAL_SERVER_ERROR
    }
    
    http_status = status_code_mapping.get(error.error_category, status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return JSONResponse(
        status_code=http_status,
        content=error.dict(exclude_none=True),
        headers={
            "X-Error-ID": error.error_id,
            "X-Error-Code": error.error_code
        }
    )


def get_request_id(request: Request) -> str:
    """Get or generate request ID"""
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    return request_id